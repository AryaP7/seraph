"""Display refresh, acquisition and progress are three different operations.

The console's 30-second timer fired `news_refresh`, and `news_refresh` was
wired to force every source. So every open browser tab forced all eleven
sources every thirty seconds, inside the web process, multiplied by the number
of sessions. Conflating "re-render the page" with "contact every publisher" is
the defect these tests exist to stop recurring.

  project   re-read the store and re-render. No network. The timer does this.
  acquire   ASK for acquisition. Coalesced and rate-limited in the store, and
            normally served by the worker that already owns the sources.
  progress  what the current or last request is doing.

The second half is about the deadline. Checking elapsed time *between*
sources constrains nothing — one feed that accepts the connection and then
stops sending holds the pass open for as long as it likes — so the remaining
budget has to reach the socket, and the retry loop has to respect it too.
"""
from __future__ import annotations

import pathlib
import time

import pytest

from seraph.news.acquisition import FetchedItem, FetchResult, NewsStore
from seraph.news.model import Source
from seraph.news.refresh import _per_source_timeout, acquire

ROOT = pathlib.Path(__file__).resolve().parents[1]
T0 = "2026-10-18T08:00:00+05:30"


def source(source_id: str, minutes: int = 60) -> Source:
    return Source(source_id=source_id, provider="p", kind="regulator",
                  url=f"https://example.invalid/{source_id}",
                  topic_coverage=("x",), language="en", rights="test",
                  may_store_full_text=False, accessibility_verified=True,
                  poll_interval_minutes=minutes)


def fetcher(n: int = 1):
    def fetch(src, cursor=None):
        return FetchResult(items=tuple(
            FetchedItem(reference=f"{src.source_id}-{i}", title=f"Doc {i}",
                        url=f"https://example.invalid/{src.source_id}/{i}",
                        raw=f"{src.source_id}-{i}".encode(), published_at=None,
                        body=None, language="en")
            for i in range(n)))
    return fetch


class Clock:
    """Advances a fixed amount per reading, so budget behaviour is asserted
    rather than waited out."""

    def __init__(self, step: float = 0.0):
        self.t, self.step = 0.0, step

    def __call__(self) -> float:
        value = self.t
        self.t += self.step
        return value


@pytest.fixture
def store(tmp_path) -> NewsStore:
    db = NewsStore(tmp_path / "refresh.sqlite")
    for sid in ("a", "b", "c"):
        db.register(source(sid))
    return db


# ----------------------------------- a request is not an acquisition

def test_two_tabs_asking_together_produce_one_acquisition(store):
    """Coalescing happens in the STORE, the only place that can see both
    sessions. This is what stops N tabs becoming N fetch storms."""
    first = store.request_acquisition(now=T0)
    second = store.request_acquisition(now=T0)
    assert first["coalesced"] is False
    assert second["coalesced"] is True
    assert second["request_id"] == first["request_id"]


def test_a_second_worker_cannot_claim_the_same_request(store):
    store.request_acquisition(now=T0)
    assert store.claim_acquisition(worker="one") is not None
    assert store.claim_acquisition(worker="two") is None


def test_asking_again_too_soon_is_refused_with_a_retry_time(store):
    """The sources have not changed in ten seconds, and saying so is more
    useful than contacting them again."""
    asked = store.request_acquisition(now=T0)
    claim = store.claim_acquisition(worker="w", now=T0)
    store.finish_acquisition(asked["request_id"], claim_token=claim['claim_token'], progress={}, now=T0)
    again = store.request_acquisition(now="2026-10-18T08:00:10+05:30")
    assert again["state"] == "rate_limited"
    assert again["retry_after_seconds"] > 0


def test_progress_is_queryable_without_performing_acquisition(store):
    asked = store.request_acquisition(now=T0)
    assert store.acquisition_progress(asked["request_id"])["state"] == "pending"
    store.claim_acquisition(worker="w", now=T0)
    assert store.acquisition_progress(asked["request_id"])["state"] == "running"


# ------------------------------------------- the console wiring itself

def test_the_display_timer_projects_and_never_acquires():
    """The defect in one line: the timer must not reach a network."""
    bridge = (ROOT / "seraph/dashboard/console_component/bridge.js").read_text(
        encoding="utf-8")
    timer = bridge.split("setInterval", 1)[1][:400]
    assert "news_project" in timer
    assert "news_refresh" not in timer, "the timer forces acquisition again"


def test_the_console_asks_rather_than_fetching_in_the_web_process():
    app = (ROOT / "seraph/dashboard/prototype_app.py").read_text(encoding="utf-8")
    marker = "op')=='news_acquire'"
    assert marker in app, "there is no way to ask for acquisition"
    handler = app.split(marker, 1)[1][:900]
    assert "request_acquisition" in handler, "the console fetches inline again"


def test_the_project_operation_does_not_touch_the_network():
    app = (ROOT / "seraph/dashboard/prototype_app.py").read_text(encoding="utf-8")
    handler = app.split("'news_project'", 1)[1][:300]
    assert "request_acquisition" not in handler
    assert "acquire(" not in handler


def test_the_worker_serves_queued_requests():
    runner = (ROOT / "scripts/run_news.py").read_text(encoding="utf-8")
    assert "claim_acquisition" in runner
    assert "finish_acquisition" in runner


# ------------------------------------------------------- the deadline

def test_acquisition_reports_five_distinct_outcomes(store):
    """fetched / unchanged / failed / timed_out / skipped call for different
    actions and must not share a word."""
    outcome = acquire(store, fetcher(2), now=T0, clock=Clock())
    described = outcome.describe()
    for key in ("fetched", "unchanged", "failed", "timed_out",
                "skipped_for_budget"):
        assert key in described
    assert outcome.new_stories == 6
    assert outcome.complete


def test_a_source_contacted_with_nothing_new_is_unchanged_not_fetched(store):
    acquire(store, fetcher(1), now=T0, clock=Clock())
    again = acquire(store, fetcher(1), now=T0, clock=Clock())
    assert set(again.unchanged) == {"a", "b", "c"}
    assert again.fetched == ()


def test_a_timeout_is_not_reported_as_a_failure(store):
    def timing_out(src, cursor=None):
        if src.source_id == "b":
            raise TimeoutError("read timed out")
        return fetcher()(src, cursor)

    outcome = acquire(store, timing_out, now=T0, clock=Clock())
    assert outcome.timed_out == ("b",)
    assert "b" not in outcome.failed


def test_an_error_is_not_reported_as_a_timeout(store):
    def angry(src, cursor=None):
        if src.source_id == "b":
            raise RuntimeError("HTTP 500")
        return fetcher()(src, cursor)

    outcome = acquire(store, angry, now=T0, clock=Clock())
    assert "b" in outcome.failed
    assert outcome.timed_out == ()


def test_work_that_cannot_finish_is_not_started(store):
    """A source begun with less than the minimum timeout left overruns the
    budget by its own timeout. Reporting it as not contacted is true; letting
    it start and be cut off is not."""
    outcome = acquire(store, fetcher(), now=T0, budget_seconds=1.0,
                      clock=Clock(step=0.6))
    assert outcome.skipped_for_budget
    assert not outcome.complete


def test_the_per_source_timeout_never_exceeds_what_is_left():
    """Otherwise the last source in a pass overshoots the whole budget."""
    assert _per_source_timeout(4.0, 1) <= 4.0
    assert _per_source_timeout(100.0, 1) <= 15.0, "and never unbounded"
    # With real budget a source gets the preferred floor, so a merely distant
    # source is not failed for being slow.
    assert _per_source_timeout(30.0, 10) >= 3.0
    # But the floor is clamped by what is left: an unclamped floor is longer
    # than the remaining budget whenever the budget is small, and the last
    # source then overshoots the whole pass. A remainder this small is
    # skipped by `_MIN_START` rather than started.
    assert _per_source_timeout(0.5, 1) == 0.5


def test_the_deadline_reaches_the_socket():
    """A budget checked only between sources constrains nothing."""
    for module in ("seraph/news/http_feed.py", "seraph/news/json_feed.py"):
        text = (ROOT / module).read_text(encoding="utf-8")
        assert "deadline_timeout" in text, f"{module} ignores the deadline"


def test_retries_respect_the_deadline():
    """Retrying a timing-out source three times with backoff spent more than
    twice the whole refresh budget on one feed: the socket timeout bit, and
    then the retry loop ignored it."""
    text = (ROOT / "seraph/news/acquisition.py").read_text(encoding="utf-8")
    retry = text.split("while attempts < max(1, budget)", 1)[1][:1400]
    assert "deadline" in retry
    assert "not retrying" in retry


def test_a_slow_source_does_not_hold_the_whole_pass(tmp_path):
    """End to end, with a real sleep and a real budget."""
    db = NewsStore(tmp_path / "slow.sqlite")
    for sid in ("s0", "s1", "s2", "s3"):
        db.register(source(sid))

    class Slow:
        deadline_timeout = None

        def __call__(self, src, cursor=None):
            if src.source_id == "s1":
                time.sleep(min(1.0, self.deadline_timeout or 1.0))
                raise TimeoutError("read timed out")
            return fetcher()(src, cursor)

    started = time.monotonic()
    outcome = acquire(db, Slow(), now=T0, budget_seconds=3.0)
    elapsed = time.monotonic() - started

    assert "s1" in outcome.timed_out
    # One in-flight fetch may overshoot by its own timeout; it must not also
    # overshoot by the whole retry budget, which is what used to happen.
    assert elapsed < 12.0, f"the pass ran away: {elapsed:.1f}s"
