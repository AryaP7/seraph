# SERAPH — PROJECT STATE / HANDOFF

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
