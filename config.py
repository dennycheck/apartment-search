"""Project configuration for NYC apartment commute search."""

from pathlib import Path

ROOT = Path(__file__).parent

# Work: 240 Greenwich St, New York, NY
WORK_ADDRESS = "240 Greenwich St, New York, NY"
WORK_LAT = 40.7130
WORK_LNG = -74.0115

# Weekday arrive-by 8:30 AM Eastern (used for exact arrival_time API searches)
ARRIVAL_TIME = "2026-07-13T08:30:00-04:00"

COMMUTE_BANDS_MIN = [10, 20, 30, 40, 50, 60]

# Wide gamut by 10-minute family (cool blue → green → yellow → orange → magenta/pink).
# 5-min halves within a family are only a subtle cooler/warmer nudge; family jumps are large.
BAND_COLORS = {
    10: "#195dfa",  # ≤10 — blue
    15: "#08c158",  # 10–15 — green (cooler)
    20: "#09da48",  # 15–20 — green (warmer)
    25: "#f7df05",  # 20–25 — yellow (cooler)
    30: "#fac61c",  # 25–30 — yellow (warmer)
    35: "#f26100",  # 30–35 — orange (cooler)
    40: "#ff4d0d",  # 35–40 — orange (warmer)
    45: "#f519ac",  # 40–45 — pink/magenta (cooler)
    50: "#f62cd8",  # 45–50 — pink/magenta (warmer / more purple)
    60: "#e71ff9",  # 50–60 — purple-magenta
}

DEFAULT_COMMUTE_MAX = 50

DATA_DIR = ROOT / "data"
ISOCHRONES_BANDS_DIR = DATA_DIR / "isochrones" / "bands"
ISOCHRONES_CONTOURS_DIR = DATA_DIR / "isochrones" / "contours"
LISTINGS_INCOMING_DIR = DATA_DIR / "listings" / "incoming"
OUTPUT_DIR = ROOT / "output"
ISOCHRONES_PATH = DATA_DIR / "isochrones.geojson"
ISOCHRONES_CONTOURS_PATH = DATA_DIR / "isochrones_contours.geojson"
# Midpoint isochrones merged into filled 5-min rings (see BAND_COLORS), e.g. 15, 25, 35, 45.
COMMUTE_CONTOURS_MIN = [15, 25, 35, 45]
LISTINGS_CSV = DATA_DIR / "listings.csv"
LISTINGS_JSON = DATA_DIR / "listings_processed.json"
MAP_HTML = OUTPUT_DIR / "index.html"
OVERLAY_HTML = OUTPUT_DIR / "overlay.html"
OVERLAY_DEFAULT_OPACITY = 0.5
POIS_JSON = DATA_DIR / "pois_processed.json"
SUBWAY_DIR = DATA_DIR / "subway"
SUBWAY_LINES_PATH = SUBWAY_DIR / "lines.geojson"
SUBWAY_STATIONS_PATH = SUBWAY_DIR / "stations.geojson"

# Points of interest shown on the map (geocoded via scripts/process_pois.py).
# shape: square | triangle | diamond | star | circle — primary way to tell pins apart.
POIS = [
    {
        "id": "current_apt",
        "label": "My apartment (Bushwick)",
        "address": "292 Stockholm St, Brooklyn, NY",
        "shape": "square",
        "color": "#ffffff",
    },
    {
        "id": "brother_apt",
        "label": "Brother & sister-in-law (UES)",
        "address": "344 E 81st St, New York, NY",
        "shape": "triangle",
        "color": "#ffffff",
    },
    {
        "id": "dan_chloe",
        "label": "Dan & Chloe's (Pacific St)",
        "address": "1148 Pacific St, Brooklyn, NY",
        "shape": "diamond",
        "color": "#ffffff",
    },
]

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "apartment-search/1.0 (personal NYC commute tool)"

# RentCast API — https://rentcast.io/api (optional bulk listing fetch)
RENTCAST_API_URL = "https://api.rentcast.io/v1/listings/rental/long-term"
RENTCAST_SEARCH = {
    "state": "NY",
    "cities": ["New York", "Brooklyn", "Queens", "Bronx", "Staten Island"],
    "zip_codes": [],  # optional, e.g. ["11211", "10003"]
    "bedrooms": None,  # e.g. "1:2" for 1–2 beds
    "price_max": None,  # e.g. 4500
    "days_old": 30,  # listings posted in last N days
    "limit_per_query": 100,
    "max_pages": 3,  # pages per city/zip query
}
