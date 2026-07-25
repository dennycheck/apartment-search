#!/usr/bin/env python3
"""Run the listing pipeline end-to-end (map-independent).

  incoming HTML/JSON → listings.csv → geocode + commute_min → hit_list.md

Screenshots: drop images in Cursor chat (or put a JSON extract in incoming/).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LISTINGS_INCOMING_DIR, ROOT


def run(script: str, *extra: str) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *extra]
    print(f"\n→ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main():
    args = sys.argv[1:]
    incoming = args[0] if args else str(LISTINGS_INCOMING_DIR)

    run("import_listings_html.py", incoming)
    run("process_listings.py")
    run("score_listings.py")
    run("generate_hitlist_ui.py")
    print("\nDone. Open output/hitlist.html (and output/hit_list.md)")


if __name__ == "__main__":
    main()
