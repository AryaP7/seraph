#!/usr/bin/env python3
# C10 — do the three pillars carry non-redundant information? (MG-1, O7, FR35)
"""Two questions the subset ablation cannot answer on its own.

MG-1's premise is that Hawkes, RMT and Hamilton measure *distinct* phenomena —
contagion, structural coupling and regime persistence — so that fusing them
beats any one. The subset table in `CRISIS-REPLAY.md` shows fusion did not help,
but it cannot say which of two very different reasons applies:

* the pillars are **redundant**, so there was nothing to gain; or
* the pillars are **independent but uninformative**, so there was nothing to
  fuse.

These are measured separately here, on the standardised (FR28 rank) series each
pillar actually emits.

**A note on the crisis label.** An earlier pass applied FR32's
`[onset, onset+30]` window to the 468-element Hawkes-refit index. Hawkes refits
every 5 sessions, so "30 rows" there spans ~150 calendar trading days — a 5x
widened label that inflated every R^2 and reversed the ranking between pillars.
The label is therefore built on the **daily** grid and then projected onto
whichever subset is being evaluated. Every R^2 below is in-sample and unpenalised,
so an honest out-of-sample value is no larger.

Run:
  python scripts/analyse_pillar_redundancy.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "rcw", pathlib.Path(__file__).resolve().parent / "replay_crisis_warnings.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402

PILLARS = ["CSRS[hawkes]", "CSRS[rmt]", "CSRS[hamilton]"]


def short(n: str) -> str:
    return n.split("[")[1][:-1]


async def main() -> int:
    sig = await R.build_signals()
    series = {n: dict(zip(sig[n][0], sig[n][1])) for n in PILLARS}
    daily = sig["CSRS[rmt]"][0]

    flag = np.zeros(len(daily), dtype=bool)
    for onset, _ in EPOCH_BREAKS.values():
        at = [i for i, d in enumerate(daily) if d >= onset]
        if at:
            flag[at[0]:at[0] + CRISIS_WINDOW_DAYS] = True
    ylab = dict(zip(daily, flag.astype(float)))
    print(f"\n[red] FR32 label on the DAILY grid: {int(flag.sum())} crisis days "
          f"of {len(daily):,} ({100*flag.mean():.2f}%)")

    # ---- 1. redundancy -------------------------------------------------
    common = sorted(set.intersection(*[set(series[n]) for n in PILLARS]))
    M = np.array([[series[n][d] for n in PILLARS] for d in common])
    M = M[np.all(np.isfinite(M), axis=1)]
    print(f"\n=== 1. redundancy, on {M.shape[0]} days where all three exist ===")
    for lab, C in (("Pearson", np.corrcoef(M.T)),
                   ("Spearman", spearmanr(M).statistic)):
        print(f"\n{lab}:")
        print(f"{'':>11}" + "".join(f"{short(n):>11}" for n in PILLARS))
        for i, n in enumerate(PILLARS):
            print(f"{short(n):>11}" + "".join(f"{C[i,j]:>11.4f}"
                                              for j in range(len(PILLARS))))
    ew = M.mean(axis=1)
    indep = M.var(axis=0).sum() / len(PILLARS) ** 2
    print(f"\nvar(equal-weight mean)     = {ew.var():.6f}")
    print(f"var if fully independent   = {indep:.6f}")
    print(f"ratio (1.0 = independent)  = {ew.var()/indep:.4f}")
    print(f"effective independent pillars = {len(PILLARS)*indep/ew.var():.2f} "
          f"of {len(PILLARS)}")

    # ---- 2. incremental information ------------------------------------
    def run(cols: list[str], label: str) -> None:
        cm = sorted(set.intersection(*[set(series[n]) for n in cols]))
        X = np.array([[series[n][d] for n in cols] for d in cm])
        ok = np.all(np.isfinite(X), axis=1)
        X, cds = X[ok], [cm[i] for i in np.flatnonzero(ok)]
        y = np.array([ylab[d] for d in cds])
        print(f"\n=== {label}: {len(cds):,} days {cds[0]}..{cds[-1]}, "
              f"{int(y.sum())} crisis days ({100*y.mean():.2f}%) ===")

        def r2(Z: np.ndarray) -> float:
            A = np.column_stack([np.ones(len(Z))]
                                + [Z[:, k] for k in range(Z.shape[1])])
            b, *_ = np.linalg.lstsq(A, y, rcond=None)
            ss = ((y - y.mean()) ** 2).sum()
            return 1 - ((y - A @ b) ** 2).sum() / ss if ss > 0 else float("nan")

        full = r2(X)
        for k, n in enumerate(cols):
            print(f"  {n:<20} alone   R2={r2(X[:, [k]]):+.5f}")
        print(f"  {'ALL':<20}         R2={full:+.5f}")
        for k, n in enumerate(cols):
            rest = [j for j in range(len(cols)) if j != k]
            if rest:
                print(f"  drop {n:<16}  R2={r2(X[:, rest]):+.5f}  "
                      f"incremental {full - r2(X[:, rest]):+.5f}")

    print("\n=== 2. incremental information on the FR32 crisis label ===")
    run(PILLARS, "all three (Hawkes-refit days only)")
    run(["CSRS[rmt]", "CSRS[hamilton]"], "RMT+Hamilton (daily, 2013-01-14+)")
    run(["CSRS[rmt]"], "RMT alone (daily, full 2005+ span)")
    print("\nAll R2 values are IN-SAMPLE and unpenalised; out-of-sample values")
    print("are no larger. The label is contemporaneous, so this measures")
    print("detection information, not advance warning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
