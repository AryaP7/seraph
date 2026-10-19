"""T07 — restart the real runtime and check what survived (audit finding R04).

`test_t07_durable_runtime.py` tests the store's transaction in isolation. This
file drives the pieces the way `scripts/run_live.py` does — loop, inference
service, store, lifecycle — then throws the process state away and starts
again from the same database, which is what a crash actually looks like.

What must hold across the restart:

* a committed decision is still there, with the same payload hash;
* the stream head did not move backwards, and a replay of the same decision
  does not advance it;
* the restored service continues from the checkpoint instead of an empty
  filter, and its ECDF history is the one it had;
* bars finalized before the restart are still finalized, and the watermark
  stops them reopening.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from seraph.live.bars import BarBuilder
from seraph.live.clock import MarketClock
from seraph.live.engine_adapter import StaticProducers, attach
from seraph.live.feed import ReplayFeed, Tick
from seraph.live.inference import InferenceService, StateSnapshot, Vintage
from seraph.live.lifecycle import SessionLifecycle
from seraph.live.loop import LiveLoop
from seraph.live.store import LiveStore

IST = timezone(timedelta(hours=5, minutes=30))
SESSIONS = [f"2024-01-{d:02d}" for d in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12)]


def at(day: str, hour: int, minute: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+05:30")


def ticks(day="2024-01-02", symbol="AAA", n=12):
    base = at(day, 9, 15)
    return [Tick(symbol=symbol, ts=(base + timedelta(minutes=5 * i)).isoformat(),
                 last_price=100.0 + i, volume_traded=1000 * (i + 1))
            for i in range(n)]


def vintages_at(bar_end):
    return [Vintage(producer="rmt", input_end=bar_end,
                    emission_available_at=bar_end, value=0.52),
            Vintage(producer="hawkes", input_end=bar_end,
                    emission_available_at=bar_end, value=0.11)]


def runtime(tmp_path, *, day="2024-01-02"):
    """One cold start: store, service, loop, lifecycle — as the runner builds."""
    store = LiveStore(tmp_path / "live.sqlite")
    service = InferenceService(session_dates=SESSIONS)
    service.warm_start([
        Vintage(producer=p, input_end=(at(SESSIONS[0], 9, 15)
                                       - timedelta(days=30 - i)).isoformat(),
                emission_available_at=(at(SESSIONS[0], 9, 15)
                                       - timedelta(days=30 - i)).isoformat(),
                value=v + i / 1000)
        for i in range(25)
        for p, v in (("hawkes", 0.1), ("rmt", 0.5), ("hamilton", 0.3))],
        cutoff=at(SESSIONS[0], 9, 15))
    loop = LiveLoop(ReplayFeed(ticks(day)), clock=MarketClock(),
                    mode="live_shadow")
    bar_end = at(day, 9, 20).isoformat()
    evaluator = attach(loop, service,
                       producers=StaticProducers({bar_end: vintages_at(bar_end)}))
    loop.connect(["AAA"])
    lifecycle = SessionLifecycle()
    lifecycle.to("warming_up")
    lifecycle.to("connecting")
    return store, service, loop, evaluator, lifecycle


def one_pass(store, service, loop, evaluator, *, at_moment):
    """What `pass_once` in the runner does, minus the printing."""
    decision = loop.tick(at=at_moment)
    for bar in loop.last_closed:
        store.record_closed_bar(bar)
    if not evaluator.results:
        return decision, None
    result = evaluator.results[-1]
    head = store.head()
    committed = store.commit_decision(
        decision_id=result.request.decision_id,
        as_of=result.request.as_of.isoformat(),
        computed_at=result.computed_at.isoformat(),
        payload=decision.describe(),
        publication_state="current" if decision.publishable else "withheld",
        state=asdict(service.snapshot()),
        expected_version=head.version,
        input_cursor=dict(batches=list(result.request.input_batch_ids)),
        pipeline_version=result.request.pipeline_version,
        events=[dict(event_kind="decision",
                     idempotency_key=result.request.decision_id,
                     payload=dict(publishable=decision.publishable))])
    return decision, committed


# ------------------------------------------------------- across a restart


def test_a_committed_decision_survives_a_restart(tmp_path):
    store, service, loop, evaluator, _ = runtime(tmp_path)
    _, committed = one_pass(store, service, loop, evaluator,
                            at_moment=at("2024-01-02", 9, 31))
    assert committed is not None

    del store, service, loop, evaluator          # the crash
    store2 = LiveStore(tmp_path / "live.sqlite")
    assert store2.decision(committed["decision_id"])["payload_hash"] == \
        committed["payload_hash"]
    assert store2.head().version == committed["version"]


def test_the_restored_service_keeps_its_ecdf_history(tmp_path):
    store, service, loop, evaluator, _ = runtime(tmp_path)
    one_pass(store, service, loop, evaluator, at_moment=at("2024-01-02", 9, 31))
    before = {p: service.standardizer.observations(p)
              for p in ("hawkes", "rmt", "hamilton")}
    checkpoint_id = store.head().checkpoint_id

    resumed = InferenceService(session_dates=SESSIONS)
    record = store.load_checkpoint(checkpoint_id)
    resumed.restore(StateSnapshot(**record["state"]))
    after = {p: resumed.standardizer.observations(p)
             for p in ("hawkes", "rmt", "hamilton")}
    assert after == before
    assert all(n > 0 for n in after.values()), "an empty ECDF is a cold start"


def test_the_restored_service_continues_the_filter(tmp_path):
    store, service, loop, evaluator, _ = runtime(tmp_path)
    one_pass(store, service, loop, evaluator, at_moment=at("2024-01-02", 9, 31))
    expected = service.snapshot().filter_state

    resumed = InferenceService(session_dates=SESSIONS)
    record = store.load_checkpoint(store.head().checkpoint_id)
    resumed.restore(StateSnapshot(**record["state"]))
    assert resumed.snapshot().filter_state == expected


def test_replaying_the_same_pass_does_not_double_decide(tmp_path):
    """A crash between commit and acknowledgement is the common case."""
    store, service, loop, evaluator, _ = runtime(tmp_path)
    _, first = one_pass(store, service, loop, evaluator,
                        at_moment=at("2024-01-02", 9, 31))

    store2 = LiveStore(tmp_path / "live.sqlite")
    service2 = InferenceService(session_dates=SESSIONS)
    record = store2.load_checkpoint(store2.head().checkpoint_id)
    service2.restore(StateSnapshot(**record["state"]))
    loop2 = LiveLoop(ReplayFeed(ticks()), clock=MarketClock(),
                     mode="live_shadow")
    bar_end = at("2024-01-02", 9, 20).isoformat()
    evaluator2 = attach(loop2, service2,
                        producers=StaticProducers({bar_end: vintages_at(bar_end)}))
    loop2.connect(["AAA"])
    _, again = one_pass(store2, service2, loop2, evaluator2,
                        at_moment=at("2024-01-02", 9, 31))

    assert again["replayed"] is True
    assert again["decision_id"] == first["decision_id"]
    assert store2.head().version == first["version"], "the head did not move"
    with store2.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM live_decisions"
                          ).fetchone()["n"] == 1


def test_bars_finalized_before_the_restart_stay_finalized(tmp_path):
    store, service, loop, evaluator, _ = runtime(tmp_path)
    one_pass(store, service, loop, evaluator, at_moment=at("2024-01-02", 9, 31))
    stored = store.bars_for("2024-01-02")
    assert stored, "the pass finalized at least one bar"

    store2 = LiveStore(tmp_path / "live.sqlite")
    assert len(store2.bars_for("2024-01-02")) == len(stored)
    # Re-recording the same finalized bar is a no-op, not a second row.
    for bar in loop.last_closed:
        assert store2.record_closed_bar(bar) is False


def test_the_bar_watermark_survives_a_restart(tmp_path):
    """A finalized window must not reopen because the process did."""
    store, service, loop, evaluator, _ = runtime(tmp_path)
    one_pass(store, service, loop, evaluator, at_moment=at("2024-01-02", 9, 31))
    snapshot = loop.builder.snapshot()

    resumed = BarBuilder(MarketClock())
    resumed.restore(snapshot)
    late = Tick(symbol="AAA", ts=at("2024-01-02", 9, 17).isoformat(),
                last_price=500.0, volume_traded=9999)
    assert resumed.add([late]) == [], "a late tick reopened a finalized window"


def test_the_outbox_event_is_still_pending_after_a_restart(tmp_path):
    """At-least-once means an undelivered event outlives the process."""
    store, service, loop, evaluator, _ = runtime(tmp_path)
    one_pass(store, service, loop, evaluator, at_moment=at("2024-01-02", 9, 31))

    store2 = LiveStore(tmp_path / "live.sqlite")
    pending = store2.pending_events()
    assert [e.event_kind for e in pending] == ["decision"]
    store2.mark_delivered(pending[0].outbox_id)

    store3 = LiveStore(tmp_path / "live.sqlite")
    assert store3.pending_events() == []


# -------------------------------------------------------- the whole shape


def test_a_cold_start_with_no_checkpoint_warms_up_rather_than_pretending(tmp_path):
    store = LiveStore(tmp_path / "live.sqlite")
    lifecycle = SessionLifecycle()
    assert store.head().checkpoint_id is None
    lifecycle.to("warming_up", reason="no checkpoint; cold start")
    assert lifecycle.may_publish is False
    assert "history is still being rebuilt" in lifecycle.why_not_publishing()


def test_a_decision_with_no_producer_is_committed_but_withheld(tmp_path):
    """The engine runs on every bar close; nothing is published from nothing."""
    from seraph.live.engine_adapter import NullProducers

    store = LiveStore(tmp_path / "live.sqlite")
    service = InferenceService(session_dates=SESSIONS)
    loop = LiveLoop(ReplayFeed(ticks()), clock=MarketClock(), mode="live_shadow")
    evaluator = attach(loop, service, producers=NullProducers())
    loop.connect(["AAA"])
    decision, committed = one_pass(store, service, loop, evaluator,
                                   at_moment=at("2024-01-02", 9, 31))
    assert decision.csrs is None
    assert committed is not None, "the absence is recorded, not discarded"
    assert store.decision(committed["decision_id"])["publication_state"] == \
        "withheld"


def test_the_persisted_payload_says_why_it_was_withheld(tmp_path):
    from seraph.live.engine_adapter import NullProducers

    store = LiveStore(tmp_path / "live.sqlite")
    service = InferenceService(session_dates=SESSIONS)
    loop = LiveLoop(ReplayFeed(ticks()), clock=MarketClock(), mode="live_shadow")
    evaluator = attach(loop, service, producers=NullProducers())
    loop.connect(["AAA"])
    _, committed = one_pass(store, service, loop, evaluator,
                            at_moment=at("2024-01-02", 9, 31))
    payload = store.decision(committed["decision_id"])["payload"]
    assert payload["publication"]["current_allowed"] is False
    assert payload["publication"]["reasons"], "a refusal with no reason is a shrug"
