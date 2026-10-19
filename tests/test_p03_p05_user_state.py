# Regression tests — P03, P05 (user-owned state integrity)
"""Portfolio import invariants and scenario revision immutability.

Audit section C, with the counterexamples saved in
`docs/evidence/engineering-audit-2026-10-18/input-portfolio-probes.jsonl`.
Each test here failed before the repair in the same commit.

These are the defects that corrupt a USER's own data rather than the
runtime's, which is why the audit rates them P0 despite sitting outside the
market path: a portfolio whose sector depends on row order, or a scenario
whose approved assumptions no longer exist, cannot be repaired after the fact.
"""
from __future__ import annotations

import math

import pytest

from seraph.decision_support.scenarios import (
    Assumption,
    Baseline,
    ScenarioStore,
)
from seraph.decision_support.workspace import WorkspaceStore, parse_holdings
from seraph.identity import IdentityRegistry


def institutional(tmp_path):
    """A real authenticated principal, built the way the existing suite does:
    organisation, user, membership, grant, session, resolve. There is no
    shortcut constructor, which is the point -- a Principal comes from the
    registry, never from a test literal."""
    registry = IdentityRegistry(tmp_path / "identity.sqlite")
    registry.add_organisation("org_a", "Alpha", "institution")
    user = registry.upsert_user(provider_subject="s1", issuer="https://idp.test")
    registry.add_membership(user.user_id, "org_a")
    registry.grant(user.user_id, "org_a", "institutional", granted_by="admin")
    principal = registry.resolve(registry.open_session(user.user_id).session_id)
    return registry, principal


# ------------------------------------------------------------------- P03


class TestP03NonFiniteNumbersCannotBeStored:
    """`float()` accepts "nan", "inf" and "Infinity" without raising, and a
    NaN quantity then passed the `< 0` check too, because every comparison
    with NaN is False. `value = quantity * price` propagated it into the
    portfolio total, so one malformed cell voided the whole arithmetic."""

    @pytest.mark.parametrize("cell", ["nan", "NaN", "inf", "-inf", "Infinity"])
    def test_a_nonfinite_quantity_is_rejected(self, cell):
        preview = parse_holdings(f"symbol,quantity\nRELIANCE,{cell}\n",
                                 source_name="t.csv")
        assert preview.accepted == []
        assert "finite" in preview.rejected[0].reason

    @pytest.mark.parametrize("cell", ["nan", "inf"])
    def test_a_nonfinite_value_is_rejected(self, cell):
        preview = parse_holdings(f"symbol,value\nRELIANCE,{cell}\n",
                                 source_name="t.csv")
        assert preview.accepted == []

    def test_a_nonfinite_price_is_rejected(self):
        preview = parse_holdings("symbol,quantity,price\nRELIANCE,10,nan\n",
                                 source_name="t.csv")
        assert preview.accepted == []

    def test_the_old_guard_would_have_admitted_nan(self):
        """The precise arithmetic of the defect."""
        assert (float("nan") < 0) is False
        assert math.isnan(float("nan") * 100.0)

    def test_an_overflowing_implied_value_is_rejected(self):
        """Finite inputs, infinite product. The invariant is about what is
        STORED, not about where it came from."""
        preview = parse_holdings(
            "symbol,quantity,price\nRELIANCE,1e308,1e308\n", source_name="t.csv")
        assert preview.accepted == []
        assert "overflow" in preview.rejected[0].reason

    def test_the_total_stays_finite(self):
        preview = parse_holdings(
            "symbol,quantity,price\nRELIANCE,10,100\nTCS,nan,50\n",
            source_name="t.csv")
        assert math.isfinite(preview.total_value)
        assert len(preview.accepted) == 1

    def test_a_valid_row_beside_a_rejected_one_still_lands(self):
        preview = parse_holdings(
            "symbol,quantity,price\nRELIANCE,nan,100\nTCS,5,50\n",
            source_name="t.csv")
        assert [r.symbol for r in preview.accepted] == ["TCS"]
        assert len(preview.rejected) == 1

    def test_a_negative_quantity_is_still_rejected(self):
        preview = parse_holdings("symbol,quantity\nRELIANCE,-5\n",
                                 source_name="t.csv")
        assert preview.accepted == [] and preview.rejected


class TestP03RowOrderIsNotEvidence:
    """`existing.X or accepted.X` resolved a DISAGREEMENT by row order, so
    reordering an uploaded file changed the stored sector -- and the sector
    drives the portfolio overlay."""

    CONFLICT = ("symbol,quantity,sector\n"
                "RELIANCE,10,Energy\n"
                "RELIANCE,5,Telecom\n")
    REVERSED = ("symbol,quantity,sector\n"
                "RELIANCE,5,Telecom\n"
                "RELIANCE,10,Energy\n")

    def test_a_conflicting_sector_is_rejected_not_silently_picked(self):
        preview = parse_holdings(self.CONFLICT, source_name="t.csv")
        assert preview.rejected, "the disagreement was resolved by row order"
        assert "sector" in preview.rejected[0].reason

    def test_the_rejection_names_both_values(self):
        preview = parse_holdings(self.CONFLICT, source_name="t.csv")
        reason = preview.rejected[0].reason
        assert "Energy" in reason and "Telecom" in reason
        assert "Row order is not evidence" in reason

    def test_reordering_the_file_cannot_change_the_outcome(self):
        one = parse_holdings(self.CONFLICT, source_name="t.csv")
        two = parse_holdings(self.REVERSED, source_name="t.csv")
        assert [r.symbol for r in one.accepted] == [r.symbol for r in two.accepted]
        assert len(one.rejected) == len(two.rejected) == 1

    @pytest.mark.parametrize("field,a,b", [
        ("sector", "Energy", "Telecom"),
        ("isin", "INE002A01018", "INE467B01029"),
        ("account", "demat-1", "demat-2"),
    ])
    def test_every_conflicting_metadata_field_is_caught(self, field, a, b):
        body = (f"symbol,quantity,{field}\nRELIANCE,10,{a}\nRELIANCE,5,{b}\n")
        assert parse_holdings(body, source_name="t.csv").rejected

    def test_agreeing_duplicates_still_merge_and_add(self):
        preview = parse_holdings(
            "symbol,quantity,sector\nRELIANCE,10,Energy\nRELIANCE,5,Energy\n",
            source_name="t.csv")
        assert len(preview.accepted) == 1
        assert preview.accepted[0].quantity == 15
        assert preview.duplicates_merged == ["RELIANCE"]

    def test_a_duplicate_with_one_side_absent_still_merges(self):
        """Absence is not disagreement."""
        preview = parse_holdings(
            "symbol,quantity,sector\nRELIANCE,10,Energy\nRELIANCE,5,\n",
            source_name="t.csv")
        assert len(preview.accepted) == 1
        assert preview.accepted[0].sector == "Energy"
        assert preview.accepted[0].quantity == 15


class TestP03AFutureSnapshotIsNotCurrent:
    """`ORDER BY effective_at DESC LIMIT 1` with no upper bound returned a
    2099-effective snapshot as the current holdings. The as-of path beside it
    always had the bound; `current` is the same question with `now` as the
    date, and simply did not ask it."""

    @pytest.fixture
    def store(self, tmp_path):
        registry, principal = institutional(tmp_path)
        workspace = WorkspaceStore(tmp_path / "workspace.sqlite", registry)
        portfolio = workspace.create_portfolio(principal, name="P")
        return workspace, principal, portfolio["portfolio_id"]

    def _snapshot(self, workspace, principal, portfolio_id, *, effective_at,
                  quantity):
        raw = f"symbol,quantity,price\nRELIANCE,{quantity},100\n"
        preview = workspace.preview_import(principal, portfolio_id, raw,
                                           source_name="t.csv")
        return workspace.commit_import(principal, portfolio_id, preview, raw,
                                       effective_at=effective_at)

    def test_a_2099_snapshot_is_not_the_current_holdings(self, store):
        workspace, principal, portfolio_id = store
        self._snapshot(workspace, principal, portfolio_id,
                       effective_at="2024-01-02T09:15:00+05:30", quantity=10)
        self._snapshot(workspace, principal, portfolio_id,
                       effective_at="2099-01-01T09:15:00+05:30", quantity=999)
        current = workspace.current_holdings(principal, portfolio_id)
        assert current["effective_at"] == "2024-01-02T09:15:00+05:30"
        assert current["holdings"][0]["quantity"] == 10, \
            "a future snapshot was served as current (P03)"

    def test_the_future_snapshot_is_reported_as_scheduled_not_hidden(self, store):
        workspace, principal, portfolio_id = store
        self._snapshot(workspace, principal, portfolio_id,
                       effective_at="2024-01-02T09:15:00+05:30", quantity=10)
        self._snapshot(workspace, principal, portfolio_id,
                       effective_at="2099-01-01T09:15:00+05:30", quantity=999)
        current = workspace.current_holdings(principal, portfolio_id)
        assert current["scheduled"]["effective_at"] == "2099-01-01T09:15:00+05:30"

    def test_only_a_future_snapshot_means_nothing_is_in_force(self, store):
        workspace, principal, portfolio_id = store
        self._snapshot(workspace, principal, portfolio_id,
                       effective_at="2099-01-01T09:15:00+05:30", quantity=999)
        current = workspace.current_holdings(principal, portfolio_id)
        assert current["basis"] == "unavailable"
        assert current["holdings"] == []
        assert "future" in current["note"]

    def test_an_injectable_clock_makes_this_testable(self, store):
        workspace, principal, portfolio_id = store
        self._snapshot(workspace, principal, portfolio_id,
                       effective_at="2030-01-01T09:15:00+05:30", quantity=42)
        assert workspace.current_holdings(
            principal, portfolio_id,
            now="2024-01-01T00:00:00+05:30")["basis"] == "unavailable"
        assert workspace.current_holdings(
            principal, portfolio_id,
            now="2031-01-01T00:00:00+05:30")["holdings"][0]["quantity"] == 42


# ------------------------------------------------------------------- P05


class TestP05AssumptionRevisionsAreImmutable:
    """`revise_assumptions` ran `UPDATE scenarios SET assumptions=?`, which
    DESTROYED the previous text while incrementing a counter. Its docstring
    claimed the old runs kept pointing at the old set; they pointed at a
    version NUMBER whose content no longer existed."""

    @pytest.fixture
    def scenario(self, tmp_path):
        registry, principal = institutional(tmp_path)
        store = ScenarioStore(tmp_path / "scenarios.sqlite", registry)
        baseline = Baseline(run_id="run-1", date="2024-01-02",
                            weights_artefact_id="fw:1",
                            reconciled_hash="a" * 64)
        saved = store.save(
            principal, name="S", kind="rank_shock", baseline=baseline,
            steps=[dict(pillar="rmt", delta=0.1)],
            assumptions=[Assumption(key="shock", value="0.1", unit="rank",
                                    justification="hypothetical")])
        return store, principal, saved["scenario_id"]

    def test_version_one_is_recorded_as_a_revision(self, scenario):
        store, principal, scenario_id = scenario
        assert store.assumptions_at(principal, scenario_id, 1)["assumptions"]

    def test_an_old_revision_survives_a_later_one(self, scenario):
        store, principal, scenario_id = scenario
        store.revise_assumptions(principal, scenario_id, [
            Assumption(key="shock", value="0.9", unit="rank",
            justification="hypothetical")])
        first = store.assumptions_at(principal, scenario_id, 1)
        assert first["assumptions"][0]["value"] == "0.1", \
            "the earlier assumption text was overwritten (P05)"

    def test_the_new_revision_is_the_current_one(self, scenario):
        store, principal, scenario_id = scenario
        store.revise_assumptions(principal, scenario_id, [
            Assumption(key="shock", value="0.9", unit="rank",
            justification="hypothetical")])
        current = store.scenario(principal, scenario_id)
        assert current["assumption_version"] == 2
        assert current["assumptions"][0]["value"] == "0.9"

    def test_the_history_reads_oldest_first(self, scenario):
        store, principal, scenario_id = scenario
        for value in ("0.2", "0.3"):
            store.revise_assumptions(principal, scenario_id, [
                Assumption(key="shock", value=value, unit="rank",
                justification="hypothetical")])
        history = store.assumption_history(principal, scenario_id)
        assert [h["version"] for h in history] == [1, 2, 3]
        assert [h["assumptions"][0]["value"] for h in history] == \
            ["0.1", "0.2", "0.3"]

    def test_a_revision_cannot_be_updated(self, scenario):
        import sqlite3
        store, _, scenario_id = scenario
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with store.connect() as db:
                db.execute('UPDATE scenario_assumptions SET assumptions=? '
                           'WHERE scenario_id=?', ('[]', scenario_id))

    def test_a_revision_cannot_be_deleted(self, scenario):
        import sqlite3
        store, _, scenario_id = scenario
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            with store.connect() as db:
                db.execute('DELETE FROM scenario_assumptions WHERE scenario_id=?',
                           (scenario_id,))

    def test_an_unknown_version_is_refused_and_explains_why(self, scenario):
        store, principal, scenario_id = scenario
        with pytest.raises(ValueError, match="no assumption version"):
            store.assumptions_at(principal, scenario_id, 7)


class TestP05ARunCanBeReconstructed:
    """The row stored `inputs_hash` and not the inputs, so a run could be
    CHECKED for sameness and never reconstructed."""

    @pytest.fixture
    def scenario(self, tmp_path):
        registry, principal = institutional(tmp_path)
        store = ScenarioStore(tmp_path / "scenarios.sqlite", registry)
        baseline = Baseline(run_id="run-1", date="2024-01-02",
                            weights_artefact_id="fw:1",
                            reconciled_hash="a" * 64)
        saved = store.save(
            principal, name="S", kind="rank_shock", baseline=baseline,
            steps=[dict(pillar="rmt", delta=0.1)],
            assumptions=[Assumption(key="shock", value="0.1", unit="rank",
                                    justification="hypothetical")])
        return store, principal, saved["scenario_id"]

    def test_the_inputs_are_stored_not_only_hashed(self, scenario):
        store, principal, scenario_id = scenario
        run = store.record_run(principal, scenario_id, results=[1, 2],
                               inputs=dict(delta=0.1))
        assert run["inputs"]["inputs"] == dict(delta=0.1)

    def test_the_run_records_the_assumption_version_in_force(self, scenario):
        store, principal, scenario_id = scenario
        run = store.record_run(principal, scenario_id, results=[1],
                               inputs=dict(delta=0.1))
        assert run["assumption_version"] == 1

    def test_identical_inputs_reuse_the_record(self, scenario):
        store, principal, scenario_id = scenario
        first = store.record_run(principal, scenario_id, results=[1],
                                 inputs=dict(delta=0.1))
        again = store.record_run(principal, scenario_id, results=[9],
                                 inputs=dict(delta=0.1))
        assert again["reused"] is True
        assert again["results"] == first["results"]

    def test_a_revision_makes_the_same_inputs_a_different_run(self, scenario):
        store, principal, scenario_id = scenario
        first = store.record_run(principal, scenario_id, results=[1],
                                 inputs=dict(delta=0.1))
        store.revise_assumptions(principal, scenario_id, [
            Assumption(key="shock", value="0.9", unit="rank",
            justification="hypothetical")])
        second = store.record_run(principal, scenario_id, results=[2],
                                  inputs=dict(delta=0.1))
        assert second["run_key"] != first["run_key"]
        assert second["assumption_version"] == 2


class TestP05AReviewIsBoundToWhatWasReviewed:
    """A verdict was bound to the scenario id and a sequence number only, so
    approving revision 1 silently became approval of revision 2."""

    @pytest.fixture
    def scenario(self, tmp_path):
        registry, principal = institutional(tmp_path)
        store = ScenarioStore(tmp_path / "scenarios.sqlite", registry)
        baseline = Baseline(run_id="run-1", date="2024-01-02",
                            weights_artefact_id="fw:1",
                            reconciled_hash="a" * 64)
        saved = store.save(
            principal, name="S", kind="rank_shock", baseline=baseline,
            steps=[dict(pillar="rmt", delta=0.1)],
            assumptions=[Assumption(key="shock", value="0.1", unit="rank",
                                    justification="hypothetical")])
        return store, principal, saved["scenario_id"]

    def test_a_verdict_records_the_revision_it_was_given_on(self, scenario):
        store, principal, scenario_id = scenario
        verdict = store.review(principal, scenario_id, verdict="approved")
        assert verdict["assumption_version"] == 1

    def test_approving_revision_one_does_not_approve_revision_two(self, scenario):
        store, principal, scenario_id = scenario
        store.review(principal, scenario_id, verdict="approved")
        store.revise_assumptions(principal, scenario_id, [
            Assumption(key="shock", value="0.9", unit="rank",
            justification="hypothetical")])
        current = store.scenario(principal, scenario_id)
        assert current["assumption_version"] == 2
        approvals = [r for r in current["reviews"] if r["verdict"] == "approved"]
        assert approvals and all(r["assumption_version"] == 1 for r in approvals), \
            "an approval of revision 1 now stands against revision 2 (P05)"

    def test_a_verdict_on_a_nonexistent_revision_is_refused(self, scenario):
        store, principal, scenario_id = scenario
        with pytest.raises(ValueError, match="no assumption version"):
            store.review(principal, scenario_id, verdict="approved",
                         assumption_version=9)

    def test_a_review_can_cite_the_exact_run_it_examined(self, scenario):
        store, principal, scenario_id = scenario
        run = store.record_run(principal, scenario_id, results=[1],
                               inputs=dict(delta=0.1))
        verdict = store.review(principal, scenario_id, verdict="approved",
                               run_key=run["run_key"])
        assert verdict["run_key"] == run["run_key"]

    def test_a_review_cannot_cite_a_run_from_another_scenario(self, scenario):
        store, principal, scenario_id = scenario
        with pytest.raises(ValueError, match="does not belong"):
            store.review(principal, scenario_id, verdict="approved",
                         run_key="sc_other:deadbeef")
