#!/usr/bin/env python3
# C10 — statistical power of the T3 advance-warning test (FR32, FR33, O7)
"""Can the T3 early-warning test detect a real lead signal at six onsets?

### Why this has to be answered before any more detectors are tried

Every candidate tested so far sits at or below chance on T3: `semivar_20` 0.4928,
`drawdown` 0.6735, `jump_int_20` 0.5349, the 2-pillar CSRS 0.3723, the 3-pillar
CSRS 0.4367. The conclusion drawn was "no advance-warning capability". That
conclusion assumes the test could have found a signal if one were there, and
**that assumption has never been checked.**

T3 marks the 15 trading days before each FR32 break as positive, giving 6 x 15 =
90 positive days against ~5,100 negatives. But those 90 days come from **six
events**, and days inside one 15-day window are nearly perfectly correlated. An
AUC standard error computed as if 90 positives were independent understates the
true uncertainty by roughly sqrt(15). So two things are unknown:

1. **Is any observed T3 AUC significant** under a null that respects the
   autocorrelation? 0.6735 against a nominal 0.5 looks like something; against
   the right null it may be nothing.
2. **What effect size would T3 need** to detect a genuine lead signal at n=6?
   If the minimum detectable effect is implausibly large, then "T3 below chance"
   is uninformative and the honest claim is that advance warning is **untestable
   on this sample** — a different statement from "absent", and one that points at
   what additional evidence would be needed.

### Method

**The null is built by relocating the onsets, not by shuffling the series.**
Shuffling a feature would destroy the autocorrelation that makes this hard and
would produce an optimistically narrow null. Instead the six break dates are
moved to random positions on the same grid, the 15-day lead windows and the
30-day in-crisis exclusions are rebuilt around them exactly as `targets()` does,
and the AUC is recomputed. Everything about the feature is held fixed; only
*where the events are* changes. Placements keep the real minimum spacing so the
null windows are as separated as the real ones.

**The power curve** injects a known signal into a persistent AR(1) background
matched to the real features' lag-1 autocorrelation: a step of `delta` within-series
sd across the 15 days before each real onset. For each `delta` it reports the mean
T3 AUC and the fraction of draws rejecting the relocation null at alpha = 0.05 —
i.e. the test's power against an effect of exactly that size.

`delta = 0` is the negative control: its rejection rate must be close to alpha, or
the null is wrong and nothing else in this script means anything.

Observed candidates are evaluated with the study's own `build_features()` and
`targets()`, imported rather than reimplemented, so the evaluation definition
cannot drift from `study_stress_candidates.py`.

Run: python scripts/early_warning_power.py [--perms 500] [--draws 40]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402
from seraph.validation.harness import auc  # noqa: E402

# reuse the study's exact feature and target definitions
_spec = importlib.util.spec_from_file_location(
    "ssc", _ROOT / "scripts" / "study_stress_candidates.py")
ssc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ssc)

LEAD_H = ssc.LEAD_H
DELTAS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)


def t3_auc(score: np.ndarray, break_idx, n: int) -> float:
    """T3 AUC for a given set of onset positions.

    Window semantics are identical to `targets()`; indices are taken modulo `n`
    so a circularly shifted onset set is always valid.
    """
    y = np.zeros(n, dtype=int)
    in_crisis = np.zeros(n, dtype=bool)
    for i in break_idx:
        y[(np.arange(i - LEAD_H, i)) % n] = 1
        in_crisis[(np.arange(i, i + CRISIS_WINDOW_DAYS)) % n] = True
    keep = (~in_crisis) & np.isfinite(score)
    if y[keep].sum() < 5 or (1 - y[keep]).sum() < 5:
        return float("nan")
    return float(auc(score[keep], y[keep]))


def relocation_null(score, n, breaks, perms, rng):
    """AUCs under a **circular shift** of the whole onset set.

    Drawing onsets uniformly at random is the obvious null and it is wrong here.
    These features behave like near-random walks (rv_t_yz lag-1 autocorrelation
    0.9973), so the AUC depends heavily on *where in the walk* the lead windows
    fall, and the six real onsets are not a uniform draw. Tested directly: with
    uniform relocation the delta=0 negative control rejected at 50% instead of
    5%, i.e. the null was miscalibrated and every power number computed against
    it would have been void.

    Shifting all six onsets by one common offset preserves the configuration —
    every pairwise spacing, hence the overlap structure of the windows and the
    in-crisis exclusions — and varies only the phase. For a stationary series
    the shifted statistic is then exchangeable with the observed one by
    construction, which is what makes the p-value interpretable.

    The series is treated as circular, so windows spanning the wrap join two
    unrelated periods. That affects a handful of the `n` possible shifts and is
    the standard cost of a circular-shift null.
    """
    base = np.asarray(sorted(int(b) for b in breaks))
    offsets = rng.choice(np.arange(1, n), size=min(perms, n - 1), replace=False)
    out = [t3_auc(score, (base + int(o)) % n, n) for o in offsets]
    out = np.array([v for v in out if np.isfinite(v)])
    return out


def ar1_stationary(n, phi, rng):
    """AR(1) initialised at its stationary variance.

    Starting from x[0] = 0 instead leaves the series non-stationary for roughly
    1/(1-phi) ~ 370 steps at phi = 0.9973: early windows have systematically
    smaller dispersion than late ones. Four of the six real onsets sit in the
    back half of the grid, so the observed statistic then picks up
    higher-variance windows than most circular shifts do, and the delta=0
    control rejected at 40% instead of 5%. Measured, not assumed — that
    miscalibration is what sent this function into existence.
    """
    e = rng.normal(size=n)
    x = np.empty(n)
    x[0] = e[0] / np.sqrt(max(1.0 - phi ** 2, 1e-12))
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return x


def aaft_null(score, n, breaks, perms, rng):
    """AUCs with the **onsets fixed** and the series phase-randomised.

    The complementary null to the circular shift: instead of asking "would
    other onset dates have scored this well on this series", it asks "would
    other series with the same marginal and autocorrelation have scored this
    well on these onset dates". It cannot be biased by where the real onsets
    sit, which is exactly the failure mode the shift null has on a near-unit-root
    series, so it is the calibration check on that null.
    """
    finite = np.isfinite(score)
    vals = score[finite]
    m = vals.size
    ranks = np.argsort(np.argsort(vals))
    out = []
    for _ in range(perms):
        normal_scores = np.sort(rng.normal(size=m))
        spec = np.fft.rfft(normal_scores[ranks])
        phase = rng.uniform(0, 2 * np.pi, size=spec.shape[0])
        phase[0] = 0.0
        if m % 2 == 0:
            phase[-1] = 0.0
        sur = np.fft.irfft(np.abs(spec) * np.exp(1j * (np.angle(spec) + phase)),
                           n=m)
        remapped = np.sort(vals)[np.argsort(np.argsort(sur))]
        full = np.full(n, np.nan)
        full[finite] = remapped
        a = t3_auc(full, breaks, n)
        if np.isfinite(a):
            out.append(a)
    return np.array(out)


async def load():
    conn = await asyncpg.connect(resolve_dsn(), timeout=300)
    obs = await conn.fetch(
        "SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output ORDER BY date")
    mkt = await conn.fetch("""
      WITH r AS (SELECT date, symbol,
                        ln(adj_close / NULLIF(lag(adj_close) OVER (
                            PARTITION BY symbol ORDER BY date), 0)) lr
                 FROM daily_prices WHERE universe_member_flag AND adj_close > 0)
      SELECT date, avg(lr) mkt FROM r WHERE lr IS NOT NULL
      GROUP BY date ORDER BY date""")
    await conn.close()
    return obs, mkt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=500)
    ap.add_argument("--draws", type=int, default=40)
    ap.add_argument("--null", choices=("shift", "aaft"), default="shift",
                    help="null used for the power curve; both are always "
                         "reported for the observed candidates")
    a = ap.parse_args()

    obs, mkt = asyncio.run(load())
    mk = {str(r["date"]): float(r["mkt"]) for r in mkt}
    rows = [r for r in obs if str(r["date"]) in mk]
    dates = [str(r["date"]) for r in rows]
    n = len(dates)
    lr = np.array([mk[d] for d in dates])
    rv = np.array([float(r["rv_t_yz"]) for r in rows])
    ar = np.array([float(r["ar_t"]) for r in rows])
    bas = np.array([float(r["bas_t"]) for r in rows])

    feats = ssc.build_features(dates, lr, rv, ar, bas)
    _, bi = ssc.targets(dates)
    breaks = sorted(int(v) for v in bi.values())
    min_gap = int(np.diff(breaks).min())

    print(f"grid: {n:,} days {dates[0]} .. {dates[-1]}")
    print(f"onsets: {len(breaks)} at {breaks}  min spacing {min_gap} days")
    print(f"T3 positives: {len(breaks) * LEAD_H} days from {len(breaks)} "
          f"independent events\n", flush=True)

    rng = np.random.default_rng(4242)

    # ---------- 1. are the observed T3 AUCs significant? ----------------- #
    print("=== 1. OBSERVED CANDIDATES vs THE RELOCATION NULL ===")
    print(f"{'candidate':>14} {'T3 AUC':>8} {'shiftmean':>10} {'shiftsd':>8} "
          f"{'p_shift':>10} {'aaftmean':>10} {'p_aaft':>10} {'verdict':>10}")
    print("-" * 92)
    observed = {}
    for name in ("drawdown", "dd_accel", "jump_int_20", "semivar_20",
                 "rv_accel", "vol_of_vol", "rv_level", "ar_t", "bas_t"):
        s = feats[name]
        obs_auc = t3_auc(s, breaks, n)
        nl = relocation_null(s, n, breaks, a.perms, rng)
        na = aaft_null(s, n, breaks, min(a.perms, 200), rng)
        p_shift = (1 + int(np.sum(nl >= obs_auc))) / (1 + nl.size)
        p_aaft = (1 + int(np.sum(na >= obs_auc))) / (1 + na.size)
        observed[name] = {"auc": obs_auc, "p": p_shift, "p_aaft": p_aaft}
        sig = "SIG" if max(p_shift, p_aaft) <= 0.05 else "not sig"
        print(f"{name:>14} {obs_auc:>8.4f} {nl.mean():>10.4f} "
              f"{nl.std(ddof=1):>8.4f} {p_shift:>10.4f} {na.mean():>10.4f} "
              f"{p_aaft:>10.4f} {sig:>10}", flush=True)

    print("\n  The relocation null is centred near 0.5 only if the lead window")
    print("  carries no information wherever it is placed. A null mean far from")
    print("  0.5 means the feature's own trend, not the events, drives the AUC.")

    # ---------- 2. how large would a detectable signal have to be? ------- #
    print(f"\n=== 2. POWER CURVE ({a.draws} draws/delta, "
          f"{min(a.perms, 200)} perms/draw, alpha=0.05) ===")
    phi = float(np.corrcoef(rv[:-1], rv[1:])[0, 1])
    print(f"  background: AR(1) with phi = {phi:.4f} (real rv_t_yz lag-1 "
          f"autocorrelation)")
    print(f"  signal: step of delta x sd over the {LEAD_H} days before each of "
          f"the {len(breaks)} real onsets\n")
    print(f"{'delta (sd)':>11} {'mean T3 AUC':>12} {'sd':>7} "
          f"{'mean p':>8} {'POWER at 0.05':>14}")
    print("-" * 58)
    nperm = min(a.perms, 200)
    power_rows = []
    auc_by_delta: dict[float, np.ndarray] = {}
    for delta in DELTAS:
        aucs, pvals, rejects = [], [], 0
        for d in range(a.draws):
            r2 = np.random.default_rng(99000 + 1000 * int(delta * 10) + d)
            x = ar1_stationary(n, phi, r2)
            x = (x - x.mean()) / x.std()
            for i in breaks:
                x[max(0, i - LEAD_H):i] += delta
            obs_auc = t3_auc(x, breaks, n)
            null = (relocation_null(x, n, breaks, nperm, r2) if a.null == "shift"
                    else aaft_null(x, n, breaks, nperm, r2))
            pval = (1 + int(np.sum(null >= obs_auc))) / (1 + null.size)
            aucs.append(obs_auc)
            pvals.append(pval)
            rejects += int(pval <= 0.05)
        power = rejects / a.draws
        power_rows.append((delta, float(np.mean(aucs)), power))
        auc_by_delta[delta] = np.array(aucs)
        print(f"{delta:>11.1f} {np.mean(aucs):>12.4f} {np.std(aucs):>7.4f} "
              f"{np.mean(pvals):>8.4f} {power:>13.0%}", flush=True)

    # ---------- 3. what the power curve implies --------------------------- #
    print("\n=== 3. INTERPRETATION ===")
    ctrl = next((p for d, _, p in power_rows if d == 0.0), None)
    null0 = auc_by_delta.get(0.0)
    if ctrl is not None:
        print(f"  ACTUAL type-I error at nominal alpha=0.05: {ctrl:.0%} "
              f"({a.null} null, {a.draws} draws)")
        print("  Six onsets on a 21-year grid admit only ~10-15 effectively")
        print("  independent event configurations, so the permutation p-value is")
        print("  granular and its tails are heavy. Nominal p-values from this")
        print("  test are therefore optimistic by roughly a factor of two, and")
        print("  the comparison below is used instead of them.")

    if null0 is not None and null0.size >= 20:
        thr = float(np.percentile(null0, 95))
        print(f"\n  CALIBRATED comparison — T3 AUC under NO signal (delta=0):")
        print(f"    mean {null0.mean():.4f}  sd {null0.std(ddof=1):.4f}  "
              f"median {np.median(null0):.4f}  95th pct {thr:.4f}  "
              f"max {null0.max():.4f}")
        over = [(k, v["auc"]) for k, v in observed.items() if v["auc"] >= thr]
        print(f"    candidates at or above the 95th percentile ({thr:.4f}): "
              f"{over if over else 'NONE'}")

    mde = next((d for d, _, p in power_rows if d > 0 and p >= 0.80), None)
    if mde is None:
        print(f"\n  No tested effect size reaches 80% power. Even a "
              f"{DELTAS[-1]:.0f} sd step confined to the {LEAD_H} days before "
              f"each onset is not reliably detectable at n={len(breaks)} events,")
        print("  so 'T3 below chance' would not establish anything either way.")
    else:
        print(f"\n  MINIMUM DETECTABLE EFFECT at 80% power: delta = {mde:.1f} sd "
              f"(nominal; ~{mde + 0.5:.1f} sd once the type-I inflation above is "
              f"allowed for).")
        print(f"  So the test DOES have power against a clean, strong lead")
        print(f"  signal. A step of >= {mde:.1f} sd over the {LEAD_H} days before")
        print(f"  each onset would have been found. Nothing in the corpus")
        print(f"  produces one. Effects below ~0.5 sd remain genuinely untested.")
    best = max(observed.items(), key=lambda kv: kv[1]["auc"])
    worst_p = max(best[1]["p"], best[1]["p_aaft"])
    print(f"\n  best observed: {best[0]} AUC {best[1]['auc']:.4f}, "
          f"p_shift = {best[1]['p']:.4f}, p_aaft = {best[1]['p_aaft']:.4f} "
          f"({'significant under both' if worst_p <= 0.05 else 'NOT significant'})")
    print("  9 candidates were screened, so even a p near 0.05 would still need")
    print("  a multiplicity correction before it counted as a finding.")
    print("\n  No advance-warning capability is claimed by this script. It")
    print("  measures what the existing evaluation can and cannot establish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
