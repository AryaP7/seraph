# Fusion-architecture experiment — pre-registration

**Written 2026-10-14, BEFORE any candidate was fitted or evaluated.** Committed
to disk and hashed before the first result, because every decision below is one
that could otherwise be made after seeing outcomes. This file is **not**
`preregistration.json` — that artefact is the FR35 ablation's and remains
deliberately uncreated while the Table B fold-count and event-count decisions
are open (D5(d)).

Nothing here amends a specification. FR32's epochs, FR32's 5–15 day lead window
and FR28's causal ECDF are used **as written**.

---

## 1. The question

Can a fusion architecture whose parameters are **learned from historical
training data** produce causal, out-of-sample advance warning of systemic
crises, at an acceptable false-alarm rate, better than the existing equal-weight
composite or the strongest individual input?

## 2. Why this is not obviously answerable — the governing constraint

Measured last session (`CRISIS-REPLAY.md` §5c, `*-67`, `*-73`), **pre-onset**
15-day separation and T3 AUC of every available input:

| input | pre-onset separation (σ) | T3 AUC |
|---|---|---|
| Hawkes (standardised) | +0.0623 | — |
| RMT `λ₁/N` (standardised) | −0.2925 | 0.4340 |
| Hamilton LSD (standardised) | −0.1769 | — |
| RMT `SCA_t` (FR18) | — | 0.5324 |
| RMT `Ω_t` | — | 0.5934 |
| RMT `V_t^eig` | — | 0.5205 |
| RMT `F_t` | — | 0.3791 |

**A convex combination of inputs that are individually non-predictive is
non-predictive.** If every input has T3 AUC ≈ 0.5, no weighting on the simplex
can move the combination far from 0.5 — this is arithmetic, not pessimism. So
candidate B is *bounded above* by roughly its best input.

Three things could still break that bound, which is why the experiment is worth
running rather than asserting:

1. **Unconstrained weights** (candidate C) can exploit *negative* loadings — a
   pillar that falls before onsets is informative with a negative sign. Whether
   that generalises from 6 events is the open question.
2. **Escalation** (candidate D) is not an average. If one pillar spikes before
   *some* onsets, an OR-rule catches what averaging suppresses.
3. **Interaction** — a pillar may be informative only conditional on another.

## 3. Pre-registered hypotheses

* **H1** — Learned convex weights do not beat the best single pillar
  out-of-sample at the false-alarm budget.
* **H2** — Learned weights are unstable across chronological folds. Operational
  definition: the per-fold argmax weight vectors span more than 0.33 in
  L1 distance (i.e. at least one pillar's weight moves by more than a third of
  the simplex) across folds.
* **H3** — Escalation raises the event-level warned rate but its false-alarm
  cost leaves it indistinguishable from the relocation null.
* **H4** — No candidate achieves a warned rate significantly above the no-skill
  benchmark at the false-alarm budget, on the untouched confirmation period.

Each is a prediction that can fail. If H1–H4 are all *rejected*, SERAPH has a
working learned fusion and that is the finding.

## 4. The false-alarm budget — fixed now

**Primary budget: ≤ 2 false-alarm episodes per year.**

Justification, stated before results: FR32 labels 6 crises in ~21.5 years, a base
rate of 0.28 events/year. At 2 FA/yr an operator receives roughly **7 false
alarms per true event**. That is already generous for a monitoring signal and is
only defensible because the intended use is an *amber* "look closer" indicator
(SPEC §7 item 7 / C11's decision-support framing), not an automatic action. A
budget above ~4/yr would mean the alert is on more often than not during stress
clusters and carries no decision content.

Reported at **0.5, 1, 2 and 4 FA/yr**; **2 is primary** and the others are
sensitivity. Model selection uses the primary budget only.

## 5. Candidates — fixed set, no additions after results

| id | architecture |
|---|---|
| **A** | Existing equal-weight composite `(1/3, 1/3, 1/3)`, D2-masked and renormalised. **Reference baseline, retained throughout.** |
| **B** | Constrained convex learned weights: `w ≥ 0`, `Σw = 1`, simplex grid at step 0.05 (231 points), plus ridge shrinkage toward equal weights at λ ∈ {0, 0.25, 0.5, 0.75}. |
| **C** | Regularised predictive fusion: L2 logistic regression on the three standardised pillar scores, `C ∈ {0.01, 0.1, 1.0}` selected by **inner** chronological CV on training folds only. Coefficients unconstrained in sign. |
| **D** | Composite **plus** independent escalation: alert if composite ≥ θ_c **OR** any single pillar ≥ θ_p, with the false-alarm budget split equally between the two arms on training data. |
| **E** | Individual-pillar baselines (Hawkes, RMT, Hamilton separately) and the strongest existing single features: `semivar_20`, `rv_20`, `drawdown`, `rv_accel_5`, `dd_accel_5`, and **India VIX** (2014-05-15+, 3,034 rows). |

**No nonlinear model, no hyperparameter search beyond the three `C` values
above, no feature engineering beyond what already exists in the repository.**

## 6. Target and labels — unchanged from the approved protocol

* **Target**: `y_t = 1` for `t ∈ [onset − 15, onset − 1]` trading days, FR32's
  upper lead bound. **In-crisis days `[onset, onset + 30]` are dropped**, so a
  crisis reading can never be scored as a warning.
* **Onsets**: `seraph/validation/epochs.py`, unmodified. `tariff_2026` remains
  `PROVISIONAL` (SPEC OQ3 open) and is flagged wherever it carries a result.
* **Event-level warning**: a rising edge of the alert inside the pre-onset
  window. A standing alert is one decision, not one per day.
* **Minimum lead**: FR32's lower bound, 5 trading days, reported alongside the
  15-day figure.

## 7. Evaluation protocol — fixed now

**Chronological development / confirmation split, declared before any fit:**

* **Development epochs (4):** `gfc_2008`, `taper_2013`, `ilfs_2018`,
  `covid_2020`. All model selection, hyperparameter choice, threshold setting
  and diagnosis happen here.
* **Untouched confirmation epochs (2):** `tightening_2022`, `tariff_2026`.
  Touched **once**, after the architecture is selected. `tariff_2026`'s label is
  provisional, so the confirmation rests materially on a single clean event —
  stated now as a limitation, not discovered later.

**Within development:** expanding-window rolling-origin, leave-one-epoch-out in
chronological order. Fold *k* trains on all data strictly before epoch *k*'s
onset and tests on epoch *k*. Fold 1 has no training data and is reported as
untrainable rather than silently dropped.

**Everything is fitted on training data only**: the ECDF normalisation window
(already causal by `window_from`), weights, logistic coefficients, `C`, and
**the alert threshold** — which is set on the training period to hit the
false-alarm budget, then applied unchanged to the test period.

**Pillar availability is reported per fold.** Hawkes exists from 2017-02-09
(473 refits, every 5 sessions); causal Hamilton from 2013-01-14; RMT from
2005-01-03. A fold without Hawkes is **not** a three-pillar evaluation and will
not be described as one. Two variants are run and reported separately:
(i) D2-masked full span, weights renormalised over available pillars;
(ii) strict all-three-available only.

**Statistics**: relocation null (common-offset circular shift, measured type-I
8% at nominal 5%), block bootstrap at the measured 770-session integral
timescale, and Holm correction over the full candidate set actually evaluated.
Six onsets give **N_eff ≈ 5**, so a 0-of-N result carries a Clopper–Pearson
upper bound, not a point claim.

## 8. Model-selection and tie-breaking rules — fixed now

1. Candidates are ranked on **development** event-level warned rate at **2
   FA/yr**.
2. Ties (within 1 warned event) break toward **fewer fitted parameters**, then
   toward the equal-weight baseline.
3. A candidate is selected only if it beats baseline A **and** its relocation-null
   p-value is below the Holm threshold on development data.
4. **If no candidate clears rule 3, the finding is reported as negative and
   baseline A is retained.** No candidate is promoted on a point estimate alone.
5. The confirmation epochs are evaluated **once**, for the selected architecture
   and for A, and the result is reported whatever it is.

## 9. What would make this a failure of integrity

Stated so it can be checked against the final report: tuning on the
confirmation epochs; adding a candidate after seeing results; relaxing the
false-alarm budget to admit a winner; reporting a development result as
out-of-sample; describing a contemporaneous rise as advance warning; or
presenting a rank-like composite as a calibrated probability.

---

**Hash of this file is recorded in the first experiment log** so the ordering is
auditable.
