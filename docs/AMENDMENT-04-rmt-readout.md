# AMENDMENT-04 — What Pillar 2 actually measures, and which spectral statistic is reportable

**Status:** Proposed 2026-08-23, pending sign-off. Two code defects are already **fixed** (§2 — that
part is not a proposal). Sections 3–6 are measurement and interpretation; they change no requirement
text and no model.

**Applies to:** SPEC FR16, FR17, FR19; AMENDMENT-02 §3.2 and its report paragraph (**one claim there
is falsified — see §5**); report §5.2 and §7.5; the FR30 weighting of Pillar 2 in C8/C9.

**Supersedes:** the two "not yet explained" observations recorded in HANDOFF.md §4.

Evidence: `scripts/diagnose_rmt_findings.py` (§3, §4) and `scripts/compare_rmt_statistics.py` (§6),
both over the same sweep of 537 dates, 2005-01-03 → 2026-08-19, stride 10, using the window and
universe the validation run uses. Every number below is measured.

---

## 1. Summary

Three things were open on Pillar 2, and a fourth was found while closing them. None is a modelling
error:

1. **FR16's trace guard failed because of an arithmetic defect in `_correlation`.** Real bug, fixed,
   verified. It was *not* the constant-column guard the handoff suspected.
2. **`F_t` does not rise at labelled breaks because it cannot.** Three separate mechanisms push it
   the wrong way, the largest of which is that `C_t` at a break date is estimated entirely on data
   preceding the break.
3. **FR19's p-value is significant on every date because its null is false on every date**, by a
   margin of roughly two orders of magnitude. The bootstrap is correctly calibrated; the hypothesis
   it tests is simply not in doubt.
4. **The 163 skipped dates were not a data limitation — they were two ETF sessions.** Found while
   re-running; fixed. See §2.2.

The consequence that matters for the report: **Pillar 2 is a trailing estimator of the coupling
regime, not an event detector**, and `F_t` is the weakest of the three FR17 signals for cross-date
use.

---

## 2. Two defects found and fixed

### 2.1 The FR16 trace defect

`seraph/pillars/rmt/engine.py::_correlation` computed the standard deviation with `ddof=1` (dividing
by `T − 1`) but normalised the Gram matrix of the resulting z-scores by `T`. Every diagonal entry was
therefore exactly `(T − 1) / T`, so

```
trace(C_t) = N_t (T − 1) / T        ⇒        N_t − trace(C_t) = N_t / T
```

which at `N_t = 499, T = 1000` is `0.499` — reproducing the reported `max |trace(C_t) − N_t| =
4.99e-01` exactly, and confirming the deficit was **purely** this scale error. The handoff's
hypothesis (constant columns guarded to `sd = 1`) was wrong: a zeroed column removes a whole unit
from the trace, so any such column would have produced an integer-sized deficit. The observed
deficit was `N_t / T` on the nose, which means **no date in the corpus contained a constant column.**

**Impact on published numbers.** `C_wrong = C_right · (T−1)/T` is an exact scalar multiple, which
bounds the damage precisely:

- **`F_t` was biased downward.** Every eigenvalue was shrunk by 0.999 while the MP edges — evaluated
  at `σ² = 1` — were not, so any eigenvalue sitting within 0.1% above `λ₊` was miscounted as bulk.
- **`Ω_t` and all D3 results are unaffected.** A scalar multiple has identical eigenvectors.
- **`V_t^eig` and `λ₁/N` are also unaffected**, because the implementation divides by the *realised*
  trace (`λ₁ / Σλᵢ`) rather than by `N_t`. The scalar cancels. The broken identity `Σλᵢ = N_t` was
  therefore a genuine defect in the reported guard and in the docstring's justification, but it did
  not propagate into the velocity signal — the code was accidentally robust to its own bug.
- **`SCA_t` moves only through its `F_t` component**, and only where the ECDF rank changed.

So §3 and §4 below, which rest on `λ₁/N`, were never contaminated by this defect.

**Fix.** Divide by `T − 1` to match the `ddof`. Constant columns — which did not occur, but are not
prevented from occurring — are now given an explicit isolated unit-variance mode rather than a zero
diagonal: that contributes exactly one eigenvalue of `1.0`, which lies strictly inside the MP band
for every `Q > 1` and so cannot inflate `F_t`, while keeping `trace(C_t) = N_t` exact. The
substitution is announced with an `ESTIMATOR_FALLBACK` warning rather than absorbed silently.

**Verified:** `max |trace(C_t) − N_t| = 2.84e-13` across all 537 sweep dates (machine precision);
`2.27e-13` on the `run_rmt.py` corpus run, against `4.99e-01` before. CT-10 passes 5/5, and five new
regression guards in `tests/test_c6_rmt.py` pin the identity, agreement with `np.corrcoef`, and the
degenerate-column path.

### 2.2 Two gold-ETF sessions were costing 30% of the corpus

The earlier run reported "374 dates evaluated, 163 skipped" and the shortfall was read as a data
limitation. It was not. **`2010-05-16` and `2012-11-11` are gold-ETF-only sessions** — six and eleven
rows respectively, every one an ETF (`GOLDBEES`, `SETFGOLD`, `QGOLDHALF`, …), with **no equity
trading on either date**.

`run_rmt.py::load` built its trading-day grid from every symbol in `daily_prices`, which still
physically contains ETF rows even though the universe itself is ETF-free under the FR52 ISIN filter.
Those two sessions therefore entered the grid as phantom equity trading days. Because FR16 requires
a finite price on all 1,001 days of the window, **a single phantom date invalidates every window
containing it** — and at `T = 1000` that is ~1,001 consecutive windows, i.e. ~100 evaluation dates
per phantom session at `stride = 10`. Two sessions, minus overlap, gives the 163 that were skipped.

This is the same ETF-contamination class already recorded for C3, entering through a different door:
the *date grid* rather than the *membership list*. The fix is to build the grid from universe
members only, which are ETF-free by construction.

**Consequence for the report:** the earlier "374 dates / 2005-01-03 → 2026-08-17" coverage figure
understates Pillar 2's real coverage and must not be quoted.

---

## 3. Why `F_t` does not rise at labelled breaks

Three mechanisms, all properties of `F_t` as FR17 defines it. They compound.

### 3.1 The window has not seen the crisis yet (dominant)

`C_t` is estimated on the 1,000 trading days **ending** at `t`. On the labelled break date the
episode contributes **zero observations**. Even a full trading day of perfect co-movement can move a
1,000-day second moment by at most about `1/1000`. Asking `F_t` to rise *on* a break date asks a
four-year moving average to respond to its newest observation.

The lag profile makes this concrete — `λ₁/N` at and after each break:

| Epoch | +0m | +6m | +12m | +18m | +24m | +30m | +36m | peak |
|---|---|---|---|---|---|---|---|---|
| gfc_2008 | 0.2634 | 0.2907 | 0.3392 | **0.3492** | 0.3315 | 0.3447 | 0.3465 | **+18m** |
| taper_2013 | 0.2340 | 0.2148 | 0.2082 | 0.2197 | 0.2092 | 0.2138 | 0.2166 | +0m |
| ilfs_2018 | 0.2226 | 0.2229 | 0.2110 | 0.2205 | **0.2462** | 0.2374 | 0.2391 | **+24m** |
| covid_2020 | 0.1996 | 0.2408 | 0.2368 | 0.2397 | 0.2461 | 0.2544 | **0.2547** | **+36m** |
| tightening_2022 | 0.2429 | **0.2560** | 0.2553 | 0.2517 | 0.2532 | 0.2195 | 0.2241 | +6m |
| tariff_2026 | 0.2370 | 0.2334 | — | — | — | — | — | (corpus ends) |

The two largest systemic episodes in the sample peak **18 and 36 months after** their break dates.
The corpus-wide maxima of `λ₁/N` land in **2010-05/06 (0.3546)** and **2011-12 / 2012-02 (0.3550)** —
i.e. when the GFC and the euro-area crisis sit fully inside the estimation window, not when they
began.

COVID is the sharpest illustration: at its break date `λ₁/N = 0.1996`, the **0th percentile of the
entire corpus** — the single least-coupled reading in twenty-one years, on the eve of the largest
crash in the sample. The preceding four years were calm, and that is all the window can see.

### 3.2 The exceedance *count* moves against coupling

`corr(k_above, λ₁/N) = −0.244` across the sweep. As the market mode inflates it **absorbs** the
sub-leading sector modes into the bulk, so the number of eigenvalues above `λ₊` falls while coupling
rises. This is the "sub-leading eigenvalues collapse" phenomenon the engine's own module docstring
describes — `F_t` counts exactly the modes that stress destroys.

### 3.3 `F_t`'s denominator makes it a proxy for `1 / N_t`

`corr(F_t, N_t) = −0.739` — by far the strongest relationship `F_t` has with anything measured here.
The reason is structural: the number of genuine factor modes is a property of the market, not of the
sample, so it grows far slower than `N_t`.

| `N_t` bucket | median `k_above` | median `F_t` |
|---|---|---|
| 122 | 4 | 0.0323 |
| 469 | 8 | 0.0170 |
| 499 | 11 | 0.0221 |

Across the full four-fold rise in `N_t`, `k_above` less than triples, so dividing by `N_t` drags
`F_t` down. The **correlation of −0.739 over all 537 dates is the evidence**, not this table: the
buckets are selected by `|N_t − target| ≤ 5%` and therefore fall in different eras with different
market structure, which is why 469 → 499 moves the wrong way. The mechanism is nonetheless
structural — the number of genuine factor modes is a property of the market, not of the sample —
and under AMENDMENT-02 `N_t` ranges over 122–499, so it contaminates every cross-date comparison in
the corpus.

### 3.4 Confirmation: the coupling is there, the window dilutes it

Same date, same aspect ratio `Q ≈ 2`, shorter memory (`T = 2N`):

| Epoch | `T=500, N=250` | `T=250, N=125` |
|---|---|---|
| gfc_2008 | 0.3153 | **0.4168** |
| covid_2020 | 0.2273 | **0.2879** |
| taper_2013 | 0.2624 | 0.2943 |

At the GFC break, halving the memory again raises `λ₁/N` from 0.315 to 0.417. The stress signal
exists at short horizons; FR16's `T = 1000` averages it away.

*Why there is no `T = 1000, N = 500` column:* fewer than 500 members have a full 1,000-day history
at these dates, so that cell cannot be filled at `Q = 2` and only the two columns above are strictly
aspect-ratio-matched. The in-force `T = 1000` readings are in §3.1's table — 0.2634 for the GFC, but
at `N = 304, Q = 3.29`, so it is not a clean like-for-like against the two columns here.

**This is a diagnostic, not a proposal.** FR16 pins `T = 1000`, and `T` is not freely tunable
anyway: `Q = T/N ≥ 1` is required for the MP support formula, so at `N = 500` the shortest
admissible window is already 500 days ≈ 2 years. **A short-horizon RMT signal is not reachable at
`N = 500` without abandoning FR16's cross-section.** No change is proposed here; the constraint is
reported.

---

## 4. Why FR19 rejects on 100% of dates

The bootstrap null is an iid standard-normal panel of the same shape — i.e. "no cross-correlation
whatsoever". Measured, at 200 replications:

| Shape `(T, N)` | null `F` mean | null `F` max | **null `k_above` max** | observed `F` median | observed `k_above` median |
|---|---|---|---|---|---|
| (1000, 122) | 0.00053 | 0.00820 | **1** | 0.0323 | 4 |
| (1000, 469) | 0.00021 | 0.00213 | **1** | 0.0170 | 8 |
| (1000, 499) | 0.00017 | 0.00200 | **1** | 0.0221 | 11 |

The null never once produced more than **one** eigenvalue above `λ₊`. The real market produces
**4 to 12** on every date. The **smallest** `F_t` observed anywhere in the corpus (0.01486) exceeds
the **largest** value the null ever generated (0.00820) by a factor of 1.8.

So the p-value is not merely small — it is **pinned at the floor `1/(reps+1)` by construction**, on
every date, and would be at any replication count (0.00498 at 200 reps, 0.000999 at FR19's specified
1,000). The bootstrap is correctly calibrated. The null hypothesis is simply one that no equity
market has ever satisfied: a market factor guarantees its rejection.

**Therefore FR19's p-value is a structure sanity-check, not a discriminator.** It confirms the
pillar is reading genuine correlation rather than estimation noise — a real and worthwhile check,
and it passes. It carries **zero** cross-date information, because a statistic that is constant
cannot rank anything.

---

## 5. What this falsifies in AMENDMENT-02

AMENDMENT-02 §3.2 argued, and its report paragraph states:

> "the parametric bootstrap p-value, which is computed under the configuration in force on each day,
> is the comparable statistic and is the one used for cross-date inference."

**This is false and must be corrected before the report is written.** The p-value is saturated at
its floor on 100% of dates (§4), so it cannot serve as a cross-date statistic. AMENDMENT-02's
comparability objection to a floating `N_t` was therefore never actually answered — §3.3 above shows
`F_t` is not merely non-comparable across `Q`, it is roughly a proxy for `1/N_t`.

AMENDMENT-02's **decision** (floating `N_t`, `λ±` at the realised `Q_t`) is unaffected and remains
correct — the MP law is a function of `Q`, and that reasoning stands. What fails is only its
argument that FR19 neutralises the resulting comparability problem.

---

## 6. Choosing the Pillar 2 state statistic — empirical comparison

`λ₁/N` is **not** adopted merely because the FR19 p-value is degenerate. A degenerate incumbent shows
the incumbent is unusable; it says nothing about which replacement is right. Five candidates were
therefore compared head-to-head on the existing corpus (537 dates, `stride = 10`) against eight
criteria, with the selection rule fixed **before** looking at the results:

> The statistic must be **exactly normalised and well-defined as `N_t` changes**, **non-degenerate**,
> **stable enough to serve as a slow state**, **free of rebalance artefacts**, and **not redundant**.
> Crisis-chart appearance is explicitly *not* a criterion. Criterion C (behaviour at labelled breaks)
> is documented for the record and was **not** used to rank.

Evidence: `scripts/compare_rmt_statistics.py`.

### 6.1 Candidates

| # | Statistic | Definition |
|---|---|---|
| 1 | `lam1_share` | `λ₁ / N` — leading-mode variance share |
| 2 | `f_t` / `k_above` | FR17 exceedance fraction `k/N`, and the raw count `k` above `λ₊` |
| 3 | `signal_mass` | `Σ_{λᵢ>λ₊} λᵢ / N` — concentration over *all* deviating modes |
| 4 | `p_value` | FR19 parametric bootstrap p-value |
| 5 | `sca_t` | FR18 aggregate, already required by SPEC |

`V_t^eig` is the derivative of candidate 1, not a level, so it is not a competitor for the same slot;
FR17 requires it regardless.

### 6.2 Criteria A + D — distribution and non-degeneracy

| Candidate | mean | sd | CV | min | max | #distinct | share at modal value |
|---|---|---|---|---|---|---|---|
| `lam1_share` | 0.25349 | 0.04243 | 0.167 | 0.19800 | 0.35501 | **537** | **0.2%** |
| `f_t` | 0.02200 | 0.00475 | 0.216 | 0.01486 | 0.04098 | 129 | 10.4% |
| `k_above` | 8.223 | 2.117 | 0.257 | 4 | 12 | **9** | 22.2% |
| `signal_mass` | 0.33102 | 0.04619 | 0.140 | 0.26607 | 0.43752 | **537** | 0.2% |
| `p_value` | 0.00498 | **0.00000** | **0.000** | 0.00498 | 0.00498 | **1** | **100%** |
| `sca_t` | 0.43834 | 0.14253 | 0.325 | 0.04167 | 0.89167 | 518 | 1.5% |

`p_value` takes **one** value on all 537 dates — formally degenerate, zero information. `k_above`
takes only **nine** distinct integer values, far too coarse for a continuous state, and `f_t`
inherits that coarseness (10.4% of dates share a single value).

### 6.3 Criterion B — temporal stability (steps of 10 trading days)

| Candidate | lag-1 autocorr | median step ÷ IQR | reading |
|---|---|---|---|
| `lam1_share` | **0.9958** | **0.027** | smooth slow state |
| `signal_mass` | 0.9941 | 0.017 | smooth slow state |
| `k_above` | 0.9873 | 0.000 | smooth but discrete |
| `f_t` | 0.9743 | 0.000 | smooth but discrete |
| `sca_t` | **0.4250** | **0.494** | **jumpy — not a slow state** |
| `p_value` | n/a (constant) | — | — |

A systemic-*coupling* state feeding a Kalman filter must be slow-moving. `SCA_t` is not: its lag-1
autocorrelation is 0.425 and its typical 10-day step is half its own IQR.

### 6.4 Criteria E + F — sensitivity to `N_t` and to rebalances (**decisive**)

*Observational* — correlation with `N_t` across the corpus, and step size at rebalance dates:

| Candidate | corr with `N_t` | median step at rebalance ÷ elsewhere |
|---|---|---|
| `lam1_share` | −0.566 | 0.35 |
| `f_t` | −0.739 | — (median step is 0) |
| `k_above` | **+0.830** | — (median step is 0) |
| `signal_mass` | −0.371 | 0.11 |
| `sca_t` | +0.067 | **2.48 — rebalance artefact** |

The observational correlation is **confounded**: `N_t` grows over time, so it is entangled with era,
and it cannot separate "depends on `N_t`" from "the market changed". A controlled experiment can.

*Experimental (causal)* — **same date, same `T = 1000`, cross-section randomly thinned**; 12 dates
with a full cross-section, 8 random subsets per size. Only `N` varies, so any drift is pure
`N`-dependence:

| Candidate | N=120 | N=240 | N=360 | N=480 | pooled drift |
|---|---|---|---|---|---|
| `lam1_share` | 0.24163 | 0.23771 | 0.23759 | 0.23745 | **+1.8%** |
| `f_t` | 0.03073 | 0.02509 | 0.02286 | 0.02120 | +44.9% |
| `k_above` | 3.688 | 6.021 | 8.229 | 10.177 | −63.8% |
| `signal_mass` | 0.29729 | 0.30881 | 0.31948 | 0.32801 | −9.4% |
| `p_value` | 0.00498 | 0.00498 | 0.00498 | 0.00498 | 0.0% * |

Within-date paired ratio `stat(N=120) / stat(N=480)`, which removes date effects entirely:

| Candidate | mean ratio | min | max | verdict |
|---|---|---|---|---|
| `lam1_share` | **1.0176** | **0.9961** | **1.0302** | **`N`-invariant on every test date** |
| `f_t` | 1.4494 | 1.1111 | 1.7500 | strongly `N`-dependent |
| `k_above` | 0.3623 | 0.2778 | 0.4375 | strongly `N`-dependent |
| `signal_mass` | 0.9060 | 0.8743 | 0.9339 | mildly but *systematically* `N`-dependent |
| `p_value` | 1.0000 | 1.0000 | 1.0000 | * invariant only because it is constant |

**This is the result that decides the question.** `λ₁/N` stays inside `[0.996, 1.030]` on *every one*
of the twelve dates while the cross-section is thinned four-fold. `signal_mass` is low by 9–13% on
every date — a small but systematic bias in one direction, which would silently make the
thin-universe early corpus look less coupled than it was. `f_t` and `k_above` move by 45–64% and are
disqualified outright.

`signal_mass` fails for an understandable reason: it sums *all* modes above `λ₊`, and the number of
such modes itself grows with `N` (`k_above` rises 3.7 → 10.2 across the grid). `λ₁` is a single,
well-separated mode, so its share does not inherit that growth.

`sca_t` has no single-window definition (it is an ECDF rank over rolling history) and so cannot enter
this experiment; its `N`-sensitivity is inherited from `f_t`, the worst performer in the table.

### 6.5 Criterion H — incremental information

Pairwise correlation, and `R²` of each candidate regressed on the other four:

| Candidate | `R²` on the others | reading |
|---|---|---|
| `lam1_share` | 0.9875 | near-substitute for `signal_mass` (r = **0.938**) |
| `signal_mass` | 0.9892 | near-substitute for `lam1_share` |
| `k_above` | 0.9137 | largely redundant |
| `f_t` | 0.7722 | some independent content |
| `sca_t` | 0.1431 | genuinely independent |

`lam1_share` and `signal_mass` are two readings of the same quantity (r = 0.938) — **one of them, not
both, belongs in the state**, and criterion E chooses between them. The high `R²` for `lam1_share` is
not an argument against it: it means the other spectral statistics add nothing once it is present,
which is exactly what a sufficient state variable should look like.

### 6.6 Criterion G — well-definedness as `N_t` changes

`λ₁/N` is well-defined for every `N_t ≥ 1` and bounded in `[0, 1]` by construction, because
`trace(C_t) = Σλᵢ = N_t` is an exact identity — genuinely exact only since the §2.1 fix. It needs no
null distribution, no bootstrap and no reference to `Q_t`, so nothing about it requires recalibrating
when the universe size moves. `F_t`, by contrast, is defined *relative to* `λ₊(Q_t)`, which is
precisely why it cannot be compared across dates with different `Q_t`.

### 6.7 Verdict

**`λ₁/N` wins on the criteria set in advance**, without any appeal to how it looks at crises:

| Criterion | Winner |
|---|---|
| A/D non-degenerate | `lam1_share`, `signal_mass` (537 distinct values) |
| B slow-state stability | `lam1_share` (0.9958) |
| E `N_t` invariance **(decisive)** | **`lam1_share` alone** |
| F rebalance-artefact free | `lam1_share`, `signal_mass` |
| G exact normalisation | `lam1_share` |
| H non-redundant | `lam1_share` supersedes `signal_mass` / `k_above` / `f_t` |

Criterion C carried no weight in this ranking.

### 6.8 What criterion C shows (documented, not used to select)

Percentile of each statistic within the corpus, at the labelled break and 24 months later:

| Epoch | `lam1_share` @break → +24m | `f_t` @break → +24m | `sca_t` @break → +24m |
|---|---|---|---|
| gfc_2008 | 77% → **87%** | 66% → 91% | 15% → 31% |
| taper_2013 | 40% → 4% | 15% → 18% | 13% → 28% |
| ilfs_2018 | 29% → 56% | 26% → 58% | 91% → 92% |
| covid_2020 | **0% → 55%** | 9% → 58% | 19% → 90% |
| tightening_2022 | 51% → 66% | 77% → 77% | 24% → 65% |

The pattern is the trailing-window signature of §3.1, now visible in every statistic: low at the
break, higher two years on. **This is reported as a property of the estimator, not tuned away.**

---

## 7. Proposed amendment (smallest defensible)

No requirement text changes; no model changes; nothing is tuned. What changes is **which statistic
the report leads with**, and what Pillar 2 is claimed to do.

1. **`F_t` and its p-value continue to be computed and stored**, exactly as FR17 and FR19 specify.
   They are reported as specified, together with §3 and §4 as their interpretation. Neither is
   deleted, and the FR19 result is reported as passing — because it does pass.
2. **`λ₁/N` becomes Pillar 2's cross-date systemic-coupling state**, on the evidence of the §6
   comparison — not because FR19 is degenerate. It needs no new code and no new requirement: the
   engine already computes it, and `trace(C_t) = N_t` (now genuinely exact, per §2.1) makes it a
   pure variance share in [0,1] whose normalisation is free of `Q`. It is the statistic
   AMENDMENT-02 needed and did not identify.

   **Note the role distinction.** `λ₁/N` does *not* replace FR19's p-value *as a test* — they are
   different objects, and a variance share is not a hypothesis test. What it replaces is the
   **cross-date state-variable role** that AMENDMENT-02 §3.2 wrongly assigned to the p-value. FR19
   keeps its own job (§4) and is not modified, re-tuned, or re-parameterised.
3. **Pillar 2 is described as a coupling-*regime* estimator with a measured 18–36 month response
   lag**, not as an early-warning detector. Any lead-time claim for Pillar 2 against the FR32 epochs
   is **withdrawn**; on the evidence in §3.1 it would be a claim of lag, not lead.
4. **FR30 weighting must not be calibrated on Pillar 2's break-date response.** Optimising a weight
   against the labelled epochs would drive Pillar 2's contribution to zero for the mechanical reason
   in §3.1, and would misattribute a window-length property to the pillar's informativeness. Flagged
   for the C10 harness before FR30 is run.

### 7.1 Known limitations of `λ₁/N` — stated, not buried

1. **It responds with an 18–36 month lag** (§3.1). This is a property of FR16's window, not of the
   statistic, and it is the single most important caveat on any Pillar 2 claim.
2. **Its observational correlation with `N_t` is −0.566** (§6.4). The controlled experiment shows
   this is era-confounding rather than `N`-dependence (paired ratio 1.0176), but a reader who
   computes the raw correlation will see −0.566 and must be told why it is not what it looks like.
3. **It is one number from a 500-dimensional object.** It captures the market mode and deliberately
   discards sector structure; `signal_mass` retains more of that but fails criterion E.
4. **Subsample dispersion is not negligible** — ±0.012–0.014 across random subsets, against a corpus
   sd of 0.0424. Differences between two nearby dates smaller than roughly 0.01 should not be
   interpreted.
5. **It is a coupling measure, not a risk measure.** High coupling is not the same as high risk;
   the market can be tightly coupled and calm. Only the fused CSRS may be described as risk.

### 7.2 Readiness for C8/C9 integration

**One concrete blocker was found and cleared.** `λ₁/N` was not persisted anywhere: `RmtDetail` has
no field for it, `rmt_output` has no scalar column, and the existing `eigenvalues` column —
`double precision[] NOT NULL` — was being written as an **empty array**. The recommended state
variable was therefore not reachable by any consumer.

The minimal fix, applied here, writes the real spectrum (descending) into the column that already
exists, so `λ₁/N = eigenvalues[1] / array_length(eigenvalues, 1)` is exactly derivable. `v1` is now
persisted for the same reason: D3's `Ω_t` needs the previous leading eigenvector, so an empty `v1`
means the rotation signal cannot resume after a restart.

**What still stands between Pillar 2 and C8/C9**, neither of which is a C6 defect:

1. **The daily production series does not exist.** Everything here is `stride = 10` — 537 of ~5,365
   trading days. FR16 specifies a daily series, and C8's Kalman step expects one. The `stride = 1`
   run is the remaining compute job (see §7.3).
2. **OQ-A04b** — the interface question below.

**Deliberately not done:** adding a scalar `lam1_share` to `RmtDetail` and to the `rmt_output`
schema. That would be the cleaner interface for C8, but `seraph/shared_types/` is ask-gated and every
component imports from it. **This needs sign-off before C8 wiring begins** — see OQ-A04b.

### 7.3 Cost of the daily production run

The engine's docstring assumes the FR19 bootstrap cache is keyed on a configuration that "changes
only at semi-annual rebalances", giving "a few dozen distinct configurations". **Measured, that is
optimistic:** `N_t` also moves whenever a member lacks a full 1,000-day history, so it changes on
**27.8%** of `stride = 10` steps, producing **99** distinct `(T, N, reps)` configurations against 44
rebalances. The cache still earns its place — 81.6% hit rate — but it is not the near-perfect cache
the comment implies.

The cost is nonetheless **bounded**, and the bound is what makes a daily run feasible: the key is
`(1000, N_t, reps)` with `N_t ∈ [122, 499]`, so there can never be more than **378** distinct
configurations no matter how many dates are evaluated. At FR19's specified 1,000 replications that
is at most ~378,000 eigendecompositions — extrapolating from this run's measured throughput, roughly
**3–5 hours, once**, after which every date reuses the cache. Persisting the null across processes
would remove even that. This is a scheduling note, not a defect, and nothing about it argues for
reducing `reps`.

### Open questions for sign-off

**OQ-A04a.** Does the team accept Pillar 2 as a trailing regime estimator (recommended — it is what
the mathematics permits at `N = 500`), or is a second short-horizon spectral signal wanted as an
explicit SPEC addition? The latter is feasible only on a reduced cross-section (§3.4: `N = 125`,
`T = 250`) and would be a **new requirement**, not a reinterpretation of FR16. It is not proposed
here.

**OQ-A04b.** Add `lam1_share: float` to `RmtDetail` and a matching `rmt_output` column, or leave C8
to derive it from the persisted `eigenvalues` array? The first is cleaner and costs an ask-gated edit
to `shared_types/`; the second costs nothing now but puts a derivation in the consumer.

---

## 8. What was *not* changed

- **FR16's `T = 1000`, FR17's three signals, FR19's bootstrap** — untouched.
- **AMENDMENT-02's floating `N_t` / per-date `Q_t`** — untouched and still correct.
- **No model was altered to make a requirement pass.** The FR16 fix corrects arithmetic that was
  provably wrong independently of any test. `F_t` was not redefined to make it respond at breaks,
  and the FR19 null was not weakened to stop it rejecting.
- **The `stride = 10` validation run is still a validation run**, not the daily production series
  FR16 specifies.

## 9. Reproduction

```
python scripts/diagnose_rmt_findings.py --stride 10      # §3, §4
python scripts/compare_rmt_statistics.py --stride 10     # §6 candidate comparison
python scripts/run_rmt.py --stride 10 --write            # FR16 guard, E7
pytest tests/test_c6_rmt.py -v                           # 9/9 AMENDMENT-04 guards
pytest tests/contract/test_ct10_rotation_artefact.py -v  # 5/5 D3 contract
```
