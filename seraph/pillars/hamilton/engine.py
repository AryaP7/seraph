# C7 — Hamilton Engine (FR20, FR21, FR23, FR24)
"""Multivariate three-state TVTP Hamilton filter on y_t = (RV_t, AR_t, BAS_t)ᵀ.

Why a subclass rather than `MarkovRegression`: AGENTS.md §2 prefers
statsmodels' regime-switching machinery and permits hand-rolling only where it
"genuinely can't express" the spec. `MarkovRegression` / `MarkovAutoregression`
are **univariate** in the endogenous variable, and FR20 is explicitly
multivariate. The base `MarkovSwitching` class, however, already implements the
Hamilton filter, the Kim smoother, and — critically — FR21's multinomial-logit
time-varying transition matrix via `exog_tvtp`. Only the emission density is
missing, and that is exactly the `_conditional_loglikelihoods` hook. So the
filter, the TVTP construction and the optimiser wiring are all statsmodels';
this module supplies the multivariate Gaussian likelihood and the regime
ordering on top.

Emission covariance is **diagonal** (per-regime variances, one per component
of y_t). With three regimes and three components that is 18 emission
parameters plus the TVTP block; a full covariance would add nine more and, at
the sample sizes involved, tends to drive EM into degenerate solutions. The
restriction is a modelling choice and must be stated in the report — the three
components are not assumed independent in reality, only conditionally on the
regime.

Regimes are relabelled after estimation so that regime 1 = tranquil,
2 = stressed, 3 = crisis, ordered by fitted mean realised volatility. SPEC O4's
acceptance criterion ("non-degenerate three-regime solution with ordered
means") is checked and reported rather than assumed.
"""
from __future__ import annotations

import warnings

import numpy as np
from statsmodels.tsa.regime_switching.markov_switching import MarkovSwitching

from seraph.shared_types import (
    Err,
    EstimationDiverged,
    HamiltonDetail,
    InsufficientHistory,
    Ok,
    PillarEmission,
    PillarObservation,
    SeraphWarning,
    UnavailableEmission,
    err,
    ok,
)

#: y_t component order — fixed, and mirrored by ObservationRow (S4).
ENDOG_ORDER = ("rv", "ar", "bas")
K_REGIMES = 3
_MIN_OBS = 250              # roughly one trading year; below this EM is unidentified
_VAR_FLOOR = 1e-12
#: Per-regime variance floor as a fraction of each y_t component's sample
#: variance. Prevents the unbounded-likelihood degeneracy described in
#: MultivariateTVTPHamilton.__init__; 1% is small enough not to bias a
#: genuinely tight regime, large enough to stop a collapse onto one point.
VAR_FLOOR_FRACTION = 0.01


class MultivariateTVTPHamilton(MarkovSwitching):
    """Three-state Gaussian HMM with diagonal covariance and TVTP transitions."""

    def __init__(self, y, exog_tvtp=None, k_regimes: int = K_REGIMES):
        y = np.asarray(y, dtype=float)
        if y.ndim != 2:
            raise ValueError(f"y must be (nobs, k_endog); got shape {y.shape}")
        self.y_multi = y
        self.k_endog_multi = y.shape[1]
        # Data-scaled variance floor. A Gaussian mixture likelihood is UNBOUNDED:
        # a component can shrink its variance to zero around a single
        # observation and drive the likelihood to infinity. With an absolute
        # floor (1e-12) that is exactly what happened on the real 5,365-day
        # series - two regimes collapsed onto single points and the third
        # absorbed 100% of the sample, making regime detection vacuous. Flooring
        # each component's variance at a fixed fraction of that component's
        # total sample variance is the standard remedy and keeps the estimator
        # scale-free.
        self._var_floor = np.maximum(
            VAR_FLOOR_FRACTION * y.var(axis=0), _VAR_FLOOR)
        # The base class is univariate in `endog`; it uses it only for nobs and
        # bookkeeping, since we override the emission density entirely.
        super().__init__(y[:, 0], k_regimes, order=0, exog_tvtp=exog_tvtp)
        self.parameters["means"] = [1] * self.k_endog_multi
        self.parameters["variances"] = [1] * self.k_endog_multi
        # Uniform known initial regime distribution rather than the steady
        # state. statsmodels defaults to solving for the ergodic distribution
        # of the transition matrix, which raises "Steady-state probabilities
        # could not be constructed" whenever the optimiser steps through a
        # near-reducible matrix — a routine occurrence mid-search. Over a
        # multi-year sample the t=0 prior is immaterial, so the neutral choice
        # is also the numerically robust one.
        self.initialize_known(np.full(k_regimes, 1.0 / k_regimes))

    # --- parameter plumbing ------------------------------------------------

    @property
    def start_params(self):
        params = np.zeros(self.k_params, dtype=float)
        params[self.parameters["regime_transition"]] = (
            0.0 if self.tvtp else 1.0 / self.k_regimes
        )
        if not self.tvtp:
            # Persistent-by-default start: strong diagonal, spread elsewhere.
            base = np.full((self.k_regimes - 1, self.k_regimes), 0.1)
            np.fill_diagonal(base, 0.8)
            params[self.parameters["regime_transition"]] = base.ravel()

        # Seed regimes by terciles of the first component (realised volatility):
        # a low-, mid- and high-volatility partition of the sample.
        order = np.argsort(self.y_multi[:, 0])
        chunks = np.array_split(order, self.k_regimes)
        for j, idx in enumerate(chunks):
            block = self.y_multi[idx]
            params[self.parameters[j, "means"]] = block.mean(axis=0)
            params[self.parameters[j, "variances"]] = np.maximum(
                block.var(axis=0), self._var_floor
            )
        return params

    def transform_params(self, unconstrained):
        constrained = super().transform_params(unconstrained)
        for j in range(self.k_regimes):
            sl = self.parameters[j, "variances"]
            constrained[sl] = constrained[sl] ** 2 + _VAR_FLOOR
        return constrained

    def untransform_params(self, constrained):
        """Analytic inverse of the transition logistic, plus the variance map.

        The base class reverses its own logistic transform with a numerical
        root-find (`scipy.optimize.root`), which fails outright for k_regimes=3
        at perfectly ordinary starting values and raises "Could not untransform
        parameters". The transform is a plain multinomial logit —
        p_j = e^{u_j} / (1 + Σ e^{u}) with the last regime as baseline — so its
        inverse u_j = log(p_j / p_baseline) is closed-form. Using it removes
        the failure mode entirely rather than working around it.
        """
        constrained = np.asarray(constrained, dtype=float)
        unconstrained = np.array(constrained, copy=True)
        if not self.tvtp:
            for i in range(self.k_regimes):
                sl = self.parameters[i, "regime_transition"]
                p = np.clip(np.asarray(constrained[sl], dtype=float), 1e-8, 1 - 1e-8)
                baseline = max(1.0 - float(p.sum()), 1e-8)
                unconstrained[sl] = np.log(p / baseline)
        for j in range(self.k_regimes):
            sl = self.parameters[j, "variances"]
            unconstrained[sl] = np.sqrt(
                np.maximum(np.asarray(constrained[sl], dtype=float) - _VAR_FLOOR, 0.0)
            )
        return unconstrained

    def _em_iteration(self, params0):
        """Gaussian M-step for the emission parameters.

        The base class's EM allocates a fresh zero vector and fills in only the
        transition block, so any parameter it does not own — here every mean
        and variance — is silently zeroed on the first EM pass, destroying the
        starting values and driving the fit to a degenerate solution.
        `MarkovRegression` overrides this hook for the same reason. The update
        below is the standard weighted M-step, with the smoothed regime
        probabilities as weights.
        """
        result, params1 = super()._em_iteration(params0)
        smoothed = np.asarray(result.smoothed_marginal_probabilities, dtype=float)
        if smoothed.shape[0] != self.k_regimes:
            smoothed = smoothed.T

        for j in range(self.k_regimes):
            w = smoothed[j]
            w_sum = float(w.sum())
            if w_sum <= 1e-12:
                # An empty regime carries no information this pass; hold its
                # previous values rather than dividing by ~0.
                params1[self.parameters[j, "means"]] = params0[self.parameters[j, "means"]]
                params1[self.parameters[j, "variances"]] = params0[
                    self.parameters[j, "variances"]
                ]
                continue
            mean = (w[:, None] * self.y_multi).sum(axis=0) / w_sum
            var = (w[:, None] * (self.y_multi - mean) ** 2).sum(axis=0) / w_sum
            params1[self.parameters[j, "means"]] = mean
            params1[self.parameters[j, "variances"]] = np.maximum(var, self._var_floor)
        return result, params1

    # --- the emission density (the whole point of the subclass) ------------

    def _conditional_loglikelihoods(self, params):
        """(k_regimes, k_regimes, nobs) log densities of a diagonal MV normal.

        Axis 0 is `S_t`; axis 1 is `S_{t-1}` and is a constant broadcast,
        because a Gaussian emission depends only on the current regime.

        **That second axis is not decoration — omitting it silently breaks EM.**
        statsmodels infers the filter order from the array it gets back,
        `order = conditional_loglikelihoods.ndim - 2` (markov_switching.py,
        `cy_kim_smoother_log` caller). Returning the apparently natural
        `(k_regimes, nobs)` therefore makes it infer order 0 instead of 1 and
        allocate `smoothed_joint_probabilities` as `(k_regimes, nobs)` — the
        marginals, not the joint. `_em_regime_transition` then evaluates

            regime_transition[i, j] = sum(joint[j, i]) / sum(marginal[i])

        where `joint[j, i]` was meant to select the time series of
        `P(S_t = j, S_{t-1} = i)` but instead selects the **scalar** smoothed
        probability of regime `j` on day `i`. The EM step consequently writes a
        transition matrix built from three arbitrary single-day numbers, and
        since `MarkovSwitching.fit` runs `em_iter=5` of these *before* handing
        over to BFGS, every fit started from a degenerate transition block.

        Measured cost of the omission, on a synthetic 3-regime series with known
        parameters (5,365 days, Markov-generated at the real corpus's scale):

            variant   llf          occupancy      path accuracy
            (k,nobs)  36,478.9     0% / 0% / 100%        0.1871
            (k,k,nobs) 53,052.6    47% / 34% / 19%       0.9998
            truth      53,041.4    47% / 34% / 19%       1.0

        The broken variant lands **16,573 log-likelihood below the true
        parameter point even when handed that point as its starting value** —
        the signature of a corrupted iteration, not a flat likelihood. The fixed
        variant recovers the generating transition diagonal
        (0.9751/0.9498/0.9511 against a true 0.975/0.950/0.950).

        The emission density itself is unchanged. `loglike()` at fixed
        parameters differs between the two shapes by a **single fixed
        initialisation term of 0.009754 nats** — measured constant to six
        decimals across n = 300, 600, 1,200, 2,400, 5,000, 10,000 and 20,000,
        so it is the t=0 boundary condition and not a per-observation
        difference (relative gap 3.1e-06 at n=300 falling to 4.6e-08 at
        n=20,000). Set that against the 16,573-nat optimisation gain above.

        So the filter and Kim smoother always marginalised correctly over the
        broadcast axis: inference was right and only the EM pre-step was wrong.
        That is why this survived five observation designs undetected — the
        likelihood was never the thing that was broken.

        The dtype must follow `params`, not be pinned to float: statsmodels
        differentiates the likelihood by the complex-step method, so it calls
        this with complex parameters and its Cython filter then demands a
        complex buffer back. Hard-coding float raises "Buffer dtype mismatch,
        expected 'double complex'". Everything below therefore stays
        holomorphic — no clipping or maxima on a possibly-complex array;
        positivity of the variance is already guaranteed by transform_params.
        """
        params = np.asarray(params)
        dtype = np.promote_types(np.float64, params.dtype)
        nobs = self.y_multi.shape[0]
        k = self.k_regimes
        out = np.zeros((k, k, nobs), dtype=dtype)
        for j in range(k):
            mean = np.asarray(params[self.parameters[j, "means"]], dtype=dtype)
            var = np.asarray(params[self.parameters[j, "variances"]], dtype=dtype)
            if not np.iscomplexobj(var):
                var = np.maximum(var, self._var_floor)
            resid = self.y_multi.astype(dtype) - mean
            # density of y_t under regime j, broadcast across the S_{t-1} axis
            out[j, :, :] = (-0.5 * np.sum(
                np.log(2.0 * np.pi * var) + resid**2 / var, axis=1
            ))[None, :]
        return out


def _half_life(p_jj: float) -> float:
    """FR24 — τ_{1/2} = ln(2)/(1 − p̂_jj). A perfectly absorbing regime has an
    infinite half-life; report it as inf rather than dividing by zero."""
    denom = 1.0 - float(p_jj)
    return float("inf") if denom <= 1e-12 else float(np.log(2.0) / denom)


def _tvtp_start_from_constant(model, y, *, k_regimes, maxiter, restarts, seed):
    """FR21 start values taken from the model's own nested special case.

    A TVTP fit is the multinomial logit `p(i|j) = softmax_i(x_t' b_ij)` with
    regime `k-1` as baseline. Setting every **slope** to zero and every
    **intercept** to `log(p_ij / p_kj)` reproduces a constant transition matrix
    exactly — the constant-transition model is a point inside the TVTP
    parameter space, not a different model.

    `MarkovSwitching.start_params` instead sets the whole logit block to 0.0
    under TVTP, which implies a **uniform 1/k transition matrix** — every
    regime half-life 1.04 days, the least persistent matrix available — while
    the data's own constant-transition MLE sits at `p_jj ~ 0.99` (half-lives
    74-462 days). statsmodels also skips EM on the transition block under TVTP
    ("EM with TVTP is not yet supported"), so those `(k-1) * k * k_tvtp`
    coefficients have to be found by BFGS with numerical gradients, starting
    from the worst available point, across a surface that is far flatter toward
    the absorbing boundary than away from it.

    That is the mechanism behind the walk-forward's **6/14 nesting violations**:
    blocks 6-11 reported a full-model likelihood *below* their own nested
    restriction, by LR -577 to -2,322.88, which cannot happen at a true
    maximum. Measured on the two ends of that range:

        block  default start   warm start      nested MLE
        6      29,988.87 (X)   30,017.71 (ok)  29,994.26
        11     41,882.55 (ok)  41,883.80 (ok)  41,866.68

    Starting at the restricted optimum makes `llf_full >= llf_restricted` hold
    by construction, since BFGS can only improve on its own start point.

    This adds a *candidate start*. It does not floor a parameter, change the
    regime count, add a covariate, or alter the likelihood — `fit()` still
    selects among starts on converged likelihood alone, so a block where the
    default start is better (block 0: 16,677.68 against the warm start's
    16,674.87) keeps the default. Returns `None` if the nested fit fails, so a
    failure here can never cost more than the pre-existing behaviour.

    Cost: one extra constant-transition fit plus one extra TVTP fit per call.
    """
    try:
        res_c, _, _ = fit(y, exog_tvtp=None, maxiter=maxiter,
                          k_regimes=k_regimes, restarts=restarts, seed=seed)
    except (np.linalg.LinAlgError, ValueError, RuntimeError):
        return None
    mc = res_c.model
    p_const = np.asarray(mc.regime_transition_matrix(res_c.params))[:, :, 0]
    warm = np.zeros(model.k_params, dtype=float)
    for j in range(k_regimes):
        warm[model.parameters[j, "means"]] = res_c.params[mc.parameters[j, "means"]]
        warm[model.parameters[j, "variances"]] = res_c.params[
            mc.parameters[j, "variances"]]
    # statsmodels TVTP layout: for each FROM-regime j, a contiguous
    # (k_regimes - 1, k_tvtp) block raveled as [to_regime, exog_column].
    for j_from in range(k_regimes):
        baseline = max(float(p_const[k_regimes - 1, j_from]), 1e-8)
        coef = np.zeros((k_regimes - 1, model.k_tvtp), dtype=float)
        for i_to in range(k_regimes - 1):
            coef[i_to, 0] = np.log(
                max(float(p_const[i_to, j_from]), 1e-8) / baseline)
        warm[model.parameters[j_from, "regime_transition"]] = coef.ravel()
    return warm


def _tvtp_start_from_intercept_only(model, y, *, k_regimes, maxiter, restarts,
                                    seed):
    """The same warm start, but built from the restriction's OWN parameterisation.

    `_tvtp_start_from_constant` fits the restricted model through the
    **non-TVTP** code path (`exog_tvtp=None`, tercile-seeded `start_params`,
    EM on the emission block). The nesting check in
    `stage2_nesting_and_truncation.py` instead fits it as **TVTP with an
    intercept-only exog** — the same model mathematically, reached by a
    different optimisation. They do not agree, and on the real corpus the gap is
    large: on block 6 the non-TVTP path reaches 29,994.26 while the
    intercept-only path reaches 30,306.30, a **312 log-likelihood** spread
    between two optimisations of one restricted model.

    That gap is what left 4 of 14 blocks still violating nesting after the first
    warm start: blocks 6, 8, 10 were seeded from the weaker of the two optima,
    so the full fit had nothing to beat the restricted fit with.

    Seeding from the intercept-only fit closes it by construction, because that
    *is* the model the LR is computed against: with the slopes at zero the start
    point reproduces the restricted optimum exactly, and BFGS can only improve
    on its own start. Both candidates are offered and `fit()` still selects on
    converged likelihood alone, so whichever restricted optimum is better wins.
    """
    n = np.asarray(y, dtype=float).shape[0]
    try:
        res_r, _, _ = fit(y, exog_tvtp=np.ones((n, 1)), maxiter=maxiter,
                          k_regimes=k_regimes, restarts=restarts, seed=seed)
    except (np.linalg.LinAlgError, ValueError, RuntimeError):
        return None
    mr = res_r.model
    warm = np.zeros(model.k_params, dtype=float)
    for j in range(k_regimes):
        warm[model.parameters[j, "means"]] = res_r.params[mr.parameters[j, "means"]]
        warm[model.parameters[j, "variances"]] = res_r.params[
            mr.parameters[j, "variances"]]
    for j_from in range(k_regimes):
        # restricted slice is (k-1, 1) — one intercept per destination regime;
        # the full slice is (k-1, k_tvtp) raveled as [to_regime, exog_column].
        inter = np.asarray(res_r.params[mr.parameters[j_from, "regime_transition"]],
                           dtype=float).ravel()
        coef = np.zeros((k_regimes - 1, model.k_tvtp), dtype=float)
        coef[:, 0] = inter[: k_regimes - 1]
        warm[model.parameters[j_from, "regime_transition"]] = coef.ravel()
    return warm


def fit(
    y,
    *,
    exog_tvtp=None,
    maxiter: int = 200,
    k_regimes: int = K_REGIMES,
    restarts: int = 4,
    seed: int = 0,
):
    """Estimate the filter and return (results, order, warnings).

    `order` maps sorted regime index → fitted regime index, so that index 0 is
    the lowest-volatility (tranquil) regime and index 2 the highest (crisis).
    """
    y = np.asarray(y, dtype=float)
    model = MultivariateTVTPHamilton(y, exog_tvtp=exog_tvtp, k_regimes=k_regimes)

    # --- multi-start over the transition block ---------------------------
    # statsmodels does NOT run its EM step on transition parameters under
    # TVTP (`if self.tvtp: params1[...] = params0[...]`, "EM with TVTP is not
    # yet supported"). Verified empirically: one EM iteration moves the
    # transition block by exactly 0.0 while emission means move ~2.2e-3. So
    # the entire transition block comes from `start_params` — all zeros — plus
    # one numerical pass, and the likelihood is 25-50x flatter toward the
    # absorbing boundary than away from it. That combination let the optimiser
    # drift to P(tranquil|stressed) ~ 1.8e-9 on short samples.
    #
    # The failure is demonstrable, not inferred: on a 2005-2022 fold the fitted
    # full model scored 207 log-likelihood BELOW its own nested intercept-only
    # special case (LR = -414.55), which is impossible at a true maximum.
    #
    # This changes no model, no regime count, no covariate and imposes no
    # transition floor. It only makes the optimiser actually maximise the
    # likelihood FR20/FR21 already specify, and selects on likelihood alone.
    def _converged(r):
        rv = getattr(r, "mle_retvals", None)
        return bool(rv.get("converged", True)) if isinstance(rv, dict) else True

    sp0 = np.asarray(model.start_params, dtype=float)
    tr = model.parameters["regime_transition"]
    starts = [None]                              # statsmodels' own default
    rng = np.random.default_rng(seed)
    for k in range(max(0, int(restarts))):
        sp = sp0.copy()
        # bounded draws: the logit block saturates well before |2|, so a wider
        # spread only wastes fits on degenerate corners
        sp[tr] = rng.uniform(-2.0, 2.0, size=np.asarray(sp0)[tr].size)
        starts.append(sp)
    if model.tvtp:
        # The nested restricted optimum, mapped into the TVTP logit block, from
        # BOTH parameterisations of that restriction — see
        # _tvtp_start_from_constant for why the default start is a uniform 1/k
        # matrix, and _tvtp_start_from_intercept_only for why one source is not
        # enough. The `model.k_tvtp > 1` test guards the recursion: the
        # intercept-only fit is itself a TVTP fit, but with a single exog column,
        # so it takes the constant warm start and never seeds itself.
        warm = _tvtp_start_from_constant(
            model, y, k_regimes=k_regimes, maxiter=maxiter,
            restarts=restarts, seed=seed)
        if warm is not None:
            starts.append(warm)
        if model.k_tvtp > 1:
            warm2 = _tvtp_start_from_intercept_only(
                model, y, k_regimes=k_regimes, maxiter=maxiter,
                restarts=restarts, seed=seed)
            if warm2 is not None:
                starts.append(warm2)

    res, best_ll, tried, ok_n = None, -np.inf, 0, 0
    best_unconverged = -np.inf
    for sp in starts:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cand = model.fit(start_params=sp, maxiter=maxiter, disp=False)
        except (np.linalg.LinAlgError, ValueError, RuntimeError):
            continue
        tried += 1
        # A non-converged fit can report a HIGHER llf than a converged one and
        # is not a valid optimum — selecting on likelihood alone would pick it.
        if not _converged(cand):
            best_unconverged = max(best_unconverged, float(cand.llf))
            continue
        ok_n += 1
        if float(cand.llf) > best_ll:
            best_ll, res = float(cand.llf), cand
    if res is None:                              # nothing converged; fall back
        with warnings.catch_warnings():          # so the caller still gets a
            warnings.simplefilter("ignore")      # result rather than a crash
            res = model.fit(maxiter=maxiter, disp=False)

    rv_means = np.array([
        res.params[model.parameters[j, "means"]][0] for j in range(k_regimes)
    ])
    order = np.argsort(rv_means)          # ascending RV: tranquil → crisis

    notes: list[SeraphWarning] = []
    # Converged-only selection is the right rule — a non-converged point is not
    # a valid optimum — but it can discard a much higher likelihood **silently**,
    # and that is what hid a real problem on walk-forward block 11: both the
    # default and the warm start reached ~41,883 without satisfying BFGS's
    # convergence test, so the engine returned a converged candidate 1,178 llf
    # lower, which then sat below its own nested restriction. The rule is kept;
    # the condition is now visible. A large gap here means the convergence test
    # is failing on a flat surface, not that the discarded point was wrong.
    if np.isfinite(best_unconverged) and best_unconverged > best_ll + 1.0:
        notes.append(SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=(
                f"a non-converged start reached llf {best_unconverged:.2f}, "
                f"{best_unconverged - best_ll:.2f} above the selected converged "
                f"fit ({best_ll:.2f}); the reported optimum may be a local one"
            ),
            context={"discardedLlf": round(best_unconverged, 4),
                     "selectedLlf": round(best_ll, 4),
                     "convergedStarts": ok_n, "triedStarts": tried},
        ))
    sep = float(rv_means[order[-1]] - rv_means[order[0]])
    rv_sd = float(np.sqrt(np.mean([
        res.params[model.parameters[j, "variances"]][0] for j in range(k_regimes)
    ])))
    # NFR17 asks for >= 3σ separation between the crisis and tranquil RV means.
    if rv_sd > 0 and sep < 3.0 * rv_sd:
        notes.append(SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=(
                f"crisis/tranquil RV separation is {sep / rv_sd:.2f} sigma, below "
                f"NFR17's 3-sigma target — regimes may be weakly identified"
            ),
            context={"separationSigma": round(sep / rv_sd, 3)},
        ))
    return res, order, notes


class HamiltonEngine:
    """S5 — Pillar 3. Emits LSD_t at daily cadence with FR23 uncertainty.

    The engine is fitted once over the estimation sample and then reads
    smoothed regime probabilities per date; `emit` never refits, so repeated
    emission is cheap and deterministic.
    """

    pillar = "hamilton"

    def __init__(self, dates, y, exog_tvtp=None):
        self.dates = tuple(dates)
        self.y = np.asarray(y, dtype=float)
        self.exog_tvtp = None if exog_tvtp is None else np.asarray(exog_tvtp, float)
        self._res = None
        self._order = None
        self._xi = None
        self._notes: tuple[SeraphWarning, ...] = ()
        self._index = {d: i for i, d in enumerate(self.dates)}
        #: Which probability series `fit()` cached — "smoothed" (in-sample,
        #: NON-CAUSAL) or "filtered" (causal). Consumers must not mix them.
        self._probabilities = "smoothed"

    def fit(self, *, probabilities: str = "smoothed") -> Ok[dict] | Err:
        """Fit once and cache the per-date regime probabilities.

        `probabilities` selects which of the two series statsmodels already
        computes from the *same* fit is read — no estimator behaviour changes:

        * `"smoothed"` — `P(S_t | y_1..y_T)`. The Kim smoother runs backward
          over the whole sample, so `ξ_t` depends on observations **after** `t`.
          This is a legitimate in-sample descriptive quantity and is what the
          existing E8 series and the 43/25/32 occupancy figures were produced
          with. It is **NOT causal** and must never back a live or replay claim.
        * `"filtered"` — `P(S_t | y_1..y_t)`. Uses no future observation and is
          the correct choice for the production path.

        Selecting `"filtered"` removes only the *smoother* leak. Parameters are
        still estimated over whatever sample this engine was handed, so a fully
        causal series additionally requires walk-forward refitting — see
        `seraph.orchestration.hamilton_causal`.
        """
        if probabilities not in ("smoothed", "filtered"):
            raise ValueError(
                f"probabilities must be 'smoothed' or 'filtered', got {probabilities!r}")
        if len(self.dates) < _MIN_OBS:
            return err(InsufficientHistory(
                required=_MIN_OBS,
                available=len(self.dates),
                as_of=self.dates[-1] if self.dates else "1970-01-01",
            ))
        try:
            res, order, notes = fit(self.y, exog_tvtp=self.exog_tvtp)
        except (np.linalg.LinAlgError, ValueError, RuntimeError) as e:
            return err(EstimationDiverged(
                estimator="MultivariateTVTPHamilton",
                iterations=0,
                last_objective=float("nan"),
            ))
        self._res = res
        self._order = order
        self._notes = tuple(notes)
        # Reordered to [tranquil, stressed, crisis].
        raw = (res.filtered_marginal_probabilities if probabilities == "filtered"
               else res.smoothed_marginal_probabilities)
        probs = np.asarray(raw)
        if probs.shape[0] != K_REGIMES:
            probs = probs.T
        # The filtered series can carry one extra column (the one-step-ahead
        # prediction past the sample end); keep it aligned to `dates`.
        if probs.shape[1] > len(self.dates):
            probs = probs[:, : len(self.dates)]
        self._xi = probs[order, :]
        self._probabilities = probabilities
        return ok(
            {"llf": float(res.llf), "order": [int(o) for o in order],
             "probabilities": probabilities},
            self._notes,
        )

    def _detail_at(self, i: int) -> HamiltonDetail:
        xi_raw = self._xi[:, i]
        total = float(xi_raw.sum())
        xi = tuple(float(v / total) for v in xi_raw) if total > 0 else (1 / 3, 1 / 3, 1 / 3)
        # Renormalise the last element so the Simplex3 validator sees an exact sum.
        xi = (xi[0], xi[1], max(0.0, 1.0 - xi[0] - xi[1]))

        trans = np.asarray(self._res.model.regime_transition_matrix(self._res.params))
        # (k, k, 1) when constant, (k, k, nobs) under TVTP.
        mat = trans[:, :, min(i, trans.shape[2] - 1)]
        o = self._order
        p22 = float(mat[o[1], o[1]])
        p33 = float(mat[o[2], o[2]])
        return HamiltonDetail(
            xi=xi,
            p_hat_22=p22,
            p_hat_33=p33,
            tau_half_stressed=_half_life(p22),
            tau_half_crisis=_half_life(p33),
        )

    def emit(self, date: str, ts: str | None = None) -> Ok[PillarEmission] | Err:
        """FR23 — LSD_t = ξ_2 + 2ξ_3, with per-update estimation uncertainty."""
        stamp = ts or f"{date}T15:30:00+05:30"
        if self._xi is None:
            fitted = self.fit()
            if fitted.status == "error":
                return fitted
        i = self._index.get(date)
        if i is None:
            # Outside the estimation sample: structurally absent, never an error.
            return ok(UnavailableEmission(
                pillar="hamilton", ts=stamp,
                absence="structural", reason="no_data_coverage",
            ), self._notes)

        detail = self._detail_at(i)
        lsd = detail.xi[1] + 2.0 * detail.xi[2]
        # FR23's uncertainty: posterior variance of the regime label under ξ,
        # scaled to LSD's own 0..3 range via the (0,1,2) weights.
        weights = np.array([0.0, 1.0, 2.0])
        xi_vec = np.array(detail.xi)
        variance = float((weights**2 * xi_vec).sum() - lsd**2)
        return ok(_observed(stamp, lsd, max(variance, 0.0)), self._notes)

    def emit_range(self, dates) -> Ok[tuple] | Err:
        out = []
        for d in dates:
            res = self.emit(d)
            if res.status == "error":
                return res
            out.append(res.value)
        return ok(tuple(out), self._notes)

    def coverage(self) -> Ok[dict] | Err:
        if not self.dates:
            return err(InsufficientHistory(
                required=_MIN_OBS, available=0, as_of="1970-01-01"
            ))
        return ok({
            "from": f"{self.dates[0]}T15:30:00+05:30",
            "to": f"{self.dates[-1]}T15:30:00+05:30",
        })

    def detail(self, date: str) -> HamiltonDetail | None:
        i = self._index.get(date)
        return None if i is None or self._xi is None else self._detail_at(i)


def _observed(ts: str, value: float, variance: float):
    from seraph.shared_types import ObservedEmission

    return ObservedEmission(obs=PillarObservation(
        pillar="hamilton", ts=ts, tau=ts, value=value, estimation_variance=variance
    ))


def project_xi(engine: "HamiltonEngine", z_path, xi0=None):
    """FR48 support — propagate regime probabilities under a hypothetical `z_t`.

    Given a counterfactual covariate path, build the TVTP transition matrix at
    each step from the *fitted* coefficients and push the regime distribution
    forward:  ξ_{t+1} = P(z_t) · ξ_t.

    This lives in C7 rather than C11 deliberately. The mapping from covariates
    to regime probabilities *is* Pillar 3's model; reimplementing it inside the
    decision-support layer would create a second, silently divergent copy of the
    regime dynamics — the same failure CT-7 guards against for scoring. C11
    consumes this as an injected callable, so no dependency edge is added.

    Returns a list of Simplex3 rows, one per step of `z_path`.
    """
    import numpy as _np

    if engine._res is None:
        raise RuntimeError("fit the engine before projecting a policy path")
    z = _np.atleast_2d(_np.asarray(z_path, dtype=float))
    order = engine._order

    xi = (_np.full(K_REGIMES, 1.0 / K_REGIMES) if xi0 is None
          else _np.asarray(xi0, dtype=float)[list(order)])
    xi = xi / xi.sum()

    trans = _np.asarray(
        engine._res.model.regime_transition_matrix(engine._res.params, exog_tvtp=z)
    )
    out = []
    for i in range(z.shape[0]):
        mat = trans[:, :, min(i, trans.shape[2] - 1)]
        xi = mat @ xi                      # left-stochastic: columns sum to 1
        total = float(xi.sum())
        xi = xi / total if total > 0 else _np.full(K_REGIMES, 1.0 / K_REGIMES)
        ordered = xi[list(order)]
        a, b = float(ordered[0]), float(ordered[1])
        out.append((a, b, max(0.0, 1.0 - a - b)))
    return out
