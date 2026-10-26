# Native Hawkes session coverage — October 24, 2026

The current native fit now succeeds. Its explicitly configured 500-session,
95-member window has 37,170 common continuous-session bins, no incomplete
members and no unexplained grid gaps. The original 4,150,272 closes remain
intact. This closes the previously reported coverage blocker, not F02's
standardizer or live-publication acceptance.

Overall engineering completion remains approximately **97%**, with the same
40 implemented and two partial feature units. F07 remains on the owner's
explicit hold; the native univariate C5 fit is separate from that network fit.

## Why the previous check reported missing candles

The old check treated the union of every symbol's candles as a joint trading
session. Dated exchange evidence shows two exceptions in this window:

- **Closing auctions:** 56 dated NSE reports, August 3–October 22, identify
  87 of the configured 95 symbols. Under the applicable timetable their
  continuous session ends at 15:15. Kite confirms its historical candles omit
  that auction. The other eight symbols' later continuous-session candles
  are retained in raw storage but excluded from the joint estimation window.
- **Special pre-open auctions:** the remaining 14 absent candles fall on four
  explicitly announced auctions running from 09:00 to 10:00. On those dates
  the joint continuous-session window starts at 10:00; its first complete
  five-minute candle ends at 10:05. Existing pre-open candles are also excluded
  from this continuous-session calculation, rather than selectively removing
  just the absent intervals.

| Dated session | Exchange symbol | NSE circular |
|---|---|---|
| 2025-01-06 | ITC | [CMTR65845](https://nsearchives.nseindia.com/content/circulars/CMTR65845.pdf) |
| 2025-10-14 | TATAMOTORS | [CMTR70614](https://nsearchives.nseindia.com/content/circulars/CMTR70614.pdf) |
| 2025-12-05 | HINDUNILVR | [CMTR71508](https://nsearchives.nseindia.com/content/circulars/CMTR71508.pdf) |
| 2026-04-30 | VEDL | [CMTR73856](https://nsearchives.nseindia.com/content/circulars/CMTR73856.pdf) |

[CML70875](https://nsearchives.nseindia.com/content/circulars/CML70875.pdf)
documents the TATAMOTORS → TMPV rename effective October 24, 2025. This connects
the broker's current historical-series label to the October 14 notice without
claiming TMPV was the exchange symbol on that earlier date.

Closing-session sources:
[dated NSE reports](https://www.nseindia.com/static/reports/closing-auction-session-historical-data),
[NSE timetable](https://www.nseindia.com/static/products-services/closing-auction-session),
[Kite historical-candle explanation](https://kite.trade/forum/discussion/16307/kite-connect-historical-5-minute-nse-candles-stop-at-15-10-ist),
[January SEBI rule](https://www.sebi.gov.in/sebi_data/attachdocs/jan-2026/1768576287344.pdf)
and [October revision](https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1792079571420.pdf).
The revised timetable takes effect December 7 and is not applied early.

## Implementation and actual evidence

`scripts/prepare_native_sessions.py` saves the raw sources, retrieval times and
hashes. `seraph/market_calendar/native_sessions.py` validates them and applies
only dated, eligible evidence. The optional `session_schedule_file` is selected
in `prototype_runs/live.native-hawkes.json`; reseeding preserves and validates
that selection. Without it the existing strict observed-grid behavior remains.

The rule excludes 4,750 actual rows from this estimation window, keeps every
raw close, and fabricates none. Both the coverage preflight and per-symbol
detector input use the same common session. Unexplained within-session holes
still prevent fitting. A filtered-away day cannot satisfy the 500-session
requirement. Receipt times prevent these October 24 acquisitions from being
used at an earlier information cutoff. New dates and unsupported timetables
are not extrapolated.

The separate native worker completed one actual fit. It is trained through
**2026-10-22 15:15 IST**, available only from **2026-10-24 18:02:45.081189 IST**.
Its manifest retains the observation-policy hash, implementation hash, basket,
input/event hashes and fitted parameters. Convergence is computational evidence;
it is not evidence of predictive skill.

All evidence below is under `docs/evidence/engineering-closeout-2026-10-24/`:

- `native-session-continuation.json`: current evidence index and code hashes.
- `native-full-session-readiness.json`: successful 500-session/95-member check.
- `native-current-fit.json`: registered native model and provenance.
- `native-session-idempotency.json`: repeat check reports `refit_not_due`,
  retains exactly one native fit and confirms 4,150,272 raw closes remain.
- `native-session-cold-start.json`: actual runtime admission — **1 Hawkes,
  253 RMT, 0 Hamilton observations**; four legacy records remain rejected.
- `native-session-schedule/`: 56 auction CSVs, four pre-open circulars, one
  rename circular, receipt records and the selected schedule. The earlier
  `cas-only-schedule.json` and intermediate 14-gap check are preserved.
- `native-session-regression.xml`: **49 passed**. Source tampering/date
  mismatches, late availability, common-session selection, raw preservation,
  unexplained holes, reseeding, runtime and launcher contracts are covered.
- `native-session-invariants.log`: all mechanical checks passed;
  `git diff --check` also passed.

No new full-suite result is claimed. The separate October 24 news handoff
records 2,585 passes, 25 skips and one database-dependent failure with Docker
stopped. The earlier October 22 full-suite and isolated-database results remain
dated evidence, not a current universal pass.

## Remaining acceptance

F02 still requires **252 legitimate Hawkes standardizer observations** and a
genuine in-session current publication. One fit supplies one observation, not
252 warm-up samples. A historical build needs point-in-time basket selection,
supported native inputs and preserved actual availability; repeated carry-forward
values and legacy estimates cannot be used to manufacture readiness. Its
five-session refit cadence and five-year ECDF window must also be respected.

F07 remains pending by explicit user choice. Hamilton's existing exclusion is
unchanged. October 24 is outside the normal market session; no live publication
was manufactured. The one-shot native worker exited. No commit or push was made.

To refresh dated source evidence:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_native_sessions.py --through 2026-10-22 --include-special-preopen --out docs/evidence/engineering-closeout-2026-10-24/native-session-schedule
```

To run the current worker or inspect its status:

```powershell
.\.venv\Scripts\python.exe scripts/run_native_hawkes.py --config prototype_runs/live.native-hawkes.json --store prototype_runs/live.sqlite --once
.\.venv\Scripts\python.exe scripts/run_live.py --hawkes-config prototype_runs/live.native-hawkes.json --status
```

Refreshing the evidence changes its content hash. Preserve the prior manifest
and its sources when intentionally selecting a new version; old fit provenance
must remain recoverable.
