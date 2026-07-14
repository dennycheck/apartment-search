#!/usr/bin/env python3
"""Import listings from saved Zillow or StreetEasy HTML search pages."""

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LISTINGS_CSV, LISTINGS_INCOMING_DIR
from scripts.listing_utils import append_listings_csv, cell_value


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


def extract_zillow(soup: BeautifulSoup, source_url: str) -> list[dict]:
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
        if not rent:
            rent_match = re.search(r"\$[\d,]+\+?", card.get_text(" ", strip=True))
            if rent_match:
                rent = format_rent(rent_match.group(0))

        beds = ""
        meta = card.get_text(" ", strip=True)
        bed_match = re.search(r"(\d+)\s*(?:bd|bed|bds|bedroom)", meta, re.I)
        if bed_match:
            beds = bed_match.group(1)

        key = (address.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)

        listings.append(
            {
                "address": address if ", NY" in address or "New York" in address else f"{address}, NY",
                "rent": rent,
                "beds": beds,
                "url": url,
                "notes": "",
                "source": "zillow_html",
            }
        )

    return listings


def extract_streeteasy(soup: BeautifulSoup, source_url: str) -> list[dict]:
    listings = []
    seen = set()

    cards = soup.select("li.searchCardList--listItem, div.listingCard, article.listing")
    if not cards:
        cards = soup.find_all("a", href=re.compile(r"streeteasy\.com/(building|rental)/", re.I))
        cards = [a.find_parent(["li", "article", "div"]) or a for a in cards]

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

        rent = ""
        price_el = card.select_one(".listingCardPrice, .price, [class*='Price']")
        if price_el:
            rent = format_rent(price_el.get_text())
        if not rent:
            rent_match = re.search(r"\$[\d,]+", card.get_text(" ", strip=True))
            if rent_match:
                rent = format_rent(rent_match.group(0))

        beds = ""
        bed_match = re.search(r"(\d+)\s*(?:bed|br|bedroom)", card.get_text(" ", strip=True), re.I)
        if bed_match:
            beds = bed_match.group(1)

        if not address or len(address) < 5:
            continue

        key = (address.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)

        listings.append(
            {
                "address": address if ", NY" in address or "New York" in address else f"{address}, New York, NY",
                "rent": rent,
                "beds": beds,
                "url": url,
                "notes": "",
                "source": "streeteasy_html",
            }
        )

    return listings


def extract_listings(path: Path, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    source = detect_source(path, html)

    if source == "zillow_html":
        listings = extract_zillow(soup, "")
        if listings:
            return listings
        return extract_streeteasy(soup, "")

    if source == "streeteasy_html":
        listings = extract_streeteasy(soup, "")
        if listings:
            return listings
        return extract_zillow(soup, "")

    # Unknown source — try both
    listings = extract_zillow(soup, "")
    if not listings:
        listings = extract_streeteasy(soup, "")
    for row in listings:
        row["source"] = row.get("source") or "html_import"
    return listings


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_listings_html.py path/to/page.html [more.html ...]", file=sys.stderr)
        print(f"  Or drop files in {LISTINGS_INCOMING_DIR} and pass that directory.", file=sys.stderr)
        sys.exit(1)

    paths: list[Path] = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.html")))
            paths.extend(sorted(p.glob("*.htm")))
        else:
            paths.append(p)

    if not paths:
        print("No HTML files found.", file=sys.stderr)
        sys.exit(1)

    all_incoming = []
    for path in paths:
        if not path.exists():
            print(f"Skipping missing file: {path}", file=sys.stderr)
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        found = extract_listings(path, html)
        print(f"{path.name}: {len(found)} listing(s)")
        all_incoming.extend(found)

    if not all_incoming:
        print("\nNo listings parsed. Save the full search results page as HTML and retry.", file=sys.stderr)
        sys.exit(1)

    total, added, updated = append_listings_csv(LISTINGS_CSV, all_incoming)
    print(f"\nMerged into {LISTINGS_CSV}: {total} total ({added} new, {updated} updated)")


if __name__ == "__main__":
    main()
