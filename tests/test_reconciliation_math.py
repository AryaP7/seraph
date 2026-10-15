"""Analytic C8 regression checks for the experimental math amendment.

These tests check information and time accounting, not historical performance.
"""
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from seraph.reconciliation.kalman import KalmanReconciler
from seraph.reconciliation.noise_model import SaturatingNoise
from seraph.reconciliation.time_clock import ReconciliationClock
from seraph.shared_types import (
    IST, ObservedEmission, PillarObservation, UnavailableEmission, ist_timestamp,
)

START = datetime(2020, 3, 2, 9, 15, tzinfo=IST)


def observed(pillar, when=START, *, tau=None, value=0.8, variance=0.02):
    return ObservedEmission(obs=PillarObservation(
        pillar=pillar, ts=ist_timestamp(when), tau=ist_timestamp(tau or when),
        value=value, estimation_variance=variance,
    ))


def absent(pillar, when=START, *, absence="transient"):
    return UnavailableEmission(
        pillar=pillar, ts=ist_timestamp(when), absence=absence,
        reason="estimation_failed" if absence == "transient" else "no_data_coverage",
    )


def state(result):
    assert result.status == "ok"
    return result.value


@pytest.mark.parametrize("absence", ["structural", "transient"])
def test_no_measurement_has_exact_random_walk_covariance(absence):
    rec = KalmanReconciler(q_proc=0.003, p0=0.2)
    before = state(rec.update([observed("rmt")]))
    later = START + timedelta(minutes=10)
    after = state(rec.update([absent("hawkes", later, absence=absence)]))
    np.testing.assert_allclose(after.P, np.asarray(before.P) + 2 * 0.003 * np.eye(3),
                               rtol=0, atol=1e-15)
    np.testing.assert_array_equal(after.x_hat, before.x_hat)
    assert not after.mask[0]  # a failed first observation is not information


def test_unmentioned_pillars_do_not_receive_virtual_measurements():
    rec = KalmanReconciler(q_proc=0, p0=0.3)
    out = state(rec.update([observed("rmt")]))
    assert out.P[0][0] == out.P[2][2] == 0.3
    assert out.P[1][1] == pytest.approx(1 / (1 / 0.3 + 1 / 0.02))


def test_genuine_observation_matches_scalar_bayes_and_recovers_missing_pillar():
    rec = KalmanReconciler(q_proc=0.001, p0=0.2, x0=(0.5, 0.5, 0.5))
    state(rec.update([absent("hawkes", absence="structural")]))
    later = START + timedelta(minutes=10)
    pred = state(rec.predict(ist_timestamp(later)))
    updated = state(rec.update([observed("hawkes", later, value=0.9, variance=0.02)]))
    prior = pred.P[0][0]
    expected_variance = prior * 0.02 / (prior + 0.02)
    expected_mean = 0.5 + prior / (prior + 0.02) * (0.9 - 0.5)
    assert updated.P[0][0] == pytest.approx(expected_variance)
    assert updated.x_hat[0] == pytest.approx(expected_mean)
    assert updated.mask[0]
    assert updated.P[1][1] == pred.P[1][1]


def test_repeated_vintage_does_not_reassimilate_even_if_value_changed():
    rec = KalmanReconciler(q_proc=0.003, p0=0.2)
    original = state(rec.update([observed("hawkes")]))
    later = START + timedelta(minutes=5)
    output = rec.update([observed("hawkes", later, tau=START, value=0.1)])
    duplicate = state(output)
    np.testing.assert_allclose(duplicate.P, np.asarray(original.P) + 0.003 * np.eye(3))
    assert duplicate.x_hat == original.x_hat
    assert duplicate.tau_last_update == original.tau_last_update
    assert [w.code for w in output.warnings] == ["STALE_OBSERVATION"]
    same_tick = state(rec.update([observed("hawkes", later, tau=START)]))
    assert same_tick == duplicate


def test_older_vintage_does_not_reassimilate():
    later = START + timedelta(minutes=10)
    rec = KalmanReconciler()
    initial = state(rec.update([observed("hamilton", later)]))
    repeated = state(rec.update([observed("hamilton", later, tau=START)]))
    assert repeated == initial


def test_repeated_observation_cannot_keep_saturated_signal_available():
    rec = KalmanReconciler(q_proc=0.003)
    initial = state(rec.update([observed("hawkes")]))
    later = START + timedelta(minutes=30)
    repeated = state(rec.update([observed("hawkes", later, tau=START)]))
    assert not repeated.mask[0] and repeated.noise_saturated[0]
    assert repeated.x_hat == initial.x_hat
    assert repeated.P[0][0] == pytest.approx(initial.P[0][0] + 6 * 0.003)


def test_saturated_observation_excluded_without_contracting_covariance():
    rec = KalmanReconciler(q_proc=0, p0=0.2)
    before = state(rec.predict(ist_timestamp(START)))
    later = START + timedelta(minutes=30)
    output = rec.update([observed("hawkes", later, tau=START)])
    after = state(output)
    assert after.P == before.P and after.x_hat == before.x_hat
    assert not after.mask[0]
    assert after.tau_last_update[0] is None
    assert [w.code for w in output.warnings] == ["NOISE_SATURATED"]


def test_transient_failure_preserves_previously_seen_pillar():
    rec = KalmanReconciler(q_proc=0.003)
    before = state(rec.update([observed("hawkes")]))
    later = START + timedelta(minutes=5)
    after = state(rec.update([absent("hawkes", later)]))
    assert after.mask[0] and after.P[0][0] > before.P[0][0]


@pytest.mark.parametrize("bad", ["2020-03-02T09:15:00", "2020-03-02T03:45:00+00:00",
                                 "2020-03-99T09:15:00+05:30"])
def test_predict_rejects_noncanonical_timestamp_without_mutation(bad):
    rec = KalmanReconciler()
    before = state(rec.predict(ist_timestamp(START)))
    assert rec.predict(bad).status == "error"
    assert state(rec.state_at(ist_timestamp(START))) == before


def test_invalid_batch_is_atomic():
    rec = KalmanReconciler()
    before = state(rec.predict(ist_timestamp(START)))
    later = START + timedelta(minutes=10)
    invalid = observed("rmt", later, value=float("nan"))
    assert rec.update([observed("hawkes", later), invalid]).status == "error"
    assert state(rec.state_at(ist_timestamp(START))) == before
    assert rec.update([observed("hawkes", later), observed("hawkes", later)]).status == "error"
    assert state(rec.state_at(ist_timestamp(START))) == before


def test_trading_clock_excludes_weekend_and_overnight():
    friday_close = datetime(2020, 3, 6, 15, 30, tzinfo=IST)
    monday_open = datetime(2020, 3, 9, 9, 15, tzinfo=IST)
    clock = ReconciliationClock()
    assert clock.elapsed_bars(friday_close, monday_open) == 0
    assert clock.elapsed_bars(friday_close, monday_open + timedelta(minutes=5)) == 1
    assert clock.elapsed_bars(START, START + timedelta(days=1)) == 75


def test_supplied_sessions_handle_holiday_and_special_weekend():
    # Synthetic explicit session list: Tuesday excluded; Saturday included.
    clock = ReconciliationClock(session_dates=frozenset({date(2020, 3, 2), date(2020, 3, 7)}))
    assert clock.elapsed_bars(START, START + timedelta(days=6)) == 150
    rec = KalmanReconciler(q_proc=0.001, session_dates=[date(2020, 3, 2)])
    before = state(rec.predict(ist_timestamp(START)))
    after = state(rec.predict(ist_timestamp(START + timedelta(days=2))))
    assert after.P[0][0] - before.P[0][0] == pytest.approx(0.075)


def test_calendar_clock_is_explicit_opt_in():
    rec = KalmanReconciler(time_basis="calendar", q_proc=0.001)
    before = state(rec.predict(ist_timestamp(START)))
    after = state(rec.predict(ist_timestamp(START + timedelta(days=1))))
    assert after.P[0][0] - before.P[0][0] == pytest.approx(288 * 0.001)
    with pytest.raises(ValueError, match="session_dates"):
        KalmanReconciler(time_basis="calendar", session_dates=[])


def test_forward_fill_baseline_carries_values_without_duplicate_updates():
    rec = KalmanReconciler(mode="forward_fill")
    before = state(rec.update([observed("hawkes", value=0.9)]))
    later = START + timedelta(minutes=5)
    after = state(rec.update([observed("hawkes", later, tau=START, value=0.1)]))
    assert after.x_hat == before.x_hat and after.P == before.P


def test_zero_variance_is_numerically_safe_and_constant_noise_is_not_stale():
    noise = SaturatingNoise(r_max_ratio=1)
    assert not noise.saturated(noise.r(100))
    rec = KalmanReconciler()
    out = state(rec.update([observed("hamilton", variance=0)]))
    assert out.mask[2] and 0 <= out.P[2][2] < 1e-9
