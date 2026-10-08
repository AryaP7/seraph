# C6 — RMT Engine (FR16–FR19)
"""Spectral coupling sub-scores from the rolling universe correlation matrix."""
from seraph.pillars.rmt.engine import (
    RmtEngine,
    BOOTSTRAP_REPS,
    COMMON_SUPPORT_FLOOR,
    SCA_MIN_HISTORY,
    SCA_WEIGHTS,
    T_WINDOW,
    compute_rmt,
    mp_bounds,
    sca,
)

__all__ = [
    "BOOTSTRAP_REPS",
    "RmtEngine",
    "SCA_MIN_HISTORY",
    "COMMON_SUPPORT_FLOOR",
    "SCA_WEIGHTS",
    "T_WINDOW",
    "compute_rmt",
    "mp_bounds",
    "sca",
]
