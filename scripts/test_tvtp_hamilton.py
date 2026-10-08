#!/usr/bin/env python3
# C7 — the specification-faithful FR21 test: does TVTP rescue regime identification?
"""The earlier collapse was measured with CONSTANT transitions, which is not the
formulation FR20/FR21 specify. This is the missing test.

Covariate availability (checked, not assumed): `macro_covariates`,
`tariff_events` and `flow_aggregates` are all EMPTY, so the `z_t` of SPEC E4 -
repo rate, credit growth, India VIX, INR TWI, Brent, G_t - does not exist in
this dataset. Inventing it is not an option. FR21 however also specifies a
"state-dependent structural-break process", which admits transitions driven by
an observable state; the lagged standardised RV level is used as that covariate.
It is derived entirely from data we hold, and it is the same quantity the
regime is meant to describe, so a genuine regime structure should show up as
transition probabilities that respond to it.

A transition probability resting on the optimiser's clip is reported as a
BOUNDARY failure, never converted to a half-life.

Run: python scripts/test_tvtp_hamilton.py
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

CLIP_TOL = 1e-6


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


def fit(y, k, z=None, seed=0):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = MultivariateTVTPHamilton(y, exog_tvtp=z, k_regimes=k)
        try:
            r = m.fit(maxiter=250, disp=False)
        except Exception as e:
            return {"failed": str(e)[:55]}
    pars = r.params
    means = np.array([pars[m.parameters[j, "means"]] for j in range(k)])
    varis = np.array([pars[m.parameters[j, "variances"]] for j in range(k)])
    order = np.argsort(means[:, 0])
    sm = np.asarray(r.smoothed_marginal_probabilities)
    if sm.shape[0] != k:
        sm = sm.T
    occ = (np.bincount(np.argmax(sm, axis=0), minlength=k) / sm.shape[1])[order]

    trans = np.asarray(m.regime_transition_matrix(pars, exog_tvtp=z))
    diag = np.array([[trans[j, j, min(t, trans.shape[2] - 1)] for j in range(k)]
                     for t in range(min(trans.shape[2], sm.shape[1]))])
    dmean = diag.mean(axis=0)[order]
    dvar = diag.std(axis=0)[order]
    boundary = bool(np.any(dmean > 1 - CLIP_TOL))
    half = [float(np.log(2) / max(1 - p, 1e-12)) for p in dmean]

    sd = float(np.sqrt(np.mean([varis[order[0]][0], varis[order[-1]][0]])))
    sep = float((means[order[-1]][0] - means[order[0]][0]) / sd) if sd > 0 else np.nan
    npar = k * y.shape[1] * 2 + (k * (k - 1) * (1 if z is None else z.shape[1]))
    bic = float(-2 * r.llf + npar * np.log(y.shape[0]))
    # does the transition actually MOVE with the covariate? (TVTP only)
    move = float(dvar.max()) if z is not None else 0.0
    return {"llf": float(r.llf), "occ": occ, "sep": sep, "bic": bic,
            "half": half, "boundary": boundary, "move": move,
            "xi": sm[order], "failed": None}


def show(tag, d):
    if d.get("failed"):
        print(f"{tag:>30}  FAILED: {d['failed']}"); return
    occ = "/".join(f"{x:.0%}" for x in d["occ"])
    hl = "BOUNDARY" if d["boundary"] else "/".join(f"{h:.0f}d" for h in d["half"])
    print(f"{tag:>30} {d['sep']:>7.2f} {occ:>14} {hl:>20} {d['move']:>8.4f} {d['bic']:>11.0f}")


async def main() -> int:
    dates, y = await load()
    rv = y[:, 0]
    zrv = (rv - rv.mean()) / rv.std()
    # covariate available at t-1 only: strictly causal transitions
    z = np.column_stack([np.ones(len(rv)), np.r_[0.0, zrv[:-1]]])
    print(f"observations: {len(dates)}  TVTP covariate: [1, lagged standardised RV]\n")

    print(f"{'model':>30} {'sep_sd':>7} {'occupancy':>14} {'half-lives':>20} "
          f"{'p_jj sd':>8} {'BIC':>11}")
    print("-" * 96)

    rng = np.random.default_rng(0)
    lab = np.concatenate([np.full(500, b) for b in (0, 2, 1, 0, 2, 1)])
    M = np.array([[0.8, 0.35, 0.10], [1.6, 0.55, 0.22], [3.2, 0.80, 0.45]])
    syn = M[lab] + rng.normal(scale=[0.18, 0.05, 0.03], size=(lab.size, 3))
    szrv = (syn[:, 0] - syn[:, 0].mean()) / syn[:, 0].std()
    sz = np.column_stack([np.ones(lab.size), np.r_[0.0, szrv[:-1]]])
    show("CONTROL synth 3-state const", fit(syn, 3))
    show("CONTROL synth 3-state TVTP", fit(syn, 3, sz))

    for k in (2, 3):
        show(f"real {k}-state constant", fit(y, k))
        show(f"real {k}-state TVTP (FR21)", fit(y, k, z))

    # fold stability of the best real TVTP fit
    print("\n[fold stability] real 3-state TVTP across chronological thirds")
    n = len(y)
    for i, (a, b) in enumerate([(0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n)]):
        d = fit(y[a:b], 3, z[a:b])
        if d.get("failed"):
            print(f"   fold {i+1}: FAILED"); continue
        print(f"   fold {i+1}: sep={d['sep']:.2f} occ={'/'.join(f'{x:.0%}' for x in d['occ'])} "
              f"{'BOUNDARY' if d['boundary'] else 'interior'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
