"""Who gains and who loses from the same measure, side by side.

`EventFrameV2` has carried `beneficiaries` and `constrained_parties` since it
was written, and nothing ever populated them. So every impact reached the
screen as a single signed direction for a single target, and the reader was
never shown the other side — which for a trade measure is not a nuance, it is
half the event.

A duty on imports of a product from India:

  * **constrains** the Indian exporter of that product,
  * **benefits** the producer in the importing country who competes with it,
  * **constrains** the downstream buyer in the importing country who now pays
    more for an input.

All three are consequences of one instrument. Reporting only the first makes
the measure look like unambiguous bad news; reporting only the second makes it
look like good news. The honest presentation is both, with the mechanism
named, and an explicit statement that the NET effect is not computed — because
computing it would need sizes this system does not have.

**This module derives roles, not parties.** It says "an exporter of this
product is constrained"; it does not claim to know which companies those are.
Naming them needs the exposure registry, which carries the documented
relationships and their citations.
"""
from __future__ import annotations

from dataclasses import dataclass

#: event class -> (constrained roles, benefiting roles, the mechanism).
#: Each entry is a structural fact about the instrument class, not a forecast.
OPPOSING_ROLES: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "trade_remedy_determination": (
        ("exporter", "downstream_buyer_in_importing_country"),
        ("domestic_producer",),
        "a duty raises the landed cost of the covered product"),
    "tariff_announcement": (
        ("exporter", "downstream_buyer_in_importing_country"),
        ("domestic_producer",),
        "a tariff raises the landed cost of the covered product"),
    "import_duty_change": (
        ("exporter", "downstream_buyer_in_importing_country"),
        ("domestic_producer",),
        "an import duty raises the landed cost of the covered product"),
    "export_restriction": (
        ("exporter", "downstream_buyer_abroad"),
        ("domestic_buyer",),
        "restricting exports keeps supply at home and withholds it abroad"),
    "subsidy_change": (
        ("competitor_of_beneficiary",), ("beneficiary",),
        "a subsidy lowers the beneficiary's cost relative to competitors"),
    "policy_rate_decision": (
        ("borrower",), ("saver", "lender"),
        "a higher policy rate raises the cost of borrowing and the return on "
        "deposits"),
    "price_control": (
        ("seller",), ("buyer",),
        "an administered price or margin cap transfers from seller to buyer"),
}

#: Measures whose END reverses the roles. A revocation relieves whoever the
#: measure constrained and exposes whoever it protected.
REVERSING_STATUSES = frozenset({"repealed", "suspended"})


@dataclass(frozen=True)
class OpposingView:
    """Both sides of one measure, with the net deliberately absent."""

    constrained: tuple[str, ...] = ()
    benefiting: tuple[str, ...] = ()
    mechanism: str = ""
    reversed_by_status: bool = False
    basis: str = ""

    @property
    def is_two_sided(self) -> bool:
        return bool(self.constrained and self.benefiting)

    def describe(self) -> dict:
        return dict(
            constrained_roles=list(self.constrained),
            benefiting_roles=list(self.benefiting),
            mechanism=self.mechanism,
            reversed_by_status=self.reversed_by_status,
            basis=self.basis,
            net_effect=("NOT COMPUTED. Both sides are consequences of one "
                        "instrument; which dominates depends on sizes this "
                        "system does not hold, so no net is asserted"))


def opposing_parties(event) -> OpposingView:
    """The roles a measure constrains and benefits, or an empty view.

    An empty view is the correct answer for an event that is not an
    instrument — a hazard harms without benefiting anyone in particular, and
    inventing a beneficiary would be worse than saying nothing.
    """
    mapping = OPPOSING_ROLES.get(getattr(event, "event_type", None))
    if mapping is None:
        return OpposingView(
            basis=(f"{getattr(event, 'event_type', 'this event')} is not an "
                   f"instrument with opposing sides, or its structure has not "
                   f"been established"))

    constrained, benefiting, mechanism = mapping
    frame = getattr(event, "frame", None)
    status = getattr(frame, "policy_status", None) if frame else None

    if status in REVERSING_STATUSES:
        # Ending a measure relieves whoever it constrained and exposes
        # whoever it protected. The roles do not change; the sign does.
        return OpposingView(
            constrained=benefiting, benefiting=constrained,
            mechanism=mechanism, reversed_by_status=True,
            basis=(f"the measure is {status}: ending it reverses who gains "
                   f"and who loses, because {mechanism}"))

    return OpposingView(constrained=constrained, benefiting=benefiting,
                        mechanism=mechanism,
                        basis=f"for this class of instrument, {mechanism}")


def annotate(event):
    """Return the frame fields this view implies, for the extractor to set."""
    view = opposing_parties(event)
    return dict(beneficiaries=view.benefiting,
                constrained_parties=view.constrained)
