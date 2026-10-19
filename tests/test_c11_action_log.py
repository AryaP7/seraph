# C11 — FR49 regulator action log: CRUD, audit journal, authorization
"""Independent of FR43 — this file imports nothing from the portfolio overlay.

Three things are being pinned down, in order of how badly they would hurt if
they drifted: the decomposition snapshot cannot be rewritten; nothing is ever
erased (NFR26); and no role but the regulator can reach any of it, checked at
the gateway before the side effect, not after.
"""
from __future__ import annotations

import asyncio

import asyncpg
import pytest
from pydantic import ValidationError

from seraph.dashboard.gateway import (
    ACTION_LOG_OPS,
    ROLE_FIELDS,
    ROLES,
    action_log_permissions,
    action_log_request,
    authorize_action_log,
)
from seraph.decision_support import (
    ACTIONS_TAKEN,
    ActionLogEntry,
    DecisionSupport,
    RegulatoryActionLog,
)

TS = "2026-08-21T15:30:00+05:30"
SNAPSHOT = (0.42, 0.31, 0.27)          # PILLAR_ORDER: hawkes, rmt, hamilton
REGULATOR = "regulator"


def _log(**kw) -> RegulatoryActionLog:
    """A log holding one created entry, for the many tests that need one."""
    log = RegulatoryActionLog()
    res = log.create(alert_id="alert-1", action="soft_warning",
                     decomposition=SNAPSHOT, actor=REGULATOR, at=TS, **kw)
    assert res.status == "ok"
    return log


# --- create / read ---------------------------------------------------------


def test_fr49_create_records_the_action_against_the_decomposition():
    log = RegulatoryActionLog()
    res = log.create(alert_id="alert-1", action="circuit_breaker",
                     decomposition=SNAPSHOT, actor=REGULATOR, at=TS)
    assert res.status == "ok"
    entry = res.value
    assert entry.alert_id == "alert-1"
    assert entry.action_taken == "circuit_breaker"
    assert entry.pillar_decomposition_snapshot == SNAPSHOT
    assert entry.revision == 1 and entry.retracted is False
    assert entry.ts == TS


def test_fr49_read_round_trips_what_was_created():
    log = _log()
    res = log.read("alert-1")
    assert res.status == "ok"
    assert res.value.action_taken == "soft_warning"
    assert log.entries() == (res.value,)


def test_fr49_create_defaults_the_timestamp_to_explicit_ist():
    res = RegulatoryActionLog().create(
        alert_id="a", action="none", decomposition=SNAPSHOT, actor=REGULATOR)
    assert res.status == "ok"
    assert res.value.ts.endswith("+05:30"), "timestamps are IST and explicit"


def test_fr49_entries_are_ordered_deterministically():
    log = RegulatoryActionLog()
    for alert, ts in (("b", "2026-08-21T15:30:00+05:30"),
                      ("a", "2026-08-20T15:30:00+05:30"),
                      ("c", "2026-08-21T15:30:00+05:30")):
        assert log.create(alert_id=alert, action="none", decomposition=SNAPSHOT,
                          actor=REGULATOR, at=ts).status == "ok"
    assert [e.alert_id for e in log.entries()] == ["a", "b", "c"]


def test_fr49_every_action_in_the_e12_enum_is_accepted():
    log = RegulatoryActionLog()
    for i, action in enumerate(ACTIONS_TAKEN):
        res = log.create(alert_id=f"alert-{i}", action=action,
                         decomposition=SNAPSHOT, actor=REGULATOR, at=TS)
        assert res.status == "ok" and res.value.action_taken == action


def test_fr49_logged_none_is_a_decision_not_an_absence():
    """"No action" is a recorded regulator decision; it must be readable as
    such and not be indistinguishable from never having logged anything."""
    log = RegulatoryActionLog()
    log.create(alert_id="a", action="none", decomposition=SNAPSHOT,
               actor=REGULATOR, at=TS)
    assert log.read("a").value.action_taken == "none"
    assert log.read("never-logged").status == "error"


# --- update ----------------------------------------------------------------


def test_fr49_update_revises_the_action_and_bumps_the_revision():
    log = _log()
    res = log.update(alert_id="alert-1", action="circuit_breaker",
                     actor=REGULATOR)
    assert res.status == "ok"
    assert res.value.action_taken == "circuit_breaker"
    assert res.value.revision == 2
    assert res.value.pillar_decomposition_snapshot == SNAPSHOT


def test_fr49_update_cannot_rewrite_the_decomposition_snapshot():
    """The snapshot is what the alert looked like when it fired. Re-keying a
    logged action to a different decomposition would void the audit trail."""
    log = _log()
    res = log.update(alert_id="alert-1", action="circuit_breaker",
                     actor=REGULATOR, decomposition=(0.9, 0.05, 0.05))
    assert res.status == "error"
    assert res.error.kind == "CONTRACT_VIOLATION"
    assert res.error.field == "decomposition"
    assert log.read("alert-1").value.pillar_decomposition_snapshot == SNAPSHOT
    assert log.read("alert-1").value.revision == 1, "a rejected update is a no-op"


def test_fr49_update_accepts_the_snapshot_echoed_back_unchanged():
    log = _log()
    res = log.update(alert_id="alert-1", action="none", actor=REGULATOR,
                     decomposition=SNAPSHOT)
    assert res.status == "ok" and res.value.revision == 2


def test_fr49_restating_the_same_action_is_a_no_op():
    log = _log()
    before = log.read("alert-1").value
    res = log.update(alert_id="alert-1", action="soft_warning", actor=REGULATOR)
    assert res.status == "ok"
    assert res.value == before and res.value.revision == 1
    assert len(log.journal()) == 1, "nothing happened, so nothing is journalled"


def test_fr49_negative_update_of_an_unknown_alert_is_rejected():
    res = RegulatoryActionLog().update(alert_id="nope", action="none",
                                       actor=REGULATOR)
    assert res.status == "error" and res.error.field == "alert_id"


# --- delete is a retraction (NFR26) ---------------------------------------


def test_fr49_delete_retracts_and_erases_nothing():
    log = _log()
    res = log.delete(alert_id="alert-1", actor=REGULATOR)
    assert res.status == "ok" and res.value.retracted is True

    assert log.entries() == (), "a retracted entry leaves the active log"
    assert log.read("alert-1").status == "error"
    # ...but it is still there for an auditor, with its action intact.
    kept = log.read("alert-1", include_retracted=True)
    assert kept.status == "ok"
    assert kept.value.action_taken == "soft_warning"
    assert kept.value.pillar_decomposition_snapshot == SNAPSHOT
    assert len(log.entries(include_retracted=True)) == 1


def test_fr49_retraction_is_recorded_in_the_journal_with_both_sides():
    log = _log()
    log.delete(alert_id="alert-1", actor=REGULATOR)
    record = log.journal()[-1]
    assert record.operation == "delete"
    assert record.before.retracted is False
    assert record.after.retracted is True
    assert record.actor == REGULATOR


def test_fr49_retracting_twice_is_idempotent():
    log = _log()
    first = log.delete(alert_id="alert-1", actor=REGULATOR)
    second = log.delete(alert_id="alert-1", actor=REGULATOR)
    assert second.status == "ok" and second.value == first.value
    assert len(log.journal()) == 2, "the second retraction is not a new event"


def test_fr49_negative_a_retracted_entry_is_not_revised_in_place():
    log = _log()
    log.delete(alert_id="alert-1", actor=REGULATOR)
    res = log.update(alert_id="alert-1", action="none", actor=REGULATOR)
    assert res.status == "error"
    assert "retracted" in res.error.detail


def test_fr49_negative_a_retracted_alert_id_stays_taken():
    log = _log()
    log.delete(alert_id="alert-1", actor=REGULATOR)
    res = log.create(alert_id="alert-1", action="none", decomposition=SNAPSHOT,
                     actor=REGULATOR, at=TS)
    assert res.status == "error"
    assert res.error.field == "alert_id"


# --- the audit journal -----------------------------------------------------


def test_fr49_journal_is_append_only_across_the_whole_history():
    log = _log()
    log.update(alert_id="alert-1", action="circuit_breaker", actor="regulator-2")
    log.delete(alert_id="alert-1", actor="regulator-3")

    journal = log.journal()
    assert [r.operation for r in journal] == ["create", "update", "delete"]
    assert [r.seq for r in journal] == [1, 2, 3]
    assert [r.actor for r in journal] == ["regulator", "regulator-2", "regulator-3"]
    assert journal[0].before is None
    # Each record's `after` is the next one's `before`: the history is
    # reconstructible from the journal alone.
    for earlier, later in zip(journal, journal[1:]):
        assert earlier.after == later.before
    assert all(r.at.endswith("+05:30") for r in journal)


def test_fr49_journal_records_are_immutable():
    log = _log()
    record = log.journal()[0]
    with pytest.raises(ValidationError):
        record.actor = "someone-else"
    with pytest.raises(ValidationError):
        log.read("alert-1").value.action_taken = "circuit_breaker"


def test_fr49_a_rejected_mutation_leaves_no_journal_record():
    log = _log()
    log.update(alert_id="alert-1", action="not-an-action", actor=REGULATOR)
    log.update(alert_id="alert-1", action="none", actor="")
    log.create(alert_id="alert-1", action="none", decomposition=SNAPSHOT,
               actor=REGULATOR)
    assert len(log.journal()) == 1


# --- rejected input --------------------------------------------------------


def test_fr49_negative_unknown_action_is_rejected():
    res = RegulatoryActionLog().create(alert_id="a", action="shut_the_market",
                                       decomposition=SNAPSHOT, actor=REGULATOR)
    assert res.status == "error"
    assert res.error.kind == "CONTRACT_VIOLATION" and res.error.field == "action"


@pytest.mark.parametrize("bad", [(0.5, 0.5), (0.3, 0.3, 0.3, 0.1), (),
                                 (0.5, 0.5, float("nan")),
                                 (0.5, 0.5, float("inf")),
                                 ("a", "b", "c"), 0.5, None])
def test_fr49_negative_malformed_decomposition_is_rejected(bad):
    res = RegulatoryActionLog().create(alert_id="a", action="none",
                                       decomposition=bad, actor=REGULATOR)
    assert res.status == "error" and res.error.field == "decomposition"


@pytest.mark.parametrize("actor", ["", "   ", None, 7])
def test_fr49_negative_an_unattributable_action_is_rejected(actor):
    """An audit record with no actor is not an audit record (NFR26)."""
    res = RegulatoryActionLog().create(alert_id="a", action="none",
                                       decomposition=SNAPSHOT, actor=actor)
    assert res.status == "error" and res.error.field == "actor"


@pytest.mark.parametrize("alert_id", ["", "   "])
def test_fr49_negative_blank_alert_id_is_rejected(alert_id):
    res = RegulatoryActionLog().create(alert_id=alert_id, action="none",
                                       decomposition=SNAPSHOT, actor=REGULATOR)
    assert res.status == "error" and res.error.field == "alert_id"


@pytest.mark.parametrize("at", ["2026-08-21", "2026-08-21T15:30:00",
                                "2026-08-21T15:30:00Z",
                                "2026-08-21T10:00:00+00:00"])
def test_fr49_negative_non_ist_timestamps_are_rejected(at):
    res = RegulatoryActionLog().create(alert_id="a", action="none",
                                       decomposition=SNAPSHOT, actor=REGULATOR,
                                       at=at)
    assert res.status == "error" and res.error.field == "at"


# --- authorization, at the gateway ----------------------------------------


def test_fr49_only_the_regulator_may_touch_the_log():
    assert action_log_permissions("regulator") == frozenset(ACTION_LOG_OPS)
    assert action_log_permissions("institutional") == frozenset()
    assert action_log_permissions("retail") == frozenset()
    assert action_log_permissions("admin") == frozenset()


def test_fr49_permissions_are_derived_from_the_gateway_field_allow_list():
    """One source of RBAC truth: visibility of `actionLog` governs reading it,
    and mutation needs the regulator role on top. A second table could drift
    from ROLE_FIELDS silently."""
    for role in ROLES:
        visible = "actionLog" in ROLE_FIELDS[role]
        perms = action_log_permissions(role)
        assert ("read" in perms) is visible
        assert bool(perms & {"create", "update", "delete"}) is (role == "regulator")


@pytest.mark.parametrize("role", ["retail", "institutional"])
@pytest.mark.parametrize("op", ACTION_LOG_OPS)
def test_fr49_negative_every_operation_is_denied_to_non_regulators(role, op):
    res = authorize_action_log(role, op)
    assert res.status == "error"
    assert res.error.kind == "CONTRACT_VIOLATION" and res.error.field == "role"


@pytest.mark.parametrize("op", ACTION_LOG_OPS)
def test_fr49_every_operation_is_allowed_to_the_regulator(op):
    assert authorize_action_log(REGULATOR, op).status == "ok"


def test_fr49_negative_unknown_role_and_unknown_operation_are_rejected():
    assert authorize_action_log("admin", "read").error.field == "role"
    assert authorize_action_log(REGULATOR, "truncate").error.field == "operation"


@pytest.mark.parametrize("role", ["retail", "institutional", "admin"])
def test_fr49_a_denied_mutation_has_no_side_effect(role):
    """Authorization resolves before the write, so a denial must leave both
    the log and its journal byte-identical."""
    log = _log()
    before = (log.entries(include_retracted=True), log.journal())
    for op, kwargs in (("create", {"alert_id": "alert-2", "action": "none",
                                   "decomposition": SNAPSHOT}),
                       ("update", {"alert_id": "alert-1",
                                   "action": "circuit_breaker"}),
                       ("delete", {"alert_id": "alert-1"})):
        res = action_log_request(role, op, log, **kwargs)
        assert res.status == "error" and res.error.field == "role"
    assert (log.entries(include_retracted=True), log.journal()) == before


def test_fr49_negative_retail_cannot_read_the_log():
    log = _log()
    res = action_log_request("retail", "read", log)
    assert res.status == "error" and res.error.field == "role"


def test_fr49_the_regulator_round_trips_crud_through_the_gateway():
    log = RegulatoryActionLog()

    created = action_log_request(REGULATOR, "create", log, alert_id="alert-1",
                                 action="soft_warning", decomposition=SNAPSHOT,
                                 at=TS)
    assert created.status == "ok"
    assert created.value["alertId"] == "alert-1"
    assert created.value["actionTaken"] == "soft_warning"
    assert created.value["pillarDecompositionSnapshot"] == SNAPSHOT

    assert action_log_request(REGULATOR, "read", log, alert_id="alert-1") \
        .value["actionTaken"] == "soft_warning"
    assert action_log_request(REGULATOR, "update", log, alert_id="alert-1",
                              action="circuit_breaker").value["revision"] == 2
    assert action_log_request(REGULATOR, "delete", log, alert_id="alert-1") \
        .value["retracted"] is True

    listed = action_log_request(REGULATOR, "read", log)
    assert listed.status == "ok" and listed.value == []
    kept = action_log_request(REGULATOR, "read", log, include_retracted=True)
    assert [e["alertId"] for e in kept.value] == ["alert-1"]
    # The actor recorded in the journal is the authorised role, not a default.
    assert {r.actor for r in log.journal()} == {REGULATOR}


def test_fr49_gateway_payload_is_the_camel_case_wire_form():
    """C12 projects `actionLog` without reshaping it (CT-8 passes it straight
    into the regulator payload)."""
    log = _log()
    rows = action_log_request(REGULATOR, "read", log).value
    assert set(rows[0]) == {"alertId", "ts", "actionTaken",
                            "pillarDecompositionSnapshot", "revision",
                            "retracted"}


@pytest.mark.parametrize("op, kwargs, field", [
    ("create", {}, "alert_id"),
    ("update", {}, "alert_id"),
    ("delete", {}, "alert_id"),
    ("create", {"alert_id": "a"}, "action"),
    ("update", {"alert_id": "a"}, "action"),
    ("create", {"alert_id": "a", "action": "none"}, "decomposition"),
])
def test_fr49_negative_gateway_rejects_incomplete_requests(op, kwargs, field):
    res = action_log_request(REGULATOR, op, RegulatoryActionLog(), **kwargs)
    assert res.status == "error" and res.error.field == field


# --- the S10 facade --------------------------------------------------------


def test_fr49_s10_log_regulatory_action_delegates_to_the_log():
    ds = DecisionSupport()
    res = ds.log_regulatory_action(alert_id="alert-1", action="soft_warning",
                                   decomposition=SNAPSHOT)
    assert res.status == "ok"
    assert isinstance(res.value, ActionLogEntry)
    assert ds.actions == [res.value.model_dump(by_alias=True)]
    assert ds.log.journal()[0].actor == REGULATOR


# --- persistence to E12 ----------------------------------------------------


class _StubConn:
    """Captures what C11 would execute. Not a database."""

    def __init__(self, fail: Exception | None = None):
        self.batches: list[tuple[str, list]] = []
        self._fail = fail

    async def executemany(self, sql, rows):
        if self._fail is not None:
            raise self._fail
        self.batches.append((sql, list(rows)))


class _StubPool:
    """Stands in for asyncpg's pool so the upsert is assertable without
    Postgres. The live round trip is CT-1's territory, not this file's."""

    def __init__(self, fail: Exception | None = None):
        self.conn = _StubConn(fail)

    def acquire(self):
        pool_conn = self.conn

        class _Acquire:
            async def __aenter__(self):
                return pool_conn

            async def __aexit__(self, *_):
                return False

        return _Acquire()


def _persist(ds: DecisionSupport, pool: _StubPool):
    return asyncio.run(ds.persist_actions(pool))


def test_fr49_persist_upserts_on_alert_id_with_the_entrys_own_timestamp():
    ds = DecisionSupport()
    ds.log_regulatory_action(alert_id="alert-1", action="soft_warning",
                             decomposition=SNAPSHOT)
    pool = _StubPool()
    res = _persist(ds, pool)
    assert res.status == "ok" and res.value == 1

    sql, rows = pool.conn.batches[0]
    assert "ON CONFLICT (alert_id) DO UPDATE" in sql, (
        "idempotency on the natural key is mandatory, not an optimisation (CT-1)")
    assert "now()" not in sql, "a replay must not restamp history"
    alert_id, ts, action, snapshot = rows[0]
    assert alert_id == "alert-1" and action == "soft_warning"
    assert snapshot == list(SNAPSHOT)
    assert ts.utcoffset().total_seconds() == 5.5 * 3600, "IST, explicit"


def test_fr49_persist_is_replayable_without_changing_the_parameters():
    ds = DecisionSupport()
    ds.log_regulatory_action(alert_id="alert-1", action="none",
                             decomposition=SNAPSHOT)
    pool = _StubPool()
    assert _persist(ds, pool).value == 1
    assert _persist(ds, pool).value == 1
    assert pool.conn.batches[0] == pool.conn.batches[1]


def test_fr49_persist_surfaces_retractions_it_cannot_express_in_e12():
    """E12 as specified has no retracted/revision column, so the gap is
    reported rather than silently dropped."""
    ds = DecisionSupport()
    ds.log_regulatory_action(alert_id="alert-1", action="soft_warning",
                             decomposition=SNAPSHOT)
    ds.log_regulatory_action(alert_id="alert-2", action="none",
                             decomposition=SNAPSHOT)
    ds.log.delete(alert_id="alert-2", actor=REGULATOR)

    pool = _StubPool()
    res = _persist(ds, pool)
    assert res.status == "ok" and res.value == 1
    assert [w.code for w in res.warnings] == ["PARTIAL_COVERAGE"]
    assert res.warnings[0].context["alertIds"] == "alert-2"
    assert [r[0] for r in pool.conn.batches[0][1]] == ["alert-1"]


def test_fr49_persisting_an_empty_log_writes_nothing():
    pool = _StubPool()
    res = _persist(DecisionSupport(), pool)
    assert res.status == "ok" and res.value == 0
    assert pool.conn.batches == []


def test_fr49_negative_a_dead_connection_is_reported_as_retryable():
    """An audit record dropped because a transient outage was reported as a
    permanent contract failure is an audit record lost."""
    ds = DecisionSupport()
    ds.log_regulatory_action(alert_id="alert-1", action="none",
                             decomposition=SNAPSHOT)
    res = _persist(ds, _StubPool(fail=asyncpg.PostgresError("connection lost")))
    assert res.status == "error"
    assert res.error.kind == "SOURCE_UNAVAILABLE"
    assert res.error.retryable is True
