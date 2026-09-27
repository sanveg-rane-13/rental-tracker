"""Uses a real (truncated) copy of ApartmentList's Hudson Point page data."""
from datetime import date
from pathlib import Path

import pytest

from parsers import PARSERS

HTML = (Path(__file__).parent / "sample_apartmentlist.html").read_text()
TODAY = date(2026, 9, 27)


def units():
    return {u["unit"]: u for u in PARSERS["apartmentlist"](HTML, building="Hudson Point", today=TODAY)}


def test_units():
    u = units()
    assert set(u) == {"316", "405", "520", "302", "130", "617"}
    assert sum(1 for x in u.values() if x["beds"] == "1 Bedroom") == 5


def test_fields_match_building_site():
    u = units()
    assert u["316"] == {
        "building": "Hudson Point", "unit": "316", "beds": "1 Bedroom", "rent": None,
        "base_rent": 3353, "base_rent_max": None, "available": "Now", "sqft": 726,
        "special": None, "floor_plan": "Hudson (A13)",
    }
    assert u["405"]["available"] == "Now"          # 2026-09-25 is past -> Now
    assert u["520"]["available"] == "10/1/2026"
    assert u["617"]["beds"] == "2 Bedrooms" and u["617"]["base_rent"] == 5494


def test_missing_data_errors():
    with pytest.raises(ValueError, match="panda_entity units not found"):
        PARSERS["apartmentlist"]("<html>no data here</html>", building="X")
