# SERAPH — independent audit, benchmark and recovery assessment

**Audit date 2026-10-14. Canonical worktree: the main checkout at
`evidence/pre-arya-experimentation`, HEAD `f3eaac8`, 149 uncommitted paths.**
Two locked worktrees are owned elsewhere and were not touched by this audit:
`c11-fr43-fr49` (FR43/FR49, at `f79299d`) and `c2-macro-ingestion` (at
`f79299d`, 6 uncommitted). All `docs/evidence/` reports live in the canonical
checkout only.

Nothing was committed, merged or pushed. No specification, pre-registration
artefact or crisis label was changed. No test was weakened. `preregistration.json`
remains deliberately absent.

---

# Deliverable A — Independent diagnosis

## What SERAPH is today

**A rigorously-validated negative result, wrapped in a working but
incompletely-integrated pipeline.** That is not a dismissal — the rigour is the
asset, and it is unusual. The system:

* ingests 8,023,206 daily rows (1995+) and 18,781,302 intraday bars (2015-02+);
* computes three pillars causally, verified in source, with 12 mechanical
  leakage tests that perturb the future and assert the past is unchanged;
* fuses through a real Kalman reconciler and a pure scoring function, 5,363
  ticks with 0 failures;
* carries 223 tests, **220 passing, 1 deliberately-failing contract, 2 strict
  `xfail` pins on open specification questions**.

And it has **not demonstrated advance-warning capability** at any horizon from 5
to 30 trading days, at any false-alarm budget from 0.5 to 4 per year, under
either Pillar 2 quantity, with any of five fusion architectures.

## Why it has not demonstrated advance warning

**Because none of the available inputs contains measurable pre-onset
information.** This has now been established at four successive layers, each
with calibrated nulls, and the conclusion is the same at every one:

| layer | what was tested | result |
|---|---|---|
| **inputs** | 19 held features, classified by *when* they move | **0 classify as BEFORE** (14 DURING, 5 AFTER); all 19 below their own no-signal 95th percentile; smallest p **0.0630** — nothing reaches even an *uncorrected* 0.05 |
| **Pillar 1's bar-frequency quantity** | conditional intensity `λ_t`, never previously screened | **+0.045σ** pre-onset, DURING class, T3 AUC 0.5496 vs own null p95 0.5697 |
| **architecture** | 5 fusion designs × 4 budgets × 2 Pillar-2 quantities | **0 warnings**; learned weights' 90% bootstrap intervals of mean width **0.983 on a [0,1] scale** |
| **mechanism** | escalation on a *resolving* raw scale (D′) | **0 of 5** — so the rank-scale saturation was not the blocker either |

**And it is not a SERAPH-specific failure.** This audit tested the single
best-documented predictive finding in the systemic-risk literature — Giglio,
Kelly & Pruitt's result that *financial-sector* equity volatility predicts macro
tail quantiles while non-financial volatility does not — on SERAPH's own corpus,
pre-registered, from held data. **It also failed**: 0 of 5 features classify as
BEFORE, all 5 below their own null, and the sharpest relative test
(`fin_minus_nonfin`) runs **backwards** at **−1.027σ** before onsets and
**+1.191σ** after. See §Deliverable F.

## The largest bottleneck

**Not the models, not the fusion layer, not the code. The information content of
daily Indian equity price data at a 5–15 day horizon, evaluated on six events.**

Two measurements pin this independently of any model:

1. **Effect size.** The largest pre-onset separation observed across 25 screened
   features is **+0.432σ** (`vix_ratio_60`). The T3 test's measured minimum
   detectable effect is ~1.0 sd (power 75–85% against both a step and a
   75-session ramp); at 0.5 sd power is 47–50%. **Every candidate sits below the
   threshold at which this test can see anything.**
2. **Independent sample.** The integral timescale of the pillar features is
   **770 sessions**, so the 5,363-day grid holds **≈7 effectively independent
   realisations** and six nominal onsets give **N_eff ≈ 5**. Nine additional
   defensible Indian episodes would buy roughly **one** more. The 0-of-N upper
   bound first falls below the no-skill rate at **N = 20**, which the exogenous
   record cannot reach.

**Sample size governs how precisely a null result is stated; only effect size
governs whether the result is null.** The binding constraint is effect size.

## What has genuine value

Ranked by what a sceptical examiner would actually credit:

1. **The evaluation methodology.** Two calibrated null families (relocation,
   measured type-I **8% at nominal 5%**; AAFT preserving the exact marginal),
   Holm correction with the comparison count declared in advance, permutation
   floors reported, block bootstrap at the *measured* dependence scale,
   pre-registration hashed before first fit, power measured against multiple
   injected signal shapes. **This is better than much of the published
   literature**, which an arXiv survey of the field describes as reporting
   strong in-sample accuracy while "few test how much advance warning they give
   on held-out data."
2. **The causal-correctness discipline.** Truncation invariance bitwise exact
   (max |Δξ| = 0.000e+00 over 3,024 cells); a genuine look-ahead leak caught by
   a type contract (the Diwali Muhurat 18:55 refit offered to a 15:30 decision);
   leakage tests written as falsification attempts.
3. **The negative result itself.** A properly-powered, properly-nulled
   demonstration that three named systemic-risk families carry no pre-onset
   information on this corpus is a publishable finding and a legitimate
   final-year result.
4. **Two real estimator defects found and fixed**, one worth **16,573
   log-likelihood** (C7's EM shape bug), proved by evaluating the likelihood at
   the generating parameters.
5. **The record of withdrawn claims.** Superseded conclusions carry banners
   rather than being deleted — including three of this project's own prior
   headline claims.

## What should stop immediately

* **Fusion search.** Five architectures, four budgets, two Pillar-2 quantities
  and D′ are excluded. A sixth attempt is tuning against six known crises.
* **Threshold tuning.** Swept over five quantile levels with the null recomputed
  at each: **1 of 50 cells reaches p ≤ 0.05 where chance predicts 2.5**.
* **Screening further transforms of held price data.** Twenty-five features now,
  all DURING or AFTER, all below their own null. The multiplicity cost already
  exceeds what another held-data candidate could demonstrate at six events.
* **Pursuing more Indian onsets.** Measured to buy ≈1 independent event per nine
  added.
* **Describing the CSRS alert as meaningful.** Amber is crossed on **57–62% of
  all days**.

## The most promising path forward

**Narrow the production claim to contemporaneous monitoring, which the evidence
supports, and pursue advance warning as a single clearly-scoped research track
against new data with a prior mechanistic reason to lead.** Detection is strong
and measurable (`semivar_20` **+2.138σ**, `vix_ratio_60` **+4.187σ** in crisis
windows; O3's spectral monitoring operational at 29/29 acceptance). The
advance-warning claim should be stated as *tested, bounded and not achieved*
rather than pending — which is a defensible scientific position, not a
concession.

---

## Severity-ranked defect and risk register

Severity: **S1** = invalidates a published claim or silently corrupts output ·
**S2** = materially wrong, contained · **S3** = conformance or hygiene.

| # | sev | defect | location | consequence | evidence | fix |
|---|---|---|---|---|---|---|
| 1 | **S1** | **Unmeasured sector reads as *cleared*.** FR14 emits `flag="none"` when `base <= 0` (`ratio = realised/base if base > 0 else 0.0`), byte-identical to measured-and-quiet. Through `normalise_flag_source` it became `covered: true`. | `seraph/pillars/hawkes/engine.py` `sector_flags`; consumed in `decision_support/portfolio.py` | A sector nobody measured reported as clean in the FR43 overlay — inverts the component's purpose | found this audit | **FIXED** in the C11 worktree: `measured_flag_source()` screens unmeasured entries → `covered: false` + PARTIAL_COVERAGE. 30 tests. |
| 2 | **S1** | **FR18 non-conformance.** SPEC FR18 specifies Pillar 2's sub-score as `SCA_t`; `rmt_emission` standardises `λ₁/N`, named nowhere in FR16–FR19, while validated `rmt_output.sca_t` is never read. | `seraph/orchestration/adapters.py:rmt_emission` | The quantity in use is **anti-predictive**: T1 AUC **0.4282** vs `SCA_t`'s 0.6623; era-controlled crisis separation −0.3784σ (1/6 epochs) vs +0.5028σ (5/6) | `CRISIS-REPLAY.md` §5c | **Approval-gated** (C6/A). Changes every CSRS ever computed. Recommend sequencing after defect 4. |
| 3 | **S1** | **Lee–Mykland threshold mis-scaled.** `extract_jumps` feeds a `μ₁`-corrected statistic to an uncorrected-`σ̂` critical value → `1/c = 1.2533×` too strict. Thin Gumbel tail ⇒ **~3 orders of magnitude in level**: effective α ≈ **1.0e−05**, **975× tighter** than documented 0.01. | `seraph/features/jump_extraction.py` | 0 rejections in 400 Brownian-null samples; power at 5σ 0.250 vs 0.620 | `BLOCKER-TRIAGE.md` D-1b | **Pinned, not patched** (`strict=True` xfail). Fixing without amending SPEC FR10 — which quotes the *uncorrected* 0.087 density — would put code and spec in contradiction. |
| 4 | **S1** | **Alert scale is meaningless.** Absolute constants (`PROVISIONAL_AMBER = 0.5`) applied to an FR28 ECDF-rank composite. | `seraph/fusion/score.py:35–36` | Amber crossed on **57–62% of all days**; BSS **−11.64**; ECE **0.575** vs a 3.36% base rate. Also made candidate D's escalation arms saturate at exactly 1.0, so the design could not be fitted. | `CRISIS-REPLAY.md` §5, `FUSION-ARCHITECTURE.md` §5 | **Approval-gated** (D/C9). Causal quantile thresholds; already prototyped (4–12% of days). **Fix for interpretability — D′ proves it is not a route to warning.** |
| 5 | **S2** | **Fitted Hawkes parameters never persisted.** `hawkes_output.alpha_beta` is a declared column, **NULL on every row**. | `scripts/write_hawkes_production.py` | `λ_t` cannot be reconstructed from the database at all; this audit had to rebuild it from SPEC-quoted constants | `THREE-CHECKS-RESULTS.md` §1 | Cheap. Owner B (C5). |
| 6 | **S2** | **`validation_results` PK omits `table_id`**, which is `NOT NULL`. Under ARCHITECTURE D5(b)'s 6-fold Table B, the three subsets in both tables collide. | `seraph/store/schema.sql:206` | **24 of 128 `EvaluationRow`s silently overwritten**; 0 under SPEC's 2-fold reading | `BLOCKER-TRIAGE.md` D-2 | Free now — no writer exists. **Blocks the ablation.** |
| 7 | **S2** | **No symbol→sector map anywhere.** `universe_snapshots` holds only symbol lists; `daily_prices` has no sector column. | schema-wide | FR14 sector micro-flags can never have production inputs; no sector-split feature is computable without a hand-specified list | found this audit | Acquire or declare a mapping. Blocks FR14 and FR22. |
| 8 | **S2** | **CT-3 jump-density floor unreachable.** 0.0865 negative jumps/symbol-day vs a floor of 1.0 — **11.6× short**, best single symbol 2.8× short. | `tests/contract/test_ct3_jump_sufficiency.py` | The only failing test. SPEC FR10 `[v4]` **already supersedes** the design this floor guards, quoting this very number | `BLOCKER-TRIAGE.md` D-1 | **Left failing, unmodified** (71 insertions, 0 deletions, docstrings only). Retiring the gate is C4/C5's call. |
| 9 | **S3** | **Documentation asserted unverified coverage.** `DATA-ACQUISITION.md:106` states *"India VIX starts Nov 2007. Confirmed."* Independent search contradicts: launch 2008, real-time ~2009–2010, futures Feb 2014 — close to the ingested 2014-05-15 start. | `docs/DATA-ACQUISITION.md` | A load-bearing coverage claim was wrong; a backfill extends coverage to **5 epochs, not 6** | `THREE-CHECKS-RESULTS.md` §3 | Downgrade to unverified. Owner: OQ5. |
| 10 | **S3** | **A prior evidence document recommended a SPEC violation.** `FR35-CONFIG-COUNT-CONFLICT.md` treated 20 configurations as a defect and proposed cutting Table A to 8. SPEC FR35 line 243 gives 7×2 + 3×2 = **20**. | `docs/evidence/` | Applying it would have frozen a wrong pre-registration hash | verified against SPEC this session | **Superseding banner added**; measurements retained. |
| 11 | **S3** | **Four intraday data defects**; 10,368 off-session bars (0.0552%), incl. 30 **impossible** post-close bars (2021-02-24) and two Muhurat sessions present in `intraday_bars` but **absent from `daily_prices`** — the corpora disagree on whether a trading day exists. | `intraday_bars` | **No published result invalidated** (0 of 4 fall in any FR32 crisis or lead window); full-span statistics carry 0.30–1.06% contamination | `BLOCKER-TRIAGE.md` D-4 | Needs a DB write or C2's ingestion. |
| 12 | **S3** | **Six of eight macro covariates are 0 non-null** (`g_t`, `g_t_sector_weighted`, `rbi_repo_rate`, `bank_credit_growth_yoy`, `inr_twi`, `brent_price`); `flow_aggregates` holds **1 row**; `tariff_events` **0**. | `macro_covariates`, `flow_aggregates` | **O8/FR22 and FR45 are unvalidatable on held data** | `PREDICTIVE-INFORMATION-AUDIT.md` §2 | Acquisition, not a fix. |

**Risks that are not defects.** `N_eff ≈ 5` is a property of the world, not a
bug. `tariff_2026`'s label is `PROVISIONAL` (SPEC OQ3 open) and three of the
five pre-onset warnings seen anywhere fall on it. Hawkes's 5-session refit
cadence is a *documented* trade-off (OOS NLL/bar 0.1325 at 500 days vs 0.2322 at
60), not an error — but it leaves **≤3 observations in FR32's 15-day lead
window**, making Pillar 1 standalone `UNTESTABLE`.

---

# Deliverable B — Quantified maturity and benchmark assessment

## Rubric and anchors

Scores are 0–100 against explicit anchors. **0–20** absent or failing ·
**21–40** present but materially deficient · **41–60** works with known gaps ·
**61–80** sound, some gaps · **81–100** strong, independently evidenced.

| # | dimension | score | confidence | evidence and reasoning |
|---|---|---|---|---|
| 1 | Mathematical / statistical validity | **70** | high | Estimators correct and now ground-truth validated: C7 recovers known 2- and 3-regime series at **path accuracy 1.0000**, BIC picks true K both directions. Two real defects found and fixed (one worth 16,573 llf). Deducted for three live defects: FR18 conformance, Lee–Mykland 1/c, FR14 `base<=0`. |
| 2 | Data quality and historical coverage | **35** | high | `daily_prices` 8.0M rows 1995+ is solid. Against that: Hawkes 2017+ at ~50 obs/yr; causal Hamilton 2013-01-14+; VIX 2014-05-15+; **all three pillars simultaneously available on 468 days**; 6 of 8 macro covariates empty; flows 1 row; no sector map; no options data. |
| 3 | Reproducibility and causal correctness | **86** | high | **SERAPH's strongest dimension.** 12 mechanical leakage tests; truncation invariance bitwise exact; pre-registrations hashed *before* first fit (`3d8e8de3…`, `26910c6a…`, `95acc3a2…`); every experiment logged with commands and real exit codes; superseded claims banner-marked not deleted. |
| 4 | Out-of-sample advance-warning performance | **5** | high | **0 pre-onset warnings, 6 epochs × 5 horizons × 4 budgets × 2 Pillar-2 quantities.** Nothing distinguishable from chance (25 features, lowest p 0.0630). Not 0 because the *measurement* is sound and bounded, so "no demonstrated capability" is itself a validated finding. |
| 5 | False-alarm control and alert usefulness | **18** | high | Amber on **57–62% of days**; **7.9 false alarms per true alarm**; episode precision **0.112**. The measurement machinery is good; the alert is unusable. |
| 6 | Probability calibration | **10** | high | Brier **0.4292**, **BSS −11.64**, ECE **0.575** vs a 3.36% base rate — ~12× worse than always predicting the base rate. Scored above 0 only because it is **measured, and correctly not claimed** as a probability. A scale error by construction: FR28 ranks are ≈U[0,1]; **FR30 cannot fix it**. |
| 7 | Robustness and generalization | **22** | high | Robust *in the right direction*: the negative survives 5 threshold levels, 3 injected signal shapes, both Pillar-2 quantities and a block bootstrap. But learned weights span L1 **1.7–1.9** of a 2.0 maximum; **N_eff ≈ 5**; zero cross-market replication. |
| 8 | Production integration, observability, operational reliability | **42** | medium | End-to-end 5,363 ticks, 0 failures; D2 availability mask; typed warning codes; idempotent upserts verified; artefact-id collision caught *before* it overwrote evidence. Against: nothing calls the FR43 overlay; `validation_results` 0 rows; `alpha_beta` unpersisted; alert semantics broken; 1 failing contract. |
| 9 | Independent validation and evidence quality | **78** | high | Two null families, Holm with declared comparison counts, permutation floors, measured power, self-corrections recorded (I corrected my own overstatement on sub-chance performance and a wrong uniform reading of the T1 bootstrap). Deducted because three evidence documents carried wrong claims until this session corrected them (defects 9, 10, and the "macro entirely empty" claim). |

## Separate maturity estimates — deliberately not aggregated

| maturity | estimate | basis |
|---|---|---|
| **Engineering maturity** | **~58 / 100** | Runs end to end, 220/223 tests pass, strong causal hygiene; held back by integration gaps and four S1/S2 defects. |
| **Predictive-evidence maturity** | **~5 / 100** | Nothing demonstrated at any horizon, budget, architecture or input. Rigorously so — which is why this is not 0. |
| **Operational readiness** | **~22 / 100** | Pipeline executes reliably; the alert it produces is not decision-grade (60%-of-days amber, 7.9 FA per true alarm), and the overlay is unwired. |
| **Research originality and project value** | **high, and the real asset** | A properly-powered, properly-nulled negative across four layers plus an independent replication failure of the literature's best-documented finding. |

**I decline to give a single aggregate number, and the reason is substantive:
these dimensions are not substitutable.** An 86 on causal correctness cannot
compensate for a 5 on predictive performance — a perfectly reproducible system
that does not predict anything is reproducibly useless for its stated purpose.
Any weighted mean would obscure precisely the fact that matters.

## Benchmark against reference systems

**I will not state a percentile against "risk engines" generally.** No
defensible comparison population or common evaluation dataset exists, and the
systems below measure *different things on different targets at different
horizons*. Claiming "better than N%" would be the kind of unsupported number
this audit exists to prevent.

| reference class | task / target | horizon | what the evidence shows | how SERAPH compares |
|---|---|---|---|---|
| **Simple vol / drawdown / semivariance baselines** | contemporaneous stress | same-day | `semivar_20` **+2.138σ**, `rv_20` +1.499σ in crisis windows; `semivar_20` T1 AUC 0.7832 | **SERAPH loses on detection**: 2-pillar CSRS 0.5218, RMT alone 0.4283. And at T3 the baselines also fail (`semivar_20` **0/6**, p = 1.0000). |
| **Giglio, Kelly & Pruitt (2016, JFE)** — 17–22 systemic-risk measures | lower-tail quantiles of future **macro** outcomes | quarterly | Combined index has out-of-sample predictive power *"despite the individual failure of many measures"*; **financial-sector** equity vol predicts, non-financial does not | **Directly tested here and it fails on this corpus** (Deliverable F): 0/5 BEFORE, `fin_minus_nonfin` **−1.027σ** pre-onset. Their target and horizon differ materially from SERAPH's. |
| **CoVaR / MES** | institution-level systemic exposure | contemporaneous | Danielsson et al.: *"a high degree of model risk so that the signal they produce is highly unreliable"*; ΔCoVaR's time-series correlation with VaR *"almost 1"* | Not comparable — institution-level, not market-wide onset. Notably, the established measures SERAPH might be benchmarked against are **themselves contested**. |
| **SRISK** | capital shortfall; macro downturns | quarters | ESRB: SRISK increases predict falls in industrial production, **stronger at longer horizons**. Acharya et al. (1927–2023): **capital-structure measures predict bank failures better than co-movement measures** | **A structural diagnosis for SERAPH**: all three pillars are *co-movement/dynamics* measures — the family the literature finds weakest for prediction — and SERAPH holds **no balance-sheet data** from the family it finds strongest. |
| **Variance risk premium / option-implied tail** | aggregate equity returns | up to a quarter | Bollerslev–Tauchen–Zhou (2009) and successors: VRP predicts returns at short horizons; tail-risk premium has independent content; Gao–Pan crash-fear index from short-dated OTM puts | **The best-documented short-horizon family, and SERAPH has none of it** — no options data. This is the top acquisition candidate. |
| **GARCH / DCC** | conditional vol and correlation | 1-step | Well-established, mature implementations (`arch`) | SERAPH has no GARCH baseline at all. A missing *baseline*, not a missing pillar — and its absence weakens every comparison SERAPH makes. |
| **Regime-switching / HMM** | state identification | contemporaneous | Mature; standard | SERAPH's P3 is exactly this, and its regime structure is **indistinguishable from a single-regime AR(1) surrogate** (AAFT p = 0.7143, AR(1) p = 0.9524). |
| **ML early-warning models** | crisis classification | varies | An arXiv survey notes many report strong **in-sample** accuracy while *"few test how much advance warning they give on held-out data"* | **SERAPH's evaluation is more rigorous than this norm.** Its negative result may be what the field would find if it tested the same way. |

**Defensible positioning:** SERAPH is a **research prototype with
publication-grade evaluation methodology and no demonstrated predictive
capability**. It is *not* an experimental monitoring engine yet — that requires
fixing the alert scale (defect 4) — and it is certainly not a validated
predictive system.

---

# Deliverable D — proposed SERAPH v2 architecture

**Preserves all three pillars and their provenance. Adds nothing that has not
passed `NEXT-PREREGISTRATION-DRAFT.md`.**

```
                      ┌─ P1 Hawkes ────┐   contagion / event excitation
  raw inputs ────────▶├─ P2 RMT ───────┤   cross-sectional dependence      each emits:
  (prices, intraday,  └─ P3 Hamilton ──┘   regime state                    value + variance
   macro, new feeds)                                                       + coverage flag
                                                                           + availability ts
                      ┌─ S4..Sn candidate signals ─┐  admitted ONLY via §7 protocol
                      │  (option skew/term, funding │
                      │   spread, participant OI…)  │
                      └─────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ L1  causal alignment (C8)   │  D2 mask: structural vs transient
                    │  no imputation, no zero-fill│  D4 bounded age-inflation R(Δ)
                    └──────────────┬──────────────┘  stale ⇒ widened variance, never a value
                                   │
                    ┌──────────────▼──────────────┐
                    │ L2  MONITORING score        │  ← supported by evidence TODAY
                    │  ordinal, rank-based        │     labelled "not a probability"
                    │  equal weights (retained)   │     thresholds = causal quantiles
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ L3  WARNING probability     │  ← GATED. Emits "UNAVAILABLE" until a
                    │  calibrated, or absent      │     signal passes §7. Never a rank.
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ L4  alert policy            │  GREEN/AMBER/RED on L2 quantiles;
                    │  declared expected frequency│  RED requires L3 when L3 exists
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ L5  interface               │  shows uncoveredPct, mask state,
                    │  degradation is first-class │  variance, and "L3 unavailable"
                    └─────────────────────────────┘
```

**The three decisions that matter.**

1. **L2 and L3 are separate objects with separate contracts.** The monitoring
   score is ordinal and says so; the warning probability is calibrated or
   **absent**. Today L3 emits `UNAVAILABLE` on every tick. This is the
   architectural fix for the BSS −11.64 problem: it stops a rank being read as a
   probability by construction rather than by disclaimer.
2. **No silent fallback is representable.** A missing pillar is a *structural
   absence* in the D2 mask with renormalised weights, never a zero and never a
   "healthy" default. The C11 `measured_flag_source` fix (defect 1) is this
   principle applied one level down, and the pattern generalises: **an
   unmeasured input must be absent, not clean.**
3. **Pillars keep their identity and are allowed their earned role.** P1 is a
   *contagion diagnostic contributing to the CSRS* — which is what **FR13 `[v4]`
   already says**, having been amended on a pre-registered no-skill result at
   intraday horizons. P2 is contemporaneous structural monitoring (O3, 29/29).
   P3 is a regime descriptor whose regime claim is **unavailable**. **None is
   forced into a predictive role it has not earned, and none is removed.**

---

# Deliverable E — prioritized roadmap

Ranked by demonstrable usefulness per unit of effort. **Every go/no-go is stated
before the work.**

### Phase 0 — stabilization (days, no approval)

| task | benefit | effort | acceptance | go/no-go |
|---|---|---|---|---|
| Persist `alpha_beta` (defect 5) | makes `λ_t` reconstructible; unblocks any future Pillar-1 work | S | column non-null on new rows; existing rows untouched | **GO** |
| Fix `validation_results` PK (defect 6) | prevents 24/128 silent overwrites | S | PK includes `table_id`; no writer exists yet so no migration | **GO** — but pair with the D-2 fold-count decision |
| Downgrade the VIX "Confirmed" claim (defect 9) | stops a wrong coverage fact propagating | XS | doc states verified start date | **GO** |

### Phase 1 — root cause (done; recorded here for completeness)

All four layers tested. **Complete.** No further held-data screening justified.

### Phase 2 — the only candidate signals worth building

| candidate | hypothesis | cost | go/no-go |
|---|---|---|---|
| **FBIL money-market term spread** | funding stress leads equity stress; the only candidate passing the point-in-time gate on verified evidence (**daily, published 12:45/13:45 IST, before the 15:30 decision**) | free | **GO**, after resolving the **2015-07-22** polled→transaction methodology break that sits on the epoch boundary |
| **NSE participant-wise F&O open interest** | direct measure of crash-protection *positioning*, which is what skew only proxies; free | free | **GO** — establish depth, publication time, revision policy first |
| **Option-implied skew / term structure** | best-documented short-horizon family (VRP, Gao–Pan crash-fear) | unknown; NSE price unpublished | **CONDITIONAL** — NO-GO unless pre-2015 strike-level data is confirmed; currently unverifiable |
| **Cross-market replication (O9/FR37–38)** | the only route adding *independent* realisations | L | **CONDITIONAL** — requires ≥3 genuinely *domestic* episodes; 10 of 15 candidates are global |

### Phase 3 — fusion, only if Phase 2 admits a signal

**No work authorised until a candidate passes §7.** Equal weights retained as
baseline; `NEXT-PREREGISTRATION-DRAFT.md` §8 governs.

### Phase 4 — operational integration

| task | benefit | go/no-go |
|---|---|---|
| **Alert scale fix** (defect 4) | every operational statistic becomes interpretable | **GO** — approval-gated (D/C9). **Must not be sold as a warning improvement**; D′ proves it is not |
| Wire the FR43 overlay with `uncoveredPct` | stops an exposure figure appearing without its coverage | **GATED** on a C12 `ROLE_FIELDS` decision (CT-8) |
| L2/L3 split | makes the probability claim unrepresentable until earned | **GO after approval** — architecture change, needs sign-off |

### Phase 5 — final evaluation

Untouched confirmation on `tightening_2022` + `tariff_2026`, once. **Note the
limitation now:** epoch 6's label is `PROVISIONAL`, so confirmation rests
materially on one clean event.

---

# Deliverable F — first concrete implementation

**Selected: a pre-registered test of the literature's best-documented predictive
finding, on SERAPH's data, from held data, at zero cost.** It was chosen because
it is the only remaining experiment that could have *overturned* the diagnosis
rather than confirming it, and because the alternatives all required approval or
money.

`scripts/screen_financial_sector_stress.py` (sha256 prefix `95acc3a2…`, hashed
before the first result). The 54-name financial list was fixed **by company
identity only** — banks, NBFCs, insurers, exchanges, depositories, AMCs — and
written into the file before any output existed. Coverage floor ≥20 financial and
≥100 other names per day. Log `*-120-financial-sector-screen.log`; results
`docs/evidence/signals/financial_sector_screen.json`.

**Result: negative on all three pre-registered criteria.**

| feature | BEFORE −15d | DURING | AFTER | class | T3 AUC | p_shift | p_aaft | own null p95 |
|---|---|---|---|---|---|---|---|---|
| `fin_rv_20` | −0.264 | +1.409 | +2.300 | AFTER | 0.4673 | 0.5967 | 0.5887 | 0.7031 |
| `nonfin_rv_20` | +0.209 | +1.653 | +1.771 | AFTER | 0.5287 | 0.4083 | 0.3988 | 0.7030 |
| **`fin_minus_nonfin`** | **−1.027** | +0.102 | +1.191 | AFTER | 0.5109 | 0.4398 | 0.4578 | 0.6856 |
| `fin_ratio_60` | +0.232 | **+2.077** | +1.612 | DURING | 0.5705 | 0.2974 | 0.2954 | 0.7150 |
| `fin_dispersion` | +0.152 | +0.781 | +0.230 | DURING | 0.5622 | 0.1794 | 0.1849 | 0.6122 |

**Zero BEFORE classifications. All five below their own no-signal 95th
percentile. None met the criteria.** Coverage 4,123 days 2010-01-05 → 2026-08-21,
**5 of 6 epochs** (the ≥20-financial-name floor is not met before 2010, so
`gfc_2008` is out of reach — stated, not worked around).

**The sharpest result runs backwards.** `fin_minus_nonfin` — the *relative*
measure that Giglio et al.'s claim actually concerns — is **−1.027σ before**
onsets and **+1.191σ after**. On this corpus, at this horizon, financial-sector
volatility relative to non-financial is **lowest** before crises. And
`nonfin_rv_20` (+0.209) is weakly *more* pre-onset elevated than `fin_rv_20`
(−0.264), the reverse of the published direction.

**Why this is the most valuable single result in the audit.** It converts the
diagnosis from *"SERAPH's inputs fail"* to *"the best-documented published
leading-indicator family also fails here, pre-registered"*. That makes the
negative a property of the data and target rather than of this implementation —
which is a materially stronger and more defensible claim, and it is the one a
sceptical examiner is most likely to probe.

Baseline comparison: unchanged. Nothing in `seraph/` was modified; the
production path is untouched; the 19-feature audit and all prior numbers stand.

---

# Final questions, answered directly

**1. Continue, redesign the fusion layer, or restructure?**
**Restructure the claims, not the code.** The fusion layer is not the problem —
five architectures were excluded and learned weights have 90% intervals of width
0.983, so there is nothing for a better fusion rule to combine. I would keep the
pipeline, implement the L2/L3 split so a rank can never be read as a
probability, fix the alert scale, and reclassify the headline objective. Redesign
would be motion without information.

**2. Which components are defensible, which merely implemented, which
predictive?**
*Scientifically defensible:* P2 RMT (29/29 acceptance, FR16 trace identity
`max|trace − N| = 2.84e-13`); C8's Kalman with D4 bounded noise; C9's purity;
the evaluation harness. *Merely implemented:* P1 Hawkes — correct estimator, but
**untestable** for advance warning at its own cadence and already reclassified
by FR13 `[v4]`; P3 Hamilton — the estimator is now ground-truth validated at
path accuracy 1.0000, but its **regime claim is unavailable** (AAFT p = 0.7143).
*Demonstrated predictive value:* **none. Not one component.**

**3. Best evidence-backed maturity estimate?**
Engineering ~58/100, predictive evidence ~5/100, operational readiness ~22/100.
**A research prototype with publication-grade methodology and no demonstrated
predictive capability.** I will not give a percentile against risk engines
generally — no defensible comparison population exists.

**4. The single most important reason it has not warned?**
**The inputs carry no pre-onset information.** 25 features screened, 0 classify
as BEFORE, all below their own null; largest pre-onset separation **+0.432σ**
against a measured MDE of ~1.0 sd. Everything else — fusion, thresholds, scale,
cadence — was tested and excluded as the cause.

**5. Three most promising external additions?**
(i) **FBIL money-market term spread** — the only candidate verified
point-in-time clean (daily, 12:45/13:45 IST, before the 15:30 decision);
(ii) **NSE participant-wise F&O open interest** — free, and a *direct* measure
of crash-protection positioning rather than a price proxy;
(iii) **option-implied skew / term structure** — the best-documented
short-horizon family (VRP, Gao–Pan), **conditional** on pre-2015 depth being
confirmed, which is currently unverifiable.

**6. Can these be added while preserving the pillars?**
Yes, and the architecture is Deliverable D. The three pillars keep their
contracts and emit value + variance + coverage + timestamp. New signals enter as
**sibling modules at the same level**, never inside a pillar, and only after
passing §7. P1/P2/P3 remain the three named pillars in `PILLAR_ORDER`.

**7. Enough history for a learned fusion model?**
**No, and this is measured, not asserted.** Integral timescale **770 sessions** ⇒
**N_eff ≈ 5** independent events for 3 weights plus a threshold. The learned
weights' 90% block-bootstrap intervals span **almost the entire simplex (mean
width 0.983 on [0,1])**, near-maximal at *every* block length from 21 to 770 —
so this is not an artefact of a conservative dependence assumption. Only **1 of
4 development folds** has ≥10 training positives.

**8. What would you implement first?**
**The alert-scale fix** (defect 4), because every operational statistic is
uninterpretable until amber means something other than "three days in five" —
and it must be shipped with the explicit caveat that **D′ proves it is not a
route to advance warning**. Second, the two free Phase-0 items (`alpha_beta`
persistence, `validation_results` PK) since both prevent silent data loss.

**9. Realistic short-term improvement vs what stays unproven?**
*Demonstrable in weeks:* an interpretable monitoring alert at a declared
frequency; a defensible contemporaneous stress score (`semivar_20` +2.138σ);
coverage-aware reporting; the FR18 conformance fix worth ~1σ of correctly-signed
detection separation. *Unproven and likely to stay so on held data:* any advance
warning, any calibrated probability, any claim that fusion adds value.

**10. What result would make you conclude advance warning is not achievable
here?**
**Two acquired inputs, each with a prior mechanistic reason to lead, both
failing `NEXT-PREREGISTRATION-DRAFT.md`.** We are now **one of two** along that
path: the financial-sector test (Deliverable F) was the first, pre-registered,
and it failed. One more — the FBIL term spread is the natural candidate — and the
honest conclusion would be that daily Indian equity data does not support
5–15 day advance warning at six events.

**11. What would a sceptical examiner criticise most strongly?**
In the order I expect it: (i) **six events** — "you have N_eff ≈ 5 and you are
discussing learned fusion"; (ii) **the headline objective O5 is unmet and the
specification still asserts it** — a published spec whose central objective the
project's own evidence refutes; (iii) **the alert threshold fires on 60% of
days**, which makes every operational number meaningless; (iv) **three prior
evidence documents carried claims that were wrong until this session** — which
invites the question of what else is unverified; (v) **FR18**: the pipeline
never used the quantity the specification names, and the one it used is
anti-predictive.

**12. Final recommendation?**
**Narrow the claims, fix the scale, and pursue advance warning as a single
scoped research track — do not abandon a pillar.** Concretely: re-scope the
*production* deliverable to contemporaneous systemic-risk monitoring, which the
evidence supports; record advance warning as **tested, bounded and not
achieved**; keep P1/P2/P3 with their earned roles (P1 a contagion diagnostic per
FR13 `[v4]`, P2 contemporaneous structural monitoring, P3 a regime descriptor
with its regime claim marked unavailable); and spend the remaining effort on the
two free Phase-2 candidates under the frozen protocol. **A rigorous negative,
honestly reported, is a stronger final-year project than a tuned backtest — and
it is what this evidence actually supports.**
