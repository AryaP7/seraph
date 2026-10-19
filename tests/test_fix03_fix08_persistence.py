"""FIX03 / FIX08 — sealed runs, immutable reports, and journal no-op commands.

Audit findings reproduced before this slice and pinned here:

* A03 — `finish()` checked only a row count, so a *completed* run accepted an
  extra point, including a date outside its declared range.
* A04 — a run became `complete` before its comparison report was written, and
  `report()` silently overwrote an existing report.
* A13 — recording an update that leaves an action unchanged raised
  `IntegrityError: UNIQUE constraint failed: action_events.run_id,
  action_events.seq`, because C11 correctly creates no journal event for a
  no-op while the store reinserted the previous event.
"""
from __future__ import annotations

import sqlite3

import pytest

from seraph.orchestration.run_store import RunStore

RANGE = dict(start="2020-01-01", end="2020-01-03")
ARGS = dict(alert_id="alert", action="none", decomposition=(0.1, 0.2, 0.3),
            at="2020-01-01T15:30:00+05:30")


def point(run, day, value=1):
    return {"run_id": run, "date": day, "evaluation_timestamp": day + "T15:30:00+05:30",
            "data_cutoff": day + "T15:30:00+05:30", "original_pillars": {},
            "reconciled": {}, "composite": None,
            "coverage": {"mask": [False, False, False]}, "limitations": [],
            "value": value}


def seeded(tmp_path, *, days=("2020-01-01", "2020-01-02"), requires_report=False):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin(dict(mode="test", **RANGE))
    for day in days:
        store.put(run, point(run, day))
    store.finish(run, list(days), requires_report=requires_report)
    return store, run


# --------------------------------------------------------------- FIX03 seal


def test_a_sealed_run_rejects_a_new_point(tmp_path):
    store, run = seeded(tmp_path)
    with pytest.raises(ValueError, match="is sealed"):
        store.put(run, point(run, "2020-01-03"))
    assert [p["date"] for p in store.points(run)] == ["2020-01-01", "2020-01-02"]


def test_a_point_outside_the_declared_range_is_rejected_even_while_running(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin(dict(mode="test", **RANGE))
    with pytest.raises(ValueError, match="outside this run's declared range"):
        store.put(run, point(run, "2099-12-31"))


def test_finish_verifies_the_exact_date_set_not_just_a_count(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin(dict(mode="test", **RANGE))
    store.put(run, point(run, "2020-01-01"))
    store.put(run, point(run, "2020-01-02"))
    # Right count, wrong dates.
    with pytest.raises(ValueError, match="do not match the expected date set"):
        store.finish(run, ["2020-01-01", "2020-01-03"])
    assert store.runs()[0]["status"] == "running"
    store.finish(run, ["2020-01-01", "2020-01-02"])
    assert store.runs()[0]["status"] == "complete"


def test_point_schema_is_validated(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin(dict(mode="test", **RANGE))
    broken = point(run, "2020-01-01")
    del broken["coverage"]
    with pytest.raises(ValueError, match="missing required fields"):
        store.put(run, broken)


def test_an_identical_retry_of_a_sealed_point_still_succeeds(tmp_path):
    store, run = seeded(tmp_path)
    store.put(run, point(run, "2020-01-01"))              # verified identical
    with pytest.raises(ValueError, match="Retry changed an already persisted point"):
        store.put(run, point(run, "2020-01-01", value=2))
    assert store.finish(run, ["2020-01-01", "2020-01-02"]) == "complete"


def test_sealing_records_the_date_set_and_a_content_digest(tmp_path):
    store, run = seeded(tmp_path)
    row = store.runs()[0]
    assert row["sealed_dates"] == ["2020-01-01", "2020-01-02"]
    assert row["content_hash"] and row["sealed_at"]


# ------------------------------------------------- FIX03 report finalisation


def test_a_run_requiring_a_report_is_not_complete_until_the_report_exists(tmp_path):
    store, run = seeded(tmp_path, requires_report=True)
    assert store.runs()[0]["status"] == "inference_complete"
    store.report(run, {"comparison": []})
    assert store.runs()[0]["status"] == "complete"


def test_an_interruption_before_the_report_cannot_present_as_complete(tmp_path):
    """The crash case: points sealed, process dies, store reopened."""
    store, run = seeded(tmp_path, requires_report=True)
    reopened = RunStore(store.path)
    assert [r for r in reopened.runs() if r["status"] == "complete"] == []
    assert reopened.report(run) is None
    # Recovery: writing the report completes the run without touching points.
    reopened.report(run, {"comparison": []})
    assert reopened.runs()[0]["status"] == "complete"
    assert len(reopened.points(run)) == 2


def test_reports_are_immutable_revisions_not_overwrites(tmp_path):
    store, run = seeded(tmp_path, requires_report=True)
    store.report(run, {"version": 1})
    store.report(run, {"version": 1})                      # identical: no-op
    assert len(store.report_revisions(run)) == 1
    store.report(run, {"version": 2})                      # different: new revision
    revisions = store.report_revisions(run)
    assert [r["revision"] for r in revisions] == [1, 2]
    assert revisions[0]["payload"] == {"version": 1}       # the first is preserved
    assert store.report(run) == {"version": 2}             # read returns the latest


def test_report_revisions_cannot_be_updated_or_deleted_through_sql(tmp_path):
    store, run = seeded(tmp_path, requires_report=True)
    store.report(run, {"version": 1})
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as db:
            db.execute("DELETE FROM report_revisions")
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as db:
            db.execute("UPDATE report_revisions SET payload='{}'")
    assert store.report(run) == {"version": 1}


# ---------------------------------------------------------- FIX08 no-op path


def test_a_noop_update_succeeds_without_consuming_a_journal_sequence(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin({"mode": "journal"})
    created = store.action(run, "r1", "regulator", "create", **ARGS)
    # Same action value again under a NEW request id: C11 creates no event.
    noop = store.action(run, "r2", "regulator", "update", alert_id="alert", action="none")
    assert noop["noop"] is True and noop["last_seq"] == created["seq"]
    journal = store.action_log(run).journal()
    assert len(journal) == 1, "a no-op must not append a journal event"


def test_a_noop_retry_returns_the_same_result(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin({"mode": "journal"})
    store.action(run, "r1", "regulator", "create", **ARGS)
    first = store.action(run, "r2", "regulator", "update", alert_id="alert", action="none")
    assert store.action(run, "r2", "regulator", "update",
                        alert_id="alert", action="none") == first


def test_a_conflicting_retry_of_a_noop_request_id_is_rejected(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin({"mode": "journal"})
    store.action(run, "r1", "regulator", "create", **ARGS)
    store.action(run, "r2", "regulator", "update", alert_id="alert", action="none")
    with pytest.raises(ValueError, match="Idempotency key reused"):
        store.action(run, "r2", "regulator", "update",
                     alert_id="alert", action="soft_warning")


def test_a_real_change_after_a_noop_still_appends_one_event(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin({"mode": "journal"})
    store.action(run, "r1", "regulator", "create", **ARGS)
    store.action(run, "r2", "regulator", "update", alert_id="alert", action="none")
    changed = store.action(run, "r3", "regulator", "update",
                           alert_id="alert", action="soft_warning")
    assert changed.get("noop") is None and changed["seq"] == 2
    assert len(store.action_log(run).journal()) == 2


def test_repeated_retraction_is_a_noop_and_survives_a_restart(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin({"mode": "journal"})
    store.action(run, "r1", "regulator", "create", **ARGS)
    store.action(run, "r2", "regulator", "delete", alert_id="alert")
    again = store.action(run, "r3", "regulator", "delete", alert_id="alert")
    reopened = RunStore(store.path)
    log = reopened.action_log(run)
    assert len(log.journal()) == 2
    assert log.entries(include_retracted=True)[0].retracted
    assert again.get("noop") is True or again.get("seq") == 3
    # Whatever C11 decided, the store never reinserted an existing sequence.
    seqs = [e.seq for e in log.journal()]
    assert len(seqs) == len(set(seqs))


def test_every_command_is_recorded_even_when_it_created_no_event(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin({"mode": "journal"})
    store.action(run, "r1", "regulator", "create", **ARGS)
    store.action(run, "r2", "regulator", "update", alert_id="alert", action="none")
    commands = store.action_commands(run)
    assert [c["request_id"] for c in commands] == ["r1", "r2"]
    assert commands[0]["event_seq"] == 1 and commands[1]["event_seq"] is None


def test_a_failed_command_rolls_back_both_the_event_and_its_command_record(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.begin({"mode": "journal"})
    with store.connect() as db:
        db.execute("CREATE TRIGGER reject BEFORE INSERT ON action_events "
                   "BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.action(run, "r1", "regulator", "create", **ARGS)
    assert store.action_log(run).journal() == ()
    assert store.action_commands(run) == []


# ------------------------------------------------------------- migration


def test_a_legacy_store_migrates_without_losing_reports_or_events(tmp_path):
    path = tmp_path / "legacy.sqlite"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE runs (id TEXT PRIMARY KEY, manifest TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE points (run_id TEXT NOT NULL, day TEXT NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY(run_id,day));
        CREATE TABLE action_events (run_id TEXT NOT NULL, seq INTEGER NOT NULL,
            request_id TEXT NOT NULL, request TEXT NOT NULL, event TEXT NOT NULL,
            PRIMARY KEY(run_id,seq), UNIQUE(run_id,request_id));
        CREATE TABLE reports (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        INSERT INTO runs VALUES ('legacy','{"mode":"old"}','complete');
        INSERT INTO reports VALUES ('legacy','{"kept":true}');
        INSERT INTO action_events VALUES ('legacy',1,'req','{}','{"seq":1}');
    """)
    db.commit()
    db.close()

    store = RunStore(path)
    assert store.report("legacy") == {"kept": True}
    assert [r["revision"] for r in store.report_revisions("legacy")] == [1]
    assert [c["request_id"] for c in store.action_commands("legacy")] == ["req"]
    assert store.runs()[0]["status"] == "complete"
    # Re-opening the same store must be idempotent.
    again = RunStore(path)
    assert again.report("legacy") == {"kept": True}
    assert len(again.report_revisions("legacy")) == 1
