"""NI03/NI16 — relevance is a different question from classification.

Half the pilot corpus classified as `other`, and that was read as an
extraction failure for weeks. Reading the events rather than counting them
shows it was not. The Federal Register feed carries the *entire* US federal
daily register:

    Marine Mammals; Incidental Take of Polar Bears ... in the Beaufort Sea
    Bulk Manufacturer of Controlled Substances Application: Groff Health Inc
    Agency Information Collection Request: 3206-0218, Death Benefit Payment
    Pacific Fishery Management Council; Public Meetings

Inventing event types for "Notice of Public Meeting" would have improved the
classification rate and made the output worse — irrelevant noise dressed up as
recognised events. So the question is split: **relevance** asks whether an
event touches anything this system is about, **classification** asks what it
is. Kept apart, `other` recovers its stated meaning — *we do not know what
this is* — and on the real corpus the in-scope unclassified count fell from
132 of 263 to 16 of 132, of which 13 are Hindi items that abstain by design.

Nothing is dropped either way. An out-of-scope event keeps its row, its
evidence and its link, and is counted where it can be seen.

The second half of this file pins the class that closed the English gap: SEBI
enforcement and recovery proceedings, which are a legal process with stages.
A notice of demand, an attachment, and a release are three different facts
about whether a constraint is in force — and none of them assigns a direction,
because most name individuals rather than issuers.
"""
from __future__ import annotations

import pytest

from seraph.news.extraction import extract_events
from seraph.news.model import Asset, Entity, Place, Story, Timing
from seraph.news.registry import MasterData
from seraph.news.relevance import assess_relevance

SEEN = "2026-10-17T09:00:00+05:30"


def registry() -> MasterData:
    data = MasterData()
    data.add_place(Place("in", "India", "country", iso_code="IND",
                         lat=22.0, lon=79.0))
    data.add_place(Place("us", "United States", "country", iso_code="USA",
                         lat=39.76, lon=-98.5))
    data.add_place(Place("in_od", "Odisha", "state", parent_id="in"))
    data.add_place(Place("in_od_kalinganagar", "Kalinganagar", "city",
                         parent_id="in_od", lat=20.98, lon=86.02))
    data.add_entity(Entity("tata_steel", "Tata Steel Limited", "company",
                           symbol="TATASTEEL", sector="steel"))
    data.add_asset(Asset("tata_kalinganagar", "Kalinganagar Works", "plant",
                         place_id="in_od_kalinganagar",
                         operator_entity_id="tata_steel"))
    return data


def story(title, body=None, source_id="federal_register"):
    return Story(story_id="s1", source_id=source_id, observation_id="o1",
                 title=title, url="https://example.invalid/1", body=body,
                 timing=Timing(first_seen_at=SEEN, published_at=SEEN),
                 syndication_group="g1")


def event_for(title, body=None, master=None, source_id="federal_register"):
    results = list(extract_events([story(title, body, source_id)],
                                  master or registry()))
    assert results and results[0].event is not None, title
    return results[0].event


# ------------------------------------------------------- out of scope

OUT_OF_SCOPE = [
    "Marine Mammals; Incidental Take of Polar Bears and Pacific Walruses in "
    "the Beaufort Sea and North Slope",
    "Bulk Manufacturer of Controlled Substances Application: Groff Health Inc",
    "Agency Information Collection Request: 3206-0218, Death Benefit Payment "
    "Rollover, RI 94-7",
    "Pacific Fishery Management Council; Public Meetings",
    "Privacy Act of 1974; System of Records",
    "President's Military Spouse Commission; Notice of Federal Advisory "
    "Committee Meeting",
]


@pytest.mark.parametrize("title", OUT_OF_SCOPE)
def test_a_whole_jurisdictions_daily_register_is_not_in_scope(title):
    master = registry()
    assert assess_relevance(event_for(title, master=master), master).in_scope is False


def test_an_exclusion_always_states_its_reason():
    """A bare boolean cannot be argued with. An exclusion that cannot say why
    it excluded something is not reviewable."""
    master = registry()
    relevance = assess_relevance(event_for(OUT_OF_SCOPE[0], master=master), master)
    assert relevance.reasons
    assert "not deleted" in relevance.reasons[0]


def test_out_of_scope_events_are_still_carried():
    """Relevance labels and counts; it does not filter. The count of received
    documents that are not about this system is a fact about coverage."""
    master = registry()
    results = list(extract_events([story(OUT_OF_SCOPE[0])], master))
    assert results[0].event is not None


# ----------------------------------------------------------- in scope

@pytest.mark.parametrize("title", [
    "Chromium Trioxide From India: Final Affirmative Determination",
    # The full headline: truncating it to "... From India" alone drops the
    # determination wording and the title then classifies on the word "rail".
    "Certain Freight Rail Couplers and Parts Thereof From India: Final "
    "Affirmative Countervailing Duty Determination",
])
def test_a_cross_border_measure_is_in_scope(title):
    master = registry()
    assert assess_relevance(event_for(title, master=master), master).in_scope


def test_a_trade_measure_is_in_scope_before_its_subject_resolves():
    """The subject origin may be unresolved rather than absent — 13 remedies
    name countries the curated registry does not hold. Excluding them would
    hide a registry gap behind a relevance label."""
    master = MasterData()                 # knows no places at all
    master.add_place(Place("us", "United States", "country", iso_code="USA"))
    relevance = assess_relevance(
        event_for("Widgets From Taiwan; Determinations", master=master), master)
    assert relevance.in_scope
    assert any("unresolved rather than absent" in r for r in relevance.reasons)


def test_a_central_bank_action_is_in_scope_without_an_indian_place():
    """These reach an Indian portfolio through rates and funding conditions
    whether or not the text names an Indian place."""
    master = registry()
    event = event_for("FOMC statement on the federal funds target range",
                      master=master)
    relevance = assess_relevance(event, master)
    assert relevance.in_scope
    assert any("monetary" in r for r in relevance.reasons)


def test_a_registered_asset_puts_an_event_in_scope():
    master = registry()
    event = event_for("Tata Steel inaugurates Phase II expansion of "
                      "Kalinganagar operations", master=master)
    assert assess_relevance(event, master).in_scope


def test_an_indian_publisher_is_itself_a_basis():
    """A Hindi PIB release was ruled OUT of scope because the Hindi
    interpreter abstains, so no Indian place resolved. That hid a declared
    coverage gap behind a relevance label: a release from an Indian
    government source is about India whether or not we can read it."""
    master = registry()
    event = event_for("सीअेक्षम "
                      "ने अनुपालन",
                      master=master, source_id="pib_releases")
    relevance = assess_relevance(event, master, issuer_places=["in"])
    assert relevance.in_scope
    assert any("publisher's jurisdiction" in r for r in relevance.reasons)


def test_a_us_publisher_jurisdiction_is_not_a_basis():
    """The converse must not hold. A US publisher's jurisdiction is the United
    States for its entire daily register, so admitting any issuer jurisdiction
    would admit everything and decide nothing."""
    master = registry()
    event = event_for(OUT_OF_SCOPE[0], master=master)
    assert assess_relevance(event, master, issuer_places=["us"]).in_scope is False


def test_an_indian_district_resolves_through_its_parent():
    """Kalinganagar carries no ISO code of its own; it is Indian because its
    state is, which is India's. Requiring an ISO code on every node would
    exclude every city and district in the registry."""
    master = registry()
    event = event_for("Flooding reported at Kalinganagar", master=master)
    located = {n for n, _ in event.locations}
    assert located, "the place did not resolve at all"
    assert assess_relevance(event, master).in_scope


# --------------------------------- SEBI enforcement and recovery actions

ENFORCEMENT = [
    ("Notice of attachment dated October 13,2026 issued against Solomon Y "
     "under RC No. 7706 of 2024", "effective"),
    ("Prohibitory Order no. 1575/2026 issued against Venkatachari Suresh in "
     "the matter of Securekloud Technologies Ltd", "effective"),
    ("Notice of Demand under Recovery Certificate number 9303 of 2026 dated "
     "October 13, 2026", "announced"),
    ("Release Order dated October 15, 2026 for RC 8924 of 2025 issued against "
     "Yuvika Tradewing LLP", "repealed"),
    ("Release of attachment on immovable property under RC No. 3965 of 2021",
     "repealed"),
    ("Completion of Recovery Certificate No. 3965 of 2021", "expired"),
    ("Confirmatory order in the matter of Rajesh Exports Limited", "adopted"),
]


@pytest.mark.parametrize("title,stage", ENFORCEMENT)
def test_an_enforcement_proceeding_is_classified_with_its_stage(title, stage):
    """A notice of demand, an attachment and a release are three different
    facts about whether a constraint is in force."""
    event = event_for(title)
    assert event.event_type == "securities_enforcement_action", title
    assert event.frame.policy_status == stage, title


def test_a_release_outranks_the_certificate_vocabulary_that_imposes_one():
    """"Release Order ... for RC 8924 of 2025" contains the same recovery
    certificate wording as an attachment. Read in the wrong order it reports a
    lifted constraint as an imposed one."""
    event = event_for("Release Order dated October 15, 2026 for RC 8924 of "
                      "2025 issued against Yuvika Tradewing LLP")
    assert event.frame.policy_status == "repealed"


def test_an_enforcement_action_assigns_no_direction():
    """Most of these name individuals, not issuers. An attachment against a
    promoter is not a loss to the company, and only a resolved target role
    could say otherwise."""
    from seraph.news.estimation import direction_of
    event = event_for(ENFORCEMENT[0][0])
    assert direction_of(event) == "ambiguous"


def test_enforcement_is_not_absorbed_by_the_generic_regulatory_rule():
    """These notices carry "order" and sometimes "penalty", so the broader
    pattern would absorb them and lose the recovery stage."""
    event = event_for("Prohibitory Order no. 1555 of 2026 in the matter of "
                      "HBN Dairies & Allied Limited under Recovery "
                      "Certificate No. 1234 of 2025")
    assert event.event_type == "securities_enforcement_action"


def test_an_ordinary_enforcement_action_is_still_a_regulatory_action():
    """The new rule must not swallow the class it was ordered in front of."""
    event = event_for("Reserve Bank of India imposes penalty on a "
                      "co-operative bank for non-compliance")
    assert event.event_type == "regulatory_action"


# ------------------------------------- a mode of transport is not an event

@pytest.mark.parametrize("title,is_disruption", [
    # The defect: a US passenger-rail rulemaking, classified as a logistics
    # disruption because the rule keyed on the bare word "rail".
    ("Advance Traveler Information for Rail", False),
    ("Certain Freight Rail Couplers and Parts Thereof From India", False),
    ("Notice of Public Meeting; Pacific Fishery Management Council", False),
    ("Port of Mumbai reports severe congestion", True),
    ("Shipping delays at Mundra port after cyclone", True),
    # Not "Rail freight suspended ...": "suspended" is matched by the
    # production_halt rule, which is tested first, and on one invented
    # sentence there is no evidence for reordering two legitimate readings.
    # These use vocabulary only the logistics rule claims.
    ("Rail freight diverted after derailment on the eastern corridor", True),
    ("Container backlog strands cargo at JNPT terminal", True),
])
def test_a_transport_noun_needs_disruption_vocabulary(title, is_disruption):
    event = event_for(title)
    if is_disruption:
        assert event.event_type == "logistics_disruption", title
    else:
        assert event.event_type != "logistics_disruption", title
