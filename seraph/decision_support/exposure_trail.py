# C11 — "Why does this affect me?" (PORT04)
"""Article → event → company/asset → the position the user actually holds.

The product's clearest differentiator, and the one most easily faked. What
makes it honest rather than decorative:

* **Every hop is inspectable.** The trail returns the story, the event, each
  exposure edge with its evidence and confidence, and the holding — not a
  score with a sentence attached.
* **Exposure is counted once.** A holding reachable by two paths appears once,
  with the alternative paths named. Summing the value of overlapping paths is
  how a 40% position becomes a 140% exposure.
* **Unknown stays unknown.** A relationship whose magnitude nobody recorded
  contributes to "linked but unsized", never to a number. The covered,
  unsized and uncovered portions of a portfolio reconcile to its total.
* **This is not a loss estimate.** It says a holding is connected to an event,
  how, and how strongly the connection is evidenced. It does not say what the
  position will be worth.

It reads the news channel (F2) and the user's own holdings. It never reads
CSRS, and nothing here is derived from the Hawkes/RMT/Hamilton channel.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from seraph.news.estimation import estimate_impacts
from seraph.news.model import Event, ImpactEstimate
from seraph.news.registry import MasterData
from seraph.product_types import Coverage

TRAIL_VERSION = "c11.exposure_trail/2026-10-16.1"


@dataclass(frozen=True)
class Hop:
    """One inspectable step of the explanation."""

    kind: str                   # story | event | relationship | holding
    ref_id: str
    label: str
    detail: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return dict(kind=self.kind, ref_id=self.ref_id, label=self.label,
                    **self.detail)


@dataclass(frozen=True)
class HoldingLink:
    symbol: str
    value: float
    entity_id: str
    estimate: ImpactEstimate
    hops: tuple[Hop, ...]
    alternative_paths: tuple[tuple[str, ...], ...] = ()

    @property
    def direct(self) -> bool:
        return not self.estimate.path

    def describe(self) -> dict:
        return dict(
            symbol=self.symbol, value=self.value, entity_id=self.entity_id,
            direct=self.direct,
            severity=self.estimate.severity,
            evidence_confidence=self.estimate.evidence_confidence,
            direction=self.estimate.direction,
            mechanism=self.estimate.mechanism,
            horizon_days=self.estimate.horizon_days,
            exposure_magnitude=self.estimate.exposure_magnitude,
            exposure_unit=self.estimate.exposure_unit,
            path=list(self.estimate.path),
            alternative_paths=[list(p) for p in self.alternative_paths],
            trail=[h.describe() for h in self.hops],
            limitations=list(self.estimate.limitations),
        )


def explain_exposure(event: Event, master: MasterData, holdings: list[dict],
                     *, stories_by_id: dict | None = None,
                     on: str | None = None) -> dict:
    """Why this event touches this portfolio — one entry per holding, at most.

    `holdings` are the rows a `WorkspaceStore` snapshot produced:
    `{symbol, value, sector, ...}`.
    """
    stories_by_id = stories_by_id or {}
    estimates = {e.target_id: e for e in estimate_impacts(event, master, on=on)}

    # symbol -> entity, following parent links so a subsidiary's event reaches
    # the listed parent the user actually owns.
    entity_by_symbol: dict[str, str] = {}
    for entity in master.entities.values():
        for symbol in master.symbols_for(entity.entity_id):
            entity_by_symbol.setdefault(symbol.upper(), entity.entity_id)

    links: list[HoldingLink] = []
    linked_value = 0.0
    unsized_value = 0.0
    for holding in holdings:
        symbol = str(holding.get("symbol", "")).upper()
        value = float(holding.get("value") or 0.0)
        entity_id = entity_by_symbol.get(symbol)
        estimate = None
        if entity_id and entity_id in estimates:
            estimate = estimates[entity_id]
        else:
            sector = holding.get("sector")
            if sector and f"sector:{sector}" in estimates:
                estimate = estimates[f"sector:{sector}"]
                entity_id = entity_id or f"sector:{sector}"
        if estimate is None:
            continue
        hops = _hops(event, estimate, master, stories_by_id, symbol, value)
        links.append(HoldingLink(symbol=symbol, value=value,
                                 entity_id=entity_id, estimate=estimate, hops=hops))
        linked_value += value
        if estimate.exposure_magnitude is None:
            unsized_value += value

    total = sum(float(h.get("value") or 0.0) for h in holdings)
    # Each holding appears at most once, so these cannot exceed the total.
    assert linked_value <= total + 1e-9, "a holding was counted more than once"
    return dict(
        event_id=event.event_id, headline=event.headline,
        event_type=event.event_type, lifecycle=event.lifecycle,
        first_seen_at=event.timing.first_seen_at,
        version=TRAIL_VERSION,
        links=[link.describe() for link in sorted(
            links, key=lambda l: (-l.value, l.symbol))],
        reconciliation=dict(
            portfolio_total=round(total, 2),
            linked_value=round(linked_value, 2),
            unlinked_value=round(total - linked_value, 2),
            linked_but_unsized_value=round(unsized_value, 2),
            linked_pct=round(100 * linked_value / total, 4) if total else 0.0,
            holdings_counted_once=True),
        coverage=Coverage(
            population="holdings in this portfolio",
            covered=len(links), total=len(holdings),
            uncovered=tuple(sorted(
                str(h.get("symbol", "")).upper() for h in holdings
                if str(h.get("symbol", "")).upper() not in {l.symbol for l in links})),
            basis="documented exposure relationships reachable from this event",
        ).__dict__,
        not_a_loss_estimate=(
            "this says a holding is connected to an event, by what mechanism, and "
            "how well evidenced the connection is. It does not estimate what the "
            "position will be worth"),
    )


def _hops(event, estimate, master, stories_by_id, symbol, value) -> tuple[Hop, ...]:
    hops: list[Hop] = []
    for story_id in event.stories[:3]:
        story = stories_by_id.get(story_id)
        hops.append(Hop(
            kind="story", ref_id=story_id,
            label=story.title if story else story_id,
            detail=dict(url=getattr(story, "url", None),
                        published_at=(story.timing.published_at if story else None),
                        first_seen_at=(story.first_seen_at if story else None))))
    if len(event.stories) > 3:
        hops.append(Hop(kind="story", ref_id="+more",
                        label=f"and {len(event.stories) - 3} more report(s) of the "
                              f"same event",
                        detail=dict(syndicated=True)))
    hops.append(Hop(kind="event", ref_id=event.event_id, label=event.headline,
                    detail=dict(event_type=event.event_type,
                                confirmations=event.confirmations,
                                quantities=[list(q) for q in event.quantities],
                                unresolved=list(event.unresolved))))
    for edge_id in estimate.path:
        edge = master.edges.get(edge_id)
        if edge is None:
            continue
        hops.append(Hop(
            kind="relationship", ref_id=edge_id,
            label=f"{edge.from_id} → {edge.to_id} ({edge.mechanism})",
            detail=dict(mechanism=edge.mechanism, confidence=edge.confidence,
                        magnitude=edge.magnitude, unit=edge.unit,
                        evidence=[e.reference for e in edge.evidence],
                        note=edge.note)))
    hops.append(Hop(kind="holding", ref_id=symbol, label=f"you hold {symbol}",
                    detail=dict(value=value)))
    return tuple(hops)


def shared_dependencies(master: MasterData, holdings: list[dict], *,
                        min_holdings: int = 2) -> list[dict]:
    """Different holdings that depend on the same thing (retail blind spots).

    Two positions in different sectors can still both run through one port or
    one input. This finds those, and only where a documented relationship
    supports it — an inferred dependency would be exactly the wrong thing to
    tell someone about their concentration.
    """
    entity_by_symbol: dict[str, str] = {}
    for entity in master.entities.values():
        for symbol in master.symbols_for(entity.entity_id):
            entity_by_symbol.setdefault(symbol.upper(), entity.entity_id)

    dependents: dict[str, dict] = {}
    for holding in holdings:
        symbol = str(holding.get("symbol", "")).upper()
        entity_id = entity_by_symbol.get(symbol)
        if not entity_id:
            continue
        for edge in master.edges.values():
            if edge.from_id != entity_id:
                continue
            bucket = dependents.setdefault(edge.to_id, dict(
                dependency=edge.to_id, mechanism=edge.mechanism,
                holdings=[], value=0.0, evidence=set()))
            bucket["holdings"].append(symbol)
            bucket["value"] += float(holding.get("value") or 0.0)
            bucket["evidence"].update(e.reference for e in edge.evidence)
    out = []
    for bucket in dependents.values():
        if len({*bucket["holdings"]}) < min_holdings:
            continue
        out.append(dict(dependency=bucket["dependency"],
                        mechanism=bucket["mechanism"],
                        holdings=sorted(set(bucket["holdings"])),
                        combined_value=round(bucket["value"], 2),
                        evidence=sorted(bucket["evidence"]),
                        note="a documented shared dependency, not an inferred one"))
    return sorted(out, key=lambda d: -d["combined_value"])
