#!/usr/bin/env python3
"""Normalize a TravelTime playground GeoJSON response for this project."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ISOCHRONES_PATH


def minutes_from_search_id(search_id: str) -> int | None:
    if not search_id:
        return None
    match = re.search(r"(\d+)\s*_?\s*min", search_id, re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)", search_id)
    if match:
        val = int(match.group(1))
        return val if val <= 120 else None
    return None


def normalize(data: dict) -> dict:
    if data.get("type") != "FeatureCollection":
        if "results" in data:
            raise ValueError(
                "Response is default JSON, not GeoJSON. "
                "Re-run playground with Accept: application/geo+json"
            )
        raise ValueError("Expected a GeoJSON FeatureCollection")

    for feature in data.get("features", []):
        props = feature.setdefault("properties", {})
        if "minutes" not in props:
            minutes = minutes_from_search_id(props.get("search_id", ""))
            if minutes:
                props["minutes"] = minutes

    return data


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_geojson.py <playground-response.json>", file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1])
    data = json.loads(src.read_text())
    data = normalize(data)

    annotated = sum(1 for f in data.get("features", []) if f.get("properties", {}).get("minutes"))
    if annotated == 0:
        print("Warning: no features got a 'minutes' property — check search IDs in the file", file=sys.stderr)

    ISOCHRONES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ISOCHRONES_PATH.write_text(json.dumps(data, indent=2))
    print(f"Saved {len(data.get('features', []))} features ({annotated} with minutes) → {ISOCHRONES_PATH}")


if __name__ == "__main__":
    main()
