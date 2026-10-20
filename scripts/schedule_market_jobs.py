#!/usr/bin/env python
"""Register SERAPH's daily pipeline with the OS scheduler (O03).

    python scripts/schedule_market_jobs.py --status      # what is registered
    python scripts/schedule_market_jobs.py --show        # the exact commands
    python scripts/schedule_market_jobs.py --register    # create the task
    python scripts/schedule_market_jobs.py --run-now     # fire it once
    python scripts/schedule_market_jobs.py --unregister  # remove it
    python scripts/schedule_market_jobs.py --cron        # the crontab line

`AGENTS.md` §2 chose cron and idempotent scripts over a workflow engine, and
then no schedule was ever written: the daily sequence ran when somebody
launched the console, so the prediction panel was current only on days the
application happened to be opened.

This registers `run_market_jobs.py --scheduled` on weekdays at 18:30 IST --
three hours after the regular close, with room for the end-of-day files to
publish. It adds no pipeline logic: the trading-day gate, the lease that
prevents overlap, and the freshness accounting all live in the job itself, so
a hand-run and a scheduled run behave identically.

**Windows Task Scheduler is the primary environment**, via `schtasks`, which
creates a task for the current user and needs no elevation. `--cron` prints
the equivalent crontab line for the other supported environments.

**Holidays.** No exchange holiday calendar exists in this repository, so the
trigger is Mon-Fri -- the two days that are certainly not sessions -- and the
job decides the rest from the corpus at run time. On an unregistered holiday
the task fires and records *executed, data unchanged*, which is a more useful
signal than silence and is why the status separates those two facts.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seraph.operations import schedule  # noqa: E402

TARGET = ROOT / "scripts" / "run_market_jobs.py"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _commands() -> dict:
    name = schedule.task_name_override()
    python = schedule.python_executable()
    return dict(
        task_name=name,
        at_ist=schedule.RUN_AT_IST.strftime("%H:%M"),
        at_local=schedule.run_at_local().strftime("%H:%M"),
        local_is_ist=schedule.local_equals_ist(),
        register=schedule.register_command(
            python=python, script=str(TARGET), task_name=name,
            working_directory=str(ROOT)),
        query=schedule.query_command(name),
        delete=schedule.delete_command(name),
        run_now=schedule.run_now_command(name),
        cron=schedule.cron_line(python=python, script=str(TARGET),
                                working_directory=str(ROOT)),
    )


def _schtasks(argv: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return 127, ("schtasks was not found: this is not a Windows machine, "
                     "or Task Scheduler is unavailable. Use --cron instead.")
    except subprocess.TimeoutExpired:
        return 124, "schtasks did not respond within 60s"
    return done.returncode, (done.stdout or done.stderr or "").strip()


def show() -> int:
    info = _commands()
    print(f"task name     {info['task_name']}")
    print(f"fires at      {info['at_ist']} IST, weekdays"
          + ("" if info["local_is_ist"]
             else f"  (= {info['at_local']} local on this machine)"))
    print(f"runs          {TARGET.relative_to(ROOT)} --scheduled")
    print()
    print("register:")
    print("  " + subprocess.list2cmdline(info["register"]))
    print("query:")
    print("  " + subprocess.list2cmdline(info["query"]))
    print("delete:")
    print("  " + subprocess.list2cmdline(info["delete"]))
    print()
    print("crontab equivalent:")
    print(info["cron"])
    return 0


def status() -> int:
    info = _commands()
    print(f"task name     {info['task_name']}")
    if not _is_windows():
        print("registration  not checked: this is not Windows. The crontab "
              "line is printed by --cron; `crontab -l` shows what is "
              "installed.")
        return 1
    code, output = _schtasks(info["query"])
    if code != 0:
        print("registration  NOT REGISTERED")
        print(f"              {output.splitlines()[0] if output else ''}")
        print("              register it with --register")
        return 1
    print("registration  REGISTERED")
    for line in output.splitlines():
        key = line.split(":", 1)[0].strip()
        if key in ("TaskName", "Next Run Time", "Status", "Last Run Time",
                   "Last Result", "Schedule Type", "Start Time", "Days",
                   "Task To Run", "Scheduled Task State"):
            print(f"  {line.strip()}")
    print()
    print("Registration is not execution, and execution is not fresh data.")
    print("`python scripts/run_market_jobs.py --status` reports what the last")
    print("run achieved, including whether the corpus actually advanced.")
    return 0


def register(dry_run: bool) -> int:
    info = _commands()
    argv = info["register"]
    print("  " + subprocess.list2cmdline(argv))
    if dry_run:
        print("\n--dry-run: nothing was registered.")
        return 0
    if not _is_windows():
        print("\nThis is not Windows. Install the crontab line from --cron "
              "instead; schtasks does not exist here.")
        return 1
    code, output = _schtasks(argv)
    print(output or "")
    if code != 0:
        print(f"\nregistration FAILED (exit {code}).")
        return 2
    # Registration is only a claim until the task is read back.
    code, _ = _schtasks(info["query"])
    if code != 0:
        print("\nschtasks reported success but the task cannot be queried, "
              "so it is NOT registered.")
        return 2
    print(f"\nRegistered and verified: {info['task_name']}, weekdays at "
          f"{info['at_local']} local.")
    print("It has not run yet. `--run-now` fires it once; "
          "`--status` reports what happened.")
    return 0


def unregister() -> int:
    info = _commands()
    if not _is_windows():
        print("Not Windows: remove the crontab line with `crontab -e`.")
        return 1
    code, output = _schtasks(info["delete"])
    print(output or "")
    return 0 if code == 0 else 2


def run_now() -> int:
    info = _commands()
    if not _is_windows():
        print("Not Windows: run `python scripts/run_market_jobs.py "
              "--scheduled` directly.")
        return 1
    code, output = _schtasks(info["run_now"])
    print(output or "")
    if code != 0:
        return 2
    print("Requested. Task Scheduler starts it asynchronously, so the run is "
          "in progress rather than finished.")
    print("`python scripts/run_market_jobs.py --status` reports the outcome "
          "once it completes; the HEALTH panel shows the same thing.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true",
                        help="is the task registered, and what did it last do")
    action.add_argument("--show", action="store_true",
                        help="print the exact commands without running them")
    action.add_argument("--register", action="store_true",
                        help="create or replace the scheduled task")
    action.add_argument("--unregister", action="store_true")
    action.add_argument("--run-now", dest="run_now", action="store_true",
                        help="fire the registered task once")
    action.add_argument("--cron", action="store_true",
                        help="print the crontab line")
    action.add_argument("--json", action="store_true",
                        help="the commands and schedule as JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --register: print, register nothing")
    args = parser.parse_args(argv)

    if args.cron:
        print(_commands()["cron"], end="")
        return 0
    if args.json:
        print(json.dumps(_commands(), indent=2))
        return 0
    if args.show:
        return show()
    if args.register:
        return register(args.dry_run)
    if args.unregister:
        return unregister()
    if args.run_now:
        return run_now()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
