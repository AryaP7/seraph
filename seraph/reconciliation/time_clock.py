# C8 — Reconciliation Layer (FR25–FR27): explicit process/staleness clock.
"""Elapsed five-minute units, with a declared calendar approximation.

The default market clock counts regular NSE session time on weekdays. This
is NOT an exchange holiday calendar. Pass exact session dates for historical
replay; an explicit list also permits exceptional weekend sessions, using
the regular hours.

`session_hours` (FIX01) supplies exact trading windows for the sessions that
deviate from regular hours — Muhurat evening sessions and the exchange's
two-window special live sessions. Dates absent from the mapping keep the
regular 09:15-15:30 window, so omitting it reproduces the previous behaviour
exactly. `seraph.market_calendar.SessionCalendar.hours_map()` builds it; this
module takes a plain mapping so C8 keeps no dependency on that package.

Calendar time is a separate opt-in model whose Q must be calibrated in its
own units. No arbitrary overnight/weekend process noise is silently added.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from types import MappingProxyType
from typing import Mapping

from seraph.shared_types import IST

BAR_SECONDS = 300.0

REGULAR_WINDOWS: tuple[tuple[time, time], ...] = ((time(9, 15), time(15, 30)),)

_EMPTY_HOURS: Mapping[date, tuple[tuple[time, time], ...]] = MappingProxyType({})


@dataclass(frozen=True)
class ReconciliationClock:
    time_basis: str = "trading"
    session_dates: frozenset[date] | None = None
    session_hours: Mapping[date, tuple[tuple[time, time], ...]] = field(
        default=_EMPTY_HOURS
    )

    def __post_init__(self) -> None:
        if self.time_basis not in ("trading", "calendar"):
            raise ValueError("time_basis must be 'trading' or 'calendar'")
        if self.time_basis == "calendar" and self.session_dates is not None:
            raise ValueError("session_dates applies only to the trading clock")
        if self.time_basis == "calendar" and self.session_hours:
            raise ValueError("session_hours applies only to the trading clock")
        if self.session_dates is not None and any(
            not isinstance(d, date) or isinstance(d, datetime) for d in self.session_dates
        ):
            raise ValueError("session_dates must contain datetime.date instances")
        for day, windows in self.session_hours.items():
            if not isinstance(day, date) or isinstance(day, datetime):
                raise ValueError("session_hours keys must be datetime.date instances")
            if not windows or any(len(w) != 2 or w[1] <= w[0] for w in windows):
                raise ValueError(f"session_hours[{day}] must hold ordered (open, close) windows")

    def windows_for(self, day: date) -> tuple[tuple[time, time], ...]:
        return self.session_hours.get(day, REGULAR_WINDOWS)

    def elapsed_bars(self, start: datetime, end: datetime) -> float:
        if end <= start:
            return 0.0
        if self.time_basis == "calendar":
            return (end - start).total_seconds() / BAR_SECONDS
        start, end = start.astimezone(IST), end.astimezone(IST)
        day = start.date()
        seconds = 0.0
        while day <= end.date():
            is_session = (day in self.session_dates if self.session_dates is not None
                          else day.weekday() < 5)
            if is_session:
                for window_open, window_close in self.windows_for(day):
                    opening = datetime.combine(day, window_open, tzinfo=IST)
                    closing = datetime.combine(day, window_close, tzinfo=IST)
                    seconds += max(0.0, (min(end, closing) - max(start, opening)).total_seconds())
            day += timedelta(days=1)
        return seconds / BAR_SECONDS
