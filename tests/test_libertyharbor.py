"""Uses a real copy of the data embedded in libertyharbor.com/availability (Sep 26, 2026)."""
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from parsers import PARSERS

HTML = (Path(__file__).parent / "sample_libertyharbor.html").read_text()
TODAY = date(2026, 9, 26)


def units():
    return {(u["building"], u["unit"]): u for u in PARSERS["libertyharbor"](HTML, today=TODAY)}


def test_all_units_and_buildings():
    u = units()
    assert len(u) == 80
    assert Counter(b for b, _ in u) == {
        "88 Regent": 20, "The Zenith": 18, "The Regent": 18, "333 Grand": 13,
        "50 Regent": 10, "The Junction": 1}
    assert sum(1 for x in u.values() if x["beds"] == "1 Bedroom") == 57


def test_fields():
    u = units()
    assert u[("The Zenith", "512")] == {
        "building": "The Zenith", "unit": "512", "beds": "1 Bedroom", "rent": None,
        "base_rent": 3254, "base_rent_max": None, "available": "Now", "sqft": 731,
        "special": "discounted", "floor_plan": None,
    }
    assert u[("The Zenith", "204")]["available"] == "10/11/2026"
    assert u[("The Zenith", "204")]["special"] is None
    assert u[("88 Regent", "PH3305")]["beds"] == "1 Bedroom"
    assert u[("88 Regent", "205")]["beds"] == "Studio"
    assert u[("The Zenith", "723")]["beds"] == "3 Bedrooms"


def test_unknown_building_uses_its_label():
    html = ('<script>const UNITS_DYNAMIC = [{"building":"77 NEW STREET (The Harbor)",'
            '"bkey":"77-new","unit":"101","beds":1,"sqft":700,"price":3000,"avail":"now"}];</script>')
    (u,) = PARSERS["libertyharbor"](html, today=TODAY)
    assert u["building"] == "The Harbor"


def test_missing_data_is_an_error_not_zero_units():
    with pytest.raises(ValueError, match="UNITS_DYNAMIC not found"):
        PARSERS["libertyharbor"]("<html>Loading availability...</html>")
