"""Parallel page downloads: faster, capped per website, and a failed page stays with its site."""
import threading
import time

import pytest
import requests

import tracker


class FakeResponse:
    def __init__(self, url, status=200):
        self.status_code, self.text = status, f"<html>{url}</html>"
        self.ok = status < 400


@pytest.fixture
def fake_net(monkeypatch):
    """requests.get that takes 0.3s, records how many requests per host overlap,
    and returns 503 for any URL containing 'broken'."""
    stats = {"active": {}, "peak": {}, "total_peak": 0, "active_total": 0}
    lock = threading.Lock()

    def get(url, headers=None, timeout=None):
        host = url.split("/")[2]
        with lock:
            stats["active"][host] = stats["active"].get(host, 0) + 1
            stats["active_total"] += 1
            stats["peak"][host] = max(stats["peak"].get(host, 0), stats["active"][host])
            stats["total_peak"] = max(stats["total_peak"], stats["active_total"])
        time.sleep(0.3)
        with lock:
            stats["active"][host] -= 1
            stats["active_total"] -= 1
        return FakeResponse(url, 503 if "broken" in url else 200)

    monkeypatch.setattr(tracker.requests, "get", get)
    monkeypatch.setattr(tracker, "_host_slots", {})
    return stats


SITES = [
    {"name": "Big", "pages": [{"url": f"https://rentcafe.test/p{i}"} for i in range(6)]},
    {"name": "One", "url": "https://one.test/avail"},
    {"name": "Two", "url": "https://two.test/avail"},
    {"name": "Bad", "pages": [{"url": "https://bad.test/ok"}, {"url": "https://bad.test/broken"}]},
]


def test_parallel_and_capped_per_host(fake_net):
    started = time.monotonic()
    fetched = tracker.prefetch(SITES)
    elapsed = time.monotonic() - started
    assert len(fetched) == 10
    # one at a time would take 10 x 0.3 = 3s; the 6 rentcafe pages, 2 at a time, need ~0.9s
    assert elapsed < 1.6
    assert fake_net["peak"]["rentcafe.test"] == tracker.PER_HOST
    assert fake_net["total_peak"] <= tracker.MAX_WORKERS
    assert fake_net["total_peak"] > tracker.PER_HOST          # different sites overlapped


def test_failed_page_is_raised_for_its_own_site_only(fake_net, capsys):
    fetched = tracker.prefetch(SITES)
    assert tracker._page_html("https://one.test/avail", fetched) == "<html>https://one.test/avail</html>"
    assert "GET https://one.test/avail -> HTTP 200" in capsys.readouterr().out
    with pytest.raises(requests.HTTPError, match="HTTP 503"):
        tracker._page_html("https://bad.test/broken", fetched)


def test_scrape_uses_prefetched_pages(fake_net, monkeypatch, tmp_path):
    monkeypatch.setattr(tracker, "OUT", tmp_path)
    monkeypatch.setitem(tracker.PARSERS, "echo", lambda html, **k: [
        {"building": "B", "unit": html[-12:-7], "beds": "1 Bedroom", "rent": 1}])
    site = {"name": "One", "url": "https://one.test/avail", "parser": "echo", "beds": ["1 Bedroom"]}
    fetched = tracker.prefetch([site])
    monkeypatch.setattr(tracker, "fetch", lambda url: pytest.fail("should not re-download"))
    units = tracker.scrape(site, fetched=fetched)
    assert len(units) == 1
    assert (tmp_path / "pages" / "one-1.html").exists()
