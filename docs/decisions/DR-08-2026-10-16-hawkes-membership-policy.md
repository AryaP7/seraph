# DR-08 — Which basket governs a Hawkes refit window

**Date:** 2026-10-16
**Raised by:** T05 / independent audit finding **R11** — the Hawkes writer's
per-window basket was metadata only; it did not govern the count stream.
**Status:** decided — **`fixed_at_fit_cutoff`** adopted; the other two policies
implemented and selectable so the choice can be audited.

---

## The finding, stated plainly

`scripts/write_hawkes_production.py` did three things in the wrong order:

1. resolved the universe **once**, at `max(ts)` of `intraday_bars`;
2. loaded **one** pooled jump stream from those symbols and sliced it for every
   refit window;
3. separately resolved `point_in_time_members(pool, window_end)` per window and
   wrote **that** into the artefact.

So the artefact declared a 2016 membership beside a number computed from the
2026 membership. The basket was a label on the row, not a description of the
input. FIX07 had already corrected the *metadata* (audit finding A09); R11 is
the observation that the correction never reached the data path.

Two error directions follow, and in this corpus they are very different sizes:

| Direction | Mechanism | In this corpus |
|---|---|---|
| **Survivorship** | a symbol that left the universe is never loaded, so its events are missing from windows where it *was* a member | **zero symbols** — every intraday-covered symbol is in the terminal basket, because the intraday pull was itself scoped to today's universe |
| **Composition inflation** | a symbol that joined late is loaded for *every* window, including ones long before it joined | **52 of 91** intraday-covered terminal-basket symbols were not in the 2005 basket |

The survivorship count being zero is a property of how the intraday backfill
was scoped, not a property the code may assume. The corrected loader reads the
union of every basket that ever existed, so the day the intraday universe is
widened the right thing happens without another correction.

## The question this record answers

A rolling window spans many sessions and the universe rebalances half-yearly,
so "the window's basket" is not well defined until someone defines it. Three
policies are coherent and they disagree:

| Policy | Membership used | Argument for | Argument against |
|---|---|---|---|
| `fixed_at_fit_cutoff` | the snapshot in force at the window's **last** session, applied across the whole window | it is what an operator standing at the cutoff actually knows; composition is constant inside the window, so a change in `n` is a change in clustering and not a change in who was counted | a symbol that joined mid-window has its pre-membership bars counted |
| `fixed_at_window_start` | the snapshot in force at the window's **first** session | no pre-membership bars at all | scores *today* using a basket up to `window_days` sessions stale — for a 500-session window, two years out of date |
| `day_varying` | each session uses the snapshot in force **on that session** | historically the most faithful attribution | the exposure denominator moves inside the window, so `n` mixes a clustering change with a composition change; the pooled series is not comparable along its own length |

## Decision

**Adopt `fixed_at_fit_cutoff`.** Three reasons, in order of weight:

1. **It is the already-adopted policy.** FIX07's `point_in_time_members(pool,
   window_end)` is a fit-cutoff basket. The plan's instruction is to match the
   adopted policy rather than introduce a fourth thing; this makes the data
   path agree with the metadata that was already being written, which is the
   whole point of T05.
2. **It is causally available.** The basket in force at the cutoff is known at
   the cutoff. Nothing from after the decision time enters. `day_varying` is
   also causal; `fixed_at_window_start` is causal but needlessly stale.
3. **It keeps the window interpretable.** The branching ratio is the quantity
   that reaches C8. Under `day_varying` a move in `n` can come from
   contagion or from the basket changing, and nothing in the output separates
   them. That ambiguity is worse than the known, bounded cost of counting a
   recent joiner's earlier bars.

**The known cost is stated, not hidden.** Under this policy a symbol that
joined at the last rebalance contributes its bars for the whole trailing
window. For a 500-session window and a half-yearly rebalance that is at most
roughly one window's worth of pre-membership bars for the newest ~3% of names.
The manifest records the policy on every row, so the cost is attributable.

## What the decision is not

- It is **not** a claim that `n` is unchanged by the correction. It changes;
  `scripts/compare_hawkes_basket_selection.py` measures by how much, and
  `docs/evidence/T05-BASKET-SELECTION-2026-10-16.json` records the result.
- It is **not** a claim about forecasting skill. T05 repairs an input; the
  original advance-warning claim remains unestablished either way.
- It is **not** permission to overwrite the existing E6 rows. Those were
  computed from the terminal basket and are evidence of what was run. The
  corrected run writes to `scope_id = 'basket_v2'`; the pre-T05 rows stay under
  `scope_id = ''`. Overwriting them needs `--namespace legacy-overwrite`
  spelled out on the command line.

## Implementation

| Piece | Where |
|---|---|
| Snapshot history as a type, `members_at(date)`, `union` | `seraph/ingestion/hawkes_universe.py` — `BasketTimeline`, `BasketSnapshot` |
| Per-symbol events on one grid, pooled per member set | `seraph/pillars/hawkes/basket_stream.py` — `StreamBuilder`, `PooledStream` |
| The three policies, as contiguous membership segments | `membership_segments()` |
| Basket digest, contributing symbols, content hash of the input rows, hash of the counts, detector version, window bounds | `WindowManifest` |
| The guard: a window whose manifest does not describe its counts is refused, not emitted | `verify_manifest()`, called in the writer before any fit |
| Tests | `tests/test_t05_hawkes_basket.py` |

The content hash is an order-independent XOR over per-session digests, so a
window's hash depends on exactly the rows inside it: a price changed inside the
window changes it, a price changed outside does not. That is what makes two
runs comparable at window granularity instead of corpus granularity.
