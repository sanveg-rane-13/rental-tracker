"""Per-property memory of units already seen, stored as data/<property-slug>.json.

Every unit that passes the bedroom filter is stored, including ones over
budget, so a later price drop into budget is reported as a drop and not as a
new listing.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent / "data"


def slug(name):
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def unit_key(u):
    return f"{u['building']}|{u['unit']}"


def price_of(u):
    """The price we compare and filter on: the total monthly rent (base rent + required
    monthly fees), falling back to base rent if a site only lists that."""
    return u.get("rent") or u.get("base_rent")


def path_for(property_name):
    return DATA / f"{slug(property_name)}.json"


def load(property_name):
    """Returns the saved units dict, or None if this property has never been saved."""
    p = path_for(property_name)
    if not p.exists():
        return None
    return json.loads(p.read_text())["units"]


def save(property_name, units):
    DATA.mkdir(exist_ok=True)
    doc = {
        "property": property_name,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "units": dict(sorted(units.items())),
    }
    path_for(property_name).write_text(json.dumps(doc, indent=2) + "\n")


def diff(old, scraped, today):
    """Compare saved units with a fresh scrape.

    Returns (new_state, events). Events are dicts with type "new" or "price",
    before any budget filter is applied.
    """
    new_state, events = {}, []
    for u in scraped:
        key = unit_key(u)
        prev = old.get(key)
        rec = {k: u.get(k) for k in
               ("building", "unit", "beds", "rent", "base_rent", "available", "sqft", "special")}
        if prev is None:
            rec["first_seen"] = today
            rec["price_history"] = [{"date": today, "price": price_of(u)}]
            events.append({"type": "new", "unit": rec})
        else:
            rec["first_seen"] = prev.get("first_seen", today)
            rec["price_history"] = list(prev.get("price_history", []))
            old_price, new_price = price_of(prev), price_of(u)
            # A price appearing on a unit that had none (old_price None) also counts.
            if new_price and new_price != old_price:
                rec["price_history"].append({"date": today, "price": new_price})
                events.append({"type": "price", "unit": rec, "old_price": old_price})
        new_state[key] = rec
    return new_state, events
