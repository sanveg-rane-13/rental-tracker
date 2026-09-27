"""Parser for Equity Residential communities (equityapartments.com), e.g.
https://www.equityapartments.com/new-york-city/jersey-city/hudson-point-apartments

The unit list is drawn by JavaScript, but its data is embedded in the page source:

    ea5.unitAvailability = {"BedroomTypes":[{"BedroomCount":1,"AvailableUnits":[
        {"UnitId":"316","BuildingId":"001","AvailableDate":"9/26/2026",
         "BestTerm":{"Length":12,"Price":3353},"SqFt":726,"Bed":1,
         "FloorplanName":"Hudson (A13)","Floor":"Floor 3",
         "Special":{"Active":true,"Title":"$1,000 Security Deposit Special on Select Apartments!"},
         "EstimatedMonthlyCosts":[{"CHGCODE":"TTL","CATEGORY":"Estimated Monthly Charges",
                                   "AMOUNT":"$3480", ...}], ...}]}], ...};

Prices: "rent" is Equity's estimated total monthly charge (base rent plus required
monthly fees) when given, like Newport's total; "base_rent" is the best-term rent.
The tracker compares "rent" when present, otherwise base rent.
"""
import json
import re
from datetime import date

DATA_RE = re.compile(r"ea5\.unitAvailability\s*=\s*")


def _money(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    digits = re.sub(r"[^\d.]", "", str(value))
    return int(round(float(digits))) if digits else None


def _beds(n):
    if n is None:
        return None
    n = int(n)
    return "Studio" if n == 0 else f"{n} Bedroom" + ("s" if n > 1 else "")


def _avail(value, today):
    """'9/26/2026' -> '9/26/2026', or 'Now' if that date has passed."""
    if not value:
        return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(value))
    if not m:
        return str(value)
    mo, d, y = (int(x) for x in m.groups())
    return "Now" if date(y, mo, d) <= today else f"{mo}/{d}/{y}"


def _total(unit):
    """The 'Estimated Monthly Charges' total (CHGCODE TTL), if listed."""
    for fee in unit.get("EstimatedMonthlyCosts") or []:
        if str(fee.get("CHGCODE", "")).strip().upper() == "TTL" or \
                "estimated monthly" in str(fee.get("CATEGORY", "")).lower():
            return _money(fee.get("AMOUNT"))
    return None


def _special(unit):
    s = unit.get("Special") or {}
    if not s.get("Active") or not s.get("Title"):
        return None
    return re.sub(r"\s+on select (apartments|homes)!?$", "", s["Title"].strip(), flags=re.I)


def extract(html):
    m = DATA_RE.search(html)
    if not m:
        raise ValueError("ea5.unitAvailability not found in page - the site's layout may have changed")
    data, _ = json.JSONDecoder().raw_decode(html[m.end():])
    return data


def parse(html, building="", today=None, **_):
    today = today or date.today()
    data = extract(html)
    units = {}
    for bedroom_type in data.get("BedroomTypes") or []:
        for u in bedroom_type.get("AvailableUnits") or []:
            unit_id = str(u.get("UnitId") or "").strip()
            if not unit_id:
                continue
            bldg_id = str(u.get("BuildingId") or "").strip()
            key = (bldg_id, unit_id)
            if key in units:
                continue
            best = u.get("BestTerm") or {}
            beds = u.get("Bed", bedroom_type.get("BedroomCount"))
            units[key] = {
                "building": building,
                "unit": unit_id,
                "beds": _beds(beds),
                "rent": _total(u),
                "base_rent": _money(best.get("Price")),
                "base_rent_max": None,
                "available": _avail(u.get("AvailableDate"), today),
                "sqft": _money(u.get("SqFt")),
                "special": _special(u),
                "floor_plan": (u.get("FloorplanName") or "").strip() or None,
            }
    # A multi-building community would reuse unit numbers; prefix the building then.
    if len({b for b, _ in units}) > 1:
        for (bldg_id, _), unit in units.items():
            unit["unit"] = f"{bldg_id}-{unit['unit']}"
    return list(units.values())
