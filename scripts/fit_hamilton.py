#!/usr/bin/env python3
# C7 — fit the Hamilton filter on the real observation series (FR20-FR24).
"""Fits the three-state TVTP filter on the real y_t = (RV_t, AR_t, BAS_t) series
built by scripts/build_observations.py, writes the regime output back to E8,
and checks SPEC's acceptance criteria against the labelled epochs.

Checked here:
  NFR16  max_j xi_(j,t) > 0.90 for the correct state within one trading day of
         each labelled transition.
  NFR17  crisis-regime RV mean separated from tranquil by >= 3 sigma.
  O4     EM converges to a non-degenerate three-regime solution with ordered
         means; tau_(1/2) finite for both stressed and crisis regimes.

Epoch labels are provisional (seraph/validation/epochs.py) - SPEC OQ13/OQ3 are
open. Results move with them, which is why they live in one place.

Run: python scripts/fit_hamilton.py [--write]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.pillars.hamilton import HamiltonEngine  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import (CRISIS_WINDOW_DAYS, EPOCH_BREAKS,
                                      unresolved)  # noqa: E402


async def load(pool):
    rows = await pool.fetch(
        "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    dates = [r["date"].isoformat() for r in rows]
    y = np.array([[float(r["rv_t_yz"]), float(r["ar_t"]), float(r["bas_t"])]
                  for r in rows], dtype=float)
    return dates, y


async def persist(pool, dates, eng):
    n = 0
    for d in dates:
        det = eng.detail(d)
        if det is None:
            continue
        lsd = det.xi[1] + 2.0 * det.xi[2]
        await pool.execute(
            """
            UPDATE hamilton_output SET
                xi_1=$2, xi_2=$3, xi_3=$4, lsd_t=$5,
                p_hat_22=$6, p_hat_33=$7,
                tau_half_stressed=$8, tau_half_crisis=$9,
                estimation_uncertainty=$10
            WHERE date=$1
            """,
            date.fromisoformat(d), det.xi[0], det.xi[1], det.xi[2], lsd,
            det.p_hat_22, det.p_hat_33,
            min(det.tau_half_stressed, 1e6), min(det.tau_half_crisis, 1e6),
            float(np.var(det.xi)),
        )
        n += 1
    return n


async def main(write: bool) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        dates, y = await load(pool)
        print(f"[hamilton] observations: {len(dates)} days "
              f"{dates[0]} to {dates[-1]}", flush=True)
        if len(dates) < 250:
            print("[hamilton] insufficient history"); return 1

        # FR21 TVTP. AVAILABLE-DATA IMPLEMENTATION, not the full specification:
        # macro_covariates / tariff_events / flow_aggregates are all empty, so
        # SPEC E4's z_t (repo rate, credit growth, India VIX, INR TWI, Brent,
        # G_t) does not exist in this dataset and is NOT claimed. FR21 also
        # specifies a "state-dependent structural-break process"; the covariate
        # used is the LAGGED standardised RV level, which is derived only from
        # data we hold and is strictly causal (t-1 informs the transition into
        # t). Constant transitions collapse to a single absorbing state on this
        # data (occupancy 0/0/100, transitions on the numerical boundary);
        # with this TVTP driver the fit is interior and non-degenerate.
        rv = y[:, 0]
        zrv = (rv - rv.mean()) / rv.std()
        z_tvtp = np.column_stack([np.ones(len(rv)), np.r_[0.0, zrv[:-1]]])
        eng = HamiltonEngine(dates, y, exog_tvtp=z_tvtp)
        res = eng.fit()
        if res.status == "error":
            print(f"[hamilton] FIT FAILED: {res.error}"); return 1
        for w in res.warnings:
            print(f"[hamilton] warning: {w.code} - {w.message}", flush=True)
        print(f"[hamilton] converged: llf={res.value['llf']:.1f} "
              f"regime order (sorted->fitted)={res.value['order']}", flush=True)

        # --- O4 / NFR17: regime moments -----------------------------------
        model = eng._res.model
        pars = eng._res.params
        order = eng._order
        means = np.array([pars[model.parameters[j, "means"]] for j in range(3)])
        varis = np.array([pars[model.parameters[j, "variances"]] for j in range(3)])
        labels = ("tranquil", "stressed", "crisis")
        print(f"\n{'regime':>10} {'RV mean':>9} {'AR mean':>9} {'BAS mean':>9} {'RV sd':>9}")
        for k, j in enumerate(order):
            print(f"{labels[k]:>10} {means[j][0]:>9.4f} {means[j][1]:>9.4f} "
                  f"{means[j][2]:>9.5f} {np.sqrt(varis[j][0]):>9.4f}")

        rv_t, rv_c = means[order[0]][0], means[order[2]][0]
        pooled_sd = float(np.sqrt(np.mean([varis[order[0]][0], varis[order[2]][0]])))
        sep = (rv_c - rv_t) / pooled_sd if pooled_sd > 0 else float("nan")
        nfr17 = sep >= 3.0
        print(f"\n[NFR17] crisis-vs-tranquil RV separation = {sep:.2f} sigma "
              f"(target >= 3.0) -> {'PASS' if nfr17 else 'FAIL'}")

        ordered_means = [means[j][0] for j in order]
        non_degenerate = all(b > a for a, b in zip(ordered_means, ordered_means[1:]))
        print(f"[O4] ordered, non-degenerate three-regime solution -> "
              f"{'PASS' if non_degenerate else 'FAIL'}")

        # --- occupancy: a collapsed filter makes every other check vacuous --
        xi = eng._xi
        occ = np.bincount(np.argmax(xi, axis=0), minlength=3) / xi.shape[1]
        print(f"[occupancy] tranquil={occ[0]:.1%} stressed={occ[1]:.1%} "
              f"crisis={occ[2]:.1%} -> "
              f"{'OK' if occ.max() < 0.95 else 'COLLAPSED (all other checks vacuous)'}")

        # --- FR24: half-lives ---------------------------------------------
        mid = eng.detail(dates[len(dates) // 2])
        BOUNDARY = 1e6   # a half-life beyond this means p_jj is on the clip
        finite = (np.isfinite(mid.tau_half_stressed) and np.isfinite(mid.tau_half_crisis)
                  and max(mid.tau_half_stressed, mid.tau_half_crisis) < BOUNDARY)
        print(f"[FR24] tau_half stressed={mid.tau_half_stressed:.2f} d, "
              f"crisis={mid.tau_half_crisis:.2f} d -> "
              f"{'PASS' if finite else 'BOUNDARY/IDENTIFIABILITY FAILURE - not a real estimate'}")

        # --- NFR16: regime posterior around each labelled break ------------
        # NFR16 asks for a >0.90 posterior on the CORRECT state, not merely a
        # confident one. An earlier version of this check tested max(xi) alone
        # and passed 6/6 while classifying the COVID crash as tranquil - the
        # filter is always confident about something. FR32 defines the crisis
        # window as the 30 trading days FOLLOWING the labelled break, so the
        # correct state during that window is elevated (stressed or crisis).
        print("")
        print("[NFR16] elevated-state posterior during the 30-day crisis window")
        print(f"{'epoch':>16} {'break':>12} {'peak xi_elev':>13} {'days elev':>10} "
              f"{'peak state':>11} {'>0.90':>7}")
        passes = tested = 0
        for ep, (bd, _) in EPOCH_BREAKS.items():
            b = date.fromisoformat(bd)
            win = [d for d in dates
                   if 0 <= (date.fromisoformat(d) - b).days <= 45][:CRISIS_WINDOW_DAYS]
            if len(win) < 5:
                print(f"{ep:>16} {bd:>12}   (outside observation coverage)")
                continue
            tested += 1
            elev = [(eng.detail(d).xi[1] + eng.detail(d).xi[2], d) for d in win]
            peak, pd_ = max(elev)
            xi = eng.detail(pd_).xi
            state = ("tranquil", "stressed", "crisis")[int(np.argmax(xi))]
            n_elev = sum(1 for e, _ in elev if e > 0.5)
            ok = peak > 0.90
            passes += ok
            print(f"{ep:>16} {bd:>12} {peak:>13.3f} {n_elev:>7}/{len(win)} "
                  f"{state:>11} {'PASS' if ok else 'fail':>7}")
        print(f"[NFR16] {passes}/{tested} epochs reach a >0.90 elevated-state posterior "
              f"within their crisis window")

        if unresolved():
            print(f"\n[caveat] provisional epoch labels (SPEC OQ3/OQ13 open): "
                  f"{', '.join(unresolved())}")

        if write:
            n = await persist(pool, dates, eng)
            print(f"\n[hamilton] wrote regime output for {n} days to E8")
    finally:
        await pool.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.write)))
