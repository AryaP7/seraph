# AMENDMENT-03 — Pillar 1: what NSE 5-minute data can and cannot support

**Status:** Measured 2026-08-23 on the complete intraday corpus (94 equity symbols, 18.27M
five-minute bars, 243,597 symbol-days, 21,180 negative jump events).
**Decision required before C5 is finalised.**
**Applies to:** SPEC FR10, FR11, FR13, FR14, FR15, O2, NFR6; ARCHITECTURE R2, CT-3; ROADMAP Phase 5.

> **Revision history.** This document has been rewritten twice as measurements arrived, and both
> earlier conclusions were wrong. Draft 1 recommended pooling *by sector* and reported that only
> 6 of 25 `S_t` states were populated — the occupancy figure was an artefact of a `|log return|`
> spread proxy, and sector counts turned out far too small. Draft 2 recommended a market-wide
> pooled continuous-time kernel with a resolution-based `β` bound. **That is also wrong, and §2
> below shows why.** The record is kept because the sequence is itself evidence: each conclusion
> looked defensible until the next measurement.

---

## 1. Confirmed: per-symbol, one-day-window estimation is impossible

Measured negative-jump density is **0.0869 per symbol-day** (21,180 events / 243,597 symbol-days) —
about one event per symbol per fortnight. FR10's per-symbol, one-trading-day window is empty on the
overwhelming majority of days, so the likelihood is undefined rather than merely imprecise.

Across the full Lee–Mykland parameter grid (`K ∈ {156, 78, 40}` × `α ∈ {0.01, 0.05, 0.10}`) density
moves only between 0.079 and 0.147 — a **1.9× span against a ~50× shortfall**. Tuning `K` or `α` is
not a mitigation and must not be presented as one; loosening `α` would raise the false-positive rate
of the jump test itself. `K = 156`, `α = 0.01` (Lee–Mykland's published defaults for 5-minute data)
are retained unchanged.

`S_t` is **not** the problem. Re-measured with the real Abdi–Ranaldo spread, **all 25 states are
populated and 20 carry ≥100 events**; on the 3×3 grid all 9 states carry ≥100.

## 2. The continuous-time Hawkes likelihood is unbounded on this data — the bound was doing all the work

Pooling across symbols produces massive timestamp ties, because the data is 5-minute *binned*, not
continuously observed:

| Tie statistic | Value |
|---|---|
| Distinct event timestamps | 7,372 |
| Event bars containing >1 simultaneous jump | 2,248 (**30.5%**) |
| Events landing in a tied bar | 16,056 (**75.8% of all events**) |
| Maximum simultaneous jumps in one bar | **89** |

With exact ties the exponential-kernel Hawkes likelihood is unbounded as `β → ∞`. Draft 2 proposed
bounding `β` at the observation resolution (288/day). **The sensitivity analysis shows that bound
determines the answer:**

| `β_max` | `n̂` | `β̂` | At the bound? | NLL |
|---|---|---|---|---|
| 72 | 0.8342 | 72.00 | **yes** | −2092.31 |
| 144 | 0.8172 | 144.00 | **yes** | −2358.76 |
| 288 | 0.8022 | 288.00 | **yes** | −2622.74 |
| 576 | 0.7917 | 576.00 | **yes** | −2879.55 |
| 2880 | 0.7516 | 2880.00 | **yes** | −3446.29 |

`β̂` pins to the ceiling at **every** value tested, the likelihood improves monotonically without
limit, and `n̂` drifts with the arbitrary choice. There is no interior optimum. A reported branching
ratio would be a function of where we set the bound, not of the market.

**Conclusion: the continuous-time formulation is misspecified for 5-minute binned data, not merely
in need of regularisation.** Options 1 and 3 from the brief are rejected — and de-duplication is
rejected additionally on the grounds below.

## 3. The ties are the signal, so they must not be aggregated away

89 symbols jumping in the same five-minute bar is not a nuisance to be de-duplicated; it is the
market-wide shock the pillar exists to detect. Counts confirm the clustering is extreme:

- mean 0.0991 events/bar, variance 1.836 → **variance/mean = 18.53** (Poisson would be 1.0)
- maximum 89 events in a single bar

Any aggregation that collapses simultaneous events would destroy precisely the systemic signal.

## 4. Correction: the n = 0.995 figure was a session-handling artefact

An earlier draft of this section reported a discrete-time fit of `a = 0.950`,
`n = 0.995` and treated it as the model "absorbing overdispersion". **That number was wrong**, and
the cause is worth recording because it is a trap anyone repeating this work will hit.

The intensity recursion needs a reset at each trading-session boundary — an overnight gap is not an
ordinary zero-count transition. The draft reset `λ` to the process's *unconditional mean*
`μ/(1−a−b)`. As `a+b → 1` that quantity explodes, so the optimiser could manufacture a huge
session-opening intensity and harvest likelihood from genuinely volatile opening bars. Resetting
instead to the **baseline immigrant rate `μ`** removes the exploit:

| Session reset | `μ` | `a` | `b` | Session-start `λ` | NLL |
|---|---|---|---|---|---|
| unconditional mean (wrong) | 0.0237 | 0.9347 | 0.0588 | **3.6234** | 10829.89 |
| baseline `μ` (correct) | 0.0798 | **0.1484** | **0.0000** | 0.0798 | 17321.85 |

Data mean is 0.0860, so the "wrong" convention was starting each session at **42× the mean**. Its
better raw likelihood is the tell, not the vindication: it was fitting the opening-bar effect
through a mis-specified reset instead of modelling it.

**Why `b` is exactly 0.0000 — the question was worth asking.** Profiling the likelihood with `b`
fixed shows a genuine boundary optimum, not a flat likelihood or an implementation fault:

| `b` fixed at | 0.00 | 0.05 | 0.20 | 0.50 | 0.80 | 0.95 |
|---|---|---|---|---|---|---|
| NLL | **17321.85** | 17347.75 | 17530.68 | 18405.08 | 20805.89 | 24574.43 |

NLL increases monotonically away from zero. So INGARCH(1,1) collapses to **INAR(1)**:
`λ_t = μ_t + a·N_{t−1}`. There is no persistence in the conditional intensity beyond the immediate
lag — which is a real finding about the process, not a numerical accident.

## 5. Model selection: six families, three time-based folds, full corpus

Out-of-sample negative log-likelihood per bar, with session resets to `μ` and an explicit
time-of-day (ToD) profile. Folds are sequential and disjoint, so each is a genuine forward test.

| Model | fold 1 | fold 2 | fold 3 | mean | sd |
|---|---|---|---|---|---|
| **NB + INAR(1) + ToD** | 0.13937 | 0.13429 | 0.13199 | **0.13522** | 0.00308 |
| Negative binomial (static) | 0.18792 | 0.18554 | 0.18406 | 0.18584 | 0.00159 |
| Beta-binomial (explicit common shock) | 0.19023 | 0.18646 | 0.18556 | 0.18741 | 0.00202 |
| INAR(1) + ToD | 0.22221 | 0.17506 | 0.20615 | 0.20114 | 0.01957 |
| Poisson + ToD | 0.22723 | 0.17671 | 0.20626 | 0.20340 | 0.02073 |
| INAR(1) | 0.50935 | 0.42132 | 0.55847 | 0.49638 | 0.05674 |
| Poisson (constant rate) | 0.51399 | 0.42273 | 0.55959 | 0.49877 | 0.05690 |

**Decomposing where the predictive power actually comes from:**

- **Overdispersion / contemporaneous common shocks — the dominant term.** Poisson → negative
  binomial improves OOS NLL by **63%** (0.4988 → 0.1858) with *no dynamics whatsoever*.
- **Intraday seasonality — comparably large.** Poisson → Poisson+ToD improves by **59%**. This is
  the lag-75 autocorrelation of §3 showing up as what it really is: time-of-day structure, not
  contagion. Any Pillar 1 statistic that skips this adjustment will re-detect the same hour of every
  trading day as "stress".
- **Sequential self-excitation — small, but real and identifiable.** Adding the lag-1 term on top
  of ToD gives only ~1% (0.2034 → 0.2011), with `a ≈ 0.050`. Within the full model `a ≈ 0.074`.
  This is an *interior, stable* estimate — unlike §2's bound-determined continuous-time figure.
- **All three together win decisively**, and the winner is also the most stable across folds in
  relative terms (0.139 / 0.134 / 0.132, monotonically improving).

The explicit beta-binomial common-shock model gives a directly interpretable quantity: the
**intra-bar jump correlation `ρ = 0.0552`** (against `ρ = 0` for independent symbols, with a
per-symbol jump probability of 0.00113). That is the cleanest single statement of the mechanism:
symbols do not jump independently, and the dependence is *within* the bar.

## 5a. Decision

**Pillar 1 is estimated with a negative-binomial INAR(1) model carrying a time-of-day profile:**

```
N_t | F_{t-1} ~ NegBinomial(mean = λ_t, dispersion k),
λ_t = μ · ToD(t) + a · N_{t−1},   reset to μ · ToD(t) at each session open
```

selected on out-of-sample likelihood across three sequential folds, not on convergence.

- **The branching ratio survives, at its true magnitude.** With `b = 0`, `n = a/(1−b) = a ≈ 0.074`.
  FR10/FR11 remain meaningful — `n < 1` is the stationarity condition — but the market is nowhere
  near critical, and the earlier 0.80–0.995 figures were artefacts (§2, §4) that must not be quoted.
- **`MTS_t` should lead with the contemporaneous term**, since that is where the predictive power
  is: report the overdispersion / `ρ` as the primary systemic signal and `a` as a secondary
  endogeneity term. This matches SPEC O2's *intent* — detecting self-reinforcing sell-side
  pressure — while being honest that at 5-minute resolution the dominant observable is
  simultaneity, not cascade.
- **Ties are retained and are the signal**, per §3.
- **What cannot be claimed:** that NSE has no self-exciting contagion. Only that at 5-minute
  resolution sequential excitation is weak (`a ≈ 0.07`) relative to contemporaneous clustering.
  Sub-bar cascades are invisible here — a direct consequence of tick data being unobtainable.

## 5b. Final comparison under the pre-registered rule

Rule committed in `docs/PILLAR1-SELECTION-RULE.md` **before** these numbers existed. Four
chronological disjoint folds, corrected session reset, full corpus.

| Model | mean OOS NLL | vs baseline | beats base in ALL folds | PIT mean | PIT sd | param CV | Spearman (fwd) | AUC (fwd) |
|---|---|---|---|---|---|---|---|---|
| Poisson | 0.51060 | — | — | 0.472 | 0.273 | 0.03 | 0.000 | 0.500 |
| INAR(1) | 0.50825 | 0.5% | **no** | 0.472 | 0.274 | 0.07 | 0.041 | 0.513 |
| Poisson + ToD | 0.21583 | 57.7% | yes | 0.492 | 0.286 | 0.13 | **0.332** | **0.747** |
| Negative binomial | 0.19429 | 61.9% | yes | 0.497 | 0.286 | 0.12 | **0.000** | **0.500** |
| NB + INAR + ToD | 0.14376 | 71.8% | yes | 0.497 | 0.285 | 0.02 | 0.334 | 0.747 |
| **Common shock (NB + lagged breadth + ToD)** | **0.14374** | **71.8%** | yes | 0.497 | 0.285 | 0.03 | 0.334 | 0.747 |

PIT targets for a calibrated model are mean 0.500 / sd 0.289. Forward metrics use information
through bar `t` to predict bars `t+1 … t+15`.

**Gate outcomes.** INAR(1) alone **fails G1 and G2** — 0.5% improvement, and it does not beat the
baseline in every fold. All other candidates pass G1–G4. Under **G5 (parsimony)** the top two are
separated by 0.014%, which is not a difference: with the active-symbol count nearly constant
(median 88/bar), lagged *breadth* and lagged *count* are the same regressor up to scale. They are
one model, not two. The breadth parameterisation is preferred only because it stays comparable as
the universe size changes over the corpus.

### The finding that matters more than the ranking

**Overdispersion does not predict anything.** The static negative binomial improves NLL by 61.9%
and scores **Spearman 0.000, AUC 0.500** on forward activity — literally no forward information. It
fits the *marginal distribution* of jump counts well and says nothing about *when* jumps arrive.
This is precisely the distinction the secondary metric exists to catch, and it means the
contemporaneous clustering of §3, on its own, is a description of the market rather than a risk
signal.

**Almost all forward predictability is intraday seasonality.** Poisson+ToD alone reaches Spearman
0.332 / AUC 0.747; adding overdispersion *and* lag-1 moves it to 0.334 / 0.747. The dynamic
components buy **essentially nothing** in forward terms — they buy distributional accuracy (NLL),
not timing.

**Limitation of this metric, stated plainly.** The forward target is total jumps in the next hour,
and at that horizon the intraday rhythm dominates. An AUC of 0.747 therefore largely reflects
"jumps cluster near the open and close", which is calendar knowledge, not risk detection. The
metric that would actually discriminate is prediction of activity **in excess of the seasonal
norm** — de-seasonalised. Until that is run, **no claim should be made that Pillar 1 predicts
systemic risk.** What is established is that it predicts jump *activity*, mostly via time of day.

## 5c. The decisive test: nothing predicts EXCESS risk intraday

Pre-registered target (`docs/PILLAR1-SELECTION-RULE.md`): realised jump count in bars
`t+1..t+H` **minus the count expected for that time-of-day position**, with the seasonal baseline
fitted on training bars only inside each chronological fold. Positive class = top decile of excess,
so **PR-AUC 0.10 is the no-skill line** and ROC 0.50 is no skill.

| Horizon | ToD-only (null) | lagged breadth | common-shock sync | NB+INAR+ToD | discrete Hawkes+ToD |
|---|---|---|---|---|---|
| 15m | 0.082 (0.82×) | 0.110 (1.10×) | 0.111 (1.11×) | 0.084 | 0.085 |
| 30m | 0.084 | 0.107 | 0.107 | 0.086 | 0.088 |
| **1h** | 0.085 | **0.122 (1.22×)** | 0.122 | 0.087 | 0.089 |
| 2h | 0.084 | 0.109 | 0.109 | 0.086 | 0.089 |
| session | 0.329 (3.29×) | 0.108 | 0.108 | 0.308 | 0.270 |

**Intraday horizons: no meaningful skill.** The best result anywhere is lagged breadth at
**1.22× lift** (PR-AUC 0.122 vs a 0.10 base rate) at one hour, with **ROC ≈ 0.485 — below 0.5** —
and *negative* Spearman. That is not a risk signal.

**The de-seasonalisation worked, and the null confirms it.** ToD-only scores *below* the base rate
(0.82×, ROC 0.37) at intraday horizons: once the seasonal mean is removed, the seasonal predictor
is anti-correlated with what remains. That is the expected behaviour of a correct residual and is
evidence the target is clean.

**The session-horizon numbers are an artefact, not a result.** Excess variance scales with how many
bars remain in the session, so top-decile excess concentrates early in the day and any predictor
encoding session position trivially finds it. ToD-only "wins" there (3.29×, ROC 0.86) precisely
because it is measuring time-of-day, which is what the target was supposed to remove. **This row
must not be quoted as predictive performance.**

**Contrast with §5b, and this is the whole point.** The same models delivered ROC 0.747 on *raw*
forward activity. Against *excess* activity they collapse to ~0.5. The earlier number was
predicting the intraday rhythm, exactly as suspected.

## 5d. Discrete-time Hawkes is identifiable — and is descriptive, not predictive

Unlike the continuous-time version (§2), the discrete-time formulation
`λ_t = μ·ToD(t) + α·Σ_k φ^(k−1)·N_(t−k)` is **well-identified at the native resolution**:

| Fold | α | φ | branching `n = α/(1−φ)` |
|---|---|---|---|
| 1 | 0.0556 | 0.5005 | 0.1113 |
| 2 | 0.0558 | 0.5005 | 0.1117 |
| 3 | 0.0541 | 0.4679 | 0.1018 |

`φ ≈ 0.50` is a genuine **interior** estimate — a geometric kernel with a roughly one-bar half-life —
and `n ≈ 0.11` is stable across folds (CV ≈ 5%). This is a real, defensible Hawkes result at
5-minute resolution, and it is the correct home for Hawkes in SERAPH: **temporal excitation exists
and is measurable, it is simply small and carries no incremental forward information about excess
risk.**

**Conclusion, stated in the pre-registered form.** No candidate clears the secondary gate at any
intraday horizon. Per the rule committed in advance, the honest report is: **at 5-minute resolution
these data support a well-calibrated description of jump activity, and do not support a
demonstrated forward signal for abnormal jump risk.** Hawkes is retained as an identifiable
contagion *diagnostic* (`n ≈ 0.11`, `φ ≈ 0.50`), not as a predictive component.

## 6. Validation criteria to apply before any Pillar 1 result is reported

None of the following has been established yet, and no accuracy claim should be made until they are:

1. **Out-of-sample predictive value** — does the synchronisation statistic lead realised drawdowns
   on held-out epochs, evaluated under D5's leave-one-epoch-out policy?
2. **Calibration** — do predicted intensities match realised counts across the distribution, not
   just on average (PIT / reliability check)?
3. **Stability** — across symbols, sectors, sub-periods and regimes; parameters must not swing with
   the estimation window.
4. **Sensitivity** — conclusions must survive reasonable changes to `K`, `α`, window length, state
   count and the seasonality adjustment.
5. **Identifiability** — a boundary solution or a bound-determined estimate is a failure, as in §2
   and §4; interior optima with finite standard errors are required.
6. **False positive / negative behaviour** — measured against the labelled epochs, at the
   asymmetric loss FR30 specifies.
7. **Baseline comparison** — must beat both the constant-rate Poisson and the static
   negative-binomial out of sample, not merely converge.
8. **Robustness to market-wide events** — the statistic should respond to the 89-jump bars rather
   than be destabilised by them.

**Convergence, a high likelihood and a green test suite are not evidence of accuracy.** §4 is the
proof: the INAR model converges, wins on likelihood, and still yields an uninterpretable parameter.

## 7. Consequential edits

| Location | Edit |
|---|---|
| **SPEC FR10** | Per-symbol one-day-window MLE is infeasible; estimation moves to a pooled discrete-time count model over a rolling multi-day window |
| **SPEC FR11** | `n(S_t) < 1` becomes the stationarity condition `a + b < 1` of the count model; it is no longer interpretable as a Hawkes branching ratio |
| **SPEC FR13** | `MTS_t` redefined as a contemporaneous synchronisation statistic; the asymmetry gate is re-specified as a significance test (§5e) |
| **SPEC FR14/FR15** | Unchanged in deliverable; sourced from per-sector baselines and a full-sample network |
| **SPEC O2** | "branching ratio as a real-time indicator of market endogeneity" is **not achievable at this resolution** and must be restated |
| **Report §5.1** | State the resolution constraint and what it forecloses |
| **Report §7.1** | Add the density, tie, dispersion and autocorrelation measurements |
| **ARCHITECTURE R2** | R2 is realised; record the resolution as this amendment |

## 8. Reproducing

```bash
python -m pytest tests/contract/test_ct3_jump_sufficiency.py -q -s
python scripts/fit_hawkes.py
```

The tie, dispersion, autocorrelation and model-comparison figures come from the diagnostics in
`scripts/diagnose_jump_process.py`, run over every equity symbol in the Hawkes universe
(selected via `build_symbol_list`, never by scanning `intraday_bars`, which still holds ETF rows
from before the equity filter landed).
