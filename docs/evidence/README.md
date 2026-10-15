# SERAPH — Evidence Recovery Report

**Phase:** evidence recovery and verification (no architecture changes, no model tuning,
no new features, no Hamilton causal run).
**Run:** 2026-10-12, 13:12Z – 13:25Z · git `f79299d` (working tree dirty only in
`.claude/settings.json`) · Python 3.12.14 · PostgreSQL 16.15 / TimescaleDB 2.29.2.

Every figure below was **measured against the live database today**. Where a number is
quoted from a prior session's markdown and was *not* re-measured, it is labelled
`DOCUMENTATION ONLY`.

---

## 1. Environment restoration

| Step | Command | Result |
|---|---|---|
| Docker daemon | `Start-Process 'Docker Desktop.exe'` | UP, server 29.7.2 |
| Volume survival | `docker volume ls` | **`seraphvarya_seraph_pgdata` intact** |
| Service start | `docker start seraph-timescaledb` | healthy in ~15 s |

`docker start` was used deliberately in place of `docker compose up -d`: it starts the
existing 7-week-old container without recreation and without re-running the
`docker-entrypoint-initdb.d` mount. **No volume was created, pruned, reset or recreated.**

The Python toolchain had to be repaired first: `.venv/pyvenv.cfg` pointed at a uv-managed
CPython 3.12.14 that uv had since removed, so every command failed with `No Python at …`.
Fixed with `uv python install 3.12.14` + `uv pip install -e ".[dev]"`.

---

## 2. Evidence classification

### REPRODUCED — measured today, matches documentation

| Claim | Source | Measured today |
|---|---|---|
| `daily_prices` 8,023,206 rows | HANDOFF | **8,023,206** (1995-01-02 → 2026-08-21) |
| `intraday_bars` 18,781,302 rows | HANDOFF | **18,781,302** (2015-02-02 → 2026-08-21) |
| `universe_snapshots` 44 | HANDOFF | **44** (2005-01-01 → 2026-07-01) |
| `hamilton_output` 5,365 | HANDOFF | **5,365** |
| `rmt_output` 5,363, FR16 PASS | DEMO-DELETE-ME | **5,363**, FR16 **PASS** |
| FR16 `max‖trace−N‖ = 2.84e-13` | AMENDMENT-04 §2.1 | **2.84e-13** (exact) |
| λ₁/N mean 0.25349 sd 0.04243 | AMENDMENT-04 §6.2 | **0.2535 / 0.0425** |
| Thinning paired ratio 1.0176, [0.9961, 1.0302] | AMENDMENT-04 §6.4 | **1.0183, [0.9973, 1.0349]** |
| 2010-05-16 / 2012-11-11 are gold-ETF-only (6 and 11 rows) | AMENDMENT-04 §2.2 | **6 and 11 rows, all gold ETFs, zero equities** (exact) |
| 21,180 negative jump events | AMENDMENT-03 | **21,180** (exact) |
| 75.8% of events share a bar; max 89 simultaneous | AMENDMENT-03 | **16,056/21,180 = 75.8%; max 89** (exact) |
| Hawkes α≈0.0557 φ≈0.4837 n≈0.1079, CV 2–4.1%, n<1 all folds | HANDOFF §2 | **α 0.0557 · φ 0.4837 · n 0.1079 · CV 2.0/2.5/4.1% · n<1 True** (exact) |
| Hamilton occupancy 43.0 / 25.2 / 31.8 | HANDOFF §3 | **43.0 / 25.2 / 31.8** — see caveat in §4 |
| `hawkes_output`, `reconciled_state`, `csrs` empty | DEMO-DELETE-ME | **all 0** |
| FusionWeights artefact missing | audit | **confirmed absent** |

Also reproduced, and **newly verified against real data for the first time**:

- **`validate_rmt_production.py`: 29/29 checks PASSED, exit 0.** Includes daily coverage
  5363/5363 with no gaps, PSD (min eigenvalue 3.698e-02), λ± recomputed per date at the
  realised `Q_t` (max deviation 0.00e+00, `Q_t` 2.00–8.20), λ₁/N lag-1 autocorrelation
  0.99974, and Ω_t reproducible from persisted `v1` on 5109/5109 identical-membership
  steps (worst 2.55e-15) — so a restarted engine resumes D3 exactly.
- **FR52 filter-before-rank CONFIRMED.** The documented bug trap (rank before filter →
  silently fewer than 500 names) does not occur: `members == eligible_count` in all 11
  early snapshots where the eligible pool is below cap (292→481), `members` pins at
  exactly 500 in all 33 snapshots where eligible exceeds 500 (535→1,758), zero cases of
  `eligible_count < members`, zero duplicate members.
- **CT-1 ingestion idempotency: 2/2 PASSED on the real database** (previously skipped).
- **Zero duplicate rows on every natural key** — `(symbol,date)`, `(symbol,ts)`, `date`,
  `rebalance_date` — so `writeBatch` idempotency holds in the persisted data, not just in
  the contract test.
- **The Hawkes production emission is accepted by C8 unmodified**:
  `status=ok n=0.1018`, `mask=[True, False, False]`, `xHat[hawkes]=0.4810`. First time a
  real pillar emission has traversed C8 in this repository.

### FAILED

| Item | Detail |
|---|---|
| **CT-3 `test_ct3_negative_jump_density_supports_a_one_day_window`** | `MIN_NEG_JUMPS_PER_DAY = 1.0`; measured **0.09/day** (EXIDEIND, 3 negative jumps over 33 trading days). **This is the project's own documented finding, not a regression.** SPEC v4 O2 states verbatim that "per-symbol one-day windows fail by construction — a property of the data, not the implementation". The test encodes the pre-AMENDMENT-03 expectation and has not been re-pointed at the pooled model. **The threshold was not touched.** |
| **`hamilton_output.gamma_ij` is NULL on all 5,365 rows** | The TVTP coefficients that produced the persisted series were never written. There is no record of what transition parameters generated E8, so that fit is not auditable or reproducible. |
| **`hamilton_output.rv_t_5min` is NULL on all 5,365 rows** | Despite intraday coverage from 2015-02-02. The intraday RV component of the observation vector never ran. |

### BLOCKED

| Item | Reason |
|---|---|
| Hamilton causal validation | Explicitly out of scope for this phase. Prerequisites now met (DB up). |
| NFR16 (4/6) and NFR17 (2.02σ) | Not re-measured — would require re-running the estimator. `DOCUMENTATION ONLY`. |

### DOCUMENTATION ONLY — quoted, not re-measured

- NFR16 = 4/6 and NFR17 = 2.02σ (and both describe the **leaky** series).
- The AMENDMENT-05 TVTP defect analysis (EM not updating the transition block; the fold-3
  LR = −414.55 anomaly). Its synthetic test suite passes; no real-corpus causal run exists.

---

## 3. Discrepancies resolved

**The 374 vs 5,363 contradiction is resolved: DEMO-DELETE-ME.md is current, HANDOFF.md §4
is superseded.**

HANDOFF.md (2026-08-23) recorded `rmt_output` = 374 rows with FR16's trace guard
**failing** at `4.99e-01`. DEMO-DELETE-ME.md (2026-08-24) recorded 5,363 rows and PASS.
Measured today: **5,363 rows, 5,363 distinct dates, FR16 `max‖trace−N‖ = 2.84e-13`.**
HANDOFF was written mid-investigation, before the `_correlation` `ddof` fix (AMENDMENT-04
§2.1) and before the `stride=1` daily production run. Its 374/FAIL state is historical and
cannot — and should not — be reproduced.

**Two apparent mismatches that are run-scope artefacts, not defects:**

| Quantity | HANDOFF (stride=10, 374 dates) | Today (daily, 5,363 dates) |
|---|---|---|
| PSD min eigenvalue | 3.71e-02 | 3.698e-02 |
| SCA_t mean / sd | 0.4359 / 0.1519 | 0.4896 / 0.1584 |

Both HANDOFF figures came from the stride-10 validation sweep; today's are the full daily
series. Different populations, both non-degenerate. Not a contradiction.

**FR19 replication count confirmed.** The p-value sits at `0.000999 = 1/(1000+1)` on 100%
of dates, which proves production ran at FR19's specified 1,000 replications (the
AMENDMENT-04 diagnostic sweep used 200, giving 0.00498). Degenerate by construction, as
AMENDMENT-04 §4 documents — a structure check, not a discriminator.

---

## 4. Caveats that must travel with these results

1. **Hamilton's reproduced occupancy is a measurement of a leaky series.** 43.0/25.2/31.8
   is confirmed as *what is persisted*, and the persisted series leaks the future three
   ways (Kim smoother, single full-sample fit, full-corpus z-scoring). It is **not causal
   evidence** and must never be cited as such.
2. **E8 has no smoothed-vs-filtered provenance column.** Nothing in the schema records
   which probability mode produced a row, so a causal series written into the same table
   would be indistinguishable from the leaky one. This should be fixed *before* any causal
   run writes to E8.
3. **A functioning pipeline is not predictive skill.** Nothing here establishes any. P1's
   own pre-registered test scored approximately no skill; P2's lead-time claims were
   withdrawn in favour of a measured 18–36 month *lag*.
4. **No end-to-end SERAPH validation is claimed.** `reconciled_state` and `csrs` are still
   empty and no FusionWeights artefact exists. P1 and P2 are validated in isolation only.

---

## 5. New findings not in any prior document

1. **`microstructure_state` is empty (0 rows).** FR6's `S_t` is not persisted anywhere;
   CT-3 constructs it ad hoc and says so. This is an input the Hawkes production writer
   will need.
2. **Pillar 1's entire validator set depended on an ephemeral OS temp file.** Five scripts
   (`verify_hawkes_production.py`, `compare_hawkes_windows.py`, `compare_pillar1_models.py`,
   `test_excess_risk_prediction.py`) load a hardcoded
   `C:/Users/.../AppData/Local/Temp/p1_data.pkl` that Windows had cleaned. Recovered by
   re-running its producer, `diagnose_inar_session_handling.py` (DB-read-only), which
   regenerated it byte-faithfully (21,180 events, max 89, 75.8% ties all exact). **The
   hardcoded temp path is a reproducibility defect: this evidence chain will break again.**
3. **`fit_hawkes.py` fits the *rejected* continuous-time model** (`fit_pooled`, with `beta`),
   not the production discrete-time one. Only the pickle-dependent scripts exercise the
   production path. Anyone running `fit_hawkes.py` expecting production parameters will get
   the superseded formulation.
4. **3,558 `intraday_bars` rows have `close <= 0`**, across 10 symbols, **all inside the
   95-symbol Hawkes universe** (INFY/ICICIBANK/ITC 900 each, MAZDOCK 341, SBIN 225,
   WEBELSOLAR 128, TCS 75, INOXWIND 75, SUNDRMFAST 13, COFORGE 1). They are contiguous
   whole sessions — INFY is 12 sessions × 75 bars, 2015-04-27 → 2015-05-13 — i.e. a Kite
   feed gap stored as zeros rather than nulls. **Impact on Pillar 1 measured as nil:**
   `extract_jumps` emits 0 NaN, 0 inf, and flags 0 jumps on a non-finite log return.
   Reported because it is undocumented and a naive return calculation would break on it.
5. **`daily_prices` has 14 rows with `close <= 0`** (ESSENTIA, 2019) — outside the Hawkes
   universe.
6. **Only one ingestion watermark exists** (`kite`/`E1`). There is no `eod2`/`E3`
   watermark, so the 8.0M daily rows were bulk-loaded without one. A side benefit: CT-1's
   `DELETE FROM ingestion_watermarks WHERE source='eod2'` is a no-op, which is why running
   CT-1 was provably safe for existing state.

---

## 6. Regression baseline

| Run | Result |
|---|---|
| Previous (DB **down**) | 134 passed, 6 skipped |
| **Today (DB up)** | **139 passed, 1 failed, 0 skipped** — 7 m 53 s |
| Invariants | **5/5 ok**, exit 0 |

The 6 skips resolved into 5 passes (CT-1 ×2, CT-3 ×3) and the single documented CT-3
density failure. No assertion was weakened, no threshold changed, no test skipped.

---

## 7. Files created

All under `docs/evidence/`, timestamped `20261012T131207Z`, nothing overwritten:

| File | Contents |
|---|---|
| `-01-db-census.log` + `.query.py` | Full table census, row counts, ranges, watermarks, RMT integrity |
| `-02-validate-rmt-production.log` | `validate_rmt_production.py`, 29/29 PASS |
| `-03-real-data-contract-tests.log` | CT-1 + CT-3 on real data, with the full CT-3 traceback |
| `-04-invariants.log` | `check_invariants.py`, 5/5 |
| `-05-full-suite-db-up.log` | Full pytest with DB reachable, 139/1/0 |
| `-06-p1-cache-regeneration.log` | Pillar 1 cache rebuild + INAR session-reset diagnostic |
| `-07-verify-hawkes-production.log` | Production discrete-time Hawkes reproduction + C8 handoff |
| `-08-fr52-universe-integrity.log` + `.query.py` | All 44 snapshots, filter-before-rank proof |
| `-09-corpus-data-quality.log` | Duplicates, nulls, ETF phantom dates, zero-close analysis |

Each log carries its own provenance header: UTC timestamp, git commit, working-tree
state, exact command, DSN, container identity and exit code.

---

## 8. Exact next action

Prerequisites for the Hamilton causal run are now met (DB up, baseline recorded, Pillar 1
and Pillar 2 reproduced). Before that run writes anything to E8, **caveat 4.2 should be
settled**: add a provenance marker distinguishing filtered from smoothed, or write the
causal series somewhere other than E8 — otherwise the leaky and causal series become
indistinguishable in the same table. That is a `shared_types`/schema decision and is
ask-gated per `CLAUDE.md`.

Reproduce everything in this report:

```bash
docker start seraph-timescaledb                                   # not `compose up -d`
.venv/Scripts/python.exe scripts/validate_rmt_production.py       # 29/29, read-only
.venv/Scripts/python.exe scripts/diagnose_inar_session_handling.py # rebuilds p1_data.pkl
.venv/Scripts/python.exe scripts/verify_hawkes_production.py      # needs the cache above
.venv/Scripts/python.exe -m pytest tests/ -v                      # 139 passed, 1 failed
.venv/Scripts/python.exe scripts/check_invariants.py              # 5/5
```
