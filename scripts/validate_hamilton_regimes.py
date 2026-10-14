#!/usr/bin/env python3
# C7 — regime-support validation (FR20, FR21, FR24, NFR16, NFR17, O4)
"""Does the real NSE feature space support 2 regimes, 3 regimes, or neither?

### Why this supersedes `diagnose_hamilton_regimes.py`

That script answered the question with one full-sample table. It was right to
ask, but a single fit cannot distinguish a genuine regime structure from a
smooth series cut into arbitrary pieces, and it had no way to tell whether its
own procedure worked. Run before the C7 fix it reported *every* real
configuration collapsing to 0%/100% on the optimiser boundary, which was an
artefact of a defect in `_conditional_loglikelihoods` (see that method's
docstring) and not a property of the data.

So this script validates the **procedure** before it reports a verdict, and
then stresses the verdict across folds, initialisations and controls.

### The controls, and why there are three

* `SYN-K2` / `SYN-K3` — Markov-generated at the real corpus's own scale, with
  known means, variances, transition matrices and state paths. These establish
  that the procedure can recover a known answer. The previous positive control
  used six deterministic 500-day blocks — about five switches in 3,000 days —
  which is far easier than any real market and passed even while the estimator
  was broken.
* `NEG-iid` — i.i.d. draws at the real marginal moments. No regimes, no
  persistence. The procedure must reject it.
* `NEG-ar1` — **the decisive control.** A single-regime vector AR(1) matched to
  the real data's lag-1 autocorrelation (0.997 for RV), marginal moments and
  contemporaneous innovation covariance. It is exactly as smooth as the real
  series and contains exactly one regime. If a 3-state fit on `NEG-ar1` looks
  like the 3-state fit on real data, then the real "regimes" are an artefact of
  smoothness and nothing more. This is the control that can actually falsify a
  positive real-data result.

### PRE-REGISTERED CRITERIA — written before the real-data run

A verdict of "K regimes are SUPPORTED" requires all of R1-R9. Each is reported
PASS/FAIL individually; a failure is reported as a failure, never softened into
a caveat, and no threshold here is to be adjusted after seeing a result.

    R1 PROCEDURE VALIDITY   on SYN-K{2,3}: occupancy within 5pp of truth,
                            transition diagonal within 0.02, state-path
                            accuracy >= 0.95, and BIC picks the true K.
    R2 NEGATIVE CONTROL     on NEG-iid AND NEG-ar1, the K-state fit must FAIL
                            at least one of R3/R4/R8. A control that passes
                            everything invalidates the real-data verdict.
    R3 NON-DEGENERACY       min occupancy >= 10% of the sample.
    R4 IDENTIFIABILITY      no transition diagonal within 1e-6 of 1.0; every
                            half-life finite and within [5, 2000] trading days.
    R5 SEPARATION (NFR17)   >= 3.0 sigma between the extreme regimes' RV means.
    R6 FOLD STABILITY       R3 and R4 hold in >= 5 of 6 chronological folds.
    R7 INIT ROBUSTNESS      over 8 seeds, >= 50% of converged starts reproduce
                            the best-llf occupancy vector to within 5pp.
    R8 LABEL STABILITY      median regime run-length >= 5 trading days. A state
                            that flips every other day is not a daily filter.
    R9 MODEL SELECTION      BIC prefers K over the other state counts tried.

R5 is the SPEC's own acceptance threshold and is kept at 3.0 sigma regardless
of what the data turns out to show. R10 (causal survival under walk-forward
refitting) is measured by the separate causal harness, not here.

Run: python scripts/validate_hamilton_regimes.py [--stage N] [--quick]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import warnings
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.pillars.hamilton.engine import fit as engine_fit  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

CLIP_TOL = 1e-6
MIN_OCC = 0.10
HALF_LIFE_RANGE = (5.0, 2000.0)
NFR17_SIGMA = 3.0
MIN_RUN_LEN = 5.0
N_FOLDS = 6
N_SEEDS = 8

#: FR32 break dates, for the in-sample interpretability cross-tab in stage 6.
EPOCH_BREAKS = {
    "gfc_2008": "2008-09-15", "taper_2013": "2013-05-22",
    "ilfs_2018": "2018-09-21", "covid_2020": "2020-02-20",
    "tightening_2022": "2022-01-05", "tariff_2026": "2026-04-02",
}


def assess(y, k, *, restarts=4, seed=0, true_lab=None, true_diag=None,
           true_occ=None):
    """Fit a k-state filter and return every diagnostic the criteria need."""
    y = np.asarray(y, dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res, order, _ = engine_fit(y, k_regimes=k, restarts=restarts, seed=seed)
        except Exception as e:                        # noqa: BLE001
            return {"failed": f"{type(e).__name__}: {e}"[:70]}
    m = res.model
    p = res.params
    means = np.array([p[m.parameters[j, "means"]] for j in range(k)])
    varis = np.array([p[m.parameters[j, "variances"]] for j in range(k)])

    sm = np.asarray(res.smoothed_marginal_probabilities)
    if sm.shape[0] != k:
        sm = sm.T
    sm = sm[:, :y.shape[0]]
    lab_raw = np.argmax(sm, axis=0)
    occ = np.bincount(lab_raw, minlength=k)[order] / lab_raw.size

    trans = np.asarray(m.regime_transition_matrix(p))[:, :, 0]
    diag = np.array([trans[j, j] for j in range(k)])[order]
    boundary = bool(np.any(diag > 1 - CLIP_TOL))
    half = np.array([np.log(2) / max(1 - d, 1e-12) for d in diag])

    rank = np.empty(k, dtype=int)
    for r, idx in enumerate(order):
        rank[idx] = r
    lab = rank[lab_raw]                               # 0 = tranquil ... k-1 = crisis

    runs, start = [], 0
    for i in range(1, lab.size + 1):
        if i == lab.size or lab[i] != lab[start]:
            runs.append(i - start)
            start = i
    median_run = float(np.median(runs)) if runs else 0.0

    sd = float(np.sqrt(np.mean([varis[order[0]][0], varis[order[-1]][0]])))
    sep = float((means[order[-1]][0] - means[order[0]][0]) / sd) if sd > 0 else np.nan

    n_par = k * y.shape[1] * 2 + k * (k - 1)
    conv = (getattr(res, "mle_retvals", {}) or {})
    out = {
        "failed": None, "k": k, "llf": float(res.llf), "occ": occ, "sep": sep,
        "diag": diag, "half": half, "boundary": boundary,
        "median_run": median_run, "n_runs": len(runs), "lab": lab,
        "means": means[order], "nobs": int(y.shape[0]), "n_par": n_par,
        "bic": float(-2 * res.llf + n_par * np.log(y.shape[0])),
        "aic": float(-2 * res.llf + 2 * n_par),
        "converged": bool(conv.get("converged", True)),
    }
    out["R3"] = bool(occ.min() >= MIN_OCC)
    out["R4"] = bool((not boundary) and np.all(np.isfinite(half))
                     and np.all(half >= HALF_LIFE_RANGE[0])
                     and np.all(half <= HALF_LIFE_RANGE[1]))
    out["R5"] = bool(np.isfinite(sep) and sep >= NFR17_SIGMA)
    out["R8"] = bool(median_run >= MIN_RUN_LEN)
    if true_lab is not None:
        out["path_acc"] = float(np.mean(lab == true_lab))
    if true_occ is not None:
        out["occ_dev"] = float(np.max(np.abs(occ - np.asarray(true_occ))))
    if true_diag is not None:
        out["diag_dev"] = float(np.max(np.abs(diag - np.asarray(true_diag))))
    return out


def line(tag, d, extra=""):
    if d.get("failed"):
        print(f"{tag:>30}  FAILED: {d['failed']}", flush=True)
        return
    flags = "".join(("." if d[r] else "X") for r in ("R3", "R4", "R5", "R8"))
    occ = "/".join(f"{x:.0%}" for x in d["occ"])
    hl = "BOUNDARY" if d["boundary"] else "/".join(f"{h:.0f}" for h in d["half"])
    print(f"{tag:>30} {d['k']:>2} {d['llf']:>10.1f} {d['sep']:>6.2f} {occ:>20} "
          f"{hl:>20} {d['median_run']:>6.0f} {d['bic']:>10.0f} {flags:>6} "
          f"{str(d['converged'])[0]:>2}{extra}", flush=True)


def header():
    print(f"{'case':>30} {'k':>2} {'llf':>10} {'sep':>6} {'occupancy':>20} "
          f"{'half-lives (d)':>20} {'medrun':>6} {'BIC':>10} {'3458':>6} {'c':>2}")
    print("-" * 128, flush=True)


def make_markov(k, n, mu, sd, p_mat, seed):
    rng = np.random.default_rng(seed)
    s, lab = 0, []
    for _ in range(n):
        lab.append(s)
        s = rng.choice(k, p=p_mat[s])
    lab = np.array(lab)
    return mu[lab] + rng.normal(scale=sd, size=(n, mu.shape[1])), lab


def make_ar1_surrogate(y, seed):
    """One-regime VAR(1)-style surrogate: same persistence, same marginal
    moments, same contemporaneous innovation covariance, NO regimes."""
    rng = np.random.default_rng(seed)
    n, kc = y.shape
    mu, sd = y.mean(axis=0), y.std(axis=0)
    z = (y - mu) / sd
    phi = np.array([np.corrcoef(z[:-1, j], z[1:, j])[0, 1] for j in range(kc)])
    eps = z[1:] - phi * z[:-1]
    chol = np.linalg.cholesky(np.cov(eps.T) + 1e-12 * np.eye(kc))
    out = np.zeros((n, kc))
    out[0] = z[0]
    draws = rng.normal(size=(n, kc)) @ chol.T
    for t in range(1, n):
        out[t] = phi * out[t - 1] + draws[t]
    return out * sd + mu, phi


async def load():
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        rows = await pool.fetch(
            "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
        return ([str(r["date"]) for r in rows],
                np.array([[float(r["rv_t_yz"]), float(r["ar_t"]), float(r["bas_t"])]
                          for r in rows]))
    finally:
        await pool.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, action="append", default=None)
    ap.add_argument("--quick", action="store_true", help="restarts=1")
    a = ap.parse_args()
    stages = set(a.stage) if a.stage else {1, 2, 3, 4, 5, 6}
    nrs = 1 if a.quick else 4

    dates, y = asyncio.run(load())
    n = len(dates)
    print(f"real corpus: {n:,} days  {dates[0]} .. {dates[-1]}\n", flush=True)
    verdict: dict[str, object] = {}

    mu2 = np.array([[0.42, 0.38, 0.0040], [0.72, 0.47, 0.0072]])
    sd2 = np.array([0.055, 0.022, 0.0007])
    pm2 = np.array([[0.98, 0.02], [0.04, 0.96]])
    mu3 = np.array([[0.40, 0.37, 0.0038], [0.56, 0.42, 0.0055], [0.85, 0.50, 0.0082]])
    sd3 = np.array([0.050, 0.020, 0.0006])
    pm3 = np.array([[0.975, 0.020, 0.005], [0.030, 0.950, 0.020],
                    [0.010, 0.040, 0.950]])
    y2, l2 = make_markov(2, n, mu2, sd2, pm2, 7)
    y3, l3 = make_markov(3, n, mu3, sd3, pm3, 11)
    occ2 = np.bincount(l2) / n
    occ3 = np.bincount(l3) / n

    if 1 in stages:
        print("=== STAGE 1 - R1 PROCEDURE VALIDITY (known ground truth) ===")
        header()
        d2 = assess(y2, 2, restarts=nrs, true_lab=l2, true_diag=np.diag(pm2),
                    true_occ=occ2)
        line("SYN-K2 fitted k=2", d2,
             f"  occ_dev={d2.get('occ_dev', float('nan')):.3f}"
             f" diag_dev={d2.get('diag_dev', float('nan')):.3f}"
             f" path={d2.get('path_acc', float('nan')):.4f}")
        r1a = (d2.get("occ_dev", 9) <= 0.05 and d2.get("diag_dev", 9) <= 0.02
               and d2.get("path_acc", 0) >= 0.95)
        d3 = assess(y3, 3, restarts=nrs, true_lab=l3, true_diag=np.diag(pm3),
                    true_occ=occ3)
        line("SYN-K3 fitted k=3", d3,
             f"  occ_dev={d3.get('occ_dev', float('nan')):.3f}"
             f" diag_dev={d3.get('diag_dev', float('nan')):.3f}"
             f" path={d3.get('path_acc', float('nan')):.4f}")
        r1b = (d3.get("occ_dev", 9) <= 0.05 and d3.get("diag_dev", 9) <= 0.02
               and d3.get("path_acc", 0) >= 0.95)
        bic2 = {kk: assess(y2, kk, restarts=nrs)["bic"] for kk in (2, 3)}
        bic3 = {kk: assess(y3, kk, restarts=nrs)["bic"] for kk in (2, 3)}
        print(f"\n  BIC on SYN-K2 (true k=2): k2={bic2[2]:,.0f}  k3={bic2[3]:,.0f}"
              f"  -> picks k={min(bic2, key=bic2.get)}")
        print(f"  BIC on SYN-K3 (true k=3): k2={bic3[2]:,.0f}  k3={bic3[3]:,.0f}"
              f"  -> picks k={min(bic3, key=bic3.get)}")
        r1c = min(bic2, key=bic2.get) == 2 and min(bic3, key=bic3.get) == 3
        verdict["R1"] = bool(r1a and r1b and r1c)
        print(f"\n  R1 PROCEDURE VALIDITY: {'PASS' if verdict['R1'] else 'FAIL'}"
              f"   (recovery k2={r1a} k3={r1b}, BIC picks true K={r1c})", flush=True)

    if 2 in stages:
        print("\n=== STAGE 2 - R2 NEGATIVE CONTROLS (must be rejected) ===")
        rng = np.random.default_rng(23)
        y_iid = y.mean(axis=0) + rng.normal(scale=y.std(axis=0), size=y.shape)
        y_ar1, phi = make_ar1_surrogate(y, 29)
        real_ac = [np.corrcoef(y[:-1, j], y[1:, j])[0, 1] for j in range(3)]
        got_ac = [np.corrcoef(y_ar1[:-1, j], y_ar1[1:, j])[0, 1] for j in range(3)]
        print(f"  real lag-1 autocorr    : {np.round(real_ac, 4)}")
        print(f"  NEG-ar1 achieved       : {np.round(got_ac, 4)}", flush=True)
        header()
        neg = {}
        for nm, yy in (("NEG-iid", y_iid), ("NEG-ar1 (smooth, 1 regime)", y_ar1)):
            for kk in (2, 3):
                d = assess(yy, kk, restarts=nrs)
                line(nm, d)
                neg[(nm, kk)] = d
        rejected = {key: not (d["R3"] and d["R4"] and d["R8"])
                    for key, d in neg.items() if not d.get("failed")}
        verdict["R2"] = all(rejected.values())
        print(f"\n  R2 NEGATIVE CONTROL: {'PASS' if verdict['R2'] else 'FAIL'}")
        for key, okf in rejected.items():
            d = neg[key]
            print(f"    {key[0]:>28} k={key[1]}  rejected={okf}  "
                  f"(R3={d['R3']} R4={d['R4']} R8={d['R8']} sep={d['sep']:.2f})",
                  flush=True)

    real = {}
    if 3 in stages:
        print("\n=== STAGE 3 - real corpus, full sample, R3/R4/R5/R8/R9 ===")
        header()
        for kk in (2, 3, 4):
            d = assess(y, kk, restarts=nrs)
            line("real RV+AR+BAS", d)
            real[kk] = d
        bics = {kk: real[kk]["bic"] for kk in real if not real[kk].get("failed")}
        best = min(bics, key=bics.get)
        print("\n  BIC: " + "  ".join(f"k{kk}={bics[kk]:,.0f}" for kk in sorted(bics))
              + f"   -> R9 prefers k={best}")
        verdict["R9_best_k"] = int(best)
        for kk in sorted(real):
            d = real[kk]
            if d.get("failed"):
                continue
            print(f"    k={kk}: R3={'PASS' if d['R3'] else 'FAIL'} "
                  f"R4={'PASS' if d['R4'] else 'FAIL'} "
                  f"R5={'PASS' if d['R5'] else 'FAIL'} (sep {d['sep']:.2f}s) "
                  f"R8={'PASS' if d['R8'] else 'FAIL'} (medrun {d['median_run']:.0f}d)",
                  flush=True)

    if 4 in stages:
        print(f"\n=== STAGE 4 - R6 FOLD STABILITY ({N_FOLDS} chronological blocks) ===")
        edges = np.linspace(0, n, N_FOLDS + 1).astype(int)
        for kk in (2, 3):
            print(f"\n  k={kk}")
            header()
            okc = 0
            for f in range(N_FOLDS):
                lo, hi = edges[f], edges[f + 1]
                d = assess(y[lo:hi], kk, restarts=nrs)
                line(f"fold{f} {dates[lo][:7]}..{dates[hi - 1][:7]}", d)
                if not d.get("failed") and d["R3"] and d["R4"]:
                    okc += 1
            verdict[f"R6_k{kk}"] = f"{okc}/{N_FOLDS}"
            print(f"    R6 k={kk}: {okc}/{N_FOLDS} folds satisfy R3+R4 - "
                  f"{'PASS' if okc >= 5 else 'FAIL'}", flush=True)

    if 5 in stages:
        print(f"\n=== STAGE 5 - R7 INIT ROBUSTNESS ({N_SEEDS} seeds, k=3) ===")
        runs = []
        for s in range(N_SEEDS):
            d = assess(y, 3, restarts=1, seed=s)
            if d.get("failed"):
                print(f"    seed {s}: FAILED {d['failed']}", flush=True)
                continue
            runs.append(d)
            print(f"    seed {s}: llf={d['llf']:>10.1f} sep={d['sep']:>5.2f} "
                  f"occ={'/'.join(f'{x:.0%}' for x in d['occ']):>18} "
                  f"medrun={d['median_run']:>4.0f}d conv={d['converged']}", flush=True)
        if runs:
            best = max(runs, key=lambda r: r["llf"])
            agree = sum(1 for r in runs
                        if np.max(np.abs(r["occ"] - best["occ"])) <= 0.05)
            lls = np.array([r["llf"] for r in runs])
            verdict["R7"] = bool(agree / len(runs) >= 0.5)
            verdict["R7_detail"] = (f"{agree}/{len(runs)} within 5pp; "
                                    f"llf spread {lls.max() - lls.min():.2f}")
            print(f"\n    best llf {best['llf']:.1f};  {agree}/{len(runs)} starts "
                  f"reproduce its occupancy within 5pp;  llf spread "
                  f"{lls.max() - lls.min():.2f}")
            print(f"    R7 INIT ROBUSTNESS: {'PASS' if verdict['R7'] else 'FAIL'}",
                  flush=True)

    if 6 in stages and real.get(3) and not real[3].get("failed"):
        print("\n=== STAGE 6 - economic interpretation (IN-SAMPLE, descriptive) ===")
        lab = real[3]["lab"]
        idx = {d: i for i, d in enumerate(dates)}
        print(f"  fitted RV means by state: {np.round(real[3]['means'][:, 0], 4)}")
        print(f"  state occupancy overall : "
              f"{'/'.join(f'{x:.1%}' for x in real[3]['occ'])}")
        print(f"\n  {'epoch':>18} {'break':>12} {'state at break':>15} "
              f"{'crisis share, 30d after':>24}")
        for nm, br in EPOCH_BREAKS.items():
            cand = [d for d in dates if d >= br]
            if not cand:
                print(f"  {nm:>18} {br:>12} {'no coverage':>15}")
                continue
            i0 = idx[cand[0]]
            win = lab[i0:i0 + 30]
            print(f"  {nm:>18} {br:>12} {int(lab[i0]):>15} "
                  f"{np.mean(win == 2):>23.1%}")
        print(f"\n  unconditional crisis-state share: {np.mean(lab == 2):.1%}")
        print("  NOTE: in-sample smoothed labels. Descriptive only - not a")
        print("        detection claim, and not evidence of advance warning.",
              flush=True)

    print("\n=== PRE-REGISTERED CRITERIA SUMMARY ===")
    for kk, vv in verdict.items():
        if not str(kk).startswith("_"):
            print(f"  {kk:>12} = {vv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
