# Apartment preferences

Scoring is soft-weighted. Commute dominates; only hard filter is max rent.
This file drives `scripts/score_listings.py` → `output/hit_list.md`.
The commute map is not involved — only the isochrone polygons for `commute_min`.

## Context

- Work: 240 Greenwich St (arrive-by ~8:30 AM transit bands).
- Current: 292 Stockholm St (Bushwick), darker orange band (~35–40 min).
- Goal: shorter commute. A move should improve by ~two subbands (~10 min) to feel worthwhile.
- Ideal: ≤30 min.

## Hard filters

- Max rent: $4000
- Beds: studio, 1BR, or 2BR OK

## Soft criteria (weights sum to 100)

### Commute — weight 45

- Ideal: ≤30 min
- Strong: ≤ ~current − 10 (two 5-min subbands inward from ~40 → ~30)
- Mild positive: any clear improvement vs ~40
- Soft penalty: ~same as current (~35–40)
- Steep soft penalty: worse than current (>40), escalating through 50/60
- Do not hard-reject on commute alone

### Size / layout — weight 20

- Prefer more square footage when known
- Bed label secondary: large studio can beat small 1BR
- 2BR is a plus if it fits rent; not required

### Rent / value — weight 15

- Cap already applied at $4000
- Prefer lower rent for similar commute/size/amenities

### Unit amenities — weight 12

- Dishwasher: strong positive
- In-unit washer/dryer: stronger positive
- Other fixture/quality signals if extractable: modest bonus

### Building extras — weight 8

- Luxury building amenity package (gym, pool, etc.): bonus only
- Absence is not a dealbreaker

### Geography — soft adjustment (not in the 100-pt base)

- Prefer **west of Nostrand Ave** (eastern edge of the preferred A/C belt in central Brooklyn).
- East of Nostrand is a soft demotion (not a hard reject) — e.g. Albany Ave / deeper Bed-Stuy.
- Applied after the base score using geocoded longitude.

## Tie-breaks

When composite scores are close: (1) better commute, (2) west of Nostrand, (3) more usable size, (4) in-unit W/D or dishwasher, (5) lower rent.

## Hit-list output

For each ranked listing: overall score, commute_min, rent, beds/sqft, amenity flags, and short likes/concerns explaining the score.
