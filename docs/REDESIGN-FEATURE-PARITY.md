# Redesigned frontend — feature parity against Classic

**Date:** 2026-10-25 · **Baseline:** `docs/evidence/frontend-baseline-2026-10-24/`
(revision `9a792b5` **plus** the uncommitted working tree, copied file-by-file)

Classic (`seraph/dashboard/prototype_app.py`, `.\launch_prototype.ps1`, port
8512) is **unchanged** and remains available as a fallback. Redesigned
(`seraph/dashboard/redesign/app.py`, `.\launch_redesign.ps1`, port 8520) is a
second frontend over the same backends.

**Every screen is built. None is a placeholder, and no gap rows remain.** No
workflow requires switching back to Classic. §5 lists the places where the
redesign deliberately behaves differently, each with its reason.

Legend: **✅ present** · **◑ partial / by design** (what differs is stated).
**No ⬜ gap rows remain.**

---

## 1. Shell, identity and honesty framing

| Classic feature | Status | Note |
|---|---|---|
| Page title and honesty caption | ✅ | Top bar + footer, same substance |
| Role switching (retail / institutional / regulator) | ✅ | The console's own role buttons, not a sidebar; every screen re-reads under the new role, and the switch lands on that role's landing route |
| RBAC enforced at the transport boundary | ✅ | `gateway.build_view` reused unchanged. Tested: a retail payload does not *contain* institutional fields (`test_retail_payload_does_not_contain_institutional_fields`) |
| Store configuration + env overrides | ✅ | `store_paths()` **imported** from Classic, so both frontends resolve the same stores |
| Single supervised news worker, however started | ✅ | `news_service.ensure_worker()`; OS lock stands the second frontend aside. Tested against the real lock |

## 2. Overview (CSRS)

| Feature | Status | Note |
|---|---|---|
| Composite dial, FR29 interval, alert level | ✅ | Two arcs, each a real quantity, each in the legend |
| **Unavailable composite** | ✅ | Track kept, nothing filled, `—` + reason. Never zero |
| D2 mask degraded notice + explanation | ✅ | |
| Publication-gate verdict and all `why` reasons | ✅ | Passed through verbatim |
| FR41 overlay (CSRS vs Nifty 500) | ✅ | Two independent axes, both units named |
| Coverage + representativeness | ✅ | Including the "not a validation result" note |
| Three pillar cards (Hawkes / RMT / Hamilton) | ✅ | One colour table keyed by `PILLAR_ORDER`; four render states |
| Hamilton structural absence · Hawkes exclusion | ✅ | Engine's own reasons, never 0 |
| Signed Shapley contributions | ✅ | Symmetric axis in score units; explicitly not percentages |
| D2 effective weights | ✅ | Drawn as shares, with why the two widgets differ |
| Pillar-readings detail chart | ✅ | A pillar with no value is not drawn and is named |
| Measured sector activity (FR14) | ✅ | Table, or reason + `blocked_by` |
| Holdings / portfolio coverage | ✅ | Activated from the Workspace screen |
| Market flow FII/DII (FR45/FR51) | ✅ | With the market-aggregate scope caveat |
| Decision timeline | ✅ | Scoreless session is hollow, not zero |
| F1/F2 channel separation statement | ✅ | Asserted structurally, not just stated |
| Loading / historical / unavailable states | ✅ | |

## 3. Forecast & early warning — SERAPH's stated purpose

| Classic feature (`prediction_panel`) | Status | Note |
|---|---|---|
| Forecast ledger id, issuance, mode, maturity | ✅ | |
| Warning banner with level and reason | ✅ | A level the console does not know is shown verbatim, not mapped to a colour |
| Staleness, shown *before* the warning | ✅ | Last valid forecast retained, labelled not current |
| Predicted probability / threshold / horizon | ✅ | |
| UNVALIDATED banner, before any number is interpreted | ✅ | |
| "What is predicted" + model manifest | ✅ | |
| Measured pillar features table | ✅ | Plus a bar chart; a feature with no value is not drawn |
| Warning policy and budget | ✅ | Including the abstention case |
| Realised history (Brier / AUC / base rate / false episodes) | ✅ | |
| Calibration table | ✅ | |
| **Calibration chart** | ➕ | New: predicted vs realised with the perfect-calibration diagonal. Empty bins are dropped, not plotted at zero. This installation over-predicts and the chart shows it |
| Forecast vs threshold chart | ✅ | Gaps break the line |
| Alarm episodes | ✅ | |

## 4. Other screens

| Classic feature | Status | Note |
|---|---|---|
| **News intelligence** — signal rail, sector routes, geography, assets, source coverage, freshness, method/manifest, temporal policy, paging, current/historical clock | ✅ | Own F2 palette; pillar colours are never used here. **Fixes a Classic defect** (§6) |
| **Workspace — portfolios**: list, holdings, basis, upload preview with rejected rows, commit snapshot, snapshot history, create, activate/clear, watchlists | ✅ | Through `console_backend.dispatch`; verified end-to-end by creating a portfolio that persisted to `workspace.sqlite` |
| **Workspace — scenarios**: list, run, render execution, history, review, export, compare, save rank-shock, scenario builders | ✅ | Classic's `scenario_ui.render_run` / `forms` reused, not reimplemented |
| **Workspace — regulator cases**: list, open, attach evidence, record decision, change status, export | ✅ | Verified end-to-end by opening a case (`triage · v1`) |
| **Evaluation** — design, saved runs, measured/unavailable/unpublishable counts, comparability warning, Tables A/B/C, absences, run-as-text, provenance | ✅ | Read-only by design (§5) |
| **Risk console** — the Three.js component and all eight views (`map`, `console`, `feed`, `pillars`, `exposure`, `forecasts`, `tools`, `method`), the globe, the role switcher, and every operation it emits: `portfolio`, `shock`, `policy`, `action` (the **FR49 regulator action journal**), `news_review`, `news_scenario`, `news_export`, `news_acquire`, `news_project` | ✅ | **Embedded, not reimplemented** — declared against the same `console_component/` directory, fed the same `project_run` payload, and driven through the same `dispatch` / `_news_action`. A test reads the operation list out of `bridge.js` so a new button there cannot be forgotten here |
| **Health** — installation health, daily schedule registration, every check, news acquisition owner + worker + per-source outcomes, market jobs steps, configured stores | ✅ | Merges Classic's HEALTH, NEWS ACQUISITION and MARKET JOBS panels |

## 5. Deliberate differences (no remaining gaps)

| Item | Status | Why |
|---|---|---|
| The news layer on the Risk console is **opt-in** | ◑ by design | Measured: the F2 branch takes ~50 s to build on this store (2,100+ eligible events) against 0.2 s without it, because the aggregates describe every eligible event by design. Off, the console opens immediately and the news surfaces read NOT CONNECTED — which is true *of that view*, and the screen says so rather than implying the channel is unavailable. On, everything works |
| The console keeps its own visual language inside its frame | ◑ by design | It **is** the original renderer, embedded rather than restyled. Stated on screen |
| Evaluation has no commit and no run control | ◑ by design | D5(d)/DR-05 step 5: committing a pre-registered design is a person's act, so a button would make it a side effect of opening a page. The command is printed. Tested |
| Forecast screen never fits | ◑ by design | Reads the saved state. A render that refit 73 models would make every refresh a cliff. Tested |
| Live revision polling | ✅ | A Streamlit **fragment** with `run_every=LIVE_POLL_SECONDS`, so it reruns only the live panel. Classic *declares* `LIVE_POLL_SECONDS = 2.0` and never uses it — there was no behaviour to copy, so this implements the intent. A fragment is what makes polling safe: Classic's own note says rebuilding the page on a revision move would silently rebase a half-typed form, which is why it recorded the move instead of acting on it. With nothing committed the dial stays unfilled and the panel says the runtime has committed nothing — a polled absence is still an absence |
| Sector analysis basis toggle | ✅ | Exposed on the Overview and the Risk console with Classic's wording verbatim; decision-time remains the default. The retrospective option carries `analysis_mode: retrospective_archive` and the engine's own note that it "does not change the historical score or prove advance warning", and a test asserts its cutoff is **later** than the decision, never backdated onto it. The basis is part of the cached decision's scope, so a payload built on one basis can never be served for the other |
| Redesigned launcher starts no market jobs / live runtime / news supervisor by default | ◑ by design | Only the news worker has a cross-process lock. Classic owns the rest; `-WithMarketJobs` / `-WithLiveRuntime` opt in when running the redesign alone |
| Charts are Altair + inline SVG rather than `st.line_chart` | ◑ by design | Exact control of colour, gaps, two-axis resolution and tabular numerals. No new dependency |

## 6. A Classic defect this work found — now fixed

`build_news_payload()` returns `surfaces` (`signals`, `sector_stress`,
`geography`, `assets`) and has never returned a `channel` key. Classic's
`news_only_panel()` reads `payload.get('channel')`, so it reports
**"Events visible now: 0" and "Sources reporting: 0" however full the store
is.** Measured against the live store at the time of writing: 2,032 eligible
events, 21 registered feeds.

That panel is only reachable when no archive store exists, which is why it
had gone unnoticed.

**RESOLVED.** The session that owns `prototype_app.py` has fixed
`news_only_panel`: it now reads `payload['surfaces']['signals']['items']`,
the count from `pagination['total']`, sources from
`source_coverage['covered']`, and freshness from `stale` /
`newest_first_seen_at` / `worker_state`. The row shape was wrong too — items
carry `headline` not `title`, and `sources` (a list) not `source_id`. The fix
is pinned from Classic's side by
`test_the_payload_has_no_channel_key_and_counts_live_on_surfaces` in
`tests/test_news06_overlays.py`, and from the redesign's side by
`test_news_adapter_reads_surfaces_not_a_channel_key`. Both pin the same
contract from both ends.

`prototype_app.py` therefore no longer matches the 2026-10-24 baseline copy.
That is an intended fix by its owner, not drift: the baseline remains the
record of what Classic looked like before this work, and the other 36 copied
files are still byte-identical.

## 7. How this was verified

- **Full suite: 2,684 passed, 5 skipped, 0 failed** (26m44s), with a fresh
  disposable test database. 2,689 collected. This is the single
  AUTHORITATIVE run, performed after both sessions stopped editing, by the
  session that owns the backend; the earlier 2668/5/0 figure here was from a
  run exposed to two hazards described below and is superseded.
  The 5 skips are external-data only: 4 need `scripts/backfill_intraday.py`,
  1 needs `SERAPH_LIVE_NSE=1`.
- Of the 2,689 collected, `tests/test_redesign_overview.py` contributes 61 and
  the backend session's four touched test files contribute 7 between them.
  That accounts for all but about one test against the 2,626 measured before
  this work; the remainder was not chased, and no exact reconciliation is
  claimed here.
- **Two hazards invalidated earlier runs, and both are worth knowing.**
  (a) Editing a module while a suite runs: pytest holds the pre-edit module
  while Streamlit's `AppTest` re-executes the post-edit app from disk, which
  produced five bogus `ImportError`s in `tests/test_u01_console_startup.py`
  (23 passed in a clean process). (b) A news worker writing to the live store
  that several tests read by its real path -- `pagination.total` was observed
  moving 2032 -> 2087 -> 2137 mid-session. The authoritative run above had
  neither: no process was acquiring, and no file changed while it ran.
- A test database that has been used is no longer disposable: the provisioning
  guard correctly refuses both `seraph_test_local` and `seraph_test_redesign`
  once `validation_results` holds rows. The authoritative run used a freshly
  created `seraph_test_auth`.
- `scripts/check_invariants.py` — 7 checks ok, 0 failures.
- All 37 copied Classic baseline files re-hash byte-identical.
- `tests/test_redesign_overview.py` — 47 tests. Isolation (no Classic module
  imports the redesign; scoped stylesheet; distinct ports; no duplicate
  workers), every honesty rule, RBAC containment, strict-replay leakage, and
  the new screens.
- Structural assertions run against the **parsed AST**, not raw text, so a
  module's prose about what it deliberately does not touch cannot satisfy or
  break a test about what its code touches.
- End-to-end against the real backend: a portfolio created through the UI
  persisted to `prototype_runs/workspace.sqlite`; a regulator case opened
  through the UI returned `triage · v1`; the news screen rendered live
  acquired events; evaluation was refused for retail and served for
  institutional.
- Classic re-rendered on 8512 while the redesign ran on 8520 and matched its
  baseline screenshot; all Classic frontend files re-hash byte-identical.
- Evidence: `docs/evidence/redesign-complete-2026-10-25/` (12 screenshots),
  `docs/evidence/redesign-overview-2026-10-24/`,
  `docs/evidence/frontend-baseline-2026-10-24/`.
