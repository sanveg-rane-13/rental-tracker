"""Parser for ApartmentList property pages, e.g.
https://www.apartmentlist.com/nj/jersey-city/hudson-point

Used as a fallback source for buildings whose own site blocks GitHub's IP (the Equity
buildings). ApartmentList is a Next.js app; the availability data streams inside
<script>self.__next_f.push([...])</script> as an escaped JS string containing, among
other things, a "panda_entity" record:

    "schema":"...panda_entity...","data":{"rental_id":"p14252","units":[
        {"unit_id":"316","floorplan_id":"Hudson (A13)","bed_count":1,"bath_count":1,
         "date_available":"2026-09-25","price":3353,"sq_ft":726}, ...]}

We unescape the payload and read that array. Unit numbers match the building's own
site (316, 405, ...), so keys stay consistent. "price" is base rent (no fees), so the
tracker compares base rent.
"""
import json
import re
from datetime import date

# panda_entity, then its "units": [ ... ]. Other blocks (priceToFloorplans) also have a
# "units" key but with different fields, so we anchor on panda_entity to get the clean one.
UNITS_RE = re.compile(r'panda_entity.*?"units"\s*:\s*\[', re.S)


def _unescape(html):
    """The availability data lives inside a JS string, so quotes/slashes are escaped.
    Undo that so the embedded JSON can be parsed, even if the page is truncated after it."""
    return html.replace('\\"', '"').replace('\\/', '/')


def _beds(n):
    if n is None:
        return None
    n = int(n)
    return "Studio" if n == 0 else f"{n} Bedroom" + ("s" if n > 1 else "")


def _avail(value, today):
    if not value:
        return "Now"
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return "Now" if d <= today else f"{d.month}/{d.day}/{d.year}"


def extract_units(html):
    text = _unescape(html)
    m = UNITS_RE.search(text)
    if not m:
        raise ValueError("panda_entity units not found - ApartmentList layout may have changed")
    start = text.index("[", m.end() - 1)
    array, _ = json.JSONDecoder().raw_decode(text[start:])
    return array


def parse(html, building="", today=None, **_):
    today = today or date.today()
    out = {}
    for u in extract_units(html):
        unit_id = str(u.get("unit_id") or "").strip()
        if not unit_id or unit_id in out:
            continue
        price = u.get("price")
        out[unit_id] = {
            "building": building,
            "unit": unit_id,
            "beds": _beds(u.get("bed_count")),
            "rent": None,
            "base_rent": int(round(price)) if price else None,
            "base_rent_max": None,
            "available": _avail(u.get("date_available"), today),
            "sqft": int(u["sq_ft"]) if u.get("sq_ft") else None,
            "special": None,
            "floor_plan": u.get("floorplan_id") or None,
        }
    return list(out.values())
