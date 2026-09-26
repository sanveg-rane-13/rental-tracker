"""Parser for https://www.libertyharbor.com/availability/

The page's list is filled in by JavaScript, but the data itself is embedded in the
page source, so a plain download has it:

    <script>
      const UNITS_DYNAMIC = [{"id":"5089-512","building":"9 REGENT STREET (The Zenith)",
          "bkey":"9-regent-street-the-zenith","unit":"512","beds":1,"baths":1,"sqft":731,
          "price":3254,"avail":"now","has_discount":true, ...}, ...];
      const BUILDINGS_DYNAMIC = {...};
    </script>

One download covers every Liberty Harbor building, including the Brownstones.

"price" is what libertyharbor.com advertises. For units with "has_discount" it
appears to be the net effective rent (a promotion averaged over the lease), which
is lower than the base rent RentCafe shows; those units get special="discounted".
"""
import json
import re
from datetime import date

# Same names the RentCafe-based setup used, so units saved before keep matching.
BUILDINGS = {
    "9-regent-street-the-zenith": "The Zenith",
    "30-regent-street-the-regent": "The Regent",
    "50-regent-street": "50 Regent",
    "88-regent-street": "88 Regent",
    "333-grand-street": "333 Grand",
    "123-river-street-the-junction": "The Junction",
    "112-tidewater-street-the-brownstone-residential": "Brownstones 112 Tidewater",
    "115-liberty-view-drive-the-brownstone-residential": "Brownstones 115 Liberty View",
}


def _building(u):
    if u.get("bkey") in BUILDINGS:
        return BUILDINGS[u["bkey"]]
    label = u.get("building") or u.get("bkey") or "?"
    m = re.search(r"\((.+?)\)", label)          # "9 REGENT STREET (The Zenith)" -> "The Zenith"
    return m.group(1) if m else label.title()


def _beds(n):
    if n is None:
        return None
    n = int(n)
    return "Studio" if n == 0 else f"{n} Bedroom" + ("s" if n > 1 else "")


def _avail(value, today):
    if not value or str(value).lower() == "now":
        return "Now"
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return "Now" if d <= today else f"{d.month}/{d.day}/{d.year}"


def extract_units(html):
    """The UNITS_DYNAMIC array from the page source."""
    m = re.search(r"UNITS_DYNAMIC\s*=\s*", html)
    if not m:
        raise ValueError("UNITS_DYNAMIC not found in page - the site's layout may have changed")
    units, _ = json.JSONDecoder().raw_decode(html[m.end():])
    return units


def parse(html, today=None, **_):
    today = today or date.today()
    out = {}
    for u in extract_units(html):
        building, unit = _building(u), str(u.get("unit") or "").strip()
        if not unit or (building, unit) in out:
            continue
        price = u.get("price")
        out[(building, unit)] = {
            "building": building,
            "unit": unit,
            "beds": _beds(u.get("beds")),
            "rent": None,
            "base_rent": int(round(price)) if price else None,
            "base_rent_max": None,
            "available": _avail(u.get("avail"), today),
            "sqft": int(u["sqft"]) if u.get("sqft") else None,
            "special": "discounted" if u.get("has_discount") else None,
            "floor_plan": None,
        }
    return list(out.values())
