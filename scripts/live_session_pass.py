#!/usr/bin/env python3
# C13 — scheduled live-session pass (FR28, NFR1); evidence recorder for run_live.
"""Run ONE live CSRS pass during a genuine NSE session and record what happened.

This exists because a command written into a document is not a scheduled run.
`scripts/register_live_task.py` registers this script with Windows Task
Scheduler, and this script is what the scheduler actually executes.

What it does, in order, recording each step whether it passes or fails:

1. **Clock and calendar.** Reads `SessionCalendar`. If the market is not open it
   records `market_closed` and exits non-zero. It never proceeds on a closed
   market and never substitutes an archived bar for a live one.
2. **Broker authentication.** One read-only `instruments_nse()` probe. A Kite
   access token is invalidated daily at ~06:00 IST regardless of when it was
   issued (`seraph/ingestion/kite_client.py`), so a token minted before the open
   is commonly dead by it. That is recorded as a blocker, not worked around.
3. **The live pass.** `run_live.py --once --hawkes-config ...` as a subprocess,
   with its stdout and stderr captured verbatim to the evidence directory.
4. **Post-state.** `run_live.py --status`, the `live` stream head, and the
   decision itself if one was committed — including its mask, its publication
   state and the reason it carries.

`withheld` is a correct outcome, not a failure: the publication gate is a
scientific safeguard and this script does not bypass it. The exit code reports
whether a decision reached the `live` stream at all, which is the engineering
question. Why it was or was not published is read off the recorded reasons.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def stamp() -> str:
    from seraph.shared_types import IST
    return datetime.now(IST).isoformat()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    os.replace(temporary, path)


def market_state(calendar_path: Path | None) -> dict:
    """What the calendar says right now. No network, no broker.

    Routed through exactly the helpers `run_live.py` uses, so this gate and
    the pass it guards read the same calendar. An earlier version called
    `SessionCalendar.default()` / `state_at()` / `.verified`, none of which
    exist, so without `--calendar` this raised AttributeError on step 1 and
    the recorder never reached the broker probe or the pass.
    """
    from seraph.live import MarketClock
    from seraph.live.lifecycle import next_session_window
    from seraph.market_calendar.exchange import load as load_calendar
    from seraph.shared_types import IST

    now = datetime.now(IST)
    clock = MarketClock(load_calendar(calendar_path) if calendar_path else None)
    window = dict(next_session_window(clock, at=now))
    window["checked_at"] = now.isoformat()
    # `next_session_window` names it `calendar_verified`; keep `verified` too
    # so the recorded evidence stays readable against older runs.
    window["verified"] = bool(window.get("calendar_verified", False))
    window["is_open"] = bool(clock.is_open(now))
    return window


def broker_probe() -> dict:
    """One read-only call. Proves the daily token is alive, or why it is not."""
    try:
        from seraph.ingestion.kite_client import KiteClient, token_cache_path
        cache = token_cache_path()
        login = None
        if cache.exists():
            login = json.loads(cache.read_text(encoding="utf-8")).get("login_time")
        instruments = KiteClient().instruments_nse()
        return dict(ok=True, nse_instruments=len(instruments), login_time=login)
    except Exception as exc:                                    # noqa: BLE001
        return dict(ok=False, error=f"{type(exc).__name__}: {exc}"[:600])


def run_pass(args, evidence: Path) -> dict:
    command = [str(PYTHON), "-I", str(ROOT / "scripts" / "run_live.py"),
               "--once", "--once-timeout", str(args.once_timeout),
               "--store", str(args.store)]
    if args.hawkes_config:
        command += ["--hawkes-config", str(args.hawkes_config)]
    if args.calendar:
        command += ["--calendar", str(args.calendar)]

    started = stamp()
    try:
        done = subprocess.run(command, capture_output=True, text=True,
                              cwd=str(ROOT), timeout=args.once_timeout + 300)
        code, out, err = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as exc:
        code = None
        out = exc.stdout or ""
        err = (exc.stderr or "") + "\n[wrapper] subprocess timeout"
    (evidence / "run_live.stdout.log").write_text(out or "", encoding="utf-8")
    (evidence / "run_live.stderr.log").write_text(err or "", encoding="utf-8")
    return dict(command=" ".join(command), started_at=started,
                finished_at=stamp(), returncode=code,
                stdout_tail=(out or "").splitlines()[-40:],
                stderr_tail=(err or "").splitlines()[-40:])


def post_state(store: Path) -> dict:
    """The store's own account of what the pass left behind."""
    from seraph.live.store import LiveStore

    live = LiveStore(store)
    head = live.stream_head("live") if hasattr(live, "stream_head") else None
    out: dict = dict(live_stream_head=head)

    import sqlite3
    con = sqlite3.connect(store)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT stream_id, publication_state, COUNT(*) n FROM live_decisions "
            "GROUP BY stream_id, publication_state").fetchall()
        out["decision_counts"] = [dict(r) for r in rows]
        latest = con.execute(
            "SELECT * FROM live_decisions WHERE stream_id='live' "
            "ORDER BY as_of DESC, computed_at DESC LIMIT 1").fetchone()
        if latest is None:
            out["live_decision"] = None
        else:
            payload = json.loads(latest["payload_json"])
            mask = payload.get("mask") or (payload.get("csrs") or {}).get("mask")
            publication = payload.get("publication") or {}
            out["live_decision"] = dict(
                decision_id=latest["decision_id"], as_of=latest["as_of"],
                computed_at=latest["computed_at"],
                publication_state=latest["publication_state"],
                mask=mask,
                csrs=(payload.get("csrs") if not isinstance(payload.get("csrs"), dict)
                      else payload["csrs"].get("csrs")),
                publication_reasons=publication.get("reasons")
                or publication.get("why_not") or publication.get("reason"),
            )
    finally:
        con.close()
    return out


def warmup() -> dict:
    from seraph.live.store import LiveStore
    from seraph.dashboard.console_backend import warmup_progress
    return warmup_progress(LiveStore(ROOT / "prototype_runs" / "live.sqlite"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path,
                        default=ROOT / "prototype_runs/live.sqlite")
    parser.add_argument("--hawkes-config", type=Path,
                        default=ROOT / "prototype_runs/live.native-hawkes.json")
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--once-timeout", type=int, default=1200)
    parser.add_argument("--evidence-dir", type=Path,
                        default=ROOT / "prototype_runs/live-passes")
    parser.add_argument("--allow-closed", action="store_true",
                        help="Run the pass even when the calendar says the "
                             "market is shut. For exercising the wrapper only "
                             "— a pass taken on a closed market is not live "
                             "verification and is recorded as such.")
    args = parser.parse_args()

    tag = datetime.now().strftime("%Y%m%dT%H%M%S")
    evidence = args.evidence_dir / tag
    evidence.mkdir(parents=True, exist_ok=True)
    report: dict = dict(schema="live-session-pass/1", tag=tag,
                        started_at=stamp(), store=str(args.store),
                        hawkes_config=str(args.hawkes_config))

    report["market"] = market_state(args.calendar)
    # `MarketClock.is_open` decides this, not a string test on the state name.
    # The previous `state.endswith("open")` was wrong twice over: the key is
    # `market_state`, not `state` (KeyError), and `"pre_open"` ends with
    # "open", so a pass taken BEFORE the bell would have been recorded as a
    # genuine live session.
    open_now = bool(report["market"]["is_open"])
    report["market_open"] = open_now
    if not open_now and not args.allow_closed:
        report["outcome"] = "market_closed"
        report["finished_at"] = stamp()
        write_json(evidence / "pass.json", report)
        print(json.dumps(report, indent=2, default=str))
        return 2
    report["ran_on_closed_market"] = bool(not open_now and args.allow_closed)

    report["broker"] = broker_probe()
    if not report["broker"]["ok"]:
        report["outcome"] = "broker_unauthenticated"
        report["finished_at"] = stamp()
        write_json(evidence / "pass.json", report)
        print(json.dumps(report, indent=2, default=str))
        return 3

    report["warmup_before"] = warmup()
    report["pass"] = run_pass(args, evidence)
    report["warmup_after"] = warmup()
    report["post"] = post_state(args.store)

    decision = report["post"].get("live_decision")
    report["outcome"] = ("live_decision_committed" if decision
                         else "no_live_decision_committed")
    report["finished_at"] = stamp()
    write_json(evidence / "pass.json", report)
    write_json(args.evidence_dir / "latest.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "pass"},
                     indent=2, default=str))
    return 0 if decision else 4


if __name__ == "__main__":
    sys.exit(main())
