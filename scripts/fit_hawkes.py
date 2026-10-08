#!/usr/bin/env python3
# C5 — fit the pooled Hawkes kernel on the real NSE jump stream (AMENDMENT-03).
"""Extracts negative jump events across the equity-only Hawkes universe, pools
them market-wide, and fits the state-conditional kernel on a rolling window.

Symbol selection goes through `build_symbol_list` — **never** by scanning
`intraday_bars`, which still physically holds ETF rows from before the equity
filter landed. An index ETF's "jumps" are index-level moves, so pooling them
would double-count market-wide shocks as independent events.

Run: python scripts/fit_hawkes.py [--window 60] [--states 9]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.features import extract_jumps, state_variable, tick_test  # noqa: E402
from seraph.features.cross_sectional import abdi_ranaldo_spread  # noqa: E402
from seraph.ingestion.hawkes_universe import build_symbol_list, sector_of  # noqa: E402
from seraph.pillars.hawkes import fit_pooled, mts  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

SPREAD_WIN, IMB_WIN, BARS_DAY = 75, 20, 75


async def load(pool, symbols):
    events, per_sector, counts = [], {}, {"neg": 0, "pos": 0, "bars": 0}
    for sym in symbols:
        rows = await pool.fetch(
            "SELECT ts, high, low, close, volume FROM intraday_bars "
            "WHERE symbol=$1 ORDER BY ts", sym)
        if len(rows) < SPREAD_WIN * 2:
            continue
        h = np.array([float(r["high"]) for r in rows])
        lo = np.array([float(r["low"]) for r in rows])
        c = np.array([float(r["close"]) for r in rows])
        v = np.array([float(r["volume"]) for r in rows])
        ts = [r["ts"] for r in rows]
        counts["bars"] += len(rows)

        out = extract_jumps(c)
        counts["neg"] += int((out["jump_sign"] == -1).sum())
        counts["pos"] += int((out["jump_sign"] == 1).sum())

        spread = np.full(c.size, np.nan)
        for i in range(SPREAD_WIN, c.size, 5):
            spread[i:i + 5] = abdi_ranaldo_spread(
                h[i - SPREAD_WIN:i], lo[i - SPREAD_WIN:i], c[i - SPREAD_WIN:i])
        signed = tick_test(c, v)
        imb = np.convolve(signed, np.ones(IMB_WIN), mode="same") / IMB_WIN
        st = state_variable(spread, imb, n_quantiles=3)["s_t"]

        sec = sector_of(sym) or "market_residual"
        for i in np.flatnonzero(out["jump_sign"] == -1):
            events.append((ts[i], int(st[i])))
            per_sector[sec] = per_sector.get(sec, 0) + 1
    return events, per_sector, counts


async def main(window_days: int, n_states: int) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        members = await pool.fetchval(
            "SELECT members FROM universe_snapshots ORDER BY rebalance_date DESC LIMIT 1")
        symbols = build_symbol_list(list(members))     # equity-only, by contract
        print(f"[hawkes] universe: {len(symbols)} equity symbols", flush=True)
        events, per_sector, counts = await load(pool, symbols)
    finally:
        await pool.close()

    if not events:
        print("[hawkes] no negative jump events found"); return 1
    events.sort()
    t0 = events[0][0]
    days = np.array([(t - t0).total_seconds() / 86400.0 for t, _ in events])
    states = np.array([s for _, s in events], dtype=int)
    span = days[-1] if days.size else 0.0
    sym_days = counts["bars"] / BARS_DAY

    print(f"[hawkes] bars={counts['bars']:,}  symbol-days={sym_days:,.0f}")
    print(f"[hawkes] negative jumps={counts['neg']:,}  positive={counts['pos']:,}  "
          f"asymmetry={counts['neg']/max(counts['pos'],1):.2f}")
    print(f"[hawkes] density={counts['neg']/max(sym_days,1):.4f} per symbol-day  |  "
          f"pooled={counts['neg']/max(span,1):.2f} per calendar day")
    print(f"[hawkes] per-sector events: {dict(sorted(per_sector.items(), key=lambda kv:-kv[1]))}")

    # Fit on the most recent window (AMENDMENT-03: rolling 60 trading days).
    cutoff = span - window_days * (7 / 5)          # trading days -> calendar
    sel = days >= cutoff
    print(f"\n[hawkes] fitting pooled kernel on the last {window_days} trading days: "
          f"{int(sel.sum())} events across {n_states} states")
    res = fit_pooled(event_times=days[sel] - days[sel].min(),
                     event_states=states[sel],
                     horizon_days=float(days[sel].max() - days[sel].min()),
                     n_states=n_states)
    if res.status == "error":
        print(f"[hawkes] fit failed: {res.error}"); return 1
    for w in res.warnings:
        print(f"[hawkes] warning: {w.code} — {w.message}")

    asym = counts["neg"] / max(counts["pos"], 1)
    print(f"\n{'state':>6} {'events':>7} {'n (branching)':>14} {'beta':>9} "
          f"{'MTS_t':>9} {'converged':>10}")
    for s, k in sorted(res.value["kernels"].items()):
        print(f"{s:>6} {k.n_events:>7} {k.branching_ratio:>14.4f} {k.beta:>9.3f} "
              f"{mts(k.branching_ratio, asym):>9.4f} {str(k.converged):>10}")
    pooled = res.value.get("pooled")
    if pooled:
        print(f"\n[hawkes] all-state pooled: n={pooled.branching_ratio:.4f} "
              f"(events={pooled.n_events}, FR11 n<1 holds: "
              f"{pooled.branching_ratio < 1.0})")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--window", type=int, default=60)
    p.add_argument("--states", type=int, default=9)
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.window, a.states)))
