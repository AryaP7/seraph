"""FIX01 — session-aware decision clock and as-of pillar selection.

Audit finding A01: `run_archive()` selected Hawkes by calendar date while
`InferenceSession.step()` pinned every decision to 15:30 IST. The real
2024-11-01 Muhurat refit is stamped 18:55 IST, so that date raised
`Future or missing pillar information timestamp` — and because the replay is
chronological from 2005, *every* range ending on or after 2024-11-01 failed.

These tests pin the repaired behaviour and, just as importantly, pin that the
future-information guard was not weakened: a vintage later than the decision
timestamp is withheld and the earlier vintage stands.
"""
from __future__ import annotations

import pytest

from seraph.market_calendar import (
    DECISION_POLICIES,
    REGULAR_CLOSE,
    SPECIAL_SESSIONS,
    DecisionClock,
    SessionCalendar,
    TradingSession,
)
from seraph.orchestration.prototype import InferenceSession


# --------------------------------------------------------------- calendar


def test_unregistered_date_uses_the_regular_session():
    calendar = SessionCalendar()
    session = calendar.session("2020-04-27")
    assert session.kind == "regular"
    assert session.close == REGULAR_CLOSE.isoformat()
    assert calendar.close_timestamp("2020-04-27") == "2020-04-27T15:30:00+05:30"
    assert not calendar.is_special("2020-04-27")


@pytest.mark.parametrize(
    "day,close,kind",
    [("2024-03-02", "12:30:00", "special_live"),
     ("2024-05-18", "12:30:00", "special_live"),
     ("2024-11-01", "19:00:00", "muhurat"),
     ("2025-10-21", "14:45:00", "muhurat")],
)
def test_registered_special_sessions_declare_their_own_close(day, close, kind):
    calendar = SessionCalendar()
    session = calendar.session(day)
    assert (session.kind, session.close) == (kind, close)
    assert calendar.is_special(day)


def test_every_registry_entry_states_its_evidence_status():
    for session in SPECIAL_SESSIONS:
        assert session.evidence and session.evidence_status in (
            "declared", "verified_against_exchange_notice")
        # Each entry is corroborated by an out-of-hours observation in the repo.
        assert session.corroborating_observation is not None


def test_a_declared_session_cannot_contradict_its_corroborating_observation():
    with pytest.raises(ValueError, match="does not contain its corroborating"):
        TradingSession(
            date="2024-11-01", windows=(("18:00:00", "18:30:00"),), kind="muhurat",
            evidence="deliberately too-early close",
            corroborating_observation="2024-11-01T18:55:00+05:30")


def test_registry_completeness_is_reported_as_partial_not_authoritative():
    report = SessionCalendar().completeness()
    assert report["completeness"].startswith("PARTIAL")
    assert report["evidence_status"].startswith("declared")
    assert len(report["registered_deviations"]) == len(SPECIAL_SESSIONS)


def test_decision_policies_differ_only_on_special_sessions():
    calendar = SessionCalendar()
    at_close = DecisionClock(calendar, "session_close")
    at_1530 = DecisionClock(calendar, "standard_1530")
    assert at_close.decision_timestamp("2020-04-27") == at_1530.decision_timestamp("2020-04-27")
    assert at_close.decision_timestamp("2024-11-01") == "2024-11-01T19:00:00+05:30"
    assert at_1530.decision_timestamp("2024-11-01") == "2024-11-01T15:30:00+05:30"
    assert set(DECISION_POLICIES) == {"session_close", "standard_1530"}
    with pytest.raises(ValueError):
        DecisionClock(calendar, "whenever_convenient")


def test_session_hours_feed_the_reconciliation_staleness_clock():
    from datetime import date, datetime, time

    from seraph.reconciliation.time_clock import ReconciliationClock
    from seraph.shared_types import IST

    hours = SessionCalendar().hours_map()
    assert hours[date(2024, 11, 1)] == ((time(18, 0), time(19, 0)),)
    # Two disjoint windows are summed, not bridged across the midday break.
    clock = ReconciliationClock(session_dates=frozenset({date(2024, 3, 2)}),
                                session_hours=hours)
    start = datetime(2024, 3, 2, 9, 15, tzinfo=IST)
    end = datetime(2024, 3, 2, 12, 30, tzinfo=IST)
    assert clock.elapsed_bars(start, end) == pytest.approx((45 + 60) * 60 / 300)
    # Default clock (no session_hours) keeps the previous behaviour exactly:
    # one continuous 09:15-15:30 window, so the midday break is counted.
    plain = ReconciliationClock(session_dates=frozenset({date(2024, 3, 2)}))
    assert plain.elapsed_bars(start, end) == pytest.approx(195 * 60 / 300)


# ------------------------------------------------------- inference session


def _eligible(day, tau, value=0.3):
    return dict(score_eligible=True, value=value, information_timestamp=tau,
                model="synthetic", reason="ok")


def _structural(reason="no history"):
    return dict(score_eligible=False, value=None, absence="structural",
                absence_reason="insufficient_history", reason=reason)


def _originals(day, tau, hamilton_absent=True):
    return {"hawkes": _eligible(day, tau), "rmt": _eligible(day, tau),
            "hamilton": _structural("diagnostic only")}


def test_step_evaluates_at_the_session_close_not_a_fixed_1530():
    days = ["2024-10-25", "2024-11-01"]
    session = InferenceSession(days)
    first = session.step(days[0], _originals(days[0], "2024-10-25T15:25:00+05:30"),
                         [], run_id="x")
    second = session.step(days[1], _originals(days[1], "2024-11-01T18:55:00+05:30"),
                          [], run_id="x")
    assert first["evaluation_timestamp"] == "2024-10-25T15:30:00+05:30"
    assert second["evaluation_timestamp"] == "2024-11-01T19:00:00+05:30"
    assert second["session"]["kind"] == "muhurat"
    # The evening vintage is usable at the authorised special-session close.
    assert second["coverage"]["mask"][:2] == [True, True]
    assert second["composite"] is not None


def test_a_later_vintage_is_withheld_at_a_1530_decision_never_assimilated():
    days = ["2024-10-25", "2024-11-01"]
    clock = DecisionClock(SessionCalendar(), "standard_1530")
    session = InferenceSession(days, decision_clock=clock)
    session.step(days[0], _originals(days[0], "2024-10-25T15:25:00+05:30"), [], run_id="x")
    point = session.step(days[1], _originals(days[1], "2024-11-01T18:55:00+05:30"),
                         [], run_id="x")
    assert point["evaluation_timestamp"] == "2024-11-01T15:30:00+05:30"
    # Withheld, not accepted: no observation was assimilated for either pillar.
    assert point["reconciled"]["tau_last_update"][:2] == [
        "2024-10-25T15:25:00+05:30", "2024-10-25T15:25:00+05:30"]
    # Withholding is transient — the pillars stay in the mask (D2).
    assert point["coverage"]["mask"][:2] == [True, True]
    assert all(v == "withheld_not_yet_available"
               for v in list(point["coverage"]["absence"].values())[:2])
    assert any("withheld as not yet available" in m for m in point["limitations"])


def test_an_observation_dated_after_the_session_is_still_a_hard_error():
    session = InferenceSession(["2020-01-01", "2020-01-02"])
    with pytest.raises(ValueError, match="dated after the decision session"):
        session.step("2020-01-01", _originals("2020-01-01", "2020-01-02T15:30:00+05:30"),
                     [], run_id="x")


def test_eligible_observation_without_a_timestamp_is_rejected():
    session = InferenceSession(["2020-01-01"])
    broken = _originals("2020-01-01", "2020-01-01T15:30:00+05:30")
    broken["rmt"]["information_timestamp"] = None
    with pytest.raises(ValueError, match="needs an information timestamp"):
        session.step("2020-01-01", broken, [], run_id="x")


def test_short_session_closes_early_and_a_1530_vintage_would_be_withheld():
    day = "2024-03-02"
    session = InferenceSession([day])
    point = session.step(day, _originals(day, "2024-03-02T12:25:00+05:30"), [], run_id="x")
    assert point["evaluation_timestamp"] == "2024-03-02T12:30:00+05:30"
    assert point["session"]["windows"] == [["09:15:00", "10:00:00"], ["11:30:00", "12:30:00"]]
    late = InferenceSession([day])
    withheld = late.step(day, _originals(day, "2024-03-02T15:25:00+05:30"), [], run_id="x")
    assert all(v == "withheld_not_yet_available"
               for v in list(withheld["coverage"]["absence"].values())[:2])


def test_a_delayed_vintage_is_seen_later_and_aged_by_d4_not_treated_as_fresh():
    """A withheld vintage is not lost — it is offered again at the next
    decision. D4 then judges its age: a week-late Hawkes observation (native
    cadence one bar) saturates and is excluded, with the reason recorded. It is
    never silently assimilated as if it had just arrived."""
    days = ["2024-10-25", "2024-11-01", "2024-11-08"]
    clock = DecisionClock(SessionCalendar(), "standard_1530")
    session = InferenceSession(days, decision_clock=clock)
    session.step(days[0], _originals(days[0], "2024-10-25T15:25:00+05:30"), [], run_id="x")
    withheld = session.step(days[1], _originals(days[1], "2024-11-01T18:55:00+05:30"),
                            [], run_id="x")
    assert withheld["original_pillars"]["hawkes"]["withheld_vintage"] == \
        "2024-11-01T18:55:00+05:30"
    # The persisted record never claims an eligible future-stamped observation.
    assert withheld["original_pillars"]["hawkes"]["score_eligible"] is False
    assert withheld["original_pillars"]["hawkes"]["information_timestamp"] is None
    later = session.step(days[2], _originals(days[2], "2024-11-01T18:55:00+05:30"),
                         [], run_id="x")
    assert later["reconciled"]["noise_saturated"][0] is True
    assert later["coverage"]["mask"][0] is False
    assert any("stale" in m and "hawkes" in m for m in later["limitations"])


def test_a_fresh_next_session_vintage_is_assimilated_normally():
    days = ["2024-11-01", "2024-11-08"]
    session = InferenceSession(days)
    session.step(days[0], _originals(days[0], "2024-11-01T18:55:00+05:30"), [], run_id="x")
    nxt = session.step(days[1], _originals(days[1], "2024-11-08T15:25:00+05:30"), [], run_id="x")
    assert nxt["reconciled"]["tau_last_update"][0] == "2024-11-08T15:25:00+05:30"
    assert nxt["coverage"]["mask"][:2] == [True, True]
