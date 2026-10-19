# C10 — Validation Harness (FR30, FR32-FR37)
"""Evaluates scoring configurations against labelled epochs and emits
calibrated weights. Owns the epoch labels, the D5 split policy, the loss L,
the FusionWeights artefact and the ablation runner.

That last clause was aspirational until T10: `run_experiment` is the FR35
Table A/B/C runner, and `EvaluationRow` — this component's declared output in
ARCHITECTURE §2 — had no producer anywhere in the repository before it.

The runner and its three companions are re-exported here so the package
interface matches what the docstring claims:

* `run_experiment` — FR35/FR36, leave-one-epoch-out under a committed design;
* `run_transfer` — FR37/O9, the same weights on another market with no refit;
* `sweep` — FR34, the one of four sensitivity axes that lives in this layer;
* `save_report` / `load_report` / `render_report` — FR38 artefacts.

`run_experiment` computes nothing without a committed `preregistration.json`
(D5(d)), which DR-05 step 5 leaves to a person.
"""
from seraph.validation.ablation import restrict, score_subset, subset_mask
from seraph.validation.experiment import (
    Dataset,
    ExperimentReport,
    ExperimentRow,
    LabelledEpoch,
    Observation,
    UnavailableReason,
)
from seraph.validation.experiment import run as run_experiment
from seraph.validation.experiment_store import (
    archive_rows,
    artefact_id,
)
from seraph.validation.experiment_store import load as load_report
from seraph.validation.experiment_store import render as render_report
from seraph.validation.experiment_store import save as save_report
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
    TABLE_B_SCOPES,
    commit,
    configuration_list,
    content_hash,
    verify,
)
from seraph.validation.sensitivity import PILLAR_AXES, SensitivityReport
from seraph.validation.sensitivity import sweep
from seraph.validation.transfer import (
    CANDIDATE_MARKETS,
    TransferResult,
    weights_are_bit_identical,
)

# Deliberately `run_transfer`, not `transfer`: the function and its module
# share a name, so re-exporting it as `transfer` made
# `from seraph.validation import transfer` return the FUNCTION and shadow the
# module, while `import seraph.validation.transfer` still gave the module.
# Fourteen tests failed on `'function' object has no attribute 'transfer'`.
from seraph.validation.transfer import transfer as run_transfer

__all__ = [
    "CANDIDATE_MARKETS",
    "Dataset",
    "EPOCHS",
    "ExperimentReport",
    "ExperimentRow",
    "HAWKES_EPOCHS",
    "LabelledEpoch",
    "Observation",
    "PILLAR_AXES",
    "PRE_HAWKES_EPOCHS",
    "SensitivityReport",
    "TABLE_B_SCOPES",
    "TransferResult",
    "UnavailableReason",
    "archive_rows",
    "artefact_id",
    "auc",
    "calibrate",
    "calibration_loss",
    "commit",
    "configuration_list",
    "content_hash",
    "leakage_check",
    "load_report",
    "mean_lead_time",
    "precision_at_recall",
    "render_report",
    "restrict",
    "run_experiment",
    "run_transfer",
    "save_report",
    "score_subset",
    "subset_mask",
    "sweep",
    "verify",
    "weights_are_bit_identical",
]
