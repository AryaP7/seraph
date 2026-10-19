# News feature — verified scope and remaining limits

Updated 18 October 2026 after continuation of the interrupted implementation.
Historical wording is preserved in
[evidence](evidence/news-intelligence/limitations-before-continuation-2026-10-18.md).

The role/portfolio and acquisition-recovery defects have engineering fixes and
regression coverage. This is still a pilot whose full release acceptance has
**not** passed. Engineering tests do not establish interpretation accuracy.

## Verified delivery

- Retail, institutional and regulator news projections render through the
  ordinary Streamlit flow. A browser check submitted holdings, displayed
  portfolio weights and an unmapped-holding warning, and opened sourced globe
  evidence. See the [browser result](evidence/news-intelligence/continuation-roles-2026-10-18-final/result.json).
- Retail accepts the app's aggregate `byHolding` output. Both uppercase and
  lowercase unclassified sector values remain unmapped. Evidence coverage is
  counted from actual current routes, separately from issuer resolution.
- Refresh claims use expiring leases and fencing tokens. Abandoned claims are
  requeued; an old owner cannot complete a replacement worker's request. The
  OS lock prevents competing workers, and the supervisor terminates/reaps a
  stalled child before replacement.
- Current-event partitioning applies available, operative supersession links.
  Strict historical replay excludes reference records with unknown availability
  dates. Current monitoring may use them with disclosed assumptions. The system
  does not establish arbitrary cross-document legal relationships from titles.
- Permitted article retrieval is bounded and rights-gated. Deferred documents
  resume from the store after HTTP 304 or restart; failed URLs have a persistent
  retry cooldown. Later permissions allow retrieval from old stored URLs without
  reconstructing discarded feed bytes. Earlier evidence remains immutable.
- PDF text extraction runs in a disposable process with a deadline, input/page/
  stream/text limits, and page boundaries. Blank/scanned pages make text partial;
  image-only or encrypted PDFs are explicitly unavailable. No OCR or general PDF
  table interpretation is claimed. HTML tables retain cell boundaries.

## Measured coverage

The [read-only production snapshot](evidence/news-intelligence/document-recovery-2026-10-18.json)
contained **17 registered endpoints, 458 stored story versions and 24 nonempty
bodies**. Counts include revisions; bodies can be feed summaries. The two fixed
historical-document monitors are not continuing publisher feeds. Newly configured
sources and permission changes take effect when the worker reconciles its registry.

The curated registry loads without errors: **21 issuers (15 with sectors),
28 facilities/assets and 64 relationships**. Twenty-seven stations and 54
relationships come from the cited NTPC station register. This reaches the numeric
pilot targets, but the new routes concentrate on one issuer and the energy sector.
None of the assets has verified exact coordinates. State-level locations must
not appear as precise facility pins. Relationship magnitudes remain unsized;
commissioned MW is capacity, not a financial exposure or expected loss.

Document retrieval was also tested against real Fed pages in an isolated copy.
Those probe additions are **not production coverage gains**. Source HTTP failures,
rights restrictions and feed rotation still limit what can be collected.

## Evaluation remains incomplete

The [legacy gate report](evidence/news-intelligence/ni17-gate-continuation-2026-10-18.json)
fails corpus sufficiency, slice completeness and thresholds. Its 34 provisional,
agent-labelled examples are regression cases, not independent accuracy evidence.
There are 14 link examples, and no gold action, numeric or unit examples. An
existing action field no longer receives automatic credit for correctness.

A separate [frozen review snapshot](evidence/news-intelligence/frozen-corpus-2026-10-18/manifest.json)
contains **395 deduplicated documents and zero reviews**. Under the fixed
300/100/200 chronological policy it contains 300 development and 95 calibration
documents, **no test documents**. It is a preparatory snapshot, not the required
600-document benchmark or an independent held-out test. Do not edit its manifest
to grow it: create a new version after sufficient eligible documents are available.

The benchmark tool validates hashes, split structure, independent reviewer
attestations and field labels; imports batches atomically; preserves disagreements;
and accepts separately recorded human adjudication. Only test documents contribute
to metrics. Agent reviews cannot satisfy the human-review requirement. The current
gold schema evaluates one event per document; multiple extracted events abstain
rather than choosing the answer that scores best. Multi-event evaluation, category
and non-English quotas, the independent locked test set, and prospective shadow
operation remain release requirements. Review independence is attested by people;
software cannot establish it merely from two different IDs.

## Operating limits

Polling is periodic, not streaming. Screen refresh reprojects the store and does
not acquire news. A stopped worker means acquisition is stopped even if the screen
refreshes. The supervisor recovers a stalled child but gives up after its bounded
restart budget. Source coverage gaps and an unmapped portfolio are missing evidence,
not an absence of risk. Archive recovery depends on each source's retention/API.

Hindi remains a narrow, explicitly qualified rule set. Sector directions are
qualitative hypotheses, not measured losses, recommendations or loss probabilities.
No news signal enters CSRS, fusion weights, Hawkes, RMT or Hamilton.

See [completion evidence](NEWS-COMPLETION-2026-10-18.md) and the
[operating/review commands](NEWS-RUNBOOK.md).
