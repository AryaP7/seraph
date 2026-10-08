# C9 — Fusion Engine (FR28, decision D2): availability-mask weight renormalisation.
"""w_j^(m) = (m ⊙ w_j) / Σ(m ⊙ w_j) — selects a point inside FR28's existing
constraint set (still sums to 1, still non-negative) when a pillar carries no
information. Both production scoring and the ablation subsets go through this
one function: the degraded path and the ablation row are the same code path
(CT-9's equality is a design invariant, not a coincidence)."""
from __future__ import annotations

from seraph.shared_types import AvailabilityMask, Simplex3


def renormalize_masked(
    row: Simplex3, mask: AvailabilityMask
) -> tuple[tuple[float, float, float], bool]:
    """Return (renormalised row, degraded_fallback).

    degraded_fallback is True when the row had all its mass on masked-out
    pillars (Σ(m ⊙ w_j) = 0), in which case D2 prescribes uniform weights over
    the available pillars. Callers must reject an all-false mask (EMPTY_MASK)
    before calling."""
    masked = tuple(w if m else 0.0 for w, m in zip(row, mask))
    total = sum(masked)
    if total <= 0.0:
        k = sum(1 for m in mask if m)
        if k == 0:
            raise ValueError("empty mask — callers must return EMPTY_MASK first")
        return tuple((1.0 / k) if m else 0.0 for m in mask), True
    return tuple(w / total for w in masked), False
