# product_types — information time (PRODUCT-CONTRACTS §1, rule 2)
"""Five distinct times, and the replay bound they exist to enforce.

A news story, a macro release and a model fit each have several times, and
collapsing them is how hindsight leaks into a replay:

* `occurred_at`   — when the thing in the world happened
* `effective_at`  — when it takes effect (a tariff announced today, effective
                    in 30 days)
* `published_at`  — when the source published it
* `first_seen_at` — when SERAPH could first have had it. **The replay bound.**
* `evaluated_at`  — the decision time a derived value was produced for

`published_at` is NOT the replay bound. A source can publish at 09:00 and a
poller reach it at 11:40; a replay at 10:00 that uses the 09:00 story is using
information the system did not have. `first_seen_at` is the only honest bound,
and it is recorded at acquisition, never back-filled from the publication time.

It can also run the other way. The Federal Register places documents on public
inspection and schedules publication one to three business days ahead, so a
document SERAPH is already holding carries a `published_at` in the future.
Such a datum is knowable now and bounded by `first_seen_at` like any other;
only its publication date is a schedule rather than a past event, which
`publication_scheduled` records and `is_forthcoming` reports. Filtering on
publication would hide a document already in hand and then present it days
later as if it had just arrived.
"""
from __future__ import annotations

from dataclasses import dataclass

from seraph.shared_types import ISOTimestamp


class ReplayBoundViolation(RuntimeError):
    """A replay tried to read information it could not have had."""


@dataclass(frozen=True)
class Timing:
    """The times a product datum carries. Only `first_seen_at` is mandatory
    for externally sourced data, because only it bounds a replay."""

    first_seen_at: ISOTimestamp | None = None
    published_at: ISOTimestamp | None = None
    occurred_at: ISOTimestamp | None = None
    effective_at: ISOTimestamp | None = None
    evaluated_at: ISOTimestamp | None = None
    #: The source assigns a publication date that has not arrived yet. The
    #: Federal Register places a document on public inspection and schedules
    #: it one to three business days ahead, so a document we hold today can
    #: carry a `published_at` two days out. Set at ACQUISITION, where
    #: `first_seen_at` is the current instant and a later `published_at` can
    #: therefore only be a future date -- never inferred at read time, where
    #: the same two timestamps cannot be told apart from a back-fill.
    publication_scheduled: bool = False

    def __post_init__(self) -> None:
        if (self.first_seen_at and self.published_at
                and self.first_seen_at < self.published_at
                and not self.publication_scheduled):
            # Two of the three cases are errors: a skewed clock, or a
            # back-filled `first_seen_at` that makes hindsight look like
            # information the system held. The third -- a publication date
            # still in the future -- is legitimate and must say so.
            raise ValueError(
                f"first_seen_at {self.first_seen_at} precedes published_at "
                f"{self.published_at}: a source cannot be read before it "
                f"publishes, unless the publication is scheduled "
                f"(publication_scheduled=True)")

    def is_forthcoming(self, as_of: ISOTimestamp) -> bool:
        """Has the official publication date not arrived yet?

        A forthcoming document is fully knowable -- it bounds replay by
        `first_seen_at` like anything else -- but its publication date is a
        schedule, not a past event, and must not be shown as one.
        """
        return bool(self.published_at) and self.published_at > as_of

    def visible_at(self, decision_ts: ISOTimestamp) -> bool:
        """Could this datum have been known at `decision_ts`?

        No `first_seen_at` means the datum is not externally sourced (a pure
        computation, a user's own input), so there is nothing to withhold.
        """
        if self.first_seen_at is None:
            return True
        return self.first_seen_at <= decision_ts

    def describe(self) -> dict:
        described = {k: v for k, v in dict(
            first_seen_at=self.first_seen_at, published_at=self.published_at,
            occurred_at=self.occurred_at, effective_at=self.effective_at,
            evaluated_at=self.evaluated_at).items() if v is not None}
        if self.publication_scheduled:
            # Travels with the times, so nothing downstream reads a scheduled
            # date as a date that has passed.
            described["publication_scheduled"] = True
        return described


def visible_at(timing: Timing | None, decision_ts: ISOTimestamp) -> bool:
    return True if timing is None else timing.visible_at(decision_ts)


@dataclass(frozen=True)
class InformationClock:
    """Filters a stream of timed items to what was knowable at a decision.

    `strict=True` raises instead of filtering, which is what a replay harness
    wants: silently dropping a future item hides a bug in the caller, while
    raising names it.
    """

    decision_ts: ISOTimestamp
    strict: bool = False

    def admits(self, timing: Timing | None) -> bool:
        if visible_at(timing, self.decision_ts):
            return True
        if self.strict:
            raise ReplayBoundViolation(
                f"item first seen at {timing.first_seen_at} is not available at "
                f"the decision time {self.decision_ts}")
        return False

    def filter(self, items, timing_of):
        """Keep only items knowable at the decision time."""
        return [item for item in items if self.admits(timing_of(item))]
