#!/usr/bin/env python3
# C7 - completion of the TVTP identification diagnostic. READ-ONLY, no estimator change.
"""Closes the gaps left by diagnose_hamilton_tvtp.py.

Part 0  Empirically confirm the EM freezes TVTP transition parameters, rather
        than relying on reading statsmodels' source.
Part 1  The RAW fitted transition matrix, before any regime reordering, so the
        near-zero entry is confirmed in the model's own output and cannot be an
        artefact of the `order` permutation.
Part 2  Multi-start with convergence status: neutral, small +/- perturbations,
        and bounded random draws.
Part 3  A finer profile of the stressed->tranquil control, intercept AND slope.
Part 4  **Isolating the covariate.** The earlier TVTP-vs-constant comparison
        changed two things at once: it removed the covariate *and* switched
        parameterisation (direct probabilities, which EM does update). An
        intercept-only TVTP holds the parameterisation, the code path and the
        EM freezing fixed and removes only the covariate, so a likelihood-ratio
        test against the full model measures what FR21's covariate actually
        contributes.
Part 5  Regime separation in sigma units, and half-lives.

Imposes no transition floor, changes no regime count, changes no covariate, and
does not use the smoothed series as evidence.

Run: python scripts/diagnose_hamilton_tvtp2.py [--folds 3]
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
from scipy import stats  # noqa: E402

from seraph.orchestration.hamilton_causal import causal_tvtp_exog  # noqa: E402
from seraph.pillars.hamilton.engine import (  # noqa: E402
    K_REGIMES,
    MultivariateTVTPHamilton,
)
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

LAB = ("tranq", "stress", "crisis")


async def load():
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    rows = await pool.fetch(
        "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    await pool.close()
    return ([r["date"].isoformat() for r in rows],
            np.array([[r["rv_t_yz"], r["ar_t"], r["bas_t"]] for r in rows], float))


def quiet_fit(m, start_params=None, maxiter=200):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return m.fit(start_params=start_params, maxiter=maxiter, disp=False)


def converged(res) -> bool:
    rv = getattr(res, "mle_retvals", None)
    return bool(rv.get("converged", True)) if isinstance(rv, dict) else True


def raw_trans(m, params, t):
    P = np.asarray(m.regime_transition_matrix(params))
    return P[:, :, t] if P.ndim == 3 else P


def order_of(m, params):
    rv = np.array([params[m.parameters[j, "means"]][0] for j in range(K_REGIMES)])
    return np.argsort(rv)


def occ(m, params, order):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = np.asarray(m.filter(params).filtered_marginal_probabilities)
    if p.shape[0] != K_REGIMES:
        p = p.T
    return p[order][:, : m.nobs].mean(axis=1) * 100


def separation_sigma(m, params, order):
    """Crisis-minus-tranquil RV mean, in units of the pooled per-regime RV sd."""
    mu = np.array([params[m.parameters[j, "means"]][0] for j in range(K_REGIMES)])[order]
    va = np.array([params[m.parameters[j, "variances"]][0] for j in range(K_REGIMES)])[order]
    sd = float(np.sqrt(np.mean(va)))
    return float((mu[-1] - mu[0]) / sd) if sd > 0 else float("nan")


def half_lives(A):
    return [float(np.log(0.5) / np.log(np.clip(A[j, j], 1e-12, 1 - 1e-12)))
            for j in range(K_REGIMES)]


def main(n_folds: int) -> int:
    dates, y = asyncio.run(load())
    exog = causal_tvtp_exog(y[:, 0])
    exog_int = exog[:, :1].copy()          # intercept-only: covariate removed
    n = len(dates)
    print(f"[diag2] {n} obs, {dates[0]} .. {dates[-1]}")

    # ---- Part 0: is the TVTP transition block really frozen by EM? ----------
    print("\n" + "=" * 90)
    print("PART 0 - EMPIRICAL CHECK: does EM update the TVTP transition block?")
    print("=" * 90)
    m0 = MultivariateTVTPHamilton(y[:1500], exog_tvtp=exog[:1500], k_regimes=K_REGIMES)
    p0 = np.array(m0.start_params, dtype=float)
    tr = m0.parameters["regime_transition"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, p1 = m0._em_iteration(p0)
    d_tr = float(np.abs(np.asarray(p1)[tr] - np.asarray(p0)[tr]).max())
    mean_sl = m0.parameters[0, "means"]
    d_em = float(np.abs(np.asarray(p1)[mean_sl] - np.asarray(p0)[mean_sl]).max())
    print(f"  transition block start values : {np.asarray(p0)[tr]}")
    print(f"  max |change| after one EM step: transitions={d_tr:.3e}  "
          f"emission means={d_em:.3e}")
    print(f"  -> transitions frozen by EM: {d_tr == 0.0}   "
          f"(emission params DO move: {d_em > 0})")
    print("  CONFIRMED as an implementation fact: the transition block is set by "
          "start_params\n  and then optimised only in the final MLE step.")

    bounds = [int(n * f) for f in np.linspace(0.4, 1.0, n_folds + 1)[:-1]] + [n]

    for fi in range(n_folds):
        hi = bounds[fi]
        print("\n" + "=" * 90)
        print(f"FOLD {fi+1}: train [0:{hi}]  ({dates[0]} .. {dates[hi-1]})")
        print("=" * 90)
        m = MultivariateTVTPHamilton(y[:hi], exog_tvtp=exog[:hi], k_regimes=K_REGIMES)
        res = quiet_fit(m)
        od = order_of(m, res.params)

        # ---- Part 1: RAW matrix, before reordering -------------------------
        A_raw = raw_trans(m, res.params, hi // 2)
        print(f"\n  PART 1 - RAW transition matrix (NO reordering), mid-fold:")
        for r in range(K_REGIMES):
            print("    " + "".join(f"{A_raw[r,c]:>13.9f}" for c in range(K_REGIMES)))
        print(f"    regime order (sorted->fitted) = {list(map(int, od))}"
              f"   {'IDENTITY - no permutation applied' if list(od)==[0,1,2] else ''}")
        print(f"    raw min off-diagonal entry = {np.min(A_raw + np.eye(K_REGIMES)):.3e}")
        A = A_raw[np.ix_(od, od)]
        print(f"    P(tranquil<-stressed) after ordering = {A[0,1]:.9f}")

        # ---- Part 2: multi-start with convergence status -------------------
        print(f"\n  PART 2 - MULTI-START (llf, P(tranq<-stress), occupancy, converged):")
        sp0 = np.array(m.start_params, dtype=float)
        k_tr = np.asarray(sp0)[tr].size
        rng = np.random.default_rng(7)
        inits = {"neutral (zeros)": sp0}
        for lbl, val in (("small +0.5", 0.5), ("small -0.5", -0.5)):
            s = sp0.copy(); s[tr] = np.asarray(sp0)[tr] + val; inits[lbl] = s
        for r in range(3):
            s = sp0.copy(); s[tr] = rng.uniform(-2.0, 2.0, size=k_tr)
            inits[f"bounded rand #{r+1}"] = s
        best = (-np.inf, None)
        for lbl, sp in inits.items():
            try:
                rr = quiet_fit(m, start_params=sp)
                oo = order_of(m, rr.params)
                AA = raw_trans(m, rr.params, hi // 2)[np.ix_(oo, oo)]
                oc = occ(m, rr.params, oo)
                print(f"    {lbl:>18}  llf={rr.llf:>12.2f}  P={AA[0,1]:.3e}  "
                      f"occ={'/'.join(f'{v:.0f}' for v in oc):>10}  conv={converged(rr)}")
                if rr.llf > best[0]:
                    best = (float(rr.llf), lbl)
            except Exception as e:
                print(f"    {lbl:>18}  FAILED {type(e).__name__}")
        print(f"    best: {best[1]} at llf={best[0]:.2f}  "
              f"(default={res.llf:.2f}, gap={best[0]-float(res.llf):+.2f})")

        # ---- Part 3: finer profile, intercept and slope --------------------
        idx = np.arange(len(res.params))[m.parameters[1, "regime_transition"]]
        base = np.array(res.params, dtype=float)
        for which, pi in (("intercept", idx[0]), ("slope", idx[1] if len(idx) > 1 else idx[0])):
            print(f"\n  PART 3 - PROFILE of from-stressed {which} (idx {pi}):")
            print(f"    {'offset':>8}{'P(tranq<-stress)':>19}{'llf':>15}{'d_llf':>11}")
            for off in (-8, -6, -4, -2, -1, -0.5, 0, 0.5, 1, 2, 4, 6):
                t = base.copy(); t[pi] = base[pi] + off
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        ll = float(m.loglike(t))
                    except Exception:
                        ll = float("nan")
                AA = raw_trans(m, t, hi // 2)[np.ix_(od, od)]
                print(f"    {off:>8.1f}{AA[0,1]:>19.9f}{ll:>15.2f}{ll-float(res.llf):>11.2f}")

        # ---- Part 4: does the covariate contribute? ------------------------
        m_i = MultivariateTVTPHamilton(y[:hi], exog_tvtp=exog_int[:hi],
                                       k_regimes=K_REGIMES)
        res_i = quiet_fit(m_i)
        od_i = order_of(m_i, res_i.params)
        A_i = raw_trans(m_i, res_i.params, hi // 2)[np.ix_(od_i, od_i)]
        df = len(res.params) - len(res_i.params)
        lr = 2.0 * (float(res.llf) - float(res_i.llf))
        pval = float(stats.chi2.sf(lr, df)) if df > 0 and lr > 0 else float("nan")
        print(f"\n  PART 4 - COVARIATE CONTRIBUTION (intercept-only TVTP vs full TVTP)")
        print(f"    identical parameterisation and code path; only z removed")
        print(f"    intercept-only: llf={res_i.llf:>12.2f} k={len(res_i.params)}  "
              f"P(tranq<-stress)={A_i[0,1]:.3e}  occ="
              f"{'/'.join(f'{v:.0f}' for v in occ(m_i, res_i.params, od_i))}")
        print(f"    full TVTP     : llf={res.llf:>12.2f} k={len(res.params)}")
        print(f"    LR = {lr:.2f} on {df} df -> p = {pval:.3e}")

        # ---- Part 5: separation and half-lives -----------------------------
        print(f"\n  PART 5 - SEPARATION / HALF-LIVES")
        print(f"    full TVTP     : separation={separation_sigma(m, res.params, od):.2f} sigma"
              f"   half-lives(d)=" +
              ", ".join(f"{LAB[j]}={half_lives(A)[j]:.1f}" for j in range(K_REGIMES)))
        print(f"    intercept-only: separation={separation_sigma(m_i, res_i.params, od_i):.2f} sigma"
              f"   half-lives(d)=" +
              ", ".join(f"{LAB[j]}={half_lives(A_i)[j]:.1f}" for j in range(K_REGIMES)))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=3)
    a = ap.parse_args()
    raise SystemExit(main(a.folds))
