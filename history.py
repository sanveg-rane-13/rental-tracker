"""Append-only event log for later analysis: data/history/events.csv

One row per change, never rewritten, so it keeps what the per-property state
files forget (delisted units, old move-in dates, when each change was seen).
Opens directly in Excel / Google Sheets / pandas.

Events:
  tracking_started  one-time snapshot of every unit already saved when the log began
  listed            unit appeared (first run for a property, a new listing, or re-listed)
  price_change      price changed; price = new, old_price = before
  available_change  move-in date changed; available = new, old_available = before
  delisted          unit no longer listed; price/available are its last known values
  site_failed       property couldn't be read this run (a gap, not a delisting)

Times are when the run saw the change (hourly runs, so accurate to about an hour),
in UTC and in New York time for time-of-day analysis.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import state

NY = ZoneInfo("America/New_York")
COLUMNS = [
    "time_utc", "time_ny", "property", "building", "unit", "beds", "event",
    "price", "old_price", "base_rent", "base_rent_max", "rent",
    "available", "old_available", "sqft", "floor_plan", "special", "first_seen", "note",
]
EVENT_NAMES = {"new": "listed", "price": "price_change",
               "available": "available_change", "delisted": "delisted"}


def _path():
    return state.DATA / "history" / "events.csv"  # resolved at call time (tests move DATA)


def _row(now, prop, unit, event, **extra):
    unit = unit or {}
    row = {
        "time_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        "time_ny": now.astimezone(NY).strftime("%Y-%m-%d %H:%M"),
        "property": prop,
        "event": event,
        "price": state.price_of(unit) if unit else None,
        **{k: unit.get(k) for k in ("building", "unit", "beds", "base_rent", "base_rent_max",
                                    "rent", "available", "sqft", "floor_plan", "special",
                                    "first_seen")},
    }
    row.update(extra)
    return row


def _append(rows):
    if not rows:
        return
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        w.writerows(rows)


def ensure_started(sites, now):
    """First time only: snapshot every unit already in the state files, so the log
    has a complete starting point even though tracking began earlier."""
    if _path().exists():
        return
    rows = []
    for site in sites:
        for unit in (state.load(site["name"]) or {}).values():
            rows.append(_row(now, site["name"], unit, "tracking_started"))
    if not rows:  # nothing saved yet: still create the file so this runs only once
        _path().parent.mkdir(parents=True, exist_ok=True)
        with _path().open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writeheader()
        return
    _append(rows)


def log_events(prop, events, now, note=None):
    rows = []
    for e in events:
        extra = {}
        if "old_price" in e:
            extra["old_price"] = e["old_price"]
        if "old_available" in e:
            extra["old_available"] = e["old_available"]
        if note:
            extra["note"] = note
        rows.append(_row(now, prop, e["unit"], EVENT_NAMES[e["type"]], **extra))
    _append(rows)


def log_failure(prop, now, reason):
    _append([_row(now, prop, None, "site_failed", note=reason)])
