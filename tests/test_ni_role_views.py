"""What each role needs from the same facts.

Role navigation existed; role-specific news intelligence did not — every role
saw the identical rail, so the question each role actually has went
unanswered.

The retail view's second half matters more than its first: **an unmapped
holding is not a holding with no risk.** It is one this system cannot speak
about, and showing a clean screen for it is the most misleading output
available here. Two different reasons are distinguished, because they call for
different work: a holding that does not resolve at all, and one that resolves
to an issuer with no sector so sector news cannot route to it.

These are three projections of one channel, not three pipelines. A number that
differed between roles would mean one of them was wrong.
"""
from __future__ import annotations

import pytest

from seraph.dashboard.news_view import news_channel
from seraph.news.acquisition import NewsStore
from seraph.news.registry import load_master_data
from seraph.news.roles import ROLES, role_view

NOW = "2026-10-18T09:00:00+05:30"


@pytest.fixture(scope="module")
def channel_and_master(tmp_path_factory):
    import pathlib
    store = NewsStore(pathlib.Path(__file__).resolve().parents[1]
                      / "prototype_runs/news-intelligence-pilot.sqlite")
    master, _ = load_master_data()
    from seraph.news.acquisition import _now
    return news_channel(store, master, decision_ts=_now(), limit=6000), master, store


# ------------------------------------------------------------- retail

def test_a_holding_with_a_documented_route_is_listed(channel_and_master):
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "retail",
                     holdings=[{"symbol": "JSW Steel Limited"}])
    assert view["items"]
    assert view["items"][0]["resolved_to"] == "jsw_steel"


def test_an_unresolvable_holding_is_uncovered_not_silently_clean(channel_and_master):
    """The warning this view exists for."""
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "retail",
                     holdings=[{"symbol": "Some Unlisted Pvt Ltd"}])
    assert view["items"] == []
    assert view["uncovered"]
    assert "NOT a finding that it is unaffected" in view["uncovered"][0]["reason"]


def test_a_resolved_issuer_with_no_sector_is_a_different_uncovered_reason(
        channel_and_master):
    """It resolves, so it is not unknown — but sector news cannot route to it,
    which is a different gap calling for different work."""
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "retail",
                     holdings=[{"symbol": "LTM Limited"}])
    assert view["uncovered"]
    reason = view["uncovered"][0]
    assert reason["resolved_to"] == "ltm_limited"
    assert "no sector" in reason["reason"]


def test_retail_never_offers_a_loss_probability(channel_and_master):
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "retail",
                     holdings=[{"symbol": "JSW Steel Limited"}])
    joined = " ".join(view["notes"]).lower()
    assert "probability of loss" in joined  # as a denial, not a claim
    assert "none of this is a probability of loss" in joined
    assert "qualitative" in joined


def test_the_uncovered_count_is_stated_not_left_to_be_inferred(channel_and_master):
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "retail", holdings=[
        {"symbol": "JSW Steel Limited"}, {"symbol": "Some Unlisted Pvt Ltd"}])
    assert any("do not" in note for note in view["notes"])


# ------------------------------------------------------ institutional

def test_institutional_shows_both_sides_where_they_exist(channel_and_master):
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "institutional")
    assert any(item["opposing"] for item in view["items"])


def test_institutional_states_how_many_relationships_are_unsized(
        channel_and_master):
    """A direction without a size supports a question, not a position."""
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "institutional")
    assert any("UNSIZED" in note for note in view["notes"])


def test_institutional_carries_the_limitations_not_just_the_direction(
        channel_and_master):
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "institutional")
    assert view["items"]
    assert view["items"][0]["limitations"]


def test_institutional_never_computes_a_net(channel_and_master):
    channel, master, _ = channel_and_master
    view = role_view(channel, master, "institutional")
    assert any("net is not computed" in note for note in view["notes"])


# ---------------------------------------------------------- regulator

def test_regulator_sees_coverage_before_anything_else(channel_and_master):
    channel, master, store = channel_and_master
    view = role_view(channel, master, "regulator", store=store)
    assert view["items"][0]["kind"] == "coverage"


def test_regulator_sees_acquisition_health_separately_from_data_age(
        channel_and_master):
    channel, master, store = channel_and_master
    view = role_view(channel, master, "regulator", store=store)
    acquisition = next(i for i in view["items"] if i["kind"] == "acquisition")
    assert "worker_state" in acquisition
    assert "stale" in acquisition


def test_regulator_sees_unresolved_references(channel_and_master):
    channel, master, store = channel_and_master
    view = role_view(channel, master, "regulator", store=store)
    assert any(i["kind"] == "unresolved" for i in view["items"])


def test_regulator_is_told_coverage_is_not_a_market_statement(
        channel_and_master):
    channel, master, store = channel_and_master
    view = role_view(channel, master, "regulator", store=store)
    joined = " ".join(view["notes"])
    assert "not about the market" in joined
    assert "not a quiet day" in joined


# ------------------------------------------------------ one set of facts

def test_every_role_is_a_projection_of_the_same_channel(channel_and_master):
    """A number that differs between roles means one of them is wrong."""
    channel, master, store = channel_and_master
    institutional = role_view(channel, master, "institutional")
    assert len(institutional["items"]) == len(channel["estimates"])

    regulator = role_view(channel, master, "regulator", store=store)
    scope = next(i for i in regulator["items"] if i["kind"] == "scope")
    assert scope["in_scope"] == channel["scope"]["in_scope"]


def test_an_unknown_role_is_refused(channel_and_master):
    channel, master, _ = channel_and_master
    with pytest.raises(ValueError, match="unknown role"):
        role_view(channel, master, "administrator")


@pytest.mark.parametrize("role", ROLES)
def test_every_role_states_its_limitations(channel_and_master, role):
    channel, master, store = channel_and_master
    view = role_view(channel, master, role, holdings=[], store=store)
    assert view["notes"], f"{role} offers no caveat at all"
