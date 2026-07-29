# NYC Apartment Commute Search

Find apartments reachable by public transit before **8:30 AM** on weekdays, relative to work at **240 Greenwich St**.

## How it works

```
TravelTime API → GeoJSON isochrones → Leaflet map
CSV listings → Nominatim geocode → point-in-polygon filter
```

Isochrone bands: **10, 20, 30, 40, 50 minutes**. Toggle bands on the map; **Max commute** (default 30 min) fades zones beyond your budget.

```
Isochrones → map
Listings (CSV / RentCast / HTML import) → geocode → commute filter → map + report
POIs (config.py) → map
```

---

## Step 1 — Get isochrones (pick one path)

TravelTime's **account signup requires a company email** — there is no personal-use tier. For a personal apartment search, use one of these instead:

### Path A — TravelTime Playground (recommended, no signup)

No API key needed. The [Isochrone Playground](https://playground.traveltime.com/isochrones) runs real TravelTime requests in your browser.

1. Open [playground.traveltime.com/isochrones](https://playground.traveltime.com/isochrones)
2. **Location:** `40.7130, -74.0115` (240 Greenwich St) — click the map or paste coords
3. **Search type:** **Arrive** (areas you can leave from and still reach work on time)
4. **Date & time:** a weekday morning near 8:30 AM (e.g. next Monday 8:30 AM)
5. **Transport type:** Public transit
6. Click **Add multiple isochrones** → add 10, 20, 30, 40, 50, 60 minutes
7. In the **Request** panel, find the headers and set:
   `Accept: application/geo+json`
8. Click **Send API Request**
9. Copy the entire **Response** JSON → save as `data/isochrones.geojson`

Then skip the API fetch and run:

```bash
python scripts/process_listings.py
python scripts/generate_map.py
```

Verify the shapes at [geojson.io](https://geojson.io) if anything looks off.

**Feeding bands one at a time (from chat or files):**

Each band is saved under `data/isochrones/bands/` and merged into `data/isochrones.geojson`:

```bash
# Save a pasted playground response (50-minute example)
python scripts/save_isochrone_band.py 50 path/to/response.geojson

# Or pipe JSON from stdin
python scripts/paste_isochrone.py 50 < response.geojson
```

Repeat for 10, 20, 30, 40, 60 min — each run merges all saved bands.

### Path B — Geoapify (personal email OK, limited free tier)

[geoapify.com](https://www.geoapify.com/) accepts personal signup (no company email). Free tier supports **transit isochrones up to 15 minutes only** — not enough for 10–60 min bands without paying. Useful for quick tests, not this project's full range.

### Path C — OpenTripPlanner (fully free, more setup)

Run [OpenTripPlanner](https://www.opentripplanner.org/) locally with NYC GTFS feeds. No signup, full control, exact 8:30 AM arrival times — but requires Docker, ~1GB graph build, and developer comfort. Best if you want fully automated re-runs without any vendor.

### Path D — TravelTime API account (business email)

If you have a company email:

1. Sign up: [account.traveltime.com](https://account.traveltime.com)
2. Applications → Create Application → copy Application ID + API Key
3. `cp .env.example .env` and paste credentials
4. `python scripts/fetch_isochrones.py`

---

## Step 2 — Install & run

```bash
cd ~/apartment-search
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: copy sample listings
mkdir -p data
cp sample/listings_sample.csv data/listings.csv

# Full pipeline
python run.py
```

Or run steps individually:

```bash
python scripts/fetch_listings_rentcast.py  # optional; needs RENTCAST_API_KEY
python scripts/import_listings_html.py data/listings/incoming/zillow.html  # optional
python scripts/fetch_isochrones.py         # optional; needs .env credentials
python scripts/process_pois.py             # optional
python scripts/process_listings.py         # requires data/listings.csv
python scripts/generate_map.py             # writes output/index.html
python scripts/report_commute.py --max 30  # CSV of listings within 30 min
```

Open the map:

```bash
open output/index.html
```

---

## Hit list pipeline (separate from the map)

The map is for exploring neighborhoods and commute bands. **Listing ingest + ranking does not plot on the map** — it only reuses `data/isochrones.geojson` to tag each address with `commute_min`, then scores against `data/apartment_preferences.md`.

```
StreetEasy search URL
  → save_streeteasy_pages.py  (HTML into StreetEasy HTMLs/)
  → import → merge/dedupe by URL (status preserved)
  → geocode (cached) + isochrone band
  → composite score
  → output/hitlist.html + hit_list.md
```

Listings carry a **status**: `active` | `toured` | `off_market`. Re-importing the same unit updates rent/open house/`last_seen_at` but **does not** resurrect something you marked toured or off-market. Missing from a crawl is not auto-deleted.

### Daily refresh

```bash
# 1) Capture search pages — StreetEasy blocks Playwright's Chromium.
#    Use your real Chrome with remote debugging instead:
#
#    Quit Chrome, then in Terminal:
#      /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
#        --remote-debugging-port=9222 \
#        --user-data-dir="$HOME/chrome-streeteasy-debug"
#    Open your search URL, pass any captcha, confirm listing cards show.
#
#    Then:
python scripts/save_streeteasy_pages.py --cdp http://127.0.0.1:9222 --pages 15

# 2) Merge → geocode new only → score → hitlist.html
python scripts/run_hitlist_pipeline.py
# (defaults to StreetEasy HTMLs/ when that folder has .html files)

# 3) On phone: triage Ranked / Tours; Mark as toured or Off the market
#    https://dennycheck.github.io/apartment-search/hitlist.html

# 4) Optional: make phone marks durable in CSV (Download status.json from the hit list)
python scripts/apply_hitlist_status.py ~/Downloads/hitlist_status.json
python scripts/score_listings.py && python scripts/generate_hitlist_ui.py
```

Publish: commit `output/hitlist.html` (or use `python scripts/publish_hitlist.py`) so GitHub Pages updates.

### One-shot (folder already saved)

```bash
python scripts/run_hitlist_pipeline.py
# or: python scripts/run_hitlist_pipeline.py "StreetEasy HTMLs"
open output/hitlist.html
```

Or step by step:

```bash
python scripts/import_listings_html.py "StreetEasy HTMLs"
python scripts/process_listings.py      # commute_min only — no map write
python scripts/score_listings.py
python scripts/generate_hitlist_ui.py
```

### How to feed listings (no one-by-one paste)

| Method | What you do | Best for |
|--------|-------------|----------|
| **Playwright saver** | `save_streeteasy_pages.py --url … --pages N` → `StreetEasy HTMLs/` | Daily multi-page refresh |
| **Saved HTML** | File → Save Page As into `StreetEasy HTMLs/` or `data/listings/incoming/` | Ad-hoc batch |
| **Screenshots in Cursor chat** | Attach results-page screenshots here | Vision extract → JSON → pipeline |
| **JSON extract** | Drop a list like `sample/listings_from_screenshot.sample.json` into `incoming/` | When you already have structured rows |

Preferences / weights live in [`data/apartment_preferences.md`](data/apartment_preferences.md) (max rent $4k; commute weight 45; soft bands, not a hard 30-min wall).

---

## Listing ingestion (three tiers)

### Tier 1 — RentCast API (bulk NYC rentals)

1. Sign up at [rentcast.io/api](https://rentcast.io/api) and copy your API key into `.env`
2. Adjust search filters in `config.py` → `RENTCAST_SEARCH` (cities, max rent, beds, days old)
3. Run:

```bash
python scripts/fetch_listings_rentcast.py
python scripts/process_listings.py
python scripts/report_commute.py --max 30
```

Listings merge into `data/listings.csv` with `source=rentcast`. Not StreetEasy/Zillow inventory, but good automated coverage.

### Tier 2 — Saved HTML from Zillow / StreetEasy (semi-auto)

**Preferred (StreetEasy):** paginate with Playwright into `StreetEasy HTMLs/`:

```bash
python scripts/save_streeteasy_pages.py --url 'https://streeteasy.com/for-rent/nyc/...' --pages 15
python scripts/run_hitlist_pipeline.py
```

Or manually:

1. Run a search on Zillow or StreetEasy in your browser
2. Save the results page as HTML (File → Save Page As) into `StreetEasy HTMLs/` or `data/listings/incoming/`
3. Import:

```bash
python scripts/import_listings_html.py "StreetEasy HTMLs"
python scripts/process_listings.py
```

Site DOMs change — if parsing returns 0 rows, re-save the page and we can adjust selectors in `import_listings_html.py`.

### Tier 3 — Manual CSV

Hand-edit or export rows into `data/listings.csv` (see format below).

### Commute report

After processing:

```bash
python scripts/report_commute.py --max 30
```

Writes `output/within_30_min.csv` and prints qualifying addresses sorted by commute time.

---

## Listings CSV format

Export or hand-build a CSV with these columns:

| Column | Required | Example |
|--------|----------|---------|
| address | yes | 123 Bedford Ave, Brooklyn, NY |
| rent | no | $3200 |
| beds | no | 2 (use `0` for studio) |
| baths | no | 1 |
| sqft | no | 650 |
| url | no | https://streeteasy.com/... |
| neighborhood | no | Williamsburg |
| dishwasher | no | yes |
| in_unit_laundry | no | yes |
| amenities | no | gym, pool, elevator |
| open_house | no | Open: Sat 1–2pm |
| open_house_start | no | 2026-07-26T13:00:00 |
| open_house_end | no | 2026-07-26T14:00:00 |
| status | no | `active` (default), `toured`, or `off_market` |
| first_seen_at | no | 2026-07-20 (set on first import) |
| last_seen_at | no | 2026-07-26 (refreshed on each merge) |
| notes | no | Has laundry |
| source | no | rentcast, zillow_html, screenshot_json, manual |

Geocoding uses [Nominatim](https://nominatim.openstreetmap.org/) (free, 1 request/sec). Addresses should include borough/city for accuracy.

---

## Map features

- Dark basemap with full-spectrum isochrone rings (toggle each band)
- **Max commute** dropdown (default 30 min) — fades bands beyond your budget
- POI pins (toggle in Summary) — your apartment, family, etc.
- Listing pins (toggle in Summary) — white = within budget, gray = outside
- Sortable listing table — click a row to pan the map

### Overlay mode (float over Zillow / StreetEasy)

Generate the map, then open **`output/overlay.html`** (link also in the main map sidebar).

- **No basemap** — only isochrone rings on a transparent background
- **Opacity slider** — default 50%; adjust so streets show through on the app underneath
- **Zoom / pan** — match the other map by eye; no perfect alignment needed
- **H key** — hide the control panel for a clean overlay

Regular browser tabs are opaque, so for a floating window use a tool like [Helium](https://heliumfloats.com/) (macOS): open `overlay.html` in Helium, set window opacity, enable “always on top,” and place it over Zillow.

---

## Configuration

Edit `config.py` to change work location, arrival time, or band minutes.

| Setting | Default |
|---------|---------|
| Work | 240 Greenwich St (40.7130, -74.0115) |
| Arrive by | 8:30 AM ET, weekday (`2026-07-13T08:30:00-04:00`) |
| Bands | 10–50 min (saved from playground) |
| Default max commute | 30 min |

---

## Project layout

```
apartment-search/
├── config.py
├── run.py
├── scripts/
│   ├── save_streeteasy_pages.py   # Playwright bulk HTML capture
│   ├── import_listings_html.py
│   ├── apply_hitlist_status.py    # merge phone status.json → CSV
│   ├── run_hitlist_pipeline.py
│   ├── score_listings.py
│   ├── generate_hitlist_ui.py
│   ├── listing_utils.py
│   ├── process_listings.py
│   └── generate_map.py
├── StreetEasy HTMLs/              # gitignored; Playwright / Save Page As drops
├── data/
│   ├── listings.csv               # status + first/last_seen_at
│   ├── listings/incoming/
│   └── isochrones.geojson
├── output/
│   ├── hitlist.html
│   ├── hit_list.md
│   ├── index.html
│   └── overlay.html
└── sample/
    └── listings_sample.csv
```

---

## Troubleshooting

**401 / 403 from TravelTime** — Check Application ID and API Key in `.env`. Trial quotas may apply.

**Empty isochrones** — Verify coords and that public transport is available for the search area.

**Geocode failures** — Add borough and "New York, NY" to addresses. Wait 1+ sec between runs (Nominatim rate limit).

**Already have GeoJSON from playground?** — Save it as `data/isochrones.geojson`. Ensure each feature has `properties.search_id` like `30_min` (or `properties.minutes`). Then skip fetch and run `process_listings.py` + `generate_map.py`.
