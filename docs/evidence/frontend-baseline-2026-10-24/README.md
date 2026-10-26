# Classic frontend baseline — 2026-10-24

Captured **before** any work on the Redesigned frontend began. The repo carries
substantial uncommitted work, so a git ref alone would not reconstruct this
state: the files themselves are copied here.

## Baseline revision

- `git rev-parse HEAD` → see `BASELINE-REVISION.txt` (`9a792b506aa7192f8c6c3f7119396b3a40e3d5ac`)
- Working tree at capture time → `BASELINE-GIT-STATUS.txt`
- Uncommitted tracked diff at capture time → `BASELINE-UNCOMMITTED.diff`

The copied files under `seraph/` and `launch_prototype.ps1` are the **working
tree** as it stood, i.e. HEAD plus the uncommitted diff. They are the ground
truth for this baseline, not HEAD.

### Hashes of the files the redesign must not disturb

| File | sha256 |
|---|---|
| `seraph/dashboard/prototype_app.py` | `c0645b2367f60869486b3c8601a42db0e255533cc881c1ccbbc28c1823bd37af` |
| `seraph/dashboard/console_backend.py` | `ca68a8df49d00addee29fdafbd389705ce9055fd28901eba5e87ff9de95a72c0` |
| `seraph/dashboard/news_view.py` | `5f87ba30db532fd41365f1d93f9d48ef120bac8ca02641b63d41c007d586e746` |
| `seraph/dashboard/console_component/bridge.js` | `30dbd98d042357feba86ee228d260deadc9ef4f8ea084da3574bbe059e94a896` |
| `launch_prototype.ps1` | `eff3953f736ebd8321d289cd9f4fb3a88368d970210321e654b734103ddd4020` |

Re-check at any time with:

```bash
sha256sum seraph/dashboard/prototype_app.py seraph/dashboard/console_backend.py seraph/dashboard/news_view.py seraph/dashboard/console_component/bridge.js launch_prototype.ps1
```

## Launching Classic — unchanged, and still the default

```powershell
.\launch_prototype.ps1
```

Serves on **http://127.0.0.1:8512**. Starts, in this order: the market jobs
(`scripts/run_market_jobs.py`, backgrounded), one owned market runtime
(`scripts/run_live.py --stay-running`), one supervised news worker
(`scripts/news_supervisor.py`), then Streamlit on
`seraph/dashboard/prototype_app.py`.

Switches: `-NoNewsWorker`, `-NoMarketJobs`, `-NoLiveRuntime`, `-Port`,
`-Store`, `-NewsStore`, `-LiveStore`, `-NativeHawkesConfig`.

Equivalent bare launch (what `.claude/launch.json → seraph-console` does, on
port 8513; the app asks for its own news worker on first page view):

```bash
.venv/Scripts/python.exe -m streamlit run seraph/dashboard/prototype_app.py --server.address 127.0.0.1 --server.port 8512 --server.headless true
```

## Screenshots

Captured from the bare launch above on port 8512 with `SERAPH_NEWS_WORKER=0`,
viewport 1600×1200, dark scheme. The flag is set only so the capture does not
kick off network acquisition; it changes one status line ("not acquiring") and
nothing else on screen.

| File | Shows |
|---|---|
| `screenshots/classic-01-prediction-top.jpg` | Title, caption, PREDICTION & EARLY WARNING open: forecast ledger id, NO WARNING banner, predicted probability 6.92% / threshold 12.52% / horizon 15 sessions, refresh-allowance line, UNVALIDATED banner, "What is predicted", "Measured — the three pillars at this close" table |
| `screenshots/classic-02-calibration-forecast.jpg` | Warning policy, Realised history (Brier 0.0634, AUC 0.637, base rate 6.84%, 1.01 false episodes/yr), Calibration table, "Forecast against its warning threshold" line chart |
| `screenshots/classic-03-alarms-live-runtime.jpg` | Most recent alarm episodes table, collapsed NEWS ACQUISITION / MARKET JOBS, LIVE RUNTIME open with live/replay/demo radio, LATEST SCORE = "no decision has been committed in this runtime…", WORKER HEALTH json |
| `screenshots/classic-04-run-selection-console.jpg` | Run selector, Historical decision date 2020-04-30, Sector analysis basis radio, News clock radio, News page, MEASURED SECTOR ACTIVITY — FR14, MY WORKSPACE / EVALUATION / HEALTH expanders, and the custom console component with its eight views |

## Frontend inventory (entry points and wiring)

| File | Lines | Role |
|---|---|---|
| `launch_prototype.ps1` | 130 | Canonical launcher. Market jobs + owned market runtime + news supervisor + Streamlit on 8512. |
| `seraph/dashboard/prototype_app.py` | 1510 | The Streamlit app. `main()` renders, in order: PREDICTION & EARLY WARNING, NEWS ACQUISITION, MARKET JOBS, LIVE RUNTIME, then run/date/role selection, sector basis, news clock/page, MEASURED SECTOR ACTIVITY, MY WORKSPACE, EVALUATION, HEALTH, and finally the custom console component. |
| `seraph/dashboard/console_backend.py` | 1152 | Payload assembly. `project_run()` is the one call that builds the browser payload. `news_branch()` carries the **explicit allow-list** comment: a field computed but not named in that dict never reaches the screen. Also `liveness_of`, `sector_analysis`, `market_flow`, `_history_with_benchmark`, `dispatch`, `experiment_surface`, `health_surface`, `prediction_surface`. |
| `seraph/dashboard/gateway.py` | 232 | RBAC at the transport boundary. `ROLE_FIELDS` / `build_view()` — a retail payload does not *contain* institutional fields, it is built by projection onto the role's allowed set. |
| `seraph/dashboard/news_view.py` | 735 | `build_news_payload()` — the F2 news channel surfaces, source coverage, freshness, manifest, temporal policy. |
| `seraph/dashboard/globe_payload.py` | 706 | `build_globe_payload()` — geometry-bound news/exposure layer for the component. |
| `seraph/dashboard/console_component/` | 3952 | The custom Streamlit component (Three.js r128). `index.html` declares eight views: `map`, `console`, `feed`, `pillars`, `exposure`, `forecasts`, `tools`, `method`. `bridge.js` is the payload→DOM bridge; `news_layer.js`, `preview_pillars.js` are layers. |
| `seraph/dashboard/workspace_service.py` | 170 | `active_portfolio()` — resolves a saved portfolio to holdings + overlay at a decision time. |
| `seraph/dashboard/current_reader.py` | 250 | `read_current()` / `revision()` — the live runtime read. `live`/`replay`/`demo` is a chosen mode with **no silent fallback**. |
| `seraph/dashboard/news_service.py` | 180 | `ensure_worker()` — stands aside when `seraph/news/worker_lock.py` reports a supervisor already holds the store lock. This is what makes two frontends safe. |
| `seraph/dashboard/app.py` | 399 | The older research dashboard (port 8501). Not part of the console. |
| `seraph/dashboard/scenario_ui.py` / `institution_ui.py` / `network_ui.py` | 163 / 58 / 40 | Panels called from `main()`. `network_ui` is the **pending F07 directed network**. |

## What the payload actually contains (measured, not assumed)

`project_run(point, manifest, points, role='institutional')` on the newest
complete archive run returns these top-level keys:

```
context cutoff date discarded_result flow history limitations liveness
mask mode news pillars portfolio portfolio_context predictions report
result role run_id sector_observations timestamp view warning_status
```

`view` (institutional projection): `alertLevel ciLower ciUpper csrs
effectiveWeights explanation maskDegraded pillarScores playbook
portfolioExposurePct reconciliationMode regimeProbabilities role sectorFlags
shapley spectral ts variance`.

Values on run `37bccf32974201f0`, decision `2020-04-30T15:30:00+05:30`:

- `csrs` 0.9899174584632234, `alertLevel` "red", `ciLower` 0.7388, `ciUpper` 1.0, `variance` 0.01641
- `mask` `[false, true, false]` in `PILLAR_ORDER = ["hawkes", "rmt", "hamilton"]` → **only RMT entered the composite**; `maskDegraded` true
- `shapley` `{hawkes: 0.0, rmt: 0.98992, hamilton: 0.0}` — these sum to the CSRS, **not to 1**
- `pillarScores.hamilton.value` `null`, `score_eligible` false, reason "regime support unvalidated; diagnostic only, existing exclusion preserved"
- `pillarScores.hawkes.value` 0.10537, `score_eligible` true, but masked out of this composite
- `history` → 81 rows `{date, csrs, benchmark_close, benchmark_return, benchmark_available}` plus `series` (NIFTY 500 official NSE close), `units` (**two different units**), `coverage`, `representativeness` (correlation 0.101, explicitly "not a validation result")
- `liveness` → `is_live` false, headline "NOT A CURRENT MARKET READING", 5 reasons, age 3,410,346 minutes
- `flow` → `available: false` with reason (no FII/DII print ingested)
- `sector_observations` → `available: false` with reason and `blocked_by`
- `news` → `absent` when no store is passed; `connected` / `empty` with the real store

Live runtime (`prototype_runs/live.sqlite`), both `live` and `replay` modes:
`decision_id` null, reason "no decision has been committed in this runtime.
Asking for live does NOT fall back to an archive run". Worker health: never
committed a pass.

`prediction_surface()` is available and current: as_of 2026-10-22, probability
0.0692, threshold 0.1252, level `no_warning`, `validation.status`
"unvalidated".

`health_surface()` status "failing": 1 failing source, 13 stale, 10 ok.

## Restoring Classic

Nothing to restore. The redesign adds only new files
(`seraph/dashboard/redesign/**`, `launch_redesign.ps1`) and edits none of the
files listed above. `.\launch_prototype.ps1` is unchanged and remains the
default. If a file above ever needs restoring, copy it back from this
directory.
