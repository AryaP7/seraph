#!/usr/bin/env python3
# C5 - production rolling-window length comparison (FR10/FR11, AMENDMENT-03).
"""Which trailing window should the PRODUCTION Hawkes kernel be refitted on?

`WINDOW_DAYS = 60` is a declared constant whose *value* was never validated:
AMENDMENT-03 selected the model family on three chronological folds spanning the
**whole corpus** (~85k-171k bars), not on 60-day windows. A spot check found the
branching ratio swinging 0.003-0.099 across five adjacent 60-day windows, against
the validated cross-fold CV of 2-4.1%. This script measures that properly.

**Selection rule, fixed in advance:** the window is chosen on stability,
identifiability, out-of-sample likelihood and computational feasibility.
It is explicitly NOT chosen for producing an `n` close to the validated 0.108 -
the large-sample validation result and the production rolling estimate are two
different objects and are reported separately (user directive 6).

Out-of-sample per-bar NLL is the comparable criterion: the in-sample NLL of a
longer window is not comparable to a shorter one, but the average NLL the fitted
kernel assigns to the *following* unseen days is.

Run: python scripts/compare_hawkes_windows.py [--points 24] [--windows 60,250,500]
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from scipy.special import gammaln  # noqa: E402

from seraph.pillars.hawkes import excitation_path, fit_discrete_hawkes  # noqa: E402

CACHE = r"C:/Users/Arlop/AppData/Local/Temp/p1_data.pkl"
BARS_PER_DAY = 75
OOS_DAYS = 5                     # unseen horizon scored after each window
BOUNDARY_SHIFT_DAYS = 5          # +/- shift used for the boundary-sensitivity probe
BOUNDARY_SUBSET = 8              # probe boundary sensitivity at this many points


def tod_profile_of(x, s, n_slots):
    tot = np.bincount(s, weights=x, minlength=n_slots)
    cnt = np.bincount(s, minlength=n_slots).astype(float)
    p = np.where(cnt > 0, tot / np.maximum(cnt, 1), x.mean())
    return p / max(p.mean(), 1e-12)


def oos_nll_per_bar(fit, counts, session_starts, tod_profile, tod_index):
    """Average NB negative log-likelihood per bar on unseen data.

    Comparable across window lengths: a longer training window cannot inflate
    this simply by having seen more data, because it is evaluated on the same
    held-out horizon.
    """
    x = np.asarray(counts, dtype=float)
    lam = np.maximum(excitation_path(x, session_starts, fit.mu, fit.alpha,
                                     fit.phi, tod_profile, tod_index), 1e-12)
    k = fit.dispersion
    val = -np.sum(gammaln(x + k) - gammaln(k) - gammaln(x + 1)
                  + k * np.log(k / (k + lam)) + x * np.log(lam / (k + lam)))
    return float(val) / max(x.size, 1)


def main(points: int, windows: list[int]) -> int:
    if not Path(CACHE).exists():
        print(f"cached bar series not found at {CACHE}\n"
              "It is built by scripts/diagnose_inar_session_handling.py. The "
              "production writer must rebuild this from intraday_bars instead "
              "of depending on a scratch pickle.")
        return 1
    D = pickle.load(open(CACHE, "rb"))
    N, tod, new_sess = D["N"], D["tod"], D["new_sess"]
    slots = np.unique(tod)
    si = np.searchsorted(slots, tod)
    n_bars = N.size
    print(f"[cmp] market-wide bar series: {n_bars:,} bars "
          f"(~{n_bars // BARS_PER_DAY:,} sessions)\n")

    oos_bars = OOS_DAYS * BARS_PER_DAY
    results: dict[int, dict] = {}

    for w_days in windows:
        w = w_days * BARS_PER_DAY
        if w + oos_bars >= n_bars:
            print(f"[cmp] window {w_days}d exceeds the corpus - skipped")
            continue
        # Evaluation points evenly spaced over the region where a full trailing
        # window AND an unseen horizon both exist.
        lo, hi = w, n_bars - oos_bars
        ends = np.linspace(lo, hi, points).astype(int)

        rows, unident, t0 = [], 0, time.perf_counter()
        for e in ends:
            tr = slice(e - w, e)
            prof = tod_profile_of(N[tr], si[tr], slots.size)
            f = fit_discrete_hawkes(N[tr], new_sess[tr], prof, si[tr])
            if f is None:
                unident += 1
                continue
            te = slice(e, e + oos_bars)
            rows.append({
                "alpha": f.alpha, "phi": f.phi, "n": f.branching_ratio,
                "k": f.dispersion, "converged": f.converged,
                "oos": oos_nll_per_bar(f, N[te], new_sess[te], prof, si[te]),
                "end": int(e),
            })
        elapsed = time.perf_counter() - t0

        # Boundary sensitivity: shift the window start by +/- BOUNDARY_SHIFT_DAYS
        # and measure how far n moves. A stable window should barely notice.
        shift = BOUNDARY_SHIFT_DAYS * BARS_PER_DAY
        probe = ends[:: max(1, len(ends) // BOUNDARY_SUBSET)][:BOUNDARY_SUBSET]
        deltas = []
        for e in probe:
            base = next((r["n"] for r in rows if r["end"] == int(e)), None)
            if base is None:
                continue
            for d in (-shift, shift):
                s2 = slice(e - w + d, e + d)
                if s2.start < 0 or s2.stop > n_bars:
                    continue
                p2 = tod_profile_of(N[s2], si[s2], slots.size)
                f2 = fit_discrete_hawkes(N[s2], new_sess[s2], p2, si[s2])
                if f2 is not None:
                    deltas.append(abs(f2.branching_ratio - base))

        if not rows:
            print(f"[cmp] window {w_days}d produced no identifiable fit")
            continue
        a = np.array([r["alpha"] for r in rows])
        p = np.array([r["phi"] for r in rows])
        nn = np.array([r["n"] for r in rows])
        oo = np.array([r["oos"] for r in rows])
        mts = nn / np.maximum(1.0 - nn, 1e-12)
        results[w_days] = {
            "fits": len(rows), "unident": unident,
            "alpha": a, "phi": p, "n": nn, "oos": oo, "mts": mts,
            "boundary": np.array(deltas) if deltas else np.array([np.nan]),
            "sec_per_fit": elapsed / max(len(rows) + unident, 1),
            "converged": sum(r["converged"] for r in rows),
        }
        print(f"[cmp] {w_days:>4}d window: {len(rows)} fits, {unident} unidentifiable, "
              f"{elapsed / max(len(rows)+unident,1):.2f} s/fit", flush=True)

    if not results:
        print("no usable results")
        return 1

    def cv(x):
        m = float(np.mean(x))
        return float(np.std(x) / abs(m)) if m else float("nan")

    print("\n" + "=" * 96)
    print("HAWKES PRODUCTION WINDOW COMPARISON")
    print("=" * 96)
    print(f"{'window':>8}{'fits':>6}{'unident':>9}{'n mean':>9}{'n sd':>9}"
          f"{'n CV':>8}{'a CV':>8}{'phi CV':>9}{'OOS NLL/bar':>13}{'s/fit':>8}")
    for w_days, r in results.items():
        print(f"{str(w_days)+'d':>8}{r['fits']:>6}{r['unident']:>9}"
              f"{r['n'].mean():>9.4f}{r['n'].std():>9.4f}{cv(r['n']):>8.3f}"
              f"{cv(r['alpha']):>8.3f}{cv(r['phi']):>9.3f}"
              f"{r['oos'].mean():>13.5f}{r['sec_per_fit']:>8.2f}")

    print(f"\n{'window':>8}{'n min':>9}{'n max':>9}{'n range':>10}"
          f"{'stationary':>12}{'converged':>11}{'|dn| boundary':>15}")
    for w_days, r in results.items():
        stat = float(((r["n"] > 0) & (r["n"] < 1)).mean())
        print(f"{str(w_days)+'d':>8}{r['n'].min():>9.4f}{r['n'].max():>9.4f}"
              f"{np.ptp(r['n']):>10.4f}{stat:>11.0%}"
              f"{r['converged']}/{r['fits']:>9}"
              f"{np.nanmedian(r['boundary']):>15.4f}")

    print(f"\n{'window':>8}{'MTS mean':>11}{'MTS sd':>10}{'MTS min':>10}{'MTS max':>10}"
          f"   (ungated n/(1-n); FR13 gate applied per-window in production)")
    for w_days, r in results.items():
        print(f"{str(w_days)+'d':>8}{r['mts'].mean():>11.4f}{r['mts'].std():>10.4f}"
              f"{r['mts'].min():>10.4f}{r['mts'].max():>10.4f}")

    print("\n" + "-" * 96)
    print("Daily-refit cost over the 2,862-session corpus, at the measured s/fit:")
    for w_days, r in results.items():
        print(f"   {w_days:>4}d window: {2862 * r['sec_per_fit'] / 60:7.1f} min")
    print("\nReference (NOT a target): the large-sample validation result is")
    print("alpha~0.0557, phi~0.4837, n~0.1079 on chronological folds of 85k-171k")
    print("bars. That is a different object from a rolling production estimate and")
    print("the window is not selected for proximity to it.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", type=int, default=24)
    ap.add_argument("--windows", type=str, default="60,250,500")
    a = ap.parse_args()
    raise SystemExit(main(a.points, [int(x) for x in a.windows.split(",")]))
