#!/usr/bin/env python3
# C3 — build and persist the point-in-time universe for every rebalance date.
"""Runs FR52 across the corpus, persists each UniverseSnapshot, stamps
universe_member_flag, and prints N_t / Q_t per date so the AMENDMENT-02 table
can be regenerated from data rather than quoted from memory.

Run: python scripts/build_universe.py [--from 2005] [--to 2026] [--no-flags]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seraph.universe import UniverseConstructor, rebalance_dates  # noqa: E402

T_WINDOW = 1000  # FR16 rolling window, in trading days


async def main(from_year: int, to_year: int, apply_flags: bool) -> int:
    uc = await UniverseConstructor.connect()
    dates = rebalance_dates(from_year, to_year)
    underfilled = 0
    try:
        print(f"{'rebalance':<12} {'N_t':>5} {'eligible':>9} {'Q_t':>6} "
              f"{'churn':>7}  flag")
        for i, d in enumerate(dates):
            res = await uc.build(d)
            if res.status == "error":
                print(f"{d:<12} ERROR {res.error}")
                continue
            snap = res.value
            n = len(snap.members)
            if n == 0:
                print(f"{d:<12} {0:>5} {snap.eligible_count:>9}      -       -  no eligible names")
                continue
            q = T_WINDOW / n
            flag = ""
            if any(w.code == "UNIVERSE_UNDERFILLED" for w in res.warnings):
                flag = "UNDERFILLED"
                underfilled += 1
            print(f"{d:<12} {n:>5} {snap.eligible_count:>9} {q:>6.2f} "
                  f"{snap.churn_fraction:>7.3f}  {flag}")

            saved = await uc.persist(snap)
            if saved.status == "error":
                print(f"   persist failed: {saved.error}")
                continue
            if apply_flags:
                until = dates[i + 1] if i + 1 < len(dates) else "2027-01-01"
                await uc.apply_membership_flags(snap, until)
    finally:
        await uc.close()
    print(f"\n{len(dates)} rebalance dates, {underfilled} underfilled "
          f"(N_t < 500 — Q_t > 2, per AMENDMENT-02)")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="from_year", type=int, default=2005)
    p.add_argument("--to", dest="to_year", type=int, default=2026)
    p.add_argument("--no-flags", action="store_true",
                   help="skip the universe_member_flag UPDATE (much faster)")
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.from_year, a.to_year, not a.no_flags)))
