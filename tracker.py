#!/usr/bin/env python3
"""Rental tracker, step 1/2: fetch each site, parse its units, print and save them.

Usage:
    python tracker.py                    # fetch every site in sites.json
    python tracker.py --html page.html   # parse a saved page instead (first site's parser)

Output goes to output/listings.json. If a site returns no units, its raw HTML
is saved to output/debug/ so the parser can be fixed.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from parsers import PARSERS

ROOT = Path(__file__).parent
OUT = ROOT / "output"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    print(f"  GET {url} -> HTTP {r.status_code}, {len(r.text):,} bytes")
    r.raise_for_status()
    return r.text


def slug(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def run_site(site, html=None):
    print(f"\n== {site['name']} ==")
    html = html if html is not None else fetch(site["url"])
    units = PARSERS[site["parser"]](html)
    print(f"  parsed {len(units)} units in total")

    if not units:
        debug = OUT / "debug" / f"{slug(site['name'])}.html"
        debug.parent.mkdir(parents=True, exist_ok=True)
        debug.write_text(html, encoding="utf-8")
        print(f"  !! no units found - saved raw HTML to {debug}")
        return None

    wanted = {b.lower() for b in site.get("beds", [])}
    if wanted:
        units = [u for u in units if (u["beds"] or "").lower() in wanted]
        print(f"  {len(units)} match beds filter {site['beds']}")

    for u in units:
        u["property"] = site["name"]
        u["source_url"] = site["url"]
    return units


def print_table(units):
    if not units:
        return
    print(f"\n{'Building':<24} {'Unit':<6} {'Rent':>8} {'Base':>8}  {'Available':<11} Special")
    print("-" * 78)
    for u in sorted(units, key=lambda u: (u["rent"] or 0)):
        rent = f"${u['rent']:,}" if u["rent"] else "?"
        base = f"${u['base_rent']:,}" if u["base_rent"] else "?"
        print(f"{u['building']:<24} {u['unit']:<6} {rent:>8} {base:>8}  "
              f"{u['available'] or '?':<11} {u['special'] or ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="parse a saved HTML file instead of fetching")
    args = ap.parse_args()

    sites = json.loads((ROOT / "sites.json").read_text())
    OUT.mkdir(exist_ok=True)

    all_units, failed = [], []
    for site in sites:
        try:
            html = Path(args.html).read_text(encoding="utf-8") if args.html else None
            units = run_site(site, html)
        except Exception as e:  # keep going so one broken site doesn't stop the rest
            print(f"  !! {site['name']} failed: {e}")
            units = None
        if units is None:
            failed.append(site["name"])
        else:
            print_table(units)
            all_units.extend(units)
        if args.html:
            break

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "failed_sites": failed,
        "units": all_units,
    }
    (OUT / "listings.json").write_text(json.dumps(result, indent=2))
    print(f"\nSaved {len(all_units)} units to output/listings.json")
    if failed:
        print(f"Failed sites: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
