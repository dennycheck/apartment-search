#!/usr/bin/env python3
"""Run the full apartment search pipeline."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SCRIPTS = ROOT / "scripts"


def run(script: str, optional: bool = False) -> bool:
    path = SCRIPTS / script
    print(f"\n{'=' * 50}\n→ {script}\n{'=' * 50}")
    result = subprocess.run([sys.executable, str(path)], cwd=ROOT)
    if result.returncode != 0:
        if optional:
            print(f"  (skipped — {script} failed or missing inputs)")
            return False
        sys.exit(result.returncode)
    return True


def main():
    run("fetch_listings_rentcast.py", optional=True)
    run("fetch_isochrones.py", optional=True)
    if not (ROOT / "data" / "isochrones.geojson").exists():
        print(
            "\nNo isochrones found. Either:\n"
            "  • Save playground response → data/isochrones.geojson (see README Path A)\n"
            "  • Or add TravelTime keys to .env and re-run",
            file=sys.stderr,
        )
        sys.exit(1)
    run("process_pois.py", optional=True)
    run("process_listings.py", optional=True)
    run("generate_map.py")
    run("report_commute.py", optional=True)
    print(f"\nDone. Open output/index.html in your browser.")


if __name__ == "__main__":
    main()
