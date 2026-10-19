# News feature audit — 18 October 2026

**Verdict: a working, connected pilot; not complete or ready for unrestricted release.**
There is substantial functioning software, but correctness defects, incomplete
evidence coverage, unfinished product workflows and an unpassed independent
evaluation remain. A completion percentage would conceal these different gates.

This audit uses the promoted Astra instructions, the news development plan,
completion/limitations documents, current implementation, stored production data,
isolated counterexamples and the ordinary browser flow. It does not change
application code, production news data, the frozen corpus or research results.
Existing uncommitted work and older evidence remain intact.

**Verification performed for this audit**

| Check | Result / evidence |
|---|---|
| News, NI, connected frontend and console backend tests | **545 passed**, [JUnit](evidence/news-intelligence/audit-tests-2026-10-18.xml) |
| Adjacent globe, source, prototype, identity, authorization, current-reader and operations tests | **188 passed**, [JUnit](evidence/news-intelligence/full-audit-2026-10-18/integration-tests.xml) |
| JavaScript | Both news-layer and bridge harnesses passed; news layer has 31 checks |
| Mechanical invariants | Passed; these checks have their documented limits |
| Ordinary browser, isolated database copies | Three roles, holdings submission, unmapped warning, six globe markers and two evidence links passed; layout/screenshot inspected. [Result](evidence/news-intelligence/full-audit-2026-10-18/browser/result.json), [screenshot](evidence/news-intelligence/full-audit-2026-10-18/browser/retail.png) |
| Existing isolated counterexamples, rerun against current code | Seven failure demonstrations remain reproducible. [Script](evidence/news-intelligence/full-audit-2026-10-18/probes.py), [results](evidence/news-intelligence/full-audit-2026-10-18/findings.json) |
| Additional semantic counterexamples | Four further failures reproduced. [Script](evidence/news-intelligence/full-audit-2026-10-18/semantic_probes.py), [results](evidence/news-intelligence/full-audit-2026-10-18/semantic-findings.json) |
| Frozen-corpus release command | **Failed, exit 1**: no reviewed/locked test evidence. [Report](evidence/news-intelligence/full-audit-2026-10-18/release-gate.json) |

These are 733 passing tests across two disjoint selections, not a full-repository
test run. Counterexample scripts intentionally record observed failures rather
than count as passing regressions. Publisher availability was not re-probed over
the network; inaccessible-source reasons below are recorded configuration/evidence,
not new claims about today's websites. No prospective operating trial was run.

**What already works**

The feature acquires RSS/JSON and selected official documents, persists observations
and revisions, respects configured body-storage restrictions, uses conditional
requests, tracks source health, schedules polling, coalesces manual acquisition,
and provides leased requests and worker supervision. It has bounded PDF text
extraction, deferred-document recovery, source-specific backfill and explicit
unrecoverable collection gaps.

Typed quantities, legal/assertion fields, evidence spans, graph traversal, unknown
exposure sizes, current/historical clocks, preview separation and role projections
are implemented. Retail portfolio data reaches the screen. The globe distinguishes
source geography and evidence, and referenced events remain accessible beyond page
one. News remains separate from CSRS and Hawkes/RMT/Hamilton. These are meaningful
completed capabilities, subject to the failures below.

**Confirmed remaining defects — fix before release**

P0 means the output or validation can support a materially false conclusion. P1
means a correctness or reliability requirement still prevents completion. This is
the priority assigned by this audit, not a claim that the old tickets are unchanged.

| ID | Priority | Reproduction and consequence | Required closure / implementation |
|---|---|---|---|
| A01 | P0 | `class_recall` reports **95%** for 95 correctly labelled negatives and five missed supported events: actual supported-event recall is **0/5**. The gate measures whole-document classification accuracy under a recall name. | Separate positive-event recall, negative specificity/false positives and per-class results. Add a regression that cannot earn recall credit from negatives. [news_corpus.py:218](../seraph/validation/news_corpus.py#L218); review the legacy gate's matching denominator too. |
| A02 | P0 | On 18 October, **“effective from 1 December 2026”** yields `effective_at=null` and `in_force=true`. The pattern recognizes named months but conversion accepts only ISO dates; lifecycle then treats the missing value as no future start. | Parse supported date forms with explicit precision; a recognized but unparsed future date must cause abstention, not in-force status. Cover both future starts and future ends/revocations. [event_frames.py](../seraph/news/event_frames.py), [extraction.py](../seraph/news/extraction.py), [lifecycle.py](../seraph/news/lifecycle.py). |
| A03 | P0 | A steel duty title with body **“This order does not apply to products from India”** still emits an adverse Indian steel-sector route at medium confidence. Impact scope checks read the headline, not the retained body. | Carry validated product/country/party exemptions into event frames and enforce them before promoting a target link. Unknown applicability can remain a labelled watch; explicit exclusions must suppress an applicable-impact claim. [estimation.py:265](../seraph/news/estimation.py#L265), [scope.py](../seraph/news/scope.py). |
| A04 | P0 | “Tata Steel halts production” followed by a body denying the halt becomes two events: a confirmed headline with affected targets, plus a separate denial. The denial does not qualify the first event. | Reconcile document-level assertion context before independent-event splitting. Test denial, historical narration, quotations and contradictory clauses. [extraction.py:517](../seraph/news/extraction.py#L517). |
| A05 | P1 | Repeating the same production halt in the title and first body sentence creates two event IDs and repeated target estimates. | Cluster repeated claims within a document; preserve genuinely distinct events and evidence spans. Event counts must reflect events rather than matching sentences. Same adapter as A04. |
| A06 | P1 | Two unrelated Hindi headlines produce the same syndication key because normalization retains only ASCII words/digits. The stored corpus contains Hindi groups of **28 and 9 versions**. | Use Unicode-aware identity with publisher/document evidence; prevent empty-token collisions. Rebuild derived groups and export a new benchmark version after reviewing affected records. Preserve original observations and old frozen manifests. [model.py:155](../seraph/news/model.py#L155). |
| A07 | P1 | A document changes **A → B → A**. The final A is treated as an old duplicate, so B remains current. | Separate reusable content identity from the timeline of observed document states. Repeated current bytes should be idempotent; returning to earlier bytes must record a new state transition. [acquisition.py:445](../seraph/news/acquisition.py#L445). |
| A08 | P1 | With a one-document budget, repeated HTTP 200 feeds and a restarted/expired fetcher cache retrieve the first already-enriched URL on every pass; the second document remains without a body. | Persist successful enrichment and prioritize outstanding documents fairly, with an explicit later refresh policy for changed full text. Verify progress across restart, repeated 200, 304 and exhausted budgets. [enrichment.py:91](../seraph/news/enrichment.py#L91). |
| A09 | P1 | An abandoned `news.poll` job lease causes **zero fetch calls**, while the replacement loop reports `running` / “waiting for next poll.” The generic lease can last 30 minutes. | Reconcile the OS worker lock and job lease safely; surface `lock_unavailable` and failed work instead of treating heartbeat activity as successful polling. Exercise an actual killed worker and replacement. [run_news.py:644](../scripts/run_news.py#L644), [jobs.py](../seraph/operations/jobs.py). |
| A10 | P1 | A strict 08:00 replay shows a worker heartbeat from 10:00, with age **−120 minutes**, and an open gap first observed at 10:00. | Version/filter operational state and gap transitions at the replay cutoff, or explicitly omit unavailable historical operations metadata. Also use historical source metadata for evidence notes. [news_view.py:104](../seraph/dashboard/news_view.py#L104), [roles.py:176](../seraph/news/roles.py#L176), [acquisition.py](../seraph/news/acquisition.py). |
| A11 | P1 | An old duty order and a separately published revocation remain unlinked (`supersedes=null`); the old order stays in force. Supersession works only when a caller already provides the link. | Build an instrument-ID/evidence-based linkage and review workflow. Do not guess links from similar titles. Test proposal → final → effective → amendment/repeal across documents, including unresolved-link warnings. [extraction.py:470](../seraph/news/extraction.py#L470), [lifecycle.py:156](../seraph/news/lifecycle.py#L156). |

**Remaining implementation and data work**

| Workstream | Current limit | Definition of done |
|---|---|---|
| Source contracts and rights | `Source` still has a coarse `may_store_full_text` boolean and prose rights. The plan's per-use permissions, structured review/version metadata and retention policy are incomplete; `retention_days` has no enforcement path. | Model and enforce fetching, transient processing, storage, display and redistribution permissions that the product actually uses. Record reviews/versions, test restricted paths and retention without silently rewriting audit history. |
| Document depth and provenance | **458 stored versions, 24 nonempty bodies**; a body can be only a feed summary. Exchange titles often identify only the issuer, so the subject of the filing is unavailable. PDF text is supported, but general table-cell provenance and annex interpretation are not. | Obtain permitted detail/attachments for the declared pilot sources; retain document/representation hashes, original text evidence and table headings/units needed for supported claims. Scanned PDFs need either validated OCR or explicit exclusion from the supported universe. Do not silently count a title-only feed as full-document coverage. |
| Source breadth | **17 registered endpoints / 12 publishers**, including two fixed historical-document monitors. DGFT, CBIC, MOSPI, IMD, grid and CEA remain listed as unavailable. Energy, pharma, weather, broader China/EU and journalism coverage is incomplete. | Close the policy, company/operations and structural-exposure routes required by each declared sector. Verify every enabled adapter's rights, dates, shape, failure behavior and source-to-screen path. Treat the larger catalogue as a backlog; enabling every listed source is not a prerequisite for a bounded pilot. |
| Exposure coverage | **21 issuers, only 15 with sectors; 28 assets; 64 edges, all unsized.** Twenty-seven assets and 54 edges come from NTPC stations. No asset has verified exact coordinates. | Fill missing issuer/sector mappings, diversify facilities and mechanisms, curate locations at their supported precision and retain cited knowledge dates. Demonstrate a real domestic operational incident, not only the historical capacity-expansion example. Add financial denominators only where supported; MW is not financial exposure. |
| Historical registry coverage | Five places, one entity and all ten source-location mappings lack `known_from`. Strict replay correctly excludes unknown dates, but loses useful routes. | Record supported acquisition/curation dates prospectively, version changes and retain old registry records. Never infer operational availability from the underlying report year. |
| Event identity and evidence independence | A headline-token/day hash remains the central group identity. `reporting_origins` is populated as one group token, not an implemented independent-origin verification workflow. | Separate document duplication, copied reporting, same-event identity, event revisions and corroboration. Support reviewed merge/split/reversal decisions and stable instrument IDs; test mirrors, translations and changed headlines. |
| Reproducible processing | Frames are reconstructed on reads using today's extractor and CSVs. `available_at` comes from story first-seen values, not persisted extraction completion. `version_manifest()` exists but has no production caller; current snapshots are saved, while historical projection rebuilds from current code. | Pin source/document/registry/parser/extractor/rule versions and input hashes in each derived revision. Record processing availability and latency. Distinguish a reconstruction with current rules from replay of what the running system actually emitted. |
| Economic mechanisms and scenarios | Qualitative role rules and safe bounded traversal exist. Product matching remains broad; general HS/versioned tariff schedules, annex applicability, quotas/specific duties and sector mechanisms are incomplete. `tariff_cost_scenario()` is tested but has no production caller. | Connect supported instrument/exposure inputs to scenarios and role UI, enforce scope and compatible units, and show both opposing mechanisms with assumptions. Add remaining mechanism families for the declared universe. Unknown size must continue to produce no monetary result. |
| Role workflows | Three role projections work. Professional document comparison, product-country matrix, news scenario ranges/export and a regulator news-review/policy-timeline workflow are not completed by rendering those projections. | Deliver and browser-test the workflows included in the released scope, with shared facts and source lineage. Keep demo role switching distinct from authentication; use the existing server identity path for any deployed privileged review/write operation. |
| UI consistency | Method-panel code still says news is “Not connected — fabricated previews retained” even when connected; some scope messages claim the body is not retained regardless of actual evidence. Retail weights display excessive decimal places. | Derive status/limitations from the actual record and capabilities; fix stale labels and formatting. Add checks across home, method, details and role views, not just the main banner. |
| Operations at release | A stopped-worker warning works; the copied browser store was stale and showed a stopped worker. Backfill is source-dependent; RSS rotation can be permanent loss. Bounded restarts are not evidence of long-running reliability. | After fixes, reconcile deployed source configuration, run an observed scheduler/manual-refresh/crash-recovery trial, verify backup/restore and end-to-end capture latency, and expose missing coverage against the intended universe. Define prospective duration/acceptance before starting; none is invented by this audit. |

The inventory above was independently read from the store and CSVs:
[inventory](evidence/news-intelligence/full-audit-2026-10-18/inventory.json).
Numeric facility/relationship targets are met; balanced and effective coverage is
not established by those totals. Unsized relationships and regional coordinates
are acceptable for a declared qualitative pilot, provided the product makes no
monetary or exact-location claim from them.

**Validation work still required**

1. **Repair the evaluator before using it for acceptance.** In addition to A01,
   support multi-event gold labels and event matching; measure detection
   precision/recall/F1, target/entity links, location roles, unsupported claims,
   duplicate-cluster errors and abstention. Report source/sector/language/legal
   slices, counts and uncertainty intervals. The current six aggregate slices
   do not cover this entire specification. Unknown/unknown action/legal labels
   should not inflate applicable-field accuracy.
2. **Strengthen look-ahead and adversarial gates.** The current look-ahead check
   only compares frame availability with story first-seen on the small legacy
   examples. It reports zero breaches while A10 reproduces one in the read model.
   Include complete payloads, registry/source versions, operational state,
   processing completion, corrections, context rejection and all new probes.
3. **Create a new adequate frozen corpus after identity fixes.** The existing
   manifest contains **395 documents: 300 development, 95 calibration, zero test**.
   It contains only **13 Hindi documents**, with no independent reviews. Nominally
   it is at least **205 documents** and **87 non-English examples** short, but
   repairing groups and meeting category quotas can change those deficits.
   Required categories are 120 Indian policy, 120 foreign trade/regulation,
   120 company/operations, 80 macro/monetary, 80 logistics/hazards and 80 hard
   negatives; at least 100 non-English examples overlap those categories.
4. **Obtain two independent human reviews**, adjudicate disagreements, measure
   agreement and freeze a 200-example chronological test partition after
   development/calibration. Group all event versions, copies and translations
   together. Current token/day grouping does not establish that guarantee.
   Agent labels and passing regression fixtures do not substitute for reviewers.
5. **Build the separate 150-case impact benchmark** required by plan §9B.
   Label target/role/mechanism/applicability using contemporaneous evidence,
   separately from subsequent outcomes. The present class/stage/sector examples
   are not this benchmark.
6. **Pass the fixed release thresholds:** at least 95% promoted-link precision,
   90% supported-class recall, 98% applicable numeric/unit/legal-stage accuracy
   (the implemented gate also requires action accuracy), zero known temporal or
   context breaches, all adversarial cases closed, and enough examples for each
   claimed slice. Do not lower thresholds to close the feature.
7. **Run prospective shadow operation and all ten integration scenarios** from
   plan §9D with a dated evidence manifest. Include errors, abstentions, revisions,
   missed events, source outages and false alerts. The browser smoke test proves
   delivery, not interpretation accuracy or prospective usefulness.

**Ticket reconciliation**

| Plan tickets | Audit disposition |
|---|---|
| NI00–02 | Baseline preservation, regression infrastructure and additive semantic contracts exist. Target contracts remain partial where noted above. |
| NI03–04 | Partial: extraction, multilingual identity and lifecycle blockers A02–07/A11 remain. |
| NI05 | Traversal/dimensional safeguards exist; scope enforcement, mechanism applicability and full impact validation remain. |
| NI06–07 | Partial: immutable observations and operational recovery machinery exist, but A07–10 and processing/version manifests prevent closure. |
| NI08 | Partial: permitted document and bounded PDF text acquisition works; A08, document depth and table/annex evidence remain. |
| NI09 | PIB/SEBI pilot acquisition exists; language quality and usable permitted detail remain limited. |
| NI10 | Exchange adapters and numeric issuer/facility targets exist; filing substance, balanced mapping and geographic evidence remain incomplete. |
| NI11–12 | Real US-to-India qualitative routes and tariff math exist; Indian trade acquisition, lifecycle, exact scope and integrated scenarios remain incomplete. |
| NI13 | Broader sector/source pilots remain incomplete; close against a declared supported universe. |
| NI14 | Optional extractor comparison has no adequate independently labelled development set/report. A particular NLP/LLM library is not mandatory. |
| NI15 | Ordinary UI delivery passes; replay defects, stale labels and end-to-end semantic acceptance prevent unconditional closure. |
| NI16 | Basic role views pass; advanced professional/regulator workflows remain partial. |
| NI17 | **Open / release blocked** by evaluator issues, corpus/review deficits, missing impact benchmark and prospective evidence. |
| NI18 | Separate research extension. ICIO and incremental predictive usefulness are not prerequisites for a qualitative news pilot. |

**Recommended completion order**

First fix A01–11 with regressions, then complete evidence acquisition, identity,
version manifests and declared-universe exposure coverage. Build the independent
corpus/review and impact benchmark in parallel with that engineering work. Finish
the promised role/scenario workflows, pass the locked gates, and run the declared
prospective acceptance trial. Publish a supported-scope statement and an evidence
index at release.

There is no need to refit or alter the three market pillars to finish this feature.
Proving crisis prediction, comprehensive global coverage, numerical company loss
estimates or universal OCR is a separate scope decision and requires its own data
and validation; none should be silently added to the definition of a completed
qualitative pilot.
