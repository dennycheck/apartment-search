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

# StreetEasy badges look like:
#   "Open: Jul 26 ( 9 AM – 8 PM )"
#   "Open: Jul 26 ( 1:15 – 1:45 PM )"   <- start has no AM/PM; inherit from end
#   "Open: Jul 26 ( 12 – 3 PM )"
OPEN_HOUSE_RE = re.compile(
    r"Open(?:\s*House)?\s*:\s*"
    r"(?P<mon>[A-Za-z]+)\s+(?P<day>\d{1,2})"
    r"(?:\s*,\s*(?P<year>\d{4}))?"
    r"(?:\s*\(\s*(?P<start>\d{1,2}(?::\d{2})?\s*(?:AM|PM)?)\s*[–\-—]\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?\s*(?:AM|PM))\s*\))?",
    re.I,
)


def parse_clock(text: str) -> tuple[int, int, str | None] | None:
    """Return (hour12, minute, meridiem-or-None); None if unparseable."""
    text = text.strip().upper().replace(" ", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(AM|PM)?$", text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2) or 0), m.group(3)


def to_24h(hour12: int, meridiem: str) -> int:
    if meridiem == "AM":
        return 0 if hour12 == 12 else hour12
    return 12 if hour12 == 12 else hour12 + 12


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

    start_raw = m.group("start")
    end_raw = m.group("end")
    start_clock = parse_clock(start_raw) if start_raw else None
    end_clock = parse_clock(end_raw) if end_raw else None

    def fmt_time(dt: datetime) -> str:
        hour = dt.hour % 12 or 12
        return f"{hour}:{dt.strftime('%M')} {dt.strftime('%p')}"

    day_label = f"{datetime(year, mon, day).strftime('%a %b')} {day}"

    # Date-only badge: keep the date, don't invent a time range.
    if not (start_clock and end_clock and end_clock[2]):
        try:
            start_dt = datetime(year, mon, day, 12, 0)
        except ValueError:
            return empty
        return {
            "open_house": day_label,
            "open_house_start": start_dt.isoformat(timespec="minutes"),
            "open_house_end": "",
        }

    end_h24 = to_24h(end_clock[0], end_clock[2])
    # Start meridiem omitted on StreetEasy when it matches the end's
    # ("1:15 – 1:45 PM"); inherit it, and flip if that puts start after end
    # ("11 – 1 PM" -> 11 AM).
    start_mer = start_clock[2] or end_clock[2]
    start_h24 = to_24h(start_clock[0], start_mer)
    if not start_clock[2]:
        start_minutes = start_h24 * 60 + start_clock[1]
        end_minutes = end_h24 * 60 + end_clock[1]
        if start_minutes >= end_minutes:
            start_mer = "AM" if start_mer == "PM" else "PM"
            start_h24 = to_24h(start_clock[0], start_mer)

    try:
        start_dt = datetime(year, mon, day, start_h24, start_clock[1])
        end_dt = datetime(year, mon, day, end_h24, end_clock[1])
    except ValueError:
        return empty

    label = f"{day_label} · {fmt_time(start_dt)}–{fmt_time(end_dt)}"
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
