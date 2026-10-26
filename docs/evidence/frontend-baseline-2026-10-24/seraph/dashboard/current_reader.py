# C12 — the current-result reader (T08, audit finding R12).
"""Read what the runtime has actually decided, and say how healthy it is.

**The defect (R12).** The console read persisted *archive runs* and nothing
else. There was no path from a live decision to the screen, so the only thing
a viewer could ever see was a replay — and because the replay and a live
reading rendered identically, nothing on screen said which it was.

Three separations this module exists to hold:

1. **The latest score and the worker's health are different facts.** A worker
   that has stopped does not make the last score disappear; a worker that is
   healthy does not make a stale score current. They are returned side by
   side and never folded into one "status".

2. **An outage does not reissue the last score.** The last valid decision
   stays inspectable *with its own timestamp*, explicitly marked as the last
   one rather than re-stamped as now. Re-dating a stale score is the single
   most dangerous thing a dashboard can do.

3. **The view mode is chosen, never fallen back to.** `live`, `replay` and
   `demo` are a first-class selector. Asking for `live` when no live decision
   exists returns an empty live result saying so — it does **not** quietly
   serve an archive run and let it look current.

**Polling.** `revision()` is a cheap, stable string that changes exactly when
something the screen shows has changed: the stream head, the latest decision
and the news revision. The UI polls that and only rebuilds when it moves, so a
two-second refresh does not thrash the camera, the selection or a half-typed
form.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from seraph.shared_types import IST, ist_timestamp

READER_VERSION = "c12.current_reader/2026-10-17.1"

ViewMode = Literal["live", "replay", "demo"]
VIEW_MODES: tuple[ViewMode, ...] = ("live", "replay", "demo")

#: Beyond this, a worker that has not completed a pass is reported stale. It
#: is a reporting threshold, not a publication gate — T01 owns that.
DEFAULT_WORKER_STALE_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class WorkerHealth:
    """Is the runtime running? Separate from whether a score is any good."""

    state: str
    last_pass_at: str | None
    stream_version: int
    undelivered_events: int
    dead_letters: int
    stale: bool
    note: str

    def describe(self) -> dict:
        return dict(state=self.state, last_pass_at=self.last_pass_at,
                    stream_version=self.stream_version,
                    undelivered_events=self.undelivered_events,
                    dead_letters=self.dead_letters, stale=self.stale,
                    note=self.note)


@dataclass(frozen=True)
class CurrentResult:
    """The latest decision in the requested mode, and what it may be called."""

    mode: ViewMode
    decision_id: str | None
    as_of: str | None
    computed_at: str | None
    publication_state: str | None
    payload: dict | None
    is_current: bool
    age_seconds: float | None
    reason: str
    health: WorkerHealth
    version: str = READER_VERSION

    def describe(self) -> dict:
        return dict(
            version=self.version, mode=self.mode,
            decision_id=self.decision_id, as_of=self.as_of,
            computed_at=self.computed_at,
            publication_state=self.publication_state,
            is_current=self.is_current, age_seconds=self.age_seconds,
            reason=self.reason, payload=self.payload,
            health=self.health.describe())


def worker_health(store, *, lifecycle_state: str = "unknown",
                  now: datetime | None = None,
                  stale_after: timedelta = DEFAULT_WORKER_STALE_AFTER
                  ) -> WorkerHealth:
    moment = now or datetime.now(IST)
    head = store.head()
    status = store.describe()
    last = head.updated_at
    stale = True
    if last:
        age = (moment - datetime.fromisoformat(last)).total_seconds()
        stale = age > stale_after.total_seconds()
    note = ("the worker has never committed a pass" if last is None
            else "no pass has completed recently; the score below is the last "
                 "one and is NOT re-dated" if stale
            else "the worker is committing passes")
    return WorkerHealth(
        state=lifecycle_state, last_pass_at=last,
        stream_version=head.version,
        undelivered_events=status["undelivered_events"],
        dead_letters=status["dead_letters"], stale=stale, note=note)


def read_current(store, *, mode: ViewMode = "live",
                 now: datetime | None = None,
                 lifecycle_state: str = "unknown",
                 max_age: timedelta | None = None) -> CurrentResult:
    """The latest decision for this mode. No silent fallback between modes."""
    if mode not in VIEW_MODES:
        raise ValueError(
            f"unknown view mode {mode!r}; the three are {', '.join(VIEW_MODES)}")
    moment = now or datetime.now(IST)
    health = worker_health(store, lifecycle_state=lifecycle_state, now=moment)

    if mode == "demo":
        return CurrentResult(
            mode=mode, decision_id=None, as_of=None, computed_at=None,
            publication_state=None, payload=None, is_current=False,
            age_seconds=None, health=health,
            reason=("demo mode shows the illustrative dataset only. It is "
                    "never a reading of the market and no live decision is "
                    "consulted"))

    latest = store.latest_decision()
    if latest is None:
        return CurrentResult(
            mode=mode, decision_id=None, as_of=None, computed_at=None,
            publication_state=None, payload=None, is_current=False,
            age_seconds=None, health=health,
            reason=("no decision has been committed in this runtime. Asking "
                    "for live does NOT fall back to an archive run — an "
                    "archive run is a replay and would be mislabelled here"))

    as_of = datetime.fromisoformat(latest["as_of"])
    age = (moment - as_of).total_seconds()
    publishable = latest["publication_state"] == "current"
    too_old = max_age is not None and age > max_age.total_seconds()
    # A decision stamped AFTER now is not fresh data — it is a clock or data
    # defect. Reporting it as "-340 min old" and letting it through is the
    # same mistake the market clock already refuses for observations.
    from_the_future = age < 0
    is_current = bool(mode == "live" and publishable and not too_old
                      and not from_the_future and not health.stale)

    if from_the_future and mode == "live":
        reason = (f"the last decision is timestamped {abs(age) / 60:.0f} "
                  f"minutes in the FUTURE. That is a clock or data defect, "
                  f"not fresh data, and nothing may be published from it")
    elif mode == "replay":
        reason = ("replay mode: this decision is shown as a replay whatever "
                  "its publication state says")
    elif not publishable:
        reason = ("the runtime withheld this decision; it is inspectable but "
                  "is not a current reading")
    elif too_old:
        reason = (f"the last decision is {age / 60:.0f} minutes old, beyond "
                  f"the age this view will call current. It is shown with its "
                  f"own timestamp and is NOT re-dated")
    elif health.stale:
        reason = ("the worker has not committed a pass recently, so the last "
                  "decision is shown as the LAST one, with its own timestamp. "
                  "It is NOT re-dated")
    else:
        reason = "current reading from the live runtime"

    return CurrentResult(
        mode=mode, decision_id=latest["decision_id"], as_of=latest["as_of"],
        computed_at=latest["computed_at"],
        publication_state=latest["publication_state"],
        payload=latest["payload"], is_current=is_current,
        age_seconds=round(age, 1), reason=reason, health=health)


def revision(store, *, news_revision: str | None = None) -> str:
    """A cheap id that moves exactly when the screen's content moves.

    The UI polls this. Rebuilding the page on every tick would discard the
    camera, the selection and any half-typed form; rebuilding only when this
    changes keeps a two-second poll cheap and non-destructive.
    """
    head = store.head()
    payload = "|".join([
        str(head.version), head.decision_id or "-", head.checkpoint_id or "-",
        news_revision or "-"])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class RefreshGate:
    """Decide whether new data may replace what is on screen.

    A data-only refresh is applied silently. A refresh that would move the
    baseline a user is editing is **not**: it is announced, and applying it is
    an explicit act. Silently rebasing a form under someone's hands is how a
    dashboard loses an edit and never says it did.
    """

    revision: str | None = None
    pending_revision: str | None = None
    editing: bool = False
    notices: list = field(default_factory=list)

    def offer(self, new_revision: str, *, at: datetime | None = None) -> dict:
        stamp = ist_timestamp(at or datetime.now(IST))
        if new_revision == self.revision:
            return dict(action="unchanged", revision=self.revision)
        if self.editing:
            self.pending_revision = new_revision
            notice = dict(at=stamp, revision=new_revision,
                          message=("newer data is available. It has not been "
                                   "applied because a form is being edited; "
                                   "apply it explicitly to change the baseline"))
            self.notices.append(notice)
            return dict(action="held", **notice)
        self.revision = new_revision
        self.pending_revision = None
        return dict(action="applied", revision=new_revision, at=stamp)

    def apply_pending(self, *, at: datetime | None = None) -> dict:
        if self.pending_revision is None:
            return dict(action="nothing_pending", revision=self.revision)
        self.revision = self.pending_revision
        self.pending_revision = None
        self.editing = False
        return dict(action="applied", revision=self.revision,
                    at=ist_timestamp(at or datetime.now(IST)))

    def describe(self) -> dict:
        return dict(revision=self.revision,
                    pending_revision=self.pending_revision,
                    editing=self.editing,
                    has_newer_data=self.pending_revision is not None,
                    notices=self.notices[-5:])
