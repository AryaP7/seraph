# C4 — cross-sectional feature estimators (FR6, FR20, FR53)
"""Estimator properties checked against data with known ground truth: a
Yang-Zhang estimate must recover a known volatility, the Absorption Ratio must
rise as variance concentrates into fewer factors, and the spread estimators
must be non-negative and increase with a widening simulated spread."""
from __future__ import annotations

import numpy as np
import pytest

from seraph.features import (
    abdi_ranaldo_spread,
    absorption_ratio,
    corwin_schultz_spread,
    volatility_estimator_agreement,
    yang_zhang_volatility,
)

TRADING_DAYS = 252


def _ohlc(rng, n_days, daily_sigma, spread=0.0, price0=100.0):
    """Simulate OHLC from an intraday random walk, optionally with a bid-ask
    bounce of the given relative width applied to the closing price."""
    o, h, l_, c = [], [], [], []
    px = price0
    for _ in range(n_days):
        steps = px * np.exp(np.cumsum(rng.normal(0, daily_sigma / np.sqrt(40), 40)))
        open_, close = steps[0], steps[-1]
        if spread > 0:
            close *= 1.0 + (spread / 2.0) * rng.choice([-1.0, 1.0])
        o.append(open_); h.append(steps.max()); l_.append(steps.min()); c.append(close)
        px = steps[-1]
    return map(np.array, (o, h, l_, c))


def test_yang_zhang_recovers_known_volatility():
    rng = np.random.default_rng(0)
    true_daily = 0.02                       # 2% daily => ~31.7% annualised
    o, h, l_, c = _ohlc(rng, 400, true_daily)
    est = yang_zhang_volatility(o, h, l_, c, window=250)
    expected = true_daily * np.sqrt(TRADING_DAYS)
    assert np.isfinite(est)
    assert est == pytest.approx(expected, rel=0.25), (
        f"Yang-Zhang gave {est:.4f} against a true {expected:.4f}"
    )


def test_yang_zhang_orders_two_volatility_levels():
    rng = np.random.default_rng(1)
    calm = yang_zhang_volatility(*_ohlc(rng, 300, 0.008), window=250)
    wild = yang_zhang_volatility(*_ohlc(rng, 300, 0.032), window=250)
    assert wild > calm * 2.0


def test_yang_zhang_needs_enough_data():
    rng = np.random.default_rng(2)
    o, h, l_, c = _ohlc(rng, 5, 0.02)
    assert np.isnan(yang_zhang_volatility(o, h, l_, c, window=21))


def test_absorption_ratio_rises_as_variance_concentrates():
    """One dominant factor absorbs far more variance than many weak ones."""
    rng = np.random.default_rng(3)
    n_obs, n_sym = 500, 60

    one_factor = (rng.normal(size=(n_obs, 1)) @ np.ones((1, n_sym))
                  + 0.3 * rng.normal(size=(n_obs, n_sym)))
    diffuse = rng.normal(size=(n_obs, n_sym))

    ar_concentrated = absorption_ratio(one_factor)
    ar_diffuse = absorption_ratio(diffuse)
    assert 0.0 <= ar_diffuse <= 1.0 and 0.0 <= ar_concentrated <= 1.0
    assert ar_concentrated > 0.9, "a single dominant factor should absorb almost everything"
    assert ar_concentrated > ar_diffuse + 0.3


def test_absorption_ratio_is_bounded_and_handles_degenerate_input():
    rng = np.random.default_rng(4)
    assert 0.0 <= absorption_ratio(rng.normal(size=(300, 40))) <= 1.0
    assert np.isnan(absorption_ratio(np.zeros((5, 1))))


def test_spread_estimators_are_non_negative_and_increase_with_spread():
    rng = np.random.default_rng(5)
    _, h0, l0, c0 = _ohlc(rng, 300, 0.015, spread=0.0)
    _, h1, l1, c1 = _ohlc(rng, 300, 0.015, spread=0.02)

    tight = abdi_ranaldo_spread(h0, l0, c0)
    wide = abdi_ranaldo_spread(h1, l1, c1)
    assert tight >= 0.0 and wide >= 0.0, "spreads are floored at zero, never negative"
    assert wide > tight, "a wider simulated bid-ask bounce must read wider"


def test_corwin_schultz_is_a_usable_cross_check():
    rng = np.random.default_rng(6)
    _, h, l_, _ = _ohlc(rng, 300, 0.015, spread=0.02)
    cs = corwin_schultz_spread(h, l_)
    assert np.isfinite(cs) and cs >= 0.0


def test_fr53_estimator_agreement_reports_correlation_and_overlap():
    rng = np.random.default_rng(7)
    yz = rng.uniform(0.1, 0.6, size=200)
    rv5 = yz * 1.05 + rng.normal(0, 0.02, size=200)
    rv5[:50] = np.nan                       # pre-2015 gap, as in the real corpus
    out = volatility_estimator_agreement(yz, rv5)
    assert out["nOverlappingDays"] == 150
    assert out["correlation"] > 0.9


def test_fr53_agreement_degrades_gracefully_without_overlap():
    out = volatility_estimator_agreement(np.array([0.1, 0.2]), np.array([np.nan, np.nan]))
    assert out["nOverlappingDays"] == 0
    assert np.isnan(out["correlation"])
