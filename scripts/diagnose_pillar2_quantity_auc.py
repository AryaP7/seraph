#!/usr/bin/env python3
# C10/C6 — which Pillar 2 quantity actually detects crises? (FR17, FR18)
"""Does `SCA_t` improve T1 detection AUC, or only mean separation?

Gate 4 in `CRISIS-REPLAY.md` recommends switching Pillar 2 from `λ₁/N` to
`SCA_t` partly on detection value. The evidence offered there was a separation of
means (+0.50σ versus −0.38σ), and separation is not AUC — a shifted mean with a
fatter tail can separate without ranking better. So the AUC is measured directly
rather than inferred.

Three cautions on reading the table:

* **`Ω_t`'s figure is a best-of-five, selected after seeing the data**, and
  carries no null here. It must not be reported as a validated result. What *is*
  robust is the comparison it enables: the equal-weight FR18 aggregate scores
  *below* one of its own three components, which is a property of the
  aggregation rule rather than a selected winner.
* **T3 drops in-crisis days**, so a crisis reading cannot be scored as a
  warning.
* AUC is rank-based, so FR28's monotone rank transform leaves every value
  unchanged. These are the pillars' own skill, not an artefact of
  standardisation.

Run:
  python scripts/diagnose_pillar2_quantity_auc.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from seraph.orchestration import lam1_share  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402

PRE_WINDOW = 15


def auc(score: np.ndarray, y: np.ndarray) -> float:
    """Mann-Whitney AUC, ties handled by average rank."""
    m = np.isfinite(score)
    sc, yy = score[m], y[m]
    if yy.sum() == 0 or (~yy).sum() == 0:
        return float("nan")
    order = np.argsort(sc, kind="mergesort")
    ranks = np.empty(sc.size, dtype=float)
    ranks[order] = np.arange(1, sc.size + 1, dtype=float)
    # average ranks within tie groups, or a discrete statistic is biased
    srt = sc[order]
    i = 0
    while i < srt.size:
        j = i
        while j + 1 < srt.size and srt[j + 1] == srt[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    n1, n0 = float(yy.sum()), float((~yy).sum())
    return float((ranks[yy].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


async def main() -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        rows = await pool.fetch(
            "SELECT date, eigenvalues, f_t, v_eig_t, omega_t, sca_t "
            "FROM rmt_output ORDER BY date")
    finally:
        await pool.close()

    d = [str(r["date"]) for r in rows]
    n = len(d)
    y = np.zeros(n, dtype=bool)
    pre = np.zeros(n, dtype=bool)
    for onset, _ in EPOCH_BREAKS.values():
        at = [i for i, x in enumerate(d) if x >= onset]
        if not at:
            continue
        s0 = at[0]
        y[s0:min(n, s0 + CRISIS_WINDOW_DAYS)] = True
        pre[max(0, s0 - PRE_WINDOW):s0] = True
    keep3 = ~y                      # disjoint: a crisis day cannot be a warning

    print(f"\n[p2] T1 label: {int(y.sum())} crisis days of {n:,}")
    print(f"[p2] T3 label: {int(pre.sum())} pre-onset days, "
          f"{int(y.sum())} in-crisis days dropped\n")

    def col(name: str) -> np.ndarray:
        return np.array([r[name] if r[name] is not None else np.nan
                         for r in rows], dtype=float)

    series = {
        "lambda1/N  (USED)": np.array(
            [lam1_share(list(r["eigenvalues"] or [])) or np.nan for r in rows]),
        "F_t (FR17)": col("f_t"),
        "V_t^eig (FR17)": col("v_eig_t"),
        "Omega_t (FR17)": col("omega_t"),
        "SCA_t (FR18 SPEC)": col("sca_t"),
    }

    print(f"{'statistic':<22}{'T1 AUC':>9}{'T3 AUC':>9}")
    print("-" * 40)
    for k, v in series.items():
        print(f"{k:<22}{auc(v, y):>9.4f}{auc(v[keep3], pre[keep3]):>9.4f}")

    print("\nT1 = contemporaneous crisis detection; T3 = 15-day pre-onset.")
    print("0.50 is chance. Values materially BELOW 0.50 are anti-predictive.")
    print("Omega_t is a best-of-five with no null attached — see the module")
    print("docstring. The reportable comparison is aggregate vs component.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
