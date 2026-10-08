# shared_types — S6: C8 → C9 (ARCHITECTURE §2)
"""ReconciledState — the Kalman layer's output.

Boundary invariant (SPEC O6 as a runtime assertion): trace(P) is
non-decreasing between updates and strictly decreasing at an update arrival.
That temporal invariant is C8's to enforce; this model enforces the pointwise
one — P symmetric PSD, asserted, not assumed.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from seraph.shared_types.core import (
    AvailabilityMask,
    FrozenModel,
    ISOTimestamp,
    Mat3,
    Vec3,
)

_PSD_TOL = 1e-9


class ReconciledState(FrozenModel):
    ts: ISOTimestamp
    x_hat: Vec3                            # PILLAR_ORDER
    P: Mat3 = Field(alias="P")             # symmetric PSD — asserted below
    tau_last_update: tuple[ISOTimestamp | None, ISOTimestamp | None, ISOTimestamp | None]
    mask: AvailabilityMask                 # D2 — set by C8, consumed by C9
    noise_saturated: tuple[bool, bool, bool] = (False, False, False)  # D4
    mode: Literal["kalman", "forward_fill"]  # FR27

    @model_validator(mode="after")
    def _p_symmetric_psd(self) -> "ReconciledState":
        p = np.asarray(self.P, dtype=float)
        if not np.allclose(p, p.T, atol=1e-8):
            raise ValueError("CONSTRAINT_VIOLATED: P is not symmetric")
        eigmin = float(np.linalg.eigvalsh(p).min())
        if eigmin < -_PSD_TOL:
            raise ValueError(
                f"CONSTRAINT_VIOLATED: P is not PSD (min eigenvalue {eigmin:.3e})"
            )
        return self
