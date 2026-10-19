# Live — tick to bar aggregation (FR1, FR5; T02, audit finding R03)
"""Accumulate ticks into closed bars, and never hand out a partial one.

The failure this prevents is specific and nasty. The Lee–Mykland detector
compares a bar's return against a local bipower volatility estimate. Feed it a
bar that is still filling and it sees a smaller return than the bar will
eventually have — so a jump appears, then un-appears five minutes later when
the bar actually closes. The CSRS built on it does the same. A flickering risk
score destroys trust faster than a wrong one.

T02 — what the audit found wrong
--------------------------------
The first version tracked only the *open* accumulators, so a window that had
already closed could be **recreated and re-emitted**. The audit probe got the
11:00–11:05 bar twice — once with close 100, then with close 999 — and
`late_ticks` stayed zero, because the late-tick check only fired while a newer
accumulator happened to exist.

Volume was worse. It used the first and last cumulative totals *inside* the
bar, so with prior cumulative 150 and next-bar ticks 170 and 200 it reported
30 instead of the 50 actually traded since the boundary. The 20 units between
the previous bar's last tick and this bar's first tick simply vanished.

Both are fixed by keeping **per-symbol session state** rather than only open
accumulators:

* `last_finalized_end` — a watermark. A window at or before it cannot reopen,
  with or without an accumulator present, and the watermark survives restart
  through `snapshot()`/`restore()`.
* `last_cumulative_volume` / `last_cumulative_at` — the running baseline
  carried *across* boundaries, so a bar's volume is the increment since the
  previous bar's last observation, not since its own first tick.

Honesty about what cannot be known
----------------------------------
A mid-session connection has no baseline for its first window, so that bar's
volume is `None` with `volume_quality='partial'` — not a number computed from
an assumption. A cumulative figure that goes *backwards* is a provider reset
or revision, so the bar's volume is invalidated rather than reported as a
negative or clamped to zero. An out-of-order tick marks volume uncertain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from seraph.live.clock import MarketClock
from seraph.live.feed import Tick
from seraph.shared_types import ist_timestamp

VolumeQuality = Literal["exact", "partial", "uncertain", "unavailable"]

QuarantineReason = Literal["outside_session", "late_finalized", "out_of_order",
                           "duplicate", "volume_reset_or_revision"]


@dataclass(frozen=True)
class Bar:
    symbol: str
    start: str
    end: str
    open: float
    high: float
    low: float
    close: float
    ticks: int
    volume: int | None = None
    complete: bool = True
    volume_quality: VolumeQuality = "exact"
    session_id: str | None = None

    def describe(self) -> dict:
        return dict(symbol=self.symbol, start=self.start, end=self.end,
                    open=self.open, high=self.high, low=self.low,
                    close=self.close, ticks=self.ticks, volume=self.volume,
                    complete=self.complete, volume_quality=self.volume_quality,
                    session_id=self.session_id)


@dataclass
class _SymbolState:
    """Everything that must survive a bar boundary, and a restart."""

    symbol: str
    session_id: str | None = None
    last_finalized_end: str | None = None
    last_cumulative_volume: int | None = None
    last_cumulative_at: str | None = None
    last_order_key: tuple | None = None
    seen_keys: set = field(default_factory=set)
    accumulator: "_Accumulator | None" = None
    #: False until a baseline exists, so the first window of a mid-session
    #: connection cannot claim exact volume.
    baseline_established: bool = False


@dataclass
class _Accumulator:
    symbol: str
    start: str
    end: str
    session_id: str
    open: float
    high: float
    low: float
    close: float
    ticks: int = 0
    volume: int = 0
    volume_quality: VolumeQuality = "exact"

    def add_price(self, price: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.ticks += 1

    def to_bar(self, *, complete: bool) -> Bar:
        return Bar(symbol=self.symbol, start=self.start, end=self.end,
                   open=self.open, high=self.high, low=self.low,
                   close=self.close, ticks=self.ticks,
                   volume=(None if self.volume_quality in ("partial", "unavailable",
                                                           "uncertain")
                           else self.volume),
                   complete=complete, volume_quality=self.volume_quality,
                   session_id=self.session_id)


class BarBuilder:
    """Ticks in, closed bars out. Finalized windows never reopen."""

    def __init__(self, clock: MarketClock | None = None):
        self.clock = clock or MarketClock()
        self._state: dict[str, _SymbolState] = {}
        self.quarantined: list[dict] = []
        self.accepted_ticks = 0

    # ------------------------------------------------------------ helpers

    @property
    def late_ticks(self) -> int:
        return sum(1 for q in self.quarantined if q["reason"] == "late_finalized")

    @property
    def out_of_session_ticks(self) -> int:
        return sum(1 for q in self.quarantined if q["reason"] == "outside_session")

    def _quarantine(self, tick: Tick, reason: QuarantineReason, note: str = "") -> None:
        self.quarantined.append(dict(symbol=tick.symbol, ts=tick.ts, reason=reason,
                                     note=note, price=tick.last_price))

    def _window(self, ts: str):
        bounds = self.clock._bar_bounds(datetime.fromisoformat(ts))
        if bounds is None:
            return None
        start, end, _ = bounds
        return ist_timestamp(start), ist_timestamp(end)

    def _state_for(self, symbol: str) -> _SymbolState:
        return self._state.setdefault(symbol, _SymbolState(symbol=symbol))

    @staticmethod
    def _order_key(tick: Tick) -> tuple:
        # Provider sequence would be better; without one this is the documented
        # fallback. Two ticks identical in all of these are indistinguishable.
        return (tick.ts, tick.last_price, tick.volume_traded)

    # ---------------------------------------------------------------- add

    def add(self, ticks) -> list[Bar]:
        """Add ticks; return any bars that closed as a result."""
        closed: list[Bar] = []
        for tick in sorted(ticks, key=lambda t: (t.ts, t.symbol)):
            window = self._window(tick.ts)
            if window is None:
                self._quarantine(tick, "outside_session")
                continue
            start, end = window
            state = self._state_for(tick.symbol)
            session_id = tick.ts[:10]

            key = self._order_key(tick)
            if key in state.seen_keys:
                self._quarantine(tick, "duplicate",
                                 "identical timestamp, price and cumulative volume")
                continue

            # THE WATERMARK. A finalized window cannot reopen, whether or not
            # an accumulator currently exists for this symbol (R03).
            if state.last_finalized_end is not None and end <= state.last_finalized_end:
                self._quarantine(tick, "late_finalized",
                                 f"window ends {end}, already finalized through "
                                 f"{state.last_finalized_end}")
                continue

            if state.last_order_key is not None and key < state.last_order_key:
                self._quarantine(tick, "out_of_order")
                if state.accumulator is not None:
                    state.accumulator.volume_quality = "uncertain"
                continue

            if state.session_id != session_id:
                # New session: cumulative volume restarts at the exchange.
                state.session_id = session_id
                state.last_cumulative_volume = None
                state.last_cumulative_at = None
                state.baseline_established = False
                state.seen_keys.clear()

            if state.accumulator is not None and start > state.accumulator.start:
                closed.append(self._finalize(state))
            if state.accumulator is None:
                state.accumulator = _Accumulator(
                    symbol=tick.symbol, start=start, end=end, session_id=session_id,
                    open=tick.last_price, high=tick.last_price,
                    low=tick.last_price, close=tick.last_price,
                    volume_quality="exact" if state.baseline_established
                    else "partial")

            self._apply_volume(state, tick)
            state.accumulator.add_price(tick.last_price)
            state.last_order_key = key
            state.seen_keys.add(key)
            self.accepted_ticks += 1
        return closed

    def _apply_volume(self, state: _SymbolState, tick: Tick) -> None:
        """Volume is the increment since the previous observation — across
        bar boundaries, not from this bar's first tick."""
        accumulator = state.accumulator
        if tick.volume_traded is None:
            if accumulator.volume_quality == "exact":
                accumulator.volume_quality = "unavailable"
            return
        if state.last_cumulative_volume is None:
            # No baseline: we joined mid-session, or this is the day's first
            # observation. We cannot know what traded before it.
            state.last_cumulative_volume = tick.volume_traded
            state.last_cumulative_at = tick.ts
            if not state.baseline_established:
                accumulator.volume_quality = "partial"
            state.baseline_established = True
            return
        delta = tick.volume_traded - state.last_cumulative_volume
        if delta < 0:
            self._quarantine(tick, "volume_reset_or_revision",
                             f"cumulative volume fell from "
                             f"{state.last_cumulative_volume} to {tick.volume_traded}")
            accumulator.volume_quality = "uncertain"
        else:
            accumulator.volume += delta
        state.last_cumulative_volume = tick.volume_traded
        state.last_cumulative_at = tick.ts

    def _finalize(self, state: _SymbolState) -> Bar:
        accumulator = state.accumulator
        bar = accumulator.to_bar(complete=True)
        state.last_finalized_end = accumulator.end
        state.accumulator = None
        return bar

    # --------------------------------------------------------------- close

    def close_elapsed(self, at: datetime | None = None) -> list[Bar]:
        """Close every bar whose window has fully elapsed.

        Called on a timer, so a bar closes at its boundary even when no
        further tick arrives — a thin symbol must not hold a bar open.
        """
        stamp = ist_timestamp(at or self.clock.now())
        closed = []
        for state in self._state.values():
            if state.accumulator is not None and stamp >= state.accumulator.end:
                closed.append(self._finalize(state))
        return closed

    def partial(self) -> list[Bar]:
        """The in-flight bars. Marked incomplete; display only."""
        return [s.accumulator.to_bar(complete=False)
                for s in self._state.values() if s.accumulator is not None]

    # ----------------------------------------------------------- recovery

    def snapshot(self) -> dict:
        """Everything needed to resume without reopening a finalized window."""
        return dict(
            version=1,
            symbols={
                symbol: dict(
                    session_id=s.session_id,
                    last_finalized_end=s.last_finalized_end,
                    last_cumulative_volume=s.last_cumulative_volume,
                    last_cumulative_at=s.last_cumulative_at,
                    baseline_established=s.baseline_established,
                    open_accumulator=(
                        None if s.accumulator is None else dict(
                            start=s.accumulator.start, end=s.accumulator.end,
                            session_id=s.accumulator.session_id,
                            open=s.accumulator.open, high=s.accumulator.high,
                            low=s.accumulator.low, close=s.accumulator.close,
                            ticks=s.accumulator.ticks, volume=s.accumulator.volume,
                            volume_quality=s.accumulator.volume_quality)))
                for symbol, s in self._state.items()},
            accepted_ticks=self.accepted_ticks)

    def restore(self, snapshot: dict) -> None:
        if snapshot.get("version") != 1:
            raise ValueError(f"unsupported bar snapshot version "
                             f"{snapshot.get('version')!r}; rebuild rather than "
                             f"restore a shape this build does not understand")
        self._state.clear()
        for symbol, payload in snapshot.get("symbols", {}).items():
            state = _SymbolState(
                symbol=symbol, session_id=payload.get("session_id"),
                last_finalized_end=payload.get("last_finalized_end"),
                last_cumulative_volume=payload.get("last_cumulative_volume"),
                last_cumulative_at=payload.get("last_cumulative_at"),
                baseline_established=payload.get("baseline_established", False))
            open_bar = payload.get("open_accumulator")
            if open_bar:
                state.accumulator = _Accumulator(symbol=symbol, **open_bar)
            self._state[symbol] = state
        self.accepted_ticks = snapshot.get("accepted_ticks", 0)

    def watermark(self, symbol: str) -> str | None:
        state = self._state.get(symbol)
        return state.last_finalized_end if state else None

    def describe(self) -> dict:
        reasons: dict[str, int] = {}
        for q in self.quarantined:
            reasons[q["reason"]] = reasons.get(q["reason"], 0) + 1
        return dict(open_bars=sum(1 for s in self._state.values()
                                  if s.accumulator is not None),
                    symbols=len(self._state),
                    accepted_ticks=self.accepted_ticks,
                    quarantined=len(self.quarantined),
                    quarantine_reasons=reasons,
                    late_ticks=self.late_ticks,
                    out_of_session_ticks=self.out_of_session_ticks,
                    watermarks={s: st.last_finalized_end
                                for s, st in self._state.items()},
                    note=("a finalized window cannot reopen, with or without an "
                          "open accumulator and across restart; volume is the "
                          "increment since the previous observation, carried "
                          "across bar boundaries"))
