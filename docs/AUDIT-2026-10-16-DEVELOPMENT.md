**SERAPH development and product audit — 16 October 2026**

Audited the working tree at base commit `51680bb`, including its existing modified and untracked integration files. This is an audit of the current local product, not just the committed baseline. No implementation, UI, scientific model, source database, or existing evidence was changed by this audit. New audit documentation and verification outputs are the deliverables.

The owner's clarification is an explicit scope requirement: the globe, news tracking, geographic and sector overlays, strategic assets, authenticated roles, portfolio tools and policy workflows are intended functionality. A preview is a development commitment, not a recommendation for deletion. News estimation is a separate subsystem from Hawkes/RMT/Hamilton. Historical removal notes in older demo files do not override this scope.

**Assessment**

SERAPH has substantial tested numerical software, preserved research evidence, a functioning historical integration path, a distinctive interactive frontend, and several real decision-support operations. It remains a historical research prototype with product workflows under development. The largest remaining work is connecting trustworthy data and estimators to the intended surfaces, adding authenticated ownership and operational workflows, and completing fresh-data execution.

There are three independent completion questions:

| Question | Current assessment |
|---|---|
| Can the software calculate, persist and display historical outputs? | Yes, on tested paths; this audit found replay and persistence edge defects. |
| Can each intended user carry out a complete, authenticated, durable workflow? | Partially. Roles select server-projected data; identity, organization isolation and most workflow lifecycle features are missing. |
| Has dependable crisis prediction or improved portfolio outcomes been established? | No. Preserve the negative results and evaluate new capabilities on their own evidence. |

No defensible single completion percentage can be assigned: a numerical function, a connected screen, an authenticated workflow and a validated estimator are different units of completion.

The companion [development backlog](AUDIT-2026-10-16-BACKLOG.csv) contains **59 actionable work packages**, with priority, area, dependencies and acceptance criteria. It covers completion work; the distinctive feature proposals below are an additional product menu rather than mandatory release scope.

**Scope and verification**

Read the Astra baseline documents first (`README-RESEARCH.md`, `EXPERIMENT.md`), then the current requirements, architecture, integration documentation, relevant amendments and research results. Inspected C1–C12, the prediction and orchestration packages, canonical frontend component and bridge, persistence schema, launch paths, test coverage and CI. Older evidence was treated as historical evidence, not a fresh database census.

Fresh checks in this audit:

| Check | Result / evidence |
|---|---|
| Core suite, excluding four expensive model/policy modules | **481 passed, 13 skipped, 1 expected failure**, 72.11 seconds. `test-results/audit-2026-10-16-core.xml`. |
| Remaining Hamilton and policy modules | **34 passed**, 1106.66 seconds. `test-results/audit-2026-10-16-models.xml`. |
| Combined suite | **515 passed, 13 skipped, 1 expected failure; zero unexpected failures**, across two non-overlapping invocations covering `tests/`. |
| Mechanical invariants | All five checks passed; these checks cover a subset of invariants and the frozen-types check is informational. |
| Research artifact verifier | Passed: data/code/output hashes, saved feature/prediction replication checks, 876 supervised fit audits and 977 alert fit audits. This is not a newly executed full forecast experiment. |
| Isolated persistence, missingness and feature probes | Reproductions in `test-results/audit-2026-10-16-probes.json`; only temporary synthetic SQLite databases used. |
| Real archive replay for 2024-11-01 | Failed with `Future or missing pillar information timestamp`; `test-results/audit-2026-10-16-special-session.json`. Temporary output store only. |
| Windows localhost source connectivity | Ports 5433 and 5434 unreachable; 8512 listening. No fresh PostgreSQL calculation or database census claimed. |
| Whitespace check | Existing trailing whitespace at `scripts/diagnose_jump_process.py:58`; left untouched. |

No fresh browser automation, load test, live news-provider integration or production authentication test was performed. Existing documented browser checks are useful prior evidence, not a new result from this audit. PostgreSQL test skips cannot establish SQL behavior. A localhost listener alone does not establish UI correctness.

Permanent compact evidence, exact test commands and hashes of 14 key audited source files are saved in [the verification record](evidence/DEVELOPMENT-AUDIT-2026-10-16.json). The JUnit and detailed probe outputs remain under the gitignored `test-results/` directory. The expected failure is the FR35 Table B scope disagreement; it is outstanding work, not accepted behavior.

**What is already implemented and worth building on**

| Area | Actual implementation | Remaining boundary |
|---|---|---|
| C1 storage | Timescale schema, typed reads, transaction-based writes, COPY upserts, watermarks, protection of derived columns on ingestion refresh | Fresh DB verification, full output-store contracts, migrations and operational recovery |
| C2 ingestion | EOD2 snapshot reader, Kite client/backfill, macro source adapters/cache, latest FII/DII flow ingestion, validated tariff registry loader | Scheduled acquisition, complete historical coverage, real vintages and filled tariff registry |
| C3 universe | Listing-history filter before liquidity ranking, buffering/churn, equity screening and snapshots | Exact turnover acquisition, source fidelity, official-index validation |
| C4 features | Jump extraction, tick test, state bins, volatility/spread/absorption calculations, date-aligned return panels | Historical regeneration, causal state bins, tariff feature builder, full estimator-agreement evidence |
| C5 Hawkes | Discrete intraday pooled count model, significance gate, sector intensity-flag helper; original diagnostic variants retained | Measured sector flag production, parameter persistence, live cadence, identifiable network data |
| C6 RMT | Correlation spectrum, MP bounds/bootstrap, common-support rotation, stateful SCA calculation | Fresh-history execution and explicit operational readout/calibration decision |
| C7 Hamilton | Multivariate TVTP model, causal walk-forward machinery, fitted transition projector | Validated macro inputs, accepted fitted model and product scenario integration |
| C8 reconciliation | Kalman and forward-fill variants, explicit time clock, vintage handling, corrected missing-measurement behavior | Correct absence classification in the new adapter and online restart/state lifecycle |
| C9 fusion | Pure score, masks, contributions, immutable weight identity, corrected conditional variance | Accepted weights/threshold policy and measured uncertainty calibration |
| C10 validation | Chronological evaluations, ablations, leakage checks, preregistration, many research diagnostics | Resolve original FR35 design conflict, prospective record, cross-market evaluation, economic decision evaluation |
| C11 support | Plain explanations, coverage-aware portfolio arithmetic, shock and regime-path simulations, action journal | Portfolio risk/valuation, fitted policy workflow, measured playbooks, case management |
| C12 frontend | Original globe/console preserved; selected run/date, projected role payloads, actual historical scores and tools | Live overlays, authentication, complete visual diagnostics, workflow UX and accessibility/performance acceptance |
| Astra prediction | Three named pillar variants, baseline/combined models, matured-label training, forecasts, fit audits and alert calibration | Refresh from new source data, prospective evaluation and deployment lifecycle |
| External hazard watch | Sourced historical health-event register and separate counterfactual replay | General news pipeline, exact dissemination times and separately evaluated prospective rules |

Evidence entry points: `seraph/dashboard/prototype_app.py`, `seraph/dashboard/console_backend.py`, `seraph/dashboard/gateway.py`, `seraph/orchestration/prototype.py`, `seraph/orchestration/run_store.py`, `seraph/decision_support/`, `PROTOTYPE.md`, `docs/FRONTEND-INTEGRATION.md`.

**Concrete defects and hardening findings**

Priority meanings: **P0** blocks a trustworthy replay or any deployment with real users; **P1** is necessary for the first operational product; **P2** completes deeper analytics/product capabilities. Priorities are recommended sequencing, not measured estimates of effort.

| ID | Priority | Finding and evidence | Required change and acceptance |
|---|---|---|---|
| A01 | P0 | `run_archive()` selects Hawkes by calendar date, while `InferenceSession.step()` fixes the decision time at 15:30. The real 2024-11-01 archive has an 18:55 IST refit. Replay of that date fails. `prototype.py:166`, `:47`. | Use timestamp-based as-of selection and a session-aware decision clock. At 15:30 use only an earlier vintage; at the special-session close permit the evening vintage. Replay the entire supported history and test holidays, short sessions and evening sessions. Do not weaken the future-information guard. |
| A02 | P0 before live feeds | `InferenceSession.step()` maps every ineligible/missing input to `absence='structural'`. A synthetic RMT temporary outage changes mask `[true,true,false]` to `[true,false,false]`. `prototype.py:91`. | Carry absence type/reason in the input contract; distinguish no historical coverage, research exclusion, feed outage and estimation failure. A transient absence must preserve mask membership and propagate uncertainty. |
| A03 | P1 | Run finalization checks only row count. A completed run accepts an extra date, even outside its declared range. `run_store.py:65`, `:76`. Reproduced. | Seal completed run contents, validate the expected date set and point schema, and reject additions or incompatible retries. Allow verified identical retries. |
| A04 | P1 | A run becomes complete before its comparison report is written, and `report()` overwrites an existing report. `prototype.py` calls `finish()` before report construction; `run_store.py:93`. Reproduced. | Atomically finalize manifest, points and required report, or expose separate inference/evaluation completion states. Give reports immutable identities or explicit revisions. Test a crash between stages. |
| A05 | P1 for legacy state path | `_bucket()` computes quantiles from the entire supplied array. Appending 20 future observations changed 16 of 20 earlier synthetic state assignments. `features/jump_extraction.py:191`. | Fit bins on training data or a trailing window and version them. Require future-append invariance. This finding concerns the state-bin path; it does not show leakage in every current Hawkes variant. |
| A06 | P1 | `validation_results` key excludes `table_id`, preregistration identity and evaluation-run identity. Table A/B results can share keys under the current six-fold Table B design. `store/schema.sql:206`. | Introduce evaluation/run/design identity in the key through a migration; preserve both tables and repeat experiments without overwriting evidence. |
| A07 | P1 | FR35 says Table B uses two pre-Hawkes epochs; `configuration_list()` uses all six. The expected-failure test still pins this disagreement. `validation/preregistration.py:41`. | Publish a versioned decision and new evaluation design. Preserve earlier hashes/results. Do not mark this resolved because pytest treats it as expected. |
| A08 | P1 | Hawkes production writer explicitly stores `alpha_beta=None` and `flag='none'`; sector baselines remain missing. `scripts/write_hawkes_production.py:224`. | Persist fitted parameters, training cutoff, universe and model identity; produce measured sector flags through their own pipeline. Reconstruct a saved intensity from its artifact. |
| A09 | P1 | Original backfill selects the latest universe snapshot before processing historical windows. `scripts/write_hawkes_production.py:167`. | Specify and implement historical membership semantics; use point-in-time universes or disclose a fixed research basket. Test future membership changes cannot alter earlier inputs. Historical parameters can be causal while basket selection still has survivorship limitations. |
| A10 | P0 before real users | Any local user can select regulator. Journal actor is the role string; run selection is global; holdings can be embedded in a run manifest and passed with the run. `prototype_app.py`, `console_backend.py`, `gateway.py`. | Bind identity, tenant and grants on the server. Filter runs/holdings/actions by ownership. Role projection is implemented, but it is not user authentication or tenant isolation. |
| A11 | P1 | Legacy `dashboard/datasource.py` independently fetches latest CSRS, Hamilton and RMT rows, and claims caching without an actual `st.cache_data` decorator. Canonical console uses RunStore instead. | Keep every supported route on a coherent run/as-of read contract; add appropriate scoped caching. Test the canonical entry point and identify legacy compatibility routes explicitly. No UI removal is required. |
| A12 | P1 | Canonical bridge uses a `pending` flag with no explicit timeout/retry recovery, and regenerates tool forms on responses. `console_component/bridge.js:11`, `tools()`, `show()`. | Add request status/error recovery, persistent drafts and context-specific results. Test delayed/lost responses and switching date or role during an operation. Static inspection finding, not a demonstrated browser outage. |
| A13 | P1 | Recording an update that leaves an action unchanged with a new request ID raises `IntegrityError: UNIQUE constraint failed: action_events.run_id, action_events.seq`. C11 correctly creates no new journal event for a no-op, but `RunStore.action()` reinserts the last event. Reproduced in a temporary store; `test-results/audit-2026-10-16-action-noop.json`. | Distinguish command results from new journal events; persist/return idempotent no-op results without reusing the event sequence. Cover same-action updates, retractions and retries. The canonical app does not catch this SQLite exception. |
| A14 | P1 | `universe/instrument_type.py` returns an empty symbol set when the ISIN file is absent, and `is_equity()` then accepts every symbol. | Missing classification data should produce explicit unavailability or a documented, visibly degraded mode; a deployment must not silently reintroduce ETFs into the equity universe. The file is present in this checkout; this is an inspected failure-path risk. |

The existing source database was not examined, so earlier row counts, missing bars and old table populations are not presented as current measurements. In particular, do not delete historical bars solely because an older audit called them impossible: validate against the official calendar, exchange outages and any extended-session notices first.

**Frontend commitments: what each surface still needs**

| Surface in the intended product | Connected today | Development needed |
|---|---|---|
| Risk globe, raised states, arcs, sector/geography drill-downs | Geometry, interaction and explicitly fabricated examples | Geographic/entity master data, dated exposure edges, news-estimate tiles, drill-down evidence, aggregation rules and update transport |
| Latest signals / news rail / crawling headlines | Design-preview content; real saved SERAPH explanation also available | Source acquisition, event clustering, source links, publication/receipt timestamps, corrections, filters, saved searches and live delivery |
| Sector stress | Preview values | Separate news-derived estimate and measured Hawkes-sector diagnostic, each with its own units, coverage, timestamp and uncertainty |
| Strategic assets | Interactive asset representations and preview records | Verified asset/operator/location/capacity/status registry; evidence-backed incident links; dated ownership relationships |
| Weather advisory | Preview cards | Actual weather/advisory feed; polygon/asset intersection; issue and valid times; exposure and impact estimation |
| Commodities and ticker | Preview values | Licensed/authorized price feeds, units/currency/session conventions, stale indicators, source metadata and date alignment |
| Portfolio exposure | Real holdings arithmetic in tools; map preview remains illustrative | Persistent owned portfolios, valuation, issuer/sector/asset mapping, time-aware news exposure and measured risk |
| CSRS console and history | Real saved C8/C9 outputs | Fresh production feed, session clock fix, accepted alert policy, alert history and notification lifecycle |
| Pillar panels | Saved diagnostics; canonical bridge largely renders detail JSON | Actual spectrum/density visualization, regime history, measured sector diagnostics, networks when identifiable, diagnostic uncertainty and source lineage |
| Forecasts | Archived Astra model predictions | New-data forecasting, target/horizon labels, reliability/coverage views and prospective scoring |
| Backtest | Saved retrospective comparisons and CSRS sparkline | Official Nifty 500 overlay, target-aligned comparisons, portfolio point-in-time backtests and exports |
| Institutional tools | Rank-shock scenario and static playbook | Reusable owned scenario sets, valuation/P&L engine, comparison, approval and assumption management |
| Regulator tools | Hypothetical regime path and durable local journal | Fitted macro-policy scenario, institution data, multi-person case lifecycle and authenticated evidence exports |
| Method and provenance | Run metadata and disclosed limitations | Human-readable artifact lineage, model version comparison, source freshness and evidence status across both mathematical and news channels |

Keep the visual layout and interactions. Replace each preview's data provider as its subsystem matures. A label such as `preview`, `observed`, `estimated`, `scenario` or `unavailable` should travel with the data, rather than depend solely on a panel-wide banner.

**News, geography and sector estimation: a complete missing subsystem**

The historical WHO watch is useful prior work but does not supply general news tracking. The globe's static `SIGNALS`, `SECTORS`, `ASSETS`, `MET`, `COMMOD`, `EXPOSURE` and related structures in `console_component/index.html` currently supply the previews.

Recommended product flow:

`Sources → immutable observations → deduplicated stories/events → resolved entities and places → documented exposure relationships → versioned impact estimates → role-specific overlays and workflows`

The mathematical flow remains independently evaluable:

`Market data → C4 → Hawkes / RMT / Hamilton → C8 → C9 → CSRS`

Both channels can meet in the decision-support view, with separate attribution. Any future combined alert policy needs its own declared logic and evaluation; putting two colors beside each other does not validate a combined predictor.

| Work package | What must be built | Definition of done |
|---|---|---|
| N01 Source register | Provider/feed, topic coverage, language, rights/retention restrictions, polling policy, source identifier and failure behavior | Each visible story links to a registered source; unsupported sources cannot silently enter scoring |
| N02 Acquisition | Scheduled fetches, bounded retries, incremental cursors, raw snapshots/hashes and per-source health | Restart/double-fetch produces one logical observation; a source outage appears as missing coverage |
| N03 Information time | Publication, first-seen, update, event-occurrence and effective-policy times, all explicit | Historical replay never sees an article or revision before the system could have received it |
| N04 Deduplication | Exact URL/content identity, syndication clustering, related-event grouping and correction/retraction chains | Ten syndicated copies do not create ten independent confirmations or ten times the estimated stress |
| N05 Extraction | Event type, actor, affected entity, action, quantities, units, geography and supporting text spans | A labeled review set measures extraction errors; unresolved/ambiguous facts remain explicit |
| N06 Entity resolution | Issuer identifiers, symbol changes, parent/subsidiary/operator relations, assets, ports, districts/states/countries and sector taxonomy | A company headquarters mention is not automatically treated as the location of a disrupted plant |
| N07 Exposure model | Revenue, imports/exports, input dependencies, facility location, logistics and supplier relationships with validity dates and confidence | Every map arc has an inspectable relationship and evidence; unknown exposure is distinct from zero |
| N08 Estimation | Separate event severity, evidence confidence, exposure magnitude, direction, duration and mechanism; normalization for source volume | Versioned estimates reproduce exactly; a score's meaning is defined; no unsupported percent-loss number is produced |
| N09 Aggregation | Event-to-asset-to-issuer-to-sector/geography aggregation; deduplication across paths and portfolio holdings | Direct and indirect exposures are distinguishable; overlapping assets/events are not double-counted |
| N10 Lifecycle | Active/developing/resolved/retracted events, superseding estimates, decay only where justified, conflicting reports | Repealed policy and resolved disruption update the map; repeated coverage alone does not prolong risk forever |
| N11 Review | Analyst review queue, correction reason, reviewer identity, rule/model version and replayable changes | Correcting an entity link changes only subsequent versions, preserving what earlier users saw |
| N12 Evaluation | Held-out extraction/linking labels; latency, false links, geographic accuracy, coverage and forecast calibration where a predictive target exists | News-system quality can be measured independently of CSRS accuracy |

Start with a narrow, useful vertical slice: official policy announcements plus one sector and its actual firms/assets. The UI already suggests steel, solar, auto components and pharmaceuticals; choose one with accessible exposure evidence. Expand only after the full source-to-map chain works.

Useful source candidates verified during this audit: [RBI RSS](https://www.rbi.org.in/Scripts/rss.aspx) offers official updates; [GDELT data documentation](https://gdeltproject.org/data.html) describes broad news and geographic-mention datasets. These are candidate inputs, not verified SERAPH integrations. GDELT geographic mentions do not establish a company's economic exposure. Provider reachability, coverage, rights and reliability still require a measured integration spike.

An optional language model may assist structured extraction or summaries, with evidence spans, schema validation, versioned prompts/models, a review set and abstention. It should not invent missing exposure edges, assign ungrounded financial losses, or have authority to mutate user permissions or regulatory actions from article text.

**Authenticated role workflows**

`gateway.build_view()` already omits restricted fields from the payload, and `dispatch()` checks roles and run/date context. Retain these controls and add a real identity and resource-ownership layer above them.

Required foundation:

1. Authenticate an identity through OIDC; bind a stable provider subject to a local user.
2. Store organizations, memberships and server-controlled grants. Separate role from portfolio ownership and institution scope.
3. Resolve allowed roles on the server. A user with several grants may switch among those grants; a browser request cannot grant regulator access.
4. Enforce resource-level permission for each run, portfolio, scenario, news annotation, case and export, including direct reads and cached responses.
5. Record actual actor identity, organization, action, object, request ID, decision timestamp and operation timestamp. The journal already distinguishes alert and operation time; retain that distinction.
6. Add membership revocation, logout/session-expiry behavior, role-change handling and tests for stale sessions.
7. Add durable preferences, watchlists, portfolio/scenario ownership and user-specific histories.
8. Test two users within one institution, two different institutions and a scoped regulator; make cross-user/cross-organization denial a required integration check.

[Streamlit's current authentication documentation](https://docs.streamlit.io/develop/concepts/connections/authentication) supports OIDC and explicitly separates authentication from authorization. Its native identity support is compatible with the current stack, but does not replace SERAPH's grants and ownership checks. Verify the installed version and auth dependencies before implementing.

| Role | Useful now | Missing end-to-end workflow |
|---|---|---|
| Retail | Simplified historical alert, explanation and current holdings coverage arithmetic | Sign in → import/save holdings → resolve/price holdings → view news and measured exposure → maintain watchlist → acknowledge/revisit alert → inspect subsequent outcome |
| Institutional | Pillar diagnostics, contribution display, archived forecasts, rank-shock simulation, coverage tool | Organization/team → multiple books → position snapshots → exposure/risk calculation → reusable scenarios → reviewer approval → decision record and monitoring |
| Regulator | Richer provenance, manual regime paths and local annotation journal | Scoped institution access → triage case → assign investigator → attach evidence → request information → review/approve decision → follow up → close/reopen with audit history |

Retail simplicity is a presentation choice, not a reason to omit freshness, missing coverage or evidence reliability. Institutional access does not imply access to other institutions. Regulator access should reflect jurisdiction and assignment rather than automatically exposing every user's personal holdings.

**Portfolio development**

`portfolio_overlay()` correctly calculates value shares and distinguishes unmeasured sectors from measured quiet sectors. It does not estimate portfolio losses. The canonical dispatch supplies an empty flag map, so a valid holdings list currently produces uncovered exposure. `portfolio_io.py` provides a user-scoped database read, but canonical tools use supplied JSON; E11 has no holdings-history dimension.

| Stage | Development | Acceptance |
|---|---|---|
| Holdings | CSV/JSON import, identifier resolution, duplicate handling, cash/currency conventions, optional quantity/value reconciliation | Preview imported changes and explain rejected rows; preserve original import and version |
| Ownership/history | Portfolio and account identifiers, owner/tenant, effective-time position snapshots, changes and valuations | A past-date view uses actual past holdings or explicitly declares current-holdings analysis |
| Valuation | Prices, FX, corporate actions, stale/missing-price handling and asset-type scope | Reconcile portfolio total with source statement within an agreed tolerance |
| Exposure | Issuer/sector/geography/asset links; measured Hawkes flags and news exposures kept attributable | Covered, uncovered and estimated portions reconcile to portfolio value without overlap inflation |
| Measured risk | Return history, covariance, concentration, drawdown, liquidity assumptions and selected tail-risk metrics | Deterministic fixtures plus out-of-sample calibration/backtesting appropriate to each metric |
| Scenario valuation | Translate explicit market/input/FX shocks to position changes under documented assumptions | Zero shock reproduces baseline; every loss has units, horizon and a reproducible valuation path |
| Decision evaluation | Rebalancing/hedging policies, availability/cost/slippage assumptions and point-in-time positions | Net realized benefit compared with appropriate controls; no fabricated drawdown-reduction claims |

If initial holdings support is long-only equity, state that scope. Short books, derivatives, funds with look-through and multi-currency assets need additional exposure conventions; they cannot be completed by simply allowing negative values in the existing percentage calculation.

**Institutional and policy scenarios**

The existing shock simulator changes an ECDF-ranked pillar value and applies a decay path, while holding the remaining baseline state. It is a working sensitivity tool. A `+0.1` shock is not automatically a 10% equity loss, a rate hike or a commodity-price move. Current scenario rows reuse the baseline state timestamp and conditional covariance; they are stepwise sensitivities, not fully simulated future observations with evolving forecast uncertainty.

To complete institutional scenarios: introduce saved scenario identity and assumptions, dated steps, portfolio scope, baseline artifact identity, propagation/valuation engine, comparisons, exports and reviewer sign-off. Keep the current rank-shock tool as an explicit expert diagnostic alongside economic scenarios.

The macro-policy function is **partially built**, not absent: `C7.project_xi()` propagates a regime distribution through fitted TVTP transition matrices, and `C11.simulate_policy()` accepts `z_path` plus an injected projector. The canonical UI only supplies hypothetical `xi_path` rows.

Remaining macro-policy chain:

1. Acquire event-time policy-rate data and usable macro series with publication/vintage metadata. The macro client discloses monthly/quarterly substitutes; these cannot silently stand in for a dated policy announcement.
2. Implement and validate the tariff `G_t` and sector-weighted feature builder; the curated CSV is empty and the feature implementation was not found.
3. Fit a causal, versioned C7 model on a documented covariate schema; persist coefficients, transformations, training cutoff, state ordering and diagnostics.
4. Select an eligible fitted artifact as of the scenario date; expose supported units, horizons and extrapolation warnings.
5. Connect `z_path → project_xi → simulate_policy`, preserving zero-change identity and transition-simplex tests.
6. State what the scenario changes: the current pathway changes regime weights, not the entire market/portfolio state. Broader macro transmission requires further models.
7. Evaluate projection stability and calibration. Fitted association is not proof of a causal policy effect.

Identical regime weight vectors currently make the score insensitive to a changed regime path. That is expected algebra under equal weights, not a UI malfunction. Do not alter weights merely to make the slider produce motion.

**Regulatory operations**

The local journal has useful foundations: transactional mutation, idempotency, revisions/retractions, immutable event models and SQL triggers against normal update/delete. It currently records annotations, including an action category named `circuit_breaker`; it does not execute a real market intervention.

Complete it with case identity, related alert/event/institution links, assignee and team, priority, status transitions, deadlines, evidence attachments, comments, information requests, review/approval, decision rationale, closure and reopening. Add concurrent-update handling and idempotent notification dispatch. Evidence exports must include the versions actually consulted, not whichever model or article is latest when exported.

Institution-level decomposition requires authorized institution/exposure data and an aggregation method. Market-wide bar data cannot supply institution-specific positions, liabilities, counterparties or interventions. Distinguish a market-dependence graph, a news supply-chain graph and a confidential financial-exposure graph.

NFR26 also asks for alert and dashboard-view audit events. The local action journal alone does not cover that requirement. Decide retention, access, backup, restoration and tamper-evidence requirements; database-admin access can still alter a local SQLite file.

**Fresh execution and data engineering**

The archive route verifies saved artifacts and executes C8/C9/C11. It does not refit the original pillars or refresh Astra forecasts. The fresh-source endpoint uses a read-only transaction and calls all three original estimators when history permits, but withholds its composite because chronological standardization warmup is absent. These are different execution modes and should remain explicit.

| Missing work | Why it matters / acceptance |
|---|---|
| Disposable Timescale integration environment | Provision a new guarded test DB; run the 13 skipped checks where their required fixtures exist. A minimal DB will not satisfy real-corpus density tests by itself. |
| Read-only source census | Confirm current table ranges, gaps, source freshness, symbols, universe membership and parameter completeness once available. |
| Complete fresh-history pipeline | Chronologically rebuild features, fit/refit pillars, warm ECDFs, reconcile, score and persist one coherent run; compare with an independently reproducible replay. |
| Fresh Astra forecast cycle | Generate features and matured-label fits from newly acquired data; save cutoff, calibration eligibility, model identity and probabilities separately from CSRS. |
| Market/session calendar | Special sessions, halts and delayed arrivals must drive ingestion, close times, staleness and decision clocks consistently. |
| Daily bhavcopy acquisition | No actual legacy/UDiFF reader was found. Existing tests of a `bhavcopy-legacy` label do not test parsing the real files. Implement both formats and exact traded value. |
| Universe/data fidelity | Compare the close×volume turnover proxy with actual TOTTRDVAL; handle listing history, symbol/ISIN changes and survivorship. Follow the floating-universe amendment rather than blindly forcing 500 complete histories. |
| Official benchmark | Ingest and version Nifty 500 data for FR41 and FR54. `validate_against_official_index()` currently returns a missing-dependency error. |
| Macro history | Store source identity, units, period date, publication date and vintage; current latest-revised downloads and conservative lags are not immutable historical vintages. |
| FII/DII flows | `ingest_latest()` exists; build an accumulating daily operational record and inspect historical source availability. Preserve gross/net and numerator/denominator definitions. |
| Tariffs | Populate cited announcement records with an explicit severity convention; keep announcement/effective/correction times distinct; compute C4 features. |
| Corrected feature regeneration | Lee–Mykland and return-alignment repairs do not retroactively regenerate old snapshots. Rebuild into new artifacts, preserve old evidence, compare impacts. |
| FR53 substitution study | Helper exists; produce aligned, comparable daily OHLC/5-minute RV evidence with units, overlapping coverage and uncertainty. |
| Online jobs | Cron/idempotent entry points, source watermarks, job locks, bounded retry, failure records and recovery checkpoints. No integrated scheduled live path found. |
| Parallel workers | No `ProcessPoolExecutor` implementation found in inspected production/script sources. Benchmark and implement independent pillar workers with bounded resources. |
| Output contracts | Extend typed store APIs beyond ingestion and avoid independent scripts owning incompatible SQL/output identities; preserve run and artifact lineage. |

A newly started empty database would not demonstrate fresh execution on historical data. Completion needs actual source coverage and an exercised raw-data-to-view path.

**Mathematical and scientific work that remains**

Retain Hawkes, RMT and Hamilton. Astra amendments already justify corrected composite variance and missing-observation treatment; do not restore incompatible historical formulas simply to match old prose. Original and daily research variants must retain distinct names and model identities.

| Topic | Remaining work |
|---|---|
| Hawkes | Reassess event density after detector regeneration; persist parameters; version basket/window/seasonality; produce coverage-qualified sector intensities. Directed multivariate contagion is a separate identifiable-model/data problem, not a graph-drawing task. |
| RMT | Formalize which readout is used for which purpose: spectrum/SCA diagnostics versus lambda-share research adapter versus daily shrinkage variant. Original FR18 conformance and calibration remain unresolved. A universally rejected MP null is not a time-varying crisis probability. |
| Hamilton | Preserve the original model's diagnostic-only exclusion until supporting evidence changes. Validate macro TVTP fit and state interpretation. The Astra variance-state variant does not establish the original multivariate model's acceptance. |
| C8/C9 | Correct adapter missingness; stress-test vintage/session transitions; evaluate conditional uncertainty coverage and parameter uncertainty. A CSRS interval is not a portfolio-loss probability interval. |
| Alert policy | Separate calibrated Astra alarm rules from provisional `.5/.75` original CSRS levels; evaluate false episodes, warning duration, abstention and threshold drift prospectively. |
| Labels | Resolve provisional events through independent definitions and record changes as new designs. Tariff-2026 is not established validation evidence. |
| Original ablations | Resolve FR35 table/fold semantics and output identity; preserve unavailable/unassessable rows rather than filling them. |
| Cross-market FR37 | No completed transfer pipeline/result found; add source/universe/currency/calendar adapters and frozen-weight evaluation. The roadmap treats it as stretch work; decide its release scope explicitly. |
| Defensive playbooks FR46 | Current `drawdownReductionPct=None` is correct. Add a real portfolio/execution/cost model and out-of-sample policy evaluation before ranking actions by realized benefit. |
| Prospective evidence | Start a timestamped shadow record with all eligible decisions, missed events, false alerts and model versions. More fitting on the same remembered crises is not independent validation. |

The verified research report gives combined future-loss Brier about **0.0695**, versus **0.0698** for volatility logistic; the descriptive paired interval crosses zero. Original advance-onset success remains unestablished. The health watch is separately attributed retrospective evidence, not a successful live news engine. See `research_results/v1_verified/REPORT.md` and `HAZARD-REPORT.md`.

**Requirement coverage cross-reference**

This is an implementation-gap map under the current amendments, not a claim of formal acceptance. Product commitments outside the historical FR list are covered by the frontend/news/role tables above.

| Requirements | Remaining completion work |
|---|---|
| FR1–2 | Fresh daily/intraday acquisition and execution; real bhavcopy parsing if that route is used; full source coverage verification |
| FR3 | Exact-versus-substitute macro identity, vintage-aware storage and native publication alignment validated end to end |
| FR4 | Populate the cited tariff registry; loader exists |
| FR5–6 | Persist/validate the full feature path and replace whole-array state quantiles with causal bins |
| FR7 | Point-in-time corporate-action, identifier and survivorship evidence; adjusted snapshot alone is insufficient |
| FR8, FR38 | PostgreSQL execution, output API coverage and experiment-aware persistence; SQLite prototype is separate |
| FR9 | Explicitly cut; no missing development obligation |
| FR10–13 | Amended discrete Hawkes exists; corrected-input regeneration, parameter artifacts and operational cadence remain |
| FR14 | Measured per-sector intensity flags/baselines and transport into views/portfolio arithmetic |
| FR15 | Defensible directed contagion output where supported by identifiable data/model; preview graph is not evidence |
| FR16–19 | Original RMT exists under variable-universe amendments; readout/calibration decision, fresh-history validation and meaningful presentation remain |
| FR20–21, FR23–24 | Original C7 implementation exists; empirical eligibility and genuine macro TVTP application remain unresolved |
| FR22 | Tariff decay/sector weighting feature construction and integration remain missing |
| FR25–27 | Reconciliation implemented; new adapter absence semantics, session clock and online lifecycle remain |
| FR28–31 | Fusion/contributions/calibration helpers exist; operational weights, policy and uncertainty acceptance remain; FR29 follows Astra mathematical repair |
| FR32–34 | Substantial research evaluation exists; independent labels, suitable new data and future validation remain |
| FR35–36 | Ablation machinery exists; Table B definition and storage-key conflict remain |
| FR37 | Cross-market transfer execution/evidence not found; roadmap stretch status needs release-scope decision |
| FR39 | Historical score and diagnostics connected; real-time supply, measured sectors/network and full intended plots remain |
| FR40 | Colors/levels exist; provisional CSRS thresholds are not an accepted operational alarm policy |
| FR41 | Official Nifty 500 overlay missing |
| FR42 | Transport projection exists; authentication, ownership and institution-level inputs missing |
| FR43 | Coverage arithmetic exists; real flags, persistent user workflow and historical holdings missing |
| FR44 | Explanation function implemented; ensure live/news explanations retain separate provenance and coverage |
| FR45 | Flow diagnostic function exists; actual feed/history not connected to saved console runs |
| FR46 | Static playbook exists; realized defensive-action benefit unmeasured |
| FR47 | Rank-shock sensitivity exists; reusable scenario workflow and economic portfolio shocks are extensions |
| FR48 | Projection/scoring functions exist; fitted macro artifact and canonical z-path workflow incomplete |
| FR49 | Local annotations/journal exist; no-op update defect, identity and operational cases remain |
| FR50 | Detector repair implemented; historical input/output regeneration and empirical revalidation remain |
| FR51 | Latest FII/DII acquisition exists; accumulated/historical data and operational scheduling remain |
| FR52 | Universe construction exists; exact turnover and classification failure handling remain |
| FR53 | Correlation helper exists; complete real overlapping-estimator study remains |
| FR54 | Official-index validation explicitly blocked on benchmark data |

**Operations, security and maintainability**

| Area | Outstanding acceptance work |
|---|---|
| Deployable environment | Pin/test the database image, define migrations and rollback, separate local research/source/test configuration. Current Compose contains local credentials and a broadly published port; it is not a production security configuration. |
| Recovery | Back up and restore run data, holdings, cases, model artifacts and observation archives; record recovery objectives and exercise interrupted jobs. |
| Transport/storage protection | Implement and verify NFR23/24 for the intended deployment. Current localhost operation does not establish deployment TLS or encrypted-at-rest acceptance. |
| Audit coverage | Identity/role changes, alert issuance/delivery, viewed evidence and export records in addition to regulator actions; define retention and access. |
| Monitoring | Feed freshness/coverage, queue/job lag, fit failures, missing inputs, database health, numerical drift and notification failure visibility. |
| Performance | Measure bar-close-to-view latency, expected user concurrency, memory and heavy daily jobs separately. No 100-user or <5-second evidence was found. |
| UI delivery | Test canonical component rendering, payload role omissions, input preservation, keyboard navigation, non-color status cues, reduced motion and WebGL fallback. Preserve the globe as the intended primary experience. |
| External maps | Handle tile/Overpass outages, caching, attribution and request budgets; distinguish a missing basemap from missing financial observations. |
| Testing | Add real PostgreSQL CI/service job, canonical browser tests, time-boundary tests, multi-user isolation tests and news replay tests. Existing Windows CI deliberately disables DB access. |
| Packaging | Verify wheel/install includes HTML, JS, CSS and Three.js license/assets; editable checkout success alone does not prove packaged distribution. No explicit package-data configuration found in `pyproject.toml`. |
| Architecture | Reduce private-attribute coupling (`RunStore._restore`, RMT state access) with explicit snapshot/restore/readout contracts; use typed results across new component seams. |
| Documentation | Add a current requirements/status index linking Astra amendments and product extensions. Older architecture says “No implementation code”; old roadmap checkboxes and test counts are stale. Do not rewrite hashed experimental evidence. |
| Change integration | Significant local modifications and untracked product files predate this audit. Review them as the release candidate; current main/CI results cannot be assumed to contain the local product. |

NFR9's 99.9% uptime is explicitly a hypothetical deployment target, not a missing student-project deliverable. NFR3/18/19/20/22/27/29 contain undefined acceptance quantities; record measurable release criteria before declaring those requirements satisfied. This audit proposes work, not invented values for those gaps.

**Distinctive role-specific additions**

These are product proposals, not claims of unique market invention or validated predictive benefit. Each proposal has a concrete dependency and an observable success condition.

| Role / idea | User experience | Dependencies | How to evaluate it |
|---|---|---|---|
| Retail — “Why does this affect me?” exposure trail | Click a news alert and see article → event → company/asset → owned position, with the amount linked and uncertainty | News event/entity/exposure graph; real holdings | Link accuracy, uncovered value and user comprehension |
| Retail — diversification blind-spot map | Show different holdings that depend on the same port, input material, supplier or region despite different sector labels | Evidence-backed dependency graph | Verify shared dependencies and avoid double-counted value |
| Retail — personal change brief | Explain what changed since the user's last visit: holdings, news, model state, or data coverage | Versioned snapshots and saved preferences | Correct change attribution and reduced repetitive alerts |
| Retail — uncertainty-aware watchlist | Prioritize relevant events with confidence and missing-data status; allow watch/acknowledge/snooze | Identity, event lifecycle, alert preferences | Relevance, missed-important-event rate and alert burden |
| Retail — decision diary and replay | Save why the user monitored or acted; later replay only information available then | Point-in-time evidence and private notes | Hindsight-free replay and useful review, without claiming causal profit |
| Institutional — event-to-book propagation workbench | Select a policy, port disruption or input-price event and inspect direct/indirect positions with editable assumptions | Books, dependency graph and valuation model | Reproducible propagation, sensitivity to assumptions and loss backtesting |
| Institutional — disagreement monitor | Highlight strong news stress with quiet market pillars, or market stress with little corroborating news | Separately evaluated news and mathematical channels | Prospectively assess event classes, coverage and warning burden |
| Institutional — common-dependency concentration | Aggregate shared operational dependencies across desks, not only issuer/sector weights | Scoped multi-book data and asset relationships | Reconciled exposure totals and new verified concentration discoveries |
| Institutional — scenario comparison notebook | Compare baseline and multiple scenarios, save assumptions, assign a reviewer and export an evidence-linked packet | Scenario persistence, authorization, valuation | Reproducibility and reviewer agreement on assumptions |
| Institutional — evidence expiry alerts | Flag a scenario when its source article is corrected, exposure estimate expires or model is superseded | Version dependencies and correction events | All dependent outputs identified without silently rewriting prior decisions |
| Regulator — incident-to-case workspace | Turn an alert/event into an assigned case with evidence, institution scope, deadlines and escalation | Authentication, case state machine and immutable event history | Time to triage/close, complete audit trace and correct access boundaries |
| Regulator — confidential concentration atlas | Show authorized aggregated exposure to shared regions/assets/suppliers, with restricted institution drill-down | Real institution submissions and explicit aggregation policy | Completeness, privacy/isolation and reconciliation to submissions |
| Regulator — intervention rehearsal | Compare hypothetical policy paths, assumptions, affected sectors and model uncertainty before recording a decision | Validated macro mapping and scenario engine | Projection stability; clearly separate modeled association from causal effect |
| Regulator — information-as-known replay | Reconstruct exactly which article revision, model fit, portfolio snapshot and alert were visible at a past decision | Immutable event/source/artifact versions | No future information appears; evidence packet reproduces the decision view |
| Regulator — conflicting-evidence review queue | Surface disagreement between official notices, news reports and institution submissions | Source provenance, event linking and analyst review | Resolution quality, latency and documented rationale |
| All roles — source correction ripple | Explain which maps, exposures, scenarios or cases changed when a source was corrected | Dependency lineage and versioned estimates | Complete impact discovery, with historical outputs preserved |

The strongest initial differentiator is the **evidence-backed path from an event to a user's exposure**, combined with clear separation between news estimates and SERAPH's mathematical diagnostics. It makes the existing geography and asset visuals useful even before predictive superiority is established.

**Recommended development order and release gates**

| Milestone | Scope | Dependencies | Completion gate |
|---|---|---|---|
| M0 — trustworthy historical baseline | A01–A07, full supported replay, sealed runs, explicit data status and current scope/status register | Existing archive and tests | Full-range replay passes; temporary outages preserve masks; completed results cannot silently change |
| M1 — authenticated personal workspaces | Identity, grants, organization/resource scope, durable portfolios/preferences and actor attribution | M0 persistence contracts | Cross-user/tenant tests pass; no self-granting roles; owned inputs survive restart |
| M2 — first real news-to-map slice | Official-source ingestion, timestamps, deduplication, one-sector entity/asset registry and explainable overlays | News contracts; identity for review features | Every non-preview estimate has source evidence, as-of time, version and measured review-set quality |
| M3 — fresh mathematical operations | Disposable DB checks, source census, corrected data rebuild, session-aware jobs, original-history warmup and new Astra forecast run | Source service/data; M0 | Verified raw-data-to-store-to-browser run plus repeatability/restart evidence |
| M4 — exposure and institutional scenarios | Position history/valuation, news exposure joins, measured sector feed, saved scenarios and comparisons | M1–M3; exposure data | Portfolio totals reconcile; no fabricated flags; scenario results are reproducible and have meaningful units |
| M5 — regulator case workflow | Cases, assignments, evidence, approvals, scoped institutions and exports | M1; reliable evidence/versioning | Multi-actor case survives restart; every decision links to immutable evidence and authorized actor |
| M6 — fitted macro-policy and evaluated actions | C4 tariff features, macro vintages, fitted C7 projector, scenario validation and cost-aware playbooks | M3–M5; suitable data/scientific evidence | Supported model projection and evaluated outcomes; unsupported claims remain withheld |
| M7 — operational release | Scheduling, monitoring, backups, deployment protection, browser/load/accessibility testing and shadow record | Relevant product milestones | Documented release acceptance met; continuing scientific evaluation stays visible |

M2 and fresh mathematical integration are separable workstreams once their interfaces are specified. The news system need not wait for the original Hamilton model to become production-eligible. Case management can also deliver value while macro-policy estimation remains experimental.

**Decisions needed before the relevant implementation, rather than blockers to this audit**

| Decision | Recommended starting position |
|---|---|
| First news domain | One official-policy/event family plus one sector already represented in the UI |
| First portfolio scope | Explicit long-only equities/current holdings, then point-in-time history; expand asset types deliberately |
| Role grants | Server-managed grants and organization scope; role buttons switch only among authorized grants |
| News estimate semantics | Explainable event/exposure/severity/confidence dimensions first; loss probabilities only with a specified calibrated target |
| Policy semantics | Distinguish fitted conditional projection, hypothetical regime sensitivity and causal intervention claims |
| First deployment audience | Determine whether private personal use, institutional pilot or regulator demonstration; this fixes operational/security acceptance |
| Original FR35 | Resolve Table B's fold definition in a new versioned design |
| Undefined requirements | Set retention, usability and performance acceptance criteria without retroactively inventing measured passes |

The intended product should retain its geography, sector, asset and role vision. The development task is to give each surface a reliable source, a defensible estimate, a durable workflow and a testable completion criterion.
