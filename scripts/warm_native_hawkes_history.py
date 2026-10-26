#!/usr/bin/env python3
# C5 — native Hawkes historical warm-up replay (FR10–15, FR28).
"""Build real registered Hawkes ECDF history by replaying the declared cadence.

The companion to `warm_runtime_history.py`, which does the same job for RMT.
That script could not do Hawkes because the native producer only ever fitted
the LATEST window: `fit_pending` used one clock for both the bar cutoff and
the arrival guard, and every native bar carries the same bulk `received_at`,
so a past cutoff saw zero bars. `fit_pending(data_cutoff=...)` now separates
the two, and this script walks the cadence with it.

What it does NOT do, by construction:

* **No look-ahead.** Each fit sees only bars whose session ended at or before
  its own cutoff, and only models whose `trained_through` is at or before that
  cutoff (`_previous_fit`). A fit trained later cannot satisfy an earlier
  cadence point.
* **No invented arrival times.** Each vintage records its ACTUAL computation
  time as `emission_available_at`, with a historical `input_end` — the
  convention `run_daily.persist` already uses for computed observations, and
  the one the RMT warm-up followed. `_persist` preserves the first
  availability when an identical input is replayed, so re-running is
  idempotent rather than re-dating.
* **No duplicate observations.** One fit yields one vintage, keyed
  `producer@input_end#bundle_id`. Cadence points that are not due are skipped,
  so a retained model is never re-emitted under a second timestamp.
* **No weakened thresholds.** The window, the refit cadence and the required
  observation count are read from the config and the standardizer; this script
  reports a shortfall, it never shrinks one to pass.

Default prints the plan. `--execute` performs the fits.

    python scripts/warm_native_hawkes_history.py --config prototype_runs/live.native-hawkes.json
    python scripts/warm_native_hawkes_history.py --config ... --execute --max-fits 4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def stamp() -> str:
    from seraph.shared_types import IST
    return datetime.now(IST).isoformat()


def write_status(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str),
                         encoding="utf-8")
    os.replace(temporary, path)


def dated_baskets() -> list[tuple[str, tuple[str, ...]]]:
    """(rebalance_date, basket) per epoch, oldest first, from C3's snapshots.

    The basket is the same `build_symbol_list` projection the live config
    uses, so a replayed epoch is the basket that epoch actually had -- not
    today's basket backdated.
    """
    import asyncio

    async def read():
        import asyncpg
        from seraph.store.bootstrap import resolve_dsn
        from seraph.ingestion.hawkes_universe import build_symbol_list
        connection = await asyncpg.connect(resolve_dsn())
        try:
            rows = await connection.fetch(
                'SELECT rebalance_date, members FROM universe_snapshots '
                'ORDER BY rebalance_date')
        finally:
            await connection.close()
        return [(row['rebalance_date'].isoformat(),
                 tuple(sorted(build_symbol_list(list(row['members'])))))
                for row in rows]

    return asyncio.run(read())


def basket_for(day: str, epochs) -> "tuple[str, tuple[str, ...]] | None":
    """The newest epoch at or before `day`; None if the day precedes them all."""
    eligible = [epoch for epoch in epochs if epoch[0] <= day]
    return eligible[-1] if eligible else None

def admitted(store, members, window_sessions, refit_sessions) -> int:
    """Hawkes vintages the standardizer would admit: distinct, valued, computed.

    Counted the way `StandardizerHistory.assimilate` counts — one per distinct
    `input_end` — so this number cannot be inflated by re-emitting a retained
    model.
    """
    seen = set()
    for row in store.vintage_history("hawkes", limit=100000):
        if row["origin"] != "computed" or row["value"] is None:
            continue
        seen.add(row["input_end"])
    return len(seen)


def build(args) -> dict:
    from seraph.live.store import LiveStore
    from seraph.live.engine_adapter import DailyVintageProducer
    from seraph.pillars.hawkes.runtime import NativeHistory, NativeHawkesProducer
    from seraph.market_calendar.native_sessions import schedule_from_config
    from seraph.orchestration.standardize import MIN_WINDOW_OBS

    config = json.loads(args.config.read_text(encoding="utf-8"))
    members = sorted(set(config["members"]))
    window = int(config["window_sessions"])
    refit = int(config["refit_sessions"])
    required = args.required if args.required is not None else MIN_WINDOW_OBS

    history = NativeHistory(args.config.parent / config["history_file"])
    schedule = schedule_from_config(args.config, config)
    store = LiveStore(args.store)

    epochs = dated_baskets() if args.baskets == "dated" else []
    if epochs:
        report_epochs = [(d, len(m)) for d, m in epochs]
    else:
        report_epochs = []

    def producer(day):
        # Rebuilt per cadence point so each fit re-reads the deployment
        # registry; `now` stays the real clock, which is what makes the
        # recorded availability actual rather than backdated.
        basket, rebalance = members, config["rebalance_date"]
        if epochs:
            chosen = basket_for(day, epochs)
            if chosen is None:
                return None
            rebalance, basket = chosen[0], list(chosen[1])
        return NativeHawkesProducer(
            history, DailyVintageProducer(LiveStore(args.store)),
            members=basket, rebalance_date=rebalance,
            window_sessions=window, refit_sessions=refit,
            session_schedule=schedule)

    sessions = history.sessions(members, stamp())
    if args.through:
        sessions = [d for d in sessions if d <= args.through]
    # A cadence point is only a candidate once `window` sessions precede it.
    candidates = sessions[window - 1:]
    if args.since:
        candidates = [d for d in candidates if d >= args.since]
    if args.newest_first:
        # NOT order only, which is what an earlier revision of this claimed.
        # `_previous_fit(cutoff)` keeps only fits with
        # `trained_through <= cutoff`, so walking backwards hides every fit
        # already written -- `previous` is always None, every candidate reads
        # as due, and the declared 5-session gate never fires. A run with it
        # produced 12 fits on CONSECUTIVE sessions, an effective
        # `refit_sessions` of 1, which is a change to a declared parameter.
        # So it is allowed only where nothing is written. Use `--since` to
        # start the FORWARD walk later, which preserves the cadence.
        candidates = list(reversed(candidates))

    report = dict(schema="native-hawkes-warmup/1", started_at=stamp(),
                  config=str(args.config), store=str(args.store),
                  window_sessions=window, refit_sessions=refit,
                  required_observations=required,
                  sessions_visible=len(sessions),
                  candidate_cadence_points=len(candidates),
                  basket_policy=args.baskets,
                  admitted_before=admitted(store, members, window, refit),
                  fits=[], skipped={}, errors=[])
    if report_epochs:
        report["epochs"] = len(report_epochs)
        report["epoch_range"] = [report_epochs[0][0], report_epochs[-1][0]]
        report["basket_sizes"] = sorted({n for _, n in report_epochs})
    if candidates:
        report["candidate_range"] = [candidates[0], candidates[-1]]

    if not args.execute:
        report["note"] = ("plan only; pass --execute to fit. Each fit reads "
                          "the full declared window, so expect minutes each.")
        report["finished_at"] = stamp()
        return report

    performed = 0
    for day in candidates:
        if args.max_fits is not None and performed >= args.max_fits:
            report["stopped_early"] = f"--max-fits {args.max_fits} reached"
            break
        cutoff = f"{day}T23:59:59+05:30"
        engine = producer(day)
        if engine is None:
            report["skipped"]["no_snapshot_at_or_before_day"] = (
                report["skipped"].get("no_snapshot_at_or_before_day", 0) + 1)
            continue
        try:
            result = engine.fit_pending(data_cutoff=cutoff)
        except Exception as exc:                            # noqa: BLE001
            report["errors"].append(dict(day=day, error=f"{type(exc).__name__}: {exc}"))
            continue
        if result.get("fitted"):
            performed += 1
            coverage = result.get("coverage") or {}
            report["fits"].append(dict(
                day=day, input_end=coverage.get("input_end"),
                observed_sessions=coverage.get("observed_sessions"),
                incomplete_members=len(coverage.get("incomplete_members") or []),
                evaluated_at=result.get("evaluated_at")))
        else:
            reason = str(result.get("reason") or "unknown")
            report["skipped"][reason] = report["skipped"].get(reason, 0) + 1

    report["fits_performed"] = performed
    report["admitted_after"] = admitted(store, members, window, refit)
    report["shortfall"] = max(0, required - report["admitted_after"])
    report["finished_at"] = stamp()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--store", type=Path,
                        default=ROOT / "prototype_runs/live.sqlite")
    parser.add_argument("--through", help="Last cadence point to consider")
    parser.add_argument("--since",
                        help="Skip cadence points before this date. Order and "
                             "scope only; what is fitted is unchanged.")
    parser.add_argument("--newest-first", action="store_true",
                        help="Attempt candidates newest first, so a bounded "
                             "run reaches fittable ones immediately. Cannot "
                             "introduce look-ahead: each fit still sees only "
                             "its own history and refuses a later model.")
    parser.add_argument("--required", type=int,
                        help="Observations required; defaults to the "
                             "standardizer's MIN_WINDOW_OBS. Never lowered "
                             "automatically to make the gate pass.")
    parser.add_argument("--max-fits", type=int,
                        help="Bound a run; it resumes where it stopped")
    parser.add_argument("--status-file", type=Path,
                        default=ROOT / "prototype_runs/native-hawkes-warmup-status.json")
    parser.add_argument("--baskets", choices=("config", "dated"),
                        default="config",
                        help="'dated' uses the basket each cadence point "
                             "actually had, from C3's universe_snapshots. "
                             "'config' (default) uses the single live basket, "
                             "which can only fit points at or after its own "
                             "rebalance_date.")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.max_fits is not None and args.max_fits < 1:
        parser.error("--max-fits must be positive")
    if args.newest_first and args.execute:
        # newest_first_requires_plan: see the note at the reversal above.
        parser.error(
            "--newest-first cannot be combined with --execute: walking "
            "backwards hides the fits already written from the refit-due "
            "test, so every candidate reads as due and the declared "
            "refit_sessions gate never fires. Use --since to start the "
            "forward walk later instead.")

    report = build(args)
    write_status(args.status_file, report)
    print(json.dumps({k: v for k, v in report.items() if k != "fits"}, indent=2,
                     default=str))
    for fit in report.get("fits", []):
        print(f"[warmup] fitted {fit['day']} -> input_end={fit['input_end']} "
              f"sessions={fit['observed_sessions']} "
              f"incomplete_members={fit['incomplete_members']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
