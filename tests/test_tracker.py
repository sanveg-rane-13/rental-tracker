"""End-to-end: seed run, then a run with changes, checking what gets notified."""
import json

import csv
from datetime import datetime, timezone

import history
import notify
import state
import tracker

NOW = datetime(2026, 9, 24, 14, 15, tzinfo=timezone.utc)   # 10:15 in New York

SITE = {"name": "Test Rentals", "url": "https://example.com", "parser": "fake",
        "beds": ["1 Bedroom"], "max_rent": 4000}


def unit(b, n, rent, beds="1 Bedroom", avail="Now"):
    return {"building": b, "unit": n, "beds": beds, "rent": rent, "base_rent": rent - 40,
            "available": avail, "sqft": 700, "special": None}


def run(monkeypatch, tmp_path, units):
    monkeypatch.setattr(state, "DATA", tmp_path / "data")
    monkeypatch.setattr(tracker, "OUT", tmp_path / "out")
    monkeypatch.setattr(tracker, "fetch", lambda url: "<html/>")
    monkeypatch.setitem(tracker.PARSERS, "fake", lambda html: units)
    sent = []
    monkeypatch.setattr(notify, "send", lambda *a, **k: sent.append(a))
    _, ok = tracker.process_site(SITE, "topic", True, NOW)
    assert ok
    return sent


BASE = [unit("A", "101", 3500), unit("A", "102", 4100), unit("B", "201", 3900),
        unit("B", "202", 3700), unit("C", "301", 2800, beds="Studio")] + \
       [unit("Z", str(i), 3000 + i) for i in range(10)]


def test_first_run_is_silent_and_saves(monkeypatch, tmp_path):
    assert run(monkeypatch, tmp_path, BASE) == []
    saved = json.loads((tmp_path / "data" / "test-rentals.json").read_text())["units"]
    assert "A|102" in saved            # over-budget units are remembered too
    assert "C|301" not in saved        # studios filtered out


def test_changes(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, BASE)
    changed = [u for u in BASE if (u["building"], u["unit"]) != ("B", "202")]  # 202 rented
    changed = [dict(u) for u in changed]
    by = {(u["building"], u["unit"]): u for u in changed}
    by[("A", "102")]["rent"] = 3950    # over budget -> under: notify as price drop
    by[("B", "201")]["rent"] = 4200    # under -> over: silent
    by[("A", "101")]["available"] = "10/1/2026"  # only availability changed: silent
    changed.append(unit("D", "401", 3600))       # new, in budget: notify
    changed.append(unit("D", "402", 4500))       # new, over budget: silent

    sent = run(monkeypatch, tmp_path, changed)
    assert len(sent) == 1
    _, title, body = sent[0]
    assert title == "Test Rentals: 1 new, 1 price change"
    assert "🆕 D 401: $3,600, available now" in body
    assert "⬇️ A 102: $4,100 → $3,950" in body
    assert "402" not in body and "201" not in body

    saved = json.loads((tmp_path / "data" / "test-rentals.json").read_text())["units"]
    assert "B|202" not in saved
    assert saved["A|102"]["price_history"] == [
        {"date": "2026-09-24", "price": 4100}, {"date": "2026-09-24", "price": 3950}]

    assert run(monkeypatch, tmp_path, changed) == []   # nothing changed -> nothing sent


def test_base_rent_only_and_missing_price(monkeypatch, tmp_path):
    """Sites like BLVD have rent=None and only base_rent; some units may have no price at all."""
    def base_only(b, n, base):
        u = unit(b, n, 3000)
        u.update(rent=None, base_rent=base)
        return u

    first = BASE + [base_only("E", "501", 3600), base_only("E", "502", None)]
    run(monkeypatch, tmp_path, first)

    later = [dict(u) for u in first] + [base_only("E", "503", None)]  # new, no price: silent
    by = {(u["building"], u["unit"]): u for u in later}
    by[("E", "501")]["base_rent"] = 3500      # base-rent drop: notify
    by[("E", "502")]["base_rent"] = 3650      # price appears: notify
    sent = run(monkeypatch, tmp_path, later)
    body = sent[0][2]
    assert "⬇️ E 501: $3,600 → $3,500" in body
    assert "💲 E 502: now priced at $3,650" in body
    assert "503" not in body

    by[("E", "503")]["base_rent"] = 3400      # its price appears later: notify then
    sent = run(monkeypatch, tmp_path, later)
    assert "💲 E 503: now priced at $3,400" in sent[0][2]


def test_multi_page_site(monkeypatch, tmp_path):
    from pathlib import Path
    import pytest
    html = (Path(__file__).parent / "sample_rentcafe_plain.html").read_text()
    site = {"name": "Liberty Harbor", "parser": "rentcafe", "link": "https://example.com/avail",
            "beds": ["1 Bedroom"], "max_rent": 3700,
            "pages": [{"building": "The Zenith", "url": "https://a"},
                      {"building": "The Regent", "url": "https://b"}]}
    monkeypatch.setattr(tracker, "OUT", tmp_path / "out")
    monkeypatch.setattr(tracker, "fetch", lambda url: html)
    units = tracker.scrape(site)
    keys = {state.unit_key(u) for u in units}
    assert {"The Zenith|512", "The Regent|512", "The Zenith|906"} <= keys
    assert len(units) == 6                       # 3 one-bed units x 2 pages
    assert tracker.link_of(site) == "https://example.com/avail"

    def flaky(url):
        if url == "https://b":
            raise RuntimeError("HTTP 503")
        return html
    monkeypatch.setattr(tracker, "fetch", flaky)
    with pytest.raises(RuntimeError):            # one page down -> whole site skipped
        tracker.scrape(site)


def test_parse_collapse_does_not_overwrite(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, BASE)
    monkeypatch.setitem(tracker.PARSERS, "fake", lambda html: BASE[:2])
    _, ok = tracker.process_site(SITE, "topic", True, NOW)
    assert not ok
    saved = json.loads((tmp_path / "data" / "test-rentals.json").read_text())["units"]
    assert len(saved) == 14


def read_log(tmp_path):
    with (tmp_path / "data" / "history" / "events.csv").open() as f:
        return list(csv.DictReader(f))


def test_history_log(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, BASE)                       # first run: all 1-beds "listed"
    rows = read_log(tmp_path)
    assert len(rows) == 14 and {r["event"] for r in rows} == {"listed"}
    assert rows[0]["time_utc"] == "2026-09-24T14:15" and rows[0]["time_ny"] == "2026-09-24 10:15"
    assert rows[0]["note"] == "first run"

    later = [dict(u) for u in BASE if (u["building"], u["unit"]) != ("B", "202")]
    by = {(u["building"], u["unit"]): u for u in later}
    by[("A", "102")]["rent"] = 4000
    by[("A", "101")]["available"] = "10/1/2026"
    run(monkeypatch, tmp_path, later)

    new_rows = read_log(tmp_path)[14:]
    got = {(r["event"], r["building"], r["unit"]) for r in new_rows}
    assert got == {("price_change", "A", "102"), ("available_change", "A", "101"),
                   ("delisted", "B", "202")}
    pc = next(r for r in new_rows if r["event"] == "price_change")
    assert (pc["price"], pc["old_price"]) == ("4000", "4100")
    ac = next(r for r in new_rows if r["event"] == "available_change")
    assert (ac["available"], ac["old_available"]) == ("10/1/2026", "Now")
    dl = next(r for r in new_rows if r["event"] == "delisted")
    assert dl["price"] == "3700"                           # last known price


def test_history_starts_with_snapshot_of_existing_state(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, BASE)
    (tmp_path / "data" / "history" / "events.csv").unlink()   # as if upgrading from before the log
    history.ensure_started([SITE, {"name": "Never Run"}], NOW)
    rows = read_log(tmp_path)
    assert len(rows) == 14 and {r["event"] for r in rows} == {"tracking_started"}
    history.ensure_started([SITE], NOW)                        # only ever once
    assert len(read_log(tmp_path)) == 14
