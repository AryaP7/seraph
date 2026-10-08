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
