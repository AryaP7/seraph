#!/usr/bin/env python3
# C5/F02 — native five-minute bar census (FR10-15).
"""Count missing native symbol-bars in the trailing window, by cause.

The acceptance check for the F02 tail recovery. Two causes are reported
separately because they have different correct answers:

* **session tail** -- 15:20/15:25/15:30 absent. These candles DO NOT EXIST
  for a member of NSE's Closing Auction Session (CAS), introduced by SEBI
  circular and effective from 2026-08-03: continuous trading ends at 15:15
  and the close is set by auction. On the 2026-10-24 census this accounted
  for 14,616 of 14,630, over 56 sessions, for exactly the 87 of 95
  configured members that are in the dated CAS list. **Do not re-acquire
  these and do not fill them.** An earlier revision of this file blamed a
  mid-session request window; that was wrong.
* **everything else** -- scattered absences. On the 2026-10-24 census these
  were 3-4 consecutive bars from 09:25 in four liquid names on four
  unrelated dates, each covered by an exchange special pre-open notice, so
  continuous trading started late that day. Also not fillable.

Neither class is a defect to repair. The correct handling for both is the
dated common-session policy in the native config, which declares the session
that actually traded; with it applied, `NativeHistory.coverage` reports zero
missing bars over the same window. This script counts RAW absences against
the observed union grid, which is a different and deliberately cruder
question -- useful for spotting a NEW gap, not for judging readiness.

The per-day grid is the UNION of slots any member reports that day, read from
the data. It is never a hardcoded 09:20-15:30, so a short session (Diwali
Muhurat trades in the evening) is not misread as dozens of missing bars.

Run:
  python scripts/census_native_bars.py
  python scripts/census_native_bars.py --sessions 500 --json
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY = ROOT / "prototype_runs/live.native-hawkes.sqlite"
#: The three slots a mid-session request window truncates.
TAIL = ("15:20", "15:25", "15:30")


def census(history: Path, sessions: int) -> dict:
    if not history.exists():
        raise SystemExit(f"no native history at {history}")
    con = sqlite3.connect(f"file:{history.as_posix()}?mode=ro", uri=True)
    try:
        days = sorted(r[0] for r in con.execute(
            "SELECT DISTINCT substr(end,1,10) d FROM native_closes "
            "ORDER BY d DESC LIMIT ?", (sessions,)))
        if not days:
            raise SystemExit("native history is empty")
        window = set(days)
        members = [r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM native_closes ORDER BY symbol")]
        present: dict[tuple[str, str], set] = collections.defaultdict(set)
        grid: dict[str, set] = collections.defaultdict(set)
        for symbol, day, slot in con.execute(
                "SELECT symbol, substr(end,1,10), substr(end,12,5) "
                "FROM native_closes"):
            if day in window:
                present[(symbol, day)].add(slot)
                grid[day].add(slot)
    finally:
        con.close()

    tail = other = 0
    tail_days: set = set()
    other_detail: dict[str, list] = collections.defaultdict(list)
    for day in days:
        for symbol in members:
            have = present.get((symbol, day))
            if not have:
                continue        # the member did not trade that session at all
            for slot in grid[day] - have:
                if slot in TAIL:
                    tail += 1
                    tail_days.add(day)
                else:
                    other += 1
                    other_detail[f"{day} {symbol}"].append(slot)
    return dict(
        history=str(history), sessions=len(days),
        first_session=days[0], last_session=days[-1], members=len(members),
        interval_slots=sum(len(grid[d]) for d in days),
        missing_total=tail + other,
        missing_session_tail=tail,
        missing_other=other,
        truncated_sessions=sorted(tail_days),
        other_detail={k: sorted(v) for k, v in sorted(other_detail.items())},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--sessions", type=int, default=500)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.sessions < 1:
        parser.error("--sessions must be positive")
    report = census(args.history, args.sessions)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"[census] {report['sessions']} sessions "
          f"{report['first_session']} .. {report['last_session']}, "
          f"{report['members']} members, "
          f"{report['interval_slots']} interval-slots")
    print(f"[census] missing symbol-bars        : {report['missing_total']}")
    print(f"[census]   session tail (CAS: no such candle): "
          f"{report['missing_session_tail']} over "
          f"{len(report['truncated_sessions'])} sessions")
    print(f"[census]   other (late open; do NOT fill)   : "
          f"{report['missing_other']}")
    print("[census] neither class is fillable or re-acquirable; the dated "
          "common-session policy is what resolves them")
    for where, slots in report["other_detail"].items():
        print(f"[census]     {where}: {slots}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
