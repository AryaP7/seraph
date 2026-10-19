# SERAPH — technical development and integration plan

Date: 2026-10-16. Intended implementer: Claude, working directly in `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`.

This is a proposed implementation design, not a record of completed implementation. Its primary input is `docs/INDEPENDENT-PRODUCT-READINESS-AUDIT-2026-10-16.md`, findings R01–R12. That audit is newer than the earlier frontend audit: news acquisition, identity, workspace, scenario and case modules now exist. Reuse them. Do not rebuild their functionality merely because they are absent from the canonical UI.

The source files and public documentation were inspected for this plan. No model refits, external account registrations, paid subscriptions, source-database writes or application changes were performed. Provider documentation availability does not establish successful production acquisition; the source acceptance procedure below must do that.

## 1. Delivery objective and constraints

Deliver a working single-node risk-and-event intelligence product with three independently attributable channels:

1. **Quantitative market channel:** current market inputs → existing Hawkes/RMT/Hamilton implementations → existing reconciliation/fusion → timestamped CSRS and diagnostics.
2. **Event intelligence channel:** received world news/official developments → evidence-backed events → locations/assets → documented exposure relationships → qualitative or explicitly hypothetical impact estimates → globe and role workflows.
3. **Decision workspace:** authenticated users → owned holdings/watchlists → saved scenarios and evidence → institutional review/regulatory cases → durable history.

The existing Astra future-loss forecasts remain a separately named research/forecast product. CSRS, event significance, hypothetical scenario loss and probability of future loss must never share an unlabeled scale.

Non-negotiable implementation constraints:

- Preserve Hawkes, RMT and Hamilton, original evidence and preregistration. Keep the standing original-Hamilton eligibility restriction until its own scientific acceptance is satisfied. Retaining a pillar does not require forcing an unvalidated output into production fusion.
- Preserve the original 3D Earth, map drill-downs and visual design. Retain requested illustrative content only with datum/panel-level `FABRICATED PREVIEW` labels and exclude it from all real calculations.
- Geographic/sector **news** impact is a separate series from Hawkes sector flags. Its provenance must travel to every view and export.
- Do not push, merge, reset, discard or silently absorb existing work. Inspect status and existing diffs first. Do not automatically commit.
- Keep `seraph/shared_types/` mathematical contracts unchanged in these integration slices. Put product extensions in `product_types`, `live`, `news`, `identity`, `decision_support` and `dashboard`. Record required schema changes and downstream effects before applying migrations; use disposable databases first.
- No automatic trading or regulatory intervention. A case decision and an alert notification are records/workflows, not execution authority.
- External credentials and data rights are real dependencies. Implement and test adapters without them, then explicitly leave real-source acceptance pending. Do not block unrelated work while waiting.
- Continue sequentially by dependency. Finish a vertical slice through the supported entry point before starting another collection of disconnected libraries.

## 2. Evidence baseline and completion accounting

Use the independent audit's baseline: **843 passed, 14 skipped, 1 expected failure**, with four expensive Hamilton/policy modules excluded. These are the audit's recorded results, not new tests run by this plan. Skips do not establish database/corpus acceptance. The original FR35 Table B conflict remains a scientific protocol decision, not a reason to block navigation or news integration.

Create `docs/IMPLEMENTATION-STATUS.md` with one row per ticket below:

`id | audit finding | implemented | canonical-route integrated | real-input verified | recovery accepted | scientific status | files | evidence | dependency/blocker`

Each nonempty verification cell must reference a command, source/config hashes, timestamp and immutable evidence artifact. A unit test injecting `lambda: 0.42` verifies callback transport only. It does not close engine integration. Remove stale completion counts by generating counts from rows; do not edit totals manually.

Initial state must be reconciled against current code. If another session already fixed a finding, inspect its diff and reproduce the relevant acceptance test, then reuse it instead of implementing twice.

## 3. Architecture decisions

### 3.1 Retain the current stack

Keep Python 3.12, NumPy/SciPy/statsmodels/Polars, Streamlit, the current Three.js component and PostgreSQL/TimescaleDB. Use existing SQLite product stores for the local prototype, with repositories/interfaces that can later support PostgreSQL. Do not introduce Kafka, a graph database, Kubernetes, a second web framework or a new dashboard to solve this audit.

Use a long-running single-writer live worker, existing `JobStore` for scheduled jobs/leases, and separate bounded news workers. Do not fit expensive models inside a Streamlit rerun. CPU-heavy refits may run in a bounded process pool after correctness; this is runtime concurrency, not a requirement for parallel development.

### 3.2 Add an application service boundary

Create `seraph/application/services.py` and `context.py`. The dashboard calls services; services authorize and invoke existing component APIs. They do not reimplement C9 or hold direct SQL for another component's tables.

Proposed methods:

```python
get_dashboard_context(session_id, requested_role, requested_org, view_mode, as_of)
list_portfolios(context)
preview_portfolio_import(context, portfolio_id, content, source_name)
commit_portfolio_import(context, portfolio_id, preview_id, expected_version, request_id)
get_news_workspace(context, filters, cursor, as_of)
get_event_evidence(context, event_id, revision)
save_scenario(context, baseline_id, assumptions, request_id)
run_scenario(context, scenario_id, expected_version, request_id)
review_scenario(context, scenario_id, decision, expected_version, request_id)
open_case_from_evidence(context, evidence_refs, request_id)
mutate_case(context, case_id, command, expected_version, request_id)
```

`RequestContext` contains server-resolved actor, org, role, session ID, request ID, authorization revision and real operation timestamp. It is constructed server-side; a browser-supplied `role` is only a requested grant selection.

### 3.3 Distinguish clocks and states

Every externally sourced record needs `source_event_at`, `published_at` when known, `received_at`, source revision and raw-content digest. Every decision needs `as_of` (information cutoff), `computed_at`, input IDs, model version and publication status. Every mutation needs `operation_at`, separate from the historical alert/decision time it references.

For a bar-close decision, `bar_end` and `as_of` are different fields: freeze `as_of` when the finalized input batch is durably available, after the bar ends, then compute. A tick received milliseconds after its exchange timestamp is not backdated into an earlier cutoff. Historical datasets without receipt timestamps support an explicitly declared retrospective availability model, not a claim of reproducing the exact live information set. Measure latency from `bar_end` through actual browser receipt.

Normalize to timezone-aware instants; keep the existing explicit IST serialization at interfaces. Do not compare arbitrary-offset ISO strings lexicographically. Preserve date-only publication precision and source timezone rather than inventing midnight as a precise release time.

Product states are orthogonal:

- Mode: `live_shadow`, `historical_replay`, `demo`.
- Data: `fresh`, `delayed`, `stale`, `unavailable`, `invalid`.
- Computation: `ready`, `warming_up`, `partial`, `failed`.
- Evidence: `observed`, `derived`, `estimate`, `scenario`, `preview`.
- Scientific qualification: `research`, `validated_for_named_use`, `excluded`.

A recent computation can be based on stale data. A valid calculation can still be an unvalidated research score. The UI must show both.

## 4. Dependency order and ticket map

| Ticket | Priority/current state | Required implementation | Depends on | Main files/interfaces | Completion evidence |
|---|---|---|---|---|---|
| T00 | P0 / baseline inconsistent | Snapshot status, hashes and ownership; reconcile audit reproductions; create status register | None | audit scripts, docs, manifest | Each R01–R12 mapped; no preexisting edits lost |
| T01 | P0 / publication defects | Fail-closed live gating; future time rejection; per-input freshness; typed reasons | T00 | `live/loop.py`, `clock.py`, `console_backend.py`, product envelope | R02 probes reject null/future/replay/disconnected readings |
| T02 | P1 / bars incorrect | Finalization watermark, cumulative-volume continuity, dedup/order/gap semantics | T00 | `live/bars.py`, `feed.py` | R03 reproduction + restart and boundary fixtures pass |
| T03 | P1 / transport partial | Explicit role routes, same-role no-op, request-ID acknowledgements, global request status | T00 | `prototype_app.py`, `bridge.js`, component HTML | Actual browser completes all role clicks without timeout |
| T04 | P0 before multiuser / disconnected | Per-request identity resolution, revocation repair, OIDC wiring, scoped list/read/mutate/export | T00,T03 | `identity/*`, application services, all private stores | Two-org tests, revoked cached principal denied, real login pending configured provider |
| T05 | P1 / historical input mismatch | Repair Hawkes per-window basket/count construction; add manifest identity | T00 | `write_hawkes_production.py`, `hawkes_universe.py` | Changing-membership fixture proves input/metadata agreement |
| T06 | P0 / missing orchestration | Timestamp inference service, deployed fit registry, warmup, per-pillar cadence | T01,T02,T05 | `live/inference.py` new, orchestration adapters, original engines | Raw replay and incremental results agree on supported configuration |
| T07 | P1 / memory-only lifecycle | Durable input cursor/checkpoints/decisions/outbox; session drain; recovery/calendar | T06 | new live store, `run_live.py`, `market_calendar`, jobs | Crash injection at every commit boundary; final bar; holiday/split session |
| T08 | P1 / UI historical only | Current-result reader and periodic refresh; runtime status and explicit replay switch | T03,T07 | datasource, prototype app, bridge | Exact persisted decision ID reaches browser without manual reload |
| T09 | P1 / narrow news acquisition | Source registry expansion and adapter contract; schedules/freshness/cursors | T00,T01 time rules | `news/http_feed.py`, acquisition, source config, new adapters | Official/global/hazard source samples acquired with provenance; outage/retry tests |
| T10 | P1 / empty reference data | Populate versioned entities/places/assets/exposure data; cited coverage manifest | T00 | `news/registry.py`, curated data, import scripts | Foreign policy and Indian facility examples resolve correctly |
| T11 | P1 / interpretation defects | Independent-source accounting; action/quantity/negation/place/facility extraction; revisions | T09,T10 | `news/model.py`, extraction, new clustering/review helpers | R08/R09 fixtures plus held-out extraction acceptance |
| T12 | P1 / simple category rules | Target-specific mechanism rules, uncertainty, bounded paths, deduplicated aggregates | T11 | `news/estimation.py`, versioned rule config | Cuts/hikes and producer/consumer examples differ correctly or abstain |
| T13 | P1 / map disconnected | `build_news_payload` integration; overlay-to-geometry adapter; evidence drill-down | T03,T09–T12 | `news_view.py`, console backend, component renderer | Received foreign and domestic events traverse actual globe and links |
| T14 | P1 / libraries unused | Retail holdings/watchlists; institutional scenario/review; regulator cases and scoped evidence | T04,T08,T13 | existing workspace/scenarios/cases + services/routes | Three durable end-to-end user journeys, restart and unauthorized checks |
| T15 | P1 / operations incomplete | Alert outbox/in-app delivery, provider health, migrations, backup/restore, runbooks | T07,T09,T14 | operations, migration runner, deployment scripts | Fault/restart/restore/load evidence, no fabricated delivery claims |
| T16 | P1 science / not achieved | Prospective ledger and immutable prediction protocol; news challenger evaluation | T07,T11,T12 | prediction/evaluation, new experiment protocol | Full positive/negative/abstention report; no automatic promotion |
| T17 | P2 / proposed additions | Role differentiators in section 12 | T14 plus each listed dependency | existing stores plus narrow extensions | Feature-specific acceptance; no unmeasured predictive claims |
| T18 | Release gate / outstanding | End-to-end shadow operation, documentation and supported-claim reconciliation | T01–T16 engineering gates | all supported entry points | Evidence bundle passes release checklist |

Recommended sequential execution: **T00 → T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08 → T09 → T10 → T11 → T12 → T13 → T14 → T15 → T16 → T18**. T17 follows a stable product or is inserted only where its dependencies are already satisfied. If credentials block real-feed acceptance, finish T09–T14 using recorded fixtures while leaving T07/T08 live acceptance visibly pending. Do not wait for predictive research to finish ordinary product integration.

## 5. Market runtime: implementation design

### 5.1 Publication policy (T01)

Replace ad-hoc timestamp labels with one function used by the worker and dashboard. It returns structured reasons and cannot promote a replay merely because `computed_at` is recent.

```python
def assess_publication(d, now, policy):
    reasons = []
    if d.mode != 'live_shadow': reasons += ['not_live_mode']
    if d.csrs is None or not valid_csrs_contract(d.csrs): reasons += ['no_valid_score']
    if not d.feed.registered or not d.feed.authenticated: reasons += ['unverified_feed']
    if not d.feed.connected: reasons += ['feed_disconnected']
    if d.as_of > now + policy.max_clock_skew: reasons += ['future_decision']
    if not d.state.warmup_complete: reasons += ['warmup_incomplete']
    if not d.calendar.coverage_verified_for(d.as_of): reasons += ['calendar_unverified']
    for x in d.required_inputs:
        if x.received_at is None: reasons += [f'{x.name}:unknown_availability']
        elif x.received_at > d.as_of: reasons += [f'{x.name}:not_known_at_cutoff']
        if x.observed_at > now + policy.max_clock_skew: reasons += [f'{x.name}:future_input']
        if not policy.accepts(x.coverage, x.freshness, x.quality):
            reasons += [f'{x.name}:input_policy_failed']
    if not d.has_eligible_information: reasons += ['empty_information_set']
    return PublicationAssessment(current_allowed=not reasons, reasons=tuple(reasons))
```

The initial policy must preserve existing pillar exclusion and transient-missingness semantics. Do not demand that every pillar emit on every bar. Declare mandatory observations and cadence-specific freshness; classify a delayed output as `DELAYED RESEARCH READING`, not a fresh reading. When disconnected, retain the last valid result visibly as last-known and publish a separate outage status.

Use `received_at <= as_of` for causal inputs even within tolerated clock skew; tolerance may flag a source-clock problem but cannot make future information eligible. Clamp neither future age nor missingness to zero. Proposed maximum source clock skew: 30 seconds, a configurable engineering assumption with negative/positive boundary tests, not a scientific threshold.

### 5.2 Bar state (T02)

Persist per-symbol/session: `last_finalized_end`, `last_tick_order_key`, `last_cumulative_volume`, `last_cumulative_at`, open accumulator and coverage state. Windows are half-open `[start,end)`; a tick exactly at end belongs to the next window.

```python
for tick in ordered_new_ticks:
    if duplicate_source_sequence(tick): continue
    window = calendar.window_for(tick.exchange_time)
    if window is None: quarantine('outside_session'); continue
    if window.end <= last_finalized_end[tick.symbol]: quarantine('late_finalized'); continue
    if tick.order_key < last_accepted_order_key[tick.symbol]:
        quarantine('out_of_order'); mark_volume_quality('uncertain'); continue
    if new_session(tick): reset_session_state()
    if cumulative_baseline_is_usable(tick):
        delta = tick.cumulative_volume - last_cumulative_volume
        if delta < 0: quarantine('volume_reset_or_revision'); invalidate_volume()
        else: current_window.volume += delta
    else:
        current_window.volume = None  # cannot infer the missing opening baseline
        current_window.volume_quality = 'partial'
    update_price_accumulator(tick)
    advance_cumulative_baseline(tick)

for accumulator in windows_ended_by(now):
    persist_final_bar_and_watermark_atomically(accumulator)
```

Cross-boundary volume 150 → 170 → 200 contributes **50** to the new window only if the 150 baseline is known at the preceding boundary/valid continuous interval. If the last tick is from well before that boundary, attribution across the boundary is uncertain: flag or reconcile with the provider's authoritative bar rather than assert exact 50. Never subtract only the first tick inside the new bar. A mid-session connection cannot label its opening partial interval fully covered. Close-only timestamps alone do not prove a complete OHLCV sample.

Record late corrections as separate input revisions; never silently rewrite a published decision. Allow explicit amended replay/run IDs later. A persisted finalization watermark must also prevent reopening after restart, including when `_open` is empty. Use provider sequence when available; if dedup relies on a hash of timestamp/token/price/volume, document collisions and absent exchange sequence limitations. Kite exposes cumulative traded volume and exchange timestamps in appropriate packet modes; use the documented full packet fields and do not treat all LTP packets as equivalent. [Kite WebSocket documentation](https://kite.trade/docs/connect/v3/websocket/)

### 5.3 Timestamp inference service (T06)

Add an orchestration-owned `DecisionRequest` and `DecisionResult`; keep `CsrsPoint` unchanged inside the result.

```python
DecisionRequest = {
  'decision_id': str, 'as_of': aware_datetime, 'trigger': 'bar_close|daily|refit',
  'mode': 'live_shadow|historical_replay', 'input_batch_ids': list[str],
  'universe_snapshot_id': str, 'pipeline_version': str,
  'model_bundle_id': str, 'standardizer_policy_id': str,
}
DecisionResult = {
  'request': DecisionRequest, 'computed_at': aware_datetime,
  'csrs': CsrsPoint | None, 'pillar_diagnostics': dict,
  'reconciled_state': ReconciledState | None,
  'input_provenance': list, 'publication': PublicationAssessment,
  'state_after_id': str, 'warnings': list,
}

class InferenceService:
    def warm_start(self, history, deployment, cutoff) -> StateSnapshot: ...
    def process(self, request, inputs, previous_state) -> DecisionResult: ...
    def snapshot(self) -> StateSnapshot: ...
    def restore(self, snapshot, deployment) -> None: ...
```

Processing steps:

1. Validate ordered decision timestamps, unique batch identities, availability cutoff and correct point-in-time universe. Multiple bar decisions on one day are allowed; duplicate request returns existing result.
2. Update feature buffers with accepted finalized observations only. Do not fabricate missing bars; preserve gaps, session boundaries and missing-volume flags.
3. Run each producer only at its declared cadence. Store `input_end`, `fit_train_end`, `fit_completed_at`, `fit_deployed_at`, `emission_available_at` independently. A model trained through yesterday but deployed tomorrow is not available today.
4. Convert producer outputs through existing adapters. Append each **new vintage once** to its standardizer; polling an old value must not create extra ECDF observations or shrink uncertainty. Declare the five-year window's session/time policy. Intraday repetition must not overweight daily pillars.
5. Invoke existing C8 predict/update and C9 pure `score()` with the deployed immutable weights. Preserve C8 structural versus transient absences and age inflation. Use the session-aware clock; verify how its time units convert at intraday cadence before choosing `Q_proc` scaling.
6. Generate C11 explanation and publication assessment. Preserve diagnostics even when the score is unavailable. Save checkpoint/result/outbox together.

Do not call the date-only `InferenceSession.step()` repeatedly with the same date. Extract/reuse its numerical orchestration in a timestamp service and leave an archive compatibility adapter. Compatibility tests must compare old archive results under the **same** date cadence/configuration; an explicitly amended source run may differ and needs its own manifest.

Cadence/deployment rules:

| Producer | Runtime behavior | Warm-start/deployment condition |
|---|---|---|
| Original Hawkes | Consume closed five-minute jump counts; use declared existing fit/emission semantics | Corrected jump version, point-in-time basket, required history, supported fit and gate semantics recorded |
| Original RMT | Daily observation after full daily data is available; retain daily vintage intraday | T=1000 supported returns and actual member IDs; common-support rotation state restored; no two-window shortcut presented as full standardizer warmup |
| Original Hamilton | Daily diagnostic at existing schedule | Causal model/training metadata; keep diagnostic-only exclusion unless independently accepted |
| Astra variants/probabilities | Separate daily forecast product | Exact feature schema, fitted transforms, matured-label cutoff, deployable model parameters and calibration artifact |
| C8/C9 | Decision ticks using latest eligible vintages | Standardizer/filter warmup and artifact IDs verified; unchanged mathematical definitions |

Heavy daily RMT bootstrap/refits need not finish within five seconds of bar close. Schedule them outside the critical path and publish only after their real completion time. Use the previous eligible vintage with proper age where the declared policy permits it. Do not backdate a new fit to bar close to meet latency. The existing evidence does not establish bar-frequency MTS merely because a callback runs every five minutes; expose actual emission cadence.

Proposed intraday clock mapping, requiring a documented adapter decision and numerical checks: let `u(t)` equal completed observed sessions plus the fraction of scheduled open minutes elapsed in the current session. Then use `delta_u = u(t)-u(previous)` with a daily-unit random-walk covariance, preserving total per-session process variance rather than injecting one full daily covariance every five minutes. Split-session breaks add no trading time. Do not assume that every existing noise parameter uses those units: inspect each C8 parameter and keep its declared age/time convention or explicitly version the conversion. Test that a day partitioned into bar predictions has the same total process covariance as one daily prediction when there are no intervening observations. If the existing implementation already supports a different verified clock, reuse that mapping and record it instead.

### 5.4 Durable store, crash protocol and session lifecycle (T07)

Add `seraph/live/store.py` using one SQLite database for the runtime transaction boundary initially. Keep append-only input payloads and content-addressed large checkpoints on disk, with atomic rename before inserting their reference. A later PostgreSQL adapter must preserve the same repository contract.

Minimum tables (versioned migrations, not ad-hoc startup schema edits):

```sql
input_batches(batch_id PRIMARY KEY, source_id, received_at, payload_hash, payload_ref, quality_json);
closed_bars(symbol, session_id, bar_end, revision, input_batch_id, payload_json,
            PRIMARY KEY(symbol,session_id,bar_end,revision));
deployments(bundle_id PRIMARY KEY, trained_through, available_at, manifest_json, manifest_hash);
inference_checkpoints(checkpoint_id PRIMARY KEY, pipeline_version, bundle_id,
                      last_decision_id, input_cursor_json, state_ref, state_hash);
live_decisions(decision_id PRIMARY KEY, as_of, computed_at, input_hash, checkpoint_id,
               payload_json, payload_hash, publication_state);
runtime_head(stream_id PRIMARY KEY, checkpoint_id, version);
outbox(outbox_id PRIMARY KEY, event_kind, aggregate_id, payload_json,
       created_at, delivered_at, attempts, next_attempt_at);
```

Within one database transaction, compare the expected `runtime_head.version`, append decision/checkpoint reference, advance head and insert outbox event. A crash before commit leaves no published decision; after commit replay returns the same logical decision. Do not claim exactly-once network delivery: use at-least-once delivery with receiver/idempotency keys. Independent databases for news/workspaces cannot participate in this transaction; connect them with versioned immutable IDs/outbox events and idempotent consumers, not a pretend cross-database atomic write.

Checkpoint contents: bar state and volume baselines, source cursor, feature rolling buffers, last pillar vintages and timestamps, ECDF histories, C8 `x/P/tau/mask`, model IDs, universe/calendar IDs, seeds, library/config versions. Validate checksum, supported schema and exact model/config identity before restore. A mismatch triggers deliberate rebuild/warmup; never deserialize arbitrary untrusted pickle.

Lifecycle state machine: `initializing → restoring/warming_up → connecting → waiting_session → collecting → draining_session → checkpointed`, with `reconnecting`, `degraded`, `stopped` branches. Poll/drain before deciding the session is over. Add `--status` that does not connect/start jobs, and define `--once` as a bounded wait for one finalized batch with explicit timeout, rather than connect-and-immediately-poll.

Calendar: source official exchange holiday/special-session notices, persist their citations/version, support all windows in a day. `next_open` chooses the next window after the instant, including a later window on the same day. Unknown calendar coverage blocks a confident current label. Bound in-memory status history with `deque`; use persisted decisions for history.

T05 historical basket correction: load per-symbol events once, then construct each window's pooled counts from its actual as-of member set; persist `basket_id`, member hash, input-row/event hash, detector version and window bounds. Membership policy must explicitly distinguish fixed-at-window-start, fixed-at-fit-cutoff and day-varying composition. Match the already adopted policy; if ambiguous, record a decision before regeneration. Test an exiting symbol whose events would disappear under terminal-basket selection. Regenerate into a new namespace, preserving old artifacts and negative results.

## 6. Identity, role routing and application transport

### 6.1 Authentication and revocation (T04)

Use Streamlit's supported OIDC `st.login`, `st.user`, `st.logout` path, then the existing `VerifiedSubject.from_streamlit_user` → `IdentityRegistry` mapping. Verify the locked Streamlit version supports these APIs; update/pin only if needed with focused regression. Streamlit identifies users; SERAPH still owns authorization. [Streamlit authentication documentation](https://docs.streamlit.io/develop/concepts/connections/authentication)

No caller may pass arbitrary claims to a helper and receive authenticated status. `OidcVerifier.verify(claims)` must only consume claims from a cryptographically verified trusted boundary; name/document this clearly. An email address or browser JSON is not an identity token. First login creates a subject record with **no privileged grant**. Bootstrap grants through a local administrative command, never through role buttons.

Repair `IdentityRegistry.can/require`: re-resolve the principal's session/current grant/membership/user status before authorization. Prefer an internal authorization snapshot per request; mutations must recheck within their commit boundary or verify an authorization revision immediately before committing. Tests revoke membership, grant, session and user independently between two calls using the same old `Principal`.

Scope all list, detail, export, scenario comparison, case replay, portfolio import and cache paths. Include user/org/scope/auth revision in private cache keys, or avoid cross-user caching initially. Regulator role has explicit scope, not unrestricted access to personal holdings. Clear payload and pending private operations when role/org changes; do not reuse an institutional response in retail.

Keep explicit localhost demo mode with conspicuous demo identity and isolated demo data. OIDC failure in authenticated mode must never fall back to demo privileges.

### 6.2 UI request/response (T03,T08)

Use a versioned transport envelope:

```json
{"request_id":"uuid","schema_version":2,"op":"role.select",
 "context":{"view_mode":"live","selected_decision_id":"...","org_id":"..."},
 "expected_resource_version":3,"arguments":{"requested_role":"institutional"}}
```

Response: `request_id`, `status=ok|error|conflict`, `code`, `message`, `context_revision`, authorized role/route, result and updated resource version. A same-role click acknowledges the request and leaves state unchanged. It never waits for role inequality. Read requests may retry; mutations use persisted idempotency keys and reject reuse with changed bodies. Stale context returns an explicit error response.

Routes: `map`, `signals`, `retail/home`, `institutional/home`, `regulator/home`, `portfolio/:id`, `scenario/:id`, `case/:id`, `evidence/:id`, `operations`. Map remains available to each allowed role. Persist selected route per session; role buttons navigate to the corresponding landing route. Display pending/error/retry status globally, not only within Tools.

Poll the current reader with a Streamlit fragment, initially every two seconds, using stable component keys and decision/news revision IDs. Preserve camera, selection and form drafts on data-only refresh. Do not refresh a form into a new baseline silently; show a newer-data notice and require an explicit baseline change. Polling interval is an engineering default subject to latency/load measurement. [Streamlit automatic fragment reruns](https://docs.streamlit.io/develop/tutorials/execution-flow/start-and-stop-fragment-auto-reruns)

Expose latest valid score and latest worker health separately. On outage the last score remains inspectable with its timestamp; it is not reissued as a new score. Show live/replay/demo as a first-class selector, with no silent fallback to historical results.

## 7. News sources: researched selection and integration

### 7.1 Source portfolio

Start with official Indian sources, a global discovery source, and structured hazards. Source diversity means different information producers and event coverage, not additional mirrors of RBI. The polling intervals below are **proposed SERAPH defaults**, subject to provider terms/rate limits; they are not provider latency guarantees.

| Source and priority | Retrieval and useful coverage | Proposed adapter/poll | Status and limitation |
|---|---|---|---|
| Existing RBI feeds / first | Keep existing press release, notification and speech configuration | Existing RSS adapter, 15 min | Audit records 30 acquired stories. Preserve these records. The RBI RSS directory did not render through the research browser; no new end-to-end fetch is claimed |
| PIB / first | Government releases: trade, industry, infrastructure, energy and policy; official feed `https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1` | RSS, 15 min; ministry/topic filters | Endpoint listed by [PIB](https://www.pib.gov.in/ViewRss.aspx?lang=1&reg=1); feed body not verified by this research tool. A government statement is evidence of its announcement, not independent proof of all claimed effects |
| SEBI / first | Market regulation, circulars, orders; `https://www.sebi.gov.in/sebirss.xml` | RSS, 15 min | Official [RSS documentation](https://www.sebi.gov.in/rss.html). Research browser rejected XML content type; test with actual HTTP/XML adapter |
| NSE corporate announcements / first if access permits | Issuer disclosures, facility incidents, operational changes and reports | RSS links discovered from official directory; 5–15 min | [NSE feed directory](https://www.nseindia.com/static/rss-feed) documents categories. Resolve actual links at implementation; do not assume an undocumented site API is supported. Preserve exchange filing time and issuer assertions |
| GDELT DOC / first global discovery | Queries for export restrictions, tariffs, ports/shipping, energy disruptions, defaults, industrial incidents | JSON `https://api.gdeltproject.org/api/v2/doc/doc`; 15 min, overlapping time windows | [Official DOC documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) supports article search/JSON. Discovery and coverage sampling only; publisher country is not event origin. API index time is not SERAPH receipt time. Do not assume an exhaustive historical archive |
| Federal Register / first international policy | US trade, Commerce/USTR and presidential regulatory documents | JSON `/api/v1/documents.json`, filters and pagination; 30 min | [Official API](https://www.federalregister.gov/developers/documentation/api/v1) requires no API key. Track document type, publication/effective dates, docket and official PDF; proposed rules are not implemented policy. Verify legal details against the linked official edition |
| Federal Reserve / second | Monetary decisions and official communications affecting global funding conditions | Monetary-policy RSS from official directory; 15 min | [Official RSS directory](https://www.federalreserve.gov/feeds/feeds.htm). Announcement is not a measured policy surprise without pre-release expectations |
| WTO / second | Trade disputes, measures and policy context | Official latest-news RSS; 30 min | [WTO RSS directory](https://www.wto.org/english/res_e/webcas_e/rss_e.htm). Good corroboration/context, not comprehensive fast national announcements |
| USGS / first structured hazard | Worldwide earthquakes with stable IDs, event/revision times and coordinates | `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.geojson`, initially 5 min | [Documented GeoJSON feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php); a current JSON response was retrieved during research. Location/magnitude alone do not establish damage to a facility |
| NASA EONET v3 / second hazard | Curated natural-event locations/geometries, source links and lifecycle | `https://eonet.gsfc.nasa.gov/api/v3/events`, 30 min | [API v3](https://eonet.gsfc.nasa.gov/docs/v3). Documentation verified; sample API fetch unavailable in this research tool. Some event geometry times have date-level precision; not a plant-impact model |
| WHO Disease Outbreak News / second | Confirmed/potential public-health developments | Official-page/available feed adapter, 60 min | [WHO DON](https://www.who.int/emergencies/disease-outbreak-news). Discover current supported machine-readable route before implementation; do not invent an RSS URL. Outbreak news and formal emergency declarations are different event types |
| ReliefWeb / optional second | Humanitarian/disaster reports, country and source metadata | Documented JSON read API, 60 min | [API documentation](https://apidoc.reliefweb.int/). Verify current app-name/access requirements and quotas during source acceptance. Its reports may repeat original sources; retain origin attribution |

Expand DGFT/CBIC/USTR and issuer investor-relations notices after this slice where they fill measured gaps. Their exact extraction endpoints, rights and access must be established individually; do not promise a generic scrape covers them. Paid news access is optional procurement, not a hidden dependency. Do not register, pay or bypass access restrictions without the owner's authorization.

Weather and commodity cards need their own observation products. USGS/EONET events do not replace forecast weather or live commodity prices. Keep those original cards tagged preview until a licensed/source-verified price or weather adapter provides units, instrument/location, observation time and freshness.

### 7.2 Common source contract (T09)

Extend existing `Source`/`SourceHealth` compatibly with: provider group, adapter kind, default timezone, timestamp precision policy, request timeout, maximum response bytes, allowed redirect hosts, rights evidence URL/date, cursor strategy, freshness budget and coverage description. A source can be technically reachable but not permitted for full-text storage; these are separate fields.

```python
class SourceAdapter(Protocol):
    def fetch(self, source, cursor, conditional_headers, now) -> FetchResult: ...
    def normalize(self, raw_item, received_at) -> FetchedItem: ...

def poll_source(source_id):
    source = registry.require_enabled(source_id)
    with jobs.lease('news:' + source_id):
        response = adapter.fetch(source, cursor=store.cursor(source_id), ...)
        if response.not_modified:
            store.record_successful_check(now, changed=False)
            return
        for item in response.items:
            # same identity + same bytes: no new story; new bytes: new revision
            store.ingest_observation_and_revision(item, first_seen_at=receipt_clock())
        # advance only after the durable batch succeeds
        store.commit_cursor(response.next_cursor)
        enqueue_idempotent_extraction_for_new_revisions()
```

Preserve conditional GET and current first-seen semantics. Fix global-source parsing: `parse_feed_datetime` currently assumes IST for naive dates. Pass a source-specific timezone; ambiguous/unknown zone yields unknown publication time with a warning. Compare parsed instants. A publisher timestamp apparently in the future is quarantined as a timing anomaly; keep receipt evidence rather than rewriting it to fit the validator.

HTTP policy: bounded connect/read timeout, bounded decompressed bytes, three bounded retries for transient failures, exponential backoff/jitter, respect Retry-After and per-source budget. Do not retry an authorization denial aggressively. Restrict schemes/redirects to public approved source hosts and reject private-network targets when following article links. Treat HTML and article text as data, never commands or model/tool instructions.

GDELT retrieval: issue a small fixed query family, request article lists, preserve query version and window; overlap prior successful windows to absorb indexing delays. If a response reaches its configured result cap, split the interval until complete or mark it `truncated`; do not silently claim full coverage. Distinguish `source checked, no new item` from `fetch failed` and from `source publishes infrequently`. Empty news does not mean no risk.

Source acceptance artifact per provider: URL/config/version, fetch time, HTTP/parse outcome, permitted stored sample/hash, mapped fields, first-seen behavior, retry/rate-limit behavior and rights decision. A source passes only after actual adapter acquisition, duplicate poll, malformed-item handling, outage visibility and cursor restart tests. These checks must not require every provider to publish a new story on demand.

## 8. Build versus reuse: library choices

Use libraries for parsing, text matching and geometry; keep SERAPH's temporal semantics, economic rules, source independence, graph provenance and role authorization in project code.

| Capability | Decision | Integration boundary and guard |
|---|---|---|
| HTTP/JSON/RSS | Retain current bounded HTTP layer. Add [feedparser](https://github.com/kurtmckee/feedparser) only if real-feed fixtures expose unsupported RSS/Atom variants | Parse bytes fetched by SERAPH; library timestamps never replace receipt time. No second hidden network client |
| Article HTML extraction | Optional [Trafilatura](https://github.com/adbar/trafilatura) | Run on permitted downloaded HTML, with text/metadata output stored as a revision. Title-only fallback is explicit. Tool capability does not confer publisher rights |
| Entity/action rules | [spaCy Matcher/PhraseMatcher/EntityRuler](https://spacy.io/usage/rule-based-matching) plus existing registries | Deterministic dictionaries and token patterns for actions, negation and units. Start with a small CPU pipeline; retain exact evidence offsets |
| Alias candidate search | [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | Candidate generation only. Similar spelling alone cannot resolve a company/facility. Normalize explicitly and require context/type agreement |
| Optional entity challenger | [GLiNER](https://github.com/urchade/GLiNER) | Benchmark against the same review set; pin model artifact and its separate license. Extractor output is a candidate with source spans, not authoritative identity |
| Optional semantic clustering | [Sentence Transformers](https://github.com/huggingface/sentence-transformers) | Retrieve candidate similar stories; event action/time/entity checks decide merges. Pin checkpoint/hash; CPU budget; no vector database required initially |
| Financial tone | [FinBERT](https://huggingface.co/ProsusAI/finbert) only as an optional research feature | Its sentiment labels do not establish economic direction, severity, loss probability or causal impact. Do not make this the primary news engine |
| Geometry | [Shapely](https://github.com/shapely/shapely) if polygon intersection is needed | Registry geometry/GeoJSON adapter. Use geographic distance/projection correctly; proximity means exposure candidate, not confirmed damage |
| Graph traversal | Existing adjacency structures, bounded traversal | No graph database. Preserve evidence on every edge, path identity and uncertainty; section 10 defines aggregation |
| Scheduling/identity/research | Existing JobStore, Streamlit OIDC, NumPy/SciPy/statsmodels/arch | Reuse current packages; don't replace working systems just for novelty |

Dependency admission: optional `news`/`news_ml` extras; record tested Python 3.12 Windows wheel support, exact version, transitive dependencies, code/model/data licenses and benchmark. Lock versions after a disposable-environment import/regression check. Do not install all optional ML packages to complete the first slice. Start with existing parsing + deterministic rules + curated reference data, then admit challengers only when measured errors justify them.

## 9. Reference data, event extraction and evidence independence

### 9.1 Populate a bounded, cited reference dataset (T10)

The empty `curated/*.csv` files are a delivery task. Claude can research public primary documents and prepare cited records; do not leave the entire task as an unspecified future human exercise. Human review is required only for unresolved factual/economic assumptions.

First coverage release: five priority economic sectors, at least 20 listed issuers, 15 physical facilities and 30 documented exposure relationships, selected for actual source coverage and the two required end-to-end cases. These counts are proposed engineering coverage goals, not statistical validation or claimed full-market coverage. Do not invent records to hit a count; report actual completion and gaps.

Record:

- Entity: stable ID, ISIN/symbol where verified, issuer/operator/subsidiary distinction, aliases, sector taxonomy version, valid dates and known-at timestamp.
- Place: ISO country and stable state/district IDs, geometry ID, coordinates with precision/source. Keep facility/site location separate from corporate headquarters and government actor headquarters.
- Asset: verified name/type/operator, place/coordinates, capacity and unit if disclosed, disclosure date, source document/page/span.
- Exposure edge: source/target ID, mechanism, input/output commodity where known, numerator/denominator/unit for a magnitude, valid interval, known-at timestamp, evidence reference and verification status.

Prioritize issuer filings/annual reports and official facility pages for asset facts. Use geographic boundary datasets only for geometry. [geoBoundaries API](https://www.geoboundaries.org/api.html) is a candidate for versioned administrative geometry; check the selected dataset's license, geopolitical representation and compatibility with the current map before adoption. It does not provide business dependencies.

Country-sector import shares cannot be relabeled as company-specific revenue/input shares. A sector classification alone establishes membership, not sensitivity. An input-output matrix is an optional later scenario model needing a dated table and explicit assumptions; it is not necessary for the first documented graph.

Versioned CSV import should validate referential integrity, ambiguous aliases, nonoverlapping validity where required, coordinate range, dimensional units and citations. Store imported snapshot hash and an append-only revision. Historical replay must filter both economic validity and when SERAPH knew the relationship; a 2026 annual report cannot populate a 2020 operational knowledge graph.

### 9.2 Extend Event and story lineage (T11)

Introduce product-model schema version 2, with a backward reader for v1. Add:

```python
EventRevision = {
 'event_id': str, 'revision': int, 'known_at': datetime,
 'event_type': str, 'action': str, 'modality': 'actual|proposed|rumour|denied',
 'actor_ids': list[str], 'origin_place_ids': list[str],
 'affected_asset_ids': list[str], 'affected_entity_ids': list[str],
 'commodity_ids': list[str], 'jurisdictions': list[str],
 'occurred_at': datetime | None, 'effective_at': datetime | None,
 'quantities': list[{'name':str,'value':float,'unit':str,'basis':str}],
 'evidence_spans': list, 'unresolved': list,
 'lineage_groups': list[str], 'method_version': str,
 'supersedes_revision': int | None, 'lifecycle': str,
}
```

Keep `event_id` stable while corrections produce revisions. Use raw source item identity + source revision for stories. Event clustering membership must itself be versioned: later knowledge of a duplicate/correction cannot silently alter an earlier replay.

### 9.3 Extraction pipeline

```python
def extract_revision(story, reference_snapshot, extractor_version):
    text, offset_map = normalize_preserving_original_offsets(story)
    candidates = detect_entities_places_assets_actions_quantities(text)
    candidates = attach_evidence_spans(candidates, offset_map)
    action = resolve_action_and_negation(candidates)  # hike/cut/hold; halt/resume
    modality = resolve_proposed_actual_denied_reported(candidates)
    assets = resolve_assets_with_operator_and_place_context(candidates, reference_snapshot)
    places = resolve_explicit_places(candidates, reference_snapshot)
    origin = choose_origin_from_explicit_event_location(assets, places, action)
    # Never substitute operator headquarters for an unresolved plant location.
    claims = validate_units_and_direction_of_change(candidates)
    return typed_event_or_review_required(action, modality, origin, claims, ...)
```

Important numerical distinctions: 25 basis points versus 25%; a rate changing from 6.5% to 6.25% is −25 bps, not −0.25%; tariff level versus tariff change; ₹ crore versus ₹; capacity per year versus inventory; permanent closure versus temporary halt. Store original units and normalized units. Preserve quoted/attributed claims and negation. Multiple events in one article must produce multiple linked event candidates instead of forcing one category.

Entity resolution hierarchy: exact stable identifier → exact curated alias with valid context → candidate fuzzy match with type/location/operator constraints → analyst review. Explicit abstention for ambiguity. Resolve facility mentions and place mentions in addition to company names; these are currently disconnected paths in R08.

### 9.4 Corroboration and deduplication

Replace `len(set(event.stories))` with evidence-lineage accounting. Store publisher/source group, original wire/filing ID if known, canonical URL, content fingerprint and quoted primary source. Different domains repeating the same release count as one origin. An independently reported observation may count separately; if independence is unknown, mark it unknown rather than award confidence.

Suggested algorithm:

1. Exact item/URL/content digest deduplication.
2. Candidate syndication pairs from normalized text shingles or optional embedding similarity in a bounded time window.
3. Merge only with compatible actor/asset, action, effective date and quantities. Opposite actions, denials and corrections are linked but not flattened into identical evidence.
4. Build provenance roots from explicit wire attribution/primary document. Count distinct independent roots, with ambiguous lineage excluded from the independent count.
5. Confidence retains distinct dimensions: event factual support, extraction reliability, entity resolution, exposure evidence. A single primary official release can strongly support that a policy was announced without two newspapers confirming it; it does not prove a downstream economic effect.

Use proposed similarity thresholds only after tuning on a labeled development set. Do not hard-code an arbitrary cosine score as proof of independence. Record merge/split reasons and allow reviewed correction.

## 10. SERAPH event-impact engine

### 10.1 What the first engine produces

An auditable **mechanism assessment**: which target may be affected, through which documented relationship, in which direction, over which stated/assumed horizon, with what uncertainty. Initial severity is ordinal and rule-based. It is not a probability or predicted return.

Implement `seraph/news/rules/*.json` and a rule evaluator in `estimation.py` or a small `mechanisms.py`. Rules have `id/version`, event predicates, action/modality predicates, target/exposure predicates, effect metric, direction, horizon/decay policy, required evidence, ambiguous branches and limitations. Include source rationale for economic assumptions. A change of rule version creates new estimates, not an overwrite of historical ones.

Example rule structure:

```json
{"id":"export_restriction_input_cost","version":1,
 "when":{"event_type":"export_restriction","modality":"actual"},
 "requires":["commodity_match","documented_import_dependency","origin_jurisdiction_match"],
 "target_metric":"input_availability_or_cost",
 "direction":"adverse","price_return_direction":"unresolved",
 "quantification":"none_without_exposure_and_pass_through",
 "horizon_basis":"effective_date_and_review_policy"}
```

Required rule cases:

| Event | Extracted fact | Conditional target interpretation |
|---|---|---|
| Rate cut/hike/hold | Signed basis-point change and effective date | Borrower funding-cost channel and lender margin channel differ; deposit repricing, maturity and expectations may make net impact ambiguous |
| Tariff increase/decrease | Product/HS scope, origin/destination, level/change, implementation status | Exporter competitiveness, import-user cost and domestic substitute opportunities have separate signs; no blanket sector direction |
| Plant halt/resumption | Actual facility, duration/capacity if stated | Operator production channel; downstream supplier/customer path only with documented dependence; restarting reverses the disruption mechanism, not necessarily the equity return |
| Port/logistics disruption | Route/port, actual versus threatened closure | Only documented dependent flows/assets receive an exposure path; country mention alone is insufficient |
| Earthquake/storm | Hazard geometry, time and intensity | Intersecting/nearby facilities are potentially exposed; confirmed shutdown requires separate evidence. No inference that every nearby plant is damaged |
| Bank resolution/default | Affected entity/instrument, actual action | Direct counterparty/holding exposure only where documented; general banking-sector concern is separately labeled context |
| Outbreak/declaration | Place, reported event and authority | Operational/travel/supply-chain watch through documented links; never assert that an outbreak predicts a market crisis |

One event may produce favourable and adverse mechanisms for the same target. Preserve both, return `mixed/ambiguous` net direction, and list missing inputs. Do not net ordinal labels or assume positive tone offsets negative exposure.

### 10.2 Bounded propagation and aggregation (T12)

Traverse only valid, knowable edges, initially at most two hops. Limit is a transparent engineering scope, not an economic theorem. Track `(event_revision, target, mechanism, exposure_basis)` to avoid counting the same exposure repeatedly. Retain alternative paths for inspection.

```python
for event in active_events_known_at(as_of):
    for origin in resolved_event_origins(event):
        for path in bounded_paths(origin, max_hops=2, no_cycles=True):
            if not all(edge.visible_at(as_of) and edge.valid_at(event_time) for edge in path):
                continue
            rule = matching_mechanism_rule(event, path)
            estimate = apply_rule_or_abstain(rule, event, path)
            save_estimate(event.revision, target=path.target,
                          method_id=rule.version, evidence_ids=path.evidence, ...)
rollup = aggregate_unique_exposures(estimates, preserve_unknowns=True)
```

Magnitude rules:

- Only multiply shares along a path when their denominators genuinely compose. Mixed revenue share, tonnes/year and national trade share cannot be multiplied as generic weights.
- For alternative paths representing the same exposure, use one documented basis and show alternatives. Do not add duplicates. Independent, disjoint quantities may be summed only with a defensible common denominator and explicit disjointness.
- Without magnitude, return `relationship_exists, magnitude_unknown`; do not substitute 1 or 0.
- Aggregate adverse/favourable/ambiguous counts and assessed exposure coverage separately. A sector with no mapped relationships is `uncovered`, not low stress.

For an explainable first map heatmap, use ordinal `no_active_evidence / watch / material / severe / unresolved` based on documented rule conditions, not a pseudo-precise 0–100 crisis score. Preserve the legacy numeric preview separately if no real mapping exists. If a numeric ranking is later wanted, name it `news_review_priority`, publish the rank formula/version and validate ranking utility; never call it loss probability.

A quantitative what-if is possible only when inputs support it. Example with compatible units: `incremental_input_cost = baseline_input_cost × affected_import_share × assumed_price_change × pass_through_to_buyer`. Each quantity has a source or an explicit user assumption. Show an interval over declared assumptions; label it a scenario, not an estimated realized P&L. Do not convert this cost mechanically into an equity return without an independently defined valuation model.

### 10.3 Event ageing and corrections

Use lifecycle and effective dates first. A policy remaining in force should not decay to zero simply because articles stopped. Temporary incidents use a versioned review/expiry rule; absence of a follow-up is not proof of recovery. A correction/retraction creates a new event revision, recalculates current estimates and marks linked cases/scenarios `evidence_changed`; historical views retain what was known then.

An exponential attention decay may be used for sorting developing news, e.g. `2**(-age/half_life)`, but keep it separate from the persistence of the real-world effect. Half-lives are proposed ranking parameters requiring review, not calibrated financial constants.

### 10.4 Measured impact and predictive research (T16)

After the event ledger works, evaluate whether news adds information. Do not keep tuning the same six historical crises until an attractive result appears.

- Keep original onset and 15-session future-loss targets separate. Preserve all existing negative results, baselines and ablations.
- Add a prospective freeze date and protocol with event families, target assets/sectors, horizons, label maturity, features, alert budgets and promotion rule before examining outcomes.
- First research features: independent event counts, novelty versus prior disclosures, direction-specific exposure, unresolved fraction, source outages, event age and measured coverage. Use training-only transforms and point-in-time reference data.
- Compare market-only baseline, existing three-pillar model, news-only challenger and market+news challenger on identical assessable dates. Keep the three families in the product; ablations diagnose marginal contribution.
- Event study diagnostic: fit a trailing market/sector factor model using only pre-event returns; measure post-receipt abnormal returns/volatility over predeclared horizons. Cluster uncertainty by event/date and handle overlapping stories. This establishes association under assumptions, not causality.
- Prevent revised full-text, late entity mappings, corrected event clusters, same-event syndications and immature outcome labels from crossing training/test boundaries. Split by event cluster and chronological time; purge overlapping target horizons.
- Report calibration/Brier/log loss, PR-AUC and ROC-AUC, warnings per year, time under warning, lead distribution, coverage, false alarms and abstentions. Bootstrap at the event/dependence level; thousands of headlines are not thousands of independent crises.
- Use ALFRED vintage data where the required series actually has vintages, rather than claiming publication lags repair revised FRED data. [ALFRED documentation](https://fred.stlouisfed.org/docs/api/fred/alfred.html) describes release/revision periods; verify series coverage individually.

Until acceptance, news remains a parallel contextual channel. Promotion into a statistical forecast requires a new versioned experiment and calibrated deployment policy; promotion into C9 changes scientific assumptions and is outside these routine integration fixes.

## 11. Connect news to the original globe (T13)

Call the existing `build_news_payload()` from the canonical application service. Replace the hardcoded fabricated-news status with per-surface/per-record status. Add a `news` transport branch with `revision`, `as_of`, `sources_health`, `signals`, `nodes`, `edges`, `sector_aggregates`, `coverage` and `limitations`. Keep quantitative CSRS in its existing branch.

Rendering contract:

```json
{"node_id":"asset:example","kind":"asset","place_id":"place:example",
 "geometry_id":"geo:example","coordinates":[85.0,20.0],
 "coordinate_order":"lon_lat","location_precision":"facility",
 "status":"derived","evidence_ids":["ref:example"]}
```

The numbers above are schema examples, not real facility data. Do not insert them into curated records.

Map edge: `edge_id`, `event_id/revision`, source node, destination node, mechanism, direction, confidence label, magnitude/unit or null, evidence IDs, known-at and validity. Use a versioned mapping from registry geometry IDs to existing Three.js meshes. Convert lon/lat to globe coordinates through one tested adapter; verify known points and antimeridian behavior. Sector nodes belong to the sector panel; locate their affected assets/regions on the globe rather than putting an industry at an invented coordinate.

Keep separate layers: event origins; potentially affected locations/assets; documented transmission paths; optionally measured market-pillar diagnostics. Use different legend/colour semantics. A positive/negative news mechanism is not CSRS green/red. Distinguish exact site, city, region and country-level locations by marker/outline precision. Unresolved location appears in the signal rail and review queue, not as a random point or headquarters.

On click, show: exact source statement, source/publication/receipt times, event revision, actor versus affected entity, mechanism path, evidence for each edge, unknowns, and allowed role actions. For country-origin policy, show the issuing jurisdiction; for a domestic plant event, show the facility. Edges should animate only when selected/relevant, with bounded visible count and deterministic prioritization. Show hidden-item counts; do not confuse visual culling with absent evidence.

Retain preview content in a separate dataset/layer. A real signal feed and fabricated geography may coexist, but labels must state that combination explicitly. No preview coordinates, stress numbers or dependencies enter `estimate_impacts`, portfolio coverage or alert dispatch.

Browser acceptance:

1. New actual source item appears automatically in Signals with stable ID and source link.
2. A sourced foreign-origin event resolves an evidenced path to Indian exposure and is clickable on the original globe.
3. A sourced domestic facility incident locates the site, not operator headquarters.
4. A source outage/retraction updates freshness/evidence state without erasing history.
5. Missing geography remains unresolved; filter/role/date changes cannot show a path from the wrong context.

Do not wait indefinitely for a new real incident. Use previously received sourced items through the same production path, clearly labeled by their historical receipt time, for the two map examples; separately prove one fresh item reaches the live feed. Synthetic fixtures remain test-only.

## 12. Role workflows and distinctive functionality

### 12.1 Minimum delivered workflows (T14)

**Retail route**

Use `WorkspaceStore.create_portfolio`, `preview_import`, `commit_import`, `current_holdings`, `holdings_as_of`, watchlists and preferences. UI flow: create → upload CSV/JSON → preview accepted/rejected rows, unsupported instruments and currency → confirm import → open saved snapshot after restart → inspect event-linked exposure and coverage.

Do not silently treat current holdings as historical holdings. Provide two explicit modes: actual holdings known/as-of the decision, or hypothetical application of current holdings to an old event. Record both `effective_at` and `received_at` for imports. Unknown prices/FX must produce partial valuation. Initial supported valuation can be INR cash equities plus explicit cash; derivatives require a separately implemented pricing model. Display gross/net/absolute exposure conventions for short positions; never divide by a near-zero net book value.

Reuse `portfolio_overlay` with a named measured dataset only. Keep market sector flags and news exposure as separate arguments/results, not a replacement mapping of categorical news into Hawkes flags. Show assessed value, unassessed value and denominator. For portfolio event exposure, `sum(abs(value_i) for unique affected holdings)/sum(abs(value_i))` is a coverage/exposure fraction; it is not a predicted loss.

**Institutional route**

Connect `ScenarioStore.save`, `revise_assumptions`, `record_run`, `review`, `scenarios`, `runs`, `compare`. Save baseline decision and all model/weight/portfolio/reference versions. Call existing `simulate_shock`/`simulate_policy` through a service; scenario results carry exact assumption IDs and actual execution time. A baseline change creates a new run/version. Require reviewer identity and prohibit self-approval where configured.

Offer separate scenario kinds: (a) pillar-rank sensitivity, (b) explicit regime-path sensitivity, (c) holding-price what-if, (d) documented event-mechanism what-if. The first two call C11/C9; a price what-if computes `sum(quantity_i * base_price_i * assumed_return_i)` in a common currency with missing positions explicitly excluded/quantified. It does not translate a 0.2 pillar bump into a 20% asset drop. Store assumptions, units, coverage, transaction-cost assumptions if used and result semantics.

No fitted macro-policy projection exists merely because the UI accepts a regime path. Keep it labeled hypothetical until a supported C7 `z → xi` model with verified exogenous-data timing is deployed. Load baseline weights by artifact ID; do not reconstruct today's default weights for an old scenario.

**Regulator route**

Connect `CaseStore.open_case`, `attach_evidence`, `assign`, `request_information`, `comment`, `record_decision`, `set_status`, `history`, `replay`, `export`. Support open → triage → review → decision → closure using the actual allowed state machine; adjust UI labels to existing enum values. Every mutation has expected version, actor, org and request ID. A closure requires rationale and evidence references. Retraction/correction does not delete earlier evidence or actions.

Keep existing local action journal usable as a cited source in cases; migrate/import by a documented mapping if needed, never silently discard it. An old role-only entry remains an unattributed legacy actor, not retroactively assigned to a real user. Record `operation_at=now` and `referenced_decision_at=historical_time` separately.

Institution-level systemic decomposition requires authorized institution submissions and a defined aggregation model. Until supplied, show the schema/import state and coverage, retaining tagged design previews. Do not infer private bank exposures from public headlines.

### 12.2 Distinctive additions worth building (T17)

These are proposed product features, not features the audit says already work. Build the first two for each role after the basic journey; the rest are ordered extensions.

| Role/feature | Concrete implementation | Dependencies | Acceptance/usefulness test |
|---|---|---|---|
| Retail: **Why this matters to my holdings** | Trace event → cited exposure edge → owned holding; show financial channel, unknown magnitude, data age and alternatives | T10–T14 | Every displayed affected holding has a reproducible evidence path; unrelated holding receives no invented link |
| Retail: **Blind-spot meter** | Split value into mapped, unmapped, stale-priced and unsupported-instrument buckets; drill down to missing evidence | Valuation/import coverage | Buckets reconcile to declared denominator; unknown exposure never displays as safe |
| Retail: **What changed since my last visit** | Diff event revisions/portfolio snapshots/decision IDs; group repeated stories into one update | Durable revisions/preferences | A syndicated repeat adds no new event; a true correction is visible |
| Retail: **Watch conditions and expiry** | Save user conditions such as a confirmed operational halt affecting a watchlist asset; source health and explicit expiry | Event rules + alert ledger | No alert from previews; duplicate polls don't duplicate alerts; correction explains reversal |
| Institutional: **Exposure bottleneck explorer** | Group portfolio exposure by shared supplier/port/input relationship; show unique affected holdings and alternative paths | Documented graph + owned books | Same asset reached by three paths counted once; country proxy cannot masquerade as issuer exposure |
| Institutional: **Assumption sensitivity ladder** | Save low/base/high user assumptions, compare scenario outputs, identify which assumptions drive the range | Saved scenarios and price/cost what-if | Zero-shock identity, monotonicity where mathematically expected, units and version parity |
| Institutional: **News–market divergence queue** | Show separate axes: documented material event exposure and market stress/return response; rank review candidates without summing scales | Live/news alignment | Review items contain both timestamps and coverage; no inferred causal claim |
| Institutional: **Evidence-change review** | Mark saved scenarios stale when a cited event/edge is corrected; create a new review run without changing old results | Version links + outbox | Retraction triggers exactly one review task and leaves original export reproducible |
| Regulator: **Decision-time evidence replay** | Reconstruct case evidence and model outputs knowable at a selected instant; compare with later corrected knowledge | Bitemporal event/reference records and cases | Later filing/edge/cluster revision cannot appear in the earlier view |
| Regulator: **Coverage and freshness atlas** | Map where evidence collection is strong/weak, source outages, unresolved locations and institution-submission coverage | Source health + coverage registries | Grey means missing/uncovered, not low risk; feed outage visibly changes coverage |
| Regulator: **Common dependency concentration** | Aggregate authorized institution exposures to common public/private dependency IDs with access-aware drill-down | Submission schema, consent/scope, graph | Aggregate reconciles to allowed submissions; suppressed/private data cannot leak through totals |
| Regulator: **Intervention review notebook** | Record hypothetical action, assumptions, rationale, observed subsequent outcomes and alternative explanations | Cases + scenario/outcome ledger | Separates scenario from actual action/outcome; never claims causal benefit from a before/after chart |

No new role is required initially. Add an analyst/reviewer capability as a scoped permission if event curation needs it; do not make every institutional user a source-of-truth editor. Public event corrections need versioned review attribution.

## 13. Operations, migration and reproducibility (T15)

### 13.1 Supported commands and deployment

Create or finish supported commands rather than scattered one-off scripts:

```text
run_live.py --status
run_live.py --replay <recorded-stream> --deployment <bundle> --store <isolated-db>
run_live.py --live --deployment <bundle> --store <runtime-db>
run_news.py --once --sources <approved-config> --store <news-db>
run_news.py --continuous --sources <approved-config> --store <news-db>
curate_reference_data.py --validate <directory>
curate_reference_data.py --import <directory> --expected-version <id>
run_product_acceptance.py --environment <isolated-config> --out <new-directory>
```

These are proposed interfaces; adapt existing scripts instead of creating duplicate entry points. Keep credentials in approved environment/secrets storage, excluded from logs/artifacts. A new machine should require explicit configuration, migrations and deployment artifact selection, not implicit access to the author's database.

Apply C1 migrations as part of the documented bootstrap/deployment workflow. Inspect `001_evaluation_identity.sql` and existing schema before planning another migration; do not assume earlier schema defects remain unfixed. Validate current rows before tightening constraints. Back up and migrate disposable copies first; preserve original source DB read-only until a separately identified migration/write target is authorized.

### 13.2 Alerts and delivery

Separate market threshold crossings, news review alerts, source outages and case notifications. Persist alert policy ID, event/decision IDs, state, actor acknowledgement and dedup key. Add hysteresis/cooldown only as explicit product alert policy; do not silently change scientific evaluation thresholds.

First delivery transport: **in-app inbox**, requiring no third-party credentials or sending messages to others. Optional email/webhook adapters are opt-in after destination verification/authorization. Delivery worker records attempts and final outcomes; `queued` is not `delivered`. Use receiver idempotency where possible and backoff/dead-letter handling. Prevent a reconnect backlog from producing hundreds of obsolete current alerts; mark catch-up alerts with their original times and an explicit policy.

### 13.3 Monitoring and recovery

Track source last successful check, newest observation, data age, freshness budget, parse failures, queue depth/oldest item, truncation, unresolvable entities, extraction exceptions, model/fit age, warmup state, decision latency, outbox lag, authorization denials and disk space. Separate ingestion age, processing duration and render acknowledgement latency. Do not log holdings, secrets or full restricted news bodies in generic diagnostics.

Bar-close-to-screen measurement includes provider lag + batching + computation + persistence + UI refresh, not only Python compute duration. Report p50/p95/p99 and maximum, with hardware/load and omitted intervals. Aim for the specification's <5-second path for supported bar decisions; if heavy refits or the chosen UI poll prevent it, expose the missed target rather than redefine the measurement.

Use consistent SQLite backup APIs or a stopped/checkpointed store, not copying one live DB file without its journal state. Use a supported PostgreSQL dump/base-backup method appropriate to the deployment; then actually restore to a clean target and reconcile logical IDs/hashes and migrations. [PostgreSQL backup documentation](https://www.postgresql.org/docs/current/backup.html)

Proposed local-shadow recovery acceptance: lose no **committed** decisions or user mutations; resume/rebuild within five minutes on the measured test dataset; explicitly disclose any unpersisted raw ticks that cannot be recovered. This is a proposed engineering SLO, not an existing guarantee. Persist raw batches before inference if they are required for exact restart replay.

### 13.4 Reproducibility manifest

Include source-code identity (relevant scripts and frontend as well as Python package), dependency lock, calendar, universe/reference snapshots, model/weights, feature/schema versions, input batch content IDs, extractor/rule versions, parameters, random seeds and time policy. Separate science identity from presentation build identity so a CSS change need not masquerade as a new model experiment.

For already-fixed run-store issues, retain existing tests. Verify completion is atomic with report/point completeness, completed runs cannot accept contradictory additions, and report revisions are explicit. Do not reimplement a fix solely because the older audit mentioned it.

## 14. Validation plan and release gates

### 14.1 Regression by finding

| Finding | Required new or adapted regression |
|---|---|
| R01 | Supported CLI with real `InferenceService` (not constant callback) produces stored C8/C9 result from recorded raw input |
| R02 | Null score, future time, recent replay, disconnected feed, stale required input, incomplete warmup and insufficient coverage all produce explicit non-current state |
| R03 | Finalized window cannot reopen with empty accumulator or after restart; volume boundary, duplicate and out-of-order cases |
| R04 | Restart during input/state/result/outbox commits; token expiry; final close drain; holiday and split session; bounded memory |
| R05 | Browser: each role landing page, same-role click, lost response/retry, stale context, request status visible on map |
| R06 | Revoked cached principal; disabled user; revoked session/membership; cross-org list/read/export/mutate; cache and browser payload isolation |
| R07 | Actual configured source acquisition → current Signals through supported app; stale/outage state and duplicate poll |
| R08 | Plant versus headquarters, explicit place/asset extraction, unresolved locations, foreign-origin→India path and real renderer consumption |
| R09 | Ten copies from one provenance root count once; conflicting independent reports remain visible; cut/hike/hold; proposed/actual/denied; quantity units |
| R10 | Restarted portfolio import/history, saved scenario run/review/comparison, scoped case assignment/evidence/decision/closure |
| R11 | Exiting/entering basket fixture changes actual fitted counts correctly; manifest matches inputs |
| R12 | Schedule operates end-to-end; outbox/inbox; migrate clean DB; restore backup; measured source-to-screen latency |

### 14.2 News quality evaluation

Build a cited review corpus of at least 300 items across six initial event families and multiple publishers, including negative/irrelevant stories, copied reports, corrections, location ambiguity and opposite actions. Proposed split: 120 development items and 180 held-out items, stratified where possible; all versions/syndications of an event stay in one split. If there are too few real examples for a family, mark that family review-only. Do not replace missing real examples with fabricated evidence.

Annotate event type/action/modality, quantities/units, actor, facility, origin, effective time, independence roots, plausible documented target paths and unresolved fields. Obtain a second review on disputed/high-impact cases; preserve disagreements. Economic direction labels must allow ambiguous/conditional, not force a bullish/bearish answer.

Proposed engineering gates, to freeze before examining the holdout:

- All deterministic timing/authorization/dedup/revision invariants pass.
- At least 95% precision among auto-resolved entity/facility links in held-out data, with sample count and confidence interval reported; report recall/abstention too. Sparse families remain review-only even if their tiny sample is perfect.
- At least 95% exact action/quantity-unit correctness among auto-published supported cases; all designated hike/cut/negation hard cases pass. Report per-family errors, not only an aggregate.
- Every displayed impact has source evidence, method/rule version and a documented path or direct relationship; 100% schema/provenance validation.
- No confidence increase from known duplicate/syndicated copies; no future revision in earlier replay.
- Failed gates route cases to review or reduce declared coverage. Do not lower the gate after seeing results to call the feature complete.

These numbers are proposed product-quality targets, not facts about current performance or guarantees of financial accuracy. Human review/abstention remains valid functionality. Sentiment F1 cannot substitute for origin resolution or mechanism correctness.

### 14.3 Test execution strategy

Reuse audit scripts as executable bug reproductions, adapting assertions into regression tests without overwriting the original evidence. Run targeted tests after each slice, then affected contract tests. Re-run expensive numerical suites only when their code, dependencies, time scaling, adapters or scientific assumptions change. A timestamp inference refactor legitimately requires equivalence/numerical regression; a role-route CSS change does not.

Add actual browser tests to the existing headless Edge harness for supported journeys and network/response failures. Keep deterministic fixture mode and real-source smoke mode separate. Browser tests must inspect request acknowledgement and displayed decision/event IDs, not just screenshot presence. Use disposable stores and explicit test identities. Never let tests discover and mutate the user's production/source database by default.

### 14.4 Staged acceptance

**Gate A — connected recorded-input product:** deterministic raw-input replay through the live service; real sourced article through news processing/map; all three role journeys durable; no authentication/publication defects; preview segregation; restart tests. Credentials are not required to implement this gate, though real source records must be properly attributed.

**Gate B — operated local shadow service:** configured broker/news sources, full supported session including close, reconnect/token-expiry drill, current UI refresh, actor audit, alerts/inbox, backup/restore. Run at least five full shadow sessions, including fault drills, as an initial operational sample; it does not establish 99.9% uptime or predictive skill. Document actual hardware and workload.

**Gate C — predictive validation:** prospective frozen protocol, sufficient matured outcomes, declared baselines, calibrated probabilities/uncertainty and false-alarm results. Duration is event/sample-driven; five shadow sessions cannot establish crisis prediction. Preserve honest failure if edge is absent.

**Gate D — broader deployment:** TLS, at-rest protection appropriate to the chosen host, secret rotation, account lifecycle, retention decisions and measured 100-user workload if that NFR remains required. These are deployment acceptance tasks, not prerequisites for fixing a local role button. Do not claim regulatory audit compliance from an append-only SQLite trigger.

## 15. Remaining scientific/data work that integration must not conceal

1. Rebuild corrected intraday jump/Hawkes artifacts in a new run namespace after point-in-time basket repair; old fitted outputs do not become corrected simply because extraction code changed.
2. Preserve original-Hamilton exclusion and compare original versus Astra variants by explicit model ID. Diagnose regime support separately; do not remove the pillar or relabel a volatility state as probability of a named crisis.
3. Resolve FR35 Table B epoch/fold policy through a versioned decision; preserve prior preregistration and report historical designs as they were. Do not “fix” it by deleting required configurations.
4. Populate the tariff registry with sourced announcement/effective dates, units and declared severity convention. A provisional tariff crisis label is not confirmed validation evidence.
5. Complete macro-source fidelity/vintage policy, flow publication timestamps and numerator/denominator scope. `20:00` ingestion watermarks cannot prove a source was known before its actual release.
6. Complete supported official Nifty 500 benchmark acquisition/overlay and reconstruction correlation; do not label the equal-weight research index Nifty 500. Complete Yang–Zhang versus available five-minute RV overlap validation and publish coverage.
7. Calibrate RMT/SCA/fusion quantities and thresholds only under a declared training protocol; retain current quantities and exclusions for compatibility. Statistical calibration and a UI confidence bar are different deliverables.
8. Cross-market frozen-model transfer and broad robustness remain scientific acceptance work if still in scope. Do not claim that better engineering satisfies AUC, lead-time or calibration targets.
9. Defensive-action drawdown reduction requires an explicit position/action/cost/valuation experiment and comparison policy. Keep `None/unmeasured` until then; no invented playbook gains.

These tasks can continue after the connected product exists, except input-integrity issues that affect live/replay correctness, which are earlier dependencies. No promise is made that completing them will produce predictive edge.

## 16. Decisions Claude may make, and decisions that need a recorded boundary

Proceed autonomously with reversible wiring, tests, bug fixes, source adapters using permitted public data, source-referenced registry curation, schema designs/migrations on disposable targets, explicit provenance and role workflow implementation.

Record an ADR before implementing: product schema version 2; timestamp/cadence/checkpoint semantics; source configuration/rights; event mechanism rules; reference-data taxonomy; notification policy; numerical ranking if introduced. An ADR does not itself require another permission request when already within the user's authorized implementation scope.

Do not silently change: mathematical `shared_types`, original pillar eligibility, scientific weights/thresholds, preregistered target/labels, user-data visibility, production DB migration target or retention/deletion policy. Seek a focused decision only where the repository/user instructions actually require it or the choice is destructive/external/paid. Continue independent authorized work while a specific dependency is pending.

No fresh confirmation is needed for routine frontend/backend integration already requested. No model upgrade, major framework replacement or additional paid service is required by this plan.

## 17. Exact first implementation instruction

Start with T00–T03 as one reviewable batch:

> Work directly in `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`. Read `AGENTS.md`, the Astra notices, `docs/INDEPENDENT-PRODUCT-READINESS-AUDIT-2026-10-16.md`, `docs/PRODUCT-CONTRACTS.md`, and this development plan. Preserve all existing uncommitted work; do not push, merge, reset or modify model assumptions. Reconcile the current state and ownership first. Implement the audit's publication/future-timestamp defects, closed-bar finality and volume-boundary defects, and role-route/same-role acknowledgement defect through the canonical application. Add focused regression tests reproducing R02/R03/R05 and exercise the actual browser. Use isolated stores; do not connect to a broker or write the source database for these tests. Record evidence and update separate implemented/integrated/real-input/operational status columns. Do not call this batch live inference completion: R01 requires T06–T08. Then continue in the dependency order in this plan, reusing existing modules and preserving all three pillars. If an external credential blocks a real-source gate, record that gate as pending and continue unaffected implementation.

## 18. Handoff and progress discipline

For each completed ticket, Claude must return: concrete behavior now possible; files changed; relevant interface/schema changes; tests with counts and exclusions; actual supported-entry-point evidence; remaining external/scientific limitations. Keep `docs/IMPLEMENTATION-STATUS.md` and a compact `docs/NEXT-SESSION.md` up to date before a session ends. Save work in small coherent steps; do not wait until the whole product is finished to record state.

Do not re-audit the entire repository on every continuation. Read the status register, recent diff and evidence for the next ticket, verify drift, then proceed. Do not generate another speculative roadmap instead of implementing the authorized first batch.

The finished engineering product must demonstrate the exact journeys: **market observation → timestamped risk output → screen**, **sourced event → documented exposure → original globe → evidence**, and **authenticated role → owned durable action → replayable history**. Predictive performance remains a separately measured result.


