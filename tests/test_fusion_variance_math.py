"""C9 variance must match the one shared uncertain pillar vector."""
import numpy as np
import pytest

from fixtures.mock_generator import DEFAULT_START, mock_fusion_weights, mock_reconciled_state
from seraph.fusion.score import score


def inputs(rows, mask=(True, True, True)):
    weights = mock_fusion_weights(seed=14).model_copy(update={"w": rows})
    p = ((0.04, 0.015, -0.005), (0.015, 0.03, 0.002), (-0.005, 0.002, 0.02))
    state = mock_reconciled_state(DEFAULT_START, np.random.default_rng(12)).model_copy(
        update={"P": p, "mask": mask, "x_hat": (0.2, 0.4, 0.6)}
    )
    return weights, state


def test_identical_regime_weights_preserve_same_variance_for_any_xi():
    w = (0.2, 0.3, 0.5)
    weights, state = inputs((w, w, w))
    expected = float(np.asarray(w) @ np.asarray(state.P) @ np.asarray(w))
    outputs = [score(reconciled=state, weights=weights, xi=xi).value
               for xi in [(1 / 3, 1 / 3, 1 / 3), (1.0, 0.0, 0.0), (0.2, 0.3, 0.5)]]
    for out in outputs:
        assert out.variance == pytest.approx(expected)
    # Old formula gave expected/3 for uniform xi even though score was identical.
    assert outputs[0].variance == pytest.approx(outputs[1].variance)


def test_cross_regime_covariance_matches_linear_transform_and_monte_carlo():
    rows = ((0.7, 0.2, 0.1), (0.1, 0.7, 0.2), (0.1, 0.1, 0.8))
    weights, state = inputs(rows)
    xi = np.asarray((0.2, 0.5, 0.3))
    a = xi @ np.asarray(rows)
    expected = a @ np.asarray(state.P) @ a
    out = score(reconciled=state, weights=weights, xi=tuple(xi)).value
    assert out.variance == pytest.approx(expected, abs=1e-14)
    # Draw latent estimation errors: uncertainty here is linear/local, not a
    # distribution of the clipped score or a random regime-mixture score.
    errors = np.random.default_rng(43).multivariate_normal(np.zeros(3), state.P, size=120000)
    simulated = (errors @ np.asarray(rows).T) @ xi
    assert np.var(simulated) == pytest.approx(out.variance, rel=0.02)


def test_masked_prior_covariance_cannot_affect_composite_variance():
    rows = ((0.7, 0.2, 0.1), (0.1, 0.7, 0.2), (0.1, 0.1, 0.8))
    weights, state = inputs(rows, mask=(False, True, True))
    inflated = np.asarray(state.P).copy()
    inflated[0, 0] = 1e8
    state2 = state.model_copy(update={"P": tuple(tuple(row) for row in inflated)})
    first = score(reconciled=state, weights=weights, xi=(0.2, 0.5, 0.3)).value
    second = score(reconciled=state2, weights=weights, xi=(0.2, 0.5, 0.3)).value
    assert second.variance == first.variance
    assert second.csrs == first.csrs
