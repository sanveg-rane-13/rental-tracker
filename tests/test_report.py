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
    assert text.startswith("1 apartment(s) at or under $3,500, at least 720 sq ft")
    assert "Liberty Harbor (1)" in text
    assert "The Zenith 512: $3,450 · 731 sq ft · available 9/30/2026" in text
    assert "1 unit(s) under the rent limit with unknown size" in text


def test_ntfy_fallback_splits_long_reports(data, monkeypatch):
    (data / "report.json").write_text(json.dumps({"emails": ["you@example.com"], "max_rent": 5000}))
    sent = []
    monkeypatch.setattr(notify, "send", lambda topic, title, body, **k: sent.append((title, body)))
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.setattr(report, "NTFY_LIMIT", 120)
    monkeypatch.setattr("sys.argv", ["report.py"])
    report.main()
    assert len(sent) > 1
    assert sent[0][0].endswith(f"(1/{len(sent)})")
    assert "".join(b for _, b in sent).count("Lincoln House 405") == 1


def test_email(data, monkeypatch):
    (data / "report.json").write_text(json.dumps(
        {"emails": ["a@x.com", " b@y.com "], "max_rent": 3500, "min_sqft": None}))
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-pass")
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self): sent["tls"] = True
        def login(self, u, p): sent["login"] = (u, p)
        def send_message(self, msg): sent["msg"] = msg

    monkeypatch.setattr(report.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr("sys.argv", ["report.py", "--max-rent", "$3,500"])
    report.main()
    msg = sent["msg"]
    assert sent["server"] == ("smtp.gmail.com", 587) and sent["tls"]
    assert msg["To"] == "a@x.com, b@y.com"
    assert msg["Subject"].startswith("Apartments at or under $3,500: 3 found")
    parts = {p.get_content_type(): p for p in msg.walk()}
    assert "Lincoln House" in parts["text/html"].get_content()
    assert parts["text/csv"].get_filename() == "report.csv"


def test_number_parsing():
    assert report._number("$3,500") == 3500
    with pytest.raises(Exception):
        report._number("cheap")
