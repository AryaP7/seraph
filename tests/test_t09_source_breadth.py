"""T09 — broaden acquisition beyond three RBI feeds (audit finding R07).

What the probe actually found, and what each finding forced:

* **SEBI parsed 30 items with ZERO usable dates.** Its `pubDate` is
  `16 Oct, 2026 +0530` — a real date with a real offset in a format RFC-822
  does not cover. A comma was discarding an entire market regulator. The
  parser now reads it, and reports that it is **day granular**, because the
  source states no time of day and inventing one would create ordering it
  never claimed.
* **PIB carries no date element at all.** Its items have `<title>` and
  `<link>` and nothing else, so its stories cannot be placed in information
  time. It stays rejected, with that reason recorded rather than quietly
  dropped from the plan.
* **Three named sources do not publish feeds.** The Federal Register exposes
  a documents API, USGS publishes GeoJSON with epoch-millisecond times, and
  GDELT returns JSON. Each needs a named adapter; there is no shape-guessing
  path.
"""
from __future__ import annotations

import json

import pytest

from seraph.news.http_feed import FeedFetchError, day_granular, parse_feed_datetime
from seraph.news.json_feed import (
    ADAPTERS,
    JsonSourceFetcher,
    _published,
    parse_json_source,
)


# --------------------------------------------------- the SEBI date format


def test_sebi_dates_are_read_rather_than_discarded():
    """The exact string the real feed serves."""
    assert parse_feed_datetime("16 Oct, 2026 +0530") == \
        "2026-10-16T00:00:00+05:30"


def test_a_sebi_date_is_reported_as_day_granular():
    """It lands at the start of the day; nothing may order within it."""
    assert day_granular("16 Oct, 2026 +0530") is True


def test_an_rfc822_timestamp_is_not_day_granular():
    assert parse_feed_datetime("Fri, 16 Oct 2026 18:30:00 +0530") == \
        "2026-10-16T18:30:00+05:30"
    assert day_granular("Fri, 16 Oct 2026 18:30:00 +0530") is False


def test_an_iso_timestamp_is_not_day_granular():
    assert day_granular("2026-10-16T18:30:00+05:30") is False


def test_an_unparseable_date_is_still_none():
    """None is a real answer; defaulting to the fetch time reorders evidence."""
    assert parse_feed_datetime("sometime last week") is None
    assert day_granular("sometime last week") is False


def test_an_empty_date_is_not_day_granular():
    assert day_granular("") is False
    assert day_granular(None) is False


# ----------------------------------------------------------- the adapters


def test_the_registered_adapters_are_named_not_guessed():
    assert set(ADAPTERS) == {"federal_register", "usgs_earthquakes",
                             "gdelt_doc"}


def test_an_unknown_adapter_is_refused():
    with pytest.raises(FeedFetchError, match="no JSON adapter named"):
        parse_json_source("whatever", b"{}")


def test_the_federal_register_adapter_reads_a_real_shape():
    body = json.dumps(dict(results=[dict(
        title="Notice of Action: Section 301",
        html_url="https://federalregister.gov/d/2026-1",
        document_number="2026-1", publication_date="2026-10-16",
        abstract="<p>The Trade Representative announces...</p>")])).encode()
    items = parse_json_source("federal_register", body)
    assert items[0]["guid"] == "2026-1"
    assert items[0]["published_raw"] == "2026-10-16"
    assert "<p>" not in items[0]["summary"]


def test_the_federal_register_is_day_granular_and_says_so():
    assert _published("2026-10-16") == "2026-10-16T00:00:00+05:30"


def test_a_response_that_is_not_the_expected_shape_is_refused():
    with pytest.raises(FeedFetchError, match="no 'results' key"):
        parse_json_source("federal_register", json.dumps(dict(x=1)).encode())


def test_usgs_epoch_milliseconds_are_not_read_as_seconds():
    """1760000000000 as seconds is the year 57000. That is the whole point."""
    body = json.dumps(dict(type="FeatureCollection", features=[dict(
        id="us1", properties=dict(title="M 5.2 - 10 km S of X",
                                  url="https://e/1", time=1760000000000,
                                  place="10 km S of X"),
        geometry=dict(coordinates=[72.5, 19.0, 10.0]))])).encode()
    item = parse_json_source("usgs_earthquakes", body)[0]
    assert item["published_raw"].startswith("2025-10-09T")


def test_usgs_carries_its_own_coordinate():
    """The one source where geography comes from the source, not the registry."""
    body = json.dumps(dict(type="FeatureCollection", features=[dict(
        id="us1", properties=dict(title="M 5.2", url="https://e/1",
                                  time=1760000000000, place="X"),
        geometry=dict(coordinates=[72.5, 19.0, 10.0]))])).encode()
    item = parse_json_source("usgs_earthquakes", body)[0]
    assert item["coordinates"] == [72.5, 19.0]
    assert item["coordinate_order"] == "lon_lat"


def test_a_usgs_feature_without_geometry_claims_no_coordinate():
    body = json.dumps(dict(type="FeatureCollection", features=[dict(
        id="us1", properties=dict(title="M 5.2", url="https://e/1",
                                  time=1760000000000))])).encode()
    assert parse_json_source("usgs_earthquakes", body)[0]["coordinates"] is None


def test_a_non_geojson_body_is_refused():
    with pytest.raises(FeedFetchError, match="FeatureCollection"):
        parse_json_source("usgs_earthquakes", json.dumps(dict(a=1)).encode())


@pytest.mark.parametrize("stamp", ["20261017T093000Z", "20261017T093000"])
def test_gdelt_timestamps_are_read(stamp):
    """With and without the trailing Z. Pinning one length discarded both."""
    body = json.dumps(dict(articles=[dict(
        title="India tariff review", url="https://x/1",
        seendate=stamp, domain="example.com")])).encode()
    item = parse_json_source("gdelt_doc", body)[0]
    assert item["published_raw"] == "2026-10-17T09:30:00+00:00"
    assert item["aggregator"] == "gdelt"


def test_a_gdelt_row_is_marked_an_aggregator_pointer():
    """Ten GDELT rows for one wire are not ten confirmations."""
    body = json.dumps(dict(articles=[dict(
        title="A", url="https://x/1", seendate="20261017T093000Z",
        domain="d")])).encode()
    assert parse_json_source("gdelt_doc", body)[0]["source_kind_hint"] == \
        "aggregator"


def test_malformed_json_is_refused_clearly():
    with pytest.raises(FeedFetchError, match="not valid JSON"):
        parse_json_source("gdelt_doc", b"{not json")


def test_an_item_without_a_title_is_dropped():
    body = json.dumps(dict(results=[dict(title="", html_url="https://x/1",
                                         document_number="1",
                                         publication_date="2026-10-16")])
                      ).encode()
    assert parse_json_source("federal_register", body) == []


def test_a_missing_time_yields_none_rather_than_now():
    body = json.dumps(dict(type="FeatureCollection", features=[dict(
        id="u", properties=dict(title="M 1", url="https://e/1"))])).encode()
    assert parse_json_source("usgs_earthquakes", body)[0]["published_raw"] is None


# ------------------------------------------------------------- the router


class _Transport:
    """A stand-in for urllib that records what was asked for."""

    def __init__(self, body: bytes, content_type="application/json"):
        self.body = body
        self.content_type = content_type
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        return 200, {"Content-Type": self.content_type}, self.body


class _Source:
    def __init__(self, source_id, url):
        self.source_id, self.url = source_id, url


def test_the_router_sends_a_json_source_to_its_adapter():
    body = json.dumps(dict(results=[dict(
        title="Notice", html_url="https://x/1", document_number="1",
        publication_date="2026-10-16", abstract="a")])).encode()
    transport = _Transport(body)
    fetcher = JsonSourceFetcher({"fr": "federal_register"},
                                transport=transport)
    result = fetcher(_Source("fr", "https://x/api"), None)
    assert [i.title for i in result.items] == ["Notice"]
    assert result.items[0].published_at == "2026-10-16T00:00:00+05:30"


def test_the_router_falls_through_to_the_feed_fetcher():
    """One router, two parsers, no third behaviour."""
    rss = (b"<rss><channel><item><title>T</title><link>https://x/1</link>"
           b"<pubDate>Fri, 16 Oct 2026 18:30:00 +0530</pubDate>"
           b"</item></channel></rss>")
    transport = _Transport(rss, content_type="application/rss+xml")
    fetcher = JsonSourceFetcher({"fr": "federal_register"},
                                transport=transport)
    result = fetcher(_Source("not_json", "https://x/feed.xml"), None)
    assert [i.title for i in result.items] == ["T"]


def test_an_unchanged_json_source_reports_304_without_items():
    class _NotModified(_Transport):
        def __call__(self, url, headers):
            self.calls.append((url, dict(headers)))
            return 304, {}, b""

    fetcher = JsonSourceFetcher({"fr": "federal_register"},
                                transport=_NotModified(b""))
    result = fetcher(_Source("fr", "https://x/api"), "cursor-1")
    assert result.items == ()
    assert result.http_status == 304
    assert result.cursor == "cursor-1", "an unchanged poll keeps the cursor"


def test_the_json_router_asks_for_json():
    transport = _Transport(json.dumps(dict(results=[])).encode())
    fetcher = JsonSourceFetcher({"fr": "federal_register"},
                                transport=transport)
    fetcher(_Source("fr", "https://x/api"), None)
    assert transport.calls[0][1]["Accept"] == "application/json"


# ------------------------------------------------- what is registered, and why


def test_the_rejected_sources_keep_their_reasons():
    """A source that vanishes from a plan looks like one nobody tried."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "run_news", root / "scripts" / "run_news.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rejected = {source_id: why for source_id, _url, why in
                module.REJECTED_SOURCES}
    assert "pib_releases" not in rejected
    pib = next(s for s in module.PILOT_SOURCES if s.source_id == "pib_releases")
    assert "First-seen-only" in pib.notes
    assert "gdelt_doc" in rejected
    assert "429" in rejected["gdelt_doc"]

    registered = {s.source_id for s in module.VERIFIED_SOURCES}
    registered |= {s.source_id for s, _ in module.VERIFIED_JSON_SOURCES}
    assert {"rbi_press_releases", "sebi_press", "federal_register",
            "usgs_earthquakes"} <= registered
    assert not (registered & set(rejected)), (
        "a source cannot be both registered and rejected")


def test_a_day_granular_source_says_so_in_its_notes():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "run_news", root / "scripts" / "run_news.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    sebi = next(s for s in module.VERIFIED_SOURCES
                if s.source_id == "sebi_press")
    assert "day-granular" in (sebi.notes or "")
    assert "within a day" in (sebi.notes or "").lower()
