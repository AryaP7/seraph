# C9 — Fusion Engine (FR31): exact pillar-level Shapley decomposition.
"""Three pillars ⇒ 2³ = 8 coalitions — computed exactly by enumeration, no
approximation library (ROADMAP Phase 7). The value function v(S) is the CSRS
scored with the mask restricted to S, through the SAME D2 renormalisation used
in production scoring, with v(∅) = 0. Efficiency then gives Σᵢ φᵢ = CSRS, and
masked pillars get φᵢ = 0 exactly — FR44's explanation can never attribute an
alert to an absent pillar."""
from __future__ import annotations

from itertools import combinations
from math import factorial

from seraph.fusion.masking import renormalize_masked
from seraph.shared_types import AvailabilityMask, Simplex3, Vec3


def exact_shapley(
    x: Vec3,
    xi: Simplex3,
    w_rows: tuple[Simplex3, Simplex3, Simplex3],
    mask: AvailabilityMask,
) -> Vec3:
    """Shapley contributions in PILLAR_ORDER; `x` is the standardised x̂."""
    avail = tuple(i for i in range(3) if mask[i])
    n = len(avail)

    def v(subset: tuple[int, ...]) -> float:
        if not subset:
            return 0.0
        submask = (0 in subset, 1 in subset, 2 in subset)
        total = 0.0
        for j in range(3):
            row, _ = renormalize_masked(w_rows[j], submask)
            total += xi[j] * (row[0] * x[0] + row[1] * x[1] + row[2] * x[2])
        return min(1.0, max(0.0, total))

    phi = [0.0, 0.0, 0.0]
    for i in avail:
        others = tuple(a for a in avail if a != i)
        for size in range(len(others) + 1):
            coeff = factorial(size) * factorial(n - size - 1) / factorial(n)
            for coalition in combinations(others, size):
                with_i = tuple(sorted(coalition + (i,)))
                phi[i] += coeff * (v(with_i) - v(coalition))
    return (phi[0], phi[1], phi[2])
