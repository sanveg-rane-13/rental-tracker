# Rental tracker

Tracks rental listing pages and (later) sends push notifications for new units and price changes.

**Current stage:** steps 1–2. The script fetches each site, parses its units, prints them and saves them to `output/listings.json`.

## Files

| File | What it does |
|---|---|
| `sites.json` | Sites to track: property name, URL, which parser to use, bedroom filter |
| `parsers/newport.py` | Parser for Newport Rentals |
| `tracker.py` | Fetches every site, applies the filter, prints a table, writes `output/listings.json` |
| `.github/workflows/tracker.yml` | Runs the tracker on GitHub Actions (manual for now, hourly later) |
| `tests/` | Parser tests against a sample page |

## Run locally

```bash
pip install -r requirements.txt
python tracker.py
```

## Run on GitHub Actions

1. Create a new repo (private is fine; an hourly run uses about 700 of the 2,000 free minutes a month).
2. Push this folder to it.
3. Open **Actions → Rental tracker → Run workflow**.
4. The log prints the table of units. `output/listings.json` is attached to the run under **Artifacts**.

If a site returns no units, the job fails and its raw HTML is saved in `output/debug/` in the same artifact. Send that file over and the parser can be adjusted.

## Adding a site

Add an entry to `sites.json`, write `parsers/<name>.py` with a `parse(html) -> list[dict]` function, and register it in `parsers/__init__.py`. Each unit dict needs at least `building`, `unit`, `beds`, `rent` and `available`.
