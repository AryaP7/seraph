# News feature: academic-scope stopping assessment

18 October 2026. Inspection and classification only. No application fixes, production-data changes, commits or pushes performed.

## Decision

**Do not implement the whole remaining news backlog. Fix one demonstrated supervision defect, perform one bounded live rehearsal, then freeze the core news feature.** The ordinary browser flow already works with the changed payload. Broader document/source/exposure coverage and advanced professional workflows would add useful functionality, but are not prerequisites for presenting the existing system accurately as an evidence-linked, qualitative, selected-source news-intelligence prototype.

Freezing that scope does not mean the original unlimited-coverage vision is 100% complete, nor that interpretation accuracy or predictive usefulness has been established. It means the intended core path is usable and its academic demonstration has a defensible finish line.

## What the earlier 11 workstreams actually were

The eleven names below come from the **Remaining implementation and data work** table in [NEWS-FULL-AUDIT-2026-10-18.md](NEWS-FULL-AUDIT-2026-10-18.md). They are different from the eleven individual A01–A11 defects. The latter now have remediation code and recorded focused regression evidence in [Amendment 06](AMENDMENT-06-news-audit-remediation.md).

I could not find a reproducible scoring formula for the quoted 65% engineering / 90% demo estimates in the project documents. They should be treated as rough prior judgments, not measured acceptance or a mandate to build another 35%. Nor should the earlier 4-complete/4-partial/3-untouched categorisation override newer implementation. Current inspection shows at least some implementation in all eleven broad workstreams; untouched *subfeatures* remain.

The main remaining gap is broader planned coverage/workflows and empirical acceptance, rather than a core pipeline that is only two-thirds functional. It is **not all production hardening**: document depth, diversified exposure and advanced role tools are meaningful missing capabilities. Their value depends on what is actually promised in the demonstration.

## Current evidence

- Production store inspected read-only: **17 registered endpoints**, 458 story versions, **24 nonempty bodies**. A body may be a summary, so this is not 24 verified complete documents. The roster includes RBI, SEBI, PIB, Fed, Federal Register, USGS, NSE/BSE, USTR and European Commission channels plus two fixed historical documents. It is not an RBI-only system.
- Curated loader: 22 entities including RBI, **21 issuers**, 15 issuers with sectors, **28 assets and 64 edges**. Twenty-seven stations/54 edges are concentrated in NTPC. Sixteen registry records lack known-from dates; strict historical views exclude them honestly.
- Browser: **six globe markers, one geographic exposure arc, two links on the inspected marker**, all three role projections, portfolio submission and the unmapped warning worked. A documented China → India relationship is drawn; a sourced Tata Kalinganagar capacity expansion is associated with its asset. The latter is an explicitly historical fixed release, not proof of current incident monitoring.
- The institutional screen had **23 unsized routes and zero usable accounting scenarios**. Code is connected; the currently held inputs do not satisfy its stated-rate/product/applicability requirements. No monetary loss is invented.
- The stored worker heartbeat was approximately **9.8 hours old** during the browser verification. The UI correctly said worker stopped/stale. The browser scripts intentionally do not run acquisition; this observation alone does not diagnose why the original worker stopped.
- Read-only census and the actual browser artifacts are in [academic-freeze-audit evidence](evidence/news-intelligence/academic-freeze-audit-2026-10-18/inventory.json).

## All 11 workstreams, classified against the requested criteria

`SKIP` means no further development for this release. `OPTIONAL` means useful expansion, not a reason to hold the current core feature open. `IMPLEMENT NOW` is reserved for a concrete defect or essential demo-risk closure.

### 1. Source contracts and rights — sufficient machinery for the present demo

**Implemented:** `Source` carries fetch/process/store/display/redistribute permissions, review metadata and versions. Document storage/display paths consult permissions; evidence quotations can be withheld while links remain. Retention removes text with an auditable redaction record, and the worker invokes it. See [model.py](../seraph/news/model.py), [enrichment.py](../seraph/news/enrichment.py), [apply_retention](../seraph/news/acquisition.py), [news_view.py](../seraph/dashboard/news_view.py).

**Remaining:** per-source rights review is incomplete; declarations are not proof of blanket permission, and complete enforcement for every possible use/deployment is not certified. Redistribution controls matter if exports are added.

**Classification/impact:** mostly source governance and deployment hardening for this local demo. Keeping conservative withholding and source links does not prevent the core feature from working. Unsupported permission claims would damage credibility; lack of a commercial rights-management subsystem would not.

**Verdict: SKIP further machinery.** Review the few sources actually quoted or distributed in the presentation. Do not add licensed full text or exports without checking their terms.

### 2. Document depth and provenance — working extraction, shallow acquired coverage

**Implemented:** bounded HTML/plain/PDF text extraction; persistent document reuse; fair outstanding-document scheduling; hashes, scopes and evidence spans; explicit unavailable/partial states. [enrichment.py](../seraph/news/enrichment.py), [pdf_text.py](../seraph/news/pdf_text.py), [news_view.py](../seraph/dashboard/news_view.py).

**Remaining:** most stored versions lack bodies, and summaries are not full instruments. General annex/table reasoning and OCR are not complete. This is a real coverage/interpretation limitation, not a micro-optimization.

**Classification/impact:** meaningful capability expansion. A title cannot establish every exception, product scope or rate change. This limits analytical depth and explains some unavailable scenarios, but does not invalidate correctly labelled title-level facts and qualitative watch items.

**Verdict: OPTIONAL targeted enrichment; SKIP a general OCR/table platform now.** If presenting quantitative tariff arithmetic, obtain a permitted real instrument with the required inputs and trace its output. Otherwise explicitly present qualitative mechanisms and show the unavailable reasons. Do not claim exhaustive document comprehension.

### 3. Source breadth — multi-source core is implemented

**Implemented:** RSS/JSON/selected-document acquisition, source health, poll policy, conditional requests, registration reconciliation and source-dependent backfill. [run_news.py](../scripts/run_news.py), [http_feed.py](../seraph/news/http_feed.py), [json_feed.py](../seraph/news/json_feed.py), [backfill.py](../seraph/news/backfill.py).

**Remaining:** DGFT/CBIC and several sector/weather/energy/pharma/foreign channels are incomplete. Independent journalism is not broadly covered. Some configured sources are not yet registered; fixed pages do not count as continuous feeds.

**Classification/impact:** meaningful breadth, not a broken existing capability. It matters if you promise universal sector or world-policy coverage. Seventeen endpoints are already enough to demonstrate actual aggregation; adding twenty more does not by itself improve interpretation.

**Verdict: OPTIONAL.** Add only a source that closes a named, demonstrated hole in your selected sectors. **SKIP source-count targets** and universal coverage as a prerequisite to freezing.

### 4. Exposure coverage — real routes work, coverage is concentrated

**Implemented:** cited entity/asset/place/relationship registry, traversal to sectors and holdings, geographic markers/arcs and clickable lineage. Current browser evidence includes foreign-to-India transmission and a domestic asset-linked event. [registry.py](../seraph/news/registry.py), [estimation.py](../seraph/news/estimation.py), [globe_payload.py](../seraph/dashboard/globe_payload.py), [roles.py](../seraph/news/roles.py).

**Remaining:** missing issuer-sector mappings, diversified facilities, verified exact coordinates and financial sizes. Many edges belong to one energy operator. A regional marker is not an exact plant location.

**Classification/impact:** meaningful data capability. Random portfolios will often be uncovered, so a claim of comprehensive portfolio intelligence would be misleading. Explicitly showing an unmapped holding is correct and was browser-verified.

**Verdict: OPTIONAL targeted curation.** Fill mappings for a portfolio or sector you actually promise to support. **SKIP arbitrary edge/facility quotas and monetary sizing now.** The existing qualitative path is demonstrable without them.

### 5. Historical registry coverage — mechanism works, some historical routes are unavailable

**Implemented:** as-of/known-from filtering, strict exclusion of undated records, temporal caveats and a completeness report. [registry.py](../seraph/news/registry.py), [news_view.py](../seraph/dashboard/news_view.py).

**Remaining:** sixteen records have no evidenced curation date; source mappings dependent on them disappear from strict historical views.

**Classification/impact:** retrospective coverage, not a current-news blocker. It matters for a claim that this news engine would have produced a particular past warning. That claim is outside the evidence currently available.

**Verdict: SKIP retrospective completion for this demo.** Preserve honest unknowns and record dates on new curation. Never invent old availability to populate a historical globe.

### 6. Event identity and evidence independence — material old defects repaired

**Implemented:** Unicode-safe grouping, document state transitions including A → B → A, within-document claim reconciliation, corroboration descriptions, cited-instrument linking and stored review decisions. Independent origin is explicitly not verified and repeated reporting does not automatically multiply confirmations. [model.py](../seraph/news/model.py), [acquisition.py](../seraph/news/acquisition.py), [corroboration.py](../seraph/news/corroboration.py), [lifecycle.py](../seraph/news/lifecycle.py).

**Remaining:** a general reviewed event merge/split/reversal interface and independently established publisher sourcing. Similar or translated reports can still require review.

**Classification/impact:** useful editorial capability, but current conservative claims avoid the main credibility failure of pretending copied coverage is independent evidence. No new demo-blocking duplicate was established in this pass.

**Verdict: SKIP general editorial tooling now.** Only reopen if a concrete duplicate or wrong instrument link materially corrupts the chosen demonstration. That is a defect trigger, not an invitation to inspect every theoretical wording.

### 7. Reproducible processing — present-day provenance is implemented

**Implemented:** payload manifest with view/extractor/frame/grouping/estimation identities, source hashes, registry metadata, representation hashes and explicit `provenance: reconstruction`; saved current snapshots. [processing_manifest](../seraph/dashboard/news_view.py), [version_manifest](../seraph/news/registry.py).

**Remaining:** full immutable historic derived revisions and stronger content-addressed registry/configuration replay. The registry manifest includes versions/counts, not a cryptographic identity for every registry row. The labelled processing-age field is not measured end-to-end compute latency.

**Classification/impact:** reproducibility hardening for exact historical claims. It does not stop current acquisition, interpretation or rendering. Do not describe reconstruction using today's rules as the exact output emitted years ago.

**Verdict: SKIP a full event-sourcing/replay platform now.** Save the code version, database copy and example output used in the project report.

### 8. Economic mechanisms and scenarios — qualitative path works; quantitative input coverage is weak

**Implemented:** direction/mechanism/confidence/unknown exposure; opposing beneficiaries and constrained parties; lifecycle/scope restrictions; `institutional_view → _scenario_for → scenario_for → tariff_cost_scenario`, rendered by `scenarioHTML`. [roles.py](../seraph/news/roles.py), [scenarios.py](../seraph/news/scenarios.py), [bridge.js](../seraph/dashboard/console_component/bridge.js).

**Remaining:** broader tariff types, HS/annex applicability, sufficient old/new rates and sized financial exposure. Current real-data view has zero eligible scenarios. Existing code explicitly supplies no financial denominator; this is not a missing display bug.

**Classification/impact:** meaningful depth beyond the qualitative feature. Do not advertise measured losses or validated sector forecasts. The displayed refusal is more credible than a fabricated number.

**Verdict: OPTIONAL one real worked scenario. SKIP a general economic-loss engine now.** If scenario arithmetic is a headline presentation claim, demonstrating one supported real input becomes essential content preparation; it does not justify adding speculative models.

### 9. Role workflows — three functioning projections, advanced actions missing

**Implemented:** retail holdings relevance and unknown mappings; institutional routes/opposing mechanisms/scenario responses; regulator coverage, unresolved links and review information. All three rendered in the current real-browser check. [roles.py](../seraph/news/roles.py), [bridge.js](../seraph/dashboard/console_component/bridge.js).

**Remaining:** professional document comparison, product-country matrix, scenario export, and UI actions to approve/reject instrument links. `record_supersession_review()` exists, but the canonical dashboard has no corresponding mutation operation. Displaying a review queue does not implement a review workflow.

**Classification/impact:** genuinely missing planned features, not just hardening. They matter if the presentation promises an interactive analyst/regulator workspace. They are not required to demonstrate distinct role-based intelligence views, which already work.

**Verdict: OPTIONAL.** Describe the implemented functionality as role projections. If one additional role feature is a formal assessed deliverable, build that exact workflow; do not expand all three roles now. Shared-user authentication belongs to the separate project integration scope, not a prerequisite for a clearly labelled local role demo.

### 10. UI consistency — changed payload works in the browser

**Implemented:** dynamic news connection/freshness/provenance status; formatted retail weights; document-scope/withheld-quotation labels; evidence buttons and original globe layer. [bridge.js](../seraph/dashboard/console_component/bridge.js), [news_view.py](../seraph/dashboard/news_view.py).

**Remaining:** minor presentation polish and verbose regulator/route detail. Some globally worded captions concern only the four dynamic news surfaces while other preview content remains visible and tagged; avoid interpreting them as “no fabricated content anywhere”.

**Classification/impact:** mostly polish. Browser checks found no payload-rendering regression, role-view exception or overlap failure. Screenshot review confirmed the portfolio panel and 66.67% weight rendering.

**Verdict: SKIP further polishing unless a specific screen becomes unusable.** Do not redesign the original globe or replace working panels to increase a completion score.

### 11. Operations at release — one realistic reliability defect remains

**Implemented:** supervised worker, bounded restart, singleton lock, heartbeat, source health, startup/catch-up, manual request queue, retained data and backfill/gap reporting. [run_news.py](../scripts/run_news.py), [news_supervisor.py](../scripts/news_supervisor.py), [launch_prototype.ps1](../launch_prototype.ps1).

**Confirmed remaining defect:** a partial source failure is classified as a failed worker pass. The worker remains alive and would continue polling, but writes heartbeat status `failed`. The supervisor only accepts `running` or `catching_up`; it interprets the heartbeat as a failed process and terminates its own child. If source failure recurs, it can exhaust restarts and stop every healthy feed too.

**Reproduction:** the actual `_run_worker` was driven with one successful feed and one simulated HTTP 503, on disposable SQLite. It emitted `failed / poll failed`. The actual `supervise` function, with simulated still-running child processes presenting that state, terminated three children and gave up after two allowed restarts. No real process was killed and no real publisher outage was induced. [Probe](evidence/news-intelligence/academic-freeze-audit-2026-10-18/partial_failure_probe.py), [result](evidence/news-intelligence/academic-freeze-audit-2026-10-18/partial-failure-result.json).

This does **not** establish that this bug caused today's stale store. It establishes a realistic failure path: public feeds routinely have isolated errors, and the current contracts can turn one into a system-wide acquisition stop.

**Classification/impact:** demo-critical reliability and essential worker/supervisor integration. This is not a theoretical high-scale case.

**Verdict: IMPLEMENT NOW, narrowly.** Separate process liveness/progress from per-source acquisition health. Keep good feeds running and visibly degrade the failed source; reserve restart for process exit, missing heartbeat or exceeded work deadline. Preserve the protection against truly stalled workers. Afterward run one bounded startup/manual-refresh/failure rehearsal. **SKIP** uptime targets, a long prospective reliability campaign, enterprise monitoring and automated disaster recovery for this academic freeze; retain an ordinary safe backup.

## Browser verification actually performed

Ran `scripts/verify_news_browser.py` with its output redirected to a new evidence directory, then `scripts/verify_news_roles_browser.py --output ...`. Both use copies of real local stores, headless Edge, normal Streamlit component interactions and no injected news payload. Production databases were not changed. Their own temporary servers/processes were cleaned up.

| Check | Result |
|---|---|
| Main news payload and original globe | PASS: six markers, one rendered exposure arc |
| Marker evidence interaction | PASS: source and relationship links available |
| Automatic refresh | PASS: decision projection time changed after the normal timer; no `NO RESPONSE` state |
| Institutional, regulator and retail navigation | PASS: each role-specific panel visible; no role projection failure |
| Layout | PASS scripted width/overlap checks; retail screenshot visually inspected |
| Portfolio submission through ordinary tools | PASS: TATASTEEL mapped, unknown holding explicitly unmapped, weight labelled “not loss” |
| Newly connected scenarios | Renderer accepted unavailable/scenario responses; real current data yielded zero priceable scenarios, so a successful numerical scenario was not browser-verified |
| Live acquisition | NOT EXERCISED by these browser scripts; they do not start the worker or fetch new publisher data |

Artifacts: [ordinary browser result](evidence/news-intelligence/academic-freeze-audit-2026-10-18/browser/ordinary-flow.json), [role result](evidence/news-intelligence/academic-freeze-audit-2026-10-18/roles/result.json), [retail screenshot](evidence/news-intelligence/academic-freeze-audit-2026-10-18/roles/retail.png), [execution summary](evidence/news-intelligence/academic-freeze-audit-2026-10-18/browser-summary.json).

**Nothing in the exercised UI flow broke because of the changed payload.** This is bounded evidence, not a claim that every route, manual-acquisition outcome, numerical scenario or historical mode was exercised. The separate supervisor defect was found by examining the integration and reproducing it, not by pretending the browser tested acquisition.

## Minimum essential work and a finite stopping rule

1. **One code repair:** separate degraded source acquisition from worker liveness in the normal loop/supervisor contract. One focused regression must show that a failing source cannot terminate healthy acquisition; retain a check that a genuinely hung worker is restarted.
2. **One bounded operational rehearsal:** start using the normal launcher, verify registration reconciliation and current heartbeat, let two polling passes complete, invoke manual refresh once, and verify fetched/unchanged/failed outcomes are truthful. New stories are not required if a publisher has none. Demonstrate an individual source failure without stopping good feeds. Repair only an observed failure of this journey.
3. **A fixed demonstration, not more development:** use a few cited examples for news → interpretation → sector/holding → globe/evidence, including the existing foreign-to-India route, a domestic asset example and an unmapped holding. Read the original evidence and verify that the displayed assertion/scope/direction does not contradict it. Explicitly identify historical fixed documents and qualitative hypotheses. Keep a labelled cached fallback for internet failure; never relabel it live.

**Stop when those checks pass.** Do not reopen news work for counts, generic refactoring, additional feeds, speculative edge cases or the unpassed full independent benchmark. Reopen only for an observed material error in a supported path or an explicitly required missing deliverable.

The original independent 600-document/150-impact-case and prospective gates remain unpassed; no thresholds are relaxed and no accuracy percentage should be advertised. A small example check supports a demonstration, not general interpretation accuracy. Their absence limits empirical claims, not the right to freeze working prototype software.

## Answers to the five decisions

1. **What does 65% mean?** There is no defensible weighted denominator to convert into missing core functionality. Current evidence supports a working core with broad-scope data/workflow and validation gaps, plus one demonstrated reliability repair. It is misleading to treat the remaining 35% as either all critical code or all harmless hardening.
2. **Important planned features still missing?** Yes: deeper document/table interpretation and balanced coverage, advanced professional comparison/matrix/export and interactive regulator review. Numerical impact scenarios are wired but not demonstrated on adequate current inputs. These are real limitations; they are optional for the stated qualitative core freeze, not magically completed.
3. **Which work meets IMPLEMENT NOW?** Workstream 11's partial-outage/supervisor contract and its bounded operational rehearsal. No blanket redevelopment of the other ten is justified by this audit. Their optional additions become required only if specifically promised in the assessed deliverable.
4. **Minimum work?** One narrowly scoped reliability fix, one operational rehearsal, and honest preparation of the existing evidence-linked examples.
5. **Can development be frozen?** **Yes after that closure; not an unconditional live-demo sign-off today.** You can move attention to the rest of SERAPH now while reserving this small final task. Do not spend the next development cycle trying to make the news backlog read 100%.
