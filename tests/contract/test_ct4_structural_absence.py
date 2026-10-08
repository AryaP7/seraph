# CT-4 — Pillars ⇄ C8: structural absence (ARCHITECTURE §5 ②)
"""This test IS Objective 6. Absence is R → ∞, never zero; the D2 mask
excludes structurally-absent pillars; on the first genuine emission the
covariance drops and the mask flips true.

Written before C8 exists (test-first, AGENTS.md §6). The C8 tests skip until
`seraph/reconciliation/kalman.py` lands with:

    class KalmanReconciler:
        def predict(self, to_ts: str) -> Result[ReconciledState]
        def update(self, emissions: Sequence[PillarEmission]) -> Result[ReconciledState]

The type-level negatives (tau > ts, transient vs structural shapes) run today
against shared_types + T0.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from fixtures.mock_generator import DEFAULT_START, BAR, mock_emission, mock_tick_stream
from seraph.shared_types import PillarObservation, ist_timestamp

N_ABSENT = 200


def _trace(state) -> float:
    return float(np.trace(np.asarray(state.P)))


def test_ct4_structural_absence_saturates_and_recovers():
    kalman = pytest.importorskip(
        "seraph.reconciliation.kalman", reason="C8 not built yet (L5)"
    )
    rec = kalman.KalmanReconciler()
    # Constant observation noise (no random Hamilton variance, no stale-tau
    # pattern) — with fluctuating R the observed pillars' variance wobbles and
    # full-trace monotonicity would not be a valid assertion.
    stream = mock_tick_stream(
        n_ticks=N_ABSENT, seed=7, hawkes_structural_ticks=N_ABSENT,
        stale_every=None, estimation_variance=0.02,
    )

    states = []
    for k, tick in enumerate(stream):
        ts = ist_timestamp(DEFAULT_START + k * BAR)
        pred = rec.predict(ts)
        assert pred.status == "ok"
        upd = rec.update(tick)
        assert upd.status == "ok"
        states.append(upd.value)

    # D2: structurally-absent pillar leaves the mask; never observed → no tau.
    assert all(s.mask[0] is False for s in states)
    assert all(s.tau_last_update[0] is None for s in states)
    # Other two pillars observe normally and stay in the mask.
    assert all(s.mask[1] and s.mask[2] for s in states)

    # xHat[0] must not collapse toward 0 — under a random-walk transition with
    # no observation, the prediction leaves the mean where it started.
    assert states[-1].x_hat[0] == pytest.approx(states[0].x_hat[0], abs=1e-6)

    # D4: trace(P) grows monotonically, then SATURATES (bounded R — never ∞).
    traces = [_trace(s) for s in states]
    assert all(b >= a - 1e-12 for a, b in zip(traces, traces[1:]))
    early_growth = traces[N_ABSENT // 4] - traces[0]
    late_growth = traces[-1] - traces[-N_ABSENT // 4]
    assert late_growth < 0.10 * max(early_growth, 1e-12), (
        "trace(P) must saturate under structural absence, not grow unbounded"
    )

    # First genuine Hawkes emission: P[0][0] drops strictly, mask flips true.
    p00_before = states[-1].P[0][0]
    ts_next = DEFAULT_START + N_ABSENT * BAR
    rng = np.random.default_rng(7)
    observed = mock_emission("hawkes", ts_next, rng)
    rec.predict(ist_timestamp(ts_next))
    after = rec.update([observed])
    assert after.status == "ok"
    assert after.value.mask[0] is True
    assert after.value.P[0][0] < p00_before
    assert after.value.tau_last_update[0] == observed.obs.tau


def test_ct4_transient_absence_keeps_pillar_in_mask():
    kalman = pytest.importorskip(
        "seraph.reconciliation.kalman", reason="C8 not built yet (L5)"
    )
    rec = kalman.KalmanReconciler()
    rng = np.random.default_rng(11)

    # One genuine observation first, then transient failures — the pillar
    # SHOULD exist, this update just failed: stays in the mask, noise inflates.
    ts0 = DEFAULT_START
    rec.predict(ist_timestamp(ts0))
    seeded = rec.update([mock_emission(p, ts0, rng) for p in ("hawkes", "rmt", "hamilton")])
    assert seeded.status == "ok" and all(seeded.value.mask)

    for k in range(1, 6):
        ts = DEFAULT_START + k * BAR
        rec.predict(ist_timestamp(ts))
        upd = rec.update([
            mock_emission("hawkes", ts, rng, absence="transient"),
            mock_emission("rmt", ts, rng),
            mock_emission("hamilton", ts, rng),
        ])
        assert upd.status == "ok"
        assert upd.value.mask[0] is True, (
            "transient absence must keep the pillar in the mask (D2); "
            "D4 age-inflation handles the staleness"
        )


# --- type-level negatives: runnable today, no C8 required -----------------


def test_ct4_negative_tau_after_ts_is_a_contract_violation():
    ts = ist_timestamp(DEFAULT_START)
    tau_late = ist_timestamp(DEFAULT_START + timedelta(minutes=5))
    with pytest.raises(ValidationError, match="CONTRACT_VIOLATION"):
        PillarObservation(pillar="hawkes", ts=ts, tau=tau_late, value=0.5)


def test_ct4_stream_shape_structural_then_observed():
    stream = mock_tick_stream(n_ticks=10, seed=1, hawkes_structural_ticks=4)
    hawkes = [tick[0] for tick in stream]
    assert all(e.kind == "unavailable" and e.absence == "structural" for e in hawkes[:4])
    assert all(e.kind == "observed" for e in hawkes[4:])
    # unavailable emissions are values inside Ok streams — they are never
    # exceptions, and never carry a magic zero.
    assert not any(hasattr(e, "value") for e in hawkes[:4])
