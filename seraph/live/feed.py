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

import math
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
    """One quote. A `Tick` that exists is a valid quote, by construction.

    The validation below is the OHLC boundary. `last_price <= 0` alone was
    not it: `float('nan') <= 0` and `float('inf') <= 0` are both `False`, so
    a nonfinite price passed straight into a bar's open, high, low and close,
    and from there into the Lee-Mykland return and the CSRS. Everything
    downstream treats a bar as numeric, so this is the only place the check
    can be made once.
    """

    symbol: str
    ts: str                      # IST, explicit offset
    last_price: float
    volume_traded: int | None = None
    source_kind: SourceKind = "none"
    #: The provider's own monotone counter, where the feed supplies one. Used
    #: ONLY for ordering, and only against another sequence from the same
    #: provider — see `BarBuilder._out_of_order`.
    sequence: int | None = None

    def __post_init__(self) -> None:
        for problem in (self._reject(),):
            if problem is not None:
                raise ValueError(f"{self.symbol or '<no symbol>'}: {problem}")

    def _reject(self) -> str | None:
        """Why this is not a quote, or `None`. Never raises."""
        if not self.symbol or not str(self.symbol).strip():
            return "a quote with no symbol cannot be attributed to an instrument"
        if not isinstance(self.last_price, (int, float)) or isinstance(self.last_price, bool):
            return f"price {self.last_price!r} is not a number"
        if not math.isfinite(self.last_price):
            return (f"price {self.last_price!r} is not finite; NaN and infinity "
                    f"must never reach OHLC")
        if self.last_price <= 0:
            return "a non-positive price is not a quote"
        if self.volume_traded is not None:
            volume = self.volume_traded
            if isinstance(volume, bool) or not isinstance(volume, (int, float)):
                return f"cumulative volume {volume!r} is not a number"
            if not math.isfinite(volume):
                return f"cumulative volume {volume!r} is not finite"
            if volume < 0:
                return (f"cumulative volume {volume!r} is negative; a traded "
                        f"total cannot fall below zero")
            if int(volume) != volume:
                return (f"cumulative volume {volume!r} is fractional; traded "
                        f"quantity is a count")
        if self.sequence is not None:
            if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
                return f"provider sequence {self.sequence!r} is not an integer"
            if self.sequence < 0:
                return f"provider sequence {self.sequence!r} is negative"
        try:
            moment = datetime.fromisoformat(self.ts)
        except (TypeError, ValueError):
            return (f"timestamp {self.ts!r} is not ISO-8601; every timestamp in "
                    f"this system is IST with an explicit offset")
        if moment.utcoffset() is None:
            return (f"timestamp {self.ts!r} carries no UTC offset; a naive "
                    f"timestamp cannot be placed in a trading session")
        return None

    @classmethod
    def accept(cls, **fields) -> "tuple[Tick | None, str | None]":
        """Build a tick, or say why these fields are not one. Never raises.

        A feed adapter runs inside a provider callback, where an exception
        can take the socket thread down with it. This is the non-raising
        door: the adapter gets back either a tick or a reason, counts the
        reason, and keeps reading.
        """
        try:
            return cls(**fields), None
        except (ValueError, TypeError) as exc:
            return None, str(exc)


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
                     volume_traded=t.volume_traded, source_kind="replay",
                     sequence=t.sequence)
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

    Health distinguishes an attempted connection, an established socket and
    receipt of a valid quote. Broker rejection never counts as a live reading.
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
        self._attempted = False
        self._connection_problem: str | None = None
        #: Packets the provider sent that are not quotes, by reason. Visible
        #: in `health()`, because a feed silently dropping half its packets
        #: and a feed receiving nothing look identical otherwise.
        self.rejected: dict[str, int] = {}

    def _reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

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
            # Runs inside the kiteconnect callback thread. Nothing here may
            # raise: an exception escaping this function can take the socket
            # thread down, and a provider that sends one malformed packet
            # would then stop the whole feed. `Tick.accept` is the
            # non-raising door; a rejected packet is counted and named.
            for raw in ticks:
                symbol = self._tokens.get(raw.get("instrument_token"))
                price = raw.get("last_price")
                if not symbol or price is None:
                    self._reject("no symbol token or no price in packet")
                    continue
                stamp = raw.get("exchange_timestamp") or datetime.now(IST)
                if isinstance(stamp, datetime):
                    stamp = ist_timestamp(stamp.astimezone(IST).replace(microsecond=0))
                tick, problem = Tick.accept(
                    symbol=symbol, ts=stamp, last_price=price,
                    volume_traded=raw.get("volume_traded"),
                    source_kind="broker_websocket",
                    sequence=raw.get("sequence_number"))
                if tick is None:
                    self._reject(problem or "unspecified")
                    continue
                self._buffer.append(tick)
                self._last = stamp
                self._verified = True

        def on_connect(ws, _response):                       # pragma: no cover
            self._connection_problem = None
            ws.subscribe(list(self._tokens))
            ws.set_mode(ws.MODE_FULL, list(self._tokens))

        def on_error(_ws, code, reason):
            # Provider error text may contain a credential-bearing URL.
            # Classify it, but never persist or display the raw text.
            if str(code) == '403' or '403' in str(reason):
                self._connection_problem = (
                    'Broker rejected authentication or market-data access (403). '
                    'Refresh the daily token with scripts/kite_login.py and '
                    'verify the Kite market-data subscription.')
            else:
                self._connection_problem = (
                    'Broker websocket failed. Check connectivity, the daily '
                    'access token and the Kite market-data subscription.')

        def on_close(_ws, _code, _reason):
            if self._connection_problem is None:
                self._connection_problem = 'Broker websocket closed; waiting for reconnection.'

        ticker.on_ticks = on_ticks
        ticker.on_connect = on_connect
        ticker.on_error = on_error
        ticker.on_close = on_close
        self._ticker = ticker
        self._attempted = True
        ticker.connect(threaded=True)

    def poll(self) -> list[Tick]:
        batch, self._buffer = self._buffer, []
        return batch

    def health(self) -> FeedHealth:
        connected = bool(self._ticker and getattr(self._ticker, "is_connected",
                                                  lambda: False)())
        detail = ("connected" if connected else "not connected")
        if self._connection_problem:
            detail += '; ' + self._connection_problem
        if not self._attempted:
            detail += ("; this adapter has never been exercised against the live "
                       "endpoint in this checkout")
        elif not self._verified:
            detail += '; no valid market quote has been received in this runtime'
        if self.rejected:
            total = sum(self.rejected.values())
            detail += (f"; {total} packet(s) rejected as not-a-quote: "
                       + ", ".join(f"{n}x {why}"
                                   for why, n in sorted(self.rejected.items())))
        return FeedHealth(source_kind="broker_websocket", connected=connected,
                          last_message_at=self._last, symbols=len(self._symbols),
                          is_live=True, detail=detail)

    def close(self) -> None:
        if self._ticker is not None:                         # pragma: no cover
            try:
                self._ticker.close()
            finally:
                self._ticker = None


def resolve_feed(*, allow_replay: ReplayFeed | None = None,
                 use_env_file: bool = False) -> MarketDataFeed:
    """Pick the source the caller asked for, and be explicit when there is none.

    **An explicit replay feed wins over credentials.** The previous order
    tested `KITE_API_KEY` first, so `run_live.py --replay` on a machine with
    a token opened a real broker websocket: the operator asked for a replay
    and got the market. That is the most dangerous shape of defect in this
    module relative to its size, because the replay path exists precisely to
    exercise the loop *without* touching a broker, and `--replay` is what a
    test or a demo runs.

    Order now: the caller's deliberate replay feed; otherwise a real broker
    connection if credentials exist; otherwise `NullFeed`. There is still no
    automatic fallback from live to archived — a caller has to hand over a
    replay feed on purpose, and live mode fails loudly rather than degrading.
    """
    if allow_replay is not None:
        return allow_replay
    if use_env_file:
        # The ordinary runtime uses the same configured credential source as
        # the existing login/backfill client. Explicit replays return above
        # without loading credentials or opening a broker connection.
        from seraph.ingestion.kite_client import _load_env_file
        _load_env_file()
    if os.environ.get("KITE_API_KEY"):
        return KiteTickerFeed()
    return NullFeed(
        "no live market data source is configured. Set KITE_API_KEY and run "
        "scripts/kite_login.py, or pass a ReplayFeed explicitly. Archived data "
        "is never substituted automatically")
