# Source-to-screen inventory

Created 2026-10-16 (Phase 0 / `DOC01`). Inventory of every visible panel and
operation in the canonical frontend, with its current source, data status,
intended real producer, permission boundary and acceptance test.

**Canonical route** (established by inspection, not assumption):

```
launch_prototype.ps1
  → streamlit run seraph/dashboard/prototype_app.py      (port 8512)
      → RunStore(prototype_runs/seraph.sqlite)           complete runs only
      → console_backend.project_run()                    role projection
          → gateway.build_view()                         restricted-field omission
      → components.declare_component('seraph_console',
            path=seraph/dashboard/console_component/)
          → index.html  (original console; globe, panels, drill-downs)
          → bridge.js   (payload render + tool requests back to Python)
          → preview_pillars.js, three.r128.min.js
      ← console_backend.dispatch()                       portfolio / shock / policy / action
```

`seraph/dashboard/app.py` opens the same integrated console.
`seraph/dashboard/connected_frontend.py` + `assets/connected.*` is the
**superseded** simplified viewer. `seraph/dashboard/datasource.py` and
`demo_data.py` are **legacy compatibility routes** that independently fetch
latest rows (see `FIX10`). `scripts/run_prototype.py` is the execution entry
point; `seraph/orchestration/prototype.py` holds `run_archive()` (archive
replay) and `run_source_endpoint()` (fresh diagnostic, opt-in, DSN required).

## Data-status vocabulary

A label travels **with the datum**, not only as a panel banner. Semantics are
fixed here and must not drift:

| Status | Meaning |
|---|---|
| `observed` | Directly measured/recorded by an identified source at a stated time |
| `derived` | Computed by an identified SERAPH producer from `observed` inputs; carries producer + version |
| `estimate` | Model output with uncertainty whose method and version are published |
| `scenario` | Hypothetical; depends on user- or analyst-supplied assumptions |
| `preview` | Illustrative placeholder; **never** an input to any calculation |
| `unavailable` | Known to be absent; distinguishes *structural* (cannot exist) from *transient* (this update failed) |
| `stale` | Real but older than its freshness policy; carries the as-of time and the policy |

`unknown` (no coverage) is never rendered as `0` or as measured quiet.

---

## 1. Shell and header

| # | Surface | Element | Current source | Status | Intended producer | Permission | Acceptance test |
|---|---|---|---|---|---|---|---|
| 1 | Brand / nav | `nav a[data-view]` × 8 | static | n/a | unchanged | public | `QA01` keyboard + route test |
| 2 | Role buttons | `#roles button` | `bridge.request('role')` → `prototype_app` validates | `derived` | `AUTH01/02` server-resolved grants | **any local user may select any role today** | `AUTH02` forged-role request denied |
| 3 | Local clock | `#clock` | browser wall clock | `observed` (client) | session-aware decision clock (`FIX01`) shown beside it | public | `FIX01` clock displays session close, not wall time |
| 4 | "1,019 desks" | `#online` | hardcoded, tagged FABRICATED | `preview` | real session count or removal of the metric | public | `QA01` asserts preview tag present |
| 5 | RUN BACKTEST cta | `.cta` → `show('backtest')` | opens saved report | `derived` | unchanged + `DATA04` benchmark overlay | non-retail for detail | `test_console_backend` role omission |
| 6 | Preview banner | `#preview-banner` | static + run/date/role | mixed | per-datum status chips (`NEWS06`) | public | `QA01` banner reflects actual preview set |
| 7 | Ticker | `#ticker` | static `COMMOD`-style array | `preview` | `NEWS08` licensed price feed | public | `NEWS08` units/currency/stale indicator present |

## 2. Risk map (`view=map`) — the primary experience

| # | Surface | Element | Current source | Status | Intended producer | Permission | Acceptance test |
|---|---|---|---|---|---|---|---|
| 8 | Globe, graticule, bathymetry | `#stage` + `globe_geometry.js` | generated geometry, Three.js r128 local | n/a | unchanged | public | `QA02` WebGL fallback + reduced motion |
| 9 | Raised states / choropleth | `SECTORS`/geo arrays in `index.html` | static | `preview` | `NEWS03` place master + `NEWS05` estimates | public | `NEWS06` every raised state links to evidence |
| 10 | Animated arcs | `EXPOSURE` array | static | `preview` | `NEWS04` documented exposure relationships | public | `NEWS04` every arc has an inspectable relationship + evidence |
| 11 | Strategic assets + `#acount` | `ASSETS` array, `#assetcard` | static 13 sites | `preview` | `NEWS03` verified asset/operator/location/capacity registry | public (aggregate) | `NEWS03` ambiguous entities abstain |
| 12 | Asset drill-down modal | `#sitemodal` `#siteinfo` | static + OSM/Overpass basemap | `preview` + live tiles | `NEWS03` + `NEWS08` | public | `NEWS08` tile/Overpass outage shows missing basemap, never invented geometry |
| 13 | Beacon key / infrastructure legend | `#beaconKey` | static legend | `preview` | registry-driven legend | public | `QA02` non-colour status cue |
| 14 | Map mode switcher | `#modes` | client-side | n/a | unchanged | public | `QA01` |
| 15 | Globe status line | `#status` | client-side | n/a | add source-health line (`OPS01`) | public | `OPS01` outage visible |
| 16 | LATEST SIGNALS rail + `#sigcount` | `SIGNALS` array, `#signals` | static | `preview` | `NEWS01/02` registered sources, dedup, correction chains | public; saved searches need `AUTH04` | `NEWS02` ten syndicated copies ≠ ten confirmations |
| 17 | INPUT COMMODITIES | `#commod` | static | `preview` | `NEWS08` licensed feed | public | `NEWS08` explicit units/session conventions |
| 18 | METEOROLOGICAL INPUTS | `#met` | static advisory cards | `preview` | `NEWS08` weather/advisory feed + polygon∩asset | public | `NEWS08` issue/valid times explicit |
| 19 | SECTOR STRESS | `#stress` | static, tagged NEWS ESTIMATE · FABRICATED | `preview` | `NEWS05` news estimate **and**, separately, `FIX07`/`PORT03` measured Hawkes sector diagnostic | public | two series with distinct units/coverage/uncertainty; never merged |
| 20 | PORTFOLIO EXPOSURE map card | `#exposure` | static "29% AMBER" | `preview` | `PORT01`–`PORT04` owned holdings + exposure trail | **owner only** | `AUTH02` cross-tenant read denied |
| 21 | Crawling headlines footer | `#crawl` | static, tagged | `preview` | `NEWS01/02` | public | as #16 |

## 3. CONSOLE (`view=console`)

| # | Surface | Element | Current source | Status | Intended producer | Permission | Acceptance test |
|---|---|---|---|---|---|---|---|
| 22 | CSRS value | `#c_csrs` | saved C9 `composite.csrs` | `derived` | `PIPE01` fresh run | all roles | `test_prototype_viewer` |
| 23 | Confidence interval | `#c_ci`, `#c_fill`, `#c_tick` | saved C9 (Astra-corrected `aᵀPa`) | `derived` | unchanged | `ciLower/Upper` omitted for retail | `test_console_backend` field omission |
| 24 | Alert level | `#c_level` | provisional `.5/.75` | `derived` (uncalibrated) | accepted alert policy (`VAL01`) | all roles | thresholds documented as provisional, not accepted |
| 25 | Reconciliation mode | `#c_mode` | saved C8 `mode` | `derived` | unchanged | non-retail | — |
| 26 | Signals / decision / coverage / warning | `#c_sigcount`, `#c_signals` | run payload | `derived` | add session clock (`FIX01`) | all roles | `FIX01` decision timestamp = session close |
| 27 | Availability mask | `#c_mask` | C8 `mask` | `derived` | `FIX02` honest structural/transient | non-retail | `FIX02` transient outage keeps mask |
| 28 | Trend sparkline | `#c_trends` | saved CSRS ≤ selected date | `derived` | unchanged; `FIX10` one run/as-of contract | all roles | `FIX10` no mixed-run history |
| 29 | Regime probabilities | `#c_stack`, `#c_slabels` | Hamilton causal archive, NOT_PRODUCTION | `derived`, diagnostic-only | `POL01` fitted artifact if eligibility changes | non-retail | exclusion decision preserved |
| 30 | Pillar decomposition (Shapley) | `#c_shapley` | saved C9 contributions | `derived` | unchanged | non-retail | `test_console_backend` |
| 31 | What this means | `#c_plain` | C11 `explain()` | `derived` | add news-channel explanation with separate provenance (`FR44`) | all roles | provenance stays separate |
| 32 | Access / field count | `#c_fields`, `#c_access` | role + payload keys | `derived` | `AUTH01/02` real identity | all roles | `AUTH02` |

## 4. PILLARS, METHOD, SIGNAL FEED, EXPOSURE, FORECASTS, BACKTEST

| # | Surface | Current source | Status | Intended producer | Permission | Acceptance test |
|---|---|---|---|---|---|---|
| 33 | Pillar cards (`#p_hawkes/#p_rmt/#p_hamilton`) | saved pillar dicts; raw `detail` JSON | `derived` | real spectrum/density/regime-history visualisation; measured sector diagnostics; `FIX07` parameter lineage | non-retail | `FIX07` saved artifact reconstructs its intensity |
| 34 | "Unfilled design preview" cards | `preview_pillars.js` | `preview` | replaced per pillar as diagnostics land | non-retail | preview never enters scoring |
| 35 | METHOD → Pipeline / Standardisation / Validation / Limitations | run manifest + `limitations` | `derived` | human-readable artifact lineage, model-version comparison, source freshness | manifest regulator-only | `test_console_backend` manifest omission |
| 36 | SIGNAL FEED | saved C11 explanation + fabricated rail | mixed | `NEWS01/02/05` | all roles | `NEWS06` |
| 37 | EXPOSURE view | supplied holdings overlay + fabricated card | mixed | `PORT01`–`PORT04` | owner only | `AUTH02`, `PORT04` no overlap inflation |
| 38 | FORECASTS | saved Astra predictions table | `derived` | `PIPE02` fresh cycle, `VAL01` shadow ledger | non-retail | `PIPE02` immutable model/input identity |
| 39 | BACKTEST | saved retrospective comparison + sparkline | `derived` | `DATA04` official Nifty 500 overlay; point-in-time portfolio backtests | non-retail detail | `DATA04` benchmark versioned |

## 5. TOOLS — real operations

| # | Operation | Backend | Status | Gaps | Permission | Acceptance test |
|---|---|---|---|---|---|---|
| 40 | Portfolio coverage | `dispatch('portfolio')` → `portfolio_overlay(holdings, {})` | `derived` | empty flag map ⇒ always uncovered (`PORT03`); no persistence (`PORT01`); no history (`PORT02`) | all roles, own data | `test_c11_portfolio` |
| 41 | Pillar shock simulator | `dispatch('shock')` → `simulate_shock` + C9 | `scenario` | not an economic shock (`SCEN02`); no saved scenarios (`SCEN01`) | non-retail | zero-shock identity test |
| 42 | Regime-path policy simulator | `dispatch('policy')` → `simulate_policy` | `scenario` | hypothetical `xi_path` only; no fitted `z → xi` (`POL01/02`) | regulator | simplex validation test |
| 43 | Regulator action journal | `RunStore.action()` → C11 `RegulatoryActionLog` | `observed` (local) | no-op defect (`FIX08`); actor is a role string (`AUTH03`); no case lifecycle (`CASE01`) | regulator | `FIX08` no-op update succeeds |
| 44 | Defensive playbook | `playbook()` | `derived` | `drawdownReductionPct=None` — correctly withheld (`VAL02`) | non-retail | no fabricated benefit claim |
| 45 | Institutional / residual flow card | static example values, tagged | `preview` | `DATA08` accumulated flow history | non-retail | `DATA08` scope definitions preserved |
| 46 | Institution / contagion preview | static example values, tagged | `preview` | `CASE02` authorized submissions; `FR15` identifiable contagion | regulator | never inferred from market bars |

## 6. Transport and request lifecycle

| # | Concern | Current | Gap | Acceptance test |
|---|---|---|---|---|
| 47 | Request envelope | `{op, id: uuid, run_id, date, …}`; Python re-validates run/date and role | no status/timeout/retry; `pending` latch blocks forever on a lost response; tool forms regenerated on each render, losing drafts (`FIX11`) | `FIX11` lost response retried; draft preserved; role/date switch during pending cannot display a stale result |
| 48 | Role projection | `gateway.build_view` omits restricted fields; `dispatch` re-checks | role is client-selected (`AUTH01/02`); no tenant scope; holdings can ride in a run manifest | `AUTH02` cross-organisation denial |
| 49 | Caching | none on the canonical route; `datasource.py` claims caching without a decorator | scope cache by identity/organisation/result context (`FIX10`) | `FIX10` scoped-cache test |

---

## Gate record

Phase 0 gate items:

- [x] Canonical launcher and component route established by inspection (§ header).
- [x] Every visible panel and operation inventoried with source, status,
      intended producer, permission boundary and acceptance test (49 rows).
- [x] Shared product-metadata requirements defined — see
      [PRODUCT-CONTRACTS.md](PRODUCT-CONTRACTS.md) §1.
- [x] Dependency-aware status register — see
      [DEVELOPMENT-STATUS.md](DEVELOPMENT-STATUS.md).
- [x] First implementation slice specified — P1-S1 (`FIX01` + `FIX02`).
- [ ] Browser capture of the current UI for later visual comparison — **not done**;
      no browser automation was run in this session. Recorded as an open item in
      the handoff rather than claimed.
