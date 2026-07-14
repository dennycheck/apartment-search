#!/usr/bin/env python3
"""Fetch NYC rental listings from RentCast API and merge into listings.csv."""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LISTINGS_CSV, RENTCAST_API_URL, RENTCAST_SEARCH
from scripts.listing_utils import append_listings_csv, cell_value

load_dotenv()


def rentcast_listing_to_row(item: dict) -> dict | None:
    address = cell_value(item.get("formattedAddress"))
    if not address:
        line1 = cell_value(item.get("addressLine1"))
        city = cell_value(item.get("city"))
        state = cell_value(item.get("state"))
        zip_code = cell_value(item.get("zipCode"))
        if line1 and city:
            address = f"{line1}, {city}, {state or 'NY'} {zip_code}".strip()
    if not address:
        return None

    price = item.get("price")
    rent = f"${int(price)}" if isinstance(price, (int, float)) else cell_value(price)

    beds = item.get("bedrooms")
    beds_str = str(int(beds)) if isinstance(beds, (int, float)) else cell_value(beds)

    url = cell_value(item.get("listingUrl") or item.get("url") or item.get("zillowUrl"))

    return {
        "address": address,
        "rent": rent,
        "beds": beds_str,
        "url": url,
        "notes": cell_value(item.get("propertyType")),
        "source": "rentcast",
    }


def fetch_page(params: dict, api_key: str) -> list[dict]:
    headers = {"Accept": "application/json", "X-Api-Key": api_key}
    response = requests.get(RENTCAST_API_URL, params=params, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("listings") or data.get("data") or []
    return []


def build_queries() -> list[dict]:
    base = {
        "state": RENTCAST_SEARCH["state"],
        "status": "Active",
        "limit": RENTCAST_SEARCH["limit_per_query"],
    }
    if RENTCAST_SEARCH.get("bedrooms"):
        base["bedrooms"] = RENTCAST_SEARCH["bedrooms"]
    if RENTCAST_SEARCH.get("price_max"):
        base["price"] = f"*:{RENTCAST_SEARCH['price_max']}"
    if RENTCAST_SEARCH.get("days_old"):
        base["daysOld"] = f"*:{RENTCAST_SEARCH['days_old']}"

    queries = []
    for city in RENTCAST_SEARCH.get("cities", []):
        queries.append({**base, "city": city})
    for zip_code in RENTCAST_SEARCH.get("zip_codes", []):
        queries.append({**base, "zipCode": zip_code})
    return queries


def main():
    api_key = os.getenv("RENTCAST_API_KEY", "").strip()
    if not api_key:
        print("RENTCAST_API_KEY not set. Add it to .env (see .env.example).", file=sys.stderr)
        sys.exit(1)

    queries = build_queries()
    if not queries:
        print("No RentCast queries configured in config.RENTCAST_SEARCH", file=sys.stderr)
        sys.exit(1)

    incoming = []
    seen_urls = set()

    for query in queries:
        label = query.get("city") or query.get("zipCode") or "search"
        print(f"Fetching {label}…")
        for page in range(RENTCAST_SEARCH.get("max_pages", 1)):
            params = {**query, "offset": page * query["limit"]}
            try:
                items = fetch_page(params, api_key)
            except requests.HTTPError as exc:
                print(f"  API error: {exc.response.status_code} {exc.response.text[:200]}", file=sys.stderr)
                break

            if not items:
                break

            for item in items:
                row = rentcast_listing_to_row(item)
                if not row:
                    continue
                key = row["url"] or row["address"]
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                incoming.append(row)

            print(f"  page {page + 1}: {len(items)} raw, {len(incoming)} unique so far")
            if len(items) < query["limit"]:
                break

    if not incoming:
        print("No listings returned from RentCast.", file=sys.stderr)
        sys.exit(1)

    total, added, updated = append_listings_csv(LISTINGS_CSV, incoming)
    print(f"\nMerged into {LISTINGS_CSV}: {total} total ({added} new, {updated} updated)")


if __name__ == "__main__":
    main()
