"""FIX04 — the FR6 state variable's bins are fitted causally and versioned.

Audit finding A05: `_bucket()` computed its quantile edges from the entire
supplied array, so the bin assigned at time t depended on observations after t.
The reproduction: appending 20 future observations changed **28 of 40** earlier
bucket assignments. That is leakage in the state the Hawkes conditional
intensity is indexed by.

These tests are written as falsification attempts — perturb the future, assert
the past did not move.
"""
from __future__ import annotations

import numpy as np
import pytest

from seraph.features.jump_extraction import (
    UNDETERMINED,
    apply_quantile_bins,
    fit_quantile_bins,
    state_variable,
    trailing_quantile_bucket,
)

CAUSAL = [
    pytest.param(dict(basis="train_prefix", train=30), id="train_prefix"),
    pytest.param(dict(basis="trailing_window", window=25, min_history=8),
                 id="trailing_window"),
]


def series(n=40, seed=3):
    return np.random.default_rng(seed).normal(size=n)


def extended(base, extra=20, shift=5.0, seed=11):
    """The same history with a violently different future appended."""
    future = np.random.default_rng(seed).normal(size=extra) + shift
    return np.concatenate([base, future])


# -------------------------------------------------- future-append invariance


@pytest.mark.parametrize("kwargs", CAUSAL)
def test_appending_the_future_leaves_every_earlier_bin_unchanged(kwargs):
    base = series()
    before = state_variable(base, base, n_quantiles=5, **kwargs)["s_t"]
    after = state_variable(extended(base), extended(base), n_quantiles=5, **kwargs)["s_t"]
    assert np.array_equal(before, after[:base.size])


@pytest.mark.parametrize("kwargs", CAUSAL)
def test_truncating_the_future_leaves_every_earlier_bin_unchanged(kwargs):
    full = extended(series())
    long_run = state_variable(full, full, n_quantiles=5, **kwargs)["s_t"]
    short = full[:40]
    short_run = state_variable(short, short, n_quantiles=5, **kwargs)["s_t"]
    assert np.array_equal(long_run[:40], short_run)


def test_the_legacy_full_sample_path_still_leaks_and_says_so():
    """Kept for artefact reproduction, and honest about what it is."""
    base = series()
    before = state_variable(base, base, n_quantiles=5, basis="full_sample")
    after = state_variable(extended(base), extended(base), n_quantiles=5,
                           basis="full_sample")
    changed = int((before["s_t"] != after["s_t"][:base.size]).sum())
    assert changed > 0, "this path is retained precisely because it leaks"
    assert before["transform"]["causal"] is False
    assert "audit finding A05" in before["transform"]["warning"]


def test_the_basis_must_be_declared():
    base = series()
    with pytest.raises(TypeError):
        state_variable(base, base)                       # no basis
    with pytest.raises(ValueError, match="positive `window`"):
        state_variable(base, base, basis="trailing_window")
    with pytest.raises(ValueError, match="positive `train`"):
        state_variable(base, base, basis="train_prefix")


# ------------------------------------------------------------- transform id


def test_the_transform_carries_a_versioned_content_hashed_identity():
    base = series()
    a = state_variable(base, base, n_quantiles=5, basis="train_prefix", train=30)
    b = state_variable(base, base, n_quantiles=5, basis="train_prefix", train=30)
    assert a["transform"]["artefact_id"] == b["transform"]["artefact_id"]
    assert a["transform"]["version"] and a["transform"]["causal"] is True


def test_a_different_fitting_basis_gives_a_different_identity():
    base = series()
    ids = {
        state_variable(base, base, n_quantiles=5, basis="train_prefix",
                       train=30)["transform"]["artefact_id"],
        state_variable(base, base, n_quantiles=5, basis="train_prefix",
                       train=20)["transform"]["artefact_id"],
        state_variable(base, base, n_quantiles=5, basis="trailing_window",
                       window=25, min_history=8)["transform"]["artefact_id"],
        state_variable(base, base, n_quantiles=5,
                       basis="full_sample")["transform"]["artefact_id"],
    }
    assert len(ids) == 4, "a regenerated feature must not reuse an old identity"


def test_changing_the_data_changes_a_fitted_transform_identity():
    base = series()
    other = series(seed=99)
    first = state_variable(base, base, n_quantiles=5, basis="train_prefix", train=30)
    second = state_variable(other, other, n_quantiles=5, basis="train_prefix", train=30)
    assert first["transform"]["artefact_id"] != second["transform"]["artefact_id"]


# --------------------------------------------------- unknown is not typical


def test_insufficient_trailing_history_is_undetermined_not_the_middle_bucket():
    base = series(60)
    codes = trailing_quantile_bucket(base, 5, window=25, min_history=20)
    assert codes[0] == UNDETERMINED and codes[5] == UNDETERMINED
    assert (codes[:20] == UNDETERMINED).all()
    assert (codes[30:] != UNDETERMINED).all()
    # The middle bucket for n=5 is 3; an unknown must never be reported as one.
    assert UNDETERMINED != 3


def test_a_non_finite_observation_has_no_bin():
    base = series()
    base[7] = np.nan
    bins = fit_quantile_bins(base, 5, basis="train_prefix", train=30)
    codes = apply_quantile_bins(base, bins)
    assert codes[7] == UNDETERMINED
    assert set(codes[np.isfinite(base)]) <= {1, 2, 3, 4, 5}


def test_a_joint_state_with_an_unknown_coordinate_is_unknown():
    base = series(60)
    out = state_variable(base, base, n_quantiles=5, basis="trailing_window",
                         window=25, min_history=20)
    unknown = out["spread_quintile"] == UNDETERMINED
    assert (out["s_t"][unknown] == UNDETERMINED).all()
    assert out["transform"]["coverage"]["undetermined"] == int(unknown.sum())


def test_a_degenerate_series_yields_no_bins_rather_than_fake_spread():
    flat = np.full(40, 2.5)
    bins = fit_quantile_bins(flat, 5, basis="train_prefix", train=30)
    assert bins.degenerate is True
    assert (apply_quantile_bins(flat, bins) == UNDETERMINED).all()


# ------------------------------------------------------- applied transform


def test_applying_fixed_edges_never_inspects_the_data_being_assigned():
    train = series(30)
    bins = fit_quantile_bins(train, 5, basis="train_prefix", train=30)
    calm = apply_quantile_bins(np.array([0.0]), bins)
    with_extremes = apply_quantile_bins(np.array([0.0, 50.0, -50.0]), bins)
    assert calm[0] == with_extremes[0], \
        "an assignment must not depend on the other values in its batch"
    assert bins.causal is True and bins.fitted_on == 30
