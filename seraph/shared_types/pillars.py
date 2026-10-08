# shared_types — S5, the critical seam: Pillars → C8 (ARCHITECTURE §2)
"""PillarEmission and per-pillar detail shapes.

Absence is a first-class VALUE, not an error and not a zero:
`structural` absence means the pillar cannot exist for this period at all
(e.g. Hawkes pre-2015) and drives D2 mask exclusion; `transient` absence means
this update failed — D4 age-inflation applies and the pillar stays in the
mask. An `unavailable` emission is therefore carried inside `Ok`, never `Err`.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from seraph.shared_types.core import (
    FrozenModel,
    ISOTimestamp,
    PillarId,
    SectorId,
    Simplex3,
)


class PillarObservation(FrozenModel):
    """`tau` is when the pillar was ACTUALLY COMPUTED — never the query time,
    never a forward-filled time. C8's R^(p)(t − τ) is only correct if honest."""

    pillar: PillarId
    ts: ISOTimestamp                       # valid AS OF
    tau: ISOTimestamp                      # COMPUTED at
    value: float                           # MTS_t | lambda_1/N | LSD_t
    estimation_variance: float | None = None   # FR23 (Hamilton); None → C8 prior

    @model_validator(mode="after")
    def _tau_not_in_future(self) -> "PillarObservation":
        # Lexicographic comparison is chronological for this fixed format.
        if self.tau > self.ts:
            raise ValueError(
                f"CONTRACT_VIOLATION: tau ({self.tau}) > ts ({self.ts}) — "
                "a pillar cannot be computed after the time it is valid for"
            )
        return self


class ObservedEmission(FrozenModel):
    kind: Literal["observed"] = "observed"
    obs: PillarObservation


class UnavailableEmission(FrozenModel):
    kind: Literal["unavailable"] = "unavailable"
    pillar: PillarId
    ts: ISOTimestamp
    absence: Literal["structural", "transient"]
    reason: Literal["no_data_coverage", "estimation_failed", "insufficient_history"]


PillarEmission = Annotated[
    Union[ObservedEmission, UnavailableEmission], Field(discriminator="kind")
]


# --- detail shapes: ride alongside, never inside, the common shape --------


class SectorFlag(FrozenModel):
    sector_id: SectorId
    n: float                                # sector-level branching ratio
    flag: Literal["none", "amber"]


class HawkesDetail(FrozenModel):
    """C5 detail (FR10–FR15)."""

    branching_ratio: float = Field(lt=1.0)  # FR11 invariant, post-regularisation
    asymmetry_ratio: float
    jump_count_neg: int
    jump_count_pos: int
    sector_flags: tuple[SectorFlag, ...] = ()
    branching_matrix: tuple[tuple[float, ...], ...] = ()


class RmtDetail(FrozenModel):
    """C6 detail (FR16–FR19, D3)."""

    f_t: float
    v_eig_t: float
    omega_t: float
    mp_p_value: float
    lambda_minus: float
    lambda_plus: float
    leading_eigenvector: tuple[float, ...] = ()
    common_support_fraction: float = 1.0    # D3
    rebalance_adjacent: bool = False        # D3


class HamiltonDetail(FrozenModel):
    """C7 detail (FR20–FR24)."""

    xi: Simplex3                            # [tranquil, stressed, crisis]
    p_hat_22: float
    p_hat_33: float
    tau_half_stressed: float
    tau_half_crisis: float
