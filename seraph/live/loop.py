# Live — the bar-close decision loop (FR39, NFR1)
"""Run the pipeline when the market says to, and label what comes out.

This is the piece that makes CSRS a *market* risk score rather than a replay
artefact. The replay path picks a date and derives a decision time; here the
clock drives the decision and the loop has to answer questions a replay never
faces: is the market open, has the bar actually closed, is the feed keeping
up, and — the one that matters most today — is this data recent enough to be
called current at all.

The publication gate
--------------------
`LiveDecision.publishable` is False unless the recency state is `live` or
`delayed`. With the corpus ending 2026-08-21 and today in October, every score
this loop can currently produce is `historical_only`, so nothing is
publishable as a current reading. That is the correct answer, and it is
returned as a value rather than left to a caller's discretion.

Latency
-------
`bar_close_to_decision_ms` is measured on every tick, because NFR1 is about
bar-close-to-view latency and the audit was right that an overnight replay
benchmark says nothing about it. One measurement from a real bar close is
worth more than any amount of batch timing, so the loop records it from the
first tick rather than waiting for a benchmark harness.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from seraph.live.bars import Bar, BarBuilder
from seraph.live.clock import MarketClock
from seraph.live.feed import FeedUnavailable, MarketDataFeed, NullFeed
from seraph.live.publication import (
    FeedProvenance,
    InputProvenance,
    PublicationPolicy,
    assess_publication,
    explain,
)
from seraph.shared_types import ist_timestamp

LOOP_VERSION = "live.loop/2026-10-17.1"


@dataclass(frozen=True)
class LiveDecision:
    """One bar-close evaluation, and whether it may be shown as current."""

    decision_ts: str
    bar_end: str | None
    publishable: bool
    recency: dict
    market: dict
    feed: dict
    bars_closed: int
    symbols: int
    csrs: dict | None = None
    skipped_reason: str | None = None
    bar_close_to_decision_ms: float | None = None
    publication: dict | None = None
    version: str = LOOP_VERSION

    def describe(self) -> dict:
        return dict(
            decision_ts=self.decision_ts, bar_end=self.bar_end,
            publishable=self.publishable, recency=self.recency,
            market=self.market, feed=self.feed, bars_closed=self.bars_closed,
            symbols=self.symbols, csrs=self.csrs,
            skipped_reason=self.skipped_reason,
            bar_close_to_decision_ms=self.bar_close_to_decision_ms,
            publication=self.publication,
            version=self.version,
            label=((self.publication or {}).get("label")
                   or ("current market reading" if self.publishable
                       else "NOT a current reading — see publication reasons")),
        )


class LiveLoop:
    """Drive the pipeline from the market clock.

    `evaluate` is injected: the loop owns *when* a decision happens and what
    it may be called, not how the pillars are computed. That keeps C9 pure and
    lets this be tested without the numerical stack.
    """

    def __init__(self, feed: MarketDataFeed, *, clock: MarketClock | None = None,
                 evaluate: Callable[[list[Bar], str], dict] | None = None,
                 on_decision: Callable[[LiveDecision], None] | None = None,
                 mode: str = "live_shadow",
                 policy: PublicationPolicy | None = None,
                 warmup_complete: bool = False):
        self.clock = clock or MarketClock()
        self.feed = feed
        self.mode = mode
        self.policy = policy or PublicationPolicy()
        # T01: warmup is False until an inference service says otherwise.
        # A loop with no engine attached has not warmed up anything.
        self.warmup_complete = warmup_complete
        #: T06: when an inference service is attached, warmup is ITS state,
        #: not a constructor argument nobody updates afterwards.
        self.warmup_source = None
        #: Lets an attached evaluator see the same feed provenance this loop's
        #: own gate sees, so the two cannot disagree about the source.
        self.feed_sink = None
        self.builder = BarBuilder(self.clock)
        self.evaluate = evaluate
        self.on_decision = on_decision
        self.decisions: list[LiveDecision] = []
        #: The bars finalized by the most recent tick. T07 persists these, and
        #: re-deriving them from the decision payload would be a second,
        #: divergeable idea of what closed.
        self.last_closed: list = []
        self._newest_observation: str | None = None
        self._symbols: tuple[str, ...] = ()

    # --------------------------------------------------------------- setup

    def connect(self, symbols) -> dict:
        self._symbols = tuple(symbols)
        try:
            self.feed.connect(self._symbols)
        except FeedUnavailable as exc:
            # Not fatal: the loop still runs and reports honestly that it has
            # no source. Crashing would hide the state; faking it would be worse.
            self.feed = NullFeed(str(exc))
            self.feed.connect(self._symbols)
        return self.feed.health().describe()

    # ----------------------------------------------------------------- tick

    def tick(self, *, at: datetime | None = None) -> LiveDecision:
        """One pass: drain the feed, close elapsed bars, decide if warranted."""
        started = time.perf_counter()
        moment = at or self.clock.now()
        stamp = ist_timestamp(moment)
        market = self.clock.state(moment)
        health = self.feed.health().describe()

        ticks = self.feed.poll()
        closed = self.builder.add(ticks)
        closed.extend(self.builder.close_elapsed(moment))
        self.last_closed = list(closed)
        if closed:
            self._newest_observation = max(b.end for b in closed)
        elif ticks:
            self._newest_observation = max(t.ts for t in ticks)

        recency = self.clock.recency(self._newest_observation, at=moment)
        base = dict(decision_ts=stamp, bar_end=(max(b.end for b in closed)
                                                if closed else None),
                    recency=recency.describe(), market=market, feed=health,
                    bars_closed=len(closed), symbols=len(self._symbols))

        if market["state"] != "open" and not closed:
            return self._emit(LiveDecision(
                **base, publishable=False,
                skipped_reason=f"market is {market['state']}; no bar closed"))
        if not closed:
            return self._emit(LiveDecision(
                **base, publishable=False,
                skipped_reason="no bar has closed since the last evaluation; a "
                               "partial bar is never evaluated"))

        csrs = None
        computation = "ready"
        if self.feed_sink is not None:
            self.feed_sink(self._feed_provenance())
        if self.evaluate is not None:
            try:
                csrs = self.evaluate(closed, stamp)
            except Exception as exc:                          # noqa: BLE001
                computation = "failed"
                csrs = None
                base["feed"] = dict(health, evaluate_error=f"{type(exc).__name__}: {exc}")

        latency = None
        if base["bar_end"]:
            latency = max(0.0, (moment - datetime.fromisoformat(base["bar_end"])
                                ).total_seconds() * 1000
                          + (time.perf_counter() - started) * 1000)

        # T01 / audit finding R02: ONE gate decides currency, and it requires a
        # valid score, a verified connected feed, a non-future cutoff, finished
        # warmup and every mandatory input known at the cutoff.
        assessment = assess_publication(
            mode=self.mode, csrs=csrs, feed=self._feed_provenance(),
            as_of=datetime.fromisoformat(base["bar_end"] or stamp), now=moment,
            computation=computation,
            warmup_complete=(self.warmup_source() if self.warmup_source
                             else self.warmup_complete),
            calendar_verified=self.clock.calendar.verified_for(moment.date().isoformat()),
            required_inputs=self._input_provenance(closed, moment),
            has_eligible_information=bool(closed), policy=self.policy)

        return self._emit(LiveDecision(
            **base, csrs=csrs,
            publishable=assessment.current_allowed,
            publication=assessment.describe(),
            bar_close_to_decision_ms=round(latency, 1) if latency is not None else None,
            skipped_reason=(None if assessment.current_allowed
                            else "; ".join(explain(assessment)))))

    def _feed_provenance(self) -> FeedProvenance:
        health = self.feed.health()
        return FeedProvenance(
            registered=health.source_kind != "none",
            # A feed is authenticated only if it is a real broker connection.
            # A replay is registered and connected but never authenticated.
            authenticated=bool(self.feed.is_live and health.connected),
            connected=health.connected, source_kind=health.source_kind,
            last_message_at=(datetime.fromisoformat(health.last_message_at)
                             if health.last_message_at else None))

    def _input_provenance(self, closed, moment) -> tuple:
        """Each closed bar is an input whose arrival time we actually know."""
        return tuple(
            InputProvenance(
                name=f"bar:{bar.symbol}",
                observed_at=datetime.fromisoformat(bar.end),
                received_at=moment, mandatory=True,
                coverage=None if bar.volume is None else 1.0,
                quality="ok" if bar.complete else "partial")
            for bar in closed)

    def _emit(self, decision: LiveDecision) -> LiveDecision:
        self.decisions.append(decision)
        if self.on_decision is not None:
            self.on_decision(decision)
        return decision

    # -------------------------------------------------------------- status

    def status(self, *, at: datetime | None = None) -> dict:
        moment = at or self.clock.now()
        published = [d for d in self.decisions if d.publishable]
        latencies = [d.bar_close_to_decision_ms for d in self.decisions
                     if d.bar_close_to_decision_ms is not None]
        return dict(
            version=LOOP_VERSION,
            market=self.clock.state(moment),
            feed=self.feed.health().describe(),
            recency=self.clock.recency(self._newest_observation, at=moment).describe(),
            bars=self.builder.describe(),
            decisions=len(self.decisions),
            published=len(published),
            latency_ms=(dict(n=len(latencies),
                             worst=max(latencies), median=sorted(latencies)[len(latencies) // 2])
                        if latencies else None),
            note=("`published` counts decisions that were safe to show as a "
                  "current market reading. A decision that ran but was not "
                  "publishable is still recorded, with the reason"),
        )


def _why_not(recency, feed) -> str:
    if not feed.is_live:
        return (f"the source is '{feed.source_kind}', not a live market "
                f"connection; its output is a replay and is labelled one")
    return f"recency is '{recency.state}': {recency.note}"
