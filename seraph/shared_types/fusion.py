# shared_types — S7/S8: FusionWeights artefact and CsrsPoint (ARCHITECTURE §2)
"""Weight artefact flow is one-directional (D1):

    C10 → FusionWeights (immutable, content-hashed) → C9

C9 consumes this artefact; it never imports C10 and never holds epoch labels.
`weightsArtefactId` and `mask` on every CsrsPoint are the audit trail that
makes FR35/FR36 falsifiable — never simplify these fields away.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from seraph.shared_types.core import (
    AvailabilityMask,
    FrozenModel,
    ISOTimestamp,
    Sha256,
    Simplex3,
    Vec3,
)

EpochId = Literal[
    "gfc_2008", "taper_2013", "ilfs_2018", "covid_2020", "tightening_2022", "tariff_2026"
]


class CalibrationConfig(FrozenModel):
    """Which epochs trained these weights, under what split and loss (D5)."""

    epochs: tuple[EpochId, ...]
    split_policy: Literal["leave_one_epoch_out"] = "leave_one_epoch_out"   # D5
    fold_held_out: EpochId | None = None    # None only for the final refit
    kappa_miss: float
    kappa_fa: float
    mask_profile: AvailabilityMask          # D2 — pillars available in training


class FusionWeights(FrozenModel):
    artefact_id: Sha256
    calibrated_on: CalibrationConfig
    w: tuple[Simplex3, Simplex3, Simplex3]  # w_j per regime j
    ecdf_window_years: Literal[5] = 5


def fusion_weights_artefact_id(
    w: tuple[Simplex3, Simplex3, Simplex3], calibrated_on: CalibrationConfig
) -> str:
    """Content hash binding the weights to their calibration config (D1)."""
    payload = json.dumps(
        {"w": w, "calibratedOn": calibrated_on.model_dump(by_alias=True)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CsrsPoint(FrozenModel):
    """S8 — the scored output. One point, fully auditable."""

    ts: ISOTimestamp
    csrs: float = Field(ge=0.0, le=1.0)
    variance: float = Field(ge=0.0)          # FR29
    ci_lower: float
    ci_upper: float
    shapley: Vec3                            # FR31, PILLAR_ORDER
    alert_level: Literal["green", "amber", "red"]
    mask: AvailabilityMask                   # D2 — provenance
    effective_weights: tuple[Simplex3, Simplex3, Simplex3]  # D2 post-renormalisation
    xi_mode: Literal["hamilton", "uniform"]  # R5 control variant
    weights_artefact_id: Sha256
    reconciliation_mode: Literal["kalman", "forward_fill"]

    @model_validator(mode="after")
    def _ci_ordered(self) -> "CsrsPoint":
        if not (self.ci_lower <= self.csrs <= self.ci_upper):
            raise ValueError(
                "CONSTRAINT_VIOLATED: confidence interval must bracket the CSRS "
                f"(got [{self.ci_lower}, {self.ci_upper}] around {self.csrs})"
            )
        return self
