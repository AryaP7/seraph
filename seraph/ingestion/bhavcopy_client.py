# C2 — Ingestion (FR1, FR7, FR8): incremental fresh EOD acquisition from NSE.
"""Acquire the sessions the corpus does not have yet, from NSE's own archive.

Why this exists
---------------
The vendored EOD2 snapshot ends 2026-08-21. Everything downstream ran
correctly on it and produced a two-month-old forecast, which is a working
pipeline on stale inputs — the scheduler fired, every step succeeded, and no
new observation entered the system. `run_market_jobs` could report
`execution ok` forever without the corpus ever moving.

What it reuses, and why none of it is reimplemented here
-------------------------------------------------------
* **`macro_client._Fetcher`** — retry, backoff, the inter-request gap, the
  total-response deadline and the raw-bytes cache with its sha256. NSE's
  behaviour is why those exist; a second copy would drift from the first.
* **`bhavcopy_reader.parse_bhavcopy`** — both NSE schemas, already written and
  already tested. On the 2026-10-19 file it accepts 2,698 rows, rejects none,
  and reports `traded_value_basis='exact_TOTTRDVAL'`.
* **`StoreWriter.write_batch_bulk`** — the same idempotent COPY path
  `eod2_client` uses, upserting on `(symbol, date)`, so re-acquiring a day
  converges to `inserted: 0` (CT-1).

**No credentials are required.** The bhavcopy archive is public, which is why
this is the path implemented first: Kite Connect is needed for *intraday*
bars (FR1's 5-minute cadence, and therefore the Hawkes pillar), not for
end-of-day data. That distinction is the whole reason the daily pillars and
the prediction engine can run fresh while Hawkes stays blocked.

Exact traded value, not the proxy
---------------------------------
`eod2_client` approximates `tottrdval` as `close × volume` and warns on every
batch. The bhavcopy carries the real `TOTTRDVAL`, so rows acquired here are
*better* than the historical ones for FR52, which ranks the universe on
six-month median traded value. `basis` records which a row came from rather
than mixing them silently.

What it refuses to do
---------------------
* **Store a file whose own trade date is not the day requested.** NSE serving
  a stale or wrong file would otherwise write yesterday's prices under
  today's date, which is the single worst thing an acquisition layer can do.
* **Store a day with implausibly few rows.** A truncated or placeholder file
  parses cleanly and would silently shrink the cross-section that C4 and C6
  compute on.
* **Store a bar whose OHLC cannot be true.** The parser validates each number;
  it does not check that the four of them are consistent with each other.
* **Treat an unpublished day as a failure.** A holiday, or a session whose
  file is not out yet, is `not_published` — distinct from `blocked` and from
  `invalid`, because the operator action differs for each.
* **Invent `adj_close`.** A bhavcopy is unadjusted. For the day it describes
  that equals the close, which is what is stored; a later corporate action
  will not retroactively adjust these rows until D04 implements that, and
  `basis` is how a reader can tell which rows are affected.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from seraph.ingestion.bhavcopy_reader import EQUITY_SERIES, parse_bhavcopy
from seraph.ingestion.macro_client import (
    _Blocked,
    _Fetcher,
    _NotFound,
    _Unavailable,
)
from seraph.shared_types import DailyBar, IngestBatch

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = ROOT / "artefacts" / "bhavcopy_raw"

#: NSE replaced the legacy layout with UDiFF in July 2024. Both are tried,
#: newest layout first, because a session near the changeover may only exist
#: under the other one.
UDIFF_URL = ("https://nsearchives.nseindia.com/content/cm/"
             "BhavCopy_NSE_CM_0_0_0_{stamp}_F_0000.csv.zip")
LEGACY_URL = ("https://nsearchives.nseindia.com/content/historical/EQUITIES/"
              "{year}/{mon}/cm{day}{mon}{year}bhav.csv.zip")
REFERER = "https://www.nseindia.com/"

#: A real NSE equity bhavcopy carries roughly 2,700 EQ rows. A file with a
#: few hundred is truncated, a placeholder, or a different product's file; it
#: parses cleanly and would quietly shrink the cross-section every downstream
#: estimator depends on. Deliberately well below the real count so an
#: ordinary thin day is not refused.
MIN_PLAUSIBLE_ROWS = 500

#: Seconds between archive requests. The shared `_Fetcher` default is 20s,
#: set for FRED's *adaptive* rate limit, which starts trickling responses
#: after a few back-to-back calls. This is a static ZIP archive with no such
#: behaviour, and a forty-session backfill at 20s each is fourteen minutes of
#: waiting for files that take a second to serve.
#:
#: 2.5s is still well under one request per second and is not a bypass of
#: anything: nothing about NSE's archive asks for a wider gap, and a cached
#: day costs no request at all. If the archive ever does start throttling,
#: `_Fetcher`'s retry and total-deadline guards are already in the path.
ARCHIVE_GAP_S = 2.5

SessionStatus = Literal[
    "stored",          # rows validated and written
    "not_published",   # no file for that day: a holiday, or not out yet
    "blocked",         # the source refused us (NSE blocks some IPs)
    "unavailable",     # transport failure after retries
    "invalid",         # a file arrived and did not survive validation
]


@dataclass
class SessionOutcome:
    day: str
    status: SessionStatus
    detail: str = ""
    rows: int = 0
    rejected: int = 0
    inserted: int = 0
    updated: int = 0
    schema: str | None = None
    traded_value_basis: str | None = None
    sha256: str | None = None

    def describe(self) -> dict:
        return dict(day=self.day, status=self.status, detail=self.detail,
                    rows=self.rows, rejected=self.rejected,
                    inserted=self.inserted, updated=self.updated,
                    schema=self.schema,
                    traded_value_basis=self.traded_value_basis,
                    sha256=self.sha256)


@dataclass
class _ListingState:
    """Per-symbol listing-day counter, carried forward from the corpus.

    `listing_days_to_date` is a monotone per-symbol counter and FR52 filters
    on `>= 1000` of them. A fresh row written with 0 would drop that symbol
    out of the eligible set, so the count has to continue from what the
    corpus already holds rather than restart.
    """
    last_date: dict[str, str] = field(default_factory=dict)
    days: dict[str, int] = field(default_factory=dict)

    def next_for(self, symbol: str, day: str) -> int:
        current = self.days.get(symbol, 0)
        if self.last_date.get(symbol, "") >= day:
            return current            # re-acquiring a day already counted
        self.days[symbol] = current + 1
        self.last_date[symbol] = day
        return self.days[symbol]


def _stamps(day: str) -> tuple[str, dict]:
    parsed = date.fromisoformat(day)
    return parsed.strftime("%Y%m%d"), dict(
        year=parsed.strftime("%Y"), mon=parsed.strftime("%b").upper(),
        day=parsed.strftime("%d"))


def candidate_urls(day: str) -> list[tuple[str, str]]:
    """`(url, cache_name)` for both archive layouts, newest first."""
    stamp, legacy = _stamps(day)
    return [
        (UDIFF_URL.format(stamp=stamp), f"bhavcopy_udiff_{stamp}.zip"),
        (LEGACY_URL.format(**legacy), f"bhavcopy_legacy_{stamp}.zip"),
    ]


def sessions_to_acquire(*, latest_stored: str | None, expected: str,
                        clock=None, limit: int | None = None) -> list[str]:
    """Trading days the corpus is missing, oldest first.

    Trading days use the scheduler's configured calendar (`MarketClock.is_session`).
    Outside verified coverage the historical registry may still include an
    unlisted holiday; its archive response remains `not_published`.
    """
    from seraph.live.clock import MarketClock

    clock = clock or MarketClock()
    end = date.fromisoformat(expected)
    start = (date.fromisoformat(latest_stored) + timedelta(days=1)
             if latest_stored else end)
    out: list[str] = []
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        if clock.is_session(iso):
            out.append(iso)
        cursor += timedelta(days=1)
    return out[:limit] if limit else out


def _unzip(payload: bytes) -> bytes:
    """The CSV inside the archive, or the payload if it is already a CSV."""
    if payload[:2] != b"PK":
        return payload
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError(f"the archive holds no CSV: {archive.namelist()}")
        return archive.read(names[0])


def validate(result, *, day: str) -> str | None:
    """Why this file must not be stored, or None if it may be.

    Ordered so the most dangerous failure is reported first: a file whose own
    trade date disagrees with the day requested would write one session's
    prices under another session's date.
    """
    if result.trade_date and result.trade_date != day:
        return (f"the file's own trade date is {result.trade_date}, not the "
                f"requested {day}. Storing it would file one session's "
                f"prices under another session's date")
    if not result.rows:
        return "no rows survived parsing"
    if len(result.rows) < MIN_PLAUSIBLE_ROWS:
        return (f"only {len(result.rows)} rows, below the {MIN_PLAUSIBLE_ROWS} "
                f"floor: a real NSE equity bhavcopy carries roughly 2,700, so "
                f"this is truncated, a placeholder, or another product's file")
    for row in result.rows:
        if not (row.low <= row.open <= row.high
                and row.low <= row.close <= row.high):
            return (f"{row.symbol} has OHLC that cannot be true: "
                    f"open={row.open} high={row.high} low={row.low} "
                    f"close={row.close}")
        if row.low <= 0 or row.traded_quantity < 0:
            return (f"{row.symbol} has a non-positive price or negative "
                    f"volume: low={row.low} volume={row.traded_quantity}")
    return None


def to_daily_bars(result, *, day: str, listing: _ListingState
                  ) -> tuple[DailyBar, ...]:
    """E3 rows. `adj_close` is the close, and `basis` says why.

    A bhavcopy is unadjusted. For the session it describes, the adjusted and
    unadjusted close are the same number, so this is not an approximation --
    but a later split or bonus will not retroactively adjust these rows until
    D04 does, which the batch's `source_schema_version` records.
    """
    return tuple(
        DailyBar(
            symbol=row.symbol, date=day,
            open=row.open, high=row.high, low=row.low, close=row.close,
            volume=int(row.traded_quantity),
            tottrdval=float(row.traded_value),
            adj_close=row.close,
            listing_days_to_date=listing.next_for(row.symbol, day),
        )
        for row in result.rows
    )


async def latest_stored_session(connection) -> str | None:
    value = await connection.fetchval("select max(date) from daily_prices")
    return str(value) if value else None


async def load_listing_state(connection) -> _ListingState:
    rows = await connection.fetch(
        "select symbol, max(date) as last_date, "
        "max(listing_days_to_date) as days from daily_prices group by symbol")
    state = _ListingState()
    for row in rows:
        state.last_date[row["symbol"]] = str(row["last_date"])
        state.days[row["symbol"]] = int(row["days"] or 0)
    return state


def fetch_session(fetcher: _Fetcher, day: str) -> tuple[bytes, str, str]:
    """`(csv_bytes, url, sha256)`; raises the fetcher's own error variants.

    Both layouts are tried. A 404 from both is `_NotFound`, which the caller
    reads as `not_published` rather than a failure.
    """
    last: Exception | None = None
    for url, cache_name in candidate_urls(day):
        try:
            fetcher.get(url, cache_name, referer=REFERER)
        except _NotFound as exc:
            last = exc
            continue
        entry = fetcher.manifest[-1]
        payload = (fetcher.cache_dir / cache_name).read_bytes()
        return _unzip(payload), url, entry.get("sha256", "")
    raise last or _NotFound(f"no bhavcopy for {day} in either layout")


async def acquire(
    *,
    days: list[str] | None = None,
    expected: str | None = None,
    limit: int | None = None,
    cache_dir: Path | None = None,
    refresh: bool = False,
    dsn: str | None = None,
) -> dict:
    """Fetch, validate and store every session the corpus is missing.

    Returns a report whose `acquired` field is the thing the scheduler cares
    about: whether any new observation actually entered the store. A run in
    which every day came back `not_published` is a successful execution that
    acquired nothing, and says so.
    """
    import asyncpg

    from seraph.operations.schedule import expected_session
    from seraph.store.bootstrap import DEFAULT_DSN
    from seraph.store.writer import StoreWriter

    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dsn = dsn or DEFAULT_DSN

    try:
        connection = await asyncpg.connect(dsn, timeout=10)
    except Exception as exc:                                # noqa: BLE001
        return dict(ok=False, acquired=False, blocked=(
            f"the research database is unreachable "
            f"({type(exc).__name__}). Run `docker compose up -d`."),
            sessions=[])

    try:
        before = await latest_stored_session(connection)
        listing = await load_listing_state(connection)
    finally:
        await connection.close()

    target = expected or expected_session()
    wanted = days or sessions_to_acquire(latest_stored=before,
                                         expected=target, limit=limit)
    if not wanted:
        return dict(ok=True, acquired=False, sessions=[],
                    latest_before=before, latest_after=before,
                    expected=target,
                    note=("the corpus already reaches the expected session; "
                          "nothing to acquire"))

    fetcher = _Fetcher(cache_dir, refresh=refresh, gap_s=ARCHIVE_GAP_S)
    writer = await StoreWriter.connect(dsn)
    outcomes: list[SessionOutcome] = []
    try:
        for day in wanted:
            outcomes.append(await _one_session(day, fetcher, writer, listing))
    finally:
        await writer.close()

    try:
        connection = await asyncpg.connect(dsn, timeout=10)
        after = await latest_stored_session(connection)
        await connection.close()
    except Exception:                                       # noqa: BLE001
        after = before

    stored = [o for o in outcomes if o.status == "stored"]
    failed = [o for o in outcomes if o.status in ("blocked", "unavailable",
                                                  "invalid")]
    return dict(
        ok=not failed,
        acquired=bool(stored),
        sessions=[o.describe() for o in outcomes],
        latest_before=before, latest_after=after, expected=target,
        stored_sessions=[o.day for o in stored],
        rows_written=sum(o.inserted + o.updated for o in stored),
        failures=[o.describe() for o in failed],
        note=("`acquired` is whether a new observation entered the store. A "
              "run where every day was not_published executed correctly and "
              "acquired nothing, which is not a failure"))


async def _one_session(day, fetcher, writer, listing) -> SessionOutcome:
    try:
        raw, url, digest = fetch_session(fetcher, day)
    except _NotFound as exc:
        return SessionOutcome(day=day, status="not_published", detail=(
            f"no file published for {day}: an exchange holiday, or the "
            f"session's file is not out yet ({exc})")[:300])
    except _Blocked as exc:
        return SessionOutcome(day=day, status="blocked", detail=str(exc)[:300])
    except (_Unavailable, Exception) as exc:                # noqa: BLE001
        return SessionOutcome(day=day, status="unavailable",
                              detail=f"{type(exc).__name__}: {exc}"[:300])

    try:
        result = parse_bhavcopy(raw, series=EQUITY_SERIES)
    except Exception as exc:                                # noqa: BLE001
        return SessionOutcome(day=day, status="invalid",
                              detail=f"parse failed: {exc}"[:300],
                              sha256=digest)

    refusal = validate(result, day=day)
    if refusal:
        return SessionOutcome(day=day, status="invalid", detail=refusal[:300],
                              rows=len(result.rows),
                              rejected=len(result.rejected),
                              schema=result.schema, sha256=digest)

    bars = to_daily_bars(result, day=day, listing=listing)
    # `source` is a closed Literal and `bhavcopy` is already one of its
    # values -- distinct from `eod2`, which is what makes a row's traded
    # value and adjustment basis traceable without a new vocabulary.
    batch = IngestBatch(
        run_id=f"bhavcopy-{day}", source="bhavcopy", entity="E3",
        rows=bars, watermark=f"{day}T18:00:00+05:30",
        source_schema_version=result.schema,
    )
    written = await writer.write_batch_bulk(batch)
    if written.status != "ok":
        return SessionOutcome(day=day, status="invalid",
                              detail=f"write refused: {written.error}"[:300],
                              rows=len(bars), schema=result.schema,
                              sha256=digest)
    return SessionOutcome(
        day=day, status="stored", rows=len(bars),
        rejected=len(result.rejected), inserted=written.value.inserted,
        updated=written.value.updated, schema=result.schema,
        traded_value_basis=result.traded_value_basis, sha256=digest,
        detail=(f"{len(bars)} rows from {url.rsplit('/', 1)[-1]}, "
                f"traded value {result.traded_value_basis}"))
