"""What each role needs from the same facts.

Role navigation existed; role-specific news intelligence did not. Every role
saw the identical signal rail, so the question each role actually has went
unanswered:

* **Retail** — "does any of this touch what I hold, and what do you not know
  about my holdings?" The second half matters more: an unmapped holding is
  not a holding with no risk, it is one this system cannot speak about, and
  presenting a clean screen for it is the most misleading thing available.
* **Institutional** — "what are the opposing mechanisms, and what is
  uncertain?" A single signed direction is not an analysis.
* **Regulator** — "where is coverage missing, can I follow the evidence, and
  what has been corrected?"

**One set of facts.** These are three projections of the same channel, not
three pipelines. A number that differs between roles would mean one of them
is wrong, so nothing here recomputes anything — it selects and frames.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ROLES = ("retail", "institutional", "regulator")


@dataclass
class RoleView:
    role: str
    items: list = field(default_factory=list)
    uncovered: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    #: Institutional only: the product/origin shape of the documented
    #: exposure, and the instrument pairs worth comparing side by side.
    matrix: dict | None = None
    comparable: list = field(default_factory=list)

    def describe(self) -> dict:
        described = dict(role=self.role, items=self.items,
                         uncovered=self.uncovered, notes=list(self.notes))
        if self.matrix is not None:
            described["matrix"] = self.matrix
        if self.comparable:
            described["comparable"] = list(self.comparable)
        return described


def _targets_of(estimates) -> dict:
    by_target = {}
    for estimate in estimates:
        by_target.setdefault(estimate.target_id, []).append(estimate)
    return by_target


def holding_rows(holdings):
    """C11 -> C12 boundary: raw rows or the portfolio tool's projection.

    `exposurePct` is the holding's portfolio weight, never a loss estimate.
    """
    if isinstance(holdings, dict):
        holdings = holdings.get("byHolding", [])
    for row in holdings or ():
        if not isinstance(row, dict):
            raise ValueError("holdings must contain objects")
        row = dict(row)
        row["sector"] = row.get("sector") or row.get("sectorId")
        if isinstance(row['sector'], str) and row['sector'].strip().lower() in (
                'unclassified', 'sector:unclassified', '', 'sector:'):
            row["sector"] = None
        yield row


def retail_view(channel, master, holdings) -> RoleView:
    """Which holdings are touched, and which this system cannot speak about.

    `holdings` is a list of {symbol|entity_id, sector?} as the user supplied
    it. Nothing is inferred about a holding that does not resolve: it goes in
    `uncovered`, which is the half of this view that carries the warning.
    """
    view = RoleView("retail")
    by_target = _targets_of(channel.get("estimates", ()))

    for holding in holding_rows(holdings):
        name = (holding.get("entity_id") or holding.get("symbol")
                or holding.get("name") or "")
        sector = holding.get("sector")
        entity = master.entities.get(name)
        if entity is None:
            # Try the resolver before giving up, but never guess.
            resolution = master.resolve(name) if name else None
            entity = (master.entities.get(resolution.entity_id)
                      if resolution and getattr(resolution, "status", "") == "resolved"
                      else None)

        selected_sector = (entity.sector if entity else None) or sector
        sector_key = "sector:" + (selected_sector or "").removeprefix("sector:")
        targets = {name}
        if entity:
            targets.add(entity.entity_id)
        if sector_key != "sector:":
            targets.add(sector_key)
        touching = []
        seen = set()
        for target in sorted(targets):
            for estimate in by_target.get(target, ()):
                key = (estimate.event_id, estimate.target_id, estimate.mechanism)
                if key not in seen:
                    touching.append(estimate)
                    seen.add(key)

        if entity is None and sector is None:
            view.uncovered.append(dict(
                holding=name, reason=(
                    "not in the exposure registry and no sector supplied, so "
                    "nothing documented connects news to it. This is NOT a "
                    "finding that it is unaffected")))
            continue
        if entity is not None and not entity.sector and sector is None:
            view.uncovered.append(dict(
                holding=name, resolved_to=entity.entity_id, reason=(
                    "resolved, but this issuer has no sector in the registry, "
                    "so sector-level news cannot route to it")))
            continue

        view.items.append(dict(
            holding=name,
            resolved_to=entity.entity_id if entity else None,
            sector=sector_key if sector_key != "sector:" else None,
            portfolio_weight_pct=holding.get("exposurePct"),
            touching=[dict(event_id=t.event_id, target=t.target_id,
                           direction=t.direction, mechanism=t.mechanism)
                      for t in touching],
            documented=bool(touching)))

    covered = sum(item["documented"] for item in view.items)
    view.notes.append(
        f"{covered} holding(s) have a documented route from news; "
        f"{len(view.items) - covered} mapped holdings have no current matched event; "
        f"{len(view.uncovered)} do not have a usable mapping. An unmapped holding is one this "
        f"system cannot speak about, not one that is unaffected")
    view.notes.append(
        "directions are qualitative hypotheses about mechanism. None of this "
        "is a probability of loss or a position recommendation")
    return view


def _scenario_for(estimate, event, master, decision_ts):
    """The accounting scenario for one route, or why there is none.

    This is the production caller the audit found missing: the tariff
    arithmetic existed and was tested, and nothing on any screen used it,
    so a duty change reached a reader as a direction and a severity band
    with no statement of how much the landed cost of the covered article
    moves. Failures are returned, not swallowed — "no scenario, because
    the document states one rate and not the other" is itself the useful
    answer.
    """
    if event is None or master is None:
        return None
    if event.event_type not in ("tariff_announcement", "import_duty_change",
                                "trade_remedy_determination"):
        return None
    edge = None
    for edge_id in reversed(estimate.path or ()):
        candidate = master.edges.get(edge_id)
        if candidate is not None and candidate.products:
            edge = candidate
            break
    try:
        from seraph.news.scenarios import scenario_for
        return scenario_for(event, master, edge=edge,
                            on=(decision_ts or "")[:10] and decision_ts,
                            # Unsized by construction here: the exposure
                            # registry records no financial denominators,
                            # so no monetary range is produced.
                            eligible_cost_base=None)
    except Exception as exc:                        # noqa: BLE001 - optional
        return dict(status="unavailable",
                    reasons=[f"{type(exc).__name__}: {exc}"])


def institutional_view(channel, master=None) -> RoleView:
    """Opposing mechanisms, the assumptions behind them, and what is unknown."""
    view = RoleView("institutional")
    events = {e.event_id: e for e in channel.get("eligible_events", ())}
    master = master if master is not None else channel.get("master")
    decision_ts = channel.get("decision_ts")

    for estimate in channel.get("estimates", ()):
        event = events.get(estimate.event_id)
        frame = getattr(event, "frame", None) if event else None
        opposing = None
        if event is not None:
            from seraph.news.opposing import opposing_parties
            found = opposing_parties(event)
            if found.constrained or found.benefiting:
                opposing = found.describe()
        view.items.append(dict(
            event_id=estimate.event_id,
            evidence_links=channel.get("references", {}).get(estimate.event_id, []),
            target=estimate.target_id, direction=estimate.direction,
            mechanism=estimate.mechanism,
            confidence=estimate.evidence_confidence,
            size=estimate.exposure_magnitude,
            unit=estimate.exposure_unit,
            opposing=opposing,
            scenario=_scenario_for(estimate, event, master, decision_ts),
            unknowns=list(getattr(frame, "unknowns", ()) or ()),
            limitations=list(estimate.limitations),
            path=[str(step) for step in (estimate.path or ())]))

    # --- the product/country shape of the exposure, not one route at a time
    if master is not None:
        from seraph.news.comparison import product_country_matrix
        view.matrix = product_country_matrix(channel, master)

    # --- instruments worth comparing side by side ----------------------
    # Offered, not guessed: a pair is proposed only where two documents
    # CITE the same instrument identifier, which is the same evidence
    # standard the supersession linkage uses.
    pairs, by_instrument = [], {}
    for event in channel.get("eligible_events", ()) or ():
        for cited in getattr(event, "instrument_ids", ()) or ():
            by_instrument.setdefault(cited, []).append(event)
    for cited, group in sorted(by_instrument.items()):
        ordered = sorted(group, key=lambda e: ((e.timing.first_seen_at
                                                if e.timing else "") or "",
                                               e.event_id))
        for earlier, later in zip(ordered, ordered[1:]):
            pairs.append(dict(instrument_id=cited,
                              earlier=earlier.event_id, later=later.event_id,
                              earlier_headline=earlier.headline[:110],
                              later_headline=later.headline[:110]))
    view.comparable = pairs[:25]

    unsized = sum(1 for i in view.items if i["size"] is None)
    priced = sum(1 for i in view.items
                 if (i["scenario"] or {}).get("status") == "conditional_scenario")
    view.notes.append(
        f"{unsized} of {len(view.items)} documented relationship(s) are "
        f"UNSIZED. A direction without a size supports a question, not a "
        f"position")
    view.notes.append(
        f"{priced} route(s) carry an accounting scenario. A scenario states "
        f"the change in the landed cost of the covered article from the "
        f"instrument's own rates; it is not a loss, a return or a forecast, "
        f"and it carries no monetary range because no relationship here has "
        f"a financial denominator")
    view.notes.append(
        "where an instrument has opposing sides, both are listed and the net "
        "is not computed: it needs sizes this system does not hold")
    return view


def regulator_view(channel, store=None) -> RoleView:
    """Coverage gaps, unresolved references and the evidence trail."""
    view = RoleView("regulator")
    coverage = channel.get("source_coverage") or {}
    freshness = channel.get("freshness") or {}
    scope = channel.get("scope") or {}

    view.items.append(dict(kind="coverage", covered=coverage.get("covered"),
                           total=coverage.get("total"),
                           uncovered=list(coverage.get("uncovered") or ()),
                           gaps=list(coverage.get("coverage_gaps") or ())))
    view.items.append(dict(kind="acquisition",
                           worker_state=freshness.get("worker_state"),
                           newest=freshness.get("newest_first_seen_at"),
                           stale=freshness.get("stale")))
    view.items.append(dict(kind="scope", in_scope=scope.get("in_scope"),
                           out_of_scope=scope.get("out_of_scope"),
                           unidentified=scope.get("unclassified_in_scope")))
    view.items.append(dict(kind="rights", **(coverage.get("rights") or {})))
    if store is not None:
        try:
            redactions = store.redactions()
            view.items.append(dict(
                kind="retention",
                redacted=len(redactions), sample=redactions[:10],
                note=("text removed under each source's declared retention "
                      "window. The observation, its content hash and this "
                      "record remain, so a retention policy cannot be used "
                      "to rewrite what the system once held")))
        except Exception:                           # noqa: BLE001 - optional
            pass

    unresolved = list(channel.get("unresolved", ()))
    for event in channel.get("eligible_events", ()):
        for mention in getattr(event, "unresolved", ()) or ():
            unresolved.append(dict(event_id=event.event_id, mention=mention))
    view.items.append(dict(kind="unresolved", count=len(unresolved),
                           sample=unresolved[:25]))

    # Instruments that end or amend something nothing here identifies. This
    # is review work with a consequence: while the link is missing, the
    # earlier order is still reported as in force.
    supersession = channel.get("supersession") or {}
    view.items.append(dict(
        kind="supersession_review",
        linked=len(supersession.get("links") or {}),
        proposed=[p for p in (supersession.get("proposals") or ())
                  if p.get("status") == "proposed"][:25],
        unresolved=list(supersession.get("unresolved") or ())[:25],
        reviews=list(supersession.get("reviews") or ())[:25],
        note=supersession.get("note")))

    if store is not None:
        try:
            # Bounded by the decision time like everything else on this
            # payload. Listing a gap first observed at 10:00 in an 08:00
            # replay reports, as of eight, something learned at ten.
            view.items.append(dict(
                kind="collection_gaps",
                open=store.open_gaps(visible_at=channel.get("decision_ts")),
                note=("gaps as they stood at the decision time: observed by "
                      "then and not yet closed")))
        except Exception:                       # noqa: BLE001 - optional
            pass

    view.notes.append(
        "every number here is a statement about COVERAGE, not about the "
        "market. An empty map with uncovered sources is missing data, not a "
        "quiet day")
    view.notes.append(
        "each event links to the document it came from; an inference links "
        "to the documented relationship it used")
    return view


def role_view(channel, master, role: str, *, holdings=None, store=None) -> dict:
    """One projection of the shared facts, selected for the role."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    if role == "retail":
        return retail_view(channel, master, holdings).describe()
    if role == "institutional":
        return institutional_view(channel, master).describe()
    return regulator_view(channel, store).describe()
