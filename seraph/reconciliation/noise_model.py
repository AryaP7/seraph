# C8 — Reconciliation Layer (FR26, decision D4): bounded saturating observation noise.
"""R^(p)(Δ) = R₀ + (R_max − R₀)·(1 − e^(−Δ/h_p))

Boundedness is the decisive property (AGENTS.md §5): an unbounded form sends
P → ∞ for a structurally-absent pillar and makes the FR29 confidence interval
infinite. At saturation the Kalman gain ≈ 0, so a fully stale pillar
contributes nothing — but P stays finite. `h_p` initialises to the pillar's
native update cadence; `h_p`, the R_max/R₀ ratio and Q_proc remain
MLE-fittable per SPEC OQ10's resolution."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, inf


@dataclass(frozen=True)
class SaturatingNoise:
    """Per-pillar D4 noise curve. Δ is measured in bars (5-minute units)."""

    r0_default: float = 0.02     # Hawkes/RMT fallback; Hamilton supplies FR23 variance
    r_max_ratio: float = 100.0   # R_max = ratio · R₀ (D4 initialisation)
    h_bars: float = 1.0          # staleness scale — the pillar's native cadence
    saturation_fraction: float = 0.95   # D4: observable saturation trigger

    def r(self, delta_bars: float, r0: float | None = None) -> float:
        base = self.r0_default if r0 is None else r0
        r_max = self.r_max_ratio * base
        if delta_bars == inf:
            return r_max                     # the "absent pillar = R → ∞" limit, kept finite
        if delta_bars < 0:
            raise ValueError(f"negative staleness {delta_bars} — tau after ts?")
        return base + (r_max - base) * (1.0 - exp(-delta_bars / self.h_bars))

    def saturated(self, r_value: float, r0: float | None = None) -> bool:
        base = self.r0_default if r0 is None else r0
        return r_value >= self.saturation_fraction * self.r_max_ratio * base
