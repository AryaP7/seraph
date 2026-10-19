# DR-11 — Runtime state contracts: time, identity, configuration, valid time

**Date:** 2026-10-19
**Raised by:** the engineering completion audit's R02, R04, R05, R06, P03 and
P05, and verification finding X04.
**Status:** decided and **implemented** — commits `89cf8d8` (runtime) and
`44d92fa` (user-owned state).

The plan called for six separate decision records (DR-11…DR-16) before any
code. This is one record written *with* the implementation instead, because
six speculative designs followed by a divergent implementation is worse than
one record that describes what the code actually does. Every rule below is
enforced by a test named for the finding it closes.

---

## 1. Time: four instants, and which one is the cutoff

**The question.** `ServiceEvaluator` set `as_of` to the bar end. A producer
cannot emit a bar-derived estimate until the bar is complete, so
`emission_available_at` was later than the cutoff on *every* bar, the vintage
was withheld every time, the previous one carried forward and aged forever,
and the pillar never updated. Nothing failed; the score stopped moving.

**Decided.** Four instants, named and kept apart:

| instant | meaning |
|---|---|
| `input_end` | when the **world** produced the information |
| `emission_available_at` | when SERAPH could first **read** it |
| `as_of` | the **decision cutoff** |
| `now` | wall clock at computation |

`as_of` = `bar_end + DECISION_ALLOWANCE` (`engine_adapter.py`, currently 5 s).
Admission then has two separate conditions:

- `input_end > as_of` → **refused as lookahead.** Causality; the allowance
  does not relax it.
- `emission_available_at > as_of` → **withheld**, previous carried forward.

**Rejected alternative:** testing availability against `now` instead of
`as_of`. This was implemented first and the tests caught it. `now` is the tick
instant, which under replay can precede the bar timestamps entirely, so every
vintage was withheld and a 40-day-old warm-start value carried forward into a
confident-looking score. The publication gate refused to publish it, but a
score computed from stale inputs is exactly what R02 exists to prevent.

The fix belongs in the **cutoff**, not in the comparison. Both conditions stay
functions of `as_of`, which is a function of the bar end, so a replay of the
same bars reproduces the same admissions.

`DECISION_ALLOWANCE` is an **engineering default, not a measured one.** O07
measures real bar-to-decision latency; this should be set from that
measurement.

## 2. Vintage revisions: observation order, not arrival order

**Decided.** Admission sorts by `(input_end, emission_available_at)` and
refuses a vintage whose `input_end` precedes the incumbent's, recording it in
`withheld` rather than dropping it silently. A correction carrying the **same**
`input_end` is a legitimate revision and still applies.

Within one batch the sort makes arrival order irrelevant. Across `process()`
calls the incumbent in `_latest` is what is defended — which is the defect's
real shape, and what the regression test exercises.

## 3. Decision identity: `{mode}:{stream_id}:{bar_end}`

**The question.** The id was `f"live:{as_of.isoformat()}"` — no stream, no
mode — so a replay pass and a live pass over the same bar end minted the same
id (X04). Combined with payload-blind replay detection, a replay commit was
accepted as the existing live decision and reported `replayed=True`.

**Decided.** Three rules, and fixing fewer than all three leaves the hole:

1. **Minting.** `decision_id(mode, stream_id, bar_end)`. Mode is part of the
   identity, not metadata on it: a live reading and a replay of the same
   instant are different facts about the world.
2. **Content.** `commit_decision` compares `payload_hash` before declaring a
   replay. Same id + same bytes is a replay; same id + different bytes raises
   `DecisionConflict`. Idempotency is a property of content, not of a name.
3. **Scope.** `latest_decision()`, `decisions()` and `pending_events()` filter
   by `stream_id` (migration `002_decision_stream.sql`). `decision()` stays
   global **by exact id** on purpose — that lookup is how rule 2 detects a
   collision.

The id keys on the **bar end**, not on `as_of`: a decision's name should be
the bar it decided on, not the cutoff it used.

The outbox is scoped too, because a replay must not be able to emit a
production alert. Existing rows are backfilled to `'live'` rather than guessed
from the id text: a wrong stream attribution is worse than a conservative one.

## 4. Checkpoint identity: configuration is state-defining

**The question.** `restore()` validated `pipeline_version` and `calendar_id`
only, so a service rebuilt with different process noise or different fusion
weights resumed from the old filter state silently. Neither value was in the
payload, so no caller could have detected it either.

**Decided.** `config_fingerprint()` hashes everything that changes what the
*same inputs* would produce: `q_proc`, the fusion weights' artefact id, the
standardizer policy and window, declared cadence, warmup threshold,
`PILLAR_ORDER`, and each model bundle's **`manifest_hash`** — its content, not
its `bundle_id`, because an id is a label and a label can be reused over
different bytes.

- Mismatch → refuse, **naming which keys differ.** A bare "configuration
  differs" sends the operator reading source.
- Missing fingerprint → refuse. An unverifiable resume is the defect, not the
  inconvenience.
- A log level is *not* state-defining and is deliberately absent.

The bar-builder snapshot travels inside the same checkpoint payload, so filter
state, bar state and input cursor are one atomic write (R08).

## 5. Portfolio import: finiteness, conflict, valid time

**Decided.**

- **Finiteness** applies to what is **stored**, not to where it came from.
  `float()` accepts `"nan"`/`"inf"`/`"Infinity"`, and NaN then passes `< 0`
  because every NaN comparison is False. Parsed *and* derived numbers are
  checked: finite inputs can still overflow (`1e308 * 1e308`).
- **Row order is not evidence.** Quantities and values add on a duplicate
  symbol; conflicting `sector`/`isin`/`account` is **rejected**, naming both
  values, because `existing.X or accepted.X` resolved a disagreement by file
  order and the sector drives the portfolio overlay. Absence is not
  disagreement — a blank side still merges.
- **Valid time.** `current_holdings` filters `effective_at <= now`. A future
  snapshot is reported as `scheduled`, not hidden, so a staged rebalance is
  visible as staged. The clock is injectable: a test that cannot control `now`
  cannot test this.

## 6. Scenario revisions: append-only, and reviews bound to one

**Decided.**

- Assumption revisions are **rows** in `scenario_assumptions`, with triggers
  refusing `UPDATE` and `DELETE`. The old `UPDATE scenarios SET assumptions=?`
  destroyed the previous text while incrementing a counter, and the docstring
  claimed the opposite.
- A run stores its **inputs**, not only `inputs_hash`. A hash tells you two
  runs differ, not what either was.
- A review records its `assumption_version`, and optionally the exact
  `run_key` examined. Approving revision 1 must never become approval of
  revision 2 — a reviewer's name standing behind numbers they never saw is the
  failure this prevents.

Versions overwritten before the table existed are **recorded as
unrecoverable**, not reconstructed.

---

## What this record does not decide

- `DECISION_ALLOWANCE`'s value, pending O07's latency measurement.
- The generic job-lease fencing (R10/DR-14). Open, and being changed
  concurrently in `seraph/operations/jobs.py` by another session.
- Server-side identity (P01). These contracts assume a `Principal`; obtaining
  a trustworthy one is W7's work.
- Anything scientific. No threshold, weight or effect size is set here.

## Verification

`tests/test_r02_r06_runtime_integrity.py` (35 cases) and
`tests/test_p03_p05_user_state.py` (41 cases). Each test names the finding it
closes and failed before the commit that closed it.

One existing test was **updated, not deleted**:
`test_t06_engine_in_the_loop.py::test_the_decision_id_is_the_bar_end_...`
asserted the old id format. X04 changed the format, not its intent; the test
now also covers the cross-stream and cross-mode collisions the old format
allowed.
