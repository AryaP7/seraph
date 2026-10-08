# C5 — Hawkes Engine: recovery of known kernels (FR10, FR11, FR13)
"""Estimator checked against simulated Hawkes processes with known parameters.
The point is not that the code runs but that it recovers the branching ratio,
which is the quantity the risk signal is built from."""
from __future__ import annotations

import numpy as np
import pytest

from seraph.pillars.hawkes import (
    MIN_EVENTS_PER_STATE,
    StateKernel,
    detail_from,
    fit_pooled,
    fit_state_kernel,
    mts,
    sector_flags,
)


def simulate_hawkes(mu, alpha, beta, horizon, rng):
    """Ogata thinning for a univariate exponential-kernel Hawkes process."""
    events, t = [], 0.0
    while t < horizon:
        lam_bar = mu + alpha * sum(np.exp(-beta * (t - s)) for s in events[-200:])
        t += rng.exponential(1.0 / max(lam_bar, 1e-9))
        if t >= horizon:
            break
        lam = mu + alpha * sum(np.exp(-beta * (t - s)) for s in events[-200:])
        if rng.uniform() <= lam / max(lam_bar, 1e-9):
            events.append(t)
    return np.array(events)


def test_c5_recovers_a_known_branching_ratio():
    rng = np.random.default_rng(0)
    mu, n_true, beta = 2.0, 0.45, 8.0
    ev = simulate_hawkes(mu, n_true * beta, beta, 300.0, rng)
    assert ev.size > 300, "simulation should produce a usable sample"
    k = fit_state_kernel(ev, 300.0)
    assert k is not None
    assert k.branching_ratio == pytest.approx(n_true, abs=0.15), (
        f"recovered n={k.branching_ratio:.3f} against a true {n_true}"
    )


def test_c5_orders_two_contagion_levels():
    """The estimator must rank a highly self-exciting process above a mild one —
    the ordering is what the risk signal actually depends on."""
    rng = np.random.default_rng(1)
    mild = fit_state_kernel(simulate_hawkes(3.0, 0.15 * 8, 8.0, 300.0, rng), 300.0)
    hot = fit_state_kernel(simulate_hawkes(3.0, 0.70 * 8, 8.0, 300.0, rng), 300.0)
    assert mild is not None and hot is not None
    assert hot.branching_ratio > mild.branching_ratio + 0.2


def test_c5_fr11_branching_ratio_always_below_one():
    """FR11 holds by construction: the optimiser works on logit(n), so n<1 is
    structural, not a clip. Even near-critical data cannot violate it."""
    rng = np.random.default_rng(2)
    ev = simulate_hawkes(1.0, 0.95 * 6.0, 6.0, 400.0, rng)
    k = fit_state_kernel(ev, 400.0)
    assert k is not None
    assert 0.0 < k.branching_ratio < 1.0


def test_c5_thin_state_is_not_estimated():
    rng = np.random.default_rng(3)
    assert fit_state_kernel(np.sort(rng.uniform(0, 60, MIN_EVENTS_PER_STATE - 1)), 60.0) is None


def test_c5_pooled_fit_reports_thin_states():
    rng = np.random.default_rng(4)
    times = np.sort(rng.uniform(0, 60, 400))
    states = rng.integers(1, 4, size=times.size)      # only 3 of 9 populated
    res = fit_pooled(event_times=times, event_states=states, horizon_days=60.0)
    assert res.status == "ok"
    assert any(w.code == "LOW_EVENT_COUNT" for w in res.warnings)
    assert set(res.value["kernels"]).issubset({1, 2, 3})


def test_c5_pooled_fit_needs_a_minimum_sample():
    res = fit_pooled(event_times=np.arange(5.0), event_states=np.ones(5, int),
                     horizon_days=60.0)
    assert res.status == "error"
    assert res.error.kind == "INSUFFICIENT_HISTORY"


def test_fr13_gate_tests_against_the_market_baseline_not_symmetry():
    """FR13 re-specified. The old rule (ratio > 1.0) implied a 0.5 downside
    share; the measured NSE share is 0.4254 at z = -33.3 from symmetry, so that
    null is falsified and the gate suppressed MTS_t corpus-wide. The replacement
    asks whether downside is elevated relative to the market's OWN baseline."""
    from seraph.pillars.hawkes import DOWNSIDE_BASELINE_SHARE, asymmetry_significance

    # A window sitting exactly at the corpus base rate is normal, not toxic.
    open_, pval, share = asymmetry_significance(21180, 28603)
    assert not open_ and share == pytest.approx(DOWNSIDE_BASELINE_SHARE, abs=1e-3)

    # A genuinely elevated downside mix opens the gate.
    open_, pval, share = asymmetry_significance(300, 300)
    assert open_ and pval < 0.05 and share == pytest.approx(0.5)

    # An upside-skewed window stays shut.
    open_, _, _ = asymmetry_significance(180, 420)
    assert not open_


def test_fr13_gate_is_not_degenerate_in_either_direction():
    """It must be possible both to open and to close the gate: a rule that
    always fires or never fires carries no information."""
    from seraph.pillars.hawkes import asymmetry_significance

    assert asymmetry_significance(600, 400)[0] is True
    assert asymmetry_significance(400, 600)[0] is False


def test_c5_mts_is_monotone_in_contagion():
    vals = [mts(n, 2.0) for n in (0.1, 0.3, 0.5, 0.7, 0.9)]
    assert all(b > a for a, b in zip(vals, vals[1:]))


def test_c5_sector_flags_use_intensity_over_baseline():
    """AMENDMENT-03(e) — FR14 flags come from realised-vs-baseline intensity,
    never from a sector branching ratio, which the event counts cannot identify."""
    flags = sector_flags(
        {"steel": 30, "pharmaceuticals": 5},
        {"steel": 0.25, "pharmaceuticals": 0.5},
        window_days=60.0,
    )
    by = {f.sector_id: f for f in flags}
    assert by["steel"].flag == "amber"          # 0.50/day vs 0.25 baseline = 2.0x
    assert by["pharmaceuticals"].flag == "none"  # 0.083/day vs 0.5 baseline


def test_c5_detail_satisfies_the_s5_contract():
    k = StateKernel(state=1, mu=1.0, branching_ratio=0.6, beta=5.0,
                    n_events=100, converged=True)
    d = detail_from(k, n_neg=40, n_pos=20)
    assert d.branching_ratio < 1.0
    assert d.asymmetry_ratio == pytest.approx(2.0)
    assert d.jump_count_neg == 40 and d.jump_count_pos == 20


# --- AMENDMENT-03 identifiability guards ---------------------------------
# These lock in a measured finding. They are not style checks: reverting to an
# unbounded continuous-time kernel on tied data reintroduces a degeneracy that
# produced beta ~ 1e300 and n = 1.0 on the real corpus.

def test_amendment03_branching_ratio_is_not_identifiable_on_tied_data():
    """The core AMENDMENT-03 §2 finding, as a regression guard.

    On tied data the continuous-time likelihood has no stable interior optimum:
    the recovered branching ratio swings wildly with the beta ceiling, so any
    n reported from this path is an artefact of the bound rather than a
    property of the market. On the real corpus beta_hat pinned to the ceiling
    at every value tested (72 -> 2880) while n drifted 0.834 -> 0.752; on the
    synthetic fixture below the same non-identifiability shows up as an even
    larger swing in n.

    If this test starts passing stably, the tie structure has changed and
    AMENDMENT-03 must be re-measured before any Pillar 1 number is reported.
    """
    import seraph.pillars.hawkes.engine as eng
    from seraph.pillars.hawkes.engine import fit_state_kernel

    tied = np.sort(np.repeat(np.arange(80) / 288.0, 6))   # 6 events per bar
    horizon = 80 / 288.0
    original = eng.BETA_MAX
    try:
        ns = []
        for ceiling in (144.0, 288.0, 576.0):
            eng.BETA_MAX = ceiling
            k = fit_state_kernel(tied, horizon)
            assert k is not None
            ns.append(k.branching_ratio)
    finally:
        eng.BETA_MAX = original

    assert max(ns) - min(ns) > 0.25, (
        f"branching ratio should be bound-dependent on tied data; got a spread "
        f"of only {max(ns) - min(ns):.3f} across ceilings {ns}"
    )


def test_amendment03_beta_is_bounded_so_a_fit_cannot_diverge():
    """The bound stops beta ~ 1e300, but AMENDMENT-03 §2 records that it also
    determines the answer — which is why a branching ratio from this path is
    not reportable. The guard is that the fit stays finite, not that it is
    interpretable."""
    from seraph.pillars.hawkes.engine import BETA_MAX, fit_state_kernel

    rng = np.random.default_rng(6)
    tied = np.sort(np.repeat(np.arange(60) / 288.0, 5))
    k = fit_state_kernel(tied, 60 / 288.0)
    assert k is not None
    assert np.isfinite(k.beta) and k.beta <= BETA_MAX + 1e-6
    assert 0.0 < k.branching_ratio < 1.0


def test_amendment03_asymmetry_gate_is_uninformative_on_real_base_rates():
    """Measured NSE asymmetry is 0.74 — positive jumps outnumber negative — so
    FR13's gate at 1.0 zeroes MTS_t across the whole corpus. Locked in as a
    known specification defect (AMENDMENT-03 §5e); the fix is a significance
    test against the symmetric null, NOT lowering the constant."""
    assert mts(0.85, asymmetry_ratio=0.74) == 0.0
    assert mts(0.85, asymmetry_ratio=1.2) > 0.0


def test_discrete_hawkes_recovers_a_known_kernel():
    """AMENDMENT-03 §5d — the RETAINED estimator. Unlike the continuous-time
    version it is identifiable at native 5-minute resolution, so this is a
    genuine recovery test rather than a stability guard."""
    from seraph.pillars.hawkes import fit_discrete_hawkes

    rng = np.random.default_rng(0)
    n_bars = 6000
    prof = np.ones(75)
    ti = np.arange(n_bars) % 75
    ss = ti == 0
    x = np.zeros(n_bars)
    exc = 0.0
    for i in range(n_bars):
        if ss[i]:
            exc = 0.0
        x[i] = rng.poisson(0.09 + 0.055 * exc)
        exc = 0.5 * exc + x[i]

    f = fit_discrete_hawkes(x, ss, prof, ti)
    assert f is not None
    assert f.branching_ratio == pytest.approx(0.110, abs=0.04), (
        f"recovered n={f.branching_ratio:.4f} against a true 0.110"
    )
    assert 0.0 < f.phi < 1.0 and 0.0 < f.branching_ratio < 1.0   # FR11


def test_discrete_hawkes_returns_none_rather_than_a_zero_reading():
    """Too little data must be `unavailable`, never a fabricated n=0."""
    from seraph.pillars.hawkes import fit_discrete_hawkes

    prof = np.ones(75)
    ti = np.arange(10) % 75
    assert fit_discrete_hawkes(np.zeros(10), ti == 0, prof, ti) is None


# --- production-path isolation and downstream contract -------------------

def test_production_path_never_uses_the_rejected_continuous_estimator():
    """Requirement 8: the discrete production path must not reach the legacy
    continuous code, whose beta bound is a diagnostic scaffold and not a
    modelling choice (AMENDMENT-03 §2)."""
    import inspect

    import seraph.pillars.hawkes.engine as E

    for fn in (E.estimate_state, E.fit_discrete_hawkes, E.excitation_path):
        src = inspect.getsource(fn)
        for banned in ("fit_state_kernel", "BETA_MAX", "_neg_loglik", "fit_pooled"):
            assert banned not in src, (
                f"{fn.__name__} references the rejected continuous path ({banned})"
            )


def test_estimate_state_emits_the_unchanged_s5_contract():
    """Requirement 9/10: downstream receives the same HawkesDetail shape C8
    already consumes — only the estimator behind branching_ratio changed."""
    from seraph.shared_types import HawkesDetail
    from seraph.pillars.hawkes import estimate_state

    rng = np.random.default_rng(3)
    n_bars = 6000
    prof = np.ones(75)
    ti = np.arange(n_bars) % 75
    ss = ti == 0
    x = np.zeros(n_bars)
    exc = 0.0
    for i in range(n_bars):
        if ss[i]:
            exc = 0.0
        x[i] = rng.poisson(0.09 + 0.055 * exc)
        exc = 0.5 * exc + x[i]

    res = estimate_state(counts=x, session_starts=ss, tod_profile=prof, tod_index=ti,
                         n_neg=int(x.sum()), n_pos=int(x.sum() * 0.7))
    assert res.status == "ok"
    detail, score = res.value
    assert isinstance(detail, HawkesDetail)
    assert 0.0 < detail.branching_ratio < 1.0          # FR11
    assert score > 0.0, "asymmetry 1.43 > 1.0 should NOT suppress MTS"


def test_gate_suppression_is_warned_not_silent():
    """FR13: at the measured NSE base rate (0.74) the gate zeroes MTS_t. That
    must surface a warning rather than pass as a calm reading."""
    from seraph.pillars.hawkes import estimate_state

    rng = np.random.default_rng(4)
    n_bars = 6000
    prof = np.ones(75)
    ti = np.arange(n_bars) % 75
    ss = ti == 0
    x = np.zeros(n_bars)
    exc = 0.0
    for i in range(n_bars):
        if ss[i]:
            exc = 0.0
        x[i] = rng.poisson(0.09 + 0.055 * exc)
        exc = 0.5 * exc + x[i]

    res = estimate_state(counts=x, session_starts=ss, tod_profile=prof, tod_index=ti,
                         n_neg=100, n_pos=135)          # asymmetry 0.74, as measured
    assert res.status == "ok"
    _, score = res.value
    assert score == 0.0
    assert any(w.code == "LOW_EVENT_COUNT" for w in res.warnings), (
        "a suppressed MTS_t must be flagged, never silently zero"
    )


def test_unidentifiable_window_is_an_error_not_a_zero():
    from seraph.pillars.hawkes import estimate_state

    prof = np.ones(75)
    ti = np.arange(10) % 75
    res = estimate_state(counts=np.zeros(10), session_starts=(ti == 0),
                         tod_profile=prof, tod_index=ti, n_neg=0, n_pos=0)
    assert res.status == "error"
    assert res.error.kind == "INSUFFICIENT_HISTORY"
