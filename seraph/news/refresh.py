"""Acquisition on request, with a deadline that actually constrains it.

Three operations exist and must not be confused:

* **projection** — re-read the store and re-render. No network. This is what a
  display timer does, and it is not in this module.
* **acquisition** — contact sources. Requested, coalesced and rate-limited in
  the store, normally served by the worker. `acquire()` below is the body of
  that work, callable by the worker or, when no worker is alive, directly.
* **progress** — `NewsStore.acquisition_progress()`.

Conflating the first two is how a thirty-second display timer became a
thirty-second fetch storm multiplied by the number of open browser tabs.

**Why the deadline is per-source and not just a stopwatch.** Checking elapsed
time *between* sources constrains nothing: one feed that accepts the
connection and then dribbles bytes holds the whole pass open for as long as it
likes, and the budget is noticed only afterwards. The remaining budget is
therefore converted into a socket timeout for each fetch.

**Five outcomes, kept apart**, because they call for different actions:

  fetched    contacted, and it had something new
  unchanged  contacted, nothing new (a 304 or identical content)
  failed     contacted, and it answered with an error
  timed_out  did not answer inside the remaining budget
  skipped    never contacted — the budget ran out first
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RefreshOutcome:
    """What an acquisition pass did, with each outcome named separately."""

    started_at: str
    fetched: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    failed: dict = field(default_factory=dict)
    timed_out: tuple[str, ...] = ()
    skipped_for_budget: tuple[str, ...] = ()
    new_stories: int = 0
    seconds: float = 0.0
    budget_seconds: float = 0.0

    @property
    def polled(self) -> tuple[str, ...]:
        """Every source actually contacted, whatever the outcome."""
        return tuple(self.fetched) + tuple(self.unchanged) + tuple(self.failed) \
            + tuple(self.timed_out)

    @property
    def complete(self) -> bool:
        return not self.skipped_for_budget and not self.timed_out

    def describe(self) -> dict:
        return dict(
            started_at=self.started_at, fetched=list(self.fetched),
            unchanged=list(self.unchanged), failed=dict(self.failed),
            timed_out=list(self.timed_out),
            skipped_for_budget=list(self.skipped_for_budget),
            polled=list(self.polled), new_stories=self.new_stories,
            seconds=round(self.seconds, 2), budget_seconds=self.budget_seconds,
            complete=self.complete,
            note=("`skipped_for_budget` were NEVER CONTACTED and their data is "
                  "exactly as old as before; `timed_out` did not answer in the "
                  "time left; `failed` answered with an error. These are "
                  "different facts and none of them is 'refreshed'"))


#: The timeout a source gets when there is plenty of budget. Below this a
#: fetch starts failing sources that are merely distant rather than broken.
_PREFERRED_FLOOR = 3.0

#: Below this much remaining budget, starting another source is not worth it:
#: it would be cut off almost immediately and reported as a timeout it was
#: never given a fair chance to avoid. Deliberately much smaller than the
#: preferred floor -- using the floor here meant a 3-second budget skipped
#: every source after the first.
_MIN_START = 1.0


def _per_source_timeout(remaining: float, sources_left: int,
                        *, floor: float = _PREFERRED_FLOOR,
                        ceiling: float = 15.0) -> float:
    """How long this one source may have.

    Divided by the number still to contact so one slow feed cannot consume
    everything, then floored — a timeout under a few seconds fails sources
    that are merely distant rather than broken.
    """
    share = remaining / max(1, sources_left)
    # The floor is itself clamped by what is left. An unclamped floor is
    # longer than the remaining budget whenever the budget is small, so the
    # last source overshoots the whole pass on its own.
    return min(ceiling, remaining, max(floor, share))


def acquire(store, fetcher, *, now: str, budget_seconds: float = 20.0,
            force: bool = True, clock=time.monotonic,
            on_progress=None, on_report=None) -> RefreshOutcome:
    """Contact sources until the budget is spent.

    `force=True`: an explicit request asks for the data to be checked **now**,
    not for the schedule to be consulted. Honouring the schedule here would
    reproduce the original defect, where the button appeared to work and
    changed nothing.

    Ordering is most-overdue first, so a spent budget costs the freshest
    sources rather than the stalest.
    """
    started = clock()
    sources = list(store.sources())

    def staleness(source) -> float:
        health = store.health_at(source.source_id, now)
        if health.last_success_at is None:
            return float("inf")
        try:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%S%z"
            age = (datetime.strptime(now, fmt)
                   - datetime.strptime(health.last_success_at, fmt))
            return age.total_seconds() / 60 / max(1, source.poll_interval_minutes)
        except (ValueError, TypeError):
            return 0.0

    sources.sort(key=staleness, reverse=True)
    if not force:
        due = {s.source_id for s in store.due_sources(now)}
        sources = [s for s in sources if s.source_id in due]

    fetched, unchanged, timed_out, skipped = [], [], [], []
    failed, new_stories = {}, 0

    for index, source in enumerate(sources):
        remaining = budget_seconds - (clock() - started)
        # Do not START work that cannot finish. A source begun with less than
        # the minimum timeout left overruns the budget by its own timeout and
        # is likely to be cut off anyway, so it is reported as not contacted
        # -- which is true -- rather than as a timeout it was never given a
        # fair chance to avoid.
        if remaining < _MIN_START:
            skipped.append(source.source_id)
            continue

        # The remaining budget becomes this fetch's socket timeout, so a feed
        # that stops sending cannot hold the pass open past the deadline.
        timeout = _per_source_timeout(remaining, len(sources) - index)
        previous = getattr(fetcher, "deadline_timeout", None)
        try:
            fetcher.deadline_timeout = timeout
        except AttributeError:
            pass                       # a plain callable fetcher; nothing to set

        # All adapters share the HTTP transport, including RSS fallback and
        # document/listing routers. Propagate an ABSOLUTE deadline through
        # that graph: restarting a relative socket timeout on every retry or
        # document used to multiply the advertised budget.
        import time
        deadline = time.monotonic() + timeout
        stack, touched, seen = [fetcher], [], set()
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            try:
                touched.append((node, getattr(node, 'deadline_at', None)))
                node.deadline_at = deadline
            except AttributeError:
                continue
            stack.extend(x for x in (getattr(node, 'fallback', None),
                                      getattr(node, '_http', None)) if x is not None)
        try:
            report = store.ingest(source.source_id, fetcher, now=now)
        finally:
            for node, prior in touched:
                node.deadline_at = prior
            try:
                fetcher.deadline_timeout = previous
            except AttributeError:
                pass

        if not report.ok:
            message = str(report.error or "")
            if "timed out" in message.lower() or "timeout" in message.lower():
                timed_out.append(source.source_id)
            else:
                failed[source.source_id] = report.error
        elif report.new_stories:
            fetched.append(source.source_id)
            new_stories += report.new_stories
        else:
            unchanged.append(source.source_id)

        if on_report is not None:
            on_report(report)
        if on_progress is not None:
            on_progress(dict(done=index + 1, total=len(sources),
                             source=source.source_id,
                             seconds=round(clock() - started, 2)))

    return RefreshOutcome(
        started_at=now, fetched=tuple(fetched), unchanged=tuple(unchanged),
        failed=failed, timed_out=tuple(timed_out),
        skipped_for_budget=tuple(skipped), new_stories=new_stories,
        seconds=clock() - started, budget_seconds=budget_seconds)


#: Kept so existing callers and tests keep working; `acquire` is the name that
#: says what it does.
refresh_now = acquire
