#!/usr/bin/env python3
"""Save a single isochrone band from playground/API output and merge into isochrones.geojson."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import COMMUTE_BANDS_MIN, DATA_DIR, ISOCHRONES_PATH

BANDS_DIR = DATA_DIR / "isochrones" / "bands"
META_PATH = DATA_DIR / "isochrones" / "meta.json"


def annotate_band(data: dict, minutes: int) -> dict:
    if data.get("type") != "FeatureCollection":
        raise ValueError("Expected GeoJSON FeatureCollection")

    for feature in data.get("features", []):
        props = feature.setdefault("properties", {})
        props["minutes"] = minutes
        props["search_id"] = f"{minutes}_min"
        props.setdefault("arrival", "2026-07-09T08:30:00-04:00")
        props.setdefault("work_address", "240 Greenwich St, New York, NY")
    return data


def save_band(minutes: int, source: Path) -> Path:
    if minutes not in COMMUTE_BANDS_MIN:
        print(f"Warning: {minutes} min not in standard bands {COMMUTE_BANDS_MIN}", file=sys.stderr)

    data = json.loads(source.read_text())
    data = annotate_band(data, minutes)

    BANDS_DIR.mkdir(parents=True, exist_ok=True)
    dest = BANDS_DIR / f"{minutes}_min.geojson"
    dest.write_text(json.dumps(data, indent=2))
    return dest


def merge_bands() -> Path:
    """Combine all saved band files into data/isochrones.geojson."""
    features = []
    saved = []

    if BANDS_DIR.exists():
        for path in sorted(BANDS_DIR.glob("*_min.geojson")):
            band_data = json.loads(path.read_text())
            for feature in band_data.get("features", []):
                features.append(feature)
            try:
                minutes = int(path.stem.replace("_min", ""))
                saved.append(minutes)
            except ValueError:
                pass

    merged = {"type": "FeatureCollection", "features": features}

    meta = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text())
    meta["bands_saved"] = sorted(saved)
    meta["work_address"] = "240 Greenwich St, New York, NY"
    meta["arrival_time"] = meta.get("arrival_time", "2026-07-09T08:30:00-04:00")
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(meta, indent=2))

    ISOCHRONES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ISOCHRONES_PATH.write_text(json.dumps(merged, indent=2))
    return ISOCHRONES_PATH


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/save_isochrone_band.py MINUTES path/to/band.geojson", file=sys.stderr)
        sys.exit(1)

    minutes = int(sys.argv[1])
    source = Path(sys.argv[2])

    dest = save_band(minutes, source)
    merged = merge_bands()

    print(f"Saved band → {dest}")
    print(f"Merged {len(list(BANDS_DIR.glob('*_min.geojson')))} band(s) → {merged}")


if __name__ == "__main__":
    main()
