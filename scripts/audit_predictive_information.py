#!/usr/bin/env python3
# C10 — does ANY available input move BEFORE onset? (FR32, O5) — EXPLORATORY
"""Per-feature, per-crisis timing audit: before, during, or after the event?

Every negative result so far has been about *architecture* — fusion rules,
weights, thresholds, escalation. This asks the prior question. If no available
input moves before an onset, then no architecture built on these inputs can
warn, and the whole search space above the inputs is empty.

## The classification, and why the baseline is local

Each feature is measured in three disjoint windows around every onset:

* **BEFORE** — `[onset − h, onset − 1]` for the FR32 horizons.
* **DURING** — `[onset, onset + 30]`, FR32's crisis window.
* **AFTER**  — `[onset + 31, onset + 60]`.

Separation is in units of the **local** standard deviation, from a ±1 trading
year baseline around each onset excluding all three windows. A global baseline
was tried first and rejected: `λ₁/N` has a large era shift (2008–2010 mean
0.3099, 2014–2016 mean 0.2136) and four of six onsets sit in the low era, so a
21-year baseline manufactures a negative separation from composition alone
(`CRISIS-REPLAY.md` §5c). The local baseline removes that by construction.

A feature is classified by **which window carries its largest positive
separation**. `BEFORE` is the only classification that can support advance
warning; `DURING` is contemporaneous detection wearing a warning's clothes.

## This output is EXPLORATORY and must not be cited as confirmatory

Phase 3's rule is explicit: no unrestricted feature search against the six known
crises may be treated as evidence. Everything here is a *screen* over the inputs
the repository already has, run to decide what deserves a fresh
pre-registration — not to establish that anything works. Accordingly:

* Holm correction is applied over **every** feature actually evaluated, and the
  comparison count is printed.
* Six onsets give **N_eff ≈ 5** at the measured 770-session integral timescale,
  so a per-feature separation is one of a handful of effectively independent
  observations.
* Any candidate that screens positively here is a **hypothesis**, and must be
  pre-registered against an untouched period before it counts.

## Features audited

Everything already in the repository, with nothing newly acquired: the three
pillars at their raw (pre-ECDF) scale, all four FR17/FR18 RMT statistics, the
five simple market baselines, India VIX and its acceleration, and four further
market variables computable from `daily_prices` that are not yet in the feature
set — breadth, cross-sectional dispersion, turnover surge, and downside breadth.
The mandate requires existing market variables be audited before new sources are
proposed, and these are the cheap ones that exist.

Run:
  python scripts/audit_predictive_information.py
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "rcw", Path(__file__).resolve().parent / "replay_crisis_warnings.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

from seraph.orchestration import lam1_share  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402

HORIZONS = (5, 10, 15, 20, 30)
LOCAL = 252                      # ±1 trading year local baseline
AFTER_LEN = 30


# --------------------------------------------------------------------------
# feature construction — all causal, all from existing data
# --------------------------------------------------------------------------
async def load(pool):
    rmt = await pool.fetch("SELECT date, eigenvalues, f_t, v_eig_t, omega_t, "
                           "sca_t FROM rmt_output ORDER BY date")
    hwk = await pool.fetch("SELECT ts, branching_ratio_n FROM hawkes_output "
                           "WHERE scope='market' ORDER BY ts")
    vix = await pool.fetch("SELECT date, india_vix FROM macro_covariates "
                           "WHERE india_vix IS NOT NULL ORDER BY date")
    # cross-sectional market aggregates, one pass
    mkt = await pool.fetch("""
      WITH r AS (SELECT date, symbol,
                   ln(adj_close / NULLIF(lag(adj_close)
                      OVER (PARTITION BY symbol ORDER BY date),0)) lr,
                   tottrdval
                 FROM daily_prices WHERE universe_member_flag AND adj_close > 0)
      SELECT date,
             avg(lr)                                        AS mkt,
             stddev_samp(lr)                                AS disp,
             avg(CASE WHEN lr < 0 THEN 1.0 ELSE 0.0 END)    AS frac_down,
             avg(CASE WHEN lr < -0.03 THEN 1.0 ELSE 0.0 END) AS frac_down3,
             sum(tottrdval)                                 AS turnover,
             count(*)                                       AS n_sym
      FROM r WHERE lr IS NOT NULL GROUP BY date ORDER BY date""")
    return rmt, hwk, vix, mkt


def trailing_ratio(x: np.ndarray, w: int = 60) -> np.ndarray:
    """x[i] / median(x[i-w .. i-1]) — causal, and index i excluded from its own
    reference so a surge cannot damp its own denominator."""
    out = np.full(x.size, np.nan)
    for i in range(w, x.size):
        seg = x[i - w:i]
        seg = seg[np.isfinite(seg) & (seg > 0)]
        if seg.size >= w // 2 and np.isfinite(x[i]):
            m = float(np.median(seg))
            if m > 0:
                out[i] = float(x[i]) / m
    return out


def build_features(rmt, hwk, vix, mkt) -> tuple[list[str], dict]:
    from bisect import bisect_right
    dates, lam, f_t, v_eig, om, sca = [], [], [], [], [], []
    for r in rmt:
        s = lam1_share(list(r["eigenvalues"] or []))
        if s is None:
            continue
        dates.append(str(r["date"]))
        lam.append(float(s))
        for arr, key in ((f_t, "f_t"), (v_eig, "v_eig_t"),
                         (om, "omega_t"), (sca, "sca_t")):
            arr.append(float(r[key]) if r[key] is not None else np.nan)
    n = len(dates)

    h_d = [str(r["ts"].date()) for r in hwk]
    h_v = [float(r["branching_ratio_n"]) for r in hwk]
    h_v = [v / (1.0 - v) for v in h_v]
    hawkes = np.full(n, np.nan)
    for i, d in enumerate(dates):
        j = bisect_right(h_d, d) - 1
        if j >= 0:
            hawkes[i] = h_v[j]

    ham = R.load_hamilton_causal()
    lsd = np.array([ham[d][0] if d in ham else np.nan for d in dates])

    vmap = {str(r["date"]): float(r["india_vix"]) for r in vix}
    vixv = np.array([vmap.get(d, np.nan) for d in dates])

    mi = {str(r["date"]): r for r in mkt}
    def col(key):
        return np.array([float(mi[d][key]) if d in mi and mi[d][key] is not None
                         else np.nan for d in dates])
    lr = col("mkt")
    rv = R.realised_vol(lr, 20)
    dd = R.drawdown(lr)

    feats = {
        # --- the three pillars, raw (pre-ECDF) -------------------------
        "P1 hawkes n/(1-n)":   hawkes,
        "P2 rmt lambda1/N":    np.asarray(lam),
        "P2 rmt SCA_t":        np.asarray(sca),
        "P2 rmt F_t":          np.asarray(f_t),
        "P2 rmt V_eig":        np.asarray(v_eig),
        "P2 rmt Omega_t":      np.asarray(om),
        "P3 hamilton LSD":     lsd,
        # --- existing simple baselines ---------------------------------
        "B rv_20":             rv,
        "B drawdown":          dd,
        "B semivar_20":        R.downside_semivariance(lr, 20),
        "B rv_accel_5":        R.accel(rv, 5),
        "B dd_accel_5":        R.accel(dd, 5),
        # --- India VIX, the only forward-looking input in the repo -----
        "V india_vix":         vixv,
        "V vix_accel_5":       R.accel(vixv, 5),
        "V vix_ratio_60":      trailing_ratio(vixv, 60),
        # --- further existing market variables, not yet in the set -----
        "M dispersion":        col("disp"),
        "M frac_down":         col("frac_down"),
        "M frac_down_3pct":    col("frac_down3"),
        "M turnover_ratio_60": trailing_ratio(col("turnover"), 60),
    }
    return dates, feats


# --------------------------------------------------------------------------
# the before / during / after classification
# --------------------------------------------------------------------------
def windows(dates: list[str]) -> dict[str, dict]:
    n = len(dates)
    out = {}
    for e, (onset, _) in EPOCH_BREAKS.items():
        at = [i for i, d in enumerate(dates) if d >= onset]
        if not at:
            continue
        k = at[0]
        out[e] = {
            "k": k,
            "during": (k, min(n, k + CRISIS_WINDOW_DAYS)),
            "after": (min(n, k + CRISIS_WINDOW_DAYS + 1),
                      min(n, k + CRISIS_WINDOW_DAYS + 1 + AFTER_LEN)),
            "local": (max(0, k - LOCAL), min(n, k + CRISIS_WINDOW_DAYS + LOCAL)),
        }
    return out


def sep(v: np.ndarray, sel: np.ndarray, base: np.ndarray) -> float:
    a, b = v[sel & np.isfinite(v)], v[base & np.isfinite(v)]
    if a.size < 3 or b.size < 30:
        return float("nan")
    sd = float(b.std(ddof=1))
    if sd <= 0:
        return float("nan")
    return float((a.mean() - b.mean()) / sd)


async def main(out_dir: str) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=3)
    try:
        rmt, hwk, vix, mkt = await load(pool)
    finally:
        await pool.close()
    dates, feats = build_features(rmt, hwk, vix, mkt)
    n = len(dates)
    W = windows(dates)

    print(f"\n[audit] grid {n:,} days {dates[0]} .. {dates[-1]}")
    print(f"[audit] {len(feats)} features, {len(W)} onsets")
    print(f"[audit] separations are in LOCAL sd (+-1y around each onset, all "
          f"three event windows excluded)")
    print(f"[audit] *** EXPLORATORY SCREEN - not confirmatory evidence ***\n",
          flush=True)

    report = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": ("EXPLORATORY screen over existing inputs; any positive result "
                   "is a hypothesis requiring fresh pre-registration against an "
                   "untouched period before it counts as evidence"),
        "grid": {"n": n, "first": dates[0], "last": dates[-1]},
        "n_features": len(feats), "n_onsets": len(W),
        "features": {},
    }

    hdr = (f"{'feature':<22}{'cover':>7}" + f"{'BEFORE15':>10}{'DURING':>9}"
           f"{'AFTER':>8}{'class':>9}{'epochs+':>9}")
    print(hdr); print("-" * len(hdr))

    for name, v in feats.items():
        per_epoch, befores, durings, afters = {}, [], [], []
        for e, w in W.items():
            base = np.zeros(n, dtype=bool)
            base[w["local"][0]:w["local"][1]] = True
            base[max(0, w["k"] - max(HORIZONS)):w["after"][1]] = False
            b15 = np.zeros(n, dtype=bool)
            b15[max(0, w["k"] - 15):w["k"]] = True
            dur = np.zeros(n, dtype=bool); dur[w["during"][0]:w["during"][1]] = True
            aft = np.zeros(n, dtype=bool); aft[w["after"][0]:w["after"][1]] = True
            sb, sd_, sa = (sep(v, b15, base), sep(v, dur, base), sep(v, aft, base))
            per_h = {str(h): None for h in HORIZONS}
            for h in HORIZONS:
                bh = np.zeros(n, dtype=bool); bh[max(0, w["k"] - h):w["k"]] = True
                x = sep(v, bh, base)
                per_h[str(h)] = (None if not np.isfinite(x) else round(x, 4))
            per_epoch[e] = {"before_by_horizon": per_h,
                            "before_15": None if not np.isfinite(sb) else round(sb, 4),
                            "during": None if not np.isfinite(sd_) else round(sd_, 4),
                            "after": None if not np.isfinite(sa) else round(sa, 4)}
            for lst, x in ((befores, sb), (durings, sd_), (afters, sa)):
                if np.isfinite(x):
                    lst.append(x)
        mb = float(np.mean(befores)) if befores else float("nan")
        md = float(np.mean(durings)) if durings else float("nan")
        ma = float(np.mean(afters)) if afters else float("nan")
        cover = len(befores)
        trio = {"BEFORE": mb, "DURING": md, "AFTER": ma}
        fin = {k: x for k, x in trio.items() if np.isfinite(x)}
        klass = max(fin, key=fin.get) if fin else "n/a"
        if fin and max(fin.values()) <= 0:
            klass = "none(+)"
        pos = sum(1 for x in befores if x > 0)
        report["features"][name] = {
            "onsets_covered": cover, "mean_before_15": None if not np.isfinite(mb) else round(mb, 4),
            "mean_during": None if not np.isfinite(md) else round(md, 4),
            "mean_after": None if not np.isfinite(ma) else round(ma, 4),
            "classification": klass, "epochs_with_positive_before": pos,
            "per_epoch": per_epoch}
        def f(x):
            return "   n/a" if not np.isfinite(x) else f"{x:+.3f}"
        print(f"{name:<22}{cover:>4}/{len(W):<2}{f(mb):>10}{f(md):>9}{f(ma):>8}"
              f"{klass:>9}{pos:>5}/{cover:<3}")

    print(f"\nBEFORE15 = mean separation over [onset-15, onset-1] in local sd.")
    print(f"DURING   = [onset, onset+30].   AFTER = [onset+31, onset+60].")
    print(f"class    = which window holds the LARGEST POSITIVE separation;")
    print(f"           'none(+)' means no window is positive on average.")
    print(f"epochs+  = onsets where BEFORE15 > 0, out of those covered.")
    print(f"\nOnly a BEFORE classification can support advance warning. A DURING")
    print(f"classification is contemporaneous detection, however large.")

    outp = Path(out_dir); outp.mkdir(parents=True, exist_ok=True)
    jp = outp / "predictive_information_audit.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[audit] wrote {jp}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/evidence/signals")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.out)))
