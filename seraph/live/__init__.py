# Live — present-market execution (FR39, NFR1)
"""The path from a live market connection to a current CSRS.

Everything else in SERAPH evaluates a chosen historical date. This package
inverts that: the market clock decides when a decision happens, and the
recency gate decides whether the result may be called a current reading.

**No live market data source is connected in this checkout.** The research
corpus ends 2026-08-21, the Kite client is REST backfill only, and
`resolve_feed()` returns `NullFeed` unless credentials are present. Nothing
here substitutes archived data for a market connection; `LiveDecision
.publishable` is False whenever the source is not live or the data is not
recent, so a replay can never be presented as the market now.
"""
from seraph.live.bars import Bar, BarBuilder
from seraph.live.clock import BAR_MINUTES, DataRecency, MarketClock
from seraph.live.feed import (
    FeedHealth,
    FeedUnavailable,
    KiteTickerFeed,
    MarketDataFeed,
    NullFeed,
    ReplayFeed,
    Tick,
    resolve_feed,
)
from seraph.live.loop import LiveDecision, LiveLoop

__all__ = [
    "BAR_MINUTES",
    "Bar",
    "BarBuilder",
    "DataRecency",
    "FeedHealth",
    "FeedUnavailable",
    "KiteTickerFeed",
    "LiveDecision",
    "LiveLoop",
    "MarketClock",
    "MarketDataFeed",
    "NullFeed",
    "ReplayFeed",
    "Tick",
    "resolve_feed",
]
