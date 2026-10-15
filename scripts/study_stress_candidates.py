#!/usr/bin/env python3
# C10 — candidate stress-signal study (FR32–FR36). Research only; writes nothing.
"""Is the SERAPH architecture missing a volatility/downside signal, and if so which?

**Pre-registered before any result was inspected.**

### Three targets, never conflated

The previous evaluation scored one target and so could not separate detection from
prediction. Three are scored here:

* **T1 contemporaneous detection** — `y=1` on the 30 trading days from each break
  (FR32). Measures "is the engine lit while the crisis is happening".
* **T2 post-onset confirmation** — `y=1` on `[break+1, break+30]`, i.e. the break
  day itself removed. Isolates confirmation from same-day coincidence.
* **T3 ADVANCE WARNING** — `y=1` iff a break begins in `(t, t+15]`, **and every
  day already inside a crisis window is dropped from the sample**. Without that
  exclusion a model "predicts" a crisis from inside one, which is not prediction.
  This is the only target that can support an early-warning claim.

### Candidates, and the mechanism each measures

| candidate | mechanism | blind to |
|---|---|---|
| `rv_level` | realised volatility level (C4 Yang–Zhang, cross-sectional) | direction; slow-building stress at normal vol |
| `rv_accel` | volatility *acceleration* vs its own trailing 20d | sustained high-vol regimes (ratio ≈ 1) |
| `semivar_20` | downside semivariance — only negative returns | upside-vol episodes (correctly) |
| `jump_int_20` | count of trailing-20d returns below −2 causal sd | gradual drift without discrete jumps |
| `drawdown` | depth below the trailing 252d peak | fast crashes from a recent peak (shallow at onset) |
| `dd_accel` | 5-day change in drawdown | slow grinding declines |
| `vol_of_vol` | sd of RV over trailing 20d | stable-but-high volatility |
| `ar_t` | C4 absorption ratio — correlation concentration | idiosyncratic stress |
| `bas_t` | C4 spread proxy — liquidity stress | solvency stress with liquid markets |

### Causality and overfitting controls

Every feature uses trailing windows ending at `t` only. Every score is converted
to a **causal trailing-2-year percentile** before thresholding, and the threshold
is the top decile of that trailing distribution — identical for every candidate,
fitted to nothing. No parameter is selected against any epoch. AUC is reported
because it is threshold-free.

### Sample size, stated first

`rv_t_yz` and the market return series span 2005–2026, giving **6 epochs** —
50% more events than the Hawkes-constrained CSRS span. Six events is still far
too few for a significance claim about lead time, so per-epoch outcomes are
reported individually and no pooled p-value is computed.

Run: python scripts/study_stress_candidates.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import (  # noqa: E402
    CRISIS_WINDOW_DAYS,
    EPOCH_BREAKS,
)
from seraph.validation.harness import auc  # noqa: E402

LEAD_H = 15          # advance-warning horizon, trading days
TRAIL_Y = 2          # causal percentile window
TOP_DECILE = 0.90


# ------------------------------------------------------------------ features --

def roll(a: np.ndarray, w: int, fn) -> np.ndarray:
    """Causal rolling reduction: out[i] uses a[max(0,i-w+1) .. i] inclusive."""
    out = np.full(a.size, np.nan)
    for i in range(a.size):
        lo = max(0, i - w + 1)
        seg = a[lo:i + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size >= max(3, w // 4):
            out[i] = fn(seg)
    return out


def build_features(dates: list[str], lr: np.ndarray, rv: np.ndarray,
                   ar: np.ndarray, bas: np.ndarray) -> dict:
    px = np.exp(np.cumsum(lr))
    peak = roll(px, 252, np.max)
    dd = 1.0 - px / peak

    sd60 = roll(lr, 60, lambda s: s.std(ddof=1))
    thr = -2.0 * sd60
    isjump = np.where(np.isfinite(thr), (lr < thr).astype(float), np.nan)

    neg = np.minimum(lr, 0.0)
    rv_ma20 = roll(rv, 20, np.mean)

    f = {
        "rv_level": rv.copy(),
        "rv_accel": np.where(np.isfinite(rv_ma20) & (rv_ma20 > 0), rv / rv_ma20, np.nan),
        "semivar_20": np.sqrt(roll(neg ** 2, 20, np.mean)),
        "jump_int_20": roll(isjump, 20, np.sum),
        "drawdown": dd,
        "dd_accel": np.r_[np.full(5, np.nan), dd[5:] - dd[:-5]],
        "vol_of_vol": roll(rv, 20, lambda s: s.std(ddof=1)),
        "ar_t": ar.copy(),
        "bas_t": bas.copy(),
    }
    return f


def trailing_pct(dates: list[str], v: np.ndarray, years: int = TRAIL_Y) -> np.ndarray:
    out = np.full(v.size, np.nan)
    d = np.array([np.datetime64(x) for x in dates])
    span = np.timedelta64(365 * years, "D")
    for i in range(v.size):
        if not np.isfinite(v[i]):
            continue
        w = v[(d >= d[i] - span) & (d <= d[i])]
        w = w[np.isfinite(w)]
        if w.size >= 60:
            out[i] = float((w <= v[i]).mean())
    return out


# ------------------------------------------------------------------- targets --

def break_index(dates: list[str], bd: str) -> int | None:
    return next((i for i, d in enumerate(dates) if d >= bd), None)


def targets(dates: list[str]) -> dict:
    n = len(dates)
    bi = {ep: break_index(dates, bd) for ep, (bd, _) in EPOCH_BREAKS.items()}
    bi = {k: v for k, v in bi.items() if v is not None}

    t1 = np.zeros(n, int)
    t2 = np.zeros(n, int)
    in_crisis = np.zeros(n, bool)
    for _, i in bi.items():
        t1[i:i + CRISIS_WINDOW_DAYS] = 1
        t2[i + 1:i + CRISIS_WINDOW_DAYS] = 1
        in_crisis[i:i + CRISIS_WINDOW_DAYS] = True

    t3 = np.zeros(n, int)
    for _, i in bi.items():
        t3[max(0, i - LEAD_H):i] = 1
    keep3 = ~in_crisis                      # never predict from inside a crisis
    return {"T1 detection": (t1, np.ones(n, bool)),
            "T2 post-onset": (t2, np.ones(n, bool)),
            f"T3 advance warning (<={LEAD_H}d)": (t3, keep3)}, bi


# ---------------------------------------------------------------------- main --

async def load():
    c = await asyncpg.connect(resolve_dsn(), timeout=300)
    obs = await c.fetch("SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    mkt = await c.fetch("""
      WITH r AS (SELECT date, symbol,
                        ln(adj_close / NULLIF(lag(adj_close) OVER (PARTITION BY symbol ORDER BY date),0)) lr
                 FROM daily_prices WHERE universe_member_flag AND adj_close > 0)
      SELECT date, avg(lr) mkt FROM r WHERE lr IS NOT NULL GROUP BY date ORDER BY date""")
    rmt = await c.fetch("SELECT date, eigenvalues FROM rmt_output ORDER BY date")
    cs = await c.fetch("SELECT ts, csrs FROM csrs "
                       "WHERE weights_artefact_id LIKE '349a6874%' ORDER BY ts")
    cs3 = await c.fetch("SELECT ts, csrs FROM csrs "
                        "WHERE weights_artefact_id LIKE '36b6f9bb%' ORDER BY ts")
    hwk = await c.fetch("SELECT ts, branching_ratio_n FROM hawkes_output WHERE scope='market' ORDER BY ts")
    await c.close()
    return obs, mkt, rmt, cs, hwk, cs3


def main() -> int:
    obs, mkt, rmt, cs, hwk, cs3 = asyncio.run(load())
    mk = {str(r["date"]): float(r["mkt"]) for r in mkt}
    rows = [r for r in obs if str(r["date"]) in mk]
    dates = [str(r["date"]) for r in rows]
    lr = np.array([mk[d] for d in dates])
    rv = np.array([float(r["rv_t_yz"]) for r in rows])
    ar = np.array([float(r["ar_t"]) for r in rows])
    bas = np.array([float(r["bas_t"]) for r in rows])

    feats = build_features(dates, lr, rv, ar, bas)

    # incumbents, on the same grid
    lam = {str(r["date"]): float(r["eigenvalues"][0]) / len(r["eigenvalues"])
           for r in rmt if r["eigenvalues"]}
    feats["[inc] rmt lam1/N"] = np.array([lam.get(d, np.nan) for d in dates])
    csd = {str(r["ts"].date()): float(r["csrs"]) for r in cs}
    feats["[inc] CSRS 2-pillar"] = np.array([csd.get(d, np.nan) for d in dates])
    cs3d = {str(r["ts"].date()): float(r["csrs"]) for r in cs3}
    feats["[NEW] CSRS 3-pillar"] = np.array([cs3d.get(d, np.nan) for d in dates])
    hv, last = {}, np.nan
    for r in hwk:
        n = float(r["branching_ratio_n"]); hv[str(r["ts"].date())] = n / (1 - n)
    carried = []
    for d in dates:
        if d in hv:
            last = hv[d]
        carried.append(last)
    feats["[inc] hawkes n/(1-n)"] = np.array(carried)

    tg, bi = targets(dates)
    print(f"span      : {dates[0]} .. {dates[-1]}  ({len(dates):,} trading days)")
    print(f"epochs    : {len(bi)} {list(bi)}")
    print(f"targets   : T1 crisis={int(tg['T1 detection'][0].sum())}d  "
          f"T2={int(tg['T2 post-onset'][0].sum())}d  "
          f"T3 lead={int(tg[f'T3 advance warning (<={LEAD_H}d)'][0].sum())}d "
          f"(sample excludes {int((~tg[f'T3 advance warning (<={LEAD_H}d)'][1]).sum())} in-crisis days)")
    print()

    pct = {k: trailing_pct(dates, v) for k, v in feats.items()}

    for tname, (y, keep) in tg.items():
        print("=" * 100)
        print(f"{tname}   (positives={int(y[keep].sum())}, sample={int(keep.sum()):,})")
        print("=" * 100)
        hdr = f"{'candidate':<24}{'AUC':>8}{'alert%':>9}{'precision':>11}{'recall':>9}{'n_finite':>10}"
        print(hdr); print("-" * len(hdr))
        res = []
        for k, v in feats.items():
            ok = keep & np.isfinite(v)
            if ok.sum() < 200 or y[ok].sum() == 0:
                print(f"{k:<24}{'n/a':>8}  (insufficient overlap)")
                continue
            a = auc(v[ok], y[ok])
            p = pct[k]
            fire = keep & np.isfinite(p) & (p >= TOP_DECILE)
            tp = int((fire & (y == 1)).sum()); fp = int((fire & (y == 0)).sum())
            prec = tp / max(tp + fp, 1); rec = tp / max(int(y[keep].sum()), 1)
            res.append((a, k))
            print(f"{k:<24}{a:>8.4f}{100.0*fire[keep].mean():>8.1f}%"
                  f"{prec:>11.4f}{rec:>9.4f}{int(ok.sum()):>10,}")
        res.sort(reverse=True)
        print(f"\n  best: {res[0][1]} (AUC {res[0][0]:.4f})   "
              f"worst: {res[-1][1]} (AUC {res[-1][0]:.4f})")
        print()

    print("=" * 100)
    print("PER-EPOCH ADVANCE WARNING: share of the 15 pre-break days already alerting")
    print("=" * 100)
    keys = [k for k in feats if not k.startswith("[inc]")] + [k for k in feats if k.startswith("[inc]")]
    print(f"  {'candidate':<24}" + "".join(f"{e[:11]:>13}" for e in bi))
    for k in keys:
        p = pct[k]
        cells = []
        for ep, i in bi.items():
            w = p[max(0, i - LEAD_H):i]
            w = w[np.isfinite(w)]
            cells.append(f"{np.mean(w >= TOP_DECILE):>12.0%}" if w.size else f"{'n/a':>12}")
        print(f"  {k:<24}" + "".join(f"{c:>13}" for c in cells))

    print("\n" + "=" * 100)
    print("REDUNDANCY: correlation among the top candidates and the incumbents")
    print("=" * 100)
    sel = [k for k in feats]
    M = np.vstack([pct[k] for k in sel])
    ok = np.all(np.isfinite(M), axis=0)
    C = np.corrcoef(M[:, ok])
    print(f"  (on {int(ok.sum()):,} days where all series are finite)")
    print("  " + "".join(f"{i:>7}" for i in range(len(sel))))
    for i, k in enumerate(sel):
        print(f"  {i:>2} {k:<22}" + "".join(f"{C[i,j]:>7.2f}" for j in range(len(sel))))

    print("\nLIMITATIONS: 6 epochs (one provisional date). No pooled significance claim.")
    print("T1/T2 are partly tautological for volatility candidates - crisis windows ARE")
    print("high-volatility windows. Only T3 can support an early-warning claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
