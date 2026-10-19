# SERAPH — audit and implementation TODO

Created 17 October 2026. Working repository: `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`.

This is the consolidated implementation backlog from the news audit, the first logic audit and the additional tick/portfolio audit. **41 open tasks: 20 logic defects, 6 integration gaps, 15 news tasks.** It is not a claim that these are every remaining project defect. All checkboxes are initially unchecked; no fixes were implemented as part of creating this document.

## Rules and evidence

- Preserve Hawkes, RMT and Hamilton, preregistered evaluation, existing uncommitted changes, historical evidence and explicitly labelled fabricated previews. No commit/push without the owner's instruction.
- Establish current ownership and inspect files before implementation; other sessions may have changed them since this audit. Line numbers below identify the inspected version, not a permanent location.
- **Reproduced** means a bounded counterexample was executed; **code-confirmed** means source/caller inspection establishes the issue but the full workflow was not executed; **gap** means missing integration, coverage or validation, not necessarily incorrect existing arithmetic.
- Priority **P1**: resolve before relying on the affected workflow. **P2**: narrower/dormant issue or later capability. A conditional failure is not proof that production data was already corrupted.
- Mark an item done only after its acceptance checks pass and its evidence is recorded. A helper test alone does not close an integration ticket.
- Run focused regressions for changes; do not rerun expensive market fits or historical evaluations without a dependency-based reason. Changes to scientific assumptions require explicit explanation and authorization; do not weaken evaluation to improve results.
- Unknown values, absent exposure, stale sources and unavailable inputs must stay unknown/unavailable, not become zeros or healthy states.

Detailed first audit: `evidence/logic-audit-2026-10-17/SERAPH-IMPLEMENTATION-LOGIC-AUDIT-2026-10-17.md`.

Executable audit probes and captured outputs: `evidence/logic-audit-2026-10-17/seraph_logic_audit_probe.py`, `seraph_logic_audit_evidence.jsonl`, `seraph_logic_audit_probe_extra.py`, `seraph_logic_audit_evidence_extra.jsonl`. These are counterexamples, not a test-suite pass report. They use disposable stores and no model fits. Copy the relevant cases into proper regression tests during repair; update the probes if interfaces change.

News source of requirements: `SERAPH-NEWS-INTELLIGENCE-DEVELOPMENT-PLAN-2026-10-17.md`; prior progress: `NEWS-INTELLIGENCE-IMPLEMENTATION.md`. Local scripts contain an explicit repository path and will need adjustment on another machine.

## Recommended order

1. Market input integrity: L13–L15, then runtime cutoff/warmup/ordering L01–L03.
2. Runtime durability: L04–L06, L09 and G06. Freeze the revised contracts before wiring producers.
3. Runtime visibility: L07–L08 and G02–G03/G05; connect real producers G01 and measured flags G04.
4. Portfolio integrity: L16–L20; scenario versioning/reviews L10–L11. These can be done sequentially without another agent.
5. News operations N01–N05, causal semantics N09/N11, then document/coverage/exposure work N06–N10 and role integrations N13.
6. Label benchmark data early; complete N12 before selecting optional extractors N14 or claiming interpretation accuracy. N15 is a separately governed research extension.
7. Deprecate or repair the legacy metric L12 without rewriting saved research results.

## A. Previously identified logic defects

- [ ] **L01 — P1 — Reconcile live decision cutoff with actual receipt/computation time.**
  - Evidence: reproduced availability predicate and code-confirmed caller mismatch. `live/loop.py:192,226`, `live/engine_adapter.py:126`, `live/publication.py:InputProvenance.reasons` under `seraph/`.
  - Defect: bar close is the cutoff but receipt is the later poll time; one second of normal delay yields `not_known_at_cutoff`.
  - Implement: distinct bar-end, receipt, emission-availability and decision timestamps. Preserve actual receipt provenance; decide only after information becomes available. Do not backdate inputs.
  - Dependencies: specify the timestamp contract first; coordinate with G01/G06.
  - Acceptance: normal delayed receipt works for a later decision and remains excluded from an earlier one, through the real loop and producer adapter.

- [ ] **L02 — P1 — Initialize the filter consistently during warm start.**
  - Evidence: reproduced; `seraph/live/inference.py:442–462`. ECDF/history loads and `_assimilated` advances without a Kalman update; next decision can have eligible data but no score.
  - Implement: choose explicit ECDF-only versus complete filter warm start; do not claim filter assimilation that never occurred. Check deployment eligibility during warm start.
  - Dependencies: L01 information availability contract.
  - Acceptance: warm start followed by no new daily vintage produces the intended carried state at its true age, with no duplicate standardizer insertion.

- [ ] **L03 — P1 — Prevent older deliveries from replacing the latest pillar vintage.**
  - Evidence: reproduced; `seraph/live/inference.py:530`. Delayed 09:20 replaces service latest 09:55 while C8 retains 09:55.
  - Implement: cross-batch monotonic ordering and explicit correction/revision rules; retain old delivery history without regressing current provenance.
  - Dependencies: L01; coordinate identity with L05.
  - Acceptance: reordered and duplicated inputs converge to the ordered state and consistent provenance; genuine corrections remain representable.

- [ ] **L04 — P1 — Bind checkpoints to effective model/runtime configuration.**
  - Evidence: reproduced; `seraph/live/inference.py:707–750`. Checkpoint from `q_proc=.001` restores into `.9` with unchanged immediate snapshot ID.
  - Implement: validate canonical fingerprints for weights, process/noise parameters, standardizer policy, session windows, deployment/model identity; include complete assimilation/rank state.
  - Dependencies: define versioned checkpoint migration/refusal policy first.
  - Acceptance: mismatches refuse before state mutation; same configuration reproduces both numerics and diagnostics after restart, including split sessions.

- [ ] **L05 — P1 — Reject conflicting contents under an existing decision ID.**
  - Evidence: reproduced; `seraph/live/store.py:379`. Different score/publication status returns the old record as successful replay.
  - Implement: compare canonical immutable decision/input identity atomically; only exact repeats are idempotent. Separate attempt metadata where needed.
  - Dependencies: L01/L03 identity conventions; coordinate L06.
  - Acceptance: identical replay succeeds; conflicting replay fails without mutation; concurrent identical submissions remain safe.

- [ ] **L06 — P1 — Scope stored decisions and reads to their runtime stream.**
  - Evidence: reproduced; `seraph/live/store.py:448`. A second empty stream reads the first stream's score.
  - Implement: either enforce one stream per database explicitly or scope decision IDs, reads, checkpoints and outbox consistently. Document schema effects before migration.
  - Dependencies: L05; migration tested on a copy.
  - Acceptance: separate stream heads and results never cross; existing single-stream data remains readable.

- [ ] **L07 — P1 — Enforce score freshness independently of worker health.**
  - Evidence: reproduced API state; `seraph/dashboard/current_reader.py:124,154`, caller `prototype_app.py:92`. A seven-day-old score and fresh head returns `is_current=true` with the default.
  - Implement: mandatory explicit calendar-aware score-age policy; separate closed-market last-known reading from current open-session output.
  - Dependencies: L01 and G05.
  - Acceptance: a recent heartbeat or delayed commit cannot renew an old score's freshness.

- [ ] **L08 — P1 — Render the scalar inside the live CSRS envelope.**
  - Evidence: reproduced Streamlit boundary; `seraph/dashboard/prototype_app.py:101`, `seraph/live/loop.py:LiveDecision`, `scripts/run_live.py:commit`.
  - Defect: a CSRS dictionary is passed to a numeric metric, raising `StreamlitInvalidParameterTypeError`.
  - Implement: typed payload projection to scalar plus explicit missing/withheld handling.
  - Dependencies: none for the projection repair.
  - Acceptance: ordinary UI renders persisted non-null, withheld and absent scores without payload injection or a crash.

- [ ] **L09 — P1 — Fence expired job writers and renew live leases.**
  - Evidence: reproduced; `seraph/operations/jobs.py:118,153,166`. Lock belongs to new worker while old worker overwrites its checkpoint.
  - Implement: renewable leases and monotonically increasing fencing tokens checked on protected writes/clears; ownership-scoped progress cleanup.
  - Dependencies: enumerate every mutation protected by the job lease; database migration if required.
  - Acceptance: expired worker cannot checkpoint, clear successor state or commit protected output after takeover.

- [ ] **L10 — P1 — Persist immutable scenario inputs and assumption revisions.**
  - Evidence: code-confirmed; `seraph/decision_support/scenarios.py:110,162–196`. Old assumptions are overwritten; run stores a hash without recoverable input/assumption content.
  - Implement: immutable revisions and canonical run inputs, baseline, steps and engine identity; link runs to exact revisions.
  - Dependencies: additive scenario schema and read compatibility; coordinate L11.
  - Acceptance: reconstruct the first run after multiple edits using only persisted records.

- [ ] **L11 — P1 — Bind reviews to the precise scenario/run revision.**
  - Evidence: code-confirmed; `seraph/decision_support/scenarios.py:116,202`. Reviews attach to mutable scenario ID only.
  - Implement: content/revision-scoped approval, stale-review presentation after changes and explicit review history.
  - Dependencies: L10.
  - Acceptance: approval for revision 1 cannot appear as approval for revision 2; reviewer and exact reviewed content remain retrievable.

- [ ] **L12 — P2 — Quarantine or repair legacy lead-time calculation.**
  - Evidence: reproduced; `seraph/validation/harness.py:60–74`. Isolated early crossing is credited to a later onset without the documented sustained-warning rule or bounded matching.
  - Implement: deprecate if unused, otherwise use an explicitly approved event/episode matching policy. Do not silently alter preregistered definitions.
  - Dependencies: confirm callers before change. Search found tests but no production caller in `seraph`/`scripts`; Astra has a different evaluator.
  - Acceptance: unmatched old alarms do not earn credit; misses/unassessable cases stay distinct. Preserve prior research evidence.

## B. Additional defects found in this pass

- [ ] **L13 — P1 — Stop using price as tick chronology.**
  - Evidence: reproduced; `seraph/live/bars.py:163,196`. Two ticks at the same timestamp, price 100 then 99 and cumulative volume 100 then 101: only the first is accepted. The valid falling-price tick is labelled out-of-order; close and low remain 100.
  - Implement: separate dedup identity from event ordering. Prefer provider sequence; otherwise define stable receipt order/timestamp tie handling and retain ambiguity explicitly. Price magnitude must not decide temporal order.
  - Dependencies: tick transport/version contract; review provider timestamp precision.
  - Acceptance: rising and falling same-timestamp ticks are handled symmetrically; replay follows the same documented order and produces correct OHLC. Duplicate detection still works.

- [ ] **L14 — P1 — Preserve duplicate/order state across bar-builder restart.**
  - Evidence: reproduced; `seraph/live/bars.py:284,306`. Snapshot omits `seen_keys` and `last_order_key`. Repeating an already accepted tick yields 1 tick uninterrupted versus 2 after restore.
  - Implement: persist necessary ordering/dedup state, or reconstruct it from a durable event cursor with a proven replay rule. Version the snapshot.
  - Dependencies: L13 and G06.
  - Acceptance: restart in an open bar plus duplicated/reordered receipts produces the same tick count, OHLC, volume quality and finalization as uninterrupted processing.

- [ ] **L15 — P1 — Reject non-finite quotes before they enter bars.**
  - Evidence: reproduced; `seraph/live/feed.py:53`. `last_price <= 0` admits NaN and positive infinity; both reach bar close values.
  - Implement: finite positive price validation at Tick and provider boundaries; validate time, symbol and cumulative-volume domain. Quarantine/report malformed provider messages without losing valid surrounding messages.
  - Dependencies: none; coordinate transport errors with L13.
  - Acceptance: NaN/infinity/invalid volume and timestamps cannot poison OHLC or derived features; failures are observable and finite valid quotes survive.

- [ ] **L16 — P1 — Validate portfolio numeric inputs and computed values.**
  - Evidence: reproduced; `seraph/decision_support/workspace.py:221,249`. Quantity 2 and price -10 is accepted as value -20 because negativity is checked before computation. Text `NaN` is accepted as value and makes the total NaN.
  - Implement: finite-number validation, price-domain validation and post-computation/merge validation, including overflow and coherent cash rules.
  - Dependencies: none; coordinate L19 unvalued semantics.
  - Acceptance: negative implied long-only values, NaN/infinity and overflow are rejected with row-level reasons; accepted totals are finite and nonnegative.

- [ ] **L17 — P1 — Refuse conflicting metadata when merging holdings.**
  - Evidence: reproduced; `seraph/decision_support/workspace.py:174–196`. Same symbol with sectors steel/IT merges silently and selects whichever appears first. Reversing the upload reverses sector attribution.
  - Implement: define position identity (instrument/account where appropriate); reject or explicitly resolve conflicting sector/ISIN/currency metadata. Preserve lot/account lineage instead of taking the first field silently.
  - Dependencies: portfolio import schema/identity contract.
  - Acceptance: row reordering cannot change economic classification; conflicting assignments are surfaced and consistent lots merge reproducibly.

- [ ] **L18 — P1 — Exclude future-effective holdings from current positions.**
  - Evidence: reproduced; `seraph/decision_support/workspace.py:381,481`. An import effective in 2099 is accepted and immediately returned with `basis='current'`.
  - Implement: normalize/validate aware timestamps, define whether scheduled imports are permitted, and bound current reads by an explicit current cutoff. Keep scheduled records separate.
  - Dependencies: define valid-time versus recorded-time query semantics. Do not confuse a reconstructed historical portfolio with an as-known historical portfolio.
  - Acceptance: future snapshots never replace current holdings prematurely; invalid/naive timestamps fail; equivalent offsets have consistent ordering.

- [ ] **L19 — P1 — Preserve unvalued holdings rather than converting them to zero.**
  - Evidence: reproduced; `seraph/decision_support/workspace.py:104,122,495`. Quantity-only import warns that value is unknown, but stored read returns `value=0.0` with no valuation-coverage field.
  - Implement: retain null value and explicit valuation status through import, storage, totals and exposure adapters. Report known subtotal and unvalued positions separately; block full-portfolio percentages when their denominator is unknown or clearly limit them to the valued subset.
  - Dependencies: L16; coordinate portfolio overlay/API consumers and G04.
  - Acceptance: a portfolio with one priced and one unpriced position cannot imply full valuation coverage or silently assign zero exposure to the unpriced holding.

- [ ] **L20 — P1 — Bind committed holdings to the validated upload and portfolio.**
  - Evidence: reproduced; `seraph/decision_support/workspace.py:389–412`. Altering `preview.accepted` from value 100 to 999 passes the raw-byte hash check; original bytes still say 100 while saved holdings say 999.
  - Implement: reparse/revalidate raw bytes server-side against the target portfolio, or store immutable server-owned preview content bound to source hash, parser version, portfolio/currency and authenticated actor. Do not trust a caller-supplied mutable preview as evidence.
  - Dependencies: L16–L19 import semantics; review commit-boundary authorization separately.
  - Acceptance: mutated previews, cross-portfolio/base-currency previews and stale parser versions are rejected or recomputed; original bytes and persisted canonical rows reconcile.

## C. Integration and operational completion

- [ ] **G01 — P1 — Replace the stock launcher's NullProducers with actual pillar production.**
  - Gap: `scripts/run_live.py:87` attaches the engine with `NullProducers`; broker connectivity alone cannot supply three-pillar outputs.
  - Implement: bar/features/pillar adapters, deployment/fit availability, warmup and declared cadence, preserving all three pillar families and explicit absence states.
  - Dependencies: L01–L06, L13–L15, G06.
  - Acceptance: normal entry point consumes a controlled feed through actual producers into persisted decisions; separately verify authorized live feed and clearly label replay fixtures.

- [ ] **G02 — P1 — Wire independent live UI polling.**
  - Gap: `prototype_app.py:33` declares `LIVE_POLL_SECONDS=2.0` without scheduling it. Current-news refresh can incidentally refresh the live panel every 30 seconds; historical-news mode does not.
  - Implement: real live revision polling with stable component state, deliberate handling of in-progress edits, and wall-clock freshness reevaluation even if no new revision arrives.
  - Dependencies: L07–L08/G05.
  - Acceptance: idle live panel changes on new output and becomes stale on time without user interaction or dependence on news mode; forms/camera are preserved.

- [ ] **G03 — P1 — Make the live panel independent of an archive database.**
  - Gap: `prototype_app.py:124` returns before `live_panel` if the archive store is absent.
  - Implement: independent live/replay availability branches and clear empty states.
  - Dependencies: L08.
  - Acceptance: valid live-only store opens; archive-only and empty installations remain honest and usable.

- [ ] **G04 — P1 — Connect measured sector flags to portfolio exposure.**
  - Gap: `console_backend.py:254` always supplies `{}` to `portfolio_overlay`.
  - Implement: current context-matched measured flag provider, coverage/baseline checks and valuation status. Keep news hypotheses separate from Hawkes measurements.
  - Dependencies: G01, L16–L20; source/version/as-of contract.
  - Acceptance: measured sectors affect exposure, unmeasured sectors remain uncovered, old flags cannot silently clear current holdings, and unvalued holdings remain explicit.

- [ ] **G05 — P1 — Persist worker heartbeat separately from decision commits.**
  - Gap: `scripts/run_live.py:151` reuses last evaluator result on no-new-evaluation passes; replay leaves head unchanged. Reader treats head age as worker-pass age.
  - Implement: standalone heartbeat/pass status and failure state; commit only newly produced decisions. Keep last score timestamp untouched.
  - Dependencies: L05/L07/L09.
  - Acceptance: active idle, stopped, failing and producing workers are distinguishable, independently of last score freshness.

- [ ] **G06 — P1 — Include bar-builder recovery state in the actual runtime restart path.**
  - New code-confirmed integration gap: `scripts/run_live.py:restore/commit` stores/restores inference state and input IDs, but does not call `builder.snapshot()` or `builder.restore()` despite those methods existing.
  - Implement: durable input replay/cursor and versioned bar-watermark/open-bar state integrated with restart and commit protocol. Do not claim recovery from tests of the isolated builder alone.
  - Dependencies: L04–L06, L13–L15. Document transaction boundaries before migration.
  - Acceptance: crash/restart mid-bar and after finalization preserves OHLC/volume, deduplication and no-reopen guarantees through the normal entry point.

## D. News acquisition, interpretation and UI completion

The earlier news audit observed 11 endpoints from 8 publishers, 278 stored stories and a last saved projection with 265 eligible events, five sector rows, 10 nodes and one geographic edge. These were dated observations, not current guarantees. Two endpoints monitored fixed historical documents; they were not broad current-news channels. The server/worker were stopped at that audit instant. Recheck before operational changes; do not overwrite newer work.

- [ ] **N01 — P1 — Make news worker lifecycle observable and reliable.**
  - Files: `launch_prototype.ps1`, `scripts/run_news.py`, operations, dashboard.
  - Implement: worker heartbeat, exit/failure reporting, supervised restart and one-worker ownership; clearly document which launch paths start acquisition.
  - Dependencies: L09 for ownership and retries; separate UI and worker status.
  - Acceptance: ordinary launch starts acquisition; worker death becomes visible; restart does not duplicate workers or observations.

- [ ] **N02 — P1 — Define bounded startup freshness and manual refresh.**
  - Defect/gap: existing source due-times survive restart; screen refresh does not fetch; a launch does not check every source immediately.
  - Implement: show cache with acquisition-pending state, perform bounded startup refresh under per-source rate limits and provide refresh-now status. Preserve conditional requests; never promise new stories when the source has none.
  - Dependencies: N01/N03/N04.
  - Acceptance: cached, checking, successful unchanged/304, updated and failed states are distinguishable; fresh launch behaviour is demonstrated without UI payload injection.

- [ ] **N03 — P1 — Separate acquisition freshness, worker health and coverage.**
  - Files: `news/acquisition.py:coverage_at`, `dashboard/news_view.py`, frontend.
  - Implement: display worker heartbeat, last source attempt/success, publication time, first-seen time and projection time distinctly. Registered-source health is not economic-universe coverage or article recency.
  - Dependencies: N01; source status contract.
  - Acceptance: stopped worker cannot read as healthy merely because last fetch remains inside the grace interval; 11/11 fetch health cannot imply complete sector coverage.

- [ ] **N04 — P1 — Reconcile source configuration on existing installations.**
  - Gap: launcher auto-registers only for a missing database; code adapters can exist without active registrations (MOFCOM listing was an example).
  - Implement: versioned, validated source-config reconciliation and explicit enable/disable/retire states; preserve historical registry versions.
  - Dependencies: N11; endpoint/rights checks before enablement.
  - Acceptance: adding an approved source reaches an existing store without deleting its history; failed/unapproved sources remain visibly disabled.

- [ ] **N05 — P1 — Recover missed articles after downtime.**
  - Gap: finite latest-item windows cannot guarantee catch-up; Federal Register acquisition did not traverse subsequent pages.
  - Implement: bounded date/cursor pagination, deduplication, retry budgets, explicit coverage-gap recording and restartable backfill where sources support it.
  - Dependencies: N01/N04/N11 and durable job progress.
  - Acceptance: outage exceeding one page of articles recovers all available items or reports a precise unrecoverable interval; failure cannot advance the durable cursor past lost data.

- [ ] **N06 — P1 — Expand actual source coverage by sector and policy channel.**
  - Implement staged verified adapters for exchange filings, DGFT/CBIC/Gazette, wider Indian ministry policy, energy/power/weather/pharma, foreign trade/government channels and permitted independent reporting. Distinguish active feed, fixed-document monitor, discovery and structural data.
  - Dependencies: N01–N05; source access/rights, parser/time fixtures and bounded live probe. No invented endpoints or bypasses of access restrictions.
  - Acceptance: per-sector source matrix records active/degraded/missing coverage; all enabled sources produce traceable ordinary-flow evidence. Historical Tata/MOFCOM pages do not count as broad issuer/policy monitoring.

- [ ] **N07 — P1 — Turn PIB acquisition into validated interpretable coverage.**
  - Gap: current Hindi PIB source is fetched but the English semantic rules abstain; publication times may be absent.
  - Implement: usable English channel and/or validated multilingual extraction with original-text alignment; preserve first-seen-only status when publication time is unknown.
  - Dependencies: N06/N08/N12.
  - Acceptance: held-out Hindi/English policy examples have measured extraction accuracy and abstention; no fabricated translation/date certainty.

- [ ] **N08 — P1 — Acquire sufficient permitted document evidence for policy reasoning.**
  - Implement: versioned permitted full documents/PDFs/tables, exact evidence spans, product/entity scope, exceptions, numerical changes, instrument relationships and provenance; keep headline-only limitations explicit.
  - Dependencies: N04/N06/N11 plus source rights review.
  - Acceptance: claims link to the exact retained/permitted representation; title-only cases abstain where scope or quantity cannot be established.

- [ ] **N09 — P1 — Fix effective-date gating and event lifetime.**
  - Files: `news/event_frames.py`, `extraction.py`, `estimation.py`, `dashboard/news_view.py`.
  - Defect/gap: generic “effective from” pattern can mark future measures effective immediately; aggregating all eligible events lacks an explicit active/expired/decayed event policy.
  - Implement: announced/adopted/effective/repealed states tied to actual dates and evidence; distinguish forthcoming information from enacted effects; explicit lifespan/reversal/supersession rules.
  - Dependencies: N08/N11; document semantic assumptions before implementation.
  - Acceptance: future-effective policy is visible but not treated as already in force; obsolete incidents do not persist as unexplained current stress; causal replay remains stable.

- [ ] **N10 — P1 — Expand documented exposure and tariff applicability.**
  - Gap: seven qualitative edges, two entities and one facility were a small pilot; no sized loss interpretation is justified.
  - Implement: dated country/product/company/facility links, applicable tariff scope and exceptions, evidence-backed sizes where available, and separately labelled accounting scenarios. Unknown exposure remains unknown.
  - Dependencies: N08/N09/N11; original plan NI10–NI12 data requirements.
  - Acceptance: independent foreign-to-Indian and domestic examples show source-to-event-to-exposure-to-sector/globe lineage; exclusions work; no unsourced company loss or double-counted exposure.

- [ ] **N11 — P1 — Complete temporal source/registry/document consistency.**
  - Defect/gap: historical coverage reads current source roster; source-place mappings lack equivalent as-of filtering. Review validators/cursors and correction transaction boundaries as part of this task.
  - Implement: bitemporal registry/source/health/document/projection rules and atomic acquisition; retain prior revisions and failures without backdating.
  - Dependencies: contract/migration design before edits; preserve old snapshots.
  - Acceptance: source or mapping added today cannot retroactively change an earlier as-known view; crash during fetch/commit cannot skip an unpersisted response.

- [ ] **N12 — P1 release gate — Finish frozen extraction/impact validation.**
  - Gap: regression tests and populated panels do not establish interpretation accuracy.
  - Implement: the plan's independently labelled/frozen extraction and impact sets, per-class/language/stage/sector metrics, abstention/error analysis, contradictory/retracted claims and ordinary browser integration scenarios.
  - Dependencies: start labels early; freeze evaluation before extractor selection; N07–N11 for release.
  - Acceptance: reproducible benchmark results and limitations; no synthetic-fixture success presented as real-world accuracy. Retain failed configurations.

- [ ] **N13 — P1 — Complete role-specific evidence-backed news use.**
  - Implement: portfolio-linked relevance/unmapped holdings, institutional mechanism/scenario views, regulator coverage/review controls, all from the same underlying evidence and honest timestamps.
  - Dependencies: N10, L10–L11/L16–L20 and appropriate identity contracts; local role switching remains a demo until real authentication is connected.
  - Acceptance: ordinary frontend role flows use genuine news data; uncovered holdings remain visible; role scope is enforced server-side where authenticated services are used.

- [ ] **N14 — P2 — Compare optional NLP/LLM extraction against the deterministic baseline.**
  - Implement only after N12 supplies labelled development/evaluation data: versioned extractor interface, evidence-bound output, latency/cost/pinning/fallback evaluation.
  - Dependencies: N08/N12; model/service access if needed.
  - Acceptance: measured per-slice benefit and safe abstention, not more fluent explanations alone. Keep the deterministic baseline and version all model changes.

- [ ] **N15 — P2 research — Establish prospective news usefulness and any predictive extension.**
  - Implement: immutable prospective alert/abstention/revision journal; separate preregistered incremental-news and structural scenario experiments only after data/semantic acceptance.
  - Dependencies: N10–N12 and explicit approval for new scientific assumptions. This is separate from operational freshness and a functioning globe.
  - Acceptance: causal out-of-sample baseline comparisons, false alarms, calibration, uncertainty and coverage; no claim that more feeds or plausible causal text proves advance crisis prediction.

## Further inspection queue — not confirmed defects and not counted above

- [ ] Investigate portfolio historical valid-time versus knowledge-time semantics: backdated imports are returned by `holdings_as_of` using effective time only. Decide whether each caller needs reconstructed positions or positions known at the decision cutoff; do not label one as the other.
- [ ] Trace authorization-revision checks through every durable mutation. The registry exposes `check_revision`, but initial scans found no call in decision-support/dashboard mutations. Establish realistic revocation-between-check-and-commit behaviour before claiming an exploitable defect.
- [ ] Inspect concurrent broker buffer handoff and sequence retention; confirm no tick can be stranded during buffer replacement. Do not infer a race merely from multiple threads.
- [ ] Review original feature standardization, universe vintages, corporate-action adjustment and model-fit availability against their actual orchestration callers. This audit does not certify all pillar mathematics.
- [ ] Review calibration/probability/reporting metrics for missing-data, class-absence and episode-boundary handling without rerunning expensive fits.

## Completion evidence template

For each item, append: status; owner/session; changed files and contract/migration effects; exact counterexample; focused regression and integration commands/results; evidence artifact paths; remaining limitations. Mark a checkbox only when its stated acceptance is met. If an item proves obsolete, record the inspected version and evidence rather than deleting it. Keep new discoveries under new stable IDs.
