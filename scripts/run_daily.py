#!/usr/bin/env python3
# Daily pillar job — compute or source the day's vintages, persist them (T03)
"""Produce one day's pillar vintages and store them for the live runtime.

This is the job `engine_adapter.NullProducers` was waiting for. Its docstring
said: "RMT and Hamilton are daily products read from the store, not derived
from a five-minute bar." This computes them; `DailyVintageProducer` reads
them.

What each pillar gets, and why they differ
------------------------------------------
**RMT (FR16-FR19) and Hamilton (FR20-FR24): computed here.** Both are
functions of the daily corpus, which `scripts/build_universe.py` and the EOD2
backfill have now loaded -- 7.4M daily rows over 3,524 symbols, and 43
point-in-time universe snapshots. `orchestration/original_execution` already
knows how to run them; this persists what it returns. Expect minutes, not
seconds: FR17 needs two endpoint windows and FR19 bootstraps each with 1,000
replications on a 1000x500 matrix.

**Hawkes (FR10-FR15): archived or absent, never computed here.** Its fresh
estimate needs 5-minute intraday bars. `intraday_bars` is empty, and filling
it needs a Kite Connect subscription and a daily interactive login
(`scripts/backfill_intraday.py` is written and checkpointed, and waits on
that). So `--hawkes archived` reads the persisted research output in
`research_data/original_hawkes.parquet` -- a real measurement of an earlier
run, stamped with ITS OWN as-of and marked `origin='archived'` -- and
`--hawkes absent` declares a structural absence instead.

That distinction is the point. An archived 2026-08-20 branching ratio shown
as a current reading would be exactly the substitution this project's mode
discipline exists to prevent, so the origin travels with the number all the
way to the screen.

Idempotent: a vintage is keyed `(producer, input_end, bundle_id)`, so a cron
tick that fires twice writes once.

Run:
    python scripts/run_daily.py --day 2026-08-21
    python scripts/run_daily.py --day 2026-08-21 --hawkes absent
    python scripts/run_daily.py --status
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seraph.live.store import LiveStore                        # noqa: E402
from seraph.shared_types import IST, ist_timestamp             # noqa: E402

#: How long after the session close a daily estimate is treated as readable.
#: An estimator cannot emit before the session it consumed has ended, and the
#: live service's availability rule is `emission_available_at <= as_of`, so a
#: vintage stamped AT the close would be admitted by a decision taken at the
#: close -- before the computation could have finished. Declared, not implied.
EMISSION_LAG = timedelta(minutes=30)

ARCHIVED_HAWKES = ROOT / "research_data" / "original_hawkes.parquet"


def _stamp(moment: datetime) -> str:
    return ist_timestamp(moment.replace(microsecond=0))


async def compute_pillars(day: str) -> tuple[dict, dict]:
    """RMT and Hamilton from the daily corpus, via the existing executor."""
    import asyncpg

    from seraph.orchestration.original_execution import execute_originals
    from seraph.store.bootstrap import DEFAULT_DSN

    conn = await asyncpg.connect(DEFAULT_DSN)
    try:
        return await execute_originals(conn, day)
    finally:
        await conn.close()


def archived_hawkes(day: str) -> dict | None:
    """The newest persisted Hawkes estimate at or before `day`, or `None`.

    Read from the research snapshot rather than recomputed. Returns the row's
    own timestamp, because an archived value's as-of is when it was measured
    and not when it was read.
    """
    if not ARCHIVED_HAWKES.exists():
        return None
    import polars as pl

    frame = pl.read_parquet(ARCHIVED_HAWKES)
    cutoff = datetime.fromisoformat(f"{day}T23:59:59+05:30")
    rows = [r for r in frame.iter_rows(named=True)
            if r["ts"].astimezone(IST) <= cutoff]
    if not rows:
        return None
    row = max(rows, key=lambda r: r["ts"])
    observed = row["ts"].astimezone(IST)
    return dict(input_end=_stamp(observed),
                emission_available_at=_stamp(observed + EMISSION_LAG),
                value=float(row["mts"]),
                detail=dict(branching_ratio_n=float(row["branching_ratio_n"]),
                            mts=float(row["mts"]),
                            source=str(ARCHIVED_HAWKES.relative_to(ROOT)),
                            measured_at=_stamp(observed)))


def persist(store: LiveStore, day: str, pillars: dict, *,
            hawkes_mode: str) -> list[dict]:
    """Write one day's vintages. Returns what was stored, per pillar."""
    close = datetime.fromisoformat(f"{day}T15:30:00+05:30")
    available = _stamp(close + EMISSION_LAG)
    written = []

    for pillar in ("rmt", "hamilton"):
        entry = pillars.get(pillar) or {}
        if entry.get("score_eligible") and entry.get("value") is not None:
            written.append(store.record_daily_vintage(
                producer=pillar,
                input_end=entry.get("information_timestamp") or _stamp(close),
                emission_available_at=available, origin="computed",
                value=float(entry["value"]),
                bundle_id=str(entry.get("model") or f"original {pillar}"),
                detail=dict(entry.get("detail") or {})))
        else:
            written.append(store.record_daily_vintage(
                producer=pillar,
                input_end=entry.get("information_timestamp") or _stamp(close),
                emission_available_at=available, origin="absent",
                absence=entry.get("absence") or "structural",
                absence_reason=entry.get("absence_reason") or "no_data_coverage",
                bundle_id=str(entry.get("model") or f"original {pillar}"),
                detail=dict(reason=entry.get("reason") or "")))

    if hawkes_mode == "archived":
        archived = archived_hawkes(day)
        if archived is not None:
            written.append(store.record_daily_vintage(
                producer="hawkes", input_end=archived["input_end"],
                emission_available_at=archived["emission_available_at"],
                origin="archived", value=archived["value"],
                bundle_id="original hawkes (research snapshot)",
                detail=archived["detail"]))
            return written
    written.append(store.record_daily_vintage(
        producer="hawkes", input_end=_stamp(close),
        emission_available_at=available, origin="absent",
        absence="structural", absence_reason="no_intraday_coverage",
        bundle_id="original hawkes",
        detail=dict(reason=(
            "a fresh Hawkes estimate needs 5-minute intraday bars; "
            "intraday_bars is empty and filling it needs a Kite Connect "
            "subscription plus a daily interactive login "
            "(scripts/backfill_intraday.py)"))))
    return written


def report_status(store: LiveStore) -> int:
    rows = store.daily_vintages()
    print(json.dumps(dict(
        stored=rows,
        note=("`origin` says where each number came from: 'computed' means "
              "this installation ran the estimator, 'archived' means it was "
              "read from a prior research artefact and is a measurement of "
              "an earlier run, 'absent' means there is no estimate")),
        indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", help="session date, YYYY-MM-DD")
    parser.add_argument("--store", type=Path,
                        default=ROOT / "prototype_runs" / "live.sqlite")
    parser.add_argument("--hawkes", choices=("archived", "absent"),
                        default="archived",
                        help="archived: read the persisted research estimate "
                             "and mark it archived. absent: declare a "
                             "structural absence. Never computed here.")
    parser.add_argument("--status", action="store_true",
                        help="report stored vintages; compute nothing")
    args = parser.parse_args(argv)

    store = LiveStore(args.store)
    if args.status:
        return report_status(store)
    if not args.day:
        parser.error("--day is required unless --status is given")

    print(f"[daily] {args.day}: computing RMT and Hamilton from the daily "
          f"corpus (minutes, not seconds -- FR17 needs two windows and FR19 "
          f"bootstraps each 1,000 times)", flush=True)
    pillars, audit = asyncio.run(compute_pillars(args.day))
    written = persist(store, args.day, pillars, hawkes_mode=args.hawkes)

    for row in written:
        print(f"[daily]   {row['producer']:9} origin={row['origin']:9} "
              f"stored={row['stored']}", flush=True)
    if audit.get("errors"):
        print(f"[daily] estimator errors: {audit['errors']}", flush=True)
    for limitation in audit.get("limitations", ()):
        print(f"[daily] limitation: {limitation}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
