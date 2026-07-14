#!/usr/bin/env python3
"""Geocode configured POIs and assign commute bands."""

import json
import sys
import time
from pathlib import Path

from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ISOCHRONES_PATH, POIS, POIS_JSON
from scripts.process_listings import geocode_address, load_isochrones, minutes_in_zone


def process_pois(pois: list[dict], bands: dict[int, object]) -> list[dict]:
    processed = []
    for i, poi in enumerate(pois, start=1):
        address = poi["address"]
        print(f"  [{i}/{len(pois)}] Geocoding: {address}")

        coords = geocode_address(address)
        if coords is None:
            print("    ✗ Could not geocode")
            processed.append(
                {
                    **poi,
                    "lat": None,
                    "lng": None,
                    "commute_min": None,
                    "geocode_error": True,
                }
            )
        else:
            lat, lng = coords
            commute_min = minutes_in_zone(Point(lng, lat), bands)
            status = f"≤{commute_min} min" if commute_min else "out of zone"
            print(f"    ✓ {lat:.5f}, {lng:.5f} — {status}")
            processed.append(
                {
                    **poi,
                    "lat": lat,
                    "lng": lng,
                    "commute_min": commute_min,
                    "geocode_error": False,
                }
            )

        if i < len(pois):
            time.sleep(1.1)

    return processed


def main():
    print("Loading isochrones…")
    bands = load_isochrones(ISOCHRONES_PATH)
    print(f"  Bands loaded: {sorted(bands.keys())}")

    print(f"Geocoding {len(POIS)} POI(s)…")
    processed = process_pois(POIS, bands)

    POIS_JSON.parent.mkdir(parents=True, exist_ok=True)
    POIS_JSON.write_text(json.dumps(processed, indent=2))
    print(f"Saved → {POIS_JSON}")


if __name__ == "__main__":
    main()
