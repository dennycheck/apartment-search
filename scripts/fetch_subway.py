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


def build_stations(zf: zipfile.ZipFile) -> dict:
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
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "stop_id": s["stop_id"],
                        "name": s.get("stop_name") or s["stop_id"],
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(s["stop_lon"]), float(s["stop_lat"])],
                    },
                }
            )

    # Deduplicate near-identical station names at same complex by rounding coords.
    seen: set[tuple] = set()
    uniq = []
    for f in features:
        lon, lat = f["geometry"]["coordinates"]
        key = (f["properties"]["name"], round(lon, 4), round(lat, 4))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)

    return {"type": "FeatureCollection", "features": uniq}


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
