"""Parser for Ironstate property pages, e.g.
https://ironstate.com/property/50-columbus/

Each available floor plan is a row in the page HTML with a link to its floorplan
page carrying a numeric id, plus a one-line summary:

    Available 10/21/2026  1 Bed 1 Bath - $3,535 - 678 sq. ft. - 1 Available  Lease Now
    <a href="https://ironstate.com/property/50-columbus/floorplan/5255677">

There are no per-unit numbers, so the floorplan id is the stable key. A row can
represent several available units of that plan ("N Available"); we track the plan
at its shown (lowest) price. "price" is base rent (no fees shown), so the tracker
compares base rent.
"""
import re

from bs4 import BeautifulSoup

FP_RE = re.compile(r"/floorplan/(\d+)")
BEDS_RE = re.compile(r"(Studio|(\d+)\s*Bed)", re.I)
PRICE_RE = re.compile(r"\$\s*([\d,]+)")
SQFT_RE = re.compile(r"([\d,]+)\s*sq\.?\s*ft", re.I)
DATE_RE = re.compile(r"Available\s+(\d{1,2}/\d{1,2}/\d{4})", re.I)
COUNT_RE = re.compile(r"(\d+)\s+Available", re.I)


def _clean(t):
    return re.sub(r"\s+", " ", t).strip()


def _money(s):
    return int(s.replace(",", "")) if s else None


def _beds(text):
    m = BEDS_RE.search(text)
    if not m:
        return None
    if m.group(1).lower().startswith("studio"):
        return "Studio"
    n = int(m.group(2))
    return f"{n} Bedroom" + ("s" if n > 1 else "")


def _avail(text):
    m = DATE_RE.search(text)
    return m.group(1) if m else None


def _row_for(link):
    """Walk up from a floorplan link to the element holding its price."""
    el = link.parent
    for _ in range(8):
        if el is None:
            return None
        if len(el.find_all("a", href=FP_RE)) > 1:
            return None  # went past this row into the list
        if "$" in el.get_text(" "):
            return el
        el = el.parent
    return None


def parse(html, building="", **_):
    soup = BeautifulSoup(html, "html.parser")
    units = {}
    for link in soup.find_all("a", href=FP_RE):
        fid = FP_RE.search(link["href"]).group(1)
        if fid in units:
            continue
        row = _row_for(link)
        if row is None:
            continue
        text = _clean(row.get_text(" "))
        price = PRICE_RE.search(text)
        sqft = SQFT_RE.search(text)
        units[fid] = {
            "building": building,
            "unit": fid,
            "beds": _beds(text),
            "rent": None,
            "base_rent": _money(price.group(1)) if price else None,
            "base_rent_max": None,
            "available": _avail(text),
            "sqft": _money(sqft.group(1)) if sqft else None,
            "special": None,
            "floor_plan": fid,
        }
    return list(units.values())
