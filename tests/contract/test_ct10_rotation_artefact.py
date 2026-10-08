# CT-10 — C3 ⇄ C6: rotation artefact (ARCHITECTURE §5 ⑥, decision D3)
"""Proves Ω_t is computed on common support and does not spike at a rebalance.

This is the only test that can prove D3 works. FR17's
Ω_t = 1 − |⟨v₁,ₜ, v₁,ₜ₋Δ⟩| takes an inner product of two eigenvectors; when
membership changes those vectors live in different coordinate spaces and the
product is undefined, not merely noisy. The setup forces a 15% membership
change at a known date while holding the underlying correlation structure
constant, so any Ω_t spike is a pure artefact.
"""
from __future__ import annotations

import numpy as np
import pytest

from seraph.pillars.rmt.engine import compute_rmt

T_WINDOW, N_SYMBOLS, CHURN_FRACTION = 400, 120, 0.15


def _factor_returns(rng, n_obs, symbols):
    """A dominant market factor plus two weaker sector factors, over
    idiosyncratic noise — a stable, known structure whose leading eigenvector
    is well separated, and which puts more than one eigenvalue above the MP
    edge (a single factor produces just one outlier, which the null itself
    yields often enough that it is not significant)."""
    n = len(symbols)
    market = rng.normal(size=(n_obs, 1)) @ rng.uniform(0.6, 1.0, size=(1, n))
    sectors = np.zeros((n_obs, n))
    half = n // 2
    for lo, hi in ((0, half), (half, n)):
        sectors[:, lo:hi] = (
            rng.normal(size=(n_obs, 1)) @ rng.uniform(0.3, 0.5, size=(1, hi - lo))
        )
    idio = rng.normal(size=(n_obs, n)) * 0.7
    return market + sectors + idio


def _panel(seed: int = 0):
    rng = np.random.default_rng(seed)
    all_symbols = [f"SYM{i:04d}" for i in range(N_SYMBOLS + 40)]
    base = all_symbols[:N_SYMBOLS]
    n_swap = int(CHURN_FRACTION * N_SYMBOLS)
    # After the rebalance, the last n_swap names are replaced by fresh ones.
    after = base[:-n_swap] + all_symbols[N_SYMBOLS:N_SYMBOLS + n_swap]
    returns = {s: None for s in all_symbols}
    data = _factor_returns(rng, T_WINDOW + 5, all_symbols)
    for i, s in enumerate(all_symbols):
        returns[s] = data[:, i]
    return base, after, returns


def _window(returns, members, end: int, t: int = T_WINDOW):
    return np.column_stack([returns[s][end - t:end] for s in members])


def test_ct10_omega_does_not_spike_at_a_rebalance():
    base, after, returns = _panel()

    # Pre-rebalance days: membership constant, so Ω_t is a clean baseline.
    baseline = []
    prev_v1 = None
    for k in range(4):
        r = compute_rmt(
            returns=_window(returns, base, T_WINDOW + k),
            members=tuple(base),
            prev_v1=prev_v1,
            prev_members=tuple(base) if prev_v1 is not None else None,
            bootstrap_reps=0,
        )
        assert r.status == "ok", r
        prev_v1 = np.array(r.value.leading_eigenvector)
        if prev_v1 is not None and k > 0:
            baseline.append(r.value.omega_t)

    # The rebalance day: 15% of names change, structure held constant.
    reb = compute_rmt(
        returns=_window(returns, after, T_WINDOW + 4),
        members=tuple(after),
        prev_v1=prev_v1,
        prev_members=tuple(base),
        bootstrap_reps=0,
        rebalance_adjacent=True,
    )
    assert reb.status == "ok"
    detail = reb.value

    assert detail.rebalance_adjacent is True
    assert detail.common_support_fraction >= 0.85, (
        f"85% of names persist across this rebalance; got "
        f"{detail.common_support_fraction:.3f}"
    )
    # The whole point of D3: Ω_t at the rebalance stays within the
    # no-membership-change distribution instead of spiking.
    assert detail.omega_t <= max(baseline) * 3 + 0.02, (
        f"Ω_t spiked at the rebalance ({detail.omega_t:.4f}) versus a "
        f"baseline max of {max(baseline):.4f} — common-support restriction "
        f"is not working"
    )


def test_ct10_low_common_support_warns_but_still_emits():
    base, _, returns = _panel()
    disjoint = [f"SYM{i:04d}" for i in range(N_SYMBOLS + 40 - 30, N_SYMBOLS + 40)]
    members_now = disjoint + base[: N_SYMBOLS - len(disjoint)]

    seed = compute_rmt(
        returns=_window(returns, base, T_WINDOW),
        members=tuple(base), bootstrap_reps=0,
    )
    res = compute_rmt(
        returns=_window(returns, members_now, T_WINDOW + 1),
        members=tuple(members_now),
        prev_v1=np.array(seed.value.leading_eigenvector),
        prev_members=tuple(base),
        bootstrap_reps=0,
        rebalance_adjacent=True,
    )
    assert res.status == "ok", "Ω_t is still emitted, just flagged"
    assert any(w.code == "COMMON_SUPPORT_LOW" for w in res.warnings)


def test_ct10_zero_common_support_is_an_error_not_a_silent_zero():
    base, _, returns = _panel()
    other = [f"SYM{i:04d}" for i in range(N_SYMBOLS, N_SYMBOLS + 40)]
    seed = compute_rmt(
        returns=_window(returns, base, T_WINDOW),
        members=tuple(base), bootstrap_reps=0,
    )
    res = compute_rmt(
        returns=_window(returns, other, T_WINDOW + 1)[:, :len(other)],
        members=tuple(other),
        prev_v1=np.array(seed.value.leading_eigenvector),
        prev_members=tuple(base),
        bootstrap_reps=0,
    )
    assert res.status == "error"
    assert res.error.kind == "CONSTRAINT_VIOLATED"


def test_ct10_q_and_mp_bounds_follow_the_realised_n():
    """AMENDMENT-02 — λ± must be evaluated at Q_t = T/N_t, not a fixed Q=2."""
    base, _, returns = _panel()
    full = compute_rmt(
        returns=_window(returns, base, T_WINDOW),
        members=tuple(base), bootstrap_reps=0,
    )
    thin_members = base[:60]
    thin = compute_rmt(
        returns=_window(returns, thin_members, T_WINDOW),
        members=tuple(thin_members), bootstrap_reps=0,
    )
    assert full.status == "ok" and thin.status == "ok"
    # A smaller cross-section means a larger Q, hence a tighter noise band.
    assert thin.value.lambda_plus < full.value.lambda_plus
    assert thin.value.lambda_minus > full.value.lambda_minus


def test_ct10_bootstrap_gives_a_pvalue():
    """FR19 — a p-value must accompany every F_t."""
    base, _, returns = _panel()
    res = compute_rmt(
        returns=_window(returns, base, T_WINDOW),
        members=tuple(base), bootstrap_reps=200,
    )
    assert res.status == "ok"
    assert 0.0 <= res.value.mp_p_value <= 1.0
    # A single strong common factor must exceed the MP null decisively.
    assert res.value.f_t > 0.0
    assert res.value.mp_p_value < 0.05
