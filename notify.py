"""Push notifications through ntfy.sh. One message per property per run."""
import os

import requests

from state import price_of

NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")


def _money(n):
    return f"${n:,}" if n else "?"


def _avail(u):
    a = u.get("available")
    return "now" if (a or "").lower() == "now" else (a or "?")


def format_event(e):
    u = e["unit"]
    name = f"{u['building']} {u['unit']}"
    special = f" · {u['special']}" if u.get("special") else ""
    if e["type"] == "new":
        return f"🆕 {name}: {_money(price_of(u))}, available {_avail(u)}{special}"
    old, new = e["old_price"], price_of(u)
    arrow = "⬇️" if new < old else "⬆️"
    return f"{arrow} {name}: {_money(old)} → {_money(new)}, available {_avail(u)}{special}"


def build_message(property_name, events):
    n_new = sum(e["type"] == "new" for e in events)
    n_price = len(events) - n_new
    parts = []
    if n_new:
        parts.append(f"{n_new} new")
    if n_price:
        parts.append(f"{n_price} price change{'s' if n_price > 1 else ''}")
    title = f"{property_name}: {', '.join(parts)}"
    body = "\n".join(format_event(e) for e in events)
    return title, body


def send(topic, title, body, click_url=None):
    headers = {"Title": title.encode("utf-8"), "Tags": "house"}
    if click_url:
        headers["Click"] = click_url
    r = requests.post(f"{NTFY_SERVER}/{topic}", data=body.encode("utf-8"),
                      headers=headers, timeout=20)
    r.raise_for_status()
