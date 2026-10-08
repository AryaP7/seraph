# CT-5 — C8 ⇄ C9: covariance propagation (ARCHITECTURE §5 ⑦)
"""Var(CSRS) must derive from the real P: scale P ×4 → csrs identical,
variance ×4, CI width ×2. Negative: non-PSD P → CONSTRAINT_VIOLATED.

Written before C9 exists. Skips until `seraph/fusion/score.py` lands with:

    def score(*, reconciled: ReconciledState, xi: Simplex3,
              weights: FusionWeights, xi_mode: str = "hamilton") -> Result[CsrsPoint]
"""
from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from fixtures.mock_generator import (
    DEFAULT_START,
    mock_fusion_weights,
    mock_reconciled_state,
    mock_xi,
)
from seraph.shared_types import ReconciledState, ist_timestamp


def _scaled(state: ReconciledState, factor: float) -> ReconciledState:
    p = tuple(tuple(x * factor for x in row) for row in state.P)
    return state.model_copy(update={"P": p})


def test_ct5_variance_tracks_p():
    fusion = pytest.importorskip("seraph.fusion.score", reason="C9 not built yet (L6)")
    rng = np.random.default_rng(3)
    state = mock_reconciled_state(DEFAULT_START, rng)
    state_x4 = _scaled(state, 4.0)
    xi = mock_xi(rng)
    weights = mock_fusion_weights(seed=3)

    a = fusion.score(reconciled=state, xi=xi, weights=weights)
    b = fusion.score(reconciled=state_x4, xi=xi, weights=weights)
    assert a.status == "ok" and b.status == "ok"

    assert b.value.csrs == pytest.approx(a.value.csrs, abs=1e-12), (
        "the point estimate must not depend on P"
    )
    assert b.value.variance == pytest.approx(4.0 * a.value.variance, rel=1e-9)
    width_a = a.value.ci_upper - a.value.ci_lower
    width_b = b.value.ci_upper - b.value.ci_lower
    assert width_b == pytest.approx(2.0 * width_a, rel=1e-6)


def test_ct5_negative_non_psd_p_is_rejected():
    # Enforced at the shared_types seam — no component can even construct it.
    with pytest.raises(ValidationError, match="CONSTRAINT_VIOLATED"):
        ReconciledState(
            ts=ist_timestamp(DEFAULT_START),
            x_hat=(0.1, 0.2, 0.3),
            P=((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),  # negative eigenvalue
            tau_last_update=(None, None, None),
            mask=(True, True, True),
            mode="kalman",
        )


def test_ct5_negative_asymmetric_p_is_rejected():
    with pytest.raises(ValidationError, match="CONSTRAINT_VIOLATED"):
        ReconciledState(
            ts=ist_timestamp(DEFAULT_START),
            x_hat=(0.1, 0.2, 0.3),
            P=((1.0, 0.5, 0.0), (0.1, 1.0, 0.0), (0.0, 0.0, 1.0)),  # P != Pᵀ
            tau_last_update=(None, None, None),
            mask=(True, True, True),
            mode="kalman",
        )
