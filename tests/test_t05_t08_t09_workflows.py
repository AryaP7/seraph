# T05, T08, T09 — the durable role workflows, through the real dispatcher
"""Portfolios, scenarios and regulator cases, end to end.

What these close is not a bug in `WorkspaceStore`, `ScenarioStore` or
`CaseStore`. All three were already implemented and tested. The defect was
that **nothing in the dashboard called them**: `grep -c` for all three store
names across `prototype_app.py` and `console_backend.py` returned 0, so
portfolios lived in `st.session_state`, scenarios were transient, and the
regulator case lifecycle had no user at all.

Every test here drives the real `dispatch()` entry point with the same
`(run_id, date, op, id)` event shape the browser sends, so a passing test
means a reachable route and not just a callable function. Persistence is
checked by constructing a SECOND set of stores over the same directory,
which is what "survives a restart" means.
"""
from __future__ import annotations

import json

import pytest

from seraph.dashboard.console_backend import dispatch
from seraph.orchestration.prototype import InferenceSession
from seraph.orchestration.run_store import RunStore


@pytest.fixture(autouse=True)
def workspace_dir(tmp_path, monkeypatch):
    """Point the durable stores at a scratch directory, per test."""
    monkeypatch.setenv("SERAPH_WORKSPACE_DIR", str(tmp_path / "runs"))
    return tmp_path / "runs"


def saved(tmp_path, *, eligible: bool = False):
    """One sealed run. `eligible=True` gives a scored point, which the
    scenario simulators need for a baseline."""
    store = RunStore(tmp_path / "ui.sqlite")
    manifest = dict(mode="synthetic test fixture",
                    data_available_through="2020-01-01")
    run = store.begin(manifest)
    if eligible:
        inputs = {p: dict(score_eligible=True, value=v, variance=0.01,
                          information_timestamp="2020-01-01T15:30:00+05:30")
                  for p, v in (("hawkes", 0.4), ("rmt", 0.5), ("hamilton", 0.6))}
    else:
        inputs = {p: dict(score_eligible=False, reason="test missing",
                          absence="structural", absence_reason="no_data_coverage")
                  for p in ("hawkes", "rmt", "hamilton")}
    point = InferenceSession(["2020-01-01"]).step("2020-01-01", inputs, [],
                                                  run_id=run)
    store.put(run, point)
    store.finish(run, 1)
    return store, manifest, point


def event(point, op, **args):
    return dict(id=f"req-{op}", run_id=point["run_id"], date=point["date"],
                op=op, **args)


HOLDINGS_CSV = ("symbol,quantity,price,sector\n"
                "RELIANCE,10,1300,Energy\n"
                "TCS,5,3500,IT\n")


# ------------------------------------------------------------------- T05


class TestT05PortfoliosArePersistent:
    def test_a_portfolio_can_be_created_and_listed(self, tmp_path):
        store, _, point = saved(tmp_path)
        made = dispatch(store, point, "retail",
                        event(point, "ws_create", name="My holdings"))
        assert made["kind"] == "ws_create"
        listed = dispatch(store, point, "retail", event(point, "ws_portfolios"))
        assert [p["name"] for p in listed["value"]] == ["My holdings"]

    def test_every_workflow_result_names_the_demo_identity(self, tmp_path):
        store, _, point = saved(tmp_path)
        made = dispatch(store, point, "retail",
                        event(point, "ws_create", name="P"))
        assert made["identity"]["authenticated"] is False
        assert "not authenticated" in made["identity"]["note"]

    def test_an_upload_previews_its_errors_before_saving(self, tmp_path):
        store, _, point = saved(tmp_path)
        pid = dispatch(store, point, "retail",
                       event(point, "ws_create", name="P"))["value"]["portfolio_id"]
        preview = dispatch(store, point, "retail", event(
            point, "ws_preview", portfolio_id=pid,
            body=HOLDINGS_CSV + "BADROW,nan,100,IT\n"))
        # `describe()` reports `accepted`/`rejected` as COUNTS and carries the
        # actionable detail in `rejected_rows`.
        assert preview["value"]["accepted"] == 2
        assert preview["value"]["rejected"] == 1
        assert preview["value"]["rejected_rows"], "the NaN row was not rejected"
        assert "finite" in preview["value"]["rejected_rows"][0]["reason"]

    def test_holdings_survive_a_restart(self, tmp_path):
        store, _, point = saved(tmp_path)
        pid = dispatch(store, point, "retail",
                       event(point, "ws_create", name="P"))["value"]["portfolio_id"]
        dispatch(store, point, "retail", event(
            point, "ws_commit", portfolio_id=pid, body=HOLDINGS_CSV,
            effective_at="2026-01-02T09:15:00+05:30"))
        # A second dispatch builds brand-new store objects over the same
        # directory: this is what "after a restart" means here.
        held = dispatch(store, point, "retail",
                        event(point, "ws_holdings", portfolio_id=pid))
        symbols = [h["symbol"] for h in held["value"]["holdings"]]
        assert symbols == ["RELIANCE", "TCS"]
        assert held["value"]["basis"] == "current"

    def test_the_commit_reparses_the_original_bytes(self, tmp_path):
        """P03: a mutated preview must not be able to change what is stored,
        so the server re-parses the upload rather than trusting the echo."""
        store, _, point = saved(tmp_path)
        pid = dispatch(store, point, "retail",
                       event(point, "ws_create", name="P"))["value"]["portfolio_id"]
        saved_rows = dispatch(store, point, "retail", event(
            point, "ws_commit", portfolio_id=pid, body=HOLDINGS_CSV,
            effective_at="2026-01-02T09:15:00+05:30",
            accepted=[dict(symbol="RELIANCE", quantity=999)]))
        held = dispatch(store, point, "retail",
                        event(point, "ws_holdings", portfolio_id=pid))
        quantities = {h["symbol"]: h["quantity"]
                      for h in held["value"]["holdings"]}
        assert quantities["RELIANCE"] == 10, "the echoed preview was trusted"
        assert saved_rows["rejected"] == 0

    def test_dated_history_is_queryable(self, tmp_path):
        store, _, point = saved(tmp_path)
        pid = dispatch(store, point, "retail",
                       event(point, "ws_create", name="P"))["value"]["portfolio_id"]
        for stamp, qty in (("2026-01-02T09:15:00+05:30", 10),
                           ("2026-02-02T09:15:00+05:30", 25)):
            dispatch(store, point, "retail", event(
                point, "ws_commit", portfolio_id=pid,
                body=f"symbol,quantity,price\nRELIANCE,{qty},1300\n",
                effective_at=stamp))
        snaps = dispatch(store, point, "retail",
                         event(point, "ws_snapshots", portfolio_id=pid))
        assert len(snaps["value"]) == 2
        earlier = dispatch(store, point, "retail", event(
            point, "ws_holdings", portfolio_id=pid,
            as_of="2026-01-15T00:00:00+05:30"))
        assert earlier["value"]["holdings"][0]["quantity"] == 10
        assert earlier["value"]["basis"] == "historical"

    def test_a_watchlist_persists(self, tmp_path):
        store, _, point = saved(tmp_path)
        dispatch(store, point, "retail", event(
            point, "ws_watchlist_save", name="energy",
            items=["reliance", "ongc"]))
        lists = dispatch(store, point, "retail", event(point, "ws_watchlists"))
        assert lists["value"], "the watchlist did not persist"
        assert "RELIANCE" in json.dumps(lists["value"])

    def test_an_oversized_upload_is_refused(self, tmp_path):
        store, _, point = saved(tmp_path)
        pid = dispatch(store, point, "retail",
                       event(point, "ws_create", name="P"))["value"]["portfolio_id"]
        with pytest.raises(ValueError, match="larger than"):
            dispatch(store, point, "retail", event(
                point, "ws_preview", portfolio_id=pid, body="x" * 4_000_001))

    def test_a_nameless_portfolio_is_refused(self, tmp_path):
        store, _, point = saved(tmp_path)
        with pytest.raises(ValueError, match="name"):
            dispatch(store, point, "retail", event(point, "ws_create", name="  "))


# ------------------------------------------------------------------- T08


class TestT08ScenariosAreSavedRunAndReviewed:
    def _scenario(self, store, point, name="Energy shock"):
        return dispatch(store, point, "institutional", event(
            point, "sc_save", name=name, kind="rank_shock",
            steps=[dict(pillar="rmt", delta=0.2, horizon=3)],
            assumptions=[dict(key="shock", value=0.2, unit="rank",
                              justification="hypothetical sensitivity probe")]
        ))["value"]

    def test_a_scenario_is_saved_and_listed(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        made = self._scenario(store, point)
        listed = dispatch(store, point, "institutional", event(point, "sc_list"))
        assert made["scenario_id"] in json.dumps(listed["value"])

    def test_a_scenario_without_assumptions_is_refused(self, tmp_path):
        """An unlabelled hypothetical cannot be told apart from a measurement
        later, which is the whole reason assumptions are versioned."""
        store, _, point = saved(tmp_path, eligible=True)
        with pytest.raises(ValueError, match="assumptions"):
            dispatch(store, point, "institutional", event(
                point, "sc_save", name="N", kind="rank_shock",
                steps=[dict(pillar="rmt", delta=0.2)], assumptions=[]))

    def test_a_saved_scenario_runs_through_the_real_simulator(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        sid = self._scenario(store, point)["scenario_id"]
        run = dispatch(store, point, "institutional",
                       event(point, "sc_run", scenario_id=sid))
        assert run["value"]["results"], "no trajectory was produced"
        assert run["value"]["assumption_version"] == 1

    def test_rerunning_the_same_scenario_reuses_its_record(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        sid = self._scenario(store, point)["scenario_id"]
        first = dispatch(store, point, "institutional",
                         event(point, "sc_run", scenario_id=sid))
        again = dispatch(store, point, "institutional",
                         event(point, "sc_run", scenario_id=sid))
        assert again["value"]["reused"] is True
        assert again["value"]["run_key"] == first["value"]["run_key"]

    def test_two_scenarios_can_be_compared(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        left = self._scenario(store, point, "Left")["scenario_id"]
        right = self._scenario(store, point, "Right")["scenario_id"]
        out = dispatch(store, point, "institutional", event(
            point, "sc_compare", left_id=left, right_id=right))
        assert out["kind"] == "sc_compare" and out["value"]

    def test_a_review_binds_to_the_exact_revision(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        sid = self._scenario(store, point)["scenario_id"]
        verdict = dispatch(store, point, "institutional", event(
            point, "sc_review", scenario_id=sid, verdict="approved",
            comment="sensible probe"))
        assert verdict["value"]["assumption_version"] == 1

    def test_history_exposes_assumptions_and_runs(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        sid = self._scenario(store, point)["scenario_id"]
        dispatch(store, point, "institutional",
                 event(point, "sc_run", scenario_id=sid))
        hist = dispatch(store, point, "institutional",
                        event(point, "sc_history", scenario_id=sid))
        assert len(hist["value"]["assumptions"]) == 1
        assert len(hist["value"]["runs"]) == 1

    def test_an_export_carries_its_limitations_and_a_filename(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        sid = self._scenario(store, point)["scenario_id"]
        out = dispatch(store, point, "institutional",
                       event(point, "sc_export", scenario_id=sid))
        assert out["filename"].endswith(".json")
        assert any("not an economic forecast" in L
                   for L in out["value"]["limitations"])
        json.dumps(out["value"])              # must be serialisable for download

    def test_retail_cannot_reach_the_scenario_tools(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        for op in ("sc_list", "sc_save", "sc_run", "sc_export"):
            with pytest.raises(ValueError, match="not available"):
                dispatch(store, point, "retail", event(point, op))

    def test_a_scenario_needs_a_scored_baseline(self, tmp_path):
        """An unscored point has no reconciled state to perturb."""
        store, _, point = saved(tmp_path, eligible=False)
        sid = self._scenario(store, point)["scenario_id"]
        with pytest.raises(ValueError, match="baseline"):
            dispatch(store, point, "institutional",
                     event(point, "sc_run", scenario_id=sid))


# ------------------------------------------------------------------- T09


class TestT09RegulatorCaseLifecycle:
    def _case(self, store, point):
        return dispatch(store, point, "regulator", event(
            point, "case_open", title="Elevated coupling review",
            priority="high"))["value"]

    def test_a_case_opens_against_the_selected_alert(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        made = self._case(store, point)
        assert made["case_id"]
        listed = dispatch(store, point, "regulator", event(point, "case_list"))
        assert made["case_id"] in json.dumps(listed["value"])

    def test_the_full_lifecycle_runs_and_survives_a_restart(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        case = self._case(store, point)
        cid, version = case["case_id"], case["version"]

        attached = dispatch(store, point, "regulator", event(
            point, "case_evidence", case_id=cid, expected_version=version,
            refs=[dict(kind="run_point", ref_id=f"{point['run_id']}:{point['date']}",
                       revision="1", label="the scored point")]))
        version = attached["value"]["version"]

        decided = dispatch(store, point, "regulator", event(
            point, "case_decision", case_id=cid, expected_version=version,
            outcome="soft_warning", rationale="coupling elevated, no action yet",
            action_category="soft_warning"))
        version = decided["value"]["version"]

        # Distinct request ids per mutation. Reusing one is not a test
        # detail: `CaseStore` dedupes on `request_id`, so a repeated id is
        # correctly treated as a replay and the second status change is a
        # no-op. That is the right behaviour and the UI must send a fresh id
        # per request, which this now mirrors.
        closed = dispatch(store, point, "regulator", dict(event(
            point, "case_status", case_id=cid, expected_version=version,
            status="closed", reason="monitored"), id="req-close"))
        version = closed["value"]["version"]
        assert closed["value"]["status"] == "closed"

        reopened = dispatch(store, point, "regulator", dict(event(
            point, "case_status", case_id=cid, expected_version=version,
            status="reopened", reason="new evidence"), id="req-reopen"))
        assert reopened["value"]["version"] > version
        assert reopened["value"]["status"] == "reopened"

        # Every dispatch above built fresh store objects over the same
        # directory, so the case surviving here is what "after a restart"
        # means for this workflow.
        after = dispatch(store, point, "regulator", event(point, "case_list"))
        assert cid in json.dumps(after["value"])

    def test_a_repeated_request_id_is_a_replay_not_a_second_change(self, tmp_path):
        """The dedupe the test above had to work around, asserted directly."""
        store, _, point = saved(tmp_path, eligible=True)
        case = self._case(store, point)
        first = dispatch(store, point, "regulator", dict(event(
            point, "case_status", case_id=case["case_id"],
            expected_version=case["version"], status="investigating"),
            id="same"))
        again = dispatch(store, point, "regulator", dict(event(
            point, "case_status", case_id=case["case_id"],
            expected_version=first["value"]["version"], status="closed"),
            id="same"))
        assert again["value"]["status"] == "investigating", \
            "a replayed request id applied a second distinct change"

    def test_unpinned_evidence_is_refused(self, tmp_path):
        """A pointer with no revision cannot be replayed honestly."""
        store, _, point = saved(tmp_path, eligible=True)
        case = self._case(store, point)
        with pytest.raises(ValueError, match="revision"):
            dispatch(store, point, "regulator", event(
                point, "case_evidence", case_id=case["case_id"],
                expected_version=case["version"],
                refs=[dict(kind="run_point", ref_id="x")]))

    def test_a_decision_needs_a_rationale(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        case = self._case(store, point)
        with pytest.raises(ValueError, match="rationale"):
            dispatch(store, point, "regulator", event(
                point, "case_decision", case_id=case["case_id"],
                expected_version=case["version"], outcome="no_action",
                rationale=""))

    def test_an_export_carries_the_actual_actor_and_evidence(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        case = self._case(store, point)
        dispatch(store, point, "regulator", event(
            point, "case_evidence", case_id=case["case_id"],
            expected_version=case["version"],
            refs=[dict(kind="run_point", ref_id="r:1", revision="1")]))
        out = dispatch(store, point, "regulator", event(
            point, "case_export", case_id=case["case_id"]))
        body = json.dumps(out["value"])
        assert "r:1" in body
        assert out["filename"].endswith(".json")

    @pytest.mark.parametrize("role", ["retail", "institutional"])
    def test_only_the_regulator_reaches_cases(self, tmp_path, role):
        store, _, point = saved(tmp_path, eligible=True)
        with pytest.raises(ValueError, match="not available"):
            dispatch(store, point, role, event(point, "case_list"))

    def test_an_unknown_status_is_refused(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        case = self._case(store, point)
        with pytest.raises(ValueError, match="Unknown case status"):
            dispatch(store, point, "regulator", event(
                point, "case_status", case_id=case["case_id"],
                expected_version=case["version"], status="deleted"))

    def test_an_illegal_move_quotes_the_permitted_ones(self, tmp_path):
        """The store owns the state machine; this layer must not duplicate
        it. A real status in an illegal position is refused by CaseStore
        with the legal moves named."""
        from seraph.decision_support.cases import InvalidTransition
        store, _, point = saved(tmp_path, eligible=True)
        case = self._case(store, point)
        with pytest.raises(InvalidTransition, match="not a valid move"):
            dispatch(store, point, "regulator", event(
                point, "case_status", case_id=case["case_id"],
                expected_version=case["version"], status="approved"))

    def test_an_invented_priority_is_refused_at_the_boundary(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        with pytest.raises(ValueError, match="Unknown priority"):
            dispatch(store, point, "regulator", event(
                point, "case_open", title="A case", priority="critical"))


class TestWorkflowDispatchHygiene:
    def test_every_declared_op_is_served(self, tmp_path):
        """A declared operation that falls through to 'Unknown operation'
        would be a silent dead route."""
        from seraph.dashboard.console_backend import WORKFLOW_ROLES
        store, _, point = saved(tmp_path, eligible=True)
        for op, roles in WORKFLOW_ROLES.items():
            try:
                dispatch(store, point, roles[0], event(point, op))
            except ValueError as exc:
                assert "Unknown operation" not in str(exc), f"{op} is unserved"

    def test_a_stale_context_is_still_rejected(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        stale = dict(event(point, "ws_portfolios"), date="1999-01-01")
        with pytest.raises(ValueError, match="Stale"):
            dispatch(store, point, "retail", stale)

    def test_results_carry_the_request_context(self, tmp_path):
        store, _, point = saved(tmp_path, eligible=True)
        out = dispatch(store, point, "retail", event(point, "ws_portfolios"))
        assert out["context"]["request_id"] == "req-ws_portfolios"
        assert out["context"]["role"] == "retail"
