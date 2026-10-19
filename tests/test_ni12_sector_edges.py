"""NI11/NI12 — the sector edges, and two defects the aluminium notices exposed.

The pilot's binding constraint was never the extractor: it was the exposure
registry. Four edges meant that of 32 recognised trade remedies, five reached
a sector. These tests pin the three edges curated from documents already in
the store (chemicals, aluminium, agriculture), and the two bugs that surfaced
while checking their output:

**A sunset review being scheduled is not a lapsed measure.** "Scheduling of
Full Five-Year Reviews" was classified `expired`, which asserts the duty no
longer applies. A five-year review is the proceeding that DECIDES whether an
order continues and is published while the order is in force, so the frame
said the opposite of the notice. This is the same failure as the earlier
"Postponement of Final Determination" bug: a notice that NAMES a stage read
as having REACHED it.

**A revocation is relief.** The direction rule gated every sign on
adopted/effective, so "Revocation of the Antidumping and Countervailing Duty
Orders" — the clearest favourable trade-remedy outcome there is — carried no
sign at all, the same as an opened investigation.

What is NOT claimed here: none of these edges is sized. A US proceeding
covering a product "From India" establishes that the import trade exists. It
is not a revenue share, not a company exposure and not a loss.
"""
from __future__ import annotations

import csv
import pathlib

import pytest

from seraph.news.estimation import direction_of, estimate_impacts
from seraph.news.extraction import extract_events
from seraph.news.model import Place, Story, Timing
from seraph.news.registry import MasterData, load_master_data

SEEN = "2026-10-17T09:00:00+05:30"
CURATED = pathlib.Path(__file__).resolve().parents[1] / "seraph/news/curated/exposure.csv"

NEW_EDGES = {
    "india_chemicals_us_trade_remedy": "sector:chemicals",
    "india_aluminium_us_trade_remedy": "sector:aluminium",
    "india_agriculture_us_trade_remedy": "sector:agriculture",
}


def story(title, body=None):
    return Story(story_id="s1", source_id="federal_register", observation_id="o1",
                 title=title, url="https://example.invalid/1", body=body,
                 timing=Timing(first_seen_at=SEEN, published_at=SEEN),
                 syndication_group="g1")


def event_for(title, body=None):
    data = MasterData()
    data.add_place(Place("in", "India", "country", iso_code="IND", lat=22.0, lon=79.0))
    data.add_place(Place("us", "United States", "country", iso_code="USA",
                         lat=39.76, lon=-98.5))
    results = list(extract_events([story(title, body)], data))
    assert results and results[0].event is not None, title
    return results[0].event


# ------------------------------------------------- the edges are real rows

@pytest.fixture(scope="module")
def curated_rows():
    with CURATED.open(newline="", encoding="utf-8") as handle:
        return {r["edge_id"]: r for r in csv.DictReader(
            line for line in handle if not line.lstrip().startswith("#"))
            if r.get("edge_id")}


@pytest.mark.parametrize("edge_id,target", sorted(NEW_EDGES.items()))
def test_edge_exists_and_targets_its_sector(curated_rows, edge_id, target):
    row = curated_rows[edge_id]
    assert row["from_id"] == "in"
    assert row["to_id"] == target
    assert row["mechanism"] == "export"
    assert row["target_role"] == "exporter"
    assert row["event_types"] == "trade_remedy_determination"


@pytest.mark.parametrize("edge_id", sorted(NEW_EDGES))
def test_edge_is_cited_to_a_first_party_document(curated_rows, edge_id):
    """An uncited relationship is an assertion. The loader refuses one."""
    ref = curated_rows[edge_id]["source_ref"]
    assert ref.startswith("https://www.federalregister.gov/documents/"), ref


@pytest.mark.parametrize("edge_id", sorted(NEW_EDGES))
def test_edge_is_unsized(curated_rows, edge_id):
    """A proceeding names no Indian volume, share or loss, so neither do we."""
    row = curated_rows[edge_id]
    assert row["magnitude"] == ""
    assert row["unit"] == ""


def test_the_registry_loads_every_edge_without_error():
    master, report = load_master_data()
    assert report.get("errors") == []
    assert NEW_EDGES.keys() <= set(master.edges)


# ---------------------------------------- products stay inside their sector

@pytest.mark.parametrize("title,expected,forbidden", [
    # Chromium trioxide is a metal-finishing CHEMICAL. An earlier version of
    # the steel edge matched it on the bare word "chromium" and duly reported
    # "adverse for the steel sector".
    ("Chromium Trioxide From India: Final Affirmative Determination of Sales "
     "at Less Than Fair Value", "sector:chemicals", "sector:steel"),
    # Graphite electrodes are a consumable INPUT to electric-arc steelmaking,
    # not a steel article, and not a chemical we claim either.
    ("Large Diameter Graphite Electrodes From India: Final Affirmative "
     "Determination of Sales at Less Than Fair Value", None, "sector:steel"),
    # Oil country tubular goods IS steel — pipe for wells.
    ("Oil Country Tubular Goods From India, South Korea, Turkey, Ukraine, and "
     "Vietnam; Determinations", "sector:steel", "sector:chemicals"),
    ("Common Alloy Aluminum Sheet From Bahrain, Brazil, Germany, India, and "
     "Turkey: Antidumping Duty Order", "sector:aluminium", "sector:steel"),
    ("Oleoresin Paprika From India: Antidumping Duty Order",
     "sector:agriculture", "sector:chemicals"),
])
def test_a_product_reaches_its_own_sector_and_no_other(title, expected, forbidden):
    master, _ = load_master_data()
    targets = {i.target_id for i in estimate_impacts(event_for(title), master)}
    if expected:
        assert expected in targets, f"{title!r} did not reach {expected}: {targets}"
    assert forbidden not in targets, (
        f"{title!r} leaked into {forbidden}: {targets}")


# ------------------------------------- a scheduled review is not a lapse

SCHEDULING = ("Common Alloy Aluminum Sheet From Bahrain, Brazil, Croatia, Egypt, "
              "Germany, India, Indonesia, Italy, Oman, Romania, Serbia, Slovenia, "
              "South Africa, Spain, Taiwan, and Turkey; Scheduling of Full "
              "Five-Year Reviews")


def test_scheduling_a_five_year_review_is_a_proceeding_not_an_expiry():
    """`expired` asserts the duty no longer applies. This notice says the
    opposite: the order is in force and its continuation is under review."""
    frame = event_for(SCHEDULING).frame
    assert frame.policy_status != "expired"
    assert frame.policy_status == "consultation"


def test_the_guard_survives_words_between_the_cue_and_the_review():
    """The Federal Register writes "Scheduling of FULL Five-Year Reviews". An
    adjacency-based guard missed it; this is the regression that caught it."""
    for filler in ("", "Full ", "Expedited ", "First Full "):
        title = f"Widgets From India; Scheduling of {filler}Five-Year Reviews"
        assert event_for(title).frame.policy_status == "consultation", filler


def test_an_explicit_lapse_is_still_expired():
    frame = event_for("Widgets From India: Antidumping Duty Order Expired").frame
    assert frame.policy_status == "expired"


def test_a_scheduled_review_carries_no_direction():
    event = event_for(SCHEDULING)
    assert direction_of(event, target_role="exporter") == "ambiguous"


# ------------------------------------------------- a revocation is relief

REVOCATION = ("Common Alloy Aluminum Sheet From India: Final Results of Changed "
              "Circumstances Reviews and Revocation of the Antidumping and "
              "Countervailing Duty Orders, in Part")


def test_a_revocation_is_favourable_for_the_exporter():
    event = event_for(REVOCATION)
    assert event.frame.policy_status == "repealed"
    assert direction_of(event, target_role="exporter") == "favourable"


def test_the_same_revocation_is_adverse_for_the_domestic_producer():
    """One sign for every target is the defect direction_of exists to avoid:
    removing a duty relieves the exporter and exposes the producer that was
    being protected."""
    assert direction_of(event_for(REVOCATION),
                        target_role="domestic_producer") == "adverse"


def test_a_revocation_reaches_the_sector_with_its_sign():
    master, _ = load_master_data()
    impacts = [i for i in estimate_impacts(event_for(REVOCATION), master)
               if i.target_id == "sector:aluminium"]
    assert impacts, "the revocation did not reach the aluminium sector"
    assert {i.direction for i in impacts} == {"favourable"}


def test_a_rescinded_administrative_review_is_not_a_revocation():
    """Rescinding a REVIEW discontinues the proceeding and leaves the existing
    duty in place. Reading it as a revocation would invent relief."""
    frame = event_for("Certain Frozen Warmwater Shrimp From India: Rescission of "
                      "Antidumping Duty Administrative Review, In Part; "
                      "2025-2026").frame
    assert frame.policy_status != "repealed"


def test_an_imposed_order_is_still_adverse_for_the_exporter():
    """The relief branch must not swallow the imposition case."""
    event = event_for("Oleoresin Paprika From India: Antidumping Duty Order and "
                      "Countervailing Duty Order")
    assert direction_of(event, target_role="exporter") == "adverse"
    assert direction_of(event, target_role="domestic_producer") == "favourable"


# ------------------------------------------- the second curation batch

BATCH_TWO = {
    "india_textiles_us_trade_remedy": "sector:textiles",
    "india_paper_us_trade_remedy": "sector:paper_packaging",
    "india_industrial_materials_us_trade_remedy": "sector:industrial_materials",
}


@pytest.mark.parametrize("edge_id,target", sorted(BATCH_TWO.items()))
def test_second_batch_edges_exist_cited_and_unsized(curated_rows, edge_id, target):
    row = curated_rows[edge_id]
    assert row["to_id"] == target
    assert row["from_id"] == "in" and row["target_role"] == "exporter"
    assert row["source_ref"].startswith("https://www.federalregister.gov/documents/")
    assert row["magnitude"] == "" and row["unit"] == ""


def test_graphite_electrodes_are_not_a_steel_article():
    """The subtle one, and a repeat offender. Graphite electrodes are a
    CONSUMABLE INPUT to electric-arc steelmaking. An earlier steel edge
    matched them and reported "adverse for the steel sector" — wrong sector
    AND wrong direction, since a duty on Indian electrode exports is adverse
    to the Indian electrode maker, not to Indian steelmakers who buy them."""
    master, _ = load_master_data()
    title = ("Large Diameter Graphite Electrodes From India: Final "
             "Affirmative Determination of Sales at Less Than Fair Value")
    targets = {i.target_id for i in estimate_impacts(event_for(title), master)}
    assert "sector:industrial_materials" in targets
    assert "sector:steel" not in targets, "the input/output confusion is back"


@pytest.mark.parametrize("title,expected,forbidden", [
    ("Fine Denier Polyester Staple Fiber From India: Final Results of "
     "Antidumping Duty Administrative Review",
     "sector:textiles", "sector:paper_packaging"),
    ("Certain Paper Shopping Bags From India: Final Affirmative "
     "Determination", "sector:paper_packaging", "sector:textiles"),
])
def test_second_batch_products_stay_in_their_sector(title, expected, forbidden):
    master, _ = load_master_data()
    targets = {i.target_id for i in estimate_impacts(event_for(title), master)}
    assert expected in targets, f"{title!r} did not reach {expected}"
    assert forbidden not in targets, f"{title!r} leaked into {forbidden}"


def test_registry_preserves_trade_edges_and_adds_cited_facility_routes():
    master, report = load_master_data()
    assert report.get("errors") == []
    assert len(master.edges) >= 10
    assert BATCH_TWO.keys() <= set(master.edges)
    station_edges = [edge for edge in master.edges.values() if edge.from_id.startswith('ntpc_')]
    assert len(station_edges) == 54
    assert all(edge.from_id in master.assets and edge.known_from
               and edge.evidence[0].reference == 'https://ntpc.co.in/power-generation/coal-stations'
               for edge in station_edges)
