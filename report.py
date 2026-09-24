#!/usr/bin/env python3
"""On-demand report: every currently listed unit (from data/*.json) at or under a rent
limit, optionally with a minimum size, sent by email (or to ntfy if email isn't set up).

Settings come from report.json and can be overridden per run:
    python report.py                               # use report.json
    python report.py --max-rent 3600 --min-sqft 650
    python report.py --dry-run                     # print only, send nothing

Email uses SMTP (e.g. Gmail with an app password), from these environment variables:
    SMTP_USER, SMTP_PASSWORD         required for email
    SMTP_HOST, SMTP_PORT             optional, default smtp.gmail.com / 587
If they're missing, the report goes to the ntfy topic in NTFY_TOPIC instead.
"""
import argparse
import csv
import html
import json
import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import notify
import state

ROOT = Path(__file__).parent
OUT = ROOT / "output"
NY = ZoneInfo("America/New_York")
NTFY_LIMIT = 3800  # ntfy messages max out around 4 KB; longer reports are split


def load_units():
    """Every unit in every property's saved file, tagged with its property name."""
    units = []
    for path in sorted(state.DATA.glob("*.json")):
        doc = json.loads(path.read_text())
        for u in doc["units"].values():
            units.append({**u, "property": doc.get("property", path.stem)})
    return units


def select(units, max_rent, min_sqft=None):
    """(matches sorted by price, count skipped because size is unknown)."""
    matches, unknown_size = [], 0
    for u in units:
        price = state.price_of(u)
        if price is None or price > max_rent:
            continue
        if min_sqft:
            if not u.get("sqft"):
                unknown_size += 1
                continue
            if u["sqft"] < min_sqft:
                continue
        matches.append(u)
    matches.sort(key=lambda u: (state.price_of(u), u["property"], u["building"], u["unit"]))
    return matches, unknown_size


def _money(n):
    return f"${n:,}" if n else "?"


def _avail(u):
    a = u.get("available") or "?"
    return "now" if a.lower() == "now" else a


def _sqft(u):
    return f"{u['sqft']:,}" if u.get("sqft") else "–"


def describe(max_rent, min_sqft):
    s = f"at or under {_money(max_rent)}"
    return s + (f", at least {min_sqft:,} sq ft" if min_sqft else "")


def text_line(u):
    size = f" · {u['sqft']:,} sq ft" if u.get("sqft") else ""
    special = f" · {u['special']}" if u.get("special") else ""
    return (f"{u['building']} {u['unit']}: {_money(state.price_of(u))}{size}"
            f" · available {_avail(u)}{special}")


def text_report(matches, max_rent, min_sqft, unknown_size):
    lines = [f"{len(matches)} apartment(s) {describe(max_rent, min_sqft)}", ""]
    by_property = {}
    for u in matches:
        by_property.setdefault(u["property"], []).append(u)
    for prop, units in sorted(by_property.items()):
        lines.append(f"{prop} ({len(units)})")
        lines += [f"  {text_line(u)}" for u in units]
        lines.append("")
    if unknown_size:
        lines.append(f"Not included: {unknown_size} unit(s) under the rent limit with unknown size.")
    return "\n".join(lines).rstrip() + "\n"


def html_report(matches, max_rent, min_sqft, unknown_size):
    th = "text-align:left;padding:6px 10px;border-bottom:2px solid #ccc"
    td = "padding:6px 10px;border-bottom:1px solid #eee"
    rows = "".join(
        f"<tr><td style='{td}'>{html.escape(u['property'])}</td>"
        f"<td style='{td}'>{html.escape(u['building'])}</td>"
        f"<td style='{td}'>{html.escape(u['unit'])}</td>"
        f"<td style='{td};text-align:right'>{_money(state.price_of(u))}</td>"
        f"<td style='{td};text-align:right'>{_sqft(u)}</td>"
        f"<td style='{td}'>{html.escape(_avail(u))}</td>"
        f"<td style='{td}'>{html.escape(u.get('special') or '')}</td>"
        f"<td style='{td}'>{html.escape(u.get('first_seen') or '')}</td></tr>"
        for u in matches)
    head = "".join(f"<th style='{th}'>{h}</th>" for h in
                   ["Property", "Building", "Unit", "Rent", "Sq ft", "Available", "Special", "Tracked since"])
    note = (f"<p style='color:#666'>Not included: {unknown_size} unit(s) under the rent limit "
            f"with unknown size.</p>" if unknown_size else "")
    return (f"<div style='font-family:-apple-system,Segoe UI,Arial,sans-serif;font-size:14px'>"
            f"<p><b>{len(matches)} apartment(s) {html.escape(describe(max_rent, min_sqft))}</b></p>"
            f"<table style='border-collapse:collapse'><thead><tr>{head}</tr></thead>"
            f"<tbody>{rows}</tbody></table>{note}"
            f"<p style='color:#666'>Rent is total monthly rent where the site shows it (Newport), "
            f"otherwise the lowest base rent.</p></div>")


def write_csv(matches, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["property", "building", "unit", "beds", "price", "base_rent", "base_rent_max", "rent",
            "sqft", "available", "special", "floor_plan", "first_seen"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for u in matches:
            w.writerow({**u, "price": state.price_of(u)})


def send_email(recipients, subject, text, html_body, csv_path):
    user, password = os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or 587)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(recipients)
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(csv_path.read_bytes(), maintype="text", subtype="csv", filename=csv_path.name)
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)


def ntfy_chunks(text):
    """Split the text report into ntfy-sized messages on line boundaries."""
    chunks, cur = [], ""
    for line in text.splitlines(keepends=True):
        if len((cur + line).encode("utf-8")) > NTFY_LIMIT and cur:
            chunks.append(cur)
            cur = ""
        cur += line
    if cur:
        chunks.append(cur)
    return chunks


def _number(s):
    """Accepts '3500', '$3,500', ' 3500 '."""
    cleaned = s.replace("$", "").replace(",", "").strip()
    if not cleaned.isdigit():
        raise argparse.ArgumentTypeError(f"not a whole number: {s!r}")
    return int(cleaned)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rent", type=_number, help="override report.json max_rent")
    ap.add_argument("--min-sqft", type=_number, help="override report.json min_sqft (0 = none)")
    ap.add_argument("--dry-run", action="store_true", help="print only, send nothing")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "report.json").read_text())
    max_rent = args.max_rent or cfg.get("max_rent")
    min_sqft = args.min_sqft if args.min_sqft is not None else cfg.get("min_sqft")
    if not max_rent:
        sys.exit("No max_rent: set it in report.json or pass --max-rent")

    matches, unknown_size = select(load_units(), max_rent, min_sqft or None)
    text = text_report(matches, max_rent, min_sqft, unknown_size)
    stamp = datetime.now(NY).strftime("%Y-%m-%d %H:%M")
    subject = f"Apartments {describe(max_rent, min_sqft)}: {len(matches)} found ({stamp})"
    csv_path = OUT / "report.csv"
    write_csv(matches, csv_path)
    print(subject + "\n\n" + text)
    if args.dry_run:
        return

    recipients = [e.strip() for e in cfg.get("emails", []) if e.strip() and "example.com" not in e]
    if recipients and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        send_email(recipients, subject, text, html_report(matches, max_rent, min_sqft, unknown_size),
                   csv_path)
        print(f"Emailed to {', '.join(recipients)}")
        return

    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        sys.exit("Nothing sent: set up email (SMTP_USER / SMTP_PASSWORD secrets and emails in "
                 "report.json) or NTFY_TOPIC.")
    why = "no email addresses in report.json" if not recipients else "SMTP secrets not set"
    print(f"Sending to ntfy instead of email ({why})")
    chunks = ntfy_chunks(text)
    for i, chunk in enumerate(chunks, 1):
        title = f"Report: {len(matches)} apartment(s) {describe(max_rent, min_sqft)}"
        if len(chunks) > 1:
            title += f" ({i}/{len(chunks)})"
        notify.send(topic, title, chunk)
    print(f"Sent {len(chunks)} ntfy message(s)")


if __name__ == "__main__":
    main()
