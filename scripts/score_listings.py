#!/usr/bin/env python3
"""Score processed listings against apartment preferences → ranked hit list.

Uses commute_min from isochrone point-in-polygon (data/isochrones.geojson).
Does not generate or update the map.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    CURRENT_COMMUTE_MIN,
    HIT_LIST_MD,
    LISTINGS_JSON,
    LISTINGS_SCORED_JSON,
    MAX_RENT,
    NOSTRAND_AVE_LNG,
    PREFERENCES_MD,
)
from scripts.listing_utils import (
    amenity_list,
    parse_bool,
    parse_int,
    parse_rent,
    write_json,
)

# Soft weights (sum 100) — mirrored in data/apartment_preferences.md
W_COMMUTE = 45
W_SIZE = 20
W_RENT = 15
W_UNIT = 12
W_BUILDING = 8

BUILDING_AMENITIES = {
    "gym",
    "fitness",
    "pool",
    "doorman",
    "concierge",
    "roof deck",
    "rooftop",
    "lounge",
    "parking",
    "elevator",
}


def commute_points(commute_min: int | None) -> tuple[float, str]:
    """0–W_COMMUTE. Soft curve around current ~40 and ideal ≤30."""
    if commute_min is None:
        return 8.0, "commute unknown (geocode/band miss)"

    c = commute_min
    # Peak at ≤20–30; strong at ≤30 (two subbands in from ~40); soft falloff after.
    if c <= 10:
        pts, note = 45.0, "excellent commute (≤10)"
    elif c <= 20:
        pts, note = 43.0, "excellent commute (≤20)"
    elif c <= 30:
        pts, note = 40.0, "ideal band (≤30) — worthwhile vs current ~40"
    elif c <= 35:
        pts, note = 28.0, "better than current, shy of ideal ≤30"
    elif c <= CURRENT_COMMUTE_MIN:
        pts, note = 16.0, "similar to current (~40) — weak reason to move"
    elif c <= 45:
        pts, note = 8.0, "slightly worse than current"
    elif c <= 50:
        pts, note = 4.0, "worse commute than current"
    else:
        pts, note = 1.0, "much worse commute"

    return pts, note


def size_points(sqft: int | None, beds: int | None) -> tuple[float, str]:
    if sqft:
        if sqft >= 900:
            return 20.0, f"spacious (~{sqft} sqft)"
        if sqft >= 750:
            return 17.0, f"solid size (~{sqft} sqft)"
        if sqft >= 600:
            return 14.0, f"decent size (~{sqft} sqft)"
        if sqft >= 450:
            return 10.0, f"compact (~{sqft} sqft)"
        return 6.0, f"small (~{sqft} sqft)"

    if beds is None:
        return 8.0, "size unknown"
    if beds >= 2:
        return 16.0, "2BR (sqft unknown — bed label only)"
    if beds == 1:
        return 11.0, "1BR (sqft unknown)"
    if beds == 0:
        return 9.0, "studio (sqft unknown)"
    return 8.0, "layout unclear"


def rent_points(rent: int | None) -> tuple[float, str]:
    if rent is None:
        return 7.0, "rent unknown"
    # Prefer lower within the allowed band; $2500→15, $4000→3
    span = max(MAX_RENT - 2500, 1)
    ratio = max(0.0, min(1.0, (MAX_RENT - rent) / span))
    pts = 3.0 + 12.0 * ratio
    return pts, f"${rent}/mo"


def unit_amenity_points(listing: dict) -> tuple[float, list[str]]:
    pts = 0.0
    likes: list[str] = []
    if parse_bool(listing.get("dishwasher")):
        pts += 5.0
        likes.append("dishwasher")
    if parse_bool(listing.get("in_unit_laundry")):
        pts += 7.0
        likes.append("in-unit W/D")
    # Cap at W_UNIT
    return min(pts, float(W_UNIT)), likes


def building_amenity_points(listing: dict) -> tuple[float, list[str]]:
    ams = {a.lower() for a in amenity_list(listing.get("amenities"))}
    notes_text = " ".join(
        [
            str(listing.get("amenities", "")),
            str(listing.get("notes", "")),
        ]
    ).lower()
    hits: list[str] = []
    for label in BUILDING_AMENITIES:
        if label in ams or label in notes_text:
            hits.append(label)
    # Unique-ish
    hits = list(dict.fromkeys(hits))
    pts = min(float(W_BUILDING), 2.5 * len(hits))
    return pts, hits


def geography_adjustment(lng: float | None) -> tuple[float, str | None]:
    """Soft preference: west of Nostrand Ave. Returns (delta, note).

    East of Nostrand along the A/C spur is a meaningful demotion (not a hard reject).
    At NYC latitudes, ~0.01° longitude ≈ 0.5 miles.
    """
    if lng is None:
        return 0.0, None
    if lng <= NOSTRAND_AVE_LNG:
        return 0.0, "west of Nostrand Ave (preferred belt)"
    miles_east = (lng - NOSTRAND_AVE_LNG) * 52.0
    # Albany Ave (~0.6 mi east) → ~17 pt hit; farther east escalates to ~22.
    penalty = min(22.0, 10.0 + miles_east * 12.0)
    return -round(penalty, 1), f"east of Nostrand Ave (~{miles_east:.1f} mi) — prefer west"


def score_listing(listing: dict) -> dict:
    rent = parse_rent(listing.get("rent"))
    beds = parse_int(listing.get("beds"))
    sqft = parse_int(listing.get("sqft"))
    commute = listing.get("commute_min")
    if isinstance(commute, str) and commute.isdigit():
        commute = int(commute)
    lng = listing.get("lng")
    if isinstance(lng, str):
        try:
            lng = float(lng)
        except ValueError:
            lng = None

    hard_reject = False
    reject_reasons: list[str] = []
    if rent is not None and rent > MAX_RENT:
        hard_reject = True
        reject_reasons.append(f"over max rent (${rent} > ${MAX_RENT})")

    c_pts, c_note = commute_points(commute if isinstance(commute, int) else None)
    s_pts, s_note = size_points(sqft, beds)
    r_pts, r_note = rent_points(rent)
    u_pts, u_likes = unit_amenity_points(listing)
    b_pts, b_likes = building_amenity_points(listing)
    g_delta, g_note = geography_adjustment(lng if isinstance(lng, float) else None)

    total = round(c_pts + s_pts + r_pts + u_pts + b_pts + g_delta, 1)
    if hard_reject:
        total = 0.0

    likes: list[str] = []
    concerns: list[str] = []

    if c_pts >= 40:
        likes.append(c_note)
    elif c_pts >= 28:
        likes.append(c_note)
    else:
        concerns.append(c_note)

    if s_pts >= 14:
        likes.append(s_note)
    elif "unknown" in s_note:
        concerns.append(s_note)
    else:
        concerns.append(s_note)

    likes.append(r_note)
    likes.extend(u_likes)
    if b_likes:
        likes.append("building: " + ", ".join(b_likes))
    if g_delta < 0 and g_note:
        concerns.append(g_note)
    elif g_note and g_delta == 0 and lng is not None and lng <= NOSTRAND_AVE_LNG:
        likes.append(g_note)
    concerns.extend(reject_reasons)

    return {
        **listing,
        "score": total,
        "score_breakdown": {
            "commute": round(c_pts, 1),
            "size": round(s_pts, 1),
            "rent": round(r_pts, 1),
            "unit_amenities": round(u_pts, 1),
            "building_extras": round(b_pts, 1),
            "geography": round(g_delta, 1),
        },
        "hard_reject": hard_reject,
        "likes": likes,
        "concerns": concerns,
        "rent_num": rent,
        "beds_num": beds,
        "sqft_num": sqft,
    }


def beds_label(beds: int | None) -> str:
    if beds is None:
        return "?"
    if beds == 0:
        return "studio"
    return f"{beds}BR"


def render_hit_list(scored: list[dict], prefs_path: Path) -> str:
    lines = [
        "# Apartment hit list",
        "",
        f"Ranked by composite score (preferences: `{prefs_path.name}`). "
        "Commute from isochrone bands only — map not updated.",
        "",
        f"Hard filter: rent ≤ ${MAX_RENT}. Current baseline commute ≈ {CURRENT_COMMUTE_MIN} min.",
        "",
    ]

    kept = [s for s in scored if not s.get("hard_reject")]
    rejected = [s for s in scored if s.get("hard_reject")]

    if not kept:
        lines.append("_No listings passed the hard filters._")
        lines.append("")
    else:
        lines.append(f"**{len(kept)}** candidates ranked (of {len(scored)} processed).")
        lines.append("")
        for i, row in enumerate(kept, start=1):
            commute = row.get("commute_min")
            commute_s = f"≤{commute} min" if commute is not None else "unknown"
            rent = row.get("rent") or "—"
            beds = beds_label(row.get("beds_num"))
            sqft = row.get("sqft_num")
            size_s = f"{beds}" + (f", {sqft} sqft" if sqft else "")
            url = row.get("url") or ""
            title = row.get("address", "(no address)")
            if url:
                title = f"[{title}]({url})"

            bd = row.get("score_breakdown") or {}
            lines.append(f"## {i}. {title}")
            lines.append("")
            lines.append(
                f"**Score {row['score']:.1f}** · {commute_s} · {rent} · {size_s}"
            )
            lines.append("")
            lines.append(
                f"_Breakdown:_ commute {bd.get('commute', 0)} / "
                f"size {bd.get('size', 0)} / rent {bd.get('rent', 0)} / "
                f"unit {bd.get('unit_amenities', 0)} / building {bd.get('building_extras', 0)} / "
                f"geo {bd.get('geography', 0)}"
            )
            lines.append("")
            if row.get("likes"):
                lines.append("**Likes**")
                for item in row["likes"]:
                    lines.append(f"- {item}")
                lines.append("")
            if row.get("concerns"):
                lines.append("**Concerns**")
                for item in row["concerns"]:
                    lines.append(f"- {item}")
                lines.append("")

    if rejected:
        lines.append("---")
        lines.append("")
        lines.append(f"## Filtered out ({len(rejected)})")
        lines.append("")
        for row in rejected:
            reason = "; ".join(row.get("concerns") or ["hard filter"])
            lines.append(f"- {row.get('address', '?')} — {reason}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Rank listings into a hit list")
    parser.add_argument(
        "--input",
        type=Path,
        default=LISTINGS_JSON,
        help="Processed listings JSON (default: data/listings_processed.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=HIT_LIST_MD,
        help="Hit list markdown path",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=0,
        help="If >0, only keep top N in the markdown (all still saved to scored JSON)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(
            f"No processed listings at {args.input}. Run: python scripts/process_listings.py",
            file=sys.stderr,
        )
        sys.exit(1)

    listings = json.loads(args.input.read_text(encoding="utf-8"))
    scored = [score_listing(row) for row in listings]
    scored.sort(
        key=lambda x: (
            x.get("hard_reject", False),
            -(x.get("score") or 0),
            x.get("commute_min") is None,
            x.get("commute_min") or 999,
            x.get("rent_num") or 99999,
        )
    )

    write_json(LISTINGS_SCORED_JSON, scored)

    md_rows = scored
    if args.top > 0:
        md_rows = [s for s in scored if not s.get("hard_reject")][: args.top] + [
            s for s in scored if s.get("hard_reject")
        ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_hit_list(md_rows, PREFERENCES_MD), encoding="utf-8")

    kept = [s for s in scored if not s.get("hard_reject")]
    print(f"Scored {len(scored)} listings → {args.output}")
    print(f"  {len(kept)} passed hard filters; top score: {kept[0]['score'] if kept else '—'}")
    print(f"  Full scored data → {LISTINGS_SCORED_JSON}")
    if PREFERENCES_MD.exists():
        print(f"  Preferences → {PREFERENCES_MD}")


if __name__ == "__main__":
    main()
