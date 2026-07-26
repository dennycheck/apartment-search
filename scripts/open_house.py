#!/usr/bin/env python3
"""Parse StreetEasy open-house / tour badge text into sortable datetimes."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

OPEN_HOUSE_RE = re.compile(
    r"Open(?:\s*House)?\s*:\s*"
    r"(?P<mon>[A-Za-z]+)\s+(?P<day>\d{1,2})"
    r"(?:\s*,\s*(?P<year>\d{4}))?"
    r"(?:\s*\(\s*(?P<start>\d{1,2}(?::\d{2})?\s*(?:AM|PM))\s*[–\-—]\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?\s*(?:AM|PM))\s*\))?",
    re.I,
)


def parse_clock(text: str) -> tuple[int, int]:
    text = text.strip().upper().replace(" ", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(AM|PM)$", text)
    if not m:
        return 9, 0
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3)
    if ampm == "AM":
        if hour == 12:
            hour = 0
    else:
        if hour != 12:
            hour += 12
    return hour, minute


def infer_year(month: int, day: int, explicit: int | None, now: datetime) -> int:
    if explicit:
        return explicit
    year = now.year
    try:
        candidate = datetime(year, month, day)
    except ValueError:
        return year
    # If the date is more than a day in the past, roll to next year
    # (open houses on the listing are near-term).
    if candidate.date() < (now - timedelta(days=1)).date():
        return year + 1
    return year


def parse_open_house(text: str, now: datetime | None = None) -> dict:
    """Return {open_house, open_house_start, open_house_end} or empty strings."""
    now = now or datetime.now()
    empty = {"open_house": "", "open_house_start": "", "open_house_end": ""}
    if not text:
        return empty
    m = OPEN_HOUSE_RE.search(text)
    if not m:
        return empty

    mon = MONTHS.get(m.group("mon").lower())
    if not mon:
        return empty
    day = int(m.group("day"))
    year = infer_year(mon, day, int(m.group("year")) if m.group("year") else None, now)

    start_h, start_m = (9, 0)
    end_h, end_m = (17, 0)
    if m.group("start"):
        start_h, start_m = parse_clock(m.group("start"))
    if m.group("end"):
        end_h, end_m = parse_clock(m.group("end"))

    try:
        start_dt = datetime(year, mon, day, start_h, start_m)
        end_dt = datetime(year, mon, day, end_h, end_m)
    except ValueError:
        return empty

    def fmt_time(dt: datetime) -> str:
        hour = dt.hour % 12 or 12
        return f"{hour}:{dt.strftime('%M')} {dt.strftime('%p')}"

    label = (
        f"{start_dt.strftime('%a %b')} {start_dt.day} · "
        f"{fmt_time(start_dt)}–{fmt_time(end_dt)}"
    )
    return {
        "open_house": label,
        "open_house_start": start_dt.isoformat(timespec="minutes"),
        "open_house_end": end_dt.isoformat(timespec="minutes"),
    }


def extract_open_house_from_card(card) -> dict:
    """BeautifulSoup card → open-house fields."""
    el = card.select_one(
        '[class*="openHouseTag"], [class*="OpenHouseCopy-module__copyContainer"]'
    )
    raw = ""
    if el:
        raw = el.get_text(" ", strip=True)
    if not raw:
        text = card.get_text(" ", strip=True)
        m = OPEN_HOUSE_RE.search(text)
        raw = m.group(0) if m else ""
    return parse_open_house(raw)
