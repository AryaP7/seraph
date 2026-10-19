# SERAPH development status register

Created 2026-10-16. One row per backlog ID from
[AUDIT-2026-10-16-BACKLOG.csv](AUDIT-2026-10-16-BACKLOG.csv) (59 items).

**States:** `not started` · `in progress` · `implemented, unverified` ·
`verified` · `blocked on external input` · `scientifically unresolved`.
Software completion and empirical acceptance are tracked separately: a
`verified` software row never implies a scientific acceptance result.

## Audit-finding re-verification (2026-10-16, this session)

The audit described the working tree at `51680bb`. Every finding was re-probed
against the current checkout before planning. Evidence:
`docs/evidence/REVERIFY-2026-10-16.json`.

| Finding | Still present? | Evidence |
|---|---|---|
| A01 archive replay by calendar date vs fixed 15:30 clock | **yes** → now **fixed** | `2024-11-01` and `2025-10-21` single-date replays both raise `Future or missing pillar information timestamp`; because `run_archive` replays chronologically from 2005, **every** range ending on/after 2024-11-01 fails |
| A02 all absence mapped to `structural` | **yes** → now **fixed** | transient RMT outage moved mask `[T,T,F] → [T,F,F]` |
| A03 completed run accepts out-of-range date | **yes** → now **fixed** | `put()` on a `complete` run with `2099-12-31` succeeded; now rejected (`FIX03`) |
| A04 report overwrite / finish-before-report | **yes** → now **fixed** | second `report()` silently replaced the first; now appends a revision, and a run requiring a report is not `complete` without one (`FIX03`) |
| A05 whole-array state quantiles | **yes** → now **fixed** | 28/40 earlier bucket assignments changed after appending 20 future values; production bases now move 0 of 40, and the deprecated `full_sample` path is marked non-causal (`FIX04`) |
| A06 `validation_results` key lacks table/design identity | **yes** (static) | `seraph/store/schema.sql:206` unchanged |
| A07 FR35 Table B two-epoch vs six-epoch | **yes** | expected-failure test still pins the disagreement |
| A08 Hawkes writer stores `alpha_beta=None`, `flag='none'` | **yes** (static) | `scripts/write_hawkes_production.py:224` |
| A09 backfill uses latest universe snapshot | **yes** (static) | `scripts/write_hawkes_production.py:167` |
| A10 any local user may select regulator | **yes** (static) | `prototype_app.py` role switch is unauthenticated |
| A11 legacy `datasource.py` mixes latest rows, no real cache | **yes** → now **fixed** | component reads bounded by a single resolved `as_of`; `st.cache_data` actually applied (`FIX10`) |
| A12 bridge `pending` latch, regenerated tool forms | **yes** → now **fixed** | in-flight record with bounded timeout and retry, preserved drafts, context-bound results (`FIX11`) |
| A13 journal no-op update raises `IntegrityError` | **yes** → now **fixed** | `UNIQUE constraint failed: action_events.run_id, action_events.seq`; now returns `{noop: true}` (`FIX08`) |
| A14 missing ISIN file ⇒ `is_equity()` accepts everything | **yes** → now **fixed** | `is_equity()` raises; C3 returns `MISSING_DEPENDENCY` (`FIX09`) |
| Source PostgreSQL 5433 / 5434 | **still unreachable** | TCP connect refused on both; 8512 listening |

No audit finding was found already fixed by someone else. The "now fixed"
annotations are this session's work, each re-probed by
`scripts/reverify_audit_findings.py` after the change. Nothing was marked
complete without re-checking.

---

## Phase 1 — historical execution and persistence

| ID | P | Area | State | Implementation | Verification | Blockers |
|---|---|---|---|---|---|---|
| `FIX01` | P0 | Orchestration | **verified** | `seraph/market_calendar/sessions.py` (new package: `TradingSession`, `SessionCalendar`, `DecisionClock`, declared `SPECIAL_SESSIONS`); `seraph/orchestration/prototype.py` as-of vintage selection + session-aware decision timestamps; `seraph/orchestration/original_execution.py` session-close cutoff; `seraph/reconciliation/time_clock.py` + `kalman.py` optional per-session hours; `scripts/run_prototype.py --decision-clock`. [DR-01](decisions/DR-01-2026-10-16-session-clock-and-absence.md) | `tests/test_fix01_session_clock.py` **16 passed**. Full supported history replayed 2005-01-03→2026-08-21, **5361 points**, under both clock policies, into a new store; **zero future-information violations**; deterministic retry reproduced run identity and content. Evidence: `docs/evidence/FIX01-FIX02-REPLAY-2026-10-16.json`. COVID window changes on 11 of 81 dates, max \|ΔCSRS\| 0.0026, no mask or alert-level change — a **correction**, explained in DR-01; baseline run preserved | — |
| `FIX02` | P0 | Orchestration | **verified** | `InferenceSession.step()` requires an explicit `absence`/`absence_reason` for every ineligible pillar and raises rather than guessing; archive and fresh-source adapters declare theirs; a later vintage becomes a transient `not_yet_available` withholding. [DR-01](decisions/DR-01-2026-10-16-session-clock-and-absence.md) | `tests/test_fix02_absence_semantics.py` **10 passed**: transient outage keeps the mask `[T,T,F]` (was `[T,F,F]`), covariance grows without a fictitious measurement, structural excludes, undeclared absence raises, unknown reason rejected, historical noncoverage→first observation, repeated vintage is stale, research exclusion persists | — |
| `FIX03` | P1 | Persistence | **verified** | `seraph/orchestration/run_store.py`: `running → inference_complete → complete`; `put()` enforces declared range + point schema + sealed state; `finish()` verifies the exact date set and records `sealed_dates`/`content_hash`/`sealed_at`; immutable `report_revisions` with triggers; additive migration of legacy stores. [DR-02](decisions/DR-02-2026-10-16-run-sealing-and-command-results.md) | `tests/test_fix03_fix08_persistence.py` **18 passed** (shared with FIX08), incl. interruption-before-report and legacy migration | — |
| `FIX08` | P1 | C11 | **verified** | `action_commands` separated from `action_events`; a no-op consumes no journal sequence and still returns an idempotent result. [DR-02](decisions/DR-02-2026-10-16-run-sealing-and-command-results.md) | no-op update now returns `{noop: true, last_seq: 1}` instead of `IntegrityError`; retry, conflicting retry, real-change-after-no-op, repeated retraction across restart, transactional rollback all covered | — |
| `FIX09` | P1 | C3 | **verified** | `classification_status()` + `ClassificationUnavailable`; `is_equity()` raises instead of accepting everything; `build_snapshot()` returns `MISSING_DEPENDENCY` with an opt-in `allow_unclassified` degraded mode carrying `PARTIAL_COVERAGE`; Hawkes basket refuses an unclassified universe. [DR-02](decisions/DR-02-2026-10-16-run-sealing-and-command-results.md) | `tests/test_fix09_classification_policy.py` **9 passed** | — |
| `FIX10` | P1 | C12 | **verified** | Canonical route caches one run/as-of bundle scoped by `(store, run, role)` and invalidates after a write; legacy `datasource.py` resolves a single `as_of` and reads every component bounded by it, labelling stale/unavailable components; `st.cache_data` really applied, keyed by `CacheScope` with identity slots reserved for `AUTH02`. [DR-03](decisions/DR-03-2026-10-16-coherent-reads-and-request-lifecycle.md) | `tests/test_fix10_fix11_transport.py` (16 Python tests): stale component labelled, aligned bundle coherent, missing component `unavailable`, component queries bounded by `as_of`, cache scope carries org, warm second read | — |
| `FIX11` | P1 | C12 | **verified** | `bridge.js` in-flight record with 15 s timeout, visible `#req-status` (`aria-live`, not colour-only), retry reusing the same idempotency id, duplicate suppression, draft capture/restore; `dispatch()` stamps `{run_id,date,role,request_id}` and `project_run()` discards a non-matching result with a reason. [DR-03](decisions/DR-03-2026-10-16-coherent-reads-and-request-lifecycle.md) | 8 harness-driven tests via `tests/js/bridge_harness.mjs`, which runs the unmodified bridge in a Node VM: send → duplicate suppressed → timeout → retry same id → answer → draft preserved → context change → discard → accepts new work | — |

## Phase 2 — data foundation and research contracts

| ID | P | Area | State | Implementation | Verification | Blockers |
|---|---|---|---|---|---|---|
| `DATA01` | P1 | C1 | **implemented, blocked on external input** | `docker-compose.test.yml` (disposable, tmpfs, loopback-only, pinned image) + `scripts/provision_test_db.py`. Three independent guards: name must start `seraph_test_`, host must be loopback, and any E1–E14 table holding rows aborts provisioning | guard refusals exercised directly: `seraph`, `seraph_research` and a non-loopback host are all refused; `seraph_test_local` accepted | **Docker's Linux engine is unavailable** (`npipe:////./pipe/dockerDesktopLinuxEngine` absent). The database has never been started and the 13 DB tests have never run |
| `DATA02` | P1 | C2 | **blocked on external input** | — | — | source PostgreSQL unreachable on 5433/5434 |
| `FIX04` | P1 | C4 | **verified** | causal `train_prefix`/`trailing_window` bins, versioned and content-hashed; `UNDETERMINED` replaces the guessed middle bucket. [DR-04](decisions/DR-04-2026-10-16-causal-state-bins.md) | `tests/test_fix04_causal_state_bins.py` **14 passed**; production bases move 0 of 40 bins under future append, the deprecated path still moves 28 and declares itself non-causal | — |
| `FIX05` | P1 | C10 | **resolved (steps 1–4)** | [DR-05](decisions/DR-05-2026-10-16-fr35-table-b-scope.md) — owner chose Reading 1 on 2026-10-16: Table B is the two pre-Hawkes epochs, six-epoch run retained as Table C | `table_b_scope` is a named parameter with no default; the scope is inside the hashed design and the two readings hash differently; Table C emits 6 rows; the xfail is a real assertion and the diagnostic is inverted to guard the resolution | **step 5 is the owner's**: `preregistration.json` must be committed by a person before the first AUC, which is the whole point of pre-registration |
| `FIX06` | P1 | C1 | **implemented, unverified** | `seraph/store/migrations/` runner (ordered, once-each, SHA-recorded, drift-detecting, per-migration transactions) + `001_evaluation_identity.sql`: adds `evaluation_runs`, widens the key to `(evaluation_run_id, table_id, pillar_subset, reconciliation_mode, xi_mode, epoch)`, adopts existing rows into `legacy_pre_migration`. [DR-06](decisions/DR-06-2026-10-16-product-subsystems.md) | `tests/test_fix06_evaluation_identity.py` **11 passed, 1 skipped**: the A/B collision is real under the old key and gone under the new one; the migration drops nothing; the runner refuses an edited applied migration | the SQL-executing test needs the blocked `DATA01` database |
| `FIX07` | P1 | C5 | **verified** | `seraph/pillars/hawkes/artefact.py`: `HawkesFitArtefact` persists mu/alpha/phi/dispersion, seasonality, training window, basket and diagnostics; `reconstruct_intensity()` rebuilds λ_t from the artefact alone; `BasketIdentity.validate()` rejects `latest_snapshot` for a historical window; `point_in_time_members()` replaces the latest-snapshot query; `write_hawkes_production.py` wired to both. [DR-06](decisions/DR-06-2026-10-16-product-subsystems.md) | `tests/test_fix07_hawkes_artefact.py` **17 passed**, including a JSON round-trip reconstruction and refusal of parameters that do not reproduce their own branching ratio | — |

## Phase 3 — authenticated workspaces

All in `seraph/identity/` + `seraph/decision_support/workspace.py`. [DR-06](decisions/DR-06-2026-10-16-product-subsystems.md)
Evidence: `tests/test_auth_identity_and_tenancy.py` **27 passed**,
`tests/test_port01_port02_workspace.py` **21 passed**.

| ID | P | State | Implementation | Verification |
|---|---|---|---|---|
| `AUTH01` | P0 | **implemented, unverified** | `OidcConfig`/`OidcVerifier`/`VerifiedSubject`; `IdentityRegistry.upsert_user` binds `(issuer, subject)` to a stable local user | every malformed-claim path tested (wrong issuer, wrong audience, expired, not-yet-valid, no subject); an unconfigured provider fails closed with no privileged fallback. **No OIDC issuer is configured, so the round trip has never run** |
| `AUTH02` | P0 | **verified** | `Scope` separates role from reach; `can()`/`require()`/`visible()` check every path; an unregistered resource is denied | two users in one org, two orgs, a scoped regulator, a forged role request, listing filtered by the same rule as reading, a regulator denied a user's private holdings despite in-scope org |
| `AUTH03` | P1 | **verified** | revocation by timestamp, never delete; membership revocation cascades to grants; session expiry and revocation | revoked grant stops access immediately; the `revoked_at` row is still present afterwards |
| `AUTH04` | P1 | **verified** | `WorkspaceStore`: portfolios, holdings snapshots, imports, watchlists, preferences — all identity-scoped | owned state survives restart, normalised and deduplicated, invisible to another organisation |

## Phase 4 — first news-to-map vertical slice

All in `seraph/news/` + `seraph/dashboard/news_view.py`. [DR-06](decisions/DR-06-2026-10-16-product-subsystems.md)
Evidence: `tests/test_news_pipeline.py` **41 passed**,
`tests/test_news06_overlays.py` **15 passed**.

| ID | P | State | Implementation | Verification |
|---|---|---|---|---|
| `NEWS01` | P1 | **implemented, unverified against a live source** | `Source` registry (rights, retention, poll policy, failure behaviour, `accessibility_verified`); `NewsStore.ingest` with bounded retries, cursors and per-source health | unregistered sources refused; a source that may not store full text keeps only a hash; retries bounded; failure recorded as missing coverage. **Nothing has been fetched over the network** |
| `NEWS02` | P1 | **verified** | observation id from `(source, reference, content_hash)`; changed content becomes a correcting story; `syndication_key` groups near-identical headlines | a double poll yields one observation; the earlier version is preserved; 10 syndicated copies → 1 event with 10 confirmations and 1 exposure |
| `NEWS03` | P1 | **verified** (machinery) / **registry empty by design** | `MasterData` with validity dates, parent links, abstaining resolution; curated CSVs refusing uncited rows | an asset's place is its own and an entity has none; ambiguous mentions abstain with candidates; an out-of-validity record does not resolve; uncited rows refused |
| `NEWS04` | P1 | **verified** (machinery) | `ExposureEdge` requiring evidence, and magnitude+unit together; `reachable()` keeps one path per target | an unevidenced edge is refused; a bare magnitude is refused; a diamond resolves to one path with the alternative reported; a chain is only as evidenced as its weakest hop; expired edges are not walked |
| `NEWS05` | P1 | **verified** | `ImpactEstimate` with five separate dimensions; severity from event type and stated quantities, never tone; versioned method id | the dimensions stay separate; an unknown size is said, not assumed; `not_a_loss_probability` travels with every estimate; two events on one target are two estimates |
| `NEWS06` | P1 | **verified** | `build_news_payload()` switches each surface between real data and an explicitly labelled preview | with no data every surface is a labelled preview; with data each carries source, both times, method and version; **news and Hawkes sector stress appear as two series with different units and are never merged** |
| `NEWS07` | P1 | not started | — | analyst review queue and a measured review set remain |
| `NEWS08` | P2 | not started | — | weather/commodity feeds remain |

Rule 4 (article text is untrusted) is enforced by `scrub()` and tested against
three injection shapes; the module has no write path to grants, commands or
regulator actions.

## Live market path (raised by the owner, 2026-10-16)

Not in the original 59-item backlog. SERAPH's CSRS is specified as a **current**
market risk score; everything built until now evaluates a chosen historical
date. See [DR-07](decisions/DR-07-2026-10-16-live-market-path.md).

| ID | State | Implementation | Verification | Blockers |
|---|---|---|---|---|
| `LIVE01` market clock | **verified** | `seraph/live/clock.py` — session state, incomplete vs closed bars, and a `recency()` gate returning `live`/`delayed`/`stale`/`historical_only` | session states incl. Muhurat and split sessions; partial bar marked incomplete; the current corpus resolves to `historical_only` | — |
| `LIVE02` feed adapters | **implemented, unverified** | `seraph/live/feed.py` — `KiteTickerFeed` (websocket), `ReplayFeed`, `NullFeed`; `resolve_feed()` never falls back automatically | refuses to start without credentials; replay never claims live; adapter admits it has never connected | **no Kite credentials; `kiteconnect` not installed** |
| `LIVE03` bar aggregation | **verified** | `seraph/live/bars.py` — closes only elapsed windows, closes on a timer, rejects late ticks, bar volume as increment | a partial bar never emitted; a thin symbol does not hold its bar open; a late tick is counted and rejected | — |
| `LIVE04` decision loop | **verified** (logic) | `seraph/live/loop.py` + `scripts/run_live.py` — `publishable` False unless recency AND feed permit; latency measured from bar close | the pipeline runs on replay data and the result is correctly **not publishable** | live execution needs LIVE02 + source DB warm-start |
| `LIVE05` liveness banner | **verified** | `console_backend.liveness_of()` + `bridge.js` — red "HISTORICAL REPLAY — NOT A CURRENT MARKET READING" banner, green only when genuinely current | rendered in the browser against the real archive run | — |

**Current reality: nothing is publishable as a current reading.** The corpus
ends 2026-08-21, today is 2026-10-16, and no feed is connected.

## Phase 5 — fresh execution and supporting data

| ID | P | State | Note |
|---|---|---|---|
| `DATA03` | P1 | **verified** | `seraph/ingestion/bhavcopy_reader.py` parses BOTH the legacy and UDiFF layouts from the header (never the filename) and reads exact `TOTTRDVAL`. An unparseable traded value is rejected, not zeroed — a zero sorts a liquid name to the bottom of the FR52 ranking. `compare_with_proxy()` quantifies what `close × volume` got wrong and whether it changes rank order. `tests/test_data03_bhavcopy.py` **17 passed**. [DR-06](decisions/DR-06-2026-10-16-product-subsystems.md) |
| `DATA04` | P1 | not started | official Nifty 500 benchmark data access needed |
| `DATA05` | P1 | not started | vintage-bearing macro sources needed |
| `DATA06` | P1 | not started | cited tariff announcements; the loader and empty registry already exist |
| `DATA07` | P1 | not started | needs `DATA06`; FR22 decay/weighting semantics still undefined |
| `DATA08` | P1 | not started | historical flow source availability |
| `DATA09` | P1 | **blocked on external input** | needs `DATA02` (source PostgreSQL) |
| `DATA10` | P2 | not started | needs `DATA09` |
| `PIPE01` | P1 | **blocked on external input** | `FIX01` `FIX02` `FIX03` are done; `DATA02` and `DATA09` are not |
| `PIPE02` | P1 | **blocked on external input** | needs `DATA02` |
| `PIPE03` | P1 | **verified** | `seraph/operations/jobs.py`: lease locks with recorded takeover, checkpoints that survive failure and clear on success, bounded retries, watermarks, every attempt a recorded row. `tests/test_ops_jobs_and_monitoring.py` (25 passed, shared with `OPS01`). [DR-06](decisions/DR-06-2026-10-16-product-subsystems.md) |
| `PIPE04` | P1 | not started | bounded parallel pillar workers; needs `PIPE01` |

## Phase 6 — portfolios and institutional scenarios

| ID | P | State | Note |
|---|---|---|---|
| `PORT01` | P1 | **verified** | preview → commit import, CSV and JSON, column aliases, duplicate merge, long-only enforced with reasons, original bytes preserved. `tests/test_port01_port02_workspace.py` **21 passed** |
| `PORT02` | P1 | **verified** | append-only holdings snapshots; `holdings_as_of()` returns the snapshot in force or `basis='unavailable'` — today's holdings are never substituted under a past date |
| `PORT03` | P1 | not started | measured sector flags need `FIX07`'s artefacts to actually run against a corpus |
| `PORT04` | P1 | **verified** | `exposure_trail.py` — article → event → each evidenced relationship → the holding. Every holding counted once; linked / unlinked / linked-but-unsized reconcile to the total; states plainly it is not a loss estimate. Plus `shared_dependencies()` for blind spots, evidenced only. `tests/test_scen01_port04.py` **25 passed** |
| `PORT05` | P2 | not started | measured risk engine; needs real valuation history |
| `SCEN01` | P1 | **verified** | `scenarios.py` — pinned baseline artefact, versioned assumptions with units and justifications, reviewer history, run records that reuse on identical inputs, comparison that refuses different baselines rather than fudging them |
| `SCEN02` | P2 | **deliberately refused** | `kind="economic"` raises: it needs a documented propagation and portfolio-valuation model, and a rank shock will not be relabelled as one |

## Phase 7 — regulator cases

| ID | P | State | Note |
|---|---|---|---|
| `CASE01` | P1 | **verified** | `cases.py` — validated state machine naming the moves that were available, `expected_version` concurrency detection, idempotent delivery, full actor trail surviving restart. `tests/test_case_workflow.py` **20 passed** |
| `CASE02` | P2 | **blocked on external input** | authorized institution submissions do not exist; institution-level exposure is not inferred from market bars |
| `CASE03` | P1 | **verified** | evidence pinned at a revision; replay anchored to an event **sequence number** (second-granularity timestamps cannot separate same-second events); exports hashed; a source correction notifies and preserves the pinned revision |

## Phase 8 — fitted policy and measured decision value

| ID | P | State | Note |
|---|---|---|---|
| `POL01` | P2 | **blocked on external input** | needs `DATA05` macro vintages and `DATA07` tariff features |
| `POL02` | P2 | not started | needs `POL01` |
| `VAL01` | P1 | **blocked on external input** | needs `PIPE02`; also accrues over real future time |
| `VAL02` | P2 | not started | needs `PORT02`✓ `SCEN02` `VAL01` |
| `VAL03` | P2 | not started | needs `DATA02`; the `FIX05` decision is taken and implemented |

## Phase 9 — operations and release

| ID | P | State | Note |
|---|---|---|---|
| `NEWS08` | P2 | not started | weather/commodity feeds |
| `OPS01` | P1 | **verified** | `monitoring.py` — health where nothing with no data reads `ok`; an alert ledger separating issued from delivered, with `undelivered()` retryable. **No delivery transport exists**; the ledger records what one would be asked to do |
| `OPS02` | P1 | **designed, not exercised** | migration runner built and tested; backup/restore inventory written ([OPERATIONS.md](OPERATIONS.md) §6) including why news `first_seen_at` is not safely re-derivable. No backup job, no restore, no recovery exercise |
| `OPS03` | P1 | **partially verified** | `docker-compose.yml` hardened: env credentials, loopback-only binding (it published on every interface), pinned image, scram-sha-256. Three-database separation and the test guard documented and tested. **TLS and at-rest protection not implemented** — everything is loopback, so NFR23/24 cannot be and is not claimed |
| `QA01` | P1 | not started | canonical browser tests; needs a browser run |
| `QA02` | P1 | not started | performance, accessibility, WebGL fallback |
| `QA03` | P1 | **verified** | wheel built, installed into a throwaway venv, console rendered from `site-packages`. `docs/evidence/PACKAGING-2026-10-16.json` |
| `DOC01` | P1 | **in progress** | plan, status, contracts, inventory, handoff, operations and six decision records exist and are current |

## Summary

| State | Count | IDs |
|---|---|---|
| verified | 25 | `FIX01` `FIX02` `FIX03` `FIX04` `FIX07` `FIX08` `FIX09` `FIX10` `FIX11` `AUTH02` `AUTH03` `AUTH04` `NEWS02` `NEWS03` `NEWS04` `NEWS05` `NEWS06` `DATA03` `PIPE03` `PORT01` `PORT02` `PORT04` `SCEN01` `CASE01` `CASE03` `OPS01` `QA03` |
| implemented, unverified | 3 | `AUTH01` (no OIDC provider), `NEWS01` (no live fetch), `FIX06` (needs the blocked test DB) |
| implemented, blocked on external input | 1 | `DATA01` (Docker engine down) |
| blocked on external input | 8 | `DATA02` `DATA09` `PIPE01` `PIPE02` `CASE02` `POL01` `VAL01` + `SCEN02` (deliberately refused pending a valuation model) |
| scientifically unresolved | 0 | — (`FIX05` resolved by DR-05 on 2026-10-16, implemented 2026-10-17) |
| designed, not exercised | 1 | `OPS02` |
| partially verified | 1 | `OPS03` |
| in progress | 1 | `DOC01` |
| not started | 17 | `DATA04`–`DATA08`, `DATA10`, `PIPE04`, `NEWS07` `NEWS08`, `PORT03` `PORT05`, `POL02`, `VAL02` `VAL03`, `QA01` `QA02` |

Counts exceed 59 where one ID appears in two lists; each ID's authoritative
state is its own row above.

## Test baseline at this checkpoint

| Partition | Result |
|---|---|
| Core (excluding four expensive Hamilton/policy modules) | **843 passed, 14 skipped, 1 xfailed, 0 failures** in 94s — `test-results/live-core.xml` (audit baseline was 481 passed) |
| Expensive Hamilton/policy partition | **34 passed, 0 failures** in 19m58s — `test-results/models-partition.xml`. This closes the gap left open at the previous checkpoint |
| Mechanical invariants | 5 passed |
| Research artifact verifier | passed — data, code and output hashes verified |
| Packaging (wheel → fresh venv → rendered console) | passed |
| `git diff --check` | clean |

The 14 skips are PostgreSQL/intraday-corpus dependent and do **not** establish
database behaviour. The xfail is the unresolved FR35 Table B design (`FIX05`),
deliberately left failing.
