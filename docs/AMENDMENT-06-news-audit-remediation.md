# Amendment 06 — remediation of the 18 October 2026 news audit

Scope: `docs/NEWS-FULL-AUDIT-2026-10-18.md`. This amendment records what was
changed in response to it, with the evidence, and what was deliberately **not**
changed. It does not restate the audit's verdict and does not claim the feature
is releasable: most of the release gate is evidence and review work that no code
change can satisfy.

Nothing in the market pillars (Hawkes, RMT, Hamilton) was touched.

---

## 1. The eleven confirmed defects

All eleven are closed, each with a regression test in
`tests/test_news_audit_2026_10_18.py` (65 tests) named after its ticket.

| ID | What produced the wrong output | What now happens |
|---|---|---|
| **A01** | `class_recall` counted every labelled document, so 95 correctly rejected hard negatives and five entirely missed supported events reported **95% recall**. | Recall is over supported positives only (**0.0** on that counterexample). Negatives are a separate `negative_specificity` slice carrying their false positives, plus per-class results. The same defect in the legacy runner (`scripts/run_news_gate.py`) is fixed too. |
| **A02** | The date pattern recognised named months; the conversion accepted only ISO. "effective from 1 December 2026" gave `effective_at=null`, which lifecycle reads as *no later start* — i.e. in force today. | `parse_date` converts day- and month-precision forms with the precision recorded. A future start downgrades to `adopted`; a month window containing the decision time abstains; a stated-but-unconvertible start abstains. Future **ends** (a revocation dated next month) no longer report the measure as already ended. |
| **A03** | Scope was read from the headline. A body reading "This order does not apply to products from India" still emitted an adverse Indian steel route. | Carve-outs are parsed from the retained text into the frame (`excluded_countries/products/parties`) and enforced in the exposure walk before a target link is promoted. The counterexample now yields **no impacts**. A carve-out that is detected but cannot be named still only caps confidence — suppressing on an unreadable exclusion is the same guess reversed. |
| **A04** | A headline halt plus a body denying it became a confirmed event with affected targets, and a separate denial that qualified nothing. | Clauses are grouped by the claim they make before splitting. A document that makes one claim is extracted over its whole text, where the assertion rules already prefer the denial. One event, `denied`, no targets. |
| **A05** | The same claim in the title and the first body sentence became two event ids and two sets of estimates. | Same mechanism: one event, with the repetition recorded in `unknowns` and the detail from the repeated sentence (the named facility) retained. |
| **A06** | `[a-z0-9]+` tokenisation returned **nothing** for Devanagari, so every Hindi item of a day hashed to one empty token set. | Script-agnostic tokenisation by Unicode category, including the combining marks `\w` drops. A headline with fewer than two content tokens gets a document-specific key rather than sharing one. `NewsStore.rebuild_syndication_groups()` recomputes derived groups into `syndication_rebuilds`, **leaving the immutable story rows and every observation untouched**. |
| **A07** | Observation ids are derived from content, so a document going A → B → A collapsed onto the first A and B stayed current. | A `document_states` timeline per reference. Repeated current bytes stay idempotent; returning to earlier bytes records a new state (`reverted=True`) with a new story that corrects the previous one. Legacy stores are backfilled from their own observations. |
| **A08** | Nothing persisted a successful document retrieval, and the cooldown explicitly excluded the `retrieved` status, so the first URL consumed the whole budget on every pass and the second document never got a body. | Retrieved text is persisted (`documents`) with a declared refresh window, reused without a request (identical bytes → idempotent, no spurious correction), and the budget is allocated to documents that have no text, least-recently-attempted first. |
| **A09** | An abandoned `news.poll` lease produced **zero fetches** while the loop beat `running` / "waiting for next poll" for the lease's full 30 minutes. | The worker reconciles a lease whose holder is provably dead on this host (recorded as a failed run, never a silent steal) and refuses to break one it cannot ask about. A pass that did not poll now beats `failed` / `lock_unavailable` with the reason. |
| **A10** | A strict 08:00 replay showed a 10:00 heartbeat with age **−120 minutes** and a gap first observed at 10:00. | Worker liveness is not versioned, so a strict replay **omits** it (`unavailable_at_decision_time`) rather than back-dating it. Gaps are filtered by observation and closure time. A negative age is never published in any mode. Evidence notes come from the source record as it stood. |
| **A11** | An order and a separately published revocation stayed unlinked; supersession only worked when a caller already knew the answer. | Documents are linked on the identifiers they **cite** (`A-533-863`, `731-TA-1234`, `RC No. …`, notification numbers), never on a similar title. A terminating document that cites nothing held raises a named unresolved-link warning on the regulator surface, stating that the earlier order is still reported as in force. Reviewers can confirm or reject links through an append-only, time-bounded review record. |

**Evidence.** The audit's own scripts, re-run unchanged against the fixed code,
are in `docs/evidence/news-intelligence/post-audit-fixes-2026-10-18/`
(`probes.py` → `findings.json`, `semantic_probes.py` → `semantic-findings.json`).
`probes.py` there carries two added cases for A11 — the same pair with a shared
case number, and with a reviewer-supplied link. The original audit evidence
directory is untouched.

---

## 2. Implementation work completed

| Workstream | What was added |
|---|---|
| **Economic mechanisms and scenarios** | `tariff_cost_scenario()` had no production caller. `measure_from_event()` builds the instrument from the document's own stated rates, the issuing jurisdiction, the subject origin and the exposure edge's products; `scenario_for()` prices it; the institutional role view calls it for every duty route and the console renders it. With no eligible cost base there is **no monetary range** — only the landed-component change, which is arithmetic on the instrument itself. With no pass-through assumption the interval is the full admissible `[0,1]`, stated as bounds rather than a fitted midpoint. A route that cannot be priced returns its reasons. |
| **Reproducible processing** | `version_manifest()` had no production caller. Every payload now carries a `manifest` pinning the view, extractor, frame-rule, syndication-key and estimation versions, the registry manifest, per-source definition hashes, per-event representation hashes, and processing latency — and states `provenance: reconstruction`, i.e. frames rebuilt with today's rules, explicitly **not** a replay of what the running system emitted. Source definitions are now versioned on change rather than once per second. |
| **Source contracts and rights** | One `may_store_full_text` boolean covered five distinct uses. `Source` now carries per-use permissions (`fetch`, `process`, `store`, `display`, `redistribute`) with reviewer, date and terms-version. An unreviewed source behaves exactly as before — the fallback is never more permissive than the registration. Storage and document retrieval are gated on `store`; quotations are withheld on the surface when `display` is not permitted (offsets survive, so the claim stays traceable); redistribution is never implied. |
| **Retention** | `retention_days` had no enforcement path. `NewsStore.apply_retention()` removes the **text** (observation bytes, story body, cached document) and keeps everything that makes the removal auditable: the observation row, its content hash, the story title and URL, and an immutable `retention_redactions` entry. The immutability triggers are restored in the same transaction. Available as `run_news.py --retention [--dry-run]`, run at worker start and every hundredth pass. |
| **Historical registry coverage** | `source_places.csv` gains the `known_from` column the loader already read. `MasterData.registry_completeness()` names every undated row (5 places, 1 entity, 10 source mappings — matching the audit's count) and states what a strict replay drops because of it. **No date was invented**: `known_from` is when this system curated the record, and nothing here knows that. |
| **Evidence independence** | `reporting_origins` held one group token, so every event reported `confirmations = 1` and nothing distinguished the four situations behind that number. `seraph/news/corroboration.py` separates document duplication, copied reporting, independently written copy and revisions, and reports them per event. It does **not** raise `confirmations`: a syndication group is one reporting origin however many outlets carry it, and differently written copy is evidence of two keyboards, not of two sources. `independence_verified` is always `False`, because nothing in this corpus records wire relationships or newsroom sourcing. |
| **UI consistency** | The method panel stated "Not connected — fabricated previews retained" as a constant; it now derives connected/preview surfaces, feed freshness, rights-review counts and provenance from the payload. Retail portfolio weights are formatted to two decimals with a `<0.01%` floor instead of printed raw. Scope messages no longer assert that a body is unretained when one is on file — the frame is told what the record holds. Evidence rows show the actual `text_scope` and any licence withholding. |

Covered by `tests/test_news_completion_2026_10_18.py` (45 tests).

**One interaction worth naming.** Removing text under a retention window
leaves a story with no body and no stored document, which the enrichment
queue would read as an outstanding document and re-fetch on every pass —
A08's defect, reintroduced by A08's neighbour. A redaction therefore also
records a long `document_attempts` deferral and excludes the observation from
`pending_documents`. A retention window is a decision not to hold the text,
not an instruction to keep fetching it.

---

## 3. What was deliberately not done

These are the audit's remaining items that no code change can close. They are
restated here so the gap stays visible, not to claim progress on them.

* **Document and source coverage.** 24 non-empty bodies out of 458 versions, 17
  endpoints from 12 publishers, and the unavailable DGFT/CBIC/MOSPI/IMD/grid/CEA
  routes are acquisition and rights work against live publishers. A08 removes
  the mechanism that was starving enrichment; it does not add documents.
* **Exposure coverage.** 21 issuers (15 with sectors), 28 assets, 64 unsized
  edges concentrated on NTPC, no verified exact coordinates. Curation with
  citations, not code.
* **Registry curation dates.** The mechanism and the report exist; the dates
  need a human with evidence of when each row was curated.
* **Reviewed merge/split decisions.** Corroboration is reported and
  supersession links are reviewable, but a reviewed merge, split or reversal
  of an *event identity* — as distinct from an instrument link — is not
  built, and nothing records wire relationships, so independent origin stays
  unverifiable here rather than merely unverified.
* **The independent evaluation.** The frozen corpus (395 documents: 300
  development, 95 calibration, **zero** test; 13 Hindi), two independent human
  reviewers with adjudication, the separate 150-case impact benchmark, and the
  prospective shadow operation. A01 repairs the evaluator; it does not supply
  the corpus or the reviewers, and agent labels do not substitute for them.
* **Release thresholds.** The gate still fails, which is the correct outcome.
  `negative_specificity` was added to `GATES` at 0.95 and frozen before the
  evaluation that reads it; no existing threshold was lowered.
* **Advanced role workflows.** Scenario ranges now reach the institutional view
  and the unresolved-link queue reaches the regulator view. Professional
  document comparison, the product–country exposure matrix and scenario export
  remain unbuilt.
* **Operational trial.** A09/A10 make a blocked or dead worker visible; a
  declared prospective duration with acceptance criteria, and the observed run
  against it, remain outstanding.

---

## 4. Verification performed

| Check | Result |
|---|---|
| Audit defect regressions (`tests/test_news_audit_2026_10_18.py`) | 65 passed |
| Completion regressions (`tests/test_news_completion_2026_10_18.py`) | 45 passed |
| Full `tests/` (excluding `tests/js`) | see the session record; baseline before this work was 1695 passed / 14 skipped |
| Mechanical invariants (`scripts/check_invariants.py`) | all checks `[ok]` |
| Release gate (`scripts/run_news_gate.py --release-check`) | still fails, for the corpus and reviewer reasons it should; adversarial cases 8/8 closed |
| End-to-end projection over a copy of the pilot store | 397 events, four surfaces connected; 2 instrument links found from cited case numbers and 18 unresolved-link warnings raised; the 28-story Hindi group splits to zero spurious multi-story groups under the corrected key |
| JavaScript harnesses (`tests/js/bridge_harness.mjs`, `news_layer_harness.mjs`) | both pass, no `false` results |
| Audit probe scripts re-run unchanged | all seven original demonstrations behave correctly; `post-audit-fixes-2026-10-18/findings.json` |
| Semantic probe script re-run unchanged | all four demonstrations behave correctly; `post-audit-fixes-2026-10-18/semantic-findings.json` |

Two pre-existing tests were changed because the audit required the behaviour to
change, and both changes are narrowings rather than relaxations:

* `test_an_unparseable_effective_date_is_left_unset_not_guessed` asserted that
  "1 Feb 2026" was unparseable. It now uses a genuinely unconvertible phrase,
  and four new parametrised cases assert the named-month forms **do** parse.
* `test_a_carve_out_does_not_silently_drop_the_match` asserted the exact wording
  of an unparsed-carve-out limitation. The carve-out in its fixture is now
  named, so the message differs; the test still asserts the match is kept and
  confidence is capped.
