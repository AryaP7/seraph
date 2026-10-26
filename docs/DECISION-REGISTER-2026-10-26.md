# Decision register — CSRS pillar eligibility, 2026-10-26

Prepared from a measured audit of the live store, the official engine and the
pre-registered pillar evidence. Every number below was produced by the official
`ArchiveReplay -> InferenceService -> KalmanReconciler -> score()` path against
`prototype_runs/live.sqlite`, read-only. Nothing was committed or pushed.

**Headline.** Hawkes is excluded from the composite by **two engineering
defects**, not by one scientific threshold. Correcting them is necessary but
**not sufficient**, and correcting them *today* would make the published CSRS
worse, not better: it would inject the ECDF's no-information placeholder 0.5
into the composite at half weight and move the latest score from **0.0900 to
0.2950** on zero information. The binding constraint is the Hawkes reference
history (3 observations exist; 252 are required), and that is a data-acquisition
problem, not a gate to relax.

Hamilton stays out. Its exclusion is supported by its own pre-registered tests,
which it fails under both surrogate families.

---

## 1. Status summary

| # | Finding | Kind | Status |
|---|---|---|---|
| D-1 | `run_daily.py` writes `absence="structural"` for Hawkes on every session without a fresh fit. Structural clears the mask bit unconditionally — even for a fresh, unsaturated carried-forward fit. | **Defect** (misclassification against AGENTS.md §5) | **Awaiting decision** — binds 251 of 254 sessions |
| D-2 | D4 `h_bars[hawkes] = 1.0` bar. The Hawkes pillar updates once per 5 sessions, so its eligibility lifetime is 0.8% of one of its own update cycles, against RMT's 299%. | **Defect** (false premise in ARCHITECTURE §D4) | **Awaiting decision** — binds the other 3 sessions |
| D-3 | The ECDF rank's own sampling uncertainty is never propagated. 0 of 777 stored vintages carry an estimation variance, so a rank from **0** reference observations is assimilated with the same `R₀ = 0.02` as a rank from 1,260. | **Defect / gap** (FR26, FR29 information accounting) | **Awaiting decision** — this is why D-1+D-2 must not be applied alone |
| D-4 | `MIN_WINDOW_OBS = 252` is a trading-**day** count applied to a pillar that emits ~49.7/year. Unsatisfiable by construction at any data depth. | Unit error | **Awaiting decision** (options carried forward from 2026-10-25) |
| D-5 | 11 Hawkes fits dated 2026-10-07..2026-10-23 were written at **daily** spacing by a run that defeated the five-session cadence gate. | Contaminated artefact | **Awaiting decision** — nothing removed |
| D-6 | `scripts/run_daily.py` archived path emitted the FR13-**gated** `mts` (0.0 on 352 of 473 rows) while the native producer emits the ungated `n/(1−n)`. | **Defect** | **FIXED** (FIX-1) — no stored value changed |
| D-7 | `scripts/live_session_pass.py` called `SessionCalendar.default()`, which does not exist. Without `--calendar` the scheduled live recorder raised `AttributeError` on step 1. | **Defect** | **FIXED** (FIX-2) — verified working |
| D-8 | No scheduled in-session live pass exists. `scripts/register_live_task.py` is referenced in the recorder's own docstring but is **absent**. The one registered task runs post-close (18:30) and its last run was **refused**. | Operational gap | **Reported** — see §6 |
| D-9 | Hamilton fails its pre-registered regime-support and surrogate-null criteria. | Scientific limitation, correctly handled | **No change — exclusion preserved** |

---

## 2. Why Hawkes is in no mask — measured, in order of what actually binds

Replay of all 254 sessions, official engine:

| configuration | composites | Hawkes masked in |
|---|---|---|
| as shipped | 254 | **0** |
| D-2 corrected only (`h = 375` bars) | 254 | 1 |
| D-1 corrected only (between-fit = transient) | 254 | 0 |
| D-1 **and** D-2 corrected | 254 | 2 |

So neither correction alone suffices, and the dominant gate is **D-1**: 251 of
254 sessions never reach D4 at all, because a stored `structural` absence has
already cleared the mask bit.

### D-1, stated precisely

AGENTS.md §5 defines the distinction: *"Structural → pillar excluded from the
mask. Transient → stays in the mask, D4 age-inflation handles it"*, and gives
the canonical structural case as *"a structurally-missing Hawkes score
pre-2015"* — i.e. a period in which the measurement **cannot exist**.

`scripts/run_daily.py` records, for every session with no fresh fit:

> `absence="structural"` … *"No fresh Hawkes estimate is supplied by this daily
> job."*

That sentence describes a **transient** condition — this job does not supply
it — not a structural one. A Hawkes fit for 2026-10-23 plainly *can* exist; one
exists for 2026-10-22, and the model is designed to refit every five sessions,
so "no new fit this session" is the ordinary between-fit state the carry-forward
machinery exists to handle. The native producer classifies the identical
condition the other way: *"Missing native inputs are transient once this
producer is configured, keeping Hawkes in the D2 mask."*

Two producers therefore disagree about the absence kind for one pillar, and the
archive replay reads the stricter one.

Measured (`tests/test_d4_cadence_and_eligibility.py`): a Hawkes fit observing
through 2026-10-22 15:15, evaluated at 2026-10-23 15:30 — 78 bars later, and
**not** saturated on a one-native-cycle scale — is masked **out** when the
session declares `structural` and masked **in** when it declares `transient`.

### D-2, stated precisely

D4's resolution (SPEC OQ10) sets `h_p` to *"each pillar's native update
cadence"*, and ARCHITECTURE §D4 reads that as *"Hawkes 5 min, RMT 1 trading day,
Hamilton 1 trading day — a signal becomes appreciably stale after roughly one of
its own update cycles."* The rule is sound; the parenthetical is false about the
pillar that was built.

With `R_max = 100·R₀` and saturation at `0.95·R_max`, the ceiling is reached at

```
Δ_sat = h · ln( (R_max/R₀ − 1) / (R_max/R₀ − 0.95·R_max/R₀) ) = 2.9857 · h
```

independent of `R₀`. So each pillar's eligibility lifetime is set entirely by
its own `h`:

| pillar | configured `h` | Δ_sat | measured native cycle | lifetime in its OWN cycles |
|---|---|---|---|---|
| RMT | 75 bars (1 session) | 2.986 sessions | 1 session (250.7 emissions/yr) | **299%** |
| Hamilton | 75 bars | 2.986 sessions | 1 session | **299%** |
| Hawkes | **1.0 bar** | **2.986 bars = 14.9 min** | **5 sessions** (49.7 emissions/yr) | **0.80%** |

The Hawkes cadence is measured, not assumed: `research_data/original_hawkes.parquet`
holds 473 observations over 2017-02-09..2026-08-20 with 473 distinct values and
consecutive gaps of 7 or 8 calendar days, and every native config carries
`refit_sessions = 5`. The pillar value is `n/(1−n)`, a function of the fitted
parameters alone, so it **cannot** change between fits — there is no
bar-frequency observation to be fresh.

The consequence is sharp enough to be worth stating: the native fit observes
through **15:15**, the end of the common continuous session (15:15–15:30 is the
closing auction, which the model's own grid excludes), and the decision is taken
at the nominal close **15:30** — exactly 3.0 bars later, against a 2.9857-bar
ceiling. The freshest observation that can possibly exist is excluded by **4.3
seconds** of trading time.

---

## 3. Why correcting D-1 and D-2 today would make the score worse

With D-1 and D-2 applied and the D-5 fits excluded, Hawkes enters the mask on
2026-10-22 and 2026-10-23, and the latest composite becomes:

| | as shipped | D-1 + D-2 |
|---|---|---|
| CSRS | 0.08998820433752137 | **0.2949941021687607** |
| mask | `(False, True, False)` | `(True, True, False)` |
| effective weights | `(0.0, 1.0, 0.0)` | `(0.5, 0.5, 0.0)` |
| variance | 0.09140964663211956 | 0.050529659337002764 |
| 95% interval | [−0.5026, 0.6826] | [−0.1456, 0.7356] |
| publishable as current | False | False |

That +0.2050 is **not** a contagion reading. On 2026-10-22 the Hawkes ECDF
reference window held **zero** prior observations, so `standardise` returned its
documented no-information midpoint (`ecdf_transform`: *"An empty window has no
distribution to rank against; the uninformative midpoint 0.5 is returned"*).
The implied filter state is **x_hawkes = 0.500000000000000 exactly** — the `x0`
prior, untouched, because the filter was updated toward 0.5 from a prior of 0.5.
It then carries forward unchanged to 2026-10-23.

So the entire movement is one hard-coded constant averaged against RMT's real
0.0900. This is **D-3**: because no pillar supplies an estimation variance, that
0.5 is assimilated with `R₀ = 0.02` — the same confidence as a rank backed by a
full five-year window.

**Therefore the correct sequence is D-3 before D-1/D-2, or D-1/D-2 only once the
Hawkes reference history exists.** Applying D-1 and D-2 on today's data would
publish a higher risk score built from a placeholder. The current single-pillar
CSRS is the scientifically correct output today — though for a different reason
than the code gives.

---

## 4. Decisions requested

### DEC-1 — D-3: propagate the ECDF rank's sampling uncertainty (recommended first)

A rank from `n` reference observations has binomial sampling standard error
`sqrt(p(1−p)/n)`, which is undefined at `n = 0` and ~0.0141 at `n = 1260`.
Feeding `estimation_variance = p(1−p)/n` (floored, and with an explicit refusal
at `n = 0` rather than a 0.5 placeholder) would let D4 down-weight an
under-warmed pillar automatically instead of trusting it equally.

- **Cost:** a new formula in the FR28→FR26 seam. Needs approval; it is not in
  any current amendment.
- **Benefit:** makes D-1 and D-2 safe to apply, and removes the "absence becomes
  a confident 0.5" path for every pillar, not just Hawkes.
- **Alternative:** have `standardise` refuse (return an `Err`/transient absence)
  below a declared minimum `n`, rather than emitting a midpoint. Smaller change,
  no new formula, but it converts a warning into a withholding.

### DEC-2 — D-1: the absence kind for a between-fit Hawkes session

- **A (recommended, after DEC-1):** between-fit sessions declare `transient`;
  sessions where no fit could exist (before any native history / basket) keep
  `structural`. Restores the documented meaning of both kinds and makes the two
  producers agree. **Must be paired with an age limit** (DEC-4), or a transient
  absence keeps an arbitrarily stale fit in the mask forever.
- **B:** leave as is. Honest status quo, but it mislabels a cadence gap as a
  structural impossibility and makes `refit_sessions` unobservable in the mask.

### DEC-3 — D-2: the D4 staleness scale for Hawkes

- **A (recommended):** `h_bars[hawkes] = 375.0` (5 sessions = one measured
  native cycle). Applies D4's own stated rule uniformly: every pillar then
  saturates after ~2.99 of **its own** update cycles, exactly as RMT does. This
  is a unit correction, not a relaxation — the absolute tolerance rises 375×,
  but the tolerance *in the pillar's own information-refresh units* becomes
  identical to RMT's.
- **B:** make Hawkes genuinely bar-frequency by refitting every bar, which is
  what FR13 (*"emit MTS_t at bar frequency"*) and AGENTS.md §2 (*"runs at bar
  frequency … the one genuinely latency-sensitive numerical component"*) assume.
  Then `h = 1` is right and D-2 is not a defect. **But** this changes
  `refit_sessions` from 5 to 1 — a declared parameter, part of `_compatible`,
  which invalidates every existing fit — and departs from the original pillar,
  which was weekly. Not recommended without a separate decision.
- **C:** leave as is, and document that Hawkes is eligible for 0.8% of trading
  time by construction.

### DEC-4 — an age limit on a transient absence

D2 row 3 (*"transient → mask true, D4 inflation handles it"*) carries no age
limit, so `mask = True` and `noise_saturated = True` can hold simultaneously.
Measured: an observation 13 sessions old is masked **out** if carried forward and
**in** if its producer declares a transient absence — identical information,
opposite mask. Declaring an absence is currently *more* favourable to inclusion
than saying nothing.

- **A (recommended):** apply the same saturation ceiling to a retained transient
  observation. Once `R` is at its ceiling, D4 is no longer "handling" anything.
- **B:** leave as is. Latent today (all stored Hawkes absences are structural),
  but it becomes live the moment DEC-2A is adopted.

### DEC-5 — D-4: the warm-up threshold's units

Carried forward unchanged from 2026-10-25. `MIN_WINDOW_OBS = 252` ("One trading
year") is a daily count; Hawkes emits ~49.7/year, so a five-year window holds
~248 and the gate is unsatisfiable at any depth. Options A (count in the
pillar's own cadence, ~50), A′ (a full five years at that cadence, ~248, needing
~5 more years of native history), B (nothing), C (make the pillar a daily
statistic — a methodology change), D (`require_warmup=False` — weakens a
declared safeguard).

Note this gate controls **publication**, not mask inclusion. It is why every one
of the 254 replay decisions is `withheld`, and it is currently the *only* thing
preventing the §3 placeholder score from being published as current.

### DEC-6 — D-5: the 11 mis-spaced fits

Real, dated, provenanced computations, each on 500 sessions with zero incomplete
members, but written at **daily** spacing by a run that defeated the five-session
cadence gate. They are in `prototype_runs/live.sqlite` and nothing was removed.

- **A:** remove exactly those 11 so the series rebuilds forward at the declared
  cadence. The only Hawkes observations then remaining are the archived
  2026-08-20 point and the legitimate 2026-10-22 fit.
- **B:** keep them and accept a daily-cadence ECDF for those dates.

Measured either way: with them excluded, Hawkes enters the mask on 1 session
(D-2 alone) or 2 (D-1+D-2); with them included, 3. The latest published CSRS is
**unaffected** in the as-shipped configuration, because the mask is
`(False, True, False)` and the Hawkes value carries weight 0.

---

## 5. Hamilton — no change recommended

Hamilton fails its own pre-registered criteria. From
`docs/evidence/20261013T030256Z-25-hamilton-surrogate-null.log`:

| test | result |
|---|---|
| AR(1) surrogates | real separation 2.020; null mean 4.109; **empirical p = 0.9524** |
| AAFT surrogates | real separation 2.020; null mean 2.147; **empirical p = 0.7143** |
| distinguishable under both families at p ≤ 0.05 | **False** |
| NFR17 (separation ≥ 3.0σ) | **False** (2.020) |

and from `…-24-hamilton-regime-support-validation.log`:

| criterion | result |
|---|---|
| R1 procedure validity | PASS |
| **R2 negative controls** | **FAIL** — a smooth AR(1) with **one** regime was *not* rejected at k=2 or k=3 |
| R5 separation | FAIL at k=2, 3, 4 |
| R6 fold stability, k=3 | **FAIL** (4/6 folds) |
| R9 BIC | prefers **k=4**, not the specified k=3 |
| R7 init robustness | PASS (8/8 identical) |

The causal TVTP walk-forward is separately unusable: 6/14 nesting violations to
LR = −2,322.88 (arithmetically impossible at a true maximum), 3/14 non-converged,
causal NFR17 = 0.269σ.

The R2 failure is decisive on its own: the acceptance criteria cannot reject a
process with no regime structure, so they have no discriminating power. There is
**no approved pathway to activation**, and `AMENDMENT-05`'s verdict ("Hamilton is
**not** cleared for production CSRS") stands. Note AMENDMENT-05 §5–6 still says
this work is blocked on Docker; it was in fact completed on 2026-10-12/13 and the
amendment was never updated. That doc should be amended to point at the evidence
above.

Enabling Hamilton to obtain a third pillar would be exactly the manufactured
participation the directive forbids.

---

## 6. Operational gaps (D-8)

- `scripts/register_live_task.py` is named in `live_session_pass.py`'s docstring
  as the registration mechanism and **does not exist**.
- The only registered task is **"SERAPH Daily Market Jobs"** →
  `run_market_jobs.py --scheduled`, Mon–Fri **18:30** (post-close), next run
  2026-10-26 18:30. There is **no scheduled in-session live CSRS pass**.
- That task's last run (2026-10-24 17:21) returned **0x800710E0** — the request
  was refused. Its settings are `DisallowStartIfOnBatteries = True`,
  `StopIfGoingOnBatteries = True`, `WakeToRun = False`, so it will silently not
  run on battery or while the machine is asleep. One line fixes it, on your
  machine rather than in the repo:

  ```powershell
  Set-ScheduledTask -TaskName "SERAPH Daily Market Jobs" -Settings (
      New-ScheduledTaskSettingsSet -StartWhenAvailable)
  ```

  Not applied: it changes your machine's power policy, not project code.
- Kite access tokens are invalidated daily at ~06:00 IST regardless of issue
  time. A token minted before the open is commonly dead by it, and
  `scripts/kite_login.py` is an interactive browser login.
