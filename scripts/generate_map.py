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
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    #app { display: grid; grid-template-columns: 320px 1fr; height: 100vh; }
    #sidebar {
      background: #1a1a2e; color: #eee; overflow-y: auto;
      display: flex; flex-direction: column; border-right: 1px solid #333;
    }
    #sidebar header { padding: 16px; border-bottom: 1px solid #333; }
    #sidebar header h1 { font-size: 1.1rem; font-weight: 600; margin-bottom: 4px; }
    #sidebar header p { font-size: 0.8rem; color: #aaa; line-height: 1.4; }
    .section { padding: 16px; border-bottom: 1px solid #333; }
    .section h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #888; margin-bottom: 10px; }
    .band-toggle { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; cursor: pointer; font-size: 0.9rem; }
    .band-toggle input, .poi-toggle input { accent-color: #4fc3f7; }
    .band-swatch {
      width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
      border: 2px solid rgba(255,255,255,0.85);
    }
    .poi-swatch {
      width: 16px; height: 16px; flex-shrink: 0; display: inline-flex;
      align-items: center; justify-content: center;
    }
    .poi-swatch svg { width: 16px; height: 16px; display: block; }
    .poi-marker-icon { background: none !important; border: none !important; }
    .poi-marker-icon.dimmed { opacity: 0.3; }
    .active-cutoff { margin-top: 12px; }
    .cutoff-help {
      margin-top: 8px; font-size: 0.75rem; color: #888; line-height: 1.4;
    }
    .active-cutoff select {
      width: 100%; padding: 8px; border-radius: 6px; border: 1px solid #444;
      background: #16213e; color: #eee; font-size: 0.9rem;
    }
    #stats { font-size: 0.85rem; color: #aaa; line-height: 1.6; }
    #listings-table-wrap { flex: 1; overflow-y: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    th {
      position: sticky; top: 0; background: #16213e; padding: 8px 10px;
      text-align: left; cursor: pointer; user-select: none; white-space: nowrap;
    }
    th:hover { background: #1f3460; }
    td { padding: 8px 10px; border-bottom: 1px solid #2a2a4a; vertical-align: top; }
    tr:hover td { background: #16213e; }
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
    a { color: #4fc3f7; }
    #controls-pill {
      display: none;
      position: fixed; z-index: 1200;
      left: 50%; bottom: max(16px, env(safe-area-inset-bottom));
      transform: translateX(-50%);
      border: none; border-radius: 999px;
      padding: 12px 20px;
      background: #1a1a2e; color: #eee;
      font: 600 0.9rem/1 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      box-shadow: 0 8px 28px rgba(0,0,0,0.45);
      cursor: pointer;
    }
    #controls-pill:active { transform: translateX(-50%) scale(0.98); }
    .sidebar-close {
      display: none;
      margin-left: auto;
      border: 1px solid #444; border-radius: 8px;
      background: #16213e; color: #eee;
      padding: 6px 10px; font-size: 0.8rem; cursor: pointer;
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
      #sidebar {
        position: fixed; z-index: 1100;
        inset: auto 0 0 0;
        max-height: min(78dvh, 640px);
        border-right: none;
        border-top: 1px solid #333;
        border-radius: 16px 16px 0 0;
        box-shadow: 0 -12px 40px rgba(0,0,0,0.45);
        transform: translateY(110%);
        transition: transform 0.25s ease;
        pointer-events: none;
      }
      #app.controls-open #sidebar {
        transform: translateY(0);
        pointer-events: auto;
      }
      #controls-pill { display: block; }
      #app.controls-open #controls-pill { display: none; }
      .sidebar-close { display: inline-flex; align-items: center; }
      #listings-table-wrap { max-height: 40vh; }
    }
  </style>
</head>
<body>
  <div id="app">
    <aside id="sidebar">
      <header>
        <div class="header-text">
          <h1>Apartment Commute Map</h1>
          <p>Work: __WORK_ADDRESS__<br>Arrive by 8:30 AM · Public transit</p>
          <p style="margin-top:10px"><a href="overlay.html" target="_blank">Open overlay mode ↗</a></p>
        </div>
        <button type="button" class="sidebar-close" id="controls-close" aria-label="Close controls">Map</button>
      </header>
      <div class="section">
        <h2>Isochrone bands</h2>
        __BAND_TOGGLES__
        <div class="active-cutoff">
          <h2 style="margin-top:12px">Max commute</h2>
          <select id="cutoff-select">
            __CUTOFF_OPTIONS__
          </select>
          <p class="cutoff-help">Highlights zones within this time; fades farther bands on the map.</p>
        </div>
      </div>
      <div class="section">
        <h2>Summary</h2>
        __POI_TOGGLES__
        __LISTING_TOGGLE__
        <div id="stats" style="margin-top:12px"></div>
      </div>
      <div id="listings-table-wrap" class="section" style="border-bottom:none;padding-top:0">
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
    </aside>
    <div id="map"></div>
    <button type="button" id="controls-pill" aria-expanded="false" aria-controls="sidebar">Controls</button>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const ISOCHRONES = __ISOCHRONES_JSON__;
    const LISTINGS = __LISTINGS_JSON__;
    const POIS = __POIS_JSON__;
    const BAND_COLORS = __BAND_COLORS_JSON__;
    const WORK = { lat: __WORK_LAT__, lng: __WORK_LNG__ };

    let activeCutoff = __DEFAULT_CUTOFF__;
    let sortKey = "commute_min";
    let sortAsc = true;

    const appEl = document.getElementById("app");
    const controlsPill = document.getElementById("controls-pill");
    const controlsClose = document.getElementById("controls-close");

    function setControlsOpen(open) {
      appEl.classList.toggle("controls-open", open);
      controlsPill.setAttribute("aria-expanded", open ? "true" : "false");
      if (window.map) setTimeout(() => map.invalidateSize(), 260);
    }
    controlsPill.addEventListener("click", () => setControlsOpen(true));
    controlsClose.addEventListener("click", () => setControlsOpen(false));

    const map = L.map("map", { zoomControl: true }).setView([WORK.lat, WORK.lng], 12);
    window.map = map;

    // Basemap under zones; place names drawn above the heat overlays.
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 20
    }).addTo(map);

    map.createPane("isochronePane");
    map.getPane("isochronePane").style.zIndex = 350;
    map.createPane("contourPane");
    map.getPane("contourPane").style.zIndex = 360;
    map.createPane("labelsPane");
    map.getPane("labelsPane").style.zIndex = 450;
    map.getPane("labelsPane").style.pointerEvents = "none";
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png", {
      pane: "labelsPane",
      subdomains: "abcd",
      maxZoom: 20,
      opacity: 0.95
    }).addTo(map);

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
    const listingsLayer = L.layerGroup().addTo(map);
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
      marker.bindPopup(() => buildPoiPopup(poi));
      poiMarkers[poi.id] = marker;
      poiLayer.addLayer(marker);
    });

    function buildPoiPopup(poi) {
      const commute = poi.commute_min != null ? `≤ ${poi.commute_min} min to work` : "Outside isochrone bands";
      return `<b>${poi.label}</b><br>${poi.address}<br>${commute}`;
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
      cb.addEventListener("change", () => {
        if (cb.checked) map.addLayer(listingsLayer);
        else map.removeLayer(listingsLayer);
      });
    });

    document.querySelectorAll(".poi-toggle input").forEach(cb => {
      cb.addEventListener("change", () => {
        const marker = poiMarkers[cb.dataset.poiId];
        if (!marker) return;
        if (cb.checked) poiLayer.addLayer(marker);
        else poiLayer.removeLayer(marker);
      });
    });

    document.querySelectorAll(".band-toggle input").forEach(cb => {
      cb.addEventListener("change", () => {
        const min = parseInt(cb.dataset.minutes);
        const layer = bandLayers[min];
        const stroke = contourLayers[min];
        if (cb.checked) {
          if (layer) map.addLayer(layer);
          if (stroke) map.addLayer(stroke);
        } else {
          if (layer) map.removeLayer(layer);
          if (stroke) map.removeLayer(stroke);
        }
      });
    });

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
      background: rgba(20, 20, 30, 0.82);
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
    #controls .swatch {
      width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0;
      border: 1px solid rgba(255,255,255,0.5);
    }
    #controls select, #controls input[type=range] { width: 100%; }
    #controls select {
      padding: 6px 8px; border-radius: 6px; border: 1px solid #444;
      background: #16213e; color: #eee; font-size: 0.8rem;
    }
    .ctrl-block { margin-top: 10px; }
    .ctrl-block label.title {
      display: block; font-size: 0.68rem; text-transform: uppercase;
      letter-spacing: 0.05em; color: #888; margin-bottom: 4px;
    }
    #opacity-val { color: #aaa; font-size: 0.72rem; }
    #controls a { color: #4fc3f7; font-size: 0.75rem; }
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

    document.querySelectorAll(".band-toggle input").forEach(cb => {
      cb.addEventListener("change", () => {
        const min = parseInt(cb.dataset.minutes, 10);
        const layer = bandLayers[min];
        const stroke = contourLayers[min];
        if (cb.checked) {
          if (layer) map.addLayer(layer);
          if (stroke) map.addLayer(stroke);
        } else {
          if (layer) map.removeLayer(layer);
          if (stroke) map.removeLayer(stroke);
        }
      });
    });

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
    lines = []
    prev_min = None
    for minutes in saved_mins:
        color = BAND_COLORS.get(minutes, "#888")
        label = band_ring_label(minutes, prev_min)
        lines.append(
            f'<label class="band-toggle">'
            f'<input type="checkbox" data-minutes="{minutes}" checked>'
            f'<span class="band-swatch" style="background:{color}"></span>'
            f"{label}"
            f"</label>"
        )
        prev_min = minutes
    return "\n        ".join(lines)


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
        return ""
    return (
        '<h2 style="margin-top:12px;margin-bottom:10px">Listings</h2>'
        '<label class="band-toggle listing-toggle">'
        '<input type="checkbox" id="show-listings" checked>'
        '<span class="band-swatch" style="background:#ffffff"></span>'
        f"Show listing pins ({listing_count})"
        "</label>"
    )


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

    html = (
        HTML_TEMPLATE.replace("__WORK_ADDRESS__", WORK_ADDRESS)
        .replace("__WORK_LAT__", str(WORK_LAT))
        .replace("__WORK_LNG__", str(WORK_LNG))
        .replace("__BAND_TOGGLES__", build_band_toggles(saved_mins))
        .replace("__POI_TOGGLES__", build_poi_toggles(pois))
        .replace("__LISTING_TOGGLE__", build_listing_toggle(len(listings)))
        .replace("__CUTOFF_OPTIONS__", build_cutoff_options(saved_mins))
        .replace("__ISOCHRONES_JSON__", json.dumps(isochrones))
        .replace("__CONTOURS_JSON__", json.dumps(contours))
        .replace("__LISTINGS_JSON__", json.dumps(listings))
        .replace("__POIS_JSON__", json.dumps(pois))
        .replace("__BAND_COLORS_JSON__", json.dumps(BAND_COLORS))
        .replace("__DEFAULT_CUTOFF__", str(DEFAULT_COMMUTE_MAX))
    )

    MAP_HTML.parent.mkdir(parents=True, exist_ok=True)
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
