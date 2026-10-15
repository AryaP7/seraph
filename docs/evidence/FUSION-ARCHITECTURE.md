# Learned fusion architecture — comparison, and the recommendation

**Recommendation: retain the equal-weight composite (candidate A). Do not learn
the pillar weights from six events** — their 90% bootstrap intervals span almost
the whole simplex (mean width **0.983** on a [0,1] scale at the measured
770-session dependence scale), so a "learned weight" here is not an estimate of
anything. Not as a fallback, and not because
"nothing worked" — for a reason the experiment establishes positively: equal
weighting is the minimum-variance convex combination when no input is known to
be more informative than another, and every learned candidate moved off it only
to fit noise. Where the learned weights moved furthest, the result got *worse*
than the baseline they were meant to improve.

**All four pre-registered hypotheses were confirmed**, as was H5 in the D′
addendum — which rules out the one mechanical explanation that remained.
Pre-registration:
`docs/evidence/FUSION-PREREGISTRATION.md`, sha256
`3d8e8de372e328444d9711fcb531c41deb8e91bac17100c0d19ff295abb4848d`, written and
hashed **before the first fit**.

**Verdict summary — every pre-registered hypothesis held:**

| hypothesis | prediction | verdict |
|---|---|---|
| **H1** | learned convex weights do not beat the best single pillar out of sample | **CONFIRMED** |
| **H2** | learned weights are unstable across chronological folds (L1 span > 0.33) | **CONFIRMED** (1.700 / 1.900 of a 2.0 maximum) |
| **H3** | escalation raises warned rate but its false-alarm cost leaves it indistinguishable from null | **CONFIRMED** — it did not even raise the warned rate (0/3), and breached the budget |
| **H4** | no candidate beats the no-skill benchmark on the untouched confirmation period | **CONFIRMED** (best p = 0.2164) |
| **H5** (addendum) | D′ on a resolving scale still does not beat its no-skill rate | **CONFIRMED** (0 of 5) |

Settled 2026-10-14 on git `f3eaac8`, working tree uncommitted. Database
read-only; nothing in `seraph/` was modified.

| artefact | path |
|---|---|
| experiment | `scripts/fusion_architecture_search.py` |
| pre-registration | `docs/evidence/FUSION-PREREGISTRATION.md` |
| results (λ₁/N) | `docs/evidence/fusion/fusion_search_lam1_b2.json` |
| results (FR18 `SCA_t`) | `docs/evidence/fusion/fusion_search_sca_b2.json` |
| logs | `*-81` … `*-92` |
| test status | **Full suite completed 2026-10-14: 220 passed, 1 failed, 2 xfailed (223 total)**, run in three exhaustive chunks after two single-process attempts were stopped on low system memory; totals reconcile against the collection count exactly. `*-100-suite-COMPLETE-chunked.log`. The failure is the preserved CT-3. |

```
python scripts/fusion_architecture_search.py --budget 2.0                # primary
python scripts/fusion_architecture_search.py --budget 2.0 --pillar2 sca  # FR18 input
```

---

## 1. The harness is faithful — asserted, not assumed

Every candidate operates on the **reconciled state**, which is where C9 actually
sits (`pillar → FR28 ECDF → C8 Kalman → C9 fuse`). Comparing a proposed fusion
rule against the baseline at a different point in the pipeline would be
meaningless.

That yields a free correctness check, and it is asserted in code: candidate A
(equal weights, D2-masked and renormalised) must reproduce the shipped
`CSRS[hawkes+rmt+hamilton]` series exactly.

**Measured: `max|Δ| = 2.220e-16` over 5,363 days — machine precision.** If this
check ever fails the script says so and declares its own output meaningless.

Coverage, reported because it bounds every claim below: `rmt` 5,363 days,
`hamilton` 3,365, `hawkes` **468**. **All three pillars are simultaneously
available on 468 days.** A fold without Hawkes is not a three-pillar evaluation
and is not described as one.

---

## 2. H2 — the learned weights are not merely unstable, they are arbitrary

Candidate B grid-searches the simplex (step 0.05, 231 points) for maximum
training AUC. Per development fold, trained strictly on data before the test
epoch:

### Pillar 2 = `λ₁/N` (shipped input)

| fold / test epoch | train days | train positives | w_hawkes | w_rmt | w_ham | best train AUC |
|---|---|---|---|---|---|---|
| gfc_2008 | 910 | 0 | — | — | — | **untrainable** |
| taper_2013 | 2,041 | 15 (1 event) | 0.00 | 0.15 | **0.85** | 0.6585 |
| ilfs_2018 | 3,330 | 30 (2 events) | **0.65** | 0.05 | 0.30 | 0.5032 |
| covid_2020 | 3,647 | 45 (3 events) | 0.10 | **0.90** | 0.00 | 0.4905 |

### Pillar 2 = `SCA_t` (FR18 input)

| fold | w_hawkes | w_rmt | w_ham | best train AUC |
|---|---|---|---|---|
| taper_2013 | 0.00 | **1.00** | 0.00 | 0.4780 |
| ilfs_2018 | **0.95** | 0.05 | 0.00 | 0.4966 |
| covid_2020 | 0.00 | **1.00** | 0.00 | 0.5810 |

**H2 CONFIRMED. Maximum pairwise L1 distance across folds: 1.700 (λ₁/N) and
1.900 (`SCA_t`), against a pre-registered instability threshold of 0.33.** The maximum possible
distance on the simplex is 2.0. **Each fold crowns a different pillar**, and the
weights land on or near simplex *corners* — single-pillar solutions.

The decisive detail is the training-AUC column. On `λ₁/N` it goes **0.6585 →
0.5032 → 0.4905** as events are added. With one event you can find weights
scoring 0.66 in sample; with three the best achievable falls *below chance*.
**That is the signature of fitting noise.** A real relationship would firm up
with more data, not dissolve.

Grid search rather than a gradient method was chosen deliberately: it is
deterministic, adds no hyperparameters of its own, and the whole surface is
inspectable — so instability becomes visible instead of hiding behind a single
converged answer.

### Uncertainty on the weights — they carry essentially no information

Fold-to-fold instability shows the weights *move*. It does not say how little
any single one is pinned down. `scripts/fusion_weight_uncertainty.py`
(`*-92-fusion-weight-uncertainty.log`) answers that with a **moving-block
bootstrap** on the widest development training period (4,081 days, 60 positives,
4 events), refitting the same simplex grid search on each replicate.

Blocks rather than days deliberately: Workstream B measured the integral
timescale of the pillar features at **770 sessions**, so resampling individual
days would treat ~5,000 dependent observations as independent and manufacture
tight intervals. Several lengths are reported so the dependence assumption is
visible.

90% intervals for each learned weight, 150 replicates per length:

| block L | hawkes | rmt | hamilton | mean interval width |
|---|---|---|---|---|
| 21 | [0.000, 1.000] | [0.000, 0.900] | [0.000, 1.000] | 0.967 |
| 63 | [0.000, 1.000] | [0.000, 0.900] | [0.000, 0.850] | 0.917 |
| 252 | [0.000, 1.000] | [0.000, 1.000] | [0.000, 1.000] | 1.000 |
| **770** (measured scale) | [0.000, 1.000] | [0.000, 1.000] | [0.000, 0.950] | **0.983** |

**The weights are constrained to [0,1] and sum to 1, and their 90% intervals
span almost that entire range.** Mean width 0.92–1.00. A learned weight here is
**not an estimate of anything**, and reporting one to two decimal places in a
production artefact would be false precision.

Two details that make this stronger than a conservative-assumption artefact:

* **Even at L = 21** — which grossly understates the measured dependence — the
  intervals are already near-maximal. The weights are unidentified under *any*
  dependence assumption, not merely under the cautious one.
* **At L = 770, 21% of replicates put more than 0.95 of the weight on a single
  pillar.** A fifth of the time the grid search discards fusion altogether and
  returns a single-pillar rule.

The point estimate on this widest window is (hawkes 0.150, rmt 0.100, hamilton
0.750) at a training AUC of **0.3771** — *below chance*. The best weights
obtainable from four events score worse than a coin on the data they were fitted
to.

---

## 3. H1 — learned fusion does not beat its own inputs

Development epochs, false-alarm budget **2 episodes/year** (primary, fixed in
advance). A and E thresholds fitted on all data before 2022-01-05; **B, C and D
have weights *and* threshold refitted per fold** on that fold's own training
period, with the test epoch never seen.

| candidate | warned | FA/yr | median lead | % days alerting |
|---|---|---|---|---|
| **A: equal weight** | **0/4** | 1.44 | — | 1.9% |
| B: convex, shrink 0 | 0/3 | 1.16 | — | 1.6% |
| B: convex, shrink 0.25 | 0/3 | 1.08 | — | 1.5% |
| B: convex, shrink 0.5 | 0/3 | 1.08 | — | 1.5% |
| B: convex, shrink 0.75 | 0/3 | 1.08 | — | 1.5% |
| C: L2 logistic | 0/1 | 1.81 | — | 24.9% |
| D: composite + escalation | 0/3 | **3.13** | — | 5.1% |
| E: pillar hawkes | untestable | — | — | — |
| E: pillar rmt | 0/4 | 1.71 | — | 2.1% |
| E: pillar hamilton | 0/3 | 1.57 | — | 6.7% |
| E: semivar_20 | 0/4 | 2.18 | — | 13.5% |
| E: rv_20 | 0/4 | 1.85 | — | 12.1% |
| **E: drawdown** | **1/4** | 1.11 | 6 | **38.2%** |
| E: rv_accel_5 | 0/4 | 2.08 | — | 3.0% |
| E: dd_accel_5 | 0/4 | 2.08 | — | 1.7% |
| E: india_vix | 0/2 | 2.69 | — | 10.8% |

**Best learned candidate: 0 warnings. Best single input: 1. Baseline A: 0.**
H1 confirmed.

`E:pillar_hawkes` is `untestable` rather than 0, for the reason established in
`CRISIS-REPLAY.md` §6a: at `refit_every = 5` sessions it has **0 assessable days
of 468** under any trailing-window threshold.

### Relocation null — nothing survives

Each candidate against a common-offset circular relocation of the onsets
(measured type-I 8% at nominal 5%), 1,500 draws:

| candidate | warned | rate | null rate | p |
|---|---|---|---|---|
| A: equal weight | 0/4 | 0.00 | 0.07 ± 0.12 | 1.0000 |
| E: drawdown | 1/4 | 0.25 | 0.05 ± 0.11 | **0.1785** |
| E: pillar_rmt | 0/4 | 0.00 | 0.09 ± 0.13 | 1.0000 |
| E: pillar_hamilton | 0/3 | 0.00 | 0.11 ± 0.19 | 1.0000 |
| E: semivar_20 | 0/4 | 0.00 | 0.12 ± 0.16 | 1.0000 |
| E: india_vix | 0/2 | 0.00 | 0.21 ± 0.28 | 1.0000 |

**Holm over 9 comparisons: no survivors.** `drawdown`'s 1/4 — the only non-zero
cell in the entire development table — reaches p = 0.1785, and it achieves that
while alerting on **38.2% of days**.

---

## 4. A blind spot in my own false-alarm budget, reported not retro-fixed

`E:drawdown` respects a 2 FA/yr *episode* budget while alerting on 38.2% of all
days. Both are true because **a standing alert is one episode however long it
lasts** — few rising edges, enormous duration.

An episode budget alone therefore does not bound operational burden, and the
pre-registered budget has that gap. It is **reported rather than silently
replaced**: changing the budget after seeing which candidate it admits is
exactly the move §9 of the pre-registration lists as a failure of integrity. A
future pre-registration should bound *both* episode rate and time-under-alert.
`% days alerting` is printed for every candidate so the gap is visible wherever
these numbers are read.

---

## 4b. The result does not depend on the budget

The pre-registration fixed 2 FA/yr as primary and 0.5, 1 and 4 as sensitivity.
Development warned counts at every level:

| candidate | 0.5 FA/yr | 1 FA/yr | **2 FA/yr** | 4 FA/yr |
|---|---|---|---|---|
| A: equal weight | 0/4 | 0/4 | **0/4** | 0/4 |
| B: convex, shrink 0 | 0/3 | 0/3 | **0/3** | 0/3 |
| B: convex, shrink 0.75 | 0/3 | 0/3 | **0/3** | 0/3 |
| D: composite + escalation | 0/3 | 0/3 | **0/3** | 0/3 |
| E: drawdown | 0/4 | 0/4 | **1/4** | 1/4 |

**No fusion candidate warned before a single development crisis at any
false-alarm budget from 0.5 to 4 episodes per year.** The only non-zero cell
anywhere remains `drawdown`, at 38.2% of days under alert.

### Escalation overshoots its budget at every level

D's realised false-alarm rate against its nominal budget:

| nominal budget | 0.5 | 1.0 | 2.0 | 4.0 |
|---|---|---|---|---|
| D realised FA/yr | **0.56** | **1.86** | **3.13** | **6.11** |
| A realised FA/yr | 0.32 | 0.69 | 1.44 | 3.01 |

D exceeds its nominal budget by roughly 1.5× consistently, while A lands under
it. This is a general property of OR-rules worth recording: **splitting a
false-alarm budget across arms does not bound the union**, because episodes from
different arms interleave and the realised rate out of sample is not the sum of
the fitted per-arm rates. Any future escalation design needs its budget enforced
on the *combined* rule, not arm by arm.

---

## 5. H3 — escalation degenerates, and the reason is the rank scale

Candidate D (composite ≥ θ_c **OR** any pillar ≥ θ_p, budget split across arms)
was the one candidate that could have broken the averaging bound, because it is
not an average. **H3 CONFIRMED:** it warned **0/3 on development while
breaching the budget at 3.13 FA/yr** — it bought false alarms without buying a
warning.

The fitted thresholds show why, and this is the useful part:

| fold | composite θ_c | pillar θ_p (hawkes, rmt, ham) |
|---|---|---|
| taper_2013 | **0.999999** | —, **1.0**, 0.956 |
| ilfs_2018 | **0.999999** | 0.716, **1.0**, **1.0** |
| covid_2020 | **0.999999** | 0.719, **1.0**, **1.0** |

Holding a rank-scale score to 2 FA/yr requires a threshold above the 99.9th
percentile — and **a rank has nothing above 1.0**. So the arms saturate and the
"escalation" degenerates to whichever single arm still has a non-degenerate
threshold. D was not tested as designed; it could not be, on this scale.

**This is the same root cause as `CRISIS-REPLAY.md`'s gate 1** (C9's absolute
alert thresholds applied to an ECDF-rank composite), surfacing in a new place.
It is a second, independent argument for fixing the alert scale: not only is
60%-of-days amber uninterpretable, the rank scale also makes a two-threshold
escalation rule unfittable at any sane false-alarm budget.

A fair test of escalation therefore required a scale with upper-tail
resolution. **That test was then run, and it changes the reading of this
section** — see §5b.

---

## 5b. D′ — escalation on a scale that resolves, and it still fails

Registered in `FUSION-PREREGISTRATION-ADDENDUM-D2.md` (sha256
`26910c6a202f2ca0c073295a3b81ad264724d2dce8d7b3bb5f68b907183793cf`), written and
hashed **after D's failure was diagnosed but before D′ was run**. D′ is a
follow-up to a diagnosed *mechanical* failure and is reported **outside** the
pre-registered A–E comparison, as that addendum requires.

**The single change:** the escalation arm fires on a pillar's **raw** quantity
(λ₁/N, Hawkes `n/(1−n)`, Hamilton `LSD_t`) against its own causal trailing
quantile, instead of on the bounded FR28 rank. Raw values are unbounded above,
so the upper tail has resolution a rank does not. The budget is also enforced on
the **combined** rule rather than split across arms, fixing D's overshoot.

**Hypothesis H5:** D′ does not beat its own no-skill rate at 2 FA/yr.

| epoch | set | warned | fitted quantile | FA/yr | % days |
|---|---|---|---|---|---|
| taper_2013 | DEV | 0 | 0.9490 | 3.95 | 40.5% |
| ilfs_2018 | DEV | 0 | 0.9620 | 2.14 | 14.3% |
| covid_2020 | DEV | 0 | 0.9695 | 2.14 | 14.0% |
| tightening_2022 | CONFIRM | 0 | 0.9745 | 2.00 | 5.3% |
| tariff_2026 | CONFIRM | 0 | 0.9795 | 1.90 | 5.6% |

**D′ warned 0 of 5 — every testable development epoch and both confirmation
epochs. H5 confirmed** (P(≥0) = 1.0000 trivially; the warned count is zero).

### What this settles, and it is the most important result in this document

**The mechanical fix worked.** The fitted quantiles are 0.9490–0.9795, not
saturated at 1.0, and the thresholds are non-degenerate. So D′ genuinely tested
the escalation *design* where D could not.

**And the design still produced nothing.** Therefore **the rank-scale saturation
was not what stood between SERAPH and advance warning.** The evidential
blocker — the inputs carry no pre-onset information — is the whole story, and
§5's suggestion that escalation might work on a resolving scale is **withdrawn**.

This matters for prioritisation. The alert-scale fix is still worth doing, for
interpretability and because 60%-of-days amber is indefensible operationally
(`CRISIS-REPLAY.md` gate 1) — but it must **not** be sold as a route to advance
warning. It is not one, and D′ is the direct evidence.

One honest detail: on the `taper_2013` fold the budget search descended the
entire quantile ladder and still realised 3.95 FA/yr at 40.5% of days under
alert, i.e. that fold's rule breached the budget even at its loosest admissible
setting. Two of five folds land above 2.0 FA/yr. D′ is thus not merely
unsuccessful; on the earliest folds it is not even budget-feasible.

---

## 6. H4 — the untouched confirmation period

Per pre-registration rule 4, **no candidate cleared the development selection
bar, so baseline A was retained and nothing was selected on a point estimate.**
Confirmation was then evaluated **once**.

| candidate | warned | FA/yr | lead | p (binomial vs own no-skill rate) |
|---|---|---|---|---|
| A: equal weight | 0/2 | 1.44 | — | 1.0000 |
| B: convex shrink 0.75 | 0/2 | 1.67 | — | 1.0000 |
| **D: composite + escalation** | **1/2** | 2.05 | **14** | **0.2164** |
| E: pillar_rmt | 0/2 | 1.71 | — | 1.0000 |
| E: pillar_hamilton | 0/2 | 1.57 | — | 1.0000 |
| E: drawdown | 0/2 | 1.11 | — | 1.0000 |
| E: semivar_20 | 0/2 | 2.18 | — | 1.0000 |
| **E: dd_accel_5** | **1/2** | 2.08 | **12** | **0.2198** |

**H4 confirmed: no candidate beat its own no-skill rate.**

The two 1-of-2 cells need care, because this is where a misleading success would
be claimed:

* **D warned on `tightening_2022` at a 14-day lead — the clean, non-provisional
  epoch.** But D scored **0/3 on development**. A rule that misses three of
  three development events and hits one of two confirmation events has no
  coherent claim to skill.
* At D's own 2.05 FA/yr, the per-event chance of a pre-onset episode is 0.1148,
  so **P(≥1 of 2) = 0.2164** by chance alone.
* With two confirmation epochs the test is coarse by construction: **even 2-of-2
  reaches only p ≈ 0.013**, and 1-of-2 cannot reach 0.05 for any candidate here.
  That is a stated limitation of the pre-registered split, not a discovery.

---

## 7. The FR18 input changes the baseline, not the conclusion

Re-running everything with `SCA_t` (SPEC FR18's specified Pillar 2 quantity)
instead of `λ₁/N`:

| | λ₁/N | `SCA_t` |
|---|---|---|
| **A: equal weight (development)** | 0/4 | **1/4, lead 15, 1.57 FA/yr, 0.8% days** |
| B: convex (all shrinkages) | 0/3 | **0/3** |
| A's relocation-null p | 1.0000 | **0.2498** |
| A (confirmation) | 0/2 | 0/2 |

**The spec-compliant input improves the *equal-weight baseline* from 0/4 to 1/4,
while learned weighting stays at 0/3 and gets relatively worse.** Under
`SCA_t` the learned weights go to pure simplex corners — (0,1,0), (0.95,0.05,0),
(0,1,0) — discarding averaging altogether, and lose the one warning the baseline
had.

That is the clearest statement of the whole result: **when there is nothing to
learn, learning the weights destroys the variance reduction that equal weighting
provides.** A's 1/4 is still not significant (p = 0.2498) and still 0/2 on
confirmation, so this is not an advance-warning claim — it is an argument about
*which* fusion rule to keep.

---

## 8. Candidate C — the regulariser agrees there is no signal

L2 logistic on the three reconciled pillar scores, `C` chosen by **inner**
chronological CV on training data only:

| input | train days | chosen C | intercept | hawkes | rmt | hamilton |
|---|---|---|---|---|---|---|
| λ₁/N | 3,647 | 1.0 | −2.682 | **−1.025** | **−0.231** | **−2.443** |
| `SCA_t` | 3,647 | **0.01** | −4.340 | −0.036 | +0.034 | −0.083 |

Two readings, both informative:

1. **All three loadings are negative on `λ₁/N`.** The model learns that a
   *higher* pillar score implies a *lower* pre-onset probability — consistent
   with the measured negative pre-onset separations (hawkes +0.06σ, rmt −0.29σ,
   hamilton −0.18σ). An unconstrained learner handed these inputs does not
   discover a risk signal; it discovers that the pillars are mildly
   *anti*-correlated with imminent crises.
2. **On `SCA_t`, inner CV selects the strongest available regularisation
   (C = 0.01) and the coefficients collapse to ≈0.** The model's own
   cross-validated answer is "predict the base rate" — the regulariser
   concluding there is nothing to fit. That is the correct behaviour and it is
   evidence, not a failure to converge.

C is also `0/1` testable: only one development fold has ≥10 training positives.
**Three pillar coefficients cannot be estimated from one usable fold**, which is
the sample-size blocker in its most concrete form.

---

## 9. Why this is a data blocker, not a fusion-design blocker

Stated as arithmetic rather than as a conclusion about effort.

Every available input's measured pre-onset (T3) AUC lies between **0.38 and
0.59** (`CRISIS-REPLAY.md` §5c, `*-73`). A convex combination of inputs that are
individually uninformative is uninformative — candidate B is *bounded above* by
roughly its best input, and that bound was confirmed rather than assumed.

The two designs that could have escaped the bound both failed for identifiable
reasons:

* **C** (unconstrained signs) could exploit negative loadings, and did find
  them — but with 1 usable fold and 3 coefficients it cannot be estimated, and
  where it can be cross-validated the regulariser zeroes it.
* **D** (no averaging) could preserve a single-pillar spike, but **cannot be
  fitted on a rank scale** at any defensible false-alarm budget.

And the sample ceiling is independently measured: Workstream B's integral
timescale of **770 sessions** gives **N_eff ≈ 5** for six nominal onsets, so
there are roughly five effectively independent events from which to estimate
three weights plus a threshold.

---

## 10. Two corrections to my own work during this experiment

Recorded because both produced wrong output before being caught.

1. **Learned candidates initially reported `untestable` on every fold.** The
   first implementation stitched each fold's out-of-sample segment into one
   series and then fitted the threshold on that series — which is all-NaN over
   the training region, so no threshold existed. Corrected to proper
   rolling-origin: weights *and* threshold refitted per fold on that fold's own
   training data. `*-82` carries the broken run and is preserved.
2. **The H4 verdict logic tested the wrong hypothesis.** It checked
   `total warnings > 0` and printed "H4 REJECTED — something warned". H4 as
   pre-registered says "significantly above the no-skill benchmark". Replaced
   with a binomial test against each candidate's own alert rate, which flips the
   verdict to **CONFIRMED**. `*-85` carries the wrong verdict and is preserved.

---

## 11. What this establishes, and what it does not

**Established.**
1. **No learned fusion architecture achieves causal out-of-sample advance
   warning** at 2 FA/yr, under either Pillar 2 quantity, on either development
   or the untouched confirmation period.
2. **Learned weights are arbitrary at this sample size**, by two independent
   measures: fold-to-fold L1 span **1.7–1.9** of a simplex maximum of 2.0, each
   fold crowning a different pillar; and 90% block-bootstrap intervals of **mean
   width 0.983** on a [0,1] scale, near-maximal at *every* block length tested.
   Best in-sample AUC also *falls* toward chance as events are added
   (0.6585 → 0.5032 → 0.4905), and on the widest window the best weights score
   **0.3771 in sample** — below chance.
3. **Equal weighting is the right production choice**, and positively so:
   learned weights move off it only to fit noise, and under the spec-compliant
   input they lose the baseline's only warning. **FR30's joint weight
   optimisation, run on six events, should be expected to make things worse** —
   which is a concrete prediction this evidence supports.
4. **The rank scale blocks a fair test of escalation**, independently of
   whether escalation would help.
5. The sample ceiling is N_eff ≈ 5 independent events for 3 weights + 1
   threshold.

**Not established, and not claimed.**
* That no fusion architecture could ever work. What is shown is that **no
  weighting of *these inputs* works**, because the inputs carry no pre-onset
  information. Fusion is downstream of that.
* That `SCA_t` gives advance warning. Its equal-weight 1/4 is p = 0.2498 and
  0/2 on confirmation.
* Any calibrated probability. Candidate C's output is a fitted logistic score on
  5 effective events and is **not** presented as a probability; the CSRS remains
  a rank-like score (Brier skill score −11.64, `CRISIS-REPLAY.md` §5).
* That candidate D works. Its 1/2 on confirmation follows 0/3 on development at
  p = 0.2164.

**Pillar identity unchanged.** P1 Hawkes, P2 RMT, P3 Hamilton remain the three
pillars in `PILLAR_ORDER`. No pillar was removed, renamed or replaced; no
baseline was promoted into a pillar slot; no fourth pillar was added.

---

## 12. The next experiment that would actually resolve this

Not more fusion search, and — after D′ — **not the alert scale either**, as far
as advance warning is concerned. In priority order:

1. **Find inputs with pre-onset content.** This is now unambiguously the binding
   constraint. Every architecture tested fails for the same reason, and D′ ruled
   out the one remaining mechanical explanation. No fusion rule can manufacture
   information none of its inputs contains. Concretely: the pillars measure
   *contemporaneous* contagion, coupling and regime state, and nothing in the
   evidence suggests any of the three leads an onset. A credible next input
   would have to be forward-looking by construction — option-implied, flow-based,
   or cross-market — rather than another transform of realised prices.
2. **Shorten Hawkes's refit cadence for evaluation** (`CRISIS-REPLAY.md`
   gate 2). Pillar 1 is currently *untestable* for the primary objective, which
   is worse than a negative result and is fixable at the cost of compute alone.
   It is second because it converts an `UNTESTABLE` into a result, not because
   it is likely to be positive.
3. **Fix the alert scale** (gate 1) — still worth doing, but **for
   interpretability, not for warning.** An amber light on 57–62% of days makes
   every operational statistic in `CRISIS-REPLAY.md` §5 unreadable. D′ is the
   evidence that it is not a route to advance warning, so it must not be
   proposed as one.
4. **FR18 conformance** (gate 4). A specification-conformance fix worth ~1σ of
   contemporaneous separation with the correct sign, and it improves the
   equal-weight baseline from 0/4 to 1/4 on development. Not significant
   (p = 0.2498) and 0/2 on confirmation, so again: conformance and detection,
   not warning.

**Not recommended:** more events. Workstream B measured that nine additional
defensible episodes buy roughly **one** effectively independent event, and the
decisive threshold (N = 20) is unreachable.
