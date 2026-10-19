# C11 — Decision Support (FR49)
"""The regulator action log: E12 rows, their CRUD, and the audit journal.

FR49 records the regulator's action per alert against that alert's pillar
decomposition. Two properties are what make the log evidence rather than
bookkeeping, and both are enforced here:

* **The snapshot is immutable.** `pillarDecompositionSnapshot` is the
  decomposition as it stood when the alert fired. `update` may change the
  action taken and nothing else — letting the snapshot be rewritten would allow
  a logged action to be re-keyed to a different decomposition, which destroys
  the only thing the log is evidence of.
* **Nothing is ever erased.** NFR26 requires immutable audit logs of every
  logged regulatory action, so `delete` is a **retraction**: the entry leaves
  the active log and the journal keeps the create, every update and the
  retraction. A hard delete is refused by design, not merely unimplemented.

Authorization is deliberately **not** here. ARCHITECTURE §3 fixes the
dependency direction C12 → C11, so the role model stays in C12's gateway
(`seraph.dashboard.gateway.authorize_action_log`) and arrives as an opaque
`actor` string that this module records and never interprets. SPEC §7 item 5
keeps using this log to recalibrate `κ` out of scope, and nothing here does so.

Two timestamps, kept apart on purpose, mirroring `PillarObservation.ts`/`tau`:
an entry's `ts` is when the action is valid as of; a journal record's `at` is
when the mutation was actually made.

**This log is in memory only, and that bounds what NFR26 currently buys.**
Entries and journal both live in the `RegulatoryActionLog` instance and are
gone when the process exits. `DecisionSupport.persist_actions` can flush the
*active* entries to E12, but that path has never been run against a live
PostgreSQL instance — only against a stub pool that captures the SQL — so
persistence is written and unverified, not working. Retractions are not durable
at all: E12 as specified (SPEC §6) carries no `retracted` or `revision`
column, so a flush skips them and reports the gap as a PARTIAL_COVERAGE
warning rather than losing it quietly. Immutability therefore holds for the
lifetime of one process and no further; making it survive a restart needs an
E12 column or a journal table, which is a C1 schema change and is not made
here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from seraph.shared_types import (
    IST,
    ContractViolation,
    Err,
    FrozenModel,
    ISOTimestamp,
    Ok,
    SeraphWarning,
    SourceUnavailable,
    Vec3,
    err,
    ist_timestamp,
    ok,
)

#: SPEC §6 E12 — the enum, verbatim. `"none"` is a recorded decision to act in
#: no way, which is not the same thing as an absent entry.
ActionTaken = Literal["none", "soft_warning", "circuit_breaker"]
ACTIONS_TAKEN: tuple[ActionTaken, ...] = ("none", "soft_warning", "circuit_breaker")

#: Only mutations are journalled. NFR26's "every dashboard view rendered" is a
#: separate C12 obligation and is not in scope here.
JournalledOperation = Literal["create", "update", "delete"]


class ActionLogEntry(FrozenModel):
    """One E12 `regulatory_action_log` row, plus the two fields the audit trail
    needs that the table as specified cannot yet hold (see `persist_actions`)."""

    alert_id: str
    ts: ISOTimestamp
    action_taken: ActionTaken
    pillar_decomposition_snapshot: Vec3        # PILLAR_ORDER
    revision: int = Field(default=1, ge=1)
    retracted: bool = False

    @field_validator("alert_id")
    @classmethod
    def _alert_id_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("alert_id must be a non-empty identifier")
        return v.strip()


class ActionLogJournalRecord(FrozenModel):
    """One append-only audit record (NFR26).

    `before`/`after` carry the whole entry on each side of the mutation, so the
    log's history is reconstructible from the journal alone without consulting
    the live entries — which is the property that makes it an audit trail
    rather than a change counter.
    """

    seq: int = Field(ge=1)
    at: ISOTimestamp
    actor: str
    operation: JournalledOperation
    alert_id: str
    before: ActionLogEntry | None = None
    after: ActionLogEntry | None = None


def _now() -> str:
    return ist_timestamp(datetime.now(IST))


def _as_decomposition(value: object) -> Ok[Vec3] | Err:
    """The snapshot is a Vec3 in PILLAR_ORDER. Length and finiteness are
    checked; sign is not, because a Shapley contribution is not constrained to
    be positive and C11 does not get to narrow C9's output."""
    try:
        items = [float(x) for x in value]              # type: ignore[union-attr]
    except (TypeError, ValueError):
        return err(ContractViolation(
            field="decomposition",
            detail="expected three numbers in PILLAR_ORDER "
                   "(hawkes, rmt, hamilton)"))
    if len(items) != 3:
        return err(ContractViolation(
            field="decomposition",
            detail=f"expected 3 components in PILLAR_ORDER, got {len(items)}"))
    if not all(math.isfinite(x) for x in items):
        return err(ContractViolation(
            field="decomposition", detail="components must be finite"))
    return ok((items[0], items[1], items[2]))


def _require_actor(actor: object) -> Ok[str] | Err:
    if not isinstance(actor, str) or not actor.strip():
        return err(ContractViolation(
            field="actor",
            detail="an audit record with no attributable actor is not an audit "
                   "record (NFR26)"))
    return ok(actor.strip())


class RegulatoryActionLog:
    """E12 held in memory, with its append-only journal.

    The container is mutable — it is the store — while every record it holds is
    frozen. Durable persistence is C1's job via E12; `DecisionSupport
    .persist_actions` flushes it.
    """

    def __init__(self) -> None:
        self._entries: dict[str, ActionLogEntry] = {}
        self._journal: list[ActionLogJournalRecord] = []

    # --- read ------------------------------------------------------------

    def read(
        self, alert_id: str, *, include_retracted: bool = False
    ) -> Ok[ActionLogEntry] | Err:
        """One entry. A retracted entry is absent from the active log but is
        still readable with `include_retracted`, because an auditor needs to
        see what was retracted."""
        entry = self._entries.get((alert_id or "").strip())
        if entry is None or (entry.retracted and not include_retracted):
            return err(ContractViolation(
                field="alert_id",
                detail=f"no action logged for alert {alert_id!r}"))
        return ok(entry)

    def entries(
        self, *, include_retracted: bool = False
    ) -> tuple[ActionLogEntry, ...]:
        """The log in a deterministic order — by alert timestamp, then id."""
        rows = [e for e in self._entries.values()
                if include_retracted or not e.retracted]
        return tuple(sorted(rows, key=lambda e: (e.ts, e.alert_id)))

    def journal(self) -> tuple[ActionLogJournalRecord, ...]:
        """The audit trail, oldest first. Returned as a tuple: callers read it,
        nothing outside this class appends to it."""
        return tuple(self._journal)

    def payload(self, *, include_retracted: bool = False) -> list[dict]:
        """Wire form for C12's `actionLog` field — camelCase per shared_types'
        alias generator, so the gateway projects it without reshaping."""
        return [e.model_dump(by_alias=True)
                for e in self.entries(include_retracted=include_retracted)]

    # --- create / update / delete ----------------------------------------

    def create(
        self,
        *,
        alert_id: str,
        action: str,
        decomposition: object,
        actor: str,
        at: str | None = None,
    ) -> Ok[ActionLogEntry] | Err:
        """Log the regulator's action against an alert's decomposition.

        Re-logging an existing alert is rejected rather than silently
        overwritten: the caller has either lost track of the log or means to
        revise it, and `update` is where a revision is recorded with its
        before/after. A retracted alert_id stays taken for the same reason.
        """
        who = _require_actor(actor)
        if who.status == "error":
            return who
        if action not in ACTIONS_TAKEN:
            return err(ContractViolation(
                field="action",
                detail=f"unknown action {action!r}; expected one of "
                       f"{ACTIONS_TAKEN}"))
        snapshot = _as_decomposition(decomposition)
        if snapshot.status == "error":
            return snapshot

        key = (alert_id or "").strip()
        if not key:
            return err(ContractViolation(
                field="alert_id",
                detail="alert_id must be a non-empty identifier"))
        existing = self._entries.get(key)
        if existing is not None:
            return err(ContractViolation(
                field="alert_id",
                detail=f"alert {key!r} already has a logged action "
                       f"({existing.action_taken!r}"
                       f"{', retracted' if existing.retracted else ''}) — "
                       f"use update to revise it"))

        try:
            entry = ActionLogEntry(
                alert_id=key,
                ts=at if at is not None else _now(),
                action_taken=action,                   # type: ignore[arg-type]
                pillar_decomposition_snapshot=snapshot.value,
            )
        except ValueError as exc:
            # The only remaining way to land here is a malformed `at` — every
            # other field has been checked above.
            return err(ContractViolation(
                field="at",
                detail=f"timestamps must be explicit IST (+05:30): {exc}"))

        self._entries[entry.alert_id] = entry
        self._append(who.value, "create", entry.alert_id, None, entry)
        return ok(entry)

    def update(
        self,
        *,
        alert_id: str,
        action: str,
        actor: str,
        decomposition: object | None = None,
    ) -> Ok[ActionLogEntry] | Err:
        """Revise the action taken, and only the action taken.

        `decomposition` is accepted so a caller can echo back what it holds,
        but it must match the stored snapshot — a mismatch is rejected rather
        than applied. Re-stating the action already on file is a no-op: no new
        revision, no journal record, nothing happened.
        """
        who = _require_actor(actor)
        if who.status == "error":
            return who
        if action not in ACTIONS_TAKEN:
            return err(ContractViolation(
                field="action",
                detail=f"unknown action {action!r}; expected one of "
                       f"{ACTIONS_TAKEN}"))

        key = (alert_id or "").strip()
        before = self._entries.get(key)
        if before is None:
            return err(ContractViolation(
                field="alert_id",
                detail=f"no action logged for alert {alert_id!r}"))
        if before.retracted:
            return err(ContractViolation(
                field="alert_id",
                detail=f"alert {key!r} was retracted; a retracted entry is "
                       f"history and is not revised in place"))

        if decomposition is not None:
            offered = _as_decomposition(decomposition)
            if offered.status == "error":
                return offered
            if offered.value != before.pillar_decomposition_snapshot:
                return err(ContractViolation(
                    field="decomposition",
                    detail="the pillar decomposition snapshot is immutable — it "
                           "is what the alert looked like when it fired; "
                           "re-keying a logged action to a different "
                           "decomposition would void the audit trail"))

        if before.action_taken == action:
            return ok(before)

        after = before.model_copy(update={
            "action_taken": action, "revision": before.revision + 1})
        self._entries[key] = after
        self._append(who.value, "update", key, before, after)
        return ok(after)

    def delete(
        self, *, alert_id: str, actor: str
    ) -> Ok[ActionLogEntry] | Err:
        """Retract an entry. **Nothing is erased** (NFR26).

        The entry is marked retracted and leaves the active log; the journal
        keeps the whole history, and `read(..., include_retracted=True)` still
        reaches it. Retracting twice is a no-op rather than a second record.
        """
        who = _require_actor(actor)
        if who.status == "error":
            return who
        key = (alert_id or "").strip()
        before = self._entries.get(key)
        if before is None:
            return err(ContractViolation(
                field="alert_id",
                detail=f"no action logged for alert {alert_id!r}"))
        if before.retracted:
            return ok(before)

        after = before.model_copy(update={
            "retracted": True, "revision": before.revision + 1})
        self._entries[key] = after
        self._append(who.value, "delete", key, before, after)
        return ok(after)

    # --- internal --------------------------------------------------------

    def _append(
        self,
        actor: str,
        operation: JournalledOperation,
        alert_id: str,
        before: ActionLogEntry | None,
        after: ActionLogEntry | None,
    ) -> None:
        self._journal.append(ActionLogJournalRecord(
            seq=len(self._journal) + 1,
            at=_now(),
            actor=actor,
            operation=operation,
            alert_id=alert_id,
            before=before,
            after=after,
        ))


@dataclass
class DecisionSupport:
    """S10 — the C11 facade. Owns the FR49 action log; persistence is C1's job
    via E12."""

    log: RegulatoryActionLog

    def __init__(self) -> None:
        self.log = RegulatoryActionLog()

    @property
    def actions(self) -> list[dict]:
        """The active log in wire form, for C12's regulator-only payload."""
        return self.log.payload()

    def log_regulatory_action(
        self,
        *,
        alert_id: str,
        action: str,
        decomposition: tuple,
        actor: str = "regulator",
    ) -> Ok[ActionLogEntry] | Err:
        """S10's `logRegulatoryAction` — FR49's create, by its interface name.

        `actor` defaults to the only role FR49 grants mutation rights to, so a
        direct call cannot misattribute the record; the gateway always passes
        the authorised role explicitly. Calling C11 directly bypasses the
        gateway exactly as calling `build_view`'s inputs directly does — the
        transport boundary is the enforcement point (FR42).
        """
        return self.log.create(alert_id=alert_id, action=action,
                               decomposition=decomposition, actor=actor)

    async def persist_actions(self, pool) -> Ok[int] | Err:
        """FR49 — flush the active log to E12 (`regulatory_action_log`).

        Idempotent on `alert_id`, matching C1's convention, so replaying a
        session cannot duplicate the audit trail: re-logging the same alert
        overwrites rather than appending a second, conflicting row. The entry's
        own `ts` is written rather than `now()`, so a replay does not silently
        restamp history.

        **Known gap, surfaced not swallowed:** E12 as specified (SPEC §6) has
        no column for `retracted` or `revision`, so a retraction cannot be
        propagated and the stale row survives in the table. Retracted entries
        are therefore skipped and a PARTIAL_COVERAGE warning names the count.
        Closing it needs an E12 column or a journal table — a C1 schema change,
        which is approval-gated and deliberately not made here.
        """
        import asyncpg as _asyncpg

        active = self.log.entries()
        retracted = [e for e in self.log.entries(include_retracted=True)
                     if e.retracted]
        warnings: tuple[SeraphWarning, ...] = ()
        if retracted:
            warnings = (SeraphWarning(
                code="PARTIAL_COVERAGE",
                message=(f"{len(retracted)} retracted entr"
                         f"{'y is' if len(retracted) == 1 else 'ies are'} not "
                         f"representable in E12 as specified; the retraction "
                         f"lives only in the in-memory journal until E12 gains "
                         f"a revision/retracted column"),
                context={"retracted": len(retracted),
                         "alertIds": ",".join(e.alert_id for e in retracted)},
            ),)
        if not active:
            return ok(0, warnings)
        try:
            async with pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO regulatory_action_log
                        (alert_id, ts, action_taken, pillar_decomposition_snapshot)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (alert_id) DO UPDATE SET
                        ts = EXCLUDED.ts,
                        action_taken = EXCLUDED.action_taken,
                        pillar_decomposition_snapshot =
                            EXCLUDED.pillar_decomposition_snapshot
                    """,
                    [(e.alert_id, datetime.fromisoformat(e.ts), e.action_taken,
                      list(e.pillar_decomposition_snapshot)) for e in active],
                )
        except (OSError, _asyncpg.InterfaceError, _asyncpg.PostgresError):
            # Matches C1's StoreReader taxonomy. A dead connection is
            # retryable and the caller must know that — an audit record
            # dropped because the write was reported as a permanent contract
            # failure is an audit record lost.
            return err(SourceUnavailable(source="postgres", http_status=None))
        return ok(len(active), warnings)
