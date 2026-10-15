#!/usr/bin/env python3
# Orchestration/C10 — unified causal historical replay (FR32, FR35, O5, O7).
"""**Would SERAPH have warned before each historical crisis?**

This is the first run in this repository that answers that question end to end
with a single causal pass. Everything else so far measured either contemporaneous
separation (T1) or a single aggregate lead statistic (T3). Neither tells you what
a live operator would have seen on a given morning in September 2008.

## What makes this a replay rather than a backtest-shaped evaluation

Every value at decision date `t` is computed from inputs dated `<= t`:

* **Pillar 2 (RMT)** — `lambda_1` share from `rmt_output`, daily, 2005-01-03+.
* **Pillar 1 (Hawkes)** — branching ratio from `hawkes_output`, selected by the
  refit's *actual timestamp* (`bisect_right` on `ts`, not on `date`), so the
  15:30 decision never receives a kernel refitted at 18:55 on a Muhurat session.
  Carried forward between refits and aged by C8's `R(t - tau)`, which is what D4
  is for. **`refit_every = 5` sessions** (HAWKES-WINDOW-SELECTION.md), so a
  5-15 day lead window contains at most 2-3 independent Hawkes observations.
* **Pillar 3 (Hamilton)** — the causal walk-forward `LSD_t = xi_2 + 2 xi_3` from
  `causal_xi_NOT_PRODUCTION.npz`, produced by the POSTFIX run with the repaired
  engine. Its own file name records that it is not production output. Its causal
  series **begins 2013-01-14**, because the walk-forward consumes the first 2,000
  observations as an initial training window.
* **Standardisation** — FR28's rolling 5-year ECDF via `window_from`, which
  selects on the ISO string and is inclusive of `as_of` only.
* **Fusion** — the real C8 `KalmanReconciler` and the real, pure C9 `score()`.

## The two things this run is designed not to do

1. **Not to confuse a crisis reading with a warning.** Every verdict is decided
   on the window strictly *before* the labelled onset. A signal that only lights
   up on day +1 scores `FAIL`, however large it gets.
2. **Not to pick its threshold on the episodes it is judged by.** Two rules are
   reported, both fixed before any epoch was examined:

   * **Rule A — frozen production config.** `CSRS >= 0.50`, C9's
     `PROVISIONAL_AMBER`. A declared constant in the shipped code, so it cannot
     have been fitted here. Only applies to CSRS-scale signals.
   * **Rule B — causal adaptive quantile.** The signal exceeds its own trailing
     5-year 95th percentile, computed from data `< t`. Scale-free, so it applies
     identically to a CSRS and to a raw volatility level, which is what makes the
     pillar-vs-baseline comparison in section 2 of the directive meaningful.
     Nothing about the crisis dates enters it.

   Rule B is the primary comparable rule. Rule A is reported because it is what
   the system would actually have done.

## Scope limits, stated rather than discovered later

* `hamilton` here is **exploratory**. Its regime structure is indistinguishable
  from a single-regime AR(1) surrogate (AAFT p = 0.714, AR(1) p = 0.952 —
  HAMILTON-REGIME-SUPPORT.md) and all 14 causal blocks hit a parameter boundary.
  It is replayed because FR35 requires every subset to be *evaluated*, and
  omitting it would be the silent removal AGENTS.md forbids. It is **not**
  promoted into any production composite, and no result here authorises that.
* The 2008 GFC cannot be replayed for Hamilton at all. SPEC section 4's coverage
  matrix marks Hamilton available for 2008; that is true only of an in-sample
  fit, which uses 2013 data to parameterise a 2008 decision. The causal answer
  is `UNTESTABLE`, and that is reported as such rather than filled in.
* Six onsets. Every per-epoch verdict is a single observation, and the
  aggregate statistics carry the power limits measured in EARLY-WARNING-POWER.md
  (actual type-I 8% at nominal 5%; MDE ~ 1.0 sd).

Run (read-only, writes nothing to the database):
  python scripts/replay_crisis_warnings.py --out docs/evidence/replay
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from bisect import bisect_left, bisect_right
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.fusion.score import PROVISIONAL_AMBER, score  # noqa: E402
from seraph.orchestration import (  # noqa: E402
    close_ts,
    hamilton_emission,
    hawkes_contagion_emission,
    lam1_share,
    rmt_emission,
    window_from,
)
from seraph.orchestration.standardize import standardise  # noqa: E402
from seraph.reconciliation.kalman import KalmanReconciler  # noqa: E402
from seraph.shared_types import (  # noqa: E402
    PILLAR_ORDER,
    ObservedEmission,
    PillarObservation,
    CalibrationConfig,
    FusionWeights,
    UnavailableEmission,
    ist_timestamp,
)
from seraph.shared_types.fusion import fusion_weights_artefact_id  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import (  # noqa: E402
    CRISIS_WINDOW_DAYS,
    EPOCH_BREAKS,
    LEAD_WINDOW_DAYS,
)

EQUAL = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
HAM_NPZ = (Path(__file__).resolve().parent.parent / "docs" / "evidence"
           / "20261013T023028Z-hamilton-causal-POSTFIX"
           / "causal_xi_NOT_PRODUCTION.npz")

#: FR35's seven pillar subsets, in PILLAR_ORDER terms.
SUBSETS: dict[str, tuple[bool, bool, bool]] = {
    "hawkes":              (True,  False, False),
    "rmt":                 (False, True,  False),
    "hamilton":            (False, False, True),
    "hawkes+rmt":          (True,  True,  False),
    "hawkes+hamilton":     (True,  False, True),
    "rmt+hamilton":        (False, True,  True),
    "hawkes+rmt+hamilton": (True,  True,  True),
}

#: Lead horizons evaluated. FR32's own early-warning window is 5-15 days.
HORIZONS = (5, 10, 15, 20, 30)

#: Rule B quantile and the minimum trailing sample before a quantile is emitted.
RULE_B_Q = 0.95
RULE_B_MIN_OBS = 250


# --------------------------------------------------------------------------
# causal transforms
# --------------------------------------------------------------------------
def causal_quantile_flags(dates: list[str], vals: np.ndarray, *,
                          q: float = RULE_B_Q,
                          min_obs: int = RULE_B_MIN_OBS,
                          years: int = 5,
                          with_assessable: bool = False):
    """Rule B: `vals[i]` strictly exceeds the trailing `years`-year `q` quantile.

    The threshold at index `i` is computed from indices `< i` only — `i` itself
    is excluded, so a value can never help set the bar it is being judged
    against. Emits `False` (not NaN) while the trailing sample is below
    `min_obs`, which makes an un-assessable early period score as "no warning"
    rather than silently vanishing from the denominator.
    """
    out = np.zeros(vals.size, dtype=bool)
    ok = np.zeros(vals.size, dtype=bool)
    for i, d in enumerate(dates):
        if not np.isfinite(vals[i]):
            continue
        # trailing window [d-years, i-1]: bisect gives the lower edge, and the
        # slice stops at i, so index i is excluded from its own threshold.
        lo = bisect_left(dates, f"{int(d[:4]) - years:04d}{d[4:]}")
        hist = vals[lo:i]
        hist = hist[np.isfinite(hist)]
        if hist.size < min_obs:
            continue
        ok[i] = True
        out[i] = bool(vals[i] > float(np.quantile(hist, q)))
    return (out, ok) if with_assessable else out


def realised_vol(lr: np.ndarray, w: int = 20) -> np.ndarray:
    """Trailing `w`-day realised volatility, causal. out[i] uses lr[i-w+1..i]."""
    out = np.full(lr.size, np.nan)
    for i in range(lr.size):
        seg = lr[max(0, i - w + 1):i + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size >= max(3, w // 4):
            out[i] = float(seg.std(ddof=1)) if seg.size > 1 else np.nan
    return out


def drawdown(lr: np.ndarray) -> np.ndarray:
    """Drawdown of the cumulative index from its running max, causal by construction.

    The running max at `i` uses only `lr[:i+1]`, so no future peak can deepen a
    past drawdown. Returned positive (0 = at the high).
    """
    r = np.where(np.isfinite(lr), lr, 0.0)
    idx = np.exp(np.cumsum(r))
    peak = np.maximum.accumulate(idx)
    return np.asarray(1.0 - idx / peak, dtype=float)


def downside_semivariance(lr: np.ndarray, w: int = 20) -> np.ndarray:
    """sqrt(mean(min(r,0)^2)) over the trailing `w` days, causal.

    Lifted verbatim in behaviour from `run_csrs_research.py` so the replay's
    comparator is the *same* `semivar_20` the rest of the project reports, not a
    near-miss reimplementation. Only negative returns contribute, so an
    upside-volatility episode does not register as stress, and `out[i]` reads
    `lr[i-w+1 .. i]` inclusive - never the future.

    Included because it is the repository's strongest known single feature:
    Workstream C measured that leave-one-epoch-out selection picks it on 4 of 6
    folds, ahead of both acceleration signals. Comparing the pillars only
    against weaker baselines would have flattered them.
    """
    neg2 = np.minimum(lr, 0.0) ** 2
    out = np.full(lr.size, np.nan)
    for i in range(lr.size):
        seg = neg2[max(0, i - w + 1):i + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size >= max(3, w // 4):
            out[i] = float(np.sqrt(seg.mean()))
    return out


def accel(x: np.ndarray, lag: int = 5) -> np.ndarray:
    """`x[i] - x[i-lag]`, a strictly backward difference. NaN for i < lag."""
    out = np.full(x.size, np.nan)
    if x.size > lag:
        out[lag:] = x[lag:] - x[:-lag]
    return out


# --------------------------------------------------------------------------
# Pillar 2's input quantity - a specification conformance question
# --------------------------------------------------------------------------
#: Which quantity stands for Pillar 2. "lam1" reproduces the shipped pipeline;
#: "sca" uses the quantity SPEC FR18 actually names.
#
# SPEC FR18: "The system shall aggregate the three spectral signals into `SCA_t`
# using calibrated weights `w^p`." FR17 emits `F_t`, `V_t^eig` and `Omega_t`.
# `rmt_output` stores all four. But `seraph/orchestration/adapters.py`'s
# `rmt_emission` standardises `lam1_share = lambda_1 / N`, which is named nowhere
# in FR16-FR19, and `sca_t` - computed, validated at 29/29 acceptance checks and
# persisted - is never read by the fusion path.
#
# This flag exists to measure the difference rather than argue about it. It is an
# isolated, reversible experiment in a research script: **nothing in `seraph/` is
# changed by it**, and switching production to SCA_t is an approval decision for
# C6/orchestration's owner, not something this script does.
PILLAR2_MODES = ("lam1", "sca")


def rmt_emission_sca(*, date: str, sca: float | None, window):
    """FR18 variant of `rmt_emission`, identical except for the raw quantity.

    Deliberately mirrors the production adapter line for line - same
    `standardise` call, same `estimation_variance=None` (C6 publishes no
    per-date sampling variance for `SCA_t` either, and inventing one would be
    fabrication) - so any measured difference is attributable to the input
    quantity and to nothing else.
    """
    ts = close_ts(date)
    if sca is None or not np.isfinite(sca):
        return UnavailableEmission(pillar="rmt", ts=ts, absence="transient",
                                   reason="estimation_failed"), ()
    value, variance, warns = standardise(
        float(sca), window=window, raw_variance=None, pillar="rmt")
    return ObservedEmission(obs=PillarObservation(
        pillar="rmt", ts=ts, tau=ts, value=value,
        estimation_variance=variance)), warns


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------
async def load_all(pool) -> dict:
    rmt = await pool.fetch("SELECT date, eigenvalues, sca_t FROM rmt_output "
                           "ORDER BY date")
    hwk = await pool.fetch("SELECT ts, branching_ratio_n FROM hawkes_output "
                           "WHERE scope='market' ORDER BY ts")
    mkt = await pool.fetch("""
      WITH r AS (SELECT date, symbol,
                   ln(adj_close / NULLIF(lag(adj_close)
                      OVER (PARTITION BY symbol ORDER BY date),0)) lr
                 FROM daily_prices WHERE universe_member_flag AND adj_close > 0)
      SELECT date, avg(lr) mkt FROM r WHERE lr IS NOT NULL GROUP BY date ORDER BY date""")
    return {"rmt": rmt, "hwk": hwk, "mkt": mkt}


def load_hamilton_causal() -> dict[str, tuple[float, float]]:
    """date -> (lsd, variance) for the causal walk-forward only.

    Entries before `first_causal_index` are deliberately absent: the warm-up
    period has no causal estimate, and fabricating one by reusing the in-sample
    fit is exactly the look-ahead this script exists to avoid.
    """
    if not HAM_NPZ.exists():
        return {}
    z = np.load(HAM_NPZ)
    fi = int(z["first_causal_index"])
    d, lsd, var = z["dates"], z["lsd"], z["variance"]
    out: dict[str, tuple[float, float]] = {}
    for i in range(fi, len(d)):
        if np.isfinite(lsd[i]):
            v = float(var[i]) if np.isfinite(var[i]) else None
            out[str(d[i])] = (float(lsd[i]), v)
    return out


# --------------------------------------------------------------------------
# the replay
# --------------------------------------------------------------------------
def subset_weights(mask: tuple[bool, bool, bool]) -> FusionWeights:
    """Equal weights with the subset bound into the artefact id.

    `mask_profile` differs per subset, so each configuration hashes to its own
    id. Nothing here is calibrated and `epochs=()` says so.
    """
    cfg = CalibrationConfig(epochs=(), fold_held_out=None,
                            kappa_miss=1.0, kappa_fa=1.0, mask_profile=mask)
    w = (EQUAL, EQUAL, EQUAL)
    return FusionWeights(artefact_id=fusion_weights_artefact_id(w, cfg),
                         calibrated_on=cfg, w=w)


def replay_subset(name: str, mask: tuple[bool, bool, bool], *, grid: list[str],
                  lam_by_date, lam_series, hwk_pts, hwk_ts_only, hwk_series,
                  ham, pillar2: str = "lam1", sca_by_date=None,
                  sca_series=None) -> tuple[list[str], np.ndarray, dict]:
    """One causal pass over the whole grid for one pillar subset."""
    use_h, use_r, use_m = mask
    weights = subset_weights(mask)
    rec = KalmanReconciler()
    out_d, out_v, fails, warn = [], [], 0, {}
    for d in grid:
        ts = close_ts(d)
        ems = []

        # ---- Pillar 1: hawkes ------------------------------------------
        if use_h:
            i = bisect_right(hwk_ts_only, datetime.fromisoformat(ts)) - 1
            if i >= 0:
                _, n, tau = hwk_pts[i]
                e, w = hawkes_contagion_emission(
                    ts=ts, tau=tau, branching_ratio=n,
                    window=window_from(hwk_series, d))
            else:
                e, w = UnavailableEmission(pillar="hawkes", ts=ts,
                                           absence="structural",
                                           reason="no_data_coverage"), ()
        else:
            e, w = UnavailableEmission(pillar="hawkes", ts=ts,
                                       absence="structural",
                                       reason="no_data_coverage"), ()
        ems.append(e)
        for x in w:
            warn[x.code] = warn.get(x.code, 0) + 1

        # ---- Pillar 2: rmt ---------------------------------------------
        if use_r:
            if pillar2 == "sca":
                e, w = rmt_emission_sca(
                    date=d, sca=sca_by_date.get(d),
                    window=window_from(sca_series, d))
            else:
                e, w = rmt_emission(date=d, eigenvalues=lam_by_date.get(d),
                                    window=window_from(lam_series, d))
        else:
            e, w = UnavailableEmission(pillar="rmt", ts=ts,
                                       absence="structural",
                                       reason="no_data_coverage"), ()
        ems.append(e)
        for x in w:
            warn[x.code] = warn.get(x.code, 0) + 1

        # ---- Pillar 3: hamilton ----------------------------------------
        if use_m:
            hit = ham.get(d)
            if hit is not None:
                lsd, var = hit
                e, w = hamilton_emission(
                    date=d, lsd=lsd, raw_variance=var,
                    window=window_from(ham_series_cache, d))
            else:
                # before 2013-01-14 there is no causal estimate at all
                e, w = UnavailableEmission(pillar="hamilton", ts=ts,
                                           absence="structural",
                                           reason="no_data_coverage"), ()
        else:
            e, w = UnavailableEmission(pillar="hamilton", ts=ts,
                                       absence="structural",
                                       reason="no_data_coverage"), ()
        ems.append(e)
        for x in w:
            warn[x.code] = warn.get(x.code, 0) + 1

        up = rec.update(ems)
        if up.status == "error":
            fails += 1
            continue
        sc = score(reconciled=up.value, xi=EQUAL, weights=weights,
                   xi_mode="uniform")
        if sc.status == "error":
            fails += 1
            continue
        out_d.append(d)
        out_v.append(sc.value.csrs)
    return out_d, np.asarray(out_v, dtype=float), {
        "failures": fails, "warnings": warn,
        "artefact_id": weights.artefact_id[:16]}


# module-level cache for hamilton's own ECDF window (set in main)
ham_series_cache: list[tuple[str, float]] = []


# --------------------------------------------------------------------------
# per-epoch assessment
# --------------------------------------------------------------------------
def assess_epoch(dates: list[str], flags: np.ndarray, vals: np.ndarray,
                 onset: str, *, horizon: int,
                 assessable: np.ndarray | None = None) -> dict:
    """The ten items the directive requires, decided on the PRE-onset window.

    `first_warning` is the earliest rising edge in `[onset-horizon, onset-1]`.
    Anything at or after `onset` is recorded separately as
    `during_or_after_only`, because that is detection, not warning.
    """
    di = {d: i for i, d in enumerate(dates)}
    # index of the last trading day strictly before onset
    pre = [i for i, d in enumerate(dates) if d < onset]
    at_or_after = [i for i, d in enumerate(dates) if d >= onset]
    if not pre:
        return {"verdict": "UNTESTABLE", "reason": "no causal data before onset",
                "coverage_days_pre": 0}
    k = pre[-1]
    lo = max(0, k - horizon + 1)
    win = range(lo, k + 1)
    covered = [i for i in win if np.isfinite(vals[i])]
    if not covered:
        return {"verdict": "UNTESTABLE",
                "reason": f"no finite signal in [onset-{horizon}, onset-1]",
                "coverage_days_pre": 0}
    # A day whose trailing window is too short to form a threshold cannot
    # produce an alert, so counting it as a missed warning would manufacture a
    # negative result out of an absent decision rule.
    if assessable is not None:
        usable = [i for i in covered if assessable[i]]
        if not usable:
            return {"verdict": "UNTESTABLE",
                    "reason": (f"alert threshold not computable anywhere in "
                               f"[onset-{horizon}, onset-1] (trailing sample "
                               f"below the {RULE_B_MIN_OBS}-observation floor)"),
                    "coverage_days_pre": len(covered),
                    "coverage_days_assessable": 0}
        covered = usable

    fired = [i for i in win if flags[i]]
    # rising edges only, so a standing alert is not re-counted every day
    edges = [i for i in fired if i == 0 or not flags[i - 1]]
    crisis_win = [i for i in at_or_after[:CRISIS_WINDOW_DAYS]]
    during = [i for i in crisis_win if flags[i]]

    res: dict = {
        "onset": onset,
        "horizon_days": horizon,
        "coverage_days_pre": len(covered),
        "coverage_days_requested": horizon,
        "first_warning_date": dates[edges[0]] if edges else None,
        "lead_time_days": (k - edges[0] + 1) if edges else None,
        "score_at_first_warning": (round(float(vals[edges[0]]), 6)
                                   if edges else None),
        "warned_pre_onset": bool(edges),
        "n_warning_days_pre": len(fired),
        "persisted_to_onset": bool(fired and flags[k]),
        "during_or_after_only": bool(not edges and during),
        "n_warning_days_in_crisis_window": len(during),
    }
    if edges:
        lead = res["lead_time_days"]
        lo_w, hi_w = LEAD_WINDOW_DAYS
        res["within_fr32_lead_window"] = bool(lo_w <= lead <= hi_w)
        res["verdict"] = "PASS"
    elif len(covered) < max(3, horizon // 3):
        res["verdict"] = "UNTESTABLE"
        res["reason"] = (f"only {len(covered)}/{horizon} pre-onset days have a "
                         f"finite causal value")
    else:
        res["within_fr32_lead_window"] = False
        res["verdict"] = "FAIL"
    return res


def false_alarms(dates: list[str], flags: np.ndarray,
                 onsets: list[str]) -> dict:
    """Rising edges outside every [onset-30, onset+30] window, as a yearly rate."""
    excl = np.zeros(len(dates), dtype=bool)
    for o in onsets:
        pre = [i for i, d in enumerate(dates) if d < o]
        if not pre:
            # onset precedes the series: exclude the first 30 days defensively
            continue
        k = pre[-1]
        excl[max(0, k - CRISIS_WINDOW_DAYS + 1):
             min(len(dates), k + 1 + CRISIS_WINDOW_DAYS)] = True
    edges = [i for i in range(len(dates))
             if flags[i] and (i == 0 or not flags[i - 1])]
    fa = [i for i in edges if not excl[i]]
    hits = [i for i in edges if excl[i]]
    yrs = max(1e-9, (int(dates[-1][:4]) - int(dates[0][:4])
                     + (int(dates[-1][5:7]) - int(dates[0][5:7])) / 12.0))
    return {
        "n_alert_episodes_total": len(edges),
        "n_false_alarm_episodes": len(fa),
        "n_in_crisis_window": len(hits),
        "false_alarms_per_year": round(len(fa) / yrs, 3),
        "precision_episodes": (round(len(hits) / len(edges), 4) if edges else None),
        "span_years": round(yrs, 2),
        "frac_days_alerting": round(float(flags.mean()), 4),
    }


async def build_signals(pillar2: str = "lam1"
                        ) -> dict[str, tuple[list[str], np.ndarray, dict]]:
    """Every replayed signal, built once from the database.

    Shared with `replay_warning_null.py` deliberately: the null must be computed
    on *the same* series as the observed statistic, and the cheapest way to
    guarantee that is for there to be only one construction path.
    """
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        raw = await load_all(pool)
    finally:
        await pool.close()

    # ---- pillar series, causal -----------------------------------------
    lam_series, lam_by_date = [], {}
    sca_series, sca_by_date = [], {}
    for r in raw["rmt"]:
        d = str(r["date"]); ev = list(r["eigenvalues"] or [])
        sc = r["sca_t"]
        if sc is not None and np.isfinite(float(sc)):
            sca_by_date[d] = float(sc); sca_series.append((d, float(sc)))
        s = lam1_share(ev)
        if s is None:
            continue
        lam_series.append((d, s)); lam_by_date[d] = ev

    hwk_series, hwk_pts = [], []
    for r in raw["hwk"]:
        n = float(r["branching_ratio_n"])
        hwk_series.append((str(r["ts"].date()), n / (1.0 - n)))
        hwk_pts.append((r["ts"], n, ist_timestamp(r["ts"])))
    hwk_pts.sort(key=lambda x: x[0])
    hwk_ts_only = [p[0] for p in hwk_pts]

    ham = load_hamilton_causal()
    global ham_series_cache
    ham_series_cache = sorted((d, v[0]) for d, v in ham.items())

    grid = [d for d, _ in lam_series]
    onsets = [EPOCH_BREAKS[e][0] for e in EPOCH_BREAKS]

    print(f"[replay] grid        : {len(grid):,} daily ticks "
          f"{grid[0]} .. {grid[-1]}")
    print(f"[replay] P1 hawkes   : {len(hwk_pts):,} refits "
          f"{str(hwk_pts[0][0])[:10]} .. {str(hwk_pts[-1][0])[:10]} "
          f"(refit_every=5 sessions)")
    _q = "SCA_t (FR18 SPEC)" if pillar2 == "sca" else "lambda1/N (shipped)"
    _x = "" if pillar2 == "lam1" else "  [EXPERIMENT - seraph/ unchanged]"
    print(f"[replay] P2 rmt      : {len(lam_series):,} daily rows, "
          f"quantity = {_q}{_x}")
    print(f"[replay] P3 hamilton : {len(ham):,} CAUSAL rows "
          f"{ham_series_cache[0][0] if ham else '-'} .. "
          f"{ham_series_cache[-1][0] if ham else '-'}  [EXPLORATORY]")
    print(f"[replay] rule A      : CSRS >= {PROVISIONAL_AMBER} (C9 frozen constant)")
    print(f"[replay] rule B      : > trailing-5y {RULE_B_Q:.0%} quantile, "
          f"min {RULE_B_MIN_OBS} obs, index i excluded from its own threshold")
    print(f"[replay] PILLAR_ORDER= {PILLAR_ORDER}", flush=True)

    signals: dict[str, tuple[list[str], np.ndarray, dict]] = {}

    # ---- the seven pillar subsets --------------------------------------
    for name, mask in SUBSETS.items():
        d, v, meta = replay_subset(
            name, mask, grid=grid, lam_by_date=lam_by_date,
            lam_series=lam_series, hwk_pts=hwk_pts, hwk_ts_only=hwk_ts_only,
            hwk_series=hwk_series, ham=ham, pillar2=pillar2,
            sca_by_date=sca_by_date, sca_series=sca_series)
        signals[f"CSRS[{name}]"] = (d, v, meta)
        print(f"[replay]   subset {name:<22} {len(d):,} pts  "
              f"{meta['failures']} failures  mean={np.nanmean(v):.4f}",
              flush=True)

    # ---- simple-feature baselines, on the same grid and labels ---------
    md = [str(r["date"]) for r in raw["mkt"]]
    ml = np.array([float(r["mkt"]) for r in raw["mkt"]])
    keep = {d: i for i, d in enumerate(md)}
    idx = np.array([keep.get(d, -1) for d in grid])
    lr = np.where(idx >= 0, np.take(ml, np.clip(idx, 0, ml.size - 1)), np.nan)

    rv = realised_vol(lr, 20)
    dd = drawdown(lr)
    base = {
        "BASE[rv_20]": rv,
        "BASE[drawdown]": dd,
        "BASE[semivar_20]": downside_semivariance(lr, 20),
        "BASE[rv_accel_5]": accel(rv, 5),
        "BASE[dd_accel_5]": accel(dd, 5),
    }
    for k, v in base.items():
        signals[k] = (grid, v, {"failures": 0, "warnings": {},
                                "artefact_id": "n/a (simple feature)"})
        print(f"[replay]   baseline {k:<20} {int(np.isfinite(v).sum()):,} finite pts",
              flush=True)

    return signals


async def main(out_dir: str, pillar2: str = "lam1") -> int:
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    signals = await build_signals(pillar2)
    grid = signals["CSRS[rmt]"][0]
    onsets = [EPOCH_BREAKS[e][0] for e in EPOCH_BREAKS]

    # ---- assessment ----------------------------------------------------
    report: dict = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grid": {"n": len(grid), "first": grid[0], "last": grid[-1]},
        "pillar2_quantity": pillar2,
        "rule_A": {"signal": "CSRS", "threshold": PROVISIONAL_AMBER,
                   "provenance": "C9 PROVISIONAL_AMBER, declared constant"},
        "rule_B": {"quantile": RULE_B_Q, "window_years": 5,
                   "min_obs": RULE_B_MIN_OBS,
                   "provenance": "causal trailing quantile, index i excluded"},
        "epochs": {e: {"onset": v[0], "provenance": v[1]}
                   for e, v in EPOCH_BREAKS.items()},
        "hamilton_status": ("EXPLORATORY - regime structure indistinguishable "
                            "from single-regime AR(1)/AAFT surrogates; causal "
                            "series begins 2013-01-14; not promoted"),
        "signals": {},
    }

    for sig, (d, v, meta) in signals.items():
        fb, ok_b = causal_quantile_flags(d, v, with_assessable=True)
        entry: dict = {"meta": meta,
                       "finite_points": int(np.isfinite(v).sum()),
                       "assessable_points": int(ok_b.sum()),
                       "first_assessable_date": (d[int(np.argmax(ok_b))]
                                                 if ok_b.any() else None),
                       "rule_B": {"false_alarms": false_alarms(d, fb, onsets),
                                  "epochs": {}}}
        for e, (onset, _) in EPOCH_BREAKS.items():
            entry["rule_B"]["epochs"][e] = {
                str(h): assess_epoch(d, fb, v, onset, horizon=h,
                                     assessable=ok_b)
                for h in HORIZONS}
        if sig.startswith("CSRS["):
            fa_ = np.asarray([bool(np.isfinite(x) and x >= PROVISIONAL_AMBER)
                              for x in v])
            entry["rule_A"] = {"false_alarms": false_alarms(d, fa_, onsets),
                               "epochs": {}}
            for e, (onset, _) in EPOCH_BREAKS.items():
                entry["rule_A"]["epochs"][e] = {
                    str(h): assess_epoch(d, fa_, v, onset, horizon=h)
                    for h in HORIZONS}
        report["signals"][sig] = entry

    suffix = "" if pillar2 == "lam1" else f"_{pillar2}"
    jp = outp / f"replay_results{suffix}.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[replay] wrote {jp}")

    # ---- console summary: the FR32 lead window, Rule B -----------------
    print(f"\n=== Rule B, horizon 15d (FR32 upper lead bound) ===")
    hdr = (f"{'signal':<24}" + "".join(f"{e[:9]:>11}" for e in EPOCH_BREAKS)
           + f"{'FA/yr':>8}{'prec':>7}")
    print(hdr); print("-" * len(hdr))
    for sig, entry in report["signals"].items():
        row = f"{sig:<24}"
        for e in EPOCH_BREAKS:
            r = entry["rule_B"]["epochs"][e]["15"]
            vd = r["verdict"]
            cell = ("UNTEST" if vd == "UNTESTABLE"
                    else (f"PASS {r['lead_time_days']}d" if vd == "PASS" else "FAIL"))
            row += f"{cell:>11}"
        fa = entry["rule_B"]["false_alarms"]
        pr = fa["precision_episodes"]
        row += f"{fa['false_alarms_per_year']:>8.2f}"
        row += f"{(f'{pr:.2f}' if pr is not None else '-'):>7}"
        print(row)
    print("\nPASS = a rising edge inside [onset-15, onset-1]. FAIL = no pre-onset")
    print("edge. UNTEST = insufficient causal coverage before the onset.")
    print("FR32's lead window is 5-15 days; `within_fr32_lead_window` in the")
    print("JSON records whether the lead also clears the 5-day lower bound.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/evidence/replay",
                    help="output directory for replay_results.json")
    ap.add_argument("--pillar2", choices=PILLAR2_MODES, default="lam1",
                    help="which quantity stands for Pillar 2: lam1 "
                         "reproduces the shipped pipeline, sca uses the "
                         "SPEC FR18 quantity. Research only; changes "
                         "nothing in seraph/")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.out, a.pillar2)))
