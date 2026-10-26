#!/usr/bin/env python3
# C13 — register the in-session live pass with Windows Task Scheduler (NFR35).
"""Install `live_session_pass.py` as a scheduled in-session task.

**Why this exists.** `scripts/live_session_pass.py` names this script in its
own docstring as the thing that registers it, and this script did not exist.
So the documented scheduling path for the live CSRS pass was a dangling
reference: the only registered SERAPH task ran `run_market_jobs.py` at 18:30,
after the close, and nothing ever took a pass *during* a session.

**What it registers.** One task per declared time, Monday–Friday, running

    .venv/Scripts/python.exe scripts/live_session_pass.py

which itself refuses to proceed on a closed market, so a holiday needs no
special case here — the task fires, the calendar says shut, and the pass
records `market_closed` and exits non-zero. The exchange calendar stays the
single source of truth about whether a session exists.

**Two settings that are not cosmetic.**

* `StartWhenAvailable` — the existing daily task carries
  `DisallowStartIfOnBatteries`, and its last run returned 0x800710E0 (the
  request was refused) because the machine was on battery. A risk engine whose
  scheduled run is silently skipped on battery is not scheduled.
* `WakeToRun` is NOT set. Waking a sleeping machine to trade-adjacent work is
  the owner's call, not this script's, and is printed as a recommendation.

**What this cannot fix.** A Kite access token is invalidated daily at ~06:00
IST and `scripts/kite_login.py` is an interactive browser login. A scheduled
pass therefore authenticates only if someone has logged in since 06:00 that
day. The task is still worth registering — it records the blocker as evidence
rather than leaving no trace — but it is not unattended operation, and this
script says so rather than implying otherwise.

Usage:

    python scripts/register_live_task.py                 # show the plan only
    python scripts/register_live_task.py --install
    python scripts/register_live_task.py --install --at 09:25 --at 15:05
    python scripts/register_live_task.py --remove
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SCRIPT = ROOT / "scripts" / "live_session_pass.py"

#: Base name; one task is registered per declared time, suffixed with it.
TASK_PREFIX = "SERAPH Live Session Pass"

#: Default in-session times, IST. 09:25 is ten minutes after the open, so at
#: least one five-minute bar has closed; 15:05 is inside the continuous
#: session, which ends at 15:15 and is the only grid the native Hawkes fit
#: uses — a pass at 15:20 would read a closing-auction window the model
#: excludes.
DEFAULT_TIMES = ("09:25", "15:05")


def task_name(at: str) -> str:
    # A Task Scheduler task name may not contain ':' -- Register-ScheduledTask
    # rejects it with 0x80070057 ("the parameter is incorrect"), which is not
    # an obvious message for a bad name. 09:25 therefore registers as 0925.
    return f"{TASK_PREFIX} {at.replace(':', '')}"


def powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True)


def register(at: str, *, dry_run: bool) -> int:
    name = task_name(at)
    action = (f'New-ScheduledTaskAction -Execute "{PYTHON}" '
              f'-Argument \'"{SCRIPT}"\' -WorkingDirectory "{ROOT}"')
    trigger = (f'New-ScheduledTaskTrigger -Weekly '
               f'-DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At {at}')
    # -StartWhenAvailable alone does NOT clear the battery restriction:
    # DisallowStartIfOnBatteries defaults to True, and that is precisely why
    # the pre-existing "SERAPH Daily Market Jobs" task returned 0x800710E0
    # (request refused) on 2026-10-24. Both battery switches are required, or
    # a scheduled risk pass silently does not happen on an unplugged laptop.
    settings = ('New-ScheduledTaskSettingsSet -StartWhenAvailable '
                '-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries '
                '-MultipleInstances IgnoreNew '
                '-ExecutionTimeLimit (New-TimeSpan -Minutes 30)')
    script = (f'$a = {action}; $t = {trigger}; $s = {settings}; '
              f'Register-ScheduledTask -TaskName "{name}" -Action $a '
              f'-Trigger $t -Settings $s -Force | '
              f'Select-Object TaskName, State | Format-List')
    if dry_run:
        print(f"[plan] would register {name!r}")
        print(f"[plan]   execute  {PYTHON}")
        print(f"[plan]   argument {SCRIPT}")
        print(f"[plan]   trigger  Mon-Fri {at} (IST, machine local time)")
        print(f"[plan]   settings StartWhenAvailable, IgnoreNew, 30m limit")
        return 0
    result = powershell(script)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        print(f"[task] FAILED to register {name!r}")
    else:
        print(f"[task] registered {name!r}")
    return result.returncode


def remove(at: str, *, dry_run: bool) -> int:
    name = task_name(at)
    if dry_run:
        print(f"[plan] would unregister {name!r}")
        return 0
    result = powershell(
        f'Unregister-ScheduledTask -TaskName "{name}" -Confirm:$false')
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        print(f"[task] {name!r} was not registered")
    else:
        print(f"[task] removed {name!r}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", action="append", metavar="HH:MM",
                        help=f"in-session time; repeatable "
                             f"(default {' '.join(DEFAULT_TIMES)})")
    parser.add_argument("--install", action="store_true",
                        help="actually register (default is to print the plan)")
    parser.add_argument("--remove", action="store_true",
                        help="unregister the tasks instead")
    args = parser.parse_args(argv)

    times = tuple(args.at) if args.at else DEFAULT_TIMES
    for at in times:
        hour, _, minute = at.partition(":")
        if not (hour.isdigit() and minute.isdigit()
                and 0 <= int(hour) < 24 and 0 <= int(minute) < 60):
            print(f"[task] {at!r} is not HH:MM")
            return 2

    if not PYTHON.exists():
        print(f"[task] no interpreter at {PYTHON}")
        return 2
    if not SCRIPT.exists():
        print(f"[task] no pass script at {SCRIPT}")
        return 2

    dry_run = not (args.install or args.remove)
    worst = 0
    for at in times:
        code = (remove(at, dry_run=dry_run) if args.remove
                else register(at, dry_run=dry_run))
        worst = max(worst, code)

    if dry_run:
        print("\n[task] nothing was changed. Re-run with --install to apply.")
    if not args.remove:
        print("\n[task] A Kite access token is invalidated daily at ~06:00 IST "
              "and `scripts/kite_login.py` is an interactive login, so a "
              "scheduled pass authenticates only if someone has logged in "
              "since 06:00 that day. Expect `broker` blockers otherwise; they "
              "are recorded, not worked around.")
        print("[task] `WakeToRun` is deliberately NOT set. If this machine "
              "sleeps through the session, add it yourself:")
        print('[task]   Set-ScheduledTask -TaskName "<name>" -Settings '
              '(New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun)')
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
