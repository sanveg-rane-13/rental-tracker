from pathlib import Path

from parsers.yardi_site import parse

HTML = (Path(__file__).parent / "sample_yardi_site.html").read_text()


def units():
    return {u["unit"]: u for u in parse(HTML, building="18 Park")}


def test_units_and_beds_by_section():
    u = units()
    # "#" in its own span (1031) isn't matched; everything else is
    assert set(u) == {"PH26", "0906", "0610", "TH2", "2112", "0517"}
    assert u["PH26"]["beds"] == "Studio"
    assert u["0906"]["beds"] == "1 Bedroom"
    assert u["2112"]["beds"] == "1 Bedroom"
    assert u["0517"]["beds"] == "2 Bedrooms"
    assert u["TH2"]["beds"] is None          # no bed count in its section: don't guess


def test_beds_given_for_single_floor_plan_page():
    u = {x["unit"]: x for x in parse(HTML, building="235 Grand", beds="1 Bedroom")}
    assert all(x["beds"] == "1 Bedroom" for x in u.values())
    assert u["2112"]["base_rent"] == 3715


def test_fields():
    u = units()
    assert u["0906"] == {
        "building": "18 Park", "unit": "0906", "beds": "1 Bedroom", "rent": None,
        "base_rent": 3720, "base_rent_max": 4090, "available": "9/25/2026", "sqft": 646,
        "special": None, "floor_plan": "1 bed 1 bath",
    }
    assert u["0610"]["available"] == "Now"
    assert u["2112"]["sqft"] is None and u["2112"]["base_rent"] == 3715   # no Sq. Ft. column
    assert u["TH2"]["sqft"] == 1100
