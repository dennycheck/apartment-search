#!/usr/bin/env python3
"""Save a midpoint isochrone contour (stroke-only on the map) and merge contours."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    COMMUTE_CONTOURS_MIN,
    DATA_DIR,
    ISOCHRONES_CONTOURS_DIR,
    ISOCHRONES_CONTOURS_PATH,
)

META_PATH = DATA_DIR / "isochrones" / "meta.json"


def annotate_contour(data: dict, minutes: int) -> dict:
    if data.get("type") != "FeatureCollection":
        raise ValueError("Expected GeoJSON FeatureCollection")

    for feature in data.get("features", []):
        props = feature.setdefault("properties", {})
        props["minutes"] = minutes
        props["kind"] = "contour"
        props["search_id"] = f"{minutes}_min_contour"
    return data


def save_contour(minutes: int, source: Path) -> Path:
    if minutes not in COMMUTE_CONTOURS_MIN:
        print(
            f"Warning: {minutes} min not in COMMUTE_CONTOURS_MIN {COMMUTE_CONTOURS_MIN}",
            file=sys.stderr,
        )

    data = json.loads(source.read_text())
    data = annotate_contour(data, minutes)

    ISOCHRONES_CONTOURS_DIR.mkdir(parents=True, exist_ok=True)
    dest = ISOCHRONES_CONTOURS_DIR / f"{minutes}_min.geojson"
    dest.write_text(json.dumps(data, indent=2))
    return dest


def merge_contours() -> Path:
    features = []
    saved = []

    if ISOCHRONES_CONTOURS_DIR.exists():
        for path in sorted(ISOCHRONES_CONTOURS_DIR.glob("*_min.geojson")):
            contour_data = json.loads(path.read_text())
            for feature in contour_data.get("features", []):
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
    meta["contours_saved"] = sorted(saved)
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(meta, indent=2))

    ISOCHRONES_CONTOURS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ISOCHRONES_CONTOURS_PATH.write_text(json.dumps(merged, indent=2))
    return ISOCHRONES_CONTOURS_PATH


def main():
    if len(sys.argv) < 3:
        print(
            "Usage: python scripts/save_isochrone_contour.py MINUTES path/to/contour.geojson",
            file=sys.stderr,
        )
        sys.exit(1)

    minutes = int(sys.argv[1])
    source = Path(sys.argv[2])

    dest = save_contour(minutes, source)
    merged = merge_contours()

    print(f"Saved contour → {dest}")
    print(f"Merged {len(list(ISOCHRONES_CONTOURS_DIR.glob('*_min.geojson')))} contour(s) → {merged}")


if __name__ == "__main__":
    main()
