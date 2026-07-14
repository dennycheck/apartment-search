#!/usr/bin/env python3
"""Read GeoJSON from stdin and save as an isochrone band. Usage: python scripts/paste_isochrone.py 50 < band.geojson"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.save_isochrone_band import merge_bands, save_band  # noqa: E402

if __name__ == "__main__":
    minutes = int(sys.argv[1])
    incoming = Path(__file__).parent.parent / "data" / "isochrones" / "incoming" / f"{minutes}_min_raw.geojson"
    incoming.parent.mkdir(parents=True, exist_ok=True)
    incoming.write_text(sys.stdin.read())
    dest = save_band(minutes, incoming)
    merged = merge_bands()
    print(f"Saved band → {dest}")
    print(f"Merged → {merged}")
