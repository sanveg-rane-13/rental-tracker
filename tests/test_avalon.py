from datetime import date
from pathlib import Path

from parsers import PARSERS

TEXT = (Path(__file__).parent / "sample_avalon.json").read_text()
TODAY = date(2026, 9, 24)


def units():
    return {u["unit"]: u for u in PARSERS["avalon"](TEXT, today=TODAY)}


def test_units_once_each():
    u = units()
    assert set(u) == {"2537", "5221", "4409", "3143"}   # 4409 is listed in two finish packages


def test_fields():
    u = units()
    assert u["5221"] == {
        "building": "Avalon Cove", "unit": "5221", "beds": "1 Bedroom", "rent": None,
        "base_rent": 3645, "base_rent_max": None, "available": "10/31/2026", "sqft": 693,
        "special": "10-month lease", "floor_plan": "A2",
    }
    assert u["2537"]["beds"] == "Studio"


def test_duplicate_keeps_lowest_price():
    u = units()
    assert u["4409"]["base_rent"] == 4105 and u["4409"]["special"] == "12-month lease"


def test_past_date_is_now_and_size_falls_back_to_plan():
    u = units()
    assert u["3143"]["available"] == "Now"       # 2026-09-20 is before "today"
    assert u["3143"]["sqft"] == 752               # no apartmentSize: plan's estimatedSize
