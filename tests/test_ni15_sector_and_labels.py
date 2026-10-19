"""NI15 — what the browser showed, and what each thing turned out to be.

Three defects found by driving the real console against the pilot store, not
by reading the code:

* **A documented sector exposure disappeared.** The sector panel, the
  geography overlay and the globe were all computed from the *displayed page*
  of events. With 181 eligible events and a 40-event page, the Kalinganagar →
  `sector:steel` relationship was simply absent, which reads as "steel has no
  documented exposure".
* **A sector sat in the globe's review queue.** `sector:auto` was filed under
  "no evidenced coordinate or mapped geometry", framing a deliberate design
  rule — an industry has no coordinate — as a data gap, and burying real
  geography failures among non-failures.
* **Real evidence was labelled FABRICATED.** Clicking an evidenced node
  opened a card headed "FABRICATED PREVIEW" above sourced Federal Register
  headlines with working links. A tag that is wrong in the safe direction
  still teaches the viewer to ignore it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from seraph.dashboard.globe_payload import build_globe_payload
from seraph.dashboard.news_view import build_news_payload, news_channel
from seraph.news.acquisition import FetchResult, NewsStore
from seraph.news.model import ExposureEdge, Place, SourceRef
from seraph.news.registry import MasterData

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "seraph/dashboard/console_component"

A = "2026-10-17T09:00:00+05:30"
B = "2026-10-17T10:00:00+05:30"


def item(title, reference=None):
    from seraph.news.acquisition import FetchedItem

    return FetchedItem(reference or title, title,
                       "https://example.invalid/" + (reference or "1"),
                       title.encode())


@pytest.fixture
def store(tmp_path):
    from seraph.news.model import Source

    db = NewsStore(tmp_path / "news.sqlite")
    db.register(Source("feed", "Official", "official_policy",
                       "https://example.invalid", (),
                       poll_interval_minutes=60, max_retries=1))
    return db


# ------------------------------------------- aggregates vs the shown page


def _master_with_sector_edge() -> MasterData:
    master = MasterData()
    master.add_place(Place("in", "India", "country", iso_code="IND",
                           lat=22.0, lon=79.0))
    master.add_edge(ExposureEdge(
        edge_id="in_demo_sector", from_id="in", to_id="sector:demo",
        mechanism="input_dependency", confidence="medium",
        evidence=(SourceRef(source_id="curated",
                            reference="https://example.invalid/evidence"),)))
    return master


def test_the_rail_pages_but_the_aggregates_do_not(store):
    store.ingest("feed", lambda *_: FetchResult(
        tuple(item(f"RBI releases bulletin {i}", str(i)) for i in range(30))),
        now=A)
    channel = news_channel(store, MasterData(), decision_ts=B, limit=5)
    assert len(channel["events"]) == 5
    assert len(channel["eligible_events"]) == 30
    assert channel["pagination"]["aggregates_cover"] == 30


def test_the_pagination_note_says_what_is_and_is_not_paged(store):
    store.ingest("feed", lambda *_: FetchResult((item("A bulletin"),)), now=A)
    channel = news_channel(store, MasterData(), decision_ts=B, limit=1)
    note = channel["pagination"]["note"]
    assert "rail is paginated" in note
    assert "every eligible event" in note


def test_an_estimate_is_never_produced_for_an_event_outside_the_eligible_set(store):
    store.ingest("feed", lambda *_: FetchResult(
        tuple(item(f"bulletin {i}", str(i)) for i in range(12))), now=A)
    channel = news_channel(store, MasterData(), decision_ts=B, limit=3)
    eligible = {e.event_id for e in channel["eligible_events"]}
    assert {e.event_id for e in channel["estimates"]} <= eligible


# ------------------------------------- a sector is not a geography failure


def _payload_with_sector_arc() -> tuple[dict, MasterData]:
    master = _master_with_sector_edge()
    payload = dict(
        decision_ts=B, version="test", injection_flags=0,
        source_coverage=dict(covered=1, total=1, uncovered=[], complete=True),
        pagination=dict(total=1, displayed=1, aggregates_cover=1),
        surfaces=dict(
            signals=dict(surface="signals", status="observed", items=[]),
            geography=dict(surface="geography", status="estimate", regions=[],
                           arcs=[dict(edge_id="in_demo_sector", from_id="in",
                                      to_id="sector:demo",
                                      mechanism="input_dependency",
                                      confidence="medium",
                                      evidence=["https://example.invalid/evidence"],
                                      event_id="ev1")]),
            assets=dict(surface="assets", status="observed", items=[]),
            sector_stress=dict(surface="sector_stress",
                               news=dict(status="estimate", rows=[]),
                               hawkes=dict(status="unavailable", rows=[]))))
    return payload, master


def test_a_sector_endpoint_does_not_enter_the_review_queue():
    payload, master = _payload_with_sector_arc()
    globe = build_globe_payload(payload, master, revision="r", as_of=B,
                                country_meshes=("IND",))
    assert globe["review_queue"]["count"] == 0
    assert [u["node_id"] for u in globe["unresolved"]] == []


def test_a_sector_terminated_path_is_recorded_not_dropped():
    payload, master = _payload_with_sector_arc()
    globe = build_globe_payload(payload, master, revision="r", as_of=B,
                                country_meshes=("IND",))
    terminated = globe["sector_terminated_paths"]
    assert [t["sector"] for t in terminated] == ["demo"]
    assert terminated[0]["shown_in"] == "sector_panel"
    assert terminated[0]["evidence_ids"] == ["https://example.invalid/evidence"]
    assert "not a point on the earth" in terminated[0]["note"]


def test_a_genuinely_unplaceable_record_still_reaches_the_review_queue():
    """The queue must keep meaning something."""
    payload, master = _payload_with_sector_arc()
    payload["surfaces"]["geography"]["regions"] = [
        dict(place_id="place:atlantis", name="Atlantis", severity="minor",
             events=["ev1"])]
    globe = build_globe_payload(payload, master, revision="r", as_of=B,
                                country_meshes=("IND",))
    assert [u["node_id"] for u in globe["unresolved"]] == ["place:atlantis"]


def test_a_sector_is_never_drawn_as_a_node():
    payload, master = _payload_with_sector_arc()
    globe = build_globe_payload(payload, master, revision="r", as_of=B,
                                country_meshes=("IND",))
    assert all(not n["node_id"].startswith("sector:") for n in globe["nodes"])


# ------------------------------------- the subject of an instrument


def test_the_subject_origin_is_its_own_globe_layer():
    """Not the publisher's office, not affected, not a mention.

    "The goods under investigation come from here" is an evidenced role of
    its own, and folding it into any existing layer would say something the
    evidence does not.
    """
    master = MasterData()
    master.add_place(Place("in", "India", "country", iso_code="IND",
                           lat=22.0, lon=79.0))
    payload = dict(
        decision_ts=B, version="test", injection_flags=0,
        source_coverage=dict(covered=1, total=1, uncovered=[], complete=True),
        pagination=dict(total=1, displayed=1, aggregates_cover=1),
        surfaces=dict(
            signals=dict(surface="signals", status="observed", items=[dict(
                event_id="ev1", headline="Chromium Trioxide From India",
                event_type="trade_remedy_determination", lifecycle="active",
                subject_origins=["in"], sources=["s1"])]),
            geography=dict(surface="geography", status="estimate", regions=[],
                           arcs=[]),
            assets=dict(surface="assets", status="observed", items=[]),
            sector_stress=dict(surface="sector_stress",
                               news=dict(status="estimate", rows=[]),
                               hawkes=dict(status="unavailable", rows=[]))))
    globe = build_globe_payload(payload, master, revision="r", as_of=B,
                                country_meshes=("IND",))
    assert globe["layers"]["subjects"]["node_ids"] == ["in"]
    assert globe["layers"]["affected"]["node_ids"] == []
    assert globe["layers"]["mentions"]["node_ids"] == []
    assert "covered by the instrument" in globe["layers"]["subjects"]["legend"]


def test_the_subjects_layer_claims_no_impact():
    source = (COMPONENT / "news_layer.js").read_text(encoding="utf-8")
    assert "subject:" in source, "the layer has its own colour"
    assert "goods from here are covered by the instrument" in source
    # Distinct from affected, so an instrument's subject never reads as a
    # documented impact.
    assert "0x7fb8a0" in source and "0x9b7bd4" in source


# ----------------------------------- a reported coordinate is not a city


def test_a_source_reported_point_is_not_a_city():
    """USGS is the one source that supplies its own coordinate.

    An epicentre has no administrative meaning, no boundary and its own
    measurement uncertainty. It was reported with `location_precision: city`
    because `city` was the nearest available place kind.
    """
    master = MasterData()
    payload = dict(
        decision_ts=B, version="test", injection_flags=0,
        source_coverage=dict(covered=1, total=1, uncovered=[], complete=True),
        pagination=dict(total=1, displayed=1, aggregates_cover=1),
        source_places=[dict(place_id="hazard_1", name="M 4.8 - 196 km SSE",
                            kind="point", lat=-16.04, lon=-177.73)],
        surfaces=dict(
            signals=dict(surface="signals", status="observed", items=[dict(
                event_id="ev1", headline="M 4.8", event_type="physical_hazard",
                lifecycle="active", origins=["hazard_1"], sources=["s1"])]),
            geography=dict(surface="geography", status="estimate", regions=[],
                           arcs=[]),
            assets=dict(surface="assets", status="observed", items=[]),
            sector_stress=dict(surface="sector_stress",
                               news=dict(status="estimate", rows=[]),
                               hawkes=dict(status="unavailable", rows=[]))))
    globe = build_globe_payload(payload, master, revision="r", as_of=B)
    node = next(n for n in globe["nodes"] if n["node_id"] == "hazard_1")
    assert node["location_precision"] == "point"
    assert node["coordinates"] == [-177.73, -16.04]


def test_the_place_kind_travels_with_the_transported_row():
    """Re-guessing it at the other end is how an epicentre became a city."""
    source = (ROOT / "seraph/dashboard/news_view.py").read_text(encoding="utf-8")
    assert "kind=p.kind" in source
    target = (ROOT / "seraph/dashboard/globe_payload.py").read_text(encoding="utf-8")
    assert "row.get('kind')" in target
    assert "'city', lat=row['lat']" not in target


# ------------------------------------------------- the label follows content


def _bridge() -> str:
    return (COMPONENT / "bridge.js").read_text(encoding="utf-8")


def _index() -> str:
    return (COMPONENT / "index.html").read_text(encoding="utf-8")


def test_the_detail_tagger_reads_the_content_declaration():
    source = _bridge()
    assert "data-evidenced" in source, (
        "the tag must depend on what the panel holds, not stamp everything")
    assert "EVIDENCED_NOTE" in source


def test_every_detail_writer_declares_its_provenance():
    """One writer, one declaration.

    Relying on each caller to remember a cleanup is what let the preview
    asset beacon inherit the previous news card's EVIDENCED label: the asset
    path wrote `innerHTML` directly and never cleared the attribute.
    """
    source = _index()
    assert "function writeDetail(html, provenance)" in source
    # Nothing writes the panel behind the helper's back.
    assert 'el("dbody").innerHTML' not in source
    assert "el('dbody').innerHTML" not in source


def test_the_news_writer_declares_news_and_the_preview_writers_declare_none():
    source = _index()
    assert "writeDetail(html, 'news')" in source
    assert source.count("writeDetail(") >= 4
    assert ", null)" in source, "preview writers pass an explicit null"


def test_the_evidenced_note_does_not_claim_a_measured_loss():
    source = _bridge()
    note = re.search(r"const EVIDENCED_NOTE=([\s\S]*?);\n", source)
    assert note, "the evidenced note must exist"
    text = note.group(1)
    assert "qualitative" in text and "not measured losses" in text
    assert "not SERAPH pillar output" in text


def test_the_evidenced_note_has_its_own_style_distinct_from_fabricated():
    source = _index()
    assert ".evidenced{" in source
    fabricated = re.search(r"\.fabricated\{([^}]*)\}", source).group(1)
    evidenced = re.search(r"\.evidenced\{([^}]*)\}", source).group(1)
    assert fabricated != evidenced
    # Warm tag for fabricated, cool note for evidenced.
    assert "#61310b" in fabricated and "#0c2027" in evidenced


# ----------------------------------------------- the sector row explains itself


def test_a_sector_row_names_its_mechanism_and_sizing():
    source = _bridge()
    assert "function sectorRow(" in source
    assert "mechanism unrecorded" in source
    assert "size unknown" in source
    assert "unsized relationship(s)" in source


def test_ambiguous_is_explained_rather_than_shown_as_a_bare_word():
    source = _bridge()
    assert "DIRECTION_TEXT" in source
    assert "opposing or unestablished mechanisms" in source


def test_a_sector_row_can_open_the_events_behind_it():
    source = _bridge()
    assert "data-event-ids" in source
    assert "function revealEvents(" in source
    assert 'details.sig[data-event-id="' in source


def test_an_event_not_on_the_page_says_so_rather_than_opening_nothing():
    source = _bridge()
    assert "not on the displayed page" in source


def test_the_empty_sector_panel_does_not_claim_safety():
    source = _bridge()
    assert "missing exposure" in source and "not an absence of risk" in source


def test_the_sector_panel_states_what_it_covers():
    source = _bridge()
    assert "aggregates_cover" in source
    assert "not just the page shown" in source


# -------------------------------------------------- end to end on real data


@pytest.mark.skipif(not (ROOT / "prototype_runs/news-intelligence-pilot.sqlite").exists(),
                    reason="the pilot store is not present in this checkout")
def test_the_pilot_sector_panel_is_page_independent():
    """The exact regression, on the real acquired corpus."""
    from seraph.news.acquisition import _now
    from seraph.news.registry import load_master_data

    store = NewsStore(ROOT / "prototype_runs/news-intelligence-pilot.sqlite")
    master, _ = load_master_data()
    now = _now()
    narrow = build_news_payload(store, master, decision_ts=now, limit=40)
    wide = build_news_payload(store, master, decision_ts=now, limit=1000)

    def sectors(payload):
        return sorted(r["sector"] for r in
                      payload["surfaces"]["sector_stress"]["news"]["rows"])

    assert sectors(narrow) == sectors(wide)
    assert narrow["pagination"]["displayed"] < narrow["pagination"]["aggregates_cover"]
