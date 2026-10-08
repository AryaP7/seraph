# AMENDMENT-05 — Pillar 3: causal mode, and the TVTP optimiser defect

**Status:** In progress, 2026-08-24. The implementation fix is made and unit-validated.
**Real-corpus causal validation is BLOCKED — Docker/TimescaleDB unavailable.** No causal
NSE result is claimed, inferred or estimated in this document.

**Applies to:** SPEC FR20, FR21, FR23; C7; the causal path into C8/C9.

**Verdict: B — the implementation defect is fixed and verified on synthetic data;
real-data causal validation has not been run.** Hamilton is **not** cleared for
production CSRS.

---

## 1. Three leakage paths in the historical E8 series

The 5,365-day `hamilton_output` series is **not causal**. It leaks the future three
separate ways:

1. **Smoother.** `ξ_t` was read from `smoothed_marginal_probabilities` — `P(S_t | y_1..y_T)`.
   The Kim smoother runs backward over the whole sample.
2. **Parameters.** One fit over all 5,365 observations, so parameters at `t` were
   estimated using data after `t`.
3. **Covariate standardisation.** `scripts/fit_hamilton.py` builds the FR21 driver as
   `(rv − rv.mean()) / rv.std()` over the **entire corpus**, so the z-score at `t`
   embeds moments from after `t`. Independent of (1) and (2), and easily missed.

**Consequence, binding:** occupancy **43.0/25.2/31.8**, **NFR16 4/6** and
**NFR17 2.02σ** are **SMOOTHED IN-SAMPLE** results. They describe in-sample fit.
They are not causal, must be labelled as such wherever they appear, and must not
be used as evidence that a causal Hamilton works.

---

## 2. The optimiser defect

### 2.1 statsmodels does not estimate TVTP transitions by EM

`MarkovSwitching._em_iteration` contains:

```python
# The EM with TVTP is not yet supported, just return the previous
# iteration parameters
if self.tvtp:
    params1[self.parameters['regime_transition']] = (
        params0[self.parameters['regime_transition']])
```

Verified empirically, not merely read: one EM iteration moves the transition block by
**exactly `0.000e+00`** while emission means move `2.202e-03`. So the entire transition
block comes from `start_params` — all zeros under TVTP — plus a single numerical pass.

### 2.2 The likelihood is far flatter toward the absorbing boundary

Profile of the from-stressed transition control, all else fixed (Δllf):

| Fold | −6 | −3 | −1 | **0** | +1 | +3 | +6 |
|---|---|---|---|---|---|---|---|
| 1 | −10.0 | −4.1 | −0.7 | **0** | −1.4 | −31.0 | −503.2 |
| 2 | −50.0 | −20.4 | −3.7 | **0** | −7.0 | −139.3 | −1229.0 |
| 3 | −58.0 | −24.3 | −4.4 | **0** | −8.4 | −172.7 | −1750.5 |

There is a clear interior optimum — the parameter is identified — but the surface is
**25–50× flatter toward absorption than away from it**. On fold 1, moving
`P(tranquil|stressed)` from 4.4e-4 to 1.1e-6 (400× smaller) costs **10 llf out of
18,091 — 0.055%**. On a short sample that is effectively free, which is how a
1,260-observation window reached `1.8e-9`.

### 2.3 The impossible likelihood ratio

Fold 3 (train 2005-01-03 → 2022-04-25): **LR = −414.55** against the intercept-only
model. The intercept-only TVTP is *nested* inside the full model — set every slope to
zero — so the full model can never legitimately score lower. It scored **207 llf
below** its own restriction. That is arithmetically impossible at a true maximum and
proves the fold-3 fit was **not at its own optimum**.

Where the optimiser succeeded, the covariate is significant: LR 14.96 (p = 0.021) on
fold 1, 37.69 (p = 1.3e-6) on fold 2.

### 2.4 What was ruled out

| Hypothesis | Test | Result |
|---|---|---|
| `transform`/`untransform` not inverse, mangling `start_params` | round-trip on synthetic | **exact** — max err 8.7e-19, transition block 0.000e+00 |
| Optimiser systematically broken | 200 random + 48 coordinate perturbations of a synthetic fit | **0 improved** — genuine local maximum |
| Data genuinely prefers absorption | fitted `P(tranquil\|stressed)` across folds | **0.00044 / 0.0177 / 0.0072** — not absorbing on adequate samples |

**The failure does not reproduce on synthetic data.** So it is not a universal
implementation defect. The remaining explanation consistent with all of the above: the
transition-block likelihood is **multi-modal**, and the all-zeros start lands in a poor
basin on some real samples.

---

## 3. The fix (smallest defensible)

No model change, no regime-count change, no covariate change, **no transition floor**,
no occupancy target.

1. **Multi-start over the transition block** in `C7 fit()` — the default start plus 4
   bounded uniform draws in `[−2, 2]`.
2. **Selection among converged fits only.** This is not cosmetic: during the diagnostic,
   restarts reporting **+48** and **+881** llf over the default were **non-converged**,
   and an earlier analysis of mine wrongly cited them as better optima. Selecting on
   likelihood alone picks exactly those.
3. **Minimum causal training window 1,260 → 2,000.** 1,260 is where the boundary drift
   occurred; a 2,146-observation fold was healthy (47.6/26.3/26.1).
4. **`causal_tvtp_exog`** — expanding-window standardisation, closing leak (3).
5. **Dual mode** — `fit(probabilities="filtered"|"smoothed")`, selecting between two
   series statsmodels already computes from the same fit. Smoothed is retained for
   in-sample description only.

---

## 4. Unit validation (synthetic — passes)

`tests/test_c7_hamilton_causal.py`, 7/7:

| Guard | Result |
|---|---|
| Multi-start returns a **converged** fit | pass |
| Fitted solution is a local maximum (40 perturbations) | pass — 0 improved |
| **Nesting invariant** `LL(full) ≥ LL(intercept-only)` | **pass** |
| Boundary transitions detectable | pass — min off-diagonal 1.455e-04 |
| Production path uses filtered, not smoothed | pass |
| Future observations cannot enter a refit window | pass |
| Causal exog uses no future moments | pass |

Repository: **134 passed**, 5 skipped (CT-3 intraday guards), invariants **5/5**.

---

## 5. What is NOT done

**Blocked — Docker daemon unavailable** (`npipe:////./pipe/dockerDesktopLinuxEngine`),
so TimescaleDB is unreachable and none of the following has been run:

- fold-3 reproduction on the real corpus with multi-start
- per-restart record of convergence / llf / AIC / BIC / transition params / boundary hits
- real-corpus nesting check
- multi-start vs single-start comparison on real data
- the full causal walk-forward
- causal occupancy, transition probabilities, half-lives, separation, NFR16, NFR17,
  fold-by-fold stability

**No causal NSE figure is stated anywhere in this document.** The synthetic tests show
the machinery is sound; they say nothing about whether the NSE corpus yields a usable
causal regime signal.

## 6. Next step

Start Docker Desktop, then run §5 in order. Until it passes, Hamilton stays out of the
production CSRS path and SERAPH is **not** a validated operational risk engine —
`hawkes_output`, `reconciled_state` and `csrs` all remain empty.
