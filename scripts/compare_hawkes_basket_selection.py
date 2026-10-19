#!/usr/bin/env python3
# C5 — Hawkes Engine (FR10–FR15): measure audit finding R11 on the real corpus.
"""How much did terminal-basket selection actually change the Hawkes input?

T05 asserts the pre-correction writer pooled every historical window over the
basket in force at the *end* of the corpus. This script measures the size of
that error against the real corpus instead of reasoning about it:

* for each refit point it pools the window twice — once over the terminal
  basket (what the old writer did) and once over the basket in force at that
  window's cutoff (what the corrected writer does) — and reports how far apart
  the two event streams are;
* on a bounded subset it fits both and reports the change in the branching
  ratio `n`, which is the number that reaches C8;
* it records which symbols the terminal basket adds to, or removes from, each
  historical window, so the direction of the error is visible per date.

Read-only. It writes nothing to the database.

Run:
  python scripts/compare_hawkes_basket_selection.py --window-days 500 \
      --refit-every 5 --fit-points 12 --out docs/evidence/T05-BASKET-2026-10-16.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.ingestion.hawkes_universe import BasketTimeline  # noqa: E402
from seraph.pillars.hawkes.basket_stream import (  # noqa: E402
    DETECTOR_VERSION,
    STREAM_VERSION,
    membership_segments,
)
from seraph.pillars.hawkes.engine import fit_discrete_hawkes  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from scripts.write_hawkes_production import (  # noqa: E402
    load_stream,
    refit_points,
    tod_profile,
)


async def main(window_days: int, refit_every: int, fit_points: int,
               out: str | None) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        rows = await pool.fetch(
            "SELECT rebalance_date, members FROM universe_snapshots "
            "ORDER BY rebalance_date")
        timeline = BasketTimeline.from_rows(rows)
        terminal = timeline.snapshots[-1]
        print(f"[compare] timeline {timeline.describe()}")

        t0 = time.time()
        stream = await load_stream(pool, timeline.union)
        print(f"[compare] stream: {len(stream.bars):,} bars, "
              f"{stream.n_sessions:,} sessions, "
              f"{stream.quality.symbols_used} symbols ({time.time()-t0:.0f}s)",
              flush=True)

        pts = refit_points(stream.day, stream.new_sess, window_days, refit_every)
        print(f"[compare] {len(pts)} refit points "
              f"{stream.day[pts[0][1]]} .. {stream.day[pts[-1][1]]}", flush=True)

        per_window = []
        for lo, hi in pts:
            cutoff = timeline.at(str(stream.day[hi]))
            correct_members = cutoff.basket if cutoff else ()
            new_inputs, new_manifest = stream.window(
                lo, hi, segments=[(lo, hi, tuple(correct_members))],
                policy="fixed_at_fit_cutoff", declared=correct_members,
                basket_id=cutoff.digest if cutoff else "",
                basket_basis="point_in_time",
                rebalance_date=cutoff.rebalance_date if cutoff else None)
            old_inputs, old_manifest = stream.window(
                lo, hi, segments=[(lo, hi, tuple(terminal.basket))],
                policy="fixed_at_fit_cutoff", declared=terminal.basket,
                basket_id=terminal.digest, basket_basis="point_in_time",
                rebalance_date=terminal.rebalance_date)

            added = sorted(set(terminal.basket) - set(correct_members))
            removed = sorted(set(correct_members) - set(terminal.basket))
            added_with_data = [s for s in added
                               if s in stream.series
                               and stream.series[s].bars_in(lo, hi)]
            removed_with_data = [s for s in removed
                                 if s in stream.series
                                 and stream.series[s].bars_in(lo, hi)]
            per_window.append(dict(
                as_of=new_manifest.as_of,
                training_start=new_manifest.training_start,
                correct_contributors=new_manifest.members_contributing,
                terminal_contributors=old_manifest.members_contributing,
                correct_neg=new_manifest.n_neg, terminal_neg=old_manifest.n_neg,
                correct_pos=new_manifest.n_pos, terminal_pos=old_manifest.n_pos,
                bars_differing=int((new_inputs["n_neg"]
                                    != old_inputs["n_neg"]).sum()),
                n_bars=new_manifest.n_bars,
                symbols_wrongly_included=len(added_with_data),
                symbols_wrongly_excluded=len(removed_with_data),
                event_hash_equal=(new_manifest.event_hash
                                  == old_manifest.event_hash),
            ))

        differing = [w for w in per_window if not w["event_hash_equal"]]
        contrib_ratio = np.array([w["terminal_contributors"]
                                  / max(w["correct_contributors"], 1)
                                  for w in per_window])
        neg_ratio = np.array([w["terminal_neg"] / max(w["correct_neg"], 1)
                              for w in per_window])
        print(f"\n[compare] windows whose pooled counts differ: "
              f"{len(differing)}/{len(per_window)}")
        print(f"[compare] terminal/correct contributors: "
              f"mean={contrib_ratio.mean():.3f} max={contrib_ratio.max():.3f}")
        print(f"[compare] terminal/correct negative events: "
              f"mean={neg_ratio.mean():.3f} max={neg_ratio.max():.3f}")

        # ---------------------------------------------------- bounded refits
        chosen = ([] if fit_points <= 0 else
                  [pts[i] for i in np.linspace(0, len(pts) - 1, fit_points,
                                               dtype=int)])
        fits = []
        for k, (lo, hi) in enumerate(chosen, 1):
            cutoff = timeline.at(str(stream.day[hi]))
            members = cutoff.basket if cutoff else ()
            row = dict(as_of=str(stream.day[hi]))
            for label, basket in (("correct", members),
                                  ("terminal", terminal.basket)):
                inputs, manifest = stream.window(
                    lo, hi, segments=[(lo, hi, tuple(basket))],
                    policy="fixed_at_fit_cutoff", declared=basket,
                    basket_id="", basket_basis="point_in_time",
                    rebalance_date=None)
                counts = inputs["n_neg"]
                prof = tod_profile(counts, inputs["tod_index"],
                                   inputs["n_slots"])
                fit = fit_discrete_hawkes(counts, inputs["session_starts"],
                                          prof, inputs["tod_index"])
                row[label] = (None if fit is None else dict(
                    n=float(fit.alpha / max(1.0 - fit.phi, 1e-12)),
                    mu=float(fit.mu), alpha=float(fit.alpha),
                    phi=float(fit.phi), converged=bool(fit.converged),
                    contributors=manifest.members_contributing,
                    n_neg=manifest.n_neg))
            if row.get("correct") and row.get("terminal"):
                row["delta_n"] = row["terminal"]["n"] - row["correct"]["n"]
            fits.append(row)
            print(f"  [compare] fit {k}/{len(chosen)} {row['as_of']}: "
                  f"delta_n={row.get('delta_n')}", flush=True)

        deltas = [f["delta_n"] for f in fits if f.get("delta_n") is not None]
        summary = dict(
            generated="T05 / audit finding R11",
            detector_version=DETECTOR_VERSION, stream_version=STREAM_VERSION,
            window_days=window_days, refit_every=refit_every,
            refit_points=len(pts),
            timeline=timeline.describe(),
            stream_quality=stream.quality.describe(),
            windows_with_differing_counts=len(differing),
            windows_total=len(per_window),
            contributor_ratio=dict(mean=float(contrib_ratio.mean()),
                                   min=float(contrib_ratio.min()),
                                   max=float(contrib_ratio.max())),
            negative_event_ratio=dict(mean=float(neg_ratio.mean()),
                                      min=float(neg_ratio.min()),
                                      max=float(neg_ratio.max())),
            branching_ratio_delta=(dict(
                fitted_points=len(deltas), mean=float(np.mean(deltas)),
                min=float(np.min(deltas)), max=float(np.max(deltas)),
                max_abs=float(np.max(np.abs(deltas)))) if deltas else None),
            fits=fits,
            per_window=per_window,
            qualification=(
                "This measures an input defect and its effect on the fitted "
                "branching ratio. It is not evidence that either version "
                "predicts anything."),
        )
        if deltas:
            print(f"\n[compare] delta n over {len(deltas)} fitted points: "
                  f"mean={np.mean(deltas):+.5f} "
                  f"range=[{np.min(deltas):+.5f}, {np.max(deltas):+.5f}]")
        if out:
            Path(out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(f"[compare] wrote {out}")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, required=True)
    ap.add_argument("--refit-every", type=int, default=5)
    ap.add_argument("--fit-points", type=int, default=12,
                    help="how many refit points to actually fit under both "
                         "selections (0 to compare inputs only)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.window_days, a.refit_every,
                                      a.fit_points, a.out)))
