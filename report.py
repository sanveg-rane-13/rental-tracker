#!/usr/bin/env python3
"""On-demand report: every currently listed unit (from data/*.json) at or under a rent
limit, optionally with a minimum size, sent to the ntfy topic in NTFY_TOPIC.

Settings come from report.json and can be overridden per run:
    python report.py                               # use report.json
    python report.py --max-rent 3600 --min-sqft 650
    python report.py --dry-run                     # print only, send nothing
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import notify
import state

ROOT = Path(__file__).parent
OUT = ROOT / "output"
NY = ZoneInfo("America/New_York")
NTFY_LIMIT = 3800  # ntfy messages max out around 4 KB; longer reports are split


def load_units():
    """Every unit in every property's saved file, tagged with its property name."""
    units = []
    for path in sorted(state.DATA.glob("*.json")):
        doc = json.loads(path.read_text())
        for u in doc["units"].values():
            units.append({**u, "property": doc.get("property", path.stem)})
    return units


def skip_buildings(units, names):
    """(units not in the named buildings, number of units skipped).
    Names match building names case-insensitively, e.g. "Parkside East"."""
    skip = {n.strip().lower() for n in names or [] if n.strip()}
    if not skip:
        return units, 0
    kept = [u for u in units if (u.get("building") or "").strip().lower() not in skip]
    return kept, len(units) - len(kept)


def select(units, max_rent, min_sqft=None):
    """(matches sorted by price, count skipped because size is unknown)."""
    matches, unknown_size = [], 0
    for u in units:
        price = state.price_of(u)
        if price is None or price > max_rent:
            continue
        if min_sqft:
            if not u.get("sqft"):
                unknown_size += 1
                continue
            if u["sqft"] < min_sqft:
                continue
        matches.append(u)
    matches.sort(key=lambda u: (state.price_of(u), u["property"], u["building"], u["unit"]))
    return matches, unknown_size


def _money(n):
    return f"${n:,}" if n else "?"


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _avail(u, this_year=None):
    """'Now' -> 'now', '9/30/2026' -> 'Sep 30' (year shown only if it isn't this year)."""
    a = u.get("available") or "?"
    if a.lower() == "now":
        return "now"
    parts = a.split("/")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        m, d, y = (int(p) for p in parts)
        this_year = this_year or datetime.now(NY).year
        return f"{MONTHS[m - 1]} {d}" + (f", {y}" if y != this_year else "")
    return a


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def describe(max_rent, min_sqft):
    """Plain ASCII on purpose: it's also used in the notification title, which is sent
    as an HTTP header where non-ASCII characters can arrive garbled."""
    s = f"up to {_money(max_rent)}"
    return s + (f", {min_sqft:,}+ sq ft" if min_sqft else "")


def text_line(u, show_building=True):
    """'$3,285 · The Zenith 507 · 731 sq ft · now · 1 Month Free'"""
    parts = [_money(state.price_of(u)),
             f"{u['building']} {u['unit']}" if show_building else f"#{u['unit']}"]
    if u.get("sqft"):
        parts.append(f"{u['sqft']:,} sq ft")
    parts.append(_avail(u))
    if u.get("special"):
        parts.append(u["special"])
    return " · ".join(parts)


def text_report(matches, max_rent, min_sqft, unknown_size, skipped=0):
    """Plain text for ntfy: a summary, then one section per property (cheapest first),
    each unit on one line with the price first. Sections are separated by blank lines."""
    if not matches:
        text = f"No apartments {describe(max_rent, min_sqft)} right now."
    else:
        by_property = {}
        for u in matches:  # matches are already sorted by price
            by_property.setdefault(u["property"], []).append(u)
        cheapest = matches[0]
        n_props = len(by_property)
        blocks = [f"{_plural(len(matches), 'apartment')} {describe(max_rent, min_sqft)}\n"
                  f"{n_props} {'property' if n_props == 1 else 'properties'} · cheapest "
                  f"{_money(state.price_of(cheapest))} ({cheapest['property']})"]
        for prop, units in by_property.items():  # insertion order = cheapest property first
            one_building = all(u["building"] == prop for u in units)
            lines = [f"━━ {prop.upper()} · {len(units)} ━━"]
            lines += [text_line(u, show_building=not one_building) for u in units]
            blocks.append("\n".join(lines))
        text = "\n\n".join(blocks)
    notes = []
    if unknown_size:
        notes.append(f"{_plural(unknown_size, 'unit')} under the rent limit left out: size unknown")
    if skipped:
        notes.append(f"{_plural(skipped, 'unit')} in excluded buildings not shown")
    if notes:
        text += "\n\n" + "\n".join(f"({n})" for n in notes)
    return text + "\n"


def write_csv(matches, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["property", "building", "unit", "beds", "price", "base_rent", "base_rent_max", "rent",
            "sqft", "available", "special", "floor_plan", "first_seen"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for u in matches:
            w.writerow({**u, "price": state.price_of(u)})


def _fits(s):
    return len(s.encode("utf-8")) <= NTFY_LIMIT


def ntfy_chunks(text):
    """Split the report into ntfy-sized messages, keeping each property's section
    together when it fits; a section too long for one message is split by lines."""
    pieces = []
    for block in text.strip("\n").split("\n\n"):
        if _fits(block):
            pieces.append(block)
            continue
        cur = ""
        for line in block.split("\n"):
            if cur and not _fits(cur + "\n" + line):
                pieces.append(cur)
                cur = ""
            cur = f"{cur}\n{line}" if cur else line
        if cur:
            pieces.append(cur)
    chunks, cur = [], ""
    for piece in pieces:
        if cur and not _fits(cur + "\n\n" + piece):
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return chunks


def _number(s):
    """Accepts '3500', '$3,500', ' 3500 '."""
    cleaned = s.replace("$", "").replace(",", "").strip()
    if not cleaned.isdigit():
        raise argparse.ArgumentTypeError(f"not a whole number: {s!r}")
    return int(cleaned)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rent", type=_number, help="override report.json max_rent")
    ap.add_argument("--min-sqft", type=_number, help="override report.json min_sqft (0 = none)")
    ap.add_argument("--include-all", action="store_true",
                    help="don't skip the buildings in report.json skip_buildings")
    ap.add_argument("--dry-run", action="store_true", help="print only, send nothing")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "report.json").read_text())
    max_rent = args.max_rent or cfg.get("max_rent")
    min_sqft = args.min_sqft if args.min_sqft is not None else cfg.get("min_sqft")
    if not max_rent:
        sys.exit("No max_rent: set it in report.json or pass --max-rent")

    matches, unknown_size = select(load_units(), max_rent, min_sqft or None)
    skipped = 0
    if not args.include_all:
        # the note counts units that matched the filters but are in excluded buildings
        matches, skipped = skip_buildings(matches, cfg.get("skip_buildings"))
    text = text_report(matches, max_rent, min_sqft, unknown_size, skipped)
    write_csv(matches, OUT / "report.csv")
    stamp = datetime.now(NY).strftime("%Y-%m-%d %H:%M")
    print(f"Report {stamp}\n\n{text}")
    if args.dry_run:
        return

    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        sys.exit("NTFY_TOPIC is not set, nothing sent.")
    chunks = ntfy_chunks(text)
    for i, chunk in enumerate(chunks, 1):
        title = f"Report: {_plural(len(matches), 'apartment')} {describe(max_rent, min_sqft)}"
        if len(chunks) > 1:
            title += f" ({i}/{len(chunks)})"
        notify.send(topic, title, chunk)
    print(f"Sent {len(chunks)} ntfy message(s)")


if __name__ == "__main__":
    main()
