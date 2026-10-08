#!/usr/bin/env python3
# C7 - is the near-absorbing TVTP solution the data's, or the estimator's?
"""Diagnosis of P(tranquil | stressed) ~ 1.8e-9, on chronological folds.

The causal walk-forward filter locks into a single regime because the fitted
transition matrix has an effectively closed class {stressed, crisis}. Before
concluding anything about Pillar 3, this separates three explanations:

  (a) the likelihood genuinely prefers an absorbing chain on this data;
  (b) the transition block is unidentified, so the optimiser is free to run the
      relevant coefficient off to a boundary at no likelihood cost;
  (c) the optimiser reaches it from one particular start and would not from
      others.

Why this is a live concern rather than a formality: statsmodels' EM explicitly
does **not** update transition parameters under TVTP —

    # The EM with TVTP is not yet supported, just return the previous
    # iteration parameters

— so the whole transition block comes from a single numerical optimisation
started at `0.0` for every TVTP coefficient. A profile and a multi-start are
therefore the only evidence that the reported solution is the likelihood's
preference and not an artefact of that one path.

Nothing here tunes the model. No transition floor is imposed, the regime count
is untouched, and the smoothed in-sample series is not used as evidence.

Run: python scripts/diagnose_hamilton_tvtp.py [--folds 3] [--restarts 4]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.orchestration.hamilton_causal import causal_tvtp_exog  # noqa: E402
from seraph.pillars.hamilton.engine import (  # noqa: E402
    K_REGIMES,
    MultivariateTVTPHamilton,
)
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

LABELS = ("tranquil", "stressed", "crisis")


async def load():
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    rows = await pool.fetch(
        "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    await pool.close()
    return ([r["date"].isoformat() for r in rows],
            np.array([[r["rv_t_yz"], r["ar_t"], r["bas_t"]] for r in rows], float))


def build(y, exog):
    return MultivariateTVTPHamilton(y, exog_tvtp=exog, k_regimes=K_REGIMES)


def fit_quiet(model, start_params=None, maxiter=200):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return model.fit(start_params=start_params, maxiter=maxiter, disp=False)


def regime_order(model, params):
    rv = np.array([params[model.parameters[j, "means"]][0] for j in range(K_REGIMES)])
    return np.argsort(rv)


def trans_at(model, params, t, order):
    P = np.asarray(model.regime_transition_matrix(params))
    A = P[:, :, t] if P.ndim == 3 else P
    return A[np.ix_(order, order)]


def occupancy(model, params, order, kind="filtered"):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = model.filter(params) if kind == "filtered" else model.smooth(params)
    p = np.asarray(getattr(res, f"{kind}_marginal_probabilities"))
    if p.shape[0] != K_REGIMES:
        p = p.T
    return p[order] if p.shape[1] == model.nobs else p[order][:, : model.nobs]


def half_lives(A):
    """τ½ from the self-transition diagonal; inf when p ≥ 1."""
    out = []
    for j in range(K_REGIMES):
        p = float(np.clip(A[j, j], 1e-12, 1 - 1e-12))
        out.append(float(np.log(0.5) / np.log(p)))
    return out


def main(n_folds: int, restarts: int) -> int:
    dates, y = asyncio.run(load())
    exog = causal_tvtp_exog(y[:, 0])
    n = len(dates)
    print(f"[diag] {n} observations, {dates[0]} .. {dates[-1]}")
    print(f"[diag] EM does NOT update transition params under TVTP — every "
          f"transition estimate below comes from one lbfgs pass\n")

    bounds = [int(n * f) for f in np.linspace(0.4, 1.0, n_folds + 1)[:-1]] + [n]
    folds = [(0, bounds[i]) for i in range(n_folds)]

    for fi, (lo, hi) in enumerate(folds):
        print("=" * 92)
        print(f"FOLD {fi+1}: train [0:{hi}]  ({dates[0]} .. {dates[hi-1]})")
        print("=" * 92)
        m_tv = build(y[:hi], exog[:hi])
        res_tv = fit_quiet(m_tv)
        order = regime_order(m_tv, res_tv.params)
        A_mid = trans_at(m_tv, res_tv.params, hi // 2, order)

        print("  TVTP transition matrix at mid-fold (columns = from):")
        for r in range(K_REGIMES):
            print(f"    to {LABELS[r]:<9}" + "".join(f"{A_mid[r,c]:>10.6f}"
                                                     for c in range(K_REGIMES)))
        k_tv = len(res_tv.params)
        bic_tv = -2 * res_tv.llf + k_tv * np.log(hi)
        print(f"  llf={res_tv.llf:,.2f}  k={k_tv}  BIC={bic_tv:,.2f}")
        print(f"  half-lives (d): " + ", ".join(
            f"{LABELS[j]}={half_lives(A_mid)[j]:.1f}" for j in range(K_REGIMES)))

        occ_f = occupancy(m_tv, res_tv.params, order, "filtered").mean(axis=1) * 100
        print(f"  FILTERED occupancy: " + " / ".join(f"{v:.1f}" for v in occ_f))

        # --- (1) is the absorbing entry identified? profile it ---------------
        # Vary the from-stressed transition block and watch the likelihood.
        sl = m_tv.parameters[1, "regime_transition"]
        base = np.array(res_tv.params, dtype=float)
        idx = np.arange(len(base))[sl]
        print(f"\n  PROFILE of the from-stressed transition block "
              f"(param idx {list(idx)}), holding all else fixed:")
        print(f"    {'offset':>8}{'P(tranq|stress)':>18}{'llf':>16}{'d_llf':>12}")
        ll0 = float(res_tv.llf)
        for off in (-6.0, -3.0, -1.0, 0.0, 1.0, 3.0, 6.0):
            trial = base.copy()
            trial[idx[0]] = base[idx[0]] + off      # intercept of to-tranquil row
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    ll = float(m_tv.loglike(trial))
                except Exception:
                    ll = float("nan")
            A = trans_at(m_tv, trial, hi // 2, order)
            print(f"    {off:>8.1f}{A[0,1]:>18.8f}{ll:>16.2f}{ll-ll0:>12.2f}")

        # --- (2) does a different start reach a different optimum? -----------
        print(f"\n  MULTI-START ({restarts} defensible inits):")
        print(f"    {'init':>22}{'P(tranq|stress)':>18}{'llf':>16}{'occupancy':>22}")
        rng = np.random.default_rng(0)
        sp0 = np.array(m_tv.start_params, dtype=float)
        tr_slice = m_tv.parameters["regime_transition"]
        inits = {"default (zeros)": sp0}
        for r in range(restarts - 1):
            sp = sp0.copy()
            sp[tr_slice] = rng.normal(0.0, 1.5, size=np.array(sp0)[tr_slice].size)
            inits[f"perturbed #{r+1}"] = sp
        for lbl, sp in inits.items():
            try:
                rr = fit_quiet(m_tv, start_params=sp)
                oo = regime_order(m_tv, rr.params)
                AA = trans_at(m_tv, rr.params, hi // 2, oo)
                oc = occupancy(m_tv, rr.params, oo, "filtered").mean(axis=1) * 100
                print(f"    {lbl:>22}{AA[0,1]:>18.8f}{rr.llf:>16.2f}"
                      f"{'/'.join(f'{v:.0f}' for v in oc):>22}")
            except Exception as e:
                print(f"    {lbl:>22}  failed: {type(e).__name__}")

        # --- (3) TVTP vs constant transitions --------------------------------
        m_c = build(y[:hi], None)
        res_c = fit_quiet(m_c)
        order_c = regime_order(m_c, res_c.params)
        A_c = trans_at(m_c, res_c.params, 0, order_c)
        k_c = len(res_c.params)
        bic_c = -2 * res_c.llf + k_c * np.log(hi)
        occ_c = occupancy(m_c, res_c.params, order_c, "filtered").mean(axis=1) * 100
        print(f"\n  CONSTANT-TRANSITION comparison:")
        print(f"    llf={res_c.llf:,.2f}  k={k_c}  BIC={bic_c:,.2f}  "
              f"(TVTP BIC {bic_tv:,.2f}; lower is better)")
        print(f"    P(tranq|stress)={A_c[0,1]:.8f}   filtered occupancy="
              f"{'/'.join(f'{v:.0f}' for v in occ_c)}")

        # --- (4) OOS: does either generalise forward? ------------------------
        if hi < n:
            test_hi = min(hi + 252, n)
            for lbl, ex, params in (("TVTP", exog, res_tv.params),
                                    ("CONST", None, res_c.params)):
                m_ext = build(y[:test_hi], None if ex is None else ex[:test_hi])
                m_in = build(y[:hi], None if ex is None else ex[:hi])
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    ll_ext = float(m_ext.loglike(params))
                    ll_in = float(m_in.loglike(params))
                oos = -(ll_ext - ll_in) / (test_hi - hi)
                oo = regime_order(m_ext, params)
                occ_o = occupancy(m_ext, params, oo, "filtered")[:, hi:test_hi]
                uq = np.unique(occ_o.round(6), axis=1).shape[1]
                print(f"    [{lbl:5s}] OOS NLL/obs over next {test_hi-hi} days = "
                      f"{oos:.5f}   distinct xi = {uq}/{test_hi-hi}   "
                      f"occ={'/'.join(f'{v:.0f}' for v in occ_o.mean(axis=1)*100)}")
        print()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--restarts", type=int, default=4)
    a = ap.parse_args()
    raise SystemExit(main(a.folds, a.restarts))
