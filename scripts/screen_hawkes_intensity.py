#!/usr/bin/env python3
# C5/C10 — does Pillar 1's CONDITIONAL INTENSITY carry pre-onset information?
"""The one held-data hypothesis the 19-feature audit did not cover.

`PREDICTIVE-INFORMATION-AUDIT.md` screened Pillar 1 as `MTS_t = n/(1−n)`, which
is a function of the **fitted parameters** and therefore piecewise-constant
between refits. FR13 `[v4]` and NFR4 specify emission at **bar frequency**, and
`DECISION-PACKAGE.md` §4.1 identified the only quantity that genuinely varies at
that frequency: the conditional intensity

    lambda_t = mu * ToD(t) + alpha * sum_k phi^(k-1) * N_(t-k)

implemented as `excitation_path()` in `seraph/pillars/hawkes/engine.py:214` and
**never persisted**. This screens it.

## Why this is reconstructed rather than read

`hawkes_output.alpha_beta` is **NULL on every row** — the production writer
stores `branching_ratio_n` and `mts` but not the fitted `alpha`, `phi`, `mu` or
time-of-day profile, so `lambda_t` cannot be recovered from the database at all.
That is itself a finding and is recorded in the decision package.

Rather than re-run the 164-minute refit schedule to recover parameters, the
excitation term is reconstructed at the **specification's own measured
parameters**: SPEC FR11 `[v4]` states *"Measured n ≈ 0.11 (α ≈ 0.055, φ ≈ 0.50,
≈ one-bar half-life)"*. Those are quoted in the requirement, not estimated here,
so nothing is fitted to the evaluation data.

**Consequence of phi ≈ 0.50, stated plainly.** A one-bar half-life means the
excitation term is dominated by the current and immediately preceding bars. The
daily aggregate of `lambda_t` is therefore close to a scaled daily negative-jump
count, and the screen is reported both ways — as the reconstructed intensity and
as the raw daily count — so the conclusion cannot hinge on the reconstruction.

## Coverage limit, which bounds the claim before any result

`intraday_bars` begins **2015-02-02**. `lambda_t` can therefore never cover
`gfc_2008` or `taper_2013`, and this screen is confined to at most **4 of 6
epochs** — the same four on which India VIX is already anti-predictive. A null
result here does not speak to the two pre-2015 epochs, and a positive one would
need the pre-2015 gap closed before it could support a general claim.

## Status: EXPLORATORY

A screen to decide whether `lambda_t` deserves a pre-registered confirmatory
experiment and a specification change. It establishes nothing on its own, and
the same two calibrated nulls and Holm correction used elsewhere are applied.

Run:
  python scripts/screen_hawkes_intensity.py --perms 2000
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402

from seraph.features.jump_extraction import extract_jumps  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402


def _load(name: str, fn: str):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / fn)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EWP = _load("ewp", "early_warning_power.py")

#: SPEC FR11 [v4]'s own measured values, quoted not estimated.
ALPHA = 0.055
PHI = 0.50
#: bars of excitation memory retained; phi^12 ~ 2e-4, so this is exact enough
MEMORY = 12
MIN_SYMBOL_BARS = 500
PRE = 15


async def jump_stream(pool) -> tuple[list, np.ndarray, np.ndarray]:
    """Market-wide per-bar negative-jump counts and the active-symbol count.

    Mirrors `write_hawkes_production.py`'s stream construction: non-positive
    closes are dropped and counted rather than patched, so they cannot inflate
    the exposure denominator.
    """
    syms = [r["symbol"] for r in await pool.fetch(
        "SELECT DISTINCT symbol FROM intraday_bars ORDER BY symbol")]
    neg, grid = [], {}
    used = dropped = 0
    for i, sym in enumerate(syms, 1):
        rows = await pool.fetch(
            "SELECT ts, close FROM intraday_bars WHERE symbol=$1 ORDER BY ts", sym)
        ts = [r["ts"] for r in rows]
        close = np.array([float(r["close"]) for r in rows], dtype=float)
        if close.size:
            good = close > 0.0
            d = int((~good).sum())
            if d:
                dropped += d
                ts = [t for t, g in zip(ts, good) if g]
                close = close[good]
        if close.size < MIN_SYMBOL_BARS:
            continue
        used += 1
        out = extract_jumps(close)
        for t in ts:
            grid[t] = grid.get(t, 0) + 1
        for j in np.flatnonzero(out["jump_sign"] == -1):
            neg.append(ts[j])
        if i % 20 == 0:
            print(f"[screen]   {i}/{len(syms)} symbols, {len(neg):,} neg jumps",
                  flush=True)
    bars = sorted(grid)
    cneg = Counter(neg)
    print(f"[screen] stream: {len(bars):,} bars, {used} symbols used, "
          f"{dropped:,} non-positive closes dropped, {len(neg):,} negative jumps")
    return (bars,
            np.array([cneg.get(t, 0) for t in bars], dtype=float),
            np.array([grid[t] for t in bars], dtype=float))


def excitation(n_neg: np.ndarray, new_sess: np.ndarray) -> np.ndarray:
    """alpha * sum_k phi^(k-1) * N_(t-k), reset at each session open.

    The reset is FR10's and matters: without it the optimiser fabricates a huge
    opening intensity, an artefact the engine docstring records. Here it means
    excitation does not carry across the overnight gap.
    """
    out = np.zeros(n_neg.size)
    for i in range(n_neg.size):
        if new_sess[i]:
            out[i] = 0.0
            continue
        acc = 0.0
        for k in range(1, MEMORY + 1):
            j = i - k
            if j < 0 or new_sess[j + 1:i + 1].any():
                break
            acc += (PHI ** (k - 1)) * n_neg[j]
        out[i] = ALPHA * acc
    return out


async def main(perms: int, out_dir: str) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=3)
    try:
        print("[screen] building the market-wide jump stream "
              "(reads intraday_bars; read-only) ...", flush=True)
        bars, n_neg, active = await jump_stream(pool)
    finally:
        await pool.close()

    day = np.array([t.date() for t in bars])
    new_sess = np.r_[True, day[1:] != day[:-1]]
    exc = excitation(n_neg, new_sess)

    # aggregate to the daily decision grid: mean intensity and total count,
    # both normalised by exposure so a day with fewer active symbols is not
    # read as a quiet day
    uniq = sorted(set(day))
    dates, lam_d, cnt_d = [], [], []
    for d in uniq:
        m = day == d
        a = active[m].sum()
        if a <= 0:
            continue
        dates.append(d.isoformat())
        lam_d.append(float(exc[m].mean()))
        cnt_d.append(float(n_neg[m].sum() / a))
    lam_d = np.asarray(lam_d)
    cnt_d = np.asarray(cnt_d)
    n = len(dates)
    print(f"\n[screen] daily grid: {n:,} days {dates[0]} .. {dates[-1]}")

    breaks, covered = [], []
    for e, (onset, _) in EPOCH_BREAKS.items():
        at = [i for i, d in enumerate(dates) if d >= onset]
        pre_ok = sum(1 for i in range(max(0, (at[0] if at else 0) - PRE),
                                      (at[0] if at else 0))) if at else 0
        if at and at[0] > PRE:
            breaks.append(at[0]); covered.append(e)
    print(f"[screen] epochs covered: {len(covered)}/6 -> {covered}")
    print(f"[screen] NOT covered (intraday_bars starts {dates[0]}): "
          f"{[e for e in EPOCH_BREAKS if e not in covered]}")

    # local-baseline before/during/after, same convention as the 19-feature audit
    LOCAL = 252
    print(f"\n=== timing classification (local +-1y baseline, as in the audit) ===")
    print(f"{'series':<26}{'BEFORE15':>10}{'DURING':>9}{'AFTER':>8}{'class':>9}")
    print("-" * 62)
    report = {"generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "status": "EXPLORATORY screen; establishes nothing on its own",
              "alpha": ALPHA, "phi": PHI,
              "alpha_phi_source": "SPEC FR11 [v4] measured values, quoted not fitted",
              "grid": {"n": n, "first": dates[0], "last": dates[-1]},
              "epochs_covered": covered,
              "epochs_not_covered": [e for e in EPOCH_BREAKS if e not in covered],
              "series": {}}

    def sep(v, sel, base):
        a, b = v[sel & np.isfinite(v)], v[base & np.isfinite(v)]
        if a.size < 3 or b.size < 30:
            return float("nan")
        sd = float(b.std(ddof=1))
        return float((a.mean() - b.mean()) / sd) if sd > 0 else float("nan")

    for nm, v in (("lambda_t (reconstructed)", lam_d),
                  ("neg jumps / active sym", cnt_d)):
        bs, ds, as_ = [], [], []
        for k in breaks:
            base = np.zeros(n, dtype=bool)
            base[max(0, k - LOCAL):min(n, k + CRISIS_WINDOW_DAYS + LOCAL)] = True
            base[max(0, k - 30):min(n, k + CRISIS_WINDOW_DAYS + 31)] = False
            b15 = np.zeros(n, dtype=bool); b15[max(0, k - PRE):k] = True
            dur = np.zeros(n, dtype=bool); dur[k:min(n, k + CRISIS_WINDOW_DAYS)] = True
            aft = np.zeros(n, dtype=bool)
            aft[min(n, k + CRISIS_WINDOW_DAYS + 1):min(n, k + CRISIS_WINDOW_DAYS + 31)] = True
            for lst, x in ((bs, sep(v, b15, base)), (ds, sep(v, dur, base)),
                           (as_, sep(v, aft, base))):
                if np.isfinite(x):
                    lst.append(x)
        mb = float(np.mean(bs)) if bs else float("nan")
        md = float(np.mean(ds)) if ds else float("nan")
        ma = float(np.mean(as_)) if as_ else float("nan")
        trio = {"BEFORE": mb, "DURING": md, "AFTER": ma}
        fin = {k: x for k, x in trio.items() if np.isfinite(x)}
        klass = max(fin, key=fin.get) if fin else "n/a"
        if fin and max(fin.values()) <= 0:
            klass = "none(+)"
        print(f"{nm:<26}{mb:>+10.3f}{md:>+9.3f}{ma:>+8.3f}{klass:>9}")
        report["series"][nm] = {"before_15": round(mb, 4), "during": round(md, 4),
                               "after": round(ma, 4), "classification": klass,
                               "epochs_with_positive_before":
                                   int(sum(1 for x in bs if x > 0))}

    # T3 AUC with both calibrated nulls
    print(f"\n=== T3 advance-warning AUC, two calibrated nulls, {perms} perms ===")
    print(f"{'series':<26}{'T3 AUC':>9}{'p_shift':>9}{'p_aaft':>9}"
          f"{'null p95':>10}{'verdict':>12}")
    print("-" * 75)
    rng = np.random.default_rng(20261014)
    for nm, v in (("lambda_t (reconstructed)", lam_d),
                  ("neg jumps / active sym", cnt_d)):
        obs = EWP.t3_auc(v, breaks, n)
        sh = np.asarray(EWP.relocation_null(v, n, breaks, perms, rng), dtype=float)
        aa = np.asarray(EWP.aaft_null(v, n, breaks, perms, rng), dtype=float)
        p_s = float((np.sum(sh >= obs) + 1) / (sh.size + 1))
        p_a = float((np.sum(aa >= obs) + 1) / (aa.size + 1))
        p95 = float(np.quantile(np.concatenate([sh, aa]), 0.95))
        verdict = ("below null" if obs < p95
                   else ("both<0.05" if max(p_s, p_a) <= 0.05 else "not sig"))
        print(f"{nm:<26}{obs:>9.4f}{p_s:>9.4f}{p_a:>9.4f}{p95:>10.4f}"
              f"{verdict:>12}")
        report["series"][nm].update(
            {"t3_auc": round(float(obs), 4), "p_shift": round(p_s, 5),
             "p_aaft": round(p_a, 5), "null_p95": round(p95, 4),
             "verdict": verdict})

    print(f"\nHolm over 2 comparisons -> tightest threshold 0.02500")
    print(f"resolution floor {1/(perms+1):.5f}")
    print(f"\nCOVERAGE BOUND: this screen can speak to {len(covered)} of 6 epochs.")
    print(f"`intraday_bars` starts {dates[0]}, so the two pre-2015 epochs are")
    print(f"out of reach for lambda_t at any refit cadence or emission frequency.")

    outp = Path(out_dir); outp.mkdir(parents=True, exist_ok=True)
    jp = outp / "hawkes_intensity_screen.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[screen] wrote {jp}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=2000)
    ap.add_argument("--out", default="docs/evidence/signals")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.perms, a.out)))
