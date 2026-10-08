# C10 — Validation Harness (FR35, FR36): ablation subset scoring.
"""D2 consequence 2 (ARCHITECTURE §7): evaluating a pillar subset IS scoring
under the corresponding availability mask — one implementation, not two.
score_subset therefore constructs the mask and calls C9's pure score()
directly; CT-9 asserts the byte-equality. The 14-configuration Table A/B
runner (Phase 8) is built on top of this function."""
from __future__ import annotations

from seraph.fusion.score import score
from seraph.shared_types import (
    AvailabilityMask,
    CsrsPoint,
    Err,
    FusionWeights,
    Ok,
    PILLAR_ORDER,
    PillarId,
    ReconciledState,
    Simplex3,
)


def subset_mask(subset: tuple[PillarId, ...]) -> AvailabilityMask:
    """Map a pillar subset to its AvailabilityMask in PILLAR_ORDER."""
    unknown = set(subset) - set(PILLAR_ORDER)
    if unknown:
        raise ValueError(f"unknown pillars {sorted(unknown)} — PILLAR_ORDER is {PILLAR_ORDER}")
    if not subset:
        raise ValueError("empty subset — nothing to evaluate")
    return tuple(p in subset for p in PILLAR_ORDER)


def score_subset(
    *,
    reconciled: ReconciledState,
    xi: Simplex3,
    weights: FusionWeights,
    subset: tuple[PillarId, ...],
    xi_mode: str = "hamilton",
) -> Ok[CsrsPoint] | Err:
    """Score exactly as production would if only `subset` were available.

    The subset mask is intersected with the state's own mask — an ablation can
    remove information, never invent it (a structurally-absent pillar stays
    absent even if the subset names it)."""
    mask = tuple(m and s for m, s in zip(reconciled.mask, subset_mask(subset)))
    tau = tuple(t if m else None for t, m in zip(reconciled.tau_last_update, mask))
    restricted = reconciled.model_copy(update={"mask": mask, "tau_last_update": tau})
    return score(reconciled=restricted, xi=xi, weights=weights, xi_mode=xi_mode)
