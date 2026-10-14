# The three free checks — results and go/no-go

**O5 (advance warning) remains the objective.** Nothing here proposes re-scoping,
and nothing claims SERAPH has demonstrated advance-warning capability.

Three checks were authorised from `DECISION-PACKAGE.md` §5. **Two are NO-GO, one
is a qualified GO**, and two unrelated findings emerged that are cheaper and
better-founded than the candidate they displace.

| # | check | verdict |
|---|---|---|
| 1 | Hawkes conditional-intensity (`λ_t`) pre-onset screen | **NO-GO** — measured, DURING, below its own null |
| 2 | RBI / money-market publication-delay audit | **QUALIFIED GO** — daily and point-in-time clean, but a methodology break sits on the epoch boundary |
| 3 | Historical option-chain coverage | **NO-GO as specified** — pre-2015 depth unverifiable publicly; evidence leans negative |

Settled 2026-10-14 on git `f3eaac8`. Database read-only. `seraph/` unmodified.
No production code, specification or pre-registration artefact changed. Nothing
committed or pushed. **No data purchased.**

| artefact | path |
|---|---|
| check 1 screen | `scripts/screen_hawkes_intensity.py` |
| check 1 results | `docs/evidence/signals/hawkes_intensity_screen.json` |
| check 1 log | `*-110-hawkes-intensity-screen.log` |

---

## Check 1 — Hawkes conditional intensity: NO-GO

**Hypothesis tested.** The 19-feature audit screened Pillar 1 as
`MTS_t = n/(1−n)`, which is a function of the fitted parameters and therefore
piecewise-constant between refits. FR13 `[v4]`/NFR4 specify emission at **bar
frequency**, and the only quantity that genuinely varies at that frequency is
the conditional intensity `λ_t = μ·ToD(t) + α·Σ_k φ^(k−1)·N_(t−k)`
(`engine.py:214`, `excitation_path`, never persisted). This was the last
held-data hypothesis the audit did not cover.

**A finding before the result: the fitted parameters are not stored.**
`hawkes_output.alpha_beta` is **NULL on every row**. The writer persists
`branching_ratio_n` and `mts` but not `α`, `φ`, `μ` or the time-of-day profile,
so **`λ_t` cannot be reconstructed from the database at all.** The column exists
and is empty. Rather than re-run the 164-minute refit schedule, the excitation
term was rebuilt at **SPEC FR11 `[v4]`'s own quoted values** — *"Measured n ≈
0.11 (α ≈ 0.055, φ ≈ 0.50, ≈ one-bar half-life)"* — so nothing was fitted to the
evaluation data.

**Stream rebuilt from `intraday_bars` (read-only):** 213,751 bars, 94 symbols,
3,558 non-positive closes dropped and counted (never patched), **22,114 negative
jumps**. Consistent with Workstream D's independent corpus-wide 21,180.

### Result

| series | BEFORE (−15d) | DURING (0..+30) | AFTER (+31..+60) | class |
|---|---|---|---|---|
| `λ_t` reconstructed | **+0.045** | +1.017 | +0.485 | **DURING** |
| negative jumps / active symbol | **+0.045** | +1.024 | +0.471 | **DURING** |

| series | T3 AUC | p (relocation) | p (AAFT) | own no-signal p95 | verdict |
|---|---|---|---|---|---|
| `λ_t` reconstructed | 0.5496 | 0.1194 | 0.1214 | **0.5697** | **below null** |
| negative jumps / active symbol | 0.5376 | 0.1774 | 0.1984 | 0.5687 | **below null** |

**`λ_t` classifies as DURING with a pre-onset separation of +0.045σ, and its T3
AUC sits below the 95th percentile of its own no-signal distribution.** Neither
p-value reaches an *uncorrected* 0.05, against Holm's 0.025 over the two
comparisons. Resolution floor 0.00050.

**The conclusion does not depend on the reconstruction.** The raw daily
negative-jump count and the reconstructed `λ_t` agree to three decimals on every
timing statistic. That is expected and was stated in advance: at φ ≈ 0.50 the
excitation term has a one-bar half-life, so its daily aggregate is close to a
scaled jump count. Both routes give the same answer.

### A hard structural bound, independent of the result

`intraday_bars` begins **2015-02-02**. The screen covers **4 of 6 epochs**
(`ilfs_2018`, `covid_2020`, `tightening_2022`, `tariff_2026`) and **cannot reach
`gfc_2008` or `taper_2013` at any refit cadence or emission frequency.** No
engineering change to Pillar 1 can alter that; only intraday data before 2015
could, and `DATA-ACQUISITION.md` records the Kite intraday limit as the reason it
does not exist.

### Consequence for the cadence proposal

`DECISION-PACKAGE.md` §4.1 proposed asking the FR13 owner whether `λ_t` should be
emitted, **gated on this screen**. **The gate has closed: do not propose the
emission change as an advance-warning improvement.** `λ_t` has no measurable
pre-onset content on the epochs it can cover, and cannot cover the other two.

Two narrower reasons to make the change anyway remain, and should be judged on
their own terms, not on O5:

1. **FR13/NFR4 conformance.** Both specify bar-frequency emission; the pipeline
   persists 473 roughly-weekly rows. That is a conformance gap whatever `λ_t`
   predicts.
2. **CSRS input resolution.** `λ_t` is the only Pillar 1 quantity with
   bar-frequency variation, and FR13 `[v4]` already classifies Pillar 1 as a
   *"contagion / risk-state diagnostic contributing to the CSRS, **not** an
   independently demonstrated forward alarm."* Improving a diagnostic's
   resolution is a coherent goal; it is simply not an O5 goal.

**Also worth fixing regardless: persist `alpha_beta`.** It is a declared column
sitting empty, and its absence meant this screen had to reconstruct what the
pipeline already computed. **Owner: B (C5).**

---

## Check 2 — money-market publication delay: QUALIFIED GO

The decisive question was never price; it was whether a funding-stress series
would have been **available at the 15:30 IST decision time**. Two sources, and
they give opposite answers.

### RBI Weekly Statistical Supplement — fails the gate

**VERIFIED (rbi.org.in).** The WSS is published **every Friday at 5 pm** and
carries the policy repo, SDF, MSF, **call money rate (weighted average)** and
Treasury-bill yields.

It fails on two counts:

* **Weekly, not daily.** A weekly series yields ~3 observations inside FR32's
  15-day lead window — the same resolution failure that makes Pillar 1
  untestable.
* **5 pm is after the 15:30 close.** A Friday figure is not available at
  Friday's decision time; it arrives the following session.

Per `NEXT-PREREGISTRATION-DRAFT.md` §2 this is a **NO-GO** for the WSS path.

### FBIL benchmarks — passes the gate

**VERIFIED (fbil.org.in and corroborating sources).**

| property | value |
|---|---|
| **Overnight MIBOR** | published **daily at 12:45 PM IST** |
| **Term MIBOR (14-day, 1-month, 3-month)** | published **daily at 1:45 PM IST** |
| frequency | daily, excluding Saturdays, Sundays and local holidays |
| availability at the 15:30 decision | **yes — both precede the close** |
| effective publication lag | **zero trading days** |
| archive | FBIL "Historical Data & Methodology" → Benchmark Data (Overnight MIBOR, Market Repo Overnight Rate) |
| basis | **transaction-based** since **2015-07-22** (replacing polled MIBID/MIBOR) |
| licensing | **FBIL does not authorise commercial use without written permission** |

**This clears the point-in-time gate that disqualified every other macro
candidate**, and the Term MIBOR series makes a **term spread** (overnight versus
3-month) constructible — which is the theoretically-leading quantity, not a
level.

### The serious caveat, and it is not price

**The benchmark methodology changed on 2015-07-22**, from polled MIBID/MIBOR
(NSE/FIMMDA era) to transaction-based FBIL. That break sits **almost exactly on
the pre/post-2015 epoch boundary**:

* legacy polled series → covers `gfc_2008`, `taper_2013`
* FBIL transaction series → covers `ilfs_2018`, `covid_2020`, `tightening_2022`,
  `tariff_2026`

**Splicing them means a feature that changes definition between the 2013 and 2018
epochs** — precisely the kind of discontinuity that produces a spurious
cross-epoch result. Third-party mirrors exist (one hosts daily MIBID/MIBOR from
1998, which is the legacy series; another carries FBIL Overnight from July 2015),
but they do not remove the break, they only make it easy to ignore.

### Recommendation for check 2

**GO, scoped as follows:**

1. **Acquire the FBIL daily series first** (overnight + term), free from
   fbil.org.in, and confirm the licensing position for an academic report.
2. **Resolve the splice before using pre-2015 data.** Establish whether any
   overlap period exists between the polled and transaction series; if it does,
   measure the level and volatility shift across it. **If there is no clean
   overlap, scope the feature to the four post-2015 epochs** and say so, rather
   than splicing across a definitional change.
3. **Screen the term spread under `NEXT-PREREGISTRATION-DRAFT.md`** before any
   fusion work. Note §2's independent-epoch gate: a 4-epoch-only feature covers
   the same four on which India VIX already fails, so it would need to clear the
   bar on its own merits rather than by adding epochs.

**This is the only one of the four acquisition candidates that passes the
point-in-time gate on verified evidence.**

---

## Check 3 — historical option-chain coverage: NO-GO as specified

**A useful reframing first.** NSE F&O bhavcopy carries strike-level
**settlement prices**, expiries and open interest. Implied volatility is
*derivable* from those via Black–Scholes, so no IV field is required — which
makes the question purely one of archive depth.

### What is VERIFIED

* The legacy archive path
  `historical/DERIVATIVES/YYYY/MON/foDDMONYYYYbhav.csv.zip` served F&O bhavcopy
  **through 2024-07-05**.
* NSE **discontinued the legacy CSV with effect from 2024-07-08**, replacing it
  with F&O-UDiFF Common Bhavcopy Final. Any backfill must therefore handle **two
  schemas** — the same two-schema problem `DATA-ACQUISITION.md` already records
  for equity bhavcopy.

### What is UNVERIFIED or UNKNOWN — including the decisive fact

* **No official NSE statement on pre-2010 F&O availability was found.**
* Third-party tool ranges, which are tool limits and not NSE limits, all start
  late: one R package's F&O function covers **2020-01-01+**, its legacy function
  **2016-01-01 to 2024-07-05**; a community data bank holds **1,579 archives
  from 2020-04-13**.
* Community reports indicate **manual fetches error before about 2010**.
* **Price: UNKNOWN.** NSE's paid EOD F&O product exists
  (`marketdata@nse.co.in`, +91-22-2659 8385) but publishes no price.

### Verdict

**NO-GO as specified, on the gate `DECISION-PACKAGE.md` §3 set in advance:** GO
only if pre-2015 strike-level data is confirmed available. It is not confirmed,
and the available evidence leans against it. The candidate is **not refuted** —
it is **unverifiable from public sources**, which is a different thing and is why
the next step is a question rather than a purchase.

**The single question to put to NSE:** *does NSE provide F&O bhavcopy or
equivalent strike-level derivatives settlement data for 2008–2010, and in what
format and at what cost?* Until answered, candidate 1 cannot be costed or
scheduled.

### A correction to the repository's own documentation

`docs/DATA-ACQUISITION.md:106` states: *"**India VIX starts Nov 2007.**
Confirmed."* **Independent search does not corroborate this and tends to
contradict it.** Public sources place the India VIX **launch in 2008** (one
specifying April 2008, with the methodology licensed from CBOE), real-time
dissemination from around **2009–2010**, and VIX **futures** only from
**February 2014**. The index's highest reading, 92.5, was recorded in **November
2008**, so values existed in its first year — but no source found supports a
November 2007 start.

**Why this matters.** The ingested series starts **2014-05-15**, suspiciously
close to the Feb-2014 futures launch, which suggests the current data came from a
source that begins when VIX became a tradeable underlying rather than when the
index began. So:

* **There probably is uningested VIX history** (roughly 2008–2014) — a free
  coverage gain.
* **But it would extend coverage from 4 epochs to 5, not 6.** Even at the
  earliest plausible launch (April 2008), the `gfc_2008` onset is ~5 months
  later, which cannot populate FR28's rolling five-year ECDF window. `taper_2013`
  would be covered properly.
* **`DATA-ACQUISITION.md`'s "Confirmed" should be downgraded to unverified** and
  the true start established from NSE Indices directly. **Owner: A/C (whoever
  owns OQ5).** Not corrected here — it is another owner's document.

---

## Two findings that displace candidate 1

Both emerged from the repository's own acquisition notes while verifying check 3,
and both are better-founded and cheaper than the paid option-chain route.

### (a) NSE participant-wise F&O open interest — free, and a more direct proxy

`DATA-ACQUISITION.md:120` records: *"NSE publishes **participant-wise open
interest** for F&O with four categories — FII, DII, PRO, CLIENT"*, flagged **"Low
priority, cheap to add later."**

**This is arguably a better candidate than option skew, and it is free.** Skew is
a *price-based proxy* for demand for crash protection; participant-wise option OI
is a **direct positioning measure** — it shows whether FIIs are actually
accumulating puts. The mechanism the skew hypothesis appeals to is measured more
directly by the quantity than by the price.

**Unknown and must be checked:** archive depth, publication time relative to
15:30, and whether the series is revised. All three are free to establish.

### (b) FII/DII timing is adequate; the obstacle is revision, not delay

`DATA-ACQUISITION.md` records FII/DII as *"published daily after close (~8:30–
9:30 PM IST)"* — a one-session lag, which **passes** the ≤2-trading-day gate. So
candidate 4's ranking was driven by the right reason: the figures are
**provisional and restated**, and replay requires the *as-first-published*
vintage. Timing was never the problem.

---

## Where this leaves the programme

**O5 remains the objective and the implementation has not earned the claim.**
What the three checks change is which route is worth funding.

**Closed by measurement.** Pillar 1's bar-frequency quantity has no pre-onset
content on the four epochs it can cover, and cannot cover the other two. With
this, **every input in or derivable from the repository has now been screened**:
19 in the audit plus `λ_t` and the raw jump count here, all DURING or AFTER, all
below their own no-signal distribution.

**The ranked next step, revised by evidence:**

1. **FBIL money-market term spread** — the only candidate passing the
   point-in-time gate on verified evidence. Free. Resolve the 2015-07-22
   methodology splice first.
2. **NSE participant-wise F&O open interest** — free, a more direct measure of
   crash-protection demand than skew. Establish depth, publication time and
   revision policy.
3. **India VIX backfill to its true start** — free, closes a coverage gap, and
   corrects a documentation error. Extends coverage to 5 epochs, not 6.
4. **Option-chain skew** — now **below** the two free candidates above, because
   its decisive coverage fact is unverifiable and its cost is unknown while both
   alternatives are free. Revisit only after NSE answers the §3 question.
5. **Cross-market replication** — unchanged; the only route adding independent
   realisations, and the largest effort.

**Stop conditions from `DECISION-PACKAGE.md` §6 remain in force**, including the
one that matters most: **if two acquired inputs, each with a prior mechanistic
reason to lead, both fail `NEXT-PREREGISTRATION-DRAFT.md`, the advance-warning
programme should stop.** Candidates 1 and 2 above are the two that should be
tested against it.

**Nothing in this document proposes an implementation change.** The three
engineering items it surfaces — persist `alpha_beta`, FR13/NFR4 emission
conformance, and the `DATA-ACQUISITION.md` VIX correction — are each another
owner's, and each is stated as a gate rather than acted on.

---

## Sources

- [RBI release calendar of communication](https://rbi.org.in/commonman/English/scripts/commpan3.aspx)
- [RBI Weekly Statistical Supplement](https://rbi.org.in/Scripts/WSSView.aspx?Id=28117)
- [RBI data releases](https://rbi.org.in/Scripts/Statistics.aspx)
- [FBIL (benchmark publication times, historical data section)](https://www.fbil.org.in/)
- [FBIL MIBOR page](https://fbil.org.in/securities?mq=o&op=mibor)
- [MIBOR background — transaction-based benchmark from 22 July 2015](https://en.wikipedia.org/wiki/MIBOR_(Indian_reference_rate))
- [NSE all reports — derivatives](https://www.nseindia.com/all-reports-derivatives)
- [NSE paid EOD / historical data subscription](https://www.nseindia.com/static/market-data/eod-historical-data-subscription)
- [`nser` package reference (documents F&O bhavcopy paths and tool ranges)](https://cran.r-project.org/web/packages/nser/nser.pdf)
- [NSE F&O data bank (community backfill, 2020-04-13 onward)](https://github.com/SantoshSrinivas79/NSE-FNO-Data-bank)
- [India VIX background (launch year, real-time dissemination, futures)](https://www.motilaloswalmf.com/motilal-oswal-edge/articles/a-study-on-india-volatility-index-vix)
