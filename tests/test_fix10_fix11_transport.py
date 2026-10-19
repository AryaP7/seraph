"""FIX10 / FIX11 — coherent reads, scoped caching, and recoverable requests.

Audit findings pinned here:

* A11 — the legacy `datasource.py` route independently fetched the newest CSRS,
  Hamilton and RMT rows, silently mixing dates whenever one component lagged,
  and its docstring claimed an `st.cache_data` that was never applied.
* A12 — the canonical bridge used a bare `pending` boolean with no timeout or
  retry, so a lost response latched it forever; tool forms were rebuilt on
  every render, losing drafts; and a late response was rendered without
  checking it still belonged to the current run, date and role.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest

from seraph.dashboard import datasource
from seraph.dashboard.console_backend import dispatch, project_run, result_matches
from seraph.orchestration.prototype import InferenceSession
from seraph.orchestration.run_store import RunStore

BRIDGE = Path(__file__).resolve().parents[1] / "seraph/dashboard/console_component/bridge.js"


# ------------------------------------------------------- FIX10 coherent read


def _csrs_row(ts=None):
    from seraph.shared_types import IST
    return {"ts": ts or datetime(2020, 3, 2, 15, 30, tzinfo=IST), "csrs": 0.4, "var_csrs": 0.01, "ci_lower": 0.3, "ci_upper": 0.5,
            "shapley": (0.1, 0.2, 0.1), "alert_level": "amber",
            "mask": (True, True, False),
            "effective_weights": ((1 / 3,) * 3,) * 3, "xi_mode": "uniform",
            "weights_artefact_id": "a" * 64, "reconciliation_mode": "kalman"}


def test_a_stale_component_is_labelled_not_presented_as_current():
    raw = {"csrs": _csrs_row(), "as_of": "2020-03-02",
           "hamilton": {"date": date(2020, 3, 2), "xi_1": 0.5, "xi_2": 0.3,
                        "xi_3": 0.2, "lsd_t": 1.1},
           "rmt": {"date": date(2020, 2, 20), "eigenvalues": [80.0] + [1.0] * 99,
                   "f_t": 0.8, "lambda_minus": 0.5, "lambda_plus": 1.5}}
    state = datasource.assemble(raw)
    assert state["as_of"] == "2020-03-02"
    assert state["component_as_of"]["hamilton"] == "2020-03-02"
    assert "stale relative to as_of 2020-03-02" in state["component_as_of"]["rmt"]
    assert state["coherent"] is False


def test_a_fully_aligned_bundle_is_reported_coherent():
    raw = {"csrs": _csrs_row(), "as_of": "2020-03-02",
           "hamilton": {"date": date(2020, 3, 2), "xi_1": 0.5, "xi_2": 0.3,
                        "xi_3": 0.2, "lsd_t": 1.1},
           "rmt": {"date": date(2020, 3, 2), "eigenvalues": [80.0] + [1.0] * 99,
                   "f_t": 0.8, "lambda_minus": 0.5, "lambda_plus": 1.5}}
    state = datasource.assemble(raw)
    assert state["coherent"] is True
    assert set(state["component_as_of"].values()) == {"2020-03-02"}


def test_a_missing_component_is_unavailable_not_borrowed_from_another_date():
    state = datasource.assemble({"csrs": _csrs_row(), "as_of": "2020-03-02",
                                 "hamilton": None, "rmt": None})
    assert state["component_as_of"] == {"hamilton": "unavailable", "rmt": "unavailable"}
    assert "hamilton" not in state["pillar_scores"] and state["spectral"] == {}


def test_nothing_scored_yields_none_rather_than_a_placeholder():
    assert datasource.assemble(None) is None
    assert datasource.assemble({"csrs": None}) is None


def test_the_component_queries_are_bounded_by_the_resolved_as_of_date():
    """The defect was three independent `ORDER BY ... LIMIT 1` reads."""
    source = Path(datasource.__file__).read_text(encoding="utf-8")
    body = source.split("async def _fetch")[1].split("def assemble")[0]
    for table in ("hamilton_output", "rmt_output"):
        statement = next(line for line in body.splitlines() if table in line)
        assert "date <= $1" in statement, f"{table} read is not bounded by as_of"
    assert body.count("ORDER BY ts DESC LIMIT 1") == 2   # the two CSRS variants only


def test_the_cache_scope_already_carries_identity_slots():
    scope = datasource.CacheScope(source="dsn", as_of="2020-03-02")
    assert scope.key() == ("dsn", "2020-03-02", None, None)
    other = datasource.CacheScope(source="dsn", as_of="2020-03-02", org_id="org-b")
    assert scope.key() != other.key(), "organisation must change the cache key"


def test_cache_data_is_actually_applied_now():
    source = Path(datasource.__file__).read_text(encoding="utf-8")
    assert "@st.cache_data" in source
    calls = {"n": 0}

    def fake_load(scope):
        calls["n"] += 1
        return {"scope": scope.key()}

    original = datasource.load_bundle
    datasource.load_bundle = fake_load
    try:
        scope = datasource.CacheScope(source="unit-test-scope", as_of="2020-03-02")
        first = datasource.cached_bundle(scope)
        second = datasource.cached_bundle(scope)
    finally:
        datasource.load_bundle = original
    assert first == second
    assert calls["n"] == 1, "a second read of the same scope must be served warm"


# -------------------------------------------- FIX11 result/context binding


def saved(tmp_path):
    store = RunStore(tmp_path / "ui.sqlite")
    manifest = dict(mode="synthetic test fixture", data_available_through="2020-01-01")
    run = store.begin(manifest)
    inputs = {p: dict(score_eligible=p != "hamilton", value=0.3, reason="ok",
                      information_timestamp="2020-01-01T15:30:00+05:30",
                      absence=None if p != "hamilton" else "structural",
                      absence_reason=None if p != "hamilton" else "no_data_coverage")
              for p in ("hawkes", "rmt", "hamilton")}
    point = InferenceSession(["2020-01-01"]).step("2020-01-01", inputs, [], run_id=run)
    store.put(run, point)
    store.finish(run, ["2020-01-01"])
    return store, manifest, point


def test_dispatch_stamps_every_result_with_its_request_context(tmp_path):
    store, manifest, point = saved(tmp_path)
    result = dispatch(store, point, "institutional", dict(
        id="req-1", run_id=point["run_id"], date=point["date"], op="shock",
        pillar="rmt", magnitude=0.1, horizon=3))
    assert result["context"] == dict(run_id=point["run_id"], date=point["date"],
                                     role="institutional", request_id="req-1")


def test_a_matching_result_is_still_shown(tmp_path):
    store, manifest, point = saved(tmp_path)
    result = dispatch(store, point, "institutional", dict(
        id="req-1", run_id=point["run_id"], date=point["date"], op="shock",
        pillar="rmt", magnitude=0.1, horizon=3))
    payload = project_run(point, manifest, [point], "institutional", result=result)
    assert payload["result"] is not None
    assert payload["discarded_result"] is None
    assert payload["context"] == dict(run_id=point["run_id"], date=point["date"],
                                      role="institutional")


def test_a_result_from_another_date_is_discarded_with_a_reason(tmp_path):
    store, manifest, point = saved(tmp_path)
    result = dispatch(store, point, "institutional", dict(
        id="req-1", run_id=point["run_id"], date=point["date"], op="shock",
        pillar="rmt", magnitude=0.1, horizon=3))
    result["context"]["date"] = "2019-12-31"
    payload = project_run(point, manifest, [point], "institutional", result=result)
    assert payload["result"] is None
    assert payload["discarded_result"]["discarded"] is True
    assert "different run, date or role" in payload["discarded_result"]["reason"]
    assert payload["discarded_result"]["produced_for"]["date"] == "2019-12-31"


def test_a_result_from_another_run_is_discarded(tmp_path):
    store, manifest, point = saved(tmp_path)
    result = dispatch(store, point, "institutional", dict(
        id="req-1", run_id=point["run_id"], date=point["date"], op="shock",
        pillar="rmt", magnitude=0.1, horizon=3))
    result["context"]["run_id"] = "some-other-run"
    assert project_run(point, manifest, [point], "institutional",
                       result=result)["result"] is None


def test_a_result_from_another_role_is_discarded(tmp_path):
    store, manifest, point = saved(tmp_path)
    result = dispatch(store, point, "institutional", dict(
        id="req-1", run_id=point["run_id"], date=point["date"], op="shock",
        pillar="rmt", magnitude=0.1, horizon=3))
    payload = project_run(point, manifest, [point], "retail", result=result)
    assert payload["result"] is None and payload["discarded_result"]["discarded"]


def test_a_contextless_legacy_result_is_not_trusted(tmp_path):
    store, manifest, point = saved(tmp_path)
    assert result_matches({"kind": "shock"}, point["run_id"], point["date"], "retail") is False
    assert project_run(point, manifest, [point], "institutional",
                       result={"kind": "shock", "value": []})["result"] is None


def test_a_stale_request_is_still_rejected_before_any_computation(tmp_path):
    store, manifest, point = saved(tmp_path)
    with pytest.raises(ValueError, match="Stale request"):
        dispatch(store, point, "institutional", dict(
            id="req-1", run_id=point["run_id"], date="2019-12-31", op="shock",
            pillar="rmt", magnitude=0.1, horizon=3))


# ------------------------------------------------- FIX11 bridge behaviour
#
# The bridge is driven for real, not grepped: `tests/js/bridge_harness.mjs`
# loads the unmodified file in a Node VM with stub DOM/timer/postMessage
# globals and exercises the request lifecycle. Skipped where Node is absent.


HARNESS = Path(__file__).resolve().parent / "js" / "bridge_harness.mjs"


@pytest.fixture(scope="module")
def bridge():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available; the bridge harness needs a JS runtime")
    proc = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        pytest.fail("bridge harness failed:\n" + proc.stderr[-3000:])
    return json.loads(proc.stdout)


def test_the_bridge_loads_and_exposes_its_lifecycle_for_testing(bridge):
    assert bridge["bridge_loaded"] is True
    assert bridge["no_status_line_before_tools"] is True
    assert bridge["status_rendered_in_tools"] is True


def test_a_request_is_sent_once_and_shows_a_pending_status(bridge):
    assert bridge["request_sent"] is True
    assert bridge["status_pending"] is True
    assert bridge["duplicate_suppressed"] is True,         "a second click while in flight must not queue a duplicate command"


def test_a_lost_response_times_out_instead_of_latching_forever(bridge):
    """This is audit finding A12: `pending=true` with nothing to clear it."""
    assert bridge["status_timed_out"] is True
    assert bridge["retry_offered"] is True


def test_retry_reuses_the_same_idempotency_id(bridge):
    assert bridge["retry_sent"] is True
    assert bridge["retry_reused_id"] is True,         "a new id would let a request that did arrive be applied twice"


def test_a_matching_answer_resolves_the_request(bridge):
    assert bridge["status_succeeded"] is True


def test_a_draft_survives_the_render_an_arriving_result_triggers(bridge):
    assert bridge["draft_preserved"] is True


def test_changing_context_mid_flight_discards_rather_than_displays(bridge):
    assert bridge["context_change_discards"] is True
    assert bridge["no_stale_result_rendered"] is True


def test_the_bridge_accepts_new_work_after_a_discard(bridge):
    assert bridge["accepts_new_request_after_discard"] is True


# --- source-level guards: the shapes the harness cannot observe ----------


def test_the_bridge_no_longer_uses_a_bare_pending_latch():
    source = BRIDGE.read_text(encoding="utf-8")
    assert not re.search(r"\bpending\s*=\s*(true|false)\b", source), (
        "the boolean latch is what made a lost response permanent")
    assert "inflight" in source and "REQUEST_TIMEOUT_MS" in source


def test_the_test_seam_is_inert_unless_a_harness_asks_for_it():
    source = BRIDGE.read_text(encoding="utf-8")
    assert "__SERAPH_BRIDGE_TEST__===null" in source.replace(" ", ""), (
        "the seam must require a pre-declared null hook, not export unconditionally")


# ---------------------------------------- T03 / audit finding R05 ---------
#
# Role buttons changed the projection but left the map on screen: `active`
# started at 'map' and every response ended with `show(active)`. And clicking
# the ALREADY-ACTIVE role waited for `data.role !== previous.role`, which can
# never become true — it timed out after 15s and blocked every later request,
# with the only status control hidden inside Tools.


def test_each_role_has_a_landing_route(bridge):
    assert bridge["role_home_table"] == {
        "retail": "console", "institutional": "pillars", "regulator": "tools"}


def test_a_role_change_navigates_to_that_roles_home(bridge):
    assert bridge["role_change_sent_request"] is True
    assert bridge["role_change_navigates"] is True
    assert bridge["role_change_left_map"] is True, \
        "the audit's finding: all three clicks left the map visible"


def test_clicking_the_already_active_role_is_a_harmless_no_op(bridge):
    assert bridge["same_role_sends_no_request"] is True
    assert bridge["same_role_acknowledged"] is True
    assert bridge["same_role_opens_home"] is True


def test_a_same_role_click_never_times_out_or_blocks(bridge):
    assert bridge["same_role_never_times_out"] is True
    assert bridge["accepts_request_after_same_role_click"] is True, \
        "the stall used to block every later request until cancelled"


def test_request_status_is_visible_outside_tools(bridge):
    assert bridge["status_visible_outside_tools"] is True
