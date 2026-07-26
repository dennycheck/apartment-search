#!/usr/bin/env python3
"""Generate a standalone ranked hit-list UI from scored listings JSON.

Views:
  - Ranked (composite score)
  - Upcoming tours (chronological open houses from StreetEasy badges)

Map-independent. Open output/hitlist.html in a browser.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

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
    if row.get("open_house"):
        tags.append(str(row["open_house"]))
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
    if "amenity" in blob or "new development" in blob:
        tags.append("Amenity / new dev")
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


def score_tone(score: float) -> str:
    if score >= 70:
        return "strong"
    if score >= 50:
        return "mid"
    return "weak"


def title_block(row: dict) -> str:
    title = row.get("address") or "(no address)"
    url = row.get("url") or ""
    maps_url = f"https://maps.apple.com/?address={quote_plus(title)}"
    maps_button = (
        f'<a class="maps-btn" href="{maps_url}" target="_blank" rel="noopener" '
        f'title="Open in Maps">📍</a>'
    )
    title_html = (
        f'<a class="title" href="{esc(url)}" target="_blank" rel="noopener">{esc(title)}</a>'
        if url
        else f'<span class="title">{esc(title)}</span>'
    )
    return f'<div class="title-with-maps">{title_html}{maps_button}</div>'


def size_line(row: dict) -> str:
    rent = row.get("rent") or "—"
    size = beds_label(row)
    if row.get("sqft_num"):
        size = f"{size} · {row['sqft_num']} sqft"
    elif row.get("sqft"):
        size = f"{size} · {esc(row['sqft'])} sqft"
    return f"{esc(rent)} · {size}"


def parse_tour_start(row: dict) -> datetime | None:
    raw = row.get("open_house_start") or ""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def day_bucket(dt: datetime, now: datetime) -> str:
    d = dt.date()
    today = now.date()
    delta = (d - today).days
    if delta < 0:
        return "Past"
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta < 7:
        return dt.strftime("%A")  # e.g. Wednesday
    return dt.strftime("%a %b ") + str(dt.day)


def render_ranked_card(i: int, row: dict) -> str:
    score = float(row.get("score") or 0)
    tone = score_tone(score)
    tag_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags_for(row))
    likes = row.get("likes") or []
    concerns = row.get("concerns") or []
    likes_html = "".join(f"<li>{esc(x)}</li>" for x in likes[:6])
    concerns_html = "".join(f"<li>{esc(x)}</li>" for x in concerns[:4])
    bd = row.get("score_breakdown") or {}
    return f"""
<article class="card tone-{tone}">
  <div class="rank">{i}</div>
  <div class="body">
    <div class="topline">
      {title_block(row)}
      <div class="score">{score:.1f}</div>
    </div>
    <div class="meta">{size_line(row)}</div>
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


def render_tour_card(row: dict, when: str) -> str:
    score = float(row.get("score") or 0)
    tone = score_tone(score)
    tag_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags_for(row))
    commute = row.get("commute_min")
    commute_s = f"≤{commute} min" if commute is not None else "commute ?"
    return f"""
<article class="card tone-{tone} tour-card">
  <div class="rank tour-when">{esc(when)}</div>
  <div class="body">
    <div class="topline">
      {title_block(row)}
      <div class="score">{score:.1f}</div>
    </div>
    <div class="meta tour-meta">{esc(row.get("open_house") or "")}</div>
    <div class="meta">{size_line(row)} · {esc(commute_s)}</div>
    <div class="tags">{tag_html}</div>
  </div>
</article>
"""


def render(scored: list[dict], now: datetime | None = None) -> str:
    now = now or datetime.now()
    kept = [r for r in scored if not r.get("hard_reject")]
    rejected = [r for r in scored if r.get("hard_reject")]

    ranked_cards = [render_ranked_card(i, row) for i, row in enumerate(kept, start=1)]

    with_tours = []
    for row in kept:
        start = parse_tour_start(row)
        if start is None:
            continue
        with_tours.append((start, row))
    with_tours.sort(key=lambda x: x[0])

    upcoming = [(dt, row) for dt, row in with_tours if dt.date() >= now.date()]
    past = [(dt, row) for dt, row in with_tours if dt.date() < now.date()]

    tour_sections: list[str] = []
    current_bucket = None
    for dt, row in upcoming:
        bucket = day_bucket(dt, now)
        if bucket != current_bucket:
            current_bucket = bucket
            tour_sections.append(f'<h2 class="day-head">{esc(bucket)}</h2>')
        hour = dt.hour % 12 or 12
        when = f"{hour}:{dt.strftime('%M')} {dt.strftime('%p')}"
        tour_sections.append(render_tour_card(row, when))

    if not upcoming:
        tour_sections.append(
            "<p class=\"empty\">No upcoming open houses in the current ingest. "
            "Re-save StreetEasy pages that show an “Open: …” badge.</p>"
        )

    if past:
        tour_sections.append('<h2 class="day-head muted">Earlier (from this ingest)</h2>')
        for dt, row in past:
            hour = dt.hour % 12 or 12
            when = f"{hour}:{dt.strftime('%M')} {dt.strftime('%p')}"
            tour_sections.append(render_tour_card(row, when))

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
    --tag: #ebe4d6;
    --accent: #1c4d3a;
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
    margin: 0 0 1.25rem;
    max-width: 40rem;
  }}
  .tabs {{
    display: flex;
    gap: 0.4rem;
    margin-bottom: 1.25rem;
    position: sticky;
    top: 0;
    z-index: 5;
    background: var(--bg);
    padding: 0.65rem 0 0.75rem;
    border-bottom: 1px solid var(--line);
  }}
  .tab {{
    appearance: none;
    border: 1px solid var(--line);
    background: var(--card);
    color: var(--ink);
    border-radius: 999px;
    padding: 0.45rem 0.9rem;
    font: inherit;
    font-size: 0.92rem;
    cursor: pointer;
  }}
  .tab[aria-selected="true"] {{
    background: var(--accent);
    border-color: var(--accent);
    color: #f7f3ea;
  }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .stats {{
    display: flex;
    gap: 1.25rem;
    flex-wrap: wrap;
    margin-bottom: 1.5rem;
    font-size: 0.95rem;
  }}
  .stats strong {{ font-variant-numeric: tabular-nums; }}
  .day-head {{
    font-size: 1.05rem;
    margin: 1.4rem 0 0.65rem;
    font-weight: 600;
  }}
  .day-head.muted {{ color: var(--muted); font-weight: 500; }}
  .empty {{ color: var(--muted); }}
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
  .tour-card {{
    grid-template-columns: 4.25rem 1fr;
  }}
  .rank {{
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    color: var(--muted);
    padding-top: 0.15rem;
  }}
  .tour-when {{
    font-size: 0.78rem;
    line-height: 1.25;
    color: var(--accent);
  }}
  .topline {{
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: start;
  }}
  .title-with-maps {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
  }}
  .title {{
    font-weight: 600;
    color: inherit;
    text-decoration: none;
  }}
  a.title:hover {{ text-decoration: underline; }}
  .maps-btn {{
    font-size: 1.1rem;
    text-decoration: none;
    opacity: 0.7;
    flex-shrink: 0;
    line-height: 1;
    padding: 0.25rem;
  }}
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
  .tour-meta {{
    color: var(--accent);
    font-weight: 600;
    margin-bottom: 0.15rem;
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
    Ranked by preferences · tours pulled from StreetEasy “Open: …” badges.
  </p>

  <div class="tabs" role="tablist">
    <button class="tab" role="tab" id="tab-ranked" aria-selected="true" aria-controls="panel-ranked">Ranked</button>
    <button class="tab" role="tab" id="tab-tours" aria-selected="false" aria-controls="panel-tours">Upcoming tours ({len(upcoming)})</button>
  </div>

  <section class="panel active" id="panel-ranked" role="tabpanel">
    <div class="stats">
      <div><strong>{len(kept)}</strong> ranked</div>
      <div><strong>{len(upcoming)}</strong> with upcoming tours</div>
      <div><strong>{len(rejected)}</strong> filtered</div>
    </div>
    {"".join(ranked_cards) if ranked_cards else "<p>No listings passed hard filters.</p>"}
    {f'<section class="filtered"><h2>Filtered out</h2><ul>{reject_items}</ul></section>' if rejected else ""}
  </section>

  <section class="panel" id="panel-tours" role="tabpanel">
    <p class="sub">Sorted soonest-first. Today / tomorrow grouped at the top.</p>
    {"".join(tour_sections)}
  </section>
</main>
<script>
(function () {{
  const tabs = Array.from(document.querySelectorAll('.tab'));
  const panels = {{
    'tab-ranked': document.getElementById('panel-ranked'),
    'tab-tours': document.getElementById('panel-tours'),
  }};
  function activate(id) {{
    tabs.forEach((t) => {{
      const on = t.id === id;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    }});
    Object.entries(panels).forEach(([key, panel]) => {{
      panel.classList.toggle('active', key === id);
    }});
    if (id === 'tab-tours') location.hash = 'tours';
    else if (location.hash === '#tours') history.replaceState(null, '', location.pathname);
  }}
  tabs.forEach((t) => t.addEventListener('click', () => activate(t.id)));
  if (location.hash === '#tours') activate('tab-tours');
}})();
</script>
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
    tours = sum(1 for r in scored if r.get("open_house_start"))
    print(f"  Open-house badges: {tours}")
    if HIT_LIST_MD.exists():
        print(f"Also see {HIT_LIST_MD}")


if __name__ == "__main__":
    main()
