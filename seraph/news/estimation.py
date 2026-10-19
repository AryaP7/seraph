# C13 — Exposure propagation and impact estimation (NEWS04, NEWS05, NEWS06)
"""Walk the exposure graph from an event to the things it touches, and say how
sure we are — in dimensions that can be argued with.

Path deduplication is the whole problem
---------------------------------------
Exposure graphs have diamonds. If an event hits a port, and a company depends
on that port both directly and through a supplier who also uses it, a naive
sum counts the same dependence twice and reports 140% exposure. Every reachable
target here keeps **one** path — the strongest-evidence, shortest one — and the
alternatives are recorded as `also_reachable_via` so a reviewer can see the
diamond rather than have it silently resolved.

Likewise ten syndicated copies of one story are one event (the extractor
already collapsed them), and two genuinely distinct events touching the same
target produce two estimates, not one doubled one.

What an estimate is not
-----------------------
`severity`, `evidence_confidence`, `exposure_magnitude`, `direction` and
`horizon_days` stay five separate fields. They are deliberately **not**
multiplied into a single "stress" number, because the product's job is to let
a user check the reasoning, and a collapsed score destroys exactly the
information needed to do that. Nothing here is a probability of financial
loss; producing one needs a declared, calibrated target and an evaluation that
does not exist.
"""
from __future__ import annotations

from dataclasses import dataclass

from seraph.news.model import Direction, Event, ExposureEdge, ImpactEstimate
from seraph.news.registry import MasterData
from seraph.product_types import Coverage

METHOD_ID = "news.exposure_walk"
METHOD_VERSION = "2026-10-16.1"

#: How far a dependence is followed. Beyond this the evidence is too thin for
#: the result to mean anything, so the walk stops and says it stopped.
MAX_DEPTH = 3

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}

#: Severity comes from the event TYPE and its stated quantities, never from
#: sentiment. A tone classifier's output is not a severity.
BASE_SEVERITY: dict[str, str] = {
    "facility_incident": "major",
    "production_halt": "major",
    "export_restriction": "moderate",
    "tariff_announcement": "moderate",
    "import_duty_change": "moderate",
    "logistics_disruption": "moderate",
    "regulatory_action": "moderate",
    "policy_rate_decision": "minor",
    "subsidy_change": "minor",
    "capacity_expansion": "minor",
    "other": "minor",
}

FAVOURABLE = {"capacity_expansion", "subsidy_change"}

HORIZON_DAYS: dict[str, int] = {
    "facility_incident": 30,
    "production_halt": 30,
    "logistics_disruption": 14,
    "export_restriction": 90,
    "tariff_announcement": 180,
    "import_duty_change": 180,
    "regulatory_action": 90,
    "policy_rate_decision": 90,
    "subsidy_change": 365,
    "capacity_expansion": 365,
    "other": 30,
}

SEVERITY_ORDER = ("minor", "moderate", "major", "severe")


@dataclass(frozen=True)
class Path:
    target_id: str
    edges: tuple[str, ...]
    mechanism: str
    magnitude: float | None
    unit: str | None
    confidence: str
    depth: int

    @property
    def rank(self) -> tuple:
        """Best path = strongest evidence, then shortest, then stable id."""
        return (-CONFIDENCE_RANK.get(self.confidence, 0), self.depth, self.edges)


def reachable(master: MasterData, origins: tuple[str, ...], *, on: str | None = None,
              max_depth: int = MAX_DEPTH, known_at: str | None = None,
              event: Event | None = None) -> dict[str, Path]:
    """Enumerate bounded simple paths; ordering cannot suppress better descendants."""
    from seraph.news.scope import excludes_product
    frame = getattr(event, "frame", None) if event else None
    outgoing = {}
    for edge in sorted(master.edges.values(), key=lambda e: e.edge_id):
        if on and not edge.active_on(on):
            continue
        if known_at and not edge.visible_at(known_at):
            continue
        if event and edge.event_types and event.event_type not in edge.event_types:
            continue
        if event and edge.products and not any(p.casefold() in event.headline.casefold() for p in edge.products):
            continue
        # A relationship whose every product the instrument names as carved
        # out is not a route this instrument travels.
        if frame is not None and excludes_product(frame, edge.products):
            continue
        outgoing.setdefault(edge.from_id, []).append(edge)
    candidates = {}
    frontier = [(o, Path(o, (), 'operation', None, None, 'high', 0), (o,)) for o in sorted(set(origins))]
    while frontier:
        node, path, visited = frontier.pop()
        if path.depth >= max_depth:
            continue
        for edge in outgoing.get(node, ()):
            if edge.to_id in visited or edge.to_id in origins:
                continue
            confidence = min((path.confidence, edge.confidence), key=lambda c: CONFIDENCE_RANK.get(c, 0))
            candidate = Path(edge.to_id, path.edges+(edge.edge_id,), edge.mechanism,
                             edge.magnitude if path.depth == 0 else None,
                             edge.unit if path.depth == 0 else None, confidence, path.depth+1)
            candidates.setdefault(edge.to_id, []).append(candidate)
            frontier.append((edge.to_id, candidate, visited+(edge.to_id,)))
    best = {}
    for target, paths in candidates.items():
        ordered = sorted(paths, key=lambda p: p.rank)
        best[target] = ordered[0]
        object.__setattr__(best[target], '_alternatives', tuple(p.edges for p in ordered[1:]))
    return best


def severity_of(event: Event) -> str:
    """Severity from the event type, escalated by its own stated quantities."""
    # An ordinal editorial category, not a measured loss or historical-rate score.
    frame = event.frame
    if frame and (frame.assertion_status != 'confirmed_statement'
                  or frame.action in ('cancel', 'unchanged')
                  or frame.policy_status in ('proposed', 'consultation')):
        return 'minor'
    return BASE_SEVERITY.get(event.event_type, 'minor')


def evidence_confidence_of(event: Event, path_confidence: str) -> str:
    """How sure we are the event is real AND correctly linked.

    Two independent sources reporting the same event raises it; an unresolved
    entity in the chain lowers it. A single uncorroborated source never
    reaches `high`.
    """
    rank = CONFIDENCE_RANK.get(path_confidence, 1)
    if event.confirmations >= 2:
        rank += 1
    if event.unresolved:
        rank -= 1
    if event.event_type == "other":
        rank -= 1
    rank = max(1, min(3 if event.confirmations >= 2 else 2, rank))
    return {3: "high", 2: "medium", 1: "low"}[rank]


def direction_of(event: Event, *, target_role: str | None = None) -> Direction:
    """Qualitative mechanism direction. Never assign one sign to every target."""
    f = event.frame
    if not f or f.assertion_status != 'confirmed_statement':
        return 'ambiguous'
    if getattr(f, 'pending_termination', None):
        # This instrument ENDS a measure from a date that has not arrived.
        # Neither sign is true yet: the old measure is still operating and
        # the relief has not started, so signing it either way reports a
        # change that has not happened.
        return 'ambiguous'
    if event.event_type == 'trade_remedy_determination':
        # For a remedy the meaningful verb is the LEGAL STAGE, not an
        # increase or decrease, so this is decided before the generic action
        # guard. Only an adopted determination or an issued order establishes
        # a measure: a preliminary finding and an initiated investigation
        # establish nothing, whatever their headline says.
        # Removing a measure is the mirror of imposing one, and is the
        # clearest favourable trade-remedy outcome there is. Treating it as
        # unsigned reported a duty REVOCATION with no more information than
        # an opened investigation.
        if f.policy_status in ('repealed', 'suspended'):
            if target_role == 'exporter':
                return 'favourable'
            if target_role == 'domestic_producer':
                return 'adverse'
            return 'ambiguous'
        if f.policy_status not in ('adopted', 'effective'):
            return 'ambiguous'
        if target_role == 'exporter':
            return 'adverse'
        if target_role == 'domestic_producer':
            # The same measure protects the producer competing with the
            # imports it restricts. One sign for every target is the defect
            # this whole function exists to avoid.
            return 'favourable'
        return 'ambiguous'
    if f.action in ('unknown', 'cancel') or f.policy_status in ('proposed', 'consultation', 'expired', 'repealed', 'suspended'):
        return 'ambiguous'
    if f.action == 'unchanged':
        return 'ambiguous'
    if event.event_type == 'policy_rate_decision':
        if target_role == 'borrower' and f.action in ('increase', 'decrease'):
            return 'adverse' if f.action == 'increase' else 'favourable'
        return 'ambiguous'
    if event.event_type == 'subsidy_change' and target_role == 'beneficiary':
        if f.action == 'withdraw': return 'adverse'
        if f.action in ('start', 'increase'): return 'favourable'
    if event.event_type in ('production_halt', 'facility_incident', 'logistics_disruption'):
        if target_role in ('operator', 'input_user'):
            if f.action == 'stop': return 'adverse'
            if f.action == 'resume': return 'favourable'
    if event.event_type == 'export_restriction' and target_role == 'input_user':
        if f.action in ('start', 'stop', 'increase'): return 'adverse'
        if f.action in ('withdraw', 'decrease', 'resume'): return 'favourable'
    if event.event_type in ('tariff_announcement', 'import_duty_change'):
        if target_role in ('importer', 'domestic_producer') and f.action in ('increase','decrease'):
            adverse = (f.action == 'increase') == (target_role == 'importer')
            return 'adverse' if adverse else 'favourable'
    return 'ambiguous'


def excluded_from(event: Event, master: MasterData) -> dict:
    """Which targets this instrument's own text places OUTSIDE its scope.

    The impact walk used to read the headline for scope and the body for
    nothing, so a steel duty whose body said "this order does not apply to
    products from India" still emitted an adverse Indian steel route. An
    explicit, named exclusion is the strongest scope evidence a document
    can carry and must suppress the claim, not merely annotate it.

    Only NAMED exclusions suppress. A carve-out that was detected but could
    not be parsed stays what it was: a confidence ceiling and a labelled
    watch, because dropping a route on an exclusion nobody could read is
    the same guess pointing the other way.
    """
    from seraph.news.scope import excluded_place_ids, excludes_party
    frame = getattr(event, "frame", None)
    if frame is None or not (frame.excluded_countries or frame.excluded_parties):
        # Nothing was named as outside the measure, so there is nothing to
        # resolve and no reason to walk the registry.
        return dict(places={}, unresolved=(), node_ids=set())
    resolved = excluded_place_ids(frame, master)
    node_ids = set(resolved["places"])
    # A named party, and anything whose location is an excluded place.
    for entity_id, entity in master.entities.items():
        if excludes_party(frame, entity.name, *entity.aliases):
            node_ids.add(entity_id)
    for asset_id, asset in master.assets.items():
        if asset.place_id in resolved["places"] or excludes_party(frame, asset.name):
            node_ids.add(asset_id)
    return dict(places=resolved["places"], unresolved=resolved["unresolved"],
                node_ids=node_ids)


def estimate_impacts(event: Event, master: MasterData, *,
                     on: str | None = None, known_at: str | None = None) -> list[ImpactEstimate]:
    """One estimate per distinct target, with its path recorded."""
    carved = excluded_from(event, master)
    excluded = carved["node_ids"]
    origins = tuple(o for o in dict.fromkeys(event.affected + event.exposure_origins)
                    if o not in excluded)
    if not origins:
        return []
    paths = reachable(master, origins, on=on, known_at=known_at, event=event)
    severity = severity_of(event)
    direction = direction_of(event)
    horizon = HORIZON_DAYS.get(event.event_type, 30)
    estimates: list[ImpactEstimate] = []

    for origin in event.affected:
        if origin in excluded:
            continue
        estimates.append(_estimate(
            event, origin, Path(origin, (), "operation", None, None, "high", 0),
            severity, direction, horizon, master, direct=True))
    for target, path in sorted(paths.items()):
        if target in excluded:
            continue
        estimates.append(_estimate(event, target, path, severity, direction,
                                   horizon, master, direct=False))
    return estimates


def _estimate(event, target, path, severity, direction, horizon, master,
              *, direct) -> ImpactEstimate:
    kind = ("sector" if target.startswith("sector:")
            else "asset" if target in master.assets
            else "place" if target in master.places
            else "entity")
    last_edge = master.edges.get(path.edges[-1]) if path.edges else None
    direction = direction_of(event, target_role=(last_edge.target_role if last_edge else
                                                'operator' if kind == 'asset' else None))
    confidence = evidence_confidence_of(event, path.confidence)
    limitations = ['qualitative mechanism hypothesis; not a measured outcome or loss forecast',
                    'severity is an editorial event category; not calibrated economic severity']
    if last_edge and last_edge.note:
        limitations.append(last_edge.note)
    # An exposure walk matches on a PRODUCT FAMILY. A trade instrument covers
    # a defined article and often excludes named variants or parties, so a
    # family match is not a scope determination -- and a missed exclusion
    # turns "this does not apply to you" into an adverse signal.
    #
    # Read from the FRAME, which scoped the retained body, not from the
    # headline. Scoping the headline is precisely how the body's "this order
    # does not apply to products from India" never reached the decision.
    from seraph.news.scope import Scope
    frame = getattr(event, "frame", None)
    determined = bool(frame is not None and frame.scope_determined)
    note = getattr(frame, "scope_note", None) if frame is not None else None
    if not determined and note is None:
        # Nothing in the received text spoke about scope. That is "we were
        # not told", never "no exclusions".
        note = Scope().limitation
    if note:
        limitations.append(note)
    named = bool(frame is not None and (frame.excluded_countries
                                        or frame.excluded_products
                                        or frame.excluded_parties))
    if named:
        # Something IS carved out and named; this target is not it (an
        # excluded one never reaches here). Say so, because a reader must
        # not read an unqualified route off an instrument that excludes its
        # neighbours.
        limitations.append(
            "this instrument carves out named origins/products/parties; "
            "this target is not among them, and the carve-out was read from "
            "the retained text rather than assumed absent")
    if named or getattr(frame, "scope_carve_out", False):
        # A carve-out we detected but could not parse must not leave a
        # confident direction standing.
        confidence = "low"

    if event.event_type == 'export_restriction' and last_edge and last_edge.products:
        direction = 'ambiguous'
        limitations.append('scope watch: exact product composition, exemptions and current legal status require instrument review')
    if direction == 'ambiguous':
        limitations.append('net direction unknown: required target role, action or applicability is not established')
    if not direct:
        limitations.append(
            f"indirect: reached through {len(path.edges)} documented "
            f"relationship(s) ({' -> '.join(path.edges)})")
    alternatives = getattr(path, "_alternatives", ())
    if alternatives:
        limitations.append(
            f"{len(alternatives)} other path(s) also reach this target; the "
            f"strongest-evidence path was kept and the exposure is counted once")
    if path.magnitude is None:
        limitations.append(
            "the size of this dependence is not recorded; the relationship is "
            "evidenced but its magnitude is unknown, which is not the same as small")
    if event.unresolved:
        limitations.append(
            f"{len(event.unresolved)} fact(s) in the source were not resolved")
    return ImpactEstimate(
        estimate_id=f"est_{event.event_id}_{target}".replace(":", "_"),
        event_id=event.event_id, target_id=target, target_kind=kind,
        severity=severity, evidence_confidence=confidence,
        exposure_magnitude=path.magnitude, exposure_unit=path.unit,
        direction=direction, horizon_days=horizon,
        mechanism=path.mechanism, method_id=METHOD_ID, method_version=METHOD_VERSION,
        path=path.edges, limitations=tuple(limitations),
        coverage=Coverage(population=f"{kind} reachable from the event",
                          basis="documented exposure relationships only"))


def aggregate_by(estimates: list[ImpactEstimate], *, key: str = "target_id"
                 ) -> dict[str, dict]:
    """Roll up WITHOUT double counting.

    Two estimates for the same target from the SAME event are one exposure
    (the stronger one survives). Two estimates from DIFFERENT events are two
    distinct pieces of news about the same target and both are kept — counted
    once each, never multiplied.
    """
    rolled: dict[str, dict] = {}
    for estimate in estimates:
        bucket = rolled.setdefault(getattr(estimate, key), {
            "target_id": estimate.target_id, "events": {}, "severity": "minor",
            "direction": set(), "mechanisms": set(), "estimates": 0,
        })
        previous = bucket["events"].get(estimate.event_id)
        if previous is None or _stronger(estimate, previous):
            bucket["events"][estimate.event_id] = estimate
        bucket["direction"].add(estimate.direction)
        bucket["mechanisms"].add(estimate.mechanism)
    for bucket in rolled.values():
        kept = list(bucket["events"].values())
        bucket["estimates"] = len(kept)
        bucket["severity"] = max((e.severity for e in kept),
                                 key=SEVERITY_ORDER.index, default="minor")
        bucket["evidence_confidence"] = max(
            (e.evidence_confidence for e in kept),
            key=lambda c: CONFIDENCE_RANK.get(c, 0), default="low")
        sized = [e.exposure_magnitude for e in kept if e.exposure_magnitude is not None]
        bucket["exposure_components"] = [dict(event_id=e.event_id, magnitude=e.exposure_magnitude,
            unit=e.exposure_unit, path=list(e.path)) for e in kept if e.exposure_magnitude is not None]
        # Unknown overlap and incompatible denominators cannot be added.
        bucket["exposure_magnitude"] = sized[0] if len(kept) == 1 and sized else None
        bucket["exposure_unit"] = next(
            (e.exposure_unit for e in kept if e.exposure_unit), None) if len(kept) == 1 else None
        bucket["unsized_relationships"] = len(kept) - len(sized)
        bucket["direction"] = sorted(bucket["direction"])
        bucket["mechanisms"] = sorted(bucket["mechanisms"])
        bucket["event_ids"] = sorted(bucket["events"])
        bucket.pop("events")
    return rolled


def _stronger(candidate: ImpactEstimate, incumbent: ImpactEstimate) -> bool:
    return ((CONFIDENCE_RANK.get(candidate.evidence_confidence, 0),
             SEVERITY_ORDER.index(candidate.severity), -len(candidate.path))
            > (CONFIDENCE_RANK.get(incumbent.evidence_confidence, 0),
               SEVERITY_ORDER.index(incumbent.severity), -len(incumbent.path)))
