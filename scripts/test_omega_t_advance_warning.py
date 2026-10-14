#!/usr/bin/env python3
# C10/C6 — does Omega_t's advance-warning AUC survive a calibrated null? (FR17)
"""`Omega_t` is the one loose end the Pillar 2 investigation created.

`diagnose_pillar2_quantity_auc.py` found the leading-eigenvector rotation speed
has the highest figures of any Pillar 2 statistic measured — T1 AUC **0.7354**
and T3 (15-day pre-onset) **0.5934** — both well above `lambda_1/N`'s 0.4282 and
0.4340, and above the FR18 aggregate `SCA_t`'s 0.6623 and 0.5324. Leaving a
0.5934 reported without a null would be exactly the kind of unqualified number
this project has spent the session removing, so it is tested here.

**The selection problem, stated plainly.** `Omega_t` was picked as the best of
five Pillar 2 statistics *after* seeing their T1 AUCs. The T3 statistic tested
here is a different quantity from the one selection used, which weakens but does
not remove the circularity: a statistic chosen for detecting crises is more
likely than a random pick to also lead them. **So this is exploratory**, the
multiplicity is reported as 5 (the candidate set it was chosen from) rather than
1, and the threshold is Bonferroni 0.05/5 = 0.01 on top of the two-null
requirement.

**Two nulls, both required.** Reusing `early_warning_power.py` unchanged:

* `relocation_null` — circular common-offset shift of the six onsets, preserving
  spacing. Measured type-I error 8% at a nominal 5%.
* `aaft_null` — onsets fixed, series phase-randomised with its exact marginal
  preserved. Answers "could a series with this autocorrelation and this
  distribution score this well on these dates".

A pre-registered rule, fixed before the run: `Omega_t`'s T3 lead is treated as
real only if `p <= 0.01` under **both** families. Anything else is reported as
not established.

**In-crisis days are dropped**, so a crisis reading cannot be scored as a
warning.

Run:
  python scripts/test_omega_t_advance_warning.py --perms 2000
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402

from seraph.orchestration import lam1_share  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "ewp", Path(__file__).resolve().parent / "early_warning_power.py")
EWP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(EWP)

#: candidate set Omega_t was selected from, for the multiplicity correction
N_CANDIDATES = 5
ALPHA = 0.05 / N_CANDIDATES


async def main(perms: int, seed: int) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        rows = await pool.fetch(
            "SELECT date, eigenvalues, f_t, v_eig_t, omega_t, sca_t "
            "FROM rmt_output ORDER BY date")
    finally:
        await pool.close()

    d = [str(r["date"]) for r in rows]
    n = len(d)
    breaks = []
    for onset, _ in EPOCH_BREAKS.values():
        at = [i for i, x in enumerate(d) if x >= onset]
        if at:
            breaks.append(at[0])
    breaks = sorted(breaks)

    def col(name):
        return np.array([r[name] if r[name] is not None else np.nan
                         for r in rows], dtype=float)

    cands = {
        "Omega_t": col("omega_t"),
        "SCA_t": col("sca_t"),
        "V_t^eig": col("v_eig_t"),
        "F_t": col("f_t"),
        "lambda1/N": np.array([lam1_share(list(r["eigenvalues"] or [])) or np.nan
                               for r in rows]),
    }

    print(f"\n[omega] grid {n:,} days {d[0]} .. {d[-1]}, {len(breaks)} onsets")
    print(f"[omega] multiplicity treated as {N_CANDIDATES} (the set Omega_t was "
          f"chosen from), so the threshold is Bonferroni {ALPHA:.3f}")
    print(f"[omega] rule fixed before the run: real only if p <= {ALPHA:.3f} "
          f"under BOTH nulls")
    print(f"[omega] {perms} permutations -> resolution floor "
          f"{1/(perms+1):.5f}\n", flush=True)

    rng = np.random.default_rng(seed)
    hdr = (f"{'statistic':<14}{'T3 AUC':>9}{'p_shift':>10}{'p_aaft':>10}"
           f"{'null p95':>10}  verdict")
    print(hdr); print("-" * (len(hdr) + 10))
    for name, v in cands.items():
        # NaNs break the surrogate machinery; interpolate only INTERIOR gaps and
        # report how many, so a heavily-gapped series cannot pass silently.
        bad = ~np.isfinite(v)
        if bad.all():
            print(f"{name:<14}  all-NaN, skipped"); continue
        if bad.any():
            idx = np.arange(n)
            v = np.interp(idx, idx[~bad], v[~bad])
        obs = EWP.t3_auc(v, breaks, n)
        shift = EWP.relocation_null(v, n, breaks, perms, rng)
        aaft = EWP.aaft_null(v, n, breaks, perms, rng)
        shift = np.asarray(shift, dtype=float)
        aaft = np.asarray(aaft, dtype=float)
        p_s = float((np.sum(shift >= obs) + 1) / (shift.size + 1))
        p_a = float((np.sum(aaft >= obs) + 1) / (aaft.size + 1))
        p95 = float(np.quantile(np.concatenate([shift, aaft]), 0.95))
        ok = (p_s <= ALPHA) and (p_a <= ALPHA)
        print(f"{name:<14}{obs:>9.4f}{p_s:>10.4f}{p_a:>10.4f}{p95:>10.4f}  "
              f"{'SURVIVES BOTH' if ok else 'not established'}"
              f"{f'  ({int(bad.sum())} gaps filled)' if bad.any() else ''}")

    print(f"\nT3 = 15-day pre-onset AUC with in-crisis days dropped.")
    print(f"null p95 = 95th percentile of the pooled null; an observed value")
    print(f"below it cannot be distinguished from no signal at all.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261014)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.perms, a.seed)))
