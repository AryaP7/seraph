# First Real End-to-End CSRS — and Why It Does Not Yet Add Value

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`.**
Evidence: `docs/evidence/20261012T18*-13..16-*.log`, `HAWKES-WINDOW-SELECTION.md`.

---

## 1. What now executes end to end

`rmt_output` (E7) + `hawkes_output` (E6) → C8 Kalman → C9 fusion → `csrs` (E10).
**2,357 CSRS points, 2017-02-09 → 2026-08-20, 0 failures, exit 0.** Real persisted
model output only; no mocks anywhere in the path.

| table | before | after |
|---|---|---|
| `hawkes_output` | 0 | **473** |
| `csrs` | 0 | **2,357** |

Idempotency proven on both: E6 `473 → 473 (inserted 0, updated 10)`;
E10 `2,357 → 2,357 (inserted 0, updated 2,357)`. Zero duplicate primary keys,
zero invariant violations (`csrs ∈ [0,1]`, `var ≥ 0`, `|shapley| = 3`, `|mask| = 3`).

## 2. The headline result: the composite is beaten by a trivial baseline

Pre-registered: labels from `validation/epochs.py`, FR32 horizons, threshold =
top decile of each series' own causal trailing 2 years, applied identically.

| series | AUC | alert% | precision | recall |
|---|---|---|---|---|
| CSRS (composite) | **0.5372** | 8.8% | 0.0529 | 0.0917 |
| RMT alone (λ₁/N) | **0.4226** | 16.8% | 0.0682 | 0.2250 |
| Hawkes alone (n/(1−n)) | 0.5931 | 14.7% | 0.1040 | 0.3000 |
| **Realised vol (baseline)** | **0.7698** | 11.4% | **0.1978** | **0.4417** |

**Realised volatility — the cheapest possible stress proxy — dominates the
composite on every detection metric** (AUC 0.77 vs 0.54; precision 3.7× higher).

**RMT alone scores AUC 0.4226, below chance.** That is not a bug: it independently
reproduces AMENDMENT-04 §3.1's measured 18–36 month response lag. At a break date
the 1,000-day window has not yet seen the crisis, so coupling reads *low*.

### Advance warning: none, from anything

| epoch | CSRS lead / crisis | RV lead / crisis |
|---|---|---|
| ilfs_2018 | 0% / 0% | 0% / **100%** |
| covid_2020 | 0% / 27% | 0% / **77%** |
| tightening_2022 | 0% / 10% | 0% / 0% |
| tariff_2026 * | 0% / 0% | 0% / 0% |

\* provisional date, SPEC OQ3 open.

**The CSRS gives 0% advance warning on all four epochs.** Only `tightening_2022`
shows any lead at all, from RMT (73%) and Hawkes (100%) individually. Realised
volatility is a strong *detector* and an equally useless *predictor* — its lead is
also 0% everywhere.

**So no series evaluated here is an early-warning system.** They are, at best,
contemporaneous detectors, and the composite is the weakest of them.

### Incremental value: there isn't any

```
corr(CSRS, RMT)            = +0.7765   <- the composite is largely RMT relabelled
corr(CSRS, Hawkes)         = +0.0692   <- Hawkes contributes almost nothing
corr(CSRS, realised vol)   = -0.0058   <- orthogonal to the one thing that works
```

Hawkes's mean Shapley contribution is **0.0139** against RMT's **0.5992**.

## 3. Why Hawkes contributes so little — a spec-vs-implementation gap

D4's age model uses `h_hawkes = 1.0 bar` (NFR4 assumes bar-frequency Hawkes).
AMENDMENT-03's pooled rolling-window estimator can only deliver **session**
cadence, and the selected refit cadence is 5 sessions = 375 bars. So R saturates
to its ceiling within one session and D2 row 4 masks Hawkes off:

```
mask (True, True, False):   468 ticks  (19.9%)  <- Hawkes's own refit dates
mask (False, True, False): 1889 ticks  (80.1%)  <- NOISE_SATURATED
```

**`h_hawkes` was not changed.** Tuning a spec'd D4 constant so a pillar stays in
the mask is exactly the kind of change that manufactures a result.

A second, independent gap: FR28's `MIN_WINDOW_OBS = 252` is **unreachable** at a
5-session cadence (~250 observations in a 5-year window), so all 473 Hawkes
emissions carry `PARTIAL_COVERAGE`. A daily refit (818 min) would close both gaps.

## 4. Two defects found, both real, both fixed honestly

**(a) FR13-gated MTS inverts the pillar.** MTS is 0 on 352/473 windows (74.4%).
Through FR28's rolling ECDF, a zero maps to the ~68th percentile because ~70% of
any trailing window is zeros:

```
gate CLOSED (MTS=0) -> rank mean 0.6791      gate OPEN -> rank mean 0.6778
corr(rank, branching ratio):  gated MTS = -0.4027   ungated n/(1-n) = +0.5419
```

So "downside asymmetry not significant" would read as *elevated* risk, and higher
contagion would *lower* the score. Fixed by adding `hawkes_contagion_emission`,
which carries the ungated `n/(1−n)` and leaves FR13 travelling as provenance —
matching C5's own docstring ("a normal-mix state, not an absence of contagion").
`hawkes_emission` was left untouched; the change is purely additive.

**(b) A look-ahead leak in the driver, caught by the S5 contract.** Selecting the
most recent Hawkes refit by **date** offered the 2024-11-01 Diwali Muhurat refit
(ts 18:55 IST) to that day's 15:30 decision. `PillarObservation` refused it:
`CONTRACT_VIOLATION: tau > ts`. Fixed by selecting on timestamps, so the Muhurat
refit becomes available the following session.

Related: the writer takes `ts` from the data rather than synthesising
`close_ts(date)`, which is why five genuine NSE irregularities persisted
correctly — two Saturday DR sessions (12:25), two Diwali Muhurat sessions
(18:55, 14:40) and one 76-bar session (15:30). Using `IST_CLOSE` would have
fabricated a 15:30 stamp that never existed and mis-stamped Muhurat by 3.5 hours.

## 5. Score semantics — exactly what this number is

`CSRS_t = Σ_j ξ_j (w_j ⊙ mask, renormalised)ᵀ x̂_t`, where `x̂` is C8's reconciled
state of FR28 ECDF-ranked pillar sub-scores.

* **`xi_mode = "uniform"`** — (⅓,⅓,⅓) substituted for Hamilton's regime
  probabilities. A spec'd mode, and part of the `csrs` primary key, so it can
  never be confused with a Hamilton-ξ run.
* **Weights: equal-weight research baseline.** `CalibrationConfig.epochs = ()`
  and `kappa_miss = kappa_fa = 1.0`, so the content hash
  `349a6874e8bc6884…` binds the fact that these weights were trained on nothing.
  FR30 has not been run. **No learned or calibrated weight is claimed.**
* **It is NOT a probability.** It is a mask-renormalised weighted average of two
  trailing-percentile state variables. It has no event definition, no horizon and
  no calibration.
* **Alert levels are C9's provisional constants** (amber 0.50, red 0.75) and are
  uncalibrated: they label 959 days red and 624 amber out of 2,357 — i.e. 67% of
  all days are amber-or-worse, which is operationally meaningless. This is
  evidence that FR30 is required, not optional.
* **Degraded mode works as designed:** every row carries `MASK_DEGRADED`, and the
  mask records Hamilton's structural absence on all 2,357 rows.

## 6. Status by category

| | Hawkes writer | CSRS path |
|---|---|---|
| Mathematical correctness | engine unchanged | C8/C9 unchanged; invariants 5/5 |
| Synthetic behaviour | **PASS** (14 tests) | covered by CT-4…CT-9 |
| Real-data reproducibility | **PASS** | **PASS** (2,357 pts, deterministic) |
| Statistical identification | **PASS** (0/120 unidentifiable fits) | n/a |
| Idempotency / persistence | **PASS** | **PASS** |
| Failure propagation | — | **PASS** (a bad bind aborted the txn; 0 partial rows) |
| Chronological out-of-sample usefulness | **FAIL** | **FAIL — beaten by realised vol** |
| Production readiness | not claimed | not claimed |

## 7. Honest conclusion

The **engineering** objective is met: a reproducible, idempotent, fully
provenance-tagged database-to-score path now exists and runs on real data, with
Hamilton correctly excluded rather than quietly included.

The **scientific** objective is not. Composing two signals that individually lack
skill did not produce skill. Each pillar's own amendment already said as much —
AMENDMENT-03 measured ≈no predictive skill for the branching ratio, AMENDMENT-04
withdrew every lead-time claim for λ₁/N and documented an 18–36 month lag — and
this evaluation reproduces both conclusions independently from the persisted data.

**SERAPH is a validated research prototype of a composite risk *state*, not an
early-warning engine.** Any stronger claim is unsupported by the evidence in this
repository.

### Limitations

1. Four evaluable epochs, one with a provisional date. No pooled significance
   claim is made and none should be inferred.
2. Realised volatility's AUC advantage is partly tautological: crisis windows are
   *defined* around market crashes, so a volatility measure will score well on
   them. That makes it a strong detector, not a predictor — its lead is 0% too.
3. `gfc_2008` and `taper_2013` are unevaluable: Pillar 1 has no data before 2015.
4. Hawkes participates in only 19.9% of ticks (§3).

## 8. Reproduction

```bash
docker start seraph-timescaledb
python scripts/compare_hawkes_windows.py --points 24 --windows 60,250,500
python scripts/compare_hawkes_windows.py --points 24 --windows 750,1000
python scripts/write_hawkes_production.py --window-days 500 --refit-every 5 --write
python scripts/run_csrs_research.py --write
python scripts/evaluate_csrs_research.py
pytest tests/test_c5_hawkes_writer.py -v        # 14 passed
pytest tests/contract -q                        # 46 passed, 1 pre-existing CT-3 failure
python scripts/check_invariants.py              # 5/5
```
