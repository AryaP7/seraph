/* F01 — behavioural harness for the console history/benchmark/flow contract.
 *
 * The audit's acceptance is explicit: "Feed the actual current Python payload
 * to the JavaScript rendering path; object-shaped history renders." So this
 * harness does not synthesise a payload. It reads one that
 * `console_backend.project_run` produced (written by the pytest wrapper to
 * argv[2]) and drives it through the real `bridge.js` message handler.
 *
 * The browser stub comes from `console_sandbox.mjs`, shared with
 * `bridge_harness.mjs`. A private copy was tried first and immediately
 * diverged — missing `insertAdjacentHTML`, then `MutationObserver` — so the
 * harness was testing its own stub's fidelity rather than the bridge.
 *
 * Reports JSON on stdout. Nothing here ships.
 */
import { readFileSync } from "node:fs";
import { build, BRIDGE_PATH } from "./console_sandbox.mjs";

const payloadPath = process.argv[2];
if (!payloadPath) {
  console.error("usage: node history_harness.mjs <payload.json>");
  process.exit(2);
}

const env = build();
const { registry, render, sandbox, errors } = env;
const html = (id) => (registry.get(id)?.innerHTML ?? "");

const payload = JSON.parse(readFileSync(payloadPath, "utf8"));
const out = {};

// ------------------------------------------- the real, object-shaped payload
out.payload_history_is_object = payload.history !== null
  && typeof payload.history === "object" && !Array.isArray(payload.history);
out.payload_history_has_rows = Array.isArray(
  payload.history && payload.history.rows);

out.render_threw = render(payload);
out.object_history_renders = out.render_threw === null;

const trends = () => html("c_trends");
out.csrs_chart_present = trends().includes("CSRS 0..1");
out.benchmark_line_rendered = trends().includes("benchmark return history");
out.benchmark_absence_explained = trends().includes("Benchmark");
out.coverage_reported = /\d+ of \d+ dates matched/.test(trends())
  || trends().includes("Benchmark");

// The statements that sit BELOW renderConsole() in the message handler, and
// which the old `history.forEach` failure skipped entirely.
out.banner_rendered = html("preview-banner").length > 0;
out.news_layer_ran = typeof sandbox.SERAPH_NEWS_FRESHNESS !== "undefined"
  || typeof sandbox.window.SERAPH_NEWS_FRESHNESS !== "undefined";
out.pillars_rendered = html("p_rmt").length > 0 || html("viewPillars").length > 0;
out.method_rendered = html("m_flow").length > 0;

// -------------------------------------------------------- gaps, not fill-ins
const rows = (payload.history && payload.history.rows) || [];
out.rows_total = rows.length;
out.rows_with_benchmark = rows.filter((r) => r.benchmark_available).length;
out.rows_missing_benchmark = rows.filter((r) => !r.benchmark_available).length;
out.polyline_count = (trends().match(/<polyline/g) || []).length;

// ------------------------------------------------------------- the flow card
out.flow_payload_present = Boolean(payload.flow);
out.flow_available = Boolean(payload.flow && payload.flow.available);
const bridgeSource = readFileSync(BRIDGE_PATH, "utf8");
/* The CALL, not the word. A first version searched the source for
   "net (example)" and matched the comment that explains the removal -- the
   file documents what it no longer does, so a text search finds the exact
   string it is trying to forbid. */
out.bridge_has_no_example_kv_calls =
  !bridgeSource.includes("kv('FII net (example)'")
  && !bridgeSource.includes("kv('DII net (example)'")
  && !bridgeSource.includes("kv('Residual share (example)'");
out.bridge_reads_data_flow = bridgeSource.includes("function flowHTML()");

/* The flow card lives in the TOOLS view, which only renders when that view
   is shown. `show` is published on the bridge's own test hook. */
const api = sandbox.__SERAPH_BRIDGE_TEST__;
out.test_hook_available = typeof api?.show === "function";
render({ ...payload, role: "regulator" });
if (out.test_hook_available) {
  try { api.show("tools"); } catch (err) { out.tools_threw = String(err); }
}
const toolsHTML = html("extra-content");
out.tools_rendered = toolsHTML.length > 0;
out.no_example_placeholders = !toolsHTML.includes("(example)");
out.flow_card_present = toolsHTML.includes("residual flow");
/* Case-insensitive: the backend's reason begins "no FII/DII print has been
   ingested yet", lowercase, and a capitalised check missed it. */
const toolsLower = toolsHTML.toLowerCase();
out.flow_card_reports_state = ["fii net", "flow unavailable",
  "no fii/dii print", "flow store could not be read", "no flow payload"]
  .some((s) => toolsLower.includes(s));
out.flow_card_shows_measurements = toolsHTML.includes("FII net")
  && toolsHTML.includes("As of");

// ------------------------------------------------- a legacy list still works
out.legacy_list_renders = render({
  ...payload,
  history: rows.map((r) => ({ date: r.date, csrs: r.csrs })),
}) === null;
out.legacy_list_states_no_benchmark = trends().includes("Benchmark");

// --------------------------------- one throwing renderer must not abort all
out.broken_view_does_not_abort_handler = render({ ...payload, view: null })
  === null;
out.broken_view_reports_visibly = trends().includes("failed to render")
  || errors.some((e) => e.includes("render failed"));
out.news_layer_ran_after_failure =
  typeof sandbox.SERAPH_NEWS_FRESHNESS !== "undefined"
  || typeof sandbox.window.SERAPH_NEWS_FRESHNESS !== "undefined";
out.banner_rendered_after_failure = html("preview-banner").length > 0;

out.console_errors = errors.slice(0, 5);
console.log(JSON.stringify(out, null, 2));
