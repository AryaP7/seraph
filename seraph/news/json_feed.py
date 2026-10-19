# C-news — JSON source adapters (T09, audit finding R07).
"""Sources that publish JSON, not RSS.

**Why this exists.** `http_feed.py` reads RSS and Atom, and three RBI feeds
are what that reached. Several of the sources the plan names do not publish a
feed at all: the US Federal Register exposes a documents API, the USGS
publishes GeoJSON, and GDELT returns JSON records. Treating those as feeds
fails with "the document root is not RSS", which is accurate and useless.

Each adapter here converts one source's JSON into exactly the dict shape
`parse_feed()` produces, so everything downstream — dedup, syndication
grouping, the information-time rules, extraction — is unchanged and untested
code paths are not introduced per source.

**Three rules every adapter keeps.**

1. **No invented time.** An item whose publication time the source does not
   give is returned with `published_raw=None`, and the acquisition layer
   treats it as undated. Substituting "now" would make a replay bound
   meaningless, because `first_seen_at` would silently equal `published_at`.
2. **No invented identity.** `guid` is the source's own stable id where it
   has one. Hashing the title to manufacture one would make an edited
   headline look like a new story.
3. **The body is data, never instructions.** These are third-party documents;
   nothing here evaluates or follows what they contain. The existing
   prompt-injection scrub in `extraction.py` still applies.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from seraph.news.http_feed import FeedFetchError, _strip_html

ADAPTER_VERSION = "c-news.json_feed/2026-10-17.1"


def _loads(body: bytes) -> object:
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FeedFetchError(f"the response is not valid JSON: {exc}") from exc


def federal_register(body: bytes, *, base_url: str = "") -> list[dict]:
    """US Federal Register `documents.json`.

    `publication_date` is a DATE, not a timestamp: the register publishes
    daily. It is passed through as the date it is, and the acquisition layer
    is responsible for not pretending that is a time of day.
    """
    payload = _loads(body)
    if not isinstance(payload, dict) or "results" not in payload:
        raise FeedFetchError(
            "this does not look like a Federal Register documents response: "
            "no 'results' key")
    out = []
    for item in payload.get("results") or []:
        number = (item.get("document_number") or "").strip()
        published = (item.get("publication_date") or "").strip()
        row = dict(
            title=(item.get("title") or "").strip(),
            url=item.get("html_url") or item.get("pdf_url") or base_url,
            guid=number or item.get("html_url") or "",
            published_raw=published,
            summary=_strip_html(item.get("abstract") or ""),
            source_kind_hint="official_policy")
        # Where the FULL TEXT can actually be read.
        #
        # federalregister.gov answers a document request with a 302 to
        # `unblock.federalregister.gov`, an access-control interstitial.
        # That is the publisher declining automated access and it is not
        # ours to work around -- the enrichment host allow-list correctly
        # refuses to follow it, which is why no document body was ever
        # retrieved from this source.
        #
        # The GPO publishes the same document, as the same US Government
        # work, at a documented stable path, and govinfo.gov is already a
        # permitted host. This is a different publisher of the same text,
        # not a way around the first one's control.
        if number and re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
            row["document_url"] = (f"https://www.govinfo.gov/content/pkg/"
                                   f"FR-{published}/html/{number}.htm")
        out.append(row)
    return [e for e in out if e["title"]]


def usgs_earthquakes(body: bytes, *, base_url: str = "") -> list[dict]:
    """USGS earthquake GeoJSON.

    The time field is epoch MILLISECONDS, which is why this adapter exists:
    handing `1760000000000` to a date parser produces either an error or a
    date in the year 57000, and the second is worse.
    """
    from datetime import datetime, timezone

    payload = _loads(body)
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise FeedFetchError(
            "this does not look like USGS GeoJSON: type is not "
            "'FeatureCollection'")
    out = []
    for feature in payload.get("features") or []:
        properties = feature.get("properties") or {}
        millis = properties.get("time")
        published = None
        if isinstance(millis, (int, float)):
            published = datetime.fromtimestamp(
                millis / 1000.0, tz=timezone.utc).isoformat()
        geometry = (feature.get("geometry") or {}).get("coordinates") or []
        out.append(dict(
            title=(properties.get("title") or "").strip(),
            url=properties.get("url") or base_url,
            guid=feature.get("id") or properties.get("code") or "",
            published_raw=published,
            summary=_strip_html(properties.get("place") or ""),
            # Carried, not consumed: an event with its own coordinate is the
            # one case where geography comes from the source rather than the
            # registry, and T13's adapter must be told it is source-supplied.
            coordinates=(list(geometry[:2]) if len(geometry) >= 2 else None),
            coordinate_order="lon_lat",
            source_kind_hint="hazard_agency"))
    return [e for e in out if e["title"]]


def gdelt_doc(body: bytes, *, base_url: str = "") -> list[dict]:
    """GDELT DOC 2.0 `format=json` article list.

    GDELT aggregates other outlets, so an item here is a POINTER to a story,
    not the story. `syndication_group` is left to the acquisition layer: ten
    GDELT rows for one wire are still one confirmation, and the dedup rules
    already in place are what enforce that.
    """
    payload = _loads(body)
    if not isinstance(payload, dict) or "articles" not in payload:
        raise FeedFetchError(
            "this does not look like a GDELT DOC response: no 'articles' key")
    out = []
    for article in payload.get("articles") or []:
        stamp = article.get("seendate")
        published = None
        if (isinstance(stamp, str) and len(stamp) in (15, 16)
                and stamp[8:9] == "T" and stamp[:8].isdigit()):
            # GDELT writes 20261017T093000Z — sixteen characters with the Z,
            # fifteen without. Pinning the length to one of them silently
            # discarded every timestamp from the live API.
            published = (f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T"
                         f"{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}+00:00")
        out.append(dict(
            title=(article.get("title") or "").strip(),
            url=article.get("url") or base_url,
            guid=article.get("url") or "",
            published_raw=published,
            summary=_strip_html(article.get("domain") or ""),
            aggregator="gdelt",
            source_kind_hint="aggregator"))
    return [e for e in out if e["title"]]


#: name -> parser. Registering an adapter is how a JSON source becomes
#: acquirable; there is no generic "try to guess the shape" path, because a
#: guess that half-works produces half-dated stories.
ADAPTERS: "dict[str, Callable[..., list[dict]]]" = {
    "federal_register": federal_register,
    "usgs_earthquakes": usgs_earthquakes,
    "gdelt_doc": gdelt_doc,
}


def parse_json_source(adapter: str, body: bytes, *, base_url: str = ""
                      ) -> list[dict]:
    if adapter not in ADAPTERS:
        raise FeedFetchError(
            f"no JSON adapter named {adapter!r}; the registered ones are "
            f"{', '.join(sorted(ADAPTERS))}. A source whose shape nobody has "
            f"read is not acquirable")
    return ADAPTERS[adapter](body, base_url=base_url)


def probe_json(url: str, adapter: str, *, timeout: float = 20.0) -> dict:
    """Is this URL really a usable JSON source for this adapter?"""
    import time
    import urllib.error
    import urllib.request

    from seraph.news.http_feed import USER_AGENT, _stamp

    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return dict(url=url, adapter=adapter, reachable=False, usable=False,
                    error=f"{type(exc).__name__}: {exc}", checked_at=_stamp())
    elapsed = (time.perf_counter() - started) * 1000
    try:
        items = parse_json_source(adapter, body, base_url=url)
    except FeedFetchError as exc:
        return dict(url=url, adapter=adapter, reachable=True, usable=False,
                    http_status=status, error=str(exc),
                    latency_ms=round(elapsed, 1), checked_at=_stamp())
    dated = [i for i in items if i.get("published_raw")]
    return dict(
        url=url, adapter=adapter, reachable=True, usable=bool(items),
        items=len(items), dated_items=len(dated),
        newest_published=max((i["published_raw"] for i in dated), default=None),
        http_status=status, latency_ms=round(elapsed, 1),
        sample_title=items[0]["title"][:120] if items else None,
        checked_at=_stamp(), adapter_version=ADAPTER_VERSION,
        note=("parsed by the adapter with dated items" if dated else
              "parsed, but no item carries a usable publication time"))


class JsonSourceFetcher:
    """`(source, cursor) -> FetchResult` for a JSON source, by adapter.

    Deliberately a thin subclass-by-composition of `HttpFeedFetcher`: the
    throttle, the conditional GET, the identity rule (an item's own bytes
    decide whether an edit is a correction) and the `FetchResult` contract are
    the feed fetcher's, unchanged. Only the parse step differs, which is the
    only thing that actually differs about a JSON source.
    """

    def __init__(self, adapters: "dict[str, str]", *, timeout: float = 20.0,
                 transport: object | None = None) -> None:
        from seraph.news.http_feed import HttpFeedFetcher

        #: source_id -> adapter name.
        self.adapters = dict(adapters)
        self._http = HttpFeedFetcher(timeout=timeout, transport=transport)

    def __call__(self, source, cursor):
        from seraph.news.acquisition import FetchedItem, FetchResult
        from seraph.news.http_feed import USER_AGENT, _stamp

        adapter = self.adapters.get(source.source_id)
        if adapter is None:
            # Not a JSON source: hand it to the feed fetcher rather than
            # guessing. One router, two parsers, no third behaviour.
            return self._http(source, cursor)

        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        saved = self._http.validators.get(source.source_id, {})
        if saved.get("etag"):
            headers["If-None-Match"] = saved["etag"]
        if saved.get("last_modified"):
            headers["If-Modified-Since"] = saved["last_modified"]

        from urllib.parse import urlsplit
        self._http._throttle(urlsplit(source.url).netloc)
        status, response_headers, body = self._http._open(
            source.url, headers, timeout=getattr(self, "deadline_timeout", None))
        if status == 304:
            return FetchResult(items=(), cursor=cursor, http_status=304)

        if status != 200:
            raise FeedFetchError(f'HTTP {status} from registered JSON source')
        entries = parse_json_source(adapter, body, base_url=source.url)
        self._http.validators[source.source_id] = {
            "etag": response_headers.get("ETag"),
            "last_modified": response_headers.get("Last-Modified")}

        received = _stamp()
        items = []
        for entry in entries:
            raw = (f"{entry['guid']}|{entry['title']}|{entry['published_raw']}|"
                   f"{entry.get('summary', '')}").encode("utf-8")
            items.append(FetchedItem(
                reference=entry["guid"] or entry["url"],
                title=entry["title"], url=entry["url"], raw=raw,
                published_at=None if adapter == "usgs_earthquakes" else _published(entry["published_raw"]),
                body=entry.get("summary") or None,
                cursor=received, metadata=dict(
                    publication_precision='unknown' if adapter == 'usgs_earthquakes' else
                    'day' if len(entry.get('published_raw') or '') == 10 else 'timestamp',
                    occurred_at=_published(entry['published_raw']) if adapter == 'usgs_earthquakes' else None,
                    coordinates=entry.get('coordinates'), coordinate_order=entry.get('coordinate_order'),
                    # Where the full text is actually readable, when the
                    # citation link is not. Enrichment fetches this and the
                    # reader still cites `url`.
                    document_url=entry.get('document_url'),
                    source_kind_hint=entry.get('source_kind_hint'))))
        return FetchResult(items=tuple(items), cursor=received,
                           http_status=status)


def _published(raw: "str | None") -> "str | None":
    """Parse an adapter's timestamp, including a bare date.

    The Federal Register gives `2026-10-16` and no time. It lands at the start
    of that day and `day_granular()` says so; inventing a publication hour
    would create ordering the source never claimed.
    """
    from seraph.news.http_feed import parse_feed_datetime

    if not raw:
        return None
    parsed = parse_feed_datetime(raw)
    if parsed:
        return parsed
    try:
        from datetime import datetime

        from seraph.shared_types import IST, ist_timestamp

        day = datetime.strptime(raw.strip(), "%Y-%m-%d").replace(tzinfo=IST)
        return ist_timestamp(day)
    except ValueError:
        return None
