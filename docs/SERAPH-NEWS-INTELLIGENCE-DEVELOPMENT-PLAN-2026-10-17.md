# SERAPH news intelligence: implementation audit and development specification

Date: 17 October 2026. Scope: external news, policies, economic events, India exposure, sector interpretation and the original globe. This is a feature-specific plan for the next development session, not a claim that the feature has been implemented or validated.

## 1. Decision and present state

Keep the existing acquisition and rendering foundation, but correct the event semantics before scaling it. Three connected RBI feeds are a useful integration demonstration; they are not a broad economic intelligence service. The largest missing capability is not an RSS reader. It is the chain from a precisely described change, through a documented exposure, to a target-specific economic consequence with justified uncertainty.

Recommended implementation: a hybrid, evidence-grounded event engine. Use deterministic adapters for official documents; structured extraction with explicit negation, action and legal status; optional NLP/LLM assistance behind validators; a versioned exposure graph; mechanism-specific impact scenarios; and prospective evaluation. Do not substitute a financial sentiment classifier for economic impact reasoning.

Preserve Hawkes, RMT and Hamilton and their ordering. News remains the separate F2 channel. No new news score enters CSRS, fusion weights or the preregistered predictive experiment through this feature plan. A later experiment can test incremental news features under a separately documented, frozen protocol.

### What was actually inspected

Read the current news modules, dashboard projection and globe adapters, run script, curated registries, source-probe evidence, T13 evidence report, and saved browser screenshot. Opened the persisted SQLite database read-only. Ran focused news/globe tests and direct semantic counterexamples. Researched official source directories, APIs, terms and library documentation. Application code and the live database were not edited.

Evidence companion: `NEWS-FEATURE-AUDIT-EVIDENCE-2026-10-17.json`. The audit driver is `news_feature_audit.py`. It reads the default `prototype_runs/news.sqlite`; other separately configured stores are outside this census. No full-project suite or market-model refit was rerun. Existing T07 work is explicitly outside this audit's implementation scope.

### Verified source and data inventory

| Item | Current evidence |
|---|---|
| Registered feeds in the default database | **3** |
| Distinct publishers/providers | **1: Reserve Bank of India** |
| Feed IDs | `rbi_press_releases`, `rbi_notifications`, `rbi_speeches` |
| Stored stories | **30: 10 from each feed** |
| Stories with stored article bodies | **0 of 30** |
| Story first-seen range | 2026-10-16 19:38:37–19:38:38 IST |
| Last successful acquisition recorded for each feed | 2026-10-16 19:38:47 IST |
| Curated entities / places / assets / exposure edges | **1 / 3 / 0 / 0** |
| Curated source-place rows | 3, all mapping RBI feeds to Mumbai |
| Actual foreign-policy/exposure paths | None in this registry |
| Economic news publishers such as ET, Mint, Reuters | None registered |
| Connected independent sector publishers | None |

The database shows a successful acquisition snapshot, not evidence of an uninterrupted polling service since then. Count feeds, publishers, reporting origins and sectors separately; three feeds from one institution must never become “three independent sources.”

### Why more sources are not currently used

`scripts/run_news.py` hardcodes the three RBI feeds as its verified source list. The saved probe investigated only five endpoints: these three feeds, one PIB feed, and the RBI RSS index page. This was a small integration exercise, not a comprehensive source search.

PIB returned HTTP 200 and 20 parsed items, but zero usable publication timestamps. The evidence JSON is inconsistent: its PIB row says `usable: true`, while the top-level usable list excludes PIB and its note defines usability as requiring dates. Resolve that reporting defect. Missing publication dates need a conservative first-seen policy and, where permitted, a detail-page date parser; they do not inherently make current monitoring impossible. The probe's sample was Hindi despite the source configuration assumptions, so language must be detected per document.

RBI's RSS index returned HTML rather than a feed. That is an adapter/endpoint mismatch, not a reason to conclude other publishers are inaccessible. There is no evidence here that SEBI, exchange filings, customs, foreign policy or sector agencies were systematically rejected after evaluation.

## 2. Audit of the globe claim

### What should be credited

- Real stored RBI stories flow through news projection to the original globe renderer.
- The documented India/Mumbai nodes have curated coordinates rather than random geography.
- Source and publication timing are exposed in detail; fabricated and connected layers have different styling.
- The fixes to partial entity matching, place labels and conservative location mentions are meaningful improvements.
- Empty exposure paths are reported honestly. No exposure should be invented just to populate the UI.

### What remains unproven or misleading

1. **Renderer demonstration versus normal live delivery.** T13's own evidence says the component was supplied a real payload evaluated at 2026-10-18. The saved screenshot still shows the selected historical decision as 2020-04-30 while displaying 2026 headlines. This is understandable as a controlled renderer demonstration, but it cannot count as a consistent production screen or a leakage-free historical replay. The ordinary projection uses the selected run's evaluation timestamp. Require a real current context or a separately labelled current-news mode, and bind the browser header and payload to the same context.
2. **Issuing office versus event origin.** `news_view.news_channel()` treats a source's issuing location as the event origin. A cited RBI Mumbai address supports issuer provenance. It does not establish that every policy, reported incident, speech or affected activity originated physically in Mumbai. Add distinct roles: publisher office, issuing authority jurisdiction, event occurrence, affected geography and mere mention. A Reuters London office must never become the origin of a Chinese export restriction.
3. **Two nodes are not two independent events or two affected areas.** A country centroid, issuer office and mentioned city represent different facts. Counts and tooltips must identify what is counted.
4. **Domestic facility and foreign transmission acceptance remain incomplete.** There are zero assets and zero edges. Test fixtures demonstrate renderer properties, not documented Indian supply-chain exposure.
5. **A documented relationship is not an observed loss.** An exposure arc may be observed as a relationship while its event-specific consequence is derived. Give the relationship and impact separate provenance/status fields.

The original fabricated layer can remain, as requested. It must retain its FABRICATED tag and never participate in real counts, ranking, portfolio calculations or alerts.

## 3. Interpretation and engineering findings

### Tests run for this audit

- `test_news_pipeline.py`, `test_news06_overlays.py`, `test_t13_globe_payload.py`: initially 94 passed and one Windows sandbox temporary-directory cleanup failure. The failed test passed on an isolated rerun with TEMP/TMP redirected to the writable workspace. Thus all **95 unique tests** passed across those executions.
- `test_t13_origin_and_resolution.py`: **17 passed**.
- `tests/js/news_layer_harness.mjs`: **27 checks passed**.
- Total: **112 unique targeted Python tests passed**, plus 27 JS checks. This does not independently confirm the reported 1,107-test full suite.
- Ten synthetic counterexamples exercised the actual extractor and direction/severity helpers. These are deliberate falsification examples, not a representative accuracy benchmark. Inputs and outputs are recorded in the companion JSON.

### Reproduced semantic defects

| Input | Current output | Required behavior |
|---|---|---|
| RBI cuts repo rate by 25 basis points | Adverse; no extracted quantity | Parse −25 bps; effects depend on borrower, lender, depositor and expectations |
| RBI holds repo rate unchanged | Adverse | Unchanged decision; surprise unknown unless an eligible expectation exists |
| Government withdraws subsidy for solar manufacturers | Favourable | Withdrawal; beneficiary cost/revenue mechanism must be evaluated |
| Factory denies reports of production halt | Active, major adverse halt | Denied allegation, not a confirmed operational halt |
| Government proposes 50% tariff; consultation opens | Active tariff event; legal stage absent | Proposed measure with unknown enactment and effective date |
| Import duty cut from 50% to 5% | Severe adverse; both levels used for escalation | Old 50%, new 5%, change −45 percentage points; target-specific effect |
| Port publishes annual report | Moderate adverse logistics disruption | Routine report; no disruption established |
| Company cancels new plant expansion | Favourable expansion | Cancelled investment/expansion, not added capacity |
| Weekly Statistical Supplement | Adverse | Publication only; economic surprise requires actual data and reference |
| Speech by Governor on financial inclusion | Adverse | Communication; no automatic economic sign |

Calling `direction_of()` on each of the 30 stored-story extractions returned **adverse for all 30**, including ten speeches and two statistical releases. This is evidence of a category-default rule, not an economic assessment of those documents. Some events may generate no downstream impact because they lack affected targets; this result must not be described as 30 rendered adverse alerts.

### Prioritized defect register

| ID / priority | Finding and consequence | Affected implementation | Required closure |
|---|---|---|---|
| N01 / P0 | Direction is global per category, so subsidy withdrawal and rate cuts are mishandled | `extraction.py`, `estimation.py`, `model.py` | Action/status/target-specific rules; unknown sign when unsupported |
| N02 / P0 | Keywords create events from negations, proposals, cancelled projects and routine reports | `extraction.py` | Clause-level assertions, modality and negation; separate reporting from occurrence |
| N03 / P0 | Percentage levels are not signed changes; bps absent; historical rates escalate severity | `extraction.py`, `severity_of` | Typed quantities, old/new/delta, scope, unit and evidence |
| N04 / P0 | `Event.confirmations` counts distinct story IDs despite its independence docstring | `model.py`, confidence logic | Reporting-lineage grouping; copies never raise confidence |
| N05 / P0 | A single story with a high-confidence path still yields `high`, contrary to the confidence helper's docstring | `evidence_confidence_of` | Separate authority/extraction/link evidence; clarify policy and calibrate only with labels |
| N06 / P0 | `occurred_at` is filled with `published_at` without occurrence evidence | `extract` | Unknown occurrence stays null; distinguish announcement, enactment and effect |
| N07 / P0 | Mere entity mentions still enter `affected`; the location fix did not establish semantic roles for organizations | `extract` | Issuer, subject, beneficiary, constrained party, quoted speaker and mention roles |
| N08 / P0 | Source office is labelled event origin | `news_view.py`, `globe_payload.py`, `source_places.csv` | Role-aware geography; no source-office-to-affected shortcut |
| N09 / P0 before scaling | Aggregation sums magnitudes across events and takes the first unit | `aggregate_by` | Group by measure/unit/denominator; union exposure, no duplicate holdings or mixed units |
| N10 / P0 for replay | Exposure edges have valid dates but no required system knowledge/version dates | `ExposureEdge`, registry loader | Bitemporal edges and as-of joins; later curation cannot silently improve earlier replay |
| N11 / P1 | `coverage_at()` reads the latest mutable health row, not health history as of the selected time | `acquisition.py` | Immutable health observations and historical as-of query |
| N12 / P1 | Stories are ordered oldest-first; channel truncates `events[:40]` before signals sort | `acquisition.py`, `news_view.py` | Sort/filter before pagination; paginate event details; do not drop the newest event |
| N13 / P1 | All sources polled each default five-minute cycle, ignoring configured 30/60/240-minute cadences | `run_news.py`, `http_feed.py` | Persist per-source due time; host budget and retries; conditional validators survive restart |
| N14 / P1 | Job callback returns normal totals even when source ingest reports fail | `run_news.py` | Failed/partial-success outcome with explicit failed sources; no healthy-job illusion |
| N15 / P1 | Thirty headline-only stories cannot support detailed quantity/causal claims | rights policy, adapters | Permitted official detail/PDF acquisition; otherwise headline-only and abstention |
| N16 / P1 | No real assets or exposure edges; origin dots cannot fill transmission placeholders | curated master data | Cited, time-aware pilot registry and structural trade datasets |
| N17 / P1 | Story-token/day hash is crude syndication and event identity; stable cross-source lifecycle is incomplete | `syndication_key`, `extract`, store | Separate document copies, event identity and event revisions |
| N18 / P1 | Graph traversal compares node IDs with edge-ID tuples for cycle checking; improved paths are not re-enqueued | `reachable` | Explicit visited-node state and deterministic relaxation; cycle/diamond/order tests |
| N19 / P1 | Coverage denominator is only registered feeds | `coverage_at`, dashboard | Intended sector/topic/jurisdiction/language coverage and exposure denominators |
| N20 / P1 | Multi-event documents are forced into first matching category | `EVENT_PATTERNS`, `extract` | One document may emit several evidenced event frames |
| N21 / P1 | Saved browser context can disagree with supplied payload | console transport/header | Reject context mismatch; show news clock and market clock explicitly |

N09–N14 and N18–N20 are code-inspection findings; they were not all executed as new adversarial tests. This distinction matters. Existing depth limits bound graph traversal, but they do not make its cycle or best-path logic correct. Current zero-edge data means some graph defects are dormant, not absent.

## 4. Source coverage programme

### Registration policy

Use four separate states: `discovered`, `documentation_checked`, `adapter_verified`, `enabled`. Rights and freshness are separate dimensions. An official documentation page or search result is not proof that its feed can be ingested here. Except for the current RBI database evidence, the following are **proposed integrations**, not newly connected sources. No paid account or subscription is assumed.

Wave 1: repair RBI semantics and add PIB, SEBI, exchange announcements, DGFT/CBIC, Federal Register/USTR, Fed and one independently licensed economic reporting provider. Wave 2: detailed Indian sector, Chinese/EU policy and physical hazards. Wave 3: additional countries, regional languages and richer company exposure. In parallel only at the conceptual level, build the structural exposure datasets: news without those cannot produce defensible Indian transmission paths.

The catalogue below contains **48 source families**, not 48 verified feeds. Family members may have common ownership or repeat the same announcement. Entries labelled “discovery” need exact endpoint, terms and access work before development promises can be made. “Docs checked” means official content/directory was consulted during this audit; it does not mean local adapter or rights approval.

### A. Indian policy, companies and sector sources

| # | Source family / official discovery reference | State / wave | Capture and intended use |
|---|---|---|---|
| 1 | RBI: current three feeds in `run_news.py` | Connected / 1 | Monetary decisions, liquidity, regulation; link official details and distinguish speeches/statistics |
| 2 | [PIB RSS directory](https://www.pib.gov.in/ViewRss.aspx?lang=1&reg=1) | Docs checked, existing partial probe / 1 | Ministry-tagged announcements; repair dates/language; deduplicate announcements repeated by departments |
| 3 | [SEBI RSS](https://www.sebi.gov.in/rss.html) | Docs checked / 1 | Circulars, orders and market regulation; feed published as `https://www.sebi.gov.in/sebirss.xml` |
| 4 | [NSE RSS directory](https://www.nseindia.com/static/rss-feed) | Docs checked / 1 | Corporate announcements, annual reports and circulars; retrieve actual feed links from directory, never guess API paths |
| 5 | BSE corporate disclosures, [BSE](https://www.bseindia.com/) | Discovery / 1 | Complement NSE; deduplicate the same issuer filing across exchanges by document identity |
| 6 | DGFT, with official [APEDA DGFT-notification listing](https://apeda.gov.in/dgft-notifications) | Listing checked / 1 | Export/import restrictions, quotas, product codes, validity changes; canonical DGFT/Gazette instrument is final authority |
| 7 | [CBIC Tax Information Portal](https://taxinformation.cbic.gov.in/) | Docs checked / 1 | Customs/GST notifications, exemptions, amended schedules; HTML/PDF adapter rather than assumed RSS |
| 8 | [DGTR trade notices](https://www.dgtr.gov.in/en/trade-notices) | Listing checked / 2 | Investigations, findings, anti-dumping/safeguards; recommendation differs from imposed duty |
| 9 | [Gazette of India](https://egazette.gov.in/) | Discovery / 1 | Canonical legal notifications; publication, instrument and amendment identity |
| 10 | [MoSPI](https://www.mospi.gov.in/) | Discovery / 2 | CPI, IIP, GDP and release calendars; distinguish reference period, release and revision |
| 11 | Finance Ministry / Budget / GST Council, [Finance Ministry](https://finmin.gov.in/) | Discovery / 2 | Fiscal measures and implementation; council recommendation alone is not an effective tax change |
| 12 | [PPAC](https://ppac.gov.in/) / MoPNG | Docs checked for PPAC / 2 | Petroleum consumption, crude basket and gas-price notices; units and preliminary/revised status |
| 13 | [CEA generation and outage reports](https://cea.nic.in/reports/external/daily-generation?lang=en) / Grid India | CEA checked, Grid India discovery / 2 | Unit-level generation/outages and coal stress; scheduled maintenance differs from unplanned outage |
| 14 | MNRE / Ministry of Power / CERC, [MNRE](https://mnre.gov.in/) | Discovery / 2 | Renewables incentives, procurement, tariffs, transmission and grid regulation |
| 15 | Steel / Mines / Coal ministries, [Steel Ministry](https://steel.gov.in/) | Discovery / 2 | Production, mining leases, duties, mineral supply; route ministry PIB notices immediately |
| 16 | Agriculture / food / APEDA, [APEDA](https://apeda.gov.in/) | Discovery beyond DGFT listing / 2 | Crop estimates, food trade, procurement, export conditions and quality restrictions |
| 17 | [IMD API reference](https://api.imd.gov.in/public/api_reference.html) | Docs checked / 2 | District warnings, rainfall and port warnings; retain forecast issuance and validity, not just place names |
| 18 | Shipping / port authorities / railways / civil aviation, [Shipping Ministry](https://shipmin.gov.in/) | Discovery / 2 | Port closure, terminal, route and transport constraints; first-party notices for actual operation status |
| 19 | MeitY / DoT / TRAI, [TRAI](https://www.trai.gov.in/) | Discovery / 2 | Telecom regulation, spectrum, electronics programmes, digital and import policy |
| 20 | CDSCO / Department of Pharmaceuticals / NPPA, [CDSCO](https://cdsco.gov.in/) | Discovery / 2 | Drug restrictions, recalls, approvals and price controls; product/facility scope |
| 21 | CCI / IBBI / IRDAI, [CCI](https://www.cci.gov.in/) | Discovery / 3 | Competition decisions, insolvency and insurance regulation; legal-stage tracking |
| 22 | State government gazettes and disaster/industry departments | Discovery, select pilot states / 3 | Local permits, power rationing, shutdown orders and infrastructure disruption |
| 23 | Company investor-relations pages and filed annual reports | Select pilot issuers / 1–2 | Plant locations, business segments, import dependencies and geographic revenue; permission-aware retrieval |

PIB is the immediate route to ministry breadth; it does not eliminate the need for authoritative legal documents or operational agency notices. CEA provides actual station/unit outage report categories, while PPAC publishes structured energy reports. These are useful operational evidence alongside news, not “news sentiment.”

### B. Foreign policy and cross-border transmission

| # | Source family / reference | State / wave | India relevance and adapter requirement |
|---|---|---|---|
| 24 | [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1) | Docs checked / 1 | US rules, proposed rules and presidential documents; retain document number, agency, dates and official PDF link; API needs no key |
| 25 | [USTR investigations](https://ustr.gov/issue-areas/enforcement/section-301-investigations) / CBP / USITC HTS | USTR checked, others discovery / 1 | Tariff scope, exclusions and implementation; join instrument to country of origin and national tariff line |
| 26 | [BIS Federal Register notices](https://www.bis.gov/regulations/federal-register-notices) | Docs checked / 2 | Export controls, restricted equipment/technology and end users; critical inputs and electronics |
| 27 | [OFAC recent actions](https://ofac.treasury.gov/recent-actions) | Page checked / 2 | Sanctions, licences and delistings; banking, oil, shipping counterparties; name-match candidates require identity review |
| 28 | [Federal Reserve feeds](https://www.federalreserve.gov/feeds/feeds.htm) | Docs checked / 1 | Monetary decisions, liquidity and banking; separate speech/decision/data and expectation surprises |
| 29 | [ECB feeds](https://www.ecb.europa.eu/home/html/rss.en.html) | Docs checked / 2 | Euro funding and demand context; no blanket adverse tag |
| 30 | EU EUR-Lex / DG Trade / TARIC / [CBAM guidance](https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism/cbam-legislation-and-guidance_en) | CBAM checked, other adapters discovery / 2 | Trade remedies, regulation, carbon compliance; inspect current instruments and exemptions, never hardcode a headline rate |
| 31 | UK DBT / HMRC / Trade Remedies Authority, [UK government](https://www.gov.uk/government/organisations/department-for-business-and-trade) | Discovery; tariff portal fetch failed in web tool / 3 | UK duties, product regulation and restrictions; document source and tariff API feasibility separately |
| 32 | [China MOFCOM announcements](https://english.mofcom.gov.cn/Policies/AnnouncementsOrders/index.html) / GACC | MOFCOM checked, GACC discovery / 2 | Critical minerals, export licensing and trade restrictions; original-language text plus translated representation |
| 33 | Japan METI / Korea MOTIE / Taiwan economic authorities | Discovery / 3 | Semiconductor/electronics supply and export rules; prioritize by observed Indian dependencies |
| 34 | OPEC and major oil-producer official statements | Discovery / 2 | Production announcements and actual implementation; output target does not equal realized supply |
| 35 | [WTO API catalogue](https://apiportal.wto.org/apis) | Docs checked / 2 | ePing SPS/TBT and quantitative-restriction notifications; member notification delays preclude assuming breaking-news coverage |

FederalRegister.gov's API rendition is an informational resource; its own documentation directs legal reliance to the official edition/PDF. Preserve that source chain. WTO QR has product/HS detail and historical notifications, but is not a substitute for immediate national announcements. China English pages may lag the original; both versions need independent first-seen and translation metadata.

### C. Discovery, economic journalism and physical hazards

| # | Source family / reference | State / wave | Use and limitations |
|---|---|---|---|
| 36 | [GDELT DOC](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | Documentation checked / 2 | Broad multilingual discovery, queries by sectors/products/places; validate current limits and availability; linked publisher remains evidence authority |
| 37 | [Economic Times RSS](https://economictimes.indiatimes.com/rss.cms), including relevant sector editions | Docs/terms checked / licensed lane | Excellent candidate breadth; published RSS terms restrict aggregation/reuse. Do not equate a public feed with permission for the intended product |
| 38 | [Mint RSS](https://www.livemint.com/rss) | Docs/terms checked / licensed lane | Industry, companies, policy, markets; listed terms limit personal noncommercial newsreader use; obtain suitable rights before wider ingestion/display |
| 39 | [Business Standard RSS directory](https://www.business-standard.com/rss-feeds/listing) | Directory checked / licensed lane | Economy, industry and policy; endpoint and rights validation still required |
| 40 | Hindu BusinessLine / PTI / other Indian business or regional reporting | Discovery / licensed lane | Local industrial, commodity and regional coverage; verify supplier, wire provenance and licence |
| 41 | [Reuters API/services](https://reutersagency.com/) | Service documentation checked / licensed option | International economics, trade, companies; commercial integration and usage rights required; no subscription assumed |
| 42 | [WHO Disease Outbreak News](https://www.who.int/emergencies/disease-outbreak-news) | Page checked / 2 | Health hazards and dated updates; external warning evidence, not proof pillars predicted a pandemic |
| 43 | [USGS GeoJSON feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php) | Docs checked / 2 | Event location/magnitude and updates; proximity is potential exposure, not confirmed facility damage |
| 44 | [ReliefWeb API](https://apidoc.reliefweb.int/) | Docs checked / 3 | Disaster/conflict reports with original reporting organizations; satisfy current app/access requirements; deduplicate underlying reports |
| 45 | [openFDA APIs](https://open.fda.gov/apis/) and FDA regulatory notices | API landing checked / 2 | Drug recalls and related evidence; API datasets do not represent every import alert or warning letter |

Do not make consumer-media licensing a reason to postpone all progress: official sources, company disclosures and appropriately licensed reporting can be developed as separate adapter lanes. GDELT indexing does not grant rights to republish publishers' full text or bypass subscriptions.

### D. Structural exposure data, not news feeds

| # | Source family / reference | State / wave | Intended use |
|---|---|---|---|
| 46 | UN Comtrade / Indian official merchandise trade, [UN API catalogue](https://unstats.un.org/unsd/api/) | Catalogue checked; current Comtrade access migration needs verification / 1–2 | Country-product imports/exports, concentration and affected trade values; record release vintage and reporting gaps |
| 47 | [OECD input-output / ICIO](https://www.oecd.org/en/data/datasets/input-output-tables.html) | Docs checked / 2–3 | Country-sector production links; aggregate scenario model only, not firm-specific supply proof |
| 48 | [EIA API v2](https://www.eia.gov/opendata/documentation.php) | Docs checked / 2 | Energy price/stock/output context; free API key required, release cadence and revisions retained |

These datasets enable transmission reasoning. A tariff story mentioning India cannot identify exposed listed companies without a separate product/segment/revenue mapping. National trade shares cannot be silently assigned to every company in a sector.

### Sector coverage acceptance matrix

For each row require at least an authoritative policy route, an operational/company route, a structural exposure route and a tested event mechanism. Broad journalism is additional coverage, not a replacement for these.

| Sector | Initial sources | Mechanisms to implement | Missing information that must remain explicit |
|---|---|---|---|
| Banking/NBFC/insurance | RBI, SEBI, IRDAI, filings, Fed | Funding cost, liquidity, capital, credit exposure | Repricing gaps, maturity profile, issuer balance sheet |
| IT/services | Filings, trade/visa authorities, MeitY, foreign policy | Client geography, procurement, visa/compliance, FX | Segment revenue, currency hedges, actual contract exposure |
| Pharma/health | CDSCO, FDA, filings, WHO, trade | Facility/product restriction, API dependence, demand | Product IDs, facility match, affected revenue |
| Auto/components | Filings, trade, ministries, China policy | Input tariffs, rare-earth supply, demand, incentives | Product mix, bill of materials, inventory cover |
| Steel/metals/mining | Steel/Mines, DGTR/CBIC, EU/US trade, filings | Duties, carbon cost, input supply, export markets | HS/CN scope, emissions, customer geography |
| Oil/gas/petrochemicals | PPAC, MoPNG, EIA, OPEC, sanctions, filings | Input price, refining margin, route/payment access | Import mix, hedges, regulated prices and substitution |
| Power/renewables | CEA, Grid India, MNRE, CERC, IMD | Outages, fuel stocks, grid constraint, subsidy change | Contract pass-through, operating capacity, duration |
| Agriculture/FMCG | Agriculture, APEDA, IMD, trade, filings | Yield/input shock, export restriction, food costs | Crop-region weights, stock/inventory, retail pass-through |
| Logistics/aviation/shipping | Ports, transport agencies, IMD, sanctions | Route closure, delays, fuel cost, capacity | Actual route usage, alternatives, insured/hedged cost |
| Electronics/telecom | MeitY, TRAI/DoT, BIS, China, filings | Export controls, equipment supply, spectrum/regulation | Product/end-use scope, vendor exposure |
| Chemicals/fertilizer/cement | Ministries, customs, energy, EU, filings | Feedstock cost, environment, subsidies, duties | Input/output proportions, plant and product coverage |
| Textiles/gems/discretionary | Trade, foreign duties, filings, business reporting | Export demand, tariff, FX and inventory | Country-product revenue and buyer concentration |
| Infrastructure/real estate | Budget, state notices, CEA, filings | Project approvals, financing and material costs | Site/project IDs, financing terms, actual execution |

Do not promise a complete global source list. This is a prioritized acquisition backlog whose coverage is measured against the declared universe, and expanded when gaps are demonstrated.

## 5. Target architecture and contracts

Keep a single-node service and the existing repository stack. No Kafka, Airflow, new graph database or GPU requirement is justified by thirty documents. Use PostgreSQL via the established store interfaces when the shared durable-store work is ready; use an explicit SQLite adapter for the prototype until then. T07 owns generic store/session durability: reconcile its current schema before adding migrations.

```text
Source registry + schedules + rights
  -> adapter fetch -> immutable observation + acquisition health
  -> versioned document representation + publication-time evidence
  -> duplicate/copy lineage -> event frame extraction
  -> assertion validators + entity/location/product resolution
  -> event revisions + policy state machine
  -> point-in-time exposure join -> mechanism-specific impact hypotheses
  -> evidence-backed news read model -> original globe / sector / role views
```

### SourceConfigV2

Add `publisher_id`, `reporting_origin_group`, `adapter_kind`, `endpoint`, `discovery_url`, `jurisdictions`, `topics`, `languages`, `schedule`, `pagination`, `backfill_policy`, `terms_url`, `rights_reviewed_at`, `permitted_uses`, `retention_policy`, `enabled`, `parser_version`, `last_adapter_verification`.

`permitted_uses` separates fetching, transient processing, body storage, snippet display, redistribution, embeddings and model training. A boolean `may_store_full_text` is too coarse. Preserve old fields through a migration adapter; an existing `accessibility_verified` flag must not silently approve all uses. Unknown rights mean the capability is unavailable until reviewed, not fabricated text.

Adapter signature: `fetch(source_config, cursor, conditional_headers, now) -> Result[FetchBatch]`. Batch contains observations, next cursor, HTTP metadata, truncation/gaps and retry guidance. Parsing must not advance the durable cursor until observations and checkpoints commit together. Emit `success`, `partial`, `failed`, `not_modified`, and `disabled` distinctly.

### Documents and evidence

Use stable `document_id = hash(publisher_id, canonical_external_id)` and immutable `document_version_id = hash(document_id, content_hash)`. Normalize tracking parameters only through publisher-specific rules; never strip meaningful query identifiers. Store `retrieved_at`, `published_at`, `publication_precision`, original timezone, MIME type, source URL, content hash, rights, parser version, and language. Preserve permitted raw input or a restricted metadata/hash record.

An `EvidenceSpanV2` references document version, representation hash, page/section/table cell, start/end offsets and exact permitted excerpt. HTML cleanup, redaction and translation produce new representations with offsets mapped to original text. Do not cite normalized offsets as raw-byte offsets. PDF table provenance must retain row/column headings and units.

### EventFrameV2: extract claims, not conclusions

Required: `event_id`, immutable `revision_id`, `event_type`, `assertion_status`, `action`, `actors`, `subjects`, `beneficiaries`, `constrained_parties`, `mentioned_entities`, `products`, `locations`, `quantities`, `evidence`, `unknowns`, `extraction_method`, `model/prompt/schema versions`.

- Assertion status: `confirmed_statement`, `reported_unconfirmed`, `denied`, `hypothetical`, `disputed`. This describes evidence, not market outcome.
- Action: increase/decrease/unchanged/start/stop/resume/withdraw/extend/cancel/announce, as applicable. Unknown is valid.
- Policy status separately: proposed/consultation/announced/adopted/effective/suspended/expired/repealed/unknown. Do not overload event lifecycle with legal status.
- Quantities: measure, old level, new level, signed delta, unit, denominator, product/target scope, date interval and supporting spans. Decimal arithmetic for legal rates/currency; bps and percentage points differ from percent relative change.
- Locations: `publisher_office`, `issuer_jurisdiction`, `occurrence`, `affected`, `mentioned`, `route_segment`. Include resolution status, precision, source, confidence basis and validity. Country centroid is a display coordinate, never a precise incident location.
- Times: published, first_seen, occurred, announced, adopted, effective, expired/resolved and system revision time. Unknown stays null. An expected future effective date is an assertion known now, not an event observed in the future.

Each event version must be available only after all required observations and processing completed. In live operation `available_at = max(required first_seen times, extraction completion, required registry-version availability)`. Persist processing latency. Historical source-availability studies must be a separate mode and cannot rewrite operational first_seen timestamps.

### Event identity and lifecycle

Document duplication, syndication, same-event clustering and event revision are four different relations. Keep them separate. Use exact official instrument IDs first, canonical URLs/content hashes next, then candidate similarity constrained by actors, product, action and time. Embeddings can retrieve candidates; they do not determine final identity alone. A proposed duty and its final enactment may belong to one policy family but are distinct revisions/stages.

Keep `reporting_origin_id` for original wire/agency/document. Ten copies of one wire count once. Two independent reports increase corroboration only if their claims actually agree. An official circular can be authoritative with one origin; the system should state that, rather than pretending it has multiple confirmations. Persist merge/split decisions and allow their reversal without rewriting history.

### ExposureEdgeV2

Add node types country, region, facility, company, business segment, product, sector and transport corridor. Edge fields: `relation`, `direction`, `measure`, `value_or_interval`, `unit`, `denominator_id`, `scope`, `reference_period`, `valid_from/to`, `known_from/to`, `evidence`, `method`, `review_status`, `registry_version`.

Relations should distinguish exports_to, imports_from, consumes_input, supplies, owns, operates, located_in, financed_by and uses_route. Ownership is not an economic transmission coefficient. Administrative containment is not exposure. Store both link provenance and the source publication date; a 2024 annual-report fact learned in 2026 is not automatically known in a 2024 operational replay.

Pilot scope proposal: 20 listed issuers across five sectors, 20 named facilities, and at least 50 cited relationships. These are development targets, not current counts; prioritize coverage and accuracy over filling quotas. At least one complete foreign-policy-to-Indian-sector path and one real domestic-facility example must be supported end to end. Unsized edges are valid but must not produce loss amounts.

### ImpactHypothesisV2

Key by event revision, target, mechanism and horizon. Fields: `direction` (favourable/adverse/mixed/neutral/unknown), `severity_basis`, `exposure`, `shock`, `scenario_range`, `assumptions`, `unknowns`, `supporting_paths`, `contradictions`, `available_at`, `validity`, `method_version`, `prediction_status`.

Keep source authority, extraction correctness, entity-link certainty, exposure quality and economic-model uncertainty separate. Do not multiply ordinal confidences into a pseudo-probability. A strong document may still support a very uncertain financial consequence.

## 6. Economic reasoning engine

### Deterministic first-stage rules

Run rules on structured frames, not whole-document keyword presence. Each rule declares required fields, applicability, target role, mechanism, formula if any, abstention condition and version. Initial rule families:

1. Policy rates/reserve requirements: compare old/new and, when available, an expectation measured before announcement. Rate cuts can lower borrower costs while compressing some lenders' margins; unknown repricing means unknown net effect.
2. Tariff/import/export restrictions: legal stage, jurisdiction, product and origin matching; separate domestic producer, importer, exporter and downstream consumer effects.
3. Operational incidents: confirmed asset state, capacity share, duration and inventories; distinguish shutdown, maintenance, threatened strike and denial.
4. Subsidies/incentives: new versus withdrawn eligibility, qualifying products/firms, budget and effective period. Announced budget does not equal cash received.
5. Logistics: route usage, closure/delay, alternatives, inventory cover and freight/insurance costs.
6. Sanctions/export controls: affected party/product/end-use, exemptions/licences, payment and supply channel. Do not infer applicability from nationality alone.
7. Macro releases: actual versus previously available expectation, reference period and revision; a data-release headline alone has no signed surprise.
8. Physical hazards/health: hazard footprint and exposure intersection yield a watch, not confirmed operational damage or financial loss.

### Tariff applicability and scenarios

Represent a measure as jurisdiction, legal instrument, issuer, legal stage, product schedule/version, origin, destination, end-use/party qualifiers, old/new rate, specific duty, quota, exemptions, effective interval and evidence. HS6 is international grouping; national 8/10-digit schedules and revision concordances require explicit mapping. Never guess an affected product from a broad sector label alone.

Implementation steps: parse official instrument and annex -> validate rates/products -> resolve effective legal state as of decision -> map covered national tariff lines to versioned HS/product exposure -> check origin/destination/exemptions -> produce beneficiary/adverse hypotheses -> quantify only where the data support it.

For a simple ad-valorem tariff with unchanged tax base and no other changes:

`landed_price_change = (1 + new_rate) / (1 + old_rate) - 1`

Rates are fractions. Moving from 50% to 5% gives `1.05/1.50 - 1 = -30%` in the tariff-inclusive component, not a 45% fall in every final price. The rate change is −45 percentage points. Exchange rates, freight, other taxes, exemptions and margin adjustments may change actual landed cost.

For a documented importer exposure:

`cost_change_scenario = eligible_import_cost_base * landed_price_change * pass_through_fraction`

This is a conditional accounting scenario, not a return forecast. Pass-through is either estimated from eligible historical data or presented as a labelled user/scenario interval. Unknown eligible share means no company-specific monetary result. A rival producer may benefit while downstream customers face higher costs; do not copy a global event sign onto every node.

For exporters, use documented eligible revenue share, buyer-country coverage and scenario price elasticity. For CBAM or specific duties, use the actual legal calculation and required physical/emissions units; the simple ad-valorem formula is inapplicable. Explain missing inputs instead of inventing them.

### Graph propagation and aggregation

Implement bounded traversal with visited node IDs, typed direction and an explicit path state. Enumerate compatible simple paths up to the declared depth; choose or aggregate only under an identified economic model. Re-enqueue improved states when using relaxation. Test invariance to CSV/input order. Preserve discarded alternative paths and exclusion reasons.

Do not multiply arbitrary edge magnitudes: a revenue share times a supplier percentage may have incompatible denominators. Propagation may return a qualitative hypothesis when coefficients are unavailable. Multi-hop magnitude becomes unknown unless a compatible accounting relationship is demonstrated.

Aggregate exposure over a unique target/sub-exposure set, not over story counts. Two events hitting the same 30% export book do not make 60% of the firm exposed. If overlap is unknown, report bounds or separate scenarios. Do not add tonnes, percentage shares, MW, revenue and rupees. Keep favourable and adverse mechanisms visible rather than cancelling them into a falsely precise net score.

### Advanced structural model, after the basic rules

OECD input-output tables describe sector purchase/sales relationships and publish Leontief-inverse material. A fixed-coefficient scenario can use `delta_x = solve(I - A, delta_final_demand)` with documented orientation, units and vintage. This is a demand-driven structural scenario; a supply interruption cannot simply be substituted as a negative final-demand shock and called a forecast. Supply constraints need an explicit capacity/rationing model and separate validation. Check spectral/stability properties and never silently rescale an unstable matrix. [OECD source](https://www.oecd.org/en/data/datasets/input-output-tables.html).

Use broad sector scenarios as priors for investigation, not proof of a named company's supplier. Defer graph neural networks and complex causal discovery until there is a sufficiently large, dated and labelled exposure/event dataset to justify them.

### Attention, significance and freshness

Separate editorial attention from estimated economic severity. Rank eligible events by a published lexicographic policy initially: high-priority unresolved legal/operational changes, relevant documented exposure, legal immediacy, novelty, and freshness. Do not train a weighted severity formula on ten examples.

Novelty is a structured delta against the previous eligible event version: new rate, new country/product scope, changed effective date, new evidence or reversal. Repeated reporting adds visibility, not additional economic shock. Lifecycle controls persistence: an effective restriction remains relevant until superseded/expired; it must not disappear just because the headline is old. A transient unconfirmed story can expire into an explicitly stale watch.

## 7. Extraction technology and implementation choices

| Tool / primary reference | Recommended job | Boundary |
|---|---|---|
| [feedparser](https://github.com/kurtmckee/feedparser) | RSS/Atom formats and metadata handling | Does not solve rights, semantic dates or impact |
| [Trafilatura](https://github.com/adbar/trafilatura) | Permitted HTML body/metadata extraction | Compare against official-page fixtures; no paywall bypass or assumed completeness |
| [spaCy matchers](https://spacy.io/usage/rule-based-matching) | Token/dependency rules, entity dictionaries and relation patterns | Rules must distinguish negation, subjects and scope; English model does not cover every Indian language |
| [GLiNER](https://github.com/urchade/GLiNER) | Optional entity/span candidate extraction for facilities/products/policy instruments | Benchmark pinned CPU model; candidate extraction is not authoritative entity linking or financial reasoning |
| [Sentence Transformers](https://github.com/huggingface/sentence-transformers) | Duplicate/event candidate retrieval and semantic search | Similarity is not confirmation or same legal event; pin model and evaluate multilingual cases |
| [FinBERT](https://huggingface.co/ProsusAI/finbert) | Optional financial tone baseline | Sentiment task; cannot determine tariff applicability, exposure or economic impact |

Use existing PDF tooling if adequate; add a parser only after a small official-document benchmark shows a need. Retain page/table evidence. No library should be selected on stars or an unsupported claim of “institutional risk engine” use. The cited projects provide components, not a validated SERAPH impact engine.

An optional hosted or local LLM can propose structured frames from permitted text. It must have no database-write, shell, browsing or arbitrary tool privileges. Supply only selected source text and the schema; treat text as untrusted data. Require exact evidence for every non-null factual field, validate numbers/units/IDs and reject unsupported spans. JSON validity is not factual correctness. Model self-rated confidence is not calibration.

Route simple official templates through deterministic parsing first. Use the model only for uncertain, high-relevance cases, with a per-run budget, token cap, timeout and deterministic fallback. Cache by document-version, model, prompt and schema hash; retain the original output and validator decisions. Pin model versions where possible and record unavoidable provider version drift. A second model is not independent confirmation of the source facts.

For Hindi and other languages: preserve original text, detect language, use a separately versioned translation representation, align evidence where feasible, and review legal/quantity spans in the original. Do not count a translation as another story source. Expand languages only when there is corresponding benchmark coverage.

## 8. Operations, persistence and frontend contract

### Acquisition correctness

Persist per-source `next_due_at`, last cursor, ETag/Last-Modified, consecutive failures, backoff and last usable item time. Respect host-level concurrency, Retry-After, response limits and source terms. Successful HTTP 200 containing a login/error page is a parse failure. HTTP 304 is a successful conditional check, not a new publication. Scheduling should use actual source cadence; five-minute outer ticks can inspect due work without fetching every feed.

Keep immutable fetch-health history. Coverage at time T must use the latest observation known by T, not today's health row. Source reliability, publication frequency and capture latency are different measurements. Missing dates may enter the live lane at first_seen with `published_at=null`; never substitute current fetch time as publication time or backdate them into historical replay.

One atomic ingestion transaction should write observation, document revision, lineage and checkpoint. Extraction can be an idempotent separately leased job keyed by document-version and extractor-version. Derived events/impacts commit with their input-manifest hash. Crash tests cover before commit, after commit/before acknowledgement, mid-batch, parser failure and correction/retraction. Coordinate with T07's crash protocol rather than creating a conflicting one.

### Proposed persistence tables

`news_sources_v2`, `news_fetch_attempts`, `news_documents`, `news_document_versions`, `news_copy_lineage`, `news_event_versions`, `news_event_evidence`, `news_entity_links`, `news_policy_versions`, `news_exposure_versions`, `news_impact_versions`, `news_review_decisions`, `news_snapshot_manifests`.

Reuse existing tables where additive migrations can represent these concepts; names are an implementation proposal, not an instruction to create duplicate stores. Add uniqueness constraints for natural document/revision and job keys, foreign keys for provenance, timestamp indexes for as-of queries, and explicit schema versions. Migrate on a backup/copy first and prove old-reader compatibility before promotion. Do not consume or overwrite uncommitted T07 changes silently.

### Read interface

`get_news_snapshot(context, filters, cursor) -> Result[NewsSnapshotV2]` must return a manifest containing snapshot ID, decision timestamp, generated timestamp, mode, source/registry/extractor/rules versions, query filters, coverage and truncation. Events and impacts use stable version IDs. Cache keys include all these dependencies; changing the registry must invalidate the relevant projection.

Before rendering, verify browser context equals payload context. Separate modes:

- `historical_decision`: only eligible evidence and registry versions at selected T.
- `current_news`: clearly labelled current timestamp and a separate market-data timestamp; never presented as what the historical market engine knew.
- `source_availability_research`: reconstructed archive research with declared availability evidence; distinct from operational replay.
- `fabricated_preview`: illustrative data excluded from real metrics and exports unless explicitly requested as examples.

The first live acceptance should use a persisted context and ordinary app refresh, not component API injection. T08 can provide a current engine run; alternatively the current-news mode can work before T08 if its separate clock is explicit. This is a material dependency improvement: do not block all news development on a market refit, but do not hide stale market context.

### Original globe and role-specific use

Preserve the earth, visual identity, role controls and preview layer. Extend the existing `news_layer.js` and payload adapters rather than replace the frontend.

- Distinct layers: issuer provenance, confirmed occurrence, mentioned geography, potential exposure, documented relationship, derived impact, scenario and fabricated preview.
- Marker detail: source link, exact evidence, assertion/legal status, times, affected target, mechanism, assumptions, unknowns and available actions.
- Arcs: endpoints, relationship source, exposure vintage, event that activated the hypothesis, direction and whether magnitude is sized. No continuous “contagion animation” implying measured flow.
- Sector panel: favourable/adverse/unknown mechanisms, coverage, new changes and unresolved claims. Keep Hawkes diagnostics in their own units.
- Coverage panel: expected publishers versus healthy publishers, sector-policy routes, languages, connected issuers/assets, unsized edges, latency and inaccessible sources. Empty coverage is not low risk.
- Pagination: latest-first before limiting; provide separate totals for all eligible events and displayed events. Never show estimates whose event detail has been silently truncated without a retrieval route.

Retail: “Why this may matter to my holdings,” maximum three mechanisms, affected share if documented, missing holdings/exposure warning, no automatic buy/sell instruction. Professional: event query, document comparison, product-country exposure matrix, portfolio scenario ranges and evidence export. Regulator: sector concentration, policy timeline, unresolved critical exposure, source outages and review workflow. Role-specific projections share the same facts; changing role must not change underlying event truth. Existing role selection is not authorization; connect real access control only through the project's approved identity work.

## 9. Validation: correctness first, usefulness separately

### A. Extraction benchmark

Create a frozen, versioned corpus of **600 documents/event examples** as a proposed first benchmark: 120 Indian policy, 120 foreign trade/regulation, 120 company/operations, 80 macro/monetary, 80 logistics/hazards and 80 hard negatives/retractions. Include at least 100 non-English examples across the supported languages, overlapping those groups. Include multi-event documents, amended PDFs, negation, old/new rates, prospective dates and mirrored agency releases.

Split chronologically and group all versions, syndications and translations of an event into the same partition. Suggested initial split: 300 development, 100 validation, 200 locked test. Two reviewers label critical fields independently and adjudicate disagreements; if only one reviewer is available, mark the corpus provisional and do not claim inter-annotator reliability. Keep evidence documents according to their rights; metadata/allowed excerpts and references can stand in for disallowed redistribution.

Measure event detection precision/recall/F1, action/status accuracy, quantity exact match, entity/link precision, location-role precision, unsupported-claim rate, abstention rate and duplicate-cluster errors. Report by source family, sector, language and legal stage; do not hide a weak foreign-policy slice behind easy RBI examples.

Proposed release gates to freeze before evaluating the locked set: at least 95% precision for promoted event/target links; at least 90% recall on supported event classes; at least 98% accuracy for numeric/unit/legal-stage fields on the applicable labelled subset; zero known look-ahead/context breaches; all adversarial regression cases fixed. These are proposed engineering requirements, not measured achievements or universal statistical guarantees. Report counts, uncertainty intervals and abstention coverage. If a slice is too small, label it unevaluated and restrict automatic promotion there.

### B. Impact correctness benchmark

Construct at least 150 event-target-mechanism cases using contemporaneous evidence: importers versus domestic producers, borrowers versus lenders, oil upstream versus downstream, tariff increases/decreases, expired exemptions, cancelled subsidies, plant restart, sanctioned entity false matches and unaffected products. Label mechanism validity and applicability separately from market-return outcomes.

Use two assessments: (1) was the claim supported and economically coherent given information at T; (2) did a predeclared future operational/financial outcome occur? A coherent scenario is not a proven forecast. Do not ask a model to generate “ground truth” from its own output. Preserve ambiguous/mixed labels where reviewers cannot establish a unique sign.

### C. Predictive usefulness experiment

Only after trustworthy timestamped events accumulate: freeze a target and horizon, universe, trading-calendar treatment, eligibility rules and baseline. Compare market baseline, original pillars, news-only and combined variants without removing the pillars from the product. Use only matured labels, train/validation/test chronology, overlapping-label embargo/purge where needed, and event-group-aware uncertainty estimates.

Evaluate precision/recall at an operational alert budget, false alerts per week, lead time from available_at, PR-AUC, Brier/log loss and calibration for actual probability models, missing-coverage slices and robustness to source outages. For return/event studies, use a pre-event estimation window and report confounding/concurrent announcements; abnormal return is not automatic proof of causal impact. Account for market already anticipating announcements. Publish null and negative results.

COVID or other historical replay must include all preregistered crises and non-crisis controls. A WHO or other external signal is credited to external evidence. Current retrieval of an old page must not masquerade as a real 2020 acquisition. Report archive-availability uncertainty and sensitivity to plausible capture delays. Do not change old crisis labels or thresholds to make this feature look successful.

### D. Required integration scenarios

1. New official item acquired through scheduler appears on ordinary refresh with stable ID, source and timestamps.
2. A cited foreign policy and eligible exposure produce a real India path; an excluded product/country produces none.
3. A real domestic plant incident maps the plant, while company headquarters and speech venue remain distinct.
4. A denial, correction, expiry and retraction update current interpretation without rewriting an earlier snapshot.
5. A source outage marks missing coverage; recovery backfills safely and does not duplicate events.
6. Several copies of one wire do not increase independent confirmation or severity.
7. A later exposure registry version is invisible to an earlier decision snapshot.
8. Current news cannot be inserted beneath a historical decision header without an explicit separate-clock mode.
9. A portfolio containing unmapped holdings shows uncovered value; no zero-risk substitution.
10. Fabricated previews remain visible when requested, but cannot enter real rankings or exports.

Persist evidence manifests, fixture hashes, commands, test output and browser screenshots. A screenshot is supporting evidence; the acceptance must also assert source-to-snapshot lineage.

## 10. Dependency-aware implementation tickets

All tickets below are **planned**, except where their baseline infrastructure already exists. Sequential work is preferred. Shared contract changes must be described with migration effects and tests before editing. Each ticket should produce a small reviewable diff and an evidence entry; do not combine unrelated market-engine refactors.

| Ticket / priority | Missing work and exact development target | Dependencies / can start? | Likely files/interfaces | Acceptance evidence |
|---|---|---|---|---|
| NI00 / P0 | Reconcile current T07/T08/T10/T13 state, ownership, dirty files and audit findings; preserve all work | None / yes | Existing docs, git status, store contracts | Baseline manifest, no discarded changes, agreed file ownership |
| NI01 / P0 | Add semantic counterexamples and table-driven field contracts; include pagination, units, health-as-of, source independence | NI00 / yes | New focused `tests/test_news_semantics_v2.py`, existing news tests | Tests demonstrate current defects without weakening old invariants |
| NI02 / P0 | Design EventFrameV2, quantity, location-role and ImpactHypothesisV2; document migration/read compatibility | NI01 / yes | `news/model.py`, product contracts, serializers | Versioned contract examples, consumer impact inventory, compatibility tests |
| NI03 / P0 | Correct action/negation/modality/quantity/temporal extraction; multi-event support; stop category-only sign | NI02 / yes after contract | `extraction.py`, proposed `event_frames.py`, `quantities.py`, `rules/` | Ten audit counterexamples plus variants pass; unsupported sign unknown |
| NI04 / P0 | Separate reporting lineage, corroboration and event version identity; correction/retraction lifecycle | NI02–03 / yes after contract | `acquisition.py`, `model.py`, proposed `lineage.py` | Copied wires count once, official authority explicit, event history reproducible |
| NI05 / P0 | Repair graph traversal, dimensional aggregation and target-specific mechanisms | NI02–04 / yes after extraction | `estimation.py`, proposed `mechanisms/` | Cycle/diamond/order tests; mixed units rejected; overlapping exposure not summed |
| NI06 / P0 replay | Bitemporal source, health, document, registry and event persistence; atomic work protocol | NI02 + reconcile T07 / coordinate first | Store migrations/adapters, acquisition, registry | Migration on copy, as-of tests, crash tests; old snapshots unchanged |
| NI07 / P1 | Scheduler due-times, persistent validators, retries/partial failures, coverage and metrics | NI06 / yes after durable interface | `run_news.py`, `http_feed.py`, operations | Per-source cadence tests; restart no duplicates; failed source visible |
| NI08 / P1 | Permitted official document acquisition, PDF/table representation and publication-date parsing | NI02, NI06 / yes | Proposed `news/adapters/`, document parser | Official fixtures with evidence spans; missing dates retain first_seen-only mode |
| NI09 / P1 | Add PIB and SEBI; fix source probe definition and report inconsistency | NI07–08 / yes | Source registry/config, probe script, adapters | Fetch/parse/replay fixtures plus bounded live smoke; no blanket accessibility claims |
| NI10 / P1 | Add exchange filings and a small issuer/facility registry | NI08 + access/rights / conditional | NSE/BSE adapters, curated data | Document dedup across exchanges; cited issuer/facility map with dates |
| NI11 / P1 | Add DGFT/CBIC/Gazette and US Federal Register/USTR; policy state machine | NI03, NI08 / yes with source access | Proposed `policy.py`, trade adapters | Proposed/final/effective/repealed states and annex parsing tests |
| NI12 / P1 | Build trade/product exposure mappings and tariff applicability/scenarios | NI05–06, NI10–11 / after data | Proposed `exposure.py`, `tariffs.py`, versioned mappings | Foreign policy→Indian exposure worked example; exclusions and unit tests |
| NI13 / P1 | Add energy, power, IMD, pharma and China/EU source pilots; broad journalism under rights | NI07–12 / staged | Adapter plugins and source config | Per-sector coverage matrix, parser fixtures, outages visible |
| NI14 / P1 | Evaluate optional NLP/LLM extractors against deterministic baseline; choose based on evidence | NI01–04 + labelled dev set / conditional | Proposed `extraction_backends.py`, benchmark tooling | Per-slice accuracy/abstention, CPU latency/cost, pinning and fallback report |
| NI15 / P1 | Repair globe semantics, latest-first pagination, context clock and explanatory panels | NI02, NI05–06 / yes after transport | `news_view.py`, `globe_payload.py`, `console_backend.py`, `prototype_app.py`, `news_layer.js` | Browser ordinary-flow acceptance, context rejection, original UI retained |
| NI16 / P2 | Role-specific portfolio relevance, professional scenario matrix, regulator coverage/review | NI12, NI15 + existing role/access contracts / staged | Dashboard/decision-support adapters | Same facts across roles, uncovered holdings visible, server authority checks |
| NI17 / P1 release | Frozen extraction/impact benchmark, prospective shadow operation and final feature acceptance | NI03–16 / begin labels early, gate late | Evaluation scripts, evidence manifests | Locked-set results, all integration scenarios, limitations and supported claims |
| NI18 / P2 research | ICIO scenarios and incremental predictive-news experiment | NI12, NI17 + preregistered extension / not immediate | Separate research modules/results | Validated units/vintages; baseline comparisons; no unsupported predictive claims |

Practical sequence: NI00–02 -> NI03–05 -> NI06–09 -> NI10–12 -> NI15 -> NI13–14 -> NI16–17. Begin benchmark curation early, but lock the test set before model selection. NI18 is a separate research extension. This order deliberately moves semantic correction ahead of coverage expansion and allows a clearly clocked news view before a fresh market-model run.

### First usable milestone

Do not wait for all 48 families. Ship a reviewed pilot with repaired semantics, durable acquisition, PIB+SEBI+exchange+Indian trade+US policy, a cited exposure registry, one real foreign-to-India path and one domestic facility example. Every remaining coverage gap must be visible. This is substantially more useful than adding dozens of unvalidated feeds to the present keyword engine.

### Advanced functionality after the pilot

- **Policy change ledger:** show exactly which clause/rate/product/exemption changed between instrument versions, with a countdown to effective dates.
- **India dependency lens:** country-product-sector heatmap with import concentration, substitutes and stale/unknown exposure flags; connect each cell to evidence.
- **Who benefits / who is hurt:** opposing target mechanisms side by side, including why the net result is unknown.
- **Contradiction and reversal monitor:** distinguish denial, correction, withdrawn proposal and actual reopening; revise hypotheses without deleting history.
- **Evidence-sensitive portfolio briefing:** highlight only changes to the user's documented exposure since the previous snapshot; expose unmapped holdings.
- **Coverage debt queue:** prioritize missing product/entity mappings by affected portfolio value and source importance, without calling that value predicted loss.
- **Policy cascade timeline:** relate proposal, consultation, adoption, implementation and measured outcome; prevent each headline becoming a new shock.
- **Scenario workbench:** vary pass-through, duration, inventory and substitute capacity with cited starting values and clearly labelled assumptions.
- **Source disagreement view:** compare independent claims and missing evidence rather than majority-voting copied headlines.
- **Prospective early-warning journal:** archive every alert, abstention and revision so later evaluation includes false alarms and missed events.

## 11. Exact first implementation prompt for Claude

> Work directly in `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`. Read this news-intelligence plan and its audit evidence. Do not commit or push. Preserve Hawkes, RMT, Hamilton, the preregistered evaluation and the original globe/role UI. Keep fabricated previews explicitly tagged and excluded from real analytics.
>
> Start with NI00–NI03 only. Inspect current repository state and ongoing T07/T08/T10/T13 work; do not overwrite or silently absorb another session's changes. Reconcile any changes since the 17 October audit. Reproduce the recorded semantic defects with focused tests. Describe EventFrameV2, typed quantities, legal/assertion status, location roles and downstream compatibility before implementing their additive migration/adapter. Then fix negation, cancellation, old/new rate parsing, bps, unsupported occurrence timestamps and category-only direction. Preserve unknowns and evidence spans. Do not activate dozens of sources before these semantics are correct.
>
> Run only relevant tests and record results and limitations. Keep existing scientific results unchanged. Update an implementation ledger with completed ticket IDs, changed files, evidence and next dependencies. After this first milestone, continue in the plan's dependency order only within the user's authorized implementation scope. External accounts, paid licences and material scientific-assumption changes must be identified explicitly; do not fabricate them or bypass access restrictions. A source is enabled only after endpoint, parser, timestamp, rights and coverage checks. End each milestone with a concrete evidence-backed report, not a claim of production readiness.

## 12. Definition of completion for this feature

The feature is complete for its declared pilot universe when ordinary acquisition populates the original frontend; legal and economic semantics pass the frozen benchmark; facts, hypotheses, scenarios and fabricated previews remain distinct; documented domestic and foreign exposure examples work end to end; replay and current modes use honest clocks; source failures and missing exposure are visible; role-specific views use the same underlying evidence; and every release claim is linked to reproducible evidence.

Broader global coverage and predictive edge remain separate claims. Neither a passing software suite, a populated globe, more news articles nor an LLM-generated explanation establishes that SERAPH can predict a crisis.
