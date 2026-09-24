#!/usr/bin/env python3
"""Rental tracker: fetch each site, compare with what was seen before, and push
new units / price changes within budget to ntfy.

Usage:
    python tracker.py                    # normal run (notifies if NTFY_TOPIC is set)
    python tracker.py --no-notify        # print what would be sent, don't send
    python tracker.py --html page.html   # parse a saved page for the first site, no state changes

Saved state: data/<property>.json (one file per property, committed back to the repo).
Latest scrape: output/listings.json. Raw HTML of a site that parsed 0 units: output/debug/.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

import notify
import state
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


def pages_of(site):
    """A site is either one "url", or several "pages" (e.g. one per building),
    each {"url": ..., "building": ...}."""
    return site.get("pages") or [{"url": site["url"]}]


def link_of(site):
    """Where a notification tap should go."""
    return site.get("link") or site.get("url") or pages_of(site)[0]["url"]


def scrape(site, html=None):
    """Returns the site's units after the bedroom filter, or None if parsing found nothing.
    If any page fails to download, the exception propagates and the whole site is skipped
    this run (otherwise that building's units would look delisted, then "new" next time)."""
    parser = PARSERS[site["parser"]]
    units, empty_pages = [], []
    for page in pages_of(site):
        page_html = html if html is not None else fetch(page["url"])
        opts = {"building": page["building"]} if page.get("building") else {}
        found = parser(page_html, **opts)
        if len(pages_of(site)) > 1:
            print(f"    {page.get('building', page['url'])}: {len(found)} units")
        if not found:
            empty_pages.append((page, page_html))
        units.extend(found)
    print(f"  parsed {len(units)} units in total")
    if not units:
        for i, (page, page_html) in enumerate(empty_pages):
            debug = OUT / "debug" / f"{state.slug(site['name'])}-{i + 1}.html"
            debug.parent.mkdir(parents=True, exist_ok=True)
            debug.write_text(page_html, encoding="utf-8")
            print(f"  !! no units found on {page['url']} - saved raw HTML to {debug}")
        return None
    wanted = {b.lower() for b in site.get("beds", [])}
    if wanted:
        units = [u for u in units if (u["beds"] or "").lower() in wanted]
        print(f"  {len(units)} match beds filter {site['beds']}")
    return units


def print_table(units, max_rent=None):
    if not units:
        return
    print(f"\n  {'Building':<24} {'Unit':<6} {'Rent':>8} {'Base':>8}  {'Available':<11} Special")
    print("  " + "-" * 78)
    for u in sorted(units, key=lambda u: state.price_of(u) or 0):
        rent = f"${u['rent']:,}" if u["rent"] else "–"
        base = f"${u['base_rent']:,}" if u["base_rent"] else "–"
        over = "  (over budget)" if max_rent and (state.price_of(u) or 0) > max_rent else ""
        print(f"  {u['building']:<24} {u['unit']:<6} {rent:>8} {base:>8}  "
              f"{u['available'] or '?':<11} {u['special'] or ''}{over}")


def process_site(site, topic, send_enabled, today):
    """Scrape one site, diff against saved state, notify, save. Returns (units, ok)."""
    name = site["name"]
    print(f"\n== {name} ==")
    units = scrape(site)
    if units is None:
        return [], False
    max_rent = site.get("max_rent")
    print_table(units, max_rent)

    old = state.load(name)
    if old is None:
        state.save(name, state.diff({}, units, today)[0])
        print(f"\n  First run for {name}: saved {len(units)} units, no notifications sent.")
        return units, True

    # A layout change that breaks half the parsing shouldn't wipe the saved units
    # (the next good run would then re-announce all of them as new).
    if len(old) >= 10 and len(units) < len(old) * 0.5:
        print(f"  !! only {len(units)} units vs {len(old)} saved - looks like a parsing "
              f"problem, not saving or notifying this run")
        return units, False

    new_state, events = state.diff(old, units, today)
    gone = len(set(old) - set(new_state))
    if max_rent:
        # Units with no listed price are held back until a price appears.
        events = [e for e in events
                  if state.price_of(e["unit"]) is not None and state.price_of(e["unit"]) <= max_rent]
    print(f"\n  {len(events)} notifiable change(s), {gone} unit(s) no longer listed")

    if events:
        title, body = notify.build_message(name, events)
        print(f"  --- {title} ---\n" + "\n".join("  " + line for line in body.splitlines()))
        if send_enabled:
            notify.send(topic, title, body, click_url=link_of(site))
            print("  sent to ntfy")
        else:
            print("  (not sent: notifications disabled)")

    state.save(name, new_state)
    return units, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="parse a saved HTML file and print it (no state changes)")
    ap.add_argument("--site", help="with --html: which site's parser to use (default: the first)")
    ap.add_argument("--no-notify", action="store_true", help="print notifications instead of sending")
    args = ap.parse_args()

    sites = json.loads((ROOT / "sites.json").read_text())
    OUT.mkdir(exist_ok=True)

    if args.html:
        site = next((s for s in sites if s["name"] == args.site), None) if args.site else sites[0]
        if site is None:
            sys.exit(f"No site named {args.site!r} in sites.json")
        print(f"\n== {site['name']} (from {args.html}) ==")
        one_page = {**site, "pages": pages_of(site)[:1]}  # a saved file is a single page
        units = scrape(one_page, Path(args.html).read_text(encoding="utf-8")) or []
        print_table(units, site.get("max_rent"))
        return

    topic = os.environ.get("NTFY_TOPIC", "").strip()
    send_enabled = bool(topic) and not args.no_notify
    if not topic and not args.no_notify and os.environ.get("GITHUB_ACTIONS"):
        # Without this, a scheduled run would record changes as seen without telling anyone.
        sys.exit("NTFY_TOPIC secret is not set. Add it under Settings -> Secrets and variables -> Actions.")

    today = datetime.now(timezone.utc).date().isoformat()
    all_units, failed = [], []
    for site in sites:
        try:
            units, ok = process_site(site, topic, send_enabled, today)
        except Exception as e:  # one broken site shouldn't stop the others
            print(f"  !! {site['name']} failed: {e}")
            units, ok = [], False
        all_units.extend({**u, "property": site["name"]} for u in units)
        if not ok:
            failed.append(site["name"])

    (OUT / "listings.json").write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "failed_sites": failed,
        "units": all_units,
    }, indent=2))
    if failed:
        print(f"\nFailed sites: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
