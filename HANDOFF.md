# Apartment Search Tool — Agent Handoff

## Goal
Build a personal NYC apartment search tool: commute isochrones on a map + filter listings by travel time to work.

**Work address:** 240 Greenwich St, New York, NY  
**Commute:** Public transit (+ walking), weekday morning arrive-by ~9 AM (confirm with user)  
**Time bands of interest:** 10, 20, 30, 40, 50, 60 minutes

## Agreed Stack (phased)

### Phase 1 — Visual exploration (user may be doing this)
- **TravelTime** isochrone map: https://app.traveltime.com
- Mode: Public Transport, origin = work address
- **Note:** app.traveltime.com has NO GeoJSON export — visual only

### Phase 2 — GeoJSON + automation (recommended build)
```
TravelTime API → GeoJSON polygons → Leaflet map → CSV listings → geocode → point-in-polygon filter
```

**GeoJSON export path:**
1. Sign up: https://account.traveltime.com (free trial)
2. Playground: https://playground.traveltime.com/isochrones
3. Set `Accept: application/geo+json`
4. Arrival search, `public_transport`, `weekday_morning`, coords ~40.7130, -74.0115
5. Use "Add multiple isochrones" for 10–60 min bands
6. Save response as `.geojson`, verify at https://geojson.io

**Listings:** No Zillow/StreetEasy API. Manual CSV from StreetEasy/Zillow searches → geocode → filter by polygon. Paid APIs (RentCast, ATTOM) overkill for personal use.

**Skip for now:** OpenTripPlanner/GTFS setup, Zillow scrapers, Felt/Mapbox Studio for automated workflow.

### Phase 3 — Optional later
- Exact per-listing commute times (TravelTime Time Filter API)
- Favorites, notes, alerts

## MVP to build (user preference TBD)
- **Option A:** Python script + static HTML map (simplest) — **SELECTED**
- **Option B:** Small web app (React or plain JS)

**User choices (Jul 9, 2026):**
- Arrive-by: **8:30 AM** weekdays
- Build: **Option A** (Python + static HTML)
- Commute band: **show all bands, toggle on map** (default highlight ≤40 min)
- API keys: **not yet** — see README Step 1

**MVP features (built):**
1. Fetch/display isochrone bands (TravelTime API, user provides keys)
2. Leaflet map with colored polygons, toggle active cutoff (e.g. ≤40 min)
3. CSV upload: `address, rent, beds, url, notes`
4. Geocode (Nominatim free, or Mapbox token)
5. Pin listings, highlight in-zone vs out-of-zone, sortable table

## TravelTime API quick ref
- Endpoint: `POST https://api.traveltimeapp.com/v4/time-map/fast`
- Headers: `Accept: application/geo+json`, `X-Application-Id`, `X-Api-Key`
- `travel_time` in seconds: 600=10m, 1200=20m, 1800=30m, 2400=40m, 3000=50m, 3600=60m

## Workspace / memory incident
- **Project folder:** `/Users/dennischeck/apartment-search`
- **Do NOT** open `/Users/dennischeck` as workspace — caused runaway `rg` indexing of entire home directory (~77GB memory spike)
- **Scope all work to** `~/apartment-search` only; no broad glob/grep outside project
- `.cursorignore` added

## Open questions for user
~~All resolved Jul 9, 2026~~ — pending: user adds TravelTime API keys to `.env` and runs `python run.py`
