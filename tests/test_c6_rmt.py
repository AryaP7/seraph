# C6 — RMT engine unit tests, including the AMENDMENT-04 regression guards.
"""Correctness of the correlation estimator underneath Pillar 2.

CT-10 covers the D3 rotation contract. What was missing — and what let the FR16
arithmetic defect reach a full corpus run undetected — is any test that the
matrix `C_t` is a correlation matrix at all.
"""
from __future__ import annotations

import numpy as np
import pytest

from seraph.pillars.rmt.engine import _correlation, compute_rmt, mp_bounds

# --- AMENDMENT-04 §2 regression guards ------------------------------------
# These lock in a measured defect. `_correlation` computed sd with ddof=1 but
# normalised the Gram matrix by T, putting exactly (T-1)/T on every diagonal
# entry. trace(C_t) was N_t (T-1)/T, so FR16's guard failed by exactly N_t/T —
# 0.499 at N_t=499, T=1000 — and every eigenvalue was shrunk by 0.999 while the
# MP edges, evaluated at sigma^2 = 1, were not.


@pytest.mark.parametrize("t_obs,n_sym", [(1000, 499), (1000, 122), (1000, 500),
                                         (400, 120), (250, 125)])
def test_amendment04_trace_equals_n_exactly(t_obs, n_sym):
    """FR16's arithmetic guard: a correlation matrix has unit diagonal.

    The failure mode this guards against is silent — the matrix stays symmetric
    and PSD, so nothing raises; only the trace reveals it. If this regresses,
    the reported N_t/T deficit is back and `Sigma lambda_i = N_t` is no longer an
    identity, which is what `V_t^eig`'s justification in the module docstring
    rests on.
    """
    rng = np.random.default_rng(0)
    c, degenerate = _correlation(rng.standard_normal((t_obs, n_sym)))
    assert not degenerate.any()
    assert np.allclose(np.diag(c), 1.0, atol=1e-12)
    assert abs(float(np.trace(c)) - n_sym) < 1e-9, (
        f"trace(C) - N = {float(np.trace(c)) - n_sym:.6f}; the ddof/divisor "
        f"mismatch produces exactly -N/T = {-n_sym / t_obs:.6f}"
    )


def test_amendment04_matches_numpy_corrcoef():
    """The estimator must agree with the canonical implementation.

    A self-consistent-but-wrong normalisation passes a unit-diagonal check on
    its own; agreeing with `np.corrcoef` pins the off-diagonals too.
    """
    rng = np.random.default_rng(7)
    # Correlated columns, so the off-diagonals are not all ~0 and the
    # comparison has something to bite on.
    factor = rng.standard_normal((300, 1))
    returns = factor @ rng.uniform(0.5, 1.5, size=(1, 40)) + rng.standard_normal((300, 40))
    c, _ = _correlation(returns)
    assert np.allclose(c, np.corrcoef(returns, rowvar=False), atol=1e-12)
    assert c.min() >= -1.0 - 1e-12 and c.max() <= 1.0 + 1e-12


def test_amendment04_constant_column_becomes_an_isolated_unit_mode():
    """A zero-variance column keeps the trace exact without inflating F_t.

    Its z-scores are identically zero, which would otherwise leave a zero on the
    diagonal and silently drop the symbol from the trace. The substitution gives
    it exactly one eigenvalue of 1.0, which lies strictly inside the MP band for
    every Q > 1 and therefore cannot be counted as an exceedance.
    """
    rng = np.random.default_rng(3)
    returns = rng.standard_normal((1000, 50))
    returns[:, 7] = 0.0                      # a suspended symbol: no variation
    c, degenerate = _correlation(returns)

    assert degenerate[7] and int(degenerate.sum()) == 1
    assert abs(float(np.trace(c)) - 50) < 1e-9
    assert np.allclose(np.delete(c[7], 7), 0.0, atol=1e-12), "must be isolated"

    eigenvalues = np.linalg.eigvalsh(c)
    lam_minus, lam_plus = mp_bounds(1000 / 50)
    assert lam_minus < 1.0 < lam_plus
    assert int(np.isclose(eigenvalues, 1.0, atol=1e-9).sum()) >= 1


def test_amendment04_degenerate_column_is_announced_not_absorbed():
    """The substitution is a modelling choice, so it must be visible in output."""
    rng = np.random.default_rng(4)
    returns = rng.standard_normal((600, 30))
    returns[:, 11] = 0.0
    res = compute_rmt(
        returns=returns,
        members=tuple(f"SYM{i:03d}" for i in range(30)),
        bootstrap_reps=0,
    )
    assert res.status == "ok"
    fallback = [w for w in res.warnings if w.code == "ESTIMATOR_FALLBACK"]
    assert fallback, [w.code for w in res.warnings]
    assert fallback[0].context["degenerateColumns"] == 1


def test_amendment04_eigenvalues_sum_to_n_so_the_variance_share_is_exact():
    """`lambda_1/N` is the statistic AMENDMENT-04 §6 puts forward for cross-date
    use, and its normalisation is only exact if the trace identity holds."""
    rng = np.random.default_rng(11)
    factor = rng.standard_normal((1000, 1))
    returns = factor @ rng.uniform(0.6, 1.0, size=(1, 200)) + rng.standard_normal((1000, 200))
    c, _ = _correlation(returns)
    eigenvalues = np.linalg.eigvalsh(c)
    assert abs(float(eigenvalues.sum()) - 200) < 1e-8
    share = float(eigenvalues[-1]) / 200
    assert 0.0 < share < 1.0
