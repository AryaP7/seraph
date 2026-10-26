# Native Hawkes runtime continuation — 22 October 2026

**October 24 update:** the coverage blocker described below is resolved. One
actual native fit covers 500 sessions and all 95 members with zero unexplained
common-session gaps. Cold start admits one Hawkes observation; the
252-observation warm-up and genuine live publication remain incomplete. See
[dated session correction and evidence](NATIVE-SESSION-COVERAGE-2026-10-24.md).
The October 22 record below is preserved as earlier evidence.

The native C5 producer is now wired to the runtime as an explicit configuration.
It persists completed five-minute closes, applies the existing C4 detector and
discrete Hawkes estimator, and retains the adopted fit-cutoff basket rule.
Its ungated `n/(1-n)` output matches the existing contagion adapter; FR13-gated
MTS remains separate provenance. The F07 directed-network estimator is untouched.

The configured window is 500 sessions, with the existing production writer's
five-session refit cadence. A carried fit retains its original input time.
Numerical fitting runs in a separate owned `run_native_hawkes.py` process with
an OS worker lock; the bar-close callback only records inputs and reads eligible
completed vintages. Runtime shutdown terminates its owned worker. Worker status
is saved beside the configuration as `.status.json`, including unavailable results.
Fits retain parameters, time-of-day profile, input/event hashes, membership,
implementation hash and actual availability. A fit completed after a decision's
cutoff cannot enter that decision. Repeated writes preserve first availability;
changed input prices require a separate archive, rather than overwriting evidence.
The worker checks common-bar coverage before extracting jumps. Its status gives
missing counts by member, affected intervals and the actual input bounds. It
reuses an unchanged evaluation until eligible append-only inputs change; late
arrivals trigger a new check only when their receipt time is eligible. Exceptions
remain retryable. `evaluated_at` distinguishes an evaluation from a cached poll.

Missing history, incomplete common coverage, within-session grid gaps and
unconverged fits cannot become zero-valued observations. Once configured, missing
Hawkes support is transient and remains in the D2 mask. Its 252-observation
standardizer requirement remains enforced; the RMT warm-up does not satisfy it.

## Verified local input state — evening update

- RMT history build resumed and completed: **252 registered observations**, no failures.
  The evening runtime admits **253** after the October 22 daily observation.
- The existing Hawkes basket builder produces **95 members**, all with current
  broker instrument mappings. This preserves the liquidity-core plus provisional
  tariff-representative rule; it does not substitute the 500-stock RMT basket.
- Refreshed broker access works: a recent-history REST request succeeds and the
  95-symbol live websocket connects. The earlier 403/failure evidence is retained.
- Acquired **3,906,400 bars** for August 2024–October 22, 2026, across all 95
  members, with zero rejected bars or incomplete request windows. Seeded native
  history now contains **4,150,272 configured-member bars**, including the older
  research inputs. Request completion is distinct from complete candle coverage.
- The actual 500-session check spans **2024-10-16 through 2026-10-22**, with
  **37,374 observed intervals**. **182 intervals** lack one or more members,
  totalling **14,630 missing symbol-bars**; eight members cover the entire grid.
  The fit is withheld under the common-grid rule. No native fit was persisted.
- A fresh source check of ITC on January 6, 2025 and RELIANCE on August 3 and
  October 22, 2026 still omits the sampled missing candles. The cause is not
  established. Repeating the completed full backfill is not a demonstrated fix.
- The optimized real-data preflight took **15.28 seconds**. This is a worker
  readiness measurement, not numerical-fit or live bar-to-decision latency.
- The websocket check ran after market close and correctly published nothing.
  The loaded calendar's next opening is **October 23, 09:15 IST**. A genuine
  in-session closed-bar/current-publication check remains unverified.
- The initial full-universe preflight is retained in the evidence folder but is
  superseded by `runtime-readiness.json`, which uses the correct Hawkes basket.

## Remaining acceptance and runtime commands

The existing resumable `scripts/backfill_intraday.py` acquires actual native
history. Repair missing observations with supported source data, or separately
specify and validate missing-bar treatment before changing the admission rule.
Do not shrink the basket/window, manufacture prices or silently count missing
contributors as zero jumps. Then obtain actual eligible Hawkes history for its
252-observation standardizer and verify current publication during a market session.
RMT warm-up alone does not close these gates. F07 remains on explicit owner hold.

Seed/read the research database without modifying it:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_native_hawkes.py --through 2026-10-22 --window-sessions 500 --bar-timestamps start --config prototype_runs/live.native-hawkes.json
```

`start` describes the existing Kite candle timestamp convention; imported bar
ends are five minutes later. The script requires the convention explicitly.
Source rows are read in a read-only repeatable-read transaction, and receipts
are recorded when this installation imports them. Refresh the configuration at
each C3 rebalance; its pinned membership is not an automatically updated universe.

Launch with the native producer explicitly selected:

```powershell
.\launch_prototype.ps1 -NativeHawkesConfig .\prototype_runs\live.native-hawkes.json
```

Or perform a bounded standalone check:

```powershell
.\.venv\Scripts\python.exe scripts/run_live.py --hawkes-config prototype_runs/live.native-hawkes.json --once
```

Inspect persisted readiness without starting a feed or fitting:

```powershell
.\.venv\Scripts\python.exe scripts/run_live.py --hawkes-config prototype_runs/live.native-hawkes.json --status
```

The ordinary daily-only mode remains available. Native configuration is refused
in replay mode so replay bars cannot populate the live native history. This
producer does not make scientific prediction claims, remove Hamilton's standing
exclusion, or bypass the exchange-calendar/current-publication gates.

## Verification evidence

`docs/evidence/engineering-closeout-2026-10-22/` retains the interrupted history
status, earlier failures, successful evening probes, current input readiness and test
reports. Native runtime tests exercise durability/revision refusal, late-arrival
withholding, missing support, closed common-grid admission, preserved fit
availability, and live/replay separation. Synthetic fitted parameters used in
transport tests are not evidence of a measured market fit.

F07 remains pending at the owner's explicit choice on October 22. Overall
engineering remains approximately 97% until the remaining integration and
acceptance gates are genuinely closed.

Broad regression evidence: `full-suite-recheck.xml` records **2,585 passed,
22 skipped, zero failures/errors**. Of those skipped tests, the 17 requiring
PostgreSQL subsequently passed against the isolated disposable database on port
5435 (`disposable-db.xml`); it was stopped again after verification. The remaining
five skips cover four retained old-corpus checks and the explicit live-NSE check.
The latest coverage/cache/runtime changes pass **38 focused checks** in
`native-coverage-regression.xml`, and the invariant checker passes. Earlier
`native-runtime.xml` records 82 overlapping checks; do not add the runs together.

The current evidence index is `evening-continuation.json`. The actual support
result is `native-readiness-final.json`, the complete gap list is
`native-common-grid-gaps.json`, and bounded source retries are in
`native-gap-source-recheck.json`. `native-evening-connection.log` preserves the
successful connection and honest after-hours withholding. No original-source
database writes or F07 fits were performed.
