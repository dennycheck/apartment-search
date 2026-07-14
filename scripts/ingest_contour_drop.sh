#!/bin/bash
# Usage: scripts/ingest_contour_drop.sh MINUTES path/to/file.geojson
#    or: pbpaste | scripts/ingest_contour_drop.sh MINUTES
set -euo pipefail
MINUTES="${1:?minutes required}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW="$ROOT/data/isochrones/incoming/${MINUTES}_min_contour_raw.geojson"
mkdir -p "$(dirname "$RAW")"
if [[ $# -ge 2 ]]; then
  cp "$2" "$RAW"
else
  cat > "$RAW"
fi
"$ROOT/.venv/bin/python" "$ROOT/scripts/save_isochrone_contour.py" "$MINUTES" "$RAW"
"$ROOT/.venv/bin/python" "$ROOT/scripts/generate_map.py"
