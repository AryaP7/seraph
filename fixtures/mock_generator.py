# T0 — Mock fixture generator (ARCHITECTURE §4; ROADMAP Phase 1)
"""Synthetic PillarEmission / ReconciledState / CsrsPoint streams conforming
exactly to ARCHITECTURE §2's shapes — no real data, no DB.

This is what lets C8/C9/C10/C11/C12 be built and tested before a single real
pillar exists. Deliberately includes `unavailable` periods of both kinds:
`structural` (Hawkes pre-coverage — drives the D2 mask) and `transient`
(a failed update — drives D4 age-inflation).

Run: python -m fixtures.mock_generator [--ticks N] [--seed S]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

import numpy as np

from seraph.shared_types import (
    IST,
    AvailabilityMask,
    CalibrationConfig,
    CsrsPoint,
    FusionWeights,
    ObservedEmission,
    PILLAR_ORDER,
    PillarEmission,
    PillarId,
    PillarObservation,
    ReconciledState,
    Simplex3,
    UnavailableEmission,
    fusion_weights_artefact_id,
    ist_timestamp,
)

#: NSE open, an arbitrary but realistic session start.
DEFAULT_START = datetime(2020, 3, 2, 9, 15, 0, tzinfo=IST)
BAR = timedelta(minutes=5)

# Mock alert thresholds — real ones are calibrated by C10 (SPEC OQ9).
_MOCK_AMBER, _MOCK_RED = 0.5, 0.75


def _simplex3(rng: np.random.Generator, mask: AvailabilityMask = (True, True, True)) -> Simplex3:
    """Random point on the 3-simplex, zero mass on masked-out pillars."""
    idx = [i for i, m in enumerate(mask) if m]
    if not idx:
        raise ValueError("cannot build a simplex over an empty mask")
    vals = rng.dirichlet(np.ones(len(idx)))
    out = [0.0, 0.0, 0.0]
    for i, v in zip(idx, vals):
        out[i] = float(v)
    out[idx[-1]] = max(0.0, 1.0 - sum(out[i] for i in idx[:-1]))
    return (out[0], out[1], out[2])


def _mock_value(pillar: PillarId, rng: np.random.Generator) -> float:
    # Native scales: MTS_t >= 0 (unbounded), SCA_t in [0,1], LSD_t in [0,3].
    if pillar == "hawkes":
        return float(rng.exponential(0.5))
    if pillar == "rmt":
        return float(rng.beta(2, 5))
    return float(rng.uniform(0.0, 3.0))


def mock_emission(
    pillar: PillarId,
    ts: datetime,
    rng: np.random.Generator,
    *,
    absence: str | None = None,
    stale_by: timedelta = timedelta(0),
    estimation_variance: float | None = None,
) -> PillarEmission:
    """One emission. `absence` in {None, "structural", "transient"}.
    `stale_by` pushes tau earlier than ts (tau is when it was ACTUALLY computed).
    `estimation_variance` fixes Hamilton's FR23 variance; None draws it randomly
    (deterministic noise matters for CT-4's trace-monotonicity assertion)."""
    if absence == "structural":
        return UnavailableEmission(
            pillar=pillar, ts=ist_timestamp(ts),
            absence="structural", reason="no_data_coverage",
        )
    if absence == "transient":
        return UnavailableEmission(
            pillar=pillar, ts=ist_timestamp(ts),
            absence="transient", reason="estimation_failed",
        )
    est_var: float | None = None
    if pillar == "hamilton":
        est_var = (float(rng.uniform(0.001, 0.05))
                   if estimation_variance is None else float(estimation_variance))
    return ObservedEmission(obs=PillarObservation(
        pillar=pillar,
        ts=ist_timestamp(ts),
        tau=ist_timestamp(ts - stale_by),
        value=_mock_value(pillar, rng),
        estimation_variance=est_var,
    ))


def mock_tick_stream(
    *,
    start: datetime = DEFAULT_START,
    n_ticks: int = 100,
    cadence: timedelta = BAR,
    seed: int = 0,
    hawkes_structural_ticks: int = 0,
    transient_rate: float = 0.0,
    stale_every: int | None = 7,
    estimation_variance: float | None = None,
) -> list[list[PillarEmission]]:
    """Per tick, one emission per pillar in PILLAR_ORDER.

    Hawkes is structurally absent for the first `hawkes_structural_ticks`
    ticks (the SPEC §4 pre-2015 coverage hole in miniature); each pillar
    independently suffers transient failures at `transient_rate`.
    `stale_every=None` disables the periodic stale-tau pattern and
    `estimation_variance` pins Hamilton's noise — CT-4's monotone-trace
    assertion needs both held constant.
    """
    rng = np.random.default_rng(seed)
    stream: list[list[PillarEmission]] = []
    for k in range(n_ticks):
        ts = start + k * cadence
        tick: list[PillarEmission] = []
        for i, pillar in enumerate(PILLAR_ORDER):
            if pillar == "hawkes" and k < hawkes_structural_ticks:
                tick.append(mock_emission(pillar, ts, rng, absence="structural"))
            elif transient_rate > 0 and rng.uniform() < transient_rate:
                tick.append(mock_emission(pillar, ts, rng, absence="transient"))
            else:
                # RMT/Hamilton update daily in production; mock them as one
                # cadence stale now and then so R^(p)(Δ) has something to do.
                stale = (cadence
                         if (i > 0 and stale_every is not None and k % stale_every == 3)
                         else timedelta(0))
                tick.append(mock_emission(pillar, ts, rng, stale_by=stale,
                                          estimation_variance=estimation_variance))
        stream.append(tick)
    return stream


def mock_psd_mat3(rng: np.random.Generator, scale: float = 0.05) -> tuple:
    """Symmetric PSD 3×3 — valid for ReconciledState.P by construction."""
    a = rng.normal(size=(3, 3))
    p = scale * (a @ a.T) + 1e-6 * np.eye(3)
    p = (p + p.T) / 2.0
    return tuple(tuple(float(x) for x in row) for row in p)


def mock_reconciled_state(
    ts: datetime,
    rng: np.random.Generator,
    *,
    mask: AvailabilityMask = (True, True, True),
    mode: str = "kalman",
    p_scale: float = 0.05,
) -> ReconciledState:
    tau = ist_timestamp(ts)
    return ReconciledState(
        ts=ist_timestamp(ts),
        x_hat=tuple(float(v) for v in rng.uniform(0.0, 1.0, size=3)),
        P=mock_psd_mat3(rng, p_scale),
        tau_last_update=tuple(tau if m else None for m in mask),
        mask=mask,
        noise_saturated=(False, False, False),
        mode=mode,
    )


def mock_reconciled_stream(
    *,
    start: datetime = DEFAULT_START,
    n: int = 50,
    cadence: timedelta = BAR,
    seed: int = 0,
    mask: AvailabilityMask = (True, True, True),
    mode: str = "kalman",
) -> list[ReconciledState]:
    rng = np.random.default_rng(seed)
    return [
        mock_reconciled_state(start + k * cadence, rng, mask=mask, mode=mode)
        for k in range(n)
    ]


def mock_fusion_weights(
    *,
    seed: int = 0,
    mask_profile: AvailabilityMask = (True, True, True),
    epochs: tuple = ("ilfs_2018", "covid_2020", "tightening_2022"),
    fold_held_out: str | None = "tariff_2026",
    kappa_miss: float = 10.0,
    kappa_fa: float = 1.0,
) -> FusionWeights:
    rng = np.random.default_rng(seed)
    w = (_simplex3(rng, mask_profile), _simplex3(rng, mask_profile), _simplex3(rng, mask_profile))
    calibrated_on = CalibrationConfig(
        epochs=epochs,
        fold_held_out=fold_held_out,
        kappa_miss=kappa_miss,
        kappa_fa=kappa_fa,
        mask_profile=mask_profile,
    )
    return FusionWeights(
        artefact_id=fusion_weights_artefact_id(w, calibrated_on),
        calibrated_on=calibrated_on,
        w=w,
    )


def mock_xi(rng: np.random.Generator) -> Simplex3:
    """Regime probabilities [tranquil, stressed, crisis]."""
    return _simplex3(rng)


def mock_csrs_point(
    ts: datetime,
    rng: np.random.Generator,
    *,
    weights: FusionWeights,
    mask: AvailabilityMask = (True, True, True),
    mode: str = "kalman",
    xi_mode: str = "hamilton",
) -> CsrsPoint:
    csrs = float(rng.uniform(0.0, 1.0))
    variance = float(rng.uniform(1e-5, 0.01))
    half = 1.96 * variance ** 0.5
    shapley = [float(rng.uniform(0.0, 0.5)) if m else 0.0 for m in mask]
    level = "red" if csrs >= _MOCK_RED else "amber" if csrs >= _MOCK_AMBER else "green"
    ew = (_simplex3(rng, mask), _simplex3(rng, mask), _simplex3(rng, mask))
    return CsrsPoint(
        ts=ist_timestamp(ts),
        csrs=csrs,
        variance=variance,
        ci_lower=max(0.0, csrs - half),
        ci_upper=min(1.0, csrs + half),
        shapley=(shapley[0], shapley[1], shapley[2]),
        alert_level=level,
        mask=mask,
        effective_weights=ew,
        xi_mode=xi_mode,
        weights_artefact_id=weights.artefact_id,
        reconciliation_mode=mode,
    )


def mock_csrs_stream(
    *,
    start: datetime = DEFAULT_START,
    n: int = 50,
    cadence: timedelta = BAR,
    seed: int = 0,
    mask: AvailabilityMask = (True, True, True),
) -> list[CsrsPoint]:
    rng = np.random.default_rng(seed)
    weights = mock_fusion_weights(seed=seed, mask_profile=mask)
    return [
        mock_csrs_point(start + k * cadence, rng, weights=weights, mask=mask)
        for k in range(n)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit synthetic SERAPH streams as JSONL.")
    parser.add_argument("--ticks", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--hawkes-absent", type=int, default=5,
                        help="ticks of structural Hawkes absence at stream start")
    parser.add_argument("--transient-rate", type=float, default=0.05)
    args = parser.parse_args(argv)

    ticks = mock_tick_stream(
        n_ticks=args.ticks, seed=args.seed,
        hawkes_structural_ticks=args.hawkes_absent,
        transient_rate=args.transient_rate,
    )
    reconciled = mock_reconciled_stream(n=args.ticks, seed=args.seed)
    csrs = mock_csrs_stream(n=args.ticks, seed=args.seed)

    n_unavailable = 0
    for tick in ticks:
        for em in tick:
            n_unavailable += em.kind == "unavailable"
            print(em.model_dump_json(by_alias=True))
    for state in reconciled:
        print(state.model_dump_json(by_alias=True))
    for point in csrs:
        print(point.model_dump_json(by_alias=True))

    print(
        f"[T0] {args.ticks} ticks × 3 pillars ({n_unavailable} unavailable emissions), "
        f"{len(reconciled)} ReconciledState, {len(csrs)} CsrsPoint — all shape-valid.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
