# C8 — Reconciliation Layer (FR26, decision D4): bounded saturating observation noise.
"""R^(p)(Δ) = R₀ + (R_max − R₀)·(1 − e^(−Δ/h_p))

This curve describes the noise of an actual newly received measurement.
Missing measurements do not trigger an update. Bounded R does NOT bound P
under absence, nor guarantee near-zero gain when P is large. Saturation is
an explicit exclusion policy, not a mathematical zero-gain limit. See the
experimental amendment in docs/EXPERIMENT-MATH.md. `h_p` is expressed in the
reconciler's declared clock; parameters still require calibration."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, inf, isfinite


@dataclass(frozen=True)
class SaturatingNoise:
    """Per-pillar D4 noise curve. Δ is measured in bars (5-minute units)."""

    r0_default: float = 0.02     # Hawkes/RMT fallback; Hamilton supplies FR23 variance
    r_max_ratio: float = 100.0   # R_max = ratio · R₀ (D4 initialisation)
    h_bars: float = 1.0          # staleness scale — the pillar's native cadence
    saturation_fraction: float = 0.95   # D4: observable saturation trigger

    def __post_init__(self) -> None:
        if not isfinite(self.r0_default) or self.r0_default <= 0:
            raise ValueError("r0_default must be finite and positive")
        if not isfinite(self.r_max_ratio) or self.r_max_ratio < 1:
            raise ValueError("r_max_ratio must be finite and >= 1")
        if not isfinite(self.h_bars) or self.h_bars <= 0:
            raise ValueError("h_bars must be finite and positive")
        if not 0 < self.saturation_fraction <= 1:
            raise ValueError("saturation_fraction must be in (0, 1]")

    def _base(self, r0: float | None) -> float:
        base = self.r0_default if r0 is None else r0
        if not isfinite(base) or base < 0:
            raise ValueError("observation variance must be finite and nonnegative")
        # A zero supplied variance is not allowed to cause 0/0 or make every
        # observation 'saturated'; this numerical floor is not calibration.
        return max(float(base), 1e-12)

    def r(self, delta_bars: float, r0: float | None = None) -> float:
        base = self._base(r0)
        r_max = self.r_max_ratio * base
        if delta_bars == inf:
            return r_max
        if not isfinite(delta_bars) or delta_bars < 0:
            raise ValueError(f"negative staleness {delta_bars} — tau after ts?")
        return base + (r_max - base) * (1.0 - exp(-delta_bars / self.h_bars))

    def saturated(self, r_value: float, r0: float | None = None) -> bool:
        base = self._base(r0)
        # A constant-noise curve (ratio=1) never signals staleness saturation.
        return (self.r_max_ratio > 1 and
                r_value >= self.saturation_fraction * self.r_max_ratio * base)
