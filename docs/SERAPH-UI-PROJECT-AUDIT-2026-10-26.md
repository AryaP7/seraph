# SERAPH — project, frontend and demonstration audit

**Report date: 26 October 2026 (IST). Audit began 25 October.**
**Scope: audit and planning only. No application fixes or model changes were made.**

## 1. Verdict

SERAPH contains substantial working engineering and real research outputs. The redesigned frontend is **not ready to be signed off as a complete, reliable college demonstration**. The most urgent problems are interaction wiring, inconsistent decision context, incomplete workflow parity, and presentation of illustrative data alongside real outputs.

The globe has not disappeared from the code or the redesigned Risk Map: it rendered during this audit. The original visual identity can be retained. Rebuilding the whole frontend is unnecessary; repair the shell and event bridge, connect the existing backends, and extend the original design system.

The existing redesign documents' statements that every workflow is available and Classic is unchanged are stronger than the evidence supports. A high automated-test pass count is not a completion percentage.

### What “fabricated preview” actually means

Some original visual components contain hardcoded demonstration values: market ticker prices, desk counts, geographical stress ratios, sample holdings, and fallback analytical displays. Other components read real stored research outputs or sourced news. Thus the whole application is not fabricated, but the mixed presentation is confusing and requires separation at the point of display.

There should be three explicit, independently understandable modes:

| Mode | Meaning | Display rule |
|---|---|---|
| Current observation | A connected, timely observation which passes its publication rules | Show its own source time, connection state, and coverage |
| Historical / research replay | Real stored data and model output for a specified decision/sample | Show decision date, availability date, limitations, and validation status |
| Visual demonstration | Illustrative data used to demonstrate design or interaction | Opt-in, prominently identified, isolated from measured readouts |

Current news does not make a historical CSRS current. A fitted model is not automatically a validated prediction. A missing value must not become zero or a decorative synthetic series.

## 2. Evidence, tests and limits

### Executed

- Inspected the authoritative objectives and functional requirements in SPEC, architectural boundaries, research amendments, dashboard sources, launchers, frontend baseline, and existing test coverage.
- Opened all **14 redesigned routes as Retail**: Current, Risk Map, Historical, Console, Signal Feed, Pillars, Exposure, Forecasts, Early Warning, Workspace, Evaluation, Health, Tools, Method.
- Inspected six additional Institutional route states and seven Regulator route states. Role switching was reproduced both failing temporarily and eventually succeeding.
- Captured screenshots and accessibility snapshots. Confirmed globe rendering and spin pause/resume state; exercised India/Global controls. The Assets control did not produce a sufficiently clear verified result and remains unverified.
- Started a UI-only Classic instance, with its news worker disabled, to inspect the fallback and compare implementation surfaces.
- Ran the full Python suite: **2,752 passed, 2 failed, 24 skipped, 3 warnings**, approximately 29 minutes.
- Reran 17 database-dependent skipped tests against the existing guarded, disposable test database: **17 passed**.
- A navigation assertion was corrected outside this audit while it was running. Its targeted recheck passed: **1 passed**.
- Mechanical invariant checks passed their implemented subset; this is not a proof of every architectural/scientific invariant.
- An isolated temporary-workspace probe reproduced the exact upload event failure without committing to a user's portfolio.

Across these runs, the latest result for each exercised test is **2,770 passed, 1 failed, 7 skipped**. This is a reconciliation across runs, not a fresh all-green run of a frozen checkout.

### Remaining test failure and an audit side effect

The existing test at tests/test_csrs_batch_scoring.py, test_scoring_is_idempotent_on_decision_id, opens prototype_runs/live.sqlite directly and calls the real commit path in its replay stream. During the full suite it changed the latest saved replay from **archive:2026-10-22 to archive:2026-10-23** before failing its assertion.

This was an unintended saved-data mutation caused by running the existing test. No blind rollback or repeat against that store was attempted. It did not change application source, but it means this audit was not entirely read-only with respect to saved runtime data. The failure does not by itself establish that committing the same decision twice is broken: the assertion compared different session IDs. The test must be isolated and reseeded before its idempotency claim can be assessed.

Remaining skips: four CT-3 intraday-fixture checks, one store-versus-replay session mismatch, one opt-in live NSE test, and one stopped-worker check skipped because a worker was running. Missing test fixtures are not evidence that the research corpus is absent.

### Concurrent changes and source integrity

The audit created reports, logs, screenshots and an isolated probe under docs/evidence. It did not edit application, script or test source.

At the final source checkpoint, of **447 tracked-by-this-audit source files**, 443 matched the starting hashes. Four changed outside the audit's actions while it was running:

- seraph/dashboard/redesign/app.py
- seraph/dashboard/redesign/component_workspace.py
- scripts/warm_native_hawkes_history.py
- tests/test_redesign_console_e2e.py

The navigation test correction was individually verified. The late Workspace changes added import-quality presentation; the missing portfolio_id and disconnected saved-portfolio analysis paths were still present on a final source check. Other concurrent work was not fully revalidated. Source line anchors below refer to the inspected snapshot and can shift as concurrent work continues. Pre-existing uncommitted changes were preserved. The before/after manifests and Git status captures are in the evidence folder.

### Limits of this sign-off

This is a broad source and runtime audit, not proof that every possible input, permission boundary, data vintage, market state, browser or screen size works. It did not complete a live in-session market-data soak, 100-user load test, broker reconnection demonstration, production OAuth/TLS deployment review, exhaustive accessibility assessment, or every persistent browser workflow. Known broken upload wiring was probed in isolation instead of writing to user portfolios.

The available SPEC says its objective text is verbatim from Chapter 6. The original college-submitted PDF/document was not independently verified against it. The traceability below therefore uses SPEC plus the documented amendments, and keeps their inferred acceptance criteria distinct from the original objective wording.

## 3. Findings

Priority: **P0** protects evidence/data integrity; **P1** blocks reliable demonstration; **P2** is a substantial usability/design or verification gap.
Evidence labels: **Observed** in the browser, **Probed** in an isolated execution, **Source** established from code, **Artifact** from stored output.

### A01 — P1 — Background news requests can block role switching

**Observed + Source.** An automatic news_project request occupied the single in-flight request slot. Clicking Institutional left Retail selected and showed “a news_project request is already in flight.” A timeout can be made worse by another click: request() changes the state back to pending, hiding Retry/Cancel without starting a new timeout. A fresh attempt and cancellation allowed Institutional and then Regulator to work.

The role backend exists; the problem is request scheduling, acknowledgement and recovery.

Source anchors: redesign/console_component/bridge.js lines 38, 84–113, 704–710, 766–806; redesign/app.py lines 110–128, 221–250, 358–410. The host documents roughly 50 seconds for news aggregation while the bridge times out at 15 seconds and requests refresh every 30 seconds.

**Plan:** Give foreground actions priority; acknowledge every request ID explicitly, including no-op selections and errors; separate background refresh from action state; keep cancellation/retry visible and preserve idempotency. Cache expensive news by the relevant revision/context.

**Acceptance:** Retail → Institutional → Regulator works repeatedly during slow/background news refresh. A failed refresh never blocks navigation or role change. Role badge, content and permission projection agree.

### A02 — P1 — Portfolio upload Preview and Save omit a required argument

**Probed + Source.** The actual Workspace buttons emit ws_preview and ws_commit without portfolio_id. The backend requires it. Both emitted payloads produced **ValueError: portfolio_id is required** in the isolated probe. Supplying the selected ID to the backend accepted the same one-row audit input, valued at INR 28,000.

Source anchors: redesign/component_workspace.py lines 69–81; dashboard/console_backend.py lines 578–603; redesign/app.py event dispatch. Existing tests manually supply portfolio_id, so they miss the UI defect.

**Plan:** Bind the selected portfolio ID into both browser actions and maintain it across rerenders. Test the actual emitted event, rejected rows, duplicate imports and successful persistence.

**Acceptance:** Select portfolio → upload → preview → save → reload → inspect the saved snapshot, using a disposable demonstration workspace.

### A03 — P1 — Saved portfolio selection does not feed the main analysis

**Source.** The redesigned host passes ad-hoc rd_console_portfolios results into project_run. It does not call the implemented resolve_active_portfolio path or provide saved holdings/portfolio_context. The selected saved portfolio is used in the Workspace bundle, leaving analysis disconnected from that durable selection.

Source anchors: redesign/app.py lines 363–374; redesign/data.py resolve_active_portfolio; Classic prototype_app.py around lines 1370–1415.

**Plan:** Resolve one active portfolio snapshot and time basis, then feed it to Exposure, overview summaries and supported news-exposure routes.

**Acceptance:** Changing the active saved snapshot changes the derived exposure values, names the same portfolio/snapshot in every affected panel, and survives reload. Historical holdings must use an explicit as-of selection.

### A04 — P1 — The shell gives the ticker the flexible content row

**Observed + Source.** The brown FABRICATED PREVIEW badge expands vertically and consumes useful screen area. The later shell grid has five explicit rows, while a dynamically inserted route crumb creates a sixth child. The ticker falls into the flexible 1fr row. Fixed iframe/shell heights and nested scrolling compound the effect.

Source anchors: redesign/console_component/index.html #shell styles around lines 19 and 389; bridge.js show() around lines 718–729.

**Plan:** Use explicit grid areas for header, route/context, status, ticker, content and footer. Size the ticker to its content, use a bounded flexible content region, and choose one primary scroll container.

**Acceptance:** No stretched badge, empty ticker block or inaccessible content at 1280×720, 1440×900 and 1920×1080, plus narrow-width checks. Header controls remain readable and reachable.

### A05 — P1 — Decision dates, pillar vintages and composite participation disagree

**Observed + Source.** Current showed a 2020 archive banner alongside October 2026 pillar readings and forecast data. Latest pillar inputs were not all from the same session. The composite reader independently selects the latest replay decision, while its “scored” list is built from numeric latest-vintage values rather than the composite's actual mask.

Consequently “a pillar has a recent value” can look like “this pillar contributed to this score,” even when freshness rules excluded it.

Source anchors: redesign/current_session.py latest_session(), composite_status() lines 113–175; redesign/component_views.py current() from line 603; redesign/app.py payload assembly.

**Plan:** Carry an explicit context through every panel: mode, run, decision ID/time, input vintages, mask, weights artifact, news clock and portfolio basis. Separate latest available observations from the inputs actually used in a composite.

**Acceptance:** Every number can be traced to the correct decision and source time. The same page cannot imply a 2020 CSRS and 2026 forecast are a single contemporaneous reading.

### A06 — P1 — New views do not consistently use the role projection

**Observed + Source.** Retail Pillars withholds model internals, but new Current/Early Warning paths render raw pillar/feature details separately. Gateway tests verify the older projected payload, not every new server-generated HTML branch.

This establishes inconsistent role presentation; it is not evidence that a real private institution dataset was exposed during the audit.

**Plan:** Specify the field policy per role and apply it before constructing all view markup. Keep local demonstration role switching clearly separate from authenticated identity.

**Acceptance:** Every route has Retail/Institutional/Regulator field-level tests, including hidden payload/markup checks. Unauthorized fields are absent, not merely CSS-hidden.

### A07 — P1 — Fabricated and measured layers coexist too closely

**Observed + Source.** Hardcoded ticker prices, “1,019 desks,” geographic stress ratios, sample holdings and fallback pillar previews coexist with real archive data and sourced news. The globe combines measured news markers with illustrative stress geometry. Labels help, but are too broad and visually inconsistent to establish which individual values are trustworthy.

Source anchors: redesign/console_component/index.html around 1752, 1853, 1886, 2331; bridge.js preview stamping, Exposure and Pillars render paths; news_layer.js preview visibility.

**Plan:** Preserve these visuals in Classic and an explicit Visual Demo mode. Operational/research views use measured values or informative unavailable states. Add provenance to each layer and detail panel. Never replace unsupported sector risk with a convenient synthetic number.

**Acceptance:** Inventory every displayed numeric field as measured, derived, unavailable or illustrative. With demo mode off, no fabricated ticker, portfolio, desk count or stress value remains in analytical panels.

### A08 — P1 — Frontend parity is incomplete despite documentation saying complete

**Source + selected browser checks.** The redesigned application does not expose the full Classic workflows for institution decomposition upload, retrospective network artifact selection, fitted macro-policy paths, defensive-action comparison, watchlists, portfolio snapshot activation/history, scenario review/comparison, or full case management/export. Evaluation renders reports[0] without a report selector. News pagination state exists without a usable page control.

A Workspace scalar-results table also filters away nested scenario output, so a valid backend trajectory can be invisible.

Source anchors: Classic institution_ui.py, network_ui.py, scenario_ui.py and prototype_app.py; redesign/app.py, component_workspace.py, component_views.py evaluation() line 427. Tools still refers to “MY WORKSPACE,” which is not the current navigation label.

**Plan:** Replace the parity checklist with evidence-based workflow rows. Reuse existing services and artifacts through the new UI. Do not count a backend function or a button as a completed workflow.

**Acceptance:** Each workflow has a browser start-to-finish demonstration, expected persistent result, and evidence of the correct role/data context.

### A09 — P2 — Signal Feed exposes internal records instead of an intelligible event story

**Observed + Source.** The feed prioritizes raw fields such as confirmed_statement / unknown / unknown, registry source notes, first-seen timestamps and licensing metadata. Headlines lack a clear hierarchy, unrelated events crowd the stream, and “No supported target impact” is repeated without helping the user decide what to inspect. Some entity-encoded text is displayed literally.

Source anchors: bridge.js newsEvidence() around line 690 and Feed rendering around line 732; headline escaping paths.

**Plan:** Each event card should answer: **What happened? Who reported it? When? Why is it relevant here? What evidence supports that connection?** Keep the source link and publication/first-seen distinction visible. Put technical metadata and provenance in an expandable drawer.

Add filters for relevant/all events, sector, source, event type, evidence status and time range, with working pagination. “No mapped portfolio connection” should be a neutral information state, not an implied zero impact.

**Acceptance:** A nontechnical reader can explain a selected alert, its date and its limitations without reading raw field names. Non-English headlines display correctly; unsupported translation/impact is not invented.

### A10 — P2 — Two conflicting visual systems are shipping

**Observed + Source.** Original black/charcoal/amber surfaces coexist with navy cards, electric blue selection and lavender product accents. The inconsistency comes from hardcoded component styles and redesign tokens, not a user's theme choice.

Source anchors: redesign/tokens.py lines 16–30; redesign/console_component/index.html new inline styles; redesign/app.py host styles and theme.py.

**Plan:** Make the original palette authoritative and apply the reference geometry, chart treatment, icons and spacing on top of it. See section 5.

**Acceptance:** All 14 routes share the same background, panel, text, border, button and status tokens. No blue/lavender product rebrand remains. Existing meaningful series colors may remain when consistently labelled.

### A11 — P2 — Charts and timeline do not deliver the intended interaction

**Observed + Source.** Historical plots are static SVG polylines with limited scale/context. The timeline is a static SVG, not a date-selection control. Tooltips, linked cursor, range selection and evidence drilldowns are missing from these components.

There is a separate source-level data correctness defect: missing CSRS values break the line, but missing benchmark returns are omitted from the point list without a gap marker, so a line can bridge missing benchmark dates. The observed 81/81 matched sample did not exercise that case.

Source anchors: component_views.py _history_block() lines 159–240; instruments.py timeline() lines 326–381.

**Plan:** Introduce real interactive time-series charts, explicit axes/units, consistent missing-data segmentation and a keyboard-operable selected-date timeline. Preserve raw samples; do not smooth away spikes or invent observations for visual appeal.

**Acceptance:** Hover gives exact values, timestamp, source and mode. Selection updates all dependent panels. Missing dates remain gaps. Confidence intervals and signed contributions are represented honestly.

### A12 — P2 — Forecast meaning and warning state need clearer separation

**Observed + Source.** New Early Warning says “of the loss event” but omits the full event definition present in Classic: a research market-index decline of at least 10% from decision close at a close within 15 sessions. Forecasts is also used for research horizon results, creating a competing meaning.

The new UI omits Classic's forecast-versus-threshold history chart. A calibrated threshold does not demonstrate predictive skill, and NO WARNING does not mean safe.

Source anchors: component_views.py warning() from line 297, current() forecast section; Classic prediction panel.

**Plan:** Show event, horizon, issue date, probability, threshold and validation status together. Separate “Market state” from “Future-loss research forecast.” Rename the research-results page or clarify its scope. Restore threshold-history and outcome inspection.

**Acceptance:** A viewer can distinguish 6.92% predicted probability from the 12.52% warning threshold and from a CSRS score. A stale or unvalidated forecast remains visibly so.

### A13 — P1 — Classic is available but not an immutable rollback

**Artifact.** Against the saved October 24 baseline, 29 of 33 compared files match and four differ: console_backend.py, console_component/bridge.js, console_component/index.html and prototype_app.py. These differences predate this audit. The launcher remains available, but “Classic is unchanged” is not true byte-for-byte.

**Plan:** Preserve a runnable Classic baseline and its backend compatibility contract, dependency/configuration manifest and screenshots. Keep separate launchers/URLs and rehearse switching and restoration without destructive Git resets.

**Acceptance:** New design changes cannot alter the frozen Classic assets. A documented rollback restores the verified experience and does not overwrite shared stores.

### A14 — P0 — Test isolation and evidence claims need repair

**Executed + Source.** One test wrote to the application replay store. Existing frontend “E2E” tests are largely markup/backend checks; they bypass the actual browser payload that breaks upload. This explains how extensive test success coexists with a broken workflow.

The earlier navigation failure is **superseded**: its externally corrected 14-page assertion passed a targeted recheck.

**Plan:** Require disposable stores for every mutating test, reject configured application stores, and test emitted browser events through the full host dispatch path. Add a deterministic test clock and immutable fixtures.

**Acceptance:** A full suite leaves application stores and source hashes unchanged. Browser workflow tests would fail for A01–A03 before fixes and pass after them.

### A15 — P1 for sign-off — Demonstration and scientific validation remain different deliverables

**Artifact + Source.** The evaluated report exposed 0 measured and 152 unavailable result cells; it cannot substantiate predictive success. Hamilton is retained but structurally excluded/NOT_PRODUCTION in the inspected archive. Hawkes is a documented diagnostic, not a demonstrated independent forward alarm. RMT has documented universe/coverage amendments.

**Plan:** Present three separate statuses per feature: implementation tested, real-data output available, empirical acceptance measured. Preserve failed/unavailable results and do not make them appear successful through new graphics.

**Acceptance:** The college demonstration and written claims agree with the actual artifact, version, date and amendment. No claims of three-pillar predictive dominance or measured early-warning skill without supporting results.

## 4. Page-by-page plan

| Page | Audit outcome | Planned interaction and design |
|---|---|---|
| Current | Mixed archive/current context; raw details bypass role presentation; newest pillar does not mean composite participant | Session selector; central original-color score dial; three compact pillar cards; separate forecast card; source-time drawer; contributors derived from the actual mask |
| Risk Map | Globe renders; real news and illustrative stress coexist; Assets result unverified | Preserve globe/camera identity; explicit News / Measured sector diagnostic / Visual demo layer controls; click opens sourced evidence; unavailable sectors remain unfilled |
| Historical | Real archive can be explored; current static chart/timeline falls short | Reference-style gradient line/area history, accurate independent axes, brush/range controls, cursor-linked date selection and a bottom timeline |
| Console | Real score/explanation present but cramped by banners/ticker; old graph treatment | Reference risk dial plus coverage badge, “what changed / why” summary, signed attribution and drilldown to evidence; retain technical detail behind disclosure |
| Signal Feed | Dense raw records; little guidance or relevance control | Rounded event cards, consistent outlined icons, compact severity/evidence markers, filters, pagination, linked evidence and portfolio connections |
| Pillars | Retail gated, other roles receive raw dictionaries; fallback preview below; shell wastes space | Hawkes diagnostic trace and support; RMT eigenvalue/MP plot; Hamilton regime display only when eligible; each card explains value/absence and opens technical detail |
| Exposure | Saved portfolio disconnected; illustrative holdings mixed in | Active-snapshot selector, measured exposure bars with rounded ends, allocation table/sparklines, explicit unmapped share and time basis |
| Forecasts | Retail gated; research horizon output can be mistaken for a current prediction | Clearly titled horizon/research evaluation; actual metric comparisons with support/sample labels; preserve unavailable rows |
| Early Warning | Navy/blue mismatch; incomplete target wording; missing history chart | Original-color concentric probability/threshold presentation with clear labels; full event definition; decision-date history with forecast/outcome inspection |
| Workspace | Upload actions malformed; activation/history and several workflows missing | Three clear areas: Portfolios, Scenarios, Cases. Stepwise import, preview, save, activate; persistent selection; scenario trajectory and comparison; visible case state/history |
| Evaluation | Real report status available, many unavailable cells; no report picker | Report/run selector, measured/unavailable counts, experiment coverage grid, expandable reasons and artifact links; show ROC/calibration only when real supported results exist |
| Health | Useful diagnostic content but too much raw detail and a different theme | Source→ingestion→feature→pillar→score→publication pipeline cards, last-success/latency badges, accessible status colors, error drilldowns; no fake percent-complete rings |
| Tools | Some legacy dispatch exists; missing institution/network/policy surfaces | Role-specific tool cards linking to actual supported workflows, input validation, output visualizations, retrospective network artifact picker |
| Method | Definitions exist but are separated from what users see | Linked explanation of each visible metric, original objectives versus amendments, data lineage, model/weights versions, limitations and the original three pillars |

## 5. Reference-faithful visual direction, preserving SERAPH

The screenshots should guide **shape, composition, spacing, line treatment, gradient depth, icons and interaction**. Their blue/purple branding should not replace SERAPH's identity.

### Palette and structure

Use the original source palette as the baseline: background **#030304**, panel **#0A0A0B**, divider **#1F1F21**, text **#CFCDC8**, muted text **#78746C**, amber **#C9A63A**, highlight amber **#E3C76A**, risk red **#B7362A**, green **#4F9E6A**. Verify contrast before retaining muted text at small sizes. Existing violet **#8B6BD0** can remain a labelled series accent where it already has meaning, not a new product-wide theme.

Proposed reusable geometry: 14–18 px card radii, 8–10 px controls, fully rounded bar caps, consistent 16–24 px card padding, fine neutral borders, restrained shadows and soft gradients. These are implementation targets to compare visually against the supplied references, not measurements claimed to have been extracted from them.

Retain the SERAPH wordmark, globe, dark terminal character and amber navigation. Keep monospace for numbers, identifiers and technical metadata; use a readable sans-serif for descriptions and event narratives. Do not make the whole product a wall of small uppercase text.

### Specific reference translations

| Reference feature | Faithful construction | Suitable placement | Data constraint |
|---|---|---|---|
| Multicolored glowing curves with shaded depth | Thin crisp line, restrained halo, translucent fill fading into charcoal; subtle grid and precise crosshair | Historical risk series, measured pillar history, scenario trajectories | Separate unlike units; no stacked sum unless components really add; retain gaps |
| Mirrored lower curve panel | Linked aligned subplot around a real zero baseline | Signed returns, residuals or signed contributions if available | Do not mirror positive values merely to reproduce a shape |
| Rixor semicircular risk score with orbital rings | Rounded arc caps, center score, small status label, subtle contextual rings, outer CI arc | Console/Current CSRS and Early Warning probability as separate instruments | Each ring has a named quantity; ornamental rings must not imply measured data |
| Rounded vertical risk-breakdown bars | Deep tracks, rounded fills, clear category/value labels, lightweight icons | Nonnegative effective fusion weights or portfolio sector exposure | Signed Shapley requires a diverging zero-centered layout, not positive percentages |
| AltRank-style radial sectors | Equal-angle sectors with a shared disclosed radial scale, neutral grid and central context | Comparable normalized sector/pillar diagnostics where support exists | Show exactly the real dimensions; do not invent a fourth pillar to fill four quadrants |
| Galaxy-style radar polygon | Fine radial grid, outlined vertices, translucent fill and visible axis labels | Side-by-side normalized scenario profiles, if normalization is meaningful | Missing axes stay missing; no fake aggregate “score” just to fill the center |
| Concentric rounded rings | Clean arc geometry and tick marks, compact legend with exact values | Forecast probability/threshold or real data-coverage fractions | Do not label CSRS as sentiment or confidence; unlike units need separate scales |
| Connected risk-driver cards and bottom time rail | Rounded cards with icon, state-color header, compact sparkline, curved connectors and click-through evidence | News-to-documented-exposure paths; Health pipeline; retrospective network archive; scenario flow | Distinguish lineage, hypotheses and fitted excitation; a line is not automatically causal |
| Seasonal overlay and bar-plus-line reference charts from earlier screenshots | Thin selected-year emphasis; rounded paired bars and separately labelled line axis | Genuine year-comparable research returns, validation/support comparisons | No annual “seasonal forecast” without the required aligned data; disclose dual axes |

The apparent “3D color” in the graph reference is principally layered translucency and gradient fill. Reproduce that depth without extruding chart coordinates or distorting values.

### Required interactions

- Consistent hover/click/focus states; tooltip content has units, observation time, mode and source.
- Charts support keyboard selection and an accessible table equivalent.
- Timeline date selection updates score, pillars, exposure and evidence together.
- Clicking a contribution opens its calculation/provenance; clicking an event opens its source and documented mappings.
- Loading, empty, stale, permission-denied and failure states use the same card system.
- Motion is subtle and respects reduced-motion preferences. Globe animation and data-loading animation must be distinct.
- Use one coherent outlined icon family with consistent stroke/size and accessible labels.
- Compare the implemented components side-by-side against the supplied references at a fixed viewport. A generic “dark dashboard” resemblance is not enough.

## 6. College objective and requirement traceability

Status is deliberately conservative: a passing unit test demonstrates implementation behavior, not all real-data or predictive acceptance criteria.

### Objectives O1–O10

| Objective | What can currently be evidenced | Remaining acceptance |
|---|---|---|
| O1 Unified framework | Real archive/composite pipeline, contract tests, masks and provenance | Consistent frontend context; demonstrate supported end-to-end stream and clearly disclose unavailable pillars |
| O2 Hawkes contagion | Native five-minute discrete diagnostic and documented empirical amendment | Complete required coverage/window evidence; trace unresolved original kernel/sector/network clauses; no independent forecast claim |
| O3 RMT monitoring | Actual spectral outputs and universe amendment | Demonstrate daily coverage, calibrated aggregation/bootstrap/representativeness artifacts; measured precursor target is not established by UI output |
| O4 Hamilton regimes | Family retained, research output and explicit structural exclusion | A valid eligible three-state fit and acceptance evidence; unavailable status is honest but does not fulfill the original performance objective |
| O5 Dynamic fusion | Fusion/calibration machinery and stored outputs | Eligible inputs, immutable weights evidence and measured held-out AUC/lead-time results |
| O6 Reconciliation | Kalman/noise/mask implementation tests | Matched-fold measured comparison, empirical CI coverage and explicitly resolved acceptance gaps |
| O7 Ablation | Registered harness/report exists | Measured supported cells; 0 measured/152 unavailable does not establish fusion dominance |
| O8 Tariff covariate | Event/covariate implementation and provenance mechanisms | Supported Hamilton comparison with/without covariate and significance evidence |
| O9 Transfer | Transfer/archive machinery tested | Real second-market fixed-weight result with matching weight hash and measured out-of-sample metric |
| O10 Decision support | Several tested services, explanations and partial UIs | Seven complete browser workflows, role correctness, persistence, understandable presentation and honest limitations |

### Functional requirements — all IDs accounted for

| FRs | Audit classification | Required closure evidence |
|---|---|---|
| 1–2 | Acquisition/price pipeline implemented; corpus completeness not certified here | Source coverage manifest, requested/completed windows, gaps and benchmark lineage |
| 3–4 | Macro/event paths and tests exist | Available-at/vintage traceability and complete required covariate/event coverage |
| 5–6, 50 | Feature and jump-extraction implementation tested | Native-bar fixture replay and detector/support evidence; resolve skipped CT-3 fixture checks |
| 7 | Point-in-time/corporate-action mechanisms exist; full corpus assertion not proven | Audited adjustment and membership samples across breaks/rebalances |
| 8 | PostgreSQL infrastructure present; runtime/workspace SQLite also used | Document amended persistence boundaries and prove required series/history are archived |
| 9 | Explicitly cut by specification | Keep out of completion denominator |
| 10–11, 13 | Amended native-bar Hawkes implementation | Window-level convergence/stationarity/support evidence; retain diagnostic scope |
| 12 | Original inhibitory-kernel clause needs explicit amendment reconciliation | Show the implementation and accepted scope decision; do not silently count it fulfilled |
| 14 | Sector computation/report path exists | Real sector flags with thresholds, support and availability; remove reliance on preview visuals |
| 15 | Retrospective network artifacts exist; redesign access missing | Inspect both original and exclusion fits with provenance; do not promote to live/causal network |
| 16–17 | RMT output exists, N/Q amendment documented | Daily spectral evidence, rebalance/common-support checks and actual coverage labels |
| 18–19 | Code/test support is not complete empirical acceptance | Calibrated weights plus 1,000-bootstrap result/provenance per required daily update, or documented scoped exception |
| 20–21, 23–24 | Hamilton currently unavailable/ineligible in inspected research archive | Eligible nondegenerate regime result and uncertainty/half-life evidence, or explicit academic scope amendment |
| 22 | Tariff feature implementation exists | Dated inputs, decay/sector mapping provenance and supported downstream use |
| 25–27 | Reconciliation implementation tests pass | Integration replay through actual vintages and matched forward-fill comparison |
| 28–31 | Fusion/CI/weights/attribution paths exist | Correct decision/mask display, immutable weight IDs and measured calibration evidence |
| 32–36 | Harness exists; inspected report has unavailable empirical results | Supported chronological folds, metrics, sensitivity and ablation evidence; retain failed/unavailable cells |
| 37 | Transfer machinery tested | Fixed-hash second-market measurement without retraining |
| 38 | Archive machinery and DB tests present | Demonstrate source-to-output-to-report retrieval and isolation from test writes |
| 39 | Partial frontend delivery | All specified plots, supported network archive, micro-flags and regime views wired; unavailable states where justified |
| 40 | Warning logic exists | Threshold source, crossing behavior, stale/current state and no-warning meaning demonstrated |
| 41 | Historical plot available, interaction/gap defect remains | Exact alignment, both units, missing-data behavior and linked historical selection |
| 42 | Role backend exists; bridge and new-view policy inconsistent | Reliable role switching plus every-route projection and authenticated deployment distinction |
| 43 | Backend exists; redesigned import/activation/exposure broken | Disposable browser portfolio workflow with reconciled percentages and persistence |
| 44 | Explanation exists | Clear dominant-pillar explanation with correct mask/time basis and nontechnical comprehension check |
| 45, 51 | Market-level flow diagnostic paths retained | Dated FII/DII/residual figures; no per-instrument counterparty claim |
| 46 | Backend/Classic capability, redesigned parity gap | Actual supported defensive-action comparison, realized-drawdown units and retrospective label |
| 47 | Scenario dispatch exists, new result visualization incomplete | User shock → baseline/scenario trajectories → comparison → save/reopen |
| 48 | Policy simulation parity gap | Supported fitted macro-path input/output and explicit unsupported-state handling |
| 49 | Action/case primitives exist; full workflow not browser-certified | Create/review/log/reopen/export with alert and decomposition linkage |
| 52 | Constructor/tests and universe amendment exist | Filter-before-rank proof and documented actual N, Q and representativeness |
| 53–54 | Validation obligations not certified by this UI audit | Versioned OHLC-vs-intraday correlation and reconstructed-vs-official-index correlation artifacts |

### Nonfunctional requirements

- **NFR1–8:** latency, cadence, parallelism, coverage and 100-user behavior require an isolated performance/in-session test. The observed role wait already demonstrates a responsiveness problem. Approximate historic data-volume planning figures are not acquired-row evidence.
- **NFR9–10:** 99.9% uptime is explicitly a hypothetical production target; do not count it as a college deliverable. Rehearse the actual single-node restart procedure.
- **NFR11–20:** predictive/lead-time/calibration targets require measured artifacts. Preserve unresolved numerical acceptance gaps instead of inventing thresholds.
- **NFR21–22:** provenance/decomposition components exist; readability and meaning are currently insufficient, especially Signal Feed. Conduct a short nontechnical comprehension walkthrough.
- **NFR23–27:** localhost role demonstration does not certify OAuth2, TLS, AES-256, immutable complete audit logging or retention. Verify/configure the intended deployment separately and identify unresolved retention policy.
- **NFR28–29:** modular sources and extensive tests are strengths; browser-path coverage and test-store isolation need repair.
- **NFR30–36:** confirm supported laptop resources and reproducible environment/Compose launch. GPU and high-bandwidth NIC requirements were cut; do not reintroduce them.

### Network diagnostic status — important correction to older handoffs

The older “keep F07 pending” note was superseded in the repository by DR-11 and saved artifacts. This audit did not execute a fit or authorize further modeling.

1. Full adopted interval, artifact **07d00f7365201da1…**: insufficient_support, 10,641 bars, five supported nodes, two within-session breaks, no matrix/edges.
2. Separate disclosed exclusion variant, artifact **a4a228b31626716a…**: fitted, 10,513 bars, excludes 2020-03-13 and 2020-03-23; four cross-sector edges above the display threshold. Its provisional basket has uneven constituent support, which belongs in the display.
3. Both are retrospective diagnostics. Conditional excitation weights are not causal effects or loss probabilities; the full-sample fit is not available to earlier decisions.
4. The handoff leaves the result-of-record choice unresolved. Preserve both artifacts and their distinct scope rather than silently replacing the unavailable original.

## 7. Ordered implementation backlog — plan only

Do not start these edits as part of this audit. Preserve the original three pillars and existing scientific records. Frontend changes should not change model equations, thresholds or evaluation protocol.

| Order / ID | Priority | Work | Depends on | Done when |
|---|---|---|---|---|
| 1 / T01 | P0 | Isolate every mutating test from application stores | — | Full suite cannot write production/research runtime paths; side-effect test uses seeded temporary store |
| 2 / T02 | P1 | Freeze and rehearse Classic fallback | — | Baseline/hash/config manifest, separate launchers and verified rollback without store loss |
| 3 / T03 | P1 | Replace optimistic parity claims with verified inventory | — | Every page/control/workflow maps to source, payload, handler, result and observed status |
| 4 / T04 | P1 | Repair foreground/background request scheduling and explicit acknowledgements | T01 | Role, selectors, retry and cancel work during slow news operations |
| 5 / T05 | P1 | Correct shell rows, ticker sizing and scrolling | T02 | Screens remain usable at target viewport sizes with no stretched preview badge |
| 6 / T06 | P1 | Unify decision/time/role context and mask interpretation | T04 | Panel contexts agree; latest-input availability cannot masquerade as score participation |
| 7 / T07 | P1 | Fix Workspace emitted import payload | T04 | Actual browser Preview/Save/reload workflow passes on disposable data |
| 8 / T08 | P1 | Wire saved snapshot activation into analysis | T06, T07 | Portfolio choice updates Exposure and supported news mappings consistently |
| 9 / T09 | P1 | Separate operational, historical and visual-demo layers | T06 | All displayed values classified; no hidden illustrative values in operational view |
| 10 / T10 | P1 | Apply role projection to all generated views | T06 | All 42 route-role combinations have field-policy coverage |
| 11 / T11 | P2 | Consolidate original palette, typography, radii and icons | T02, T05 | Shared token usage and visual comparison on all 14 pages |
| 12 / T12 | P2 | Rebuild Signal Feed information hierarchy and controls | T04, T06, T11 | Understandable cards, correct Unicode, filters/pagination and evidence drawer |
| 13 / T13 | P2 | Build reference-faithful chart components and gap behavior | T06, T11 | Axes/units/hover/range/keyboard/table support; no fabricated or bridged missing data |
| 14 / T14 | P2 | Make historical timeline a real selection control | T04, T13 | Date selection updates dependent views and survives navigation |
| 15 / T15 | P1 | Complete portfolio/watchlist/snapshot workflow parity | T08 | Save, activate, history and restore demonstrated with durable state |
| 16 / T16 | P1 | Complete shock, macro-path and defensive-comparison workflows | T06, T13 | Supported input produces visual trajectory/comparison; saved result reopens |
| 17 / T17 | P1 | Complete regulator/institution/case workflows | T10 | Correct decomposition import, case lifecycle, action journal and export |
| 18 / T18 | P1 | Expose retrospective network artifact archive | T09, T10, T13 | Both F07 variants inspectable with scope/support and unavailable result preserved |
| 19 / T19 | P2 | Repair forecast wording, page scope and threshold history | T06, T13 | Exact event, horizon, issuance and unvalidated status accompany every probability |
| 20 / T20 | P2 | Complete Evaluation report selection and support display | T06, T11 | Every saved report selectable; unavailable reasons clear; no unsupported success graphics |
| 21 / T21 | P2 | Restyle Health into a usable pipeline monitor | T06, T11 | Stage freshness/failure drilldowns and meaningful recovery guidance |
| 22 / T22 | P1 | Reconcile SPEC clauses with amendments and measured evidence | T03 | FR-by-FR status distinguishes implementation, data availability and scientific result |
| 23 / T23 | P1 | Complete required empirical work or record accepted academic limits | T22 | Registered supported evaluations/coverage/transfer artifacts, no post-hoc claim inflation |
| 24 / T24 | P1 | Verify live market session, restart and reconnect behavior | T04, T06, T09 | Genuine fresh observations propagate; stale/disconnected states are correct |
| 25 / T25 | P2 | Browser regression, accessibility and performance pass | T05–T21 | Full role/route/workflow matrix, keyboard/contrast/layout checks and measured budgets |
| 26 / T26 | P1 | Rehearse and record the college demonstration | T15–T25 | Repeatable script with real evidence, honest limitations and working Classic fallback |

T23 involves research evidence, not cosmetic engineering. A UI developer must not silently alter a model or validation protocol to make that row green.

## 8. Demonstration acceptance script

Use disposable portfolios/cases and a copied replay store. First capture versions, hashes, run IDs and expected results.

1. Start Classic and Redesign independently; verify no duplicate acquisition ownership. Switch between them and show the retained globe/original identity.
2. Select historical replay. State the exact date and data coverage; show score, interval, actual contributing mask and evidence.
3. Change roles while background news is refreshing. Verify role-specific fields and access boundaries.
4. Select a date using the timeline; verify score, pillars, attribution, benchmark and associated evidence move together.
5. Hover a chart point and reconcile it with the stored value; demonstrate a missing-data interval without an invented connection.
6. Open a Signal Feed event; explain it in plain language, follow its source and show why any sector/portfolio mapping is supported.
7. Create a disposable portfolio, preview a CSV with a rejected row, save valid holdings, activate the snapshot, reload and reconcile total/exposure percentages.
8. Run a supported single-pillar scenario; inspect baseline/scenario trajectories, save and reopen. Demonstrate unavailable macro-policy input honestly.
9. Under the correct roles, inspect institutional decomposition and a regulatory case; record and retrieve an action with alert linkage.
10. Open both F07 artifacts. Show the full-interval unavailable result and the separate exclusion variant with its four real edges and limitations.
11. Explain the future-loss event, horizon and threshold. Show a stale/unvalidated example and why NO WARNING is not a safety guarantee.
12. Select an evaluation report; distinguish measured, unavailable and unpublishable results.
13. Demonstrate disconnected feed/restart recovery without confusing the local clock or current news with current market risk.
14. Reopen Classic and verify rollback. Confirm demo operations did not mutate the original research evidence or user workspace.

## 9. Evidence index and review entry points

All audit evidence is under **docs/evidence/ui-audit-2026-10-25/**:

- pytest.log / pytest.xml — full-suite outcome, skips, warnings and two original failures.
- pytest-db.log / pytest-db.xml — 17 guarded DB passes.
- pytest-nav-recheck.log / pytest-nav-recheck.xml — externally corrected navigation assertion passes.
- audit-probes.json — malformed Workspace event reproduction and 33-file Classic comparison.
- source-hashes-before.json / source-hashes-after.json / source-integrity.json — audit source integrity and concurrent changes.
- git-status-before.txt / git-status-after.txt — pre-existing and final working-tree state.
- page-audit-retail.json and named page/role text captures — actual rendered routes.
- role-switch-blocked.png, role-fresh-attempt.txt, role-after-wait.txt — interaction evidence.
- pillars-final-regulator.png — stretched ticker badge and raw pillar presentation.
- risk-map-regulator.png and globe-interactions.json — globe presence and interaction checks.
- classic-initial.txt — fallback UI inspection.

The temporary Classic audit server was stopped after inspection. The existing redesign server and background workers were left running. The 26-row companion backlog is docs/SERAPH-UI-AUDIT-BACKLOG-2026-10-26.csv.

Primary sources: docs/SPEC.md; docs/ARCHITECTURE.md; README-RESEARCH.md; EXPERIMENT.md; amendments 02–05; docs/REDESIGN-FRONTEND.md; docs/REDESIGN-FEATURE-PARITY.md; docs/decisions/DR-11-2026-10-25-f07-adoption.md; both saved F07 artifacts.

**Audit outcome:** actionable defects and a staged plan are recorded. No listed application repair has been implemented by this audit.

