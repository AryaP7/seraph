"""T07 — a crash must lose nothing that was promised (audit finding R04).

The live path held everything in memory: a restart lost the bar accumulators,
the volume baselines, the filter state and every decision made since start-up,
and there was no cursor, so a restart could not know which inputs it had
already consumed.

The claim this file tests is narrow and checkable: **a decision, its
checkpoint, the advanced head and its outbox events are one transaction.** A
crash before the commit leaves none of them; a crash after it leaves all of
them, and a replay returns the same logical decision rather than computing a
second one.

Crashes are injected by making the real SQLite connection raise at each commit
boundary, not by mocking the store — a test that stubs the thing it is
checking proves only that the stub works.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from seraph.live.lifecycle import (
    HISTORY_LIMIT,
    LifecycleError,
    SessionLifecycle,
    next_session_window,
)
from seraph.live.store import (
    MAX_ATTEMPTS,
    CheckpointUnusable,
    HeadConflict,
    LiveStore,
    MigrationDrift,
    StoreError,
)

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def store(tmp_path):
    return LiveStore(tmp_path / "live.sqlite")


def commit(store, n=1, *, expected=None, events=(), state=None):
    return store.commit_decision(
        decision_id=f"d{n}", as_of=f"2026-10-17T10:{n:02d}:00+05:30",
        computed_at=f"2026-10-17T10:{n:02d}:01+05:30",
        payload=dict(csrs=0.4 + n / 100), publication_state="withheld",
        state=state or dict(x=[1.0, 2.0, 3.0], n=n),
        expected_version=expected, events=list(events))


class _Bar:
    def __init__(self, symbol="AAA", end="2026-10-17T09:20:00+05:30",
                 close=101.0, session="2026-10-17"):
        self._payload = dict(symbol=symbol, start="2026-10-17T09:15:00+05:30",
                             end=end, open=100.0, high=102.0, low=99.0,
                             close=close, ticks=5, volume=1000,
                             complete=True, volume_quality="exact",
                             session_id=session)

    def describe(self):
        return dict(self._payload)


# ----------------------------------------------------------- the migration


def test_the_schema_comes_from_migrations_not_startup_ddl(store):
    with store.connect() as db:
        names = {r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ("input_batches", "closed_bars", "deployments",
                  "inference_checkpoints", "live_decisions", "runtime_head",
                  "outbox", "schema_migrations"):
        assert table in names, table


def test_migrations_are_applied_once(store, tmp_path):
    assert store.migrate() == []
    again = LiveStore(tmp_path / "live.sqlite")
    assert again.migrate() == []


def test_a_changed_migration_is_an_error_not_a_silent_rerun(tmp_path):
    migrations = tmp_path / "m"
    migrations.mkdir()
    (migrations / "001.sql").write_text("CREATE TABLE t(a TEXT);",
                                        encoding="utf-8")
    LiveStore(tmp_path / "live.sqlite", migrations_dir=migrations)
    (migrations / "001.sql").write_text("CREATE TABLE t(a TEXT, b TEXT);",
                                        encoding="utf-8")
    with pytest.raises(MigrationDrift, match="nobody knows what this database"):
        LiveStore(tmp_path / "live.sqlite", migrations_dir=migrations)


# ------------------------------------------------- crash at every boundary


class _ExplodingConnection(sqlite3.Connection):
    """A real connection that fails on one statement.

    A connection FACTORY, not a mock: the transaction, its rollback and the
    durability settings are SQLite's own. Stubbing the store would prove only
    that the stub works.
    """

    target: str | None = None

    def execute(self, sql, *args, **kwargs):
        if self.target and sql.strip().startswith(self.target):
            raise sqlite3.OperationalError("disk I/O error (injected)")
        return super().execute(sql, *args, **kwargs)


@pytest.mark.parametrize("failing_statement", [
    "INSERT OR IGNORE INTO inference_checkpoints",
    "INSERT INTO live_decisions",
    "INSERT INTO runtime_head",
    "INSERT OR IGNORE INTO outbox",
])
def test_a_crash_before_commit_leaves_nothing(store, monkeypatch,
                                              failing_statement):
    """Injected at each of the four writes inside the one transaction."""
    real_connect = sqlite3.connect

    def connect(*args, **kwargs):
        kwargs["factory"] = _ExplodingConnection
        return real_connect(*args, **kwargs)

    _ExplodingConnection.target = failing_statement
    monkeypatch.setattr(sqlite3, "connect", connect)
    try:
        with pytest.raises(sqlite3.OperationalError):
            commit(store, 1, expected=0,
                   events=[dict(event_kind="decision", payload={})])
    finally:
        _ExplodingConnection.target = None
        monkeypatch.undo()

    assert store.decision("d1") is None, "no decision survived the crash"
    assert store.head().version == 0, "the head did not advance"
    assert store.pending_events() == [], "no outbox event was published"


def test_after_commit_everything_is_there(store):
    result = commit(store, 1, expected=0,
                    events=[dict(event_kind="decision", payload=dict(a=1))])
    assert result["replayed"] is False
    assert store.decision("d1")["payload"]["csrs"] == pytest.approx(0.41)
    assert store.head().version == 1
    assert store.head().decision_id == "d1"
    assert [e.event_kind for e in store.pending_events()] == ["decision"]
    assert store.load_checkpoint(result["checkpoint_id"])["state"]["n"] == 1


def test_a_replay_returns_the_same_logical_decision(store):
    """A crash BETWEEN commit and acknowledgement must not double-decide."""
    first = commit(store, 1, expected=0)
    again = commit(store, 1, expected=0)
    assert again["replayed"] is True
    assert again["checkpoint_id"] == first["checkpoint_id"]
    assert store.head().version == 1, "a replay must not advance the head"
    with store.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM live_decisions"
                          ).fetchone()["n"] == 1


def test_two_writers_cannot_interleave(store):
    commit(store, 1, expected=0)
    with pytest.raises(HeadConflict, match="was NOT applied"):
        commit(store, 2, expected=0)          # stale expectation
    assert store.decision("d2") is None
    assert store.head().version == 1


def test_an_unconditional_writer_still_works(store):
    """`expected_version=None` is the single-writer case, not a loophole."""
    commit(store, 1)
    commit(store, 2)
    assert store.head().version == 2


# ---------------------------------------------------------- the checkpoint


def test_the_blob_lands_before_the_row_that_names_it(store):
    result = commit(store, 1, expected=0, state=dict(big="x" * 1000))
    with store.connect() as db:
        ref = db.execute("SELECT state_ref FROM inference_checkpoints "
                         "WHERE checkpoint_id=?",
                         (result["checkpoint_id"],)).fetchone()["state_ref"]
    assert (store.blobs / ref).exists()
    assert json.loads((store.blobs / ref).read_text())["big"].startswith("x")


def test_no_partial_blob_is_left_behind(store):
    commit(store, 1, expected=0)
    assert list(store.blobs.glob("*.part")) == []


def test_a_corrupt_checkpoint_is_refused_not_deserialized(store):
    result = commit(store, 1, expected=0)
    with store.connect() as db:
        ref = db.execute("SELECT state_ref FROM inference_checkpoints "
                         "WHERE checkpoint_id=?",
                         (result["checkpoint_id"],)).fetchone()["state_ref"]
    (store.blobs / ref).write_text('{"x": "tampered"}', encoding="utf-8")
    with pytest.raises(CheckpointUnusable, match="corrupt"):
        store.load_checkpoint(result["checkpoint_id"])


def test_a_missing_checkpoint_blob_says_rebuild(store):
    result = commit(store, 1, expected=0)
    for path in store.blobs.glob("*.json"):
        path.unlink()
    with pytest.raises(CheckpointUnusable, match="rebuild by warm start"):
        store.load_checkpoint(result["checkpoint_id"])


def test_a_checkpoint_from_another_pipeline_version_is_refused(store):
    result = commit(store, 1, expected=0)
    with pytest.raises(CheckpointUnusable, match="rebuild by warm start"):
        store.load_checkpoint(result["checkpoint_id"],
                              pipeline_version="something.else/9")


def test_an_identical_state_is_stored_once(store):
    a = commit(store, 1, expected=0, state=dict(same=True))
    b = commit(store, 2, expected=1, state=dict(same=True))
    assert a["checkpoint_id"] == b["checkpoint_id"]
    assert len(list(store.blobs.glob("*.json"))) == 1


# ---------------------------------------------------------------- the feed


def test_re_recording_a_batch_is_a_no_op(store):
    """A reconnecting feed replays its buffer; that must not double-count."""
    first = store.record_input_batch(batch_id="b1", source_id="kite",
                                     payload=dict(ticks=3))
    again = store.record_input_batch(batch_id="b1", source_id="kite",
                                     payload=dict(ticks=3))
    assert first == again
    with store.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM input_batches"
                          ).fetchone()["n"] == 1


def test_the_same_batch_id_with_different_content_is_refused(store):
    store.record_input_batch(batch_id="b1", source_id="kite",
                             payload=dict(ticks=3))
    with pytest.raises(StoreError, match="identifies its payload"):
        store.record_input_batch(batch_id="b1", source_id="kite",
                                 payload=dict(ticks=4))


def test_a_finalized_bar_is_written_once(store):
    assert store.record_closed_bar(_Bar()) is True
    assert store.record_closed_bar(_Bar()) is False
    assert len(store.bars_for("2026-10-17")) == 1


def test_a_finalized_bar_cannot_be_rewritten_with_different_content(store):
    store.record_closed_bar(_Bar())
    with pytest.raises(StoreError, match="a finalized bar does not change"):
        store.record_closed_bar(_Bar(close=999.0))


def test_a_correction_is_a_new_revision(store):
    store.record_closed_bar(_Bar())
    assert store.record_closed_bar(_Bar(close=103.0), revision=1) is True
    assert len(store.bars_for("2026-10-17")) == 2


def test_a_bundle_id_is_immutable_in_the_store(store):
    from seraph.live.inference import ModelBundle
    bundle = ModelBundle("b1", "rmt", "2026-10-01", "2026-10-02")
    store.register_deployment(bundle)
    store.register_deployment(bundle)
    with pytest.raises(StoreError, match="immutable"):
        store.register_deployment(ModelBundle("b1", "rmt", "2026-10-01",
                                              "2026-10-09"))


# --------------------------------------------------------------- the outbox


def test_delivery_is_at_least_once_with_a_receiver_key(store):
    commit(store, 1, expected=0, events=[dict(
        event_kind="alert", aggregate_id="d1",
        idempotency_key="alert:d1", payload=dict(level="amber"))])
    event = store.pending_events()[0]
    assert event.idempotency_key == "alert:d1"
    store.mark_delivered(event.outbox_id)
    assert store.pending_events() == []


def test_a_failed_delivery_is_retried_with_backoff(store):
    commit(store, 1, expected=0, events=[dict(event_kind="alert", payload={})])
    event = store.pending_events()[0]
    now = datetime(2026, 10, 17, 10, 0, tzinfo=IST)
    outcome = store.mark_failed(event.outbox_id, "receiver refused", at=now)
    assert outcome["attempts"] == 1
    assert outcome["exhausted"] is False
    assert store.pending_events(at=now) == [], "not retried immediately"
    assert store.pending_events(at=now + timedelta(seconds=10)), "retried later"


def test_retries_are_bounded_and_the_event_is_not_dropped(store):
    commit(store, 1, expected=0, events=[dict(event_kind="alert", payload={})])
    outbox_id = store.pending_events()[0].outbox_id
    for _ in range(MAX_ATTEMPTS):
        store.mark_failed(outbox_id, "still refused")
    assert store.pending_events(at=datetime(2030, 1, 1, tzinfo=IST)) == []
    dead = store.dead_letters()
    assert [e.outbox_id for e in dead] == [outbox_id]
    assert dead[0].last_error == "still refused"


def test_marking_delivered_twice_does_not_resurrect_the_event(store):
    commit(store, 1, expected=0, events=[dict(event_kind="alert", payload={})])
    outbox_id = store.pending_events()[0].outbox_id
    store.mark_delivered(outbox_id)
    store.mark_delivered(outbox_id)
    assert store.pending_events() == []
    assert store.dead_letters() == []


# ---------------------------------------------------------------- --status


def test_status_reads_without_connecting_to_anything(store):
    commit(store, 1, expected=0, events=[dict(event_kind="alert", payload={})])
    status = store.describe()
    assert status["stream"]["version"] == 1
    assert status["counts"]["live_decisions"] == 1
    assert status["undelivered_events"] == 1
    assert status["latest_decision"]["decision_id"] == "d1"


def test_the_latest_decision_is_by_as_of_not_by_insertion_order(store):
    commit(store, 2, expected=0)
    commit(store, 1, expected=1)
    assert store.latest_decision()["decision_id"] == "d2"


# ------------------------------------------------------------- lifecycle


def test_the_happy_path_runs_through_every_state():
    lc = SessionLifecycle()
    lc.to("restoring"); lc.to("warming_up"); lc.to("connecting")
    lc.to("waiting_session"); lc.open_session("2026-10-17")
    assert lc.may_publish is True
    lc.begin_drain()
    assert lc.may_publish is True, "the final bar is still being collected"
    lc.close_session()
    assert lc.may_publish is False


def test_an_illegal_transition_raises_rather_than_landing_somewhere_odd():
    lc = SessionLifecycle()
    with pytest.raises(LifecycleError, match="not a legal transition"):
        lc.to("collecting")


def test_a_session_is_not_closed_without_draining():
    lc = SessionLifecycle()
    lc.to("warming_up"); lc.to("connecting"); lc.open_session("2026-10-17")
    with pytest.raises(LifecycleError, match="polled out first"):
        lc.close_session()


def test_the_drain_waits_for_the_feed_to_go_quiet():
    lc = SessionLifecycle(drain_seconds=60)
    lc.to("warming_up"); lc.to("connecting"); lc.open_session("2026-10-17")
    close = datetime(2026, 10, 17, 15, 30, tzinfo=IST)
    lc.begin_drain(at=close)
    assert lc.drain_complete(at=close + timedelta(seconds=30)) is False
    # A late tick for the final bar restarts the quiet window.
    late = (close + timedelta(seconds=40)).isoformat()
    assert lc.drain_complete(at=close + timedelta(seconds=70),
                             last_tick_at=late) is False
    assert lc.drain_complete(at=close + timedelta(seconds=120),
                             last_tick_at=late) is True


def test_degraded_keeps_running_and_refuses_to_publish():
    lc = SessionLifecycle()
    lc.to("warming_up"); lc.to("connecting"); lc.open_session("2026-10-17")
    lc.degrade(["the macro feed is unreachable"])
    assert lc.is_running is True
    assert lc.may_publish is False
    assert "macro feed" in lc.why_not_publishing()


def test_degrading_without_a_reason_is_refused():
    lc = SessionLifecycle()
    with pytest.raises(LifecycleError, match="worse word for running"):
        lc.degrade([])


def test_recovering_from_degraded_clears_the_reasons():
    lc = SessionLifecycle()
    lc.to("warming_up"); lc.to("connecting")
    lc.degrade(["feed down"])
    lc.to("connecting", reason="feed back")
    assert lc.degraded_reasons == ()


def test_a_reconnect_does_not_pass_through_warmup():
    """Reconnecting mid-session must not look like a cold start."""
    lc = SessionLifecycle()
    lc.to("warming_up"); lc.to("connecting"); lc.open_session("2026-10-17")
    lc.to("reconnecting", reason="socket closed")
    lc.to("collecting", reason="socket back")
    assert lc.state == "collecting"
    assert [t.to for t in lc.history][-2:] == ["reconnecting", "collecting"]


def test_nothing_runs_after_stopped():
    lc = SessionLifecycle()
    lc.to("stopped", reason="operator")
    assert lc.is_running is False
    with pytest.raises(LifecycleError):
        lc.to("collecting")


def test_in_memory_history_is_bounded():
    lc = SessionLifecycle()
    lc.to("warming_up")
    for _ in range(HISTORY_LIMIT * 2):
        lc.to("connecting")
        lc.to("waiting_session")
    assert len(lc.history) == HISTORY_LIMIT
    assert lc.describe()["history_bound"] == HISTORY_LIMIT


def test_the_status_says_why_it_is_not_publishing():
    lc = SessionLifecycle()
    assert "nothing has been read" in lc.why_not_publishing()
    lc.to("warming_up")
    assert "history is still being rebuilt" in lc.why_not_publishing()


# ----------------------------------------------------- calendar and windows


def test_next_open_finds_a_later_window_on_the_same_day():
    """The plan's named case: the lunch gap of a two-window session."""
    from seraph.live.clock import MarketClock
    from seraph.market_calendar import SessionCalendar

    clock = MarketClock(SessionCalendar(session_dates=frozenset(["2024-03-02"])))
    windows = clock._windows("2024-03-02")
    if len(windows) < 2:
        pytest.skip("this build's calendar has one window on 2024-03-02")
    between = windows[0][1] + timedelta(minutes=5)
    assert clock.next_open(between) == windows[1][0].isoformat(), (
        "between windows the next open is this afternoon, not tomorrow")


def test_unknown_calendar_coverage_blocks_a_confident_label():
    from seraph.live.clock import MarketClock

    window = next_session_window(MarketClock())
    assert "calendar_verified" in window
    if not window["calendar_verified"]:
        assert "no confident current label" in window["calendar_note"]
