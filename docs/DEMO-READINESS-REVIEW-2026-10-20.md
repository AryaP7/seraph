# SERAPH development and demo readiness review — 20 October 2026

**Verdict: substantial implementation, but not ready for a demonstration of all features.** A limited research demonstration is possible. The current embedded console has a reproduced rendering failure that should be fixed before a normal walkthrough.

On the project's existing 42-feature scope, this review assigns **28 complete, 12 partial or blocked, and 2 absent**: **66.7% of feature units complete**, or **81.0% implementation progress** when partial units receive half credit. This is an explicit planning estimate, not a measurement of hours remaining, scientific validity, or production readiness.

The scope is unchanged from the [19 October checklist](SERAPH-FEATURE-COMPLETION-CHECKLIST-2026-10-19.md). It excludes commercial multi-user deployment, universal news coverage, and achievement of predictive-performance targets. These percentages therefore must not be presented as completion of every original FR/NFR. The [42-row assessment](evidence/demo-readiness-2026-10-20/feature-assessment.json) contains each decision and its original acceptance criterion.

| Area | Complete | Partial / blocked | Absent | Progress with half credit |
|---|---:|---:|---:|---:|
| Core data, models, runtime and evaluation | 11 | 3 | 1 | 83.3% |
| Console and user workflows | 7 | 7 | 1 | 70.0% |
| News capabilities | 10 | 2 | 0 | 91.7% |
| Total | 28 | 12 | 2 | 81.0% |

The news percentage describes implemented capabilities, not source freshness, extraction accuracy, comprehensive coverage, or a successful current browser walkthrough. The shared console regression is counted under U01/U02 rather than deducted again from every downstream feature.

## What was actually checked

Read the Astra baseline/amendments, objectives and component contracts; inspected the fixed feature register, current implementation/callers, launchers, scheduler, CI and prior evidence; ran the broad test suite and focused checks; queried the research PostgreSQL using a read-only transaction; inspected production SQLite through read-only connections; exercised supported verification functions against copied runtime stores; and launched headless Edge against isolated store copies.

Browser acquisition was disabled deliberately so the audit did not initiate external fetching or alter source stores. The browser used normal Streamlit component messaging and real saved inputs, without injecting a replacement payload. Its owned processes were stopped afterward. No application code, model parameters, original results or production records were edited by this review.

**The checkout was changing concurrently.** HEAD moved from `8c9bd0f` to `f7be092`, and runtime/producer tests changed during execution. A focused recheck covers the newly added acquisition tests; evidence is a set of timestamped observations, not certification of one immutable release. A [source manifest](evidence/demo-readiness-2026-10-20/source-manifest.json) records hashes for 385 source/test/assets files at capture.

## Immediate demo blocker: the console does not finish binding its real payload

The real browser repeatedly reported:

```text
TypeError: history.forEach is not a function
    at spark (bridge.js:132)
    at renderConsole (bridge.js:139)
    at ... bridge.js:641
```

The backend's [`project_run`](../seraph/dashboard/console_backend.py) now supplies `history=_history_with_benchmark(...)`, an **object** carrying rows, labels and coverage. The frontend's [`spark`](../seraph/dashboard/console_component/bridge.js) still calls `history.forEach(...)` as though it were an **array**.

This throws before the render handler updates the run banner and applies the real news layers. The outer prediction panel renders, but the embedded console remains on its labelled fabricated preview. Waiting 90 seconds did not resolve it. There were no Streamlit Python exceptions; the failure is in JavaScript.

Evidence: [browser error and page text](evidence/demo-readiness-2026-10-20/browser.json), [screenshot](evidence/demo-readiness-2026-10-20/browser.png), [longer second attempt](evidence/demo-readiness-2026-10-20/browser-second-attempt.json), and [reproducible probe](evidence/demo-readiness-2026-10-20/browser_probe.py).

**Required repair:** agree on the history payload and update both console/backtest consumers. Render the official benchmark series with its units and missing periods. Passing only the array of CSRS rows would stop the exception but would not finish the benchmark feature. Then rerun the actual browser using a backend-produced payload and traverse all three roles.

The existing JavaScript harness supplies `history: [{date, csrs}]` at `tests/js/bridge_harness.mjs:163`. Backend benchmark tests check the new object's rows independently. Both halves can pass while disagreeing about the actual interface. A regression test should pass the actual backend payload through the renderer.

## Important gaps behind the headline percentages

| Finding | Current evidence | Demo implication |
|---|---|---|
| Current three-pillar runtime is not demonstrated | `intraday_bars=0`; original Hamilton is explicitly excluded; only one saved runtime decision, a withheld historical replay. Daily RMT and the separate Astra prediction path exist. | Do not present the historical console or Astra variants as the fully operating original live three-pillar system. |
| New forecasts are not reaching the durable ledger | Prediction state is dated **2026-10-19**, but the ledger has **14 rows, all as of 2026-08-21**, first issued on 2026-10-19. `run_forecast.py` reads saved experiment predictions; the operational prediction job writes a separate state file. | A working current probability panel is not yet a demonstrated ongoing prospective forecast record. Reissuing old predictions after their horizon is not prospective validation. |
| Flow frontend still uses examples | Backend `market_flow()` returns a real 2026-10-19 record. `bridge.js` still prints FII `-1200`, DII `900`, residual share `0.72` as fabricated examples and does not consume `data.flow`. | The runbook's claim of a completed real flow display is ahead of the frontend. Historical dates without a matching record must show absence. |
| News operations are unhealthy at capture | 19 sources: **5 healthy, 13 stale, 1 failing**. `news.poll` reports three abandoned leases since its last successful run. | Saved-news inspection is possible after the console repair; a fresh-news demonstration needs a successful acquisition rehearsal and visible source status. These are captured operational conditions, not permanent publisher judgements. |
| Measured sector/network outputs missing | Sector flags are unavailable in the archive path; Hawkes detail emits an empty branching matrix. | News exposure arcs do not demonstrate a measured Hawkes contagion network or portfolio sector-risk overlay. |
| Macro-policy simulation incomplete | UI supports a hypothetical regime-probability path; no connected persisted fitted macro-covariate-to-regime mapping. `macro_covariates=0` in the research database. | Demonstrate rank shocks or declared regime paths, not a completed macro-policy counterfactual. |
| Defensive drawdown and institution exposure unavailable | Playbook deliberately returns no measured drawdown reduction; no authorised institution position dataset/decomposition journey. | These cannot be shown as working measured outputs. |
| News numerical scenario and export incomplete | Scenario machinery can refuse unsupported rate/applicability inputs; no fresh successful priced example was established. Export sends empty arguments, and the component displays JSON without a complete downloadable scenario/matrix export. | Backend functions and buttons are not completion of these end-to-end journeys. |
| Original evaluation results incomplete | Experiment runner/sensitivity/transfer/archive code exists and is tested; committed preregistration and full real epoch inputs are absent. Public `EvaluationRow` still accepts only A/B, while the archive supports C. | The runner and its refusals are demonstrable; full original real-data ablation/transfer results are not. |
| Scientific acceptance remains unmet | Original results and the current prediction panel explicitly retain the unvalidated status. | No claim of dependable advance crisis prediction, calibrated financial advice or validated news interpretation. |

The runtime code gained a deployment-registry repair during this audit. Its targeted tests passed on recheck, but this does not create a saved live decision or remove the intraday/Hamilton limitations above.

## What is substantially built and worth demonstrating

- **Data foundation:** 7,489,028 daily rows, latest date 2026-10-19; 43 universe snapshots. Fresh NSE EOD acquisition now re-flags the universe and rebuilds the operational snapshot.
- **Three model families and research pipeline:** implemented Hawkes, RMT and Hamilton calculations, reconciliation, fusion, uncertainty, attribution, historical forecasts, baseline comparisons and retained negative results.
- **Current experimental prediction panel:** browser showed the 2026-10-19 decision, 6.23% estimated probability, 12.52% threshold and “NO WARNING,” with its unvalidated banner. These are captured model outputs, not endorsed risk estimates.
- **Durable user workflows:** portfolio CSV validation/history/watchlists, stored scenarios and comparisons/reviews/exports, regulator case lifecycle and evidence export are connected in the separate Streamlit workspace and have passing dispatcher/UI tests. A complete current browser click-through was not achieved because of the console blocker.
- **News backend and saved evidence:** 19 source registrations, 2,796 story rows and 38 document-cache rows at the read-only census. Acquisition, extraction, evidence links, qualitative exposure mechanisms and role projections exist. Counts do not measure accuracy or breadth.
- **Operations and packaging:** a registered/enabled daily task, market/news launcher integration, health reporting, durable replay/recovery code, and previously recorded installed-wheel verification.

The separate Astra prediction variants use daily-tail Hawkes, portfolio-based RMT and a variance Hamilton model. Their working panel does not remove the standing limitations of the original intraday/TVTP implementations.

## Verification results and their limits

- **Broad core suite:** 2,437 passed, 14 skipped, zero failures, 467.81 seconds. Skips include disposable-database/corpus-dependent checks. [JUnit](evidence/demo-readiness-2026-10-20/core-tests.xml) · [log](evidence/demo-readiness-2026-10-20/core-tests.log).
- **New acquisition/runtime changes:** a first focused run encountered seven test-fixture signature errors while the file was being edited externally; after those edits, the acquisition module reran at **54 passed, 1 skipped**. The live NSE test is intentionally opt-in. Preserve both outcomes; do not count duplicate tests as additional coverage. [First focused run](evidence/demo-readiness-2026-10-20/latest-changes-tests.xml) · [recheck](evidence/demo-readiness-2026-10-20/acquisition-recheck.xml).
- **Hamilton/policy partition:** see the separate [model test log](evidence/demo-readiness-2026-10-20/model-tests.log); its final result is recorded below when the run completes.
- **Mechanical invariants:** all checker checks returned OK; its frozen-type audit is informational rather than proof of every readonly contract.
- **Research-artifact verifier:** passed data/code/output hash checks and exact saved prediction/feature replication checks. This verifies the frozen research artifacts, not scientific success.
- **Functional verifier:** all 11 selected checks passed against copied runtime state/read-only source data. This is a deliberately narrow denominator. The composite demonstration uses synthetic warm-start values; the packaging check reads prior packaging evidence; the flow check exercises a backend reader, not the frontend. None supersedes the observed browser failure.
- **Browser:** prediction and outer Streamlit page rendered; real embedded-console payload failed. Consequently the all-role/all-feature browser acceptance gate is **not passed**.

Read-only data counts, forecast timestamps, health and prediction details are saved in [runtime.json](evidence/demo-readiness-2026-10-20/runtime.json). The [probe](evidence/demo-readiness-2026-10-20/probe.py) documents how the isolated checks were performed.

## Demo decision and completion order

**All-features demonstration today: no.** **Limited experimental/research demonstration: possible, with the console issue disclosed; preferable after fixing it.**

1. Repair the history/benchmark frontend contract and verify real payload rendering across every role and tab.
2. Connect the actual flow payload; verify which surfaces are historical, current, unavailable or previews.
3. Connect current operational forecasts to an immutable issue/settlement ledger and prove a new date survives restart without duplication.
4. Rehearse news acquisition, source failures, scenario output and actual export download on a clean demo copy.
5. Choose a finite demo scope for the missing original-live, sector/network, macro-policy, defensive-action and institution features. Implement them with the required inputs, or mark them explicitly outside the demonstration.
6. Freeze the exact code/data snapshot and run the acceptance walkthrough again. Keep scientific claims restricted to the measured evidence.

An appropriate demo sequence after the console repair is: current experimental prediction and caveat → historical CSRS/pillars/uncertainty → portfolio import/history → saved scenario → regulator case → sourced news/evidence → health/provenance. Showing an honest absence/refusal can explain system design, but does not make the missing feature complete.
