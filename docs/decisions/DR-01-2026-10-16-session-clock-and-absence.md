# DR-01 — Session-aware decision clock, as-of pillar selection, declared absence

**Date:** 2026-10-16
**Backlog:** `FIX01`, `FIX02` (audit findings A01, A02)
**Status:** adopted and implemented
**Supersedes:** nothing. Preserves all prior evidence; the pre-change COVID
replay `77cc8a2f…` in `prototype_runs/seraph.sqlite` is untouched.

## Decisions

1. **The decision timestamp comes from a session calendar**, not a hardcoded
   15:30 IST. `seraph/market_calendar/sessions.py` holds the regular session
   (09:15–15:30 IST) and an explicit registry of deviations. Two policies:
   `session_close` (default) and `standard_1530`.

2. **Pillar inputs are selected as-of**, by information timestamp: the latest
   vintage whose τ is at or before the decision timestamp. Calendar-date keying
   is retired.

3. **A later vintage is withheld, not accepted and not fatal.** An observation
   whose τ is after the decision timestamp becomes a `transient` absence with
   reason `not_yet_available`; the previous vintage stands. An observation
   dated on a *later date* remains a hard error — nothing inside a session can
   carry a later date, so that is an adapter bug.

4. **Absence type is declared, never inferred.** An ineligible pillar must
   state `absence` as `structural` or `transient`. Omitting it raises. Guessing
   `structural` was audit finding A02: it dropped a temporarily unavailable
   pillar out of the D2 mask, defeating the `R → ∞` mechanism SPEC objective O6
   relies on.

5. **C8's staleness clock accepts optional per-session hours.** Omitting them
   reproduces the previous behaviour exactly; supplying them makes Muhurat and
   two-window special sessions count real trading time.

## Session registry: what it is and is not

Four deviations are registered. Every one is corroborated by an out-of-hours
observation already in this repository (a Hawkes refit timestamp in
`research_data/original_hawkes.parquet`), and `TradingSession.__post_init__`
refuses an entry whose declared window does not contain its corroborating
observation.

| Date | Windows (IST) | Kind | Corroborating refit |
|---|---|---|---|
| 2024-03-02 | 09:15–10:00, 11:30–12:30 | special_live | 12:25 |
| 2024-05-18 | 09:15–10:00, 11:30–12:30 | special_live | 12:25 |
| 2024-11-01 | 18:00–19:00 | muhurat | 18:55 |
| 2025-10-21 | 13:45–14:45 | muhurat | 14:40 |

Every entry's `evidence_status` is **`declared`**. No official exchange
calendar has been ingested into this repository, and the registry is
deliberately **partial** — only sessions this repo evidences are registered;
other historical special sessions fall back to regular hours.
`SessionCalendar.completeness()` reports this, and every run manifest now
carries it.

The asymmetry that makes this safe: a close declared **too early** only
withholds information, which is causally conservative. A close declared **too
late** would be the real hazard, which is what `evidence_status` exists to
track. Ingesting an official calendar is Phase 5 work.

## Consequence: the archived COVID replay changes, and why

Replaying 2020-01-01…2020-04-30 now produces a slightly different CSRS series.
This is a **correction**, reported rather than hidden.

**Cause.** The archive holds one Hawkes refit stamped `2020-02-01T15:25 IST`
whose calendar date is *not* a session in `market_snapshot.parquet`.
Date-keyed selection never matched it, so that observation was silently
dropped from the replay entirely. As-of selection offers it at the next
decision (2020-02-03). D4 correctly rejects it as stale — the set of
*assimilated* vintages is unchanged, and no mask changes — but the
chronological standardisation window now contains it, so subsequent Hawkes
ranks shift slightly.

**Magnitude.** 11 of 81 dates change. Maximum |ΔCSRS| = **0.00264** (rank
units, scale 0–1). No mask changed; no alert level changed.

| Date | Baseline | New | Δ |
|---|---|---|---|
| 2020-02-07 | 0.017633 | 0.017521 | −0.000112 |
| 2020-02-14 | 0.023894 | 0.023742 | −0.000152 |
| 2020-02-24 | 0.036238 | 0.037409 | +0.001171 |
| 2020-03-02 | 0.051681 | 0.053581 | +0.001899 |
| 2020-03-09 | 0.042317 | 0.043354 | +0.001036 |
| 2020-03-17 | 0.221057 | 0.222834 | +0.001776 |
| 2020-03-24 | 0.568727 | 0.570832 | +0.002105 |
| 2020-03-31 | 0.570570 | 0.572957 | +0.002388 |
| 2020-04-09 | 0.585714 | 0.588157 | +0.002444 |
| 2020-04-20 | 0.594996 | 0.597451 | +0.002455 |
| 2020-04-27 | 0.581129 | 0.583766 | +0.002636 |

This changes **no scientific conclusion**. The original advance-warning claim
remains unestablished, and these differences are far below anything that would
bear on it. The baseline run is preserved in place for comparison; the new
replay is written to separate stores.

## Related data finding (not fixed here)

`research_data/market_snapshot.parquet` has no row for **2020-02-01**, although
the intraday Hawkes corpus evidences a session on that date. The daily snapshot
is therefore missing at least one trading session. This is recorded for the
Phase 5 source census (`DATA02`) and the session-calendar work; it is **not**
patched here, because the snapshot is hashed research evidence.

## Verification

`scripts/verify_fix01_fix02.py` → `docs/evidence/FIX01-FIX02-REPLAY-2026-10-16.json`

- Full supported history replayed, 2005-01-03 → 2026-08-21, **5361 points**,
  under both decision-clock policies, into a new output location.
- Zero future-information violations in either replay.
- Deterministic retry reproduced the same run identity and the same content.
- Tests: `tests/test_fix01_session_clock.py` (16),
  `tests/test_fix02_absence_semantics.py` (10).
