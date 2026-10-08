# C5 - Hawkes Engine (FR10-FR15, as amended by AMENDMENT-03)
"""Discrete-time Hawkes contagion diagnostic on the pooled negative-jump stream.

**What the data supports, and what it does not.** Every statement here is
measured on the full corpus (94 symbols, 18.27M five-minute bars, 21,180
negative jumps); the evidence trail is AMENDMENT-03.

*Rejected - continuous-time pooled Hawkes.* Five-minute binning produces exact
timestamp ties (75.8% of events share a bar; up to 89 simultaneous). With ties
the exponential-kernel likelihood is unbounded in beta: beta pinned to the
ceiling at every bound tested (72 -> 2880) while the branching ratio drifted
0.834 -> 0.752. The estimate is a function of the bound, not of the market, so
this formulation is **misspecified for this data**. It is retained below only as
a reproducible diagnostic and never for reported figures.

*Retained - discrete-time Hawkes at the native resolution.* Modelling whole-bar
counts with a geometric excitation kernel

    lambda_t = mu * ToD(t) + alpha * sum_k phi^(k-1) * N_(t-k)

is well identified, with interior, fold-stable estimates: alpha ~ 0.055,
**phi ~ 0.50** (about a one-bar half-life), branching ratio
**n = alpha/(1-phi) ~ 0.11**, parameter CV ~5% across chronological folds.
Ties are the observation here rather than a degeneracy, and no sub-bar ordering
is invented. This is a genuine Hawkes result and a real component of SERAPH.

*What this component is FOR.* It measures **the current degree of temporal
self-excitation** and contributes that state to the CSRS through C8. Under a
pre-registered de-seasonalised test it showed **approximately no skill**
(PR-AUC 0.085-0.089 against a 0.10 no-skill line) at 15m/30m/1h/2h horizons, so
it is a **contagion / risk-state diagnostic, not a forward alarm**. Nothing here
may be described as forecasting abnormal future risk.

*Related findings.* Negative-binomial count models improve out-of-sample NLL by
~72% but score exactly no skill (Spearman 0.000, ROC 0.500) on forward excess
activity: they characterise the count **distribution**, not the timing.
Cross-sectional synchronisation is a **contemporaneous** market-state measure.
Time-of-day seasonality explains most apparent raw forward predictability and
must be removed before any activity statistic is read as stress.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from seraph.shared_types import (
    ConstraintViolated,
    Err,
    EstimationDiverged,
    HawkesDetail,
    InsufficientHistory,
    Ok,
    SectorFlag,
    SeraphWarning,
    err,
    ok,
)

WINDOW_DAYS = 60             # AMENDMENT-03: rolling estimation window
N_STATES = 9                 # 3x3 coarsening (AMENDMENT-03 §3c)
MIN_EVENTS_PER_STATE = 10    # below this a state's kernel is not estimated
MIN_EVENTS_TOTAL = 50
KERNEL_ORDER_K = 1           # single exponential — see module docstring
#: Bars are 5 minutes, so 1/beta cannot be shorter than the sampling interval:
#: a decay faster than the observation resolution is not identifiable from this
#: data, it is the optimiser exploiting timestamp ties. 5 min = 1/288 day.
BAR_INTERVAL_DAYS = 5.0 / (60.0 * 24.0)
BETA_MAX = 1.0 / BAR_INTERVAL_DAYS          # 288 per day
#: FR14 amber threshold: a sector's realised intensity this many multiples above
#: its own baseline. Uncalibrated (SPEC §8 lists the micro-flag threshold as
#: undefined); FR34 sweeps it.
SECTOR_AMBER_MULTIPLE = 2.0
#: FR13 gate. Measured unconditional downside share of NSE 5-minute jump events:
#: 21,180 negative of 49,783 total. Positive jumps genuinely outnumber negative
#: (z = -33.3 against a symmetric null, p ~ 1.6e-243), and the share is stable
#: across symbols (mean 0.4236, sd 0.055) and sectors (0.402-0.450). Production
#: should re-estimate this per training fold; the constant is the corpus value
#: and a safe default.
DOWNSIDE_BASELINE_SHARE = 0.4254
#: One-sided significance level for the FR13 gate.
ASYMMETRY_ALPHA = 0.05


# =====================================================================
# LEGACY - REJECTED CONTINUOUS-TIME PATH. NOT USED IN PRODUCTION.
#
# Kept deliberately for reproducibility and audit: AMENDMENT-03 section 2 is a
# claim about this code, and deleting it would make that claim unverifiable.
# `scripts/diagnose_jump_process.py` and the regression test
# `test_amendment03_branching_ratio_is_not_identifiable_on_tied_data` both
# exercise it to demonstrate the degeneracy.
#
# Do not call any of the following from the production path. The BETA_MAX
# bound below exists ONLY to keep the legacy diagnostic finite; it is not a
# modelling choice and it is absent from the discrete formulation.
# =====================================================================


@dataclass(frozen=True)
class StateKernel:
    """Fitted kernel for one `S_t` state."""

    state: int
    mu: float
    branching_ratio: float       # n = alpha/beta, invariant: < 1 (FR11)
    beta: float
    n_events: int
    converged: bool

    @property
    def alpha(self) -> float:
        return self.branching_ratio * self.beta


def _neg_loglik(theta: np.ndarray, times: np.ndarray, horizon: float) -> float:
    """Negative log-likelihood of a univariate exponential-kernel Hawkes process.

    Parameterised as theta = (log mu, logit n, log beta) so mu > 0, beta > 0 and
    **0 < n < 1 by construction** — FR11's spectral-radius constraint is
    structural here, not a post-hoc clip that a clipped optimum could sit on.

    Uses the standard O(N) recursion for the compensator and the intensity sum.
    """
    log_mu, logit_n, logit_beta = theta
    mu = np.exp(log_mu)
    n = 1.0 / (1.0 + np.exp(-logit_n))
    # beta is bounded to the observation resolution (see BETA_MAX): pooling
    # across symbols puts many events in the same 5-minute bar, and with exact
    # ties the exponential-kernel likelihood is unbounded as beta -> infinity.
    # Left unbounded the optimiser drives beta to ~1e300 and n to 1, which is a
    # numerical artefact of the tie structure, not measured contagion.
    beta = BETA_MAX / (1.0 + np.exp(-logit_beta))
    alpha = n * beta
    if not np.isfinite(mu) or not np.isfinite(beta) or mu <= 0 or beta <= 0:
        return 1e12

    # Sum of log-intensities, via the recursive state variable.
    r = 0.0
    log_terms = np.log(mu)
    prev = times[0]
    for t in times[1:]:
        r = np.exp(-beta * (t - prev)) * (1.0 + r)
        val = mu + alpha * r
        if val <= 0:
            return 1e12
        log_terms += np.log(val)
        prev = t

    # Compensator: mu*T + (alpha/beta) * sum(1 - exp(-beta (T - t_i)))
    compensator = mu * horizon + n * np.sum(1.0 - np.exp(-beta * (horizon - times)))
    nll = compensator - log_terms
    return float(nll) if np.isfinite(nll) else 1e12


def fit_state_kernel(
    event_times: np.ndarray, horizon: float, state: int = 0
) -> StateKernel | None:
    """MLE for one state's pooled event stream. `event_times` in days, sorted."""
    t = np.asarray(event_times, dtype=float)
    t = t[np.isfinite(t)]
    if t.size < MIN_EVENTS_PER_STATE or horizon <= 0:
        return None
    t = np.sort(t)
    rate0 = max(t.size / horizon, 1e-6)
    best = None
    # A couple of starts: the likelihood is mildly multimodal in (n, beta).
    for n0, beta0 in ((0.3, 5.0), (0.6, 40.0), (0.45, 150.0)):
        b_frac = min(max(beta0 / BETA_MAX, 1e-4), 1 - 1e-4)
        x0 = np.array([
            np.log(rate0 * (1 - n0)), np.log(n0 / (1 - n0)),
            np.log(b_frac / (1 - b_frac)),
        ])
        try:
            res = minimize(
                _neg_loglik, x0, args=(t, horizon), method="Nelder-Mead",
                options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-6},
            )
        except (ValueError, FloatingPointError):
            continue
        if best is None or (res.fun < best.fun):
            best = res
    if best is None:
        return None
    log_mu, logit_n, logit_beta = best.x
    return StateKernel(
        state=state,
        mu=float(np.exp(log_mu)),
        branching_ratio=float(1.0 / (1.0 + np.exp(-logit_n))),
        beta=float(BETA_MAX / (1.0 + np.exp(-logit_beta))),
        n_events=int(t.size),
        converged=bool(best.success),
    )


@dataclass(frozen=True)
class DiscreteHawkes:
    """Fitted discrete-time Hawkes state (AMENDMENT-03 5d)."""

    mu: float
    alpha: float
    phi: float
    dispersion: float
    n_bars: int
    converged: bool

    @property
    def branching_ratio(self) -> float:
        """n = alpha/(1-phi). Stationary iff phi < 1 and n < 1 (FR11)."""
        return float(self.alpha / max(1.0 - self.phi, 1e-9))


def excitation_path(counts, session_starts, mu, alpha, phi, tod_profile, tod_index):
    """lambda_t under the geometric kernel, reset at each session open.

    The reset is to the baseline mu*ToD(t) and NOT to the unconditional mean:
    the unconditional form explodes near the edge of stationarity and lets the
    optimiser fabricate a huge opening intensity - the artefact recorded in
    AMENDMENT-03 section 4.
    """
    counts = np.asarray(counts, dtype=float)
    base = mu * np.asarray(tod_profile)[np.asarray(tod_index)]
    lam = np.empty(counts.size)
    exc = 0.0
    for i in range(counts.size):
        if session_starts[i]:
            exc = 0.0
        lam[i] = base[i] + alpha * exc
        exc = phi * exc + counts[i]
    return lam


def fit_discrete_hawkes(counts, session_starts, tod_profile, tod_index):
    """FR10/FR11 - the retained estimator. Negative-binomial emission.

    Returns None when the sample cannot identify the kernel; callers must treat
    that as `unavailable`, never as a zero contagion reading.
    """
    from scipy.special import gammaln as _g

    x = np.asarray(counts, dtype=float)
    if x.size < MIN_EVENTS_TOTAL or x.sum() <= 0:
        return None
    m = max(float(x.mean()), 1e-6)

    def nll(theta):
        mu, alpha = np.exp(theta[0]), np.exp(theta[1])
        phi = 1.0 / (1.0 + np.exp(-theta[2]))
        k = np.exp(theta[3])
        if alpha / max(1.0 - phi, 1e-9) >= 1.0:      # FR11 stationarity
            return 1e12
        lam = np.maximum(
            excitation_path(x, session_starts, mu, alpha, phi, tod_profile, tod_index),
            1e-12)
        val = -np.sum(_g(x + k) - _g(k) - _g(x + 1)
                      + k * np.log(k / (k + lam)) + x * np.log(lam / (k + lam)))
        return float(val) if np.isfinite(val) else 1e12

    best = None
    for a0, p0 in ((0.05, 0.5), (0.02, 0.2), (0.10, 0.7)):
        x0 = np.array([np.log(m), np.log(a0), np.log(p0 / (1 - p0)), 0.0])
        r = minimize(nll, x0, method="Nelder-Mead", options={"maxiter": 6000})
        if best is None or r.fun < best.fun:
            best = r
    if best is None or best.fun >= 1e12:
        return None
    return DiscreteHawkes(
        mu=float(np.exp(best.x[0])), alpha=float(np.exp(best.x[1])),
        phi=float(1.0 / (1.0 + np.exp(-best.x[2]))),
        dispersion=float(np.exp(best.x[3])),
        n_bars=int(x.size), converged=bool(best.success),
    )


def asymmetry_significance(
    n_neg: int,
    n_pos: int,
    baseline_share: float = DOWNSIDE_BASELINE_SHARE,
    alpha: float = ASYMMETRY_ALPHA,
):
    """FR13 gate - is downside dominance ELEVATED relative to this market's norm?

    The original gate compared the raw ratio `n_neg/n_pos` to 1.0, which is
    equivalent to testing whether the downside share exceeds 0.5. That null is
    **empirically false for the NSE at 5-minute resolution**: the measured
    downside share is 0.4254 (21,180 of 49,783 jumps), which differs from
    symmetry at z = -33.3, p ~ 1.6e-243. Positive jumps genuinely outnumber
    negative ones here, so a gate anchored at 0.5 demands dominance the market
    never exhibits and suppresses MTS_t across the entire corpus. It was not
    merely mis-tuned - it had no reference distribution and no notion of
    significance, so no threshold choice could have made it principled.

    The replacement tests the window against the market's own baseline:

        H0: p_window  = baseline_share      (normal downside mix)
        H1: p_window  > baseline_share      (elevated sell-side pressure)

    one-sided exact binomial at level `alpha`. This is scale-free, has a proper
    null, and fires on evidence rather than on a magic constant. Empirically it
    opens on 28.3% of 500-jump windows at alpha=0.05 - informative, neither
    always nor never.

    **The baseline must come from training data**, never from the window under
    test, or the gate leaks.

    Returns `(gate_open, p_value, observed_share)`.
    """
    from scipy.stats import binomtest

    total = int(n_neg) + int(n_pos)
    if total <= 0:
        return False, 1.0, 0.0
    share = float(n_neg) / total
    b = min(max(float(baseline_share), 1e-6), 1 - 1e-6)
    pval = float(binomtest(int(n_neg), total, b, alternative="greater").pvalue)
    return bool(pval < alpha), pval, share


def mts(branching_ratio: float, asymmetry_ratio: float, threshold: float = 1.0) -> float:
    """FR13 - MTS_t = n/(1-n), a **contagion / risk-state diagnostic**.

    Not a forward alarm, and it must never be presented as one: under the
    pre-registered de-seasonalised test the contagion signal scored roughly no
    skill at every intraday horizon (AMENDMENT-03 section 5c). What it reports
    is the *current* degree of temporal self-excitation, which C8 reconciles
    into the CSRS alongside the other pillars.

    MTS_t is likewise **not independently calibrated** - no calibration test has
    been run on MTS itself, only on the count models underneath it.

    KNOWN SPECIFICATION DEFECT in the asymmetry gate (AMENDMENT-03 section 5e).
    Measured NSE asymmetry is 0.74 - positive jumps *outnumber* negative - so
    the default threshold of 1.0 zeroes MTS_t across the entire corpus. The gate
    is left at its specified value deliberately rather than quietly retuned: the
    correct fix is a significance test against the symmetric null, and lowering
    the constant to make the signal non-zero would be manufacturing a reading.
    Callers must check `asymmetry_ratio` and surface a warning when the gate
    suppresses the score.
    """
    n = min(max(branching_ratio, 0.0), 1.0 - 1e-9)
    if asymmetry_ratio < threshold:
        return 0.0
    return float(n / (1.0 - n))


def fit_pooled(
    *,
    event_times: np.ndarray,
    event_states: np.ndarray,
    horizon_days: float,
    n_states: int = N_STATES,
) -> Ok[dict] | Err:
    """FR10/FR11 — fit one kernel per `S_t` state on the pooled event stream."""
    times = np.asarray(event_times, dtype=float)
    states = np.asarray(event_states, dtype=int)
    if times.size != states.size:
        return err(EstimationDiverged(
            estimator="hawkes_pooled", iterations=0, last_objective=float("nan")))
    if times.size < MIN_EVENTS_TOTAL:
        return err(InsufficientHistory(
            required=MIN_EVENTS_TOTAL, available=int(times.size), as_of="1970-01-01"))

    kernels: dict[int, StateKernel] = {}
    warnings: list[SeraphWarning] = []
    thin = 0
    for s in range(1, n_states + 1):
        sel = np.sort(times[states == s])
        k = fit_state_kernel(sel, horizon_days, state=s)
        if k is None:
            thin += 1
            continue
        kernels[s] = k
    if not kernels:
        return err(EstimationDiverged(
            estimator="hawkes_pooled", iterations=0, last_objective=float("nan")))
    if thin:
        warnings.append(SeraphWarning(
            code="LOW_EVENT_COUNT",
            message=(
                f"{thin} of {n_states} states held fewer than "
                f"{MIN_EVENTS_PER_STATE} events in this window and were not "
                f"estimated; MTS_t falls back to the pooled all-state kernel there"
            ),
            context={"statesUnfitted": thin, "statesFitted": len(kernels)},
        ))
    pooled = fit_state_kernel(np.sort(times), horizon_days, state=0)
    return ok({"kernels": kernels, "pooled": pooled}, tuple(warnings))


def sector_flags(
    sector_counts: "dict[str, int]",
    sector_baselines: "dict[str, float]",
    window_days: float,
    *,
    amber_multiple: float = SECTOR_AMBER_MULTIPLE,
) -> tuple[SectorFlag, ...]:
    """FR14 — per-sector micro-flags from realised intensity vs own baseline.

    AMENDMENT-03(e): the flag is driven by realised-intensity-over-baseline, not
    by a sector-specific branching ratio, which the event counts cannot identify.
    `n` on the returned SectorFlag carries that intensity ratio.
    """
    out = []
    for sector, count in sorted(sector_counts.items()):
        base = sector_baselines.get(sector, 0.0)
        realised = count / max(window_days, 1e-9)
        ratio = realised / base if base > 0 else 0.0
        out.append(SectorFlag(
            sector_id=sector,
            n=float(ratio),
            flag="amber" if ratio >= amber_multiple else "none",
        ))
    return tuple(out)


def detail_from(
    kernel: StateKernel,
    *,
    n_neg: int,
    n_pos: int,
    flags: tuple[SectorFlag, ...] = (),
) -> HawkesDetail:
    """Assemble the S5 HawkesDetail for the current bar's state."""
    return HawkesDetail(
        branching_ratio=min(kernel.branching_ratio, 1.0 - 1e-9),   # FR11
        asymmetry_ratio=float(n_neg / max(n_pos, 1)),
        jump_count_neg=int(n_neg),
        jump_count_pos=int(n_pos),
        sector_flags=flags,
        branching_matrix=(),      # FR15 network is full-sample; see AMENDMENT-03(f)
    )


# =====================================================================
# PRODUCTION PATH - discrete-time Hawkes at native 5-minute resolution.
# =====================================================================


def estimate_state(
    *,
    counts,
    session_starts,
    tod_profile,
    tod_index,
    n_neg: int,
    n_pos: int,
    sector_counts=None,
    sector_baselines=None,
    window_days: float = WINDOW_DAYS,
    baseline_share: float = DOWNSIDE_BASELINE_SHARE,
    alpha: float = ASYMMETRY_ALPHA,
):
    """FR10/FR11/FR13/FR14 - the production Pillar 1 estimate.

    Fits the discrete-time Hawkes kernel on whole-bar counts and packages the
    result as the S5 `HawkesDetail` that C8 already consumes. **The emission
    contract is unchanged** - downstream components receive the same
    conceptual information (contagion/endogeneity state plus an MTS-style
    score); only the estimator behind `branching_ratio` differs.

    Returns `Ok((HawkesDetail, mts_value))`, or `Err` when the window cannot
    identify a kernel. An unidentifiable window is an absence for C8 to handle,
    never a fabricated `n = 0`.
    """
    fit = fit_discrete_hawkes(counts, session_starts, tod_profile, tod_index)
    if fit is None:
        return err(InsufficientHistory(
            required=MIN_EVENTS_TOTAL,
            available=int(np.asarray(counts).size),
            as_of="1970-01-01",
        ))

    warnings: list[SeraphWarning] = []
    n = fit.branching_ratio
    if not (0.0 < n < 1.0):                     # FR11 stationarity
        return err(ConstraintViolated(
            constraint="discrete Hawkes stationarity n = alpha/(1-phi) < 1",
            observed=float(n), bound=1.0))

    asym = n_neg / max(n_pos, 1)
    gate_open, gate_p, share = asymmetry_significance(
        n_neg, n_pos, baseline_share, alpha)
    score = float(n / (1.0 - n)) if gate_open else 0.0
    if not gate_open and n > 0.0:
        # The FR13 gate suppressed a live reading. Surfaced, never silent -
        # measured NSE asymmetry is 0.74, so this fires corpus-wide.
        # Suppressed because downside pressure is NOT significantly elevated -
        # a normal-mix reading, explicitly distinguishable from "no contagion".
        warnings.append(SeraphWarning(
            code="LOW_EVENT_COUNT",
            message=(
                f"MTS_t gated off: downside share {share:.4f} is not "
                f"significantly above the {baseline_share:.4f} baseline "
                f"(one-sided p = {gate_p:.3f} >= {alpha}), despite contagion "
                f"n = {n:.4f}. This is a normal-mix state, not an absence of "
                f"contagion - the branching ratio is still reported in detail"
            ),
            context={
                "downsideShare": round(share, 4),
                "baselineShare": round(baseline_share, 4),
                "gatePValue": round(gate_p, 5),
                "branchingRatio": round(n, 4),
            },
        ))

    flags = ()
    if sector_counts and sector_baselines:
        flags = sector_flags(sector_counts, sector_baselines, window_days)

    detail = HawkesDetail(
        branching_ratio=min(n, 1.0 - 1e-9),
        asymmetry_ratio=float(asym),
        jump_count_neg=int(n_neg),
        jump_count_pos=int(n_pos),
        sector_flags=flags,
        branching_matrix=(),        # FR15 network is full-sample; AMENDMENT-03
    )
    return ok((detail, float(score)), tuple(warnings))
