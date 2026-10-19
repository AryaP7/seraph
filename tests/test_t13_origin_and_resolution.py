"""T11/T13 — what the real RBI corpus exposed when the globe was first wired.

Two defects, both found by running the adapter against the 30 stories actually
in the store rather than against a fixture:

**D1 — a substring match attributed an event to the wrong body.** The mention
"India" resolved to the ENTITY `reserve_bank_of_india`, because the partial
rule accepted any substring and "india" sits inside "reserve bank of india".
Partial matching is now on whole tokens with a two-token floor.

**D2 — a venue was recorded as an impact.** "Mumbai", named in the title of a
speech, was marked an affected place. A venue, a dateline and a registered
address are indistinguishable to a name matcher, so the role is no longer
claimed: located records are `mentions` until something evidences more.

And the capability those two fixes made safe: an event's **origin** comes from
the curated issuing location of its SOURCE, with its own citation, rather than
from guessing at the prose.
"""
from __future__ import annotations

import pytest

from seraph.news.extraction import extract
from seraph.news.model import Entity, Place, Story, Timing
from seraph.news.registry import CurationError, MasterData, load_master_data


SEEN = "2026-10-17T09:00:00+05:30"


def story(title, body=None, *, story_id="s1", source_id="rbi"):
    return Story(story_id=story_id, source_id=source_id, observation_id="o1",
                 title=title, url="https://example.invalid/1", body=body,
                 timing=Timing(first_seen_at=SEEN, published_at=SEEN),
                 syndication_group="g1")


@pytest.fixture
def registry():
    data = MasterData()
    data.add_place(Place(place_id="in", name="India", kind="country",
                         iso_code="IND", lat=22.0, lon=79.0))
    data.add_place(Place(place_id="in_mh_mumbai", name="Mumbai", kind="city",
                         parent_id="in", lat=19.07283, lon=72.88261))
    data.add_entity(Entity(entity_id="reserve_bank_of_india",
                           name="Reserve Bank of India", kind="government_body",
                           aliases=("RBI", "Reserve Bank")))
    return data


# ------------------------------------------------------------------- D1


def test_a_single_common_token_does_not_capture_a_mention(registry):
    """The exact defect: 'India' must not resolve to the RBI entity."""
    assert registry.resolve("India").status == "unknown"


def test_a_two_token_run_still_matches(registry):
    result = registry.resolve("Reserve Bank")
    assert result.status == "resolved"
    assert result.entity_id == "reserve_bank_of_india"


def test_an_exact_alias_still_matches(registry):
    assert registry.resolve("RBI").entity_id == "reserve_bank_of_india"


def test_a_token_run_must_be_contiguous(registry):
    """'Reserve India' is not a run of words inside the registered name."""
    assert registry.resolve("Reserve India").status == "unknown"


def test_a_longer_mention_containing_the_name_matches(registry):
    assert registry.resolve("the Reserve Bank of India today").entity_id == \
        "reserve_bank_of_india"


def test_a_place_resolves_as_a_place_not_as_an_entity(registry):
    assert registry.resolve("India").status == "unknown"
    assert registry.resolve_place("India").entity_id == "in"


def test_place_resolution_abstains_when_ambiguous():
    data = MasterData()
    data.add_place(Place(place_id="a", name="Springfield", kind="city"))
    data.add_place(Place(place_id="b", name="Springfield", kind="city"))
    result = data.resolve_place("Springfield")
    assert result.status == "ambiguous"
    assert result.candidates == ("a", "b")


# ------------------------------------------------------------------- D2


def test_a_named_location_is_a_mention_not_an_impact(registry):
    """The exact defect: a speech venue was marked affected."""
    result = extract([story("Keynote address delivered in Mumbai")], registry)
    assert ("in_mh_mumbai", "mentioned") in result.event.locations
    assert "in_mh_mumbai" not in result.event.affected


def test_issuing_authority_is_an_actor_not_automatically_affected(registry):
    result = extract([story("Reserve Bank of India amends directions")],
                     registry)
    assert "reserve_bank_of_india" not in result.event.affected
    assert "reserve_bank_of_india" in result.event.actors


def test_the_mention_keeps_its_evidence_span(registry):
    result = extract([story("Keynote address delivered in Mumbai")], registry)
    fields = {span.field: span.text for span in result.event.evidence}
    # The span is the mention as the text wrote it, trailing punctuation and
    # all — it points at the source, so it must quote the source.
    assert (fields.get("affected_place") or "").startswith("Mumbai")


def test_a_location_mentioned_twice_is_recorded_once(registry):
    result = extract([story("Mumbai update", "Issued at Mumbai.")],
                     registry)
    assert [node for node, _ in result.event.locations] == ["in_mh_mumbai"]


# ------------------------------------------------- origin from the source


def test_a_source_issuing_location_is_curated_with_a_citation(registry):
    registry.add_source_place(source_id="rbi", place_id="in_mh_mumbai",
                              basis="issuing_office",
                              source="https://rbi.org.in/x.pdf")
    record = registry.origin_of("rbi")
    assert record["place_id"] == "in_mh_mumbai"
    assert record["basis"] == "issuing_office"
    assert record["source"].startswith("https://")


def test_an_unregistered_source_has_no_origin(registry):
    assert registry.origin_of("unknown_source") is None


def test_an_issuing_place_must_be_a_curated_place(registry):
    with pytest.raises(CurationError, match="not registered"):
        registry.add_source_place(source_id="x", place_id="atlantis",
                                  basis="jurisdiction", source="https://x/")


def test_the_basis_must_distinguish_an_office_from_a_territory(registry):
    with pytest.raises(CurationError, match="different claims"):
        registry.add_source_place(source_id="x", place_id="in",
                                  basis="somewhere", source="https://x/")


def test_the_shipped_rbi_sources_have_an_issuing_office():
    """The curated rows that make the real corpus reach the globe."""
    data, _ = load_master_data()
    for source_id in ("rbi_notifications", "rbi_press_releases",
                      "rbi_speeches"):
        record = data.origin_of(source_id)
        assert record is not None, source_id
        assert record["place_id"] == "in_mh_mumbai"
        assert record["basis"] == "issuing_office"
        assert "rbi.org.in" in record["source"]


def test_the_shipped_mumbai_coordinate_is_the_gazetteer_one():
    data, _ = load_master_data()
    mumbai = data.places["in_mh_mumbai"]
    assert (mumbai.lat, mumbai.lon) == (19.07283, 72.88261)
    assert mumbai.parent_id == "in_mh"
