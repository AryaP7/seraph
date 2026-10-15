#!/usr/bin/env python3
"""STAGE 2 - ISOLATED DIAGNOSTIC HARNESS. NOT PRODUCTION CODE, NO PERSISTENCE.

Three tests the stage-1 run cannot answer on its own:

  2a  TRANSITION-BLOCK MOVEMENT.  Does the TVTP transition block actually move
      off its initial value?  Reproduces AMENDMENT-05 2.1 on real data by
      (i) calling statsmodels' own `_em_iteration` and measuring how far the
      transition slice moves versus the emission means, and (ii) fitting with
      restarts=0 so the default all-zeros start is the only start.

  2b  NESTING INVARIANT.  LL(full TVTP) >= LL(intercept-only TVTP), because the
      latter is the former with every slope set to zero. Restricted model uses
      exog[:, :1] (the constant column alone) -> 6 transition params against the
      full model's 12, so df = 6, which reproduces AMENDMENT-05's reported
      p-values. A NEGATIVE LR is arithmetically impossible at a true maximum and
      is the fold-3 anomaly signature.

  2c  TRUNCATION INVARIANCE.  The decisive empirical causality test: re-run
      walk_forward on y[:K] and require xi[:, :K] to be IDENTICAL to the full
      run's prefix. A filter that peeks at future data cannot pass this.

Writes only beside this file. Reads only C4 observation columns from E8.
"""
import asyncio
import json
import os
import sys
import time
import warnings

import asyncpg
import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

from seraph.store.bootstrap import resolve_dsn
from seraph.orchestration.hamilton_causal import (
    DEFAULT_INITIAL_TRAIN,
    DEFAULT_REFIT_EVERY,
    causal_tvtp_exog,
    walk_forward,
)
from seraph.pillars.hamilton.engine import (
    K_REGIMES,
    MultivariateTVTPHamilton,
    fit as fit_hamilton,
)

TRUNC_BLOCKS = 4          # 2000 + 4*252 = 3008 -> a clean block boundary
OUT = os.path.join(HERE, "stage2_results.json")


async def load():
    conn = await asyncpg.connect(resolve_dsn(), timeout=30)
    rows = await conn.fetch(
        "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    await conn.close()
    return rows


def save(res):
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2)


def main():
    rows = asyncio.run(load())
    dates = [str(r["date"]) for r in rows]
    y = np.array(
        [[float(r["rv_t_yz"]), float(r["ar_t"]), float(r["bas_t"])] for r in rows])
    exog = causal_tvtp_exog(y[:, 0])
    n = len(dates)
    print("INPUT : %d obs %s .. %s" % (n, dates[0], dates[-1]), flush=True)

    stage1 = json.load(open(os.path.join(HERE, "causal_run.json")))
    results = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "stage1_ref": stage1["generated_utc"]}

    # ================= 2a  TRANSITION-BLOCK MOVEMENT =====================
    print("\n" + "=" * 70)
    print("2a  DOES THE TVTP TRANSITION BLOCK MOVE OFF ITS INITIAL VALUE?")
    print("=" * 70, flush=True)
    m = MultivariateTVTPHamilton(y[:DEFAULT_INITIAL_TRAIN],
                                 exog_tvtp=exog[:DEFAULT_INITIAL_TRAIN],
                                 k_regimes=K_REGIMES)
    sp = np.asarray(m.start_params, dtype=float)
    tr_sl = m.parameters["regime_transition"]
    mu_sl = m.parameters["means"]
    print("  tvtp flag on model            : %s" % getattr(m, "tvtp", None))
    print("  transition slice size         : %d params" % np.asarray(sp[tr_sl]).size)
    print("  start_params transition block : max|.| = %.3e" % np.max(np.abs(sp[tr_sl])))

    a2 = {"start_transition_absmax": float(np.max(np.abs(sp[tr_sl])))}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p1 = np.asarray(m._em_iteration(sp), dtype=object)
        p1v = np.asarray(p1[0], dtype=float) if p1.ndim and np.ndim(p1[0]) else np.asarray(p1, dtype=float)
        d_tr = float(np.max(np.abs(np.asarray(p1v)[tr_sl] - sp[tr_sl])))
        d_mu = float(np.max(np.abs(np.asarray(p1v)[mu_sl] - sp[mu_sl])))
        print("  ONE EM ITERATION moves:")
        print("    transition block  : %.3e   <- AMENDMENT-05 2.1 predicts EXACTLY 0" % d_tr)
        print("    emission means    : %.3e" % d_mu)
        a2.update({"em_move_transition": d_tr, "em_move_means": d_mu,
                   "em_transition_frozen": bool(d_tr == 0.0)})
    except Exception as exc:
        print("  _em_iteration probe failed: %r" % exc)
        a2["em_probe_error"] = repr(exc)

    print("\n  fitting with restarts=0 (default all-zeros start is the ONLY start) ...", flush=True)
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r0, _, _ = fit_hamilton(y[:DEFAULT_INITIAL_TRAIN],
                                exog_tvtp=exog[:DEFAULT_INITIAL_TRAIN],
                                maxiter=200, restarts=0)
    tr0 = np.ravel(np.asarray(r0.params)[tr_sl])
    print("  restarts=0 : llf=%.2f  transition max|.|=%.3e  (%.0fs)"
          % (r0.llf, np.max(np.abs(tr0)), time.time() - t0))
    a2.update({"restarts0_llf": float(r0.llf),
               "restarts0_transition_absmax": float(np.max(np.abs(tr0))),
               "restarts0_transition_exactly_zero": bool(np.all(tr0 == 0.0))})
    b0 = stage1["blocks"][0]
    a2["multistart_llf_block0"] = b0["llf"]
    a2["multistart_gain_over_restarts0"] = b0["llf"] - float(r0.llf)
    print("  multi-start (stage 1 block 0): llf=%.2f  -> gain %.2f llf"
          % (b0["llf"], a2["multistart_gain_over_restarts0"]))
    results["stage2a_transition_movement"] = a2
    save(results)

    # ================= 2b  NESTING INVARIANT =============================
    print("\n" + "=" * 70)
    print("2b  NESTING: LL(full) >= LL(intercept-only), same sample, df=6")
    print("=" * 70, flush=True)
    hdr = "%3s %8s %12s %14s %14s %10s %11s %6s" % (
        "blk", "train_n", "train_last", "llf_full", "llf_restricted", "LR", "p(chi2,6)", "ok")
    print(hdr)
    print("-" * len(hdr), flush=True)
    nest = []
    for b in stage1["blocks"]:
        te = b["train_end"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rr, _, _ = fit_hamilton(y[:te], exog_tvtp=exog[:te, :1],
                                    maxiter=200)
        llf_r = float(rr.llf)
        llf_f = float(b["llf"])
        lr = 2.0 * (llf_f - llf_r)
        p = float(stats.chi2.sf(lr, 6)) if lr > 0 else float("nan")
        ok = lr >= 0.0
        print("%3d %8d %12s %14.2f %14.2f %10.2f %11.3g %6s"
              % (b["index"], te, b["train_last_date"], llf_f, llf_r, lr, p, ok),
              flush=True)
        nest.append({"index": b["index"], "train_end": te,
                     "train_last_date": b["train_last_date"],
                     "llf_full": llf_f, "llf_restricted": llf_r,
                     "lr": lr, "p_chi2_df6": p, "nesting_ok": bool(ok)})
        results["stage2b_nesting"] = nest
        save(results)
    viol = [x for x in nest if not x["nesting_ok"]]
    print("\n  nesting violations (LR < 0, impossible at a true maximum): %d/%d"
          % (len(viol), len(nest)))
    for v in viol:
        print("    block %d (train<=%s): LR=%.2f" % (v["index"], v["train_last_date"], v["lr"]))
    results["stage2b_violations"] = len(viol)
    save(results)

    # ================= 2c  TRUNCATION INVARIANCE =========================
    k = DEFAULT_INITIAL_TRAIN + TRUNC_BLOCKS * DEFAULT_REFIT_EVERY
    print("\n" + "=" * 70)
    print("2c  TRUNCATION INVARIANCE at K=%d (%s)" % (k, dates[k - 1]))
    print("=" * 70, flush=True)
    exog_t = causal_tvtp_exog(y[:k, 0])
    print("  exog(y[:K]) == exog_full[:K] ? %s" % np.allclose(exog_t, exog[:k]))
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_t = walk_forward(dates[:k], y[:k], exog_tvtp=exog_t,
                             initial_train=DEFAULT_INITIAL_TRAIN,
                             refit_every=DEFAULT_REFIT_EVERY, progress=True)
    print("  truncated run: %d blocks in %.1f min" % (len(run_t.blocks), (time.time() - t0) / 60))

    z = np.load(os.path.join(HERE, "causal_xi_NOT_PRODUCTION.npz"), allow_pickle=True)
    xi_full = z["xi"][:, :k]
    xi_tr = run_t.xi
    both = ~np.isnan(xi_full) & ~np.isnan(xi_tr)
    md = float(np.max(np.abs(xi_full[both] - xi_tr[both]))) if both.any() else float("nan")
    nan_match = bool((np.isnan(xi_full) == np.isnan(xi_tr)).all())
    print("  overlapping finite cells compared : %d" % int(both.sum()))
    print("  max |xi_full - xi_truncated|      : %.3e" % md)
    print("  NaN masks identical               : %s" % nan_match)
    exact = bool(md == 0.0)
    tol = bool(md < 1e-10)
    print("  VERDICT: bitwise identical=%s   within 1e-10=%s" % (exact, tol))
    llf_match = [(bf["llf"], bt.llf) for bf, bt in zip(stage1["blocks"][:len(run_t.blocks)], run_t.blocks)]
    print("  per-block llf (full vs truncated):")
    for i, (a, bb) in enumerate(llf_match):
        print("    block %d: %.4f vs %.4f  delta=%.3e" % (i, a, bb, abs(a - bb)))
    results["stage2c_truncation"] = {
        "K": k, "K_date": dates[k - 1],
        "exog_prefix_identical": bool(np.allclose(exog_t, exog[:k])),
        "cells_compared": int(both.sum()),
        "max_abs_xi_diff": md, "nan_masks_identical": nan_match,
        "bitwise_identical": exact, "within_1e-10": tol,
        "blocks_truncated": len(run_t.blocks),
        "per_block_llf": [{"block": i, "llf_full": a, "llf_trunc": bb,
                           "delta": abs(a - bb)} for i, (a, bb) in enumerate(llf_match)],
    }
    save(results)

    # ========== 2d  IS THE TRANSITION MATRIX PERSISTENTLY NEAR-ABSORBING? ==
    # Stage 1 records only min(off-diagonal) across all t, which cannot tell
    # "one extreme covariate day" from "absorbing throughout". Fit the full
    # model once on the whole sample and look at the DISTRIBUTION over time.
    print("\n" + "=" * 70)
    print("2d  TRANSITION-MATRIX DISTRIBUTION OVER TIME (absorbing or not?)")
    print("=" * 70, flush=True)
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rf, order_f, _ = fit_hamilton(y, exog_tvtp=exog, maxiter=200)
    print("  full-sample fit: llf=%.2f (%.0fs)" % (rf.llf, time.time() - t0))
    rt = np.asarray(rf.regime_transition, dtype=float)
    print("  regime_transition shape: %s" % (rt.shape,))
    d2 = {"full_sample_llf": float(rf.llf), "shape": list(rt.shape)}
    if rt.ndim == 3:
        k = min(rt.shape[0], rt.shape[1])
        off = rt.copy()
        for i in range(k):
            off[i, i, :] = np.nan
        per_t = np.nanmin(off.reshape(-1, rt.shape[-1]), axis=0)
        qs = [0, 1, 5, 25, 50, 75, 100]
        pv = np.nanpercentile(per_t, qs)
        print("  min off-diagonal transition probability, percentiles over t:")
        for q, v in zip(qs, pv):
            print("    p%-3d = %.3e" % (q, v))
        frac = float(np.mean(per_t < 1e-6))
        print("  fraction of dates with min off-diag < 1e-6 : %.4f" % frac)
        print("  (isolated extremes => small fraction; genuinely absorbing => near 1)")
        d2.update({"percentiles_q": qs,
                   "min_offdiag_percentiles": [float(v) for v in pv],
                   "fraction_dates_below_1e-6": frac})
        for i in range(k):
            pii = rt[i, i, :]
            print("    regime %d self-persistence p_ii: median=%.6f max=%.6f"
                  % (i, float(np.nanmedian(pii)), float(np.nanmax(pii))))
            d2["p%d%d_median" % (i, i)] = float(np.nanmedian(pii))
    tr_f = np.ravel(np.asarray(rf.params)[rf.model.parameters["regime_transition"]])
    print("  fitted transition params max|.| = %.6f" % float(np.max(np.abs(tr_f))))
    d2["fitted_transition_absmax"] = float(np.max(np.abs(tr_f)))
    d2["fitted_transition_params"] = [round(float(v), 6) for v in tr_f]
    d2["order"] = [int(o) for o in order_f]
    results["stage2d_transition_distribution"] = d2
    save(results)

    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
