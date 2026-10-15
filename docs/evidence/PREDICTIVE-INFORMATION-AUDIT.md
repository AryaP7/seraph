# Predictive-information audit — is there anything to fuse?

**Answer: no. Within the data this repository holds, there is no detectable
pre-onset information in any available input.** Of 19 features audited — all
three pillars, all four FR17/FR18 RMT statistics, five simple market baselines,
India VIX and two VIX transforms, and four further market variables — **zero
classify as changing BEFORE onset**, and **all 19 have a T3 advance-warning AUC
below the 95th percentile of their own no-signal distribution.**

The smallest p-value over two calibrated nulls is **0.0630**, so nothing reaches
even an *uncorrected* 0.05. Holm survivors over 19 comparisons: **none**.

This completes the negative. The previous phase showed no *architecture* over
these inputs produces advance warning; this shows there is no *signal* in the
inputs for an architecture to use. Those are different claims and both are now
measured.

**Status: EXPLORATORY.** This is a screen over inputs the repository already
has, run to decide what deserves a fresh pre-registration. It establishes that
nothing here warrants one. Nothing below is confirmatory evidence and none of it
may be cited as such.

Settled 2026-10-14 on git `f3eaac8`. Database read-only; `seraph/` unmodified.

| artefact | path |
|---|---|
| timing audit | `scripts/audit_predictive_information.py` |
| ranking screen | `scripts/rank_predictive_candidates.py` |
| results | `docs/evidence/signals/predictive_information_audit.json`, `candidate_ranking.json` |
| logs | `*-101-predictive-information-audit.log`, `*-102-candidate-ranking.log` |

```
python scripts/audit_predictive_information.py
python scripts/rank_predictive_candidates.py --perms 2000
```

---

## 1. Phase 1 verification — the full suite now has a completed result

Two earlier single-process runs were stopped by the harness on low system memory
(**2.37 GB free of 15.8 GB**; `vmmemWSL` alone held 3.0 GB). A partial run is not
a result, so the suite was run in **three exhaustive, non-overlapping foreground
chunks**:

| chunk | scope | result | time |
|---|---|---|---|
| A | `tests/` minus `tests/contract` minus the three `test_c7_hamilton*` files | 148 passed, 2 xfailed | 25.3 s |
| B | the three Hamilton files | 26 passed | 637.5 s |
| C | `tests/contract` | 46 passed, **1 failed** | 180.8 s |
| **total** | | **220 passed, 1 failed, 2 xfailed** | 843.6 s |

**220 + 1 + 2 = 223, which equals the collection count exactly** — no test was
skipped, double-counted or lost. The arithmetic is recorded in
`*-100-suite-COMPLETE-chunked.log`. The single failure is the deliberately
preserved CT-3; both xfails are `strict=True` pins on open specification
questions (D-1b, D-2). The killed partial run is preserved as
`*-90-...-INCOMPLETE-KILLED-LOW-MEMORY.log`.

Both pre-registration hashes verify unchanged and are correctly cited:
`FUSION-PREREGISTRATION.md` → `3d8e8de3…`, addendum → `26910c6a…`.

---

## 2. Coverage and data-availability report

### What auxiliary data actually exists

Audited directly rather than from documentation, because several tables are
named in specifications but empty:

| table | rows | usable? |
|---|---|---|
| `rmt_output` | 5,363 | yes, 2005-01-03 .. 2026-08-21 daily |
| `hamilton_output` | 5,365 | **pre-fix degenerate**; the causal series used is the POSTFIX `.npz`, **2013-01-14+** |
| `hawkes_output` | 473 | yes but **every 5 sessions**, 2017-02-09+ |
| `daily_prices` | 8,023,206 | yes, 1995+ |
| `intraday_bars` | 18,781,302 | yes, 2015-02-02+ |
| `macro_covariates` | 5,363 | **only `india_vix` is populated** (3,034 rows) |
| `flow_aggregates` | **1** | **no** — a single row dated 2026-10-12 |
| `tariff_events` | **0** | **no** |
| `microstructure_state` | **0** | no |
| `regulatory_action_log` | **0** | no |
| `validation_results` | **0** | no (nothing written yet) |

Two findings that bear directly on what inputs are even *possible*:

* **FR45's FII/DII flow data has no history at all.** `flow_aggregates` holds
  **one row**, dated 2026-10-12 — a single live snapshot, not a series. Flow
  information is therefore **not** an available candidate input; it would be an
  acquisition.
* **`tariff_events` is empty**, so O8/FR22's `G_t` covariate has no event table
  and `g_t`/`g_t_sector_weighted` are 0 non-null in `macro_covariates`.
* `daily_prices.log_return_std` and `yz_volatility` are **0 non-null** — the
  precomputed volatility columns were never filled; features are derived on the
  fly, which is fine but means the columns are not a data source.

### India VIX — point-in-time availability

| property | value |
|---|---|
| rows | 3,034, **100% dense in range** |
| span | **2014-05-15 .. 2026-08-21** |
| epochs covered | 4 of 6 — **not** `gfc_2008`, **not** `taper_2013` |
| publication delay | none material: NSE disseminates India VIX intraday; the daily close is available at the 15:30 IST decision time |
| revisions | none — index values are not restated |
| survivorship | not applicable (an index level, not a cross-section) |

**Note a specification discrepancy:** SPEC OQ5 states "India VIX starts
Nov 2007" and discusses dropping or substituting it for the 2008 epoch. The
**ingested** series starts **2014-05-15**, six and a half years later, so the
OQ5 discussion is based on a longer history than the repository has. This does
not change any conclusion here — VIX is anti-predictive on the epochs it *does*
cover — but the gap should be recorded.

### Per-epoch pillar coverage, stated so no result is overclaimed

| epoch | onset | RMT | Hamilton (causal) | Hawkes | India VIX |
|---|---|---|---|---|---|
| gfc_2008 | 2008-09-15 | yes | **no** (series starts 2013-01-14) | **no** | **no** |
| taper_2013 | 2013-05-22 | yes | **no** (88 days of history) | **no** | **no** |
| ilfs_2018 | 2018-09-21 | yes | yes | sparse (7 obs in ±30d) | yes |
| covid_2020 | 2020-02-20 | yes | yes | sparse (8) | yes |
| tightening_2022 | 2022-01-05 | yes | yes | sparse (8) | yes |
| tariff_2026 | 2026-02-01 (**PROVISIONAL**, OQ3 open) | yes | yes | sparse (9) | yes |

**No epoch before 2018 received a three-pillar evaluation, and none is claimed.**
The 2008 and 2013 epochs are RMT-only in any causal replay.

---

## 3. The timing audit — not one feature moves before onset

Each feature measured in three disjoint windows around every onset, in units of
the **local** standard deviation (±1 trading year around the onset, with all
three event windows excluded). A local baseline is required: a 21-year global
baseline manufactures a negative separation for `λ₁/N` from era composition
alone, since four of six onsets sit in its low-mean era (`CRISIS-REPLAY.md` §5c).

| feature | onsets | **BEFORE** (−15d) | DURING (0..+30) | AFTER (+31..+60) | class | epochs with BEFORE > 0 |
|---|---|---|---|---|---|---|
| P1 hawkes `n/(1−n)` | 4/6 | −0.128 | +0.406 | −0.148 | DURING | 1/4 |
| P2 rmt `λ₁/N` | 6/6 | **−0.620** | −0.401 | +0.198 | AFTER | 1/6 |
| P2 rmt `SCA_t` | 6/6 | −0.077 | +0.534 | +0.382 | DURING | 3/6 |
| P2 rmt `F_t` | 6/6 | −0.304 | −0.059 | +0.036 | AFTER | 2/6 |
| P2 rmt `V_eig` | 6/6 | −0.579 | +0.353 | +0.200 | DURING | 3/6 |
| P2 rmt `Ω_t` | 6/6 | +0.171 | +0.332 | +0.095 | DURING | 3/6 |
| P3 hamilton `LSD` | 5/6 | −0.392 | +0.692 | +0.079 | DURING | 1/5 |
| B `rv_20` | 6/6 | −0.028 | +1.499 | +1.777 | AFTER | 3/6 |
| B `drawdown` | 6/6 | −0.018 | +0.508 | +0.940 | AFTER | 3/6 |
| B `semivar_20` | 6/6 | −0.118 | **+2.138** | +1.643 | DURING | 3/6 |
| B `rv_accel_5` | 6/6 | +0.004 | +0.740 | −0.541 | DURING | 4/6 |
| B `dd_accel_5` | 6/6 | +0.286 | +0.859 | −0.007 | DURING | 5/6 |
| V `india_vix` | 4/6 | **−0.613** | +1.777 | +2.544 | AFTER | **0/4** |
| V `vix_accel_5` | 4/6 | +0.241 | +1.467 | −0.574 | DURING | 2/4 |
| V `vix_ratio_60` | 4/6 | **+0.432** | **+4.187** | +2.167 | DURING | **4/4** |
| M `dispersion` | 6/6 | −0.146 | +0.452 | +0.316 | DURING | 2/6 |
| M `frac_down` | 6/6 | +0.161 | +0.332 | −0.073 | DURING | 4/6 |
| M `frac_down_3pct` | 6/6 | +0.074 | +0.980 | +0.372 | DURING | 4/6 |
| M `turnover_ratio_60` | 6/6 | −0.030 | +0.204 | −0.036 | DURING | 3/6 |

**Zero features classify as BEFORE.** Every one is DURING or AFTER.

The contrast is the point: the DURING column reaches **+4.187σ**
(`vix_ratio_60`) and **+2.138σ** (`semivar_20`), while the largest BEFORE value
anywhere is **+0.432σ**, an order of magnitude smaller. **These features detect
crises spectacularly and anticipate them not at all.**

### India VIX refutes the forward-looking hypothesis directly

The mandate asked for forward-looking inputs to be investigated while warning
against assuming a feature is predictive *because* it is forward-looking by
construction. India VIX is the test case, and it fails in the most informative
way: option-implied, genuinely forward-looking, and its **BEFORE separation is
−0.613σ with 0 of 4 epochs positive**, against +1.777 DURING and **+2.544
AFTER**.

**India VIX is lowest before onsets, high during them, and highest afterwards.**
Implied volatility in this sample is a *lagging* measure — it reprices after
realised stress arrives, not before. Being forward-looking by construction did
not make it forward-looking in fact.

---

## 4. The ranking screen — all 19 sit below their own no-signal distribution

T3 advance-warning AUC against two calibrated nulls: **relocation** (common
circular shift of the onsets; measured type-I 8% at nominal 5%) and **AAFT**
(onsets fixed, series phase-randomised preserving its exact marginal). 2,000
permutations, resolution floor 0.00050. In-crisis days dropped.

Ranked by the worse of the two p-values — **exploratory order, not a result**:

| rank | feature | T3 AUC | p (worst) | AUC − own null p95 |
|---|---|---|---|---|
| 1 | M `frac_down` | 0.5560 | 0.0630 | **−0.0034** |
| 2 | B `dd_accel_5` | 0.6005 | 0.0650 | −0.0085 |
| 3 | B `drawdown` | 0.6322 | 0.0820 | −0.0247 |
| 4 | P2 rmt `Ω_t` | 0.5934 | 0.0979 | −0.0237 |
| 5 | V `vix_accel_5` | 0.5847 | 0.1189 | −0.0210 |
| 6 | P3 hamilton `LSD` | 0.5978 | 0.1519 | −0.0485 |
| 7 | M `frac_down_3pct` | 0.5516 | 0.1659 | −0.0372 |
| 8 | V `vix_ratio_60` | 0.5609 | 0.2834 | −0.1074 |
| 9–15 | `V_eig`, `SCA_t`, `rv_accel_5`, `turnover_ratio_60`, `semivar_20`, `rv_20`, `dispersion` | 0.47–0.53 | 0.31–0.66 | −0.04 to −0.19 |
| 16 | P2 rmt `λ₁/N` | 0.4340 | 0.7841 | −0.2026 |
| 17 | V `india_vix` | 0.4057 | 0.8536 | −0.2305 |
| 18 | P2 rmt `F_t` | 0.3791 | 0.9061 | −0.2608 |
| 19 | P1 hawkes `n/(1−n)` | 0.3805 | 0.9470 | −0.2341 |

**Every single entry in the last column is negative.** Each feature's observed
AUC sits *below* the 95th percentile of its own no-signal distribution, so none
can be distinguished from no signal at all.

**The smallest p-value is 0.0630 — nothing reaches even an uncorrected 0.05**,
let alone Holm's tightest threshold of 0.00263 over 19 comparisons. Holm
survivors: **none**.

### Why a high AUC is not enough, and this table shows it

`drawdown` has the **highest** raw T3 AUC at 0.6322 — and its own null's 95th
percentile is **0.6569**. A strongly persistent feature produces a wide null,
because a near-random-walk will often happen to be elevated before any date you
nominate. Reading 0.6322 as skill would be the exact error these nulls exist to
prevent. The same applies to `Ω_t` (0.5934 against a 0.6171 null) and
`hamilton LSD` (0.5978 against 0.6463).

---

## 5. Exploratory versus confirmatory — what this does and does not license

**Exploratory (this document).** A screen over 19 existing inputs against the
six known crises. Its purpose is to decide what deserves a fresh
pre-registration. Its answer is **nothing does**.

**Not confirmatory, and not claimed as such.** No feature here has been
evaluated on a period untouched by this selection, because none screened
positively enough to justify spending an untouched period on it. If any future
work revisits one of these features it needs its own pre-registration with an
untouched evaluation window, exactly as `FUSION-PREREGISTRATION.md` did.

**Statistical limits, stated rather than discovered later.**
* Six onsets, **N_eff ≈ 5** at the measured 770-session integral timescale. Every
  separation above is one of a handful of effectively independent observations.
* The T3 test's measured minimum detectable effect is ~1.0 sd against a
  rectangular step and ~1.0 sd against a 75-session ramp (power 75–77%); at
  0.5 sd power is 47–50%. **The largest BEFORE separation observed anywhere is
  0.432 sd**, i.e. below the threshold at which this test has useful power. So
  the honest statement is: *no input shows pre-onset information, and an effect
  smaller than ~0.5 sd would not be detectable here either way.*
* Two epochs (2008, 2013) have no Hawkes, no causal Hamilton and no VIX, so for
  those features the audit rests on 4 of 6 onsets.
* `tariff_2026`'s label is PROVISIONAL (SPEC OQ3 open).

---

## 6. What this means for the architecture

**Pillar identity unchanged.** P1 Hawkes, P2 RMT and P3 Hamilton remain the
three pillars in `PILLAR_ORDER`. Nothing was removed, renamed or replaced. The
market variables audited here are **comparators**, not pillar candidates, and
none is proposed for promotion.

**Equal-weight fusion remains the reference baseline**, per
`FUSION-ARCHITECTURE.md`. Phase 4's precondition — "only after a candidate input
demonstrates credible, causal pre-onset information should you evaluate whether
adding it improves the existing system" — **is not met by any input**, so no
further fusion experiment is justified and none was run.

**The two negatives compose.** The fusion phase showed that no architecture over
these inputs warns. This phase shows the inputs contain nothing to warn with.
Together they close the space: within the data this repository holds, advance
warning is not achievable, and the limiting factor is the information content of
the inputs rather than the method applied to them.

---

## 7. Recommendation for the next approved experiment

**Do not run another fusion search, feature transform, or threshold study on
these inputs.** All three have now been excluded, and a fourth attempt would be
tuning against six known crises.

The only route that could change the conclusion is **new data with genuine
pre-onset content**, and the audit narrows what that means. Ranked by expected
information per unit of acquisition cost:

1. **Option-implied *skew* and term structure, not the VIX level.** India VIX's
   level is lagging (−0.613σ before, +2.544σ after). But a *level* discards the
   two things that are theoretically forward-looking: the **put-call skew**
   (demand for crash protection) and the **term-structure slope** (near-dated
   versus far-dated implied vol, which inverts under stress). Neither is in the
   repository. NSE options data would be an acquisition; the question is cheap
   to scope and the hypothesis is specific and falsifiable.
2. **Funding and liquidity indicators.** Nothing of this kind exists in the
   repository (`macro_covariates` has `rbi_repo_rate` at **0 non-null**). An
   interbank-spread or CP-spread series is the classic pre-crisis stress channel
   and is absent. RBI publishes candidates; publication delay must be audited
   before use, since a weekly series lagged two weeks cannot support a 5–15 day
   lead window.
3. **Cross-market replication (O9/FR37–38).** The only route that adds genuinely
   *independent* realisations rather than more onsets on the same ~7 independent
   blocks — Workstream B measured that nine additional Indian episodes buy
   roughly **one** effectively independent event, while 10 of 15 candidate
   onsets are global and would be common to any second market.
4. **FII/DII flow — but note it does not currently exist.**
   `flow_aggregates` holds **one row**. FR45 is unvalidatable as things stand,
   and flow would be an acquisition from scratch, not an audit of held data.

**Before any of these is built, two cheap prerequisites.** (a) Fix the
alert scale (`CRISIS-REPLAY.md` gate 1) so a new input can be evaluated against
an interpretable alarm. (b) Shorten Hawkes's refit cadence
(gate 2) so Pillar 1 stops being *untestable* — currently worse than negative.

**And a specification question that should be settled regardless:** the project
has now established, with calibrated nulls at every layer, that its stated
objective O5 (advance warning) is not achievable on the available data. O3
(contemporaneous spectral monitoring) and the detection objectives **are**
supported — `semivar_20` separates crises at +2.138σ and `vix_ratio_60` at
+4.187σ. Whether SERAPH should be re-scoped around contemporaneous systemic-risk
*monitoring*, with advance warning recorded as tested and not achieved, is an
owner decision and not one this analysis can make.
