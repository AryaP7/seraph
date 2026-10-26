/* FIX11 — behavioural harness for seraph/dashboard/console_component/bridge.js.
 *
 * The bridge is a plain IIFE written against the browser globals Streamlit's
 * component iframe provides. This harness supplies the smallest DOM, timer and
 * postMessage stubs it needs, runs the real file unmodified, then drives the
 * request lifecycle and reports the outcome as JSON on stdout. Pytest reads
 * that JSON, so the assertions live with the other FIX11 tests.
 *
 * Nothing here is shipped: it exists only so "a lost response can be retried"
 * is a tested claim rather than a grep for the word "retry".
 */
import { build } from "./console_sandbox.mjs";

/* The browser stub lives in `console_sandbox.mjs`, shared with
   `history_harness.mjs`. It used to be inline here; the moment a second
   harness needed it the copy diverged — missing `insertAdjacentHTML`, then
   `MutationObserver` — so a harness was testing the fidelity of its own stub
   instead of the bridge. One definition now. */
const env = build();
const { registry, sent, requests, sandbox, render, advance, ensure } = env;

const base = {
  run_id: "run-a", date: "2020-01-01", role: "institutional",
  timestamp: "2020-01-01T15:30:00+05:30", cutoff: "2020-01-01T15:30:00+05:30",
  mode: "test", view: { csrs: 0.4, alertLevel: "amber", explanation: "x", playbook: {} },
  history: [{ date: "2020-01-01", csrs: 0.4 }], mask: [true, true, false],
  pillars: {}, predictions: [], limitations: [], portfolio: null, report: null,
  result: null, discarded_result: null,
  context: { run_id: "run-a", date: "2020-01-01", role: "institutional" },
};

const out = {};
const statusText = () => (registry.get("req-status")?.innerHTML ?? "");
const globalStatusText = () =>
  (registry.get("req-status-global")?.innerHTML ?? "");

render(base);
// The status line lives in the TOOLS card, so it does not exist yet.
out.no_status_line_before_tools = statusText() === "";

// Open TOOLS so the forms and status line exist, then type a draft.
const api = sandbox.__SERAPH_BRIDGE_TEST__;
out.bridge_loaded = typeof api?.request === "function";

// Drive the lifecycle directly through the message/postMessage seam.
const toolsNodes = ["holdings", "shock-pillar", "magnitude", "horizon", "shock-go",
                    "portfolio-go", "req-status"];
for (const id of toolsNodes) ensure(id);
api.show("tools");
out.status_rendered_in_tools = statusText().length > 0;

ensure("holdings").value = '[{"symbol":"RELIANCE","value":100}]';
ensure("magnitude").value = "0.25";
api.captureDrafts();

// Fire a request.
sent.length = 0;
api.request("shock", { pillar: "rmt", magnitude: 0.25, horizon: 3 });
out.request_sent = sent.length === 1 && sent[0].value.op === "shock";
out.request_id = sent[0]?.value?.id;
out.status_pending = statusText().includes("SENDING");

// A second click while in flight must not queue a duplicate request.
api.request("shock", { pillar: "rmt", magnitude: 0.25, horizon: 3 });
out.duplicate_suppressed = sent.length === 1;

// No response: the timeout must surface, not latch forever.
advance(16000);
out.status_timed_out = statusText().includes("NO RESPONSE");
out.retry_offered = statusText().includes("req-retry");

// Retry reuses the SAME idempotency id.
api.retry();
out.retry_sent = sent.length === 2;
out.retry_reused_id = sent.length === 2 && sent[1].value.id === sent[0].value.id;

// The answer finally arrives, stamped with that request id.
render({ ...base, result: { kind: "shock", value: [], basis: "b",
                            context: { run_id: "run-a", date: "2020-01-01",
                                       role: "institutional", request_id: out.request_id } } });
api.show("tools");
out.status_succeeded = statusText().includes("DONE");
out.draft_preserved = ensure("holdings").value === '[{"symbol":"RELIANCE","value":100}]';

// A new request, then the user switches date before the answer comes back.
sent.length = 0;
api.request("shock", { pillar: "rmt", magnitude: 0.25, horizon: 3 });
render({ ...base, date: "2020-01-02",
         context: { run_id: "run-a", date: "2020-01-02", role: "institutional" },
         discarded_result: { discarded: true, reason: "produced for another date",
                             produced_for: { date: "2020-01-01" } } });
api.show("tools");
out.context_change_discards = statusText().includes("DISCARDED");
out.no_stale_result_rendered = !registry.get("extra-content").innerHTML.includes('"kind": "shock"');

// After a discard the bridge accepts new work again (no permanent latch).
sent.length = 0;
api.request("portfolio", { holdings: [] });
out.accepts_new_request_after_discard = sent.length === 1;


// ---------------------------------------------------- T03 / audit R05
// Role buttons used to leave the map on screen and a same-role click used to
// hang for 15 seconds. Drive both through the real handlers.
// Clear anything left in flight by the earlier lifecycle section.
api.cancelInflight();
render({ ...base, role: "retail" });
out.role_home_table = api.roleHome;

// A DIFFERENT role: the response must navigate to that role's landing route.
sent.length = 0;
api.clickRole("institutional");
out.role_change_sent_request =
  requests().length === 1 && requests()[0].value.op === "role";
render({ ...base, role: "institutional",
         context: { run_id: "run-a", date: "2020-01-01", role: "institutional" } });
out.role_change_navigates = api.active() === api.roleHome.institutional;
out.role_change_left_map = api.active() !== "map";

// The SAME role: acknowledged at once, no request, no timeout.
sent.length = 0;
// (The harness clock was captured here and never read; the shared
//  sandbox owns the clock now and `advance` is the only thing that
//  needs it.)
api.clickRole("institutional");
out.same_role_sends_no_request = requests().length === 0;
out.same_role_acknowledged = globalStatusText().includes("DONE");
advance(20000);
out.same_role_never_times_out = !globalStatusText().includes("NO RESPONSE");
out.same_role_opens_home = api.active() === api.roleHome.institutional;

// A later ordinary request still works: the same-role click did not latch.
sent.length = 0;
api.request("portfolio", { holdings: [] });
out.accepts_request_after_same_role_click = requests().length === 1;

// The status bar exists outside Tools.
api.show("map");
out.status_visible_outside_tools = globalStatusText().length > 0;

/* The panel FABRICATED tag must describe the payload, not the page's load
   state. Both directions are asserted: a CONNECTED surface loses the tag,
   and an absent channel keeps it. The tag is the only thing protecting the
   preview layer from being read as data, so neither direction may regress --
   a stale tag above sourced headlines teaches the reader to ignore it, and a
   missing tag over a preview is worse. */
const NEWS_HEADINGS = ["h3-signals", "h3-assets", "h3-stress"];
// The real page stamps every card heading at load via
// querySelectorAll('main .card h3'); this sandbox's querySelectorAll returns
// [], so the starting state is seeded here instead. Without this the
// elements would not exist, getElementById would return null, and the
// assertions below would pass vacuously -- which they did on the first run.
const seedTagged = () => {
  // renderNewsPanels() reads these bodies before writing them, so they must
  // exist or the handler throws before the re-tag is reached -- which is
  // exactly how the first version of this test passed vacuously.
  for (const id of ["signals", "stress", "sigcount", "assets",
                    "assetscope", "acount"]) ensure(id);
  for (const id of NEWS_HEADINGS) {
    ensure(id);
    registry.get(id).innerHTML =
      'LATEST <span class="fabricated">FABRICATED PREVIEW</span>';
  }
};
const headingHTML = (id) => (registry.get(id)?.innerHTML ?? "");
const TAGGED = /class="fabricated"/;
seedTagged();
out.harness_seeded_the_load_time_tag =
  NEWS_HEADINGS.every((id) => TAGGED.test(headingHTML(id)));

// 1. Connected: three surfaces reported connected, so their headings must
//    carry no fabricated tag after the render.
render({ ...base, news: {
  status: "connected", mode: "historical_decision",
  as_of: "2020-01-01T15:30:00+05:30",
  connected_surfaces: ["signals", "assets", "sector_stress"],
  preview_surfaces: [],
  source_coverage: { covered: 3, total: 3 },
  surfaces: { signals: { items: [], scope: {} } },
  pagination: { total: 0 }, globe: {}, role_view: null } });
out.connected_surface_loses_the_fabricated_tag =
  !TAGGED.test(headingHTML("h3-signals"))
  && !TAGGED.test(headingHTML("h3-assets"))
  && !TAGGED.test(headingHTML("h3-stress"));

// 2. Absent: the channel is not connected, so every heading must be tagged
//    again -- including ones cleared by the connected render above, which is
//    what makes this a real round trip rather than a one-way clear.
render({ ...base, news: {
  status: "absent", version: null, reason: "no news store is attached",
  surfaces: {}, preview_only: true } });
out.absent_channel_restores_the_fabricated_tag =
  TAGGED.test(headingHTML("h3-signals"))
  && TAGGED.test(headingHTML("h3-assets"))
  && TAGGED.test(headingHTML("h3-stress"));

// 3. A surface reported as preview while others are connected keeps its tag:
//    the label is per surface, never per payload.
render({ ...base, news: {
  status: "connected", mode: "historical_decision",
  as_of: "2020-01-01T15:30:00+05:30",
  connected_surfaces: ["signals"], preview_surfaces: ["assets"],
  source_coverage: { covered: 1, total: 3 },
  surfaces: { signals: { items: [], scope: {} } },
  pagination: { total: 0 }, globe: {}, role_view: null } });
out.tag_is_per_surface_not_per_payload =
  !TAGGED.test(headingHTML("h3-signals"))
  && TAGGED.test(headingHTML("h3-assets"));

process.stdout.write(JSON.stringify(out, null, 2));
