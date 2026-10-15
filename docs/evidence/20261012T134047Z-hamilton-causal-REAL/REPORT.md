# Hamilton Causal Validation on Real NSE Data — Evidence Report

**Option 3 executed: validation only, nothing persisted.**
Stage 1: 2026-10-12 13:41Z → 15:36Z (114.7 min, 14 blocks). Stage 2: → 16:35Z, exit 0.
git `f79299d`. Python 3.12.14. PostgreSQL 16.15 / TimescaleDB 2.29.2.

Input: `hamilton_output` **observation** columns (`rv_t_yz`, `ar_t`, `bas_t`) — C4 output,
5,365 obs, 2005-01-03 → 2026-08-21, all finite. The leaky `xi_1/xi_2/xi_3` were never
read and never used as ground truth.

Config: `initial_train=2000`, `refit_every=252`, `K_REGIMES=3`, `restarts=4`, `seed=0`,
`maxiter=200`, exog = `[1, z_{t-1}]` from `causal_tvtp_exog`.

---

## Headline

**The implementation is genuinely causal. The fit is not statistically identified on the
real corpus, and AMENDMENT-05's fix does not resolve the anomaly it was written for.**

These are four separate claims and only the first is established:

| Claim | Verdict | Evidence |
|---|---|---|
| **Causal correctness** | **PROVEN** | truncation invariance bitwise exact (§2c) |
| **Optimiser convergence** | **FAILED 3/14** | blocks 7, 12, 13 non-converged (§1) |
| **Statistical identification** | **FAILED** | 6/14 nesting violations to −2,322.88 (§2b); 53% of dates near-absorbing (§2d); NFR17 0.269σ |
| **Predictive usefulness** | **NOT TESTED** | requires C10 against FR32 epochs; out of scope |

---

## 1. Stage 1 — block schedule and convergence

| blk | train_n | train ≤ | emit first | emit last | llf | conv | min off-diag |
|---|---|---|---|---|---|---|---|
| 0 | 2000 | 2013-01-11 | 2013-01-14 | 2014-01-15 | 16,677.67 | True | −7.105e-15 |
| 1 | 2252 | 2014-01-15 | 2014-01-16 | 2015-01-28 | 19,189.77 | True | −3.553e-15 |
| 2 | 2504 | 2015-01-28 | 2015-01-29 | 2016-02-03 | 21,669.40 | True | −7.105e-15 |
| 3 | 2756 | 2016-02-03 | 2016-02-04 | 2017-02-09 | 23,983.18 | True | −3.553e-15 |
| 4 | 3008 | 2017-02-09 | 2017-02-10 | 2018-02-15 | 25,786.67 | True | −3.553e-15 |
| 5 | 3260 | 2018-02-15 | 2018-02-16 | 2019-02-21 | 27,757.84 | True | −3.553e-15 |
| 6 | 3512 | 2019-02-21 | 2019-02-22 | 2020-03-05 | 30,017.71 | True | 2.331e-15 |
| **7** | 3764 | 2020-03-05 | **2020-03-06** | **2021-03-10** | 32,373.24 | **False** | 8.364e-15 |
| 8 | 4016 | 2021-03-10 | 2021-03-12 | 2022-03-17 | 34,044.69 | True | **8.913e-27** |
| 9 | 4268 | 2022-03-17 | 2022-03-21 | 2023-03-23 | 36,454.76 | True | −8.882e-16 |
| 10 | 4520 | 2023-03-23 | 2023-03-24 | 2024-04-01 | 38,518.56 | True | −3.553e-15 |
| 11 | 4772 | 2024-04-01 | 2024-04-02 | 2025-04-04 | 40,705.24 | True | −3.553e-15 |
| **12** | 5024 | 2025-04-04 | **2025-04-07** | **2026-04-15** | 44,257.07 | **False** | 2.171e-10 |
| **13** | 5276 | 2026-04-15 | **2026-04-16** | **2026-08-21** | 45,430.56 | **False** | **1.278e-26** |

`converged: 11/14`. Regime `order` was `(0, 1, 2)` on every block — labelling is stable.
Per-block wall time 186 s → 2,141 s (block 13 ran all five restarts to `maxiter`).

**Which windows the non-convergence covers matters more than the count.** `fit()` has a
documented fallback — when no restart converges it returns the plain default fit rather
than crashing:

```python
if res is None:                              # nothing converged; fall back
    res = model.fit(maxiter=maxiter, disp=False)
```

So blocks 7, 12 and 13 emit ξ from parameters **not at an optimum**, and those blocks span
**2020-03-06 → 2021-03-10** (the COVID crash) and **2025-04-07 → 2026-08-21** (which
contains the provisional `tariff_2026` break date, 2026-02-01). Two of the six FR32
labelled epochs therefore sit inside non-converged emission windows. Any NFR16 figure
computed on this series would be scored on parameters that failed to converge.

### Causality checks (stage 1)

| Check | Result |
|---|---|
| A — causal exog ≠ full-sample z-score | `max|Δ| = 2.645324` |
| A — prefix stability `exog(y[:3000]) == exog_full[:3000]` | **True** |
| B — `assert_causal` | **PASS** — no block's parameters saw its own emission window |
| C — warm-up is absence | all NaN before index 2000 = True; any NaN after = False |
| D — simplex validity | `max|Σξ−1| = 1.110e-15`, min 0.000000, max 1.000000 |

---

## 2. Stage 2

### 2a — does the TVTP transition block move off its initial value?

- `tvtp = True`, transition slice = **12 parameters**
- `start_params` transition block = **exactly 0.000e+00** (confirms AMENDMENT-05's premise)
- **`restarts=0` (all-zeros default as the only start): llf 16,677.67, transition
  `max|·| = 44.23`** — the block moves a very long way off zero
- Stage 1 block 0 with multi-start: llf 16,677.67 → **gain over `restarts=0` = 1.16e-10**

**Two conclusions.** (i) AMENDMENT-05 §2.1's *consequence* — that the transition block is
effectively stuck at its all-zeros start — is **falsified on real data**: `0/14` blocks
ended with a zero transition block, and a single-start fit reaches `|44.2|`. (ii) On block
0 the multi-start bought **nothing** (1.16e-10 llf). It is not harmful, but on this corpus
it is not doing the work AMENDMENT-05 intended.

**Unresolved:** the direct `_em_iteration` probe **failed** —
`TypeError: float() argument must be a string or a real number, not 'KimSmootherResults'`.
That is a defect in my probe, not in statsmodels. So AMENDMENT-05's specific claim that one
EM iteration moves the transition block by *exactly* 0.0 while emission means move ~2.2e-3
is **neither confirmed nor refuted here**. Its downstream consequence is falsified (above),
which is the part that matters for the model.

### 2b — nesting invariant: LL(full) ≥ LL(intercept-only)

Restricted = `exog[:, :1]` (constant column alone, 6 transition params) against full
(12 params), same sample, `df = 6`. This construction is correct: it reproduces
AMENDMENT-05's reported p-values for positive LRs.

| blk | train ≤ | llf full | llf restricted | LR | p(χ²,6) | ok |
|---|---|---|---|---|---|---|
| 0 | 2013-01-11 | 16,677.67 | 16,667.45 | +20.45 | 0.0023 | ✓ |
| 1 | 2014-01-15 | 19,189.77 | 19,181.52 | +16.50 | 0.0113 | ✓ |
| 2 | 2015-01-28 | 21,669.40 | 21,664.78 | +9.24 | 0.16 | ✓ |
| 3 | 2016-02-03 | 23,983.18 | 23,966.42 | +33.52 | 8.31e-06 | ✓ |
| 4 | 2017-02-09 | 25,786.67 | 25,769.04 | +35.27 | 3.82e-06 | ✓ |
| 5 | 2018-02-15 | 27,757.84 | 27,746.24 | +23.19 | 7.34e-04 | ✓ |
| **6** | 2019-02-21 | 30,017.71 | 30,306.30 | **−577.17** | — | **✗** |
| **7** | 2020-03-05 | 32,373.24 | 32,969.61 | **−1,192.73** | — | **✗** |
| **8** | 2021-03-10 | 34,044.69 | 34,682.70 | **−1,276.01** | — | **✗** |
| **9** | 2022-03-17 | 36,454.76 | 37,117.61 | **−1,325.70** | — | **✗** |
| **10** | 2023-03-23 | 38,518.56 | 39,352.76 | **−1,668.39** | — | **✗** |
| **11** | 2024-04-01 | 40,705.24 | 41,866.68 | **−2,322.88** | — | **✗** |
| 12 | 2025-04-04 | 44,257.07 | 44,242.52 | +29.11 | 5.81e-05 | ✓ |
| 13 | 2026-04-15 | 45,430.56 | 45,416.64 | +27.84 | 1.01e-04 | ✓ |

**6/14 violations, in a contiguous band (blocks 6–11, training samples ending 2019 → 2024),
worsening monotonically to −2,322.88 — i.e. the full model scores 1,161 log-likelihood
BELOW its own nested special case.** AMENDMENT-05 recorded `LR = −414.55` on one fold and
treated it as an isolated anomaly its fix would remove. Measured here it is **systematic
and 5.6× larger at worst.**

Note block 8 **converged** and still violates nesting by −1,276. Convergence flag and
identification are orthogonal.

### 2c — truncation invariance (the decisive causality test)

Re-ran `walk_forward` on `y[:3008]` (K = 3,008, 2017-02-09, a clean block boundary) and
compared `ξ[:, :3008]` against the full run's prefix.

| Quantity | Result |
|---|---|
| `exog(y[:K]) == exog_full[:K]` | **True** |
| overlapping finite cells compared | 3,024 |
| `max |ξ_full − ξ_truncated|` | **0.000e+00** |
| NaN masks identical | **True** |
| per-block llf delta (blocks 0–3) | **0.000e+00** on all four |

**Bitwise identical.** Deleting every observation after 2017-02-09 changes nothing about
any ξ before it. A filter that peeked at future data could not produce this. **Causal
correctness is established empirically, not merely asserted.**

### 2d — is the transition matrix persistently near-absorbing?

Full-sample fit, llf 46,327.14, `regime_transition` shape (3, 3, 5365).

Minimum off-diagonal transition probability, percentiles over t:

| p0 | p1 | p5 | p25 | **p50** | p75 | p100 |
|---|---|---|---|---|---|---|
| 1.059e-27 | 4.742e-21 | 3.791e-10 | 2.810e-08 | **6.905e-07** | 6.923e-05 | 1.795e-03 |

**Fraction of dates with min off-diagonal < 1e-6: 0.5299.** The *median* date has a
transition probability below 1e-6. Fitted transition params reach `|13.23|`, i.e. the
multinomial logit is saturated.

Self-persistence and implied half-lives:

| regime | median `p_ii` | implied half-life |
|---|---|---|
| 0 tranquil | 0.998129 | 370 trading days (~1.5 yr) |
| 1 stressed | 0.995492 | 153 trading days (~0.6 yr) |
| 2 crisis | 0.994323 | 122 trading days (~0.5 yr) |

**This corrects an earlier reading of mine.** During the run I attributed the small
`min_offdiag` values to floating-point residue, because blocks 0–6 and 9–11 sit at ±1e-15
and straddle zero. That holds for those blocks. But blocks 8, 12 and 13 report 8.9e-27,
2.2e-10 and 1.3e-26, which cannot arise from `1 − Σ` rounding (that floors near 1e-16), and
the full-sample distribution confirms genuine saturation on 53% of dates. **The
near-absorbing pathology AMENDMENT-05 §2.2 described is still present on the real corpus.**

---

## 3. The causal series itself — a different object, and a weaker one

| Quantity | Smoothed (leaky, persisted) | **Causal (this run, not persisted)** |
|---|---|---|
| span | 5,365 days | **3,365 days** (2013-01-14 → 2026-08-21) |
| occupancy | 43.0 / 25.2 / 31.8 % | **74.3 / 7.0 / 18.7 %** |
| NFR17 separation | 2.02 σ (fails 3σ) | **0.269 σ** |
| crisis vs tranquil RV | 0.664 vs 0.389 | **0.4478 (n=630) vs 0.4117 (n=2500)** |
| LSD_t | — | mean 0.4459, sd 0.7806, range [0.000, 2.000] |
| FR23 variance | — | mean 0.0132, max 1.0000 |

The first 2,000 days (2005-01-03 → 2013-01-11) have **no causal estimate at all** and are
correctly emitted as `insufficient_history` absence, not back-filled.

**The economically important result:** in the causal setting the crisis and tranquil
regimes have realised volatility of **0.4478 and 0.4117** — a difference of 0.036, or
**0.269 σ** against NFR17's 3 σ requirement. The smoothed series' 2.02 σ already failed;
the causal series is roughly an order of magnitude worse. ξ saturates to the corners
(min 0.000000, max 1.000000) and occupancy collapses toward one regime (74.3%).

**No threshold was altered and no parameter tuned to improve any of these numbers.**

---

## 4. What this means

AMENDMENT-05 was explicit that its fix was validated only on synthetic data and that "the
failure does not reproduce on synthetic data". That is exactly what played out: the fix
passes 7/7 synthetic guards (re-confirmed today, 115.19 s) and **does not fix the real-data
anomaly**. The nesting violation it was written to eliminate is present on 6 of 14 folds and
is 5.6× worse than the single instance it documented.

Consequences, stated plainly:

1. **The causal series must not be persisted or used** — not because provenance is
   unresolved, but because on 6/14 folds the fit is demonstrably not at a maximum, on 3/14
   it did not converge, and the regimes carry almost no volatility information (0.269 σ).
   Provenance was the blocker I expected; identification is the blocker that actually bit.
2. **Hamilton stays out of the production CSRS path**, consistent with AMENDMENT-05 §6.
3. **The smoothed figures remain in-sample descriptions only.** They are not rehabilitated
   by this run; if anything the gap between 2.02 σ and 0.269 σ quantifies how much of the
   smoothed result was hindsight.
4. **A causal Hamilton is not demonstrated to be achievable at this specification.** What is
   demonstrated is that the *machinery* is correctly causal (§2c) — the estimator, not the
   plumbing, is what fails.

---

## 5. No production data or code was modified

```
git status --short
 M .claude/settings.json      <- operator's own config from an earlier session
?? .claude/worktrees/         <- harness-created, empty, not from this phase
?? docs/evidence/             <- additive only
git diff --stat -- seraph/ scripts/ tests/ docs/SPEC.md docs/ARCHITECTURE.md
(empty)
```

Row counts after the run, unchanged from before it:

| table | rows |
|---|---|
| `hamilton_output` | 5,365 (`gamma_ij` non-null: **0**, exactly as before) |
| `rmt_output` | 5,363 |
| `hawkes_output` | 0 |
| `reconciled_state` | 0 |
| `csrs` | 0 |
| `validation_results` | 0 |

No schema change, no migration, no `shared_types` edit, no model or threshold change, no
FusionWeights artefact, no CSRS run. All nine earlier evidence files preserved. The causal
ξ exists only as `causal_xi_NOT_PRODUCTION.npz` beside this report.

---

## 6. Files

| File | Contents |
|---|---|
| `run_causal_validation.py` | Stage 1 harness (isolated; wraps `fit` for diagnostics, edits nothing) |
| `run.log` | Stage 1 full stdout with provenance header |
| `causal_run.json` | Per-block schedule, llf, convergence, transition params, boundary flags |
| `causal_xi_NOT_PRODUCTION.npz` | Causal ξ, LSD, variance, warm-up index — diagnostic only |
| `stage2_nesting_and_truncation.py` | Stage 2 harness (2a transition movement, 2b nesting, 2c truncation, 2d absorption) |
| `stage2.log` | Stage 2 full stdout, exit 0 |
| `stage2_results.json` | All stage 2 measurements |
| `REPORT.md` | This file |
