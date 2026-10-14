#!/usr/bin/env python3
# Orchestration — the first real database-to-CSRS path: E7 + E6 -> C8 -> C9 -> E10.
"""Produce a **research-baseline** CSRS series from genuinely persisted pillar output.

This is the first end-to-end run in this repository that uses real model output
rather than mocks. What it is, precisely:

* **Inputs are real.** Pillar 2 from `rmt_output` (5,363 validated daily rows,
  29/29 acceptance checks) and Pillar 1 from `hawkes_output` (473 rows at the
  selected 500-session window, 5-session refit cadence).
* **Hamilton is EXCLUDED, and not by omission.** Its real-data causal
  investigation found 6/14 nesting violations to LR = -2,322.88, 3/14
  non-converged folds (including the COVID and tariff windows), near-absorbing
  transitions on 53% of dates and NFR17 separation of 0.269 sigma. An
  unidentified regime series must not enter fusion merely to complete the
  original architecture. It is emitted as a **structural** absence, which is the
  D2 mechanism built for exactly this, so the mask records its exclusion on every
  single row.
* **`xi_mode="uniform"` is used, which is a first-class spec'd mode**, not a
  workaround: `score()` substitutes (1/3,1/3,1/3) for Hamilton's regime
  probabilities and `xi_mode` sits in the `csrs` primary key, so a uniform-xi run
  can never be confused with a Hamilton-xi run.
* **Weights are an explicitly labelled equal-weight research baseline**, not a
  calibration. `CalibrationConfig.epochs` is deliberately EMPTY and
  `kappa_miss == kappa_fa == 1.0` (symmetric, i.e. no asymmetric loss asserted),
  so the artefact is self-evidently uncalibrated and its content hash binds that
  fact. C10's FR30 optimisation has not been run and no learned weight is claimed.
* **Alert thresholds are C9's documented provisional constants** (amber 0.50,
  red 0.75), still uncalibrated pending FR30. `alert_level` here is therefore a
  research label, not an operational alarm.

**What this does NOT establish.** A functioning pipeline is not predictive skill.
The CSRS produced here is a reproducible composite of two validated state
variables under a stated baseline weighting. It is not a calibrated probability
of anything, and nothing in this script evaluates lead time.

Run:
  python scripts/run_csrs_research.py                 # dry run
  python scripts/run_csrs_research.py --write         # persist to E10 (csrs)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.fusion.score import PROVISIONAL_AMBER, PROVISIONAL_RED, score  # noqa: E402
from seraph.orchestration import (  # noqa: E402
    close_ts,
    hawkes_contagion_emission,
    lam1_share,
    rmt_emission,
    stress_emission,
    window_from,
)
from seraph.reconciliation.kalman import KalmanReconciler  # noqa: E402
from seraph.shared_types import (  # noqa: E402
    PILLAR_ORDER,
    CalibrationConfig,
    FusionWeights,
    UnavailableEmission,
    ist_timestamp,
)
from seraph.shared_types.fusion import fusion_weights_artefact_id  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

ARTEFACT_DIR = Path(__file__).resolve().parent.parent / "artefacts"
EQUAL = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)


def baseline_weights(stress_slot: bool = False) -> FusionWeights:
    """An equal-weight research baseline, labelled as such in its own config.

    Empty `epochs` is the honest signal: these weights were trained on nothing.
    The D2 mask renormalises (1/3,1/3,1/3) to (1/2,1/2,0) once Hamilton is
    excluded, so the effective weighting is equal over the pillars that exist.
    """
    cfg = CalibrationConfig(
        epochs=(),                      # trained on NO epoch - not a calibration
        fold_held_out=None,
        kappa_miss=1.0,                 # symmetric: no asymmetric loss asserted
        kappa_fa=1.0,
        # The mask profile MUST differ between configurations: weights_artefact_id
        # is part of the csrs primary key, so reusing one id across two pillar
        # line-ups would silently overwrite one run with the other.
        mask_profile=(True, True, True) if stress_slot else (True, True, False),
    )
    w = (EQUAL, EQUAL, EQUAL)
    return FusionWeights(
        artefact_id=fusion_weights_artefact_id(w, cfg), calibrated_on=cfg, w=w)


def downside_semivariance(lr: np.ndarray, w: int = 20) -> np.ndarray:
    """sqrt(mean(min(r,0)^2)) over the trailing `w` days, causal.

    Only negative returns contribute, so an upside-volatility episode does not
    register as stress. out[i] uses lr[i-w+1 .. i] inclusive - never the future.
    """
    neg2 = np.minimum(lr, 0.0) ** 2
    out = np.full(lr.size, np.nan)
    for i in range(lr.size):
        seg = neg2[max(0, i - w + 1):i + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size >= max(3, w // 4):
            out[i] = float(np.sqrt(seg.mean()))
    return out


async def load_market(pool):
    return await pool.fetch("""
      WITH r AS (SELECT date, symbol,
                        ln(adj_close / NULLIF(lag(adj_close) OVER (PARTITION BY symbol ORDER BY date),0)) lr
                 FROM daily_prices WHERE universe_member_flag AND adj_close > 0)
      SELECT date, avg(lr) mkt FROM r WHERE lr IS NOT NULL GROUP BY date ORDER BY date""")


async def load(pool) -> dict:
    rmt = await pool.fetch(
        "SELECT date, eigenvalues FROM rmt_output ORDER BY date")
    hwk = await pool.fetch(
        "SELECT ts, branching_ratio_n FROM hawkes_output "
        "WHERE scope='market' ORDER BY ts")
    return {"rmt": rmt, "hwk": hwk}


async def main(write: bool, limit: int | None, stress_slot: bool,
               full_span: bool = False, dump: str | None = None) -> int:
    if write and full_span:
        # `weights_artefact_id` is in the csrs primary key and nothing in
        # CalibrationConfig encodes the span, so a full-span run would hash to
        # the SAME id as the 2017+ run and its overlapping rows would overwrite
        # them. The values genuinely differ — KalmanReconciler is recursive, so
        # a 2017 tick reached after 12 years of updates is not the same tick
        # reached from a cold start — so that overwrite would destroy evidence,
        # not deduplicate it. Persisting this needs a deliberate decision about
        # artefact identity; until then, research only.
        print("[csrs] REFUSING --write with --full-span: it would reuse the "
              "2017+ run's weights_artefact_id and overwrite its rows "
              "(PK = reconciliation_mode, xi_mode, weights_artefact_id, ts). "
              "Use --dump to evaluate without persisting.")
        return 2
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        raw = await load(pool)
        rmt_rows, hwk_rows = raw["rmt"], raw["hwk"]
        if not rmt_rows or not hwk_rows:
            print(f"[csrs] need both pillars: rmt_output={len(rmt_rows)} "
                  f"hawkes_output={len(hwk_rows)}")
            return 1

        # --- Pillar 2: the full lambda1/N history, for the FR28 ECDF window ---
        lam_series: list[tuple[str, float]] = []
        lam_by_date: dict[str, list[float]] = {}
        for r in rmt_rows:
            d = str(r["date"])
            ev = list(r["eigenvalues"] or [])
            s = lam1_share(ev)
            if s is None:
                continue
            lam_series.append((d, s))
            lam_by_date[d] = ev

        # --- Pillar 1: the contagion state at each refit, keyed by date -------
        # Keyed by the refit's ACTUAL timestamp, not its date.
        #
        # Comparing dates here is a real look-ahead leak, and the S5 contract
        # catches it: NSE's Diwali Muhurat session on 2024-11-01 ran 18:00-18:55
        # IST, so that refit carries ts 18:55 while the decision timestamp for
        # the same calendar day is the 15:30 close. A date-level "most recent
        # refit <= d" would hand the 15:30 decision a value computed three and a
        # half hours later, and `PillarObservation` rejects it outright:
        #   CONTRACT_VIOLATION: tau > ts - a pillar cannot be computed after the
        #   time it is valid for.
        # Selecting on timestamps makes the Muhurat refit become available the
        # following session, which is when it genuinely was.
        hwk_series: list[tuple[str, float]] = []
        hwk_pts: list[tuple[object, float, str]] = []   # (ts, n, tau iso)
        for r in hwk_rows:
            n = float(r["branching_ratio_n"])
            hwk_series.append((str(r["ts"].date()), n / (1.0 - n)))
            hwk_pts.append((r["ts"], n, ist_timestamp(r["ts"])))
        hwk_pts.sort(key=lambda x: x[0])
        hwk_dates = [str(p[0].date()) for p in hwk_pts]
        hwk_ts_only = [p[0] for p in hwk_pts]

        # --- the decision grid ------------------------------------------------
        # Default: daily RMT dates from the first Hawkes refit, which clamps the
        # CSRS to 2017-02-09+ (473 refits) even though Pillar 2 runs from
        # 2005-01-03 (5,363 rows) and 1,889 of the 2,357 ticks have Hawkes
        # masked off anyway.
        #
        # `--full-span` instead runs the whole Pillar 2 history and lets Hawkes
        # be a STRUCTURAL absence before its first refit. That is not a
        # workaround, it is the mechanism AGENTS.md section 5 specifies: "a
        # structurally-missing Hawkes score pre-2015 is expected, not a failure".
        # The per-tick loop below already emits exactly that when no refit
        # precedes the decision timestamp, so nothing else changes.
        #
        # It matters because the evaluation is onset-limited, not day-limited.
        # On the 2017+ span only 4 of the 6 FR32 breaks are covered, and the
        # no-signal 95th percentile of T1 AUC is 0.74-0.78 — above the 3-pillar
        # CSRS's 0.6743, so the detection claim cannot be tested there at all
        # (docs/evidence/EARLY-WARNING-POWER.md). Six onsets narrows that null to
        # ~0.62-0.65, which makes the claim decidable either way.
        first_h, last_h = hwk_dates[0], hwk_dates[-1]
        if full_span:
            grid = [d for d, _ in lam_series]
        else:
            grid = [d for d, _ in lam_series if first_h <= d <= last_h]
        if limit:
            grid = grid[:limit]
        print(f"[csrs] pillar 2 (E7): {len(lam_series):,} daily rows "
              f"{lam_series[0][0]} .. {lam_series[-1][0]}")
        print(f"[csrs] pillar 1 (E6): {len(hwk_dates):,} refits "
              f"{first_h} .. {last_h}")
        print(f"[csrs] pillar 3     : EXCLUDED as a STRUCTURAL absence "
              f"(causal run unidentified - see "
              f"docs/evidence/20261012T134047Z-hamilton-causal-REAL/REPORT.md)")
        print(f"[csrs] decision grid: {len(grid):,} daily ticks "
              f"{grid[0]} .. {grid[-1]}", flush=True)

        semi_at: dict[str, float] = {}
        semi_series: list[tuple[str, float]] = []
        if stress_slot:
            mkt = await load_market(pool)
            md = [str(r["date"]) for r in mkt]
            ml = np.array([float(r["mkt"]) for r in mkt])
            sv = downside_semivariance(ml)
            for dd, vv in zip(md, sv):
                if np.isfinite(vv):
                    semi_at[dd] = float(vv)
                    semi_series.append((dd, float(vv)))
            print(f"[csrs] pillar 3 slot : downside semivariance (20d, causal) over "
                  f"{len(semi_series):,} days {semi_series[0][0]} .. {semi_series[-1][0]}")
            print(f"[csrs]   PROVENANCE  : slot 3 is NAMED 'hamilton' in PILLAR_ORDER. "
                  f"mask[2]=True here means STRESS, not Hamilton.")
            print(f"[csrs]   NOT an early-warning signal: T3 AUC 0.4928 (chance), led 0/6 epochs")

        weights = baseline_weights(stress_slot)
        print(f"[csrs] weights      : equal-weight RESEARCH BASELINE, "
              f"artefact {weights.artefact_id[:16]}... "
              f"(epochs=() -> trained on nothing)")
        print(f"[csrs] xi_mode      : uniform (1/3,1/3,1/3) - Hamilton xi not used")
        print(f"[csrs] thresholds   : amber={PROVISIONAL_AMBER} red={PROVISIONAL_RED} "
              f"(C9 provisional, FR30 not run)", flush=True)

        rec = KalmanReconciler()
        points, errs, warn_codes = [], [], {}
        t0 = time.time()
        for d in grid:
            ts = close_ts(d)
            ems, ws = [], []

            e, w = rmt_emission(date=d, eigenvalues=lam_by_date.get(d),
                                window=window_from(lam_series, d))
            ems.append(e); ws.extend(w)

            # Pillar 1: the most recent refit whose ACTUAL timestamp is at or
            # before this decision timestamp. ts is the decision time, tau the
            # refit time, so C8's R(t-tau) inflates by real age rather than
            # pretending the kernel was refitted today.
            decision_dt = datetime.fromisoformat(ts)
            idx = bisect_right(hwk_ts_only, decision_dt) - 1
            if idx >= 0:
                _, n, tau = hwk_pts[idx]
                e, w = hawkes_contagion_emission(
                    ts=ts, tau=tau, branching_ratio=n,
                    window=window_from(hwk_series, d))
            else:
                e, w = UnavailableEmission(
                    pillar="hawkes", ts=ts, absence="structural",
                    reason="no_data_coverage"), ()
            ems.append(e); ws.extend(w)

            # Pillar 3 slot.
            if stress_slot:
                sv = semi_at.get(d)
                e3, w3 = stress_emission(
                    ts=ts, tau=ts, semivariance=sv,
                    window=window_from(semi_series, d))
                ems.append(e3); ws.extend(w3)
            else:
                # structural absence, every tick, by decision not accident
                ems.append(UnavailableEmission(
                    pillar="hamilton", ts=ts, absence="structural",
                    reason="no_data_coverage"))

            up = rec.update(ems)
            if up.status == "error":
                errs.append({"date": d, "stage": "C8", "error": repr(up.error)})
                continue
            st = up.value
            for w_ in (up.warnings or ()):
                warn_codes[w_.code] = warn_codes.get(w_.code, 0) + 1
            for w_ in ws:
                warn_codes[w_.code] = warn_codes.get(w_.code, 0) + 1

            sc = score(reconciled=st, xi=EQUAL, weights=weights,
                       xi_mode="uniform")
            if sc.status == "error":
                errs.append({"date": d, "stage": "C9", "error": repr(sc.error)})
                continue
            points.append(sc.value)
            for w_ in (sc.warnings or ()):
                warn_codes[w_.code] = warn_codes.get(w_.code, 0) + 1

        el = time.time() - t0
        print(f"\n[csrs] {len(points):,} CSRS points, {len(errs)} failures "
              f"in {el:.1f}s")
        if errs:
            print(f"[csrs] first failures: {errs[:3]}")
        if warn_codes:
            for c, k in sorted(warn_codes.items(), key=lambda x: -x[1]):
                print(f"[csrs] warning {c}: {k}")

        if points:
            v = np.array([p.csrs for p in points])
            var = np.array([p.variance for p in points])
            masks = {str(tuple(p.mask)) for p in points}
            lv = {}
            for p in points:
                lv[p.alert_level] = lv.get(p.alert_level, 0) + 1
            print(f"\n[csrs] CSRS  : mean={v.mean():.4f} sd={v.std():.4f} "
                  f"range=[{v.min():.4f}, {v.max():.4f}]")
            print(f"[csrs] var    : mean={var.mean():.6f} max={var.max():.6f}")
            print(f"[csrs] masks  : {masks}  (PILLAR_ORDER={PILLAR_ORDER})")
            print(f"[csrs] alerts : {lv}  (PROVISIONAL thresholds, not calibrated)")
            sh = np.array([p.shapley for p in points])
            print(f"[csrs] shapley mean by pillar: "
                  f"{dict(zip(PILLAR_ORDER, sh.mean(axis=0).round(4)))}")
            ew = {str(p.effective_weights) for p in points}
            print(f"[csrs] effective weights seen: {list(ew)[:2]}")

        if dump and points:
            dp = Path(dump)
            dp.parent.mkdir(parents=True, exist_ok=True)
            with dp.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write("ts,csrs,var,mask_hawkes,mask_rmt,mask_slot3\n")
                for p in points:
                    m = tuple(bool(x) for x in p.mask)
                    fh.write(f"{p.ts},{p.csrs:.10f},{p.variance:.10f},"
                             f"{int(m[0])},{int(m[1])},{int(m[2])}\n")
            print(f"\n[csrs] dumped {len(points):,} points to {dp} "
                  f"(NOT persisted to E10)")

        if not write:
            print("\n[csrs] DRY RUN - nothing written. Re-run with --write.")
            return 0

        ARTEFACT_DIR.mkdir(exist_ok=True)
        ap = ARTEFACT_DIR / f"fusion_weights.{weights.artefact_id[:16]}.json"
        ap.write_text(json.dumps(weights.model_dump(by_alias=True), indent=2,
                                 default=str), encoding="utf-8")
        print(f"\n[csrs] wrote weights artefact {ap}")

        before = await pool.fetchval("SELECT count(*) FROM csrs")
        async with pool.acquire() as conn:
            async with conn.transaction():
                for p in points:
                    await conn.execute(
                        """
                        INSERT INTO csrs (ts, reconciliation_mode, xi_mode,
                            weights_artefact_id, csrs, var_csrs, ci_lower, ci_upper,
                            shapley, alert_level, mask, effective_weights)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
                        ON CONFLICT (reconciliation_mode, xi_mode,
                                     weights_artefact_id, ts) DO UPDATE SET
                            csrs=EXCLUDED.csrs, var_csrs=EXCLUDED.var_csrs,
                            ci_lower=EXCLUDED.ci_lower, ci_upper=EXCLUDED.ci_upper,
                            shapley=EXCLUDED.shapley, alert_level=EXCLUDED.alert_level,
                            mask=EXCLUDED.mask,
                            effective_weights=EXCLUDED.effective_weights
                        """,
                        # CsrsPoint.ts is an ISOTimestamp *string* per the S8
                        # contract; csrs.ts is timestamptz, so asyncpg needs a
                        # datetime. The +05:30 offset is preserved by fromisoformat.
                        datetime.fromisoformat(p.ts), p.reconciliation_mode, p.xi_mode,
                        p.weights_artefact_id, p.csrs, p.variance,
                        p.ci_lower, p.ci_upper, list(p.shapley), p.alert_level,
                        list(p.mask),
                        json.dumps([list(r) for r in p.effective_weights]))
        after = await pool.fetchval("SELECT count(*) FROM csrs")
        print(f"[csrs] E10 rows: {before:,} -> {after:,} "
              f"(inserted {after-before:,}, updated {len(points)-(after-before):,})")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--write", action="store_true", help="persist to E10 (csrs)")
    ap_.add_argument("--stress-slot", action="store_true",
                     help="put downside semivariance in PILLAR_ORDER slot 3 instead of "
                          "leaving Hamilton structurally absent (see stress_emission)")
    ap_.add_argument("--limit", type=int, default=None,
                     help="process only the first N ticks (smoke testing)")
    ap_.add_argument("--full-span", action="store_true",
                     help="run the whole Pillar 2 history (2005+) with Hawkes a "
                          "STRUCTURAL absence before its first refit, instead of "
                          "clamping the grid to the Hawkes span. Research only — "
                          "incompatible with --write, see main()")
    ap_.add_argument("--dump", default=None,
                     help="write the CSRS series to this CSV instead of E10")
    a = ap_.parse_args()
    raise SystemExit(asyncio.run(
        main(a.write, a.limit, a.stress_slot, a.full_span, a.dump)))
