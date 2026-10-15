#!/usr/bin/env python3
# C10 — calibrated no-signal benchmark for the unified replay (FR32, O5).
"""Is a replay's pre-onset warning record better than a signal with no skill?

`replay_crisis_warnings.py` answers "did it warn before the onset" per epoch.
That number is uninterpretable on its own, and the reason is arithmetic rather
than philosophical: a signal that alerts on 30% of all days warns before almost
any date you nominate. Reporting "warned before 5 of 6 crises" for such a signal
would be true and worthless.

**The null therefore relocates the events, not the series.** The six onsets are
circularly shifted along the trading-day index by a common offset, which
preserves their exact spacing, and the statistic is recomputed. The alternative
nulls were tested and rejected in `early_warning_power.py`:

* drawing onsets uniformly at random rejected at **50%** against a nominal 5%,
  because near-random-walk features make the statistic depend on where in the
  sample you look;
* an AR(1) surrogate started at `x[0] = 0` rejected at 40%/17%, because it is
  non-stationary for ~1/(1-phi) ~ 370 steps while four of six real onsets sit
  late in the sample.

The common-offset circular shift measured an actual type-I error of **8% at a
nominal 5%**, which is the calibration this script inherits. Offsets landing
within `MIN_SEPARATION` days of any real onset are discarded, so the null cannot
be contaminated by the episodes it is meant to be a null for.

Two statistics, both pre-registered here before any result was inspected:

1. **`n_warned`** — how many testable epochs show a rising edge inside
   `[onset-h, onset-1]`. Integer, so its null is coarse and its p-values are
   step-shaped; that is a property of six events, not a defect.
2. **`mean_lead`** — mean lead time over the epochs that warned. Reported
   because a signal can warn everywhere with a 1-day lead, which is detection
   wearing a warning's clothes.

A p-value is only meaningful above the permutation-resolution floor
`1/(n_draws+1)`, which is printed.

Run:
  python scripts/replay_warning_null.py --horizon 15 --draws 2000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

import replay_crisis_warnings as R  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402

#: an offset is discarded if any shifted onset lands this close to a real one
MIN_SEPARATION = CRISIS_WINDOW_DAYS + 15


def onset_indices(dates: list[str], onsets: list[str]) -> list[int]:
    """Index of the last trading day strictly before each onset, or -1."""
    out = []
    for o in onsets:
        pre = [i for i, d in enumerate(dates) if d < o]
        out.append(pre[-1] if pre else -1)
    return out


def statistic(flags: np.ndarray, vals: np.ndarray, ks: list[int], *,
              horizon: int, assessable: np.ndarray) -> tuple[int, int, float]:
    """(n_warned, n_testable, mean_lead) for a set of pre-onset indices `ks`.

    An epoch is testable when its pre-onset window holds at least a third of
    the requested days with BOTH a finite value and a computable threshold —
    the same rule `assess_epoch` uses, so the null and the observed statistic
    are computed identically. Requiring the threshold matters: Hawkes refits
    every 5 sessions, so its trailing 5-year window holds fewer than the
    250-observation floor for most of its own span, and a relocated onset
    landing there must count as untestable rather than as a miss.
    """
    warned, testable, leads = 0, 0, []
    for k in ks:
        if k < 0:
            continue
        lo = max(0, k - horizon + 1)
        win = range(lo, k + 1)
        if sum(1 for i in win
               if np.isfinite(vals[i]) and assessable[i]) < max(3, horizon // 3):
            continue
        testable += 1
        edges = [i for i in win if flags[i] and (i == 0 or not flags[i - 1])]
        if edges:
            warned += 1
            leads.append(k - edges[0] + 1)
    return warned, testable, (float(np.mean(leads)) if leads else float("nan"))


def relocation_null(dates: list[str], flags: np.ndarray, vals: np.ndarray,
                    real_ks: list[int], *, horizon: int, draws: int,
                    assessable: np.ndarray, seed: int = 20261013) -> dict:
    n = len(dates)
    real = [k for k in real_ks if k >= 0]
    if not real:
        return {"error": "no real onset inside the signal's span"}
    obs_w, obs_t, obs_l = statistic(flags, vals, real_ks, horizon=horizon,
                                    assessable=assessable)

    rng = np.random.default_rng(seed)
    # candidate offsets: every shift, then thinned to `draws` at random so the
    # null is not an arithmetic lattice aligned with the onset spacing
    all_off = np.arange(1, n)
    ok = []
    for off in all_off:
        shifted = [(k + int(off)) % n for k in real]
        if min(abs(s - r) for s in shifted for r in real) < MIN_SEPARATION:
            continue
        ok.append(int(off))
    if len(ok) > draws:
        ok = sorted(rng.choice(ok, size=draws, replace=False).tolist())

    nw, nl = [], []
    for off in ok:
        shifted = [(k + off) % n for k in real]
        w, t, l = statistic(flags, vals, shifted, horizon=horizon,
                            assessable=assessable)
        if t == 0:
            continue
        nw.append(w / t)          # rate, so differing testability is comparable
        if np.isfinite(l):
            nl.append(l)
    nw = np.asarray(nw, dtype=float)
    nl = np.asarray(nl, dtype=float)
    obs_rate = (obs_w / obs_t) if obs_t else float("nan")

    res = {
        "horizon_days": horizon,
        "observed": {"n_warned": obs_w, "n_testable": obs_t,
                     "rate": round(obs_rate, 4) if obs_t else None,
                     "mean_lead_days": (round(obs_l, 2)
                                        if np.isfinite(obs_l) else None)},
        "null_draws_used": int(nw.size),
        "resolution_floor": round(1.0 / (nw.size + 1), 5) if nw.size else None,
    }
    if nw.size and obs_t:
        res["null_rate"] = {
            "mean": round(float(nw.mean()), 4),
            "sd": round(float(nw.std()), 4),
            "p50": round(float(np.quantile(nw, 0.50)), 4),
            "p95": round(float(np.quantile(nw, 0.95)), 4),
        }
        # one-sided: how often does a skill-free relocation do at least as well
        res["p_rate"] = round(float((np.sum(nw >= obs_rate) + 1)
                                    / (nw.size + 1)), 5)
        res["observed_vs_null_sd"] = (
            round(float((obs_rate - nw.mean()) / nw.std()), 3)
            if nw.std() > 0 else None)
    if nl.size and np.isfinite(obs_l):
        res["null_mean_lead"] = {
            "mean": round(float(nl.mean()), 3),
            "sd": round(float(nl.std()), 3),
            "p95": round(float(np.quantile(nl, 0.95)), 3),
        }
        # LONGER lead is the alternative, so the tail is the upper one
        res["p_mean_lead"] = round(float((np.sum(nl >= obs_l) + 1)
                                         / (nl.size + 1)), 5)
    return res


def holm(pairs: list[tuple[str, float]]) -> dict[str, dict]:
    """Holm step-down over every comparison reported, alpha = 0.05."""
    m = len(pairs)
    order = sorted(pairs, key=lambda x: x[1])
    out, blocked = {}, False
    for rank, (name, p) in enumerate(order):
        thr = 0.05 / (m - rank)
        rej = (p <= thr) and not blocked
        if not rej:
            blocked = True
        out[name] = {"p": p, "holm_threshold": round(thr, 6),
                     "survives_holm": bool(rej)}
    return out


async def main(horizon: int, draws: int, out_dir: str,
               pillar2: str = "lam1") -> int:
    signals = await R.build_signals(pillar2)
    onsets = [EPOCH_BREAKS[e][0] for e in EPOCH_BREAKS]

    print(f"[null] horizon {horizon}d, up to {draws} relocation draws, "
          f"min separation {MIN_SEPARATION}d from any real onset")
    print(f"[null] statistic 1: warned-rate over testable epochs")
    print(f"[null] statistic 2: mean lead over epochs that warned\n", flush=True)

    report: dict = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizon_days": horizon, "draws_requested": draws,
        "pillar2_quantity": pillar2,
        "min_separation_days": MIN_SEPARATION,
        "null": "common-offset circular relocation of the six onsets",
        "calibration": ("actual type-I 8% at nominal 5% "
                        "(docs/evidence/EARLY-WARNING-POWER.md)"),
        "signals": {},
    }
    hdr = (f"{'signal':<24}{'warned':>9}{'rate':>7}{'null':>14}"
           f"{'p_rate':>8}{'lead':>7}{'p_lead':>8}")
    print(hdr); print("-" * len(hdr))
    for sig, (d, v, _meta) in signals.items():
        fb, ok_b = R.causal_quantile_flags(d, v, with_assessable=True)
        ks = onset_indices(d, onsets)
        res = relocation_null(d, fb, v, ks, horizon=horizon, draws=draws,
                              assessable=ok_b)
        report["signals"][sig] = res
        if "p_rate" not in res:
            print(f"{sig:<24}{'(no testable onset)':>50}")
            continue
        o = res["observed"]; nr = res["null_rate"]
        print(f"{sig:<24}{o['n_warned']}/{o['n_testable']:<7}"
              f"{o['rate']:>7.2f}{nr['mean']:>8.2f}+-{nr['sd']:<4.2f}"
              f"{res['p_rate']:>8.4f}"
              f"{(o['mean_lead_days'] or float('nan')):>7.1f}"
              f"{res.get('p_mean_lead', float('nan')):>8.4f}")

    pairs = [(s, r["p_rate"]) for s, r in report["signals"].items()
             if "p_rate" in r]
    report["holm_over_warned_rate"] = holm(pairs)
    report["n_comparisons"] = len(pairs)
    floor = next((r["resolution_floor"] for r in report["signals"].values()
                  if r.get("resolution_floor")), None)
    report["resolution_floor"] = floor

    print(f"\n[null] Holm over {len(pairs)} comparisons "
          f"(tightest threshold {0.05/len(pairs):.5f}); "
          f"permutation floor {floor}")
    if floor and floor > 0.05 / max(1, len(pairs)):
        print(f"[null] WARNING: the floor {floor} exceeds Holm's tightest "
              f"threshold {0.05/len(pairs):.5f} — no comparison can reach "
              f"significance at this draw count. Raise --draws.")
    for s, h in sorted(report["holm_over_warned_rate"].items(),
                       key=lambda x: x[1]["p"]):
        print(f"       {s:<24} p={h['p']:.4f} thr={h['holm_threshold']:.5f} "
              f"{'SURVIVES' if h['survives_holm'] else 'no'}")

    outp = Path(out_dir); outp.mkdir(parents=True, exist_ok=True)
    sfx = "" if pillar2 == "lam1" else f"_{pillar2}"
    jp = outp / f"warning_null_h{horizon}{sfx}.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[null] wrote {jp}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=15,
                    help="lead window in trading days (FR32 upper bound is 15)")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--out", default="docs/evidence/replay")
    ap.add_argument("--pillar2", choices=R.PILLAR2_MODES,
                    default="lam1",
                    help="Pillar 2 quantity: lam1 (shipped) or sca "
                         "(SPEC FR18). Research only.")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(
        main(a.horizon, a.draws, a.out, a.pillar2)))
