#!/usr/bin/env python3
# C5 — the decisive Pillar 1 test: does anything predict EXCESS future risk?
"""De-seasonalised forward prediction across horizons, strictly causal.

PRE-REGISTERED before results were seen (see docs/PILLAR1-SELECTION-RULE.md §2):

  TARGET      excess future negative-jump activity, i.e. realised count in bars
              t+1..t+H minus the count expected for that time-of-day position.
              The seasonal baseline is fitted on TRAINING bars only, inside each
              chronological fold, so no future information reaches it.
  BINARY      "excess lands in the top decile" — the abnormal-activity class.
  PRIMARY     PR-AUC on the binary target (the class is imbalanced by
              construction, so ROC-AUC alone would flatter every model).
  SECONDARY   Spearman on continuous excess, ROC-AUC, lift over base rate.
  HORIZONS    15m, 30m, 1h, 2h, rest-of-session (3, 6, 12, 24, EOD bars).
  NULL        ToD-only. On a de-seasonalised target it should score ~0 skill by
              construction; anything that beats it carries genuine incremental
              information.

Discrete-time Hawkes is included as a first-class candidate:
    lambda_t = mu*ToD(t) + alpha * sum_{k=1..K} phi^(k-1) * N_(t-k)
which is the native-resolution self-excitation form — a geometric kernel over
whole bars, inventing no sub-bar ordering. INAR(1) is its phi=0 special case.

Run: python scripts/test_excess_risk_prediction.py
"""
from __future__ import annotations

import pickle

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import spearmanr

CACHE = r"C:/Users/Arlop/AppData/Local/Temp/p1_data.pkl"
HORIZONS = {"15m": 3, "30m": 6, "1h": 12, "2h": 24, "session": None}
KMAX = 12                     # lags in the discrete Hawkes kernel (~1 hour)

D = pickle.load(open(CACHE, "rb"))
N, S, tod, ns = D["N"], D["S"], D["tod"], D["new_sess"]
slots = np.unique(tod)
si = np.searchsorted(slots, tod)
sess_id = np.cumsum(ns) - 1
print(f"bars={N.size:,} events={int(N.sum()):,}")


def tod_profile(x, sidx):
    tot = np.bincount(sidx, weights=x, minlength=slots.size)
    c = np.bincount(sidx, minlength=slots.size).astype(float)
    p = np.where(c > 0, tot / np.maximum(c, 1), x.mean())
    return p / max(p.mean(), 1e-12)


def forward_sum(x, h):
    """Realised count in bars t+1..t+h (session-bounded for 'session')."""
    if h is not None:
        c = np.convolve(x, np.ones(h), mode="full")[h - 1:]
        return np.r_[c[1:], np.zeros(1)]
    out = np.zeros(x.size)
    for s in np.unique(sess_id):
        idx = np.flatnonzero(sess_id == s)
        rev = np.cumsum(x[idx][::-1])[::-1]
        out[idx] = np.r_[rev[1:], 0.0]
    return out


def expected_forward(prof, sidx, h):
    """Seasonally expected forward count, from the TRAIN-fitted profile only."""
    lam = prof[sidx]
    if h is not None:
        c = np.convolve(lam, np.ones(h), mode="full")[h - 1:]
        return np.r_[c[1:], np.zeros(1)]
    out = np.zeros(lam.size)
    for s in np.unique(sess_id):
        idx = np.flatnonzero(sess_id == s)
        rev = np.cumsum(lam[idx][::-1])[::-1]
        out[idx] = np.r_[rev[1:], 0.0]
    return out


def nll_nb(x, mu, k):
    mu = np.maximum(mu, 1e-12)
    k = max(k, 1e-6)
    return float(-np.sum(gammaln(x + k) - gammaln(k) - gammaln(x + 1)
                         + k * np.log(k / (k + mu)) + x * np.log(mu / (k + mu))))


def hawkes_lam(x, ns_, mu, alpha, phi, prof, sidx, kmax=KMAX):
    """Discrete-time Hawkes: geometric excitation kernel over whole bars."""
    base = mu * prof[sidx]
    lam = np.empty(x.size)
    exc = 0.0
    for i in range(x.size):
        if ns_[i]:
            exc = 0.0
        lam[i] = base[i] + alpha * exc
        exc = phi * exc + x[i]          # recursive geometric sum of past counts
    return lam


def roc_auc(s, y):
    y = np.asarray(y, int)
    pos, neg = int(y.sum()), int((1 - y).sum())
    if pos == 0 or neg == 0:
        return float("nan")
    o = np.argsort(s, kind="mergesort")
    r = np.empty(o.size)
    r[o] = np.arange(1, o.size + 1)
    return float((r[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def pr_auc(s, y):
    """Average precision — the honest metric for an imbalanced positive class."""
    y = np.asarray(y, int)
    o = np.argsort(-s, kind="mergesort")
    ys = y[o]
    tp = np.cumsum(ys)
    prec = tp / np.arange(1, ys.size + 1)
    total = max(int(y.sum()), 1)
    return float(np.sum(prec * ys) / total)


n = N.size
bnds = [int(f * n) for f in (0.40, 0.60, 0.80, 1.00)]
folds = [(0, bnds[i], bnds[i + 1]) for i in range(3)]

CANDIDATES = ["ToD-only (null)", "lagged breadth", "common-shock sync",
              "NB+INAR+ToD", "discrete Hawkes+ToD"]
out = {h: {c: {"pr": [], "roc": [], "sp": []} for c in CANDIDATES} for h in HORIZONS}
params = []

for (s0, tre, tee) in folds:
    xtr, xte = N[s0:tre], N[tre:tee]
    sitr, site = si[s0:tre], si[tre:tee]
    nstr, nste = ns[s0:tre], ns[tre:tee]
    prof = tod_profile(xtr, sitr)          # TRAIN ONLY
    m = xtr.mean()

    # --- fit the two dynamic candidates on the training block --------------
    rk = minimize(lambda p: nll_nb(xtr, m, np.exp(p[0])), [0.0], method="Nelder-Mead")
    k0 = np.exp(rk.x[0])

    r_in = minimize(
        lambda p: nll_nb(xtr, hawkes_lam(xtr, nstr, np.exp(p[0]),
                                         np.exp(p[1]), 0.0, prof, sitr), np.exp(p[2])),
        [np.log(m), np.log(0.05), np.log(k0)], method="Nelder-Mead",
        options={"maxiter": 4000})
    mu_i, a_i, k_i = np.exp(r_in.x[0]), np.exp(r_in.x[1]), np.exp(r_in.x[2])

    r_hk = minimize(
        lambda p: nll_nb(xtr, hawkes_lam(xtr, nstr, np.exp(p[0]), np.exp(p[1]),
                                         1 / (1 + np.exp(-p[2])), prof, sitr),
                         np.exp(p[3])),
        [np.log(m), np.log(0.05), 0.0, np.log(k0)], method="Nelder-Mead",
        options={"maxiter": 6000})
    mu_h, a_h, phi_h, k_h = (np.exp(r_hk.x[0]), np.exp(r_hk.x[1]),
                             1 / (1 + np.exp(-r_hk.x[2])), np.exp(r_hk.x[3]))
    branch = a_h / max(1 - phi_h, 1e-9)
    params.append((a_i, a_h, phi_h, branch))

    # --- causal predictors, information through t only ---------------------
    breadth_te = np.r_[0.0, xte[:-1] / np.maximum(S[tre:tee][:-1], 1)]
    sync_te = np.zeros(xte.size)
    for i in range(1, xte.size):
        sync_te[i] = 0.0 if nste[i] else breadth_te[i]
    preds = {
        "ToD-only (null)": prof[site],
        "lagged breadth": breadth_te,
        "common-shock sync": sync_te,
        "NB+INAR+ToD": hawkes_lam(xte, nste, mu_i, a_i, 0.0, prof, site),
        "discrete Hawkes+ToD": hawkes_lam(xte, nste, mu_h, a_h, phi_h, prof, site),
    }

    for hname, h in HORIZONS.items():
        realised = forward_sum(N, h)[tre:tee]
        expected = expected_forward(prof[si], np.arange(n), h)[tre:tee] if False else \
            expected_forward(prof, si, h)[tre:tee]
        excess = realised - expected
        hi = (excess >= np.quantile(excess, 0.9)).astype(int)
        for cname, p in preds.items():
            out[hname][cname]["pr"].append(pr_auc(p, hi))
            out[hname][cname]["roc"].append(roc_auc(p, hi))
            out[hname][cname]["sp"].append(float(spearmanr(p, excess).statistic))

base_rate = 0.10
print(f"\nTARGET: EXCESS activity vs train-fitted time-of-day baseline "
      f"(top decile = positive class, base rate {base_rate:.0%})")
print(f"{'horizon':>9} {'candidate':>22} {'PR-AUC':>8} {'lift':>6} {'ROC':>7} {'Spear':>8}")
for hname in HORIZONS:
    for cname in CANDIDATES:
        d = out[hname][cname]
        pr = float(np.mean(d["pr"]))
        print(f"{hname:>9} {cname:>22} {pr:>8.4f} {pr/base_rate:>5.2f}x "
              f"{np.mean(d['roc']):>7.4f} {np.mean(d['sp']):>8.4f}")
    print()
p = np.array(params)
print(f"[params across folds] INAR a: {p[:,0].round(4)}")
print(f"[params across folds] Hawkes alpha: {p[:,1].round(4)}  phi: {p[:,2].round(4)}  "
      f"branching n=alpha/(1-phi): {p[:,3].round(4)}")
print("\nPR-AUC of 0.10 = no skill (base rate). ROC of 0.5 = no skill.")
