# SERAPH fixed feature checklist and engineering finish line

Audit date: 19 October 2026. Checkout: `C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya`. Inspected HEAD: `092258f`, branch `seraph/engineering-completion`, plus the existing uncommitted news work. This is a feature audit, not an instruction to implement or push.

## The answer

**75% feature-implementation progress on the explicit 42-feature scope below.** There are **24 implemented and integrated, 0 assigned to implemented-with-known-defect, 15 partial and 3 absent**. Therefore **18 named features still need completion** to deliver the whole listed scope. The 24 completed units are about 57% of the units; partial credit produces the 75% progress figure. Neither figure measures hours remaining, scientific accuracy, commercial readiness or the chance a demonstration succeeds.

The formula is `(24 × 1 + 15 × 0.5 + 3 × 0) / 42 = 75%`. Equal feature weights and half-credit for partial work are declared planning conventions, not objective effort estimates. The important output is the finite checklist. Current-score integration can take more work than several finished views combined. This score must not be described as “only 25% effort remains.”

The original rough 75% estimate is now replaced by this explicit, inspectable denominator. Do not change the denominator to make the score improve; add/remove an intended feature only through an explicit scope decision.

## Scope and what counts as done

This freezes the major feature families in the original C1–C12 requirements and Astra/product/news amendments: the three original pillars, historical and current risk/forecast journeys, the original frontend, meaningful role workflows, and the supported news pipeline. It is not a line-by-line count of every FR/NFR and not a new enterprise product specification.

- **Implemented and integrated:** the feature has a connected supported route to its consumer/UI. Code tracing and existing evidence are distinguished in each row; it does not mean every path was freshly browser-tested.
- **Implemented with a known defect:** the main supported journey works but a known non-blocking defect remains. It earns full feature-existence credit under the user's criterion; record the limitation rather than chasing perfection. No row is currently assigned here—this does not mean the repository has zero bugs.
- **Partially implemented:** a meaningful input, producer, persistence, interaction or consumer is still missing; a helper function/button alone is insufficient.
- **Absent:** no functioning producer/user journey for the intended capability, even if a schema or preview slot exists.

A working raw-JSON comparison counts as a feature. Nicer comparison cards are optional. A nominal Export button that only displays partial JSON does not complete the intended downloadable analysis. A negative scientific result does not make a working estimator absent. An absent live producer does.

Excluded from this denominator and from the immediate todo: a target AUC/lead time or calibrated accuracy win; successful news interpretation benchmark; arbitrary source/edge quotas; universal document/OCR/multilingual comprehension; multi-user commercial deployment/OIDC/TLS; high-availability infrastructure; general historical event-sourcing; cosmetic refactoring; additional test-count targets. Existing weather/commodity/ticker/online-desk preview layers may stay clearly tagged as the user previously permitted. They are not credited as real live features.

No offline mode is required. Recorded real inputs can be used for bounded engineering verification, but must remain explicitly labelled replay rather than a live connection.

## Evidence and current-state corrections

This pass inspected current files/callers, recent commits, the latest saved browser/rehearsal evidence, and selected SQLite tables using read-only connections. It did **not** run test suites, refits, fetch jobs, a new browser session or migrations. No application code or production database was modified. The artifact/source manifest alongside this checklist records the snapshot used; another session was finishing news work during inspection.

- Recent runtime, portfolio-validation, scenario-versioning and wheel-packaging repairs are present. Old defect reports are not a current todo. The latest engineering report records 2,078 passed / 14 skipped; that is prior-run evidence, not a suite run performed here and not proof of complete features.
- Canonical archive store: 2 complete runs, 162 points. Final read-only news snapshot: 19 sources, 1,459 story rows, 26 document-cache rows and 0 production review rows. Acquisition continued during this audit (the earlier read had 938 stories/17 documents). A separate rehearsal copy recorded 938→1,186 stories; its review writes do not belong to the production store. Document-depth evidence can describe a different inspected corpus—do not add these counts together. See [captured source hashes and census](evidence/feature-completion-audit-2026-10-19/snapshot.json).
- The default `prototype_runs/live.sqlite` was absent. More decisively, current `scripts/run_live.py:87` still attaches `NullProducers()`. This establishes missing live producer integration regardless of any alternate store configuration.
- Saved news startup rehearsal reports automatic acquisition, two passes, manual outcomes, one failed source while 18 healthy sources remained covered, and zero owned processes after shutdown. Those earlier blockers are closed.
- Latest news workflow browser result (12:34 on 19 October) supersedes the earlier failing result: scenario/export request round trips are DONE, and one regulator review is stored in the isolated browser store. It does **not** establish a priced scenario, downloaded export file, or that every comparison control was clicked.
- The news completion amendment calls export done. Current bridge sends `news_export` with empty arguments; handler reads absent scenario/matrix data; result renderer displays JSON with no download path. The export serializer exists, but the complete user-facing export remains partial.

Relevant evidence: [engineering implementation report](SERAPH-IMPLEMENTATION-REPORT-2026-10-19.md), [news amendment](AMENDMENT-07-news-completion.md), [installed wheel](evidence/PACKAGING-2026-10-19.json), [news rehearsal](evidence/news-intelligence/news-completion-2026-10-19/rehearsal/rehearsal.json), [latest workflow browser](evidence/news-intelligence/news-completion-2026-10-19/browser-workflows/result.json), [scenario evidence](evidence/news-intelligence/news-completion-2026-10-19/scenario-on-real-data.json).

## Fixed feature register

The checkboxes are feature completion, not every possible test passing. CSV and JSON versions carry the same 42 IDs and statuses.

### Core

| Done | ID | Feature | Status | Remaining work / boundary | Completion task |
|---|---|---|---|---|---|
| [ ] | C01 | Refresh source history, universe and model inputs | Partially implemented | Connect a usable authorised source/history and a repeatable incremental data-to-features path; current fresh endpoint is diagnostic only. | T02 |
| [x] | C02 | Hawkes pillar calculation and inspectable diagnostics | Implemented and integrated | No new feature work for this unit; live scheduling and sector/network outputs are separate rows. | — |
| [x] | C03 | RMT pillar calculation and inspectable diagnostics | Implemented and integrated | Prediction quality is separate; no need to retune to complete this unit. | — |
| [x] | C04 | Hamilton pillar calculation and inspectable regimes | Implemented and integrated | An excluded or scientifically inadequate estimate is not an absent implementation; preserve its exclusion. | — |
| [x] | C05 | Reconciliation, composite score, uncertainty and attribution | Implemented and integrated | No requirement to prove predictive skill or recalibrate thresholds for engineering credit. | — |
| [x] | C06 | Historical end-to-end replay and durable results | Implemented and integrated | No expensive rerun needed; saved archive is not fresh live execution. | — |
| [x] | C07 | Market tick/bar runtime with restart recovery | Implemented and integrated | Actual publisher/broker access and live producer connection remain separate requirements. | — |
| [ ] | C08 | Fresh market inputs through real pillars to current dashboard risk | Partially implemented | run_live.build still attaches NullProducers; no actual scheduled producer-to-current-score journey. Default live.sqlite absent at inspection. | T03 |
| [x] | C09 | Historical future-loss forecasts and baseline comparison | Implemented and integrated | Forecast quality may be poor without making this feature absent. | — |
| [ ] | C10 | Ongoing forecast generation and prospective record | Partially implemented | Incremental forecast publication and an immutable dated prospective record are not integrated into normal operation. | T04 |
| [x] | C11 | Inspect existing evaluation and retrospective reports | Implemented and integrated | This credit does not imply original-spec full ablations/cross-market completion or positive performance. | — |
| [ ] | C12 | Complete original evaluation experiment runner | Partially implemented | A complete original-design Tables A/B, sensitivity and fixed-weight cross-market execution/report journey is not demonstrated. Existing Astra reports are not substitutes. | T10 |
| [ ] | C13 | Measured Hawkes sector micro-flags | Partially implemented | Fresh/source producer does not supply sector histories/baselines; archive coverage explicitly says unavailable. | T06 |
| [ ] | C14 | Measured directed market contagion network | Absent | No connected network-estimation producer; Hawkes branching_matrix is empty. News exposure arcs are a different feature. | T13 |
| [ ] | C15 | Ordinary project launch orchestrates market refresh as well as news | Partially implemented | No integrated startup/schedule for the supported market, daily-input and forecast jobs. Starting the console does not start all computation. | T03 |

### Product

| Done | ID | Feature | Status | Remaining work / boundary | Completion task |
|---|---|---|---|---|---|
| [x] | U01 | Original console, 3D globe shell and three role views | Implemented and integrated | Local role selection is deliberately not production authentication. | — |
| [x] | U02 | Historical run/date risk dashboard | Implemented and integrated | Do not describe the archived console as a current market reading. | — |
| [ ] | U03 | Official Nifty 500 benchmark overlay | Absent | No dated official benchmark input/payload/chart overlay is connected. | T07 |
| [x] | U04 | Enter holdings and calculate portfolio value/coverage | Implemented and integrated | Persistence and measured-sector linkage are separate units. | — |
| [ ] | U05 | Persistent portfolios, upload preview, history and watchlists | Partially implemented | Canonical UI still uses pasted JSON/session state rather than the existing persistent workspace. | T05 |
| [ ] | U06 | Measured portfolio sector-risk overlay | Partially implemented | Canonical dispatch passes empty sector flags; news relevance does not satisfy measured pillar-risk linkage. | T06 |
| [ ] | U07 | Market-level FII/DII and residual flow display | Partially implemented | Frontend still displays fabricated flow example values. | T06 |
| [x] | U08 | Single-pillar shock sensitivity tool | Implemented and integrated | No need to turn a rank shock into an economic forecast. | — |
| [ ] | U09 | Save, compare, review and export market scenarios | Partially implemented | Canonical scenario tool remains transient; no ScenarioStore UI caller. | T08 |
| [ ] | U10 | Macro/policy covariate-path simulation | Partially implemented | UI accepts xi_path only, not a macro z path tied to a fitted artifact. | T11 |
| [ ] | U11 | Retrospective defensive-action drawdown comparison | Partially implemented | Measured strategy comparison absent; drawdownReductionPct remains None. Requires declared positions, execution/cost assumptions and data. | T12 |
| [x] | U12 | Durable regulator alert-action journal | Implemented and integrated | Case management is a separate feature; no real trading/circuit-breaker execution is implied. | — |
| [ ] | U13 | Regulator case lifecycle and evidence export | Partially implemented | No dashboard caller for CaseStore. | T09 |
| [ ] | U14 | Institution-level exposure decomposition | Absent | No real submission/import-to-decomposition journey. Market/news data do not establish private institution positions. | T13 |
| [x] | U15 | Installable canonical frontend and runtime resources | Implemented and integrated | Do not redo closed packaging repair; later changes need proportionate verification. | — |

### News

| Done | ID | Feature | Status | Remaining work / boundary | Completion task |
|---|---|---|---|---|---|
| [x] | N01 | Automatic news startup and owned shutdown | Implemented and integrated | Do not reimplement this closed item. Bare Streamlit starts on first page execution; canonical launcher starts before page attachment. | — |
| [x] | N02 | Polling, manual refresh, freshness and source failure isolation | Implemented and integrated | No production uptime campaign required. | — |
| [x] | N03 | Real multi-source aggregation | Implemented and integrated | Specific blocked/unsupported publishers remain coverage limits, not an absent aggregation feature. | — |
| [x] | N04 | Substantive document extraction and structured interpretation | Implemented and integrated | Universal OCR, table reasoning, Hindi comprehension and validated accuracy are not claimed. | — |
| [x] | N05 | Qualitative sector/exposure impact inference | Implemented and integrated | Financial magnitudes and comprehensive exposure coverage remain unknown; not a reason to rebuild working qualitative inference. | — |
| [x] | N06 | News markers, documented globe paths and clickable evidence | Implemented and integrated | No fabricated extra arc to fill empty geography. | — |
| [x] | N07 | Retail holdings news relevance | Implemented and integrated | Durable holdings workspace is U05, not an unfinished news-matching function. | — |
| [x] | N08 | Institutional product-country exposure matrix | Implemented and integrated | Do not inflate coverage by counting product aliases as independent exposures. | — |
| [x] | N09 | Cited instrument comparison | Implemented and integrated | Presentation is raw JSON rather than polished side-by-side cards. Count as implemented under the user's functional-demo criterion; formatting is OPTIONAL. | — |
| [ ] | N10 | Usable conditional numerical tariff scenario | Partially implemented | No usable priced example: saved analysis has 22 routes and zero priced scenarios; missing supported rate/applicability evidence. | T01 |
| [x] | N11 | Persisted regulator instrument-link review | Implemented and integrated | Older failing browser result has been superseded. Do not reopen that repaired exception. | — |
| [ ] | N12 | Download complete displayed news analysis/scenario | Partially implemented | Export control sends empty arguments, lacks displayed scenario/matrix binding and only renders JSON; actual download not connected. | T01 |

## Per-feature evidence and finite acceptance

### C01 — Refresh source history, universe and model inputs

**Partially implemented.** Readers, bhavcopy parser, universe construction and feature scripts exist.

**Acceptance / demonstration:** A supplied real data interval produces dated, aligned model inputs; re-running does not duplicate records.

**Code/evidence:** [seraph/ingestion/bhavcopy_reader.py:173](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/ingestion/bhavcopy_reader.py:173>) · [scripts/build_observations.py:102](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/build_observations.py:102>) · [seraph/orchestration/original_execution.py:32](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/original_execution.py:32>)

### C02 — Hawkes pillar calculation and inspectable diagnostics

**Implemented and integrated.** Original count/kernel estimators, fitted artifacts and archive diagnostics are connected.

**Acceptance / demonstration:** Inspect a real archived Hawkes result and its model/input provenance.

**Code/evidence:** [seraph/pillars/hawkes/engine.py:440](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/hawkes/engine.py:440>) · [seraph/pillars/hawkes/artefact.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/hawkes/artefact.py>) · [seraph/orchestration/prototype.py:188](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/prototype.py:188>)

### C03 — RMT pillar calculation and inspectable diagnostics

**Implemented and integrated.** Spectral estimator and state adapter execute; archived spectral outputs reach the console.

**Acceptance / demonstration:** Inspect real spectrum/state diagnostics on a dated result.

**Code/evidence:** [seraph/pillars/rmt/engine.py:150](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/rmt/engine.py:150>) · [seraph/pillars/rmt/engine.py:366](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/rmt/engine.py:366>) · [seraph/orchestration/original_execution.py:65](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/original_execution.py:65>)

### C04 — Hamilton pillar calculation and inspectable regimes

**Implemented and integrated.** Original TVTP model, causal research route and Astra variant exist; diagnostics are displayed with eligibility caveats.

**Acceptance / demonstration:** Show an actual fitted/archived regime result and the stated eligibility limitation.

**Code/evidence:** [seraph/pillars/hamilton/engine.py:384](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/hamilton/engine.py:384>) · [seraph/pillars/hamilton/engine.py:518](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/hamilton/engine.py:518>) · [seraph/prediction/pillars.py:161](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/prediction/pillars.py:161>)

### C05 — Reconciliation, composite score, uncertainty and attribution

**Implemented and integrated.** C8/C9 execute on archive inputs; masks, timestamps, score/variance and Shapley outputs are connected.

**Acceptance / demonstration:** Selected historical input produces persisted score, uncertainty and attribution with missingness visible.

**Code/evidence:** [seraph/orchestration/prototype.py:66](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/prototype.py:66>) · [seraph/reconciliation/kalman.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/reconciliation/kalman.py>) · [seraph/fusion/score.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/fusion/score.py>) · [seraph/fusion/shapley.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/fusion/shapley.py>)

### C06 — Historical end-to-end replay and durable results

**Implemented and integrated.** Archive replay saves sealed runs and reports; two complete canonical runs/162 points were read during this audit.

**Acceptance / demonstration:** Select/reopen the saved run and its dated results.

**Code/evidence:** [seraph/orchestration/prototype.py:230](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/prototype.py:230>) · [seraph/orchestration/run_store.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/run_store.py>) · [docs/evidence/FIX01-FIX02-REPLAY-2026-10-16.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/FIX01-FIX02-REPLAY-2026-10-16.json>)

### C07 — Market tick/bar runtime with restart recovery

**Implemented and integrated.** Feed/bar/session/runtime components exist; recent integrity fixes and recorded crash recovery cover three crash points.

**Acceptance / demonstration:** Recorded real runtime-path recovery evidence preserves bars/decision identity across restart.

**Code/evidence:** [scripts/run_live.py:91](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_live.py:91>) · [scripts/run_live.py:175](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_live.py:175>) · [seraph/live/bars.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/live/bars.py>) · [docs/SERAPH-IMPLEMENTATION-REPORT-2026-10-19.md](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/SERAPH-IMPLEMENTATION-REPORT-2026-10-19.md>)

### C08 — Fresh market inputs through real pillars to current dashboard risk

**Partially implemented.** Runtime, inference service, publication gating and current-result reader exist.

**Acceptance / demonstration:** Through the real producer interfaces, fresh authorised inputs create a persisted current decision and update the full intended risk view; recorded historical verification must be labelled replay.

**Code/evidence:** [scripts/run_live.py:80](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_live.py:80>) · [scripts/run_live.py:87](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_live.py:87>) · [seraph/live/engine_adapter.py:83](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/live/engine_adapter.py:83>) · [seraph/dashboard/prototype_app.py:114](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/prototype_app.py:114>)

### C09 — Historical future-loss forecasts and baseline comparison

**Implemented and integrated.** Walk-forward predictive models, saved probabilities, event/false-alarm metrics and research viewer are implemented.

**Acceptance / demonstration:** Inspect actual out-of-sample saved forecasts and baseline results with negative findings retained.

**Code/evidence:** [seraph/prediction/models.py:219](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/prediction/models.py:219>) · [scripts/run_prediction_experiment.py:108](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_prediction_experiment.py:108>) · [seraph/prediction/app.py:303](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/prediction/app.py:303>) · [research_results/v1_verified/REPORT.md](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/research_results/v1_verified/REPORT.md>)

### C10 — Ongoing forecast generation and prospective record

**Partially implemented.** Batch historical forecasting and display exist.

**Acceptance / demonstration:** One newly available input date creates an identified forecast record and visible result; retry does not duplicate it or use unmatured outcome labels.

**Code/evidence:** [seraph/prediction/app.py:323](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/prediction/app.py:323>) · [scripts/run_prediction_experiment.py:108](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_prediction_experiment.py:108>) · [seraph/prediction/models.py:219](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/prediction/models.py:219>)

### C11 — Inspect existing evaluation and retrospective reports

**Implemented and integrated.** Saved research reports, backtest view, baseline comparison and hazard-watch evidence are accessible.

**Acceptance / demonstration:** Open actual report, see method/input scope, scores and limitations.

**Code/evidence:** [seraph/dashboard/console_backend.py:219](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:219>) · [seraph/prediction/app.py:244](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/prediction/app.py:244>) · [research_results/v1_verified/REPORT.md](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/research_results/v1_verified/REPORT.md>) · [research_results/v1_verified/HAZARD-REPORT.md](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/research_results/v1_verified/HAZARD-REPORT.md>)

### C12 — Complete original evaluation experiment runner

**Partially implemented.** Metric/calibration functions, subset scoring and preregistered configuration lists exist.

**Acceptance / demonstration:** One command exposes the fixed configurations, runs eligible supplied inputs and saves labelled results/unavailable reasons. Outcome quality is not a pass condition; expensive full scientific evaluation can be deferred.

**Code/evidence:** [seraph/validation/__init__.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/validation/__init__.py>) · [seraph/validation/ablation.py:34](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/validation/ablation.py:34>) · [seraph/validation/preregistration.py:53](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/validation/preregistration.py:53>) · [seraph/validation/harness.py:121](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/validation/harness.py:121>)

### C13 — Measured Hawkes sector micro-flags

**Partially implemented.** sector_flags helper and transport types exist.

**Acceptance / demonstration:** A supported measured/replayed sector input yields a dated micro-flag that reaches the UI and portfolio overlay.

**Code/evidence:** [seraph/pillars/hawkes/engine.py:391](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/hawkes/engine.py:391>) · [seraph/orchestration/original_execution.py:90](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/original_execution.py:90>) · [seraph/orchestration/prototype.py:184](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/prototype.py:184>)

### C14 — Measured directed market contagion network

**Absent.** Network fields/readers/rendering contracts exist.

**Acceptance / demonstration:** Using an explicitly defined, approved estimator and sufficient input, display actual directed links with dates and provenance; do not infer institution balance sheets from prices.

**Code/evidence:** [seraph/pillars/hawkes/engine.py:417](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/hawkes/engine.py:417>) · [seraph/pillars/hawkes/engine.py:517](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/hawkes/engine.py:517>) · [seraph/dashboard/gateway.py:104](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/gateway.py:104>)

### C15 — Ordinary project launch orchestrates market refresh as well as news

**Partially implemented.** Frontend/news startup now works; standalone market and data scripts exist.

**Acceptance / demonstration:** One normal launcher starts required configured services, shows clear unavailable dependencies, updates data/decisions without a second terminal and stops owned services.

**Code/evidence:** [launch_prototype.ps1](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/launch_prototype.ps1>) · [scripts/run_live.py:232](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_live.py:232>) · [seraph/operations/jobs.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/operations/jobs.py>) · [docs/SERAPH-IMPLEMENTATION-REPORT-2026-10-19.md](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/SERAPH-IMPLEMENTATION-REPORT-2026-10-19.md>)

### U01 — Original console, 3D globe shell and three role views

**Implemented and integrated.** Original component and distinct server-projected roles are wired.

**Acceptance / demonstration:** Switch roles and show their permitted real fields without replacing the original frontend.

**Code/evidence:** [seraph/dashboard/prototype_app.py:33](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/prototype_app.py:33>) · [seraph/dashboard/gateway.py:34](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/gateway.py:34>) · [seraph/dashboard/console_component/bridge.js:30](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:30>)

### U02 — Historical run/date risk dashboard

**Implemented and integrated.** Real score, alert, explanation, uncertainty, pillar details and history are rendered.

**Acceptance / demonstration:** Change date/run and see coherent actual results.

**Code/evidence:** [seraph/dashboard/prototype_app.py:415](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/prototype_app.py:415>) · [seraph/dashboard/console_backend.py:219](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:219>) · [seraph/dashboard/console_component/bridge.js:133](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:133>)

### U03 — Official Nifty 500 benchmark overlay

**Absent.** Current historical chart carries CSRS only.

**Acceptance / demonstration:** Display actual benchmark returns and CSRS on aligned dates; name series/source and show genuine gaps.

**Code/evidence:** [seraph/dashboard/console_backend.py:232](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:232>) · [seraph/dashboard/console_component/bridge.js:132](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:132>) · [seraph/universe/constructor.py:341](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/universe/constructor.py:341>)

### U04 — Enter holdings and calculate portfolio value/coverage

**Implemented and integrated.** JSON holdings submission and coverage arithmetic work.

**Acceptance / demonstration:** Submit supplied holdings and view labelled value weights/unmapped coverage.

**Code/evidence:** [seraph/dashboard/console_backend.py:270](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:270>) · [seraph/dashboard/console_component/bridge.js:165](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:165>) · [seraph/decision_support/portfolio.py:184](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/portfolio.py:184>)

### U05 — Persistent portfolios, upload preview, history and watchlists

**Partially implemented.** WorkspaceStore implements imports, as-of holdings and watchlists; recent import integrity fixes are present.

**Acceptance / demonstration:** Upload CSV/JSON, preview errors, save/select/reopen holdings and a watchlist after restart under an explicit local demo identity.

**Code/evidence:** [seraph/decision_support/workspace.py:316](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/workspace.py:316>) · [seraph/decision_support/workspace.py:420](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/workspace.py:420>) · [seraph/decision_support/workspace.py:583](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/workspace.py:583>) · [seraph/dashboard/prototype_app.py:532](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/prototype_app.py:532>)

### U06 — Measured portfolio sector-risk overlay

**Partially implemented.** Coverage-aware overlay calculation is implemented.

**Acceptance / demonstration:** A real dated sector flag changes the relevant holding's flagged share; unknown positions remain unknown.

**Code/evidence:** [seraph/dashboard/console_backend.py:275](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:275>) · [seraph/decision_support/portfolio.py:295](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/portfolio.py:295>)

### U07 — Market-level FII/DII and residual flow display

**Partially implemented.** Flow client/parser and diagnostic function exist.

**Acceptance / demonstration:** Show one real dated flow record and proxy definition; no claim of identifying retail counterparties.

**Code/evidence:** [seraph/ingestion/flow_client.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/ingestion/flow_client.py>) · [seraph/decision_support/artefacts.py:92](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/artefacts.py:92>) · [seraph/dashboard/console_component/bridge.js:153](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:153>)

### U08 — Single-pillar shock sensitivity tool

**Implemented and integrated.** Form invokes the actual simulator/C9 and shows a hypothetical score path.

**Acceptance / demonstration:** Enter baseline/changed shock and view the response with the hypothetical label.

**Code/evidence:** [seraph/dashboard/console_backend.py:288](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:288>) · [seraph/decision_support/artefacts.py:126](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/artefacts.py:126>) · [seraph/dashboard/console_component/bridge.js:165](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:165>)

### U09 — Save, compare, review and export market scenarios

**Partially implemented.** ScenarioStore supports immutable assumptions, runs, comparison and reviews.

**Acceptance / demonstration:** Save a named shock scenario, run it, compare to baseline, review the exact revision, export and reopen after restart.

**Code/evidence:** [seraph/decision_support/scenarios.py:186](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/scenarios.py:186>) · [seraph/decision_support/scenarios.py:215](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/scenarios.py:215>) · [seraph/decision_support/scenarios.py:418](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/scenarios.py:418>) · [seraph/dashboard/console_backend.py:288](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:288>)

### U10 — Macro/policy covariate-path simulation

**Partially implemented.** Direct regime-path simulator works; fitted z-to-xi projector exists.

**Acceptance / demonstration:** Use an available permitted fitted artifact and declared covariates to compare baseline/scenario; do not invent coefficients or require a desired risk direction.

**Code/evidence:** [seraph/dashboard/console_backend.py:299](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:299>) · [seraph/decision_support/artefacts.py:160](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/artefacts.py:160>) · [seraph/pillars/hamilton/engine.py:675](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/pillars/hamilton/engine.py:675>)

### U11 — Retrospective defensive-action drawdown comparison

**Partially implemented.** Dominant-pillar advice card exists.

**Acceptance / demonstration:** Calculate and display a bounded historical baseline/action comparison under explicit assumptions; improvement is not mandatory.

**Code/evidence:** [seraph/decision_support/artefacts.py:203](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/artefacts.py:203>) · [scripts/replay_operational_value.py:48](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/replay_operational_value.py:48>)

### U12 — Durable regulator alert-action journal

**Implemented and integrated.** Create/update/retract actions persist against an alert and its decomposition.

**Acceptance / demonstration:** Create/reopen an annotation under the local demo identity.

**Code/evidence:** [seraph/dashboard/console_backend.py:276](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_backend.py:276>) · [seraph/orchestration/run_store.py:309](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/orchestration/run_store.py:309>) · [seraph/dashboard/console_component/bridge.js:154](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:154>)

### U13 — Regulator case lifecycle and evidence export

**Partially implemented.** CaseStore implements assignment, evidence, decisions, close/reopen and export.

**Acceptance / demonstration:** Create a case from an alert, attach evidence, record a decision, close/reopen and export; persist across restart.

**Code/evidence:** [seraph/decision_support/cases.py:164](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/cases.py:164>) · [seraph/decision_support/cases.py:361](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/cases.py:361>) · [seraph/decision_support/cases.py:410](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/decision_support/cases.py:410>)

### U14 — Institution-level exposure decomposition

**Absent.** Role field/preview slot exists; institutionDecomposition is None.

**Acceptance / demonstration:** Accept authorised user-supplied exposures through a documented schema and show their evidenced aggregation; synthetic examples must remain labelled scenarios.

**Code/evidence:** [seraph/dashboard/gateway.py:104](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/gateway.py:104>) · [seraph/dashboard/console_component/bridge.js:154](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:154>)

### U15 — Installable canonical frontend and runtime resources

**Implemented and integrated.** Actual installed-wheel check passes: component assets, curated registries, migrations and schema load outside checkout.

**Acceptance / demonstration:** Use the existing installed-wheel evidence; preserve the working package declarations.

**Code/evidence:** [pyproject.toml](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/pyproject.toml>) · [docs/evidence/PACKAGING-2026-10-19.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/PACKAGING-2026-10-19.json>)

### N01 — Automatic news startup and owned shutdown

**Implemented and integrated.** Canonical launcher and app start one supervised worker; no separate news command.

**Acceptance / demonstration:** Saved rehearsal starts services through normal app and records zero owned news processes after shutdown.

**Code/evidence:** [seraph/dashboard/news_service.py:69](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/news_service.py:69>) · [seraph/dashboard/prototype_app.py:389](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/prototype_app.py:389>) · [launch_prototype.ps1](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/launch_prototype.ps1>) · [docs/evidence/news-intelligence/news-completion-2026-10-19/rehearsal/rehearsal.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/news-intelligence/news-completion-2026-10-19/rehearsal/rehearsal.json>)

### N02 — Polling, manual refresh, freshness and source failure isolation

**Implemented and integrated.** Worker uses degraded source state while healthy feeds continue; manual acquisition is serviced.

**Acceptance / demonstration:** Saved rehearsal covers two passes, manual fetch results and a failing source with 18 healthy sources remaining covered.

**Code/evidence:** [scripts/run_news.py:707](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_news.py:707>) · [scripts/news_supervisor.py:148](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/news_supervisor.py:148>) · [docs/evidence/news-intelligence/news-completion-2026-10-19/partial-failure-result.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/news-intelligence/news-completion-2026-10-19/partial-failure-result.json>)

### N03 — Real multi-source aggregation

**Implemented and integrated.** 19 registered sources in current store; feed/document adapters, registration and source health work.

**Acceptance / demonstration:** Show actual sourced articles and individual source status; fixed historical documents labelled as such.

**Code/evidence:** [scripts/run_news.py:307](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_news.py:307>) · [scripts/run_news.py:370](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/scripts/run_news.py:370>) · [docs/evidence/news-intelligence/news-completion-2026-10-19/new-source-acquisition.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/news-intelligence/news-completion-2026-10-19/new-source-acquisition.json>)

### N04 — Substantive document extraction and structured interpretation

**Implemented and integrated.** Permitted full document route, scopes, legal stages, quantities and evidence provenance implemented.

**Acceptance / demonstration:** Show extracted fields with their actual source text/scope and abstentions.

**Code/evidence:** [seraph/news/json_feed.py:71](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/json_feed.py:71>) · [seraph/news/enrichment.py:69](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/enrichment.py:69>) · [seraph/news/extraction.py](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/extraction.py>) · [docs/evidence/news-intelligence/news-completion-2026-10-19/document-depth.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/news-intelligence/news-completion-2026-10-19/document-depth.json>)

### N05 — Qualitative sector/exposure impact inference

**Implemented and integrated.** Documented routes produce direction/mechanism/confidence and unknown exposure.

**Acceptance / demonstration:** Inspect one domestic and one foreign-to-India route with citations and explicit qualitative labels.

**Code/evidence:** [seraph/news/estimation.py:264](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/estimation.py:264>) · [seraph/dashboard/news_view.py:534](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/news_view.py:534>)

### N06 — News markers, documented globe paths and clickable evidence

**Implemented and integrated.** Original globe has real news markers/paths; saved rehearsal shows 7 markers and 1 arc.

**Acceptance / demonstration:** Click through a real marker and its relationship evidence.

**Code/evidence:** [seraph/dashboard/news_view.py:581](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/news_view.py:581>) · [seraph/dashboard/news_view.py:629](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/news_view.py:629>) · [docs/evidence/news-intelligence/news-completion-2026-10-19/rehearsal/rehearsal.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/news-intelligence/news-completion-2026-10-19/rehearsal/rehearsal.json>)

### N07 — Retail holdings news relevance

**Implemented and integrated.** Matched holdings and unmapped holdings are separately shown; weights are not loss estimates.

**Acceptance / demonstration:** Existing browser evidence shows TATASTEEL relevance and explicit unmapped holding.

**Code/evidence:** [seraph/news/roles.py:73](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/roles.py:73>) · [docs/evidence/news-intelligence/academic-freeze-audit-2026-10-18/roles/result.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/news-intelligence/academic-freeze-audit-2026-10-18/roles/result.json>)

### N08 — Institutional product-country exposure matrix

**Implemented and integrated.** Documented pairs render as explicitly unsized cells.

**Acceptance / demonstration:** Matrix displays actual documented relationships and unknown sizes.

**Code/evidence:** [seraph/news/comparison.py:122](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/comparison.py:122>) · [seraph/news/roles.py:214](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/roles.py:214>) · [seraph/dashboard/console_component/bridge.js:274](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:274>)

### N09 — Cited instrument comparison

**Implemented and integrated.** Pair selection calls comparison, returns field differences and evidence to the visible result.

**Acceptance / demonstration:** Select a real comparable pair and inspect differences/evidence; direct code path is traced, latest browser only confirms control offered.

**Code/evidence:** [seraph/news/comparison.py:70](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/comparison.py:70>) · [seraph/dashboard/prototype_app.py:240](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/prototype_app.py:240>) · [seraph/dashboard/console_component/bridge.js:468](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:468>)

### N10 — Usable conditional numerical tariff scenario

**Partially implemented.** Input form, guarded formula and unavailable responses are connected; browser round trip succeeds.

**Acceptance / demonstration:** One real supported measure plus labelled user cost assumptions produces conditional arithmetic, or keep this explicitly input-blocked. Never assume missing old rate is zero.

**Code/evidence:** [seraph/news/workflows.py:115](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/workflows.py:115>) · [seraph/news/scenarios.py:55](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/scenarios.py:55>) · [docs/evidence/news-intelligence/news-completion-2026-10-19/scenario-on-real-data.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/news-intelligence/news-completion-2026-10-19/scenario-on-real-data.json>)

### N11 — Persisted regulator instrument-link review

**Implemented and integrated.** Latest browser result records DONE and one stored review with local demo attribution; current projection reads stored decisions.

**Acceptance / demonstration:** Latest artifact proves UI submission and stored record; reload/projection behavior also has a traced code path, not a claimed fresh browser run here.

**Code/evidence:** [seraph/news/workflows.py:59](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/workflows.py:59>) · [seraph/news/acquisition.py:606](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/acquisition.py:606>) · [seraph/dashboard/news_view.py:322](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/news_view.py:322>) · [docs/evidence/news-intelligence/news-completion-2026-10-19/browser-workflows/result.json](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/docs/evidence/news-intelligence/news-completion-2026-10-19/browser-workflows/result.json>)

### N12 — Download complete displayed news analysis/scenario

**Partially implemented.** Backend export serializer returns evidence and limitations; request round trip now succeeds.

**Acceptance / demonstration:** Download JSON or CSV that includes displayed inputs/result, matrix/comparison where selected, evidence, as-of and limitations; reopen file and compare to screen.

**Code/evidence:** [seraph/dashboard/console_component/bridge.js:486](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/console_component/bridge.js:486>) · [seraph/dashboard/prototype_app.py:248](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/dashboard/prototype_app.py:248>) · [seraph/news/workflows.py:157](<C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/seraph/news/workflows.py:157>)

## The actual implementation todo

These are feature-completion packages, not 76 unrelated defects. All 18 partial/absent feature IDs map to one of the 13 packages below. Completion fixes belong inside their package only if they prevent that journey. Do not repair every old audit finding as a prerequisite.

### Completion checkboxes

- [ ] **T01** — P1 • finish existing news slice; closes N10, N12.
- [ ] **T02** — P0 • unblock core; closes C01.
- [ ] **T03** — P0 • complete flagship journey; closes C08, C15.
- [ ] **T04** — P1 • current forecasting; closes C10.
- [ ] **T05** — P1 • meaningful role workflow; closes U05.
- [ ] **T06** — P1 • replace consequential placeholders; closes C13, U06, U07.
- [ ] **T07** — P1 • visible backtest feature; closes U03.
- [ ] **T08** — P1 • institutional workflow; closes U09.
- [ ] **T09** — P1 • regulator workflow; closes U13.
- [ ] **T10** — P2 • finish research software, not scientific acceptance; closes C12.
- [ ] **T11** — P2 • intended policy feature; closes U10.
- [ ] **T12** — P2 • intended retrospective action feature; closes U11.
- [ ] **T13** — P2 • intended graph/decomposition features; closes C14, U14.

### Recommended order

1. Finish **T01** in the existing news slice without reopening its successful startup/reliability checks. Do not let a missing real tariff example block other project work.
2. **T02 → T03** is the critical path: usable inputs → real producers → current results and ordinary project startup. This is the most consequential missing journey.
3. Once data is available, **T06, T07, T04** connect measured exposure/flows, benchmark backtest and ongoing forecasts.
4. **T05 → T08 → T09** complete the three durable role workflows. These can proceed before data access is resolved; they reuse existing backend stores and do not need an enterprise identity provider.
5. **T10–T13** complete the remaining original research/policy/playbook/graph capabilities. Their model/data contracts are explicit dependencies. They cannot be labelled complete merely because broad predictive science is postponed.
6. One final rehearsal covers the fixed journeys. Then freeze. No new redesign, source quota, test-coverage quota or general audit campaign.

If time is short, finish T02/T03 and the role workflows before polishing news. A strong demonstration can use already implemented features before all 42 are complete; that is different from claiming the entire intended project is feature-complete.

### [ ] T01 — P1 • finish existing news slice

**Closes:** N10, N12. **Readiness/dependencies:** Can start now; numerical example needs adequate source evidence.

**Build:** Keep startup/isolation/review fixes closed. Wire a real downloadable export to the displayed scenario, matrix and comparison. Find one permitted instrument that satisfies the existing tariff calculation contract, retaining explicit user assumptions. If evidence remains unavailable, finish export and record N10 as input-blocked.

**Likely files/interfaces:** seraph/dashboard/prototype_app.py; seraph/dashboard/console_component/bridge.js; seraph/news/workflows.py; seraph/news/scenarios.py

**Done when:** Download and reopen the actual displayed analysis; one supported numeric example or a precise evidence blocker. Do not rerun the unchanged acquisition rehearsal.

**Boundary:** Existing news session is editing these paths: reconcile its final state before writing.

### [ ] T02 — P0 • unblock core

**Closes:** C01. **Readiness/dependencies:** Can implement adapters/orchestration now; actual source/history access may need external configuration.

**Build:** Connect one authorised usable market-history source, point-in-time universe and incremental feature build. Reuse current ingestion/universe modules. Establish explicit input ranges and safe data-store ownership; do not attach, migrate or overwrite an old volume silently.

**Likely files/interfaces:** seraph/ingestion/; seraph/universe/; scripts/build_observations.py; seraph/orchestration/original_execution.py

**Done when:** A real bounded interval loads and builds inputs, with source dates/coverage visible; repeat does not duplicate data. No full model refit needed just to test the connector.

**Boundary:** No external access requirement is counted as solved by a passing unit test.

### [ ] T03 — P0 • complete flagship journey

**Closes:** C08, C15. **Readiness/dependencies:** Depends on T02 for real inputs; producer and launch wiring can start independently.

**Build:** Implement the real Producers adapter using existing model families/artifacts and histories; carry vintages into InferenceService and persisted decisions. Add the minimal supported market/daily-job lifecycle to ordinary startup. Connect current results to the intended console views, not only a separate diagnostic panel. Keep eligibility/withholding scientifically honest.

**Likely files/interfaces:** scripts/run_live.py; seraph/live/engine_adapter.py; seraph/live/inference.py; seraph/dashboard/current_reader.py; seraph/dashboard/prototype_app.py; launch_prototype.ps1

**Done when:** Normal launch needs no second news/market terminal; supported inputs flow through real producers to saved decision and visible score/provenance. Replayed captured data may test the path but must never be called live.

**Boundary:** This is the biggest remaining integration package; do not treat it as a small bug.

### [ ] T04 — P1 • current forecasting

**Closes:** C10. **Readiness/dependencies:** Depends on T02; can share T03 orchestration.

**Build:** Wrap existing forecasting with incremental input-date processing, artifact identity and an append-only prospective output store. Display the latest eligible forecast separately from CSRS and preserve older forecasts.

**Likely files/interfaces:** seraph/prediction/models.py; scripts/run_prediction_experiment.py; seraph/prediction/app.py; orchestration/store adapter

**Done when:** One new input date yields exactly one identified forecast/result revision; rerun is idempotent and no future labels enter inference.

**Boundary:** Do not optimise predictive score in this engineering task.

### [ ] T05 — P1 • meaningful role workflow

**Closes:** U05. **Readiness/dependencies:** Can start now; no market-feed or enterprise login dependency.

**Build:** Connect existing WorkspaceStore to a labelled local demo identity. Add upload/preview/save/select/reopen portfolio, dated holdings history and simple watchlist. Preserve current JSON entry as supported input if useful.

**Likely files/interfaces:** seraph/decision_support/workspace.py; seraph/dashboard/prototype_app.py; seraph/dashboard/console_backend.py; bridge.js

**Done when:** Upload supplied holdings, see errors, save and reopen after application restart; watchlist persists. Unknown valuations/mappings stay explicit.

**Boundary:** Reuse repaired P03 import logic; do not rewrite it or add OIDC.

### [ ] T06 — P1 • replace consequential placeholders

**Closes:** C13, U06, U07. **Readiness/dependencies:** Sector branch depends on T02/T03; flow branch can start with a real dated record.

**Build:** Supply measured sector inputs to the existing micro-flag helper, persist/provide dated flags and pass them into portfolio_overlay instead of {}. Wire an actual FII/DII/turnover observation through flow_diagnostic to the UI.

**Likely files/interfaces:** seraph/pillars/hawkes/engine.py; seraph/orchestration/original_execution.py; seraph/decision_support/portfolio.py; seraph/ingestion/flow_client.py; console_backend.py; bridge.js

**Done when:** A supported sector flag changes only relevant covered portfolio exposure; real flow values replace preview values and show date/source/proxy label.

**Boundary:** News-derived sector mechanisms must remain separate from pillar-measured flags.

### [ ] T07 — P1 • visible backtest feature

**Closes:** U03. **Readiness/dependencies:** Chart/payload work can start now; requires a real benchmark series.

**Build:** Import/version the official Nifty 500 benchmark, align dates and connect an actual benchmark-return versus CSRS view. Keep absent intervals explicit.

**Likely files/interfaces:** seraph/dashboard/console_backend.py; bridge.js; appropriate benchmark ingestion/store adapter

**Done when:** A cited date window shows both actual series with clear units/scales and no substituted index.

**Boundary:** No trading strategy, optimisation or giant backtest run required.

### [ ] T08 — P1 • institutional workflow

**Closes:** U09. **Readiness/dependencies:** Can start now using existing shock simulator/store.

**Build:** Connect ScenarioStore to UI save/run/list/compare/review/export, with immutable assumption/run identity and local actor. Preserve the existing temporary quick simulator.

**Likely files/interfaces:** seraph/decision_support/scenarios.py; console_backend.py; prototype_app.py; bridge.js

**Done when:** Create a named scenario, compare to baseline, review exact run, export and reopen it after restart.

**Boundary:** Reuse recently fixed assumption versioning; do not reopen P05.

### [ ] T09 — P1 • regulator workflow

**Closes:** U13. **Readiness/dependencies:** Can start now; independent of live-feed/real identity-provider access.

**Build:** Connect CaseStore to local case creation, alert/evidence attachment, decision, close/reopen and export. Keep the existing alert journal distinct and working.

**Likely files/interfaces:** seraph/decision_support/cases.py; console_backend.py; prototype_app.py; bridge.js

**Done when:** One case goes through creation to closure/reopen and evidence export, surviving restart.

**Boundary:** No enterprise organisation hierarchy required for the local demonstration.

### [ ] T10 — P2 • finish research software, not scientific acceptance

**Closes:** C12. **Readiness/dependencies:** Runner assembly can start now; complete real results depend on eligible data and preregistered configuration.

**Build:** Connect the existing metric/calibration/subset/configuration primitives into a bounded original-design experiment runner and report loader for Tables A/B, sensitivity and fixed-weight cross-market transfer. Preserve explicit unavailable rows and original designs.

**Likely files/interfaces:** seraph/validation/; seraph/store/migrations/; a focused experiment entry point/report adapter

**Done when:** A small supplied valid dataset exercises runner/configuration/report plumbing; full expensive scientific evaluation is separate. Real runs cannot silently change splits/labels or claim invented results.

**Boundary:** Do not repeat completed Astra reports as if they are the original full experiment.

### [ ] T11 — P2 • intended policy feature

**Closes:** U10. **Readiness/dependencies:** Engineering can start; needs a usable fitted artifact/covariate definition.

**Build:** Connect macro z-path inputs to the existing fitted project_xi path and baseline/scenario display, preserving model provenance. Keep existing direct-xi sensitivity available.

**Likely files/interfaces:** seraph/pillars/hamilton/engine.py:675; seraph/decision_support/artefacts.py; console_backend.py; bridge.js

**Done when:** An identified artifact accepts a valid macro path and returns reproducible scenario output; missing artifact is a clear input blocker.

**Boundary:** If artifact/model assumptions are unresolved, record that decision dependency; do not fabricate coefficients.

### [ ] T12 — P2 • intended retrospective action feature

**Closes:** U11. **Readiness/dependencies:** Needs explicit supported action/position/execution/cost assumptions plus prices.

**Build:** Implement a bounded baseline-versus-defensive-action historical comparison and connect the real result to the playbook. A generic advice label alone is not this feature.

**Likely files/interfaces:** seraph/decision_support/artefacts.py:203; scripts/replay_operational_value.py; report/payload adapter

**Done when:** One declared historical example reports realised drawdown comparison and assumptions, even when the action is worse.

**Boundary:** This requires a model/design contract, not prediction tuning. Do not invent a benefit or silently choose financially material assumptions.

### [ ] T13 — P2 • intended graph/decomposition features

**Closes:** C14, U14. **Readiness/dependencies:** Input schemas/UI can start; network estimator and real institution evidence are explicit dependencies.

**Build:** Keep two different features distinct: measured market contagion from an approved supported estimator, and institution exposure decomposition from authorised submitted positions/links. Add the needed producers/imports/payloads and honest graph views; reuse the original design.

**Likely files/interfaces:** seraph/pillars/hawkes/engine.py; seraph/dashboard/gateway.py; console_backend.py; bridge.js; a scoped institution exposure input adapter

**Done when:** Display a graph from actual supported model inputs and a separately sourced institution decomposition. Label hypothetical user submissions as scenarios; never derive private balance sheets from public price bars.

**Boundary:** If the mathematical/data contract is undefined, this is a named blocked feature—not a reason for unlimited generic auditing.

## Required final demonstration, not another development phase

- [ ] Start the normal project once; news and configured market services start with clear source/worker/result status. No separate news command.
- [ ] Show an actual current market input reaching real pillar adapters, a persisted decision and the intended current display. Outside market hours, show the last actual session result with its timestamp; a recorded-data run is labelled replay.
- [ ] Inspect the existing historical run, all three pillar diagnostics, score/explanation/uncertainty and actual benchmark overlay. Poor prediction remains visible.
- [ ] Upload/save/reopen a portfolio and show covered and unknown exposure; show dated market flows separately from news hypotheses.
- [ ] Run/save/compare/export an institutional scenario, and distinguish rank sensitivity, macro-policy assumptions and conditional news arithmetic.
- [ ] Show real news → interpretation → sector/holding → original globe/evidence; demonstrate review persistence and actual analysis download.
- [ ] Create an alert action and a case, attach evidence, close/reopen and export.
- [ ] Show the original evaluation runner/report and the named policy/playbook/network features once their declared data/model dependencies are satisfied; do not substitute fabricated panels.
- [ ] Restart once and reopen saved workspace/scenario/case state. Run only relevant bounded checks after changes; reuse unchanged passing evidence.

**Stop rule:** for the full intended feature claim, every fixed row must be integrated (or integrated with a documented non-demo-blocking defect), the chosen supported journeys must work, and no fabricated output may masquerade as real data. Do not demand scientific success or commercial hardening. If a data/model-dependent feature is deferred, leave its row partial/absent and name the reduced scope; do not silently shrink the denominator.

The principal work remaining is connecting existing capabilities into complete journeys. There are also genuine absent features (benchmark overlay, measured market network, institution decomposition) and model/data-dependent unfinished features. It would be misleading to describe all of the remainder as minor defect fixing.

