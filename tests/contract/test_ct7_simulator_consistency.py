# CT-7 — C11 ⇄ C9: simulator consistency (ARCHITECTURE §5 ⑨)
"""A zero-magnitude shock must reproduce the unperturbed CSRS series exactly.
If it does not, the simulator has forked the scoring logic instead of calling
C9's score() — which would let the "what if" view and the live view disagree,
the worst possible failure for a decision-support tool."""
from __future__ import annotations

import numpy as np
import pytest

from fixtures.mock_generator import (
    DEFAULT_START,
    mock_fusion_weights,
    mock_reconciled_state,
    mock_xi,
)
from seraph.decision_support import (
    explain,
    playbook,
    portfolio_overlay,
    simulate_policy,
    simulate_shock,
)
from seraph.fusion.score import score


def _fixture():
    rng = np.random.default_rng(11)
    return mock_reconciled_state(DEFAULT_START, rng), mock_xi(rng), mock_fusion_weights(seed=11)


def test_ct7_zero_shock_reproduces_the_unperturbed_series_exactly():
    state, xi, w = _fixture()
    baseline = score(reconciled=state, xi=xi, weights=w)
    assert baseline.status == "ok"

    sim = simulate_shock(reconciled=state, xi=xi, weights=w,
                         pillar="rmt", magnitude=0.0, horizon_days=5)
    assert sim.status == "ok"
    for point in sim.value:
        assert point.model_dump_json() == baseline.value.model_dump_json(), (
            "a zero shock changed the answer — the simulator has forked score()"
        )


def test_ct7_positive_shock_raises_risk_and_decays():
    state, xi, w = _fixture()
    base = score(reconciled=state, xi=xi, weights=w).value
    sim = simulate_shock(reconciled=state, xi=xi, weights=w,
                         pillar="rmt", magnitude=0.5, horizon_days=4)
    assert sim.status == "ok"
    series = [p.csrs for p in sim.value]
    assert series[0] >= base.csrs
    assert all(a >= b - 1e-12 for a, b in zip(series, series[1:])), "shock must decay"


def test_ct7_negative_unknown_pillar_is_rejected():
    state, xi, w = _fixture()
    res = simulate_shock(reconciled=state, xi=xi, weights=w,
                         pillar="not_a_pillar", magnitude=0.1)
    assert res.status == "error" and res.error.kind == "CONTRACT_VIOLATION"


def test_fr44_explanation_never_attributes_to_a_masked_pillar():
    rng = np.random.default_rng(12)
    state = mock_reconciled_state(DEFAULT_START, rng, mask=(False, True, True))
    res = score(reconciled=state, xi=mock_xi(rng), weights=mock_fusion_weights(seed=12))
    assert res.status == "ok"
    out = explain(res.value)
    assert out.status == "ok"
    assert out.value["dominantPillar"] != "hawkes"
    assert "unavailable for this period" in out.value["sentence"]
    assert any(w.code == "MASK_DEGRADED" for w in out.warnings)


def test_fr43_portfolio_overlay_sizes_the_exposure():
    holdings = [
        {"symbol": "TATASTEEL", "value": 60000, "sector": "steel"},
        {"symbol": "SUNPHARMA", "value": 40000, "sector": "pharmaceuticals"},
    ]
    res = portfolio_overlay(holdings, {"steel": "amber"})
    assert res.status == "ok"
    assert res.value["exposedPct"] == pytest.approx(60.0)


def test_fr46_playbook_does_not_invent_a_drawdown_number():
    res = playbook("rmt")
    assert res.status == "ok"
    assert res.value["drawdownReductionPct"] is None, (
        "an uncalibrated magnitude must stay None, not a plausible-looking guess"
    )


def test_fr48_policy_path_routes_through_the_fitted_regime_model():
    """FR48 takes a z_t path, not a xi path. The z->xi mapping must come from
    C7's fitted TVTP transitions so the counterfactual and the live model
    cannot diverge."""
    from seraph.pillars.hamilton import HamiltonEngine, project_xi

    rng = np.random.default_rng(21)
    labels = np.concatenate([np.full(400, b) for b in (0, 2, 1, 0)])
    means = np.array([[0.8, 0.35, 0.10], [1.6, 0.55, 0.22], [3.2, 0.80, 0.45]])
    y = means[labels] + rng.normal(scale=[0.18, 0.05, 0.03], size=(labels.size, 3))
    base = np.datetime64("2005-01-03")
    dates = [str(base + np.timedelta64(int(i), "D")) for i in range(labels.size)]
    z = np.column_stack([np.ones(len(dates)), (labels == 2).astype(float)])

    eng = HamiltonEngine(dates, y, exog_tvtp=z)
    assert eng.fit().status == "ok"

    calm = project_xi(eng, np.array([[1.0, 0.0]] * 6))
    stressed = project_xi(eng, np.array([[1.0, 1.0]] * 6))
    for path in (calm, stressed):
        for row in path:
            assert sum(row) == pytest.approx(1.0, abs=1e-9)
            assert all(0.0 <= v <= 1.0 for v in row)
    assert calm != stressed, "a different policy path must yield different regimes"

    state, _, w = _fixture()
    res = simulate_policy(reconciled=state, weights=w,
                          z_path=np.array([[1.0, 1.0]] * 4),
                          xi_projector=lambda zp: project_xi(eng, zp))
    assert res.status == "ok" and len(res.value) == 4


def test_fr48_negative_missing_projector_is_rejected():
    state, _, w = _fixture()
    res = simulate_policy(reconciled=state, weights=w, z_path=[[1.0, 0.0]])
    assert res.status == "error" and res.error.kind == "CONTRACT_VIOLATION"
