"""Shared helpers for reading, merging, and deduplicating listing CSV rows."""

import csv
import re
from pathlib import Path

LISTING_COLUMNS = ["address", "rent", "beds", "url", "notes", "source"]

ABBREV = {
    "st": "street",
    "st.": "street",
    "ave": "avenue",
    "ave.": "avenue",
    "blvd": "boulevard",
    "blvd.": "boulevard",
    "rd": "road",
    "rd.": "road",
    "dr": "drive",
    "dr.": "drive",
    "ln": "lane",
    "ln.": "lane",
    "ct": "court",
    "ct.": "court",
    "pl": "place",
    "pl.": "place",
    "e": "east",
    "w": "west",
    "n": "north",
    "s": "south",
}


def cell_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value).strip()
    return str(value).strip()


def normalize_address(address: str) -> str:
    """Normalize address for dedupe comparisons."""
    text = cell_value(address).lower()
    text = re.sub(r"[#,.\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = []
    for token in text.split():
        parts.append(ABBREV.get(token, token))
    return " ".join(parts)


def dedupe_key(listing: dict) -> tuple[str, str]:
    return normalize_address(listing.get("address", "")), cell_value(listing.get("url", "")).lower()


def listing_row(listing: dict) -> dict:
    row = {col: cell_value(listing.get(col, "")) for col in LISTING_COLUMNS}
    if not row["source"]:
        row["source"] = "manual"
    return row


def read_listings_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "address" not in reader.fieldnames:
            raise ValueError("CSV must include an 'address' column")

        rows = []
        for row in reader:
            address = cell_value(row.get("address"))
            if not address:
                continue
            rows.append(listing_row(row))
        return rows


def write_listings_csv(path: Path, listings: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LISTING_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for listing in listings:
            writer.writerow(listing_row(listing))


def merge_listings(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    """Merge incoming into existing; newer incoming wins on duplicate keys."""
    merged: dict[tuple[str, str], dict] = {}
    for listing in existing:
        key = dedupe_key(listing)
        if key[0]:
            merged[key] = listing_row(listing)

    added = 0
    updated = 0
    for listing in incoming:
        row = listing_row(listing)
        key = dedupe_key(row)
        if not key[0]:
            continue
        if key in merged:
            merged[key] = {**merged[key], **{k: v for k, v in row.items() if v}}
            updated += 1
        else:
            merged[key] = row
            added += 1

    result = sorted(merged.values(), key=lambda x: normalize_address(x["address"]))
    return result, added, updated


def append_listings_csv(path: Path, incoming: list[dict]) -> tuple[int, int, int]:
    existing = read_listings_csv(path)
    merged, added, updated = merge_listings(existing, incoming)
    write_listings_csv(path, merged)
    return len(merged), added, updated
