# C10 — Validation Harness (FR32–FR37): the Table A/B/C experiment runner.
"""Assembles the primitives that already existed into one pre-registered run.

Every piece this needs was already written and had no caller: `score_subset`
(the D2-mask ablation), `calibrate` (FR30), `auc` / `mean_lead_time` /
`precision_at_recall` (FR33), `leakage_check` (D5), `configuration_list`
(FR35) and the epoch labels. `EvaluationRow` — C10's own declared output type
— had no producer anywhere in the repository. This is that producer.

Three things the runner refuses to do, because each is a way a runner can
quietly manufacture a result:

* **Compute before the design is committed.** D5(d): a result whose hash does
  not match the committed pre-registration is not reportable. `run()` verifies
  the file and takes every parameter that could flatter a number from it, so a
  run cannot evaluate a split, subset or threshold the design never declared.
* **Turn an absence into a number.** A subset naming a pillar the epoch has no
  coverage for, a fold with one class, a failed calibration and a leaking fold
  are four different absences, and each gets its own explicit row with its own
  reason. An unavailable row **is a result** — it is what FR35's table honestly
  contains in that cell — not an error, and never 0.5.
* **Train on what the test fold cannot see.** Calibration runs on states
  restricted by the same subset mask the test fold is scored under, and
  `leakage_check` reads the weight artefact's own recorded training epochs
  rather than what the runner believes it did.

The fold counts differ by table on purpose (4 / 2 / 6) and the three tables
answer three different questions. `ExperimentReport` carries that warning
beside the rows rather than leaving it in a document, because the one thing a
reader will do with three tables is rank them together.

**A single-pillar row is invariant to both the weights and the xi mode**, and
a reader needs to know that before comparing columns. Under a one-pillar mask
every regime row of the weight matrix renormalises to the same indicator
vector, so C9's `a = xi @ effective` collapses to that indicator and
`CSRS = x_hat[k]` exactly — whatever the weights are and whichever xi mode
ran. Two consequences, both tested:

* The R5 control (`xi_mode="hamilton"` against `"uniform"`) is **structurally
  incapable of diverging** on a single-pillar subset. ARCHITECTURE R5 aims it
  at "Hamilton-standalone", which is precisely the case where it cannot say
  anything; it is informative only for the multi-pillar subsets, where
  `rmt+hamilton` does move. Identical columns there are the arithmetic, not
  agreement between two ways of weighting.
* A single-pillar AUC is just that pillar's own discriminative power, so those
  rows carry no information about fusion. They are still calibrated and still
  reported, because leaving a cell blank in an ablation table because it is
  uninformative is how an ablation stops being descriptive.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

import numpy as np

from seraph.shared_types import (
    ContractViolation,
    EpochId,
    Err,
    FrozenModel,
    FusionWeights,
    Ok,
    PillarId,
    ReconciledState,
    Sha256,
    Simplex3,
    err,
    ok,
)
from seraph.validation.ablation import restrict, score_subset, subset_mask
from seraph.validation.harness import (
    auc,
    calibrate,
    leakage_check,
    mean_lead_time,
    precision_at_recall,
)
from seraph.validation.preregistration import verify as verify_design

ReconciliationMode = Literal["kalman", "forward_fill"]
XiMode = Literal["hamilton", "uniform"]
TableId = Literal["A", "B", "C"]

#: Why a cell of the table holds no number. Closed on purpose: an open string
#: here is how a runner ends up with twelve spellings of "no data" and a reader
#: cannot tell which absences are the same absence.
UnavailableReason = Literal[
    "structural_pillar_absence",   # the subset names a pillar the epoch lacks
    "reconciliation_mode_absent",  # FR36 wants both modes; this one is missing
    "insufficient_training_sample",
    "insufficient_test_sample",
    "calibration_failed",
    "train_test_overlap",          # D5 machine check — not reportable
    "scoring_failed",
    "single_class_fold",           # AUC undefined; 0.5 would be a fabrication
]


# --- the dataset the runner consumes -------------------------------------

@dataclass(frozen=True)
class Observation:
    """One scored instant and its FR32 label."""
    state: ReconciledState
    xi: Simplex3
    label: int  # 1 inside the labelled crisis window, else 0


@dataclass(frozen=True)
class LabelledEpoch:
    """One epoch's observations, by reconciliation mode, plus its coverage.

    `pillar_coverage` is supplied by the dataset, not inferred by the runner.
    That is deliberate: whether Hawkes exists before 2015 is a property of the
    data, and a runner that guessed it could silently evaluate a subset on an
    epoch that has nothing to evaluate it with.
    """
    epoch: EpochId
    pillar_coverage: frozenset[PillarId]
    observations: Mapping[ReconciliationMode, tuple[Observation, ...]]


Dataset = Mapping[EpochId, LabelledEpoch]


# --- what one cell of a table contains -----------------------------------

class ExperimentRow(FrozenModel):
    """One configuration on one fold — measured or explicitly unavailable.

    A superset of `EvaluationRow`, C10's published shape, which cannot express
    two things this runner produces: `table="C"` (created by DR-05, whose
    `Literal` was never widened to match) and an unavailable cell (which FR35's
    tables need and the published row has no field for). `as_evaluation_row()`
    converts the rows the published contract does cover, so nothing here
    silently redefines it.
    """
    table: TableId
    pillar_subset: tuple[PillarId, ...]
    reconciliation_mode: ReconciliationMode
    xi_mode: XiMode
    epoch: EpochId
    folds: int
    availability: Literal["measured", "unavailable"]
    pre_registration_hash: Sha256

    # measured only
    auc: float | None = None
    mean_lead_time_days: float | None = None
    precision_at_fixed_recall: float | None = None
    weights_artefact_id: Sha256 | None = None
    leakage_check: Literal["clean", "TRAIN_TEST_OVERLAP"] | None = None
    train_epochs: tuple[EpochId, ...] = ()

    # unavailable only
    unavailable_reason: UnavailableReason | None = None
    detail: str | None = None

    def as_evaluation_row(self):
        """The published `EvaluationRow`, or None when it cannot express this.

        None for Table C and for every unavailable row. That is not a silent
        drop: `ExperimentReport.unpublishable_rows` counts them, so the gap
        between what was measured and what the declared contract can carry is
        visible rather than inferred from a short table.
        """
        from seraph.shared_types import EvaluationRow

        if self.availability != "measured" or self.table not in ("A", "B"):
            return None
        return EvaluationRow(
            pillar_subset=self.pillar_subset,
            reconciliation_mode=self.reconciliation_mode,
            xi_mode=self.xi_mode,
            epoch=self.epoch,
            table=self.table,
            auc=float(self.auc),
            mean_lead_time_days=float(self.mean_lead_time_days),
            precision_at_fixed_recall=float(self.precision_at_fixed_recall),
            weights_artefact_id=self.weights_artefact_id,
            leakage_check=self.leakage_check or "clean",
            pre_registration_hash=self.pre_registration_hash,
        )


def _unavailable(cfg: dict, epoch: EpochId, xi_mode: XiMode, digest: Sha256,
                 reason: UnavailableReason, detail: str) -> ExperimentRow:
    return ExperimentRow(
        table=cfg["table"], pillar_subset=tuple(cfg["pillarSubset"]),
        reconciliation_mode=cfg["reconciliationMode"], xi_mode=xi_mode,
        epoch=epoch, folds=cfg["folds"], availability="unavailable",
        pre_registration_hash=digest, unavailable_reason=reason, detail=detail)


# --- one fold ------------------------------------------------------------

def _fold(
    *,
    cfg: dict,
    epoch: EpochId,
    xi_mode: XiMode,
    dataset: Dataset,
    digest: Sha256,
    amber_threshold: float,
    kappa_miss: float,
    kappa_fa: float,
    max_iterations: int,
    target_recall: float,
) -> tuple[ExperimentRow, FusionWeights | None]:
    """Leave-one-epoch-out: train on the configuration's other epochs.

    Returns the fitted artefact alongside the row. FR37's transfer test needs
    the exact artefact, not a fresh fit of the same shape — O9's acceptance is
    "weight vectors bit-identical between NSE and second-market runs", which
    is only checkable if the second run can reuse the first one's object.
    """
    subset = tuple(cfg["pillarSubset"])
    mode: ReconciliationMode = cfg["reconciliationMode"]
    epochs = tuple(cfg["epochs"])
    def miss(reason: UnavailableReason, detail: str):
        """No artefact: there was nothing to fit, or the fit failed."""
        return _unavailable(cfg, epoch, xi_mode, digest, reason,
                            detail), None


    held = dataset.get(epoch)
    if held is None:
        return miss("insufficient_test_sample",
                    f"the dataset has no epoch {epoch!r}")

    absent = sorted(set(subset) - set(held.pillar_coverage))
    if absent:
        return miss("structural_pillar_absence",
                    f"{epoch} has no coverage for {', '.join(absent)}")

    if mode not in held.observations:
        return miss("reconciliation_mode_absent",
                    f"{epoch} has no {mode} states; FR36 needs both modes")

    test = held.observations[mode]
    if not test:
        return miss("insufficient_test_sample",
                    f"{epoch} has no {mode} observations")

    train_epochs: list[EpochId] = []
    train: list[Observation] = []
    for other in epochs:
        if other == epoch:
            continue
        block = dataset.get(other)
        if block is None or mode not in block.observations:
            continue
        if set(subset) - set(block.pillar_coverage):
            # A training epoch that cannot carry the subset is skipped rather
            # than contributing states whose mask differs from the test fold's.
            continue
        if block.observations[mode]:
            train_epochs.append(other)
            train.extend(block.observations[mode])

    if not train:
        return miss("insufficient_training_sample",
                    f"no usable {mode} training data outside {epoch}")

    # Calibrate under the SAME restriction the test fold is scored under.
    fitted = calibrate(
        states=[restrict(o.state, subset) for o in train],
        xis=[o.xi for o in train],
        labels=[o.label for o in train],
        train_epochs=tuple(train_epochs), held_out=epoch,
        kappa_miss=kappa_miss, kappa_fa=kappa_fa,
        mask_profile=subset_mask(subset), max_iterations=max_iterations)
    if fitted.status == "error":
        return miss("calibration_failed",
                    f"calibration returned {fitted.error.kind}")
    weights: FusionWeights = fitted.value

    leak = leakage_check(weights, [epoch])
    if leak != "clean":
        return miss("train_test_overlap",
                    f"{epoch} appears in the artefact's own training epochs")

    scores = []
    for obs in test:
        scored = score_subset(reconciled=obs.state, xi=obs.xi, weights=weights,
                              subset=subset, xi_mode=xi_mode)
        if scored.status == "error":
            return miss("scoring_failed",
                        f"score returned {scored.error.kind} at {obs.state.ts}")
        scores.append(scored.value.csrs)

    labels = [o.label for o in test]
    measured = auc(scores, labels)
    if not np.isfinite(measured):
        pos = sum(1 for v in labels if v == 1)
        return miss("single_class_fold",
                    f"{pos} positive of {len(labels)}; AUC is undefined")

    # A NaN lead time stays a NaN MEASUREMENT rather than becoming an
    # unavailable row: it means the threshold was never crossed before onset,
    # which is a missed warning and a real finding about the configuration.
    # Only an undefined AUC makes the cell itself empty.
    return ExperimentRow(
        table=cfg["table"], pillar_subset=subset, reconciliation_mode=mode,
        xi_mode=xi_mode, epoch=epoch, folds=cfg["folds"],
        availability="measured", pre_registration_hash=digest,
        auc=float(measured),
        mean_lead_time_days=float(mean_lead_time(scores, labels,
                                                 amber_threshold)),
        precision_at_fixed_recall=float(precision_at_recall(scores, labels,
                                                           target_recall)),
        weights_artefact_id=weights.artefact_id, leakage_check=leak,
        train_epochs=tuple(train_epochs)), weights


# --- the run -------------------------------------------------------------

class ConfigurationSummary(FrozenModel):
    """One configuration's result across its own folds.

    `declared_folds` and `measured_folds` are both here and are not the same
    number. A Table A subset naming Hawkes declares four folds and may measure
    fewer; reporting only the mean would hide that, and reporting only the
    count would hide which absence caused it — hence `unavailable_folds`.
    """
    table: TableId
    pillar_subset: tuple[PillarId, ...]
    reconciliation_mode: ReconciliationMode
    xi_mode: XiMode
    declared_folds: int
    measured_folds: int
    mean_auc: float
    auc_min: float | None
    auc_max: float | None
    per_fold_auc: tuple[float, ...]
    mean_lead_time_days: float
    unavailable_folds: dict[str, int]

    @property
    def complete(self) -> bool:
        return self.measured_folds == self.declared_folds


class ExperimentReport(FrozenModel):
    pre_registration_hash: Sha256
    table_b_scope: str
    rows: tuple[ExperimentRow, ...]
    comparability: str
    unpublishable_rows: int
    #: The declared optimiser budget these rows were produced under. Carried
    #: on the report because a plumbing run and a full evaluation differ in
    #: exactly this number, and a reader holding only the rows cannot tell.
    calibration_max_iter: int
    #: The fitted artefacts, by id. FR37 transfers these exact objects;
    #: O9 asks for weight vectors bit-identical between the NSE run and
    #: the second market, which a re-fit of the same shape would not be.
    weight_artefacts: dict[str, FusionWeights] = {}
    note: str = ""

    def by_table(self) -> dict[str, tuple[ExperimentRow, ...]]:
        out: dict[str, list[ExperimentRow]] = {}
        for row in self.rows:
            out.setdefault(row.table, []).append(row)
        return {t: tuple(r) for t, r in sorted(out.items())}

    def measured(self) -> tuple[ExperimentRow, ...]:
        return tuple(r for r in self.rows if r.availability == "measured")

    def unavailable(self) -> tuple[ExperimentRow, ...]:
        return tuple(r for r in self.rows if r.availability == "unavailable")

    def configurations(self) -> tuple[ConfigurationSummary, ...]:
        """One summary per configuration, each a mean over ITS OWN folds.

        The unit of aggregation is the configuration, never the table. D5 asks
        for "mean AUC with per-fold spread", and a configuration's folds are
        the only thing a mean is defined over: averaging a table pools rows
        from different subsets, modes and xi modes, which answers no question
        anyone asked and reads as though it ranked them.
        """
        groups: dict[tuple, list[ExperimentRow]] = {}
        for row in self.rows:
            key = (row.table, row.pillar_subset, row.reconciliation_mode,
                   row.xi_mode)
            groups.setdefault(key, []).append(row)

        out = []
        for (table, subset, mode, xi_mode), rows in sorted(
                groups.items(), key=lambda kv: (kv[0][0], len(kv[0][1]),
                                                kv[0][1], kv[0][2], kv[0][3])):
            vals = [float(r.auc) for r in rows if r.availability == "measured"]
            leads = [float(r.mean_lead_time_days) for r in rows
                     if r.availability == "measured"
                     and np.isfinite(r.mean_lead_time_days)]
            reasons: dict[str, int] = {}
            for r in rows:
                if r.availability == "unavailable":
                    k = str(r.unavailable_reason)
                    reasons[k] = reasons.get(k, 0) + 1
            out.append(ConfigurationSummary(
                table=table, pillar_subset=subset, reconciliation_mode=mode,
                xi_mode=xi_mode,
                declared_folds=rows[0].folds, measured_folds=len(vals),
                mean_auc=float(np.mean(vals)) if vals else float("nan"),
                auc_min=min(vals) if vals else None,
                auc_max=max(vals) if vals else None,
                per_fold_auc=tuple(vals),
                mean_lead_time_days=(float(np.mean(leads)) if leads
                                     else float("nan")),
                unavailable_folds=dict(sorted(reasons.items()))))
        return tuple(out)

    def absence_census(self) -> dict[str, int]:
        """How many cells each kind of absence accounts for."""
        out: dict[str, int] = {}
        for row in self.unavailable():
            key = str(row.unavailable_reason)
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items()))


def run(
    *,
    dataset: Dataset,
    preregistration: Path,
    tables: Sequence[str] = ("A", "B", "C"),
    target_recall: float = 0.8,
) -> Ok[ExperimentReport] | Err:
    """Run the committed design against `dataset`. D5(d) is enforced here.

    The design file is the authority for every parameter that could flatter a
    result — the split policy, the loss ratios, the amber threshold and the
    configuration list itself. None of them is an argument to this function,
    because an argument is something a caller can change after seeing a number.
    """
    path = Path(preregistration)
    if not path.exists():
        return err(ContractViolation(
            field="preregistration",
            detail=(f"{path} does not exist. D5(d): the design is committed by "
                    f"a person before the first AUC is computed. See DR-05 "
                    f"step 5 — commit() refuses to overwrite, so committing is "
                    f"a deliberate one-time act, not a build step.")))

    intact, digest = verify_design(path)
    if not intact:
        return err(ContractViolation(
            field="preregistration",
            detail=(f"{path} does not match its own recorded hash; the design "
                    f"was edited after it was committed, so no result produced "
                    f"under it is reportable")))

    blob = json.loads(path.read_text(encoding="utf-8"))
    design = blob.get("design", {})
    configs = design.get("configurations", [])
    if not configs:
        return err(ContractViolation(
            field="preregistration.configurations",
            detail="the committed design lists no configurations"))

    amber = design.get("amberThreshold")
    if not isinstance(amber, (int, float)) or isinstance(amber, bool):
        return err(ContractViolation(
            field="preregistration.amberThreshold",
            detail=("the committed design carries no numeric amberThreshold. "
                    "The lead-time metric needs the threshold the design fixed "
                    "and must not choose its own")))

    kappa_miss = float(design.get("kappaMiss", 10.0))
    kappa_fa = float(design.get("kappaFa", 1.0))
    max_iterations = int(design.get("calibrationMaxIter", 1200))

    rows: list[ExperimentRow] = []
    artefacts: dict[str, FusionWeights] = {}
    for cfg in configs:
        if cfg["table"] not in tables:
            continue
        for xi_mode in cfg.get("xiModes", ["hamilton"]):
            for epoch in cfg["epochs"]:
                row, fitted = _fold(
                    cfg=cfg, epoch=epoch, xi_mode=xi_mode, dataset=dataset,
                    digest=digest, amber_threshold=float(amber),
                    kappa_miss=kappa_miss, kappa_fa=kappa_fa,
                    max_iterations=max_iterations,
                    target_recall=target_recall)
                rows.append(row)
                if fitted is not None:
                    artefacts[fitted.artefact_id] = fitted

    unpublishable = sum(1 for r in rows if r.as_evaluation_row() is None)
    return ok(ExperimentReport(
        pre_registration_hash=digest,
        table_b_scope=design.get("tableBScope", "unrecorded"),
        rows=tuple(rows),
        comparability=design.get("tableComparability", ""),
        unpublishable_rows=unpublishable,
        calibration_max_iter=max_iterations,
        weight_artefacts=artefacts,
        note=("rows the declared EvaluationRow contract cannot carry are "
              "counted, not dropped: Table C has no place in its table "
              "Literal, and an unavailable cell has no fields there")))
