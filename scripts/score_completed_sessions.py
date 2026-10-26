#!/usr/bin/env python3
# C8/C9 — score completed sessions from their own daily vintages (batch path).
"""Produce a genuine CSRS for the latest completed session, without a feed.

**The gap this closes.** SERAPH computed its pillars daily — `run_daily.py`
writes a vintage per pillar per session — but nothing ever fused them. The
fusion lived only in `live/engine_adapter.py`, which is driven by closing
bars, so a composite could be produced only while the market was open and a
feed was connected. The result was a system holding a year of real pillar
readings and no composite at all.

**This is not a new engine.** It drives `live/archive_adapter.ArchiveReplay`,
which is the documented compatibility path onto the same
`InferenceService.process()` the live loop uses: the same Kalman
reconciliation, the same `StandardizerHistory`, the same pure C9 `score()`,
the same D2 mask and the same publication gate. Nothing here computes a
number.

**Partial pillar coverage is the approved behaviour, not a workaround.** D2
is explicit that a structurally absent pillar is excluded from the mask and
the remaining weights renormalise; `_warmup_complete_at` excludes structural
absences from the warm-up requirement for the same reason. On this
installation Hamilton is a standing structural absence and Hawkes is usually
absent or stale, so most sessions score on RMT alone — and the mask records
exactly that, which is what makes the reading auditable rather than silently
degraded.

**What this does NOT claim.** Every decision is `mode="historical_replay"`,
so the publication gate refuses to call it a current market reading, and the
stream is `replay` — never `live`. A score for the last completed session is
not a statement about the market now, and the gate's own reasons travel with
it.

Usage:

    python scripts/score_completed_sessions.py                # score, report
    python scripts/score_completed_sessions.py --commit       # and persist
    python scripts/score_completed_sessions.py --since 2026-01-01
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.live.archive_adapter import ArchiveReplay          # noqa: E402
from seraph.live.store import LiveStore                        # noqa: E402

#: The replay stream. NEVER `live`: `latest_decision()` is stream-scoped
#: precisely so a replay cannot be served as the current reading.
STREAM = "replay"
SCORER_VERSION = "c9.batch_sessions/2026-10-25.1"


def read_vintages(store_path: Path, *, since: str | None = None) -> dict:
    """Daily vintages grouped by session, in the archive input contract.

    The contract (PRODUCT-CONTRACTS §3) is per pillar: `score_eligible`,
    `value`, `information_timestamp`, or a declared `absence`. A vintage that
    declared an absence keeps its KIND — `structural` and `transient` mean
    different things to the D2 mask and one is never inferred from the other.
    """
    db = sqlite3.connect(store_path)
    db.row_factory = sqlite3.Row
    try:
        rows = list(db.execute(
            "SELECT * FROM daily_vintages ORDER BY input_end"))
    finally:
        db.close()

    by_day: dict[str, dict] = defaultdict(dict)
    for row in rows:
        day = str(row["input_end"])[:10]
        if since and day < since:
            continue
        if row["absence"] is None and row["value"] is not None:
            by_day[day][row["producer"]] = dict(
                score_eligible=True, value=float(row["value"]),
                information_timestamp=row["input_end"])
        else:
            by_day[day][row["producer"]] = dict(
                score_eligible=False, value=None,
                information_timestamp=row["input_end"],
                absence=row["absence"] or "structural",
                reason=row["absence_reason"] or "")
    return dict(by_day)


def score_sessions(by_day: dict) -> list:
    """Replay every session in order through the official service.

    Order matters and is not an implementation detail: the standardizer's
    ECDF window and the Kalman state are built by the sessions before this
    one. Scoring the latest session alone would rank it against nothing.
    """
    days = sorted(by_day)
    if not days:
        return []
    replay = ArchiveReplay(session_dates=tuple(days))
    results = []
    for day in days:
        results.append((day, replay.step(day, by_day[day])))
    return results


def describe(day: str, result) -> dict:
    point = result.csrs
    publication = result.publication
    return dict(
        session=day,
        decision_id=result.request.decision_id,
        as_of=result.request.as_of.isoformat(),
        computed_at=result.computed_at.isoformat(),
        csrs=getattr(point, "csrs", None),
        alert_level=getattr(point, "alert_level", None),
        mask=list(getattr(point, "mask", ()) or ()),
        ci_lower=getattr(point, "ci_lower", None),
        ci_upper=getattr(point, "ci_upper", None),
        variance=getattr(point, "variance", None),
        shapley=list(getattr(point, "shapley", ()) or ()),
        publishable_as_current=getattr(publication, "current_allowed", False),
        publication_label=getattr(publication, "label", None),
        publication_reasons=list(getattr(publication, "reasons", ()) or ()),
        warnings=list(result.warnings),
        scorer=SCORER_VERSION,
    )


def commit(store: LiveStore, day: str, result) -> dict:
    """Persist one decision with its OWN source-session timestamp.

    `as_of` is the session's decision timestamp, never the wall clock: a
    score for 2026-10-22 that carried today's date would be the one
    substitution this codebase's mode discipline exists to prevent.
    """
    point = result.csrs
    payload = dict(
        csrs=(point.model_dump() if point is not None else None),
        pillar_diagnostics=result.pillar_diagnostics,
        explanation=result.explanation,
        warnings=list(result.warnings),
        scorer=SCORER_VERSION,
        source="daily_vintages",
        note=("composed from the daily vintages for this session by the "
              "documented archive replay; not a live reading"),
    )
    state = dict(result.publication.describe()
                 if hasattr(result.publication, "describe") else {})
    return store.commit_decision(
        decision_id=result.request.decision_id,
        as_of=result.request.as_of.isoformat(),
        computed_at=result.computed_at.isoformat(),
        payload=payload,
        publication_state=("current" if getattr(
            result.publication, "current_allowed", False) else "withheld"),
        state=state,
        pipeline_version=SCORER_VERSION)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=Path(os.environ.get(
        "SERAPH_LIVE_STORE", ROOT / "prototype_runs" / "live.sqlite")))
    parser.add_argument("--since", help="only replay sessions from this date")
    parser.add_argument("--commit", action="store_true",
                        help="persist the decisions (idempotent per id)")
    parser.add_argument("--json", action="store_true",
                        help="print the latest decision as JSON")
    args = parser.parse_args(argv)

    if not args.store.exists():
        print(f"[score] no live store at {args.store}; "
              f"`python scripts/run_daily.py` writes the vintages it reads")
        return 2

    by_day = read_vintages(args.store, since=args.since)
    if not by_day:
        print("[score] no daily vintage to score")
        return 2

    results = score_sessions(by_day)
    scored = [(d, r) for d, r in results if r.csrs is not None]
    print(f"[score] replayed {len(results)} session(s); "
          f"{len(scored)} produced a composite")

    if not scored:
        print("[score] no session produced a composite. Every pillar "
              "declared an absence, which is a result, not a failure.")
        return 1

    day, latest = scored[-1]
    shown = describe(day, latest)
    print(f"[score] latest  session {shown['session']} · as_of {shown['as_of']}")
    print(f"[score]   CSRS  {shown['csrs']:.6f}  ({shown['alert_level']})")
    print(f"[score]   mask  {shown['mask']}  (hawkes, rmt, hamilton)")
    print(f"[score]   CI    [{shown['ci_lower']:.4f}, {shown['ci_upper']:.4f}]")
    print(f"[score]   {shown['publication_label']} "
          f"— {', '.join(shown['publication_reasons']) or 'no reasons'}")
    for warning in shown["warnings"]:
        print(f"[score]   warning: {warning}")

    if args.commit:
        store = LiveStore(args.store, stream_id=STREAM)
        committed = 0
        for d, r in scored:
            commit(store, d, r)
            committed += 1
        print(f"[score] committed {committed} decision(s) to stream "
              f"'{STREAM}' in {args.store.name}")
        print("[score] these are REPLAY decisions. `latest_decision()` is "
              "stream-scoped, so they can never be served as a live reading.")

    if args.json:
        print(json.dumps(shown, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
