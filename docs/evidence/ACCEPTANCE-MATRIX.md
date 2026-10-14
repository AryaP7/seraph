# SERAPH Acceptance Matrix

**2026-10-13 04:15Z, git `f3eaac8`, branch `evidence/pre-arya-experimentation`.
Nothing committed, nothing pushed. Both parallel worktrees intact.**

This is the "define completion before claiming success" record. Every criterion
is `PASS` / `FAIL` / `BLOCKED` / `NOT YET VALIDATED`, each with the evidence that
decides it. Nothing is marked `PASS` on an assumption. Where a criterion was
previously treated as passed and is no longer, that is stated.

---

## 0. Integration assessment — six categories, judged separately

The mandate requires these six to be distinguished and warns that **a pass in
one must not imply a pass in another**. They are judged separately here because
in this project they genuinely diverge: the engineering is sound and the science
is not.

| category | verdict | the one number that decides it |
|---|---|---|
| **Implementation correctness** | **PASS, with one open defect** | 207 passed / 1 failed / 2 xfailed. Three real defects found this session: two C7 bugs **fixed** (EM shape, worth 16,573 llf; TVTP uniform start), one C4 Lee–Mykland mis-scaling **pinned not patched** (1/c = 1.2533× too strict). The failure is CT-3, deliberately preserved. |
| **Data and pipeline integrity** | **PASS** | 12 mechanical causality tests falsify leakage by perturbing the future and asserting the past is unchanged; all three pillars verified causal in source; truncation invariance bitwise exact. 5,363 ticks, 0 failures, 0 DB writes. |
| **Contemporaneous stress detection** | **FAIL — and selectively so** | Block bootstrap at the measured 770-session integral timescale: **every one of the 7 pillar/CSRS subsets loses 0.5-exclusion by L=21**, the shortest non-trivial block tested, and 0/7 exclude at L=770. But **3 of 4 simple baselines exclude 0.5 at *every* block length** — `rv_20` 0.7347, `dd_accel_5` 0.7015, `rv_accel_5` 0.6622. Precision overstatement 3.9–5.7× for every subset containing RMT or Hamilton. |
| **Incremental detection value** | **FAIL** | Pillars are **non-redundant** (2.75 effective of 3 — MG-1's premise holds) but near-empty: RMT alone explains **R² = 0.00001** of the crisis label over 5,363 days. Best three-pillar figure 4.0%, in-sample, on 468 days. **Learning the fusion weights does not recover value and can destroy it**: under the FR18 input, equal weights warn 1/4 on development while learned convex weights warn 0/3, because with nothing to learn the grid search lands on simplex corners and discards averaging. `FUSION-ARCHITECTURE.md` §7. **No further fusion experiment is justified 2026-10-14:** the precondition — that some candidate input first demonstrate credible causal pre-onset information — **is met by no available input** (§criterion 9), so none was run. `PREDICTIVE-INFORMATION-AUDIT.md` §6. |
| **Advance-warning capability** | **FAIL — and this is the primary question** | **0 pre-onset warnings, 6 epochs × 5 horizons.** Nothing distinguishable from chance (11 comparisons, lowest p = 0.1108 vs Holm 0.00455). Robust to threshold (1 of 50 cells at p ≤ 0.05 where chance predicts 2.5), to signal shape (ramp power 75–77% at δ=1.0), and to dependence (**0/7 pillars and 0/4 baselines** exclude 0.5 at L=770). `semivar_20`, the best known feature, also 0/6. **And closed at the input level:** of 19 available inputs, **0 classify as moving before onset** and all 19 sit below their own no-signal 95th percentile. India VIX — the only forward-looking input held — is **−0.613σ before** onsets, +1.777 during and **+2.544 after**: implied volatility here is a *lagging* measure. |
| **Calibration and operational actionability** | **FAIL** | Brier skill score **−11.64**, ECE **0.575** against a 3.36% base rate. C9's amber threshold is crossed on **57–62% of all days**; 7.9 false alarms per true alarm; episode precision 0.112. |

**The shape of the result.** SERAPH is a correctly-implemented, causally-sound,
well-tested pipeline that **does not do the thing it was built to do**. The first
two categories pass on their own terms and say nothing about the last four.

**The sharpest single finding is in row 3, and it is worse than a uniform
negative.** Correcting for dependence does not flatten everything equally: it
destroys every pillar and every fusion configuration while leaving three
one-line volatility and drawdown features standing at every dependence
assumption tested. So the defensible claim is **not** "T1 has no resolving
power" — it is *"T1 has no resolving power for anything SERAPH builds, while
simple baselines retain it."* (Measured by Workstream B; it corrects a uniform
reading of mine.)

No economic claim is made anywhere: no position, execution or cost model exists
in this repository, so no drawdown-avoided or risk-reduction figure is
computable.

**What is *not* claimed.** Not that SERAPH cannot warn. Six onsets give a 95%
upper bound on the per-event warning probability of **0.393** against a no-skill
rate of 0.14, so this is a demonstrated *absence of evidence*, not evidence of
sub-chance behaviour — and the bound only becomes decisive at N = 20 onsets
against a record supporting at most 15. An effect below ~0.5 sd remains untested
(power 47–50%).

**Pillar identity is unchanged.** P1 Hawkes, P2 RMT and P3 Hamilton remain the
three pillars in `PILLAR_ORDER`. Nothing was renamed, removed or substituted; no
baseline was promoted into a pillar slot; no fourth pillar was added. The
baselines are comparators.

---

## 1. The twelve criteria

| # | criterion | status | evidence |
|---|---|---|---|
| 1 | **Mathematical / statistical correctness** | **PASS — two defects fixed, one pinned** | Two real C7 defects found and repaired this session: the EM plumbing shape bug (worth 16,573 llf) and the TVTP uniform start. Estimator now recovers known 2- and 3-regime series at **path accuracy 1.0000**. `HAMILTON-REGIME-SUPPORT.md` §2–3; 11 new regression tests. **A third defect found 2026-10-13 and pinned rather than patched:** C4's `extract_jumps` feeds a `μ₁`-corrected Lee–Mykland statistic to an uncorrected-`σ̂` critical value, so the rejection threshold is **1/c = 1.2533× too strict**. Because the Gumbel tail is thin the cost is **~3 orders of magnitude in level, not 25%**: effective α ≈ **1.0e−05** at production `n`, **975× tighter** than the documented 0.01. Monte Carlo on a pure-Brownian null: the shipped threshold rejects in **0 of 400** samples; power at 5σ is 0.250 against 0.620 corrected. Not fixed: SPEC FR10 `[v4]` quotes the *uncorrected* density (0.087) verbatim, so correcting the code without amending SPEC would put the two in contradiction (AGENTS.md §1). `xfail`-pinned in `tests/test_c4_lee_mykland_calibration.py`; `BLOCKER-TRIAGE.md` §D-1b |
| 2 | **Causal timestamp alignment, no leakage** | **PASS** | Truncation invariance bitwise exact (`20261012T134047Z-hamilton-causal-REAL/REPORT.md` §2c). A real look-ahead leak was caught by the S5 contract (Diwali Muhurat 18:55 refit offered to a 15:30 decision) and fixed with `bisect_right` on timestamps. All features trailing-window; universe point-in-time. **Strengthened 2026-10-13:** 12 new mechanical causality tests (`tests/test_replay_causality.py`) falsify leakage by perturbing the future and asserting the past is unchanged; all three pillars verified causal in source (RMT `dates[i-1000:i+1]`, Hamilton `check_B_assert_causal`, Hawkes timestamp selection) |
| 3 | **Data coverage and provenance** | **PARTIAL** | RMT 5,363 rows 2005–2026, 29/29 acceptance. Hawkes 473 refits 2017+ only (Kite intraday limit) — participates in 19.9% of 2017+ ticks. Universe coverage 91/95 (4 symbols lack intraday rows, needs an interactive Kite login). Hamilton observations causal, 5,365 rows. **Two coverage limits found 2026-10-13:** (a) the *causal* Hamilton series begins **2013-01-14** (2,000-day initial train), so SPEC §4's “Hamilton available for 2008 GFC” is unachievable without look-ahead and both pre-2015 epochs are `UNTESTABLE`; (b) Hawkes's `refit_every=5` cadence puts **at most 3 observations inside FR32's 15-day lead window**, below any threshold rule's minimum, so Pillar 1 standalone has **0 assessable days of 468**. `CRISIS-REPLAY.md` §6a–6b. **Two more coverage facts 2026-10-13:** (c) **`macro_covariates` is mostly but not entirely empty** — `g_t`, `g_t_sector_weighted`, `rbi_repo_rate`, `bank_credit_growth_yoy`, `inr_twi` and `brent_price` are **all 0 non-null** across 5,363 rows, so **O8/FR22's tariff covariate is unvalidatable as things stand** and production Hamilton substitutes lagged standardised RV (`fit_hamilton.py:82`). **Correction 2026-10-14:** `india_vix` *is* populated — **3,034 non-null rows, 2014-05-15 .. 2026-08-21, 100% dense in range** — covering 4 of 6 epochs but not 2008 or 2013. An earlier statement that the table was entirely empty was wrong. (SPEC OQ5 assumed India VIX from Nov 2007; the ingested series starts 2014-05-15.) VIX is now evaluated as a baseline and **fails**: 0 of 2 testable epochs warned, T3 AUC **0.4057** (p = 0.8536). **Note a SPEC discrepancy:** OQ5 states India VIX starts Nov 2007 and discusses substituting it for the 2008 epoch; the **ingested** series starts **2014-05-15**, so OQ5 reasons from a longer history than the repository holds. **Auxiliary inventory 2026-10-14:** `flow_aggregates` holds **1 row** (dated 2026-10-12, a live snapshot, no history) so **FR45 is unvalidatable and flow is an acquisition, not held data**; `tariff_events` **0 rows**; `microstructure_state`, `regulatory_action_log`, `validation_results` **0 rows**; and `daily_prices.log_return_std`/`yz_volatility` are **0 non-null**. `PREDICTIVE-INFORMATION-AUDIT.md` §2; (d) the 2005 corpus boundary is the **EOD2 adjustment caveat**, not FR52 (which binds at ~1999) and not macro — 637,900 pre-2005 rows are held and 0 are universe-flagged. `EVENT-COUNT-LIMITATION.md` §4. **Two documentation defects found 2026-10-14:** (e) `hawkes_output.alpha_beta` is a declared column that is **NULL on every row**, so the fitted Hawkes parameters are not persisted and `λ_t` cannot be reconstructed from the database — cheap to fix, owner B (C5); (f) `docs/DATA-ACQUISITION.md:106` asserts *“India VIX starts Nov 2007. Confirmed”*, which **independent search does not corroborate** — public sources place the launch in 2008 and real-time dissemination at ~2009–2010. The claim should be downgraded to unverified; a backfill would extend VIX coverage to **5 epochs, not 6**, since no plausible launch date populates FR28's 5-year window before 2008-09-15. `THREE-CHECKS-RESULTS.md` |
| 4 | **Reproducible, idempotent persistence** | **PASS** | E6 upsert idempotency verified (`*-14-hawkes-E6-idempotency.log`); csrs 4,714 rows, 0 duplicate PKs; artefact-id collision caught *before* it overwrote a run; `--write --full-span` now refused for the same reason. **A third artefact-identity hazard found 2026-10-13, before any writer exists:** `validation_results`' primary key is `(pillar_subset, reconciliation_mode, xi_mode, epoch)` and **omits `table_id`**, which is declared `NOT NULL`. Under ARCHITECTURE D5(b)'s 6-fold Table B the three subsets appearing in both tables collide on the 4 Hawkes-covered epochs — **24 of 128 `EvaluationRow`s silently overwritten**; under SPEC's 2-fold reading, 0. Free to fix now because no writer has been built. `BLOCKER-TRIAGE.md` §D-2 |
| 5 | **Integration and fusion contracts** | **PARTIAL** *(was PASS — downgraded 2026-10-13: the contracts hold, FR18 conformance does not)* | E7+E6 → C8 → C9 → E10 end to end, 5,363 ticks 0 failures on the full span; invariants 5/5; CT-4/5/7/9 pass; masks exactly as D2 predicts. **One conformance defect found 2026-10-13:** SPEC FR18 specifies Pillar 2's sub-score as `SCA_t`, but `orchestration/adapters.py:rmt_emission` standardises `λ₁/N`, named nowhere in FR16–FR19, while `rmt_output.sca_t` is computed, validated at 29/29 and **never read by the fusion path**. Era-controlled crisis separation **+0.5028σ (5/6 epochs) for `SCA_t` vs −0.3784σ (1/6) for λ₁/N** — a sign reversal. In T1 AUC: **0.6623 vs 0.4282**, i.e. the quantity in use is **anti-predictive**, not merely uninformative. A smaller sub-question rides with it: FR18 specifies “calibrated weights”, C6 uses equal thirds (SPEC §8 leaves them undefined), and the aggregate scores **below its own `Ω_t` component (0.7354)**. **But `Ω_t` has no advance-warning content either** — its T3 AUC 0.5934 falls below its own no-signal 95th percentile (0.6158), p = 0.088/0.104 under two calibrated nulls, Bonferroni threshold 0.01 over the 5 candidates. **No Pillar 2 statistic — specified, in use, or component — is distinguishable from no signal on T3.** Not fixed: it changes every CSRS value ever computed and C6 is another owner's. AGENTS.md §1 says the docs win, so this is a defect, not a variant. `CRISIS-REPLAY.md` §5c, gate 4 |
| 6 | **Each required pillar validated** | **FAIL (0 of 3 fully)** *(was 1 of 3)* | **P1 Hawkes** operational but **untestable for advance warning** — `refit_every=5` leaves ≤3 observations in FR32's lead window, 0 assessable days of 468. **P2 RMT** operational and 29/29 on its own acceptance, but the fusion path reads a **non-spec'd quantity** whose crisis separation has the wrong sign (criterion 5), and the spec'd `SCA_t` is flat pre-onset (+0.0861σ). **P3 Hamilton UNAVAILABLE** — not distinguishable from a no-regime process (AAFT `p = 0.7143`, AR(1) `p = 0.9524`). `HAMILTON-REGIME-SUPPORT.md` §5 |
| 7 | **Chronological out-of-sample evaluation vs baselines** | **PASS** | Walk-forward causal harness; 6 chronological folds; leave-one-epoch-out policy; 9 candidate baselines + 2 CSRS configurations scored on identical targets. **Extended 2026-10-13:** unified causal replay over all **7 FR35 pillar subsets + 4 simple-feature baselines × 6 epochs × 5 lead horizons**, identical grid and labels, nothing fitted — both alert rules are pre-specified, so there is no holdout to contaminate. `CRISIS-REPLAY.md` |
| 8 | **Demonstrated incremental value of the combined system** | **FAIL** | **The two validated pillars do not detect crises.** 2-pillar CSRS T1 0.5218 (p 0.40/0.41, 6 onsets); RMT alone 0.4283 (p 0.79); Hawkes alone 0.5937 (p 0.32). The composite also loses to its best single input (0.6573 vs `semivar_20` 0.7832). `DETECTION-CALIBRATION.md` §4. **Diagnosed 2026-10-13:** the pillars are **not redundant** — 2.75 effective independent of 3, |Spearman| ≤ 0.21, which *supports* MG-1's diversity premise — but they are near-empty: RMT alone explains **R² = 0.00001** of the FR32 crisis label over its own 5,363 days, and the best three-pillar figure is 4.0% in-sample on 468 days. A better fusion rule cannot help; only better inputs could. `CRISIS-REPLAY.md` §5b. **Block bootstrap at the measured 770-session timescale, 2026-10-13:** all **7 pillar/CSRS subsets lose 0.5-exclusion by L=21** and 0/7 exclude at L=770, while **3 of 4 simple baselines exclude 0.5 at every block length** (`rv_20` 0.7347, `dd_accel_5` 0.7015, `rv_accel_5` 0.6622). Precision was overstated **3.9–5.7×** for every subset containing RMT or Hamilton. Under `SCA_t` the point estimates improve materially (`CSRS[rmt]` 0.5292 → 0.6289, full system 0.5733 → 0.6632) and reach 7/7 exclusion at L=1 — **still 0/7 at L=770**. `EVENT-COUNT-LIMITATION.md` §6. **Two further results 2026-10-13:** the surviving acceleration signals are **not unique** — `rv_diff1` (realised vol minus *yesterday's*) has a lower p (0.0010) than `rv_accel` (0.0017) under a stricter 18-wide Holm, so `DETECTION-CALIBRATION.md` §2's “both survivors are second-difference quantities” does not hold; and **leave-one-epoch-out would have selected `dd_accel` on 0 of 6 folds and `rv_accel` on 2 of 6** (usual winner `semivar_20`). Their out-of-sample T1 AUCs do survive (0.6666 and 0.7534, both clearing two nulls) where `drawdown` collapses 0.8681 → 0.5940. `ACCELERATION-SIGNALS.md`. **Learned fusion tested 2026-10-14 and it does not help** — five pre-registered architectures (equal weight; constrained convex learned weights at 4 shrinkages; L2 logistic; composite+escalation; individual pillars plus 6 single-feature baselines incl. India VIX), rolling-origin with weights **and** threshold refitted per fold. **No fusion candidate warned before a single development crisis at any false-alarm budget from 0.5 to 4 episodes/year**, under either Pillar 2 quantity. Learned weights are arbitrary at this sample size: max pairwise L1 distance **1.700** (λ₁/N) and **1.900** (`SCA_t`) against a simplex maximum of 2.0, each fold crowning a different pillar, and best in-sample AUC *falling* toward chance as events are added (0.6585 → 0.5032 → 0.4905). **Weight uncertainty quantified:** 90% moving-block bootstrap intervals at the measured 770-session scale are hawkes [0.000, 1.000], rmt [0.000, 1.000], hamilton [0.000, 0.950] — **mean width 0.983 on a [0,1] scale**, near-maximal at every block length tested, with 21% of replicates putting >0.95 of the weight on a single pillar. A learned weight here is **not an estimate of anything**. **And the one mechanical explanation is ruled out:** candidate D's escalation arms saturated because FR28 ranks are bounded at 1.0, so a follow-up (D′, separately pre-registered) moved the escalation arm onto **raw** unbounded pillar magnitudes. The thresholds then resolved properly (fitted quantiles 0.9490–0.9795, not 1.0) and D′ still warned **0 of 5** — every testable development epoch and both confirmation epochs. **The rank scale was not what stood between SERAPH and advance warning**; the evidential blocker is the whole story. `FUSION-ARCHITECTURE.md` §5b |
| 9 | **Advance warning: lead time and false alarms** | **FAIL, and now bounded** | T3 null for every candidate under a calibrated null. A clean lead signal of ≥1.0–1.5 sd over 15 days is **excluded** (power 85–98%); below ~0.5 sd is untested (power 47%). **Bound challenged and held 2026-10-13:** those figures were against a rectangular step, the easiest alternative. Re-measured against a 75-session linear ramp and an AR(1) drift (φ = 0.9973) — the shapes a systemic-risk thesis predicts — power at δ = 1.0 sd is **75–77%** and **78–80%** respectively, against a pre-registered downgrade threshold of ~50%, with type-I 2–8% at nominal 5%. The negative is bounded against the realistic shape, not only the convenient one. `drawdown`'s 0.6735 is below the no-signal 95th pct (0.6774). `EARLY-WARNING-POWER.md`. **Now decisive 2026-10-13:** the unified causal replay gives the full three-pillar system **0 pre-onset warnings across 6 epochs × 5 horizons (5–30 days)**, p = 1.0000 against a no-skill relocation expectation of 0.14 ± 0.13. **This is absence of evidence, not evidence of sub-chance behaviour**: the 95% upper bound on the per-event warning probability is 0.393, and it only falls below the no-skill rate at N = 20 onsets against a record supporting at most 15. **And more events are not the lever:** the integral timescale of `rv_t_yz` is **770 sessions**, so the 5,363-session grid holds ≈**7 effectively independent realisations** and six nominal onsets give **N_eff ≈ 5**; nine additional defensible episodes would buy roughly **one**. Minimum detectable warned-rate 0.50 at N=6 → 0.33 at N=15, against an observed 0.00 — **the binding constraint is effect size, not sample size**. `EVENT-COUNT-LIMITATION.md`. No RMT-containing subset warned anywhere. **No signal tested — pillar, fusion or baseline — is distinguishable from chance** (11 comparisons, lowest p = 0.1108 against a Holm threshold of 0.00455). **The comparison set was not weak:** `semivar_20`, the repository's strongest known single feature and the leave-one-epoch-out winner on 4 of 6 folds, warns before **0 of 6** onsets at every horizon, p = 1.0000. Robust to the threshold: swept over 5 quantile levels with the null recomputed at each, **1 of 50 testable cells reaches p ≤ 0.05 where chance predicts 2.5**. Operationally 7.9 false alarms per true alarm, episode precision 0.112. `CRISIS-REPLAY.md` §3–5. **Closed at the INPUT level 2026-10-14, which is the decisive result:** 19 available inputs — all 3 pillars, all 4 FR17/FR18 RMT statistics, 5 simple baselines, India VIX + 2 transforms, 4 further market variables — were classified by *when* they move. **Zero classify as moving BEFORE onset** (14 DURING, 5 AFTER), and **all 19 have a T3 AUC below the 95th percentile of their own no-signal distribution**. Smallest p over two calibrated nulls is **0.0630**, so nothing reaches even an *uncorrected* 0.05 (Holm tightest 0.00263 over 19; survivors none). The largest pre-onset separation anywhere is **+0.432σ**, below the ~0.5 sd at which the T3 test has useful power. **So the two negatives compose: no architecture over these inputs warns, and the inputs contain nothing to warn with.** `PREDICTIVE-INFORMATION-AUDIT.md`. **The last held-data hypothesis closed 2026-10-14:** Pillar 1's **conditional intensity** `λ_t` — the only bar-frequency quantity, reconstructed at SPEC FR11's own quoted α = 0.055 / φ = 0.50 because `hawkes_output.alpha_beta` is **NULL on every row** — scores **+0.045σ before** onsets (DURING class) with T3 AUC **0.5496 below its own null p95 of 0.5697**, p = 0.119/0.121. The raw daily jump count agrees to three decimals. And `intraday_bars` starts 2015-02-02, so **Pillar 1 cannot reach the pre-2015 epochs at any refit cadence or emission frequency**. `THREE-CHECKS-RESULTS.md` |
| 10 | **Calibration / uncertainty for probabilistic claims** | **FAIL** *(was NOT YET VALIDATED — now measured, and it fails)* | Brier/ECE/BSS computed 2026-10-13 against FR32's contemporaneous label (180 crisis days of 5,363 = 3.36%). Full system: **Brier 0.4292, Brier skill score −11.64, ECE 0.575** — roughly 12× worse than always predicting the base rate. This is a **scale error by construction**, not a tuning gap: FR28 makes each sub-score an ECDF rank ≈ U[0,1], so the composite cannot be a calibrated probability of a 3.36% event and **FR30 will not fix it** — FR30 optimises weights, not scale. Consequently C9's `PROVISIONAL_AMBER = 0.50` is crossed on **57–62% of all days**. FR29 variance and CIs are still emitted and the score is still not *described* as a probability; what is new is that the distance from one is now quantified. **2026-10-14:** candidate C fitted an L2 logistic on the three reconciled pillar scores, which *would* emit a probability — but only **1 development fold has ≥10 training positives**, so three coefficients cannot be estimated, and where inner CV can choose it selects the strongest regularisation (`C = 0.01`) and drives the coefficients to ≈0. **The model's own cross-validated answer is “predict the base rate”.** Its output is therefore *not* presented as a calibrated probability and the CSRS remains rank-like. `CRISIS-REPLAY.md` §5, `FUSION-ARCHITECTURE.md` §8 |
| 11 | **Regression, integration, end-to-end tests** | **PASS** | **203 passed, 1 failed in 1713.96s** over all of `tests/` (`*-64-full-suite-after-replay.log`), up from 170/1 — **33 new tests this session**, including 12 mechanical causality tests for the replay. The single failure remains the pre-existing CT-3 jump-density check, now quantified: `assert 0.0909 >= 1.0` on EXIDEIND (2,475 bars, ~33 trading days, 3 negative jumps) — **0.09 negative jumps per symbol-day against a structural floor of 1.0**. Workstream D classifies this as genuinely insufficient jump density in the real intraday data, not a code defect; see `BLOCKER-TRIAGE.md` D-1. **Updated 2026-10-14: 220 passed, 1 failed, 2 xfailed (223 total, ~14m04s)**, up from 207/1/2 — **16 further tests**, including 13 fusion-learning leakage tests. Run in **three exhaustive, non-overlapping foreground chunks** because two single-process attempts were stopped by the harness on low system memory; the chunk totals reconcile against the 223-test collection count exactly. `*-100-suite-COMPLETE-chunked.log` carries the auditable arithmetic. The single failure remains the deliberately-preserved CT-3; both xfails are `strict=True` pins on open specification questions. |
| 12 | **Documentation matches implementation and evidence** | **PASS, after corrections** | Three prior evidence documents carried claims measured to be wrong; all three now carry superseding banners pointing at the newer measurement (§3 below). **Two findings 2026-10-13.** (a) `preregistration.json` **does not exist** (`verify()` returns `(False, '')`) and would hash over 20 configurations, so the open FR35 and event-count questions are **free to settle today** and invalidate every `EvaluationRow` the moment that file lands — D5(d) freezes it before the first AUC. (b) **A prior evidence document is wrong and is now superseded:** `FR35-CONFIG-COUNT-CONFLICT.md` treated 20 as a defect against 14 and recommended restricting Table A to 8. SPEC FR35 `[v2]` line 243 reads *“Table A (7 subsets × 2 reconciliation modes…) and Table B (3 subsets × 2 modes…)”* = 14 + 6 = **20**, so the existing enumeration is **SPEC-correct and that fix must not be applied**. The one genuine ambiguity is Table B's fold count (SPEC: the 2 pre-2015 epochs; ARCHITECTURE D5(b): all 6). `BLOCKER-TRIAGE.md` §D-2 |

**Score: 5 PASS, 4 FAIL, 2 PARTIAL, 1 NOT YET VALIDATED.**

*Three changes on 2026-10-13, all in the same direction because the evidence went that way, not because the bar moved:*

* *Criterion 10: NOT YET VALIDATED → **FAIL**. Not reclassified to make the matrix look decided — it was measured, and it fails.*
* *Criterion 6: FAIL (1 of 3) → **FAIL (0 of 3 fully)**. Pillar 1 is untestable for the primary objective; Pillar 2's fusion input is not the specified quantity.*
* *Criterion 5: PASS → **PARTIAL**. The integration contracts genuinely hold — types, D2 masks, CT-4/5/7/9 — but the fusion path reads `λ₁/N` where SPEC FR18 specifies `SCA_t`, and that is a conformance failure, not a variant.*

SERAPH is a reproducible, causally-correct, well-tested research pipeline whose
**core scientific claim is not established**: the combined system has not been
shown to add value for systemic-risk detection, and it has no advance-warning
capability.

---

## 2. Statistically established, under calibrated nulls

Short list, because it is short. Everything here survived a null that respects
the autocorrelation and the six-event sample size.

| finding | evidence |
|---|---|
| `dd_accel` and `rv_accel` detect FR32 crisis windows | survive **Holm across all 15 comparisons** (p = 0.0007, 0.0020) under two independent nulls. `DETECTION-CALIBRATION.md` §2 |
| The Hamilton estimator recovers known regimes | occupancy dev 0.000, transition-diagonal dev 0.001–0.003, **path accuracy 1.0000**, BIC picks the true K in both directions. `HAMILTON-REGIME-SUPPORT.md` §4.1 |
| NSE daily (RV, AR, BAS) contains no identifiable discrete regimes | AAFT surrogate null mean **2.147 ± 0.202** vs real 2.020 — real sits 0.63 sd *below* the no-regime mean |
| A ≥1.0–1.5 sd clean lead signal is absent from the corpus | power 85–98% to detect one; nothing produces one |
| FR16 trace identity | `max|trace − N| = 2.84e-13` |

Two caveats on the first row: T1 is partly tautological for volatility-derived
signals (FR32 crisis windows *are* high-volatility windows), and both survivors
are acceleration measures, so neither is a systemic-risk construct in itself.

---

## 3. Claims withdrawn or downgraded this session

Preserved here so a fresh session does not re-cite them.

| claim | where | now |
|---|---|---|
| "the estimator is exonerated by the control" | `HAMILTON-UNAVAILABLE-DECISION.md` §2 | **WRONG.** Control was ~5 switches in 3,000 days and passed while the estimator was broken |
| "the NSE daily feature space supports at most two regimes, not three" | same, §3 | **WRONG.** EM-bug artefact. Post-fix 43/25/32 occupancy; two states fare *worse* than three |
| nesting violations caused by multi-start logic | same, §2(a) | **Measurement right, diagnosis wrong.** Cause is the TVTP uniform start value |
| "AUC +0.137 … the measurable incremental detection value" | `STRESS-PILLAR-DECISION.md` §3 | **NOT ESTABLISHED.** Both values inside their nulls on the 2017+ span |
| "Contemporaneous detection IMPROVED and measured" | same, §6 | **NOT YET VALIDATED** |
| likelihood "identical" across the C7 shape fix | my own statement earlier this session | **Over-stated.** Differs by a fixed 0.009754-nat initialisation term, constant for n = 300…20,000 |
| `rv_level` T1 AUC 0.7698 | earlier session | already corrected to 0.6098; **additionally not significant** (p 0.11/0.10) |

---

## 4. Approval gates — stated, not crossed

### NEW 2026-10-14 — the objective-scope decision

The project has now tested its stated objective **O5 (regime-conditional fusion
for advance warning)** at every layer, with calibrated nulls at each, and the
result is negative at all three:

| layer | result |
|---|---|
| **architecture** | 5 fusion designs, 4 false-alarm budgets, 2 Pillar 2 quantities → 0 warnings (`FUSION-ARCHITECTURE.md`) |
| **mechanism** | escalation on a resolving scale (D′) → 0 of 5 (`FUSION-ARCHITECTURE.md` §5b) |
| **inputs** | 19 inputs, 0 classify as pre-onset, all 19 below their own null (`PREDICTIVE-INFORMATION-AUDIT.md`) |

Meanwhile the **detection** objectives are well supported: `semivar_20`
separates crisis windows at **+2.138σ** and `vix_ratio_60` at **+4.187σ**, and
O3's spectral monitoring is operational at 29/29 acceptance.

**The decision, which is not this analysis's to make:** whether SERAPH is
re-scoped around contemporaneous systemic-risk *monitoring* — with advance
warning recorded as tested-and-not-achieved rather than pending — or whether
new data acquisition is funded to pursue O5 (see
`PREDICTIVE-INFORMATION-AUDIT.md` §7 for the ranked acquisition candidates and
their costs). **Owner: whoever owns SPEC §2's objectives.** Nothing was
re-scoped here and O5 remains in the specification as written.



None of these was performed.

| gate | what it needs | why it is blocked |
|---|---|---|
| **`PILLAR_ORDER` slot-3 rename** | `seraph/shared_types/core.py:54-55`, ask-gated. 16 files, 60 references | `mask[2]=True` from `stress_emission` could imply Hamilton ran. Contained by distinct artefact ids; evidence does not justify a 4th pillar |
| **Hamilton state count** | FR20 ("three-state"), FR23 (`LSD = ξ₂ + 2ξ₃`), FR24, O4 acceptance, `HamiltonDetail`/`Simplex3` | **No amendment requested** — the evidence supports neither 2 nor 3 regimes |
| **Persisting a full-span CSRS** | A `CalibrationConfig` field encoding the span, or a convention that span is part of artefact identity | Same `weights_artefact_id` as the 2017+ run ⇒ would overwrite it, and values genuinely differ (Kalman is recursive). Driver now refuses `--write --full-span` |
| **FR35 configuration count: 20 vs 14** | C10 owner's reading of ARCHITECTURE D5(b). `configuration_list()` returns **20**; D5/D5(b)/D5(c)/D5(d)/R4 and the module's own docstring all say **14** | `(rmt)`, `(hamilton)`, `(rmt,hamilton)` are duplicated into Table A at `folds=4` when D5(b) assigns them 6. **Must be settled before `preregistration.json` is committed** — D5(d) freezes it thereafter and results under a wrong list are unreportable. Not fixed; `FR35-CONFIG-COUNT-CONFLICT.md` |
| **Kite token for 4 uncovered symbols** | Interactive login (`MTARTECH`, `INDUSINDBK`, `CGPOWER`, `POLICYBZR`) | Human action; coverage stays 91/95 |

---

## 5. What would move the needle, in order

**Rewritten 2026-10-14. The two items that previously headed this list are now
refuted by evidence gathered since, and are retained below as withdrawn rather
than deleted.**

### ~~1. More onsets~~ — WITHDRAWN

Previously: *"the binding constraint on criteria 8, 9 and 10, and nothing else
comes close."* **Refuted twice.**

* Workstream B measured the integral timescale of `rv_t_yz` at **770 sessions**:
  the 5,363-session grid holds ≈**7 effectively independent realisations**, six
  nominal onsets give **N_eff ≈ 5**, and nine additional defensible episodes buy
  roughly **one** effectively independent event. The 0-of-N upper bound first
  falls below the no-skill rate at **N = 20**, which the exogenous record cannot
  reach. `EVENT-COUNT-LIMITATION.md`
* The input audit then showed there is nothing for more events to measure: 0 of
  19 inputs move before onset. More events of the same kind would estimate the
  same absence more precisely.

**Sample size governs how precisely a null result is stated; only effect size
governs whether the result is null.** The binding constraint is effect size.

### ~~2. FR30 under leave-one-epoch-out~~ — WITHDRAWN

Previously: *"Equal weights demonstrably dilute the best input."* That was a
statement about **T1** AUC and does not transfer to advance warning.
**Refuted directly** by the pre-registered fusion experiment: learned weights
have 90% bootstrap intervals of **mean width 0.983 on a [0,1] scale**, each fold
crowns a different pillar, and under the FR18 input learned weights **lose** the
equal-weight baseline's only warning. **FR30 run on six events should be
expected to make things worse**, which is now a concrete prediction the evidence
supports rather than a worry. `FUSION-ARCHITECTURE.md`

### The current list

1. **New data with genuine pre-onset content.** The only route that could change
   the conclusion, and the audit narrows what qualifies. Ranked with costs in
   `PREDICTIVE-INFORMATION-AUDIT.md` §7: option-implied **skew and term
   structure** (not the VIX *level*, which is measurably lagging: −0.613σ before,
   +2.544σ after); **funding/liquidity spreads** (absent — `rbi_repo_rate` is 0
   non-null), subject to a publication-delay audit since a weekly series lagged
   two weeks cannot serve a 5–15 day lead window; and **FII/DII flow**, which
   must be acquired from scratch because `flow_aggregates` holds **one row**.
2. **Cross-market replication (O9/FR37–38).** The only route that adds genuinely
   *independent* realisations rather than more onsets on the same ~7 blocks.
   Caveat measured by Workstream B: 10 of 15 candidate onsets are global and
   would be common to any second market, so only ~5 are domestic.
3. **Shorten Hawkes's refit cadence for evaluation** (`CRISIS-REPLAY.md` gate 2).
   Pillar 1 is currently **untestable** for the primary objective — worse than a
   negative result, and fixable at the cost of compute alone.
4. **Fix the alert scale** (gate 1) — for interpretability, **not for warning**.
   D′ is the direct evidence that the rank scale is not what blocks advance
   warning (`FUSION-ARCHITECTURE.md` §5b), so it must not be proposed as a route
   to it. 57–62%-of-days amber nonetheless makes every operational statistic
   unreadable.
5. **A Kalman filter-consistency check, to close criterion 10 without inventing a
   probability.** CSRS is deliberately not a probability, so no reliability
   diagram is meaningful. What *is* testable is whether C8's uncertainty is
   self-consistent: the normalised innovation squared,
   `ν²/(P⁻_jj + R_j(Δ))` per available pillar, should average 1 and distribute as
   χ²₁. Over- or under-dispersion would mean FR29's intervals are wrong by a
   measurable factor. `ReconciledState` exposes `x_hat` and `P` but not the
   innovations, so this needs `run_csrs_research.py` instrumented to record the
   prior `x_hat`/`P` with each emission and its `R_j(Δ)`. Scoped, not started.

**Not useful: more candidate features from held data.** **Nineteen** series have
now been screened with two calibrated nulls; all 19 sit below their own
no-signal 95th percentile and the multiplicity cost already exceeds what another
held-data candidate could demonstrate at six events.

**Not useful: another fusion search.** Five architectures, four false-alarm
budgets and two Pillar 2 quantities are excluded, plus D′ on a resolving scale.

---

## 6. The causal walk-forward, completed

Both the 14-block run and its stage-2 checks finished — full detail in
`HAMILTON-CAUSAL-POSTFIX.md`. Headline:

| metric | pre-fix | post-fix |
|---|---|---|
| converged blocks | 11/14 | **14/14** |
| nesting violations | 6/14 | **2/14** (blocks 10, 11 only) |
| truncation invariance | bitwise exact | **bitwise exact**, max \|Δξ\| = 0.000e+00 over 3,024 cells |
| near-absorbing dates | 53.0% | **38.6%** |
| max \|transition param\| | 44.23 | **11.59** |
| NFR17 causal separation | 0.269σ | 0.291σ — still ≪ 3σ |
| causal occupancy | — | 70.9 / 10.0 / 19.1, none below 10% |

All 6 original violations trace to exactly two causes, both measured:

* **4 of 6 — a sub-optimal restricted seed. FIXED.** The warm start fitted the
  restriction through the non-TVTP path; the nesting check fits it as
  intercept-only TVTP. The same restricted model, two optimisations, **312 llf
  apart** on block 6. `_tvtp_start_from_intercept_only` now seeds from the
  restriction in its own parameterisation: blocks 6 and 8 moved to **+15.13** and
  **+23.09** (from −577.18 and −1,276.02).
* **2 of 6 — the converged-only selection rule. SURFACED, not changed.** On
  blocks 10 and 11 the optimiser *found* points satisfying nesting
  (39,392.03 vs a restriction of 39,378.13; 41,883.88 vs 41,866.68) and discarded
  them for failing BFGS's convergence test, returning candidates 873 and 1,179
  llf lower. `fit()` now emits a `PARTIAL_COVERAGE` warning with
  `discardedLlf`/`selectedLlf`/`convergedStarts`, so this can never again be
  silent. **Whether to relax the rule is a judgement about what counts as a valid
  optimum and is left to the C7 owner** — it changes what `fit()` may return and
  should not be decided from two blocks.

**Also closed: AMENDMENT-05 §2.1**, previously unresolved because the stage-2
probe crashed on `_em_iteration` returning a tuple. Measured correctly: under
TVTP, EM moves the transition block by **exactly 0.000000e+00** while moving
means by 1.50e-02. Claim confirmed.

## 7. Nothing in flight

All runs completed. Final test state: **170 passed, 1 failed** across `tests/`
(`*-30-final-full-suite.log`), the single failure being the pre-existing CT-3
jump-density check in C4/Hawkes territory, unrelated to this work.

**Cost note carried forward:** offering both warm starts roughly quadruples
`fit()` — the four re-tested block pairs took **999–1,278 s** each. Acceptable at
Hamilton's daily cadence with a 252-session refit interval; **not** acceptable at
bar frequency, and the first thing to revisit if C7's cadence ever changes.

None of the optimiser work reopens criterion 6. A perfectly identified TVTP fit
would still have to clear the surrogate null, and at **0.291σ** causal separation
it is nowhere near.
