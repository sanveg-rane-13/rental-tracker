"""Parser for https://www.newportrentals.com/apartments-jersey-city-for-rent/

Every available unit is server-rendered into the page. A unit card reads like:

    Parkside West | Residence 1504 40 Newport Parkway
    1 Bedroom | 1 Bathroom  Floor Plan
    767 Sq Ft
    $3,389 /mo*  Base Rent: $3,376  Available Now • 0.5 Month Free

We don't depend on CSS class names (they change often). Instead we find each
"Residence <number>" text and walk up the DOM to the smallest element that
also has the price, which is that unit's card. Then we read the fields from
the card's text with regexes.
"""
import re

from bs4 import BeautifulSoup

RESIDENCE_RE = re.compile(r"Residence\s+([A-Za-z0-9-]+)")
BEDS_RE = re.compile(r"\b(Studio|\d+\s+Bedrooms?)\b", re.I)
RENT_RE = re.compile(r"\$\s*([\d,]+)\s*/\s*mo", re.I)
BASE_RENT_RE = re.compile(r"Base\s+Rent:?\s*\$\s*([\d,]+)", re.I)
AVAIL_RE = re.compile(r"Available\s+(Now|\d{1,2}/\d{1,2}/\d{2,4})", re.I)
SQFT_RE = re.compile(r"([\d,]+)\s*Sq\.?\s*Ft", re.I)
SPECIAL_RE = re.compile(r"([\d.]+\s+Months?\s+Free)", re.I)


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()


def _money(s):
    return int(s.replace(",", "")) if s else None


def _find_card(node):
    """Walk up from a 'Residence NNN' text node to the unit's card element."""
    el = node.parent
    for _ in range(12):
        if el is None:
            return None
        text = el.get_text(" ")
        if len(RESIDENCE_RE.findall(text)) > 1:
            return None  # went past the card and into the list
        if RENT_RE.search(text):
            return el
        el = el.parent
    return None


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    units = {}
    for node in soup.find_all(string=RESIDENCE_RE):
        card = _find_card(node)
        if card is None:
            continue
        text = _clean(card.get_text(" "))
        m = RESIDENCE_RE.search(text)
        building = text[: m.start()].strip(" |")
        unit = m.group(1)
        if not building or (building, unit) in units:
            continue

        beds = BEDS_RE.search(text[m.end():])
        rent = RENT_RE.search(text)
        base = BASE_RENT_RE.search(text)
        avail = AVAIL_RE.search(text)
        sqft = SQFT_RE.search(text)
        special = SPECIAL_RE.search(text)

        units[(building, unit)] = {
            "building": building,
            "unit": unit,
            "beds": _clean(beds.group(1)).title() if beds else None,
            "rent": _money(rent.group(1)) if rent else None,
            "base_rent": _money(base.group(1)) if base else None,
            "available": avail.group(1).title() if avail else None,
            "sqft": _money(sqft.group(1)) if sqft else None,
            "special": special.group(1) if special else None,
        }
    return list(units.values())
