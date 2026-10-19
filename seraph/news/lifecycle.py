"""Is this measure applying RIGHT NOW, at the decision time being asked about?

Three defects motivated this module, and the first two were mine.

**`adopted` was treated as in force.** A final determination is *decided*; a
measure begins applying when it takes effect, which may be weeks later or may
require a separate order. Collapsing the two meant a 2024 determination
reported as currently operating, and — because an in-force instrument never
ages out — reported so forever.

**A 2099 effective date still read as in force.** The earlier fix converted a
future `effective` to `adopted`, which was right, and then `adopted` was
itself in the in-force set. The downgrade only moved the problem one step.

**Applicability was evaluated once, at acquisition.** It has to be evaluated
against the decision time being asked about, or a replay of last year sees
this year's measures and a measure that has since been repealed still applies.

So the stages are kept apart — announced, adopted, effective-from, suspended,
expired, repealed, superseded — and `applicability(event, as_of)` answers the
only question a reader actually has: *does this apply at the moment I am
asking about?*

What this module will not do is guess. An instrument whose effective date
cannot be established is reported `decided_effect_unknown`, not promoted to
in force and not dismissed.
"""
from __future__ import annotations

from datetime import datetime

#: The document says the measure applies, as of its own publication.
STAGE_EFFECTIVE = "effective"
#: Decided, but applying only from a date that may not have arrived.
STAGE_ADOPTED = "adopted"
#: Announced or proposed: nothing applies yet.
STAGES_PENDING = frozenset({"announced", "proposed", "consultation", "unknown"})
#: The measure has stopped applying.
STAGES_ENDED = frozenset({"repealed", "expired", "suspended"})
#: Lifecycles that remove an event regardless of stage.
DEAD_LIFECYCLES = frozenset({"superseded", "retracted"})


def _before(a: str | None, b: str | None) -> bool | None:
    """Is `a` at or before `b`? None when either cannot be read."""
    if not a or not b:
        return None
    try:
        fmt = "%Y-%m-%dT%H:%M:%S%z"
        return datetime.strptime(a, fmt) <= datetime.strptime(b, fmt)
    except (ValueError, TypeError):
        return None


def effective_from(event) -> str | None:
    """The date the measure begins applying, if the document stated one."""
    timing = getattr(event, "timing", None)
    return getattr(timing, "effective_at", None) if timing else None


def applicability(event, as_of: str) -> dict:
    """Does this measure apply at `as_of`? With a reason, always.

    Returns `state` as one of:

      `in_force`                 applying at `as_of`
      `decided_not_yet_in_force` decided, with a known later effective date
      `decided_effect_unknown`   decided, effective date not established
      `pending`                  announced or proposed; nothing applies
      `ended`                    repealed, expired or suspended
      `dead`                     superseded or retracted
      `not_an_instrument`        no legal stage: this is not a measure
    """
    lifecycle = getattr(event, "lifecycle", "active")
    if lifecycle in DEAD_LIFECYCLES:
        return dict(state="dead", in_force=False, as_of=as_of,
                    basis=f"lifecycle is {lifecycle}")

    frame = getattr(event, "frame", None)
    stage = getattr(frame, "policy_status", None) if frame else None
    if stage is None:
        return dict(state="not_an_instrument", in_force=False, as_of=as_of,
                    basis="no frame, so no legal stage")

    if stage in STAGES_ENDED:
        return dict(state="ended", in_force=False, as_of=as_of, stage=stage,
                    basis=f"the measure is {stage} and no longer applies")

    starts = effective_from(event)

    if stage == STAGE_EFFECTIVE:
        if starts is None:
            # The document asserts it is in force as of its own publication.
            return dict(state="in_force", in_force=True, as_of=as_of,
                        stage=stage,
                        basis="the instrument states it is in force and names "
                              "no later start date")
        arrived = _before(starts, as_of)
        if arrived is None:
            return dict(state="decided_effect_unknown", in_force=False,
                        as_of=as_of, stage=stage, effective_from=starts,
                        basis=f"effective date {starts!r} could not be read; "
                              f"not assumed to have arrived")
        return dict(
            state="in_force" if arrived else "decided_not_yet_in_force",
            in_force=bool(arrived), as_of=as_of, stage=stage,
            effective_from=starts,
            basis=(f"effective from {starts}, which is "
                   f"{'on or before' if arrived else 'after'} {as_of}"))

    if stage == STAGE_ADOPTED:
        # Decided is NOT applying. A final determination is a decision; the
        # measure begins when it takes effect, which may need a separate
        # order. Treating the two as one reported a 2024 determination as
        # currently operating, forever.
        if starts is None:
            return dict(state="decided_effect_unknown", in_force=False,
                        as_of=as_of, stage=stage,
                        basis="decided, but the document names no effective "
                              "date: whether it applies now is not established")
        arrived = _before(starts, as_of)
        if arrived is None:
            return dict(state="decided_effect_unknown", in_force=False,
                        as_of=as_of, stage=stage, effective_from=starts,
                        basis=f"effective date {starts!r} could not be read")
        return dict(
            state="in_force" if arrived else "decided_not_yet_in_force",
            in_force=bool(arrived), as_of=as_of, stage=stage,
            effective_from=starts,
            basis=(f"decided, effective from {starts}, which is "
                   f"{'on or before' if arrived else 'after'} {as_of}"))

    if stage in STAGES_PENDING:
        return dict(state="pending", in_force=False, as_of=as_of, stage=stage,
                    basis=f"stage is {stage}: nothing applies yet")

    return dict(state="not_an_instrument", in_force=False, as_of=as_of,
                stage=stage, basis=f"unrecognised legal stage {stage!r}")


def link_instruments(events, *, confirmed=None, rejected=None) -> dict:
    """Link documents about the SAME instrument, on cited identifiers only.

    `supersedes` was only ever set by a caller that already knew the
    answer, so an antidumping duty order and a separately published
    revocation of it sat in the store unlinked and the order went on
    being reported as in force. Two things are needed to fix that, and
    only one of them is linkage:

    * **A link made of evidence.** Two documents are the same instrument
      when they CITE the same identifier — a case number, an investigation
      number, a notification number. A shared headline is not evidence: on
      this corpus one product-and-country headline covers a proposal, a
      preliminary determination, a final determination, an order, several
      administrative reviews and a revocation, and merging on it would
      destroy the distinctions the whole lifecycle module exists to keep.

    * **A warning when there is no evidence.** The far more common case is
      a terminating document that cites nothing we hold. Leaving it silent
      is what let the old order stand. It becomes an `unresolved` item: a
      named review task, not a guess in either direction.

    `confirmed` and `rejected` carry human decisions — `{(later, earlier)}`
    pairs — so a reviewer can establish a link the documents did not, and
    can throw out one the identifiers got wrong.
    """
    from seraph.news.extraction import STAGE_LADDER, TERMINATING_STAGES, AMENDS
    events = sorted(events, key=lambda e: (getattr(getattr(e, 'timing', None),
                                                   'first_seen_at', '') or '',
                                           e.event_id))
    confirmed = {tuple(pair) for pair in (confirmed or ())}
    rejected = {tuple(pair) for pair in (rejected or ())}

    by_id: dict[str, list] = {}
    links: dict[str, str] = {}
    proposals, unresolved = [], []

    for event in events:
        frame = getattr(event, 'frame', None)
        stage = getattr(frame, 'policy_status', None)
        cited = tuple(getattr(event, 'instrument_ids', ()) or ())
        matched = []
        for value in cited:
            for earlier in by_id.get(value, ()):
                if earlier.event_id == event.event_id:
                    continue
                if (event.event_id, earlier.event_id) in rejected:
                    continue
                earlier_stage = getattr(getattr(earlier, 'frame', None),
                                        'policy_status', None)
                advances = (stage in TERMINATING_STAGES
                            or STAGE_LADDER.get(stage, 0)
                            > STAGE_LADDER.get(earlier_stage, 0))
                record = dict(
                    later=event.event_id, earlier=earlier.event_id,
                    instrument_id=value, later_stage=stage,
                    earlier_stage=earlier_stage,
                    basis=(f"both documents cite {value}"),
                    status='linked' if advances else 'proposed',
                    reason=('the later document advances or ends the stage '
                            'the earlier one recorded' if advances else
                            'same instrument, but the later document does '
                            'not advance the stage: a revision or a parallel '
                            'proceeding, which needs a reviewer'))
                proposals.append(record)
                if advances:
                    matched.append(earlier.event_id)
        for value in cited:
            by_id.setdefault(value, []).append(event)

        for later, earlier in confirmed:
            if later == event.event_id:
                matched.append(earlier)
                proposals.append(dict(later=later, earlier=earlier,
                                      instrument_id=None, later_stage=stage,
                                      basis='confirmed by a reviewer',
                                      status='linked',
                                      reason='human review established this link'))
        declared = getattr(event, 'supersedes', None)
        if declared and (event.event_id, declared) not in rejected:
            matched.append(declared)
        for target in dict.fromkeys(matched):
            links[target] = event.event_id

        # --- a terminating document that links to nothing ---------------
        ends = (stage in TERMINATING_STAGES
                or getattr(frame, 'pending_termination', None)
                or AMENDS.search(getattr(event, 'headline', '') or ''))
        if ends and not matched:
            unresolved.append(dict(
                event_id=event.event_id,
                headline=getattr(event, 'headline', ''),
                stage=stage, cited_instrument_ids=list(cited),
                warning=(
                    'this document ends or amends a measure, but nothing it '
                    'cites identifies an instrument held here, so the measure '
                    'it affects is NOT linked. Any earlier order on the same '
                    'subject is still reported as in force; that is the '
                    'record, not a finding that it survived' if cited else
                    'this document ends or amends a measure and cites no '
                    'instrument identifier at all, so it cannot be linked to '
                    'what it changes. Any earlier order on the same subject '
                    'is still reported as in force, and linking the two on a '
                    'similar title would be a guess'),
                review=('confirm or reject a link between this document and '
                        'the instrument it changes')))
    return dict(links=links, proposals=proposals, unresolved=unresolved)


def supersession_chain(events, *, links: dict | None = None) -> dict:
    """Map each event to the one that supersedes it, if any.

    An old adopted measure must not remain in force forever because its own
    row never changes: a later instrument modifying it is what ends it, and
    that link lives on the later event.
    """
    superseded_by: dict[str, str] = dict(links or {})
    for event in events:
        target = getattr(event, "supersedes", None)
        if target:
            superseded_by[target] = event.event_id
    return superseded_by


def apply_supersession(events, as_of: str, *, links: dict | None = None) -> dict:
    """Applicability for every event, with supersession taken into account."""
    events = list(events)
    eligible = []
    for event in events:
        timing = getattr(event, 'timing', None)
        if timing is None or not timing.visible_at(as_of):
            continue
        state = applicability(event, as_of)
        # An announced replacement is evidence of a future change, not that
        # the old measure has already stopped operating.
        if state['state'] in ('in_force', 'ended', 'not_an_instrument'):
            eligible.append(event)
    eligible.sort(key=lambda e: (e.timing.first_seen_at or '', e.event_id))
    eligible_ids = {e.event_id for e in eligible}
    chain = supersession_chain(
        eligible, links={k: v for k, v in (links or {}).items()
                         if v in eligible_ids})
    out = {}
    for event in events:
        state = applicability(event, as_of)
        replacement = chain.get(event.event_id)
        if replacement:
            state = dict(state, state="superseded", in_force=False,
                         superseded_by=replacement,
                         basis=(f"superseded by {replacement}: a later "
                                f"instrument modifies this measure, so this "
                                f"row is no longer what applies"))
        out[event.event_id] = state
    return out
