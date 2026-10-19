"""Keep the acquisition worker alive, and be honest when it cannot be.

    python scripts/news_supervisor.py                  # supervise forever
    python scripts/news_supervisor.py --max-restarts 3 # give up after 3
    python scripts/news_supervisor.py --once           # one worker, no restart

The worker is a long-running process that makes network calls, so it dies: a
feed hangs, a DNS lookup fails, the machine sleeps. Until now nothing noticed.
The heartbeat made a dead worker *visible*; this makes it *recover*.

**Why a supervisor rather than a try/except inside the worker.** A worker that
catches its own crash and continues is a worker that cannot be killed by a bug
it is suffering from — it will spin on the same failure forever and report
itself healthy throughout. A separate process that watches, restarts with
backoff, and gives up loudly after a bounded number of attempts is the honest
shape: it recovers from the transient case and escalates the persistent one.

**Restarting is not success.** A supervisor that silently restarts a worker
crashing every ten seconds has converted a loud failure into a quiet one. So
restarts are counted, exponentially backed off, recorded in the heartbeat the
console already reads, and after `--max-restarts` the supervisor stops trying
and writes `failed` with the reason. The UI then says nothing is fetching,
which is true.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import threading
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.news.acquisition import NewsStore, _now        # noqa: E402

DEFAULT_STORE = ROOT / "prototype_runs" / "news-intelligence-pilot.sqlite"
WORKER = "news.poll"
SUPERVISOR = "news.supervisor"


def _backoff(attempt: int, *, base: float = 5.0, cap: float = 300.0) -> float:
    """Exponential, capped. A feed that is down stays down for minutes, not
    milliseconds, and hammering it is both rude and useless."""
    return min(cap, base * (2 ** max(0, attempt - 1)))


def supervise(store_path: Path, *, interval: float, max_restarts: int,
              once: bool, python: str | None = None,
              spawn=subprocess.Popen, sleep=time.sleep,
              check_seconds: float = 5, startup_grace: float = 30,
              monotonic=time.monotonic) -> int:
    store = NewsStore(store_path)
    python = python or sys.executable
    restarts = 0
    child = None

    def start():
        return spawn(
            [python, str(ROOT / "scripts/run_news.py"),
             "--store", str(store_path), "--catch-up",
             "--interval", str(interval)],
            cwd=str(ROOT))

    try:
        while True:
            store.beat(SUPERVISOR, status="running", pid=os.getpid(),
                       detail=f"restarts={restarts}/{max_restarts}")
            child = start()
            print(f"[supervisor] worker pid={child.pid} "
                  f"(restart {restarts}/{max_restarts})")

            # The supervisor must prove IT is alive too. Beating only when a
            # child starts meant that during a healthy long-lived child -- the
            # normal case -- the watcher's own heartbeat went stale and the
            # thing watching for death looked dead.
            stop_beating = threading.Event()

            def keep_alive():
                beats = 0
                while not stop_beating.wait(30.0):
                    beats += 1
                    try:
                        store.beat(SUPERVISOR, status="running",
                                   pid=os.getpid(), sequence=beats,
                                   activity=f"supervising pid {child.pid}",
                                   detail=f"restarts={restarts}/{max_restarts}")
                    except Exception:            # noqa: BLE001 - best effort
                        pass

            pulse = threading.Thread(target=keep_alive, daemon=True)
            pulse.start()
            try:
                started = monotonic()
                while True:
                    try:
                        code = child.wait(timeout=check_seconds)
                        break
                    except subprocess.TimeoutExpired:
                        state = store.worker_state(_now(), WORKER)
                        belongs = state.get('pid') == child.pid
                        if monotonic() - started < startup_grace:
                            continue
                        if belongs and state['state'] in ('running', 'catching_up'):
                            continue
                        # Only terminate our own child. A stale PID in SQLite
                        # is never authority to kill an unrelated process.
                        detail = f"worker made no timely progress: {state['state']}"
                        store.beat(SUPERVISOR, status='restarting', pid=os.getpid(),
                                   detail=detail)
                        child.send_signal(signal.SIGTERM)
                        try:
                            child.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait(timeout=10)
                        store.beat(WORKER, status='failed', pid=child.pid, detail=detail)
                        code = 1
                        break
            finally:
                stop_beating.set()

            if once:
                print(f"[supervisor] worker exited {code}; --once, not restarting")
                return 0 if code == 0 else 1

            if code == 0:
                # A clean exit is the operator stopping it on purpose.
                print("[supervisor] worker exited cleanly; not restarting")
                store.beat(SUPERVISOR, status="stopped", pid=os.getpid(),
                           detail="worker exited cleanly")
                return 0

            restarts += 1
            if restarts > max_restarts:
                detail = (f"worker exited {code}; gave up after {max_restarts} "
                          f"restarts. Nothing is fetching")
                print(f"[supervisor] {detail}")
                # Both rows: the worker is not running, and the supervisor has
                # stopped trying. The console reads the worker row, so this is
                # what makes the UI tell the truth rather than imply a restart
                # is imminent.
                store.beat(WORKER, status="failed", pid=None, detail=detail)
                store.beat(SUPERVISOR, status="failed", pid=os.getpid(),
                           detail=detail)
                return 1

            wait = _backoff(restarts)
            detail = (f"worker exited {code}; restart {restarts}/{max_restarts} "
                      f"in {wait:.0f}s")
            print(f"[supervisor] {detail}")
            store.beat(WORKER, status="failed", pid=None, detail=detail)
            store.beat(SUPERVISOR, status="restarting", pid=os.getpid(),
                       detail=detail)
            sleep(wait)
    except KeyboardInterrupt:
        print("\n[supervisor] stopping")
        store.beat(SUPERVISOR, status="stopped", pid=os.getpid(),
                   detail="stopped by operator")
        return 0
    finally:
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signal.SIGTERM)
                child.wait(timeout=10)
            except Exception:                        # noqa: BLE001 - best effort
                child.kill()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--max-restarts", type=int, default=5,
                        help="after this many consecutive failures the "
                             "supervisor stops trying and records `failed`, "
                             "rather than converting a loud failure into a "
                             "quiet restart loop")
    parser.add_argument("--once", action="store_true",
                        help="run one worker and do not restart it")
    args = parser.parse_args(argv)
    from seraph.news.worker_lock import worker_lock, WorkerAlreadyRunning
    try:
        with worker_lock(args.store, 'supervisor'):
            return supervise(args.store, interval=args.interval,
                             max_restarts=args.max_restarts, once=args.once)
    except WorkerAlreadyRunning as exc:
        print(f'[supervisor] {exc}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
