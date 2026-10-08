# C7 — Hamilton Engine: recovery of known synthetic regimes (FR20, FR23, FR24)
"""Not a numbered contract test — ARCHITECTURE defines no CT for Pillar 3.
These check SPEC O4's acceptance conditions on data whose true regimes are
known by construction: ordered means, a non-degenerate three-regime solution,
a valid simplex every day, LSD_t in [0,3], and finite half-lives.
"""
from __future__ import annotations

import numpy as np
import pytest

from seraph.pillars.hamilton import HamiltonEngine

N_PER_REGIME = 400
# (rv, ar, bas) means per regime — tranquil, stressed, crisis.
TRUE_MEANS = np.array([[0.8, 0.35, 0.10], [1.6, 0.55, 0.22], [3.2, 0.80, 0.45]])
TRUE_SD = np.array([0.18, 0.05, 0.03])


def _synthetic(seed: int = 0):
    """Three persistent blocks: tranquil → crisis → stressed → tranquil."""
    rng = np.random.default_rng(seed)
    blocks = [0, 2, 1, 0]
    labels = np.concatenate([np.full(N_PER_REGIME, b) for b in blocks])
    y = TRUE_MEANS[labels] + rng.normal(scale=TRUE_SD, size=(labels.size, 3))
    base = np.datetime64("2005-01-03")
    dates = [str(base + np.timedelta64(int(i), "D")) for i in range(labels.size)]
    return dates, y, labels


def test_c7_recovers_ordered_regimes():
    dates, y, labels = _synthetic()
    eng = HamiltonEngine(dates, y)
    res = eng.fit()
    assert res.status == "ok", res

    # O4: non-degenerate, ordered means. `order` maps sorted → fitted index and
    # must be a genuine permutation of all three regimes.
    assert sorted(res.value["order"]) == [0, 1, 2]
    assert np.isfinite(res.value["llf"])


def test_c7_regime_probabilities_are_a_valid_simplex_every_day():
    dates, y, _ = _synthetic()
    eng = HamiltonEngine(dates, y)
    assert eng.fit().status == "ok"
    for d in dates[::37]:
        detail = eng.detail(d)
        assert detail is not None
        assert sum(detail.xi) == pytest.approx(1.0, abs=1e-9)
        assert all(0.0 <= v <= 1.0 for v in detail.xi)


def test_c7_identifies_the_crisis_block():
    """The middle block is the true crisis regime; its posterior crisis
    probability must dominate its tranquil probability there, and not elsewhere."""
    dates, y, labels = _synthetic()
    eng = HamiltonEngine(dates, y)
    assert eng.fit().status == "ok"

    crisis_idx = np.where(labels == 2)[0]
    tranquil_idx = np.where(labels == 0)[0]
    xi_crisis = np.array([eng.detail(dates[i]).xi[2] for i in crisis_idx[::10]])
    xi_tranquil = np.array([eng.detail(dates[i]).xi[2] for i in tranquil_idx[::10]])
    assert xi_crisis.mean() > 0.80, "crisis regime should be confidently detected"
    assert xi_tranquil.mean() < 0.20, "tranquil days must not read as crisis"


def test_c7_emits_lsd_in_range_with_uncertainty():
    dates, y, _ = _synthetic()
    eng = HamiltonEngine(dates, y)
    assert eng.fit().status == "ok"

    res = eng.emit(dates[500])
    assert res.status == "ok"
    em = res.value
    assert em.kind == "observed"
    assert 0.0 <= em.obs.value <= 3.0, "LSD_t = xi_2 + 2*xi_3 lives in [0,3]"
    assert em.obs.estimation_variance is not None and em.obs.estimation_variance >= 0
    assert em.obs.tau <= em.obs.ts


def test_c7_half_lives_are_positive_and_finite():
    dates, y, _ = _synthetic()
    eng = HamiltonEngine(dates, y)
    assert eng.fit().status == "ok"
    detail = eng.detail(dates[500])
    assert 0.0 < detail.p_hat_22 < 1.0
    assert 0.0 < detail.p_hat_33 < 1.0
    assert detail.tau_half_stressed > 0 and np.isfinite(detail.tau_half_stressed)
    assert detail.tau_half_crisis > 0 and np.isfinite(detail.tau_half_crisis)


def test_c7_date_outside_sample_is_structural_absence_not_error():
    dates, y, _ = _synthetic()
    eng = HamiltonEngine(dates, y)
    assert eng.fit().status == "ok"
    res = eng.emit("1999-01-01")
    assert res.status == "ok", "absence is a value, never an Err"
    assert res.value.kind == "unavailable"
    assert res.value.absence == "structural"


def test_c7_too_short_a_sample_is_insufficient_history():
    dates, y, _ = _synthetic()
    eng = HamiltonEngine(dates[:50], y[:50])
    res = eng.fit()
    assert res.status == "error"
    assert res.error.kind == "INSUFFICIENT_HISTORY"


def test_c7_tvtp_covariates_are_accepted():
    """FR21 — transition probabilities vary with z_t. With a covariate the
    transition matrix must actually be time-varying."""
    dates, y, labels = _synthetic()
    # index 0 sits in a tranquil block (z=[1,0]); index 500 in the crisis block (z=[1,1])
    z = np.column_stack([np.ones(len(dates)), (labels == 2).astype(float)])
    eng = HamiltonEngine(dates, y, exog_tvtp=z)
    assert eng.fit().status == "ok"
    trans = np.asarray(eng._res.model.regime_transition_matrix(eng._res.params))
    assert trans.shape[2] == len(dates), "TVTP must give one matrix per date"
    assert not np.allclose(trans[:, :, 0], trans[:, :, 500]), (
        "transition probabilities should respond to z_t"
    )
