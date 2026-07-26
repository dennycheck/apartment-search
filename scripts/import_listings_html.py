#!/usr/bin/env python3
"""Import listings from saved Zillow/StreetEasy HTML or structured JSON dumps.

HTML: File → Save Page As into data/listings/incoming/
JSON: array of listing objects (from screenshot extraction or manual entry)

Does not touch the map — only merges into data/listings.csv.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LISTINGS_CSV, LISTINGS_INCOMING_DIR
from scripts.listing_utils import append_listings_csv, cell_value, listing_row
from scripts.open_house import extract_open_house_from_card


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def detect_source(path: Path, html: str) -> str:
    name = path.name.lower()
    if "zillow" in name or "zillow.com" in html[:5000].lower():
        return "zillow_html"
    if "streeteasy" in name or "streeteasy.com" in html[:5000].lower():
        return "streeteasy_html"
    if "zillow.com" in html:
        return "zillow_html"
    if "streeteasy.com" in html:
        return "streeteasy_html"
    return "html_import"


def format_rent(value: str) -> str:
    text = cell_value(value)
    if not text:
        return ""
    digits = re.sub(r"[^\d]", "", text)
    return f"${digits}" if digits else text


def parse_card_meta(text: str) -> dict:
    """Pull beds/baths/sqft and amenity hints from card text."""
    meta = text or ""
    out: dict = {
        "beds": "",
        "baths": "",
        "sqft": "",
        "dishwasher": "",
        "in_unit_laundry": "",
        "amenities": "",
        "neighborhood": "",
    }

    if re.search(r"\bstudio\b", meta, re.I):
        out["beds"] = "0"
    else:
        bed_match = re.search(r"(\d+)\s*(?:bd|bed|bds|br|bedroom)s?", meta, re.I)
        if bed_match:
            out["beds"] = bed_match.group(1)

    bath_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:ba|bath)s?", meta, re.I)
    if bath_match:
        out["baths"] = bath_match.group(1)

    sqft_match = re.search(r"([\d,]+)\s*(?:sq\.?\s*ft|sqft|sf)\b", meta, re.I)
    if sqft_match:
        out["sqft"] = sqft_match.group(1).replace(",", "")

    amenities: list[str] = []
    lower = meta.lower()
    if "dishwasher" in lower:
        out["dishwasher"] = "yes"
        amenities.append("dishwasher")
    if re.search(r"in[- ]?unit\s+(washer|dryer|w/?d|laundry)|washer\s*/\s*dryer|w/?d\s+in\s+unit", lower):
        out["in_unit_laundry"] = "yes"
        amenities.append("in-unit laundry")
    for label, pattern in (
        ("gym", r"\b(gym|fitness)\b"),
        ("pool", r"\bpool\b"),
        ("doorman", r"\bdoorman\b"),
        ("elevator", r"\belevator\b"),
        ("roof deck", r"\broof(\s+deck|\s+top)?\b"),
        ("parking", r"\bparking\b"),
    ):
        if re.search(pattern, lower):
            amenities.append(label)
    out["amenities"] = ", ".join(dict.fromkeys(amenities))
    return out


def extract_zillow(soup: BeautifulSoup) -> list[dict]:
    listings = []
    seen = set()

    cards = soup.select('[data-test="property-card"], article[data-test="property-card"]')
    if not cards:
        cards = soup.select("article.list-card, li[class*='ListItem']")

    for card in cards:
        link = card.find("a", href=re.compile(r"/(homedetails|apartments)/", re.I))
        if not link:
            continue

        href = link.get("href", "")
        url = urljoin("https://www.zillow.com", href) if href.startswith("/") else href

        address = ""
        addr_el = card.select_one('[data-test="property-card-addr"], address, [data-test="property-card-link"]')
        if addr_el:
            address = cell_value(addr_el.get_text(" ", strip=True))
        if not address:
            address = cell_value(link.get_text(" ", strip=True))
        if not address or len(address) < 5:
            continue

        rent = ""
        price_el = card.select_one('[data-test="property-card-price"], span[data-test*="price"]')
        if price_el:
            rent = format_rent(price_el.get_text())
        card_text = card.get_text(" ", strip=True)
        if not rent:
            rent_match = re.search(r"\$[\d,]+\+?", card_text)
            if rent_match:
                rent = format_rent(rent_match.group(0))

        meta = parse_card_meta(card_text)
        key = (address.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)

        listings.append(
            listing_row(
                {
                    "address": address if ", NY" in address or "New York" in address else f"{address}, NY",
                    "rent": rent,
                    "beds": meta["beds"],
                    "baths": meta["baths"],
                    "sqft": meta["sqft"],
                    "url": url,
                    "dishwasher": meta["dishwasher"],
                    "in_unit_laundry": meta["in_unit_laundry"],
                    "amenities": meta["amenities"],
                    "notes": "",
                    "source": "zillow_html",
                }
            )
        )

    return listings


def _streeteasy_borough(text: str) -> str:
    lower = text.lower()
    if "brooklyn" in lower:
        return "Brooklyn, NY"
    if "queens" in lower:
        return "Queens, NY"
    if "bronx" in lower:
        return "Bronx, NY"
    return "New York, NY"


def extract_streeteasy_cards(soup: BeautifulSoup) -> list[dict]:
    """Current StreetEasy search UI: data-testid=listing-card."""
    listings = []
    seen = set()
    cards = soup.select('[data-testid="listing-card"]')

    for card in cards:
        link = card.select_one('a[href*="/building/"], a[href*="/rental/"]')
        if not link:
            continue
        href = link.get("href", "")
        url = href.split("?")[0]
        if url.startswith("/"):
            url = urljoin("https://streeteasy.com", url)

        addr_el = card.select_one('[class*="addressTextAction"]') or link
        address = cell_value(addr_el.get_text(" ", strip=True))
        if not address or len(address) < 5:
            continue

        card_text = card.get_text(" ", strip=True)
        title_el = card.select_one('[class*="ListingDescription-module__title"]')
        title = cell_value(title_el.get_text(" ", strip=True)) if title_el else ""
        neighborhood = ""
        area_match = re.search(
            r"(?:Rental unit|New development|Co-op|Condo|Three-family home)\s*in\s+(.+)$",
            title,
            re.I,
        )
        if area_match:
            neighborhood = area_match.group(1).strip()

        # Prefer net effective when present (what you actually pay with concession).
        notes = []
        rent = ""
        net = re.search(r"\$([\d,]+)\s*net effective", card_text, re.I)
        base_el = card.select_one('[class*="PriceInfo-module__price___"]')
        base = format_rent(base_el.get_text()) if base_el else ""
        if net:
            rent = format_rent(net.group(1))
            if base:
                notes.append(f"base {base}")
            notes.append("using net effective rent")
        else:
            rent = base
            if not rent:
                m = re.search(r"\$[\d,]+", card_text)
                if m:
                    rent = format_rent(m.group(0))

        beds = baths = sqft = ""
        for part in card.select('[class*="BedsBathsSqft-module__text"]'):
            t = cell_value(part.get_text(" ", strip=True)).lower().replace(" ", "")
            if "studio" in t:
                beds = "0"
            elif "bed" in t:
                m = re.search(r"(\d+)", t)
                if m:
                    beds = m.group(1)
            elif "bath" in t:
                m = re.search(r"(\d+(?:\.\d+)?)", t)
                if m:
                    baths = m.group(1)
            elif "ft" in t:
                m = re.search(r"([\d,]+)", t)
                if m:
                    sqft = m.group(1).replace(",", "")

        meta = parse_card_meta(card_text)
        amenities = amenity_list_from_card(card_text, title)
        if "no fee" in card_text.lower():
            amenities = ", ".join(filter(None, [amenities, "no fee"]))

        tour = extract_open_house_from_card(card)

        city = _streeteasy_borough(f"{title} {url} {neighborhood}")
        full_address = address if ", NY" in address else f"{address}, {city}"

        key = (address.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)

        listings.append(
            listing_row(
                {
                    "address": full_address,
                    "rent": rent,
                    "beds": beds or meta["beds"],
                    "baths": baths or meta["baths"],
                    "sqft": sqft or meta["sqft"],
                    "url": url,
                    "neighborhood": neighborhood,
                    "dishwasher": meta["dishwasher"],
                    "in_unit_laundry": meta["in_unit_laundry"],
                    "amenities": amenities or meta["amenities"],
                    "open_house": tour["open_house"],
                    "open_house_start": tour["open_house_start"],
                    "open_house_end": tour["open_house_end"],
                    "notes": "; ".join(notes),
                    "source": "streeteasy_html",
                }
            )
        )

    return listings


def amenity_list_from_card(card_text: str, title: str) -> str:
    lower = f"{card_text} {title}".lower()
    hits = []
    if "new development" in lower:
        hits.append("new development")
    if "no fee" in lower:
        hits.append("no fee")
    for label, pattern in (
        ("gym", r"\b(gym|fitness)\b"),
        ("pool", r"\bpool\b"),
        ("doorman", r"\bdoorman\b"),
        ("elevator", r"\belevator\b"),
    ):
        if re.search(pattern, lower):
            hits.append(label)
    return ", ".join(dict.fromkeys(hits))


def extract_streeteasy_legacy(soup: BeautifulSoup) -> list[dict]:
    """Older StreetEasy markup fallback."""
    listings = []
    seen = set()

    cards = soup.select("li.searchCardList--listItem, div.listingCard, article.listing")
    if not cards:
        return []

    for card in cards:
        if card is None:
            continue
        link = card.find("a", href=re.compile(r"streeteasy\.com/(building|rental)/", re.I))
        if not link:
            continue

        href = link.get("href", "")
        url = href if href.startswith("http") else urljoin("https://streeteasy.com", href)

        address = ""
        title_el = card.select_one(".listingCardLabel, .cardV2BuildingLink, h6, h5, .title")
        if title_el:
            address = cell_value(title_el.get_text(" ", strip=True))
        if not address:
            address = cell_value(link.get_text(" ", strip=True))

        card_text = card.get_text(" ", strip=True)
        rent = ""
        price_el = card.select_one(".listingCardPrice, .price, [class*='Price']")
        if price_el:
            rent = format_rent(price_el.get_text())
        if not rent:
            rent_match = re.search(r"\$[\d,]+", card_text)
            if rent_match:
                rent = format_rent(rent_match.group(0))

        meta = parse_card_meta(card_text)
        if not address or len(address) < 5:
            continue

        key = (address.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)

        listings.append(
            listing_row(
                {
                    "address": address if ", NY" in address or "New York" in address else f"{address}, New York, NY",
                    "rent": rent,
                    "beds": meta["beds"],
                    "baths": meta["baths"],
                    "sqft": meta["sqft"],
                    "url": url,
                    "dishwasher": meta["dishwasher"],
                    "in_unit_laundry": meta["in_unit_laundry"],
                    "amenities": meta["amenities"],
                    "notes": "",
                    "source": "streeteasy_html",
                }
            )
        )

    return listings


def extract_streeteasy(soup: BeautifulSoup) -> list[dict]:
    modern = extract_streeteasy_cards(soup)
    if modern:
        return modern
    return extract_streeteasy_legacy(soup)


def extract_listings_html(path: Path, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    source = detect_source(path, html)

    if source == "zillow_html":
        listings = extract_zillow(soup)
        return listings or extract_streeteasy(soup)

    if source == "streeteasy_html":
        listings = extract_streeteasy(soup)
        return listings or extract_zillow(soup)

    listings = extract_zillow(soup) or extract_streeteasy(soup)
    for row in listings:
        row["source"] = row.get("source") or "html_import"
    return listings


def extract_listings_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "listings" in data:
        data = data["listings"]
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: expected a JSON list of listings")
    rows = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        row = listing_row(raw)
        if not row["address"]:
            continue
        if not row["source"]:
            row["source"] = "screenshot_json"
        rows.append(row)
    return rows


def collect_paths(args: list[str]) -> list[Path]:
    paths: list[Path] = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.html")))
            paths.extend(sorted(p.glob("*.htm")))
            paths.extend(sorted(p.glob("*.json")))
        else:
            paths.append(p)
    return paths


def main():
    args = sys.argv[1:] or [str(LISTINGS_INCOMING_DIR)]
    if not args:
        print("Usage: python scripts/import_listings_html.py [files_or_dirs…]", file=sys.stderr)
        print(f"  Default: {LISTINGS_INCOMING_DIR}", file=sys.stderr)
        sys.exit(1)

    paths = collect_paths(args)
    if not paths:
        print("No HTML/JSON files found.", file=sys.stderr)
        sys.exit(1)

    all_incoming: list[dict] = []
    image_notes: list[str] = []

    for path in paths:
        if not path.exists():
            print(f"Skipping missing file: {path}", file=sys.stderr)
            continue
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            image_notes.append(path.name)
            continue
        if suffix in {".html", ".htm"}:
            html = path.read_text(encoding="utf-8", errors="replace")
            found = extract_listings_html(path, html)
            print(f"{path.name}: {len(found)} listing(s) [html]")
            all_incoming.extend(found)
        elif suffix == ".json":
            found = extract_listings_json(path)
            print(f"{path.name}: {len(found)} listing(s) [json]")
            all_incoming.extend(found)
        else:
            print(f"Skipping unsupported file: {path.name}", file=sys.stderr)

    if image_notes:
        print(
            "\nScreenshot images are not auto-OCR'd here. "
            "Drop them in Cursor chat (or write a JSON extract into incoming/) "
            f"— saw: {', '.join(image_notes)}",
            file=sys.stderr,
        )

    if not all_incoming:
        print("\nNo listings parsed.", file=sys.stderr)
        sys.exit(1)

    total, added, updated = append_listings_csv(LISTINGS_CSV, all_incoming)
    print(f"\nMerged into {LISTINGS_CSV}: {total} total ({added} new, {updated} updated)")


if __name__ == "__main__":
    main()
