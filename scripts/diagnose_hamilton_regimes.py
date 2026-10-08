#!/usr/bin/env python3
# C7 — how many latent regimes does the NSE feature space actually support?
"""Two focused diagnostics, run before any C7 redesign.

1. FEATURE INFORMATION - do AR_t and BAS_t carry regime information independent
   of RV_t, or is the problem effectively univariate?
2. REGIME COUNT - fit 2-state and 3-state filters and ask which, if either, the
   data supports. Not "can two be made to work".

Transition estimates are guarded: a probability sitting on the optimiser's
clip (1-1e-8) is a boundary/identifiability FAILURE and is reported as such,
never as a half-life. The 3.47e7-day figure seen earlier was exactly this.

Run: python scripts/diagnose_hamilton_regimes.py
"""
from __future__ import annotations

import asyncio
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.pillars.hamilton.engine import MultivariateTVTPHamilton  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

CLIP_TOL = 1e-6          # within this of 1.0 => on the boundary, not estimated


async def load():
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        rows = await pool.fetch(
            "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
        return ([r["date"] for r in rows],
                np.array([[float(r["rv_t_yz"]), float(r["ar_t"]), float(r["bas_t"])]
                          for r in rows]))
    finally:
        await pool.close()


def fit(y, k, seed_note=""):
    """Fit a k-state filter; return diagnostics with an explicit boundary flag."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = MultivariateTVTPHamilton(y, k_regimes=k)
        try:
            r = m.fit(maxiter=200, disp=False)
        except Exception as e:
            return {"failed": str(e)[:60]}
    pars = r.params
    means = np.array([pars[m.parameters[j, "means"]] for j in range(k)])
    varis = np.array([pars[m.parameters[j, "variances"]] for j in range(k)])
    order = np.argsort(means[:, 0])
    sm = np.asarray(r.smoothed_marginal_probabilities)
    if sm.shape[0] != k:
        sm = sm.T
    occ = np.bincount(np.argmax(sm, axis=0), minlength=k) / sm.shape[1]

    trans = np.asarray(m.regime_transition_matrix(pars))[:, :, 0]
    diag = np.array([trans[j, j] for j in range(k)])
    on_boundary = bool(np.any(diag > 1 - CLIP_TOL))
    half = [float(np.log(2) / max(1 - p, 1e-12)) for p in diag]

    sd = float(np.sqrt(np.mean([varis[order[0]][0], varis[order[-1]][0]])))
    sep = float((means[order[-1]][0] - means[order[0]][0]) / sd) if sd > 0 else np.nan
    n_par = k * y.shape[1] * 2 + k * (k - 1)
    bic = float(-2 * r.llf + n_par * np.log(y.shape[0]))
    aic = float(-2 * r.llf + 2 * n_par)
    return {"llf": float(r.llf), "occ": occ[order], "sep": sep, "bic": bic,
            "aic": aic, "half": [half[j] for j in order],
            "boundary": on_boundary, "means": means[order],
            "diag": diag[order], "failed": None}


def show(tag, d):
    if d.get("failed"):
        print(f"{tag:>26}  FAILED: {d['failed']}"); return
    occ = "/".join(f"{x:.1%}" for x in d["occ"])
    hl = "BOUNDARY" if d["boundary"] else "/".join(f"{h:.0f}d" for h in d["half"])
    print(f"{tag:>26} {d['sep']:>7.2f} {occ:>22} {hl:>22} {d['bic']:>11.0f} {d['aic']:>11.0f}")


async def main() -> int:
    dates, y = await load()
    rv, ar, bas = y[:, 0], y[:, 1], y[:, 2]
    z = (y - y.mean(axis=0)) / y.std(axis=0)
    print(f"observations: {len(dates)} days\n")

    # ---------- 1. FEATURE INFORMATION ----------------------------------
    print("=== 1. FEATURE INFORMATION ===")
    for nm, v in (("RV", rv), ("AR", ar), ("BAS", bas)):
        print(f"  {nm:>4}  mean={v.mean():>8.4f} sd={v.std():>8.4f} "
              f"cv={v.std()/abs(v.mean()):>6.3f} "
              f"range={v.max()-v.min():>8.4f} p5-p95={np.percentile(v,95)-np.percentile(v,5):>8.4f}")
    c = np.corrcoef(y.T)
    print(f"\n  correlations  RV-AR={c[0,1]:+.3f}  RV-BAS={c[0,2]:+.3f}  AR-BAS={c[1,2]:+.3f}")
    ev = np.linalg.eigvalsh(np.corrcoef(z.T))[::-1]
    print(f"  PCA on standardised features: variance shares "
          f"{'/'.join(f'{e/ev.sum():.1%}' for e in ev)}")

    hi = rv >= np.percentile(rv, 80)
    lo = rv <= np.percentile(rv, 20)
    print(f"\n  separation between high-RV and low-RV quintiles (in sd units):")
    for nm, v in (("RV", rv), ("AR", ar), ("BAS", bas)):
        d = (v[hi].mean() - v[lo].mean()) / v.std()
        print(f"    {nm:>4}  {d:+.3f} sd  -> {'informative' if abs(d) > 0.5 else 'WEAK/REDUNDANT'}")

    # ---------- 2. REGIME COUNT ------------------------------------------
    print(f"\n=== 2. REGIME COUNT ===")
    print(f"{'model':>26} {'sep_sd':>7} {'occupancy':>22} {'half-lives':>22} "
          f"{'BIC':>11} {'AIC':>11}")
    print("-" * 104)
    rng = np.random.default_rng(0)
    lab = np.concatenate([np.full(500, b) for b in (0, 2, 1, 0, 2, 1)])
    M = np.array([[0.8, 0.35, 0.10], [1.6, 0.55, 0.22], [3.2, 0.80, 0.45]])
    syn = M[lab] + rng.normal(scale=[0.18, 0.05, 0.03], size=(lab.size, 3))
    show("CONTROL synth 3-state", fit(syn, 3))
    show("CONTROL synth 2-state", fit(syn, 2))
    for k in (2, 3):
        show(f"real RV+AR+BAS {k}-state", fit(y, k))
        show(f"real RV only   {k}-state", fit(rv.reshape(-1, 1), k))
        show(f"real RV+AR     {k}-state", fit(y[:, :2], k))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
