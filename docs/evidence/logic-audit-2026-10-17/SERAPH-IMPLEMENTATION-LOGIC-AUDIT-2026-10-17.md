# SERAPH implementation logic audit — 17 October 2026

Repository inspected: `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`.

Scope: selected live inference, persistence, scheduling, dashboard, scenario and validation paths beyond the preceding news audit. This is a targeted correctness audit, not an exhaustive mathematical certification or a new project-completion estimate. No project implementation or production database was modified; no model fitting, historical replay or full test suite was run. Ten bounded counterexamples ran against in-memory objects or disposable databases. The accompanying `seraph_logic_audit_probe.py` and `seraph_logic_audit_evidence.jsonl` reproduce and record them. Temporary database directories were removed by the probe's context manager.

Evidence labels: **reproduced** means a counterexample was executed; **code-confirmed** means the implementation and caller establish the defect but a complete user workflow was not executed. A reachable defect is not proof it has already damaged saved results. P1 means fix before relying on the affected feature; P2 means a narrower or currently dormant defect.

The original three pillars and preregistered evaluations should remain intact. Existing Astra negative results are not overturned by this audit. In particular, the legacy lead-time defect below was not found in the Astra event-warning path.

## Findings

### L01 — P1 — Normal live polling delay fails the information-cutoff check

**Reproduced predicate; code-confirmed integration.** `seraph/live/loop.py:192` uses `bar_end` as publication `as_of`, but `_input_provenance` at line 226 stamps `received_at=moment`, the later polling time. `InputProvenance.reasons` correctly rejects arrival after the cutoff. A bar closing at 10:00 and processed at 10:00:01 therefore receives `bar:X:not_known_at_cutoff`. The service adapter also chooses bar end for its request at `seraph/live/engine_adapter.py:126`, withholding an emission computed just after bar close.

**Impact:** normal asynchronous ingestion/computation can prevent current publication even with an otherwise working feed and model. Arrival time is also inferred from the polling moment rather than retained as actual receipt provenance.

**Fix:** retain distinct bar end, actual receipt, emission availability and decision cutoff. Decide at a timestamp when all admitted information is available, while retaining bar end as the market observation time. Do not fix this by pretending inputs arrived before they did or relaxing causality.

**Acceptance:** a bar received one second after close may contribute to a later valid decision; it must remain unavailable to a decision at bar close. Test delayed and out-of-order receipts through the actual loop/adapter.

### L02 — P1 — Warm start marks data assimilated without initializing the filter

**Reproduced.** `seraph/live/inference.py:442–462` loads ECDF history and sets `_assimilated`, but never updates the Kalman filter. The next decision therefore skips the last historical vintage as already assimilated. Probe result: diagnostic `eligible=true`, `carried_forward=true`, rank null, all filter observation times null, and no CSRS.

**Impact:** a supposedly warmed service can lack the actual state its diagnostics claim to carry forward. Daily pillars may wait for another emission before entering the filter. The stock launcher currently does not call this warm-start path, which limits current exposure but is itself an integration gap.

**Fix:** define warm start as ECDF-only or full filter initialization, explicitly. For full warm start, replay eligible emissions chronologically through standardization and C8. For ECDF-only loading, do not mark the latest observation filter-assimilated. Enforce deployment eligibility while loading history.

**Acceptance:** after warm start, a decision with no new daily emission retains a valid historical state with correct age, without duplicate ECDF entries or repeated assimilation.

### L03 — P1 — An older incoming vintage overwrites the latest service vintage

**Reproduced.** At `seraph/live/inference.py:530`, every eligible incoming vintage replaces `_latest[producer]`; sorting the current batch does not compare it against existing state. After ingesting 09:55, supplying a delayed 09:20 vintage makes the service's latest timestamp 09:20 while C8 correctly retains 09:55 and emits an older-observation warning.

**Impact:** service provenance, rank history and filter state disagree. Subsequent carry-forward behaviour refers to the older vintage, potentially until another new one arrives.

**Fix:** enforce a cross-batch ordering/revision contract. Distinguish a genuine correction from an old delivery and keep superseded deliveries in history without making them the current input.

**Acceptance:** shuffled/duplicated deliveries produce the same current state and provenance as ordered delivery; corrections have explicit revision identities.

### L04 — P1 — Checkpoints accept materially different numerical configuration

**Reproduced.** Snapshot/restore at `seraph/live/inference.py:707–750` checks pipeline version and session dates, but not process noise, weights, session hours or equivalent effective configuration. A checkpoint made with `q_proc=0.001` successfully restores into `q_proc=0.9`; the immediate snapshot identity is unchanged. Subsequent prediction covariance will follow the new configuration. Bundle IDs are stored but are not validated by restore. The calendar identity hashes dates, not session windows.

**Impact:** restart can silently change the model while retaining apparent state continuity. This is a reproducibility defect, not evidence that every current restart changes the model.

**Fix:** persist and validate a canonical effective-configuration fingerprint covering weights, noise, standardizer policy, session windows, model deployment identities and versions. Restore diagnostic rank/assimilation metadata explicitly as well.

**Acceptance:** incompatible configurations are refused before mutating state; identical configurations reproduce both numerical state and diagnostics after restart, including split sessions.

### L05 — P1 — Duplicate decision IDs accept conflicting contents

**Reproduced.** `seraph/live/store.py:379` returns the existing decision before checking incoming payload, state, timestamps or publication status. Probe: commit `csrs=0.1` as withheld, then reuse the ID with `csrs=0.99` as current. The second call reports replay success and returns the old payload instead of reporting a conflict.

**Impact:** an ID collision or caller bug is hidden as successful idempotency. A caller can think a changed decision has been committed when it has not.

**Fix:** define immutable input/decision identity and compare canonical hashes on replay. Identical repeats return the old record; changed repeats fail explicitly. Resolve concurrent identical inserts atomically.

**Acceptance:** same-ID/same-content is idempotent; same-ID/different-content fails without altering stored records, including concurrent writers.

### L06 — P1 — Live decision reads ignore stream identity

**Reproduced.** `LiveStore` accepts `stream_id` and scopes its head, but `latest_decision()` at `seraph/live/store.py:448` reads all `live_decisions`. A second stream sharing a database has an empty head yet receives the first stream's latest decision. Decision identity is also global in the current schema.

**Impact:** consumers can combine one stream's health with another stream's score if multiple streams share a database. The ordinary default uses one stream; this is a conditional multi-stream defect, not evidence of current cross-stream contamination.

**Fix:** either explicitly reject multiple streams per database or carry stream identity consistently through decision keys, reads, checkpoints and outbox records.

**Acceptance:** two streams cannot read or overwrite each other's decisions; health and score always refer to the same stream.

### L07 — P1 — A sufficiently old score can still be called current

**Reproduced API behaviour.** `seraph/dashboard/current_reader.py:124` defaults `max_age=None`; line 154 then disables score-age rejection. The actual caller in `prototype_app.py:92` supplies no bound. A seven-day-old score with a fresh worker head returns `is_current=true` in the probe.

**Impact:** score freshness depends on worker freshness unless a caller remembers an optional setting. A fresh head with an old as-of can arise from delayed commits; the probe supplies that state directly and does not claim it is in the current production store.

**Fix:** require an explicit, calendar-aware decision freshness policy independent of worker heartbeat. Define after-hours presentation separately from a current open-session reading.

**Acceptance:** old scores stay inspectable but never become current merely because a worker is active or a delayed record was committed recently.

### L08 — P1 — The live metric receives a dictionary instead of a scalar

**Reproduced library boundary; code-confirmed transport.** `LiveDecision.csrs` is a dictionary, and `scripts/run_live.py:158` persists `decision.describe()`. `seraph/dashboard/prototype_app.py:101` passes `current.payload['csrs']` directly to `st.metric`. The installed Streamlit metric parser raises `StreamlitInvalidParameterTypeError` for `{'csrs': 0.4}`.

**Impact:** the live panel can fail as soon as it receives an actual scored decision. Null-score fixtures do not exercise this case.

**Fix:** project the scalar CSRS from the stored typed envelope and handle missing scores explicitly; validate the persisted-to-view contract.

**Acceptance:** render the ordinary live panel from a real-shaped persisted decision with a non-null composite, then cover withheld and absent scores too.

### L09 — P1 — An expired job can overwrite its successor's checkpoint

**Reproduced.** `seraph/operations/jobs.py:118` grants expiring leases, but checkpoint writes at line 153 do not verify current ownership. There is no renewal path. After lease A expires and B acquires, A can still overwrite B's checkpoint. Probe result: lock owner `new`, checkpoint owner `old`. `clear_checkpoint(job)` is likewise not owner-scoped.

**Impact:** a job exceeding its lease can overlap its successor, corrupt resume progress or clear the successor's checkpoint. Default lease is 30 minutes; this is not a claim that today's short news polls exceed it.

**Fix:** renewable leases plus monotonically increasing fencing tokens checked by every protected mutation. Scope checkpoint clearing to the owning run/token. Renewal alone does not protect against paused old workers.

**Acceptance:** simulate expiry/takeover; the old worker cannot checkpoint, clear progress or commit protected output afterward.

### L10 — P1 — Scenario history loses the assumptions and inputs behind old results

**Code-confirmed.** `seraph/decision_support/scenarios.py:162–196` overwrites assumptions while incrementing a version. The run hash includes inputs and assumption version, but `scenario_runs` stores only the hash, results and basic execution metadata. It stores neither the original inputs nor the historical assumption set/version as retrievable fields.

**Impact:** an old run cannot be reconstructed from this store after assumptions change. A hash can verify known content; it cannot recover missing content. This contradicts the method's claim that old runs keep pointing at old assumptions.

**Fix:** immutable assumption revisions and canonical run inputs, baseline identity, step definition and engine version; each run references exact revisions.

**Acceptance:** save a run, revise assumptions twice, reopen the first run and recover all original inputs and assumptions without external files or caller memory.

### L11 — P1 — Scenario approval does not identify the version approved

**Code-confirmed.** `scenario_reviews` and `review()` at `seraph/decision_support/scenarios.py:116,202` attach approval to a scenario ID only. `scenario()` returns these reviews beside the current, mutable assumptions. Revising assumptions neither scopes the old approval to a revision nor marks it stale.

**Impact:** an earlier approval can be displayed alongside materially different assumptions without identifying the mismatch. No claim is made that a downstream execution gate currently auto-accepts it.

**Fix:** bind reviews to an immutable scenario/run content hash. Show old reviews as historical and require new review for changed content where approval is required.

**Acceptance:** approval of revision 1 cannot be presented as approval of revision 2; reviewer identity, exact content and review timestamp remain available.

### L12 — P2 — Legacy lead-time metric rewards an unrelated old alarm

**Reproduced; legacy helper.** `seraph/validation/harness.py:60–74` searches the entire prefix before each onset and selects the first threshold crossing. It implements neither the documented sustained crossing nor a bounded pre-onset matching window. One isolated alarm followed by four quiet sessions receives five sessions of lead time. The same early crossing can be credited to multiple later crises.

**Impact:** misleading lead-time values if this helper is used for reporting. Search found the function and its tests, but no production caller in `seraph` or `scripts`. Astra uses the separate `prediction/evaluation.py:event_warnings` path, so this finding does not invalidate its saved results.

**Fix:** align the helper with a documented event/episode matching definition; deprecate it if unused. Preserve prior results and do not silently change preregistered research definitions.

**Acceptance:** old, expired and isolated alarms do not receive credit contrary to the declared policy; misses and unassessable events remain distinct.

## Missing integrations and operational gaps — separate from the 12 defects

1. **Stock live entry point installs `NullProducers`.** `scripts/run_live.py:87` wires the inference service but does not connect real pillar producers. Connecting a broker alone will not create the promised live three-pillar engine. Implement and validate the bar-to-feature-to-pillar adapters and model deployment lifecycle before claiming live scores.
2. **The advertised two-second live refresh is not wired.** `LIVE_POLL_SECONDS=2.0` in `prototype_app.py:33` has no scheduling use. The panel reruns when the app reruns; the separate current-news timer can incidentally cause 30-second refreshes. Historical-news mode does not supply that timer. Add an actual independent live polling mechanism and verify idle-page updates.
3. **Live UI depends on an archive database existing.** `prototype_app.py:124` returns before `live_panel` when the prototype archive store is missing. A valid live store alone cannot open its panel. Render the independent live surface before checking historical-run availability.
4. **Portfolio dispatch always supplies empty measured flags.** `console_backend.py:254` calls `portfolio_overlay(holdings,{})`. It honestly reports uncovered exposure, but does not consume measured flags even if a future producer supplies them. Connect the approved measured-flag/coverage adapter; do not substitute news estimates as Hawkes flags.
5. **No-new-bar passes are not independent heartbeats.** `scripts/run_live.py:151` reuses `evaluator.results[-1]` even when the current pass produced no evaluation. The store's duplicate return leaves the head unchanged. The worker-health view treats head age as pass age, so an active idle worker can look stopped. Persist a separate pass heartbeat and commit a decision only when that pass produced one. Do not refresh the old decision timestamp as a workaround.

## Recommended repair order

1. Define and fix timestamp/provenance semantics (L01), then warm start and vintage ordering (L02–L03).
2. Fix checkpoint/configuration identity, immutable decision replay and stream scoping (L04–L06), then job fencing (L09).
3. Fix scalar live rendering and independent freshness/heartbeat/refresh behaviour (L07–L08 and gaps 2, 3, 5).
4. Connect actual pillar producers and measured portfolio flags, using the corrected runtime contracts (gaps 1, 4).
5. Make scenario revisions, inputs and reviews reproducible (L10–L11).
6. Quarantine or correct the legacy metric with an explicit policy decision (L12).

For each change, add the specific counterexample as a regression and check the relevant caller, not only the helper. Only broaden test execution when the change's dependencies warrant it. Do not rerun expensive market experiments merely because a UI or operational bug was fixed.

## Boundaries of this conclusion

The audit found substantial implementation defects, but did not prove that all production scores are wrong. Some defects are blocked today by missing live integrations, and some are conditional on restart, reordering, multiple streams or lease expiry. Existing tests and prior browser evidence can coexist with these findings because their inputs may not cross these boundaries. Remaining mathematical correctness, authenticated deployment behaviour and full feature acceptance require their own focused checks; this report does not certify them.
