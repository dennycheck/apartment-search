#!/usr/bin/env python3
"""Paginate a StreetEasy search URL and save each results page as HTML.

StreetEasy blocks Playwright's Chromium (press-and-hold captcha loops forever).
Recommended: open *your* Chrome with remote debugging, pass the captcha yourself,
then attach this script so it only paginates + saves HTML.

  # Terminal 1 — quit Chrome first, then:
  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
    --remote-debugging-port=9222 \\
    --user-data-dir=\"$HOME/chrome-streeteasy-debug\"

  # In that Chrome: open your search, solve captcha, confirm listing cards show.

  # Terminal 2:
  python scripts/save_streeteasy_pages.py \\
    --cdp http://127.0.0.1:9222 \\
    --pages 15
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ROOT, STREETEASY_HTMLS_DIR

PROFILE_DIR = ROOT / ".playwright-streeteasy"
CARD_SEL = '[data-testid="listing-card"]'


def with_page(url: str, page: int) -> str:
    """Set or replace page=N on the search URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["page"] = [str(page)]
    query = urlencode({k: v[-1] if isinstance(v, list) else v for k, v in qs.items()})
    return urlunparse(parsed._replace(query=query))


def sanitize_stem(url: str) -> str:
    host = urlparse(url).path.strip("/").replace("/", "_") or "streeteasy"
    host = re.sub(r"[^a-zA-Z0-9_-]+", "_", host)[:60]
    return host or "streeteasy"


def find_streeteasy_page(context):
    """Prefer a tab that already shows listing cards; else any streeteasy tab."""
    with_cards = []
    any_se = []
    for pg in context.pages:
        url = (pg.url or "").lower()
        if "streeteasy.com" not in url:
            continue
        any_se.append(pg)
        try:
            if pg.locator(CARD_SEL).count() > 0:
                with_cards.append(pg)
        except Exception:
            pass
    if with_cards:
        return with_cards[0]
    if any_se:
        return any_se[0]
    return None


def wait_for_listings(page, *, timeout_s: int, allow_manual: bool) -> bool:
    try:
        page.wait_for_selector(CARD_SEL, timeout=min(timeout_s * 1000, 30000))
        return True
    except Exception:
        pass

    html = page.content()
    if "listing-card" in html:
        return True

    denied = "access to this page has been denied" in html.lower() or "px-captcha" in html.lower()
    if not allow_manual:
        if denied:
            print(
                "  Blocked by captcha. Use --cdp with your real Chrome "
                "(see --help), not Playwright's Chromium."
            )
        return False

    print(
        "  No listing cards yet"
        + (" (captcha detected)" if denied else "")
        + f". Finish any challenge in Chrome — waiting up to {timeout_s}s…"
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            page.wait_for_selector(CARD_SEL, timeout=5000)
            print("  Listings appeared.")
            return True
        except Exception:
            continue
    return False


def save_pages(page, *, base_url: str, out_dir: Path, start: int, count: int, delay: float) -> int:
    stem = sanitize_stem(base_url)
    saved = 0
    for page_num in range(start, start + count):
        target = with_page(base_url, page_num)
        print(f"[{page_num}] {target}")
        page.goto(target, wait_until="domcontentloaded", timeout=60000)
        ok = wait_for_listings(page, timeout_s=60, allow_manual=True)
        if not ok:
            html = page.content()
            if page_num > start and "listing-card" not in html:
                print("  No listing cards — stopping.")
                break
            print("  Warning: listing cards not detected; saving page anyway.")

        time.sleep(min(delay, 2.0))
        html = page.content()
        out_path = out_dir / f"{stem}_page_{page_num:02d}.html"
        out_path.write_text(html, encoding="utf-8")
        cards = html.count('data-testid="listing-card"')
        print(f"  → {out_path.name} ({cards} card markers)")
        saved += 1
        if cards == 0 and page_num == start:
            print("  First page empty — stopping.")
            break
        time.sleep(delay)
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save StreetEasy search result pages as HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Recommended (bypasses bot Chromium):
  1. Quit Chrome completely
  2. Start Chrome with debugging:
       /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
         --remote-debugging-port=9222 \\
         --user-data-dir=\"$HOME/chrome-streeteasy-debug\"
  3. In that window: open your StreetEasy search and pass any captcha
  4. Run:
       python scripts/save_streeteasy_pages.py --cdp http://127.0.0.1:9222 --pages 15
""",
    )
    parser.add_argument(
        "--url",
        default="",
        help="Search URL. Optional with --cdp if a StreetEasy results tab is already open.",
    )
    parser.add_argument(
        "--cdp",
        default="",
        help="Attach to Chrome via CDP, e.g. http://127.0.0.1:9222 (recommended)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=STREETEASY_HTMLS_DIR,
        help=f"Output directory (default: {STREETEASY_HTMLS_DIR})",
    )
    parser.add_argument("--pages", type=int, default=10, help="Max pages to save")
    parser.add_argument("--start-page", type=int, default=1, help="First page number")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Launch Playwright Chromium (often blocked — prefer --cdp)",
    )
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between pages")
    parser.add_argument(
        "--captcha-wait",
        type=int,
        default=180,
        help="Seconds to wait for listings / captcha when attached or headed",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright not installed. Run:\n"
            "  pip install playwright\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.cdp and not args.url:
        parser.error("Provide --url, or --cdp with an open StreetEasy tab")

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        if args.cdp:
            print(f"Connecting to Chrome at {args.cdp} …")
            browser = p.chromium.connect_over_cdp(args.cdp)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = find_streeteasy_page(context)
            if page is None:
                page = context.new_page()
                if not args.url:
                    print(
                        "No StreetEasy tab found. Open your search in the debug Chrome, "
                        "or pass --url.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

            base_url = args.url.strip() or page.url
            # Drop page= from whatever tab you're on so pagination starts clean
            if "streeteasy.com" not in base_url.lower():
                print(f"Current tab is not StreetEasy: {base_url}", file=sys.stderr)
                sys.exit(1)

            print(f"Using base URL: {base_url}")
            ok = wait_for_listings(page, timeout_s=args.captcha_wait, allow_manual=True)
            if not ok and not args.url:
                print("Still no listings — open the results page, then re-run.", file=sys.stderr)
                sys.exit(1)

            saved = save_pages(
                page,
                base_url=base_url,
                out_dir=out_dir,
                start=args.start_page,
                count=args.pages,
                delay=args.delay,
            )
            # Do not browser.close() — that would quit the user's Chrome
        else:
            print(
                "Note: launching Playwright Chromium is often blocked by StreetEasy. "
                "Prefer --cdp (see --help)."
            )
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=not args.headed,
                viewport={"width": 1400, "height": 900},
                locale="en-US",
            )
            page = context.pages[0] if context.pages else context.new_page()
            saved = save_pages(
                page,
                base_url=args.url,
                out_dir=out_dir,
                start=args.start_page,
                count=args.pages,
                delay=args.delay,
            )
            context.close()

    print(f"\nSaved {saved} page(s) to {out_dir}")
    print(f'Next: python scripts/run_hitlist_pipeline.py "{out_dir}"')


if __name__ == "__main__":
    main()
