#!/usr/bin/env python3
# C10 — does FINANCIAL-SECTOR equity volatility lead onsets? (external-research test)
"""The one published finding that SERAPH has never tested, run on SERAPH's data.

## Why this hypothesis and not another

Giglio, Kelly & Pruitt, *Systemic Risk and the Macroeconomy: An Empirical
Evaluation* (NBER w20963; Journal of Financial Economics, 2016) evaluate 17–22
systemic-risk measures across the US and Europe over several decades. Two of
their results bear directly on this project:

1. **"Financial sector equity volatility exhibits strong univariate predictive
   power for the quantiles of future real outcomes, while equity volatility in
   non-financial sectors appears to have little, if any, predictive power."**
2. The compendium predicts the **lower tail** (10th/20th percentile) of future
   outcomes, **not the mean or median** — and does so *"despite the individual
   failure of many measures on this account."*

Every one of the 19 features screened in `PREDICTIVE-INFORMATION-AUDIT.md`, and
both series in `THREE-CHECKS-RESULTS.md`, is computed on a **market-wide**
aggregate. The financial/non-financial split has never been computed here, so
the single best-documented predictive result in this literature is untested on
this corpus. That is the gap this script closes.

**What it does not claim.** Giglio et al. predict macro tail quantiles at
quarterly horizons. SERAPH's target is market-crisis onset at 5–15 trading days.
These are different targets at different horizons, so a positive result there
does not imply one here — which is exactly why it has to be measured rather than
assumed.

## PRE-REGISTRATION — fixed before the first result was seen

**The symbol list below was chosen by company identity alone** — banks, NBFCs,
insurers, exchanges, depositories and AMCs — and **not** by any return,
volatility or crisis statistic. It is written into this file before any output
exists, so the selection cannot have been informed by what the features do.
Names absent from `daily_prices` are simply unavailable (8 of the 61 candidates:
DHFL, HDFC, IBULHSGFIN, IDFC, INDIABULLS, JKBANK, SRTRANSFIN, UJJIVAN).

**Features, fixed now:**

* `fin_rv_20`          — 20-day realised vol of the financial-sector mean return
* `nonfin_rv_20`       — the same for every other universe member
* `fin_minus_nonfin`   — the difference; this is the sharper test, because it is
                         the *relative* claim Giglio et al. actually make
* `fin_ratio_60`       — `fin_rv_20` over its own trailing 60-day median
* `fin_dispersion`     — cross-sectional sd of financial-sector returns

**Minimum coverage, fixed now:** a day is emitted only if **≥ 20 financial names
and ≥ 100 non-financial names** are present, so a thin day cannot masquerade as
a quiet one.

**Decision criteria, fixed now.** A feature is worth taking further only if all
three hold:

1. it classifies as **BEFORE** on the local-baseline timing test;
2. its T3 AUC **exceeds the 95th percentile of its own no-signal distribution**;
3. `p ≤ 0.05` under **both** calibrated nulls after Holm correction over the
   five features tested (tightest threshold 0.01).

Anything less is a negative result and is reported as one. In-crisis days are
dropped, so a crisis reading can never score as a warning.

**Status: EXPLORATORY** — a screen against six known onsets. A pass here earns a
fresh pre-registration against an untouched period under
`NEXT-PREREGISTRATION-DRAFT.md`, not a production change.

Run:
  python scripts/screen_financial_sector_stress.py --perms 2000
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

from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402


def _load(name: str, fn: str):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / fn)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EWP = _load("ewp", "early_warning_power.py")
R = _load("rcw", "replay_crisis_warnings.py")

#: Chosen by company identity only, before any result existed. See the
#: pre-registration note in the module docstring.
FINANCIALS: tuple[str, ...] = (
    "SBIN", "HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "INDUSINDBK",
    "BANKBARODA", "PNB", "CANBK", "UNIONBANK", "BANKINDIA", "IDBI",
    "IDFCFIRSTB", "FEDERALBNK", "RBLBANK", "YESBANK", "IFCI", "LICHSGFIN",
    "BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN", "CHOLAFIN", "M&MFIN", "PFC",
    "RECLTD", "SBILIFE", "HDFCLIFE", "ICICIPRULI", "ICICIGI", "LICI",
    "MUTHOOTFIN", "MANAPPURAM", "SBICARD", "HDFCAMC", "NAM-INDIA", "BSE",
    "MCX", "CDSL", "POLICYBZR", "PAYTM", "IIFL", "JMFINANCIL", "MOTILALOFS",
    "EDELWEISS", "GICRE", "NIACL", "EQUITASBNK", "AUBANK", "CUB",
    "KARURVYSYA", "SOUTHBANK", "DCBBANK", "CSBBANK", "TMB",
)
MIN_FIN, MIN_NONFIN = 20, 100
PRE = 15
LOCAL = 252
AFTER_LEN = 30


async def load(pool):
    return await pool.fetch("""
      WITH r AS (
        SELECT date, symbol,
               ln(adj_close / NULLIF(lag(adj_close)
                  OVER (PARTITION BY symbol ORDER BY date), 0)) lr,
               (symbol = ANY($1::text[])) AS is_fin
        FROM daily_prices
        WHERE universe_member_flag AND adj_close > 0)
      SELECT date,
             avg(lr)    FILTER (WHERE is_fin)        AS fin_mean,
             stddev_samp(lr) FILTER (WHERE is_fin)   AS fin_disp,
             count(*)   FILTER (WHERE is_fin)        AS n_fin,
             avg(lr)    FILTER (WHERE NOT is_fin)    AS nonfin_mean,
             count(*)   FILTER (WHERE NOT is_fin)    AS n_nonfin
      FROM r WHERE lr IS NOT NULL GROUP BY date ORDER BY date""", list(FINANCIALS))


def sep(v, sel, base):
    a, b = v[sel & np.isfinite(v)], v[base & np.isfinite(v)]
    if a.size < 3 or b.size < 30:
        return float("nan")
    sd = float(b.std(ddof=1))
    return float((a.mean() - b.mean()) / sd) if sd > 0 else float("nan")


async def main(perms: int, out_dir: str) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        rows = await load(pool)
    finally:
        await pool.close()

    keep = [r for r in rows
            if r["n_fin"] and r["n_fin"] >= MIN_FIN
            and r["n_nonfin"] and r["n_nonfin"] >= MIN_NONFIN]
    dates = [str(r["date"]) for r in keep]
    n = len(dates)
    fin_lr = np.array([float(r["fin_mean"]) if r["fin_mean"] is not None
                       else np.nan for r in keep])
    non_lr = np.array([float(r["nonfin_mean"]) if r["nonfin_mean"] is not None
                       else np.nan for r in keep])
    disp = np.array([float(r["fin_disp"]) if r["fin_disp"] is not None
                     else np.nan for r in keep])
    nf = np.array([int(r["n_fin"]) for r in keep])

    print(f"\n[fin] pre-registered financial list: {len(FINANCIALS)} names")
    print(f"[fin] coverage floor: >={MIN_FIN} financial, >={MIN_NONFIN} other")
    print(f"[fin] days retained: {n:,} of {len(rows):,}  "
          f"{dates[0] if n else '-'} .. {dates[-1] if n else '-'}")
    print(f"[fin] financial names per day: min {nf.min()} median "
          f"{int(np.median(nf))} max {nf.max()}")

    fin_rv = R.realised_vol(fin_lr, 20)
    non_rv = R.realised_vol(non_lr, 20)
    feats = {
        "fin_rv_20": fin_rv,
        "nonfin_rv_20": non_rv,
        "fin_minus_nonfin": fin_rv - non_rv,
        "fin_ratio_60": np.array([np.nan] * n),
        "fin_dispersion": disp,
    }
    # trailing-median ratio, causal, index i excluded from its own reference
    out = np.full(n, np.nan)
    for i in range(60, n):
        seg = fin_rv[i - 60:i]
        seg = seg[np.isfinite(seg) & (seg > 0)]
        if seg.size >= 30 and np.isfinite(fin_rv[i]):
            m = float(np.median(seg))
            if m > 0:
                out[i] = fin_rv[i] / m
    feats["fin_ratio_60"] = out

    breaks, covered = [], []
    for e, (onset, _) in EPOCH_BREAKS.items():
        at = [i for i, d in enumerate(dates) if d >= onset]
        if at and at[0] > PRE:
            breaks.append(at[0]); covered.append(e)
    print(f"[fin] epochs covered: {len(covered)}/6 -> {covered}\n", flush=True)

    report = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "EXPLORATORY screen; a pass earns a fresh pre-registration",
        "hypothesis_source": ("Giglio, Kelly & Pruitt 2016 (NBER w20963 / JFE): "
                              "financial-sector equity volatility has strong "
                              "univariate predictive power for macro tail "
                              "quantiles; non-financial has little or none"),
        "financials_preregistered": list(FINANCIALS),
        "coverage_floor": {"min_financial": MIN_FIN, "min_other": MIN_NONFIN},
        "grid": {"n": n, "first": dates[0], "last": dates[-1]},
        "epochs_covered": covered, "perms": perms, "features": {},
    }

    print("=== timing classification (local +-1y baseline) ===")
    print(f"{'feature':<20}{'BEFORE15':>10}{'DURING':>9}{'AFTER':>8}{'class':>9}"
          f"{'epochs+':>9}")
    print("-" * 65)
    for name, v in feats.items():
        bs, ds, as_ = [], [], []
        for k in breaks:
            base = np.zeros(n, dtype=bool)
            base[max(0, k - LOCAL):min(n, k + CRISIS_WINDOW_DAYS + LOCAL)] = True
            base[max(0, k - 30):min(n, k + CRISIS_WINDOW_DAYS + AFTER_LEN + 1)] = False
            b15 = np.zeros(n, dtype=bool); b15[max(0, k - PRE):k] = True
            dur = np.zeros(n, dtype=bool); dur[k:min(n, k + CRISIS_WINDOW_DAYS)] = True
            aft = np.zeros(n, dtype=bool)
            aft[min(n, k + CRISIS_WINDOW_DAYS + 1):
                min(n, k + CRISIS_WINDOW_DAYS + 1 + AFTER_LEN)] = True
            for lst, x in ((bs, sep(v, b15, base)), (ds, sep(v, dur, base)),
                           (as_, sep(v, aft, base))):
                if np.isfinite(x):
                    lst.append(x)
        mb = float(np.mean(bs)) if bs else float("nan")
        md = float(np.mean(ds)) if ds else float("nan")
        ma = float(np.mean(as_)) if as_ else float("nan")
        trio = {"BEFORE": mb, "DURING": md, "AFTER": ma}
        fin_ = {k: x for k, x in trio.items() if np.isfinite(x)}
        klass = max(fin_, key=fin_.get) if fin_ else "n/a"
        if fin_ and max(fin_.values()) <= 0:
            klass = "none(+)"
        pos = sum(1 for x in bs if x > 0)
        report["features"][name] = {
            "before_15": round(mb, 4), "during": round(md, 4),
            "after": round(ma, 4), "classification": klass,
            "epochs_with_positive_before": pos, "onsets_covered": len(bs)}
        print(f"{name:<20}{mb:>+10.3f}{md:>+9.3f}{ma:>+8.3f}{klass:>9}"
              f"{f'{pos}/{len(bs)}':>9}")

    print(f"\n=== T3 AUC, two calibrated nulls, {perms} perms ===")
    print(f"{'feature':<20}{'T3 AUC':>9}{'p_shift':>9}{'p_aaft':>9}"
          f"{'null p95':>10}{'verdict':>12}")
    print("-" * 69)
    rng = np.random.default_rng(20261014)
    ps = []
    for name, v in feats.items():
        fin_m = np.isfinite(v)
        if fin_m.sum() < 500:
            print(f"{name:<20}  insufficient coverage ({int(fin_m.sum())})")
            continue
        w = np.interp(np.arange(n), np.arange(n)[fin_m], v[fin_m])
        obs = EWP.t3_auc(w, breaks, n)
        sh = np.asarray(EWP.relocation_null(w, n, breaks, perms, rng), dtype=float)
        aa = np.asarray(EWP.aaft_null(w, n, breaks, perms, rng), dtype=float)
        p_s = float((np.sum(sh >= obs) + 1) / (sh.size + 1))
        p_a = float((np.sum(aa >= obs) + 1) / (aa.size + 1))
        p95 = float(np.quantile(np.concatenate([sh, aa]), 0.95))
        verdict = ("below null" if obs < p95
                   else ("both<0.05" if max(p_s, p_a) <= 0.05 else "not sig"))
        ps.append((name, max(p_s, p_a)))
        report["features"][name].update(
            {"t3_auc": round(float(obs), 4), "p_shift": round(p_s, 5),
             "p_aaft": round(p_a, 5), "null_p95": round(p95, 4),
             "verdict": verdict})
        print(f"{name:<20}{obs:>9.4f}{p_s:>9.4f}{p_a:>9.4f}{p95:>10.4f}"
              f"{verdict:>12}", flush=True)

    thr = 0.05 / max(1, len(ps))
    print(f"\n[fin] Holm over {len(ps)} features -> tightest threshold {thr:.5f}")
    print(f"[fin] resolution floor {1/(perms+1):.5f}")
    passed = [nm for nm, p in ps
              if p <= thr
              and report["features"][nm].get("classification") == "BEFORE"
              and report["features"][nm].get("t3_auc", 0)
              > report["features"][nm].get("null_p95", 1)]
    print(f"[fin] features meeting ALL THREE pre-registered criteria: "
          f"{passed if passed else 'NONE'}")
    report["passed_all_criteria"] = passed

    outp = Path(out_dir); outp.mkdir(parents=True, exist_ok=True)
    jp = outp / "financial_sector_screen.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[fin] wrote {jp}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=2000)
    ap.add_argument("--out", default="docs/evidence/signals")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.perms, a.out)))
