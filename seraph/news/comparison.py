"""Two instruments side by side, and what a measure covers by product and origin.

Both answer questions a role projection could not. The institutional view
could say what one document means; it could not say *what changed between
two of them*, which is the question an analyst actually has when a
proceeding moves from a preliminary determination to an order. And it
could list routes one at a time without ever showing the shape of the
exposure — which products, from which origins, reach which sectors.

What neither of these will do is manufacture a relationship. A comparison
cites the spans it compared and says when a field is simply absent from
one side; the matrix is built from exposure edges that already carry their
own evidence, and a cell with no edge is empty rather than zero.
"""
from __future__ import annotations

#: Frame fields worth comparing, and how to read each one out. Ordered as
#: an analyst reads an instrument: what it is, where it stands, what it
#: covers, what it carves out, what it says in numbers.
COMPARED = (
    ("event_type", "Event class", lambda e, f: e.event_type),
    ("assertion_status", "Assertion", lambda e, f: getattr(f, "assertion_status", None)),
    ("policy_status", "Legal stage", lambda e, f: getattr(f, "policy_status", None)),
    ("action", "Action", lambda e, f: getattr(f, "action", None)),
    ("effective_at", "Effective from",
     lambda e, f: (e.timing.effective_at if e.timing else None)
     or getattr(f, "effective_at", None)),
    ("effective_precision", "Effective-date precision",
     lambda e, f: getattr(f, "effective_precision", None)),
    ("pending_termination", "Scheduled end",
     lambda e, f: getattr(f, "pending_termination", None)),
    ("instrument_ids", "Cited instrument ids",
     lambda e, f: tuple(getattr(e, "instrument_ids", ()) or ())),
    ("excluded_countries", "Excluded origins",
     lambda e, f: tuple(getattr(f, "excluded_countries", ()) or ())),
    ("excluded_products", "Excluded products",
     lambda e, f: tuple(getattr(f, "excluded_products", ()) or ())),
    ("excluded_parties", "Exempted parties",
     lambda e, f: tuple(getattr(f, "excluded_parties", ()) or ())),
    ("subjects", "Subject origins",
     lambda e, f: tuple(sorted(n for n, role in (e.locations or ())
                               if role == "subject_origin"))),
    ("quantities", "Stated quantities",
     lambda e, f: tuple(f"{q.measure} {q.old_level}->{q.new_level} {q.unit}"
                        for q in (getattr(f, "quantities", ()) or ()))),
)


def _cite(event, field: str) -> list:
    """The spans the extractor attributed to this field, if any."""
    wanted = {"effective_at": {"effective_at"},
              "policy_status": {"policy_status"},
              "action": {"action"},
              "assertion_status": {"assertion_status"},
              "instrument_ids": {"instrument_id"},
              "quantities": {"old_new_rate", "rate_level", "rate_delta"},
              "subjects": {"subject_origin"}}.get(field, set())
    frame = getattr(event, "frame", None)
    spans = list(getattr(frame, "evidence", ()) or ()) + list(event.evidence or ())
    return [dict(text=s.text, start=s.start, end=s.end, field=s.field)
            for s in spans if s.field in wanted][:3]


def _render(value):
    if isinstance(value, tuple):
        return list(value)
    return value


def compare_instruments(left, right, *, master=None) -> dict:
    """Field-by-field, with the text each side was read from.

    `left` and `right` are events. Order is chronological by first
    sighting where both have one, so "changed" reads forwards.
    """
    if left is None or right is None:
        return dict(status="unavailable",
                    reason="two documents are needed for a comparison")
    pair = sorted([left, right],
                  key=lambda e: ((e.timing.first_seen_at if e.timing else "") or "",
                                 e.event_id))
    earlier, later = pair
    lframe = getattr(earlier, "frame", None)
    rframe = getattr(later, "frame", None)

    rows = []
    for field, label, read in COMPARED:
        a, b = read(earlier, lframe), read(later, rframe)
        if a in (None, (), "") and b in (None, (), ""):
            continue                      # absent on both sides is not a change
        rows.append(dict(
            field=field, label=label,
            earlier=_render(a), later=_render(b),
            changed=a != b,
            # "absent" is not "unchanged": a field the later document does
            # not state has not been confirmed to be the same.
            only_on_one_side=bool((a in (None, (), "")) != (b in (None, (), ""))),
            earlier_evidence=_cite(earlier, field),
            later_evidence=_cite(later, field)))

    shared_ids = sorted(set(getattr(earlier, "instrument_ids", ()) or ())
                        & set(getattr(later, "instrument_ids", ()) or ()))
    return dict(
        status="compared",
        earlier=dict(event_id=earlier.event_id, headline=earlier.headline,
                     first_seen_at=(earlier.timing.first_seen_at
                                    if earlier.timing else None)),
        later=dict(event_id=later.event_id, headline=later.headline,
                   first_seen_at=(later.timing.first_seen_at
                                  if later.timing else None)),
        same_instrument=bool(shared_ids),
        shared_instrument_ids=shared_ids,
        rows=rows,
        changes=sum(1 for r in rows if r["changed"]),
        note=("field-by-field over what each document STATES, with the text "
              "each value was read from. Two documents that cite no common "
              "instrument identifier may still be about different measures: "
              "`same_instrument` says whether anything evidences that they "
              "are the same one, and a similar headline is not evidence"))


def product_country_matrix(channel, master) -> dict:
    """Which products, from which origins, reach which targets — and by what.

    Built from `ExposureEdge` rows, which carry their own evidence and
    their own temporal scope, plus the events currently routing through
    them. A cell exists because a documented relationship exists; a pair
    with no edge is absent from the matrix rather than present with a
    zero, because "no documented route" and "no exposure" are different
    claims and only the first one is ours to make.
    """
    estimates = list(channel.get("estimates", ()) or ())
    events = {e.event_id: e for e in channel.get("eligible_events", ()) or ()}
    by_edge: dict[str, list] = {}
    for estimate in estimates:
        for edge_id in estimate.path or ():
            by_edge.setdefault(edge_id, []).append(estimate)

    places = getattr(master, "places", {})
    cells, products, origins = [], set(), set()
    for edge_id, edge in sorted(getattr(master, "edges", {}).items()):
        if not edge.products:
            continue
        origin = edge.from_id
        origin_name = getattr(places.get(origin), "name", origin)
        touching = by_edge.get(edge_id, [])
        for product in edge.products:
            products.add(product)
            origins.add(origin_name)
            cells.append(dict(
                product=product, origin=origin, origin_name=origin_name,
                target=edge.to_id, mechanism=edge.mechanism,
                target_role=edge.target_role,
                confidence=edge.confidence,
                magnitude=edge.magnitude, unit=edge.unit,
                sized=edge.magnitude is not None,
                edge_id=edge_id,
                evidence=[ref.reference for ref in (edge.evidence or ())][:3],
                valid_from=edge.valid_from, valid_to=edge.valid_to,
                known_from=edge.known_from,
                active_events=sorted({e.event_id for e in touching}),
                active_headlines=[events[e.event_id].headline[:90]
                                  for e in touching
                                  if e.event_id in events][:3],
                directions=sorted({e.direction for e in touching}) or None))

    live = [c for c in cells if c["active_events"]]
    return dict(
        status="observed" if cells else "preview",
        cells=cells, products=sorted(products), origins=sorted(origins),
        documented_pairs=len(cells), pairs_with_current_events=len(live),
        unsized=sum(1 for c in cells if not c["sized"]),
        note=("every cell is a documented exposure relationship with its own "
              "evidence and validity window. A product/origin pair that is "
              "NOT here has no documented route in this registry, which is "
              "not a finding that no exposure exists. Unsized cells carry a "
              "direction and no magnitude; that is the registry's state, not "
              "a rounding to zero"))
