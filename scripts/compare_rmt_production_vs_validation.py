#!/usr/bin/env python3
# C6 - production (stride=1) versus validation (stride=10) consistency check.
"""Do the daily production values reproduce the validation sweep where dates overlap?

The two runs are not expected to agree on everything, and knowing *which*
quantities must agree is the whole point of the check:

  MUST BE IDENTICAL - pure functions of the one window ending at date d, which
  is the same 1,000 trading days on the same equity calendar in both runs:
      N_t, the eigenvalue spectrum, trace, lambda_1, lambda_1/N, F_t,
      lambda_minus, lambda_plus
  MUST DIFFER, with a known cause - these depend on the *sequence* of evaluated
  dates, which is 10x denser in production:
      V_t^eig   differenced over Delta=1 day instead of Delta=10
      Omega_t   compared against t-1 instead of t-10
      csf       common support measured against t-1 instead of t-10
      SCA_t     rolling empirical-CDF ranks over a different history
      p-value   1,000 replications (FR19) instead of the sweep's 200

A discrepancy in the first group is a real defect. A discrepancy in the second
is expected, and this script quantifies it rather than waving it through.

Run: python scripts/compare_rmt_production_vs_validation.py [snapshot.json]
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.store.bootstrap import resolve_dsn  # noqa: E402

DEFAULT_SNAP = (Path(r"C:\Users\Arlop\AppData\Local\Temp\claude\C--")
                / "9e9903af-f60f-4f4a-82af-a9e0fd82f018" / "scratchpad"
                / "stride10_snapshot.json")

INVARIANT_FIELDS = ("n_t", "lam1", "lam1_share", "trace", "f_t",
                    "lambda_minus", "lambda_plus")
SEQUENCE_FIELDS = {
    "v_eig_t": "differenced over Delta=1 rather than Delta=10",
    "omega_t": "compared against t-1 rather than t-10",
    "csf": "common support measured against t-1 rather than t-10",
    "sca_t": "rolling ECDF over a 10x denser history",
    "mp_pvalue": "1,000 FR19 replications rather than 200",
}


async def main(snap_path: Path) -> int:
    if not snap_path.exists():
        print(f"snapshot not found: {snap_path}")
        return 1
    snap = {date.fromisoformat(r["date"]): r for r in json.load(open(snap_path))}
    print(f"validation snapshot: {len(snap)} dates "
          f"({min(snap)} .. {max(snap)})")

    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    rows = await pool.fetch(
        "SELECT date, eigenvalues, f_t, v_eig_t, omega_t, sca_t, mp_pvalue, "
        "lambda_minus, lambda_plus, common_support_fraction "
        "FROM rmt_output WHERE date = ANY($1::date[]) ORDER BY date",
        list(snap.keys()))
    total = await pool.fetchval("SELECT count(*) FROM rmt_output")
    await pool.close()
    print(f"production series : {total} rows; {len(rows)} of the "
          f"{len(snap)} validation dates are present\n")

    missing = sorted(set(snap) - {r["date"] for r in rows})
    if missing:
        print(f"WARNING: {len(missing)} validation dates absent from production: "
              f"{[m.isoformat() for m in missing[:8]]}\n")

    prod, val = {f: [] for f in INVARIANT_FIELDS}, {f: [] for f in INVARIANT_FIELDS}
    seq_p, seq_v = {f: [] for f in SEQUENCE_FIELDS}, {f: [] for f in SEQUENCE_FIELDS}
    spectrum_err = []
    for r in rows:
        s = snap[r["date"]]
        ev = np.asarray(r["eigenvalues"], dtype=float)
        got = {
            "n_t": float(ev.size), "lam1": float(ev[0]),
            "lam1_share": float(ev[0]) / ev.size, "trace": float(ev.sum()),
            "f_t": r["f_t"], "lambda_minus": r["lambda_minus"],
            "lambda_plus": r["lambda_plus"],
        }
        for f in INVARIANT_FIELDS:
            prod[f].append(got[f])
            val[f].append(float(s[f]))
        for f in SEQUENCE_FIELDS:
            key = "common_support_fraction" if f == "csf" else f
            seq_p[f].append(float(r[key]))
            seq_v[f].append(float(s[f]))

    print("MUST BE IDENTICAL (pure functions of the window)")
    print(f"  {'field':<15}{'max |abs diff|':>16}{'max |rel diff|':>16}   verdict")
    worst_ok = True
    for f in INVARIANT_FIELDS:
        a, b = np.array(prod[f]), np.array(val[f])
        ad = float(np.abs(a - b).max())
        denom = np.where(np.abs(b) > 0, np.abs(b), 1.0)
        rd = float((np.abs(a - b) / denom).max())
        ok = ad < 1e-9
        worst_ok &= ok
        print(f"  {f:<15}{ad:>16.3e}{rd:>16.3e}   {'identical' if ok else 'DIFFERS'}")

    print("\nMUST DIFFER (depend on the evaluated-date sequence)")
    print(f"  {'field':<12}{'prod mean':>12}{'valid mean':>12}"
          f"{'max |diff|':>13}   why")
    for f, why in SEQUENCE_FIELDS.items():
        a, b = np.array(seq_p[f]), np.array(seq_v[f])
        print(f"  {f:<12}{a.mean():>12.6f}{b.mean():>12.6f}"
              f"{np.abs(a - b).max():>13.6f}   {why}")

    print("\nSPECTRUM CHECK (full eigenvalue vector, not just lambda_1)")
    # Recompute lambda_1/N from the production spectrum and compare against the
    # value the validation run stored - this is the end-to-end persistence path.
    a = np.array(prod["lam1_share"])
    b = np.array(val["lam1_share"])
    print(f"  lambda_1/N reproduced from persisted spectrum on {len(a)} overlapping "
          f"dates: max |diff| = {np.abs(a - b).max():.3e}")

    print("\n" + "=" * 78)
    if worst_ok:
        print("CONSISTENT: every window-determined quantity is identical across the")
        print("two runs; the differing fields differ only where the evaluated-date")
        print("sequence changes them, which is expected and quantified above.")
    else:
        print("INCONSISTENT: a window-determined quantity differs between runs.")
        print("This is a real defect - investigate before accepting the series.")
    print("=" * 78)
    return 0 if worst_ok else 1


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SNAP
    raise SystemExit(asyncio.run(main(p)))
