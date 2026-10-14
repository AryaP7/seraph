# Why validation stops at six events — and whether it has to

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`. Nothing committed.
Database access was read-only throughout; no row was written, no schema touched.**

Pre-registration: `20261013T124358Z-32-event-count-preregistration.log` (written before
the first query).
Evidence: `20261013T125145Z-33-event-coverage-audit.log` (full audit, four arms),
`20261013T130107Z-34-event-count-dependence-deflation.log` (§6.3, the effective-N
measurement), `20261013T133320Z-35-event-count-vs-effect-size.log` (§6.5, whether more
onsets could change an observed 0/6),
`20261013T134906Z-36-block-bootstrap-pillar-csrs.log` (§6.6, the block bootstrap),
`20261013T135024Z-37-fr18-sca-false-alarm-matched-null.log` (§6.8),
`20261013T183324Z-38-auc-05-exclusion-accounting.log` (§6.7, the exact 0.5 ledger).
Code: `scripts/audit_event_coverage.py` (new, read-only).

> **No SPEC amendment is made here.** §8 is an approval request, and its recommendation
> is to make **no change** to FR32. FR32 is unchanged.

---

## 1. What this document decides, and what it does not

**Decides, on evidence:** whether SERAPH's six-event validation limit is imposed by
FR32's text or by the data. It is imposed by the text. Nine additional
exogenously-datable Indian stress episodes sit inside the existing pillar span with
100% RMT and Hamilton coverage, and not one of them is excluded by any data boundary.

**Does not decide:** whether those nine *should* be used. That is a specification
decision gated on SPEC **OQ13** (crisis-labelling source), which is still open, and on
the approval request in §8.

**Explicitly does not claim** that more events would make SERAPH work. §6.5 shows the
opposite: against the unified causal replay's measured 0 warnings over 6 epochs, the
binding constraint is **effect size, not sample size**, and no reachable event count
converts that into a detection.

**Also establishes, as a by-product that outgrew the mandate:** applying the measured
dependence to the existing six-epoch results (§6.6–§6.7) shows present AUC intervals are
too narrow by **2.1–5.7×**, and that **0 of 7 pillar/CSRS subsets retain any resolving
power at T1 or T3** once corrected — while **3 of 4 simple baselines do**.

---

## 2. The hypothesis and the pre-registered test

**H_B** — *"The six-event limit is imposed by FR32's specification, not by data
availability: the corpus contains materially more independently-datable Indian
systemic-stress episodes with full RMT+Hamilton coverage than the six FR32 names."*

Acceptance required all three criteria, fixed in the pre-registration log before any
query ran:

| | criterion | threshold | measured | verdict |
|---|---|---|---|---|
| **B1** | count of admissible non-FR32 candidates in the pillar span, each ≥ 60 trading days from every other accepted onset | ≥ 4 | **9** | **PASS** |
| **B2** | RMT **and** Hamilton rows present over `[onset−15, onset+30]` | ≥ 95% | **100% for all 9** (46/46 sessions each) | **PASS** |
| **B3** | the "6" traces to a specification artefact, and the pillar-span start does not exclude ≥ 2 candidates | spec-bound | 8 spec sites; **0 of 9** candidates fall before 2005 | **PASS** |

### Verdict: **H_B is ACCEPTED.**

**Accepted, and largely moot.** Five qualifications are load-bearing and are not
footnotes — the first two matter more than the verdict:

1. **The constraint that actually binds is effect size, not event count.** Against the
   unified causal replay's **0 warnings over 6 epochs × 5 lead horizons** (warned rate
   0.00 vs a 0.14 ± 0.13 no-skill rate), the minimum *detectable* warned rate falls only
   from 0.50 at N = 6 to ~0.33 at N = 15 — while the system's deficit is the full 0.33 to
   0.50. **No reachable event count converts 0/6 into a detection** (§6.5).
2. **Nominal N is not effective N.** `rv_t_yz`
   decorrelates on a measured **770-session integral timescale**, so the whole
   5,363-session grid holds only ≈ **7** effectively independent realisations. Deflating
   the designs by that scale, going from **6 nominal onsets to 15 raises the effective
   count from 5 to 6** (§6.3). H_B is true as stated; the headroom it exposes is
   nonetheless mostly illusory.
3. The 2005 corpus start **is** partly data-bound (§4.3) — but it excludes **none** of
   the nine candidates, so it is not what makes the count six.
4. Only **3 of 9** candidates have Hawkes coverage (§3.4). The power-starved fold
   count — Table A's four — gains least.
5. Hamilton's output is currently declared **unavailable**
   (`HAMILTON-REGIME-SUPPORT.md`: AAFT surrogate `p = 0.7143`, AR(1) `p = 0.9524`).
   B2 passing at 100% means *the rows exist*, not that two working pillars exist. More
   events do not repair a pillar that cannot beat its own surrogate null.

---

## 3. Specification trace: what the number six actually controls

### 3.1 FR32, quoted exactly

`docs/SPEC.md` line 240:

> | FR32 `[v2]` | The system shall evaluate against **six** labelled structural-break
> epochs (2008 GFC, 2013 taper tantrum, 2018 IL&FS, 2020 COVID-19, 2022 tightening,
> 2025–26 tariff sequence), each crisis window being the 30 trading days following the
> labelled break, with a 5–15 trading-day early-warning lead window. | O5, O8 |

The count is **enumerated by name**, not derived from a rule. There is no stated
criterion an episode must satisfy to be an epoch — which is exactly why OQ13 is open:

`docs/SPEC.md` line 466, open question 13:

> **Crisis labelling source** — who fixes the exact break date for each epoch, against
> what source?

### 3.2 The eight load-bearing sites

| site | what it holds | what it controls |
|---|---|---|
| `docs/SPEC.md:240` FR32 `[v2]` | six epochs by name, 30-day crisis window, 5–15d lead | **normative source**; everything below derives from it |
| `docs/SPEC.md:102` O5 `[v2]` | "**Six** epochs, corpus **2005–2026**" | binds event count and corpus bound *in one sentence* |
| `docs/SPEC.md:243` FR35 `[v2]` | Table A = 7 subsets × 2 on 4 Hawkes epochs; Table B = 3 × 2 on 2 pre-2015 | the **4/2 partition** of the six |
| `docs/ARCHITECTURE.md:756` D5(a)(b) | LOEO; Table A **4 folds**, Table B **6 folds**; tables not comparable | **fold counts are literally the event counts** |
| `docs/ARCHITECTURE.md:645` R4 | "Six positive events, 14 configurations" | the stated reason pre-registration exists at all |
| `seraph/shared_types/fusion.py:27` `EpochId` | `Literal` of exactly 6 ids | **closed type**. A 7th epoch is a type error |
| `seraph/validation/epochs.py:23` `EPOCH_BREAKS` | 6 (date, provenance) pairs; `HAWKES_COVERED` 4, `PRE_HAWKES` 2 | the only place dates live; OQ3 + OQ13 both flagged open here |
| `seraph/validation/preregistration.py:24` `EPOCHS` | 6-tuple duplicated from `epochs.py`; `folds=len(EPOCHS)` | feeds `configuration_list()` → `content_hash()` → the **pre-registration hash** |

`seraph/shared_types/validation.py:20` closes the loop: `EvaluationRow.epoch: EpochId`.
**There is no way to express a seventh epoch in an evaluation row — even in a secondary
sensitivity table — without editing the approval-gated `EpochId` Literal.** That is the
single hardest gate and the smallest concrete decision in §7.

So the "6" controls: **fold counts** (D5b), a **closed type** (`EpochId`), the
**pre-registration hash** (D5d), and the **Table A/B partition**. It does *not* control
the configuration count — `7×2 + 3×2` is independent of the event count. (FR35's "14"
versus the code's 20 is a separate, already-documented conflict:
`FR35-CONFIG-COUNT-CONFLICT.md`. Not re-adjudicated here.)

### 3.3 The cost of changing the count is zero today and rises on commit

Measured: `preregistration.json` **does not exist**. `preregistration.verify()` returns
`(False, '')`. The design as `build()` would emit it right now hashes to
`ce8f161a77539677ae8790253dd4564eda2594b0199a9675212b092b1595ac05` over 20
configurations (14 Table A at 4 folds, 6 Table B at 6 folds).

D5(d) says a result whose hash does not match the committed file is not reportable.
Since no file is committed and no ablation has been run, **changing the event count
today invalidates nothing**. The moment `preregistration.json` is committed, every
later change to the event set makes every existing `EvaluationRow` unreportable and
forces a full re-run. This is the same timing argument `FR35-CONFIG-COUNT-CONFLICT.md`
already makes for the configuration list, and it applies identically here.

### 3.4 Mechanical consequence of a count change, in dependency order

1. `EpochId` Literal gains members — **approval-gated** (`seraph/shared_types/`).
2. `EPOCH_BREAKS` gains `(date, provenance)` rows → **OQ13 must close first**, or the
   repo acquires nine more provisional labels on top of two it already has.
3. `preregistration.EPOCHS` changes → `configuration_list()` → `content_hash()` changes.
4. D5(b) fold counts change. Table B: 6 → 12 or 15. Table A: 4 → 5 or 7 — **only** for
   candidates after the Hawkes start, measured below.
5. FR35's subset counts are unaffected.

Measured Hawkes coverage in each `[onset−15, onset+30]` window (`hawkes_output` is
sparse by design — `refit_every=5` sessions, 473 rows over 2017-02-09 … 2026-08-20):

| event set | Hawkes points in window | Table A eligible |
|---|---|---|
| FR32 `gfc_2008`, `taper_2013` | 0, 0 | no (pre-2015, by design) |
| FR32 `ilfs_2018` / `covid_2020` / `tightening_2022` / `tariff_2026` | 10 / 8 / 9 / 9 | **yes** (confirms D5b's 4) |
| candidates `ltcg_budget_2018`, `adani_hindenburg_2023`, `loksabha_result_2024` | 9 / 9 / 9 | **yes** |
| candidates `fomc_may_2006` … `demonetisation_2016` (6 of them) | 0 each | no |

**Table A gains at most 3 folds (4 → 7), and only 1 (4 → 5) if tier-2 candidates are
excluded.** Table B gains 6 or 9 (6 → 12 or 15).

---

## 4. Data or definition? Where the 2005 boundary comes from

`daily_prices` holds 8,023,206 rows from **1995-01-02**, but every pillar output starts
**2005-01-03**. Three candidate causes were tested.

### 4.1 Raw reach of the corpus

| year | rows | distinct symbols | rows flagged `universe_member` |
|---|---|---|---|
| 1995 | 27,780 | 217 | **0** |
| 2000 | 64,813 | 306 | **0** |
| 2004 | 96,958 | 415 | **0** |
| 2005 | 112,991 | 494 | 74,059 |
| 2010 | 233,240 | 984 | 123,290 |

**637,900 pre-2005 rows are held and 0 of them are flagged as universe members** —
2,460 sessions of unused data (1995-01-02 … 2004-12-31).

### 4.2 Cause (i): the FR52 1000-listing-day filter — binds, but only before ~1999

`listing_days_to_date` counts from each symbol's true first row (1995+), not from the
corpus start (`eod2_client.py:21`), so this is real listing age. First session on which
*K* symbols clear the 1000-day filter:

| K symbols eligible | first session |
|---|---|
| 100 | **1999-07-29** |
| 150 | 2000-01-27 |
| 200 | 2001-05-08 |
| 250 | 2003-05-09 |
| 292 | 2004-12-14 |
| 500 | 2010-03-17 |

And FR16's rolling window is `T_WINDOW = 1000` trading days, so RMT's first possible
output is the 1000th session of the corpus: **1999-03-16**.

Both constraints are therefore satisfiable from **1999-07-29** at `N_t ≈ 100`, rising to
~292 by end-2004. The realised universe confirms the constructor's floating-`N`
behaviour is already doing this work at the current start:

| rebalance | eligible | realised `N_t` |
|---|---|---|
| 2005-01-01 | 292 | **292** |
| 2008-01-01 | 358 | 358 |
| 2010-01-01 | 481 | 481 |
| **2010-07-01** | 535 | **500** ← first date the 500 target is reachable |

**Verdict: the 1000-day filter is not what binds at 2005.** It binds at ~1999, and
`N_t = min(500, eligible_t)` already handles a short universe with
`UNIVERSE_UNDERFILLED`.

### 4.3 Cause (ii): the EOD2 adjustment caveat — this is the real data boundary

`seraph/ingestion/eod2_client.py:8`:

> Documented caveat: pre-2005 rows may not be fully adjusted — the corpus starts 2005,
> so only the return series is exposed, and report §7.1 must state this.

and line 38: `CORPUS_START = "2005-01-01"`.

This is a **data-quality decision recorded as a constant**. It is the binding reason the
pillars start in 2005 rather than 1999. Its severity is concrete: an unadjusted split or
bonus appears as a one-session return near −50%, which would feed C4's jump extraction,
inflate realised volatility and corrupt the correlation matrix RMT eigendecomposes. It
is *reducible* — it is an unacquired-adjustment-factor problem, not a physical limit —
but reducing it is a data-acquisition task with a real cost, and nothing in the current
corpus lets it be checked cheaply.

### 4.4 Cause (iii): `macro_covariates` — not a constraint, because it is empty

`macro_covariates` has 5,363 rows spanning 2005-01-03 … 2026-08-21, and measured
non-null counts are:

| column | non-null | from |
|---|---|---|
| `india_vix` | 3,034 | 2014-05-15 |
| `rbi_repo_rate` | **0** | — |
| `bank_credit_growth_yoy` | **0** | — |
| `inr_twi` | **0** | — |
| `brent_price` | **0** | — |
| `g_t` | **0** | — |
| `g_t_sector_weighted` | **0** | — |

So SPEC E4's `z_t` does not exist in this dataset, and production Hamilton does not use
it. `scripts/fit_hamilton.py:82` states this in-code and substitutes the lagged
standardised RV level as the TVTP driver. **`macro_covariates` therefore places no
constraint on how far back Hamilton could run** — there is nothing in it to lose.

### 4.5 What the current span actually covers

| quantity | measured |
|---|---|
| pillar trading-day grid (universe members, 2005+) | **5,363 sessions**, 2005-01-03 … 2026-08-21 |
| full `daily_prices` grid (1995+) | 7,825 sessions |
| `rmt_output` / `hamilton_output` | 5,363 / 5,365 rows, same span |
| `hawkes_output` | 473 rows, 2017-02-09 … 2026-08-20 (≈50/yr by design) |
| `csrs` | 4,714 rows, 2017-02-09 … 2026-08-20 |
| FR32 onsets on the grid | 6, at indices 925 / 2086 / 3405 / 3752 / 4216 / 5225 |
| minimum spacing between FR32 onsets | **347 trading days** |
| arithmetic ceiling on 60-session-separated onsets | **89** |

The ceiling is the decisive number for §2's B1: separation is nowhere near binding. The
constraint on event count is **how many episodes the exogenous public record supports**,
not the grid.

### 4.6 Could the pillars be extended before 2005?

Yes, conditionally, and it is worth stating precisely what it would buy and cost.

* **Feasible from 1999-07-29** on both hard constraints (§4.2), adding ~1,350 sessions at
  `N_t` 100 → 292.
* **Blocked by** the §4.3 adjustment caveat, which must be resolved first. Running RMT on
  possibly-unadjusted pre-2005 closes would produce eigenvalue spectra contaminated by
  corporate-action artefacts, and the contamination is not detectable from within the
  spectrum.
* **Would also require a SPEC change**, because O5 fixes the corpus at 2005–2026 in the
  same sentence that fixes six epochs.
* **Survivorship cost**: at `N_t ≈ 100–200` the universe is a small, heavily
  selected slice of the market, and `Q_t = T/N_t` rises from 2 to 5–10, moving the
  Marchenko–Pastur bounds into a regime the current validation has never exercised.

This is a *separate* question from H_B and it does not affect the verdict: **zero of the
nine accepted candidates falls before 2005.**

---

## 5. Candidate episodes

### 5.1 The admissibility rule, stated before the candidates were listed

A candidate onset is admissible only if fixed by an event **exogenous to Indian equity
prices and to every SERAPH signal**: a dated policy or administrative action, a statutory
result declaration, a rating action, or a dated foreign-central-bank decision. Declared
inadmissible in the pre-registration log: any date chosen because the Indian market fell,
any date read off `rmt_output` / `hamilton_output` / `csrs` / `hawkes_output`, any date
chosen to maximise a drawdown or an AUC.

**Not one date below was selected by inspecting a SERAPH output or an Indian return
series.** The candidate list is a literal constant in `scripts/audit_event_coverage.py`,
fixed before coverage was measured; the coverage test can only remove candidates.

Where the exogenous anchor fell outside NSE trading hours or on a non-trading day, the
onset moves to the next session, and both dates are recorded.

Tiers: **tier 1** = dated non-market action *and* a broad macro-financial transmission
channel. **tier 2** = dated action, but a narrower channel or a weaker/compound anchor.

### 5.2 Accepted — passed separation (≥ 60 sessions) and coverage (≥ 95%)

| # | id | anchor | NSE onset | tier | exogenous public record | RMT+Ham coverage | Hawkes |
|---|---|---|---|---|---|---|---|
| 1 | `fomc_may_2006` | 2006-05-10 | 2006-05-11 | 2 | FOMC raised the funds target to 5.00% and signalled further firming (statement 2006-05-10). **Weak anchor** — the May-2006 EM/commodity unwind has no single crisp exogenous trigger; this is the closest dated policy action, not an undisputed onset | **46/46 = 100%** | no |
| 2 | `greece_bailout_2010` | 2010-04-23 | 2010-04-23 | 1 | Greece formally requested the EU/IMF support package (2010-04-23) — a dated sovereign administrative act | **46/46 = 100%** | no |
| 3 | `us_downgrade_2011` | 2011-08-05 | 2011-08-08 | 1 | Standard & Poor's downgraded the US sovereign rating AAA→AA+ after the US close on Friday 2011-08-05; first NSE session Monday | **46/46 = 100%** | no |
| 4 | `pboc_cny_2015` | 2015-08-11 | 2015-08-11 | 1 | People's Bank of China changed the CNY central-parity mechanism and devalued, announced 2015-08-11 | **46/46 = 100%** | no |
| 5 | `brexit_vote_2016` | 2016-06-24 | 2016-06-24 | 1 | UK EU-membership referendum result declared 2016-06-24; date fixed by a statutory count | **46/46 = 100%** | no |
| 6 | `demonetisation_2016` | 2016-11-08 | 2016-11-09 | 1 | Government of India withdrew ₹500/₹1000 notes, announced 20:15 IST 2016-11-08. **Confounded** — the US presidential result landed in the same session, so this onset has two causes and cannot be attributed to either alone | **46/46 = 100%** | no |
| 7 | `ltcg_budget_2018` | 2018-02-01 | 2018-02-01 | 2 | Union Budget 2018-19 reintroduced long-term capital-gains tax on listed equity. Dated fiscal action with a direct equity channel; coincident with the global Feb-2018 volatility spike, hence tier 2 | **46/46 = 100%** | **yes** (9) |
| 8 | `adani_hindenburg_2023` | 2023-01-24 | 2023-01-25 | 2 | Hindenburg Research report published 2023-01-24 (US hours); first full NSE session 2023-01-25. Dated publication, but a **single-issuer** event — "systemic" is contestable | **46/46 = 100%** | **yes** (9) |
| 9 | `loksabha_result_2024` | 2024-06-04 | 2024-06-04 | 1 | Election Commission of India declared the 18th Lok Sabha result on 2024-06-04; date fixed by statute, independent of any market outcome | **46/46 = 100%** | **yes** (9) |

### 5.3 Rejected, and why — published so the rejections are auditable

**Rejected on separation (the 60-session rule).** Both had 100% coverage; both lost to a
chronologically earlier candidate under the pre-registered mechanical tie-break (date
priority, not judgement):

| id | onset | gap | collides with | note |
|---|---|---|---|---|
| `svb_cs_2023` | 2023-03-13 | **31 sessions** | `adani_hindenburg_2023` (2023-01-25) | SVB placed in FDIC receivership 2023-03-10 — a statutory action, and the *stronger* systemic case of the two. The mechanical rule still drops it. A 30-session rule would admit both |
| `boj_carry_2024` | 2024-07-31 | **39 sessions** | `loksabha_result_2024` (2024-06-04) | BoJ rate rise + JGB taper 2024-07-31, trigger of the yen carry unwind that peaked 2024-08-05. Anchored on the policy date, not the rout date |

**Rejected for crisis-splitting** — each would slice one FR32 episode into two:

| id | date | reason |
|---|---|---|
| `bnp_credit_crunch_2007` | 2007-08-09 | BNP Paribas froze three ABS funds. Same crisis as `gfc_2008` at an earlier phase |
| `india_crash_jan_2008` | 2008-01-21 | `EPOCH_BREAKS` already names this as the **alternative** label for `gfc_2008` |
| `rupee_crisis_2013` | 2013-08-28 | Inside `taper_2013`'s sequence, and a price extremum — an endogenous date |
| `covid_bottom_2020` | 2020-03-23 | `EPOCH_BREAKS` names this as the **alternative** label for `covid_2020`; also a market bottom |
| `reciprocal_tariff_2025` | 2025-04-03 | FR32 epoch 6 **is** the "2025–26 tariff sequence", and `EPOCH_BREAKS/tariff_2026` names the 50% peak and the solar-CVD drop as competing labels for that same sequence. SPEC **OQ3** is the open question of which date wins — not a licence to use several |

### 5.4 The two resulting designs

| design | N | min gap | median gap | T3 positive days | prevalence |
|---|---|---|---|---|---|
| FR32 six (current) | **6** | 347 | 1,009 | 90 | 1.7% |
| FR32 + tier-1 only | **12** | 92 | 413 | 180 | 3.4% |
| FR32 + tier-1 + tier-2 | **15** | 92 | 340 | 225 | 4.2% |

The minimum gap drops from 347 to 92 sessions. §6.3 shows why that matters more than the
rise in N.

Onset sessions, N = 15: 2006-05-11, 2008-09-15, 2010-04-23, 2011-08-08, 2013-05-22,
2015-08-11, 2016-06-24, 2016-11-09, 2018-02-01, 2018-09-21, 2020-02-20, 2022-01-05,
2023-01-25, 2024-06-04, 2026-02-01.

---

## 6. Statistical power

### 6.1 Protocol, and the reproduction check

The N-extension reuses `scripts/early_warning_power.py`'s own `t3_auc`,
`relocation_null`, `aaft_null` and `ar1_stationary` **by import**, so the null cannot
drift from the published one. Background is AR(1) at the real `rv_t_yz` lag-1
autocorrelation `φ = 0.9973`, initialised at its stationary variance; signal is a step of
`δ` within-series sd over the 15 sessions before each onset; null is the AAFT surrogate
(the circular-shift null is miscalibrated on a near-unit-root series — the measured
finding in `EARLY-WARNING-POWER.md`, not an assumption made here). 60 draws per δ, 400
surrogates per draw, α = 0.05, matching the authoritative published run.

Every N randomises onset placement subject to the real 347-session minimum spacing, so
the only quantity varying across rows is the event count. Row **6\*** holds the real FR32
dates fixed, as the anchor against the published result:

| | δ=0 (type-I) | δ=0.5 | δ=1.0 | δ=1.5 |
|---|---|---|---|---|
| published `EARLY-WARNING-POWER.md` §3 | 8% | 47% | 85% | 98% |
| **this run, row 6\*** (real FR32 dates) | **5%** | **43%** | **93%** | **97%** |

Within sampling error at 60 draws (SE ≈ 2.8% on the control, ≈ 6% on a power near 90%).
**The published power result reproduces independently.**

### 6.2 Power and minimum detectable effect at N = 6, 10, 15, 20

Power at α = 0.05 against the AAFT null, by injected effect `δ` (within-series sd):

| N | **δ = 0 (type-I)** | δ = 0.5 | δ = 1.0 | δ = 1.5 | δ = 2.0 | **MDE @ 80%** |
|---|---|---|---|---|---|---|
| **6\*** (real FR32 dates) | 5% | 43% | 93% | 97% | 100% | **1.0 sd** |
| **6** (randomised placement) | 8% | 38% | 92% | 100% | 100% | **1.0 sd** |
| **10** | 3% | **70%** | 100% | 100% | 100% | **1.0 sd** |
| **15** | 5% | **97%** | 100% | 100% | 100% | **0.5 sd** |
| **20** | 2% | **100%** | 100% | 100% | 100% | **0.5 sd** |

**Every negative control is calibrated** — 2% to 8% against a nominal 5%, all inside the
±2.8% sampling error at 60 draws. No row is void.

Mean T3 AUC and its dispersion, which show the actual mechanism:

| N | mean AUC @ δ=0.5 | **sd of AUC @ δ=0.5** | mean AUC @ δ=0 | sd of AUC @ δ=0 |
|---|---|---|---|---|
| 6\* | 0.6357 | **0.1000** | 0.4974 | 0.0966 |
| 6 | 0.6157 | **0.0901** | 0.5063 | 0.0880 |
| 10 | 0.6343 | **0.0500** | 0.5031 | 0.0584 |
| 15 | 0.6449 | **0.0338** | 0.4955 | 0.0463 |
| 20 | 0.6400 | **0.0254** | 0.4997 | 0.0273 |

Three things to read off this, in order of importance:

1. **Mean AUC is flat in N; only its dispersion falls.** AUC measures effect size, not
   sample size, so the mean stays near 0.64 at δ = 0.5 for every N. What buys power is the
   collapse in sampling dispersion: **sd 0.090 → 0.025 from N = 6 to N = 20**, faster than
   `1/√N` (which would predict 0.090 → 0.049). More onsets make the AUC *estimate*
   stable, not larger.

2. **The MDE moves one grid step, from 1.0 sd to 0.5 sd, and it needs N ≈ 15 to do it.**
   N = 10 does not move it (δ = 0.5 reaches 70%, short of 80%). The MDE is reported on a
   coarse 0.5-sd grid, so the more informative number is power at δ = 0.5:
   **38% → 70% → 97% → 100%** across N = 6, 10, 15, 20. The regime where the corpus is
   currently blind — effects below ~0.5 sd, declared untested in
   `EARLY-WARNING-POWER.md` — becomes testable at **N ≈ 15**, not before.

3. **Everything at δ ≥ 1.0 sd is already saturated at N = 6.** Power is 92–93% at N = 6
   and 100% from N = 10. So more events buy **nothing at all** for the claim the project
   has actually made ("no clean ≥ 1.0 sd lead signal exists"). That claim is already
   established and does not need more events. The gain is confined entirely to the
   0.5-sd band.

**This table is an upper bound.** It injects an independent, identical step at every
onset. §6.3 measures what the real series can deliver.

### 6.3 The correction that matters most: nominal N is not effective N

The power curve above injects a **clean, independent, identical** step at every onset.
That is the best case, and it is an upper bound on what more events can buy. The real
constraint is measured directly on the real series.

Autocorrelation of the Hamilton observables over all 5,365 sessions:

| series | lag-1 `φ` | AR(1) `1/(1−φ)` | lag at `acf = 1/e` | first zero crossing | **integral timescale** | effectively independent blocks on the grid |
|---|---|---|---|---|---|---|
| `rv_t_yz` | 0.9973 | 375 | **423** | 1,508 | **770** | **7.0** (integral) / 12.7 (1/e) |
| `ar_t` | 0.9981 | 533 | 209 | 1,214 | 495 | 10.8 / 25.7 |
| `bas_t` | 0.9964 | 275 | 222 | 1,214 | 616 | 8.7 / 24.2 |

`rv_t_yz` decorrelates on a **770-session integral timescale**. The entire 5,363-session
pillar grid therefore contains only about **7 effectively independent realisations of the
series.** That is a property of the data, not of FR32, and no event definition can change
it.

Applying those two scales to the three designs — greedily keeping only onsets separated
by at least one decorrelation length:

| design | N nominal | gaps < 423 | gaps < 770 | **N_eff @ 423 (1/e)** | **N_eff @ 770 (integral)** |
|---|---|---|---|---|---|
| FR32 six | 6 | 1 of 5 | 2 of 5 | **5** | **5** |
| FR32 + tier-1 | 12 | 6 of 11 | 11 of 11 | **7** | **5** |
| FR32 + tier-1 + tier-2 | 15 | 10 of 14 | 14 of 14 | **9** | **6** |

Adjacent gaps for N = 15: 588, 388, 328, 445, 549, 214, 92, 307, 157, 347, 464, 262, 334,
413 — **ten of fourteen are shorter than the 423-session `1/e` lag, and fourteen of
fourteen are shorter than the 770-session integral timescale.**

**This is the single most important number in the document.** Going from 6 nominal events
to 15 raises the effective count from 5 to 9 on the optimistic `1/e` scale, and from
**5 to 6** on the integral timescale. On the honest scale, nine additional episodes buy
roughly **one** effectively independent event.

Note also that FR32's own six are not fully independent: one adjacent gap (347 sessions,
`ilfs_2018` → `covid_2020`) is already inside the `1/e` lag, and two are inside the
integral timescale.

So H_B is accepted *as stated* — the six-event limit is spec-imposed, and the corpus does
hold nine more coverable, exogenously-datable episodes — but the practical gain from
exercising that headroom is far smaller than the nominal count suggests, because the
underlying series cannot support fifteen independent observations.

### 6.4 Raising power without inflating effective sample size

| route | what it does to power | measured basis |
|---|---|---|
| **Block / stationary bootstrap** on the feature series | **Does not raise power.** With a block length ≥ the 770-session integral timescale, only ~7 blocks exist in the grid. The bootstrap *corrects the standard error* — it reveals how little information is there rather than adding any. Worth doing for honest inference; worthless as a power strategy | §6.3 |
| **Event-clustered / cluster-robust variance** on pooled event-time regressions | Same: fixes inference, does not add information. But **necessary** if the extended set is ever used, because §6.3 shows nominal N overstates independence by ~2.5× | §6.3 |
| **Replace the binary crisis label with a graded severity response** | **Genuinely raises information per event.** A 0/1 indicator at 1.7–4.2% prevalence is close to the least informative encoding available; a continuous response uses the whole window. **But** any severity measure defined on Indian returns is endogenous and reintroduces the §7.1–7.2 selection problem. Needs an exogenous severity proxy to be usable. FR33 currently specifies "AUC against binary crisis labels" — this would be a specification change | §5.4 prevalence |
| **Cross-market replication (O9 / FR37–38)** | **The only route that adds independent realisations of the series**, which is what §6.3 shows is actually scarce. But of the N = 15 set, **10 onsets are global** (2006 FOMC, 2008 GFC, 2010 Greece, 2011 US downgrade, 2013 taper, 2015 PBoC, 2016 Brexit, 2020 COVID, 2022 tightening, 2026 tariff) and would be **common to any second market**, so they add correlated, not independent, observations. Only the **5 domestic** onsets (2016 demonetisation, 2018 LTCG, 2018 IL&FS, 2023 Adani, 2024 Lok Sabha) are India-specific, and the gain is in the second market's *own* domestic episodes | §5.2, §7.6 |
| **A single pre-registered primary metric instead of a screen** | Recovers the multiplicity already spent on nine screened features (`EARLY-WARNING-POWER.md` §5). Cheap, and larger than it sounds at this event count | — |
| **Longer lead window than 15 days** | Widens the positive window but leaves the event count unchanged; `EARLY-WARNING-POWER.md` §6 already assesses this as buying little, and §6.3 explains why — the windows are already far inside one decorrelation length | §6.3 |

### 6.5 Could more onsets change an observed 0/6? No — the constraint is effect size

Established by another workstream after this audit began: the unified causal replay
finds the full three-pillar system gives **0 pre-onset warnings across 6 epochs × 5 lead
horizons**, a warned rate of **0.00** against a no-skill relocation expectation of
**0.14 ± 0.13**, with no signal — pillar, fusion or baseline — distinguishable from
chance (10 comparisons, lowest `p = 0.1108`).

§6.2's AUC power curve cannot answer whether more onsets would change that, because AUC
power says nothing about a count of zero. The decidable questions, on the warned-rate
metric the replay actually reports, are answered exactly
(`20261013T133320Z-35-event-count-vs-effect-size.log`, Clopper–Pearson and exact
one-sided binomial, α = 0.05):

**(a) How sharp is the negative claim, given k = 0 warnings?**

| N onsets | 95% upper bound on per-event warn probability `p` | below the 0.14 no-skill rate? |
|---|---|---|
| **6** (current) | **0.393** | no |
| 10 | 0.259 | no |
| 12 | 0.221 | no |
| 15 | 0.181 | no |
| **20** | **0.139** | **yes** |
| 25 | 0.113 | yes |
| 30 | 0.095 | yes |

**0 warnings out of 6 is consistent with a true per-event warning probability as high as
0.39.** It therefore does not even establish *sub-chance* performance — 0.39 is nearly
three times the 0.14 no-skill rate. The upper bound first falls below 0.14 at **N = 20**,
which is the point at which a continued zero-warning record would become positive
evidence of *worse than chance* rather than an absence of evidence.

**(b) How large would a positive result have to be?**

| N onsets | minimum warned count `k` to reject `p ≤ 0.14` | implied warned **rate** | deficit vs observed 0.00 |
|---|---|---|---|
| 6 | 3 | 0.500 | 0.500 |
| 10 | 4 | 0.400 | 0.400 |
| 15 | 5 | 0.333 | 0.333 |
| 20 | 7 | 0.350 | 0.350 |
| 30 | 8 | 0.267 | 0.267 |

The minimum detectable warned rate falls only from **0.50 at N = 6 to ~0.27–0.35 at
N = 20–30**. The system sits at **0.00**. The deficit is 0.27–0.50 in warned rate, and
more onsets close **none** of it.

**(c) Verdict, stated plainly.** A detector that warns on 0 of 6 onsets warns on ~0 of 15
and ~0 of 20 unless its per-event warning probability is genuinely non-zero. Sample size
governs how *precisely* a null result can be stated; only effect size governs whether the
result is null. **At a warned rate of 0.00 against a 0.14 no-skill rate, the binding
constraint is effect size, unambiguously. Additional onsets could not plausibly convert
0/6 into a detection.**

**(d) But the one thing more onsets would buy is specific, and it is out of reach.** They
would upgrade *"we cannot tell whether the system beats chance"* (the honest N = 6
position) to *"the system demonstrably does not beat chance"* — a falsifiable negative,
which is a stronger and more publishable result than an indeterminate one. That upgrade
needs **N = 20**. The exogenous public record supports at most **N = 15** under the
pre-registered 60-session rule, or **N = 17** if that rule is relaxed to 30 sessions
(admitting `svb_cs_2023` and `boj_carry_2024`, §5.3). **N = 20 is therefore not reachable
from the 2005–2026 corpus by any defensible event definition** — and §6.3's effective-N
deflation makes the real shortfall larger still, since N = 15 nominal is N ≈ 6 effective.

This is the sharpest single conclusion in the document: **the six-event limit is
spec-imposed (H_B accepted), the headroom above it is real but small, and it is not
large enough to reach the one threshold that would have made it worth exercising.**

### 6.6 Event-clustered block bootstrap on the pillar and CSRS series

§6.3 measured the dependence. This applies it: a **circular moving-block bootstrap** of
the AUC on every replayed series, at block lengths `L ∈ {1, 21, 63, 252, 423, 770}`
trading days, 2,000 resamples each. `L = 1` is the naive i.i.d. pair bootstrap — the
implicit basis of any interval that treats the 5,363 daily rows as independent
observations. `L = 423` and `L = 770` are arm 3b's **measured** `rv_t_yz` scales.

Series come from `replay_crisis_warnings.build_signals()` **by import**, not rebuilt, so
the bootstrap cannot be computed on a different construction path than the replay.
Evidence: `20261013T134906Z-36-block-bootstrap-pillar-csrs.log`.

**How much is present precision overstated?** The ratio of the `L = 770` interval width
to the `L = 1` width:

| signal | T1 width `L=1` | T1 width `L=770` | **overstatement** | T3 **overstatement** |
|---|---|---|---|---|
| `CSRS[hamilton]` | 0.0837 | 0.4692 | **5.61×** | 4.66× |
| `CSRS[hawkes+hamilton]` | 0.0785 | 0.4470 | **5.70×** | 4.45× |
| `CSRS[rmt+hamilton]` | 0.0894 | 0.3853 | 4.31× | 3.85× |
| `CSRS[hawkes+rmt+hamilton]` | 0.0879 | 0.3779 | 4.30× | 3.66× |
| `CSRS[hawkes+rmt]` | 0.1068 | 0.4238 | 3.97× | 2.78× |
| `CSRS[rmt]` | 0.1113 | 0.4283 | 3.85× | 2.81× |
| `CSRS[hawkes]` | 0.1975 | 0.4548 | 2.30× | 1.44× |
| `BASE[rv_20]` | 0.0639 | 0.2708 | 4.24× | 3.94× |
| `BASE[drawdown]` | 0.0921 | 0.4149 | 4.50× | 2.92× |
| `BASE[rv_accel_5]` | 0.0887 | 0.2823 | 3.18× | 2.37× |
| `BASE[dd_accel_5]` | 0.0865 | 0.1842 | 2.13× | 1.79× |

**Present precision is overstated by 2.1× to 5.7×, and by 3.9–5.7× for every CSRS subset
that includes Hamilton or RMT.** My earlier §6.3 estimate of "~2.5×" was conservative.

### 6.7 Exact 0.5-exclusion accounting — does T1 retain *any* resolving power?

"Essentially every interval spans 0.5" is impressionistic and a reader cannot check it.
Stated exactly instead (`20261013T183324Z-38-auc-05-exclusion-accounting.log`, parsed
deterministically from log 36): does each 95% interval **exclude AUC = 0.5**?

**T1 crisis detection, Pillar 2 = `λ₁/N` (as shipped):**

| signal | AUC | L=1 | L=21 | L=63 | L=252 | L=423 | **L=770** |
|---|---|---|---|---|---|---|---|
| `CSRS[hawkes]` | 0.6464 | **excl** | — | — | — | — | **—** |
| `CSRS[rmt]` | 0.5292 | — | — | — | — | — | **—** |
| `CSRS[hamilton]` | 0.6350 | **excl** | — | — | — | — | **—** |
| `CSRS[hawkes+rmt]` | 0.5218 | — | — | — | — | — | **—** |
| `CSRS[hawkes+hamilton]` | 0.6239 | **excl** | — | — | — | — | **—** |
| `CSRS[rmt+hamilton]` | 0.5778 | **excl** | — | — | — | — | **—** |
| `CSRS[hawkes+rmt+hamilton]` | 0.5733 | **excl** | — | — | — | — | **—** |
| `BASE[rv_20]` | 0.7347 | excl | excl | excl | excl | excl | **excl** |
| `BASE[drawdown]` | 0.6713 | excl | — | — | — | — | — |
| `BASE[rv_accel_5]` | 0.6622 | excl | excl | excl | excl | excl | **excl** |
| `BASE[dd_accel_5]` | 0.7015 | excl | excl | excl | excl | excl | **excl** |

**Pillar/CSRS: 5/7 exclude 0.5 at L=1 → 0/7 at L=770. Baselines: 4/4 → 3/4.**

With Pillar 2 = `SCA_t` (FR18-conformant), the point AUCs improve materially —
`CSRS[rmt]` 0.5292 → **0.6289**, the full system 0.5733 → **0.6632** — and pillar/CSRS
goes **7/7** excluding at L=1. At L=770 it is still **0/7**. `CSRS[hawkes+rmt+hamilton]`
under `SCA_t` holds out furthest, retaining exclusion to L=63 before losing it.

**T3 advance warning:** pillar/CSRS 6/7 → **0/7** at L=770 under `λ₁/N`, 2/7 → **0/7**
under `SCA_t`; baselines 2/4 → **0/4**. **Nothing survives at T3, pillar or baseline.**

Two conclusions, and the second is the uncomfortable one:

1. **The previously-reported T1 detection results have no resolving power at all for any
   SERAPH pillar or composite** — not merely reduced precision. Every one of the seven
   subsets, under both Pillar 2 quantities, spans 0.5 once dependence is accounted for at
   the measured integral timescale. Results in `DETECTION-CALIBRATION.md` and
   `STRESS-PILLAR-DECISION.md` that rest on T1 intervals computed as if daily rows were
   independent should be read as **non-resolving**, and the exclusion table above is the
   exact ledger of which claims survive at which dependence assumption.
2. **Three simple baselines do survive, at every block length tested.** `BASE[rv_20]`
   (0.7347), `BASE[rv_accel_5]` (0.6622) and `BASE[dd_accel_5]` (0.7015) exclude 0.5 from
   L = 1 through L = 770. So the correct statement is **not** "T1 has no resolving power";
   it is **"T1 has no resolving power for anything SERAPH builds, while three
   one-line volatility and drawdown features retain it."** That is a worse result for the
   architecture than a uniform loss of power would have been, because the correction that
   destroys the pillars leaves the baselines standing.

### 6.8 Both Pillar 2 quantities, against two independent nulls

The FR18 conformance defect (SPEC FR18 specifies `SCA_t`; `adapters.rmt_emission`
standardises `λ₁/N`) raises the full system from **0/6 to 2/6** pre-onset warnings — but
its false-alarm rate nearly doubles, 3.66 → 6.90/yr. Two nulls, built on different
principles, were applied (`20261013T135024Z-37-fr18-sca-false-alarm-matched-null.log`):

| null | principle | `CSRS[hawkes+rmt+hamilton]` under `SCA_t` | verdict |
|---|---|---|---|
| **False-alarm-matched** (this workstream) | `p₀ = 1 − exp(−(FA/yr)·15/252)`: chance of ≥1 alert episode landing in the 15-day pre-window if alert timing were unrelated to onsets | observed rate **0.333** vs `p₀` = **0.337**; `P(X≥2) = 0.656` | **below its own null** |
| **Circular relocation** (Workstream C, measured) | relocate the six onsets, recompute | observed **0.33** vs null **0.26 ± 0.17**; `p = 0.4993` | not significant |

Where both exist the measured relocation null is the better number, and it confirms the
direction this workstream predicted: Poisson matching gave `p₀ = 0.413` for `CSRS[rmt]`
under `SCA_t` where relocation measures **0.36**, i.e. the approximation overstates `p₀`
because alert episodes cluster, exactly as flagged. **Two independent nulls, built on
different principles, both put the FR18 variant's 2/6 inside chance** — a stronger
statement than either alone.

**So the arm-5 arithmetic does not need restating against a genuine detection.** The
numerator moved off zero, so the Clopper–Pearson `k = 0` bound no longer applies to the
`SCA_t` variant; the replacement statement is that its warned rate is **indistinguishable
from, and marginally below, its own false-alarm-matched expectation**. The FR18 fix makes
Pillar 2 conform to specification and materially improves its T1 point estimate — both
worth having on their own merits — but it does not produce advance warning.

Two further results from elsewhere this session sharpen the same conclusion:

* **The negative survives a realistic signal shape.** T3 power against a 75-session
  linear ramp is 75–77% at δ = 1.0 sd, and 78–80% against an AR(1)-persistent drift,
  versus 80–85% for the rectangular step (type-I 2–8% at nominal 5%). §6.2's MDE and
  §6.5's unreachability arithmetic therefore apply to a test that is genuinely informative
  about the persistent build-up a systemic-risk thesis predicts — not to a test tuned to
  an implausible step.
* **The best available single feature warns before 0 of 6 onsets.** `semivar_20`,
  the repository's strongest known input, scores `p = 1.0000` against a null of
  0.04 ± 0.08 at *every* horizon from 5 to 30 days. When the best input has a per-event
  warn rate indistinguishable from zero, the deficit is not one of sample size.

### 6.9 The verdict the mandate asked for

> **Sample size governs how precisely a null result is stated; only effect size governs
> whether the result is null.**

At a warned rate of 0.00 (or 0.33 against a 0.34 no-skill rate) the binding constraint is
effect size, unambiguously. More onsets would sharpen the negative finding; they could not
plausibly convert it into a detection. And the one sharpening worth having — the
falsifiable negative at N = 20 — is unreachable from the 2005–2026 corpus by any
defensible event definition (§6.5).

### 6.10 Where this bootstrap and Workstream C's agree, and where they diverge

Two different corrections were run this session on deliberately different resampling
units. Both belong in the record.

| | **this workstream** | **Workstream C** |
|---|---|---|
| resampling unit | contiguous **blocks** of the series, L = 770 (measured) | the **six onsets**, clustered |
| series | pillar and CSRS subsets (+ replay baselines) | its own acceleration signals |
| captures | serial dependence in the ~5,100 **negative** days, where the AUC's variance mostly lives | between-**episode** heterogeneity |
| cannot do | lead time — resampling blocks destroys the time axis an onset is measured from | widen an AUC interval beyond ~6 clusters' resolution |

**Where they agree.** Both widen intervals materially versus naive i.i.d.; both leave
every pillar and CSRS conclusion non-significant; and both independently reach "not
distinguishable from chance" for the advance-warning claim. On the two signals where a
comparison is even meaningful, both put the acceleration features among the strongest
available and still short of a defensible positive at T3.

**Where they diverge, and why.** C's onset-clustered `rv_accel` is 0.7706 [0.6614,
0.8877], excluding 0.5; the replay's `BASE[rv_accel_5]` at T3 is 0.5288 with
L = 770 interval [0.374, 0.649], including it. **These are not the same statistic** — the
series are constructed differently (C's own features versus the replay's `accel(rv, 20d
RV, 5)`) and the targets differ, so the point estimates are not comparable and no
contradiction should be read into the gap. The *structural* divergence is the informative
one: onset clustering resamples six units and so cannot resolve an AUC computed over
5,363 days, while the block bootstrap addresses precisely the dependence in the negative
class. **For AUC the block bootstrap is the appropriate correction; for per-epoch warned
rates and lead times the onset cluster is the only option** — and for a 0/N warned count
even that degenerates to `[0, 0]`, which is why §6.5 uses an exact binomial bound instead
of any bootstrap.

---

## 7. Selection-bias risks of adding events

Stated specifically, because this is where an extended event set would actually fail
review.

1. **Outcome-informed inclusion, which exogenous dating does not fix.** Every onset above
   is dated exogenously, but the *decision to nominate the episode at all* was made by
   someone who knows Indian market history. "The 2011 US downgrade was an Indian stress
   episode" is a judgement informed by knowing what followed. Exogenous dating removes
   look-ahead from the *date*, not from the *list*. This is the single largest risk and
   it is not fully mitigable — only disclosable. Mitigation applied: the list is a
   pre-registered constant, tiered by anchor strength, with every rejection published.

2. **No severity criterion exists, so the list has an arbitrary boundary.** FR32 names
   episodes; it defines no threshold an episode must clear. Without one, the boundary can
   be moved until the results flatter. And the obvious fix is circular: any severity rule
   defined on Indian returns reintroduces outcome selection. **This tension is
   unresolved** and is the strongest argument for closing OQ13 *before* extending the set,
   rather than after.

3. **Crisis-splitting recurs with every addition.** Five candidates were rejected on this
   ground (§5.3), two of them because `EPOCH_BREAKS` already names the date as an
   *alternative* label for an existing epoch. The 2025 tariff dates are the live case:
   OQ3 is open precisely because one sequence has several defensible onsets, and treating
   them as several events would inflate N by re-slicing one episode.

4. **Separation-rule arbitrage.** 60 sessions is pre-registered and derived
   (`CRISIS_WINDOW_DAYS` 30 + lead 15, rounded up). A 30-session rule admits
   `svb_cs_2023` and `boj_carry_2024` and gives N = 17. The rule choice moves N by 2, and
   it was chosen before the results — but a reader cannot verify that from the numbers
   alone, only from the timestamped log.

5. **Tier boundary is my judgement.** Tier 1 vs 2 is not mechanical. Reporting both
   N = 12 and N = 15 is the mitigation; picking whichever performs better would be exactly
   the D5(c) violation the architecture already forbids.

6. **Nominal N overstates independent information.** `brexit_vote_2016` and
   `demonetisation_2016` are 92 sessions apart inside one macro regime;
   `greece_bailout_2010` and `us_downgrade_2011` are two phases of one sovereign-stress
   cycle. The 60-session rule guarantees non-overlapping *windows*, not independent
   *episodes*. Any inference on the extended set needs an event-clustered variance, and
   the honest headline count is lower than 15.

7. **Multiplicity is already spent.** Nine candidate features were screened with no
   correction (`EARLY-WARNING-POWER.md` §5). Adding events does not buy that back; it
   changes the denominator of future tests only.

8. **Non-stationarity over 21 years.** Pooling 15 events from 2006 to 2026 assumes the
   lead-signal mechanism is stable. The universe itself is not: realised `N_t` goes
   292 → 500 between 2005 and 2010 (§4.2), so `Q_t` and the Marchenko–Pastur bounds move
   across the sample. Events bought by widening the window trade sample size against
   homogeneity.

9. **Nine more provisional labels on top of two.** OQ3 and OQ13 are both open; two of
   FR32's six dates are already flagged `PROVISIONAL` in `epochs.py`. Adding nine more
   un-ruled labels multiplies an unresolved labelling problem by 2.5× instead of solving
   it.

---

## 8. Approval request — FR32 event count

**No amendment has been made. This section asks for one decision.**

### 8.1 Exact current restriction

`docs/SPEC.md:240` FR32 `[v2]` enumerates **six** epochs by name. `EpochId`
(`seraph/shared_types/fusion.py:27`) is a closed `Literal` of those six ids, and
`EvaluationRow.epoch: EpochId` means no seventh epoch can be represented in an evaluation
row at all. D5(b) derives Table A's 4 folds and Table B's 6 folds directly from the
count.

### 8.2 The limitation it creates — and its precise size

At N = 6 the T3 early-warning test has an MDE of **1.0 sd** and **38–43%** power at
δ = 0.5 sd. Effects below ~0.5 sd are therefore untested, not absent, and criteria 8, 9
and 10 of `ACCEPTANCE-MATRIX.md` are unmeetable at this event count. Nine additional
episodes with 100% RMT+Hamilton coverage sit unused inside the existing span.

But the gain is narrower than it first appears, and §6 bounds it from both sides:

* **Upper bound (§6.2).** The ≥ 1.0 sd band is **already saturated at N = 6** (92–93%
  power). More events buy nothing for the claim the project has actually made. The entire
  gain is confined to the 0.5-sd band, where power goes 38% → 97% — and that needs
  **N ≈ 15**; N = 10 only reaches 70%.
* **Realistic value (§6.3).** The N = 15 design's **effective** count is **6** on the
  measured 770-session integral timescale (9 on the optimistic `1/e` scale). So the
  realistic power at δ = 0.5 for the extended set sits much closer to the N = 6 row than
  to the N = 15 row. **Nine nominal events buy roughly one effectively independent
  event.**

* **Against the actual observed result (§6.5).** The causal replay measures 0 warnings
  over 6 epochs. The minimum *detectable* warned rate falls only from 0.50 at N = 6 to
  ~0.33 at N = 15; the system's deficit is that entire 0.33–0.50. **More onsets close none
  of it.** The one upgrade they would deliver — turning *"we cannot tell whether the
  system beats chance"* into *"it demonstrably does not"* — requires the 95% upper bound
  on the per-event warn probability to fall below the 0.14 no-skill rate, which happens
  at **N = 20**. The exogenous record supports at most **N = 15** (17 at a relaxed
  separation rule). **That threshold is unreachable.**

The honest statement of the limitation is therefore: *FR32's six is a specification
choice, not a data limit — but exercising the available headroom would move the MDE by at
most one coarse grid step, would not change any conclusion the project has drawn, and
falls short of the N = 20 needed to sharpen the negative result into a falsifiable one.
The limitation is real and the headroom is real; they do not meet.*

### 8.3 Alternatives, with consequences

| | alternative | consequence | evidence | cost today |
|---|---|---|---|---|
| **A0** | **Do nothing.** Keep six | MDE stays 1.0 sd; criteria 8/9/10 stay unmet; advance-warning claim stays "untestable at n=6". Nothing breaks, no selection-bias exposure, no `shared_types` edit. **Recommended** — §8.4 | §6.2, §6.5 | none |
| **A1** | Keep FR32's six as the **primary** pre-registered evaluation; add tier-1 (N=12) as a **secondary, separately-labelled extended-event sensitivity analysis**, explicitly not the headline | No FR32 text change. **Still requires editing the approval-gated `EpochId` Literal** (§3.2) — there is no other way to type the rows. Table A 4→5, Table B 6→12 | §3.2, §5.4 | one `shared_types` edit; zero re-runs (no pre-reg file exists) |
| **A2** | **Amend FR32** to an explicit N with a stated labelling rule | Closes OQ13 as a side-effect. `EpochId`, `EPOCH_BREAKS`, `preregistration.EPOCHS`, D5(b) fold counts all change. **Free today; after `preregistration.json` is committed it invalidates every existing `EvaluationRow`** | §3.3, §3.4 | zero today, high later |
| **A3** | **Close OQ13 first** with a mechanical labelling rule, then let the rule *generate* the event set | Most defensible — removes risk 1 and risk 2 of §7 at the root, because the list stops being a human nomination. Slowest; needs an agreed exogenous severity criterion that does not read Indian returns | §7.1, §7.2 | highest effort, lowest bias |
| **A4** | **Cross-market replication** (O9 / FR37–38) instead | The only route to genuinely *independent* onsets, and it needs no FR32 change. But of the 15-event set, 10 onsets are **global** and would be common to any second market; the gain is confined to that market's own **domestic** episodes | §5.2, §7.6 | new data acquisition |
| **A5** | **Extend the corpus before 2005** | Technically feasible from 1999-07-29; would add ~1,350 sessions and plausibly 3–4 more exogenously-datable episodes. Blocked by the EOD2 adjustment caveat, and O5 fixes the corpus at 2005–2026 in the same sentence as the six epochs | §4.3, §4.6 | data-acquisition + SPEC change |

### 8.4 The smallest explicit decision required

> **May `seraph/shared_types/fusion.py`'s `EpochId` Literal be extended, and if so, to
> which of the two pre-registered candidate sets — tier-1 only (N = 12) or tier-1 + tier-2
> (N = 15)?**

Everything else follows mechanically from that one answer. Two things should be settled
in the same breath:

1. **OQ13 must close first if A2 or A3 is chosen** — otherwise the repo acquires nine more
   provisional labels on top of the two it already has (§7.9).
2. **Decide before `preregistration.json` is committed.** The change is free today and
   invalidates every ablation result afterwards (§3.3). This is the same timing argument
   `FR35-CONFIG-COUNT-CONFLICT.md` makes for the configuration list.

**Recommendation, for the record: A0 — do nothing to FR32.** This is a change from the
position this audit started with, and §6.5 is what changed it.

The case for A0 over A1 and A2:

* Extending the event count cannot change any conclusion the project has drawn. The
  ≥ 1.0 sd band is saturated at N = 6 (§6.2), and against the measured 0/6 warned rate the
  entire 0.33–0.50 deficit survives every reachable N (§6.5).
* The one genuinely valuable upgrade — a falsifiable *negative* at N = 20 — is
  **unreachable** from the exogenous record (max N = 15, or 17 at a relaxed rule), and
  §6.3's deflation makes the real shortfall worse (N = 15 nominal ≈ N = 6 effective).
* Against that, A1/A2 cost an edit to the approval-gated `EpochId` Literal, nine more
  provisional labels while OQ13 is open, and every selection-bias exposure in §7 —
  converting a clean, defensible *"untestable at n = 6"* into a contestable *"tested at
  n = 15 on a hand-nominated list"*.

**That trade is unfavourable, and the measurement says so rather than the judgement.**

**What to do instead.** The binding constraint is effect size (§6.5), so the productive
routes are the ones that change effect size or add independent realisations — **A4
cross-market replication** (O9/FR37–38), which needs no FR32 change, and the graded
severity response in §6.4, which raises information per event. Both are specification
questions for the C10 owner, not event-count questions.

**What this audit's artefacts are for, if A0 is chosen.** They are the citable evidence
that the six-event limit was *examined and found not to be the binding constraint* —
which is a stronger statement in a report than leaving FR32's six unexamined. §5.2's
candidate table, §6.3's effective-N deflation and §6.5's reachability result are the
material for that paragraph.

---

## 9. What this could not establish

1. **Whether the nine candidates are genuinely "systemic".** No severity criterion exists
   (§7.2), and defining one on Indian returns would reintroduce outcome selection. The
   candidates are admissible by *dating*; their *severity* is unadjudicated.
2. **Whether 2025–26 contains additional non-tariff episodes.** The corpus runs to
   2026-08-21. Any 2025–26 tariff date is a re-slice of epoch 6 (§5.3), and a
   non-tariff 2025–26 candidate would need verification against public record that was not
   available to this audit. **Flagged for human verification.**
3. **Whether pre-2005 data is actually mis-adjusted, and by how much.** The caveat in
   `eod2_client.py:8` is documented, not measured. Quantifying it is the gate on A5.
4. **The real effect size.** §6.2's power curve is parameterised in *injected* sd. The
   corpus's own lead-signal magnitude is unknown — which is exactly why §6.5 is argued on
   the warned-rate metric, where the observed value (0.00) is known, instead of on an
   unobserved sd.
5. **Whether the 0/6 result is itself robust.** §6.5 takes the unified causal replay's
   warned rate of 0.00 and its 0.14 ± 0.13 no-skill expectation as given inputs from
   another workstream; this audit did not re-derive them. If either number moves, §6.5's
   N = 20 reachability threshold moves with it. The arithmetic is re-runnable in two
   seconds with different inputs (`warned_rate_arm(no_skill=…)`).
6. **Whether a graded severity response would actually help.** §6.4 argues it raises
   information per event, which is standard, but the magnitude on this corpus is
   unmeasured and an exogenous severity proxy has not been identified.
7. **The right block length is estimated, not known.** §6.6 uses L = 770, the measured
   `rv_t_yz` integral timescale. The integral timescale is itself a noisy statistic on a
   near-unit-root series, and `ar_t` (495) and `bas_t` (616) give different values. The
   full L sweep is reported rather than a single number for exactly this reason — but if
   the true scale were nearer 250, the overstatement factors would be ~10–20% smaller.
   They would not change any 0.5-exclusion verdict: §6.7 shows pillar/CSRS lose exclusion
   by L = 21–63, far below any defensible scale.
8. **One caveat in log 37 is now superseded.** That log states the `SCA_t` relocation
   null "does not exist yet"; it was run later the same session
   (`warning_null_h15_sca.json`) and §6.8 quotes the measured values. The log is left
   unedited, as the evidence rules require; this note is the correction.

---

## 10. Reproduction

```bash
# arms 1, 2, 3, 3b — spec trace, data-vs-definition, candidates, effective N (~30 s)
.venv/Scripts/python.exe -I scripts/audit_event_coverage.py

# §6.6 — block bootstrap on the replayed pillar/CSRS series, both P2 quantities (~40 min)
.venv/Scripts/python.exe -I scripts/audit_event_coverage.py --bootstrap-only \
    --pillar2 lam1 sca --boot-draws 2000

# §6.7 — exact 0.5-exclusion ledger, parsed from the arm-6 log. Needs no database
.venv/Scripts/python.exe -I scripts/audit_event_coverage.py \
    --exclusion-table docs/evidence/20261013T134906Z-36-block-bootstrap-pillar-csrs.log

# all arms at the authoritative power settings (~25 min; matches the published
# EARLY-WARNING-POWER.md run at 60 draws / 400 AAFT surrogates)
.venv/Scripts/python.exe -I scripts/audit_event_coverage.py --power --draws 60 --perms 400

# §6.3 alone — the effective-N deflation
.venv/Scripts/python.exe -I scripts/audit_event_coverage.py --dependence-only

# §6.5 alone — 0/N detectability. Needs no database
.venv/Scripts/python.exe -I scripts/audit_event_coverage.py --warned-rate-only
```

| log | arms | exit |
|---|---|---|
| `20261013T124358Z-32-event-count-preregistration.log` | pre-registration, **predates the first query** | — |
| `20261013T125145Z-33-event-coverage-audit.log` | 1, 2, 3, 4 (power) | **0** |
| `20261013T130107Z-34-event-count-dependence-deflation.log` | 3b (effective N) | **0** |
| `20261013T133320Z-35-event-count-vs-effect-size.log` | 5 (0/N detectability) | **0** |
| `20261013T134906Z-36-block-bootstrap-pillar-csrs.log` | 6 (block bootstrap, both P2 quantities) | **0** |
| `20261013T135024Z-37-fr18-sca-false-alarm-matched-null.log` | 5 + 5(b2) (false-alarm-matched null) | **0** |
| `20261013T183324Z-38-auc-05-exclusion-accounting.log` | 6b (exact 0.5 ledger) | **0** |

Read-only: every database statement in the script is a `SELECT`. Each log carries the
exact command, start and finish timestamps in UTC, the git HEAD (`f3eaac8`) and the real
observed exit code. Nothing was committed, staged or pushed.
