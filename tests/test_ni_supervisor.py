"""Worker supervision: recover from the transient, escalate the persistent.

The heartbeat made a dead worker visible. This makes it recover — without
converting a loud failure into a quiet restart loop, which is the failure mode
a supervisor most easily introduces.

A supervisor that silently restarts a worker crashing every ten seconds is
worse than no supervisor: the console reports `running` on every sample and
nobody learns that nothing works. So restarts are counted, backed off, and
bounded, and giving up writes `failed` to the row the console actually reads.

These tests use a fake spawn and a fake sleep, so they assert the policy
rather than wait out real backoff.
"""
from __future__ import annotations

import pytest

import importlib.util
import pathlib

from seraph.news.acquisition import NewsStore

# `scripts/` is not a package — it holds entry points, not library modules —
# so it is loaded by path, the same way the other script-level tests do it.
_SPEC = importlib.util.spec_from_file_location(
    "news_supervisor_under_test",
    pathlib.Path(__file__).resolve().parents[1] / "scripts/news_supervisor.py")
_SUP = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SUP)
SUPERVISOR, WORKER = _SUP.SUPERVISOR, _SUP.WORKER
_backoff, supervise = _SUP._backoff, _SUP.supervise

T0 = "2026-10-18T08:00:00+05:30"


class FakeChild:
    def __init__(self, code: int, pid: int = 4242):
        self._code, self.pid = code, pid

    def wait(self, timeout=None):
        return self._code

    def poll(self):
        return self._code

    def send_signal(self, sig):
        pass

    def kill(self):
        pass


def spawner(codes):
    """Yields a child per start, with the given exit codes in order."""
    seq = list(codes)
    started = []

    def spawn(argv, cwd=None):
        started.append(argv)
        return FakeChild(seq.pop(0) if seq else 0)

    spawn.started = started
    return spawn


@pytest.fixture
def store(tmp_path):
    return NewsStore(tmp_path / "sup.sqlite")


def run(tmp_path, codes, *, max_restarts=3, once=False):
    slept = []
    spawn = spawner(codes)
    code = supervise(tmp_path / "sup.sqlite", interval=30,
                     max_restarts=max_restarts, once=once,
                     python="python", spawn=spawn, sleep=slept.append)
    return code, spawn.started, slept


# --------------------------------------------------------------- recovery

def test_a_crashed_worker_is_restarted(tmp_path, store):
    """Two crashes then a clean exit: three starts in all."""
    code, started, _ = run(tmp_path, [1, 1, 0])
    assert len(started) == 3
    assert code == 0


def test_a_clean_exit_is_not_restarted(tmp_path, store):
    """Exit 0 is the operator stopping it on purpose. Restarting would fight
    the person at the keyboard."""
    code, started, _ = run(tmp_path, [0])
    assert len(started) == 1
    assert code == 0
    assert store.worker_state(T0, SUPERVISOR)["state"] == "stopped"


def test_the_worker_is_started_with_catch_up(tmp_path, store):
    """A restarted worker that waits out each source's interval leaves the
    console stale for exactly as long as the crash cost plus the interval."""
    _, started, _ = run(tmp_path, [0])
    assert "--catch-up" in started[0]


# ------------------------------------------------------------ escalation

def test_it_gives_up_after_the_bound_and_says_so(tmp_path, store):
    """The important half. A restart loop that never ends is a loud failure
    made quiet."""
    code, started, _ = run(tmp_path, [1, 1, 1, 1, 1, 1], max_restarts=3)
    assert code == 1
    assert len(started) == 4, "one initial start plus three restarts"
    state = store.worker_state(T0, WORKER)
    assert state["state"] == "failed"
    assert "gave up" in state["detail"]
    assert "Nothing is fetching" in state["detail"]


def test_giving_up_marks_the_row_the_console_reads(tmp_path, store):
    """The console reads the WORKER row. Writing only the supervisor's own row
    would leave the UI implying a restart is imminent when none is coming."""
    run(tmp_path, [1, 1], max_restarts=1)
    assert store.worker_state(T0, WORKER)["state"] == "failed"
    assert store.worker_state(T0, SUPERVISOR)["state"] == "failed"


def test_a_pending_restart_is_distinguishable_from_giving_up(tmp_path, store):
    """Mid-sequence the supervisor is `restarting`, not `failed`: a reader
    should be able to tell "it is coming back" from "it is not"."""
    codes = [1, 0]
    slept = []
    spawn = spawner(codes)
    seen = []

    def watch(seconds):
        seen.append(store.worker_state(T0, SUPERVISOR)["state"])
        slept.append(seconds)

    supervise(tmp_path / "sup.sqlite", interval=30, max_restarts=3, once=False,
              python="python", spawn=spawn, sleep=watch)
    assert seen == ["restarting"]


# -------------------------------------------------------------- backoff

def test_backoff_grows_and_is_capped():
    """A feed that is down stays down for minutes. Hammering it is rude and
    useless, and an uncapped exponential eventually stops retrying at all."""
    assert _backoff(1) == 5
    assert _backoff(2) == 10
    assert _backoff(3) == 20
    assert _backoff(99) == 300


def test_the_supervisor_waits_between_restarts(tmp_path, store):
    _, _, slept = run(tmp_path, [1, 1, 0])
    assert slept == [5, 10]


def test_once_runs_a_single_worker(tmp_path, store):
    code, started, slept = run(tmp_path, [1], once=True)
    assert len(started) == 1
    assert slept == []
    assert code == 1
