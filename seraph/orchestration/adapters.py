# Orchestration — persisted pillar output → standardised PillarEmission.
"""Pure row-in / emission-out conversions. No I/O, so the S5 contract is
testable against real rows without a database.

Three rules these functions exist to enforce, each of which was a live risk in
the integration audit:

1. **`ts` is when the value is valid; `tau` is when it was computed.** They are
   equal for the daily pillars (a daily statistic over data ending at the close
   is computable at that close) and they are *not* equal for a pillar whose
   kernel is refitted less often than it is emitted. `PillarObservation`'s own
   validator rejects `tau > ts`; these adapters never manufacture a `tau` to get
   past it.
2. **Absence is emitted, never imputed.** A pillar with no data for a period
   returns `UnavailableEmission`, which C8 handles through D2/D4. Substituting a
   zero, a carried-forward value or a mock is what the `Ok`-carried absence
   design exists to prevent.
3. **λ₁/N is Pillar 2's state and `SCA_t` is not a substitute for it.** If the
   spectrum is missing, `rmt_emission` reports absence. It never quietly falls
   back to the `sca_t` column just because that column is populated — SCA_t
   remains the FR18 supporting statistic and stays persisted, but it is a
   different object with different measured behaviour.
"""
from __future__ import annotations

from typing import Literal, Sequence

import numpy as np

from seraph.orchestration.standardize import standardise
from seraph.shared_types import (
    ObservedEmission,
    PillarEmission,
    PillarObservation,
    SeraphWarning,
    UnavailableEmission,
)

#: NSE close, IST. The daily pillars are valid as of the close of their date and
#: are computable at that close, so `ts == tau` for them.
IST_CLOSE = "T15:30:00+05:30"

Absence = Literal["structural", "transient"]
Reason = Literal["no_data_coverage", "estimation_failed", "insufficient_history"]


def close_ts(date: str) -> str:
    """`YYYY-MM-DD` → the ISO close stamp C8 parses."""
    return f"{date}{IST_CLOSE}"


def _unavailable(pillar: str, ts: str, absence: Absence, reason: Reason):
    return UnavailableEmission(pillar=pillar, ts=ts, absence=absence, reason=reason)


def lam1_share(eigenvalues: Sequence[float] | None) -> float | None:
    """Pillar 2's coupling state from the persisted spectrum.

    `run_rmt.py` stores the spectrum descending, and the FR16 trace identity
    makes `Σλ = N_t` exact, so `λ₁ / N_t` is a pure variance share in [0,1].
    Returns `None` when the spectrum is absent — the caller must then emit
    absence rather than reach for another column.
    """
    if not eigenvalues:
        return None
    ev = list(eigenvalues)
    return float(ev[0]) / float(len(ev))


def rmt_emission(
    *,
    date: str,
    eigenvalues: Sequence[float] | None,
    window: Sequence[float],
    absence: Absence = "transient",
    reason: Reason = "estimation_failed",
) -> tuple[PillarEmission, tuple[SeraphWarning, ...]]:
    """C6 → S5. `window` is the trailing five years of λ₁/N, caller-supplied.

    `estimation_variance` is `None` by design: C6 publishes no per-date sampling
    variance for λ₁/N, and inventing one to satisfy the interface would be
    fabrication. C8 falls back to its own prior, which is the documented path.
    """
    ts = close_ts(date)
    raw = lam1_share(eigenvalues)
    if raw is None:
        return _unavailable("rmt", ts, absence, reason), ()
    value, variance, warns = standardise(
        raw, window=window, raw_variance=None, pillar="rmt")
    return ObservedEmission(obs=PillarObservation(
        pillar="rmt", ts=ts, tau=ts, value=value, estimation_variance=variance,
    )), warns


def hamilton_emission(
    *,
    date: str,
    lsd: float | None,
    raw_variance: float | None,
    window: Sequence[float],
    absence: Absence = "transient",
    reason: Reason = "estimation_failed",
) -> tuple[PillarEmission, tuple[SeraphWarning, ...]]:
    """C7 → S5. `lsd` is `ξ₂ + 2ξ₃`; `raw_variance` is FR23's, in LSD units.

    The variance is carried through the rank transform by the delta method, so
    the value and its uncertainty stay in the same coordinate system — the
    property that makes FR29's `Var(CSRS)` coherent once C8 filters in
    standardised space.

    **Causality is the caller's responsibility.** This function cannot tell a
    filtered ξ from a smoothed one; the pipeline must supply values produced in
    the causal mode for any live or replay claim.
    """
    ts = close_ts(date)
    if lsd is None:
        return _unavailable("hamilton", ts, absence, reason), ()
    value, variance, warns = standardise(
        float(lsd), window=window, raw_variance=raw_variance, pillar="hamilton")
    return ObservedEmission(obs=PillarObservation(
        pillar="hamilton", ts=ts, tau=ts, value=value,
        estimation_variance=variance,
    )), warns


def stress_emission(
    *,
    ts: str,
    tau: str,
    semivariance: float | None,
    window: Sequence[float],
    absence: Absence = "transient",
    reason: Reason = "estimation_failed",
) -> tuple[PillarEmission, tuple[SeraphWarning, ...]]:
    """Downside-semivariance stress state, occupying PILLAR_ORDER slot 3.

    **PROVENANCE WARNING, read before using any output of this.** Slot 3 of
    `PILLAR_ORDER` is named `"hamilton"`, so a `CsrsPoint` whose `mask[2]` is
    `True` because of THIS adapter does **not** mean the Hamilton regime filter
    was available. Distinguishing them properly needs a `PILLAR_ORDER` change in
    `seraph/shared_types/`, which is ask-gated; until that is agreed, callers
    must separate the two by `weights_artefact_id`, and any run using this
    adapter must say so explicitly. Nothing here renames a pillar.

    **Why this replaces Hamilton rather than supplementing it.** Hamilton's
    real-data causal run is unidentified (6/14 nesting violations to
    LR = -2,322.88, 3/14 non-converged folds, 53% near-absorbing dates, NFR17
    0.269 sigma), so slot 3 is empty in practice. A pre-registered study of nine
    candidates over six epochs found downside semivariance the strongest
    contemporaneous detector and nearly orthogonal to the two live pillars:

        T1 detection AUC   semivar 0.7832 | rv_accel 0.7706 | rv_level 0.6098
                           hawkes  0.5933 | CSRS     0.5372 | rmt      0.4283
        correlation        vs rmt 0.06, vs CSRS 0.13, vs hawkes 0.21

    **What it is blind to, stated up front.** It carries NO advance warning:
    its T3 (crisis begins within 15 days, in-crisis days excluded) AUC is
    **0.4928**, i.e. chance, and it led 0 of 6 epochs. It is a *detector* of
    realised downside dispersion. It cannot see stress that has not yet moved
    prices, it says nothing about regime persistence or liquidity recovery
    half-life (which is what Hamilton was for), and it is partly tautological
    against crisis labels because crisis windows are high-volatility windows.

    `estimation_variance` is `None`: this estimator publishes no per-date
    sampling variance and one is not invented. C8 falls back to its own prior.

    Evidence: `docs/evidence/*-17-stress-candidate-study.log`.
    """
    if semivariance is None or not np.isfinite(semivariance):
        return _unavailable("hamilton", ts, absence, reason), ()
    value, variance, warns = standardise(
        float(semivariance), window=window, raw_variance=None, pillar="hamilton")
    return ObservedEmission(obs=PillarObservation(
        pillar="hamilton", ts=ts, tau=tau, value=value,
        estimation_variance=variance,
    )), warns


def hawkes_contagion_emission(
    *,
    ts: str,
    tau: str,
    branching_ratio: float | None,
    window: Sequence[float],
    absence: Absence = "structural",
    reason: Reason = "no_data_coverage",
) -> tuple[PillarEmission, tuple[SeraphWarning, ...]]:
    """C5 → S5 carrying the **UNGATED** contagion state `n/(1−n)`, not FR13-gated MTS.

    **Why this exists, measured not assumed.** `hawkes_emission` below carries
    `MTS_t`, which FR13 sets to exactly 0 whenever the downside-asymmetry test is
    not significant. On the real E6 series that gate is closed on **352 of 473
    windows (74.4%)**. Pushing that through FR28's rolling ECDF is not merely
    lossy, it **inverts the pillar**: because ~70% of any trailing window is
    zeros, a zero maps to the ~68th percentile, so

        gate CLOSED (MTS=0, n=352) -> standardised rank mean 0.6791
        gate OPEN   (MTS>0, n=121) -> standardised rank mean 0.6778
        corr(rank, branching ratio) = -0.4027      <-- DIRECTIONALLY INVERTED

    i.e. "downside pressure is not significantly elevated" would read as
    moderately elevated systemic risk, and higher measured contagion would lower
    the score. The same measurement on the ungated statistic gives
    `corr(rank, n) = +0.5419` (attenuated from 1.0 only by the rolling window's
    intended adaptivity).

    This is not a redefinition of MTS and it does not weaken FR13. C5's own
    engine docstring is explicit that a closed gate is "a normal-mix state, not
    an absence of contagion — the branching ratio is still reported in detail".
    This adapter emits that branching-ratio state and leaves the gate to travel
    as provenance (the `LOW_EVENT_COUNT` warning C5 already raises), rather than
    letting it zero the pillar.

    `estimation_variance` is `None` for the same reason as `hawkes_emission`:
    C5 publishes no per-window variance for `n` and one is not invented here.

    Evidence: `docs/evidence/*-15-csrs-research-*.log`.
    """
    if branching_ratio is None:
        return _unavailable("hawkes", ts, absence, reason), ()
    n = float(branching_ratio)
    if not (0.0 <= n < 1.0):                      # FR11; never emit a bad state
        return _unavailable("hawkes", ts, "transient", "estimation_failed"), ()
    value, variance, warns = standardise(
        n / (1.0 - n), window=window, raw_variance=None, pillar="hawkes")
    return ObservedEmission(obs=PillarObservation(
        pillar="hawkes", ts=ts, tau=tau, value=value,
        estimation_variance=variance,
    )), warns


def hawkes_emission(
    *,
    ts: str,
    tau: str,
    mts: float | None,
    window: Sequence[float],
    absence: Absence = "structural",
    reason: Reason = "no_data_coverage",
) -> tuple[PillarEmission, tuple[SeraphWarning, ...]]:
    """C5 → S5. `MTS_t = n/(1−n)`, a kernel-level contagion-state statistic.

    **`ts` and `tau` are separate here and must stay separate.** The kernel is
    refitted on a trailing multi-day window at a periodic cadence, so a bar
    emitted between refits is valid as of its own bar (`ts`) but was computed at
    the last refit (`tau`). C8's `R(t − τ)` is only honest if that gap is
    reported rather than papered over by setting `tau = ts`.

    MTS_t is a contagion/risk-state diagnostic. It is **not** a forward
    probability of abnormal risk and carries no independent calibration.

    `estimation_variance` is `None`: C5 publishes no per-window variance for
    `n`, and one will not be invented for integration convenience.
    """
    if mts is None:
        return _unavailable("hawkes", ts, absence, reason), ()
    value, variance, warns = standardise(
        float(mts), window=window, raw_variance=None, pillar="hawkes")
    return ObservedEmission(obs=PillarObservation(
        pillar="hawkes", ts=ts, tau=tau, value=value,
        estimation_variance=variance,
    )), warns
