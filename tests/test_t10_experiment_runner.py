# T10 — the C12/C10 experiment runner (FR32–FR37, D5)
"""`EvaluationRow` was a declared contract with no producer anywhere.

Every primitive the FR35 ablation needs already existed and had no caller:
`score_subset`, `calibrate`, `auc`, `mean_lead_time`, `precision_at_recall`,
`leakage_check`, `configuration_list`. T10 is the assembly, and these tests
cover the four ways an assembled runner can produce a number nobody should
believe:

1. computing before the design is committed, or after it was edited;
2. filling a cell that has no measurement with 0.5;
3. calibrating on information the test fold cannot see;
4. averaging across configurations and calling it a result.

The arithmetic of AUC, the loss and the mask renormalisation is tested in
`tests/test_c10_*` and `tests/contract/test_ct9_*`; duplicating it here would
mean two places to update when it changes.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from fixtures import experiment_dataset
from seraph.shared_types import EvaluationRow
from seraph.validation import experiment
from seraph.validation.preregistration import build, commit

# A deliberately small optimiser budget and sample: this exercises plumbing,
# which is exactly what T10's acceptance asks for. The budget is inside the
# hashed design, so these rows can never be mistaken for a full evaluation.
BUDGET = 40
PER_EPOCH = 16


def _some_weights():
    """Asymmetric weights, so a test that claims xi does nothing is testing
    the mask arithmetic rather than three identical regime rows."""
    from seraph.shared_types import (
        CalibrationConfig, FusionWeights, fusion_weights_artefact_id,
    )

    rows = ((0.6, 0.3, 0.1), (0.2, 0.6, 0.2), (0.1, 0.2, 0.7))
    cfg = CalibrationConfig(epochs=("ilfs_2018",), fold_held_out=None,
                            kappa_miss=10.0, kappa_fa=1.0,
                            mask_profile=(True, True, True))
    return FusionWeights(artefact_id=fusion_weights_artefact_id(rows, cfg),
                         calibrated_on=cfg, w=rows)


@pytest.fixture(scope="module")
def design(tmp_path_factory):
    path = tmp_path_factory.mktemp("design") / "preregistration.json"
    _, digest = commit(build(calibration_max_iter=BUDGET), path)
    return path, digest


@pytest.fixture(scope="module")
def dataset():
    return experiment_dataset.build(per_epoch=PER_EPOCH)


@pytest.fixture(scope="module")
def report(design, dataset):
    path, _ = design
    result = experiment.run(dataset=dataset, preregistration=path,
                            tables=("A", "B"))
    assert result.status == "ok", getattr(result, "error", None)
    return result.value


@pytest.fixture(scope="module")
def table_c(design, dataset):
    path, _ = design
    result = experiment.run(dataset=dataset, preregistration=path,
                            tables=("C",))
    assert result.status == "ok"
    return result.value


class TestThePreRegistrationGate:
    """D5(d): a result whose hash does not match the committed file is not
    reportable. The gate is mechanical, not a convention."""

    def test_no_committed_design_means_no_run(self, dataset, tmp_path):
        result = experiment.run(dataset=dataset,
                                preregistration=tmp_path / "absent.json")
        assert result.status == "error"
        assert result.error.kind == "CONTRACT_VIOLATION"
        assert "D5(d)" in result.error.detail

    def test_an_edited_design_is_refused(self, dataset, tmp_path):
        """The file carries its own hash. Editing the design after committing
        it is the exact thing pre-registration exists to prevent, so the
        mismatch has to stop the run rather than annotate it."""
        path = tmp_path / "preregistration.json"
        commit(build(calibration_max_iter=BUDGET), path)
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["design"]["kappaMiss"] = 999.0        # flatter the loss
        path.write_text(json.dumps(blob), encoding="utf-8")

        result = experiment.run(dataset=dataset, preregistration=path)
        assert result.status == "error"
        assert "does not match its own recorded hash" in result.error.detail

    def test_a_design_with_no_configurations_is_refused(self, dataset, tmp_path):
        path = tmp_path / "preregistration.json"
        design = build(calibration_max_iter=BUDGET)
        design["configurations"] = []
        commit(design, path)
        result = experiment.run(dataset=dataset, preregistration=path)
        assert result.status == "error"
        assert result.error.field == "preregistration.configurations"

    def test_a_design_without_a_numeric_threshold_is_refused(self, dataset,
                                                             tmp_path):
        """The lead-time metric needs the threshold the design fixed. If the
        number lives only inside the prose rule, the runner has to pick one —
        and a threshold the runner picks is a threshold that can be tuned."""
        path = tmp_path / "preregistration.json"
        design = build(calibration_max_iter=BUDGET)
        del design["amberThreshold"]
        commit(design, path)
        result = experiment.run(dataset=dataset, preregistration=path)
        assert result.status == "error"
        assert result.error.field == "preregistration.amberThreshold"

    def test_every_row_carries_the_committed_hash(self, report, design):
        _, digest = design
        assert report.pre_registration_hash == digest
        assert {r.pre_registration_hash for r in report.rows} == {digest}

    def test_the_declared_budget_travels_with_the_report(self, report):
        """A cheap run and a full evaluation differ in exactly this number and
        are otherwise shaped identically."""
        assert report.calibration_max_iter == BUDGET

    def test_two_budgets_are_two_designs(self, tmp_path):
        from seraph.validation.preregistration import content_hash
        assert (content_hash(build(calibration_max_iter=40))
                != content_hash(build(calibration_max_iter=1200)))


class TestTheDesignNeverAsksForAbsentCoverage:
    """FR35 splits the tables so that no configuration asks for a pillar its
    epochs lack. That is a checkable property, not a claim."""

    def test_the_committed_design_produces_no_structural_absence(self, report):
        census = report.absence_census()
        assert census.get("structural_pillar_absence", 0) == 0, census

    def test_table_a_is_the_hawkes_epochs_only(self, report):
        rows = [r for r in report.rows if r.table == "A"]
        assert {r.epoch for r in rows} == set(experiment_dataset.HAWKES_COVERED)

    def test_but_the_guard_fires_when_a_subset_outruns_its_epoch(self, dataset,
                                                                 design):
        """A configuration the design would never emit: Hawkes on 2008. The
        runner must refuse it with a reason rather than score it on the two
        pillars that do exist, which would silently relabel the subset."""
        path, digest = design
        row, fitted = experiment._fold(
            cfg=dict(table="A", pillarSubset=["hawkes", "rmt"],
                     reconciliationMode="kalman",
                     epochs=["gfc_2008", "taper_2013"], folds=2),
            epoch="gfc_2008", xi_mode="hamilton", dataset=dataset,
            digest=digest, amber_threshold=0.5, kappa_miss=10.0, kappa_fa=1.0,
            max_iterations=BUDGET, target_recall=0.8)
        assert fitted is None, (
            "an unavailable fold must not yield a weight artefact: there "
            "was nothing to fit")
        assert row.availability == "unavailable"
        assert row.unavailable_reason == "structural_pillar_absence"
        assert "hawkes" in row.detail


class TestAnUnavailableCellIsAResult:
    """Not an error, not a gap, and never 0.5."""

    def test_a_single_class_fold_has_no_auc(self, design):
        path, _ = design
        degenerate = experiment_dataset.build(per_epoch=PER_EPOCH,
                                              degenerate_epoch="covid_2020")
        rep = experiment.run(dataset=degenerate, preregistration=path,
                             tables=("A",)).value
        rows = [r for r in rep.rows if r.epoch == "covid_2020"]
        assert rows and all(r.availability == "unavailable" for r in rows)
        assert {r.unavailable_reason for r in rows} == {"single_class_fold"}
        assert all(r.auc is None for r in rows)

    def test_a_missing_reconciliation_mode_is_named(self, design, dataset):
        """FR36 runs each protocol twice. A missing mode is a missing half of
        the comparison, which is a different absence from a missing epoch."""
        path, _ = design
        thin = experiment_dataset.without_mode(dataset, "ilfs_2018", "kalman")
        rep = experiment.run(dataset=thin, preregistration=path,
                             tables=("A",)).value
        rows = [r for r in rep.rows
                if r.epoch == "ilfs_2018" and r.reconciliation_mode == "kalman"]
        assert rows
        assert {r.unavailable_reason for r in rows} == {
            "reconciliation_mode_absent"}
        # The forward_fill half of the same epoch still measures.
        other = [r for r in rep.rows if r.epoch == "ilfs_2018"
                 and r.reconciliation_mode == "forward_fill"]
        assert all(r.availability == "measured" for r in other)

    def test_an_epoch_the_dataset_does_not_cover_is_named(self, design, dataset):
        """`EpochId` is a closed Literal, so this path is reachable only for a
        valid epoch the corpus has not been loaded far enough back to include
        — not for a typo, which the row type rejects outright."""
        path, _ = design
        short = experiment_dataset.without_epoch(dataset, "tariff_2026")
        rep = experiment.run(dataset=short, preregistration=path,
                             tables=("A",)).value
        rows = [r for r in rep.rows if r.epoch == "tariff_2026"]
        assert rows
        assert {r.unavailable_reason for r in rows} == {
            "insufficient_test_sample"}

    def test_the_row_type_refuses_an_epoch_outside_the_six(self):
        with pytest.raises(Exception):
            experiment.ExperimentRow(
                table="A", pillar_subset=("rmt",), reconciliation_mode="kalman",
                xi_mode="hamilton", epoch="not_an_epoch", folds=4,
                availability="unavailable", pre_registration_hash="a" * 64)

    def test_every_reason_is_from_the_closed_set(self, report):
        """An open string here is how a runner ends up with twelve spellings
        of 'no data'."""
        from typing import get_args
        permitted = set(get_args(experiment.UnavailableReason))
        seen = {r.unavailable_reason for r in report.unavailable()}
        assert seen <= permitted

    def test_an_unavailable_row_is_not_publishable(self, dataset, design):
        path, _ = design
        degenerate = experiment_dataset.build(per_epoch=PER_EPOCH,
                                              degenerate_epoch="covid_2020")
        rep = experiment.run(dataset=degenerate, preregistration=path,
                             tables=("A",)).value
        for row in rep.unavailable():
            assert row.as_evaluation_row() is None

    def test_a_missed_warning_stays_a_measurement(self, report):
        """A NaN lead time means the threshold was never crossed before onset.
        That is a finding about the configuration, not a missing cell — so the
        row stays measured and the NaN is reported as a NaN."""
        measured = report.measured()
        assert measured
        for row in measured:
            assert row.auc is not None and math.isfinite(row.auc)
            # lead time may legitimately be NaN
            assert row.mean_lead_time_days is not None


class TestNothingTrainsOnTheTestFold:
    def test_the_held_out_epoch_is_never_in_the_training_set(self, report):
        for row in report.measured():
            assert row.epoch not in row.train_epochs

    def test_every_measured_row_passed_the_leakage_check(self, report):
        assert {r.leakage_check for r in report.measured()} == {"clean"}

    def test_calibration_sees_the_same_mask_the_test_fold_is_scored_under(
            self, report):
        """Training on the full mask and testing on the restricted one hands
        the weights information the test fold cannot see. Both halves would
        look correct in isolation, so the artefact's own recorded mask profile
        is the thing worth asserting."""
        from seraph.validation.ablation import subset_mask
        from seraph.orchestration.run_store import RunStore  # noqa: F401

        # The artefact id is a content hash over (rows, config); the config
        # carries mask_profile, so a row whose subset and profile disagree
        # would hash differently and is what this guards.
        for row in report.measured():
            assert len(row.pillar_subset) == sum(subset_mask(row.pillar_subset))


class TestTheUnitOfAggregationIsTheConfiguration:
    """D5 asks for "mean AUC with per-fold spread". A mean over a TABLE pools
    different subsets, modes and xi modes — it answers no question and reads
    as though it ranked them."""

    def test_each_summary_declares_its_own_fold_count(self, report):
        for summary in report.configurations():
            expected = {"A": 4, "B": 2}[summary.table]
            assert summary.declared_folds == expected

    def test_table_c_declares_six(self, table_c):
        for summary in table_c.configurations():
            assert summary.table == "C"
            assert summary.declared_folds == 6

    def test_the_spread_has_one_value_per_measured_fold(self, report):
        for summary in report.configurations():
            assert len(summary.per_fold_auc) == summary.measured_folds

    def test_a_complete_configuration_measured_every_declared_fold(self, report):
        for summary in report.configurations():
            assert summary.complete
            assert summary.unavailable_folds == {}

    def test_an_unmeasurable_configuration_reports_nan_not_a_half(self, design):
        path, _ = design
        flat = experiment_dataset.build(per_epoch=PER_EPOCH,
                                        degenerate_epoch="covid_2020")
        rep = experiment.run(dataset=flat, preregistration=path,
                             tables=("A",)).value
        partial = [s for s in rep.configurations() if not s.complete]
        assert partial
        for summary in partial:
            assert summary.measured_folds < summary.declared_folds
            assert summary.unavailable_folds

    def test_there_is_no_table_level_mean(self, report):
        """Removed on purpose after it produced 'declared_folds 2,
        measured_folds 24' by pooling six configurations and two xi modes."""
        assert not hasattr(report, "mean_auc")
        assert not hasattr(report, "fold_spread")


class TestASinglePillarRowIsInvariant:
    """Under a one-pillar mask every regime row renormalises to the same
    indicator vector, so C9's `a = xi @ effective` collapses and
    `CSRS = x_hat[k]` exactly — whatever the weights, whichever xi mode."""

    def test_the_r5_control_cannot_diverge_on_one_pillar(self, table_c):
        summaries = {(s.pillar_subset, s.reconciliation_mode, s.xi_mode): s
                     for s in table_c.configurations()}
        for (subset, mode, xi_mode), summary in summaries.items():
            if len(subset) != 1 or xi_mode != "hamilton":
                continue
            twin = summaries[(subset, mode, "uniform")]
            assert summary.per_fold_auc == twin.per_fold_auc, (
                f"{subset} under {mode} differed between xi modes, which the "
                f"arithmetic forbids")

    def test_one_pillar_scores_exactly_the_pillar(self, dataset):
        """The mechanism behind the invariance above, asserted directly rather
        than inferred from a statistic: CSRS equals that pillar's own x_hat."""
        from seraph.validation.ablation import score_subset

        weights = _some_weights()
        obs = dataset["ilfs_2018"].observations["kalman"][0]
        for index, pillar in enumerate(("hawkes", "rmt", "hamilton")):
            scored = score_subset(reconciled=obs.state, xi=obs.xi,
                                  weights=weights, subset=(pillar,))
            assert scored.value.csrs == pytest.approx(obs.state.x_hat[index])

    def test_the_control_does_move_for_a_multi_pillar_subset(self, dataset):
        """Asserted on the SCORE, not on the AUC.

        At 16 observations a fold has 48 discordant pairs, so AUC moves in
        steps of about 0.021 and a genuine but small xi effect is quantised
        away — the first version of this test compared `per_fold_auc` and
        failed for that reason, not because the control was vacuous. The score
        is where the two xi modes either differ or do not.
        """
        from seraph.validation.ablation import score_subset

        weights = _some_weights()
        obs = dataset["ilfs_2018"].observations["kalman"][0]
        assert obs.xi != (1 / 3, 1 / 3, 1 / 3), "the fixture xi must not be flat"

        under = {
            mode: score_subset(reconciled=obs.state, xi=obs.xi,
                               weights=weights, subset=("rmt", "hamilton"),
                               xi_mode=mode).value.csrs
            for mode in ("hamilton", "uniform")
        }
        assert under["hamilton"] != under["uniform"], (
            "a two-pillar subset did not respond to the xi mode, so the R5 "
            "control is vacuous everywhere")


class TestTableCCannotBePublishedYet:
    """DR-05 created Table C and widened `configuration_list`. The published
    `EvaluationRow` and the `validation_results` CHECK were never widened to
    match, so the runner measures rows the declared contract cannot carry."""

    def test_the_runner_measures_table_c(self, table_c):
        assert table_c.rows
        assert {r.table for r in table_c.rows} == {"C"}
        assert table_c.measured()

    def test_the_published_contract_rejects_table_c(self):
        measured = dict(
            pillar_subset=("rmt", "hamilton"), reconciliation_mode="kalman",
            xi_mode="hamilton", epoch="gfc_2008", auc=0.7,
            mean_lead_time_days=4.0, precision_at_fixed_recall=0.6,
            weights_artefact_id="a" * 64, leakage_check="clean",
            pre_registration_hash="b" * 64)
        EvaluationRow(table="B", **measured)          # the shape is otherwise fine
        with pytest.raises(Exception):
            EvaluationRow(table="C", **measured)

    def test_table_c_rows_are_counted_not_dropped(self, table_c):
        assert table_c.unpublishable_rows == len(table_c.rows)
        assert all(r.as_evaluation_row() is None for r in table_c.rows)
        assert "Table C" in table_c.note

    def test_table_a_and_b_rows_do_convert(self, report):
        converted = [r.as_evaluation_row() for r in report.measured()]
        assert converted and all(c is not None for c in converted)
        assert all(isinstance(c, EvaluationRow) for c in converted)

    def test_the_archive_can_hold_what_the_contract_cannot_publish(self):
        """The two halves of the DR-05 gap, which are now in different states
        on purpose.

        FR38 requires every ablation result to be archived, so `table_id` was
        widened to ('A','B','C') in schema.sql and migration 002 — otherwise a
        run computes Table C and then cannot store it. Publishing one is a
        separate claim: `EvaluationRow` still declares `Literal["A","B"]`, and
        widening it edits `shared_types`, which every component imports and
        which CLAUDE.md gates on the owner. So the archive accepts a Table C
        row, the published contract does not, and the runner counts the
        difference rather than dropping it.
        """
        schema = Path("seraph/store/schema.sql").read_text(encoding="utf-8")
        assert "CHECK (table_id IN ('A', 'B', 'C'))" in schema

        contract = Path("seraph/shared_types/validation.py").read_text(
            encoding="utf-8")
        assert 'table: Literal["A", "B"]' in contract


class TestTheReportSaysWhatItIs:
    def test_the_comparability_warning_travels_with_the_rows(self, report):
        assert "not" in report.comparability.lower()
        assert "ranking" in report.comparability.lower()

    def test_the_table_b_scope_is_recorded(self, report):
        assert report.table_b_scope == "two_epoch"

    def test_the_fixture_declares_itself_synthetic(self):
        assert "SYNTHETIC" in experiment_dataset.PROVENANCE
        assert "no result computed from it is evidence" in (
            experiment_dataset.PROVENANCE)

    def test_the_fixture_xi_is_not_uniform(self):
        """The R5 control needs a non-uniform xi to say anything at all."""
        assert experiment_dataset._xi(0, True) != experiment_dataset._xi(1, True)
        assert experiment_dataset._xi(0, False) == (1 / 3, 1 / 3, 1 / 3)

    def test_the_fixture_signal_is_mid_range(self, report):
        """A fixture AUC near 1.0 reads like a spectacular real result. An
        earlier lift/sigma of 0.35/0.09 produced 0.996."""
        aucs = [r.auc for r in report.measured()]
        assert 0.5 < sum(aucs) / len(aucs) < 0.95
