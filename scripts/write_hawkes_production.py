#!/usr/bin/env python3
# C5 — Hawkes Engine (FR10–FR15, as amended by AMENDMENT-03): the E6 production writer.
"""Fit the production discrete-time Hawkes kernel on a rolling window and persist
the resulting market-scope state to `hawkes_output` (E6).

**Why this script exists.** Every other Pillar 1 entry point is a diagnostic. The
validated parameters (alpha~0.0557, phi~0.4837, n~0.1079) came from chronological
folds of the *whole corpus*; `hawkes_output` had no writer at all, so E6 was empty
and C8 had no Hawkes emission to consume.

**Conventions followed, deliberately.**

* `hawkes_output` / E6 is **not** registered in `StoreWriter._REGISTRY` — that
  registry serves ingestion entities, which arrive as an `IngestBatch` with a
  source and a watermark. A pillar output has neither. `scripts/run_rmt.py`
  persists E7 with a direct `INSERT ... ON CONFLICT DO UPDATE`, so this script
  does the same for E6 rather than bending the ingestion contract.
* **Idempotency is on the natural key** `(scope, scope_id, ts)`, which is E6's
  primary key. Re-running over the same span must leave the row count unchanged.
* **Timestamps.** `hawkes_output.ts` is `timestamptz`; asyncpg takes an aware
  `datetime` directly. `ist_timestamp()` / `close_ts()` produce the `+05:30`
  *strings* the S5 emission boundary parses — they are not for the database. The
  `ts` written here is the timestamp of the window's final bar, taken from the
  data, so no timestamp is ever synthesised.
* **Absence is recorded, never imputed.** When `estimate_state` returns `Err`
  (unidentifiable window, FR11 violation) the date is skipped and counted. A
  fabricated `n = 0` would be indistinguishable from genuine calm, which is
  exactly what the `Ok`-carried-absence design exists to prevent.

**The window is a required argument with no default.** `WINDOW_DAYS = 60` is a
declared constant in the engine whose value was never validated; on 60-day
windows the branching ratio's CV is 0.714 (it swings 0.0057–0.2034). Passing the
window explicitly forces the caller to state which validated configuration they
are running. See `docs/evidence/*-hawkes-window-*.log`.

Run:
  python scripts/write_hawkes_production.py --window-days 500 --refit-every 5
  python scripts/write_hawkes_production.py --window-days 500 --refit-every 5 --write
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.features import extract_jumps  # noqa: E402
from seraph.ingestion.hawkes_universe import build_symbol_list  # noqa: E402
from seraph.pillars.hawkes import estimate_state  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

#: A ±5-session shift of a 500-day window moves the branching ratio by
#: |dn| = 0.0012, against n's own corpus sd of 0.0193 — so refitting every five
#: sessions rather than daily costs essentially nothing and is 5x cheaper.
#: Measured, not assumed: see the boundary-sensitivity column of
#: scripts/compare_hawkes_windows.py.
DEFAULT_REFIT_EVERY = 5
MIN_SYMBOL_BARS = 200


async def load_stream(pool, symbols: list[str]) -> dict:
    """Build the pooled market-wide jump stream from E1, with explicit data quality.

    Returns per-bar negative and positive jump counts, the number of symbols
    actually contributing to each bar, and the session/time-of-day indices the
    discrete-time kernel needs.

    **Zero-close handling is explicit.** 3,558 intraday bars in this corpus carry
    `close <= 0` across 10 symbols, all of them inside the Hawkes universe, and
    they arrive as contiguous whole sessions (INFY: 12 sessions x 75 bars,
    2015-04-27..2015-05-13) — a feed gap stored as zeros rather than nulls. A
    non-positive price has no log return, so such bars are **dropped from the
    stream and counted**, never patched with a carried-forward or interpolated
    price. `extract_jumps` is empirically robust to them (0 NaN, 0 inf, 0 jumps
    flagged on a non-finite return), so this changes no measured jump; it stops
    them inflating the per-bar active-symbol count, which is the one place they
    would otherwise distort the exposure denominator.
    """
    neg, pos, grid = [], [], {}
    dq = {"symbols_requested": len(symbols), "symbols_used": 0,
          "symbols_too_short": 0, "bars_read": 0, "bars_dropped_nonpositive": 0}

    for sym in symbols:
        rows = await pool.fetch(
            "SELECT ts, close FROM intraday_bars WHERE symbol=$1 ORDER BY ts", sym)
        dq["bars_read"] += len(rows)
        ts = [r["ts"] for r in rows]
        close = np.array([float(r["close"]) for r in rows], dtype=float)
        if close.size:
            good = close > 0.0
            dropped = int((~good).sum())
            if dropped:
                dq["bars_dropped_nonpositive"] += dropped
                ts = [t for t, g in zip(ts, good) if g]
                close = close[good]
        if close.size < MIN_SYMBOL_BARS:
            dq["symbols_too_short"] += 1
            continue
        dq["symbols_used"] += 1
        out = extract_jumps(close)
        for t in ts:
            grid[t] = grid.get(t, 0) + 1
        sign = out["jump_sign"]
        for i in np.flatnonzero(sign == -1):
            neg.append(ts[i])
        for i in np.flatnonzero(sign == 1):
            pos.append(ts[i])

    bars = sorted(grid)
    cneg, cpos = Counter(neg), Counter(pos)
    day = np.array([t.date() for t in bars])
    tod = np.array([t.hour * 60 + t.minute for t in bars])
    slots = np.unique(tod)
    return {
        "bars": bars,
        "n_neg": np.array([cneg.get(t, 0) for t in bars], dtype=float),
        "n_pos": np.array([cpos.get(t, 0) for t in bars], dtype=float),
        "active": np.array([grid[t] for t in bars], dtype=float),
        "day": day,
        "tod_index": np.searchsorted(slots, tod),
        "n_slots": slots.size,
        "new_sess": np.r_[True, day[1:] != day[:-1]],
        "dq": dq,
    }


def tod_profile(counts: np.ndarray, tod_index: np.ndarray, n_slots: int) -> np.ndarray:
    """Mean intensity per time-of-day slot, normalised to mean 1.

    Computed on the *window* only, so a production refit never sees a future
    session's diurnal pattern.
    """
    tot = np.bincount(tod_index, weights=counts, minlength=n_slots)
    cnt = np.bincount(tod_index, minlength=n_slots).astype(float)
    prof = np.where(cnt > 0, tot / np.maximum(cnt, 1.0), counts.mean())
    return prof / max(prof.mean(), 1e-12)


def refit_points(day: np.ndarray, new_sess: np.ndarray, window_days: int,
                 refit_every: int) -> list[tuple[int, int]]:
    """`(window_start_index, as_of_index)` pairs, stepping by whole sessions.

    The first refit is the earliest bar that has `window_days` complete sessions
    behind it; `as_of_index` is the last bar of that session, so the emitted `ts`
    is a real bar timestamp from the data.
    """
    starts = np.flatnonzero(new_sess)                 # first bar of each session
    ends = np.r_[starts[1:] - 1, len(day) - 1]        # last bar of each session
    out = []
    for k in range(window_days, starts.size, refit_every):
        out.append((int(starts[k - window_days]), int(ends[k])))
    return out


async def main(window_days: int, refit_every: int, write: bool) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        members = await pool.fetchval(
            "SELECT members FROM universe_snapshots ORDER BY rebalance_date DESC LIMIT 1")
        if not members:
            print("[hawkes] no universe snapshot — run scripts/build_universe.py first")
            return 1
        symbols = build_symbol_list(list(members))
        print(f"[hawkes] universe: {len(symbols)} symbols (equity-only, "
              f"build_symbol_list — never a raw intraday_bars scan)", flush=True)

        t0 = time.time()
        st = await load_stream(pool, symbols)
        dq = st["dq"]
        print(f"[hawkes] stream: {len(st['bars']):,} bars, "
              f"{int(st['n_neg'].sum()):,} negative / {int(st['n_pos'].sum()):,} positive "
              f"jumps, {int(st['new_sess'].sum()):,} sessions  ({time.time()-t0:.0f}s)")
        print(f"[hawkes] data quality: {dq['symbols_used']}/{dq['symbols_requested']} symbols "
              f"used, {dq['symbols_too_short']} too short, "
              f"{dq['bars_dropped_nonpositive']:,} bars dropped for close<=0 "
              f"(of {dq['bars_read']:,} read)")

        pts = refit_points(st["day"], st["new_sess"], window_days, refit_every)
        if not pts:
            print(f"[hawkes] window_days={window_days} exceeds the corpus "
                  f"({int(st['new_sess'].sum())} sessions) — nothing to emit")
            return 1
        print(f"[hawkes] schedule: window={window_days}d refit_every={refit_every} "
              f"-> {len(pts)} refit points, "
              f"{st['day'][pts[0][1]]} .. {st['day'][pts[-1][1]]}", flush=True)

        rows, errs, warn_counts = [], [], Counter()
        t0 = time.time()
        for j, (lo, hi) in enumerate(pts):
            sl = slice(lo, hi + 1)
            counts = st["n_neg"][sl]
            prof = tod_profile(counts, st["tod_index"][sl], st["n_slots"])
            res = estimate_state(
                counts=counts,
                session_starts=st["new_sess"][sl],
                tod_profile=prof,
                tod_index=st["tod_index"][sl],
                n_neg=int(st["n_neg"][sl].sum()),
                n_pos=int(st["n_pos"][sl].sum()),
            )
            if res.status == "error":
                errs.append({"as_of": str(st["day"][hi]), "error": repr(res.error)})
                continue
            detail, mts = res.value
            for w in res.warnings:
                warn_counts[w.code] += 1
            rows.append({
                "ts": st["bars"][hi],                     # aware datetime, from the data
                "scope": "market",
                "scope_id": "",
                "n": float(detail.branching_ratio),
                "mts": float(mts),
                "neg": int(detail.jump_count_neg),
                "pos": int(detail.jump_count_pos),
                "asym": float(detail.asymmetry_ratio),
                "flag": "none",                           # FR14 needs sector baselines
                "bmatrix": json.dumps(
                    [list(r) for r in detail.branching_matrix]) if detail.branching_matrix else None,
                "alpha_beta": None,
            })
            if (j + 1) % 50 == 0:
                print(f"  [hawkes] {j+1}/{len(pts)} refits, {len(rows)} ok, "
                      f"{len(errs)} absent ({time.time()-t0:.0f}s)", flush=True)

        print(f"\n[hawkes] {len(rows)} estimates, {len(errs)} absences "
              f"in {(time.time()-t0)/60:.1f} min")
        if warn_counts:
            for code, k in warn_counts.most_common():
                print(f"[hawkes] warning {code}: {k}/{len(rows)} windows")
        if errs:
            print(f"[hawkes] first absences: {errs[:3]}")

        if rows:
            n_arr = np.array([r["n"] for r in rows])
            m_arr = np.array([r["mts"] for r in rows])
            print(f"[hawkes] n   : mean={n_arr.mean():.4f} sd={n_arr.std():.4f} "
                  f"range=[{n_arr.min():.4f}, {n_arr.max():.4f}] CV={n_arr.std()/n_arr.mean():.3f}")
            print(f"[hawkes] MTS : mean={m_arr.mean():.4f} sd={m_arr.std():.4f} "
                  f"range=[{m_arr.min():.4f}, {m_arr.max():.4f}]")
            print(f"[hawkes] FR11 n<1 on every row: {bool((n_arr < 1.0).all())}")
            print(f"[hawkes] FR13 mts>=0 on every row: {bool((m_arr >= 0.0).all())}")

        if not write:
            print("\n[hawkes] DRY RUN — nothing written. Re-run with --write to persist.")
            return 0

        before = await pool.fetchval("SELECT count(*) FROM hawkes_output")
        async with pool.acquire() as conn:
            async with conn.transaction():
                for r in rows:
                    await conn.execute(
                        """
                        INSERT INTO hawkes_output (ts, scope, scope_id, branching_ratio_n,
                            mts, jump_count_neg, jump_count_pos, asymmetry_ratio,
                            sector_microflag, branching_matrix, alpha_beta)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb)
                        ON CONFLICT (scope, scope_id, ts) DO UPDATE SET
                            branching_ratio_n=EXCLUDED.branching_ratio_n,
                            mts=EXCLUDED.mts,
                            jump_count_neg=EXCLUDED.jump_count_neg,
                            jump_count_pos=EXCLUDED.jump_count_pos,
                            asymmetry_ratio=EXCLUDED.asymmetry_ratio,
                            sector_microflag=EXCLUDED.sector_microflag,
                            branching_matrix=EXCLUDED.branching_matrix,
                            alpha_beta=EXCLUDED.alpha_beta
                        """,
                        r["ts"], r["scope"], r["scope_id"], r["n"], r["mts"],
                        r["neg"], r["pos"], r["asym"], r["flag"],
                        r["bmatrix"], r["alpha_beta"])
        after = await pool.fetchval("SELECT count(*) FROM hawkes_output")
        print(f"\n[hawkes] E6 rows: {before:,} -> {after:,} "
              f"(inserted {after-before:,}, updated {len(rows)-(after-before):,})")
        print("[hawkes] re-run this command to confirm idempotency: the count must not move")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, required=True,
                    help="rolling estimation window in SESSIONS; no default on purpose — "
                         "pass the validated value (see docs/evidence/*hawkes-window*)")
    ap.add_argument("--refit-every", type=int, default=DEFAULT_REFIT_EVERY,
                    help=f"sessions between refits (default {DEFAULT_REFIT_EVERY}; "
                         f"justified by |dn|=0.0012 at a +/-5-session shift)")
    ap.add_argument("--write", action="store_true",
                    help="persist to E6; omit for a dry run")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.window_days, a.refit_every, a.write)))
