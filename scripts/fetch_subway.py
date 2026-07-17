#!/usr/bin/env python3
"""Download MTA subway GTFS and write compact line/station GeoJSON for the map."""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR

GTFS_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip"
OUT_DIR = DATA_DIR / "subway"
LINES_PATH = OUT_DIR / "lines.geojson"
STATIONS_PATH = OUT_DIR / "stations.geojson"

# Keep embedded HTML small: keep ~every Nth shape vertex.
SHAPE_STRIDE = 3


def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    with zf.open(name) as f:
        text = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(text))


def build_lines(zf: zipfile.ZipFile) -> dict:
    routes = {r["route_id"]: r for r in _read_csv(zf, "routes.txt")}
    trips = _read_csv(zf, "trips.txt")

    # Longest shape per route (enough to draw each line once).
    shape_len: dict[str, int] = defaultdict(int)
    with zf.open("shapes.txt") as f:
        text = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
        for row in csv.DictReader(text):
            shape_len[row["shape_id"]] += 1

    best_shape: dict[str, str] = {}
    for t in trips:
        rid, sid = t["route_id"], t.get("shape_id") or ""
        if not sid:
            continue
        prev = best_shape.get(rid)
        if prev is None or shape_len[sid] > shape_len[prev]:
            best_shape[rid] = sid

    wanted = set(best_shape.values())
    coords_by_shape: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    with zf.open("shapes.txt") as f:
        text = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
        for row in csv.DictReader(text):
            sid = row["shape_id"]
            if sid not in wanted:
                continue
            coords_by_shape[sid].append(
                (int(row["shape_pt_sequence"]), float(row["shape_pt_lon"]), float(row["shape_pt_lat"]))
            )

    features = []
    for rid, sid in sorted(best_shape.items()):
        pts = sorted(coords_by_shape[sid])
        line = [[lon, lat] for i, (_, lon, lat) in enumerate(pts) if i % SHAPE_STRIDE == 0 or i == len(pts) - 1]
        if len(line) < 2:
            continue
        r = routes.get(rid, {})
        color = (r.get("route_color") or "888888").lstrip("#")
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "route_id": rid,
                    "name": r.get("route_short_name") or rid,
                    "long_name": r.get("route_long_name") or "",
                    "color": f"#{color}",
                },
                "geometry": {"type": "LineString", "coordinates": line},
            }
        )

    return {"type": "FeatureCollection", "features": features}


def _route_meta(zf: zipfile.ZipFile) -> dict[str, dict]:
    out = {}
    for r in _read_csv(zf, "routes.txt"):
        color = (r.get("route_color") or "888888").lstrip("#")
        out[r["route_id"]] = {
            "name": r.get("route_short_name") or r["route_id"],
            "color": f"#{color}",
        }
    return out


def _routes_by_station(zf: zipfile.ZipFile) -> dict[str, set[str]]:
    """Map station stop_id → set of route_ids that stop there (via platforms)."""
    stops = _read_csv(zf, "stops.txt")
    stop_to_station: dict[str, str] = {}
    for s in stops:
        sid = s["stop_id"]
        parent = (s.get("parent_station") or "").strip()
        loc = (s.get("location_type") or "").strip()
        if loc == "1":
            stop_to_station[sid] = sid
        elif parent:
            stop_to_station[sid] = parent
        else:
            stop_to_station[sid] = sid

    trip_route = {t["trip_id"]: t["route_id"] for t in _read_csv(zf, "trips.txt")}
    station_routes: dict[str, set[str]] = defaultdict(set)
    with zf.open("stop_times.txt") as f:
        text = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
        for row in csv.DictReader(text):
            rid = trip_route.get(row["trip_id"])
            if not rid:
                continue
            station = stop_to_station.get(row["stop_id"])
            if station:
                station_routes[station].add(rid)
    return station_routes


def build_stations(zf: zipfile.ZipFile) -> dict:
    routes = _route_meta(zf)
    station_routes = _routes_by_station(zf)
    stops = _read_csv(zf, "stops.txt")
    features = []
    for s in stops:
        # Prefer station nodes; skip entrances / child platforms.
        loc = (s.get("location_type") or "").strip()
        parent = (s.get("parent_station") or "").strip()
        if loc == "1" or (loc in ("", "0") and not parent):
            if loc == "0" and parent:
                continue
            if loc == "" and parent:
                continue
            stop_id = s["stop_id"]
            served = []
            for rid in sorted(station_routes.get(stop_id, ()), key=lambda x: routes.get(x, {}).get("name") or x):
                meta = routes.get(rid)
                if meta:
                    served.append(meta)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "stop_id": stop_id,
                        "name": s.get("stop_name") or stop_id,
                        "routes": served,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(s["stop_lon"]), float(s["stop_lat"])],
                    },
                }
            )

    # Merge same-name stations that sit near each other (transfer complexes).
    # Keep one point; union route lists so tooltips show every line that stops there.
    MERGE_DEG = 0.0025  # ~250m
    merged: list[dict] = []
    for f in features:
        name = f["properties"]["name"]
        lon, lat = f["geometry"]["coordinates"]
        routes = list(f["properties"].get("routes") or [])
        found = None
        for m in merged:
            if m["properties"]["name"] != name:
                continue
            mlon, mlat = m["geometry"]["coordinates"]
            if abs(mlon - lon) <= MERGE_DEG and abs(mlat - lat) <= MERGE_DEG:
                found = m
                break
        if found is None:
            merged.append(f)
            continue
        existing = found["properties"].setdefault("routes", [])
        seen_names = {r["name"] for r in existing}
        for r in routes:
            if r["name"] not in seen_names:
                existing.append(r)
                seen_names.add(r["name"])
        existing.sort(key=lambda r: r["name"])

    return {"type": "FeatureCollection", "features": merged}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {GTFS_URL} …")
    req = urllib.request.Request(GTFS_URL, headers={"User-Agent": "apartment-search/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        blob = resp.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        lines = build_lines(zf)
        stations = build_stations(zf)
    LINES_PATH.write_text(json.dumps(lines))
    STATIONS_PATH.write_text(json.dumps(stations))
    print(f"Lines → {LINES_PATH} ({len(lines['features'])} routes)")
    print(f"Stations → {STATIONS_PATH} ({len(stations['features'])} stops)")


if __name__ == "__main__":
    main()
