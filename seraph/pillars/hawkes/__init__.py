# C5 — Hawkes Engine (FR10-FR15, as amended by AMENDMENT-03)
"""Market-wide pooled jump-contagion kernel and the MTS_t sub-score."""
from seraph.pillars.hawkes.engine import (
    DiscreteHawkes,
    excitation_path,
    ASYMMETRY_ALPHA,
    DOWNSIDE_BASELINE_SHARE,
    asymmetry_significance,
    estimate_state,
    fit_discrete_hawkes,
    MIN_EVENTS_PER_STATE,
    N_STATES,
    WINDOW_DAYS,
    StateKernel,
    detail_from,
    fit_pooled,
    fit_state_kernel,
    mts,
    sector_flags,
)

__all__ = [
    "DiscreteHawkes",
    "excitation_path",
    "ASYMMETRY_ALPHA",
    "DOWNSIDE_BASELINE_SHARE",
    "asymmetry_significance",
    "estimate_state",
    "fit_discrete_hawkes",
    "MIN_EVENTS_PER_STATE",
    "N_STATES",
    "WINDOW_DAYS",
    "StateKernel",
    "detail_from",
    "fit_pooled",
    "fit_state_kernel",
    "mts",
    "sector_flags",
]
