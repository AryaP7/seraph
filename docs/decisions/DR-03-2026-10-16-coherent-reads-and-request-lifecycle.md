# DR-03 — Coherent reads, scoped caching, and a recoverable request lifecycle

**Date:** 2026-10-16
**Backlog:** `FIX10`, `FIX11` (audit findings A11, A12)
**Status:** adopted and implemented
**Closes:** Phase 1.

## 1. Every supported view reads one coherent run/as-of bundle (`FIX10`)

### Canonical route — `seraph/dashboard/prototype_app.py`

Already read one complete run from `RunStore`; it now also **caches** that read,
scoped by `(store_path, run_id, role)`:

- `_complete_runs(store_path)` — complete runs only. A run sealed but awaiting
  its report (`inference_complete`, see DR-02) is deliberately not offered.
- `_bundle(store_path, run_id, role)` — points, report and action log in one
  object. The action log is fetched **only** for the role permitted to see it,
  so a cached regulator payload cannot be handed to a retail session.
- The cache is invalidated after an `action` write, because that write changes
  durable state the bundle holds.

Before this, every Streamlit rerun re-parsed every point of the selected run —
81 for the COVID window, 5361 for a full-history replay.

### Legacy route — `seraph/dashboard/datasource.py`

This serves `app.main()`'s Streamlit-native panels. It is **kept** and remains
supported; no panel was removed. It took three independent
`ORDER BY … LIMIT 1` reads — newest CSRS, newest Hamilton row, newest RMT row —
which silently mixed dates whenever one component lagged. It now:

1. resolves a single `as_of` from the CSRS row (or from an explicit `as_of`
   argument), and
2. reads every other component **bounded by that same date**
   (`WHERE date <= $1 ORDER BY date DESC LIMIT 1`).

A component with no row at or before `as_of` is reported `unavailable`. One
older than `as_of` is labelled `"<its date> (stale relative to as_of …)"` and
sets `coherent: False`. Neither is ever presented as the current reading.

### Caching that is actually applied

The old module docstring claimed `st.cache_data` was applied. It was not — the
decorator was absent. `cached_bundle(scope)` now applies it for real, keyed by
`CacheScope(source, as_of, user_id, org_id)`. `user_id` and `org_id` are
present but unset: they exist in the key **now** so that adding identity at
`AUTH01`/`AUTH02` cannot accidentally serve one tenant a payload built for
another. TTL is 60 s (30 s on the canonical route) — short, because this is a
risk surface.

## 2. A recoverable request lifecycle (`FIX11`)

### What was wrong

`bridge.js` used a bare `pending` boolean, set on send and cleared only by the
next `streamlit:render`. A lost or slow response latched it forever and every
later click was silently dropped. `tools()` rebuilt the forms on each render,
so a half-typed holdings JSON or `xi_path` vanished whenever a result arrived.
And a response was rendered without checking it still belonged to the run, date
and role on screen.

### What it does now

| Concern | Behaviour |
|---|---|
| In-flight state | one `inflight` record: `{id, op, args, sentAt, timer, context}` |
| Status | a visible `#req-status` line — `READY` / `SENDING…` / `DONE` / `FAILED` / `NO RESPONSE` / `DISCARDED`, with `role="status"` and `aria-live="polite"` so it is not colour-only |
| Timeout | `REQUEST_TIMEOUT_MS = 15000`; on expiry the status becomes `timed_out` and Retry/Cancel appear |
| Retry | resends the **same** idempotency id, so a request that did arrive cannot be applied twice. `RunStore.action()` already deduplicates on it (DR-02) |
| Duplicate suppression | a second click while a request is in flight is refused with an explanatory status, not queued |
| Drafts | `captureDrafts()` on every input/change and before every send; `restoreDrafts()` on re-render. A render triggered by an arriving result cannot destroy a draft |
| Context binding | `dispatch()` stamps every result with `{run_id, date, role, request_id}`; `project_run()` discards a result whose context does not match and returns `discarded_result` with the reason; the bridge shows that reason instead of the stale value |
| No permanent latch | after a timeout, cancel, failure or discard the bridge accepts new work |

The server remains the boundary: `dispatch()` still re-validates run, date and
role before any computation or write. The bridge changes are the visible half.

### Testing it for real

`tests/js/bridge_harness.mjs` loads the **unmodified** `bridge.js` in a Node VM
with stub DOM, timer and `postMessage` globals and drives the whole lifecycle:
send → duplicate suppressed → timeout → retry with the same id → answer →
draft preserved → context change → discard → accept new work. `pytest` runs it
and asserts each outcome, skipping where Node is absent.

The bridge exposes a **test seam** only when a harness pre-declares
`globalThis.__SERAPH_BRIDGE_TEST__ = null`. In the browser that global does not
exist, so nothing is exported. A test asserts the seam stays conditional.

## Verification

- `tests/test_fix10_fix11_transport.py` — 24 tests (16 Python, 8 harness-driven).
- Core partition: **558 passed, 13 skipped, 1 xfailed, 0 failures**.
- Canonical console re-rendered against a real 81-point archive run via
  Streamlit `AppTest`: no exception, run and date selectors populated, all
  three role projections built, manifest carrying the decision clock.
- Five mechanical invariants pass; `git diff --check` clean.

## Not done here

- No browser screenshot was taken, so there is no visual before/after. The
  `AppTest` render and the Node harness together cover behaviour, not pixels.
- `demo_data.py` remains reachable only behind `SERAPH_DEMO=1` with its banner;
  it now also stamps `data_status: "preview"` on what it returns. It is still
  never a fallback for a failed fetch.
