"""R08 acceptance probe — crash recovery through the NORMAL caller.

The audit's acceptance for R08 is specific: "Crash mid-bar, after
finalization and before/after decision commit yields the same OHLC, volume
and decisions as uninterrupted execution."

`tests/test_r07_r09_tick_integrity.py` covers the `BarBuilder` half in
isolation. This probe exercises the whole runtime path -- `run_live.build`,
`run_live.restore`, `run_live.commit`, `LiveStore`, `InferenceService` -- at
three different interruption points, and compares each against an
uninterrupted baseline run over the same ticks.

Read-only with respect to the repository: writes a scratch SQLite store per
scenario into a temporary directory, and prints JSON on stdout.

    python docs/evidence/engineering-audit-2026-10-18/r08_recovery_probe.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from seraph.live.clock import MarketClock                       # noqa: E402
from seraph.live.engine_adapter import StaticProducers, attach  # noqa: E402
from seraph.live.feed import ReplayFeed, Tick                   # noqa: E402
from seraph.live.inference import InferenceService, Vintage     # noqa: E402
from seraph.live.lifecycle import SessionLifecycle              # noqa: E402
from seraph.live.loop import LiveLoop                           # noqa: E402
from seraph.live.store import LiveStore                         # noqa: E402

import run_live                                                 # noqa: E402

SESSIONS = [f"2024-01-{d:02d}" for d in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12)]
DAY = "2024-01-02"


def at(hour: int, minute: int) -> datetime:
    return datetime.fromisoformat(f"{DAY}T{hour:02d}:{minute:02d}:00+05:30")


def ticks() -> list[Tick]:
    """Twelve ticks from the open, rising then falling inside one second so
    the ordering repair is exercised too."""
    base = at(9, 15)
    out = []
    for i in range(12):
        stamp = (base + timedelta(minutes=5 * i)).isoformat()
        out.append(Tick(symbol="AAA", ts=stamp, last_price=100.0 + i,
                        volume_traded=1000 * (i + 1)))
        if i % 4 == 3:                      # a same-timestamp down-tick
            out.append(Tick(symbol="AAA", ts=stamp, last_price=99.5 + i,
                            volume_traded=1000 * (i + 1) + 5))
    return out


def warm(service: InferenceService) -> None:
    history = []
    for i in range(30):
        stamp = at(9, 15) - timedelta(days=40 - i)
        for pillar, scale in (("hawkes", 0.1), ("rmt", 0.5), ("hamilton", 0.3)):
            history.append(Vintage(producer=pillar, input_end=stamp.isoformat(),
                                   emission_available_at=stamp.isoformat(),
                                   value=scale + 0.001 * i))
    service.warm_start(history, cutoff=at(9, 15))


def build(store: LiveStore, feed_ticks: list[Tick]):
    """What `run_live.build` builds, with a deliberate replay feed."""
    clock = MarketClock()
    feed = ReplayFeed(list(feed_ticks), label="r08 probe")
    loop = LiveLoop(feed, clock=clock, mode="historical_replay")
    service = InferenceService(session_dates=SESSIONS)
    warm(service)
    evaluator = attach(loop, service, producers=StaticProducers(),
                       stream_id="probe")
    loop.connect(["AAA"])
    return loop, service, evaluator


def drive(loop, service, evaluator, store, *, passes: int, moments):
    """Run `passes` ticks, committing through `run_live.commit` each time."""
    committed = []
    for index in range(passes):
        decision = loop.tick(at=moments[index])
        if decision is None:
            continue
        record = run_live.commit(store, loop, service, evaluator, decision)
        if record:
            committed.append(dict(decision_id=record["decision_id"],
                                  replayed=record["replayed"]))
    return committed


def bars_of(store: LiveStore) -> list[dict]:
    """Every recorded bar's OHLC, volume and quality.

    `closed_bars` keeps the bar in `payload_json` with a revision, so the
    comparison is over the payload rather than over columns.
    """
    with store.connect() as db:
        rows = db.execute(
            "SELECT symbol,session_id,bar_end,revision,payload_json "
            "FROM closed_bars ORDER BY bar_end, symbol, revision").fetchall()
    out = []
    for symbol, session_id, bar_end, revision, payload in rows:
        body = json.loads(payload)
        out.append(dict(symbol=symbol, session_id=session_id, bar_end=bar_end,
                        revision=revision,
                        open=body.get("open"), high=body.get("high"),
                        low=body.get("low"), close=body.get("close"),
                        ticks=body.get("ticks"), volume=body.get("volume"),
                        quality=body.get("volume_quality")))
    return out


def decisions_of(store: LiveStore) -> list[dict]:
    return [dict(decision_id=d["decision_id"], as_of=d["as_of"],
                 payload_hash=d["payload_hash"],
                 state=d["publication_state"])
            for d in reversed(store.decisions(limit=200))]


def uninterrupted(root: Path, moments) -> dict:
    store = LiveStore(root / "baseline.sqlite", stream_id="probe")
    loop, service, evaluator = build(store, ticks())
    drive(loop, service, evaluator, store, passes=len(moments), moments=moments)
    return dict(bars=bars_of(store), decisions=decisions_of(store))


def interrupted(root: Path, moments, *, crash_after: int, label: str) -> dict:
    """Run `crash_after` passes, abandon the process state, then resume from
    the store exactly as `run_live.main` does on restart."""
    path = root / f"{label}.sqlite"
    store = LiveStore(path, stream_id="probe")
    loop, service, evaluator = build(store, ticks())
    drive(loop, service, evaluator, store, passes=crash_after, moments=moments)

    # --- the crash. Every in-memory object is dropped. ------------------
    del loop, service, evaluator

    store2 = LiveStore(path, stream_id="probe")
    loop2, service2, evaluator2 = build(store2, ticks())
    lifecycle = SessionLifecycle()
    restored = run_live.restore(service2, store2, lifecycle, loop2)
    # The feed is replayed from the start, as a redelivering provider would:
    # the recovered dedup state is what must reject the already-consumed
    # ticks rather than double-counting them.
    drive(loop2, service2, evaluator2, store2,
          passes=len(moments), moments=moments)
    return dict(bars=bars_of(store2), decisions=decisions_of(store2),
                restored=restored)


def main() -> int:
    moments = [at(9, 31), at(10, 16), at(11, 1), at(11, 46)]
    report: dict = {"scenarios": {}}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        base = uninterrupted(root, moments)
        report["baseline"] = dict(bars=len(base["bars"]),
                                  decisions=len(base["decisions"]))

        for label, crash_after in (("crash_mid_bar", 1),
                                   ("crash_after_finalization", 2),
                                   ("crash_after_commit", 3)):
            run = interrupted(root, moments, crash_after=crash_after,
                              label=label)
            report["scenarios"][label] = dict(
                crash_after_passes=crash_after,
                restored=run["restored"].get("restored"),
                bars_restored=run["restored"].get("bars_restored"),
                open_bars_after_restore=run["restored"].get("open_bars"),
                config_id=(run["restored"].get("config_id") or "")[:12],
                bars_match_baseline=run["bars"] == base["bars"],
                decisions_match_baseline=run["decisions"] == base["decisions"],
                bars=len(run["bars"]), decisions=len(run["decisions"]))

    report["verdict"] = dict(
        all_bars_match=all(s["bars_match_baseline"]
                           for s in report["scenarios"].values()),
        all_decisions_match=all(s["decisions_match_baseline"]
                                for s in report["scenarios"].values()),
        all_restored=all(s["restored"] for s in report["scenarios"].values()),
    )
    report["verdict"]["passed"] = all(report["verdict"].values())
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["verdict"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
