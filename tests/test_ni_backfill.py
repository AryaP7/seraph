"""Recovering from downtime, and admitting when recovery is impossible.

A poller down for six hours restarts and fetches "the latest items". Whether
that recovers the gap depends entirely on the source:

* The **Federal Register** API takes an explicit publication-date range and
  pages through it. A gap of any length is recoverable, exactly.
* An **RSS feed** returns the publisher's latest N items. If more than N were
  published during the outage, the earlier ones are *gone* — not delayed.

The dangerous outcome is not the gap; it is a gap nobody records. A console
that resumes showing a tidy list gives no hint that six hours of banking
circulars are missing, and every downstream count is quietly computed over a
corpus with a hole in it.

So the module does two separate things and keeps them separate: it **reports**
every gap, always; and it **backfills** only the sources that genuinely can.
A source that cannot backfill is not a failure of the code — it is a property
of the feed, and saying so is the point.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from seraph.news.acquisition import FetchedItem, FetchResult, NewsStore
from seraph.news.backfill import (
    BACKFILLABLE,
    federal_register_backfill_urls,
    gaps_at,
    plan_backfill,
)
from seraph.news.model import Source

ROOT = pathlib.Path(__file__).resolve().parents[1]
T0 = "2026-10-18T08:00:00+05:30"

_SPEC = importlib.util.spec_from_file_location(
    "run_news_backfill_under_test", ROOT / "scripts/run_news.py")
_RN = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RN)


def at(minutes: int) -> str:
    from datetime import datetime, timedelta
    moment = datetime.strptime(T0, "%Y-%m-%dT%H:%M:%S%z") + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + moment.strftime("%z")[-2:]


def source(source_id: str, minutes: int = 60) -> Source:
    return Source(source_id=source_id, provider="p", kind="regulator",
                  url="https://www.federalregister.gov/api/v1/documents.json?x=1",
                  topic_coverage=("x",), language="en", rights="test",
                  may_store_full_text=True, accessibility_verified=True,
                  poll_interval_minutes=minutes)


def fetcher(n: int = 1):
    def fetch(src, cursor=None):
        return FetchResult(items=tuple(
            FetchedItem(reference=f"r{i}", title=f"Doc {i}",
                        url=f"https://example.invalid/{i}", raw=f"r{i}".encode(),
                        published_at=None, body=None, language="en")
            for i in range(n)))
    return fetch


@pytest.fixture
def store(tmp_path) -> NewsStore:
    return NewsStore(tmp_path / "backfill.sqlite")


# ----------------------------------------------------------- gap detection

def test_a_never_fetched_source_is_a_total_gap(store):
    store.register(source("rbi_press_releases"))
    gap = gaps_at(store, T0)[0]
    assert gap.since is None
    assert "never successfully fetched" in gap.note


def test_a_source_within_its_allowance_has_no_gap(store):
    store.register(source("rbi_press_releases", minutes=60))
    store.ingest("rbi_press_releases", fetcher(), now=T0)
    assert gaps_at(store, at(60)) == []


def test_a_gap_is_reported_before_health_calls_it_stale(store):
    """`coverage_at` allows three intervals before calling a source unhealthy.
    A gap is a statement about COLLECTION, so a source that missed a single
    scheduled poll has a real gap while still counting as healthy — and the
    two must not be conflated."""
    store.register(source("rbi_press_releases", minutes=60))
    store.ingest("rbi_press_releases", fetcher(), now=T0)

    assert gaps_at(store, at(150))          # a gap at 2.5 intervals
    assert store.coverage_at(at(150)).is_complete   # still "healthy"


# ------------------------------------------- recoverable vs permanently lost

def test_the_federal_register_is_recoverable(store):
    store.register(source("federal_register", minutes=120))
    store.ingest("federal_register", fetcher(), now=T0)
    gap = gaps_at(store, at(600))[0]
    assert gap.recoverable is True
    assert "publication-date range" in gap.note


def test_an_rss_feed_gap_is_permanent_and_says_so(store):
    """The honest half. No amount of polling retrieves what rotated out."""
    store.register(source("rbi_press_releases", minutes=30))
    store.ingest("rbi_press_releases", fetcher(), now=T0)
    gap = gaps_at(store, at(600))[0]
    assert gap.recoverable is False
    assert "PERMANENTLY missing" in gap.note
    assert "not merely late" in gap.note
    assert "hole in it" in gap.note


def test_the_backfillable_list_is_a_short_allow_list():
    """Assuming a feed supports date ranges and silently missing items is the
    failure this module exists to prevent, so capability is declared, never
    inferred."""
    assert set(BACKFILLABLE) == {"federal_register", "federal_register_india"}


def test_the_plan_separates_recoverable_from_lost(store):
    store.register(source("federal_register", minutes=60))
    store.register(source("rbi_press_releases", minutes=60))
    for sid in ("federal_register", "rbi_press_releases"):
        store.ingest(sid, fetcher(), now=T0)
    plan = plan_backfill(store, at(600))
    assert plan["recoverable"] == ["federal_register"]
    assert plan["unrecoverable"] == ["rbi_press_releases"]
    assert "cannot be backfilled by any amount of polling" in plan["note"]


# ------------------------------------------------------- the range URLs

def test_the_urls_carry_an_explicit_date_range():
    urls = federal_register_backfill_urls(
        "https://www.federalregister.gov/api/v1/documents.json"
        "?stale=1&order=newest",
        "2026-09-01T00:00:00+05:30", "2026-09-03T00:00:00+05:30")
    assert "conditions[publication_date][gte]=2026-09-01" in urls[0]
    assert "conditions[publication_date][lte]=2026-09-03" in urls[0]
    # The caller's own parameters are KEPT. This assertion used to require
    # them dropped, which is exactly the defect that would have backfilled the
    # entire US federal register into a store that had only ever asked for
    # the India-filtered subset.
    assert "stale=1" in urls[0], "the source's own query was discarded"
    assert "order=newest" not in urls[0], "the replaced parameter survived"


def test_paging_is_bounded():
    """A caller asking for a decade would otherwise issue hundreds of
    requests. A bounded attempt that reports what it missed beats an unbounded
    one that looks complete."""
    urls = federal_register_backfill_urls(
        "https://x.invalid/api", T0, T0, max_pages=4)
    assert len(urls) == 4
    assert "page=1" in urls[0] and "page=4" in urls[-1]


def test_pages_are_ordered_oldest_first():
    """Paging newest-first over a moving corpus revisits and skips rows."""
    urls = federal_register_backfill_urls("https://x.invalid/api", T0, T0)
    assert "order=oldest" in urls[0]


# ------------------------------------------------- the runner's behaviour

def test_a_never_fetched_source_gets_a_bounded_window_not_zero_width():
    """Found by running it: with no `since`, the range was decision_ts to
    decision_ts — zero width — and the backfill silently recovered nothing
    while reporting success."""
    assert _RN.DEFAULT_BACKFILL_DAYS == 7

    # Behavioural, not a grep for a comment: capture the range the runner
    # actually asks for when the source has never been fetched.
    import tempfile
    asked = {}

    def capture(url_builder, since, until):
        asked["since"], asked["until"] = since, until
        def fetch(src, cursor=None):
            from seraph.news.acquisition import FetchResult
            return FetchResult(items=())
        return fetch

    with tempfile.TemporaryDirectory() as tmp:
        db = NewsStore(pathlib.Path(tmp) / "never.sqlite")
        db.register(source("federal_register", minutes=120))
        original = _RN.backfill_fetcher
        _RN.backfill_fetcher = capture
        try:
            _RN.run_backfill(db, T0)
        finally:
            _RN.backfill_fetcher = original

    assert asked["until"] == T0
    span = (__import__("datetime").datetime.strptime(asked["until"], "%Y-%m-%dT%H:%M:%S%z")
            - __import__("datetime").datetime.strptime(asked["since"], "%Y-%m-%dT%H:%M:%S%z"))
    assert span.days == 7, f"expected a bounded 7-day window, got {span}"


def test_a_failed_backfill_is_not_reported_as_nothing_to_recover():
    """"0 recovered" reads as "nothing to recover". A failed fetch is a
    different fact and must not wear the same words — this printed success
    for a run that raised NameError inside the fetcher."""
    runner = (ROOT / "scripts/run_news.py").read_text(encoding="utf-8")
    assert "FAILED" in runner and "The gap is NOT recovered" in runner
    assert "failed_backfills" in runner


def test_backfill_reuses_the_ordinary_ingest_path(store):
    """Dedup, hashing, idempotency, the rights gate and immutability all come
    from `ingest()`. A backfill that bypassed it would be a second, less
    tested write path into the same table."""
    store.register(source("federal_register"))
    first = store.ingest("federal_register", fetcher(3), now=T0)
    second = store.ingest("federal_register", fetcher(3), now=at(1))
    assert first.new_stories == 3
    assert second.new_stories == 0, "a re-run must not duplicate recovered rows"


# ------------------------------ the source's own filters must survive

def test_the_india_filter_is_preserved():
    """`base_url.split("?")[0]` discarded `conditions[term]=India`, so
    backfilling the India-filtered feed would have pulled the entire US
    federal register into a store that never asked for it."""
    india = ("https://www.federalregister.gov/api/v1/documents.json"
             "?per_page=40&order=newest&conditions[term]=India"
             "&fields[]=title&fields[]=abstract")
    url = federal_register_backfill_urls(
        india, "2026-09-01T00:00:00+05:30", "2026-09-03T00:00:00+05:30")[0]
    assert "conditions[term]=India" in url, "the India filter was dropped"
    assert "fields[]=abstract" in url, "requested fields were dropped"
    assert "per_page=100" in url and "per_page=40" not in url


def test_paging_can_resume_from_a_cursor():
    urls = federal_register_backfill_urls(
        "https://x.invalid/api", T0, T0, max_pages=3, start_page=7)
    assert "page=7" in urls[0] and "page=9" in urls[-1]


# --------------------------------- gaps outlive the poll that hid them

def test_a_persisted_gap_survives_the_poll_that_erased_the_evidence(store):
    """Detection read `source_health.last_success_at`, which the first
    successful poll after an outage overwrites. Resuming therefore destroyed
    the record of the outage it was recovering from."""
    store.register(source("rbi_press_releases", minutes=30))
    store.ingest("rbi_press_releases", fetcher(), now=T0)
    later = at(9 * 60)

    from seraph.news.backfill import record_gaps
    assert record_gaps(store, later), "no gap was observed"
    store.ingest("rbi_press_releases", fetcher(), now=later)

    assert gaps_at(store, later) == [], "health-derived detection lost it"
    assert store.open_gaps(), "the persisted gap was lost too"


def test_re_observing_one_outage_does_not_open_a_row_each_time(store):
    store.register(source("rbi_press_releases", minutes=30))
    store.ingest("rbi_press_releases", fetcher(), now=T0)
    from seraph.news.backfill import record_gaps
    for minutes in (120, 150, 180):
        record_gaps(store, at(minutes))
    assert len(store.open_gaps()) == 1


def test_an_unrecoverable_gap_is_settled_not_left_pending(store):
    """The feed cannot reach back that far. The corpus has a known hole, and
    saying so is different from leaving the gap looking pending forever."""
    store.register(source("rbi_press_releases", minutes=30))
    store.ingest("rbi_press_releases", fetcher(), now=T0)
    from seraph.news.backfill import record_gaps
    record_gaps(store, at(600))
    gap = store.open_gaps()[0]
    store.close_gap(gap["gap_id"], state="unrecoverable", note="cannot reach back")
    assert store.open_gaps() == []


def test_a_truncated_backfill_keeps_a_continuation_cursor(store):
    """Stopping at a page cap and reporting success claims an interval was
    covered when it was not."""
    store.register(source("federal_register", minutes=120))
    store.ingest("federal_register", fetcher(), now=T0)
    from seraph.news.backfill import record_gaps
    record_gaps(store, at(600))
    gap = store.open_gaps("federal_register")[0]

    store.advance_gap(gap["gap_id"], next_page=11, recovered=250)
    resumed = store.open_gaps("federal_register")[0]
    assert resumed["next_page"] == 11
    assert resumed["recovered_stories"] == 250
    assert resumed["covered_until"] is None, "the interval is not yet covered"


def test_a_gap_closes_only_when_its_interval_is_covered(store):
    store.register(source("federal_register", minutes=120))
    store.ingest("federal_register", fetcher(), now=T0)
    from seraph.news.backfill import record_gaps
    record_gaps(store, at(600))
    gap = store.open_gaps("federal_register")[0]
    store.advance_gap(gap["gap_id"], covered_until=gap["until"], recovered=10)
    store.close_gap(gap["gap_id"], state="recovered")
    assert store.open_gaps("federal_register") == []


def test_catch_up_records_gaps_before_it_polls():
    """Order matters: polling first overwrites the health timestamps that gap
    detection reads."""
    runner = (ROOT / "scripts/run_news.py").read_text(encoding="utf-8")
    block = runner.split("if args.catch_up:", 1)[1][:1200]
    assert block.index("record_gaps") < block.index("_work_forced"), (
        "catch-up polls before recording gaps again")


def test_the_historical_backfill_does_not_block_startup():
    """A catch-up launch still recovers gaps -- but after current news is
    serving, not before it.

    Both ran under one 300-second catch-up deadline. On a real roster that
    expires while the backfill is still working, `worker_state` reports
    `stalled`, and the supervisor terminates a worker that was doing
    exactly what it was asked to. Startup is also the worst place for an
    unbounded recovery of old pages: nothing on screen can update until it
    finishes.
    """
    runner = (ROOT / "scripts/run_news.py").read_text(encoding="utf-8")
    catch_up = runner.split("if args.catch_up:", 1)[1].split("owned = store.claim", 1)[0]
    assert "resume_backfills" not in catch_up, (
        "the historical backfill is back on the blocking startup path")
    assert "resume_backfills" in runner, "the backfill must still happen"
    deferred = runner.split("if args.catch_up and passes == 1:", 1)
    assert len(deferred) == 2, "the backfill is no longer deferred into the loop"
    assert "resume_backfills" in deferred[1][:1200]
    assert "_deadline_in" in deferred[1][:1200], (
        "a long recovery must declare its own deadline, or it cannot be "
        "told apart from a hung worker")
