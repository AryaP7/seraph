/* Shared browser stub for the console-component harnesses.
 *
 * `bridge.js` is a plain IIFE written against the browser globals Streamlit's
 * component iframe provides. Running it needs a small DOM, a timer, a
 * postMessage seam, and a handful of globals it touches at load time
 * (`MutationObserver`, `crypto.randomUUID`, `PREVIEW_PILLARS`, the role
 * buttons it binds once).
 *
 * This was duplicated the moment a second harness needed it, and the copy
 * immediately diverged: it was missing `insertAdjacentHTML`, then
 * `MutationObserver`, discovered one crash at a time. One definition, so a
 * harness tests the bridge rather than the fidelity of its own stub.
 *
 * `build()` returns everything a harness needs and runs the real bridge file
 * unmodified. Nothing here ships.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
export const BRIDGE_PATH = resolve(
  here, "../../seraph/dashboard/console_component/bridge.js");

/** Elements the bridge touches unconditionally at load. */
const AT_LOAD = [
  "ticker", "online", "beaconKey", "dbody", "siteinfo", "stage",
  "preview-banner", "extra-content", "extra-title", "signals",
  "exposure", "viewConsole", "viewPillars", "viewMethod", "viewExtra",
  "c_csrs", "c_ci", "c_level", "c_mode", "c_plain", "c_fill", "c_tick",
  "c_sigcount", "c_signals", "c_trends", "c_mask", "c_shapley",
  "c_stack", "c_slabels", "c_fields", "c_access",
  "p_hawkes", "p_rmt", "p_hamilton",
  "m_flow", "m_std", "m_status", "m_limits",
];

export function build({ bridgePath = BRIDGE_PATH } = {}) {
  let now = 0;
  const timers = new Map();
  let timerId = 1;
  const registry = new Map();
  const sent = [];
  const listeners = [];
  const errors = [];

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
        toggle: (c, on) => (on ? this.classList._set.add(c)
          : this.classList._set.delete(c)),
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
        if (!registry.has(m[1])) registry.set(m[1], new Node(m[1]));
      }
    }
    get textContent() { return this._html; }
    set textContent(v) { this._html = String(v); }
    insertAdjacentHTML(_where, html) { this._html += html; }
    setAttribute(k, v) { this[k] = v; }
    getAttribute() { return null; }
    querySelector() { return new Node(); }
    querySelectorAll() { return []; }
    appendChild(n) { this.children.push(n); return n; }
    addEventListener() {}
    getContext() { return null; }
    focus() {}
    scrollIntoView() {}
    remove() {}
    closest() { return null; }
  }

  const ensure = (id) => {
    if (!registry.has(id)) registry.set(id, new Node(id));
    return registry.get(id);
  };
  for (const id of AT_LOAD) ensure(id);

  const document = {
    getElementById: (id) => registry.get(id) ?? null,
    querySelector: () => new Node(),
    querySelectorAll: () => [],
    createElement: (tag) => {
      const n = new Node("", tag);
      // Mirror a real DOM: once it has an id, getElementById finds it. The
      // bridge creates its global status bar this way.
      Object.defineProperty(n, "id", {
        get() { return n._id ?? ""; },
        set(v) { n._id = v; if (v) registry.set(v, n); },
        configurable: true,
      });
      return n;
    },
    body: new Node("body"),
  };

  const sandbox = {
    document,
    console: {
      log: () => {},
      warn: () => {},
      error: (...a) => errors.push(a.map(String).join(" ")),
    },
    PREVIEW_PILLARS: {
      hawkes: { label: "x", val: 0, rows: [] },
      rmt: { label: "x", val: 0, rows: [] },
      hamilton: { label: "x", val: 0, rows: [] },
    },
    crypto: { randomUUID: () => "req-fixed-id" },
    parent: { postMessage: (msg) => sent.push(msg) },
    MutationObserver: class { observe() {} },
    window: {
      addEventListener: (type, fn) => listeners.push({ type, fn }),
      dispatchEvent: () => {},
    },
    Event: class { constructor(t) { this.type = t; } },
    Blob: class { constructor(p) { this.parts = p; } },
    URL: { createObjectURL: () => "blob:x", revokeObjectURL: () => {} },
    setTimeout: (fn, ms) => {
      const id = timerId++;
      timers.set(id, { fn, at: now + ms });
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
  };
  sandbox.globalThis = sandbox;
  // Pre-declare the bridge's test hook; without this it exposes nothing.
  sandbox.__SERAPH_BRIDGE_TEST__ = null;
  sandbox.window.document = document;

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

  vm.createContext(sandbox);
  vm.runInContext(readFileSync(bridgePath, "utf8"), sandbox,
    { filename: "bridge.js" });

  function advance(ms) {
    now += ms;
    for (const [id, t] of [...timers]) {
      if (t.at <= now) { timers.delete(id); t.fn(); }
    }
  }

  /** Drive one render. Returns the thrown message, or null. */
  function render(payload) {
    let threw = null;
    for (const l of listeners) {
      if (l.type !== "message") continue;
      try {
        l.fn({
          source: sandbox.parent,
          data: { type: "streamlit:render", args: { payload } },
        });
      } catch (err) {
        threw = String((err && err.message) || err);
      }
    }
    return threw;
  }

  const requests = () =>
    sent.filter((m) => m.type === "streamlit:setComponentValue");

  return { Node, registry, ensure, document, sandbox, sent, listeners,
           errors, render, advance, requests, roleButtons };
}
