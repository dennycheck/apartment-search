#!/usr/bin/env python3
"""Generate a static Leaflet map HTML from isochrones and processed listings."""

import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    BAND_COLORS,
    DEFAULT_COMMUTE_MAX,
    ISOCHRONES_CONTOURS_PATH,
    ISOCHRONES_PATH,
    LISTINGS_JSON,
    MAP_HTML,
    OVERLAY_DEFAULT_OPACITY,
    OVERLAY_HTML,
    POIS_JSON,
    ROOT,
    SUBWAY_LINES_PATH,
    SUBWAY_STATIONS_PATH,
    WORK_ADDRESS,
    WORK_LAT,
    WORK_LNG,
)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NYC Apartment Commute Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <link rel="stylesheet" href="https://unpkg.com/maplibre-gl@5.11.0/dist/maplibre-gl.css">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    @font-face {
      font-family: "IBM Plex Mono";
      src: url("fonts/IBMPlexMono-Regular.ttf") format("truetype");
      font-weight: 400;
      font-style: normal;
      font-display: swap;
    }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    #app { display: grid; grid-template-columns: 320px 1fr; height: 100vh; }
    #sidebar {
      background: #1a1a1a; color: #eee; overflow-y: auto;
      display: flex; flex-direction: column; border-right: 1px solid #333;
    }
    #sidebar header { padding: 16px; border-bottom: 1px solid #333; }
    #sidebar header h1 { font-size: 1.1rem; font-weight: 600; margin-bottom: 4px; }
    #sidebar header p { font-size: 0.8rem; color: #aaa; line-height: 1.4; }
    .section { padding: 16px; border-bottom: 1px solid #333; }
    .section h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #888; margin-bottom: 10px; }
    #sidebar button,
    #sidebar a,
    #sidebar label,
    #sidebar summary,
    #sidebar select,
    #sidebar input,
    #sidebar th[data-sort] {
      cursor: pointer;
    }
    #sidebar input:disabled,
    #sidebar .subway-toggle-nested:has(input:disabled) {
      cursor: default;
    }
    .band-toggle {
      display: flex; align-items: center; gap: 10px;
      min-height: 36px; margin-bottom: 2px; padding: 4px 0;
      font-size: 0.9rem; -webkit-tap-highlight-color: transparent;
    }
    .band-toggle input[type=checkbox] {
      width: 18px; height: 18px; flex-shrink: 0;
      accent-color: #c8c8c8;
    }
    .subway-toggle-nested { margin-left: 28px; }
    .subway-toggle-nested:has(input:disabled) { opacity: 0.45; cursor: default; }
    details.accordion.section { padding: 0; border-bottom: 1px solid #333; }
    details.accordion > summary {
      list-style: none; cursor: pointer; user-select: none;
      padding: 16px; font-size: 0.75rem; text-transform: uppercase;
      letter-spacing: 0.05em; color: #888;
    }
    details.accordion > summary::-webkit-details-marker { display: none; }
    details.accordion > summary::before {
      content: "▸"; display: inline-block; margin-right: 8px;
      transition: transform 0.15s ease;
    }
    details.accordion[open] > summary::before { transform: rotate(90deg); }
    details.accordion .accordion-body { padding: 0 16px 16px; }
    /* Whole subway system pulses together — no direction, no stagger. */
    .leaflet-subway-pane path.subway-line,
    .leaflet-subway-pane path.subway-station {
      animation: subway-pulse 2.15s ease-in-out infinite;
      /* Decorative only — never steal hover from station hit targets. */
      pointer-events: none !important;
    }
    .leaflet-subway-pane.subway-paused path.subway-line,
    .leaflet-subway-pane.subway-paused path.subway-station {
      animation: none;
      opacity: 0.9;
    }
    @keyframes subway-pulse {
      0%, 100% { opacity: 0.35; }
      50% { opacity: 1; }
    }
    /* Invisible hit targets for stations only (lines are non-interactive). */
    .leaflet-subway-pane path.subway-station-hit {
      fill: transparent !important;
      stroke: transparent !important;
      pointer-events: auto !important;
      cursor: pointer;
    }
    /* Tooltips must never capture the pointer or they leave sticky tips. */
    .leaflet-tooltip,
    .leaflet-tooltip.subway-station-tip {
      pointer-events: none !important;
    }
    /* Kill Leaflet/browser focus rings on paths (blue/white click borders). */
    .leaflet-container path.leaflet-interactive:focus,
    .leaflet-container .leaflet-interactive:focus {
      outline: none !important;
    }
    .subway-tip-routes {
      display: inline-flex; flex-wrap: wrap; gap: 4px 6px;
      margin-top: 4px; align-items: center;
    }
    .subway-tip-route {
      display: inline-flex; align-items: center; gap: 3px;
      font-weight: 600; font-size: 0.85em;
    }
    .subway-tip-dot {
      width: 8px; height: 8px; border-radius: 50%;
      flex-shrink: 0; box-shadow: 0 0 0 1px rgba(0,0,0,0.35);
    }
    .band-swatch {
      width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
    }
    .band-range {
      display: flex; gap: 10px; align-items: stretch;
      margin-bottom: 4px;
      --band-row-h: 20px;
      --band-thumb-h: 10px;
      --band-off: #3d3d3d;
      --unfilled: 0%;
    }
    .band-range-labels {
      flex: 1; display: flex; flex-direction: column; gap: 0;
    }
    .band-range-row {
      display: flex; align-items: center; gap: 8px;
      height: var(--band-row-h);
      font-size: 0.85rem; line-height: 1.2;
      transition: opacity 0.15s ease;
    }
    .band-range-row.is-off { opacity: 0.32; }
    .band-range-track {
      position: relative; width: 32px; flex-shrink: 0;
    }
    /* Full rail: muted track always visible; gradient only on the filled (lower) portion. */
    .band-range-fill {
      position: absolute;
      left: 50%; top: 0; bottom: 0;
      width: 10px;
      transform: translateX(-50%);
      border-radius: 5px;
      border: none;
      pointer-events: none;
      background-color: var(--band-off);
      background-image:
        linear-gradient(var(--band-off), var(--band-off)),
        var(--band-gradient);
      background-size: 100% var(--unfilled), 100% 100%;
      background-position: top, center;
      background-repeat: no-repeat, no-repeat;
    }
    .band-range-track input[type=range] {
      position: absolute;
      left: 50%;
      /* Inset so each thumb stop centers on a label/swatch row. */
      top: calc(var(--band-row-h) / 2 - var(--band-thumb-h) / 2);
      height: calc(100% - var(--band-row-h) + var(--band-thumb-h));
      bottom: auto;
      /* Body 2×H + tip H/2 (right angle); wider body, then re-centered. */
      width: calc(var(--band-thumb-h) * 2.5);
      margin: 0; padding: 0;
      transform: translateX(-50%);
      writing-mode: vertical-lr;
      direction: rtl;
      cursor: pointer;
      -webkit-appearance: none;
      appearance: none;
      background: transparent;
    }
    /* Native range inputs ignore most cursor CSS while pressed — force it on <html>. */
    html.band-slider-active,
    html.band-slider-active * {
      cursor: grabbing !important;
    }
    .band-range-track input[type=range]::-webkit-slider-runnable-track {
      width: calc(var(--band-thumb-h) * 2.5);
      height: 100%;
      background: transparent;
      border: none;
    }
    .band-range-track input[type=range]::-moz-range-track {
      width: calc(var(--band-thumb-h) * 2.5);
      height: 100%;
      background: transparent;
      border: none;
    }
    .band-range-track input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: calc(var(--band-thumb-h) * 2.5);
      height: var(--band-thumb-h);
      margin: 0;
      border: none;
      border-radius: 0;
      background-color: transparent;
      background-repeat: no-repeat;
      background-size: 100% 100%;
      /* Inset left edge + round left corners; tip still right-angled on the right. */
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 25 10'%3E%3Cpath fill='%23fff' d='M5 0H20L25 5L20 10H5Q3 10 3 8V2Q3 0 5 0Z'/%3E%3C/svg%3E");
      box-shadow: none;
      cursor: pointer;
    }
    .band-range-track input[type=range]::-moz-range-thumb {
      width: calc(var(--band-thumb-h) * 2.5);
      height: var(--band-thumb-h);
      border: none;
      border-radius: 0;
      background-color: transparent;
      background-repeat: no-repeat;
      background-size: 100% 100%;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 25 10'%3E%3Cpath fill='%23fff' d='M5 0H20L25 5L20 10H5Q3 10 3 8V2Q3 0 5 0Z'/%3E%3C/svg%3E");
      box-shadow: none;
      cursor: pointer;
    }
    .poi-swatch {
      width: 16px; height: 16px; flex-shrink: 0; display: inline-flex;
      align-items: center; justify-content: center;
    }
    .poi-swatch svg { width: 16px; height: 16px; display: block; }
    .poi-marker-icon { background: none !important; border: none !important; }
    .poi-marker-icon.dimmed { opacity: 0.3; }
    .commute-panel {
      display: flex; flex-direction: column; gap: 0;
    }
    .commute-bands { min-width: 0; }
    .active-cutoff { margin-top: 12px; min-width: 0; }
    .cutoff-help {
      margin-top: 8px; font-size: 0.75rem; color: #888; line-height: 1.4;
    }
    .active-cutoff select {
      width: 100%; padding: 8px; border-radius: 6px; border: 1px solid #444;
      background: #242424; color: #eee; font-size: 0.9rem;
    }
    .band-range-label .label-short { display: none; }
    .mobile-only { display: none; }
    #stats { font-size: 0.85rem; color: #aaa; line-height: 1.6; }
    #listings-accordion { flex: 1; min-height: 0; display: flex; flex-direction: column; border-bottom: none; }
    #listings-accordion[open] { min-height: 120px; }
    #listings-accordion .accordion-body {
      flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden;
    }
    #listings-table-wrap { flex: 1; overflow-y: auto; min-height: 0; margin-top: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    th {
      position: sticky; top: 0; background: #242424; padding: 8px 10px;
      text-align: left; cursor: pointer; user-select: none; white-space: nowrap;
    }
    th:hover { background: #333333; }
    td { padding: 8px 10px; border-bottom: 1px solid #2a2a4a; vertical-align: top; }
    tr:hover td { background: #242424; }
    tr.in-zone td { background: rgba(26, 152, 80, 0.12); }
    tr.out-zone td { opacity: 0.55; }
    tr.geocode-error td { opacity: 0.4; }
    .badge {
      display: inline-block; padding: 2px 6px; border-radius: 4px;
      font-size: 0.7rem; font-weight: 600;
    }
    .badge-in { background: #1a9850; color: #fff; }
    .badge-out { background: #555; color: #ccc; }
    .badge-err { background: #c0392b; color: #fff; }
    #map { height: 100%; background: #0d0d0d; }
    a { color: #c8c8c8; }
    #controls-pill {
      display: none;
      position: fixed; z-index: 1200;
      left: 50%; bottom: max(16px, env(safe-area-inset-bottom));
      transform: translateX(-50%);
      border: none; border-radius: 999px;
      min-height: 48px; min-width: 140px;
      padding: 14px 28px;
      background: #1a1a1a; color: #eee;
      font: 600 1rem/1 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      box-shadow: 0 8px 28px rgba(0,0,0,0.45);
      cursor: pointer;
      -webkit-tap-highlight-color: transparent;
      touch-action: manipulation;
    }
    #controls-pill:active { transform: translateX(-50%) scale(0.98); }
    #controls-scrim {
      display: none;
      position: fixed; inset: 0; z-index: 1050;
      background: rgba(0, 0, 0, 0.5);
      -webkit-tap-highlight-color: transparent;
    }
    .sheet-grabber {
      display: none;
      width: 44px; height: 5px; margin: 10px auto 2px;
      border-radius: 999px; background: #555; flex-shrink: 0;
    }
    .sidebar-close {
      display: none;
      margin-left: auto;
      border: 1px solid #444; border-radius: 10px;
      background: #242424; color: #eee;
      min-height: 44px; min-width: 72px;
      padding: 10px 16px; font-size: 0.95rem; font-weight: 600;
      cursor: pointer; touch-action: manipulation;
      -webkit-tap-highlight-color: transparent;
    }
    #sidebar header {
      display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px;
    }
    #sidebar header .header-text { flex: 1 1 200px; min-width: 0; }
    @media (max-width: 768px) {
      #app {
        grid-template-columns: 1fr;
        grid-template-rows: 1fr;
        height: 100dvh;
      }
      #map { min-height: 100dvh; }
      /* Keep zoom clear of the Controls pill. */
      .leaflet-bottom.leaflet-right {
        bottom: calc(72px + env(safe-area-inset-bottom, 0px));
      }
      .leaflet-control-zoom a {
        width: 44px !important; height: 44px !important;
        line-height: 44px !important; font-size: 22px !important;
      }
      #controls-scrim { display: none; }
      #app.controls-open #controls-scrim { display: block; }
      #sidebar {
        position: fixed; z-index: 1100;
        inset: auto 0 0 0;
        max-height: min(88dvh, 760px);
        padding-bottom: env(safe-area-inset-bottom, 0px);
        border-right: none;
        border-top: 1px solid #333;
        border-radius: 18px 18px 0 0;
        box-shadow: 0 -12px 40px rgba(0,0,0,0.45);
        transform: translateY(110%);
        transition: transform 0.25s ease;
        pointer-events: none;
        overscroll-behavior: contain;
        -webkit-overflow-scrolling: touch;
      }
      #app.controls-open #sidebar {
        transform: translateY(0);
        pointer-events: auto;
      }
      .sheet-grabber { display: block; }
      #controls-pill { display: inline-flex; align-items: center; justify-content: center; }
      #app.controls-open #controls-pill { display: none; }
      .sidebar-close { display: inline-flex; align-items: center; justify-content: center; }
      #sidebar header {
        position: sticky; top: 0; z-index: 2;
        background: #1a1a1a;
        padding: 8px 18px 14px;
        align-items: center; gap: 12px;
        border-bottom: 1px solid #333;
      }
      #sidebar header .header-text { flex: 1 1 auto; }
      #sidebar header h1 { font-size: 1.05rem; margin-bottom: 2px; }
      #sidebar header p { font-size: 0.85rem; }
      #sidebar header .overlay-link { display: none; }
      .section { padding: 14px 18px 18px; }
      .section h2 {
        font-size: 0.8rem; margin-bottom: 12px; letter-spacing: 0.06em;
      }
      details.accordion > summary {
        display: flex; align-items: center;
        min-height: 52px; padding: 16px 18px;
        font-size: 0.8rem;
      }
      details.accordion .accordion-body { padding: 0 18px 18px; }
      .band-toggle {
        min-height: 48px; padding: 12px 0; gap: 14px;
        font-size: 1rem; margin-bottom: 0;
      }
      .band-toggle + .band-toggle { border-top: 1px solid #2a2a2a; }
      .band-toggle input[type=checkbox] {
        width: 24px; height: 24px;
      }
      .subway-toggle-nested { margin-left: 38px; }
      /* Mobile-native commute cluster: keep vertical band metaphor, fill the gutter. */
      .commute-panel {
        display: grid;
        grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
        gap: 0 16px;
        align-items: stretch;
      }
      .commute-bands > .cutoff-help { display: none; }
      .band-range {
        --band-row-h: 34px;
        --band-thumb-h: 16px;
        gap: 10px;
        margin: 0;
      }
      .band-range-track { width: 40px; }
      .band-range-fill { width: 12px; border-radius: 6px; }
      .band-range-row {
        font-size: 0.9rem; gap: 8px;
      }
      .band-range-label .label-full { display: none; }
      .band-range-label .label-short { display: inline; }
      .band-swatch { width: 12px; height: 12px; }
      .poi-swatch, .poi-swatch svg { width: 20px; height: 20px; }
      .active-cutoff {
        margin-top: 0;
        padding: 0 0 0 16px;
        border-left: 1px solid #333;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 16px;
      }
      .cutoff-primary {
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .active-cutoff h2 {
        margin: 0;
        font-size: 0.8rem;
      }
      .active-cutoff select {
        min-height: 48px; padding: 12px 10px;
        font-size: 0.95rem; border-radius: 10px;
        touch-action: manipulation;
      }
      .cutoff-notes .cutoff-help {
        margin-top: 0;
        font-size: 0.8rem;
      }
      .cutoff-notes .cutoff-help + .cutoff-help { margin-top: 8px; }
      .mobile-only { display: block; }
      #stats { font-size: 0.95rem; line-height: 1.55; }
      #listings-table-wrap { max-height: 42vh; margin-top: 12px; }
      table { font-size: 0.9rem; }
      th, td { padding: 12px 10px; }
      th { font-size: 0.85rem; }
      .badge { padding: 4px 8px; font-size: 0.75rem; }
    }
    /* Narrow phones: keep the cluster, tighten the band column. */
    @media (max-width: 390px) {
      .commute-panel {
        grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
        gap: 0 12px;
      }
      .band-range {
        --band-row-h: 32px;
        --band-thumb-h: 15px;
        gap: 8px;
      }
      .band-range-track { width: 36px; }
      .active-cutoff { padding-left: 12px; }
      .active-cutoff select { font-size: 0.9rem; padding: 12px 8px; }
    }
  </style>
</head>
<body>
  <div id="app">
    <div id="controls-scrim" hidden></div>
    <aside id="sidebar" aria-labelledby="controls-title">
      <div class="sheet-grabber" aria-hidden="true"></div>
      <header>
        <div class="header-text">
          <h1 id="controls-title">Apartment Commute Map</h1>
          <p>Work: __WORK_ADDRESS__<br>Arrive by 8:30 AM · Public transit</p>
          <p class="overlay-link" style="margin-top:10px"><a href="overlay.html" target="_blank">Open overlay mode ↗</a></p>
        </div>
        <button type="button" class="sidebar-close" id="controls-close" aria-label="Close controls">Map</button>
      </header>
      <div class="section commute-section">
        <h2>Commute</h2>
        <div class="commute-panel">
          <div class="commute-bands">
            __BAND_TOGGLES__
          </div>
          <div class="active-cutoff">
            <div class="cutoff-primary">
              <h2>Max commute</h2>
              <select id="cutoff-select">
                __CUTOFF_OPTIONS__
              </select>
            </div>
            <div class="cutoff-notes">
              <p class="cutoff-help">Highlights zones within this time; fades farther bands on the map.</p>
              <p class="cutoff-help mobile-only">Drag the slider to peel off outer bands.</p>
            </div>
          </div>
        </div>
      </div>
      <div class="section layers-section">
        <h2>Layers</h2>
        __POI_TOGGLES__
        __SUBWAY_TOGGLE__
        <div id="stats" style="margin-top:12px"></div>
      </div>
      <details class="section accordion" id="listings-accordion">
        <summary>__LISTINGS_ACCORDION_LABEL__</summary>
        <div class="accordion-body">
          __LISTING_TOGGLE__
          <div id="listings-table-wrap">
            <table>
              <thead>
                <tr>
                  <th data-sort="address">Address</th>
                  <th data-sort="rent">Rent</th>
                  <th data-sort="beds">Beds</th>
                  <th data-sort="commute_min">Commute</th>
                </tr>
              </thead>
              <tbody id="listings-body"></tbody>
            </table>
          </div>
        </div>
      </details>
    </aside>
    <div id="map"></div>
    <button type="button" id="controls-pill" aria-expanded="false" aria-controls="sidebar">Controls</button>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/maplibre-gl@5.11.0/dist/maplibre-gl.js"></script>
  <script src="https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.3/leaflet-maplibre-gl.js"></script>
  <script>
    const ISOCHRONES = __ISOCHRONES_JSON__;
    const LISTINGS = __LISTINGS_JSON__;
    const POIS = __POIS_JSON__;
    const SUBWAY_LINES = __SUBWAY_LINES_JSON__;
    const SUBWAY_STATIONS = __SUBWAY_STATIONS_JSON__;
    const BAND_COLORS = __BAND_COLORS_JSON__;
    const WORK = { lat: __WORK_LAT__, lng: __WORK_LNG__ };

    let activeCutoff = __DEFAULT_CUTOFF__;
    let sortKey = "commute_min";
    let sortAsc = true;

    const appEl = document.getElementById("app");
    const controlsPill = document.getElementById("controls-pill");
    const controlsClose = document.getElementById("controls-close");
    const controlsScrim = document.getElementById("controls-scrim");
    const sidebarEl = document.getElementById("sidebar");

    function setControlsOpen(open) {
      const mobileSheet = window.matchMedia("(max-width: 768px)").matches;
      appEl.classList.toggle("controls-open", open);
      controlsPill.setAttribute("aria-expanded", open ? "true" : "false");
      controlsScrim.hidden = !open;
      document.body.style.overflow = open && mobileSheet ? "hidden" : "";
      if (mobileSheet) {
        sidebarEl.setAttribute("role", open ? "dialog" : "complementary");
        sidebarEl.setAttribute("aria-modal", open ? "true" : "false");
        const focusEl = open ? controlsClose : controlsPill;
        if (focusEl) focusEl.focus({ preventScroll: true });
      }
      if (window.map) setTimeout(() => map.invalidateSize(), 260);
    }
    controlsPill.addEventListener("click", () => setControlsOpen(true));
    controlsClose.addEventListener("click", () => setControlsOpen(false));
    controlsScrim.addEventListener("click", () => setControlsOpen(false));
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && appEl.classList.contains("controls-open")) {
        setControlsOpen(false);
      }
    });
    // Swipe sheet down from the grabber/header to dismiss on phones.
    (function enableSheetSwipeClose() {
      let startY = null;
      let dragging = false;
      const threshold = 72;
      function onStart(e) {
        if (!appEl.classList.contains("controls-open")) return;
        const t = e.target;
        if (!(t.closest("header") || t.closest(".sheet-grabber"))) return;
        if (t.closest("button, a, input, select, label, summary")) return;
        startY = e.touches ? e.touches[0].clientY : e.clientY;
        dragging = true;
      }
      function onMove(e) {
        if (!dragging || startY == null) return;
        const y = e.touches ? e.touches[0].clientY : e.clientY;
        const dy = Math.max(0, y - startY);
        sidebarEl.style.transition = "none";
        sidebarEl.style.transform = `translateY(${dy}px)`;
      }
      function onEnd(e) {
        if (!dragging || startY == null) return;
        const y = (e.changedTouches ? e.changedTouches[0].clientY : e.clientY);
        const dy = y - startY;
        dragging = false;
        startY = null;
        sidebarEl.style.transition = "";
        sidebarEl.style.transform = "";
        if (dy > threshold) setControlsOpen(false);
      }
      sidebarEl.addEventListener("touchstart", onStart, { passive: true });
      sidebarEl.addEventListener("touchmove", onMove, { passive: true });
      sidebarEl.addEventListener("touchend", onEnd);
      sidebarEl.addEventListener("touchcancel", onEnd);
    })();

    const map = L.map("map", { zoomControl: true }).setView([WORK.lat, WORK.lng], 12);
    window.map = map;

    // Basemap (no labels). Streets sit under zones; neighborhoods/places sit above.
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap &copy; CARTO &copy; OpenFreeMap",
      subdomains: "abcd",
      maxZoom: 20
    }).addTo(map);

    map.createPane("streetLabelsPane");
    map.getPane("streetLabelsPane").style.zIndex = 250;
    map.getPane("streetLabelsPane").style.pointerEvents = "none";
    map.createPane("isochronePane");
    map.getPane("isochronePane").style.zIndex = 350;
    map.createPane("contourPane");
    map.getPane("contourPane").style.zIndex = 360;
    map.createPane("subwayPane");
    map.getPane("subwayPane").style.zIndex = 370;
    map.getPane("subwayPane").classList.add("leaflet-subway-pane");
    map.createPane("labelsPane");
    map.getPane("labelsPane").style.zIndex = 450;
    map.getPane("labelsPane").style.pointerEvents = "none";

    function stripIcons(layout) {
      const next = { ...(layout || {}), "text-optional": true };
      delete next["icon-image"];
      delete next["icon-size"];
      delete next["icon-offset"];
      delete next["icon-anchor"];
      return next;
    }

    function addVectorLabelLayer(baseStyle, { pane, zIndex, keepLayer, paint, clearMaxZoom }) {
      const style = JSON.parse(JSON.stringify(baseStyle));
      delete style.sources.ne2_shaded;
      // Use the page's IBM Plex Mono via local TinySDF (no remote glyph atlas).
      delete style.glyphs;
      style.layers = (style.layers || [])
        .filter(l => l.type === "symbol" && keepLayer(l))
        .map(l => {
          const layout = {
            ...stripIcons(l.layout),
            "text-font": ["IBM Plex Mono"]
          };
          const layer = {
            ...l,
            layout,
            paint: { ...(typeof paint === "function" ? paint(l) : paint) }
          };
          if (clearMaxZoom) delete layer.maxzoom;
          // OpenMapTiles tags many NYC neighborhoods (Williamsburg, Bushwick, …) as
          // "quarter", not "neighbourhood" — include both.
          if (layer.id === "place_other") {
            const walk = (node) => {
              if (!Array.isArray(node)) return node;
              if (node[0] === "match" && node[1] && node[1][0] === "get" && node[1][1] === "class"
                  && Array.isArray(node[2])) {
                if (!node[2].includes("quarter")) node[2] = [...node[2], "quarter"];
                return node;
              }
              return node.map(walk);
            };
            layer.filter = walk(layer.filter);
          }
          return layer;
        });
      style.layers.unshift({
        id: "transparent-bg",
        type: "background",
        paint: { "background-color": "rgba(0,0,0,0)" }
      });
      const layer = L.maplibreGL({ style, interactive: false, pane }).addTo(map);
      const el = layer.getContainer && layer.getContainer();
      if (el) {
        el.style.pointerEvents = "none";
        el.style.zIndex = String(zIndex);
      }
      return layer;
    }

    const PLACE_PAINT = {
      "text-color": "#ffffff",
      "text-halo-color": "#000000",
      "text-halo-width": 1,
      "text-halo-blur": 0,
      "text-opacity": 1,
      "icon-opacity": 0
    };
    const STREET_PAINT = {
      "text-color": "rgba(220,220,220,0.9)",
      "text-halo-color": "rgba(0,0,0,0.85)",
      "text-halo-width": 1,
      "text-halo-blur": 0,
      "text-opacity": 1,
      "icon-opacity": 0
    };

    fetch("https://tiles.openfreemap.org/styles/dark")
      .then(r => r.json())
      .then(baseStyle => {
        // Streets / major roads under the isochrones.
        addVectorLabelLayer(baseStyle, {
          pane: "streetLabelsPane",
          zIndex: 250,
          keepLayer: l => String(l.id).startsWith("highway_name"),
          paint: STREET_PAINT,
          clearMaxZoom: false
        });
        // Neighborhoods, boroughs, cities above the isochrones (no maxzoom cutoff).
        addVectorLabelLayer(baseStyle, {
          pane: "labelsPane",
          zIndex: 450,
          keepLayer: l => String(l.id).startsWith("place_"),
          paint: PLACE_PAINT,
          clearMaxZoom: true
        });
      })
      .catch(() => {
        // Fallback: full Carto label stack under zones if vector tiles fail.
        L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png", {
          pane: "streetLabelsPane",
          subdomains: "abcd",
          maxZoom: 20,
          opacity: 0.85
        }).addTo(map);
      });

    L.marker([WORK.lat, WORK.lng], {
      title: "Work"
    }).addTo(map).bindPopup("<b>Work</b><br>__WORK_ADDRESS__");

    const bandLayers = {};
    const bandStyles = {};
    const bandMins = ISOCHRONES.features
      .map(f => f.properties.minutes)
      .filter(Boolean)
      .sort((a, b) => a - b);

    function contourColor(minutes) {
      for (const band of bandMins) {
        if (minutes <= band) return BAND_COLORS[band] || "#888";
      }
      return BAND_COLORS[bandMins[bandMins.length - 1]] || "#888";
    }

    // 10-min family edges are full weight; 5-min midpoints are half that.
    function ringStrokeWeight(minutes, inBudget) {
      const major = minutes % 10 === 0;
      if (inBudget) return major ? 2.5 : 1.25;
      return major ? 1 : 0.5;
    }

    ISOCHRONES.features.forEach(f => {
      const min = f.properties.minutes;
      if (!min) return;
      const fill = BAND_COLORS[min] || "#888";
      const layer = L.geoJSON(f, {
        pane: "isochronePane",
        interactive: false,
        style: {
          stroke: false,
          fillColor: fill,
          fillOpacity: 0.48
        }
      }).addTo(map);
      bandLayers[min] = layer;
      bandStyles[min] = fill;
    });

    const contourLayers = {};
    const CONTOURS = __CONTOURS_JSON__;
    CONTOURS.features.forEach(f => {
      const min = f.properties.minutes;
      if (!min) return;
      const stroke = BAND_COLORS[min] || "#888";
      const layer = L.geoJSON(f, {
        pane: "contourPane",
        interactive: false,
        style: {
          color: stroke,
          weight: ringStrokeWeight(min, min <= activeCutoff),
          fillOpacity: 0,
          opacity: 0.95,
          lineJoin: "round",
          lineCap: "round"
        }
      }).addTo(map);
      contourLayers[min] = layer;
    });

    const listingMarkers = [];
    const listingsLayer = L.layerGroup();
    LISTINGS.forEach(listing => {
      if (listing.lat == null) return;
      const marker = L.circleMarker([listing.lat, listing.lng], {
        radius: 6,
        fillColor: "#bbbbbb",
        color: "#fff",
        weight: 1.5,
        fillOpacity: 0.85
      });
      marker.listing = listing;
      marker.bindPopup(() => buildListingPopup(listing));
      listingMarkers.push(marker);
      listingsLayer.addLayer(marker);
    });

    function poiShapeSvg(shape, fill, size) {
      const s = size || 22;
      const stroke = "#111";
      const sw = 2.2;
      const common = `fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-linejoin="round"`;
      const shapes = {
        square: `<rect x="4" y="4" width="14" height="14" rx="1.5" ${common}/>`,
        triangle: `<polygon points="11,3 20,19 2,19" ${common}/>`,
        diamond: `<polygon points="11,2 20,11 11,20 2,11" ${common}/>`,
        star: `<polygon points="11,2 13.5,8.5 20.5,8.5 15,12.5 17,19 11,15.5 5,19 7,12.5 1.5,8.5 8.5,8.5" ${common}/>`,
        circle: `<circle cx="11" cy="11" r="8" ${common}/>`
      };
      const body = shapes[shape] || shapes.circle;
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 22" width="${s}" height="${s}">${body}</svg>`;
    }

    function poiIcon(poi, dimmed) {
      const fill = poi.color || "#fff";
      const shape = poi.shape || "circle";
      const size = 22;
      return L.divIcon({
        className: "poi-marker-icon" + (dimmed ? " dimmed" : ""),
        html: poiShapeSvg(shape, fill, size),
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        popupAnchor: [0, -size / 2]
      });
    }

    const poiMarkers = {};
    const poiLayer = L.layerGroup().addTo(map);
    POIS.forEach(poi => {
      if (poi.lat == null) return;
      const marker = L.marker([poi.lat, poi.lng], { icon: poiIcon(poi, false), zIndexOffset: 600 });
      marker.poi = poi;
      marker.bindTooltip(() => buildPoiTooltip(poi), { direction: "top", opacity: 0.9 });
      poiMarkers[poi.id] = marker;
      poiLayer.addLayer(marker);
    });

    const subwayLayer = L.layerGroup();
    const stationDots = [];
    const stationHits = [];
    // One shared tip — avoids leftover bound tooltips when SVG mouseout is flaky.
    const stationTip = L.tooltip({
      direction: "top",
      opacity: 0.95,
      className: "subway-station-tip",
      sticky: false,
      interactive: false,
      offset: [0, -8]
    });
    let stationTipOwner = null;

    function closeStationTip() {
      if (stationTipOwner) {
        map.closeTooltip(stationTip);
        stationTipOwner = null;
      }
    }

    // Screen-pixel radii grow gently with zoom so dots stay readable when zoomed in.
    function stationDotRadius(z) {
      return Math.max(3.5, Math.min(9, 3.5 + Math.max(0, z - 11) * 0.9));
    }
    function stationHitRadius(z) {
      return stationDotRadius(z) + 5;
    }
    function updateStationSizes() {
      const z = map.getZoom();
      const r = stationDotRadius(z);
      const hr = stationHitRadius(z);
      stationDots.forEach(m => m.setRadius(r));
      stationHits.forEach(m => m.setRadius(hr));
    }

    function stationTooltipHtml(name, routes, commute) {
      const title = `<div><strong>${name || "Station"}</strong></div>`;
      const commuteLine = commute
        ? `<div style="margin-top:2px;opacity:0.9">${commute}</div>`
        : "";
      if (!routes || !routes.length) return `${title}${commuteLine}`;
      const chips = routes.map(r => {
        const color = r.color || "#888";
        const label = r.name || "?";
        return `<span class="subway-tip-route"><span class="subway-tip-dot" style="background:${color}"></span>${label}</span>`;
      }).join("");
      return `${title}${commuteLine}<div class="subway-tip-routes">${chips}</div>`;
    }

    if (SUBWAY_LINES && SUBWAY_LINES.features && SUBWAY_LINES.features.length) {
      SUBWAY_LINES.features.forEach(f => {
        const color = (f.properties && f.properties.color) || "#888";
        // Visible route only — no hover/click hit target on the stroke.
        const layer = L.geoJSON(f, {
          pane: "subwayPane",
          interactive: false,
          style: {
            color,
            weight: 3,
            opacity: 0.9,
            lineCap: "round",
            lineJoin: "round",
            className: "subway-line"
          }
        });
        subwayLayer.addLayer(layer);
      });
    }
    if (SUBWAY_STATIONS && SUBWAY_STATIONS.features && SUBWAY_STATIONS.features.length) {
      const z0 = map.getZoom();
      const r0 = stationDotRadius(z0);
      const hr0 = stationHitRadius(z0);
      SUBWAY_STATIONS.features.forEach(f => {
        const coords = f.geometry && f.geometry.coordinates;
        if (!coords) return;
        const minutes = f.properties && f.properties.minutes;
        const fill = (minutes != null && BAND_COLORS[minutes]) || "#555";
        const label = (f.properties && f.properties.name) || "Station";
        const routes = (f.properties && f.properties.routes) || [];
        const latlng = [coords[1], coords[0]];
        const commute = minutes != null ? `≤ ${minutes} min to work` : "Outside mapped bands";
        const tipHtml = stationTooltipHtml(label, routes, commute);

        // Visible decorative dot first (pointer-events: none via CSS).
        const marker = L.circleMarker(latlng, {
          pane: "subwayPane",
          radius: r0,
          fillColor: fill,
          fillOpacity: 0.95,
          stroke: false,
          interactive: false,
          className: "subway-station"
        });
        subwayLayer.addLayer(marker);
        stationDots.push(marker);

        // Hit target on top — owns hover open/close explicitly.
        const hit = L.circleMarker(latlng, {
          pane: "subwayPane",
          radius: hr0,
          stroke: false,
          fillColor: "#000",
          fillOpacity: 0.01,
          className: "subway-station-hit",
          bubblingMouseEvents: false
        });
        hit.on("mouseover", () => {
          stationTipOwner = hit;
          stationTip.setContent(tipHtml);
          stationTip.setLatLng(latlng);
          map.openTooltip(stationTip);
        });
        hit.on("mouseout", () => {
          if (stationTipOwner === hit) closeStationTip();
        });
        // Hover only — swallow clicks so focus rings / map-drag fights don't appear.
        hit.on("click", e => L.DomEvent.stop(e));
        subwayLayer.addLayer(hit);
        stationHits.push(hit);
      });
      map.on("zoomend", updateStationSizes);
      // Safety nets: stuck tips if SVG mouseout is skipped while leaving the map.
      map.getContainer().addEventListener("mouseleave", closeStationTip);
      map.on("movestart zoomstart", closeStationTip);
    }

    function setSubwayVisible(on) {
      if (on) map.addLayer(subwayLayer);
      else {
        closeStationTip();
        map.removeLayer(subwayLayer);
      }
    }
    function setSubwayAnimating(on) {
      const pane = map.getPane("subwayPane");
      if (!pane) return;
      pane.classList.toggle("subway-paused", !on);
    }
    const showSubway = document.getElementById("show-subway");
    const animSubway = document.getElementById("animate-subway");
    function syncSubwayControls() {
      const on = !!(showSubway && showSubway.checked);
      setSubwayVisible(on);
      if (animSubway) {
        animSubway.disabled = !on;
        if (!on) animSubway.checked = false;
        setSubwayAnimating(on && animSubway.checked);
      } else {
        setSubwayAnimating(false);
      }
    }
    if (showSubway) {
      showSubway.addEventListener("change", () => {
        // Turning subway on also turns pulse on; turning off clears pulse.
        // While subway is on, pulse can still be toggled independently.
        if (showSubway.checked && animSubway) animSubway.checked = true;
        syncSubwayControls();
      });
      syncSubwayControls();
    }
    if (animSubway) {
      animSubway.addEventListener("change", () => {
        setSubwayAnimating(!!(showSubway && showSubway.checked && animSubway.checked));
      });
    }

    function buildPoiTooltip(poi) {
      const commute = poi.commute_min != null ? `≤ ${poi.commute_min} min to work` : "Outside isochrone bands";
      const addr = poi.address ? `<br>${poi.address}` : "";
      return `<b>${poi.label || "POI"}</b>${addr}<br>${commute}`;
    }

    function buildListingPopup(l) {
      const commute = l.commute_min != null ? `≤ ${l.commute_min} min` : "Out of zone";
      const link = l.url ? `<br><a href="${l.url}" target="_blank">View listing</a>` : "";
      const notes = l.notes ? `<br><em>${l.notes}</em>` : "";
      return `<b>${l.address}</b><br>${l.rent || "—"} · ${l.beds || "—"} bed<br>Commute: ${commute}${link}${notes}`;
    }

    function updateBandStyles() {
      Object.entries(bandLayers).forEach(([min, layer]) => {
        const minutes = parseInt(min, 10);
        const fill = bandStyles[minutes] || "#888";
        const inBudget = minutes <= activeCutoff;
        layer.setStyle({
          stroke: false,
          fillColor: fill,
          fillOpacity: inBudget ? 0.48 : 0.06
        });
      });
      Object.entries(contourLayers).forEach(([min, layer]) => {
        const minutes = parseInt(min, 10);
        const stroke = BAND_COLORS[minutes] || "#888";
        const inBudget = minutes <= activeCutoff;
        layer.setStyle({
          color: stroke,
          weight: ringStrokeWeight(minutes, inBudget),
          fillOpacity: 0,
          opacity: inBudget ? 0.95 : 0.2
        });
      });
    }

    function updateListingStyles() {
      listingMarkers.forEach(m => {
        const l = m.listing;
        const inBudget = l.commute_min != null && l.commute_min <= activeCutoff;
        m.setStyle({
          fillColor: inBudget ? "#ffffff" : "#888888",
          fillOpacity: inBudget ? 1 : 0.35,
          opacity: inBudget ? 1 : 0.5,
          radius: inBudget ? 7 : 5
        });
      });
    }

    function updatePoiStyles() {
      Object.values(poiMarkers).forEach(m => {
        const poi = m.poi;
        const inBudget = poi.commute_min != null && poi.commute_min <= activeCutoff;
        m.setIcon(poiIcon(poi, !inBudget));
      });
    }

    function updateMarkerStyles() {
      updateBandStyles();
      updatePoiStyles();
      updateListingStyles();
    }

    function renderTable() {
      const tbody = document.getElementById("listings-body");
      const sorted = [...LISTINGS].sort((a, b) => {
        let av = a[sortKey], bv = b[sortKey];
        if (sortKey === "commute_min") {
          av = av ?? 9999; bv = bv ?? 9999;
        } else if (sortKey === "rent" || sortKey === "beds") {
          av = parseFloat(String(av).replace(/[^0-9.]/g, "")) || 9999;
          bv = parseFloat(String(bv).replace(/[^0-9.]/g, "")) || 9999;
        } else {
          av = String(av || "").toLowerCase();
          bv = String(bv || "").toLowerCase();
        }
        if (av < bv) return sortAsc ? -1 : 1;
        if (av > bv) return sortAsc ? 1 : -1;
        return 0;
      });

      tbody.innerHTML = sorted.map(l => {
        const rowClass = l.geocode_error ? "geocode-error" :
          (l.commute_min != null && l.commute_min <= activeCutoff ? "in-zone" : "out-zone");
        let badge;
        if (l.geocode_error) badge = '<span class="badge badge-err">No geo</span>';
        else if (l.commute_min == null) badge = '<span class="badge badge-out">Out</span>';
        else if (l.commute_min <= activeCutoff) badge = `<span class="badge badge-in">≤${l.commute_min}m</span>`;
        else badge = `<span class="badge badge-out">${l.commute_min}m</span>`;

        const link = l.url ? `<a href="${l.url}" target="_blank">${l.address}</a>` : l.address;
        return `<tr class="${rowClass}" data-lat="${l.lat}" data-lng="${l.lng}">
          <td>${link}</td>
          <td>${l.rent || "—"}</td>
          <td>${l.beds || "—"}</td>
          <td>${badge}</td>
        </tr>`;
      }).join("");

      const inZone = LISTINGS.filter(l => l.commute_min != null && l.commute_min <= activeCutoff).length;
      const poiLines = POIS.map(poi => {
        if (poi.geocode_error) return `${poi.label}: <span style="color:#888">geocode failed</span>`;
        const commute = poi.commute_min != null ? `≤${poi.commute_min} min` : "outside bands";
        const highlight = poi.commute_min != null && poi.commute_min <= activeCutoff;
        const icon = poiShapeSvg(poi.shape || "circle", poi.color || "#fff", 12);
        return `<span style="display:inline-flex;align-items:center;gap:6px">${icon}<strong>${poi.label}</strong></span>: ${commute}` +
          (highlight ? " ✓" : ` <span style="color:#666">(outside ≤${activeCutoff} min budget)</span>`);
      }).join("<br>");

      let stats = poiLines;
      if (LISTINGS.length) {
        stats += `<br><br><strong>${inZone}</strong> of <strong>${LISTINGS.length}</strong> listings within ≤${activeCutoff} min`;
      }
      stats += `<br><span style="color:#666">Click table rows to pan · toggle layers above</span>`;
      document.getElementById("stats").innerHTML = stats;
    }

    document.querySelectorAll(".listing-toggle input").forEach(cb => {
      const syncListings = () => {
        if (cb.checked) map.addLayer(listingsLayer);
        else map.removeLayer(listingsLayer);
      };
      syncListings();
      cb.addEventListener("change", syncListings);
    });

    document.querySelectorAll(".poi-toggle input").forEach(cb => {
      cb.addEventListener("change", () => {
        const marker = poiMarkers[cb.dataset.poiId];
        if (!marker) return;
        if (cb.checked) poiLayer.addLayer(marker);
        else poiLayer.removeLayer(marker);
      });
    });

    const bandRange = document.getElementById("band-range");
    function setBandRangeHidden(hiddenCount) {
      const visibleThrough = bandMins.length - 1 - hiddenCount;
      bandMins.forEach((min, idx) => {
        const show = idx <= visibleThrough;
        const layer = bandLayers[min];
        const stroke = contourLayers[min];
        if (show) {
          if (layer) map.addLayer(layer);
          if (stroke) map.addLayer(stroke);
        } else {
          if (layer) map.removeLayer(layer);
          if (stroke) map.removeLayer(stroke);
        }
        const row = document.querySelector(`#band-range-control .band-range-row[data-minutes="${min}"]`);
        if (row) row.classList.toggle("is-off", !show);
      });
    }
    function bandRangeHiddenFromValue() {
      // Vertical rtl range: max sits at the top (filled). Map that to "all bands on".
      const maxHidden = parseInt(bandRange.max, 10);
      return maxHidden - parseInt(bandRange.value, 10);
    }
    function syncBandRangeFill() {
      if (!bandRange) return;
      const root = document.getElementById("band-range-control");
      const track = bandRange.closest(".band-range-track");
      const rows = root ? root.querySelectorAll(".band-range-row") : [];
      if (!root || !track || !rows.length) return;
      const maxHidden = parseInt(bandRange.max, 10) || 0;
      const value = parseInt(bandRange.value, 10);
      // Top stop: fill the entire rail (no muted gap above the knob).
      if (value >= maxHidden) {
        root.style.setProperty("--unfilled", "0%");
        return;
      }
      const i = Math.max(0, Math.min(rows.length - 1, maxHidden - value));
      const trackRect = track.getBoundingClientRect();
      const rowRect = rows[i].getBoundingClientRect();
      const thumbH = parseFloat(getComputedStyle(root).getPropertyValue("--band-thumb-h")) || 10;
      const rowCenter = rowRect.top + rowRect.height / 2 - trackRect.top;
      const thumbTop = rowCenter - thumbH / 2;
      const unfilled = Math.max(0, Math.min(100, (thumbTop / trackRect.height) * 100));
      root.style.setProperty("--unfilled", `${unfilled}%`);
    }
    if (bandRange) {
      bandRange.addEventListener("input", () => {
        setBandRangeHidden(bandRangeHiddenFromValue());
        syncBandRangeFill();
      });
      function setBandSliderActive(on) {
        document.documentElement.classList.toggle("band-slider-active", on);
      }
      function endBandSliderActive() {
        setBandSliderActive(false);
        window.removeEventListener("pointerup", endBandSliderActive, true);
        window.removeEventListener("mouseup", endBandSliderActive, true);
        window.removeEventListener("pointercancel", endBandSliderActive, true);
        window.removeEventListener("blur", endBandSliderActive, true);
      }
      // Apply fist immediately on press (browsers won't honor cursor on <input type=range>).
      bandRange.addEventListener("pointerdown", e => {
        if (e.button != null && e.button !== 0) return;
        setBandSliderActive(true);
        window.addEventListener("pointerup", endBandSliderActive, true);
        window.addEventListener("mouseup", endBandSliderActive, true);
        window.addEventListener("pointercancel", endBandSliderActive, true);
        window.addEventListener("blur", endBandSliderActive, true);
      });
      syncBandRangeFill();
    }

    document.getElementById("cutoff-select").addEventListener("change", e => {
      activeCutoff = parseInt(e.target.value);
      updateMarkerStyles();
      renderTable();
    });

    document.querySelectorAll("th[data-sort]").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (sortKey === key) sortAsc = !sortAsc;
        else { sortKey = key; sortAsc = true; }
        renderTable();
      });
    });

    document.getElementById("listings-body").addEventListener("click", e => {
      const row = e.target.closest("tr");
      if (!row || !row.dataset.lat) return;
      map.setView([parseFloat(row.dataset.lat), parseFloat(row.dataset.lng)], 15);
    });

    updateMarkerStyles();
    renderTable();

    const allLayers = Object.values(bandLayers);
    if (allLayers.length) {
      const group = L.featureGroup(allLayers);
      map.fitBounds(group.getBounds().pad(0.05));
    }
  </script>
</body>
</html>
"""


OVERLAY_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Commute Overlay</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      height: 100%;
      background: transparent !important;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    #map {
      position: fixed;
      inset: 0;
      background: transparent !important;
    }
    .leaflet-container { background: transparent !important; }
    .leaflet-control-zoom { border: none !important; box-shadow: 0 2px 8px rgba(0,0,0,0.35) !important; }
    #controls {
      position: fixed;
      top: 12px;
      left: 12px;
      z-index: 1000;
      max-width: 280px;
      padding: 12px 14px;
      border-radius: 10px;
      background: rgba(20, 20, 20, 0.82);
      color: #eee;
      font-size: 0.8rem;
      backdrop-filter: blur(8px);
      box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }
    #controls.hidden { display: none; }
    #controls h1 { font-size: 0.95rem; font-weight: 600; margin-bottom: 4px; }
    #controls .hint { color: #aaa; font-size: 0.72rem; line-height: 1.35; margin-bottom: 10px; }
    #controls label.row {
      display: flex; align-items: center; gap: 8px;
      margin-bottom: 6px; cursor: pointer;
    }
    #controls button,
    #controls a,
    #controls label,
    #controls select,
    #controls input {
      cursor: pointer;
    }
    #controls input:disabled {
      cursor: default;
    }
    #controls .swatch {
      width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0;
      border: 1px solid rgba(255,255,255,0.5);
    }
    #controls select, #controls input[type=range] { width: 100%; }
    #controls select {
      padding: 6px 8px; border-radius: 6px; border: 1px solid #444;
      background: #242424; color: #eee; font-size: 0.8rem;
    }
    .ctrl-block { margin-top: 10px; }
    .ctrl-block label.title {
      display: block; font-size: 0.68rem; text-transform: uppercase;
      letter-spacing: 0.05em; color: #888; margin-bottom: 4px;
    }
    #opacity-val { color: #aaa; font-size: 0.72rem; }
    #controls a { color: #c8c8c8; font-size: 0.75rem; }
    .band-swatch {
      width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
    }
    .band-range {
      display: flex; gap: 8px; align-items: stretch;
      --band-row-h: 18px;
      --band-thumb-h: 9px;
      --band-off: #3d3d3d;
      --unfilled: 0%;
    }
    .band-range-labels {
      flex: 1; display: flex; flex-direction: column; gap: 0;
    }
    .band-range-row {
      display: flex; align-items: center; gap: 6px;
      height: var(--band-row-h);
      font-size: 0.72rem; line-height: 1.2;
      transition: opacity 0.15s ease;
    }
    .band-range-label .label-short { display: none; }
    .band-range-row.is-off { opacity: 0.32; }
    .band-range-track {
      position: relative; width: 28px; flex-shrink: 0;
    }
    .band-range-fill {
      position: absolute;
      left: 50%; top: 0; bottom: 0;
      width: 8px;
      transform: translateX(-50%);
      border-radius: 4px;
      border: none;
      pointer-events: none;
      background-color: var(--band-off);
      background-image:
        linear-gradient(var(--band-off), var(--band-off)),
        var(--band-gradient);
      background-size: 100% var(--unfilled), 100% 100%;
      background-position: top, center;
      background-repeat: no-repeat, no-repeat;
    }
    .band-range-track input[type=range] {
      position: absolute;
      left: 50%;
      top: calc(var(--band-row-h) / 2 - var(--band-thumb-h) / 2);
      height: calc(100% - var(--band-row-h) + var(--band-thumb-h));
      bottom: auto;
      width: calc(var(--band-thumb-h) * 2.5) !important;
      margin: 0; padding: 0;
      transform: translateX(-50%);
      writing-mode: vertical-lr;
      direction: rtl;
      cursor: pointer;
      -webkit-appearance: none;
      appearance: none;
      background: transparent;
    }
    /* Native range inputs ignore most cursor CSS while pressed — force it on <html>. */
    html.band-slider-active,
    html.band-slider-active * {
      cursor: grabbing !important;
    }
    .band-range-track input[type=range]::-webkit-slider-runnable-track {
      width: calc(var(--band-thumb-h) * 2.5);
      height: 100%;
      background: transparent;
      border: none;
    }
    .band-range-track input[type=range]::-moz-range-track {
      width: calc(var(--band-thumb-h) * 2.5);
      height: 100%;
      background: transparent;
      border: none;
    }
    .band-range-track input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: calc(var(--band-thumb-h) * 2.5);
      height: var(--band-thumb-h);
      margin: 0;
      border: none;
      border-radius: 0;
      background-color: transparent;
      background-repeat: no-repeat;
      background-size: 100% 100%;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 25 10'%3E%3Cpath fill='%23fff' d='M5 0H20L25 5L20 10H5Q3 10 3 8V2Q3 0 5 0Z'/%3E%3C/svg%3E");
      box-shadow: none;
      cursor: pointer;
    }
    .band-range-track input[type=range]::-moz-range-thumb {
      width: calc(var(--band-thumb-h) * 2.5);
      height: var(--band-thumb-h);
      border: none;
      border-radius: 0;
      background-color: transparent;
      background-repeat: no-repeat;
      background-size: 100% 100%;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 25 10'%3E%3Cpath fill='%23fff' d='M5 0H20L25 5L20 10H5Q3 10 3 8V2Q3 0 5 0Z'/%3E%3C/svg%3E");
      box-shadow: none;
      cursor: pointer;
    }
    #hide-hint {
      position: fixed; bottom: 10px; right: 12px; z-index: 1000;
      font-size: 0.7rem; color: rgba(255,255,255,0.45);
      text-shadow: 0 1px 2px rgba(0,0,0,0.8);
      pointer-events: none;
    }
  </style>
</head>
<body>
  <div id="controls">
    <h1>Commute overlay</h1>
    <p class="hint">Isochrones only — no basemap. Zoom/pan to match Zillow, then float this window on top. Press <kbd>H</kbd> to hide controls.</p>
    <div class="ctrl-block">
      <label class="title">Band opacity</label>
      <input type="range" id="opacity-slider" min="10" max="90" value="__OVERLAY_OPACITY_PCT__">
      <span id="opacity-val">__OVERLAY_OPACITY_PCT__%</span>
    </div>
    <div class="ctrl-block">
      <label class="title">Max commute</label>
      <select id="cutoff-select">
        __CUTOFF_OPTIONS__
      </select>
    </div>
    <div class="ctrl-block">
      <label class="title">Bands</label>
      __BAND_TOGGLES__
    </div>
    <div class="ctrl-block">
      <label class="row"><input type="checkbox" id="show-work" checked> Show work pin</label>
    </div>
    <p style="margin-top:10px"><a href="index.html">← Full map</a></p>
  </div>
  <div id="hide-hint">H — toggle controls</div>
  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const ISOCHRONES = __ISOCHRONES_JSON__;
    const BAND_COLORS = __BAND_COLORS_JSON__;
    const WORK = { lat: __WORK_LAT__, lng: __WORK_LNG__ };

    let activeCutoff = __DEFAULT_CUTOFF__;
    let bandOpacity = __OVERLAY_OPACITY__;

    const map = L.map("map", {
      zoomControl: true,
      attributionControl: false
    }).setView([WORK.lat, WORK.lng], 12);

    const bandLayers = {};
    const bandStyles = {};
    const bandMins = ISOCHRONES.features
      .map(f => f.properties.minutes)
      .filter(Boolean)
      .sort((a, b) => a - b);

    function contourColor(minutes) {
      for (const band of bandMins) {
        if (minutes <= band) return BAND_COLORS[band] || "#888";
      }
      return BAND_COLORS[bandMins[bandMins.length - 1]] || "#888";
    }

    function ringStrokeWeight(minutes, inBudget) {
      const major = minutes % 10 === 0;
      if (inBudget) return major ? 2.5 : 1.25;
      return major ? 1 : 0.5;
    }

    ISOCHRONES.features.forEach(f => {
      const min = f.properties.minutes;
      if (!min) return;
      const fill = BAND_COLORS[min] || "#888";
      const layer = L.geoJSON(f, {
        interactive: false,
        style: {
          stroke: false,
          fillColor: fill,
          fillOpacity: bandOpacity
        }
      }).addTo(map);
      bandLayers[min] = layer;
      bandStyles[min] = fill;
    });

    const contourLayers = {};
    const CONTOURS = __CONTOURS_JSON__;
    CONTOURS.features.forEach(f => {
      const min = f.properties.minutes;
      if (!min) return;
      const stroke = BAND_COLORS[min] || "#888";
      const layer = L.geoJSON(f, {
        interactive: false,
        style: {
          color: stroke,
          weight: ringStrokeWeight(min, min <= activeCutoff),
          fillOpacity: 0,
          opacity: 0.95,
          lineJoin: "round",
          lineCap: "round"
        }
      }).addTo(map);
      contourLayers[min] = layer;
    });

    const workMarker = L.circleMarker([WORK.lat, WORK.lng], {
      radius: 5,
      fillColor: "#ffffff",
      color: "#000",
      weight: 1.5,
      fillOpacity: 0.9
    }).addTo(map);

    function styleBands() {
      Object.entries(bandLayers).forEach(([min, layer]) => {
        const minutes = parseInt(min, 10);
        const fill = bandStyles[minutes] || "#888";
        const inBudget = minutes <= activeCutoff;
        layer.setStyle({
          stroke: false,
          fillColor: fill,
          fillOpacity: inBudget ? bandOpacity : bandOpacity * 0.15
        });
      });
      Object.entries(contourLayers).forEach(([min, layer]) => {
        const minutes = parseInt(min, 10);
        const stroke = BAND_COLORS[minutes] || "#888";
        const inBudget = minutes <= activeCutoff;
        layer.setStyle({
          color: stroke,
          weight: ringStrokeWeight(minutes, inBudget),
          fillOpacity: 0,
          opacity: inBudget ? 0.95 : 0.2
        });
      });
    }

    document.getElementById("opacity-slider").addEventListener("input", e => {
      bandOpacity = parseInt(e.target.value, 10) / 100;
      document.getElementById("opacity-val").textContent = e.target.value + "%";
      styleBands();
    });

    document.getElementById("cutoff-select").addEventListener("change", e => {
      activeCutoff = parseInt(e.target.value, 10);
      styleBands();
    });

    const bandRange = document.getElementById("band-range");
    function setBandRangeHidden(hiddenCount) {
      const visibleThrough = bandMins.length - 1 - hiddenCount;
      bandMins.forEach((min, idx) => {
        const show = idx <= visibleThrough;
        const layer = bandLayers[min];
        const stroke = contourLayers[min];
        if (show) {
          if (layer) map.addLayer(layer);
          if (stroke) map.addLayer(stroke);
        } else {
          if (layer) map.removeLayer(layer);
          if (stroke) map.removeLayer(stroke);
        }
        const row = document.querySelector(`#band-range-control .band-range-row[data-minutes="${min}"]`);
        if (row) row.classList.toggle("is-off", !show);
      });
    }
    function bandRangeHiddenFromValue() {
      // Vertical rtl range: max sits at the top (filled). Map that to "all bands on".
      const maxHidden = parseInt(bandRange.max, 10);
      return maxHidden - parseInt(bandRange.value, 10);
    }
    function syncBandRangeFill() {
      if (!bandRange) return;
      const root = document.getElementById("band-range-control");
      const track = bandRange.closest(".band-range-track");
      const rows = root ? root.querySelectorAll(".band-range-row") : [];
      if (!root || !track || !rows.length) return;
      const maxHidden = parseInt(bandRange.max, 10) || 0;
      const value = parseInt(bandRange.value, 10);
      // Top stop: fill the entire rail (no muted gap above the knob).
      if (value >= maxHidden) {
        root.style.setProperty("--unfilled", "0%");
        return;
      }
      const i = Math.max(0, Math.min(rows.length - 1, maxHidden - value));
      const trackRect = track.getBoundingClientRect();
      const rowRect = rows[i].getBoundingClientRect();
      const thumbH = parseFloat(getComputedStyle(root).getPropertyValue("--band-thumb-h")) || 10;
      const rowCenter = rowRect.top + rowRect.height / 2 - trackRect.top;
      const thumbTop = rowCenter - thumbH / 2;
      const unfilled = Math.max(0, Math.min(100, (thumbTop / trackRect.height) * 100));
      root.style.setProperty("--unfilled", `${unfilled}%`);
    }
    if (bandRange) {
      bandRange.addEventListener("input", () => {
        setBandRangeHidden(bandRangeHiddenFromValue());
        syncBandRangeFill();
      });
      function setBandSliderActive(on) {
        document.documentElement.classList.toggle("band-slider-active", on);
      }
      function endBandSliderActive() {
        setBandSliderActive(false);
        window.removeEventListener("pointerup", endBandSliderActive, true);
        window.removeEventListener("mouseup", endBandSliderActive, true);
        window.removeEventListener("pointercancel", endBandSliderActive, true);
        window.removeEventListener("blur", endBandSliderActive, true);
      }
      bandRange.addEventListener("pointerdown", e => {
        if (e.button != null && e.button !== 0) return;
        setBandSliderActive(true);
        window.addEventListener("pointerup", endBandSliderActive, true);
        window.addEventListener("mouseup", endBandSliderActive, true);
        window.addEventListener("pointercancel", endBandSliderActive, true);
        window.addEventListener("blur", endBandSliderActive, true);
      });
      syncBandRangeFill();
    }

    document.getElementById("show-work").addEventListener("change", e => {
      if (e.target.checked) workMarker.addTo(map);
      else map.removeLayer(workMarker);
    });

    document.addEventListener("keydown", e => {
      if (e.key === "h" || e.key === "H") {
        document.getElementById("controls").classList.toggle("hidden");
        document.getElementById("hide-hint").classList.toggle("hidden");
      }
    });

    styleBands();
    const allLayers = Object.values(bandLayers);
    if (allLayers.length) {
      map.fitBounds(L.featureGroup(allLayers).getBounds().pad(0.05));
    }
  </script>
</body>
</html>
"""


def band_ring_label(minutes: int, prev_min: int | None) -> str:
    if prev_min is None:
        return f"≤ {minutes} min"
    return f"{prev_min}–{minutes} min"


def band_ring_label_short(minutes: int, prev_min: int | None) -> str:
    """Compact label for narrow mobile layouts beside the vertical slider."""
    if prev_min is None:
        return f"≤{minutes}"
    return f"{prev_min}–{minutes}"


def _feature_minutes(feature: dict) -> int | None:
    props = feature.get("properties") or {}
    if props.get("minutes") is not None:
        return int(props["minutes"])
    search_id = str(props.get("search_id") or "")
    # e.g. "30_min", "15_min_contour"
    for part in search_id.replace("-", "_").split("_"):
        if part.isdigit():
            return int(part)
    return None


def merge_isochrone_layers(*collections: dict) -> dict:
    """Merge nested isochrone FeatureCollections keyed by minutes (later wins)."""
    by_min: dict[int, dict] = {}
    for collection in collections:
        if not collection:
            continue
        for feature in collection.get("features", []):
            minutes = _feature_minutes(feature)
            if minutes is None:
                continue
            props = dict(feature.get("properties") or {})
            props["minutes"] = minutes
            by_min[minutes] = {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": props,
            }
    return {
        "type": "FeatureCollection",
        "features": [by_min[m] for m in sorted(by_min)],
    }


def isochrones_to_rings(isochrones: dict) -> dict:
    """Turn nested isochrones into non-overlapping ring polygons so colors don't stack."""
    by_min: dict[int, object] = {}
    for feature in isochrones.get("features", []):
        minutes = feature.get("properties", {}).get("minutes")
        if minutes is None:
            continue
        geom = shape(feature["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        by_min[int(minutes)] = geom

    rings = []
    prev_geom = None
    prev_min = None
    for minutes in sorted(by_min):
        geom = by_min[minutes]
        ring_geom = geom if prev_geom is None else geom.difference(prev_geom)
        if ring_geom.is_empty:
            prev_geom = geom
            prev_min = minutes
            continue
        props = {"minutes": minutes, "ring_label": band_ring_label(minutes, prev_min)}
        rings.append(
            {
                "type": "Feature",
                "geometry": mapping(ring_geom),
                "properties": props,
            }
        )
        prev_geom = geom
        prev_min = minutes

    return {"type": "FeatureCollection", "features": rings}


def isochrones_to_boundaries(isochrones: dict) -> dict:
    """One outline per commute threshold (avoids double-stroking shared ring edges)."""
    features = []
    for feature in isochrones.get("features", []):
        minutes = feature.get("properties", {}).get("minutes")
        if minutes is None:
            continue
        geom = shape(feature["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        boundary = geom.boundary
        if boundary.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(boundary),
                "properties": {
                    "minutes": int(minutes),
                    "kind": "boundary",
                    "major": int(minutes) % 10 == 0,
                },
            }
        )
    features.sort(key=lambda f: f["properties"]["minutes"])
    return {"type": "FeatureCollection", "features": features}


def build_band_toggles(saved_mins: list[int]) -> str:
    if not saved_mins:
        return '<p class="cutoff-help">No isochrone bands loaded.</p>'
    labels_by_min: dict[int, tuple[str, str]] = {}
    prev_min = None
    for minutes in saved_mins:
        labels_by_min[minutes] = (
            band_ring_label(minutes, prev_min),
            band_ring_label_short(minutes, prev_min),
        )
        prev_min = minutes
    max_hidden = max(0, len(saved_mins) - 1)
    rows = []
    top_down = list(reversed(saved_mins))
    for minutes in top_down:
        color = BAND_COLORS.get(minutes, "#888")
        label_full, label_short = labels_by_min[minutes]
        rows.append(
            f'<div class="band-range-row" data-minutes="{minutes}">'
            f'<span class="band-swatch" style="background:{color}"></span>'
            f'<span class="band-range-label">'
            f'<span class="label-full">{label_full}</span>'
            f'<span class="label-short">{label_short}</span>'
            f"</span>"
            f"</div>"
        )
    rows_html = "\n          ".join(rows)
    colors = [BAND_COLORS.get(m, "#888") for m in top_down]
    if len(colors) == 1:
        gradient = colors[0]
    else:
        stops = []
        last = len(colors) - 1
        for i, color in enumerate(colors):
            pct = (i / last) * 100
            stops.append(f"{color} {pct:.2f}%")
        gradient = f"linear-gradient(to bottom, {', '.join(stops)})"
    return (
        f"<style>#band-range-control{{--band-gradient:{gradient};}}</style>"
        f'<div class="band-range" id="band-range-control" style="--band-count:{len(saved_mins)}">'
        f'<div class="band-range-track">'
        f'<div class="band-range-fill" aria-hidden="true"></div>'
        f'<input type="range" id="band-range" min="0" max="{max_hidden}" value="{max_hidden}" step="1"'
        f' aria-label="Hide outer commute bands" orient="vertical">'
        f"</div>"
        f'<div class="band-range-labels">{rows_html}</div>'
        f"</div>"
        f'<p class="cutoff-help">Slide down to hide outer bands one at a time.</p>'
    )


def _poi_shape_svg(shape: str, fill: str = "#fff", size: int = 16) -> str:
    stroke = "#111"
    sw = 2.2
    common = f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"'
    bodies = {
        "square": f'<rect x="4" y="4" width="14" height="14" rx="1.5" {common}/>',
        "triangle": f'<polygon points="11,3 20,19 2,19" {common}/>',
        "diamond": f'<polygon points="11,2 20,11 11,20 2,11" {common}/>',
        "star": (
            f'<polygon points="11,2 13.5,8.5 20.5,8.5 15,12.5 17,19 11,15.5 '
            f'5,19 7,12.5 1.5,8.5 8.5,8.5" {common}/>'
        ),
        "circle": f'<circle cx="11" cy="11" r="8" {common}/>',
    }
    body = bodies.get(shape, bodies["circle"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 22" '
        f'width="{size}" height="{size}">{body}</svg>'
    )


def build_poi_toggles(pois: list[dict]) -> str:
    if not pois:
        return '<p style="font-size:0.85rem;color:#888">No POIs configured.</p>'
    lines = ['<h2 style="margin-bottom:10px">Points of interest</h2>']
    for poi in pois:
        color = poi.get("color", "#fff")
        shape = poi.get("shape", "circle")
        swatch = _poi_shape_svg(shape, color, 16)
        lines.append(
            f'<label class="band-toggle poi-toggle">'
            f'<input type="checkbox" data-poi-id="{poi["id"]}" checked>'
            f'<span class="poi-swatch">{swatch}</span>'
            f'{poi["label"]}'
            f"</label>"
        )
    return "\n        ".join(lines)


def build_listing_toggle(listing_count: int) -> str:
    if listing_count == 0:
        return '<p class="cutoff-help">No listings loaded.</p>'
    return (
        '<label class="band-toggle listing-toggle">'
        '<input type="checkbox" id="show-listings">'
        '<span class="band-swatch" style="background:#ffffff"></span>'
        f"Show listing pins ({listing_count})"
        "</label>"
    )


def build_listings_accordion_label(listing_count: int) -> str:
    if listing_count:
        return f"Listings ({listing_count})"
    return "Listings"


def build_subway_toggle(has_subway: bool) -> str:
    if not has_subway:
        return (
            '<h2 style="margin-top:12px;margin-bottom:6px">Subway</h2>'
            '<p style="font-size:0.85rem;color:#888">Run <code>python scripts/fetch_subway.py</code> to add lines.</p>'
        )
    return (
        '<h2 style="margin-top:12px;margin-bottom:10px">Subway</h2>'
        '<label class="band-toggle subway-toggle">'
        '<input type="checkbox" id="show-subway">'
        '<span class="band-swatch" style="background:#D82233"></span>'
        "Show subway lines &amp; stations"
        "</label>"
        '<label class="band-toggle subway-toggle subway-toggle-nested">'
        '<input type="checkbox" id="animate-subway" disabled>'
        "Pulse lines"
        "</label>"
        '<p class="cutoff-help">Lines use MTA colors; stations use your commute band colors.</p>'
    )


def color_stations_by_band(stations: dict, rings: dict) -> dict:
    """Tag each station with the tightest isochrone ring that contains it."""
    band_polys = []
    for f in rings.get("features", []):
        minutes = f.get("properties", {}).get("minutes")
        if minutes is None:
            continue
        try:
            band_polys.append((int(minutes), shape(f["geometry"])))
        except Exception:
            continue
    band_polys.sort(key=lambda x: x[0])

    out_features = []
    for f in stations.get("features", []):
        props = dict(f.get("properties") or {})
        coords = (f.get("geometry") or {}).get("coordinates")
        minutes = None
        if coords and len(coords) >= 2:
            pt = shape({"type": "Point", "coordinates": coords})
            for m, poly in band_polys:
                if poly.contains(pt) or poly.touches(pt):
                    minutes = m
                    break
        if minutes is not None:
            props["minutes"] = minutes
            props["color"] = BAND_COLORS.get(minutes, "#555")
        else:
            props.pop("minutes", None)
            props["color"] = "#555"
        out_features.append({**f, "properties": props})
    return {"type": "FeatureCollection", "features": out_features}


def build_cutoff_options(saved_mins: list[int]) -> str:
    return "\n            ".join(
        f'<option value="{m}"{" selected" if m == DEFAULT_COMMUTE_MAX else ""}>Within {m} minutes</option>'
        for m in saved_mins
    )


def main():
    if not ISOCHRONES_PATH.exists():
        print(f"Isochrones not found. Run: python scripts/fetch_isochrones.py", file=sys.stderr)
        sys.exit(1)

    isochrones_raw = json.loads(ISOCHRONES_PATH.read_text())
    contours_raw = {"type": "FeatureCollection", "features": []}
    if ISOCHRONES_CONTOURS_PATH.exists():
        contours_raw = json.loads(ISOCHRONES_CONTOURS_PATH.read_text())
    # Midpoints become filled 5-min rings; boundaries are stroked once (not per-ring).
    merged = merge_isochrone_layers(isochrones_raw, contours_raw)
    isochrones = isochrones_to_rings(merged)
    contours = isochrones_to_boundaries(merged)
    saved_mins = sorted(
        f["properties"]["minutes"]
        for f in isochrones["features"]
        if f.get("properties", {}).get("minutes") is not None
    )
    listings = []
    if LISTINGS_JSON.exists():
        listings = json.loads(LISTINGS_JSON.read_text())

    pois = []
    if POIS_JSON.exists():
        pois = json.loads(POIS_JSON.read_text())
    else:
        print(f"No POIs at {POIS_JSON} — run: python scripts/process_pois.py", file=sys.stderr)

    subway_lines = {"type": "FeatureCollection", "features": []}
    subway_stations = {"type": "FeatureCollection", "features": []}
    has_subway = SUBWAY_LINES_PATH.exists() and SUBWAY_STATIONS_PATH.exists()
    if has_subway:
        subway_lines = json.loads(SUBWAY_LINES_PATH.read_text())
        subway_stations = color_stations_by_band(
            json.loads(SUBWAY_STATIONS_PATH.read_text()), isochrones
        )
    else:
        print(
            f"No subway data — run: python scripts/fetch_subway.py",
            file=sys.stderr,
        )

    html = (
        HTML_TEMPLATE.replace("__WORK_ADDRESS__", WORK_ADDRESS)
        .replace("__WORK_LAT__", str(WORK_LAT))
        .replace("__WORK_LNG__", str(WORK_LNG))
        .replace("__BAND_TOGGLES__", build_band_toggles(saved_mins))
        .replace("__POI_TOGGLES__", build_poi_toggles(pois))
        .replace("__LISTING_TOGGLE__", build_listing_toggle(len(listings)))
        .replace("__LISTINGS_ACCORDION_LABEL__", build_listings_accordion_label(len(listings)))
        .replace("__SUBWAY_TOGGLE__", build_subway_toggle(has_subway))
        .replace("__CUTOFF_OPTIONS__", build_cutoff_options(saved_mins))
        .replace("__ISOCHRONES_JSON__", json.dumps(isochrones))
        .replace("__CONTOURS_JSON__", json.dumps(contours))
        .replace("__LISTINGS_JSON__", json.dumps(listings))
        .replace("__POIS_JSON__", json.dumps(pois))
        .replace("__SUBWAY_LINES_JSON__", json.dumps(subway_lines))
        .replace("__SUBWAY_STATIONS_JSON__", json.dumps(subway_stations))
        .replace("__BAND_COLORS_JSON__", json.dumps(BAND_COLORS))
        .replace("__DEFAULT_CUTOFF__", str(DEFAULT_COMMUTE_MAX))
    )

    MAP_HTML.parent.mkdir(parents=True, exist_ok=True)
    font_src = ROOT / "fonts" / "IBMPlexMono-Regular.ttf"
    if font_src.exists():
        font_dest_dir = MAP_HTML.parent / "fonts"
        font_dest_dir.mkdir(parents=True, exist_ok=True)
        (font_dest_dir / font_src.name).write_bytes(font_src.read_bytes())
    else:
        print(f"Missing label font at {font_src}", file=sys.stderr)
    MAP_HTML.write_text(html)

    opacity_pct = int(OVERLAY_DEFAULT_OPACITY * 100)
    overlay = (
        OVERLAY_TEMPLATE.replace("__WORK_LAT__", str(WORK_LAT))
        .replace("__WORK_LNG__", str(WORK_LNG))
        .replace("__BAND_TOGGLES__", build_band_toggles(saved_mins))
        .replace("__CUTOFF_OPTIONS__", build_cutoff_options(saved_mins))
        .replace("__ISOCHRONES_JSON__", json.dumps(isochrones))
        .replace("__CONTOURS_JSON__", json.dumps(contours))
        .replace("__BAND_COLORS_JSON__", json.dumps(BAND_COLORS))
        .replace("__DEFAULT_CUTOFF__", str(DEFAULT_COMMUTE_MAX))
        .replace("__OVERLAY_OPACITY__", str(OVERLAY_DEFAULT_OPACITY))
        .replace("__OVERLAY_OPACITY_PCT__", str(opacity_pct))
    )
    OVERLAY_HTML.write_text(overlay)

    print(f"Map saved → {MAP_HTML}")
    print(f"Overlay saved → {OVERLAY_HTML}")
    print(f"Rings: {saved_mins} (subtle 5-min fills; major strokes at 10-min edges)")
    print(f"Open: open {MAP_HTML}")


if __name__ == "__main__":
    main()
