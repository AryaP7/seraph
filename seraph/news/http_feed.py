# C13 — Real HTTP acquisition: RSS/Atom fetching (NEWS01)
"""The missing half of the news subsystem: actually going and getting it.

`NewsStore.ingest()` takes an injected fetcher, which kept the pipeline
testable — and meant that until now the only fetchers that ever existed were
test fakes. There was no HTTP client in `seraph/news/` at all. This is it.

What it does that a two-line `requests.get` would not
----------------------------------------------------
* **Conditional GET.** `ETag`/`Last-Modified` are stored per source and
  replayed, so a 15-minute poll of an unchanged feed costs one 304 rather
  than re-downloading and re-hashing a megabyte. Polite to the source and
  cheap for us.
* **`first_seen_at` is stamped on arrival, never parsed from the feed.** This
  is the replay bound. A feed's `pubDate` says when the publisher published;
  only the clock says when SERAPH could have known. Trusting `pubDate` would
  let a replay read an item hours before the poller actually had it.
* **A dateless or unparseable `pubDate` is left unset**, not defaulted to now.
  A wrong publication time silently reorders the evidence.
* **Rate limiting and a declared User-Agent.** A source that blocks us is a
  source we lose.
* **The raw bytes are hashed before anything is parsed**, so the observation
  identity is of what actually arrived.

Parsing is RSS 2.0 and Atom, done with the standard library's XML parser in
its defused configuration. `feedparser` would be friendlier and is one more
dependency for a format this regular.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from seraph.news.acquisition import FetchedItem, FetchResult
from seraph.news.model import Source
from seraph.shared_types import IST, ist_timestamp

USER_AGENT = "SERAPH-research/0.1 (market-risk research; contact via repository)"

#: Never hammer a source. One request per source per this many seconds, floor.
MIN_SECONDS_BETWEEN_REQUESTS = 2.0

ATOM = "{http://www.w3.org/2005/Atom}"


class FeedFetchError(RuntimeError):
    """The source could not be read. Raised so `ingest()` records an outage."""


def _stamp(moment: datetime | None = None) -> str:
    return ist_timestamp((moment or datetime.now(IST)).astimezone(IST)
                         .replace(microsecond=0))


def parse_feed_datetime(raw: str | None) -> str | None:
    """RFC-822 or ISO-8601 to an IST timestamp, or None.

    None is a real answer. A publication time that will not parse is unknown,
    and defaulting it to the fetch time would silently reorder the evidence.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            # RBI's feed omits the offset; its times are IST.
            parsed = parsed.replace(tzinfo=IST)
        return ist_timestamp(parsed.astimezone(IST).replace(microsecond=0))
    except (TypeError, ValueError, IndexError):
        pass
    try:
        normalised = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalised)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return ist_timestamp(parsed.astimezone(IST).replace(microsecond=0))
    except ValueError:
        pass
    # T09: SEBI publishes "16 Oct, 2026 +0530" — a real date with a real
    # offset in a format RFC-822 does not cover. Thirty items were being
    # discarded as undated because of a comma. This is DAY granularity: the
    # time of day is not stated and is not invented, so it lands at the start
    # of that day in its own offset, and `day_granular()` says so to anything
    # that needs to know it is not a time.
    for fmt in _DAY_GRANULAR:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return ist_timestamp(parsed.astimezone(IST).replace(microsecond=0))
    return None


#: Day-granularity formats seen on real Indian regulator feeds. A match here
#: means the SOURCE gave a date and no time, which is different from the
#: source giving nothing.
_DAY_GRANULAR = (
    "%d %b, %Y %z",      # SEBI: 16 Oct, 2026 +0530
    "%d %B, %Y %z",
    "%d %b %Y %z",
    "%Y-%m-%d %z",
)


def day_granular(raw: str | None) -> bool:
    """Did the source give a DATE with no time of day?

    Callers that order evidence within a day need to know this: a story
    stamped at the start of its day is not known to have been published then,
    and treating it as a time would invent ordering the source never claimed.
    """
    if not raw or not raw.strip():
        return False
    text = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text): return True
    try:
        parsedate_to_datetime(text)
        return False
    except (TypeError, ValueError, IndexError):
        pass
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return False
    except ValueError:
        pass
    for fmt in _DAY_GRANULAR:
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def _text(element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip() if element is not None else ""


def _strip_html(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw or "")).strip()


def parse_feed(body: bytes, *, base_url: str = "") -> list[dict]:
    """RSS 2.0 or Atom to plain dicts. Unknown shapes yield nothing, loudly."""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise FeedFetchError(f"the response is not well-formed XML: {exc}") from exc

    entries = []
    for item in root.iter("item"):                       # RSS 2.0
        link = _text(item.find("link")) or _text(item.find("guid"))
        entries.append(dict(
            title=_text(item.find("title")),
            url=link or base_url,
            guid=_text(item.find("guid")) or link,
            published_raw=_text(item.find("pubDate")),
            summary=_strip_html(_text(item.find("description")))))
    for entry in root.iter(f"{ATOM}entry"):              # Atom
        link_element = entry.find(f"{ATOM}link")
        link = (link_element.get("href") if link_element is not None else "") or ""
        entries.append(dict(
            title=_text(entry.find(f"{ATOM}title")),
            url=link or base_url,
            guid=_text(entry.find(f"{ATOM}id")) or link,
            published_raw=(_text(entry.find(f"{ATOM}published"))
                           or _text(entry.find(f"{ATOM}updated"))),
            summary=_strip_html(_text(entry.find(f"{ATOM}summary"))
                                or _text(entry.find(f"{ATOM}content")))))
    if not entries and root.tag not in ("rss", f"{ATOM}feed"):
        raise FeedFetchError(
            f"the document root is <{root.tag}>, which is neither RSS nor Atom. "
            f"This URL is probably a landing page rather than a feed")
    return [e for e in entries if e["title"]]


@dataclass
class HttpFeedFetcher:
    """A callable `(source, cursor) -> FetchResult` that really fetches.

    Pass it straight to `NewsStore.ingest(source_id, fetcher)`.
    """

    timeout: float = 20.0
    user_agent: str = USER_AGENT
    #: Per-source conditional-GET state, carried between polls.
    validators: dict = field(default_factory=dict)
    _last_request: dict = field(default_factory=dict)
    #: Set for tests; production leaves it None and uses urllib.
    transport: object | None = None

    def _throttle(self, source_id: str) -> None:
        previous = self._last_request.get(source_id)
        if previous is not None:
            wait = MIN_SECONDS_BETWEEN_REQUESTS - (time.monotonic() - previous)
            if wait > 0:
                deadline = getattr(self, 'deadline_at', None)
                if deadline is not None and time.monotonic() + wait >= deadline:
                    raise TimeoutError('acquisition deadline exhausted during source throttle')
                time.sleep(wait)
        self._last_request[source_id] = time.monotonic()

    def _open(self, url: str, headers: dict, timeout: "float | None" = None,
              allowed_hosts=None):
        """`timeout` overrides the fetcher's default for THIS call.

        A budget that is only checked between sources constrains nothing: one
        feed that accepts the connection and then dribbles bytes holds the
        whole refresh open for as long as it likes. The remaining budget has
        to reach the socket, which is what this parameter is for.
        """
        budget = self.timeout if timeout is None else timeout
        deadline = min(time.monotonic() + budget,
                       getattr(self, 'deadline_at', None) or float('inf'))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('acquisition deadline exhausted')
        if self.transport is not None:
            return self.transport(url, headers)
        request = urllib.request.Request(url, headers=headers)
        try:
            if allowed_hosts is not None:
                class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                        target = urlsplit(newurl)
                        if target.scheme != 'https' or target.hostname not in allowed_hosts:
                            raise FeedFetchError('document redirect leaves permitted hosts')
                        return super().redirect_request(req, fp, code, msg, hdrs, newurl)
                opener = urllib.request.build_opener(RestrictedRedirect())
                response = opener.open(request, timeout=remaining)
            else:
                response = urllib.request.urlopen(request, timeout=remaining)
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return 304, {}, b""
            raise FeedFetchError(
                f"HTTP {exc.code} from {url}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise FeedFetchError(f"could not reach {url}: {exc.reason}") from exc
        with response:
            chunks, size = [], 0
            while size <= 8 * 1024 * 1024:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('acquisition deadline exhausted while reading body')
                sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                if sock is not None:
                    sock.settimeout(remaining)
                chunk = response.read1(min(65536, 8 * 1024 * 1024 + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            body = b''.join(chunks)
        if len(body) > 8 * 1024 * 1024:
            raise FeedFetchError('response exceeds 8 MiB acquisition limit')
        if response.headers.get("Content-Encoding") == "gzip":
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as compressed:
                body = compressed.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise FeedFetchError('decompressed response exceeds 8 MiB acquisition limit')
        return response.status, dict(response.headers), body

    def __call__(self, source: Source, cursor: str | None) -> FetchResult:
        headers = {"User-Agent": self.user_agent,
                   "Accept": "application/rss+xml, application/atom+xml, "
                             "application/xml;q=0.9, text/xml;q=0.9"}
        saved = self.validators.get(source.source_id, {})
        if saved.get("etag"):
            headers["If-None-Match"] = saved["etag"]
        if saved.get("last_modified"):
            headers["If-Modified-Since"] = saved["last_modified"]

        self._throttle(urlsplit(source.url).netloc)
        status, response_headers, body = self._open(
            source.url, headers, timeout=getattr(self, "deadline_timeout", None))

        if status not in (200, 304):
            raise FeedFetchError(f'HTTP {status} from registered source')
        if status == 304:
            # Unchanged since the last poll. Nothing new, and that is not an
            # error — the cursor is preserved so health stays healthy.
            return FetchResult(items=(), cursor=cursor, http_status=304)


        content_type = (response_headers.get("Content-Type") or "").lower()
        if "html" in content_type and "xml" not in content_type:
            raise FeedFetchError(
                f"{source.url} returned {content_type!r}. That is a web page, not "
                f"a feed — check the registered URL points at the feed itself")

        entries = parse_feed(body, base_url=source.url)
        self.validators[source.source_id] = {
            "etag": response_headers.get("ETag"),
            "last_modified": response_headers.get("Last-Modified")}

        received = _stamp()
        items = []
        for entry in entries:
            # The item's own bytes decide its identity, so an edited headline
            # becomes a correction rather than being mistaken for the original.
            raw = (f"{entry['guid']}|{entry['title']}|{entry['published_raw']}|"
                   f"{entry['summary']}").encode("utf-8")
            items.append(FetchedItem(
                reference=entry["guid"] or entry["url"],
                title=entry["title"], url=entry["url"], raw=raw,
                published_at=parse_feed_datetime(entry["published_raw"]),
                body=entry["summary"] or None,
                cursor=received,
                metadata=dict(publication_precision='day' if day_granular(entry['published_raw']) else
                              'timestamp' if parse_feed_datetime(entry['published_raw']) else 'unknown',
                              published_raw=entry['published_raw'],
                              # The exchange announcement feeds put the FILING
                              # ENTITY in the title and the subject in the
                              # body. Marking it lets the extractor treat the
                              # title as an entity rather than prose, without
                              # guessing from the shape of the string.
                              # getattr: a fetcher is handed whatever the
                              # caller calls a source, and a test stub need
                              # not carry every field of the full record.
                              title_is_filing_entity=getattr(
                                  source, 'kind', None) in
                              ("company_filing", "exchange_notice"))))
        return FetchResult(items=tuple(items), cursor=received,
                           http_status=status)


def probe(url: str, *, timeout: float = 20.0) -> dict:
    """Is this URL actually a usable feed? Used to verify accessibility.

    `Source.accessibility_verified` stays False until something has really
    fetched and parsed the URL, and this is what does that.
    """
    fetcher = HttpFeedFetcher(timeout=timeout)
    probe_source = Source(source_id="__probe__", provider="probe",
                          kind="news_agency", url=url, topic_coverage=())
    started = time.perf_counter()
    try:
        result = fetcher(probe_source, None)
    except (FeedFetchError, TimeoutError, OSError) as exc:
        return dict(url=url, reachable=False, usable=False, error=str(exc),
                    checked_at=_stamp())
    elapsed = (time.perf_counter() - started) * 1000
    dated = [i for i in result.items if i.published_at]
    return dict(
        url=url, reachable=True, usable=bool(result.items),
        items=len(result.items), dated_items=len(dated),
        newest_published=max((i.published_at for i in dated), default=None),
        http_status=result.http_status,
        latency_ms=round(elapsed, 1),
        sample_title=result.items[0].title[:120] if result.items else None,
        checked_at=_stamp(),
        publication_mode=('source_timestamp' if dated else 'first_seen_only'),
        replay_eligible=bool(dated),
        note=("parsed as a feed with dated items" if dated else
              "parsed, but no item carries a usable publication time"))
