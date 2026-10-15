"""C9/C10 experimental predictive layer, supplemental to FR28/FR30/FR32-37.

This module implements a new future-loss endpoint, not the existing CSRS or
its original crisis-onset acceptance test. It never accesses the database.
Rows are decision times after the observed session closes. Label i matures
only at i + horizon. Inputs must themselves be point-in-time causal.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or int(value) != value or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _return_vector(returns: Sequence[float]) -> np.ndarray:
    result = np.asarray(returns, dtype=float)
    if result.ndim != 1:
        raise ValueError("returns must be one-dimensional")
    if np.any(np.isfinite(result) & (result <= -1)):
        raise ValueError("finite simple returns must be greater than -1")
    return result


def future_loss_labels(
    returns: Sequence[float], horizon: int = 15, barrier: float = 0.10,
) -> np.ndarray:
    """Label a fall from today's close during the NEXT horizon sessions.

    `returns[t]` is the simple return ending at decision t; it is excluded
    from label t. This is a loss from today's value, not peak-to-trough
    drawdown. An incomplete or missing future path is NaN, never a negative.
    """
    horizon = _positive_integer(horizon, "horizon")
    if not 0 < barrier < 1:
        raise ValueError("barrier must be between zero and one")
    r = _return_vector(returns)
    labels = np.full(len(r), np.nan)
    log_barrier = np.log1p(-barrier)
    for t in range(len(r) - horizon):
        path = r[t + 1:t + horizon + 1]
        if np.isfinite(path).all():
            labels[t] = float(np.min(np.cumsum(np.log1p(path))) <= log_barrier)
    return labels


def _matrix(features: object, feature_names: tuple[str, ...]) -> np.ndarray:
    # Supports small pandas frames while keeping pandas optional here.
    if hasattr(features, "loc") and hasattr(features, "columns"):
        if not features.columns.is_unique:
            raise ValueError("feature column names must be unique")
        features = features.loc[:, list(feature_names)]
    values = np.asarray(features, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(feature_names):
        raise ValueError("features must be a 2D matrix matching feature_names")
    return values


class FutureLossLogit:
    """Small L2 logistic challenger with train-only robust transforms.

    `C` is inverse L2 regularization. The objective is summed Bernoulli loss
    divided by horizon plus ||beta||**2/(2*C): overlapping daily labels do
    not receive the same regularization strength as independent samples.
    This discount is regularization, NOT an uncertainty/independence proof.
    No class weighting is used because it distorts base event probabilities.

    Missing features are imputed to their TRAIN median, without a missingness
    indicator. Features never observed in training remain inactive. Pairwise
    interactions are explicit feature-name pairs, fixed before evaluation.
    """

    def __init__(
        self, feature_names: Sequence[str], *, horizon: int = 15,
        C: float = 0.1, interactions: Sequence[tuple[str, str]] = (),
        min_events: int = 5, clip: float = 6.0,
    ) -> None:
        self.feature_names = tuple(feature_names)
        if not self.feature_names or len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature_names must be nonempty and unique")
        self.horizon = _positive_integer(horizon, "horizon")
        self.min_events = _positive_integer(min_events, "min_events")
        if not np.isfinite(C) or C <= 0 or not np.isfinite(clip) or clip <= 0:
            raise ValueError("C and clip must be finite and positive")
        self.C = float(C)
        self.clip = float(clip)
        self.interactions = tuple(tuple(pair) for pair in interactions)
        if any(len(pair) != 2 or any(name not in self.feature_names for name in pair)
               for pair in self.interactions):
            raise ValueError("interaction pairs must name existing features")
        if len(set(tuple(sorted(pair)) for pair in self.interactions)) != len(self.interactions):
            raise ValueError("interaction pairs must be unique")
        self._pairs = tuple((self.feature_names.index(a), self.feature_names.index(b))
                            for a, b in self.interactions)
        self.design_names = self.feature_names + tuple(f"{a}*{b}" for a, b in self.interactions)
        self.fitted = False

    def _transform(self, values: np.ndarray) -> np.ndarray:
        clean = np.where(np.isfinite(values), values, self.center_)
        scaled = np.clip((clean - self.center_) / self.scale_, -self.clip, self.clip)
        scaled[:, ~self.active_] = 0.0
        if self._pairs:
            products = np.column_stack([np.clip(scaled[:, a] * scaled[:, b],
                                                -self.clip, self.clip)
                                        for a, b in self._pairs])
            scaled = np.column_stack((scaled, products))
        return scaled

    def fit(self, features: object, labels: Sequence[float]) -> "FutureLossLogit":
        """Fit exactly the supplied mature rows; call the wrapper for purging."""
        self.fitted = False
        values = _matrix(features, self.feature_names)
        y = np.asarray(labels, dtype=float)
        if y.ndim != 1 or len(y) != len(values):
            raise ValueError("labels must match feature rows")
        valid_y = np.isfinite(y)
        if not valid_y.any():
            raise ValueError("at least one observed binary label is required")
        if not np.isin(y[valid_y], [0, 1]).all():
            raise ValueError("finite labels must be zero or one")
        values, y = values[valid_y], y[valid_y]
        self.training_count_ = len(y)
        self.positive_count_ = int(y.sum())
        self.active_ = np.isfinite(values).any(axis=0)
        self.center_ = np.zeros(len(self.feature_names))
        self.scale_ = np.ones(len(self.feature_names))
        for j in np.flatnonzero(self.active_):
            column = values[np.isfinite(values[:, j]), j]
            self.center_[j] = np.median(column)
            q25, q75 = np.percentile(column, [25, 75])
            robust_scale = (q75 - q25) / 1.3489795003921634
            if robust_scale < 1e-12:
                robust_scale = np.std(column)
            self.scale_[j] = robust_scale if robust_scale >= 1e-12 else 1.0
        design = self._transform(values)
        # Jeffreys smoothing prevents a one-class sample masquerading as certainty.
        self.base_rate_ = (self.positive_count_ + 0.5) / (self.training_count_ + 1)
        self.intercept_ = float(logit(self.base_rate_))
        self.coef_ = np.zeros(design.shape[1])
        self.optimizer_message_ = "not run"
        if not self.active_.any():
            self.fit_status_ = "intercept_only_no_features"
        elif min(self.positive_count_, len(y) - self.positive_count_) < self.min_events:
            self.fit_status_ = "intercept_only_low_events"
        else:
            def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
                eta = theta[0] + design @ theta[1:]
                residual = (expit(eta) - y) / self.horizon
                loss = (np.logaddexp(0, eta) - y * eta).sum() / self.horizon
                loss += np.dot(theta[1:], theta[1:]) / (2 * self.C)
                # Weak intercept prior: half an observation of each outcome.
                # This prevents intercept divergence for separable sparse samples.
                loss += (np.logaddexp(0, theta[0]) - 0.5 * theta[0]) / self.horizon
                grad = np.r_[residual.sum() + (expit(theta[0]) - 0.5) / self.horizon,
                             design.T @ residual + theta[1:] / self.C]
                return float(loss), grad

            solution = minimize(objective, np.r_[self.intercept_, self.coef_],
                                jac=True, method="L-BFGS-B",
                                options={"maxiter": 400, "ftol": 1e-11, "gtol": 1e-7})
            self.optimizer_message_ = str(solution.message)
            if solution.success and np.isfinite(solution.x).all():
                self.intercept_ = float(solution.x[0])
                self.coef_ = solution.x[1:].copy()
                self.fit_status_ = "fitted"
            else:
                self.fit_status_ = "intercept_only_optimizer_failed"
        self.fitted = True
        return self

    def observed_features(self, features: object) -> np.ndarray:
        if not self.fitted:
            raise RuntimeError("model must be fitted before prediction")
        values = _matrix(features, self.feature_names)
        return (np.isfinite(values) & self.active_).sum(axis=1)

    def predict_proba(self, features: object) -> np.ndarray:
        """Return positive-event probabilities, NaN if no trained feature observed."""
        if not self.fitted:
            raise RuntimeError("model must be fitted before prediction")
        values = _matrix(features, self.feature_names)
        probability = expit(self.intercept_ + self._transform(values) @ self.coef_)
        probability[self.observed_features(values) == 0] = np.nan
        return probability

    def metadata(self) -> dict[str, object]:
        if not self.fitted:
            raise RuntimeError("model must be fitted before metadata")
        return {"fit_status": self.fit_status_, "training_count": self.training_count_,
                "positive_count": self.positive_count_, "base_rate": self.base_rate_,
                "feature_names": list(self.feature_names),
                "design_names": list(self.design_names),
                "active_features": self.active_.tolist(),
                "center": self.center_.tolist(), "scale": self.scale_.tolist(),
                "coef": self.coef_.tolist(), "intercept": self.intercept_,
                "optimizer_message": self.optimizer_message_, "C": self.C,
                "horizon": self.horizon}


@dataclass(frozen=True)
class WalkForwardPrediction:
    probability: np.ndarray
    train_end: np.ndarray
    fitted_at: np.ndarray
    training_count: np.ndarray
    fit_status: np.ndarray
    observed_features: np.ndarray
    fits: tuple[dict[str, object], ...]


def walk_forward_predict(
    features: object, labels: Sequence[float], feature_names: Sequence[str], *,
    horizon: int = 15, min_train: int = 756, refit_every: int = 63,
    C: float = 0.1, interactions: Sequence[tuple[str, str]] = (),
    min_events: int = 5, max_train: int | None = None,
) -> WalkForwardPrediction:
    """Expanding (or fixed trailing) chronological fit with horizon purging.

    At t close, only labels i <= t-horizon are eligible. Future labels are
    not read by fit or scaling, including at periodic refits. `labels` can
    instead be supplied original onset-warning labels with the corresponding
    horizon; target selection belongs to the evaluation protocol.
    """
    horizon = _positive_integer(horizon, "horizon")
    min_train = _positive_integer(min_train, "min_train")
    refit_every = _positive_integer(refit_every, "refit_every")
    if max_train is not None:
        max_train = _positive_integer(max_train, "max_train")
        if max_train < min_train:
            raise ValueError("max_train must not be smaller than min_train")
    names = tuple(feature_names)
    values = _matrix(features, names)
    y = np.asarray(labels, dtype=float)
    if y.ndim != 1 or len(y) != len(values):
        raise ValueError("labels must match feature rows")
    n = len(y)
    probability = np.full(n, np.nan)
    train_end = np.full(n, -1, dtype=int)
    fitted_at = np.full(n, -1, dtype=int)
    training_count = np.zeros(n, dtype=int)
    fit_status = np.full(n, "insufficient_training", dtype="U40")
    observed_features = np.zeros(n, dtype=int)
    fits: list[dict[str, object]] = []
    model: FutureLossLogit | None = None
    last_fit = -refit_every
    last_train_end = -1
    for t in range(horizon, n):
        if model is None or t - last_fit >= refit_every:
            stop = t - horizon + 1
            start = 0 if max_train is None else max(0, stop - max_train)
            count = int(np.isfinite(y[start:stop]).sum())
            if count < min_train:
                # A pre-existing model is not silently reused when its declared
                # trailing window no longer has sufficient mature labels.
                model = None
                continue
            model = FutureLossLogit(names, horizon=horizon, C=C,
                                    interactions=interactions, min_events=min_events)
            model.fit(values[start:stop], y[start:stop])
            last_fit, last_train_end = t, stop - 1
            fits.append({"fitted_at": t, "train_start": start,
                         "train_end": last_train_end, **model.metadata()})
        if model is not None:
            probability[t] = model.predict_proba(values[t:t + 1])[0]
            observed_features[t] = model.observed_features(values[t:t + 1])[0]
            train_end[t] = last_train_end
            fitted_at[t] = last_fit
            training_count[t] = model.training_count_
            fit_status[t] = (model.fit_status_ if observed_features[t]
                             else "no_observed_trained_features")
    return WalkForwardPrediction(probability, train_end, fitted_at, training_count,
                                 fit_status, observed_features, tuple(fits))


class EWMAStudentTForecaster:
    """Fixed-parameter historical benchmark, not a calibrated crisis predictor.

    Returns a path-loss probability from zero-drift Student-t log-return paths
    with today's EWMA volatility held constant across the forecast horizon.
    Fixed nu/lambda precede evaluation. This is neither GARCH nor a jump model.
    Common seeded draws make all decisions and repeated runs reproducible.
    """

    def __init__(
        self, *, horizon: int = 15, barrier: float = 0.10,
        decay: float = 0.94, nu: float = 7.0, min_history: int = 60,
        simulations: int = 20000, seed: int = 1729,
    ) -> None:
        self.horizon = _positive_integer(horizon, "horizon")
        self.min_history = _positive_integer(min_history, "min_history")
        self.simulations = _positive_integer(simulations, "simulations")
        if not 0 < barrier < 1 or not 0 < decay < 1 or not np.isfinite(nu) or nu <= 2:
            raise ValueError("require 0<barrier<1, 0<decay<1 and finite nu>2")
        self.barrier, self.decay, self.nu, self.seed = barrier, decay, nu, seed
        random = np.random.default_rng(seed)
        innovations = random.standard_t(nu, size=(simulations, horizon))
        innovations *= np.sqrt((nu - 2) / nu)
        # Positive magnitude of most adverse cumulative standardized return.
        self._loss_magnitudes = np.sort(-np.min(np.cumsum(innovations, axis=1), axis=1))

    def predict(self, returns: Sequence[float]) -> dict[str, np.ndarray | dict[str, object]]:
        """Compute all after-close forecasts in one causal pass.

        A missing daily return resets warm-up; it is never interpreted as zero.
        Monte-Carlo standard error measures simulation error only, not model
        uncertainty or historical calibration accuracy.
        """
        r = _return_vector(returns)
        probability = np.full(len(r), np.nan)
        volatility = np.full(len(r), np.nan)
        mc_se = np.full(len(r), np.nan)
        status = np.full(len(r), "insufficient_history", dtype="U24")
        history = 0
        variance = 0.0
        threshold = -np.log1p(-self.barrier)
        for t, value in enumerate(r):
            if not np.isfinite(value):
                history, variance = 0, 0.0
                status[t] = "missing_return"
                continue
            log_return = np.log1p(value)
            variance = (log_return ** 2 if history == 0 else
                        self.decay * variance + (1 - self.decay) * log_return ** 2)
            history += 1
            if history < self.min_history:
                continue
            sigma = float(np.sqrt(max(variance, 0)))
            volatility[t] = sigma
            if sigma == 0:
                probability[t], mc_se[t] = 0.0, 0.0
            else:
                crossing = self.simulations - np.searchsorted(
                    self._loss_magnitudes, threshold / sigma, side="left")
                probability[t] = crossing / self.simulations
                mc_se[t] = np.sqrt(probability[t] * (1 - probability[t]) / self.simulations)
            status[t] = "forecast"
        return {"probability": probability, "volatility": volatility,
                "monte_carlo_se": mc_se, "status": status,
                "metadata": {"model": "ewma_student_t_constant_future_volatility",
                             "horizon": self.horizon, "barrier": self.barrier,
                             "decay": self.decay, "nu": self.nu,
                             "min_history": self.min_history,
                             "simulations": self.simulations, "seed": self.seed}}


def gjr_garch_student_t_predict(
    returns: Sequence[float], *, horizon: int = 15, barrier: float = 0.10,
    min_train: int = 756, refit_every: int = 63, max_train: int | None = None,
    simulations: int = 2048, seed: int = 1729,
) -> dict[str, object]:
    """Causal optional `arch` GJR-GARCH(1,1,1)/Student-t loss benchmark.

    Parameters fit only returns strictly before t, then today's observed return
    updates the conditional variance before simulating t+1...t+h. The mean is
    fixed at zero; degrees of freedom and variance parameters are estimated.
    Missing data resets training and state. Failed fits emit no forecast until
    the next scheduled refit. No sample-wide fitting, selection, or scaling.
    """
    from arch import arch_model  # Optional; missing installation is explicit.

    horizon = _positive_integer(horizon, "horizon")
    min_train = _positive_integer(min_train, "min_train")
    refit_every = _positive_integer(refit_every, "refit_every")
    simulations = _positive_integer(simulations, "simulations")
    if not 0 < barrier < 1:
        raise ValueError("barrier must be between zero and one")
    if max_train is not None:
        max_train = _positive_integer(max_train, "max_train")
        if max_train < min_train:
            raise ValueError("max_train must not be smaller than min_train")
    r = _return_vector(returns)
    log_r = np.full(len(r), np.nan)
    good = np.isfinite(r)
    log_r[good] = 100 * np.log1p(r[good])
    probability = np.full(len(r), np.nan)
    next_volatility = np.full(len(r), np.nan)
    mc_se = np.full(len(r), np.nan)
    train_end = np.full(len(r), -1, dtype=int)
    status = np.full(len(r), "insufficient_training", dtype="U32")
    fits: list[dict[str, object]] = []
    segment_start = 0
    last_attempt = -refit_every
    last_end = -1
    params: tuple[float, float, float, float, float] | None = None
    innovations = np.empty((simulations, horizon))
    multipliers = np.empty_like(innovations)
    variance = 0.0
    current_status = "insufficient_training"
    threshold = 100 * np.log1p(-barrier)
    for t in range(len(r)):
        if not good[t]:
            segment_start, params, last_attempt = t + 1, None, -refit_every
            status[t] = "missing_return"
            continue
        if t - segment_start < min_train:
            continue
        if t - last_attempt >= refit_every:
            last_attempt = t
            start = segment_start if max_train is None else max(segment_start, t - max_train)
            fit_info: dict[str, object] = {"fitted_at": t, "train_start": start,
                                          "train_end": t - 1, "training_count": t - start}
            params = None
            sample = log_r[start:t]
            try:
                if np.var(sample) < 1e-12:
                    raise ValueError("training sample has no return variation")
                fitted = arch_model(sample, mean="Zero", vol="GARCH", p=1, o=1,
                                    q=1, power=2.0, dist="StudentsT", rescale=False).fit(
                                        disp="off", show_warning=False,
                                        options={"maxiter": 300, "ftol": 1e-8})
                fitted_params = fitted.params
                omega, alpha, gamma, beta, nu = map(float, [
                    fitted_params["omega"], fitted_params["alpha[1]"],
                    fitted_params["gamma[1]"], fitted_params["beta[1]"],
                    fitted_params["nu"]])
                raw_parameters = np.array([omega, alpha, gamma, beta, nu])
                fit_info.update({"params": {"omega": omega, "alpha": alpha,
                                            "gamma": gamma, "beta": beta, "nu": nu},
                                 "convergence_flag": int(fitted.convergence_flag),
                                 "persistence": alpha + .5 * gamma + beta})
                if (fitted.convergence_flag != 0 or not np.isfinite(raw_parameters).all()
                        or omega < 0 or alpha < -1e-8 or alpha + gamma < -1e-8
                        or beta < -1e-8 or nu <= 2):
                    current_status = "fit_failed"
                else:
                    params = omega, alpha, gamma, beta, nu
                    variance = float(np.asarray(fitted.conditional_volatility)[-1] ** 2)
                    previous_return = log_r[t - 1]
                    variance = (omega + (alpha + gamma * (previous_return < 0))
                                * previous_return ** 2 + beta * variance)
                    random = np.random.default_rng(seed)
                    innovations = random.standard_t(nu, size=(simulations, horizon))
                    innovations *= np.sqrt((nu - 2) / nu)
                    multipliers = beta + innovations ** 2 * (alpha + gamma * (innovations < 0))
                    last_end = t - 1
                    current_status = "forecast"
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                current_status = "fit_failed"
                fit_info["error"] = str(exc)
            fit_info["status"] = current_status
            fits.append(fit_info)
        status[t] = current_status
        if params is None:
            continue
        omega, alpha, gamma, beta, _ = params
        variance = omega + (alpha + gamma * (log_r[t] < 0)) * log_r[t] ** 2 + beta * variance
        if not np.isfinite(variance) or variance < 0:
            params = None
            status[t] = current_status = "invalid_filtered_variance"
            continue
        next_volatility[t] = np.sqrt(variance) / 100
        path_variance = np.full(simulations, variance)
        cumulative = np.zeros(simulations)
        crossed = np.zeros(simulations, dtype=bool)
        for step in range(horizon):
            cumulative += np.sqrt(np.maximum(path_variance, 0)) * innovations[:, step]
            crossed |= cumulative <= threshold
            path_variance = omega + path_variance * multipliers[:, step]
        p = float(crossed.mean())
        probability[t] = p
        mc_se[t] = np.sqrt(p * (1 - p) / simulations)
        train_end[t] = last_end
    return {"probability": probability, "volatility": next_volatility,
            "monte_carlo_se": mc_se, "status": status, "train_end": train_end,
            "fits": fits,
            "metadata": {"model": "gjr_garch_111_student_t_zero_mean",
                         "horizon": horizon, "barrier": barrier,
                         "min_train": min_train, "refit_every": refit_every,
                         "max_train": max_train, "simulations": simulations,
                         "seed": seed, "fit_through": "t-1; filter through t"}}
