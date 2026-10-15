#!/usr/bin/env python3
# C10/C6 — does the FR28 rank transform destroy pillar signal? (FR28, NFR17)
"""Why does RMT explain R^2 = 0.00001 of the crisis label?

Two very different causes, and the remedy differs completely:

* **(a) the pillar does not move in crises** — then the input is the problem and
  no transform or fusion rule can help; or
* **(b) the pillar moves but the pipeline flattens it** — then FR28's rolling
  rank is destroying signal, which is an architectural defect and fixable.

Distinguishing them needs the raw and standardised series compared on the *same*
windows. Measured here for each pillar:

* crisis-vs-tranquil mean separation in sigma, on the RAW value and on the
  STANDARDISED rank, using FR32's `[onset, onset+30]` window;
* the same for the 15-day PRE-onset window, which is the advance-warning
  question rather than the detection one;
* rank-correlation between raw and standardised, which bounds how much the
  transform can have destroyed.

**Interpretation guard.** A rolling rank is *designed* to attenuate: it measures
a value against its own recent history, so a slow regime shift becomes a smaller
rank move than the raw move. That is adaptivity, not a bug. The test is whether
attenuation is so severe that a large raw separation becomes a negligible rank
separation — and whether the two even point the same way.

Run:
  python scripts/diagnose_pillar_signal_loss.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "rcw", pathlib.Path(__file__).resolve().parent / "replay_crisis_warnings.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

from seraph.orchestration import lam1_share  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402

PRE_WINDOW = 15


def sep(x: np.ndarray, m: np.ndarray) -> tuple[float, float, float]:
    """(separation in sigma, mean inside, mean outside) for boolean mask `m`."""
    a, b = x[m & np.isfinite(x)], x[~m & np.isfinite(x)]
    if a.size < 5 or b.size < 5:
        return float("nan"), float("nan"), float("nan")
    sd = float(b.std(ddof=1))
    if sd <= 0:
        return float("nan"), float(a.mean()), float(b.mean())
    return float((a.mean() - b.mean()) / sd), float(a.mean()), float(b.mean())


async def raw_series() -> dict[str, dict[str, float]]:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        rmt = await pool.fetch("SELECT date, eigenvalues FROM rmt_output ORDER BY date")
        hwk = await pool.fetch("SELECT ts, branching_ratio_n FROM hawkes_output "
                               "WHERE scope='market' ORDER BY ts")
    finally:
        await pool.close()
    out: dict[str, dict[str, float]] = {"rmt": {}, "hawkes": {}, "hamilton": {}}
    for r in rmt:
        s = lam1_share(list(r["eigenvalues"] or []))
        if s is not None:
            out["rmt"][str(r["date"])] = float(s)
    for r in hwk:
        n = float(r["branching_ratio_n"])
        out["hawkes"][str(r["ts"].date())] = n / (1.0 - n)
    ham = R.load_hamilton_causal()
    for d, (lsd, _v) in ham.items():
        out["hamilton"][d] = float(lsd)
    return out


async def main() -> int:
    sig = await R.build_signals()
    raw = await raw_series()
    daily = sig["CSRS[rmt]"][0]

    crisis = np.zeros(len(daily), dtype=bool)
    pre = np.zeros(len(daily), dtype=bool)
    for onset, _ in EPOCH_BREAKS.values():
        at = [i for i, d in enumerate(daily) if d >= onset]
        if not at:
            continue
        s0 = at[0]
        crisis[s0:min(len(daily), s0 + CRISIS_WINDOW_DAYS)] = True
        pre[max(0, s0 - PRE_WINDOW):s0] = True
    print(f"\n[loss] FR32 crisis window : {int(crisis.sum())} days")
    print(f"[loss] 15-day PRE-onset   : {int(pre.sum())} days")
    print(f"[loss] raw units differ per pillar; separation is in sigma of the")
    print(f"[loss] NON-crisis distribution, so the two scales are comparable.\n")

    hdr = (f"{'pillar':<10}{'n':>6}" + f"{'RAW crisis':>13}{'STD crisis':>13}"
           + f"{'RAW pre':>11}{'STD pre':>11}{'rho(raw,std)':>14}")
    print(hdr); print("-" * len(hdr))
    for name, key in (("hawkes", "CSRS[hawkes]"), ("rmt", "CSRS[rmt]"),
                      ("hamilton", "CSRS[hamilton]")):
        d, v, _ = sig[key]
        std = dict(zip(d, v))
        common = [x for x in daily if x in raw[name] and x in std
                  and np.isfinite(std[x])]
        if len(common) < 50:
            print(f"{name:<10}{len(common):>6}  insufficient overlap")
            continue
        idx = {x: i for i, x in enumerate(daily)}
        rv = np.array([raw[name][x] for x in common])
        sv = np.array([std[x] for x in common])
        cm = np.array([crisis[idx[x]] for x in common])
        pm = np.array([pre[idx[x]] for x in common])
        from scipy.stats import spearmanr
        rho = float(spearmanr(rv, sv).statistic)
        rc, _, _ = sep(rv, cm); sc, _, _ = sep(sv, cm)
        rp, _, _ = sep(rv, pm); sp, _, _ = sep(sv, pm)
        print(f"{name:<10}{len(common):>6}{rc:>13.4f}{sc:>13.4f}"
              f"{rp:>11.4f}{sp:>11.4f}{rho:>14.4f}")

    print("\nRAW/STD crisis = crisis-vs-tranquil separation in sigma.")
    print("RAW/STD pre    = the same on the 15-day PRE-onset window.")
    print("rho            = Spearman(raw, standardised); 1.0 would mean the")
    print("                 transform is exactly monotone over the whole span")
    print("                 and destroys no ordering information at all.")
    print("\nA pillar with a large RAW crisis separation and a negligible STD one")
    print("would indicate cause (b), the transform flattening signal. A pillar")
    print("small on BOTH indicates cause (a), the input carrying little.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
