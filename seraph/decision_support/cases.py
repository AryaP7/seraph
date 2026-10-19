# C11 — Regulator case workflow (PRODUCT-CONTRACTS §8; CASE01, CASE03)
"""Turn an alert or an event into an assigned, auditable case.

This EXTENDS the existing journal rather than replacing it. `action_log.py`
keeps doing what it does — immutable annotations on a scored alert, with
revisions and retractions — and a case links to those annotations. Nothing in
the existing journal is rewritten.

Three properties worth stating plainly:

* **The state machine is validated, not advisory.** `TRANSITIONS` is the whole
  truth; an unlisted move is refused with the moves that were available. A
  status field anyone can set to anything is not a workflow.
* **Concurrent edits are detected.** Every mutation carries the `expected_version`
  the caller last saw. Two investigators editing the same case do not silently
  overwrite each other — the second one is told.
* **Evidence is pinned, never "latest".** An `EvidenceRef` names a revision.
  An export resolves those exact revisions, so reopening a decision shows what
  the decider actually saw, not what the article says today.

`circuit_breaker` remains an action CATEGORY recorded against a case. Nothing
here executes a market intervention, and the export says so.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from seraph.identity import AuthorizationError, IdentityRegistry, Principal
from seraph.shared_types import IST, ist_timestamp

Status = Literal["triage", "investigating", "awaiting_information",
                 "under_review", "approved", "closed", "reopened"]

Priority = Literal["low", "medium", "high", "urgent"]

#: The same four values, iterable. A caller validating a priority needs the
#: tuple -- `Literal` is a type, not a runtime collection -- and the console
#: dispatcher inventing its own list is how "critical" got accepted at the
#: boundary and refused in the store.
PRIORITIES: tuple[str, ...] = ("low", "medium", "high", "urgent")

#: The only moves that exist. Anything else is refused, with this map quoted.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "triage": ("investigating", "closed"),
    "investigating": ("awaiting_information", "under_review", "closed"),
    "awaiting_information": ("investigating", "closed"),
    "under_review": ("approved", "investigating", "closed"),
    "approved": ("closed",),
    "closed": ("reopened",),
    "reopened": ("investigating", "closed"),
}

EventKind = Literal[
    "opened", "assigned", "status_changed", "comment", "evidence_attached",
    "information_requested", "information_received", "review_recorded",
    "decision_recorded", "closed", "reopened", "notification_sent",
]


class CaseConflict(RuntimeError):
    """Someone else changed this case since you read it."""


class InvalidTransition(ValueError):
    """That status move does not exist."""


def _now() -> str:
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


@dataclass(frozen=True)
class EvidenceRef:
    """A pinned pointer. `revision` is what makes replay honest."""

    kind: Literal["story", "news_event", "impact_estimate", "run_point",
                  "model_fit", "holdings_snapshot", "scenario", "action_log_entry"]
    ref_id: str
    revision: str
    label: str | None = None
    captured_at: str | None = None

    def key(self) -> str:
        return f"{self.kind}:{self.ref_id}@{self.revision}"

    def describe(self) -> dict:
        return dict(kind=self.kind, ref_id=self.ref_id, revision=self.revision,
                    label=self.label, captured_at=self.captured_at, pinned=True)


@dataclass(frozen=True)
class CaseEvent:
    seq: int
    case_id: str
    kind: EventKind
    actor_user_id: str
    actor_org_id: str
    at: str
    request_id: str
    detail: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return dict(seq=self.seq, case_id=self.case_id, kind=self.kind,
                    actor=self.actor_user_id, org=self.actor_org_id, at=self.at,
                    request_id=self.request_id, detail=self.detail)


class CaseStore:
    """Cases, their append-only event history, and pinned evidence."""

    def __init__(self, path, registry: IdentityRegistry):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY, org_id TEXT NOT NULL,
                    title TEXT NOT NULL, status TEXT NOT NULL, priority TEXT NOT NULL,
                    opened_by TEXT NOT NULL, opened_at TEXT NOT NULL,
                    assignee_user_id TEXT, team TEXT, due_at TEXT,
                    related TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                    closed_at TEXT, decision TEXT);
                CREATE TABLE IF NOT EXISTS case_events (
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    seq INTEGER NOT NULL, kind TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL, actor_org_id TEXT NOT NULL,
                    at TEXT NOT NULL, request_id TEXT NOT NULL, detail TEXT NOT NULL,
                    PRIMARY KEY(case_id, seq), UNIQUE(case_id, request_id));
                CREATE TABLE IF NOT EXISTS case_evidence (
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    evidence_key TEXT NOT NULL, kind TEXT NOT NULL,
                    ref_id TEXT NOT NULL, revision TEXT NOT NULL, label TEXT,
                    captured_at TEXT, attached_at TEXT NOT NULL, attached_by TEXT NOT NULL,
                    PRIMARY KEY(case_id, evidence_key));
                CREATE TABLE IF NOT EXISTS notifications (
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    dedupe_key TEXT NOT NULL, channel TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(case_id, dedupe_key));
                CREATE TRIGGER IF NOT EXISTS case_events_no_update
                    BEFORE UPDATE ON case_events
                    BEGIN SELECT RAISE(ABORT,'case history is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS case_events_no_delete
                    BEFORE DELETE ON case_events
                    BEGIN SELECT RAISE(ABORT,'case history is append-only'); END;
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

    # ------------------------------------------------------------- open

    def open_case(self, principal: Principal, *, title: str,
                  priority: Priority = "medium", related: dict | None = None,
                  due_at: str | None = None, request_id: str | None = None) -> dict:
        if principal.role != "regulator":
            raise AuthorizationError("only a regulator may open a case")
        case_id = "case_" + uuid.uuid4().hex[:16]
        opened = _now()
        related = related or {}
        with self.connect() as db:
            db.execute('INSERT INTO cases VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?,1,NULL,NULL)',
                       (case_id, principal.org_id, title, "triage", priority,
                        principal.user_id, opened, due_at, json.dumps(related)))
        self.registry.register_resource('case', case_id, org_id=principal.org_id,
                                        visibility='org')
        self._append(principal, case_id, "opened",
                     request_id or f"open:{case_id}",
                     dict(title=title, priority=priority, related=related))
        return self.case(principal, case_id)

    # ------------------------------------------------------------ reads

    def case(self, principal: Principal, case_id: str) -> dict:
        self.registry.require(principal, 'read', 'case', case_id)
        with self.connect() as db:
            row = db.execute(
                'SELECT case_id,org_id,title,status,priority,opened_by,opened_at,'
                'assignee_user_id,team,due_at,related,version,closed_at,decision '
                'FROM cases WHERE case_id=?', (case_id,)).fetchone()
        if not row:
            raise AuthorizationError('unknown case')
        return dict(case_id=row[0], org_id=row[1], title=row[2], status=row[3],
                    priority=row[4], opened_by=row[5], opened_at=row[6],
                    assignee_user_id=row[7], team=row[8], due_at=row[9],
                    related=json.loads(row[10]), version=row[11],
                    closed_at=row[12],
                    decision=json.loads(row[13]) if row[13] else None,
                    available_transitions=list(TRANSITIONS.get(row[3], ())))

    def cases(self, principal: Principal, *, status: str | None = None) -> list[dict]:
        with self.connect() as db:
            ids = [r[0] for r in db.execute(
                'SELECT case_id FROM cases' + (' WHERE status=?' if status else '')
                + ' ORDER BY opened_at', (status,) if status else ())]
        return [self.case(principal, i)
                for i in self.registry.visible(principal, 'case', ids)]

    def history(self, principal: Principal, case_id: str) -> list[CaseEvent]:
        self.registry.require(principal, 'read', 'case', case_id)
        with self.connect() as db:
            rows = db.execute(
                'SELECT seq,case_id,kind,actor_user_id,actor_org_id,at,request_id,'
                'detail FROM case_events WHERE case_id=? ORDER BY seq',
                (case_id,)).fetchall()
        return [CaseEvent(seq=r[0], case_id=r[1], kind=r[2], actor_user_id=r[3],
                          actor_org_id=r[4], at=r[5], request_id=r[6],
                          detail=json.loads(r[7])) for r in rows]

    def evidence(self, principal: Principal, case_id: str) -> list[EvidenceRef]:
        self.registry.require(principal, 'read', 'case', case_id)
        with self.connect() as db:
            rows = db.execute(
                'SELECT kind,ref_id,revision,label,captured_at FROM case_evidence '
                'WHERE case_id=? ORDER BY attached_at,evidence_key',
                (case_id,)).fetchall()
        return [EvidenceRef(kind=r[0], ref_id=r[1], revision=r[2], label=r[3],
                            captured_at=r[4]) for r in rows]

    # --------------------------------------------------------- mutations

    def assign(self, principal: Principal, case_id: str, *, assignee_user_id: str,
               team: str | None = None, expected_version: int,
               request_id: str) -> dict:
        return self._mutate(
            principal, case_id, expected_version, request_id, "assigned",
            lambda db: db.execute(
                'UPDATE cases SET assignee_user_id=?, team=? WHERE case_id=?',
                (assignee_user_id, team, case_id)),
            dict(assignee_user_id=assignee_user_id, team=team))

    def set_status(self, principal: Principal, case_id: str, *, status: Status,
                   expected_version: int, request_id: str,
                   reason: str | None = None) -> dict:
        current = self.case(principal, case_id)["status"]
        if status not in TRANSITIONS.get(current, ()):
            raise InvalidTransition(
                f"{current} -> {status} is not a valid move. From {current} you "
                f"may go to: {', '.join(TRANSITIONS.get(current, ())) or 'nowhere'}")
        closed_at = _now() if status == "closed" else None
        return self._mutate(
            principal, case_id, expected_version, request_id, "status_changed",
            lambda db: db.execute(
                'UPDATE cases SET status=?, closed_at=? WHERE case_id=?',
                (status, closed_at, case_id)),
            dict(**{"from": current}, to=status, reason=reason))

    def comment(self, principal: Principal, case_id: str, *, text: str,
                expected_version: int, request_id: str) -> dict:
        return self._mutate(principal, case_id, expected_version, request_id,
                            "comment", None, dict(text=text))

    def request_information(self, principal: Principal, case_id: str, *,
                            institution: str, question: str,
                            expected_version: int, request_id: str) -> dict:
        return self._mutate(principal, case_id, expected_version, request_id,
                            "information_requested",
                            None, dict(institution=institution, question=question))

    def attach_evidence(self, principal: Principal, case_id: str,
                        refs: list[EvidenceRef], *, expected_version: int,
                        request_id: str) -> dict:
        attached = _now()

        def write(db):
            for ref in refs:
                db.execute(
                    'INSERT OR IGNORE INTO case_evidence VALUES (?,?,?,?,?,?,?,?,?)',
                    (case_id, ref.key(), ref.kind, ref.ref_id, ref.revision,
                     ref.label, ref.captured_at, attached, principal.user_id))
        return self._mutate(principal, case_id, expected_version, request_id,
                            "evidence_attached", write,
                            dict(refs=[r.describe() for r in refs]))

    def record_decision(self, principal: Principal, case_id: str, *,
                        outcome: str, rationale: str, action_category: str | None,
                        expected_version: int, request_id: str) -> dict:
        """Record a decision. `action_category` is a label, not an execution."""
        decision = dict(outcome=outcome, rationale=rationale,
                        action_category=action_category, by=principal.user_id,
                        at=_now(),
                        note=("action_category records what KIND of action was "
                              "decided. SERAPH does not execute market "
                              "interventions and this record does not authorise one"))
        return self._mutate(
            principal, case_id, expected_version, request_id, "decision_recorded",
            lambda db: db.execute('UPDATE cases SET decision=? WHERE case_id=?',
                                  (json.dumps(decision), case_id)),
            decision)

    def _mutate(self, principal, case_id, expected_version, request_id, kind,
                write, detail) -> dict:
        self.registry.require(principal, 'write', 'case', case_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT version FROM cases WHERE case_id=?',
                             (case_id,)).fetchone()
            if not row:
                raise AuthorizationError('unknown case')
            prior = db.execute(
                'SELECT seq,kind,detail FROM case_events WHERE case_id=? '
                'AND request_id=?', (case_id, request_id)).fetchone()
            if prior:
                # Idempotent retry: the same request id returns its own result.
                return self.case(principal, case_id)
            if row[0] != expected_version:
                raise CaseConflict(
                    f"case {case_id} is at version {row[0]}, you last saw "
                    f"{expected_version}. Re-read it and re-apply your change")
            if write is not None:
                write(db)
            seq = (db.execute('SELECT COALESCE(MAX(seq),0) FROM case_events '
                              'WHERE case_id=?', (case_id,)).fetchone()[0]) + 1
            db.execute('INSERT INTO case_events VALUES (?,?,?,?,?,?,?,?)',
                       (case_id, seq, kind, principal.user_id, principal.org_id,
                        _now(), request_id, json.dumps(detail)))
            db.execute('UPDATE cases SET version=version+1 WHERE case_id=?',
                       (case_id,))
        return self.case(principal, case_id)

    def _append(self, principal, case_id, kind, request_id, detail) -> None:
        with self.connect() as db:
            seq = (db.execute('SELECT COALESCE(MAX(seq),0) FROM case_events '
                              'WHERE case_id=?', (case_id,)).fetchone()[0]) + 1
            db.execute('INSERT OR IGNORE INTO case_events VALUES (?,?,?,?,?,?,?,?)',
                       (case_id, seq, kind, principal.user_id, principal.org_id,
                        _now(), request_id, json.dumps(detail)))

    # ----------------------------------------------------- notifications

    def notify(self, principal: Principal, case_id: str, *, channel: str,
               payload: dict, dedupe_key: str) -> dict:
        """Idempotent delivery. The same dedupe key sends once."""
        self.registry.require(principal, 'write', 'case', case_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute(
                'SELECT created_at FROM notifications WHERE case_id=? AND dedupe_key=?',
                (case_id, dedupe_key)).fetchone()
            if existing:
                return dict(sent=False, already_sent_at=existing[0],
                            dedupe_key=dedupe_key)
            created = _now()
            db.execute('INSERT INTO notifications VALUES (?,?,?,?,?)',
                       (case_id, dedupe_key, channel, json.dumps(payload), created))
        return dict(sent=True, created_at=created, dedupe_key=dedupe_key)

    # ---------------------------------------------- information-as-known

    def replay(self, principal: Principal, case_id: str, *, at: str | None = None,
               through_seq: int | None = None) -> dict:
        """What was visible to this case at a past point.

        Anchor it to an event with `through_seq` wherever you can. Timestamps
        here are second-granularity, so several events in one second are
        indistinguishable by time alone — anchoring a decision replay to the
        decision's own sequence number is exact, and "what did they see before
        deciding" is `through_seq = decision_seq - 1`.

        `at` remains supported for "what did this case look like on Tuesday",
        where a second either way does not matter. The result says which bound
        was used.
        """
        self.registry.require(principal, 'read', 'case', case_id)
        if at is None and through_seq is None:
            raise ValueError('replay needs either `at` or `through_seq`')
        events = self.history(principal, case_id)
        if through_seq is not None:
            events = [e for e in events if e.seq <= through_seq]
            cutoff = events[-1].at if events else (at or _now())
            bound = f'event sequence <= {through_seq} (exact)'
        else:
            events = [e for e in events if e.at <= at]
            cutoff = at
            bound = (f'timestamp <= {at} (second granularity: events within the '
                     f'same second are all included)')
        with self.connect() as db:
            rows = db.execute(
                'SELECT kind,ref_id,revision,label,captured_at,attached_at FROM '
                'case_evidence WHERE case_id=? AND attached_at<=? ORDER BY attached_at',
                (case_id, cutoff)).fetchall()
        status = "triage"
        decision = None
        for event in events:
            if event.kind == "status_changed":
                status = event.detail.get("to", status)
            if event.kind == "decision_recorded":
                decision = event.detail
        return dict(
            case_id=case_id, as_of=cutoff, bound=bound, through_seq=through_seq,
            status_then=status, decision_then=decision,
            events=[e.describe() for e in events],
            evidence=[dict(kind=r[0], ref_id=r[1], revision=r[2], label=r[3],
                           captured_at=r[4], attached_at=r[5], pinned=True)
                      for r in rows],
            note=("every reference is resolved at the revision pinned when it was "
                  "attached, not at whatever that reference says now"))

    def export(self, principal: Principal, case_id: str, *,
               at: str | None = None, through_seq: int | None = None) -> dict:
        """An evidence packet that reproduces the decision view."""
        self.registry.require(principal, 'export', 'case', case_id)
        case = self.case(principal, case_id)
        snapshot = (self.replay(principal, case_id, through_seq=through_seq)
                    if through_seq is not None
                    else self.replay(principal, case_id, at=at or _now()))
        packet = dict(
            case=case, exported_by=principal.user_id, exported_at=_now(),
            as_of=snapshot["as_of"], bound=snapshot["bound"],
            through_seq=snapshot["through_seq"], history=snapshot["events"],
            evidence=snapshot["evidence"],
            capabilities_note=(
                "SERAPH records decisions and annotations. It does not execute "
                "market interventions; an action category in a decision record "
                "is a label, not an instruction to any venue"),
        )
        packet["packet_hash"] = hashlib.sha256(
            json.dumps(packet, sort_keys=True, default=str).encode()).hexdigest()
        return packet

    # ------------------------------------------------ correction ripple

    def cases_citing(self, principal: Principal, kind: str, ref_id: str) -> list[dict]:
        """Which cases pinned this reference — for a source-correction notice.

        Returns the cases and the revision each pinned. Nothing is rewritten:
        a correction notifies, it does not edit a past decision.
        """
        with self.connect() as db:
            rows = db.execute(
                'SELECT case_id,revision,attached_at FROM case_evidence '
                'WHERE kind=? AND ref_id=? ORDER BY attached_at',
                (kind, ref_id)).fetchall()
        allowed = set(self.registry.visible(principal, 'case', [r[0] for r in rows]))
        return [dict(case_id=r[0], pinned_revision=r[1], attached_at=r[2],
                     action="notify; the pinned revision is preserved")
                for r in rows if r[0] in allowed]
