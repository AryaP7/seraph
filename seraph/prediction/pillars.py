"""Research extensions to C5/C6/C7 (FR10-24); not replacements for their engines.

Every output is an after-close-t quantity using observations through t. Model
parameters are estimated through t-1 on fixed, rolling, chronological windows.
These functions do not read/write the database or revise historical emissions.
See docs/PREDICTION-PILLARS.md for hypotheses, limitations, and provenance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class PillarConfig:
    """Fixed research plan; changing it is a new experiment, not calibration."""

    min_train: int = 252
    train_window: int = 1000
    refit_every: int = 63
    fast_window: int = 60
    slow_window: int = 252
    covariance_shrinkage: float = .10
    ewma_decay: float = .94
    ewma_warmup: int = 20
    tail_sigma: float = 2.0
    hawkes_half_life: float = 5.0
    min_hawkes_events: int = 5
    hmm_iterations: int = 80
    hmm_transition_prior: float = 2.0

    def __post_init__(self):
        if not (20 <= self.min_train <= self.train_window):
            raise ValueError('Require 20 <= min_train <= train_window')
        if not (3 <= self.fast_window <= self.slow_window):
            raise ValueError('Require 3 <= fast_window <= slow_window')
        if not 0 <= self.covariance_shrinkage < 1:
            raise ValueError('covariance_shrinkage must be in [0, 1)')
        if not 0 < self.ewma_decay < 1:
            raise ValueError('ewma_decay must be in (0, 1)')
        if min(self.refit_every, self.ewma_warmup, self.hmm_iterations,
               self.hawkes_half_life, self.tail_sigma, self.min_hawkes_events) <= 0:
            raise ValueError('cadences, iterations and event parameters must be positive')
        if self.hmm_transition_prior < 0:
            raise ValueError('hmm_transition_prior cannot be negative')


@dataclass(frozen=True)
class PillarFeatureResult:
    values: dict[str, np.ndarray]
    diagnostics: dict[str, Any]


def _emissions(observations: np.ndarray, variances: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Numerically scaled zero-mean Gaussian densities; missing = unit density."""
    finite = np.isfinite(observations)
    log_density = np.zeros((len(observations), 3))
    log_density[finite] = -.5 * (np.log(2 * np.pi * variances)[None, :]
                                 + observations[finite, None] ** 2 / variances[None, :])
    offsets = log_density.max(axis=1)
    return np.exp(log_density - offsets[:, None]), offsets


def _filter_hmm(observations: np.ndarray, transition: np.ndarray,
                variances: np.ndarray, initial: np.ndarray | None = None
                ) -> tuple[np.ndarray, float]:
    """Hamilton forward recursion; initial is the prior *at first observation*."""
    if initial is None:
        initial = np.full(3, 1 / 3)
    emission, offsets = _emissions(observations, variances)
    filtered = np.empty((len(observations), 3))
    probability = initial.copy()
    loglike = 0.0
    for i in range(len(observations)):
        if i:
            probability = probability @ transition
        probability = probability * emission[i]
        scale = probability.sum()
        probability /= scale
        filtered[i] = probability
        loglike += float(np.log(scale) + offsets[i])
    return filtered, loglike


def _fit_hmm(observations: np.ndarray, config: PillarConfig) -> tuple[np.ndarray, np.ndarray, dict]:
    """Restricted 3-state variance HMM, forward/backward EM on training data only.

    EM smooths *training* observations to estimate parameters. Only a fresh
    forward filter is emitted; no retrospective smoothed probabilities escape.
    Fixed diagonal transition pseudocounts regularize a small-sample baseline.
    """
    finite = np.isfinite(observations)
    squared = np.where(finite, observations ** 2, 0.0)
    sample_variance = max(float(squared[finite].mean()), 1e-10)
    floor = max(sample_variance * .05, 1e-10)
    variances = sample_variance * np.array([.3, 1., 3.])
    transition = np.full((3, 3), .025)
    np.fill_diagonal(transition, .95)
    prior_counts = np.full((3, 3), .01)
    prior_counts += np.eye(3) * config.hmm_transition_prior
    previous_map = -np.inf
    converged = False
    for iteration in range(config.hmm_iterations):
        emission, offsets = _emissions(observations, variances)
        forward = np.empty((len(observations), 3))
        scale = np.empty(len(observations))
        probability = np.full(3, 1 / 3)
        for t in range(len(observations)):
            if t:
                probability = probability @ transition
            probability = probability * emission[t]
            scale[t] = probability.sum()
            probability /= scale[t]
            forward[t] = probability
        backward = np.ones_like(forward)
        for t in range(len(observations) - 2, -1, -1):
            backward[t] = transition @ (emission[t + 1] * backward[t + 1]) / scale[t + 1]
        posterior = forward * backward
        posterior /= posterior.sum(axis=1, keepdims=True)
        occupancy = posterior[finite].sum(axis=0)
        loglike = float(np.sum(np.log(scale) + offsets))
        map_objective = loglike + float(np.sum(prior_counts * np.log(transition)))
        # A likelihood-only stopping rule is inappropriate for the regularized
        # transition fit. Check the actual MAP objective at current parameters.
        improvement = map_objective - previous_map
        if (np.isfinite(previous_map) and -1e-8 <= improvement
                <= 1e-6 * max(1., abs(previous_map))):
            converged = True
            break
        pair_posterior = (forward[:-1, :, None] * transition[None, :, :]
                          * (emission[1:] * backward[1:])[:, None, :])
        pair_posterior /= pair_posterior.sum(axis=(1, 2), keepdims=True)
        counts = pair_posterior.sum(axis=0) + prior_counts
        next_transition = counts / counts.sum(axis=1, keepdims=True)
        next_variances = np.maximum((posterior.T @ squared) / np.maximum(occupancy, 1e-12), floor)
        # Stop using parameter movement: MAP transition regularization need not
        # monotonically increase the unpenalized likelihood.
        change = max(float(np.max(np.abs(next_transition - transition))),
                     float(np.max(np.abs(np.log(next_variances / variances)))))
        transition, variances = next_transition, next_variances
        previous_map = map_objective
        if change < 1e-5:
            converged = True
            break
    order = np.argsort(variances)
    variances = variances[order]
    transition = transition[np.ix_(order, order)]
    return transition, variances, {
        'iterations': iteration + 1, 'converged': converged,
        'last_preupdate_training_loglike': loglike,
        'last_preupdate_map_objective': map_objective,
        'convergence_criterion': 'relative MAP objective 1e-6 or parameter movement 1e-5',
        'occupancy_fraction': (occupancy[order] / finite.sum()).tolist(),
        'variance_ratio_high_to_low': float(variances[-1] / variances[0]),
    }


def _hamilton_features(market: np.ndarray, config: PillarConfig) -> tuple[dict, list]:
    names = ('tranquil_prob', 'stressed_prob', 'crisis_prob', 'next_crisis_prob',
             'next_volatility', 'lsd')
    values = {f'hamilton_daily_{name}': np.full(len(market), np.nan) for name in names}
    fit_log = []
    transition = variances = probability = None
    last_fit = -config.refit_every
    for t in range(config.min_train, len(market)):
        if transition is None or t - last_fit >= config.refit_every:
            start = max(0, t - config.train_window)
            training = market[start:t]
            if np.isfinite(training).sum() >= config.min_train:
                transition, variances, info = _fit_hmm(training, config)
                probability = _filter_hmm(training, transition, variances)[0][-1]
                last_fit = t
                fit_log.append({'train_start': start, 'train_end_exclusive': t,
                                'first_emission_index': t,
                                'transition': transition.tolist(), 'variances': variances.tolist(),
                                **info})
        if transition is None:
            continue
        probability = _filter_hmm(market[t:t + 1], transition, variances,
                                  initial=probability @ transition)[0][0]
        next_probability = probability @ transition
        for j, state in enumerate(('tranquil', 'stressed', 'crisis')):
            values[f'hamilton_daily_{state}_prob'][t] = probability[j]
        values['hamilton_daily_next_crisis_prob'][t] = next_probability[2]
        values['hamilton_daily_next_volatility'][t] = np.sqrt(next_probability @ variances)
        values['hamilton_daily_lsd'][t] = probability[1] + 2 * probability[2]
    return values, fit_log


def _tail_counts(market: np.ndarray, config: PillarConfig) -> np.ndarray:
    """Daily loss exceeds tail_sigma times a strictly prior EWMA volatility."""
    counts = np.full(len(market), np.nan)
    variance = 0.0
    observed = 0
    for t, value in enumerate(market):
        if not np.isfinite(value):
            continue
        if observed >= config.ewma_warmup and variance > 1e-12:
            counts[t] = float(value < -config.tail_sigma * np.sqrt(variance))
        if observed == 0:
            variance = value ** 2
        else:
            variance = config.ewma_decay * variance + (1 - config.ewma_decay) * value ** 2
        observed += 1
    return counts


def _hawkes_features(counts: np.ndarray, config: PillarConfig, label: str) -> tuple[dict, list]:
    """Binned Hawkes conditional mean with a fixed normalized geometric kernel.

    lambda[t] = mu + n * driver[t]; driver[t+1] = phi*driver[t]+(1-phi)*count[t].
    Hence n is branching strength, unlike an unnormalized alpha coefficient.
    Missing observations reset the history and require a full training warmup.
    """
    prefix = f'hawkes_{label}_'
    values = {prefix + name: np.full(len(counts), np.nan)
              for name in ('intensity', 'branching', 'excitation_ratio')}
    fit_log = []
    phi = float(np.exp(np.log(.5) / config.hawkes_half_life))
    driver = np.full(len(counts), np.nan)
    state = 0.0
    segment_start = 0
    last_fit = -config.refit_every
    parameters = None
    for t, count in enumerate(counts):
        if not np.isfinite(count):
            state = 0.0
            segment_start = t + 1
            parameters = None
            last_fit = -config.refit_every
            continue
        driver[t] = state
        if t - segment_start >= config.min_train and (
                parameters is None or t - last_fit >= config.refit_every):
            start = max(segment_start, t - config.train_window)
            observations, predictors = counts[start:t], driver[start:t]
            if observations.sum() >= config.min_hawkes_events:
                rate = float(observations.mean())

                def objective(par):
                    intensity = par[0] + par[1] * predictors
                    loss = float(np.sum(intensity - observations * np.log(intensity)))
                    residual = 1 - observations / intensity
                    gradient = np.array([residual.sum(), residual @ predictors])
                    return loss, gradient

                fit = minimize(objective, np.array([max(rate * .9, 1e-6), .1]),
                               method='L-BFGS-B', jac=True,
                               bounds=[(1e-8, None), (0., .95)],
                               options={'maxiter': 100, 'ftol': 1e-12})
                if fit.success and np.isfinite(fit.x).all():
                    parameters = fit.x
                    last_fit = t
                    fit_log.append({'train_start': start, 'train_end_exclusive': t,
                                    'first_emission_index': t, 'mu': float(fit.x[0]),
                                    'branching': float(fit.x[1]), 'events': float(observations.sum()),
                                    'success': True})
        state = phi * state + (1 - phi) * count
        if parameters is not None:
            mu, branching = parameters
            values[prefix + 'intensity'][t] = mu + branching * state
            values[prefix + 'branching'][t] = branching
            # Ratio to stationary mean, not a probability of crisis.
            values[prefix + 'excitation_ratio'][t] = (
                (mu + branching * state) / (mu / (1 - branching)))
    return values, fit_log


def _spectrum(window: np.ndarray, shrinkage: float) -> tuple[float, np.ndarray]:
    correlation = np.corrcoef(window, rowvar=False)
    correlation = (1 - shrinkage) * correlation + shrinkage * np.eye(window.shape[1])
    eigenvalues, eigenvectors = np.linalg.eigh(correlation)
    vector = eigenvectors[:, -1]
    if eigenvalues[-1] - eigenvalues[-2] < 1e-10:
        # A repeated leading eigenvalue has no identifiable leading direction.
        vector = np.full(window.shape[1], np.nan)
    return float(eigenvalues[-1] / window.shape[1]), vector


def _rmt_features(panel: np.ndarray, config: PillarConfig) -> dict[str, np.ndarray]:
    names = ('fast_leading_share', 'slow_leading_share', 'fast_minus_slow',
             'fast_rotation', 'panel_n')
    values = {f'rmt_{name}': np.full(len(panel), np.nan) for name in names}
    previous_vector = np.full(panel.shape[1], np.nan)
    for t in range(config.fast_window - 1, len(panel)):
        fast = panel[t + 1 - config.fast_window:t + 1]
        slow = panel[max(0, t + 1 - config.slow_window):t + 1]
        # When available, compare fast and slow spectra on exactly the same
        # fixed-column support. No forward filling or pairwise-PSD assumption.
        support_window = slow if len(slow) == config.slow_window else fast
        support = np.isfinite(support_window).all(axis=0)
        complete_columns = np.flatnonzero(support)
        support[complete_columns] &= (
            (np.std(support_window[:, complete_columns], axis=0) > 1e-12)
            & (np.std(fast[:, complete_columns], axis=0) > 1e-12))
        n = int(support.sum())
        values['rmt_panel_n'][t] = n
        if n < 2:
            previous_vector[:] = np.nan
            continue
        share, vector = _spectrum(fast[:, support], config.covariance_shrinkage)
        values['rmt_fast_leading_share'][t] = share
        current_vector = np.full(panel.shape[1], np.nan)
        current_vector[support] = vector
        common = np.isfinite(previous_vector) & np.isfinite(current_vector)
        if common.sum() >= 2:
            old, new = previous_vector[common], current_vector[common]
            common_norm = np.linalg.norm(old) * np.linalg.norm(new)
            if common_norm > 1e-12:
                overlap = abs(float(old @ new)) / common_norm
                values['rmt_fast_rotation'][t] = 1 - np.clip(overlap, 0., 1.)
        previous_vector = current_vector
        if len(slow) == config.slow_window:
            slow_share, _ = _spectrum(slow[:, support], config.covariance_shrinkage)
            values['rmt_slow_leading_share'][t] = slow_share
            values['rmt_fast_minus_slow'][t] = share - slow_share
    return values


def build_pillar_features(market_returns: np.ndarray, factor_returns: np.ndarray, *,
                          daily_jump_counts: np.ndarray | None = None,
                          config: PillarConfig | None = None) -> PillarFeatureResult:
    """Return chronological, same-length research features from all three pillars.

    Inputs use decimal returns and must already align on ascending trading dates.
    factor_returns has a fixed column identity across time, with 2..64 columns.
    NaN denotes unavailable data. Do not use retrospectively selected survivors
    or silently reindex changing constituents into the same column identity.
    daily_jump_counts optionally supplies aggregated genuine intraday counts;
    its channel stays separate from the daily tail proxy at every date.
    """
    config = config or PillarConfig()
    market = np.asarray(market_returns, dtype=float)
    panel = np.asarray(factor_returns, dtype=float)
    if market.ndim != 1 or panel.ndim != 2 or len(market) != len(panel):
        raise ValueError('market_returns and factor_returns must align as (n,) and (n,k)')
    if not 2 <= panel.shape[1] <= 64:
        raise ValueError('factor_returns requires 2..64 fixed columns')
    if np.isinf(market).any() or np.isinf(panel).any():
        raise ValueError('Use finite observations or NaN, never infinity')
    if daily_jump_counts is not None:
        counts = np.asarray(daily_jump_counts, dtype=float)
        if counts.shape != market.shape:
            raise ValueError('daily_jump_counts must align with market_returns')
        if np.isinf(counts).any() or np.any(counts[np.isfinite(counts)] < 0):
            raise ValueError('daily_jump_counts must be nonnegative finite counts or NaN')
        if np.any(counts[np.isfinite(counts)] != np.floor(counts[np.isfinite(counts)])):
            raise ValueError('daily_jump_counts must contain integer counts')
    values, hmm_fits = _hamilton_features(market, config)
    values.update(_rmt_features(panel, config))
    hawkes, hawkes_fits = _hawkes_features(_tail_counts(market, config), config, 'daily')
    values.update(hawkes)
    diagnostics = {
        'config': asdict(config),
        'observation_cutoff': 'after close t; parameters estimated through t-1',
        'hamilton_fits': hmm_fits,
        'hawkes_daily_fits': hawkes_fits,
        'daily_hawkes_event': 'return[t] < -tail_sigma * prior_EWMA_sigma[t]',
        'daily_hawkes_count_model': 'quasi-Poisson binary daily exceedance proxy',
        'rmt_support': 'fully observed, nonconstant fixed columns; common fast/slow support',
        'original_engines_modified': False,
    }
    if daily_jump_counts is not None:
        extra, extra_fits = _hawkes_features(counts, config, 'intraday_count')
        values.update(extra)
        diagnostics['hawkes_intraday_count_fits'] = extra_fits
    return PillarFeatureResult(values=values, diagnostics=diagnostics)
