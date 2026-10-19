"""Live market loop — the entry point a scheduler calls.

    python scripts/run_live.py --status        # read state only; connect to nothing
    python scripts/run_live.py --once          # wait (bounded) for ONE finalized batch
    python scripts/run_live.py                 # run until the session drains

What this does NOT do
---------------------
It does not invent a market connection. With no `KITE_API_KEY` the feed
resolves to `NullFeed`, every pass reports `publishable: false`, and the
reason is printed. That is the current state of this checkout:

* the research corpus ends **2026-08-21**;
* `kite_client.py` is a REST backfill client, not a streaming one;
* no feed has ever been connected.

It also does not invent a pillar estimate. T06 put the inference service in
the loop, so every bar close really does run C8/C9 — but with no live
producer attached each pillar reports a *structural* absence, no CSRS is
produced, and the publication gate refuses. That is the honest state, and it
is visible in the output rather than implied by its absence.

What T07 added
--------------
Durability. A decision, its checkpoint, the advanced stream head and its
outbox events commit in **one** transaction (`seraph/live/store.py`), so a
crash before the commit leaves nothing and a replay after it returns the same
logical decision. On start the runtime restores the last checkpoint rather
than silently beginning from an empty filter, and the lifecycle
(`seraph/live/lifecycle.py`) says which state it is in and why it is not
publishing.

`--status` reads the store and the clock and connects to nothing. `--once` is
a bounded wait for one finalized batch with an explicit timeout, not
connect-and-immediately-poll — polling once at an arbitrary instant almost
never lands on a bar close.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.live import LiveLoop, MarketClock, ReplayFeed, resolve_feed  # noqa: E402
from seraph.live.engine_adapter import NullProducers, attach              # noqa: E402
from seraph.live.inference import InferenceService                        # noqa: E402
from seraph.live.lifecycle import SessionLifecycle, next_session_window   # noqa: E402
from seraph.live.store import LiveStore                                   # noqa: E402
from seraph.operations import JobStore                                    # noqa: E402

JOB = "live.market_loop"

#: A small, liquid default. The real universe comes from C3 once a point-in-time
#: snapshot is reachable; this is enough to prove the path end to end.
DEFAULT_SYMBOLS = ("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK")

#: `--once` waits this long for a bar to close before giving up and saying so.
DEFAULT_ONCE_TIMEOUT = 330.0        # one five-minute bar, plus a margin


def session_dates(clock: MarketClock, *, back: int = 400) -> list[str]:
    """Recent sessions, for the service's process clock."""
    from datetime import timedelta

    today = clock.now().date()
    out = []
    for offset in range(back, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        if clock.is_session(day):
            out.append(day)
    return out


def build(*, replay: bool, store: LiveStore, clock: MarketClock
          ) -> "tuple[LiveLoop, InferenceService, object]":
    feed = resolve_feed(allow_replay=ReplayFeed([], label="empty replay")
                        if replay else None)
    loop = LiveLoop(feed, clock=clock,
                    mode="historical_replay" if replay else "live_shadow")
    service = InferenceService(session_dates=session_dates(clock))
    evaluator = attach(loop, service, producers=NullProducers())
    return loop, service, evaluator


def restore(service: InferenceService, store: LiveStore,
            lifecycle: SessionLifecycle, loop: "LiveLoop | None" = None) -> dict:
    """Resume from the last checkpoint, or say why a rebuild is needed.

    R08: this used to restore the INFERENCE service and nothing else. The
    bar builder came back empty and the input cursor was never read, so
    after a crash mid-bar the runtime re-accepted ticks it had already
    consumed -- double-counting the open bar's volume and moving its close --
    while the filter state resumed correctly. Half-recovered is the worst of
    the three possible states, because the inconsistency is between two
    components that each look fine.

    `loop` is optional so `--status` can report restorability without
    building a feed, which is the one thing `--status` must never do.
    """
    head = store.head()
    if head.checkpoint_id is None:
        lifecycle.to("warming_up", reason="no checkpoint; cold start")
        return dict(restored=False,
                    reason="no checkpoint exists; this is a cold start")
    lifecycle.to("restoring", reason=f"checkpoint {head.checkpoint_id}")
    try:
        record = store.load_checkpoint(head.checkpoint_id)
        from seraph.live.inference import StateSnapshot

        state = record["state"]
        service.restore(StateSnapshot(
            state_id=record["checkpoint_id"],
            pipeline_version=state.get("pipeline_version", ""),
            as_of=state.get("as_of"),
            filter_state=state.get("filter_state", {}),
            standardizer=state.get("standardizer", {}),
            vintages=state.get("vintages", {}),
            decisions=state.get("decisions", 0),
            calendar_id=state.get("calendar_id", ""),
            bundle_ids=tuple(state.get("bundle_ids", ())),
            config_id=state.get("config_id", ""),
            config=state.get("config", {})))

        # The bar builder and the input cursor, which R08 found unrestored.
        cursor = record.get("input_cursor") or {}
        bars_restored = False
        if loop is not None and state.get("bars"):
            loop.builder.restore(state["bars"])
            bars_restored = True
        return dict(restored=True, checkpoint_id=head.checkpoint_id,
                    as_of=state.get("as_of"),
                    bars_restored=bars_restored,
                    open_bars=(len(loop.builder.partial())
                               if loop is not None else None),
                    consumed_batches=len(cursor.get("batches", ())),
                    config_id=state.get("config_id", ""))
    except Exception as exc:                                  # noqa: BLE001
        # A checkpoint that cannot be validated is rebuilt, never forced.
        # R05 makes this reachable for a changed configuration, which is the
        # point: a rebuild is correct and a silent resume was not.
        lifecycle.to("warming_up", reason=f"checkpoint unusable: {exc}")
        return dict(restored=False, reason=f"{type(exc).__name__}: {exc}")


def report_status(store: LiveStore, clock: MarketClock,
                  lifecycle: SessionLifecycle) -> int:
    """Read-only. Connects to no feed and starts no job."""
    status = dict(
        store=store.describe(),
        lifecycle=lifecycle.describe(),
        market=next_session_window(clock),
        note=("--status reads persisted state and the clock. It connects to "
              "no feed and starts no job, so running it can never change what "
              "the next real pass will do"))
    print(json.dumps(status, indent=2, default=str))
    head = store.head()
    if head.decision_id is None:
        print("\n[live] NO DECISION HAS EVER BEEN COMMITTED.")
    else:
        latest = store.latest_decision()
        print(f"\n[live] last decision {head.decision_id} "
              f"as_of {latest['as_of']} ({latest['publication_state']})")
    if not status["market"]["calendar_verified"]:
        print("[live] calendar coverage is incomplete; no confident current "
              "label can be derived from it")
    return 0


def commit(store: LiveStore, loop: LiveLoop, service: InferenceService,
           evaluator, decision) -> dict | None:
    """Persist one pass: bars, then the decision transaction.

    R11: `result` used to be `evaluator.results[-1]` unconditionally -- the
    evaluator's most recent result, not the one belonging to the `decision`
    being committed. On a pass that produced no new decision that re-committed
    the previous one, and on any pass where the two disagreed it persisted a
    payload describing one decision under another's identity. The result is
    now matched to the decision by bar end, and a mismatch returns None
    rather than guessing.

    R08: the bar-builder snapshot travels inside the checkpoint state, in the
    same transaction as the decision, so the recoverable boundary between a
    closed bar and a committed decision is one atomic write rather than two
    independent ones.
    """
    for bar in loop.last_closed:
        store.record_closed_bar(bar)

    # `LiveDecision.bar_end` is what the decision id is derived from
    # (`engine_adapter.decision_id`), so it is the join key between the
    # loop's decision and the service's result.
    bar_end = getattr(decision, "bar_end", None)
    result = next((c for c in reversed(evaluator.results)
                   if bar_end and c.request.decision_id.endswith(bar_end)), None)
    if result is None:
        # Nothing to commit for THIS decision. Committing the evaluator's
        # most recent result instead is what R11 found: it persisted a
        # payload describing one decision under another's identity.
        return None

    state = asdict(service.snapshot())
    # One recoverable boundary: filter state, bar state and input cursor are
    # written together or not at all.
    state["bars"] = loop.builder.snapshot()
    head = store.head()
    return store.commit_decision(
        decision_id=result.request.decision_id,
        as_of=result.request.as_of.isoformat(),
        computed_at=result.computed_at.isoformat(),
        payload=decision.describe(),
        publication_state=("current" if decision.publishable else "withheld"),
        state=state,
        expected_version=head.version,
        input_cursor=dict(batches=list(result.request.input_batch_ids),
                          watermarks={s: loop.builder.watermark(s)
                                      for s in loop._symbols}),
        pipeline_version=result.request.pipeline_version,
        events=[dict(event_kind="decision",
                     aggregate_id=result.request.decision_id,
                     idempotency_key=result.request.decision_id,
                     payload=dict(
                         as_of=result.request.as_of.isoformat(),
                         publishable=decision.publishable))])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--once", action="store_true",
                        help="wait (bounded) for ONE finalized batch, then exit")
    parser.add_argument("--once-timeout", type=float,
                        default=DEFAULT_ONCE_TIMEOUT,
                        help="how long --once waits for a bar to close")
    parser.add_argument("--status", action="store_true",
                        help="report persisted state, lifecycle and clock; "
                             "connect to nothing and start no job")
    parser.add_argument("--replay", action="store_true",
                        help="use an explicit replay feed. Its output is never "
                             "publishable as a current reading")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="seconds between passes")
    parser.add_argument("--store", type=Path,
                        default=ROOT / "prototype_runs" / "live.sqlite")
    parser.add_argument("--jobs", type=Path,
                        default=ROOT / "prototype_runs" / "jobs.sqlite")
    args = parser.parse_args(argv)

    clock = MarketClock()
    store = LiveStore(args.store)
    lifecycle = SessionLifecycle()

    # --status is answered BEFORE anything is built or connected. The audit's
    # complaint was that asking what the system would do changed what it did.
    if args.status:
        return report_status(store, clock, lifecycle)

    loop, service, evaluator = build(replay=args.replay, store=store,
                                     clock=clock)
    # R08: the loop is handed over so the BAR BUILDER is restored too, not
    # only the inference service.
    restored = restore(service, store, lifecycle, loop)
    print(f"[live] restore: {json.dumps(restored, default=str)}")

    lifecycle.to("connecting")
    health = loop.connect(args.symbols)
    print(f"[live] feed: {health['source_kind']} "
          f"(live={health['is_live']}) — {health['detail']}")
    if not health["is_live"]:
        lifecycle.degrade([f"no live feed: {health['detail']}"])
    else:
        lifecycle.to("waiting_session", reason="feed attached")

    jobs = JobStore(args.jobs)

    def pass_once(context) -> dict:
        decision = loop.tick()
        if decision.bars_closed and lifecycle.state in (
                "waiting_session", "connecting", "degraded", "checkpointed",
                "reconnecting"):
            lifecycle.open_session(decision.decision_ts[:10])
        committed = commit(store, loop, service, evaluator, decision)
        context.checkpoint({"last_decision_ts": decision.decision_ts,
                            "head": store.head().version})
        line = (f"[live] {decision.decision_ts} "
                f"state={lifecycle.state} "
                f"market={decision.market['state']} "
                f"bars={decision.bars_closed} "
                f"recency={decision.recency['state']} "
                f"publishable={decision.publishable}")
        if committed:
            line += f" committed={committed['decision_id']}"
        if decision.skipped_reason:
            line += f" — {decision.skipped_reason}"
        print(line, flush=True)
        return decision.describe()

    if args.once:
        # A bounded WAIT, not one poll. Polling once at an arbitrary instant
        # almost never lands on a bar close, so "--once did nothing" used to
        # be indistinguishable from "the market is shut".
        deadline = time.monotonic() + args.once_timeout
        while True:
            outcome = jobs.run(JOB, pass_once, max_attempts=1)
            if outcome.status == "lock_unavailable":
                print(f"[live] {outcome.error}")
                return 1
            detail = outcome.detail or {}
            if detail.get("bars_closed"):
                return 0
            if time.monotonic() >= deadline:
                print(f"[live] --once timed out after {args.once_timeout:.0f}s "
                      f"with no finalized batch. Market is "
                      f"{clock.state()['state']}; next open "
                      f"{clock.next_open()}")
                return 2
            time.sleep(max(1.0, args.interval))

    print("[live] running until the session drains; Ctrl+C to stop")
    try:
        while True:
            state = clock.state()["state"]
            if state in ("closed_for_day", "not_a_session"):
                if lifecycle.state == "collecting":
                    lifecycle.begin_drain()
                if lifecycle.state == "draining_session":
                    # Poll the feed OUT before calling the session over: a
                    # late tick for the final bar is the normal case.
                    jobs.run(JOB, pass_once, max_attempts=1)
                    if lifecycle.drain_complete(
                            last_tick_at=loop.decisions[-1].bar_end
                            if loop.decisions else None):
                        lifecycle.close_session()
                        print("[live] session drained and checkpointed")
                        break
                    time.sleep(max(1.0, args.interval))
                    continue
                print(f"[live] market is {state}; next open "
                      f"{clock.next_open()}")
                break
            jobs.run(JOB, pass_once, max_attempts=1)
            time.sleep(max(1.0, args.interval))
    except KeyboardInterrupt:
        lifecycle.to("stopped", reason="operator interrupt")
        print("\n[live] stopped")
    print(json.dumps(dict(loop=loop.status(), lifecycle=lifecycle.describe(),
                          store=store.describe()), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
