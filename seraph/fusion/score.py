# C9 — Fusion Engine (FR28, FR29, FR31): the pure scoring function.
"""score() is PURE: no I/O, no DB access, no hidden state, and it never uses
C10's package — weights arrive as the immutable FusionWeights artefact (D1).
Identical inputs give byte-identical CsrsPoints, 100/100 (CT-6).

Contract notes:
- x̂ is expected already standardised to [0,1] (standardize.py runs upstream in
  the pipeline); components are clipped defensively here.
- The confidence interval is a normal approximation csrs ± 1.96·σ and may
  extend past [0,1]; FR29's *calibration* of the interval is C10's job.
- Alert thresholds are provisional until FR30 calibration (SPEC OQ9).
"""
from __future__ import annotations

import numpy as np

from seraph.fusion.masking import renormalize_masked
from seraph.fusion.shapley import exact_shapley
from seraph.shared_types import (
    CsrsPoint,
    EmptyMask,
    Err,
    FusionWeights,
    Ok,
    ReconciledState,
    SeraphWarning,
    Simplex3,
    err,
    ok,
)

_Z95 = 1.959963984540054  # two-sided 95% normal quantile

# Provisional until C10 calibrates them (SPEC OQ9 — undefined constants).
PROVISIONAL_AMBER = 0.5
PROVISIONAL_RED = 0.75

_UNIFORM_XI: Simplex3 = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)


def score(
    *,
    reconciled: ReconciledState,
    xi: Simplex3,
    weights: FusionWeights,
    xi_mode: str = "hamilton",
    amber_threshold: float = PROVISIONAL_AMBER,
    red_threshold: float = PROVISIONAL_RED,
) -> Ok[CsrsPoint] | Err:
    """CSRS_t = Σ_j ξ_j (w_j^(m))ᵀ x̂_t  (FR28, D2 mask renormalisation)."""
    mask = reconciled.mask
    if not any(mask):
        return err(EmptyMask(ts=reconciled.ts))

    xi_used: Simplex3 = _UNIFORM_XI if xi_mode == "uniform" else xi
    x = tuple(float(v) for v in np.clip(np.asarray(reconciled.x_hat, dtype=float), 0.0, 1.0))
    p = np.asarray(reconciled.P, dtype=float)

    effective: list[tuple[float, float, float]] = []
    any_fallback = False
    for row in weights.w:
        renorm, fallback = renormalize_masked(row, mask)
        effective.append(renorm)
        any_fallback = any_fallback or fallback

    csrs = 0.0
    variance = 0.0
    for j in range(3):
        w_j = np.asarray(effective[j], dtype=float)
        csrs += xi_used[j] * float(w_j @ np.asarray(x))
        # FR29 — computed with masked-zero weights, so the absent pillar's
        # prior block of P never leaks into the interval (D2 consequence 3).
        variance += (xi_used[j] ** 2) * float(w_j @ p @ w_j)
    csrs = min(1.0, max(0.0, csrs))
    variance = max(0.0, variance)
    half = _Z95 * variance ** 0.5

    shapley = exact_shapley(x, xi_used, weights.w, mask)

    warnings: tuple[SeraphWarning, ...] = ()
    if not all(mask):
        detail = "uniform fallback over available pillars" if any_fallback else "weights renormalised"
        warnings = (SeraphWarning(
            code="MASK_DEGRADED",
            message=f"scoring on a degraded mask {list(mask)} — {detail}; "
                    "not comparable to full-mask CSRS without annotation (D2)",
            context={"available": sum(mask)},
        ),)

    level = "red" if csrs >= red_threshold else "amber" if csrs >= amber_threshold else "green"

    point = CsrsPoint(
        ts=reconciled.ts,
        csrs=csrs,
        variance=variance,
        ci_lower=csrs - half,
        ci_upper=csrs + half,
        shapley=shapley,
        alert_level=level,
        mask=mask,
        effective_weights=(effective[0], effective[1], effective[2]),
        xi_mode="uniform" if xi_mode == "uniform" else "hamilton",
        weights_artefact_id=weights.artefact_id,
        reconciliation_mode=reconciled.mode,
    )
    return ok(point, warnings)
