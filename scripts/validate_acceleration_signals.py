#!/usr/bin/env python3
# C10 — leakage, out-of-sample and incremental-value audit of the two surviving
# T1 detection signals (FR28, FR32, FR33, FR35, O7). Research only; writes nothing.
"""Are `dd_accel` and `rv_accel` genuine signals, or artefacts?

`DETECTION-CALIBRATION.md` reports that out of 15 screened series only two
survive Holm correction on the T1 contemporaneous-detection objective:
`dd_accel` (p = 0.0007) and `rv_accel` (p = 0.0020). SERAPH's own headline CSRS
claim does not. Three things were never checked, and any one of them could
reduce both survivors to artefacts.

================================================================================
PRE-REGISTRATION — written and committed to this file before any result below
was computed. Acceptance criteria are stated first so they cannot be moved.
================================================================================

H_C1  LEAKAGE.  `dd_accel` and `rv_accel` are computable strictly from
      information available at or before time t.

      ACCEPT iff all five hold:
        (a) TRUNCATION INVARIANCE. Rebuilding the whole feature pipeline from
            inputs restricted to indices [0 .. t*] reproduces the full-sample
            value at index t* to within 1e-12 relative, at every tested cut t*.
        (b) FUTURE PERTURBATION. Replacing every input at index > t* with
            different numbers leaves values at indices [0 .. t*] bit-identical.
        (c) TEETH. Four deliberately non-causal variants — a centred window, a
            forward difference, a full-sample normalisation, and a reversed
            cumulative — each FAIL (a) or (b). A test that passes everything
            proves nothing.
        (d) LABELS. The T1 label at index t is a function only of breaks at
            indices <= t, and no observed crisis window wraps the grid.
        (e) STANDARDISATION. Every standardisation on the path to a reported
            number is causal (FR28's rolling five-year ECDF included), or is
            provably absent from it.
      REJECT if (a), (b) or (d) fails anywhere, or if (c) shows no teeth.

H_C2  OUT OF SAMPLE.  The detection advantage survives chronological
      evaluation on a span the signals were not selected on.

      Splits are fixed here, before running:
        SPLIT-B (PRIMARY) — equal onset counts, 3 and 3.
            select  : grid start .. 2018-12-31   (gfc_2008, taper_2013, ilfs_2018)
            evaluate: 2019-01-01 .. grid end     (covid_2020, tightening_2022,
                                                  tariff_2026)
        SPLIT-A (SECONDARY) — the span boundary the project already uses.
            select  : grid start .. 2016-12-31   (2 onsets)
            evaluate: 2017-01-01 .. grid end     (4 onsets)
        SPLIT-C (SECONDARY) — leave-one-epoch-out. For each epoch, screen on the
            other five and evaluate the winner on the held-out epoch alone.

      ACCEPT iff, on SPLIT-B's evaluation span, the signal's T1 AUC exceeds the
        95th percentile of BOTH its nulls on that span AND
        max(p_shift, p_aaft) <= 0.05.
      PARTIAL if it clears nominal 0.05 but not the 95th percentile, or clears
        on one split and not the other.
      REJECT if the out-of-sample AUC falls inside its own null.
      Multiplicity here is 2 pre-specified signals, not 15 — Holm over 2 is also
      reported. Nothing is tuned on any evaluation span; no parameter is fitted
      at all, which is what makes a pure re-measurement the right OOS test.

H_C3  INCREMENTAL VALUE.  They add information beyond trivially simpler
      alternatives and beyond the existing pillars.

      Comparators, fixed here: raw daily return (sign-flipped), absolute return,
        realised-volatility level, its 20-day trailing mean, drawdown level, and
        the plain 1-day difference of realised volatility and of drawdown; plus
        the existing pillar scores (RMT lambda1/N, Hawkes n) and both full-span
        CSRS configurations.
      ACCEPT iff (a) both signals survive Holm over the FULL expanded primary
        family, whose size is reported and is larger than the original 15 — so
        the correction gets strictly stricter, not looser; AND (b) each signal,
        after causal orthogonalisation against each comparator, still clears its
        own null at nominal 0.05.
      PARTIAL if (a) holds and (b) fails against some comparator.
      REJECT if (a) fails.

SIGN CONVENTIONS are fixed by economics, never by the observed AUC: higher
volatility, wider spreads, higher absorption, deeper drawdown and *lower*
returns all mean more risk, so the raw return enters as `-lr`. AUC is one-sided
throughout, exactly as in the original screen.

T1 AND T3 ARE REPORTED SEPARATELY AND ARE NOT TRADED OFF. T1 asks "is the engine
lit while the crisis is happening". Only T3 can support an advance-warning claim.
A T1 pass is NOT evidence of T3 capability. T3 is evaluated at lead horizons of
5, 10, 20 and 30 trading days against `early_warning_power.py`'s own calibrated
no-signal distribution, re-derived per horizon because the horizon changes the
null's width.

MACHINERY IS IMPORTED, NEVER REIMPLEMENTED: `t1_auc`, `shift_null_t1`,
`aaft_null_t1` and the Holm step come from `calibrate_detection_claims.py`;
`t3_auc`, `relocation_null`, `aaft_null`, `ar1_stationary` from
`early_warning_power.py`; `build_features` from `study_stress_candidates.py`;
`auc` from `seraph.validation.harness`. The T3 horizon is varied by rebinding
`early_warning_power.LEAD_H` at runtime, so the horizon sweep runs through that
module's own code path and cannot drift from it. Nothing on disk is modified.

EXCLUDED ON PURPOSE: `hamilton_output.xi_*`. The persisted values are not
established as causal — `HAMILTON-CAUSAL-POSTFIX.md` states the causal
walk-forward output was deliberately *not* persisted — so admitting them as a
comparator would import an unaudited look-ahead into a leakage audit.

Writes nothing. Reads `hamilton_output` (rv_t_yz, ar_t, bas_t only),
`daily_prices`, `rmt_output`, `hawkes_output`, and the two committed full-span
CSRS dumps under `docs/evidence/`.

Run: python scripts/validate_acceleration_signals.py [--perms 3000]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402


def _load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ssc = _load_module("ssc", "scripts/study_stress_candidates.py")
cdc = _load_module("cdc", "scripts/calibrate_detection_claims.py")
ewp = _load_module("ewp", "scripts/early_warning_power.py")

CSRS_2P = "docs/evidence/20261013T040058Z-28-csrs-fullspan-2pillar.csv"
CSRS_3P = "docs/evidence/20261013T040058Z-28-csrs-fullspan-3pillar.csv"

#: H_C3's comparator set and the two signals under test.
SIGNALS = ("dd_accel", "rv_accel")
ORIGINAL_OTHERS = ("rv_level", "semivar_20", "jump_int_20", "drawdown",
                   "vol_of_vol", "ar_t", "bas_t")
SIMPLER = ("neg_return", "abs_return", "rv_ma20", "rv_diff1", "dd_diff1")
INCUMBENTS = ("rmt lam1/N", "hawkes n", "CSRS 2p fullspan", "CSRS 3p fullspan")
PRIMARY = SIGNALS + ORIGINAL_OTHERS + SIMPLER + INCUMBENTS

#: (signal, comparator) pairs orthogonalised causally for H_C3(b).
ORTHO_PAIRS = (("dd_accel", "drawdown"), ("dd_accel", "dd_diff1"),
               ("dd_accel", "rv_level"), ("dd_accel", "rmt lam1/N"),
               ("rv_accel", "rv_level"), ("rv_accel", "rv_ma20"),
               ("rv_accel", "rv_diff1"), ("rv_accel", "rmt lam1/N"))

SPLITS = {
    "SPLIT-B (primary)": ("2018-12-31", "2019-01-01"),
    "SPLIT-A (secondary)": ("2016-12-31", "2017-01-01"),
}
T3_HORIZONS = (5, 10, 20, 30)
ORTHO_WINDOW = 1260        # 5 years of trading days — matches FR28's ECDF window
ORTHO_MIN_OBS = 250


# --------------------------------------------------------------- derivation --

def extra_features(dates: list[str], lr: np.ndarray, rv: np.ndarray,
                   base: dict) -> dict:
    """The trivially simpler alternatives of H_C3. Causal by the same rules.

    `neg_return` is the raw market log return with the sign fixed by economics
    (lower return = more risk), NOT by whichever orientation scored better.
    """
    dd = base["drawdown"]
    rv_ma20 = ssc.roll(rv, 20, np.mean)
    d1 = lambda a: np.r_[np.nan, a[1:] - a[:-1]]  # noqa: E731  backward diff
    return {
        "neg_return": -lr,
        "abs_return": np.abs(lr),
        "rv_ma20": rv_ma20,
        "rv_diff1": d1(rv),
        "dd_diff1": d1(dd),
    }


def build_all(dates: list[str], lr: np.ndarray, rv: np.ndarray,
              ar: np.ndarray, bas: np.ndarray) -> dict:
    """Every series derivable from the observation grid, in one causal pass."""
    f = dict(ssc.build_features(dates, lr, rv, ar, bas))
    f.update(extra_features(dates, lr, rv, f))
    return f


def causal_residual(s: np.ndarray, c: np.ndarray, *, window: int = ORTHO_WINDOW,
                    min_obs: int = ORTHO_MIN_OBS) -> np.ndarray:
    """`s` orthogonalised against `c` by a strictly backward-looking OLS.

    resid[t] = s[t] - (a_t + b_t * c[t]), where (a_t, b_t) are fitted on the
    finite pairs at indices u in [t-window, t-1] — the fit never sees index t
    itself, let alone anything after it. Implemented with prefix sums so the
    whole series costs O(n); the prefix array P[i] holds the sum over u < i,
    which is what makes the exclusive upper bound exact rather than approximate.
    """
    s = np.asarray(s, float)
    c = np.asarray(c, float)
    ok = np.isfinite(s) & np.isfinite(c)
    m = ok.astype(float)
    x = np.where(ok, c, 0.0)
    y = np.where(ok, s, 0.0)
    P = lambda a: np.r_[0.0, np.cumsum(a)]  # noqa: E731
    Pm, Px, Py, Pxx, Pxy = P(m), P(x), P(y), P(x * x), P(x * y)
    out = np.full(s.size, np.nan)
    for t in range(s.size):
        if not ok[t]:
            continue
        lo, hi = max(0, t - window), t          # u in [lo, t-1]
        cnt = Pm[hi] - Pm[lo]
        if cnt < min_obs:
            continue
        sx, sy = Px[hi] - Px[lo], Py[hi] - Py[lo]
        sxx, sxy = Pxx[hi] - Pxx[lo], Pxy[hi] - Pxy[lo]
        den = sxx - sx * sx / cnt
        if not np.isfinite(den) or abs(den) < 1e-18:
            continue
        b = (sxy - sx * sy / cnt) / den
        a = sy / cnt - b * sx / cnt
        out[t] = s[t] - (a + b * c[t])
    return out


# --------------------------------------------- deliberately leaky variants --

def leaky_variants(dates: list[str], lr: np.ndarray, rv: np.ndarray,
                   ar: np.ndarray, bas: np.ndarray) -> dict:
    """H_C1(c). Each of these is wrong in exactly one documented way.

    If the audit below does not flag every one of them, the audit is useless.
    """
    base = ssc.build_features(dates, lr, rv, ar, bas)
    dd = base["drawdown"]
    n = dd.size

    centred = np.full(n, np.nan)              # dd[t+2] - dd[t-3]
    for t in range(3, n - 2):
        centred[t] = dd[t + 2] - dd[t - 3]

    forward = np.full(n, np.nan)              # dd[t+5] - dd[t]
    forward[:n - 5] = dd[5:] - dd[:n - 5]

    fin = np.isfinite(rv)                     # rv[t] / mean(rv) over ALL time
    full_mean = float(rv[fin].mean()) if fin.any() else np.nan
    fullsample = rv / full_mean

    # reversed cumulative: minus the cumulative return from t to the end
    rev = -np.cumsum(lr[::-1])[::-1]

    # drawdown measured against the FORWARD 252-day peak, then differenced
    px = np.exp(np.cumsum(lr))
    fut_peak = np.full(n, np.nan)
    for t in range(n):
        seg = px[t:min(n, t + 252)]
        if seg.size >= 63:
            fut_peak[t] = seg.max()
    fut_dd = 1.0 - px / fut_peak
    fut = np.r_[np.full(5, np.nan), fut_dd[5:] - fut_dd[:-5]]

    # The documented BLIND SPOT, kept deliberately: a reversed cumulative that
    # is then passed through a scale-invariant transform. dd = 1 - px/peak is
    # unchanged when px is multiplied by a constant, and truncating a reversed
    # cumsum does exactly that, so neither test can see it above float rounding.
    rev_px = np.exp(np.cumsum(lr[::-1]))[::-1]
    rev_peak = ssc.roll(rev_px, 252, np.max)
    rev_dd = 1.0 - rev_px / rev_peak
    blind = np.r_[np.full(5, np.nan), rev_dd[5:] - rev_dd[:-5]]

    return {"LEAK centred-window": centred,
            "LEAK forward-difference": forward,
            "LEAK full-sample-norm": fullsample,
            "LEAK reversed-cumulative": rev,
            "LEAK future-peak-drawdown": fut,
            "BLINDSPOT scale-inv-reversal": blind}


# ------------------------------------------------------------------- audits --

def truncation_audit(dates, lr, rv, ar, bas, full: dict, cuts, names,
                     builder) -> dict:
    """H_C1(a). Rebuild from inputs [0..t*] and compare the value AT t*."""
    worst: dict[str, tuple[float, int, str]] = {k: (0.0, -1, "ok") for k in names}
    for t in cuts:
        sub = builder(dates[:t + 1], lr[:t + 1], rv[:t + 1],
                      ar[:t + 1], bas[:t + 1])
        for k in names:
            a, b = full[k][t], sub[k][t]
            if not np.isfinite(a) and not np.isfinite(b):
                continue
            if np.isfinite(a) != np.isfinite(b):
                worst[k] = (float("inf"), t, "finiteness differs")
                continue
            rel = abs(a - b) / max(abs(a), abs(b), 1e-300)
            if rel > worst[k][0]:
                worst[k] = (rel, t, f"{a!r} vs {b!r}")
    return worst


def perturbation_audit(dates, lr, rv, ar, bas, full: dict, cuts, names,
                       builder, rng) -> dict:
    """H_C1(b). Corrupt every input after t*; the past must not move at all."""
    worst: dict[str, tuple[float, int]] = {k: (0.0, -1) for k in names}
    for t in cuts:
        lr2, rv2, ar2, bas2 = lr.copy(), rv.copy(), ar.copy(), bas.copy()
        k = t + 1
        lr2[k:] = lr[k:] * 7.0 + 0.013 + rng.normal(scale=0.01, size=lr.size - k)
        rv2[k:] = rv[k:] * 3.0 + 5.0
        ar2[k:] = np.clip(1.0 - ar[k:], 1e-6, 1.0)
        bas2[k:] = bas[k:] * 11.0 + 1.0
        sub = builder(dates, lr2, rv2, ar2, bas2)
        for nm in names:
            a, b = full[nm][:k], sub[nm][:k]
            fa, fb = np.isfinite(a), np.isfinite(b)
            if not np.array_equal(fa, fb):
                worst[nm] = (float("inf"), t)
                continue
            if not fa.any():
                continue
            d = np.max(np.abs(a[fa] - b[fb]))
            scale = max(float(np.max(np.abs(a[fa]))), 1e-300)
            rel = float(d / scale)
            if rel > worst[nm][0]:
                worst[nm] = (rel, t)
    return worst


def label_audit(dates: list[str], breaks: list[int], n: int) -> list[str]:
    """H_C1(d). The T1 label must be a backward-looking function of breaks."""
    notes = []
    y = np.zeros(n, int)
    for i in breaks:
        y[(np.arange(i, i + CRISIS_WINDOW_DAYS)) % n] = 1
    wraps = [i for i in breaks if i + CRISIS_WINDOW_DAYS > n]
    notes.append(f"observed crisis windows that wrap the grid: "
                 f"{len(wraps)} {'(none — label is purely backward)' if not wraps else wraps}")
    # rebuild y[t] using only breaks at indices <= t and require equality
    y_causal = np.zeros(n, int)
    for t in range(n):
        y_causal[t] = int(any(0 <= t - i < CRISIS_WINDOW_DAYS for i in breaks
                              if i <= t))
    same = bool(np.array_equal(y, y_causal))
    notes.append(f"y[t] reproduced from breaks at indices <= t only: "
                 f"{'IDENTICAL' if same else 'DIFFERS'} "
                 f"({int((y != y_causal).sum())} cells differ)")
    notes.append(f"T1 positives: {int(y.sum())} days from {len(breaks)} onsets "
                 f"({CRISIS_WINDOW_DAYS} per onset, FR32)")
    return notes


def standardisation_audit() -> list[str]:
    """H_C1(e). Where standardisation is, and whether it is causal."""
    from seraph.fusion.standardize import ECDF_WINDOW_YEARS, ecdf_transform
    from seraph.orchestration.standardize import window_from
    out = []
    series = [(f"20{y:02d}-06-15", float(y)) for y in range(0, 26)]
    w = window_from(series, "2020-06-15", years=ECDF_WINDOW_YEARS)
    future = [v for ts, v in series if ts > "2020-06-15"]
    out.append(f"window_from(as_of=2020-06-15, years={ECDF_WINDOW_YEARS}) -> "
               f"{w}; admits any value dated after as_of: "
               f"{'YES — LEAK' if set(w) & set(future) else 'no'}")
    out.append(f"ecdf_transform(0.5, [0,1]) = {ecdf_transform(0.5, [0, 1])} "
               f"(ranks against the supplied window only; the window is the "
               f"caller's, and the only caller is window_from)")
    # trailing_pct from the study, on a long enough grid to clear its min count
    d = [str(np.datetime64("2005-01-03") + np.timedelta64(i, "D"))
         for i in range(1200)]
    v = np.arange(len(d), dtype=float)
    pc = ssc.trailing_pct(d, v, years=2)
    rev = ssc.trailing_pct(d, v[::-1], years=2)
    out.append(f"trailing_pct on a strictly INCREASING series: last value's "
               f"percentile = {pc[-1]:.4f} (must be 1.0000 — a causal window "
               f"ending at t contains its own maximum at t)")
    out.append(f"trailing_pct on a strictly DECREASING series: last value's "
               f"percentile = {rev[-1]:.4f} (must be the window minimum's rank; "
               f"a centred or full-sample window would not give this)")
    out.append("NOT ON THE PATH: t1_auc scores the RAW series. AUC is "
               "rank-based (Mann-Whitney U), so no standardisation of any kind "
               "enters any AUC reported here. trailing_pct feeds only the "
               "alert/precision/recall columns of study_stress_candidates.py, "
               "which this report does not use.")
    return out


# ------------------------------------------------------------- evaluation ----

def span_bounds(dates: list[str], lo: str, hi: str) -> tuple[int, int]:
    a = next(i for i, d in enumerate(dates) if d >= lo)
    b = max(i for i, d in enumerate(dates) if d <= hi) + 1
    return a, b


def evaluate(score: np.ndarray, a: int, b: int, breaks_all, perms: int, rng):
    """T1 AUC plus both nulls, restricted to the grid slice [a, b)."""
    sub = score[a:b]
    nsub = b - a
    brk = [i - a for i in breaks_all if a <= i < b]
    fin = int(np.isfinite(sub).sum())
    if not brk or fin < 200:
        return None
    wrap = [i for i in brk if i + CRISIS_WINDOW_DAYS > nsub]
    obs = cdc.t1_auc(sub, brk, nsub)
    if not np.isfinite(obs):
        return None
    ns = cdc.shift_null_t1(sub, nsub, brk, perms, rng)
    na = cdc.aaft_null_t1(sub, nsub, brk, perms, rng)
    p_s = (1 + int(np.sum(ns >= obs))) / (1 + ns.size)
    p_a = (1 + int(np.sum(na >= obs))) / (1 + na.size)
    p95 = float(np.percentile(np.concatenate([ns, na]), 95))
    return {"auc": obs, "p_shift": p_s, "p_aaft": p_a, "p": max(p_s, p_a),
            "p95": p95, "onsets": len(brk), "finite": fin, "n": nsub,
            "shift_mu": float(ns.mean()), "aaft_mu": float(na.mean()),
            "wrap": wrap,
            "sig": bool(max(p_s, p_a) <= 0.05 and obs >= p95)}


def holm(pvals: dict[str, float], label: str) -> list[str]:
    ranked = sorted((p, k) for k, p in pvals.items())
    m = len(ranked)
    print(f"\n  Holm over {m} comparisons ({label}); "
          f"tightest threshold 0.05/{m} = {0.05 / m:.5f}")
    survive = []
    for i, (p, k) in enumerate(ranked, start=1):
        thr = 0.05 / (m - i + 1)
        ok = p <= thr
        print(f"    {i:>2}. {k:<26} p={p:.4f}  thr={thr:.5f}  "
              f"{'survives' if ok else 'does NOT survive — step-down stops here'}")
        if not ok:
            break
        survive.append(k)
    print(f"  survives Holm over all {m}: {survive if survive else 'NONE'}")
    return survive


def per_onset_aucs(score: np.ndarray, breaks, n: int) -> dict:
    """AUC of each onset's own 30-day window against all non-crisis days.

    Also the arithmetic cross-check that the pooled T1 AUC is the positive-day
    weighted mean of these — true exactly when the negative set is shared, which
    is what makes a cluster bootstrap over onsets the right event-level CI.
    """
    in_crisis = np.zeros(n, bool)
    for i in breaks:
        in_crisis[(np.arange(i, i + CRISIS_WINDOW_DAYS)) % n] = True
    fin = np.isfinite(score)
    neg = score[(~in_crisis) & fin]
    out, weights = {}, {}
    for i in breaks:
        w = (np.arange(i, i + CRISIS_WINDOW_DAYS)) % n
        pos = score[w][np.isfinite(score[w])]
        if pos.size == 0 or neg.size == 0:
            continue
        beat = float(np.mean((pos[:, None] > neg[None, :])
                             + 0.5 * (pos[:, None] == neg[None, :])))
        out[i] = beat
        weights[i] = pos.size
    return out, weights


def cluster_bootstrap(per_onset: dict, weights: dict, boots: int, rng):
    keys = list(per_onset)
    v = np.array([per_onset[k] for k in keys])
    w = np.array([weights[k] for k in keys], float)
    draws = np.empty(boots)
    for b in range(boots):
        idx = rng.integers(0, v.size, size=v.size)
        draws[b] = float(np.average(v[idx], weights=w[idx]))
    return float(np.average(v, weights=w)), draws


# ---------------------------------------------------------------- data load --

async def load():
    c = await asyncpg.connect(resolve_dsn(), timeout=300)
    obs = await c.fetch(
        "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    mkt = await c.fetch("""
      WITH r AS (SELECT date, symbol,
                        ln(adj_close / NULLIF(lag(adj_close) OVER (
                            PARTITION BY symbol ORDER BY date), 0)) lr
                 FROM daily_prices WHERE universe_member_flag AND adj_close > 0)
      SELECT date, avg(lr) mkt FROM r WHERE lr IS NOT NULL
      GROUP BY date ORDER BY date""")
    rmt = await c.fetch("SELECT date, eigenvalues FROM rmt_output ORDER BY date")
    hwk = await c.fetch("SELECT ts, branching_ratio_n FROM hawkes_output "
                        "WHERE scope='market' ORDER BY ts")
    await c.close()
    return obs, mkt, rmt, hwk


def read_csrs_csv(path: Path, idx: dict, n: int) -> tuple[np.ndarray, int]:
    v = np.full(n, np.nan)
    hit = 0
    for ln in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = ln.split(",")
        if len(parts) < 2:
            continue
        d = parts[0][:10]
        if d in idx:
            v[idx[d]] = float(parts[1])
            hit += 1
    return v, hit


# ---------------------------------------------------------------------- main --

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=3000,
                    help="permutations per null for the T1 screens")
    ap.add_argument("--t3-perms", type=int, default=1000)
    ap.add_argument("--t3-draws", type=int, default=60,
                    help="synthetic draws per delta for the T3 no-signal "
                         "distribution, per horizon")
    ap.add_argument("--boots", type=int, default=5000)
    a = ap.parse_args()
    t_start = time.time()

    print("=" * 100)
    print("VALIDATION OF dd_accel AND rv_accel — leakage, out-of-sample, "
          "incremental value")
    print("=" * 100)
    print(__doc__.split("MACHINERY IS IMPORTED")[0].strip())
    print("=" * 100)

    obs, mkt, rmt, hwk = asyncio.run(load())
    mk = {str(r["date"]): float(r["mkt"]) for r in mkt}
    rows = [r for r in obs if str(r["date"]) in mk]
    dates = [str(r["date"]) for r in rows]
    n = len(dates)
    idx = {d: i for i, d in enumerate(dates)}
    lr = np.array([mk[d] for d in dates])
    rv = np.array([float(r["rv_t_yz"]) for r in rows])
    ar = np.array([float(r["ar_t"]) for r in rows])
    bas = np.array([float(r["bas_t"]) for r in rows])

    series = build_all(dates, lr, rv, ar, bas)
    lam = np.full(n, np.nan)
    for r in rmt:
        d, ev = str(r["date"]), r["eigenvalues"]
        if d in idx and ev:
            e = np.asarray(ev, float)
            lam[idx[d]] = float(e.max() / e.size)
    series["rmt lam1/N"] = lam
    hw = np.full(n, np.nan)
    for r in hwk:
        d = str(r["ts"])[:10]
        if d in idx and r["branching_ratio_n"] is not None:
            hw[idx[d]] = float(r["branching_ratio_n"])
    series["hawkes n"] = hw
    c2, h2 = read_csrs_csv(_ROOT / CSRS_2P, idx, n)
    c3, h3 = read_csrs_csv(_ROOT / CSRS_3P, idx, n)
    series["CSRS 2p fullspan"] = c2
    series["CSRS 3p fullspan"] = c3

    breaks = sorted(idx[next(d for d in dates if d >= bd)]
                    for bd, _ in EPOCH_BREAKS.values()
                    if any(d >= bd for d in dates))
    ep_of = {}
    for ep, (bd, _) in EPOCH_BREAKS.items():
        i = next((k for k, d in enumerate(dates) if d >= bd), None)
        if i is not None:
            ep_of[i] = ep

    print(f"\ngrid       : {n:,} trading days {dates[0]} .. {dates[-1]}")
    print(f"onsets     : {len(breaks)} at {breaks} -> "
          f"{[ep_of[i] for i in breaks]}")
    print(f"csrs dumps : 2p {h2:,}/{n:,} days, 3p {h3:,}/{n:,} days")
    print(f"perms      : {a.perms} per null; smallest resolvable p = "
          f"1/{a.perms + 1} = {1 / (1 + a.perms):.6f}")

    # ========================================================= H_C1 ======== #
    print("\n" + "=" * 100)
    print("H_C1 — LEAKAGE AUDIT (highest priority: this one can invalidate "
          "everything else)")
    print("=" * 100)

    cuts = sorted(set([300, 700] + [b for b in breaks] + [b + 10 for b in breaks]
                      + [n // 2, n - 400, n - 1]))
    cuts = [c for c in cuts if 0 <= c < n]
    print(f"cuts tested: {len(cuts)} indices {cuts}")

    audit_names = [k for k in PRIMARY if k not in INCUMBENTS]
    leaks = leaky_variants(dates, lr, rv, ar, bas)

    def builder(d, l_, r_, a_, b_):
        out = build_all(d, l_, r_, a_, b_)
        out.update(leaky_variants(d, l_, r_, a_, b_))
        for sig, comp in ORTHO_PAIRS:
            if comp in INCUMBENTS:
                continue
            out[f"{sig} |_ {comp}"] = causal_residual(out[sig], out[comp])
        return out

    full = build_all(dates, lr, rv, ar, bas)
    full.update(leaks)
    for sig, comp in ORTHO_PAIRS:
        if comp in INCUMBENTS:
            continue
        full[f"{sig} |_ {comp}"] = causal_residual(full[sig], full[comp])
    audit_names = (audit_names
                   + [k for k in full if k.startswith("LEAK ")]
                   + [k for k in full if k.startswith("BLINDSPOT")]
                   + [k for k in full if " |_ " in k])

    t0 = time.time()
    trunc = truncation_audit(dates, lr, rv, ar, bas, full, cuts, audit_names,
                             builder)
    rng = np.random.default_rng(20261013)
    pert = perturbation_audit(dates, lr, rv, ar, bas, full,
                              [c for c in cuts if c < n - 1], audit_names,
                              builder, rng)
    print(f"(audit took {time.time() - t0:.1f}s)\n")
    print(f"{'series':<28}{'max rel |delta| at t*':>24}"
          f"{'max rel |delta| on past':>26}  verdict")
    print("-" * 100)
    verdicts, flagged = {}, {}
    for k in audit_names:
        rt, ct, _ = trunc[k]
        rp, cp = pert[k]
        # Two-sided criterion. A causal series must be EXACTLY invariant. A leak
        # must be caught CLEARLY, not at float-rounding scale; anything in
        # 1e-12 .. 1e-6 is a grey zone and is reported as such rather than
        # counted as a catch.
        clean = (rt == 0.0) and (rp == 0.0)
        clear = (rt > 1e-6) or (rp > 1e-6)
        verdicts[k], flagged[k] = clean, clear
        rts = "inf (finiteness)" if rt == float("inf") else f"{rt:.3e}"
        rps = "inf (finiteness)" if rp == float("inf") else f"{rp:.3e}"
        tag = ("CAUSAL" if clean else
               "NON-CAUSAL *** LEAK ***" if clear else
               "GREY ZONE — below 1e-6")
        print(f"{k:<28}{rts:>24}{rps:>26}  {tag}")

    print("\n  (a) truncation invariance : rebuild from inputs [0..t*] only, "
          "compare the value AT t*")
    print("  (b) future perturbation   : corrupt every input after t*, "
          "compare all values up to t* (must be bit-identical, 0.000e+00)")
    teeth = [k for k in audit_names if k.startswith("LEAK ")]
    caught = [k for k in teeth if flagged[k]]
    print(f"\n  (c) TEETH: {len(caught)}/{len(teeth)} deliberately non-causal "
          f"variants were flagged clearly (> 1e-6). "
          f"{'The audit has teeth.' if len(caught) == len(teeth) else 'AUDIT MISSED ONE — see below.'}")
    for k in teeth:
        print(f"        {k:<30} {'FLAGGED (correct)' if flagged[k] else 'MISSED — audit invalid for this form'}")
    blind = [k for k in audit_names if k.startswith("BLINDSPOT")]
    for k in blind:
        rt, _, _ = trunc[k]
        rp, _ = pert[k]
        print(f"\n  (c') MEASURED BLIND SPOT — {k}")
        print(f"        truncation {rt:.3e}, perturbation {rp:.3e}: both at "
              f"float-rounding scale, so NEITHER test sees it.")
        print("        Cause: `drawdown = 1 - px/peak` is invariant to a "
              "constant multiple of px,")
        print("        and truncating a reversed cumsum rescales px by exactly "
              "such a constant.")
        print("        This is a real limit of the method, stated rather than "
              "hidden. It does not")
        print("        affect the verdict on dd_accel — the arithmetic "
              "identities below show its")
        print("        cumulative runs forward — but it does mean these two "
              "tests alone could not")
        print("        have refuted a scale-invariantly-reversed "
              "implementation, so the forward")
        print("        direction of `np.cumsum` is checked directly instead.")

    print("\n  (d) LABELS")
    for ln in label_audit(dates, breaks, n):
        print(f"        {ln}")
    print("\n  (e) STANDARDISATION")
    for ln in standardisation_audit():
        print(f"        {ln}")

    print("\n  ARITHMETIC IDENTITIES (the definitions, checked against the "
          "arrays rather than read)")
    dd = full["drawdown"]
    man = np.r_[np.full(5, np.nan), dd[5:] - dd[:-5]]
    both = np.isfinite(man) & np.isfinite(full["dd_accel"])
    print(f"        dd_accel[t] == drawdown[t] - drawdown[t-5]  : max|delta| = "
          f"{np.max(np.abs(man[both] - full['dd_accel'][both])):.3e} "
          f"over {int(both.sum()):,} cells  (a BACKWARD 5-day difference)")
    ma = ssc.roll(rv, 20, np.mean)
    man2 = np.where(np.isfinite(ma) & (ma > 0), rv / ma, np.nan)
    both2 = np.isfinite(man2) & np.isfinite(full["rv_accel"])
    print(f"        rv_accel[t] == rv[t] / mean(rv[t-19..t])    : max|delta| = "
          f"{np.max(np.abs(man2[both2] - full['rv_accel'][both2])):.3e} "
          f"over {int(both2.sum()):,} cells  (a TRAILING ratio)")
    probe = np.arange(50, dtype=float)
    rr = ssc.roll(probe, 7, np.max)
    exp = np.array([probe[max(0, i - 6):i + 1].max() if i >= 6 else np.nan
                    for i in range(50)])
    ok = np.isfinite(exp)
    print(f"        roll(a,w,f)[i] == f(a[i-w+1..i])            : max|delta| = "
          f"{np.max(np.abs(rr[ok] - exp[ok])):.3e}  (window ENDS at i, "
          f"never centred on it)")
    print(f"        drawdown uses px = exp(cumsum(lr)) forward  : px[0] == "
          f"exp(lr[0]) -> {np.exp(np.cumsum(lr))[0]:.10f} vs "
          f"{np.exp(lr[0]):.10f}  (a reversed cumulative would not match)")

    sig_clean = all(verdicts[k] for k in SIGNALS)
    print(f"\n  >>> H_C1 VERDICT: "
          f"{'ACCEPTED' if sig_clean and len(caught) == len(teeth) else 'REJECTED'}"
          f" — dd_accel and rv_accel are "
          f"{'strictly causal' if sig_clean else 'NOT causal'}")
    print("\n  RESIDUAL CAVEAT, not resolved by the above: `daily_prices.adj_close`")
    print("  carries split/dividend adjustment factors that are applied")
    print("  retroactively, so the price level at t embeds corporate actions")
    print("  announced after t. Log returns are invariant to a constant factor,")
    print("  so this perturbs only the handful of days on which an adjustment")
    print("  lands; it is a real but small look-ahead that lives in the data,")
    print("  not in the feature code, and these tests cannot see it.")

    # ========================================================= full span === #
    print("\n" + "=" * 100)
    print("REFERENCE — FULL-SPAN T1 (reproducing DETECTION-CALIBRATION.md §2 "
          "at higher permutation count)")
    print("=" * 100)
    rng = np.random.default_rng(777)
    hdr = (f"{'series':<22}{'AUC':>8}{'shiftmu':>9}{'p_shift':>9}"
           f"{'aaftmu':>9}{'p_aaft':>9}{'null p95':>10}{'ons':>5}{'verdict':>9}")
    print(hdr)
    print("-" * len(hdr))
    fullspan = {}
    for k in PRIMARY:
        r = evaluate(series[k], 0, n, breaks, a.perms, rng)
        if r is None:
            print(f"{k:<22}  insufficient coverage")
            continue
        fullspan[k] = r
        print(f"{k:<22}{r['auc']:>8.4f}{r['shift_mu']:>9.4f}{r['p_shift']:>9.4f}"
              f"{r['aaft_mu']:>9.4f}{r['p_aaft']:>9.4f}{r['p95']:>10.4f}"
              f"{r['onsets']:>5}{'SIG' if r['sig'] else 'not sig':>9}",
              flush=True)

    # ========================================================= H_C2 ======== #
    print("\n" + "=" * 100)
    print("H_C2 — OUT-OF-SAMPLE CHRONOLOGICAL EVALUATION")
    print("=" * 100)
    oos_p = {}
    for label, (sel_hi, ev_lo) in SPLITS.items():
        sa, sb = span_bounds(dates, dates[0], sel_hi)
        ea, eb = span_bounds(dates, ev_lo, dates[-1])
        print(f"\n--- {label} ---")
        print(f"  selection  : {dates[sa]} .. {dates[sb - 1]}  "
              f"({sb - sa:,} days, onsets "
              f"{[ep_of[i] for i in breaks if sa <= i < sb]})")
        print(f"  evaluation : {dates[ea]} .. {dates[eb - 1]}  "
              f"({eb - ea:,} days, onsets "
              f"{[ep_of[i] for i in breaks if ea <= i < eb]})")
        print(f"  {'series':<22}{'IN-SAMPLE':>22}{'OUT-OF-SAMPLE':>30}")
        print(f"  {'':<22}{'AUC':>8}{'p':>7}{'p95':>7}"
              f"{'AUC':>10}{'p_sh':>7}{'p_aa':>7}{'p95':>7}{'verdict':>9}")
        print("  " + "-" * 79)
        rng = np.random.default_rng(4040)
        ins, outs = {}, {}
        for k in PRIMARY:
            ri = evaluate(series[k], sa, sb, breaks, a.perms, rng)
            ro = evaluate(series[k], ea, eb, breaks, a.perms, rng)
            ins[k], outs[k] = ri, ro
            si = f"{ri['auc']:>8.4f}{ri['p']:>7.4f}{ri['p95']:>7.4f}" if ri \
                else f"{'n/a':>22}"
            so = (f"{ro['auc']:>10.4f}{ro['p_shift']:>7.4f}"
                  f"{ro['p_aaft']:>7.4f}{ro['p95']:>7.4f}"
                  f"{'SIG' if ro['sig'] else 'not sig':>9}") if ro \
                else f"{'n/a':>40}"
            mark = " <<<" if k in SIGNALS else ""
            print(f"  {k:<22}{si}{so}{mark}", flush=True)
        rank_in = sorted((v["auc"], k) for k, v in ins.items() if v)
        rank_out = sorted((v["auc"], k) for k, v in outs.items() if v)
        print(f"\n  in-sample  top 5 by AUC: "
              f"{[(k, round(v, 4)) for v, k in rank_in[::-1][:5]]}")
        print(f"  out-of-sample top 5    : "
              f"{[(k, round(v, 4)) for v, k in rank_out[::-1][:5]]}")
        for s in SIGNALS:
            pos_in = [k for _, k in rank_in[::-1]].index(s) + 1 if ins.get(s) else None
            pos_out = [k for _, k in rank_out[::-1]].index(s) + 1 if outs.get(s) else None
            print(f"    {s}: rank {pos_in}/{len(rank_in)} in-sample, "
                  f"{pos_out}/{len(rank_out)} out-of-sample")
        if label.startswith("SPLIT-B"):
            for s in SIGNALS:
                if outs.get(s):
                    oos_p[s] = outs[s]["p"]
    if oos_p:
        holm(oos_p, "H_C2: the 2 pre-specified signals on SPLIT-B's "
                    "evaluation span")

    print("\n--- SPLIT-C — leave-one-epoch-out ---")
    print("  For each epoch: screen the primary family on the other five "
          "onsets, then")
    print("  evaluate on the held-out epoch alone (1 onset, so the null is at "
          "its widest).")
    print(f"  {'held out':<18}{'screen winner':<22}{'win AUC':>9}"
          f"{'held-out AUC of winner':>24}{'dd_accel':>10}{'rv_accel':>10}")
    print("  " + "-" * 93)
    rng = np.random.default_rng(5050)
    loo = {s: [] for s in SIGNALS}
    loo_rank = {s: [] for s in SIGNALS}
    for held in breaks:
        rest = [b for b in breaks if b != held]
        scr = {}
        for k in PRIMARY:
            y = np.zeros(n, int)
            for i in rest:
                y[(np.arange(i, i + CRISIS_WINDOW_DAYS)) % n] = 1
            s = series[k]
            keep = np.isfinite(s)
            if y[keep].sum() < 5 or (1 - y[keep]).sum() < 5:
                continue
            from seraph.validation.harness import auc as _auc
            scr[k] = float(_auc(s[keep], y[keep]))
        if not scr:
            continue
        win = max(scr, key=scr.get)
        y1 = np.zeros(n, int)
        y1[(np.arange(held, held + CRISIS_WINDOW_DAYS)) % n] = 1
        held_aucs = {}
        for k in PRIMARY:
            s = series[k]
            keep = np.isfinite(s)
            if y1[keep].sum() < 5:
                continue
            from seraph.validation.harness import auc as _auc
            held_aucs[k] = float(_auc(s[keep], y1[keep]))
        order = sorted(held_aucs, key=held_aucs.get, reverse=True)
        for s in SIGNALS:
            if s in held_aucs:
                loo[s].append(held_aucs[s])
                loo_rank[s].append(order.index(s) + 1)
        print(f"  {ep_of[held]:<18}{win:<22}{scr[win]:>9.4f}"
              f"{held_aucs.get(win, float('nan')):>24.4f}"
              f"{held_aucs.get('dd_accel', float('nan')):>10.4f}"
              f"{held_aucs.get('rv_accel', float('nan')):>10.4f}")
    for s in SIGNALS:
        if loo[s]:
            v = np.array(loo[s])
            print(f"  {s}: held-out AUCs {np.round(v, 4).tolist()}  "
                  f"mean {v.mean():.4f}  min {v.min():.4f}  "
                  f"ranks {loo_rank[s]} of {len(PRIMARY)}")

    # ========================================================= H_C3 ======== #
    print("\n" + "=" * 100)
    print("H_C3 — INCREMENTAL VALUE OVER SIMPLER ALTERNATIVES AND OVER THE "
          "PILLARS")
    print("=" * 100)
    print("\n(a) MARGINAL screen. Every comparator scored on the same full span "
          "with the")
    print("    same two nulls. The family is LARGER than the original 15, so "
          "Holm is")
    print("    strictly stricter here than in DETECTION-CALIBRATION.md — "
          "adding\n    comparisons cannot make a claim easier to pass.")
    print(f"\n  {'series':<22}{'AUC':>8}{'p_shift':>9}{'p_aaft':>9}"
          f"{'max p':>8}{'null p95':>10}{'>=p95':>7}")
    print("  " + "-" * 73)
    for k in PRIMARY:
        r = fullspan.get(k)
        if r is None:
            continue
        print(f"  {k:<22}{r['auc']:>8.4f}{r['p_shift']:>9.4f}"
              f"{r['p_aaft']:>9.4f}{r['p']:>8.4f}{r['p95']:>10.4f}"
              f"{'yes' if r['auc'] >= r['p95'] else 'no':>7}")
    fam1 = {k: v["p"] for k, v in fullspan.items()}
    surv1 = holm(fam1, "H_C3(a) primary family — the original 9 candidates, "
                       "5 simpler alternatives, 2 pillars, 2 CSRS configs")

    print("\n(b) CONDITIONAL screen. Each signal orthogonalised against each "
          "comparator by")
    print(f"    a strictly backward-looking OLS fitted on indices [t-"
          f"{ORTHO_WINDOW}, t-1] (min "
          f"{ORTHO_MIN_OBS} obs).")
    print("    The fit never sees index t. If the signal's detection is just a "
          "repackaging")
    print("    of the comparator, the residual carries nothing.")
    print(f"\n  {'residual':<28}{'AUC':>8}{'p_shift':>9}{'p_aaft':>9}"
          f"{'max p':>8}{'null p95':>10}{'verdict':>9}")
    print("  " + "-" * 81)
    rng = np.random.default_rng(6060)
    resid_p = {}
    for sig, comp in ORTHO_PAIRS:
        res = causal_residual(series[sig], series[comp])
        name = f"{sig} |_ {comp}"
        r = evaluate(res, 0, n, breaks, a.perms, rng)
        if r is None:
            print(f"  {name:<28}  insufficient overlap")
            continue
        resid_p[name] = r["p"]
        print(f"  {name:<28}{r['auc']:>8.4f}{r['p_shift']:>9.4f}"
              f"{r['p_aaft']:>9.4f}{r['p']:>8.4f}{r['p95']:>10.4f}"
              f"{'SIG' if r['sig'] else 'not sig':>9}", flush=True)
    surv_r = holm(resid_p, "H_C3(b) orthogonalised family")
    allp = dict(fam1)
    allp.update(resid_p)
    surv_all = holm(allp, "CONSERVATIVE: every T1 comparison in this study "
                          "pooled into one family")

    # ========================================================= T3 ========== #
    print("\n" + "=" * 100)
    print("T3 — ADVANCE WARNING. REPORTED SEPARATELY AND DELIBERATELY NOT "
          "MIXED WITH T1.")
    print("=" * 100)
    print("A T1 pass says the signal is lit DURING a crisis. It is not evidence "
          "of any")
    print("ability to warn BEFORE one. T3 drops every in-crisis day from the "
          "sample, so a")
    print("model cannot 'predict' a crisis from inside it.")
    print(f"\nNo-signal distribution is re-derived per horizon "
          f"({a.t3_draws} draws of an AR(1)")
    print("background at the stationary variance, delta=0), because the null's "
          "width")
    print("depends on the horizon. delta=1.0 sd is also run as the power check.")
    phi = float(np.corrcoef(rv[:-1], rv[1:])[0, 1])
    print(f"background phi = {phi:.4f} (real rv_t_yz lag-1 autocorrelation)")
    saved_h = ewp.LEAD_H
    print(f"\nself-check at h=15 against EARLY-WARNING-POWER.md §4: "
          f"dd_accel 0.5924, rv_accel 0.4229, no-signal p95 0.6774")
    ewp.LEAD_H = 15
    for s in SIGNALS:
        print(f"  reproduced: {s} T3 AUC = "
              f"{ewp.t3_auc(series[s], breaks, n):.4f}")
    print(f"\n  {'h':>4} {'series':<11}{'T3 AUC':>9}{'shiftmu':>9}{'p_shift':>9}"
          f"{'aaftmu':>9}{'p_aaft':>9}{'null p95':>10}{'d=0 p95':>9}"
          f"{'pow d=1':>9}{'verdict':>9}")
    print("  " + "-" * 99)
    t3_p = {}
    for h in T3_HORIZONS:
        ewp.LEAD_H = h
        # horizon-specific no-signal distribution and a delta=1 power check
        ctrl, pow1 = [], 0
        for d in range(a.t3_draws):
            r2 = np.random.default_rng(770000 + 100 * h + d)
            x = ewp.ar1_stationary(n, phi, r2)
            x = (x - x.mean()) / x.std()
            ctrl.append(ewp.t3_auc(x, breaks, n))
            x1 = x.copy()
            for i in breaks:
                x1[max(0, i - h):i] += 1.0
            o1 = ewp.t3_auc(x1, breaks, n)
            nl1 = ewp.aaft_null(x1, n, breaks, min(a.t3_perms, 200), r2)
            pow1 += int((1 + int(np.sum(nl1 >= o1))) / (1 + nl1.size) <= 0.05)
        ctrl = np.array([c for c in ctrl if np.isfinite(c)])
        c95 = float(np.percentile(ctrl, 95))
        powr = pow1 / a.t3_draws
        rng3 = np.random.default_rng(8080 + h)
        for s in SIGNALS:
            o = ewp.t3_auc(series[s], breaks, n)
            nl = ewp.relocation_null(series[s], n, breaks, a.t3_perms, rng3)
            na = ewp.aaft_null(series[s], n, breaks, a.t3_perms, rng3)
            ps = (1 + int(np.sum(nl >= o))) / (1 + nl.size)
            pa = (1 + int(np.sum(na >= o))) / (1 + na.size)
            p95 = float(np.percentile(np.concatenate([nl, na]), 95))
            ok = max(ps, pa) <= 0.05 and o >= p95 and o >= c95
            t3_p[f"{s} T3 h={h}"] = max(ps, pa)
            print(f"  {h:>4} {s:<11}{o:>9.4f}{nl.mean():>9.4f}{ps:>9.4f}"
                  f"{na.mean():>9.4f}{pa:>9.4f}{p95:>10.4f}{c95:>9.4f}"
                  f"{powr:>9.0%}{'SIG' if ok else 'not sig':>9}", flush=True)
    ewp.LEAD_H = saved_h
    holm(t3_p, "T3: 2 signals x 4 horizons")
    print("  'pow d=1' is the test's power at this horizon against a clean "
          "1-sd step\n  over the h days before every onset — i.e. what T3 "
          "could have found had it\n  been there. A low number there means a "
          "T3 null is uninformative, not that\n  the signal is flat.")

    # =================================================== stability ========= #
    print("\n" + "=" * 100)
    print("STABILITY AND SENSITIVITY — EXPLORATORY. No variant below is "
          "selected, and")
    print("no claim is made from this section; the Holm families above are "
          "fixed and")
    print("deliberately exclude these, because screening windows and then "
          "reporting the")
    print("best one is exactly the error this whole study exists to catch.")
    print("=" * 100)

    print("\n--- acceleration window (dd_accel is k=5; k=1 is a plain 1-day "
          "difference) ---")
    print(f"  {'k':>4}{'T1 AUC':>9}{'p_shift':>9}{'p_aaft':>9}{'null p95':>10}"
          f"{'T3 h=15':>9}")
    print("  " + "-" * 50)
    rng = np.random.default_rng(9090)
    dd = series["drawdown"]
    for k in (1, 2, 3, 5, 10, 20):
        v = np.r_[np.full(k, np.nan), dd[k:] - dd[:-k]]
        r = evaluate(v, 0, n, breaks, a.perms, rng)
        ewp.LEAD_H = 15
        t3v = ewp.t3_auc(v, breaks, n)
        ewp.LEAD_H = saved_h
        print(f"  {k:>4}{r['auc']:>9.4f}{r['p_shift']:>9.4f}{r['p_aaft']:>9.4f}"
              f"{r['p95']:>10.4f}{t3v:>9.4f}", flush=True)

    print("\n--- rv_accel denominator window (rv_accel is w=20) ---")
    print(f"  {'w':>4}{'T1 AUC':>9}{'p_shift':>9}{'p_aaft':>9}{'null p95':>10}"
          f"{'T3 h=15':>9}")
    print("  " + "-" * 50)
    for w in (5, 10, 20, 40, 60):
        ma = ssc.roll(rv, w, np.mean)
        v = np.where(np.isfinite(ma) & (ma > 0), rv / ma, np.nan)
        r = evaluate(v, 0, n, breaks, a.perms, rng)
        ewp.LEAD_H = 15
        t3v = ewp.t3_auc(v, breaks, n)
        ewp.LEAD_H = saved_h
        print(f"  {w:>4}{r['auc']:>9.4f}{r['p_shift']:>9.4f}{r['p_aaft']:>9.4f}"
              f"{r['p95']:>10.4f}{t3v:>9.4f}", flush=True)

    print("\n--- causal trailing-mean smoothing of each signal ---")
    print(f"  {'series':<12}{'m':>4}{'T1 AUC':>9}{'p_shift':>9}{'p_aaft':>9}"
          f"{'null p95':>10}")
    print("  " + "-" * 53)
    for s in SIGNALS:
        for m in (1, 3, 5, 10):
            v = series[s] if m == 1 else ssc.roll(series[s], m, np.mean)
            r = evaluate(v, 0, n, breaks, a.perms, rng)
            print(f"  {s:<12}{m:>4}{r['auc']:>9.4f}{r['p_shift']:>9.4f}"
                  f"{r['p_aaft']:>9.4f}{r['p95']:>10.4f}", flush=True)

    print("\n--- per sub-period (grid split into thirds) ---")
    print(f"  {'series':<12}{'period':<26}{'ons':>4}{'T1 AUC':>9}{'p_shift':>9}"
          f"{'p_aaft':>9}{'null p95':>10}")
    print("  " + "-" * 79)
    thirds = [(0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n)]
    for s in SIGNALS:
        for (aa, bb) in thirds:
            r = evaluate(series[s], aa, bb, breaks, a.perms, rng)
            lbl = f"{dates[aa]}..{dates[bb - 1]}"
            if r is None:
                print(f"  {s:<12}{lbl:<26}{'0':>4}  no onset in sub-period")
                continue
            print(f"  {s:<12}{lbl:<26}{r['onsets']:>4}{r['auc']:>9.4f}"
                  f"{r['p_shift']:>9.4f}{r['p_aaft']:>9.4f}{r['p95']:>10.4f}",
                  flush=True)

    # =================================================== uncertainty ======= #
    print("\n" + "=" * 100)
    print("UNCERTAINTY — event-level, because the effective sample size is the "
          "number of")
    print("onsets, not the number of positive days")
    print("=" * 100)
    print(f"permutation-resolution floor: smallest p this study can report is "
          f"1/{a.perms + 1} = {1 / (1 + a.perms):.6f}.")
    print("Any p quoted at that value is censored, not measured: it means "
          "'no permutation")
    print("out of this many reached the observed statistic', and the true p "
          "could be smaller.")
    print(f"\n  {'series':<22}{'pooled AUC':>11}{'wmean per-onset':>17}"
          f"{'boot 2.5%':>11}{'boot 50%':>10}{'boot 97.5%':>12}")
    print("  " + "-" * 83)
    rngb = np.random.default_rng(1212)
    per_ep = {}
    for k in SIGNALS + ("drawdown", "rv_level", "semivar_20",
                        "CSRS 2p fullspan"):
        if k not in fullspan:
            continue
        po, w = per_onset_aucs(series[k], breaks, n)
        if not po:
            continue
        per_ep[k] = po
        pooled = fullspan[k]["auc"]
        wm, draws = cluster_bootstrap(po, w, a.boots, rngb)
        lo, md, hi = np.percentile(draws, [2.5, 50, 97.5])
        print(f"  {k:<22}{pooled:>11.4f}{wm:>17.4f}{lo:>11.4f}{md:>10.4f}"
              f"{hi:>12.4f}")
    print(f"\n  The cluster bootstrap resamples the {len(breaks)} ONSETS with "
          f"replacement, not the")
    print("  positive days. With 6 clusters the interval is wide by "
          "construction — that is")
    print("  the honest width, and the reason a single pooled AUC overstates "
          "precision.")
    print("  'wmean per-onset' is the positive-day-weighted mean of the "
          "per-onset AUCs; it")
    print("  equals the pooled AUC exactly when the negative set is shared, "
          "which is the")
    print("  arithmetic that licenses the bootstrap.")

    print(f"\n  {'series':<22}" + "".join(f"{ep_of[i][:11]:>13}" for i in breaks))
    print("  " + "-" * (22 + 13 * len(breaks)))
    for k, po in per_ep.items():
        print(f"  {k:<22}" + "".join(
            f"{po.get(i, float('nan')):>13.4f}" for i in breaks))
    print("\n  Per-epoch AUCs are the stability evidence that matters: a signal "
          "driven by one")
    print("  episode and flat on the rest is not a detector, whatever its "
          "pooled number.")

    print(f"\n[done in {time.time() - t_start:.0f}s. Nothing was written to the "
          f"database or to any existing file.]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
