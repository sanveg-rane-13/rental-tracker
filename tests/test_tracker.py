"""End-to-end: seed run, then a run with changes, checking what gets notified."""
import json

import notify
import state
import tracker

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
    _, ok = tracker.process_site(SITE, "topic", True, "2026-09-24")
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


def test_parse_collapse_does_not_overwrite(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, BASE)
    monkeypatch.setitem(tracker.PARSERS, "fake", lambda html: BASE[:2])
    _, ok = tracker.process_site(SITE, "topic", True, "2026-09-24")
    assert not ok
    saved = json.loads((tmp_path / "data" / "test-rentals.json").read_text())["units"]
    assert len(saved) == 14
