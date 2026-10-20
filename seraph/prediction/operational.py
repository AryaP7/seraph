"""The operational prediction and early-warning path (C9/C10 -> C12).

SERAPH is a risk prediction and early-warning system, and until now its
prediction engine existed only as backend code, a CLI experiment and a
separate read-only artifact viewer. This module is the path the main
application uses: one function that runs the **actual** engine on the actual
market snapshot and returns the current forecast, the current warning state
and the provenance of both.

It does not reimplement anything. `build_pillar_features`, EWMA volatility,
`future_loss_labels`, `walk_forward_predict` and `calibrate_alerts` are
called exactly as the frozen experiment calls them, with the same declared
protocol — `assert_matches_experiment()` fails if the operational feature set
ever drifts from the experiment's `combined` candidate, so the two cannot
silently diverge.

**Three different claims, kept apart** (and the console renders them under
three separate headings, because conflating them is how a research
instrument becomes an overconfident one):

* **measured** — pillar feature values at the decision date, and realised
  metrics over matured history. These are observations and arithmetic.
* **predicted** — one probability: that the market index falls 10% or more
  from the decision close at any close within the next 15 sessions. A model
  output, point-in-time, fitted only on labels whose horizon had already
  elapsed.
* **warning** — whether that probability crossed a threshold calibrated from
  PAST out-of-sample scores under a declared budget. A policy decision, not a
  proof that the budget will hold in future.

**What this is not.** No advance-warning skill has been demonstrated.
AMENDMENT-03 measured Pillar 1 at approximately no skill at every intraday
horizon and reclassified it as a contagion diagnostic; the research run's own
`empirical_acceptance` reads `unvalidated`. `VALIDATION_STATUS` carries that
into every state this module produces, so a reader cannot receive the number
without it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from seraph.prediction.evaluation import (
    AlertConfig,
    alarm_stats,
    calibrate_alerts,
    episode_spans,
    probability_metrics,
)
from seraph.prediction.models import (
    EWMAStudentTForecaster,
    future_loss_labels,
    walk_forward_predict,
)
from seraph.prediction.pillars import PillarConfig, build_pillar_features

#: The frozen protocol. These are the experiment's values, not new choices:
#: a 10% fall from the decision close at any close within 15 sessions.
HORIZON = 15
LOSS_BARRIER = 0.10
FACTOR_COLUMNS = tuple(f"factor_{i}" for i in range(10))

#: The operational model is the experiment's `combined` candidate: EWMA
#: volatility plus one feature from each pillar family. Ablations belong to
#: the research protocol, not to a live warning surface -- showing six models
#: side by side in an operational panel invites choosing the flattering one,
#: which is what D5 forbids.
PILLAR_FEATURES = (
    "hawkes_daily_intensity",
    "rmt_fast_leading_share",
    "rmt_fast_minus_slow",
    "hamilton_daily_next_volatility",
)
OPERATIONAL_FEATURES = ("ewma_volatility",) + PILLAR_FEATURES

#: Which pillar family each operational feature belongs to, so the console can
#: show the three-pillar architecture rather than a flat list of five numbers.
FEATURE_PILLAR = {
    "ewma_volatility": "volatility baseline",
    "hawkes_daily_intensity": "hawkes",
    "rmt_fast_leading_share": "rmt",
    "rmt_fast_minus_slow": "rmt",
    "hamilton_daily_next_volatility": "hamilton",
}

VALIDATION_STATUS = "unvalidated"
VALIDATION_NOTE = (
    "No advance-warning skill, calibration or economic effect size has been "
    "demonstrated. AMENDMENT-03 measured Pillar 1 at approximately no skill "
    "at every intraday horizon and reclassified it as a contagion diagnostic, "
    "and the research replay records empirical_acceptance as unvalidated. "
    "These are honest limitations of a working instrument, not grounds for "
    "treating its output as a validated forecast."
)

#: Fixed reliability bins, declared before the numbers are seen. Quantile bins
#: would move with the forecast distribution and make a miscalibrated model
#: look evenly spread.
RELIABILITY_EDGES = (0.0, 0.02, 0.05, 0.10, 0.20, 0.50, 1.0)


def assert_matches_experiment() -> None:
    """Fail if the operational feature set has drifted from the experiment.

    The frozen experiment script is the record `research_results/` was
    produced under, and it is deliberately not edited to import from here.
    That leaves two declarations of the same list, so this is the mechanical
    check that they agree -- without it, drift would be invisible.
    """
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "run_prediction_experiment.py"
    if not path.exists():                      # an installed wheel has no scripts/
        return
    spec = importlib.util.spec_from_file_location("_seraph_experiment", path)
    module = importlib.util.module_from_spec(spec)
    saved = dict(sys.modules)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.clear()
        sys.modules.update(saved)
    expected = tuple(module.CANDIDATES["combined"])
    if expected != OPERATIONAL_FEATURES:
        raise AssertionError(
            f"operational features {OPERATIONAL_FEATURES} no longer match the "
            f"experiment's combined candidate {expected}")
    if module.HORIZON != HORIZON:
        raise AssertionError(
            f"horizon drifted: operational {HORIZON}, experiment {module.HORIZON}")


def reliability(probability, labels, edges=RELIABILITY_EDGES) -> list[dict]:
    """Predicted probability against realised frequency, on matured labels.

    This is the uncertainty statement a probability forecast actually
    supports. The logistic challenger produces no interval, so reporting one
    would be an invention; what can be reported is whether, historically,
    days it called 5% turned out 5%.
    """
    p = np.asarray(probability, dtype=float)
    y = np.asarray(labels, dtype=float)
    valid = np.isfinite(p) & np.isfinite(y)
    p, y = p[valid], y[valid]
    out = []
    for low, high in zip(edges[:-1], edges[1:]):
        inside = (p >= low) & (p < high if high < 1.0 else p <= 1.0)
        count = int(inside.sum())
        out.append(dict(
            lower=float(low), upper=float(high), count=count,
            mean_predicted=float(p[inside].mean()) if count else None,
            realised_rate=float(y[inside].mean()) if count else None))
    return out


@dataclass
class PredictionState:
    """Everything the console needs, with the three claims kept apart."""
    as_of: str
    generated_at: str
    snapshot: dict
    protocol: dict
    measured: dict
    predicted: dict
    warning: dict
    history: dict
    validation: dict
    series: list = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def _snapshot_frame(snapshot_path: Path):
    import pandas as pd

    frame = (pd.read_parquet(snapshot_path)
             .sort_values("date").reset_index(drop=True))
    if frame["date"].duplicated().any():
        raise ValueError("the snapshot has duplicate decision sessions")
    missing = [c for c in ("date", "market_return", *FACTOR_COLUMNS)
               if c not in frame.columns]
    if missing:
        raise ValueError(f"the snapshot is missing columns: {missing}")
    return frame


def run(snapshot_path, *, pillar_config=None, alert_config=None,
        series_tail: int = 1260) -> PredictionState:
    """Run the actual engine on the actual snapshot. ~25 seconds.

    Every forecast is point-in-time: `walk_forward_predict` refuses labels
    whose horizon has not elapsed by the decision date, and
    `calibrate_alerts` chooses each threshold from past scores and matured
    outcomes only. Nothing here reads a future value to produce a present
    one, which is the property that makes the series replayable rather than
    retrospective.
    """
    from datetime import datetime, timezone

    snapshot_path = Path(snapshot_path)
    frame = _snapshot_frame(snapshot_path)
    pillar_config = pillar_config or PillarConfig()
    alert_config = alert_config or AlertConfig(horizon=HORIZON)

    log_returns = frame["market_return"].to_numpy(float)
    simple = np.expm1(log_returns)
    panel = frame[list(FACTOR_COLUMNS)].to_numpy(float)

    pillars = build_pillar_features(log_returns, panel, config=pillar_config)
    ewma = EWMAStudentTForecaster().predict(simple)

    import pandas as pd

    features = pd.DataFrame(pillars.values)
    features["ewma_volatility"] = ewma["volatility"]

    labels = future_loss_labels(simple, horizon=HORIZON, barrier=LOSS_BARRIER)
    forecast = walk_forward_predict(features, labels,
                                    list(OPERATIONAL_FEATURES),
                                    horizon=HORIZON)
    alerts = calibrate_alerts(forecast.probability, labels, alert_config)

    dates = [str(d)[:10] for d in frame["date"]]
    last = len(dates) - 1
    probability = forecast.probability
    thresholds = alerts["threshold"]
    alarm = alerts["alarm"]

    # --- measured: observations and arithmetic, not model output ---------
    pillar_values = {}
    for name in OPERATIONAL_FEATURES:
        value = float(features[name].iloc[last]) if name in features else float("nan")
        pillar_values[name] = dict(
            value=None if not np.isfinite(value) else value,
            pillar=FEATURE_PILLAR[name])
    measured = dict(
        pillar_features=pillar_values,
        market_return=float(log_returns[last]),
        sessions=len(dates),
        note=("feature values at the decision date, computed from data "
              "available at that close; parameters estimated through t-1"))

    # --- predicted: one probability, with its own provenance -------------
    current_p = probability[last]
    predicted = dict(
        probability=None if not np.isfinite(current_p) else float(current_p),
        horizon_sessions=HORIZON,
        loss_barrier=LOSS_BARRIER,
        definition=(f"probability that the research market index falls "
                    f"{LOSS_BARRIER:.0%} or more from this decision close at "
                    f"any close within the next {HORIZON} sessions"),
        model="combined (EWMA volatility + one feature per pillar family)",
        features=list(OPERATIONAL_FEATURES),
        fit_status=str(forecast.fit_status[last]),
        observed_features=int(forecast.observed_features[last]),
        training_count=int(forecast.training_count[last]),
        train_end_date=(dates[int(forecast.train_end[last])]
                        if forecast.train_end[last] >= 0 else None),
        fitted_at_date=(dates[int(forecast.fitted_at[last])]
                        if forecast.fitted_at[last] >= 0 else None),
        refits=len(forecast.fits))

    # --- warning: a policy decision against a calibrated threshold -------
    current_threshold = thresholds[last]
    if np.isnan(current_threshold):
        level, reason = "unassessable", (
            "no threshold: the calibration window does not hold enough "
            "matured outcomes, so no warning can be issued either way")
    elif np.isinf(current_threshold):
        level, reason = "abstained", (
            "explicit abstention: no finite threshold met the declared "
            "false-alarm budget on recent history")
    elif bool(alarm[last]):
        level, reason = "warning", (
            f"the forecast {current_p:.4f} is at or above the calibrated "
            f"threshold {current_threshold:.4f}")
    else:
        level, reason = "no_warning", (
            f"the forecast {current_p:.4f} is below the calibrated threshold "
            f"{current_threshold:.4f}")

    matured = np.isfinite(labels)
    warning = dict(
        level=level, reason=reason,
        threshold=(None if not np.isfinite(current_threshold)
                   else float(current_threshold)),
        threshold_is_abstention=bool(np.isinf(current_threshold)),
        budget=dict(
            false_episodes_per_year=alert_config.false_episodes_per_year,
            max_alarm_fraction=alert_config.max_alarm_fraction,
            lookback_sessions=alert_config.lookback,
            min_calibration=alert_config.min_calibration),
        calibrations=len(alerts["fits"]),
        note=("the threshold is chosen from past out-of-sample scores and "
              "matured outcomes only. A frozen threshold is a policy, not a "
              "proof that the future false-alarm budget will be met"))

    # --- realised history: measured, and explicitly retrospective --------
    metrics = probability_metrics(probability, labels)
    stats = alarm_stats(probability, labels, thresholds,
                        alert_config.sessions_per_year)
    spans = episode_spans(alarm)
    history = dict(
        metrics=metrics, alarm_stats=stats,
        episodes=[dict(start=dates[s], end=dates[min(e, last)])
                  for s, e in spans][-12:],
        reliability=reliability(probability, labels),
        forecast_sessions=int(np.isfinite(probability).sum()),
        matured_labels=int(matured.sum()),
        positive_labels=int(np.nansum(labels)),
        note=("retrospective replay over the available history. It shows "
              "what the instrument would have produced, which is "
              "implementation behaviour rather than demonstrated foresight"))

    tail = slice(max(0, len(dates) - series_tail), len(dates))
    series = [
        dict(date=dates[i],
             probability=(None if not np.isfinite(probability[i])
                          else float(probability[i])),
             threshold=(None if not np.isfinite(thresholds[i])
                        else float(thresholds[i])),
             alarm=bool(alarm[i]),
             label=(None if not np.isfinite(labels[i]) else int(labels[i])))
        for i in range(*tail.indices(len(dates)))
    ]

    return PredictionState(
        as_of=dates[last],
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        snapshot=dict(
            path=str(snapshot_path),
            sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
            rows=len(dates), first_session=dates[0], last_session=dates[last]),
        protocol=dict(
            horizon=HORIZON, loss_barrier=LOSS_BARRIER,
            pillar_config=asdict(pillar_config),
            alert_config=asdict(alert_config),
            features=list(OPERATIONAL_FEATURES)),
        measured=measured, predicted=predicted, warning=warning,
        history=history,
        validation=dict(status=VALIDATION_STATUS, note=VALIDATION_NOTE),
        series=series)


DEFAULT_STATE_PATH = Path("prototype_runs/prediction/state.json")


def state_path() -> Path:
    """Where the saved warning state lives. `SERAPH_PREDICTION_STATE` wins.

    In the package, not in `scripts/`, because the console reads this and an
    installed wheel has no `scripts/` directory. Routing the import through
    the job script worked in a checkout and would have left the console
    unable to show a forecast in an installed distribution — which
    `verify_packaging.py` installs and probes.
    """
    import os

    override = os.environ.get("SERAPH_PREDICTION_STATE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / DEFAULT_STATE_PATH


def load_state(path=None) -> dict:
    """Read the saved state, reporting absence and damage rather than raising.

    Returns `{"ran": bool, ...}`. A console that raised on a missing or
    truncated file would take every other surface down with it.
    """
    target = Path(path) if path is not None else state_path()
    if not target.exists():
        return dict(ran=False, path=str(target),
                    note=("no prediction state has been saved. Run "
                          "`python scripts/run_prediction.py`, or let "
                          "`run_market_jobs.py` do it as part of the daily "
                          "sequence."))
    try:
        return dict(ran=True, path=str(target),
                    state=json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        return dict(ran=False, path=str(target), error=str(exc),
                    note="the saved prediction state could not be read")


def save(state: PredictionState, path) -> Path:
    """Write the state. Overwrites: this is current status, not evidence.

    Deliberately different from `experiment_store.save`, which refuses to
    overwrite because each ablation run is evidence of its own. A daily
    warning state is the opposite: the point is that it is current, and
    keeping every one would make the console pick among them.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_json(), indent=2, allow_nan=False),
                    encoding="utf-8")
    return path


def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
