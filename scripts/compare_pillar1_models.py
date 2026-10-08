#!/usr/bin/env python3
# C5 — Pillar 1 model selection under the pre-registered rule.
"""Six candidate families, chronological forward folds, corrected session reset.

Selection rule is committed in `docs/PILLAR1-SELECTION-RULE.md` BEFORE these
numbers were produced. Primary metric is out-of-sample NLL per bar; the gates
(materiality, consistency, identifiability, calibration, parsimony) and the
secondary forward-prediction metric are applied mechanically below.

The secondary metric is the one that decides whether this is a *risk* model:
using only information through bar t, does the statistic predict jump activity
in bars t+1..t+H? A model that describes the current bar but carries no forward
information is not usable for Pillar 1 whatever its likelihood.

Run: python scripts/compare_pillar1_models.py
Requires the cached panel from scripts/diagnose_jump_process.py.
"""
from __future__ import annotations

import pickle

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom, poisson, spearmanr

CACHE = r"C:/Users/Arlop/AppData/Local/Temp/p1_data.pkl"
H = 15                      # forward window, ~1 trading hour at 5-minute bars

D = pickle.load(open(CACHE, "rb"))
N, S, tod, ns = D["N"], D["S"], D["tod"], D["new_sess"]
slots = np.unique(tod)
si_all = np.searchsorted(slots, tod)
print(f"bars={N.size:,} events={int(N.sum()):,} var/mean={N.var()/N.mean():.2f}")


def tod_prof(x, si):
    tot = np.bincount(si, weights=x, minlength=slots.size)
    c = np.bincount(si, minlength=slots.size).astype(float)
    p = np.where(c > 0, tot / np.maximum(c, 1), x.mean())
    return p / max(p.mean(), 1e-12)


def inar_lam(x, ns_, mu, a, prof=None, si=None):
    """lambda_t = mu_t + a*N_{t-1}, reset to mu_t at each session open.

    Resetting to mu (not the unconditional mean mu/(1-a-b)) is essential: the
    unconditional form explodes as a+b -> 1 and lets the optimiser fake a huge
    opening intensity. See AMENDMENT-03 §4.
    """
    base = mu * prof[si] if prof is not None else np.full(x.size, mu)
    lam = np.empty(x.size)
    prev = 0.0
    for i in range(x.size):
        if ns_[i]:
            prev = 0.0
        lam[i] = base[i] + a * prev
        prev = x[i]
    return lam


def nll_p(lam, x):
    lam = np.maximum(lam, 1e-12)
    return float(np.sum(lam - x * np.log(lam) + gammaln(x + 1)))


def nll_n(x, mu, k):
    mu = np.maximum(mu, 1e-12)
    k = max(k, 1e-6)
    return float(-np.sum(gammaln(x + k) - gammaln(k) - gammaln(x + 1)
                         + k * np.log(k / (k + mu)) + x * np.log(mu / (k + mu))))


def pit(x, lam, k=None, seed=0):
    """Randomised PIT for count data (Czado et al.): uniform if calibrated."""
    r = np.random.default_rng(seed)
    if k is None:
        lo, hi = poisson.cdf(x - 1, lam), poisson.cdf(x, lam)
    else:
        p = k / (k + lam)
        lo, hi = nbinom.cdf(x - 1, k, p), nbinom.cdf(x, k, p)
    return lo + r.uniform(size=x.size) * (hi - lo)


def forward_counts(x, i0, i1):
    """Total events in bars t+1 .. t+H, aligned to t."""
    c = np.convolve(x, np.ones(H), mode="full")[H - 1:]
    f = np.r_[c[1:], np.zeros(1)]
    return f[i0:i1]


def auc(score, y):
    y = np.asarray(y, int)
    pos, neg = int(y.sum()), int((1 - y).sum())
    if pos == 0 or neg == 0:
        return float("nan")
    o = np.argsort(score, kind="mergesort")
    r = np.empty(o.size)
    r[o] = np.arange(1, o.size + 1)
    return float((r[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


n = N.size
bnds = [int(f * n) for f in (0.40, 0.55, 0.70, 0.85, 1.00)]
folds = [(0, bnds[i], bnds[i + 1]) for i in range(4)]
MODELS = ["Poisson", "INAR(1)", "Poisson+ToD", "NegBinomial",
          "NB+INAR+ToD", "CommonShock(NB+sync)"]
res = {m: {kk: [] for kk in ("nll", "pit_m", "pit_s", "sp", "auc", "par")}
       for m in MODELS}

for (s0, tre, tee) in folds:
    xtr, xte = N[s0:tre], N[tre:tee]
    sitr, site = si_all[s0:tre], si_all[tre:tee]
    nstr, nste = ns[s0:tre], ns[tre:tee]
    nb = xte.size
    fut = forward_counts(N, tre, tee)
    hi_act = (fut >= np.quantile(fut, 0.9)).astype(int)
    m = xtr.mean()
    prof = tod_prof(xtr, sitr)

    def record(name, nll_val, lam, k, par, predictive=True):
        res[name]["nll"].append(nll_val / nb)
        res[name]["par"].append(par)
        u = pit(xte, lam, k)
        res[name]["pit_m"].append(float(u.mean()))
        res[name]["pit_s"].append(float(u.std()))
        if predictive:
            res[name]["sp"].append(float(spearmanr(lam, fut).statistic))
            res[name]["auc"].append(auc(lam, hi_act))
        else:
            res[name]["sp"].append(0.0)
            res[name]["auc"].append(0.5)

    # 1 constant Poisson
    lam = np.full(nb, m)
    record("Poisson", nll_p(lam, xte), lam, None, m, predictive=False)

    # 2 INAR(1), corrected reset
    r = minimize(lambda p: nll_p(inar_lam(xtr, nstr, np.exp(p[0]),
                                          1 / (1 + np.exp(-p[1]))), xtr),
                 [np.log(m), -2.0], method="Nelder-Mead")
    mu, a = np.exp(r.x[0]), 1 / (1 + np.exp(-r.x[1]))
    lam = inar_lam(xte, nste, mu, a)
    record("INAR(1)", nll_p(lam, xte), lam, None, a)

    # 3 Poisson + time-of-day
    lam = m * prof[site]
    record("Poisson+ToD", nll_p(lam, xte), lam, None, float(prof.max()))

    # 4 static negative binomial
    rk = minimize(lambda p: nll_n(xtr, m, np.exp(p[0])), [0.0], method="Nelder-Mead")
    k = np.exp(rk.x[0])
    lam = np.full(nb, m)
    record("NegBinomial", nll_n(xte, m, k), lam, k, k, predictive=False)

    # 5 NB + INAR + ToD
    r2 = minimize(lambda p: nll_n(xtr, inar_lam(xtr, nstr, np.exp(p[0]),
                                                1 / (1 + np.exp(-p[1])), prof, sitr),
                                  np.exp(p[2])),
                  [np.log(m), -2.0, np.log(k)], method="Nelder-Mead",
                  options={"maxiter": 4000})
    mu2, a2, k2 = np.exp(r2.x[0]), 1 / (1 + np.exp(-r2.x[1])), np.exp(r2.x[2])
    lam = inar_lam(xte, nste, mu2, a2, prof, site)
    record("NB+INAR+ToD", nll_n(xte, lam, k2), lam, k2, a2)

    # 6 common shock: LAGGED cross-sectional breadth, so it is predictive not
    #   contemporaneous — breadth_t-1 = share of active symbols that jumped.
    br_tr = np.r_[0.0, xtr[:-1] / np.maximum(S[s0:tre][:-1], 1)]
    br_te = np.r_[0.0, xte[:-1] / np.maximum(S[tre:tee][:-1], 1)]
    r3 = minimize(lambda p: nll_n(xtr, np.exp(p[0]) * prof[sitr] + np.exp(p[1]) * br_tr,
                                  np.exp(p[2])),
                  [np.log(m), np.log(max(m, 1e-3)), np.log(k)],
                  method="Nelder-Mead", options={"maxiter": 4000})
    mu3, g3, k3 = np.exp(r3.x[0]), np.exp(r3.x[1]), np.exp(r3.x[2])
    lam = mu3 * prof[site] + g3 * br_te
    record("CommonShock(NB+sync)", nll_n(xte, lam, k3), lam, k3, g3)

base_folds = np.array(res["Poisson"]["nll"])
base = base_folds.mean()
print(f"\n{'model':>22} {'meanNLL':>9} {'vsBase':>8} {'allFolds':>9} {'PITm':>6} "
      f"{'PITsd':>6} {'parCV':>7} {'Spear':>7} {'AUC':>6}")
for name in MODELS:
    d = res[name]
    v = np.array(d["nll"])
    p = np.array(d["par"], float)
    better = (name == "Poisson") or bool(np.all(v < base_folds))
    cv = float(np.std(p) / max(abs(np.mean(p)), 1e-12))
    print(f"{name:>22} {v.mean():>9.5f} {100*(base-v.mean())/base:>7.1f}% "
          f"{str(better):>9} {np.mean(d['pit_m']):>6.3f} {np.mean(d['pit_s']):>6.3f} "
          f"{cv:>7.2f} {np.mean(d['sp']):>7.3f} {np.mean(d['auc']):>6.3f}")
print(f"\nfolds (chronological, disjoint): {folds}")
print("PIT target: mean 0.500, sd 0.289 (uniform). Spear/AUC use info through t "
      f"to predict bars t+1..t+{H}.")
