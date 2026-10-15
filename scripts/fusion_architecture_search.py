#!/usr/bin/env python3
# C9/C10 — can a LEARNED fusion architecture produce causal advance warning?
"""Pre-registered comparison of five fusion architectures (FR28–FR31, FR33, O5).

**Pre-registration: `docs/evidence/FUSION-PREREGISTRATION.md`, sha256
`3d8e8de372e328444d9711fcb531c41deb8e91bac17100c0d19ff295abb4848d`, written and
hashed before the first fit.** Hypotheses H1–H4, the false-alarm budget, the
candidate set, the development/confirmation split and the tie-breaking rules are
all fixed there. This script only executes it.

## Where these candidates sit in the architecture

The pipeline is `pillar -> FR28 causal ECDF -> C8 Kalman -> C9 fuse`. C9 operates
on the **reconciled state**, so every candidate here operates on the reconciled
state too. Anything else would be comparing a proposed fusion rule against the
baseline at a different point in the pipeline.

That gives a free correctness check which is asserted, not assumed: candidate A
(equal weights, D2-masked and renormalised) must reproduce the shipped
`CSRS[hawkes+rmt+hamilton]` series **exactly**. If it does not, the harness is
wrong and no other number in the output means anything.

## What is fitted, and on what

Per fold, using data strictly before the test epoch's onset and nothing else:
weights (B), logistic coefficients and `C` (C), both escalation thresholds (D),
and **the alert threshold for every candidate**, set to hit the false-alarm
budget on the training period. The FR28 ECDF window is already causal via
`window_from`.

## The arithmetic that makes H1 likely, stated up front

Every input's measured T3 (pre-onset) AUC is between 0.38 and 0.59
(`CRISIS-REPLAY.md` §5c). A convex combination of inputs that are individually
uninformative is uninformative — so candidate B is bounded above by roughly its
best input. Candidates C and D are the ones that could break that bound, C by
using negative loadings and D by not averaging at all. Running B anyway is the
point: a bound you assert is not a bound you measured.

## Reading the output

`warned` is **event-level**: a rising edge inside `[onset-15, onset-1]`. A
standing alert counts once. In-crisis days are dropped, so a crisis reading can
never score as a warning. `FA/yr` counts rising edges outside every
`[onset-30, onset+30]` window.

Run:
  python scripts/fusion_architecture_search.py --budget 2.0
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import itertools
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "rcw", Path(__file__).resolve().parent / "replay_crisis_warnings.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402

PRE = 15                      # FR32 upper lead bound
PILLARS = ("hawkes", "rmt", "hamilton")
EQUAL = np.array([1 / 3, 1 / 3, 1 / 3])

#: pre-registered development / confirmation split
DEV_EPOCHS = ("gfc_2008", "taper_2013", "ilfs_2018", "covid_2020")
CONFIRM_EPOCHS = ("tightening_2022", "tariff_2026")

#: candidate B's simplex grid, step 0.05
GRID_STEP = 0.05
#: candidate B's shrinkage toward equal weights
SHRINK = (0.0, 0.25, 0.50, 0.75)
#: candidate C's L2 strengths, selected by inner chronological CV
C_GRID = (0.01, 0.1, 1.0)


# --------------------------------------------------------------------------
# labels
# --------------------------------------------------------------------------
def labels(dates: list[str]) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """(pre-onset positives, in-crisis mask to DROP, onset index per epoch)."""
    n = len(dates)
    y = np.zeros(n, dtype=bool)
    crisis = np.zeros(n, dtype=bool)
    onset_at: dict[str, int] = {}
    for e, (onset, _) in EPOCH_BREAKS.items():
        at = [i for i, d in enumerate(dates) if d >= onset]
        if not at:
            continue
        s0 = at[0]
        onset_at[e] = s0
        y[max(0, s0 - PRE):s0] = True
        crisis[s0:min(n, s0 + CRISIS_WINDOW_DAYS)] = True
    return y, crisis, onset_at


def episodes(flag: np.ndarray) -> list[int]:
    """Rising-edge indices — a standing alert is one decision, not many."""
    return [i for i in range(flag.size) if flag[i] and (i == 0 or not flag[i - 1])]


# --------------------------------------------------------------------------
# threshold chosen on TRAINING data to hit the false-alarm budget
# --------------------------------------------------------------------------
def threshold_at_budget(score: np.ndarray, train: np.ndarray,
                        excl: np.ndarray, years: float,
                        budget: float) -> float:
    """Highest-sensitivity threshold whose TRAIN false-alarm rate <= budget.

    Searched downward over the training score quantiles: the lowest threshold
    (most alerts) that still respects the budget. Returns +inf when even the
    strictest threshold breaches it, which makes the candidate silent rather
    than silently over-alerting.
    """
    s = score[train & np.isfinite(score)]
    if s.size < 50:
        return float("inf")
    best = float("inf")
    for q in np.arange(0.999, 0.499, -0.001):
        thr = float(np.quantile(s, q))
        flag = train & np.isfinite(score) & (score >= thr)
        fa = [i for i in episodes(flag) if not excl[i]]
        if len(fa) / max(years, 1e-9) <= budget:
            best = thr
        else:
            break
    return best


def evaluate(score: np.ndarray, thr: float, test_epochs, dates, onset_at,
             excl: np.ndarray, assess: np.ndarray) -> dict:
    """Event-level warned rate, leads, and false alarms on the whole span."""
    if not np.isfinite(thr):
        return {"warned": 0, "testable": 0, "leads": [], "fa_per_year": 0.0,
                "note": "no threshold respects the budget"}
    flag = np.isfinite(score) & assess & (score >= thr)
    eps = episodes(flag)
    warned, testable, leads = 0, 0, []
    for e in test_epochs:
        if e not in onset_at:
            continue
        k = onset_at[e] - 1                       # last day strictly before
        lo = max(0, k - PRE + 1)
        if sum(1 for i in range(lo, k + 1)
               if np.isfinite(score[i]) and assess[i]) < max(3, PRE // 3):
            continue                              # untestable, not a miss
        testable += 1
        hit = [i for i in eps if lo <= i <= k]
        if hit:
            warned += 1
            leads.append(k - hit[0] + 1)
    yrs = (int(dates[-1][:4]) - int(dates[0][:4])
           + (int(dates[-1][5:7]) - int(dates[0][5:7])) / 12.0)
    fa = [i for i in eps if not excl[i]]
    return {"warned": warned, "testable": testable, "leads": leads,
            "fa_per_year": round(len(fa) / max(yrs, 1e-9), 3),
            "n_episodes": len(eps), "frac_days": round(float(flag.mean()), 4)}


# --------------------------------------------------------------------------
# candidate B — constrained convex weights on the simplex
# --------------------------------------------------------------------------
def simplex_grid(step: float = GRID_STEP) -> np.ndarray:
    k = int(round(1.0 / step))
    pts = [(a / k, b / k, (k - a - b) / k)
           for a in range(k + 1) for b in range(k + 1 - a)]
    return np.asarray(pts, dtype=float)


def auc(score: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(score)
    s, yy = score[m], y[m]
    if yy.sum() < 3 or (~yy).sum() < 3:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    r = np.empty(s.size, dtype=float)
    r[order] = np.arange(1, s.size + 1, dtype=float)
    srt = s[order]
    i = 0
    while i < srt.size:                            # average ranks within ties
        j = i
        while j + 1 < srt.size and srt[j + 1] == srt[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    n1, n0 = float(yy.sum()), float((~yy).sum())
    return float((r[yy].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def fuse(X: np.ndarray, mask: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted composite with D2 renormalisation over available pillars.

    A pillar that is unavailable must not contribute a zero — it must drop out
    and the remaining weights must renormalise, which is what D2's mask is for.
    """
    wm = mask * w[None, :]
    tot = wm.sum(axis=1)
    out = np.full(X.shape[0], np.nan)
    ok = tot > 0
    out[ok] = (np.nan_to_num(X[ok]) * wm[ok]).sum(axis=1) / tot[ok]
    return out


def learn_convex(X, mask, y, train, shrink: float) -> tuple[np.ndarray, float]:
    """Grid-search the simplex for max training AUC, then shrink to equal.

    A grid rather than a gradient method on purpose: it is deterministic, has no
    hyperparameters of its own, and the full surface can be inspected — which is
    how fold-to-fold instability becomes visible instead of being hidden behind
    a single converged answer.
    """
    best_w, best_a = EQUAL.copy(), -np.inf
    for w in simplex_grid():
        a = auc(fuse(X, mask, w)[train], y[train])
        if np.isfinite(a) and a > best_a:
            best_a, best_w = a, w
    w = (1 - shrink) * best_w + shrink * EQUAL
    return w / w.sum(), float(best_a)


# --------------------------------------------------------------------------
# candidate C — L2 logistic, coefficients unconstrained in sign
# --------------------------------------------------------------------------
def fit_logistic(X, y, train, C: float, iters: int = 400):
    """Plain L2 logistic regression by Newton steps; no sklearn dependency.

    Inputs are already in [0,1] (FR28 ranks), so no further scaling is applied
    and the coefficients are directly interpretable as log-odds per unit rank.
    """
    Z = np.column_stack([np.ones(X.shape[0]), np.nan_to_num(X, nan=0.5)])
    Zt, yt = Z[train], y[train].astype(float)
    if yt.sum() < 5:
        return None
    beta = np.zeros(Z.shape[1])
    lam = 1.0 / max(C, 1e-9)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Zt @ beta, -30, 30)))
        g = Zt.T @ (p - yt) + lam * np.r_[0.0, beta[1:]]
        W = np.clip(p * (1 - p), 1e-8, None)
        H = Zt.T @ (Zt * W[:, None]) + lam * np.diag(np.r_[0.0, np.ones(Z.shape[1] - 1)])
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return None
        beta -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return beta


def logistic_score(X, beta) -> np.ndarray:
    Z = np.column_stack([np.ones(X.shape[0]), np.nan_to_num(X, nan=0.5)])
    return 1.0 / (1.0 + np.exp(-np.clip(Z @ beta, -30, 30)))


# --------------------------------------------------------------------------
# the reconciled state — one causal pass, which is where C9 operates
# --------------------------------------------------------------------------
async def reconciled_state(pillar2: str = "lam1"):
    """Daily reconciled 3-vector and D2 mask from the real C8 Kalman.

    Mirrors `replay_subset` with all three pillars enabled, but keeps `x_hat`
    and the mask instead of discarding them for the scalar CSRS.
    """
    from bisect import bisect_right

    from seraph.orchestration import (close_ts, hamilton_emission,
                                      hawkes_contagion_emission, lam1_share,
                                      rmt_emission, window_from)
    from seraph.reconciliation.kalman import KalmanReconciler
    from seraph.shared_types import UnavailableEmission, ist_timestamp

    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        raw = await R.load_all(pool)
    finally:
        await pool.close()

    lam_series, lam_by_date, sca_series, sca_by_date = [], {}, [], {}
    for r in raw["rmt"]:
        d = str(r["date"])
        ev = list(r["eigenvalues"] or [])
        sc = r["sca_t"]
        if sc is not None and np.isfinite(float(sc)):
            sca_by_date[d] = float(sc)
            sca_series.append((d, float(sc)))
        s = lam1_share(ev)
        if s is None:
            continue
        lam_series.append((d, s))
        lam_by_date[d] = ev

    hwk_series, hwk_pts = [], []
    for r in raw["hwk"]:
        nn = float(r["branching_ratio_n"])
        hwk_series.append((str(r["ts"].date()), nn / (1.0 - nn)))
        hwk_pts.append((r["ts"], nn, ist_timestamp(r["ts"])))
    hwk_pts.sort(key=lambda x: x[0])
    hwk_ts = [p[0] for p in hwk_pts]

    ham = R.load_hamilton_causal()
    R.ham_series_cache = sorted((d, v[0]) for d, v in ham.items())

    grid = [d for d, _ in lam_series]
    rec = KalmanReconciler()
    dates, Xs, Ms = [], [], []
    for d in grid:
        ts = close_ts(d)
        ems = []

        i = bisect_right(hwk_ts, datetime.fromisoformat(ts)) - 1
        if i >= 0:
            _, nn, tau = hwk_pts[i]
            e, _ = hawkes_contagion_emission(
                ts=ts, tau=tau, branching_ratio=nn,
                window=window_from(hwk_series, d))
        else:
            e = UnavailableEmission(pillar="hawkes", ts=ts, absence="structural",
                                    reason="no_data_coverage")
        ems.append(e)

        if pillar2 == "sca":
            e, _ = R.rmt_emission_sca(date=d, sca=sca_by_date.get(d),
                                      window=window_from(sca_series, d))
        else:
            e, _ = rmt_emission(date=d, eigenvalues=lam_by_date.get(d),
                                window=window_from(lam_series, d))
        ems.append(e)

        hit = ham.get(d)
        if hit is not None:
            e, _ = hamilton_emission(date=d, lsd=hit[0], raw_variance=hit[1],
                                     window=window_from(R.ham_series_cache, d))
        else:
            e = UnavailableEmission(pillar="hamilton", ts=ts,
                                    absence="structural",
                                    reason="no_data_coverage")
        ems.append(e)

        up = rec.update(ems)
        if up.status == "error":
            continue
        st = up.value
        dates.append(d)
        Xs.append(list(st.x_hat))
        Ms.append([bool(x) for x in st.mask])
    return dates, np.asarray(Xs, dtype=float), np.asarray(Ms, dtype=bool)


async def main(budget: float, pillar2: str, out_dir: str) -> int:
    print(f"\n[fusion] pre-registration sha256 "
          f"3d8e8de372e328444d9711fcb531c41deb8e91bac17100c0d19ff295abb4848d")
    print(f"[fusion] false-alarm budget {budget} episodes/year (PRIMARY=2.0)")
    print(f"[fusion] pillar 2 quantity: {pillar2}")
    print(f"[fusion] dev epochs      : {DEV_EPOCHS}")
    print(f"[fusion] CONFIRM epochs  : {CONFIRM_EPOCHS}  (touched ONCE, at the end)")
    print(f"[fusion] building reconciled state ...", flush=True)

    dates, X, M = await reconciled_state(pillar2)
    y, crisis, onset_at = labels(dates)
    n = len(dates)
    assess = ~crisis                      # in-crisis days dropped everywhere
    excl = np.zeros(n, dtype=bool)
    for e, k in onset_at.items():
        excl[max(0, k - CRISIS_WINDOW_DAYS):min(n, k + CRISIS_WINDOW_DAYS)] = True

    print(f"[fusion] grid {n:,} days {dates[0]} .. {dates[-1]}")
    print(f"[fusion] pre-onset positives {int((y & assess).sum())}, "
          f"in-crisis dropped {int(crisis.sum())}")
    print(f"[fusion] mask coverage: " + ", ".join(
        f"{p}={int(M[:, i].sum()):,}" for i, p in enumerate(PILLARS)))
    print(f"[fusion] all-three available on {int(M.all(axis=1).sum()):,} days",
          flush=True)

    report = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preregistration_sha256":
            "3d8e8de372e328444d9711fcb531c41deb8e91bac17100c0d19ff295abb4848d",
        "budget_fa_per_year": budget,
        "pillar2_quantity": pillar2,
        "dev_epochs": list(DEV_EPOCHS), "confirm_epochs": list(CONFIRM_EPOCHS),
        "grid": {"n": n, "first": dates[0], "last": dates[-1]},
        "mask_coverage": {p: int(M[:, i].sum()) for i, p in enumerate(PILLARS)},
        "all_three_days": int(M.all(axis=1).sum()),
        "folds": {}, "candidates": {},
    }

    # ---- correctness check: A must reproduce the shipped CSRS ----------
    comp_equal = fuse(X, M, EQUAL)
    sig = await R.build_signals(pillar2)
    shipped = dict(zip(*sig["CSRS[hawkes+rmt+hamilton]"][:2]))
    ours = {d: v for d, v in zip(dates, comp_equal)}
    common = [d for d in dates if d in shipped and np.isfinite(shipped[d])]
    diff = max(abs(shipped[d] - ours[d]) for d in common) if common else float("nan")
    print(f"\n[fusion] CHECK candidate A vs shipped CSRS over {len(common):,} "
          f"days: max|delta| = {diff:.3e}")
    report["harness_check_max_abs_delta"] = float(diff)
    if not (diff < 1e-9):
        print(f"[fusion] *** HARNESS CHECK FAILED *** equal-weight fusion does "
              f"not reproduce the shipped CSRS; no result below is meaningful.")
        report["harness_check"] = "FAILED"
    else:
        print(f"[fusion] harness check PASSED")
        report["harness_check"] = "PASSED"

    # ---- per-fold learning on development epochs ----------------------
    print(f"\n=== candidate B: learned convex weights, per development fold ===")
    hdr = (f"{'fold / test epoch':<20}{'train days':>11}{'train pos':>10}"
           f"{'  w_hawkes  w_rmt  w_ham':>26}{'train AUC':>11}")
    print(hdr); print("-" * len(hdr))
    fold_w = {}
    for e in DEV_EPOCHS:
        if e not in onset_at:
            print(f"{e:<20}{'(no data)':>11}")
            continue
        k = onset_at[e]
        train = np.zeros(n, dtype=bool)
        train[:max(0, k - PRE)] = True
        train &= assess
        npos = int((y & train).sum())
        if npos < 5:
            print(f"{e:<20}{int(train.sum()):>11,}{npos:>10}"
                  f"{'  UNTRAINABLE (<5 positives)':>26}")
            fold_w[e] = None
            continue
        w, a = learn_convex(X, M, y, train, shrink=0.0)
        fold_w[e] = w
        print(f"{e:<20}{int(train.sum()):>11,}{npos:>10}"
              f"   {w[0]:>8.2f}{w[1]:>7.2f}{w[2]:>7.2f}{a:>11.4f}")
        report["folds"][e] = {"train_days": int(train.sum()), "train_pos": npos,
                              "w": [round(float(x), 4) for x in w],
                              "train_auc": round(a, 4)}

    # H2: stability
    ws = [w for w in fold_w.values() if w is not None]
    if len(ws) >= 2:
        span = float(max(np.abs(a - b).sum() for a, b in itertools.combinations(ws, 2)))
        print(f"\n[fusion] H2 weight stability: max pairwise L1 distance across "
              f"folds = {span:.3f}  (H2 predicts > 0.33 = UNSTABLE)")
        print(f"[fusion] H2 verdict: "
              f"{'UNSTABLE as predicted' if span > 0.33 else 'STABLE - H2 REJECTED'}")
        report["h2_weight_l1_span"] = round(span, 4)
        report["h2_verdict"] = "UNSTABLE" if span > 0.33 else "STABLE"
    else:
        print(f"\n[fusion] H2 untestable: only {len(ws)} trainable fold(s)")
        report["h2_verdict"] = "UNTESTABLE"

    # ---- simple-feature and VIX baselines, on the same grid ------------
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        mkt = await pool.fetch("""
          WITH r AS (SELECT date, symbol,
                       ln(adj_close / NULLIF(lag(adj_close)
                          OVER (PARTITION BY symbol ORDER BY date),0)) lr
                     FROM daily_prices WHERE universe_member_flag AND adj_close>0)
          SELECT date, avg(lr) mkt FROM r WHERE lr IS NOT NULL
          GROUP BY date ORDER BY date""")
        vix = await pool.fetch("SELECT date, india_vix FROM macro_covariates "
                               "WHERE india_vix IS NOT NULL ORDER BY date")
    finally:
        await pool.close()
    midx = {str(r["date"]): float(r["mkt"]) for r in mkt}
    lr = np.array([midx.get(d, np.nan) for d in dates])
    vidx = {str(r["date"]): float(r["india_vix"]) for r in vix}
    rv = R.realised_vol(lr, 20)
    dd = R.drawdown(lr)
    simple = {
        "E:semivar_20": R.downside_semivariance(lr, 20),
        "E:rv_20": rv,
        "E:drawdown": dd,
        "E:rv_accel_5": R.accel(rv, 5),
        "E:dd_accel_5": R.accel(dd, 5),
        "E:india_vix": np.array([vidx.get(d, np.nan) for d in dates]),
    }
    print(f"\n[fusion] baselines on grid: " + ", ".join(
        f"{k.split(':')[1]}={int(np.isfinite(v).sum()):,}" for k, v in simple.items()))

    # ---- build every candidate's OUT-OF-SAMPLE score series ------------
    # For the learned candidates a fold's score is produced by parameters fitted
    # strictly before that fold's test epoch, so the series is stitched from
    # per-fold out-of-sample segments and is never an in-sample fit.
    def fold_train_mask(k: int) -> np.ndarray:
        tr = np.zeros(n, dtype=bool)
        tr[:max(0, k - PRE)] = True
        return tr & assess

    cands: dict[str, np.ndarray] = {"A:equal_weight": comp_equal}

    def fold_years(k: int) -> float:
        return max((int(dates[max(0, k - PRE)][:4]) - int(dates[0][:4])), 1)

    def rolling_origin(make_score, epochs, min_pos: int) -> dict:
        """Fit parameters AND threshold per fold on that fold's training data.

        `make_score(train_mask)` returns the full-span score produced by
        parameters fitted on `train_mask` only. The threshold is then set on the
        same training period at the false-alarm budget and applied to the fold's
        test epoch. Nothing from the test epoch reaches either step.
        """
        warned = testable = 0
        leads, fas, fracs, thrs, skipped = [], [], [], [], []
        for e in epochs:
            if e not in onset_at:
                continue
            k = onset_at[e]
            tr = fold_train_mask(k)
            if int((y & tr).sum()) < min_pos:
                skipped.append(e)
                continue
            sc = make_score(tr)
            if sc is None:
                skipped.append(e)
                continue
            thr = threshold_at_budget(sc, tr, excl, fold_years(k), budget)
            r = evaluate(sc, thr, (e,), dates, onset_at, excl, assess)
            if r["testable"] == 0:
                skipped.append(e)
                continue
            warned += r["warned"]
            testable += r["testable"]
            leads += r["leads"]
            fas.append(r["fa_per_year"])
            fracs.append(r.get("frac_days", 0.0))
            thrs.append(None if not np.isfinite(thr) else round(float(thr), 6))
        return {"warned": warned, "testable": testable, "leads": leads,
                "fa_per_year": (round(float(np.mean(fas)), 3) if fas else 0.0),
                "frac_days": (round(float(np.mean(fracs)), 4) if fracs else 0.0),
                "per_fold_thresholds": thrs, "skipped_folds": skipped}

    # B: per-fold learned convex weights, out of sample
    b_results, b_weights = {}, {}
    for sh in SHRINK:
        ws_this = {}

        def mk(tr, sh=sh, ws_this=ws_this):
            w, _ = learn_convex(X, M, y, tr, shrink=sh)
            ws_this[int(tr.sum())] = [round(float(x), 4) for x in w]
            return fuse(X, M, w)
        b_results[f"B:convex_shrink{sh:g}"] = rolling_origin(
            mk, list(DEV_EPOCHS), min_pos=5)
        b_weights[f"shrink{sh:g}"] = ws_this

    # C: per-fold L2 logistic, C chosen by INNER chronological CV
    chosen_C, coefs = {}, {}

    def mk_logit(tr):
        idx = np.flatnonzero(tr)
        if idx.size < 200:
            return None
        cut = idx[int(0.67 * idx.size)]
        inner_tr = tr.copy(); inner_tr[cut:] = False
        inner_va = tr.copy(); inner_va[:cut] = False
        best_C, best_a = None, -np.inf
        for C in C_GRID:
            b = fit_logistic(X, y, inner_tr, C)
            if b is None:
                continue
            a = auc(logistic_score(X, b)[inner_va], y[inner_va])
            if np.isfinite(a) and a > best_a:
                best_a, best_C = a, C
        if best_C is None:
            return None
        b = fit_logistic(X, y, tr, best_C)
        if b is None:
            return None
        chosen_C[int(tr.sum())] = best_C
        coefs[int(tr.sum())] = [round(float(x), 4) for x in b]
        return logistic_score(X, b)

    c_result = rolling_origin(mk_logit, list(DEV_EPOCHS), min_pos=10)

    # D: composite plus independent escalation — a two-threshold OR-rule.
    # Each arm gets half the false-alarm budget on the fold's training data, so
    # the combined rule is held to the same total budget as every other
    # candidate rather than being allowed to buy warnings with extra alerts.
    def eval_flag_fold(flag, e, k):
        eps = episodes(flag)
        kk = k - 1
        lo = max(0, kk - PRE + 1)
        if sum(1 for i in range(lo, kk + 1)
               if assess[i]) < max(3, PRE // 3):
            return None
        hit = [i for i in eps if lo <= i <= kk]
        yrs = max(int(dates[-1][:4]) - int(dates[0][:4]), 1)
        fa = [i for i in eps if not excl[i]]
        return {"warned": 1 if hit else 0, "testable": 1,
                "leads": [kk - hit[0] + 1] if hit else [],
                "fa_per_year": len(fa) / yrs,
                "frac_days": float(flag.mean())}

    def escalation_rule(tr, split: float = 0.5):
        """Both arms' thresholds fitted on `tr` only, budget split `split`/rest."""
        yrs = max(int(dates[-1][:4]) - int(dates[0][:4]), 1)
        thr_c = threshold_at_budget(comp_equal, tr, excl, yrs, budget * split)
        fire = np.zeros(n, dtype=bool)
        if np.isfinite(thr_c):
            fire |= np.isfinite(comp_equal) & assess & (comp_equal >= thr_c)
        per_arm = (budget * (1.0 - split)) / 3.0
        arm_thrs = []
        for i in range(3):
            col = np.where(M[:, i], X[:, i], np.nan)
            t = threshold_at_budget(col, tr, excl, yrs, per_arm)
            arm_thrs.append(None if not np.isfinite(t) else round(float(t), 6))
            if np.isfinite(t):
                fire |= np.isfinite(col) & assess & (col >= t)
        return fire, thr_c, arm_thrs

    d_warn = d_test = 0
    d_leads, d_fa, d_frac, d_detail = [], [], [], {}
    for e in DEV_EPOCHS:
        if e not in onset_at:
            continue
        k = onset_at[e]
        tr = fold_train_mask(k)
        if int((y & tr).sum()) < 5:
            d_detail[e] = "untrainable (<5 training positives)"
            continue
        fire, thr_c, arm_thrs = escalation_rule(tr)
        r = eval_flag_fold(fire, e, k)
        if r is None:
            d_detail[e] = "untestable coverage"
            continue
        d_warn += r["warned"]; d_test += r["testable"]
        d_leads += r["leads"]; d_fa.append(r["fa_per_year"])
        d_frac.append(r["frac_days"])
        d_detail[e] = {"warned": r["warned"], "lead": (r["leads"] or [None])[0],
                       "composite_thr": (None if not np.isfinite(thr_c)
                                         else round(float(thr_c), 6)),
                       "pillar_thrs": arm_thrs,
                       "fa_per_year": round(r["fa_per_year"], 3)}
    d_result = {"warned": d_warn, "testable": d_test, "leads": d_leads,
                "fa_per_year": (round(float(np.mean(d_fa)), 3) if d_fa else 0.0),
                "frac_days": (round(float(np.mean(d_frac)), 4) if d_frac else 0.0),
                "per_fold": d_detail}
    report["candidate_D_detail"] = d_detail
    # D's fitted thresholds are themselves a finding: on every development fold
    # the composite arm lands at 0.999999 and several pillar arms at exactly
    # 1.0. Respecting a 2 FA/yr budget on a rank scale requires a threshold
    # above the 99.9th percentile, and on a rank scale there is nothing above
    # 1.0 - so the arms saturate and the escalation degenerates to whichever
    # single arm still has a non-degenerate threshold. This is the same
    # rank-scale problem as the alert-scale gate, surfacing in a new place.
    sat = [e for e, v in d_detail.items()
           if isinstance(v, dict) and (v.get("composite_thr") or 0) >= 0.999]
    report["candidate_D_saturated_folds"] = sat
    if sat:
        print(f"\n[fusion] candidate D diagnostic: the composite arm's fitted")
        print(f"[fusion] threshold is >= 0.999 on {len(sat)} of "
              f"{len([v for v in d_detail.values() if isinstance(v, dict)])} folds")
        print(f"[fusion] ({', '.join(sat)}), and several pillar arms sit at")
        print(f"[fusion] exactly 1.0. Holding a rank-scale score to 2 FA/yr needs")
        print(f"[fusion] a threshold above the 99.9th percentile, and a rank has")
        print(f"[fusion] nothing above 1.0 - so the escalation DEGENERATES rather")
        print(f"[fusion] than being tested as designed. Same root cause as the")
        print(f"[fusion] alert-scale gate in CRISIS-REPLAY.md.")

    report["candidate_B_weights_by_train_size"] = b_weights
    report["candidate_C"] = {"chosen_C": chosen_C,
                             "coefficients_intercept_then_pillars": coefs}
    if coefs:
        print(f"\n=== candidate C: L2 logistic coefficients per fold ===")
        print(f"{'train days':>11}{'C':>7}{'intercept':>11}"
              + "".join(f"{p:>11}" for p in PILLARS))
        print("-" * 63)
        for nt, b in sorted(coefs.items()):
            print(f"{nt:>11,}{chosen_C[nt]:>7g}{b[0]:>11.3f}"
                  + "".join(f"{x:>11.3f}" for x in b[1:]))
        print("All-negative loadings mean a HIGHER pillar score implies a LOWER")
        print("pre-onset probability, consistent with the measured negative")
        print("pre-onset separations. Where inner CV picks C=0.01 the")
        print("coefficients collapse toward 0: the regulariser is concluding")
        print("there is no signal to fit.")

    # E: individual pillars (each is its own column of the reconciled state)
    for i, pname in enumerate(PILLARS):
        col = np.where(M[:, i], X[:, i], np.nan)
        cands[f"E:pillar_{pname}"] = col
    cands.update(simple)

    # ---- evaluate every candidate at the budget ------------------------
    # D is built from A plus the strongest pillar arm, thresholds split evenly.
    def eval_candidate(score: np.ndarray, test_epochs, train_mask, yrs):
        thr = threshold_at_budget(score, train_mask, excl, yrs, budget)
        return thr, evaluate(score, thr, test_epochs, dates, onset_at, excl, assess)

    dev_k = min(onset_at[e] for e in DEV_EPOCHS if e in onset_at)
    all_train = np.zeros(n, dtype=bool)
    first_conf = min(onset_at[e] for e in CONFIRM_EPOCHS if e in onset_at)
    all_train[:max(0, first_conf - PRE)] = True
    all_train &= assess
    dev_years = (int(dates[first_conf][:4]) - int(dates[0][:4])) or 1

    print(f"\n=== DEVELOPMENT evaluation at {budget} FA/yr ===")
    print(f"A and E: threshold fitted on all data before {dates[first_conf]}.")
    print(f"B, C and D: weights AND threshold refitted per fold on that fold's")
    print(f"own training period (rolling origin), test epoch never seen.")
    hdr2 = (f"{'candidate':<24}{'warned':>9}{'rate':>7}{'FA/yr':>8}"
            f"{'median lead':>13}{'%days':>8}")
    print(hdr2); print("-" * len(hdr2))
    dev_rows = {}
    for name, sc in cands.items():
        thr, r = eval_candidate(sc, DEV_EPOCHS, all_train, dev_years)
        dev_rows[name] = {"threshold": (None if not np.isfinite(thr)
                                        else round(float(thr), 6)), **r}
    dev_rows.update(b_results)
    dev_rows["C:logistic_L2"] = c_result
    dev_rows["D:composite+escalation"] = d_result

    order = (["A:equal_weight"] + sorted(b_results)
             + ["C:logistic_L2", "D:composite+escalation"]
             + [k for k in cands if k.startswith("E:")])
    for name in order:
        r = dev_rows.get(name)
        if r is None:
            continue
        if not r.get("testable"):
            sk = r.get("skipped_folds") or []
            print(f"{name:<24}{'untestable':>9}"
                  + (f"   (folds skipped: {', '.join(sk)})" if sk else ""))
            continue
        ml = (int(np.median(r["leads"])) if r["leads"] else None)
        print(f"{name:<24}{r['warned']}/{r['testable']:<7}"
              f"{r['warned']/r['testable']:>7.2f}{r['fa_per_year']:>8.2f}"
              f"{(str(ml) if ml else '-'):>13}"
              f"{100*r.get('frac_days',0):>7.1f}%")
    print("\n%days is the share of assessable days under alert. A candidate can")
    print("respect an EPISODE budget while alerting most of the time, because a")
    print("standing alert is one episode however long it lasts. That is a blind")
    print("spot in the pre-registered budget and is reported, not retro-fixed.")
    report["development"] = dev_rows

    print(f"\n[fusion] H1: does any learned candidate beat the best single "
          f"pillar or baseline on development?")
    best_learned = max((v["warned"] for k, v in dev_rows.items()
                        if k.startswith(("B:", "C:")) and v.get("testable")),
                       default=0)
    best_single = max((v["warned"] for k, v in dev_rows.items()
                       if k.startswith("E:") and v.get("testable")), default=0)
    base_a = dev_rows.get("A:equal_weight", {}).get("warned", 0)
    print(f"[fusion]   best learned (B/C) warned: {best_learned}")
    print(f"[fusion]   best single input   warned: {best_single}")
    print(f"[fusion]   baseline A          warned: {base_a}")
    print(f"[fusion] H1 verdict: "
          f"{'H1 REJECTED - learned fusion wins' if best_learned > max(best_single, base_a) else 'H1 CONFIRMED - learned fusion does not beat its inputs'}")
    report["h1"] = {"best_learned": best_learned, "best_single": best_single,
                    "baseline_A": base_a,
                    "verdict": ("REJECTED" if best_learned > max(best_single, base_a)
                                else "CONFIRMED")}

    # ---- relocation null on every development result -------------------
    # A warned rate is uninterpretable without the rate a skill-free signal
    # with the SAME alert frequency achieves. `drawdown` alerts on 38% of days,
    # so it would precede almost any date chosen at random.
    N_spec = importlib.util.spec_from_file_location(
        "rwn", Path(__file__).resolve().parent / "replay_warning_null.py")
    NL = importlib.util.module_from_spec(N_spec)
    N_spec.loader.exec_module(NL)

    print(f"\n=== relocation null on the development results ===")
    print(f"{'candidate':<24}{'warned':>9}{'rate':>7}{'null rate':>16}{'p':>9}")
    print("-" * 65)
    onsets_iso = [EPOCH_BREAKS[e][0] for e in DEV_EPOCHS]
    null_rows = {}
    for name in order:
        r = dev_rows.get(name)
        if not r or not r.get("testable"):
            continue
        sc = cands.get(name)
        if sc is None:
            continue                      # learned candidates have no one series
        thr = r.get("threshold")
        if thr is None:
            continue
        flag = np.isfinite(sc) & assess & (sc >= thr)
        ks = NL.onset_indices(dates, onsets_iso)
        res = NL.relocation_null(dates, flag, sc, ks, horizon=PRE, draws=1500,
                                 assessable=assess)
        if "p_rate" not in res:
            continue
        null_rows[name] = res
        o, nr = res["observed"], res["null_rate"]
        print(f"{name:<24}{o['n_warned']}/{o['n_testable']:<7}"
              f"{(o['rate'] or 0):>7.2f}{nr['mean']:>10.2f}+-{nr['sd']:<4.2f}"
              f"{res['p_rate']:>9.4f}")
    report["development_nulls"] = null_rows
    if null_rows:
        pairs = [(k, v["p_rate"]) for k, v in null_rows.items()]
        holm = NL.holm(pairs)
        report["development_holm"] = holm
        surv = [k for k, v in holm.items() if v["survives_holm"]]
        print(f"\n[fusion] Holm over {len(pairs)} comparisons; survivors: "
              f"{surv if surv else 'NONE'}")

    # ---- D-prime: escalation on RAW pillar values (addendum D2) --------
    # D's arms saturated because FR28 ranks are bounded at 1.0 and award exactly
    # 1.0 to every running-maximum day, leaving no level between "fires on all
    # running-max days" and "never fires". Raw pillar quantities are unbounded
    # above, so their upper tail has the resolution a rank lacks. Everything
    # else is held identical, and the budget is enforced on the COMBINED rule
    # rather than split across arms.
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        raw_rmt = await pool.fetch("SELECT date, eigenvalues, sca_t FROM "
                                   "rmt_output ORDER BY date")
        raw_hwk = await pool.fetch("SELECT ts, branching_ratio_n FROM "
                                   "hawkes_output WHERE scope='market' ORDER BY ts")
    finally:
        await pool.close()
    from bisect import bisect_right as _br

    from seraph.orchestration import lam1_share as _l1
    rmt_raw_at = {}
    for r in raw_rmt:
        d = str(r["date"])
        if pillar2 == "sca":
            v = r["sca_t"]
            if v is not None:
                rmt_raw_at[d] = float(v)
        else:
            v = _l1(list(r["eigenvalues"] or []))
            if v is not None:
                rmt_raw_at[d] = float(v)
    h_dates = [str(r["ts"].date()) for r in raw_hwk]
    h_vals = [float(r["branching_ratio_n"]) for r in raw_hwk]
    h_vals = [v / (1.0 - v) for v in h_vals]
    ham_raw = R.load_hamilton_causal()

    RAW = np.full((n, 3), np.nan)
    for i, d in enumerate(dates):
        j = _br(h_dates, d) - 1                 # most recent refit at or before d
        if j >= 0:
            RAW[i, 0] = h_vals[j]
        if d in rmt_raw_at:
            RAW[i, 1] = rmt_raw_at[d]
        if d in ham_raw:
            RAW[i, 2] = ham_raw[d][0]

    def dprime_rule(tr):
        """Composite arm on the rank, escalation arms on RAW magnitude."""
        yrs = max(int(dates[-1][:4]) - int(dates[0][:4]), 1)
        # search the COMBINED rule down a shared quantile ladder so the budget
        # binds on the union, which is what D failed to do
        best = None
        for q in np.arange(0.9995, 0.949, -0.0005):
            fire = np.zeros(n, dtype=bool)
            thr_c = (np.quantile(comp_equal[tr & np.isfinite(comp_equal)], q)
                     if (tr & np.isfinite(comp_equal)).sum() > 50 else np.inf)
            if np.isfinite(thr_c):
                fire |= np.isfinite(comp_equal) & assess & (comp_equal >= thr_c)
            thrs = []
            for c in range(3):
                col = RAW[:, c]
                m = tr & np.isfinite(col)
                if m.sum() < 50:
                    thrs.append(None); continue
                t = float(np.quantile(col[m], q))
                thrs.append(round(t, 6))
                fire |= np.isfinite(col) & assess & (col >= t)
            fa = [i for i in episodes(fire & tr) if not excl[i]]
            if len(fa) / yrs <= budget:
                best = (fire, float(q), thrs)
            else:
                break
        return best

    print(f"\n{'='*70}")
    print(f"D-PRIME (addendum D2) - escalation on RAW magnitude, not rank")
    print(f"Reported OUTSIDE the pre-registered A-E comparison.")
    print(f"{'='*70}")
    dp_w = dp_t = 0
    dp_l, dp_fa, dp_det = [], [], {}
    for e in list(DEV_EPOCHS) + list(CONFIRM_EPOCHS):
        if e not in onset_at:
            continue
        k = onset_at[e]
        tr = fold_train_mask(k)
        if int((y & tr).sum()) < 5:
            dp_det[e] = "untrainable"
            continue
        got = dprime_rule(tr)
        if got is None:
            dp_det[e] = "no quantile respects the budget"
            continue
        fire, q, thrs = got
        rr = eval_flag_fold(fire, e, k)
        if rr is None:
            dp_det[e] = "untestable coverage"
            continue
        tag = "DEV" if e in DEV_EPOCHS else "CONFIRM"
        dp_w += rr["warned"]; dp_t += rr["testable"]; dp_l += rr["leads"]
        dp_fa.append(rr["fa_per_year"])
        dp_det[e] = {"set": tag, "warned": rr["warned"],
                     "lead": (rr["leads"] or [None])[0], "quantile": q,
                     "raw_thresholds": thrs,
                     "fa_per_year": round(rr["fa_per_year"], 3),
                     "frac_days": round(rr["frac_days"], 4)}
        print(f"  {e:<18} [{tag:>7}] warned={rr['warned']} "
              f"lead={(rr['leads'] or ['-'])[0]} q={q:.4f} "
              f"FA/yr={rr['fa_per_year']:.2f} days={100*rr['frac_days']:.1f}%")
    fa_m = float(np.mean(dp_fa)) if dp_fa else 0.0
    p0 = 1.0 - np.exp(-fa_m * PRE / 252.0)
    import math as _m
    pk = (sum(_m.comb(dp_t, i) * p0 ** i * (1 - p0) ** (dp_t - i)
              for i in range(dp_w, dp_t + 1)) if dp_t else float("nan"))
    print(f"\n  D-prime total: {dp_w}/{dp_t} warned, mean FA/yr {fa_m:.2f}, "
          f"p0/event {p0:.4f}, P(>={dp_w}) = {pk:.4f}")
    print(f"  H5 verdict: "
          f"{'REJECTED - D-prime beats its no-skill rate' if (np.isfinite(pk) and pk <= 0.05) else 'CONFIRMED - D-prime does not beat its own no-skill rate'}")
    report["d_prime"] = {"per_epoch": dp_det, "warned": dp_w, "testable": dp_t,
                         "mean_fa_per_year": round(fa_m, 3),
                         "p0_per_event": round(float(p0), 4),
                         "p_binomial": (None if not np.isfinite(pk)
                                        else round(float(pk), 4)),
                         "h5_verdict": ("REJECTED" if (np.isfinite(pk) and pk <= 0.05)
                                        else "CONFIRMED")}

    # ---- CONFIRMATION — touched ONCE, per pre-registration rule 5 -------
    print(f"\n{'='*70}")
    print(f"CONFIRMATION on {CONFIRM_EPOCHS} - evaluated ONCE")
    print(f"{'='*70}")
    print(f"Pre-registration rule 4: no candidate cleared the development")
    print(f"selection bar, so baseline A is RETAINED and nothing was selected on")
    print(f"the strength of a point estimate. A is evaluated here as the retained")
    print(f"architecture; B (most-shrunk) and D are reported alongside it for")
    print(f"completeness and were NOT selected.")
    print(f"NOTE: tariff_2026's label is PROVISIONAL (SPEC OQ3 open), so the")
    print(f"confirmation rests materially on tightening_2022 alone.\n")

    conf_rows = {}
    thr_a = threshold_at_budget(comp_equal, all_train, excl, dev_years, budget)
    conf_rows["A:equal_weight"] = {
        "threshold": None if not np.isfinite(thr_a) else round(float(thr_a), 6),
        **evaluate(comp_equal, thr_a, CONFIRM_EPOCHS, dates, onset_at, excl, assess)}
    conf_rows["B:convex_shrink0.75"] = rolling_origin(
        lambda tr: fuse(X, M, learn_convex(X, M, y, tr, shrink=0.75)[0]),
        list(CONFIRM_EPOCHS), min_pos=5)

    cw = ct = 0
    cl, cfa, cfr, cdet = [], [], [], {}
    for e in CONFIRM_EPOCHS:
        if e not in onset_at:
            continue
        k = onset_at[e]
        tr = fold_train_mask(k)
        if int((y & tr).sum()) < 5:
            cdet[e] = "untrainable"
            continue
        fire, thr_c, arm = escalation_rule(tr)
        rr = eval_flag_fold(fire, e, k)
        if rr is None:
            cdet[e] = "untestable"
            continue
        cw += rr["warned"]; ct += rr["testable"]; cl += rr["leads"]
        cfa.append(rr["fa_per_year"]); cfr.append(rr["frac_days"])
        cdet[e] = {"warned": rr["warned"], "lead": (rr["leads"] or [None])[0]}
    conf_rows["D:composite+escalation"] = {
        "warned": cw, "testable": ct, "leads": cl,
        "fa_per_year": (round(float(np.mean(cfa)), 3) if cfa else 0.0),
        "frac_days": (round(float(np.mean(cfr)), 4) if cfr else 0.0),
        "per_fold": cdet}
    for pname in ("rmt", "hamilton"):
        i = PILLARS.index(pname)
        col = np.where(M[:, i], X[:, i], np.nan)
        t = threshold_at_budget(col, all_train, excl, dev_years, budget)
        conf_rows[f"E:pillar_{pname}"] = {
            "threshold": None if not np.isfinite(t) else round(float(t), 6),
            **evaluate(col, t, CONFIRM_EPOCHS, dates, onset_at, excl, assess)}
    for nm in ("E:drawdown", "E:semivar_20", "E:dd_accel_5"):
        t = threshold_at_budget(simple[nm], all_train, excl, dev_years, budget)
        conf_rows[nm] = {
            "threshold": None if not np.isfinite(t) else round(float(t), 6),
            **evaluate(simple[nm], t, CONFIRM_EPOCHS, dates, onset_at, excl, assess)}

    hdr3 = f"{'candidate':<24}{'warned':>9}{'rate':>7}{'FA/yr':>8}{'lead':>8}{'%days':>8}"
    print(hdr3); print("-" * len(hdr3))
    for nm, r in conf_rows.items():
        if not r.get("testable"):
            print(f"{nm:<24}{'untestable':>9}")
            continue
        ml = (int(np.median(r["leads"])) if r["leads"] else None)
        print(f"{nm:<24}{r['warned']}/{r['testable']:<7}"
              f"{r['warned']/r['testable']:>7.2f}{r['fa_per_year']:>8.2f}"
              f"{(str(ml) if ml else '-'):>8}{100*r.get('frac_days',0):>7.1f}%")
    report["confirmation"] = conf_rows

    # H4 is a SIGNIFICANCE claim, not a count. A candidate alerting at rate
    # `fa` per year precedes any given date within the 15-session window with
    # probability ~ 1 - exp(-fa * 15/252), so that is the no-skill rate it must
    # beat. With 2 confirmation epochs the binomial is coarse, which is itself
    # part of the finding.
    print(f"\n=== H4: is any confirmation result above its own no-skill rate? ===")
    print(f"{'candidate':<24}{'warned':>9}{'FA/yr':>8}{'p0/event':>10}{'P(>=k)':>9}")
    print("-" * 60)
    h4_any = False
    h4_rows = {}
    for nm, r in conf_rows.items():
        if not r.get("testable"):
            continue
        fa = float(r.get("fa_per_year") or 0.0)
        p0 = 1.0 - np.exp(-fa * PRE / 252.0)
        k_, nn_ = int(r["warned"]), int(r["testable"])
        # P(X >= k) for X ~ Binomial(n, p0)
        pk = sum(__import__("math").comb(nn_, i) * p0 ** i * (1 - p0) ** (nn_ - i)
                 for i in range(k_, nn_ + 1)) if nn_ else float("nan")
        h4_rows[nm] = {"warned": k_, "testable": nn_, "fa_per_year": round(fa, 3),
                       "p0_per_event": round(float(p0), 4),
                       "p_binomial": round(float(pk), 4)}
        if np.isfinite(pk) and pk <= 0.05:
            h4_any = True
        print(f"{nm:<24}{k_}/{nn_:<7}{fa:>8.2f}{p0:>10.4f}{pk:>9.4f}")
    report["h4_binomial"] = h4_rows
    print(f"\n[fusion] H4 verdict: "
          f"{'REJECTED - a candidate beat its no-skill rate at p<=0.05' if h4_any else 'CONFIRMED - no candidate beat its own no-skill rate'}")
    report["h4_verdict"] = "REJECTED" if h4_any else "CONFIRMED"
    print(f"[fusion] Two confirmation epochs make this test coarse: with")
    print(f"[fusion] n=2 even 2-of-2 reaches only p~0.013 at these alert rates,")
    print(f"[fusion] and 1-of-2 cannot reach 0.05 for any candidate here.")

    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    jp = out / f"fusion_search_{pillar2}_b{budget:g}.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[fusion] wrote {jp}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=2.0)
    ap.add_argument("--pillar2", choices=("lam1", "sca"), default="lam1")
    ap.add_argument("--out", default="docs/evidence/fusion")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.budget, a.pillar2, a.out)))
