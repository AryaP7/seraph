"""PIPE03 / OPS01 — idempotent jobs, recovery, health and alert delivery.

The properties here are the ones that make "cron plus idempotent scripts" an
honest architecture rather than a hope:

* two overlapping ticks do not both run;
* a crashed run does not wedge the job forever, and the takeover is recorded;
* an interrupted job resumes from its checkpoint instead of restarting;
* retries are bounded and exhaustion is visible;
* a source nobody fetched reads as `never_succeeded`, not `ok`;
* an alert that was issued and never delivered is retryable, not lost.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from seraph.news import FetchResult, NewsStore, Source
from seraph.operations import (
    ALERT_TRANSITIONS,
    AlertLedger,
    JobStore,
    LockUnavailable,
    job_checks,
    overall,
    source_checks,
)
from seraph.operations.jobs import _now
from seraph.shared_types import ist_timestamp

AT = "2026-01-02T12:00:00+05:30"


@pytest.fixture
def jobs(tmp_path):
    return JobStore(tmp_path / "jobs.sqlite")


# ----------------------------------------------------------- locking


def test_a_second_tick_does_not_run_while_the_first_holds_the_lock(jobs):
    jobs.acquire("ingest", "run_1")
    outcome = jobs.run("ingest", lambda ctx: {"did": "work"})
    assert outcome.status == "lock_unavailable"
    assert "locked by" in outcome.error


def test_an_expired_lease_is_taken_over_and_the_takeover_is_recorded(jobs):
    stale = _now() - timedelta(hours=2)
    jobs.acquire("ingest", "dead_run", lease_minutes=1, now=stale)
    outcome = jobs.run("ingest", lambda ctx: {"ok": True})
    assert outcome.status == "succeeded"
    assert outcome.detail["lease"]["took_over_expired_lease"] is True
    assert outcome.detail["lease"]["previous_owner"]


def test_a_successful_run_releases_its_lock(jobs):
    jobs.run("ingest", lambda ctx: {})
    assert jobs.lock_state("ingest") is None


def test_a_failed_run_also_releases_its_lock(jobs):
    def boom(ctx):
        raise RuntimeError("nope")
    assert jobs.run("ingest", boom, max_attempts=1).status == "failed"
    assert jobs.lock_state("ingest") is None, \
        "a crash must not wedge the job until someone notices"


# ------------------------------------------------- retries and recovery


def test_retries_are_bounded_and_exhaustion_is_visible(jobs):
    attempts = {"n": 0}

    def flaky(ctx):
        attempts["n"] += 1
        raise ConnectionError("source refused")
    outcome = jobs.run("ingest", flaky, max_attempts=3)
    assert attempts["n"] == 3
    assert outcome.status == "failed" and outcome.attempt == 3
    assert "ConnectionError" in outcome.error


def test_a_transient_failure_succeeds_on_a_later_attempt(jobs):
    attempts = {"n": 0}

    def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("not yet")
        return {"attempts": attempts["n"]}
    outcome = jobs.run("ingest", flaky, max_attempts=3)
    assert outcome.status == "succeeded" and outcome.attempt == 3


def test_an_interrupted_job_resumes_from_its_checkpoint(jobs):
    def half(ctx):
        ctx.checkpoint({"done_through": "2024-03-31"})
        raise RuntimeError("died halfway")
    first = jobs.run("backfill", half, max_attempts=1)
    assert first.status == "failed"
    assert jobs.last_checkpoint("backfill")["payload"] == {"done_through": "2024-03-31"}

    seen = {}

    def rest(ctx):
        seen["resume_from"] = ctx.resume_from
        return {"finished": True}
    second = jobs.run("backfill", rest)
    assert second.status == "succeeded"
    assert seen["resume_from"] == {"done_through": "2024-03-31"}


def test_a_successful_run_clears_its_checkpoint(jobs):
    jobs.run("backfill", lambda ctx: ctx.checkpoint({"x": 1}) or {"ok": True})
    assert jobs.last_checkpoint("backfill") is None


def test_a_failed_run_keeps_its_checkpoint_and_says_so(jobs):
    def half(ctx):
        ctx.checkpoint({"done_through": "2024-03-31"})
        raise RuntimeError("died")
    outcome = jobs.run("backfill", half, max_attempts=1)
    assert outcome.checkpoint == {"done_through": "2024-03-31"}
    assert "resumes rather than restarts" in outcome.detail["note"]


def test_watermarks_persist_between_runs(jobs):
    jobs.run("ingest", lambda ctx: ctx.set_watermark("rbi", "2026-01-02") or {})
    seen = {}
    jobs.run("ingest", lambda ctx: seen.update(mark=ctx.watermark("rbi")) or {})
    assert seen["mark"] == "2026-01-02"


def test_every_attempt_is_a_recorded_row_not_a_log_line(jobs):
    jobs.run("ingest", lambda ctx: {})
    jobs.run("ingest", lambda ctx: (_ for _ in ()).throw(RuntimeError("x")),
             max_attempts=1)
    recorded = jobs.runs("ingest")
    assert [r.status for r in recorded] == ["failed", "succeeded"] or \
        sorted(r.status for r in recorded) == ["failed", "succeeded"]


# ----------------------------------------------------------- health


@pytest.fixture
def news(tmp_path):
    store = NewsStore(tmp_path / "news.sqlite")
    store.register(Source(source_id="rbi", provider="RBI", kind="official_policy",
                          url="https://example.test", topic_coverage=("policy",),
                          poll_interval_minutes=60))
    return store


def test_a_source_nobody_fetched_is_never_succeeded_not_ok(news):
    checks = source_checks(news, at=AT)
    assert [c.health for c in checks] == ["never_succeeded"]
    assert overall(checks)["status"] == "never_succeeded"
    assert "silence is not health" in overall(checks)["note"]


def test_a_recently_fetched_source_is_ok(news):
    news.ingest("rbi", lambda s, c: FetchResult(), now="2026-01-02T11:40:00+05:30")
    assert source_checks(news, at=AT)[0].health == "ok"


def test_a_source_past_its_freshness_policy_is_stale(news):
    news.ingest("rbi", lambda s, c: FetchResult(), now="2026-01-01T11:40:00+05:30")
    check = source_checks(news, at=AT)[0]
    assert check.health == "stale" and "policy" in check.detail


def test_a_repeatedly_failing_source_is_failing(news):
    def boom(source, cursor):
        raise ConnectionError("refused")
    news.ingest("rbi", lambda s, c: FetchResult(), now="2026-01-02T11:00:00+05:30")
    for _ in range(3):
        news.ingest("rbi", boom, now="2026-01-02T11:30:00+05:30",
                    sleep=lambda *_: None)
    assert source_checks(news, at=AT)[0].health == "failing"


def test_a_job_that_never_ran_is_never_run(jobs):
    checks = job_checks(jobs, {"ingest": 60}, at=AT)
    assert checks[0].health == "never_run"


def test_a_job_whose_runs_all_failed_is_never_succeeded(jobs):
    jobs.run("ingest", lambda ctx: (_ for _ in ()).throw(RuntimeError("x")),
             max_attempts=1)
    assert job_checks(jobs, {"ingest": 60}, at=AT)[0].health == "never_succeeded"


def test_overall_reports_the_worst_check(jobs, news):
    jobs.run("ingest", lambda ctx: {})
    status = overall(source_checks(news, at=AT) + job_checks(jobs, {"ingest": 60},
                                                             at=AT))
    assert status["status"] == "never_succeeded"
    assert "rbi" in status["by_health"]["never_succeeded"]


# ------------------------------------------------------ alert delivery


@pytest.fixture
def ledger(tmp_path):
    return AlertLedger(tmp_path / "alerts.sqlite")


def test_an_alert_moves_through_its_lifecycle(ledger):
    issued = ledger.issue(kind="source_stale", subject="rbi", severity="medium",
                          payload={"age": 200})
    assert issued["issued"] is True and issued["state"] == "issued"
    ledger.transition(issued["alert_id"], "delivered")
    ledger.transition(issued["alert_id"], "acknowledged", actor="usr_1")
    ledger.transition(issued["alert_id"], "resolved", actor="usr_1")
    alert = ledger.alert(issued["alert_id"])
    assert alert["state"] == "resolved"
    assert [e["state"] for e in alert["trail"]] == [
        "issued", "delivered", "acknowledged", "resolved"]
    assert alert["trail"][2]["actor"] == "usr_1"


def test_sent_is_not_delivered(ledger):
    issued = ledger.issue(kind="x", subject="s", severity="low", payload={})
    assert ledger.alert(issued["alert_id"])["state"] == "issued"
    ledger.transition(issued["alert_id"], "delivery_failed",
                      detail="smtp timeout")
    assert ledger.alert(issued["alert_id"])["state"] == "delivery_failed"


def test_an_undelivered_alert_is_retryable_not_lost(ledger):
    ledger.issue(kind="x", subject="s", severity="low", payload={},
                 dedupe_key="a1")
    pending = ledger.undelivered(older_than_minutes=0)
    assert [p["alert_id"] for p in pending] == ["a1"]
    assert "retry or escalate" in pending[0]["note"]
    ledger.transition("a1", "delivered")
    assert ledger.undelivered(older_than_minutes=0) == []


def test_issuing_the_same_dedupe_key_twice_issues_once(ledger):
    first = ledger.issue(kind="x", subject="s", severity="low", payload={},
                         dedupe_key="same")
    second = ledger.issue(kind="x", subject="s", severity="low", payload={},
                          dedupe_key="same")
    assert first["issued"] is True and second["issued"] is False
    assert len(ledger.alert("same")["trail"]) == 1


def test_an_invalid_alert_move_is_refused(ledger):
    issued = ledger.issue(kind="x", subject="s", severity="low", payload={})
    with pytest.raises(ValueError, match="not a valid alert move"):
        ledger.transition(issued["alert_id"], "acknowledged")


def test_resolved_is_terminal():
    assert ALERT_TRANSITIONS["resolved"] == ()


def test_the_alert_trail_is_append_only(ledger):
    issued = ledger.issue(kind="x", subject="s", severity="low", payload={})
    with pytest.raises(sqlite3.IntegrityError):
        with ledger.connect() as db:
            db.execute("UPDATE alert_events SET state='resolved'")
    assert ledger.alert(issued["alert_id"])["state"] == "issued"
