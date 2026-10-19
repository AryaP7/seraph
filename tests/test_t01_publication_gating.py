"""T01 — publication fails closed (audit finding R02).

The audit reproduced three ways a replay could claim currency:

* a live-capable feed with no evaluator produced `publishable=true, csrs=null`;
* `liveness_of()` judged currency from the *evaluation* timestamp, so a recent
  archive point displayed `CURRENT MARKET READING` while its own payload said
  no feed was configured;
* `MarketClock.recency()` accepted a future timestamp as live — age −1435
  minutes, permission granted.

Plan §14.1 R02 requires: null score, future time, recent replay, disconnected
feed, stale required input, incomplete warmup and insufficient coverage each
produce an explicit non-current state.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from seraph.live import BarBuilder, LiveLoop, MarketClock, ReplayFeed, Tick
from seraph.live.publication import (
    MAX_CLOCK_SKEW,
    FeedProvenance,
    InputProvenance,
    PublicationPolicy,
    assess_publication,
    explain,
    valid_csrs_contract,
)
from seraph.shared_types import IST, ist_timestamp

NOW = datetime(2026, 10, 16, 11, 30, tzinfo=IST)
GOOD_CSRS = {"csrs": 0.42}


def live_feed(**overrides):
    base = dict(registered=True, authenticated=True, connected=True,
                source_kind="broker_websocket")
    base.update(overrides)
    return FeedProvenance(**base)


def good_input(**overrides):
    base = dict(name="bar:X", observed_at=NOW - timedelta(minutes=5),
                received_at=NOW - timedelta(minutes=5), mandatory=True)
    base.update(overrides)
    return InputProvenance(**base)


def assess(**overrides):
    base = dict(mode="live_shadow", csrs=GOOD_CSRS, feed=live_feed(),
                as_of=NOW - timedelta(minutes=1), now=NOW,
                warmup_complete=True, calendar_verified=True,
                required_inputs=(good_input(),), has_eligible_information=True)
    base.update(overrides)
    return assess_publication(**base)


# ------------------------------------------------- the happy path exists


def test_a_complete_live_decision_is_publishable():
    outcome = assess()
    assert outcome.current_allowed is True
    assert outcome.reasons == ()
    assert outcome.label == "CURRENT MARKET READING"


# ------------------------------------------- each condition fails closed


def test_a_missing_score_is_not_publishable():
    """The exact defect: live feed, no evaluator, null score."""
    outcome = assess(csrs=None)
    assert outcome.current_allowed is False
    assert "no_valid_score" in outcome.reasons


@pytest.mark.parametrize("bad", [
    {}, {"csrs": None}, {"csrs": "high"}, {"csrs": float("nan")},
    {"csrs": 1.4}, {"csrs": -0.1},
])
def test_an_invalid_score_contract_is_rejected(bad):
    assert valid_csrs_contract(bad) is False
    assert "no_valid_score" in assess(csrs=bad).reasons


def test_a_replay_is_not_publishable_however_recent():
    outcome = assess(mode="historical_replay")
    assert outcome.current_allowed is False
    assert "not_live_mode" in outcome.reasons
    assert outcome.label.startswith("HISTORICAL REPLAY")


def test_a_future_decision_time_is_rejected():
    outcome = assess(as_of=NOW + timedelta(days=1))
    assert "future_decision" in outcome.reasons


def test_clock_skew_tolerance_does_not_admit_real_future_time():
    inside = assess(as_of=NOW + MAX_CLOCK_SKEW - timedelta(seconds=1))
    outside = assess(as_of=NOW + MAX_CLOCK_SKEW + timedelta(seconds=1))
    assert "future_decision" not in inside.reasons
    assert "future_decision" in outside.reasons


def test_an_unverified_or_disconnected_feed_is_rejected():
    assert "unverified_feed" in assess(feed=live_feed(authenticated=False)).reasons
    assert "unverified_feed" in assess(feed=live_feed(registered=False)).reasons
    assert "feed_disconnected" in assess(feed=live_feed(connected=False)).reasons


def test_incomplete_warmup_is_rejected():
    assert "warmup_incomplete" in assess(warmup_complete=False).reasons


def test_an_unverified_calendar_is_rejected():
    assert "calendar_unverified" in assess(calendar_verified=False).reasons


def test_an_empty_information_set_is_rejected():
    assert "empty_information_set" in assess(has_eligible_information=False).reasons


def test_a_failed_computation_is_rejected():
    assert "computation_failed" in assess(computation="failed").reasons


# -------------------------------------------------- per-input provenance


def test_an_input_that_arrived_after_the_cutoff_is_rejected():
    """Causality: skew tolerance never makes future information eligible."""
    late = good_input(received_at=NOW)
    outcome = assess(as_of=NOW - timedelta(minutes=5), required_inputs=(late,))
    assert "bar:X:not_known_at_cutoff" in outcome.reasons


def test_an_input_with_no_recorded_arrival_is_rejected():
    unknown = good_input(received_at=None)
    assert "bar:X:unknown_availability" in assess(required_inputs=(unknown,)).reasons


def test_a_future_input_observation_is_rejected():
    future = good_input(observed_at=NOW + timedelta(hours=2))
    assert "bar:X:future_input" in assess(required_inputs=(future,)).reasons


def test_a_stale_input_is_rejected_against_its_own_budget():
    stale = good_input(received_at=NOW - timedelta(hours=3),
                       freshness_budget=timedelta(minutes=30))
    reasons = assess(required_inputs=(stale,)).reasons
    assert any(r.startswith("bar:X:stale_") for r in reasons)


def test_insufficient_coverage_is_rejected():
    thin = good_input(coverage=0.4)
    assert "bar:X:coverage_0.40" in assess(required_inputs=(thin,)).reasons


def test_an_optional_input_does_not_block_publication():
    """C8 structural/transient absence survives: not every pillar must emit."""
    optional = good_input(name="pillar:hamilton", mandatory=False,
                          received_at=None)
    outcome = assess(required_inputs=(good_input(), optional))
    assert outcome.current_allowed is True


# ------------------------------------------------- reasons are explained


def test_every_reason_renders_as_a_sentence_not_a_code():
    outcome = assess(csrs=None, feed=live_feed(connected=False),
                     warmup_complete=False,
                     required_inputs=(good_input(received_at=None),))
    sentences = explain(outcome)
    assert len(sentences) == len(outcome.reasons)
    assert all(" " in s for s in sentences), "a bare code is not an explanation"
    assert any("no valid score" in s for s in sentences)
    assert any("no recorded arrival time" in s for s in sentences)


# ------------------------------------------------------ the clock itself


def test_the_clock_rejects_a_future_observation():
    """Audit probe: age −1435 minutes previously returned `live`."""
    clock = MarketClock()
    future = ist_timestamp(NOW + timedelta(days=1))
    recency = clock.recency(future, at=NOW)
    assert recency.state == "historical_only"
    assert recency.is_live is False and recency.may_publish_as_current is False
    assert "FUTURE" in recency.note


# ----------------------------------------------------- the loop wiring


def ticks_at(symbol, hour, minute, prices):
    base = datetime(2026, 10, 16, hour, minute, tzinfo=IST)
    return [Tick(symbol=symbol, ts=ist_timestamp(base + timedelta(seconds=i * 30)),
                 last_price=p, source_kind="replay")
            for i, p in enumerate(prices)]


def test_the_loop_without_an_evaluator_is_never_publishable():
    """The audit's exact reproduction, now failing closed."""
    loop = LiveLoop(ReplayFeed(ticks_at("X", 11, 0, [100, 101])),
                    clock=MarketClock(), mode="live_shadow",
                    warmup_complete=True)
    loop.connect(["X"])
    decision = loop.tick(at=datetime(2026, 10, 16, 11, 6, tzinfo=IST))
    assert decision.bars_closed == 1
    assert decision.csrs is None
    assert decision.publishable is False
    assert "no_valid_score" in decision.publication["reasons"]


def test_an_evaluator_that_raises_is_reported_not_published():
    def boom(bars, ts):
        raise RuntimeError("pillar unavailable")
    loop = LiveLoop(ReplayFeed(ticks_at("X", 11, 0, [100, 101])),
                    clock=MarketClock(), evaluate=boom, warmup_complete=True)
    loop.connect(["X"])
    decision = loop.tick(at=datetime(2026, 10, 16, 11, 6, tzinfo=IST))
    assert decision.publishable is False
    assert "computation_failed" in decision.publication["reasons"]


def test_the_decision_carries_every_reason_it_was_refused():
    loop = LiveLoop(ReplayFeed(ticks_at("X", 11, 0, [100, 101])),
                    clock=MarketClock(), evaluate=lambda b, t: None)
    loop.connect(["X"])
    decision = loop.tick(at=datetime(2026, 10, 16, 11, 6, tzinfo=IST))
    reasons = set(decision.publication["reasons"])
    assert {"no_valid_score", "unverified_feed", "warmup_incomplete"} <= reasons


# ------------------------------------------------ the dashboard banner


def test_a_recent_archive_point_is_not_a_current_reading():
    """The audit's second reproduction, through the real backend function."""
    from seraph.dashboard.console_backend import liveness_of

    recent = ist_timestamp(datetime.now(IST).replace(microsecond=0)
                           - timedelta(minutes=2))
    liveness = liveness_of({"evaluation_timestamp": recent,
                            "composite": {"csrs": 0.4}})
    assert liveness["publishable_as_current"] is False
    assert liveness["headline"] != "CURRENT MARKET READING"
    assert "unverified_feed" in liveness["reasons"]
    assert liveness["mode"] == "historical_replay"


def test_the_banner_explains_itself_in_sentences():
    from seraph.dashboard.console_backend import liveness_of

    liveness = liveness_of({"evaluation_timestamp": "2020-04-30T15:30:00+05:30",
                            "composite": {"csrs": 0.4}})
    assert liveness["why"], "the banner must say why, not just that"
    assert all(" " in sentence for sentence in liveness["why"])
