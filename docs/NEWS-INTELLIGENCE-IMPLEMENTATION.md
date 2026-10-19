# News intelligence implementation ledger

Scope: F2 acquisition, interpretation, exposure and the existing C12 globe. No
market-pillar, CSRS, shared_types or historical research artefact changes.

NI00 baseline: existing working tree preserved; status and SHA-256 hashes are in
`evidence/news-intelligence/baseline-*`. T09 already supplies SEBI, Federal Register
and USGS adapters; the audit's three-feed inventory is no longer the code baseline.

NI02 migration contract (written before implementation): add an immutable
EventFrameV2 to the existing Event transport. Existing Event constructor fields
remain readable; unknown legacy semantics abstain. Decimal quantities retain
old/new/delta and units, with exact spans in the permitted title/body text.
Frame identity hashes content, extraction version and schema; document grouping
is not evidence independence. Event.confirmations uses explicit reporting origins,
with one conservative unknown origin for legacy grouped documents. Add exposure
knowledge intervals and applicability metadata; legacy undated edges remain usable
only when no historical knowledge cutoff is requested. No historical knowledge
date is inferred from economic valid_from.

SQLite migrations are additive: health observations, source versions, validator
state and immutable projection snapshots. Existing stories/observations stay
unchanged. Current projection excludes replaced document revisions; historical
reads retain those versions until the correcting document first arrives. Freshness
is evaluated from historical health, never the mutable current row. New clients
receive semantic fields alongside the existing signals/sector/geography shapes.
Current-news mode has a separate news clock and market clock. A context mismatch
is rejected before the renderer applies it.

Release claims and remaining gates will be recorded after verification. Passing
synthetic regressions is software evidence, not a frozen accuracy benchmark or
proof of predictive value. Paid reporting, unverified endpoints, missing structural
exposure and prospective observation periods cannot be fabricated to fill quotas.

## NI15 verification (2026-10-17, browser-driven)

Five defects found by driving the real console against the pilot store
(`prototype_runs/news-intelligence-pilot.sqlite`, 200 stories, 11 feeds,
8 publishers, 181 eligible events). Evidence:
`evidence/news-intelligence/ni15-fixes.json` and
`ni15-sector-and-labels-2026-10-17.jpg`.

| # | Observed on screen | Now |
|---|---|---|
| D1 | the documented Kalinganagar → `sector:steel` exposure was **absent** from the sector panel: impacts were estimated from the 40-event page, not the 181 eligible events | impacts cover every eligible event; only the rail pages; `pagination.aggregates_cover` states the difference |
| D2 | `sector:auto` sat in the globe's **review queue** as a missing coordinate | a sector-terminated path with its evidence, routed to the sector panel; the review queue is empty and keeps its meaning |
| D3 | clicking an evidenced node opened a card headed **FABRICATED PREVIEW** above sourced Federal Register headlines with working links | one `writeDetail(html, provenance)` writer; evidenced news gets a cool EVIDENCED note, preview keeps the warm FABRICATED tag |
| D4 | a sector row read `auto` / `ambiguous · 1 events` / `Exposure unknown` | mechanism, explained direction, severity, evidence confidence, sizing, and a click that opens the source events |
| D5 | clicking a sector row could answer "the event is not on the displayed page" | events referenced by an on-screen inference travel with the rail, badged REFERENCED |

D1 is the one that mattered most: a sector panel that silently drops a
documented exposure is worse than an empty one, because it reads as evidence
of absence. The inherited test
`test_latest_before_pagination_and_matching_estimates` asserted that estimates
were a **subset of the displayed page** — it encoded the defect, and is
replaced by tests asserting the corrected property.

Still true after this work: three curated exposure edges are a pilot, not a
transmission model; most events produce no sector impact because no documented
exposure reaches them, which is the correct answer; and Federal Register prose
still classifies mostly as `other` (NI03/NI11).

## NI03/NI05/NI11/NI12 — a foreign measure reaches an Indian sector (2026-10-17)

The plan asks for "at least one complete foreign-policy-to-Indian-sector
path". It now exists, from real acquired documents, and it is gated by the
legal stage rather than by a headline.

**The gap.** 125 of 181 events classified as `other`, and the largest group
among them were US anti-dumping and countervailing determinations naming
Indian products — the one class that carries a foreign measure and an Indian
product in a single sentence.

**What was added**

| Piece | Rule |
|---|---|
| `trade_remedy_determination` | ordered ahead of the generic tariff rule: "anti-dumping" appears in both, and a determination is a stage in a proceeding, not a new tariff |
| legal stage | `consultation` → `announced` → `adopted` → `effective`, plus `expired` and `repealed`, read from the instrument |
| subject origin | `"<Product> From <Country>:"` is the Federal Register's documented title form. The country is the subject origin of the goods, resolved against the curated registry only, with an evidence span. It is **not** marked `affected` — it seeds a scoped exposure query |
| direction | role-based **and** stage-gated. Only `adopted` or `effective` establishes a measure; `exporter` is adverse, `domestic_producer` favourable, because the same measure protects the producer competing with the imports it restricts |
| exposure | one cited, **unsized** edge `in → sector:steel`, keyed to the event type and steel product terms, `target_role=exporter` |

**A defect found while building it.** A *preliminary* determination was
classified `adopted`, because its title reads "Preliminary Affirmative
Determination …, **Postponement of Final Determination**, and Extension of
Provisional Measures" and the final-stage rule matched "Final Determination"
inside the postponement. That turned "no duty yet" into an adverse signal for
Indian steel. Preliminary is now tested before final, and the final rule is
guarded against a preceding postponement, extension or scheduling.

**Observed in the ordinary browser flow** (no payload injection), *before*
the scope correction below:

> **steel** · `export, operation` · *adverse for this sector; direction
> unknown — opposing or unestablished mechanisms* · severity minor · evidence
> medium · **size unknown · 8 unsized relationship(s)** · 8 event(s) — click
> for the documents

Clicking it opened **8 of 8** source events in LATEST SIGNALS, each linking to
its Federal Register document. The screenshot shows this state; the scope
correction below took the count to 4. Evidence:
`evidence/news-intelligence/ni11-trade-remedy.json` and
`ni11-trade-remedy-to-sector-2026-10-17.jpg`.

**A scope correction on the edge itself.** The first version matched
`chromium` and `graphite electrode`, and both duly produced "adverse for the
steel sector". Chromium trioxide is a metal-finishing chemical and
large-diameter graphite electrodes are a consumable *input* to electric-arc
steelmaking: a US duty on either is a duty on a different Indian industry.
The edge now covers steel articles only, and steel-sector events fell from 8
to 4 — every remaining one a steel article.

**Still true.** One unsized edge is not a transmission model, and the row says
so. "Adverse for the exporter" is a qualitative mechanism direction, not a
measured effect on any listed company. 116 events remain `other`, correctly:
agency information collections and debarment orders are outside this
vocabulary. 13 of 28 remedies name a country the curated registry does not
hold, so they resolve no subject origin — visible, not hidden. (This read 15
before the place-alias fix in the section below.)

## NI03/NI15 — place aliases, and the instrument's subject on the globe

Three more defects, each found by running against the acquired corpus rather
than by reading code. Evidence:
`evidence/news-intelligence/ni15-subjects-and-aliases.json`.

**A place had no aliases.** Official documents write countries in their long
legal form, and none of them resolved — `"People's Republic of China"` →
unknown, while `cn` *is* curated and carries the exposure edge into the Indian
auto sector. `Entity` has had aliases since the beginning; `Place` had none,
so a curated country could never match the name an official document uses.
Exact-match only: "Korea" must not quietly become "Republic of Korea", and two
places claiming one alias still abstain. Subject origins resolved on the real
corpus rose from 13 to 15 of 28 remedies.

**The subject of an instrument is not its issuer's jurisdiction.**
`exposure_origins` carried both the new subject-origin rule and the inherited
issuer-jurisdiction seed, so a US tariff notice put the United States in the
globe's new `subjects` layer captioned "goods from here are covered by the
instrument". The subject origin is now a location **role**, and the rail reads
that rather than the shared seed. `subjects` is now exactly `['cn', 'in']`.

**A subject outranked by a publisher's office.** A country that is both was
drawn and captioned as merely a publisher's office. `subjects` now outranks
`provenance` — a publisher's office is a fact about the *publisher*, a subject
origin a fact about the *instrument*. The inherited rules are preserved:
origin still beats affected (a source of a development is never drawn as one
of its victims) and affected still beats subjects. The first attempt inverted
the origin/affected rule; the JS harness caught it.

Observed in the ordinary browser flow: `cn / subjects`, `in / affected`,
`in_od_kalinganagar / affected`, `tata_kalinganagar / origins`,
`us / provenance`, with the new legend line "goods from here are covered by
the instrument" and an EVIDENCED NEWS detail card.

**Still visible, not hidden.** 13 of 28 remedies name countries the curated
registry does not hold (Taiwan, Korea, Brazil, Germany and others), so they
place no marker. A subject marker claims no impact: who is affected still
needs a documented exposure edge.


---

## NI11/NI12 — the exposure registry stops being the bottleneck (2026-10-17)

The extractor was never the binding constraint. With 32 recognised trade
remedies and four curated edges, **five** reached a sector: the pipeline could
read a determination correctly and then had nowhere to send it. The plan's
pilot target is five sectors, so three more edges were curated — chemicals,
aluminium and agriculture.

**The citations are read out of the store, not typed in.**
`scripts/curate_trade_remedy_exposure.py` resolves each edge's `source_ref` by
matching a headline against events the pipeline actually received and taking
that event's own document URL. A mistyped reference is therefore not possible,
and an edge whose document is not in the store is refused rather than written:

```
[plan]  india_chemicals_us_trade_remedy -> sector:chemicals
        products: chromium trioxide|perfluoroalkoxy|polyethylene terephthalate
        cite    : https://www.federalregister.gov/documents/2026/10/08/2026-20695/...
```

Impacts on the real corpus went from 5 to **18**, over 206 eligible events,
reaching `sector:agriculture` (3), `sector:aluminium` (2), `sector:auto` (1),
`sector:chemicals` (4), `sector:steel` (5), plus `tata_steel`,
`tata_kalinganagar` and `in`. Registry: 2 entities, 8 places, 1 asset,
**7 edges**, 10 source places.

**What these edges do not say.** A US proceeding covering a product "From
India" establishes that the import trade exists. It is not a revenue share,
not a company exposure and not a loss. Every one of the three is unsized, and
`test_edge_is_unsized` keeps it that way.

**Product terms stay inside their sector.** The earlier steel edge matched
`chromium` and `graphite electrode` and reported both as adverse for steel —
chromium trioxide is a metal-finishing chemical and graphite electrodes are a
consumable *input* to electric-arc steelmaking. Five parametrised cases now
assert both the sector a product must reach and one it must not.

### Two defects the new rows exposed

Checking the 18 impacts rather than counting them found two.

**A sunset review being scheduled is not a lapsed measure.** "Scheduling of
Full Five-Year Reviews" was classified `expired`, which asserts the duty no
longer applies. A five-year review is the proceeding that *decides* whether an
order continues, published while the order is still in force — so the frame
said the opposite of the notice. This is the same failure as the earlier
"Postponement of Final Determination" bug: a notice that *names* a stage read
as having *reached* it.

The first fix was a negative lookbehind, and it did not work: the Federal
Register writes "Scheduling of **Full** Five-Year Reviews", the words are not
adjacent, and `re` has no variable-width lookbehind. The rule itself was also
wrong, so `expired` now requires explicit lapse wording and a review being
opened is classified as the proceeding it is. Stage distribution across 32
remedies: announced 15, adopted 6, unknown 6, effective 2, consultation 2,
repealed 1.

**A revocation is relief, and was reported as nothing.** Direction was gated
on `adopted`/`effective`, so "Revocation of the Antidumping and Countervailing
Duty Orders" — the clearest favourable trade-remedy outcome there is — carried
no sign at all, identical to an opened investigation. A repealed or suspended
measure is now `favourable` for an `exporter` and `adverse` for a
`domestic_producer`, mirroring the imposition case. The aluminium revocation
now reads `favourable` for `sector:aluminium`.

A **rescission of an administrative review** is deliberately *not* treated as
a revocation: it discontinues the proceeding and leaves the existing duty in
place, so reading it as relief would invent a benefit. The frozen-shrimp
notice stays unsigned, and a test pins that.

**A test of mine encoded the first defect.** `test_ni11_trade_remedy.py`
asserted `"Scheduling of Full Five-Year Reviews" -> "expired"`, written when
the rule was added. The expectation was wrong, not the new behaviour; it is
corrected in place with a comment recording why, which is the second time in
this work that a test had to be read as a symptom rather than a specification.

Verification: 24 new tests in `tests/test_ni12_sector_edges.py`, 103 across
the three remedy/label files, 357 passed across the news-side selection, 31 JS
harness checks.


---

## A forthcoming publication — the live channel broke on real data (2026-10-17)

Running one ordinary poll to check that "continuously updated" actually works
brought in 70 new stories and then took the whole news channel down.

```
ValueError: first_seen_at 2026-10-17T21:47:26+05:30 precedes published_at
2026-10-19T00:00:00+05:30: a source cannot be read before it publishes
```

The Federal Register places documents on **public inspection** and assigns
them a scheduled publication date, normally one to three business days ahead.
So a document SERAPH legitimately holds on 17 October carries a `published_at`
of 19 October. `Timing.__post_init__` refused to construct it, and its comment
said why: *"Receiving before publication means one of the two is wrong."*

There is a third case it did not allow for — the publication date has not
arrived yet. 40 such documents landed in one poll, and from that moment every
read of the store raised: the signal rail, the sector panel, the geography
overlay and the globe all stopped together. 44 rows in the pilot store are of
this kind.

**The guard was kept, not removed.** Its real target is a back-filled
`first_seen_at` — hindsight dressed up as information the system held — and
that check is worth keeping. What it lacked was the one fact that separates
the two cases, and that fact exists only at acquisition: there `first_seen_at`
is the current instant, so a later `published_at` can only be a future date,
whereas a back-fill has both timestamps in the past. The determination is made
once, when the story arrives, and recorded on the row. It is an observation,
not a re-derivation at read time, because at read time the two are
indistinguishable.

`Timing` gained `publication_scheduled` (default `False`, so every existing
caller keeps the old behaviour) and `is_forthcoming(as_of)`. The flag is
recorded by the store, carried into the event by the extractor — dropping it
there left the event unconstructible even after the store was fixed — and
`describe()` emits it so nothing downstream has to guess.

**The pilot store was migrated additively.** A column was added and 44 rows
were marked from two values already on each row. Stories are immutable by
trigger; that trigger guards story *content*, so it was lifted for the
migration and restored verbatim in the same transaction, with the restoration
asserted. No story text, time, url or identifier changed and nothing was
deleted.

**A scheduled date is no longer shown as a date that has passed.** The
evidence card read `Published 2026-10-19 · First seen 2026-10-17` on a
17 October screen. It now reads "Scheduled for publication … (not yet
published; on public inspection)", and the rail says "scheduled for
publication …, not yet published". Verified in the browser: **31** such labels
render in the ordinary Streamlit flow.

This case is the strongest argument yet for the module's own rule that
`first_seen_at`, never `published_at`, bounds a replay. Filtering on
publication would have hidden a document already in hand and then presented it
two days later as if it had just arrived.

### What the live poll demonstrated

| | before the poll | after |
|---|---|---|
| eligible events | 206 | **263** |
| trade remedies recognised | 32 | **38** |
| sector/entity impacts | 18 | **20** |

The two new impacts are chemicals, one of them a brand-new "Perfluoroalkoxy
Alkane From India: Postponement of Preliminary Determination" — correctly
unsigned, because a postponed preliminary determination establishes nothing.

### Verified in the browser, not in the payload

`scripts/verify_news_sectors_browser.py` drives the ordinary Streamlit flow on
read-only copies of both stores, with no payload injection:

```
{ "sectors_named": 5, "forthcoming_labels": 31,
  "clicked_links": 1, "government_links": 1 }
```

All five sectors render with mechanism, direction set, severity, evidence
confidence, `size unknown`, relationship count and "click for the documents".
The clicked evidence resolved to a Federal Register document — and the one it
opened happens to be a 19 October forthcoming document, the exact class that
had been crashing the channel an hour earlier.

Verification: 11 new tests in `tests/test_ni_forthcoming_publication.py`
pinning both halves (the legitimate case is representable and labelled, the
back-fill case still raises), 492 passed across the time/news/globe selection,
31 JS harness checks.

**Not claimed:** `fed_press` returning `new=0` on recent polls is correct
conditional-request behaviour — it holds 20 stories and the server answers
304 Not Modified against a stored ETag. An earlier reading of that line as a
dead source was wrong.


---

## NI03/NI16 — `other` was never an extraction failure (2026-10-17)

Half the corpus classified as `other` — 132 of 263 — and that number had been
treated as an extraction problem for the whole of this work, including by me.
Reading the events instead of counting them settles it:

```
Marine Mammals; Incidental Take of Polar Bears ... in the Beaufort Sea
Bulk Manufacturer of Controlled Substances Application: Groff Health Inc
Agency Information Collection Request: 3206-0218, Death Benefit Payment
Pacific Fishery Management Council; Public Meetings
Privacy Act of 1974; System of Records
```

The Federal Register feed carries the **entire US federal daily register**.
Writing patterns for "Notice of Public Meeting" would have improved the
classification rate and made the output worse: irrelevant noise dressed up as
recognised events.

So the question is split in two. **Relevance** asks whether an event touches
anything this system is about; **classification** asks what an event is. Kept
apart, `other` recovers the meaning this ledger has claimed for it all along —
*we do not know what this is*.

| | before | after |
|---|---|---|
| `other`, whole corpus | 132 / 263 (50%) | — |
| in scope | — | **132** |
| received but not about this system | — | **133** |
| in scope and unidentified | — | **16** (13 of them Hindi, abstaining by design) |
| in scope, English, unidentified | 23 | **3** |

`seraph/news/relevance.py` is deliberately **inclusive**: wrongly excluding an
event costs more than carrying a few irrelevant ones, so any one of an Indian
place, a registered entity or asset, a mapped sector, a monetary or
market-structure action, a cross-border measure, or a hazard with a resolved
affected location is enough. A cross-border measure stays in scope even when
its subject origin has not resolved — 13 remedies name countries the curated
registry does not hold, and excluding those would hide a **registry** gap
behind a **relevance** label.

**Nothing is dropped.** An out-of-scope event keeps its row, its evidence and
its link. The rail states the split, and every item carries its reason, because
an exclusion that cannot say why it excluded something is not reviewable.

**A publisher's jurisdiction counts, but only one way.** A Hindi PIB release
about CAQM in the NCR was ruled *out of scope* — the Hindi interpreter
abstains, so no Indian place resolved. That hid a declared coverage gap behind
a relevance label: a release from an Indian government source is about India
whether or not we can read it. An Indian publisher is now a basis in its own
right, labelled as the publisher's jurisdiction rather than a parsed location.
The converse is explicitly refused: a US publisher's jurisdiction is the
United States for its whole daily register, so admitting any issuer
jurisdiction would admit everything and decide nothing.

### The class that closed the English gap

All 23 remaining in-scope English events were one thing — SEBI enforcement and
recovery proceedings:

```
Notice of attachment dated October 13,2026 ... under RC No. 7712 of 2024
Notice of Demand under Recovery Certificate number 9303 of 2026
Prohibitory Order no. 1575/2026 ... Securekloud Technologies Ltd
Confirmatory order in the matter of Rajesh Exports Limited
Release Order dated October 15, 2026 for RC 8924 of 2025
Completion of Recovery Certificate No. 3965 of 2021
```

This is a real company-level risk class — several name listed companies — and
it is a legal **process with stages**, like a trade remedy. 22 are now
classified: effective 11, repealed 3, adopted 2, announced 2, expired 2,
unknown 2. Release is tested before the imposing forms because "Release Order
… for RC 8924 of 2025" contains the same recovery-certificate vocabulary as an
attachment, and read in the wrong order a lifted constraint reports as an
imposed one.

It assigns **no direction**. Most of these name individuals, not issuers, and
an attachment against a promoter is not a loss to the company. Only a resolved
target role could say otherwise — the same rule the trade-remedy class follows.

The 3 still unidentified are two SEBI publicity items (a hackathon win is not
a market event) and one bare "Order in the matter of Capital Stroke Investment
Services Pvt. Ltd." carrying no stage vocabulary at all. `other` is the honest
answer for all three.

### A mode of transport is not an event

Checking the rare classifications found `logistics_disruption` on **"Advance
Traveler Information for Rail"** — a US passenger-rail rulemaking. The rule
keyed on the bare words `port|shipping|rail|freight|berth`, so any document
mentioning a railway was a disruption of one. A transport noun now needs
disruption vocabulary with it, in either order and within a sentence's reach;
`congestion` and `blockade` stay standalone because they are disruptions by
themselves.

The other three rare classes checked out: `capacity_expansion` on Tata Steel
Kalinganagar, `bank_resolution` on the RBI's approval of the Emirates NBD /
RBL amalgamation, and `debt_instrument_event` on a Sovereign Gold Bond
premature redemption.

**One test case of mine was a bad discriminator** and is replaced rather than
forced: "Rail freight suspended on the eastern corridor" classifies as
`production_halt`, because `suspended` belongs to that rule and it is tested
first. Both readings are legitimate and one invented sentence is no evidence
for reordering them, so the case now uses vocabulary only the logistics rule
claims.

### Verified in the browser

```
scope_line: "132 in scope · 133 received but not about this system
             (carried and linked, never deleted) · 16 in scope and unidentified"
scope_reason_labels: 56   sectors_named: 5
forthcoming_labels: 31    government_links: 1
```

Verification: 34 tests in `tests/test_ni16_relevance_and_enforcement.py`,
485 passed across the news-side selection, 31 JS harness checks.

---

## NI08 — the rights question, answered per source (2026-10-18)

`may_store_full_text` was `False` for all eleven sources, with an honest
reason: *"'publicly reachable' is not 'licensed to redistribute', and that
question has not been answered for any of them… Changing that needs the terms
read, not a convenient assumption."*

The cost was real — of 278 stories only ~20 had bodies, so interpretation ran
on titles, and the Federal Register adapter was extracting each document's
`abstract` only for the store to discard it.

The terms are now read, per source, and **the answer differs by source**,
which is the whole point. A blanket answer either way would have been wrong.
Full quotes and citations: `docs/decisions/DR-10-2026-10-18-source-text-rights.md`.

| Source | | Basis |
|---|---|---|
| `federal_register`, `federal_register_india` | **permitted** | 17 U.S.C. §105 via GPO: "Copyright protection under this title is not available for any work of the United States Government" |
| `usgs_earthquakes` | **permitted** | "Most USGS information resides in the Public Domain"; credit requested |
| `pib_releases` | **permitted** | PIB Copyright Policy: "may be reproduced free of charge and there is no need for any prior approval" |
| `fed_press` | already permitted | Board-authored, unchanged |
| three RBI feeds | **refused** | its copyright page says only "© Reserve Bank of India. All Rights Reserved" — no grant |
| `sebi_press` | **refused** | permitted only "after taking proper permission by sending a mail to us"; that mail has not been sent |

Two conditions travel with every permitted source and are written into its
`rights` string: **acknowledge the source**, and **third-party material
embedded in a government document is not covered** by the government's own
licence.

The refusals now say *"terms REVIEWED and full-text retention REFUSED"* with
the reason, not *"terms NOT reviewed"*. Those are different facts and the
second is more useful: it stops the work being redone, and it records that
SEBI is one email away rather than an open question.

### The policy was already enforced where it matters

`stories.body` **and** `observations.raw` are both gated on the same flag —
`item.raw if source.may_store_full_text else None`. So the abstracts of the
124 Federal Register documents already stored were never retained and cannot
be recovered. That is the policy working, not a loss, and it settles cleanly
what might otherwise have been a temptation to re-project history: there is
nothing to re-project.

**Bodies accrue forward only.** Rows are immutable and a re-poll of an
unchanged item yields `unchanged`, so coverage grows from this date — 20/278
to 22/280 immediately, climbing as new documents publish.

### Retaining bodies is not a uniform improvement

Measured by running 34 real Federal Register documents through extraction
twice, once title-only and once with the abstract: **9 are interpreted
differently.** Abstracts average 455 characters against titles of 134.

Most changes are gains — "the Commission is proposing to amend the rule" gives
a stage where the title gave none; the issuing agency's country resolves. Two
were **regressions**, and both are one shape: a rule firing on boilerplate, or
on a body's account of the procedure that produced a decision rather than the
decision itself.

**Paperwork Reduction Act boilerplate became an economic action.** Every PRA
notice carries "As part of our continuing effort to reduce paperwork and
respondent burden" verbatim, and `reduce` made it `action=decrease`. Such
sentences are now **blanked** before the rules run — blanked, not deleted,
because every evidence span is an offset into the text the source actually
sent and removing characters would silently move every span after the cut.

**A final order was read as a proposal.** "Jeffrey Thies: Final Debarment
Order" became `proposed`, because its abstract narrates the proposal and
hearing that preceded the order. The title states what a document *is*; the
body often narrates how it got there. A finality marker in the title now
outranks a pending stage found only in the body — and only then, so a notice
whose title genuinely proposes something is untouched.

That is the **third** instance of one family — after "Postponement of Final
Determination" read as `adopted` and "Scheduling of Full Five-Year Reviews"
read as `expired` — so it is now a named rule rather than a third ad-hoc patch.

**A real gap the measurement exposed:** the stage rule matched `propose`,
`proposes`, `proposed`, `proposal` but **not `proposing`** — which is how a
Federal Register abstract almost always phrases it. Every such proposal was
reading as having no stage at all. Fixed in both the stage and action rules.

**What was deliberately not chased:** two documents still have imprecise
frames (a PRA burden estimate, a Medicare pricing model). Both are **out of
scope** — no Indian place, no mapped sector, no tracked authority — so neither
reaches a user. Writing rules to perfect the frames of US paperwork notices is
exactly the work NI16 argued against.

**Still out of scope entirely:** fetching each document's *full text* from its
own page. These bodies are feed-supplied abstracts; retrieving complete
documents is a separate question about volume and per-page terms.

Verification: 26 tests in `tests/test_ni08_source_text_rights.py`, 428 passed
across the news-side selection, 31 JS harness checks.

---

## P0 — a stopped worker was indistinguishable from a quiet market (2026-10-18)

An independent audit put worker reliability and truthful freshness reporting
first. It was right, and parts of it corrected my own earlier account: I had
reported that "nothing fetches on launch" after checking `seraph/dashboard/`
and **not** the launchers. `launch_prototype.ps1` does start a worker. The
real defects were different and worse.

### Three defects in the launch path

**Registration ran only when the store file was missing.**
`if (-not (Test-Path $NewsStore))` meant an existing database never received a
source added to the catalogue later — the feed sat in `run_news.py` and was
silently never fetched. Registration is idempotent and now runs on every
launch.

**Starting the worker fetched nothing.** It entered its loop and asked which
sources were *due*. A source polled ten minutes before a restart is not due
for another twenty, so a freshly launched server could show hours-old data
with a perfectly healthy worker attached. `--catch-up` polls every source once
before the loop, and both launchers use it. A partial catch-up deliberately
does **not** raise: one unreachable source must not stop the server coming up,
and the failure is recorded as uncovered, which is where it belongs.

**Nothing recorded that the worker was running.** This is the serious one.
`source_coverage` only notices a dead worker once each source drifts past
**three times** its own polling interval — up to twelve hours for the slowest
feed. For that entire window a dead worker and a calm news day look identical
on every surface.

### Four times, kept apart

Four distinct facts were collapsing into one impression of "current":

| | what it is |
|---|---|
| `projected_for` | the decision time the screen was built for — **not** evidence of freshness |
| `newest_first_seen_at` | when an article last reached us |
| `stale` | whether a **source** is past the policy it declared |
| `worker.state` | whether anything is **fetching at all** — this did not exist |

The worker now beats on every pass, marks itself `stopped` on a clean exit and
`failed` with the exception on a crash. `worker_state()` reports
`never_started` / `running` / `catching_up` / `stopped` / `failed` against a
threshold of five minutes that is deliberately **independent of any source's
polling interval** — a 240-minute feed must not buy a dead worker four hours
of looking alive.

**A hole found by running it, not by reading it.** `catching_up` was exempt
from the age check, so a worker hung inside a long catch-up would advertise
`catching_up` forever and never be reported dead. Any status that claims to be
alive is now age-checked; `stopped` and `failed` stay terminal, because the
worker said so itself and elapsed time does not make that truer.

### What "11/11 covered" actually means

It was being read as "the news is current". Its `basis` now says what it
measures: per-source fetch health within **three times the interval each
source declared** — explicitly *not* worker liveness and *not* editorial or
economic coverage of the news.

### The payload reached the UI only after a browser check

The freshness block was correct and invisible. `console_backend` re-shapes the
payload into an **explicit allow-list**, and a new field reaches the console
only by being named there — so `freshness` was computed, attached to every
surface, and dropped one layer below the screen. The browser verification
caught it; the unit tests could not have.

Verified in the real browser, both ways, on a throwaway copy whose heartbeat
is aged to 2020 to exercise the warning:

```
dead worker  -> worker_warning_rendered: true,  stale_warning_rendered: false
healthy      -> worker_warning_rendered: false, stale_warning_rendered: false
```

`stale=false` with a dead worker is the exact condition the audit named: the
sources were fetched recently, so source coverage calls it healthy. Only the
heartbeat separates them.

### A measure not yet in force was reported as in force

Also from the audit, and confirmed: `"effective from 2026-12-01"` read as
`policy_status='effective'` on 18 October, identical to a measure already
applying. `effective` asserts the measure **applies now**; a scheduled one has
been decided, which is `adopted`. It matters downstream — `adopted` and
`effective` are the two statuses that produce a signed direction in the
exposure walk. The frame now compares the date to the decision time and
records `decided but NOT yet in force` as an unknown.

The effective-date pattern now has **one** definition, imported by the
extractor. It was about to exist in two modules, which is exactly how
`DEFAULT_DSN` came to disagree with `docker-compose.yml`.

Verification: 20 tests in `tests/test_ni_worker_liveness.py`, 454 passed
across the news-side selection, 31 JS harness checks, and the browser
verification above.


---

## Autonomous batch — the ten definition-of-done items (2026-10-18)

### Worker supervision and recovery

`scripts/news_supervisor.py`. A worker that catches its own crash and
continues cannot be killed by the bug it is suffering from — it spins on the
same failure and reports itself healthy throughout. A separate supervising
process restarts with exponential backoff (5s, 10s, 20s … capped at 300s) and
after `--max-restarts` **stops trying and writes `failed`** to the heartbeat
row the console reads. Restarting silently would convert a loud failure into a
quiet one, which is the hazard a supervisor most easily introduces. A clean
exit is the operator stopping it on purpose and is never restarted.

### Downtime backfill, and admitting when recovery is impossible

`seraph/news/backfill.py`. Recoverability is a property of the **source**, not
of our code:

* the Federal Register API takes a publication-date range and pages through
  it — a gap of any length is recoverable exactly. Proved on a fresh store:
  **436 stories recovered** from a 7-day window the live feed (newest 40) can
  never return.
* an RSS feed returns the publisher latest N items. Anything that rotated out
  during an outage is **permanently missing, not late**, and the gap note says
  exactly that: "counts computed over this period are computed over a corpus
  with a hole in it".

`BACKFILLABLE` is a short declared allow-list, never inferred — assuming a
feed supports date ranges and silently missing items is the failure the module
exists to prevent. A gap is reported at **2×** a source interval while
`coverage_at` still calls it healthy at 3×, because collection and health are
different questions.

Two defects found by running it: a never-fetched source backfilled from
`decision_ts` to `decision_ts` — a zero-width window that recovered nothing
while reporting success (now a bounded 7-day default, named in the output);
and a failed ingest printed "0 recovered", which reads as "nothing to
recover" (now `FAILED — the gap is NOT recovered`).

### Manual refresh that actually fetches

The console already had a `news_refresh` action. It called `st.rerun()`, which
re-projects the store — so the one button a user presses when they suspect the
data is old re-read the same rows. It now fetches within a **20-second
budget**, polling the most overdue sources first so a spent budget costs the
freshest rather than the stalest. A refresh that could not reach every source
**names the ones it skipped**, reported with `st.warning` rather than a quiet
caption. Measured live: 10 sources polled in 27s, 1 skipped and named.

### Event expiry — and the decay deliberately not built

Nothing here carries a loss estimate; every edge is unsized and every
direction qualitative. Multiplying a non-existent quantity by a half-life
nobody fitted would manufacture precision from a chosen constant, so no
magnitude is decayed anywhere and a test asserts it stays that way.

What is built: a **declared relevance horizon per event class** in
`seraph/news/currency.py`, each arguable and all in one place. The asymmetry
that makes this more than an age cutoff: **a measure in force does not
expire.** A duty order from 2024 that has not been revoked is currently
costing an exporter money; an earthquake from 2024 is not. On the real corpus
six months forward, 183 events expire and the **24 in-force instruments
survive**.

### Hindi

`Lang=1` returns the same Hindi content as `Lang=2` — there is no English PIB
RSS at that endpoint, checked across three `Regid` values, so "obtain usable
English coverage" is not available.

`seraph/news/hindi.py` is a narrow rule set grounded in the 42 PIB items
actually received, each rule quoted with the headline that motivated it. It
**never claims comprehension**: a Hindi event stays `reported_unconfirmed`
however confidently a keyword matched, carries a caveat naming the rule set,
and keeps the original text as an evidence span. Other languages still abstain
entirely.

Reading the whole corpus first mattered: most of it is condolences, a craft
fair, Ayurveda awareness and youth programmes. **4 of 42 are market-relevant**,
and a rule set that classified most of this feed would be wrong. In-scope
unidentified fell 16 → 14.

### Exposure expansion

Three further cited edges — textiles, paper packaging, industrial materials —
taking the registry to **10 edges, 8 sectors, 24 impacts** (from 4 / 2 / 5 at
the start of the session). Graphite electrodes get their own sector precisely
because they are a consumable **input** to electric-arc steelmaking: a duty on
Indian electrode exports is adverse to the Indian electrode maker, not to
Indian steelmakers who buy them. A test pins that they never reach
`sector:steel` again.

### Replay versioning

`as_of()` filtered entities, places, assets and edges — and passed
`source_places` through untouched. Two leaks: a mapping curated today appeared
in a replay of an earlier date, and, silently, a mapping pointing at a place
the same `as_of` had already filtered out survived as a dangling reference.
Nothing raises — the marker simply loses its coordinates, and an absent marker
is indistinguishable from an absent source. Both are closed, and an invariant
test asserts no `as_of` can produce a dangling mapping at any epoch.

### NI17 — the gate, executed against its actual specification

Thresholds frozen in `seraph/validation/news_gate.py` **before** evaluating:
95% link precision, 90% class recall, 98% field accuracy, zero look-ahead
breaches, all adversarial cases fixed.

Measured on 34 hand-labelled examples, each labelled by reading the document
*before* comparing with the extractor:

```
link_precision    34/34  100%
class_recall      34/34  100%
field_accuracy    31/31  100%   (3 Hindi abstentions, reported)
thresholds_met    true
corpus_sufficient false
gate_passed       FALSE
```

**The gate does not pass, and that is the correct result.** The plan specifies
600 documents across six groups, 100+ non-English, a 300/100/200 chronological
split and **two independent reviewers**. This corpus is 34 documents with one
labeller — and not a human one. Passing at 100% on a twentieth of the
specified corpus, single-labelled, would be exactly the false assurance the
gate exists to prevent, so `gate_passed` requires a sufficient corpus **and**
met thresholds **and** a non-provisional labelling.

Running it found three more real defects: a title-only "Final Debarment Order"
resolved to `unknown` (title finality now stands alone, not only as an
override of a body stage); "Previously Approved Collections" matched the
adoption rule, promoting every Paperwork Reduction Act renewal to `adopted`;
and proposed rulemaking — most of what a federal register publishes — fell
through to `other`.

One of my own labels was also wrong. "Investment Company Cross Trading" is a
*topic*: the title alone carries neither class nor stage, so labelling it from
a body I had read was scoring the wrong text. The example now carries the
abstract it came with.

### A bug only the browser could catch

The console stopped rendering entirely: `UnboundLocalError: NewsStore`. The
refresh handler imported `NewsStore` *inside* `main()`, which makes the name
local for the whole function — so a call seventy lines earlier hit an unbound
local. No unit test exercises `main()`. An AST scan now confirms no other
function re-imports a module-level name.

Verified in the browser afterwards, both worker states:

```
healthy       worker_warning_rendered: false   sectors_named: 8
dead worker   worker_warning_rendered: true    sectors_named: 8
```

Verification: 600 passed across the news-side selection, 31 JS harness checks,
browser verification both ways. New test files: supervisor (9), backfill (13),
manual refresh (8), event currency (15), Hindi (21), replay versioning (9),
release gate (14).

---

## Sections 2-5 — acquisition, coverage, interpretation, roles (2026-10-18)

### The defect I introduced, and the fix

The console's 30-second timer fired `news_refresh`, and I had wired
`news_refresh` to `refresh_now(force=True)`. Every open browser tab therefore
forced all eleven sources every thirty seconds, inside the web process,
multiplied by the number of sessions. Wrong for the publishers and wrong for
the page.

Three operations now, and only one touches a network:

* **project** — re-read the store and re-render. The timer does this.
* **acquire** — *ask*. Coalesced in the store (two tabs produce one
  acquisition), rate-limited to one per minute, claimed by the worker with a
  conditional UPDATE so two workers cannot serve the same request.
* **progress** — queryable without performing anything.

### A deadline that reaches the socket

Checking elapsed time *between* sources constrains nothing: one feed that
accepts the connection and then stops sending holds the pass open for as long
as it likes. The remaining budget now becomes each fetch's socket timeout —
and the retry loop respects it too, which halved a measured overrun from 9.0s
to 5.0s on a 4s budget. Work that cannot finish is not started.

Five outcomes, kept apart because they call for different actions: `fetched`,
`unchanged`, `failed`, `timed_out`, `skipped_for_budget`.

### Gaps that survive the poll that used to erase them

Gap detection read `source_health.last_success_at`, which the first successful
poll after an outage overwrites. **Resuming destroyed the evidence of the
outage it was recovering from.** Gaps are now their own rows, recorded before
polling, with continuation cursors.

Three further defects found by running it:

* `base_url.split("?")[0]` **dropped `conditions[term]=India`** — backfilling
  the India-filtered feed would have pulled the entire US federal register
  into a store that never asked for it;
* a never-fetched source backfilled from `decision_ts` to `decision_ts`, a
  zero-width window that recovered nothing while reporting success;
* a failed ingest printed "0 recovered", which reads as "nothing to recover".

A page cap now leaves the gap **open** with a cursor. Truncation is not
completion.

### Decided is not operating

`adopted` was treated as in force, and an in-force instrument never ages out —
so a 2024 final determination reported as currently operating, forever. The
earlier future-effective fix had converted a future `effective` to `adopted`,
which was right, and `adopted` was itself in the in-force set: the downgrade
only moved the problem one step.

Applicability is now evaluated against the **requested decision time**:
`in_force`, `decided_not_yet_in_force`, `decided_effect_unknown`, `pending`,
`ended`, `dead`, each with a stated reason. Supersession ends a measure a
later instrument modifies. A document received long after publication is a
`late_discovery`, not a new development.

### Both sides of the same instrument

`beneficiaries` and `constrained_parties` had existed on the frame since it
was written and **nothing ever populated them**. Every impact reached the
screen as one signed direction, so the same document read as good or bad news
depending on which target happened to be mapped.

A duty now reports that it constrains the exporter *and* the downstream buyer
in the importing country while benefiting the domestic producer; a revocation
reverses the roles. The **net is not computed** — it needs sizes this system
does not hold.

### Product scope

An exposure walk matches on a product family, and a trade instrument covers a
defined article. A missed exclusion turns "this does not apply to you" into an
adverse signal. A detected carve-out now drops confidence to `low`; silence
about scope reports `unknown`, never "no exclusions". Both corpus false
friends — "Exclusively listed companies", "Exclusive Economic Zone" — are
rejected.

### Coverage

13 endpoints probed live, **6 registered**: NSE corporate announcements, NSE
circulars, BSE notices, USTR, Federal Reserve speeches, EC news. Sources
11 -> **17**, stories 280 -> **453**, entities 2 -> **21**.

Six recorded as uncovered with the reason: DGFT (403), CBIC / MOSPI / IMD
(certificate verification fails — **not** disabled to work around it), POSOCO
(502), CEA (not a feed).

**NSE titles are the filing entity only.** The subject lives in the body,
which is not retained. A filing resolves to its issuer and produces **no
impact and no direction**: "JSW Steel filed something" must not become
"adverse for steel", which is the most tempting invention available here.

### Roles

Three projections of one channel. Retail distinguishes a holding that does not
resolve from one that resolves to an issuer with no sector — different gaps
calling for different work — and states that an unmapped holding is one the
system cannot speak about, not one that is unaffected. Institutional shows
opposing mechanisms and that **all ten relationships are unsized**. Regulator
sees coverage, acquisition health, scope split, unresolved references and open
collection gaps.

### Targets: one met, two short and not padded

| | plan | now |
|---|---:|---:|
| issuers | 20 | **20** |
| facilities | 20 | **1** |
| relationships | 50 | **10** |

A facility record needs a source naming the site, its operator and its
location; the corpus holds one such document. Nineteen more from general
knowledge would be exactly the uncited rows the loader exists to refuse.

### The gate

34 labelled documents of 600, one labeller of two, no locked split. Three
slices are below the minimum size and now report `unevaluated`, which **fails**
rather than being skipped. `--release-check` exits nonzero; report-only exits
zero.

Precision is computed over predicted links with extra incorrect links counted
against it, recall keeps abstentions in its denominator, each field is gated
separately, and the look-ahead and adversarial checks must have actually RUN —
a zero passed as an argument is a claim, not a result.

### Two bugs only a full run could find

`CREATE TABLE IF NOT EXISTS` never adds a column to an existing table, so the
live store lacked `sequence`/`activity`/`deadline` and stall detection was
quietly inoperative on every existing store. Additive migration now runs on
every open.

And `getattr(source, 'kind', None)`: a fetcher is handed whatever the caller
calls a source, and a test stub need not carry every field of the full record.
