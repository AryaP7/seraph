# Addendum to the fusion pre-registration — candidate D′

**Written 2026-10-14, after candidate D's failure was diagnosed but BEFORE D′
was run or evaluated.** Hashed before the first D′ result.

The parent pre-registration (`FUSION-PREREGISTRATION.md`, sha256
`3d8e8de372e328444d9711fcb531c41deb8e91bac17100c0d19ff295abb4848d`) fixed the
candidate set and its §9 lists "adding a candidate after seeing results" as a
failure of integrity. **This addendum does not amend that set.** D′ is recorded
as a separate, clearly-labelled follow-up to a *diagnosed mechanical failure*,
and its result must never be reported as part of the pre-registered A–E
comparison.

---

## 1. Why D′ exists — the failure was mechanical, not evidential

Candidate D (composite ≥ θ_c **OR** any pillar ≥ θ_p) warned 0/3 on development.
But its fitted thresholds show it was **never tested as designed**:

| fold | composite θ_c | pillar θ_p (hawkes, rmt, ham) |
|---|---|---|
| taper_2013 | 0.999999 | —, **1.0**, 0.956 |
| ilfs_2018 | 0.999999 | 0.716, **1.0**, **1.0** |
| covid_2020 | 0.999999 | 0.719, **1.0**, **1.0** |

FR28 maps each sub-score to an ECDF **rank**, which is bounded at 1.0 and awards
exactly 1.0 to every running-maximum day. Holding such a score to 2 false alarms
a year requires a threshold above the 99.9th percentile — and **a rank has
nothing above 1.0**. There is no level between "fires on every running-max day"
and "never fires", so the arms saturate and the OR-rule collapses to whichever
single arm still has a non-degenerate threshold.

That is a **resolution** failure of the scale, distinct from the evidential
failure (no pre-onset information) that defeated candidates A, B and C. The two
must not be conflated, and the only way to separate them is to re-test the same
design on a scale with upper-tail resolution.

## 2. D′ — the single change

**D′ is D with the escalation arm moved from the rank to the raw pillar
quantity**, compared against its own causal trailing quantile:

* **Composite arm, unchanged:** the equal-weight rank composite ≥ θ_c.
* **Escalation arm, changed:** pillar *p*'s **raw** value exceeds its trailing
  five-year `q_p` quantile, where the raw values are λ₁/N (or `SCA_t`), the
  Hawkes contagion state `n/(1−n)`, and Hamilton's `LSD_t`. Raw values are
  unbounded above, so the upper tail has resolution a rank does not.

Nothing else changes: same reconciled composite, same rolling-origin folds, same
development/confirmation split, same false-alarm budget, same onsets, same
15-day pre-onset target with in-crisis days dropped.

**The budget is enforced on the combined rule, not arm by arm.** Candidate D
overshot its nominal budget at every level (0.56/1.86/3.13/6.11 against
0.5/1/2/4) because splitting a budget across OR-arms does not bound the union.
D′ fixes the *total* realised false-alarm rate on training data instead.

## 3. Pre-registered hypothesis

* **H5** — D′ does not achieve an event-level warned rate above its own no-skill
  rate at 2 FA/yr, on either development or confirmation.

If **H5 is rejected**, the conclusion changes materially: the escalation design
works and candidate D's failure was the scale. If **H5 is confirmed**, the
rank-scale diagnosis is shown *not* to have been the thing standing between
SERAPH and advance warning, and the evidential blocker is the whole story.

Either outcome is informative, which is the test for whether an experiment is
worth running.

## 4. What is fixed now

* Budget: **2 FA/yr** primary, enforced on the combined rule.
* Thresholds: both arms fitted on each fold's training period only.
* Quantile grid for `q_p`: the same downward search already used for θ_c, over
  trailing-window quantiles, with no additional hyperparameter.
* Statistics: binomial test against D′'s own realised alert rate, plus the
  relocation null where a single series exists.
* **Reporting**: D′ appears in `FUSION-ARCHITECTURE.md` under its own heading,
  explicitly outside the pre-registered A–E table.

## 5. What would make this a failure of integrity

Reporting D′ inside the pre-registered comparison; tuning its quantile grid
after seeing results; relaxing the budget to admit it; or presenting a 1-of-2
confirmation hit as validated advance warning when development says otherwise.
