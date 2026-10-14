# Unified causal crisis replay — would SERAPH have warned?

**Answer: no demonstrated advance-warning capability.** The complete
three-pillar system produced **zero pre-onset warnings across six labelled
crises and five lead horizons** (5, 10, 15, 20, 30 trading days). No pillar
subset containing RMT warned before any crisis at any horizon. Simple baselines
warned more often in raw count, but none is distinguishable from chance (best
p = 0.34, 10 comparisons, Holm).

**What six events cannot support.** The point estimate 0.00 sits below the
no-skill expectation of 0.14 ± 0.13, but the 95% upper bound on the per-event
warning probability is **0.393** — so this is a demonstrated *absence of
evidence*, not evidence of sub-chance behaviour, and the distinction is kept
throughout. Workstream B shows the bound only falls below the no-skill rate at
N = 20 onsets, against an exogenous record supporting at most N = 15.

Settled 2026-10-13 on git `f3eaac8`, working tree uncommitted. Nothing was
written to the database; every run below is read-only.

| artefact | path |
|---|---|
| replay driver | `scripts/replay_crisis_warnings.py` |
| null calibration | `scripts/replay_warning_null.py` |
| operational evaluation | `scripts/replay_operational_value.py` |
| causality tests (12, all pass) | `tests/test_replay_causality.py` |
| machine-readable results | `docs/evidence/replay/replay_results.json` |
| null results | `docs/evidence/replay/warning_null_h15.json` |
| operational results | `docs/evidence/replay/operational_value.json` |
| run logs | `*-61-unified-causal-replay-ASSESSABILITY-FIX.log`, `*-62-replay-warning-null-h15.log`, `*-63-replay-operational-value.log` |

Exact commands:

```
python scripts/replay_crisis_warnings.py   --out docs/evidence/replay
python scripts/replay_warning_null.py      --horizon 15 --draws 2000 --out docs/evidence/replay
python scripts/replay_operational_value.py --out docs/evidence/replay
python -m pytest tests/test_replay_causality.py -v      # 12 passed
```

---

## 1. What was replayed, and why it is a replay

Every value at decision date `t` uses inputs dated `<= t`. The pipeline is the
real one: the real C8 `KalmanReconciler`, the real pure C9 `score()`, FR28's
rolling five-year causal ECDF via `window_from`, and D2's availability mask.

| pillar | source | cadence | causal span |
|---|---|---|---|
| P1 Hawkes | `hawkes_output.branching_ratio_n` | **every 5 sessions** | 2017-02-09 .. 2026-08-20 (473 refits) |
| P2 RMT | `rmt_output.eigenvalues` → `lambda_1` share | daily | 2005-01-03 .. 2026-08-21 (5,363) |
| P3 Hamilton | `causal_xi_NOT_PRODUCTION.npz` → `LSD = xi_2 + 2 xi_3` | daily, refit yearly | **2013-01-14** .. 2026-08-21 (3,365) |

Hawkes is selected by the refit's *actual timestamp*, never its date, so a 15:30
decision cannot receive a kernel refitted at 18:55 on a Muhurat session, and
C8's `R(t - tau)` ages the carried-forward value. All seven FR35 pillar subsets
were replayed, plus four simple-feature baselines on the identical grid and
labels.

### Leakage controls are enforced by test, not asserted

`tests/test_replay_causality.py` perturbs the future and asserts the past did
not move: a 5.0-sigma shock at index 500 leaves every realised-vol value before
500 bitwise unchanged; a later rally does not deepen an earlier drawdown; a
regime shift at index 1200 leaves alert flags before 1200 identical. Two further
tests pin the threshold rule — that index `i` is excluded from the trailing
quantile it is judged against, and that an alert beginning *at* the onset scores
`FAIL` with `during_or_after_only` set, never `PASS`.

### Nothing in the replay estimates a parameter on future data

Verified in source rather than assumed, because this is the claim everything
else rests on:

* **RMT** — `scripts/run_rmt.py:106` builds the correlation window as
  `dates[i - T_WINDOW : i + 1]`, the trailing 1,001 days inclusive of `i`. The
  spectrum is a contemporaneous computation with no fitted parameters, and the
  2005-01-03 output start already absorbs the 1,000-day warm-up (`daily_prices`
  reaches back to 1995).
* **Hamilton** — walk-forward with `initial_train = 2000`, `refit_every = 252`.
  The run's own `check_B_assert_causal` is `True` and
  `check_C_warmup_all_nan` confirms the warm-up emits nothing.
* **Hawkes** — rolling 500-session window refit every 5 sessions, selected by
  the refit's actual timestamp.
* **Alert thresholds** — Rule A is a shipped constant; Rule B is a
  pre-specified quantile computed from indices `< t`. **Neither is estimated**,
  so there is no train/test split to get wrong and no holdout to contaminate.

This is why section 3 of the directive ("separate development from final
evaluation") has no further requirement here: the replay fits nothing. The only
selection that occurred was which signals to report, and all eleven are
reported, with Holm correction applied over all ten that are testable.

---

## 2. The two alert rules, both fixed before any epoch was examined

* **Rule A — frozen production config.** `CSRS >= 0.50`, C9's
  `PROVISIONAL_AMBER`. A declared constant in shipped code, so it cannot have
  been fitted here.
* **Rule B — causal adaptive quantile (primary).** The signal exceeds its own
  trailing five-year 95th percentile, computed from indices `< t`. Scale-free,
  so it applies identically to a CSRS and to a raw volatility level, which is
  what makes the pillar-versus-baseline comparison meaningful. Requires 250
  trailing observations; below that the day is **un-assessable**, not a miss.

That last distinction was a defect in the first version of this evaluation and
it changed the result. See section 6.

---

## 3. Primary result — Rule B, all horizons

`n/t` = epochs warned / epochs testable.

| signal | 5d | 10d | 15d | 20d | 30d |
|---|---|---|---|---|---|
| CSRS[hawkes] | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| CSRS[rmt] | 0/6 | 0/6 | 0/6 | 0/6 | 0/6 |
| CSRS[hamilton] | 1/4 | 1/4 | 1/4 | 1/4 | 1/4 |
| CSRS[hawkes+rmt] | 0/6 | 0/6 | 0/6 | 0/6 | 0/6 |
| CSRS[hawkes+hamilton] | 1/4 | 1/4 | 1/4 | 1/4 | 1/4 |
| CSRS[rmt+hamilton] | 0/6 | 0/6 | 0/6 | 0/6 | 0/6 |
| **CSRS[hawkes+rmt+hamilton]** | **0/6** | **0/6** | **0/6** | **0/6** | **0/6** |
| BASE[rv_20] | 0/6 | 1/6 | 1/6 | 1/6 | 1/6 |
| BASE[drawdown] | 0/6 | 0/6 | 0/6 | 0/6 | 1/6 |
| **BASE[semivar_20]** | **0/6** | **0/6** | **0/6** | **0/6** | **0/6** |
| BASE[rv_accel_5] | 1/6 | 1/6 | 1/6 | 2/6 | 2/6 |
| BASE[dd_accel_5] | 1/6 | 1/6 | 2/6 | 2/6 | 2/6 |

Per-epoch detail at the 15-day horizon (FR32's upper lead bound):

| signal | gfc_2008 | taper_2013 | ilfs_2018 | covid_2020 | tightening_2022 | tariff_2026 |
|---|---|---|---|---|---|---|
| CSRS[hawkes] | UNTEST | UNTEST | UNTEST | UNTEST | UNTEST | UNTEST |
| CSRS[rmt] | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| CSRS[hamilton] | UNTEST | UNTEST | FAIL | FAIL | FAIL | PASS 12d |
| CSRS[hawkes+rmt] | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| CSRS[hawkes+hamilton] | UNTEST | UNTEST | FAIL | FAIL | FAIL | PASS 12d |
| CSRS[rmt+hamilton] | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| **CSRS[hawkes+rmt+hamilton]** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| BASE[rv_20] | FAIL | FAIL | FAIL | FAIL | FAIL | PASS 8d |
| BASE[drawdown] | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| BASE[rv_accel_5] | FAIL | FAIL | FAIL | FAIL | PASS 2d | FAIL |
| BASE[dd_accel_5] | FAIL | FAIL | FAIL | FAIL | PASS 12d | PASS 5d |

### The distinction, in one record

`covid_2020`, full three-pillar system, 15-day horizon, verbatim from
`replay_results.json`:

```
onset                            2020-02-20
coverage_days_pre                15        (full coverage - not a data gap)
first_warning_date               None
lead_time_days                   None
warned_pre_onset                 False
n_warning_days_pre               0
during_or_after_only             True
n_warning_days_in_crisis_window  10
verdict                          FAIL
```

**The system alerted on 10 of the 30 days after the COVID onset and on 0 of the
15 days before it**, with complete data throughout. Read without the pre-onset
split, "the CSRS was elevated through the COVID crash" is true and would sound
like a success. It is a `FAIL`. Every epoch carries this breakdown, which is why
the ten fields the directive asks for are recorded per epoch rather than
summarised.

The three warnings that do land inside FR32's 5–15 day window are
`CSRS[hamilton]` / `CSRS[hawkes+hamilton]` at 12 days on the 2026 tariff epoch,
`BASE[rv_20]` at 8 days on the same epoch, and `BASE[dd_accel_5]` at 12 and 5
days on 2022 and 2026. **The 2026 tariff onset is itself provisional** — SPEC
OQ3 is open and `epochs.py` labels that date `PROVISIONAL`, so a result resting
only on it is not reportable as a finding.

---

## 4. Calibrated no-signal benchmark — nothing survives

The null **relocates the events, not the series**: the six onsets are circularly
shifted by a common offset along the trading-day index, preserving their exact
spacing, with offsets landing within 45 days of a real onset discarded. This is
the family whose actual type-I error was measured at **8% against a nominal 5%**
in `EARLY-WARNING-POWER.md`; the alternatives (uniform onset draws, AR(1) from
`x[0]=0`) rejected at 50% and 40%/17% and were discarded there.

Horizon 15 days, 2,000 draws, permutation-resolution floor 0.0005 — comfortably
below Holm's tightest threshold of **0.00455 over 11 comparisons**, so the
test had adequate resolution.

| signal | warned | rate | null rate | p | mean lead | p(lead) |
|---|---|---|---|---|---|---|
| CSRS[hamilton] | 1/4 | 0.25 | 0.08 ± 0.12 | 0.1108 | 12.0 | 0.4125 |
| CSRS[hawkes+hamilton] | 1/4 | 0.25 | 0.09 ± 0.12 | 0.1497 | 12.0 | 0.4621 |
| BASE[rv_20] | 1/6 | 0.17 | 0.05 ± 0.09 | 0.2434 | 8.0 | 0.5688 |
| BASE[dd_accel_5] | 2/6 | 0.33 | 0.21 ± 0.17 | 0.3398 | 8.5 | 0.5453 |
| BASE[rv_accel_5] | 1/6 | 0.17 | 0.19 ± 0.16 | 0.7111 | 2.0 | 0.9649 |
| CSRS[rmt] | 0/6 | 0.00 | 0.13 ± 0.14 | 1.0000 | — | — |
| CSRS[hawkes+rmt] | 0/6 | 0.00 | 0.19 ± 0.16 | 1.0000 | — | — |
| CSRS[rmt+hamilton] | 0/6 | 0.00 | 0.11 ± 0.12 | 1.0000 | — | — |
| **CSRS[hawkes+rmt+hamilton]** | **0/6** | **0.00** | **0.14 ± 0.13** | **1.0000** | — | — |
| BASE[drawdown] | 0/6 | 0.00 | 0.04 ± 0.07 | 1.0000 | — | — |
| **BASE[semivar_20]** | **0/6** | **0.00** | **0.04 ± 0.08** | **1.0000** | — | — |

**Not one of the eleven comparisons reaches significance, even unadjusted at
α = 0.05.** The lowest p-value is 0.1108 against a Holm threshold of 0.00455.

**`semivar_20` is the one that matters most here.** It is the repository's
strongest known single feature — Workstream C measured that leave-one-epoch-out
selection picks it on 4 of 6 folds, ahead of both acceleration signals, and
`STRESS-PILLAR-DECISION.md` was built around it. It warns before **0 of 6**
onsets at every horizon from 5 to 30 days, p = 1.0000. So the pillars were not
flattered by a weak comparison set: **the best feature anyone in this project
has found also has no advance-warning capability.**

Two readings matter and must not be conflated:

* The baselines' apparent advantage in raw count **is not a real advantage.**
  `dd_accel_5`'s 2/6 looks like twice the full system's 0/6, but a skill-free
  relocation achieves 0.21 ± 0.17 on that signal — because it alerts often
  enough (3.94 false alarms/year) to land before a randomly chosen date about a
  fifth of the time. p = 0.34.
* The full system's 0.00 is **at the bottom of its own chance distribution** —
  but that is a statement about the point estimate, and it must not be read as
  evidence of sub-chance performance. **Six events cannot support that claim.**
  The Clopper-Pearson one-sided 95% upper bound for 0 successes in 6 trials is
  `1 − 0.05^(1/6) =` **0.393**, nearly three times the 0.14 no-skill rate. So the
  honest statement is that the data are consistent with a true per-event warning
  probability anywhere from 0 to 0.393 — which includes values well *above*
  chance. 0/6 establishes **no demonstrated warning capability**; it does not
  establish *worse than chance*. (Measured by Workstream B; it corrects an
  earlier overstatement in this document.) Workstream B further computes that the
  upper bound first falls below 0.14 at **N = 20 onsets**, while the exogenous
  record supports at most N = 15 — so the threshold at which 0-of-N would become
  decisive is **unreachable**. See `EVENT-COUNT-LIMITATION.md`.

---

## 4b. Is the negative result an artefact of a strict threshold? No.

A 95th-percentile rule mechanically produces few alerts, so 0/6 only means
something if it survives a looser rule.
`scripts/replay_threshold_sensitivity.py` sweeps Rule B's quantile over
0.80/0.85/0.90/0.95/0.99 and **recomputes the relocation null at every level** —
because loosening the rule raises the no-skill warned-rate too, and comparing a
loosened observed rate against a strict null would manufacture significance.
Logged as `*-66-replay-threshold-sensitivity.log`; full cells in
`replay/threshold_sensitivity_h15.json`. All levels are reported and **none is
selected**.

The full three-pillar system, across every level:

| quantile | warned | no-skill null | p |
|---|---|---|---|
| 0.80 | 0/6 | 0.21 ± 0.14 | 1.0000 |
| 0.85 | 1/6 | 0.19 ± 0.15 | 0.7271 |
| 0.90 | 0/6 | 0.17 ± 0.14 | 1.0000 |
| 0.95 | 0/6 | 0.14 ± 0.13 | 1.0000 |
| 0.99 | 0/6 | 0.06 ± 0.10 | 1.0000 |

### The clearest demonstration in this whole investigation

At q = 0.80, `BASE[rv_accel_5]` warned before **5 of 6 onsets**. In isolation
that reads as a working early-warning system. Its no-skill null rate at that
threshold is **0.53** — a signal with that alert frequency warns before about
three of six *relocated* onsets anyway. **p = 0.1131.**

`BASE[dd_accel_5]` at q = 0.80 gives 4/6 against a null of **0.58**, so its
observed rate is *below* chance. **p = 0.4480.**

A loose threshold buys a 5-of-6 headline and zero evidence. This is precisely
why the raw per-epoch table in §3 cannot be read without §4.

### Multiple comparisons across the sweep

50 of the 55 cells are testable (the five `CSRS[hawkes]` cells are not).

* Cells with p ≤ 0.05: **1**
* Expected under the global null at α = 0.05: **2.5**
* Bonferroni/Holm threshold over 50 cells: **0.00100**

**Fewer cells reach nominal significance than chance alone predicts.**

The one cell that does deserves naming rather than burying: **`CSRS[rmt]` at
q = 0.85 warned before 3 of 6 onsets against a null of 0.12, p = 0.0250.** It is
the single most interesting number in this study. It is also not evidence:

1. It is 1 of 50 cells, and 0.0250 is 25× the corrected threshold of 0.00100.
2. The same signal at the four neighbouring thresholds gives p = 0.4413 (q=0.80),
   0.5060 (q=0.90), 1.0000 (q=0.95) and 1.0000 (q=0.99). A real effect does not
   appear at the 85th percentile and vanish at the 80th and 90th.

If anything in this replay warrants a follow-up it is that cell — pre-registered,
on an independent span, before being believed. It is recorded here so that a
future run cannot present it as a discovery.

---

## 5. Operational usefulness — the CSRS is not a probability

Label: FR32's contemporaneous crisis window `[onset, onset+30]`, **180 crisis
days of 5,363 (3.36%)**. This section measures *detection*, not warning.

| signal | Brier | BSS | ECE | ep. precision | FA/yr | FA per TA | % days alerting |
|---|---|---|---|---|---|---|---|
| CSRS[rmt] | 0.4701 | **−12.84** | 0.572 | 0.062 | 2.78 | 15.0 | 11.7% |
| CSRS[hamilton] | 0.3934 | −9.62 | 0.520 | 0.091 | 2.21 | 10.0 | 3.7% |
| CSRS[hawkes+rmt] | 0.4483 | −12.20 | 0.556 | 0.098 | 5.10 | 9.2 | 11.4% |
| CSRS[hawkes+hamilton] | 0.3754 | −9.14 | 0.506 | 0.188 | 2.87 | 4.3 | 3.5% |
| CSRS[rmt+hamilton] | 0.4390 | −11.93 | 0.583 | 0.071 | 2.41 | 13.0 | 9.5% |
| **CSRS[hawkes+rmt+hamilton]** | 0.4292 | **−11.64** | 0.575 | 0.112 | 3.66 | 7.9 | 9.4% |
| BASE[rv_20] | 0.0342 | −0.006 | 0.023 | 0.179 | 1.07 | 4.6 | 5.4% |
| BASE[drawdown] | 0.0942 | −1.774 | 0.184 | 0.133 | 0.60 | 6.5 | 11.2% |
| BASE[rv_accel_5] | 0.0352 | −0.033 | 0.024 | 0.140 | 3.43 | 6.2 | 5.5% |
| BASE[dd_accel_5] | 0.0346 | −0.018 | 0.018 | 0.086 | 3.94 | 10.6 | 4.6% |

**A Brier skill score of −11.6 means the CSRS is roughly twelve times worse than
always predicting the 3.36% base rate.** ECE 0.575 says the score reads ~0.58
where the realised crisis frequency is ~0.03.

This is not a tuning failure, it is a **scale error by construction**. FR28
makes each sub-score an ECDF rank, approximately uniform on [0,1]; C9 combines
ranks and so emits a rank-like quantity. A quantity uniform on [0,1] cannot be a
calibrated probability of a 3.36% event, whatever weights it is given. FR30 will
not fix this, because FR30 optimises weights, not scale.

**Consequence for C9's alert levels.** `PROVISIONAL_AMBER = 0.50` and
`PROVISIONAL_RED = 0.75` are quantiles of a rank distribution, not risk
thresholds. Under Rule A the CSRS sits above 0.50 on **57–62% of all days**
(`CSRS[rmt]` 61.6%, `CSRS[hawkes+rmt]` 59.2%, full system 60.5%). An amber light
that is on three days in five is not an alert.

The baselines' low ECE must **not** be read as calibration skill: their BSS is
≈ 0 (−0.006 to −0.033), i.e. no better than the base rate. Their ECE is small
only because a 20-day volatility happens to be numerically near 0.03. That is a
coincidence of units.

### Verified not to be a defect

The 57.5% of days sitting above their own trailing five-year median is **not**
an upward drift in the input and **not** an ECDF bug: the `lambda_1` share's OLS
trend is **−0.0274 per decade** (down, not up), mean 0.2535, sd 0.0425. The
asymmetry comes from the series being strongly persistent around slowly-moving
levels, so a trailing five-year reference mixes regimes and most days within a
persistent level sit on one side of it. `ecdf_transform` was checked directly:
`searchsorted(..., side="right") / n` gives mean rank `(n+1)/2n ≈ 0.5` on a
stationary input. No defect; an earlier drift hypothesis of mine was wrong.

---

## 5b. Why fusion did not help — the pillars are independent but uninformative

`scripts/analyse_pillar_redundancy.py`, logged as `*-65-pillar-redundancy.log`.
The subset table shows fusion failed; it cannot say whether that is because the
pillars are redundant or because they are individually empty. Measured
separately:

### The diversity premise holds

On the 468 days where all three pillars exist, the standardised scores are very
nearly orthogonal:

| | hawkes | rmt | hamilton |
|---|---|---|---|
| **hawkes** | 1.0000 | −0.1223 | 0.1091 |
| **rmt** | −0.1223 | 1.0000 | 0.1337 |
| **hamilton** | 0.1091 | 0.1337 | 1.0000 |

Spearman: −0.0792, 0.1533, 0.2090. The equal-weight mean has variance 1.0912×
the fully-independent value, giving **2.75 effective independent pillars of 3**.

**This supports MG-1's premise.** The three pillars really do measure distinct
things, and fusion is not failing through redundancy. It is the first result in
this investigation that favours the architecture as designed.

### The information premise does not

In-sample, unpenalised R² against the contemporaneous FR32 label:

| configuration | span | days | R² | incremental |
|---|---|---|---|---|
| RMT alone | 2005-01-03 .. 2026-08-21 | 5,363 | **+0.00001** | — |
| Hamilton alone | 2013-01-14 .. 2026-08-21 | 3,365 | +0.00925 | — |
| RMT + Hamilton | 2013-01-14 .. 2026-08-21 | 3,365 | +0.00936 | RMT +0.00011 |
| Hawkes alone | 2017-02-09 .. 2026-08-20 | 468 | +0.01114 | — |
| all three | 2017-02-09 .. 2026-08-20 | 468 | **+0.04012** | Hamilton +0.02885, Hawkes +0.00653, RMT +0.00134 |

**RMT — the pillar with full historical coverage and 29/29 acceptance checks
passed — explains 0.001% of the variance in the crisis label over its own
5,363-day span.** Its incremental contribution alongside Hamilton is +0.00011.
The best three-pillar figure, 4.0%, is in-sample on 468 days with 24 crisis
days, so it is an upper bound on anything out-of-sample.

Hamilton's being largest is not a point in its favour: its regime structure is
indistinguishable from a single-regime AR(1) surrogate
(`HAMILTON-REGIME-SUPPORT.md`), so `LSD_t` here is most plausibly tracking
realised volatility rather than regime state — which is also why it is the one
pillar whose standardised score correlates positively with both others.

**So the diagnosis is: non-redundant, but near-empty.** Fusion had three
genuinely different views and almost no signal in any of them. That distinction
matters for what to do next — a better fusion rule cannot help, whereas better
inputs might.

### A label error found and corrected mid-analysis

The first pass applied `[onset, onset+30]` to the 468-element Hawkes-refit
index. Hawkes refits every 5 sessions, so 30 rows there span ~150 calendar
trading days — a 5× widened label. It inflated every R² and **reversed the
ranking**, reporting RMT as the largest contributor (+0.01957) when on the
corrected daily-grid label it is the smallest (+0.00001). The corrected script
builds the label on the daily grid and projects it onto each evaluated subset.

---

## 5c. Why the pillars are near-empty — and a specification discrepancy

`scripts/diagnose_pillar_signal_loss.py` (`*-67-pillar-signal-loss.log`) asks
which of two causes produces §5b's near-zero R²: the pillar does not move in
crises (input problem, unfixable by any transform), or it moves and FR28's rank
flattens it (pipeline problem, fixable).

Separation is in sigma of the non-crisis distribution, so pillars with different
raw units are comparable.

| pillar | n | RAW crisis | STD crisis | RAW pre-onset | STD pre-onset | ρ(raw, std) |
|---|---|---|---|---|---|---|
| hawkes | 468 | 0.3916 | 0.4809 | 0.1271 | 0.0623 | 0.5752 |
| rmt | 5,363 | **−0.3951** | **0.0177** | −0.3518 | −0.2925 | 0.6451 |
| hamilton | 3,365 | 0.5753 | 0.4643 | −0.1068 | −0.1769 | 0.8451 |

**The direct mechanism behind 0/6 is in the pre-onset columns.** All three
pillars are flat or *negative* before onsets: hawkes +0.06, rmt −0.29, hamilton
−0.18 standardised. The pillars do not elevate before a crisis, so no threshold
rule applied to them can fire before one. That is the whole result, in one row.

### RMT falls during crises, and it is not an era artefact

λ₁/N's raw crisis separation is **−0.3951σ** — the wrong sign for a measure of
systemic coupling, which theory says should rise as correlations spike.

The obvious confound is era composition: λ₁/N has a large regime shift
(2008–2010 mean 0.3099, 2014–2016 mean 0.2136), four of six crisis windows sit
in the low era, and the "tranquil" baseline spans all 21 years. Tested directly
by re-measuring each epoch against a **±1-year local baseline**, which removes
the era effect by construction:

| epoch | crisis mean | local mean | separation |
|---|---|---|---|
| gfc_2008 | 0.2716 | 0.2863 | −0.4741σ |
| taper_2013 | 0.2313 | 0.2589 | −0.5864σ |
| ilfs_2018 | 0.2226 | 0.2198 | **+0.6940σ** |
| covid_2020 | 0.2165 | 0.2281 | −0.8214σ |
| tightening_2022 | 0.2443 | 0.2467 | −0.3328σ |
| tariff_2026 | 0.2363 | 0.2398 | −0.7499σ |

**Mean −0.3784σ, negative in 5 of 6 epochs.** The era-controlled figure matches
the global one, so the confound is not the explanation. λ₁/N genuinely falls in
FR32's crisis windows.

### The discrepancy: FR18 specifies `SCA_t`, the pipeline uses λ₁/N

**SPEC FR18:** *"The system shall aggregate the three spectral signals into
`SCA_t` using calibrated weights `w^p`."* FR17 emits `F_t`, `V_t^eig` and `Ω_t`.
`rmt_output` stores all four, and `sca_t` passed C6's 29/29 acceptance checks.

`seraph/orchestration/adapters.py:rmt_emission` standardises
`lam1_share = λ₁/N`, **which is named nowhere in FR16–FR19**, and never reads
`sca_t`. Measured consequence (`*-68`, era-controlled as above):

| statistic | crisis (global) | crisis (era-controlled) | epochs positive | pre-onset |
|---|---|---|---|---|
| **λ₁/N — what the pipeline uses** | **−0.3951** | **−0.3784 ± 0.51** | **1/6** | −0.3518 |
| `F_t` (FR17) | −0.3972 | −0.0431 ± 0.49 | 3/6 | −0.3880 |
| `V_t^eig` (FR17) | 0.3518 | +0.3928 ± 0.80 | 5/6 | −0.4828 |
| `Ω_t` (FR17) | 0.1648 | +0.3028 ± 0.72 | 5/6 | +0.1191 |
| **`SCA_t` — what FR18 specifies** | **+0.6813** | **+0.5028 ± 0.48** | **5/6** | **+0.0861** |
| `mp_pvalue` (FR17) | −0.9999 | −0.4163 ± 0.19 | 0/6 | −0.9999 |

**A sign reversal and roughly a 1σ swing between the specified quantity and the
one in use.** `SCA_t` separates crises at +0.50σ era-controlled, positive in 5 of
6 epochs; λ₁/N separates at −0.38σ, positive in 1 of 6.

Per AGENTS.md §1 — *"If code and docs disagree, the docs win"* — this is a
**conformance defect, not a design choice**. It was not fixed here: changing
Pillar 2's input quantity alters every CSRS value and every published RMT result,
and C6/orchestration is another owner's component. See gate 4 in §8.

### Measured: the FR18 variant replayed end to end

`--pillar2 sca` reruns the whole replay on `SCA_t`, changing nothing else.
Logged as `*-68-replay-FR18-sca-variant.log` and `*-69-replay-null-FR18-sca.log`;
results in `replay_results_sca.json` and `warning_null_h15_sca.json`. **Nothing
in `seraph/` was modified** — the flag lives in the research script.

Raw warning counts improve substantially:

| configuration | λ₁/N | `SCA_t` | FA/yr (λ₁/N → SCA) |
|---|---|---|---|
| CSRS[rmt] | 0/6 | **2/6** (gfc_2008 15d, ilfs_2018 11d) | 2.78 → 8.94 |
| CSRS[hawkes+rmt] | 0/6 | **2/6** | 5.10 → 9.13 |
| CSRS[rmt+hamilton] | 0/6 | **2/6** | 2.41 → 6.76 |
| CSRS[hawkes+rmt+hamilton] | 0/6 | **2/6** (gfc_2008 15d, tariff_2026 15d) | 3.66 → 6.90 |

The leads are genuine, not boundary artefacts: `gfc_2008` reports a 15-day lead
at horizons 15, 20 **and** 30, so the rising edge really is 15 sessions before
the onset with no earlier edge inside 30. `ilfs_2018` likewise reports 11 at all
three.

**And the null erases all of it.**

| configuration | rate | no-skill null | p |
|---|---|---|---|
| CSRS[rmt] | 0.33 | **0.36 ± 0.18** | 0.6737 |
| CSRS[hawkes+rmt] | 0.33 | 0.37 ± 0.18 | 0.7111 |
| CSRS[rmt+hamilton] | 0.33 | 0.26 ± 0.17 | 0.4993 |
| **CSRS[hawkes+rmt+hamilton]** | **0.33** | **0.26 ± 0.17** | **0.4993** |

`CSRS[rmt]`'s observed warned-rate is **below its own null mean.** Nothing is
nominally significant, let alone Holm-significant. The explanation is in the
false-alarm column: the quantity that warns twice also triples the alert rate,
and 218 alert episodes over 21 years will precede two of six onsets by chance.

### Separation is not AUC, so the AUC was measured too

Gate 4 leans partly on detection value, and a separation of means is not a
ranking statistic. `scripts/diagnose_pillar2_quantity_auc.py`
(`*-72-pillar2-quantity-auc.log`) measures AUC directly. AUC is rank-based, so
FR28's monotone transform cannot change these — they are the pillars' own skill.

| statistic | T1 AUC (contemporaneous) | T3 AUC (15-day pre-onset) |
|---|---|---|
| **λ₁/N — what the pipeline uses** | **0.4282** | 0.4340 |
| `F_t` (FR17) | 0.3969 | 0.3791 |
| `V_t^eig` (FR17) | 0.5305 | 0.5205 |
| `Ω_t` (FR17) | **0.7354** | 0.5934 |
| **`SCA_t` (FR18)** | **0.6623** | 0.5324 |

T3 drops in-crisis days, so a crisis reading cannot score as a warning.

Two things follow.

**λ₁/N is anti-predictive, not merely uninformative.** T1 AUC **0.4282** is
materially below chance. This is the same sign problem as the separation
measurement, now in a ranking statistic, and it explains §5b's R² = 0.00001: a
linear fit against an anti-predictor lands near zero. Gate 4's detection case is
confirmed in AUC terms and is large — **0.4282 → 0.6623**.

**FR18's equal-weight aggregate is beaten by its own best component.** `Ω_t`
alone scores 0.7354 against `SCA_t`'s 0.6623, because equal thirds dilutes it
with `F_t` (0.3969, below chance) and `V_t^eig` (0.5305, near chance).

That second point needs stating carefully. **`Ω_t`'s 0.7354 is a best-of-five
chosen after seeing the data and carries no null here — it is not a validated
result and must not be reported as one.** What *is* robust is the comparison
itself: an equal-weight aggregate scoring below one of its own inputs is a
property of the aggregation rule, not a selected winner. And it is precisely
what FR18's *"using calibrated weights `w^p`"* exists to prevent. SPEC §8 lists
`w^p_F, w^p_V, w^p_Ω` among the undefined constants, C6 uses equal thirds as a
declared uninformative prior, and the measured cost of that prior is
0.7354 → 0.6623 in T1 AUC. **Calibrating FR18's weights is a separate, smaller
decision than gate 4** and is worth raising with it.

**None of this rescues advance warning, and `Ω_t` was tested rather than left
hanging.** A 0.5934 reported without a null is exactly the kind of unqualified
number this session has been removing, so
`scripts/test_omega_t_advance_warning.py` put all five Pillar 2 statistics
through the same two calibrated nulls used elsewhere — relocation (measured
type-I 8% at nominal 5%) and AAFT — with multiplicity treated as 5, the
candidate set `Ω_t` was chosen from, giving a Bonferroni threshold of 0.01. Rule
fixed before the run: real only if `p ≤ 0.01` under **both**.
`*-73-omega-t-advance-warning-null.log`, 2,000 permutations, resolution floor
0.00050.

| statistic | T3 AUC | p (relocation) | p (AAFT) | no-signal p95 | verdict |
|---|---|---|---|---|---|
| `Ω_t` | 0.5934 | 0.0880 | 0.1039 | **0.6158** | not established |
| `SCA_t` | 0.5324 | 0.3163 | 0.3053 | 0.6076 | not established |
| `V_t^eig` | 0.5205 | 0.2999 | 0.3108 | 0.5626 | not established |
| `F_t` | 0.3791 | 0.8976 | 0.9060 | 0.6399 | not established |
| `λ₁/N` | 0.4340 | 0.7741 | 0.7641 | 0.6354 | not established |

**`Ω_t`'s 0.5934 falls below its own no-signal 95th percentile of 0.6158**, so it
cannot be distinguished from no signal at all — the same pattern
`EARLY-WARNING-POWER.md` found for `drawdown` (0.6735 against a p95 of 0.6774).
Neither p-value reaches even an uncorrected 0.05.

So the most promising single number anywhere in the Pillar 2 evidence is
refuted, and `F_t` and `λ₁/N` are actively anti-predictive at p = 0.90 and 0.77.
**No Pillar 2 statistic — specified, in use, or component — has demonstrable
advance-warning content.**

**Confirmed by a second, independent null.** Workstream B built a
false-alarm-matched Poisson null — each signal compared against its *own*
measured alert rate rather than against relocated onsets — and reached the same
verdict: `CSRS[rmt]` with `SCA_t` has `p0 = 0.413` at 8.94 FA/yr, so
`P(X >= 2 | p0) = 0.7860`, "BELOW null"; the full system `p0 = 0.337`,
`P = 0.6559`. B also noted that Poisson matching *overstates* `p0` because alert
episodes cluster (0.413 against the relocation null's measured 0.36), which is
the direction it predicted. **Two nulls built on different principles, same
answer.** `*-37-fr18-sca-false-alarm-matched-null.log`.

**This is the §4b lesson again, now on a real fix rather than a loosened
threshold.** Switching Pillar 2 to the specified quantity takes the headline
from 0/6 to 2/6 — which reads like a repair working — and moves the evidence not
at all.

**So the discrepancy matters, but not for the primary question.** `SCA_t`'s
*pre-onset* separation is **+0.0861σ**, essentially flat. Fixing it should
materially improve contemporaneous detection (T1) and leaves advance warning
(T3) where it was. The two objectives fail for different reasons, and only one of
them has a defect behind it.

---

## 6. Two findings about testability that changed the result

### 6a. Pillar 1 standalone cannot be evaluated for advance warning at all

`CSRS[hawkes]` has **0 assessable days out of 468**. `refit_every = 5` sessions
(a decision justified on its own merits in `HAWKES-WINDOW-SELECTION.md`:
out-of-sample NLL/bar 0.1325 at 500 days versus 0.2322 at 60) yields ~50
observations a year. A trailing five-year window therefore holds ~250
observations only at the very end of a 9.5-year span, and FR32's 15-day lead
window contains **at most 3 Hawkes observations** — below the 5 any threshold
rule needs.

This is a structural resolution limit, not a fit failure, and it is invisible in
the aggregate AUC work done previously. **Pillar 1's cadence and FR32's lead
window are mutually incompatible as currently specified.** Either the refit
cadence must shorten (at a documented cost in parameter stability) or the lead
window must widen — and that is a specification decision, not an implementation
one.

### 6b. SPEC §4's coverage matrix is not causally achievable

SPEC §4 marks Hamilton available for the 2008 GFC. The causal walk-forward
consumes its first 2,000 observations as an initial training window, so the
earliest causal Hamilton estimate is **2013-01-14**. Producing a 2008 Hamilton
reading requires parameters estimated from 2013 data — look-ahead.

`taper_2013` (onset 2013-05-22) is likewise `UNTESTABLE`: only ~88 causal days
precede it, below the 250-observation threshold floor.

So the real causal coverage differs from the published matrix:

| epoch | RMT | Hamilton (SPEC §4) | Hamilton (causal) | Hawkes |
|---|---|---|---|---|
| gfc_2008 | yes | **yes** | **no — series starts 2013-01-14** | no |
| taper_2013 | yes | **yes** | **no — 88 days of history** | no |
| ilfs_2018 | yes | yes | yes | sparse (7 obs in ±30d) |
| covid_2020 | yes | yes | yes | sparse (8) |
| tightening_2022 | yes | yes | yes | sparse (8) |
| tariff_2026 | yes | yes | yes | sparse (9) |

A corrected coverage matrix is a SPEC §4 amendment and is **not made here**. See
section 8.

### 6c. The defect this evaluation found in itself

The first version of Rule B returned only `flags`, with no record of whether a
threshold had been computable. Days whose trailing window was too short produced
`False`, which `assess_epoch` scored as `FAIL`. That reported
`CSRS[hawkes]` as having *missed* four crises when in fact it had no decision
rule at those dates, and reported Hamilton as missing 2008 and 2013 rather than
being absent. Fixed by returning an `assessable` mask and routing it into both
`assess_epoch` and the null's `statistic`, so the observed statistic and its
null use one testability rule. The pre-fix log is preserved as
`*-60b-unified-causal-replay-PRE-ASSESSABILITY-SUPERSEDED.log`.

---

## 7. What this does and does not establish

**Established.**
1. The complete three-pillar system issued **no pre-onset warning at any of six
   crises, at any horizon from 5 to 30 trading days**, under a causal adaptive
   threshold. Warned-rate 0.00 against a no-skill 0.14 ± 0.13.
2. **No RMT-containing subset warned before any crisis.** RMT is the only pillar
   with full historical coverage, so this is the configuration with the most
   data behind it.
3. **No signal tested — pillar, fusion or baseline — is distinguishable from
   chance** on pre-onset warning. Ten comparisons, lowest p = 0.1108, Holm
   threshold 0.005.
4. **The CSRS is not a probability and its alert constants are mis-scaled.** BSS
   −11.6, ECE 0.575, amber on 60% of days. This follows from FR28's rank
   transform and is not fixable by FR30 weight optimisation.
5. Operationally the full system gives **7.9 false alarms per true alarm** and
   **episode precision 0.112** — and those true alarms are contemporaneous, not
   advance.
6. **Fusion did not help.** The three-pillar CSRS (0/6) did not beat its best
   component subset (`hawkes+hamilton`, 1/4), and adding RMT to
   `hawkes+hamilton` removed the only warning it had.
7. **The negative result is not a threshold artefact.** Swept over five quantile
   levels with the null recomputed at each, the full system gives 0/6 at four of
   five levels and 1/6 (p = 0.7271) at the fifth. Across all 50 testable cells,
   **1 reaches p ≤ 0.05 where chance alone predicts 2.5.**
8. **Raw warning counts are worthless without a base-rate null**, demonstrated
   concretely twice: `rv_accel_5` at an 80th-percentile threshold warns before 5
   of 6 onsets at p = 0.1131, because its no-skill rate at that threshold is
   0.53; and switching Pillar 2 to the spec'd quantity takes the full system
   from 0/6 to 2/6 at p = 0.4993, because it triples the alert rate.
9. **No Pillar 2 statistic has advance-warning content**, including the most
   promising one. `Ω_t`'s T3 AUC of 0.5934 — the highest of any pillar quantity
   measured — falls **below its own no-signal 95th percentile of 0.6158**
   (p = 0.0880 relocation, 0.1039 AAFT, Bonferroni threshold 0.01 over the
   5 candidates it was selected from). `F_t` and `λ₁/N` are actively
   anti-predictive at p = 0.90 and 0.77.
10. **One confirmed implementation defect, found and not fixed here.** SPEC FR18
   specifies Pillar 2's sub-score as `SCA_t`; `rmt_emission` standardises
   `λ₁/N`, which FR16–FR19 never name, while `sca_t` is computed, validated at
   29/29 and never read. Era-controlled crisis separation **+0.5028σ (5/6
   epochs) for `SCA_t` versus −0.3784σ (1/6) for λ₁/N** — a sign reversal. Per
   AGENTS.md §1 this is a conformance defect, not a design choice. It is worth
   ~1σ for *detection* and **nothing for advance warning** (§5c). Gate 4.

**Not established, and explicitly not claimed.**
* That SERAPH *cannot* warn. The negative is **bounded, not absolute** — and the
  bound was challenged and held. `EARLY-WARNING-POWER.md`'s original power
  figures were measured against a **rectangular step** confined to the lead
  window, which is the easiest possible alternative; Workstream C pointed out
  that a systemic-risk thesis predicts a *gradual build-up* instead, and that if
  T3 had no power against that shape, "no advance warning" would have to be
  downgraded to "untestable at six onsets". **That was pre-registered as a
  decision rule and then tested** (`*-42-t3-power-persistent-alternatives.log`),
  at the project horizon h = 15 with a 75-session build-up:

  | injected shape | δ=0 (type-I) | δ=0.5 | **δ=1.0** | δ=1.5 |
  |---|---|---|---|---|
  | rectangular step | 3% | 30–32% | 80–85% | 100% |
  | **linear ramp (75 sessions)** | 7–8% | 47–50% | **75–77%** | 97–98% |
  | AR(1)-persistent drift (φ = 0.9973) | 2–3% | 35–37% | 78–80% | 95–97% |

  Power against the ramp is **75–77% at 1.0 sd** and 97–98% at 1.5 sd, against a
  pre-registered downgrade threshold of ~50%. Type-I error is 2–8% against a
  nominal 5% for all three shapes, so the test is calibrated. The ramp survives
  because it **peaks at the onset**: although 360 of its 450 signal-carrying days
  land on days T3 labels *negative* (which pushes AUC down), its final 15 days
  still carry mean amplitude 0.9067 against the step's 1.0000.

  **Two limits on this bound, both measured rather than assumed.**

  * **It is horizon-specific.** At a *matched* 75-session horizon the ramp's
    power falls to **37%** and the drift's to 35% — below the 50% line — because
    a linear rise averages half its peak over its own length (mean amplitude on
    positive days 0.5067 against the step's 1.0000). FR32 specifies a 5–15 day
    lead window, so h = 15 is the project-relevant row and h = 75 is a
    sensitivity. The honest narrower statement: **at the horizon SERAPH
    specifies, the T3 negative is informative; at 60–90 session leads the test
    would be underpowered against a gradual build-up, so a long-lead claim is
    untestable on six onsets either way.** Nobody has made a long-lead claim, so
    this costs nothing today — it bounds any future one.
  * **It assumes the build-up peaks at onset.** The injection was pre-registered
    at equal *peak* amplitude, which is the generous choice. Under fixed-*energy*
    normalisation, or against a plateau or an early-peaking build-up already
    decaying by onset, the labelled window receives less and power would be
    lower. Neither was tested, and neither can be grafted on after the fact.
    **This is the one open threat to the "informative null" claim**, so §6.1 of
    `ACCELERATION-SIGNALS.md` states it as *informative against build-ups that
    peak at onset*, not against build-ups generally.

  An effect below ~0.5 sd remains untested (power 47–50%).
* Any economic consequence. No position model, execution assumption or cost
  model exists in this repository, so no drawdown-avoided or risk-reduction
  figure is computable, and none is stated.
* Anything about the 2026 tariff epoch, whose label is provisional (SPEC OQ3).
* That Hamilton has advance-warning value. Its 1/4 rests entirely on that
  provisional epoch, p = 0.1108, and its regime structure is indistinguishable
  from a single-regime AR(1) surrogate (`HAMILTON-REGIME-SUPPORT.md`).

**Pillar identity is unchanged.** P1 Hawkes, P2 RMT and P3 Hamilton remain the
three pillars in `PILLAR_ORDER`. Nothing was renamed, removed or substituted,
and no baseline was promoted into a pillar slot. The baselines are reported as
comparators, which is what section 2 of the directive asked for.

---

## 8. Approval gates — stated, not crossed

Each is written as the mandate requires: the question, the evidence, the
alternatives with their consequences, and a recommendation. **None was acted
on.** No SPEC, ARCHITECTURE or pre-registration file was modified, and `seraph/`
was not touched by this workstream.

### Gate 1 — C9's alert thresholds are quantiles of a rank, not risk levels

**Question.** Should `PROVISIONAL_AMBER = 0.50` / `PROVISIONAL_RED = 0.75` remain
absolute constants applied to an ECDF-rank composite?

**Evidence.** FR28 maps each sub-score to a rolling-five-year ECDF rank, which is
approximately uniform on [0,1]. The composite inherits that scale. Measured
consequence: the CSRS exceeds 0.50 on **57–62% of all days** (`CSRS[rmt]` 61.6%,
`CSRS[hawkes+rmt]` 59.2%, full system 60.5%), against an FR32 crisis base rate of
**3.36%**. Brier skill score **−11.64**, ECE **0.575**.

**Alternatives.**
| option | consequence |
|---|---|
| (a) Replace the absolute constants with causal trailing-quantile thresholds | This is exactly Rule B, already measured here. Alert rate falls to 4–12% of days and becomes comparable across signals. Changes `alert_level` *semantics* (a level becomes relative, not absolute) without changing the schema. |
| (b) Insert a calibration layer mapping CSRS → probability | Preserves absolute thresholds and makes them meaningful, but needs a fitted mapping, which needs a training span and therefore a holdout protocol. More work; also the honest fix if the CSRS is ever to be called a probability. |
| (c) Leave as is, and document that `alert_level` is a research label | Zero work. But every operational statistic in §5 stays uninterpretable, and the dashboard (C12) would display an amber light on three days in five. |

**Recommendation: (a) now, (b) later.** (a) is cheap, reversible and already
evidenced; (b) is the only option that would let FR29's CIs be read
probabilistically. **Note FR30 fixes neither** — it optimises weights, not scale.
**Owner: D (C9).**

### Gate 2 — Pillar 1's refit cadence and FR32's lead window are incompatible

**Question.** FR32 specifies a 5–15 trading-day early-warning window.
`refit_every = 5` sessions puts at most 3 Hawkes observations inside it. Which
gives?

**Evidence.** `hawkes_output` holds 473 refits over 9.5 years (~50/yr).
`CSRS[hawkes]` has **0 assessable days of 468** under any trailing-window
threshold rule, and is `UNTESTABLE` at all six epochs. The cadence is not
arbitrary: `HAWKES-WINDOW-SELECTION.md` selected it on out-of-sample NLL/bar
(0.1325 at 500 days versus 0.2322 at 60) and on branching-ratio stability
(CV 0.204 versus 0.714).

**Alternatives.**
| option | consequence |
|---|---|
| (a) Shorten `refit_every` for evaluation only | Pillar 1 becomes evaluable. Costs compute (17.1 s/fit × ~5× more fits) and nothing else — the *window* stays 500 days, so parameter stability is unaffected. Produces a second Hawkes series, needing its own artefact id. |
| (b) Widen FR32's lead window | Touches a pre-registered requirement and every lead-time figure already published. Changes the target after seeing results. |
| (c) Record that Pillar 1 is not independently evaluable for advance warning | Honest, free, and leaves FR35's Table A permanently incomplete for the `(hawkes)` subset. |

**Recommendation: (a).** It is the only option that converts an `UNTESTABLE`
into a result, and it costs compute rather than validity. (b) should be refused:
widening the window after observing 0/6 is exactly the target-redefinition the
mandate forbids. **Owner: B (C5) with D (C10).**

### Gate 3 — SPEC §4's coverage matrix is not causally achievable

**Question.** SPEC §4 marks Hamilton available for the 2008 GFC and the 2013
taper tantrum. Causally it is not. Which does the published matrix mean?

**Evidence.** The causal walk-forward consumes 2,000 observations as an initial
training window, so the first causal Hamilton estimate is **2013-01-14**. A 2008
reading requires parameters estimated from 2013 data. `taper_2013` has only ~88
causal days before its onset, below the 250-observation threshold floor.

**Alternatives.**
| option | consequence |
|---|---|
| (a) Amend §4 to separate *in-sample* from *causal* availability | Accurate. Table B (the 2 pre-2015 epochs) becomes RMT-only, so FR35's Table B drops from 3 subsets × 2 modes to 1 × 2. That collides with the open FR35 config-count question. |
| (b) Shorten Hamilton's `initial_train` | Buys earlier coverage at the cost of estimating a 3-state TVTP model on fewer observations — and the regime structure is already indistinguishable from a single-regime surrogate at 2,000. Likely to make a weak result weaker. |
| (c) Accept in-sample Hamilton for the two pre-2015 epochs, labelled as such | Keeps the matrix, but any lead-time figure from those epochs is not a replay claim and must never be reported as one. |

**Recommendation: (a).** The matrix should say what a live system could have
produced. **Owner: C (C7) with D (C10).**

This interacts with FR35, but **not** in the way `FR35-CONFIG-COUNT-CONFLICT.md`
supposed. Workstream D established that FR35's **20 configurations are
SPEC-correct** — SPEC FR35 `[v2]` line 243 reads *"Table A (7 subsets × 2
reconciliation modes…) and Table B (3 subsets × 2 modes…)"*, i.e. 14 + 6 = 20 —
and that the conflict note's §5 recommendation to restrict Table A to 8 **would
violate SPEC and freeze a wrong hash. It must not be applied.** The one genuine
ambiguity is Table B's *fold count*: SPEC says *"the 2 pre-2015 epochs"* (2
folds), ARCHITECTURE D5(b) says all 6. That question and this gate must be
decided together, because if Hamilton cannot cover 2008 or 2013 causally then
Table B's pre-2015 rows are RMT-only whichever fold count wins. See
`BLOCKER-TRIAGE.md` §D-2.

### Gate 4 — FR18 specifies `SCA_t`; the pipeline uses λ₁/N

**Question.** Should `rmt_emission` standardise `SCA_t`, the quantity SPEC FR18
names, instead of `λ₁/N`, which FR16–FR19 never mention?

**Evidence.** §5c. Era-controlled crisis separation: `SCA_t` **+0.5028σ,
positive in 5 of 6 epochs**; `λ₁/N` **−0.3784σ, positive in 1 of 6**. In T1
AUC: `SCA_t` **0.6623** against `λ₁/N`'s **0.4282**, i.e. the quantity in use
is *anti-predictive*, not merely uninformative. `sca_t` is
computed, passed C6's 29/29 acceptance checks, is persisted on all 5,363 rows —
and is never read by the fusion path. Replaying on `SCA_t` moves the full system
from 0/6 to 2/6 pre-onset warnings, **but p = 0.4993 against its own null**, so
it changes no conclusion about advance warning.

**Causality checked, not assumed.** `SCA_WEIGHTS = (1/3, 1/3, 1/3)` is an
explicitly uninformative prior — the engine docstring says equal thirds "must not
be reported as" a calibration, and SPEC §8 lists `w^p_F, w^p_V, w^p_Ω` among the
undefined constants. Each component is ranked on its own *rolling* window
(`SCA_MIN_HISTORY = 250`) before weighting. So no parameter is fitted and the
2/6 is not weight-calibration leakage.

**Alternatives.**
| option | consequence |
|---|---|
| (a) Switch `rmt_emission` to `SCA_t` | Restores FR18 conformance and roughly a 1σ improvement in crisis separation, with the correct sign. Changes **every** CSRS value ever computed, so `csrs` rows and the two weight artefacts become stale and `DETECTION-CALIBRATION.md`'s AUCs need re-running. Raises the alert rate ~2–3×, which interacts with gate 1. |
| (b) Keep λ₁/N and amend FR18 to name it | Cheap, but requires arguing that a quantity with the *wrong-signed* crisis separation is the intended measure of systemic coupling. Hard to justify on the evidence. |
| (c) Emit both and let FR34's sensitivity analysis decide | FR34 exists for exactly this. Costs a second artefact id and a second `csrs` line-up; defers the decision without losing information. |

**Recommendation: (a), and treat it as a conformance fix rather than a design
change.** AGENTS.md §1 is explicit — *"If code and docs disagree, the docs
win"* — and λ₁/N is not a documented variant of FR18, it is an undocumented
substitution. **But sequence it after gate 1**, because (a) triples the alert
rate and the alert scale is already broken. **Owner: A (C6) with orchestration.**
Expect to re-run every published RMT and CSRS figure.

**A smaller sub-question, raised with it.** FR18 says *"using calibrated
weights `w^p`"*; C6 uses equal thirds, declared as an uninformative prior
because SPEC §8 leaves the weights undefined. The measured cost is that
`SCA_t` (T1 AUC 0.6623) scores **below its own `Ω_t` component (0.7354)**,
diluted by `F_t` (0.3969) and `V_t^eig` (0.5305). Whether to calibrate those
weights is a separate and cheaper decision than (a). `Ω_t`'s figure is a
best-of-five with no null, so this is a reason to *investigate*, not a result.

**What this is not.** It is not a fix for advance warning, and must not be
reported as one. §5c measures that directly: p = 0.4993, and every T3 AUC in
the table sits between 0.38 and 0.59.

### Gate 5 — SPEC OQ3: epoch 6's label is still provisional

**Question.** Which 2025–26 tariff date labels epoch 6?

**Evidence.** `epochs.py` marks `tariff_2026 = 2026-02-01` `PROVISIONAL`, naming
the 50% peak and the solar CVD single-day drop as the other candidates. **Three
of the five pre-onset warnings observed anywhere in this replay fall on that
epoch** — including both of Hamilton's and one of `rv_20`'s.

**Consequence of not deciding.** Every positive result in this replay rests on a
date that may move. **Recommendation: resolve before any lead-time figure is
published.** Owner: whoever owns OQ13 (crisis labelling source), itself open.

## 9. Next executable step

**More onsets remains the binding constraint**, as recorded in
`ACCEPTANCE-MATRIX.md` §5 — but this replay narrows what that would buy. The
null's spread (± 0.12 to ± 0.17 on the warned-rate) is driven by six events; at
the observed effect sizes, no plausible number of additional Indian equity
onsets makes a 0/6 into a significant result. The more informative next steps,
in order:

1. **Resolve gate 1 (alert scale).** An amber light on 57–62% of days makes
   every operational statistic in §5 uninterpretable, and fixing it is cheap and
   reversible. Until then no alert-based claim can be assessed.
2. **Resolve gate 4 (FR18 conformance), sequenced after gate 1.** It is the one
   confirmed defect found anywhere in this replay, it restores a specified
   requirement, and it is worth roughly 1σ of crisis separation with the correct
   sign. It will **not** improve advance warning (§5c measures p = 0.4993) and
   must not be sold as though it would.
3. **Resolve gate 2 (Pillar 1 cadence).** Pillar 1 is currently *untestable* for
   the system's primary objective. That is worse than a negative result, and it
   is fixable at the cost of compute alone.
4. **Event count is not the lever.** Workstream B measured the integral timescale
   of `rv_t_yz` at **770 sessions**, so the 5,363-session grid holds ≈ 7
   effectively independent realisations and six nominal onsets give N_eff ≈ 5.
   Nine additional defensible episodes would buy roughly **one** effectively
   independent event. The 0-of-N upper bound first falls below the no-skill rate
   at **N = 20**, while the exogenous record supports at most N = 15 — so the
   decisive threshold is unreachable. **The binding constraint is effect size,
   not sample size.** See `EVENT-COUNT-LIMITATION.md`.
