# Orchestration — FR28 standardisation applied at the EMISSION boundary.
"""Rolling five-year causal ECDF, plus the variance mapping that must go with it.

**Why here and not after reconciliation.** `fusion/score.py` assumes `x̂` is
already in [0,1] and its docstring says the pipeline transforms the *reconciled*
state. Applying a nonlinear transform after the Kalman is wrong in a way that
matters: `P` would then be the covariance of the **untransformed** state while
CSRS is computed from transformed values, so FR29's
`Var(CSRS) = Σ ξ² wᵀ P w` would mix the two coordinate systems. Standardising
each sub-score at emission instead satisfies FR28 exactly as written ("each
sub-score is standardised to [0,1] by empirical-CDF transform on a rolling
five-year window") and leaves the filter operating in one consistent coordinate
system, where:

  * `x0 = (0.5, 0.5, 0.5)` is the correct median-rank prior rather than a guess;
  * a single `Q_proc` and `r0_default` are commensurable across three pillars
    whose raw units are not (MTS ≈ 0.12 unbounded, λ₁/N ≈ 0.25, LSD ∈ [0, 3]);
  * `score()`'s defensive clip never binds, so **a legitimate LSD of 3.0 becomes
    rank 1.0 by rank, not by truncation**.

**Causality.** The window for date `t` is `[t − 5y, t]`. Including `t` is
correct and not leakage — its own value is known at `t` — but nothing after `t`
ever enters, in replay or live. The two paths run identical code.

**What the number means.** An ECDF rank is *relative to the trailing five years*,
not an absolute probability of anything. Two identical raw readings five years
apart can carry different ranks because the reference distribution moved. That
adaptivity is the point (it is what makes the transform robust to a drifting
distribution), but it must be stated wherever a standardised value is reported.
"""
from __future__ import annotations

import numpy as np

from seraph.fusion import ECDF_WINDOW_YEARS, ecdf_transform
from seraph.shared_types import SeraphWarning

#: Bump when the transform's *definition* changes in a way that alters output.
#: Persisted alongside emissions so a replay can be tied to the rule that
#: produced it; the transform is otherwise reproducible from the raw pillar
#: series, which C1 already stores.
STANDARDISER_VERSION = "ecdf-5y-v1"

#: Trading days in the FR28 window. 252 × 5; the pipeline passes actual
#: observations, so this is only the completeness threshold.
FULL_WINDOW_OBS = 252 * ECDF_WINDOW_YEARS

#: Below this many observations the ECDF is too coarse to be a stable reference
#: and the emission carries PARTIAL_COVERAGE. One trading year.
MIN_WINDOW_OBS = 252

#: Delta-method guards, on the [0,1] rank scale.
#: Floor: `f̂ → 0` in a sparse tail sends `r_std → 0`, which would give the
#: Kalman an infinite gain and collapse `P` onto a single observation. The floor
#: is a numerical guard, not a modelling choice.
#: Ceiling: a variance above the 1/12 of a uniform on [0,1] already means the
#: observation carries no rank information; 0.25 is a generous cap past that.
R_STD_FLOOR = 1e-8
R_STD_CEIL = 0.25


def _bandwidth(window: np.ndarray) -> float:
    """Silverman-style bandwidth on a robust scale, for the density estimate.

    `n^(-1/3)` rather than `n^(-1/5)`: this bandwidth serves a finite-difference
    derivative of the CDF, not a density plot, and the derivative's optimal rate
    is the slower one.
    """
    n = window.size
    if n < 2:
        return 0.0
    q1, q3 = np.percentile(window, [25, 75])
    scale = max(float(q3 - q1), float(window.std()), 1e-12)
    return float(scale * n ** (-1.0 / 3.0))


def density_at(value: float, window: "np.typing.ArrayLike") -> float:
    """`f̂(x)` — central finite difference of the empirical CDF at `value`.

    This is the `g'(x)` the delta method needs to carry a raw-scale variance
    through the rank transform.
    """
    arr = np.asarray(window, dtype=float).ravel()
    h = _bandwidth(arr)
    if arr.size < 2 or h <= 0:
        return 0.0
    hi = ecdf_transform(value + h, arr)
    lo = ecdf_transform(value - h, arr)
    return float(max(hi - lo, 0.0) / (2.0 * h))


def standardise(
    value: float,
    *,
    window: "np.typing.ArrayLike",
    raw_variance: float | None = None,
    pillar: str = "",
) -> tuple[float, float | None, tuple[SeraphWarning, ...]]:
    """Map one raw sub-score to its causal ECDF rank, with its variance.

    `window` is that pillar's own past values over the trailing five years,
    supplied by the caller — this function performs no I/O so that replay and
    live use provably identical code.

    Returns `(rank, transformed_variance, warnings)`. `transformed_variance` is
    `None` exactly when `raw_variance` is `None`, which is the documented signal
    for C8 to fall back to its own prior (Hawkes and RMT have no per-observation
    estimator variance; only Hamilton supplies one, under FR23).
    """
    arr = np.asarray(window, dtype=float).ravel()
    arr = arr[np.isfinite(arr)]
    warnings: list[SeraphWarning] = []

    if arr.size < MIN_WINDOW_OBS:
        warnings.append(SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=(
                f"{pillar or 'pillar'}: ECDF reference window holds {arr.size} "
                f"observations, below the {MIN_WINDOW_OBS} needed for a stable "
                f"rank and the {FULL_WINDOW_OBS} of a full five years "
                f"(FR28). The rank is emitted and flagged, not withheld"
            ),
            context={"available": int(arr.size), "required": MIN_WINDOW_OBS},
        ))

    rank = ecdf_transform(float(value), arr) if arr.size else 0.5

    if raw_variance is None:
        return rank, None, tuple(warnings)

    # Delta method: Var(g(X)) ≈ g'(μ)² Var(X), with g = F the ECDF.
    f_hat = density_at(float(value), arr)
    r_std = float(np.clip(f_hat ** 2 * float(raw_variance),
                          R_STD_FLOOR, R_STD_CEIL))
    return rank, r_std, tuple(warnings)


def window_from(
    series: "list[tuple[str, float]]", as_of: str, years: int = ECDF_WINDOW_YEARS
) -> list[float]:
    """Trailing `years` of a pillar's own values, strictly causal.

    `series` is `(iso_timestamp, value)` sorted ascending. Selection is on the
    ISO string, which is chronological for this fixed format, so no timezone
    arithmetic can silently admit a future observation. The bound is inclusive
    of `as_of` and exclusive of anything after it.
    """
    if not series:
        return []
    year = int(as_of[:4]) - years
    lower = f"{year:04d}{as_of[4:]}"
    return [v for ts, v in series if lower <= ts <= as_of]
