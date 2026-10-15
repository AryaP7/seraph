#!/usr/bin/env python3
# C7 — observation design D (FR20): does an INFORMATIVE y_t rescue the regime filter?
"""Hamilton stays a 3-state TVTP Markov regime filter. Only its observations change.

### Why this test exists

`scripts/compare_hamilton_features.py` showed three designs and a positive
control:

    design                 ac_RV   ac_AR  ac_BAS |  tranq stress crisis | sep_s
    CONTROL synthetic     0.9650  0.9295  0.9572 |  66.7%   0.0%  33.3% |  5.80
    CURRENT (overlapping) 0.9973  0.9983  0.9965 |   0.0%   0.0% 100.0% |  1.12
    A short/non-overlap   0.7812  0.9919  0.9603 |   0.0%   0.0% 100.0% |  0.99
    C innovations         0.4240  0.0928 -0.1922 |  78.3%  11.1%  10.6% |  0.14

Its stated hypothesis was "a series that cannot move cannot switch". **That
hypothesis does not survive its own control.** The control's autocorrelations
are 0.965/0.930/0.957 — nearly as high as the current features — and it
separates at 5.80 sigma. Design A cut `ac_RV` from 0.997 to 0.781 and failed
*identically* (0/0/100, sep 0.99). So persistence is not the binding constraint.

What distinguishes the control is **separation**: its three regimes have genuinely
different means. The current `y_t` components `AR_t` and `BAS_t` are (i)
unavoidably smooth, because a covariance matrix and a serial covariance each need
a window to exist at all, and (ii) **uninformative about crises** — measured this
session over six epochs, `ar_t` crisis-detection AUC = 0.4453 and `bas_t` =
0.3799, both BELOW chance.

So the hypothesis under test here is: **Hamilton fails because two of its three
observations carry no crisis information, not because its optimiser is broken and
not because its features are too smooth.**

### Design D — informative, daily-defined, causal, complementary

From the nine-candidate study (6 epochs, pre-registered), the three informative
daily quantities with the lowest mutual correlation:

    semivar_20   T1 AUC 0.7832   downside dispersion
    rv_accel     T1 AUC 0.7706   volatility acceleration   (corr w/ semivar 0.43)
    drawdown     T1 AUC 0.7185   price vs trailing peak    (corr 0.48 / 0.04)

All three are computed from trailing windows ending at `t`, so the series is
causal. `D2` swaps `rv_accel` for `jump_int_20` as a robustness variant, not as a
second attempt at a pass.

### Pre-registered expectation, written before running

* If **separation** is the binding constraint, Design D should escape the 0/0/100
  absorbing collapse and reach a separation materially above CURRENT's 1.12 —
  ideally toward the control's 5.80 — with a finite half-life.
* If Design D **also** collapses to 0/0/100, then the NSE daily feature space does
  not contain separable volatility regimes at this frequency in any of the
  combinations tried, the estimator is exonerated by the control, and **Hamilton
  should be formally declared unavailable with evidence** rather than repaired.
  That is a legitimate and reportable outcome, not a failure of this test.

Either way: no threshold is tuned, no regime count changed, no parameter floored.
`HamiltonEngine.fit()` is called unmodified, exactly as the other designs are.

Run: python scripts/test_hamilton_observation_d.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.store.bootstrap import resolve_dsn  # noqa: E402

# reuse the EXACT scoring harness the other designs used, so numbers compare
_spec = importlib.util.spec_from_file_location(
    "chf", _ROOT / "scripts" / "compare_hamilton_features.py")
chf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chf)
diagnose = chf.diagnose


def roll(a, w, fn):
    out = np.full(a.size, np.nan)
    for i in range(a.size):
        seg = a[max(0, i - w + 1):i + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size >= max(3, w // 4):
            out[i] = fn(seg)
    return out


async def load():
    c = await asyncpg.connect(resolve_dsn(), timeout=300)
    obs = await c.fetch("SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    mkt = await c.fetch("""
      WITH r AS (SELECT date, symbol,
                        ln(adj_close / NULLIF(lag(adj_close) OVER (PARTITION BY symbol ORDER BY date),0)) lr
                 FROM daily_prices WHERE universe_member_flag AND adj_close > 0)
      SELECT date, avg(lr) mkt FROM r WHERE lr IS NOT NULL GROUP BY date ORDER BY date""")
    await c.close()
    return obs, mkt


def main() -> int:
    obs, mkt = asyncio.run(load())
    mk = {str(r["date"]): float(r["mkt"]) for r in mkt}
    rows = [r for r in obs if str(r["date"]) in mk]
    dates = [str(r["date"]) for r in rows]
    lr = np.array([mk[d] for d in dates])
    rv = np.array([float(r["rv_t_yz"]) for r in rows])
    oy = np.array([[float(r["rv_t_yz"]), float(r["ar_t"]), float(r["bas_t"])] for r in rows])

    px = np.exp(np.cumsum(lr))
    dd = 1.0 - px / roll(px, 252, np.max)
    semivar = np.sqrt(roll(np.minimum(lr, 0.0) ** 2, 20, np.mean))
    rv_ma20 = roll(rv, 20, np.mean)
    rv_accel = np.where(np.isfinite(rv_ma20) & (rv_ma20 > 0), rv / rv_ma20, np.nan)
    sd60 = roll(lr, 60, lambda s: s.std(ddof=1))
    isj = np.where(np.isfinite(sd60), (lr < -2.0 * sd60).astype(float), np.nan)
    jump20 = roll(isj, 20, np.sum)

    print(f"[build] {len(dates):,} days {dates[0]} .. {dates[-1]}")
    print(f"\n{'design':>22} {'ac_1':>7} {'ac_2':>7} {'ac_3':>7} | "
          f"{'tranq':>6} {'stress':>6} {'crisis':>6} | {'sep_s':>6} | "
          f"{'tau_half':>10} | {'BIC':>10}")
    print("-" * 104)

    # positive control, identical construction to the other run
    rng = np.random.default_rng(0)
    lab = np.concatenate([np.full(500, b) for b in (0, 2, 1, 0, 2, 1)])
    M = np.array([[0.8, 0.35, 0.10], [1.6, 0.55, 0.22], [3.2, 0.80, 0.45]])
    syn = M[lab] + rng.normal(scale=[0.18, 0.05, 0.03], size=(lab.size, 3))
    diagnose("CONTROL synthetic", [f"{i:04d}-01-01" for i in range(lab.size)], syn, "syn")

    diagnose("CURRENT (RV,AR,BAS)", dates, oy)

    D1 = np.column_stack([rv_accel, semivar, dd])
    diagnose("D1 accel+semivar+dd", dates, D1)

    D2 = np.column_stack([semivar, jump20, dd])
    diagnose("D2 semivar+jump+dd", dates, D2)

    # ablations: is any single informative feature doing the work?
    D3 = np.column_stack([rv, semivar, dd])
    diagnose("D3 rv+semivar+dd", dates, D3)

    print("\n  ac_* are the lag-1 autocorrelations of the three columns, in column order.")
    print("  The CONTROL is the exoneration test: it shares the high autocorrelation of")
    print("  CURRENT yet separates at 5.80 sigma, so a collapse below is attributable to")
    print("  the features, not to HamiltonEngine.fit().")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
