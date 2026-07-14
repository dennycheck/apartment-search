#!/usr/bin/env python3
"""Geocode CSV listings and filter by commute isochrone bands."""

import csv
import json
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DEFAULT_COMMUTE_MAX,
    ISOCHRONES_PATH,
    LISTINGS_CSV,
    LISTINGS_JSON,
    NOMINATIM_URL,
    NOMINATIM_USER_AGENT,
)
from scripts.listing_utils import read_listings_csv


def load_isochrones(path: Path) -> dict[int, object]:
    """Load isochrone polygons keyed by minutes."""
    if not path.exists():
        raise FileNotFoundError(
            f"Isochrones not found at {path}. Run: python scripts/fetch_isochrones.py"
        )

    data = json.loads(path.read_text())
    bands = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        minutes = props.get("minutes")
        if minutes is None and props.get("search_id", "").endswith("_min"):
            minutes = int(props["search_id"].replace("_min", ""))
        if minutes is not None:
            bands[int(minutes)] = shape(feature["geometry"])
    return bands


def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocode a NYC-area address via Nominatim (free, rate-limited)."""
    params = {
        "q": address if "NY" in address.upper() else f"{address}, New York, NY",
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }
    headers = {"User-Agent": NOMINATIM_USER_AGENT}

    response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    results = response.json()
    if not results:
        return None

    return float(results[0]["lat"]), float(results[0]["lon"])


def minutes_in_zone(point: Point, bands: dict[int, object]) -> int | None:
    """Return the smallest band (minutes) that contains the point, or None."""
    for minutes in sorted(bands):
        if bands[minutes].contains(point):
            return minutes
    return None


def read_listings(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"Listings CSV not found at {path}.\n"
            f"Copy sample: cp sample/listings_sample.csv data/listings.csv"
        )
    return read_listings_csv(path)


def process_listings(listings: list[dict], bands: dict[int, object], default_cutoff: int) -> list[dict]:
    processed = []
    for i, listing in enumerate(listings, start=1):
        address = listing["address"]
        print(f"  [{i}/{len(listings)}] Geocoding: {address}")

        coords = geocode_address(address)
        if coords is None:
            print(f"    ✗ Could not geocode")
            processed.append(
                {
                    **listing,
                    "lat": None,
                    "lng": None,
                    "commute_min": None,
                    "in_zone": False,
                    "geocode_error": True,
                }
            )
        else:
            lat, lng = coords
            commute_min = minutes_in_zone(Point(lng, lat), bands)
            in_zone = commute_min is not None and commute_min <= default_cutoff
            status = f"≤{commute_min} min" if commute_min else "out of zone"
            print(f"    ✓ {lat:.5f}, {lng:.5f} — {status}")
            processed.append(
                {
                    **listing,
                    "lat": lat,
                    "lng": lng,
                    "commute_min": commute_min,
                    "in_zone": in_zone,
                    "geocode_error": False,
                }
            )

        if i < len(listings):
            time.sleep(1.1)  # Nominatim usage policy: max 1 req/sec

    processed.sort(key=lambda x: (x["commute_min"] is None, x["commute_min"] or 999, x.get("rent", "")))
    return processed


def main():
    default_cutoff = DEFAULT_COMMUTE_MAX

    print("Loading isochrones…")
    bands = load_isochrones(ISOCHRONES_PATH)
    print(f"  Bands loaded: {sorted(bands.keys())}")

    print(f"Reading listings from {LISTINGS_CSV}…")
    listings = read_listings(LISTINGS_CSV)
    print(f"  {len(listings)} listings found")

    if not listings:
        print("No listings to process.")
        sys.exit(0)

    print("Geocoding (Nominatim, ~1 req/sec)…")
    processed = process_listings(listings, bands, default_cutoff)

    LISTINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    LISTINGS_JSON.write_text(json.dumps(processed, indent=2))

    in_zone = sum(1 for x in processed if x.get("commute_min"))
    print(f"\nDone. {in_zone}/{len(processed)} within some isochrone band.")
    print(f"Saved → {LISTINGS_JSON}")


if __name__ == "__main__":
    main()
