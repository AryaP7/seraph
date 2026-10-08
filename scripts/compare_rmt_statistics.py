#!/usr/bin/env python3
# C6 - empirical comparison of candidate RMT state statistics.
"""Which spectral statistic should carry Pillar 2's systemic-coupling state?

This selects on measured properties, NOT on which produces the most striking
crisis chart. The candidates are compared on eight criteria, and a statistic
that merely looks dramatic at a crisis date while being N_t-dependent or
redundant is disqualified by criteria E and H regardless of how it plots.

Candidates (all are per-date levels, i.e. state variables):
  1. lam1_share   lambda_1 / N            leading-mode variance share
  2. f_t          k_above / N             FR17 exceedance fraction, as specified
     k_above      count above lambda_+    the same signal without the 1/N
  3. signal_mass  sum(lambda_i > lam_+)/N spectral concentration over ALL
                                          deviating modes, not just the top one
  4. p_value      FR19 parametric bootstrap p-value (read from E7)
  5. sca_t        FR18 aggregate, already required by SPEC

`V_t^eig` is reported alongside but is a velocity, not a state level, so it is
not a candidate for the same slot; FR17 requires it either way.

Criteria:
  A distribution across dates          E sensitivity to N_t  (observational
  B temporal stability                   AND a controlled subsampling test)
  C behaviour around labelled breaks    F sensitivity to rebalance dates
  D non-degeneracy                      G well-definedness as N_t changes
                                        H incremental information

Run: python scripts/compare_rmt_statistics.py [--stride 10]
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

from seraph.pillars.rmt import T_WINDOW, mp_bounds  # noqa: E402
from seraph.pillars.rmt.engine import RmtEngine, _correlation, _null_exceedance  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import EPOCH_BREAKS  # noqa: E402

CANDIDATES = ("lam1_share", "f_t", "k_above", "signal_mass", "p_value", "sca_t")


async def load(pool):
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
    pvals = {r["date"]: float(r["mp_pvalue"]) for r in
             await pool.fetch("SELECT date, mp_pvalue FROM rmt_output")}
    return dates, di, universe, si, px, snaps, pvals


def members_at(snaps, d):
    cur = []
    for rd, m in snaps:
        if rd <= d:
            cur = m
        else:
            break
    return cur


def window_returns(px, di, si, d, members, t_window):
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


def stats_from(returns):
    """Every candidate that is a pure function of one window's spectrum."""
    n = returns.shape[1]
    ev = np.linalg.eigvalsh(_correlation(returns)[0])[::-1]
    _, lam_plus = mp_bounds(returns.shape[0] / n)
    above = ev > lam_plus
    k = int(above.sum())
    return {
        "lam1_share": float(ev[0]) / n,
        "k_above": float(k),
        "f_t": k / n,
        "signal_mass": float(ev[above].sum()) / n,
    }


def describe(name, x):
    x = np.asarray(x, float)
    finite = x[np.isfinite(x)]
    if finite.size == 0:
        return f"{name:<12} (no finite values)"
    q1, q3 = np.percentile(finite, [25, 75])
    cv = finite.std() / abs(finite.mean()) if finite.mean() != 0 else float("nan")
    uniq = len(np.unique(np.round(finite, 12)))
    modal = float(np.bincount(
        np.unique(np.round(finite, 12), return_inverse=True)[1]).max()) / finite.size
    return (f"{name:<12}{finite.mean():>11.5f}{finite.std():>11.5f}{cv:>9.3f}"
            f"{finite.min():>11.5f}{finite.max():>11.5f}{q3 - q1:>10.5f}"
            f"{uniq:>8d}{modal:>9.1%}")


async def main(stride: int) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        print("[cmp] loading panel ...", flush=True)
        dates, di, universe, si, px, snaps, pvals = await load(pool)
    finally:
        await pool.close()
    print(f"[cmp] {len(dates)} trading days, {len(universe)} symbols, "
          f"{len(pvals)} p-values available from E7", flush=True)

    rebal = {rd for rd, _ in snaps}
    run_dates = [d for d in dates[T_WINDOW + 1:] if d >= date(2005, 1, 3)][::stride]
    eng = RmtEngine(bootstrap_reps=0)
    rec = []
    for k, d in enumerate(run_dates):
        R, keep = window_returns(px, di, si, d, members_at(snaps, d), T_WINDOW)
        if R is None or len(keep) < 30:
            continue
        res = eng.step(returns=R, members=tuple(keep), date=d.isoformat(),
                       delta_days=stride, rebalance_adjacent=(d in rebal))
        if res.status == "error":
            continue
        det, sca_t = res.value
        row = stats_from(R)
        row.update({"date": d, "n": float(len(keep)), "sca_t": sca_t,
                    "v_eig": det.v_eig_t, "omega": det.omega_t,
                    "p_value": pvals.get(d, np.nan), "reb": d in rebal})
        rec.append(row)
        if (k + 1) % 150 == 0:
            print(f"[cmp] {k+1}/{len(run_dates)}", flush=True)

    dl = [r["date"] for r in rec]
    A = {c: np.array([r[c] for r in rec], float) for c in CANDIDATES + ("n", "v_eig", "omega")}
    reb_mask = np.array([r["reb"] for r in rec])
    n_pv = int(np.isfinite(A["p_value"]).sum())
    print(f"\n[cmp] {len(rec)} dates ({dl[0]} to {dl[-1]}); "
          f"p-value matched on {n_pv}/{len(rec)} dates")

    # ---------- A + D: distribution and non-degeneracy --------------------
    print("\n" + "=" * 96)
    print("A/D. DISTRIBUTION ACROSS DATES  (CV = sd/|mean|; 'modal' = share at the single "
          "most common value)")
    print("=" * 96)
    print(f"{'candidate':<12}{'mean':>11}{'sd':>11}{'CV':>9}{'min':>11}{'max':>11}"
          f"{'IQR':>10}{'#uniq':>8}{'modal':>9}")
    for c in CANDIDATES:
        print(describe(c, A[c]))
    print(describe("v_eig*", A["v_eig"]))
    print("* velocity, not a state level - shown for completeness only")

    # ---------- B: temporal stability -------------------------------------
    print("\n" + "=" * 96)
    print(f"B. TEMPORAL STABILITY (steps of {stride} trading days)")
    print("=" * 96)
    print(f"{'candidate':<12}{'lag-1 autocorr':>16}{'median |step|':>15}"
          f"{'|step| / IQR':>14}   interpretation")
    for c in CANDIDATES:
        x = A[c]
        if not np.isfinite(x).all() or np.unique(x).size < 2:
            print(f"{c:<12}{'n/a (constant)':>16}")
            continue
        ac = float(np.corrcoef(x[:-1], x[1:])[0, 1])
        step = float(np.median(np.abs(np.diff(x))))
        iqr = float(np.subtract(*np.percentile(x, [75, 25])))
        ratio = step / iqr if iqr else float("nan")
        tag = ("smooth slow state" if ac > 0.95 and ratio < 0.25 else
               "moderately smooth" if ac > 0.8 else "jumpy")
        print(f"{c:<12}{ac:>16.4f}{step:>15.5f}{ratio:>14.3f}   {tag}")

    # ---------- E-observational + F: N_t and rebalance ---------------------
    print("\n" + "=" * 96)
    print("E(obs)/F. ASSOCIATION WITH N_t, AND BEHAVIOUR AT REBALANCES")
    print("=" * 96)
    print(f"{'candidate':<12}{'corr with N_t':>15}{'|step| at rebal':>17}"
          f"{'|step| elsewhere':>18}{'ratio':>8}")
    for c in CANDIDATES:
        x = A[c]
        if np.unique(x[np.isfinite(x)]).size < 2:
            print(f"{c:<12}{'n/a (constant)':>15}")
            continue
        cn = float(np.corrcoef(x, A["n"])[0, 1])
        steps = np.abs(np.diff(x))
        at_reb = reb_mask[1:]
        a = float(np.median(steps[at_reb])) if at_reb.any() else float("nan")
        b = float(np.median(steps[~at_reb]))
        print(f"{c:<12}{cn:>15.3f}{a:>17.5f}{b:>18.5f}{(a / b if b else float('nan')):>8.2f}")

    # ---------- E-experimental: the decisive N_t test ----------------------
    print("\n" + "=" * 96)
    print("E(exp). CONTROLLED SUBSAMPLING - same date, same T=1000, cross-section thinned")
    print("=" * 96)
    print("If a statistic is cross-date comparable it must not drift as N_t changes,")
    print("because N_t itself ranges 122-499 across this corpus for reasons unrelated to risk.")
    rng = np.random.default_rng(0)
    # N_t peaks at 499 (the universe never quite fills 500 with a full 1000-day
    # history), so the top of the grid is 480 rather than 500.
    draws, n_grid = 8, (120, 240, 360, 480)
    # N_t per date is already recorded in the sweep, so reuse it rather than
    # rebuilding every window just to find the dates with a full cross-section.
    eligible = [d for d, n in zip(dl, A["n"]) if n >= max(n_grid)]
    test_dates = eligible[:: max(1, len(eligible) // 12)][:12]
    print(f"test dates: {len(test_dates)} (each with >= 500 eligible members), "
          f"{draws} random subsets per N\n")
    cand_exp = ("lam1_share", "f_t", "k_above", "signal_mass", "p_value")
    acc = {c: {n: [] for n in n_grid} for c in cand_exp}
    per_date = {c: [] for c in cand_exp}          # within-date paired ratios
    for d in test_dates:
        R, keep = window_returns(px, di, si, d, members_at(snaps, d), T_WINDOW)
        local = {c: {n: [] for n in n_grid} for c in cand_exp}
        for n in n_grid:
            for _ in range(draws):
                cols = rng.choice(R.shape[1], size=n, replace=False)
                s = stats_from(R[:, cols])
                for c in ("lam1_share", "f_t", "k_above", "signal_mass"):
                    acc[c][n].append(s[c]); local[c][n].append(s[c])
                null = _null_exceedance(R.shape[0], n, 200, seed=0)
                pv = (float((null >= s["f_t"]).sum()) + 1) / 201.0
                acc["p_value"][n].append(pv); local["p_value"][n].append(pv)
        for c in cand_exp:
            lo, hi = np.mean(local[c][n_grid[0]]), np.mean(local[c][n_grid[-1]])
            per_date[c].append(lo / hi if hi else np.nan)

    print(f"{'candidate':<12}" + "".join(f"{f'N={n}':>17}" for n in n_grid)
          + f"{'drift':>9}")
    for c in cand_exp:
        cells = "".join(f"{np.mean(acc[c][n]):>10.5f}+-{np.std(acc[c][n]):<5.3f}"
                        for n in n_grid)
        m = [float(np.mean(acc[c][n])) for n in n_grid]
        drift = (m[0] - m[-1]) / abs(m[-1]) if m[-1] else float("nan")
        print(f"{c:<12}{cells}{drift:>9.1%}")
    print(f"\n(drift is the pooled change in level from N={n_grid[-1]} down to "
          f"N={n_grid[0]}, as a fraction of\n the N={n_grid[-1]} level. A "
          f"cross-date-comparable state variable should be ~0%.)")

    print(f"\nWithin-date paired ratio  stat(N={n_grid[0]}) / stat(N={n_grid[-1]}) "
          f"- removes all date effects:")
    print(f"{'candidate':<12}{'mean ratio':>12}{'min':>10}{'max':>10}   verdict")
    for c in cand_exp:
        r = np.array(per_date[c], float)
        if c == "p_value":
            verdict = "invariant only because it is constant"
        elif abs(np.mean(r) - 1) < 0.05 and (np.abs(r - 1) < 0.10).all():
            verdict = "N-INVARIANT on every test date"
        elif abs(np.mean(r) - 1) < 0.15:
            verdict = "mildly N-dependent"
        else:
            verdict = "STRONGLY N-dependent - not cross-date comparable"
        print(f"{c:<12}{np.mean(r):>12.4f}{np.min(r):>10.4f}{np.max(r):>10.4f}   {verdict}")
    print("sca_t is excluded here: it is an ECDF rank over a rolling history, so it has no")
    print("single-window definition - its N-sensitivity is inherited from f_t (see above).")

    # ---------- H: incremental information --------------------------------
    print("\n" + "=" * 96)
    print("H. INCREMENTAL INFORMATION - pairwise correlation, and R^2 against the others")
    print("=" * 96)
    usable = [c for c in CANDIDATES if np.isfinite(A[c]).all()
              and np.unique(A[c]).size > 1]
    print(f"{'':<12}" + "".join(f"{c:>13}" for c in usable))
    for a_ in usable:
        cells = "".join(f"{np.corrcoef(A[a_], A[b_])[0, 1]:>13.3f}" for b_ in usable)
        print(f"{a_:<12}{cells}")
    print(f"\n{'candidate':<12}{'R^2 on the other candidates':>30}   verdict")
    for c in usable:
        others = [o for o in usable if o != c]
        X = np.column_stack([A[o] for o in others] + [np.ones(len(rec))])
        beta, *_ = np.linalg.lstsq(X, A[c], rcond=None)
        resid = A[c] - X @ beta
        r2 = 1 - resid.var() / A[c].var()
        tag = ("redundant - fully explained by the others" if r2 > 0.95 else
               "largely redundant" if r2 > 0.8 else "carries independent information")
        print(f"{c:<12}{r2:>30.4f}   {tag}")

    # ---------- C: behaviour around labelled breaks -----------------------
    print("\n" + "=" * 96)
    print("C. BEHAVIOUR AROUND LABELLED BREAKS (documented, NOT a selection criterion)")
    print("=" * 96)
    print("Percentile of each statistic within the corpus, at the break and 24 months on.")

    def near(target, tol):
        cand = [i for i, x in enumerate(dl) if abs((x - target).days) <= tol]
        return min(cand, key=lambda i: abs((dl[i] - target).days)) if cand else None

    for c in ("lam1_share", "f_t", "signal_mass", "sca_t"):
        x = A[c]
        print(f"\n  {c}:")
        for eid, (bd, _) in EPOCH_BREAKS.items():
            b = date.fromisoformat(bd)
            i0, i24 = near(b, stride * 3), near(b + timedelta(days=730), stride * 3)
            f0 = f"{float((x <= x[i0]).mean()):.0%}" if i0 is not None else "n/a"
            f24 = f"{float((x <= x[i24]).mean()):.0%}" if i24 is not None else "n/a"
            print(f"    {eid:<18} at break {f0:>5}   at +24m {f24:>5}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=10)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.stride)))
