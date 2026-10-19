"""Is this event still current, and how confident can we be that it is?

`aggregate_by` had no notion of age. A tariff announcement from six months ago
rolled into the sector panel with exactly the weight of one from this morning,
and the panel presented both as "what is happening".

Two things could have been built here, and only one of them is honest.

**Not built: magnitude decay.** Nothing in this system carries a loss estimate
— every edge is unsized and every direction is qualitative. Multiplying a
non-existent quantity by a half-life nobody fitted would manufacture precision
out of a decay constant chosen to look reasonable.

**Built: a declared relevance horizon per event class, and an age band.** How
long a piece of news remains *current* is a property of what kind of news it
is, and it can be stated and argued with rather than fitted to anything.

The crucial asymmetry, and the reason this is not just "drop anything older
than N days": **a measure that is in force does not expire.** An anti-dumping
duty order from 2024 that has not been revoked is current today — it is
currently costing an exporter money. An earthquake from 2024 is not. So the
rule is lifecycle-aware: an instrument whose legal status is `effective` or
`adopted`, and which has not been repealed, suspended or expired, stays
current regardless of age. Everything else ages out on its class's horizon.
"""
from __future__ import annotations

from datetime import datetime

#: How long an event of each class remains *current* for a reader asking
#: "what is happening now", in days. Declared, not fitted. Each is a claim
#: about the kind of news, and each is arguable — which is the point of
#: writing them down in one place rather than scattering `if age >` through
#: the aggregation.
HORIZONS_DAYS = {
    # A hazard is news while response and damage assessment run.
    "physical_hazard": 14,
    "logistics_disruption": 21,
    "production_halt": 30,
    "facility_incident": 30,
    # A rate decision governs conditions until the next meeting.
    "policy_rate_decision": 60,
    "liquidity_operation": 30,
    "reserve_requirement_change": 90,
    # Commentary ages quickly; it is a signal about intent, not an instrument.
    "official_speech": 21,
    "statistical_release": 45,
    # Proceedings run for months and their stages matter throughout.
    "trade_remedy_determination": 365,
    "securities_enforcement_action": 365,
    "regulatory_appeal": 365,
    "regulatory_action": 180,
    "prudential_norms_change": 365,
    "tariff_announcement": 365,
    "import_duty_change": 365,
    "export_restriction": 365,
    "sanctions_action": 365,
    "forex_regulation": 180,
    "bank_resolution": 180,
    "debt_instrument_event": 90,
    "subsidy_change": 365,
    "capacity_expansion": 180,
}

#: Used when a class has no declared horizon. Deliberately short: an
#: unrecognised event is the one we understand least, and quietly carrying it
#: forever is worse than ageing it out early where it can be noticed.
DEFAULT_HORIZON_DAYS = 90

#: Legal statuses that mean the instrument APPLIES RIGHT NOW. An event in one
#: of these states does not age out — it is not a report of something that
#: happened, it is a measure that is still operating.
IN_FORCE = frozenset({"effective", "adopted"})

#: Statuses that end an instrument. These age out normally once ended.
ENDED = frozenset({"repealed", "expired", "suspended"})

#: Lifecycles that remove an event from "what is happening" immediately,
#: whatever its age.
DEAD_LIFECYCLES = frozenset({"superseded", "retracted"})


def _days_between(later: str, earlier: str) -> float | None:
    try:
        fmt = "%Y-%m-%dT%H:%M:%S%z"
        return (datetime.strptime(later, fmt)
                - datetime.strptime(earlier, fmt)).total_seconds() / 86400
    except (ValueError, TypeError):
        return None


def horizon_days(event) -> int:
    return HORIZONS_DAYS.get(event.event_type, DEFAULT_HORIZON_DAYS)


def age_days(event, as_of: str) -> float | None:
    """Age from when SERAPH could first have known it.

    `first_seen_at`, not `published_at`: the same bound that governs replay
    governs currency, so an event cannot age from a date the system could not
    have seen.
    """
    seen = event.timing.first_seen_at if event.timing else None
    return _days_between(as_of, seen) if seen else None


def in_force(event, as_of: "str | None" = None) -> bool:
    """Is this measure applying at `as_of`?

    Delegates to `seraph.news.lifecycle`, which keeps the stages apart. This
    used to be a set membership test -- `policy_status in {effective,
    adopted}` -- which collapsed *decided* into *applying* and had no notion
    of a decision time at all. A 2024 determination therefore reported as
    currently operating, forever, and a measure effective in 2099 reported as
    operating today.
    """
    from seraph.news.lifecycle import applicability
    if as_of is None:
        # No decision time means the question cannot be answered. Returning
        # True here is what made every adopted measure permanent.
        return False
    return bool(applicability(event, as_of)["in_force"])


#: How much older than its first sighting a document must be before we call
#: it a late discovery rather than a current development. A day absorbs
#: ordinary publication lag and timezone edges.
LATE_DISCOVERY_DAYS = 1.0


def discovery(event, as_of: str) -> dict:
    """Is this a new development, or old news we only just received?

    Both are legitimately "first seen today", and the signal rail sorts by
    `first_seen_at`, so a backfilled document from last year appears at the
    top beside this morning's. They are different facts: one is something
    that just happened, the other is something we just learned.
    """
    timing = getattr(event, "timing", None)
    seen = getattr(timing, "first_seen_at", None) if timing else None
    published = getattr(timing, "published_at", None) if timing else None
    if not seen or not published:
        return dict(kind="unknown", lag_days=None,
                    basis="no publication time to compare with first sighting")
    lag = _days_between(seen, published)
    if lag is None:
        return dict(kind="unknown", lag_days=None,
                    basis="times could not be compared")
    if lag < 0:
        return dict(kind="forthcoming", lag_days=round(lag, 2),
                    basis="scheduled for publication after we received it")
    if lag <= LATE_DISCOVERY_DAYS:
        return dict(kind="current", lag_days=round(lag, 2),
                    basis="received close to publication")
    return dict(kind="late_discovery", lag_days=round(lag, 2),
                basis=(f"published {lag:.0f} days before we first saw it: this "
                       f"is old news newly received, not a new development"))


def currency(event, as_of: str) -> dict:
    """Whether the event is current, in what band, and why.

    Returns a reason in every case. A filter that drops an event without being
    able to say why is one nobody can audit.
    """
    lifecycle = getattr(event, "lifecycle", "active")
    if lifecycle in DEAD_LIFECYCLES:
        return dict(current=False, band="dead", age_days=None,
                    horizon_days=None, basis=f"lifecycle is {lifecycle}")

    age = age_days(event, as_of)
    horizon = horizon_days(event)

    if in_force(event, as_of):
        return dict(current=True, band="in_force",
                    age_days=None if age is None else round(age, 1),
                    horizon_days=None,
                    basis=("an instrument in force AT THIS DECISION TIME does "
                           "not age out: it is currently operating, not a "
                           "report of something that happened"))

    if age is None:
        return dict(current=True, band="unknown_age", age_days=None,
                    horizon_days=horizon,
                    basis="no first_seen_at, so age cannot be established; "
                          "kept rather than dropped on an unknown")

    if age <= horizon * 0.25:
        band = "fresh"
    elif age <= horizon * 0.5:
        band = "recent"
    elif age <= horizon:
        band = "ageing"
    else:
        band = "historic"

    return dict(current=band != "historic", age_days=round(age, 1), band=band,
                horizon_days=horizon, discovery=discovery(event, as_of),
                basis=(f"{event.event_type} has a declared relevance horizon "
                       f"of {horizon} days; this event is {age:.1f} days old"))


def partition(events, as_of: str, *, confirmed_links=None,
              rejected_links=None) -> dict:
    """Split events into those still current and those that have aged out.

    Nothing is deleted. The aged-out set is returned so a caller can say how
    many events it excluded and why, rather than silently narrowing.

    Supersession links are derived here from the identifiers the documents
    cite, plus whatever a reviewer has confirmed. The unresolved ones — a
    revocation that cites nothing we hold — travel back with the result,
    because an unlinked revocation leaves an old order reported as in force
    and that has to be visible rather than merely true.
    """
    from seraph.news.lifecycle import apply_supersession, link_instruments
    events = list(events)
    linkage = link_instruments(events, confirmed=confirmed_links,
                               rejected=rejected_links)
    applicability = apply_supersession(events, as_of, links=linkage['links'])
    current, expired = [], []
    for event in events:
        state = currency(event, as_of)
        legal = applicability[event.event_id]
        state['applicability'] = legal
        if legal['state'] in ('superseded', 'dead', 'ended'):
            state = dict(state, current=False, band=legal['state'], basis=legal['basis'])
        if not event.timing.visible_at(as_of):
            state = dict(state, current=False, band='not_available',
                         basis='event was not available at this decision time')
        (current if state["current"] else expired).append((event, state))
    return dict(
        current=[e for e, _ in current], expired=[e for e, _ in expired],
        states={e.event_id: s for e, s in current + expired},
        supersession=linkage,
        note=("expired events are excluded from 'what is happening now' and "
              "retained in the corpus. An instrument in force never expires, "
              "however old, because it is still operating"))
