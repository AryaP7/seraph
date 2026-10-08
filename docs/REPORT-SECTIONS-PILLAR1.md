# Report sections for Pillar 1 — drop-in prose

**Purpose.** Ready-to-paste replacement text for report §5.1 (with the new §5.1.2 that SPEC §11
requires), the Pillar-1 portion of §7.1, and the §9 expected-outcome entries that must change.
Every figure here is measured; nothing is a design target. Sources: `AMENDMENT-03`,
`PILLAR1-SELECTION-RULE.md`, and the four diagnostic scripts named in §7.1 below.

**House rules observed throughout.** SPEC §7 item 12 forbids any claim about queue depth or
quote-level behaviour — spread and imbalance are *estimated*, never observed. Per SPEC §11 the
Pillar-1 framing is "return-jump contagion", not "order-flow toxicity". And every statement below
is marked as demonstrated, descriptive, assumed, or limitation, because the credibility of the
whole instrument rests on not blurring those four.

---

## §5.1 — Pillar 1: Return-Jump Contagion

Pillar 1 measures the degree to which downside price jumps in the Indian equity market excite
further downside jumps — the *endogeneity* of sell-side pressure. Where the market's reaction to a
shock is largely exogenous, an initial jump is absorbed and the arrival rate of subsequent jumps
returns quickly to its baseline. Where the reaction is endogenous, each jump raises the conditional
intensity of the next, and the market becomes capable of amplifying a small disturbance into a
cascade without further external news. The branching ratio of a self-exciting point process
quantifies exactly this: the expected number of directly-triggered offspring per event.

The pillar is estimated on a **market-wide pooled stream of negative jump events** drawn from the
intraday universe, using a **discrete-time Hawkes process at the native five-minute bar
resolution**. Writing `N_t` for the number of negative jump events across the pooled universe in
bar `t`, the conditional intensity is

> λ_t = μ · ToD(t) + α · Σ_{k≥1} φ^(k−1) · N_(t−k),  N_t | F_(t−1) ~ NegBinomial(λ_t, κ)

with the excitation term reset to the baseline at each session open, since an overnight gap is not
an ordinary transition between consecutive bars. Here `μ` is the baseline arrival rate, `ToD(t)` a
multiplicative intraday-seasonality profile, `α` the excitation magnitude, `φ` the geometric decay
of the excitation kernel across bars, and `κ` a negative-binomial dispersion parameter that
accommodates the pronounced clustering of jumps within a single bar. The branching ratio is

> n = α / (1 − φ)

and stationarity — the requirement of FR11 that the process not be explosive — is the condition
`n < 1`, enforced during estimation rather than imposed by clipping afterwards.

Three properties of this specification deserve emphasis. First, it operates at the resolution at
which the data is actually observed: bars are modelled as counts, so multiple symbols jumping in
the same five-minute interval are represented as the observation they are, rather than as an
artefact requiring correction. Second, it invents no sub-bar ordering; the model never assumes
knowledge of which of two simultaneous jumps occurred first, because the data does not contain
that information. Third, the excitation structure of the original continuous-time specification is
preserved in discrete form — the geometric kernel `α φ^(k−1)` is the exact bar-level analogue of
the exponential kernel `α e^(−βτ)` — so the economic interpretation of the branching ratio carries
over unchanged. §5.1.2 explains why the continuous-time form itself could not be used.

### §5.1.1 — Sector-Level Micro-Flag Granularity

*(Unchanged in intent.)* Sector-level attribution is retained, but is derived from **per-sector
baseline intensities** rather than from sector-specific excitation kernels. A sector's micro-flag
is raised when its realised jump intensity stands significantly above its own baseline. This
change is forced by event counts: the least-represented tariff-exposed sectors yield fewer than 150
negative jump events across the entire corpus, which cannot identify a kernel of their own, whereas
a baseline intensity is estimable from that many observations. The deliverable of FR14 is therefore
preserved while the statistic behind it is one the data can support.

### §5.1.2 — Observation-Channel Constraint and Jump-Event Reformulation

*(New section, required by SPEC §11.)*

The original design specified a sell-side conditional multivariate Hawkes process estimated on
**order-flow events**. Tick-level order-flow data for the NSE is not obtainable within the budget of
this project, and the observation channel was therefore changed: Pillar 1 models **negative
price-jump events extracted from five-minute intraday bars** by the Lee–Mykland bipower-variation
test, with the test's published parameters for this frequency (`K = 156`, `α = 0.01`). This
substitution follows established practice — Nyawa, Ceccarelli and Tiozzo Pezzoli estimate
mutually-exciting jump contagion on five-minute equity data with no order book, and Aït-Sahalia,
Cacho-Díaz and Laeven provide the theoretical basis for treating jumps as the contagion channel.

The change of observation channel has a second, less obvious consequence, which is the subject of
this section. Because events are recorded at bar resolution rather than as a continuous point
process, pooling across symbols produces **exact timestamp ties**: 75.8% of negative jump events in
the pooled stream share their bar with at least one other event, and as many as 89 symbols jump
within a single five-minute interval. For a continuous-time exponential-kernel Hawkes process, ties
are a measure-zero event, and their systematic presence renders the likelihood **unbounded in the
decay parameter**. Estimation was attempted under bounds on `β` ranging from 72 to 2,880 per day;
the estimate pinned to the imposed ceiling at every value, the likelihood improved monotonically as
the ceiling was raised, and the recovered branching ratio drifted from 0.834 to 0.752 as a direct
function of the bound. The parameter was therefore not being identified from the data at all, and
the continuous-time specification was rejected as misspecified for binned observations.

It is important to state what this does *not* mean. The ties are not a data defect and were not
removed: many symbols jumping simultaneously is precisely the market-wide shock the instrument
exists to detect, and de-duplicating those events to restore continuous-time identifiability would
have discarded the signal in order to preserve the model. Nor does the finding imply that self-
exciting contagion is absent from the NSE; it implies only that its continuous-time limit cannot be
recovered from five-minute data. Sub-bar cascades, if present, are invisible at this resolution —
a direct consequence of the order-flow constraint described above, and a limitation of the
observation channel rather than of the method.

---

## §7.1 — Stage 1: Data Acquisition and Pre-processing *(Pillar 1 subsection)*

*(This text follows the universe-construction and burn-in paragraphs specified in AMENDMENT-02 §4.)*

**Intraday corpus.** Five-minute OHLCV bars were obtained through the Zerodha Kite Connect
historical endpoint for a 94-symbol equity universe comprising the most liquid NSE constituents by
six-month median traded value together with hand-selected representatives of the five
tariff-exposed sectors. A direct probe of the endpoint established that intraday history begins on
**2 February 2015** — identically for large-cap, mid-cap and small-cap names — which fixes the start
of Pillar 1's coverage and confirms the coverage matrix of §4 as an observed rather than assumed
boundary. The completed corpus comprises **18,781,302 bars spanning 2 February 2015 to 21 August
2026**. Exchange-traded funds were excluded by ISIN prefix, since index ETFs are near-exact linear
combinations of other universe members and their inclusion would inject mechanical, non-economic
correlation into the analysis.

**Event extraction and density.** Applying the Lee–Mykland test yields **21,180 negative and 28,603
positive jump events over 243,597 symbol-days**, a negative-jump density of **0.087 per symbol-day**
— approximately one event per symbol per fortnight. This density is the central empirical constraint
on Pillar 1. A rolling one-trading-day estimation window on a single symbol is empty on the large
majority of days, so the per-symbol specification originally proposed cannot be estimated at all;
the likelihood is undefined rather than merely imprecise. A sweep over the jump test's own
parameters (`K ∈ {156, 78, 40}`, `α ∈ {0.01, 0.05, 0.10}`) moves the density by a factor of at most
1.9 against a shortfall of roughly fiftyfold, so no parameter choice resolves it — and loosening
the significance level would in any case raise the false-positive rate of the very test on which the
pillar depends. Estimation is therefore pooled across the universe, which is the only adjustment
that scales the event count by a large factor rather than a small one.

**Model selection.** Because the continuous-time formulation proved unidentifiable (§5.1.2), six
candidate specifications were compared on out-of-sample predictive likelihood across chronological,
disjoint forward folds, under a selection rule committed in writing before the results were
computed. The rule set out the primary metric, five eligibility gates — materiality, consistency
across folds, parameter identifiability, calibration, and parsimony — and a secondary forward-
prediction criterion, together with an explicit undertaking to report that no candidate beat the
baseline if that proved to be the case. The discrete-time Hawkes specification of §5.1, combined
with negative-binomial dispersion and an intraday-seasonality profile, was selected: it improved
out-of-sample negative log-likelihood by **71.8%** over a constant-rate Poisson baseline, beat that
baseline in every fold, and was the best calibrated of the candidates, with a randomised
probability-integral transform of mean 0.497 and standard deviation 0.285 against uniform targets
of 0.500 and 0.289.

**Parameter identification.** Fitted on real data across three chronological folds, the model
returns `α = 0.0557`, `φ = 0.4837` and a branching ratio of **`n = 0.108`**, with coefficients of
variation of 2.0%, 2.5% and 4.1% respectively. The estimates are interior — none sits at a
constraint boundary — and the stationarity condition `n < 1` holds on every fold with a wide margin.
The decay parameter corresponds to an excitation half-life of approximately one bar. These figures
should be read against the values produced by the rejected specifications, which are recorded in
AMENDMENT-03 and are **not** reportable: the bounded continuous-time fits returned 0.75–0.83
depending on the bound imposed, and an early discrete fit returned 0.995 as an artefact of resetting
the intensity to the process's unconditional mean at each session open rather than to its baseline
rate. The market described by the validated estimate is measurably self-exciting but far from
critical.

**Predictive evaluation, and its outcome.** A model that fits well is not thereby a risk instrument,
and the two were tested separately. Using only information available at bar `t`, each candidate was
asked to predict jump activity in the following 15 minutes, 30 minutes, one hour, two hours and
remainder of session. Against *raw* future activity the selected model achieved an ROC-AUC of
approximately 0.75. However, a model that merely knows the market is busier near the open and close
has not detected risk, and so the target was reconstructed as **excess activity relative to the
expected level for that time of day**, with the seasonal baseline estimated from training data only
within each fold. Against this de-seasonalised target, performance falls to approximately the
no-skill line at every intraday horizon: the best result obtained anywhere is a precision-recall
area of 0.122 against a base rate of 0.10, with ROC-AUC of 0.485. **No candidate model demonstrated
a forward signal for abnormal jump activity at five-minute resolution.** The apparent predictive
performance against the raw target was intraday seasonality, as the de-seasonalised test was
designed to determine.

This result is reported as measured. It establishes a limitation of what can be inferred from
five-minute data, not a deficiency of the estimator: the selected model remains a well-identified,
stable and calibrated description of the contagion state, and it is in that capacity that it
contributes to the composite score.

**Reproducibility.** Every figure in this section regenerates from
`scripts/diagnose_jump_process.py`, `scripts/diagnose_inar_session_handling.py`,
`scripts/compare_pillar1_models.py`, `scripts/test_excess_risk_prediction.py` and
`scripts/diagnose_fr13_gate.py`, against the stored corpus.

---

## §5.4 / §5.5 — What Pillar 1 contributes to the composite score

Pillar 1 emits the Market Toxicity Score `MTS_t = n/(1 − n)`, a monotone transform of the branching
ratio that expands as the process approaches criticality. It is passed to the state-space
reconciliation layer as a **contagion / risk-state observation**, on the same footing as the
spectral and regime signals, and is not treated as an alarm in its own right.

The score carries a sell-side condition. Because the pillar is concerned specifically with downside
pressure, `MTS_t` is reported only where the downside share of jump activity is **significantly
elevated relative to the market's own baseline**, assessed by a one-sided exact binomial test at the
5% level. The baseline is a measured quantity: across the corpus, **42.54%** of jump events are
negative, a share that is stable across symbols (mean 0.424, standard deviation 0.055) and across
sectors (0.402 to 0.450). This differs from a symmetric mix at `z = −33.3`, so the NSE jump stream
at this frequency is genuinely skewed toward upside events, and a criterion demanding that negative
jumps simply outnumber positive ones would never be satisfied. Testing against the market's own
mix, rather than against symmetry, opens the condition on 28.3% of windows — a criterion that
discriminates rather than one that always or never fires. Where the condition is not met, the
reading is a *normal-mix* state and is labelled as such; the branching ratio continues to be
reported, and a suppressed score is at no point conflated with an absence of contagion.

---

## §9 — Expected Outcome: entries that must change

| Original expectation | Status after measurement |
|---|---|
| Branching ratio as a real-time indicator of market endogeneity | **Demonstrated as a measurement.** `n = 0.108`, stable at 2–4% CV. **Not demonstrated as a forecast** — the de-seasonalised test found no forward skill. |
| Hawkes criticality crossing 3–7 trading days ahead of a sell-off (NFR14) | **Not demonstrated.** Report as untested rather than as an achieved lead time. |
| `MTS_t` emitted at bar frequency | **Achieved**, with the sell-side condition of §5.4 applied. |
| Per-symbol branching ratios | **Withdrawn.** Not identifiable at 0.087 events per symbol-day; must not be reported at any granularity below the pooled universe. |
| Directed contagion network (FR15) | **Retained, scoped to full-sample estimation.** A six-group cross-excitation matrix is a structural characterisation, not a rolling signal. |

---

## Statement of scope, for the viva

Four categories, kept distinct deliberately.

**Demonstrated.** Discrete-time Hawkes contagion is identifiable and stable on NSE five-minute data
(`n = 0.108`, CV 2–4.1%, interior, stationary on every fold). The selected model improves
out-of-sample likelihood by 71.8% over baseline and is well calibrated. The intraday jump stream is
strongly overdispersed (variance/mean 18.5) and skewed toward upside events (42.54% negative).

**Descriptive, not predictive.** Negative-binomial dispersion characterises the count distribution
and carries no forward information whatsoever (rank correlation 0.000). Cross-sectional
synchronisation describes the current bar. Time-of-day structure explains most apparent forward
predictability of raw activity.

**Assumed.** That Lee–Mykland jump identification at `K = 156`, `α = 0.01` is appropriate for this
market; that pooling across the universe is preferable to per-symbol estimation, which the density
forces; that the negative-binomial emission adequately captures within-bar clustering.

**Limitations.** No forward signal for abnormal jump risk is demonstrated at five-minute resolution.
`MTS_t` has not itself been calibration-tested — calibration was established for the count models
beneath it. Sub-bar contagion is unobservable given the data available. The sector micro-flag
threshold and the excitation state count remain uncalibrated constants pending the FR34 sensitivity
sweep.
