"""T06 — the live loop invokes the risk engine (R01), and says what it cannot.

R01 was that `LiveLoop` had an `evaluate` slot and nothing in it. These tests
drive the loop with a replay feed, attach a real `InferenceService`, and check
that a bar close produces a `DecisionResult` through the same C8/C9 path the
archive uses — and, just as importantly, that with no live producer connected
the loop reports structural absence and refuses to publish rather than
emitting something that looks like a score.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from seraph.live.bars import Bar
from seraph.live.clock import MarketClock
from seraph.live.engine_adapter import (
    NullProducers,
    ServiceEvaluator,
    StaticProducers,
    attach,
)
from seraph.live.feed import ReplayFeed
from seraph.live.inference import InferenceService, Vintage
from seraph.live.loop import LiveLoop

IST = timezone(timedelta(hours=5, minutes=30))
SESSIONS = [f"2024-01-{d:02d}" for d in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12)]


def at(day: str, hour: int, minute: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+05:30")


def ticks(day: str, symbol: str = "AAA", n: int = 4):
    """Five-minute ticks from the open, enough to close three bars."""
    from seraph.live.feed import Tick
    base = at(day, 9, 15)
    return [Tick(symbol=symbol, ts=(base + timedelta(minutes=5 * i)).isoformat(),
                 last_price=100.0 + i, volume_traded=1000 * (i + 1))
            for i in range(n * 3)]


def service() -> InferenceService:
    svc = InferenceService(session_dates=SESSIONS)
    history = []
    for i in range(30):
        stamp = at(SESSIONS[0], 9, 15) - timedelta(days=40 - i)
        for pillar, scale in (("hawkes", 0.1), ("rmt", 0.5), ("hamilton", 0.3)):
            history.append(Vintage(producer=pillar, input_end=stamp.isoformat(),
                                   emission_available_at=stamp.isoformat(),
                                   value=scale + 0.001 * i))
    svc.warm_start(history, cutoff=at(SESSIONS[0], 9, 15))
    return svc


def loop_with(producers, *, day: str = "2024-01-02") -> tuple:
    feed = ReplayFeed(ticks(day))
    clock = MarketClock()
    loop = LiveLoop(feed, clock=clock, mode="live_shadow")
    evaluator = attach(loop, service(), producers=producers)
    loop.connect(["AAA"])
    return loop, evaluator


# ------------------------------------------------------- the slot is filled


def test_a_bar_close_produces_a_decision_result():
    loop, evaluator = loop_with(StaticProducers())
    loop.tick(at=at("2024-01-02", 9, 31))
    assert evaluator.results, "the loop must invoke the engine on a bar close"
    assert evaluator.results[0].request.trigger == "bar_close"
    assert evaluator.results[0].request.mode == "live_shadow"


def test_the_decision_id_is_the_bar_end_so_a_replayed_tick_is_idempotent():
    """A decision is named by the bar it decided on, not by when it ran.

    X04 changed the FORMAT, not this intent. It was
    `f"live:{as_of.isoformat()}"` -- no stream, no mode -- so a replay pass
    and a live pass over the same bar end minted the same id, and
    `LiveStore.commit_decision` (which returned an existing row as a replay
    before comparing payloads) accepted the replay as the live decision. The
    id is now `{mode}:{stream_id}:{bar_end}`: still keyed on the bar rather
    than on when it ran, and no longer collidable across streams or modes.

    Note it keys on the BAR END, not on `as_of`. `as_of` is the bar end plus
    `DECISION_ALLOWANCE` (R02), and a decision's name should be the bar it
    decided on, not the cutoff it used to decide.
    """
    loop, evaluator = loop_with(StaticProducers())
    loop.tick(at=at("2024-01-02", 9, 31))
    first = evaluator.results[0]
    assert first.request.decision_id == "live_shadow:live:2024-01-02T10:10:00+05:30"
    assert first.request.as_of.isoformat() == "2024-01-02T10:10:05+05:30"


def test_the_decision_id_distinguishes_mode_and_stream():
    """The collision X04 names: same bar end, different mode or stream."""
    from seraph.live.engine_adapter import decision_id

    bar_end = "2024-01-02T10:10:00+05:30"
    live = decision_id(mode="live_shadow", stream_id="live", bar_end=bar_end)
    replay = decision_id(mode="historical_replay", stream_id="live", bar_end=bar_end)
    other = decision_id(mode="live_shadow", stream_id="demo", bar_end=bar_end)
    assert len({live, replay, other}) == 3
    # The old format for all three was identical.
    assert len({f"live:{bar_end}"} ) == 1


def test_the_decision_cutoff_allows_normal_producer_latency():
    """R02. A producer cannot emit a bar-derived estimate until the bar is
    complete, so a cutoff AT the bar end withheld every bar-derived vintage
    on every bar and the pillar never updated."""
    from seraph.live.engine_adapter import DECISION_ALLOWANCE

    loop, evaluator = loop_with(StaticProducers())
    loop.tick(at=at("2024-01-02", 9, 31))
    request = evaluator.results[0].request
    assert DECISION_ALLOWANCE.total_seconds() > 0
    assert request.as_of - DECISION_ALLOWANCE == \
        datetime.fromisoformat("2024-01-02T10:10:00+05:30")


def test_the_input_batch_ids_name_the_bars_that_produced_the_decision():
    loop, evaluator = loop_with(StaticProducers())
    loop.tick(at=at("2024-01-02", 9, 31))
    ids = evaluator.results[0].request.input_batch_ids
    assert ids and all("AAA@" in i for i in ids)
    assert len(set(ids)) == len(ids)


# ------------------------------------- with no producer, say so and refuse


def test_with_no_producer_every_pillar_is_a_structural_absence():
    loop, evaluator = loop_with(NullProducers())
    loop.tick(at=at("2024-01-02", 9, 31))
    diagnostics = evaluator.results[0].pillar_diagnostics
    assert {d["absence"] for d in diagnostics.values()} == {"structural"}
    assert all(d["eligible"] is False for d in diagnostics.values())


def test_with_no_producer_no_score_is_published():
    loop, evaluator = loop_with(NullProducers())
    decision = loop.tick(at=at("2024-01-02", 9, 31))
    assert decision.csrs is None
    assert decision.publishable is False
    assert "no_valid_score" in decision.publication["reasons"]


def test_the_null_producer_states_why_rather_than_being_silent():
    described = NullProducers().describe()
    assert described["connected"] == []
    assert "durable store" in described["reason"]


# --------------------------------------------- with producers, a real score


def test_a_supplied_vintage_produces_a_csrs():
    bar_end = at("2024-01-02", 9, 20).isoformat()
    producers = StaticProducers({bar_end: [
        Vintage(producer="hawkes", input_end=bar_end,
                emission_available_at=bar_end, value=0.12),
        Vintage(producer="rmt", input_end=bar_end,
                emission_available_at=bar_end, value=0.52)]})
    loop, evaluator = loop_with(producers)
    decision = loop.tick(at=at("2024-01-02", 9, 31))
    assert decision.csrs is not None
    assert evaluator.results[0].csrs is not None
    assert evaluator.results[0].pillar_diagnostics["hawkes"]["eligible"] is True


def test_a_replay_feed_is_never_publishable_as_current():
    """Registered and connected, but not authenticated: it is not a broker."""
    bar_end = at("2024-01-02", 9, 20).isoformat()
    producers = StaticProducers({bar_end: [
        Vintage(producer="rmt", input_end=bar_end,
                emission_available_at=bar_end, value=0.52)]})
    loop, _ = loop_with(producers)
    decision = loop.tick(at=at("2024-01-02", 9, 31))
    assert decision.publishable is False
    assert "unverified_feed" in decision.publication["reasons"]


def test_the_engine_sees_the_same_feed_provenance_as_the_loop_gate():
    loop, evaluator = loop_with(StaticProducers())
    loop.tick(at=at("2024-01-02", 9, 31))
    service_reasons = set(evaluator.results[0].publication.reasons)
    assert "unverified_feed" in service_reasons, (
        "the service must not see a better feed than the loop's own gate does")


# ------------------------------------------------------- warmup is the engine's


def test_warmup_comes_from_the_service_once_attached():
    feed = ReplayFeed(ticks("2024-01-02"))
    loop = LiveLoop(feed, clock=MarketClock(), mode="live_shadow",
                    warmup_complete=True)
    svc = InferenceService(session_dates=SESSIONS, warmup_observations=5)
    attach(loop, svc, producers=NullProducers())
    loop.connect(["AAA"])
    decision = loop.tick(at=at("2024-01-02", 9, 31))
    assert "warmup_incomplete" in decision.publication["reasons"], (
        "the loop's constructor flag must not override the engine's state")


def test_warmup_clears_once_the_service_has_history():
    feed = ReplayFeed(ticks("2024-01-02"))
    loop = LiveLoop(feed, clock=MarketClock(), mode="live_shadow")
    evaluator = attach(loop, service(), producers=NullProducers())
    loop.connect(["AAA"])
    decision = loop.tick(at=at("2024-01-02", 9, 31))
    assert evaluator.warmup_complete is True
    assert "warmup_incomplete" not in decision.publication["reasons"]


# ----------------------------------------------------------------- describe


def test_the_evaluator_describes_what_is_connected():
    loop, evaluator = loop_with(NullProducers())
    loop.tick(at=at("2024-01-02", 9, 31))
    described = evaluator.describe()
    assert described["producers"]["kind"] == "null"
    assert described["decisions"] == 1
    assert described["last_decision"]["publication"]["current_allowed"] is False
