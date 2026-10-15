"""C9/C10 predictive extension: maturity, causality, and coverage contracts."""
import numpy as np
import pytest

from seraph.prediction.models import (
    EWMAStudentTForecaster, FutureLossLogit, future_loss_labels,
    gjr_garch_student_t_predict, walk_forward_predict,
)


def test_future_loss_is_from_current_close_and_excludes_current_return():
    returns = np.array([-0.90, 0.01, -0.06, -0.06, 0.02, 0.01])
    labels = future_loss_labels(returns, horizon=2, barrier=0.10)
    np.testing.assert_equal(labels, [0, 1, 0, 0, np.nan, np.nan])


def test_incomplete_or_missing_future_paths_are_not_negative_labels():
    labels = future_loss_labels([0, 0, np.nan, 0, 0, 0], horizon=2)
    np.testing.assert_equal(labels, [np.nan, np.nan, 0, 0, np.nan, np.nan])


def test_close_loss_does_not_mean_peak_to_trough_drawdown():
    # A loss from a future high is not a loss from today's close.
    np.testing.assert_equal(future_loss_labels([0, .50, -.20], horizon=2),
                            [0, np.nan, np.nan])


def _sample(n=300):
    rng = np.random.default_rng(821)
    x = rng.normal(size=(n, 3))
    y = (rng.random(n) < 1 / (1 + np.exp(1 - x[:, 0]))).astype(float)
    return x, y


def test_scaling_and_coefficients_do_not_change_when_prediction_changes():
    x, y = _sample()
    model = FutureLossLogit(["hawkes", "rmt", "hamilton"])
    model.fit(x[:160], y[:160])
    before = model.metadata()
    model.predict_proba(x[160:])
    model.predict_proba(np.full_like(x[160:], 1e20))
    assert model.metadata() == before
    np.testing.assert_allclose(model.center_, np.median(x[:160], axis=0))


def test_future_perturbation_leaves_earlier_walk_forward_predictions_identical():
    x, y = _sample()
    first = walk_forward_predict(x, y, ["hawkes", "rmt", "hamilton"],
                                 horizon=15, min_train=70, refit_every=19)
    x2, y2 = x.copy(), y.copy()
    x2[210:] = 1e10
    y2[210:] = 1 - y2[210:]
    second = walk_forward_predict(x2, y2, ["hawkes", "rmt", "hamilton"],
                                  horizon=15, min_train=70, refit_every=19)
    np.testing.assert_equal(first.probability[:210], second.probability[:210])
    assert first.fits[0] == second.fits[0]


def test_unmatured_labels_cannot_affect_today_even_if_supplied():
    x, y = _sample(200)
    first = walk_forward_predict(x, y, ["h", "r", "m"], horizon=15,
                                 min_train=40, refit_every=1)
    y2 = y.copy()
    y2[136:] = 1 - y2[136:]
    second = walk_forward_predict(x, y2, ["h", "r", "m"], horizon=15,
                                  min_train=40, refit_every=1)
    # At 150, y[135] has matured; y[136] has not.
    assert first.train_end[150] == 135
    assert first.probability[150] == second.probability[150]
    valid = first.train_end >= 0
    assert np.all(first.train_end[valid] + 15 <= np.flatnonzero(valid))


def test_first_forecast_has_required_number_of_mature_labels():
    x, y = _sample(100)
    result = walk_forward_predict(x, y, ["h", "r", "m"], horizon=15,
                                  min_train=40, refit_every=10)
    assert np.isnan(result.probability[:54]).all()
    assert np.isfinite(result.probability[54])
    assert result.train_end[54] == 39
    assert result.training_count[54] == 40


def test_one_class_is_explicit_historical_rate_fallback_not_half():
    x, _ = _sample(100)
    model = FutureLossLogit(["h", "r", "m"]).fit(x, np.zeros(100))
    assert model.fit_status_ == "intercept_only_low_events"
    np.testing.assert_allclose(model.predict_proba(x), .5 / 101)
    assert np.all(model.coef_ == 0)


def test_missing_pillar_is_neutral_but_all_missing_abstains():
    x, y = _sample(100)
    x[:, 0] = np.nan
    model = FutureLossLogit(["hawkes", "rmt", "hamilton"],
                            interactions=[("hawkes", "rmt")]).fit(x, y)
    assert model.active_.tolist() == [False, True, True]
    base = model.predict_proba(x[0:1])[0]
    altered = x[0:1].copy()
    altered[0, 0] = 1e10
    assert model.predict_proba(altered)[0] == base
    assert np.isnan(model.predict_proba(np.full((1, 3), np.nan))[0])
    assert model.coef_[0] == 0
    assert model.coef_[3] == 0


def test_no_features_returns_no_prediction_even_with_observed_labels():
    model = FutureLossLogit(["h"]).fit(np.full((30, 1), np.nan), np.zeros(30))
    assert model.fit_status_ == "intercept_only_no_features"
    assert np.isnan(model.predict_proba([[100]])[0])


def test_t_baseline_is_prefix_stable_and_handles_missing_observations():
    rng = np.random.default_rng(192)
    returns = rng.normal(0, .01, 200)
    model = EWMAStudentTForecaster(min_history=30, simulations=2000)
    first = model.predict(returns)
    altered = returns.copy()
    altered[120:] = -.30
    second = model.predict(altered)
    np.testing.assert_equal(first["probability"][:120], second["probability"][:120])
    np.testing.assert_equal(model.predict(returns[:120])["probability"],
                            first["probability"][:120])
    altered = returns.copy()
    altered[100] = np.nan
    missing = model.predict(altered)
    assert np.isnan(missing["probability"][100:130]).all()
    assert np.isfinite(missing["probability"][130])


def test_volatility_benchmark_loss_probability_increases_with_scale():
    returns = np.tile([.01, -.01], 60)
    model = EWMAStudentTForecaster(min_history=30, simulations=4000)
    small = model.predict(returns)
    big = model.predict(returns * 3)
    assert big["probability"][-1] > small["probability"][-1]
    assert small["status"][-1] == "forecast"


def test_training_window_restricts_fit_rows():
    x, y = _sample(150)
    result = walk_forward_predict(x, y, ["h", "r", "m"], min_train=40,
                                  max_train=60, refit_every=20)
    assert result.fits[-1]["training_count"] == 60
    assert result.fits[-1]["train_end"] - result.fits[-1]["train_start"] == 59


@pytest.mark.parametrize("kwargs", [{"horizon": 0}, {"horizon": 1.5},
                                    {"barrier": 0}, {"barrier": 1}])
def test_bad_target_parameters_rejected(kwargs):
    with pytest.raises(ValueError):
        future_loss_labels([0, .01, -.02], **kwargs)


def test_nonbinary_labels_and_impossible_returns_rejected():
    with pytest.raises(ValueError):
        FutureLossLogit(["x"]).fit([[0], [1]], [0, .5])
    with pytest.raises(ValueError):
        future_loss_labels([0, -1, 0])


def test_gjr_baseline_is_prefix_stable_and_fits_only_past_returns():
    pytest.importorskip("arch")
    rng = np.random.default_rng(278)
    returns = .01 * rng.standard_t(7, 200)
    kwargs = dict(horizon=5, min_train=100, refit_every=31, simulations=128)
    result = gjr_garch_student_t_predict(returns, **kwargs)
    altered = returns.copy()
    altered[170:] = -.10
    second = gjr_garch_student_t_predict(altered, **kwargs)
    np.testing.assert_equal(result["probability"][:170], second["probability"][:170])
    np.testing.assert_equal(result["volatility"][:170], second["volatility"][:170])
    prefix = gjr_garch_student_t_predict(returns[:170], **kwargs)
    np.testing.assert_equal(result["probability"][:170], prefix["probability"])
    assert np.isfinite(result["probability"][100:]).any()
    assert all(fit["train_end"] == fit["fitted_at"] - 1 for fit in result["fits"])


def test_gjr_no_variation_is_reported_as_failed_fit():
    pytest.importorskip("arch")
    result = gjr_garch_student_t_predict(np.zeros(120), min_train=100,
                                        simulations=128, refit_every=10)
    assert np.isnan(result["probability"]).all()
    assert result["status"][-1] == "fit_failed"
    assert len(result["fits"]) == 2
