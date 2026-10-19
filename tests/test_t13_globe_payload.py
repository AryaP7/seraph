"""T13 — a sourced event reaches the globe, or the globe says why it cannot.

Audit findings R07/R08: `build_news_payload()` ran against the real store and
nothing called it; the map drew a hardcoded fabricated dataset and the whole
payload carried one flat `news_status='FABRICATED PREVIEW'` string.

The properties pinned here are the ones that make a map trustworthy:

* one coordinate adapter, checked against known points, the antimeridian, the
  poles **and against the renderer's own JavaScript**;
* a node is placed by evidence or goes to the review queue — never to the
  operator's headquarters or a country centroid;
* precision survives: a facility, a city, a region and a country are drawn
  differently because they are different claims;
* layers do not blend, and the fabricated preview is a separate labelled
  layer that shares no identifier space with the evidenced ones;
* edge visibility is bounded, deterministic, and reports what it hid.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess

import pytest

from seraph.dashboard.globe_payload import (
    ADAPTER_VERSION,
    GEOMETRY_MAP_VERSION,
    GeometryResolver,
    build_globe_payload,
    node_detail,
    to_globe,
)

STATE_MESHES = ("Gujarat", "Odisha", "Tamil Nadu", "Telangana", "Maharashtra")
COUNTRY_MESHES = ("IND", "USA", "BEL", "CHN")


# ------------------------------------------------------- fixture registry


class _Place:
    def __init__(self, place_id, name, kind, *, lat=None, lon=None,
                 iso_code=None, parent_id=None):
        self.place_id, self.name, self.kind = place_id, name, kind
        self.lat, self.lon = lat, lon
        self.iso_code, self.parent_id = iso_code, parent_id


class _Asset:
    def __init__(self, asset_id, name, place_id, *, lat=None, lon=None):
        self.asset_id, self.name, self.place_id = asset_id, name, place_id
        self.lat, self.lon = lat, lon


class _Master:
    def __init__(self, places=(), assets=(), entity_places=None):
        self.places = {p.place_id: p for p in places}
        self.assets = {a.asset_id: a for a in assets}
        self._entity_places = entity_places or {}

    def place_of(self, target_id):
        if target_id in self.assets:
            return self.assets[target_id].place_id
        if target_id in self.places:
            return target_id
        return self._entity_places.get(target_id)


@pytest.fixture
def master():
    return _Master(
        places=[
            _Place("place:in", "India", "country", iso_code="IND",
                   lat=22.0, lon=79.0),
            _Place("place:us", "United States", "country", iso_code="USA",
                   lat=38.9, lon=-77.0),
            _Place("place:in-od", "Odisha", "state", parent_id="place:in",
                   lat=20.5, lon=85.0),
            _Place("place:in-mh", "Maharashtra", "state", parent_id="place:in"),
            _Place("place:in-mumbai", "Mumbai", "city",
                   parent_id="place:in-mh", lat=19.07, lon=72.88),
            _Place("place:nowhere", "Unlocated District", "district",
                   parent_id=None),
        ],
        assets=[
            _Asset("asset:plant-a", "Plant A", "place:in-od",
                   lat=22.26, lon=84.85),
            _Asset("asset:plant-b", "Plant B", "place:in-od"),
        ],
        entity_places={"entity:operator": "place:in-mumbai"})


def news_payload(*, regions=(), arcs=(), signals=(), assets=(),
                 coverage=None, injection=0):
    return dict(
        decision_ts="2026-10-17T10:00:00+05:30",
        source_coverage=coverage or dict(covered=3, total=3, uncovered=[],
                                         complete=True),
        injection_flags=injection,
        channel_note="news channel (F2), separate from CSRS",
        surfaces=dict(
            signals=dict(surface="signals", status="observed",
                         items=list(signals)),
            geography=dict(surface="geography", status="estimate",
                           regions=list(regions), arcs=list(arcs)),
            assets=dict(surface="assets", status="observed",
                        items=list(assets)),
            sector_stress=dict(surface="sector_stress",
                               news=dict(status="preview", rows=[]),
                               hawkes=dict(status="unavailable", rows=[]))))


def build(payload, master, **kw):
    kw.setdefault("state_meshes", STATE_MESHES)
    kw.setdefault("country_meshes", COUNTRY_MESHES)
    return build_globe_payload(payload, master, revision="r1",
                               as_of="2026-10-17T10:00:00+05:30", **kw)


# -------------------------------------------------- the coordinate adapter


def test_the_prime_meridian_at_the_equator():
    x, y, z = to_globe(0.0, 0.0)
    assert (round(x, 12), round(y, 12), round(z, 12)) == (1.0, 0.0, 0.0)


def test_the_north_pole_is_plus_y():
    x, y, z = to_globe(0.0, 90.0)
    assert round(y, 12) == 1.0
    assert abs(x) < 1e-12 and abs(z) < 1e-12


def test_the_south_pole_is_minus_y():
    _, y, _ = to_globe(137.0, -90.0)
    assert round(y, 12) == -1.0


def test_every_point_is_on_the_sphere():
    for lon in range(-180, 181, 17):
        for lat in range(-90, 91, 13):
            x, y, z = to_globe(lon, lat, 3.5)
            assert math.isclose(math.sqrt(x * x + y * y + z * z), 3.5,
                                rel_tol=1e-12)


def test_the_antimeridian_is_a_seam_in_the_data_not_the_sphere():
    """181E and 179W are the same meridian and must land on one point."""
    a = to_globe(181.0, 10.0)
    b = to_globe(-179.0, 10.0)
    assert all(math.isclose(p, q, abs_tol=1e-12) for p, q in zip(a, b))


def test_longitude_wraps_rather_than_being_rejected():
    assert all(math.isclose(p, q, abs_tol=1e-12)
               for p, q in zip(to_globe(540.0, 0.0), to_globe(180.0, 0.0)))


def test_an_impossible_latitude_is_refused():
    with pytest.raises(ValueError, match="outside"):
        to_globe(0.0, 91.0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_python_adapter_matches_the_renderers_javascript():
    """One conversion, two languages. They must agree to the last bit.

    Drift here would put the server's idea of a facility somewhere other than
    where the browser draws it, which no test of either side alone can catch.
    """
    script = """
    const D2R = Math.PI / 180;
    function toXYZ(lon, lat, r) {
      var p = (90 - lat) * D2R, t = (lon + 180) * D2R;
      return [-r*Math.sin(p)*Math.cos(t), r*Math.cos(p), r*Math.sin(p)*Math.sin(t)];
    }
    const pts = [[0,0],[72.88,19.07],[-77.03,38.9],[180,0],[-179,10],[85,20.5],
                 [4.35,50.85],[0,90],[0,-90]];
    console.log(JSON.stringify(pts.map(p => toXYZ(p[0], p[1], 1))));
    """
    out = subprocess.run(["node", "-e", script], capture_output=True,
                         text=True, check=True).stdout
    expected = json.loads(out)
    points = [(0, 0), (72.88, 19.07), (-77.03, 38.9), (180, 0), (-179, 10),
              (85, 20.5), (4.35, 50.85), (0, 90), (0, -90)]
    for (lon, lat), js in zip(points, expected):
        py = to_globe(lon, lat)
        assert all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(py, js)), (
            f"python and javascript disagree at {lon},{lat}: {py} vs {js}")


# ------------------------------------------------------ placing by evidence


def test_an_asset_with_a_coordinate_is_a_facility(master):
    placement = GeometryResolver(master, state_meshes=STATE_MESHES).resolve(
        "asset:plant-a")
    assert placement.location_precision == "facility"
    assert placement.coordinates == (84.85, 22.26)
    assert placement.describe()["marker"] == "pin"


def test_an_asset_without_a_coordinate_degrades_to_its_place(master):
    """And says so: it is drawn as a region, not as a false pinpoint."""
    placement = GeometryResolver(master, state_meshes=STATE_MESHES).resolve(
        "asset:plant-b")
    assert placement.location_precision == "region"
    assert placement.mesh_id == "india_state:Odisha"


def test_an_entity_is_located_only_by_what_the_registry_says(master):
    """The adapter asks `place_of`; it does not reason about entities itself."""
    placement = GeometryResolver(master, state_meshes=STATE_MESHES).resolve(
        "entity:operator")
    assert placement.coordinates == (72.88, 19.07)
    assert placement.location_precision == "city"


def test_the_real_registry_does_not_place_an_entity_at_all():
    """`MasterData.place_of` returns nothing for an entity, deliberately.

    A registered office is not an operating location. The adapter must not
    quietly supply the headquarters the registry refused to give it — the
    body goes to the review queue instead.
    """
    from seraph.news.model import Entity, Place
    from seraph.news.registry import MasterData

    registry = MasterData()
    registry.add_place(Place(place_id="in_mh_mumbai", name="Mumbai",
                             kind="city", lat=19.07, lon=72.88))
    registry.add_entity(Entity(entity_id="rbi", name="Reserve Bank of India",
                               kind="government_body"))
    resolver = GeometryResolver(registry, state_meshes=STATE_MESHES)
    assert resolver.resolve("rbi") is None
    assert resolver.resolve("in_mh_mumbai").coordinates == (72.88, 19.07)


def test_a_sector_is_never_a_point_on_the_earth(master):
    """Sector nodes belong to the sector panel, not to an invented coordinate."""
    assert GeometryResolver(master).resolve("sector:steel") is None


def test_a_country_resolves_to_the_renderers_own_ring(master):
    placement = GeometryResolver(master, country_meshes=COUNTRY_MESHES).resolve(
        "place:us")
    assert placement.mesh_id == "world_country:USA"
    assert placement.location_precision == "country"
    assert placement.describe()["marker"] == "outline"


def test_a_state_without_a_centroid_still_gets_its_ring(master):
    placement = GeometryResolver(master, state_meshes=STATE_MESHES).resolve(
        "place:in-mh")
    assert placement.mesh_id == "india_state:Maharashtra"
    assert "ring only" in placement.source_record


def test_an_unplaceable_record_resolves_to_nothing(master):
    assert GeometryResolver(master).resolve("place:nowhere") is None
    assert GeometryResolver(master).resolve("entity:unknown") is None


def test_an_unplaceable_record_goes_to_the_review_queue_not_the_map(master):
    payload = build(news_payload(regions=[dict(
        place_id="place:nowhere", name="Unlocated District",
        severity="major", events=["ev1"])]), master)
    assert payload["nodes"] == []
    assert payload["review_queue"]["count"] == 1
    assert payload["unresolved"][0]["node_id"] == "place:nowhere"
    assert "somewhere plausible" in payload["unresolved"][0]["reason"]


def test_a_domestic_incident_locates_the_site_not_the_operator(master):
    """Browser acceptance 3, as a unit property."""
    payload = build(news_payload(assets=[dict(
        asset_id="asset:plant-a", name="Plant A", events=["ev1"])]), master)
    node = payload["nodes"][0]
    assert node["coordinates"] == [84.85, 22.26]
    assert node["location_precision"] == "facility"
    assert node["placed_from"] == "asset:asset:plant-a"


# ------------------------------------------------------- layers and edges


def test_origins_and_affected_are_separate_layers(master):
    payload = build(news_payload(
        signals=[dict(event_id="ev1", headline="H", event_type="tariff",
                      lifecycle="active", origins=["place:us"], sources=["s1"])],
        regions=[dict(place_id="place:in-od", name="Odisha",
                      severity="major", events=["ev1"])]), master)
    assert payload["layers"]["origins"]["node_ids"] == ["place:us"]
    assert payload["layers"]["affected"]["node_ids"] == ["place:in-od"]
    assert payload["layers"]["origins"]["legend"] != \
        payload["layers"]["affected"]["legend"]


def test_a_foreign_origin_reaches_indian_exposure_over_an_evidenced_path(master):
    """Browser acceptance 2, as a unit property."""
    payload = build(news_payload(
        signals=[dict(event_id="ev1", headline="Section 301 review",
                      event_type="tariff", lifecycle="active",
                      origins=["place:us"], sources=["s1"])],
        regions=[dict(place_id="place:in-od", name="Odisha",
                      severity="major", events=["ev1"])],
        arcs=[dict(edge_id="edge:1", from_id="place:us", to_id="place:in-od",
                   mechanism="trade_policy", confidence="high",
                   evidence=["ref:ustr-301"], event_id="ev1",
                   direction="negative", magnitude=None, unit=None)]), master)
    assert [e["edge_id"] for e in payload["edges"]] == ["edge:1"]
    edge = payload["edges"][0]
    assert edge["from_node"] == "place:us" and edge["to_node"] == "place:in-od"
    assert edge["evidence_ids"] == ["ref:ustr-301"]
    detail = node_detail(payload, "place:in-od", role="institutional")
    assert detail["mechanism_path"][0]["edge_id"] == "edge:1"
    assert "open_scenario" in detail["allowed_actions"]


def test_an_arc_whose_endpoint_cannot_be_placed_is_not_drawn(master):
    payload = build(news_payload(arcs=[dict(
        edge_id="edge:1", from_id="place:nowhere", to_id="place:in-od",
        mechanism="trade_policy", confidence="high", evidence=["ref:x"],
        event_id="ev1")]), master)
    assert payload["edges"] == []
    assert payload["review_queue"]["count"] >= 1


def test_edge_visibility_is_bounded_and_reports_what_it_hid(master):
    arcs = [dict(edge_id=f"edge:{i:02d}", from_id="place:us",
                 to_id="place:in-od", mechanism="trade_policy",
                 confidence="low", evidence=["ref:x"], event_id="ev1")
            for i in range(10)]
    payload = build(news_payload(arcs=arcs), master, max_edges=4)
    assert len(payload["edges"]) == 4
    assert payload["hidden_edges"]["count"] == 6
    assert len(payload["hidden_edges"]["edge_ids"]) == 6
    assert "Hidden is not absent" in payload["hidden_edges"]["reason"]


def test_edge_priority_is_deterministic_and_prefers_better_evidence(master):
    arcs = [
        dict(edge_id="edge:low", from_id="place:us", to_id="place:in-od",
             mechanism="trade_policy", confidence="low", evidence=["r1"],
             event_id="ev1"),
        dict(edge_id="edge:high", from_id="place:us", to_id="place:in-od",
             mechanism="trade_policy", confidence="high", evidence=["r2"],
             event_id="ev1"),
        dict(edge_id="edge:med", from_id="place:us", to_id="place:in-od",
             mechanism="trade_policy", confidence="medium", evidence=["r3"],
             event_id="ev1")]
    first = build(news_payload(arcs=arcs), master, max_edges=2)
    second = build(news_payload(arcs=list(reversed(arcs))), master, max_edges=2)
    assert [e["edge_id"] for e in first["edges"]] == ["edge:high", "edge:med"]
    assert [e["edge_id"] for e in first["edges"]] == \
        [e["edge_id"] for e in second["edges"]]


def test_a_news_mechanism_is_not_a_csrs_colour(master):
    payload = build(news_payload(arcs=[dict(
        edge_id="edge:1", from_id="place:us", to_id="place:in-od",
        mechanism="trade_policy", confidence="high", evidence=["r"],
        event_id="ev1", direction="negative")]), master)
    assert "not a CSRS quantity" in payload["edges"][0]["note"]
    assert any("share no scale with CSRS" in limitation
               for limitation in payload["limitations"])


# --------------------------------------------------- the preview coexists


def test_the_preview_is_its_own_labelled_layer(master):
    payload = build(news_payload(), master,
                    preview=dict(items=[dict(id="rourkela", lon=84.85)],
                                 arcs=[dict(id="us")]))
    layer = payload["layers"]["preview"]
    assert layer["fabricated"] is True
    assert "FABRICATED PREVIEW" in layer["label"]
    assert any("labelled FABRICATED" in limitation
               for limitation in payload["limitations"])


def test_no_preview_item_leaks_into_the_evidenced_layers(master):
    payload = build(news_payload(), master,
                    preview=dict(items=[dict(id="rourkela", lon=84.85,
                                             lat=22.26)]))
    assert payload["nodes"] == []
    assert payload["layers"]["affected"]["node_ids"] == []
    assert payload["edges"] == []


def test_without_a_preview_the_layer_says_absent_not_empty(master):
    payload = build(news_payload(), master)
    assert payload["layers"]["preview"]["status"] == "absent"
    assert payload["layers"]["preview"]["fabricated"] is False


# ---------------------------------------------------------- honest status


def test_incomplete_source_coverage_is_a_stated_limitation(master):
    payload = build(news_payload(coverage=dict(
        covered=1, total=3, uncovered=["pib", "sebi"], complete=False)), master)
    assert any("missing coverage, not a quiet world" in limitation
               for limitation in payload["limitations"])


def test_an_injection_flag_is_surfaced(master):
    payload = build(news_payload(injection=2), master)
    assert any("prompt-injection" in limitation
               for limitation in payload["limitations"])


def test_the_payload_states_its_versions(master):
    payload = build(news_payload(), master)
    assert payload["version"] == ADAPTER_VERSION
    assert payload["geometry_map_version"] == GEOMETRY_MAP_VERSION
    assert payload["revision"] == "r1"
    assert payload["as_of"] == "2026-10-17T10:00:00+05:30"


def test_the_transport_branch_has_every_field_the_plan_names(master):
    payload = build(news_payload(), master)
    for field in ("revision", "as_of", "sources_health", "signals", "nodes",
                  "edges", "sector_aggregates", "coverage", "limitations"):
        assert field in payload, field


# ----------------------------------------------------------- click detail


def test_a_click_shows_the_source_statement_and_both_times(master):
    payload = build(news_payload(
        signals=[dict(event_id="ev1", headline="Duty raised",
                      event_type="tariff", lifecycle="active",
                      origins=["place:us"], sources=["s1"],
                      source_statement="USTR opened a review of PV imports.",
                      published_at="2026-10-17T08:00:00+05:30",
                      first_seen_at="2026-10-17T08:12:00+05:30",
                      unresolved=["effective date"])]), master)
    detail = node_detail(payload, "place:us")
    event = detail["events"][0]
    assert event["source_statement"].startswith("USTR opened")
    assert event["published_at"] != event["first_seen_at"]
    assert event["unknowns"] == ["effective date"]
    assert "bounded by first-seen" in detail["qualification"]


def test_a_click_on_an_unresolved_record_explains_the_gap(master):
    payload = build(news_payload(regions=[dict(
        place_id="place:nowhere", name="X", severity="minor",
        events=["ev1"])]), master)
    detail = node_detail(payload, "place:nowhere")
    assert detail["status"] == "unresolved"
    assert "review queue" in detail["reason"]
    assert "add_to_watchlist" not in detail["allowed_actions"]


def test_allowed_actions_depend_on_the_role(master):
    payload = build(news_payload(assets=[dict(
        asset_id="asset:plant-a", name="Plant A", events=["ev1"])]), master)
    retail = node_detail(payload, "asset:plant-a", role="retail")
    regulator = node_detail(payload, "asset:plant-a", role="regulator")
    assert "add_to_watchlist" in retail["allowed_actions"]
    assert "open_case" in regulator["allowed_actions"]
    assert "open_case" not in retail["allowed_actions"]


def test_a_click_on_an_unknown_node_says_so(master):
    payload = build(news_payload(), master)
    assert node_detail(payload, "place:made-up")["status"] == "unknown"


# ---------------------------------- the mesh vocabulary is the renderer's


def test_every_mesh_this_adapter_names_exists_in_the_renderer():
    """The mapping is verified against the renderer, not merely asserted."""
    import pathlib

    source = pathlib.Path(
        "seraph/dashboard/console_component/index.html").read_text(
            encoding="utf-8")
    start = source.index("var DATA = ")
    line = source[start + len("var DATA = "):source.index("\n", start)]
    data = json.loads(line.rstrip().rstrip(";"))
    states = {s["n"] for s in data["india"]}
    countries = {c["i"] for c in data["world"]}

    master = _Master(places=[
        _Place("place:in-od", "Odisha", "state", lat=20.5, lon=85.0),
        _Place("place:us", "United States", "country", iso_code="USA")])
    resolver = GeometryResolver(master, state_meshes=states,
                                country_meshes=countries)
    assert resolver.resolve("place:in-od").mesh_id == "india_state:Odisha"
    assert resolver.resolve("place:us").mesh_id == "world_country:USA"
    assert "Odisha" in states and "USA" in countries


def test_a_state_the_renderer_does_not_have_is_not_pinned_to_a_guess():
    master = _Master(places=[
        _Place("place:xx", "Nowhereland", "state", parent_id=None)])
    assert GeometryResolver(master, state_meshes=STATE_MESHES).resolve(
        "place:xx") is None
