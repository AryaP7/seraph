"""SCEN01 / PORT04 — saved scenarios and the event-to-position trail.

SCEN01: a scenario is reproducible or it is a slider. Baseline identity,
versioned assumptions with units, reviewer history, and a comparison that
refuses to pretend two different baselines are comparable.

PORT04: "Why does this affect me?" — every hop inspectable, each holding
counted once, unknown magnitudes kept out of the arithmetic, and the whole
thing reconciling to the portfolio total.
"""
from __future__ import annotations

import sqlite3

import pytest

from seraph.decision_support.exposure_trail import (
    explain_exposure,
    shared_dependencies,
)
from seraph.decision_support.scenarios import (
    Assumption,
    Baseline,
    ScenarioStore,
    baseline_from_point,
)
from seraph.identity import AuthorizationError, IdentityRegistry
from seraph.news.extraction import extract
from seraph.news.model import Asset, Entity, ExposureEdge, Place, Story
from seraph.news.registry import MasterData
from seraph.product_types import SourceRef, Timing

SEEN = "2026-01-02T11:40:00+05:30"


def cite(ref="ref:annual-report-2025-segment-note"):
    return (SourceRef(source_id="curated", reference=ref),)


@pytest.fixture
def desk(tmp_path):
    registry = IdentityRegistry(tmp_path / "identity.sqlite")
    store = ScenarioStore(tmp_path / "scenarios.sqlite", registry)
    registry.add_organisation("org_a", "Alpha", "institution")
    registry.add_organisation("org_b", "Beta", "institution")
    registry.add_organisation("org_home", "Household", "retail_household")
    people = {}
    for key, sub, org, role in [("alpha", "s1", "org_a", "institutional"),
                                ("alpha2", "s2", "org_a", "institutional"),
                                ("beta", "s3", "org_b", "institutional"),
                                ("retail", "s4", "org_home", "retail")]:
        user = registry.upsert_user(provider_subject=sub, issuer="https://idp.test")
        registry.add_membership(user.user_id, org)
        registry.grant(user.user_id, org, role, granted_by="admin")
        people[key] = registry.resolve(registry.open_session(user.user_id).session_id)
    return registry, store, people


POINT = {
    "run_id": "run_a", "date": "2026-01-02",
    "composite": {"weights_artefact_id": "w" * 64, "csrs": 0.4},
    "reconciled": {"x_hat": [0.4, 0.5, 0.5]},
}

ASSUMPTIONS = [
    Assumption(key="shock_magnitude", value=0.1, unit="ecdf_rank",
               justification="one tenth of the rank distribution, as a probe"),
    Assumption(key="horizon", value=5, unit="sessions",
               justification="one trading week"),
]


# ------------------------------------------------------------- SCEN01


def test_a_saved_scenario_pins_its_baseline(desk):
    _, store, people = desk
    baseline = baseline_from_point(POINT)
    saved = store.save(people["alpha"], name="RMT probe", kind="rank_shock",
                       baseline=baseline, steps=[{"pillar": "rmt", "magnitude": 0.1}],
                       assumptions=ASSUMPTIONS)
    assert saved["baseline"]["run_id"] == "run_a"
    assert saved["baseline"]["artefact_id"] == baseline.artefact_id
    assert len(saved["baseline"]["reconciled_hash"]) == 64


def test_the_same_baseline_inputs_give_the_same_artefact_id():
    assert baseline_from_point(POINT).artefact_id == \
        baseline_from_point(dict(POINT)).artefact_id
    moved = dict(POINT, date="2026-01-03")
    assert baseline_from_point(moved).artefact_id != \
        baseline_from_point(POINT).artefact_id


def test_a_rank_shock_says_what_it_is_not(desk):
    _, store, people = desk
    saved = store.save(people["alpha"], name="probe", kind="rank_shock",
                       baseline=baseline_from_point(POINT), steps=[],
                       assumptions=ASSUMPTIONS)
    assert "NOT a 10% price move" in saved["semantics"]


def test_an_economic_scenario_is_refused_rather_than_approximated(desk):
    _, store, people = desk
    with pytest.raises(ValueError, match="propagation and portfolio-valuation model"):
        store.save(people["alpha"], name="rate shock", kind="economic",
                   baseline=baseline_from_point(POINT), steps=[],
                   assumptions=ASSUMPTIONS)


def test_an_assumption_needs_a_unit_and_a_justification():
    with pytest.raises(ValueError, match="needs a unit"):
        Assumption(key="x", value=1, unit="  ", justification="because")
    with pytest.raises(ValueError, match="needs a justification"):
        Assumption(key="x", value=1, unit="pct", justification="")


def test_a_retail_user_cannot_save_a_scenario(desk):
    _, store, people = desk
    with pytest.raises(AuthorizationError, match="institutional/regulator"):
        store.save(people["retail"], name="x", kind="rank_shock",
                   baseline=baseline_from_point(POINT), steps=[],
                   assumptions=ASSUMPTIONS)


def test_identical_inputs_reuse_the_recorded_run(desk):
    _, store, people = desk
    saved = store.save(people["alpha"], name="probe", kind="rank_shock",
                       baseline=baseline_from_point(POINT), steps=[],
                       assumptions=ASSUMPTIONS)
    first = store.record_run(people["alpha"], saved["scenario_id"],
                             results=[{"csrs": 0.44}], inputs={"magnitude": 0.1})
    again = store.record_run(people["alpha"], saved["scenario_id"],
                             results=[{"csrs": 0.44}], inputs={"magnitude": 0.1})
    assert first["reused"] is False and again["reused"] is True
    assert again["results"] == first["results"]
    assert len(store.runs(people["alpha"], saved["scenario_id"])) == 1


def test_revising_assumptions_makes_a_later_run_a_different_record(desk):
    _, store, people = desk
    saved = store.save(people["alpha"], name="probe", kind="rank_shock",
                       baseline=baseline_from_point(POINT), steps=[],
                       assumptions=ASSUMPTIONS)
    first = store.record_run(people["alpha"], saved["scenario_id"],
                             results=[{"csrs": 0.44}], inputs={"magnitude": 0.1})
    store.revise_assumptions(people["alpha"], saved["scenario_id"], [
        Assumption(key="shock_magnitude", value=0.2, unit="ecdf_rank",
                   justification="doubled probe")])
    second = store.record_run(people["alpha"], saved["scenario_id"],
                              results=[{"csrs": 0.48}], inputs={"magnitude": 0.1})
    assert second["reused"] is False
    assert second["inputs_hash"] != first["inputs_hash"], \
        "the assumption version is part of what makes a run reproducible"
    assert store.scenario(people["alpha"], saved["scenario_id"])[
        "assumption_version"] == 2


def test_a_scenario_run_is_a_record_not_a_draft(desk):
    _, store, people = desk
    saved = store.save(people["alpha"], name="probe", kind="rank_shock",
                       baseline=baseline_from_point(POINT), steps=[],
                       assumptions=ASSUMPTIONS)
    store.record_run(people["alpha"], saved["scenario_id"], results=[],
                     inputs={"magnitude": 0.1})
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as db:
            db.execute("UPDATE scenario_runs SET results='[]'")


def test_reviewer_history_is_kept(desk):
    _, store, people = desk
    saved = store.save(people["alpha"], name="probe", kind="rank_shock",
                       baseline=baseline_from_point(POINT), steps=[],
                       assumptions=ASSUMPTIONS)
    store.review(people["alpha2"], saved["scenario_id"],
                 verdict="changes_requested", comment="state the horizon")
    store.review(people["alpha2"], saved["scenario_id"], verdict="approved")
    reviews = store.scenario(people["alpha"], saved["scenario_id"])["reviews"]
    assert [r["verdict"] for r in reviews] == ["changes_requested", "approved"]
    assert reviews[0]["reviewer"] == people["alpha2"].user_id


def test_comparing_across_different_baselines_is_refused_not_fudged(desk):
    _, store, people = desk
    a = store.save(people["alpha"], name="a", kind="rank_shock",
                   baseline=baseline_from_point(POINT), steps=[],
                   assumptions=ASSUMPTIONS)
    b = store.save(people["alpha"], name="b", kind="rank_shock",
                   baseline=baseline_from_point(dict(POINT, date="2026-01-03")),
                   steps=[], assumptions=ASSUMPTIONS)
    comparison = store.compare(people["alpha"], a["scenario_id"], b["scenario_id"])
    assert comparison["comparable"] is False
    assert "not directly comparable" in comparison["note"]


def test_comparison_names_the_assumptions_that_differ(desk):
    _, store, people = desk
    baseline = baseline_from_point(POINT)
    a = store.save(people["alpha"], name="a", kind="rank_shock", baseline=baseline,
                   steps=[], assumptions=ASSUMPTIONS)
    b = store.save(people["alpha"], name="b", kind="rank_shock", baseline=baseline,
                   steps=[], assumptions=[
                       ASSUMPTIONS[0],
                       Assumption(key="horizon", value=20, unit="sessions",
                                  justification="a month")])
    comparison = store.compare(people["alpha"], a["scenario_id"], b["scenario_id"])
    assert comparison["comparable"] is True
    changed = {d["key"] for d in comparison["assumption_differences"]}
    assert changed == {"horizon"}


def test_another_institution_cannot_read_a_scenario(desk):
    _, store, people = desk
    saved = store.save(people["alpha"], name="probe", kind="rank_shock",
                       baseline=baseline_from_point(POINT), steps=[],
                       assumptions=ASSUMPTIONS)
    assert store.scenarios(people["beta"]) == []
    with pytest.raises(AuthorizationError):
        store.scenario(people["beta"], saved["scenario_id"])


def test_a_colleague_in_the_same_organisation_can_read_it(desk):
    _, store, people = desk
    saved = store.save(people["alpha"], name="probe", kind="rank_shock",
                       baseline=baseline_from_point(POINT), steps=[],
                       assumptions=ASSUMPTIONS)
    assert store.scenario(people["alpha2"], saved["scenario_id"])["name"] == "probe"


# ------------------------------------------------------------- PORT04


@pytest.fixture
def world():
    master = MasterData()
    master.add_place(Place(place_id="in_od", name="Odisha", kind="state"))
    master.add_entity(Entity(entity_id="tata_steel", name="Tata Steel",
                             kind="issuer", symbol="TATASTEEL", sector="steel"))
    master.add_entity(Entity(entity_id="maruti", name="Maruti Suzuki",
                             kind="issuer", symbol="MARUTI", sector="auto"))
    master.add_entity(Entity(entity_id="infy", name="Infosys", kind="issuer",
                             symbol="INFY", sector="it"))
    master.add_asset(Asset(asset_id="kalinganagar", name="Kalinganagar",
                           kind="plant", place_id="in_od",
                           operator_entity_id="tata_steel"))
    master.add_edge(ExposureEdge(edge_id="supply", from_id="tata_steel",
                                 to_id="maruti", mechanism="supplier",
                                 confidence="medium", evidence=cite()))
    story = Story(story_id="s1", source_id="wire", observation_id="o1",
                  title="Tata Steel halts output after fire at Kalinganagar",
                  url="https://example.test/s1",
                  timing=Timing(first_seen_at=SEEN,
                                published_at="2026-01-02T09:00:00+05:30"),
                  syndication_group="g1")
    event = extract([story], master).event
    return master, event, {story.story_id: story}


HOLDINGS = [
    {"symbol": "TATASTEEL", "value": 100000.0, "sector": "steel"},
    {"symbol": "MARUTI", "value": 50000.0, "sector": "auto"},
    {"symbol": "INFY", "value": 25000.0, "sector": "it"},
]


def test_the_trail_runs_from_article_to_position(world):
    master, event, stories = world
    result = explain_exposure(event, master, HOLDINGS, stories_by_id=stories)
    link = next(l for l in result["links"] if l["symbol"] == "TATASTEEL")
    kinds = [h["kind"] for h in link["trail"]]
    assert kinds[0] == "story" and kinds[-1] == "holding"
    assert "event" in kinds
    assert link["trail"][0]["url"] == "https://example.test/s1"
    assert link["direct"] is True


def test_an_indirect_link_shows_the_relationship_and_its_evidence(world):
    master, event, stories = world
    result = explain_exposure(event, master, HOLDINGS, stories_by_id=stories)
    link = next(l for l in result["links"] if l["symbol"] == "MARUTI")
    assert link["direct"] is False and link["path"] == ["supply"]
    relationship = next(h for h in link["trail"] if h["kind"] == "relationship")
    assert relationship["mechanism"] == "supplier"
    assert relationship["evidence"] == ["ref:annual-report-2025-segment-note"]
    assert relationship["confidence"] == "medium"


def test_an_unconnected_holding_is_not_linked(world):
    master, event, stories = world
    result = explain_exposure(event, master, HOLDINGS, stories_by_id=stories)
    assert "INFY" not in [l["symbol"] for l in result["links"]]
    assert "INFY" in result["coverage"]["uncovered"]


def test_every_holding_is_counted_once_and_the_total_reconciles(world):
    master, event, stories = world
    result = explain_exposure(event, master, HOLDINGS, stories_by_id=stories)
    reconciliation = result["reconciliation"]
    assert reconciliation["portfolio_total"] == 175000.0
    assert reconciliation["linked_value"] == 150000.0
    assert reconciliation["unlinked_value"] == 25000.0
    assert (reconciliation["linked_value"] + reconciliation["unlinked_value"]
            == reconciliation["portfolio_total"])
    assert len({l["symbol"] for l in result["links"]}) == len(result["links"])


def test_a_holding_reachable_twice_still_appears_once(world):
    master, event, stories = world
    # A second documented route to the same holding.
    master.add_edge(ExposureEdge(edge_id="logistics", from_id="tata_steel",
                                 to_id="maruti", mechanism="logistics",
                                 confidence="high", evidence=cite("ref:port-filing")))
    result = explain_exposure(event, master, HOLDINGS, stories_by_id=stories)
    maruti = [l for l in result["links"] if l["symbol"] == "MARUTI"]
    assert len(maruti) == 1
    assert result["reconciliation"]["linked_value"] == 150000.0, \
        "two routes must not double the exposed value"


def test_an_unsized_relationship_is_reported_not_counted_as_a_number(world):
    master, event, stories = world
    result = explain_exposure(event, master, HOLDINGS, stories_by_id=stories)
    link = next(l for l in result["links"] if l["symbol"] == "MARUTI")
    assert link["exposure_magnitude"] is None
    assert result["reconciliation"]["linked_but_unsized_value"] == 150000.0
    assert any("not the same as small" in l for l in link["limitations"])


def test_the_trail_does_not_claim_to_be_a_loss_estimate(world):
    master, event, stories = world
    result = explain_exposure(event, master, HOLDINGS, stories_by_id=stories)
    assert "does not estimate what the position will be worth" in \
        result["not_a_loss_estimate"]


def test_syndicated_copies_are_summarised_not_listed_ten_times(world):
    master, _, _ = world
    copies = [Story(story_id=f"s{i}", source_id=f"o{i}", observation_id=f"ob{i}",
                    title="Tata Steel halts output after fire at Kalinganagar",
                    url=f"u{i}", timing=Timing(first_seen_at=SEEN),
                    syndication_group="g1") for i in range(6)]
    event = extract(copies, master).event
    result = explain_exposure(event, master, HOLDINGS,
                              stories_by_id={s.story_id: s for s in copies})
    trail = next(l for l in result["links"] if l["symbol"] == "TATASTEEL")["trail"]
    story_hops = [h for h in trail if h["kind"] == "story"]
    assert len(story_hops) == 4 and story_hops[-1]["ref_id"] == "+more"
    assert "3 more report(s)" in story_hops[-1]["label"]


def test_a_subsidiary_event_reaches_the_listed_parent(world):
    master, _, _ = world
    master.add_entity(Entity(entity_id="ts_long", name="Tata Steel Long Products",
                             kind="subsidiary", parent_id="tata_steel"))
    master.add_edge(ExposureEdge(edge_id="own", from_id="ts_long",
                                 to_id="tata_steel", mechanism="ownership",
                                 confidence="high", evidence=cite("ref:filing")))
    story = Story(story_id="s9", source_id="w", observation_id="o9",
                  title="Tata Steel Long Products halts output after fire",
                  url="u", timing=Timing(first_seen_at=SEEN))
    event = extract([story], master).event
    result = explain_exposure(event, master, HOLDINGS,
                              stories_by_id={story.story_id: story})
    assert "TATASTEEL" in [l["symbol"] for l in result["links"]]


# ------------------------------------------- shared-dependency blind spots


def test_shared_dependencies_need_two_holdings_and_real_evidence(world):
    master, _, _ = world
    master.add_entity(Entity(entity_id="port_paradip", name="Paradip Port",
                             kind="operator"))
    for symbol_entity in ("tata_steel", "maruti"):
        master.add_edge(ExposureEdge(
            edge_id=f"{symbol_entity}_port", from_id=symbol_entity,
            to_id="port_paradip", mechanism="logistics", confidence="medium",
            evidence=cite("ref:port-traffic-statement")))
    shared = shared_dependencies(master, HOLDINGS)
    assert shared and shared[0]["dependency"] == "port_paradip"
    assert shared[0]["holdings"] == ["MARUTI", "TATASTEEL"]
    assert shared[0]["combined_value"] == 150000.0
    assert shared[0]["evidence"] == ["ref:port-traffic-statement"]
    assert "not an inferred one" in shared[0]["note"]


def test_a_dependency_with_only_one_holding_is_not_a_blind_spot(world):
    master, _, _ = world
    assert shared_dependencies(master, HOLDINGS) == []
