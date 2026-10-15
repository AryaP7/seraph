#!/usr/bin/env python3
# C7 — surrogate null for regime separation (FR20, NFR17, O4)
"""Is the 3-regime structure in the NSE feature space distinguishable from none?

### The question this answers, and why the other diagnostics could not

After the `_conditional_loglikelihoods` repair, a 3-state fit on the real corpus
is well behaved: occupancy 43%/25%/32%, half-lives 177/134/169 days, no
transition on the optimiser boundary, median regime run 116 days. Every
non-degeneracy check passes. It looks like a working regime filter.

`validate_hamilton_regimes.py` then showed that a **single-regime VAR(1)
surrogate**, matched only to the real data's lag-1 autocorrelation and marginal
moments, produces occupancy 44%/22%/33% with half-lives 382/196/312 days and
passes the same checks. A process built to contain exactly one regime is
therefore indistinguishable from the real data under those criteria. Occupancy,
persistence and identifiability cannot settle the question.

Separation can, but only against a null. NFR17 asks for >= 3 sigma between the
crisis and tranquil RV means; the real fit gives 2.02 sigma and the one-regime
surrogate gives 1.45 sigma. Whether 2.02 is meaningfully above 1.45 is a
question about a sampling distribution, so this script estimates it.

### Method

For each of two surrogate families, draw `--reps` independent series the same
length as the real corpus, fit the same 3-state filter with the same estimator
and settings, and record the separation. The real value's position in that
distribution is an empirical p-value: `p = (1 + #{surrogate >= real}) / (1 + M)`.

* `ar1` — vector AR(1) matched to each column's lag-1 autocorrelation, marginal
  mean and sd, with the empirical innovation covariance across columns. One
  regime, correct persistence, Gaussian marginal.
* `aaft` — amplitude-adjusted Fourier transform. Randomises the Fourier phases
  and then rank-remaps onto the original sample, so the surrogate has the
  **exact** marginal distribution of the real series and approximately its full
  autocorrelation function, while any regime structure is destroyed. This is the
  stronger control: it removes the objection that an AR(1) with Gaussian
  innovations cannot reproduce realised volatility's skew, and it matches long
  memory rather than only lag 1.

Both are linear/stationary by construction and contain no regimes. Phases are
randomised **jointly across the three columns**, which preserves their
cross-spectrum and so their contemporaneous correlation.

### PRE-REGISTERED DECISION RULE — written before the run

    Separation is GENUINE only if the real value exceeds the surrogate null at
    p <= 0.05 under BOTH families, AND clears NFR17's 3.0 sigma.

Three outcomes, all reportable:

* `p <= 0.05` and `sep >= 3.0` — regimes are supported and meet the SPEC.
* `p <= 0.05` and `sep <  3.0` — the structure is real but below the SPEC's
  acceptance threshold. Report as a measured shortfall against NFR17, not as a
  pass, and do not adjust NFR17.
* `p >  0.05` — the fit is not distinguishable from a no-regime process with
  matched persistence. Hamilton's output stays unavailable, and this is the
  evidence for why.

No threshold here is to be changed after seeing a result. `llf` and BIC are
recorded too, but they are not decision variables: a surrogate and the real
series have different likelihood scales and are not comparable that way.

Run: python scripts/hamilton_surrogate_null.py [--reps 20] [--k 3]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import warnings
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.pillars.hamilton.engine import fit as engine_fit  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402


def fit_sep(y, k, *, restarts, seed):
    """Separation, occupancy and half-lives from one k-state fit."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res, order, _ = engine_fit(y, k_regimes=k, restarts=restarts, seed=seed)
        except Exception as e:                            # noqa: BLE001
            return {"failed": f"{type(e).__name__}"}
    m, p = res.model, res.params
    mu = np.array([p[m.parameters[j, "means"]][0] for j in range(k)])
    var = np.array([p[m.parameters[j, "variances"]][0] for j in range(k)])
    sm = np.asarray(res.smoothed_marginal_probabilities)
    if sm.shape[0] != k:
        sm = sm.T
    sm = sm[:, :y.shape[0]]
    occ = (np.bincount(np.argmax(sm, axis=0), minlength=k) / sm.shape[1])[order]
    trans = np.asarray(m.regime_transition_matrix(p))[:, :, 0]
    diag = np.array([trans[j, j] for j in range(k)])[order]
    sd = float(np.sqrt(np.mean([var[order[0]], var[order[-1]]])))
    conv = (getattr(res, "mle_retvals", {}) or {})
    return {
        "failed": None,
        "sep": float((mu[order[-1]] - mu[order[0]]) / sd) if sd > 0 else float("nan"),
        "llf": float(res.llf),
        "occ": [float(x) for x in occ],
        "min_occ": float(occ.min()),
        "half": [float(np.log(2) / max(1 - d, 1e-12)) for d in diag],
        "converged": bool(conv.get("converged", True)),
    }


def surrogate_ar1(y, rng):
    """Vector AR(1): one regime, matched lag-1 persistence and moments."""
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
    return out * sd + mu


def surrogate_aaft(y, rng):
    """Amplitude-adjusted Fourier transform: exact marginal, matched ACF, no
    regimes. Phases are randomised jointly so the cross-spectrum survives."""
    n, kc = y.shape
    # Gaussianise by rank, phase-randomise, then rank-remap to the original.
    ranks = np.argsort(np.argsort(y, axis=0), axis=0)
    gauss = np.zeros_like(y, dtype=float)
    normal_scores = np.sort(rng.normal(size=n))
    for j in range(kc):
        gauss[:, j] = normal_scores[ranks[:, j]]

    spec = np.fft.rfft(gauss, axis=0)
    nf = spec.shape[0]
    phase = rng.uniform(0, 2 * np.pi, size=nf)          # shared across columns
    phase[0] = 0.0
    if n % 2 == 0:
        phase[-1] = 0.0
    rot = np.abs(spec) * np.exp(1j * (np.angle(spec) + phase[:, None]))
    sur = np.fft.irfft(rot, n=n, axis=0)

    out = np.zeros_like(y, dtype=float)
    for j in range(kc):
        order_sur = np.argsort(np.argsort(sur[:, j]))
        out[:, j] = np.sort(y[:, j])[order_sur]
    return out


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
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--restarts", type=int, default=1,
                    help="restarts per surrogate fit; the real fit always uses 4")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    dates, y = asyncio.run(load())
    k = a.k
    print(f"real corpus: {len(dates):,} days  {dates[0]} .. {dates[-1]}")
    print(f"k={k}  reps={a.reps} per family  surrogate restarts={a.restarts}\n",
          flush=True)

    t0 = time.time()
    real = fit_sep(y, k, restarts=4, seed=0)
    print(f"REAL   sep={real['sep']:.4f}  llf={real['llf']:.1f}  "
          f"occ={'/'.join(f'{x:.0%}' for x in real['occ'])}  "
          f"half={'/'.join(f'{h:.0f}d' for h in real['half'])}  "
          f"conv={real['converged']}  ({time.time() - t0:.0f}s)\n", flush=True)

    ac_real = [float(np.corrcoef(y[:-1, j], y[1:, j])[0, 1]) for j in range(3)]
    results: dict[str, list] = {}
    for fam, gen in (("ar1", surrogate_ar1), ("aaft", surrogate_aaft)):
        print(f"--- {fam} surrogates ---", flush=True)
        seps, rows = [], []
        for i in range(a.reps):
            rng = np.random.default_rng(1000 * (1 if fam == "ar1" else 2) + i)
            ys = gen(y, rng)
            ac = [float(np.corrcoef(ys[:-1, j], ys[1:, j])[0, 1]) for j in range(3)]
            d = fit_sep(ys, k, restarts=a.restarts, seed=0)
            d["ac"] = ac
            rows.append(d)
            if d["failed"]:
                print(f"  rep {i:>2}: FAILED {d['failed']}", flush=True)
                continue
            seps.append(d["sep"])
            print(f"  rep {i:>2}: sep={d['sep']:>6.3f}  "
                  f"occ={'/'.join(f'{x:.0%}' for x in d['occ']):>14}  "
                  f"minocc={d['min_occ']:.2f}  ac1={np.round(ac, 4)}  "
                  f"conv={str(d['converged'])[0]}", flush=True)
        results[fam] = rows
        if seps:
            s = np.array(seps)
            ge = int(np.sum(s >= real["sep"]))
            pval = (1 + ge) / (1 + s.size)
            print(f"\n  {fam}: n={s.size}  null sep mean={s.mean():.3f} "
                  f"sd={s.std(ddof=1):.3f}  median={np.median(s):.3f}  "
                  f"max={s.max():.3f}  p95={np.percentile(s, 95):.3f}")
            print(f"  real sep={real['sep']:.3f}  #surrogate>=real = {ge}  "
                  f"empirical p = {pval:.4f}")
            print(f"  -> {'DISTINGUISHABLE' if pval <= 0.05 else 'NOT DISTINGUISHABLE'}"
                  f" from a no-regime process at p<=0.05\n", flush=True)
            results[fam + "_summary"] = {
                "n": int(s.size), "mean": float(s.mean()),
                "sd": float(s.std(ddof=1)), "median": float(np.median(s)),
                "max": float(s.max()), "p95": float(np.percentile(s, 95)),
                "ge_real": ge, "p": float(pval),
            }

    print("=== PRE-REGISTERED DECISION ===")
    ps = {f: results[f + "_summary"]["p"] for f in ("ar1", "aaft")
          if f + "_summary" in results}
    both = bool(ps) and all(v <= 0.05 for v in ps.values())
    nfr17 = real["sep"] >= 3.0
    print(f"  p-values: " + "  ".join(f"{f}={v:.4f}" for f, v in ps.items()))
    print(f"  distinguishable under BOTH families at p<=0.05: {both}")
    print(f"  NFR17 (sep >= 3.0 sigma): {nfr17}  (sep = {real['sep']:.3f})")
    if both and nfr17:
        verdict = "SUPPORTED and meets NFR17"
    elif both:
        verdict = "structure real but BELOW NFR17 — measured shortfall, not a pass"
    else:
        verdict = ("NOT DISTINGUISHABLE from a no-regime process — "
                   "Hamilton output stays unavailable")
    print(f"  VERDICT: {verdict}")

    if a.out:
        payload = {"real": real, "ac_real": ac_real, "k": k, "reps": a.reps,
                   "verdict": verdict, "p": ps,
                   **{f: results[f] for f in ("ar1", "aaft") if f in results},
                   **{f + "_summary": results[f + "_summary"]
                      for f in ("ar1", "aaft") if f + "_summary" in results}}
        Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"\n  wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
