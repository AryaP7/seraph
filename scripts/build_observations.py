#!/usr/bin/env python3
# C4 — Feature Deriver: build the daily observation vector y_t over the real corpus.
"""Assembles `y_t = (RV_t, AR_t, BAS_t)` per trading day from daily_prices,
restricted to each day's point-in-time universe (C3), and writes it to
hamilton_output's observation columns so C7 can estimate on real NSE data.

Only the observation columns are written here; the regime fields are C7's and
are filled by scripts/fit_hamilton.py.

Run: python scripts/build_observations.py [--from 2005-01-03] [--stride 1]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.features import (  # noqa: E402
    absorption_ratio,
    bid_ask_spread,
    yang_zhang_volatility,
)
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

YZ_LOOKBACK = 22        # trading days needed by Yang–Zhang (window + 1)
AR_LOOKBACK = 250       # ~1y of returns for the covariance
CAL_DAYS = 420          # calendar days to fetch to cover AR_LOOKBACK trading days


async def universe_for(pool, day: date) -> list[str]:
    members = await pool.fetchval(
        "SELECT members FROM universe_snapshots WHERE rebalance_date <= $1::date "
        "ORDER BY rebalance_date DESC LIMIT 1", day)
    return list(members) if members else []


async def trading_days(pool, start: str) -> list[date]:
    rows = await pool.fetch(
        "SELECT DISTINCT date FROM daily_prices WHERE date >= $1::date ORDER BY date",
        date.fromisoformat(start))
    return [r["date"] for r in rows]


async def build_row(pool, day: date, members: list[str]):
    rows = await pool.fetch(
        """
        SELECT symbol, date, open, high, low, close, adj_close
        FROM daily_prices
        WHERE symbol = ANY($1) AND date <= $2::date
          AND date > $2::date - make_interval(days => $3)
        ORDER BY symbol, date
        """, members, day, CAL_DAYS)
    if not rows:
        return None

    by_sym: dict[str, list] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)

    rv_each, bas_each, ret_cols = [], [], []
    fallbacks: dict[str, int] = {}
    for obs in by_sym.values():
        if len(obs) < YZ_LOOKBACK:
            continue
        o = np.array([x["open"] for x in obs], dtype=float)
        h = np.array([x["high"] for x in obs], dtype=float)
        lo = np.array([x["low"] for x in obs], dtype=float)
        c = np.array([x["close"] for x in obs], dtype=float)
        if (o <= 0).any() or (h <= 0).any() or (lo <= 0).any() or (c <= 0).any():
            continue
        rv = yang_zhang_volatility(o, h, lo, c)
        if np.isfinite(rv):
            rv_each.append(rv)
        bas, which = bid_ask_spread(h, lo, c)
        if np.isfinite(bas):
            bas_each.append(bas)
            fallbacks[which] = fallbacks.get(which, 0) + 1
        adj = np.array([x["adj_close"] for x in obs], dtype=float)
        if len(adj) >= AR_LOOKBACK and (adj > 0).all():
            ret_cols.append(np.diff(np.log(adj[-AR_LOOKBACK:])))

    if not rv_each or not bas_each or len(ret_cols) < 10:
        return None
    ar = absorption_ratio(np.column_stack(ret_cols))
    if not np.isfinite(ar):
        return None
    return (day, float(np.median(rv_each)), float(ar),
            float(np.median(bas_each)), fallbacks)


async def main(start: str, stride: int) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    written = skipped = 0
    fb_total: dict[str, int] = {}
    try:
        days = await trading_days(pool, start)
        days = days[::stride]
        print(f"[obs] {len(days)} trading days from {days[0]} to {days[-1]}", flush=True)
        cached_members: list[str] = []
        cached_key = None
        for i, day in enumerate(days, start=1):
            key = (day.year, 1 if day.month < 7 else 2)
            if key != cached_key:
                cached_members = await universe_for(pool, day)
                cached_key = key
            if not cached_members:
                skipped += 1
                continue
            row = await build_row(pool, day, cached_members)
            if row is None:
                skipped += 1
                continue
            d, rv, ar, bas, fb = row
            for k, v in fb.items():
                fb_total[k] = fb_total.get(k, 0) + v
            await pool.execute(
                """
                INSERT INTO hamilton_output
                    (date, rv_t_yz, rv_t_5min, ar_t, bas_t,
                     xi_1, xi_2, xi_3, lsd_t, p_hat_22, p_hat_33,
                     tau_half_stressed, tau_half_crisis, estimation_uncertainty)
                VALUES ($1,$2,NULL,$3,$4, 1,0,0, 0, 0,0, 0,0, 0)
                ON CONFLICT (date) DO UPDATE SET
                    rv_t_yz = EXCLUDED.rv_t_yz,
                    ar_t    = EXCLUDED.ar_t,
                    bas_t   = EXCLUDED.bas_t
                """, d, rv, ar, bas)
            written += 1
            if i % 250 == 0:
                print(f"[obs] {i}/{len(days)} days — {written} written, "
                      f"{skipped} skipped", flush=True)
    finally:
        await pool.close()
    total_est = sum(fb_total.values()) or 1
    shares = {k: f"{100*v/total_est:.1f}%" for k, v in sorted(fb_total.items())}
    print(f"[obs] done: {written} observation rows, {skipped} skipped "
          f"(insufficient history)", flush=True)
    print(f"[obs] FR6 spread estimator usage: {shares}", flush=True)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", default="2005-01-03")
    p.add_argument("--stride", type=int, default=1,
                   help="take every Nth trading day (5 = weekly, for a fast pass)")
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.start, a.stride)))
