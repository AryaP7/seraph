# C8 — Reconciliation Layer (FR25–FR27): hand-rolled NumPy Kalman (AGENTS.md §2).
"""Predict: random-walk transition, P += Q_proc·Δ at every tick (FR25).
Update: EVERY pillar gets an update at every tick — a pillar with no fresh
emission is 'observed' at its own prior mean with age-inflated, BOUNDED noise
R^(p)(Δ) (FR26 + D4). That is exactly SPEC O6's "an absent pillar is the
limiting case R → ∞" argument with D4 keeping R finite: the mean never
collapses toward zero, trace(P) grows to a Riccati fixed point and saturates
instead of diverging, and the first genuine emission snaps P down (CT-4).

D2 mask rules (AGENTS.md §5):
  observed                        → mask true
  observed but R at ceiling       → mask false + NOISE_SATURATED
  unavailable, transient          → mask true  (D4 inflation handles it)
  unavailable, structural         → mask false
Forward-fill is retained only as the FR27/FR36 ablation baseline.
"""
from __future__ import annotations

from datetime import datetime
from math import inf

import numpy as np

from seraph.reconciliation.noise_model import SaturatingNoise
from seraph.shared_types import (
    ContractViolation,
    Err,
    Ok,
    PILLAR_ORDER,
    PillarEmission,
    ReconciledState,
    SeraphWarning,
    err,
    ist_timestamp,
    ok,
)

BAR_SECONDS = 300.0
#: Native cadences per D4 — Hawkes: one 5-min bar; RMT/Hamilton: one trading
#: day (~75 five-minute bars in an NSE session).
DEFAULT_H_BARS = (1.0, 75.0, 75.0)

_STATUS_MASK = {
    "unseen": False,       # nothing ever emitted — no information yet
    "observed": True,
    "transient": True,     # should exist; D4 age-inflation handles it
    "structural": False,   # cannot exist for this period
    "saturated": False,    # present but contributing nothing (D2 row 4)
}


class KalmanReconciler:
    """S6 — predict/update over the 3-dim pillar state in PILLAR_ORDER."""

    def __init__(
        self,
        *,
        q_proc: float = 1e-3,
        r0_default: float = 0.02,
        r_max_ratio: float = 100.0,
        h_bars: tuple[float, float, float] = DEFAULT_H_BARS,
        x0: tuple[float, float, float] = (0.5, 0.5, 0.5),
        p0: float = 1e-3,
        mode: str = "kalman",
    ):
        if mode not in ("kalman", "forward_fill"):
            raise ValueError(f"mode must be 'kalman' or 'forward_fill', got {mode!r}")
        self._q = float(q_proc)
        self._mode = mode
        self._noise = tuple(
            SaturatingNoise(r0_default=r0_default, r_max_ratio=r_max_ratio, h_bars=h)
            for h in h_bars
        )
        self._x = np.asarray(x0, dtype=float).copy()
        self._P = np.eye(3) * float(p0)
        self._tau: list[datetime | None] = [None, None, None]
        self._r0: list[float | None] = [None, None, None]   # last FR23 variance seen
        self._status = ["unseen", "unseen", "unseen"]
        self._ts: datetime | None = None

    # ------------------------------------------------------------- interface

    def predict(self, to_ts: str) -> Ok[ReconciledState] | Err:
        """FR25 — advance x̂, P under the random walk to `to_ts`."""
        t = self._parse(to_ts)
        if t is None:
            return err(ContractViolation(field="to_ts", detail=f"unparseable {to_ts!r}"))
        if self._ts is not None and t < self._ts:
            return err(ContractViolation(
                field="to_ts", detail=f"time reversed: {to_ts} < {ist_timestamp(self._ts)}"
            ))
        self._advance(t)
        return ok(self._snapshot())

    def update(self, emissions: "list[PillarEmission]") -> Ok[ReconciledState] | Err:
        """FR26 — one update tick. Pillars without an emission this tick get
        the virtual (age-inflated) update."""
        if not emissions:
            return err(ContractViolation(field="emissions", detail="empty update batch"))

        by_pillar: dict[str, PillarEmission] = {}
        latest: datetime | None = None
        for em in emissions:
            pillar = em.obs.pillar if em.kind == "observed" else em.pillar
            by_pillar[pillar] = em
            t = self._parse(em.obs.ts if em.kind == "observed" else em.ts)
            if t is None:
                return err(ContractViolation(field="ts", detail="unparseable emission ts"))
            latest = t if latest is None or t > latest else latest

        if self._ts is not None and latest < self._ts:
            return err(ContractViolation(
                field="emissions",
                detail=f"time reversed: {ist_timestamp(latest)} < {ist_timestamp(self._ts)}",
            ))
        self._advance(latest)

        warnings: list[SeraphWarning] = []
        for i, pillar in enumerate(PILLAR_ORDER):
            self._update_pillar(i, by_pillar.get(pillar), warnings)
        self._P = (self._P + self._P.T) / 2.0
        return ok(self._snapshot(), tuple(warnings))

    def state_at(self, ts: str) -> Ok[ReconciledState] | Err:
        """Current state if `ts` is not in the past; C1-backed history is the
        pipeline's job, not this in-memory filter's."""
        t = self._parse(ts)
        if t is None:
            return err(ContractViolation(field="ts", detail=f"unparseable {ts!r}"))
        if self._ts is not None and t < self._ts:
            return err(ContractViolation(
                field="ts", detail="historical stateAt requires the store (E9), not the live filter"
            ))
        self._advance(t)
        return ok(self._snapshot())

    # -------------------------------------------------------------- internals

    @staticmethod
    def _parse(ts: str) -> datetime | None:
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return None

    def _advance(self, t: datetime) -> None:
        if self._ts is None:
            self._ts = t
            return
        delta_bars = (t - self._ts).total_seconds() / BAR_SECONDS
        if delta_bars > 0 and self._mode == "kalman":
            self._P = self._P + self._q * delta_bars * np.eye(3)
        self._ts = t

    def _staleness_bars(self, i: int) -> float:
        if self._tau[i] is None or self._ts is None:
            return inf
        return max(0.0, (self._ts - self._tau[i]).total_seconds() / BAR_SECONDS)

    def _update_pillar(self, i: int, em: PillarEmission | None, warnings: list) -> None:
        noise = self._noise[i]

        if em is not None and em.kind == "observed":
            obs = em.obs
            tau = self._parse(obs.tau)
            if tau is None:
                warnings.append(SeraphWarning(
                    code="STALE_OBSERVATION",
                    message=f"{PILLAR_ORDER[i]}: unparseable tau, treated as transient",
                    context={"pillar": PILLAR_ORDER[i]},
                ))
                self._virtual_update(i)
                return
            r0 = obs.estimation_variance
            self._r0[i] = r0
            delta_bars = max(0.0, (self._ts - tau).total_seconds() / BAR_SECONDS)
            r_val = noise.r(delta_bars, r0)
            if noise.saturated(r_val, r0):
                # D2 row 4: real but so stale it contributes ~nothing.
                self._status[i] = "saturated"
                warnings.append(SeraphWarning(
                    code="NOISE_SATURATED",
                    message=f"{PILLAR_ORDER[i]}: observation {delta_bars:.1f} bars stale, "
                            "R at ceiling — excluded from the mask",
                    context={"pillar": PILLAR_ORDER[i], "deltaBars": delta_bars},
                ))
            else:
                self._status[i] = "observed"
            self._scalar_update(i, float(obs.value), r_val)
            self._tau[i] = tau
            return

        if em is not None and em.absence == "structural":
            self._status[i] = "structural"
        elif em is not None:  # transient
            self._status[i] = "transient"
        # em is None → pillar simply not in this batch: keep prior status.
        self._virtual_update(i)

    def _virtual_update(self, i: int) -> None:
        """Observe the pillar at its own prior mean with age-inflated noise:
        innovation is exactly zero (the mean never drifts toward 0), and the
        bounded R caps P at the Riccati fixed point instead of ∞."""
        r_val = self._noise[i].r(self._staleness_bars(i), self._r0[i])
        self._scalar_update(i, float(self._x[i]), r_val)

    def _scalar_update(self, i: int, z: float, r_val: float) -> None:
        if self._mode == "forward_fill":
            # FR27 ablation baseline: carry the last value, no uncertainty model.
            self._x[i] = z
            return
        h = np.zeros(3)
        h[i] = 1.0
        s = float(self._P[i, i] + r_val)
        k = self._P @ h / s
        self._x = self._x + k * (z - self._x[i])
        ikh = np.eye(3) - np.outer(k, h)
        # Joseph form — PSD-preserving under floating point.
        self._P = ikh @ self._P @ ikh.T + r_val * np.outer(k, k)

    def _snapshot(self) -> ReconciledState:
        saturated = tuple(
            bool(self._status[i] == "saturated"
                 or self._noise[i].saturated(
                     self._noise[i].r(self._staleness_bars(i), self._r0[i]), self._r0[i]))
            for i in range(3)
        )
        return ReconciledState(
            ts=ist_timestamp(self._ts),
            x_hat=tuple(float(v) for v in self._x),
            P=tuple(tuple(float(x) for x in row) for row in self._P),
            tau_last_update=tuple(
                ist_timestamp(t) if t is not None else None for t in self._tau
            ),
            mask=tuple(bool(_STATUS_MASK[s]) for s in self._status),
            noise_saturated=saturated,
            mode=self._mode,
        )
