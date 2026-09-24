from pathlib import Path

from parsers.newport import parse

HTML = (Path(__file__).parent / "sample_newport.html").read_text()


def by_key(units):
    return {(u["building"], u["unit"]): u for u in units}


def test_finds_all_units_once():
    units = by_key(parse(HTML))
    assert set(units) == {
        ("Parkside West", "1504"),
        ("Lincoln House", "405"),
        ("Parkside East", "2007"),
        ("Ellipse", "2007"),
        ("Pacific", "303"),
    }


def test_fields():
    u = by_key(parse(HTML))
    assert u[("Lincoln House", "405")] == {
        "building": "Lincoln House", "unit": "405", "beds": "1 Bedroom",
        "rent": 3064, "base_rent": 3051, "available": "10/18/2026",
        "sqft": 700, "special": "0.5 Month Free",
    }
    assert u[("Parkside West", "1504")]["beds"] == "Studio"
    assert u[("Parkside West", "1504")]["available"] == "Now"
    assert u[("Parkside East", "2007")]["rent"] == 3394
    assert u[("Parkside East", "2007")]["available"] == "11/6/2026"
    assert u[("Pacific", "303")]["beds"] == "2 Bedrooms"
