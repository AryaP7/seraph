# Amendment 08 — NI17's two short quotas are a corpus-rule ceiling, not a source gap

25 October 2026. Measurement and one withdrawal, not an audit. This records
why registering further news sources cannot move NI17's `non_english` and
`logistics_hazards` quotas, and withdraws a duplicate source registered
earlier the same day.

**This confirms a finding already on record rather than making a new one.**
`docs/NEXT-SESSION.md` §"NI17: the language quota cannot be met today"
already established that the corpus window is historical and that
`pib_releases` supplies 29 of the 600. What is new here is the proof of *why*
no further PIB feed exists, the measured contribution of the two sources
registered today (zero), and the withdrawal of one of them.

Nothing in the corpus rule, the category quotas, the chronological split or
the reviewer requirements was changed. The frozen corpus at
`prototype_runs/review-corpus-2026-10-25/` was read, not altered, and no
review was fabricated — its `reviews.jsonl` is still 0 bytes. Nothing was
committed.

---

## 1. The withdrawal: PIB's `Lang` parameter is inert

`pib_hindi_lang3` was registered at 2026-10-25T18:06:16+05:30 on the
assumption that `Lang=3` served a different feed from the `Lang=2` URL
`pib_releases` already polls. It does not.

Measured by sweeping the whole matrix (`scripts` probe, 2026-10-25):

| probe | result |
|---|---|
| `Lang=1` … `Lang=20` at `Regid=3` | 20 items each, **identical ordered item lists**, identical link sets, identical Devanagari titles |
| every `Regid` other than 3 (0–35, `Lang=3`) | 0 items |
| `Lang=2&Regid=3` vs `Lang=3&Regid=3`, compared item by item | 20 of 20 URLs shared; ordered `(title, url)` lists equal |

So PIB exposes exactly **one** feed through this endpoint, `pib_releases` is
already it, and the `Lang` value is ignored by the server. A second
`source_id` over the same URL polls a government endpoint twice an hour for
no new information.

**Corpus impact: none.** `export_corpus` dedupes by `(title, body)` digest
before it selects, so all 20 duplicate rows were collapsed. The non-English
documents in the store carry exactly one `source_id`, `pib_releases`. The
duplicate never reached a manifest.

**What was done.** The registration is removed from `NI17_COVERAGE_SOURCES`
in `scripts/run_news.py`, and the current-state row is deleted from the
store's `sources` table so the worker stops polling it. Deliberately *not*
deleted:

* `source_versions` keeps the registration payload at its real `known_at`,
  so the record that it was registered survives.
* The 20 observations, 20 stories, 2 `ingest_log` rows and 1 `source_health`
  row stay. Those fetches really happened; erasing them would falsify the
  acquisition record to tidy up a mistake.

The store has no retirement or deactivation mechanism — `sources` is
current state and the worker polls every row in it — so deleting that one row
is the only way to stop a source. That gap is noted, not filled here.

## 2. Why no new source can move either quota

`export_corpus` selects the **oldest 600** documents by `first_seen_at`:

```python
stories.sort(key=lambda s: (s.first_seen_at, s.story_id))
...
for index, story in enumerate(stories[:600]):
```

This is deliberate — the split policy is `first_seen chronological
300/100/200` precisely so that training never sees documents that arrived
after the test set. It is the thing that makes the benchmark honest, and it
is not a defect.

Its consequence is that **the selection window is closed and fixed in the
past.** This is not a reconstruction: the corpus was frozen earlier the same
day at `prototype_runs/review-corpus-2026-10-25/`, manifest hash
`144c8f6496d707f0…`, 600 documents, splits 300/100/200, `first_seen_at`
spanning 2026-10-16T19:38:37 → **2026-10-19T22:12:32**. Reading that manifest
directly:

| source registered today | items it supplied | documents in the frozen corpus |
|---|---|---|
| `gdacs_alerts` | 328 (+23 in a later pass) | **0** |
| `pib_hindi_lang3` | 20 | **0** |

Measured against the live store on 2026-10-25, reproducing the export rule
independently (syndication-group dedup, then `(title, body)` digest dedup,
then the chronological cut) gives the same answer the frozen manifest does —
29 non-English of 600 — which is the cross-check that the figures below are
the export rule's and not an artefact of how they were counted:

| quantity | value |
|---|---|
| distinct documents in the store after dedup | 1,960 |
| `first_seen_at` span of the store | 2026-10-16T19:38:37 → 2026-10-25T18:14:23 |
| `first_seen_at` span of the oldest 600 | 2026-10-16T19:38:37 → **2026-10-19T22:12:32** |
| non-English documents inside the 600 | **29** (required: 100) |
| non-English documents anywhere in the store | 87, all `pib_releases` |
| of those 87, first-seen after the cut | 39 — unreachable by a freeze |

Any source registered after 2026-10-19T22:12:32 contributes **zero**
documents to a freeze, however much it supplies. That is measured, not
inferred:

* `gdacs_alerts` supplied 328 items and first-saw all of them on 2026-10-25.
  Its contribution to the oldest 600 is **0 documents**.
* `pib_hindi_lang3`'s 20 items, same date: 0 documents.

Source composition of the 600 that a freeze would take today:

| source | documents |
|---|---|
| `federal_register` | 158 |
| `nse_corporate_announcements` | 131 |
| `bse_notices` | 52 |
| `nse_circulars` | 48 |
| `usgs_earthquakes` | 40 |
| `sebi_press` | 36 |
| `pib_releases` | 29 |
| `rbi_press_releases` | 15 |
| `ec_news`, `federal_register_ita` | 13 each |
| `rbi_notifications`, `rbi_speeches`, `wto_news` | 10 each |
| `ustr_press`, `fed_press` | 9 each |
| `federalreserve_speeches` | 8 |
| `federal_register_india` | 7 |
| `tata_kalinganagar_expansion`, `mofcom_rare_earth_18_2025` | 1 each |

### The two quotas, stated as ceilings

**`non_english` (needs 100).** At most 29 of the 600 frozen documents can be
non-English, because only 29 non-English documents exist inside the window.
`counts['non_english']` is tallied over *reviewed* documents, so recruiting
reviewers raises the count toward 29 and no further. **The ceiling is 29.**
This holds regardless of reviewer availability, and no reachable source
changes it, because the only non-English publisher reachable at all is PIB
and its one feed carries 20 items at a time.

**`logistics_hazards` (needs 80).** This is a reviewer-assigned category, so
its ceiling is not strictly derivable from source identity — a port or
shipping release could legitimately be categorised here. But the window
contains only one dedicated hazard feed, `usgs_earthquakes`, with 40
documents, and the feed registered to widen that coverage contributes none.
**A reviewer-independent floor of 40 from the dedicated feed; the rest would
have to come from documents reviewers categorise as logistics or hazards.**

## 3. Earlier numbers this corrects

A measurement taken earlier the same day reported 58 non-English in an
"oldest 600" window and 348 hazard documents in a "newest 600" window. Both
were taken over raw store rows without the group and text dedup that
`export_corpus` applies first, and the hazard figure was taken over a
*newest*-600 window, which is not the window the export rule uses. The
figures above apply the real rule and supersede those.

## 4. What this leaves for the owner

The remedy is a scientific decision, not an engineering one, so none of these
was taken:

1. **Accept the ceiling** and record `non_english` as 29 of 100 with this
   amendment as the reason — the quota fails, and the gate correctly reports
   it. This is already the de facto state: the corpus is frozen, its
   `gate.json` reads `gate_passed: false` / `corpus_sufficient: false`, and
   nothing done today changed that.
2. **Change the corpus selection rule** to a quota-aware or stratified draw.
   This materially alters the declared `first_seen chronological 300/100/200`
   split policy and the look-ahead guarantee that depends on it.
3. **Widen the corpus total** beyond 600 so later documents enter the window.
   Changes a declared corpus size.
4. **Re-found the store** so its earliest period already carries every
   source. This destroys the existing nine-day acquisition record and its
   first-seen history, which is itself evidence.

Option 1 changes nothing and is the only one available without an owner
decision; the gate already fails on this quota and says why.

Unchanged and still outstanding, as before: NI17 needs **two independent
human reviewers**, and no software can supply or attest that.
