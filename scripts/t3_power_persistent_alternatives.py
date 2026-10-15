#!/usr/bin/env python3
# C10 — T3 power against PERSISTENT alternatives, not just a rectangular step
# (FR32, FR33, O7). Research only; writes nothing.
"""Does the T3 advance-warning test have power against the signal shape a
systemic-risk thesis actually predicts?

### The claim under test, and whose claim it is

`EARLY-WARNING-POWER.md` §3 reports 85% power at delta = 1.0 sd and 98% at 1.5,
and concludes the T3 negative is informative rather than underpowered.
`CRISIS-REPLAY.md` rests its "bounded, not absolute" advance-warning negative on
that number.

But the injected signal there is a **rectangular step of delta sd confined to
exactly the LEAD_H = 15 days that T3 labels positive**. That is the single most
favourable alternative the test can face: the signal is on precisely where the
label is on, and off precisely where it is off. A systemic-risk thesis does not
predict that. It predicts a **build-up** — stress accumulating over weeks or
months before the break. Under a build-up, most of the injected signal falls on
days T3 labels NEGATIVE, which actively works against the AUC.

So the existing power curve may bound the wrong thing, and both reports' bounds
may be weaker than stated. This script settles it.

### The three injected shapes, stated precisely

All three are added to the same AR(1) background (`ar1_stationary`, phi measured
from real `rv_t_yz`), standardised to zero mean and unit variance first, so
`delta` is in within-series sd units for all three. All three are normalised to
the **same peak amplitude** `delta`, so the sweep varies shape at fixed peak and
cannot be confounded with amplitude. The mean amplitude *inside the T3 positive
window* differs between shapes, is reported, and is the mechanism by which power
differs.

Let `i` be an onset index, `h` the T3 lead horizon (label is 1 on `[i-h, i)`),
`L` the build-up length, and `D = CRISIS_WINDOW_DAYS = 30` the decay length.

1. **step** (reference, as in `early_warning_power.py`)
   `a[u] = delta` for `u` in `[i-h, i)`, else 0.
   Peak `delta`. Confined to the labelled window by construction.

2. **ramp** — linear build-up, then fall back
   `a[u] = delta * (u - (i-L) + 1) / L` for `u` in `[i-L, i)`
   `a[u] = delta * (1 - (u - i + 1) / D)` for `u` in `[i, i+D)`   (fall back)
   else 0. Peak `delta` at `u = i-1`. Rises from `delta/L` at the start of the
   build-up. The decay sits entirely inside the FR32 crisis window, which T3
   excludes from the sample, so it is present for realism and has no effect on
   the statistic — stated so no one mistakes it for a tuning knob.

3. **ar1drift** — AR(1)-persistent drift switched on `L` sessions early
   `s[i-L-1] = 0`;  `s[u] = phi_d * s[u-1] + (1 - phi_d) * A` for `u` in `[i-L, i)`
   with `A = delta / (1 - phi_d**L)` so that `max(s) = delta` exactly.
   `phi_d` is the measured lag-1 autocorrelation of real `rv_t_yz`. Same linear
   fall-back over `[i, i+D)`. This is a concave approach to `delta` with the
   corpus's own persistence, rather than the ramp's linear one.

`delta` sweeps `early_warning_power.DELTAS` unchanged: 0, 0.5, 1.0, 1.5, 2.0,
3.0, 4.0. `delta = 0` is the negative control for all three shapes and must
reject near alpha or nothing else here means anything.

### Two horizons, because the mismatch is the point

* `h = 15` — the project's own LEAD_H, and the horizon both existing reports'
  claims rest on. With `L = 75` only the last 15 of 75 build-up days are labelled
  positive; the other 60 are labelled negative while carrying signal.
* `h = L` — the horizon matched to the build-up. If a ramp is detectable here but
  not at `h = 15`, the problem is horizon mis-specification, not absent signal,
  and that is a different and more actionable finding.

### Nulls, and why their nominal resolution overstates what they can resolve

Both null families are kept, imported not copied: `relocation_null` (circular
shift of the whole onset set) and `aaft_null` (onsets fixed, series
phase-randomised). Power is reported under each separately and under the
**conjunction** `max(p_shift, p_aaft) <= 0.05`, which is the rule the rest of the
project uses for a verdict.

The permutation-resolution floor `1/(1+perms)` is printed. It is an upper bound
on precision, not a description of it: Workstream B measured the integral
timescale of `rv_t_yz` at ~770 sessions, so a 5,362-session grid holds only
~7 effectively independent circular shifts. This script measures that timescale
itself and prints the implied **effective** shift-null resolution alongside the
nominal one. A 60-90 session build-up is well inside one decorrelation length,
which is exactly why the shift null is the weaker of the two here and why the
AAFT null — which regenerates the series rather than moving the events — carries
the weight.

### Pre-registered decision rule (set by the coordinator before this was run)

If power against a 60-90 session ramp at `delta = 1.0` sd is **below ~50%**, then
"SERAPH shows no advance warning" is NOT supportable and must be downgraded to
"advance warning is untestable at six onsets against the signal shape a
systemic-risk thesis predicts". The number is reported either way. Nothing about
the injection is tuned to reach any particular answer: the shapes, the
normalisation, the delta grid, the horizons and the build-up lengths were all
fixed in this docstring before the first run.

Writes nothing. Reads `hamilton_output` (rv_t_yz, ar_t, bas_t) and
`daily_prices`.

Run: python scripts/t3_power_persistent_alternatives.py [--draws 60] [--perms 200]
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
from seraph.validation.epochs import CRISIS_WINDOW_DAYS  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ssc = _load("ssc", "scripts/study_stress_candidates.py")
ewp = _load("ewp", "scripts/early_warning_power.py")

DELTAS = ewp.DELTAS                 # 0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0 — unchanged
BUILDUP = 75                        # primary build-up length, midpoint of 60-90
BUILDUP_ALT = (60, 90)              # the stated range's endpoints
DECAY = CRISIS_WINDOW_DAYS          # 30; falls inside T3's exclusion by design
PROJECT_H = 15                      # early_warning_power.LEAD_H
OBSERVED_H = (60, 75, 90)           # matched horizons for the real signals
SHAPES = ("step", "ramp", "ar1drift")


# ------------------------------------------------------------ the injections --

def inject(x: np.ndarray, breaks, n: int, shape: str, delta: float, *,
           h: int, L: int, phi_d: float) -> np.ndarray:
    """Add `shape` at peak amplitude `delta` before each onset. See docstring."""
    a = np.zeros(n)
    if delta == 0.0:
        return x
    for i in breaks:
        if shape == "step":
            for u in range(i - h, i):
                if 0 <= u < n:
                    a[u] += delta
            continue
        if shape == "ramp":
            for k in range(L):
                u = i - L + k
                if 0 <= u < n:
                    a[u] += delta * (k + 1) / L
        elif shape == "ar1drift":
            denom = 1.0 - phi_d ** L
            A = delta / denom if abs(denom) > 1e-12 else delta
            s = 0.0
            for k in range(L):
                s = phi_d * s + (1.0 - phi_d) * A
                u = i - L + k
                if 0 <= u < n:
                    a[u] += s
        else:
            raise ValueError(shape)
        for k in range(DECAY):          # fall-back, inside T3's exclusion
            u = i + k
            if 0 <= u < n:
                a[u] += delta * (1.0 - (k + 1) / DECAY)
    return x + a


def shape_diagnostics(breaks, n: int, shape: str, *, h: int, L: int,
                       phi_d: float) -> dict:
    """Peak, and mean amplitude on the days T3 actually labels positive."""
    a = inject(np.zeros(n), breaks, n, shape, 1.0, h=h, L=L, phi_d=phi_d)
    pos = np.zeros(n, bool)
    in_crisis = np.zeros(n, bool)
    for i in breaks:
        pos[(np.arange(i - h, i)) % n] = True
        in_crisis[(np.arange(i, i + CRISIS_WINDOW_DAYS)) % n] = True
    carrying = (a > 1e-12) & (~in_crisis)
    return {"peak": float(a.max()),
            "mean_on_positive": float(a[pos].mean()),
            "days_carrying": int(carrying.sum()),
            "days_positive": int(pos.sum()),
            "carrying_but_labelled_negative": int((carrying & ~pos).sum())}


# --------------------------------------------------------- autocorrelation ----

def integral_timescale(v: np.ndarray, max_lag: int = 2500) -> tuple[float, int]:
    """tau = 1 + 2 * sum rho_k, summed to the first non-positive rho.

    The number of effectively independent realisations on a grid of length n is
    then about n / tau. For a near-unit-root series tau is large and the
    circular-shift null's nominal permutation count badly overstates how many
    independent draws it actually contains.
    """
    x = v[np.isfinite(v)]
    x = x - x.mean()
    m = x.size
    denom = float(np.dot(x, x))
    if denom <= 0:
        return float("nan"), 0
    tau, used = 1.0, 0
    for k in range(1, min(max_lag, m - 2)):
        rho = float(np.dot(x[:-k], x[k:])) / denom
        if rho <= 0.0:
            break
        tau += 2.0 * rho
        used = k
    return tau, used


# ----------------------------------------------------------------- data load --

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
    await c.close()
    return obs, mkt


def holm(pvals: dict[str, float], label: str) -> list[str]:
    ranked = sorted((p, k) for k, p in pvals.items())
    m = len(ranked)
    print(f"\n  Holm over {m} comparisons ({label}); tightest threshold "
          f"0.05/{m} = {0.05 / m:.5f}")
    surv = []
    for i, (p, k) in enumerate(ranked, start=1):
        thr = 0.05 / (m - i + 1)
        ok = p <= thr
        print(f"    {i:>2}. {k:<24} p={p:.4f}  thr={thr:.5f}  "
              f"{'survives' if ok else 'does NOT survive — step-down stops here'}")
        if not ok:
            break
        surv.append(k)
    print(f"  survives Holm over all {m}: {surv if surv else 'NONE'}")
    return surv


# ---------------------------------------------------------------------- main --

def power_sweep(n, breaks, phi, phi_d, h, L, draws, perms, seed0):
    """Power for each shape x delta at horizon h and build-up L."""
    saved = ewp.LEAD_H
    ewp.LEAD_H = h
    rows = {}
    for shape in SHAPES:
        for delta in DELTAS:
            rej_s = rej_a = rej_c = 0
            aucs, ps_l, pa_l = [], [], []
            for d in range(draws):
                r2 = np.random.default_rng(seed0 + 7919 * SHAPES.index(shape)
                                           + 101 * int(delta * 10) + d)
                x = ewp.ar1_stationary(n, phi, r2)
                x = (x - x.mean()) / x.std()
                x = inject(x, breaks, n, shape, delta, h=h, L=L, phi_d=phi_d)
                o = ewp.t3_auc(x, breaks, n)
                if not np.isfinite(o):
                    continue
                nl = ewp.relocation_null(x, n, breaks, perms, r2)
                na = ewp.aaft_null(x, n, breaks, perms, r2)
                ps = (1 + int(np.sum(nl >= o))) / (1 + nl.size)
                pa = (1 + int(np.sum(na >= o))) / (1 + na.size)
                aucs.append(o)
                ps_l.append(ps)
                pa_l.append(pa)
                rej_s += int(ps <= 0.05)
                rej_a += int(pa <= 0.05)
                rej_c += int(max(ps, pa) <= 0.05)
            k = max(len(aucs), 1)
            rows[(shape, delta)] = {
                "auc": float(np.mean(aucs)) if aucs else float("nan"),
                "sd": float(np.std(aucs)) if aucs else float("nan"),
                "p_shift": float(np.mean(ps_l)) if ps_l else float("nan"),
                "p_aaft": float(np.mean(pa_l)) if pa_l else float("nan"),
                "pow_shift": rej_s / k, "pow_aaft": rej_a / k,
                "pow_conj": rej_c / k, "draws": len(aucs),
                "aucs": np.array(aucs)}
            print(f"  {shape:<9}{delta:>6.1f}{rows[(shape, delta)]['auc']:>11.4f}"
                  f"{rows[(shape, delta)]['sd']:>8.4f}"
                  f"{rows[(shape, delta)]['p_shift']:>9.4f}"
                  f"{rows[(shape, delta)]['p_aaft']:>9.4f}"
                  f"{rows[(shape, delta)]['pow_shift']:>11.0%}"
                  f"{rows[(shape, delta)]['pow_aaft']:>10.0%}"
                  f"{rows[(shape, delta)]['pow_conj']:>11.0%}", flush=True)
    ewp.LEAD_H = saved
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=60)
    ap.add_argument("--perms", type=int, default=200)
    ap.add_argument("--obs-perms", type=int, default=1000)
    a = ap.parse_args()
    t0 = time.time()

    print("=" * 100)
    print("T3 POWER AGAINST PERSISTENT ALTERNATIVES — is the advance-warning "
          "negative informative?")
    print("=" * 100)
    print(__doc__.split("### Pre-registered decision rule")[0].strip())
    print("\n### Pre-registered decision rule")
    print(__doc__.split("### Pre-registered decision rule")[1]
          .split("Writes nothing")[0].strip())
    print("=" * 100)

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

    phi = float(np.corrcoef(rv[:-1], rv[1:])[0, 1])
    phi_d = phi
    print(f"\ngrid    : {n:,} days {dates[0]} .. {dates[-1]}")
    print(f"onsets  : {len(breaks)} at {breaks}, min spacing "
          f"{int(np.diff(breaks).min())}")
    print(f"phi     : {phi:.4f} (real rv_t_yz lag-1 autocorrelation); used for "
          f"both the AR(1) background and ar1drift")
    print(f"deltas  : {list(DELTAS)}  (unchanged from early_warning_power.py)")
    print(f"build-up: L = {BUILDUP} primary, {BUILDUP_ALT} as the stated "
          f"60-90 range's endpoints; decay {DECAY} days")

    # --------------------------------------------------- resolution limits --
    print("\n" + "=" * 100)
    print("0. WHAT THESE NULLS CAN AND CANNOT RESOLVE")
    print("=" * 100)
    print(f"nominal permutation-resolution floor: 1/(1+{a.perms}) = "
          f"{1 / (1 + a.perms):.5f} for the power sweep,")
    print(f"                                      1/(1+{a.obs_perms}) = "
          f"{1 / (1 + a.obs_perms):.6f} for the observed signals.")
    print(f"\n  {'series':<14}{'integral timescale tau':>24}{'lags used':>11}"
          f"{'n/tau = N_eff':>15}{'eff. shift resolution':>23}")
    print("  " + "-" * 87)
    for nm, v in (("rv_t_yz", rv), ("dd_accel", feats["dd_accel"]),
                  ("rv_accel", feats["rv_accel"]),
                  ("AR(1) background", ewp.ar1_stationary(
                      n, phi, np.random.default_rng(1)))):
        tau, used = integral_timescale(v)
        neff = n / tau if np.isfinite(tau) and tau > 0 else float("nan")
        print(f"  {nm:<14}{tau:>24.1f}{used:>11,}{neff:>15.1f}"
              f"{1 / max(neff, 1):>23.3f}")
    print("\n  The circular-shift null prints a p-value to 1/(1+perms) but its")
    print("  draws are not independent: shifts closer together than one")
    print("  decorrelation length give almost the same statistic. The effective")
    print("  resolution column is the honest granularity of p_shift. A 60-90")
    print("  session build-up is well inside one decorrelation length, so the")
    print("  AAFT null — which regenerates the series instead of moving the")
    print("  events — is the one that carries weight here, and power is also")
    print("  reported under it separately for that reason.")
    print("  CONSEQUENCE: Holm's threshold at 6 comparisons is 0.00833. If the")
    print("  effective shift resolution is coarser than that, no p_shift can")
    print("  reach it however many permutations are drawn — a resolution limit,")
    print("  not evidence.")

    # ------------------------------------------------- shape diagnostics ---
    print("\n" + "=" * 100)
    print("1. THE THREE SHAPES, AT PEAK AMPLITUDE delta = 1.0")
    print("=" * 100)
    print("Same peak for all three, so the sweep varies SHAPE at fixed "
          "amplitude. What")
    print("differs is how much of the injected signal lands on days T3 labels "
          "positive.")
    for h, L in ((PROJECT_H, BUILDUP), (BUILDUP, BUILDUP)):
        print(f"\n  horizon h={h}, build-up L={L}")
        print(f"  {'shape':<10}{'peak':>7}{'mean on positive days':>24}"
              f"{'days carrying signal':>23}{'of which labelled NEG':>24}")
        print("  " + "-" * 88)
        for shape in SHAPES:
            d = shape_diagnostics(breaks, n, shape, h=h, L=L, phi_d=phi_d)
            print(f"  {shape:<10}{d['peak']:>7.3f}"
                  f"{d['mean_on_positive']:>24.4f}"
                  f"{d['days_carrying']:>23,}"
                  f"{d['carrying_but_labelled_negative']:>24,}")
    print("\n  This table is the whole mechanism. At h=15 the step puts its full")
    print("  amplitude on every labelled day and nothing anywhere else. The ramp")
    print("  and the drift put most of their signal on days T3 labels NEGATIVE,")
    print("  which pushes the AUC DOWN, not up.")

    # ------------------------------------------------------- power sweeps --
    allrows = {}
    for h, L, tag in ((PROJECT_H, BUILDUP, "PROJECT HORIZON"),
                      (BUILDUP, BUILDUP, "MATCHED HORIZON")):
        print("\n" + "=" * 100)
        print(f"2{'ab'[h != PROJECT_H]}. POWER SWEEP — {tag}: h={h}, L={L}, "
              f"{a.draws} draws/cell, {a.perms} perms/null, alpha=0.05")
        print("=" * 100)
        print(f"  {'shape':<9}{'delta':>6}{'mean T3 AUC':>11}{'sd':>8}"
              f"{'p_shift':>9}{'p_aaft':>9}{'POW shift':>11}{'POW aaft':>10}"
              f"{'POW conj':>11}")
        print("  " + "-" * 84)
        allrows[h] = power_sweep(n, breaks, phi, phi_d, h, L, a.draws,
                                 a.perms, 310000 + 1000 * h)

    # ----------------------------------------- build-up length sensitivity --
    print("\n" + "=" * 100)
    print(f"3. BUILD-UP LENGTH SENSITIVITY at delta = 1.0 "
          f"(the decision rule's amplitude)")
    print("=" * 100)
    print(f"  {'shape':<10}{'L':>5}{'h':>5}{'mean T3 AUC':>12}{'POW shift':>11}"
          f"{'POW aaft':>10}{'POW conj':>11}")
    print("  " + "-" * 64)
    for L in BUILDUP_ALT:
        for h in (PROJECT_H, L):
            saved = ewp.LEAD_H
            ewp.LEAD_H = h
            for shape in ("ramp", "ar1drift"):
                rej_s = rej_a = rej_c = 0
                aucs = []
                for d in range(a.draws):
                    r2 = np.random.default_rng(
                        420000 + 977 * L + 31 * h
                        + 7 * SHAPES.index(shape) + d)
                    x = ewp.ar1_stationary(n, phi, r2)
                    x = (x - x.mean()) / x.std()
                    x = inject(x, breaks, n, shape, 1.0, h=h, L=L, phi_d=phi_d)
                    o = ewp.t3_auc(x, breaks, n)
                    if not np.isfinite(o):
                        continue
                    nl = ewp.relocation_null(x, n, breaks, a.perms, r2)
                    na = ewp.aaft_null(x, n, breaks, a.perms, r2)
                    ps = (1 + int(np.sum(nl >= o))) / (1 + nl.size)
                    pa = (1 + int(np.sum(na >= o))) / (1 + na.size)
                    aucs.append(o)
                    rej_s += int(ps <= 0.05)
                    rej_a += int(pa <= 0.05)
                    rej_c += int(max(ps, pa) <= 0.05)
                k = max(len(aucs), 1)
                print(f"  {shape:<10}{L:>5}{h:>5}{np.mean(aucs):>12.4f}"
                      f"{rej_s / k:>11.0%}{rej_a / k:>10.0%}"
                      f"{rej_c / k:>11.0%}", flush=True)
            ewp.LEAD_H = saved

    # ------------------------------------- the real signals, matched horizons -
    print("\n" + "=" * 100)
    print("4. THE REAL SIGNALS AT THE MATCHED HORIZONS (60/75/90) — never "
          "tested before")
    print("=" * 100)
    print("If a build-up is the hypothesised shape, the matched horizon is where")
    print("it should be looked for. Log 40 only reached h=30.")
    print(f"\n  {'series':<11}{'h':>4}{'T3 AUC':>9}{'shiftmu':>9}{'p_shift':>9}"
          f"{'aaftmu':>9}{'p_aaft':>9}{'null p95':>10}{'d=0 p95':>9}"
          f"{'verdict':>9}")
    print("  " + "-" * 88)
    saved = ewp.LEAD_H
    obs_p = {}
    for h in OBSERVED_H:
        ewp.LEAD_H = h
        ctrl = []
        for d in range(a.draws):
            r2 = np.random.default_rng(555000 + 13 * h + d)
            x = ewp.ar1_stationary(n, phi, r2)
            x = (x - x.mean()) / x.std()
            v = ewp.t3_auc(x, breaks, n)
            if np.isfinite(v):
                ctrl.append(v)
        c95 = float(np.percentile(np.array(ctrl), 95))
        rng = np.random.default_rng(66000 + h)
        for nm in ("dd_accel", "rv_accel"):
            s = feats[nm]
            o = ewp.t3_auc(s, breaks, n)
            nl = ewp.relocation_null(s, n, breaks, a.obs_perms, rng)
            na = ewp.aaft_null(s, n, breaks, a.obs_perms, rng)
            ps = (1 + int(np.sum(nl >= o))) / (1 + nl.size)
            pa = (1 + int(np.sum(na >= o))) / (1 + na.size)
            p95 = float(np.percentile(np.concatenate([nl, na]), 95))
            ok = max(ps, pa) <= 0.05 and o >= p95 and o >= c95
            obs_p[f"{nm} h={h}"] = max(ps, pa)
            print(f"  {nm:<11}{h:>4}{o:>9.4f}{nl.mean():>9.4f}{ps:>9.4f}"
                  f"{na.mean():>9.4f}{pa:>9.4f}{p95:>10.4f}{c95:>9.4f}"
                  f"{'SIG' if ok else 'not sig':>9}", flush=True)
    ewp.LEAD_H = saved
    holm(obs_p, "2 signals x 3 matched horizons")

    # ---------------------------------------------------------- the verdict --
    print("\n" + "=" * 100)
    print("5. VERDICT AGAINST THE PRE-REGISTERED RULE")
    print("=" * 100)
    print("Rule: if power against a 60-90 session ramp at delta = 1.0 sd is")
    print("below ~50%, 'SERAPH shows no advance warning' is NOT supportable and")
    print("must be downgraded to 'advance warning is untestable at six onsets")
    print("against the signal shape a systemic-risk thesis predicts'.\n")
    print(f"  {'shape':<10}{'h':>5}{'power(shift)':>14}{'power(aaft)':>13}"
          f"{'power(conj)':>13}")
    print("  " + "-" * 55)
    for h in (PROJECT_H, BUILDUP):
        for shape in SHAPES:
            r = allrows[h][(shape, 1.0)]
            print(f"  {shape:<10}{h:>5}{r['pow_shift']:>14.0%}"
                  f"{r['pow_aaft']:>13.0%}{r['pow_conj']:>13.0%}")
    ramp15 = allrows[PROJECT_H][("ramp", 1.0)]
    ramp_m = allrows[BUILDUP][("ramp", 1.0)]
    step15 = allrows[PROJECT_H][("step", 1.0)]
    ctrl0 = {(sh, h): allrows[h][(sh, 0.0)]["pow_conj"]
             for sh in SHAPES for h in (PROJECT_H, BUILDUP)}
    print(f"\n  negative controls (delta=0, must sit near 0.05): "
          f"{ {k: f'{v:.0%}' for k, v in ctrl0.items()} }")
    print(f"\n  REFERENCE  step at h={PROJECT_H}, delta=1.0 : "
          f"power(conj) = {step15['pow_conj']:.0%}  "
          f"(this is what EARLY-WARNING-POWER.md reported)")
    print(f"  TESTED     ramp L={BUILDUP} at h={PROJECT_H}, delta=1.0: "
          f"power(conj) = {ramp15['pow_conj']:.0%}")
    print(f"  TESTED     ramp L={BUILDUP} at h={BUILDUP} (matched)   : "
          f"power(conj) = {ramp_m['pow_conj']:.0%}")
    below = ramp15["pow_conj"] < 0.50
    print(f"\n  >>> ramp power at the PROJECT horizon is "
          f"{'BELOW' if below else 'AT OR ABOVE'} 50%.")
    if below:
        print("  >>> The rule licenses: 'SERAPH shows no advance warning' is NOT")
        print("  >>> supportable as stated. It must be downgraded to 'advance")
        print("  >>> warning is UNTESTABLE at six onsets against the signal")
        print("  >>> shape a systemic-risk thesis predicts'. The existing 85-98%")
        print("  >>> power figure bounds only a rectangular step aligned to the")
        print("  >>> label window, which is not that shape.")
    else:
        print("  >>> The rule licenses the existing conclusion: the test retains")
        print("  >>> real power against a build-up, so the T3 negative is")
        print("  >>> informative and 'no advance warning' stands as stated.")
    print(f"\n  Reported either way, as pre-registered. Nothing about the")
    print(f"  injection was tuned: shapes, peak normalisation, delta grid,")
    print(f"  horizons and build-up lengths were all fixed in the docstring")
    print(f"  before the first run.")
    print(f"\n[done in {time.time() - t0:.0f}s. Nothing written to the database "
          f"or to any existing file.]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
