#!/usr/bin/env python3
"""ISOLATED DIAGNOSTIC HARNESS - NOT PRODUCTION CODE, NOT A PILLAR WRITER.

Runs the EXISTING, UNMODIFIED `seraph.orchestration.hamilton_causal.walk_forward`
on the real NSE corpus and records causality + convergence diagnostics.

Boundaries honoured (operator's Option 3 decision):
  * persists NOTHING to hamilton_output or any production table;
  * imports and calls existing code only - no model, threshold or schema change;
  * reads ONLY the C4 OBSERVATION columns (rv_t_yz, ar_t, bas_t) from E8. Those
    are inputs produced by C4, NOT the leaky xi/regime outputs. The leaky xi is
    never read and never used as ground truth;
  * instrumentation is added by WRAPPING the fit function in THIS PROCESS only;
    nothing under seraph/ is edited.

Outputs land beside this file, clearly marked non-production.
"""
import asyncio
import json
import os
import sys
import time
import warnings

import asyncpg
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

from seraph.store.bootstrap import resolve_dsn
import seraph.orchestration.hamilton_causal as HC
from seraph.orchestration.hamilton_causal import (
    DEFAULT_INITIAL_TRAIN,
    DEFAULT_REFIT_EVERY,
    assert_causal,
    causal_tvtp_exog,
    walk_forward,
)
from seraph.pillars.hamilton.engine import K_REGIMES

DIAG = []
_real_fit = HC.fit_hamilton


def instrumented_fit(y, exog_tvtp=None, maxiter=200, **kw):
    """Wrap the real fit to record convergence, llf, transition block, boundary."""
    t0 = time.time()
    res, order, warns = _real_fit(y, exog_tvtp=exog_tvtp, maxiter=maxiter, **kw)
    el = time.time() - t0
    rec = {
        "n_train": int(np.asarray(y).shape[0]),
        "seconds": round(el, 1),
        "llf": float(res.llf),
        "order": [int(o) for o in order],
        "n_warnings": len(warns or []),
    }
    rv = getattr(res, "mle_retvals", {}) or {}
    rec["converged"] = bool(rv.get("converged", True)) if isinstance(rv, dict) else True
    rec["iterations"] = int(rv.get("iterations", -1)) if isinstance(rv, dict) else -1
    try:
        sl = res.model.parameters["regime_transition"]
        tp = np.ravel(np.asarray(res.params)[sl])
        rec["transition_params"] = [round(float(v), 6) for v in tp]
        rec["transition_absmax"] = round(float(np.max(np.abs(tp))), 6)
    except Exception as exc:
        rec["transition_params_error"] = repr(exc)
    try:
        rt = np.asarray(res.regime_transition)
        if rt.ndim == 3:
            off = rt.astype(float).copy()
            for i in range(min(rt.shape[0], rt.shape[1])):
                off[i, i, :] = np.nan
            rec["min_offdiag_transition"] = float(np.nanmin(off))
            rec["boundary_hit_1e6"] = bool(np.nanmin(off) < 1e-6)
    except Exception as exc:
        rec["regime_transition_error"] = repr(exc)
    DIAG.append(rec)
    mo = rec.get("min_offdiag_transition", float("nan"))
    print(
        "    [fit] n=%d llf=%.2f conv=%s min_offdiag=%.3e (%.0fs)"
        % (rec["n_train"], rec["llf"], rec["converged"], mo, el),
        flush=True,
    )
    return res, order, warns


async def load():
    conn = await asyncpg.connect(resolve_dsn(), timeout=30)
    rows = await conn.fetch(
        "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    await conn.close()
    return rows


def main():
    rows = asyncio.run(load())
    dates = [str(r["date"]) for r in rows]
    y = np.array(
        [[float(r["rv_t_yz"]), float(r["ar_t"]), float(r["bas_t"])] for r in rows])
    n = len(dates)
    print("INPUT  : %d obs  %s .. %s  cols=(rv_t_yz, ar_t, bas_t)" % (n, dates[0], dates[-1]))
    print("         finite=%s   (leaky xi columns NOT read)" % np.isfinite(y).all())

    exog = causal_tvtp_exog(y[:, 0])
    print("CONFIG : initial_train=%d refit_every=%d K=%d exog=%s"
          % (DEFAULT_INITIAL_TRAIN, DEFAULT_REFIT_EVERY, K_REGIMES, exog.shape))

    # ---- CHECK A: the FR21 driver uses no future moments -------------------
    full_z = (y[:, 0] - y[:, 0].mean()) / y[:, 0].std()
    causal_z = exog[1:, 1]
    print("\nCHECK A  causal exog is not the full-sample z-score")
    print("  max|causal_z - full_sample_z[:-1]| = %.6f"
          % np.max(np.abs(causal_z - full_z[:-1])))
    prefix = causal_tvtp_exog(y[:3000, 0])
    print("  prefix stability: exog(y[:3000]) == exog_full[:3000] ? %s"
          % np.allclose(prefix, exog[:3000]))

    print("\nRUN    : walk_forward (existing code, unmodified; fit wrapped for diagnostics)")
    HC.fit_hamilton = instrumented_fit
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run = walk_forward(
            dates, y, exog_tvtp=exog,
            initial_train=DEFAULT_INITIAL_TRAIN,
            refit_every=DEFAULT_REFIT_EVERY, progress=True)
    el = time.time() - t0
    print("\nwalk_forward completed in %.1f min, %d blocks" % (el / 60, len(run.blocks)))

    # ---- CHECK B: the module's own structural invariant --------------------
    print("\nCHECK B  assert_causal (module's own invariant)")
    try:
        assert_causal(run)
        print("  PASS - no block's parameters saw its own emission window")
        ok_b = True
    except AssertionError as exc:
        print("  FAIL - %s" % exc)
        ok_b = False

    xi = run.xi
    pre = xi[:, : run.first_causal_index]
    post = xi[:, run.first_causal_index:]

    # ---- CHECK C: warm-up is absence, not a substituted prior --------------
    print("\nCHECK C  warm-up emits absence (NaN), never a prior")
    print("  all NaN before index %d : %s" % (run.first_causal_index, bool(np.isnan(pre).all())))
    print("  any NaN at/after  %d    : %s" % (run.first_causal_index, bool(np.isnan(post).any())))

    # ---- CHECK D: simplex validity on the causal span ---------------------
    sums = post.sum(axis=0)
    print("\nCHECK D  xi is a valid simplex on the causal span")
    print("  max|sum-1| = %.3e   min=%.6f max=%.6f"
          % (np.nanmax(np.abs(sums - 1.0)), np.nanmin(post), np.nanmax(post)))

    # ---- block schedule + fit diagnostics ---------------------------------
    print("\nBLOCK SCHEDULE AND FIT DIAGNOSTICS")
    hdr = ("%3s %8s %12s %12s %12s %12s %5s %9s %12s"
           % ("blk", "train_n", "train_last", "emit_first", "emit_last", "llf",
              "conv", "order", "min_offdiag"))
    print(hdr)
    print("-" * len(hdr))
    blocks_json = []
    for b, d in zip(run.blocks, DIAG):
        print("%3d %8d %12s %12s %12s %12.2f %5s %9s %12.3e"
              % (b.index, b.train_end, b.train_last_date, b.emit_first_date,
                 b.emit_last_date, b.llf, b.converged, str(b.order),
                 d.get("min_offdiag_transition", float("nan"))))
        blocks_json.append({
            "index": b.index, "train_start": b.train_start, "train_end": b.train_end,
            "emit_start": b.emit_start, "emit_end": b.emit_end,
            "train_first_date": b.train_first_date, "train_last_date": b.train_last_date,
            "emit_first_date": b.emit_first_date, "emit_last_date": b.emit_last_date,
            "llf": b.llf, "order": list(b.order), "converged": b.converged,
            "diag": d,
        })

    n_conv = sum(1 for b in run.blocks if b.converged)
    boundary = [d for d in DIAG if d.get("boundary_hit_1e6")]
    zero_tr = [d for d in DIAG if d.get("transition_absmax", 1.0) == 0.0]
    print("\nconverged blocks                                  : %d/%d" % (n_conv, len(run.blocks)))
    print("blocks with a transition prob < 1e-6 (near-absorbing): %d/%d" % (len(boundary), len(DIAG)))
    print("blocks whose transition block stayed EXACTLY zero    : %d/%d   <- AMENDMENT-05 2.1 defect signature"
          % (len(zero_tr), len(DIAG)))

    # ---- causal results (a NEW object, not comparable to smoothed) ---------
    lsd = run.lsd()
    var = run.variance()
    argmax = np.nanargmax(post, axis=0)
    occ = [float((argmax == k).mean()) for k in range(K_REGIMES)]
    print("\nCAUSAL RESULTS (new object - NOT comparable to the smoothed figures)")
    print("  causal span      : %s .. %s  (%d of %d days)"
          % (dates[run.first_causal_index], dates[-1], post.shape[1], n))
    print("  occupancy        : %.1f%% / %.1f%% / %.1f%%" % (occ[0] * 100, occ[1] * 100, occ[2] * 100))
    print("  (smoothed in-sample was 43.0/25.2/31.8 - DIFFERENT OBJECT, not a target)")
    print("  LSD_t            : mean=%.4f sd=%.4f range=[%.4f, %.4f]"
          % (np.nanmean(lsd), np.nanstd(lsd), np.nanmin(lsd), np.nanmax(lsd)))
    print("  FR23 variance    : mean=%.4f max=%.4f" % (np.nanmean(var), np.nanmax(var)))

    rv0 = y[run.first_causal_index:, 0]
    crisis = rv0[argmax == 2]
    tranquil = rv0[argmax == 0]
    sep = None
    if crisis.size > 1 and tranquil.size > 1:
        pooled = np.sqrt((crisis.var(ddof=1) + tranquil.var(ddof=1)) / 2.0)
        sep = float(abs(crisis.mean() - tranquil.mean()) / max(pooled, 1e-12))
        print("  NFR17 separation : %.3f sigma  (requires >= 3; NOT tuned)" % sep)
        print("    crisis RV mean=%.4f (n=%d)   tranquil RV mean=%.4f (n=%d)"
              % (crisis.mean(), crisis.size, tranquil.mean(), tranquil.size))

    out = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_obs": n, "date_first": dates[0], "date_last": dates[-1],
        "initial_train": DEFAULT_INITIAL_TRAIN, "refit_every": DEFAULT_REFIT_EVERY,
        "k_regimes": K_REGIMES, "wall_minutes": round(el / 60, 2),
        "check_B_assert_causal": ok_b,
        "check_C_warmup_all_nan": bool(np.isnan(pre).all()),
        "check_C_no_nan_after": bool(not np.isnan(post).any()),
        "check_D_max_simplex_dev": float(np.nanmax(np.abs(sums - 1.0))),
        "converged_blocks": n_conv, "n_blocks": len(run.blocks),
        "boundary_hit_blocks": len(boundary), "zero_transition_blocks": len(zero_tr),
        "causal_first_date": dates[run.first_causal_index],
        "causal_occupancy": occ, "nfr17_separation_sigma": sep,
        "blocks": blocks_json,
    }
    with open(os.path.join(HERE, "causal_run.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    np.savez_compressed(
        os.path.join(HERE, "causal_xi_NOT_PRODUCTION.npz"),
        dates=np.array(dates), xi=xi, lsd=lsd, variance=var,
        first_causal_index=run.first_causal_index)
    print("\nwrote causal_run.json and causal_xi_NOT_PRODUCTION.npz (diagnostic only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
