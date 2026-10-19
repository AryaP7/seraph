"""T06 — deciding at a timestamp, and the properties that makes necessary (R01).

The audit found the live entry point never invoked the risk engine. The only
orchestration that existed was keyed by a session date, so the obvious way to
get intraday decisions — call `InferenceSession.step()` again with the same
date — would re-append the same vintage to each pillar's ECDF and shrink the
uncertainty of a pillar that had produced nothing new.

These tests pin the properties that make a timestamp service correct:

* ordering, idempotency and request immutability,
* the five producer times kept apart, so a model deployed tomorrow is not
  available today,
* a vintage assimilated exactly once however often it is polled,
* declared cadence, with a carried-forward daily pillar ageing properly,
* the process clock's additivity — a day of bar-by-bar predictions carries the
  same total process covariance as one daily prediction,
* snapshot/restore that refuses a mismatched pipeline or calendar.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from seraph.live.inference import (
    BARS_PER_REGULAR_SESSION,
    DECLARED_CADENCE,
    DecisionRequest,
    DeploymentRegistry,
    InferenceError,
    InferenceService,
    ModelBundle,
    StandardizerHistory,
    Vintage,
    sessions_elapsed,
)
from seraph.live.publication import FeedProvenance
from seraph.reconciliation.kalman import KalmanReconciler
from seraph.reconciliation.time_clock import ReconciliationClock

IST = timezone(timedelta(hours=5, minutes=30))

SESSIONS = [f"2024-01-{d:02d}" for d in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12)]


def at(day: str, hour: int, minute: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+05:30")


def service(**kw) -> InferenceService:
    return InferenceService(session_dates=SESSIONS, **kw)


def vintage(producer: str, day: str, hour: int, minute: int, value: float,
            **kw) -> Vintage:
    stamp = at(day, hour, minute).isoformat()
    return Vintage(producer=producer, input_end=stamp,
                   emission_available_at=kw.pop("available", stamp),
                   value=value, **kw)


def request(n: int, day: str, hour: int, minute: int, **kw) -> DecisionRequest:
    return DecisionRequest(decision_id=f"d{n}", as_of=at(day, hour, minute),
                           trigger=kw.pop("trigger", "bar_close"),
                           mode=kw.pop("mode", "historical_replay"), **kw)


def seeded(svc: InferenceService, day: str = "2024-01-01") -> None:
    """Give every pillar enough ECDF history that a rank is meaningful."""
    history = []
    for i in range(30):
        stamp = at(SESSIONS[0], 9, 15) - timedelta(days=40 - i)
        for pillar, scale in (("hawkes", 0.1), ("rmt", 0.5), ("hamilton", 0.3)):
            history.append(Vintage(
                producer=pillar, input_end=stamp.isoformat(),
                emission_available_at=stamp.isoformat(),
                value=scale + 0.001 * i))
    svc.warm_start(history, cutoff=at(SESSIONS[0], 9, 15))


# ------------------------------------------------------- ordering, identity


def test_a_decision_timestamp_must_be_aware():
    with pytest.raises(InferenceError, match="timezone-aware"):
        DecisionRequest(decision_id="d", as_of=datetime(2024, 1, 2, 10, 0),
                        trigger="bar_close", mode="historical_replay")


def test_decisions_must_not_go_backwards():
    svc = service()
    seeded(svc)
    svc.process(request(1, "2024-01-02", 10, 0),
                vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    with pytest.raises(InferenceError, match="decisions are ordered"):
        svc.process(request(2, "2024-01-02", 9, 30))


def test_several_decisions_in_one_day_are_allowed():
    """Bar-close decisions are the point; one per day is the defect."""
    svc = service()
    seeded(svc)
    for i, minute in enumerate((20, 25, 30, 35), start=1):
        result = svc.process(request(i, "2024-01-02", 10, minute),
                             vintages=[vintage("hawkes", "2024-01-02", 10,
                                               minute, 0.1 + 0.001 * i)])
        assert result.csrs is not None


def test_a_duplicate_request_returns_the_existing_result():
    svc = service()
    seeded(svc)
    first = svc.process(request(1, "2024-01-02", 10, 0),
                        vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    again = svc.process(request(1, "2024-01-02", 10, 0),
                        vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    assert again.duplicate_of == "d1"
    assert again.state_after_id == first.state_after_id
    assert again.csrs.model_dump() == first.csrs.model_dump()


def test_a_decision_id_cannot_be_reused_with_different_content():
    svc = service()
    seeded(svc)
    svc.process(request(1, "2024-01-02", 10, 0))
    with pytest.raises(InferenceError, match="immutable"):
        svc.process(request(1, "2024-01-02", 10, 5))


def test_repeating_a_request_does_not_advance_the_ecdf():
    svc = service()
    seeded(svc)
    v = vintage("rmt", "2024-01-02", 9, 50, 0.5)
    before = svc.standardizer.observations("rmt")
    svc.process(request(1, "2024-01-02", 10, 0), vintages=[v])
    once = svc.standardizer.observations("rmt")
    svc.process(request(1, "2024-01-02", 10, 0), vintages=[v])
    assert once == before + 1
    assert svc.standardizer.observations("rmt") == once


def test_input_batch_ids_must_be_unique_within_a_decision():
    with pytest.raises(InferenceError, match="batch identity"):
        DecisionRequest(decision_id="d", as_of=at("2024-01-02", 10, 0),
                        trigger="bar_close", mode="historical_replay",
                        input_batch_ids=("b1", "b1"))


# ------------------------------------------------- the five producer times


def test_a_vintage_available_after_the_cutoff_is_withheld():
    """Withheld, and the previous eligible vintage carries forward.

    Not an absence: a pillar that is a few minutes behind is still a pillar.
    D4's saturating noise is what makes carrying it forward honest, and the
    diagnostics name the vintage that was held back.
    """
    svc = service()
    seeded(svc)
    late = Vintage(producer="rmt", input_end=at("2024-01-02", 9, 50).isoformat(),
                   emission_available_at=at("2024-01-02", 11, 0).isoformat(),
                   value=0.5)
    out = svc.process(request(1, "2024-01-02", 10, 0), vintages=[late])
    rmt = out.pillar_diagnostics["rmt"]
    assert rmt["withheld"]["input_end"] == late.input_end
    assert rmt["vintage"]["input_end"] != late.input_end, (
        "the not-yet-available vintage must not be the one in force")
    assert rmt["carried_forward"] is True
    assert any("after this decision" in w for w in out.warnings)


def test_a_withheld_vintage_with_no_predecessor_is_a_transient_absence():
    """With nothing to carry forward, the honest answer is 'not yet'."""
    svc = service()
    late = Vintage(producer="rmt", input_end=at("2024-01-02", 9, 50).isoformat(),
                   emission_available_at=at("2024-01-02", 11, 0).isoformat(),
                   value=0.5)
    out = svc.process(request(1, "2024-01-02", 10, 0), vintages=[late])
    rmt = out.pillar_diagnostics["rmt"]
    assert rmt["eligible"] is False
    assert rmt["absence"] == "transient"
    # A pillar never yet observed is not in the mask — there is nothing to
    # weight. The D2 rule that transience keeps a pillar in the mask applies
    # once it HAS been observed, which the next test covers.
    assert out.reconciled_state.mask[1] is False


def test_a_transient_absence_after_an_observation_stays_in_the_mask():
    svc = service()
    seeded(svc)
    svc.process(request(1, "2024-01-02", 10, 0),
                vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    out = svc.process(request(2, "2024-01-03", 10, 0), vintages=[
        Vintage(producer="rmt", input_end=at("2024-01-03", 9, 50).isoformat(),
                emission_available_at=at("2024-01-03", 9, 50).isoformat(),
                absence="transient", absence_reason="estimation_failed")])
    assert out.pillar_diagnostics["rmt"]["absence"] == "transient"
    assert out.reconciled_state.mask[1] is True, (
        "transient absence keeps the pillar in the mask; D4 inflates its age")


def test_a_bundle_deployed_tomorrow_is_not_available_today():
    """Trained through yesterday is not the same as usable today."""
    registry = DeploymentRegistry([ModelBundle(
        bundle_id="b-tomorrow", producer="rmt",
        trained_through="2024-01-01",
        available_at=at("2024-01-03", 9, 15).isoformat())])
    svc = service(deployments=registry)
    out = svc.process(
        request(1, "2024-01-02", 10, 0),
        vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5,
                          bundle_id="b-tomorrow")])
    assert out.pillar_diagnostics["rmt"]["eligible"] is False
    assert any("becomes available at" in w for w in out.warnings)


def test_an_unregistered_bundle_is_refused_not_assumed_fine():
    svc = service()
    out = svc.process(
        request(1, "2024-01-02", 10, 0),
        vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5, bundle_id="ghost")])
    assert out.pillar_diagnostics["rmt"]["eligible"] is False
    assert any("not registered" in w for w in out.warnings)


def test_a_deployed_bundle_is_used():
    registry = DeploymentRegistry([ModelBundle(
        bundle_id="b-live", producer="rmt", trained_through="2023-12-29",
        available_at=at("2024-01-01", 9, 0).isoformat())])
    svc = service(deployments=registry)
    seeded(svc)
    out = svc.process(
        request(1, "2024-01-02", 10, 0),
        vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5, bundle_id="b-live")])
    assert out.pillar_diagnostics["rmt"]["eligible"] is True


def test_a_bundle_id_is_immutable():
    registry = DeploymentRegistry()
    registry.register(ModelBundle("b", "rmt", "2024-01-01", "2024-01-02"))
    registry.register(ModelBundle("b", "rmt", "2024-01-01", "2024-01-02"))
    with pytest.raises(InferenceError, match="immutable"):
        registry.register(ModelBundle("b", "rmt", "2024-01-01", "2024-01-03"))


def test_the_five_times_are_stored_separately():
    v = Vintage(producer="rmt", input_end="2024-01-02T09:50:00+05:30",
                emission_available_at="2024-01-02T10:05:00+05:30",
                fit_train_end="2024-01-01T15:30:00+05:30",
                fit_completed_at="2024-01-02T02:00:00+05:30",
                fit_deployed_at="2024-01-02T08:00:00+05:30", value=0.5)
    described = v.describe()
    assert len({described["input_end"], described["emission_available_at"],
                described["fit_train_end"], described["fit_completed_at"],
                described["fit_deployed_at"]}) == 5


# ------------------------------------------- assimilate each vintage once


def test_polling_the_same_vintage_appends_one_ecdf_observation():
    """The exact failure mode of calling a date-keyed step() intraday."""
    svc = service()
    seeded(svc)
    v = vintage("rmt", "2024-01-02", 9, 50, 0.5)
    before = svc.standardizer.observations("rmt")
    for i, minute in enumerate((0, 5, 10, 15, 20), start=1):
        svc.process(request(i, "2024-01-02", 10, minute), vintages=[v])
    assert svc.standardizer.observations("rmt") == before + 1


def test_a_genuinely_new_vintage_does_append():
    svc = service()
    seeded(svc)
    before = svc.standardizer.observations("rmt")
    svc.process(request(1, "2024-01-02", 10, 0),
                vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    svc.process(request(2, "2024-01-03", 10, 0),
                vintages=[vintage("rmt", "2024-01-03", 9, 50, 0.52)])
    assert svc.standardizer.observations("rmt") == before + 2


def test_the_diagnostics_say_whether_a_tick_assimilated_anything():
    svc = service()
    seeded(svc)
    v = vintage("rmt", "2024-01-02", 9, 50, 0.5)
    first = svc.process(request(1, "2024-01-02", 10, 0), vintages=[v])
    second = svc.process(request(2, "2024-01-02", 10, 5), vintages=[v])
    assert first.pillar_diagnostics["rmt"]["assimilated"] is True
    assert second.pillar_diagnostics["rmt"]["assimilated"] is False
    assert second.pillar_diagnostics["rmt"]["eligible"] is True


def test_the_standardizer_policy_id_travels_on_the_request():
    req = request(1, "2024-01-02", 10, 0)
    assert req.standardizer_policy_id == StandardizerHistory.policy_id
    assert "ecdf_5y" in req.standardizer_policy_id


def test_history_assimilates_a_vintage_key_once():
    history = StandardizerHistory()
    v = Vintage(producer="rmt", input_end="2024-01-02T09:50:00+05:30",
                emission_available_at="2024-01-02T09:50:00+05:30", value=0.5)
    assert history.assimilate(v) is True
    assert history.assimilate(v) is False
    assert history.observations("rmt") == 1


# ------------------------------------------------------- cadence and ageing


def test_the_declared_cadence_is_per_producer():
    assert DECLARED_CADENCE["hawkes"] == "bar_close"
    assert DECLARED_CADENCE["rmt"] == "daily"
    assert DECLARED_CADENCE["hamilton"] == "daily"


def test_a_daily_pillar_carried_through_the_day_ages():
    """Its value is reused; its staleness is not reset."""
    svc = service()
    seeded(svc)
    daily = vintage("rmt", "2024-01-02", 9, 50, 0.5)
    first = svc.process(request(1, "2024-01-02", 10, 0), vintages=[daily])
    later = svc.process(request(2, "2024-01-02", 15, 25), vintages=[daily])
    i = ("hawkes", "rmt", "hamilton").index("rmt")
    assert first.reconciled_state.tau_last_update[i] == \
        later.reconciled_state.tau_last_update[i], "same vintage, same tau"
    assert later.reconciled_state.P[i][i] >= first.reconciled_state.P[i][i], (
        "a carried-forward pillar must not become more certain with time")


def test_a_structural_absence_is_declared_never_inferred():
    with pytest.raises(InferenceError, match="never inferred"):
        Vintage(producer="hawkes", input_end="2024-01-02T09:50:00+05:30",
                emission_available_at="2024-01-02T09:50:00+05:30")


def test_a_structural_absence_leaves_the_mask():
    svc = service()
    seeded(svc)
    out = svc.process(request(1, "2024-01-02", 10, 0), vintages=[
        Vintage(producer="hawkes", input_end=at("2024-01-02", 9, 50).isoformat(),
                emission_available_at=at("2024-01-02", 9, 50).isoformat(),
                absence="structural", absence_reason="insufficient_history"),
        vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    assert out.pillar_diagnostics["hawkes"]["absence"] == "structural"
    assert out.reconciled_state.mask[0] is False


def test_an_unknown_producer_is_refused():
    with pytest.raises(InferenceError, match="unknown producer"):
        Vintage(producer="astra", input_end="2024-01-02T09:50:00+05:30",
                emission_available_at="2024-01-02T09:50:00+05:30", value=0.5)


# ----------------------------------------------------- the process clock


def test_a_day_of_bar_predictions_equals_one_daily_prediction():
    """The plan's required numerical check, on the clock C8 already uses.

    Open trading time is additive, so partitioning a session into bar-by-bar
    predictions must accumulate exactly the total of one prediction across the
    whole session. If it did not, a five-minute cadence would inject a full
    day's process noise seventy-five times.
    """
    dates = [datetime.fromisoformat(d).date() for d in SESSIONS]
    one = KalmanReconciler(session_dates=dates, q_proc=1e-3)
    many = KalmanReconciler(session_dates=dates, q_proc=1e-3)

    start, end = at("2024-01-02", 9, 15), at("2024-01-02", 15, 30)
    one.predict(start.isoformat())
    one.predict(end.isoformat())

    many.predict(start.isoformat())
    t = start
    while t < end:
        t = min(t + timedelta(minutes=5), end)
        many.predict(t.isoformat())

    a = np.array(one.state_at(end.isoformat()).value.P)
    b = np.array(many.state_at(end.isoformat()).value.P)
    assert np.allclose(a, b, atol=1e-12), (
        "partitioning a session changed the total process covariance")


def test_a_split_session_break_adds_no_trading_time():
    from datetime import time as _time
    day = datetime.fromisoformat("2024-01-02").date()
    clock = ReconciliationClock(
        session_dates=frozenset([day]),
        session_hours={day: ((_time(9, 15), _time(11, 0)),
                             (_time(13, 0), _time(15, 30)))})
    whole = clock.elapsed_bars(at("2024-01-02", 9, 15), at("2024-01-02", 15, 30))
    windows = (105 + 150) * 60 / 300.0
    assert whole == pytest.approx(windows)


def test_sessions_elapsed_is_the_plans_u_of_t():
    clock = ReconciliationClock(
        session_dates=frozenset(datetime.fromisoformat(d).date()
                                for d in SESSIONS))
    full = sessions_elapsed(clock, at("2024-01-02", 9, 15),
                            at("2024-01-02", 15, 30))
    half = sessions_elapsed(clock, at("2024-01-02", 9, 15),
                            at("2024-01-02", 12, 22))
    assert full == pytest.approx(1.0)
    assert 0.4 < half < 0.6
    assert BARS_PER_REGULAR_SESSION == 75.0


def test_overnight_adds_no_process_noise_beyond_trading_time():
    clock = ReconciliationClock(
        session_dates=frozenset(datetime.fromisoformat(d).date()
                                for d in SESSIONS))
    overnight = sessions_elapsed(clock, at("2024-01-02", 15, 30),
                                 at("2024-01-03", 9, 15))
    assert overnight == pytest.approx(0.0)


# ------------------------------------------------------ snapshot / restore


def test_a_restored_service_continues_identically():
    svc = service()
    seeded(svc)
    svc.process(request(1, "2024-01-02", 10, 0),
                vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    snap = svc.snapshot()
    nxt = vintage("hawkes", "2024-01-02", 10, 5, 0.12)
    expected = svc.process(request(2, "2024-01-02", 10, 5), vintages=[nxt])

    resumed = service()
    resumed.restore(snap)
    actual = resumed.process(request(2, "2024-01-02", 10, 5), vintages=[nxt])
    assert actual.csrs.model_dump() == expected.csrs.model_dump()
    assert actual.reconciled_state.model_dump() == \
        expected.reconciled_state.model_dump()


def test_restore_refuses_a_different_calendar():
    svc = service()
    seeded(svc)
    svc.process(request(1, "2024-01-02", 10, 0))
    snap = svc.snapshot()
    other = InferenceService(session_dates=SESSIONS[:-1])
    with pytest.raises(InferenceError, match="different session calendar"):
        other.restore(snap)


def test_restore_refuses_a_different_pipeline_version():
    from dataclasses import replace as _replace
    svc = service()
    seeded(svc)
    snap = _replace(svc.snapshot(), pipeline_version="something.else/1")
    with pytest.raises(InferenceError, match="rebuild by warm start"):
        service().restore(snap)


def test_a_snapshot_is_plain_data_not_a_pickle():
    import json
    svc = service()
    seeded(svc)
    svc.process(request(1, "2024-01-02", 10, 0),
                vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    snap = svc.snapshot()
    json.dumps(dict(filter_state=snap.filter_state,
                    standardizer=snap.standardizer, vintages=snap.vintages))


def test_the_state_id_changes_when_the_state_does():
    svc = service()
    seeded(svc)
    a = svc.process(request(1, "2024-01-02", 10, 0),
                    vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    b = svc.process(request(2, "2024-01-02", 10, 5),
                    vintages=[vintage("hawkes", "2024-01-02", 10, 5, 0.12)])
    assert a.state_after_id != b.state_after_id


# -------------------------------------------------------------- warm start


def test_warm_start_ignores_anything_available_at_or_after_the_cutoff():
    svc = service()
    cutoff = at("2024-01-02", 9, 15)
    svc.warm_start([
        Vintage(producer="rmt", input_end=at("2024-01-01", 9, 50).isoformat(),
                emission_available_at=at("2024-01-01", 9, 50).isoformat(),
                value=0.4),
        Vintage(producer="rmt", input_end=at("2024-01-02", 9, 50).isoformat(),
                emission_available_at=at("2024-01-02", 10, 0).isoformat(),
                value=0.6),
    ], cutoff=cutoff)
    assert svc.standardizer.observations("rmt") == 1


def test_warm_start_after_a_decision_is_refused():
    svc = service()
    seeded(svc)
    svc.process(request(1, "2024-01-02", 10, 0))
    with pytest.raises(InferenceError, match="restore"):
        svc.warm_start([], cutoff=at("2024-01-03", 9, 15))


def test_warmup_gates_publication_until_every_pillar_has_history():
    svc = service(warmup_observations=5)
    assert svc.warmup_complete is False
    seeded(svc)
    assert svc.warmup_complete is True


# ------------------------------------------------------------- publication


def test_a_replay_decision_is_never_publishable_as_current():
    svc = service()
    seeded(svc)
    out = svc.process(request(1, "2024-01-02", 10, 0),
                      vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    assert out.publication.current_allowed is False
    assert "not_live_mode" in out.publication.reasons


def test_a_live_decision_still_needs_a_verified_connected_feed():
    svc = service()
    seeded(svc)
    out = svc.process(
        request(1, "2024-01-02", 10, 0, mode="live_shadow"),
        vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)],
        feed=FeedProvenance(registered=True, authenticated=True,
                            connected=False, source_kind="kite_ticker"),
        now=at("2024-01-02", 10, 0))
    assert out.publication.current_allowed is False
    assert "feed_disconnected" in out.publication.reasons


def test_diagnostics_survive_a_refused_publication():
    svc = service()
    seeded(svc)
    out = svc.process(request(1, "2024-01-02", 10, 0),
                      vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    assert out.publication.current_allowed is False
    assert out.pillar_diagnostics["rmt"]["rank"] is not None
    assert out.reconciled_state is not None


def test_input_provenance_is_recorded_per_pillar():
    svc = service()
    seeded(svc)
    out = svc.process(request(1, "2024-01-02", 10, 0),
                      vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    names = {p["name"] for p in out.input_provenance}
    assert names == {"hawkes", "rmt", "hamilton"}
    rmt = next(p for p in out.input_provenance if p["name"] == "rmt")
    assert rmt["observed_at"] and rmt["received_at"]


def test_the_result_describes_itself_as_json_shaped_data():
    import json
    svc = service()
    seeded(svc)
    out = svc.process(request(1, "2024-01-02", 10, 0),
                      vintages=[vintage("rmt", "2024-01-02", 9, 50, 0.5)])
    json.dumps(out.describe())
