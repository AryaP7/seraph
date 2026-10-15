# SERAPH experimental replay

Status: research implementation complete; original crisis-prediction claim remains unvalidated.

Data as of **2026-08-21**. This is a historical snapshot, not live monitoring.

All three pillar families are present in `three_pillars` and `combined`. Ablations are comparison controls.

## Original pre-onset question

Combined model, fixed 15-session window before each unchanged project event date:

| Event | Label | Result | First warning | Lead sessions |
|---|---|---|---|---|
| gfc_2008 | 2008-09-15 | unassessable | - | - |
| taper_2013 | 2013-05-22 | missed | - | - |
| ilfs_2018 | 2018-09-21 | missed | - | - |
| covid_2020 | 2020-02-20 | missed | - | - |
| tightening_2022 | 2022-01-05 | missed | - | - |
| tariff_2026 | 2026-02-01 | missed | - | - |

All dates are inherited provisional research labels; tariff-2026 is explicitly unresolved and cannot establish validation.

## Probability and alert comparisons

Lower Brier score is better. Metrics below share common forecast coverage within each target. Alert rates use each model’s own assessable coverage.

| Target | Model | Brier | AUC | False episodes/year | Warning time |
|---|---|---:|---:|---:|---:|
| loss10_15 | baseline_logit | 0.0698 | 0.6548 | 0.9940 | 5.8% |
| loss10_15 | three_pillars | 0.0706 | 0.6506 | 1.4032 | 2.0% |
| loss10_15 | combined | 0.0695 | 0.6588 | 1.4617 | 2.5% |
| loss10_15 | without_hawkes | 0.0699 | 0.6559 | 1.3448 | 3.5% |
| loss10_15 | without_rmt | 0.0695 | 0.6579 | 1.1694 | 3.0% |
| loss10_15 | without_hamilton | 0.0695 | 0.6620 | 1.3448 | 3.0% |
| onset15 | baseline_logit | 0.0194 | 0.3488 | 1.6371 | 18.4% |
| onset15 | three_pillars | 0.0195 | 0.2553 | 3.1573 | 12.3% |
| onset15 | combined | 0.0195 | 0.2691 | 2.7480 | 13.3% |
| onset15 | without_hawkes | 0.0195 | 0.2758 | 2.9234 | 13.5% |
| onset15 | without_rmt | 0.0195 | 0.3099 | 2.9819 | 14.4% |
| onset15 | without_hamilton | 0.0195 | 0.2782 | 2.3387 | 16.2% |
| loss10_15 | ewma_student_t | 0.0711 | 0.6357 | 1.2045 | 10.0% |
| loss10_15 | gjr_garch_t | 0.0697 | 0.6566 | 1.7484 | 2.6% |

The loss endpoint is a 10% decline from the decision close at any close in the next 15 sessions. It is not a named-crisis forecast.

## Combined versus volatility logistic baseline

Paired Brier differences below use common pairwise coverage. Negative favors combined. Intervals are descriptive 63-session block bootstrap intervals, not confirmation after model selection.

- loss10_15: difference -0.0003; interval [-0.0019, 0.0011].
- onset15: difference 0.0000; interval [0.0000, 0.0001].

## What this establishes

The software now issues causal, timestamped future-target forecasts and auditable alerts. It can replay the available history without reading future labels during fitting. That establishes implementation behavior, not dependable crisis foresight.

## Limits

- Retrospective research: COVID and the other events informed project design. This is not an untouched pre-COVID model or prospective validation.
- Underlying adjusted prices are a current snapshot, not an as-first-published vintage archive. Universe/survivorship and turnover-proxy caveats are inherited.
- The market series is an equal-weight geometric-return research index of available universe members, not a tradable portfolio or the NIFTY index.
- All project event dates are provisional; tariff-2026 is explicitly unresolved. Warnings against that placeholder are diagnostic only.
- New daily-tail Hawkes and 10 hash-portfolio RMT are distinct from original intraday/500-stock estimators; no high-dimensional RMT significance claim is made.
- Hamilton next-crisis-state probability denotes a fitted high-volatility latent state, not the probability of a named crisis.
- Only six labelled episodes exist; overlapping daily positives do not create six independent years of crises. Sampling and regime uncertainty remain substantial.
- Threshold budgets are fit on past data and may be violated subsequently. Abstention, missingness, and unassessable early periods are retained.
- Bootstrap intervals do not correct for research/model selection, changing regimes, data revisions or label uncertainty.
- HMM cap-limited and Hawkes sparse-event fits remain visible in fit_audit.json; forecasts contain model uncertainty not captured by simulation standard errors.
- No broker execution, production monitoring, point-in-time news/macro ingestion, or production acceptance is claimed.

## Reproduction

Run `./.venv/Scripts/python.exe scripts/run_prediction_experiment.py --out research_results/replication` from this copied project. No source database access is needed. See `EXPERIMENT.md` for fixed choices and `docs/EXPERIMENT-MATH.md` for repaired fusion equations.

Artifacts: `predictions.parquet`, `features.parquet`, `summary.json`, `fit_audit.json`, `alert_episodes.csv`, `event_warnings.csv`, `provenance.json`.
