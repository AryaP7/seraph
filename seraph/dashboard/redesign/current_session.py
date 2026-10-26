# C12 — Redesigned console: the latest completed market session.
"""What SERAPH knows about the market *now*, as opposed to a 2020 replay.

**The defect this closes.** The console opened on an archive run from
2020-04-30 because that was the only basis wired to it, so a system holding
current pillar readings and a current forecast presented a six-year-old
replay as its headline. The data was there; nothing showed it.

**What is actually current**, read rather than assumed:

* `daily_vintages` in the live store carries the newest reading per pillar —
  Hawkes and RMT computed for the last session the daily job covered,
  Hamilton as its standing structural absence.
* `prospective_forecasts` / the saved prediction state carries the forecast
  and its calibrated warning threshold for the same session.

**What is NOT available, and why.** There is no composite (CSRS) for a
current session. The fusion that would produce one lives in
`live/engine_adapter.py` and runs inside the live bar loop, which needs an
open market and a connected feed. So this surface reports the pillars it has
and says plainly that no composite exists — it does **not** fuse them here.
Computing a composite in the dashboard would put analytics in C12, which
ARCHITECTURE §1 forbids, and would create a second idea of what the CSRS is.

Nothing here fabricates, back-dates or re-stamps anything: every value
carries the `input_end` it was computed through and the
`emission_available_at` it became readable at.
"""
from __future__ import annotations

from pathlib import Path

from seraph.shared_types import PILLAR_ORDER


def latest_session(live_path, *, as_of: str | None = None) -> dict:
    """The newest readable vintage per pillar, and when each was computed.

    `as_of=None` means "everything readable now". Passing a timestamp
    applies the same availability rule the inference service uses
    (`emission_available_at <= as_of`), so this cannot show a reading the
    engine would itself have withheld.
    """
    path = Path(live_path)
    if not path.exists():
        return dict(available=False, pillars=[], reason=(
            f"no live store at {path}; the daily job writes its vintages "
            f"there"), input_end=None, computed_at=None)

    from seraph.live.store import LiveStore

    rows = {r["producer"]: r
            for r in LiveStore(path).daily_vintages(as_of=as_of)}
    if not rows:
        return dict(available=False, pillars=[], reason=(
            "the live store holds no daily vintage yet. "
            "`python scripts/run_daily.py` writes one per session"),
            input_end=None, computed_at=None)

    pillars = []
    for name in PILLAR_ORDER:
        row = rows.get(name)
        if row is None:
            pillars.append(dict(
                name=name, value=None, present=False, absence=None,
                reason=("this pillar produced no vintage for the session, "
                        "which is different from producing one and declaring "
                        "an absence"),
                input_end=None, computed_at=None, origin=None, quality=None))
            continue
        pillars.append(dict(
            name=name,
            value=row["value"] if row.get("absence") is None else None,
            present=True,
            absence=row.get("absence"),
            reason=row.get("absence_reason") or _detail_reason(row),
            input_end=row.get("input_end"),
            computed_at=row.get("computed_at"),
            emission_available_at=row.get("emission_available_at"),
            origin=row.get("origin"),
            quality=row.get("quality"),
            bundle_id=row.get("bundle_id"),
        ))

    ends = [p["input_end"] for p in pillars if p.get("input_end")]
    computed = [p["computed_at"] for p in pillars if p.get("computed_at")]
    scored = [p for p in pillars if p["value"] is not None]
    return dict(
        available=bool(scored),
        pillars=pillars,
        input_end=max(ends) if ends else None,
        computed_at=max(computed) if computed else None,
        scored=len(scored),
        reason=("" if scored else
                "every pillar declared an absence for this session"),
    )


def _detail_reason(row) -> str:
    """A reason out of the vintage's own detail, never one invented here."""
    import json

    raw = row.get("detail_json")
    if not raw:
        return ""
    try:
        detail = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    return str(detail.get("reason") or "")


def composite_status(session: dict, live_path=None) -> dict:
    """The composite for the latest scored session, or why there is none.

    This does not compute a score. `scripts/score_completed_sessions.py`
    drives the documented archive replay onto the same
    `InferenceService.process()` the live loop uses, and commits the result
    to the `replay` stream; this reads what that produced.

    **What the score is and is not.** It is a genuine CSRS from the official
    engine over the session's own vintages, carrying its own source-session
    timestamp. It is NOT a current market reading: every such decision is
    `mode="historical_replay"`, the publication gate refuses to call it
    current, and its reasons travel with it so the refusal can be read rather
    than inferred.
    """
    pillars = session.get("pillars") or []
    scored = [p for p in pillars if p["value"] is not None]
    absent = [p for p in pillars if p["value"] is None]
    missing = dict(
        value=None, available=False,
        reason=("no composite has been computed for this session. "
                "`python scripts/score_completed_sessions.py --commit` "
                "replays the daily vintages through the official engine"),
        scored=[p["name"] for p in scored],
        absent=[(p["name"], p.get("absence") or "not emitted") for p in absent])

    if live_path is None:
        return missing
    path = Path(live_path)
    if not path.exists():
        return dict(missing, reason=f"no live store at {path}")

    from seraph.live.store import LiveStore

    decision = LiveStore(path, stream_id="replay").latest_decision()
    if decision is None:
        return missing
    point = ((decision.get("payload") or {}).get("csrs")) or {}
    value = point.get("csrs")
    if not isinstance(value, (int, float)):
        return dict(missing, reason=(
            "the latest scored decision carries no numeric CSRS"))

    payload = decision.get("payload") or {}
    return dict(
        value=float(value),
        available=True,
        ci_lower=point.get("ci_lower"), ci_upper=point.get("ci_upper"),
        alert_level=point.get("alert_level"),
        variance=point.get("variance"),
        mask=point.get("mask"),
        shapley=point.get("shapley"),
        decision_id=decision.get("decision_id"),
        as_of=decision.get("as_of"),
        computed_at=decision.get("computed_at"),
        publication_state=decision.get("publication_state"),
        publishable=decision.get("publication_state") == "current",
        warnings=payload.get("warnings") or [],
        scored=[p["name"] for p in scored],
        absent=[(p["name"], p.get("absence") or "not emitted") for p in absent],
        reason="",
        note=str(payload.get("note") or ""),
    )
