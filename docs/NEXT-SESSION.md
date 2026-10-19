# Next session — SERAPH

Updated 2026-10-17 after batch **T04 · T05 · T06 · T13 · T07 · T08 · T09**,
then the **news-intelligence plan** (NI00–NI15 work; its own ledger is
`docs/NEWS-INTELLIGENCE-IMPLEMENTATION.md`).
The T00–T03 batch is summarised in
`docs/evidence/T01-T03-REPRODUCTIONS-2026-10-16.json`.

## Done in this batch

| Ticket | Behaviour now possible |
|---|---|
| **T04** (authorization half) | A `Principal` is a snapshot, never standing authority. Revoked grant, revoked session, revoked membership, disabled user and expired session all deny; `visible()` revalidates **once** for a 50-resource list. |
| **T05** | Each Hawkes window's counts are pooled from **that window's** member set, and every row carries a `WindowManifest`. A window whose manifest does not describe its counts is refused, not emitted. |
| **T06** | The live loop **invokes the risk engine**. Decisions are keyed by timestamp: ordered, idempotent, each vintage assimilated exactly once, each producer gated by declared cadence and five separately-stored times. |
| **T13** (+T10/T11 partial) | **Real sourced news reaches the real globe.** 30 RBI stories place India and Mumbai on the original Three.js globe, beside the fabricated layer, in a different palette, with click-through to real headlines and both timestamps. |
| **T07** | A decision, its checkpoint, the advanced head and its outbox events commit in **one transaction**. Crash injected at all four writes leaves nothing; a replay returns the same logical decision. A lifecycle says which state the runtime is in and why it is not publishing. |
| **T08** | A live decision reaches the screen **labelled for what it is**. `live`/`replay`/`demo` is chosen, never fallen back to; the latest score and the worker's health are separate facts; an outage never re-dates the last score. |
| **T09** | Acquisition went from **3 RBI feeds / 30 stories** to **6 sources across 3 jurisdictions / 116 stories**. SEBI, the US Federal Register and USGS are registered and polling; Washington D.C. now appears on the globe as a real foreign origin. |

## Evidence

- `docs/evidence/T04-AUTHZ-FRESHNESS-2026-10-16.json`
- `docs/evidence/T05-BASKET-SELECTION-2026-10-16.json` — **465 of 473** windows had different pooled counts; terminal-basket selection inflated contributors ×1.41 and negative events ×1.42; Δn up to **+0.0324** against a corpus `n` of mean ≈0.108.
- `docs/evidence/T06-EQUIVALENCE-FULL-2026-10-17.json` / `-1530-` — **5,361 archive sessions under both decision policies, 0 disagreements**.
- `docs/evidence/T13-NEWS-TO-GLOBE-2026-10-17.json` + `T13-GLOBE-BROWSER-2026-10-17.jpg`
- `docs/evidence/T07-DURABILITY-2026-10-17.json`
- `docs/evidence/T08-CURRENT-READER-2026-10-17.json`
- Decisions: **DR-08** (Hawkes membership policy), **DR-09** (intraday process clock).

## News intelligence (separate plan, separate ledger)

`docs/SERAPH-NEWS-INTELLIGENCE-DEVELOPMENT-PLAN-2026-10-17.md` is a
feature-specific plan with its own ticket set (NI00–NI18). What works now, on
the pilot store (`prototype_runs/news-intelligence-pilot.sqlite`, 200 stories,
11 feeds, 8 publishers, 181 eligible events):

**real news → interpretation → inferred sector impact → globe → clickable
evidence**, end to end, in the ordinary Streamlit flow:

- a US anti-dumping determination on an Indian product is classified
  `trade_remedy_determination`, its **legal stage** is read from the
  instrument (`consultation` → `announced` → `adopted` → `effective`), and its
  **subject origin** comes from the Federal Register's documented
  `"<Product> From <Country>:"` title form;
- direction is **role-based and stage-gated** — only an adopted determination
  or an issued order establishes a measure, and `exporter` is adverse while
  `domestic_producer` is favourable;
- the sector panel shows `steel · export, operation · adverse for this sector
  · size unknown · 8 unsized relationship(s)`, and clicking it opens all 8
  source documents;
- the globe carries five layers — origins, subjects, mentions, affected and
  documented paths — beside the preserved FABRICATED preview.

See the ledger for the defect-by-defect record. The ones worth knowing:
sector impacts were computed from the *displayed page* (a documented steel
exposure vanished); real evidence was captioned FABRICATED; a *preliminary*
determination was read as final (a false adverse signal); places had no
aliases, so `"People's Republic of China"` matched nothing; an earthquake
epicentre was labelled a city.

**Still not true there:** three RBI feeds plus SEBI, the Federal Register and
USGS are not world coverage; 13 of 28 remedies name countries the curated
registry does not hold; four exposure edges are a pilot, not a transmission
model; and no claim here is a measured loss or evidence of predictive skill.

## Defects found by running on real data, not fixtures

| Where | What |
|---|---|
| news resolution | the mention **"India" resolved to the RBI *entity*** — substring matching let a common word inside a longer name capture a mention. Now a contiguous whole-token run with a two-token floor. |
| news extraction | a **speech venue was recorded as an *affected* place**. Located records are now `mentions` with the role explicitly not established. |
| current reader | a decision stamped after now was reported as **"-340 min old"** and allowed through. Now refused as a clock or data defect. |
| market clock | `next_open` took the day's **first** window only, so during the lunch gap of a two-window special session it reported the market shut until the next day. |
| T06 harness | the first `standard_1530` equivalence run reported 449 disagreements; the cause was the harness letting `InferenceSession` build its own default clock, comparing two policies. |
| news acquisition | **SEBI parsed 30 items with zero usable dates** — its `pubDate` is `16 Oct, 2026 +0530`, a real date in a format RFC-822 does not cover. A comma was discarding an entire market regulator. |
| news acquisition | **PIB carries no date element at all** — `<title>` and `<link>` only. Rejected, with the reason recorded rather than dropped from the plan. |
| news acquisition | USGS times are epoch **milliseconds** (read as seconds: the year 57000); GDELT's `seendate` is 15 or 16 characters and pinning one length discarded every live timestamp. |

## Commands

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/python.exe scripts/run_live.py --status        # reads only
.venv/Scripts/python.exe scripts/run_live.py --once --replay # bounded wait
.venv/Scripts/python.exe scripts/verify_t06_equivalence.py --start 2005-01-01 --end 2026-12-31
node tests/js/news_layer_harness.mjs && node tests/js/bridge_harness.mjs
.venv/Scripts/python.exe scripts/build_implementation_status.py
```

## What is still NOT true, stated plainly

1. **No live feed.** The durable path, the engine-in-the-loop and the current
   reader have never run against a real tick stream. Every pass so far is a
   replay or a fixture, and the lifecycle correctly sits in `degraded`.
2. **No live pillar producer.** The loop calls the engine on every bar close,
   and `NullProducers` returns a *structural* absence for all three pillars,
   so a live tick produces no CSRS.
3. **No exposure edge is curated**, so the globe's **paths** layer is empty
   and browser acceptance 2 (foreign origin → evidenced Indian exposure) is
   unmet. Both endpoints now exist as real nodes — Washington D.C. and
   Mumbai — but the evidenced relationship between them does not, and nothing
   is invented to fill it.
4. **The corrected Hawkes rows are not persisted** — the source database is
   read-only, so `--write` needs the research instance on 5434.
5. **Engineering completion is not predictive validation.** The original
   advance-warning claim remains unestablished.

## Next

**T11/T12 — the extractor's vocabulary is RBI-shaped.** Broadening the sources
made this visible: **10 of 12 visible events now classify as `other`**,
because the classifier knows monetary and banking prose and does not know
trade-action, enforcement or seismic language. That is the single highest-value
next fix, and it is now measurable against a real multi-source corpus.

**T10 remainder — assets and exposure edges.** 5 places, 1 entity and 5 source
locations are curated. An exposure edge needs a documented, citable
relationship; until one exists the globe shows origins and mentions only,
which is the honest state and is why browser acceptance 2 is still unmet.

Also worth doing while it is cheap: **USGS already supplies its own
coordinate**, parsed and carried by the adapter but not yet used to place a
node. That is the one source where geography comes from the source rather than
the registry, and it would put a real physical-hazard node on the globe
without any curation at all.

Then **T14** (three role journeys through the actual UI), **T15** (operations,
delivery transport, backup/restore) and **T16** (prospective ledger).

### Also unblocked, out of sequence

**FIX05** is a normal task now: the owner recorded the FR35 decision (two
epochs for Table B, six-epoch kept separately as Table C) in
`docs/decisions/DR-05-2026-10-16-fr35-table-b-scope.md`. Parameterise
`configuration_list()` with an explicit `table_b_scope`, add Table C, replace
the xfail in `tests/test_fr35_ablation_design_pins.py` with a real assertion,
and commit `preregistration.json` **before** any AUC is computed.


---

# Batch 2026-10-17 (evening) — NI11/NI12/NI16 and FIX05

## What changed

**The exposure registry stopped being the bottleneck.** With 32 recognised
trade remedies and four curated edges, only five reached a sector — the
pipeline could read a determination correctly and had nowhere to send it.
Three more edges were curated (chemicals, aluminium, agriculture), each cited
to a first-party Federal Register document **read out of the store** by
`scripts/curate_trade_remedy_exposure.py` rather than transcribed, so a
mistyped reference is impossible and an edge whose document is not held is
refused. Impacts went 5 → **20**, across five sectors.

**The live channel was broken by real data, and is fixed.** One ordinary poll
brought 70 new stories and every subsequent read of the store raised:
`first_seen_at … precedes published_at … a source cannot be read before it
publishes`. The Federal Register places documents on public inspection and
schedules publication days ahead, so a document held today carries a future
publication date. 44 rows in the pilot store are of this kind. The guard was
kept — its real target is a back-filled `first_seen_at`, which is hindsight
dressed up as information the system held — and given the one fact that
separates the cases, which exists only at acquisition. See the ledger.

**`other` was never an extraction failure.** 132 of 263 events classified as
`other` and that had been read as an extraction problem for the whole of this
work. The Federal Register feed carries the entire US federal daily register:
polar bears, fishery councils, OMB paperwork. Relevance is now a separate
question from classification, and on that split the in-scope unclassified
count is **16 of 132**, 13 of them Hindi items abstaining by design.

**FIX05 is implemented.** The owner's DR-05 decision (Table B = two pre-Hawkes
epochs, six-epoch run retained as Table C) is in the code, the hash and the
tests. The long-standing `xfail` is retired because the question was answered.

## Numbers, measured not estimated

| | before | after |
|---|---|---|
| eligible events | 206 | 263 |
| trade remedies recognised | 32 | 38 |
| sector/entity impacts | 5 | **20** |
| sectors reached | 2 | **5** |
| exposure edges | 4 | **7** |
| in scope / received-but-not-relevant | — | 132 / 133 |
| in scope and unidentified | 132 (unsplit) | **16** (13 Hindi) |
| in scope, English, unidentified | 23 | **3** |
| scientifically unresolved tickets | 1 | **0** |

## Defects found by checking output rather than counting it

1. **"Scheduling of Full Five-Year Reviews" → `expired`.** A sunset review
   being *scheduled* is the proceeding that decides whether an order
   continues, published while it is in force; `expired` asserts the opposite.
   The first fix was a negative lookbehind and did not work — the Register
   writes "Scheduling of **Full** Five-Year Reviews" and `re` has no
   variable-width lookbehind — and the rule itself was wrong, so `expired` now
   needs explicit lapse wording.
2. **A revocation carried no sign.** Direction was gated on
   `adopted`/`effective`, so the clearest favourable trade-remedy outcome
   there is read identically to an opened investigation. Repealed/suspended is
   now `favourable` for an exporter, `adverse` for a domestic producer. A
   *rescission of an administrative review* is deliberately **not** treated as
   relief: it discontinues the proceeding and leaves the duty in place.
3. **"Advance Traveler Information for Rail" → `logistics_disruption`.** The
   rule keyed on bare transport nouns, so any document mentioning a railway
   was a disruption of one.
4. **A Hindi PIB release about India ruled out of scope.** The Hindi
   interpreter abstains, so no Indian place resolved — which hid a declared
   coverage gap behind a relevance label. An Indian publisher is now a basis
   in its own right; a US publisher's jurisdiction explicitly is not, or the
   filter would admit everything.
5. **Two tests of mine encoded defects** and are corrected in place with the
   reason, not quietly rewritten: the Table B stage expectation, and a
   logistics case that was a bad discriminator.

## Verified in the browser, not in the payload

`scripts/verify_news_sectors_browser.py`, ordinary Streamlit flow, read-only
store copies, no payload injection:

```
scope_line: "132 in scope · 133 received but not about this system
             (carried and linked, never deleted) · 16 in scope and unidentified"
scope_reason_labels: 56   sectors_named: 5
forthcoming_labels: 31    government_links: 1
```

Evidence: `docs/evidence/news-intelligence/ni12-sector-edges.json`,
`ni16-relevance-and-enforcement.json`, `sectors-and-forthcoming.json`,
`sectors-and-forthcoming.png`.

## What remains

**Owner's, not mine:**

- **DR-05 step 5** — commit `preregistration.json` **before the first AUC**.
  Deliberately not scripted: pre-registration exists so a person fixes the
  design before seeing a result.
  `python -c "from seraph.validation.preregistration import commit; print(commit())"`

**News plan (NI):**

| Ticket | What is left |
|---|---|
| NI08 | Official document bodies. Only ~20 of 278 stories have bodies; the rest are headline-only, which caps what interpretation can assert. Needs the redistribution terms actually read, per source — `may_store_full_text` is `False` everywhere on purpose. |
| NI10/NI12 | More cited edges. 7 against the plan's pilot target of 20 issuers / 20 facilities / 50 relationships. This is still the binding constraint on inferred impact; the extractor is ahead of the registry. |
| NI13 | Energy, power, IMD, pharma, China/EU source pilots. |
| NI14 | Evaluate optional NLP/LLM extractors against the deterministic baseline — including Hindi, which would retire the 13 abstentions. |
| NI17 | Frozen extraction/impact benchmark and release gates. |

**Market plan (T):** T14 (three role journeys), T15 (operations, backup and
restore), T16 (prospective ledger), T18 (release gate).

**Operational, not code:** the poller is not running as a service. One
`python scripts/run_news.py --once` is what brought in the 70 stories that
exposed the forthcoming-publication bug; `python scripts/run_news.py` polls on
the registered intervals. Until it runs continuously, "continuously updated"
is a capability rather than a state.

## Things worth not relearning

- `fed_press` reporting `new=0` is **correct**: it holds 20 stories and the
  server answers 304 Not Modified against a stored ETag. An earlier reading of
  that line as a dead source was wrong.
- The suite genuinely takes ~20 minutes; `tests/contract/test_ct7_simulator_consistency.py`
  alone is ~190s. It is not hung.
- Heredocs mangle backslashes and quotes in this environment. Write a patch
  script to the scratchpad and run it with `-I`.
- `sector:` targets terminate in the sector panel, not on the globe, because a
  sector is not a place. A thin arc count on the globe is the design, not a
  missing feature.


---

# Batch 2026-10-18 (early) — FIX05, and closing the 14 skipped tests

## FIX05 — the last `scientifically unresolved` ticket

The owner's DR-05 decision (Table B = the two pre-Hawkes epochs, six-epoch
RMT/Hamilton run retained as Table C) is implemented across steps 1–4 in one
change, because the scope, the hash and the test are only sound together.

```
two_epoch  rows=26  tables={'A': 14, 'B': 6, 'C': 6}  folds={'A': [4], 'B': [2], 'C': [6]}
six_epoch  rows=20  tables={'A': 14, 'B': 6}          folds={'A': [4], 'B': [6]}
hash two_epoch d12ed87f9a9e1f60…   hash six_epoch 68cea514cfdc655f…
```

`configuration_list(*, table_b_scope)` has **no default** — a `TypeError`
without it, a `ValueError` naming DR-05 on an unknown value — because the fold
count is inside the pre-registration hash, so a caller that inherits the scope
can produce a result under one reading and have it read as the other. SPEC
FR35's "20 configurations" is preserved as A + B; Table C is additional, not a
renumbering. `PRE_HAWKES_EPOCHS` is reached by a code path for the first time.

The long-standing `xfail` is retired **because the question was answered**, not
because the marker was inconvenient — DR-05 was explicit that this distinction
mattered. The diagnostic test that recorded the contradiction is kept, inverted
to guard the resolution: if Table B ever stops being built from
`PRE_HAWKES_EPOCHS` without DR-05 being revisited, it fails.

**Step 5 is the owner's and is deliberately not scripted.**
`preregistration.json` must be committed by a person before the first AUC —
a script writing it unprompted defeats what pre-registration is for.
`commit()` already refuses to overwrite.

## The 14 skipped tests → 4

Docker was simply not running. But starting it was not enough, and finding out
why took longer than it should have:

**`DEFAULT_DSN` could never authenticate.** `bootstrap.py` hardcoded
`postgresql://seraph:seraph@localhost:5434/seraph_research`; compose sets
`POSTGRES_PASSWORD: ${SERAPH_DB_PASSWORD:-change-me-locally}`. Two copies of
one default in two files, drifted. Following AGENTS.md §7 produced
`InvalidPasswordError` and a message telling you to run the command you had
just run. The default is now assembled from the same variables compose reads,
and a password is no longer hardcoded in a versioned source file.

**The skip reason named a cause it had not established.** The probe caught
every exception and reported "TimescaleDB not reachable". An auth failure, a
wrong port, a missing database and a stopped container are four different
problems and three are not unreachability. It now carries the real error and
names `SERAPH_TEST_DB_DSN` / `SERAPH_TEST_TOKEN`, with "`docker compose up -d`
alone is not enough" stated outright.

**A misconfigured opt-in printed an INTERNALERROR traceback.** Setting
`SERAPH_TEST_DB_DSN` to something unusable let the exception escape
`pytest_configure`, so a wrong password looked like a broken harness. Now a
one-line `pytest.UsageError`. The guard's behaviour is unchanged; only its
reporting.

With the guard satisfied: **98 passed, 0 skipped** across
`test_ct1_ingestion_idempotency`, `test_c2_macro_ingestion`,
`test_c5_hawkes_writer`, `test_fix06_evaluation_identity`.

## Two things I got wrong, recorded

**I improvised a test database the project already had tooling for.** I created
`seraph_test_ct` inside the research container before finding
`docker-compose.test.yml` + `scripts/provision_test_db.py` — tmpfs, own port,
own container, three independent refusals. Theirs is better on every count. I
re-ran against it (98 passed again) and **dropped mine**; `seraph_research` is
the only database in that container again. *Look for the provisioning script
before writing the setup by hand.*

**One of my tests depended on the wall clock.** `test_syndication_groups_read_a_
forthcoming_story` hardcoded `visible_at="2026-10-18T00:00:00+05:30"`, which
was comfortably in the future when written and went stale when the date rolled
over mid-session — the ingested story's `first_seen_at` is `_now()`, so it
sorted after the cutoff and the query returned nothing. It now takes the cutoff
from the story the store actually recorded. It also called `stories()` while
claiming to test `syndication_groups()`, which is the line that actually raised
in the original bug; it now calls the latter and checks the withheld case too.

## Database state — read `docs/DATABASE-STATE-2026-10-18.md`

Bringing compose up removed an older **stopped** container (`seraph-timescaledb`)
predating the source/research split. Nothing running was stopped and nothing
was deleted: `seraphvarya_seraph_pgdata` still holds a complete 9.2 GB PG 16
directory, verified by a read-only mount. But **nothing serves 5433 now**, and
OPERATIONS.md §1 says the source database is never started from this repo, so
no service was added for it. Restore recipe is in that document; the password
must come from outside the repo.

**One trap closed structurally.** Both compose files defaulted to the same
project name, so compose reported the research container as an "orphan" of the
test project and suggested `--remove-orphans` — which **would have deleted it**.
`docker-compose.test.yml` now declares `name: seraph-test`. It applies on the
next recreate; not applied here because a suite run was using the instance.

## Suite, definitive

```
1407 passed, 4 skipped in 1250.26s (0:20:50)     exit 0
```

Against the canonically provisioned test database. Previous run was
`1397 passed, 14 skipped` — 12 of those skips were the DB-dependent tests,
which now run; 10 extra passes come from them plus the new tests in this batch.

The 4 remaining skips are environmental and named: `test_ct3_jump_sufficiency`
needs `scripts/backfill_intraday.py` run first. Nothing is skipped for a
reason the suite cannot state.

Evidence: `docs/evidence/SUITE-2026-10-18-FINAL.json`.

---

# Batch 2026-10-18 (NI08) — the rights question, answered

`may_store_full_text` was `False` for every source, capping interpretation to
headlines: ~20 of 278 stories had bodies, and the Federal Register adapter was
extracting each document's `abstract` only for the store to discard it.

The terms are now **read per source** — `docs/decisions/DR-10-2026-10-18-source-text-rights.md`
carries the quotes and citations — and the answer differs by source, which is
why a blanket answer would have been wrong.

**Permitted:** `federal_register`, `federal_register_india` (17 U.S.C. §105),
`usgs_earthquakes` (USGS public domain), `pib_releases` (PIB's own policy
needs no prior approval), `fed_press` (already).
**Refused:** three RBI feeds ("© Reserve Bank of India. All Rights Reserved" —
no grant) and `sebi_press` (permitted only after a permission that has not
been requested).

Refusals now record "terms REVIEWED and REFUSED" with the reason, not "NOT
reviewed" — SEBI is one email away rather than an open question.

**Two facts checked rather than assumed:** the extractor does use bodies
(`text = f"{title}. {body}"`), and old abstracts cannot be recovered because
`observations.raw` is gated on the same flag — refused sources never had their
bytes kept. Bodies therefore accrue forward only, 20/278 -> 22/280 and
climbing.

**Retaining bodies is not a uniform improvement**, measured on 34 real
documents: 9 interpreted differently, of which **two were regressions**, both
fixed — PRA boilerplate making `action=decrease`, and a *Final Debarment
Order* read as `proposed` because its abstract narrates the preceding
proposal. The latter is the third instance of one family (after "Postponement
of Final Determination" and "Scheduling of Full Five-Year Reviews"), so it is
now a named rule: a finality marker in the **title** outranks a pending stage
found only in the **body**.

A real gap surfaced too: the stage rule matched `propose/proposes/proposed/
proposal` but **not `proposing`**, which is how a Federal Register abstract
almost always phrases it.

## Suite

```
1433 passed, 4 skipped in 913.22s (0:15:13)     exit 0
```

Up from 1407. The 4 skips are environmental and named (`backfill_intraday.py`).
Evidence: `docs/evidence/news-intelligence/ni08-source-text-rights.json`.

## What remains

**Owner's:** DR-05 step 5 (commit `preregistration.json` before the first
AUC); port 5433 not served (see `docs/DATABASE-STATE-2026-10-18.md`); and, if
wanted, one email to SEBI to unlock their full text.

**News:** NI10/NI12 more cited edges (7 against a pilot target of 50 — still
the binding constraint on inferred impact), NI13 further source pilots, NI14
NLP/LLM evaluation incl. Hindi (would retire the 13 abstentions), NI17 frozen
benchmark and release gates.

**Market:** T14 role journeys, T15 operations/backup/restore, T16 prospective
ledger, T18 release gate.

**Operational:** the poller still is not running as a service.
