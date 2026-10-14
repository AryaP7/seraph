#!/usr/bin/env python3
# C10 — chronological evaluation of the research CSRS against baselines (FR32–FR36).
"""Does the composite add anything over its parts and over trivial baselines?

**Everything below is fixed before any number is looked at.**

* **Event labels.** `seraph/validation/epochs.py` is the single source of truth.
  Only epochs inside the CSRS span (2017-02-09 .. 2026-08-20) are evaluable:
  `ilfs_2018`, `covid_2020`, `tightening_2022`, `tariff_2026`. `gfc_2008` and
  `taper_2013` precede the Hawkes corpus and are excluded — not because they are
  inconvenient, but because Pillar 1 has no data there.
  **`tariff_2026`'s date is provisional (SPEC OQ3 is open).**
* **Horizons.** FR32: the crisis window is the 30 trading days from the break;
  the early-warning window is 5-15 trading days *before* it. Detection and
  advance warning are scored separately and never conflated.
* **Threshold rule, identical for every series.** Alert when the series sits in
  the top decile of its own **trailing two years**, computed causally (the
  reference window ends at `t`, never including the future). No threshold is
  fitted to any epoch. AUC is also reported because it is threshold-free.
* **Baselines.** The composite must beat (a) RMT alone, (b) Hawkes alone,
  (c) trailing-ranked realised volatility - the cheapest defensible stress proxy,
  taken from C4's `rv_t_yz` observations. If it does not, that is the result.
* **Sample-size limit, stated up front.** Four events, one with a provisional
  date, is far too few for a significance claim about lead time. Per-epoch
  outcomes are reported individually; no pooled p-value is computed, because with
  n=4 it would be theatre.

Run: python scripts/evaluate_csrs_research.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.validation.epochs import (  # noqa: E402
    CRISIS_WINDOW_DAYS,
    EPOCH_BREAKS,
    LEAD_WINDOW_DAYS,
)
from seraph.validation.harness import auc  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

TRAILING_YEARS = 2
TOP_DECILE = 0.90


def trailing_rank(dates: list[str], values: np.ndarray, years: int = TRAILING_YEARS) -> np.ndarray:
    """Causal percentile of each value within its own trailing `years` window."""
    out = np.full(values.size, np.nan)
    d = np.array([np.datetime64(x) for x in dates])
    span = np.timedelta64(365 * years, "D")
    for i in range(values.size):
        lo = d[i] - span
        w = values[(d >= lo) & (d <= d[i])]
        w = w[np.isfinite(w)]
        if w.size >= 60:
            out[i] = float((w <= values[i]).mean())
    return out


def crisis_labels(dates: list[str], epochs: dict) -> np.ndarray:
    """1 on the `CRISIS_WINDOW_DAYS` trading days from each break (inclusive)."""
    y = np.zeros(len(dates), dtype=int)
    idx = {d: i for i, d in enumerate(dates)}
    for _, (bd, _) in epochs.items():
        start = next((i for d, i in sorted(idx.items()) if d >= bd), None)
        if start is None:
            continue
        y[start:start + CRISIS_WINDOW_DAYS] = 1
    return y


async def load():
    c = await asyncpg.connect(resolve_dsn(), timeout=30)
    csrs = await c.fetch(
        "SELECT ts, csrs FROM csrs WHERE xi_mode='uniform' ORDER BY ts")
    rmt = await c.fetch("SELECT date, eigenvalues FROM rmt_output ORDER BY date")
    hwk = await c.fetch("SELECT ts, branching_ratio_n FROM hawkes_output "
                        "WHERE scope='market' ORDER BY ts")
    rv = await c.fetch("SELECT date, rv_t_yz FROM hamilton_output ORDER BY date")
    await c.close()
    return csrs, rmt, hwk, rv


def main() -> int:
    csrs_rows, rmt_rows, hwk_rows, rv_rows = asyncio.run(load())
    if not csrs_rows:
        print("[eval] csrs is empty — run scripts/run_csrs_research.py --write first")
        return 1

    dates = [str(r["ts"].date()) for r in csrs_rows]
    dset = set(dates)
    series = {"CSRS (composite)": np.array([float(r["csrs"]) for r in csrs_rows])}

    lam = {str(r["date"]): (float(r["eigenvalues"][0]) / len(r["eigenvalues"]))
           for r in rmt_rows if r["eigenvalues"]}
    series["RMT alone (lam1/N)"] = np.array([lam.get(d, np.nan) for d in dates])

    hv, hd = {}, sorted({str(r["ts"].date()) for r in hwk_rows})
    for r in hwk_rows:
        n = float(r["branching_ratio_n"])
        hv[str(r["ts"].date())] = n / (1.0 - n)
    carried, last = [], np.nan
    for d in dates:
        if d in hv:
            last = hv[d]
        carried.append(last)
    series["Hawkes alone (n/(1-n))"] = np.array(carried)

    rvd = {str(r["date"]): float(r["rv_t_yz"]) for r in rv_rows}
    series["Realised vol (baseline)"] = np.array([rvd.get(d, np.nan) for d in dates])

    evaluable = {k: v for k, v in EPOCH_BREAKS.items()
                 if any(d >= v[0] for d in dates) and v[0] <= dates[-1]
                 and v[0] >= dates[0]}
    y = crisis_labels(dates, evaluable)

    print(f"span            : {dates[0]} .. {dates[-1]}  ({len(dates):,} trading days)")
    print(f"evaluable epochs: {list(evaluable)}")
    print(f"excluded epochs : {[k for k in EPOCH_BREAKS if k not in evaluable]} "
          f"(outside the Hawkes corpus)")
    print(f"crisis days     : {int(y.sum())} of {y.size} ({100.0*y.mean():.1f}%)")
    print(f"threshold rule  : top decile of own trailing {TRAILING_YEARS}y (causal), "
          f"identical for every series")
    print()

    ranks = {k: trailing_rank(dates, v) for k, v in series.items()}

    print("=" * 92)
    print("A. DETECTION over the whole span (threshold-free AUC + top-decile alert behaviour)")
    print("=" * 92)
    hdr = f"{'series':<26}{'AUC':>8}{'alerts':>9}{'alert%':>8}{'precision':>11}{'recall':>9}"
    print(hdr); print("-" * len(hdr))
    for k, v in series.items():
        ok = np.isfinite(v)
        a = auc(v[ok], y[ok]) if ok.sum() else float("nan")
        r = ranks[k]
        fire = np.isfinite(r) & (r >= TOP_DECILE)
        tp = int((fire & (y == 1)).sum()); fp = int((fire & (y == 0)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(int(y.sum()), 1)
        print(f"{k:<26}{a:>8.4f}{int(fire.sum()):>9}{100.0*fire.mean():>7.1f}%"
              f"{prec:>11.4f}{rec:>9.4f}")
    print("\n  AUC 0.5 = no discrimination. A high alert% with low precision is a"
          "\n  permanently-on alarm, which is worse than useless operationally.")

    print("\n" + "=" * 92)
    print("B. PER-EPOCH: advance warning vs post-onset detection, reported separately")
    print("=" * 92)
    lo_d, hi_d = LEAD_WINDOW_DAYS
    for ep, (bd, _) in evaluable.items():
        bi = next((i for i, d in enumerate(dates) if d >= bd), None)
        if bi is None:
            continue
        lead = slice(max(0, bi - hi_d), max(0, bi - lo_d) + 1)
        crisis = slice(bi, min(len(dates), bi + CRISIS_WINDOW_DAYS))
        print(f"\n  {ep}  break={bd}"
              f"{'   [PROVISIONAL - SPEC OQ3 open]' if ep == 'tariff_2026' else ''}")
        print(f"    {'series':<26}{'lead t-15..t-5':>16}{'crisis t..t+30':>16}"
              f"{'pre-break rank':>16}")
        for k in series:
            r = ranks[k]
            lw, cw = r[lead], r[crisis]
            lf = np.nanmean(lw >= TOP_DECILE) if np.isfinite(lw).any() else np.nan
            cf = np.nanmean(cw >= TOP_DECILE) if np.isfinite(cw).any() else np.nan
            pre = np.nanmean(lw) if np.isfinite(lw).any() else np.nan
            print(f"    {k:<26}{lf:>15.0%}{cf:>15.0%}{pre:>16.3f}")
    print("\n  'lead' = share of the 5-15-day pre-break window already alerting"
          "\n  'crisis' = share of the 30 post-break days alerting."
          "\n  High crisis with low lead = a DETECTOR, not an early-warning system.")

    print("\n" + "=" * 92)
    print("C. INCREMENTAL VALUE of the composite")
    print("=" * 92)
    base = ranks["CSRS (composite)"]
    for k in series:
        if k == "CSRS (composite)":
            continue
        o = ranks[k]
        m = np.isfinite(base) & np.isfinite(o)
        print(f"  corr(CSRS, {k:<26}) = {np.corrcoef(base[m], o[m])[0,1]:+.4f}")
    print("\n  A composite that correlates ~1.0 with one pillar is that pillar"
          "\n  wearing a different label.")
    print("\nLIMITATION: 4 events, one with a provisional date. No pooled significance"
          "\nclaim is made and none should be read into the per-epoch table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
