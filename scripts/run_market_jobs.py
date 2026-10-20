#!/usr/bin/env python3
# C15 / O03 — the market side of ordinary startup
"""Bring the market data and decisions up to date, once, then exit.

C15's gap was that starting the console started the news worker and nothing
else: the daily pillar vintages and the prospective forecasts needed a
second terminal. This is the piece the launcher runs so that does not.

It is a SEQUENCE OF IDEMPOTENT STEPS, not a daemon. `AGENTS.md` §2 chose
cron plus idempotent scripts over a workflow engine, and that choice is
right here: each step below is keyed so that running it twice writes once,
so the launcher can run this on every start, a scheduler can run it hourly,
and an operator can run it by hand, all without coordinating.

What it does NOT do
-------------------
It does not start the live tick loop. `run_live.py` connects to a market
feed, and whether to open a broker connection is an operator's decision
rather than a side effect of opening a dashboard. The launcher prints how
to start it.

It does not fabricate a session. If the corpus has no data, or the database
is unreachable, it says which and exits non-zero. A startup path that
quietly produces nothing is worse than one that fails loudly, because the
console then shows an empty panel with no explanation.

Run:
    python scripts/run_market_jobs.py                 # latest session in corpus
    python scripts/run_market_jobs.py --day 2026-08-21
    python scripts/run_market_jobs.py --status
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seraph.shared_types import IST, ist_timestamp                # noqa: E402

#: Where the console reads what this run achieved.
from seraph.operations.market_jobs_status import (
    read_status,
    status_path as _status_path,
)
from seraph.operations.schedule import freshness

#: Resolved once at import for backwards compatibility. Everything that
#: WRITES or READS calls `_status_path()` per use instead: a constant cannot
#: see an override applied after this module was imported, and that
#: divergence is how a writer and a reader end up on different files.
STATUS_PATH = _status_path()


def _stamp() -> str:
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


async def _latest_session() -> tuple[str | None, str]:
    """The newest session the daily corpus actually holds."""
    try:
        import asyncpg

        from seraph.store.bootstrap import DEFAULT_DSN
        connection = await asyncpg.connect(DEFAULT_DSN, timeout=8)
    except Exception as exc:                                # noqa: BLE001
        return None, (
            f"the research database is unreachable ({type(exc).__name__}). "
            f"Run `docker compose up -d`, then "
            f"`python -m seraph.ingestion.eod2_client` to load the corpus")
    try:
        last = await connection.fetchval("select max(date) from daily_prices")
        rows = await connection.fetchval("select count(*) from daily_prices")
    finally:
        await connection.close()
    if not rows:
        return None, ("the daily corpus is empty. Run "
                      "`python -m seraph.ingestion.eod2_client` (about eight "
                      "minutes; it is idempotent)")
    return str(last), f"{rows:,} daily rows through {last}"


def _run(label: str, argv: list[str], *, timeout: int) -> dict:
    """One step. Captures its outcome rather than letting it abort the rest:
    a failed forecast must not stop the vintages that already landed."""
    started = _stamp()
    try:
        done = subprocess.run(
            [sys.executable, *argv], cwd=ROOT, capture_output=True,
            text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return dict(step=label, ok=False, started=started,
                    error=f"exceeded {timeout}s")
    except Exception as exc:                                # noqa: BLE001
        return dict(step=label, ok=False, started=started,
                    error=f"{type(exc).__name__}: {exc}"[:200])
    tail = (done.stdout or done.stderr or "").strip().splitlines()
    return dict(step=label, ok=done.returncode == 0, started=started,
                finished=_stamp(), exit_code=done.returncode,
                output=tail[-6:])


def _skip(decision: dict, *, note: str, **extra) -> dict:
    """Record a firing that did no work WITHOUT erasing the last real run.

    The first version wrote a fresh report with `session: None`, which blanked
    the console's panel every weekend and -- worse -- made the next weekday
    compare its corpus against nothing, so a Monday with no new data reported
    `first_run` instead of `unchanged`. A skip is an event about the schedule,
    not a replacement for what the pipeline last achieved.
    """
    previous = read_status()
    kept = {key: previous[key] for key in
            ("session", "corpus", "steps", "data", "execution_ok", "job_run")
            if key in previous}
    report = dict(kept, generated=_stamp(), ok=True, skipped=True,
                  schedule=decision, note=note, **extra)
    if "session" in kept:
        report["note"] += (f". The fields above describe the last run that did "
                           f"work, for session {kept['session']}")
    _write(report)
    return report


def run_scheduled(day: str | None = None) -> dict:
    """What the scheduler invokes: trading-day gate, then one fenced run.

    The gate and the lease are the two things a schedule needs and a manual
    run does not. Both reuse machinery that already exists -- the weekday
    plus session-registry rule from `MarketClock`, and `JobStore`'s lease,
    which also records the run in the ledger the HEALTH panel reads.
    """
    from seraph.operations.jobs import JobStore
    from seraph.operations.schedule import JOB_NAME, should_run

    decision = should_run(day)
    if not decision["run"]:
        return _skip(decision, note=("skipped, not failed: "
                                     + decision["reason"]))

    store = JobStore(ROOT / "prototype_runs" / "jobs.sqlite")
    # One run at a time. A second firing while the first is still estimating
    # RMT would duplicate the work and interleave two writes to one status
    # file.
    #
    # `JobStore.run` CATCHES LockUnavailable and records a run with that
    # status rather than raising it, so the overlap case is a status to
    # inspect. An `except LockUnavailable` around this call was dead code --
    # the overlap test is what found it.
    record = store.run(JOB_NAME, lambda context: run_all(day),
                       max_attempts=1)
    if record.status == "lock_unavailable":
        return _skip(decision, overlap=record.error,
                     note=("skipped, not failed: another run of this job "
                           "holds the lease, so this firing stood aside "
                           "rather than duplicating the work"))

    # Write the ledger linkage back, not just onto the returned dict. The
    # first version set it on the return value only, so the status file --
    # which is what the console and the HEALTH panel read -- never carried
    # the run id, and a scheduled run could not be traced to its ledger row.
    saved = read_status()
    saved["job_run"] = dict(run_id=record.run_id, status=record.status,
                            attempt=record.attempt, error=record.error)
    saved["schedule"] = decision
    if record.status != "succeeded":
        # `run_all` raised before reaching `_write`, so every field below
        # describes an EARLIER run. Saying so matters: otherwise the previous
        # session and its green steps read as this firing's result.
        saved["ok"] = False
        saved["execution_ok"] = False
        saved["note"] = (
            f"the run FAILED under the lease: {record.error}. Any session, "
            f"steps or freshness shown here describe the last run that "
            f"completed, not this firing.")
    persisted = {k: v for k, v in saved.items() if k not in ("ran", "path")}
    _write(persisted)
    return saved


def run_all(day: str | None = None) -> dict:
    # Acquisition FIRST, and the corpus is read AFTER it. The session read
    # used to happen before any step, so with acquisition added the vintages
    # and the forecast would have been computed for the pre-acquisition date
    # -- a run that fetched today's prices and then scored yesterday.
    acquisition = _run("fresh market data",
                       ["scripts/run_acquisition.py"], timeout=2400)

    session, detail = asyncio.run(_latest_session())
    if session is None:
        report = dict(generated=_stamp(), ok=False, blocked=detail,
                      steps=[acquisition])
        _write(report)
        return report

    target = day or session
    steps = [
        acquisition,
        # The daily pillar vintages. RMT is computed here (about two
        # minutes: FR17 needs two windows and FR19 bootstraps each 1,000
        # times); Hamilton records its standing exclusion; Hawkes is the
        # archived research estimate or a declared absence.
        _run("daily vintages",
             ["scripts/run_daily.py", "--day", target], timeout=900),
        # The prospective forecast for the same cutoff. Publishes what the
        # saved walk-forward produced; reports rather than refits if the
        # experiment has not reached this date.
        _run("prospective forecast",
             ["scripts/run_forecast.py", "--as-of", target], timeout=300),
        # Settle anything whose horizon has now elapsed. The store refuses
        # an immature outcome, so this is safe to run every time.
        _run("settle matured forecasts",
             ["scripts/run_forecast.py", "--settle"], timeout=300),
        # Prediction and early warning: the actual engine, on the market
        # snapshot, about twenty seconds. This is what makes the console's
        # PREDICTION panel current rather than whatever was last computed by
        # hand -- the refresh schedule the system is supposed to have.
        # Overwrites its state file by design: a warning is current status,
        # not evidence of a particular run.
        _run("prediction and early warning",
             ["scripts/run_prediction.py"], timeout=600),
    ]
    # Two separate facts (O03). The steps above can all succeed while the
    # corpus has not moved -- an exchange holiday, or nobody ran the loader.
    # Reporting one number for both is how a green panel ends up sitting on
    # a corpus that stopped updating.
    previous = read_status()
    data = freshness(previous_session=previous.get("session") if previous.get("ran") else None,
                     current_session=session)
    # The acquisition step is the authority on whether a new OBSERVATION
    # arrived, as opposed to the corpus merely differing from the last run's
    # record. Its own report is read rather than inferred from dates.
    data["acquisition"] = _acquisition_summary()
    report = dict(generated=_stamp(), ok=all(s["ok"] for s in steps),
                  execution_ok=all(s["ok"] for s in steps),
                  session=target, corpus=detail, steps=steps, data=data,
                  note=("every step is idempotent, so this is safe to run on "
                        "each launch, from a scheduler, or by hand. "
                        "`ok`/`execution_ok` says whether the steps ran; "
                        "`data` says separately whether new data arrived and "
                        "whether the corpus is current. The live tick loop is "
                        "NOT started here: opening a broker connection is an "
                        "operator decision, not a side effect of opening a "
                        "dashboard. Start it with "
                        "`python scripts/run_live.py --status` first, then "
                        "`--replay --once` or a live run."))
    _write(report)
    return report


def _acquisition_summary() -> dict:
    """What the acquisition step reported, read from its own status file."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_seraph_acquisition", ROOT / "scripts" / "run_acquisition.py")
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        saved = module.status()
    except Exception as exc:                                # noqa: BLE001
        return dict(ran=False, note=f"acquisition status unreadable: {exc}")
    if not saved.get("ran"):
        return dict(ran=False, note=saved.get("note", ""))
    inner = saved.get("acquisition") or {}
    return dict(ran=True, ok=saved.get("ok"), acquired=saved.get("acquired"),
                generated=saved.get("generated"),
                latest_before=inner.get("latest_before"),
                latest_after=inner.get("latest_after"),
                stored_sessions=inner.get("stored_sessions") or [],
                rows_written=inner.get("rows_written"),
                failures=inner.get("failures") or [],
                note=saved.get("note", ""))


def _write(report: dict) -> None:
    # Resolved here, not at import: a module-level constant captured at
    # import time ignores a later SERAPH_MARKET_JOBS_STATUS, which would let
    # the writer and the console's reader disagree about the file.
    path = _status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str),
                    encoding="utf-8")


def status() -> dict:
    """What the last run achieved. The package owns the read.

    One definition of where the status lives, so the writer here and the
    console's reader cannot drift -- and so the console does not need this
    script on its import path.
    """
    from seraph.operations.market_jobs_status import read_status

    return read_status()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", help="session date, YYYY-MM-DD; "
                                      "defaults to the newest in the corpus")
    parser.add_argument("--status", action="store_true",
                        help="report the last run; compute nothing")
    parser.add_argument("--scheduled", action="store_true",
                        help=("run as the scheduler does: skip non-trading "
                              "days and hold a lease so two firings cannot "
                              "overlap"))
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(status(), indent=2, default=str))
        return 0

    report = run_scheduled(args.day) if args.scheduled else run_all(args.day)
    if report.get("skipped"):
        print(f"[market] skipped: {report['note']}", flush=True)
        return 0
    if report.get("blocked"):
        print(f"[market] BLOCKED: {report['blocked']}", flush=True)
        return 2
    print(f"[market] session {report['session']} ({report['corpus']})",
          flush=True)
    for step in report["steps"]:
        mark = "ok  " if step["ok"] else "FAIL"
        print(f"[market]   [{mark}] {step['step']}", flush=True)
        if not step["ok"]:
            print(f"[market]          {step.get('error') or step.get('output')}",
                  flush=True)
    # Resolved here and formatted defensively. A module constant captured at
    # import ignores a later override, and `relative_to` RAISES for a path
    # outside the tree -- so a completely successful pipeline exited 1 on a
    # print, which is exactly the shape of failure that makes a scheduled run
    # look broken when the work landed.
    written = _status_path()
    try:
        shown = written.relative_to(ROOT)
    except ValueError:
        shown = written
    print(f"[market] status: {shown}", flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
