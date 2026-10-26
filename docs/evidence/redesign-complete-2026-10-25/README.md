# Redesigned frontend — complete, 2026-10-25

All six screens, captured from `.\launch_redesign.ps1` on port 8520 while
Classic ran on 8512. Viewport 1680×1150, dark scheme.

| File | Screen | What it evidences |
|---|---|---|
| `01-forecast-warning-state.jpg` | Forecast | NO WARNING with its reason, refresh-allowance line, UNVALIDATED banner before any number is interpreted, probability 6.92% / threshold 12.52% / horizon 15 sessions, forecast ledger id |
| `02-forecast-calibration.jpg` | Forecast | Calibration scatter with the perfect-calibration diagonal — this installation over-predicts and the chart shows it. One empty bin is named as not drawn, not plotted at zero |
| `03-news-signal-rail.jpg` | News intelligence | Live-acquired events: tariff determinations, USGS earthquakes, POWERGRID capacity expansion. **Classic's `news_only_panel` shows 0 events for this same store** (see parity doc §6) |
| `04-news-sector-routes-assets.jpg` | News intelligence | Sector exposure routes with "**not** an estimate of contagion, it carries no magnitude", and the registered-assets table. F2 palette throughout — no pillar colours |
| `05-workspace-portfolio-created.jpg` | Workspace | A portfolio created through the UI; it persisted to `prototype_runs/workspace.sqlite` as `pf_46bacb5f48cf4e5d` |
| `06-evaluation-withheld-retail.jpg` | Evaluation | Retail is refused by the **backend**, with the reason |
| `07-evaluation-institutional.jpg` | Evaluation | Pre-registered design chips, 0 measured / 152 unavailable / 152 not publishable, the "NOT A SINGLE RANKING" comparability warning, Table A with every absence named |
| `08-health-schedule-checks.jpg` | Health | Installation health, daily schedule with live task state, "a check with no data reads as never_succeeded or never_run, never as ok" |
| `09-health-acquisition-marketjobs.jpg` | Health | News acquisition owner + worker liveness + per-source outcomes (1 of 21 failing), market jobs steps, configured stores |
| `10-workspace-regulator-case.jpg` | Workspace | A regulator case opened through the UI — `triage · v1` — with evidence / decision / status / export controls |
| `11-overview-active-portfolio.jpg` | Overview | A portfolio activated in Workspace reaching the Overview, with the honest "this portfolio has no holdings snapshot yet" |
| `12-classic-unchanged-8512.jpg` | **Classic** | Classic re-rendered on 8512 while the redesign ran on 8520 — identical to its baseline |

## Reproducing

```powershell
.\launch_prototype.ps1        # Classic, 8512
.\launch_redesign.ps1         # Redesigned, 8520
```

## End-to-end checks behind these captures

- Portfolio created in the UI → row in `workspace.sqlite`
  (`pf_46bacb5f48cf4e5d`, owner `usr_0c60bba81a9f43e0`, created
  `2026-10-25T02:43:35+05:30`).
- Regulator case opened in the UI → `triage · v1`.
- Evaluation: `permitted False` for retail, `True` for institutional.
- RBAC: a retail payload does not *contain* institutional fields.
- 36 of the 37 copied Classic files re-hash byte-identical to
  `../frontend-baseline-2026-10-24/`. The exception is
  `seraph/dashboard/prototype_app.py`, which the session that owns it changed
  **after** these captures, to fix the `news_only_panel` defect recorded in
  `docs/REDESIGN-FEATURE-PARITY.md` §6. That is an intended fix by its owner,
  not drift from this work: nothing here writes to Classic, and the baseline
  remains the record of what Classic looked like before the redesign began.

## Added 2026-10-25 (gap closure)

| File | Shows | What it evidences |
|---|---|---|
| `13-risk-console-globe.jpg` | Risk console with the F2 layer off | The embedded component — globe, eight-view nav, sector stress — opening in ~9 s, with the banner correctly reporting the illustrative map layer as FABRICATED |
| `14-risk-console-news-attached.jpg` | Risk console with F2 attached | The news map layer, inferred-mechanism panel and "over all 2128 eligible events, not just the page shown" |
| `15-risk-console-tools.jpg` | The TOOLS view | Ad-hoc portfolio coverage, and the operation-status panel. The FR49 action journal and the shock/policy simulators appear here at institutional/regulator |
| `16-sector-basis-retrospective.jpg` | Overview on the **retrospective** sector basis | The toggle surfaces genuinely different data — measured ratios for aluminium, auto_components, pharmaceuticals, solar and steel that did **not** exist at the 2020-04-30 decision — under `analysis mode retrospective_archive`, a cutoff of 2026-10-25, and the engine's own note that it "does not change the historical score or prove advance warning" |

Live revision polling is evidenced by page text rather than a capture (it is a
2-second fragment): the live panel reads `polling every 2s`, `runtime revision
9fef38f7a257`, `last moved 12:31:31`, with the dial unfilled and "no decision
has been committed in this runtime" — a polled absence is still an absence.
