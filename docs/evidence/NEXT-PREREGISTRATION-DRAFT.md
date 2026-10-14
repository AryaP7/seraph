# DRAFT pre-registration — admitting a new input to SERAPH

**STATUS: DRAFT. NOT IN FORCE. NOT HASHED.**

This is deliverable 4 of `DECISION-PACKAGE.md`: the protocol a *future* candidate
input must pass before it may be considered for fusion. It is deliberately
unhashed and unsigned, because a pre-registration is only meaningful once the
data it governs exists and the owner has authorised the experiment. **It becomes
binding only when (a) a candidate input has been acquired, (b) §2's coverage
minimum is met, and (c) the owner signs and hashes it unchanged.**

It is **not** `preregistration.json` — that artefact belongs to the FR35 ablation
and remains deliberately absent pending the Table B fold-count and event-count
decisions (D5(d)).

Written 2026-10-14 against git `f3eaac8`.

---

## 0. Why this exists in this form

Three prior investigations each reached a negative result, and each was credible
only because its rules were fixed first. The failures this protocol is shaped to
prevent are the specific ones already encountered:

* **A high contemporaneous AUC read as predictive.** `semivar_20` separates
  crisis windows at **+2.138σ** and `vix_ratio_60` at **+4.187σ** — and both warn
  before **0 of 6** onsets. Contemporaneous strength is not weak evidence of
  advance warning; it is **no** evidence of it.
* **A high T3 AUC read as skill without its null.** `drawdown` has the highest
  raw T3 AUC in the corpus at **0.6322** — against its own no-signal 95th
  percentile of **0.6569**, because a persistent series produces a wide null.
* **A loose threshold read as a result.** `rv_accel_5` at an 80th-percentile
  threshold warns before **5 of 6** onsets at **p = 0.1131**, because its
  no-skill rate at that threshold is 0.53.
* **Selection mistaken for generalisation.** Leave-one-epoch-out would have
  picked `dd_accel` on **0 of 6** folds and `rv_accel` on **2 of 6**.

Each rule below exists because of one of these.

---

## 1. Scope — what this protocol does and does not decide

**Decides:** whether a single named candidate input carries credible, causal
pre-onset information, on its own, independent of fusion.

**Does not decide:** whether the input improves the CSRS. That is a separate
question and a separate experiment, gated on this one passing. **A feature must
demonstrate pre-onset information independently before it is considered for
fusion** — fusion cannot be the test, because a composite's performance confounds
the new input with the three pillars.

**Unchanged by this protocol:** FR32's six epochs and its 5–15 trading-day lead
window; FR28's causal ECDF; the three pillars in `PILLAR_ORDER`; equal-weight
fusion as the reference baseline. **Any change to a crisis label, horizon or
event definition requires explicit documented approval and invalidates this
protocol.**

---

## 2. Admission preconditions — checked before any evaluation runs

A candidate is **not evaluated at all** unless all of the following hold. These
are gates, not criteria: failing one makes the result untestable rather than
negative, and an untestable result must not be reported as a negative one.

| precondition | threshold | why |
|---|---|---|
| **Epoch coverage** | ≥ **4** of FR32's 6 epochs | below 4 the binomial is too coarse for any verdict |
| **Pre-onset density** | ≥ **80%** of days in `[onset−30, onset−1]` populated, per covered epoch | a sparse feature produces an untestable window, as Hawkes does at ≤ 3 observations |
| **Point-in-time availability** | value available **at or before 15:30 IST** on its own date | FR32's lead window cannot be populated by a value published later |
| **Publication lag** | documented, and ≤ **2 trading days** | the decisive gate for any macro series |
| **Revision policy** | documented; if restated, **vintages must be retained** and the *as-first-published* value used | a revised series is a look-ahead trap |
| **Independent epochs** | ≥ **1** covered epoch not already covered by India VIX (i.e. pre-2015) | otherwise the candidate is confined to the four epochs where VIX already fails, and adds no independent evidence |

The last row is the one that most plausibly disqualifies a real candidate, and
it is stated as a gate rather than a preference on purpose.

---

## 3. Target, labels and the warning definition

* **Target.** `y_t = 1` for `t ∈ [onset − h, onset − 1]`, trading days, for each
  horizon `h ∈ {5, 10, 15, 20, 30}`. **15 is primary** (FR32's upper lead bound);
  the others are reported as sensitivity and **do not** get their own
  significance claim.
* **In-crisis days `[onset, onset + 30]` are dropped.** A crisis reading can
  then never be scored as a warning — the single most important structural rule
  here.
* **Onsets.** `seraph/validation/epochs.py`, unmodified. `tariff_2026` remains
  `PROVISIONAL` (SPEC OQ3 open) and any result resting on it is flagged and not
  reported as a finding.
* **Event-level warning.** A **rising edge** of the alert inside the pre-onset
  window. A standing alert is one decision however long it lasts.
* **Minimum lead.** FR32's lower bound of 5 trading days; a 1-day lead is
  reported but does not count as an FR32-compliant warning.

---

## 4. False-alarm budget — fixed before evaluation

**Primary: ≤ 2 false-alarm episodes per year**, with **≤ 15% of assessable days
under alert**.

The second half is new and exists because the previous budget had a measured
blind spot: `drawdown` respected 2 FA/yr while alerting on **38.2% of days**,
since a standing alert counts once however long it lasts. **An episode budget
alone does not bound operational burden.** Both constraints must hold.

Reported at 0.5, 1, 2 and 4 FA/yr as sensitivity; **2 is primary and model
selection uses it alone.**

**The threshold is fitted on training data only**, to hit the budget there, and
applied unchanged to the test period.

---

## 5. Chronological protocol

* **Development epochs:** `gfc_2008`, `taper_2013`, `ilfs_2018`, `covid_2020` —
  all diagnosis, threshold setting and parameter choice happen here.
* **Untouched confirmation:** `tightening_2022`, `tariff_2026`. Evaluated
  **once**. Because `tariff_2026`'s label is provisional, the confirmation rests
  materially on `tightening_2022` alone — **stated now, not discovered later**.
* **Within development:** expanding-window rolling origin, leave-one-epoch-out
  in chronological order. Fold 1 has no training data and is reported
  **untrainable**, not silently dropped.
* **Everything is fitted on training data only:** normalisation windows,
  transformations, any parameters, and the alert threshold.

**Coverage is reported per fold.** A fold lacking the candidate, Hawkes or causal
Hamilton is **not** described as a full evaluation of those inputs.

---

## 6. Statistical requirements

* **Two calibrated nulls, both required.**
  * **relocation** — common circular shift of the onsets, preserving spacing;
    measured type-I error **8% at a nominal 5%**. The alternatives it replaced
    rejected at 50% and 40%/17% and are not to be reused.
  * **AAFT** — onsets fixed, series phase-randomised preserving its exact
    marginal.
* **A candidate must clear both**, at the Holm-corrected threshold over every
  comparison actually run. The comparison count is declared **before** running.
* **The permutation-resolution floor `1/(draws+1)` is printed**, and a p-value at
  the floor is reported as **censored, not measured**.
* **Dependence is corrected.** Intervals use a moving-block bootstrap at the
  measured integral timescale (**770 sessions** for `rv_t_yz`; re-measure for the
  candidate). Daily resampling is forbidden — it treats ~5,000 dependent
  observations as independent.
* **Power is stated, not assumed.** The T3 test's measured MDE is ~1.0 sd
  against both a rectangular step and a 75-session ramp (power 75–85%); at 0.5 sd
  power is 47–50%. **An effect below ~0.5 sd is not detectable here**, so a null
  result must be reported as "no detectable effect above ~0.5 sd", never as "no
  effect".
* **N_eff ≈ 5.** Six onsets at the measured timescale give about five
  effectively independent events. A 0-of-N result carries a Clopper–Pearson
  bound (0/6 ⇒ 95% upper **0.393**), not a point claim.

---

## 7. The admission criterion — one number, fixed now

A candidate input is admitted to a **fusion** experiment if and only if **all**
of the following hold:

1. All §2 preconditions pass.
2. On **development**, the event-level warned rate exceeds the candidate's **own
   no-skill rate** at 2 FA/yr, with `p ≤ 0.05` under **both** nulls after Holm
   correction over all comparisons run.
3. The candidate's T3 AUC at `h = 15` **exceeds the 95th percentile of its own
   no-signal distribution**. *(No input in the repository currently satisfies
   this — all 19 fall below it, which is why this clause is stated explicitly.)*
4. On the **untouched confirmation** period, the warned rate again exceeds its
   own no-skill rate, evaluated **once**.
5. Performance is **not** attributable to a single epoch: at least **2** covered
   epochs show a pre-onset warning.

**If criteria 2–5 are not all met, the candidate is rejected and the result is
published as negative.** No candidate is admitted on a point estimate, a chart,
a contemporaneous AUC, or an in-sample improvement.

**Tie-breaking**, fixed now: fewer fitted parameters first, then the simpler
construction, then the one with longer historical coverage.

---

## 8. Only then — the fusion experiment

If and only if a candidate is admitted:

* **Baseline:** equal-weight fusion over the three pillars, unchanged — the
  reference throughout.
* **Comparison:** baseline vs baseline-plus-candidate, with the candidate
  entering as a **fourth input to the fusion layer, not as a pillar.** P1
  Hawkes, P2 RMT and P3 Hamilton remain the three pillars; nothing is renamed or
  replaced.
* **Weights:** given that learned weights currently have 90% bootstrap intervals
  of **mean width 0.983** on a [0,1] scale, any weighting must report the same
  interval and **must not be reported to a precision the interval does not
  support**.
* **The question** is whether the composite beats both the baseline *and* the
  candidate alone. Beating only the baseline means the candidate should be used
  directly rather than fused.

---

## 9. What would make this protocol's result invalid

Stated so it can be audited against the eventual report: tuning on the
confirmation epochs; adding or swapping a candidate after seeing results;
relaxing either half of the false-alarm budget to admit a candidate; reporting a
development result as out-of-sample; describing a contemporaneous rise as
advance warning; presenting a rank-like score as a calibrated probability;
substituting a revised data vintage for the as-published one; or reporting an
untestable coverage failure as a negative finding.

---

## 10. Sign-off block — to be completed when this is adopted

```
candidate input      : ____________________________________
preconditions (§2)   : PASS / FAIL  (attach the coverage table)
comparison count     : ______   Holm threshold: ______
draws / floor        : ______ / ______
declared by          : ____________________  date: __________
owner approval       : ____________________  date: __________
sha256 of this file at adoption: ______________________________
```

**Until that block is completed and the file hashed, nothing in this document is
in force and no result may cite it as a pre-registration.**
