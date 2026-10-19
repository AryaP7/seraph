# Live — publication policy (T01; audit finding R02)
"""One function decides whether anything may be shown as a current reading.

The defect this replaces
------------------------
Two places independently decided "is this current", and both were wrong:

* `LiveLoop` checked recency and `feed.is_live` but **not whether a score
  existed**. A live-capable feed with no evaluator installed produced
  `publishable=true, csrs=null`.
* `console_backend.liveness_of()` judged currency from the *evaluation*
  timestamp. A synthetic recent archive point displayed `CURRENT MARKET
  READING` while its own payload said no feed was configured.
* `MarketClock.recency()` accepted a **future** timestamp as live: the audit
  probe got age −1435 minutes and permission to publish.

The rule
--------
Publication is **fail-closed and reason-bearing**. `assess_publication`
returns every reason it refused, never a bare boolean, and a recent
`computed_at` can never promote a replay. Current evaluation time is not
observation age — that substitution is the whole bug.

What it deliberately does *not* demand: that every pillar emit on every bar.
C8's structural-versus-transient absence semantics are preserved, so a
pillar that is legitimately absent does not block publication. Only
**mandatory** observations do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from seraph.shared_types import IST

#: Tolerated clock skew between a source's clock and ours. An engineering
#: assumption with boundary tests, not a scientific threshold. Skew may excuse
#: a slightly-ahead *observation* clock; it never makes future information
#: eligible for an earlier cutoff.
MAX_CLOCK_SKEW = timedelta(seconds=30)

Mode = Literal["live_shadow", "historical_replay", "demo"]

DataState = Literal["fresh", "delayed", "stale", "unavailable", "invalid"]

ComputationState = Literal["ready", "warming_up", "partial", "failed"]


@dataclass(frozen=True)
class InputProvenance:
    """One input, and what is actually known about when it arrived."""

    name: str
    observed_at: datetime | None          # when the world produced it
    received_at: datetime | None          # when SERAPH could first have it
    mandatory: bool = True
    coverage: float | None = None         # 0..1 of the expected population
    freshness_budget: timedelta | None = None
    quality: str = "ok"

    def reasons(self, *, as_of: datetime, now: datetime,
                skew: timedelta) -> list[str]:
        out: list[str] = []
        if self.received_at is None:
            out.append(f"{self.name}:unknown_availability")
        elif self.received_at > as_of:
            # Causality, and skew tolerance does NOT relax it: an input that
            # arrived after the cutoff was not known at the cutoff.
            out.append(f"{self.name}:not_known_at_cutoff")
        if self.observed_at is not None and self.observed_at > now + skew:
            out.append(f"{self.name}:future_input")
        if self.quality not in ("ok", "partial"):
            out.append(f"{self.name}:quality_{self.quality}")
        if self.freshness_budget is not None and self.received_at is not None:
            age = as_of - self.received_at
            if age > self.freshness_budget:
                out.append(f"{self.name}:stale_{int(age.total_seconds() // 60)}min")
        if self.coverage is not None and self.coverage < 1.0:
            out.append(f"{self.name}:coverage_{self.coverage:.2f}")
        return out


@dataclass(frozen=True)
class FeedProvenance:
    registered: bool = False
    authenticated: bool = False
    connected: bool = False
    source_kind: str = "none"
    last_message_at: datetime | None = None


@dataclass(frozen=True)
class PublicationPolicy:
    max_clock_skew: timedelta = MAX_CLOCK_SKEW
    #: Inputs whose coverage shortfall is tolerated rather than blocking.
    tolerate_partial_coverage: bool = False
    require_warmup: bool = True


@dataclass(frozen=True)
class PublicationAssessment:
    """Whether this may be shown as current, and exactly why not."""

    current_allowed: bool
    reasons: tuple[str, ...] = ()
    label: str = ""
    mode: Mode = "historical_replay"

    def describe(self) -> dict:
        return dict(current_allowed=self.current_allowed,
                    reasons=list(self.reasons), label=self.label, mode=self.mode)


#: Human-readable text per reason code, so the UI never shows a bare code.
REASON_TEXT = {
    "not_live_mode": "this is a replay, not a live session",
    "no_valid_score": "no valid score was produced",
    "unverified_feed": "the market data source is not registered and authenticated",
    "feed_disconnected": "the market data source is not connected",
    "future_decision": "the decision time is in the future",
    "warmup_incomplete": "the model state has not finished warming up",
    "calendar_unverified": "the trading calendar is not verified for this instant",
    "empty_information_set": "no eligible information was available",
    "computation_failed": "the computation failed",
}


def valid_csrs_contract(csrs) -> bool:
    """A score must exist and be a real number in the CSRS range."""
    if csrs is None:
        return False
    value = csrs.get("csrs") if isinstance(csrs, dict) else getattr(csrs, "csrs", None)
    if value is None:
        return False
    try:
        value = float(value)
    except (TypeError, ValueError):
        return False
    return 0.0 <= value <= 1.0


def assess_publication(*, mode: Mode, csrs, feed: FeedProvenance,
                       as_of: datetime, now: datetime,
                       computation: ComputationState = "ready",
                       warmup_complete: bool = True,
                       calendar_verified: bool = True,
                       required_inputs: tuple[InputProvenance, ...] = (),
                       has_eligible_information: bool = True,
                       policy: PublicationPolicy | None = None
                       ) -> PublicationAssessment:
    """The single gate. Every caller uses this; nobody decides currency alone."""
    policy = policy or PublicationPolicy()
    reasons: list[str] = []

    if mode != "live_shadow":
        reasons.append("not_live_mode")
    if computation == "failed":
        reasons.append("computation_failed")
    if not valid_csrs_contract(csrs):
        reasons.append("no_valid_score")
    if not (feed.registered and feed.authenticated):
        reasons.append("unverified_feed")
    if not feed.connected:
        reasons.append("feed_disconnected")
    if as_of > now + policy.max_clock_skew:
        reasons.append("future_decision")
    if policy.require_warmup and not warmup_complete:
        reasons.append("warmup_incomplete")
    if not calendar_verified:
        reasons.append("calendar_unverified")

    for provenance in required_inputs:
        if not provenance.mandatory:
            continue
        for reason in provenance.reasons(as_of=as_of, now=now,
                                         skew=policy.max_clock_skew):
            if policy.tolerate_partial_coverage and reason.endswith(
                    tuple(f"coverage_{c:.2f}" for c in (0.0,))):
                continue
            reasons.append(reason)

    if not has_eligible_information:
        reasons.append("empty_information_set")

    allowed = not reasons
    if allowed:
        label = "CURRENT MARKET READING"
    elif reasons == ["not_live_mode"]:
        label = "HISTORICAL REPLAY — NOT A CURRENT MARKET READING"
    elif any(r.endswith(tuple(["_stale"])) or "stale_" in r for r in reasons):
        label = "DELAYED RESEARCH READING — NOT CURRENT"
    else:
        label = "NOT A CURRENT MARKET READING"
    return PublicationAssessment(current_allowed=allowed,
                                 reasons=tuple(reasons), label=label, mode=mode)


def explain(assessment: PublicationAssessment) -> list[str]:
    """Reason codes as sentences, for the UI."""
    out = []
    for reason in assessment.reasons:
        if reason in REASON_TEXT:
            out.append(REASON_TEXT[reason])
            continue
        # Input names legitimately contain colons (`bar:RELIANCE`), so split
        # on the LAST one: the suffix is the condition, the rest is the name.
        name, _, detail = reason.rpartition(":")
        if detail.startswith("stale_"):
            out.append(f"{name} is stale ({detail[6:]} old)")
        elif detail == "not_known_at_cutoff":
            out.append(f"{name} arrived after the decision cutoff")
        elif detail == "unknown_availability":
            out.append(f"{name} has no recorded arrival time")
        elif detail == "future_input":
            out.append(f"{name} is timestamped in the future")
        elif detail.startswith("coverage_"):
            out.append(f"{name} covers only {float(detail[9:]) * 100:.0f}% "
                       f"of its expected population")
        elif detail.startswith("quality_"):
            out.append(f"{name} quality is {detail[8:]}")
        else:
            out.append(reason)
    return out
