"""Parser for RentCafe (Yardi) property pages, e.g.
https://www.rentcafe.com/apartments/nj/jersey-city/the-blvd-collection/default.aspx
https://www.rentcafe.com/apartments/nj/jersey-city/9-regent-street-the-zenith/default.aspx

Units are server-rendered, grouped under floor plans:

    B475N A1                              ZENITH 1-BEDROOM DUPLEX PLAN G
    1 Bed / 1 Bath / 708 Sqft             1 Bed / 1 Bath / 731 Sqft
    $4,030 - $4,956                       $3,510 - $3,550
    | Unit     | Base rent       | Availability |
    | MN-2503N | $4,055 - $4,866 | Now          |      | 512 | $3,550 | Now    |
    | MS-1802S | $3,780 - $4,536 | Sep 30       |      | 712 | $3,510 | Sep 30 |

Unit codes are either prefixed ("MN-2503N", "M1-PH205") or plain ("512").
Only rows with a move-in date ("Now" or e.g. "Sep 30") count as available
units. Floor-plan summary lines like "104-105-106 ... Contact us" or plans
showing "Check for available units" are skipped.

The base rent is a range when it depends on lease term; we track the low end
and keep the high end for reference. RentCafe shows no fees, so `rent` is None
and the tracker compares base rent. "Ask for pricing" gives base_rent None.

No CSS class names are used: unit codes are found in the text, and each
unit's row and floor-plan heading are read from the surrounding text.
"""
import re
from datetime import date

from bs4 import BeautifulSoup

# "MN-2503N", "M1-PH205", "512", "1218", optionally written as "Unit 512".
# Needs a run of 3+ digits; rejects "104-105-106", "201/301", "$3,445", "1,057".
UNIT_RE = re.compile(r"^(?:(?:Unit|Apt\.?)\s+)?(?=[A-Z0-9-]*\d{3})([A-Z0-9]{1,5}(?:-[A-Z0-9]{1,6})?)$", re.I)
PRICE_RE = re.compile(r"\$\s*([\d,]+)(?:\s*-\s*\$\s*([\d,]+))?")
NO_PRICE_RE = re.compile(r"Ask for pricing|Call for (?:pricing|details)", re.I)
AVAIL_RE = re.compile(
    r"\b(Now|Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
    r"Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\.?(?:\s+(\d{1,2})\b)?")
PLAN_TAIL = (r"\s+(?P<beds>Studio|\d+\s+Beds?)\s*/\s*[\d.]+\s+Baths?\s*/\s*"
             r"(?P<sqft>[\d,]+)(?:\s*-\s*[\d,]+)?\s*Sq\s*ft")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _plan_re(prefixes):
    if prefixes:  # e.g. "B475N A1 1 Bed / 1 Bath / 708 Sqft"
        alt = "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True))
        return re.compile(rf"(?P<plan>\b(?:{alt})\s+\S+)" + PLAN_TAIL, re.I)
    # the last one or two words before the beds line, e.g. "PLAN G", "FLOOR PLAN AJ", "Regent-1Bed A7"
    return re.compile(r"(?P<plan>[A-Z0-9][\w+()-]*(?:\s+[A-Z0-9][\w+()-]*)?)" + PLAN_TAIL)


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()


def _money(s):
    return int(s.replace(",", "")) if s else None


def _code(s):
    m = UNIT_RE.match(s.strip())
    return m.group(1).upper() if m else None


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
    """Smallest ancestor of a unit code that also holds a price or 'Ask for pricing',
    without spilling into a neighbouring unit."""
    el = node.parent
    for _ in range(8):
        if el is None:
            return None
        if sum(1 for s in el.find_all(string=True) if _code(s)) > 1:
            return None
        text = el.get_text(" ")
        if "$" in text or NO_PRICE_RE.search(text):
            return el
        el = el.parent
    return None


def _text_before(el, stop):
    """Text of `el` up to (not including) the string node `stop`."""
    parts = []
    for s in el.strings:
        if s is stop:
            break
        parts.append(s)
    return _clean(" ".join(parts))


def _find_plan(row, node, plan_re):
    """Walk up until a floor-plan heading appears before the unit; return the closest one."""
    el = row.parent
    for _ in range(15):
        if el is None:
            return None
        matches = list(plan_re.finditer(_text_before(el, node)))
        if matches:
            return matches[-1]
        el = el.parent
    return None


def parse(html, building=None, building_names=None, today=None):
    """building: name for every unit on the page (one page per building).
    building_names: maps a floor-plan prefix to a building, for pages covering
    several buildings, e.g. {"B475N": "BLVD 475 North"}."""
    building_names = building_names or {}
    today = today or date.today()
    plan_re = _plan_re(list(building_names))
    soup = BeautifulSoup(html, "html.parser")
    units = {}
    for node in soup.find_all(string=lambda s: s and _code(s)):
        code = _code(node)
        if code in units:
            continue
        row = _find_row(node)
        if row is None:
            continue
        after = _clean(_text_after(row, node))
        price = PRICE_RE.search(after)
        avail = AVAIL_RE.search(after[price.end():] if price else after)
        if not avail:
            continue  # floor-plan summary line, not an available unit
        plan = _find_plan(row, node, plan_re)
        if plan is None:
            continue

        plan_name = plan.group("plan").split()
        prefix = plan_name[0]
        if building:
            bldg, unit = building, code
        elif building_names.get(prefix):
            bldg, unit = building_names[prefix], code.split("-", 1)[-1]
        else:
            bldg, unit = prefix, code

        units[code] = {
            "building": bldg,
            "unit": unit,
            "beds": _beds(plan.group("beds")),
            "rent": None,
            "base_rent": _money(price.group(1)) if price else None,
            "base_rent_max": _money(price.group(2)) if price and price.group(2) else None,
            "available": _avail(avail.group(1), avail.group(2), today),
            "sqft": _money(plan.group("sqft")),
            "special": None,
            "floor_plan": " ".join(plan_name),
        }
    return list(units.values())


def _text_after(el, start):
    """Text of `el` after the string node `start`."""
    parts, seen = [], False
    for s in el.strings:
        if seen:
            parts.append(s)
        elif s is start:
            seen = True
    return " ".join(parts)
