# How Many Regimes Does the NSE Feature Space Support? Two C7 Repairs, and a Negative Answer

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`. Nothing committed, nothing pushed.**

Evidence: `*-22-hamilton-regime-count.log` (pre-fix), `*-23-hamilton-regime-count-POSTFIX.log`,
`*-24-hamilton-regime-support-validation.log`, `*-25-hamilton-surrogate-null.log` + `.json`,
`20261013T023028Z-hamilton-causal-POSTFIX/WHY-STOPPED.md`.
Code: `scripts/validate_hamilton_regimes.py`, `scripts/hamilton_surrogate_null.py`,
`tests/test_c7_hamilton_regime_recovery.py`, `seraph/pillars/hamilton/engine.py`.

---

## 0. Summary

| | finding |
|---|---|
| **Two real defects found and fixed in C7** | an EM-plumbing shape bug worth **16,573 log-likelihood**, and a TVTP start value implying a uniform transition matrix |
| **The estimator is now validated against ground truth** | recovers known 2- and 3-regime series at **path accuracy 1.0000**; BIC picks the true K in both directions |
| **The previous "≤2 regimes" conclusion was wrong** | it was an artefact of the EM bug. Post-fix, the real 3-state fit is non-degenerate, stable and reproducible |
| **But neither 2 nor 3 regimes is supported** | the fit is **indistinguishable from a process with no regimes at all** — AAFT surrogate null `p = 0.7143`, AR(1) `p = 0.9524` |
| **Decision** | **NEITHER SUPPORTED.** Hamilton stays explicit in the architecture with output unavailable. **No SPEC amendment is requested.** |

The headline is not that Hamilton failed again. It is that Hamilton's failure is now
**measured against a null** rather than inferred from a collapse, and that the
collapse everything was previously reasoning from was our own bug.

---

## 1. Hypothesis and methodology

`HAMILTON-UNAVAILABLE-DECISION.md` §3 concluded, from five observation designs all
leaving ≥1 of 3 states near 0% occupancy, that "the NSE daily feature space supports
at most two regimes, not three", and recommended testing a two-state formulation.

**The mandate's instruction — "do not assume that two states must work merely
because three states failed" — turned out to be the decisive one.** Running the
existing `scripts/diagnose_hamilton_regimes.py` showed two states failing *identically*
to three (both 0%/100% on the optimiser boundary), **and the 3-regime positive
control also failing when fitted with k=2**. A procedure that cannot merge two of
three well-separated synthetic regimes cannot be trusted to count regimes in real
data, so the procedure was validated first.

Methodology, in the order it was executed:

1. **Validate the procedure on known ground truth** before reading any real-data
   verdict. Markov-generated series at the real corpus's own scale and length
   (5,365 days), with known means, variances, transition matrices and state paths.
2. **Diagnose whatever the controls expose** — this is where both C7 defects were
   found, by evaluating the likelihood *at the generating parameters*.
3. **Pre-register acceptance criteria** (R1–R9, in `validate_hamilton_regimes.py`'s
   docstring) before the real-data run, and report each PASS/FAIL individually.
4. **Build a null distribution**, because non-degeneracy and persistence turned out
   not to discriminate.

### Why the previous positive control did not exonerate the estimator

The control in `compare_hamilton_features.py` is six deterministic 500-day blocks —
about **five switches in 3,000 days**. It passed (5.80σ) even while the estimator was
broken, and that pass is what grounded the claim "the estimator is exonerated by the
control". A Markov-generated 3-regime control switching every 20–40 days, which is
the realistic case, **fails** pre-fix. The control was too easy, and the exoneration
was not valid.

---

## 2. Defect 1 — the EM transition step read time-points instead of transition counts

### Root cause, located exactly

`MultivariateTVTPHamilton._conditional_loglikelihoods` returned `(k_regimes, nobs)`.
statsmodels infers the filter order from the array it gets back —
`order = conditional_loglikelihoods.ndim - 2` — so it inferred 0 instead of 1 and
allocated `smoothed_joint_probabilities` as `(k, nobs)`: the **marginals**, not the
joint. `_em_regime_transition` then computes

```python
regime_transition[i, j] = sum(joint[j, i]) / sum(marginal[i])
```

where `joint[j, i]` is meant to select the time series of `P(S_t=j, S_{t-1}=i)` but
instead selects the **scalar** smoothed probability of regime `j` on day `i`.

Measured directly, smoothing at the generating parameters (state path recovered at
**99.94% accuracy**, occupancy exact to three decimals):

| | regime 0 | regime 1 | regime 2 |
|---|---|---|---|
| true `p_jj` | 0.975 | 0.950 | 0.950 |
| **EM wrote** | **0.0004** | **0.0000** | 0.9988 |

Because `MarkovSwitching.fit` runs `em_iter=5` by default, that degenerate matrix was
applied five times before BFGS ever started. Confirmed as ours, not statsmodels':
`MarkovRegression` at the same `order=0` returns `(3, 3, 3000)` and its EM recovers
the true matrix to within 0.004.

### Cost, on a synthetic 3-regime series with known parameters

| variant | llf | occupancy | path accuracy | fitted RV means |
|---|---|---|---|---|
| `(k, nobs)` — broken | 36,478.9 | 0% / 0% / **100%** | 0.1871 | [−93439, −1789, 0.54] |
| `(k, k, nobs)` — fixed | **53,052.6** | 47% / 34% / 19% | **0.9998** | [0.399, 0.559, 0.851] |
| generating truth | 53,041.4 | 47.4% / 33.9% / 18.7% | 1.0 | [0.40, 0.56, 0.85] |

The broken variant lands **16,562 log-likelihood below the true parameter point even
when handed that point as its starting value** — the signature of a corrupted
iteration, not a flat likelihood. The fixed variant recovers the generating
transition diagonal as 0.9751 / 0.9498 / 0.9511 against a true 0.975 / 0.950 / 0.950.

### The fix changes plumbing, not the model — stated precisely

`loglike()` at fixed parameters is **not** bitwise identical between the two shapes;
it differs by **0.009754 nats, constant to six decimals for every n from 300 to
20,000**. A fixed sample-size-independent gap is the t=0 boundary condition, not a
per-observation difference (relative gap 3.1e-06 at n=300, 4.6e-08 at n=20,000).
Against a 16,573-nat optimisation gain. This corrects a claim made earlier in this
session that the likelihoods were "identical"; that was true only at print precision.

`tests/test_c7_hamilton_regime_recovery.py::test_likelihood_differs_only_by_a_fixed_initialisation_term`
asserts the constant-in-n property, which is the stronger and correct statement.

---

## 3. Defect 2 — the TVTP fit started from a uniform transition matrix

Under TVTP, `MarkovSwitching.start_params` sets the entire multinomial-logit block to
`0.0`, which implies a **uniform 1/k transition matrix — every regime half-life 1.04
days**, against the data's own constant-transition MLE at `p_jj ≈ 0.99` (half-lives
74–462 days). statsmodels additionally skips EM on that block under TVTP, so all
`(k−1)·k·k_tvtp = 12` coefficients must be found by BFGS with numerical gradients
from the worst available point.

That is the mechanism behind the walk-forward's **6/14 nesting violations**: blocks
6–11 reported a full-model likelihood *below their own nested restriction*, which
cannot happen at a true maximum.

The repair adds the nested constant-transition optimum as a **candidate start**
(`_tvtp_start_from_constant`): zero slopes, intercepts `log(p_ij / p_kj)`. That
reproduces the constant matrix exactly (`max|ΔP| = 1e-8`, llf equal to the nested fit
to 1e-4), so `llf_full ≥ llf_restricted` holds by construction.

| block | pre-fix LR vs nested | post-fix, default start | post-fix, warm start |
|---|---|---|---|
| 0 | +20.45 ok | +20.47 ok (llf 16,677.68) | +9.29 (llf 16,674.87) |
| 6 | **−577.18 VIOLATION** | **−10.79 VIOLATION** | **+46.90 ok** |
| 11 | **−2,322.88 VIOLATION** | **+31.74 ok** (llf +1,177 vs pre-fix) | **+34.25 ok** |

`fit()` still selects among starts on **converged likelihood alone**, so block 0 keeps
its better default start. This floors no parameter, changes no regime count, adds no
covariate and does not alter the likelihood.

**Not yet established:** that all 6 violations are eliminated. Two of six were tested.
The full 14-block re-run is the next concrete step (§8).

---

## 4. Results — 3-state, 2-state, controls

### 4.1 Pre-registered criteria

| | criterion | verdict | evidence |
|---|---|---|---|
| **R1** | procedure recovers known K | **PASS** | path accuracy **1.0000** both k=2 and k=3; occupancy dev 0.000; diag dev 0.001 / 0.003; BIC picks true K in both directions |
| **R2** | no-regime controls rejected | **FAIL** | see §4.3 |
| **R3** | min occupancy ≥ 10% | PASS at k=2,3,4 | 68/32; 43/25/32; 28/27/22/22 |
| **R4** | identifiable, half-life ∈ [5,2000]d | PASS at k=2,3,4 | no boundary; 177/134/169 d at k=3 |
| **R5** | **NFR17 ≥ 3σ** | **FAIL at every K** | 1.64 (k=2), **2.02** (k=3), 2.26 (k=4) |
| **R6** | ≥5/6 chronological folds | k=2 **5/6 PASS**, k=3 **4/6 FAIL** | §4.4 |
| **R7** | initialisation robustness | **PASS** | 8/8 seeds, llf spread **0.00** |
| **R8** | median regime run ≥ 5 d | PASS | 296 / 116 / 66 d |
| **R9** | BIC prefers K | **no interior optimum** | BIC k2 −86,576 → k3 −92,421 → **k4 −94,691** |

### 4.2 Real corpus, full sample (5,365 days, 2005-01-03 → 2026-08-21)

```
                case  k        llf    sep            occupancy       half-lives (d) medrun        BIC
      real RV+AR+BAS  2    43347.9   1.64              68%/32%              496/191    296     -86576
      real RV+AR+BAS  3    46313.5   2.02          43%/25%/32%          177/134/169    116     -92421
      real RV+AR+BAS  4    47500.0   2.26      28%/27%/22%/22%         131/68/34/97     66     -94691
```

Post-fix this is a well-behaved fit: non-degenerate, off the boundary, plausible
persistence, and **perfectly reproducible** — all 8 initialisations return llf
46,313.5 / sep 2.02 / occupancy 43/25/32 with zero spread. The k=3 occupancy
43.0/25.2/31.8 and NFR17 2.02σ reproduce the stored `hamilton_output` series exactly,
so that series was always this optimum; its defect is non-causality (smoothed), not
degeneracy.

**Separation and BIC both increase monotonically in K, with no interior optimum.**
On synthetic data with a true K, BIC picked it correctly (R1). On real data it just
keeps going. That is the signature of an HMM approximating a smooth persistent
process with a step function, not of discovering discrete regimes.

### 4.3 R2 — the controls, and why this is the decisive result

Three controls. Two are rejected; the one that matters is not.

```
                        case  k        llf    sep            occupancy       half-lives (d) medrun   R3/R4/R5/R8
                     NEG-iid  2    36238.9   0.22               4%/96%                 6/38     17   X . X .
                     NEG-iid  3    36246.4   0.16           21%/3%/77%                9/1/5      3   X X X X
  NEG-ar1 (smooth, 1 regime)  2    39145.1   0.97              66%/34%              617/313    286   . . X .
  NEG-ar1 (smooth, 1 regime)  3    42090.4   1.45          44%/22%/33%          382/196/312    288   . . X .
  -------------------------------------------------------------------------------------------------
              REAL for compare  3    46313.5   2.02          43%/25%/32%          177/134/169    116   . . X .
```

`NEG-ar1` is a vector AR(1) with **exactly one regime by construction**, matched to
the real data's lag-1 autocorrelation (achieved 0.9972/0.9990/0.9960 against real
0.9973/0.9983/0.9965), marginal moments and innovation cross-covariance. Fitted with
k=3 it returns occupancy **44%/22%/33%** against the real data's **43%/25%/32%**,
with finite plausible half-lives and a 288-day median run — passing R3, R4 and R8
exactly as the real data does.

**Occupancy, persistence, identifiability and reproducibility cannot tell the real
data apart from a process containing no regimes.** Every criterion the post-fix fit
passes, a one-regime series with matched smoothness passes too.

### 4.4 R6 — fold-level stability

```
  k=3
        fold0 2005-01..2008-07  sep 2.65   32%/36%/32%     66/113/98   ok
        fold1 2008-07..2012-03  sep 2.44   48%/19%/33%     BOUNDARY    R4 FAIL
        fold2 2012-03..2015-10  sep 1.58   34%/26%/40%     70/79/60    ok
        fold3 2015-10..2019-05  sep 3.86   61%/24%/14%     189/77/22   ok  (NFR17 pass)
        fold4 2019-05..2023-01  sep 1.96   68%/22%/ 9%     421/138/58  R3 FAIL
        fold5 2023-01..2026-08  sep 3.46   18%/41%/41%     112/82/61   ok  (NFR17 pass)
    -> 4/6 satisfy R3+R4 — FAIL
```

Separation ranges **1.58 to 3.86** across folds, a 2.4× spread, and only 2 of 6 folds
clear NFR17. At k=2, 5/6 folds satisfy R3+R4 (fold1 hits the boundary) but **all six
fail NFR17** (0.89–2.62). Neither state count is stable across history.

---

## 5. The surrogate null — the quantitative answer

20 independent surrogates per family, same length, same estimator, same settings.
Decision rule pre-registered: genuine only if `p ≤ 0.05` under **both** families
**and** `sep ≥ 3.0`.

| family | what it preserves | null sep mean | sd | median | max | `#≥ real` | **p** |
|---|---|---|---|---|---|---|---|
| `ar1` | lag-1 ACF, marginal moments | 4.109 | 1.281 | 3.625 | 6.682 | 19/20 | **0.9524** |
| `aaft` | **exact marginal**, full ACF | **2.147** | **0.202** | 2.077 | 2.686 | 14/20 | **0.7143** |

Real `sep = 2.0197`.

The AAFT family is the stronger control: amplitude-adjusted Fourier transform with
jointly randomised phases preserves the **exact** marginal distribution of each
column and approximately its whole autocorrelation function, destroying only
regime structure. Its null is extremely tight — **2.147 ± 0.202** — and the real
value sits **0.63 sd below the null mean**. This is not a marginal miss; the real
separation is what a no-regime process with these statistical properties produces.

**VERDICT (pre-registered): NOT DISTINGUISHABLE from a no-regime process.**

### Two findings that travel beyond Hamilton

1. **NFR17 as specified is not a regime test.** 18 of 20 single-regime AR(1)
   surrogates exceed its 3σ threshold (3.36–6.68). A fit "passing NFR17" on a smooth
   series is passing a test that a process with no regimes passes 90% of the time.
   This is reported as a specification observation; **NFR17 was not changed**, and
   R5 was scored against 3.0σ exactly as written.
2. **Why smoothness inflates the metric.** `sep = (μ_crisis − μ_tranquil)/σ_within`.
   A highly persistent Gaussian process wanders slowly across a wide range, so a
   3-state HMM carves it into bands with small within-band variance and large
   between-band spread — a large `sep` with no regimes present. The real data's
   jumps and fat tails *raise* within-band variance, which is why AR(1) surrogates
   score **above** the real data and AAFT surrogates — which keep the real marginal —
   land right on it.

---

## 6. Decision, and the approval gate

**NEITHER two nor three regimes is supported on the available causal NSE daily
feature space.** Hamilton remains explicit in the architecture (P3: regime dynamics
and stress persistence) with its output **unavailable** via D2's structural-absence
mechanism, exactly as before — but the reason is now a measured null result rather
than an estimator collapse.

**No SPEC amendment is requested.** For completeness, the gate a state-count change
*would* have hit, since the mandate asked:

| artefact | why a 2-state model is not interface-compatible |
|---|---|
| **FR20** | specifies "multivariate **three-state** TVTP Hamilton filter" |
| **FR23** | `LSD_t = ξ_{2,t} + 2ξ_{3,t}` is a three-state formula; at k=2 its range collapses from [0,2] to [0,1], changing the scale C8 consumes |
| **FR24** | names "the **stressed and crisis** regimes" — two non-tranquil states |
| **O4 acceptance** | "non-degenerate **three-regime** solution with ordered means" |
| **`HamiltonDetail`** | `xi: Simplex3`, `p_hat_22`, `p_hat_33`, `tau_half_stressed`, `tau_half_crisis` — in **ask-gated** `seraph/shared_types/` |

A two-state research experiment was run (it is compatible with `fit(k_regimes=2)`,
which already takes the parameter) and **its result does not justify requesting any
of the above.** Nothing in `seraph/shared_types/`, `schema.sql` or any migration was
touched.

**What would reverse this decision.** A feature set, frequency or sample on which the
k=3 fit's separation exceeds the AAFT surrogate null at `p ≤ 0.05` **and** clears
NFR17's 3σ. The null is cheap to recompute: `scripts/hamilton_surrogate_null.py`
against any candidate observation vector. That is the bar any future Hamilton
redesign must clear before its output is used, and it is a bar none of the six
designs tried so far comes close to.

---

## 7. Changes made, tests run, limitations

### Files changed

| file | change |
|---|---|
| `seraph/pillars/hamilton/engine.py` | **C7.** `_conditional_loglikelihoods` returns `(k,k,nobs)`; new `_tvtp_start_from_constant`; `fit()` appends the nested-MLE warm start under TVTP. +120/−5. |
| `scripts/validate_hamilton_regimes.py` | new — R1–R9 with pre-registered criteria, three controls, folds, seeds, interpretation |
| `scripts/hamilton_surrogate_null.py` | new — AR(1) and AAFT surrogate nulls with a pre-registered decision rule |
| `tests/test_c7_hamilton_regime_recovery.py` | new — 11 regression tests for both repairs |

Untouched: `seraph/shared_types/`, `schema.sql`, all migrations, C8, C9, C10, every
production table, and both parallel worktrees.

### Tests

| suite | result |
|---|---|
| `tests/test_c7_hamilton_regime_recovery.py` | **11 passed** |
| `test_c7_hamilton.py` + `test_c7_hamilton_causal.py` | **15 passed** |
| above + CT-4 / CT-5 / CT-7 / CT-9 | **34 passed** |
| all of `tests/`, final state after every change | **170 passed, 1 failed** (`*-30-final-full-suite.log`) |

The single failure is `test_ct3_jump_sufficiency` (0.09 negative jumps/symbol-day
against a floor of 1.0) — **pre-existing**, recorded in `STRESS-PILLAR-DECISION.md`
§5, in C4/Hawkes territory and unrelated to C7. No regression.

Three of my own tests failed first and were corrected, not weakened:

* two compared the fitted transition diagonal to the **generating** matrix; the MLE
  targets the realised sample, whose `p_22` on that draw is 0.896, reproduced to four
  decimals by both the EM step and the full MLE. They now compare against the
  realised transition frequencies and the tolerance was **tightened** 0.05 → 0.03.
* one asserted bitwise likelihood equality across the shape change. The gap is a
  fixed 0.009754-nat initialisation term; the test now asserts the stronger
  constant-in-n property.

### Limitations

1. **The null uses 20 reps per family**, so the finest resolvable p-value is 1/21 ≈
   0.048. Adequate for a non-rejection (p = 0.71 and 0.95) but it could not have
   established a strong positive.
2. **Surrogate fits use `restarts=1`** against the real fit's 4, for runtime. R7
   showed zero llf spread across 8 seeds on real data, so this is unlikely to matter,
   but it is not proven for surrogates.
3. **AAFT preserves the marginal and the linear ACF, not nonlinear dependence.**
   Volatility clustering beyond the ACF is partially destroyed, which if anything
   makes the control conservative.
4. **Only the SPEC's `y_t = (RV, AR, BAS)` was tested against the null.** The six
   alternative observation designs were tested against the older, weaker criteria.
5. **Only 2 of 6 nesting violations re-tested** (§3).
6. Six epochs, one with a provisional break date (SPEC OQ3 open).

### Unresolved

* Whether the warm start clears all 6 nesting violations (§8).
* Whether any observation design can clear the surrogate null — untested for the five
  non-SPEC designs.
* **The early-warning problem is untouched by this work.** T3 remains below chance for
  everything tested. A working regime filter would not by itself have been evidence of
  advance warning, and no such claim is made.

### Descriptive interpretation (in-sample, not a detection claim)

Fitted RV means [0.389, 0.489, 0.664]. Crisis-state share in the 30 days after each
FR32 break: GFC **100%**, IL&FS **76.7%**, COVID **66.7%**, taper / tightening /
tariff **0.0%** — against a 31.8% unconditional base rate. Three of six epochs light
up. These are smoothed in-sample labels and, given §5, are not evidence of regimes.

---

## 8. Next concrete step

**Re-run the 14-block causal walk-forward with the warm start and re-run stage 2's
nesting check**, to establish whether all 6 violations are eliminated rather than the
2 of 6 tested here:

```bash
docker start seraph-timescaledb
python docs/evidence/20261013T023028Z-hamilton-causal-POSTFIX/run_causal_validation.py
python docs/evidence/20261013T023028Z-hamilton-causal-POSTFIX/stage2_nesting_and_truncation.py
```

~2–3 h, persists nothing. This matters independently of the regime verdict: the
nesting violation is a *correctness* defect in C7's optimiser, and C7 should be left
correct whether or not its output is currently used. It does not reopen §6 — a
well-identified TVTP fit would still have to clear the surrogate null.

### Reproduction

```bash
docker start seraph-timescaledb
python scripts/diagnose_hamilton_regimes.py                 # 2 vs 3 vs 4, full sample
python scripts/validate_hamilton_regimes.py                 # R1-R9, ~25 min
python scripts/hamilton_surrogate_null.py --reps 20 --k 3    # the null, ~45 min
pytest tests/test_c7_hamilton_regime_recovery.py -q          # 11 passed
```

---

## 9. Corrections to `HAMILTON-UNAVAILABLE-DECISION.md`

That document's **conclusion stands** — Hamilton's output is unavailable — but three
of its supporting claims do not, and it should not be cited for them:

| claim | status |
|---|---|
| §2 "the estimator is exonerated by the control" | **WRONG.** The control was six 500-day deterministic blocks and passed while the estimator was broken. A realistically-switching 3-regime control fails pre-fix, and the defect is now located to a line. |
| §3 "the NSE daily feature space supports at most two regimes, not three" | **WRONG.** An artefact of the EM bug. Post-fix all three states are populated 43/25/32 with finite half-lives — and two states fare *worse* than three on every criterion. |
| §2(a) "6/14 nesting violations… AMENDMENT-05's fix does not resolve it" | **Correct as a measurement, wrong as a diagnosis.** The cause is the TVTP start value, not the multi-start logic; §3 above fixes 2 of 2 blocks tested. |
| §4.3 the stored series' "occupancy 43.0/25.2/31.8, NFR17 2.02σ" | **Confirmed.** Reproduced exactly post-fix, from 8/8 initialisations. Still smoothed and still non-causal. |
| §1 "downside semivariance is not a Hamilton regime filter" | **Unchanged and still in force.** |

**All three pillars remain explicit.** P1 Hawkes operational, P2 RMT operational,
P3 Hamilton unavailable — now with a quantified reason and a stated reversal bar.
