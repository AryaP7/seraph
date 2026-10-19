"""Live market path — the clock, the feed gate, bar closing and the loop.

SERAPH's CSRS is specified as a *current* market risk score. Everything built
until now evaluates a chosen historical date, which is right for policy work
and historical segments and is not the product.

These tests pin the properties that keep the live path honest:

* a partial bar never reaches a detector;
* a late tick never amends a bar the pillars already consumed;
* archived data is never automatically substituted for a market connection;
* a score computed from old data is **not publishable as current**, and the
  system says so as a value rather than a footnote.

The corpus ends 2026-08-21, so the last property is not hypothetical: it is
the state the system is in today.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from seraph.live import (
    BarBuilder,
    FeedUnavailable,
    KiteTickerFeed,
    LiveLoop,
    MarketClock,
    NullFeed,
    ReplayFeed,
    Tick,
    resolve_feed,
)
from seraph.shared_types import IST, ist_timestamp

CORPUS_END = "2026-08-21T15:30:00+05:30"


def at(hour, minute, *, day=(2026, 10, 16)):
    return datetime(*day, hour, minute, tzinfo=IST)


@pytest.fixture
def clock():
    return MarketClock()


# ------------------------------------------------------------- the clock


def test_market_state_tracks_the_session(clock):
    assert clock.state(at(8, 0))["state"] == "pre_open"
    assert clock.state(at(11, 0))["state"] == "open"
    assert clock.state(at(16, 0))["state"] == "closed_for_day"
    # 2026-10-17 is a Saturday.
    assert clock.state(at(11, 0, day=(2026, 10, 17)))["state"] == "not_a_session"


def test_a_muhurat_evening_session_is_open_when_a_regular_day_is_not(clock):
    """The live clock inherits the session registry rather than re-deciding."""
    muhurat = datetime(2024, 11, 1, 18, 30, tzinfo=IST)
    state = clock.state(muhurat)
    assert state["state"] == "open" and state["session_kind"] == "muhurat"
    # The same wall-clock time on an ordinary day is after the close.
    assert clock.state(at(18, 30))["state"] == "closed_for_day"


def test_a_short_session_closes_early(clock):
    """2024-03-02 is a registered two-window special live session."""
    assert clock.state(datetime(2024, 3, 2, 9, 30, tzinfo=IST))["state"] == "open"
    assert clock.state(datetime(2024, 3, 2, 14, 0, tzinfo=IST))["state"] == \
        "closed_for_day"


def test_the_midday_break_of_a_split_session_is_not_open(clock):
    gap = clock.state(datetime(2024, 3, 2, 10, 30, tzinfo=IST))
    assert gap["state"] == "pre_open"
    assert "between two windows" in gap["note"]


def test_the_current_bar_is_marked_incomplete(clock):
    bar = clock.current_bar(at(11, 7))
    assert bar["start"].endswith("11:05:00+05:30")
    assert bar["end"].endswith("11:10:00+05:30")
    assert bar["complete"] is False
    assert "must not reach a jump detector" in bar["note"]


def test_the_last_closed_bar_is_the_one_before_it(clock):
    assert clock.last_closed_bar(at(11, 7))["end"].endswith("11:05:00+05:30")


def test_there_is_no_closed_bar_in_the_first_bar_of_the_day(clock):
    assert clock.last_closed_bar(at(9, 17)) is None


def test_next_open_skips_the_weekend(clock):
    assert clock.next_open(at(16, 0)).startswith("2026-10-19")


# ----------------------------------------------- the recency gate


def test_the_current_corpus_is_historical_only_not_live(clock):
    """The state the system is actually in today."""
    recency = clock.recency(CORPUS_END, at=at(11, 0))
    assert recency.state == "historical_only"
    assert recency.is_live is False
    assert recency.may_publish_as_current is False
    assert "REPLAY" in recency.note


def test_no_observation_at_all_is_historical_only(clock):
    recency = clock.recency(None, at=at(11, 0))
    assert recency.state == "historical_only"
    assert "nothing can be said about the market now" in recency.note


def test_a_fresh_observation_during_the_session_is_live(clock):
    now = at(11, 0)
    recency = clock.recency(ist_timestamp(now - timedelta(minutes=3)), at=now)
    assert recency.state == "live" and recency.may_publish_as_current


def test_a_lagging_feed_is_delayed_then_stale(clock):
    now = at(11, 0)
    delayed = clock.recency(ist_timestamp(now - timedelta(minutes=30)), at=now)
    stale = clock.recency(ist_timestamp(now - timedelta(minutes=120)), at=now)
    assert delayed.state == "delayed" and delayed.may_publish_as_current
    assert stale.state == "stale" and not stale.may_publish_as_current
    assert "not keeping up" in stale.note


def test_yesterdays_close_out_of_hours_is_the_current_reading(clock):
    """Out of hours, the last session's close is correct, not stale."""
    friday_close = "2026-10-16T15:30:00+05:30"
    recency = clock.recency(friday_close, at=at(10, 0, day=(2026, 10, 17)))
    assert recency.state == "delayed" and recency.may_publish_as_current


# ------------------------------------------------------- feed selection


def test_without_credentials_there_is_no_feed_and_nothing_is_substituted(monkeypatch):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    feed = resolve_feed()
    assert isinstance(feed, NullFeed)
    health = feed.health()
    assert health.is_live is False and health.connected is False
    assert "never substituted automatically" in health.detail


def test_a_replay_feed_must_be_handed_over_deliberately(monkeypatch):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    replay = ReplayFeed([])
    assert resolve_feed(allow_replay=replay) is replay
    assert resolve_feed() is not replay


def test_a_replay_feed_never_claims_to_be_live():
    feed = ReplayFeed([Tick(symbol="X", ts="2020-01-01T09:20:00+05:30",
                            last_price=100.0)])
    feed.connect(["X"])
    assert feed.is_live is False
    assert feed.health().source_kind == "replay"
    assert "NOT a market connection" in feed.health().detail
    assert all(t.source_kind == "replay" for t in feed.poll())


def test_the_kite_feed_refuses_to_start_without_credentials(monkeypatch):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    with pytest.raises(FeedUnavailable, match="not be substituted"):
        KiteTickerFeed().connect(["RELIANCE"])


def test_the_kite_adapter_admits_it_has_never_connected(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "k")
    assert "never been exercised against the live endpoint" in \
        KiteTickerFeed().health().detail


# ----------------------------------------------------------- bar building


def ticks(symbol, start_hour, start_minute, prices, *, step_seconds=30):
    base = at(start_hour, start_minute)
    return [Tick(symbol=symbol,
                 ts=ist_timestamp(base + timedelta(seconds=i * step_seconds)),
                 last_price=price, source_kind="replay")
            for i, price in enumerate(prices)]


def test_a_bar_is_only_emitted_once_its_window_has_elapsed(clock):
    builder = BarBuilder(clock)
    assert builder.add(ticks("X", 11, 0, [100, 101, 102])) == []
    assert builder.partial()[0].complete is False
    closed = builder.add(ticks("X", 11, 5, [103]))
    assert len(closed) == 1 and closed[0].complete is True
    assert (closed[0].open, closed[0].high, closed[0].low, closed[0].close) == \
        (100, 102, 100, 102)


def test_a_bar_closes_on_the_timer_even_with_no_further_tick(clock):
    builder = BarBuilder(clock)
    builder.add(ticks("THIN", 11, 0, [100]))
    assert builder.close_elapsed(at(11, 4)) == []
    closed = builder.close_elapsed(at(11, 5))
    assert len(closed) == 1 and closed[0].symbol == "THIN", \
        "a thin symbol must not hold its bar open"


def test_a_late_tick_is_rejected_not_folded_into_a_closed_bar(clock):
    builder = BarBuilder(clock)
    builder.add(ticks("X", 11, 0, [100]))
    builder.add(ticks("X", 11, 5, [110]))          # closes the 11:00 bar
    before = builder.late_ticks
    builder.add(ticks("X", 11, 1, [999]))          # arrives for a closed window
    assert builder.late_ticks == before + 1
    assert "cannot reopen" in builder.describe()["note"]


def test_ticks_outside_a_session_are_counted_not_banked(clock):
    builder = BarBuilder(clock)
    builder.add([Tick(symbol="X", ts="2026-10-17T11:00:00+05:30",
                      last_price=100.0)])
    assert builder.out_of_session_ticks == 1 and builder.partial() == []


def test_bar_volume_is_the_increment_since_the_previous_observation(clock):
    """T02: the increment is carried ACROSS the boundary.

    The first bar of a connection has no prior baseline, so it reports
    `partial` rather than a number computed from an assumption. The second bar
    then measures everything traded since the first bar's last tick.
    """
    builder = BarBuilder(clock)
    builder.add([Tick(symbol="X", ts=ist_timestamp(at(11, 0)), last_price=100.0,
                      volume_traded=500_000),
                 Tick(symbol="X", ts=ist_timestamp(at(11, 2)), last_price=101.0,
                      volume_traded=512_000)])
    first = builder.close_elapsed(at(11, 5))
    assert first[0].volume is None and first[0].volume_quality == "partial", \
        "a mid-session connection cannot claim exact volume for its first window"

    builder.add([Tick(symbol="X", ts=ist_timestamp(at(11, 6)), last_price=102.0,
                      volume_traded=520_000),
                 Tick(symbol="X", ts=ist_timestamp(at(11, 8)), last_price=103.0,
                      volume_traded=530_000)])
    second = builder.close_elapsed(at(11, 10))
    assert second[0].volume == 18_000, \
        "530,000 - 512,000: measured from the previous bar's last observation, "\
        "not from this bar's first tick"
    assert second[0].volume_quality == "exact"


# ------------------------------------------------------------- the loop


def test_the_loop_runs_with_no_feed_and_reports_it_honestly(monkeypatch):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    loop = LiveLoop(resolve_feed())
    health = loop.connect(["RELIANCE", "TCS"])
    assert health["source_kind"] == "none" and health["is_live"] is False
    decision = loop.tick(at=at(11, 7))
    assert decision.publishable is False
    assert decision.recency["state"] == "historical_only"
    assert "no bar has closed" in decision.skipped_reason


def test_a_replay_fed_decision_is_computed_but_not_publishable(clock):
    """The whole point: the pipeline runs, and the result is labelled."""
    feed = ReplayFeed(ticks("X", 11, 0, [100, 101, 102]))
    seen = {}
    loop = LiveLoop(feed, clock=clock,
                    evaluate=lambda bars, ts: seen.setdefault(
                        "csrs", {"csrs": 0.42, "bars": len(bars)}))
    loop.connect(["X"])
    decision = loop.tick(at=at(11, 6))
    assert decision.bars_closed == 1
    assert decision.csrs == {"csrs": 0.42, "bars": 1}, "the pipeline did run"
    assert decision.publishable is False
    # T01: the gate now reports EVERY failed condition, not one of them.
    assert "not registered and authenticated" in decision.skipped_reason
    assert "unverified_feed" in decision.publication["reasons"]
    assert decision.describe()["label"] == "NOT A CURRENT MARKET READING"


def test_a_partial_bar_alone_never_triggers_an_evaluation(clock):
    calls = []
    loop = LiveLoop(ReplayFeed(ticks("X", 11, 0, [100, 101])), clock=clock,
                    evaluate=lambda bars, ts: calls.append(bars))
    loop.connect(["X"])
    decision = loop.tick(at=at(11, 3))
    assert calls == [] and decision.csrs is None
    assert "partial bar is never evaluated" in decision.skipped_reason


def test_a_closed_market_with_no_bar_is_skipped_with_its_reason(clock):
    loop = LiveLoop(ReplayFeed([]), clock=clock, evaluate=lambda b, t: {})
    loop.connect(["X"])
    decision = loop.tick(at=at(20, 0))
    assert decision.publishable is False
    assert "market is closed_for_day" in decision.skipped_reason


def test_latency_is_measured_from_the_bar_close(clock):
    feed = ReplayFeed(ticks("X", 11, 0, [100, 101]))
    loop = LiveLoop(feed, clock=clock, evaluate=lambda b, t: {"csrs": 0.1})
    loop.connect(["X"])
    decision = loop.tick(at=at(11, 5) + timedelta(seconds=2))
    assert decision.bar_close_to_decision_ms is not None
    assert decision.bar_close_to_decision_ms >= 2000, \
        "measured from the bar's close, not from when the loop started work"


def test_status_separates_decisions_that_ran_from_those_published(clock):
    loop = LiveLoop(ReplayFeed(ticks("X", 11, 0, [100, 101])), clock=clock,
                    evaluate=lambda b, t: {"csrs": 0.2})
    loop.connect(["X"])
    loop.tick(at=at(11, 6))
    status = loop.status(at=at(11, 6))
    assert status["decisions"] == 1 and status["published"] == 0
    assert status["feed"]["is_live"] is False
    assert "still recorded, with the reason" in status["note"]


def test_every_decision_carries_the_clock_and_the_calendar_it_used(clock):
    described = clock.describe(CORPUS_END, at=at(11, 0))
    assert described["clock"]["state"] == "open"
    assert described["recency"]["state"] == "historical_only"
    assert described["calendar"]["completeness"].startswith("PARTIAL")
