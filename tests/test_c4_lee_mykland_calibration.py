# C4 — Feature Deriver (FR50): normalization and causal multiplicity regressions.
"""Experimental copy repairs the formerly xfailed normalization defect.

The published helper keeps its original convention by default. Actual
extraction uses corrected-sigma constants and a preset test family. Historical
database counts and AMENDMENT-03 estimates are not thereby regenerated.
"""
from __future__ import annotations

import numpy as np
import pytest

from seraph.features.jump_extraction import (
    LM_ALPHA,
    LM_TEST_BLOCK_SIZE,
    LM_WINDOW_K,
    _C_CONST,
    bipower_volatility,
    extract_jumps,
    lee_mykland_threshold,
)


def _extreme_value_constants(n_obs: int) -> tuple[float, float]:
    """Constants for the maximum of n independent absolute N(0,1) variates."""
    log_n = np.log(n_obs)
    root = np.sqrt(2.0 * log_n)
    return float(root - (np.log(log_n) + np.log(np.pi)) / (2.0 * root)), float(1.0 / root)


def test_bipower_volatility_estimates_sigma_not_mu1_times_sigma():
    rng = np.random.default_rng(20261013)
    sigma = .0012
    sig = bipower_volatility(rng.normal(0.0, sigma, size=60_000), LM_WINDOW_K)
    sig = sig[np.isfinite(sig)]
    assert sig.size > 50_000
    assert float(sig.mean() / sigma) == pytest.approx(1.0, abs=.02)


def test_lee_mykland_threshold_is_the_published_cn_sn_form():
    """Existing callers still receive the published uncorrected-sigma value."""
    for n in (75, 500, 2_319, 18_781_302):
        a_n, b_n = _extreme_value_constants(n)
        beta_star = -np.log(-np.log(1.0 - LM_ALPHA))
        published = (a_n + b_n * beta_star) / _C_CONST
        assert lee_mykland_threshold(n, LM_ALPHA) == pytest.approx(published, rel=1e-12)


def test_standardized_threshold_matches_the_actual_statistic_units():
    for n in (75, 500, 2_319, 18_781_302):
        a_n, b_n = _extreme_value_constants(n)
        beta_star = -np.log(-np.log(1.0 - LM_ALPHA))
        assert lee_mykland_threshold(n, LM_ALPHA, standardized=True) == pytest.approx(
            a_n + b_n * beta_star, rel=1e-12)


def test_extract_jumps_uses_the_corrected_threshold_on_actual_prices():
    """A jump between the two critical values catches a helper-only repair."""
    n = LM_WINDOW_K + 40
    returns = .001 * np.where(np.arange(n) % 2, 1., -1.)
    returns[0] = 0.
    sigma = bipower_volatility(returns)[-1]
    corrected = lee_mykland_threshold(LM_TEST_BLOCK_SIZE, standardized=True)
    uncorrected = lee_mykland_threshold(LM_TEST_BLOCK_SIZE)
    desired_statistic = (corrected + uncorrected) / 2
    returns[-1] = -sigma * desired_statistic
    prices = 100 * np.exp(np.cumsum(returns))
    result = extract_jumps(prices)
    assert result['test_statistic'][-1] == pytest.approx(desired_statistic, rel=1e-10)
    assert corrected < result['test_statistic'][-1] < uncorrected
    assert result['is_jump'][-1]
    assert result['jump_sign'][-1] == -1


def test_default_jump_flags_are_prefix_invariant_when_prices_are_appended():
    """Designed so the old full-input multiplicity would revise the shock."""
    rng = np.random.default_rng(531)
    returns = rng.normal(0, .001, size=1400)
    returns[0] = 0.
    cut, shock = 700, 300
    sigma = bipower_volatility(returns)[shock]
    old_short = lee_mykland_threshold(cut - LM_WINDOW_K)
    old_full = lee_mykland_threshold(len(returns) - LM_WINDOW_K)
    returns[shock] = -sigma * (old_short + old_full) / 2
    prices = 100 * np.exp(np.cumsum(returns))
    full, prefix = extract_jumps(prices), extract_jumps(prices[:cut])
    for name in full:
        np.testing.assert_array_equal(full[name][:cut], prefix[name])
    assert full['is_jump'][shock]
    assert old_short < full['test_statistic'][shock] < old_full


def test_explicit_retrospective_mode_uses_full_input_multiplicity_in_correct_units():
    rng = np.random.default_rng(12)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, .001, 1200)))
    result = extract_jumps(prices, test_block_size=None)
    sigma = bipower_volatility(result['log_return'])
    a_n, b_n = _extreme_value_constants(int(np.isfinite(sigma).sum()))
    threshold = a_n - b_n * np.log(-np.log(1 - LM_ALPHA))
    np.testing.assert_array_equal(result['is_jump'], result['test_statistic'] > threshold)


def test_invalid_multiplicity_and_alpha_are_rejected():
    for bad in (0, 1, 2.5, True):
        with pytest.raises(ValueError, match='test_block_size'):
            extract_jumps(np.ones(300), test_block_size=bad)
    for bad in (0, 1, -1):
        with pytest.raises(ValueError, match='alpha'):
            extract_jumps(np.ones(300), alpha=bad)
