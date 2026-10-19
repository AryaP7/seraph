# C8/C9 orchestration — archive compatibility for the timestamp service (T06).
"""Drive `InferenceService` from the date-cadence archive input contract.

T06 moves orchestration from a session *date* to a decision *timestamp*. The
plan requires a compatibility adapter rather than a replacement, and requires
the comparison to be made **at the same date cadence and configuration** — an
amended source run may legitimately differ, and would need its own manifest.

So this adapter takes exactly the `originals` mapping that
`InferenceSession.step()` takes (PRODUCT-CONTRACTS §3: per pillar,
`score_eligible`, `value`, `information_timestamp`, or a declared `absence`)
and turns it into the `Vintage` objects the service consumes. One decision per
session, timestamped by the same `DecisionClock`.

Two translations carry the meaning across, and neither is cosmetic:

* **`information_timestamp` becomes both `input_end` and
  `emission_available_at`.** The archive contract has one time per
  observation and treats it as "when this became knowable", which is what the
  service reads for eligibility. Saying so explicitly is the point of the
  service's five separate times: the archive simply does not distinguish them,
  and the adapter must not pretend it does.
* **An ineligible entry keeps its declared absence kind.** `structural` and
  `transient` mean different things to the D2 mask, and the adapter never
  infers one from the other — the same rule the archive path already enforces.

`equivalence_report()` replays a date range through both paths and compares the
reconciled state and the composite field by field, so "the two agree" is a
printed diff rather than an assurance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from seraph.live.inference import (
    ORDER,
    DecisionRequest,
    DecisionResult,
    InferenceService,
    Vintage,
)
from seraph.market_calendar import DecisionClock, SessionCalendar

ADAPTER_VERSION = "c8c9.archive_adapter/2026-10-17.1"


def vintages_from_originals(originals: "Mapping[str, dict]") -> list[Vintage]:
    """Translate one session's archive `originals` mapping into vintages."""
    out: list[Vintage] = []
    for pillar in ORDER:
        item = originals.get(pillar)
        if item is None:
            continue
        eligible = bool(item.get("score_eligible")) and item.get("value") is not None
        if eligible:
            tau = item.get("information_timestamp")
            if not tau:
                raise ValueError(
                    f"{pillar}: an eligible archive observation needs an "
                    f"information timestamp")
            out.append(Vintage(producer=pillar, input_end=tau,
                               emission_available_at=tau,
                               value=float(item["value"]),
                               variance=item.get("variance")))
            continue
        absence = item.get("absence")
        if absence not in ("structural", "transient"):
            raise ValueError(
                f"{pillar}: an ineligible archive entry must declare absence "
                f"as 'structural' or 'transient'; absence is never inferred")
        # An absence has no information timestamp of its own in the archive
        # contract. It is known at the decision, so the decision timestamp is
        # supplied by the caller through `decision_ts`.
        out.append(Vintage(producer=pillar, input_end="",
                           emission_available_at="", absence=absence,
                           absence_reason=item.get("absence_reason",
                                                   "no_data_coverage")))
    return out


def _stamp_absences(vintages: "Sequence[Vintage]", decision_ts: str
                    ) -> list[Vintage]:
    from dataclasses import replace
    return [replace(v, input_end=decision_ts, emission_available_at=decision_ts)
            if v.value is None and not v.input_end else v for v in vintages]


@dataclass
class ArchiveReplay:
    """One decision per session, through the timestamp service."""

    session_dates: tuple[str, ...]
    decision_policy: str = "session_close"
    service: InferenceService | None = None

    def __post_init__(self) -> None:
        calendar = SessionCalendar(session_dates=frozenset(self.session_dates))
        self.clock = DecisionClock(calendar, policy=self.decision_policy)
        if self.service is None:
            self.service = InferenceService(session_dates=self.session_dates,
                                            decision_clock=self.clock)

    def step(self, day: str, originals: "Mapping[str, dict]", *,
             decision_id: str | None = None) -> DecisionResult:
        ts = self.clock.decision_timestamp(day)
        vintages = _stamp_absences(vintages_from_originals(originals), ts)
        request = DecisionRequest(
            decision_id=decision_id or f"archive:{day}",
            as_of=datetime.fromisoformat(ts), trigger="daily",
            mode="historical_replay", universe_snapshot_id="archive",
            pipeline_version=ADAPTER_VERSION)
        return self.service.process(request, vintages=vintages)


def equivalence_report(session, replay: ArchiveReplay, day: str,
                       originals: "Mapping[str, dict]", *,
                       run_id: str = "equivalence") -> dict:
    """Run one session through both paths and diff what they produced.

    `session` is an `InferenceSession`. The comparison is on the two things
    that leave the orchestration layer: the reconciled state and the composite
    point. Warnings are reported but not required to match — the timestamp
    service deliberately omits a carried-forward pillar from the batch instead
    of re-emitting it and collecting a STALE_OBSERVATION, which changes the
    warning list without changing a single number.
    """
    old = session.step(day, dict(originals), {}, run_id=run_id)
    new = replay.step(day, originals)

    old_state = old["reconciled"]
    new_state = (new.reconciled_state.model_dump()
                 if new.reconciled_state is not None else None)
    old_point = old["composite"]
    new_point = new.csrs.model_dump() if new.csrs is not None else None

    differences: list[str] = []
    for field in ("x_hat", "P", "mask", "tau_last_update", "noise_saturated",
                  "ts", "mode"):
        a = old_state.get(field) if old_state else None
        b = new_state.get(field) if new_state else None
        if _normalise(a) != _normalise(b):
            differences.append(f"reconciled.{field}: archive={a!r} service={b!r}")
    if (old_point is None) != (new_point is None):
        differences.append(
            f"composite presence: archive={old_point is not None} "
            f"service={new_point is not None}")
    elif old_point is not None:
        for field in sorted(set(old_point) | set(new_point)):
            if _normalise(old_point.get(field)) != _normalise(new_point.get(field)):
                differences.append(
                    f"composite.{field}: archive={old_point.get(field)!r} "
                    f"service={new_point.get(field)!r}")
    return dict(day=day, agrees=not differences, differences=differences,
                archive_warnings=old.get("limitations", []),
                service_warnings=list(new.warnings))


def _normalise(value):
    """Compare numbers as floats and sequences element-wise, not by type."""
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 12)
    return value
