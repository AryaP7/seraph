# C7 — regression guards for the causal Hamilton path and the multi-start fix.
"""These lock in the failures found during the TVTP identification diagnostic.

Context, so a future reader knows why each guard exists:

* statsmodels does **not** run its EM step on transition parameters under TVTP
  (`if self.tvtp: params1[...] = params0[...]`). Verified empirically: one EM
  iteration moves the transition block by exactly 0.0. The whole block
  therefore comes from `start_params` plus one numerical pass.
* The likelihood is 25–50x flatter toward the absorbing boundary than away from
  it, so that single pass can drift to `P(tranquil|stressed) ~ 1.8e-9`.
* On a 2005–2022 fold the fitted full model scored 207 log-likelihood **below**
  its own nested intercept-only special case (LR = −414.55), which is impossible
  at a true maximum.
* Several apparently-better restarts were **non-converged** — selecting on
  likelihood alone would have picked one.

Synthetic data throughout: these guard the estimation machinery, not the NSE
result. Real-corpus causal validation is a separate, currently-blocked step.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from seraph.orchestration.hamilton_causal import (
    CausalRun,
    RefitBlock,
    assert_causal,
    causal_tvtp_exog,
)
from seraph.pillars.hamilton.engine import (
    K_REGIMES,
    MultivariateTVTPHamilton,
    fit as fit_hamilton,
)

_N = 600


def _synthetic(seed: int = 0):
    """Three-variable series with a genuine, recoverable regime structure."""
    rng = np.random.default_rng(seed)
    mu = np.array([[0.50, 0.40, 0.005],
                   [0.70, 0.46, 0.007],
                   [0.95, 0.52, 0.010]])
    sd = np.array([0.05, 0.03, 0.0008])
    y, s = np.zeros((_N, 3)), 0
    for t in range(_N):
        if rng.random() < 0.03:
            s = int(rng.integers(0, K_REGIMES))
        y[t] = mu[s] + rng.normal(0, sd)
    return y


def _converged(res) -> bool:
    rv = getattr(res, "mle_retvals", None)
    return bool(rv.get("converged", True)) if isinstance(rv, dict) else True


def _transition(model, params, t):
    p = np.asarray(model.regime_transition_matrix(params))
    return p[:, :, t] if p.ndim == 3 else p


@pytest.fixture(scope="module")
def fitted():
    y = _synthetic()
    exog = causal_tvtp_exog(y[:, 0])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res, order, _ = fit_hamilton(y, exog_tvtp=exog, restarts=2)
    model = MultivariateTVTPHamilton(y, exog_tvtp=exog, k_regimes=K_REGIMES)
    return y, exog, res, order, model


def test_multistart_returns_a_converged_fit(fitted):
    """A non-converged restart must never win model selection.

    It is not enough to take the highest likelihood: during the diagnostic,
    restarts reporting +48 and +881 llf over the default were **not converged**,
    and an earlier analysis of mine wrongly cited them as better optima.
    """
    _, _, res, _, _ = fitted
    assert _converged(res), (
        "fit() returned a non-converged result; selection must be restricted "
        "to converged restarts"
    )
    assert np.isfinite(res.llf)


def test_fitted_solution_is_a_local_maximum(fitted):
    """No small perturbation of the transition block may raise the likelihood.

    This is the check that distinguishes 'the optimiser found the MLE' from
    'the optimiser stopped somewhere'. It is done inside a single model, so it
    cannot be confounded by comparing two separate optimisations.
    """
    _, _, res, _, model = fitted
    rng = np.random.default_rng(3)
    base = np.asarray(res.params, dtype=float)
    idx = np.arange(len(base))[model.parameters["regime_transition"]]
    ll0 = float(res.llf)

    improved = 0
    for _ in range(40):
        trial = base.copy()
        trial[idx] = base[idx] + rng.normal(0, 0.25, size=idx.size)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                ll = float(model.loglike(trial))
            except (ValueError, np.linalg.LinAlgError):
                continue
        if np.isfinite(ll) and ll > ll0 + 1e-6:
            improved += 1
    assert improved == 0, (
        f"{improved}/40 perturbations raised the likelihood — the reported fit "
        f"is not at a maximum"
    )


def test_nesting_invariant_full_tvtp_beats_its_own_restriction(fitted):
    """LL(full TVTP) >= LL(intercept-only), because the latter is nested.

    Setting every slope to zero turns the full model into the intercept-only
    model, so the full model can never legitimately score lower. A negative
    likelihood ratio is arithmetically impossible at a true maximum and is
    exactly how the fold-3 optimiser failure was caught.
    """
    y, exog, res, _, _ = fitted
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res_i, _, _ = fit_hamilton(y, exog_tvtp=exog[:, :1], restarts=2)
    lr = 2.0 * (float(res.llf) - float(res_i.llf))
    assert lr >= -1e-6, (
        f"NESTING VIOLATED: full TVTP llf={res.llf:.2f} is below its nested "
        f"intercept-only case llf={res_i.llf:.2f} (LR={lr:.2f}). The full fit "
        f"is not at its own maximum."
    )


def test_boundary_transitions_are_detectable(fitted):
    """A near-absorbing solution must be observable, not silently accepted.

    No floor is imposed — the guard only asserts the check is computable and
    reports on the fitted solution, so a boundary result would be flagged
    rather than hidden.
    """
    _, _, res, order, model = fitted
    a = _transition(model, res.params, model.nobs // 2)[np.ix_(order, order)]
    off = a + np.eye(K_REGIMES)          # mask the diagonal
    assert np.isfinite(a).all()
    assert np.allclose(a.sum(axis=0), 1.0, atol=1e-6), "columns must be a simplex"
    # informational: recorded so a boundary solution is visible in test output
    print(f"\n[boundary] min off-diagonal transition = {off.min():.3e}")


def test_production_path_uses_filtered_not_smoothed():
    """`probabilities="filtered"` must select P(S_t | y_1..y_t).

    The smoothed series runs the Kim smoother backward over the whole sample,
    so xi_t depends on observations after t. It stays available for in-sample
    description and must never back a live or replay claim.
    """
    from seraph.pillars.hamilton.engine import HamiltonEngine

    y = _synthetic(1)
    dates = [f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(_N)]
    exog = causal_tvtp_exog(y[:, 0])

    eng = HamiltonEngine(dates, y, exog_tvtp=exog)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = eng.fit(probabilities="filtered")
    assert res.status == "ok"
    assert res.value["probabilities"] == "filtered"
    assert eng._probabilities == "filtered"

    with pytest.raises(ValueError):
        eng.fit(probabilities="smoothed_and_filtered")   # typo must not pass


def test_future_observations_cannot_enter_a_refit_window():
    """`assert_causal` must reject any block whose parameters saw its own
    emission window — the invariant the walk-forward exists to provide."""
    ok_block = RefitBlock(
        index=0, train_start=0, train_end=100, emit_start=100, emit_end=150,
        train_first_date="2005-01-03", train_last_date="2009-12-31",
        emit_first_date="2010-01-01", emit_last_date="2010-06-30",
        llf=1.0, order=(0, 1, 2), converged=True,
    )
    assert_causal(CausalRun(xi=np.zeros((K_REGIMES, 150)), blocks=[ok_block]))

    leaky = RefitBlock(
        index=0, train_start=0, train_end=120, emit_start=100, emit_end=150,
        train_first_date="2005-01-03", train_last_date="2010-03-31",
        emit_first_date="2010-01-01", emit_last_date="2010-06-30",
        llf=1.0, order=(0, 1, 2), converged=True,
    )
    with pytest.raises(AssertionError, match="future data reached the fit"):
        assert_causal(CausalRun(xi=np.zeros((K_REGIMES, 150)), blocks=[leaky]))


def test_causal_exog_uses_no_future_moments():
    """The FR21 driver must standardise with expanding, not full-sample, moments.

    `scripts/fit_hamilton.py` used `(rv - rv.mean()) / rv.std()` over the whole
    corpus, so the z-score at date t embedded moments computed from data after
    t — a third leakage path independent of the smoother and the parameter fit.
    """
    rv = np.arange(1.0, 401.0)                    # strictly increasing
    x = causal_tvtp_exog(rv, warmup=10)
    assert x.shape == (400, 2)
    assert np.allclose(x[:, 0], 1.0)              # intercept column
    assert x[0, 1] == 0.0                         # lag has no t-1 at t=0

    # truncating the series must not change any earlier value: that is exactly
    # what a full-sample mean/sd would violate.
    short = causal_tvtp_exog(rv[:250], warmup=10)
    assert np.allclose(short[:, 1], x[:250, 1], atol=1e-12), (
        "z-score at t changed when later data was removed — the standardisation "
        "is reading the future"
    )
