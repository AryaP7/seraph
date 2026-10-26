# C12 — News channel projection for the console (NEWS06)
"""Project the news channel into the console payload, with its status attached.

This is the seam the audit asked for: *replace each preview's data provider as
its subsystem becomes ready*. The panels do not change and nothing is deleted.
Each surface asks this module for its data and gets back one of two things:

* real content, every number carrying source, as-of time, method and version; or
* an explicit `preview` marker, so the existing illustrative card keeps its
  FABRICATED tag.

The switch is per surface and automatic — it depends on whether the news store
and the curated registries actually have anything for that surface at that
decision time. A surface with no data never borrows another's.

Two separations are load-bearing:

* **News sector stress is not Hawkes sector stress.** They appear as two
  series with different `channel` values, different units and different
  coverage. `sector_panel()` returns both side by side and never merges them.
* **A geography arc is not a fitted contagion edge.** Arcs come from
  `ExposureEdge` rows with evidence; the CSRS channel contributes none.
"""
from __future__ import annotations

from seraph.news.estimation import aggregate_by, estimate_impacts
from seraph.news.extraction import extract_events
from datetime import datetime

from seraph.news.registry import MasterData
from seraph.news.currency import partition as partition_by_currency
from seraph.news.relevance import assess_relevance
from seraph.news.model import Place
from dataclasses import replace
import math
from seraph.product_types import Coverage

VIEW_VERSION = "c12.news_view/2026-10-18.1"

#: What a panel says when its subsystem has nothing for this decision time.
PREVIEW_NOTE = ("no connected data for this surface yet; the original "
                "illustrative card is shown and remains labelled as a preview")


def _age_minutes(later: str, earlier: str) -> "float | None":
    """Minutes between two explicit IST timestamps, or None if unparseable.

    Every timestamp in SERAPH is `YYYY-MM-DDTHH:mm:ss+05:30` by invariant, so
    this parses rather than guesses — but a malformed one must not take the
    whole console down, which is why it returns None instead of raising.
    """
    try:
        fmt = "%Y-%m-%dT%H:%M:%S%z"
        return (datetime.strptime(later, fmt)
                - datetime.strptime(earlier, fmt)).total_seconds() / 60
    except (ValueError, TypeError):
        return None


def _freshness(coverage, decision_ts: str, events, worker=None) -> dict:
    """How old is what this console is about to describe?

    Derived from the coverage the channel already computes: a source is late
    when it is past the freshness policy **it declared**, not past a number
    invented here. `stale` is therefore a statement about the sources' own
    terms.
    """
    newest = max((e.timing.first_seen_at or "" for e in events), default="")
    age = _age_minutes(decision_ts, newest) if newest else None
    # Four different times, kept apart on purpose. Collapsing them is how a
    # screen that re-renders every 30 seconds comes to look like news that
    # arrives every 30 seconds.
    return dict(
        # when an ARTICLE reached us
        newest_first_seen_at=newest or None,
        age_minutes=None if age is None else round(age, 1),
        # whether any SOURCE is past the policy it declared
        stale=not coverage.is_complete,
        late_sources=len(coverage.uncovered),
        total_sources=coverage.total,
        # whether the WORKER is alive at all — a different question, and the
        # one nothing used to answer
        worker=worker,
        worker_state=(worker or {}).get("state"),
        # the DECISION time this projection was built for
        projected_for=decision_ts,
        note=("four distinct times: `projected_for` is the decision time this "
              "screen was built for and is NOT evidence of freshness; "
              "`newest_first_seen_at` is when an article last reached us; "
              "`stale` says whether a source is past the policy it declared; "
              "`worker.state` says whether anything is fetching at all. A "
              "screen that re-renders is not news that arrived"))


def _permits(source, use: str) -> bool:
    """Whether a source permits a use, tolerant of an older registration."""
    try:
        return bool(source.permits(use))
    except Exception:                               # noqa: BLE001 - optional
        return bool(getattr(source, "may_store_full_text", False))


#: What stands in for a quotation the licence does not permit showing. The
#: span's OFFSETS stay, so the claim is still traceable to a position in the
#: document a reader can open at the source; only the words are withheld.
WITHHELD = "[text withheld: this source's terms do not permit display]"


def _redact_spans(payload, allowed: bool):
    """Blank evidence-span text for a source that may not be displayed.

    Storing the text and showing it to a reader are different permissions,
    and the one boolean that used to cover both meant a source whose terms
    allow retention for analysis but not republication had to be modelled
    as "store nothing" — which throws away analysis the licence permits.
    """
    if allowed or not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for key in ("evidence", "quantities"):
        rows = out.get(key)
        if isinstance(rows, list):
            out[key] = [
                dict(row, **({"text": WITHHELD} if "text" in row else {}),
                     **({"evidence": _redact_spans(dict(evidence=row["evidence"]),
                                                   allowed)["evidence"]}
                        if isinstance(row.get("evidence"), list) else {}))
                if isinstance(row, dict) else row for row in rows]
    return out


def _opposing_view(event) -> "dict | None":
    """Who the measure constrains and who it benefits, or None."""
    from seraph.news.opposing import opposing_parties
    view = opposing_parties(event)
    if not (view.constrained or view.benefiting):
        return None
    return view.describe()


def _worker_state(store, decision_ts: str, *, strict_replay: bool = False) -> dict:
    """Ask the store whether an acquisition worker is alive.

    Tolerant on purpose: a store written before the heartbeat existed has no
    such table, and an old projection must still render rather than fail.

    Under a strict replay the store omits a heartbeat recorded after the
    cutoff: liveness is not versioned, so there is nothing to reconstruct
    and showing today's row would put information from after the moment
    into the moment.
    """
    try:
        return store.worker_state(decision_ts, strict_replay=strict_replay)
    except TypeError:                               # a store predating the flag
        return store.worker_state(decision_ts)
    except Exception:                               # noqa: BLE001 - optional
        return dict(worker="news.poll", state="unknown", last_beat_at=None,
                    age_minutes=None,
                    note="this store predates worker heartbeats")


def _preview(surface: str, reason: str) -> dict:
    return dict(surface=surface, status="preview", items=[], reason=reason,
                note=PREVIEW_NOTE, version=VIEW_VERSION)


def processing_manifest(store, master, *, decision_ts: str,
                        strict_replay: bool, events=()) -> dict:
    """Every version that shapes this projection, pinned in one place.

    `MasterData.version_manifest()` existed and had no production caller,
    so a payload carried its own view version and nothing else: the
    extractor, the grouping rule, the source definitions and the document
    hashes were all implicit, and two runs that differed in any of them
    were indistinguishable afterwards.

    It also states, in the payload rather than in a document, that what the
    reader is looking at is a RECONSTRUCTION — frames rebuilt from stored
    text with today's rules — and not a replay of the bytes the running
    system emitted at the time. Those are different claims and only one of
    them is true here.
    """
    from seraph.news.extraction import EXTRACTOR_VERSION
    from seraph.news.event_frames import VERSION as FRAME_RULES
    from seraph.news.model import SYNDICATION_KEY_VERSION
    from seraph.news.estimation import METHOD_ID, METHOD_VERSION
    from seraph.shared_types import IST, ist_timestamp

    produced_at = ist_timestamp(datetime.now(IST).replace(microsecond=0))
    try:
        registry = master.version_manifest()
        registry["completeness"] = master.registry_completeness()
    except Exception:                               # noqa: BLE001 - optional
        registry = dict(note="registry version manifest unavailable")
    try:
        sources = store.source_version_hashes(decision_ts if strict_replay else None)
    except Exception:                               # noqa: BLE001 - optional
        sources = {}
    documents = {}
    for event in events:
        frame = getattr(event, "frame", None)
        if frame is not None and frame.representation_hash:
            documents[event.event_id] = frame.representation_hash
    latencies = [
        _age_minutes(produced_at, getattr(event.frame, "available_at", None))
        for event in events
        if getattr(event, "frame", None) is not None
        and getattr(event.frame, "available_at", None)]
    latencies = [value for value in latencies if value is not None and value >= 0]
    return dict(
        decision_ts=decision_ts, produced_at=produced_at,
        strict_replay=strict_replay,
        view=VIEW_VERSION,
        extractor=EXTRACTOR_VERSION,
        frame_rules=FRAME_RULES,
        syndication_key=SYNDICATION_KEY_VERSION,
        estimation=f"{METHOD_ID}@{METHOD_VERSION}",
        registry=registry,
        source_versions=sources,
        representation_hashes=documents,
        processing=dict(
            events=len(list(events)),
            with_availability=len(latencies),
            median_latency_minutes=(
                round(sorted(latencies)[len(latencies) // 2], 1)
                if latencies else None),
            max_latency_minutes=round(max(latencies), 1) if latencies else None,
            note=("latency is measured from the frame's `available_at` -- the "
                  "latest first-sighting of the stories it was built from -- "
                  "to the moment this projection was produced. It is the age "
                  "of the evidence at render time, NOT a measurement of how "
                  "long the running pipeline took to emit a result")),
        provenance="reconstruction",
        note=("every version that shapes this projection, pinned together. "
              "`provenance: reconstruction` means the frames here were "
              "rebuilt from stored text using the rule versions named above, "
              "which is NOT the same as replaying what the running system "
              "emitted at `decision_ts`. A saved snapshot is the only "
              "artefact that supports the second claim"))


def news_channel(store, master: MasterData, *, decision_ts: str,
                 sectors: dict | None = None, limit: int = 40, offset: int = 0,
                 strict_replay: bool = False) -> dict:
    """Everything the news channel can honestly show at `decision_ts`.

    Only stories whose `first_seen_at` is at or before the decision time are
    read, so the same call is correct for a live view and for a replay.
    """
    master = master.as_of(decision_ts, strict=strict_replay)
    groups = store.syndication_groups(visible_at=decision_ts)
    coverage = store.coverage_at(decision_ts, strict_replay=strict_replay)
    sources = store.sources_at(decision_ts) if strict_replay else store.sources()
    # Evidence notes come from the source record AS IT STOOD, not from
    # today's registration. A replay that quotes a note written last week
    # attributes to the past a description the system did not yet hold.
    source_records = {s.source_id: s for s in sources}

    events, extractions = [], []
    origins, references, corroboration = {}, {}, {}
    for stories in groups.values():
        for result in extract_events(stories, master, sectors=sectors):
            if result.event is None:
                continue
            primary = min(stories, key=lambda s: (s.first_seen_at or '', s.story_id))
            coords = primary.metadata.get('coordinates')
            if (primary.metadata.get('source_kind_hint') == 'hazard_agency' and
                isinstance(coords, list) and len(coords) == 2 and
                all(isinstance(x, (int,float)) and math.isfinite(x) for x in coords)
                and -180 <= coords[0] <= 180 and -90 <= coords[1] <= 90):
                node = 'hazard_' + primary.story_id
                master.add_place(Place(node, primary.title, 'point',
                                       lat=coords[1], lon=coords[0]))
                result = replace(result,event=replace(result.event,
                    locations=result.event.locations+((node,'occurrence'),)))
            events.append(result.event)
            extractions.append(result)
            found = {}
            refs = []
            for story in stories:
                record = master.origin_of(story.source_id)
                if record:
                    found[record['place_id']] = record
                observation = store.observation(story.observation_id)
                refs.append(dict(story_id=story.story_id, source_id=story.source_id,
                    url=story.url, content_hash=observation.content_hash if observation else None,
                    published_at=story.timing.published_at, first_seen_at=story.first_seen_at,
                    source_note=getattr(source_records.get(story.source_id),
                                        'notes', None),
                    # Per-use permission, carried to the surface that would
                    # render the text. Storing and SHOWING are different
                    # permissions and one boolean was covering both.
                    display_permitted=_permits(source_records.get(story.source_id),
                                               'display'),
                    redistribution_permitted=_permits(
                        source_records.get(story.source_id), 'redistribute'),
                    rights_reviewed=getattr(source_records.get(story.source_id),
                                            'rights_reviewed', False),
                    language=story.language, publication_precision=story.metadata.get('publication_precision','unknown'),
                    text_scope=story.metadata.get('text_scope', 'body_available' if story.body else 'headline_only'),
                    document_status=story.metadata.get('document_status'),
                    document_hash=story.metadata.get('document_hash')))
            origins[result.event.event_id] = list(found.values())
            references[result.event.event_id] = refs
            # Duplication, copied reporting and corroboration are four
            # different facts behind one `confirmations` number. Reported
            # here; none of them raises it.
            from seraph.news.corroboration import describe_event
            corroboration[result.event.event_id] = describe_event(
                result.event, stories)
    events.sort(key=lambda e: (e.timing.first_seen_at or '', e.event_id), reverse=True)
    total = len(events)
    eligible_events = list(events)
    # Latest-first, THEN page. The rail is paginated; the aggregates are not.
    page = events[max(0, offset):max(0, offset) + max(1, limit)]

    # An event that has aged out is not "what is happening now". An
    # instrument still in force never ages out, however old, because it is
    # still operating — that asymmetry is the whole reason this is not a
    # simple age cutoff. Nothing is deleted: the expired set is reported.
    # Supersession links come from cited instrument identifiers plus the
    # reviews a human has recorded, both bounded by the decision time. An
    # unlinked revocation leaves an older order reported as in force, so
    # the unresolved ones travel to the regulator surface as review work
    # rather than staying a silent property of the data.
    try:
        decisions = store.supersession_decisions(visible_at=decision_ts)
    except Exception:                               # noqa: BLE001 - optional
        decisions = dict(confirmed=(), rejected=(), decisions=[])
    aged = partition_by_currency(eligible_events, decision_ts,
                                 confirmed_links=decisions["confirmed"],
                                 rejected_links=decisions["rejected"])
    current_events = aged["current"]

    # Impacts are estimated over EVERY eligible event, not the displayed page.
    # Slicing first made a documented sector exposure disappear whenever its
    # event fell off page one: on the pilot store, 181 eligible events and a
    # 40-event page hid the Kalinganagar -> sector:steel relationship
    # completely, which reads as "steel has no documented exposure" rather
    # than "you are looking at page 1 of 5".
    estimates = []
    for event in current_events:
        estimates.extend(estimate_impacts(event, master,
                                          on=(decision_ts or "")[:10] or None, known_at=decision_ts))

    # Any event an on-screen inference points at must be reachable, even when
    # it falls outside the page being browsed. Otherwise the sector panel can
    # assert a documented exposure whose documents the user cannot open.
    # Relevance is a different question from classification, and keeping them
    # apart is what makes `other` mean "we do not know what this is" rather
    # than "this is about polar bears". Computed over every eligible event,
    # like the estimates, so a count cannot change with the page.
    relevance = {
        event.event_id: assess_relevance(
            event, master,
            issuer_places=[o["place_id"]
                           for o in origins.get(event.event_id, ())])
        for event in eligible_events}

    on_page = {e.event_id for e in page}
    referenced = {e.event_id for e in estimates} - on_page
    referenced_events = [e for e in eligible_events if e.event_id in referenced]
    events = page

    return dict(
        decision_ts=decision_ts, master=master,
        version=VIEW_VERSION,
        freshness=_freshness(coverage, decision_ts, eligible_events,
                             worker=_worker_state(store, decision_ts,
                                                  strict_replay=strict_replay)),
        source_coverage=dict(
            publishers=len({s.provider for s in sources}),
            registered_feeds=len(sources),
            coverage_gaps=['Pilot coverage only: no licensed independent journalism',
                'No validated Hindi interpretation; received Hindi items abstain',
                'Exchange filings, Indian trade instruments and broader sector routes are incomplete',
                'Pilot exposure registry is qualitative; unmapped firms and unknown sizes are not zero risk'],
            languages=sorted({s.language for s in sources}),
            covered=coverage.covered, total=coverage.total,
            uncovered=list(coverage.uncovered),
            complete=coverage.is_complete,
            # Per-use rights, and how many of them anyone has actually
            # reviewed. A permission nobody read the terms for is a guess
            # carrying a boolean's confidence.
            rights=dict(
                reviewed=sum(1 for s in sources
                             if getattr(s, 'rights_reviewed', False)),
                total=len(sources),
                permitted_uses={
                    use: sum(1 for s in sources if _permits(s, use))
                    for use in ('fetch', 'process', 'store', 'display',
                                'redistribute')},
                unreviewed=[s.source_id for s in sources
                            if not getattr(s, 'rights_reviewed', False)],
                note=('a source with no per-use review falls back to the '
                      'coarse storage flag, which is never more permissive '
                      'than the registration it came from')),
            note=("sources that failed or were never fetched are listed. An "
                  "empty map with uncovered sources is missing coverage, not "
                  "a quiet market")),
        events=events, eligible_events=eligible_events,
        referenced_events=referenced_events, references=references,
        corroboration=corroboration,
        relevance=relevance,
        currency=dict(
            current=len(aged["current"]), expired=len(aged["expired"]),
            states=aged["states"], note=aged["note"]),
        supersession=dict(
            links=aged["supersession"]["links"],
            proposals=aged["supersession"]["proposals"],
            unresolved=aged["supersession"]["unresolved"],
            reviews=decisions["decisions"],
            note=("instruments are linked on the identifiers the documents "
                  "cite, or on a recorded human review. They are never "
                  "linked on a similar title: one product-and-country "
                  "headline covers a proposal, a determination, an order "
                  "and its revocation")),
        scope=dict(
            in_scope=sum(1 for r in relevance.values() if r.in_scope),
            out_of_scope=sum(1 for r in relevance.values() if not r.in_scope),
            unclassified_in_scope=sum(
                1 for e in eligible_events
                if relevance[e.event_id].in_scope and e.event_type == "other"),
            note=("relevance is separate from classification. An out-of-scope "
                  "event is carried, linked and counted, never deleted: a feed "
                  "covering a whole jurisdiction's daily register contains far "
                  "more than this system is about, and `other` is reserved for "
                  "an in-scope event we could not identify")),
        pagination=dict(total=total, offset=offset, limit=limit, displayed=len(events),
                        next_offset=offset+limit if offset+limit<total else None,
                        aggregates_cover=len(eligible_events),
                        note=('the signal rail is paginated; the sector panel, '
                              'the geography overlay and the globe describe '
                              'every eligible event at this decision time, so '
                              'a documented exposure cannot disappear by '
                              'being on another page')),
        origins=origins,
        estimates=estimates,
        manifest=processing_manifest(store, master, decision_ts=decision_ts,
                                     strict_replay=strict_replay,
                                     events=eligible_events),
        injection_flags=sum(1 for e in extractions if e.injection_detected),
        unresolved=[u for e in extractions for u in e.unresolved][:limit],
    )


def signals_rail(channel: dict, *, limit: int = 40) -> dict:  # noqa: C901
    """LATEST SIGNALS. Real stories, or the preview card.

    Carries the page being browsed, plus any event an on-screen inference
    references. The second group is marked `off_page=True`: it is a retrieval
    route for evidence, not a claim about what is newest.
    """
    events = channel["events"]
    if not events:
        return _preview("signals", "no story has been received at this decision time")
    on_page = {e.event_id for e in events}
    ordered = sorted(events, key=lambda e: e.timing.first_seen_at or "",
                     reverse=True)[:limit]
    ordered = ordered + sorted(channel.get("referenced_events", []),
                               key=lambda e: e.timing.first_seen_at or "",
                               reverse=True)
    items = []
    for event in ordered:
        # T13: the globe adapter places a node from `origins` and shows the
        # exact source statement on click, so both travel here rather than
        # being re-derived from the store by a second reader that could
        # disagree with this one.
        statement = next((span.text for span in event.evidence
                          if span.field in ("headline", "summary")),
                         None) or event.headline
        references = channel.get('references', {}).get(event.event_id, [])
        # A source that may be stored but not displayed still contributes
        # its extracted FACTS; what it does not contribute is quotations.
        displayable = all(r.get('display_permitted', True) for r in references) \
            if references else True
        items.append(dict(
            event_id=event.event_id, headline=event.headline,
            event_type=event.event_type, lifecycle=event.lifecycle,
            revision=event.frame.revision_id if event.frame else event.supersedes,
            interpretation=_redact_spans(
                event.frame.describe() if event.frame else None, displayable),
            display_permitted=displayable,
            # Both sides of the same instrument. Showing only the signed
            # direction for one target made a measure look like unambiguous
            # good or bad news depending on which target happened to be
            # mapped. The NET is deliberately absent: it needs sizes this
            # system does not hold.
            opposing=_opposing_view(event),
            evidence_links=channel.get('references', {}).get(event.event_id, []),
            impacts=[e.describe() for e in channel['estimates'] if e.event_id == event.event_id],
            first_seen_at=event.timing.first_seen_at,
            published_at=event.timing.published_at,
            # The Federal Register schedules publication a few days ahead, so
            # `published_at` can be a future date on a document already in
            # hand. Presenting that as "Published" asserts a past event.
            publication_scheduled=event.timing.publication_scheduled,
            effective_at=event.timing.effective_at,
            confirmations=event.confirmations,
            corroboration=channel.get('corroboration', {}).get(event.event_id),
            sources=list(event.stories)[:5],
            actors=list(event.actors),
            affected=list(event.affected),
            locations=[dict(node_id=node_id, role=role)
                       for node_id, role in event.locations],
            # The issuing location of the source that published it, plus
            # any actor the extractor resolved. Unfiltered: deciding here
            # which ids *look* placeable would hide an unplaceable actor
            # instead of putting it in the review queue.
            origins=[n for n,r in event.locations if r == 'occurrence'],
            # The countries whose goods an instrument covers. An evidenced
            # role of its own: not the publisher's office, not a documented
            # affected location, not a passing mention.
            subject_origins=[n for n, r in event.locations
                             if r == 'subject_origin'],
            issuer_provenance=[o['place_id'] for o in channel.get('origins', {}).get(event.event_id, [])],
            origin_basis=[dict(place_id=o["place_id"], basis=o["basis"],
                               source=o["source"]) for o in
                          channel.get("origins", {}).get(event.event_id, [])],
            source_statement=(statement if displayable else WITHHELD),
            relevance=(channel.get("relevance", {}).get(event.event_id).describe()
                       if channel.get("relevance", {}).get(event.event_id)
                       else None),
            unresolved=list(event.unresolved),
            off_page=event.event_id not in on_page,
            status="observed"))
    return dict(surface="signals", status="observed", items=items,
                scope=channel.get("scope"),
                version=VIEW_VERSION, pagination=channel.get('pagination'),
                note=("publication time and first-seen time are both shown; "
                      "first-seen is what a replay is bounded by"))


def sector_panel(channel: dict, *, hawkes_sector_flags=None) -> dict:
    """SECTOR STRESS — two channels, side by side, never merged.

    `news` is derived from events and documented exposure. `hawkes` is the
    measured pillar diagnostic. They have different units and different
    coverage, and the panel says so rather than averaging them into one bar.
    """
    rolled = aggregate_by([e for e in channel["estimates"]
                           if e.target_kind == "sector"])
    news_rows = [dict(
        sector=target.removeprefix("sector:"), channel="news",
        severity=bucket["severity"],
        evidence_confidence=bucket["evidence_confidence"],
        direction=bucket["direction"], mechanisms=bucket["mechanisms"],
        events=bucket["estimates"], event_ids=bucket["event_ids"],
        exposure_magnitude=bucket["exposure_magnitude"],
        exposure_unit=bucket["exposure_unit"],
        unsized_relationships=bucket["unsized_relationships"],
        unit="ordinal severity (minor|moderate|major|severe)",
        status="estimate")
        for target, bucket in sorted(rolled.items())]

    if hawkes_sector_flags:
        hawkes_rows = [dict(sector=sector, channel="hawkes", flag=flag,
                            unit="negative-jump intensity versus historical baseline", status="derived")
                       for sector, flag in sorted(hawkes_sector_flags.items())]
        hawkes_block = dict(status="derived", rows=hawkes_rows)
    else:
        hawkes_block = dict(
            status="unavailable", absence="structural", rows=[],
            reason=("No eligible measured sector intensity flags at the selected analysis cutoff; "
                    "missing coverage is not a measured zero."))

    return dict(
        surface="sector_stress", version=VIEW_VERSION,
        news=dict(status="estimate" if news_rows else "preview",
                  rows=news_rows,
                  reason=None if news_rows else
                  "no sector-level news estimate at this decision time"),
        hawkes=hawkes_block,
        separation_note=(
            "these are two different measurements. News sector stress is an "
            "ordinal severity derived from events and documented exposure. "
            "Hawkes sector stress is a measured branching-ratio diagnostic. "
            "They are not comparable and are never combined into one number"))


def geography_overlay(channel: dict, master: MasterData) -> dict:
    """Raised regions and arcs — each one backed by an evidenced relationship."""
    regions: dict[str, dict] = {}
    arcs: list[dict] = []
    for estimate in channel["estimates"]:
        place_id = master.place_of(estimate.target_id)
        if place_id:
            region = regions.setdefault(place_id, dict(
                place_id=place_id,
                name=getattr(master.places.get(place_id), "name", place_id),
                severity="minor", events=set(), status="estimate"))
            region["events"].add(estimate.event_id)
            order = ("minor", "moderate", "major", "severe")
            if order.index(estimate.severity) > order.index(region["severity"]):
                region["severity"] = estimate.severity
        for edge_id in estimate.path:
            edge = master.edges.get(edge_id)
            if edge is None:
                continue
            arcs.append(dict(
                edge_id=edge_id, from_id=edge.from_id, to_id=edge.to_id,
                mechanism=edge.mechanism, confidence=edge.confidence,
                evidence=[e.reference for e in edge.evidence],
                event_id=estimate.event_id, status="observed",
                relationship_status="documented", impact_status="hypothesis",
                # T13: an arc the globe draws must carry its own direction,
                # size and validity. A magnitude with no unit is refused by
                # ExposureEdge itself, so an arc either has both or neither.
                direction=getattr(estimate, "direction", "unknown"),
                magnitude=edge.magnitude, unit=edge.unit,
                valid_from=edge.valid_from, valid_to=edge.valid_to,
                known_at=edge.known_from,
                note="a documented relationship, not a fitted contagion edge"))
    if not regions and not arcs:
        return _preview("geography",
                        "no evidenced place or relationship is reachable from the "
                        "events visible at this decision time")
    for region in regions.values():
        region["events"] = sorted(region["events"])
    # One arc per (edge, event): a repeated path does not thicken the line.
    unique = {(a["edge_id"], a["event_id"]): a for a in arcs}
    return dict(surface="geography", status="estimate", version=VIEW_VERSION,
                regions=sorted(regions.values(), key=lambda r: r["place_id"]),
                arcs=sorted(unique.values(), key=lambda a: a["edge_id"]),
                note=("every arc is an ExposureEdge with its own evidence. No arc "
                      "is derived from the CSRS channel"))


def asset_overlay(channel: dict, master: MasterData) -> dict:
    """STRATEGIC ASSETS — the registry, with any events touching each site."""
    if not master.assets:
        return _preview("assets",
                        "the curated asset registry is empty; rows require a "
                        "citation (seraph/news/curated/assets.csv)")
    touched: dict[str, list[str]] = {}
    for estimate in channel["estimates"]:
        if estimate.target_kind == "asset":
            touched.setdefault(estimate.target_id, []).append(estimate.event_id)
    items = []
    for asset in sorted(master.assets.values(), key=lambda a: a.asset_id):
        items.append(dict(
            asset_id=asset.asset_id, name=asset.name, kind=asset.kind,
            place_id=asset.place_id, operator=asset.operator_entity_id,
            capacity=asset.capacity, capacity_unit=asset.capacity_unit,
            status=asset.status, lat=asset.lat, lon=asset.lon,
            source=asset.source, events=sorted(touched.get(asset.asset_id, [])),
            data_status="observed"))
    return dict(surface="assets", status="observed", items=items,
                version=VIEW_VERSION,
                note="an asset's location is the facility's, not its operator's")


def _role_projection(channel, master, role, holdings, store):
    """The role-specific view, or None with a reason.

    Never allowed to break the page: a role projection is a convenience over
    facts that are already on the payload, and a failure here must not take
    the console down with it.
    """
    if not role:
        return None
    try:
        from seraph.news.roles import role_view
        return role_view(channel, master, role, holdings=holdings, store=store)
    except Exception as exc:                        # noqa: BLE001 - optional
        return dict(role=role, items=[], uncovered=[],
                    notes=[f"role view unavailable: {type(exc).__name__}. The "
                           f"shared facts below are unaffected"])


def build_news_payload(store, master: MasterData, *, decision_ts: str,
                       sectors: dict | None = None,
                       hawkes_sector_flags=None, offset: int = 0,
                       limit: int = 40, role: str | None = None,
                       holdings=None, strict_replay: bool = False) -> dict:
    """Everything the console's news-side surfaces need, in one coherent read."""
    channel = news_channel(store, master, decision_ts=decision_ts, sectors=sectors,
                           offset=offset, limit=limit, strict_replay=strict_replay)
    master = channel["master"]
    surfaces = dict(
        signals=signals_rail(channel, limit=limit),
        sector_stress=sector_panel(channel,
                                   hawkes_sector_flags=hawkes_sector_flags),
        geography=geography_overlay(channel, master),
        assets=asset_overlay(channel, master),
    )
    # Attached to EVERY surface, not just the rail. The defect being fixed is
    # that the globe and the sector panel described a stale world without
    # saying so, and they are the surfaces a reader acts on.
    freshness = channel["freshness"]
    for surface in surfaces.values():
        surface["freshness"] = freshness

    connected = [name for name, surface in surfaces.items()
                 if surface.get("status") != "preview"
                 and not (name == "sector_stress"
                          and surface["news"]["status"] == "preview")]
    return dict(
        decision_ts=decision_ts, version=VIEW_VERSION,
        source_coverage=channel["source_coverage"], pagination=channel["pagination"],
        freshness=freshness,
        currency={k: v for k, v in channel["currency"].items() if k != "states"},
        # Instrument linkage and, more importantly, the documents that end
        # or amend something nothing here identifies: while a link is
        # missing the earlier order is still reported as in force, and that
        # has to be visible rather than merely true.
        supersession=dict(
            channel["supersession"],
            proposals=[p for p in channel["supersession"]["proposals"]
                       if p.get("status") == "proposed"][:50],
            links_count=len(channel["supersession"]["links"])),
        # Three projections of the SAME facts. A number that differed between
        # roles would mean one of them was wrong, so nothing here recomputes.
        role_view=_role_projection(channel, master, role, holdings, store),
        surfaces=surfaces,
        connected_surfaces=connected,
        preview_surfaces=[n for n in surfaces if n not in connected],
        registry=master.describe(),
        # Source, document, registry, grouping, extractor and estimation
        # versions, plus whether this is a reconstruction or a replay.
        manifest=channel["manifest"],
        temporal_policy=master.temporal_assumptions,
        # The KIND travels with the row. Re-guessing it at the other end of
        # the transport is how a reported epicentre became a city.
        source_places=[dict(place_id=p.place_id, name=p.name, kind=p.kind,
                            lat=p.lat, lon=p.lon)
                       for p in master.places.values()
                       if p.place_id.startswith("hazard_")],
        injection_flags=channel["injection_flags"],
        channel_note=(
            "this is the news channel (F2). It is separate from the market "
            "pillar channel (F1) that produces CSRS: different sources, "
            "different units, separate evaluation. Nothing here is a "
            "probability of financial loss"),
    )
