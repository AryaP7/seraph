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
STATUS_PATH = ROOT / "prototype_runs" / "market-jobs-status.json"


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


def run_all(day: str | None = None) -> dict:
    session, detail = asyncio.run(_latest_session())
    if session is None:
        report = dict(generated=_stamp(), ok=False, blocked=detail, steps=[])
        _write(report)
        return report

    target = day or session
    steps = [
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
    ]
    report = dict(generated=_stamp(), ok=all(s["ok"] for s in steps),
                  session=target, corpus=detail, steps=steps,
                  note=("every step is idempotent, so this is safe to run on "
                        "each launch, from a scheduler, or by hand. The live "
                        "tick loop is NOT started here: opening a broker "
                        "connection is an operator decision, not a side "
                        "effect of opening a dashboard. Start it with "
                        "`python scripts/run_live.py --status` first, then "
                        "`--replay --once` or a live run."))
    _write(report)
    return report


def _write(report: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(report, indent=2, default=str),
                           encoding="utf-8")


def status() -> dict:
    """What the last run achieved, for the console's startup panel."""
    if not STATUS_PATH.is_file():
        return dict(ran=False,
                    note=("the market jobs have not run in this "
                          "installation. The launcher runs them; "
                          "`python scripts/run_market_jobs.py` runs them by "
                          "hand"))
    try:
        body = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return dict(ran=False, note=f"status file unreadable: {exc}")
    return dict(ran=True, **body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", help="session date, YYYY-MM-DD; "
                                      "defaults to the newest in the corpus")
    parser.add_argument("--status", action="store_true",
                        help="report the last run; compute nothing")
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(status(), indent=2, default=str))
        return 0

    report = run_all(args.day)
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
    print(f"[market] status: {STATUS_PATH.relative_to(ROOT)}", flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
