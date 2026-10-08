# C10 — Validation Harness (FR30, FR32-FR37)
"""Evaluates scoring configurations against labelled epochs and emits
calibrated weights. Owns the epoch labels, the D5 split policy, the loss L,
the FusionWeights artefact and the ablation runner."""
from seraph.validation.ablation import score_subset, subset_mask
from seraph.validation.harness import (
    auc,
    calibrate,
    calibration_loss,
    leakage_check,
    mean_lead_time,
    precision_at_recall,
)
from seraph.validation.preregistration import (
    EPOCHS,
    HAWKES_EPOCHS,
    PRE_HAWKES_EPOCHS,
    commit,
    configuration_list,
    content_hash,
    verify,
)

__all__ = [
    "EPOCHS",
    "HAWKES_EPOCHS",
    "PRE_HAWKES_EPOCHS",
    "auc",
    "calibrate",
    "calibration_loss",
    "commit",
    "configuration_list",
    "content_hash",
    "leakage_check",
    "mean_lead_time",
    "precision_at_recall",
    "score_subset",
    "subset_mask",
    "verify",
]
