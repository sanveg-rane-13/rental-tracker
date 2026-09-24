"""Parser for RentCafe (Yardi) property pages, e.g.
https://www.rentcafe.com/apartments/nj/jersey-city/the-blvd-collection/default.aspx

Units are server-rendered, grouped under floor plans:

    B475N A1
    1 Bed / 1 Bath / 708 Sqft
    $4,030 - $4,956
    | Unit     | Base rent       | Availability |
    | MN-2503N | $4,055 - $4,866 | Now          |
    | MS-1802S | $3,780 - $4,536 | Sep 30       |

Floor plans with nothing available show "Check for available units" and no
unit rows, so they produce nothing.

The base rent is a range because it depends on lease term. We track the low
end (the best price on offer) and keep the high end for reference. RentCafe
doesn't show required monthly fees, so there is no total rent here: `rent`
is None and the tracker compares base rent instead.

Like the Newport parser, this avoids CSS class names: it finds unit codes
(e.g. "MN-2503N") and reads each unit's row and floor-plan heading from the
surrounding text.
"""
import re
from datetime import date

from bs4 import BeautifulSoup

UNIT_RE = re.compile(r"^[A-Z0-9]{1,4}-[A-Z]{0,3}\d{2,5}[A-Z]?$")
PRICE_RE = re.compile(r"\$\s*([\d,]+)(?:\s*-\s*\$\s*([\d,]+))?")
AVAIL_RE = re.compile(r"\b(Now|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b\.?\s*(\d{1,2})?", re.I)
PLAN_TAIL = (r"\s+(?P<beds>Studio|\d+\s+Beds?)\s*/\s*[\d.]+\s+Baths?\s*/\s*"
             r"(?P<sqft>[\d,]+)(?:\s*-\s*[\d,]+)?\s*Sq\s*ft")


def _plan_re(prefixes):
    if prefixes:  # e.g. "B475N A1 1 Bed / 1 Bath / 708 Sqft"
        alt = "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True))
        return re.compile(rf"(?P<plan>\b(?:{alt})\s+\S+)" + PLAN_TAIL, re.I)
    return re.compile(r"(?P<plan>[A-Z0-9][\w-]*(?:\s+[A-Z0-9][\w-]*)?)" + PLAN_TAIL)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()


def _money(s):
    return int(s.replace(",", "")) if s else None


def _beds(text):
    text = _clean(text).lower()
    if text == "studio":
        return "Studio"
    n = int(text.split()[0])
    return f"{n} Bedroom" + ("s" if n > 1 else "")


def _avail(month, day, today):
    """'Now' stays 'Now'; 'Sep 30' becomes '9/30/2026', rolling into next year when needed."""
    if month.lower() == "now":
        return "Now"
    m = MONTHS[month.lower()[:3]]
    if not day:
        return month.title()
    year = today.year
    if date(year, m, int(day)) < date.fromordinal(today.toordinal() - 60):
        year += 1  # e.g. "Jan 5" seen in November means next January
    return f"{m}/{int(day)}/{year}"


def _find_row(node):
    """Smallest ancestor of a unit code that also holds its price."""
    el = node.parent
    for _ in range(8):
        if el is None:
            return None
        text = el.get_text(" ")
        if sum(1 for s in el.find_all(string=True) if UNIT_RE.match(s.strip())) > 1:
            return None
        if "$" in text or "Contact" in text or "Call" in text:
            return el
        el = el.parent
    return None


def _find_plan(row, code, plan_re):
    """Walk up from a unit row until a floor-plan heading appears before the unit code,
    and return the closest such heading."""
    el = row.parent
    for _ in range(15):
        if el is None:
            return None
        text = _clean(el.get_text(" "))
        pos = text.find(code)
        before = [m for m in plan_re.finditer(text) if m.start() < pos]
        if before:
            return before[-1]
        el = el.parent
    return None


def parse(html, building_names=None, today=None):
    """building_names maps a floor-plan prefix to a display name, e.g. {"B475N": "BLVD 475 North"}."""
    building_names = building_names or {}
    today = today or date.today()
    plan_re = _plan_re(list(building_names))
    soup = BeautifulSoup(html, "html.parser")
    units = {}
    for node in soup.find_all(string=lambda s: s and UNIT_RE.match(s.strip())):
        code = node.strip()
        if code in units:
            continue
        row = _find_row(node)
        if row is None:
            continue
        plan = _find_plan(row, code, plan_re)
        if plan is None:
            continue

        row_text = _clean(row.get_text(" "))
        after_code = row_text.split(code, 1)[-1]
        price = PRICE_RE.search(after_code)
        avail = AVAIL_RE.search(after_code[price.end():] if price else after_code)

        plan_name = plan.group("plan").split()
        prefix = plan_name[0]
        building = building_names.get(prefix, prefix)
        unit = code.split("-", 1)[1] if building_names.get(prefix) else code

        units[code] = {
            "building": building,
            "unit": unit,
            "beds": _beds(plan.group("beds")),
            "rent": None,
            "base_rent": _money(price.group(1)) if price else None,
            "base_rent_max": _money(price.group(2)) if price and price.group(2) else None,
            "available": _avail(avail.group(1), avail.group(2), today) if avail else None,
            "sqft": _money(plan.group("sqft")),
            "special": None,
            "floor_plan": " ".join(plan_name),
        }
    return list(units.values())
