#!/usr/bin/env python3
# C10 — calibrated nulls for the T1 detection claims (FR32, FR33, FR35, O7)
"""Does the 3-pillar CSRS's detection improvement survive a calibrated null?

### The claim under test

`STRESS-PILLAR-DECISION.md` §3 reports the headline result SERAPH currently
makes: adding the stress slot raises T1 crisis-detection AUC from **0.5372 to
0.6743**, with precision 3.1x and recall 3.7x. That was measured against a
nominal null — AUC compared to 0.5 — which assumes the positive days are
independent.

They are not. T1 marks the 30 trading days from each FR32 break as positive. Over
the CSRS span that is a handful of events, and days inside one 30-day window are
nearly perfectly correlated, so the effective sample size is the **number of
onsets**, not the number of days. `EARLY-WARNING-POWER.md` showed what this does
to T3: the one candidate that looked like advance warning (`drawdown`, 0.6735)
sits below the 95th percentile of the no-signal distribution.

T1 has the same structure and has never been checked the same way. Unlike T3,
**T1 is a claim the project actively makes**, so it matters more.

### Method

Identical machinery to `early_warning_power.py`, imported rather than copied:

* `shift` — circular shift of the whole onset set, preserving every pairwise
  spacing and varying only the phase.
* `aaft` — onsets fixed, series phase-randomised with its exact marginal and
  approximate ACF preserved.

Both were calibrated on synthetic data there: actual type-I error 8% at a nominal
5%, with the AR(1) background initialised at its stationary variance (two earlier
versions of the null were measured to be badly miscalibrated and are documented
in that report).

Each series is scored on **its own available span**, and the onset set is
restricted to breaks inside that span — so the CSRS, which begins in 2017, is
scored on the four epochs it actually covers. That is why its AUC is not
comparable to a full-corpus candidate's, and the number of onsets is printed for
every row.

Writes nothing. Reads `csrs`, `hawkes_output`, `rmt_output`, `hamilton_output`,
`daily_prices`.

Run: python scripts/calibrate_detection_claims.py [--perms 400]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402
from seraph.validation.harness import auc  # noqa: E402

_s1 = importlib.util.spec_from_file_location(
    "ewp", _ROOT / "scripts" / "early_warning_power.py")
ewp = importlib.util.module_from_spec(_s1)
_s1.loader.exec_module(ewp)

_s2 = importlib.util.spec_from_file_location(
    "ssc", _ROOT / "scripts" / "study_stress_candidates.py")
ssc = importlib.util.module_from_spec(_s2)
_s2.loader.exec_module(ssc)


def t1_auc(score: np.ndarray, break_idx, n: int) -> float:
    """T1 detection AUC: positive on [break, break + 30), whole sample kept."""
    y = np.zeros(n, dtype=int)
    for i in break_idx:
        y[(np.arange(i, i + CRISIS_WINDOW_DAYS)) % n] = 1
    keep = np.isfinite(score)
    if y[keep].sum() < 5 or (1 - y[keep]).sum() < 5:
        return float("nan")
    return float(auc(score[keep], y[keep]))


def shift_null_t1(score, n, breaks, perms, rng):
    base = np.asarray(sorted(int(b) for b in breaks))
    offs = rng.choice(np.arange(1, n), size=min(perms, n - 1), replace=False)
    out = [t1_auc(score, (base + int(o)) % n, n) for o in offs]
    return np.array([v for v in out if np.isfinite(v)])


def aaft_null_t1(score, n, breaks, perms, rng):
    finite = np.isfinite(score)
    vals = score[finite]
    m = vals.size
    ranks = np.argsort(np.argsort(vals))
    srt = np.sort(vals)
    out = []
    for _ in range(perms):
        ns = np.sort(rng.normal(size=m))
        spec = np.fft.rfft(ns[ranks])
        ph = rng.uniform(0, 2 * np.pi, size=spec.shape[0])
        ph[0] = 0.0
        if m % 2 == 0:
            ph[-1] = 0.0
        sur = np.fft.irfft(np.abs(spec) * np.exp(1j * (np.angle(spec) + ph)), n=m)
        full = np.full(n, np.nan)
        full[finite] = srt[np.argsort(np.argsort(sur))]
        a = t1_auc(full, breaks, n)
        if np.isfinite(a):
            out.append(a)
    return np.array(out)


async def load():
    c = await asyncpg.connect(resolve_dsn(), timeout=300)
    obs = await c.fetch(
        "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    mkt = await c.fetch("""
      WITH r AS (SELECT date, symbol,
                        ln(adj_close / NULLIF(lag(adj_close) OVER (
                            PARTITION BY symbol ORDER BY date), 0)) lr
                 FROM daily_prices WHERE universe_member_flag AND adj_close > 0)
      SELECT date, avg(lr) mkt FROM r WHERE lr IS NOT NULL
      GROUP BY date ORDER BY date""")
    rmt = await c.fetch("SELECT date, eigenvalues FROM rmt_output ORDER BY date")
    cs2 = await c.fetch("SELECT ts, csrs FROM csrs "
                        "WHERE weights_artefact_id LIKE '349a6874%' ORDER BY ts")
    cs3 = await c.fetch("SELECT ts, csrs FROM csrs "
                        "WHERE weights_artefact_id LIKE '36b6f9bb%' ORDER BY ts")
    hwk = await c.fetch("SELECT ts, branching_ratio_n FROM hawkes_output "
                        "WHERE scope='market' ORDER BY ts")
    await c.close()
    return obs, mkt, rmt, cs2, cs3, hwk


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=400)
    ap.add_argument("--csv", action="append", default=[], metavar="LABEL=PATH",
                    help="extra series from a run_csrs_research.py --dump CSV; "
                         "repeatable. Lets the full-span (2005+, 6 onsets) CSRS "
                         "be scored without persisting it to E10.")
    a = ap.parse_args()

    obs, mkt, rmt, cs2, cs3, hwk = asyncio.run(load())
    mk = {str(r["date"]): float(r["mkt"]) for r in mkt}
    rows = [r for r in obs if str(r["date"]) in mk]
    dates = [str(r["date"]) for r in rows]
    n = len(dates)
    idx = {d: i for i, d in enumerate(dates)}
    lr = np.array([mk[d] for d in dates])
    rv = np.array([float(r["rv_t_yz"]) for r in rows])
    ar = np.array([float(r["ar_t"]) for r in rows])
    bas = np.array([float(r["bas_t"]) for r in rows])

    series: dict[str, np.ndarray] = dict(ssc.build_features(dates, lr, rv, ar, bas))

    def from_rows(rs, key, tskey):
        v = np.full(n, np.nan)
        for r in rs:
            d = str(r[tskey])[:10]
            if d in idx and r[key] is not None:
                v[idx[d]] = float(r[key])
        return v

    series["CSRS 2-pillar"] = from_rows(cs2, "csrs", "ts")
    series["CSRS 3-pillar"] = from_rows(cs3, "csrs", "ts")
    series["hawkes n"] = from_rows(hwk, "branching_ratio_n", "ts")
    lam = np.full(n, np.nan)
    for r in rmt:
        d = str(r["date"])
        ev = r["eigenvalues"]
        if d in idx and ev:
            e = np.asarray(ev, dtype=float)
            lam[idx[d]] = float(e.max() / e.size)
    series["rmt lam1/N"] = lam

    for spec in a.csv:
        label, _, path = spec.partition("=")
        v = np.full(n, np.nan)
        hit = 0
        for ln in Path(path).read_text(encoding="utf-8").splitlines()[1:]:
            parts = ln.split(",")
            if len(parts) < 2:
                continue
            d = parts[0][:10]
            if d in idx:
                v[idx[d]] = float(parts[1])
                hit += 1
        print(f"[csv] {label}: {hit:,} of {n:,} grid days from {path}")
        series[label] = v

    print(f"grid: {n:,} days {dates[0]} .. {dates[-1]}")
    # Permutation resolution matters for the Holm step below: the smallest
    # achievable p is 1/(1+perms), so with 200 draws nothing can go under
    # 0.00498 and Holm's tightest threshold (0.05/15 = 0.00333) is unreachable
    # by construction. That is a resolution limit, not evidence.
    print(f"perms: {a.perms} per null; smallest resolvable p = "
          f"{1 / (1 + a.perms):.5f}\n")
    print(f"{'series':>16} {'span':>7} {'ons':>4} {'T1 AUC':>8} {'shiftmu':>8} "
          f"{'p_shift':>8} {'aaftmu':>8} {'p_aaft':>8} {'null p95':>9} {'verdict':>9}")
    print("-" * 104)

    rng = np.random.default_rng(777)
    out = {}
    for name, s in series.items():
        fin = np.isfinite(s)
        if fin.sum() < 400:
            print(f"{name:>16}  insufficient coverage ({int(fin.sum())} days)")
            continue
        first, last = dates[int(np.argmax(fin))], dates[n - 1 - int(np.argmax(fin[::-1]))]
        brk = [idx[next(d for d in dates if d >= bd)]
               for bd, _ in EPOCH_BREAKS.values()
               if any(d >= bd for d in dates)]
        brk = [b for b in brk if first <= dates[b] <= last]
        if len(brk) < 2:
            print(f"{name:>16}  only {len(brk)} onsets in span — skipped")
            continue
        obs_auc = t1_auc(s, brk, n)
        ns = shift_null_t1(s, n, brk, a.perms, rng)
        na = aaft_null_t1(s, n, brk, a.perms, rng)
        p_s = (1 + int(np.sum(ns >= obs_auc))) / (1 + ns.size)
        p_a = (1 + int(np.sum(na >= obs_auc))) / (1 + na.size)
        p95 = float(np.percentile(np.concatenate([ns, na]), 95))
        verdict = "SIG" if (max(p_s, p_a) <= 0.05 and obs_auc >= p95) else "not sig"
        out[name] = (obs_auc, p_s, p_a, p95, len(brk))
        print(f"{name:>16} {first[:4]}+ {len(brk):>4} {obs_auc:>8.4f} "
              f"{ns.mean():>8.4f} {p_s:>8.4f} {na.mean():>8.4f} {p_a:>8.4f} "
              f"{p95:>9.4f} {verdict:>9}", flush=True)

    print("\n=== THE CLAIM UNDER TEST ===")
    if "CSRS 2-pillar" in out and "CSRS 3-pillar" in out:
        a2, b2 = out["CSRS 2-pillar"][0], out["CSRS 3-pillar"][0]
        print(f"  STRESS-PILLAR-DECISION.md reports T1 0.5372 -> 0.6743 "
              f"(+0.137) for the stress slot.")
        print(f"  measured here: {a2:.4f} -> {b2:.4f} ({b2 - a2:+.4f}) "
              f"on {out['CSRS 3-pillar'][4]} onsets")
        for nm in ("CSRS 2-pillar", "CSRS 3-pillar"):
            v, ps, pa, p95, k = out[nm]
            ok = max(ps, pa) <= 0.05 and v >= p95
            print(f"    {nm:>14}: AUC {v:.4f}  p_shift {ps:.4f}  p_aaft {pa:.4f}"
                  f"  no-signal 95th pct {p95:.4f}  -> "
                  f"{'SIGNIFICANT' if ok else 'NOT SIGNIFICANT'}")
        print("\n  A per-configuration AUC can only be called an improvement if")
        print("  the higher value clears its own null. Reporting a difference")
        print("  between two numbers that both sit inside their nulls is not a")
        print("  detection result.")
    print("\n=== MULTIPLICITY (Holm, on max(p_shift, p_aaft)) ===")
    ranked = sorted(((max(v[1], v[2]), k) for k, v in out.items()))
    m = len(ranked)
    print(f"  {m} series screened. Holm: reject p_(i) only while "
          f"p_(i) <= 0.05/({m}-i+1).")
    still = []
    for i, (p, k) in enumerate(ranked, start=1):
        thr = 0.05 / (m - i + 1)
        ok = p <= thr
        print(f"    {i:>2}. {k:>16}  p={p:.4f}  threshold={thr:.5f}  "
              f"{'survives' if ok else 'does NOT survive'}")
        if not ok:
            break
        still.append(k)
    print(f"  survives Holm across all {m} comparisons: "
          f"{still if still else 'NONE'}")
    print("  A nominal p just under 0.05 from a 15-way screen is not a finding.")
    print("  Measured type-I error of this test is ~8% at nominal 5%")
    print("  (docs/evidence/EARLY-WARNING-POWER.md), so treat 0.04-0.05 as")
    print("  borderline rather than as a pass.")

    print("\n  Onset counts differ by span, so AUCs across rows are NOT")
    print("  comparable (ARCHITECTURE D5(b)). Each row is judged only against")
    print("  its own null.")
    print("  T1 is partly TAUTOLOGICAL for volatility-derived signals: FR32")
    print("  crisis windows are high-volatility windows by construction (mean")
    print("  rv_t_yz 0.6109 inside vs 0.4979 outside). A T1 pass is therefore")
    print("  not independent evidence of systemic-risk detection, and it says")
    print("  nothing at all about advance warning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
