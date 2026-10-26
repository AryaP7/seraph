# Live — the session lifecycle (T07, audit finding R04).
"""What state the runtime is in, and what it is allowed to do there.

**Why a state machine and not a few booleans.** The audit's R04 was that the
live path had no lifecycle at all: it connected, polled, and had no answer to
"are we warmed up", "did we drain the session before deciding it was over",
"is this a reconnect or a cold start". Those questions were answered
implicitly by whichever branch ran, which is how a restart silently produced
decisions from an empty filter.

The states, and the one rule each exists to enforce:

``initializing``      nothing has been read yet; nothing may be published.
``restoring``         a checkpoint is being validated. A failed validation
                      goes to ``warming_up``, never to ``collecting``.
``warming_up``        rebuilding from history because there was no usable
                      checkpoint. Publication is refused for want of warmup,
                      which is the T01 gate's own reason code.
``connecting``        the feed is being attached. Not yet a session.
``waiting_session``   the market is shut. `next_open` says when it is not, and
                      a later window on the same day counts.
``collecting``        the session is open and bars are being finalized.
``draining_session``  the session's scheduled close has passed and the feed is
                      being polled out. **A session is not over because the
                      clock says so** — a late tick for the final bar arrives
                      after the close, and deciding too early loses it.
``checkpointed``      the drain finished and state was committed.
``reconnecting``      the feed dropped mid-session. Bars keep their
                      watermark; nothing finalized reopens.
``degraded``          running, but something required is missing. Explicitly
                      not ``stopped``: a degraded runtime still records what
                      it can, and still refuses to publish.
``stopped``           deliberate end.

**Publication is a property of the state, not of the caller's optimism.**
`may_publish` is false everywhere except ``collecting`` and
``draining_session``, and even there the T01 gate gets the final word.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Literal

from seraph.shared_types import IST, ist_timestamp

LIFECYCLE_VERSION = "live.lifecycle/2026-10-17.1"

State = Literal[
    "initializing", "restoring", "warming_up", "connecting", "waiting_session",
    "collecting", "draining_session", "checkpointed", "reconnecting",
    "degraded", "stopped",
]

#: Which transitions are legal. A move that is not here is a bug in the
#: caller, and raising beats silently ending up in a state nothing expects.
TRANSITIONS: "dict[str, tuple[str, ...]]" = {
    "initializing": ("restoring", "warming_up", "degraded", "stopped"),
    "restoring": ("warming_up", "connecting", "degraded", "stopped"),
    "warming_up": ("connecting", "degraded", "stopped"),
    "connecting": ("waiting_session", "collecting", "reconnecting",
                   "degraded", "stopped"),
    "waiting_session": ("collecting", "connecting", "reconnecting",
                        "degraded", "stopped"),
    "collecting": ("draining_session", "reconnecting", "degraded", "stopped"),
    "draining_session": ("checkpointed", "reconnecting", "degraded", "stopped"),
    "checkpointed": ("waiting_session", "collecting", "connecting",
                     "degraded", "stopped"),
    "reconnecting": ("collecting", "waiting_session", "connecting",
                     "degraded", "stopped"),
    "degraded": ("connecting", "waiting_session", "collecting",
                 "reconnecting", "warming_up", "stopped"),
    "stopped": (),
}

#: Only these two states are even candidates for a current reading. The T01
#: publication gate still decides; this is the floor, not the ceiling.
PUBLISHING_STATES = ("collecting", "draining_session")

#: How long to keep polling after the scheduled close before calling the
#: session drained. A late tick for the final bar is the normal case, not an
#: anomaly, and ending the session at the close timestamp loses it.
DEFAULT_DRAIN_SECONDS = 90.0

#: In-memory history is bounded. Durable history is the decision table; a
#: status ring that grows all day is a leak pretending to be an audit trail.
HISTORY_LIMIT = 200


class LifecycleError(RuntimeError):
    """An illegal transition, or an operation this state does not allow."""


@dataclass(frozen=True)
class Transition:
    at: str
    frm: State
    to: State
    reason: str

    def describe(self) -> dict:
        return dict(at=self.at, **{"from": self.frm}, to=self.to,
                    reason=self.reason)


@dataclass
class SessionLifecycle:
    """The runtime's state, its legal moves, and a bounded history."""

    state: State = "initializing"
    drain_seconds: float = DEFAULT_DRAIN_SECONDS
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_LIMIT))
    degraded_reasons: tuple = ()
    session_id: str | None = None
    drain_started_at: str | None = None

    # ----------------------------------------------------------- transitions

    def to(self, state: State, *, reason: str = "",
           at: datetime | None = None) -> Transition:
        if state not in TRANSITIONS:
            raise LifecycleError(f"unknown lifecycle state {state!r}")
        allowed = TRANSITIONS[self.state]
        if state != self.state and state not in allowed:
            raise LifecycleError(
                f"{self.state} -> {state} is not a legal transition; from "
                f"{self.state} the runtime may go to "
                f"{', '.join(allowed) or 'nowhere'}")
        moved = Transition(at=ist_timestamp(at or datetime.now(IST)),
                           frm=self.state, to=state, reason=reason)
        self.history.append(moved)
        self.state = state
        if state != "degraded":
            self.degraded_reasons = ()
        return moved

    def degrade(self, reasons: "Iterable[str]", *,
                at: datetime | None = None) -> Transition:
        """Keep running, record what is missing, and refuse to publish."""
        reasons = tuple(reasons)
        if not reasons:
            raise LifecycleError(
                "degraded without a reason is just a worse word for running")
        moved = self.to("degraded", reason="; ".join(reasons), at=at)
        self.degraded_reasons = reasons
        return moved

    # ------------------------------------------------------------- sessions

    def open_session(self, session_id: str, *, at: datetime | None = None
                     ) -> Transition:
        self.session_id = session_id
        self.drain_started_at = None
        return self.to("collecting", reason=f"session {session_id} open", at=at)

    def begin_drain(self, *, at: datetime | None = None) -> Transition:
        moment = at or datetime.now(IST)
        self.drain_started_at = ist_timestamp(moment)
        return self.to("draining_session",
                       reason="scheduled close passed; polling out", at=moment)

    def drain_complete(self, *, at: datetime | None = None,
                       last_tick_at: str | None = None) -> bool:
        """Has the drain window elapsed since the last thing we heard?

        Measured from the later of the drain start and the last tick, so a
        feed still delivering keeps the session open rather than being cut
        off by a fixed timer.
        """
        if self.state != "draining_session" or self.drain_started_at is None:
            return False
        moment = at or datetime.now(IST)
        since = max([datetime.fromisoformat(self.drain_started_at)]
                    + ([datetime.fromisoformat(last_tick_at)]
                       if last_tick_at else []))
        return (moment - since).total_seconds() >= self.drain_seconds

    def close_session(self, *, at: datetime | None = None) -> Transition:
        if self.state != "draining_session":
            raise LifecycleError(
                f"a session is closed from draining_session, not from "
                f"{self.state}: the feed must be polled out first, because a "
                f"late tick for the final bar is the normal case")
        return self.to("checkpointed",
                       reason=f"session {self.session_id} drained and committed",
                       at=at)

    # --------------------------------------------------------------- queries

    @property
    def may_publish(self) -> bool:
        return self.state in PUBLISHING_STATES

    @property
    def is_running(self) -> bool:
        return self.state != "stopped"

    def why_not_publishing(self) -> str | None:
        if self.may_publish:
            return None
        if self.state == "degraded":
            return ("the runtime is degraded: "
                    + "; ".join(self.degraded_reasons))
        return {
            "initializing": "nothing has been read yet",
            "restoring": "a checkpoint is still being validated",
            "warming_up": "history is still being rebuilt",
            "connecting": "the feed is not attached yet",
            "waiting_session": "the market is not open",
            "checkpointed": "the session is over and state is committed",
            "reconnecting": "the feed dropped and is being re-attached",
            "stopped": "the runtime was stopped",
        }.get(self.state, f"state {self.state}")

    def describe(self) -> dict:
        return dict(
            version=LIFECYCLE_VERSION, state=self.state,
            session_id=self.session_id,
            may_publish=self.may_publish,
            why_not=self.why_not_publishing(),
            degraded_reasons=list(self.degraded_reasons),
            drain_started_at=self.drain_started_at,
            allowed_next=list(TRANSITIONS[self.state]),
            history=[t.describe() for t in list(self.history)[-12:]],
            history_bound=self.history.maxlen,
            history_note=("in-memory history is bounded; the durable record "
                          "is the decision table, not this ring"),
        )


def next_session_window(clock, *, at: datetime | None = None) -> dict:
    """When the market is next open, including a later window the same day.

    The plan calls this out because the obvious implementation takes the
    day's FIRST window and reports the market shut for the rest of a
    two-window special session.
    """
    moment = at or clock.now()
    opens = clock.next_open(moment)
    state = clock.state(moment)
    verified = clock.calendar.verified_for(moment.date().isoformat())
    return dict(
        now=ist_timestamp(moment), market_state=state.get("state"),
        next_open=opens,
        calendar_verified=verified,
        calendar_note=(None if verified else
                       "calendar coverage is incomplete, so no confident "
                       "current label may be derived from it"),
        seconds_to_open=(
            (datetime.fromisoformat(opens) - moment).total_seconds()
            if opens else None))
