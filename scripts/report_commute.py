#!/usr/bin/env python3
"""Export listings within a max commute time."""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DEFAULT_COMMUTE_MAX, LISTINGS_JSON, OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser(description="Report listings within max commute minutes")
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_COMMUTE_MAX,
        help=f"Max commute minutes (default: {DEFAULT_COMMUTE_MAX})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: output/within_{max}_min.csv)",
    )
    args = parser.parse_args()

    if not LISTINGS_JSON.exists():
        print(f"No processed listings at {LISTINGS_JSON}. Run: python scripts/process_listings.py", file=sys.stderr)
        sys.exit(1)

    listings = json.loads(LISTINGS_JSON.read_text())
    in_budget = [
        l
        for l in listings
        if l.get("commute_min") is not None and l["commute_min"] <= args.max
    ]
    in_budget.sort(key=lambda x: (x["commute_min"], x.get("rent", "")))

    out_path = args.output or OUTPUT_DIR / f"within_{args.max}_min.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fields = ["address", "rent", "beds", "commute_min", "url", "notes", "source"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in in_budget:
            writer.writerow({k: row.get(k, "") for k in fields})

    total = len(listings)
    geocoded = sum(1 for l in listings if not l.get("geocode_error"))
    print(f"\nCommute report (≤{args.max} min)")
    print(f"  {len(in_budget)} of {total} listings qualify ({geocoded} geocoded)")
    print(f"  Saved → {out_path}\n")

    for row in in_budget[:20]:
        print(f"  ≤{row['commute_min']}m  {row.get('rent', '—'):>8}  {row['address']}")
    if len(in_budget) > 20:
        print(f"  … and {len(in_budget) - 20} more in {out_path}")


if __name__ == "__main__":
    main()
