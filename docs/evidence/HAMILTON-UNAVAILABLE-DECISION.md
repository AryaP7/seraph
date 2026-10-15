# Pillar 3 (Hamilton): Formally Unavailable, With Evidence

> ## ⚠ PARTLY SUPERSEDED — read `HAMILTON-REGIME-SUPPORT.md` first
>
> Its **conclusion stands** (Hamilton's output is unavailable), but three of the
> supporting claims below were measured to be wrong later the same day, after two
> real defects were found in C7:
>
> * **§2 "the estimator is exonerated by the control" — WRONG.** The positive
>   control was six deterministic 500-day blocks (~5 switches in 3,000 days) and
>   passed *while the estimator was broken*. A realistically-switching 3-regime
>   control fails pre-fix. `_conditional_loglikelihoods` returned `(k, nobs)`
>   instead of `(k, k, nobs)`, so the EM transition step read single time-points
>   as transition counts. Cost: **16,573 log-likelihood** on a synthetic series
>   with known regimes.
> * **§3 "the NSE daily feature space supports at most two regimes, not three" —
>   WRONG.** An artefact of that bug. Post-fix all three states are populated
>   43%/25%/32% with half-lives 177/134/169 d, and *two* states fare worse than
>   three on every criterion.
> * **§2(a) the nesting violations — correct measurement, wrong diagnosis.** The
>   cause is the TVTP start value (all-zero logit ⇒ uniform 1/k matrix, 1.04-day
>   half-life), not the multi-start logic.
>
> The unavailability decision now rests on a **surrogate null**: the 3-state fit
> is not distinguishable from a process with no regimes at all (AAFT `p = 0.7143`,
> AR(1) `p = 0.9524`). §1's rule that semivariance is not a Hamilton regime filter
> is unchanged and still in force.

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`. Nothing committed.**
Evidence: `*-20-hamilton-observation-redesign.log`, `*-21-hamilton-design-D.log`,
`20261012T134047Z-hamilton-causal-REAL/REPORT.md`, `*-17-stress-candidate-study.log`.

---

## 1. What this document decides, and what it does not

**Decides:** Pillar 3's *current implementation* is declared **unavailable**, with
the evidence that forced it. SERAPH emits Hamilton as a **structural absence** on
every tick, which D2 already handles, and the mask records that on every row.

**Does NOT decide:** that the Hamilton research objective is invalid. Regime
dynamics and stress-state persistence remain a distinct dimension of systemic
risk in the paper's architecture, and nothing here authorises replacing that
objective with a volatility detector. **Downside semivariance is not a Hamilton
regime filter and is never to be presented as one.**

## 2. Three independent explanations were tested. All are now eliminated or ruled out.

### (a) The optimiser — eliminated by AMENDMENT-05's own fix failing

AMENDMENT-05 attributed the failure to the optimiser and implemented multi-start
over the transition block plus converged-only selection. Run on real data this
session (14 blocks, 114.7 min):

* **6/14 nesting violations**, to `LR = −2,322.88` — the full model scoring 1,161
  log-likelihood *below its own nested restriction*, which is impossible at a
  true maximum. AMENDMENT-05 documented one such fold at −414.55 and expected its
  fix to remove it; it is **systematic and 5.6× worse**.
* **3/14 folds non-converged**, covering the COVID and tariff emission windows.
* Multi-start gained **1.16e-10 llf** over a single start on block 0 — nothing.
* AMENDMENT-05 §2.1's premise is additionally **falsified**: 0/14 blocks ended
  with a zero transition block, and a single-start fit reaches `|44.2|`.

### (b) Feature smoothness — falsified by the positive control

`compare_hamilton_features.py` hypothesised "a series that cannot move cannot
switch". Its **own control refutes it**:

| design | ac_1 | ac_2 | ac_3 | tranq/stress/crisis | sep_σ |
|---|---|---|---|---|---|
| **CONTROL synthetic** | 0.9650 | 0.9295 | 0.9572 | 66.7 / 0 / 33.3 | **5.80** |
| CURRENT (RV,AR,BAS) | 0.9973 | 0.9983 | 0.9965 | 0 / 0 / **100** | 1.12 |
| A short/non-overlap | **0.7812** | 0.9919 | 0.9603 | 0 / 0 / **100** | 0.99 |
| C innovations | 0.4240 | 0.0928 | −0.1922 | 78.3 / 11.1 / 10.6 | **0.14** |

The control's autocorrelations are nearly as high as CURRENT's and it separates
at 5.80σ. Design A cut `ac_RV` from 0.997 to 0.781 and failed **identically**.
Persistence is not the binding constraint.

### (c) Uninformative observations — tested here, and also insufficient

Measured over six epochs, two of Hamilton's three observations are **below chance**
for crisis detection: `ar_t` AUC **0.4453**, `bas_t` **0.3799**. So the hypothesis
was that Hamilton fails for want of informative inputs. Design D replaced them
with the three informative, daily-defined, causal, mutually-complementary
quantities from the nine-candidate study (`semivar_20` 0.7832, `rv_accel` 0.7706,
`drawdown` 0.7185):

| design | ac_1 | ac_2 | ac_3 | tranq/stress/crisis | sep_σ | τ_half |
|---|---|---|---|---|---|---|
| CONTROL synthetic | .965 | .930 | .957 | 66.7 / 0 / 33.3 | 5.80 | 346 d |
| CURRENT | .997 | .998 | .997 | 0 / 0 / **100** | 1.12 | 3.5e7 |
| D1 accel+semivar+dd | .975 | .979 | .997 | 0 / 0 / **100** | 0.98 | 3.5e7 |
| D2 semivar+jump+dd | .979 | .970 | .997 | 0 / **100** / 0 | **6.50** | **0.7 d** |
| D3 rv+semivar+dd | .997 | .979 | .997 | 0 / 55 / 45 | 1.24 | 71 d |

**D2 must not be read as a success.** Its 6.50σ exceeds the control, but occupancy
is 0/100/0 and the half-life is **0.7 days**: all mass sits in one state, so the
separation is measured between two regimes that are **never occupied**, switching
sub-daily. It is CURRENT's absorbing pathology parked in a different state.

D3 is the only non-degenerate fit — 55/45 occupancy, finite 71-day half-life — but
separates at **1.24σ**, below NFR17's 3σ and far below the control, and never
occupies tranquil.

**The pre-registered falsification condition triggered.** It was written before the
run: *"If Design D also collapses, the estimator is exonerated by the control, and
Hamilton should be formally declared unavailable with evidence rather than
repaired."*

## 3. The new finding worth carrying into the paper

**Every real-data design leaves at least one of three states at ~0% occupancy.**
CURRENT 0/0/100; D1 0/0/100; D2 0/100/0; D3 0/55/45; A 0/0/100. Only the synthetic
control, which has three genuinely separated means by construction, occupies more
than two.

This is evidence that **the NSE daily feature space supports at most two regimes,
not three** — which bears directly on objective O4's three-state specification. It
is a property of the data, measured across five observation designs and one
positive control, not a property of the estimator.

`scripts/diagnose_hamilton_regimes.py` ("how many latent regimes does the NSE
feature space actually support?") already exists for this question and is the
recommended next investigation. A two-state formulation would be a **SPEC
amendment with evidence**, preserving Hamilton's research identity (regime
dynamics) while matching what the data supports. It is **proposed, not done.**

## 4. Consequences for the engine

1. **Hamilton emits `UnavailableEmission(absence="structural")` on every tick.**
   This is the architecture's own mechanism (D2), not a workaround. `mask[2]` is
   `False` on every row of the primary configuration, so an unavailable pillar can
   never be mistaken for a valid estimate.
2. **The FR35 ablation cannot be completed as specified.** D5(b)'s Table B needs
   subsets `(rmt)`, `(hamilton)`, `(rmt, hamilton)` over 6 epochs. With Hamilton
   unavailable, every Hamilton-containing subset collapses to its available part
   via `score_subset`'s mask intersection ("an ablation can remove information,
   never invent it"). This is a reportable blocker, not a skipped task.
3. **The leaky 5,365-row `hamilton_output` series stays in place, unchanged**, and
   remains in-sample-descriptive only. Its occupancy 43.0/25.2/31.8 and NFR17
   2.02σ are smoothed figures and must never be cited as causal.
4. **Semivariance is NOT promoted into pillar 3.** The `--stress-slot` experiment
   remains an explicitly flagged research configuration under a distinct artefact
   id; see §5.

## 5. Provenance defect: contained, and the gated fix stated precisely

`PILLAR_ORDER` slot 3 is **named `"hamilton"`**, so a `CsrsPoint` with
`mask[2] = True` produced by `stress_emission` could falsely imply Hamilton ran.

**Containment in force:**

* The **default** path emits Hamilton as a structural absence — `mask[2] = False`
  on all 2,357 rows of the primary configuration.
* Semivariance enters only behind an explicit `--stress-slot` flag.
* The two line-ups carry **distinct artefact ids bound into the `csrs` primary
  key**: `349a6874e8bc6884` (mask_profile T,T,F) and `36b6f9bb7977e544` (T,T,T).
  A real defect was caught here before it bit — `baseline_weights()` initially
  returned one id for both, which would have **silently overwritten** one run.
* `stress_emission` carries a PROVENANCE WARNING as its first paragraph.
* The 3-pillar run is **not treated as a clean three-pillar result anywhere.**

**The gated change, for sign-off — not performed.** In ask-gated
`seraph/shared_types/core.py:54-55`:

```python
PILLAR_ORDER = ["hawkes", "rmt", "hamilton"]        # rename slot 3, or add a 4th
PillarId = Literal["hawkes", "rmt", "hamilton"]     # add the new id
```

**Blast radius: 16 files, 60 references** — heaviest `validation/ablation.py` (8),
`reconciliation/kalman.py` (7), `check_invariants.py` (7),
`fixtures/mock_generator.py` (6), `decision_support/artefacts.py` (5). A *fourth*
pillar additionally widens `Vec3`/`Mat3`/`AvailabilityMask`/`Simplex3`
(`core.py:57-71`), changing the Kalman state dimension, the Shapley enumeration
(2³ → 2⁴ subsets), `FusionWeights.w` (3×3 → 3×4), the `csrs.shapley`/`mask` array
lengths, and CT-9's renormalisation contract. The current evidence does **not**
justify a fourth pillar.

## 6. The FR30 fusion question — resolved by the specification, not by me

ARCHITECTURE **D5(c)** is authoritative and settles it:

> "The ablation is **descriptive, not selective**. All 14 configurations are
> reported. **No configuration is selected as best and then reported as the
> headline result** — that is selection bias with n=6 and it would invalidate the
> number."

So unconstrained nine-parameter calibration is not merely risky, **selecting any
winner is forbidden**. The correct deliverable is the descriptive 14-configuration
ablation with full per-fold spread, which `configuration_list()`, `subset_mask()`
and `score_subset()` already implement — and which is **blocked on §4.2**.

**Therefore equal weights remain in force as an explicitly uncalibrated research
baseline**, which is exactly the fallback the specification prescribes. No weights
have been manufactured.

**D5(b) also corrects a presentation error of mine:** Table A (Hawkes subsets, 4
folds) and Table B (RMT/Hamilton, 6 folds) "are not directly comparable and must
not be placed in a single ranking". The nine-candidate study placed Hawkes
(4 epochs) and RMT (6 epochs) in one ranked table. The per-candidate figures
stand; **the cross-fold-count ranking does not.**

## 7. Status

| pillar | research role | implementation status |
|---|---|---|
| **P1 Hawkes** | event contagion, propagation, toxicity | **operational** — 473 E6 rows, validated window, idempotent. Participates in 19.9% of ticks (D4 cadence gap). |
| **P2 RMT** | spectral coupling, structural instability | **operational** — 5,363 rows, 29/29 acceptance. Trailing estimator, 18–36 month lag, crisis-label AUC 0.4283. |
| **P3 Hamilton** | regime dynamics, stress persistence | **UNAVAILABLE** — estimator exonerated by control; features insufficient across 5 designs; ≤2 regimes supported. |

**All three pillars remain explicit in the architecture.** One is marked
unavailable, honestly, which is what the mask mechanism exists for.

## 8. Reproduction

```bash
docker start seraph-timescaledb
python scripts/compare_hamilton_features.py        # control + CURRENT + A + C
python scripts/test_hamilton_observation_d.py      # control + CURRENT + D1/D2/D3
python scripts/study_stress_candidates.py          # 9 candidates, 3 targets, 6 epochs
python scripts/run_csrs_research.py --write        # primary 2-pillar path
python scripts/check_invariants.py
```

## 9. Recommended next action

**Run `scripts/diagnose_hamilton_regimes.py` to establish how many regimes the
NSE daily feature space supports**, then decide whether a two-state Hamilton is a
defensible SPEC amendment. This is the only route that repairs Hamilton's intended
role rather than abandoning or counterfeiting it, and §3's evidence points
directly at it.

The early-warning problem (T3 below chance for everything tested) remains open and
is **not** solved by any work in this phase. No advance-warning capability is
claimed.
