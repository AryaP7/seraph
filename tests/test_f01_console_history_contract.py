# F01 — the original console's history contract, benchmark overlay and flow
"""`console_backend` has returned an OBJECT for `history` since the FR41
benchmark overlay landed, and `bridge.js` still called `history.forEach`.

Every render of the original console therefore threw

    TypeError: history.forEach is not a function

and because `renderConsole()` runs *before* the role toggles, the liveness
banner, `applyNewsLayer()` and `show()` in the message handler, the whole
update aborted. The console drew nothing and the news layer never applied.
This was the audit's named demonstration blocker.

These tests feed a **real** `project_run` payload to the real `bridge.js`
through a Node harness, which is the audit's own acceptance condition: "Feed
the actual current Python payload to the JavaScript rendering path;
object-shaped history renders." A screenshot cannot establish the absence of
a JavaScript exception, so this does it in the suite instead.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from seraph.dashboard import console_backend
from seraph.orchestration.prototype import InferenceSession
from seraph.orchestration.run_store import RunStore

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "js" / "history_harness.mjs"
BRIDGE = ROOT / "seraph" / "dashboard" / "console_component" / "bridge.js"

node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is not on PATH; the JS harness needs Node >= 20")


def _points(tmp_path, dates):
    """A saved run with a scored point per date, as the console reads them."""
    from seraph.decision_support import explain
    from seraph.fusion.score import score
    from seraph.shared_types import ReconciledState

    store = RunStore(tmp_path / "f01.sqlite")
    manifest = dict(mode="f01 contract fixture",
                    data_available_through=dates[-1])
    run = store.begin(manifest)
    session = InferenceSession(list(dates))
    weights = session.weights
    points = []
    for index, day in enumerate(dates):
        inputs = {p: dict(score_eligible=True,
                          value=0.2 + 0.05 * index,
                          variance=0.01,
                          information_timestamp=f"{day}T15:30:00+05:30")
                  for p in ("hawkes", "rmt", "hamilton")}
        point = session.step(day, inputs, [], run_id=run)
        state = ReconciledState(
            ts=point["evaluation_timestamp"],
            x_hat=(0.2, 0.4, 0.6),
            P=((0.01, 0, 0), (0, 0.01, 0), (0, 0, 0.01)),
            tau_last_update=(point["evaluation_timestamp"],) * 3,
            mask=(True, True, False), mode="kalman")
        composite = score(reconciled=state, xi=(1 / 3,) * 3,
                          weights=weights).value
        point["reconciled"] = state.model_dump(mode="json")
        point["composite"] = composite.model_dump(mode="json")
        point["explanation"] = explain(composite).value
        store.put(run, point)
        points.append(point)
    store.finish(run, len(points))
    return store, manifest, points


@pytest.fixture(scope="module")
def payload(tmp_path_factory):
    """A real payload from `project_run`, not a synthesised one."""
    tmp_path = tmp_path_factory.mktemp("f01")
    # Dates the stored FII/DII print covers, so the flow card's measured
    # path is exercised rather than only its unavailable path. The
    # date-bounding itself is asserted separately on a historical payload.
    _, manifest, points = _points(
        tmp_path, ["2026-10-15", "2026-10-16", "2026-10-19"])
    return console_backend.project_run(points[-1], manifest, points,
                                       "institutional")


@pytest.fixture(scope="module")
def harness(payload, tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    path = tmp_path_factory.mktemp("f01-payload") / "payload.json"
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    done = subprocess.run(["node", str(HARNESS), str(path)], cwd=ROOT,
                          capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        pytest.fail(f"harness exited {done.returncode}\n{done.stderr[-2000:]}")
    return json.loads(done.stdout)


class TestTheBackendContract:
    """Asserted on the real payload, so the JS side is tested against what
    Python actually sends rather than against a guess."""

    def test_history_is_an_object_not_a_list(self, payload):
        assert isinstance(payload["history"], dict)

    def test_it_carries_the_documented_keys(self, payload):
        history = payload["history"]
        for key in ("rows", "series", "units", "coverage"):
            assert key in history, key

    def test_each_row_carries_its_benchmark_availability(self, payload):
        rows = payload["history"]["rows"]
        assert rows
        for row in rows:
            assert "date" in row and "csrs" in row
            assert "benchmark_available" in row

    def test_the_flow_payload_is_present(self, payload):
        """It always was. The tools panel simply never read it."""
        assert "flow" in payload
        assert "available" in payload["flow"]


@node
class TestObjectShapedHistoryRenders:
    """The audit's acceptance condition, exactly."""

    def test_the_render_handler_does_not_throw(self, harness):
        assert harness["render_threw"] is None, harness["render_threw"]
        assert harness["object_history_renders"] is True

    def test_the_harness_was_given_the_object_shape(self, harness):
        """Otherwise this would pass by testing a list."""
        assert harness["payload_history_is_object"] is True
        assert harness["payload_history_has_rows"] is True

    def test_the_csrs_chart_is_drawn(self, harness):
        assert harness["csrs_chart_present"] is True

    def test_the_benchmark_is_either_drawn_or_explained(self, harness):
        """FR41 is an overlay. With the index series present it draws; with
        it absent the panel says why, rather than showing a bare CSRS line
        that looks like the overlay is working."""
        assert (harness["benchmark_line_rendered"]
                or harness["benchmark_absence_explained"])

    def test_coverage_is_reported(self, harness):
        assert harness["coverage_reported"] is True


@node
class TestTheHandlerNoLongerAbortsWholesale:
    """The part the `forEach` failure silently skipped: every statement after
    `renderConsole()` in the message handler."""

    def test_the_liveness_banner_still_renders(self, harness):
        assert harness["banner_rendered"] is True

    def test_the_news_layer_still_runs(self, harness):
        assert harness["news_layer_ran"] is True

    def test_a_throwing_renderer_does_not_suppress_news_or_role_updates(
            self, harness):
        """The audit's requirement, stated precisely: "a localized optional-
        chart failure can produce a visible chart error without suppressing
        all role/news updates".

        The payload here has `view: null`, which is fault injection --
        `project_run` always supplies a view. The console renderer throws, is
        caught, and reports visibly; the banner and the news layer, which sit
        BELOW it in the handler and used to be skipped entirely, both still
        run.

        `show()` can still propagate an error from such a malformed payload,
        and that is deliberately not wrapped: it is the last statement in the
        handler, so nothing is lost after it, and the audit asked for a narrow
        boundary around the known failure rather than a blanket try/catch over
        the whole component.
        """
        assert harness["broken_view_reports_visibly"] is True
        assert harness["news_layer_ran_after_failure"] is True
        assert harness["banner_rendered_after_failure"] is True


@node
class TestGapsSurviveRatherThanBeingFilled:
    def test_a_missing_benchmark_date_is_not_forward_filled(self, harness):
        """Forward-filling draws a flat segment where there is no
        measurement. With gaps present there must be more than one polyline;
        a filled series would collapse to exactly one."""
        if harness["rows_missing_benchmark"] and harness["rows_with_benchmark"]:
            assert harness["polyline_count"] >= 2
        else:
            assert harness["polyline_count"] >= 1

    def test_the_row_counts_reconcile(self, harness):
        assert (harness["rows_with_benchmark"]
                + harness["rows_missing_benchmark"]) == harness["rows_total"]


@node
class TestTheFlowCardShowsMeasurementsOrNothing:
    def test_the_example_placeholders_are_gone(self, harness):
        """`FII net (example) -1200`, `DII net (example) 900` and
        `Residual share (example) 0.72` were three fabricated numbers sitting
        where a measurement belongs."""
        assert harness["no_example_placeholders"] is True
        assert harness["bridge_has_no_example_kv_calls"] is True

    def test_it_reads_the_real_payload(self, harness):
        assert harness["flow_payload_present"] is True

    def test_the_backend_never_serves_a_later_print(self, payload):
        """A historical decision must not show a flow print from after it.
        `market_flow` filters `date <= as_of`, so this is asserted on the
        backend where the guarantee lives."""
        flow = payload["flow"]
        if flow.get("available") and flow.get("date"):
            assert flow["date"] <= payload["date"]


@node
class TestALegacyListStillRenders:
    """One normalisation point, so an older payload degrades rather than
    crashing. Shape checks scattered through every chart would be the
    alternative, and that is how the first mismatch went unnoticed."""

    def test_a_list_payload_renders(self, harness):
        assert harness["legacy_list_renders"] is True

    def test_it_declares_the_benchmark_unavailable(self, harness):
        assert harness["legacy_list_states_no_benchmark"] is True


class TestTheRendererHasOneNormalisationPoint:
    def test_no_chart_does_its_own_shape_check(self):
        """`historyOf` exists so the object/list decision is made once."""
        source = BRIDGE.read_text(encoding="utf-8")
        assert "function historyOf(" in source
        assert source.count("Array.isArray(h)") == 1

    def test_spark_no_longer_calls_foreach_on_the_payload(self):
        source = BRIDGE.read_text(encoding="utf-8")
        body = source.split("function spark(", 1)[1].split("\nfunction ", 1)[0]
        assert "history.forEach" not in body

    def test_the_bridge_still_parses(self):
        if shutil.which("node") is None:
            pytest.skip("node is not on PATH")
        done = subprocess.run(["node", "--check", str(BRIDGE)],
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr
