#!/usr/bin/env python3
"""Run the listing pipeline end-to-end (map-independent).

  StreetEasy HTMLs/ (or incoming/) → listings.csv → geocode + commute_min → hitlist.html

Screenshots: drop images in Cursor chat (or put a JSON extract in incoming/).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LISTINGS_INCOMING_DIR, ROOT, STREETEASY_HTMLS_DIR


def run(script: str, *extra: str) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *extra]
    print(f"\n→ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def default_incoming() -> str:
    if STREETEASY_HTMLS_DIR.exists() and any(STREETEASY_HTMLS_DIR.glob("*.html")):
        return str(STREETEASY_HTMLS_DIR)
    return str(LISTINGS_INCOMING_DIR)


def main():
    args = sys.argv[1:]
    incoming = args[0] if args else default_incoming()

    run("import_listings_html.py", incoming)
    run("process_listings.py")
    run("score_listings.py")
    run("generate_hitlist_ui.py")
    print("\nDone. Open output/hitlist.html (and output/hit_list.md)")
    print("Phone: https://dennycheck.github.io/apartment-search/hitlist.html")
    print(
        "If you marked status on your phone, Download status.json then:\n"
        "  python scripts/apply_hitlist_status.py path/to/hitlist_status.json\n"
        "  python scripts/score_listings.py && python scripts/generate_hitlist_ui.py"
    )


if __name__ == "__main__":
    main()
