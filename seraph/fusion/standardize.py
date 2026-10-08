# C9 — Fusion Engine (FR28): rolling five-year empirical-CDF standardiser.
"""Each pillar sub-score is standardised to [0,1] as its ECDF rank within a
rolling window of that pillar's own history before entering the CSRS. The
pipeline applies this transform to the reconciled x̂ upstream of score();
score() itself only clips defensively. Pure over its inputs — the caller
supplies the window, nothing is fetched."""
from __future__ import annotations

import numpy as np

ECDF_WINDOW_YEARS = 5  # FR28; also recorded on every FusionWeights artefact


def ecdf_transform(value: float, window: "np.typing.ArrayLike") -> float:
    """Right-continuous ECDF rank of `value` within `window` (→ [0,1]).

    An empty window has no distribution to rank against; the uninformative
    midpoint 0.5 is returned — callers should attach a PARTIAL_COVERAGE
    warning when that happens."""
    arr = np.sort(np.asarray(window, dtype=float).ravel())
    if arr.size == 0:
        return 0.5
    return float(np.searchsorted(arr, value, side="right")) / float(arr.size)
