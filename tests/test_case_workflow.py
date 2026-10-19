"""CASE01 / CASE03 — regulator case lifecycle, concurrency and pinned evidence.

What these hold:

* a multi-actor case survives a restart with a complete actor trail;
* an invalid status move is refused and says what was available;
* two investigators cannot silently overwrite each other;
* delivery is idempotent;
* **information-as-known replay** reopens the revisions pinned then, not
  whatever those references say now;
* a source correction notifies without rewriting a past decision;
* `circuit_breaker` is a recorded category, never an executed intervention.
"""
from __future__ import annotations

import sqlite3

import pytest

from seraph.decision_support.cases import (
    TRANSITIONS,
    CaseConflict,
    CaseStore,
    EvidenceRef,
    InvalidTransition,
)
from seraph.identity import AuthorizationError, IdentityRegistry, Scope


@pytest.fixture
def desk(tmp_path):
    registry = IdentityRegistry(tmp_path / "identity.sqlite")
    store = CaseStore(tmp_path / "cases.sqlite", registry)
    registry.add_organisation("org_reg", "Market Regulator", "regulator_body")
    registry.add_organisation("org_bank", "A Bank", "institution")
    people = {}
    for key, sub, org, role in [("lead", "s-1", "org_reg", "regulator"),
                                ("analyst", "s-2", "org_reg", "regulator"),
                                ("banker", "s-3", "org_bank", "institutional")]:
        user = registry.upsert_user(provider_subject=sub, issuer="https://idp.test",
                                    display_name=key)
        registry.add_membership(user.user_id, org)
        registry.grant(user.user_id, org, role, granted_by="admin",
                       scope=Scope(own_org_only=True))
        people[key] = registry.resolve(registry.open_session(user.user_id).session_id)
    return registry, store, people


@pytest.fixture
def case(desk):
    registry, store, people = desk
    opened = store.open_case(people["lead"], title="Steel sector alert",
                             priority="high",
                             related=dict(alerts=["run:2026-01-02"],
                                          events=["evt_abc"]))
    return registry, store, people, opened


# ------------------------------------------------------------ lifecycle


def test_only_a_regulator_may_open_a_case(desk):
    _, store, people = desk
    with pytest.raises(AuthorizationError, match="only a regulator"):
        store.open_case(people["banker"], title="nope")


def test_a_new_case_starts_in_triage_and_records_who_opened_it(case):
    _, store, people, opened = case
    assert opened["status"] == "triage"
    assert opened["opened_by"] == people["lead"].user_id
    assert opened["related"]["events"] == ["evt_abc"]
    history = store.history(people["lead"], opened["case_id"])
    assert [e.kind for e in history] == ["opened"]
    assert history[0].actor_user_id == people["lead"].user_id


def test_a_full_triage_to_closure_run_survives_a_restart(case):
    registry, store, people, opened = case
    case_id = opened["case_id"]
    lead, analyst = people["lead"], people["analyst"]

    current = store.assign(lead, case_id, assignee_user_id=analyst.user_id,
                           team="surveillance", expected_version=opened["version"],
                           request_id="r1")
    current = store.set_status(analyst, case_id, status="investigating",
                               expected_version=current["version"], request_id="r2")
    current = store.comment(analyst, case_id, text="pulled the run",
                            expected_version=current["version"], request_id="r3")
    current = store.set_status(analyst, case_id, status="under_review",
                               expected_version=current["version"], request_id="r4")
    current = store.record_decision(lead, case_id, outcome="soft_warning",
                                    rationale="elevated but not systemic",
                                    action_category="soft_warning",
                                    expected_version=current["version"],
                                    request_id="r5")
    current = store.set_status(lead, case_id, status="approved",
                               expected_version=current["version"], request_id="r6")
    current = store.set_status(lead, case_id, status="closed",
                               expected_version=current["version"], request_id="r7")
    assert current["status"] == "closed" and current["closed_at"]

    reopened_store = CaseStore(store.path, registry)
    persisted = reopened_store.case(lead, case_id)
    assert persisted["status"] == "closed"
    assert persisted["assignee_user_id"] == analyst.user_id
    assert persisted["decision"]["outcome"] == "soft_warning"
    history = reopened_store.history(lead, case_id)
    assert [e.kind for e in history] == [
        "opened", "assigned", "status_changed", "comment", "status_changed",
        "decision_recorded", "status_changed", "status_changed"]
    # Every event names a real actor, not a role string.
    assert {e.actor_user_id for e in history} == {lead.user_id, analyst.user_id}


def test_a_closed_case_can_be_reopened(case):
    _, store, people, opened = case
    lead = people["lead"]
    current = store.set_status(lead, opened["case_id"], status="closed",
                               expected_version=opened["version"], request_id="c1")
    current = store.set_status(lead, opened["case_id"], status="reopened",
                               expected_version=current["version"], request_id="c2")
    assert current["status"] == "reopened"
    assert "investigating" in current["available_transitions"]


# ------------------------------------------------- transitions


def test_an_invalid_move_is_refused_and_names_what_was_available(case):
    _, store, people, opened = case
    with pytest.raises(InvalidTransition, match="not a valid move"):
        store.set_status(people["lead"], opened["case_id"], status="approved",
                         expected_version=opened["version"], request_id="x")
    try:
        store.set_status(people["lead"], opened["case_id"], status="approved",
                         expected_version=opened["version"], request_id="y")
    except InvalidTransition as exc:
        assert "investigating" in str(exc) and "closed" in str(exc)


def test_the_transition_map_has_no_dead_ends_except_by_design():
    for status, moves in TRANSITIONS.items():
        assert moves, f"{status} has no exits"
        for move in moves:
            assert move in TRANSITIONS, f"{status} -> {move} leads nowhere"


# ------------------------------------------------- concurrency


def test_two_investigators_cannot_silently_overwrite_each_other(case):
    _, store, people, opened = case
    stale_version = opened["version"]
    store.comment(people["lead"], opened["case_id"], text="first",
                  expected_version=stale_version, request_id="a")
    with pytest.raises(CaseConflict, match="Re-read it"):
        store.comment(people["analyst"], opened["case_id"], text="second",
                      expected_version=stale_version, request_id="b")


def test_an_identical_retry_is_idempotent(case):
    _, store, people, opened = case
    first = store.comment(people["lead"], opened["case_id"], text="note",
                          expected_version=opened["version"], request_id="same")
    again = store.comment(people["lead"], opened["case_id"], text="note",
                          expected_version=opened["version"], request_id="same")
    assert first == again
    assert len(store.history(people["lead"], opened["case_id"])) == 2


def test_case_history_is_append_only_in_sql(case):
    _, store, people, opened = case
    for statement in ("UPDATE case_events SET kind='x'", "DELETE FROM case_events"):
        with pytest.raises(sqlite3.IntegrityError):
            with store.connect() as db:
                db.execute(statement)


# ------------------------------------------------- notifications


def test_delivery_is_idempotent(case):
    _, store, people, opened = case
    payload = dict(to="desk@example.test", subject="assigned")
    first = store.notify(people["lead"], opened["case_id"], channel="email",
                         payload=payload, dedupe_key="assign-1")
    second = store.notify(people["lead"], opened["case_id"], channel="email",
                          payload=payload, dedupe_key="assign-1")
    assert first["sent"] is True and second["sent"] is False
    assert second["already_sent_at"] == first["created_at"]


# ------------------------------------- information-as-known replay


@pytest.fixture
def with_evidence(case):
    _, store, people, opened = case
    lead = people["lead"]
    refs = [EvidenceRef(kind="story", ref_id="sty_1", revision="rev-1",
                        label="original wire", captured_at="2026-01-02T11:40:00+05:30"),
            EvidenceRef(kind="run_point", ref_id="run_a:2026-01-02", revision="1",
                        label="CSRS at decision")]
    current = store.attach_evidence(lead, opened["case_id"], refs,
                                    expected_version=opened["version"],
                                    request_id="ev1")
    current = store.set_status(lead, opened["case_id"], status="investigating",
                               expected_version=current["version"], request_id="st1")
    current = store.record_decision(lead, opened["case_id"], outcome="monitor",
                                    rationale="watching", action_category=None,
                                    expected_version=current["version"],
                                    request_id="dec1")
    return store, people, opened["case_id"], current


def test_evidence_is_pinned_at_a_revision_never_latest(with_evidence):
    store, people, case_id, _ = with_evidence
    refs = store.evidence(people["lead"], case_id)
    assert {r.revision for r in refs} == {"rev-1", "1"}
    assert all(r.describe()["pinned"] for r in refs)


def test_replay_anchored_to_an_event_is_exact(with_evidence):
    """Second-granularity timestamps cannot separate same-second events, so a
    decision replay anchors to the decision's own sequence number."""
    store, people, case_id, _ = with_evidence
    history = store.history(people["lead"], case_id)
    decision = next(e for e in history if e.kind == "decision_recorded")
    snapshot = store.replay(people["lead"], case_id, through_seq=decision.seq - 1)
    assert snapshot["status_then"] == "investigating"
    assert snapshot["decision_then"] is None, \
        "a decision taken later must not appear in an earlier replay"
    assert len(snapshot["evidence"]) == 2
    assert "pinned when it was attached" in snapshot["note"]
    assert "exact" in snapshot["bound"]


def test_replay_by_timestamp_is_supported_and_declares_its_granularity(with_evidence):
    store, people, case_id, _ = with_evidence
    latest = store.history(people["lead"], case_id)[-1].at
    snapshot = store.replay(people["lead"], case_id, at=latest)
    assert snapshot["decision_then"] is not None
    assert "second granularity" in snapshot["bound"]


def test_replay_needs_a_bound(with_evidence):
    store, people, case_id, _ = with_evidence
    with pytest.raises(ValueError, match="either `at` or `through_seq`"):
        store.replay(people["lead"], case_id)


def test_evidence_attached_after_the_replay_point_is_not_shown(with_evidence):
    store, people, case_id, current = with_evidence
    history = store.history(people["lead"], case_id)
    assert history[1].kind == "evidence_attached"
    early = store.replay(people["lead"], case_id, through_seq=history[0].seq)
    assert all(e["attached_at"] <= early["as_of"] for e in early["evidence"])


def test_an_export_reproduces_the_decision_view_and_is_hashed(with_evidence):
    store, people, case_id, _ = with_evidence
    packet = store.export(people["lead"], case_id)
    assert packet["case"]["case_id"] == case_id
    decision = next(e for e in store.history(people["lead"], case_id)
                    if e.kind == "decision_recorded")
    pinned = store.export(people["lead"], case_id, through_seq=decision.seq)
    assert pinned["as_of"] == decision.at and pinned["through_seq"] == decision.seq
    assert packet["evidence"] and all(e["pinned"] for e in packet["evidence"])
    assert len(packet["packet_hash"]) == 64
    assert "does not execute market interventions" in packet["capabilities_note"]


def test_a_source_correction_notifies_without_rewriting_the_decision(with_evidence):
    store, people, case_id, _ = with_evidence
    affected = store.cases_citing(people["lead"], "story", "sty_1")
    assert affected and affected[0]["case_id"] == case_id
    assert affected[0]["pinned_revision"] == "rev-1"
    assert "preserved" in affected[0]["action"]
    # The pinned revision is unchanged by the notice.
    assert [r.revision for r in store.evidence(people["lead"], case_id)
            if r.ref_id == "sty_1"] == ["rev-1"]


def test_circuit_breaker_is_a_recorded_category_not_an_execution(case):
    _, store, people, opened = case
    current = store.record_decision(
        people["lead"], opened["case_id"], outcome="escalate",
        rationale="systemic risk", action_category="circuit_breaker",
        expected_version=opened["version"], request_id="d1")
    decision = current["decision"]
    assert decision["action_category"] == "circuit_breaker"
    assert "does not execute market interventions" in decision["note"]


# ------------------------------------------------- authorization


def test_another_organisation_cannot_see_or_touch_a_case(case):
    _, store, people, opened = case
    banker = people["banker"]
    assert store.cases(banker) == []
    for call in (lambda: store.case(banker, opened["case_id"]),
                 lambda: store.history(banker, opened["case_id"]),
                 lambda: store.export(banker, opened["case_id"]),
                 lambda: store.comment(banker, opened["case_id"], text="x",
                                       expected_version=1, request_id="z")):
        with pytest.raises(AuthorizationError):
            call()


def test_a_regulator_colleague_in_the_same_body_can_work_the_case(case):
    _, store, people, opened = case
    assert [c["case_id"] for c in store.cases(people["analyst"])] == \
        [opened["case_id"]]
