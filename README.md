# Rental tracker

Checks rental listing pages every hour and sends a push notification (via [ntfy](https://ntfy.sh)) when a unit within budget is newly listed or changes price.

## How it works

1. `tracker.py` fetches each site in `sites.json` and parses its units with the matching parser in `parsers/`.
2. Only units matching `beds` are kept.
3. The units are compared with `data/<property>.json`, which holds every unit seen before, including over-budget ones.
4. You're notified (one message per property per run) when:
   - a **new unit** appears at or under `max_rent`
   - a known unit's **price changes** and the new price is at or under `max_rent` (e.g. $4,079 → $3,950)
5. The updated `data/*.json` files are committed back to the repo, so the commit history doubles as a price history.

Which price is compared depends on what the site shows:

| Property | Parser | Price used |
|---|---|---|
| Newport Rentals | `newport` | Total monthly rent (base + required fees), e.g. $3,064/mo rather than $3,051 base |
| BLVD Collection | `blvd` (RentCafe page) | Base rent, lowest lease-term price (RentCafe shows "$4,055 - $4,866" and no fees) |
| Liberty Harbor | `rentcafe` (one RentCafe page per building) | Base rent, as above |
| 235 Grand, 18 Park | `yardi_site` (the building's own `/availableunits` page) | Base rent, low end of "$3,720.00 to $4,090.00" |

Stays silent for: availability-date changes, price changes that end over budget, units being delisted, and the **first run for a property** (it just records what's there).

Safety checks:
- A site that parses 0 units, or fewer than half of what was saved, is treated as a parser problem: nothing is saved or sent for it, and the run fails so you notice.
- On GitHub Actions, the run refuses to proceed if `NTFY_TOPIC` isn't set, so no changes are recorded as seen without being notified.

## Setup

1. **Phone:** install the ntfy app from the App Store and subscribe to a topic with a hard-to-guess name, e.g. `rentals-7f3k9q2m`. (Anyone who knows the topic name can read it, so don't use something like `rentals`.)
2. **GitHub:** in the repo, go to **Settings → Secrets and variables → Actions → New repository secret**. Name: `NTFY_TOPIC`, value: your topic name.
3. Push this code. The workflow runs hourly by itself; you can also start it from **Actions → Rental tracker → Run workflow**.

The first run saves `data/newport-rentals.json` and sends nothing. Later runs notify on changes.

## Configuration: `sites.json`

```json
{
  "name": "Newport Rentals",
  "url": "https://www.newportrentals.com/apartments-jersey-city-for-rent/",
  "parser": "newport",
  "beds": ["1 Bedroom"],
  "max_rent": 4000
}
```

- `name` is shown in notifications and sets the data file name (`data/newport-rentals.json`).
- A property spread over several pages uses `pages` instead of `url`, one entry per building: `{"building": "The Zenith", "url": "..."}`. If any page fails to load, the whole property is skipped that run, so a temporarily missing building isn't mistaken for delisted units. `link` sets where tapping a notification goes.
- `beds` values are matched against the parser's output: `Studio`, `1 Bedroom`, `2 Bedrooms`, …
- Leave out `max_rent` to be notified about every new unit and price change.

## Adding a site

Add an entry to `sites.json`, write `parsers/<name>.py` with a `parse(html) -> list[dict]` function, and register it in `parsers/__init__.py`. Each unit needs `building`, `unit`, `beds`, `rent` and `available`, and ideally `base_rent`, `sqft` and `special`.

## Running locally

```bash
pip install -r requirements.txt
python tracker.py --no-notify              # full run, prints notifications instead of sending
NTFY_TOPIC=your-topic python tracker.py    # full run with notifications
python tracker.py --html saved_page.html   # just parse a saved page
python -m pytest tests                     # tests
```
