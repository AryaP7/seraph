# C8/C9 orchestration — the timestamp inference service (T06, audit finding R01).
"""Decide at a *timestamp*, not at a date.

**The defect (R01).** The live entry point never invoked the risk engine. The
only orchestration that existed, `InferenceSession.step()`, is keyed by a
session *date*: one decision per day, the decision timestamp derived from the
calendar. Calling it repeatedly with the same date to simulate intraday
decisions would re-append the same vintage to each standardizer's ECDF, which
shrinks the uncertainty of a pillar that has not produced a single new number.

This module keeps `InferenceSession`'s numerics — the same `standardise`, the
same `KalmanReconciler`, the same pure `score()` — and moves the orchestration
onto an explicit `DecisionRequest`/`DecisionResult` pair. `CsrsPoint` travels
unchanged inside the result; nothing here widens a frozen shared type.

**Five times, kept apart.** A producer's output carries `input_end`,
`fit_train_end`, `fit_completed_at`, `fit_deployed_at` and
`emission_available_at`, and the service reads only the last one when deciding
eligibility. A model trained through yesterday but deployed tomorrow is not
available today, and saying so requires storing the five separately rather than
collapsing them into one "timestamp".

**A vintage is appended to its standardizer exactly once.** Eligibility is
re-evaluated every tick; *assimilation* is not. Polling the same RMT value at
09:20, 09:25 and 09:30 must leave the ECDF with one new observation, not three.
`StandardizerHistory` enforces this on the vintage key, so the rule holds
however often the caller ticks.

**Cadence is declared, not inferred from how often a callback fires.** Hawkes
runs at bar close, RMT and Hamilton are daily. A five-minute tick that has no
new daily vintage carries the previous one forward *with its true age*, which
is what D4's saturating noise is for — it does not re-emit it as fresh.

**The process clock is the one C8 already uses, and it was already right.**
`KalmanReconciler._advance` adds `q_proc * elapsed_bars * I`, where
`elapsed_bars` counts *open trading time* in five-minute units. Elapsed trading
time is additive, so a day partitioned into bar-by-bar predictions accumulates
exactly the same total process covariance as one daily prediction, and a
split-session break contributes none. The plan's proposed `u(t)` — completed
sessions plus the fraction of scheduled open minutes elapsed — is the same
quantity in session units: `u = elapsed_bars / BARS_PER_REGULAR_SESSION`. So
the existing verified mapping is reused rather than replaced, and
`sessions_elapsed()` exposes the session-unit view for anything that needs it.
`tests/test_t06_inference_service.py` pins the additivity property.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Literal, Mapping, Sequence

import numpy as np

from seraph.decision_support import explain
from seraph.fusion.score import score
from seraph.live.publication import (
    FeedProvenance,
    InputProvenance,
    PublicationAssessment,
    PublicationPolicy,
    assess_publication,
)
from seraph.market_calendar import DecisionClock, SessionCalendar
from seraph.orchestration.standardize import standardise
from seraph.reconciliation.kalman import KalmanReconciler
from seraph.reconciliation.time_clock import BAR_SECONDS, ReconciliationClock
from seraph.shared_types import (
    CalibrationConfig,
    FusionWeights,
    ObservedEmission,
    PillarObservation,
    UnavailableEmission,
)
from seraph.shared_types.fusion import fusion_weights_artefact_id

SERVICE_VERSION = "c8c9.inference_service/2026-10-17.1"

#: PILLAR_ORDER. Global and fixed — every Vec3, Mat3 and mask uses it.
ORDER: tuple[str, str, str] = ("hawkes", "rmt", "hamilton")

#: A regular NSE session is 09:15–15:30 = 375 minutes = 75 five-minute bars.
#: This is the only constant needed to read C8's per-bar process units as the
#: session units the plan's `u(t)` is written in.
BARS_PER_REGULAR_SESSION = 75.0

Trigger = Literal["bar_close", "daily", "refit"]
Mode = Literal["live_shadow", "historical_replay"]
AbsenceKind = Literal["structural", "transient"]

#: Declared cadence per producer. Not a guess about how often the callback
#: fires — a statement of when that producer can emit a NEW vintage at all.
DECLARED_CADENCE: Mapping[str, Trigger] = {
    "hawkes": "bar_close",
    "rmt": "daily",
    "hamilton": "daily",
}


class InferenceError(RuntimeError):
    """The request cannot be processed as stated."""


def _parse(ts: "str | datetime | None") -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts)


def _iso(ts: datetime | None) -> str | None:
    return None if ts is None else ts.isoformat()


# ----------------------------------------------------------------- vintages


@dataclass(frozen=True)
class ModelBundle:
    """A deployable fit, and the two dates that are not the same date.

    `trained_through` is what the model saw. `available_at` is when SERAPH
    could first use it. Backdating a fit to bar close to meet a latency budget
    is exactly what keeping these apart prevents.
    """

    bundle_id: str
    producer: str
    trained_through: str
    available_at: str
    manifest_hash: str = ""
    notes: str = ""

    def usable_at(self, as_of: datetime) -> bool:
        return _parse(self.available_at) <= as_of

    def describe(self) -> dict:
        return dict(bundle_id=self.bundle_id, producer=self.producer,
                    trained_through=self.trained_through,
                    available_at=self.available_at,
                    manifest_hash=self.manifest_hash, notes=self.notes or None)


@dataclass(frozen=True)
class Vintage:
    """One producer emission, with its five times kept apart.

    `value` is the raw sub-score; `None` with an `absence` is a declared
    absence, never an inferred one.
    """

    producer: str
    input_end: str                      # last observation the producer consumed
    emission_available_at: str          # when SERAPH could first read it
    value: float | None = None
    variance: float | None = None
    bundle_id: str = ""
    fit_train_end: str | None = None
    fit_completed_at: str | None = None
    fit_deployed_at: str | None = None
    absence: AbsenceKind | None = None
    absence_reason: str = "no_data_coverage"
    quality: str = "ok"
    coverage: float | None = None

    def __post_init__(self) -> None:
        if self.producer not in ORDER:
            raise InferenceError(
                f"unknown producer {self.producer!r}; the three pillars are "
                f"{ORDER} and that order is fixed")
        if self.value is None and self.absence is None:
            raise InferenceError(
                f"{self.producer}: a vintage with no value must declare its "
                f"absence as 'structural' or 'transient'. Absence type is "
                f"never inferred — structural drops the pillar from the D2 "
                f"mask and transient does not")
        if self.value is not None and not np.isfinite(self.value):
            raise InferenceError(f"{self.producer}: non-finite vintage value")

    @property
    def key(self) -> str:
        """Vintage identity: what makes this a *new* observation.

        Two polls of the same producer state share a key and are assimilated
        once. A genuinely new emission has a later `input_end`.
        """
        return f"{self.producer}@{self.input_end}#{self.bundle_id}"

    def eligible_at(self, as_of: datetime) -> bool:
        return (self.value is not None
                and _parse(self.emission_available_at) <= as_of)

    def describe(self) -> dict:
        return dict(producer=self.producer, input_end=self.input_end,
                    emission_available_at=self.emission_available_at,
                    fit_train_end=self.fit_train_end,
                    fit_completed_at=self.fit_completed_at,
                    fit_deployed_at=self.fit_deployed_at,
                    bundle_id=self.bundle_id or None,
                    value=self.value, variance=self.variance,
                    absence=self.absence, absence_reason=self.absence_reason,
                    quality=self.quality, coverage=self.coverage,
                    vintage_key=self.key)


class DeploymentRegistry:
    """Which bundles exist, and from when each may be used."""

    def __init__(self, bundles: "Sequence[ModelBundle]" = ()) -> None:
        self._by_id: dict[str, ModelBundle] = {}
        for bundle in bundles:
            self.register(bundle)

    def register(self, bundle: ModelBundle) -> None:
        existing = self._by_id.get(bundle.bundle_id)
        if existing is not None and existing != bundle:
            raise InferenceError(
                f"bundle {bundle.bundle_id} is already registered with "
                f"different content; a bundle id is immutable")
        self._by_id[bundle.bundle_id] = bundle

    def get(self, bundle_id: str) -> ModelBundle | None:
        return self._by_id.get(bundle_id)

    def usable(self, bundle_id: str, as_of: datetime) -> bool:
        bundle = self._by_id.get(bundle_id)
        return bool(bundle and bundle.usable_at(as_of))

    def reason_unusable(self, bundle_id: str, as_of: datetime) -> str | None:
        if not bundle_id:
            return None
        bundle = self._by_id.get(bundle_id)
        if bundle is None:
            return f"bundle {bundle_id} is not registered"
        if not bundle.usable_at(as_of):
            return (f"bundle {bundle_id} becomes available at "
                    f"{bundle.available_at}, which is after this decision")
        return None

    def describe(self) -> list[dict]:
        return [b.describe() for b in sorted(self._by_id.values(),
                                             key=lambda b: b.bundle_id)]


# ------------------------------------------------------------ standardizer


class StandardizerHistory:
    """Per-pillar ECDF history that assimilates each vintage exactly once.

    The five-year window is measured in *calendar* years on the vintage's own
    information timestamp, which is what `InferenceSession` did; the policy id
    travels on the result so a later change is visible rather than silent.
    """

    policy_id = "ecdf_5y_calendar_by_input_end/2026-10-17.1"

    def __init__(self, window_years: int = 5) -> None:
        self.window_years = window_years
        self._values: dict[str, list[tuple[str, float]]] = {p: [] for p in ORDER}
        self._seen: dict[str, set[str]] = {p: set() for p in ORDER}

    def window(self, pillar: str, as_of: datetime) -> list[float]:
        lower = f"{as_of.year - self.window_years:04d}{as_of.isoformat()[4:10]}"
        past = self._values[pillar]
        past[:] = [(k, v) for k, v in past if k[:10] >= lower]
        return [v for _, v in past]

    def assimilate(self, vintage: Vintage) -> bool:
        """Append this vintage if it is new. Returns whether it was appended."""
        if vintage.value is None:
            return False
        seen = self._seen[vintage.producer]
        if vintage.key in seen:
            return False
        seen.add(vintage.key)
        self._values[vintage.producer].append(
            (vintage.input_end, float(vintage.value)))
        self._values[vintage.producer].sort(key=lambda kv: kv[0])
        return True

    def observations(self, pillar: str) -> int:
        return len(self._values[pillar])

    def snapshot(self) -> dict:
        return dict(policy_id=self.policy_id, window_years=self.window_years,
                    values={p: [list(kv) for kv in v]
                            for p, v in self._values.items()},
                    seen={p: sorted(v) for p, v in self._seen.items()})

    @classmethod
    def restore(cls, payload: dict) -> "StandardizerHistory":
        out = cls(window_years=int(payload.get("window_years", 5)))
        for pillar, values in payload.get("values", {}).items():
            out._values[pillar] = [(k, float(v)) for k, v in values]
        for pillar, seen in payload.get("seen", {}).items():
            out._seen[pillar] = set(seen)
        return out


# --------------------------------------------------------- request/result


@dataclass(frozen=True)
class DecisionRequest:
    decision_id: str
    as_of: datetime
    trigger: Trigger
    mode: Mode
    input_batch_ids: tuple[str, ...] = ()
    universe_snapshot_id: str = ""
    pipeline_version: str = SERVICE_VERSION
    model_bundle_id: str = ""
    standardizer_policy_id: str = StandardizerHistory.policy_id

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise InferenceError(
                f"decision {self.decision_id}: as_of must be timezone-aware "
                f"and IST-explicit, never naive")
        if len(set(self.input_batch_ids)) != len(self.input_batch_ids):
            raise InferenceError(
                f"decision {self.decision_id}: input_batch_ids repeat; a batch "
                f"identity must be unique within one decision")

    def describe(self) -> dict:
        return dict(decision_id=self.decision_id, as_of=self.as_of.isoformat(),
                    trigger=self.trigger, mode=self.mode,
                    input_batch_ids=list(self.input_batch_ids),
                    universe_snapshot_id=self.universe_snapshot_id,
                    pipeline_version=self.pipeline_version,
                    model_bundle_id=self.model_bundle_id,
                    standardizer_policy_id=self.standardizer_policy_id)


@dataclass(frozen=True)
class DecisionResult:
    request: DecisionRequest
    computed_at: datetime
    csrs: object | None
    pillar_diagnostics: dict
    reconciled_state: object | None
    input_provenance: tuple[dict, ...]
    publication: PublicationAssessment
    state_after_id: str
    warnings: tuple[str, ...] = ()
    explanation: dict | None = None
    duplicate_of: str | None = None

    def describe(self) -> dict:
        return dict(
            request=self.request.describe(),
            computed_at=self.computed_at.isoformat(),
            csrs=(self.csrs.model_dump() if self.csrs is not None else None),
            reconciled=(self.reconciled_state.model_dump()
                        if self.reconciled_state is not None else None),
            pillar_diagnostics=self.pillar_diagnostics,
            input_provenance=list(self.input_provenance),
            publication=self.publication.describe(),
            state_after_id=self.state_after_id,
            warnings=list(self.warnings),
            explanation=self.explanation,
            duplicate_of=self.duplicate_of,
        )


@dataclass(frozen=True)
class StateSnapshot:
    """Everything needed to resume, plus what it must match to be restorable.

    R05: `restore()` used to validate `pipeline_version` and `calendar_id`
    only, so a service rebuilt with a DIFFERENT process-noise constant or a
    different set of fusion weights resumed from the old filter state
    silently. The numbers carried on, computed under one configuration and
    continued under another, with nothing in the record saying so. Neither
    `q_proc` nor `weights` was even in the payload, so no caller could have
    detected it either.

    `config_id` closes that. It is a hash over everything that DEFINES the
    state rather than merely accompanying it: the process noise, the fusion
    weights' artefact id, the standardizer policy, the declared cadence, the
    warmup threshold, and the CONTENT hash of each deployed model bundle
    rather than its label -- the audit is explicit that a bundle id is a
    name, and a name can be reused over different bytes.
    """

    state_id: str
    pipeline_version: str
    as_of: str | None
    filter_state: dict
    standardizer: dict
    vintages: dict
    decisions: int
    calendar_id: str = ""
    bundle_ids: tuple[str, ...] = ()
    #: Fingerprint of the state-defining configuration (R05). Empty only in
    #: a snapshot written before this field existed, which `restore()`
    #: refuses rather than accepting as "no configuration to check".
    config_id: str = ""
    #: The inputs to `config_id`, kept in the payload so a mismatch can be
    #: EXPLAINED instead of only detected. A bare "configuration differs"
    #: sends the operator reading source to find out which part.
    config: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return dict(state_id=self.state_id,
                    pipeline_version=self.pipeline_version, as_of=self.as_of,
                    decisions=self.decisions, calendar_id=self.calendar_id,
                    bundle_ids=list(self.bundle_ids),
                    config_id=self.config_id, config=dict(self.config),
                    standardizer_observations={
                        p: len(v) for p, v in
                        self.standardizer.get("values", {}).items()})


def sessions_elapsed(clock: ReconciliationClock, start: datetime,
                     end: datetime) -> float:
    """The plan's `u(t)` in session units: open trading time, not wall time.

    Completed sessions plus the fraction of scheduled open minutes elapsed in
    the current one. A split-session break adds nothing, because the clock
    counts only the declared windows.
    """
    return clock.elapsed_bars(start, end) / BARS_PER_REGULAR_SESSION


# ------------------------------------------------------------- the service


class InferenceService:
    """Timestamp-keyed orchestration over the unchanged pillar numerics."""

    def __init__(self, *, session_dates: "Sequence[str]",
                 decision_clock: DecisionClock | None = None,
                 weights: FusionWeights | None = None,
                 deployments: DeploymentRegistry | None = None,
                 cadence: "Mapping[str, Trigger] | None" = None,
                 warmup_observations: int = 0,
                 q_proc: float = 1e-3) -> None:
        self.session_strings = tuple(session_dates)
        dates = [date.fromisoformat(d) for d in self.session_strings]
        self.clock = decision_clock or DecisionClock(
            SessionCalendar(session_dates=frozenset(self.session_strings)))
        self._hours = self.clock.calendar.hours_map()
        self._q_proc = float(q_proc)
        self.filter = KalmanReconciler(session_dates=dates,
                                       session_hours=self._hours,
                                       q_proc=self._q_proc)
        self.process_clock = ReconciliationClock(
            session_dates=frozenset(dates), session_hours=self._hours)
        self.standardizer = StandardizerHistory()
        self.deployments = deployments or DeploymentRegistry()
        self.cadence = dict(cadence or DECLARED_CADENCE)
        self.warmup_observations = int(warmup_observations)
        self.weights = weights or _uniform_weights()
        self._last_as_of: datetime | None = None
        self._results: dict[str, DecisionResult] = {}
        self._latest: dict[str, Vintage] = {}
        self._assimilated: dict[str, str] = {}      # pillar -> vintage key
        self._last_rank: dict[str, float] = {}
        self._decisions = 0

    # ------------------------------------------------------------ warm start

    def warm_start(self, history: "Sequence[Vintage]", *,
                   cutoff: datetime) -> StateSnapshot:
        """Assimilate everything available strictly before `cutoff`.

        Warm start is an ECDF and filter prior, not a decision: nothing is
        published from it and no `DecisionResult` is produced. A vintage that
        only becomes available at or after the cutoff is left for the first
        real tick, so warm start cannot smuggle future information in.
        """
        if self._decisions:
            raise InferenceError(
                "warm_start must run before the first decision; restarting an "
                "already-running service is restore(), not warm_start()")

        # R03. This used to assimilate into the standardizer, set `_latest`
        # and mark `_assimilated` -- and never touch `self.filter`. So the
        # ECDF was warm, the vintages were recorded as CONSUMED, and the
        # Kalman state was still at its cold prior. `process()` then skipped
        # them (they are already assimilated) and the first real decision ran
        # on an uninitialised filter whose `x` and `P` had seen nothing,
        # reporting a confident-looking state built from no history. A cold
        # warm-start and an equivalent chronological replay produced
        # different states from the same inputs.
        #
        # The filter is now driven through the same predict/update path a
        # live tick uses, in observation order, one batch per distinct
        # `input_end`. No decision is produced and nothing is published: this
        # is a prior, and `_decisions` stays at zero.
        eligible = [v for v in sorted(history,
                                      key=lambda v: (v.input_end,
                                                     v.emission_available_at))
                    if _parse(v.emission_available_at) < cutoff
                    and v.value is not None]

        batches: dict[str, list[Vintage]] = {}
        for vintage in eligible:
            batches.setdefault(vintage.input_end, []).append(vintage)

        for input_end in sorted(batches):
            observed = _parse(input_end)
            emissions = []
            for vintage in batches[input_end]:
                # The SAME ranking the live path uses: the standardizer's
                # window as it stood at this observation, then `standardise`.
                # Ranking against the window AS OF this batch is what makes a
                # warm start equal to a chronological replay -- using the
                # final window for every historical point would standardise
                # 2015 against 2026 and leak the future into the prior.
                window = self.standardizer.window(vintage.producer, observed)
                rank, variance, _ = standardise(
                    vintage.value, window=window,
                    raw_variance=vintage.variance, pillar=vintage.producer)
                self.standardizer.assimilate(vintage)
                self._latest[vintage.producer] = vintage
                self._assimilated[vintage.producer] = vintage.key
                self._last_rank[vintage.producer] = float(rank)
                emissions.append(ObservedEmission(obs=PillarObservation(
                    pillar=vintage.producer, ts=input_end,
                    tau=vintage.input_end, value=rank,
                    estimation_variance=variance)))
            if not emissions:
                continue
            state = self.filter.update(emissions)
            if state.status != "ok":
                raise InferenceError(
                    f"warm start could not assimilate the batch observing "
                    f"through {input_end}: {state.error}")

        # `_last_as_of` stays None on purpose: no DECISION has happened, so
        # the first live decision is not ordered against a warm-start batch.
        return self.snapshot()

    @property
    def warmup_complete(self) -> bool:
        if self.warmup_observations <= 0:
            return True
        return all(self.standardizer.observations(p) >= self.warmup_observations
                   for p in ORDER)

    # --------------------------------------------------------------- process

    def process(self, request: DecisionRequest, *,
                vintages: "Sequence[Vintage]" = (),
                feed: FeedProvenance | None = None,
                calendar_verified: bool = True,
                now: datetime | None = None,
                policy: PublicationPolicy | None = None) -> DecisionResult:
        """Run one decision. Idempotent on `decision_id`."""
        existing = self._results.get(request.decision_id)
        if existing is not None:
            if existing.request != request:
                raise InferenceError(
                    f"decision {request.decision_id} was already processed with "
                    f"a different request; a decision id is immutable")
            return replace(existing, duplicate_of=request.decision_id)

        if self._last_as_of is not None and request.as_of < self._last_as_of:
            raise InferenceError(
                f"decision {request.decision_id} is timestamped "
                f"{request.as_of.isoformat()}, before the previous decision at "
                f"{self._last_as_of.isoformat()}: decisions are ordered")

        now = now or request.as_of
        warnings: list[str] = []
        diagnostics: dict[str, dict] = {}

        # 1. Admit vintages.
        #
        # Three outcomes, kept distinct because they mean different things:
        #
        #   * not yet available, or from a bundle not yet deployed — the
        #     vintage is WITHHELD. The previous eligible vintage stays in
        #     force and ages; D4's saturating noise is what makes that safe.
        #     Declaring an absence here instead would throw away a pillar that
        #     is merely a few minutes behind.
        #   * available and carrying a value — it replaces the previous one.
        #   * available and declaring an absence — it ALSO replaces the
        #     previous one. "I cannot emit" is information from the producer,
        #     not silence, and a structural absence has to reach the D2 mask.
        # R02 — the four instants, kept apart (DR-11).
        #
        #   input_end              when the WORLD produced the information
        #   emission_available_at  when SERAPH could first READ it
        #   as_of                  the decision cutoff (deterministic)
        #   now                    wall clock at computation
        #
        # The rule used to be `emission_available_at > as_of` -> withheld,
        # with `as_of` set by the caller to the bar end. A producer cannot
        # emit a bar-derived estimate until the bar is complete, so a normal
        # one-second processing delay made `emission_available_at` later than
        # the bar end on EVERY bar: the vintage was withheld every time, the
        # previous one carried forward and aged forever, and the pillar never
        # updated. Nothing failed loudly; the score simply stopped moving.
        #
        # The fix is in the CUTOFF, not in this comparison. `as_of` is now
        # the bar end plus a declared allowance (`engine_adapter`), so a
        # producer emitting at its normal latency is readable BY the cutoff
        # and is admitted. The availability test therefore stays against
        # `as_of` -- the decision's own cutoff -- and not against `now`:
        #
        #   * `input_end > as_of`              -> LOOKAHEAD. Refused.
        #   * `emission_available_at > as_of`  -> not readable at the cutoff.
        #                                         Withheld, carried forward.
        #
        # Testing availability against the wall clock instead was tried and
        # is wrong: `now` is the tick instant, which under replay can precede
        # the bar timestamps entirely, so every vintage was withheld and a
        # 40-day-old warm-start value carried forward into a confident score.
        # The publication gate caught it, but a score computed from stale
        # inputs is exactly what R02 exists to prevent.
        #
        # Both conditions are functions of `as_of`, which is a function of
        # the bar end, so a replay of the same bars reproduces the same
        # admissions and the same decision identity.
        withheld: dict[str, Vintage] = {}
        for vintage in sorted(vintages, key=lambda v: (v.input_end,
                                                       v.emission_available_at)):
            producer = vintage.producer
            reason = self.deployments.reason_unusable(vintage.bundle_id,
                                                      request.as_of)
            if reason:
                warnings.append(
                    f"{producer}: {reason}; its vintage was withheld and the "
                    f"previous one carried forward")
                withheld[producer] = vintage
                continue
            if _parse(vintage.input_end) > request.as_of:
                # Causality. Skew tolerance does not relax this.
                warnings.append(
                    f"{producer}: vintage observes through {vintage.input_end}, "
                    f"after this decision's cutoff {request.as_of.isoformat()}; "
                    f"REFUSED as lookahead and the previous one carried forward")
                withheld[producer] = vintage
                continue
            if _parse(vintage.emission_available_at) > request.as_of:
                warnings.append(
                    f"{producer}: vintage {vintage.input_end} becomes readable "
                    f"at {vintage.emission_available_at}, after this decision's "
                    f"cutoff {request.as_of.isoformat()}; withheld and the "
                    f"previous one carried forward")
                withheld[producer] = vintage
                continue
            # R04 — a late-arriving OLDER vintage must not replace a newer
            # input. The loop used to assign unconditionally, having sorted by
            # `emission_available_at` alone, so the emission that ARRIVED last
            # won regardless of which one OBSERVED last: a producer re-emitting
            # a stale window silently rolled the pillar backwards. A correction
            # to the same `input_end` is a legitimate revision and still
            # applies; an earlier `input_end` does not.
            incumbent = self._latest.get(producer)
            if incumbent is not None and vintage.input_end < incumbent.input_end:
                warnings.append(
                    f"{producer}: vintage observing through {vintage.input_end} "
                    f"arrived after one observing through "
                    f"{incumbent.input_end}; the newer observation stands and "
                    f"the late older one is recorded, not applied")
                withheld[producer] = vintage
                continue
            self._latest[producer] = vintage

        # 2. Build the emission batch from the latest eligible vintage each.
        ts = request.as_of.isoformat()
        emissions = []
        provenance: list[InputProvenance] = []
        for pillar in ORDER:
            vintage = self._latest.get(pillar)
            entry, emission, prov = self._emission_for(
                pillar, vintage, ts, request.as_of, withheld.get(pillar))
            diagnostics[pillar] = entry
            if emission is not None:
                emissions.append(emission)
            if not entry["eligible"]:
                # Say the absence out loud, in the archive path's own wording.
                # An unavailable pillar that leaves no trace in the warnings is
                # the kind of silence this system is supposed to not produce.
                warnings.append(
                    f"{pillar}: {entry['absence_reason']} "
                    f"[{entry['absence']}]")
            warnings.extend(entry.get("warnings") or ())
            provenance.append(prov)

        # 3. C8 predict/update, then the pure C9 score. Unchanged numerics.
        #
        # A pillar with nothing new to say is OMITTED from the batch rather
        # than re-emitted with its old tau. C8 would ignore a repeated tau
        # anyway — but it would ignore it with a STALE_OBSERVATION warning on
        # every tick, and a daily pillar at five-minute cadence would raise
        # that warning seventy-five times a day for behaving correctly.
        # Omission is the same arithmetic without the false alarm: the filter
        # keeps the pillar's status and D4 ages it toward saturation.
        if emissions:
            state = self.filter.update(emissions)
        else:
            state = self.filter.predict(ts)
        if state.status != "ok":
            raise InferenceError(str(state.error))
        warnings.extend(w.message for w in state.warnings)

        # Omitting a carried-forward pillar from the batch also omits C8's
        # NOISE_SATURATED warning for it, even though the mask still excludes
        # it. The exclusion must not go unsaid: a pillar silently dropping out
        # of the composite is exactly the kind of invisible degradation the
        # mask is meant to make visible.
        for i, pillar in enumerate(ORDER):
            if (diagnostics[pillar].get("carried_forward")
                    and state.value.noise_saturated[i]):
                warnings.append(
                    f"{pillar}: the carried-forward vintage "
                    f"{diagnostics[pillar]['vintage']['input_end']} is stale "
                    f"enough that R has reached its ceiling; the pillar is "
                    f"excluded from the mask")
                diagnostics[pillar]["noise_saturated"] = True

        result = score(reconciled=state.value, xi=(1 / 3, 1 / 3, 1 / 3),
                       weights=self.weights, xi_mode="uniform")
        point = result.value if result.status == "ok" else None
        if point is None:
            warnings.append(
                "CSRS unavailable: no eligible pillar observation at this "
                "decision timestamp")

        # 4. The single publication gate. Diagnostics survive a refusal.
        assessment = assess_publication(
            mode=request.mode, csrs=point,
            feed=feed or FeedProvenance(),
            as_of=request.as_of, now=now,
            # "partial", not "failed": the computation ran and produced
            # diagnostics; what is missing is an eligible observation, which
            # `no_valid_score` and `empty_information_set` already name.
            computation="ready" if point is not None else "partial",
            warmup_complete=self.warmup_complete,
            calendar_verified=calendar_verified,
            required_inputs=tuple(provenance),
            has_eligible_information=any(
                d["eligible"] for d in diagnostics.values()),
            policy=policy)

        self._last_as_of = request.as_of
        self._decisions += 1
        snapshot = self.snapshot()
        decision = DecisionResult(
            request=request, computed_at=now, csrs=point,
            pillar_diagnostics=diagnostics, reconciled_state=state.value,
            input_provenance=tuple(_provenance_dict(p) for p in provenance),
            publication=assessment, state_after_id=snapshot.state_id,
            warnings=tuple(sorted(set(warnings))),
            explanation=(explain(point).value if point is not None else None))
        self._results[request.decision_id] = decision
        return decision

    # ------------------------------------------------------------- internals

    def _emission_for(self, pillar: str, vintage: "Vintage | None", ts: str,
                      as_of: datetime, withheld: "Vintage | None" = None):
        cadence = self.cadence.get(pillar, "daily")
        if vintage is None or not vintage.eligible_at(as_of):
            absence: AbsenceKind = "transient"
            reason = "no_data_coverage"
            if vintage is not None and vintage.absence is not None:
                absence, reason = vintage.absence, vintage.absence_reason
            entry = dict(pillar=pillar, cadence=cadence, eligible=False,
                         absence=absence, absence_reason=reason,
                         vintage=vintage.describe() if vintage else None,
                         withheld=withheld.describe() if withheld else None,
                         assimilated=False, rank=None)
            emission = UnavailableEmission(pillar=pillar, ts=ts,
                                           absence=absence, reason=reason)
            prov = InputProvenance(
                name=pillar,
                observed_at=_parse(vintage.input_end) if vintage else None,
                received_at=(_parse(vintage.emission_available_at)
                             if vintage else None),
                mandatory=False,
                coverage=vintage.coverage if vintage else None,
                quality=vintage.quality if vintage else "unavailable")
            return entry, emission, prov

        # A vintage already assimilated is carried forward at its true age:
        # eligibility is re-evaluated each tick, assimilation is not.
        fresh = self._assimilated.get(pillar) != vintage.key
        if not fresh:
            entry = dict(pillar=pillar, cadence=cadence, eligible=True,
                         absence=None, absence_reason=None,
                         vintage=vintage.describe(),
                         withheld=withheld.describe() if withheld else None,
                         carried_forward=True, assimilated=False,
                         rank=self._last_rank.get(pillar),
                         ecdf_observations=self.standardizer.observations(pillar),
                         note=("already assimilated; the filter carries it "
                               "forward and D4 ages it"))
            prov = InputProvenance(
                name=pillar, observed_at=_parse(vintage.input_end),
                received_at=_parse(vintage.emission_available_at),
                mandatory=False, coverage=vintage.coverage,
                quality=vintage.quality)
            return entry, None, prov

        window = self.standardizer.window(pillar, as_of)
        rank, variance, std_warnings = standardise(
            vintage.value, window=window, raw_variance=vintage.variance,
            pillar=pillar)
        self.standardizer.assimilate(vintage)
        self._assimilated[pillar] = vintage.key
        self._last_rank[pillar] = float(rank)
        entry = dict(pillar=pillar, cadence=cadence, eligible=True,
                     absence=None, absence_reason=None,
                     vintage=vintage.describe(),
                     withheld=withheld.describe() if withheld else None,
                     carried_forward=False, assimilated=True,
                     rank=float(rank), variance=variance,
                     ecdf_observations=self.standardizer.observations(pillar),
                     warnings=[w.message for w in std_warnings])
        emission = ObservedEmission(obs=PillarObservation(
            pillar=pillar, ts=ts, tau=vintage.input_end, value=rank,
            estimation_variance=variance))
        prov = InputProvenance(
            name=pillar, observed_at=_parse(vintage.input_end),
            received_at=_parse(vintage.emission_available_at),
            mandatory=False, coverage=vintage.coverage,
            quality=vintage.quality)
        return entry, emission, prov

    # ------------------------------------------------------ snapshot/restore

    def config_fingerprint(self) -> tuple[str, dict]:
        """The state-defining configuration, and its hash (R05).

        What belongs here is anything that changes what the SAME inputs
        would produce. `q_proc` and the fusion weights do; a log level does
        not. Model bundles contribute their `manifest_hash` -- their CONTENT
        -- not their `bundle_id`, because an id is a label and a label can
        be reused over different bytes.
        """
        config = dict(
            q_proc=self._q_proc,
            weights_artefact_id=getattr(self.weights, "artefact_id", ""),
            standardizer_policy_id=StandardizerHistory.policy_id,
            standardizer_window_years=self.standardizer.window_years,
            cadence={p: self.cadence.get(p) for p in ORDER},
            warmup_observations=self.warmup_observations,
            pillar_order=list(ORDER),
            bundles=sorted(
                (b.get("bundle_id", ""), b.get("manifest_hash", ""))
                for b in self.deployments.describe()),
        )
        digest = hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        return digest, config

    def snapshot(self) -> StateSnapshot:
        filter_state = _filter_state(self.filter)
        config_id, config = self.config_fingerprint()
        payload = dict(
            pipeline_version=SERVICE_VERSION,
            as_of=_iso(self._last_as_of),
            filter_state=filter_state,
            standardizer=self.standardizer.snapshot(),
            vintages={p: (v.describe() if v else None)
                      for p, v in self._latest.items()},
            assimilated=dict(self._assimilated),
            decisions=self._decisions,
            calendar_id=_calendar_id(self.session_strings),
            bundle_ids=sorted(b["bundle_id"]
                              for b in self.deployments.describe()),
            config_id=config_id,
            config=config,
        )
        state_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        return StateSnapshot(
            state_id=state_id, pipeline_version=SERVICE_VERSION,
            as_of=payload["as_of"], filter_state=filter_state,
            standardizer=payload["standardizer"], vintages=payload["vintages"],
            decisions=self._decisions, calendar_id=payload["calendar_id"],
            bundle_ids=tuple(payload["bundle_ids"]),
            config_id=config_id, config=config)

    def restore(self, snapshot: StateSnapshot) -> None:
        """Resume from a snapshot, or refuse and say what did not match.

        Never a deserialization of arbitrary estimator internals: the state is
        plain JSON-shaped data, and the pipeline version and calendar identity
        must match exactly before any of it is applied.
        """
        if snapshot.pipeline_version != SERVICE_VERSION:
            raise InferenceError(
                f"snapshot was written by {snapshot.pipeline_version} and this "
                f"service is {SERVICE_VERSION}; rebuild by warm start rather "
                f"than resuming across a version change")
        expected = _calendar_id(self.session_strings)
        if snapshot.calendar_id and snapshot.calendar_id != expected:
            raise InferenceError(
                "snapshot was taken against a different session calendar; "
                "resuming would silently change the process clock")

        # R05 — the configuration that DEFINES this state must match.
        config_id, config = self.config_fingerprint()
        if not snapshot.config_id:
            raise InferenceError(
                "snapshot carries no configuration fingerprint, so it was "
                "written before this check existed and there is no way to "
                "tell whether its process noise, fusion weights or model "
                "bundle contents match this service. Rebuild by warm start: "
                "an unverifiable resume is the defect, not the inconvenience")
        if snapshot.config_id != config_id:
            differing = sorted(
                key for key in set(config) | set(snapshot.config or {})
                if config.get(key) != (snapshot.config or {}).get(key))
            raise InferenceError(
                f"snapshot was written under configuration "
                f"{snapshot.config_id} and this service is {config_id}; "
                f"these differ: {', '.join(differing) or 'unknown'}. "
                f"Resuming would continue a filter state computed under one "
                f"configuration as though it had been computed under this "
                f"one. Rebuild by warm start.")
        self.standardizer = StandardizerHistory.restore(snapshot.standardizer)
        _restore_filter(self.filter, snapshot.filter_state)
        self._last_as_of = _parse(snapshot.as_of)
        self._decisions = int(snapshot.decisions)
        self._latest = {}
        self._assimilated = {}
        self._last_rank = {}
        for pillar, described in (snapshot.vintages or {}).items():
            if not described:
                continue
            vintage = _vintage_from(described)
            self._latest[pillar] = vintage
            self._assimilated[pillar] = vintage.key


# ------------------------------------------------------------------ helpers


def _uniform_weights() -> FusionWeights:
    w = ((1 / 3, 1 / 3, 1 / 3),) * 3
    cfg = CalibrationConfig(epochs=(), kappa_miss=1, kappa_fa=1,
                            mask_profile=(True, True, False))
    return FusionWeights(artefact_id=fusion_weights_artefact_id(w, cfg),
                         calibrated_on=cfg, w=w)


def _calendar_id(sessions: "Sequence[str]") -> str:
    return hashlib.sha256("|".join(sessions).encode()).hexdigest()[:16]


def _provenance_dict(p: InputProvenance) -> dict:
    return dict(name=p.name, observed_at=_iso(p.observed_at),
                received_at=_iso(p.received_at), mandatory=p.mandatory,
                coverage=p.coverage, quality=p.quality)


def _vintage_from(described: dict) -> Vintage:
    return Vintage(
        producer=described["producer"], input_end=described["input_end"],
        emission_available_at=described["emission_available_at"],
        value=described.get("value"), variance=described.get("variance"),
        bundle_id=described.get("bundle_id") or "",
        fit_train_end=described.get("fit_train_end"),
        fit_completed_at=described.get("fit_completed_at"),
        fit_deployed_at=described.get("fit_deployed_at"),
        absence=described.get("absence"),
        absence_reason=described.get("absence_reason") or "no_data_coverage",
        quality=described.get("quality", "ok"),
        coverage=described.get("coverage"))


def _filter_state(filt: KalmanReconciler) -> dict:
    """C8's `x/P/tau/mask` as plain data — no pickle, ever."""
    return dict(
        x=[float(v) for v in filt._x],
        P=[[float(v) for v in row] for row in filt._P],
        tau=[t.isoformat() if t is not None else None for t in filt._tau],
        r0=[None if r is None else float(r) for r in filt._r0],
        status=list(filt._status),
        ts=filt._ts.isoformat() if filt._ts is not None else None,
    )


def _restore_filter(filt: KalmanReconciler, state: dict) -> None:
    filt._x = np.asarray(state["x"], dtype=float)
    filt._P = np.asarray(state["P"], dtype=float)
    filt._tau = [_parse(t) for t in state["tau"]]
    filt._r0 = [None if r is None else float(r) for r in state["r0"]]
    filt._status = list(state["status"])
    filt._ts = _parse(state["ts"])
