# Operations — idempotent scheduled jobs with locks and recovery (PIPE03)
"""Cron-shaped jobs that survive being run twice, interrupted, or both.

AGENTS.md §2 chose cron plus idempotent scripts over a workflow engine, which
is right for a single node at daily cadence — but "idempotent script" is a
claim, and this module is where it becomes a property:

* **A lock, with an owner and an expiry.** Two cron ticks overlapping is the
  normal failure, not an exotic one. A lock that cannot expire turns one
  crashed run into a permanently wedged job, so leases time out and the
  takeover is recorded.
* **A checkpoint per job run.** A long backfill that dies halfway resumes from
  its checkpoint instead of starting again or, worse, skipping the gap.
* **Failures are rows, not log lines.** `JobRun` records the attempt, the
  error and the retry count, so "the feed has been failing since Tuesday" is
  a query rather than an archaeology exercise.
* **Bounded retries.** A job that fails its budget stays failed and visible.
  Infinite retry is how a broken source becomes silent.

Nothing here schedules anything itself. Cron (or Task Scheduler) invokes the
entry point; this provides the guarantees the entry point needs.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from seraph.shared_types import IST, ist_timestamp

JobStatus = Literal["running", "succeeded", "failed", "lock_unavailable"]

DEFAULT_LEASE_MINUTES = 30


def _now() -> datetime:
    return datetime.now(IST).replace(microsecond=0)


def _stamp(moment: datetime | None = None) -> str:
    return ist_timestamp(moment or _now())


class LockUnavailable(RuntimeError):
    """Another live holder has this job's lock."""


def pid_alive(pid: int) -> bool | None:
    """Is this local process id running?

    `True`, `False`, or `None` when the question cannot be answered. The
    third answer is the important one: callers decide whether to break a
    lease or shut a supervisor down on the strength of it, and an
    unanswerable question must never be rounded down to "dead".
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True                 # exists, owned by someone else
        except OSError:
            return None
        return True
    import ctypes
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE = 0x1000, 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # 87 ERROR_INVALID_PARAMETER: no such process. Anything else
        # (access denied, for instance) leaves the question open.
        return False if kernel32.GetLastError() == 87 else None
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


@dataclass(frozen=True)
class JobRun:
    run_id: str
    job: str
    started_at: str
    status: JobStatus
    attempt: int = 1
    finished_at: str | None = None
    error: str | None = None
    checkpoint: dict | None = None
    detail: dict | None = None

    def describe(self) -> dict:
        return dict(run_id=self.run_id, job=self.job, started_at=self.started_at,
                    finished_at=self.finished_at, status=self.status,
                    attempt=self.attempt, error=self.error,
                    checkpoint=self.checkpoint, detail=self.detail)


class JobStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS job_locks (
                    job TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    acquired_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                    run_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS job_runs (
                    run_id TEXT PRIMARY KEY, job TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT,
                    status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 1,
                    error TEXT, detail TEXT);
                CREATE INDEX IF NOT EXISTS job_runs_by_job
                    ON job_runs(job, started_at DESC);
                CREATE TABLE IF NOT EXISTS job_checkpoints (
                    job TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL, run_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS job_watermarks (
                    job TEXT NOT NULL, stream TEXT NOT NULL,
                    position TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(job, stream));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    # ------------------------------------------------------------- locks

    @staticmethod
    def owner_tag() -> str:
        return f"{socket.gethostname()}:{os.getpid()}"

    def acquire(self, job: str, run_id: str, *,
                lease_minutes: int = DEFAULT_LEASE_MINUTES,
                now: datetime | None = None) -> dict:
        moment = now or _now()
        expires = _stamp(moment + timedelta(minutes=lease_minutes))
        owner = self.owner_tag()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            held = db.execute('SELECT owner,expires_at,run_id FROM job_locks '
                              'WHERE job=?', (job,)).fetchone()
            if held and held[1] > _stamp(moment):
                raise LockUnavailable(
                    f"{job} is locked by {held[0]} until {held[1]} "
                    f"(run {held[2]})")
            taken_over = bool(held)
            db.execute('INSERT OR REPLACE INTO job_locks VALUES (?,?,?,?,?)',
                       (job, owner, _stamp(moment), expires, run_id))
        return dict(job=job, owner=owner, expires_at=expires,
                    took_over_expired_lease=taken_over,
                    previous_owner=held[0] if held else None)

    def release(self, job: str, run_id: str) -> None:
        with self.connect() as db:
            db.execute('DELETE FROM job_locks WHERE job=? AND run_id=?',
                       (job, run_id))

    def lock_state(self, job: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT job,owner,acquired_at,expires_at,run_id '
                             'FROM job_locks WHERE job=?', (job,)).fetchone()
        return dict(job=row[0], owner=row[1], acquired_at=row[2],
                    expires_at=row[3], run_id=row[4]) if row else None

    @staticmethod
    def owner_alive(owner: str) -> bool | None:
        """Is the process in this owner tag still running on THIS host?

        `True`, `False`, or `None` when the question cannot be answered —
        another host, or a tag that cannot be read. `None` is never
        treated as `False`: killing a lease on an unanswerable question is
        how two workers end up fetching the same sources at once.
        """
        try:
            host, pid = owner.rsplit(":", 1)
            pid = int(pid)
        except (AttributeError, ValueError):
            return None
        if host != socket.gethostname():
            return None
        return pid_alive(pid)

    def reconcile_lock(self, job: str, *, reason: str,
                       now: datetime | None = None) -> dict:
        """Clear a lease whose holder is provably gone. Never on a guess.

        A worker that crashes mid-run leaves a lease behind for its whole
        term — thirty minutes by default. The replacement worker then holds
        the OS lock on the store (so it IS the only worker), calls
        `run()`, gets `lock_unavailable`, and does **no fetching at all**
        while its heartbeat keeps saying `running`. Half an hour of a
        healthy-looking worker that is not acquiring anything is worse than
        a crash, because nothing on any screen distinguishes it.

        The caller must already hold the exclusive OS lock for the store
        this job serves; that is the evidence that no live local worker is
        legitimately mid-run. This then checks the recorded owner as well,
        and refuses to break a lease held by a live process or by a process
        it cannot ask about.
        """
        moment = now or _now()
        held = self.lock_state(job)
        if held is None:
            return dict(job=job, cleared=False, held=None,
                        reason="no lease is held")
        if held["expires_at"] <= _stamp(moment):
            return dict(job=job, cleared=False, held=held, expired=True,
                        reason=("the lease has already expired and will be "
                                "taken over by the next run"))
        alive = self.owner_alive(held["owner"])
        if alive is not False:
            return dict(job=job, cleared=False, held=held, owner_alive=alive,
                        reason=(f"lease owner {held['owner']} is "
                                + ("still running" if alive
                                   else "on another host or cannot be "
                                        "checked from here")
                                + ": not broken"))
        with self.connect() as db:
            db.execute('DELETE FROM job_locks WHERE job=? AND run_id=?',
                       (job, held["run_id"]))
        record = JobRun(run_id=held["run_id"], job=job,
                        started_at=held["acquired_at"],
                        finished_at=_stamp(moment), status="failed",
                        error=(f"lease abandoned by {held['owner']}: the "
                               f"process is gone. Cleared by {self.owner_tag()} "
                               f"({reason})"),
                        detail=dict(reconciled=True, previous_owner=held["owner"],
                                    expires_at=held["expires_at"]))
        self._record(record)
        return dict(job=job, cleared=True, held=held, owner_alive=False,
                    reason=(f"lease owner {held['owner']} is gone; the "
                            f"abandoned run is recorded as failed"))

    # ------------------------------------------------------ checkpoints

    def checkpoint(self, job: str, payload: dict, *, run_id: str) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO job_checkpoints VALUES (?,?,?,?)',
                       (job, json.dumps(payload), _stamp(), run_id))

    def last_checkpoint(self, job: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT payload,updated_at,run_id FROM '
                             'job_checkpoints WHERE job=?', (job,)).fetchone()
        if not row:
            return None
        return dict(payload=json.loads(row[0]), updated_at=row[1], run_id=row[2])

    def clear_checkpoint(self, job: str) -> None:
        with self.connect() as db:
            db.execute('DELETE FROM job_checkpoints WHERE job=?', (job,))

    def set_watermark(self, job: str, stream: str, position: str) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO job_watermarks VALUES (?,?,?,?)',
                       (job, stream, position, _stamp()))

    def watermark(self, job: str, stream: str) -> str | None:
        with self.connect() as db:
            row = db.execute('SELECT position FROM job_watermarks WHERE job=? '
                             'AND stream=?', (job, stream)).fetchone()
        return row[0] if row else None

    # -------------------------------------------------------- execution

    def runs(self, job: str | None = None, *, limit: int = 50) -> list[JobRun]:
        sql = ('SELECT run_id,job,started_at,finished_at,status,attempt,error,'
               'detail FROM job_runs')
        args: tuple = ()
        if job:
            sql += ' WHERE job=?'
            args = (job,)
        sql += ' ORDER BY started_at DESC, rowid DESC LIMIT ?'
        with self.connect() as db:
            rows = db.execute(sql, args + (limit,)).fetchall()
        return [JobRun(run_id=r[0], job=r[1], started_at=r[2], finished_at=r[3],
                       status=r[4], attempt=r[5], error=r[6],
                       detail=json.loads(r[7]) if r[7] else None) for r in rows]

    def run(self, job: str, work, *, max_attempts: int = 3,
            lease_minutes: int = DEFAULT_LEASE_MINUTES,
            now: datetime | None = None) -> JobRun:
        """Run `work(context)` under a lock, with bounded retries.

        `context` exposes `checkpoint(payload)` and `resume_from`, so a job
        that died halfway continues instead of restarting.
        """
        run_id = "job_" + uuid.uuid4().hex[:16]
        started = _stamp(now)
        try:
            lease = self.acquire(job, run_id, lease_minutes=lease_minutes, now=now)
        except LockUnavailable as exc:
            record = JobRun(run_id=run_id, job=job, started_at=started,
                            finished_at=started, status="lock_unavailable",
                            error=str(exc))
            self._record(record)
            return record

        resume = self.last_checkpoint(job)
        context = _JobContext(self, job, run_id,
                              resume_from=resume["payload"] if resume else None,
                              lease=lease)
        error = None
        for attempt in range(1, max_attempts + 1):
            try:
                detail = work(context) or {}
                self.clear_checkpoint(job)
                self.release(job, run_id)
                record = JobRun(run_id=run_id, job=job, started_at=started,
                                finished_at=_stamp(), status="succeeded",
                                attempt=attempt,
                                detail=dict(detail, lease=lease))
                self._record(record)
                return record
            except Exception as exc:                          # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                context.last_traceback = traceback.format_exc(limit=3)
        # Budget exhausted: the checkpoint is KEPT so the next tick resumes.
        self.release(job, run_id)
        record = JobRun(run_id=run_id, job=job, started_at=started,
                        finished_at=_stamp(), status="failed",
                        attempt=max_attempts, error=error,
                        checkpoint=(self.last_checkpoint(job) or {}).get("payload"),
                        detail=dict(lease=lease,
                                    note="the checkpoint is preserved so the next "
                                         "run resumes rather than restarts"))
        self._record(record)
        return record

    def _record(self, record: JobRun) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO job_runs VALUES (?,?,?,?,?,?,?,?)',
                       (record.run_id, record.job, record.started_at,
                        record.finished_at, record.status, record.attempt,
                        record.error,
                        json.dumps(record.detail) if record.detail else None))


@dataclass
class _JobContext:
    store: JobStore
    job: str
    run_id: str
    resume_from: dict | None = None
    lease: dict | None = None
    last_traceback: str | None = None

    def checkpoint(self, payload: dict) -> None:
        self.store.checkpoint(self.job, payload, run_id=self.run_id)

    def set_watermark(self, stream: str, position: str) -> None:
        self.store.set_watermark(self.job, stream, position)

    def watermark(self, stream: str) -> str | None:
        return self.store.watermark(self.job, stream)
