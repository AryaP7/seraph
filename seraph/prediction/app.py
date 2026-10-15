"""C12 research-only viewer of saved C9/C10 prediction experiment artifacts.

This app reads local files and performs no model fitting, database access,
external requests, or publication. Historical features are displayed at their
recorded decision date; evaluation outcomes remain explicitly retrospective.
Run using launch_research.ps1 from the experimental project root.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = ROOT / "research_results" / "v1_verified"
PILLARS = (
    ("Hawkes", "hawkes_daily_intensity", "Next-session tail-event intensity",
     "Conditional daily tail-event intensity; not a crisis probability."),
    ("RMT", "rmt_fast_leading_share", "Fast leading eigenvalue share",
     "Share of correlation-spectrum mass in the leading factor; not a loss probability."),
    ("Hamilton", "hamilton_daily_next_crisis_prob", "Next-session high-volatility state",
     "Probability of the model's highest-variance latent regime; not the probability of a market crisis."),
)


def load_artifacts(directory: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, list[str]]:
    """Read saved artifacts, reporting partial/malformed outputs explicitly."""
    issues: list[str] = []
    summary: dict = {}
    try:
        with (directory / "summary.json").open(encoding="utf-8") as handle:
            summary = json.load(handle)
        if not isinstance(summary, dict):
            summary = {}
            issues.append("summary.json must contain an object.")
    except (OSError, ValueError) as exc:
        issues.append(f"Summary unavailable: {exc}")
    frames = []
    for name in ("predictions.parquet", "features.parquet"):
        try:
            frame = pl.read_parquet(directory / name).to_pandas()
            if "date" in frame:
                frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            frames.append(frame)
        except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
            issues.append(f"{name} unavailable: {exc}")
            frames.append(pd.DataFrame())
    return summary, frames[0], frames[1], issues


def load_hazard_artifacts(directory: Path) -> tuple[dict, pd.DataFrame, list[str]]:
    """Optional rule-based watch artifacts; absence is not a negative signal."""
    summary_path, watch_path = directory / "hazard_summary.json", directory / "hazard_watch.parquet"
    if not summary_path.exists() and not watch_path.exists():
        return {}, pd.DataFrame(), []
    summary: dict = {}
    watch = pd.DataFrame()
    issues = []
    try:
        with summary_path.open(encoding="utf-8") as handle:
            summary = json.load(handle)
        if not isinstance(summary, dict):
            summary = {}
            issues.append("hazard_summary.json must contain an object.")
    except (OSError, ValueError) as exc:
        issues.append(f"Public-event watch summary unavailable: {exc}")
    try:
        watch = pl.read_parquet(watch_path).to_pandas()
        if "date" in watch:
            watch["date"] = pd.to_datetime(watch["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            issues.append("Public-event watch has no decision-date column.")
    except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
        issues.append(f"Public-event watch rows unavailable: {exc}")
    return summary, watch, issues


def prediction_views(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Normalize explicit probability fields; never infer probability from CSRS.

    Supports a long artifact with model/candidate, probability and optional
    endpoint/target, or explicit p_/prob_/probability_ fields in a wide artifact.
    Unknown schemas remain available as raw tables without invented readings.
    """
    if frame.empty or "date" not in frame:
        return {}
    candidate = next((name for name in ("candidate", "model", "model_name") if name in frame), None)
    probability = next((name for name in ("probability", "prediction", "p") if name in frame), None)
    endpoint = next((name for name in ("endpoint", "target") if name in frame), None)
    views = {}
    if candidate is not None and probability is not None:
        keys = [candidate] + ([endpoint] if endpoint else [])
        for key, rows in frame.groupby(keys, dropna=False, sort=True):
            parts = key if isinstance(key, tuple) else (key,)
            name = " · ".join(str(part) for part in parts)
            rows = rows.copy().rename(columns={probability: "probability"})
            views[name] = rows.sort_values("date")
        return views
    for column in frame:
        prefix = next((p for p in ("probability_", "prob_", "p_") if column.startswith(p)), None)
        if prefix:
            name = column[len(prefix):]
            rows = frame[["date", column]].rename(columns={column: "probability"}).copy()
            threshold = next((field for field in (f"threshold_{name}", f"{name}_threshold")
                              if field in frame), None)
            if threshold:
                rows["threshold"] = frame[threshold]
            views[name] = rows.sort_values("date")
    return views


def _finite(value) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _table(value) -> pd.DataFrame:
    """Present saved records; no evaluation metric is computed in the UI."""
    if isinstance(value, list) and all(isinstance(v, dict) for v in value):
        return pd.json_normalize(value)
    if isinstance(value, dict) and value and all(isinstance(v, dict) for v in value.values()):
        return pd.json_normalize([{"name": key, **row} for key, row in value.items()])
    return pd.DataFrame()


def training_endpoint(value, features: pd.DataFrame) -> str:
    """Resolve the runner's zero-based training-row index to its actual date."""
    if _finite(value) and float(value).is_integer():
        index = int(value)
        if index < 0:
            return "Not fitted / not applicable"
        if "date" in features and index < len(features):
            return str(features.iloc[index]["date"])
        return f"row {index} (date unavailable)"
    return str(value) if value is not None else "Unavailable"


def _render_pillars(features: pd.DataFrame, as_of: str) -> None:
    st.subheader("Three retained pillars")
    rows = features[features["date"] == as_of] if "date" in features else pd.DataFrame()
    row = rows.iloc[-1] if len(rows) else pd.Series(dtype=float)
    for column, (name, field, label, explanation) in zip(st.columns(3), PILLARS):
        with column:
            st.markdown(f"**{name}**")
            value = row.get(field)
            formatted = (f"{float(value):.1%}" if name != "Hawkes" else f"{float(value):.4f}") \
                if _finite(value) else "Unavailable"
            st.metric(label, formatted)
            st.caption(explanation)
    st.caption("These are the experimental daily pillar extensions. Feature availability does not establish predictive skill.")
    if not rows.empty:
        columns = [c for c in rows if c.startswith(("hawkes_", "rmt_", "hamilton_"))]
        with st.expander("All recorded pillar features for this date"):
            st.dataframe(rows[["date", *columns]], hide_index=True, width="stretch")


def watch_status(value) -> str:
    """Do not interpret missing watch data as a false signal (or vice versa)."""
    if isinstance(value, (bool, np.bool_)):
        return "Active" if value else "Inactive"
    if _finite(value) and float(value) in (0.0, 1.0):
        return "Active" if float(value) == 1 else "Inactive"
    return "Unavailable"


def covered_watch_status(row: pd.Series, field: str) -> str:
    coverage = "external_assessable" if field == "external_watch" else "combined_assessable"
    if watch_status(row.get(coverage)) != "Active":
        return "Unavailable"
    return watch_status(row.get(field))


def render_hazard_watch(directory: Path, as_of: str) -> None:
    """Keep the hypothetical public-event rule visibly separate from probabilities."""
    summary, watch, issues = load_hazard_artifacts(directory)
    if not summary and watch.empty and not issues:
        return
    st.subheader("Public-event watch")
    st.info(
        "Retrospective hypothetical hazard watch. A fixed rule starts a temporary watch "
        "after recorded public emergency declarations. This is not a crisis probability, "
        "not proof of pre-COVID prediction, and does not alter the model probability above."
    )
    st.caption(
        "The saved combined watch uses the combined/onset15 model alarm plus the external rule. "
        "It is independent of the candidate selected above. The public-event rule's contribution "
        "is shown separately so it cannot be attributed to the three pillars."
    )
    st.caption("Evaluation status: a hypothetical scenario policy awaiting prospective validation; no live public-event feed or live forecast is implied.")
    for issue in issues:
        st.info(issue)
    rows = watch[watch["date"] == as_of] if "date" in watch else pd.DataFrame()
    row = rows.iloc[-1] if len(rows) else pd.Series(dtype=object)
    for card, field, label in zip(st.columns(3),
                                  ("external_watch", "combined_model_alarm", "combined_watch"),
                                  ("Public-event rule", "Combined model alarm", "Combined watch")):
        card.metric(label, covered_watch_status(row, field))
    st.caption(f"Recorded watch state on {as_of}; missing rows or unassessable source/model coverage remain unavailable.")
    events = row.get("active_events")
    active_ids = [event.strip() for event in str(events).split(";") if event.strip()] \
        if events is not None and not pd.isna(events) else []
    if active_ids:
        st.markdown("**Public trigger identifiers:** " + ", ".join(active_ids))
    elif covered_watch_status(row, "external_watch") == "Inactive":
        st.caption("No public-event trigger is active in this saved row.")
    else:
        st.caption("Public-event trigger details are unavailable for this date.")

    st.markdown("**Retrospective watch evaluation, including false alarms**")
    st.caption("These tables use the complete saved evaluation, including outcomes after the selected historical date.")
    evaluation = summary.get("evaluation", {})
    alarm_rows, event_rows = [], []
    if isinstance(evaluation, dict):
        for name, result in evaluation.items():
            if not isinstance(result, dict):
                continue
            if isinstance(result.get("alarm_stats"), dict):
                alarm_rows.append({"watch_rule": name, **result["alarm_stats"]})
            for event in result.get("events", []):
                if isinstance(event, dict):
                    event_rows.append({"watch_rule": name, **event})
    if alarm_rows:
        st.dataframe(_table(alarm_rows), hide_index=True, width="stretch")
    if event_rows:
        st.dataframe(_table(event_rows), hide_index=True, width="stretch")
    if not alarm_rows and not event_rows:
        st.info("No saved watch-evaluation table is available yet.")
    with st.expander("Public-event rule, source register, and limitations"):
        st.json(summary.get("protocol", {}))
        source_table = _table(summary.get("source_events"))
        if not source_table.empty:
            st.dataframe(source_table, hide_index=True, width="stretch")
        for limitation in summary.get("limitations", []):
            st.markdown(f"- {limitation}")


def _render_summary(summary: dict, *, model: str | None = None, target: str | None = None) -> None:
    st.subheader("Retrospective evaluation")
    st.caption("The tables below describe the full saved experiment. They are not information available at the selected historical decision date.")
    records = summary.get("models", [])
    if isinstance(records, list) and records:
        metric_rows = []
        for record in records:
            if not isinstance(record, dict):
                continue
            metric_rows.append({"target": record.get("target"), "model": record.get("model"),
                                **{f"common_{key}": value for key, value in record.get("metrics_common", {}).items()}})
        table = _table(metric_rows)
        if not table.empty:
            st.markdown("**Candidate comparison on common forecast coverage**")
            st.caption("Compare within the same target. These are the saved metrics_common values on dates available for every candidate; own-coverage metrics remain in the full summary.")
            st.dataframe(table, hide_index=True, width="stretch")
        event_rows = []
        for record in records:
            if not isinstance(record, dict):
                continue
            if model is not None and str(record.get("model")) != model:
                continue
            if target is not None and str(record.get("target")) != target:
                continue
            if record.get("alarm_stats"):
                st.markdown("**Selected candidate's complete alarm record**")
                st.caption("Alarm totals use this candidate's recorded coverage, which can differ from the common forecast-coverage table.")
                st.dataframe(pd.DataFrame([record["alarm_stats"]]), hide_index=True, width="stretch")
            for event in record.get("events", []):
                if isinstance(event, dict):
                    event_rows.append({"model": record.get("model"), "target": record.get("target"), **event})
        if event_rows:
            st.markdown("**Event-by-event warning record for the selected candidate**")
            st.caption("A loss-target warning near an event does not establish that the model predicted that event's onset.")
            st.dataframe(_table(event_rows), hide_index=True, width="stretch")
    found = bool(isinstance(records, list) and records)
    for key, label in (("metrics", "Candidate metrics"), ("models", "Candidate results"),
                       ("results", "Experiment results"), ("events", "Crisis-onset results"),
                       ("event_results", "Crisis-onset results"), ("event_table", "Crisis-onset results")):
        if key == "models" and found:
            continue
        table = _table(summary.get(key))
        if not table.empty:
            st.markdown(f"**{label}**")
            st.dataframe(table, hide_index=True, width="stretch")
            found = True
    if not found:
        st.info("No recognized evaluation table is available yet. The complete saved summary is below.")
    if isinstance(summary.get("empirical_acceptance"), dict):
        st.markdown("**Recorded acceptance assessment**")
        st.json(summary["empirical_acceptance"])
    if summary.get("limitations"):
        with st.expander("Evidence limits", expanded=True):
            for limitation in summary["limitations"]:
                st.markdown(f"- {limitation}")
    with st.expander("Full experiment summary and provenance"):
        st.json(summary)


def main() -> None:
    st.set_page_config(page_title="SERAPH · Prediction Research", page_icon="◈", layout="wide")
    st.title("SERAPH prediction research")
    st.caption("Hawkes · Random Matrix Theory · Hamilton")
    st.warning("Experimental historical research. These are saved as-of forecasts, not a live alert service or validated investment advice.")
    st.markdown(
        "The predictive layer estimates a defined **future outcome**. It is separate from the original "
        "**CSRS**, which is an uncalibrated diagnostic risk score. A latent Hamilton regime probability "
        "is also a different quantity. Keep each endpoint and its false-alarm record separate."
    )
    directory = Path(os.environ.get("SERAPH_RESEARCH_RESULTS", str(DEFAULT_RESULTS))).resolve()
    st.sidebar.markdown("**Saved experiment**")
    st.sidebar.code(str(directory), language=None)
    st.sidebar.caption("Local files only. This viewer does not fit models or connect to the database.")
    summary, predictions, features, issues = load_artifacts(directory)
    if summary.get("as_of"):
        st.caption(f"Saved dataset as of {summary['as_of']}. Generated {summary.get('created_utc', 'at an unrecorded time')}.")
    for issue in issues:
        st.info(issue)
    if predictions.empty:
        st.info("No forecast artifact is available. Run scripts/run_prediction_experiment.py in the experimental project, then refresh this page.")
        if summary:
            _render_summary(summary)
        return

    views = prediction_views(predictions)
    if not views:
        st.error("Forecast schema is not recognized. No probability or alarm will be inferred from other numeric columns.")
        st.dataframe(predictions.head(100), hide_index=True, width="stretch")
        _render_summary(summary)
        return
    names = list(views)
    preferred = names.index("combined · onset15") if "combined · onset15" in names else next(
        (i for i, name in enumerate(names) if "three_pillars" in name.lower()), 0)
    choice = st.selectbox("Candidate and endpoint", names, index=preferred)
    selected = views[choice]
    dates = sorted(selected["date"].dropna().unique())
    if not dates:
        st.error("No valid decision dates in the selected forecast artifact.")
        return
    as_of = st.selectbox("Historical decision date", dates, index=len(dates) - 1,
                         help="Recorded after-close decision date. Forecast outcomes lie in the future relative to this date.")
    st.caption(f"As of {as_of}, after the NSE close (IST). No later feature row is used for the readouts below.")
    row = selected[selected["date"] == as_of].iloc[-1]
    target, model = row.get("target"), row.get("model")
    if target == "onset15":
        st.markdown("**Onset endpoint:** a labelled crisis begins within the next 15 trading sessions. This depends on the recorded event-label protocol.")
    elif target == "loss10_15":
        st.markdown("**Loss endpoint:** the research market series falls at least 10% from this decision's close at some point in the next 15 trading sessions.")
    probability, threshold = row.get("probability"), row.get("threshold")
    cards = st.columns(3)
    valid_probability = _finite(probability) and 0 <= float(probability) <= 1
    cards[0].metric("Estimated outcome probability", f"{float(probability):.1%}" if valid_probability else "Unavailable")
    abstained = threshold is not None and float(threshold) == float("inf")
    cards[1].metric("Recorded alarm threshold", "Abstain" if abstained else
                    f"{float(threshold):.1%}" if _finite(threshold) else "Unavailable")
    status = "Unavailable"
    if abstained:
        status = "Abstained"
    elif valid_probability and _finite(threshold):
        status = "Warning" if float(probability) >= float(threshold) else "Below threshold"
    cards[2].metric("Historical alarm decision", status)
    st.caption(f"Recorded fit status: {row.get('fit_status', 'unavailable')}. Latest training endpoint: {training_endpoint(row.get('train_end'), features)}.")
    if abstained:
        st.info("The saved policy abstained from issuing alarms at this date. An infinite threshold is abstention, not a zero predicted risk.")
    chart = selected[selected["date"] <= as_of].copy()
    chart["date"] = pd.to_datetime(chart["date"])
    chart_fields = ["probability"] + (["threshold"] if "threshold" in chart else [])
    chart[chart_fields] = chart[chart_fields].replace([np.inf, -np.inf], np.nan)
    st.line_chart(chart.set_index("date")[chart_fields], width="stretch")
    _render_pillars(features, as_of)
    render_hazard_watch(directory, as_of)
    _render_summary(summary, model=str(model) if model is not None else None,
                    target=str(target) if target is not None else None)
    with st.expander("Recorded forecast rows for this candidate"):
        st.dataframe(selected, hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
