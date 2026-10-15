# C7 — regression tests for the EM plumbing and ground-truth regime recovery
"""Locks in two repairs that are invisible to every other Hamilton test.

Both are shape/start-value contracts with statsmodels, not behaviour any
public SERAPH interface exposes, so nothing in `test_c7_hamilton.py` or the
contract suite would catch a regression. Both had real, measured costs:

1. `_conditional_loglikelihoods` must return `(k, k, nobs)`, axis 1 being a
   broadcast `S_{t-1}`. statsmodels infers the filter order from
   `ndim - 2`, so the natural-looking `(k, nobs)` makes it allocate
   `smoothed_joint_probabilities` as the *marginals*. `_em_regime_transition`
   then reads single time-points where it means to read transition counts and
   writes a degenerate transition matrix — five times, before BFGS starts.
   Cost: a 3-state fit on a synthetic series with known regimes landed 16,573
   log-likelihood **below the true parameter point even when started there**,
   with 0%/0%/100% occupancy.

   The likelihood itself was never wrong, which is why this hid for so long.
   `test_likelihood_is_invariant_to_the_broadcast_axis` pins that down, so a
   future reader can see the fix changed plumbing and not the model.

2. `fit()` must offer the nested constant-transition optimum as a TVTP start.
   statsmodels sets the whole logit block to 0.0, implying a uniform 1/k
   transition matrix — half-life 1.04 days against a real p_jj of ~0.99 — and
   skips EM on that block entirely under TVTP. Cost: 6 of 14 walk-forward
   blocks reported a full-model likelihood *below their own nested
   restriction*, to LR = -2,322.88.

Series here are short and strongly separated so the suite stays quick; the
full-length, weakly-separated real-data behaviour is the job of
`scripts/validate_hamilton_regimes.py` and `scripts/hamilton_surrogate_null.py`.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from seraph.pillars.hamilton.engine import (
    MultivariateTVTPHamilton,
    _tvtp_start_from_constant,
    fit as engine_fit,
)

K = 3
NOBS = 1200

#: Three well-separated regimes at the real corpus's scale, persistent enough
#: that a working filter should identify them almost perfectly.
MU3 = np.array([[0.40, 0.37, 0.0038],
                [0.60, 0.43, 0.0058],
                [0.90, 0.51, 0.0085]])
SD3 = np.array([0.040, 0.016, 0.0005])
P3 = np.array([[0.970, 0.025, 0.005],
               [0.030, 0.950, 0.020],
               [0.010, 0.040, 0.950]])
MU2 = np.array([[0.42, 0.38, 0.0040], [0.74, 0.48, 0.0074]])
SD2 = np.array([0.045, 0.018, 0.0006])
P2 = np.array([[0.975, 0.025], [0.040, 0.960]])


def _markov(k, n, mu, sd, p_mat, seed):
    rng = np.random.default_rng(seed)
    s, lab = 0, []
    for _ in range(n):
        lab.append(s)
        s = rng.choice(k, p=p_mat[s])
    lab = np.array(lab)
    return mu[lab] + rng.normal(scale=sd, size=(n, mu.shape[1])), lab


def _realised_transition(labels, k):
    """Transition frequencies actually realised in this draw.

    The MLE targets the sample it was given, not the generating parameters. On
    a 1,200-day draw the crisis state holds only ~180 days, so its realised
    p_jj can sit well away from the generating value — here 0.896 against a
    generating 0.95, which both the EM step and the full MLE reproduce to four
    decimals. Comparing against the generating matrix would be testing the
    random draw, not the estimator.
    """
    counts = np.zeros((k, k))
    for a, b in zip(labels[:-1], labels[1:]):
        counts[a, b] += 1
    return counts / np.maximum(counts.sum(axis=1, keepdims=True), 1.0)


def _true_params(model, k, mu, sd, p_mat):
    """The generating parameters in the model's own parameterisation."""
    p = np.zeros(model.k_params)
    block = np.zeros((k - 1, k))
    for j_from in range(k):
        for i_to in range(k - 1):
            block[i_to, j_from] = p_mat[j_from, i_to]
    p[model.parameters["regime_transition"]] = block.ravel()
    for j in range(k):
        p[model.parameters[j, "means"]] = mu[j]
        p[model.parameters[j, "variances"]] = np.maximum(sd ** 2, model._var_floor)
    return p


def _summarise(res, model, k, nobs):
    params = res.params
    mu = np.array([params[model.parameters[j, "means"]][0] for j in range(k)])
    order = np.argsort(mu)
    smoothed = np.asarray(res.smoothed_marginal_probabilities)
    if smoothed.shape[0] != k:
        smoothed = smoothed.T
    smoothed = smoothed[:, :nobs]
    raw = np.argmax(smoothed, axis=0)
    rank = np.empty(k, dtype=int)
    for r, idx in enumerate(order):
        rank[idx] = r
    trans = np.asarray(model.regime_transition_matrix(params))[:, :, 0]
    return {
        "occ": np.bincount(raw, minlength=k)[order] / raw.size,
        "labels": rank[raw],
        "diag": np.array([trans[j, j] for j in range(k)])[order],
    }


@pytest.fixture(scope="module")
def syn3():
    return _markov(K, NOBS, MU3, SD3, P3, seed=11)


@pytest.fixture(scope="module")
def syn2():
    return _markov(2, NOBS, MU2, SD2, P2, seed=7)


# --- 1. the shape contract with statsmodels ----------------------------- #

def test_conditional_loglikelihoods_carries_the_previous_regime_axis(syn3):
    y, _ = syn3
    model = MultivariateTVTPHamilton(y, k_regimes=K)
    out = np.asarray(model._conditional_loglikelihoods(model.start_params))
    assert out.shape == (K, K, NOBS), (
        "statsmodels infers filter order from ndim-2; a (k, nobs) return makes "
        "it allocate the marginals where _em_regime_transition expects the joint"
    )
    # axis 1 is S_{t-1}: a Gaussian emission cannot depend on it
    assert np.allclose(out, out[:, 0][:, None, :])
    # axis 0 is S_t and must actually vary across regimes
    assert not np.allclose(out, out[0][None, ...])


def test_smoothed_joint_probabilities_is_a_joint_not_a_marginal(syn3):
    y, _ = syn3
    model = MultivariateTVTPHamilton(y, k_regimes=K)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = model.smooth(model.start_params, transformed=True, return_raw=True)
    assert np.asarray(res.smoothed_joint_probabilities).shape == (K, K, NOBS)
    assert np.asarray(res.smoothed_marginal_probabilities).shape == (K, NOBS)


def test_em_transition_step_recovers_a_known_transition_matrix(syn3):
    """The direct regression test for the defect.

    Smoothing at the generating parameters identifies the state path almost
    exactly, so the EM transition update must return approximately the
    generating transition matrix. The broken version returned a matrix built
    from three arbitrary single-day probabilities, with p_00 = 4e-4 and
    p_11 = 0.0 against a true 0.970 and 0.950.
    """
    y, labels = syn3
    model = MultivariateTVTPHamilton(y, k_regimes=K)
    true = _true_params(model, K, MU3, SD3, P3)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = model.smooth(true, transformed=True, return_raw=True)
        _, params1 = model._em_iteration(true)
    recovered = np.asarray(model.regime_transition_matrix(params1))[:, :, 0]
    realised = _realised_transition(labels, K)
    for j in range(K):
        assert recovered[j, j] == pytest.approx(realised[j, j], abs=0.03), (
            f"EM put p_{j}{j} at {recovered[j, j]:.4g}, realised "
            f"{realised[j, j]:.4g} (generating {P3[j, j]})"
        )
    assert np.max(np.abs(np.asarray(res.smoothed_marginal_probabilities).sum(axis=0)
                         - 1.0)) < 1e-8


def test_likelihood_differs_only_by_a_fixed_initialisation_term(syn3):
    """The fix changed plumbing, not the emission density.

    Collapsing the broadcast `S_{t-1}` axis by hand does *not* give a bitwise
    identical likelihood: it differs by the t=0 boundary condition. What makes
    that harmless is that the gap is **constant in the sample size** — a single
    initialisation term, not a per-observation discrepancy. Measured at
    0.009754 nats to six decimals for every n from 300 to 20,000, against the
    16,573-nat optimisation gain the fix buys.

    If this ever fails by growing with n, the repair altered the emission
    density and every number produced under it needs re-deriving.
    """
    class Collapsed(MultivariateTVTPHamilton):
        def _conditional_loglikelihoods(self, params):
            return np.asarray(super()._conditional_loglikelihoods(params))[:, 0, :]

    y_full, _ = syn3
    gaps = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for n in (300, 600, 1200):
            y = y_full[:n]
            full = MultivariateTVTPHamilton(y, k_regimes=K)
            coll = Collapsed(y, k_regimes=K)
            gaps[n] = (float(full.loglike(_true_params(full, K, MU3, SD3, P3)))
                       - float(coll.loglike(_true_params(coll, K, MU3, SD3, P3))))
    values = list(gaps.values())
    assert max(values) - min(values) < 1e-9, f"gap must not vary with n: {gaps}"
    assert abs(values[0]) < 0.05, f"initialisation gap unexpectedly large: {gaps}"


# --- 2. ground-truth recovery -------------------------------------------- #

def test_three_state_fit_recovers_known_regimes(syn3):
    y, labels = syn3
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res, _, _ = engine_fit(y, k_regimes=K, restarts=1, seed=0)
    got = _summarise(res, res.model, K, NOBS)
    true_occ = np.bincount(labels, minlength=K) / labels.size

    assert np.max(np.abs(got["occ"] - true_occ)) < 0.05, (
        f"occupancy {np.round(got['occ'], 3)} vs true {np.round(true_occ, 3)}")
    realised = np.diag(_realised_transition(labels, K))
    assert np.max(np.abs(got["diag"] - realised)) < 0.03, (
        f"transition diagonal {np.round(got['diag'], 4)} vs realised "
        f"{np.round(realised, 4)} (generating {np.diag(P3)})")
    assert np.mean(got["labels"] == labels) > 0.95
    assert got["occ"].min() > 0.05, "a state at ~0% is the old absorbing collapse"


def test_two_state_fit_recovers_known_regimes(syn2):
    y, labels = syn2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res, _, _ = engine_fit(y, k_regimes=2, restarts=1, seed=0)
    got = _summarise(res, res.model, 2, NOBS)
    true_occ = np.bincount(labels, minlength=2) / labels.size
    assert np.max(np.abs(got["occ"] - true_occ)) < 0.05
    realised = np.diag(_realised_transition(labels, 2))
    assert np.max(np.abs(got["diag"] - realised)) < 0.03
    assert np.mean(got["labels"] == labels) > 0.95


def test_fit_does_not_land_far_below_the_true_parameter_point(syn3):
    """The precise signature of the defect, as an assertion.

    A maximum-likelihood fit on a well-identified sample should match or beat
    the generating parameters. The broken version landed 16,573 below them.
    """
    y, _ = syn3
    model = MultivariateTVTPHamilton(y, k_regimes=K)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        llf_true = float(model.loglike(_true_params(model, K, MU3, SD3, P3)))
        res, _, _ = engine_fit(y, k_regimes=K, restarts=1, seed=0)
    assert float(res.llf) > llf_true - 50.0, (
        f"fit llf {res.llf:.1f} is {llf_true - float(res.llf):.1f} below the "
        f"true parameter point's {llf_true:.1f}")


def test_white_noise_does_not_yield_persistent_well_populated_regimes():
    """Negative control: no regimes in, no regimes out.

    A procedure that finds persistent, well-populated regimes in i.i.d. noise
    cannot be used as evidence of regimes anywhere.
    """
    rng = np.random.default_rng(23)
    y = np.array([0.50, 0.40, 0.0048]) + rng.normal(
        scale=[0.164, 0.056, 0.0018], size=(NOBS, 3))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res, _, _ = engine_fit(y, k_regimes=K, restarts=1, seed=0)
    got = _summarise(res, res.model, K, NOBS)
    half = np.array([np.log(2) / max(1 - d, 1e-12) for d in got["diag"]])
    assert got["occ"].min() < 0.10 or half.min() < 5.0, (
        f"i.i.d. noise produced occupancy {np.round(got['occ'], 3)} with "
        f"half-lives {np.round(half, 1)} — all states populated and persistent")


# --- 3. the TVTP warm start ---------------------------------------------- #

def _exog(y):
    """Causal [1, z_{t-1}] on the first column, as hamilton_causal builds it."""
    rv = y[:, 0]
    z = np.zeros(rv.size)
    for t in range(1, rv.size):
        hist = rv[:t]
        sd = hist.std(ddof=1) if t > 1 else 0.0
        z[t] = (rv[t] - hist.mean()) / sd if sd > 0 else 0.0
    return np.column_stack([np.ones(rv.size), np.r_[0.0, z[:-1]]])


def test_tvtp_warm_start_reproduces_the_nested_transition_matrix(syn3):
    """Zero slopes and intercepts log(p_ij / p_kj) must rebuild the constant
    matrix exactly — that is what makes it the restricted model's optimum."""
    y, _ = syn3
    exog = _exog(y)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = MultivariateTVTPHamilton(y, exog_tvtp=exog, k_regimes=K)
        assert model.tvtp
        warm = _tvtp_start_from_constant(
            model, y, k_regimes=K, maxiter=200, restarts=0, seed=0)
        assert warm is not None
        nested, _, _ = engine_fit(y, k_regimes=K, restarts=0, seed=0)
        llf_warm = float(model.loglike(warm))
    p_nested = np.asarray(
        nested.model.regime_transition_matrix(nested.params))[:, :, 0]
    p_warm = np.asarray(model.regime_transition_matrix(warm))[:, :, 0]
    assert np.max(np.abs(p_warm - p_nested)) < 1e-6
    assert llf_warm == pytest.approx(float(nested.llf), abs=1e-4), (
        "the warm start must sit exactly at the restricted optimum")


def test_tvtp_fit_is_not_below_its_nested_restriction(syn3):
    """FR21's full model nests the constant-transition model, so its likelihood
    cannot be lower. 6 of 14 real walk-forward blocks violated this."""
    y, _ = syn3
    exog = _exog(y)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        nested, _, _ = engine_fit(y, k_regimes=K, restarts=1, seed=0)
        full, _, _ = engine_fit(y, exog_tvtp=exog, k_regimes=K,
                                restarts=1, seed=0)
    assert float(full.llf) >= float(nested.llf) - 1e-6, (
        f"TVTP llf {full.llf:.2f} below its own nested restriction "
        f"{nested.llf:.2f} (LR = {2 * (full.llf - nested.llf):+.2f})")


def test_default_tvtp_start_is_the_uniform_matrix(syn3):
    """Documents the start value the warm start exists to replace. If
    statsmodels ever changes this, the warm start may be unnecessary."""
    y, _ = syn3
    model = MultivariateTVTPHamilton(y, exog_tvtp=_exog(y), k_regimes=K)
    start = np.asarray(model.start_params, dtype=float)
    assert np.allclose(start[model.parameters["regime_transition"]], 0.0)
    implied = np.asarray(model.regime_transition_matrix(start))[:, :, 0]
    assert np.allclose(implied, 1.0 / K, atol=1e-9)
