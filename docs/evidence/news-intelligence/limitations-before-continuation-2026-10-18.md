# What the SERAPH news channel does not do

**Date:** 2026-10-18, updated after the acquisition/interpretation batch.
Counts are generated from the running system by
`docs/evidence/news-intelligence/acceptance-state.json`, not typed by hand.

Every claim below was checked against the running system, not inferred from
the code. Where a number appears, it was measured. This document exists so
that nobody has to discover these by being surprised by them.

---

## 1. It is a pilot, not broad coverage

**11 registered endpoints from 8 publishers**, ~280 stored stories. Two of
those endpoints are *single fixed historical documents* under monitoring
(a MOFCOM rare-earth announcement, a Tata Steel facility release) — they watch
one document for changes and are not ongoing feeds for their publishers.

Not covered at all: Indian exchange filings (BSE/NSE), Indian trade
instruments (DGFT, CBIC), most sector-specific sources, and broader
foreign-policy channels. The `mofcom_policy_listing` adapter exists in code
and is **not registered**, which is a concrete example of "implemented
adapter" not meaning "active coverage".

## 2. Freshness depends on a process somebody has to run

Launching Streamlit alone does **not** fetch. `launch_prototype.ps1` starts a
supervised worker that reconciles source registrations, catches up every
source once, then polls on each source's own schedule.

The console now separates four facts that used to blur into "current":
`projected_for` (screen), `newest_first_seen_at` (article), `stale` (source
past its declared policy), and `worker.state` (whether anything is fetching).
A stopped worker is reported in the banner, the sector panel and the detail
card.

**It is still periodic polling, not streaming.** A 30-second screen refresh is
not 30-second news.

## 3. Some downtime is unrecoverable, by the source's nature

Only the two Federal Register endpoints accept a publication-date range and
can be backfilled exactly. Every other feed exposes its latest ~30 items: if
more than that published during an outage, the earlier ones are **gone, not
late**. The gap is reported with that wording; it cannot be fixed by polling.

## 4. Interpretation is deterministic rules over mostly titles

Bodies are retained for 5 of 11 sources (DR-10), and only **22 of 280**
stories currently have one, because rights were refused for RBI and SEBI and
bodies accrue forward only. Those bodies are feed-supplied *abstracts*, not
full documents; fetching complete documents is a separate unanswered question
about volume and per-page terms.

No PDF or table extraction. No product scope, exceptions, affected-party or
instrument-relationship extraction. Measured on 34 real documents, retaining
abstracts changed 9 interpretations — **two of them for the worse** before
they were fixed, so more text is not automatically better.

## 5. Hindi is keyword matching, not comprehension

There is no English PIB RSS at that endpoint (checked across three `Regid`
values). The Hindi rules read a handful of nouns. They do not parse grammar or
negation and cannot tell a proposal from a decision, so **no Hindi event ever
claims `confirmed_statement`** and each carries a caveat naming the rule set.

4 of 42 received PIB items are market-relevant; the rest are correctly left
unclassified. 14 in-scope events remain unidentified, 11 of them Hindi.

## 6. Impacts are qualitative hypotheses, not estimated losses

**10 cited exposure edges, 8 sectors, 2 entities, 1 facility** — against the
plan's pilot target of 20 issuers, 20 facilities and 50 relationships. This is
the binding constraint on inferred impact; the extractor is well ahead of the
registry.

**Every edge is unsized.** A US proceeding covering a product "From India"
establishes the import trade exists. It is not a revenue share, not a company
exposure and not a loss. Directions are qualitative and role-based. An unmapped
firm is **not** a firm with zero risk — it is a firm we have no mapping for.

## 7. The accuracy gate does not pass

Run `python scripts/run_news_gate.py`. All three measured slices are at 100%
and all thresholds are met — and `gate_passed` is **false**, because:

* the corpus is **34 documents of the 600** the plan specifies,
* across six groups that each fall far short,
* with **no locked chronological test split**,
* labelled by **one** reviewer of the two required, and not a human one.

No inter-annotator reliability is claimed. The measured rates are a regression
and sanity instrument; they are **not evidence of real-world accuracy**, and
the gate is written so that perfect scores on an insufficient corpus cannot
pass it.

## 8. Nothing here reaches CSRS

The news channel (F2) is separate from the market pillar channel (F1) that
produces CSRS. Different sources, different units, separate evaluation. **No
news signal enters CSRS or the fusion weights**, and nothing in this channel
is a probability of financial loss.

## 9. Known-and-left

- **Role-specific news intelligence (NI18/P2)** — connecting news to a user's
  documented portfolio, professional scenarios and regulator review workflows
  is not built. Role navigation alone does not complete it.
- **`sebi_press` full text** is one email away: SEBI permits reproduction
  after permission is obtained, and that permission has not been requested.
  Fabricating it was not an option.
- **Port 5433** — the 9.2 GB source corpus is intact on its volume but no
  container serves it. See `DATABASE-STATE-2026-10-18.md`.
- **DR-05 step 5** — `preregistration.json` must be committed by a person
  before the first AUC. Deliberately not scripted.
- **4 skipped tests** need `scripts/backfill_intraday.py` run first.

---

## How to check any of this yourself

```bash
python scripts/run_news.py --status          # coverage and per-source health
python scripts/run_news.py --backfill        # gaps, recoverable and not
python scripts/run_news_gate.py              # the accuracy gate, honestly
python scripts/verify_news_sectors_browser.py [--simulate-dead-worker]
```


---

## Update — what changed, and what is still short

**Acquisition is now separated from display.** The 30-second timer re-projects
stored data and touches no network. Acquisition is *requested*, coalesced in
the store across browser tabs, rate-limited, and served by the worker. Before
this, every open tab forced all sources every thirty seconds.

**Coverage: 17 sources, 453 stories.** Indian exchange filings (NSE
announcements, NSE circulars, BSE notices) were absent and are now covered,
along with USTR, Fed speeches and EC news.

Still **uncovered**, each probed and recorded with its reason: DGFT (403),
CBIC / MOSPI / IMD (certificate verification fails — verification is **not**
disabled to work around it), POSOCO (502), CEA (not a feed).

**NSE announcement titles are the filing entity only.** The subject is in the
body, which is not retained. A filing therefore resolves to its issuer and
produces **no impact and no direction** — "JSW Steel filed something" must
not become "adverse for steel".

### Coverage targets: one met, two short

| target | plan | now |
|---|---:|---:|
| issuers | 20 | **20** |
| facilities | 20 | **1** |
| documented relationships | 50 | **10** |

The two shortfalls are **not padded**. A facility record needs a source naming
the site, its operator and its location; the corpus contains one such document
(the Tata Kalinganagar release). Adding nineteen more from general knowledge
would produce exactly the uncited rows the registry loader exists to refuse.
The same applies to relationships: each of the ten cites a document in the
store.

### What is sized

**Nothing.** All ten relationships are unsized, and the institutional view
states that explicitly. A direction without a size supports a question, not a
position.

### Temporal semantics are stricter now

`adopted` is no longer treated as in force — a final determination is a
decision, and the measure begins when it takes effect. A measure effective in
2099 does not apply today. Applicability is evaluated against the **requested
decision time**, so a replay no longer sees later measures. Supersession ends
a measure that a later instrument modifies.

### The gate still does not pass

34 labelled documents of the 600 required, one labeller of two, no locked
chronological split, and three metric slices below the minimum size — so
`link_precision`, `field_numeric` and `field_unit` report **unevaluated**,
which now fails rather than being skipped.

`python scripts/run_news_gate.py --release-check` exits nonzero. That is the
correct result and the command a pipeline should run.
