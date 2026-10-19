# Original frontend integration

The canonical launcher and original dashboard entry point now use the original
`assets/console.html` layout through a local Streamlit custom component. The globe,
raised states, animated arcs, asset models, drill-downs, news rail, sector stress,
commodity/weather panels, ticker, console, and role buttons remain available.
The original source asset is preserved unchanged. The first simplified connected
viewer is superseded; it is no longer the canonical route.

## What is actually connected

| Surface | Backend and status |
|---|---|
| Run/date controls | Complete runs from `RunStore`; one selected run/date |
| Console score, colour, explanation, uncertainty | Existing C9/C11 persisted outputs, projected by `gateway.build_view` |
| Historical trend | Actual saved CSRS through the selected date; no generated trend |
| Pillars / spectral diagnostics | Saved original Hawkes, RMT and Hamilton diagnostics; excluded status preserved |
| Astra forecasts | Actual saved predictions, separate from CSRS, institutional/regulator views |
| Retail role | Simplified warning/explanation, coverage and personal portfolio tools; no real model internals in payload |
| Institutional role | Pillars, decomposition, forecasts, playbook, shock simulator, portfolio coverage |
| Regulator role | Institutional tools plus provenance, explicit regime-path scenario and durable action journal |
| Portfolio input | JSON holdings passed to existing C11 coverage calculation; fabricated map flags never used |
| Shock simulator | Existing `simulate_shock` and C9 with matching saved weights; hypothetical rank shock, not forecast |
| Policy simulator | Existing `simulate_policy` with explicitly supplied regime paths; no invented macro-to-regime mapping |
| Regulatory log | Create/update/retract through existing authorized C11 API and transactional SQLite journal |
| Backtest button | Opens stored retrospective comparison; does not silently launch a costly new fit |
| News/geographic/sector stress | Original fabricated previews retained and tagged; separate from pillar computation |
| Strategic assets, weather, commodities, ticker | Original fabricated previews retained and tagged, including drill-downs |
| Missing pillar readings | Explicit unavailable status plus separately tagged original design-preview examples |

## Role boundary and interaction safety

Role buttons send a component event to Python. Python validates the role and
projects the new payload before sending it back. Restricted real fields are
omitted, not merely dimmed. On role changes the component clears previous
view content. A local user can select any role: this is a demonstrator, not
OAuth or authenticated access control. All endpoints here are local.

Every tool request carries run/date and an idempotency ID. Python rejects stale
contexts and unauthorized operations. Journal writes are idempotent and durable.
Portfolio inputs and scenario results are local session state; they do not modify
historical model runs. Portfolio holdings are current, not historical positions.

## Remaining dependencies, not hidden behind previews

- News ingestion, publication timestamps, deduplication, entity/sector mapping,
  and news-stress estimation are not implemented by this integration. The
  original fabricated geometry/stress examples are not pillar output.
- No measured geographic/sector flags exist in these runs. A supplied portfolio
  therefore reports uncovered exposure; fabricated flags never become real input.
- Full macro-policy scenario requires an approved fitted C7 `z -> xi` projector.
  The UI's manual regime path is explicitly hypothetical. Equal regime weights
  can produce no change; that is displayed without inventing a policy effect.
- Defensive actions' realised drawdown benefits remain unmeasured; C11 returns
  `None`, and the interface does not replace that with a claimed performance gain.
- Institution-level decompositions, contagion networks, and daily flow inputs
  are not available in saved runs. Tagged illustrative cards occupy those slots.
- The official Nifty 500 benchmark is not in the saved run contract. Saved CSRS
  and target baseline comparisons are available; FR41 benchmark overlay remains
  unavailable and is not replaced with a different index under that name.
- Source PostgreSQL and fresh model execution remain unverified. No change to
  scientific assumptions, preregistration or prediction acceptance was made.

## Verification

Latest focused regression: **163 passed**, recorded in
`test-results/frontend-integration.xml`. All five mechanical invariants and
`git diff --check` passed.

Focused tests cover role transport omissions, stale request rejection, portfolio
coverage, zero-shock identity, nonzero shock response, policy simplex validation,
and action create/update/retraction with idempotent durable persistence. Existing
C11 and prototype tests are reused. Browser checks exercise the actual component
role switch and Python simulator round trip, in addition to visual globe rendering.

Three.js r128 is served locally with its MIT license. Site-detail basemaps and
OpenStreetMap building requests retain the original external-network dependency;
failures are displayed by the original asset, not replaced with invented geometry.


Browser acceptance also verified regulator annotation submission against an
isolated SQLite QA store, restoration of that event from disk, and a switch to
retail that removed the journal, scenario controls and private decomposition.
The main historical-run journal remained untouched. The QA server was stopped.
