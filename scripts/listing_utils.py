"""Shared helpers for reading, merging, and deduplicating listing rows."""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

# Core + optional enrichment fields. Empty strings when unknown.
LISTING_COLUMNS = [
    "address",
    "rent",
    "beds",
    "baths",
    "sqft",
    "url",
    "neighborhood",
    "dishwasher",
    "in_unit_laundry",
    "amenities",
    "open_house",
    "open_house_start",
    "open_house_end",
    "status",
    "first_seen_at",
    "last_seen_at",
    "notes",
    "source",
]

STATUS_ACTIVE = "active"
STATUS_TOURED = "toured"
STATUS_OFF_MARKET = "off_market"
VALID_STATUSES = {STATUS_ACTIVE, STATUS_TOURED, STATUS_OFF_MARKET}
PROTECTED_STATUSES = {STATUS_TOURED, STATUS_OFF_MARKET}

BOOL_TRUE = {"1", "true", "yes", "y", "t"}


def cell_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value).strip()
    return str(value).strip()


def parse_bool(value) -> bool | None:
    text = cell_value(value).lower()
    if not text:
        return None
    if text in BOOL_TRUE:
        return True
    if text in {"0", "false", "no", "n", "f"}:
        return False
    return None


def parse_rent(value) -> int | None:
    digits = re.sub(r"[^\d]", "", cell_value(value))
    return int(digits) if digits else None


def parse_int(value) -> int | None:
    text = cell_value(value).lower()
    if not text:
        return None
    if "studio" in text:
        return 0
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def normalize_status(value) -> str:
    text = cell_value(value).lower().replace(" ", "_").replace("-", "_")
    if text in {"offmarket", "off_the_market", "rented", "gone"}:
        return STATUS_OFF_MARKET
    if text in VALID_STATUSES:
        return text
    return STATUS_ACTIVE


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


def normalize_address(address: str) -> str:
    """Normalize address for dedupe comparisons."""
    text = cell_value(address).lower()
    text = re.sub(r"[#,.\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = []
    for token in text.split():
        parts.append(ABBREV.get(token, token))
    return " ".join(parts)


def normalize_url(url: str) -> str:
    text = cell_value(url).lower().split("?")[0].rstrip("/")
    return text


def dedupe_key(listing: dict) -> str:
    """Primary key: URL when present; else normalized address."""
    url = normalize_url(listing.get("url", ""))
    if url:
        return f"url:{url}"
    addr = normalize_address(listing.get("address", ""))
    return f"addr:{addr}" if addr else ""


def today_iso() -> str:
    return date.today().isoformat()


def listing_row(listing: dict) -> dict:
    row = {col: cell_value(listing.get(col, "")) for col in LISTING_COLUMNS}
    if not row["source"]:
        row["source"] = "manual"
    row["status"] = normalize_status(row.get("status"))
    # Normalize bool-ish amenity flags to yes/blank for CSV stability
    for flag in ("dishwasher", "in_unit_laundry"):
        parsed = parse_bool(row[flag])
        if parsed is True:
            row[flag] = "yes"
        elif parsed is False:
            row[flag] = "no"
        else:
            row[flag] = ""
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
    seen = today_iso()
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LISTING_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for listing in listings:
            row = listing_row(listing)
            if not row["first_seen_at"]:
                row["first_seen_at"] = seen
            if not row["last_seen_at"]:
                row["last_seen_at"] = seen
            writer.writerow(row)


def merge_listings(
    existing: list[dict],
    incoming: list[dict],
    *,
    seen_at: str | None = None,
) -> tuple[list[dict], int, int]:
    """Merge incoming into existing; preserve toured/off_market status."""
    seen = seen_at or today_iso()
    merged: dict[str, dict] = {}

    for listing in existing:
        row = listing_row(listing)
        key = dedupe_key(row)
        if key:
            merged[key] = row

    added = 0
    updated = 0
    for listing in incoming:
        row = listing_row(listing)
        key = dedupe_key(row)
        if not key:
            continue

        if key in merged:
            prev = merged[key]
            prev_status = normalize_status(prev.get("status"))
            # Incoming empty fields don't wipe; non-empty update.
            combined = {**prev, **{k: v for k, v in row.items() if v}}
            # Never let HTML import resurrect protected statuses.
            if prev_status in PROTECTED_STATUSES:
                combined["status"] = prev_status
            else:
                combined["status"] = normalize_status(combined.get("status") or STATUS_ACTIVE)
            combined["first_seen_at"] = prev.get("first_seen_at") or seen
            combined["last_seen_at"] = seen
            merged[key] = listing_row(combined)
            updated += 1
        else:
            row["status"] = normalize_status(row.get("status") or STATUS_ACTIVE)
            row["first_seen_at"] = row.get("first_seen_at") or seen
            row["last_seen_at"] = seen
            merged[key] = listing_row(row)
            added += 1

    result = sorted(merged.values(), key=lambda x: normalize_address(x["address"]))
    return result, added, updated


def append_listings_csv(path: Path, incoming: list[dict]) -> tuple[int, int, int]:
    existing = read_listings_csv(path)
    merged, added, updated = merge_listings(existing, incoming)
    write_listings_csv(path, merged)
    return len(merged), added, updated


def apply_status_updates(path: Path, updates: dict[str, str]) -> tuple[int, int]:
    """Apply {listing_key: status} to CSV. Returns (changed, total)."""
    rows = read_listings_csv(path)
    changed = 0
    for row in rows:
        key = dedupe_key(row)
        # Also accept raw URL or address keys from the hitlist UI
        candidates = {
            key,
            normalize_url(row.get("url", "")),
            cell_value(row.get("url", "")).lower(),
            cell_value(row.get("address", "")).lower(),
            listing_key_for_ui(row),
        }
        for cand in candidates:
            if cand and cand in updates:
                new_status = normalize_status(updates[cand])
                if row.get("status") != new_status:
                    row["status"] = new_status
                    changed += 1
                break
    write_listings_csv(path, rows)
    return changed, len(rows)


def listing_key_for_ui(row: dict) -> str:
    """Stable key used by hitlist.html localStorage / status patches."""
    url = cell_value(row.get("url", "")).lower()
    if url:
        return url
    return cell_value(row.get("address", "")).lower()


def read_listings_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "listings" in data:
        data = data["listings"]
    if not isinstance(data, list):
        raise ValueError(f"Expected list of listings in {path}")
    return [listing_row(row) for row in data if cell_value(row.get("address"))]


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def amenity_list(value) -> list[str]:
    text = cell_value(value)
    if not text:
        return []
    parts = re.split(r"[,;|/]+", text)
    return [p.strip() for p in parts if p.strip()]
