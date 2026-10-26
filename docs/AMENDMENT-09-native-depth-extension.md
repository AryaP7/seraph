# Amendment 09 — native intraday depth extension, and what it does and does not unlock

25 October 2026. Acquisition and verification, not an audit. This records the
completed depth-extension backfill, the coverage verification, the re-seeded
native history, a newly surfaced class of absence and its upstream cause, and
the measured cost of the historical Hawkes replay.

No threshold, cadence, window, equation or validation requirement was
changed. Evidence:
[`docs/evidence/native-depth-2026-10-25/native-depth-extension.json`](evidence/native-depth-2026-10-25/native-depth-extension.json).
Nothing was committed.

---

## 1. The backfill is complete

The unblocking command recorded in `docs/NEXT-SESSION.md` ran to completion:

```
python scripts/backfill_intraday.py --from 2023-09-01 --to 2024-08-01 \
  --checkpoint prototype_runs/depth-extension.checkpoint.json
```

380 of 380 planned requests done — 95 symbols × 4 windows, exactly the
dry-run's figure. The Kite token issued at 2026-10-25 17:32:33 was live
throughout; no re-login was needed.

## 2. Coverage verified, duplicates ruled out

| check | result |
|---|---|
| duplicate `(symbol, ts)` rows | **0** |
| `intraday_bars` rows | 5,744,265 |
| dated sessions in the requested range | 227 |
| of those, **all-member** (95/95) sessions | **227** |
| sessions missing at least one member | 0 |
| members absent entirely from the range | none |
| session-days per member | min 227, max 227 |
| **all-member sessions store-wide** | **778** (was 552) |
| all-member session span | 2023-09-01 → 2026-10-22 |

Duplicates are structurally impossible under `PRIMARY KEY (symbol, ts)`, and
every write goes through C1's idempotent upsert. The count is reported anyway
rather than argued from the schema.

The handoff predicted 552 → ~782 against a 751 bar. The measured figure is
**778**, which clears 751.

## 3. The native history was re-seeded, without backdating an arrival

```
python scripts/prepare_native_hawkes.py --through 2026-10-22 \
  --window-sessions 500 --bar-timestamps start \
  --config prototype_runs/live.native-hawkes.json
```

4,150,272 → **5,744,265** rows; 695 → **921** distinct dates; 95 of 95
members covered. The row count matches the store exactly, so nothing was
dropped in transit.

The arrival discipline survived the reseed, which was the thing most at risk.
`NativeHistory.append` is `INSERT OR IGNORE` on `PRIMARY KEY (symbol, end)`,
so rows by receipt date are now:

| receipt date | rows |
|---|---|
| 2026-10-22 | 4,150,272 |
| 2026-10-25 | 1,593,993 |

The pre-existing rows kept their original receipt and only genuinely new rows
carry today's. **No arrival time was backdated**, and re-running the seed is
idempotent rather than re-dating.

**The session schedule was deliberately NOT regenerated.** It declares dated
exceptions only, and `NativeSessionSchedule.load` constrains them to
`2026-08-03 <= day < 2026-12-07`. The four dated special pre-open notices are
2025-01-06, 2025-10-14, 2025-12-05 and 2026-04-30. The backfilled range
precedes every one of them, so the normal session applies across it and there
is nothing dated to add. Regenerating would have changed a hash for no
change in content.

## 4. The census over the extended era, and one new class of absence

`census_native_bars.py --sessions 778` now covers the whole all-member era
(2023-09-01 → 2026-10-22), 58,053 union-grid slots:

| class | slots | new? | fillable? |
|---|---|---|---|
| session tail (CAS) | 14,616 | no | **no** — the candle does not exist |
| dated special pre-open | 14 | no | **no** |
| **GVT&D single intervals** | **12** | **yes** | **no** — see below |
| unexplained | **0** | — | — |

The trailing-500 census is unchanged at 14,630 / 14,616 / 14, matching the
2026-10-24 reading exactly, so the backfill disturbed nothing already
verified.

### The 12 new absences are upstream, and were confirmed as such

Twelve isolated single-interval absences, all in **GVT&D**, on eleven
scattered dates between 2023-10-09 and 2024-04-23 (one interval each, except
2023-10-12 with two). They are not a contiguous block, not aligned to any
session boundary, and shared with no other member — so they are not a
request-window artefact and not a session-schedule gap.

GVT&D is the **3rd least liquid of the 95 members** over the backfilled range
by median five-minute volume (383). It holds 16,842 bars against 16,854 for a
fully covered member — exactly the 12-bar difference. Intervals adjacent to
each gap carry volumes of 0 to 60.

That is suggestive, not proof, so **the broker was re-asked**. For four of
these sessions Kite's own response returns **74 candles, not 75**, and the
absent interval is missing from the broker's response too:

| session | absent interval | neighbours either side | broker's answer |
|---|---|---|---|
| 2023-10-09 | 13:55 | 13:45, 13:50 / 14:00, 14:05 present | **absent** |
| 2023-10-10 | 13:20 | 13:10, 13:15 / 13:25, 13:30 present | **absent** |
| 2023-12-05 | 11:05 | 10:55, 11:00 / 11:10, 11:15 present | **absent** |
| 2024-01-25 | 09:15 | 09:20, 09:25 present (late first trade) | **absent** |

So no such candle exists. **The backfill did not miss them.** The correct
handling is the one already applied to the CAS tail and the pre-open notices:
declare the session that actually traded, and fabricate nothing.

## 5. The Hawkes replay: engineering works, the arithmetic has not moved

The structural blocker recorded in the handoff — one clock serving both the
bar cutoff and the arrival guard, so a past cutoff saw zero bars — is
resolved in the code already: `fit_pending(data_cutoff=...)` separates them
and `warm_native_hawkes_history.py` walks the cadence with it.

The planner, against the deepened history with point-in-time baskets:

```
python scripts/warm_native_hawkes_history.py \
  --config prototype_runs/live.native-hawkes.json --baskets dated
```

| | |
|---|---|
| sessions visible | 921 |
| candidate cadence points | 422 |
| candidate range | 2025-02-05 → 2026-10-22 |
| epochs / range | 43 / 2005-07-01 → 2026-07-01 |
| basket sizes across epochs | 91–98 |
| required observations | 252 |
| admitted before | 1 |

**Measured execution cost — and a correction.** A first run produced zero
completed fits in 35 minutes, from which this amendment originally
extrapolated "hours per fit". That extrapolation was wrong. Timing individual
candidates on the dated path gives:

| candidate | epoch basket | `fit_pending` | outcome |
|---|---|---|---|
| 2025-02-05 | 2025-01-01, 94 members | 17.9 s | `Incomplete common native-bar coverage`, **82** incomplete members |
| 2025-12-15 | 2025-07-01, 94 members | 60.2 s | `Incomplete common native-bar coverage`, **19** incomplete members |
| 2026-10-23 | 2026-07-01, 95 members | 51.9 s | `refit_not_due` |

Mean 43.3 s, so the full 423-candidate replay is about **5.1 hours** of
compute. Affordable. **Cost was never the blocker.**

Two mechanisms were confirmed working in the process. At the 2025-02-05 bar
cutoff `fit_pending` reported `observed_sessions=500` even though every row in
the history carries a 2026 arrival, while a raw `NativeHistory.rows()` call
with a single cutoff returns **0** rows at that date — the original defect and
its fix, observed side by side. And at the 2026-10-23 candidate `rows()`
returned exactly 4,150,272 rows, the original receipt batch, excluding the
1,593,993 received today: the re-seed backdated nothing.

### What actually blocks it: point-in-time basket coverage

**70 distinct symbols appear in the dated epoch baskets and have no intraday
bars in the store at all.** Every one has since left the universe — none is
in today's 95. The depth backfill acquired *today's* members; a point-in-time
basket needs the members each epoch actually had.

| epoch | members | with no bars |
|---|---|---|
| 2023-01-01 | 94 | 34 |
| 2024-01-01 | 93 | 27 |
| 2025-01-01 | 94 | 23 |
| 2025-07-01 | 94 | 19 |
| 2026-01-01 | 96 | 14 |
| **2026-07-01** | 95 | **0** |

Only the current epoch is complete, and its candidates are `refit_not_due`.
That is why the replay produced nothing. (82 incomplete against 23 absent at
2025-02-05 is the window reaching back past 2023-09-01 into the sparse era
where only the ~17 deep-history members hold bars.)

So the remedy is acquisition, not a parameter: 5-minute bars for those
members over the same era today's members cover. 69 of the 70 resolve against
the broker's NSE EQ list and the history depth is there — ABB, ACC and
ADANIENSOL each return 450 candles for the first week of 2023-09, six
sessions at 75 bars. 828 requests, 12 windows for each of 69 symbols.

This changes no equation, threshold, window, cadence or basket rule. The
point-in-time discipline *requires* the epoch's own members; without them the
replay either fails, as it did, or would have to substitute today's basket,
which is look-ahead.

**Acquired, and it closed the gap.** 4,000,917 bars across 69 symbols, **0
rejected, 0 incomplete windows**. `intraday_bars` now holds **9,752,046** rows
across **164** distinct symbols with **0** duplicate `(symbol, ts)` rows.
Epoch coverage re-measured:

| epoch | members | with no bars | first bar after the epoch |
|---|---|---|---|
| 2023-01-01 | 94 | 0 | 71 |
| 2023-07-01 | 95 | 0 | 72 |
| 2024-01-01 | 93 | **0** | 0 |
| 2024-07-01 | 95 | 1 — HFCL only | 0 |
| 2025-01-01 | 94 | 1 — HFCL only | 0 |
| 2025-07-01 | 94 | **0** | 0 |
| 2026-01-01 | 96 | **0** | 0 |
| 2026-07-01 | 95 | **0** | 0 |

Two residual gaps, both understood. HFCL stays absent from its two epochs by
the decision below. And the 2023 baskets have every member present but 71 and
72 of them hold their first bar on 2023-09-01, which is where this
acquisition era starts — so candidates whose window reaches before then stay
incomplete. That is more acquisition of the same kind, not a new problem.

**One integration had to be added for any of this to reach the model.**
`prepare_native_hawkes.py` seeded only the latest snapshot's basket, so the 69
newly acquired members would have sat in Postgres and never reached the native
history the replay reads. It now takes
`--seed-members {config,dated-union}`, defaulting to `config` so every
existing invocation behaves identically; `dated-union` seeds the union of
every snapshot's basket while the config keeps declaring the latest basket as
`members`, because the live estimation path must not move when a replay needs
deeper inputs. The selection is a pure `seeded_symbols()` helper pinned by a
regression test — that the latest basket is always included, that the result
is deduplicated and ordered so a reseed is byte-stable, that omitting the
snapshots cannot silently widen anything, and that an unknown policy raises.

**One symbol is blocked, and was not worked around.** HFCL does not resolve:
it now trades as `HFCL-BE`, having moved to the **BE series**
(trade-for-trade settlement, a surveillance measure). That is a series change,
not a rename, and the two are not interchangeable — a trade-for-trade counter
has no intraday netting, so its microstructure and hence its jump process
differ from its EQ-series history. Splicing the two would be a data-identity
decision with scientific consequences, and the repository's existing
discipline for an identity change (the TATAMOTORS/TMPV handling) requires a
dated exchange notice, which is not held here. HFCL appears in exactly two
epoch baskets, 2024-07-01 and 2025-01-01, so those stay one member short;
the 2025-07-01 and later epochs do not contain it.

### What the replay will now produce, measured before running it

The replay is about five hours, so what it can yield was checked from the
history first rather than discovered at the end. For every candidate: does
each member of **its own** epoch basket hold a bar on every date in the
500-session window?

| | |
|---|---|
| candidates | 423 |
| with complete epoch coverage | **280** |
| covered range | **2025-09-05 → 2026-10-23** |
| fits at cadence 5 | **about 56** |
| required | 252 |

The transition is sharp and self-consistent: 2025-08-08 has **71** incomplete
members, 2025-09-16 has **0**. Session 500 of the all-member era lands around
2025-09-05, so every earlier candidate's window reaches back before
2023-09-01 where only the deep-history members hold bars — and 71 is exactly
the count of members whose first bar is 2023-09-01.

So the remedy works: the replay goes from producing **zero** historical fits
to about **56** real ones, with point-in-time baskets and actual availability
times. It still does not reach 252 at the declared cadence, which is the same
conclusion the cadence arithmetic reaches by an independent route — reaching
252 at cadence 5 would need 500 + 5×251 = **1,755** covered sessions, i.e.
extending every epoch member's coverage back to roughly 2019. This makes the
replay produce real verifiable vintages; it does not make the gate pass, and
nothing was tuned so that it would.

### What the extra depth did and did not change

It **did** clear the session count that cadence 1 would need: 778 all-member
sessions against the 751 that table required. That is a real change and it
was the point of the backfill.

It did **not** make the requirement satisfiable, because the cadence is
unchanged at five sessions:

| | |
|---|---|
| sessions for 252 fits at cadence 5 | 1,755 |
| all-member sessions available | 778 |
| what a 5-year ECDF window holds at cadence 5 | ~248 fits — fewer than the 252 required |

So at the declared cadence the requirement stays unsatisfiable **no matter
how much history is acquired**, which is the same conclusion the handoff
reached, now measured against 778 sessions instead of 552.

`refit_sessions` is part of `_compatible`, so changing it invalidates every
existing fit. **It was not changed, and neither was the 252 threshold.** Both
remain owner decisions. Acquiring and re-seeding the data did not require
either decision, which is why it was done first.

## 6. A whole session was missing from both stores, and is now acquired

Checking whether F02's *other* half — "verify a genuine in-session current
publication" — could be done today turned up a gap nothing had reported.

Today is **Sunday 2026-10-25**. Walking the calendar either side of it
against the broker's own data, for RELIANCE, the most liquid member:

| day | `SessionCalendar.is_session` | broker candles | verdict |
|---|---|---|---|
| 2026-10-19 | True | 72 | traded, in store |
| **2026-10-20** | True | **0** | **did not trade** |
| 2026-10-21 | True | 72 | traded, in store |
| 2026-10-22 | True | 72 | traded, in store |
| **2026-10-23** | True | **72** | **traded, and was MISSING from both stores** |
| 2026-10-24 | False | 0 | did not trade |

**2026-10-23 (Friday) was a real session that nothing had acquired.**
`intraday_bars` ended at 2026-10-22 and `daily_prices` ended at 2026-10-22,
while the exchange had traded a full session on the Friday. Both have now
been acquired:

| | |
|---|---|
| intraday | 6,864 bars, 95 of 95 members, **0 rejected, 0 incomplete windows** |
| end of day | 2,706 rows, universe flags re-derived for 2026, market snapshot rebuilt |
| `intraday_bars` rows | 5,744,265 → **5,751,129** |
| duplicate `(symbol, ts)` rows | still **0** |
| all-member sessions | 778 → **779** |
| native history re-seeded `--through 2026-10-23` | **5,751,129** rows, 95 of 95 covered |

6,864 bars is exactly the figure every other recent all-member session
carries, so the session is complete rather than partially recovered.

### 2026-10-20: the production calendar is right, and I first read it wrong

My probe called `SessionCalendar()` directly, which returned `True` for
2026-10-20 while the broker returned no candles and neither store holds the
day. I initially recorded that as the calendar being wrong but deliberately
unpatched. **That was my error, and the correction matters.**

An ingested, evidence-pinned exchange calendar already exists and is
configured: `prototype_runs/exchange_calendar/current.json`, covering
2026-10-19 → 2026-10-23, pinned to NSE circular `CMTR71775.pdf` with its
sha256 and retrieval time recorded. Asking the calendar the production path
actually uses, `seraph.market_calendar.exchange.configured()`:

| day | `configured()` says | verified by evidence? | broker |
|---|---|---|---|
| 2026-10-19 | session | yes | traded |
| **2026-10-20** | **not a session** | **yes** | did not trade |
| 2026-10-22 | session | yes | traded |
| 2026-10-23 | session | yes | traded |
| 2026-10-26 | session | **no** — outside the interval | — |

So the holiday is correctly known, with exchange evidence behind it, and
`seraph/live/clock.py` consults exactly this. `SessionCalendar`'s
`weekday() < 5` is only the fallback used when no such document is installed,
which is what `seraph/operations/schedule.py` documents when it says
inventing a holiday table "would be fabricating exchange data". Nothing was
patched, and now for a better reason: there is nothing wrong to patch.

**One real inconsistency remains, and it was left alone deliberately.**
`scripts/backfill_intraday.py` builds a bare `SessionCalendar()` rather than
calling `configured()`, so its `_last_completed_session_close` would treat a
closed day as a completed session. Traced through, that changes no outcome: a
window ending at a close on a non-trading day still ends at or after the
previous real session's close, so it cannot truncate anything — which is the
failure that function exists to prevent. Since it is behaviour-neutral and
`configured()` can raise on a malformed document, swapping it was not worth
the risk during an acquisition run. It is a one-line change for whoever wants
the two paths to agree on a fact that has evidence.

Worth noting too that `live/inference.py`, `live/archive_adapter.py` and
`orchestration/prototype.py` all construct `SessionCalendar` with an explicit
`session_dates` set derived from observed data, so the weekday fallback is
bypassed there as well.

## 7. Monday is now a verified session, not an assumed one

The configured calendar's interval ended 2026-10-23, so
`configured().verified_for('2026-10-26')` was **False**: Monday could only be
*assumed* to be a session, and assuming the session is exactly what this
calendar exists to prevent. Since F02's remaining requirement is a genuine
in-session publication, that assumption would have sat underneath the one
thing being verified.

No new evidence was needed. `CMTR71775.pdf`, already stored and hashed under
`prototype_runs/exchange_calendar/2026-10-21/`, is NSE's trading-holiday
circular for the **whole of calendar year 2026** (Download Ref
NSE/CMTR/71775, 12 December 2025). It already covered next week.

The interval now runs **2026-10-19 → 2026-10-30**, all 12 days enumerated,
built by [`extend_calendar.py`](evidence/native-depth-2026-10-25/extend_calendar.py).
The holiday statuses are **parsed out of the circular**, not hand-entered —
a transcription slip is the realistic failure mode here, so the circular
decides and the script asserts it found the Dussehra row before writing
anything. Same two evidence files, same hashes, re-verified on the way
through.

| day | session | verified |
|---|---|---|
| 2026-10-20 Tue | **no** — Dussehra, from the circular | yes |
| 2026-10-24 Sat, 2026-10-25 Sun | no — weekend | yes |
| **2026-10-26 Mon** | **yes, close 15:30** | **yes** |
| 2026-10-27 … 2026-10-30 | yes, close 15:30 | yes |
| 2026-10-31 onward | — | no, outside the interval |

**Bounded at 2026-10-30 on purpose.** The circular's next entries are Sunday
2026-11-08 (Diwali Laxmi Pujan, whose Muhurat trading "timings shall be
notified subsequently") and Tuesday 2026-11-10 (Diwali-Balipratipada).
Muhurat is a non-standard session with unpublished hours, so going past
2026-11-07 needs that later notice; the script refuses to. The previous
bounded week is preserved at
`prototype_runs/exchange_calendar/2026-10-21/calendar.json`.

91 clock, calendar and session tests pass against the wider interval.

## 8. What is left

* **F02's in-session verification is time-gated, not blocked.** It needs a
  live session, and today is Sunday. The next session is **Monday
  2026-10-26**, now verified against exchange evidence; both stores reach the
  last completed session, so nothing stands in the way of attempting it then.
* Resume the replay and let it run; it will produce real historical vintages
  with actual availability times and point-in-time baskets. It cannot reach
  252 observations at cadence 5, and it is not on the critical path for
  anything else.
* The cadence question in §5 is the owner's. Nothing else in F02 is blocked
  on data any more.
