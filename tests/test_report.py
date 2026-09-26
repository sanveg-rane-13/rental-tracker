import json

import pytest

import notify
import report
import state


def unit(b, n, rent=None, base=None, sqft=None, avail="Now"):
    return {"building": b, "unit": n, "beds": "1 Bedroom", "rent": rent, "base_rent": base,
            "available": avail, "sqft": sqft, "special": None, "first_seen": "2026-09-24"}


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "DATA", tmp_path / "data")
    monkeypatch.setattr(report, "OUT", tmp_path / "out")
    monkeypatch.setattr(report, "ROOT", tmp_path)
    state.save("Newport Rentals", {
        "A|1": unit("Lincoln House", "405", rent=3064, base=3051, sqft=700),
        "A|2": unit("Atlantic", "2810", rent=3904, base=3856, sqft=899),     # over 3500
    })
    state.save("Liberty Harbor", {
        "Z|512": unit("The Zenith", "512", base=3450, sqft=731, avail="9/30/2026"),
        "Z|600": unit("The Zenith", "600", base=3300),                        # size unknown
        "Z|700": unit("The Zenith", "700", base=None, sqft=650),              # no price
    })
    (state.DATA / "history").mkdir()
    (state.DATA / "history" / "events.csv").write_text("not,a,state,file\n")  # must be ignored
    return tmp_path


def test_select_by_rent_and_size(data):
    units = report.load_units()
    assert len(units) == 5
    m, unknown = report.select(units, 3500)
    assert [u["unit"] for u in m] == ["405", "600", "512"]   # sorted by price
    m, unknown = report.select(units, 3500, min_sqft=720)
    assert [u["unit"] for u in m] == ["512"] and unknown == 1


def test_text_report(data):
    m, unknown = report.select(report.load_units(), 3500, 720)
    text = report.text_report(m, 3500, 720, unknown)
    assert text.startswith("1 apartment up to $3,500, 720+ sq ft\n1 property · cheapest $3,450 (Liberty Harbor)")
    assert "━━ LIBERTY HARBOR · 1 ━━\n$3,450 · The Zenith 512 · 731 sq ft · Sep 30" in text
    assert "(1 unit under the rent limit left out: size unknown)" in text


def test_long_reports_are_split(data, monkeypatch):
    (data / "report.json").write_text(json.dumps({"max_rent": 5000}))
    sent = []
    monkeypatch.setattr(notify, "send", lambda topic, title, body, **k: sent.append((title, body)))
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setattr(report, "NTFY_LIMIT", 120)
    monkeypatch.setattr("sys.argv", ["report.py"])
    report.main()
    assert len(sent) > 1
    assert sent[0][0].endswith(f"(1/{len(sent)})")
    assert "".join(b for _, b in sent).count("Lincoln House 405") == 1



def test_number_parsing():
    assert report._number("$3,500") == 3500
    with pytest.raises(Exception):
        report._number("cheap")


def test_ntfy_report_with_overrides(data, monkeypatch):
    (data / "report.json").write_text(json.dumps({"max_rent": 3000, "min_sqft": 800}))
    sent = []
    monkeypatch.setattr(notify, "send", lambda topic, title, body, **k: sent.append((title, body)))
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setattr("sys.argv", ["report.py", "--max-rent", "$3,500", "--min-sqft", "0"])
    report.main()
    assert len(sent) == 1
    title, body = sent[0]
    assert title == "Report: 3 apartments up to $3,500"
    assert title.isascii()
    assert "$3,064 · Lincoln House 405 · 700 sq ft · now" in body
    assert (data / "out" / "report.csv").exists()


def test_sections_ordered_by_cheapest_and_single_building_short_form(data):
    state.save("18 Park", {"18|0610": {**unit("18 Park", "0610", base=2900, sqft=651)}})
    m, _ = report.select(report.load_units(), 3500)
    text = report.text_report(m, 3500, None, 0)
    sections = [line for line in text.splitlines() if line.startswith("━━")]
    assert sections == ["━━ 18 PARK · 1 ━━", "━━ NEWPORT RENTALS · 1 ━━", "━━ LIBERTY HARBOR · 2 ━━"]
    assert "$2,900 · #0610 · 651 sq ft · now" in text     # building name not repeated


def test_empty_report(data):
    assert report.text_report([], 1000, None, 0) == "No apartments up to $1,000 right now.\n"


def test_chunks_keep_sections_together(monkeypatch):
    monkeypatch.setattr(report, "NTFY_LIMIT", 60)
    text = "summary line\n\n━━ A · 2 ━━\n$1 · a\n$2 · b\n\n━━ B · 1 ━━\n$3 · c\n"
    chunks = report.ntfy_chunks(text)
    assert all(len(c.encode()) <= 60 for c in chunks)
    assert any("━━ A · 2 ━━\n$1 · a\n$2 · b" in c for c in chunks)   # section A not split
    assert "".join(chunks).count("$") == 3


def test_skip_buildings(data, monkeypatch):
    (data / "report.json").write_text(json.dumps(
        {"max_rent": 3500, "skip_buildings": ["lincoln house ", "Parkside East"]}))
    sent = []
    monkeypatch.setattr(notify, "send", lambda topic, title, body, **k: sent.append((title, body)))
    monkeypatch.setenv("NTFY_TOPIC", "t")

    monkeypatch.setattr("sys.argv", ["report.py"])                    # checkbox on (default)
    report.main()
    title, body = sent[-1]
    assert title == "Report: 2 apartments up to $3,500"
    assert "Lincoln House" not in body.split("(")[0]
    assert "(1 unit in excluded buildings not shown)" in body

    monkeypatch.setattr("sys.argv", ["report.py", "--include-all"])   # checkbox off
    report.main()
    title, body = sent[-1]
    assert title == "Report: 3 apartments up to $3,500"
    assert "Lincoln House 405" in body and "excluded" not in body


def test_skip_list_optional(data):
    units = report.load_units()
    assert report.skip_buildings(units, None) == (units, 0)
    assert report.skip_buildings(units, ["", "  "]) == (units, 0)
