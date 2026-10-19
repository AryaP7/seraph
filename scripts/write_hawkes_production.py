#!/usr/bin/env python3
# C5 — Hawkes Engine (FR10–FR15, as amended by AMENDMENT-03): the E6 production writer.
"""Fit the production discrete-time Hawkes kernel on a rolling window and persist
the resulting market-scope state to `hawkes_output` (E6).

**Why this script exists.** Every other Pillar 1 entry point is a diagnostic. The
validated parameters (alpha~0.0557, phi~0.4837, n~0.1079) came from chronological
folds of the *whole corpus*; `hawkes_output` had no writer at all, so E6 was empty
and C8 had no Hawkes emission to consume.

**T05 / audit finding R11 — the basket now governs the counts.** Until this
revision the universe was resolved once, at the end of the corpus; one pooled
stream was loaded from those symbols and every window was a slice of it. A
point-in-time basket *was* resolved per window, but only to be written into the
artefact — so the metadata described a membership that had not produced the
numbers beside it. Now `BasketTimeline` carries the whole snapshot history, the
stream holds each symbol's events separately
(`seraph.pillars.hawkes.basket_stream`), and each window's counts are pooled
from that window's own member set. Every row carries a `WindowManifest`:
basket digest, membership policy, contributing symbols, a content hash of the
input rows and a hash of the counts handed to the estimator, so the agreement
is checkable rather than asserted.

**Membership policy is an argument, not a default.** `fixed_at_fit_cutoff` is
the adopted policy (DR-08) and matches the basket the artefact already
recorded; `fixed_at_window_start` and `day_varying` are implemented so the
choice can be audited rather than argued about.

**Conventions followed, deliberately.**

* `hawkes_output` / E6 is **not** registered in `StoreWriter._REGISTRY` — that
  registry serves ingestion entities, which arrive as an `IngestBatch` with a
  source and a watermark. A pillar output has neither. `scripts/run_rmt.py`
  persists E7 with a direct `INSERT ... ON CONFLICT DO UPDATE`, so this script
  does the same for E6 rather than bending the ingestion contract.
* **Idempotency is on the natural key** `(scope, scope_id, ts)`, which is E6's
  primary key. Re-running over the same span must leave the row count unchanged.
* **A regeneration goes to a new namespace.** `--namespace` sets `scope_id`, so
  corrected rows never overwrite the pre-T05 ones: the old artefacts and the
  negative results computed from them stay exactly where they are. Writing into
  the legacy empty namespace requires `--namespace legacy-overwrite` to be
  spelled out.
* **Timestamps.** `hawkes_output.ts` is `timestamptz`; asyncpg takes an aware
  `datetime` directly. The `ts` written here is the timestamp of the window's
  final bar, taken from the data, so no timestamp is ever synthesised.
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
  python scripts/write_hawkes_production.py --window-days 500 --refit-every 5 \
      --namespace basket_v2 --write
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

from seraph.ingestion.hawkes_universe import BasketTimeline  # noqa: E402
from seraph.pillars.hawkes import estimate_state  # noqa: E402
from seraph.pillars.hawkes.artefact import (  # noqa: E402
    BasketIdentity,
    artefact_from_fit,
)
from seraph.pillars.hawkes.basket_stream import (  # noqa: E402
    MEMBERSHIP_POLICIES,
    PooledStream,
    StreamBuilder,
    membership_segments,
    segments_digest,
    verify_manifest,
)
from seraph.pillars.hawkes.engine import fit_discrete_hawkes  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

#: A ±5-session shift of a 500-day window moves the branching ratio by
#: |dn| = 0.0012, against n's own corpus sd of 0.0193 — so refitting every five
#: sessions rather than daily costs essentially nothing and is 5x cheaper.
#: Measured, not assumed: see the boundary-sensitivity column of
#: scripts/compare_hawkes_windows.py.
DEFAULT_REFIT_EVERY = 5

#: Writing into the pre-T05 namespace (`scope_id = ''`) would overwrite rows
#: whose counts came from the terminal basket. That is a destructive act on
#: evidence, so it needs this word rather than an empty default.
LEGACY_NAMESPACE_TOKEN = "legacy-overwrite"


async def load_stream(pool, symbols, *, progress_every: int = 20) -> PooledStream:
    """Read E1 once per symbol and reduce each symbol as it arrives.

    Each symbol is read once for the whole corpus; which windows it then
    contributes to is decided by that window's member set, not by this read —
    that separation is the whole of the T05 correction. The rows are released
    per symbol rather than accumulated, so the footprint is the reduced arrays
    and not the corpus.
    """
    builder = StreamBuilder(requested=list(symbols))
    for i, sym in enumerate(symbols, 1):
        rows = await pool.fetch(
            "SELECT ts, close FROM intraday_bars WHERE symbol=$1 ORDER BY ts", sym)
        builder.add(sym, [r["ts"] for r in rows],
                    np.fromiter((float(r["close"]) for r in rows), dtype=float,
                                count=len(rows)))
        del rows
        if progress_every and i % progress_every == 0:
            print(f"  [hawkes] read {i}/{len(symbols)} symbols", flush=True)
    return builder.finish()


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
                 refit_every: int) -> "list[tuple[int, int]]":
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


def basket_identity_for(manifest, timeline: BasketTimeline) -> BasketIdentity:
    """The basket the artefact declares — now the one that produced the counts.

    `day_varying` has no single rebalance date, so it is recorded as a fixed
    research basket carrying its own limitation note rather than claimed as a
    point-in-time snapshot it is not.
    """
    snapshot = timeline.at(manifest.as_of)
    members = snapshot.basket if snapshot else ()
    if manifest.membership_policy == "day_varying":
        return BasketIdentity(
            basis="fixed_research_basket", symbols=members,
            rebalance_date=snapshot.rebalance_date if snapshot else None,
            note=("day-varying membership: composition changes inside the "
                  "window, so a change in n cannot be separated from a change "
                  "in who was counted. The symbols listed are the set in force "
                  "at the cutoff; the per-segment composition is in the "
                  "window manifest"))
    if snapshot is None:
        return BasketIdentity(
            basis="fixed_research_basket", symbols=(), rebalance_date=None,
            note=f"no universe snapshot exists at or before {manifest.as_of}")
    return BasketIdentity(basis="point_in_time", symbols=members,
                          rebalance_date=snapshot.rebalance_date)


async def main(window_days: int, refit_every: int, write: bool, *,
               policy: str, namespace: str, limit: int | None,
               manifest_out: str | None) -> int:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        rows = await pool.fetch(
            "SELECT rebalance_date, members FROM universe_snapshots "
            "ORDER BY rebalance_date")
        if not rows:
            print("[hawkes] universe_snapshots is empty — no basket to fit over")
            return 1
        timeline = BasketTimeline.from_rows(rows)
        described = timeline.describe()
        print(f"[hawkes] basket timeline: {described['snapshots']} snapshots "
              f"{described['first']} .. {described['last']}; "
              f"{described['union_size']} symbols ever a member, "
              f"{described['terminal_size']} in the terminal basket, "
              f"{len(described['never_in_terminal'])} never in it")
        print(f"[hawkes] membership policy: {policy}")

        t0 = time.time()
        stream = await load_stream(pool, timeline.union)
        quality = stream.quality
        if not stream.bars:
            print("[hawkes] no usable intraday bars — nothing to fit")
            return 1
        print(f"[hawkes] stream: {len(stream.bars):,} bars over "
              f"{stream.n_sessions:,} sessions, {quality.symbols_used} symbols "
              f"carrying events  ({time.time()-t0:.0f}s)")
        print(f"[hawkes] data quality: {quality.symbols_used}/"
              f"{quality.symbols_requested} symbols used, "
              f"{len(quality.symbols_too_short)} too short, "
              f"{len(quality.symbols_absent)} with no intraday rows at all, "
              f"{quality.bars_dropped_nonpositive:,} bars dropped for close<=0 "
              f"(of {quality.bars_read:,} read)")

        pts = refit_points(stream.day, stream.new_sess, window_days, refit_every)
        if not pts:
            print(f"[hawkes] window_days={window_days} exceeds the corpus "
                  f"({stream.n_sessions} sessions) — nothing to emit")
            return 1
        if limit:
            pts = pts[-limit:]
            print(f"[hawkes] --limit {limit}: running the most recent "
                  f"{len(pts)} refit points only")
        print(f"[hawkes] schedule: window={window_days}d refit_every={refit_every} "
              f"-> {len(pts)} refit points, "
              f"{stream.day[pts[0][1]]} .. {stream.day[pts[-1][1]]}", flush=True)

        out_rows, errs, warn_counts = [], [], Counter()
        manifests, mismatches = [], []
        coverage = []
        t0 = time.time()
        for j, (lo, hi) in enumerate(pts):
            segments = membership_segments(stream, lo, hi, policy=policy,
                                           resolve=timeline.members_at)
            cutoff = timeline.at(str(stream.day[hi]))
            # What was DECLARED to govern this window is the union of its
            # segments, not the cutoff basket: under `day_varying` those are
            # different sets, and the manifest must describe the schedule that
            # actually ran rather than one convenient member of it.
            declared = sorted(set().union(*(set(m) for _, _, m in segments)))
            inputs, manifest = stream.window(
                lo, hi, segments=segments, policy=policy, declared=declared,
                basket_id=segments_digest(segments),
                basket_basis=("point_in_time" if len(segments) == 1
                              else "fixed_research_basket"),
                rebalance_date=cutoff.rebalance_date if cutoff else None)

            # The manifest must describe the counts actually passed on. This is
            # the R11 guard: a mismatch here means the metadata has drifted off
            # the input again, and the run stops rather than emitting a row
            # whose description is wrong.
            problems = verify_manifest(manifest, n_neg=inputs["n_neg"],
                                       n_pos=inputs["n_pos"],
                                       active=inputs["active"])
            if problems:
                mismatches.append(dict(as_of=manifest.as_of, problems=problems))
                continue
            coverage.append(manifest.coverage)
            manifests.append(manifest.describe())

            counts = inputs["n_neg"]
            prof = tod_profile(counts, inputs["tod_index"], inputs["n_slots"])
            res = estimate_state(
                counts=counts,
                session_starts=inputs["session_starts"],
                tod_profile=prof,
                tod_index=inputs["tod_index"],
                n_neg=manifest.n_neg,
                n_pos=manifest.n_pos,
            )
            if res.status == "error":
                errs.append({"as_of": manifest.as_of, "error": repr(res.error)})
                continue
            detail, mts = res.value
            for w in res.warnings:
                warn_counts[w.code] += 1

            # FIX07 / audit finding A08: keep the fit. Re-running the estimator
            # here is cheap relative to the stream read, and it is the only way
            # to persist parameters the public estimator does not return.
            fit = fit_discrete_hawkes(counts, inputs["session_starts"], prof,
                                      inputs["tod_index"])
            artefact = None
            if fit is not None:
                basket = basket_identity_for(manifest, timeline)
                basket_problems = basket.validate(window_end=manifest.as_of)
                if basket_problems:
                    basket = BasketIdentity(
                        basis="fixed_research_basket", symbols=basket.symbols,
                        rebalance_date=basket.rebalance_date,
                        note=("the point-in-time basket was not usable here ("
                              + "; ".join(basket_problems) + "), so the "
                              "survivorship limitation is recorded explicitly "
                              "rather than passed off as point-in-time"))
                artefact = artefact_from_fit(
                    fit, as_of=manifest.as_of,
                    training_start=manifest.training_start,
                    tod_profile=prof, n_slots=int(inputs["n_slots"]),
                    basket=basket,
                    n_neg=manifest.n_neg, n_pos=manifest.n_pos,
                    n_sessions=manifest.n_sessions,
                    mts=float(mts),
                    warnings=tuple(w.code for w in res.warnings))
            payload = artefact.describe() if artefact else {}
            if payload:
                payload["window_manifest"] = manifest.describe()
            out_rows.append({
                "ts": inputs["bars"][-1],                 # aware datetime, from the data
                "scope": "market",
                "scope_id": namespace,
                "n": float(detail.branching_ratio),
                "mts": float(mts),
                "neg": int(detail.jump_count_neg),
                "pos": int(detail.jump_count_pos),
                "asym": float(detail.asymmetry_ratio),
                # FR14 needs measured sector baselines. Until they exist no
                # flag is emitted at all: a constant 'none' is indistinguishable
                # from a measurement that found nothing (audit finding A08).
                "flag": (detail.sector_flags[0].flag if detail.sector_flags else None),
                "bmatrix": json.dumps(
                    [list(r) for r in detail.branching_matrix]) if detail.branching_matrix else None,
                # The fitted kernel, its seasonality, its training window, the
                # basket it used and the manifest proving that basket produced
                # these counts — enough to rebuild lambda_t from the row alone.
                "alpha_beta": json.dumps(payload) if payload else None,
                "artefact_id": artefact.artefact_id if artefact else None,
            })
            if (j + 1) % 50 == 0:
                print(f"  [hawkes] {j+1}/{len(pts)} refits, {len(out_rows)} ok, "
                      f"{len(errs)} absent ({time.time()-t0:.0f}s)", flush=True)

        print(f"\n[hawkes] {len(out_rows)} estimates, {len(errs)} absences "
              f"in {(time.time()-t0)/60:.1f} min")
        if mismatches:
            print(f"[hawkes] {len(mismatches)} windows REFUSED — the manifest "
                  f"did not describe the counts: {mismatches[:2]}")
        if coverage:
            cov = np.array(coverage)
            print(f"[hawkes] basket coverage (declared members with bars in the "
                  f"window): mean={cov.mean():.3f} min={cov.min():.3f} "
                  f"max={cov.max():.3f}")
        if warn_counts:
            for code, k in warn_counts.most_common():
                print(f"[hawkes] warning {code}: {k}/{len(out_rows)} windows")
        if errs:
            print(f"[hawkes] first absences: {errs[:3]}")

        if out_rows:
            n_arr = np.array([r["n"] for r in out_rows])
            m_arr = np.array([r["mts"] for r in out_rows])
            print(f"[hawkes] n   : mean={n_arr.mean():.4f} sd={n_arr.std():.4f} "
                  f"range=[{n_arr.min():.4f}, {n_arr.max():.4f}] "
                  f"CV={n_arr.std()/max(n_arr.mean(), 1e-12):.3f}")
            print(f"[hawkes] MTS : mean={m_arr.mean():.4f} sd={m_arr.std():.4f} "
                  f"range=[{m_arr.min():.4f}, {m_arr.max():.4f}]")
            print(f"[hawkes] FR11 n<1 on every row: {bool((n_arr < 1.0).all())}")
            print(f"[hawkes] FR13 mts>=0 on every row: {bool((m_arr >= 0.0).all())}")

        if manifest_out:
            Path(manifest_out).write_text(json.dumps(dict(
                policy=policy, namespace=namespace, window_days=window_days,
                refit_every=refit_every, timeline=timeline.describe(),
                stream_quality=quality.describe(),
                refit_points=len(pts), emitted=len(out_rows),
                absences=len(errs), refused=mismatches,
                windows=manifests), indent=2), encoding="utf-8")
            print(f"[hawkes] manifest written to {manifest_out}")

        if not write:
            print("\n[hawkes] DRY RUN — nothing written. Re-run with --write to persist.")
            return 0

        scope_id = "" if namespace == LEGACY_NAMESPACE_TOKEN else namespace
        before = await pool.fetchval(
            "SELECT count(*) FROM hawkes_output WHERE scope_id=$1", scope_id)
        async with pool.acquire() as conn:
            async with conn.transaction():
                for r in out_rows:
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
                        r["ts"], r["scope"], scope_id, r["n"], r["mts"],
                        r["neg"], r["pos"], r["asym"], r["flag"],
                        r["bmatrix"], r["alpha_beta"])
        after = await pool.fetchval(
            "SELECT count(*) FROM hawkes_output WHERE scope_id=$1", scope_id)
        print(f"\n[hawkes] E6 rows in namespace {scope_id!r}: {before:,} -> {after:,} "
              f"(inserted {after-before:,}, updated {len(out_rows)-(after-before):,})")
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
    ap.add_argument("--policy", default="fixed_at_fit_cutoff",
                    choices=list(MEMBERSHIP_POLICIES),
                    help="which membership governs a window's pooled counts "
                         "(DR-08 adopts fixed_at_fit_cutoff)")
    ap.add_argument("--namespace", default="basket_v2",
                    help="E6 scope_id to write into. The pre-T05 rows live under "
                         f"'' and are preserved; pass {LEGACY_NAMESPACE_TOKEN!r} "
                         "to overwrite them deliberately")
    ap.add_argument("--limit", type=int, default=None,
                    help="run only the most recent N refit points (for a bounded "
                         "verification run; a full regeneration omits this)")
    ap.add_argument("--manifest-out", default=None,
                    help="write the per-window manifests to this JSON file")
    ap.add_argument("--write", action="store_true",
                    help="persist to E6; omit for a dry run")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(
        a.window_days, a.refit_every, a.write, policy=a.policy,
        namespace=a.namespace, limit=a.limit, manifest_out=a.manifest_out)))
