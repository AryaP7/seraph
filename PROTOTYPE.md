# SERAPH integrated historical prototype

Work in `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`.
No commit or push is authorized by the integration task.

## Reproduce the demonstration

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-research.lock.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
.\.venv\Scripts\python.exe scripts/run_prototype.py --from 2020-01-01 --to 2020-04-30
.\launch_prototype.ps1
```

Open http://127.0.0.1:8512. Select the persisted run and historical decision
date. The default range deliberately demonstrates the COVID period; metrics
on that selected interval are not a new validation experiment or a headline
measure of general predictive performance. Use any available interval ending
no later than 2026-08-21. No network or PostgreSQL access is needed in archive mode.

Optional `--holdings path/to/holdings.json` accepts actual supplied holdings:
an array of objects with symbol, quantity, value and sector. No sample portfolio
is silently supplied. Holdings are current inputs, not point-in-time history.
With no measured sector flags, the overlay reports uncovered exposure. Local
run databases can contain portfolio information and are gitignored.

## What actually executes

The command verifies the saved snapshot, model-code and prediction-artifact
hashes, loads the historical observations, and replays the existing C8 filter
and C9 scoring function chronologically from the beginning of the snapshot.
It persists only the requested interval. C11 produces explanations and the
coverage-aware portfolio result. The dashboard reads complete runs from one
SQLite store; it never joins unrelated latest rows from different tables.

Original Hawkes, RMT and causal TVTP Hamilton diagnostics are **reused fitted
artifacts**, not freshly fitted in this mode. The daily Astra variants and
future-loss/onset predictions remain separate. Saved outcome labels are never
passed to inference; retrospective comparisons are computed afterwards on
common dates per target, and stored in a separate report.

Hamilton's original research archive is explicitly NOT_PRODUCTION. Its existing
scientific unavailability decision is retained: diagnostics are displayed but
not promoted into fusion. Original CSRS uses the existing lambda_1/N research
adapter, equal uncalibrated weights, uniform xi and provisional .5/.75 levels.
Its repaired conditional uncertainty is not a loss-probability interval.
All missingness, source timestamps, stale observations and degraded masks are
reported. None of this establishes predictive skill or satisfies unresolved
FR18/FR35 scientific decisions.

## Identity, persistence and retries

A run ID hashes the input hashes, code versions, interval, holdings and stated
configuration. Repeating the same command with unchanged inputs produces the
same ID and rows. A changed result under an existing ID is rejected. Interrupted
runs remain incomplete; retry deterministically replays the inputs and verifies
already saved points before completing. This is replay-based recovery, not a
low-latency online model checkpoint.

`prototype_runs/seraph.sqlite` is **local prototype storage**, separate from
PostgreSQL E1-E14. The C11 action log is restored from its immutable event
records. Mutations are serialized in a SQLite transaction, deduplicated by
request ID, and preserve revisions and retractions. SQL triggers reject journal
updates/deletes through normal database operations. Role selection is a local
demonstration convenience, not authentication. Database owners can still alter
the database. No regulatory immutability, OAuth, NFR26 compliance or PostgreSQL
E12 durability is claimed.

## Fresh original-model endpoint: requires real source data

```powershell
# Set SERAPH_SOURCE_DB_DSN privately to the existing source database.
.\.venv\Scripts\python.exe scripts/run_prototype.py --source-date 2020-02-19
```

This opt-in path opens a read-only repeatable-read transaction, bounds raw
queries by the decision timestamp, prepares date-aligned C4 observations,
and invokes the original RMT, pooled intraday Hawkes and causal TVTP Hamilton
implementations. It does not write to E1-E14 or substitute cached results when
the source fails. Rebuilding the original Hamilton observations can be expensive.

This is a **fresh diagnostic endpoint**, not the completed fresh-history route:
it has no chronological ECDF warmup across fresh original estimates and therefore
withholds its composite. It does not refit Astra forecasts. Fresh source execution,
PostgreSQL integration, a complete fresh-original replay and online ingestion
remain unverified until the source service is available and the path is exercised.
The archive demonstration must not be represented as proving those stages.

## Worktree integration and correctness boundaries

`integration_worktree_manifest.json` records the source and previous-main hashes
of the C2/C11 files copied into main. Source worktrees were not edited. Existing
portfolio, action-log, gateway, fixtures and tests were reused.

C1 ingestion updates now exclude C4-owned E1/E4 fields and C3-owned E3 membership.
C2 macro refresh supplies only successfully fetched fields; failed sources cannot
null stored values, while actual published gaps remain explicit nulls. This is
an atomic SQL update-column policy, not a read-merge workaround. No shared schema
or scientific contract was changed. Existing insert payloads remain supported.

The C4 observation builder now aligns return columns by dates and excludes
stale last observations. Previously stored C4/Hamilton rows were not regenerated.
Full-history state-variable quantiles remain a legacy limitation; the prototype
does not claim that path is causally validated. The fresh Hawkes path uses the
existing pooled count estimator, not those state bins.

## Safe tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_prototype_integration.py tests/test_prototype_viewer.py -q
```

The suite no longer inherits an application `SERAPH_DB_DSN`. By default database
tests are disabled. Database-writing tests require an explicitly provisioned
disposable database named `seraph_test_*`, `SERAPH_TEST_DB_DSN`, and
`SERAPH_TEST_TOKEN`. Before any test DDL/DML, a read-only check requires the
connected database to contain `seraph_test_guard(token text)` with that token.
Provision this marker **only in a new disposable test database**. Never place
it in source/research databases. Test results with PostgreSQL skipped are not
live integration evidence. CT-3's real-corpus investigation remains separate.

## Remaining scientific work

Preserve the original evaluation and negative results. Next predictive work is
point-in-time source/vintage improvement, fixed chronological evaluation and
prospective shadow forecasts against the existing baselines—not tuning the
integration demonstration to obtain a better number.

## Verified integration handoff (2026-10-16)

- Core regression: **472 passed, 13 skipped, 1 expected failure** in 102.14s.
  JUnit evidence: `test-results/prototype-core.xml`.
- Focused prototype persistence, alignment, ownership, missingness, cutoff,
  action history and Streamlit tests: **12 passed**.
- The unchanged expensive Hamilton and policy-simulator suites were excluded
  from this regression; this is not a claim that every repository test ran.
- All five mechanical invariants and `git diff --check` passed.
- Real archived COVID-period replay persisted **81 daily points**. An identical
  rerun reproduced the same run ID and all point payloads. Streamlit AppTest
  rendered the actual saved run without exceptions. The running localhost
  dashboard health endpoint returned `ok`.
- Verified run ID:
  `77cc8a2fb747507a553169669d8b97b78d1b1f92eb1d7698661969525a769fcd`.
- All 15 integrated source files remained unchanged in their original worktrees.
- PostgreSQL source ports 5433/5434 remained unreachable and Docker's Linux
  engine pipe remained unavailable after starting Docker Desktop. Thirteen
  database-dependent tests were skipped. Fresh model execution and full raw-data
  integration have **not** passed verification. No source database was mutated.
- No commits, pushes, merges or rebases were performed.

Core regression command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests --ignore=tests/test_c7_hamilton.py --ignore=tests/test_c7_hamilton_causal.py --ignore=tests/test_c7_hamilton_regime_recovery.py --ignore=tests/contract/test_ct7_simulator_consistency.py -q --junitxml=test-results/prototype-core.xml
```


## Restored original console and role tools (2026-10-16)

The original globe/console layout is now the canonical frontend. The initial
simplified connected viewer was superseded. Original news, sector, geography,
asset, price, weather and exposure previews are preserved with FABRICATED tags;
news estimation is separate from SERAPH pillar computation.

Retail, institutional and regulator buttons request server-projected payloads.
Portfolio inputs, pillar shocks, explicit hypothetical regime paths and durable
regulator actions call the existing C11 implementations. Backtest opens the saved
comparison without refitting. The original `seraph/dashboard/app.py` entry point
opens the same integrated console. See [full feature coverage and limitations](docs/FRONTEND-INTEGRATION.md).

Latest integration regression: 163 passed; five mechanical invariants passed.
Browser verification confirmed original globe rendering, institutional role
switching, saved CSRS display, and an actual Python shock-simulator round trip.
