from pathlib import Path

from parsers import PARSERS

HTML = (Path(__file__).parent / "sample_ironstate.html").read_text()


def units():
    return {u["unit"]: u for u in PARSERS["ironstate"](HTML, building="50 Columbus")}


def test_units_keyed_by_floorplan_id():
    u = units()
    assert set(u) == {"4775266", "5255677", "4775841", "4775864"}


def test_fields():
    u = units()
    assert u["5255677"] == {
        "building": "50 Columbus", "unit": "5255677", "beds": "1 Bedroom", "rent": None,
        "base_rent": 3535, "base_rent_max": None, "available": "10/21/2026", "sqft": 678,
        "special": None, "floor_plan": "5255677",
    }
    assert u["4775266"]["beds"] == "Studio"
    assert u["4775864"]["beds"] == "2 Bedrooms" and u["4775864"]["sqft"] == 1250
