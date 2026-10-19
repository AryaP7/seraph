"""Recovering from downtime, and admitting when recovery is impossible.

A poller down for six hours restarts and fetches "the latest items". Whether
that recovers the gap depends entirely on the source:

* The **Federal Register** API takes an explicit publication-date range and
  pages through it. A gap of any length is recoverable, exactly.
* An **RSS feed** returns the publisher's latest N items. If more than N were
  published during the outage, the earlier ones are *gone*, not delayed.

Three things this module has to get right, each of which it got wrong first:

**The gap must be recorded before it becomes invisible.** Gap detection read
`source_health.last_success_at`. The first successful poll after an outage
overwrites that — so the evidence of the gap is destroyed by the act of
resuming, and a console that came back up showed a tidy list with no hint that
six hours of circulars are missing. Gaps are now persisted as their own rows,
opened the moment one is observed, and closed only when the interval has
actually been covered.

**A backfill must keep the source's own filters.** The URL builder took
`base_url.split("?", 1)[0]`, which discarded `conditions[term]=India` — so
backfilling the India-filtered feed would have pulled the entire US federal
register into a store that had never asked for it. Query parameters are now
preserved except the ones being replaced.

**Truncation is not completion.** Paging stops at a cap. Stopping at the cap
and reporting success claims an interval was covered when it was not, so the
cap returns a continuation cursor and the gap stays open.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: Sources whose API accepts an explicit date range and pages through it.
#: Membership is a claim about the SOURCE's capability, deliberately a short
#: allow-list: assuming a feed supports backfill and silently missing items is
#: the failure this file exists to prevent.
BACKFILLABLE = {
    "federal_register": "publication_date range + per_page paging",
    "federal_register_india": "publication_date range + per_page paging",
}

#: Roughly how many items a feed exposes at once. Used only to say how much of
#: a gap an un-backfillable source could plausibly have covered. An estimate,
#: labelled as one.
TYPICAL_WINDOW_ITEMS = 30

#: Query parameters the backfill replaces. Everything else on the source's own
#: URL is preserved, because it is part of what the source IS.
_REPLACED_PARAMS = {"per_page", "page", "order",
                    "conditions[publication_date][gte]",
                    "conditions[publication_date][lte]"}


@dataclass(frozen=True)
class Gap:
    """A period during which a source was not collected."""

    source_id: str
    since: str | None
    until: str
    minutes: float | None
    recoverable: bool
    method: str
    note: str

    def describe(self) -> dict:
        return dict(source_id=self.source_id, since=self.since, until=self.until,
                    minutes=None if self.minutes is None else round(self.minutes, 1),
                    recoverable=self.recoverable, method=self.method,
                    note=self.note)


def _minutes(later: str, earlier: str) -> float | None:
    try:
        fmt = "%Y-%m-%dT%H:%M:%S%z"
        return (datetime.strptime(later, fmt)
                - datetime.strptime(earlier, fmt)).total_seconds() / 60
    except (ValueError, TypeError):
        return None


def gaps_at(store, decision_ts: str, *, slack_multiple: float = 2.0
            ) -> list[Gap]:
    """Every source whose last successful fetch is older than it should be.

    `slack_multiple` is deliberately smaller than the 3x allowance
    `coverage_at` uses for *health*. A gap is a statement about COLLECTION, so
    a source that missed a scheduled poll has a real gap while still counting
    as healthy.
    """
    out: list[Gap] = []
    for source in store.sources():
        health = store.health_at(source.source_id, decision_ts)
        since = health.last_success_at
        if since is None:
            out.append(Gap(
                source_id=source.source_id, since=None, until=decision_ts,
                minutes=None,
                recoverable=source.source_id in BACKFILLABLE,
                method=BACKFILLABLE.get(source.source_id, "none"),
                note=("never successfully fetched: everything this source has "
                      "ever published is outside the corpus")))
            continue
        elapsed = _minutes(decision_ts, since)
        if elapsed is None:
            continue
        if elapsed <= source.poll_interval_minutes * slack_multiple:
            continue

        missed = elapsed / max(1, source.poll_interval_minutes)
        if source.source_id in BACKFILLABLE:
            note = (f"{missed:.0f} scheduled polls missed; this source accepts "
                    f"a publication-date range, so the gap is recoverable "
                    f"exactly")
        else:
            note = (f"{missed:.0f} scheduled polls missed. This feed exposes "
                    f"only its latest items (~{TYPICAL_WINDOW_ITEMS}), so "
                    f"anything it published and rotated out during the gap is "
                    f"PERMANENTLY missing, not merely late. Counts computed "
                    f"over this period are computed over a corpus with a hole "
                    f"in it")
        out.append(Gap(
            source_id=source.source_id, since=since, until=decision_ts,
            minutes=elapsed, recoverable=source.source_id in BACKFILLABLE,
            method=BACKFILLABLE.get(source.source_id, "none"), note=note))
    return out


def record_gaps(store, decision_ts: str) -> list[dict]:
    """Persist observed gaps BEFORE any polling can hide them.

    `source_health.last_success_at` is overwritten by the first successful
    poll after an outage, so detection that reads only health destroys its own
    evidence by resuming. Calling this first makes the gap durable.
    """
    opened = []
    for gap in gaps_at(store, decision_ts):
        row = store.open_gap(source_id=gap.source_id, since=gap.since,
                             until=gap.until, recoverable=gap.recoverable,
                             note=gap.note)
        if row:
            opened.append(row)
    return opened


def federal_register_backfill_urls(base_url: str, since: str, until: str, *,
                                   per_page: int = 100, max_pages: int = 20,
                                   start_page: int = 1) -> list[str]:
    """Page URLs covering an explicit publication-date range.

    **The source's own query parameters are preserved.** Taking
    `base_url.split("?")[0]` discarded `conditions[term]=India`, which would
    have backfilled the entire US federal register into a store that had only
    ever asked for the India-filtered subset.

    `start_page` resumes a truncated run from a stored cursor.
    """
    parts = urlsplit(base_url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k not in _REPLACED_PARAMS]
    start, end = since[:10], until[:10]

    urls = []
    for page in range(start_page, start_page + max_pages):
        query = kept + [
            ("per_page", str(per_page)), ("page", str(page)),
            # Oldest first: paging newest-first over a corpus that is still
            # growing revisits and skips rows.
            ("order", "oldest"),
            ("conditions[publication_date][gte]", start),
            ("conditions[publication_date][lte]", end),
        ]
        urls.append(urlunsplit((parts.scheme, parts.netloc, parts.path,
                                urlencode(query, safe="[]"), "")))
    return urls


def plan_backfill(store, decision_ts: str) -> dict:
    """What a backfill would do, without doing it."""
    found = gaps_at(store, decision_ts)
    return dict(
        decision_ts=decision_ts,
        gaps=[g.describe() for g in found],
        recoverable=[g.source_id for g in found if g.recoverable],
        unrecoverable=[g.source_id for g in found if not g.recoverable],
        note=("a source absent from `recoverable` cannot be backfilled by any "
              "amount of polling: its feed exposes only the latest items. The "
              "gap is reported so that a count computed over the period is "
              "known to be computed over an incomplete corpus"))
