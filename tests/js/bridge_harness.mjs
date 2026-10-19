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
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const bridgePath = resolve(here, "../../seraph/dashboard/console_component/bridge.js");

// ---------------------------------------------------------------- tiny DOM
let now = 0;
const timers = new Map();
let timerId = 1;

class Node {
  constructor(id = "", tag = "div") {
    this.id = id;
    this.tagName = tag.toUpperCase();
    this._html = "";
    this.value = "";
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.classList = {
      _set: new Set(),
      add: (c) => this.classList._set.add(c),
      remove: (c) => this.classList._set.delete(c),
      toggle: (c, on) => (on ? this.classList._set.add(c) : this.classList._set.delete(c)),
      contains: (c) => this.classList._set.has(c),
    };
    this.onclick = null;
    this.oninput = null;
    this.onchange = null;
    this.childNodes = [];
  }
  get innerHTML() { return this._html; }
  set innerHTML(v) {
    this._html = String(v);
    // Re-materialise any element the bridge will look up by id afterwards.
    for (const m of this._html.matchAll(/id="([a-zA-Z0-9_-]+)"/g)) {
      const id = m[1];
      if (!registry.has(id)) registry.set(id, new Node(id));
    }
  }
  get textContent() { return this._html; }
  set textContent(v) { this._html = String(v); }
  insertAdjacentHTML(_where, html) { this._html += html; }
  setAttribute(k, v) { this[k] = v; }
  querySelector() { return new Node(); }
  querySelectorAll() { return []; }
  appendChild(n) { this.children.push(n); return n; }
}

const registry = new Map();
const ensure = (id) => {
  if (!registry.has(id)) registry.set(id, new Node(id));
  return registry.get(id);
};
// Elements the bridge touches unconditionally at load.
for (const id of ["ticker", "online", "beaconKey", "dbody", "siteinfo", "stage",
                  "preview-banner", "extra-content", "extra-title", "signals",
                  "exposure", "viewConsole", "viewPillars", "viewMethod", "viewExtra",
                  "c_csrs", "c_ci", "c_level", "c_mode", "c_plain", "c_fill", "c_tick",
                  "c_sigcount", "c_signals", "c_trends", "c_mask", "c_shapley",
                  "c_stack", "c_slabels", "c_fields", "c_access",
                  "p_hawkes", "p_rmt", "p_hamilton",
                  "m_flow", "m_std", "m_status", "m_limits"]) ensure(id);

const sent = [];
const requests = () =>
  sent.filter((m) => m.type === "streamlit:setComponentValue");
const document = {
  getElementById: (id) => registry.get(id) ?? null,
  querySelector: () => new Node(),
  querySelectorAll: () => [],
  createElement: (tag) => {
    const n = new Node("", tag);
    // Mirror a real DOM: once it has an id and is attached, getElementById
    // finds it. The bridge creates its global status bar this way.
    const define = Object.getOwnPropertyDescriptor(Node.prototype, "id");
    Object.defineProperty(n, "id", {
      get() { return n._id ?? ""; },
      set(v) { n._id = v; if (v) registry.set(v, n); },
      configurable: true,
    });
    return n;
  },
  body: new Node("body"),
};
const listeners = [];
const sandbox = {
  document,
  console,
  PREVIEW_PILLARS: { hawkes: { label: "x", val: 0, rows: [] },
                     rmt: { label: "x", val: 0, rows: [] },
                     hamilton: { label: "x", val: 0, rows: [] } },
  crypto: { randomUUID: () => "req-fixed-id" },
  parent: { postMessage: (msg) => sent.push(msg) },
  MutationObserver: class { observe() {} },
  window: {
    addEventListener: (type, fn) => listeners.push({ type, fn }),
    dispatchEvent: () => {},
  },
  Event: class { constructor(t) { this.type = t; } },
  setTimeout: (fn, ms) => { const id = timerId++; timers.set(id, { fn, at: now + ms }); return id; },
  clearTimeout: (id) => timers.delete(id),
};
sandbox.globalThis = sandbox;
// Pre-declare the bridge's test hook; without this it exposes nothing.
sandbox.__SERAPH_BRIDGE_TEST__ = null;
sandbox.window.document = document;

function advance(ms) {
  now += ms;
  for (const [id, t] of [...timers]) {
    if (t.at <= now) { timers.delete(id); t.fn(); }
  }
}

function render(payload) {
  for (const l of listeners) {
    if (l.type === "message") {
      l.fn({ source: sandbox.parent, data: { type: "streamlit:render", args: { payload } } });
    }
  }
}

// Role buttons must exist BEFORE the bridge loads: it binds their onclick
// handlers once, at load time.
for (const id of ["roles", "route-crumb"]) ensure(id);
const roleButtons = {};
for (const role of ["retail", "institutional", "regulator"]) {
  const b = new Node("", "button");
  b.dataset.role = role;
  roleButtons[role] = b;
}
document.querySelector = (sel) => {
  const m = /#roles button\[data-role="([a-z]+)"\]/.exec(sel);
  if (m) return roleButtons[m[1]] ?? null;
  return new Node();
};
document.querySelectorAll = (sel) =>
  sel === "#roles button" ? Object.values(roleButtons) : [];

// -------------------------------------------------------------- run bridge
vm.createContext(sandbox);
vm.runInContext(readFileSync(bridgePath, "utf8"), sandbox, { filename: "bridge.js" });

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
const beforeSameRole = now;
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

process.stdout.write(JSON.stringify(out, null, 2));
