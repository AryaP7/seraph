"""Research C5/C6/C7 extensions: causal replay and independent math checks."""
import itertools

import numpy as np
import pytest

from seraph.prediction.pillars import (
    PillarConfig,
    _filter_hmm,
    build_pillar_features,
)


def _data(n=220):
    rng = np.random.default_rng(581)
    market = rng.normal(0, .012, n)
    market[25::25] = -.06
    panel = market[:, None] + rng.normal(0, .018, (n, 5))
    counts = rng.poisson(.3, n).astype(float)
    return market, panel, counts


def _config():
    return PillarConfig(min_train=60, train_window=120, refit_every=31,
                        fast_window=20, slow_window=60, hmm_iterations=8,
                        min_hawkes_events=3)


def test_all_pillar_features_are_prefix_invariant():
    """Adding future observations cannot revise an already emitted feature."""
    market, panel, counts = _data()
    full = build_pillar_features(market, panel, daily_jump_counts=counts,
                                config=_config())
    cut = 153
    prefix = build_pillar_features(market[:cut], panel[:cut],
                                  daily_jump_counts=counts[:cut], config=_config())
    assert {name.split('_')[0] for name in full.values} == {
        'hawkes', 'rmt', 'hamilton'}
    for name in full.values:
        np.testing.assert_allclose(full.values[name][:cut], prefix.values[name],
                                   rtol=0, atol=0, equal_nan=True)


def test_hamilton_filter_matches_exhaustive_state_path_enumeration():
    observations = np.array([.007, -.03, .002])
    transition = np.array([[.9, .08, .02], [.1, .8, .1], [.05, .15, .8]])
    variances = np.array([.005 ** 2, .015 ** 2, .04 ** 2])
    initial = np.array([.6, .3, .1])
    filtered, _ = _filter_hmm(observations, transition, variances, initial)
    for t in range(len(observations)):
        weights = np.zeros(3)
        for states in itertools.product(range(3), repeat=t + 1):
            weight = initial[states[0]]
            for j, state in enumerate(states):
                if j:
                    weight *= transition[states[j - 1], state]
                weight *= np.exp(-observations[j] ** 2 / (2 * variances[state])) / np.sqrt(
                    2 * np.pi * variances[state])
            weights[states[-1]] += weight
        np.testing.assert_allclose(filtered[t], weights / weights.sum(), atol=1e-12)


def test_missing_hamilton_observation_propagates_without_fake_measurement():
    transition = np.array([[.9, .08, .02], [.1, .8, .1], [.05, .15, .8]])
    variances = np.array([.0001, .0004, .0016])
    initial = np.array([.7, .2, .1])
    filtered, _ = _filter_hmm(np.array([.01, np.nan]), transition, variances, initial)
    np.testing.assert_allclose(filtered[1], filtered[0] @ transition, atol=1e-14)


def test_refits_are_strictly_past_and_probability_outputs_are_valid():
    market, panel, counts = _data()
    result = build_pillar_features(market, panel, daily_jump_counts=counts, config=_config())
    for fit in result.diagnostics['hamilton_fits']:
        assert fit['train_end_exclusive'] == fit['first_emission_index']
        assert fit['train_start'] < fit['train_end_exclusive']
        transition = np.array(fit['transition'])
        np.testing.assert_allclose(transition.sum(axis=1), 1)
        assert np.all(np.diff(fit['variances']) >= 0)
    probabilities = np.column_stack([result.values[f'hamilton_daily_{state}_prob']
                                     for state in ('tranquil', 'stressed', 'crisis')])
    complete = np.isfinite(probabilities).all(axis=1)
    assert complete.sum() > 100
    np.testing.assert_allclose(probabilities[complete].sum(axis=1), 1)
    assert np.all((probabilities[complete] >= 0) & (probabilities[complete] <= 1))
    for channel in ('daily', 'intraday_count'):
        assert result.diagnostics[f'hawkes_{channel}_fits']
        for fit in result.diagnostics[f'hawkes_{channel}_fits']:
            assert fit['train_end_exclusive'] == fit['first_emission_index']
            assert 0 <= fit['branching'] <= .95


def test_missing_intraday_history_is_not_replaced_with_zero_counts():
    market, panel, counts = _data()
    counts[:120] = np.nan
    result = build_pillar_features(market, panel, daily_jump_counts=counts, config=_config())
    assert np.isnan(result.values['hawkes_intraday_count_intensity'][:180]).all()
    assert np.isfinite(result.values['hawkes_daily_intensity'][100:]).any()


def test_constant_factor_is_excluded_and_high_dimension_is_rejected():
    market, panel, _ = _data()
    panel[:, 0] = 0
    result = build_pillar_features(market, panel, config=_config())
    assert np.all(result.values['rmt_panel_n'][60:] == 4)
    share = result.values['rmt_fast_leading_share'][60:]
    assert np.isfinite(share).all()
    assert np.all((share >= .25 - 1e-10) & (share <= 1))
    with pytest.raises(ValueError, match='64'):
        build_pillar_features(market, np.zeros((len(market), 65)))


def test_rmt_does_not_invent_direction_when_leading_eigenvalue_is_repeated():
    market, _, _ = _data()
    panel = np.tile(np.array([[1., 0.], [0., 1.], [-1., 0.], [0., -1.]]), (55, 1))
    result = build_pillar_features(market, panel, config=_config())
    np.testing.assert_allclose(result.values['rmt_fast_leading_share'][60:], .5)
    assert np.isnan(result.values['rmt_fast_rotation']).all()


def test_invalid_inputs_fail_explicitly():
    market, panel, counts = _data()
    with pytest.raises(ValueError, match='align'):
        build_pillar_features(market, panel[:-1])
    with pytest.raises(ValueError, match='nonnegative'):
        counts[80] = -1
        build_pillar_features(market, panel, daily_jump_counts=counts)
    with pytest.raises(ValueError, match='integer'):
        counts[80] = .5
        build_pillar_features(market, panel, daily_jump_counts=counts)
