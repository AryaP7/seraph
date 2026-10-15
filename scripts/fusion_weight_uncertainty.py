#!/usr/bin/env python3
# C9/C10 — how uncertain are the learned fusion weights? (FR30, O5)
"""Fold-to-fold instability says the weights *move*. This says how little they
are pinned down at all.

`FUSION-ARCHITECTURE.md` §2 reports a maximum pairwise L1 distance of 1.7–1.9
between per-fold weight vectors, against a simplex maximum of 2.0. That is a
statement about three point estimates. It does not say how wide the uncertainty
on any *one* of them is, and a deliverable that reports learned weights without
that is reporting a number as if it were a measurement.

**Method: block bootstrap on the training period, then refit.** Resampling
individual days would be wrong — Workstream B measured the integral timescale of
the pillar features at **770 sessions**, so daily resampling would treat ~5,000
dependent observations as independent and produce absurdly tight intervals. The
resample is therefore over contiguous **blocks**, at several block lengths
including the measured scale, and the spread is reported per length so the
dependence assumption is visible rather than buried.

Each replicate re-runs the same simplex grid search the main experiment uses, so
the output is the sampling distribution of exactly the estimator being reported.

**What a wide interval means here.** If the 90% interval for a pillar's weight
spans most of [0, 1], then the "learned weight" is not an estimate of anything —
and reporting it to two decimals in a production artefact would be false
precision. That is the question this script answers.

Run:
  python scripts/fusion_weight_uncertainty.py --reps 200
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_spec = importlib.util.spec_from_file_location(
    "fas", Path(__file__).resolve().parent / "fusion_architecture_search.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

#: block lengths in trading days. 770 is the measured integral timescale of
#: `rv_t_yz` (EVENT-COUNT-LIMITATION.md); the shorter ones show how much the
#: interval depends on that assumption.
BLOCKS = (21, 63, 252, 770)
PILLARS = ("hawkes", "rmt", "hamilton")


def block_resample(idx: np.ndarray, L: int, rng) -> np.ndarray:
    """Circular moving-block bootstrap over the training indices."""
    if idx.size == 0:
        return idx
    n_blocks = int(np.ceil(idx.size / L))
    starts = rng.integers(0, idx.size, size=n_blocks)
    take = np.concatenate([(np.arange(s, s + L) % idx.size) for s in starts])
    return idx[take[:idx.size]]


async def main(reps: int, pillar2: str, out_dir: str) -> int:
    dates, X, M = await F.reconciled_state(pillar2)
    y, crisis, onset_at = F.labels(dates)
    n = len(dates)
    assess = ~crisis

    # the widest development training period: everything before the first
    # confirmation onset, which is the fold with the most events available
    first_conf = min(onset_at[e] for e in F.CONFIRM_EPOCHS if e in onset_at)
    train = np.zeros(n, dtype=bool)
    train[:max(0, first_conf - F.PRE)] = True
    train &= assess
    idx = np.flatnonzero(train)

    w_hat, a_hat = F.learn_convex(X, M, y, train, shrink=0.0)
    print(f"\n[unc] pillar 2 = {pillar2}")
    print(f"[unc] training period: {idx.size:,} days {dates[idx[0]]} .. "
          f"{dates[idx[-1]]}, {int((y & train).sum())} positives "
          f"({int((y & train).sum()) // F.PRE} events)")
    print(f"[unc] point estimate: " + ", ".join(
        f"{p}={w_hat[i]:.3f}" for i, p in enumerate(PILLARS))
        + f"  (train AUC {a_hat:.4f})")
    print(f"[unc] {reps} block-bootstrap replicates per block length\n",
          flush=True)

    report = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pillar2_quantity": pillar2, "reps": reps,
        "training_days": int(idx.size),
        "training_positives": int((y & train).sum()),
        "point_estimate": {p: round(float(w_hat[i]), 4)
                           for i, p in enumerate(PILLARS)},
        "point_train_auc": round(float(a_hat), 4),
        "by_block_length": {},
    }

    hdr = (f"{'block L':>8}" + "".join(f"{p+' 5%':>12}{p+' 95%':>12}"
                                       for p in PILLARS) + f"{'mean width':>12}")
    print(hdr); print("-" * len(hdr))
    for L in BLOCKS:
        rng = np.random.default_rng(20261014 + L)
        W = []
        for _ in range(reps):
            samp = block_resample(idx, L, rng)
            tr = np.zeros(n, dtype=bool)
            tr[samp] = True                   # a resampled training mask
            if int((y & tr).sum()) < 5:
                continue
            w, _ = F.learn_convex(X, M, y, tr, shrink=0.0)
            W.append(w)
        if len(W) < 20:
            print(f"{L:>8}  too few usable replicates ({len(W)})")
            continue
        W = np.asarray(W)
        lo = np.quantile(W, 0.05, axis=0)
        hi = np.quantile(W, 0.95, axis=0)
        width = float(np.mean(hi - lo))
        report["by_block_length"][str(L)] = {
            "replicates": len(W),
            "q05": [round(float(x), 4) for x in lo],
            "q50": [round(float(x), 4) for x in np.quantile(W, 0.50, axis=0)],
            "q95": [round(float(x), 4) for x in hi],
            "mean_interval_width": round(width, 4),
            "frac_replicates_at_a_corner": round(float(
                np.mean(W.max(axis=1) > 0.95)), 4),
        }
        row = f"{L:>8}"
        for i in range(3):
            row += f"{lo[i]:>12.3f}{hi[i]:>12.3f}"
        row += f"{width:>12.3f}"
        print(row, flush=True)

    print(f"\nEach pair is the 90% block-bootstrap interval for that pillar's")
    print(f"learned weight. The simplex constrains weights to [0,1] summing to")
    print(f"1, so an interval spanning most of [0,1] means the weight is not an")
    print(f"estimate of anything and two-decimal reporting would be false")
    print(f"precision. L=770 is the measured integral timescale; shorter")
    print(f"lengths understate dependence and so understate the width.")

    fc = report["by_block_length"].get("770", {}).get(
        "frac_replicates_at_a_corner")
    if fc is not None:
        print(f"\n[unc] at L=770, {100*fc:.0f}% of replicates put >0.95 of the")
        print(f"[unc] weight on a SINGLE pillar - the grid search is choosing a")
        print(f"[unc] corner of the simplex, i.e. discarding fusion entirely.")

    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    jp = out / f"weight_uncertainty_{pillar2}.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[unc] wrote {jp}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--pillar2", choices=("lam1", "sca"), default="lam1")
    ap.add_argument("--out", default="docs/evidence/fusion")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.reps, a.pillar2, a.out)))
