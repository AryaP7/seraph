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
import hashlib
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


#: Hamilton's standing exclusion, recorded rather than re-derived.
#:
#: `original_execution` ends its Hamilton block by setting
#: `absence='structural'` with
#: `exclusion='standing research decision (NOT_PRODUCTION)'`. The pillar is
#: excluded by a research decision about regime-support validity, not by a
#: data-dependent outcome -- so the estimate is diagnostic and never
#: contributes to the composite however it comes out.
#:
#: Re-deriving it on every daily tick is therefore expensive and changes
#: nothing. The cost is not the EM fit: that block loops over EVERY date in
#: the calendar (5,363 of them) issuing two database queries each --
#: `universe_for` and `build_row` -- before Hamilton is fitted at all. On
#: this corpus that dominates the entire job.
#:
#: So the default records the exclusion with its reason, and
#: `--hamilton diagnostic` runs the full walk-forward for anyone who wants
#: the diagnostic. Nothing is dropped and nothing is pretended.
HAMILTON_EXCLUSION = dict(
    absence="structural",
    # One of PillarObservation's three permitted reasons: this value reaches
    # `UnavailableEmission.reason`, a closed Literal. The exclusion's actual
    # nature is in `reason` below and in the stored vintage's detail.
    absence_reason="no_data_coverage",
    reason=("regime support unvalidated; diagnostic only, and excluded from "
            "the composite by a standing research decision (NOT_PRODUCTION). "
            "This is NOT a feed outage. Run with --hamilton diagnostic to "
            "recompute the walk-forward estimate anyway"),
)


async def compute_pillars(day: str, *, hamilton: str = "excluded"
                          ) -> tuple[dict, dict]:
    """RMT (and optionally the Hamilton diagnostic) from the daily corpus.

    `hamilton='excluded'` skips the walk-forward and records the standing
    exclusion directly. `hamilton='diagnostic'` calls the full executor.
    """
    import asyncpg

    from seraph.store.bootstrap import resolve_dsn

    conn = await asyncpg.connect(resolve_dsn())
    try:
        if hamilton == "diagnostic":
            from seraph.orchestration.original_execution import execute_originals
            return await execute_originals(conn, day)
        return await _rmt_only(conn, day)
    finally:
        await conn.close()


async def _rmt_only(conn, day: str) -> tuple[dict, dict]:
    """RMT from the daily corpus; Hamilton's exclusion recorded, not re-derived.

    This mirrors `original_execution`'s RMT block exactly -- two endpoint
    windows so FR17's eigenvector rotation has a predecessor, the same
    `aligned_returns` preparation and the same `RmtEngine` -- rather than
    reimplementing the spectral path.
    """
    import hashlib
    from datetime import date as _date

    import numpy as np

    from seraph.features.alignment import aligned_returns
    from seraph.market_calendar import SessionCalendar
    from seraph.orchestration.research_scripts import load as load_scripts
    from seraph.pillars.rmt.engine import RmtEngine, T_WINDOW

    (universe_for,) = load_scripts("build_observations", "universe_for")

    stamp = SessionCalendar().close_timestamp(day)
    end = _date.fromisoformat(day)
    members = await universe_for(conn, end)
    if not members:
        raise ValueError(f"no point-in-time universe at {day}")

    output = {p: dict(model=f"original {p}",
                      origin="fresh read-only source execution",
                      score_eligible=False, value=None,
                      information_timestamp=stamp, detail=None,
                      absence="structural",
                      absence_reason="insufficient_history",
                      reason="insufficient data")
              for p in ("hawkes", "rmt", "hamilton")}
    audit: dict = {"cutoff": stamp, "errors": {}, "input_hashes": {},
                   "limitations": [
                       "RMT spectral-state warmup uses two endpoint windows; "
                       "SCA calibration is incomplete"]}

    rows = await conn.fetch(
        "SELECT symbol,date,adj_close FROM daily_prices WHERE symbol=ANY($1::text[]) "
        "AND date<=$2 AND adj_close>0 ORDER BY date,symbol", members, end)
    calendar = sorted({r["date"] for r in rows})
    px: dict = {s: {} for s in members}
    for row in rows:
        px[row["symbol"]][row["date"]] = float(row["adj_close"])

    engine = RmtEngine()
    if calendar and calendar[-1] == end and len(calendar) >= T_WINDOW + 2:
        last, keep = None, ()
        for days in (calendar[:-1], calendar):
            panel, keep = aligned_returns(px, days, T_WINDOW + 1)
            if len(keep) < 30:
                break
            audit["input_hashes"][f"rmt_{days[-1]}"] = hashlib.sha256(
                panel.tobytes()).hexdigest()
            last = engine.step(returns=panel, members=keep,
                               date=days[-1].isoformat())
        if last is not None and last.status == "ok" and len(keep) >= 30:
            detail, sca = last.value
            output["rmt"].update(
                score_eligible=True, value=engine._prev_share,
                detail={"spectral": detail.model_dump(), "sca_t": sca},
                reason=None, absence=None, absence_reason=None)
            audit["limitations"].extend(w.message for w in last.warnings)
    else:
        output["rmt"]["reason"] = (
            f"RMT needs {T_WINDOW + 2} aligned sessions ending {day}; "
            f"the corpus has {len(calendar)} ending "
            f"{calendar[-1] if calendar else 'nothing'}")

    output["hamilton"].update(HAMILTON_EXCLUSION)
    audit["limitations"].append(HAMILTON_EXCLUSION["reason"])
    return output, audit


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
    # FR13 v4 emits the branching ratio REGARDLESS of the sell-side gate:
    # "a gated-off reading ... is distinct from an absence of contagion -- the
    # branching ratio is reported regardless". The `mts` column is the GATED
    # statistic and is 0.0 on 352 of these 473 rows, so emitting it as the
    # pillar value would feed the ECDF a reference series that is 74%
    # structural zeros -- and would disagree with the native producer, which
    # persists `n/(1-n)` ungated for exactly this reason
    # (`pillars/hawkes/runtime.py:_persist`). The gate stays as provenance.
    n = float(row["branching_ratio_n"])
    gated = float(row["mts"])
    return dict(input_end=_stamp(observed),
                emission_available_at=_stamp(observed + EMISSION_LAG),
                value=n / (1.0 - n),
                detail=dict(branching_ratio_n=n,
                            mts=gated,
                            fr13_gate_open=bool(gated > 0.0),
                            raw_statistic="ungated_n_over_one_minus_n",
                            source=str(ARCHIVED_HAWKES.relative_to(ROOT)),
                            measured_at=_stamp(observed)))


def persist_absence(store, pillar, input_end, *, absence, reason, detail):
    """Register the declaration itself, without inventing a fitted model.

    An unregistered named absence was withheld by the runtime just like an
    unknown model, so even Hamilton's standing exclusion could not reach D2.
    Availability is when this producer recorded the declaration, not its
    historical observation date.
    """
    from seraph.live.inference import ModelBundle
    manifest = dict(producer=pillar, input_end=input_end, kind='declared_absence',
                    absence=absence, absence_reason=reason, detail=detail,
                    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    identity = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    bundle_id = f'{pillar}:absence:{identity}'
    prior = next((b for b in store.deployments() if b['bundle_id'] == bundle_id), None)
    available = prior['available_at'] if prior else _stamp(datetime.now(IST))
    store.register_deployment(ModelBundle(bundle_id=bundle_id, producer=pillar,
        trained_through=input_end, available_at=available, manifest_hash=identity,
        notes=json.dumps(manifest, sort_keys=True)))
    return store.record_daily_vintage(producer=pillar, input_end=input_end,
        emission_available_at=available, origin='absent', absence=absence,
        absence_reason=reason, bundle_id=bundle_id, detail=detail)


def persist(store: LiveStore, day: str, pillars: dict, *,
            hawkes_mode: str, input_audit=None) -> list[dict]:
    """Write one day's vintages. Returns what was stored, per pillar."""
    close = datetime.fromisoformat(f"{day}T15:30:00+05:30")
    available = _stamp(close + EMISSION_LAG)
    written = []

    for pillar in ("rmt", "hamilton"):
        entry = pillars.get(pillar) or {}
        if entry.get("score_eligible") and entry.get("value") is not None:
            from seraph.live.inference import ModelBundle
            input_end = entry.get("information_timestamp") or _stamp(close)
            manifest = dict(producer=pillar, input_end=input_end, output=entry,
                input_audit=input_audit or {},
                implementation_sha256=hashlib.sha256(
                    (ROOT/'seraph/pillars'/pillar/'engine.py').read_bytes()).hexdigest())
            identity = hashlib.sha256(json.dumps(manifest, sort_keys=True,
                                                 default=str).encode()).hexdigest()
            bundle_id = f'{pillar}:{identity}'
            prior = next((b for b in store.deployments()
                          if b['bundle_id'] == bundle_id), None)
            computed_at = prior['available_at'] if prior else _stamp(datetime.now(IST))
            store.register_deployment(ModelBundle(
                bundle_id=bundle_id, producer=pillar, trained_through=input_end,
                available_at=computed_at, manifest_hash=identity,
                notes=json.dumps(manifest, sort_keys=True, default=str)))
            written.append(store.record_daily_vintage(
                producer=pillar,
                input_end=input_end,
                emission_available_at=computed_at, origin="computed",
                value=float(entry["value"]),
                bundle_id=bundle_id,
                detail=dict(entry.get("detail") or {})))
        else:
            written.append(persist_absence(store, pillar,
                entry.get("information_timestamp") or _stamp(close),
                absence=entry.get("absence") or "structural",
                reason=entry.get("absence_reason") or "no_data_coverage",
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
    written.append(persist_absence(store, 'hawkes', _stamp(close),
        # `absence_reason` must be one of PillarObservation's three
        # permitted reasons; it flows into UnavailableEmission.reason, which
        # is a closed Literal. The specific cause goes in `detail` below.
        absence="structural", reason="no_data_coverage",
        detail=dict(reason=(
            "No fresh Hawkes estimate is supplied by this daily job. "
            "It requires a registered native-intraday producer with sufficient "
            "history; archived observations are not current estimates."))))
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
    parser.add_argument("--hamilton", choices=("excluded", "diagnostic"),
                        default="excluded",
                        help="excluded: record the standing research "
                             "exclusion without re-deriving it (default; the "
                             "walk-forward costs 5,363 date iterations with "
                             "two queries each and the result is excluded "
                             "from the composite either way). diagnostic: run "
                             "the full walk-forward anyway.")
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

    what = ("RMT and the Hamilton diagnostic" if args.hamilton == "diagnostic"
            else "RMT")
    print(f"[daily] {args.day}: computing {what} from the daily corpus "
          f"(minutes, not seconds -- FR17 needs two windows and FR19 "
          f"bootstraps each 1,000 times)", flush=True)
    pillars, audit = asyncio.run(compute_pillars(args.day,
                                                 hamilton=args.hamilton))
    written = persist(store, args.day, pillars, hawkes_mode=args.hawkes, input_audit=audit)

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
