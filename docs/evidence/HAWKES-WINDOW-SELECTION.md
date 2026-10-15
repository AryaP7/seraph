# C5 — Production Rolling-Window Selection (FR10/FR11, AMENDMENT-03)

**Decision: `window_days = 500`, `refit_every = 5`.**
Settled 2026-10-13 on git `f3eaac8`. Evidence:
`docs/evidence/20261012T174208Z-10-hawkes-window-selection.log` (60/250/500d) and
`docs/evidence/20261012T180114Z-11-hawkes-window-bracket.log` (750/1000d).
Both runs: `scripts/compare_hawkes_windows.py --points 24`, read-only, 213,751-bar
market-wide stream over ~2,850 sessions.

---

## 1. Why a selection was needed at all

`WINDOW_DAYS = 60` is a declared constant in `seraph/pillars/hawkes/engine.py`
whose **value was never validated**. The validated parameters
(`alpha ~ 0.0557`, `phi ~ 0.4837`, `n ~ 0.1079`, CV 2–4.1%) were estimated on
chronological folds of the **whole corpus** (85k–171k bars). A rolling production
estimate is a different object, and on 60-day windows the branching ratio's
coefficient of variation is **0.714** — it swings 0.0057 to 0.2034, a 36x ratio.
That is noise, not a state variable.

## 2. Selection rule, fixed before the experiment

Quoted from `scripts/compare_hawkes_windows.py`:

> **Selection rule, fixed in advance:** the window is chosen on stability,
> identifiability, out-of-sample likelihood and computational feasibility.
> It is explicitly NOT chosen for producing an `n` close to the validated 0.108.
>
> Out-of-sample per-bar NLL is **the comparable criterion**: the in-sample NLL of
> a longer window is not comparable to a shorter one, but the average NLL the
> fitted kernel assigns to the *following* unseen days is.

## 3. Measured results

| window | fits | unident | n mean | n sd | n CV | α CV | φ CV | **OOS NLL/bar** | s/fit |
|---|---|---|---|---|---|---|---|---|---|
| 60d | 24 | 0 | 0.0739 | 0.0527 | 0.714 | 0.858 | 0.842 | 0.23221 | 1.79 |
| 250d | 24 | 0 | 0.0847 | 0.0292 | 0.344 | 0.459 | 0.299 | 0.17622 | 8.45 |
| **500d** | 24 | 0 | 0.0948 | 0.0193 | 0.204 | 0.255 | 0.231 | **0.13253** | 17.14 |
| 750d | 24 | 0 | 0.0943 | 0.0130 | 0.137 | 0.124 | 0.167 | 0.15347 | 25.96 |
| 1000d | 24 | 0 | 0.0961 | 0.0131 | 0.137 | 0.112 | 0.136 | 0.14290 | 30.93 |

| window | n min | n max | n range | stationary | converged | ±5-session \|dn\| |
|---|---|---|---|---|---|---|
| 60d | 0.0057 | 0.2034 | 0.1976 | 100% | 24/24 | 0.0090 |
| 250d | 0.0346 | 0.1332 | 0.0986 | 100% | 24/24 | 0.0018 |
| **500d** | 0.0494 | 0.1241 | 0.0748 | 100% | 24/24 | **0.0012** |
| 750d | 0.0737 | 0.1215 | 0.0478 | 100% | 24/24 | 0.0006 |
| 1000d | 0.0720 | 0.1189 | 0.0469 | 100% | 24/24 | 0.0002 |

## 4. Applying the rule, criterion by criterion

**Identifiability — does not discriminate.** All five windows: 0 unidentifiable
fits, 24/24 converged, 100% stationary (`n < 1`). No candidate is rejected here.

**Stability — disqualifies 60d outright, then improves monotonically and
plateaus.** `n` CV falls 0.714 → 0.344 → 0.204 → 0.137 → 0.137. 60d is
unusable: the parameter's standard deviation is 71% of its mean. Improvement
stops between 750d and 1000d (both 0.137), so additional length buys no further
stability.

**Out-of-sample per-bar NLL — the designated comparable criterion. 500d is the
interior minimum.** 0.23221 → 0.17622 → **0.13253** → 0.15347 → 0.14290. The
first grid (60/250/500d) was monotone decreasing, which put the winner at the
grid boundary and left the optimum unbracketed; that is why the grid was
extended rather than the boundary point selected. With 750d and 1000d measured,
the minimum is interior at 500d.

This is a bias–variance trade, not a contradiction: windows longer than 500
sessions produce steadier parameters that are also **staler**, and they assign a
worse likelihood to the next five unseen days.

**Computational feasibility — 500d is the cheapest qualifying candidate.** At the
measured 17.14 s/fit, a daily refit over the corpus costs 818 min; at
`refit_every = 5` it costs **164 min**, against 248 min (750d) and 295 min
(1000d).

## 5. Why `refit_every = 5`

Measured, not assumed. The boundary-sensitivity probe shifts the window start by
±5 sessions and reports how far `n` moves. At 500d that is **|dn| = 0.0012**,
against `n`'s own corpus standard deviation of **0.0193** — i.e. a five-session
shift moves the estimate by about 6% of one standard deviation. Refitting every
fifth session therefore discards almost no information while cutting cost 5x.

## 6. Verdict

**`window_days = 500`, `refit_every = 5`.** It wins the criterion the experiment
designated as comparable, is adequately stable, is identifiable on every tested
point, and is the cheapest candidate that qualifies.

### Stated limitations

1. **The 500d-vs-1000d margin is not statistically separated.** 500d's OOS NLL is
   7.8% below 1000d's, but with 24 heavily-overlapping evaluation points no
   confidence interval can be attached from this experiment. The robust findings
   are that **60d is disqualified** and **>= 500d is required**; the choice among
   500/750/1000 rests on the designated criterion plus cost, not on a
   demonstrated significant difference.
2. **750d breaks tail monotonicity** (0.15347 against 1000d's 0.14290), which is
   further evidence that OOS NLL estimates at long windows carry noise as
   evaluation windows overlap more heavily.
3. **A rolling estimate is not the whole-corpus estimate.** The selected
   configuration yields `n` around 0.095 against the whole-corpus 0.1079. These
   are different objects. The window was **not** chosen for proximity — had it
   been, 1000d (`n` 0.0961) would have been preferred over 500d (0.0948).
4. **This selects an estimation window. It is not evidence of predictive skill.**
   The criterion is the likelihood the fitted kernel assigns to the next five
   days of *jump counts*. AMENDMENT-03 separately measured approximately no skill
   for this signal against future systemic risk, and nothing here revisits that.
   A validated window makes Pillar 1 a reproducible, identifiable, persistable
   state variable — not an early-warning signal.

## 7. Exact configuration to reproduce

```bash
# the selection experiment (read-only)
python scripts/compare_hawkes_windows.py --points 24 --windows 60,250,500
python scripts/compare_hawkes_windows.py --points 24 --windows 750,1000

# the production writer at the selected configuration
python scripts/write_hawkes_production.py --window-days 500 --refit-every 5          # dry run
python scripts/write_hawkes_production.py --window-days 500 --refit-every 5 --write  # persist to E6
```

`--window-days` has **no default**, deliberately, so the unvalidated `WINDOW_DAYS
= 60` constant cannot leak into a production run.
`tests/test_c5_hawkes_writer.py::test_window_days_has_no_default_so_an_unvalidated_constant_cannot_leak_in`
pins that.
