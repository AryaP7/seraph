"""C10 predictive extension: chronological policy and pre-onset accounting."""
import numpy as np
import pytest

from seraph.prediction.evaluation import (
    AlertConfig, alarm_stats, calibrate_alerts, episode_spans, event_warnings,
    onset_labels, paired_brier_block_interval, probability_metrics,
)


def _business_dates(n=60):
    return np.busday_offset(np.datetime64("2020-01-01"), np.arange(n))


def test_threshold_never_reads_later_or_still_unmatured_outcomes():
    rng = np.random.default_rng(284)
    scores = rng.uniform(.01, .4, 700)
    labels = (rng.random(700) < .1).astype(float)
    cfg = AlertConfig(horizon=15, min_calibration=100, lookback=300, refit_every=1)
    original = calibrate_alerts(scores, labels, cfg)
    altered_labels = labels.copy()
    altered_labels[351:] = 1 - altered_labels[351:]
    altered_scores = scores.copy()
    altered_scores[351:] = .99
    changed = calibrate_alerts(altered_scores, altered_labels, cfg)
    # At decision 365, label 350 has matured; label 351 has not.
    np.testing.assert_equal(original["threshold"][:366], changed["threshold"][:366])
    np.testing.assert_equal(original["alarm"][:351], changed["alarm"][:351])
    assert all(fit["calibration_end_exclusive"] - 1 + 15 <= fit["decision_index"]
               for fit in original["fits"])


def test_missing_forecast_warmup_cannot_be_counted_as_calibration():
    scores = np.linspace(.01, .40, 500)
    scores[:100] = np.nan
    labels = np.zeros(500)
    result = calibrate_alerts(scores, labels, AlertConfig(min_calibration=252))
    # 252 observed scores at rows100..351 mature at decision366.
    assert np.isnan(result["threshold"][:366]).all()
    assert not np.isnan(result["threshold"][366])
    assert not result["alarm"][:366].any()
    assert result["fits"][0]["calibration"]["evaluated_sessions"] == 252


def test_policy_fits_respect_both_empirical_calibration_budgets():
    scores = np.full(600, .10)
    scores[[50, 120, 300, 410]] = .90
    labels = np.zeros(600)
    cfg = AlertConfig(horizon=15, min_calibration=252, refit_every=63,
                      false_episodes_per_year=2., max_alarm_fraction=.10)
    result = calibrate_alerts(scores, labels, cfg)
    assert result["fits"]
    assert np.isfinite(result["threshold"][266])
    for fit in result["fits"]:
        measured = fit["calibration"]
        assert measured["false_episodes_per_year"] <= 2.
        assert measured["alarm_fraction"] <= .10


def test_constant_scores_abstain_instead_of_a_perpetual_alarm():
    result = calibrate_alerts(np.full(320, .1), np.zeros(320))
    assert np.isposinf(result["threshold"][266:]).all()
    assert not result["alarm"].any()
    stats = alarm_stats(np.full(320, .1), np.zeros(320), result["threshold"])
    assert stats["evaluated_sessions"] == 54
    assert stats["episodes"] == 0
    assert stats["alarm_fraction"] == 0


def test_missing_scores_and_labels_split_alarm_episodes():
    stats = alarm_stats([.9, np.nan, .9, .9, .9], [0, 0, 0, np.nan, 0], .5)
    assert stats["evaluated_sessions"] == 3
    assert stats["episodes"] == 3
    assert stats["false_episodes"] == 3
    assert episode_spans([True, True, False, True]) == [(0, 2), (3, 4)]


def test_an_alarm_episode_overlapping_a_positive_window_is_not_false():
    stats = alarm_stats([.9, .9, 0, .9], [0, 1, 0, 0], .5)
    assert stats["episodes"] == 2
    assert stats["false_episodes"] == 1
    assert stats["alarm_sessions"] == 3


def test_future_onset_labels_are_exclusive_of_onset_and_unknown_at_tail():
    dates = _business_dates()
    result = onset_labels(dates, [str(dates[30])], horizon=15)
    assert not result[:15].any()
    np.testing.assert_equal(result[15:30], np.ones(15))
    assert result[30] == 0
    assert np.isnan(result[-15:]).all()


def test_non_session_onset_maps_to_next_session():
    dates = _business_dates()
    # 2020-02-01 is Saturday; next session is Monday February 3.
    onset = np.searchsorted(dates, np.datetime64("2020-02-03"))
    labels = onset_labels(dates, ["2020-02-01"], horizon=5)
    np.testing.assert_equal(labels[onset - 5:onset], np.ones(5))
    assert labels[onset] == 0
    scores = np.zeros(len(dates))
    scores[onset - 2] = .9
    result = event_warnings(dates, scores, np.full(len(dates), .5),
                            {"test": ("2020-02-01", "project event")}, horizon=5)[0]
    assert result["session_date"] == "2020-02-03"
    assert result["lead_sessions"] == 2


def test_onset_day_and_earlier_than_horizon_are_not_advance_warnings():
    dates = _business_dates()
    events = {"test": (str(dates[30]), "project event")}
    scores = np.zeros(len(dates))
    scores[14] = .9  #16 sessions ahead, outside declared15-session window
    scores[30] = .9  #onset day, contemporaneous
    result = event_warnings(dates, scores, np.full(len(dates), .5), events)[0]
    assert result["status"] == "missed"
    assert result["first_warning"] is None
    scores[15] = .9
    result = event_warnings(dates, scores, np.full(len(dates), .5), events)[0]
    assert result["status"] == "warned"
    assert result["lead_sessions"] == 15


def test_event_window_with_missing_policy_is_unassessable_not_missed():
    dates = _business_dates()
    scores = np.full(len(dates), .9)
    thresholds = np.full(len(dates), .5)
    thresholds[20] = np.nan
    result = event_warnings(dates, scores, thresholds,
                            {"test": (str(dates[30]), "project event")})[0]
    assert result["status"] == "unassessable"
    assert result["available_sessions"] == 14
    assert result["first_warning"] is None
    assert result["lead_sessions"] is None


def test_explicit_infinity_abstention_is_assessable_and_does_not_warn():
    dates = _business_dates()
    result = event_warnings(dates, np.full(len(dates), .9), np.full(len(dates), np.inf),
                            {"test": (str(dates[30]), "PROVISIONAL tariff label")})[0]
    assert result["status"] == "missed"
    assert result["available_sessions"] == 15
    assert result["label_status"] == "explicitly_unresolved"


def test_events_outside_coverage_do_not_create_proven_warnings_or_labels():
    dates = _business_dates()
    labels = onset_labels(dates, ["2021-01-01"], horizon=15)
    assert not labels[np.isfinite(labels)].any()
    events = {"early": (str(dates[5]), "project event"),
              "late": ("2021-01-01", "project event")}
    rows = event_warnings(dates, np.full(len(dates), .9), np.full(len(dates), .5), events)
    assert all(row["status"] == "unassessable" for row in rows)
    assert all(row["first_warning"] is None for row in rows)


def test_probability_metrics_have_tie_aware_auc_and_known_proper_scores():
    result = probability_metrics([.25, .25, .75, .75], [0, 1, 0, 1])
    assert result["auc"] == pytest.approx(.5)
    assert result["brier"] == pytest.approx(.3125)
    assert result["log_loss"] == pytest.approx(-.5 * (np.log(.25) + np.log(.75)))
    perfect = probability_metrics([0, 1, 0, 1], [0, 1, 0, 1])
    assert perfect["auc"] == 1
    assert perfect["brier"] == 0
    assert perfect["log_loss"] < 1e-8


def test_probability_metrics_use_only_common_finite_masked_rows():
    result = probability_metrics([.1, np.nan, .8, .4, .7], [0, 0, 1, np.nan, 1],
                                 mask=[True, True, True, True, False])
    assert result["n"] == 2
    assert result["positives"] == 1
    assert result["brier"] == pytest.approx(.025)
    assert probability_metrics([.1, .2], [0, 0])["auc"] is None
    assert probability_metrics([np.nan], [0])["n"] == 0
    with pytest.raises(ValueError):
        probability_metrics([1.01], [0])


def test_paired_interval_preserves_identity_and_common_coverage():
    candidate = np.tile([.1, .8], 200).astype(float)
    labels = np.tile([0, 1], 200).astype(float)
    candidate[100:140] = np.nan
    result = paired_brier_block_interval(candidate, candidate.copy(), labels,
                                         block=20, draws=100)
    assert result["n"] == 360
    assert result["mean"] == result["lower"] == result["upper"] == 0
    sparse = paired_brier_block_interval(candidate[:30], candidate[:30], labels[:30],
                                         block=20, draws=100)
    assert sparse["mean"] is None


@pytest.mark.parametrize("invalid_budget", [np.nan, np.inf, -1.])
def test_nonfinite_or_negative_false_alarm_budgets_rejected(invalid_budget):
    with pytest.raises(ValueError):
        AlertConfig(false_episodes_per_year=invalid_budget)


def test_event_reporting_rejects_misaligned_arrays_instead_of_broadcasting():
    dates = _business_dates()
    with pytest.raises(ValueError):
        event_warnings(dates, np.zeros(len(dates)), np.array([.5]),
                       {"test": (str(dates[30]), "project event")})


def test_alert_policy_expires_when_calibration_coverage_ages_out():
    scores = np.linspace(.01, .2, 700)
    scores[400:] = np.nan
    result = calibrate_alerts(scores, np.zeros(700),
                              AlertConfig(min_calibration=100, lookback=150))
    assert not np.isnan(result['threshold'][350])
    assert np.isnan(result['threshold'][600])
    assert not result['alarm'][600]


def test_reject_invalid_public_evaluation_arguments():
    dates = _business_dates()
    for value in (0, 2.5, np.nan, True):
        with pytest.raises(ValueError):
            onset_labels(dates, [], horizon=value)
    with pytest.raises(ValueError):
        onset_labels(np.array(['NaT'], dtype='datetime64[D]'), [])
    with pytest.raises(ValueError):
        probability_metrics([.5,.5], [0,1], mask=[True])
    with pytest.raises(ValueError):
        paired_brier_block_interval([.1,.2], [.1], [0,1])
    for value in (0, 2.5, np.nan, True):
        with pytest.raises(ValueError):
            paired_brier_block_interval([.1,.2], [.1,.2], [0,1], block=value)
