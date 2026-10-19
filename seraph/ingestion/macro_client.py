# C2 — Ingestion Layer (FR3): macro covariate client → E4 macro_covariates (z_t).
"""Lands the FR3 covariate set — RBI repo rate, YoY bank credit growth, India
VIX, trade-weighted INR, Brent crude — onto E4's daily date axis.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not validate FR21. FR21 is the TVTP multinomial logit on `z_t`; this
module only supplies `z_t`'s columns. Hamilton still has to be re-estimated
against them and re-evaluated before anything about FR21 may be claimed.
It also never writes `g_t` / `g_t_sector_weighted` — those are C4's (FR22).

SOURCE FIDELITY — read this before quoting any of these series
--------------------------------------------------------------
Two of the five covariates are **substitutes**, not the series FR3 names, and
one is **truncated**. Every row this module writes is real, published data; none
of it is simulated. But the substitutions are material and the report must say
so:

- `brent_price`    EXACT.      FRED `DCOILBRENTEU` (EIA Brent spot, USD/bbl).
- `rbi_repo_rate`  SUBSTITUTE. FRED `IRSTCI01INM156N` is a *monthly average*
                   central-bank policy rate for India, not RBI's dated repo
                   step. A policy change mid-month shows up smeared across two
                   monthly points. For event-study work on policy dates this
                   series is the wrong instrument, and a hand-curated dated step
                   table is required instead.
- `inr_twi`        SUBSTITUTE. FRED `NBINBIS` is the BIS *broad nominal
                   effective* exchange rate for India (2020 = 100), not RBI's
                   own 40-currency NEER. Same construct, different basket and
                   base. Monthly.
- `bank_credit_growth_yoy`
                   SUBSTITUTE. Derived as the 4-quarter percentage change of
                   FRED `CRDQINAPABIS` (BIS credit to the private non-financial
                   sector *from banks*, INR bn). This is not RBI's weekly
                   non-food bank credit: it is quarterly, broader in scope, and
                   published with a long lag. A quarterly series forward-filled
                   onto a daily axis contributes ~4 genuinely new values a year.
- `india_vix`      EXACT VALUES, TRUNCATED HISTORY. NSE's close, via the
                   vendored EOD2 index CSV, **from 2014-05-14 only**.

THE PRE-2014 VIX GAP IS NOT A BUG AND NOT FIXABLE FROM FREE SOURCES
-------------------------------------------------------------------
India VIX itself starts Nov 2007 (DATA-ACQUISITION §2), but probed 2026-10-12:
  - NSE `/api/historical/vixhistory`              → 503, Akamai bot block.
  - `nsearchives .../ind_close_all_02012008.csv`  → 404 (archive starts later).
  - `nsearchives .../ind_close_all_02012014.csv`  → 200 but carries no India VIX row.
  - `nsearchives .../ind_close_all_15052014.csv`  → 200, first file *with* India VIX.
  - niftyindices `Backpage.aspx` historical API   → returns HTML, endpoint gone.
So Nov 2007 → 13 May 2014 has no reachable free source. Those dates get
`india_vix = NULL, vix_available = False`. SPEC OQ5's 2008-epoch substitution is
therefore mandatory, and its scope is wider than SPEC assumes: it covers the
taper-2013 epoch too. Do not fill this gap with a proxy inside this module —
whatever substitution the team agrees on belongs in C4/C7, labelled as such.

LOOK-AHEAD LEAKAGE — the alignment rule (resolves a SPEC [GAP])
---------------------------------------------------------------
SPEC §6 E4 records `[GAP] — no alignment rule for mixing publication
frequencies inside z_t`. AGENTS.md §9 forbids silently inventing a value, so the
rule is explicit, conservative, recorded in the cache manifest, and needs team
sign-off:

    The value of covariate f on date d is the most recent observation o of f
    with  available_from(o) = period_end(o) + publication_lag(f)  <=  d.
    No interpolation. No back-fill. NULL before f's first publication.

`period_end` is the end of the observation's *period* (month-end for a monthly
point dated to the 1st, quarter-end for a quarterly one), never its label. A
monthly observation dated 2026-07-01 describes all of July and cannot be known
on 1 July. Collapsing that distinction is the most common way a macro panel
leaks, so the period arithmetic is done explicitly in `period_end()`.

The lags in `_SERIES` are deliberately pessimistic. An over-long lag only
discards information; an under-long one fabricates foresight. Never tune a lag
down to improve a downstream metric.

REVISION HISTORY IS NOT PRESERVED — and cannot be, by this route
----------------------------------------------------------------
`fredgraph.csv` serves the *latest revised* vintage. BIS NEER and BIS credit are
both revised. E4 has no vintage column, so a value written today may differ from
what a forecaster could have seen at the time. The raw fetched bytes are cached
with a sha256 manifest so any row is reproducible back to the exact download,
but that is an audit trail, not a point-in-time vintage. True vintages need
ALFRED plus an E4 schema change — both out of scope here.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests

from seraph.shared_types import (
    IST,
    IngestBatch,
    MacroRow,
    SeraphWarning,
    SourceBlocked,
    SourceUnavailable,
    ist_timestamp,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = _REPO_ROOT / "artefacts" / "macro_raw"
DEFAULT_VIX_FILE = (
    _REPO_ROOT / "vendor" / "eod2" / "src" / "eod2_data" / "daily" / "india vix.csv"
)

FRED_CSV_ROOT = "https://fred.stlouisfed.org/graph/fredgraph.csv"
NSE_INDEX_ARCHIVE = "https://nsearchives.nseindia.com/content/indices"
NSE_VIX_API = "https://www.nseindia.com/api/historical/vixhistory"

CORPUS_START = "2005-01-01"

#: Trading-calendar reference symbols. A date is an NSE trading day if any of
#: these traded on it — four long-lived large caps rather than one, so a single
#: symbol's suspension or rename cannot punch holes in E4's date axis.
CALENDAR_SYMBOLS = ("RELIANCE", "INFY", "ITC", "SBIN")

#: India VIX's first reachable observation — see the module docstring. Dates
#: before this are NULL/unavailable, never proxied.
VIX_FIRST_AVAILABLE = "2014-05-14"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

#: Seconds to wait between *network* fetches (cache hits do not wait).
#: Measured 2026-10-12: FRED serves a single CSV in ~0.5 s, but four
#: back-to-back requests trip an adaptive rate limit that then read-times-out
#: every subsequent request for minutes. Retrying harder makes it worse. The
#: whole covariate set is five files fetched once a day, so a generous gap costs
#: nothing and is the difference between the client working and not.
_REQUEST_GAP_S = 20.0

#: Total wall-clock budget for one response body. Separate from the socket
#: timeout because `requests`' timeout is per-read and a trickling server
#: resets it indefinitely — see `_Fetcher._fetch_once`. The largest covariate
#: CSV is ~170 KB and normally arrives in well under a second.
_TOTAL_DEADLINE_S = 45.0


@dataclass(frozen=True)
class MacroSeries:
    """Declarative provenance for one E4 column. Everything a reader needs in
    order to audit or dispute the series lives here, not in prose."""

    field: str                  # E4 / MacroRow field name
    provider: str               # "fred" | "eod2-index"
    series_id: str
    units: str
    native_frequency: str       # "business-daily" | "monthly" | "quarterly"
    period: str                 # "day" | "month" | "quarter"
    publication_lag_days: int   # added to period_end → available_from
    transform: str              # "level" | "yoy_pct_4q"
    fidelity: str               # "exact" | "substitute"
    licence: str
    note: str


#: FR3's covariate set. `fidelity="substitute"` is a claim about the *construct*,
#: not about data quality — every value is genuine published data.
_SERIES: tuple[MacroSeries, ...] = (
    MacroSeries(
        field="brent_price", provider="fred", series_id="DCOILBRENTEU",
        units="USD per barrel", native_frequency="business-daily", period="day",
        # FRED refreshes the EIA spot series weekly; 7 days keeps every row
        # strictly behind a refresh boundary.
        publication_lag_days=7, transform="level", fidelity="exact",
        licence="FRED/EIA — public domain, free redistribution",
        note="Brent spot FOB, EIA via FRED. Matches FR3 exactly.",
    ),
    MacroSeries(
        field="rbi_repo_rate", provider="fred", series_id="IRSTCI01INM156N",
        units="percent per annum", native_frequency="monthly", period="month",
        publication_lag_days=30, transform="level", fidelity="substitute",
        licence="FRED/OECD MEI — free for non-commercial use",
        note="Monthly AVERAGE central-bank policy rate for India. Not RBI's "
             "dated repo step; a mid-month change smears across two points.",
    ),
    MacroSeries(
        field="inr_twi", provider="fred", series_id="NBINBIS",
        units="index, 2020=100", native_frequency="monthly", period="month",
        publication_lag_days=30, transform="level", fidelity="substitute",
        licence="FRED/BIS — free for non-commercial use, BIS attribution required",
        note="BIS broad NOMINAL effective exchange rate for India. Same "
             "construct as RBI's NEER, different basket and base.",
    ),
    MacroSeries(
        field="bank_credit_growth_yoy", provider="fred", series_id="CRDQINAPABIS",
        units="percent YoY", native_frequency="quarterly", period="quarter",
        # BIS credit statistics publish roughly 4.5 months after quarter end.
        publication_lag_days=135, transform="yoy_pct_4q", fidelity="substitute",
        licence="FRED/BIS — free for non-commercial use, BIS attribution required",
        note="4-quarter pct change of BIS credit to the private non-financial "
             "sector FROM BANKS (INR bn). Not RBI weekly non-food bank credit: "
             "quarterly, broader scope, long publication lag.",
    ),
    MacroSeries(
        field="india_vix", provider="eod2-index", series_id="india vix",
        units="index points, annualised vol", native_frequency="business-daily",
        period="day",
        # A session's close is known that evening; usable from the next day.
        publication_lag_days=1, transform="level", fidelity="exact",
        licence="NSE via EOD2 (MIT) — NSE terms restrict redistribution",
        note=f"NSE India VIX close. Reachable history starts {VIX_FIRST_AVAILABLE}; "
             "Nov-2007→May-2014 unavailable from free sources (SPEC OQ5).",
    ),
)

SERIES_BY_FIELD: dict[str, MacroSeries] = {s.field: s for s in _SERIES}

#: The alignment rule, recorded verbatim in the manifest so a result can always
#: be traced to the convention that produced it.
ALIGNMENT_RULE = (
    "as-of forward-fill: value(f, d) = latest observation o of f with "
    "period_end(o) + publication_lag(f) <= d; no interpolation, no back-fill, "
    "NULL before first publication. Resolves SPEC E4 [GAP]; pending team sign-off."
)


# --- observations ---------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    """One source datum, at its native grain, with its units unchanged.

    `value is None` means the source published a gap (FRED's "." sentinel) —
    distinct from "we have no observation at all for this period", which is
    represented by the absence of an Observation.
    """

    period_start: date
    period_end: date
    value: float | None

    @property
    def label(self) -> date:
        """The date the source puts on the row (period start, for FRED)."""
        return self.period_start


def period_end(label: date, period: str) -> date:
    """End of the observation period a source row describes.

    FRED labels monthly rows with the 1st and quarterly rows with the first day
    of the quarter. Treating that label as the moment the value became knowable
    is the classic macro look-ahead bug, so the period is closed explicitly.
    """
    if period == "day":
        return label
    if period == "month":
        nxt = date(label.year + (label.month == 12), (label.month % 12) + 1, 1)
        return nxt - timedelta(days=1)
    if period == "quarter":
        q_start_month = ((label.month - 1) // 3) * 3 + 1
        end_month = q_start_month + 3
        year = label.year + (end_month > 12)
        end_month = (end_month - 1) % 12 + 1
        return date(year, end_month, 1) - timedelta(days=1)
    raise ValueError(f"unknown period {period!r}")


def available_from(obs: Observation, series: MacroSeries) -> date:
    """First date on which `obs` could have been acted on."""
    return obs.period_end + timedelta(days=series.publication_lag_days)


# --- FRED ----------------------------------------------------------------


def parse_fred_csv(
    text: str, series_id: str, series: MacroSeries
) -> tuple[Observation, ...]:
    """FRED CSV → native-grain observations, units untouched.

    FRED's current header is `observation_date,<SERIES_ID>`; older downloads
    used `DATE`. Missing values arrive as "." (and, defensively, as empty). Both
    are kept as `value=None` rather than dropped: a published gap is
    information, and dropping it would let the previous value carry across it.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return ()
    if len(header) < 2:
        raise ValueError(f"FRED CSV for {series_id} has no value column: {header!r}")
    if header[0].strip().lower() not in {"observation_date", "date"}:
        raise ValueError(
            f"unexpected FRED date column {header[0]!r} for {series_id} "
            "— the download format changed; re-check the parser"
        )
    if header[1].strip().upper() != series_id.upper():
        raise ValueError(f"FRED returned series {header[1]!r}, expected {series_id!r}")

    out: list[Observation] = []
    for row in reader:
        if not row or not row[0].strip():
            continue
        label = date.fromisoformat(row[0].strip())
        raw = row[1].strip() if len(row) > 1 else ""
        value = None if raw in {"", "."} else float(raw)
        out.append(Observation(label, period_end(label, series.period), value))
    return tuple(out)


def yoy_pct_4q(obs: tuple[Observation, ...]) -> tuple[Observation, ...]:
    """4-period percentage change of a level series.

    Availability is governed by the *later* of the two levels, which is the
    current observation — so the derived point inherits its period_end and the
    lag arithmetic stays correct without special-casing.
    """
    out: list[Observation] = []
    for i in range(4, len(obs)):
        now, then = obs[i], obs[i - 4]
        if now.value is None or then.value is None or then.value == 0:
            out.append(Observation(now.period_start, now.period_end, None))
            continue
        out.append(Observation(
            now.period_start, now.period_end,
            100.0 * (now.value - then.value) / then.value,
        ))
    return tuple(out)


# --- India VIX -----------------------------------------------------------


def parse_eod2_index_csv(text: str) -> tuple[Observation, ...]:
    """EOD2 index CSV (`Date,Open,High,Low,Close,...`) → close observations.

    Later EOD2 rows carry the literal string "nan" in unrelated columns; only
    Date and Close are read, and a non-numeric Close is a published gap.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "Date" not in reader.fieldnames:
        raise ValueError(f"not an EOD2 index CSV: header={reader.fieldnames!r}")
    if "Close" not in reader.fieldnames:
        raise ValueError("EOD2 index CSV has no Close column")
    out: list[Observation] = []
    for row in reader:
        raw_date = (row.get("Date") or "").strip()
        if not raw_date:
            continue
        label = date.fromisoformat(raw_date)
        raw = (row.get("Close") or "").strip()
        try:
            value: float | None = float(raw)
        except ValueError:
            value = None
        if value is not None and value != value:      # NaN
            value = None
        out.append(Observation(label, label, value))
    return tuple(out)


def parse_nse_index_close_all(
    text: str, index_name: str = "India VIX"
) -> Observation | None:
    """One row out of `ind_close_all_<ddmmyyyy>.csv`.

    Columns: Index Name, Index Date (dd-mm-yyyy), Open, High, Low, Close, …
    NSE's own "-" placeholder becomes a published gap. Returns None when the
    file carries no row for `index_name` — the real situation for India VIX
    before 2014-05-15, and not an error.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return None
    if not header or header[0].strip().lower() != "index name":
        raise ValueError(f"not an NSE ind_close_all CSV: header={header[:3]!r}")
    for row in reader:
        if len(row) < 6 or row[0].strip().lower() != index_name.lower():
            continue
        label = datetime.strptime(row[1].strip(), "%d-%m-%Y").date()
        raw = row[5].strip()
        value = None if raw in {"", "-"} else float(raw)
        return Observation(label, label, value)
    return None


# --- HTTP ----------------------------------------------------------------


def _fetch_tag(url: str) -> str:
    """Short stable tag for a URL — used to name fetch threads so a stuck
    fetch is identifiable in a stack dump."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]


class _HostAlreadyDead(Exception):
    """Cause used when the circuit breaker refuses a fetch outright, so the
    provenance record says "not attempted" rather than reporting another
    series' failure as this one's."""

    def __init__(self, host: str, first: Exception):
        super().__init__(
            f"not attempted: {host} already exhausted its retries earlier in "
            f"this run (first failure there: {first})"
        )
        self.host, self.first = host, first


class _Blocked(Exception):
    def __init__(self, url: str, status: int):
        super().__init__(f"blocked ({status}): {url}")
        self.url, self.status = url, status


class _NotFound(Exception):
    pass


class _Unavailable(Exception):
    def __init__(self, url: str, cause: Exception | None):
        super().__init__(f"unavailable after retries: {url} ({cause})")
        self.url, self.cause = url, cause


class _Fetcher:
    """Retrying GET with a raw-bytes cache, an inter-request gap and a total
    response deadline.

    All three exist because of measured source behaviour, not caution. FRED
    serves a covariate CSV in ~0.5 s cold, but four back-to-back requests trip
    an adaptive rate limit; once tripped it does not refuse requests, it
    *trickles* them, which defeats a per-read socket timeout entirely. NSE
    fails often and blocks non-residential IPs outright. The cached bytes plus
    their sha256 are the provenance record behind every row written, and make a
    re-run free rather than another chance to get throttled.
    """

    def __init__(self, cache_dir: Path, *, refresh: bool = False,
                 attempts: int = 5, timeout: int = 90,
                 gap_s: float = _REQUEST_GAP_S,
                 deadline_s: float = _TOTAL_DEADLINE_S):
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.attempts = attempts
        self.timeout = timeout
        self.gap_s = gap_s
        self.deadline_s = deadline_s
        self.manifest: list[dict] = []
        self._last_fetch: float | None = None
        #: Hosts that have already exhausted their retries in this run. A
        #: sustained block (FRED blocked this IP for 25+ min on 2026-10-12)
        #: otherwise costs `attempts × deadline` per series — five minutes each,
        #: four series, for an answer the first series already gave. Covariates
        #: are fetched once per host, so one exhausted host means the rest of
        #: its series will fail too.
        self._dead_hosts: dict[str, Exception] = {}
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})

    def _fetch_once(self, url: str, headers: dict) -> requests.Response:
        """One GET under a TOTAL wall-clock deadline.

        `requests`' `timeout` is per-socket-read, not a budget for the whole
        response, so a server that dribbles a few bytes at a time resets it
        indefinitely: a nominal 30 s timeout hung for over fifteen minutes
        against a throttling FRED. Streaming with an in-loop clock check does
        NOT fix that either — `iter_content(chunk_size=N)` blocks until a full
        N bytes arrive, so with a slow trickle the check never runs. (Both of
        those were tried here; the test
        `test_total_deadline_aborts_a_trickling_source` pins the behaviour.)

        The only bound that holds regardless of how the bytes arrive is an
        external clock, so the request runs on a worker thread and we wait at
        most `deadline_s` for it. An abandoned thread stays parked on its
        socket until the process exits; that is acceptable because a run makes
        a handful of requests and then terminates, and the alternative is a
        cron job that hangs forever instead of failing.
        """
        import threading

        box: dict[str, object] = {}

        def work() -> None:
            try:
                box["r"] = self._session.get(
                    url, headers=headers, timeout=self.timeout
                )
            except BaseException as e:                      # noqa: BLE001
                box["e"] = e

        t = threading.Thread(target=work, daemon=True,
                             name=f"macro-fetch-{_fetch_tag(url)}")
        t.start()
        t.join(self.deadline_s)
        if t.is_alive():
            raise requests.Timeout(
                f"total deadline {self.deadline_s}s exceeded for {url} "
                "(source accepted the connection but is trickling the body)"
            )
        if "e" in box:
            raise box["e"]                                  # type: ignore[misc]
        return box["r"]                                     # type: ignore[return-value]

    def get(self, url: str, cache_name: str, *, referer: str | None = None) -> str:
        path = self.cache_dir / cache_name
        if path.exists() and not self.refresh:
            data = path.read_bytes()
            self._record(url, cache_name, data, cached=True)
            return data.decode("utf-8", errors="replace")

        host = urlsplit(url).netloc
        if host in self._dead_hosts:
            # Attribute this correctly: the sibling never got its own attempt.
            # Naming the original cause without saying so would put "deadline
            # exceeded for <other URL>" in this series' provenance record.
            raise _Unavailable(url, _HostAlreadyDead(host, self._dead_hosts[host]))

        # Space out network fetches. Cache hits above never reach here, so a
        # re-run off a warm cache pays nothing.
        if self._last_fetch is not None:
            waited = time.monotonic() - self._last_fetch
            if waited < self.gap_s:
                time.sleep(self.gap_s - waited)

        headers = {"Referer": referer} if referer else {}
        last: Exception | None = None

        def backoff(attempt: int) -> None:
            # A timeout here usually means the rate limit has already tripped,
            # and it stays tripped for minutes — so back off by at least the
            # inter-request gap, not by a sub-second exponent. Never sleep after
            # the final attempt: nothing follows it but the raise.
            if attempt < self.attempts - 1:
                time.sleep(max(2.0 ** attempt, self.gap_s))

        for attempt in range(self.attempts):
            self._last_fetch = time.monotonic()
            try:
                r = self._fetch_once(url, headers)
            except requests.RequestException as e:
                last = e
                backoff(attempt)
                continue
            if r.status_code == 200:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                self._record(url, cache_name, r.content, cached=False)
                return r.text
            if r.status_code in (403, 503):
                # NSE's Akamai block. Non-retryable by design — burning retries
                # on it only makes a hard block look like flakiness in the logs.
                raise _Blocked(url, r.status_code)
            if r.status_code == 404:
                raise _NotFound(url)
            last = requests.HTTPError(f"{r.status_code} for {url}")
            backoff(attempt)
        # Retries exhausted: trip the breaker so sibling series on this host
        # fail immediately instead of re-proving the same block.
        self._dead_hosts[host] = last or requests.RequestException("unknown")
        raise _Unavailable(url, last)

    def _record(self, url: str, name: str, data: bytes, *, cached: bool) -> None:
        self.manifest.append({
            "url": url,
            "cacheFile": name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "fetchedAt": ist_timestamp(datetime.now(IST)),
            "servedFromCache": cached,
        })


def fetch_series(fetcher: _Fetcher, series: MacroSeries) -> tuple[Observation, ...]:
    """One FRED MacroSeries → native-grain observations, transform applied."""
    if series.provider != "fred":
        raise ValueError(f"{series.field}: fetch_series handles FRED only")
    text = fetcher.get(
        f"{FRED_CSV_ROOT}?id={series.series_id}", f"fred_{series.series_id}.csv"
    )
    obs = parse_fred_csv(text, series.series_id, series)
    if series.transform == "yoy_pct_4q":
        obs = yoy_pct_4q(obs)
    elif series.transform != "level":
        raise ValueError(f"unknown transform {series.transform!r}")
    return obs


def load_vix(vix_file: Path = DEFAULT_VIX_FILE) -> tuple[Observation, ...]:
    """India VIX from the vendored EOD2 snapshot.

    `vendor/` is gitignored, so this needs an EOD2 sync to have been run — the
    same precondition `eod2_client.py` already carries. A missing file is a
    source problem, not a parse problem, and is reported as such.
    """
    if not vix_file.exists():
        raise FileNotFoundError(
            f"India VIX file not found at {vix_file} — run the EOD2 vendor sync "
            "(vendor/ is gitignored, so it is absent on a fresh clone)"
        )
    return parse_eod2_index_csv(vix_file.read_text(encoding="utf-8"))


def fetch_vix_topup(
    fetcher: _Fetcher, day: date
) -> Observation | None:
    """One trading day's India VIX from the NSE index archive.

    Extends the EOD2 snapshot forward without touching the Akamai-blocked
    website API. Returns None when the archive has no India VIX row for that
    day (weekend, holiday, or pre-2014-05-15).
    """
    stamp = day.strftime("%d%m%Y")
    try:
        text = fetcher.get(
            f"{NSE_INDEX_ARCHIVE}/ind_close_all_{stamp}.csv",
            f"nse_ind_close_all_{stamp}.csv",
            referer="https://www.nseindia.com/",
        )
    except _NotFound:
        return None
    return parse_nse_index_close_all(text)


def probe_nse_vix_api(fetcher: _Fetcher) -> SeraphWarning | None:
    """Confirm, rather than assume, that the documented NSE VIX endpoint is
    blocked. Recorded as a warning so the limitation is evidenced per run, and
    so it will be noticed if NSE ever reopens the endpoint."""
    try:
        fetcher.get(
            f"{NSE_VIX_API}?from=01-01-2010&to=31-01-2010",
            "nse_vixhistory_probe.json",
            referer="https://www.nseindia.com/",
        )
    except _Blocked as e:
        return SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=f"NSE historical VIX API blocked (HTTP {e.status}) — India VIX "
                    f"history limited to the EOD2 snapshot from {VIX_FIRST_AVAILABLE}",
            context={"source": "nse-vixhistory", "httpStatus": e.status},
        )
    except (_NotFound, _Unavailable):
        return SeraphWarning(
            code="PARTIAL_COVERAGE",
            message="NSE historical VIX API unreachable — India VIX history "
                    "limited to the EOD2 snapshot",
            context={"source": "nse-vixhistory"},
        )
    return None


# --- alignment -----------------------------------------------------------


def align_as_of(
    observations: dict[str, tuple[Observation, ...]],
    trading_dates: tuple[date, ...],
) -> dict[date, dict[str, float | None]]:
    """Apply ALIGNMENT_RULE. This is the leakage boundary of the whole module.

    Walks each series once in availability order against the sorted target axis,
    so the value placed at `d` is the last one whose `available_from <= d`. A
    published gap (`value=None`) still advances the cursor: the gap is the
    latest thing known, and carrying the prior value past it would invent
    continuity the source does not claim.
    """
    out: dict[date, dict[str, float | None]] = {d: {} for d in trading_dates}
    for field, obs in observations.items():
        series = SERIES_BY_FIELD[field]
        ready = sorted(
            ((available_from(o, series), o.value) for o in obs), key=lambda t: t[0]
        )
        i: int = 0
        current: float | None = None
        for d in trading_dates:
            while i < len(ready) and ready[i][0] <= d:
                current = ready[i][1]
                i += 1
            out[d][field] = current
    return out


def align_native(
    observations: dict[str, tuple[Observation, ...]],
) -> dict[date, dict[str, float | None]]:
    """Alternative to ALIGNMENT_RULE: every observation at its own label date,
    nothing carried forward. Sparse and NULL-heavy by construction — the
    unaligned panel, for anyone who wants to apply their own convention."""
    out: dict[date, dict[str, float | None]] = {}
    for field, obs in observations.items():
        for o in obs:
            out.setdefault(o.label, {})[field] = o.value
    return out


def compose_rows(
    aligned: dict[date, dict[str, float | None]],
    *,
    preserve: dict[str, tuple[float | None, float | None]] | None = None,
) -> tuple[MacroRow, ...]:
    """Aligned values → E4 rows.

    `preserve` carries C4's `g_t` / `g_t_sector_weighted` for dates already in
    E4, keyed by ISO date. C1's E4 upsert sets *every* non-key column from the
    incoming row, so composing without this would null out FR22's output on a
    macro re-run. The proper fix is a partial-column upsert in C1; this is the
    in-lane workaround.
    """
    preserve = preserve or {}
    rows: list[MacroRow] = []
    for d in sorted(aligned):
        vals = aligned[d]
        iso = d.isoformat()
        g_t, g_t_sw = preserve.get(iso, (None, None))
        vix = vals.get("india_vix")
        rows.append(MacroRow(
            date=iso,
            rbi_repo_rate=vals.get("rbi_repo_rate"),
            bank_credit_growth_yoy=vals.get("bank_credit_growth_yoy"),
            india_vix=vix,
            # vix_available tracks the datum, not the calendar: True iff a real
            # VIX close is carried on this row.
            vix_available=vix is not None,
            inr_twi=vals.get("inr_twi"),
            brent_price=vals.get("brent_price"),
            g_t=g_t,
            g_t_sector_weighted=g_t_sw,
        ))
    return tuple(rows)


def coverage_report(rows: tuple[MacroRow, ...]) -> dict[str, dict[str, object]]:
    """Per-field non-null coverage. Printed every run so a silently empty
    covariate cannot pass for an ingested one."""
    report: dict[str, dict[str, object]] = {}
    for s in _SERIES:
        present = [r.date for r in rows if getattr(r, s.field) is not None]
        report[s.field] = {
            "nonNull": len(present),
            "total": len(rows),
            "firstDate": present[0] if present else None,
            "lastDate": present[-1] if present else None,
            "fidelity": s.fidelity,
        }
    return report


# --- orchestration -------------------------------------------------------


async def _trading_calendar(
    from_date: str, to_date: str, symbols: tuple[str, ...] = CALENDAR_SYMBOLS
) -> tuple[date, ...]:
    """NSE trading days from E3, via S2 — the real calendar, holidays included.

    E3 is C2's own entity and the read goes through StoreReader as published
    (no reach-in). The union of several reference symbols is used so one
    symbol's suspension cannot punch a hole in E4's axis.
    """
    from seraph.store import StoreReader

    reader = await StoreReader.connect()
    try:
        res = await reader.daily_bars(
            symbols=symbols, from_date=from_date, to_date=to_date
        )
        if res.status != "ok":
            raise RuntimeError(f"trading calendar unavailable: {res.error}")
        return tuple(sorted({date.fromisoformat(b.date) for b in res.value}))
    finally:
        await reader.close()


async def _existing_derived(
    from_date: str, to_date: str
) -> dict[str, tuple[float | None, float | None]]:
    """C4's FR22 columns already in E4, so a re-run preserves them."""
    from seraph.store import StoreReader

    reader = await StoreReader.connect()
    try:
        res = await reader.macro_covariates(from_date=from_date, to_date=to_date)
        if res.status != "ok":
            raise RuntimeError(f"cannot read existing E4: {res.error}")
        return {
            r.date: (r.g_t, r.g_t_sector_weighted)
            for r in res.value
            if r.g_t is not None or r.g_t_sector_weighted is not None
        }
    finally:
        await reader.close()


async def backfill(
    *,
    from_date: str = CORPUS_START,
    to_date: str | None = None,
    alignment: str = "asof",
    cache_dir: Path = DEFAULT_CACHE_DIR,
    vix_file: Path = DEFAULT_VIX_FILE,
    refresh: bool = False,
    dry_run: bool = False,
    probe_blocked: bool = True,
) -> dict:
    """Fetch → align → compose → write E4. Idempotent end to end (CT-1
    semantics): an identical re-run reports `inserted: 0`."""
    to_date = to_date or date.today().isoformat()
    fetcher = _Fetcher(cache_dir, refresh=refresh)
    warnings: list[SeraphWarning] = []

    observations: dict[str, tuple[Observation, ...]] = {}
    failures: dict[str, str] = {}
    for series in _SERIES:
        try:
            if series.provider == "fred":
                observations[series.field] = fetch_series(fetcher, series)
            elif series.provider == "eod2-index":
                observations[series.field] = load_vix(vix_file)
            else:
                raise ValueError(f"unhandled provider {series.provider!r}")
        except _Blocked as e:
            failures[series.field] = f"SOURCE_BLOCKED {e.status}"
            print(f"[macro] BLOCKED {series.field}: "
                  f"{SourceBlocked(source=series.series_id)}", flush=True)
        except (_NotFound, _Unavailable, FileNotFoundError, OSError) as e:
            failures[series.field] = f"SOURCE_UNAVAILABLE {e}"
            print(f"[macro] UNAVAILABLE {series.field}: "
                  f"{SourceUnavailable(source=series.series_id)} ({e})", flush=True)
        except ValueError as e:
            # The source's published format disagrees with the parser. Do not
            # fall back to anything — a changed schema must be looked at.
            failures[series.field] = f"SCHEMA_MISMATCH {e}"
            print(f"[macro] SCHEMA {series.field}: {e}", flush=True)

    if failures:
        warnings.append(SeraphWarning(
            code="PARTIAL_COVERAGE",
            message="covariates missing from this run: " + ", ".join(sorted(failures)),
            context=dict(failures),
        ))
    if probe_blocked:
        w = probe_nse_vix_api(fetcher)
        if w:
            warnings.append(w)

    if not observations:
        return {"status": "error", "reason": "no covariate could be fetched",
                "failures": failures}

    if alignment == "asof":
        trading_dates = await _trading_calendar(from_date, to_date)
        if not trading_dates:
            return {"status": "error",
                    "reason": f"no E3 trading days in {from_date}..{to_date} — "
                              "load daily_prices before aligning macro data"}
        aligned = align_as_of(observations, trading_dates)
    elif alignment == "native":
        lo, hi = date.fromisoformat(from_date), date.fromisoformat(to_date)
        aligned = {d: v for d, v in align_native(observations).items() if lo <= d <= hi}
    else:
        raise ValueError(f"alignment must be 'asof' or 'native', got {alignment!r}")

    preserve = {}  # C1 excludes C4-owned fields atomically; no read/merge race.
    rows = compose_rows(aligned, preserve=preserve)

    manifest = {
        "runId": f"macro-{datetime.now(IST).strftime('%Y%m%dT%H%M%S')}",
        "generatedAt": ist_timestamp(datetime.now(IST)),
        "alignment": alignment,
        "alignmentRule": ALIGNMENT_RULE,
        "window": {"from": from_date, "to": to_date},
        "series": [
            {
                "field": s.field, "provider": s.provider, "seriesId": s.series_id,
                "units": s.units, "nativeFrequency": s.native_frequency,
                "publicationLagDays": s.publication_lag_days,
                "transform": s.transform, "fidelity": s.fidelity,
                "licence": s.licence, "note": s.note,
                "observations": len(observations.get(s.field, ())),
                "failure": failures.get(s.field),
            }
            for s in _SERIES
        ],
        "downloads": fetcher.manifest,
        "coverage": coverage_report(rows),
        "revisionHistory": "NOT PRESERVED — fredgraph.csv serves latest-revised "
                           "vintages only; E4 has no vintage column.",
        "warnings": [w.model_dump(by_alias=True) for w in warnings],
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )

    result: dict = {
        "status": "ok", "rows": len(rows), "alignment": alignment,
        "coverage": manifest["coverage"], "failures": failures,
        "warnings": [w.message for w in warnings],
        "manifest": str(cache_dir / "manifest.json"),
    }
    if dry_run or not rows:
        result["written"] = False
        return result

    from seraph.store import StoreWriter

    writer = await StoreWriter.connect()
    try:
        batch = IngestBatch(
            run_id=manifest["runId"],
            # ARCHITECTURE S1's IngestSource has no literal covering the NSE
            # index archive, so a composed row cannot be labelled per field.
            # "fred" is the majority provider; true per-field provenance lives
            # in the manifest. Adding "nse-index" is a shared-contract change
            # and is deliberately not made here.
            source="fred",
            entity="E4",
            rows=rows,
            watermark=f"{rows[-1].date}T18:00:00+05:30",
            source_schema_version=f"macro-{alignment}-v1",
        )
        # Failed retrievals are absent updates, not authoritative NULLs.
        # Published gaps inside a successfully fetched series remain explicit NULL.
        fields = list(observations)
        if "india_vix" in fields:
            fields.append("vix_available")
        res = await writer.write_batch_bulk(batch, update_fields=fields)
        if res.status != "ok":
            result["status"] = "error"
            result["reason"] = str(res.error)
            return result
        result["written"] = True
        result["inserted"] = res.value.inserted
        result["updated"] = res.value.updated
    finally:
        await writer.close()
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR3 macro covariate ingestion (C2 → E4).")
    p.add_argument("--from", dest="from_date", default=CORPUS_START)
    p.add_argument("--to", dest="to_date", default=None)
    p.add_argument("--alignment", choices=("asof", "native"), default="asof",
                   help="asof = leakage-safe publication-lagged forward fill "
                        "(default); native = observations at their own dates")
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    p.add_argument("--vix-file", type=Path, default=DEFAULT_VIX_FILE)
    p.add_argument("--refresh", action="store_true", help="ignore the raw cache")
    p.add_argument("--dry-run", action="store_true",
                   help="fetch and report, do not write")
    p.add_argument("--no-probe", action="store_true",
                   help="skip the NSE VIX-API block probe")
    a = p.parse_args(argv)
    out = asyncio.run(backfill(
        from_date=a.from_date, to_date=a.to_date, alignment=a.alignment,
        cache_dir=a.cache_dir, vix_file=a.vix_file, refresh=a.refresh,
        dry_run=a.dry_run, probe_blocked=not a.no_probe,
    ))
    print(json.dumps(out, indent=2, default=str), flush=True)
    return 0 if out.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
