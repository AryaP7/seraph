"""What a measure covers, and what it carves out.

An exposure walk matches an event to an edge on `products`, which treats the
document as if its scope were the whole product family. Trade instruments
almost never are: they cover a defined article, exclude named variants, and
sometimes exempt named producers.

Getting this wrong is **directional**, not merely imprecise — a missed
exclusion turns "this does not apply to you" into an adverse signal.

What is extractable from a title is narrow, and the module says so rather
than hiding it: silence about scope is reported as `unknown`, never as "no
exclusions".
"""
from __future__ import annotations

import pytest

from seraph.news.estimation import estimate_impacts
from seraph.news.extraction import extract_events
from seraph.news.model import Story, Timing
from seraph.news.registry import load_master_data
from seraph.news.scope import applies_to_product, scope_of

SEEN = "2026-10-18T09:00:00+05:30"


def impacts_for(title: str):
    master, _ = load_master_data()
    story = Story(story_id="s", source_id="x", observation_id="o", title=title,
                  url="https://x.invalid/1", body=None,
                  timing=Timing(first_seen_at=SEEN), syndication_group="g")
    event = list(extract_events([story], master))[0].event
    return estimate_impacts(event, master)


# ------------------------------------------------- reading what is there

def test_an_exclusion_is_detected():
    scope = scope_of("Certain Corrosion-Resistant Steel Products From India: "
                     "Final Results, excluding products with an aluminium coating")
    assert scope.has_exclusions
    assert scope.determined
    assert scope.spans


def test_an_explicit_scope_section_is_detected():
    scope = scope_of("Scope of the Order: the covered merchandise is certain "
                     "paper shopping bags")
    assert scope.has_explicit_coverage
    assert scope.determined


def test_a_named_party_exemption_is_detected():
    scope = scope_of("Final Results; certain excluded producers are not "
                     "subject to the order")
    assert scope.exempts_named_parties


# ----------------------------------------- silence is not "no exclusions"

def test_an_undetermined_scope_says_so_rather_than_claiming_none():
    """The distinction that matters. A title that says nothing about scope
    has not told us there are no carve-outs."""
    scope = scope_of("Chromium Trioxide From India: Antidumping Duty Order")
    assert scope.determined is False
    assert scope.has_exclusions is False
    assert "NOT established" in scope.limitation
    assert "may therefore include articles the measure does not cover" in scope.limitation


def test_empty_text_is_undetermined_not_clean():
    assert scope_of("").determined is False
    assert scope_of("").limitation


# ---------------------------------------------------- the false friends

@pytest.mark.parametrize("headline", [
    # Both appear verbatim in this corpus and neither is an exclusion.
    "Removal of Exclusively listed companies of De-recognized Stock Exchanges",
    "Fisheries of the Exclusive Economic Zone Off Alaska; Reallocation",
])
def test_the_word_exclusive_is_not_an_exclusion(headline):
    """`exclusive` is deliberately absent from the pattern: these two phrases
    are in the received corpus and matching them would invent a carve-out."""
    assert scope_of(headline).has_exclusions is False


# ------------------------------------------- it limits the claim downstream

def test_an_undetermined_scope_attaches_a_limitation_to_the_impact():
    found = impacts_for("Chromium Trioxide From India: Antidumping Duty Order")
    assert found
    assert any("product scope was NOT established" in limit
               for limit in found[0].limitations)


def test_a_detected_carve_out_lowers_confidence():
    """A carve-out we detected but could not parse must not leave a confident
    direction standing."""
    plain = impacts_for("Chromium Trioxide From India: Antidumping Duty Order")
    carved = impacts_for("Chromium Trioxide From India: Antidumping Duty "
                         "Order, excluding material with a specified coating")
    assert plain and carved
    assert plain[0].evidence_confidence == "medium"
    assert carved[0].evidence_confidence == "low"


def test_a_carve_out_does_not_silently_drop_the_match():
    """Requiring full scope before any inference would silently drop every
    title-only document, which is most of this corpus. The match stands and
    carries its limitation.

    The carve-out here names an article the relationship is not about
    ("material with a specified coating" is not the edge's product), so it
    caps confidence and is reported, but it does not suppress — only an
    exclusion that covers the route may do that.
    """
    carved = impacts_for("Chromium Trioxide From India: Antidumping Duty "
                         "Order, excluding material with a specified coating")
    assert carved, "the match was dropped instead of limited"
    assert any("carves out" in limit or "EXCLUDES" in limit
               for limit in carved[0].limitations)
    assert carved[0].evidence_confidence == "low"


def test_applies_to_product_never_claims_a_scope_determination():
    scope = scope_of("Chromium Trioxide From India: Antidumping Duty Order")
    verdict = applies_to_product(scope, product_matched=True)
    assert verdict["matched"] is True
    assert verdict["scope_determined"] is False
    assert "not a scope determination" in verdict["note"]


def test_a_clean_explicit_scope_permits_a_higher_ceiling():
    scope = scope_of("Scope of the Order: the covered merchandise is certain "
                     "paper shopping bags")
    assert applies_to_product(scope, True)["confidence_ceiling"] == "medium"
