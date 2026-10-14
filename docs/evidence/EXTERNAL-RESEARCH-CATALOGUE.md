# External research catalogue — what could actually help, and what could not

**Deliverable C of `INDEPENDENT-AUDIT.md`.** Screened against one question:
**would this plausibly add pre-onset information that SERAPH does not already
have, on data we can obtain, at the 5–15 trading-day horizon FR32 specifies?**

Most candidates fail that screen for a reason worth recording. A method that
measures risk *during* a crisis cannot help a project whose 25 screened features
are already all DURING or AFTER.

## Verification markers — applied to every row

* **VERIFIED** — confirmed from a primary or near-primary source this session.
* **UNVERIFIED** — named and plausible, not confirmed; must be checked before commitment.
* **UNKNOWN** — could not be established. No figure is invented in its place.

**I could not verify a single price, and historical depth for none of the paid
options.** That is itself the finding that keeps the free candidates ranked
above the paid one.

---

## The screening logic, stated before the ranking

Three filters, applied in order. A candidate must pass all three.

1. **Does the literature show it *leading*, or only coinciding?** Most
   systemic-risk measures are contemporaneous by construction. Giglio, Kelly &
   Pruitt's evaluation of 17–22 measures found predictive content in the
   *combined* index *"despite the individual failure of many measures on this
   account"* — i.e. individually, most fail.
2. **Is it computable at the decision time?** FR32's lead window cannot be
   populated by a value published after 15:30 IST, or by a revised vintage.
3. **Does it add information beyond the 25 features already screened?** All 25
   are transforms of held NSE price/intraday data, so another such transform
   adds multiplicity cost without new information.

---

## Ranked catalogue

### 1. FBIL money-market term spread — **ADOPT (free)**

| field | detail |
|---|---|
| source | `https://www.fbil.org.in/` — Historical Data & Methodology → Benchmark Data |
| method | Overnight MIBOR vs Term MIBOR (14d / 1m / 3m); the spread, not the level |
| evidence | Funding stress is the classic pre-equity-crisis channel. **VERIFIED**: Overnight MIBOR published **daily at 12:45 PM IST**, Term MIBOR at **1:45 PM** — both *before* the 15:30 decision, giving **zero-day lag**. Transaction-based since **2015-07-22** |
| licence | **VERIFIED constraint**: FBIL "does not authorise commercial use of the data available in its website without written permission". Academic position **UNKNOWN** |
| data needed | daily overnight + term rates, 2008+ |
| library or model | neither — a data feed plus a two-line spread |
| compatibility | trivial; a new `macro_covariates` column or a C2 ingestion path |
| expected benefit | **the only candidate verified point-in-time clean.** A term spread is the theoretically-leading quantity, not a level |
| limitations | **the methodology break at 2015-07-22 sits on the pre/post-2015 epoch boundary.** Splicing polled and transaction series means a feature that changes definition between the 2013 and 2018 epochs |
| effort | S |
| recommendation | **ADOPT**, after resolving the splice. If no clean overlap exists, scope to the four post-2015 epochs and say so |

### 2. NSE participant-wise F&O open interest — **PROTOTYPE (free)**

| field | detail |
|---|---|
| source | NSE daily reports; recorded in this repo's own `docs/DATA-ACQUISITION.md:120` as *"participant-wise open interest for F&O with four categories — FII, DII, PRO, CLIENT"*, flagged **"Low priority, cheap to add later"** |
| method | FII net option positioning, especially put open interest |
| evidence | Skew is a *price proxy* for demand for crash protection; participant OI measures that **positioning directly**. The option-implied literature (Gao–Pan crash-fear index from short-dated OTM puts) motivates the channel |
| licence | **UNVERIFIED** |
| data needed | daily participant-category OI by instrument type, 2008+ |
| compatibility | new ingestion; no pillar change |
| expected benefit | **more direct than skew, and free** — the main reason it outranks candidate 4 |
| limitations | **UNKNOWN**: archive depth, publication time relative to 15:30, revision policy. All three free to establish |
| effort | S–M |
| recommendation | **PROTOTYPE** — establish the three unknowns first; they are a desk exercise |

### 3. `arch` (Python) — **ADOPT as a baseline, not as a pillar**

| field | detail |
|---|---|
| source | `https://pypi.org/project/arch/` (bashtage / Kevin Sheppard). **VERIFIED**: GARCH, TARCH, EGARCH, EWMA/RiskMetrics; Cython/Numba accelerated; Python-3 only; docs on Read the Docs (released) and GitHub Pages (main); PyPI versions seen to 6.3.0 |
| licence | **UNKNOWN** — not stated in the sources retrieved. **Check the repo LICENSE before adding to `pyproject.toml`** |
| method | conditional volatility; a GARCH baseline |
| evidence | Mature, standard, widely used. Not an early-warning method — a *baseline* |
| compatibility | high; pure-Python/NumPy, matches the declared stack |
| expected benefit | **closes a real gap in the evidence, not in the model.** SERAPH currently has **no GARCH baseline**, which weakens every comparison it makes. A conditional-volatility baseline is what a sceptical examiner will ask for first |
| limitations | adds no pre-onset information; GARCH is a contemporaneous/1-step-ahead vol model |
| effort | S |
| recommendation | **ADOPT** — as a declared baseline in the comparison suite. **Do not present it as a predictive addition** |

### 4. Option-implied skew and term structure — **CONDITIONAL (gated)**

| field | detail |
|---|---|
| source | NSE paid EOD F&O (**VERIFIED** to exist; `marketdata@nse.co.in`, +91-22-2659 8385; **price not published**). Free bhavcopy archive: legacy path served through **2024-07-05**, **discontinued 2024-07-08** in favour of UDiFF |
| method | 25-delta risk reversal; near/far implied-vol ratio. **IV is derivable from strike-level settlement prices — no IV field required** |
| evidence | **The best-documented short-horizon family.** Bollerslev–Tauchen–Zhou (2009): variance risk premium predicts aggregate returns at horizons up to a quarter; Bollerslev et al. (2015): tail-risk premium has independent predictive content; a Fed paper finds the skewness risk premium (VRP^U − VRP^D) matters; Gao–Pan (2018) crash-fear index |
| licence | **UNKNOWN** |
| data needed | daily NIFTY option chain, strike-level, **2008+**, ≥5 strikes either side on the two nearest expiries |
| limitations | **the decisive fact is UNKNOWN**: no official NSE statement on pre-2010 availability; third-party tool ranges start 2016/2020; community reports of fetch errors before ~2010. Two schemas for any backfill. Illiquid far strikes give unstable IVs |
| effort | M–L |
| recommendation | **CONDITIONAL — NO-GO until pre-2015 depth is confirmed.** If coverage starts after ~2015 it covers only the four epochs where India VIX is **already anti-predictive** (−0.613σ pre-onset, T3 AUC 0.4057) and adds no independent episode. One question to NSE resolves it |

### 5. Cross-market replication (O9 / FR37–38) — **MONITOR**

| field | detail |
|---|---|
| method | run the same pillars on a second market |
| evidence | **The only route that adds genuinely independent realisations** rather than more onsets on the same ~7 independent blocks |
| limitations | **measured caveat**: 10 of 15 candidate onsets are *global* and would be common to any second market; only ~5 are domestic. So it adds far less independence than the event count suggests |
| effort | L — the largest in the catalogue |
| recommendation | **MONITOR.** Correct in principle, poor return per unit effort until a signal exists worth replicating |

### 6. `ruptures` (change-point detection) — **PROTOTYPE, low priority**

| field | detail |
|---|---|
| source | PyPI / GitHub (`deepcharles/ruptures`). **UNVERIFIED** — not covered by this session's search; maintenance status and licence unconfirmed |
| method | offline/online change-point detection on a univariate or multivariate series |
| evidence | Mature method family. **Offline detection is retrospective by construction** — it finds breaks in a completed series |
| expected benefit | Could sharpen *crisis labelling* (SPEC OQ13, "who fixes the exact break date, against what source", is still open) rather than provide a signal |
| limitations | **an offline change-point detector is not an early-warning signal.** Using it to date onsets and then evaluating a signal against those onsets risks circularity — the labels must stay exogenous |
| effort | S |
| recommendation | **PROTOTYPE for labelling only**, and only if OQ13 is being settled. **Reject as a predictive input** |

### 7. `hmmlearn` — **REJECT for this purpose**

| field | detail |
|---|---|
| source | PyPI / GitHub. **UNVERIFIED** — not covered by this session's search |
| method | Gaussian / discrete HMMs |
| evidence | Mature and standard |
| limitations | **SERAPH already has a regime model (P3), implemented with `statsmodels` TVTP as the spec requires, and its estimator is now ground-truth validated at path accuracy 1.0000.** The failure is not the library: the *regime structure itself* is indistinguishable from a single-regime AR(1) surrogate (AAFT p = 0.7143, AR(1) p = 0.9524). A different HMM library fits the same absent structure |
| recommendation | **REJECT.** Swapping libraries cannot create regimes the data does not contain. AGENTS.md §3 also already rejects `rpy2`/`MSwM` for the same reason |

### 8. Gradient-boosted trees (XGBoost / LightGBM / CatBoost) — **REJECT at current N**

| field | detail |
|---|---|
| evidence | Strong on tabular problems with many independent examples |
| limitations | **N_eff ≈ 5 independent events.** A regularised *logistic* model with three coefficients already could not be estimated — only 1 of 4 development folds had ≥10 training positives, and where inner CV could choose it selected the **strongest** regularisation (`C = 0.01`) and drove the coefficients to ≈0. Its own cross-validated answer was "predict the base rate" |
| recommendation | **REJECT until N_eff supports it.** Minimum to revisit: ~20 independent episodes. Adding capacity to a problem with no signal and 5 effective events manufactures overfit, which is the failure mode this audit exists to prevent |

### 9. CoVaR / MES — **REJECT as a predictive input**

| field | detail |
|---|---|
| evidence | **VERIFIED critique**: Danielsson et al., *Model Risk of Systemic Risk Models* — MES and CoVaR *"contain a high degree of model risk so that the signal they produce is highly unreliable"*; ΔCoVaR's time-series correlation with VaR is *"almost 1"*, so it may add little beyond VaR |
| limitations | Institution-level systemic *exposure*, contemporaneous, and requires institution balance sheets SERAPH does not hold. Not a market-wide onset forecast |
| recommendation | **REJECT.** Different task, contested evidence, missing data |

### 10. SRISK and capital-structure measures — **MONITOR (the most interesting rejection)**

| field | detail |
|---|---|
| evidence | ESRB working paper: SRISK increases predict falls in industrial production and rises in unemployment, **stronger at longer horizons**. Acharya et al. (1927–2023): **capital-structure measures (SRISK/ME, market leverage, book equity ratio) are better predictors of bank failures than co-movement measures** |
| why it matters here | **This is the sharpest structural diagnosis of SERAPH available.** All three pillars are *co-movement/dynamics* measures — RMT is correlation structure, Hawkes is event co-excitation, Hamilton is regime dynamics — which is the family the literature finds **weakest** for prediction. SERAPH holds **no balance-sheet data at all**, which is the family it finds **strongest** |
| limitations | Target is macro downturns at quarterly horizons, not 5–15 day market onset. Needs bank balance-sheet data (acquisition) |
| recommendation | **MONITOR, and record the diagnosis.** Not actionable now, but it explains the shape of the negative better than any internal finding |

### 11. Giglio–Kelly–Pruitt financial-sector volatility — **TESTED AND FAILED**

| field | detail |
|---|---|
| source | NBER w20963 / *Journal of Financial Economics* 2016 |
| evidence | *"Financial sector equity volatility exhibits strong univariate predictive power for the quantiles of future real outcomes, while equity volatility in non-financial sectors appears to have little, if any, predictive power."* Predicts the **10th/20th percentiles**, not the mean |
| **status** | **Implemented and tested on SERAPH's corpus this session, pre-registered** (`scripts/screen_financial_sector_stress.py`, hash prefix `95acc3a2…`). **Result negative**: 0 of 5 features classify as BEFORE, all 5 below their own null, and `fin_minus_nonfin` runs **backwards** at **−1.027σ** pre-onset / **+1.191σ** after |
| limitations | Their target (macro tail quantiles, quarterly) differs materially from SERAPH's (market onset, 5–15 days), so this is not a failed replication of their result — it is a failure of the *transfer* to a harder target |
| recommendation | **CLOSED.** Do not retry on held data. The honest reading: the best-documented published leading-indicator family does not transfer to this target on this corpus |

### 12. ML early-warning literature generally — **CAUTION, and a useful mirror**

| field | detail |
|---|---|
| evidence | An arXiv survey of stock-market-turbulence early-warning systems notes that many models report strong **in-sample** accuracy but *"few test how much advance warning they give on held-out data"* |
| why it matters | **SERAPH's evaluation is more rigorous than this norm.** Its negative may be what much of this literature would report if it tested the same way. That is both a defence of the project's method and a warning against adopting published results uncritically |
| recommendation | **Use as a benchmark frame, not a source of methods.** Do not adopt a published EWS without replicating its out-of-sample design |

---

## Data alternatives — public before paid

Per the audit's own rule: **do not recommend purchasing data until you can say
what new independent information it provides and which episodes it unlocks.**

| source | status | unlocks | verdict |
|---|---|---|---|
| FBIL benchmarks | free, **VERIFIED daily and pre-15:30** | funding channel; 4 epochs cleanly, 6 only if the 2015-07-22 splice resolves | **first choice** |
| NSE participant-wise F&O OI | free, depth **UNKNOWN** | positioning channel | **second choice** |
| India VIX backfill | free; repo's `DATA-ACQUISITION.md:106` claims a Nov-2007 start **but independent search contradicts it** (launch 2008, real-time ~2009–2010, futures Feb 2014) | extends VIX from 4 to **5** epochs, not 6 — no plausible launch date populates FR28's 5-year window before 2008-09-15 | **third; also corrects a documentation error** |
| NSE paid EOD F&O | **price UNKNOWN**, pre-2015 depth **UNKNOWN** | option skew / term structure | **gated on one question to NSE** |
| FII/DII flows | NSE/MSEI publish daily, ~8:30–9:30 PM IST (**passes** the ≤2-day gate) | flow channel | **blocked on revision**: figures are *provisional and restated*; replay needs the as-first-published vintage. `flow_aggregates` holds **1 row**, so this is acquisition from scratch |
| Bank balance-sheet data | **UNKNOWN** | the capital-structure family the literature finds strongest (candidate 10) | **worth scoping** if the funding candidate also fails |

---

## What this catalogue concludes

**Of twelve candidates, two are worth building now, both free, and both are data
rather than models.** Three are rejected on measured grounds (`hmmlearn`,
gradient boosting, CoVaR/MES), one is tested-and-failed (Giglio–Kelly–Pruitt),
one is adopted purely as a missing *baseline* (`arch`), and the paid option-chain
route is gated behind a single unanswered question.

**No model or library in this catalogue would fix SERAPH.** The constraint is
information in the inputs, and only new data can change that. The most valuable
item here is arguably candidate 10 — not because it is actionable, but because it
explains the shape of the negative: **SERAPH's three pillars all belong to the
measure family the literature finds weakest for prediction, and it holds none of
the data from the family it finds strongest.**

---

## Sources

- [Giglio, Kelly & Pruitt — Systemic Risk and the Macroeconomy (NBER w20963)](https://www.nber.org/system/files/working_papers/w20963/w20963.pdf)
- [Giglio, Kelly & Pruitt — SSRN abstract page](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2158347)
- [Danielsson, James, Valenzuela — Model Risk of Systemic Risk Models](https://personal.lse.ac.uk/valenzum/MValenzuela_files/DJVZ12b.pdf)
- [Danielsson et al. — Model Risk of Risk Models (FMG DP)](https://www.fmg.ac.uk/sites/default/files/publications/dp-11.pdf)
- [Acharya, Berner, Philippon — Systemic Risk Measures: Taking Stock from 1927 to 2023](https://w4.stern.nyu.edu/sternfin/vacharya/public_html/pdfs/working-papers/ABP_systemic_risk_ARFE_preprint.pdf)
- [ESRB Working Paper 37 — SRISK: a conditional capital shortfall measure](https://www.esrb.europa.eu/pub/pdf/wp/esrbwp37.en.pdf)
- [Bollerslev, Tauchen & Zhou — Expected Stock Returns and Variance Risk Premia](https://public.econ.duke.edu/~boller/Published_Papers/rfs_09.pdf)
- [Federal Reserve FEDS — Downside Variance Risk Premium](https://www.federalreserve.gov/econresdata/feds/2015/files/2015020pap.pdf)
- [An Integrated Early Warning System for Stock Market Turbulence (arXiv)](https://arxiv.org/pdf/1911.12596)
- [Early warning signals for stock market crashes — EPJ Data Science 2024](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-024-00457-2)
- [`arch` on PyPI](https://pypi.org/project/arch/)
- [FBIL — benchmarks and historical data](https://www.fbil.org.in/)
- [NSE paid EOD / historical data subscription](https://www.nseindia.com/static/market-data/eod-historical-data-subscription)
- [NSE all reports — derivatives](https://www.nseindia.com/all-reports-derivatives)
