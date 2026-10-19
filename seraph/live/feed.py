# Live — market data feed adapters (FR1, FR2)
"""Where present market data comes from, and what happens when it does not.

The honest position this module encodes
---------------------------------------
SERAPH has **no live market data source connected**. The Kite client in
`seraph/ingestion/kite_client.py` is a REST backfill client — historical
candles, daily token, no websocket. The research corpus ends 2026-08-21. So
every score the system has produced is a replay.

This module is the seam that changes that, and it is built so the gap cannot
be papered over:

* `MarketDataFeed` is the protocol a real source implements.
* `KiteTickerFeed` is the real adapter. It **requires credentials** and raises
  `FeedUnavailable` without them. It does not fall back to anything.
* `ReplayFeed` replays archived bars at wall-clock speed for testing. It
  reports `is_live=False` and `source_kind='replay'` on every tick, so a
  caller cannot mistake it for a market connection — the recency gate in
  `clock.py` refuses to publish its output as current regardless.

A feed that cannot say *when* it last heard from the market is not usable, so
`last_message_at` is part of the protocol rather than an optional extra.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Literal, Protocol

from seraph.shared_types import IST, ist_timestamp

SourceKind = Literal["broker_websocket", "broker_rest", "exchange_file",
                     "replay", "none"]


class FeedUnavailable(RuntimeError):
    """No live market data source is reachable or configured.

    This is never a reason to substitute archived data and call it current.
    """


@dataclass(frozen=True)
class Tick:
    symbol: str
    ts: str                      # IST, explicit offset
    last_price: float
    volume_traded: int | None = None
    source_kind: SourceKind = "none"

    def __post_init__(self) -> None:
        if self.last_price <= 0:
            raise ValueError(f"{self.symbol}: a non-positive price is not a quote")


@dataclass(frozen=True)
class FeedHealth:
    source_kind: SourceKind
    connected: bool
    last_message_at: str | None
    symbols: int
    is_live: bool
    detail: str

    def describe(self) -> dict:
        return dict(source_kind=self.source_kind, connected=self.connected,
                    last_message_at=self.last_message_at, symbols=self.symbols,
                    is_live=self.is_live, detail=self.detail)


class MarketDataFeed(Protocol):
    """What the live loop needs from any source of present market data."""

    source_kind: SourceKind
    is_live: bool

    def connect(self, symbols: Iterable[str]) -> None: ...

    def poll(self) -> list[Tick]:
        """Ticks since the previous call. Never blocks indefinitely."""

    def health(self) -> FeedHealth: ...

    def close(self) -> None: ...


class NullFeed:
    """The current state of the world: no source configured.

    Returned by `resolve_feed()` when nothing is set up, so the live loop has
    something honest to report rather than crashing or inventing data.
    """

    source_kind: SourceKind = "none"
    is_live = False

    def __init__(self, reason: str):
        self.reason = reason
        self._symbols: tuple[str, ...] = ()

    def connect(self, symbols: Iterable[str]) -> None:
        self._symbols = tuple(symbols)

    def poll(self) -> list[Tick]:
        return []

    def health(self) -> FeedHealth:
        return FeedHealth(source_kind="none", connected=False,
                          last_message_at=None, symbols=len(self._symbols),
                          is_live=False, detail=self.reason)

    def close(self) -> None:
        return None


class ReplayFeed:
    """Replays archived bars. **Explicitly not live.**

    Used to exercise the live loop end to end without a broker connection.
    Every tick is stamped `source_kind='replay'` and `is_live` is False, so
    the recency gate refuses to publish its output as a current reading.
    """

    source_kind: SourceKind = "replay"
    is_live = False

    def __init__(self, ticks: Iterable[Tick], *, label: str = "archived bars"):
        self._pending = list(ticks)
        self._cursor = 0
        self._last: str | None = None
        self.label = label
        self._symbols: tuple[str, ...] = ()

    def connect(self, symbols: Iterable[str]) -> None:
        self._symbols = tuple(symbols)

    def poll(self) -> list[Tick]:
        batch = self._pending[self._cursor:]
        self._cursor = len(self._pending)
        if batch:
            self._last = batch[-1].ts
        return [Tick(symbol=t.symbol, ts=t.ts, last_price=t.last_price,
                     volume_traded=t.volume_traded, source_kind="replay")
                for t in batch]

    def feed(self, ticks: Iterable[Tick]) -> None:
        self._pending.extend(ticks)

    def health(self) -> FeedHealth:
        return FeedHealth(
            source_kind="replay", connected=True, last_message_at=self._last,
            symbols=len(self._symbols), is_live=False,
            detail=(f"replaying {self.label}; this is NOT a market connection "
                    f"and its output is never a current reading"))

    def close(self) -> None:
        return None


class KiteTickerFeed:
    """The real adapter: Zerodha Kite's streaming quotes.

    Deliberately thin and deliberately unforgiving. It needs
    `KITE_API_KEY`/`KITE_API_SECRET` plus a daily access token, and raises
    `FeedUnavailable` without them rather than degrading to anything.

    **Unverified.** No credentials exist in this checkout, so this adapter has
    never connected to the live endpoint. Its contract and failure paths are
    tested; its success path is not, and `health().detail` says so until a
    real session has been established.
    """

    source_kind: SourceKind = "broker_websocket"
    is_live = True

    def __init__(self, *, api_key: str | None = None,
                 access_token: str | None = None):
        self._api_key = api_key or os.environ.get("KITE_API_KEY")
        self._access_token = access_token
        self._ticker = None
        self._buffer: list[Tick] = []
        self._last: str | None = None
        self._symbols: tuple[str, ...] = ()
        self._tokens: dict[int, str] = {}
        self._verified = False

    def _require_credentials(self) -> tuple[str, str]:
        if not self._api_key:
            raise FeedUnavailable(
                "KITE_API_KEY is not set. There is no live market data source "
                "configured, and archived data will not be substituted for one")
        token = self._access_token
        if not token:
            try:
                from seraph.ingestion.kite_client import cached_access_token
                token = cached_access_token()
            except Exception as exc:                          # noqa: BLE001
                raise FeedUnavailable(
                    f"no Kite access token available ({exc}). Run "
                    f"`python scripts/kite_login.py`; tokens die daily at "
                    f"~06:00 IST") from exc
        return self._api_key, token

    def connect(self, symbols: Iterable[str]) -> None:
        api_key, access_token = self._require_credentials()
        self._symbols = tuple(symbols)
        try:
            from kiteconnect import KiteTicker              # type: ignore
        except ImportError as exc:
            raise FeedUnavailable(
                "the `kiteconnect` package is not installed, so no websocket "
                "feed can be opened. `pip install kiteconnect` and supply "
                "credentials; nothing is faked in its absence") from exc
        from seraph.ingestion.kite_client import KiteClient

        client = KiteClient(access_token=access_token)
        instruments = client.instruments_nse()
        self._tokens = {instruments[s]: s for s in self._symbols
                        if s in instruments}
        missing = [s for s in self._symbols if s not in instruments]
        if missing:
            raise FeedUnavailable(
                f"{len(missing)} requested symbol(s) have no NSE instrument "
                f"token ({', '.join(missing[:5])}); subscribing to a partial "
                f"universe silently would change what the pillars measure")

        ticker = KiteTicker(api_key, access_token)

        def on_ticks(_ws, ticks):                            # pragma: no cover
            for raw in ticks:
                symbol = self._tokens.get(raw.get("instrument_token"))
                price = raw.get("last_price")
                if not symbol or not price:
                    continue
                stamp = raw.get("exchange_timestamp") or datetime.now(IST)
                if isinstance(stamp, datetime):
                    stamp = ist_timestamp(stamp.astimezone(IST).replace(microsecond=0))
                self._buffer.append(Tick(
                    symbol=symbol, ts=stamp, last_price=float(price),
                    volume_traded=raw.get("volume_traded"),
                    source_kind="broker_websocket"))
                self._last = stamp
            self._verified = True

        def on_connect(ws, _response):                       # pragma: no cover
            ws.subscribe(list(self._tokens))
            ws.set_mode(ws.MODE_FULL, list(self._tokens))

        ticker.on_ticks = on_ticks
        ticker.on_connect = on_connect
        ticker.connect(threaded=True)
        self._ticker = ticker

    def poll(self) -> list[Tick]:
        batch, self._buffer = self._buffer, []
        return batch

    def health(self) -> FeedHealth:
        connected = bool(self._ticker and getattr(self._ticker, "is_connected",
                                                  lambda: False)())
        detail = ("connected" if connected else "not connected")
        if not self._verified:
            detail += ("; this adapter has never been exercised against the live "
                       "endpoint in this checkout")
        return FeedHealth(source_kind="broker_websocket", connected=connected,
                          last_message_at=self._last, symbols=len(self._symbols),
                          is_live=True, detail=detail)

    def close(self) -> None:
        if self._ticker is not None:                         # pragma: no cover
            try:
                self._ticker.close()
            finally:
                self._ticker = None


def resolve_feed(*, allow_replay: ReplayFeed | None = None) -> MarketDataFeed:
    """Pick the best available source, and be explicit when there is none.

    Order: a real broker connection if credentials exist; otherwise the
    caller's replay feed if they supplied one *deliberately*; otherwise
    `NullFeed`. There is no automatic fallback from live to archived — the
    caller has to hand over a replay feed on purpose.
    """
    if os.environ.get("KITE_API_KEY"):
        return KiteTickerFeed()
    if allow_replay is not None:
        return allow_replay
    return NullFeed(
        "no live market data source is configured. Set KITE_API_KEY and run "
        "scripts/kite_login.py, or pass a ReplayFeed explicitly. Archived data "
        "is never substituted automatically")
