# SERAPH: overall engineering completion and finite closeout checklist

Date: 2026-10-24  
Inspected commit: `9a792b506aa7192f8c6c3f7119396b3a40e3d5ac` **plus the uncommitted implementation listed in the companion JSON**  
Branch: `seraph/engineering-completion`  
Workspace: `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`  
Assessment snapshot: October 24 native-session continuation; exact time in companion JSON.

**October21 reassessment (superseded below): approximately 96% overall engineering completion, up from 95%.** The scope remains the same 42 feature units and ten closeout packages, with unchanged responsibility weights. This includes the current uncommitted code. The original filename is retained so existing handoff links continue to work; this update is dated October 21.

## Latest native-session continuation — October 24

**Approximately 97%**, using the same weights and 42-unit scope: 40 implemented
and two partial. The native coverage blocker is resolved by verified exchange
session handling. A real native Hawkes fit now covers 500 sessions, 95 members
and 37,170 common continuous-session bins with zero unexplained gaps. All
4,150,272 raw closes remain intact. The fit's actual availability is October 24
at 18:02:45.081189 IST; it is not backdated to its October 22 training end.

Cold start admits **1 Hawkes and 253 RMT observations**. F02 still needs the
252-observation Hawkes history and actual in-session current publication. F07
remains pending by explicit user choice; no network fit was run. This progress
does not close another feature unit or establish predictive skill.

**49 focused checks passed**, along with mechanical invariants and whitespace
checks. The independent October 24 news full-suite run reported 2,585 passes,
25 skips and one database-dependent failure with Docker stopped. No fresh
universal suite pass is claimed here. See
[native-session evidence](NATIVE-SESSION-COVERAGE-2026-10-24.md) for sources,
provenance, precise results and remaining acceptance. Earlier assessments below
are preserved; this section supersedes their native-coverage conclusions.

## Earlier native-runtime continuation — October 22 evening

Overall remains **approximately 97%** on the same scope: 40 implemented units and
two partial. RMT warm-up completed with 252 observations and no failures; the
evening runtime admits 253 after the latest daily observation. Native Hawkes has
a durable closed-bar producer, explicit runtime/launcher configuration, an owned
worker and tested input admission. The worker now checks coverage before jump
extraction and reuses unchanged evaluations until eligible inputs change.

Refreshed broker access succeeds for both REST and the actual 95-symbol websocket.
The recent backfill completed with **3,906,400 bars**, no rejected bars and no
incomplete request windows; native history now holds **4,150,272 configured-member
bars**. The actual trailing 500-session check finds **182 incomplete intervals /
14,630 missing symbol-bars**. Eight of 95 members cover every observed interval.
The fit remains withheld; three direct source retries still omit sampled gaps.
The real preflight takes 15.28 seconds, not a measured numerical-fit latency.
Current publication is still unverified: the successful websocket probe ran
after market close and correctly published nothing.

F07 is explicitly **pending by the owner's October22 choice**; no fit was run.
See [native-runtime continuation](NATIVE-HAWKES-RUNTIME-2026-10-22.md) and its
dated evidence directory. This section supersedes the earlier 403, stale-history
and absent-native-producer findings below. F02 still requires supported native
coverage, actual Hawkes standardizer history and in-session publication acceptance.

**Final verification reconciliation:** `engineering-closeout-2026-10-22/full-suite-recheck.xml`
records **2,585 passed, 22 skipped, zero failures/errors** (1,250.376 seconds).
The earlier run's October20 scheduling assertion was corrected to respect the
verified exchange holiday; its failure is retained in `full-suite.xml`.
The 17 database-dependent skips subsequently passed against isolated disposable
PostgreSQL on port 5435 (`disposable-db.xml`); that container is stopped again.
Four retained old-corpus checks and one explicit live-NSE check remain skipped.
The latest worker coverage/cache changes pass **38 focused checks** in
`native-coverage-regression.xml`; invariant checks and `git diff --check` pass.
Earlier `native-runtime.xml` records 82 overlapping checks. Runs are not added
together, and synthetic checks do not establish real live publication.
A fresh canonical cold-start inspection (`engineering-closeout-2026-10-21/runtime-history-complete.json`)
loads252 usable RMT observations and admits all latest daily inputs without
producing a decision. It does not satisfy the configured native Hawkes history
or its separate standardizer requirement.

**Current audit-to-implementation result:** F01/F03/F04/F05/F06/F08/F09/F10 are
complete within their documented bounded actual-input/browser criteria. F01's
renderer repair was already committed in `9a792b5`; daily acquisition and initial
registration repairs from `f7be092`/`6db3e83` were reused. F02's native producer,
owned worker and history admission software now exist, but a usable current
native fit, its latency, and an actual current decision remain unverified because
common native coverage and Hawkes warm-up are incomplete. Broker access is now
working. F07's actual fit and graph
acceptance remain unfinished by the owner's explicit decision to keep it pending.
No remaining live-input failure is labelled as completed functionality.

**Demo status:** the bounded historical application is demonstrable through the
canonical frontend with saved browser evidence. The complete live application is
**not yet demo-ready**. Preserve the native-data requirements, explicit F07 hold,
Hamilton exclusion and scientific limitations. The full test pass does not close
these acceptance gates. No additional broad suite rerun is needed without a new
change or failure.

## Earlier implementation reconciliation — October 22 continuation

This section supersedes the older assessment snapshots below; their implementation plans and evidence remain retained. The same 42 units and ten packages apply. Current inventory is **40 implemented, two partial**, with approximately **97%** weighted engineering completion. The additional point closes bounded real-input evaluation integration, not measured predictive performance. SERAPH is **not yet fully complete or ready for an unrestricted live demonstration**.

Evidence paths below are relative to `docs/evidence/engineering-closeout-2026-10-21/` unless stated otherwise.

| Package | Verified implementation and evidence | Remaining work |
|---|---|---|
| F01 | Earlier commit `9a792b5` repaired history rendering. `console-browser-02/result.json` passes canonical console/backtest/benchmark/three-role/globe checks; historical flow unavailability is correct. | Closed; preserve existing real-payload flow tests. |
| F02 | Owned launcher passes (`launcher-01`). Actual broker connected pre-open (`runtime-probe-final/result.json`), superseding the old 403. Declared absence manifests now reach admission without backdating availability. Resumable `warm_runtime_history.py` computes real registered history. | Historical computation is running; inspect durable status. Current-score publication on a genuine closed market bar is unverified. A fresh native-intraday Hawkes producer is still not connected; Hamilton's standing exclusion is retained. |
| F03 | `forecast-ledger-final.json` verifies exact October21 state/ledger identity, probability, threshold and single issuance. Browser shows the ID. | Closed; future outcome is correctly unset until its 15 observed sessions mature. |
| F04 | Actual 243,872 native bars support bounded historical sector observations. `sector-browser-03/result.json` passes saved-book integration: INR1,000 of INR3,000 covered, remainder unassessed; switching back to historical knowledge removes late-produced flags. Fixed selection to honor both market-input date and availability cutoff. | Closed within bounded historical scope; partial basket coverage remains visible. |
| F05 | Earlier October20 `news-priced-browser` evidence verifies cited 25%→50% historical tariff accounting and pinned downloaded analysis. | Closed; no automatic live extraction or causal effect claim. |
| F06 | Authorized registered real report plus `evaluation-browser-03/result.json`: both reconciliation modes, tables A/B/C, provenance, 152 honestly unavailable cells. | Closed for bounded report integration. No scientific performance claim. |
| F07 | Actual native counts for five sectors now exist; estimator/artifact/renderer implemented. `network-input-readiness.json` and `NETWORK-DIAGNOSTIC-DESIGN.md` document support and proposed constants. | Awaiting explicit adoption of the prepared scientific specification before actual fitting. Then inspect fit/non-identifiability and browser graph/export. This is not blocked by missing bars anymore. |
| F08 | `macro-browser-03/result.json` passes actual RBI repo fit save/run/reopen/export. Maximum regime-probability change is about .9653; score changes remain zero under retained exclusions. Saved-scenario refusal now warns without crashing the workspace. | Closed with visible retrospective, fit-convergence and production-exclusion limits. |
| F09 | Earlier `browser-13` verifies persisted defensive execution, reopen/history and downloaded observed-index paths. | Closed; hypothetical actions are not prospective strategy evidence. |
| F10 | Earlier `institution-browser-01/result.json` verifies import/reopen/console/export and access isolation, INR3,000 total. | Closed; exposure shares are not loss contributions. |

**Verification:** `acceptance-regressions.xml` records 87 passed. `runtime-preparation-recovery.xml` records 84 passed and one intentionally skipped live-NSE check, after removing workspace-dependent calendar/snapshot test assumptions. The full-suite attempt crashed in native post-fit Hamilton covariance estimation; `full-suite-attempt.json` preserves that failure. Disabling unused parameter covariance calculation leaves fitting/filtering/emission variances intact; `ct7-projection-recovery.xml` then passed all eight contracts, including the previously crashing fit. A successful complete full-suite run has **not** been established. Counts overlap and must not be added.

**Demo readiness:** the canonical historical console, portfolios, sectors, scenarios, news export, evaluation and regulator workflows have saved browser evidence. Owned startup/shutdown is verified. Full live readiness remains open pending legitimate warm-up, an actual in-session bar/current decision and the unconnected live Hawkes producer. F07 remains a concrete model-decision dependency. P01 is still explicitly local demonstration identity; prior D04, U02/U03, V01/V03, X08 and Kite directives are unchanged. No required prediction or warning capability is reclassified to avoid implementation.

The [demo runbook](SERAPH-DEMO-RUNBOOK-2026-10-21.md) gives the canonical paths and retained limits. No existing work was reset, no unrelated edits were overwritten, and no commit or push was made by this continuation.

## Historical assessment snapshots

## Assessment

**Overall academic-project engineering completion: approximately 96%.**

This is the whole academic engineering deliverable, including integration and a defensible demonstration. It is not predictive accuracy, test coverage, a feature-count percentage, or an estimate of hours remaining.

All previously absent feature categories now have substantive implementation. The new directed-network code is no longer an empty schema field, defensive comparisons have an actual calculator and UI, and fitted covariate scenarios have a persisted model path. However, implementation alone does not establish usable real outputs: sector flags are unavailable, no measured network artifact is saved, and final policy/console browser acceptance remains. The remaining work is concentrated in those input/model integrations and bounded acceptance, rather than inventing more feature categories.

Scientific success remains separate. Preserve negative results, Hamilton's production exclusion and the three original pillars. A historical accounting example or hypothetical action comparison does not establish prospective prediction skill.

### Latest progress: 95% to 96%

**One additional dashboard/role implementation point is earned (19/20 to 20/20).** An actual RBI repo-rate fitted artifact now completes the missing named policy-input implementation, and saved defensive, institution and portfolio workflows have concrete browser evidence. Remaining macro/console acceptance stays within the existing delivery deduction; scientific effectiveness is not required for this implementation credit. Inventory: **38 implemented, four partial, zero absent**. U10 is implemented within explicit retrospective conditional-sensitivity scope; F08 browser acceptance remains open.

| Progress | Evidence and bounded conclusion |
|---|---|
| Actual policy fit | `policy-fit.json` and artifact `b9a7459...` record 278 actual observation pairs through July23, named `rbi_repo_rate`, retained source/receipt metadata and passed loaded-versus-fitted transition check. Latest-vintage retrospective data are not causal replay evidence. A local-optimum warning remains; Hamilton remains excluded from production scoring. |
| Defensive workflow completed | `browser-13/result.json` contains rendered result/history, `scenario_reopened=true`, and downloaded scenario with persisted execution and observed index paths. Its later regulator assertion failed, so the entire combined run is not called passed; the completed defensive journey is credited. |
| Institution workflow completed | `institution-browser-01/result.json` passes: saved submissions reopen, INR1000+INR2000 aggregates to INR3000, regulator console/export agree, restricted retail form absent. Holdings are explicitly demonstration inputs. |
| Portfolio workflow completed | `portfolio-browser-03/result.json` passes: INR3000 saved book reaches exposure overlay, two mapped holdings reach news analysis, and reopen/reactivation works. Missing measured sector coverage remains unassessed, not zero risk. |
| Fresh daily output | Saved acquisition/job/state now reach October21; corpus records7,491,722 daily rows. Two explicit deployments exist. This is end-of-day acquisition/forecast progress, not current intraday CSRS publication. |
| Remaining verification | Macro browser attempts01–02 fail before a completed fit scenario journey. Console-only attempt01 fails. Latest UI edits follow those results and have no later pass at inspection. Saved final-integration tests report137 passed but predate later UI changes. |

Live readiness remains incomplete: two RMT standardizer observations against252 required, no admitted Hawkes history, and only the old withheld replay decision. The last actual broker attempt was rejected403. Sector output remains unavailable; no real network artifact or completed registered real evaluation report was found. The fixed remaining work is F02/F04/F06/F07 integration plus F01/F08 browser acceptance. F09 and F10 are closed; do not keep re-running them without a relevant change.

This update used source/artifact inspection and read-only runtime queries, with no application edits, test reruns, model refits or pushes. Earlier chronological sections below preserve superseded snapshot findings; use this section and the current package table for present status.

### Historical check after the 12:16 IST snapshot

**Work demonstrably continued; overall engineering remains approximately 95%.** Eight files from the prior hash manifest changed, plus newly inspected feed changes and evidence. Git HEAD remains `9a792b5`; progress is uncommitted. These observations prove subsequent work, not which automation or session caused it.

- **Configured live feed:** runtime now loads configured credential inputs and attempts the actual broker websocket. Saved `broker-rejection.json` records HTTP 403, no received bars, degraded health and warm-start counts 0/1/0. This supersedes the older NullFeed diagnosis for the configured attempt. It does not establish successful live data or current publication; token validity versus market-data entitlement cannot be distinguished from that response.
- **Policy data:** BIS retrieval and `observed-policy-covariates.json` contain 287 observed RBI repo-rate rows. The adapter/export/projection path adds explicit retrospective latest-vintage handling, retaining actual receipt time and marking this unsuitable for causal replay. `F08-POLICY-DESIGN.md` defines the bounded diagnostic. No fitted repo-rate artifact exists yet; F08 remains partial.
- **Verification:** saved broker-health tests report 133 passed, zero failures; calendar/feed final tests report 105 passed. Do not sum overlapping runs. They precede the later macro edits and do not validate those edits. An earlier configured-feed run had three failures; retain that evidence alongside subsequent results.
- **Browser continuation:** attempts 09–11 render role/benchmark surfaces but stop waiting for the Run control. Attempt 12 has a workspace DOM artifact and no final result at inspection. The rehearsal remains incomplete; do not call repeated attempts a successful demo or infer the root cause from a timeout alone.

No application changes, tests, fits, server starts or pushes were performed by this progress check. The five partial feature units and finite acceptance checklist remain unchanged. Do not raise the completion estimate simply because files or test counts increased.

### Earlier delta after the 95% snapshot

**The estimate stays at 95%; progress is real, but no remaining responsibility point is fully closed.** Same 42 feature units, ten packages and weights. Inventory remains 37 implemented, five partial, none wholly absent. This is not an estimate that the remaining work takes only 5% of the elapsed time.

| New evidence | What it establishes | What stays open |
|---|---|---|
| `engineering-closeout-2026-10-21/launcher-01/result.json` | Saved ordinary-launch check passes: app, market/news/runtime children start; duplicate runtime is refused; owned children stop. | F02 current publication still missing. Startup/lifecycle is no longer merely code-inspected or a pending launcher acceptance. |
| Evidence-backed exchange calendar | `exchange.py`, clock/loop/lifecycle wiring and pinned calendar distinguish the October 20 holiday. Verified interval is October 19–23 only. | Do not extrapolate verified calendar coverage beyond that interval. This does not populate market history. |
| Observed macro-covariate adapter | `covariates.py` plus exporter support actual supplied variables, provenance, availability, units, finite/nonconstant values and at least 250 paired observations. | F08 still has no fitted policy-rate/inflation/tariff input artifact. Existing saved fit contains only lagged realised volatility. |
| Saved browser attempts through `browser-07/result.json` | Forecast identity is visible; all three roles have a canvas; backtest text includes the official NIFTY benchmark. | Latest attempt times out waiting for the saved defensive comparison name. Save/run/reopen/export and later institutional acceptance did not complete. The timeout alone does not prove an application defect; harness interaction versus app persistence needs one bounded diagnosis. No full browser-pass credit. |
| Saved JUnit results | `targeted.xml`: 119 passed, one skipped, zero failures/errors. `configured-calendar-tests.xml`: 116 passed, zero failures/errors. | These overlapping runs are not added together and do not replace actual-data/browser acceptance. |

Read-only recheck still finds one explicit deployment and only the old withheld replay decision, zero scenarios in the main scenario store, no network artifact, the existing unavailable sector artifact, and the same lagged-RV fit. Saved runtime readiness records `NullFeed` and warm-start observations Hawkes=0, RMT=1, Hamilton=0. Therefore process startup is verified, but usable current market publication is not. An isolated browser's stopped-worker banner is not evidence that the ordinary launcher failed.

**Finite next work, unchanged in scope:** complete the scenario/institution browser journey (distinguishing harness errors from product failures); finish legitimate live input/history support; obtain measured sector/network outputs under an explicit diagnostic specification; fit supported actual macro inputs; produce the bounded real evaluation report. Keep finished news and launcher work closed. Do not start another general defect hunt.

The sections below retain the preceding 92→95 implementation comparison; this latest delta supersedes older statements that owned lifecycle or forecast-ID visibility have not yet been checked.

### Previous implementation increase: 92% to 95%

| Change | Inspected evidence | Completion treatment |
|---|---|---|
| Measured sector implementation | `hawkes/sectors.py`, writer CLI, artifact selection, dashboard panel and flags passed into saved/ad-hoc portfolios, news and institution views. Saved actual artifact has `available=false`, empty flags and zero observed sessions. | C13 remains partial for usable-input integration; stop calling the producer/consumer path absent. F04 now needs supported native bars and a measured result, not another sector module. |
| Directed network implementation | Native sector-count adapter, explicit-specification constrained fit, versioned artifact/select path and regulator graph/matrix/export UI. Saved tests include synthetic direction checks. | C14 moves absent → partial. No real network artifact exists; the design is explicitly proposed/unadopted and real support is missing. Synthetic edges are not measured market transmission. |
| Fitted covariate scenarios | Actual 305-observation Hamilton artifact, persisted preprocessing/parameters, covariate-to-regime projection, score comparison and save/run UI. Read-only projection from this artifact returns a valid simplex. | U10 stays partial: the sole covariate is `lagged_rv`. The generic path works, but policy-rate/inflation/tariff covariates are not fitted or supported by this artifact. Do not silently rename volatility as policy input. |
| Defensive action comparison | `defensive.py` implements no-op, cash reduction, rotation, linear hedge and supplied-price puts; workspace forms and charts invoke the saved-scenario executor. A read-only calculation on 37 official index observations produces available baseline/action paths. | U11 moves partial → implemented within declared hypothetical/ex-post scope. No saved macro/defensive scenarios exist in the inspected store yet; perform save/run/reopen/export in final rehearsal. |
| Supported numerical tariff example | Browser-download JSON contains a cited, visibly historical India-origin steel example: old/new rates 25%/50%, cost base 1,000,000 and pass-through 0.5–0.8 produce a conditional range 100,000–160,000. Cached document hash matches its citation record. | N10 implemented for the agreed one-supported-example criterion; F05 closed. This is a manually curated historical case routed to the calculator, not proof of automatic rate extraction from live feeds. |
| Real evaluation coverage | Saved coverage now contains 81 Kalman and 81 independently derived forward-fill observations, with RMT-only pillar coverage. The adapter preserves source provenance and missing support. | F06 advanced; no completed real-data evaluation report was found. C12 remains partial pending the bounded runner/report acceptance, not a new adapter. |
| Ordinary market job / runtime readiness | Saved ordinary job reports acquisition, daily vintages and prediction succeeded. Read-only runtime store now has one explicit deployment, up from zero. | Startup and registration progress retained. Only an old withheld replay decision exists; current live publication is still unproved. |

The **three-point increase** is core/sector-network implementation 23 → 24, dashboard analytical functionality 18 → 19, and completion of the bounded news example 14 → 15. The other responsibility allocations are unchanged. This does not award points for added tests or for writing an unavailable result.

### Current closeout status

The October22 reconciliation above is authoritative for present status: F01/F03/F04/F05/F06/F08/F09/F10 are verified within their stated bounds. F02 remains incomplete; F07 awaits model-specification adoption and actual fit/browser acceptance. Earlier snapshots below explain prior findings, not current blockers.

## Scope, method, and limits of this audit

The scope remains the original 42 named units and ten packages. No new source-count target, commercial deployment requirement, scientific success gate or cosmetic backlog was added.

The preceding implementation comparison used the 92% snapshot hashes against `9a792b5` plus the October 21 working copy. New analytical modules, writers, consumers and saved artifacts were inspected; unchanged modules reuse previous evidence. Only the audit MD/JSON were edited. No application fixes, production writes, model refits, server launches or pushes were performed.

No test suite or browser rehearsal was rerun by this audit. The latest saved runs and incomplete browser attempt are documented above. Earlier saved `analytics-tests.xml` reports **42 passed**; it includes synthetic arithmetic/direction/projection checks and must not be described as 42 actual-data acceptance journeys. Earlier saved test evidence remains earlier evidence and is not summed into a new total.

Two lightweight read-only calculations resolved missing evidence: (1) one projection from the saved real Hamilton artifact, yielding one regime-probability row summing to 1; (2) a cash-reduction comparison on 37 stored official NIFTY 500 observations (February 20–April 20, 2020). Baseline maximum drawdown was approximately 0.33906 and the declared hypothetical action's 0.17912. These values validate that the software returns actual-price paths, not a tradable strategy, causal benefit or prospective warning claim. The request used one notional index unit, 1,000 initial cash, 50% reduction at the next supplied close, 10 basis points cost and zero cash return.

The new saved browser download was inspected directly. Its historical tariff case is `conditional_scenario`, includes evidence/curation and assumptions, and matches the cached proclamation hash. It is manually curated, separate from automatically interpreted live news. The old unavailable example remains an honest unsupported case, not evidence that the new supported case failed.

Read-only store evidence: one explicit deployment; one August replay decision marked withheld; the existing operational forecast remains dated October 19. No saved scenario rows were found, so the new macro/defensive save/run/reopen/export journey is not yet evidenced. The sector artifact is unavailable with zero observed sessions; the network artifact directory is empty. The fitted Hamilton artifact supports only lagged realised volatility and retains weak-regime-separation limitations. The real-evaluation coverage file is a coverage result, not a completed evaluation report.

### Basis for the one overall percentage

These are judgment-based scope weights, not development-hour measurements. Report **approximately 96%**. Responsibility weights remain unchanged.

| Engineering responsibility | Project points | Earned points | Reason for remaining deduction |
|---|---:|---:|---|
| Data foundation, acquisition, and runtime orchestration | 20 | 19 | Automatic owned runtime and real-history cold-start paths now exist; manifest/history population and actual current publication remain unproved. |
| Three pillars, reconciliation/fusion, and forecasting | 25 | 24 | Sector/network producers and consumers now exist; usable real support and current composite publication remain incomplete. |
| Dashboard and role decision-support capabilities | 20 | 20 | All intended bounded analytical implementations now exist, including actual fitted policy inputs. Remaining macro/console browser acceptance is counted under delivery. |
| News intelligence | 15 | 15 | Agreed bounded pilot functionality includes a cited historical numerical example and download; broad live extraction accuracy is not claimed. |
| Evaluation and reproducibility machinery | 10 | 9 | Stored-data adapter and Table C are implemented; real-input report acceptance remains. |
| Delivery, persistence/recovery, and demonstration reliability | 10 | 9 | Known renderer blocker repaired; one final cross-component rehearsal and bounded changed-contract checks remain. |
| **Whole project** | **100** | **96** | **Engineering estimate; predictive success and enterprise hardening excluded.** |

The shared history failure was counted once as a reliability issue. Finishing two planned market displays additionally earns product integration credit; it does not imply every affected role was previously absent. Feature counts below are tracking information, not another completion percentage.

## Real progress that should remain closed

- The three original pillar families remain implemented. Mathematical weakness or diagnostic-only eligibility does not erase their software.
- Historical replay, persisted runs, reconciliation, composite uncertainty and attribution have working implementations and saved evidence.
- The historical loader, point-in-time universe and new public-NSE acquisition have recorded real results: 7,489,028 daily rows, 3,584 symbols and 43 universe snapshots in the newer evidence. The recorded corpus now ends on **2026-10-19**.
- `seraph/prediction/operational.py` now computes the declared combined future-loss forecast and warning from the supplied snapshot. `scripts/run_prediction.py` persists it; the main application's **PREDICTION & EARLY WARNING** panel reads it. This is no longer merely an isolated research viewer.
- The latest daily chain runs acquisition before computation, re-flags new universe rows, rebuilds the current snapshot and invokes prediction. Scheduling, lease handling and separate execution/data-freshness status exist. A subsequent no-new-data run correctly reported that the corpus already reached the expected session.
- The runtime now supports persisted explicit deployment manifests and loads real eligible history on cold start; the launcher starts it automatically. The inspected store now has one explicit deployment but still needs sufficient legitimate history and actual current publication evidence.
- Portfolios now have upload/preview/save/history controls. Market scenarios have save/run/compare/review/download controls. Regulator cases have evidence/decision/status/export controls.
- News startup, supervision, source failure isolation, manual refresh, freshness distinctions, substantive text extraction, qualitative impact inference, real globe nodes/paths, instrument comparison and regulator reviews have substantial implementations and prior acceptance evidence.
- Packaging includes frontend assets, migrations and curated reference resources, with an installed-wheel probe. Local identity/role restrictions and durable stores exist.

Do not reopen those whole areas merely to refactor them, add more tests, beautify JSON, or improve hypothetical production-scale behavior.

## Major discrepancies in the completion report

### 1. Original console/history defect resolved in implementation

`bridge.js` now normalizes the object-shaped history through `historyOf`, draws the official benchmark with labelled units and gaps, and consumes actual `data.flow` through `flowHTML`. Localized renderer failures no longer abort the later news update. Both console and backtest use the repaired chart helper.

The 22 Python-payload/actual-JavaScript contract cases pass on the inspected working copy. They use a Node browser stub and synthetic stored test points, not a complete actual-browser visual journey. The earlier `history.forEach` exception is superseded; do not keep reporting it as a current defect.

**Verdict: IMPLEMENTATION COMPLETE; F01 browser acceptance pending.** Perform the remaining finite journey once; do not redesign or reimplement these charts.

### 2. Runtime startup/admission code exists; actual current publication remains open

The launcher now starts one owned `run_live.py --stay-running` process. A store-scoped lock prevents duplicate runtime ownership, `--owner-pid` detects launcher exit, and the PowerShell cleanup targets the process tree it started. `-NoLiveRuntime` is the explicit opt-out. The old finding that ordinary launch deliberately omits live operation is resolved in code.

`run_daily.persist` now creates content-based deployment IDs and records actual emission availability. `registry_from_store(..., allow_legacy=replay)` admits persisted manifests in live mode; legacy-derived registrations are restricted to replay. `cold_start` passes eligible real stored history to `warm_start`; it does not manufacture standardizer samples.

The inspected `prototype_runs/live.sqlite` now has **one explicit deployment** and still only an old withheld replay decision. The saved engine tests exercise fixture-backed paths; they do not demonstrate a real fresh live score. Availability of a launch command alone does not populate missing legitimate history.

**Verdict: reuse completed F02 startup/manifest/warm-up implementation; finish its actual-data journey.** Populate registered inputs through the existing producer, inspect actual readiness and demonstrate admitted current publication when supported. Preserve Hamilton's exclusion and honest absent/stale inputs. Do not reopen the empty-registry wiring fix or silently permit legacy data in live mode.

### 3. Fresh daily acquisition and snapshot refresh are now implemented

Commit `f7be092` makes `run_market_jobs.py` call `run_acquisition.py` before reading the latest session. The acquisition script fetches public NSE bhavcopies, re-flags affected universe years and rebuilds `research_data/current/`. The operational prediction path selects that current snapshot, preserving the original frozen research input.

The newer saved job status records `session=2026-10-19`, and the prediction state has that same decision date. The subsequent acquisition check correctly says there is nothing to acquire because the expected session is already stored. This supersedes the earlier August-staleness finding.

The launcher now starts the configured market runtime automatically. Remaining F02 acceptance concerns the actually populated inputs, readiness, service lifecycle and publication, not writing another launcher.

**Verdict: DAILY ACQUISITION RESOLVED; remaining F02 integration only.** Keep the new sequence. The new acquisition code retains pending derived sessions even when no new rows arrive, and checks a versioned snapshot before pointer publication. Verify that recovery path once; the earlier missing-recovery finding is no longer an absent implementation. The new published-cutoff check also detects missed pending-status writes. Reuse these paths; the remaining integration acceptance does not warrant rebuilding acquisition.

### 4. Forecast generation and ledger are now connected; acceptance is outstanding

`run_prediction.py` calls `issuance.issue(state, ledger)` before saving the UI state, then `issuance.settle` using the matching research snapshot. The current job chain no longer invokes the old experimental importer as its prospective forecast. `issuance.py` carries the fit/input identity and settles only after the next H observed sessions; the migration preserves outcome evidence. The panel displays the issued identity when present.

The saved October 19 state now contains its issuance identity, and a read-only ledger query confirms identical probability and model/input references. Actual issue time is October 20 at 22:06:41 IST, explicitly `delayed_operational`; the original as-of date was not presented as the issuance time. The saved retry reports `stored=false` with the same identity. Outcome settlement remains pending because the next 15 sessions have not been observed.

**Verdict: F03 actual-data/store integration complete; saved browser now also confirms the displayed forecast identity.** Reuse `operational-issuance.json` and the matching state/store. The latest saved browser confirms the panel identity is visible. Do not rerun an expensive research study or create another forecast ledger.

### 5. Analytical implementation now exists; do not repeat the old absent-feature claims

- **Sector flags:** the new producer counts actual C4 negative jumps in declared baseline/observation windows, persists coverage and supplies flags to portfolio/news/regulator consumers. The saved run has no observed sessions, so a nonempty measured demonstration remains F04.
- **Directed network:** the dedicated native-count estimator, artifact and graph UI now exist independently of the pooled Hawkes output. The old pooled `branching_matrix=()` no longer proves no network implementation exists. Real data and adoption of the explicit diagnostic specification remain F07; no real network artifact is saved.
- **Macro scenarios:** a real fitted artifact and generic covariate-to-regime-to-score path exist. Its sole covariate is lagged volatility. F08 is not yet a demonstrated monetary/trade-policy sensitivity engine, and Hamilton's production exclusion remains unchanged.
- **Defensive comparison:** the old guidance field may still have `drawdownReductionPct=None`; the separate saved-scenario calculator now generates actual-price wealth/drawdown paths. That old field alone is no longer evidence that F09 is absent. Final save/run/reopen/export acceptance remains.
- **Evaluation:** both reconciliation modes now have 81 real observations in the saved bounded coverage result, independently derived from archived inputs. Table C serialization exists. F06 needs one runner/report acceptance; it does not need another dataset loader.
- **News scenario:** the manually curated historical steel case uses cited 25%/50% rates and the existing calculator, with a real downloaded conditional result. F05 is complete for the bounded example; automatic extraction of live legal rates remains unproved and must not be implied.

## Fixed feature inventory

**I** = implemented and connected within this row's scope.  
**D** = implemented with a major known integration defect.  
**P** = partially implemented, including usable-result/input integration still missing.  
**A** = intended deliverable absent; a schema field or preview is insufficient.

“I” credits inspected implementation and applicable saved evidence. It does not claim a new browser pass at this revision. Implementation credit can precede final actual-data/browser acceptance; package status records that remaining acceptance explicitly.

| ID | Intended capability | Status | What exists / exactly what remains |
|---|---|---|---|
| C01 | Source history, universe and model inputs | I | Fresh public daily acquisition, universe re-flagging and current snapshot are now in normal operation with real October inputs. Remaining run-recovery/live concerns are in F02. |
| C02 | Hawkes calculations and diagnostics | I | Original/discrete estimators and archived diagnostics exist. Fresh production/sector/network paths are separate rows. |
| C03 | RMT calculations and diagnostics | I | Real daily spectral calculation exists. Current-score admission/warm-up belongs C08. |
| C04 | Hamilton calculations and regimes | I | Original and declared variant implementations exist. Preserve diagnostic eligibility/exclusion; scientific adequacy is separate. |
| C05 | Reconciliation, CSRS, uncertainty and attribution | I | Historical implementations and persisted output exist. Live integration is C08. |
| C06 | Historical replay and durable results | I | Sealed historical runs, reports and provenance are available. |
| C07 | Tick/bar runtime and restart recovery | I | Tick/bar, checkpoint and recovery runtime exists and is started by the launcher. Actual registered producer readiness/current publication remains C08. |
| C08 | Fresh inputs through real pillars to current risk | P | One explicit deployment and normal startup now exist; no current published live decision is evidenced. Sufficient legitimate history/input readiness remains. |
| C09 | Future-loss forecasts and baseline comparison | I | Historical pipeline plus newly integrated operational prediction panel. No claim of dependable predictive skill. |
| C10 | Ongoing forecast generation and prospective record | I | Saved operational forecast now matches the durable ledger, actual issue time and input/model identity. Retry evidence is idempotent; unobserved outcomes remain pending. |
| C11 | Existing evaluation/report inspection | I | Saved comparisons and current prediction diagnostics can be inspected. |
| C12 | Original experiment runner | I | Registered real-input report and canonical browser acceptance verified; unsupported cells remain unavailable. |
| C13 | Measured Hawkes sector flags | I | Actual native historical observations and saved-portfolio browser integration verified; partial coverage and receipt-time limits retained. |
| C14 | Directed market contagion network | P | Native-count directed estimator, explicit specification, artifact and regulator graph/export exist. No real fit saved; model adoption and actual support remain. |
| C15 | Ordinary launch orchestrates required services | I | Ordinary launcher starts news, daily jobs and one owned market runtime by default; explicit opt-out and store lock exist. Actual current scoring remains C08/F02. |
| U01 | Original console, globe and role views | I | Original console/globe/role rendering path repaired; current contract checks pass. Full visual journey remains F01 acceptance. |
| U02 | Historical run/date dashboard | I | Historical selection and object-shaped history renderer connected; actual-browser date/backtest check remains. |
| U03 | Official Nifty 500 overlay | I | Official benchmark payload now rendered with labelled scale, coverage and null gaps. |
| U04 | Holdings value/coverage | I | User-entered holdings calculation exists; missing measured sector risk is U06. |
| U05 | Durable portfolios/uploads/history/watchlists | I | New workspace controls connect the store. Selection does not yet activate saved holdings in the analysis/news context; that adjacent integration is explicitly F04. |
| U06 | Measured portfolio sector risk | I | Saved portfolio activation resolves authorised current/historical holdings into portfolio and news analysis; measured flags remain F04. |
| U07 | FII/DII and residual flow display | I | Tools renderer consumes real flow payload, date, INR-crore units and unavailable state; no longer hardcoded constants. |
| U08 | Pillar shock sensitivity | I | Existing C11/C9 calculation and control path; hypothetical output is labelled. |
| U09 | Durable market scenarios | I | Save/run/history/compare/review/download controls now exist. |
| U10 | Macro/policy covariate-path simulation | I | Actual RBI repo-rate fitted artifact, projection and scenario UI exist within explicit retrospective sensitivity scope. F08 final browser acceptance remains; no causal policy or prediction claim. |
| U11 | Defensive action drawdown comparison | I | Defensive action calculator and saved-scenario UI implemented; read-only actual-index comparison produces wealth/drawdown paths. Final save/run/reopen/export rehearsal remains. |
| U12 | Regulator action journal | I | Existing durable, role-scoped action workflow. |
| U13 | Regulator cases and evidence exports | I | New controls connect lifecycle, evidence, decisions and downloads. |
| U14 | Institution-level exposure decomposition | I | Authorised versioned institution holdings, aggregate/institution/sector shares, cutoff and regulator UI/export implemented; saved arithmetic/access tests pass. Final UI rehearsal pending. |
| U15 | Installable frontend/runtime resources | I | Installed-resource verification exists. A fully portable installed-worker launcher is outside the local-demo completion requirement. |
| N01 | Automatic news startup/shutdown | I | Supervisor, lock and owned lifecycle paths exist. |
| N02 | Polling/manual refresh/freshness/isolation | I | Implemented with saved partial-source-failure and rehearsal evidence. Current external acquisition health is not certified by old evidence. |
| N03 | Multi-source aggregation | I | Real registry/reconciliation/fetch routing. Wider coverage is optional for this freeze. |
| N04 | Substantive extraction/interpretation | I | Document enrichment, structured fields and lifecycle interpretation exist. General accuracy remains unvalidated. |
| N05 | Qualitative sector/exposure impacts | I | Evidence-linked mechanisms, lifecycle filtering and sector projections exist; no invented loss sizing. |
| N06 | Globe markers, paths and evidence | I | Backend and original-globe layer exist; shared history failure repaired. News paths are exposure links, not the measured contagion network. |
| N07 | Retail holdings news relevance | I | Supplied holdings route exists; activating durable saved holdings is F04. |
| N08 | Product-country matrix | I | Role-specific matrix and original-console renderer exist. |
| N09 | Cited instrument comparison | I | Pair selection/dispatch/comparison path exists. JSON presentation is sufficient; no beautification task. |
| N10 | Numerical conditional tariff scenario | I | Cited historical steel tariff case produces conditional amount and appears in downloaded browser JSON. Manually curated historical example, not automated live-rate extraction. |
| N11 | Regulator instrument-link review | I | Attributed persistence and subsequent projection read-path exist, with saved successful browser evidence. |
| N12 | Download displayed news analysis | I | Pinned displayed analysis, matrix and evidence can be downloaded as JSON; saved browser file inspected. Numerical scenario acceptance is N10. |

Inventory: **38 I, 0 D, 4 P, 0 A**. This count is not the overall percentage. Partial units are C08 current scoring, C12 real evaluation, C13 measured sector output and C14 measured directed network. F01/F08 acceptance is tracked separately.

## Finite implementation checklist

These are ten bounded packages, not an invitation to discover an unlimited new backlog. Reuse all newly implemented slices. Complete their bounded acceptance and remaining F02/F04 integration before extending the advanced calculations.

| Package | Priority and classification | Required implementation | Main files/interfaces | Completion evidence and stopping condition |
|---|---|---|---|---|
| **F01 Restore the original console and finish existing market displays** | **IMPLEMENTED — acceptance only** | History normalization, benchmark/flow rendering and localized failure boundaries are implemented. Complete the one remaining browser journey. | `dashboard/console_backend.py`, `console_component/bridge.js`, `ingestion/benchmark_client.py`. | One actual browser pass through console, role switch, backtest and news/globe update with current payload. No `history.forEach` failure; benchmark visible; stored flow values/date shown when available. |
| **F02 Complete current market operation** | **PARTLY COMPLETE — remaining core integration** | Reuse automatic runtime startup, explicit manifest registration, real-history cold-start and recovery code. Populate legitimate inputs/manifests and finish admitted current publication/lifecycle acceptance. | `launch_prototype.ps1`, `run_market_jobs.py`, `run_acquisition.py`, `run_daily.py`, `run_live.py`, `live/inference.py`, `engine_adapter.py`. | Reuse real October-input evidence; demonstrate legitimate admitted observations and cold startup without synthetic warm-up; complete actual current publication and owned restart/shutdown without duplicates. |
| **F03 Join operational forecasting to its prospective ledger** | **IMPLEMENTED — real state/ledger evidence complete** | Preserve the verified issuance/settlement path and evidence. Include the panel identity in final rehearsal; no new feature implementation. | `prediction/operational.py`, `run_prediction.py`, `run_forecast.py`, `live/store.py`, prediction panel. | One newer supplied input date yields a generated forecast and matching immutable ledger record; repeat does not duplicate; stored issue time is not backdated; immature outcome refused. No requirement that the model predicts a crisis successfully. |
| **F04 Finish portfolio-to-analysis and measured sector integration** | **IMPLEMENT NOW — meaningful functionality; measured part depends on F02** | Reuse saved-portfolio activation and the now-connected sector producer/consumer path. Obtain supported native bars and demonstrate actual measured flags with coverage. | `prototype_app.py:310`, `:1147`, `:1268`; `console_backend.py:736`; `pillars/hawkes/engine.py`; `write_hawkes_production.py`; portfolio adapters. | Selecting/reopening a saved portfolio changes relevant news/holdings without repasting JSON. A real supported sector interval produces inspectable flags and matching portfolio coverage; uncovered sectors stay unassessed. Do not convert qualitative news into measured Hawkes flags. |
| **F05 Finish the two remaining news deliverables** | **COMPLETE FOR AGREED PILOT SCOPE** | Retain the demonstrated historical numerical case and displayed-analysis export. Preserve curation, historical dates and hypothetical cost/pass-through labels. | `bridge.js:486`, `prototype_app.py:244–253`, `news/workflows.py`, `news/scenarios.py`, `news_view.py` role payload. | Download opens and matches the displayed analysis. One real cited rate change produces a conditional amount from explicit user cost/pass-through assumptions, or the scope explicitly states numerical pricing is unavailable. No new engine or universal tariff coverage required. |
| **F06 Complete the original evaluation data interface** | **IMPLEMENTED INTERFACES — real-input acceptance pending** | Reuse the new stored-data adapter, CLI and widened Table C publication. Verify a real input/report slice with truthful coverage; preserve preregistration. | `run_experiment.py`, `validation/experiment.py`, `experiment_store.py`, `shared_types/validation.py`, evaluation panel. | A supported real data slice reaches the runner and renders genuine measured/unavailable cells with provenance; Table C is not silently omitted. No synthetic cells presented as real; no altered thresholds or forced positive metrics. Large expensive evaluation is not necessary merely to close this adapter. |
| **F07 Implement measured directed contagion** | **PARTIAL — real design/input integration** | Reuse the new estimator/artifact/renderer. Adopt a supported specification and obtain real native counts before fitting. Keep full-sample retrospective analysis distinct from point-in-time live inference. | Hawkes network producer, `shared_types/pillars.py`, `dashboard/gateway.py`, original frontend. | An evidenced directed edge can be inspected back to actual fitted input/method/window; all-zero/unidentifiable outcomes remain valid and visible. No fabricated arrows, no relabelling news exposure paths. Model definition must respect amendments; no silent scientific change. |
| **F08 Complete macro-policy scenario input** | **IMPLEMENT FOR FULL INTENDED SCOPE — incomplete role capability** | Reuse the fitted projection artifact and `z → xi → conditional score` workflow. Supply a documented fitted macro-policy covariate artifact; the existing lagged-RV-only fit does not support arbitrary policy variables. Keep excluded Hamilton out of the actual composite unless separately approved. | `decision_support/artefacts.py:159`, Hamilton projection/artifact code, `console_backend.py:775`, role UI. | A named hypothetical macro path reaches the documented projection and displays its resulting regime/score path and assumptions. No claim of causal policy effectiveness or guaranteed score movement. |
| **F09 Implement realised defensive-action comparison** | **IMPLEMENTED — workflow acceptance pending** | Reuse the calculator, benchmark adapter and scenario UI; verify save/run/reopen/export with declared actual prices and assumptions. Do not require unavailable option histories merely to demonstrate another supported action. | `decision_support/artefacts.py:203`, action comparison calculator, evaluation data adapter, institutional UI. | A historical epoch produces reproducible baseline/action wealth paths and drawdown differences under visible assumptions. A worse or zero-benefit action is a valid result. No fabricated reduction percentage. |
| **F10 Implement institution exposure decomposition** | **IMPLEMENTED WORKFLOW — acceptance pending** | Reuse the new submission schema/store, regulator controls and holdings aggregation. Verify revisions, access scope, cutoff, totals and export; do not describe holdings shares as measured systemic-risk contributions. | `dashboard/gateway.py:105`, institution input/aggregation service, identity guards, regulator UI. | Two explicitly identified submissions reconcile to totals and can be inspected by regulator; other roles cannot receive restricted data. User-supplied/demo positions are labelled. Access to a real institution's private book is not needed to implement this software. |

F07–F10 are planned substantive features, not production polish. They may be explicitly deferred by narrowing the assessed academic scope, but their current absence cannot be counted as full completion of the originally intended project.

**Dependency order:** F01 → F02 → F03/F04 → F05 → F06 → F07–F10. The news download portion of F05 is independent and can be completed earlier. F08–F10 need explicit model/input assumptions; prepare them as declared interfaces, not hidden defaults. No new permission rule is inferred from old component ownership notes.

### Work to skip for this finish line

- More news sources merely to increase the count, universal Hindi/OCR/table interpretation, or a much larger exposure registry.
- Cosmetic redesign, replacing readable JSON with elaborate panels, micro-optimizations, or sweeping refactors.
- More tests solely to improve totals or coverage percentages.
- Cloud/multi-tenant deployment, enterprise identity integrations, scale testing, or fully portable installed background services when the assessed demo uses this local checkout.
- Re-running expensive experiments already evidenced without a relevant code or assumption change.
- Forcing predictive gains, a successful COVID warning, positive action performance, or a passed scientific benchmark as a precondition for **engineering** completion.
- Unrelated minor defects that do not change the meaning of results, block a required journey, lose important data, or crash the demonstration.

## Acceptance and stopping rule

Use the same ten packages until they are completed or explicitly removed from the submitted scope. Do not add requirements because another library, metric, source, visualization or hypothetical deployment improvement is discovered.

After the affected paths are completed, perform one focused final rehearsal:

1. Start through the ordinary launcher; observe news and configured market operation plus separate input/decision freshness.
2. Show an actual eligible current decision or clearly labelled supported replay, the three retained pillar families, and an operational forecast with matching ledger record.
3. Navigate the original globe/console and all three roles without a rendering failure.
4. Select a saved portfolio, see its news relevance and measured risk coverage, and reopen it.
5. Run and reopen a market scenario, compare it, and download it.
6. Open a regulator case, attach evidence, record a decision, and export it.
7. Inspect cited news on the globe, run the supported tariff scenario, and download the same displayed analysis.
8. Demonstrate the planned network, macro scenario, defensive comparison, institution decomposition and real evaluation input interface.

A passing rehearsal means required functionality works, dates/evidence/limitations are truthful, outputs survive the relevant restart, and no major integration defect interrupts the journey. It does **not** require every market/news source to be reachable or a model to be predictive.

**At that point, freeze feature development and move to scientific evaluation and final presentation.** Reopen engineering only for a reproducible blocker of one of these agreed journeys.

## Evidence references

- Scope: `docs/SERAPH-FEATURE-COMPLETION-CHECKLIST-2026-10-19.{md,json}`.
- Current report and caveats: `docs/SERAPH-FUNCTIONAL-COMPLETION-REPORT-2026-10-19.md`.
- Selected checks: `docs/evidence/functional-completion-2026-10-20.json` — now 11 selected journeys; contains synthetic warm-start disclosure.
- Operator paths: `docs/DEMONSTRATION-RUNBOOK-2026-10-19.md`.
- Recorded jobs: `prototype_runs/market-jobs-status.json` — newer successful run uses 2026-10-19; `prototype_runs/acquisition-status.json` distinguishes no new rows needed from a failed fetch.
- New browser/runtime review: `docs/evidence/demo-readiness-2026-10-20/{browser.json,source-manifest.json,runtime.json}`; rendering files match the captured hashes.
- Current prediction: `prototype_runs/prediction/state.json`; ledger comparison from a read-only query of `prototype_runs/live.sqlite`.
- Installed resources: `docs/evidence/PACKAGING-2026-10-20.json`.
- News evidence: `docs/evidence/news-intelligence/news-completion-2026-10-19/`.
- Scientific boundaries: `README-RESEARCH.md`, `EXPERIMENT.md`, documented amendments, and preregistered evaluation.

The accompanying `SERAPH-OVERALL-ENGINEERING-COMPLETION-AUDIT-2026-10-20.json` contains the status index and hashes of the key inspected files. Line numbers refer to the inspected revision and may move with later changes.

---

## Technical implementation plan

Plan added: 2026-10-20; latest refresh: 2026-10-21. Current planning baseline: `9a792b5` plus the October 21 uncommitted implementation in this 95% reassessment. New analytical paths below are implementation references where already built, not instructions to rewrite them. F01 is committed; F03/F04/F05/F06/F10 and acquisition recovery include newer working-copy code. This is a development specification and handoff; the current status tables above identify completed parts. Proposed work is not automatically a claim of completion.

### P0. Starting state and change control

**Do this once, before implementing.**

1. Read this plan, `AGENTS.md`, `README-RESEARCH.md`, `EXPERIMENT.md`, and the relevant adopted contracts/amendments. Preserve the three pillar families and the frozen scientific evidence.
2. Inspect `git status --short` and the current diff. `registry_from_store` and `daily_vintage_bundles` have now landed in `6db3e83`; reuse them. At reassessment, the issuance, dashboard/news, acquisition, evaluation and institution files contain other ongoing uncommitted work; consult the JSON working-copy inventory. Do not reset, overwrite, commit as your own, or silently replace existing work. Establish ownership before overlapping edits; work on independent packages meanwhile.
3. Record the starting commit and hashes of files that will be changed. Use the existing evidence directory conventions. No new worktree or duplicate main codebase is needed for this plan.
4. Do not push. Do not modify the previous research snapshot or reinterpret historical imports as prospective forecasts. Additive schema migrations must preserve existing records.
5. Maintain one completion ledger for F01–F10. A package has one of `not_started`, `in_progress`, `input_blocked`, `verification_pending`, or `complete`, with its acceptance evidence. A claimed completion without evidence stays `verification_pending`. Do not add new packages for cosmetic issues discovered along the way.

**Changes since the audit that must be reused:**

| Area | Current evidence | Planning consequence |
|---|---|---|
| Public daily market acquisition | Commit `f7be092` adds `seraph/ingestion/bhavcopy_client.py` and `scripts/run_acquisition.py`. The saved functional evidence reports 7,489,028 rows through 2026-10-19. | Do not rebuild the acquisition client or require Kite credentials for this daily-data route. |
| Derived input refresh | `run_acquisition.py` re-flags the affected universe years and writes a new snapshot under `research_data/current/`; `operational.snapshot_path()` selects it. | Preserve the frozen original snapshot. Finish/reuse recovery and lineage checks, not a second snapshot pipeline. |
| Startup ordering | `run_market_jobs.py` now invokes acquisition before reading the latest stored session and calculating daily products. | The audit's “no acquisition step” finding is historical. Complete the rest of F02 against this new chain. |
| Bundle registration | `6db3e83` supplies `registry_from_store` to the service; focused admission/refusal tests exist. | Keep the repaired registration. Verify remaining manifest identity, real warm-up and current publication; do not repeat the empty-registry fix. |
| Prediction ledger | The ordinary chain issues the actual operational prediction; actual state/ledger values and identity now match. | F03 actual-data connection is accepted. Retain evidence; check the existing displayed ID only in the final combined browser rehearsal. |
| New closeout implementation | F01 committed; F03 issuance, F04 activation, F05 download, F06 stored adapter/Table C and F10 institution paths now exist. | Reuse these changes; current package status defines the remaining work. Do not repeat earlier absent-feature findings. |

Do not treat an evolving completion percentage as the work queue. The queue is these ten deliverables. The audit percentage is a dated estimate, not an instruction to earn arbitrary points.

### P1. Execution order and dependencies

Use a sequential implementation session by default. These changes share the launcher, dashboard dispatcher, stores and data contracts; simultaneous edits would create unnecessary integration work.

| Sequence | Slice | Dependency | Why this order |
|---:|---|---|---|
| 1 | F01 final browser acceptance | Existing implementation | Verify the repaired main route once; no chart rewrite. |
| 2 | Reuse completed F05a download | Saved browser evidence | No independent rebuild; include it with the supported tariff acceptance later. |
| 3 | F04 saved-portfolio browser acceptance | Existing activation implementation | Verify selection/reopen once; retain measured-sector work separately. |
| 4 | F02 remaining runtime integration | Reuse `f7be092` and `6db3e83`; inspect current ownership | Establishes trustworthy current input/output behavior beyond the repaired acquisition/admission steps. |
| 5 | F03 operational forecast ledger | Operational prediction result and input lineage | Connects prediction generation, persistence, display and later outcome settlement. |
| 6 | F04 measured sector portion; F05 evidenced tariff example | Appropriate market/news evidence | Finish actual measured coverage and one numerical news demonstration. |
| 7 | F06 real evaluation adapter | Stored states/labels/coverage | Makes existing evaluation machinery consume actual project data. |
| 8 | F10 institution decomposition | Holdings parser, identity, sector/coverage adapters | Reuses the completed portfolio infrastructure; does not depend on a new financial model. |
| 9 | F08 macro-policy workflow | Fitted diagnostic artifact and saved scenarios | Reuses existing projection and scenario machinery. |
| 10 | F09 saved comparison acceptance | Existing calculator and actual-price adapter | Reuse implemented paths; verify save/run/reopen/export once. |
| 11 | F07 directed network | Sector streams and declared network specification | Most model-dependent slice; use the completed data/attribution infrastructure. |
| 12 | One final acceptance rehearsal | All retained package criteria | Freeze once the agreed journeys pass. |

This refines the earlier coarse dependency order: export, saved holdings and institution decomposition need not wait for all market-model work. A missing intraday credential blocks the relevant data verification, not every independent package.

### P2. Shared implementation rules and contracts

Use the existing Python 3.12, Streamlit, embedded JavaScript/Three.js, Polars, NumPy/SciPy, Pydantic and direct database access. No new service framework, task orchestrator, authentication provider or general-purpose agent system is required.

The following shapes are **proposed interface additions** where equivalent fields do not already exist. Reuse existing `product_types` provenance/timing/coverage structures and `Ok`/`Err` conventions; do not create competing envelope systems.

| Interface | Required content | Consumers and invariants |
|---|---|---|
| Market run context | `run_id`, mode, input manifest/hash, data cutoff, generated/received timestamps, model/weight IDs, requested and actual session | Prediction, inference, dashboard and evidence files must identify the same underlying run. Fetch time is not the observation date. |
| Analysis context | Market run/date, role/principal scope, news decision time, selected portfolio/snapshot ID, scenario/result ID | Dispatch/export must reject or visibly discard stale-context requests. The server resolves private resources; IDs from the browser are not authority. |
| Available analytical result | Producer/version, observation window, evidence references, coverage, units, status, limitations | “Missing” is not numeric zero. Preview data never becomes an observed/derived value merely because it has the same shape. |
| Unavailable result | Machine reason plus actionable human explanation, affected field/path, source/model context | Localized absence must not crash the entire page. An absence message does not complete an otherwise unimplemented feature. |
| Persisted analytical artifact | Stable content identity, input references, parameters/assumptions, created time, result, schema version | Reopen/export reproduce the recorded result. Preserve old artifacts and scientific evidence. |

For model artifacts, separate `training_end`, `fit_completed_at`, `deployed_at` and `input_end`. Do not derive an entire model's training interval from whichever observations happen to be in a table today. If old artifacts lack reliable provenance, mark them historical/legacy and constrain their use.

For migrations, inspect the latest existing migration before choosing the next filename. Do not reserve a migration number in this document while other work is active. Extend product contracts in their owning modules; the Table C mathematical-contract change is isolated in F06 with downstream tests.

### F01 implementation: console, benchmark and flow

**Current status:** Implemented in `9a792b5`; 22 current contract checks pass. The numbered implementation specification is retained for traceability, not a rewrite request. Remaining: one full browser journey.

**Existing building blocks:** `console_backend.project_run`, `_history_with_benchmark`, `benchmark_client.align`, `bridge.js` rendering functions, `market_flow`.

**Implement these changes:**

1. Establish one current history contract:

   ```text
   history = {
     rows: [{date, csrs, benchmark_close, benchmark_return, benchmark_available}],
     series: {label, source, available, first, last},
     units: {csrs, benchmark},
     coverage: {csrs_dates, matched, benchmark_missing, first_missing},
     representativeness, note
   }
   ```

2. In `bridge.js`, normalize at the component message boundary. Current payloads use the object; if retaining legacy list support, convert a list to `{rows: list, benchmark unavailable}` in one place. Do not scatter shape checks through every chart.
3. Make `spark` consume rows explicitly. Update both `renderConsole` and the historical backtest call site. Render CSRS and benchmark returns in aligned charts with separate labelled scales, or explicit dual axes. Preserve `null` gaps; do not forward-fill missing index observations.
4. Replace the tools-panel FII/DII/residual example values with `data.flow` when `available=true`. Display the source date, INR-crore units, numerator/denominator scope and proxy caveat. Show unavailable/fabricated status when actual values are absent for the selected date. Never show a future flow print on a historical decision.
5. Keep console rendering separate from news-layer application so a localized optional-chart failure can produce a visible chart error without suppressing all role/news updates. This is a narrow boundary around the known failure, not a redesign of the component.

**Files:** `seraph/dashboard/console_backend.py`, `seraph/dashboard/console_component/bridge.js`, relevant renderer tests. Change `benchmark_client.py` only if its existing contract lacks a required field.

**Acceptance:**

- Feed the actual current Python payload to the JavaScript rendering path; object-shaped history renders.
- Test one matched index date and one genuine missing date; units and gaps survive.
- In the actual browser, switch all three roles, select a historical date, open backtest and tools, and confirm news markers still update.
- Record one screenshot and browser-console result with the commit and payload hash. No screenshot-only acceptance for hidden JavaScript exceptions.

Stop F01 when these pass. Do not redesign the globe or all charts.

### F02 implementation: current data, admitted models and ordinary startup

**Current status:** Automatic runtime startup, explicit deployment registration, real-history cold-start and recoverable snapshot publication are now implemented. The live store now has one explicit deployment and no current published decision. The specification below is a reference for finishing actual-data readiness/acceptance, not an instruction to rewrite these paths.

Split this into **F02a daily inputs**, **F02b model/state admission**, and **F02c runtime lifecycle**.

#### F02a — reuse the new daily acquisition sequence

Retain:

```text
public NSE acquisition
  → affected-universe updates
  → research_data/current snapshot + manifest
  → daily pillar vintages
  → operational prediction
  → publication/read models
```

1. Reuse `run_acquisition.py` and `bhavcopy_client.py`. Inspect the recorded acquisition/derived-step results instead of downloading the entire history again.
2. Reuse the implemented pending-session and published-cutoff recovery. The earlier no-new-rows skip defect has been addressed. If acquisition succeeded but snapshot/universe derivation failed, the next run must resume the missing derived step even when there are no additional rows to fetch. Persist source and derived cutoffs/hashes; decide from those, not only `stored_sessions`.
3. Publish the snapshot and its manifest consistently. Write temporary artifacts, validate dates/required columns and provenance, then promote a completed version. Retain the last valid version on failure and mark it stale; do not pair a new manifest with old parquet bytes.
4. Confirm the fresh-return construction uses a coherent corporate-action/price basis. The new bhavcopy is unadjusted while the historical corpus may be adjusted. Preserve basis metadata and use an existing verified adjustment path where available. Otherwise identify affected/unusable observations and coverage; do not silently interpret split-induced jumps as market crashes. This is input correctness, not a new corporate-actions platform.
5. Distinguish corpus readiness, snapshot readiness and model readiness in the existing job status. A source failure can leave the old dashboard usable, but must not label its outputs newly current.

#### F02b — connect legitimate bundles and warm-up state

1. Retain the committed `registry_from_store` repair and reconcile its provenance with `LiveStore.register_deployment`/`deployments`. Prefer the existing persisted deployment manifest as authority. If legacy vintages need an adapter, give it a declared legacy identity and bounded historical mode.
2. Ensure model IDs distinguish materially different fits. Hash the artifact/configuration, not just the label `original rmt`. Record training end and actual artifact availability. A query taking earliest emission plus latest input across a shared model name is insufficient evidence of one immutable fitted bundle.
3. Construct `InferenceService` with eligible registered deployments before restoring its state. Preserve config/checkpoint compatibility checks.
4. On cold start, load real, point-in-time historical vintages and the required state/standardizer history up to the decision cutoff. If there is insufficient history, show warming-up and its actual progress. Do not synthesize a time series or rely on synthetic fixtures from `verify_functional_completion.py`.
5. Feed the actual new vintage into the service; confirm the diagnostics name the admitted input, model and mask. Preserve Hamilton's standing exclusion and Hawkes staleness behavior. Do not weaken the registry or publication gate to obtain a green dashboard.
6. Avoid counting an old carried-forward score as proof that the new producer is connected. Acceptance must inspect the selected vintage IDs and admission reasons.

#### F02c — launch and maintain the configured runtime

1. Keep `launch_prototype.ps1` as the canonical entry point. Start news and daily inputs as now, and start one configured market runtime with the same resolved store paths. Add an explicit opt-out for users who want no live connection; routine startup should not require a second terminal.
2. Resolve the broker once, without logging secrets. Valid credentials permit connection; expired/missing credentials produce a named degraded state and refresh instructions while daily public acquisition/news continue.
3. Use the current session lifecycle/clock to wait outside the session and resume at the next supported session. A dashboard opened before market hours must not require restarting manually to begin the market session.
4. Reuse ownership/lease/supervision patterns; do not start a worker per Streamlit rerun. Stop only owned children. Where ordinary bare Streamlit is documented as supported, provide the equivalent guarded ensure-runtime path or clearly consolidate supported startup instructions.
5. Persist decisions through the existing atomic decision/checkpoint/outbox path. Route the selected current decision to the existing UI adapter. Keep historical run selection and current news clocks independent and visibly labelled.

**Targeted tests:** extend `test_fresh_data_acquisition.py`, `test_t03_real_producers.py`, `test_t06_engine_in_the_loop.py`, `test_c15_unified_launch.py` and existing runtime-recovery tests only for changed behavior.

**Acceptance:** reuse the completed real daily-acquisition evidence; verify a failed derivation resumes; demonstrate one genuine model admission and a cold-start state with real history; confirm ordinary startup starts configured workers once and shutdown is owned. For a live current-score claim, require an actual eligible current observation/decision. A replay or unavailable message cannot satisfy that live claim. Credential/data limits stay explicit without blocking independent development.

### F03 implementation: one forecast result, one issuance record

**Current status:** Implemented, with a matching real state/ledger result and retry evidence. The following specification is retained for traceability; only the panel check in final combined rehearsal remains, not a new issuance implementation.

**Resolved problem:** operational forecasts and imported experiment rows were different producers. The normal job chain now issues the operational result directly; old imports remain explicitly historical.

**Implemented service responsibility** in `prediction/issuance.py` (names below describe the contract):

```text
issue_operational_forecast(state, input_manifest, model_manifest, issued_at)
  → {forecast_id, stored, mode, as_of, issued_at}
settle_matured_forecasts(observed_price_path, observation_manifest, now)
  → {settled_ids, pending_ids, unavailable_reasons}
```

1. Have `run_prediction.py` pass the computed `PredictionState` to issuance before publishing the UI state. The state file/read model carries the resulting forecast ID.
2. Use the same probability, warning threshold, abstention state, target, horizon, actual issuance time and input/model hashes in storage and display. Preserve `null`/unassessable rather than converting it to “no risk.”
3. Reorder `run_market_jobs.py`: generate and issue current prediction once; settle eligible prior records separately. Remove the routine call that imports old experiment rows as if it were today's producer. Keep a separately named historical-import command with `historical_import`/replay metadata.
4. Extend the existing `prospective_forecasts` schema additively only where necessary: issue mode, stable model-manifest reference, input-manifest reference, explicit target definition and outcome-window identity. Reuse current columns and triggers; do not create another forecast table.
5. Separate model identity from the hash of a growing full predictions file. A refit's identity must remain reproducible after more observations arrive. Persist the fitted parameters/scaler/feature ordering or a deterministic reconstruction manifest sufficient to reproduce that issuance.
6. Derive maturity from the actual ordered market sessions, not a calendar approximation alone; the implemented settlement uses observed sessions. For the existing target, settle using the minimum close relative to the decision close across the next 15 observed sessions, preserving the declared 10% barrier. Missing observations delay settlement; they are not negative labels.
7. Record the index/return definition used. Do not settle a forecast on official Nifty returns if it predicted the research market index. Outcomes must use the same defined series and traceable revisions.
8. Keep issued forecasts immutable. If the same key arrives with materially different prediction content, report a conflict rather than overwrite. Retries of the same result are idempotent.

**Acceptance:** generate one new cutoff from supplied real inputs; inspect the identical stored/displayed probability and ID; retry once; refuse premature settlement; settle an already matured historical test record against its exact price window. The historical settlement test must not be described as prospective performance.

**Tests to extend:** `test_t04_prospective_forecasts.py`, `test_prediction_integration.py`; add only the specific same-result, maturity and provenance cases above.

### F04 implementation: saved holdings and measured sector risk

**Current status:** Saved-portfolio activation and measured-sector producer/consumer integration now exist. The saved real sector artifact has zero observed sessions. Remaining: supported native input, one covered output and final UI acceptance; do not rebuild the producer.

#### F04a — make the saved portfolio the analysis input

1. Add an explicit “Use this portfolio” action, or make the existing selection activate it with a visible active indicator. Resolve `portfolio_id` and the effective snapshot server-side through `WorkspaceStore` and the current principal.
2. Store IDs/context in session state, not an unaudited client-side copy of private holdings. Re-read the selected snapshot when it changes.
3. Pass the selected snapshot's normalized holdings to both the existing `portfolio_overlay` and the news-role/exposure-trail adapters. The news adapter expects holdings; the existing coverage result contains `byHolding`/`bySector`, so normalize once instead of confusing these shapes.
4. Reconcile this route with `console_portfolios`, which currently updates only after the ad hoc JSON calculator. Make the precedence explicit: active saved snapshot or an explicitly labelled ad hoc input. Do not silently let an old ad hoc portfolio override the selected saved one.
5. Preserve historical semantics: current holdings overlaid on a historical market decision must be labelled as current holdings. Historical holdings mode must use `holdings_as_of` and its original effective times.
6. A role/owner switch clears or re-resolves unauthorized selection. A saved watchlist remains a watchlist; do not silently treat it as monetary holdings.

#### F04b — replace empty measured-flag inputs

1. Reuse jump extraction, point-in-time membership and sector mapping. Build per-sector negative-jump counts over documented observed sessions, with eligible-member coverage and actual observation denominators.
2. Compute baselines from the declared historical/training interval using the same counting units. Feed these into existing `hawkes.engine.sector_flags`; do not invent a second threshold formula.
3. Persist a sector observation set containing sector ID, count/window, baseline, flag, input cutoff, model/config ID and coverage. Use the existing Hawkes output/store location if it can hold per-sector rows without losing identity; otherwise add an additive owned table.
4. Select the flag set eligible at the requested decision time. Replace the hardcoded `{}` in `console_backend` with this adapter; route the same set to the sector diagnostics view.
5. Missing sector history remains uncovered, not cleared. A sparse sector must not receive an invented baseline merely to fill the UI.
6. Keep news-derived sector mechanisms and measured market micro-flags distinct in transport and legend.

**Acceptance:** reopen a saved portfolio and see matching holdings/news relevance without repasting; show one real measured flag set and its coverage; check portfolio total/exposed/uncovered arithmetic and a missing sector. Extend `test_port01_port02_workspace.py`, `test_c11_portfolio.py`, `test_t06_t07_measured_surfaces.py` and a focused browser journey.

### F05 implementation: complete news export and a supported tariff example

**Current status:** Complete for the agreed bounded scope: a cited historical numerical tariff case and downloaded displayed analysis now exist. The steps below are retained acceptance/reference requirements, not a request for another example or automatic universal rate extraction.

#### F05a — export the displayed work product

1. Save the last scenario/comparison result in the current server-side analysis context with its event IDs, revisions, assumptions and decision time. Generate a stable result ID. Reuse the existing request/result correlation mechanism.
2. Change the frontend export request from `{}` to identifiers for the selected displayed result and context. The server must reconstruct or retrieve the analysis; do not trust a browser-supplied arbitrary result dictionary as authoritative.
3. Supply the institutional matrix from the actual role payload builder. `news_channel` itself does not contain `role_view`; remove the current lookup that silently yields `None`.
4. Use `workflows.export_analysis` to include sector/holding links, matrix, comparison, scenario, assumptions, evidence URLs/revisions, timestamps and limitations, restricted to the current role.
5. Provide a real download. The simplest implementation is a Streamlit `download_button` bound to the export bytes after the result returns; a browser Blob/download link is also acceptable if already supported. Choose one route and retain UTF-8 JSON as the required format. PDF/Excel are not required.
6. Name the file with analysis ID/as-of and format version. A role/date/portfolio change must not export the previous context without a visible explicit selection.

#### F05b — make one real numerical scenario demonstrable

1. Inspect stored enriched instruments first. Select a cited ad-valorem change with compatible old/new levels, product scope, origin/destination and effective date. If none exists, add a bounded first-party document import through the existing acquisition/enrichment path; retain raw evidence and actual receipt time.
2. If the old rate is in an earlier instrument, link the two evidenced instrument versions explicitly. Do not label a rate pair inferred from separate documents as a direct extraction from one sentence.
3. Retain the current supported formula and applicability checks. Specify the cost-base convention in the form and export: the existing `(1 + new_rate)/(1 + old_rate) - 1` ratio is relative to the old duty-inclusive component. Do not call its input an untaxed customs value; that would require different arithmetic and a deliberate contract change.
4. User-supplied pass-through and cost base remain hypothetical assumptions. Foreign-jurisdiction direction must be correct: an Indian exporter facing a foreign tariff is not an Indian import-duty scenario.
5. Return named refusal reasons for missing rate, unsupported unit, wrong product, unconfirmed status or date mismatch. Do not add manual “force applicable” controls.

**Acceptance:** in the real browser, produce a supported conditional result, export it, open the downloaded JSON and compare the IDs, rates, units, assumptions and monetary range. Also export a matrix/comparison without a scenario. Check one inapplicable case. Use `verify_news_workflows_browser.py` and the relevant existing role verifier once after the shared payload changes; change scripts only where they fail to assert actual download/content.

**Stop:** one real supported scenario plus honest unsupported cases is enough. No requirement to make every feed event priceable or replace the interpretation engine.

### F06 implementation: real evaluation input and Table C

**Current status:** Stored adapter, independent reconciliation replay, Table C publication and actual 81+81 observation coverage exist. Remaining: one bounded real runner/report acceptance; missing scientific coverage must remain explicit.

**Reuse:** `validation.experiment.Dataset`, `LabelledEpoch`, `Observation`, `run`, existing preregistration verification, transfer/sensitivity tools and `experiment_store`.

1. Add an owned real-data adapter, for example `seraph/validation/datasets.py` (proposed new file). Its interface should be:

   ```text
   from_run_store(run_ids, epoch_definitions, required_modes, cutoff)
     → {dataset, provenance_manifest, coverage_report}
   ```

2. Load actual persisted `ReconciledState`, regime probabilities, timestamps, masks and weight/config IDs. Match labels from the declared epoch definition; do not infer crisis labels from high model scores.
3. Preserve the distinction between missing input data, structurally absent pillars, an uncomputed reconciliation mode and a class-deficient evaluation fold. Do not duplicate Kalman states and relabel them forward-fill to populate both modes.
4. Assert temporal ordering and the engine's existing coverage restrictions. If the archive lacks a supported mode, add a bounded producer from actual pillar vintages using the existing reconciler. Never use fixture observations to complete a real epoch.
5. Extend `run_experiment.py --dataset` with a real stored-run option and explicit run/cutoff arguments; keep `fixture` visibly synthetic. A `--validate-inputs`/dry-read option should report coverage without running expensive calibration.
6. Extend `EvaluationRow.table` to include `C` if the current adopted evaluation design still requires it. Update serialization, table filters, reporting/UI consumers and contract tests together. The experiment archive already supports C; do not create a parallel publication schema.
7. Preserve preregistration verification. If the current design is not yet committed, report that precisely and continue building the adapter. Do not auto-register a changed design after inspecting its results or bypass the gate to finish a test.
8. Render real measured and unavailable cells with provenance in the existing EVALUATION panel. Keep A/B/C interpretation warnings and measured/declared fold counts.

**Acceptance:** validate one real supported slice without a refit; exercise the real adapter into the runner under a valid design; confirm all published table kinds survive serialization and reload. Reuse existing runner tests; add data-adapter bounds and Table C round-trip tests. No demand for a favorable AUC, six fabricated epochs or a full repeated historical experiment.

### F07 implementation: directed measured market network

**Current status:** Estimator, explicit-specification contract, native counts adapter, versioned artifact and regulator graph UI now exist. Remaining: adopt the real diagnostic specification and obtain supported native data. Synthetic direction tests are not a measured market graph.

This package needs a declared scientific mapping as well as engineering. The existing pooled scalar Hawkes estimator cannot produce a sector-by-sector directed branching matrix merely by reshaping its scalar.

**First determine the intended method.** Reconcile the current SPEC/amendment and any existing fitted network artifact. If an adopted full-sample network estimator/artifact exists, use it. If no executable method exists, document a bounded model choice before fitting; do not silently choose a correlation graph and label it Hawkes contagion.

**Proposed engineering contract** in the Hawkes owning package:

```text
NetworkArtifact:
  node_ids and stable order
  matrix with explicit convention: matrix[target, source]
  input interval, fitted_at, available_at, method/config/hash
  eligible observations and missing-sector coverage
  fit status, stationarity/diagnostic fields, limitations
```

**Implementation sequence:**

1. Reuse F04 sector jump streams, binned at the native sampling frequency. Preserve simultaneous events; do not invent sub-bar order to create direction.
2. Implement/load the declared estimator behind `fit_network(counts, timestamps, specification)`. For a proposed discrete multivariate excitation model, the design must specify lag kernel, seasonality, window, sparse-sector rule, constraints and fitting objective in advance. It must identify what constitutes a branching weight and what is only an association. These are model choices, not hidden UI defaults.
3. If adopting a nonnegative geometric excitation formulation, explicitly define lagged source contributions to each target intensity and the integrated-kernel matrix; constrain/check its spectral radius below one for a stationary branching interpretation. Kernel decay, regularization and sample thresholds must come from the recorded design. Do not tune them until an attractive network appears.
4. Save fitted matrix and diagnostics with actual input/model identity. A full-sample retrospective network must not be exposed as knowable before its sample end/availability.
5. Convert nonzero supported off-diagonal entries to graph edges with source/target labels, weight units and evidence. Keep self-excitation accessible as a diagnostic rather than an unexplained cross-sector arrow.
6. Supply the graph to the regulator/institutional surface allowed by the adopted contract. Use a dedicated network panel; keep the original geographic news globe's evidence paths separate. Do not overload country coordinates with sector-network semantics.
7. Add a declared display threshold only for readability, retaining the full matrix and hidden-edge count in details. No top-k padding when the fitted graph is empty.

**Acceptance:** verify direction on a controlled synthetic example explicitly labelled synthetic; exercise the real input path and persist/reopen its honest fitted/zero/insufficient-support outcome; inspect an edge when supported. A generic `not implemented` result or an adapter with no estimator does not complete F07. If the chosen method is not identifiable on available data, record that as a substantive scope/model decision, continue the other packages, and do not manufacture a successful measured graph.

**No scientific success requirement:** a correctly implemented, evidenced model may yield no supported edges. Its status and limitations must make that outcome distinguishable from missing software.

### F08 implementation: macro-policy scenario workflow

**Current status:** Persisted real fitted projection, preprocessing, covariate path and scenario UI now exist. Only lagged RV is fitted. Remaining: intended macro-policy covariates under a documented model, or explicit user-approved scope narrowing; do not silently treat volatility as policy.

**Reuse:** `HamiltonEngine`, `project_xi`, `decision_support.simulate_policy`, `ScenarioStore`, existing role gates.

1. Persist the fitted diagnostic model in a reproducible parameter artifact: parameter vector, regime order, model dimension, covariate names/order/units, intercept treatment, training-only scaling, training end, software/config identity and filtered initial state. Prefer explicit arrays/metadata over loading untrusted pickled objects.
2. Add a load/reconstruction method and verify its transition probabilities match the original fitted engine on the same covariates.
3. Create a macro-path form for the actual model covariates. Each row has an effective session and named values/units. Validate finite values, complete columns, dimensions and an explicit baseline. Reject unsupported variables rather than ignoring them.
4. Transform with the persisted training preprocessing and call existing `project_xi`; use the model's canonical regime order. Display initial assumptions and projected regime probabilities.
5. Pass the projected path to the existing `simulate_policy`. Pin the baseline reconciled state and weight artifact using `ScenarioStore`; persist the macro input, fitted artifact ID, resulting `xi_path`, score path and limitations.
6. Keep this an isolated hypothetical scenario. The standing Hamilton production exclusion is not lifted by making the scenario available. Equal or excluded fusion weights may legitimately leave the score unchanged; show the projected regime path and explain the unchanged score.
7. Reuse save/run/compare/export controls instead of creating a second scenario store. If a new scenario kind is needed, extend its supported-kind contract and dispatcher together; never label a macro scenario a simple rank shock.

**Acceptance:** round-trip a real fitted diagnostic artifact, project one explicitly hypothetical path, save/reopen/compare/export it, and verify no-shock/baseline consistency. Use the existing C11/CT-7 consistency checks for the shared scorer. Causal policy-effectiveness claims and model calibration are outside this engineering acceptance.

### F09 implementation: defensive-action outcome calculator

**Current status:** Calculator, benchmark-backed request, executor and charts are implemented. A read-only 37-observation actual-price calculation succeeds. Remaining: one saved scenario run/reopen/export journey; options/futures data are not required to demonstrate the supported notional cash-reduction case.

**Required deliverable:** baseline and supported defensive action wealth paths over a labelled historical epoch, with realised drawdown differences and assumptions. A recommendation sentence alone is insufficient.

**Proposed owned module:** `seraph/decision_support/defensive.py`; reuse scenario artifacts and the existing playbook presentation.

1. Define a request containing epoch/window, positions and weights, valuation currency, evidence-backed price-series references, decision/execution timing, supported action and explicit transaction/carry assumptions.
2. Implement a minimal first action supported by available data: a declared reduction of risky exposure into cash, or sector rotation when both sector return series are present. Supply weights/costs through the scenario inputs; do not hide a default that creates a favorable outcome.
3. Apply the action no earlier than the declared executable price after the decision. Maintain holdings/cash and cash flows through the window. Define buy-and-hold versus rebalancing explicitly and use the same convention for baseline and action.
4. Compute wealth and drawdown:

   ```text
   running_peak[t] = max(wealth[0..t])
   drawdown[t] = 1 - wealth[t] / running_peak[t]
   maximum_drawdown = max(drawdown)
   reduction_percentage_points = 100 × (baseline_MDD - action_MDD)
   ```

   Keep relative percentage improvement separate, and undefined when baseline drawdown is zero. Negative reductions are retained.

5. Add hedge-ratio adjustment and index-put overlay only with an explicit supported instrument price path and its costs. A market-index line is not an option-price history. Do not mark the entire original FR46 action family complete when only one action has been implemented; record each supported/unsupported action.
6. Make the engine accept valid supplied instrument histories so functionality is not permanently tied to one external vendor. Clearly labelled scenario/test histories can verify arithmetic but cannot support a claim of real historical action performance.
7. Display baseline/action paths, maximum drawdowns, reduction in percentage points, action/execution dates and cost assumptions. Save/export with the evidence/input hashes.
8. Distinguish an ex-post “best among evaluated actions” from an implementable ex-ante recommendation. Never use the best action selected after seeing the epoch to claim prospective strategy returns.

**Acceptance:** a no-op reproduces the baseline; a supported real historical action reconciles positions/costs/wealth; a worse action stays worse; insufficient option data yields an explicit unsupported result. At least the required action paths must have implemented calculators before declaring full FR46 engineering complete. Missing market data may limit measured examples; it does not excuse omitting their interfaces/valuation logic.

### F10 implementation: institution submissions and decomposition

**Current status:** The bounded institution holdings workflow is implemented; saved tests verify totals, revisions, cutoffs and role denials. Remaining: one UI import/reopen/export rehearsal. Treat the implementation list below as the retained contract, not a new feature backlog.

**Reuse:** `WorkspaceStore` import/preview patterns, identity/grants, normalized holdings, `portfolio_overlay`, news exposure trails and the regulator gateway.

1. Define a versioned institution submission with `institution_id`, submitter/owner scope, effective and received timestamps, base currency, positions, valuation basis, source/demo flag, revision and content hash.
2. Reuse holdings parsing; validate required institution identity, duplicate positions, finite values, supported currency/basis and consistent totals. A mixed-currency total requires a dated FX conversion source; otherwise keep currency totals separate.
3. Persist accepted submissions and their revisions in an owned store/table. Record rejection details without partially accepting an ambiguous book. Do not allow a browser role string to authorize reading another institution's submission.
4. Implement decomposition at a requested cutoff:

   ```text
   select eligible submission version per institution
   → normalize holdings once
   → aggregate value and portfolio share by institution/sector
   → attach measured flag coverage and optional news linkage separately
   → report known / unsized / unmapped amounts and totals
   ```

5. Do not call an institution's market-value share a loss contribution or a CSRS Shapley contribution. Those require a different propagation model. Preserve the three-pillar Shapley values in their existing meaning.
6. Populate `institutionDecomposition` in the server-projected regulator view with table, totals, coverage and source labels. Non-regulator payloads must omit restricted institution records before transmission.
7. Add regulator controls to import/preview/select submissions and inspect aggregate/detail rows. Add an export using the same evidence/provenance conventions. Reuse existing case evidence references when applicable; no new case-management system.
8. Use two clearly labelled demonstration institutions with user-supplied/demo holdings for the workflow demonstration if private real submissions are unavailable. Their numbers must never appear as observations about actual institutions.

**Acceptance:** totals reconcile from holdings to sectors to institutions; effective-date revision selection works; unauthorized roles cannot read/export restricted data; import, reopen and regulator display work in one browser journey. Real institutional loss prediction is outside this feature's engineering claim.

### P3. Focused validation and evidence plan

Reuse existing passing evidence. Run only checks that resolve the retained completion conditions; do not rerun this entire matrix routinely.

| Slice | Reuse first | Remaining material check |
|---|---|---|
| F01 | Existing Python/JS contract checks and news-browser evidence | One combined actual console/backtest/flow/role/globe rehearsal. |
| F02 | Runtime/engine XML and ordinary market-job log | Real registered input readiness, current publication and owned startup/shutdown. |
| F03 | Matching actual ledger/state and issuance evidence | Existing displayed ID during final rehearsal; no new issuance run needed solely for test count. |
| F04 | Sector producer/artifact and portfolio checks | Supported native input yields a covered sector and matching portfolio/news coverage. |
| F05 | Historical priced download and cited cached document | Preserve labels/assumptions during final rehearsal; do not require another historical example. |
| F06 | Two-mode 81+81 real coverage and Table C tests | One bounded real runner/report output with truthful unsupported cells. |
| F07 | Synthetic direction/stationarity tests and declared design | Supported real input and adopted specification reach artifact/graph, or substantive unidentifiability is documented. |
| F08 | Actual policy fit and scenario implementation complete; browser acceptance pending | Complete one save/run/reopen/export journey with the fitted RBI repo artifact; retain retrospective and exclusion labels. |
| F09 | Complete for bounded observed-index hypothetical comparison | Preserve browser-13 reopened result/history and download; no additional feature work. |
| F10 | Complete for bounded institution holdings workflow | Preserve institution-browser-01 passing reopen/export/role evidence; no additional feature work. |

For each package, record:

```text
package and acceptance criterion
commit plus hash of relevant uncommitted files, if any
mode: real observation / historical replay / hypothetical / synthetic test
input IDs, source/effective/received dates and artifact hashes
command or browser actions actually executed
observed result and expected result
persisted output/download/screenshot location
remaining input limitation, if any
```

Use `docs/evidence/engineering-closeout-2026-10-20/` as a proposed common evidence directory, or the already active equivalent if another session owns one. Do not overwrite earlier evidence. A synthetic test can close an arithmetic regression; it cannot establish a successful real current-data journey.

Run the relevant existing invariant checks after changes to shared computation/transport contracts. Run the full suite once near final integration if its relevant code has changed; reuse that result until another relevant change warrants a rerun. Do not automatically rerun expensive model fitting or full historical replay after every UI change.

### P4. Final acceptance and completion accounting

The final demo must exercise the real user-facing application, not just direct calls to helper functions. Use the eight journeys in the audit's acceptance section, with these clarifications:

- Where the feature promises live/current operation, a historical replay is supporting evidence only; it does not close that requirement.
- A supported but scientifically negative result is valid: no warning, no demonstrated edge, no effective defensive action, or a genuinely unsupported network estimate can be shown honestly.
- An absent calculator, disconnected control, always-empty placeholder or permanently rejected valid input is still incomplete engineering.
- A transient external source outage is not automatically a code defect. The bounded failure behavior and freshness disclosure must work, and the successful path needs applicable evidence.
- If only part of an originally required action/model family is implemented, explicitly retain that sub-item as incomplete. Do not silently narrow the denominator to declare completion.

Close F01–F10 only against their written criteria. Then reconcile the 42-row inventory and issue one updated overall engineering assessment using the same responsibility weights. The earlier 80%/84%/90%/92% and current approximate 95% are dated assessments, not quotas; do not derive 100% from an unrelated test total.

**Freeze rule:** no further feature work after all retained package criteria and the final demonstration pass. New work requires either a reproducible major failure of an agreed journey or an explicit user request to expand scope. Keep scientific model improvement as a separate workstream.

### P5. Implementation handoff prompt

The following can be given to the implementation agent. It does not authorize implementation during the current planning-only edit.

> Work directly in `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`. Implement the technical plan in `docs/SERAPH-OVERALL-ENGINEERING-COMPLETION-AUDIT-2026-10-20.md`, starting with its newer planning baseline rather than blindly repeating the historical audit findings. Preserve all existing uncommitted work, the original Hawkes/RMT/Hamilton families, scientific exclusions, preregistered evaluation and frozen evidence. Do not push.
>
> First inspect current status and ownership of overlapping files. Reuse all now-present analytical modules, writers and UI paths. F05 is complete for its bounded historical example; F04/F07 primarily need supported inputs/design, F08 still lacks fitted policy covariates, and F06/F09 need their bounded acceptance. Do not rewrite completed modules. Complete only the remaining implementation and acceptance in F01–F10 sequentially in the specified dependency order, splitting the independent export and portfolio activation slices as described. Use the existing stores, contracts, engines and UI. Do not replace the application or create a second version.
>
> For each package, implement its missing behavior, run the targeted acceptance checks, and record evidence. Do not stop after writing backend functions when the feature requires UI integration. Do not claim a live feature is complete from a fixture, historical import or an unavailable message. Preserve missing-data/refusal behavior; do not invent measured values or change scientific assumptions silently.
>
> Use declared scenario inputs for ordinary user-controlled assumptions. If a real credential, unavailable source, incompatible concurrent edit or unresolved scientific definition blocks one package, name the exact dependency, complete all independent work, and return a concrete bounded question when necessary. Do not wait on that blocker while unrelated packages remain actionable. Do not bypass authorization, overwrite another session's work, or manufacture evidence.
>
> Avoid broad refactoring, new source-count targets, UI redesign, test-count goals and repeated full-suite/model runs. The finish line is the ten package criteria plus one actual application rehearsal, not perfection. Finish by updating their status/evidence, the 42-feature inventory and the overall engineering assessment, and state exactly what still depends on external inputs or science.
