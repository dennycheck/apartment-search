#!/usr/bin/env python3
"""Generate a standalone ranked hit-list UI from scored listings JSON.

Map-independent. Open output/hitlist.html in a browser.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import HIT_LIST_MD, LISTINGS_SCORED_JSON, OUTPUT_DIR


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def beds_label(row: dict) -> str:
    beds = row.get("beds_num")
    if beds is None:
        raw = row.get("beds", "")
        if str(raw).strip() == "0" or str(raw).lower() == "studio":
            return "Studio"
        return esc(raw) if raw else "?"
    if beds == 0:
        return "Studio"
    return f"{beds}BR"


def tags_for(row: dict) -> list[str]:
    tags: list[str] = []
    am = str(row.get("amenities") or "").lower()
    notes = str(row.get("notes") or "").lower()
    blob = f"{am} {notes}"
    if "no fee" in blob:
        tags.append("No fee")
    if row.get("dishwasher") in ("yes", True, "true"):
        tags.append("Dishwasher")
    if row.get("in_unit_laundry") in ("yes", True, "true"):
        tags.append("In-unit W/D")
    if "pool" in blob:
        tags.append("Pool")
    if "gym" in blob or "fitness" in blob:
        tags.append("Gym")
    if "amenity" in blob:
        tags.append("Amenity building")
    if row.get("neighborhood"):
        tags.append(str(row["neighborhood"]))
    commute = row.get("commute_min")
    if commute is not None:
        tags.append(f"≤{commute} min")
    elif row.get("geocode_error"):
        tags.append("Geocode failed")
    else:
        tags.append("Commute pending")
    return tags


def score_tone(score: float, hard_reject: bool) -> str:
    if hard_reject:
        return "reject"
    if score >= 70:
        return "strong"
    if score >= 50:
        return "mid"
    return "weak"


def render(scored: list[dict]) -> str:
    kept = [r for r in scored if not r.get("hard_reject")]
    rejected = [r for r in scored if r.get("hard_reject")]

    cards = []
    for i, row in enumerate(kept, start=1):
        score = float(row.get("score") or 0)
        tone = score_tone(score, False)
        title = row.get("address") or "(no address)"
        url = row.get("url") or ""
        title_html = (
            f'<a class="title" href="{esc(url)}" target="_blank" rel="noopener">{esc(title)}</a>'
            if url
            else f'<span class="title">{esc(title)}</span>'
        )
        rent = row.get("rent") or "—"
        size = beds_label(row)
        if row.get("sqft_num"):
            size = f"{size} · {row['sqft_num']} sqft"
        elif row.get("sqft"):
            size = f"{size} · {esc(row['sqft'])} sqft"

        tag_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags_for(row))
        likes = row.get("likes") or []
        concerns = row.get("concerns") or []
        likes_html = "".join(f"<li>{esc(x)}</li>" for x in likes[:6])
        concerns_html = "".join(f"<li>{esc(x)}</li>" for x in concerns[:4])
        bd = row.get("score_breakdown") or {}

        cards.append(
            f"""
<article class="card tone-{tone}">
  <div class="rank">{i}</div>
  <div class="body">
    <div class="topline">
      {title_html}
      <div class="score">{score:.1f}</div>
    </div>
    <div class="meta">{esc(rent)} · {size}</div>
    <div class="tags">{tag_html}</div>
    <div class="cols">
      <div>
        <div class="label">Why it ranks</div>
        <ul>{likes_html or "<li>—</li>"}</ul>
      </div>
      <div>
        <div class="label">Watch-outs</div>
        <ul class="concerns">{concerns_html or "<li>None flagged</li>"}</ul>
      </div>
    </div>
    <div class="breakdown">
      commute {esc(bd.get("commute", "—"))}
      · size {esc(bd.get("size", "—"))}
      · rent {esc(bd.get("rent", "—"))}
      · unit {esc(bd.get("unit_amenities", "—"))}
      · building {esc(bd.get("building_extras", "—"))}
    </div>
  </div>
</article>
"""
        )

    reject_items = "".join(
        f"<li><strong>{esc(r.get('address'))}</strong> — "
        f"{esc('; '.join(r.get('concerns') or ['filtered']))}</li>"
        for r in rejected
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Apartment hit list</title>
<style>
  :root {{
    --bg: #f3efe6;
    --ink: #1c1a16;
    --muted: #6b6458;
    --card: #fffdf8;
    --line: #d9d0c0;
    --strong: #0f6b4c;
    --mid: #9a6b12;
    --weak: #7a4a3a;
    --reject: #8a3030;
    --tag: #ebe4d6;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--ink);
    line-height: 1.45;
  }}
  main {{
    max-width: 820px;
    margin: 0 auto;
    padding: 2rem 1.25rem 4rem;
  }}
  h1 {{
    font-family: "IBM Plex Serif", Georgia, serif;
    font-weight: 600;
    font-size: 1.85rem;
    margin: 0 0 0.35rem;
    letter-spacing: -0.02em;
  }}
  .sub {{
    color: var(--muted);
    margin: 0 0 1.75rem;
    max-width: 40rem;
  }}
  .stats {{
    display: flex;
    gap: 1.25rem;
    flex-wrap: wrap;
    margin-bottom: 1.5rem;
    font-size: 0.95rem;
  }}
  .stats strong {{ font-variant-numeric: tabular-nums; }}
  .card {{
    display: grid;
    grid-template-columns: 2.5rem 1fr;
    gap: 0.75rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1rem 1rem 0.85rem;
    margin-bottom: 0.85rem;
  }}
  .rank {{
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    color: var(--muted);
    padding-top: 0.15rem;
  }}
  .topline {{
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: start;
  }}
  .title {{
    font-weight: 600;
    color: inherit;
    text-decoration: none;
  }}
  a.title:hover {{ text-decoration: underline; }}
  .score {{
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    font-size: 1.25rem;
    min-width: 3.5rem;
    text-align: right;
  }}
  .tone-strong .score {{ color: var(--strong); }}
  .tone-mid .score {{ color: var(--mid); }}
  .tone-weak .score {{ color: var(--weak); }}
  .meta {{
    color: var(--muted);
    font-size: 0.95rem;
    margin: 0.2rem 0 0.55rem;
  }}
  .tags {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-bottom: 0.75rem;
  }}
  .tag {{
    background: var(--tag);
    border-radius: 999px;
    padding: 0.15rem 0.55rem;
    font-size: 0.78rem;
    color: var(--ink);
  }}
  .cols {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem 1.25rem;
  }}
  @media (max-width: 640px) {{
    .cols {{ grid-template-columns: 1fr; }}
  }}
  .label {{
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    margin-bottom: 0.2rem;
  }}
  ul {{
    margin: 0;
    padding-left: 1.1rem;
    font-size: 0.9rem;
  }}
  ul.concerns {{ color: var(--weak); }}
  .breakdown {{
    margin-top: 0.7rem;
    font-size: 0.78rem;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }}
  .filtered {{
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--line);
  }}
  .filtered h2 {{
    font-size: 1rem;
    margin: 0 0 0.5rem;
  }}
</style>
</head>
<body>
<main>
  <h1>Apartment hit list</h1>
  <p class="sub">
    Ranked by composite score from <code>apartment_preferences.md</code>.
    Commute uses isochrone bands only — this page is separate from the map.
  </p>
  <div class="stats">
    <div><strong>{len(kept)}</strong> ranked</div>
    <div><strong>{len(rejected)}</strong> filtered (hard rules)</div>
    <div><strong>{len(scored)}</strong> total ingested</div>
  </div>
  {"".join(cards) if cards else "<p>No listings passed hard filters.</p>"}
  {f'<section class="filtered"><h2>Filtered out</h2><ul>{reject_items}</ul></section>' if rejected else ""}
</main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Build hit-list HTML UI")
    parser.add_argument("--input", type=Path, default=LISTINGS_SCORED_JSON)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "hitlist.html")
    args = parser.parse_args()

    if not args.input.exists():
        print(
            f"No scored listings at {args.input}. Run score_listings.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    scored = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(scored), encoding="utf-8")
    print(f"Wrote {args.output} ({len(scored)} listings)")
    if HIT_LIST_MD.exists():
        print(f"Also see {HIT_LIST_MD}")


if __name__ == "__main__":
    main()
