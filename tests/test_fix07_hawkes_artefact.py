"""FIX07 — a Hawkes fit is persisted well enough to rebuild its intensity.

Audit findings A08 and A09:

* the production writer stored `"alpha_beta": None` and `"flag": "none"`, so
  the fitted kernel was discarded and the sector flag was a constant standing
  in for a measurement;
* the backfill selected the LATEST universe snapshot and applied it to
  historical windows.

The acceptance criterion is literal: a saved artefact reconstructs its own
intensity. These tests fit a real stream, save it, throw the fit away, and
rebuild `lambda_t` from the artefact.
"""
from __future__ import annotations

import numpy as np
import pytest

from seraph.pillars.hawkes.artefact import (
    BasketIdentity,
    FitDiagnostics,
    HawkesFitArtefact,
    artefact_from_fit,
)
from seraph.pillars.hawkes.engine import excitation_path, fit_discrete_hawkes

N_SLOTS = 25


@pytest.fixture
def stream():
    """A synthetic session-structured count stream the estimator can fit."""
    rng = np.random.default_rng(11)
    sessions, per_session = 40, N_SLOTS
    counts, starts, tod = [], [], []
    excitation = 0.0
    profile = 0.8 + 0.4 * np.sin(np.linspace(0, np.pi, per_session))
    for _ in range(sessions):
        excitation = 0.0
        for slot in range(per_session):
            rate = 1.5 * profile[slot] + 0.35 * excitation
            drawn = rng.poisson(max(rate, 1e-6))
            counts.append(drawn)
            starts.append(slot == 0)
            tod.append(slot)
            excitation = 0.5 * excitation + drawn
    return (np.array(counts, dtype=float), np.array(starts, dtype=bool),
            np.array(tod), profile / profile.mean())


@pytest.fixture
def basket():
    return BasketIdentity(basis="point_in_time",
                          symbols=("RELIANCE", "TCS", "TATASTEEL"),
                          rebalance_date="2024-01-01")


@pytest.fixture
def artefact(stream, basket):
    counts, starts, tod, profile = stream
    fit = fit_discrete_hawkes(counts, starts, profile, tod)
    assert fit is not None, "the fixture must be fittable"
    return artefact_from_fit(
        fit, as_of="2024-06-28", training_start="2024-01-02",
        tod_profile=profile, n_slots=N_SLOTS, basket=basket,
        n_neg=int(counts.sum()), n_pos=int(counts.sum() * 1.2),
        n_sessions=40, mts=0.12)


# --------------------------------------------- A08: the fit is kept


def test_the_fitted_parameters_survive(artefact):
    described = artefact.describe()["parameters"]
    for name in ("mu", "alpha", "phi", "dispersion", "branching_ratio"):
        assert described[name] is not None
        assert np.isfinite(described[name])


def test_the_seasonality_profile_survives(artefact):
    seasonality = artefact.describe()["seasonality"]
    assert seasonality["n_slots"] == N_SLOTS
    assert len(seasonality["profile"]) == N_SLOTS


def test_the_training_window_and_diagnostics_survive(artefact):
    described = artefact.describe()
    assert described["training_start"] == "2024-01-02"
    assert described["as_of"] == "2024-06-28"
    diagnostics = described["diagnostics"]
    assert diagnostics["n_sessions"] == 40 and diagnostics["n_bars"] > 0
    assert isinstance(diagnostics["converged"], bool)


def test_a_saved_artefact_reconstructs_its_own_intensity(stream, artefact):
    """The acceptance criterion, taken literally."""
    counts, starts, tod, profile = stream
    original = excitation_path(counts, starts, artefact.mu, artefact.alpha,
                               artefact.phi, profile, tod)
    # Round-trip through JSON, so only what was persisted is available.
    revived = HawkesFitArtefact.from_describe(
        __import__("json").loads(artefact.to_json()))
    rebuilt = revived.reconstruct_intensity(counts, starts, tod)
    assert np.allclose(original, rebuilt, rtol=1e-9, atol=1e-12)


def test_parameters_that_do_not_reproduce_the_headline_number_are_refused(basket):
    with pytest.raises(ValueError, match="not reconstructible"):
        HawkesFitArtefact(
            as_of="2024-06-28", training_start="2024-01-02",
            mu=1.0, alpha=0.05, phi=0.5, dispersion=1.0,
            tod_profile=(1.0,), n_slots=1, basket=basket,
            branching_ratio=0.9,            # alpha/(1-phi) = 0.1, not 0.9
            diagnostics=FitDiagnostics(True, 10, 1, 1, 1))


def test_a_non_stationary_fit_is_refused(basket):
    with pytest.raises(ValueError, match="FR11 stationarity"):
        HawkesFitArtefact(
            as_of="2024-06-28", training_start="2024-01-02",
            mu=1.0, alpha=0.6, phi=0.4, dispersion=1.0,
            tod_profile=(1.0,), n_slots=1, basket=basket,
            branching_ratio=1.0, diagnostics=FitDiagnostics(True, 10, 1, 1, 1))


def test_a_mismatched_seasonality_length_is_refused(basket):
    with pytest.raises(ValueError, match="slots but"):
        HawkesFitArtefact(
            as_of="2024-06-28", training_start="2024-01-02",
            mu=1.0, alpha=0.05, phi=0.5, dispersion=1.0,
            tod_profile=(1.0, 1.0), n_slots=5, basket=basket,
            branching_ratio=0.1, diagnostics=FitDiagnostics(True, 10, 1, 1, 1))


def test_an_absent_sector_baseline_emits_no_flag_rather_than_a_constant(artefact):
    described = artefact.describe()
    assert described["sector_baselines"] is None
    assert "rather than a constant 'none'" in described["sector_flags_note"]


# -------------------------------------------- artefact identity


def test_the_same_fit_gives_the_same_identity(stream, basket):
    counts, starts, tod, profile = stream
    fit = fit_discrete_hawkes(counts, starts, profile, tod)
    common = dict(as_of="2024-06-28", training_start="2024-01-02",
                  tod_profile=profile, n_slots=N_SLOTS, basket=basket,
                  n_neg=10, n_pos=12, n_sessions=40)
    assert artefact_from_fit(fit, **common).artefact_id == \
        artefact_from_fit(fit, **common).artefact_id


def test_a_different_basket_gives_a_different_identity(stream, basket, artefact):
    counts, starts, tod, profile = stream
    fit = fit_discrete_hawkes(counts, starts, profile, tod)
    other = BasketIdentity(basis="point_in_time", symbols=("RELIANCE", "INFY"),
                           rebalance_date="2024-01-01")
    rebuilt = artefact_from_fit(
        fit, as_of="2024-06-28", training_start="2024-01-02", tod_profile=profile,
        n_slots=N_SLOTS, basket=other, n_neg=int(counts.sum()),
        n_pos=int(counts.sum() * 1.2), n_sessions=40, mts=0.12)
    assert rebuilt.artefact_id != artefact.artefact_id


def test_a_different_window_gives_a_different_identity(stream, basket, artefact):
    counts, starts, tod, profile = stream
    fit = fit_discrete_hawkes(counts, starts, profile, tod)
    moved = artefact_from_fit(
        fit, as_of="2024-07-05", training_start="2024-01-02", tod_profile=profile,
        n_slots=N_SLOTS, basket=basket, n_neg=int(counts.sum()),
        n_pos=int(counts.sum() * 1.2), n_sessions=40, mts=0.12)
    assert moved.artefact_id != artefact.artefact_id


# ------------------------------------- A09: the basket is point-in-time


def test_the_latest_snapshot_basis_is_rejected_for_a_historical_window():
    basket = BasketIdentity(basis="latest_snapshot", symbols=("A", "B"))
    problems = basket.validate(window_end="2019-06-28")
    assert any("audit finding A09" in p for p in problems)
    assert any("point_in_time" in p for p in problems)


def test_a_point_in_time_basket_must_predate_its_window():
    future = BasketIdentity(basis="point_in_time", symbols=("A",),
                            rebalance_date="2025-01-01")
    assert any("did not exist yet" in p
               for p in future.validate(window_end="2024-06-28"))
    valid = BasketIdentity(basis="point_in_time", symbols=("A",),
                           rebalance_date="2024-01-01")
    assert valid.validate(window_end="2024-06-28") == []


def test_a_point_in_time_basket_must_name_its_rebalance_date():
    basket = BasketIdentity(basis="point_in_time", symbols=("A",))
    assert any("must name its rebalance date" in p
               for p in basket.validate(window_end="2024-06-28"))


def test_a_fixed_research_basket_must_state_its_limitation():
    bare = BasketIdentity(basis="fixed_research_basket", symbols=("A",))
    assert any("survivorship limitation" in p
               for p in bare.validate(window_end="2024-06-28"))
    declared = BasketIdentity(
        basis="fixed_research_basket", symbols=("A",),
        note="frozen 2024 membership; survivorship bias is accepted and declared")
    assert declared.validate(window_end="2024-06-28") == []


def test_an_empty_basket_is_a_problem():
    assert any("empty" in p for p in BasketIdentity(
        basis="point_in_time", symbols=(), rebalance_date="2024-01-01"
    ).validate(window_end="2024-06-28"))


def test_the_basket_digest_is_order_independent():
    a = BasketIdentity(basis="point_in_time", symbols=("A", "B"),
                       rebalance_date="2024-01-01")
    b = BasketIdentity(basis="point_in_time", symbols=("B", "A"),
                       rebalance_date="2024-01-01")
    assert a.digest == b.digest
