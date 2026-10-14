# Does SERAPH's Detection Claim Survive a Calibrated Null?

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`. Nothing committed.**
Evidence: `*-27-t1-detection-calibration.log`, `*-28-csrs-full-span.log`,
`*-29-t1-calibration-fullspan.log`, `*-28-csrs-fullspan-{2,3}pillar.csv`.
Code: `scripts/calibrate_detection_claims.py`, `scripts/run_csrs_research.py --full-span`.

---

## 0. Summary

| claim | before | after calibration |
|---|---|---|
| 3-pillar CSRS T1 **0.5372 → 0.6743**, "measurable incremental detection value" (`STRESS-PILLAR-DECISION.md` §3) | reported as established | **NOT significant on the 2017+ span.** Both values sit inside their own nulls (no-signal 95th pct **0.7078**) because only 4 of 6 onsets are covered |
| the same comparison on a **full 2005+ span** (6 onsets) | never run — the grid was clamped by Hawkes | **0.5218 → 0.6573.** The 3-pillar value clears both nulls (p = 0.034 / 0.040, null p95 0.6449) but **does not survive multiplicity** |
| the two genuine pillars (Hawkes + RMT) detect crises | implied by "CSRS 2-pillar 0.5372" | **firmly refuted.** 0.5218, p = 0.40 / 0.41. Individually: RMT 0.4283 (p 0.79), Hawkes 0.5937 (p 0.32) |
| any candidate detects crises after full correction | 9 screened, none corrected | **`dd_accel` and `rv_accel` survive Holm across all 15 comparisons** |

The one sentence worth carrying: **SERAPH's two validated pillars do not detect
crises, individually or together.** What detection exists in the composite comes
from the slot-3 semivariance research configuration, and it is marginal.

---

## 1. Why T1 needed this

`EARLY-WARNING-POWER.md` established that T3's positives come from six events,
not ninety days, and that the nominal null is therefore wrong. T1 has exactly the
same structure — 30 positive days per break from the same six breaks — and had
never been tested the same way. The difference is that T3 was being reported as a
negative, where an optimistic null is harmless, while **T1 is reported as
SERAPH's headline positive**, where it is not.

Same two nulls as the T3 work, imported rather than copied:

* `shift` — circular shift of the whole onset set, preserving every pairwise spacing.
* `aaft` — onsets fixed, series phase-randomised with its exact marginal preserved.

Both calibrated on synthetic data in that report: actual type-I error 8% at a
nominal 5%. Permutations raised to 1,500 per null here, because Holm's tightest
threshold at 15 comparisons is 0.05/15 = 0.00333 and 200 permutations cannot
resolve below 1/201 = 0.00498 — a resolution limit that would have silently
failed every candidate for the wrong reason. The script now prints its own
resolution floor.

## 2. Full results (T1 detection, 30-day windows)

```
          series    span  ons   T1 AUC  shiftmu  p_shift   aaftmu   p_aaft  null p95   verdict
        rv_level 2005+    6   0.6098   0.4995   0.1119   0.4975   0.1013    0.6445   not sig
        rv_accel 2005+    6   0.7706   0.4993   0.0020   0.4978   0.0007    0.6197       SIG
      semivar_20 2005+    6   0.7832   0.4989   0.0060   0.4944   0.0013    0.6457       SIG
     jump_int_20 2005+    6   0.7515   0.5009   0.0053   0.4979   0.0007    0.6409       SIG
        drawdown 2005+    6   0.7185   0.5007   0.0207   0.4999   0.0067    0.6512       SIG
        dd_accel 2005+    6   0.7064   0.5000   0.0007   0.5000   0.0007    0.5799       SIG
      vol_of_vol 2005+    6   0.7278   0.5006   0.0120   0.4970   0.0033    0.6432       SIG
            ar_t 2005+    6   0.4453   0.4957   0.6935   0.4989   0.7109    0.6612   not sig
           bas_t 2005+    6   0.3799   0.5003   0.9114   0.4950   0.8901    0.6548   not sig
      rmt lam1/N 2005+    6   0.4283   0.5012   0.7948   0.5020   0.7981    0.6346   not sig
        hawkes n 2017+    4   0.5937   0.5109   0.3157   0.4986   0.1925    0.8038   not sig
   CSRS 2-pillar 2017+    4   0.5372   0.4901   0.4265   0.5008   0.3698    0.7432   not sig
   CSRS 3-pillar 2017+    4   0.6743   0.4825   0.1201   0.4978   0.0533    0.7078   not sig
CSRS 2p fullspan 2005+    6   0.5218   0.5012   0.4011   0.5028   0.4137    0.6355   not sig
CSRS 3p fullspan 2005+    6   0.6573   0.4984   0.0340   0.5005   0.0400    0.6449       SIG
```

Every null mean lands on 0.48–0.51, which is the sanity check that the crisis
windows carry no information at an arbitrary phase.

**Both nulls widen sharply with fewer onsets.** The no-signal 95th percentile is
**0.63–0.65 at six onsets** and **0.71–0.80 at four**. That single fact is why the
2017+ CSRS comparison was undecidable: 0.6743 is a perfectly respectable AUC that
a no-signal series beats 12% of the time on four events.

### Holm correction across all 15 comparisons

```
   1.    dd_accel  p=0.0007  threshold=0.00333  survives
   2.    rv_accel  p=0.0020  threshold=0.00357  survives
   3. jump_int_20  p=0.0053  threshold=0.00385  does NOT survive
```

Holm is step-down, so everything below rank 3 falls with it. **`dd_accel` and
`rv_accel` are the only series that survive.** Both are *acceleration* measures —
the rate of change of drawdown and of realised volatility — not levels. `rv_level`
(0.6098) is not significant even uncorrected. That the two survivors are both
second-difference quantities is the most interesting substantive result here, and
it is consistent across two independent nulls.

## 3. Extending the CSRS span — what it changed and what it cost

The CSRS was clamped to 2017-02-09+ because the decision grid was built from the
Hawkes refit span (473 refits), even though Pillar 2 runs from 2005-01-03 (5,363
rows) and **1,889 of the 2,357 existing ticks already have Hawkes masked off**.

`--full-span` runs the whole Pillar 2 history and lets Hawkes be a structural
absence before its first refit. This is not a workaround — AGENTS.md §5 states it
directly: *"a structurally-missing Hawkes score pre-2015 is expected, not a
failure"*. The per-tick loop already emitted exactly that when no refit preceded
the decision timestamp, so **only the grid definition changed**; no emission, mask,
weight or threshold logic was touched. Result: 5,363 ticks, 0 failures, masks
`{(F,T,F), (T,T,F)}` and `{(F,T,T), (T,T,T)}` as expected.

**It is not persisted, and `--write --full-span` is refused.** `weights_artefact_id`
is part of the `csrs` primary key and nothing in `CalibrationConfig` encodes the
span, so a full-span run hashes to the **same id** as the 2017+ run. Its
overlapping rows would overwrite them — and the values genuinely differ, because
`KalmanReconciler` is recursive and a 2017 tick reached after twelve years of
updates is not the same tick reached from a cold start. That would have destroyed
evidence rather than deduplicating it. The driver now refuses the combination and
prints that reason; `--dump` writes a CSV instead.

Persisting a full-span CSRS therefore needs a **deliberate decision about artefact
identity** — either a new `CalibrationConfig` field, or a convention that the span
is part of the artefact. That is a `seraph/shared_types/` change and is **not
made here.** Stated for sign-off, not performed.

## 4. What this establishes and what it refutes

| | status |
|---|---|
| Hawkes + RMT, the two pillars with validated production output, detect crises | **REFUTED.** 2-pillar CSRS 0.5218 (p 0.40/0.41) on 6 onsets; RMT alone 0.4283 (p 0.79); Hawkes alone 0.5937 (p 0.32) |
| The 3-pillar CSRS detects crises | **marginal.** Clears both nulls at 6 onsets (p 0.034/0.040) but fails Holm. Not established |
| The reported 0.5372 → 0.6743 improvement | **not a detection result** on its own span — both values sit inside their nulls |
| `dd_accel`, `rv_accel` detect crises | **ESTABLISHED** under two nulls with full multiplicity correction |
| Any of this is advance warning | **NO.** T3 remains null — see `EARLY-WARNING-POWER.md` |

### Three caveats that travel with the positive results

1. **T1 is partly tautological** for volatility-derived signals. FR32 crisis
   windows *are* high-volatility windows by construction (mean `rv_t_yz` 0.6109
   inside vs 0.4979 outside, `STRESS-PILLAR-DECISION.md` §1). A T1 pass is
   therefore not independent evidence of *systemic-risk* detection. `dd_accel`
   and `rv_accel` are less exposed to this than levels are, but not immune.
2. **The composite still loses badly to its best single input.** `semivar_20`
   alone is 0.7832 against the 3-pillar composite's 0.6573. Equal weights dilute
   the strongest signal with RMT (0.4283, below chance) and a Hawkes input masked
   off on 1,889 of 5,363 ticks. This remains the strongest argument for FR30 —
   and D5(c) still forbids selecting a winner from the ablation.
3. **Six onsets, one provisional** (SPEC OQ3 open). The nulls are correctly wide
   because the event count is small; that is a property of the problem, not of the
   method.

## 5. Reproduction

```bash
docker start seraph-timescaledb
python scripts/run_csrs_research.py --full-span \
    --dump docs/evidence/csrs-fullspan-2pillar.csv
python scripts/run_csrs_research.py --full-span --stress-slot \
    --dump docs/evidence/csrs-fullspan-3pillar.csv
python scripts/calibrate_detection_claims.py --perms 1500 \
    --csv "CSRS 2p fullspan=docs/evidence/csrs-fullspan-2pillar.csv" \
    --csv "CSRS 3p fullspan=docs/evidence/csrs-fullspan-3pillar.csv"
```

~15 min total. Writes nothing to the database.

## 6. Corrections to `STRESS-PILLAR-DECISION.md`

§3's measured result table and its conclusion need qualifying:

| claim | status |
|---|---|
| "AUC +0.137, precision 3.1×, recall 3.7×. That is the measurable incremental detection value the mandate asked for." | **Not established as reported.** On the 2017+ span both configurations sit inside their nulls. On a 6-onset span the 3-pillar value does clear its null at nominal 5% but fails Holm across 15 comparisons. |
| §6 "Contemporaneous detection **IMPROVED and measured** (0.537 → 0.674)" | **Downgrade to NOT YET VALIDATED.** The direction holds; the significance does not. |
| §2's refusal to claim `drawdown`'s T3 0.6735 | **Correct, and now quantified** — below the no-signal 95th percentile (`EARLY-WARNING-POWER.md` §4) |
| §1's correction of `rv_level` to 0.6098 | **Confirmed**, and `rv_level` is additionally **not significant** (p 0.11/0.10) |
| §3's decision not to add a fourth pillar | **Unchanged and still correct** |

## 7. Next step

**Run the FR30/FR35 descriptive ablation on the full-span series**, which is now
possible for the Hawkes-free subsets: Table B's `(rmt)` subset is estimable over 6
epochs rather than 4, and the per-fold spread — which D5(c) requires to be
reported for all 14 configurations — can finally be computed against nulls of the
right width. Hamilton-containing subsets remain blocked (`HAMILTON-REGIME-SUPPORT.md`
§6), so the ablation will be partial, and D5(c) still forbids selecting a headline
winner from it.
