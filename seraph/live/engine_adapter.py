# Live — binding the inference service into the bar-close loop (T06, R01).
"""Make the live loop actually invoke the risk engine.

Audit finding R01 was that `LiveLoop` had an `evaluate` slot and nothing in
it: the loop closed bars, measured latency and assessed publication, and never
computed a score. This module fills that slot with the real
`InferenceService`, so a bar close produces a `DecisionResult` through the
same C8/C9 path the archive replay uses.

**What is connected, and what is not.** The loop → service wiring is complete
and exercised. The *producers* that turn closed bars into pillar vintages are
not: a live Hawkes estimate needs a warm-started window of pooled counts from
the store, which is T07's durable state, and RMT and Hamilton are daily
products read from the store rather than derived from a five-minute bar. So
`NullProducers` is the honest default — it returns no vintage, every pillar
reports a structural absence, no CSRS is produced and the publication gate
refuses to call anything current. That is a true description of the system
today, and it is visible in the decision rather than implied by its absence.

`StaticProducers` exists for replay and tests, where the vintages are known.
Nothing here invents a pillar value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol, Sequence

from seraph.live.bars import Bar
from seraph.live.inference import (
    ORDER,
    DecisionRequest,
    DecisionResult,
    InferenceService,
    Vintage,
)
from seraph.live.publication import FeedProvenance

ADAPTER_VERSION = "live.engine_adapter/2026-10-19.1"

#: How long after a bar closes the decision for it is taken (R02, DR-11).
#:
#: A producer cannot emit a bar-derived estimate until the bar is complete,
#: so a cutoff AT the bar end withholds every bar-derived vintage forever.
#: This is the declared allowance that admits normal producer latency while
#: staying a deterministic function of the bar end, so a replay reproduces
#: the same cutoff. It is an ENGINEERING default, not a measured one: O07
#: measures real bar-to-decision latency and this should be set from that
#: measurement rather than from this comment.
DECISION_ALLOWANCE = timedelta(seconds=5)


def decision_id(*, mode: str, stream_id: str, bar_end: str) -> str:
    """The identity of one decision.

    X04 (completion-audit verification, Part 3). This was
    `f"live:{as_of.isoformat()}"` -- no stream, no mode. A replay pass and a
    live pass over the same bar end minted the SAME id, and because
    `LiveStore.commit_decision` returned an existing row as a replay before
    comparing its payload, a replay commit was accepted as the existing live
    decision and reported `replayed=True`. The audit names the read side of
    this (R06: `latest_decision` is not stream-scoped) but not the minting
    side, and fixing only the read side leaves the collision.

    Mode is part of the identity, not metadata on it: a live reading and a
    replay of the same instant are different facts about the world, and the
    whole mode discipline in this codebase rests on never being able to
    substitute one for the other.
    """
    return f"{mode}:{stream_id}:{bar_end}"


class Producers(Protocol):
    """Turn a batch of finalized bars into the pillar vintages they imply."""

    def vintages_for(self, bars: "Sequence[Bar]", as_of: datetime
                     ) -> "list[Vintage]": ...

    def describe(self) -> dict: ...


@dataclass(frozen=True)
class NullProducers:
    """No live producer is connected, and the decision says so.

    Every pillar is a *structural* absence: there is no estimator running, so
    this is not a feed outage that might clear on the next tick. Structural is
    what drops a pillar out of the D2 mask, which is the correct treatment for
    a producer that does not exist yet.
    """

    reason: str = ("no live pillar producer is connected; a live Hawkes "
                   "estimate needs the warm-started count window from the "
                   "durable store (T07), and RMT/Hamilton are daily products "
                   "read from the store, not derived from a five-minute bar")

    def vintages_for(self, bars: "Sequence[Bar]", as_of: datetime
                     ) -> "list[Vintage]":
        stamp = as_of.isoformat()
        return [Vintage(producer=p, input_end=stamp,
                        emission_available_at=stamp, absence="structural",
                        absence_reason="no_data_coverage")
                for p in ORDER]

    def describe(self) -> dict:
        return dict(kind="null", connected=[], reason=self.reason)


@dataclass
class StaticProducers:
    """Vintages supplied by the caller, keyed by the bar end they belong to.

    For replay and tests. It never interpolates: a bar end with no entry
    yields nothing, and the service then carries the previous vintage forward
    or reports an absence, exactly as it would live.
    """

    by_bar_end: dict = field(default_factory=dict)

    def vintages_for(self, bars: "Sequence[Bar]", as_of: datetime
                     ) -> "list[Vintage]":
        out: list[Vintage] = []
        for bar in bars:
            out.extend(self.by_bar_end.get(bar.end, ()))
        return out

    def describe(self) -> dict:
        return dict(kind="static", bar_ends=len(self.by_bar_end),
                    note="supplied vintages; not a live estimator")


class ServiceEvaluator:
    """The callable `LiveLoop.evaluate` expects, backed by `InferenceService`.

    Returns the CSRS dict the loop puts on its decision, and keeps the full
    `DecisionResult` so the caller can persist the whole thing — the loop only
    needs the score, and the audit trail must not be thrown away to fit that.
    """

    def __init__(self, service: InferenceService, *,
                 producers: Producers | None = None,
                 mode: str = "live_shadow",
                 universe_snapshot_id: str = "",
                 model_bundle_id: str = "",
                 stream_id: str = "live") -> None:
        self.service = service
        self.producers = producers or NullProducers()
        self.mode = mode
        self.universe_snapshot_id = universe_snapshot_id
        self.model_bundle_id = model_bundle_id
        #: Which stream these decisions belong to. Part of the decision
        #: identity (X04) and of every scoped read in `LiveStore` (R06).
        self.stream_id = stream_id
        self.results: list[DecisionResult] = []

    @property
    def warmup_complete(self) -> bool:
        return self.service.warmup_complete

    def __call__(self, bars: "Sequence[Bar]", stamp: str) -> dict | None:
        bar_end = max(b.end for b in bars) if bars else stamp
        # R02/DR-11: `as_of` is the DECISION CUTOFF, not the bar end. It is
        # the bar end plus a declared allowance, so that a producer which
        # cannot emit until the bar is complete is admitted at its normal
        # latency instead of being withheld on every single bar. It stays a
        # function of the bar end rather than of the wall clock, so replaying
        # the same bars yields the same cutoff and the same decision identity.
        as_of = datetime.fromisoformat(bar_end) + DECISION_ALLOWANCE
        request = DecisionRequest(
            decision_id=decision_id(mode=self.mode,
                                    stream_id=self.stream_id,
                                    bar_end=bar_end),
            as_of=as_of, trigger="bar_close", mode=self.mode,
            input_batch_ids=tuple(sorted({f"{b.symbol}@{b.end}" for b in bars})),
            universe_snapshot_id=self.universe_snapshot_id,
            pipeline_version=ADAPTER_VERSION,
            model_bundle_id=self.model_bundle_id)
        result = self.service.process(
            request, vintages=self.producers.vintages_for(bars, as_of),
            feed=self.feed_provenance, now=datetime.fromisoformat(stamp))
        self.results.append(result)
        return result.csrs.model_dump() if result.csrs is not None else None

    #: Set by the loop before each tick so the service sees the same feed
    #: provenance the loop's own gate sees. Left unset it is an unverified
    #: feed, which refuses publication — the safe default.
    feed_provenance: FeedProvenance = FeedProvenance()

    def describe(self) -> dict:
        return dict(version=ADAPTER_VERSION, mode=self.mode,
                    producers=self.producers.describe(),
                    warmup_complete=self.warmup_complete,
                    decisions=len(self.results),
                    last_decision=(self.results[-1].describe()
                                   if self.results else None))


def attach(loop, service: InferenceService, *,
           producers: Producers | None = None,
           mode: str | None = None,
           stream_id: str = "live") -> ServiceEvaluator:
    """Put the engine in the loop's `evaluate` slot and keep warmup honest.

    After this call the loop computes a score on every bar close instead of
    leaving the slot empty, and its warmup flag is the service's rather than a
    constructor argument nobody updates.
    """
    evaluator = ServiceEvaluator(service, producers=producers,
                                 mode=mode or loop.mode, stream_id=stream_id)
    loop.evaluate = evaluator
    loop.warmup_source = lambda: evaluator.warmup_complete
    loop.feed_sink = lambda provenance: setattr(
        evaluator, "feed_provenance", provenance)
    return evaluator
