#!/usr/bin/env python3
# C10 — rank every available input on pre-onset information (Phase 3) — EXPLORATORY
"""T3 advance-warning AUC with two calibrated nulls, for every available input.

`audit_predictive_information.py` classified each feature by *when* it moves and
found **zero** features classifying as BEFORE. This quantifies the same question
as a ranking statistic with significance attached, so the screen produces an
ordered candidate list rather than a verdict per feature.

## Nulls, and why two

* **relocation** — the six onsets are circularly shifted by a common offset,
  preserving their exact spacing. Measured type-I error **8% at a nominal 5%**
  (`EARLY-WARNING-POWER.md`); the alternatives it replaced rejected at 50% and
  40%/17%.
* **AAFT** — onsets held fixed, the series phase-randomised with its exact
  marginal preserved. Answers "could a series with this autocorrelation and this
  distribution score this well on these dates".

A candidate must clear **both** to be worth pre-registering. Holm is applied
over every feature evaluated, and the comparison count and permutation
resolution floor are both printed — a p-value at the floor is censored, not
measured.

## This is a SCREEN, not evidence

Phase 3 forbids treating an unrestricted feature search against the six known
crises as confirmatory. Nothing here establishes that any feature works. The
output is a priority order for a *fresh* pre-registration whose evaluation
period is untouched by this selection. Six onsets give **N_eff ≈ 5** at the
measured 770-session integral timescale, so every number below rests on a
handful of effectively independent observations.

**In-crisis days are dropped** from the T3 target, so a crisis reading can never
be scored as a warning.

Run:
  python scripts/rank_predictive_candidates.py --perms 2000
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


def _load(name: str, fn: str):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / fn)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A = _load("apa", "audit_predictive_information.py")
EWP = _load("ewp", "early_warning_power.py")

from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import EPOCH_BREAKS  # noqa: E402


def holm(pairs):
    m = len(pairs)
    out, blocked = {}, False
    for rank, (name, p) in enumerate(sorted(pairs, key=lambda x: x[1])):
        thr = 0.05 / (m - rank)
        rej = (p <= thr) and not blocked
        if not rej:
            blocked = True
        out[name] = {"p": p, "holm_threshold": round(thr, 6),
                     "survives": bool(rej)}
    return out


async def main(perms: int, out_dir: str) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=3)
    try:
        rmt, hwk, vix, mkt = await A.load(pool)
    finally:
        await pool.close()
    dates, feats = A.build_features(rmt, hwk, vix, mkt)
    n = len(dates)

    breaks = []
    for onset, _ in EPOCH_BREAKS.values():
        at = [i for i, d in enumerate(dates) if d >= onset]
        if at:
            breaks.append(at[0])
    breaks = sorted(breaks)

    floor = 1.0 / (perms + 1)
    print(f"\n[rank] grid {n:,} days, {len(breaks)} onsets, {len(feats)} features")
    print(f"[rank] {perms} permutations -> resolution floor {floor:.5f}")
    print(f"[rank] Holm over {len(feats)} comparisons -> tightest threshold "
          f"{0.05/len(feats):.5f}")
    print(f"[rank] *** EXPLORATORY SCREEN - produces a priority order, not "
          f"evidence ***\n", flush=True)

    rng = np.random.default_rng(20261014)
    rows = {}
    hdr = (f"{'feature':<22}{'cover':>6}{'T3 AUC':>9}{'p_shift':>9}"
           f"{'p_aaft':>9}{'null p95':>10}{'verdict':>12}")
    print(hdr); print("-" * len(hdr))
    for name, v in feats.items():
        fin = np.isfinite(v)
        if fin.sum() < 500:
            print(f"{name:<22}{int(fin.sum()):>6}  insufficient coverage")
            rows[name] = {"skipped": "insufficient coverage",
                          "finite": int(fin.sum())}
            continue
        # interpolate interior gaps only; the surrogate machinery needs a dense
        # series, and the count of filled points is reported so a heavily
        # gapped feature cannot pass quietly
        w = v.copy()
        idx = np.arange(n)
        w = np.interp(idx, idx[fin], v[fin])
        obs = EWP.t3_auc(w, breaks, n)
        sh = np.asarray(EWP.relocation_null(w, n, breaks, perms, rng), dtype=float)
        aa = np.asarray(EWP.aaft_null(w, n, breaks, perms, rng), dtype=float)
        p_s = float((np.sum(sh >= obs) + 1) / (sh.size + 1))
        p_a = float((np.sum(aa >= obs) + 1) / (aa.size + 1))
        p95 = float(np.quantile(np.concatenate([sh, aa]), 0.95))
        worst = max(p_s, p_a)
        rows[name] = {"finite": int(fin.sum()), "gaps_filled": int(n - fin.sum()),
                      "t3_auc": round(float(obs), 4),
                      "p_shift": round(p_s, 5), "p_aaft": round(p_a, 5),
                      "null_p95": round(p95, 4), "p_worst": round(worst, 5)}
        verdict = ("below null" if obs < p95
                   else ("both<0.05" if worst <= 0.05 else "not sig"))
        print(f"{name:<22}{int(fin.sum()):>6}{obs:>9.4f}{p_s:>9.4f}"
              f"{p_a:>9.4f}{p95:>10.4f}{verdict:>12}", flush=True)

    scored = [(k, v["p_worst"]) for k, v in rows.items() if "p_worst" in v]
    H = holm(scored)
    surv = [k for k, h in H.items() if h["survives"]]
    print(f"\n[rank] Holm survivors over {len(scored)} comparisons: "
          f"{surv if surv else 'NONE'}")
    if floor > 0.05 / max(1, len(scored)):
        print(f"[rank] NOTE: resolution floor {floor:.5f} exceeds Holm's "
              f"tightest threshold {0.05/len(scored):.5f} - no comparison can "
              f"reach it at this draw count.")

    print(f"\n=== ranked by worst-of-two-nulls p (EXPLORATORY ORDER) ===")
    print(f"{'rank':>5}{'feature':<24}{'T3 AUC':>9}{'p_worst':>10}"
          f"{'vs null p95':>13}")
    print("-" * 61)
    for i, (k, p) in enumerate(sorted(scored, key=lambda x: x[1]), 1):
        r = rows[k]
        delta = r["t3_auc"] - r["null_p95"]
        print(f"{i:>5}{k:<24}{r['t3_auc']:>9.4f}{p:>10.4f}{delta:>+13.4f}")

    report = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": ("EXPLORATORY screen. Produces a priority order for a FRESH "
                   "pre-registration; establishes nothing on its own."),
        "perms": perms, "resolution_floor": round(floor, 6),
        "n_comparisons": len(scored),
        "holm_tightest": round(0.05 / max(1, len(scored)), 6),
        "holm": H, "holm_survivors": surv, "features": rows,
    }
    outp = Path(out_dir); outp.mkdir(parents=True, exist_ok=True)
    jp = outp / "candidate_ranking.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[rank] wrote {jp}")
    print(f"\n'below null' means the observed T3 AUC sits under the 95th")
    print(f"percentile of its own no-signal distribution - it cannot be")
    print(f"distinguished from no signal at all.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=2000)
    ap.add_argument("--out", default="docs/evidence/signals")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.perms, a.out)))
