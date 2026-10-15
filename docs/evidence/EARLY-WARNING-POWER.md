# What the T3 Advance-Warning Test Can and Cannot Establish

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`. Nothing committed.**
Evidence: `*-26b-early-warning-power-AAFT-FINAL.log` (authoritative) and
`*-26a-early-warning-power-SHIFT-NULL-SUPERSEDED.log` (the earlier shift-null run,
kept because §2's miscalibration findings are measured in it).
Code: `scripts/early_warning_power.py`.
Reuses `study_stress_candidates.build_features()` / `targets()` and
`seraph.validation.harness.auc` by import, so the evaluation definition cannot drift.

---

## 1. Why this had to come before another detector

Every candidate tested sits at or below chance on T3 — `semivar_20` 0.4928,
`drawdown` 0.6735, `jump_int_20` 0.5349, 2-pillar CSRS 0.3723, 3-pillar CSRS
0.4367 — and the conclusion recorded was "no advance-warning capability".

That conclusion assumes the test could have found a signal if one were present,
and **nothing had checked that assumption.** T3 marks the 15 trading days before
each FR32 break as positive: 6 × 15 = 90 positive days against ~5,100 negatives.
But those 90 days come from **six events**, and days inside one 15-day window are
nearly perfectly correlated. An AUC standard error that treats 90 positives as
independent understates the true uncertainty by roughly √15.

Two different claims were therefore being conflated:

* *"We measured no advance warning"* — true, and uninformative on its own.
* *"There is no advance warning to find"* — requires knowing the test's power.

This establishes the second, and it also re-tests the first under a null that
respects the autocorrelation.

## 2. Method

**Two nulls, because the obvious one is wrong.**

| null | what varies | what it asks |
|---|---|---|
| `shift` | all six onsets move by one common circular offset | would other onset *dates* have scored this well on this series? |
| `aaft` | onsets fixed; the series is phase-randomised and rank-remapped | would other series with the same marginal and ACF have scored this well on these dates? |

Drawing onsets **uniformly at random** — the first thing I tried — is
miscalibrated here. These features are near-random walks (`rv_t_yz` lag-1
autocorrelation 0.9973), so the AUC depends heavily on *where in the walk* the
lead windows fall, and six fixed onsets are not a uniform draw. Measured: the
δ=0 negative control rejected at **50%** instead of 5%. The circular shift fixes
this by preserving every pairwise spacing and varying only the phase.

**A second miscalibration, also measured.** With the shift null the δ=0 control
still rejected at 40%, then 17%. Cause: the synthetic AR(1) background started at
`x[0] = 0`, leaving it non-stationary for ~1/(1−φ) ≈ 370 steps, so early windows
had systematically smaller dispersion than late ones — and four of the six real
onsets sit in the back half of the grid. Initialising at the stationary variance
(`ar1_stationary`) removed the bias.

**The power curve** injects a known signal into that background: a step of `δ`
within-series sd across the 15 days before each *real* onset, 60 draws per δ.
δ=0 is the negative control and is what calibrates everything else.

## 3. The test is calibrated, and it has real power

```
 delta (sd)  mean T3 AUC      sd   mean p  POWER at alpha=0.05
        0.0       0.4915  0.1068   0.5324            8%     <- negative control
        0.5       0.6376  0.1024   0.1788           47%
        1.0       0.7680  0.0791   0.0222           85%
        1.5       0.8379  0.0758   0.0103           98%
        2.0       0.9165  0.0480   0.0052          100%
        3.0       0.9841  0.0154   0.0050          100%
        4.0       0.9985  0.0031   0.0050          100%
```

**Actual type-I error at nominal α = 0.05 is 8%** (60 draws, SE ≈ 2.8%, so within
about one standard error of nominal). Good enough to use, and the residual
inflation is accounted for below.

**Minimum detectable effect at 80% power: δ ≈ 1.0 sd** nominal, ~1.5 sd once the
type-I inflation is allowed for. **So the test is not powerless.** A clean step of
1–1.5 within-series sd confined to the 15 days before each onset would have been
found 85–98% of the time.

Residual limitation on the nominal p-values: six onsets on a 21-year grid admit
only **~10–15 effectively independent event configurations**, so a circular-shift
p-value is granular with heavy tails, and it moved between runs (drawdown's
`p_shift` 0.042 ↔ 0.060, `p_aaft` 0.020 ↔ 0.055). The conclusion below therefore
rests on the calibrated AUC distribution rather than on any single p-value.

## 4. No candidate clears the calibrated null

**T3 AUC under no signal at all** (the δ=0 distribution, 60 draws):

```
    mean 0.4915   sd 0.1077   median 0.4741   95th pct 0.6774   max 0.6911
```

| candidate | T3 AUC | shift null mean | `p_shift` | aaft null mean | `p_aaft` | ≥ 0.6774? |
|---|---|---|---|---|---|---|
| **drawdown** | **0.6735** | 0.5059 | 0.0424 | 0.5022 | 0.0547 | **no** |
| dd_accel | 0.5924 | 0.5036 | 0.0798 | 0.4923 | 0.0846 | no |
| jump_int_20 | 0.5349 | 0.5021 | 0.3641 | 0.5247 | 0.5075 | no |
| vol_of_vol | 0.5098 | 0.4921 | 0.3940 | 0.5054 | 0.4826 | no |
| semivar_20 | 0.4928 | 0.5062 | 0.5786 | 0.4926 | 0.4826 | no |
| rv_accel | 0.4229 | 0.4958 | 0.7830 | 0.5071 | 0.8259 | no |
| ar_t | 0.4036 | 0.5063 | 0.8529 | 0.5064 | 0.8209 | no |
| rv_level | 0.3722 | 0.4941 | 0.9077 | 0.5167 | 0.9453 | no |
| bas_t | 0.3356 | 0.4971 | 0.9850 | 0.4961 | 0.9453 | no |

Both nulls are centred on 0.49–0.52 for every candidate, which is the sanity
check that the lead windows carry no information at an arbitrary phase.

**`drawdown`'s 0.6735 is not significant.** It is the one number in the whole
study that looked like advance warning, and it sits *below* the 95th percentile of
the no-signal distribution (0.6774), with nominal p-values of 0.042–0.055 against
an actual 8% type-I rate, from **9 candidates screened with no multiplicity
correction**. `STRESS-PILLAR-DECISION.md` §2 already declined to claim it; this
quantifies why that was right.

## 5. What this establishes

| claim | status |
|---|---|
| No measured advance warning in any candidate | **confirmed, and now under a calibrated null** |
| A clean lead signal of ≥ 1.0–1.5 sd over 15 days is **absent** from the corpus | **established** — power 85–98% to detect one |
| A lead signal below ~0.5 sd is absent | **NOT established** — power 47%, genuinely untested |
| `drawdown` provides advance warning | **refuted** — below the no-signal 95th percentile |
| SERAPH has early-warning capability | **not claimed, and nothing here supports it** |

The useful shift is from *"we measured nothing"* to *"a strong, clean lead signal
is excluded; a weak one cannot be ruled out on six events."* That is a real
negative result with a stated boundary, and it is the honest headline for O7.

## 6. What would change it

The binding constraint is **six onsets**, not the estimator and not the feature
set. Three routes, in order of how much they would actually buy:

1. **More events.** Power scales with onsets, not days. The FR32 epoch set is six
   by construction. A broader event definition — sector-level or
   single-name stress onsets — would multiply the event count without needing new
   data, at the cost of defining a different target than FR32's. That is a
   specification question, not an engineering one, and it is the only route that
   materially changes the power.
2. **Cross-market replication** (O9/FR37–38). Independent markets give independent
   onsets. NFR20 already contemplates cross-market evaluation.
3. **A longer horizon than 15 days.** Mechanically widens the positive window, but
   the events stay at six, so it buys much less than it appears to.

Not useful: more candidate features. Nine were screened; the multiplicity cost
already exceeds what another candidate could demonstrate at this event count.

## 7. Limitations

1. The power curve's background is an AR(1) matched on **lag-1** autocorrelation
   only. Real features have longer memory, which would likely *reduce* power
   relative to these figures, making the MDE a lower bound.
2. The injected signal is a clean step. A ramp, or one that fires before only some
   onsets, would be harder, so again these are optimistic bounds.
3. 60 draws per δ gives SE ≈ 2.8% on the δ=0 rate and ~6% on a power of 85%.
4. The δ=0 null is synthetic. `aaft_null` on each real feature is the
   feature-specific equivalent and agrees (null means 0.49–0.52), but it was not
   used to recalibrate per candidate.
5. One of the six break dates is provisional (SPEC OQ3 open), so the onset set is
   itself not fully settled.
6. T1/T2 detection is untouched here. Those have 180 positive days from the same
   six events and will have their own, separate calibration problem — **not yet
   measured.** The 3-pillar CSRS's T1 improvement 0.537 → 0.674 has not been
   tested against a calibrated null and should not be treated as significant
   until it has been.

## 8. Reproduction

```bash
docker start seraph-timescaledb
python scripts/early_warning_power.py --perms 400 --draws 60 --null aaft
```

~12 min. Reads only; writes nothing.

## 9. Next step

Apply the same calibration to **T1**, the detection target, which is where the
3-pillar CSRS's headline improvement lives (0.5372 → 0.6743,
`STRESS-PILLAR-DECISION.md` §3). T1's positives come from the same six events, so
it has the same dependence problem, and that improvement is currently reported
against a nominal null. Until it is tested against a calibrated one, it is not
established either — and unlike T3, **it is a claim SERAPH currently makes.**
