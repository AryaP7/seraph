# DR-09 — The intraday process clock for C8

**Date:** 2026-10-17
**Raised by:** T06 §5.3 — "Proposed intraday clock mapping, requiring a
documented adapter decision and numerical checks."
**Status:** decided — **reuse C8's existing per-bar trading clock**; no
conversion layer is introduced, because the existing units are already the
right ones.

---

## The question

Moving from one decision per session to one per bar raises an obvious hazard:
if the process-noise model is written in *daily* units and the filter is asked
to predict seventy-five times a day, it may inject a full day's covariance on
every bar. The plan proposes a mapping to guard against that — let `u(t)` be
completed observed sessions plus the fraction of scheduled open minutes
elapsed in the current session, then advance with `Δu` against a daily-unit
random-walk covariance — and instructs: *"If the existing implementation
already supports a different verified clock, reuse that mapping and record it
instead."*

## What the existing implementation does

`KalmanReconciler._advance` (`seraph/reconciliation/kalman.py`):

```python
delta_bars = self._clock.elapsed_bars(self._ts, t)
if delta_bars > 0 and self._mode == "kalman":
    self._P = self._P + self._q * delta_bars * np.eye(3)
```

and `ReconciliationClock.elapsed_bars` sums **seconds inside declared session
windows**, divided by 300. So:

- `q_proc` is already a **per-five-minute-bar** variance, not a daily one;
- overnight, weekends and holidays contribute **zero**, because they are not
  inside a session window;
- a split-session break contributes zero for the same reason — the clock
  iterates `windows_for(day)`, not open-to-close;
- a Muhurat hour contributes 12 bars, not a day.

The same clock drives `_staleness_bars`, so D4's `h_bars` and the saturating
noise ceiling are in the same units as the process noise. There is one clock,
not two.

## Decision

**Reuse it.** The plan's `u(t)` is this quantity in different units:

```
u(t) = elapsed_bars(t₀, t) / BARS_PER_REGULAR_SESSION      (75)
```

`seraph/live/inference.py` exposes that as `sessions_elapsed()` for anything
that wants the session-unit view, and nothing converts the filter's own
arithmetic. Introducing a daily-unit `Q` and a conversion would add a second
place for the units to be wrong, to fix a defect this code does not have.

The corresponding statement about parameters: **`q_proc`, `h_bars` and
`r0_default` are all per-bar and are not re-scaled by the move to intraday
cadence.** The plan warns "do not assume that every existing noise parameter
uses those units" — they were inspected, and they do.

## The numerical check

`tests/test_t06_inference_service.py`:

| Test | Property |
|---|---|
| `test_a_day_of_bar_predictions_equals_one_daily_prediction` | a session predicted bar-by-bar accumulates exactly the covariance of one prediction across the whole session (`allclose`, atol 1e-12) |
| `test_a_split_session_break_adds_no_trading_time` | a two-window day counts 105 + 150 minutes, not 375 |
| `test_sessions_elapsed_is_the_plans_u_of_t` | a full session is `u = 1.0`; mid-session is strictly between 0 and 1 |
| `test_overnight_adds_no_process_noise_beyond_trading_time` | 15:30 → next 09:15 is `u = 0.0` |

The first of these is the one the plan asked for by name. It passes without
any change to C8.

## What this decision does not settle

- It does not calibrate `q_proc`. The value in use (`1e-3` per bar) is the
  declared research default and has not been fitted; nothing here changes
  that, and nothing here should be read as endorsing it.
- The `calendar` time basis remains a separate opt-in model whose `Q` would
  need its own calibration in its own units, exactly as
  `time_clock.py` already states.
- It says nothing about predictive skill. It is a units decision.
