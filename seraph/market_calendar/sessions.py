# Market/session calendar (FIX01) — session hours and the decision clock.
"""Explicit NSE equity session hours, and the decision clock built on them.

Why this exists
---------------
The historical replay previously evaluated every session at a hardcoded 15:30
IST and selected pillar inputs by calendar date. Real sessions are not all
09:15-15:30: Diwali Muhurat trading is a one-hour evening or afternoon session,
and the exchange has run Saturday special live sessions with two short windows.
A refit stamped 18:55 IST on a Muhurat day is a perfectly valid observation that
a fixed 15:30 clock reads as a future timestamp, which aborted the whole replay.

The future-information guard is NOT relaxed here
------------------------------------------------
An observation whose vintage falls after the decision timestamp is *withheld*,
not accepted: the caller records a transient `not_yet_available` absence and
uses the most recent earlier vintage. A registry entry that declares a close
too EARLY is therefore safe (it only withholds information). A registry entry
that declares a close too LATE is the real risk, which is what
`evidence_status` and `corroborating_observation` exist to bound.

Registry completeness
---------------------
`SPECIAL_SESSIONS` is deliberately **partial**. It registers only sessions this
repository holds direct evidence for — an archived observation whose IST
timestamp falls outside regular hours. Other historical special sessions exist
and are not registered; they fall back to regular hours. Replacing this
registry with an ingested official exchange calendar is Phase 5 work
(`docs/DEVELOPMENT-PLAN.md`). `SessionCalendar.completeness()` reports this
honestly so a run manifest can carry it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal, Mapping

from seraph.shared_types import IST

#: Regular NSE equity session, IST.
REGULAR_OPEN = time(9, 15)
REGULAR_CLOSE = time(15, 30)

SessionKind = Literal["regular", "muhurat", "special_live", "short"]
EvidenceStatus = Literal["declared", "verified_against_exchange_notice"]

#: Decision-clock policies. `session_close` evaluates at the session's actual
#: close (so an authorised special-session close may use that session's own
#: later vintage). `standard_1530` pins every decision to the regular close,
#: which answers "what was already available at the regular close?".
DECISION_POLICIES = ("session_close", "standard_1530")


def _parse_hms(value: str) -> time:
    hh, mm, ss = (int(part) for part in value.split(":"))
    return time(hh, mm, ss)


@dataclass(frozen=True)
class TradingSession:
    """One dated session's trading windows and the evidence behind them."""

    date: str                                   # YYYY-MM-DD
    windows: tuple[tuple[str, str], ...]        # ordered, disjoint (open, close) HH:MM:SS IST
    kind: SessionKind
    evidence: str
    evidence_status: EvidenceStatus = "declared"
    corroborating_observation: str | None = None   # archived IST timestamp inside this session

    def __post_init__(self) -> None:
        if not self.windows:
            raise ValueError(f"{self.date}: a session needs at least one window")
        previous_end: time | None = None
        for opening, closing in self.windows:
            start, end = _parse_hms(opening), _parse_hms(closing)
            if end <= start:
                raise ValueError(f"{self.date}: window {opening}-{closing} does not advance")
            if previous_end is not None and start < previous_end:
                raise ValueError(f"{self.date}: windows must be ordered and disjoint")
            previous_end = end
        if self.corroborating_observation is not None:
            # A declared close must not contradict evidence already in the repo.
            observed = datetime.fromisoformat(self.corroborating_observation)
            if observed.date().isoformat() != self.date:
                raise ValueError(f"{self.date}: corroborating observation is on another date")
            if not (_parse_hms(self.windows[0][0]) <= observed.timetz().replace(tzinfo=None)
                    <= _parse_hms(self.close)):
                raise ValueError(
                    f"{self.date}: declared session does not contain its corroborating "
                    f"observation {self.corroborating_observation}"
                )

    @property
    def open(self) -> str:
        return self.windows[0][0]

    @property
    def close(self) -> str:
        return self.windows[-1][1]

    def hours(self) -> tuple[tuple[time, time], ...]:
        return tuple((_parse_hms(a), _parse_hms(b)) for a, b in self.windows)


#: Sessions whose hours deviate from the regular session AND for which this
#: repository holds a corroborating out-of-hours observation. Close times are
#: `declared` from exchange session notices; each is lower-bounded by the
#: archived refit timestamp named in `corroborating_observation`, which is
#: checked above. None has been verified against an ingested exchange notice.
SPECIAL_SESSIONS: tuple[TradingSession, ...] = (
    TradingSession(
        date="2024-03-02",
        windows=(("09:15:00", "10:00:00"), ("11:30:00", "12:30:00")),
        kind="special_live",
        evidence="Saturday special live trading session (primary then disaster-recovery "
                 "window). Corroborated by an archived Hawkes refit at 12:25 IST, outside "
                 "regular hours, in research_data/original_hawkes.parquet.",
        corroborating_observation="2024-03-02T12:25:00+05:30",
    ),
    TradingSession(
        date="2024-05-18",
        windows=(("09:15:00", "10:00:00"), ("11:30:00", "12:30:00")),
        kind="special_live",
        evidence="Saturday special live trading session (primary then disaster-recovery "
                 "window). Corroborated by an archived Hawkes refit at 12:25 IST.",
        corroborating_observation="2024-05-18T12:25:00+05:30",
    ),
    TradingSession(
        date="2024-11-01",
        windows=(("18:00:00", "19:00:00"),),
        kind="muhurat",
        evidence="Diwali Muhurat trading, a one-hour evening session. Corroborated by an "
                 "archived Hawkes refit at 18:55 IST — the observation a fixed 15:30 "
                 "decision clock misread as a future timestamp (audit finding A01).",
        corroborating_observation="2024-11-01T18:55:00+05:30",
    ),
    TradingSession(
        date="2025-10-21",
        windows=(("13:45:00", "14:45:00"),),
        kind="muhurat",
        evidence="Diwali Muhurat trading, a one-hour afternoon session. Corroborated by an "
                 "archived Hawkes refit at 14:40 IST.",
        corroborating_observation="2025-10-21T14:40:00+05:30",
    ),
)


class SessionCalendar:
    """Session hours for a set of trading dates.

    Unregistered dates use the regular session. `session_dates` is optional and
    only narrows which dates are considered sessions at all.
    """

    def __init__(
        self,
        *,
        sessions: tuple[TradingSession, ...] = SPECIAL_SESSIONS,
        session_dates: "frozenset[str] | set[str] | tuple[str, ...] | None" = None,
    ) -> None:
        self._special: dict[str, TradingSession] = {}
        for item in sessions:
            if item.date in self._special:
                raise ValueError(f"duplicate session registry entry for {item.date}")
            self._special[item.date] = item
        self._dates = frozenset(session_dates) if session_dates is not None else None

    # ------------------------------------------------------------- lookups

    def verified_for(self, day: str) -> bool:
        """Publication eligibility for a specific date, not all past history."""
        return not self.completeness()['completeness'].startswith('PARTIAL')

    def is_session(self, day: str) -> bool:
        if self._dates is not None:
            return day in self._dates
        return self.is_special(day) or date.fromisoformat(day).weekday() < 5

    def session(self, day: str) -> TradingSession:
        known = self._special.get(day)
        if known is not None:
            return known
        return TradingSession(
            date=day,
            windows=((REGULAR_OPEN.isoformat(), REGULAR_CLOSE.isoformat()),),
            kind="regular",
            evidence="Regular NSE equity session; no registry deviation for this date.",
            evidence_status="declared",
        )

    def is_special(self, day: str) -> bool:
        return day in self._special

    def close_timestamp(self, day: str) -> str:
        return f"{day}T{self.session(day).close}+05:30"

    def open_timestamp(self, day: str) -> str:
        return f"{day}T{self.session(day).open}+05:30"

    def hours_map(self) -> Mapping[date, tuple[tuple[time, time], ...]]:
        """Per-date trading windows for C8's staleness clock.

        Only registered deviations are returned; the clock applies regular hours
        to every other session, exactly as before this calendar existed.
        """
        return {date.fromisoformat(d): s.hours() for d, s in self._special.items()}

    def registered(self) -> tuple[TradingSession, ...]:
        return tuple(self._special[d] for d in sorted(self._special))

    def completeness(self) -> dict:
        """Honest description of this registry, for run manifests."""
        applicable = [
            s for s in self.registered()
            if self._dates is None or s.date in self._dates
        ]
        return dict(
            registry="seraph/market_calendar/sessions.py::SPECIAL_SESSIONS",
            regular_session=f"{REGULAR_OPEN.isoformat()}-{REGULAR_CLOSE.isoformat()} IST",
            registered_deviations=[
                dict(date=s.date, kind=s.kind, windows=list(s.windows),
                     evidence_status=s.evidence_status,
                     corroborating_observation=s.corroborating_observation)
                for s in applicable
            ],
            completeness="PARTIAL — only sessions corroborated by an out-of-hours "
                         "observation already in this repository are registered. Other "
                         "historical special sessions fall back to regular hours. An "
                         "ingested official exchange calendar is outstanding "
                         "(docs/DEVELOPMENT-PLAN.md Phase 5).",
            evidence_status="declared; no exchange notice has been ingested",
        )


class DecisionClock:
    """Maps a session date to the timestamp a decision is evaluated at."""

    def __init__(self, calendar: SessionCalendar, policy: str = "session_close") -> None:
        if policy not in DECISION_POLICIES:
            raise ValueError(f"policy must be one of {DECISION_POLICIES}, got {policy!r}")
        self.calendar = calendar
        self.policy = policy

    def decision_timestamp(self, day: str) -> str:
        if self.policy == "standard_1530":
            return f"{day}T{REGULAR_CLOSE.isoformat()}+05:30"
        return self.calendar.close_timestamp(day)

    def describe(self) -> dict:
        return dict(
            policy=self.policy,
            meaning={
                "session_close": "evaluated at the session's declared close; an authorised "
                                 "special-session close may use that session's own vintage",
                "standard_1530": "evaluated at the regular 15:30 IST close; a later "
                                 "special-session vintage is withheld as not yet available",
            }[self.policy],
            session_calendar=self.calendar.completeness(),
        )


def to_ist(day: str, hms: str) -> datetime:
    """`day` + `hms` as an aware IST datetime."""
    return datetime.combine(date.fromisoformat(day), _parse_hms(hms), tzinfo=IST)
