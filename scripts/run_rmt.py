#!/usr/bin/env python3
# C6 — RMT corpus run and Pillar 2 validation (FR16-FR19, D3, AMENDMENT-02).
"""Runs the spectral monitor across the corpus and validates the result as
rigorously as Pillars 1 and 3 were validated.

Checks performed, not merely executed:
  FR16  C_t over a rolling T-day window; trace(C_t) == N_t exactly (a
        correlation matrix has unit diagonal) - the arithmetic guard.
  FR17  F_t, V_t^eig, Omega_t emitted; eigenvalues real and non-negative.
  FR18  SCA_t aggregate is non-degenerate across the corpus.
  FR19  bootstrap p-value accompanies every F_t.
  D3    Omega_t computed on common support; no spike at rebalance dates.
  AM-02 Q_t = T/N_t and lambda_pm recomputed per date as N_t varies.
Cross-period behaviour is inspected at known stress dates, but nothing is
tuned to them.

Run: python scripts/run_rmt.py [--stride 5] [--write]
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

from seraph.pillars.rmt import BOOTSTRAP_REPS, T_WINDOW, mp_bounds  # noqa: E402
from seraph.pillars.rmt.engine import RmtEngine, _correlation  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

STRESS_DATES = {"2008-10-24": "GFC peak", "2020-03-23": "COVID bottom",
                "2013-08-28": "taper trough", "2018-10-26": "IL&FS trough"}


async def load(pool):
    """Price panel and trading-day grid, restricted to universe members.

    The grid must be built from equities only. `daily_prices` still physically
    contains ETF rows (see the C3 ISIN filter note), and two sessions in the
    corpus - **2010-05-16 and 2012-11-11** - are gold-ETF-only: not one equity
    traded on either. Deriving the trading-day grid from every symbol therefore
    admits two phantom equity sessions, and because FR16 requires a finite price
    on all 1001 days of the window, each phantom date invalidates every window
    containing it. That alone was costing **163 of 537 evaluation dates**, which
    is why the earlier run covered only 374.

    Restricting the fetch to universe members fixes the grid at the source - the
    universe is ETF-free by construction under FR52 - and incidentally cuts the
    load from 3,524 symbols to roughly 1,100.
    """
    snaps = await pool.fetch(
        "SELECT rebalance_date, members FROM universe_snapshots ORDER BY rebalance_date")
    snaps = [(s["rebalance_date"], list(s["members"])) for s in snaps]
    universe = sorted({s for _, m in snaps for s in m})
    rows = await pool.fetch(
        "SELECT symbol, date, adj_close FROM daily_prices "
        "WHERE date >= '2001-01-01' AND adj_close > 0 AND symbol = ANY($1::text[]) "
        "ORDER BY date", universe)
    px, dates = {}, []
    seen = set()
    for r in rows:
        d = r["date"]
        if d not in seen:
            seen.add(d); dates.append(d)
        px.setdefault(r["symbol"], {})[d] = float(r["adj_close"])
    return dates, px, snaps


def members_at(snaps, d):
    cur = None
    for rd, m in snaps:
        if rd <= d:
            cur = m
        else:
            break
    return cur or []


async def main(stride: int, write: bool, reps: int) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        print("[rmt] loading panel ...", flush=True)
        dates, px, snaps = await load(pool)
        idx = {d: i for i, d in enumerate(dates)}
        rebal = {rd for rd, _ in snaps}
        start = T_WINDOW + 1
        run_dates = [d for d in dates[start:] if d >= date(2005, 1, 3)][::stride]
        print(f"[rmt] {len(dates)} trading days available, "
              f"{len(run_dates)} evaluation dates (stride={stride})", flush=True)

        # FR19 specifies 1,000 replications; the exploratory stride>1 sweeps used
        # 200 to keep turnaround short. The production daily run must use the
        # requirement's value, which is this script's default.
        print(f"[rmt] FR19 bootstrap replications = {reps}", flush=True)
        eng = RmtEngine(bootstrap_reps=reps)
        rows, skipped = [], 0
        prev_members = None
        for k, d in enumerate(run_dates):
            mem = members_at(snaps, d)
            i = idx[d]
            win = dates[i - T_WINDOW: i + 1]
            cols, keep = [], []
            for s in mem:
                series = px.get(s, {})
                v = np.array([series.get(w, np.nan) for w in win])
                if np.isfinite(v).all() and (v > 0).all():
                    cols.append(np.diff(np.log(v))); keep.append(s)
            if len(keep) < 30:
                skipped += 1; continue
            R = np.column_stack(cols)
            adj = prev_members is not None and set(keep) != set(prev_members)
            res = eng.step(returns=R, members=tuple(keep), date=d.isoformat(),
                           delta_days=stride, rebalance_adjacent=(d in rebal))
            if res.status == "error":
                skipped += 1; continue
            det, sca = res.value
            C, _ = _correlation(R)
            ev = np.linalg.eigvalsh(C)
            rows.append({
                "date": d, "n": len(keep), "T": R.shape[0], "f": det.f_t,
                "v": det.v_eig_t, "om": det.omega_t, "p": det.mp_p_value,
                "lm": det.lambda_minus, "lp": det.lambda_plus, "sca": sca,
                "trace": float(ev.sum()), "minev": float(ev.min()),
                "csf": det.common_support_fraction, "reb": d in rebal,
                # AMENDMENT-04 §6/§7: lambda_1/N is Pillar 2's cross-date coupling
                # state, but there is no scalar column for it and RmtDetail is in
                # ask-gated shared_types. The `eigenvalues` column already exists
                # (NOT NULL) and was being written as an empty array, so persist the
                # real spectrum - DESCENDING, lambda_1 first - and lambda_1/N is then
                # exactly derivable as eigenvalues[1] / array_length(eigenvalues, 1).
                "ev": [float(x) for x in ev[::-1]],
                "v1": [float(x) for x in det.leading_eigenvector],
                "lam1_share": float(ev[-1]) / len(keep),
            })
            prev_members = keep
            if (k + 1) % 200 == 0:
                print(f"[rmt] {k+1}/{len(run_dates)}", flush=True)
    finally:
        await pool.close()

    if not rows:
        print("[rmt] no evaluable dates"); return 1
    A = {k: np.array([r[k] for r in rows]) for k in
         ("n", "T", "f", "v", "om", "p", "lm", "lp", "sca", "trace", "minev", "csf",
          "lam1_share")}
    n_ok = len(rows)
    print(f"\n[coverage] {n_ok} dates evaluated, {skipped} skipped "
          f"({rows[0]['date']} to {rows[-1]['date']})")

    # --- FR16 arithmetic guard: trace(C) == N exactly --------------------
    terr = np.abs(A["trace"] - A["n"]).max()
    print(f"[FR16] max |trace(C_t) - N_t| = {terr:.2e} -> "
          f"{'PASS' if terr < 1e-6 else 'FAIL'}")
    print(f"[FR16] min eigenvalue across corpus = {A['minev'].min():.2e} -> "
          f"{'PASS (PSD)' if A['minev'].min() > -1e-8 else 'FAIL'}")

    # --- AMENDMENT-02: Q and lambda_pm move with N -----------------------
    q = A["T"] / A["n"]
    lm_exp = np.array([mp_bounds(x)[0] for x in q])
    lp_exp = np.array([mp_bounds(x)[1] for x in q])
    berr = max(np.abs(A["lm"] - lm_exp).max(), np.abs(A["lp"] - lp_exp).max())
    print(f"[AM-02] N_t range {A['n'].min()}-{A['n'].max()}, "
          f"Q_t range {q.min():.2f}-{q.max():.2f}")
    print(f"[AM-02] max |lambda_pm - MP(Q_t)| = {berr:.2e} -> "
          f"{'PASS (recomputed per date)' if berr < 1e-9 else 'FAIL'}")

    # --- FR17/FR18: non-degenerate signal --------------------------------
    print(f"[FR17] F_t  mean={A['f'].mean():.4f} sd={A['f'].std():.4f} "
          f"range=[{A['f'].min():.4f}, {A['f'].max():.4f}]")
    print(f"[FR17] Omega_t mean={A['om'].mean():.4f} sd={A['om'].std():.4f}")
    print(f"[FR18] SCA_t mean={A['sca'].mean():.4f} sd={A['sca'].std():.4f} -> "
          f"{'PASS (non-degenerate)' if A['sca'].std() > 1e-3 else 'FAIL (constant)'}")
    # AMENDMENT-04 §6 — the recommended cross-date coupling state, surfaced here so
    # the validation run reports it alongside the FR17 signals it is derived from.
    print(f"[A04] lambda_1/N mean={A['lam1_share'].mean():.4f} "
          f"sd={A['lam1_share'].std():.4f} "
          f"range=[{A['lam1_share'].min():.4f}, {A['lam1_share'].max():.4f}] -> "
          f"{'PASS (non-degenerate)' if A['lam1_share'].std() > 1e-3 else 'FAIL'}")
    print(f"[FR19] p-values in [0,1]: "
          f"{'PASS' if (A['p'] >= 0).all() and (A['p'] <= 1).all() else 'FAIL'}; "
          f"share significant at 5% = {(A['p'] < 0.05).mean():.1%}")

    # --- D3: no Omega spike at rebalances --------------------------------
    reb = np.array([r["reb"] for r in rows])
    if reb.any():
        print(f"[D3] Omega_t at rebalance dates mean={A['om'][reb].mean():.4f} vs "
              f"{A['om'][~reb].mean():.4f} elsewhere -> "
              f"{'PASS' if A['om'][reb].mean() <= A['om'][~reb].mean()*3+0.02 else 'FAIL (spike)'}")
    print(f"[D3] common-support fraction min={A['csf'].min():.3f} "
          f"mean={A['csf'].mean():.3f}")

    # --- cross-period behaviour (inspected, not tuned) -------------------
    print(f"\n[cross-period] F_t at known stress dates vs corpus median "
          f"({np.median(A['f']):.4f})")
    dl = [r["date"].isoformat() for r in rows]
    for sd_, lbl in STRESS_DATES.items():
        near = [i for i, x in enumerate(dl) if abs((date.fromisoformat(x)
                - date.fromisoformat(sd_)).days) <= stride * 2]
        if near:
            i = near[0]
            print(f"   {sd_} {lbl:<15} F_t={A['f'][i]:.4f} SCA={A['sca'][i]:.4f} "
                  f"N={int(A['n'][i])} Q={q[i]:.2f} p={A['p'][i]:.4f}")

    if write:
        pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
        try:
            for r in rows:
                await pool.execute(
                    """
                    INSERT INTO rmt_output (date, eigenvalues, v1, f_t, v_eig_t,
                        omega_t, sca_t, mp_pvalue, lambda_minus, lambda_plus,
                        common_support_fraction, rebalance_adjacent)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                    ON CONFLICT (date) DO UPDATE SET
                        eigenvalues=EXCLUDED.eigenvalues, v1=EXCLUDED.v1,
                        f_t=EXCLUDED.f_t, v_eig_t=EXCLUDED.v_eig_t,
                        omega_t=EXCLUDED.omega_t, sca_t=EXCLUDED.sca_t,
                        mp_pvalue=EXCLUDED.mp_pvalue,
                        lambda_minus=EXCLUDED.lambda_minus,
                        lambda_plus=EXCLUDED.lambda_plus,
                        common_support_fraction=EXCLUDED.common_support_fraction,
                        rebalance_adjacent=EXCLUDED.rebalance_adjacent
                    """, r["date"], r["ev"], r["v1"], r["f"], r["v"], r["om"], r["sca"],
                    r["p"], r["lm"], r["lp"], r["csf"], r["reb"])
            print(f"\n[rmt] wrote {len(rows)} rows to E7")
        finally:
            await pool.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=5,
                    help="1 = the FR16 daily production series; >1 samples for validation")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--reps", type=int, default=BOOTSTRAP_REPS,
                    help=f"FR19 bootstrap replications (default {BOOTSTRAP_REPS})")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.stride, a.write, a.reps)))
