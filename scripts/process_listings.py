#!/usr/bin/env python3
"""Geocode CSV listings and tag commute_min via isochrone point-in-polygon.

Map-independent: writes data/listings_processed.json for scoring/reports.
Does not update the Leaflet map.
"""

import csv
import json
import re
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


def strip_unit(address: str) -> str:
    """Remove apt/unit suffixes that confuse Nominatim (#11E, Apt 2, PH127, etc.)."""
    text = address.strip()
    text = re.sub(r"\s+#\s*[\w-]+\s*", " ", text, flags=re.I)
    text = re.sub(r"\s+(?:apt|apartment|unit|ste|suite)\.?\s*[\w-]+\s*", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" ,")


def geocode_address(address: str, hint_url: str = "") -> tuple[float, float] | None:
    """Geocode a NYC-area address via Nominatim (free, rate-limited)."""
    queries = []
    raw = address if "NY" in address.upper() else f"{address}, New York, NY"
    # Prefer borough from StreetEasy URL when city line is wrong/ambiguous
    if "brooklyn" in (hint_url or "").lower() and "Brooklyn" not in raw:
        raw_bk = strip_unit(raw).replace("New York, NY", "Brooklyn, NY")
        queries.append(raw_bk)
    queries.append(raw)
    cleaned = strip_unit(raw)
    if cleaned != raw:
        queries.append(cleaned)

    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    seen_q = set()
    for q in queries:
        if q in seen_q:
            continue
        seen_q.add(q)
        params = {
            "q": q,
            "format": "json",
            "limit": 1,
            "countrycodes": "us",
        }
        response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        results = response.json()
        if results:
            lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
            # Reject obvious non-NYC hits (e.g. same street name upstate)
            if 40.40 <= lat <= 40.95 and -74.30 <= lon <= -73.70:
                return lat, lon
        time.sleep(1.1)
    return None


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


def process_listings(
    listings: list[dict],
    bands: dict[int, object],
    default_cutoff: int,
    cache: dict[str, dict] | None = None,
) -> list[dict]:
    processed = []
    cache = cache or {}
    for i, listing in enumerate(listings, start=1):
        address = listing["address"]
        cached = cache.get(address)
        if (
            cached
            and cached.get("lat") is not None
            and cached.get("lng") is not None
            and not cached.get("geocode_error")
        ):
            lat, lng = cached["lat"], cached["lng"]
            commute_min = minutes_in_zone(Point(lng, lat), bands)
            in_zone = commute_min is not None and commute_min <= default_cutoff
            status = f"≤{commute_min} min" if commute_min else "out of zone"
            print(f"  [{i}/{len(listings)}] Cache hit: {address} — {status}")
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
            continue

        print(f"  [{i}/{len(listings)}] Geocoding: {address}")

        coords = geocode_address(address, hint_url=listing.get("url", ""))
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

    cache: dict[str, dict] = {}
    if LISTINGS_JSON.exists():
        try:
            for row in json.loads(LISTINGS_JSON.read_text(encoding="utf-8")):
                addr = row.get("address")
                if addr:
                    cache[addr] = row
            print(f"  Reusing {len(cache)} cached geocodes when possible")
        except Exception:
            pass

    print("Geocoding (Nominatim, ~1 req/sec; cached skipped)…")
    processed = process_listings(listings, bands, default_cutoff, cache=cache)

    LISTINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    LISTINGS_JSON.write_text(json.dumps(processed, indent=2))

    in_zone = sum(1 for x in processed if x.get("commute_min"))
    print(f"\nDone. {in_zone}/{len(processed)} within some isochrone band.")
    print(f"Saved → {LISTINGS_JSON}")


if __name__ == "__main__":
    main()
