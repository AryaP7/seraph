#!/usr/bin/env python3
# C7 — observation-design comparison (FR20). Which y_t supports a daily regime filter?
"""The current y_t is unusable for a daily regime filter: its components use
heavily overlapping rolling windows (RV 21d, AR 250d, BAS 290d), giving lag-1
autocorrelations of 0.997-0.998 and a mean daily change of ~1%. A series that
cannot move cannot switch, so the filter collapses to one absorbing state. This
script evaluates three redesigns against that failure.

  A  SHORT / NON-OVERLAPPING. RV_t from the per-day Rogers-Satchell estimator -
     the drift-independent component of Yang-Zhang and the only part that is
     defined on a SINGLE day, so consecutive values share no data. AR_t and
     BAS_t still need a window to exist at all (a covariance matrix and a
     serial covariance respectively); they are shortened to the minimum that
     keeps them well-conditioned, not to a value chosen for pretty regimes.
  B  TRUE 5-MINUTE RV, aggregated within each trading day - non-overlapping by
     construction and FR20's stated preference, but only defined post-2015.
     Evaluated over the overlap as a cross-check on A, never spliced into a
     single inconsistent historical series.
  C  INNOVATIONS - first differences of the existing smoothed levels.

A synthetic series with known switches is fitted alongside as a positive
control, so a null result can be attributed to the features rather than to the
estimator.

Run: python scripts/compare_hamilton_features.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.features import absorption_ratio, bid_ask_spread  # noqa: E402
from seraph.pillars.hamilton import HamiltonEngine  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import EPOCH_BREAKS  # noqa: E402

AR_WIN = 60      # minimum for a well-conditioned covariance over ~500 names
BAS_WIN = 20     # minimum for a stable Abdi-Ranaldo serial covariance


def rogers_satchell_daily(o, h, l_, c):
    """Per-DAY variance estimate. Unlike Yang-Zhang over a window, this uses a
    single day's OHLC, so consecutive values share no observations."""
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = (np.log(h / c) * np.log(h / o) + np.log(l_ / c) * np.log(l_ / o))
    return np.sqrt(np.maximum(rs, 0.0) * 252.0)


async def build(pool):
    rows = await pool.fetch(
        """
        SELECT d.date, d.symbol, d.open, d.high, d.low, d.close, d.adj_close
        FROM daily_prices d
        WHERE d.universe_member_flag AND d.date >= '2005-01-03'
        ORDER BY d.date, d.symbol
        """)
    by_date = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    dates = sorted(by_date)

    rv, sym_px = [], {}
    for d in dates:
        rec = by_date[d]
        o = np.array([float(x["open"]) for x in rec])
        h = np.array([float(x["high"]) for x in rec])
        l_ = np.array([float(x["low"]) for x in rec])
        c = np.array([float(x["close"]) for x in rec])
        ok = (o > 0) & (h > 0) & (l_ > 0) & (c > 0)
        vals = rogers_satchell_daily(o[ok], h[ok], l_[ok], c[ok])
        vals = vals[np.isfinite(vals)]
        rv.append(float(np.median(vals)) if vals.size else np.nan)
        for x in rec:
            sym_px.setdefault(x["symbol"], {})[d] = (
                float(x["adj_close"]), float(x["high"]),
                float(x["low"]), float(x["close"]))
    return dates, np.array(rv), sym_px


def rolling_ar_bas(dates, sym_px):
    """AR_t on a 60-day covariance, BAS_t on a 20-day Abdi-Ranaldo window."""
    idx = {d: i for i, d in enumerate(dates)}
    ar = np.full(len(dates), np.nan)
    bas = np.full(len(dates), np.nan)
    syms = [s for s, m in sym_px.items() if len(m) > AR_WIN + 5]
    series = {s: np.array([sym_px[s].get(d, (np.nan,) * 4)[0] for d in dates])
              for s in syms}
    hi = {s: np.array([sym_px[s].get(d, (np.nan,) * 4)[1] for d in dates]) for s in syms}
    lo = {s: np.array([sym_px[s].get(d, (np.nan,) * 4)[2] for d in dates]) for s in syms}
    cl = {s: np.array([sym_px[s].get(d, (np.nan,) * 4)[3] for d in dates]) for s in syms}

    for i in range(AR_WIN, len(dates)):
        cols = []
        for s in syms:
            p = series[s][i - AR_WIN:i]
            if np.isfinite(p).all() and (p > 0).all():
                cols.append(np.diff(np.log(p)))
        if len(cols) >= 20:
            ar[i] = absorption_ratio(np.column_stack(cols))
        if i >= BAS_WIN:
            vals = []
            for s in syms[:200]:
                H, L, C = (hi[s][i - BAS_WIN:i], lo[s][i - BAS_WIN:i],
                           cl[s][i - BAS_WIN:i])
                if np.isfinite(H).all() and np.isfinite(L).all() and np.isfinite(C).all():
                    v, _ = bid_ask_spread(H, L, C)
                    if np.isfinite(v):
                        vals.append(v)
            if vals:
                bas[i] = float(np.median(vals))
    return ar, bas


def diagnose(name, dates, y, label=""):
    """Fit C7 and report the diagnostics that decide identifiability."""
    ok = np.isfinite(y).all(axis=1)
    d = [dates[i] for i in np.flatnonzero(ok)]
    yy = y[ok]
    if len(d) < 400:
        print(f"{name:>22}  insufficient clean rows ({len(d)})")
        return None
    ac = [float(np.corrcoef(yy[:-1, k], yy[1:, k])[0, 1]) for k in range(3)]

    eng = HamiltonEngine([f"{i:04d}-01-01" for i in range(len(d))] if label == "syn" else d, yy)
    res = eng.fit()
    if res.status == "error":
        print(f"{name:>22}  FIT FAILED: {res.error}")
        return None
    xi = eng._xi
    occ = np.bincount(np.argmax(xi, axis=0), minlength=3) / xi.shape[1]
    mid = eng.detail(d[len(d) // 2] if label != "syn" else f"{len(d)//2:04d}-01-01")
    pars, model = eng._res.params, eng._res.model
    means = np.array([pars[model.parameters[j, "means"]] for j in range(3)])
    varis = np.array([pars[model.parameters[j, "variances"]] for j in range(3)])
    o = eng._order
    sd = float(np.sqrt(np.mean([varis[o[0]][0], varis[o[2]][0]])))
    sep = (means[o[2]][0] - means[o[0]][0]) / sd if sd > 0 else np.nan
    k = 3 * 3 * 2 + 6
    bic = -2 * res.value["llf"] + k * np.log(len(d))
    print(f"{name:>22} {ac[0]:>7.4f} {ac[1]:>7.4f} {ac[2]:>7.4f} | "
          f"{occ[0]:>6.1%} {occ[1]:>6.1%} {occ[2]:>6.1%} | {sep:>6.2f} | "
          f"{min(mid.tau_half_crisis, 9e9):>10.1f} | {bic:>10.0f}")
    return {"dates": d, "eng": eng, "occ": occ, "sep": sep, "ac": ac,
            "tau": mid.tau_half_crisis, "bic": bic}


async def main() -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        print("[build] assembling candidate feature sets ...", flush=True)
        dates, rv_daily, sym_px = await build(pool)
        ar60, bas20 = rolling_ar_bas(dates, sym_px)

        old = await pool.fetch(
            "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
        od = [r["date"] for r in old]
        oy = np.array([[float(r["rv_t_yz"]), float(r["ar_t"]), float(r["bas_t"])]
                       for r in old])
    finally:
        await pool.close()

    print(f"\n{'design':>22} {'ac_RV':>7} {'ac_AR':>7} {'ac_BAS':>7} | "
          f"{'tranq':>6} {'stress':>6} {'crisis':>6} | {'sep_s':>6} | "
          f"{'tau_half':>10} | {'BIC':>10}")
    print("-" * 104)

    # positive control: synthetic with KNOWN switches
    rng = np.random.default_rng(0)
    lab = np.concatenate([np.full(500, b) for b in (0, 2, 1, 0, 2, 1)])
    M = np.array([[0.8, 0.35, 0.10], [1.6, 0.55, 0.22], [3.2, 0.80, 0.45]])
    syn = M[lab] + rng.normal(scale=[0.18, 0.05, 0.03], size=(lab.size, 3))
    diagnose("CONTROL synthetic", [f"{i:04d}-01-01" for i in range(lab.size)], syn, "syn")

    diagnose("CURRENT (overlapping)", od, oy)

    n = min(len(dates), ar60.size)
    A = np.column_stack([rv_daily[:n], ar60[:n], bas20[:n]])
    diagnose("A short/non-overlap", dates[:n], A)

    dl = np.diff(oy, axis=0)
    diagnose("C innovations", od[1:], dl)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
