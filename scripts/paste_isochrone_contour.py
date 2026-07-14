#!/usr/bin/env python3
"""Read GeoJSON from stdin and save as a stroke-only midpoint contour.

Usage: python scripts/paste_isochrone_contour.py 15 < contour.geojson
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.save_isochrone_contour import merge_contours, save_contour  # noqa: E402

if __name__ == "__main__":
    minutes = int(sys.argv[1])
    incoming = (
        Path(__file__).parent.parent
        / "data"
        / "isochrones"
        / "incoming"
        / f"{minutes}_min_contour_raw.geojson"
    )
    incoming.parent.mkdir(parents=True, exist_ok=True)
    incoming.write_text(sys.stdin.read())
    dest = save_contour(minutes, incoming)
    merged = merge_contours()
    print(f"Saved contour → {dest}")
    print(f"Merged → {merged}")
