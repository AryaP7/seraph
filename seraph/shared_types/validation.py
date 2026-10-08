# shared_types — S9: C10 evaluation rows (ARCHITECTURE §2, E13)
"""EvaluationRow — one ablation configuration on one epoch.

`leakage_check` is a machine check (intersect weights.calibratedOn.epochs with
the test epochs) — a non-clean row must not be reported. `pre_registration_hash`
gates reportability per D5(d).
"""
from __future__ import annotations

from typing import Literal

from seraph.shared_types.core import FrozenModel, PillarId, Sha256
from seraph.shared_types.fusion import EpochId


class EvaluationRow(FrozenModel):
    pillar_subset: tuple[PillarId, ...]
    reconciliation_mode: Literal["kalman", "forward_fill"]   # FR36
    xi_mode: Literal["hamilton", "uniform"]                  # R5 control
    epoch: EpochId
    table: Literal["A", "B"]                                 # FR35
    auc: float
    mean_lead_time_days: float
    precision_at_fixed_recall: float
    weights_artefact_id: Sha256
    leakage_check: Literal["clean", "TRAIN_TEST_OVERLAP"]    # D5 machine check
    pre_registration_hash: Sha256                            # D5(d)
