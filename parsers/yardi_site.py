"""Parser for property websites on Yardi's RentCafe website template, e.g.
    https://www.235grand.com/floorplans/1-bedroom---1-bathroom   (one floor plan; pass beds=)
    https://www.18park.com/availableunits                       (all plans; beds read from headings)

Prefer the single-floor-plan pages with `beds` set in sites.json: reading bed
counts from the /availableunits headings depends on markup that varies by site.

Every floor plan has a heading followed by a table of its available units:

    ## 1 bed 1 bath
    | Apartment | Sq. Ft. | Rent                          | Date Available | Action |
    | #0906     | 646     | $3,720.00 to -$4,090.00       | 9/25/2026      | Apply  |

(Some buildings leave out the Sq. Ft. column.) The bed count is read from the
floor-plan heading and the text under it. A plan whose section never says how
many bedrooms it has (e.g. "Townhouse") gets beds=None, so a bedroom filter
leaves it out rather than guessing.

The rent is a range by lease term; we track the low end, like the RentCafe
parser. No fees are shown, so `rent` is None and base rent is compared.
"""
import re

from bs4 import BeautifulSoup, NavigableString

CODE_RE = re.compile(r"^#\s?([A-Z0-9][A-Z0-9-]{1,9})$", re.I)
PRICE_RE = re.compile(r"\$\s*([\d,]+)(?:\.\d{2})?(?:\s*(?:to|-)\s*-?\s*\$\s*([\d,]+)(?:\.\d{2})?)?")
SQFT_RE = re.compile(r"^\s*([\d,]{3,6})\b")
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b|\b(Now)\b", re.I)
BEDS_RE = re.compile(r"\b(?:(Studio)|(\d+)\s*-?\s*(?:Bed(?:room)?s?|BR))\b", re.I)
HEADINGS = ["h1", "h2", "h3", "h4", "h5"]


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()


def _money(s):
    return int(s.replace(",", "")) if s else None


def _code(s):
    m = CODE_RE.match(s.strip())
    return m.group(1).upper() if m else None


def _beds(match):
    if not match:
        return None
    if match.group(1):
        return "Studio"
    n = int(match.group(2))
    return f"{n} Bedroom" + ("s" if n > 1 else "")


def _find_row(node):
    el = node.parent
    for _ in range(8):
        if el is None:
            return None
        if sum(1 for s in el.find_all(string=True) if _code(s)) > 1:
            return None
        if "$" in el.get_text(" ") or DATE_RE.search(el.get_text(" ")):
            return el
        el = el.parent
    return None


def _text_after(el, start):
    parts, seen = [], False
    for s in el.strings:
        if seen:
            parts.append(s)
        elif s is start:
            seen = True
    return _clean(" ".join(parts))


def _section(node):
    """(heading text, text between that heading and the unit) for the floor plan a unit is under."""
    heading = node.find_previous(HEADINGS)
    if heading is None:
        return "", _clean(" ".join(s for s in node.find_all_previous(string=True)[::-1]))
    parts = []
    for el in heading.next_elements:
        if el is node:
            break
        if isinstance(el, NavigableString):
            parts.append(el)
    return _clean(heading.get_text(" ")), _clean(" ".join(parts))


def parse(html, building=None, beds=None):
    """beds: set this when the page is a single floor plan (e.g. /floorplans/1-bed-1-bath),
    so every unit on it gets that bed count instead of reading it from the page."""
    soup = BeautifulSoup(html, "html.parser")
    units = {}
    for node in soup.find_all(string=lambda s: s and _code(s)):
        code = _code(node)
        if code in units:
            continue
        row = _find_row(node)
        if row is None:
            continue
        after = _text_after(row, node)
        date = DATE_RE.search(after)
        if not date:
            continue
        price = PRICE_RE.search(after)
        before_price = after[: price.start()] if price else after[: date.start()]
        sqft = SQFT_RE.search(before_price)

        heading, section = _section(node)
        if beds:
            unit_beds = beds
        else:
            in_section = list(BEDS_RE.finditer(section))
            unit_beds = _beds(BEDS_RE.search(heading) or (in_section[-1] if in_section else None))

        units[code] = {
            "building": building or "",
            "unit": code,
            "beds": unit_beds,
            "rent": None,
            "base_rent": _money(price.group(1)) if price else None,
            "base_rent_max": _money(price.group(2)) if price and price.group(2) else None,
            "available": date.group(1) or "Now",
            "sqft": _money(sqft.group(1)) if sqft else None,
            "special": None,
            "floor_plan": heading or None,
        }
    return list(units.values())
