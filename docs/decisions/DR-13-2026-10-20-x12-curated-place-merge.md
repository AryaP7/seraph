# DR-13 — X12: merging the duplicated curated place rows

**Date:** 2026-10-20
**Backlog:** `X12` (new finding, recorded 2026-10-19, not fixed at the time)
**Status:** implemented and verified.

---

## The conflict

Exactly two Indian states carried two place rows each:

| id | name | lat/lon | citation | children |
|---|---|---|---|---|
| `in_mh` | Maharashtra | 19.5, 76.0 | geonames.org/1264418 | `in_mh_mumbai` |
| `ntpc_state_maharashtra` | Maharashtra | — | ntpc.co.in/power-generation/coal-stations | — |
| `in_od` | Odisha | 20.5, 84.41667 | geonames.org advanced-search | `in_od_kalinganagar` |
| `ntpc_state_odisha` | Odisha | — | ntpc.co.in/power-generation/coal-stations | — |

Two rows claimed the same `(name, kind)`, so `resolve_place` correctly
abstained with `status="ambiguous"`. **The resolver was right and the data was
wrong.** The consequence was specific and bad: Maharashtra and Odisha — two of
the states where NTPC assets actually sit — could not be resolved from a
mention at all, while every other `ntpc_state_*` row (Uttar Pradesh, Bihar and
the rest) had no canonical twin and resolved fine.

## Why this was recorded rather than fixed on the day

The finding was logged with the note that merging "is a curated-data migration
with citation implications, not a normalisation fix, and it changes registry
counts". That was the right call at the time: dropping a row that carries a
citation is not a mechanical edit, and nobody had read the two citations
against each other.

## What reading them settled

The citations are not in conflict, because **they support different claims**:

* geonames is a geographic authority. It backs "Maharashtra is a state of
  India at these coordinates". That is a *place* fact.
* `ntpc.co.in/power-generation/coal-stations` backs "NTPC operates a coal
  station in this state". That is an *asset* fact — and it **already sits on
  every affected asset row**, where it belongs.

So the `ntpc_state_*` place rows were not an alternative account of the same
geography. They were a side effect of the NTPC facility mapping creating a
place to hang assets from, duplicating an asset citation onto a geographic
entity that did not need it.

## The decision

**The `in_*` rows survive.** They carry the coordinates, the geographic
citation, the non-Latin aliases, and the child places parented to them — they
are structurally load-bearing and the `ntpc_state_*` rows are not.

1. Dropped `ntpc_state_maharashtra` and `ntpc_state_odisha` from
   `places.csv`.
2. Repointed the three asset rows that referenced them —
   `ntpc_darlipali` → `in_od`, `ntpc_mouda` → `in_mh`,
   `ntpc_solapur` → `in_mh`.
3. **No citation was dropped.** The NTPC page still backs each of those three
   stations on its own asset row, and the places keep geonames. A test
   asserts this rather than leaving it as a claim here.

The other `ntpc_state_*` rows are untouched. X12 was a duplication defect, not
an argument against that namespace.

## Registry counts

| | before | after |
|---|---|---|
| entities | 22 | 22 |
| **places** | **21** | **19** |
| assets | 28 | 28 |
| edges | 64 | 64 |

Only places moved, and by exactly the two rows removed. Assets were repointed,
not deleted. Verified both in the checkout and from an installed wheel —
`verify_packaging.py` reports `curated.places = 19` in a fresh environment and
its gate is green.

## Tests

The three tests that **pinned the defect** are inverted rather than deleted,
so the fix is asserted where the bug used to be:

* `test_a_previously_duplicated_state_now_resolves` — both states resolve to
  their canonical id.
* `test_no_place_name_is_duplicated_any_more` — the duplication scan must now
  find nothing. This is the old blast-radius pin pointing the other way: if a
  duplicate reappears, this fails rather than a resolver silently abstaining
  on a state nobody checks.
* `test_the_unduplicated_ntpc_states_still_resolve` — kept as it was.

Three added, because the merge had failure modes the old tests could not have:

* `test_the_repointed_assets_sit_in_the_canonical_places` — the specific three.
* `test_every_asset_points_at_a_place_that_exists` — the general form, so the
  next curated edit cannot leave a dangling reference. That is the failure
  mode that otherwise appears only at load time, or not at all.
* `test_the_ntpc_citation_survived_on_the_assets` — no citation lost.

The count assertion moves from `== 21` to `== 19` with a note to re-derive
from the loader rather than adjust it to whatever comes out, since the point
of asserting a count is to catch a silent row loss.

631 tests pass across every module that touches the curated registry.

## What this does not do

It does not curate asset coordinates, fill the missing issuer/sector mappings,
or diversify the NTPC concentration — all of which the news audits raise
separately and none of which X12 was about.
