# C8 — Reconciliation Layer (FR25–FR27): explicit process/staleness clock.
"""Elapsed five-minute units, with a declared calendar approximation.

The default market clock counts regular NSE session time on weekdays. This
is NOT an exchange holiday calendar. Pass exact session dates for historical
replay; an explicit list also permits exceptional weekend sessions, using
the regular hours. Special shortened sessions need a richer calendar model.
Calendar time is a separate opt-in model whose Q must be calibrated in its
own units. No arbitrary overnight/weekend process noise is silently added.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from seraph.shared_types import IST

BAR_SECONDS = 300.0


@dataclass(frozen=True)
class ReconciliationClock:
    time_basis: str = "trading"
    session_dates: frozenset[date] | None = None

    def __post_init__(self) -> None:
        if self.time_basis not in ("trading", "calendar"):
            raise ValueError("time_basis must be 'trading' or 'calendar'")
        if self.time_basis == "calendar" and self.session_dates is not None:
            raise ValueError("session_dates applies only to the trading clock")
        if self.session_dates is not None and any(
            not isinstance(d, date) or isinstance(d, datetime) for d in self.session_dates
        ):
            raise ValueError("session_dates must contain datetime.date instances")

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
                opening = datetime.combine(day, time(9, 15), tzinfo=IST)
                closing = datetime.combine(day, time(15, 30), tzinfo=IST)
                seconds += max(0.0, (min(end, closing) - max(start, opening)).total_seconds())
            day += timedelta(days=1)
        return seconds / BAR_SECONDS
