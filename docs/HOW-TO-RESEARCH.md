# Open the independent SERAPH research viewer

This viewer is part of the separate **SERAPH-Research** project. It does not
change the original project, connect to its database, fit a model, or send
alerts. It reads saved experiment artifacts from local files.

From PowerShell in this experimental project directory:

```powershell
.\launch_research.ps1
```

Open `http://127.0.0.1:8511` if the browser does not open automatically. The
server binds only to the loopback address. Stop it with Ctrl+C in the launching
terminal. There is no authentication layer, so keep the local-only binding.

An alternate run directory or port can be selected explicitly:

```powershell
.\launch_research.ps1 -Results research_results/v1_verified -Port 8512
```

The launcher uses this project's `.venv/Scripts/python.exe`; it never uses
the original Downloads project's interpreter. If the environment is missing,
set up the experimental environment using the project README before launch.

The default saved inputs are:

- `research_results/v1_verified/summary.json`: protocol, provenance, metrics,
  event-by-event warning records, limitations, and acceptance assessment.
- `research_results/v1_verified/predictions.parquet`: chronological forecasts and
  their recorded thresholds, fit status, and training endpoints.
- `research_results/v1_verified/features.parquet`: dated pillar features.

The experiment runner is `scripts/run_prediction_experiment.py`; use its
`--help` and the project README for the data preparation and execution options.
Opening the viewer before a run completes shows explicit missing-artifact
messages rather than synthetic scores. Refresh after the experiment finishes.

## Interpret the display

The default candidate is `combined` on `onset15`. Select another fixed
candidate to inspect baselines and pillar ablations. Candidate selection is
an inspection control, not a validated model-selection rule.

- **Onset15:** probability of a labelled crisis beginning within the next
  15 trading sessions, under the recorded event-label protocol.
- **Loss10_15:** probability that the research market series falls at least
  10% from the current close at some point in the next 15 trading sessions.
- **CSRS:** the original diagnostic composite; it is not converted into a
  probability by this viewer and remains a distinct output.

Choose a historical decision date to view the saved after-close forecast and
the pillar features on exactly that date. Later feature rows are not used to
fill missing readings. The three cards retain their own units: daily Hawkes
event intensity, RMT leading-eigenvalue share, and Hamilton next-session
highest-variance-regime probability. The Hamilton quantity is not a market
crisis probability.

A saved infinite alarm threshold means **abstention**, not zero risk. Missing
probability/threshold values remain unavailable; no substitute forecast is
invented. The training endpoint and fit status are shown next to the result.

The retrospective tables cover the full saved evaluation. They contain future
outcomes relative to a selected historical date and are explicitly separated
from the historical readouts. Compare models within the same target. A
loss-target warning near a crisis does not itself establish pre-onset skill.
Read the false-alarm record, event labels, coverage, and limitations alongside
the warning dates; the COVID row alone is not an acceptance test. The main
comparison table uses saved `metrics_common` results on common forecast
coverage within each target. Candidate-specific alarm totals and full-summary
own-coverage metrics may cover different dates.

The market series is the experiment's equal-weight geometric-return research
index of available universe members, not a tradable portfolio or the NIFTY
index. Consult the dataset manifest and limitations before interpreting it.

All displayed results remain experimental historical research. A causal replay
does not remove retrospective research choices or establish future performance.
No view is a live alert service, a production risk engine, or a claim of proven
crisis forecasting.

## Optional public-event watch

When the chosen results directory contains `hazard_watch.parquet` and
`hazard_summary.json`, the viewer adds a separate public-event watch section.
It displays the saved state at exactly the selected date, the public trigger
identifiers, and separate states for the external rule, the `combined/onset15`
model alarm, and their combined watch. Changing the candidate selector does
not change the source model used by this independently saved watch.

This is a retrospective hypothetical rule that opens a fixed temporary watch
after a public emergency declaration. It is not a probability, does not alter
the forecast probability, and cannot establish that the original three-pillar
system predicted COVID. A public trigger's contribution must remain separately
attributed. Inspect the complete source register, stated timing rule, false
alarms, and event outcomes; a successful retrospective COVID trigger alone is
not sufficient evidence of general predictive utility.

The entire section is optional when neither file exists. Incomplete artifacts,
missing historical rows, or false/missing coverage flags are reported as
unavailable, never as inactive. `external_assessable` controls the external
reading; `combined_assessable` controls the combined-model and combined-watch
readings. Precoverage periods cannot appear to be successful calm forecasts.
