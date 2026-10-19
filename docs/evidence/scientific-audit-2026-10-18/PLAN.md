# Scientific audit protocol — 2026-10-18

This is retrospective, hypothesis-generating research requested by the owner.
The existing v1_verified results and their failures were inspected before this
plan. This is NOT historical preregistration or an untouched holdout.

Preserve Hawkes, RMT and Hamilton, existing results, and all working-tree edits.
Write audit evidence separately. Do not change production models or shared types.
Do not access or mutate the original database. Use the frozen local snapshot.

## Questions fixed before the new calculations

1. Recompute existing scores, coverage, event hits, probability calibration,
   feature redundancy, fit quality, and data provenance.
2. Compare against a genuinely causal expanding event-frequency forecast;
   report rare-event average precision as well as AUROC/Brier/log loss.
3. Test mathematical counterexamples: CSRS linear calibration, unbounded
   historical lead-time credit, Hamilton geometric half-life approximation,
   and nonmonotonic MP exceedance under rising common correlation.
4. Check the original and experimental implementation boundaries and run the
   existing relevant tests plus the invariant checker. Tests establish software
   behavior, not predictive validity.

## Limited forecast sensitivity experiment

Keep both existing targets unchanged (loss10_15 and onset15), including the
explicitly unresolved tariff label for replication only. Report a sensitivity
excluding that label from assessment; do not silently invent a new onset date.
Keep 756 mature training labels, 63-session refits, 15-session horizon, and the
existing chronological alert budgets. Use saved causal features, verified by
hashes. No new pillar fits or full-history feature scaling.

Run exactly these diagnostic candidates, retaining every outcome:

- Original EWMA logistic baseline and original five-feature combined model.
- Expanding Jeffreys-smoothed mature event frequency (no market predictors).
- Baseline/combined with C=1 instead of C=0.1 (regularization sensitivity).
- Baseline/combined with a trailing 1260-session training window and C=0.1.
- Combined plus ONE predeclared interaction: Hawkes daily intensity times RMT
  fast-minus-slow, using the existing train-only transform, C=0.1.
- Context baseline: EWMA volatility, trailing 20-session cumulative log return,
  and the saved contemporaneous cross-sectional downside breadth; context plus
  all four original pillar features. C=0.1, expanding training.

Context breadth must be present in the saved snapshot; otherwise record that
pair as unavailable. No VIX/macro/news inputs in this experiment: their vintage
and release-time suitability require a separate audit. This prevents an
unverified external series from becoming claimed prediction evidence.

Use common coverage and matched baseline/candidate comparisons. Save all daily
forecasts, fit cutoffs, calibration cutoffs, events, and metrics. Report paired
63-session block intervals as descriptive only, with 21/126-session sensitivity
for the original combined versus baseline. Also break loss scores into fixed
calendar eras (through 2014, 2015–2019, 2020–2022, 2023 onward).

No winner is deployed. No historical result from this search can establish a
statistically significant improvement after selection. The deliverable is an
audit, reproducible evidence, and an ordered development/validation plan.
