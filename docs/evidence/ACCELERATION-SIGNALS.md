# Are `dd_accel` and `rv_accel` Real Signals, or Artefacts?

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`. Nothing
committed. Database read-only; nothing written to any table or existing file.**

Evidence: `20261013T125931Z-40-acceleration-signal-validation.log` (the full run,
exit 0, 1,248 s); `20261013T133334Z-41-acceleration-causality-tests.log`
(causality suite plus its mutation check, both exit 0);
`20261013T134402Z-42-t3-power-persistent-alternatives.log` (exit 0, 1,588 s).
Code: `scripts/validate_acceleration_signals.py` (new),
`scripts/t3_power_persistent_alternatives.py` (new),
`tests/test_acceleration_signal_causality.py` (new, 21 tests, no database).
All machinery imported, never reimplemented: `t1_auc`, `shift_null_t1`,
`aaft_null_t1`, the Holm step from `scripts/calibrate_detection_claims.py`;
`t3_auc`, `relocation_null`, `aaft_null`, `ar1_stationary` from
`scripts/early_warning_power.py`; `build_features` from
`scripts/study_stress_candidates.py`; `auc` from `seraph.validation.harness`.

---

## 0. Summary

| hypothesis | verdict | the number that decides it |
|---|---|---|
| **H_C1** `dd_accel`/`rv_accel` use only information at or before `t` | **ACCEPTED** | max relative `|Δ|` = **0.000e+00** under both truncation and future-perturbation, across 17 cuts; **5/5** deliberately non-causal controls flagged |
| **H_C2** the advantage survives out-of-sample chronological evaluation | **ACCEPTED** | SPLIT-B evaluation span: `dd_accel` **0.6666** (p 0.0153/0.0060, no-signal p95 0.6165), `rv_accel` **0.7534** (p 0.0095/0.0087, p95 0.6775). Both clear their nulls; both survive Holm over 2 |
| **H_C3** they add information beyond simpler alternatives and the pillars | **ACCEPTED as pre-registered, but uniqueness NOT established** | both survive Holm over an **18**-wide family — and so do `rv_diff1` (p 0.0010), `dd_diff1` (0.0017) and the **raw sign-flipped market return** (0.0020) |
| T3 advance warning at 5/10/20/30 days | **NULL at every horizon** | best is `dd_accel` h=10 at **0.5514**, against a no-signal 95th percentile of **0.6308** |
| Is that T3 null informative, or just underpowered? | **INFORMATIVE — and the bound is now stronger than it was** | at the project horizon h=15 the test has **75%** power against a 75-session linear ramp and **78%** against an AR(1) build-up at δ=1 sd, vs **80%** against the rectangular step it was previously only tested on; type-I 2–8% at δ=0 (§6.1) |

### Two findings that belong in the summary, not in a footnote

**Neither signal would have been selected out of sample.** Leave-one-epoch-out
(SPLIT-C, §4.3) screens the 18-wide family on five onsets and evaluates on the
sixth. It would have picked **`dd_accel` on 0 of 6 folds and `rv_accel` on 2 of
6**; the usual winner is `semivar_20`. Their *performance* replicates out of
sample (§4.1–4.2); their *selection* does not. This is a materially negative
finding about the T1 result and it qualifies everything in §4 and §5.

**`dd_accel`'s full-span p = 0.0003 is censored, not measured.** It sits exactly
at the permutation-resolution floor `1/3001 = 0.000333`, which means no
permutation out of 3,000 reached the observed statistic — the true p could be
anywhere below that. The same applies to the six `p_aaft` values marked † in
§5.1. **Two p-values both at the floor cannot be compared**, so `dd_accel`'s
apparent rank-1 position in the Holm step-down is not evidence that it beats
`rv_diff1` or anything else at the floor.

**The one sentence worth carrying.** `dd_accel` and `rv_accel` are genuinely
causal and their contemporaneous-detection result genuinely replicates out of
sample — and they are *still* not early-warning signals, and they are *not*
measurably better than differencing a volatility series by one day or flipping
the sign of the market return. The surviving claim is narrow: these are real
coincident stress indicators, not forecasts and not a discovery.

---

## 1. Definitions, stated explicitly (they differ from Workstream B's)

Everything downstream depends on exactly which array is being differenced, and
two workstreams converged on similar names for different objects.

| this report | definition | Workstream B's `replay_crisis_warnings.py` |
|---|---|---|
| `drawdown` | `1 − px[t] / max(px[t−251 .. t])`, a **252-day rolling** peak; `px = exp(cumsum(lr))`, `lr` = cross-sectional mean log return of universe members | `1 − idx/running-max`, an **expanding** peak |
| `dd_accel` | `drawdown[t] − drawdown[t−5]` | `dd_accel_5` = same 5-day backward difference, but of the expanding-peak drawdown |
| `rv_level` | `hamilton_output.rv_t_yz` — Yang–Zhang from OHLC over a trailing 21 days, cross-sectional median, annualised | `rv_20` = trailing 20-day sd of `lr` |
| `rv_accel` | `rv_level[t] / mean(rv_level[t−19 .. t])` — a **ratio** to a 20-day trailing mean | `rv_accel_5` = `rv_20[t] − rv_20[t−5]`, a **difference** |

So `dd_accel` is near-identical across the two studies (the peak window differs);
`rv_accel` is a **different construct** — a ratio of a Yang–Zhang estimator, not
a difference of a return-sd estimator. The reconciliation in §6.2 is therefore
stronger than it looks for `dd_accel` and is a genuinely independent check for
`rv_accel`.

Sign conventions were fixed by economics before any AUC was seen: higher
volatility, wider spreads, higher absorption and deeper drawdown mean more risk,
so the raw return enters as `−lr`. AUC is one-sided throughout, as in the
original screen.

---

## 2. Pre-registration

Written into `scripts/validate_acceleration_signals.py`'s module docstring, and
printed at the head of log 40, before any result in it was computed.

**H_C1 (leakage).** ACCEPT iff all five hold: **(a)** rebuilding the pipeline
from inputs `[0 .. t*]` reproduces the full-sample value at `t*` to within 1e-12
relative, at every tested cut; **(b)** replacing every input after `t*` leaves
values up to `t*` bit-identical; **(c)** four deliberately non-causal variants —
centred window, forward difference, full-sample normalisation, reversed
cumulative — each fail (a) or (b); **(d)** the T1 label at `t` depends only on
breaks at `≤ t`, and no observed crisis window wraps the grid; **(e)** every
standardisation on the path to a reported number is causal, or provably absent
from it. REJECT if (a), (b) or (d) fails, or if (c) shows no teeth.

**H_C2 (out of sample).** Splits fixed before running:

* **SPLIT-B (primary)** — equal onset counts. Select `grid start .. 2018-12-31`
  (`gfc_2008`, `taper_2013`, `ilfs_2018`); evaluate `2019-01-01 .. grid end`
  (`covid_2020`, `tightening_2022`, `tariff_2026`).
* **SPLIT-A (secondary)** — the project's existing span boundary. Select
  `.. 2016-12-31` (2 onsets); evaluate `2017-01-01 ..` (4 onsets).
* **SPLIT-C (secondary)** — leave-one-epoch-out: screen on five onsets, evaluate
  on the sixth alone.

ACCEPT iff, on SPLIT-B's evaluation span, the AUC exceeds the 95th percentile of
**both** nulls on that span **and** `max(p_shift, p_aaft) ≤ 0.05`. PARTIAL if it
clears nominal 0.05 but not the 95th percentile, or clears on one split only.
REJECT if the out-of-sample AUC falls inside its own null. Multiplicity here is
2 pre-specified signals, not 15; Holm over 2 is also reported.

**H_C3 (incremental value).** Comparators fixed before running: raw daily return
(sign-flipped), absolute return, realised-volatility level, its 20-day trailing
mean, drawdown level, the plain 1-day difference of realised volatility and of
drawdown, plus RMT `λ₁/N`, Hawkes `n`, and both full-span CSRS configurations.
ACCEPT iff **(a)** both signals survive Holm over the full expanded primary
family, whose size is reported and is **larger** than the original 15 — so the
correction gets strictly stricter, never looser — **and (b)** each signal, after
causal orthogonalisation against each comparator, still clears its own null at
nominal 0.05. PARTIAL if (a) holds and (b) fails somewhere. REJECT if (a) fails.

**T1 and T3 are reported separately and are not traded off.** A T1 pass says the
signal is lit *during* a crisis. It is not evidence of any ability to warn
*before* one. T3 is evaluated at lead horizons of 5, 10, 20 and 30 trading days
against a no-signal distribution re-derived **per horizon**, because the horizon
changes the null's width.

**Excluded on purpose:** `hamilton_output.xi_*`. The persisted values are not
established as causal — `HAMILTON-CAUSAL-POSTFIX.md` states the causal
walk-forward output was deliberately *not* persisted — so admitting them as a
comparator would import an unaudited look-ahead into a leakage audit.

**Permutation-resolution floor.** 3,000 permutations per null, so the smallest
reportable p is `1/3001 = 0.000333`. Holm's tightest threshold at 18 comparisons
is `0.05/18 = 0.00278`, which is above the floor, so the correction is
resolvable rather than unreachable by construction. **Any p printed as 0.0003 is
censored at the floor, not measured** — it means no permutation out of 3,000
reached the observed statistic, and the true p could be smaller. This affects
`dd_accel`'s full-span p and six of the `p_aaft` values in §5.

Grid: **5,362 trading days, 2005-01-04 .. 2026-08-21**, 6 onsets at indices
`[924, 2085, 3404, 3751, 4215, 5224]`.

---

## 3. H_C1 — leakage: ACCEPTED, with one measured blind spot

### 3.1 The arithmetic

Two tests, 17 cut indices (`[300, 700, 924, 934, 2085, 2095, 2681, 3404, 3414,
3751, 3761, 4215, 4225, 4962, 5224, 5234, 5361]` — deliberately including every
onset and the day after it).

* **(a) Truncation invariance.** Rebuild the entire feature pipeline from
  `dates[:t*+1], lr[:t*+1], rv[:t*+1], ar[:t*+1], bas[:t*+1]`, then compare the
  value **at** `t*`. A centred window, a forward difference or a full-sample
  normaliser all read an index above `t*` and so cannot reproduce it.
* **(b) Future perturbation.** Keep full length but replace every input after
  `t*`: `lr → 7·lr + 0.013 + noise`, `rv → 3·rv + 5`, `ar → 1 − ar`,
  `bas → 11·bas + 1`. Every value up to `t*` must be bit-identical.

```
series                         max rel |delta| at t*   max rel |delta| on past  verdict
dd_accel                                   0.000e+00                 0.000e+00  CAUSAL
rv_accel                                   0.000e+00                 0.000e+00  CAUSAL
drawdown, rv_level, semivar_20, jump_int_20, vol_of_vol, ar_t, bas_t,
neg_return, abs_return, rv_ma20, rv_diff1, dd_diff1 ......... all 0.000e+00  CAUSAL
all six orthogonalised residual series ...................... all 0.000e+00  CAUSAL
LEAK centred-window                 inf (finiteness)                 8.957e-01  LEAK
LEAK forward-difference             inf (finiteness)                 1.971e+00  LEAK
LEAK full-sample-norm                      2.380e-01                 9.185e-01  LEAK
LEAK reversed-cumulative                   1.181e+00                 3.331e+01  LEAK
LEAK future-peak-drawdown           inf (finiteness)                 5.072e+00  LEAK
BLINDSPOT scale-inv-reversal               1.137e-13                 4.116e-13  GREY ZONE
```

The criterion is deliberately two-sided: a causal series must be **exactly**
invariant (`0.000e+00`, not "within tolerance"), and a leak must be caught
**clearly** (`> 1e-6`), not at float-rounding scale. **5/5 non-causal controls
were flagged. The audit has teeth.**

### 3.2 The definitions, checked as arithmetic rather than read

```
dd_accel[t] == drawdown[t] - drawdown[t-5]  : max|delta| = 0.000e+00 over 5,295 cells   (BACKWARD 5-day difference)
rv_accel[t] == rv[t] / mean(rv[t-19..t])    : max|delta| = 0.000e+00 over 5,358 cells   (TRAILING ratio)
roll(a,w,f)[i] == f(a[i-w+1..i])            : max|delta| = 0.000e+00                    (window ENDS at i)
px = exp(cumsum(lr)) runs forward           : px[0] == exp(lr[0]) = 1.0041807746         (reversed would not match)
```

Each is also pinned against its own counterfactual in
`tests/test_acceleration_signal_causality.py`: `dd_accel` is asserted *not* to
match the forward difference, `rv_accel` *not* to match the full-sample
normaliser, `roll` *not* to match a centred window.

### 3.3 Labels and standardisation

```
observed crisis windows that wrap the grid: 0  (the label is purely backward)
y[t] reproduced from breaks at indices <= t only: IDENTICAL (0 cells differ)
T1 positives: 180 days from 6 onsets (30 per onset, FR32)
window_from(as_of=2020-06-15, years=5) admits a value dated after as_of: no
trailing_pct on a rising series: last percentile 1.0000; on a falling series 0.0014
```

FR32's T1 window runs **forward from the break**, so `y[t] = 1` iff a break
occurred in `(t−30, t]` — a function of the past only. The `% n` modulo inside
`t1_auc` exists for the shifted null and *does* wrap; it is harmless for the
observed statistic only because no real onset sits within 30 days of the grid
end, which is now asserted rather than assumed (and pinned by
`test_t1_label_wraps_the_grid_when_an_onset_sits_at_the_end`).

On FR28: `window_from` selects on the ISO string with an inclusive upper bound at
`as_of`, so it is strictly causal, and `ECDF_WINDOW_YEARS == 5` as FR28 requires.
**But the more important fact is that no ECDF is on the path at all.** `t1_auc`
scores the **raw** series, and AUC is rank-based (Mann–Whitney U), so no
standardisation of any kind enters any AUC in this report. `trailing_pct` feeds
only the alert/precision/recall columns of `study_stress_candidates.py`, which
nothing here uses.

### 3.4 The blind spot, and the caveat the tests cannot reach

**Measured blind spot.** A reversed cumulative placed *behind a scale-invariant
transform* is invisible to both tests: `drawdown = 1 − px/peak` is unchanged when
`px` is multiplied by a constant, and truncating a reversed `cumsum` rescales
`px` by exactly such a constant. Measured at `1.137e-13` and `4.116e-13` — float
rounding. This is reported rather than hidden, is asserted as a test
(`test_the_one_form_these_tests_cannot_see`), and is why §3.2 checks the forward
direction of `np.cumsum` directly instead of relying on invariance alone.

**Caveat outside the code.** `daily_prices.adj_close` carries split and dividend
adjustment factors applied retroactively, so the price level at `t` embeds
corporate actions announced after `t`. Log returns are invariant to a constant
factor, so this perturbs only the handful of days on which an adjustment lands.
It is a real but small look-ahead that lives in the **data**, not the feature
code, and neither test can see it. Quantifying it would need an unadjusted price
series.

**Verdict: H_C1 ACCEPTED.** Nothing in the rest of this report is invalidated by
leakage in these two signals.

---

## 4. H_C2 — out of sample: ACCEPTED, with the advantage shrinking

### 4.1 SPLIT-B (primary, 3 onsets each side)

Selection `2005-01-04 .. 2018-12-31` (3,471 days); evaluation
`2019-01-01 .. 2026-08-21` (1,891 days). Features are computed causally and are
allowed to use pre-2019 history at a post-2019 `t` — that is history, not future.
Each span gets its own null, so shifts wrap within the span and negatives are
drawn only from it.

| series | in AUC | in p | in p95 | **out AUC** | out p_shift | out p_aaft | out p95 | out |
|---|---|---|---|---|---|---|---|---|
| **dd_accel** | 0.7467 | 0.0023 | 0.6197 | **0.6666** | 0.0153 | 0.0060 | 0.6165 | **SIG** |
| **rv_accel** | 0.7912 | 0.0060 | 0.6914 | **0.7534** | 0.0095 | 0.0087 | 0.6775 | **SIG** |
| drawdown | 0.8681 | 0.0267 | 0.7433 | 0.5940 | 0.2073 | 0.2076 | 0.6775 | not sig |
| jump_int_20 | 0.8189 | 0.0050 | 0.6902 | 0.6872 | 0.0661 | 0.0470 | 0.6914 | not sig |
| semivar_20 | 0.8086 | 0.0107 | 0.7206 | 0.7629 | 0.0307 | 0.0217 | 0.7264 | SIG |
| vol_of_vol | 0.6943 | 0.0720 | 0.7114 | 0.7908 | 0.0175 | 0.0073 | 0.7201 | SIG |
| rv_level | 0.6566 | 0.0813 | 0.6773 | 0.6937 | 0.1111 | 0.0860 | 0.7409 | not sig |
| rv_diff1 | 0.7101 | 0.0010 | 0.6136 | 0.6780 | 0.0016 | 0.0030 | 0.6070 | SIG |
| dd_diff1 | 0.6217 | 0.0040 | 0.5672 | 0.5900 | 0.0069 | 0.0137 | 0.5648 | SIG |
| neg_return | 0.6376 | 0.0040 | 0.5772 | 0.5900 | 0.0185 | 0.0080 | 0.5649 | SIG |
| abs_return | 0.6704 | 0.0013 | 0.5904 | 0.6173 | 0.0206 | 0.0197 | 0.5932 | SIG |
| CSRS 3p fullspan | 0.7004 | 0.0423 | 0.6843 | 0.5872 | 0.2729 | 0.2746 | 0.7351 | not sig |
| CSRS 2p fullspan | 0.5462 | 0.3569 | 0.6468 | 0.4745 | 0.5664 | 0.5575 | 0.7233 | not sig |
| rmt λ₁/N | 0.4785 | 0.6681 | 0.6172 | 0.3821 | 0.8408 | 0.8377 | 0.7247 | not sig |
| hawkes n | — | — | n/a | 0.5887 | 0.2311 | 0.2329 | 0.6924 | not sig |

Holm over the 2 pre-specified signals on the evaluation span: `rv_accel`
p = 0.0095 ≤ 0.0250 **survives**; `dd_accel` p = 0.0153 ≤ 0.05 **survives**.

**The control that failed is what makes this informative.** `drawdown` is the
best in-sample series at 0.8681 and collapses to **0.5940 (p 0.21)** out of
sample, inside its own null. The 3-pillar CSRS does the same (0.7004 → 0.5872,
p 0.27). So the split is capable of destroying a selection artefact, and it did
not destroy these two.

**The advantage does shrink.** `dd_accel` loses 0.080 of AUC (0.7467 → 0.6666)
and its out-of-sample margin over its own null is only **0.0501**. `rv_accel`
loses 0.038 (0.7912 → 0.7534), margin **0.0759**. Rank among 17–18 series:
`dd_accel` 5th in-sample → 7th out; `rv_accel` 4th → 3rd.

### 4.2 SPLIT-A (secondary, 2 onsets select / 4 evaluate)

Both still clear: `dd_accel` 0.7971 → **0.6602** (p 0.0034/0.0050, p95 0.5984);
`rv_accel` 0.7904 → **0.7660** (p 0.0008/0.0010, p95 0.6412). On this split
`dd_accel` falls to **rank 10 of 18** out of sample while `rv_accel` holds rank 4
— significance survives, pre-eminence does not.

### 4.3 SPLIT-C — leave-one-epoch-out, and the negative sub-finding

| held out | screen winner on the other 5 | winner's held-out AUC | dd_accel | rv_accel |
|---|---|---|---|---|
| gfc_2008 | semivar_20 (0.7467) | 0.9456 | 0.8757 | 0.9315 |
| taper_2013 | semivar_20 (0.8185) | 0.5951 | 0.7199 | 0.6324 |
| ilfs_2018 | rv_accel (0.7637) | 0.7892 | 0.6433 | 0.7892 |
| covid_2020 | semivar_20 (0.7515) | 0.9223 | 0.8113 | 0.9572 |
| tightening_2022 | rv_accel (0.8041) | 0.5916 | 0.5851 | 0.5916 |
| tariff_2026 | jump_int_20 (0.8147) | 0.4287 | 0.5678 | 0.6759 |

Held-out AUCs — `dd_accel` `[0.8757, 0.7199, 0.6433, 0.8113, 0.5851, 0.5678]`,
mean 0.7005; `rv_accel` `[0.9315, 0.6324, 0.7892, 0.9572, 0.5916, 0.6759]`,
mean 0.7630. Ranks of 18: `dd_accel` `[10, 2, 12, 9, 9, 5]`, `rv_accel`
`[6, 4, 8, 1, 8, 2]`.

**Report this as negative:** a leave-one-epoch-out screen would have selected
`dd_accel` on **none** of the six folds, and `rv_accel` on only two. Its
performance *replicates*; its *selection* does not. The screen's winner is
usually `semivar_20`, which is also the series `DETECTION-CALIBRATION.md` §4
already flagged as beating the composite.

### 4.4 The limitation this cannot remove

The original candidate list was drawn up with knowledge of the whole corpus. No
*parameter* was fitted — which is why a pure re-measurement is the right
out-of-sample test — but the **candidate-list selection** channel remains:
SPLIT-B's evaluation span contributed 3 of the 6 onsets to the pooled statistic
these two were selected on, so the two spans are not statistically independent.
SPLIT-C addresses this more directly and returns the mixed answer above. Nothing
in this study was tuned on any evaluation span.

**Verdict: H_C2 ACCEPTED** on the pre-registered criterion, on both splits, with
the shrinkage and the SPLIT-C selection failure recorded as material
qualifications.

---

## 5. H_C3 — incremental value: accepted as pre-registered, uniqueness refuted

### 5.1 (a) Marginal screen, Holm over 18

The family is **18** series, three wider than `DETECTION-CALIBRATION.md`'s 15, so
the correction is strictly stricter here. Tightest threshold `0.05/18 = 0.00278`;
resolution floor `0.000333`.

| series | AUC | p_shift | p_aaft | max p | null p95 | ≥ p95 |
|---|---|---|---|---|---|---|
| **rv_accel** | **0.7706** | 0.0017 | 0.0003† | 0.0017 | 0.6223 | yes |
| semivar_20 | 0.7832 | 0.0067 | 0.0007 | 0.0067 | 0.6554 | yes |
| jump_int_20 | 0.7515 | 0.0040 | 0.0013 | 0.0040 | 0.6379 | yes |
| vol_of_vol | 0.7278 | 0.0133 | 0.0020 | 0.0133 | 0.6450 | yes |
| drawdown | 0.7185 | 0.0277 | 0.0083 | 0.0277 | 0.6562 | yes |
| **dd_accel** | **0.7064** | 0.0003† | 0.0003† | 0.0003† | 0.5806 | yes |
| **rv_diff1** | 0.6947 | 0.0010 | 0.0003† | **0.0010** | 0.5726 | yes |
| CSRS 3p fullspan | 0.6573 | 0.0333 | 0.0407 | 0.0407 | 0.6459 | yes |
| **abs_return** | 0.6392 | 0.0037 | 0.0003† | 0.0037 | 0.5665 | yes |
| **neg_return** | 0.6133 | 0.0020 | 0.0003† | **0.0020** | 0.5492 | yes |
| rv_level | 0.6098 | 0.1073 | 0.1050 | 0.1073 | 0.6412 | no |
| **dd_diff1** | 0.6050 | 0.0017 | 0.0003† | 0.0017 | 0.5453 | yes |
| hawkes n | 0.5937 | 0.2536 | 0.2086 | 0.2536 | 0.7525 | no |
| CSRS 2p fullspan | 0.5218 | 0.4072 | 0.3989 | 0.4072 | 0.6326 | no |
| rv_ma20 | 0.5172 | 0.4092 | 0.4362 | 0.4362 | 0.6484 | no |
| ar_t | 0.4453 | 0.7038 | 0.7021 | 0.7038 | 0.6693 | no |
| rmt λ₁/N | 0.4283 | 0.8001 | 0.7924 | 0.8001 | 0.6336 | no |
| bas_t | 0.3799 | 0.9080 | 0.8980 | 0.9080 | 0.6545 | no |

† at the permutation-resolution floor `1/3001`; censored, not measured.

Holm step-down over 18 — **7 survive**, in this order:

```
 1. dd_accel     p=0.0003  thr=0.00278  survives
 2. rv_diff1     p=0.0010  thr=0.00294  survives
 3. dd_diff1     p=0.0017  thr=0.00313  survives
 4. rv_accel     p=0.0017  thr=0.00333  survives
 5. neg_return   p=0.0020  thr=0.00357  survives
 6. abs_return   p=0.0037  thr=0.00385  survives
 7. jump_int_20  p=0.0040  thr=0.00417  survives
 8. semivar_20   p=0.0067  thr=0.00455  does NOT survive — step-down stops
```

**Both target signals survive, so (a) passes.** And the headline finding of this
section is what else survives with them: **`rv_diff1` — realised volatility
minus yesterday's realised volatility — has a *lower* p-value than `rv_accel`,
and the raw sign-flipped market return `neg_return` survives too.** The claim
"the two survivors are both second-difference quantities, and that is the
interesting substantive result" (`DETECTION-CALIBRATION.md` §2) **does not hold
once trivially simpler alternatives are added to the family.** A 1-day
difference and a raw daily return are not second differences.

Why p-ranks and AUC-ranks disagree: each series is judged against **its own**
null, and null width depends on the series' own autocorrelation. `rv_accel`'s
null p95 is 0.6223 against `rv_diff1`'s 0.5726. By *margin over its own null*
`rv_accel` leads (+0.148 vs +0.122) even though its p is larger. Both readings
are reported; neither is selected after the fact.

### 5.2 (b) Conditional screen — causal orthogonalisation

Each signal residualised against each comparator by an OLS fitted strictly on
indices `[t−1260, t−1]` (5 years, matching FR28's window; minimum 250
observations). The fit never sees index `t`. The implementation is pinned against
a brute-force explicit-slice fit to 1e-8, and asserted *not* to match a fit that
includes `t` (`test_causal_residual_matches_an_explicit_backward_ols`).

| residual | AUC | p_shift | p_aaft | max p | null p95 | verdict |
|---|---|---|---|---|---|---|
| rv_accel ⟂ rv_ma20 | **0.7888** | 0.0013 | 0.0003† | 0.0013 | 0.6281 | SIG |
| rv_accel ⟂ rmt λ₁/N | 0.7519 | 0.0007 | 0.0003† | 0.0007 | 0.6178 | SIG |
| rv_accel ⟂ rv_diff1 | 0.7355 | 0.0017 | 0.0003† | 0.0017 | 0.6121 | SIG |
| rv_accel ⟂ rv_level | 0.6726 | 0.0087 | 0.0173 | 0.0173 | 0.6319 | SIG |
| dd_accel ⟂ rmt λ₁/N | 0.6754 | 0.0003† | 0.0003† | 0.0003† | 0.5826 | SIG |
| dd_accel ⟂ dd_diff1 | 0.6745 | 0.0007 | 0.0003† | 0.0007 | 0.5702 | SIG |
| dd_accel ⟂ drawdown | 0.6601 | 0.0003† | 0.0027 | 0.0027 | 0.5871 | SIG |
| dd_accel ⟂ rv_level | 0.6451 | 0.0040 | 0.0020 | 0.0040 | 0.5832 | SIG |

**All 8 clear nominal 0.05, and all 8 survive Holm over the 8-wide
orthogonalised family.** So (b) passes: neither signal is a repackaging of its
comparator. `rv_accel ⟂ rv_ma20` at 0.7888 even exceeds the raw `rv_accel`,
which is the cleanest statement available that the *ratio* carries information
the *level* of the same smoothed series does not.

### 5.3 The conservative pooled correction

Every T1 comparison in this study — 18 marginal plus 8 conditional — pooled into
a single 26-wide family, tightest threshold `0.05/26 = 0.00192`. Eleven survive,
including `dd_accel` (rank 1) and `rv_accel` (rank 8), and also `rv_diff1`
(rank 5), `dd_diff1` (rank 7) and `neg_return` (rank 10). `abs_return` at
p = 0.0037 is where the step-down stops.

### 5.4 Verdict

**H_C3 ACCEPTED on the pre-registered criterion** — (a) and (b) both pass, under
a correction strictly stricter than the one that produced the original claim.

**But the pre-registered criterion asked the weaker of two questions.** It asked
whether these signals *add* information beyond the comparators (they do), not
whether they are *better than* them (they are not, measurably). Four trivially
simpler series — a 1-day volatility difference, a 1-day drawdown difference, the
absolute return, and the sign-flipped raw return — survive the same correction
alongside them. **The uniqueness of the acceleration construction is NOT
established**, and that limitation is the honest cost of having stated the
criterion before seeing the result rather than after.

---

## 6. T3 — advance warning: NULL at every horizon

**This section is deliberately separate from §4 and §5 and must not be read as
continuous with them.** T1 asks whether the signal is lit *while* the crisis is
happening. T3 asks whether it was lit *before*, and it drops every in-crisis day
from the sample so that a model cannot "predict" a crisis from inside one. **A
strong T1 result is not evidence of T3 capability.** That is exactly the contrast
these two sections exist to keep visible.

**The sharpest single illustration of that separation comes from the series that
*wins* T1 selection.** `semivar_20` is the leave-one-epoch-out winner on 3 of 6
folds (§4.3) and has the highest full-span T1 AUC of any genuine candidate
(0.7832, §5.1). Workstream B's causal replay measures it warning before **0 of 6**
onsets at every horizon from 5 to 30 days, **p = 1.0000** against a no-skill rate
of 0.04 ± 0.08 (`CRISIS-REPLAY.md`). The best contemporaneous detector in the
corpus has **no advance-warning capability whatsoever**. T1 and T3 are not two
measurements of one ability; they are different objectives, and ranking well on
the first predicts nothing about the second.

Reproduction self-check at h = 15 against `EARLY-WARNING-POWER.md` §4:
`dd_accel` 0.5924 and `rv_accel` 0.4229 reproduced exactly, so the horizon sweep
runs through that module's own code path with only `LEAD_H` rebound.

| h | series | T3 AUC | shift μ | p_shift | aaft μ | p_aaft | null p95 | no-signal p95 | power at δ=1 sd | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | dd_accel | 0.5340 | 0.4994 | 0.3387 | 0.4957 | 0.3497 | 0.6618 | 0.6418 | 92% | not sig |
| 5 | rv_accel | 0.4523 | 0.5007 | 0.6613 | 0.5044 | 0.6713 | 0.6825 | 0.6418 | 92% | not sig |
| 10 | dd_accel | **0.5514** | 0.5014 | 0.2557 | 0.4960 | 0.2378 | 0.6374 | 0.6308 | 83% | not sig |
| 10 | rv_accel | 0.4318 | 0.4968 | 0.7253 | 0.5030 | 0.7353 | 0.6672 | 0.6308 | 83% | not sig |
| 20 | dd_accel | 0.5296 | 0.4994 | 0.2777 | 0.5014 | 0.3357 | 0.6022 | 0.6359 | 93% | not sig |
| 20 | rv_accel | 0.4218 | 0.5012 | 0.8072 | 0.4971 | 0.7982 | 0.6355 | 0.6359 | 93% | not sig |
| 30 | dd_accel | 0.5018 | 0.5015 | 0.5125 | 0.5002 | 0.4785 | 0.5837 | 0.6911 | 82% | not sig |
| 30 | rv_accel | 0.4491 | 0.5002 | 0.7483 | 0.4978 | 0.7313 | 0.6191 | 0.6911 | 82% | not sig |

Holm over the 8 comparisons (2 signals × 4 horizons): the smallest p is 0.2557,
against a threshold of 0.00625. **None survives. None comes close.**

**This is an informative null, not an underpowered one.** The δ=1 sd power
column is 82–93% at every horizon: a clean 1-within-series-sd step confined to
the `h` days before every onset would have been found four times out of five.
Nothing in the corpus produces one. `rv_accel` is **below chance at every
horizon** (0.42–0.45), which is consistent with a ratio-to-trailing-mean being
mechanically near 1 in the quiet run-up.

`dd_accel`'s best, 0.5514 at h=10, is below the no-signal 95th percentile
(0.6308) on both the per-horizon synthetic control and its own two permutation
nulls. Both null means sit at 0.496–0.502 at every horizon, which is the sanity
check that the lead windows carry no information at an arbitrary phase.

### 6.1 Is that null informative? Power against a *persistent* alternative

Evidence: `20261013T134402Z-42-t3-power-persistent-alternatives.log` (exit 0,
1,588 s). Code: `scripts/t3_power_persistent_alternatives.py` (new).

The 82–93% power quoted above, and `EARLY-WARNING-POWER.md`'s 85–98%, are power
against a **rectangular step of δ sd confined to exactly the days T3 labels
positive**. That is the single most favourable alternative the test can face —
signal on precisely where the label is on, off precisely where it is off. A
systemic-risk thesis does not predict that; it predicts a **build-up**. So the
existing bound might have bounded the wrong thing, which would have made both
this report's and `CRISIS-REPLAY.md`'s negatives weaker than stated.

Three shapes, all normalised to the **same peak amplitude** δ so that the sweep
varies shape at fixed amplitude and cannot be confounded with it. `L` = build-up
length, `D` = 30 = the FR32 crisis window, `φ_d` = 0.9973 (measured `rv_t_yz`
lag-1 autocorrelation):

* **step** — `δ` on `[i−h, i)`, 0 elsewhere. The existing reference.
* **ramp** — linear `0 → δ` over `[i−L, i)`, then linear `δ → 0` over `[i, i+D)`.
* **ar1drift** — `s[u] = φ_d·s[u−1] + (1−φ_d)·A` on `[i−L, i)` from `s = 0`, with
  `A = δ/(1 − φ_d^L)` so `max(s) = δ` exactly; same fall-back.

The fall-back sits entirely inside T3's own exclusion window, so it is present
for realism and has no effect on the statistic. Everything — shapes,
normalisation, the δ grid (unchanged from `early_warning_power.py`), the horizons
and the build-up lengths — was fixed in the script's docstring before the first
run.

**The mechanism, and why shape matters at all.** Measured at δ = 1.0:

| h | shape | peak | mean amplitude on T3-positive days | days carrying signal | of which labelled **NEGATIVE** |
|---|---|---|---|---|---|
| 15 | step | 1.000 | 1.0000 | 90 | **0** |
| 15 | ramp | 1.000 | 0.9067 | 450 | **360** |
| 15 | ar1drift | 1.000 | 0.9147 | 450 | **360** |
| 75 | step | 1.000 | 1.0000 | 450 | 0 |
| 75 | ramp | 1.000 | 0.5067 | 450 | 0 |
| 75 | ar1drift | 1.000 | 0.5235 | 450 | 0 |

At `h = 15` a 75-session ramp puts **360 of its 450 signal-carrying days on days
T3 labels negative**, which pushes the AUC *down*, not up. That is the whole
mechanism by which shape could have destroyed the power claim. It does not,
and the table also shows why: because the ramp **peaks at onset**, its final 15
days still carry mean amplitude **0.9067** — almost the step's full 1.0 — so the
labelled window is nearly as well served. The contamination of the negative days
costs some power; the near-peak loading of the positive days preserves most of it.

**Power at the project horizon `h = 15`, `L = 75`, 60 draws/cell, 200 perms/null:**

| shape | δ=0 | δ=0.5 | δ=1.0 | δ=1.5 | δ=2.0 | δ=3.0 | δ=4.0 |
|---|---|---|---|---|---|---|---|
| step (reference) | 3% | 30% | **80%** | 100% | 100% | 100% | 100% |
| **ramp** | 7% | 47% | **75%** | 97% | 100% | 100% | 100% |
| ar1drift | 2% | 35% | **78%** | 95% | 100% | 100% | 100% |

(power under the conjunction `max(p_shift, p_aaft) ≤ 0.05`, the rule the project
uses for a verdict; per-null columns 77/77% and 80/78% at δ=1.0 are in the log)

**Type-I error at δ=0 is 2–8% against a nominal 5% across all three shapes at
`h = 15`**, so the test is calibrated and the power numbers mean something.
Build-up length barely matters at this horizon: `L = 60` gives 82% (ramp) and
80% (ar1drift), `L = 90` gives 80% and 82%.

**The conclusion the pre-registered rule licenses.** The rule was: *downgrade
"SERAPH shows no advance warning" to "advance warning is untestable at six
onsets against the signal shape a systemic-risk thesis predicts" if ramp power at
δ = 1.0 falls below ~50%.* Measured: **75%**. That clears the threshold
comfortably, so **the rule licenses the existing conclusion.** The T3 negative is
informative, and it now holds against a persistent build-up as well as against a
step — a *strengthening* of the bound, not a weakening. `CRISIS-REPLAY.md`'s
"bounded, not absolute" phrasing is supported, and is better supported than it
was when it rested on the step alone.

**Cross-check at the matched horizon, which is materially worse.** At `h = 75`,
ramp power at δ = 1.0 collapses to **37%** (ar1drift 35%), against the step's
88% on the same horizon — and 37% is *below* the rule's 50% line. The mechanism
table explains it exactly: at `h = 75` the ramp's mean amplitude on positive days
is **0.5067** against the step's 1.0000, because a linear rise averages half its
peak over its own length. The same holds at `L = 60, h = 60` (32%) and
`L = 90, h = 90` (32%).

**This is a sensitivity, not the project-relevant row.** FR32's early-warning
window is `LEAD_WINDOW_DAYS = (5, 15)` — the project's T3 objective is defined at
5–15 sessions, which is what `h = 15` measures and what both reports' claims rest
on. The honest statement of the limit is therefore narrower than the headline:
**at the horizon SERAPH actually specifies, the T3 negative is informative; at a
60–90 session horizon the test would be underpowered against a gradual build-up,
so a long-lead advance-warning claim is untestable on six onsets either way.**
Nobody has made a long-lead claim, so this costs nothing — but it bounds what any
future one could assert. Type-I at `h = 75` also runs wider (3–12% vs 2–8%),
which is a second reason not to lean on that row.

**The real signals at the matched horizons 60/75/90**, never tested before (log 40
stopped at h=30): `dd_accel` 0.5415 / 0.5561 / 0.5534 and `rv_accel` 0.5281 /
0.5330 / 0.5168. `dd_accel`'s nominal `p_shift` reaches 0.0280 at h=75 and h=90 —
the closest anything in this corpus has come to a T3 result — but its AUC sits
**below the δ=0 synthetic no-signal 95th percentile (0.6343, 0.6360)** at both,
and **none of the 6 comparisons survives Holm** (tightest threshold 0.00833;
smallest p 0.0330). Not significant, not a finding, and recorded so it is not
rediscovered as one.

### 6.2 Reconciliation with Workstream B's independent replay

`CRISIS-REPLAY.md` evaluated `dd_accel_5` and `rv_accel_5` (definitions in §1 —
`dd_accel_5` nearly matches `dd_accel`; `rv_accel_5` is a different construct
from `rv_accel`) under a causal trailing-5-year 95th-percentile alert rule over
6 epochs × 5 lead horizons, and found 2/6 and 2/6 warnings at 20–30 days with
relocation-null **p = 0.3398** and **0.7111** against a Holm threshold of 0.005
over 10 comparisons.

Those sit **inside this study's measured ranges**: `dd_accel` p_shift 0.2557 to
0.3387 across h = 5..30, `rv_accel` 0.6613 to 0.8072. Two implementations with
different drawdown-peak conventions, a different volatility estimator, a
different `rv` transform (ratio vs difference), a different decision rule
(threshold-crossing vs AUC) and different horizon grids agree to within the
granularity of a 6-event permutation test. **T3 is null under both.**

On calibration, Workstream B measured Brier skill ≈ 0 (−0.018 for `dd_accel_5`,
−0.033 for `rv_accel_5`), i.e. no better than the 3.36% base rate, and noted
that the low ECE (0.018, 0.024) is an artefact of units rather than calibration
skill. This study measured no calibration at all and takes that result as
standing. **The low ECE is not credited as skill anywhere in this report.**

---

## 7. Stability and sensitivity — exploratory

Labelled exploratory and excluded from every Holm family above, deliberately. No
variant is selected and no claim is made from this section: screening windows and
then reporting the best one is precisely the error this study exists to catch.
Any claim about a variant would need its own correction.

**Acceleration window** (`dd_accel` is k = 5; k = 1 is a plain 1-day difference):

```
   k   T1 AUC  p_shift   p_aaft  null p95  T3 h=15
   1   0.6050   0.0017   0.0003    0.5450   0.5437
   2   0.6383   0.0020   0.0003    0.5557   0.5527
   3   0.6686   0.0007   0.0003    0.5649   0.5648
   5   0.7064   0.0003   0.0003    0.5806   0.5924
  10   0.7614   0.0003   0.0003    0.6116   0.5794
  20   0.7740   0.0040   0.0010    0.6424   0.4713
```

**`rv_accel` denominator window** (`rv_accel` is w = 20):

```
   w   T1 AUC  p_shift   p_aaft  null p95  T3 h=15
   5   0.7263   0.0003   0.0003    0.5916   0.4858
  10   0.7524   0.0003   0.0003    0.6057   0.4517
  20   0.7706   0.0003   0.0003    0.6201   0.4229
  40   0.7830   0.0043   0.0010    0.6433   0.4322
  60   0.7646   0.0047   0.0017    0.6509   0.4748
```

**Causal trailing-mean smoothing** (m days): `dd_accel` 0.7064 → 0.7625 as m goes
1 → 10; `rv_accel` 0.7706 → 0.7538. All remain significant.

**Reading.** T1 significance is **stable**: every one of the 11 window variants
and 8 smoothing variants clears both nulls. T1 AUC is **monotone in the window**
for `dd_accel` (0.605 at k=1 to 0.774 at k=20) — a longer difference is a better
coincident detector, which is unsurprising since it converges on the drawdown
level itself. T3 is **flat and null everywhere**: 0.47–0.59 for `dd_accel`,
0.42–0.49 for `rv_accel`, across every window tried. **No window choice turns
either signal into a forecast.**

**Per sub-period** (grid split into thirds):

| series | period | onsets | T1 AUC | p_shift | p_aaft | null p95 |
|---|---|---|---|---|---|---|
| dd_accel | 2005-01-04..2012-03-12 | 1 | 0.8627 | 0.0006 | 0.0027 | 0.7206 |
| dd_accel | 2012-03-13..2019-05-31 | 2 | 0.6910 | 0.0218 | 0.0053 | 0.6315 |
| dd_accel | 2019-06-03..2026-08-21 | 3 | 0.6643 | 0.0078 | 0.0053 | 0.6045 |
| rv_accel | 2005-01-04..2012-03-12 | 1 | 0.9341 | 0.0067 | 0.0037 | 0.8213 |
| rv_accel | 2012-03-13..2019-05-31 | 2 | 0.7229 | 0.0173 | 0.0320 | 0.6925 |
| rv_accel | 2019-06-03..2026-08-21 | 3 | 0.7549 | 0.0062 | 0.0040 | 0.6689 |

Significant in all six sub-periods, declining monotonically for `dd_accel`. The
decline is partly mechanical — the first third contains only the GFC, the easiest
episode in the corpus.

---

## 8. Uncertainty

**Permutation-resolution floor: `1/3001 = 0.000333`.** `dd_accel`'s full-span
p = 0.0003 sits *at* it and is therefore **censored, not measured**. Any
comparison of two p-values that are both at the floor is meaningless.

**Event-level cluster bootstrap**, 5,000 resamples of the **6 onsets** with
replacement (not of the positive days — the effective sample size is the number
of onsets). Licensed by an identity verified in the run: the pooled T1 AUC equals
the positive-day-weighted mean of the per-onset AUCs, exactly, when the negative
set is shared. Measured agreement to 4 decimals for every series.

| series | pooled AUC | wmean per-onset | boot 2.5% | boot 50% | boot 97.5% |
|---|---|---|---|---|---|
| rv_accel | 0.7706 | 0.7706 | **0.6614** | 0.7710 | 0.8877 |
| semivar_20 | 0.7832 | 0.7832 | 0.6736 | 0.7832 | 0.8917 |
| drawdown | 0.7185 | 0.7185 | 0.4975 | 0.7242 | 0.9160 |
| dd_accel | 0.7064 | 0.7064 | **0.6205** | 0.7064 | 0.7968 |
| rv_level | 0.6098 | 0.6098 | 0.4037 | 0.6085 | 0.8078 |
| CSRS 2p fullspan | 0.5218 | 0.5218 | 0.2614 | 0.5243 | 0.7606 |

Both signals' 95% intervals exclude 0.5; `drawdown`'s (0.4975) and
`rv_level`'s (0.4037) do not, and `CSRS 2p`'s spans 0.26 to 0.76. The two target
signals have the **narrowest** intervals of the six, which is the quantitative
form of "driven by more than one episode".

**Per-epoch AUC** — the stability evidence that matters most, because a signal
driven by one episode and flat on the others is not a detector whatever its
pooled number:

| series | gfc_2008 | taper_2013 | ilfs_2018 | covid_2020 | tightening_2022 | tariff_2026 |
|---|---|---|---|---|---|---|
| dd_accel | 0.8814 | 0.7283 | 0.6478 | 0.8143 | 0.5914 | 0.5752 |
| rv_accel | 0.9379 | 0.6437 | 0.7952 | 0.9619 | 0.6012 | 0.6836 |
| drawdown | 0.9841 | 0.7734 | 0.9145 | 0.9199 | **0.3105** | **0.4087** |
| rv_level | 0.9572 | 0.4591 | 0.8123 | 0.8286 | **0.2837** | **0.3181** |
| semivar_20 | 0.9488 | 0.6081 | 0.8991 | 0.9254 | 0.6794 | 0.6385 |
| CSRS 2p fullspan | 0.8855 | **0.0199** | 0.7463 | **0.3906** | 0.8277 | **0.2607** |

`dd_accel` and `rv_accel` are **above 0.57 on all six epochs**. `drawdown` and
`rv_level` go sharply *below* chance on the two most recent, which is where their
pooled numbers come from and why they fail out of sample. The 2-pillar CSRS is at
0.0199 on `taper_2013` — worse than inverting it.

---

## 9. What the evidence does and does not support

**Supported.**

1. `dd_accel` and `rv_accel` are **strictly causal**. Exact invariance under both
   truncation and future perturbation, against an audit demonstrated to catch 5/5
   non-causal controls, with the one blind spot measured and closed by a direct
   check instead.
2. Their **contemporaneous (T1) detection replicates out of sample** on two
   pre-registered chronological splits, clearing both nulls' 95th percentiles,
   while the best in-sample series (`drawdown`, 0.8681) collapses to 0.5940 and
   the 3-pillar CSRS collapses to 0.5872 on the same split.
3. They **add information beyond** each simpler comparator and beyond RMT
   `λ₁/N`: all 8 causally-orthogonalised residuals clear nominal 0.05 and survive
   Holm over 8.
4. They are **broad across episodes**: above 0.57 on all six epochs, with the
   narrowest event-level bootstrap intervals of any series tested.
5. `DETECTION-CALIBRATION.md`'s §2 numbers **reproduce** at 3,000 permutations,
   as do `EARLY-WARNING-POWER.md` §4's T3 values.
6. **The T3 negative is informative at the horizon SERAPH specifies, and that
   bound is now stronger than when it rested on a rectangular step.** At
   `h = 15` the test has 75% power against a 75-session linear ramp and 78%
   against an AR(1) build-up at δ = 1 sd, against 80% for the step, with type-I
   2–8% at δ = 0 (§6.1). The shape a systemic-risk thesis predicts would have
   been found four times in five and was not.

**Not supported — and some of it refuted.**

1. **No advance warning.** T3 is null at 5, 10, 20 and 30 days, under two
   permutation nulls and a per-horizon synthetic control, and the test is now
   shown to have 75–80% power against *persistent* build-ups as well as against a
   step. `rv_accel` is below chance at every horizon. Independently confirmed by
   Workstream B at p = 0.3398 / 0.7111, and `semivar_20` — the best T1 series in
   the corpus — warns before 0 of 6 onsets at p = 1.0000. **Nothing in §4 or §5
   may be cited as early-warning evidence.**
2. **Uniqueness is refuted.** `rv_diff1` (p = 0.0010) has a lower p than
   `rv_accel` (0.0017); `dd_diff1` and the raw sign-flipped market return also
   survive Holm over 18. The claim that *acceleration specifically* is the
   substantive finding does not survive adding trivially simpler alternatives to
   the family.
3. **They would not have been selected out of sample.** Leave-one-epoch-out picks
   `dd_accel` on 0 of 6 folds and `rv_accel` on 2 of 6; the usual winner is
   `semivar_20`.
4. **T1 remains partly tautological.** FR32 crisis windows *are* high-volatility
   windows by construction (`rv_t_yz` mean 0.6109 inside vs 0.4979 outside). A T1
   pass is not independent evidence of *systemic-risk* detection. Acceleration
   measures are less exposed than levels, not immune.
5. **Independence of the two spans is not established.** The candidate list was
   drawn up knowing the whole corpus; no parameter was fitted, so the leakage
   channel is candidate selection, not estimation — but SPLIT-B's evaluation span
   still supplied 3 of the 6 onsets to the statistic that selected them.
6. **Calibration is unmeasured here.** Workstream B's Brier skill ≈ 0 stands.
   The low ECE is not skill and is not credited.
7. **The `adj_close` retroactive-adjustment look-ahead is unquantified.** It
   lives in the data, not the code, and needs an unadjusted price series to
   measure.
8. **Six onsets, one provisional** (SPEC OQ3 open for `tariff_2026`). Every null
   here is correctly wide because the event count is small; that is a property of
   the problem.
9. **A long-lead (60–90 session) advance-warning claim remains untestable.** At
   `h = 75` the test has only 37% power against a ramp (§6.1), below the
   pre-registered 50% line. FR32 defines the early-warning window as 5–15
   sessions, so this costs nothing today — nobody has made a long-lead claim —
   but it bounds what any future one could assert, in either direction.
10. **Sub-chance performance is not established either.** Workstream B computes
    that 0 of 6 warnings puts a 95% upper bound of **0.393** on the per-event warn
    probability against a no-skill rate of 0.14, so 0/6 does not demonstrate
    *worse* than chance. Paired with §6.1's 75% power, the defensible joint
    statement is: *a 1-sd build-up in the 5–15 session window would have been
    found and was not; smaller or longer-lead effects remain genuinely untested.*

**What this changes in the existing record.** `DETECTION-CALIBRATION.md` §2's
closing observation — "that the two survivors are both second-difference
quantities is the most interesting substantive result here" — should be read as
an artefact of the family's composition. With 1-day differences and the raw
return in the family, second-differencing is no longer distinguished. The two
signals' *significance* survives; their *interpretation* does not.

---

## 10. Reproduction

```bash
docker start seraph-timescaledb        # port 5433

# log 40 — the full study (~21 min, writes nothing)
.venv/Scripts/python.exe -I scripts/validate_acceleration_signals.py \
    --perms 3000 --t3-perms 1000 --t3-draws 60 --boots 5000

# log 41 — causality suite, no database needed (~2 s)
.venv/Scripts/python.exe -I -m pytest tests/test_acceleration_signal_causality.py -v

# log 42 — T3 power against persistent alternatives (~26 min, writes nothing)
.venv/Scripts/python.exe -I scripts/t3_power_persistent_alternatives.py \
    --draws 60 --perms 200 --obs-perms 1000
```

Observed exit codes: **0** for all three. 21 tests passed. The mutation check in
log 41 §2 confirms the suite fails against each of five non-causal rewrites, so a
pass is evidence rather than silence.

## 11. Next executable task

The task this report previously named here — T3 power against a persistent
alternative — **was executed**; it is §6.1, and it vindicated the existing
conclusion rather than overturning it. Two candidates remain, in priority order.

**1. Settle whether the fixed-peak normalisation was the generous choice, and by
how much.** §6.1 normalised all three shapes to the same *peak* amplitude, which
was pre-registered and is why the ramp retained 75% power: a ramp peaking at
onset delivers mean amplitude 0.9067 on the labelled window, almost the step's
1.0. Under a **fixed-energy** normalisation (same total injected signal, so a
longer build-up is proportionally *shallower*), or against a **plateau** or
**early-peaking** build-up that is already decaying by onset, the labelled window
would get much less and power would be lower. Neither shape was tested, and
neither can be grafted onto §6.1 after the fact — it needs its own
pre-registration and its own script. This is the one genuinely open threat to the
"informative null" claim, and it should be stated as such until closed.

**2. Quantify the `adj_close` look-ahead** (§3.4). It is the only leakage channel
this study could not measure, because it lives in the data rather than the code:
retroactive split and dividend factors mean the price level at `t` embeds
corporate actions announced after `t`. Needs an unadjusted close series for the
universe, then a re-run of §5.1 on returns built from it. Until then every
T1 number here carries an unquantified — probably small, certainly non-zero —
look-ahead.

Not recommended: further window or shape sweeps on `dd_accel`/`rv_accel`
themselves. §7 already shows T1 significance is stable across 11 window variants
and T3 flat and null across all of them, and §5.4 establishes that the
acceleration construction is not distinguishable from a 1-day difference. More
variants would add comparisons without adding information.
