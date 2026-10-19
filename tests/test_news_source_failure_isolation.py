"""A failing publisher is degraded coverage, not a failed worker.

The contract these tests pin, and the way it was broken:

`work()` raised on any partial failure, so one source returning 503 made
the job fail; the loop wrote heartbeat `failed`; and the supervisor — which
terminates its child whenever the heartbeat is not in `ALIVE_STATUSES` —
killed a worker that was running perfectly and polling every other feed. A
recurring publisher error could therefore spend the whole restart budget
and stop every healthy feed with it.

The three states have to stay apart:

* the pass ran and every source answered      -> `running`
* the pass ran with failed sources, or no pass
  ran because the job lease was held          -> `degraded`, still alive
* the pass machinery itself raised, repeatedly -> `failed`, and only this
  invites a restart

The last two tests exist so the fix cannot be "never report a problem":
a worker that stops beating, and one whose own machinery keeps raising,
must both still be replaced.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import pathlib
import subprocess
import sys
from unittest.mock import patch

import pytest

from seraph.news.acquisition import NewsStore, _now

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def run_news():
    spec = importlib.util.spec_from_file_location(
        "run_news_isolation_test", ROOT / "scripts/run_news.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def supervisor():
    spec = importlib.util.spec_from_file_location(
        "news_supervisor_isolation_test", ROOT / "scripts/news_supervisor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drive_pass(run_news, store, reports, *, passes=1):
    """Run the real worker loop for `passes` passes, then interrupt it."""
    seen = []

    def stop(_seconds):
        seen.append(store.worker_state(_now()))
        if len(seen) >= passes:
            raise KeyboardInterrupt

    args = argparse.Namespace(jobs=store.path.parent / "jobs.sqlite",
                              backfill=False, once=False, catch_up=False,
                              interval=30)
    with patch.object(run_news, "register", return_value=0), \
         patch.object(run_news, "build_fetcher", return_value=object()), \
         patch.object(run_news, "poll_once", return_value=reports), \
         patch.object(run_news.time, "sleep", side_effect=stop), \
         contextlib.redirect_stdout(io.StringIO()) as out:
        run_news._run_worker(args, store)
    return seen, out.getvalue()


HEALTHY = dict(source_id="working_feed", ok=True, new_stories=1)
DOWN = dict(source_id="unavailable_feed", ok=False, new_stories=0,
            error="HTTP 503")


# ------------------------------------- the worker side of the contract

def test_a_failing_source_leaves_the_worker_alive(run_news, tmp_path):
    store = NewsStore(tmp_path / "degraded.sqlite")
    seen, _out = drive_pass(run_news, store, [HEALTHY, DOWN])
    state = seen[0]
    assert state["state"] == "degraded"
    assert state["state"] in NewsStore.ALIVE_STATUSES, (
        "a publisher's outage is not a dead worker; the supervisor "
        "restarts anything not in this tuple")


def test_the_failing_source_is_named_rather_than_hidden(run_news, tmp_path):
    store = NewsStore(tmp_path / "named.sqlite")
    seen, out = drive_pass(run_news, store, [HEALTHY, DOWN])
    assert "unavailable_feed" in (seen[0]["detail"] or "")
    assert "healthy feeds continuing" in (seen[0]["detail"] or "")
    assert "degraded sources this pass" in out


def test_a_pass_with_every_source_healthy_is_running(run_news, tmp_path):
    store = NewsStore(tmp_path / "healthy.sqlite")
    seen, _out = drive_pass(run_news, store, [HEALTHY])
    assert seen[0]["state"] == "running"
    assert seen[0]["activity"] == "waiting for next poll"


def test_a_held_lease_is_degraded_not_dead(run_news, tmp_path):
    """No acquisition happened, which must be visible — but the process is
    alive and the next pass may well get the lease."""
    from seraph.operations.jobs import JobStore
    jobs = JobStore(tmp_path / "jobs.sqlite")
    jobs.acquire(run_news.JOB, "held-by-a-live-process")
    store = NewsStore(tmp_path / "locked.sqlite")
    seen, _out = drive_pass(run_news, store, [HEALTHY])
    assert seen[0]["state"] == "degraded"
    assert seen[0]["activity"] == "lock_unavailable"


def test_repeated_job_failures_do_end_the_worker(run_news, tmp_path):
    """The fix must not become "never report a problem". When the pass
    machinery itself keeps raising, the worker exits for replacement."""
    store = NewsStore(tmp_path / "broken.sqlite")
    calls = {"n": 0}

    def exploding(*_a, **_k):
        calls["n"] += 1
        raise RuntimeError("the fetcher itself is broken")

    args = argparse.Namespace(jobs=tmp_path / "jobs.sqlite", backfill=False,
                              once=False, catch_up=False, interval=30)
    with patch.object(run_news, "register", return_value=0), \
         patch.object(run_news, "build_fetcher", return_value=object()), \
         patch.object(run_news, "poll_once", side_effect=exploding), \
         patch.object(run_news.time, "sleep", lambda _s: None), \
         contextlib.redirect_stdout(io.StringIO()):
        code = run_news._run_worker(args, store)
    assert code == 1
    assert calls["n"] == NewsStore.MAX_CONSECUTIVE_JOB_FAILURES
    assert store.worker_state(_now())["state"] == "failed"


# ---------------------------------- the supervisor side of the contract

class _Child:
    def __init__(self, pid):
        self.pid, self.signalled = pid, False

    def wait(self, timeout=None):
        if self.signalled:
            return 1
        raise subprocess.TimeoutExpired("fake", timeout)

    def poll(self):
        return 1 if self.signalled else None

    def send_signal(self, _sig):
        self.signalled = True

    def kill(self):
        self.signalled = True


def drive_supervisor(supervisor, store, *, status, max_checks=30,
                     max_restarts=2):
    children, checks = [], {"n": 0}

    def spawn(*_a, **_k):
        child = _Child(900000 + len(children))
        children.append(child)
        store.beat(pid=child.pid, status=status, activity="t", detail="t")
        return child

    def monotonic():
        checks["n"] += 1
        if checks["n"] > max_checks:
            raise KeyboardInterrupt      # bound the probe, not the policy
        return float(checks["n"])

    with contextlib.redirect_stdout(io.StringIO()):
        supervisor.supervise(store.path, interval=30, max_restarts=max_restarts,
                             once=False, spawn=spawn, sleep=lambda _s: None,
                             startup_grace=0, check_seconds=.01,
                             monotonic=monotonic)
    # `starts - 1` is what the supervisor decided; the loop is ended by a
    # KeyboardInterrupt whose teardown signals the last child.
    return max(0, len(children) - 1)


def test_the_supervisor_leaves_a_degraded_worker_alone(supervisor, tmp_path):
    store = NewsStore(tmp_path / "sup-degraded.sqlite")
    assert drive_supervisor(supervisor, store, status="degraded") == 0, (
        "a worker polling healthy feeds while one publisher is down must "
        "not be replaced")


def test_the_supervisor_still_replaces_a_worker_that_stopped(supervisor, tmp_path):
    store = NewsStore(tmp_path / "sup-stopped.sqlite")
    assert drive_supervisor(supervisor, store, status="stopped") == 2, (
        "the protection against a genuinely dead worker must survive")


def test_the_alive_set_has_one_definition(supervisor):
    """The supervisor repeated the tuple as a literal and the two drifted:
    the store learned `degraded` and the supervisor did not."""
    source = (ROOT / "scripts/news_supervisor.py").read_text(encoding="utf-8")
    assert "store.ALIVE_STATUSES" in source
    assert "('running', 'catching_up')" not in source
