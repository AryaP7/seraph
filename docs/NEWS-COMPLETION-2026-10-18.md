# News completion work — 18 October 2026

Work directly in the promoted Astra checkout; preserve existing changes. No
commit or push is authorized. News remains F2, separate from CSRS and all three
original pillars. Baseline copies and git status are saved outside this checkout
in `Documents/Codex/2026-10-14/f/news-baseline-2026-10-18`.

## Implementation order and acceptance contracts

1. **Role delivery.** Accept both raw holdings and the existing `byHolding`
   portfolio result at the news boundary. Deduplicate event routes, distinguish
   mapped holdings from holdings with current evidence, and render each role's
   actual news projection with clickable evidence. Regression: the normal
   portfolio tool output must render without the optional-view exception.
2. **Acquisition recovery.** Add backward-compatible request lease/token columns;
   reclaim expired requests atomically and reject late completion by a previous
   lease holder. Serialize ownership/coalescing. Claim worker ownership before
   catch-up, supervise deadlines with bounded child waits and terminate/reap
   before replacement. Test crash/restart, concurrent asks, stale completion,
   hung worker and healthy long operation.
3. **Lifecycle and temporal evidence.** Apply supersession to the actual current
   event set, gated by replacement availability and effective time. Historical
   replay must exclude records of unknown availability while current monitoring
   can display explicitly disclosed undated reference data. Test future and
   unknown effective dates, ended instruments and replay truncation.
4. **Evidence depth and coverage.** Inspect permitted full-document acquisition,
   implement missing bounded extraction and persist new evidence without editing
   immutable stories. Curate only first-party supported facilities/relationships;
   counts alone cannot close geographic or sector coverage.
5. **Validation and delivery.** Exercise changed Python contracts, JS rendering,
   actual browser roles/globe and invariants; record outcomes. Complete benchmark
   tooling and release reporting without changing the preregistered thresholds.
   Reconcile limitations and provide a resumable acceptance inventory.

## Definition of completion

Engineering, curated coverage and scientific validation are separate acceptance
requirements. A running feature is not proof of interpretation accuracy. The
600-document corpus, chronological locked test set, two independent reviewers,
exposure targets and prospective observation remain required by the plan. No
synthetic or agent-generated labels count as independent human review. External
sources must retain their publication/first-seen timestamps and licensing rules.

## Results

Continuation completed the interrupted scoring work and checked the preceding
fixes against the current working tree. This is **not a claim of 100% feature
acceptance**: the independent benchmark and prospective evidence remain absent.

| Area | Implemented and verified | Remaining limit |
|---|---|---|
| Roles / portfolio | All three role views render; actual portfolio `byHolding` output works; lowercase `unclassified` stays unmapped; documented counts require actual routes; full-width role panels avoid grid overlap | Exposure coverage remains incomplete; retail shows three route summaries and links to the full evidence |
| Acquisition | Expiring claims, fenced completion, OS ownership lock, bounded supervisor waits with termination/reaping | Source/network failure is still possible and visible |
| Documents | Bounded HTML/plain/PDF extraction; persistent attempt cooldown; deferred retrieval survives HTTP 304/restart; metadata-only older rows can be enriched after permissions change | No OCR or arbitrary PDF table interpretation; source permission and access restrictions remain |
| Revision / replay | Supersession applied in current partition; strict replay excludes undated records; same-second corrections now form a single latest revision | Cross-document legal links require evidence; missing dates are excluded, not invented |
| Exposure | Cited NTPC curation loads: registry now has 21 issuers, 28 assets, 64 relationships | Only 15 issuers have sectors; no verified exact asset coordinates; relationships remain financially unsized and concentrated |
| Evaluation | Real gold-field scoring; no automatic action credit; validated/atomic review imports; chronological/hash checks; human adjudication; test-only scoring; fixed predictor's reversed Story body/timing arguments | 395 frozen candidates, zero independent reviews, no locked test set; current gold schema is single-event; multi-event evaluation and prospective shadow operation remain |

### Verification evidence

- **542 tests passed** in the news/NI/frontend/backend suite:
  [JUnit](evidence/news-intelligence/continuation-tests-2026-10-18-final.xml).
  After the final metadata-only recovery and same-second revision fixes,
  **82 targeted tests passed**:
  [JUnit](evidence/news-intelligence/continuation-final-regressions-2026-10-18.xml).
  These runs overlap; do not add them to invent a distinct-test count.
- Both JS harnesses passed; the news layer has 31 checks. The mechanical
  invariant checker passed. This session did not rerun the unrelated full market
  and database suite.
- Ordinary Streamlit browser flow verified three role projections, portfolio
  submission, the unmapped warning, six globe markers and two source links.
  [Final browser result](evidence/news-intelligence/continuation-roles-2026-10-18-final/result.json),
  [retail screenshot](evidence/news-intelligence/continuation-roles-2026-10-18-final/retail.png).
  Screenshot review additionally caught grid compression from the inserted role
  panel; its row now spans all columns. The browser verifier checks visibility,
  width and overlap as well as DOM text.
- [Real document recovery](evidence/news-intelligence/document-recovery-2026-10-18-r2.json)
  retrieved two Fed articles in an isolated copy. The unchanged-feed response was
  simulated; document HTTP requests were real. Federal Register attempts remained
  explicitly unavailable. Probe stories were not merged into production counts.
- Both legacy and frozen-corpus release commands returned **exit 1**, correctly:
  [legacy report](evidence/news-intelligence/ni17-gate-continuation-2026-10-18.json),
  [frozen snapshot report](evidence/news-intelligence/frozen-corpus-evaluation-2026-10-18.json).
  The frozen manifest is unchanged; no labels were invented.

### Operational handoff

The existing launcher starts the supervisor and reconciles source registrations.
Restart it to use the updated worker. Install the updated project dependencies
when recreating the environment; `pypdf 6.21.1` was installed and tested here.
The PDF implementation follows the package's
[documented text API and limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

Use [NEWS-RUNBOOK.md](NEWS-RUNBOOK.md) for acquisition, isolated browser/document
probes and independent review imports. Current limitations were reconciled in
[NEWS-INTELLIGENCE-LIMITATIONS.md](NEWS-INTELLIGENCE-LIMITATIONS.md); its prior
wording was archived as evidence. The 395-document snapshot is preparation for
review, not an adequate benchmark: collect the missing category/language/event
coverage and create a new frozen version before an independent locked evaluation.

No commit, push, market-model refit or change to the three pillar families was
made by this continuation. Pre-existing work and prior evidence were preserved.
