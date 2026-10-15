"""C12 research artifact display: no live connections or invented missing data."""
import json
from pathlib import Path

import polars as pl
from streamlit.testing.v1 import AppTest

from seraph.prediction.app import (
    covered_watch_status, load_artifacts, load_hazard_artifacts, prediction_views,
    training_endpoint, watch_status,
)

APP = Path(__file__).resolve().parents[1] / "seraph" / "prediction" / "app.py"


def test_missing_artifacts_are_explicit_and_viewer_renders(tmp_path, monkeypatch):
    summary, predictions, features, issues = load_artifacts(tmp_path)
    assert summary == {} and predictions.empty and features.empty and len(issues) == 3
    monkeypatch.setenv("SERAPH_RESEARCH_RESULTS", str(tmp_path))
    app = AppTest.from_file(str(APP)).run(timeout=15)
    assert not app.exception
    assert any("No forecast artifact" in item.value for item in app.info)


def test_viewer_keeps_historical_features_and_abstention_explicit(tmp_path, monkeypatch):
    dates = ["2020-01-02", "2020-01-03"]
    pl.DataFrame({
        "date": dates, "target": ["onset15"] * 2, "model": ["combined"] * 2,
        "probability": [0.1, 0.2], "threshold": [0.15, float("inf")],
        "label": [0, 0], "alarm": [False, False], "fit_status": ["fitted"] * 2,
        "train_end": ["2019-12-01"] * 2,
    }).write_parquet(tmp_path / "predictions.parquet")
    pl.DataFrame({
        "date": dates, "hawkes_daily_intensity": [0.1, 0.9],
        "rmt_fast_leading_share": [0.2, 0.7],
        "hamilton_daily_next_crisis_prob": [0.3, 0.8],
    }).write_parquet(tmp_path / "features.parquet")
    (tmp_path / "summary.json").write_text(json.dumps({
        "as_of": dates[-1], "created_utc": "2020-01-04T00:00:00Z",
        "models": [{"model": "combined", "target": "onset15", "metrics": {"brier": 0.1},
                    "events": [{"event": "fixture", "status": "missed"}]}],
        "limitations": ["Synthetic test fixture only."],
        "empirical_acceptance": {"status": "not established"},
    }), encoding="utf-8")
    monkeypatch.setenv("SERAPH_RESEARCH_RESULTS", str(tmp_path))
    app = AppTest.from_file(str(APP)).run(timeout=15)
    assert not app.exception
    assert app.selectbox[0].value == "combined · onset15"
    assert app.metric[2].value == "Abstained"
    assert app.metric[3].value == "0.9000"
    app.selectbox[1].set_value(dates[0]).run()
    assert not app.exception
    assert app.metric[0].value == "10.0%"
    assert app.metric[2].value == "Below threshold"
    assert app.metric[3].value == "0.1000"  # no future feature substitution


def test_csrs_column_is_not_silently_presented_as_probability():
    import pandas as pd
    assert prediction_views(pd.DataFrame({"date": ["2020-01-02"], "csrs": [0.9]})) == {}


def test_training_endpoint_is_a_historical_date_not_a_row_number():
    import pandas as pd
    dates = pd.DataFrame({"date": ["2020-01-02", "2020-01-03"]})
    assert training_endpoint(0, dates) == "2020-01-02"
    assert training_endpoint(-1, dates) == "Not fitted / not applicable"


def test_optional_hazard_watch_missing_artifacts_are_not_inactive(tmp_path):
    summary, watch, issues = load_hazard_artifacts(tmp_path)
    assert summary == {} and watch.empty and issues == []
    assert watch_status(None) == "Unavailable"
    assert watch_status(float("nan")) == "Unavailable"
    assert watch_status(False) == "Inactive"
    import pandas as pd
    assert covered_watch_status(pd.Series({"external_watch": False, "external_assessable": False}),
                                "external_watch") == "Unavailable"
    assert covered_watch_status(pd.Series({"combined_model_alarm": False}),
                                "combined_model_alarm") == "Unavailable"


def test_hazard_watch_attributes_external_rule_and_uses_exact_date(tmp_path):
    pl.DataFrame({
        "date": ["2020-01-30", "2020-01-31"],
        "external_watch": [False, True], "combined_model_alarm": [False, False],
        "combined_watch": [False, True], "active_events": ["", "synthetic_public_event"],
        "external_assessable": [True, True], "combined_assessable": [False, True],
    }).write_parquet(tmp_path / "hazard_watch.parquet")
    (tmp_path / "hazard_summary.json").write_text(json.dumps({
        "protocol": {"watch_sessions": 20, "timing": "next session"},
        "source_events": [{"event_id": "synthetic_public_event", "public_date": "2020-01-30"}],
        "evaluation": {"external": {"alarm_stats": {"false_episodes": 1},
                                    "events": [{"event": "fixture", "status": "warned"}]}},
        "limitations": ["Synthetic fixture; no historical claim."],
    }), encoding="utf-8")
    source = ("from pathlib import Path\n"
              "import streamlit as st\n"
              "from seraph.prediction.app import render_hazard_watch\n"
              "date = st.selectbox('date', ['2020-01-30','2020-01-31','2020-02-03'])\n"
              f"render_hazard_watch(Path({str(tmp_path)!r}), date)\n")
    app = AppTest.from_string(source).run(timeout=15)
    assert not app.exception
    assert app.metric[0].value == "Inactive"
    assert app.metric[1].value == app.metric[2].value == "Unavailable"
    app.selectbox[0].set_value("2020-01-31").run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["Active", "Inactive", "Active"]
    assert any("synthetic_public_event" in element.value for element in app.markdown)
    assert any("not a crisis probability" in element.value for element in app.info)
    assert app.dataframe[0].value["false_episodes"].iloc[0] == 1
    app.selectbox[0].set_value("2020-02-03").run()
    assert [metric.value for metric in app.metric] == ["Unavailable"] * 3
