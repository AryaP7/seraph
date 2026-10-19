# Operations — freshness, failures and alert delivery (OPS01)
"""What is stale, what is broken, and who was told.

The audit's requirement is narrow and worth keeping narrow: outages, missing
inputs and failed notifications must be **visible and recoverable**. So this
is a health reader over what the other stores already record, plus an alert
ledger with a delivery lifecycle — not a metrics framework.

Two things it refuses to do:

* **Silence is never health.** A source that has never been fetched is
  `never_succeeded`, not `ok`. A job with no run is `never_run`. An empty
  dashboard with a green banner is the specific failure this prevents.
* **"Sent" is not "delivered".** An alert moves through
  `issued → delivered → acknowledged`, with `snoozed`, `escalated` and
  `resolved` as explicit states. A notification that failed to send is a
  recorded failure that can be retried, not an absence.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from seraph.shared_types import IST, ist_timestamp

AlertState = Literal["issued", "delivered", "acknowledged", "snoozed",
                     "escalated", "resolved", "delivery_failed"]

#: Which moves exist. Anything else is refused.
ALERT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "issued": ("delivered", "delivery_failed", "resolved"),
    "delivery_failed": ("delivered", "escalated", "resolved"),
    "delivered": ("acknowledged", "snoozed", "escalated", "resolved"),
    "acknowledged": ("snoozed", "escalated", "resolved"),
    "snoozed": ("delivered", "escalated", "resolved"),
    "escalated": ("acknowledged", "resolved"),
    "resolved": (),
}

Health = Literal["ok", "degraded", "stale", "failing", "never_succeeded",
                 "never_run"]


def _now() -> str:
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


@dataclass(frozen=True)
class Check:
    name: str
    kind: Literal["source", "job", "model", "database"]
    health: Health
    detail: str
    as_of: str | None = None
    age_minutes: float | None = None

    @property
    def ok(self) -> bool:
        return self.health == "ok"

    def describe(self) -> dict:
        return dict(name=self.name, kind=self.kind, health=self.health,
                    detail=self.detail, as_of=self.as_of,
                    age_minutes=self.age_minutes)


def _age_minutes(stamp: str, at: str) -> float:
    return (datetime.fromisoformat(at) - datetime.fromisoformat(stamp)
            ).total_seconds() / 60


def source_checks(news_store, *, at: str) -> list[Check]:
    checks = []
    for source in news_store.sources():
        health = news_store.health(source.source_id)
        if health.last_success_at is None:
            checks.append(Check(
                name=source.source_id, kind="source", health="never_succeeded",
                detail=(f"never fetched successfully"
                        + (f"; last error {health.last_error}"
                           if health.last_error else "")),
                as_of=None))
            continue
        age = _age_minutes(health.last_success_at, at)
        limit = source.poll_interval_minutes * 3
        if health.consecutive_failures >= source.max_retries:
            level, detail = "failing", (
                f"{health.consecutive_failures} consecutive failures; "
                f"last error {health.last_error}")
        elif health.consecutive_failures:
            level, detail = "degraded", (
                f"{health.consecutive_failures} consecutive failure(s) since the "
                f"last success")
        elif age > limit:
            level, detail = "stale", (
                f"last success {age:.0f}min ago, past its {limit}min policy")
        else:
            level, detail = "ok", f"last success {age:.0f}min ago"
        checks.append(Check(name=source.source_id, kind="source", health=level,
                            detail=detail, as_of=health.last_success_at,
                            age_minutes=round(age, 1)))
    return checks


def job_checks(job_store, jobs: dict[str, int], *, at: str) -> list[Check]:
    """`jobs` maps a job name to how many minutes may pass between successes."""
    checks = []
    for job, budget in sorted(jobs.items()):
        runs = job_store.runs(job, limit=10)
        succeeded = [r for r in runs if r.status == "succeeded"]
        if not runs:
            checks.append(Check(name=job, kind="job", health="never_run",
                                detail="no run has ever been recorded"))
            continue
        if not succeeded:
            checks.append(Check(
                name=job, kind="job", health="never_succeeded",
                detail=f"{len(runs)} run(s), none succeeded; "
                       f"last error {runs[0].error}"))
            continue
        latest = succeeded[0]
        age = _age_minutes(latest.finished_at or latest.started_at, at)
        failures_since = sum(1 for r in runs
                             if r.started_at > latest.started_at
                             and r.status == "failed")
        if failures_since:
            level = "failing" if failures_since >= 3 else "degraded"
            detail = f"{failures_since} failure(s) since the last success"
        elif age > budget:
            level, detail = "stale", (f"last success {age:.0f}min ago, past its "
                                      f"{budget}min budget")
        else:
            level, detail = "ok", f"last success {age:.0f}min ago"
        checks.append(Check(name=job, kind="job", health=level, detail=detail,
                            as_of=latest.finished_at, age_minutes=round(age, 1)))
    return checks


def overall(checks: list[Check]) -> dict:
    by_health: dict[str, list[str]] = {}
    for check in checks:
        by_health.setdefault(check.health, []).append(check.name)
    worst = next((h for h in ("failing", "never_succeeded", "never_run",
                              "stale", "degraded") if h in by_health), "ok")
    return dict(
        status=worst, checks=[c.describe() for c in checks],
        by_health={k: sorted(v) for k, v in sorted(by_health.items())},
        note=("a check with no data reads as never_succeeded or never_run, "
              "never as ok: silence is not health"))


class AlertLedger:
    """Issued alerts and what actually happened to them."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    subject TEXT NOT NULL, severity TEXT NOT NULL,
                    issued_at TEXT NOT NULL, state TEXT NOT NULL,
                    recipient TEXT, payload TEXT NOT NULL,
                    snooze_until TEXT);
                CREATE TABLE IF NOT EXISTS alert_events (
                    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
                    seq INTEGER NOT NULL, state TEXT NOT NULL, at TEXT NOT NULL,
                    actor TEXT, detail TEXT, PRIMARY KEY(alert_id, seq));
                CREATE TRIGGER IF NOT EXISTS alert_events_no_update
                    BEFORE UPDATE ON alert_events
                    BEGIN SELECT RAISE(ABORT,'the alert trail is append-only'); END;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def issue(self, *, kind: str, subject: str, severity: str,
              payload: dict, recipient: str | None = None,
              dedupe_key: str | None = None) -> dict:
        """Issue an alert. A repeated dedupe key does not issue a second."""
        alert_id = dedupe_key or ("alert_" + uuid.uuid4().hex[:16])
        issued = _now()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT state,issued_at FROM alerts WHERE '
                                  'alert_id=?', (alert_id,)).fetchone()
            if existing:
                return dict(alert_id=alert_id, issued=False,
                            state=existing[0], issued_at=existing[1])
            db.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,NULL)',
                       (alert_id, kind, subject, severity, issued, "issued",
                        recipient, json.dumps(payload)))
            db.execute('INSERT INTO alert_events VALUES (?,?,?,?,?,?)',
                       (alert_id, 1, "issued", issued, None, None))
        return dict(alert_id=alert_id, issued=True, state="issued",
                    issued_at=issued)

    def transition(self, alert_id: str, state: AlertState, *,
                   actor: str | None = None, detail: str | None = None,
                   snooze_until: str | None = None) -> dict:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM alerts WHERE alert_id=?',
                             (alert_id,)).fetchone()
            if not row:
                raise KeyError(f"unknown alert {alert_id}")
            current = row[0]
            if state not in ALERT_TRANSITIONS.get(current, ()):
                raise ValueError(
                    f"{current} -> {state} is not a valid alert move. From "
                    f"{current}: {', '.join(ALERT_TRANSITIONS.get(current, ())) or 'nowhere'}")
            seq = (db.execute('SELECT COALESCE(MAX(seq),0) FROM alert_events '
                              'WHERE alert_id=?', (alert_id,)).fetchone()[0]) + 1
            at = _now()
            db.execute('UPDATE alerts SET state=?, snooze_until=COALESCE(?,snooze_until) '
                       'WHERE alert_id=?', (state, snooze_until, alert_id))
            db.execute('INSERT INTO alert_events VALUES (?,?,?,?,?,?)',
                       (alert_id, seq, state, at, actor, detail))
        return dict(alert_id=alert_id, state=state, at=at, seq=seq)

    def alert(self, alert_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                'SELECT alert_id,kind,subject,severity,issued_at,state,recipient,'
                'payload,snooze_until FROM alerts WHERE alert_id=?',
                (alert_id,)).fetchone()
            events = db.execute(
                'SELECT seq,state,at,actor,detail FROM alert_events '
                'WHERE alert_id=? ORDER BY seq', (alert_id,)).fetchall()
        if not row:
            return None
        return dict(alert_id=row[0], kind=row[1], subject=row[2], severity=row[3],
                    issued_at=row[4], state=row[5], recipient=row[6],
                    payload=json.loads(row[7]), snooze_until=row[8],
                    trail=[dict(seq=e[0], state=e[1], at=e[2], actor=e[3],
                                detail=e[4]) for e in events])

    def undelivered(self, *, older_than_minutes: int = 15,
                    at: str | None = None) -> list[dict]:
        """Alerts that were issued and never reached anyone. Retryable."""
        moment = at or _now()
        with self.connect() as db:
            rows = db.execute(
                "SELECT alert_id,kind,subject,issued_at,state FROM alerts "
                "WHERE state IN ('issued','delivery_failed') ORDER BY issued_at"
            ).fetchall()
        out = []
        for alert_id, kind, subject, issued_at, state in rows:
            age = _age_minutes(issued_at, moment)
            if age >= older_than_minutes:
                out.append(dict(alert_id=alert_id, kind=kind, subject=subject,
                                issued_at=issued_at, state=state,
                                age_minutes=round(age, 1),
                                note="issued but never delivered; retry or escalate"))
        return out
