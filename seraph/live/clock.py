# Live — the market clock (FR39, NFR1)
"""Is the market open *right now*, and when does the current bar close?

Everything SERAPH has computed so far is a replay: a date is chosen, a
decision timestamp is derived from it, and the pipeline runs. A live score
inverts that — the clock decides when a decision happens, and the answer has
to be right about three things the replay never had to care about:

* **Whether the market is open at all.** A score emitted at 02:00 on a Sunday
  is not a market risk score. `state()` distinguishes `pre_open`, `open`,
  `closed_for_day`, `not_a_session` and `after_cutoff`.
* **Which bar is in flight.** A 5-minute bar that has not closed yet is
  incomplete, and feeding a partial bar to a jump detector produces a jump
  that un-happens a few minutes later. `current_bar()` returns the bar being
  accumulated; `last_closed_bar()` returns the newest one that is safe to use.
* **How far behind the data is.** This is the one that matters most here,
  because the corpus ends well before today. `DataRecency` makes the gap a
  first-class value that a caller must handle, so a score computed from
  two-month-old inputs can never be presented as current.

Built on `seraph.market_calendar`, so Muhurat and short sessions are already
right: the live clock inherits the session registry rather than re-deciding
when the market closes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from seraph.market_calendar import SessionCalendar
from seraph.shared_types import IST, ist_timestamp

#: NSE equity bar size for the intraday pillar path.
BAR_MINUTES = 5

MarketState = Literal["pre_open", "open", "closed_for_day", "not_a_session",
                      "after_cutoff"]

Recency = Literal["live", "delayed", "stale", "historical_only"]


@dataclass(frozen=True)
class DataRecency:
    """How old the newest usable observation is, and what that permits.

    `historical_only` is not a degraded live mode. It means the newest data
    predates today's session entirely, so nothing computed from it is a
    statement about the market now — it is a replay, and must be labelled one.
    """

    newest_observation: str | None
    now: str
    age_minutes: float | None
    state: Recency
    note: str

    @property
    def is_live(self) -> bool:
        return self.state == "live"

    @property
    def may_publish_as_current(self) -> bool:
        """Only `live` and `delayed` describe the market now."""
        return self.state in ("live", "delayed")

    def describe(self) -> dict:
        return dict(newest_observation=self.newest_observation, now=self.now,
                    age_minutes=self.age_minutes, state=self.state,
                    is_live=self.is_live,
                    may_publish_as_current=self.may_publish_as_current,
                    note=self.note)


@dataclass(frozen=True)
class BarWindow:
    start: str
    end: str
    index: int

    def contains(self, moment: str) -> bool:
        return self.start <= moment < self.end


class MarketClock:
    """Where the market is, right now, on this machine's wall clock."""

    def __init__(self, calendar: SessionCalendar | None = None, *,
                 bar_minutes: int = BAR_MINUTES,
                 delayed_after_minutes: int = 15,
                 stale_after_minutes: int = 90):
        self.calendar = calendar or SessionCalendar()
        self.bar_minutes = bar_minutes
        self.delayed_after_minutes = delayed_after_minutes
        self.stale_after_minutes = stale_after_minutes

    # ------------------------------------------------------------- basics

    @staticmethod
    def now() -> datetime:
        return datetime.now(IST).replace(microsecond=0)

    def _windows(self, day: str) -> list[tuple[datetime, datetime]]:
        session = self.calendar.session(day)
        out = []
        for opening, closing in session.hours():
            out.append((datetime.combine(date.fromisoformat(day), opening, tzinfo=IST),
                        datetime.combine(date.fromisoformat(day), closing, tzinfo=IST)))
        return out

    def is_session(self, day: str) -> bool:
        """Whether `day` trades.

        Without an ingested exchange calendar this is weekday-plus-registry,
        and it says so: a market holiday that is not in the registry reads as
        a session with no data, which the recency check then catches. It never
        silently invents trading on a holiday.
        """
        if self.calendar.is_special(day):
            return True
        return date.fromisoformat(day).weekday() < 5

    # -------------------------------------------------------------- state

    def state(self, at: datetime | None = None) -> dict:
        moment = at or self.now()
        day = moment.date().isoformat()
        stamp = ist_timestamp(moment)
        if not self.is_session(day):
            return dict(state="not_a_session", at=stamp, day=day,
                        next_open=self.next_open(moment),
                        note="not a trading day by the weekday rule and the session "
                             "registry; an unregistered exchange holiday would also "
                             "land here only if it falls on a weekend")
        windows = self._windows(day)
        session = self.calendar.session(day)
        first_open, last_close = windows[0][0], windows[-1][1]
        if moment < first_open:
            return dict(state="pre_open", at=stamp, day=day,
                        opens_at=ist_timestamp(first_open),
                        minutes_to_open=round((first_open - moment).total_seconds() / 60, 1),
                        session_kind=session.kind)
        if moment >= last_close:
            return dict(state="closed_for_day", at=stamp, day=day,
                        closed_at=ist_timestamp(last_close),
                        session_kind=session.kind,
                        next_open=self.next_open(moment))
        for opening, closing in windows:
            if opening <= moment < closing:
                return dict(state="open", at=stamp, day=day,
                            window=(ist_timestamp(opening), ist_timestamp(closing)),
                            session_kind=session.kind,
                            minutes_to_close=round((closing - moment).total_seconds() / 60, 1),
                            current_bar=self.current_bar(moment),
                            last_closed_bar=self.last_closed_bar(moment))
        # Between two windows of a split session (the DR-site break).
        return dict(state="pre_open", at=stamp, day=day, session_kind=session.kind,
                    opens_at=ist_timestamp(next(o for o, _ in windows if o > moment)),
                    note="between two windows of a split session")

    def is_open(self, at: datetime | None = None) -> bool:
        return self.state(at)["state"] == "open"

    def next_open(self, at: datetime | None = None, *, horizon_days: int = 10
                  ) -> str | None:
        moment = at or self.now()
        for offset in range(0, horizon_days + 1):
            day = (moment.date() + timedelta(days=offset)).isoformat()
            if not self.is_session(day):
                continue
            # EVERY window, not just the day's first. On the two-window
            # special sessions (2024-03-02, 2024-05-18) the next open during
            # the lunch gap is that afternoon, not the following morning —
            # taking `[0]` reported the market shut for the rest of the day.
            for opening, _close in self._windows(day):
                if opening > moment:
                    return ist_timestamp(opening)
        return None

    # --------------------------------------------------------------- bars

    def _bar_bounds(self, moment: datetime) -> tuple[datetime, datetime, int] | None:
        day = moment.date().isoformat()
        if not self.is_session(day):
            return None
        index = 0
        for opening, closing in self._windows(day):
            if moment < opening:
                return None
            span = int((closing - opening).total_seconds() // 60)
            bars = span // self.bar_minutes
            if moment >= closing:
                index += bars
                continue
            offset = int((moment - opening).total_seconds() // 60) // self.bar_minutes
            start = opening + timedelta(minutes=offset * self.bar_minutes)
            return start, start + timedelta(minutes=self.bar_minutes), index + offset
        return None

    def current_bar(self, at: datetime | None = None) -> dict | None:
        """The bar being accumulated right now. **Incomplete.**"""
        bounds = self._bar_bounds(at or self.now())
        if bounds is None:
            return None
        start, end, index = bounds
        return dict(start=ist_timestamp(start), end=ist_timestamp(end), index=index,
                    complete=False,
                    note="this bar is still filling; a partial bar must not reach "
                         "a jump detector")

    def last_closed_bar(self, at: datetime | None = None) -> dict | None:
        """The newest bar that is safe to compute on."""
        moment = at or self.now()
        bounds = self._bar_bounds(moment)
        if bounds is None:
            day = moment.date().isoformat()
            if self.is_session(day):
                windows = self._windows(day)
                if moment >= windows[-1][1]:
                    end = windows[-1][1]
                    return dict(start=ist_timestamp(end - timedelta(minutes=self.bar_minutes)),
                                end=ist_timestamp(end), index=-1, complete=True,
                                note="final bar of a closed session")
            return None
        start, _, index = bounds
        if index == 0:
            return None
        previous = start - timedelta(minutes=self.bar_minutes)
        return dict(start=ist_timestamp(previous), end=ist_timestamp(start),
                    index=index - 1, complete=True)

    def seconds_to_bar_close(self, at: datetime | None = None) -> float | None:
        moment = at or self.now()
        bounds = self._bar_bounds(moment)
        if bounds is None:
            return None
        return (bounds[1] - moment).total_seconds()

    # ----------------------------------------------------------- recency

    def recency(self, newest_observation: str | None, *,
                at: datetime | None = None) -> DataRecency:
        """How old the data is, and whether it may be called current.

        This is the gate the whole live path hangs on. With the corpus ending
        2026-08-21 and today in October, every score is `historical_only` —
        and that is the honest answer, not a degraded live one.
        """
        moment = at or self.now()
        stamp = ist_timestamp(moment)
        if newest_observation is None:
            return DataRecency(
                None, stamp, None, "historical_only",
                "no observation at all; nothing can be said about the market now")
        age = (moment - datetime.fromisoformat(newest_observation)).total_seconds() / 60
        if age < 0:
            # T01 / audit finding R02: a future observation used to come back
            # `live` with age -1435 minutes and permission to publish. An
            # observation from the future is not fresh data, it is a broken
            # clock or a corrupt record, and it fails closed.
            return DataRecency(
                newest_observation, stamp, round(age, 1), "historical_only",
                f"the newest observation is timestamped {abs(age):.0f} minutes in "
                f"the FUTURE. That is a clock or data defect, not fresh data; "
                f"nothing may be published from it")
        today = moment.date().isoformat()
        if newest_observation[:10] < today and not self.is_open(moment):
            # Yesterday's close, out of hours, is the correct current reading.
            if age <= 24 * 60 * 3:
                return DataRecency(
                    newest_observation, stamp, round(age, 1), "delayed",
                    "the market is closed; the last session's close is the current "
                    "reading")
        if newest_observation[:10] < today and age > 24 * 60:
            days = age / (24 * 60)
            return DataRecency(
                newest_observation, stamp, round(age, 1), "historical_only",
                f"the newest observation is {days:.1f} days old. Anything computed "
                f"from it is a REPLAY of that period, not a statement about the "
                f"market now, and must be labelled as such")
        if age <= self.delayed_after_minutes:
            return DataRecency(newest_observation, stamp, round(age, 1), "live",
                               f"newest observation {age:.0f}min old")
        if age <= self.stale_after_minutes:
            return DataRecency(
                newest_observation, stamp, round(age, 1), "delayed",
                f"newest observation {age:.0f}min old, past the "
                f"{self.delayed_after_minutes}min live threshold")
        return DataRecency(
            newest_observation, stamp, round(age, 1), "stale",
            f"newest observation {age:.0f}min old, past the "
            f"{self.stale_after_minutes}min staleness limit; the feed is not "
            f"keeping up and this is not a current reading")

    def describe(self, newest_observation: str | None = None,
                 at: datetime | None = None) -> dict:
        moment = at or self.now()
        return dict(clock=self.state(moment),
                    recency=self.recency(newest_observation, at=moment).describe(),
                    bar_minutes=self.bar_minutes,
                    calendar=self.calendar.completeness())
