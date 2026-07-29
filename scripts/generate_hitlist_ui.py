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


def listing_key(row: dict) -> str:
    url = (row.get("url") or "").strip().lower()
    addr = (row.get("address") or "").strip().lower()
    return url or addr


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


def listing_status(row: dict) -> str:
    raw = (row.get("status") or "active").strip().lower().replace("-", "_")
    if raw in {"offmarket", "off_the_market", "rented", "gone"}:
        return "off_market"
    if raw in {"active", "toured", "off_market"}:
        return raw
    return "active"


def action_row(row: dict, *, mode: str = "active") -> str:
    """mode: active | toured | off_market"""
    key = esc(listing_key(row))
    if mode == "toured":
        return (
            f'<div class="actions">'
            f'<button type="button" class="action-btn" data-status-set="active" data-key="{key}">'
            f'Restore to active</button>'
            f'<button type="button" class="action-btn" data-status-set="off_market" data-key="{key}">'
            f'Off the market</button></div>'
        )
    if mode == "off_market":
        return (
            f'<div class="actions">'
            f'<button type="button" class="action-btn" data-status-set="active" data-key="{key}">'
            f'Restore to active</button></div>'
        )
    return (
        f'<div class="actions">'
        f'<button type="button" class="action-btn" data-status-set="toured" data-key="{key}">'
        f'Mark as toured</button>'
        f'<button type="button" class="action-btn" data-status-set="off_market" data-key="{key}">'
        f'Off the market</button></div>'
    )


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
    key = esc(listing_key(row))
    status = listing_status(row)
    return f"""
<article class="card tone-{tone} listing-card" data-key="{key}" data-score="{score:.1f}" data-status="{status}">
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
      · geo {esc(bd.get("geography", 0))}
    </div>
    {action_row(row, mode="active")}
  </div>
</article>
"""


def render_tour_card(row: dict, when: str) -> str:
    score = float(row.get("score") or 0)
    tone = score_tone(score)
    tag_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags_for(row))
    commute = row.get("commute_min")
    commute_s = f"≤{commute} min" if commute is not None else "commute ?"
    key = esc(listing_key(row))
    status = listing_status(row)
    return f"""
<article class="card tone-{tone} tour-card listing-card" data-key="{key}" data-score="{score:.1f}" data-status="{status}">
  <div class="rank tour-when">{esc(when)}</div>
  <div class="body">
    <div class="topline">
      {title_block(row)}
      <div class="score">{score:.1f}</div>
    </div>
    <div class="meta tour-meta">{esc(row.get("open_house") or "")}</div>
    <div class="meta">{size_line(row)} · {esc(commute_s)}</div>
    <div class="tags">{tag_html}</div>
    {action_row(row, mode="active")}
  </div>
</article>
"""


def render_archive_card(row: dict, *, mode: str) -> str:
    score = float(row.get("score") or 0)
    tone = score_tone(score)
    tag_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags_for(row))
    key = esc(listing_key(row))
    status = listing_status(row)
    open_house = row.get("open_house") or ""
    extra = f'<div class="meta tour-meta">{esc(open_house)}</div>' if open_house else ""
    mark = "✓" if mode == "toured" else "—"
    return f"""
<article class="card tone-{tone} listing-card archive-card" data-key="{key}" data-score="{score:.1f}" data-status="{status}" data-bucket="{mode}">
  <div class="rank">{mark}</div>
  <div class="body">
    <div class="topline">
      {title_block(row)}
      <div class="score">{score:.1f}</div>
    </div>
    {extra}
    <div class="meta">{size_line(row)}</div>
    <div class="tags">{tag_html}</div>
    {action_row(row, mode=mode)}
  </div>
</article>
"""


def render(scored: list[dict], now: datetime | None = None) -> str:
    now = now or datetime.now()
    viable = [r for r in scored if not r.get("hard_reject")]
    rejected = [r for r in scored if r.get("hard_reject")]

    # Pipeline status is source of truth; phone localStorage overlays on top.
    active = [r for r in viable if listing_status(r) == "active"]
    csv_toured = [r for r in viable if listing_status(r) == "toured"]
    csv_off = [r for r in viable if listing_status(r) == "off_market"]

    # All viable cards are in the DOM; JS shows/hides by CSV status + localStorage overlay.
    # Ranked/tours include non-active rows so "Restore" can resurface them without a rebuild.
    ranked_cards = [render_ranked_card(i, row) for i, row in enumerate(viable, start=1)]
    toured_cards = [render_archive_card(row, mode="toured") for row in viable]
    off_market_cards = [render_archive_card(row, mode="off_market") for row in viable]

    with_tours = []
    for row in viable:
        start = parse_tour_start(row)
        if start is None:
            continue
        with_tours.append((start, row))
    with_tours.sort(key=lambda x: x[0])

    upcoming = [
        (dt, row)
        for dt, row in with_tours
        if dt.date() >= now.date() and listing_status(row) == "active"
    ]
    past = [
        (dt, row)
        for dt, row in with_tours
        if dt.date() < now.date() and listing_status(row) == "active"
    ]
    # Inactive tour cards stay in the DOM (JS-hidden) so Restore can resurface them.
    upcoming_dom = [(dt, row) for dt, row in with_tours if dt.date() >= now.date()]
    past_dom = [(dt, row) for dt, row in with_tours if dt.date() < now.date()]

    def when_label(dt: datetime, row: dict) -> str:
        if not row.get("open_house_end"):
            return "time TBA"
        hour = dt.hour % 12 or 12
        return f"{hour}:{dt.strftime('%M')} {dt.strftime('%p')}"

    tour_sections: list[str] = []
    current_bucket = None
    for dt, row in upcoming_dom:
        bucket = day_bucket(dt, now)
        if bucket != current_bucket:
            current_bucket = bucket
            tour_sections.append(f'<h2 class="day-head">{esc(bucket)}</h2>')
        tour_sections.append(render_tour_card(row, when_label(dt, row)))

    if not upcoming_dom:
        tour_sections.append(
            "<p class=\"empty\">No upcoming open houses in the current ingest. "
            "Re-save StreetEasy pages that show an “Open: …” badge.</p>"
        )

    if past_dom:
        tour_sections.append('<h2 class="day-head muted">Earlier (from this ingest)</h2>')
        for dt, row in past_dom:
            tour_sections.append(render_tour_card(row, when_label(dt, row)))

    reject_items = "".join(
        f"<li><strong>{esc(r.get('address'))}</strong> — "
        f"{esc('; '.join(r.get('concerns') or ['filtered']))}</li>"
        for r in rejected
    )

    seed_statuses = {
        listing_key(r): listing_status(r)
        for r in viable
        if listing_status(r) != "active"
    }
    seed_json = json.dumps(seed_statuses).replace("</", "<\\/")

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
    max-width: 42rem;
  }}
  .tabs {{
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
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
    font-size: 0.88rem;
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
  .tour-filters {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.75rem 1.25rem;
    margin: 0 0 1.1rem;
    padding: 0.7rem 0.85rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
  }}
  .tour-filters label {{
    display: flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.92rem;
    cursor: pointer;
    user-select: none;
  }}
  .tour-filters input {{
    width: 1.05rem;
    height: 1.05rem;
    accent-color: var(--accent);
  }}
  .tour-count {{
    color: var(--muted);
    font-size: 0.88rem;
    font-variant-numeric: tabular-nums;
  }}
  .sync-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin: 0 0 1rem;
  }}
  .listing-card.is-hidden,
  .day-head.is-hidden {{
    display: none;
  }}
  .actions {{
    margin-top: 0.75rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }}
  .action-btn {{
    appearance: none;
    border: 1px solid var(--line);
    background: transparent;
    color: var(--ink);
    border-radius: 999px;
    padding: 0.35rem 0.75rem;
    font: inherit;
    font-size: 0.82rem;
    cursor: pointer;
  }}
  .action-btn:active {{
    background: var(--tag);
  }}
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
    Ranked by preferences · tours from StreetEasy badges · status survives re-ingest
    (CSV is source of truth; phone marks overlay until you download status.json and apply it).
  </p>

  <div class="tabs" role="tablist">
    <button class="tab" role="tab" id="tab-ranked" aria-selected="true" aria-controls="panel-ranked">Ranked</button>
    <button class="tab" role="tab" id="tab-tours" aria-selected="false" aria-controls="panel-tours">Upcoming tours ({len(upcoming)})</button>
    <button class="tab" role="tab" id="tab-toured" aria-selected="false" aria-controls="panel-toured">Already toured <span id="toured-tab-count"></span></button>
    <button class="tab" role="tab" id="tab-off" aria-selected="false" aria-controls="panel-off">Off the market <span id="off-tab-count"></span></button>
  </div>

  <div class="sync-bar">
    <button type="button" class="action-btn" id="download-status">Download status.json</button>
  </div>

  <section class="panel active" id="panel-ranked" role="tabpanel">
    <div class="stats">
      <div><strong id="ranked-count">{len(active)}</strong> active ranked</div>
      <div><strong>{len(upcoming)}</strong> with upcoming tours</div>
      <div><strong>{len(csv_toured)}</strong> toured in CSV</div>
      <div><strong>{len(csv_off)}</strong> off-market in CSV</div>
      <div><strong>{len(rejected)}</strong> filtered</div>
    </div>
    <div id="ranked-list">
    {"".join(ranked_cards) if ranked_cards else "<p>No active listings passed hard filters.</p>"}
    </div>
    {f'<section class="filtered"><h2>Filtered out</h2><ul>{reject_items}</ul></section>' if rejected else ""}
  </section>

  <section class="panel" id="panel-tours" role="tabpanel">
    <p class="sub">Sorted soonest-first. Today / tomorrow grouped at the top.</p>
    <div class="tour-filters">
      <label>
        <input type="checkbox" id="tour-score-filter" checked />
        Only score ≥ 50
      </label>
      <span class="tour-count" id="tour-visible-count"></span>
    </div>
    <div id="tour-list">
    {"".join(tour_sections)}
    <p class="empty is-hidden" id="tour-empty-filter">No upcoming tours at score ≥ 50.</p>
    </div>
  </section>

  <section class="panel" id="panel-toured" role="tabpanel">
    <p class="sub">Places you’ve already seen. Restore puts them back in Ranked / Tours.</p>
    <div id="toured-list">
    {"".join(toured_cards)}
    <p class="empty" id="toured-empty">No toured listings yet.</p>
    </div>
  </section>

  <section class="panel" id="panel-off" role="tabpanel">
    <p class="sub">Rented / taken down. Restore if the listing comes back.</p>
    <div id="off-list">
    {"".join(off_market_cards)}
    <p class="empty" id="off-empty">No off-market listings yet.</p>
    </div>
  </section>
</main>
<script type="application/json" id="seed-statuses">{seed_json}</script>
<script>
(function () {{
  const STATUS_KEY = 'hitlist-status-map';
  const SCORE_KEY = 'hitlist-tours-score50';
  const MIN_SCORE = 50;
  const LEGACY_TOURED = 'hitlist-toured-keys';

  function loadStatusMap() {{
    let map = {{}};
    try {{
      const seedEl = document.getElementById('seed-statuses');
      if (seedEl && seedEl.textContent) {{
        map = {{ ...JSON.parse(seedEl.textContent) }};
      }}
    }} catch (e) {{}}
    try {{
      const raw = localStorage.getItem(STATUS_KEY);
      if (raw) map = {{ ...map, ...JSON.parse(raw) }};
    }} catch (e) {{}}
    // Migrate older toured-only localStorage
    try {{
      const legacy = localStorage.getItem(LEGACY_TOURED);
      if (legacy) {{
        const arr = JSON.parse(legacy);
        if (Array.isArray(arr)) {{
          arr.forEach((k) => {{ if (k && !map[k]) map[k] = 'toured'; }});
        }}
      }}
    }} catch (e) {{}}
    return map;
  }}

  function saveStatusMap(map) {{
    try {{ localStorage.setItem(STATUS_KEY, JSON.stringify(map)); }} catch (e) {{}}
  }}

  let statusMap = loadStatusMap();

  function effectiveStatus(card) {{
    const key = card.getAttribute('data-key') || '';
    if (statusMap[key]) return statusMap[key];
    return card.getAttribute('data-status') || 'active';
  }}

  const tabs = Array.from(document.querySelectorAll('.tab'));
  const panels = {{
    'tab-ranked': document.getElementById('panel-ranked'),
    'tab-tours': document.getElementById('panel-tours'),
    'tab-toured': document.getElementById('panel-toured'),
    'tab-off': document.getElementById('panel-off'),
  }};
  function activate(id) {{
    tabs.forEach((t) => t.setAttribute('aria-selected', t.id === id ? 'true' : 'false'));
    Object.entries(panels).forEach(([key, panel]) => {{
      panel.classList.toggle('active', key === id);
    }});
    const hashMap = {{ 'tab-tours': 'tours', 'tab-toured': 'toured', 'tab-off': 'off' }};
    const hash = hashMap[id] || '';
    if (hash) location.hash = hash;
    else if (['#tours', '#toured', '#off'].includes(location.hash)) {{
      history.replaceState(null, '', location.pathname);
    }}
  }}
  tabs.forEach((t) => t.addEventListener('click', () => activate(t.id)));
  if (location.hash === '#tours') activate('tab-tours');
  if (location.hash === '#toured') activate('tab-toured');
  if (location.hash === '#off') activate('tab-off');

  const scoreFilter = document.getElementById('tour-score-filter');
  const countEl = document.getElementById('tour-visible-count');
  const emptyEl = document.getElementById('tour-empty-filter');
  const tourList = document.getElementById('tour-list');
  const touredEmpty = document.getElementById('toured-empty');
  const offEmpty = document.getElementById('off-empty');
  const touredTabCount = document.getElementById('toured-tab-count');
  const offTabCount = document.getElementById('off-tab-count');

  function applyVisibility() {{
    let touredN = 0;
    let offN = 0;

    document.querySelectorAll('#ranked-list .listing-card').forEach((card) => {{
      card.classList.toggle('is-hidden', effectiveStatus(card) !== 'active');
    }});

    document.querySelectorAll('#tour-list .listing-card').forEach((card) => {{
      const inactive = effectiveStatus(card) !== 'active';
      card.classList.toggle('is-hidden', inactive);
    }});

    document.querySelectorAll('#toured-list .listing-card').forEach((card) => {{
      const show = effectiveStatus(card) === 'toured';
      card.classList.toggle('is-hidden', !show);
      if (show) touredN += 1;
    }});

    document.querySelectorAll('#off-list .listing-card').forEach((card) => {{
      const show = effectiveStatus(card) === 'off_market';
      card.classList.toggle('is-hidden', !show);
      if (show) offN += 1;
    }});

    if (touredTabCount) touredTabCount.textContent = touredN ? `(${{touredN}})` : '';
    if (offTabCount) offTabCount.textContent = offN ? `(${{offN}})` : '';
    if (touredEmpty) touredEmpty.classList.toggle('is-hidden', touredN > 0);
    if (offEmpty) offEmpty.classList.toggle('is-hidden', offN > 0);
  }}

  function applyTourFilter() {{
    const on = !!(scoreFilter && scoreFilter.checked);
    try {{ localStorage.setItem(SCORE_KEY, on ? '1' : '0'); }} catch (e) {{}}
    const cards = Array.from(tourList.querySelectorAll('.tour-card'));
    let visible = 0;
    cards.forEach((card) => {{
      const score = parseFloat(card.getAttribute('data-score') || '0');
      const inactive = effectiveStatus(card) !== 'active';
      const hideScore = on && score < MIN_SCORE;
      // Keep inactive hidden; score filter only among active
      if (inactive) {{
        card.classList.add('is-hidden');
        return;
      }}
      card.classList.toggle('is-hidden', hideScore);
      if (!hideScore) visible += 1;
    }});
    const nodes = Array.from(tourList.children);
    let i = 0;
    while (i < nodes.length) {{
      const node = nodes[i];
      if (!node.classList || !node.classList.contains('day-head')) {{
        i += 1;
        continue;
      }}
      let j = i + 1;
      let any = false;
      while (j < nodes.length && !(nodes[j].classList && nodes[j].classList.contains('day-head'))) {{
        const c = nodes[j];
        if (c.classList && c.classList.contains('tour-card') && !c.classList.contains('is-hidden')) {{
          any = true;
        }}
        j += 1;
      }}
      node.classList.toggle('is-hidden', !any);
      i = j;
    }}
    const totalActive = cards.filter((c) => effectiveStatus(c) === 'active').length;
    if (countEl) {{
      countEl.textContent = on
        ? `Showing ${{visible}} of ${{totalActive}} with tours`
        : `${{totalActive}} with tours`;
    }}
    if (emptyEl) {{
      emptyEl.classList.toggle('is-hidden', !(on && visible === 0 && totalActive > 0));
    }}
  }}

  function refresh() {{
    applyVisibility();
    applyTourFilter();
  }}

  document.addEventListener('click', (ev) => {{
    const btn = ev.target.closest('[data-status-set]');
    if (!btn) return;
    const key = btn.getAttribute('data-key');
    const status = btn.getAttribute('data-status-set');
    if (!key || !status) return;
    // Always store explicitly so Restore wins over data-status from CSV seed.
    statusMap[key] = status;
    saveStatusMap(statusMap);
    refresh();
  }});

  const dl = document.getElementById('download-status');
  if (dl) {{
    dl.addEventListener('click', () => {{
      const blob = new Blob([JSON.stringify({{ statuses: statusMap }}, null, 2)], {{ type: 'application/json' }});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'hitlist_status.json';
      a.click();
      URL.revokeObjectURL(a.href);
    }});
  }}

  if (scoreFilter) {{
    try {{
      const saved = localStorage.getItem(SCORE_KEY);
      if (saved === '0') scoreFilter.checked = false;
      if (saved === '1') scoreFilter.checked = true;
    }} catch (e) {{}}
    scoreFilter.addEventListener('change', applyTourFilter);
  }}
  refresh();
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
