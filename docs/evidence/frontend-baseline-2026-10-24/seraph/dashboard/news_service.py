"""One supervised acquisition worker, however the dashboard was started.

`launch_prototype.ps1` started a supervisor; `.claude/launch.json` and a
bare `streamlit run` did not. The same application therefore had live news
or a frozen store depending on which command the operator happened to use,
and the screen could not tell you which — it said "worker stopped", which
was true and useless.

This makes the worker a property of the application rather than of one
launcher, and three things have to hold for that to be safe:

**Exactly one.** Streamlit re-runs the script on every interaction and for
every browser tab. A naive spawn here would start a worker per tab. The
process-wide memo means the decision happens once per server process, and
behind it the OS lock in `worker_lock` is the real guarantee — a second
supervisor refuses to start even if two processes race.

**Only our own.** A launcher that already started a supervisor owns it. We
probe the lock and stand aside rather than spawning a doomed second
process, and we never signal anything we did not start.

**No orphans.** A hard-killed Streamlit cannot run cleanup, so the worker
is told to watch us: `--owner-pid` makes the supervisor shut down when
this process is gone. `atexit` handles the ordinary case.
"""
from __future__ import annotations

import atexit
import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR = ROOT / "scripts" / "news_supervisor.py"

#: Set to "0"/"false"/"off" to run the UI with no acquisition at all. The
#: screen then says nothing is fetching, which is true and is the honest
#: thing for a reviewer who wants a frozen store.
ENV_FLAG = "SERAPH_NEWS_WORKER"

_lock = threading.Lock()
_state: dict | None = None


def _enabled() -> bool:
    return os.environ.get(ENV_FLAG, "1").strip().lower() not in (
        "0", "false", "off", "no")


def _spawn(store_path: Path, interval: float, log: Path) -> subprocess.Popen:
    log.parent.mkdir(parents=True, exist_ok=True)
    stream = log.open("a", encoding="utf-8")
    # Detached enough to survive a Streamlit script re-run, but still our
    # child so we can terminate exactly this process and nothing else.
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(
        [sys.executable, str(SUPERVISOR), "--store", str(store_path),
         "--interval", str(interval), "--max-restarts", "5",
         "--owner-pid", str(os.getpid())],
        cwd=str(ROOT), stdout=stream, stderr=stream,
        creationflags=flags)


def ensure_worker(store_path, *, interval: float = 30.0,
                  log: "Path | None" = None) -> dict:
    """Make sure one supervised worker is running against `store_path`.

    Returns what was decided and why, so the UI can say which of the three
    situations it is in rather than leaving the reader to guess from a
    stale heartbeat.
    """
    global _state
    store_path = Path(store_path)
    with _lock:
        if _state is not None:
            child = _state.get("process")
            if child is not None and child.poll() is not None:
                # Ours exited. Report it; the supervisor already escalated
                # and a new one here would just re-run that escalation.
                _state = dict(_state, started=False, owner="exited",
                              reason=(f"the worker this dashboard started "
                                      f"exited with code {child.returncode}; "
                                      f"see {_state.get('log')}"))
            return dict(_state, process=None)

        if not _enabled():
            _state = dict(started=False, owner="disabled",
                          reason=(f"{ENV_FLAG} is set to off: this dashboard "
                                  f"is not acquiring news, and nothing on "
                                  f"screen will be newer than the store"))
            return dict(_state, process=None)

        from seraph.news.worker_lock import lock_held
        if lock_held(store_path, "supervisor"):
            _state = dict(started=False, owner="external",
                          reason=("a supervisor is already running against "
                                  "this store -- started by the launcher or "
                                  "by hand. This dashboard did not start a "
                                  "second one"))
            return dict(_state, process=None)

        log = Path(log or (ROOT / "prototype_runs" / "news-worker.log"))
        try:
            child = _spawn(store_path, interval, log)
        except Exception as exc:                    # noqa: BLE001 - reported
            _state = dict(started=False, owner="failed",
                          reason=f"could not start a worker: "
                                 f"{type(exc).__name__}: {exc}")
            return dict(_state, process=None)

        _state = dict(started=True, owner="dashboard", pid=child.pid,
                      process=child, log=str(log), store=str(store_path),
                      reason=(f"this dashboard started a supervised worker "
                              f"(pid {child.pid}); it stops when this "
                              f"process does"))
        atexit.register(stop_worker)
        return dict(_state, process=None)


def stop_worker() -> dict:
    """Stop the worker THIS process started, and its worker. Never anything else.

    The supervisor spawns the actual acquisition process, so stopping just
    our direct child is not enough: on Windows `terminate()` is
    `TerminateProcess`, which gives the supervisor no chance to run its
    own cleanup, and the grandchild went on fetching against a store
    nobody was reading. A measured run left two orphaned processes behind.

    So: ask politely first (a console break the supervisor handles like
    Ctrl+C, which runs its cleanup), then fall back to killing the process
    TREE by our child's pid. Both address exactly the process we started.
    """
    global _state
    with _lock:
        child = (_state or {}).get("process")
        if child is None:
            return dict(stopped=False, reason="this process started no worker")
        if child.poll() is not None:
            _state = dict(_state, started=False, owner="stopped")
            return dict(stopped=False, reason="it had already exited")
        how = []
        if os.name == "nt":
            try:
                import signal as _signal
                child.send_signal(_signal.CTRL_BREAK_EVENT)
                child.wait(timeout=10)
                how.append("console break, supervisor cleaned up")
            except Exception:                       # noqa: BLE001 - expected
                pass
        else:
            try:
                child.terminate()
                child.wait(timeout=10)
                how.append("SIGTERM, supervisor cleaned up")
            except Exception:                       # noqa: BLE001
                pass
        if child.poll() is None:
            # The tree, by pid. `/T` is what reaches the acquisition
            # process the supervisor started.
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                   capture_output=True, timeout=30)
                else:
                    child.kill()
                child.wait(timeout=10)
                how.append("killed the process tree")
            except Exception:                       # noqa: BLE001 - last resort
                how.append("could not confirm termination")
        _state = dict(_state, started=False, owner="stopped")
        return dict(stopped=True, reason="stopped the worker we started: "
                                         + "; ".join(how or ["no method succeeded"]))


def status() -> dict:
    """What this process decided about the worker, without deciding again."""
    return dict(_state or dict(started=False, owner="not_asked",
                               reason="the worker has not been asked for"))
