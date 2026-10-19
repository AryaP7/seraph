# T10 — FR37 transfer, FR34 sensitivity, FR38 archival
"""The three deliverables T10 names beside the tables.

> "Connect the existing metric/calibration/subset/configuration primitives
> into a bounded original-design experiment runner and report loader for
> Tables A/B, sensitivity and fixed-weight cross-market transfer. Preserve
> explicit unavailable rows and original designs."

Each has a way of going quietly wrong, and that is what these cover:

* **Transfer** can refit. O9's acceptance is "weight vectors bit-identical
  between NSE and second-market runs" and "execution log contains no refit
  step", so the absence of a refit has to be a property of the code rather
  than a claim in a report.
* **Sensitivity** can present one axis of four as the whole of FR34, or sweep
  designs that do not actually differ and report the resulting zero spread as
  stability.
* **Archival** can drop the unavailable rows, which would make a later reader
  conclude the run was smaller than it was.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fixtures import experiment_dataset
from seraph.shared_types import (
    CalibrationConfig,
    FusionWeights,
    fusion_weights_artefact_id,
)
from seraph.validation import experiment, experiment_store, sensitivity, transfer
from seraph.validation.preregistration import build, commit

BUDGET = 40
PER_EPOCH = 16
MIGRATION = Path("seraph/store/migrations/002_experiment_rows.sql")


def weights(epochs=("ilfs_2018",), rows=((0.6, 0.3, 0.1), (0.2, 0.6, 0.2),
                                         (0.1, 0.2, 0.7))):
    cfg = CalibrationConfig(epochs=tuple(epochs), fold_held_out=None,
                            kappa_miss=10.0, kappa_fa=1.0,
                            mask_profile=(True, True, True))
    return FusionWeights(artefact_id=fusion_weights_artefact_id(rows, cfg),
                         calibrated_on=cfg, w=rows)


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dataset():
    return experiment_dataset.build(per_epoch=PER_EPOCH)


@pytest.fixture(scope="module")
def observations(dataset):
    return dataset["taper_2013"].observations["kalman"]


@pytest.fixture(scope="module")
def report(tmp_path_factory, dataset):
    path = tmp_path_factory.mktemp("d") / "preregistration.json"
    commit(build(calibration_max_iter=BUDGET), path)
    result = experiment.run(dataset=dataset, preregistration=path,
                            tables=("B",))
    assert result.status == "ok"
    return result.value


# --- FR37 ----------------------------------------------------------------

class TestTheTransferCannotRefit:
    def test_the_module_does_not_import_a_calibrator(self):
        """"Without retraining" as a property of the dependency graph.

        Asserted on the parsed imports, not on the text: the first version of
        this test matched the substring "calibrate" inside the field name
        `calibrated_on_epochs` and failed on a module that imports no
        calibrator at all.
        """
        import ast

        tree = ast.parse(Path("seraph/validation/transfer.py").read_text(
            encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(a.name for a in node.names)
        assert "calibrate" not in imported
        assert "minimize" not in imported
        assert not any(name.endswith("harness.calibrate")
                       for name in imported)
        # The metrics ARE imported; only the fitter must not be.
        assert "auc" in imported

    def test_refit_cannot_be_set_true(self, observations):
        result = transfer.transfer(weights=weights(), target_market="JSE",
                                   observations=observations,
                                   amber_threshold=0.5)
        assert result.status == "ok"
        assert result.value.refit is False
        with pytest.raises(Exception):
            result.value.model_copy(update={"refit": True}).model_dump_json()
            transfer.TransferResult(**{
                **result.value.model_dump(), "refit": True})

    def test_the_artefact_travels_onto_the_result(self, observations):
        artefact = weights()
        value = transfer.transfer(weights=artefact, target_market="IDX",
                                  observations=observations,
                                  amber_threshold=0.5).value
        assert value.weights_artefact_id == artefact.artefact_id
        assert value.calibrated_on_epochs == artefact.calibrated_on.epochs

    def test_bit_identity_checks_the_rows_and_the_hash(self):
        """The hash alone would test the hash function; the rows alone would
        miss a differing calibration config the hash is supposed to cover."""
        a = weights()
        assert transfer.weights_are_bit_identical(a, weights())
        other = weights(rows=((0.5, 0.4, 0.1), (0.2, 0.6, 0.2),
                              (0.1, 0.2, 0.7)))
        assert not transfer.weights_are_bit_identical(a, other)
        relabelled = weights(epochs=("covid_2020",))
        assert not transfer.weights_are_bit_identical(a, relabelled)


class TestThePackageInterfaceDoesNotShadowItsModules:
    """A re-export must not share a name with its own module.

    `seraph/validation/__init__.py` briefly re-exported the `transfer`
    FUNCTION under the bare name `transfer`, which shadowed the `transfer`
    MODULE: `from seraph.validation import transfer` returned a function while
    `import seraph.validation.transfer` returned the module. Fourteen tests
    failed on `'function' object has no attribute 'transfer'`. It is exported
    as `run_transfer` now, matching `run_experiment`.
    """

    def test_the_submodules_are_reachable_by_their_own_names(self):
        import seraph.validation as package

        for name in ("experiment", "experiment_store", "sensitivity",
                     "transfer", "ablation", "harness", "preregistration"):
            attribute = getattr(package, name)
            assert hasattr(attribute, "__file__"), (
                f"seraph.validation.{name} resolves to {attribute!r}, not the "
                f"module -- a re-export is shadowing it")

    def test_no_export_collides_with_a_submodule_name(self):
        import pkgutil

        import seraph.validation as package

        submodules = {m.name for m in pkgutil.iter_modules(package.__path__)}
        collisions = sorted(submodules & set(package.__all__))
        assert collisions == [], (
            f"{collisions} are exported under the same name as a submodule")

    def test_the_exports_all_resolve(self):
        import seraph.validation as package

        assert [n for n in package.__all__ if not hasattr(package, n)] == []


class TestTheTransferScopeIsReportedNotOmitted:
    def test_a_market_outside_the_spec_set_is_refused(self, observations):
        result = transfer.transfer(weights=weights(), target_market="FTSE",
                                   observations=observations,
                                   amber_threshold=0.5)
        assert result.status == "error"
        assert "IDX" in result.error.detail

    def test_it_can_be_widened_deliberately(self, observations):
        result = transfer.transfer(weights=weights(), target_market="FTSE",
                                   observations=observations,
                                   amber_threshold=0.5,
                                   allow_market_outside_spec=True)
        assert result.status == "ok"

    def test_three_pillars_without_declared_intraday_is_refused(self,
                                                                observations):
        """FR37 scopes to RMT+Hamilton unless the target's intraday data is
        free and available. A Hawkes coordinate no data supports is the thing
        being prevented."""
        result = transfer.transfer(
            weights=weights(), target_market="JSE", observations=observations,
            subset=("hawkes", "rmt", "hamilton"), amber_threshold=0.5)
        assert result.status == "error"
        assert result.error.field == "pillar_subset"

    def test_the_default_scope_says_why_it_is_the_default(self, observations):
        value = transfer.transfer(weights=weights(), target_market="JSE",
                                  observations=observations,
                                  amber_threshold=0.5).value
        assert value.pillar_subset == ("rmt", "hamilton")
        assert "RMT+Hamilton" in value.scope_reason
        assert "5-minute bars" in value.scope_reason

    def test_a_single_class_sample_is_refused_not_scored_at_a_half(self):
        flat = experiment_dataset.build(per_epoch=PER_EPOCH,
                                        degenerate_epoch="taper_2013")
        result = transfer.transfer(
            weights=weights(), target_market="JSE",
            observations=flat["taper_2013"].observations["kalman"],
            amber_threshold=0.5)
        assert result.status == "error"
        assert "0.5 would not be one" in result.error.detail


class TestTheTransferIsActuallyOutOfSample:
    """"Out-of-sample" is the whole claim of FR37, and a different market name
    does not by itself make a sample new. Found in the CLI's own stand-in
    path: the donor artefact had been fitted on the epoch being scored, and
    the reported out-of-sample AUC was in-sample."""

    def test_an_overlapping_target_is_refused(self, observations):
        result = transfer.transfer(
            weights=weights(epochs=("taper_2013",)), target_market="JSE",
            observations=observations, target_epochs=("taper_2013",),
            amber_threshold=0.5)
        assert result.status == "error"
        assert result.error.field == "target_epochs"
        assert "in-sample" in result.error.detail

    def test_a_disjoint_target_is_accepted(self, observations):
        result = transfer.transfer(
            weights=weights(epochs=("gfc_2008",)), target_market="JSE",
            observations=observations, target_epochs=("taper_2013",),
            amber_threshold=0.5)
        assert result.status == "ok"

    def test_the_check_is_skipped_when_the_caller_cannot_say(self,
                                                             observations):
        """A real second market has its own epochs and no overlap to compute.
        The guard applies when the caller names the target's epochs; it does
        not invent them."""
        result = transfer.transfer(
            weights=weights(epochs=("taper_2013",)), target_market="JSE",
            observations=observations, amber_threshold=0.5)
        assert result.status == "ok"

    def test_the_cli_donor_is_held_out_at_the_stand_in(self):
        """The CLI uses a fixture epoch as the stand-in market, so it must
        pick the row that was held out there -- under leave-one-epoch-out that
        is exactly the artefact fitted without it."""
        source = Path("scripts/run_experiment.py").read_text(encoding="utf-8")
        assert "r.epoch == stand_in" in source
        assert "stand_in not in r.train_epochs" in source

    def test_the_cli_claims_no_degradation_without_a_reference(self):
        """Passing the donor's own AUC produced +0.0000, which reads as
        perfect transfer and is the same number twice."""
        source = Path("scripts/run_experiment.py").read_text(encoding="utf-8")
        assert "nse_reference_auc=donor.auc" not in source
        assert "no degradation is reported" in source


class TestNfr20IsAnAcknowledgedGap:
    def test_no_bound_and_no_verdict(self, observations):
        value = transfer.transfer(weights=weights(), target_market="JSE",
                                  observations=observations,
                                  amber_threshold=0.5,
                                  nse_reference_auc=0.80).value
        assert value.degradation_bound is None
        assert "[GAP]" in value.bound_note
        assert "neither a pass nor a failure" in value.bound_note

    def test_degradation_is_absent_without_a_reference(self, observations):
        value = transfer.transfer(weights=weights(), target_market="JSE",
                                  observations=observations,
                                  amber_threshold=0.5).value
        assert value.degradation is None

    def test_degradation_is_the_signed_difference(self, observations):
        value = transfer.transfer(weights=weights(), target_market="JSE",
                                  observations=observations,
                                  amber_threshold=0.5,
                                  nse_reference_auc=0.80).value
        assert value.degradation == pytest.approx(
            0.80 - value.out_of_sample_auc)


# --- FR34 ----------------------------------------------------------------

class TestTheSweepSaysWhatItDoesNotCover:
    def test_the_three_pillar_axes_are_named_with_their_owners(self):
        axes = {a.axis: a for a in sensitivity.PILLAR_AXES}
        assert set(axes) == {"rolling-window length", "Hawkes kernel order K",
                             "Absorption-Ratio component count"}
        for axis in axes.values():
            assert axis.owner and axis.constant and axis.why

    def test_the_note_states_one_axis_of_four(self, dataset, tmp_path):
        designs = _two_designs(tmp_path)
        rep = sensitivity.sweep(dataset=dataset, designs=designs,
                                tables=("B",)).value
        assert "four axes" in rep.note
        assert len(rep.unavailable_axes) == 3

    def test_one_design_is_a_run_not_a_sweep(self, dataset, tmp_path):
        path = tmp_path / "one.json"
        commit(build(calibration_max_iter=BUDGET), path)
        result = sensitivity.sweep(dataset=dataset, designs=[("only", path)])
        assert result.status == "error"
        assert "not a sweep" in result.error.detail

    def test_two_identical_designs_are_refused(self, dataset, tmp_path):
        """A sweep over designs that do not differ reports a spread of zero,
        which reads as stability."""
        path = tmp_path / "same.json"
        commit(build(calibration_max_iter=BUDGET), path)
        result = sensitivity.sweep(dataset=dataset,
                                   designs=[("a", path), ("b", path)],
                                   tables=("B",))
        assert result.status == "error"
        assert "looks like stability" in result.error.detail

    def test_each_point_is_its_own_hashed_design(self, dataset, tmp_path):
        rep = sensitivity.sweep(dataset=dataset,
                                designs=_two_designs(tmp_path),
                                tables=("B",)).value
        hashes = {p.pre_registration_hash for p in rep.points}
        assert len(hashes) == len(rep.points)

    def test_every_point_is_marked_sensitivity(self, dataset, tmp_path):
        rep = sensitivity.sweep(dataset=dataset,
                                designs=_two_designs(tmp_path),
                                tables=("B",)).value
        assert all(p.is_sensitivity for p in rep.points)

    def test_the_swept_axis_actually_varied(self, dataset, tmp_path):
        rep = sensitivity.sweep(dataset=dataset,
                                designs=_two_designs(tmp_path),
                                tables=("B",)).value
        assert len(rep.swept_axes()["kappa_ratio"]) == 2

    def test_the_spread_is_the_answer_not_a_best_point(self, dataset, tmp_path):
        rep = sensitivity.sweep(dataset=dataset,
                                designs=_two_designs(tmp_path),
                                tables=("B",)).value
        key = next(iter(rep.points[0].mean_auc_by_configuration))
        spread = rep.spread(key)
        assert spread["points"] == 2
        assert spread["range"] is not None and spread["range"] >= 0
        ordered = rep.most_sensitive()
        assert set(ordered) <= set(rep.points[0].mean_auc_by_configuration)

    def test_an_unknown_configuration_has_an_empty_spread(self, dataset,
                                                          tmp_path):
        rep = sensitivity.sweep(dataset=dataset,
                                designs=_two_designs(tmp_path),
                                tables=("B",)).value
        assert rep.spread("Z:nothing:kalman:hamilton")["measured"] == 0


def _two_designs(tmp_path) -> list[tuple[str, Path]]:
    """Two designs differing only in the loss ratio FR34 names."""
    out = []
    for label, kappa in (("kappa10", 10.0), ("kappa3", 3.0)):
        path = tmp_path / f"{label}.json"
        commit(build(calibration_max_iter=BUDGET, kappa_miss=kappa), path)
        out.append((label, path))
    return out


# --- FR38 ----------------------------------------------------------------

class TestTheArtefactIsEvidence:
    def test_the_id_covers_the_design_not_only_the_rows(self, report):
        """Two runs of the same rows under different designs are different
        results; an id that ignored the design would call them the same."""
        first = experiment_store.artefact_id(report)
        other = report.model_copy(update={"pre_registration_hash": "f" * 64})
        assert experiment_store.artefact_id(other) != first

    def test_the_id_covers_the_budget(self, report):
        other = report.model_copy(update={"calibration_max_iter": 9999})
        assert (experiment_store.artefact_id(other)
                != experiment_store.artefact_id(report))

    def test_it_round_trips(self, report, tmp_path):
        path, digest = experiment_store.save(report, tmp_path / "r.json")
        loaded, stored, intact = experiment_store.load(path)
        assert intact and stored == digest
        assert len(loaded.rows) == len(report.rows)
        assert loaded.pre_registration_hash == report.pre_registration_hash

    def test_saving_refuses_to_overwrite(self, report, tmp_path):
        """Replacing a report in place is how the earlier run's numbers
        disappear -- the defect migration 001 fixed in the database."""
        path = tmp_path / "once.json"
        experiment_store.save(report, path)
        with pytest.raises(FileExistsError):
            experiment_store.save(report, path)

    def test_an_edited_report_does_not_verify(self, report, tmp_path):
        path = tmp_path / "edited.json"
        experiment_store.save(report, path)
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["report"]["rows"][0]["auc"] = 0.99
        path.write_text(json.dumps(blob), encoding="utf-8")
        _, _, intact = experiment_store.load(path)
        assert not intact


class TestArchivalKeepsTheAbsences:
    def test_unavailable_rows_are_archived_too(self, dataset, tmp_path):
        path = tmp_path / "preregistration.json"
        commit(build(calibration_max_iter=BUDGET), path)
        flat = experiment_dataset.build(per_epoch=PER_EPOCH,
                                        degenerate_epoch="covid_2020")
        rep = experiment.run(dataset=flat, preregistration=path,
                             tables=("A",)).value
        rows = experiment_store.archive_rows(rep, "run-1")
        assert len(rows) == len(rep.rows)
        assert any(r[6] == "unavailable" for r in rows)

    def test_the_column_order_matches_the_tuples(self, report):
        rows = experiment_store.archive_rows(report, "run-1")
        assert all(len(r) == len(experiment_store.ARCHIVE_COLUMNS)
                   for r in rows)

    def test_an_unavailable_row_carries_no_metric_and_a_reason(self, dataset,
                                                               tmp_path):
        """The shape migration 002's CHECK enforces, asserted on the tuples
        the writer actually sends."""
        path = tmp_path / "preregistration.json"
        commit(build(calibration_max_iter=BUDGET), path)
        flat = experiment_dataset.build(per_epoch=PER_EPOCH,
                                        degenerate_epoch="covid_2020")
        rep = experiment.run(dataset=flat, preregistration=path,
                             tables=("A",)).value
        columns = experiment_store.ARCHIVE_COLUMNS
        auc_at = columns.index("auc")
        reason_at = columns.index("unavailable_reason")
        state_at = columns.index("availability")
        for row in experiment_store.archive_rows(rep, "run-1"):
            if row[state_at] == "unavailable":
                assert row[auc_at] is None and row[reason_at] is not None
            else:
                assert row[auc_at] is not None and row[reason_at] is None


class TestMigration002:
    """Static assertions run everywhere; applying it needs a real Postgres
    and is gated like FIX06's, so the SQL is checked and its application is
    not claimed."""

    def test_it_widens_table_id_to_include_c(self, sql):
        assert "CHECK (table_id IN ('A', 'B', 'C'))" in sql

    def test_it_drops_not_null_from_every_metric(self, sql):
        for column in ("auc", "mean_lead_time_days", "precision_at_recall"):
            assert f"ALTER COLUMN {column} DROP NOT NULL" in sql

    def test_it_keeps_each_availability_state_whole(self, sql):
        assert "validation_results_availability_is_whole" in sql
        assert "unavailable_reason IS NOT NULL" in sql

    def test_it_finds_the_generated_constraint_name(self, sql):
        """The CHECK name is generated, so dropping it by a guessed name
        would fail on a database that was created by schema.sql."""
        assert "pg_get_constraintdef" in sql
        assert "DROP CONSTRAINT %I" in sql

    def test_every_addition_is_idempotent(self, sql):
        adds = [line for line in sql.splitlines()
                if "ADD COLUMN" in line]
        assert adds
        assert all("IF NOT EXISTS" in line for line in adds)

    def test_it_says_what_it_does_not_widen(self, sql):
        """Archiving a Table C row and publishing one are different claims."""
        assert "EvaluationRow" in sql
        assert "ask-before-edit" in sql

    def test_schema_and_migration_agree_on_the_domain(self, sql):
        schema = Path("seraph/store/schema.sql").read_text(encoding="utf-8")
        assert "CHECK (table_id IN ('A', 'B', 'C'))" in schema
        assert "validation_results_availability_is_whole" in schema

    def test_the_migration_runner_discovers_it_in_order(self):
        from seraph.store.migrations import discover

        names = [name for name, _, _ in discover()]
        assert names == sorted(names)
        assert "002_experiment_rows.sql" in names

    def test_the_published_contract_is_still_narrow(self):
        """The remaining gap, pinned so it cannot be forgotten: the archive
        can hold Table C and the published row type cannot. Widening
        `EvaluationRow` is gated on the owner."""
        source = Path("seraph/shared_types/validation.py").read_text(
            encoding="utf-8")
        assert 'table: Literal["A", "B"]' in source


class TestTheRendererDoesNotInviteARanking:
    def test_the_comparability_warning_comes_first(self, report):
        text = experiment_store.render(report)
        assert text.index("COMPARABILITY") < text.index("TABLE B")

    def test_every_line_carries_its_fold_count(self, report):
        text = experiment_store.render(report)
        assert "folds declared" in text
        assert "2/2" in text

    def test_the_absence_census_is_always_printed(self, report):
        text = experiment_store.render(report)
        assert "UNAVAILABLE CELLS" in text

    def test_it_reports_what_cannot_be_published(self, report):
        text = experiment_store.render(report)
        assert "cannot carry" in text
