#!/usr/bin/env python3
"""Apply hit-list status patches to data/listings.csv (+ data/hitlist_status.json).

Accepts a JSON object mapping listing keys (URL or address) to status:

  {
    "https://streeteasy.com/building/...": "off_market",
    "654 saint marks avenue #2a, brooklyn, ny": "toured"
  }

Or a {"statuses": {...}} wrapper / array of {key, status} objects.

After applying, re-run score_listings + generate_hitlist_ui (or run_hitlist_pipeline).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import HITLIST_STATUS_JSON, LISTINGS_CSV
from scripts.listing_utils import apply_status_updates, normalize_status


def load_updates(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    updates: dict[str, str] = {}
    if isinstance(data, dict) and "statuses" in data:
        data = data["statuses"]
    if isinstance(data, dict):
        for k, v in data.items():
            if k and v:
                updates[str(k).strip().lower()] = normalize_status(v)
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("url") or item.get("address")
            status = item.get("status")
            if key and status:
                updates[str(key).strip().lower()] = normalize_status(status)
    else:
        raise ValueError("Expected object or list of status updates")
    return updates


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply hitlist status JSON to listings.csv")
    parser.add_argument("status_json", type=Path, help="Path to status patch JSON")
    parser.add_argument(
        "--csv",
        type=Path,
        default=LISTINGS_CSV,
        help="Listings CSV path",
    )
    args = parser.parse_args()

    if not args.status_json.exists():
        print(f"Missing {args.status_json}", file=sys.stderr)
        sys.exit(1)

    updates = load_updates(args.status_json)
    if not updates:
        print("No status updates found in file.", file=sys.stderr)
        sys.exit(1)

    changed, total = apply_status_updates(args.csv, updates)
    print(f"Updated {changed} of {total} listings in {args.csv}")

    # Merge into durable repo status file (survives future re-ingests).
    existing: dict[str, str] = {}
    if HITLIST_STATUS_JSON.exists() and args.status_json.resolve() != HITLIST_STATUS_JSON.resolve():
        try:
            existing = load_updates(HITLIST_STATUS_JSON)
        except Exception:
            existing = {}
    merged = {**existing, **updates}
    durable = {k: v for k, v in merged.items() if v and v != "active"}
    HITLIST_STATUS_JSON.write_text(
        json.dumps({"statuses": durable}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote durable status file → {HITLIST_STATUS_JSON} ({len(durable)} non-active)")
    print("Next: python scripts/score_listings.py && python scripts/generate_hitlist_ui.py")


if __name__ == "__main__":
    main()
