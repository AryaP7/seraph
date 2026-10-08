#!/usr/bin/env python3
# C6 - diagnosis of the two unexplained Pillar 2 findings in HANDOFF.md section 4.
"""Why F_t does not rise at stress dates, and why FR19 rejects on 100% of dates.

Nothing here changes a model or a requirement. It measures the two behaviours
the handoff recorded as unexplained and reports what they are.

  A. Spectral sweep    - F_t, the count of eigenvalues above lambda_plus, and
                         the leading variance share lambda_1/N on the same dates
                         the validation run used. Separates "the pillar sees no
                         stress" from "F_t is the wrong readout of stress".
  B. Window memory     - the same dates evaluated at a fixed Q ~ 2 but shorter
                         windows (T = 1000/500/250 with N = T/2). FR16 pins
                         T = 1000, so this is a diagnostic of what that window
                         costs in event response, NOT a proposed change to it.
  C. FR19 null         - the bootstrap null's own F distribution against the
                         observed F_t, which is what decides whether the test is
                         mis-calibrated or simply aimed at a null that is false
                         on every date.

Run: python scripts/diagnose_rmt_findings.py [--stride 10]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.pillars.rmt import T_WINDOW  # noqa: E402
from seraph.pillars.rmt.engine import (  # noqa: E402
    RmtEngine,
    _correlation,
    _null_exceedance,
)
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import EPOCH_BREAKS  # noqa: E402


async def load(pool):
    """Dense (dates x symbols) adjusted-close panel, restricted to universe members."""
    snaps = await pool.fetch(
        "SELECT rebalance_date, members FROM universe_snapshots ORDER BY rebalance_date")
    snaps = [(s["rebalance_date"], list(s["members"])) for s in snaps]
    universe = sorted({s for _, m in snaps for s in m})
    rows = await pool.fetch(
        "SELECT symbol, date, adj_close FROM daily_prices "
        "WHERE date >= '2001-01-01' AND adj_close > 0 AND symbol = ANY($1::text[])",
        universe)
    dates = sorted({r["date"] for r in rows})
    di = {d: i for i, d in enumerate(dates)}
    si = {s: j for j, s in enumerate(universe)}
    px = np.full((len(dates), len(universe)), np.nan)
    for r in rows:
        px[di[r["date"]], si[r["symbol"]]] = float(r["adj_close"])
    return dates, di, universe, si, px, snaps


def members_at(snaps, d):
    cur = []
    for rd, m in snaps:
        if rd <= d:
            cur = m
        else:
            break
    return cur


def window_returns(px, di, si, d, members, t_window):
    """(T, N) log-return panel over the t_window days ending at d, full data only."""
    i = di[d]
    if i - t_window < 0:
        return None, []
    block = px[i - t_window: i + 1]
    cols, keep = [], []
    for s in members:
        j = si.get(s)
        if j is None:
            continue
        v = block[:, j]
        if np.isfinite(v).all() and (v > 0).all():
            cols.append(np.diff(np.log(v)))
            keep.append(s)
    if not cols:
        return None, []
    return np.column_stack(cols), keep


def spectrum(returns):
    """Descending eigenvalues of the panel's correlation matrix."""
    c, _ = _correlation(returns)
    return np.linalg.eigvalsh(c)[::-1]


async def main(stride: int) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        print("[diag] loading panel ...", flush=True)
        dates, di, universe, si, px, snaps = await load(pool)
    finally:
        await pool.close()
    print(f"[diag] {len(dates)} trading days, {len(universe)} universe symbols", flush=True)

    run_dates = [d for d in dates[T_WINDOW + 1:] if d >= date(2005, 1, 3)][::stride]
    eng = RmtEngine(bootstrap_reps=0)          # F_t / V_eig / SCA need no bootstrap
    rec = []
    for k, d in enumerate(run_dates):
        R, keep = window_returns(px, di, si, d, members_at(snaps, d), T_WINDOW)
        if R is None or len(keep) < 30:
            continue
        res = eng.step(returns=R, members=tuple(keep), date=d.isoformat(),
                       delta_days=stride)
        if res.status == "error":
            continue
        det, sca_t = res.value
        ev = spectrum(R)
        n = len(keep)
        rec.append({
            "date": d, "n": n, "q": R.shape[0] / n, "f": det.f_t,
            "k_above": int((ev > det.lambda_plus).sum()),
            "lam1": float(ev[0]), "share1": float(ev[0]) / n,
            "share2": float(ev[1]) / n, "lp": det.lambda_plus,
            "v": det.v_eig_t, "sca": sca_t, "trace_err": abs(float(ev.sum()) - n),
        })
        if (k + 1) % 100 == 0:
            print(f"[diag] {k+1}/{len(run_dates)}", flush=True)

    keys = ("n", "q", "f", "k_above", "lam1", "share1", "share2", "lp", "v", "sca",
            "trace_err")
    A = {key: np.array([r[key] for r in rec]) for key in keys}
    dl = [r["date"] for r in rec]
    print(f"\n[diag] {len(rec)} dates evaluated ({dl[0]} to {dl[-1]})")
    print(f"[diag] max |trace(C_t) - N_t| over the sweep = {A['trace_err'].max():.2e}")

    def near(target, tol_days):
        cand = [i for i, x in enumerate(dl) if abs((x - target).days) <= tol_days]
        return min(cand, key=lambda i: abs((dl[i] - target).days)) if cand else None

    # --- A. is stress visible in the spectrum at all? ---------------------
    print("\n" + "=" * 78)
    print("A. F_t VERSUS THE LEADING VARIANCE SHARE AT LABELLED BREAKS")
    print("=" * 78)
    print(f"corpus medians: F_t={np.median(A['f']):.4f}  "
          f"k_above={np.median(A['k_above']):.0f}  "
          f"lambda_1/N={np.median(A['share1']):.4f}  "
          f"lambda_2/N={np.median(A['share2']):.4f}")
    print("'pctile' is the rank of that date's value within the whole sweep.")
    hdr = (f"{'epoch':<16}{'date used':<12}{'N':>5}{'Q':>6}{'F_t':>8}{'F pct':>7}"
           f"{'k>lam+':>8}{'lam1/N':>9}{'lam1 pct':>9}{'V_eig':>10}{'V pct':>7}"
           f"{'SCA_t':>8}")
    print(hdr)
    for eid, (bd, _) in EPOCH_BREAKS.items():
        i = near(date.fromisoformat(bd), stride * 3)
        if i is None:
            print(f"{eid:<16}(no evaluated date within {stride * 3} days)")
            continue
        p_s = float((A["share1"] <= A["share1"][i]).mean())
        p_f = float((A["f"] <= A["f"][i]).mean())
        p_v = float((A["v"] <= A["v"][i]).mean())
        print(f"{eid:<16}{dl[i].isoformat():<12}{int(A['n'][i]):>5}{A['q'][i]:>6.2f}"
              f"{A['f'][i]:>8.4f}{p_f:>7.0%}{int(A['k_above'][i]):>8}"
              f"{A['share1'][i]:>9.4f}{p_s:>9.0%}{A['v'][i]:>+10.5f}{p_v:>7.0%}"
              f"{A['sca'][i]:>8.4f}")

    print("\ncorrelation across the sweep:")
    print(f"  corr(F_t,     lambda_1/N) = {np.corrcoef(A['f'], A['share1'])[0, 1]:+.3f}")
    print(f"  corr(k_above, lambda_1/N) = {np.corrcoef(A['k_above'], A['share1'])[0, 1]:+.3f}")
    print(f"  corr(SCA_t,   lambda_1/N) = {np.corrcoef(A['sca'], A['share1'])[0, 1]:+.3f}")
    print(f"  corr(F_t,     N_t)        = {np.corrcoef(A['f'], A['n'])[0, 1]:+.3f}")

    top = np.argsort(A["share1"])[::-1][:8]
    print("\nhighest lambda_1/N dates in the corpus (where the coupling peak lands):")
    for i in top:
        print(f"   {dl[i]}  lambda_1/N={A['share1'][i]:.4f}  F_t={A['f'][i]:.4f}  "
              f"k_above={int(A['k_above'][i])}  N={int(A['n'][i])}")

    # --- B. what the T=1000 window costs in event response ----------------
    print("\n" + "=" * 78)
    print("B. WINDOW MEMORY AT FIXED Q ~ 2 (diagnostic only; FR16 pins T=1000)")
    print("=" * 78)
    print("Same date and same aspect ratio, shorter memory. N is the first N members")
    print("of the point-in-time universe (FR52 ranks it by liquidity), T = 2N.")
    print(f"{'epoch':<16}{'date':<12}"
          f"{'T=1000 N=500':>16}{'T=500 N=250':>16}{'T=250 N=125':>16}")
    for eid, (bd, _) in EPOCH_BREAKS.items():
        i = near(date.fromisoformat(bd), stride * 3)
        if i is None:
            continue
        d = dl[i]
        mem = members_at(snaps, d)
        cells = []
        for t_w in (1000, 500, 250):
            n_target = t_w // 2
            R, keep = window_returns(px, di, si, d, mem, t_w)
            if R is None or len(keep) < n_target:
                cells.append("n/a")
                continue
            ev = spectrum(R[:, :n_target])
            cells.append(f"{ev[0] / n_target:.4f}")
        print(f"{eid:<16}{d.isoformat():<12}"
              + "".join(f"{c:>16}" for c in cells))

    # --- B2. lag profile: when does the coupling peak actually arrive? -----
    print("\n" + "=" * 78)
    print("B2. lambda_1/N AT AND AFTER EACH LABELLED BREAK")
    print("=" * 78)
    print("C_t at a break date is estimated on the 1000 days BEFORE it, so the break")
    print("itself contributes no observations. Reading across a row shows when the")
    print("episode has actually entered the estimation window.")
    offsets = (0, 6, 12, 18, 24, 30, 36)
    print(f"{'epoch':<16}" + "".join(f"{f'+{m}m':>9}" for m in offsets) + f"{'peak at':>11}")
    for eid, (bd, _) in EPOCH_BREAKS.items():
        bdate = date.fromisoformat(bd)
        cells, vals = [], []
        for m in offsets:
            j = near(bdate + timedelta(days=int(round(m * 30.44))), stride * 3)
            if j is None:
                cells.append("n/a")
                vals.append(None)
            else:
                cells.append(f"{A['share1'][j]:.4f}")
                vals.append((A["share1"][j], m))
        seen = [v for v in vals if v is not None]
        peak = f"+{max(seen, key=lambda t: t[0])[1]}m" if seen else "n/a"
        print(f"{eid:<16}" + "".join(f"{c:>9}" for c in cells) + f"{peak:>11}")

    # --- C. the FR19 null -------------------------------------------------
    print("\n" + "=" * 78)
    print("C. THE FR19 BOOTSTRAP NULL AGAINST THE OBSERVED F_t")
    print("=" * 78)
    reps = 200
    shapes = sorted({(1000, int(x)) for x in np.quantile(A["n"], [0.0, 0.5, 1.0]).round()})
    print(f"null = iid standard normal panel of the same shape, {reps} reps")
    print(f"{'shape (T,N)':<16}{'null F mean':>13}{'null F max':>12}"
          f"{'null k max':>12}{'obs F med':>12}{'obs k med':>11}{'p floor':>10}")
    for (t_w, n_s) in shapes:
        null = _null_exceedance(t_w, n_s, reps, seed=0)
        sel = np.abs(A["n"] - n_s) <= max(2, 0.05 * n_s)
        obs_f = float(np.median(A["f"][sel])) if sel.any() else float("nan")
        obs_k = float(np.median(A["k_above"][sel])) if sel.any() else float("nan")
        print(f"{f'({t_w},{n_s})':<16}{null.mean():>13.5f}{null.max():>12.5f}"
              f"{null.max() * n_s:>12.1f}{obs_f:>12.4f}{obs_k:>11.1f}"
              f"{1.0 / (reps + 1):>10.5f}")
    print(f"\nobserved F_t range across the sweep: "
          f"[{A['f'].min():.4f}, {A['f'].max():.4f}]  "
          f"(k_above {int(A['k_above'].min())}-{int(A['k_above'].max())})")
    biggest = max(_null_exceedance(t, n, reps, seed=0).max() for t, n in shapes)
    print(f"largest F the null ever produced across those shapes: {biggest:.5f}")
    verdict = ("observed F_t exceeds every null draw on every date"
               if A["f"].min() > biggest else "the null and the observed F_t overlap")
    print(f"smallest observed F_t: {A['f'].min():.5f}  ->  {verdict}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=10)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.stride)))
