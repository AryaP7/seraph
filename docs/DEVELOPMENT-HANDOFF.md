# SERAPH development handoff

**Last updated:** 2026-10-16
**Workspace:** `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`
(WSL: `/mnt/c/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya`)
**Base commit:** `51680bb` — **no commit, push, merge or deployment has been made.**
All work is in the working tree, alongside the modified and untracked files
that predate this session. Nothing was reset, cleaned or overwritten.

Read first: [DEVELOPMENT-PLAN.md](DEVELOPMENT-PLAN.md) ·
[DEVELOPMENT-STATUS.md](DEVELOPMENT-STATUS.md) ·
[PRODUCT-CONTRACTS.md](PRODUCT-CONTRACTS.md) ·
[SOURCE-TO-SCREEN-INVENTORY.md](SOURCE-TO-SCREEN-INVENTORY.md)

---

## 1. Where the programme stands

Phase 0 (orientation, scope, contracts) is **complete**.
Phase 1 is **complete**: `FIX01`, `FIX02`, `FIX03`, `FIX08`, `FIX09`, `FIX10`,
`FIX11` are all implemented and verified, each with regression coverage and a
dated decision record (DR-01, DR-02, DR-03).

Phase 2 has started: `FIX04` is verified. `DATA01`, `FIX05`, `FIX06`, `FIX07`
and `DATA02` remain. `QA03` (packaging) is verified out of order, since it was
dependency-free.

**Phases 3–9 have not been started at all.** No identity or tenancy layer, no
news subsystem, no fresh-data pipeline, no portfolio persistence, no case
workflow, no fitted macro-policy artefact, no operational monitoring. 46 of the
59 backlog items are not started; the status register says which are blocked
and on what.

## 2. Exact next step

`FIX04` (causal state bins) is **done and verified** — see
[DR-04](decisions/DR-04-2026-10-16-causal-state-bins.md). The next
dependency-ready items, in order:

**`DATA01` — disposable guarded Timescale service.**
- Provision a **new** database named `seraph_test_*`, create
  `seraph_test_guard(token text)` and insert the token. `tests/conftest.py`
  refuses anything else: the DSN's database name must start with
  `seraph_test_`, `SERAPH_TEST_TOKEN` must be set, and the marker row must
  exist. Never place that marker in a source or research database.
- Then run the 13 currently-skipped tests (`CT-1` ingestion idempotency,
  `test_c2_macro_ingestion`, `test_c5_hawkes_writer`). `CT-3`'s four skips need
  a real intraday corpus, not a schema — keep that distinction explicit.
- Docker's Linux engine was unavailable at the last check. If it stays
  unavailable, `DATA01` is blocked and `FIX07` proceeds instead.

**`FIX07` — persist Hawkes fit parameters and a point-in-time basket.**
- `scripts/write_hawkes_production.py:224` writes `"alpha_beta": None` and a
  hardcoded `"flag": "none"`, so no fitted parameter survives and FR14's
  sector flags are never measured.
- `scripts/write_hawkes_production.py:167` selects
  `FROM universe_snapshots ORDER BY rebalance_date DESC LIMIT 1` — today's
  membership applied to historical windows.
- Persist coefficients, training cutoff, input/basket identity, seasonality and
  fit diagnostics; verify an intensity can be reconstructed from a saved fit;
  use point-in-time membership or disclose a fixed research basket. Test that a
  future membership change cannot alter earlier inputs.
- `FIX04`'s `QuantileBins.artefact_id` is the pattern to follow for artefact
  identity.

**`FIX05` — FR35 Table B.** Still `scientifically unresolved`. SPEC FR35 puts
Table B on the two pre-Hawkes epochs; `validation/preregistration.py` /
`configuration_list()` uses all six. The xfail test deliberately still fails.
Write a dated design decision; do not pick an interpretation to clear it.
`FIX06` (evaluation-identity migration, audit finding A06 — the
`validation_results` primary key still omits `table_id`, the preregistration
hash and any evaluation-run identity) depends on that design.

## 3. Commands

```powershell
# Core partition (~110 s) — run at every slice close
$env:OPENBLAS_NUM_THREADS='1'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m pytest tests `
  --ignore=tests/test_c7_hamilton.py --ignore=tests/test_c7_hamilton_causal.py `
  --ignore=tests/test_c7_hamilton_regime_recovery.py `
  --ignore=tests/contract/test_ct7_simulator_consistency.py -q

# Expensive model/policy partition (~18 min) — integration gates only
.\.venv\Scripts\python.exe -m pytest tests/test_c7_hamilton.py `
  tests/test_c7_hamilton_causal.py tests/test_c7_hamilton_regime_recovery.py `
  tests/contract/test_ct7_simulator_consistency.py -q

# Mechanical invariants and research-artifact verification
.\.venv\Scripts\python.exe scripts/check_invariants.py
.\.venv\Scripts\python.exe scripts/verify_research_artifacts.py

# Re-probe every audit finding (A01-A14) against the current checkout
.\.venv\Scripts\python.exe scripts/reverify_audit_findings.py

# FIX01/FIX02 acceptance: full supported replay, both clock policies (~4 min)
.\.venv\Scripts\python.exe scripts/verify_fix01_fix02.py

# Archive replay and dashboard
.\.venv\Scripts\python.exe scripts/run_prototype.py --from 2020-01-01 --to 2020-04-30
.\.venv\Scripts\python.exe scripts/run_prototype.py --from 2024-10-01 --to 2024-11-30 --decision-clock standard_1530
.\launch_prototype.ps1          # http://127.0.0.1:8512
```

Never run the expensive partition after a UI-only edit.

## 4. Evidence paths

| Artifact | What it holds |
|---|---|
| `docs/evidence/REVERIFY-2026-10-16.json` | every audit finding re-probed; `fixed` / `present` / `static-check` |
| `docs/evidence/FIX01-FIX02-REPLAY-2026-10-16.json` | full 5361-point replay under both clock policies, retry determinism, COVID-window delta |
| `docs/decisions/DR-01-2026-10-16-session-clock-and-absence.md` | session calendar, as-of selection, declared absence, and the COVID-window correction |
| `docs/decisions/DR-02-2026-10-16-run-sealing-and-command-results.md` | run lifecycle, immutable reports, command/event separation, classification policy |
| `docs/decisions/DR-03-2026-10-16-coherent-reads-and-request-lifecycle.md` | coherent reads, scoped caching, recoverable requests, context-bound results |
| `test-results/slice-p1-core.xml`, `test-results/slice-p1s3-core.xml` | core partition JUnit (gitignored) |
| `docs/evidence/DEVELOPMENT-AUDIT-2026-10-16.json` | the original audit's baseline — **unchanged** |

Preserved and untouched: `prototype_runs/seraph.sqlite` (the pre-change COVID
replay `77cc8a2f…`), `research_data/`, `research_results/`,
`source_original_manifest.json`, all hashed experimental records.

New local stores (gitignored): `prototype_runs/fix01-full-replay.sqlite`,
`prototype_runs/fix01-covid-window.sqlite`.

## 5. What changed in the code

| File | Change |
|---|---|
| `seraph/market_calendar/{__init__,sessions}.py` | **new**: `TradingSession`, `SessionCalendar`, `DecisionClock`, declared `SPECIAL_SESSIONS` registry with self-checking evidence |
| `seraph/orchestration/prototype.py` | session-aware decision timestamps; as-of vintage selection; explicit absence contract; withheld-vintage recording; sealed finish with `requires_report` |
| `seraph/orchestration/run_store.py` | run lifecycle, range/schema/seal enforcement, exact-date-set verification, immutable report revisions, `action_commands` table, additive migrations |
| `seraph/orchestration/original_execution.py` | session-close cutoff instead of a fixed 15:30; declared absence on every pillar |
| `seraph/reconciliation/time_clock.py` | optional `session_hours`; multi-window sessions. Default behaviour unchanged |
| `seraph/reconciliation/kalman.py` | optional `session_hours` passthrough |
| `seraph/features/jump_extraction.py` | `QuantileBins`, `fit_quantile_bins`, `apply_quantile_bins`, `trailing_quantile_bucket`, `UNDETERMINED`; `state_variable()` requires a declared fitting basis; `_bucket` deprecated as non-causal |
| `seraph/features/__init__.py` | exports the new bin API |
| `scripts/fit_hawkes.py` | 20-day trailing state bins; undetermined events counted, not pooled |
| `tests/contract/test_ct3_jump_sufficiency.py` | declares a `train_prefix` basis |
| `seraph/universe/instrument_type.py` | `classification_status()`, `ClassificationUnavailable`; `is_equity()` raises instead of accepting everything |
| `seraph/universe/constructor.py` | `MISSING_DEPENDENCY` when classification is unavailable; opt-in `allow_unclassified` degraded mode with a `PARTIAL_COVERAGE` warning |
| `seraph/ingestion/hawkes_universe.py` | refuses to pool an unclassified basket |
| `seraph/universe/__init__.py` | exports the new classification API |
| `scripts/run_prototype.py` | `--decision-clock {session_close,standard_1530}` |
| `seraph/dashboard/datasource.py` | one coherent `as_of` bundle; stale/unavailable component labelling; `CacheScope` with identity slots; `st.cache_data` actually applied |
| `seraph/dashboard/prototype_app.py` | scoped `(store, run, role)` caching, invalidated after a write; error results carry their context |
| `seraph/dashboard/console_backend.py` | `result_matches()`; `dispatch()` stamps every result with `{run_id,date,role,request_id}`; `project_run()` discards non-matching results and reports why |
| `seraph/dashboard/console_component/bridge.js` | in-flight record, bounded timeout, same-id retry, duplicate suppression, visible status line, draft capture/restore, context-checked results, conditional test seam |
| `pyproject.toml` | `[tool.setuptools.package-data]` so the console's HTML/JS/CSS and the Three.js licence ship in a wheel; `.bak`/`.broken` excluded |
| `scripts/verify_fix01_fix02.py`, `scripts/reverify_audit_findings.py`, `scripts/verify_packaging.py` | **new** verification scripts |
| `tests/test_fix01_session_clock.py`, `test_fix02_absence_semantics.py`, `test_fix03_fix08_persistence.py`, `test_fix09_classification_policy.py`, `test_fix10_fix11_transport.py` | **new**, 77 tests |
| `tests/js/bridge_harness.mjs` | **new** Node harness that runs the unmodified bridge against stub DOM/timer/postMessage globals and drives the real request lifecycle |
| `tests/test_fix04_causal_state_bins.py` | **new**, 14 tests (91 new tests in total) |
| `docs/decisions/DR-04-…-causal-state-bins.md` | **new** decision record |
| `tests/test_prototype_integration.py`, `test_console_backend.py`, `test_prototype_viewer.py` | fixtures updated for the declared-absence and point-schema contracts |

`seraph/shared_types/` was **not** modified. No `WarningCode` or error Literal
was widened; the existing `PARTIAL_COVERAGE` code and `MISSING_DEPENDENCY`
variant carry the new conditions. No UI panel was removed and no preview was
deleted.

## 6. Open decisions and external inputs

Blocking the paths named, and nothing else:

| Needed | Blocks | Note |
|---|---|---|
| Source PostgreSQL (5433/5434 still refusing connections) | `DATA02` census, `PIPE01` fresh execution, real-corpus density tests | Synthetic persistence, contracts, identity abstractions, news fixtures and case logic are **not** blocked |
| Docker/Linux engine for a disposable Timescale instance | `DATA01`, the 13 skipped DB tests | Needs a guarded `seraph_test_*` database with `seraph_test_guard(token)`; that marker must never enter a source or research database |
| OIDC provider configuration | `AUTH01` round-trip verification only | Grants, tenancy and their deterministic tests can be built now |
| Authorized news source + rights (decision D-A) | `NEWS01` live acquisition | Registry schema, dedup, extraction, exposure and replay logic can be built against fixtures |
| Authorized institution submissions | `CASE02` | `CASE01` and `CASE03` are not blocked |
| **FR35 Table B fold definition** (decision D-G) | `FIX05`, then `FIX06`, `VAL03` | **Scientifically unresolved.** SPEC FR35 says two pre-Hawkes epochs; `configuration_list()` uses all six. The xfail test deliberately still fails. Do not pick one to make it pass |
| Deployment audience (decision D-F) | `OPS03` acceptance criteria | |
| Official exchange session calendar | replacing the `declared` session registry | Every registry entry is corroborated by an in-repo observation, but none is verified against an ingested exchange notice |

## 7. Known limitations of this checkpoint

- **No browser verification was performed this session.** The canonical console
  was rendered through Streamlit `AppTest` against a real 81-point archive run
  (no exception, selectors populated, all three role projections built), and
  `bridge.js` was driven for real in a Node VM. Neither is a pixel check: no
  visual capture of the globe or console was taken, so there is no before/after
  image for later comparison. Port 8512 was listening throughout; that alone
  proves nothing about rendering.
- **The expensive Hamilton/policy partition did NOT complete.** It was started
  at the Phase 1 gate and the background process was stopped after roughly 12
  of its 34 tests; no JUnit file was written. **This is an open verification
  gap**, not a pass. Re-run it before any release claim:

  ```
  pytest tests/test_c7_hamilton.py tests/test_c7_hamilton_causal.py \
         tests/test_c7_hamilton_regime_recovery.py \
         tests/contract/test_ct7_simulator_consistency.py -q \
         --junitxml=test-results/slice-p1-models.xml
  ```

  Expect ~18–30 minutes. The argument that it should pass — no numerical model
  was changed, and C8's clock gained only an optional, default-off parameter —
  is an argument, not a result.
- **`QA03` is now verified**, not merely assessed: `pyproject.toml` declares
  package data, and `scripts/verify_packaging.py` builds a wheel, installs it
  into a throwaway venv and renders the console from `site-packages`
  (`docs/evidence/PACKAGING-2026-10-16.json`).
- **Data finding, recorded not patched:** `research_data/market_snapshot.parquet`
  has no row for **2020-02-01**, although the intraday Hawkes corpus evidences
  a session that day. Carried into the Phase 5 source census; the snapshot is
  hashed research evidence and was not edited.
- **The COVID-window CSRS series changed** on 11 of 81 dates (max 0.0026, no
  mask or alert-level change) because a previously-dropped real observation is
  now seen. This is a correction, documented in DR-01, and it changes no
  scientific conclusion. The original run is preserved.
- Nothing here establishes predictive skill. The original advance-warning claim
  remains unestablished, and the Astra future-loss result is still within its
  descriptive interval of the volatility baseline.
