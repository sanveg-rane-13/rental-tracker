"""Uses a real copy of the data embedded in Equity's Hudson Point page (Sep 26, 2026)."""
from datetime import date
from pathlib import Path

import pytest

import state
from parsers import PARSERS

HTML = (Path(__file__).parent / "sample_equity.html").read_text()
TODAY = date(2026, 9, 25)


def units():
    return {u["unit"]: u for u in PARSERS["equity"](HTML, building="Hudson Point", today=TODAY)}


def test_units():
    u = units()
    assert set(u) == {"316", "405", "520", "302", "130", "617"}
    assert sum(1 for x in u.values() if x["beds"] == "1 Bedroom") == 5
    assert u["617"]["beds"] == "2 Bedrooms"


def test_fields_and_prices():
    u = units()
    assert u["316"] == {
        "building": "Hudson Point", "unit": "316", "beds": "1 Bedroom",
        "rent": 3480, "base_rent": 3353, "base_rent_max": None,
        "available": "9/26/2026", "sqft": 726,
        "special": "$1,000 Security Deposit Special", "floor_plan": "Hudson (A13)",
    }
    assert state.price_of(u["316"]) == 3480            # total monthly charge is compared
    assert u["520"]["special"] is None
    assert u["130"]["floor_plan"] == "Morris (A2)" and u["130"]["base_rent"] == 3718


def test_past_date_becomes_now():
    u = {x["unit"]: x for x in PARSERS["equity"](HTML, building="Hudson Point",
                                                  today=date(2026, 9, 30))}
    assert u["316"]["available"] == "Now" and u["520"]["available"] == "10/1/2026"


def test_missing_data_is_an_error():
    with pytest.raises(ValueError, match="ea5.unitAvailability not found"):
        PARSERS["equity"]("<html>{{vm.totalUnitCount}}</html>", building="Hudson Point")


def _page(units):
    import json
    data = {"BedroomTypes": [{"BedroomCount": 1, "AvailableUnits": units}]}
    return f"<script>var ea5 = ea5 || {{}}; ea5.unitAvailability = {json.dumps(data)};</script>"


def _u(unit_id, bldg, price=3000):
    return {"UnitId": unit_id, "BuildingId": bldg, "AvailableDate": "10/1/2026", "Bed": 1,
            "BestTerm": {"Length": 12, "Price": price}, "SqFt": 700}


def test_tower_prefix_is_stable():
    """A unit's label depends only on its own building, not on what else is listed."""
    alone = PARSERS["equity"](_page([_u("1203", "002")]), building="Portside Towers", today=TODAY)
    mixed = PARSERS["equity"](_page([_u("1203", "002"), _u("1203", "001"), _u("805", "1")]),
                              building="Portside Towers", today=TODAY)
    assert [u["unit"] for u in alone] == ["002-1203"]
    assert sorted(u["unit"] for u in mixed) == ["002-1203", "1203", "805"]
