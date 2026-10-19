"""P0 — a stopped worker and a quiet market used to look identical.

An independent audit put this first, and it was right. If the acquisition
worker dies, Streamlit keeps serving, every surface keeps rendering, and
`source_coverage` only notices once each source drifts past **three times**
its own polling interval — up to twelve hours for the slowest. For that whole
window a dead worker is indistinguishable from a calm news day.

Four different times were being collapsed into one impression of "current":

* when the **screen** last re-rendered — every 30s, and proves nothing
* when a **source** was last checked
* when an **article** was published
* when the **worker** last ran — *nothing recorded this at all*

These tests pin the fourth into existence and keep the four apart.

They also pin two launch-path defects the same audit found: registration ran
only when the store file was missing, so an existing database never received
a newly added source; and starting the worker fetched nothing, because it
asked which sources were *due* — a source polled ten minutes before a restart
is not due for another twenty.
"""
from __future__ import annotations

import pathlib

import pytest

from seraph.news.acquisition import NewsStore
from seraph.news.model import Source

ROOT = pathlib.Path(__file__).resolve().parents[1]
T0 = "2026-10-18T08:00:00+05:30"


def at(minutes: int) -> str:
    """A timestamp `minutes` after T0, as an explicit IST string."""
    from datetime import datetime, timedelta
    moment = datetime.strptime(T0, "%Y-%m-%dT%H:%M:%S%z") + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + \
        moment.strftime("%z")[-2:]


@pytest.fixture
def store(tmp_path) -> NewsStore:
    return NewsStore(tmp_path / "liveness.sqlite")


# ------------------------------------------- the fact that did not exist

def test_a_store_with_no_worker_says_so(store):
    """The honest state of a store filled by a one-off run. Previously this
    was indistinguishable from a healthy system."""
    state = store.worker_state(T0)
    assert state["state"] == "never_started"
    assert state["last_beat_at"] is None
    assert "nothing is fetching" in state["note"]


def test_a_beating_worker_is_running(store):
    store.beat(status="running", pid=1234, now=T0)
    state = store.worker_state(at(1))
    assert state["state"] == "running"
    assert state["pid"] == 1234
    assert state["age_minutes"] == pytest.approx(1.0, abs=0.1)


def test_a_silent_worker_is_stopped(store):
    """The whole point: silence means the WORKER stopped, which is a different
    fact from a source being slow."""
    store.beat(status="running", pid=1234, now=T0)
    assert store.worker_state(at(30))["state"] == "stopped"


def test_the_death_threshold_is_independent_of_any_polling_interval(store):
    """The worker beats every pass whether or not a source was due, so its
    liveness must not inherit a source's schedule — a 240-minute feed must not
    buy a dead worker four hours of looking alive."""
    store.beat(status="running", pid=1234, now=T0)
    assert store.worker_state(at(4))["state"] == "running"
    assert store.worker_state(at(6))["state"] == "stopped"
    assert store.worker_state(T0)["dead_after_minutes"] == 5


def test_a_crashed_worker_records_why(store):
    store.beat(status="failed", pid=1234, detail="ConnectionError: unreachable",
               now=T0)
    state = store.worker_state(at(1))
    assert state["state"] == "failed"
    assert "ConnectionError" in state["detail"]


@pytest.mark.parametrize("terminal", ["stopped", "failed"])
def test_a_terminal_state_is_not_rewritten_by_elapsed_time(store, terminal):
    """The worker said so itself; a day of silence does not make it truer or
    less true, and relabelling it would lose the reason."""
    store.beat(status=terminal, pid=1, detail="because", now=T0)
    assert store.worker_state(at(60 * 24))["state"] == terminal


def test_a_worker_hung_inside_catch_up_is_reported_dead(store):
    """Found by running it: `catching_up` is a claim to be ALIVE, so it must
    be age-checked like `running`. Exempting it let a hung worker advertise
    `catching_up` forever — the exact hole the heartbeat exists to close."""
    store.beat(status="catching_up", pid=1234, now=T0)
    assert store.worker_state(at(1))["state"] == "catching_up"
    assert store.worker_state(at(30))["state"] == "stopped"


def test_the_heartbeat_is_liveness_not_history(store):
    """One row per worker, overwritten. The append-only account of what it did
    is `ingest_log`; conflating the two would make neither readable."""
    store.beat(status="running", pid=1, now=T0)
    store.beat(status="running", pid=1, now=at(1))
    with store.connect() as db:
        rows = db.execute("SELECT COUNT(*) FROM worker_heartbeat").fetchone()[0]
    assert rows == 1


# ------------------------------- source coverage is not worker liveness

def feed_source(source_id: str, minutes: int) -> Source:
    return Source(source_id=source_id, provider="p", kind="regulator",
                  url=f"https://example.invalid/{source_id}",
                  topic_coverage=("x",), language="en", rights="test",
                  may_store_full_text=False, accessibility_verified=True,
                  poll_interval_minutes=minutes)


def test_coverage_states_what_it_actually_measures(store):
    """"11/11 covered" was being read as "the news is current". It measures
    per-source fetch health within three times each source's OWN declared
    interval — not worker liveness, and not editorial coverage."""
    store.register(feed_source("a", 60))
    basis = store.coverage_at(T0).basis
    assert "THREE TIMES" in basis
    assert "not worker liveness" in basis
    assert "not editorial" in basis or "economic coverage" in basis


def test_fresh_sources_and_a_dead_worker_are_reported_separately(store):
    """The condition the audit called out: sources fetched recently, worker
    dead. Coverage alone calls this healthy, and for up to three intervals it
    would have been the only thing anyone saw."""
    store.register(feed_source("a", 60))
    store.beat(status="running", pid=1, now=T0)

    # 30 minutes later: well inside a 60-minute source's allowance, but five
    # times past the worker's.
    assert store.worker_state(at(30))["state"] == "stopped"


# ------------------------------------------------ the launch path itself

def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_registration_is_reconciled_on_every_launch():
    """It used to run only when the store file was missing, so an existing
    database never received a source added to the catalogue later: the feed
    was in the code and silently never fetched."""
    script = read("launch_prototype.ps1")
    assert "--register" in script
    assert "if (-not (Test-Path $NewsStore))" not in script, (
        "registration is gated on a missing store again")


@pytest.mark.parametrize("script", ["launch_prototype.ps1", "launch_news.ps1"])
def test_the_worker_catches_up_before_entering_its_loop(script):
    """Starting the worker used to fetch nothing: it asked which sources were
    DUE. A source polled ten minutes before a restart is not due for another
    twenty, so a fresh launch could show hours-old data under a healthy
    worker.

    Asserted as the PROPERTY, not the mechanism. Both launchers now start the
    supervisor, which passes `--catch-up` to every worker it spawns — so a
    launcher satisfies this either by passing the flag itself or by delegating
    to something that always does.
    """
    text = read(script)
    direct = "--catch-up" in text
    supervised = "news_supervisor.py" in text
    assert direct or supervised, "no catch-up is guaranteed on launch"
    if supervised:
        supervisor = read("scripts/news_supervisor.py")
        assert '"--catch-up"' in supervisor, (
            "the supervisor no longer guarantees a catch-up, so neither "
            "launcher does")


def test_catch_up_is_offered_by_the_runner_itself():
    runner = read("scripts/run_news.py")
    assert '"--catch-up"' in runner
    assert "regardless of whether it is due" in runner


def test_a_partial_catch_up_does_not_stop_the_server_coming_up():
    """One unreachable source at startup must be reported as uncovered, not
    raised — the steady-state pass raises on partial failure, and a startup
    pass must not inherit that."""
    runner = read("scripts/run_news.py")
    assert "does NOT raise on a partial failure" in runner


# ------------------------- a measure not yet in force is not yet in force

def test_a_future_effective_date_is_adopted_not_effective():
    """`effective` asserts the measure APPLIES NOW. A tariff effective
    1 December does not apply on 18 October — it has been decided, which is
    `adopted`. This reaches the exposure walk, where `adopted` and `effective`
    are the two statuses that produce a signed direction."""
    from seraph.news.event_frames import frame_for
    frame = frame_for("Tariff on widgets: the measure is effective from "
                      "2026-12-01.", "s1", "tariff_announcement",
                      available_at="2026-10-18T09:00:00+05:30",
                      title="Tariff on widgets")
    assert frame.policy_status == "adopted"
    assert any("NOT yet in force" in u for u in frame.unknowns)


def test_a_past_effective_date_is_still_effective():
    from seraph.news.event_frames import frame_for
    frame = frame_for("Tariff on widgets: the measure is effective from "
                      "2026-01-01.", "s1", "tariff_announcement",
                      available_at="2026-10-18T09:00:00+05:30",
                      title="Tariff on widgets")
    assert frame.policy_status == "effective"
    assert not any("NOT yet in force" in u for u in frame.unknowns)


def test_in_force_without_a_date_is_unchanged():
    """The check needs an explicit parseable date; absent one, nothing is
    inferred about timing."""
    from seraph.news.event_frames import frame_for
    frame = frame_for("Tariff on widgets: the measure is now in force.", "s1",
                      "tariff_announcement",
                      available_at="2026-10-18T09:00:00+05:30",
                      title="Tariff on widgets")
    assert frame.policy_status == "effective"


def test_the_effective_date_pattern_has_exactly_one_definition():
    """It was about to exist in two modules, which is how DEFAULT_DSN came to
    disagree with docker-compose.yml."""
    extraction = (ROOT / "seraph/news/extraction.py").read_text(encoding="utf-8")
    assert "from seraph.news.event_frames import EFFECTIVE" in extraction
    assert extraction.count("EFFECTIVE = re.compile") == 0


# ------------------------- alive is not the same as making progress

def test_a_worker_past_its_own_deadline_is_stalled(store):
    """The heartbeat detects a worker that STOPPED. A process wedged inside a
    socket read still beats and still says `running` — only an operation that
    blew through its own declared deadline reveals it."""
    store.beat("news.poll", status="running", pid=1, now=T0, sequence=5,
               activity="polling rbi", deadline=at(2))
    assert store.worker_state(at(1))["state"] == "running"
    assert store.worker_state(at(5))["state"] == "stalled"


def test_a_long_operation_that_declares_its_deadline_is_not_a_stall(store):
    """Expected-long work and deadlock must be distinguishable, or every
    backfill looks like a hang."""
    store.beat("news.poll", status="catching_up", pid=1, now=T0, sequence=5,
               activity="backfilling 20 pages", deadline=at(30))
    assert store.worker_state(at(5))["state"] == "catching_up"


def test_an_operation_with_no_deadline_cannot_be_judged_stalled(store):
    """Absent a declared deadline there is nothing to overrun, so the age
    check is all that applies. Inventing a deadline here would make every
    slow-but-healthy operation look stuck."""
    store.beat("news.poll", status="running", pid=1, now=T0, sequence=5)
    assert store.worker_state(at(1))["state"] == "running"


def test_the_sequence_survives_a_beat_that_does_not_supply_one(store):
    """Resetting the counter on every beat would make a progressing worker
    look permanently stalled."""
    store.beat("news.poll", status="running", pid=1, now=T0, sequence=7)
    store.beat("news.poll", status="running", pid=1, now=T0, activity="x")
    assert store.worker_state(T0)["sequence"] == 7


# ------------------------------------------------- single ownership

def test_a_second_worker_is_refused_while_the_first_is_alive(store):
    """Two workers on one store double every fetch and race on the same
    acquisition requests."""
    assert store.claim_worker_ownership("news.poll", 1, now=T0)["granted"]
    refused = store.claim_worker_ownership("news.poll", 999, now=T0)
    assert refused["granted"] is False
    assert refused["held_by"] == 1
    assert "double every fetch" in refused["reason"]


def test_the_same_worker_may_reclaim_its_own_ownership(store):
    store.claim_worker_ownership("news.poll", 1, now=T0)
    assert store.claim_worker_ownership("news.poll", 1, now=at(1))["granted"]


def test_a_stale_owner_hands_over(store):
    """The previous owner is gone; refusing forever would mean a crashed
    worker locks the store out permanently."""
    store.claim_worker_ownership("news.poll", 1, now=T0)
    handover = store.claim_worker_ownership("news.poll", 999, now=at(30))
    assert handover["granted"] is True
    assert "handover" in handover["reason"]


def test_the_runner_claims_ownership_before_looping():
    runner = read("scripts/run_news.py")
    assert "claim_worker_ownership" in runner
    assert "not starting" in runner


def test_the_supervisor_beats_while_its_child_runs():
    """Beating only when a child STARTS meant that during a healthy
    long-lived child the watcher's own heartbeat went stale."""
    supervisor = read("scripts/news_supervisor.py")
    assert "threading" in supervisor
    assert "keep_alive" in supervisor or "stop_beating" in supervisor


# ----------------------------- a schema that ships must still migrate

def test_a_store_created_before_a_column_existed_gains_it(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` never adds a column to a table that
    already exists. A store created before `sequence` was introduced silently
    lacked it, and the read degraded to `unknown` instead of failing loudly —
    so stall detection was quietly inoperative on every existing store."""
    import sqlite3

    path = tmp_path / "old.sqlite"
    NewsStore(path)                       # current schema

    # Drop a column the way an older release would simply not have had it.
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE worker_heartbeat")
        db.execute("CREATE TABLE worker_heartbeat (worker TEXT PRIMARY KEY, "
                   "beat_at TEXT NOT NULL, pid INTEGER, "
                   "status TEXT NOT NULL DEFAULT 'running', detail TEXT)")
        db.commit()

    reopened = NewsStore(path)            # opening must migrate
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(worker_heartbeat)")}
    assert {"sequence", "activity", "deadline"} <= columns

    reopened.beat("news.poll", status="running", pid=1, now=T0, sequence=3,
                  activity="polling", deadline=at(2))
    assert reopened.worker_state(at(5))["state"] == "stalled"


def test_the_migration_is_additive_only(tmp_path):
    """It runs on every open, so it must not be able to lose anything."""
    source = (ROOT / "seraph/news/acquisition.py").read_text(encoding="utf-8")
    migration = source.split("def _add_missing_columns", 1)[1][:900]
    assert "ADD COLUMN" in migration
    for destructive in ("DROP COLUMN", "DROP TABLE", "DELETE FROM", "UPDATE "):
        assert destructive not in migration, f"migration can {destructive}"
