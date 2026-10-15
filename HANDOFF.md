# SERAPH — PROJECT STATE / HANDOFF

> ## ⚠ CURRENT STATE IS 2026-10-13 — START HERE, THEN READ THE BODY BELOW
>
> The body of this file was written **2026-08-23** and several of its headline
> claims have since been measured to be wrong. Read in this order:
>
> 1. **`docs/evidence/ACCEPTANCE-MATRIX.md`** — the authoritative current state:
>    12 acceptance criteria scored PASS/FAIL/BLOCKED/NOT YET VALIDATED, the short
>    list of what is statistically established, every claim withdrawn, and the
>    open approval gates. **Now 5 PASS, 4 FAIL, 2 PARTIAL, 1 NOT YET VALIDATED.**
> 2. **`docs/evidence/CRISIS-REPLAY.md`** — **the answer to the project's primary
>    question, and it is negative.** A unified causal replay of the whole pipeline
>    finds the complete three-pillar system issued **0 pre-onset warnings across
>    six labelled crises and five lead horizons (5–30 trading days)**. Its
>    warned-rate of 0.00 is *below* the no-skill expectation of 0.14 ± 0.13 from
>    relocating the onsets. **No signal tested — pillar, fusion or simple baseline
>    — is distinguishable from chance** (10 comparisons, lowest p = 0.1108 against
>    a Holm threshold of 0.005). Also: the CSRS is **not a probability** (Brier
>    skill score −11.64, ECE 0.575) and C9's amber threshold is crossed on 57–62%
>    of all days. Four approval gates are stated there with evidence, alternatives
>    and recommendations; none was crossed.
> 3. **`docs/evidence/INDEPENDENT-AUDIT.md`** — **START HERE. The independent
>    audit: diagnosis, a 12-item severity-ranked defect register, a 9-dimension
>    maturity rubric with scores, a benchmark against the systemic-risk
>    literature, the proposed v2 architecture, a phased roadmap, and direct
>    answers to the twelve closing questions.** Headline: SERAPH is a **research
>    prototype with publication-grade evaluation methodology and no demonstrated
>    predictive capability** — engineering ~58/100, predictive evidence ~5/100,
>    operational readiness ~22/100, **deliberately not aggregated** because an 86
>    on causal correctness cannot compensate for a 5 on prediction. Companion:
>    **`EXTERNAL-RESEARCH-CATALOGUE.md`** (12 candidates screened; 2 worth
>    building, both free and both *data* not models).
> 4. **`docs/evidence/THREE-CHECKS-RESULTS.md`** — **the three free checks.**
>    Two NO-GO, one qualified GO. **Pillar 1's conditional intensity `λ_t` has
>    no pre-onset content** (+0.045σ before, DURING class, T3 AUC 0.5496 below
>    its own null p95 of 0.5697) and **cannot reach the pre-2015 epochs at any
>    cadence** — `intraday_bars` starts 2015-02-02. **FBIL money-market
>    benchmarks pass the point-in-time gate** (daily, published 12:45/13:45 IST,
>    before the 15:30 decision) but carry a **methodology break at 2015-07-22**
>    sitting on the epoch boundary. **Option-chain pre-2015 depth is
>    unverifiable publicly.** Two free candidates displace the paid one.
> 5. **`docs/evidence/DECISION-PACKAGE.md`** — **the standing decision package.** Recommends **not** acquiring data yet: the top-ranked
>    candidate (option-implied skew) probably cannot cover the two pre-2015
>    epochs, and if it cannot it is confined to the four epochs where India VIX
>    is already anti-predictive. Carries the ranked acquisition shortlist with
>    **verified / unverified / unknown** markers (no price was obtainable for
>    any source), the two prerequisite engineering proposals, explicit stop
>    conditions, and **the one decision the owner must make** (§7). Companion
>    draft protocol: **`NEXT-PREREGISTRATION-DRAFT.md`** — not in force, not
>    hashed.
> 6. **`docs/evidence/PREDICTIVE-INFORMATION-AUDIT.md`** — **the decisive
>    result, and it is at the input level.** Of 19 available inputs (3 pillars,
>    4 RMT statistics, 5 simple baselines, India VIX + 2 transforms, 4 further
>    market variables), **zero classify as moving BEFORE onset** — 14 DURING,
>    5 AFTER — and **all 19 have a T3 AUC below the 95th percentile of their own
>    no-signal distribution.** Smallest p over two calibrated nulls is 0.0630,
>    so nothing reaches even an *uncorrected* 0.05. **India VIX, the only
>    forward-looking input held, is −0.613σ BEFORE onsets, +1.777 during and
>    +2.544 after** — implied volatility here is a *lagging* measure. Also the
>    auxiliary-data inventory: `flow_aggregates` has **1 row**, `tariff_events`
>    **0**, so FR45 and O8/FR22 are unvalidatable on held data.
> 7. **`docs/evidence/FUSION-ARCHITECTURE.md`** — **the learned-fusion answer.**
>    Five pre-registered architectures, rolling-origin with weights *and*
>    threshold refitted per fold. **No fusion candidate warned before a single
>    development crisis at any false-alarm budget from 0.5 to 4 episodes/year**,
>    under either Pillar 2 quantity. All four pre-registered hypotheses
>    confirmed. **Recommendation: retain equal weights** — and positively so,
>    not as a fallback: learned weights move off the equal-weight point only to
>    fit noise, and under the FR18 input they lose the baseline's only warning.
>    Pre-registration `FUSION-PREREGISTRATION.md` was hashed before the first
>    fit (`3d8e8de3…`).
> 8. `docs/evidence/HAMILTON-REGIME-SUPPORT.md` — two C7 defects found and fixed;
>    the regime-count answer.
> 9. `docs/evidence/DETECTION-CALIBRATION.md` — whether SERAPH's detection claim
>    survives a calibrated null.
> 10. `docs/evidence/EARLY-WARNING-POWER.md` — what the T3 test can and cannot
>    establish.
> 11. `DEMO-DELETE-ME.md` — supersedes **§4** of this file on RMT (5,363 rows and
>    FR16 PASS, not 374 rows and FR16 FAIL).
>
> **Three corrections to this file specifically:**
>
> * **§3 is wrong.** "Specification-faithful TVTP rescued the model" does not
>   hold. The 3-state fit is non-degenerate but **not distinguishable from a
>   process with no regimes at all** (AAFT surrogate null `p = 0.7143`). Pillar 3
>   is **unavailable**. Its occupancy 43.0/25.2/31.8 is reproducible and correct,
>   but it is a smoothed in-sample series and is not evidence of regimes.
> * **§6's immediate next task is done.** The three Pillar 2 findings were
>   resolved; RMT is 5,363 rows at 29/29 acceptance with FR16
>   `max|trace − N| = 2.84e-13`.
> * **§7's data counts are stale.** Now: `rmt_output` **5,363**, `csrs` **4,714**
>   across 2 artefacts, `hawkes_output` **473** (≈ 50/yr — `refit_every = 5`
>   sessions, which puts at most 3 Hawkes observations inside FR32's 15-day
>   lead window and makes Pillar 1 standalone **untestable** for advance
>   warning; see `CRISIS-REPLAY.md` §6a).
>
> The §5 methodology principle and §6's "Do NOT" list remain binding.

---

# SESSION RECORD — 2026-10-14, independent audit

**Canonical worktree: the main checkout, `evidence/pre-arya-experimentation`,
HEAD `f3eaac8`.** The two locked worktrees are owned elsewhere and were not
touched: `c11-fr43-fr49` and `c2-macro-ingestion`, both at `f79299d`. Nothing
committed, merged or pushed. No specification, pre-registration artefact or
crisis label changed. No test weakened. `preregistration.json` still absent.

Deliverables: **`docs/evidence/INDEPENDENT-AUDIT.md`** (diagnosis, defect
register, maturity rubric, benchmark, v2 architecture, roadmap, 12 answers) and
**`docs/evidence/EXTERNAL-RESEARCH-CATALOGUE.md`** (12 screened candidates).
New code: `scripts/screen_financial_sector_stress.py`. Log `*-120`. Results
`docs/evidence/signals/financial_sector_screen.json`.

## The audit's headline

SERAPH is a **research prototype with publication-grade evaluation methodology
and no demonstrated predictive capability.** Engineering ~58/100, predictive
evidence ~5/100, operational readiness ~22/100 — **deliberately not aggregated**,
because these dimensions are not substitutable: an 86 on causal correctness
cannot compensate for a 5 on prediction.

**The bottleneck is not the models, the fusion layer or the code. It is the
information content of daily Indian equity price data at a 5–15 day horizon,
evaluated on six events.** Largest pre-onset separation across 25 screened
features is **+0.432σ** against a measured MDE of ~1.0 sd; the integral timescale
is **770 sessions**, so six onsets give **N_eff ≈ 5**.

## Deliverable F — the first implementation, and it is the most valuable result

**A pre-registered test of the literature's best-documented predictive finding,
on SERAPH's data, from held data, at zero cost — and it failed.**

Giglio, Kelly & Pruitt (NBER w20963 / JFE 2016) find *financial-sector* equity
volatility predicts macro tail quantiles while non-financial volatility does
not. Every one of SERAPH's 25 previously-screened features uses a **market-wide**
aggregate, so the split had never been computed here.

`scripts/screen_financial_sector_stress.py` (hash prefix `95acc3a2…`, fixed
before the first result; 54-name financial list chosen **by company identity
only** and written into the file in advance; coverage floor ≥20 financial and
≥100 other names per day):

| feature | BEFORE −15d | DURING | AFTER | class | T3 AUC | own null p95 |
|---|---|---|---|---|---|---|
| `fin_rv_20` | −0.264 | +1.409 | +2.300 | AFTER | 0.4673 | 0.7031 |
| `nonfin_rv_20` | +0.209 | +1.653 | +1.771 | AFTER | 0.5287 | 0.7030 |
| **`fin_minus_nonfin`** | **−1.027** | +0.102 | +1.191 | AFTER | 0.5109 | 0.6856 |
| `fin_ratio_60` | +0.232 | **+2.077** | +1.612 | DURING | 0.5705 | 0.7150 |
| `fin_dispersion` | +0.152 | +0.781 | +0.230 | DURING | 0.5622 | 0.6122 |

**Zero BEFORE classifications; all five below their own no-signal 95th
percentile; none met the three pre-registered criteria.** The sharpest
Giglio-motivated test runs **backwards**: `fin_minus_nonfin` is **−1.027σ**
before onsets and **+1.191σ** after. Coverage 4,123 days 2010-01-05 → 2026-08-21,
**5 of 6 epochs** (the ≥20-name floor is unmet before 2010, so `gfc_2008` is out
of reach — stated, not worked around).

**Why it matters:** it converts the diagnosis from *"SERAPH's inputs fail"* to
*"the best-documented published leading-indicator family also fails here,
pre-registered"* — a property of the data and target rather than of this
implementation. Nothing in `seraph/` was modified; the production path and all
prior numbers stand.

## Two structural diagnoses from the literature

1. **SERAPH's pillars are all in the family the literature finds weakest.**
   Acharya et al. (1927–2023) find **capital-structure measures predict bank
   failures better than co-movement measures**. All three pillars are
   co-movement/dynamics measures — RMT is correlation structure, Hawkes is event
   co-excitation, Hamilton is regime dynamics — and SERAPH holds **no
   balance-sheet data at all**.
2. **SERAPH's rigour exceeds the field norm.** An arXiv survey of stock-market
   early-warning systems notes many report strong *in-sample* accuracy while
   *"few test how much advance warning they give on held-out data."* SERAPH's
   negative may be what much of that literature would report under the same
   design — which both defends the method and warns against adopting published
   EWS results uncritically.

## New defects found by this audit

- **S1 — unmeasured sector read as *cleared*** (FR14's `base <= 0` falls through
  to `flag="none"`). **FIXED** in the C11 worktree by `measured_flag_source()`,
  30 tests. See that worktree's own HANDOFF entry.
- **S2 — no symbol→sector map exists anywhere** (`universe_snapshots` holds only
  symbol lists; `daily_prices` has no sector column). This blocks FR14's sector
  micro-flags from ever having production inputs and blocks FR22. It is why
  Deliverable F had to pre-register a hand-specified financial list.

Full 12-item severity-ranked register in `INDEPENDENT-AUDIT.md`.

## Recommendation

**Narrow the claims, fix the alert scale, pursue advance warning as one scoped
research track — abandon no pillar.** Re-scope the *production* deliverable to
contemporaneous monitoring (which the evidence supports: `semivar_20` +2.138σ,
`vix_ratio_60` +4.187σ, O3 at 29/29); record advance warning as **tested,
bounded and not achieved**; keep P1/P2/P3 with their earned roles — P1 a
contagion diagnostic per **FR13 `[v4]`, which already says exactly that**, P2
contemporaneous structural monitoring, P3 a regime descriptor with its regime
claim marked unavailable.

**Implement first:** the alert-scale fix (amber currently fires on 57–62% of
days), shipped with the explicit caveat that **D′ proves it is not a route to
advance warning**. Then the two free Phase-0 items — persist `alpha_beta`, and
fix the `validation_results` PK before any writer exists.

**Stop condition, now one of two:** two acquired inputs with a prior mechanistic
reason to lead, both failing `NEXT-PREREGISTRATION-DRAFT.md`. **The
financial-sector test was the first and it failed.** One more — the FBIL term
spread — and the honest conclusion is that daily Indian equity data does not
support 5–15 day advance warning at six events.

---

# SESSION RECORD — 2026-10-14, the three free checks

**O5 confirmed by the owner as the objective. Nothing re-scoped.** HEAD remains
`f3eaac8`; both worktrees intact (9 and 6 uncommitted); database read-only;
`seraph/` unmodified; **no data purchased**; no production code, specification
or pre-registration artefact changed.

Deliverable: `docs/evidence/THREE-CHECKS-RESULTS.md`.
New code: `scripts/screen_hawkes_intensity.py` (research screen; changes nothing
in `seraph/`). Results: `docs/evidence/signals/hawkes_intensity_screen.json`.
Log: `*-110-hawkes-intensity-screen.log`.

## Check 1 — Hawkes conditional intensity `λ_t`: **NO-GO**

| series | BEFORE −15d | DURING | AFTER | class | T3 AUC | p_shift | p_aaft | own null p95 |
|---|---|---|---|---|---|---|---|---|
| `λ_t` reconstructed | **+0.045** | +1.017 | +0.485 | DURING | 0.5496 | 0.1194 | 0.1214 | **0.5697** |
| neg jumps / active sym | +0.045 | +1.024 | +0.471 | DURING | 0.5376 | 0.1774 | 0.1984 | 0.5687 |

Both below their own no-signal 95th percentile; neither p reaches an
*uncorrected* 0.05. **The two series agree to three decimals**, which was
predicted in advance: at φ ≈ 0.50 (one-bar half-life) daily `λ_t` is essentially
a scaled jump count, so the verdict does not depend on the reconstruction.
Stream: 213,751 bars, 94 symbols, **22,114 negative jumps** (consistent with
Workstream D's independent 21,180).

**A finding en route: `hawkes_output.alpha_beta` is NULL on every row.** The
writer stores `branching_ratio_n` and `mts` but not `α`, `φ`, `μ` or the ToD
profile, so **`λ_t` cannot be reconstructed from the database at all.** The
screen therefore rebuilt the excitation term at **SPEC FR11 `[v4]`'s own quoted
values** (α ≈ 0.055, φ ≈ 0.50) — nothing fitted to the evaluation data.
**Persisting `alpha_beta` is a cheap fix worth making regardless. Owner: B (C5).**

**A hard structural bound:** `intraday_bars` starts **2015-02-02**, so the screen
covers **4 of 6 epochs** and **Pillar 1 cannot reach `gfc_2008` or `taper_2013`
at any refit cadence or emission frequency.** No engineering change alters that.

**Consequence.** `DECISION-PACKAGE.md` §4.1's proposal to emit `λ_t` was gated on
this screen, and **the gate has closed: do not propose it as an advance-warning
improvement.** Two narrower reasons survive on their own terms — FR13/NFR4
bar-frequency conformance, and CSRS input resolution (FR13 `[v4]` already calls
Pillar 1 a diagnostic, *not* a forward alarm).

## Check 2 — publication delay: **QUALIFIED GO**, and it is the only GO

**RBI Weekly Statistical Supplement fails** (VERIFIED, rbi.org.in): published
**Friday 5 pm**, weekly, carrying call money rate and T-bill yields. Weekly gives
~3 observations in FR32's 15-day window, and 5 pm is **after** the 15:30 close.

**FBIL passes** (VERIFIED, fbil.org.in): **Overnight MIBOR daily at 12:45 PM**,
**Term MIBOR (14d/1m/3m) daily at 1:45 PM** — both **before** the 15:30 decision,
so **zero-day lag**, and the term series makes a **term spread** constructible
(the theoretically-leading quantity, not a level).

**The caveat is not price.** The benchmark changed from polled to
**transaction-based on 2015-07-22**, a methodology break sitting almost exactly
on the pre/post-2015 epoch boundary. Splicing would mean a feature that changes
definition between the 2013 and 2018 epochs. **Resolve the splice first; if no
clean overlap exists, scope to the four post-2015 epochs and say so.** Also:
**FBIL does not authorise commercial use without written permission** — check the
academic position.

## Check 3 — option-chain coverage: **NO-GO as specified**

Useful reframing: bhavcopy carries strike-level **settlement prices**, so IV is
*derivable* and no IV field is needed — the question is purely archive depth.

**VERIFIED:** the legacy F&O path served through **2024-07-05** and was
**discontinued 2024-07-08** in favour of UDiFF, so any backfill spans two
schemas. **UNKNOWN and decisive:** no official NSE statement on pre-2010
availability; third-party tool ranges all start late (2016, 2020); community
reports of fetch errors before ~2010; **price not published.**

**NO-GO on the gate set in advance.** The candidate is **not refuted — it is
unverifiable publicly**, so the next step is one question to NSE: *does NSE
provide strike-level F&O settlement data for 2008–2010, in what format, at what
cost?*

## A correction to the repository's own documentation

`docs/DATA-ACQUISITION.md:106` states *"**India VIX starts Nov 2007.**
Confirmed."* **Independent search does not corroborate and tends to contradict
it:** public sources place the launch in **2008** (one specifying April 2008),
real-time dissemination from ~2009–2010, and VIX **futures** only from **Feb
2014** — close to the ingested series' 2014-05-15 start, suggesting the data came
from a futures-era source. So there probably *is* uningested VIX history
(~2008–2014), but **it would extend coverage from 4 epochs to 5, not 6**: even an
April-2008 launch cannot populate FR28's five-year ECDF window before the
2008-09-15 onset. **The "Confirmed" should be downgraded to unverified.
Owner: whoever owns OQ5.** Not corrected here — another owner's document.

## Two free findings that displace the paid candidate

1. **NSE participant-wise F&O open interest** (`DATA-ACQUISITION.md:120`, flagged
   "low priority"): free, four categories (FII/DII/PRO/CLIENT), and **a more
   direct measure of crash-protection demand than skew** — skew is a price proxy
   for the positioning this measures directly. Depth, publication time and
   revision policy all unknown and free to check.
2. **FII/DII timing is adequate** — published ~8:30–9:30 PM IST, a one-session
   lag that passes the ≤2-day gate. Its obstacle is **revision**, not delay, so
   candidate 4's low rank was for the right reason.

## Revised ranking of next steps

1. **FBIL money-market term spread** — the only candidate passing the
   point-in-time gate on verified evidence. Free. Splice question first.
2. **NSE participant-wise F&O open interest** — free, more direct than skew.
3. **India VIX backfill to its true start** — free; closes a coverage gap and
   corrects a documentation error. Extends to 5 epochs, not 6.
4. **Option-chain skew** — now *below* the free candidates, because its decisive
   fact is unverifiable and its cost unknown. Revisit after NSE answers.
5. **Cross-market replication** — unchanged; largest effort, only route to
   independent realisations.

**Every input in or derivable from the repository has now been screened** — 19 in
the audit plus `λ_t` and the raw jump count — and all are DURING or AFTER, all
below their own no-signal distribution. **SERAPH has not demonstrated
advance-warning capability and nothing here claims it has.**

## Next decision required

**Authorise the two free checks on candidates 1 and 2** (FBIL splice resolution;
participant-wise OI depth/timing/revision), and **send NSE the single
pre-2015 F&O question.** No purchase is warranted until those return.
`DECISION-PACKAGE.md` §6's stop conditions remain in force — in particular, if
candidates 1 and 2 both fail `NEXT-PREREGISTRATION-DRAFT.md`, the
advance-warning programme should stop.

---

# SESSION RECORD — 2026-10-14 (latest), decision package

**Documentation-only phase. No production code, specification, test or
pre-registration artefact changed. Nothing committed or pushed.** HEAD remains
`f3eaac8`; both locked worktrees intact (9 and 6 uncommitted); database
read-only; `seraph/` still the three files modified before this work began.

Deliverables: `docs/evidence/DECISION-PACKAGE.md` and
`docs/evidence/NEXT-PREREGISTRATION-DRAFT.md`.

## Recommendation

**Do not acquire new data yet.** Spend one short cycle on the two prerequisites
and the scope question, then commit. The reason is specific: the top-ranked
candidate (option-implied skew and term structure) **probably cannot cover the
two pre-2015 epochs**, and nothing in the public record I could verify
establishes that strike-level option IV exists for India back to 2008. If it
does not, the feature is confined to the four epochs where **India VIX is
already measurably anti-predictive** (−0.613σ before onsets, T3 AUC 0.4057,
p = 0.8536) and cannot add an independent episode.

## Workstream A1 — the Hawkes cadence question is the wrong question

Measured read-only on the existing 473-refit series:

| quantity | value |
|---|---|
| autocorrelation between **adjacent** refits (5 sessions apart) | **ρ = +0.9843** |
| data shared by adjacent 500-day windows | **99.0%** (99.8% at `refit_every=1`) |
| share of total variation appearing between adjacent refits | **9.0%** |
| decorrelation lag | ~250 sessions (ρ = 0.0755 at lag 50) |
| non-overlapping 500-day windows in the span | **≈ 4.7** |

**A 1-session refit would multiply rows five-fold and add almost no
information** — independence is governed by the 500-day window, not the refit
interval, so the span holds ~5 independent Hawkes observations and a 15-day
window holds none at any cadence. It would convert Pillar 1 from `UNTESTABLE` to
a **measurable zero**: reportability value, no predictive value. Cost from the
repo's own measurement: **818 min** for daily refits vs 164 min at `refit_every=5`.

**The real conformance gap is the emission quantity, not the cadence.** FR13
`[v4]` and NFR4 specify Hawkes emission **at bar frequency**, but
`MTS_t = n/(1−n)` is a function of the fitted parameters only
(`engine.py:320`), so "emit MTS at bar frequency" either repeats a
piecewise-constant value (adds nothing) or requires per-bar refitting
(infeasible). The substantive option is to emit the **conditional intensity
`λ_t`**, which varies per bar at fixed parameters and **is already implemented**
as `excitation_path()` (`engine.py:214`) but never persisted — with precedent,
since FR14's sector flags already use realised intensity over baseline.
**`λ_t` is a different quantity from `MTS_t`, so this is a specification change,
not a free fix.**

**And the specification has already conceded the forward-alarm point.** FR13
`[v4]` states Pillar 1 is "a contagion / risk-state diagnostic contributing to
the CSRS, **not** an independently demonstrated forward alarm", citing a
pre-registered test that found approximately no skill at 15m/30m/1h/2h. My
daily-horizon result (Hawkes T3 AUC 0.3805, p = 0.9470) extends that to 15 days.
The cadence work should be framed as CSRS input resolution, not as rescuing a
forward alarm.

## Workstream A2 — alert thresholds

Three options with the validation each needs, in `DECISION-PACKAGE.md` §4.2.
**Recommended: causal quantile thresholds now** (already prototyped as Rule B —
4–12% of days under alert instead of 57–62%), **plus** documenting the CSRS as
an uncalibrated ordinal monitor. A separately calibrated probability is
**premature**: there is currently nothing to calibrate against. `score()` already
takes the thresholds as parameters so no contract change is needed, but
**`alert_level` semantics are frozen and C9 is owner D's — no change was made.**

## Workstream B — acquisition shortlist

Ranked, with **verified / unverified / unknown** markers throughout.
**No price was obtainable for any source, and historical depth for none** — which
is itself why the recommendation is to check the two free go/no-go facts first.

1. **Option-implied skew and term structure.** NSE's paid EOD F&O product is
   VERIFIED to exist (`marketdata@nse.co.in`, +91-22-2659 8385); **price not
   published**; **pre-2015 strike-level IV depth UNKNOWN and decisive.**
2. **Funding/liquidity spreads.** SERAPH holds none (`rbi_repo_rate` is 0
   non-null). RBI's DBIE is the expected home but UNVERIFIED — my search did not
   resolve the portal or its series codes. **The decisive risk is publication
   delay, not price:** a weekly series lagged two weeks cannot populate a 5–15
   day lead window.
3. **Cross-market replication.** The only route adding *independent*
   realisations — but Workstream B measured **10 of 15** candidate onsets as
   global, so only ~5 are domestic.
4. **FII/DII flows — do not currently exist.** `flow_aggregates` holds **1 row**.
   NSE/MSEI publish daily figures but **flagged provisional and subject to
   revision**, which is a look-ahead trap: replay needs the *as-first-published*
   vintage. Ranked last for that reason, not for lack of a hypothesis.

## Workstream C — draft protocol

`NEXT-PREREGISTRATION-DRAFT.md`. **Not in force, not hashed**; it binds only
once a candidate exists, coverage passes and the owner signs. Two additions
driven by measured failures: the false-alarm budget now bounds **both** episode
rate (≤ 2/yr) **and** time-under-alert (≤ 15% of days), because `drawdown`
respected the old budget while alerting on 38.2% of days; and admission requires
the candidate's T3 AUC to **exceed its own no-signal 95th percentile** — a clause
**no** current input satisfies, all 19 falling below it.

## Six stop conditions, stated before any acquisition

In `DECISION-PACKAGE.md` §6. The two that matter most: **stop candidate 1** if
option IV does not reach pre-2015; and **stop the advance-warning programme
entirely** if two acquired inputs, each with a prior mechanistic reason to lead,
both fail the protocol.

## THE DECISION REQUIRED FROM THE OWNER

> **Is O5 (advance warning) still SERAPH's objective**, given it has now been
> tested at the architecture, mechanism and input layers with calibrated nulls at
> each and failed at all three — while the detection objectives are well
> supported (`semivar_20` +2.138σ, `vix_ratio_60` +4.187σ, O3 operational at
> 29/29)?

* **Yes** → authorise the three free checks (λ_t screen; RBI publication-delay
  audit; option-chain depth confirmation) and fund a candidate only if its check
  passes.
* **No** → re-scope around contemporaneous monitoring and record advance warning
  as **tested and not achieved** rather than pending; the shortlist becomes
  unnecessary.

**Nothing was re-scoped. O5 stands in the specification as written, and P1
Hawkes / P2 RMT / P3 Hamilton are unchanged in `PILLAR_ORDER`.**

---

# SESSION RECORD — 2026-10-14 (later), predictive-information audit

**Nothing committed or pushed; HEAD remains `f3eaac8`.** Both locked worktrees
intact (9 and 6 uncommitted). Database **read-only**; `seraph/` **unmodified**.
`preregistration.json` still deliberately absent.

## Phase 1 — verification, and the suite now has a COMPLETED result

**220 passed, 1 failed, 2 xfailed (223 total, ~14m04s).** Two earlier
single-process attempts were stopped by the harness on low system memory
(2.37 GB free of 15.8 GB; `vmmemWSL` held 3.0 GB). A partial run is not a
result, so the suite was run in **three exhaustive, non-overlapping foreground
chunks** — 148+26+46 = 220 passed — and reconciled against the 223-test
collection count **exactly**. Auditable arithmetic in
`*-100-suite-COMPLETE-chunked.log`; chunk logs `*-100a/b/c`. The killed partial
run is preserved with a banner.

Both pre-registration hashes verify unchanged and are correctly cited
(`3d8e8de3…`, `26910c6a…`).

## Phase 2–3 — the decisive result is at the INPUT level

Deliverable: `docs/evidence/PREDICTIVE-INFORMATION-AUDIT.md`.
Code: `scripts/audit_predictive_information.py`,
`scripts/rank_predictive_candidates.py`.
Results: `docs/evidence/signals/{predictive_information_audit,candidate_ranking}.json`.
Logs `*-101`, `*-102`.

- **Zero of 19 inputs move before onset.** Classified by which of three disjoint
  windows holds the largest positive separation, against a **local** ±1-year
  baseline (a global baseline manufactures a spurious negative for `λ₁/N` from
  era composition): **14 DURING, 5 AFTER, 0 BEFORE.**
- **The contrast is the finding.** DURING separations reach **+4.187σ**
  (`vix_ratio_60`) and **+2.138σ** (`semivar_20`); the largest BEFORE value
  anywhere is **+0.432σ**, an order of magnitude smaller. These features detect
  crises spectacularly and anticipate them not at all.
- **All 19 sit below their own no-signal 95th percentile** on T3 AUC under two
  calibrated nulls (relocation, measured type-I 8% at nominal 5%; and AAFT).
  Smallest p = **0.0630** — nothing reaches even an *uncorrected* 0.05, against a
  Holm tightest of 0.00263 over 19. Survivors: **none**.
- **A high AUC is not enough, and the table shows why.** `drawdown` has the
  highest raw T3 AUC at 0.6322 — and its own null's 95th percentile is **0.6569**,
  because a strongly persistent feature produces a wide null. Same for `Ω_t`
  (0.5934 vs 0.6171) and `hamilton LSD` (0.5978 vs 0.6463).
- **India VIX refutes the forward-looking hypothesis directly.** The mandate
  asked for forward-looking inputs while warning against assuming
  forward-looking-by-construction implies predictive. VIX is the test case and
  fails informatively: **BEFORE −0.613σ with 0 of 4 epochs positive**, DURING
  +1.777, **AFTER +2.544**, T3 AUC **0.4057 (p = 0.8536)**. It is lowest before
  onsets and highest *after* them.
- **Auxiliary-data inventory — most of the specified inputs do not exist.**
  `flow_aggregates` holds **1 row** (2026-10-12, a live snapshot), so **FR45 is
  unvalidatable and flow is an acquisition, not held data**; `tariff_events`
  **0 rows**, so O8/FR22's `G_t` has no event table; `microstructure_state`,
  `regulatory_action_log`, `validation_results` all **0**; and
  `daily_prices.log_return_std`/`yz_volatility` are **0 non-null**.
- **A SPEC discrepancy recorded:** OQ5 states India VIX starts Nov 2007 and
  discusses substituting it for 2008; the **ingested** series starts
  **2014-05-15**, so OQ5 reasons from a longer history than the repository has.

## Phase 4 — not entered, and why

Phase 4's own precondition is *"only after a candidate input demonstrates
credible, causal pre-onset information."* **No available input does**, so no
further fusion experiment was run. Equal-weight fusion remains the reference
baseline; the three pillars are unchanged.

**The two negatives compose.** The fusion phase showed no architecture over
these inputs warns; this phase shows the inputs contain nothing to warn with.
Together they close the space: within the data this repository holds, advance
warning is not achievable, and the limit is the information content of the
inputs, not the method applied to them.

## Claims withdrawn this phase

`ACCEPTANCE-MATRIX.md` §5's two top priorities are now **withdrawn with
markers, not deleted**:

1. ~~"More onsets — the binding constraint, nothing else comes close"~~ —
   refuted by N_eff ≈ 5 and by there being nothing for more events to measure.
2. ~~"FR30 under leave-one-epoch-out; equal weights demonstrably dilute the best
   input"~~ — that was a **T1** statement; on T3 learned weights have bootstrap
   intervals of mean width 0.983 and *lose* the baseline's only warning.

## New approval gate raised

**The objective-scope decision.** O5 (advance warning) has now been tested at
three layers — architecture, mechanism, inputs — with calibrated nulls at each,
and is negative at all three. The **detection** objectives are well supported
(`semivar_20` +2.138σ, `vix_ratio_60` +4.187σ, O3 operational at 29/29). Whether
SERAPH is re-scoped around contemporaneous *monitoring*, with advance warning
recorded as tested-and-not-achieved, or new acquisition is funded to pursue O5,
is the owner's call. **Nothing was re-scoped; O5 stands in the specification as
written.**

## Next executable task

**No further held-data experiment is justified.** The recommendation is an
acquisition decision, ranked in `PREDICTIVE-INFORMATION-AUDIT.md` §7:
option-implied **skew and term structure** (not the VIX level, which is
measurably lagging); **funding/liquidity spreads**, subject to a
publication-delay audit; **cross-market replication** (the only route to
independent realisations); and **FII/DII flow**, which must be built from
scratch. Two cheap prerequisites first: shorten Hawkes's refit cadence so
Pillar 1 stops being untestable, and fix the alert scale so a new input can be
judged against an interpretable alarm.

---

# SESSION RECORD — 2026-10-14, learned fusion architecture

**Nothing committed or pushed; HEAD remains `f3eaac8`.** Both locked worktrees
intact (9 and 6 uncommitted). Database **read-only**; `seraph/` **unmodified** by
this phase. `validation_results` still 0 rows; `preregistration.json` still
deliberately absent pending the FR35 Table B and event-count decisions.

## The question and the answer

**Can fusion weights learned from historical data produce causal out-of-sample
advance warning? No — and equal weighting is the right production choice, for a
positive reason rather than as a fallback.**

Pre-registration `docs/evidence/FUSION-PREREGISTRATION.md`
(sha256 `3d8e8de372e328444d9711fcb531c41deb8e91bac17100c0d19ff295abb4848d`)
fixed the hypotheses, the 2 FA/yr budget, the candidate set, the
development/confirmation split and the tie-breaking rules **before the first
fit**. All four hypotheses were confirmed.

Deliverable: `docs/evidence/FUSION-ARCHITECTURE.md`.
Code: `scripts/fusion_architecture_search.py`,
`tests/test_fusion_learning_leakage.py` (13 tests, all pass).

- **Full suite: COMPLETED 2026-10-14 — 220 passed, 1 failed, 2 xfailed (223 total, ~14m04s).** Two earlier single-process attempts were stopped by the harness on low system memory (2.37 GB free of 15.8 GB; `vmmemWSL` alone held 3.0 GB); a partial run is not a result, so the suite was run in **three exhaustive non-overlapping foreground chunks** and the totals reconciled against the 223-test collection count exactly (148+26+46 = 220 passed). Combined record with the auditable arithmetic: `*-100-suite-COMPLETE-chunked.log`; chunk logs `*-100a/b/c`. The killed partial run is preserved as `*-90-full-suite-after-fusion-INCOMPLETE-KILLED-LOW-MEMORY.log`. **The single failure is the deliberately-preserved CT-3**; both xfails are `strict=True` pins on open specification questions (D-1b, D-2).
Results: `docs/evidence/fusion/fusion_search_{lam1,sca}_b2.json`. Logs `*-81`…`*-90`.

## What was measured

- **Harness is faithful**, asserted not assumed: candidate A reproduces the
  shipped `CSRS[hawkes+rmt+hamilton]` to **`max|Δ| = 2.220e-16`** over 5,363
  days. Every candidate operates on the **reconciled state**, which is where C9
  actually sits.
- **H1 confirmed.** Best learned candidate 0 warnings; best single input 1;
  baseline A 0. No learned architecture beats its own inputs.
- **H2 confirmed, and worse than instability.** Max pairwise L1 distance between
  per-fold weight vectors is **1.700** (λ₁/N) and **1.900** (`SCA_t`), against a
  simplex maximum of 2.0 and a pre-registered threshold of 0.33. **Each fold
  crowns a different pillar** and the weights land on simplex *corners*. Best
  in-sample AUC **falls** as events are added — 0.6585 (1 event) → 0.5032 (2) →
  0.4905 (3) — the signature of fitting noise.
- **Weight uncertainty quantified, and it is the strongest single result.** A
  moving-block bootstrap (blocks, not days — the measured integral timescale is
  770 sessions) on the widest development window gives 90% intervals of
  hawkes **[0.000, 1.000]**, rmt **[0.000, 1.000]**, hamilton
  **[0.000, 0.950]** — **mean width 0.983 on a [0,1] scale**, near-maximal at
  *every* block length from 21 to 770, so this is not an artefact of the
  cautious dependence assumption. 21% of replicates put >0.95 of the weight on a
  single pillar, i.e. discard fusion entirely. The point estimate on that window
  scores **0.3771 in sample — below chance**. A learned weight here is **not an
  estimate of anything**, and reporting one to two decimals would be false
  precision.
- **H3 confirmed, with a reusable diagnostic.** Escalation warned 0/3 on
  development *while breaching its budget* (3.13 against 2.0 FA/yr), and
  overshoots at every level (0.56/1.86/3.13/6.11 against 0.5/1/2/4). Its fitted
  thresholds land at **0.999999 for the composite arm and exactly 1.0 for
  several pillar arms** — holding a rank-scale score to 2 FA/yr needs a
  threshold above the 99.9th percentile and **a rank has nothing above 1.0**, so
  the escalation degenerates rather than being tested. **Same root cause as
  `CRISIS-REPLAY.md` gate 1**.
- **D′ rules out that mechanical explanation — the most important result of the
  phase.** Separately pre-registered
  (`FUSION-PREREGISTRATION-ADDENDUM-D2.md`, sha256 `26910c6a…`, hashed after D's
  diagnosis and before D′ ran), D′ moves the escalation arm onto **raw**,
  unbounded pillar magnitudes and enforces the budget on the combined rule. The
  thresholds then resolve properly — fitted quantiles **0.9490–0.9795**, not
  saturated at 1.0 — **and D′ still warned 0 of 5**, across every testable
  development epoch and both confirmation epochs. So the scale fix worked
  mechanically and changed nothing: **the rank scale was not what stood between
  SERAPH and advance warning.** An earlier statement of mine that a fair test of
  escalation “requires the scale fix first” is withdrawn. Two of five D′ folds
  are not even budget-feasible at their loosest admissible setting.
- **H4 confirmed.** On the untouched confirmation epochs no candidate beat its
  own no-skill rate. Two 1-of-2 cells exist (D at a 14-day lead on
  `tightening_2022`, `dd_accel_5` at 12 days) but D scored **0/3 on
  development**, and at its own 2.05 FA/yr the chance of ≥1 hit in 2 events is
  **0.2164**. With two epochs even 2-of-2 reaches only p ≈ 0.013.
- **Robust to the budget.** 0/4 or 0/3 for every fusion candidate at 0.5, 1, 2
  and 4 FA/yr.
- **Candidate C's own regulariser agrees there is no signal.** All three
  loadings negative on λ₁/N (hawkes −1.025, rmt −0.231, hamilton −2.443); on
  `SCA_t` inner CV picks the strongest regularisation (`C = 0.01`) and drives
  the coefficients to ≈0 — "predict the base rate". Only **1 development fold
  has ≥10 training positives**, so three coefficients cannot be estimated.
- **The FR18 input changes the baseline, not the conclusion.** With `SCA_t`,
  equal weights improve **0/4 → 1/4** (lead 15, p = 0.2498, still not
  significant) while learned convex weights stay **0/3** and go to pure simplex
  corners. **When there is nothing to learn, learning destroys the variance
  reduction equal weighting provides.** Concrete prediction this supports:
  **FR30's joint weight optimisation, run on six events, should be expected to
  make things worse.**

## Reconciliation and corrections

- **A reproducibility defect in the previous session's own deliverable:** 4 of 7
  JSON paths cited in `CRISIS-REPLAY.md` did not exist — the semivar re-run had
  regenerated only 2 of 6 artefacts, leaving the rest as `.PRE-SEMIVAR.json`.
  All six are now regenerated (exits 0) with the pre-semivar copies preserved.
- **`macro_covariates` is not entirely empty.** A Workstream B claim carried
  into the matrix said all covariates were 0 non-null. `india_vix` has **3,034
  non-null rows, 2014-05-15 .. 2026-08-21, 100% dense**, covering 4 of 6 epochs.
  Six covariates *are* empty, so O8/FR22 remains unvalidatable. VIX is now
  evaluated as a baseline: **0 of 2 testable epochs warned.**
- **Two bugs of mine during this experiment, both caught before publication.**
  (i) Learned candidates first reported `untestable` on every fold because their
  threshold was fitted on a stitched series that is all-NaN over the training
  region; corrected to true rolling origin. (ii) The H4 verdict logic tested
  `warnings > 0` and printed "H4 REJECTED", where H4 says *significantly* above
  no-skill; replaced with a binomial test, which flips the verdict to
  **CONFIRMED**. Both broken runs (`*-82`, `*-85`) are preserved.
- **A blind spot in my own pre-registered budget, reported not retro-fixed.**
  `drawdown` respects a 2 FA/yr *episode* budget while alerting on **38.2% of
  days**, because a standing alert is one episode however long it lasts. The
  budget should bound time-under-alert as well; changing it after seeing which
  candidate it admits would be the integrity failure §9 of the pre-registration
  names, so `% days alerting` is printed for every candidate instead.

## Next executable task

1. **Find inputs with pre-onset content.** After D′ this is unambiguously the
   binding constraint — every architecture fails for the same reason and the
   last mechanical explanation is ruled out. The three pillars measure
   *contemporaneous* contagion, coupling and regime state; nothing in the
   evidence suggests any of them leads an onset. A credible new input would have
   to be forward-looking by construction (option-implied, flow-based, or
   cross-market) rather than another transform of realised prices.
2. **Shorten Hawkes's refit cadence for evaluation** (gate 2). Pillar 1 is
   currently *untestable* for the primary objective, which is worse than a
   negative result and is fixable at the cost of compute alone. Second because
   it converts an UNTESTABLE into a result, not because it is likely positive.
3. **Fix the alert scale** (gate 1) — still worth doing, but **for
   interpretability, not for warning**. 57–62%-of-days amber makes every
   operational statistic unreadable. D′ is the evidence that it is not a route
   to advance warning, so it must not be proposed as one.
4. **FR18 conformance** (gate 4) — conformance and contemporaneous detection,
   explicitly not warning.
   **Not** more events: nine more defensible episodes buy roughly one
   effectively independent event (N_eff ≈ 5 at the measured 770-session scale).

---

# SESSION RECORD — 2026-10-13, autonomous validation program

Four parallel workstreams. **Nothing committed or pushed; HEAD remains
`f3eaac8`.** Both locked worktrees intact (`c11-fr43-fr49` 9 uncommitted,
`c2-macro-ingestion` 6 uncommitted). Database **read-only throughout** — row
counts identical to session start (`csrs` 4,714, `rmt_output` 5,363,
`hawkes_output` 473, `hamilton_output` 5,365, `daily_prices` 8,023,206,
`intraday_bars` 18,781,302). `seraph/` changed **only** in the three files
already modified before this session (C7 engine + orchestration); no workstream
added a production change.

**Full suite: 207 passed, 1 failed, 2 xfailed in 1,097.52s** (was 170/1 — **37 new tests this session**). The single failure
is CT-3, deliberately left failing — see below.

## The headline

**SERAPH has no demonstrated advance-warning capability, and the evidence is
strong enough to say so rather than merely note it unproven.** The complete
three-pillar system issued **zero pre-onset warnings across six labelled crises
and five lead horizons (5–30 trading days)** under a causal adaptive threshold.
No RMT-containing subset warned anywhere. **No signal tested — pillar, fusion or
simple baseline — is distinguishable from chance.**

**What six events cannot support:** 0/6 gives a 95% upper bound on the per-event
warning probability of **0.393** against a no-skill rate of 0.14, so this is a
demonstrated *absence of evidence*, not evidence of sub-chance behaviour. That
distinction is held throughout and an earlier overstatement of mine was
corrected.

## Workstream A — unified causal crisis replay (PRIMARY)

**`docs/evidence/CRISIS-REPLAY.md`.** Scripts: `replay_crisis_warnings.py`,
`replay_warning_null.py`, `replay_operational_value.py`,
`replay_threshold_sensitivity.py`, `analyse_pillar_redundancy.py`,
`diagnose_pillar_signal_loss.py`. Tests: `tests/test_replay_causality.py`
(12 passed). Logs `*-61` … `*-69`; JSON in `docs/evidence/replay/`.

- 7 FR35 pillar subsets + 4 simple baselines × 6 epochs × 5 horizons, one causal
  pass. Nothing fitted: both alert rules are pre-specified, so there is no
  holdout to contaminate.
- **Robust to the threshold.** Swept 5 quantile levels with the null recomputed
  at each: full system 0/6 at four of five levels, 1/6 (p = 0.7271) at the
  fifth. Across 50 testable cells, **1 reaches p ≤ 0.05 where chance predicts
  2.5**.
- **The CSRS is not a probability.** Brier skill score **−11.64**, ECE **0.575**
  against a 3.36% base rate. A scale error by construction (FR28 makes each
  sub-score a rank ≈ U[0,1]); **FR30 cannot fix it** — it optimises weights, not
  scale. C9's amber threshold is crossed on **57–62% of all days**.
- **Why fusion failed: non-redundant but near-empty.** 2.75 effective
  independent pillars of 3 (|Spearman| ≤ 0.21) — MG-1's diversity premise is
  *supported*. But RMT alone explains **R² = 0.00001** of the crisis label over
  5,363 days; the best three-pillar figure is 4.0% in-sample on 468 days.
- **Direct mechanism:** all three pillars are flat or negative pre-onset
  (hawkes +0.06σ, rmt −0.29σ, hamilton −0.18σ standardised).
- **The comparison set was not weak.** `semivar_20` — the repository's strongest
  known single feature, which Workstream C found wins leave-one-epoch-out
  selection on 4 of 6 folds — warns before **0 of 6** onsets at every horizon,
  p = 1.0000. The best feature anyone in this project has found has no
  advance-warning capability either.
- **One confirmed defect (gate 4):** SPEC FR18 specifies Pillar 2's sub-score as
  `SCA_t`; `rmt_emission` standardises `λ₁/N`, named nowhere in FR16–FR19, while
  `rmt_output.sca_t` is computed, validated at 29/29 and never read.
  Era-controlled crisis separation **+0.5028σ (5/6 epochs) vs −0.3784σ (1/6)** —
  a sign reversal. Replaying on `SCA_t` moves the full system 0/6 → 2/6 **and
  p = 0.4993**, because it also triples the alert rate. Worth ~1σ for detection,
  **nothing for advance warning**. In T1 AUC the gap is **0.6623 vs 0.4282** —
  the quantity in use is *anti-predictive*, which is also why λ₁/N's R² against
  the crisis label is 0.00001. Not fixed: changes every CSRS value ever computed;
  C6 is another owner's. A cheaper sub-question rides with it — FR18 specifies
  “calibrated weights”, C6 uses equal thirds, and the aggregate scores **below its
  own `Ω_t` component (0.7354)**. `Ω_t` was then tested rather than left
  hanging: **its T3 AUC 0.5934 falls below its own no-signal 95th percentile of
  0.6158** (p = 0.088/0.104, two nulls, Bonferroni 0.01 over 5 candidates), so
  the most promising number anywhere in the Pillar 2 evidence is refuted and
  **no Pillar 2 statistic has demonstrable advance-warning content**.
- **Two coverage facts that contradict SPEC §4:** causal Hamilton begins
  **2013-01-14** (2,000-day initial train), so 2008 and 2013 are `UNTESTABLE`
  without look-ahead; and Hawkes's `refit_every = 5` leaves ≤3 observations in
  FR32's 15-day lead window, giving **0 assessable days of 468** — Pillar 1
  standalone is untestable for the system's primary objective.

## Workstream B — event count and statistical power

**`docs/evidence/EVENT-COUNT-LIMITATION.md`**, `scripts/audit_event_coverage.py`,
logs `*-32` … `*-35`.

- H_B **accepted**: the six-event limit is spec-imposed, not data-imposed — 9
  admissible non-FR32 episodes at 100% RMT+Hamilton coverage. **And largely
  moot.**
- **Integral timescale of `rv_t_yz` = 770 sessions.** The 5,363-session grid
  holds **≈7 effectively independent realisations**; 6 nominal onsets → N_eff 5,
  15 nominal → N_eff 6. Nine added events buy roughly **one** effectively
  independent event.
- The 0-of-N upper bound first falls below the no-skill rate at **N = 20**; the
  exogenous record supports at most **N = 15**. **The decisive threshold is
  unreachable.** Minimum detectable warned-rate 0.50 at N=6 → 0.33 at N=15,
  against an observed 0.00. **Binding constraint is effect size, not sample
  size.**
- The 2005 boundary is the **EOD2 adjustment caveat**, not FR52 (which binds at
  ~1999) and not macro. 637,900 pre-2005 rows are held, 0 universe-flagged.
- **`macro_covariates` is entirely empty** — `g_t`, `rbi_repo_rate`,
  `bank_credit_growth_yoy`, `inr_twi`, `brent_price` all 0 non-null; production
  Hamilton substitutes lagged standardised RV. **O8/FR22's tariff covariate is
  therefore unvalidatable as things stand.**
- **`preregistration.json` does not exist**, and would hash over **20**
  configurations. An event-count or config-count change is free today and
  invalidates every `EvaluationRow` the moment that file lands.
- Recommendation: **no change to FR32** (option A0). Block bootstrap and
  event-clustered variance are assessed and explicitly **do not** raise power.
- **The 0.5-exclusion ledger, and it corrects a reading of mine.** At the
  measured 770-session block length, **all 7 pillar/CSRS subsets lose
  0.5-exclusion by L = 21** — the shortest non-trivial block tested — and 0/7
  exclude at L = 770. But **3 of 4 simple baselines exclude 0.5 at *every* block
  length** (`rv_20` 0.7347, `dd_accel_5` 0.7015, `rv_accel_5` 0.6622); only
  `drawdown` loses it. So the defensible claim is **not** "T1 has no resolving
  power" but **"T1 has no resolving power for anything SERAPH builds, while
  three one-line volatility and drawdown features retain it at every dependence
  assumption tested."** That is worse for the architecture than a uniform loss.
  Precision was overstated **3.9–5.7×** for every subset containing RMT or
  Hamilton (my earlier ~2.5× was conservative). Under `SCA_t` the point
  estimates improve materially (`CSRS[rmt]` 0.5292 → 0.6289, full system
  0.5733 → 0.6632) and reach 7/7 exclusion at L = 1 — **still 0/7 at L = 770**.
  **T3: 0/7 pillars and 0/4 baselines at L = 770, under both Pillar 2
  quantities.**
- Deconfliction with C, stated structurally rather than as a contradiction: for
  an AUC the **block** bootstrap is the right correction; for per-epoch warned
  rates and lead times the **onset cluster** is the only option, and for a 0-of-N
  count even that degenerates to [0, 0] — which is why the exact binomial bound
  is used there instead.

## Workstream C — acceleration signals

**`docs/evidence/ACCELERATION-SIGNALS.md`**,
`scripts/validate_acceleration_signals.py`,
`tests/test_acceleration_signal_causality.py` (21 tests), logs `*-40`, `*-41`.

- **H_C1 leakage ACCEPTED**: max relative |Δ| = **0.000e+00** under truncation
  invariance and future perturbation across 17 cuts, against an audit that
  catches **5/5** deliberately planted leaks (centred window, forward
  difference, full-sample normalisation, reversed cumulative, future-peak
  drawdown). Mutation-tested.
- **H_C2 out-of-sample ACCEPTED but shrinking**: `dd_accel` 0.7467 → **0.6666**
  (p 0.0153/0.0060), `rv_accel` 0.7912 → **0.7534**. The informative control:
  `drawdown` collapses 0.8681 → **0.5940** (p 0.21) and the 3-pillar CSRS
  0.7004 → 0.5872 (p 0.27).
- **H_C3 uniqueness REFUTED**: `rv_diff1` — realised vol minus *yesterday's* —
  has a **lower p (0.0010) than `rv_accel` (0.0017)** under an 18-wide Holm. So
  `DETECTION-CALIBRATION.md` §2's "both survivors are second-difference
  quantities" does not hold once trivial alternatives enter the family.
- **T3 advance warning NULL at 5/10/20/30 days**; smallest p 0.2557 against a
  Holm threshold of 0.00625.
- **SPLIT-C is materially negative**: leave-one-epoch-out would have selected
  `dd_accel` on **0 of 6** folds and `rv_accel` on **2 of 6** (usual winner
  `semivar_20`).
- `dd_accel`'s full-span p = 0.0003 is **censored at the 1/3001 permutation
  floor, not measured**.

## Workstream D — implementation and specification blockers

**`docs/evidence/BLOCKER-TRIAGE.md`**, logs `*-51` … `*-55`, new tests
`test_c4_lee_mykland_calibration.py`, `test_fr35_ablation_design_pins.py`,
`test_c5_hawkes_writer.py`.

- **D-1 CT-3 — classification (5), external/unavailable data.** Corpus-wide
  negative-jump density **0.0865 per symbol-day against a floor of 1.0** (95
  symbols, 18,269,762 bars, 244,772 symbol-days); best single symbol 0.3512,
  still 2.8× short. **Deliberately left failing** — the assertion was not
  weakened, the floor not lowered, no `xfail`. Crucially: **SPEC FR10 `[v4]` was
  amended to supersede** per-symbol one-day estimation, quoting this test's own
  0.087 figure, while ARCHITECTURE §5 ① still states the floor. Retiring the
  gate is the C4/C5 owner's call.
- **D-1b — a real numerical defect, pinned not patched.** `extract_jumps` feeds
  a `μ₁`-corrected statistic to an uncorrected-σ̂ critical value, so the
  rejection threshold is **1/c = 1.2533× too strict** and realised size is ≈0
  against nominal α = 0.01. Correcting it moves density 0.0865 → 0.1478 — still
  6.8× below the floor, so D-1's conclusion is robust to it. Pinned `xfail`;
  fixing the code without amending SPEC FR10 would put code and spec in
  contradiction.
- **D-2 FR35 — classification (4), approval required, and sharper than
  previously stated.** SPEC FR35 `[v2]` puts Table B *"on the 2 pre-2015
  epochs"* (2 folds); ARCHITECTURE D5(b) says Table B uses all 6 → 6 folds.
  `configuration_list()` implements D5(b); `preregistration.PRE_HAWKES_EPOCHS`
  encodes SPEC's reading **and is never used**. The fold count is inside the
  D5(d) hash, so a mismatch is unreportable. Pinned `xfail`.
- **D-1b is far worse than a 25% effect.** Because the Gumbel tail is thin, the
  1/c mis-scaling costs **~3 orders of magnitude in level**: effective
  α ≈ **1.0e−05** at production `n`, **975× tighter** than the documented 0.01.
  On a pure-Brownian null the shipped threshold rejects in **0 of 400** samples;
  power at 5σ is 0.250 against 0.620 corrected.
- **D-2 — and a prior evidence document is now superseded.**
  `FR35-CONFIG-COUNT-CONFLICT.md` treated 20 configurations as a defect against
  14 and recommended restricting Table A to 8. **SPEC FR35 `[v2]` line 243 reads
  “Table A (7 subsets × 2 modes) … Table B (3 subsets × 2 modes)” = 14 + 6 = 20**,
  so the existing enumeration is **SPEC-correct and that fix must not be
  applied**; a superseding banner now says so at the top of that file. The one
  genuine ambiguity is Table B's **fold count** (SPEC: the 2 pre-2015 epochs;
  D5(b): all 6). New independent argument for SPEC's reading:
  `validation_results`' PK **omits `table_id`**, so under D5(b) **24 of 128
  `EvaluationRow`s would be silently overwritten**; under SPEC's reading, none.
  No writer exists yet, so it is free to settle now. **This is the only item
  actually blocking the ablation.**
- **D-3 C7 converged optimum — the two blocks disagree**, which is why no blanket
  rule change is safe. **Block 11:** the discarded higher-llf candidate is a
  **genuine interior optimum wrongly rejected** — negative-definite Hessian,
  30/30 eigenvalues < 0, condition number 4.7e+14 (**100× better** than the
  selected point's 3.2e+16). **Block 10:** it is a **boundary/ridge artefact** —
  indefinite, at `|logit coef| = 434` (saturated to e^−434); the extra likelihood
  is bought with saturation. **On both blocks the currently-returned “converged”
  fit itself fails the second-order test** (3 positive eigenvalues each), and 12
  of 30 eigenvalues are near-null throughout, so the model is weakly identified
  and these verdicts rest on eigenvalues near double precision. Both options
  `HAMILTON-CAUSAL-POSTFIX.md` §5 floated are **contradicted**: a margin rule
  cannot separate the blocks (+873 and +1,179, both large) and a gradient-norm
  rule changes nothing (`|gopt|` already 1.1e−05 / 1.3e−05 at the selected
  points). A second-order negative-definite check is right on both blocks but
  returns **no fit** for block 10, needing a paired emit decision.
- **D-4 — all five mandated invariants verified correct** (IST timestamps: 0 of
  29 columns naive, `csrs.ts` 15:30 IST on all 4,714 rows; `writeBatch`
  idempotency verified **read-only**, no write performed; D4 noise exactly the
  bounded saturating form; `PILLAR_ORDER` single definition; D3 Ω_t on
  common-support intersection with both vectors renormalised).
- **Off-session bars fully characterised:** 10,368 bars (0.0552%) outside
  09:15–15:30 IST across 17 non-standard session dates. **15 legitimate** — 11
  Muhurat, 2 Saturday specials, and **2 COVID circuit-breaker halt days
  (2020-03-13, 2020-03-23) that sit *inside* the `covid_2020` crisis window**,
  which belong in the limitations. **4 genuine defects, none fixed** (each needs
  a DB write or C2's `ingestion/`): a missing morning on 2017-07-10 (~3,120
  bars); 30 **impossible** post-close bars on 2021-02-24; and two Muhurat
  sessions (2019-10-27, 2020-11-14) present in `intraday_bars` but **absent from
  `daily_prices`/`rmt_output`/`hamilton_output`** — the daily and intraday
  corpora disagree on whether a trading day exists. **No published result is
  invalidated**: 0 of the 4 defects fall in any FR32 crisis or lead window, so
  epoch-windowed statistics are unaffected; full-span statistics carry a
  0.30–1.06% contamination rate, stated as a rate rather than as zero.

## Approval gates — stated, none crossed

`CRISIS-REPLAY.md` §8 carries five with evidence, alternatives, consequences and
a recommendation each:

1. **C9's alert scale** — amber on 57–62% of days. *Recommended first; cheap and
   reversible.* Owner D.
2. **Pillar 1 cadence vs FR32's lead window** — mutually incompatible. Owner B
   with D.
3. **SPEC §4 coverage matrix** — not causally achievable for Hamilton pre-2015.
   Couples with D-2. Owners C + D.
4. **FR18 conformance** (`SCA_t` vs `λ₁/N`) — the one confirmed defect.
   *Sequence after gate 1.* Owner A.
5. **SPEC OQ3** — epoch 6's label is provisional, and three of the five warnings
   seen anywhere in the replay fall on that epoch.

Plus, from the workstreams: **FR35 Table B fold count** (D-2) and **CT-3 floor
retirement** (D-1), both owner decisions; and **FR32 unchanged** on B's
recommendation.

## Next executable task, per workstream

- **A:** resolve gate 1 (alert scale). Every operational statistic is
  uninterpretable until an amber light means something.
- **B:** *done.* Next: **re-state the T1 intervals in
  `DETECTION-CALIBRATION.md` and `STRESS-PILLAR-DECISION.md` against log 38's
  per-signal, per-block-length ledger, and mark every non-resolving claim as
  such.** No new computation or data — it is the smallest action that stops the
  repository asserting resolving power it does not have. Belongs to whoever owns
  those two documents. Strategic follow-on: **A4 cross-market replication**, the
  only route that adds *independent* realisations rather than more onsets on the
  same ~7 independent blocks.
- **C:** *done, and it mattered.* T3 power was re-measured against a 75-session
  linear ramp and an AR(1)-persistent drift (φ = 0.9973) rather than only a
  rectangular step, under a **pre-registered** rule that "no advance warning"
  would be downgraded to "untestable at six onsets" if ramp power at δ = 1.0 sd
  fell below ~50%. Measured: **75–77% (ramp)** and **78–80% (drift)** against
  80–85% (step), type-I 2–8% at nominal 5%. **The bound held**, so the negative
  stands against the signal shape a systemic-risk thesis predicts — a stronger
  statement than the original step-only figure licensed. The ramp survives
  because it **peaks at the onset**: 360 of its 450 signal-carrying days land on
  days T3 labels negative, yet its final 15 days still carry mean amplitude
  0.9067 against the step's 1.0000.
  **Two measured limits on that bound, both now written into the reports:**
  (i) it is **horizon-specific** — at a matched 75-session horizon ramp power
  falls to **37%**, below the 50% line, so at 60–90 session leads the test is
  underpowered and a long-lead claim is untestable on six onsets either way
  (nobody has made one; this bounds any future one); (ii) it assumes the build-up
  **peaks at onset** — the injection was pre-registered at equal *peak*
  amplitude, which is the generous choice, and under fixed-*energy*, plateau or
  early-peaking shapes power would be lower. **(ii) is the one open threat to the
  “informative null” claim**, and C's next task is to close it.
- **D:** *done.* Next, and it may dissolve D-3 entirely: **raise `maxiter` above
  200 and re-run causal blocks 10 and 11.** Every non-converged candidate across
  both blocks reports `warnflag = 1` — *maximum iterations reached* — and never
  `2` (precision loss), so the convergence failures may be nothing but the
  200-iteration budget. No approval and no engine edit needed (pass `maxiter` to
  the existing `fit()` from a script); ~1 hour for two blocks. In parallel, get
  the one-sentence **D-2 Table B fold-count decision**, the only item actually
  blocking the ablation.
- **C:** *done.* Next: **pre-register and test fixed-energy, plateau and
  early-peaking build-ups** — the one remaining way the “informative null” could
  fail. Until it is closed, the T3 power claim should read *informative against
  build-ups that peak at onset*, not against build-ups generally.

---

**Written 2026-08-23. Verified facts and decisions only — no speculation.**
Read this before `docs/SPEC.md`. Where this file and older docs disagree, **this file wins**, because
several earlier conclusions were measured to be wrong and are recorded as such.

---

## 1. ARCHITECTURE (locked)

```
5-minute + daily NSE data
  Pillar 1  discrete-time Hawkes  -> contagion / risk-state
  Pillar 2  RMT                   -> systemic coupling
  Pillar 3  TVTP Hamilton         -> regime / liquidity state
        -> C8 Kalman multi-timescale reconciliation
        -> C9 CSRS final systemic-risk state
```

- **NB / count models are supporting activity and distributional features. They are NOT a pillar and
  do NOT replace Hawkes.**
- **Hawkes is not claimed to independently predict future abnormal risk.**
- **Hamilton is required to remain in SERAPH.**
- All 12 components (C1–C12) plus T0 exist. Suite was **120 passed** at the last full run.

---

## 2. PILLAR 1 / HAWKES — **LOCKED, do not redesign**

- Continuous-time pooled Hawkes **rejected**: 5-minute timestamp ties make `β` unidentifiable
  (75.8% of events share a bar, max 89 simultaneous; `β̂` pinned at every bound 72→2880).
  Retained in code as **legacy/diagnostic only**; `BETA_MAX` must never re-enter production.
- **Production model: discrete-time Hawkes at native 5-minute resolution**, geometric kernel,
  negative-binomial emission, intensity reset to the ToD baseline at each session open.
- Validated real-data parameters: **α ≈ 0.0557, φ ≈ 0.4837, n ≈ 0.1079**, parameter **CV ≈ 2–4.1%**,
  interior and stationary on every fold.
- **FR13 asymmetry gate** re-specified: one-sided exact binomial test of the window's downside share
  against the **empirical NSE baseline ≈ 0.4254**, not the invalid 0.5 symmetric null
  (measured z = −33.3 from symmetry). Fires on 28.3% of windows. A closed gate is a **normal-mix
  state** (warned, `n` still reported), not an absence of contagion.
- C5 production path verified isolated from legacy code by test.
- **Do not redesign C5 unless a concrete correctness issue is found.**

Evidence: `docs/AMENDMENT-03-jump-sparsity-R2.md`, `docs/PILLAR1-SELECTION-RULE.md`,
`docs/REPORT-SECTIONS-PILLAR1.md`. SPEC is at **v4** with FR10/FR11/FR13/O2 amended.

---

## 3. PILLAR 3 / HAMILTON — **current authoritative result**

- Constant-transition 2- and 3-state formulations are **invalid / non-identifiable** on real data
  (occupancy 0/0/100, transitions on the numerical boundary). This was **not** a feature-smoothness
  problem — innovation features with autocorrelation removed collapsed identically.
- **Specification-faithful TVTP rescued the model.** TVTP is the retained Hamilton formulation.
- Current 3-state TVTP result, written to E8 for all **5,365 days**:
  - occupancy **43.0% / 25.2% / 31.8%**
  - separation **2.02σ**
  - half-lives **finite** (stressed 110d, crisis 46d), transitions **interior**
  - regime means economically ordered: RV **0.389 → 0.489 → 0.664**, BAS and AR also increasing
- **FR21 macro covariates are NOT ingested.** `macro_covariates`, `tariff_events` and
  `flow_aggregates` are all **empty**. Do not claim they were used. The implementation uses
  **strictly causal lagged standardised RV** under FR21's *state-dependent structural-break* clause.
- **NFR16 = 4/6** (corrected; an earlier 6/6 was vacuous — it tested only whether the filter was
  confident, not whether it was confident in the *correct* state):

  | Epoch | Result |
  |---|---|
  | GFC 2008 | PASS (crisis, 30/30 days elevated) |
  | Taper 2013 | PASS (stressed, 30/30) |
  | IL&FS 2018 | PASS (crisis, 23/30) |
  | COVID 2020 | PASS (crisis, 18/29) |
  | Tightening 2022 | **FAIL** (0/30) |
  | Tariff 2026 | **FAIL** (0/30, provisional date) |

- **NFR17 FAILS: 2.02σ < 3σ required.** Do not tune to force it to pass.
- **Do not redesign C7 unless a new concrete issue is found.**

---

## 4. PILLAR 2 / RMT — validation run **COMPLETE**, with one failure

Run finished after the handoff was requested. Results below are measured, `stride=10`.

- **Coverage: 374 dates evaluated, 163 skipped**, 2005-01-03 → 2026-08-17. **374 rows written to E7.**
- **`N_t` range 122–499; `Q_t` range 2.00–8.20** — early corpus behaves as AMENDMENT-02 predicts.
- **PASS — PSD:** min eigenvalue across corpus `3.71e-02` (> 0).
- **PASS — AMENDMENT-02:** `max |λ± − MP(Q_t)| = 0.00e+00`. Bounds are genuinely recomputed per date;
  no hard-coded Q=2.
- **PASS — FR18:** SCA_t mean 0.4359, sd 0.1519 — non-degenerate.
- **PASS — FR19:** all p-values in [0,1].
- **PASS — D3:** Ω_t at rebalance dates 0.0000 vs 0.0002 elsewhere — no spike. Common-support
  fraction mean 0.992, min 0.412.
- **FAIL — FR16 arithmetic guard:** `max |trace(C_t) − N_t| = 4.99e-01`. A correlation matrix has unit
  diagonal, so the trace must equal `N_t` exactly. **This is a real defect and must be diagnosed
  before Pillar 2 is declared validated.** Most likely cause: constant/zero-variance columns being
  guarded to `sd = 1` in `_correlation`, which yields a diagonal entry ≠ 1 for those symbols.
  Check `seraph/pillars/rmt/engine.py::_correlation`.

**Two further observations, not yet explained:**
- **`F_t` does not rise at stress dates.** GFC 0.0230, COVID 0.0182, IL&FS 0.0183 against a corpus
  median of 0.0221 — COVID and IL&FS are *below* median. SCA_t does move (0.5587–0.7321 vs mean
  0.4359). Whether `F_t` is the wrong stress statistic here, or whether this reflects the
  Q-dependence documented in AMENDMENT-02, is **unresolved**.
- **FR19 p-values are significant at 5% on 100.0% of dates.** A test that always rejects carries no
  discriminating information; the bootstrap null may be mis-calibrated. **Investigate.**

**Pillar 2 is NOT fully validated.** The engine's isolated behaviour is sound (CT-10 5/5; 2008 and
2020 spot checks reproduce), but the FR16 trace failure and the two observations above must be
resolved first. `stride=10` means this is a **validation run, not the production daily series**
FR16 specifies.

---

## 5. METHODOLOGY PRINCIPLE (binding)

- **Never alter a model just to make a requirement or test pass.**
- If a requirement is unsupported by the available data, report the limitation and propose the
  smallest scientifically defensible amendment.
- **Do not fabricate unavailable macro data.**
- **Do not manufacture predictive skill.**
- **Do not hide failed validation criteria.** NFR17 fails. NFR16 is 4/6. FR16's trace guard fails.
  All three stay visible.

---

## 6. IMMEDIATE NEXT TASK

**Diagnose the three Pillar 2 findings in §4** — the FR16 trace failure first, then the flat `F_t`
at stress dates and the 100%-significant p-values. Then re-run and decide whether C6 is ready for a
full daily production run.

**Do NOT:** redesign Hawkes; redesign Hamilton; modify Kalman; modify CSRS; rewrite the
architecture; ingest external data; tune models to improve reported metrics.

### Known open items (context only, not the current task)
- SPEC OQ3 (Epoch 6 tariff break date) and OQ13 (crisis labelling source) are **open**;
  `seraph/validation/epochs.py` holds provisional defaults in one place.
- FR22 `G_t`, C2 macro/flow/tariff clients, FR54 index validation: not built.
- 20-config ablation: not run.
- `csrs` table: **empty** — no end-to-end CSRS has been produced yet.
- Tariff-sector basket in `seraph/ingestion/hawkes_universe.py` needs team sign-off (SPEC OQ1).
- Kite redistribution constraint (SPEC §7.14) still to be raised with Dr. Satisha.

---

## 7. NEXT CONTEXT

Start the next session with:

> "Read the project handoff. Continue from the current validated SERAPH state; do not repeat
> completed Hawkes/Hamilton investigations."

Environment: uv-managed venv at `.venv` (CPython 3.12; no system Python, MSI blocked).
TimescaleDB via `docker compose up -d`, DSN `postgresql://seraph:seraph@localhost:5433/seraph`.
Kite tokens expire ~06:00 IST daily — re-auth with `python scripts/kite_login.py`.

Data in place: `daily_prices` 8,023,206 · `intraday_bars` 18,781,302 (94 symbols) ·
`universe_snapshots` 44 (ETF-free) · `hamilton_output` 5,365 · `rmt_output` 374 · `csrs` 0.
