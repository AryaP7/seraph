# Causal Hamilton Walk-Forward After the Two C7 Repairs

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`. Nothing
committed. Nothing persisted to `hamilton_output` or any production table.**

Evidence: `20261013T023028Z-hamilton-causal-POSTFIX/{run.log, stage2.log,
causal_run.json, causal_xi_NOT_PRODUCTION.npz, WHY-STOPPED.md}`.
Baseline for comparison: `20261012T134047Z-hamilton-causal-REAL/REPORT.md`
(pre-fix, unchanged and preserved).

---

## 0. Summary

| metric | pre-fix | post-fix | verdict |
|---|---|---|---|
| **converged blocks** | 11/14 | **14/14** | **all 3 convergence failures eliminated** |
| **nesting violations** | 6/14 | **2/14** | 7, 9 fixed by the first warm start; 6, 8 by the second (§5). The 2 survivors are diagnosed to the convergence test, not to optimisation |
| **total llf across blocks** | — | **+1,305.85** | concentrated in blocks 7 (+607) and 9 (+677) |
| **truncation invariance** | bitwise exact | **bitwise exact**, max \|Δξ\| = 0.000e+00 over 3,024 cells | causality preserved by the fix |
| **transition block exactly zero** | 0/14 | 0/14 | AMENDMENT-05 §2.1's defect signature absent in both |
| **NFR17 causal separation** | 0.269σ | **0.291σ** | still an order of magnitude below the 3σ requirement |
| **causal occupancy** | — | **70.9% / 10.0% / 19.1%** | all three states occupied, none below 10% |

The estimator is now **numerically healthy and causally correct** on the real
corpus, and still **statistically useless for regime detection**. Those are
separate facts and both are established here.

---

## 1. Block schedule

```
blk  train_n   train_last   emit_first    emit_last          llf  conv     order  min_offdiag
  0     2000   2013-01-11   2013-01-14   2014-01-15     16677.68  True (0, 1, 2)   -7.105e-15
  1     2252   2014-01-15   2014-01-16   2015-01-28     19189.79  True (0, 1, 2)   -3.553e-15
  2     2504   2015-01-28   2015-01-29   2016-02-03     21679.68  True (0, 1, 2)   -4.441e-16
  3     2756   2016-02-03   2016-02-04   2017-02-09     23983.18  True (0, 1, 2)   -3.553e-15
  4     3008   2017-02-09   2017-02-10   2018-02-15     25786.67  True (0, 1, 2)   -6.883e-15
  5     3260   2018-02-15   2018-02-16   2019-02-21     27769.04  True (0, 1, 2)   -6.661e-16
  6     3512   2019-02-21   2019-02-22   2020-03-05     30017.71  True (0, 1, 2)    5.392e-15
  7     3764   2020-03-05   2020-03-06   2021-03-10     32980.29  True (0, 1, 2)    0.000e+00
  8     4016   2021-03-10   2021-03-12   2022-03-17     34044.69  True (0, 1, 2)    1.072e-26
  9     4268   2022-03-17   2022-03-21   2023-03-23     37131.86  True (0, 1, 2)    2.356e-13
 10     4520   2023-03-23   2023-03-24   2024-04-01     38518.59  True (0, 1, 2)   -3.553e-15
 11     4772   2024-04-01   2024-04-02   2025-04-04     40705.23  True (0, 1, 2)   -3.553e-15
 12     5024   2025-04-04   2025-04-07   2026-04-15     44257.12  True (0, 1, 2)    1.205e-10
 13     5276   2026-04-15   2026-04-16   2026-08-21     45430.68  True (0, 1, 2)    2.127e-24
```

Against the pre-fix run, by block: 0 +0.01, 1 +0.02, **2 +10.28**, 3 0, 4 0,
**5 +11.20**, 6 0, **7 +607.05**, 8 0, **9 +677.10**, 10 +0.03, 11 −0.01,
12 +0.05, 13 +0.12. Regime ordering is `(0,1,2)` on every block, so the
tranquil→crisis labelling is consistent throughout.

**Blocks 7, 12 and 13 were the three pre-fix convergence failures. All three now
converge**, and block 7 — which covers the COVID emission window
2020-03-06…2021-03-10 — gained 607 log-likelihood in doing so.

## 2. Nesting: 6/14 → 4/14, with a cause for each survivor

`LL(full) ≥ LL(intercept-only)` must hold: the full TVTP model nests the
constant-transition model exactly. A negative LR is impossible at a true maximum.

```
blk  train_last       llf_full llf_restricted         LR        ok     pre-fix LR
  0  2013-01-11       16677.68       16667.45      20.47      True        +20.45
  1  2014-01-15       19189.79       19181.52      16.53      True        +16.50
  2  2015-01-28       21679.68       21664.78      29.81      True         +9.24
  3  2016-02-03       23983.18       23966.42      33.52      True        +33.52
  4  2017-02-09       25786.67       25769.04      35.27      True        +35.27
  5  2018-02-15       27769.04       27746.24      45.60      True        +23.19
  6  2019-02-21       30017.71       30306.30    -577.18     False       -577.17
  7  2020-03-05       32980.29       32969.61      21.36   **True**   **-1192.73**
  8  2021-03-10       34044.69       34682.70   -1276.02     False      -1276.01
  9  2022-03-17       37131.86       37117.62      28.49   **True**   **-1325.70**
 10  2023-03-23       38518.59       39378.13   -1719.08     False      -1668.39
 11  2024-04-01       40705.23       41866.68   -2322.90     False      -2322.88
 12  2025-04-04       44257.12       44242.52      29.20      True        +29.11
 13  2026-04-15       45430.68       45416.64      28.09      True        +27.84
```

### Why blocks 6, 8 and 10 still violate

The warm start fits the restricted model through the **non-TVTP** path
(`exog_tvtp=None`). The nesting check fits the *same* restricted model as **TVTP
with an intercept-only exog**. These are the same model mathematically and they
**do not reach the same optimum**: on block 6 the non-TVTP path reaches
**29,994.26** while the intercept-only path reaches **30,306.30** — a **312
log-likelihood** spread between two optimisations of one restricted model.

So those blocks were seeded from the weaker of two restricted optima, and the
full fit had nothing to beat the stronger one with. This is a diagnosis, not a
guess: both numbers were measured directly.

**Fix implemented:** `_tvtp_start_from_intercept_only` offers the restricted
optimum **in the same parameterisation the LR is computed against**, so with the
slopes at zero the start point reproduces `llf_restricted` exactly and BFGS can
only improve on it. Both warm starts are now offered and `fit()` still selects on
converged likelihood alone. Targeted re-test of exactly these four blocks is the
open item in §5.

### Why block 11 still violates — a different cause

Measured directly on that block: the default start reaches **41,882.55** and the
warm start **41,883.80**, both **above** the restricted 41,866.68 — but **both
report `converged=False`**. `fit()`'s converged-only rule therefore discarded
them and returned a converged candidate at **40,705.23**, which is 1,162 below
the restriction.

The rule is right in principle — a non-converged point is not a valid optimum —
but it was discarding a far better likelihood **silently**. The rule is kept; the
condition is now **visible**: `fit()` emits a `PARTIAL_COVERAGE` warning carrying
`discardedLlf`, `selectedLlf`, `convergedStarts` and `triedStarts` whenever the
best non-converged start exceeds the selected one by more than 1 llf. A large gap
there means BFGS's convergence test is failing on a flat surface, not that the
discarded point was wrong.

## 3. Causality: bitwise preserved

```
exog(y[:K]) == exog_full[:K] ?      True
overlapping finite cells compared : 3024
max |xi_full - xi_truncated|      : 0.000e+00
NaN masks identical               : True
VERDICT: bitwise identical=True   within 1e-10=True
per-block llf: 16677.6838 / 19189.7887 / 21679.6795 / 23983.1819 — all delta=0.000e+00
```

Truncating the corpus at 2017-02-09 and re-running reproduces the overlapping
regime probabilities **exactly**. The two C7 repairs did not introduce any
dependence on future observations. This is the single most important regression
check on a change to this estimator and it passes without tolerance.

## 4. The statistical verdict is unchanged

```
causal span   : 2013-01-14 .. 2026-08-21  (3365 of 5365 days)
occupancy     : 70.9% / 10.0% / 19.1%
LSD_t         : mean=0.4828 sd=0.7864 range=[0.0000, 2.0000]
FR23 variance : mean=0.0145 max=0.9994
NFR17         : 0.291 sigma   (requires >= 3; NOT tuned)
                crisis RV mean=0.4519 (n=643)   tranquil RV mean=0.4128 (n=2387)
```

All three states are occupied and none falls below 10%, so the causal fit is
**not degenerate** — a genuine improvement in behaviour. But the crisis and
tranquil RV means differ by **0.291σ**, against NFR17's 3σ and against the
full-sample non-TVTP fit's 2.02σ, which itself is indistinguishable from a
no-regime surrogate (`HAMILTON-REGIME-SUPPORT.md` §5).

**The causal series is not production-eligible and nothing here changes that.**
`hamilton_output` was not written. The smoothed in-sample occupancy
43.0/25.2/31.8 is a **different object** and is not a target this run was trying
to reproduce.

## 5. Closed and open

**Closed this run — AMENDMENT-05 §2.1, previously unresolved.** The stage-2 probe
crashed with `TypeError("float() argument must be ... not 'KimSmootherResults'")`
because `_em_iteration` returns a `(result, params)` **tuple**, leaving the claim
neither confirmed nor refuted. Measured correctly on block 0's sample:

| path | max\|Δ transition\| | max\|Δ means\| | max\|Δ variances\| |
|---|---|---|---|
| TVTP `[1, z]` | **0.000000e+00** | 1.50e-02 | 3.27e-03 |
| non-TVTP | 1.81e-01 | 6.36e-03 | 6.08e-04 |

**The claim is confirmed:** under TVTP, EM moves the transition block by exactly
zero while it does update the emission parameters. Note the second row — post-fix
the non-TVTP path's EM now moves the transition block *correctly*, where before
the repair it wrote a degenerate matrix built from three single-day
probabilities.

**Resolved — the intercept-only warm start takes 4/14 down to 2/14.** Targeted
re-test of exactly the four failing blocks (`*-31-nesting-intercept-warm-start.log`):

```
 blk  train_n     llf_full    llf_restr          LR     ok    prior LR   secs
   6     3512     30313.87     30306.30      +15.13   True     -577.18    999
   8     4016     34694.24     34682.70      +23.09   True    -1276.02   1013
  10     4520     38518.59     39378.13    -1719.08  False    -1719.08   1162
  11     4772     40705.23     41866.68    -2322.90  False    -2322.90   1278
```

Blocks **6 and 8 now satisfy nesting**: the intercept-only start lifted block 6
from 30,017.71 to **30,313.87** (+296) and block 8 from 34,044.69 to **34,694.24**
(+650), both clearing their restrictions. Final tally **2/14, from 6/14**.

**And the two survivors are now fully diagnosed — they are not optimisation
failures.** The new warning fires on exactly those blocks and gives the numbers:

| blk | best non-converged llf | llf_restricted | would the discarded point pass? |
|---|---|---|---|
| 10 | **39,392.03** | 39,378.13 | **yes, LR = +27.8** |
| 11 | **41,883.88** | 41,866.68 | **yes, LR = +34.4** |

In both cases the optimiser **found a point that satisfies nesting and then threw
it away** for failing BFGS's convergence test, returning a converged candidate
873–1,179 llf lower. So all 6 original violations trace to two causes, both now
named: 4 to a sub-optimal restricted seed (fixed), 2 to the converged-only
selection rule (surfaced, not changed).

Whether to relax that rule is a judgement about what counts as a valid optimum,
not a bug fix, so it is **left for the C7 owner**. The options are a gradient-norm
criterion instead of statsmodels' convergence flag, or accepting a non-converged
candidate when it beats every converged one by more than some margin. Either
changes what `fit()` is allowed to return and should not be decided from four
blocks.

**Still open:**

1. Near-absorbing dates are reduced but not gone — see §5b.
2. **Cost.** Offering both warm starts roughly quadruples `fit()`: each block pair
   above took **999–1,278 s**. At Hamilton's daily cadence with a 252-session
   refit interval that is acceptable; at bar frequency it would not be, and this
   is the first thing to revisit if C7's cadence ever changes.

### 5b. Transition distribution over time (stage 2d), full sample

```
full-sample TVTP fit: llf=46327.30          regime_transition shape (3, 3, 5365)
min off-diagonal transition probability, percentiles over t:
  p0 9.07e-24   p1 3.94e-18   p5 4.61e-09   p25 2.01e-07
  p50 3.29e-06  p75 1.86e-04  p100 1.36e-03
fraction of dates with min off-diag < 1e-6 : 0.3864     (pre-fix: 0.530)
  regime 0 self-persistence p_ii: median=0.998172 max=0.999907
  regime 1 self-persistence p_ii: median=0.995436 max=0.999180
  regime 2 self-persistence p_ii: median=0.994299 max=0.999279
fitted transition params max|.| = 11.592292             (pre-fix: 44.231)
```

Three improvements and one residual:

* Near-absorbing dates fall from **53.0% to 38.6%**.
* The fitted logit coefficients are far less extreme — **max |·| 11.6 against
  44.2** — so the optimiser is no longer being driven to the saturating corners.
* Self-persistence is now sane on every regime: median half-lives of **379 / 152 /
  122 trading days**, all finite and none on the boundary.
* **Residual:** 38.6% of dates still have one transition at under 1e-6. The
  script's own reading is "isolated extremes ⇒ small fraction; genuinely
  absorbing ⇒ near 1", so this sits between the two. Under TVTP a logit
  saturating at extreme `z_t` is expected rather than pathological, but 38.6% is
  too large to dismiss and is **not** explained here.

The full-sample TVTP fit at 46,327.30 against the non-TVTP fit's 46,313.5 gives
LR = **+27.6**, so nesting holds on the full sample even though 4 of 14
walk-forward blocks violate it.

## 6. Reproduction

```bash
docker start seraph-timescaledb
python docs/evidence/20261013T023028Z-hamilton-causal-POSTFIX/run_causal_validation.py
python docs/evidence/20261013T023028Z-hamilton-causal-POSTFIX/stage2_nesting_and_truncation.py
```

~2 h and ~1 h respectively. Persists nothing; writes only beside those scripts.
