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
        """(k_regimes, nobs) log densities of a diagonal multivariate normal.

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
        out = np.zeros((self.k_regimes, nobs), dtype=dtype)
        for j in range(self.k_regimes):
            mean = np.asarray(params[self.parameters[j, "means"]], dtype=dtype)
            var = np.asarray(params[self.parameters[j, "variances"]], dtype=dtype)
            if not np.iscomplexobj(var):
                var = np.maximum(var, self._var_floor)
            resid = self.y_multi.astype(dtype) - mean
            out[j] = -0.5 * np.sum(
                np.log(2.0 * np.pi * var) + resid**2 / var, axis=1
            )
        return out


def _half_life(p_jj: float) -> float:
    """FR24 — τ_{1/2} = ln(2)/(1 − p̂_jj). A perfectly absorbing regime has an
    infinite half-life; report it as inf rather than dividing by zero."""
    denom = 1.0 - float(p_jj)
    return float("inf") if denom <= 1e-12 else float(np.log(2.0) / denom)


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

    res, best_ll, tried, ok_n = None, -np.inf, 0, 0
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
