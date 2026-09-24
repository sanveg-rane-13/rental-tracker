"""Parser for AvalonBay communities, using AvalonBay's apartment-search JSON
(the data behind the "Available apartments" list on avaloncommunities.com):

    https://api.avalonbay.com/json/reply/ApartmentSearch?communityCode=NJ002   (Avalon Cove)

The community code is in any unit link on the site, e.g. .../apartment/NJ002-NJ002-005-5221/.

Structure:
    results.availableFloorPlanTypes[]        one per bed count ("Studio", "1 Bedroom", ...)
      .availableFloorPlans[]                 floorPlanName, beds, ...
        .finishPackages[]                    "Classic Package", "Renovated I", ...
          .apartments[]                      apartmentNumber "005-5221", beds, apartmentSize,
                                             pricing {effectiveRent, term, availableDate}

A unit can be listed under more than one finish package; it's kept once, at its
lowest price. The price is AvalonBay's best offered rent, which depends on lease
length, so the lease term goes in "special" (e.g. "10-month lease"). Required
monthly fees aren't included, so it's treated like base rent.
"""
import json
from datetime import date


def _beds(n):
    if n is None:
        return None
    n = int(n)
    return "Studio" if n == 0 else f"{n} Bedroom" + ("s" if n > 1 else "")


def _avail(iso, today):
    """'2026-10-31' -> '10/31/2026'; today or earlier -> 'Now'."""
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return "Now" if d <= today else f"{d.month}/{d.day}/{d.year}"


def _apartments(data):
    """Yields (floor plan, apartment) pairs from the nested structure."""
    results = data.get("results") or data
    for plan_type in results.get("availableFloorPlanTypes") or []:
        for plan in plan_type.get("availableFloorPlans") or []:
            for package in plan.get("finishPackages") or []:
                for apt in package.get("apartments") or []:
                    yield plan, apt


def parse(text, building="Avalon Cove", today=None):
    today = today or date.today()
    data = json.loads(text)
    units = {}
    for plan, apt in _apartments(data):
        code = apt.get("unitKey") or apt.get("apartmentCode") or apt.get("apartmentNumber")
        if not code:
            continue
        pricing = apt.get("pricing") or {}
        price = pricing.get("effectiveRent") or pricing.get("amenitizedRent")
        price = int(round(price)) if price else None
        prev = units.get(code)
        if prev and (prev["base_rent"] or 10**9) <= (price or 10**9):
            continue  # already have this unit at the same or a lower price

        number = str(apt.get("apartmentNumber") or code)
        term = pricing.get("term")
        beds = apt.get("beds", plan.get("beds"))
        sqft = apt.get("apartmentSize") or plan.get("estimatedSize")
        units[code] = {
            "building": building,
            "unit": number.split("-")[-1],          # "005-5221" -> "5221"
            "beds": _beds(beds),
            "rent": None,
            "base_rent": price,
            "base_rent_max": None,
            "available": _avail(pricing.get("availableDate"), today),
            "sqft": int(sqft) if sqft else None,
            "special": f"{term}-month lease" if term else None,
            "floor_plan": plan.get("floorPlanName"),
        }
    return list(units.values())
