#!/usr/bin/env python3
"""Fetch public-transit isochrones from TravelTime API and save as GeoJSON."""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    ARRIVAL_TIME,
    COMMUTE_BANDS_MIN,
    ISOCHRONES_PATH,
    WORK_LAT,
    WORK_LNG,
)

load_dotenv()

API_URL = "https://api.traveltimeapp.com/v4/time-map"
MAX_BANDS = 10


def build_searches():
    """Build many_to_one arrival searches — areas reachable before arrive-by time."""
    searches = []
    for minutes in COMMUTE_BANDS_MIN:
        searches.append(
            {
                "id": f"{minutes}_min",
                "coords": {"lat": WORK_LAT, "lng": WORK_LNG},
                "arrival_time": ARRIVAL_TIME,
                "travel_time": minutes * 60,
                "transportation": {"type": "public_transport"},
            }
        )
    return searches


def fetch_isochrones(app_id: str, api_key: str) -> dict:
    if len(COMMUTE_BANDS_MIN) > MAX_BANDS:
        raise ValueError(f"TravelTime allows max {MAX_BANDS} searches; got {len(COMMUTE_BANDS_MIN)}")

    payload = {"arrival_searches": {"many_to_one": build_searches()}}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/geo+json",
        "X-Application-Id": app_id,
        "X-Api-Key": api_key,
    }

    print(f"Requesting {len(COMMUTE_BANDS_MIN)} isochrone bands → {WORK_LAT}, {WORK_LNG}")
    print(f"Arrive by: {ARRIVAL_TIME} (public transit)")

    response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    if not response.ok:
        print(f"API error {response.status_code}: {response.text[:500]}", file=sys.stderr)
        response.raise_for_status()

    return response.json()


def annotate_features(geojson: dict) -> dict:
    """Add minutes property from search id for map toggling."""
    for feature in geojson.get("features", []):
        props = feature.setdefault("properties", {})
        search_id = props.get("search_id", "")
        if search_id.endswith("_min"):
            props["minutes"] = int(search_id.replace("_min", ""))
    return geojson


def main():
    app_id = os.getenv("TRAVELTIME_APP_ID", "").strip()
    api_key = os.getenv("TRAVELTIME_API_KEY", "").strip()

    if not app_id or not api_key or app_id.startswith("your_"):
        print(
            "Missing TravelTime credentials.\n\n"
            "1. Sign up: https://account.traveltime.com\n"
            "2. Applications → Create Application\n"
            "3. Copy Application ID and API Key\n"
            "4. cp .env.example .env  &&  edit .env\n",
            file=sys.stderr,
        )
        sys.exit(1)

    geojson = fetch_isochrones(app_id, api_key)
    geojson = annotate_features(geojson)

    ISOCHRONES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ISOCHRONES_PATH.write_text(json.dumps(geojson, indent=2))

    feature_count = len(geojson.get("features", []))
    print(f"Saved {feature_count} isochrone features → {ISOCHRONES_PATH}")


if __name__ == "__main__":
    main()
