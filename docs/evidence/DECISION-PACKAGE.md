# Decision package — what to do after the predictive-information audit

**Documentation only. No production code, specification, test or
pre-registration artefact was changed. Nothing committed or pushed.**

Written 2026-10-14 on git `f3eaac8`. Database read-only throughout; `seraph/`
unmodified (still the three files changed before this work began).

---

## 1. The recommended next step, and why

**Recommendation: do not acquire new data yet. Spend one short cycle resolving
the two prerequisites, and in the same cycle settle the objective-scope question
in §5. Only then commit to an acquisition.**

That is a deliberately conservative recommendation and the reasoning is
specific, not cautious-by-default:

1. **The highest-ranked acquisition candidate probably cannot cover the epochs
   that matter.** SERAPH's two pre-2015 epochs (`gfc_2008`, `taper_2013`) are
   the only ones not already covered by India VIX. Nothing in the public record
   I could verify establishes that strike-level option-chain implied volatility
   is available for India back to 2008 (§3, candidate 1). **If it is not, an
   options-derived skew feature covers the same four post-2015 epochs on which
   India VIX is already measurably *anti*-predictive** (−0.613σ before onsets,
   T3 AUC 0.4057, p = 0.8536). Buying data that cannot add an independent epoch
   would be the expensive version of the mistake this project has just spent
   three phases avoiding.
2. **One prerequisite is nearly free and changes what "Pillar 1 is untestable"
   means** (§4.1). It turns out not to be a refit-cadence problem at all.
3. **The other prerequisite is required before any new input can be judged**
   (§4.2): an alert threshold crossed on 57–62% of days cannot adjudicate
   anything, new input or old.
4. **A scope decision is pending that could change what "next step" even means**
   (§5). O5 has now been tested at three layers and failed at all three, while
   the detection objectives are well supported. Acquiring data to pursue O5
   before the owner decides whether O5 is still the objective risks spending on
   a goal that may be retired.

**Verification performed for this package:** repository state, worktree
integrity, database row counts, both pre-registration hashes, the Hawkes
autocorrelation measurement in §4.1, the specification text for FR10/FR11/FR13/
NFR4/FR18, and the engine source for `excitation_path`/`mts`. All read-only.

---

## 2. What the evidence already settles, so it is not re-litigated

Stated once, with sources, because every option below is judged against it.

| question | answer | evidence |
|---|---|---|
| Does any held input move before onset? | **No.** 0 of 19 classify as BEFORE (14 DURING, 5 AFTER) | `PREDICTIVE-INFORMATION-AUDIT.md` §3 |
| Is any held input distinguishable from no signal on T3? | **No.** All 19 below their own null p95; smallest p 0.0630, under *no* correction | ibid. §4 |
| Does any fusion architecture help? | **No.** 5 designs × 4 budgets × 2 Pillar 2 quantities → 0 warnings | `FUSION-ARCHITECTURE.md` |
| Can learned weights be estimated? | **No.** 90% bootstrap intervals of mean width **0.983** on a [0,1] scale | ibid. §2 |
| Was the rank scale the blocker? | **No.** D′ on raw unbounded magnitudes still warned 0 of 5 | ibid. §5b |
| Would more Indian onsets help? | **No.** N_eff ≈ 5; nine more buy ≈ one; the decisive threshold N = 20 is unreachable | `EVENT-COUNT-LIMITATION.md` |
| Is contemporaneous detection supported? | **Yes.** `semivar_20` +2.138σ, `vix_ratio_60` +4.187σ during crisis windows | `PREDICTIVE-INFORMATION-AUDIT.md` §3 |

**SERAPH has not demonstrated advance-warning capability, and nothing in this
package claims otherwise.**

---

## 3. Ranked acquisition shortlist

**Reading the cost column.** I could verify *existence* for several sources but
**not a single price**, and **not the historical depth** that actually decides
each go/no-go. Everything is marked:

* **VERIFIED** — confirmed from a primary or near-primary public source this session.
* **UNVERIFIED** — plausible and named, but not confirmed; must be checked before commitment.
* **UNKNOWN** — I could not establish it at all. No figure is invented in its place.

### Candidate 1 — Option-implied skew and term structure

**Hypothesis.** India VIX's *level* is a 30-day at-the-money implied volatility
and is measurably lagging here (+2.544σ *after* onsets, −0.613σ before). But a
level discards the two components with a theoretical claim to leading
behaviour: **put-call skew** (the price of crash protection, which should rise
as protection is demanded, before realised stress) and the **term-structure
slope** (near-dated vs far-dated implied vol, which inverts under stress). These
are different quantities from the level, not transforms of it, so the level's
failure does not pre-judge them.

**Fields required.** Per trading day, per NIFTY option expiry: strike, option
type, settlement/close price, implied volatility, open interest, and the
underlying close — sufficient to construct 25-delta risk reversal and a
near/far implied-vol ratio. Timestamps must be end-of-day at or before 15:30 IST.

**Sources.**
* **VERIFIED** — NSE sells a paid end-of-day product covering the Futures &
  Options segment, generated in binary format at day end; enquiries to
  `marketdata@nse.co.in` / +91-22-2659 8385. **Price UNKNOWN — not published.**
* **VERIFIED** — F&O bhavcopy is fetchable per date and third-party wrappers do
  this (the R package `nser`). One wrapper documents an *equity* range of
  2016-01-01 to 2024-07-05 — **a package range, not NSE's archive depth** — and
  reports scripted access as unreliable (a 2021 fetch timed out).
* **UNVERIFIED** — third-party option-chain history with strike-level IV
  (niftytrader, stockmojo). Depth, licensing and reliability all unconfirmed.
* **UNKNOWN** — whether strike-level IV exists for India back to **2008**. This
  is the decisive fact and I could not establish it.

**Coverage / look-ahead risks.** Settlement prices are end-of-day and not
restated, so point-in-time availability is clean *if* the archive is genuine
EOD. Illiquid far strikes produce unstable IVs; a skew built from thin quotes is
noise. No survivorship concern for index options.

**Integration effort.** Moderate: a new ingestion path, a skew/term-structure
feature in C4, and no change to the pillars.

**Minimum viable dataset.** Daily NIFTY option chain with strike-level IV
covering **at least 2008-01-01 onward**, ≥ 5 strikes either side of the money on
the two nearest expiries.

**GO only if** pre-2015 strike-level IV is confirmed available. **NO-GO if**
coverage starts after ~2015: the feature would then span only the four epochs on
which India VIX already fails, adding no independent episode, and the audit's
conclusion would be untestable-by-construction rather than tested.

### Candidate 2 — Funding and liquidity stress indicators

**Hypothesis.** Funding stress is the classic pre-equity-crisis channel:
interbank and commercial-paper spreads widen as balance-sheet capacity is
withdrawn, typically before equity volatility reprices. This is the one
mechanism with a prior reason to *lead* rather than coincide, and SERAPH holds
nothing of the kind — `macro_covariates.rbi_repo_rate` is **0 non-null**.

**Fields required.** Daily (or at worst weekly) call money / MIBOR, 1-month and
3-month commercial-paper rates, and T-bill yields, with **publication
timestamps**.

**Sources.**
* **UNVERIFIED** — RBI's Database on Indian Economy (`dbie.rbi.org.in`) is the
  expected home for these series. My search did not resolve the portal, its
  series codes or its export mechanics; it must be checked directly.
* **VERIFIED (as evidence the series exist, not as a source)** — third-party
  daily debt dashboards quote call rate, MIBOR, CBLO and 1-month CP side by
  side, sourced to "Bloomberg and RBI press releases". These are PDF snapshots,
  **not a downloadable history**, and are unusable as a feed.
* **UNKNOWN** — whether a continuous daily CP series reaches 2008, and all costs.

**The decisive risk is publication delay, not price.** A weekly series published
with a two-week lag **cannot** support FR32's 5–15 trading-day lead window: the
value would not have existed at the simulated decision time. This must be
audited *before* acquisition, not after.

**Minimum viable dataset.** Daily call/MIBOR and 1-month CP from 2008-01-01,
with a documented publication lag of **≤ 2 trading days**.

**GO only if** the publication lag is ≤ 2 trading days and daily frequency
reaches 2008. **NO-GO** on a weekly series, or any lag that exceeds the lead
window it is meant to populate.

### Candidate 3 — Cross-market stress and independent episodes (O9/FR37–38)

**Hypothesis.** This is the only candidate that addresses the *sample*, not the
features: it adds genuinely independent realisations rather than more onsets on
the same ~7 independent blocks.

**Measured caveat that bounds the gain.** Workstream B found **10 of 15**
candidate onsets are global and would be common to any second market; only ~5
are domestic. So a second market adds far less independence than the headline
event count suggests.

**Sources.** **UNKNOWN / out of scope to verify here** — a second market's
equity history plus whatever pillar inputs it needs. Likely the largest
integration effort of the four.

**Minimum viable dataset.** One additional market with ≥ 15 years of daily
constituent prices and ≥ 3 *domestic* stress episodes not shared with India.

**GO only if** ≥ 3 genuinely independent domestic episodes are identifiable from
exogenous public record *before* any SERAPH signal is computed on that market.

### Candidate 4 — FII/DII flows

**Hypothesis.** Foreign-institutional outflow is often described as a leading
indicator of Indian equity stress.

**Status in the repository: does not exist.** `flow_aggregates` holds **1 row**,
dated 2026-10-12 — a single live snapshot. **FR45 is unvalidatable on held data
and this is an acquisition from scratch, not an audit.**

**Sources.**
* **VERIFIED** — NSE publishes daily provisional FII/DII activity after market
  close; MSEI publishes a combined NSE/BSE/MSEI report that **flags the data
  provisional and subject to change** and points to NSDL/CDSL for final FPI
  figures.
* **VERIFIED** — an academic dataset (Mendeley) covers daily FII/DII
  **2018–2024**, restricted to NIFTY 50 constituents.
* **UNVERIFIED** — third-party archives (StockZee and similar); depth unclear.
* **UNKNOWN** — NSE's own archive start date, and all costs.

**The disqualifying risk is revision.** The daily figure is **provisional and
restated**. A revised series is a look-ahead trap: the value used in replay must
be the provisional one published at the time, not the final one. Unless a
vintage-preserving source is found, this candidate cannot be evaluated causally.

**Minimum viable dataset.** Daily FII and DII net figures from 2008-01-01 **as
first published**, with revision vintages retained.

**GO only if** a vintage-preserving source is found. **NO-GO otherwise** — this
is ranked last for that reason, not for lack of a plausible hypothesis.

---

## 4. The two prerequisite engineering proposals

### 4.1 Hawkes cadence — the question turns out to be the wrong one

**What was asked:** quantify the consequences of shortening the refit cadence.
**What the measurement shows:** shortening it would add rows and almost no
information, and the real conformance gap is elsewhere.

Measured on the existing 473-refit series (read-only):

| quantity | value |
|---|---|
| autocorrelation between **adjacent** refits (5 sessions apart) | **ρ = +0.9843** |
| data shared by adjacent 500-day windows | **99.0%** |
| data that *would* be shared at `refit_every = 1` | **99.8%** |
| mean \|Δn\| between adjacent refits | 0.00157 |
| corpus sd of `n` | 0.01757 |
| share of total variation appearing between adjacent refits | **9.0%** |
| lag at which the series decorrelates | ~50 refits ≈ **250 sessions** (ρ = 0.0755) |
| non-overlapping 500-day windows in the whole span | **≈ 4.7** |

**Consequence.** A 1-session refit multiplies `hawkes_output` five-fold and
interpolates between points already correlated at 0.984. The estimate's
independence is governed by the **500-day window**, not the refit interval, so
the span holds roughly **5 independent Hawkes observations** and a 15-day
pre-onset window holds **none** at any cadence. **Shortening the cadence would
convert Pillar 1 from `UNTESTABLE` to a measurable zero — which has
reportability value and no predictive value, and must not be sold as the
latter.**

**Cost (from the repository's own measurement, `HAWKES-WINDOW-SELECTION.md`).**
17.14 s/fit at the 500-day window; a daily refit over the corpus costs
**818 minutes (≈13.6 h)** against **164 minutes** at `refit_every = 5`. One-off,
no new data required.

**The actual conformance gap, and it is not the refit cadence.** FR13 `[v4]` and
NFR4 both specify Hawkes **emission at bar frequency**; `hawkes_output` holds
473 roughly-weekly rows. But `MTS_t = n/(1−n)` is a function of the *fitted
parameters only* (`seraph/pillars/hawkes/engine.py:320`), so "emit MTS at bar
frequency" resolves three ways:

| option | effect |
|---|---|
| (a) repeat the piecewise-constant MTS per bar | conforms textually, adds **nothing** |
| (b) refit per bar | computationally infeasible |
| (c) emit the **conditional intensity** `λ_t` | genuinely time-varying per bar even at fixed parameters; **already implemented** as `excitation_path()` (engine.py:214, "lambda_t under the geometric kernel, reset at each session open"); never persisted |

**Option (c) is the substantive proposal**, and it has precedent: FR14's sector
flags already use realised-intensity-over-baseline rather than the parameter
(engine.py:398–402). But `λ_t` is **a different quantity from `MTS_t`**, so
adopting it is a specification change, not a free fix.

**Approval gate.** FR13 names `MTS_t`; emitting `λ_t` instead, or in addition,
requires the FR13/NFR4 owner's decision. **Also note FR13 `[v4]` already states
Pillar 1 is "a contagion / risk-state diagnostic contributing to the CSRS, **not**
an independently demonstrated forward alarm", citing a pre-registered test that
found approximately no skill at 15m/30m/1h/2h horizons.** My daily-horizon
result (Hawkes T3 AUC 0.3805, p = 0.9470) extends that same finding to the 15-day
horizon. **The specification has already conceded this point**; the cadence work
should therefore be framed as improving CSRS input resolution, not as rescuing a
forward alarm. **Owner: B (C5) with the SPEC owner.**

**Recommendation.** Do **not** shorten the refit cadence for its own sake.
Instead: (i) ask the FR13 owner whether `λ_t` should be emitted; (ii) if yes,
screen `λ_t` for pre-onset content under the §6 protocol *before* any production
change. Cheap, and it tests the hypothesis rather than assuming it.

### 4.2 Making CSRS alert thresholds interpretable

**The problem, measured.** C9 applies absolute constants
(`PROVISIONAL_AMBER = 0.5`, `PROVISIONAL_RED = 0.75`,
`seraph/fusion/score.py:35–36`) to a composite built from FR28 ECDF **ranks**.
Consequences already measured: the amber threshold is crossed on **57–62% of all
days**; Brier skill score **−11.64**; ECE **0.575** against a crisis base rate of
**3.36%**; and in the fusion work the escalation arms saturated at exactly 1.0
because a rank has nothing above it (`FUSION-ARCHITECTURE.md` §5).

**The distinction that has to be made explicit.** A **normalised risk score**
answers "how unusual is today relative to its own recent history" — which is
what an ECDF rank is, and it is scale-free and self-normalising. A **calibrated
probability** answers "what fraction of days like today are followed by the
labelled event" — which requires a fitted mapping and a validation of that
mapping. **A rank is not a probability and cannot be made into one by choosing a
different threshold.** The two must stay separate objects.

**Options, with the validation each requires.**

| option | what it is | validation required | cost |
|---|---|---|---|
| **(1) Causal quantile thresholds** | replace the absolute constants with "exceeds the trailing 5-year *q*th percentile", *q* fixed in advance | a leakage test that index *t* is excluded from its own threshold (already written: `tests/test_replay_causality.py`), and an alert-rate report at several *q* | low; already prototyped as Rule B in `CRISIS-REPLAY.md`, which gives 4–12% of days under alert instead of 57–62% |
| **(2) Keep the score, add a separate calibrated probability** | leave CSRS as a rank; fit `P(event \| CSRS)` as a *distinct* field | a reliability curve, Brier/ECE **on an untouched period**, and a training span — which at N_eff ≈ 5 events is not currently available | high, and **not currently feasible**: the audit shows nothing to calibrate against |
| **(3) Document CSRS as an uncalibrated ordinal monitor and remove the probability-like framing** | no code change; the alert levels become explicit relative bands | a documentation pass asserting no probabilistic interpretation | lowest; honest; does not improve operability |

**Recommendation: (1) now, (3) alongside it, and (2) only if an input with
pre-onset content is ever found.** (1) makes the alert interpretable as "unusual
relative to its own history", which is what the score actually measures; (3)
stops the rank being read as a probability; (2) is premature because there is
currently no signal to calibrate.

**Explicitly not done here.** `score()`'s signature already takes
`amber_threshold` / `red_threshold` as parameters, so (1) is expressible without
changing the function contract — but **C9 is owner D's component and
`alert_level` semantics are part of the frozen scoring contract**, so no change
was made. **Owner: D (C9).**

**A sequencing note.** `FUSION-ARCHITECTURE.md` §5b is the evidence that the
scale fix is **not** a route to advance warning — candidate D′ on a resolving
raw scale still warned 0 of 5. Fix it for interpretability, and do not let it be
proposed as a predictive improvement.

---

## 5. What can proceed now, what needs approval, what needs external data

### Can proceed now — no approval, no new data

* The `λ_t` pre-onset screen (§4.1), under the §6 protocol, **as a research
  experiment that changes nothing in `seraph/`**. It is the only remaining
  held-data hypothesis the audit did not cover, because the audit screened the
  *parameter* `n/(1−n)` and not the *conditional intensity*.
* A publication-delay audit for candidate 2 — a desk exercise on RBI's portal,
  no purchase required, and it is the gate that decides that candidate.
* Confirming option-chain historical depth for candidate 1 — the single fact
  that decides the highest-ranked acquisition.
* The Kalman filter-consistency check (`ACCEPTANCE-MATRIX.md` §5 item 5), which
  closes acceptance criterion 10 without inventing a probability.

### Needs owner approval

| gate | owner | blocking? |
|---|---|---|
| FR35 Table B fold count | D (C10) | **yes** — blocks the ablation and `preregistration.json` |
| C9 alert scale (§4.2) | D | blocks interpretation of every operational statistic |
| FR13/NFR4 Hawkes emission quantity (§4.1) | B + SPEC owner | blocks the `λ_t` proposal going to production |
| FR18 `SCA_t` vs `λ₁/N` conformance | A (C6) | not blocking; conformance + detection only |
| SPEC §4 coverage matrix (Hamilton pre-2015) | C + D | not blocking |
| SPEC OQ3 (epoch-6 label) | OQ13 owner | blocks reporting any epoch-6 result |
| **Objective scope: is O5 still the objective?** | SPEC §2 owner | **the decision this package exists to surface** |

### Needs external data

Everything in §3. **None of it should be purchased before the two go/no-go facts
in §3 candidates 1 and 2 are confirmed**, because both can be checked for free.

---

## 6. Stop conditions — stated now, before any acquisition

The mandate asks for explicit stop conditions. These are the ones I would hold
this project to:

1. **Stop candidate 1** if strike-level option IV does not reach pre-2015. It
   would then cover only the four epochs where India VIX is already
   anti-predictive, and could not add an independent episode.
2. **Stop candidate 2** if the publication lag exceeds 2 trading days or the
   series is weekly. It cannot populate a 5–15 day lead window it is not
   available inside.
3. **Stop candidate 4** unless a vintage-preserving FII/DII source is found.
   Provisional-and-restated data cannot be replayed causally.
4. **Stop candidate 3** unless ≥ 3 genuinely *domestic* episodes are datable
   from exogenous record in the second market, given 10 of 15 candidate onsets
   are global.
5. **Stop the advance-warning programme entirely** if two acquired inputs, each
   with a prior mechanistic reason to lead, both fail the §6 protocol. At that
   point the evidence would support the conclusion that daily-frequency Indian
   equity data does not contain exploitable pre-onset information at six events,
   and further spending would not be justified.
6. **Stop any individual candidate** that cannot satisfy the §6 protocol's
   minimum coverage — ≥ 4 epochs with ≥ 80% of pre-onset days populated — since
   below that the evaluation is untestable rather than negative.

**And a stop condition on method, not data:** if a future cycle finds itself
re-running fusion search, threshold tuning or feature transforms on the existing
19 inputs, that is the failure mode this package exists to prevent. All three
are excluded.

---

## 7. The decision required from the project owner

**One decision, and it gates the rest:**

> **Is O5 (advance warning) still SERAPH's objective, given that it has now been
> tested at the architecture, mechanism and input layers with calibrated nulls at
> each and failed at all three — while the detection objectives are well
> supported (`semivar_20` +2.138σ, `vix_ratio_60` +4.187σ, O3 operational at
> 29/29)?**

* **If yes** — authorise the two free go/no-go checks in §5 ("can proceed now"),
  and fund candidate 1 or 2 only if its check passes.
* **If no** — re-scope around contemporaneous systemic-risk *monitoring*, record
  advance warning as **tested and not achieved** rather than pending, and the
  acquisition shortlist becomes unnecessary.

**Nothing was re-scoped here. O5 stands in the specification exactly as
written.** The three pillars — P1 Hawkes, P2 RMT, P3 Hamilton — are unchanged in
`PILLAR_ORDER` and no input audited in this package is proposed as a pillar.

---

## Sources consulted for §3

Availability was checked this session; **no price was obtainable from any of
them**, and depth was obtainable from none.

- [NSE paid end-of-day / historical data subscription](https://www.nseindia.com/static/market-data/eod-historical-data-subscription)
- [NSE India VIX index page](https://www.nseindia.com/static/products-services/indices-indiavix-index)
- [NSE historical reports archive](https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives)
- [MSEI FII/DII trading activity (NSE/BSE/MSE combined)](https://www.msei.in/downloads/equity-reports/fii-dii-activities)
- [`nser` F&O bhavcopy vignette (third-party wrapper, documents access mechanics)](https://cran.csail.mit.edu/web/packages/nser/index.html)
- [Mendeley dataset — daily institutional (FII/DII) activity and returns, NSE](https://data.mendeley.com/datasets/ygnt7ddjdw/1)
- [niftytrader historical option chain (third-party, unverified depth)](https://www.niftytrader.in/nse-option-historical-data)
