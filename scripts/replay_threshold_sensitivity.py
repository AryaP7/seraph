#!/usr/bin/env python3
# C10 — is the replay's negative result an artefact of the alert threshold?
"""Sweep Rule B's quantile and re-run the calibrated null at every level.

`CRISIS-REPLAY.md` reports 0/6 pre-onset warnings for the full three-pillar
system at a trailing-five-year 95th-percentile threshold. A strict threshold
mechanically produces few alerts, so that result is only meaningful if it
survives a looser one.

**This is a sensitivity analysis, not threshold selection.** Every level tested
is reported, no level is chosen as the headline, and the relocation null is
recomputed at each level — because loosening the threshold raises the no-skill
warned-rate too, and comparing a loosened observed rate against a strict null
would manufacture significance. The whole point is that the null moves with the
rule.

Run:
  python scripts/replay_threshold_sensitivity.py --horizon 15 --draws 600
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import sys
from datetime import UTC, datetime

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_here = pathlib.Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _here / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load("replay_crisis_warnings")
N = _load("replay_warning_null")

from seraph.validation.epochs import EPOCH_BREAKS  # noqa: E402

QUANTILES = (0.80, 0.85, 0.90, 0.95, 0.99)


async def main(horizon: int, draws: int, out_dir: str,
               pillar2: str = "lam1") -> int:
    signals = await R.build_signals(pillar2)
    onsets = [EPOCH_BREAKS[e][0] for e in EPOCH_BREAKS]

    print(f"\n[sens] horizon {horizon}d, {draws} relocation draws per cell")
    print(f"[sens] quantiles tested: {QUANTILES}")
    print(f"[sens] ALL levels reported; none is selected. The null is recomputed")
    print(f"[sens] at each level, because a looser rule also raises the no-skill")
    print(f"[sens] warned-rate.\n", flush=True)

    report = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizon_days": horizon, "draws": draws,
        "pillar2_quantity": pillar2,
        "quantiles": list(QUANTILES),
        "note": ("sensitivity analysis; no level selected as headline; null "
                 "recomputed per level"),
        "cells": {},
    }

    hdr = f"{'signal':<26}" + "".join(f" | {f'q={q:.2f}':^20}" for q in QUANTILES)
    print(hdr); print("-" * len(hdr))
    for sig, (d, v, _m) in signals.items():
        row = f"{sig:<26}"
        report["cells"][sig] = {}
        for q in QUANTILES:
            fb, ok = R.causal_quantile_flags(d, v, q=q, with_assessable=True)
            ks = N.onset_indices(d, onsets)
            res = N.relocation_null(d, fb, v, ks, horizon=horizon, draws=draws,
                                    assessable=ok)
            report["cells"][sig][f"{q:.2f}"] = res
            if "p_rate" not in res:
                row += f" | {'untestable':^20}"
                continue
            o = res["observed"]
            row += " | " + (f"{o['n_warned']}/{o['n_testable']} "
                            f"n={res['null_rate']['mean']:.2f} "
                            f"p={res['p_rate']:.3f}").center(20)
        print(row, flush=True)

    print("\ncell = warned/testable, n = no-skill null rate, p = relocation p-value")
    print("A result is only interesting where the observed rate exceeds n AND p is")
    print("small. Loosening the threshold raises both together.")

    # explicit check on the headline configuration
    full = report["cells"].get("CSRS[hawkes+rmt+hamilton]", {})
    warned_any = [q for q, r in full.items()
                  if r.get("observed", {}).get("n_warned", 0) > 0]
    print(f"\n[sens] full three-pillar system warned at ANY quantile in "
          f"{QUANTILES}: {warned_any if warned_any else 'NO — 0/6 at every level'}")

    outp = pathlib.Path(out_dir); outp.mkdir(parents=True, exist_ok=True)
    sfx = "" if pillar2 == "lam1" else f"_{pillar2}"
    jp = outp / f"threshold_sensitivity_h{horizon}{sfx}.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[sens] wrote {jp}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--draws", type=int, default=600)
    ap.add_argument("--out", default="docs/evidence/replay")
    ap.add_argument("--pillar2", choices=R.PILLAR2_MODES,
                    default="lam1",
                    help="Pillar 2 quantity: lam1 (shipped) or sca "
                         "(SPEC FR18). Research only.")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(
        main(a.horizon, a.draws, a.out, a.pillar2)))
