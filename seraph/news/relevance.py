"""NI16 — is this event in scope for an Indian equity portfolio at all?

Half the pilot corpus classifies as `other`, and reading it rather than
counting it shows the rate is not an extraction failure. The Federal Register
feed carries the *entire* US federal daily register, so the unrecognised pile
is mostly:

    Marine Mammals; Incidental Take of Polar Bears ... in the Beaufort Sea
    Bulk Manufacturer of Controlled Substances Application: Groff Health Inc
    Agency Information Collection Request: 3206-0218, Death Benefit Payment
    Pacific Fishery Management Council; Public Meetings
    Privacy Act of 1974; System of Records

None of these is a market-risk event for an Indian portfolio, and inventing
event types for "Notice of Public Meeting" would make the classification rate
look better while making the output worse — it would dress irrelevant noise up
as recognised events.

So the question is split in two. **Relevance** asks whether an event touches
anything this system is about; **classification** asks what an event is. Kept
separate, `other` recovers the meaning the ledger claims for it: *we do not
know what this is*. A Hindi PIB release about Indian agriculture is in scope
and unclassified — an honest state worth seeing. A US fishery council meeting
is neither.

The test is deliberately **inclusive**, because the cost of wrongly excluding
an event is higher than the cost of carrying a few irrelevant ones: anything
that resolves an Indian place, a registered entity or asset, a sector the
exposure registry covers, or an action by a monetary or market authority this
system tracks, stays in scope. Nothing is deleted or hidden either way — an
out-of-scope event keeps its row, its evidence and its link, and is counted
where it can be seen.
"""
from __future__ import annotations

from dataclasses import dataclass

from seraph.news.model import Event
from seraph.news.registry import MasterData

#: Event classes that are market-relevant by their nature, because the body
#: issuing them sets monetary, prudential or market-structure policy. These
#: reach an Indian portfolio through rates, liquidity and funding conditions
#: whether or not the text names an Indian place.
AUTHORITY_EVENT_TYPES = frozenset({
    "policy_rate_decision",
    "reserve_requirement_change",
    "liquidity_operation",
    "prudential_norms_change",
    "forex_regulation",
    "bank_resolution",
    "debt_instrument_event",
})

#: Classes that carry a cross-border measure. A trade remedy, tariff or export
#: restriction is in scope even before a subject origin resolves, because the
#: subject may be an Indian product the place registry does not yet hold.
TRADE_EVENT_TYPES = frozenset({
    "trade_remedy_determination",
    "tariff_announcement",
    "import_duty_change",
    "export_restriction",
    "sanctions_action",
})


@dataclass(frozen=True)
class Relevance:
    """Why an event is, or is not, in scope. Never a bare boolean: an
    exclusion that cannot state its reason cannot be argued with."""

    in_scope: bool
    reasons: tuple[str, ...] = ()

    def describe(self) -> dict:
        return dict(in_scope=self.in_scope, reasons=list(self.reasons))


def _indian(master: MasterData, node_id: str) -> bool:
    """Is this registry node in India?

    Walks `parent_id` so a district resolves through its state to its country
    rather than needing its own ISO code.
    """
    seen = set()
    current = node_id
    while current and current not in seen:
        seen.add(current)
        place = master.places.get(current)
        if place is None:
            break
        if (place.iso_code or "").upper() == "IND" or place.place_id == "in":
            return True
        current = place.parent_id
    return False


def assess_relevance(event: Event, master: MasterData, *,
                     issuer_places: "tuple[str, ...] | list[str]" = ()) -> Relevance:
    """Decide whether `event` is in scope, and say why.

    Inclusive by construction: any single basis is enough, and the reasons are
    accumulated rather than short-circuited so the rail can show all of them.

    `issuer_places` is the publishing source's own jurisdiction, which is a
    basis **only when it is India**. An Indian official source publishing an
    announcement is about India whether or not the extractor could read the
    text — a Hindi PIB release was being ruled out of scope because the Hindi
    interpreter abstains, which hid a known coverage gap behind a relevance
    label. The converse does not hold: a US publisher's jurisdiction is the
    United States for its entire daily register, so treating any issuer
    jurisdiction as a basis would admit everything and decide nothing.
    """
    reasons: list[str] = []

    located = {node_id for node_id, _role in event.locations}
    located |= set(event.affected) | set(event.exposure_origins)

    indian_nodes = sorted(n for n in located if _indian(master, n))
    if indian_nodes:
        reasons.append("resolves an Indian place: " + ", ".join(indian_nodes))

    registered = sorted(n for n in located | set(event.actors)
                        if n in master.entities or n in master.assets)
    if registered:
        reasons.append("names a registered entity or asset: "
                       + ", ".join(registered))

    # A sector the exposure registry can actually route to. A sector mentioned
    # with no edge reaching it cannot produce an inference, so it is not on
    # its own a reason to call the event in scope.
    sector_targets = {edge.to_id for edge in master.edges.values()
                      if edge.to_id.startswith("sector:")}
    sectors = sorted(located & sector_targets)
    if sectors:
        reasons.append("touches a mapped sector: " + ", ".join(sectors))

    if event.event_type in AUTHORITY_EVENT_TYPES:
        reasons.append(f"monetary, prudential or market-structure action "
                       f"({event.event_type})")
    if event.event_type in TRADE_EVENT_TYPES:
        reasons.append(f"cross-border measure ({event.event_type}); the "
                       f"subject origin may be unresolved rather than absent")

    if event.event_type == "physical_hazard" and event.affected:
        reasons.append("physical hazard with a resolved affected location")

    # Deliberately last and deliberately narrow: see the docstring.
    indian_issuers = sorted(p for p in issuer_places if _indian(master, p))
    if indian_issuers:
        reasons.append("published by a source whose own jurisdiction is India "
                       "(" + ", ".join(indian_issuers) + "); this is the "
                       "publisher's jurisdiction, not a location parsed from "
                       "the text")

    if reasons:
        return Relevance(True, tuple(reasons))
    return Relevance(False, (
        "no Indian place, registered entity or asset, mapped sector, tracked "
        "monetary or market authority, or cross-border measure. Carried and "
        "counted, not deleted: a source feed covering a whole jurisdiction's "
        "daily register contains far more than this system is about.",))
