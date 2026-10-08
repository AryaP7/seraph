# Orchestration — the production path that wires validated pillars into C8/C9.
"""C5/C6/C7 persisted output -> standardised PillarEmission -> C8 -> C9.

This package exists because the pillars are I/O-free by design (AGENTS.md §4)
and C8/C9 are pure; something has to own the database reads, the FR28
standardisation boundary and the multi-cadence tick loop. `adapters.py` stays
pure (row in, emission out) so the contract is testable without a database.
"""
from seraph.orchestration.adapters import (
    IST_CLOSE,
    close_ts,
    hamilton_emission,
    hawkes_emission,
    lam1_share,
    rmt_emission,
)
from seraph.orchestration.standardize import (
    MIN_WINDOW_OBS,
    R_STD_CEIL,
    R_STD_FLOOR,
    STANDARDISER_VERSION,
    density_at,
    standardise,
    window_from,
)

__all__ = [
    "IST_CLOSE",
    "close_ts",
    "hamilton_emission",
    "hawkes_emission",
    "lam1_share",
    "rmt_emission",
    "MIN_WINDOW_OBS",
    "R_STD_CEIL",
    "R_STD_FLOOR",
    "STANDARDISER_VERSION",
    "density_at",
    "standardise",
    "window_from",
]
