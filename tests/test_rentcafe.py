from datetime import date
from pathlib import Path

from parsers import PARSERS
from parsers.rentcafe import parse

HTML = (Path(__file__).parent / "sample_rentcafe.html").read_text()
TODAY = date(2026, 11, 20)


def units():
    return {u["unit"]: u for u in PARSERS["blvd"](HTML, today=TODAY)}


def test_all_units_found_with_building_names():
    u = units()
    assert set(u) == {"0901S", "2503N", "2103N", "1802S", "PH205", "1613", "0308"}
    assert u["2503N"]["building"] == "BLVD 475 North"
    assert u["1802S"]["building"] == "BLVD 475 South"
    assert u["PH205"]["building"] == "BLVD 425"
    assert u["0308"]["building"] == "BLVD 401"


def test_fields():
    u = units()
    assert u["2503N"] == {
        "building": "BLVD 475 North", "unit": "2503N", "beds": "1 Bedroom", "rent": None,
        "base_rent": 4055, "base_rent_max": 4866, "available": "Now", "sqft": 708,
        "special": None, "floor_plan": "B475N A1",
    }
    assert u["0901S"]["beds"] == "Studio"
    assert u["0308"]["beds"] == "2 Bedrooms"
    assert u["0308"]["sqft"] == 1057
    assert u["PH205"]["base_rent"] == 3600 and u["PH205"]["base_rent_max"] is None
    assert u["1613"]["sqft"] == 827


def test_dates_get_a_year():
    u = units()
    assert u["0308"]["available"] == "10/5/2026"   # recent past date stays this year
    assert u["1613"]["available"] == "1/5/2027"    # January seen in November -> next year


def test_without_building_names_keeps_raw_codes():
    u = {x["unit"]: x for x in parse(HTML, today=TODAY)}
    assert u["MN-2503N"]["building"] == "B475N"
