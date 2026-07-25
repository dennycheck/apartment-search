#!/usr/bin/env python3
"""Publish output/hitlist.html (and map) to the gh-pages branch for phone viewing.

Live URL: https://dennycheck.github.io/apartment-search/hitlist.html
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MAP_HTML, OUTPUT_DIR, OVERLAY_HTML, ROOT

HITLIST = OUTPUT_DIR / "hitlist.html"
REMOTE = "origin"
BRANCH = "gh-pages"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=cwd or ROOT)


def main() -> None:
    if not HITLIST.exists():
        print(f"Missing {HITLIST}. Run score_listings + generate_hitlist_ui first.", file=sys.stderr)
        sys.exit(1)

    run(["git", "fetch", REMOTE, BRANCH])

    with tempfile.TemporaryDirectory(prefix="gh-pages-") as tmp:
        tmp_path = Path(tmp)
        run(["git", "worktree", "add", "--force", str(tmp_path), f"{REMOTE}/{BRANCH}"])
        try:
            # Keep existing map artifacts if present; always refresh hit list.
            for name in ("hitlist.html", "hit_list.md"):
                src = OUTPUT_DIR / name
                if src.exists():
                    shutil.copy2(src, tmp_path / name)
            if MAP_HTML.exists():
                shutil.copy2(MAP_HTML, tmp_path / "index.html")
            if OVERLAY_HTML.exists():
                shutil.copy2(OVERLAY_HTML, tmp_path / "overlay.html")
            (tmp_path / ".nojekyll").touch()

            # Small index link helper if hitlist is the phone entry
            nav = tmp_path / "hitlist.html"
            html = nav.read_text(encoding="utf-8")
            if "github.io/apartment-search" not in html:
                html = html.replace(
                    "<h1>Apartment hit list</h1>",
                    "<h1>Apartment hit list</h1>\n  <p class=\"sub\" style=\"margin-top:-0.5rem\">"
                    "<a href=\"./index.html\">Commute map</a> · updated via gh-pages</p>",
                    1,
                )
                nav.write_text(html, encoding="utf-8")

            run(["git", "add", "-A"], cwd=tmp_path)
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                text=True,
            )
            if not status.stdout.strip():
                print("gh-pages already up to date")
            else:
                run(
                    [
                        "git",
                        "commit",
                        "-m",
                        "Publish hit list for phone viewing",
                    ],
                    cwd=tmp_path,
                )
                run(["git", "push", REMOTE, f"HEAD:{BRANCH}"], cwd=tmp_path)
                print("Pushed gh-pages")
        finally:
            run(["git", "worktree", "remove", "--force", str(tmp_path)])

    print("Phone URL: https://dennycheck.github.io/apartment-search/hitlist.html")


if __name__ == "__main__":
    main()
