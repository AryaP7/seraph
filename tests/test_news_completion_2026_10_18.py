"""The remaining-work items from the 18 October 2026 news audit.

Separate from `test_news_audit_2026_10_18.py`, which pins the eleven
correctness defects. These cover the workstreams the audit listed as
incomplete implementation rather than as wrong output:

* per-use source permissions and an enforced retention window
* `tariff_cost_scenario()` reaching production through the role view
* `version_manifest()` reaching production through the payload manifest
* UI status derived from the record instead of asserted as a constant
"""
from __future__ import annotations

from decimal import Decimal
import pathlib
import re

import pytest

from seraph.dashboard.news_view import build_news_payload, news_channel
from seraph.news.acquisition import FetchedItem, FetchResult, NewsStore
from seraph.news.extraction import extract_events
from seraph.news.model import DEFAULT_PERMISSIONS, USES, Source, Story
from seraph.news.registry import load_master_data
from seraph.news.scenarios import (
    TariffMeasure, measure_from_event, scenario_for, tariff_cost_scenario)
from seraph.product_types import Timing

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "seraph/dashboard/console_component/bridge.js"

T0 = "2026-10-18T08:00:00+05:30"
T2 = "2026-10-18T10:00:00+05:30"
OLD = "2026-08-01T08:00:00+05:30"
URL = "https://www.federalreserve.gov/news/"


@pytest.fixture(scope="module")
def master():
    data, _info = load_master_data()
    return data


def source(**kwargs):
    base = dict(source_id="feed", provider="Feed", kind="official_policy",
                url=URL, topic_coverage=("policy",),
                accessibility_verified=True)
    base.update(kwargs)
    return Source(**base)


# ------------------------------------------- per-use source permissions

def test_an_unreviewed_source_keeps_exactly_its_old_behaviour():
    """One boolean covered five different uses. Replacing it must not
    quietly widen what an existing registration permits."""
    closed = source(may_store_full_text=False)
    open_ = source(may_store_full_text=True)
    assert [closed.permits(u) for u in USES] == [True, True, False, False, False]
    assert [open_.permits(u) for u in USES] == [True, True, True, True, False]


def test_redistribution_is_never_implied_by_storage():
    assert source(may_store_full_text=True).permits("redistribute") is False
    assert "redistribute" not in DEFAULT_PERMISSIONS


def test_a_reviewed_source_can_store_without_permitting_display():
    """The use this granularity exists for: terms that allow retention for
    analysis but not republication."""
    analysed = source(permissions=("fetch", "process", "store"))
    assert analysed.permits("store") is True
    assert analysed.permits("display") is False


def test_an_unknown_use_is_refused_rather_than_ignored():
    with pytest.raises(ValueError):
        source(permissions=("fetch", "telepathy"))
    with pytest.raises(ValueError):
        source().permits("telepathy")


def test_storing_what_may_not_be_fetched_is_refused():
    with pytest.raises(ValueError):
        source(permissions=("store",))


def test_a_permission_with_no_review_behind_it_says_so():
    assert source(may_store_full_text=True).rights_reviewed is False
    reviewed = source(permissions=("fetch", "process"),
                      rights_reviewed_by="legal", rights_reviewed_at=T0,
                      rights_version="terms-2026-07")
    assert reviewed.rights_reviewed is True
    assert reviewed.describe()["permitted_uses"]["store"] is False


def test_the_registration_survives_a_round_trip_through_the_store(tmp_path):
    store = NewsStore(tmp_path / "rights.sqlite")
    store.register(source(permissions=("fetch", "process", "store"),
                          rights_reviewed_by="legal", rights_reviewed_at=T0,
                          rights_version="terms-2026-07"))
    back = store.source("feed")
    assert back.permissions == ("fetch", "process", "store")
    assert back.rights_reviewed is True
    assert back.permits("display") is False


def test_storage_permission_gates_what_is_written(tmp_path):
    store = NewsStore(tmp_path / "gate.sqlite")
    store.register(source(permissions=("fetch", "process")))
    item = FetchedItem("r", "Policy", URL + "r", b"bytes", body="full text")
    store.ingest("feed", lambda *_: FetchResult((item,)), now=T0)
    assert [s.body for s in store.stories()] == [None]
    assert store.observation(store.stories()[0].observation_id).raw is None


# ----------------------------------------------- retention enforcement

def _store_with_old_and_new(tmp_path, **kwargs):
    store = NewsStore(tmp_path / "retention.sqlite")
    store.register(source(may_store_full_text=True, retention_days=30, **kwargs))
    for reference, stamp in (("old", OLD), ("new", "2026-10-17T08:00:00+05:30")):
        item = FetchedItem(reference, f"Policy {reference}", URL + reference,
                           b"article bytes " * 4, body="article text")
        store.ingest("feed", lambda *_, _i=item: FetchResult((_i,)), now=stamp)
    return store


def test_a_declared_retention_window_is_actually_enforced(tmp_path):
    store = _store_with_old_and_new(tmp_path)
    assert all(s.body for s in store.stories())
    report = store.apply_retention(now=T2)
    assert report["redacted"] == 1
    bodies = {s.title: s.body for s in store.stories()}
    assert bodies["Policy old"] is None
    assert bodies["Policy new"] == "article text"


def test_retention_removes_text_and_keeps_the_audit_trail(tmp_path):
    store = _store_with_old_and_new(tmp_path)
    store.apply_retention(now=T2)
    redactions = store.redactions()
    assert len(redactions) == 1
    row = redactions[0]
    assert row["reference"] == "old"
    assert row["content_hash"] and row["raw_bytes_removed"] > 0
    assert row["retention_days"] == 30
    # The observation itself is still there, with its hash.
    kept = [s for s in store.stories() if s.title == "Policy old"][0]
    assert store.observation(kept.observation_id) is not None
    assert store.observation(kept.observation_id).content_hash == row["content_hash"]


def test_a_dry_run_reports_without_removing(tmp_path):
    store = _store_with_old_and_new(tmp_path)
    report = store.apply_retention(now=T2, dry_run=True)
    assert report["redacted"] == 1 and report["dry_run"] is True
    assert all(s.body for s in store.stories())
    assert store.redactions() == []


def test_retention_is_idempotent(tmp_path):
    store = _store_with_old_and_new(tmp_path)
    assert store.apply_retention(now=T2)["redacted"] == 1
    assert store.apply_retention(now=T2)["redacted"] == 0


def test_retention_leaves_the_immutability_triggers_in_place(tmp_path):
    store = _store_with_old_and_new(tmp_path)
    store.apply_retention(now=T2)
    with pytest.raises(Exception, match="immutable"):
        with store.connect() as db:
            db.execute("UPDATE stories SET title='tampered'")
    with pytest.raises(Exception, match="immutable"):
        with store.connect() as db:
            db.execute("UPDATE observations SET content_hash='x'")


def test_a_source_with_no_window_is_untouched(tmp_path):
    store = NewsStore(tmp_path / "forever.sqlite")
    store.register(source(may_store_full_text=True, retention_days=None))
    item = FetchedItem("r", "Policy", URL + "r", b"bytes", body="text")
    store.ingest("feed", lambda *_: FetchResult((item,)), now=OLD)
    report = store.apply_retention(now=T2)
    assert report["redacted"] == 0
    assert store.stories()[0].body == "text"


def test_a_zero_day_window_is_refused_rather_than_silently_meaning_nothing():
    with pytest.raises(ValueError):
        source(retention_days=0)


def test_the_worker_exposes_retention_as_a_command():
    runner = (ROOT / "scripts/run_news.py").read_text(encoding="utf-8")
    assert '"--retention"' in runner
    assert "store.apply_retention(" in runner


# ------------------------------------ the tariff scenario in production

def tariff_event(master, title, *, story_id="t",
                 source_id="federal_register_india"):
    item = Story(story_id, source_id, "o", title, "https://x.invalid",
                 Timing(first_seen_at=T0))
    return [r.event for r in extract_events([item], master) if r.event][0]


RATE_CHANGE = ("Import duty on rare earth magnets raised from 10 per cent to "
               "25 per cent, effective from 1 June 2026")


def test_a_documented_duty_change_produces_an_accounting_scenario(master):
    event = tariff_event(master, RATE_CHANGE)
    edge = master.edges["cn_india_rare_earth_supply"]
    result = scenario_for(event, master, edge=edge, on=T2)
    assert result["status"] == "conditional_scenario"
    # 1.25 / 1.10 - 1
    assert Decimal(result["landed_component_change"]) == pytest.approx(
        Decimal("0.1363636"), abs=1e-6)
    assert result["origin"] == "cn" and result["destination"] == "us"


def test_an_unsized_relationship_produces_no_monetary_result(master):
    event = tariff_event(master, RATE_CHANGE)
    result = scenario_for(event, master,
                          edge=master.edges["cn_india_rare_earth_supply"], on=T2)
    assert result["monetary_range"] is None
    assert "unsized" in result["monetary_basis"]


def test_a_caller_supplied_base_and_pass_through_does_produce_a_range(master):
    event = tariff_event(master, RATE_CHANGE)
    result = scenario_for(event, master,
                          edge=master.edges["cn_india_rare_earth_supply"], on=T2,
                          eligible_cost_base=Decimal("1000000"),
                          pass_through=(Decimal("0.5"), Decimal("0.8")))
    low, high = (Decimal(v) for v in result["monetary_range"])
    assert low < high
    assert result["pass_through_basis"] == "caller assumption"
    assert result["prediction_status"] == "not_a_return_forecast"


def test_no_assumption_means_bounds_not_an_invented_midpoint(master):
    event = tariff_event(master, RATE_CHANGE)
    result = scenario_for(event, master,
                          edge=master.edges["cn_india_rare_earth_supply"], on=T2)
    assert result["pass_through"] == ["0", "1"]
    assert "bounds rather than an estimate" in result["pass_through_basis"]


def test_one_rate_level_prices_nothing_and_says_why(master):
    event = tariff_event(master, "Import duty on rare earth magnets set at "
                                 "25 per cent")
    built = measure_from_event(event, master,
                               edge=master.edges["cn_india_rare_earth_supply"])
    assert built["status"] == "unavailable"
    assert any("one rate level" in r for r in built["reasons"])


def test_a_scenario_needs_a_documented_product_scope(master):
    event = tariff_event(master, RATE_CHANGE)
    built = measure_from_event(event, master, edge=None)
    assert built["status"] == "unavailable"
    assert any("covered products" in r for r in built["reasons"])


def test_an_excluded_product_is_refused_by_the_measure_itself():
    measure = TariffMeasure(
        instrument_id="i", jurisdiction="us", origin="cn",
        products=("rare earth", "permanent magnet"), policy_status="effective",
        old_rate=Decimal("0.1"), new_rate=Decimal("0.25"),
        effective_from=T0, excluded_products=("permanent magnet",),
        evidence=("doc",))
    out = tariff_cost_scenario(measure, product="permanent magnet", origin="cn",
                               destination="us", on=T2,
                               eligible_cost_base=None,
                               pass_through=(Decimal(0), Decimal(1)))
    assert out["status"] == "inapplicable"


def _routed_payload(master, tmp_path, name):
    """A store whose single document reaches a documented exposure edge."""
    store = NewsStore(tmp_path / name)
    store.register(source(source_id="federal_register_india",
                          may_store_full_text=True))
    item = FetchedItem(
        "r1", "Certain Hot-Rolled Steel From India: Antidumping Duty Order",
        URL + "1", b"x")
    store.ingest("federal_register_india",
                 lambda *_: FetchResult((item,)), now=T0)
    return build_news_payload(store, master, decision_ts=T2,
                              role="institutional")


def test_the_institutional_view_is_the_production_caller(master, tmp_path):
    payload = _routed_payload(master, tmp_path, "scenario.sqlite")
    items = payload["role_view"]["items"]
    assert items, "the fixture must produce at least one documented route"
    assert all("scenario" in item for item in items), (
        "the tariff arithmetic existed and nothing on any screen called it")
    assert any("accounting scenario" in note
               for note in payload["role_view"]["notes"])


def test_a_route_with_no_priceable_instrument_explains_itself(master, tmp_path):
    """A duty ORDER that states no ad-valorem rate prices nothing, and the
    reader is told which input is missing rather than shown a blank."""
    payload = _routed_payload(master, tmp_path, "noscenario.sqlite")
    scenarios = [i["scenario"] for i in payload["role_view"]["items"]
                 if i["scenario"]]
    assert scenarios
    for scenario in scenarios:
        if scenario["status"] != "conditional_scenario":
            assert scenario["reasons"], "a refusal states its reasons"


# ------------------------------------- the version manifest in production

def _manifest(tmp_path, master, **kwargs):
    store = NewsStore(tmp_path / "manifest.sqlite")
    store.register(source(source_id="federal_register_india",
                          may_store_full_text=True))
    item = FetchedItem("r1", "Import duty on steel raised to 25 per cent",
                       URL + "1", b"x")
    store.ingest("federal_register_india",
                 lambda *_: FetchResult((item,)), now=T0)
    return store, build_news_payload(store, master, decision_ts=T2, **kwargs)


def test_every_version_that_shapes_the_projection_is_pinned(tmp_path, master):
    _store, payload = _manifest(tmp_path, master)
    manifest = payload["manifest"]
    for key in ("view", "extractor", "frame_rules", "syndication_key",
                "estimation", "registry", "source_versions",
                "representation_hashes"):
        assert manifest.get(key), f"{key} is not pinned"


def test_the_payload_says_it_is_a_reconstruction_not_a_replay(tmp_path, master):
    _store, payload = _manifest(tmp_path, master)
    assert payload["manifest"]["provenance"] == "reconstruction"
    assert "NOT the same as replaying" in payload["manifest"]["note"]


def test_source_definitions_are_pinned_by_content_hash(tmp_path, master):
    store, payload = _manifest(tmp_path, master)
    before = payload["manifest"]["source_versions"]
    assert before["federal_register_india"]["payload_hash"]
    store.register(source(source_id="federal_register_india",
                          may_store_full_text=True,
                          notes="rights re-read on 18 October"))
    after = build_news_payload(store, master, decision_ts=T2)["manifest"]
    assert (after["source_versions"]["federal_register_india"]["payload_hash"]
            != before["federal_register_india"]["payload_hash"]), (
        "a changed source definition must change the pinned version")


def test_processing_latency_is_recorded_and_labelled(tmp_path, master):
    _store, payload = _manifest(tmp_path, master)
    processing = payload["manifest"]["processing"]
    assert processing["events"] >= 1
    assert processing["median_latency_minutes"] is not None
    assert "NOT a measurement of how long the running pipeline took" in \
        processing["note"]


def test_the_registry_manifest_is_the_one_that_already_existed(tmp_path, master):
    _store, payload = _manifest(tmp_path, master)
    registry = payload["manifest"]["registry"]
    assert "interpretation" in registry and "counts" in registry


# ------------------------------------------------------ UI consistency

def test_the_method_panel_no_longer_asserts_a_disconnected_channel():
    source_js = BRIDGE.read_text(encoding="utf-8")
    assert "newsConnectionLine()" in source_js
    constant = re.search(
        r"kv\('News ingestion / estimator','Not connected", source_js)
    assert constant is None, (
        "the method panel stated the channel was not connected as a "
        "constant, so it went on saying so after it was connected")


def test_the_method_panel_derives_its_line_from_the_payload():
    source_js = BRIDGE.read_text(encoding="utf-8")
    body = source_js.split("function newsConnectionLine(){", 1)[1].split("\n}", 1)[0]
    assert "connected_surfaces" in body and "preview_surfaces" in body
    assert "status==='absent'" in body, (
        "an absent channel must still be reported as a fabricated preview")


def test_retail_weights_are_formatted_rather_than_printed_raw():
    source_js = BRIDGE.read_text(encoding="utf-8")
    assert "pct(i.portfolio_weight_pct)" in source_js
    assert "i.portfolio_weight_pct+'%'" not in source_js
    assert "toFixed(2)" in source_js.split("const pct=", 1)[1][:400]


def test_the_institutional_panel_renders_the_scenario():
    source_js = BRIDGE.read_text(encoding="utf-8")
    assert "scenarioHTML(i.scenario)" in source_js
    assert "Not a return forecast" in source_js


def test_a_scope_message_does_not_contradict_the_record(master):
    """Some scope messages claimed the body was not retained regardless of
    what the record actually held."""
    from seraph.news.scope import scope_of
    retained = scope_of("A notice with a body and nothing about scope.",
                        body_retained=True)
    assert "not retained" not in (retained.limitation or "")
    missing = scope_of("A title-only notice.", body_retained=False)
    assert "not retained for this item" in missing.limitation


def test_the_frame_reports_scope_against_the_retained_text(master):
    with_body = extract_events(
        [Story("a", "federal_register_india", "o",
               "Certain Hot-Rolled Steel From India: Antidumping Duty Order",
               "https://x.invalid", Timing(first_seen_at=T0),
               body="The order covers hot-rolled flat products.")], master)
    frame = with_body[0].event.frame
    assert "not retained" not in (frame.scope_note or "")


# ------------------------------------------------- rights on the surface

def test_the_payload_reports_how_many_source_rights_were_reviewed(tmp_path, master):
    store = NewsStore(tmp_path / "rights_surface.sqlite")
    store.register(source(source_id="a", may_store_full_text=True))
    store.register(source(source_id="b", permissions=("fetch", "process"),
                          rights_reviewed_by="legal", rights_reviewed_at=T0,
                          rights_version="v1"))
    payload = build_news_payload(store, master, decision_ts=T2, role="regulator")
    rights = payload["source_coverage"]["rights"]
    assert rights["total"] == 2 and rights["reviewed"] == 1
    assert rights["unreviewed"] == ["a"]
    assert rights["permitted_uses"]["redistribute"] == 0


def test_a_source_that_may_not_be_displayed_has_its_quotations_withheld(tmp_path, master):
    store = NewsStore(tmp_path / "display.sqlite")
    store.register(source(source_id="federal_register_india",
                          permissions=("fetch", "process", "store"),
                          rights_reviewed_by="legal", rights_reviewed_at=T0,
                          rights_version="v1"))
    item = FetchedItem("r1", "Import duty on steel raised to 25 per cent",
                       URL + "1", b"x", body="The duty rises to 25 per cent.")
    store.ingest("federal_register_india",
                 lambda *_: FetchResult((item,)), now=T0)
    payload = build_news_payload(store, master, decision_ts=T2)
    items = payload["surfaces"]["signals"]["items"]
    assert items and items[0]["display_permitted"] is False
    spans = items[0]["interpretation"]["evidence"]
    assert spans and all("withheld" in span["text"] for span in spans)
    # The offsets survive, so the claim is still traceable at the source.
    assert all(span["end"] > span["start"] for span in spans)


def test_a_displayable_source_still_shows_its_evidence(tmp_path, master):
    store = NewsStore(tmp_path / "shown.sqlite")
    store.register(source(source_id="federal_register_india",
                          may_store_full_text=True))
    item = FetchedItem("r1", "Import duty on steel raised to 25 per cent",
                       URL + "1", b"x", body="The duty rises to 25 per cent.")
    store.ingest("federal_register_india",
                 lambda *_: FetchResult((item,)), now=T0)
    payload = build_news_payload(store, master, decision_ts=T2)
    items = payload["surfaces"]["signals"]["items"]
    assert items[0]["display_permitted"] is True
    spans = items[0]["interpretation"]["evidence"]
    assert spans and not any("withheld" in span["text"] for span in spans)


def test_retention_does_not_reopen_the_document_budget(tmp_path):
    """A retention window is a decision not to hold the text, not an
    instruction to keep fetching it. Without this, a redacted story looked
    like an outstanding document and re-consumed the budget on every pass
    -- the defect A08 closed, reintroduced by the retention policy."""
    from seraph.news.enrichment import EnrichingFetcher
    from seraph.news.http_feed import HttpFeedFetcher

    raw = b"<article>" + b"The Board has adopted a capital rule. " * 8 + b"</article>"
    calls = []

    class Feed:
        _http = HttpFeedFetcher(
            transport=lambda url, headers:
            (calls.append(url) or (200, {"Content-Type": "text/html"}, raw)))

        def __call__(self, *_):
            return FetchResult((FetchedItem("0", "Policy 0", URL + "0", b"0"),))

    store = NewsStore(tmp_path / "retention_budget.sqlite")
    store.register(source(may_store_full_text=True, retention_days=30))
    fetcher = EnrichingFetcher(Feed(), store=store, max_documents=2)
    fetcher._http._throttle = lambda *_: None
    store.ingest("feed", fetcher)
    assert len(calls) == 1 and all(s.body for s in store.stories())

    assert store.apply_retention(now="2027-01-01T00:00:00+05:30")["redacted"] == 1
    assert not any(s.body for s in store.stories())

    for _ in range(3):
        later = EnrichingFetcher(Feed(), store=store, max_documents=2)
        later._http._throttle = lambda *_: None
        store.ingest("feed", later)
    assert len(calls) == 1, "expired text must not be fetched again every pass"
    assert store.pending_documents("feed") == []


# ------------------------------------- duplication versus corroboration

def _copy(index, source_id, title, body=None):
    return Story(f"s{index}", source_id, f"o{index}", title,
                 f"https://example.invalid/{index}", Timing(first_seen_at=T0),
                 body=body, syndication_group="g")


def test_ten_outlets_carrying_one_wire_are_copied_reporting():
    from seraph.news.corroboration import assess
    found = assess([_copy(i, f"outlet{i}", "Tata Steel halts output after fire")
                    for i in range(10)])
    assert found["corroboration"] == "copied_reporting"
    assert len(found["publishers"]) == 10 and found["distinct_texts"] == 1


def test_differently_written_copy_is_reported_but_never_called_independent():
    from seraph.news.corroboration import assess
    found = assess([
        _copy(0, "a", "Tata Steel halts output after fire at Kalinganagar"),
        _copy(1, "b", "Fire forces shutdown of Odisha steel plant, company says")])
    assert found["corroboration"] == "independently_written"
    assert found["independence_verified"] is False, (
        "two newsrooms rewriting one handout produce this too")
    assert "NOT established by this system" in found["note"]


def test_the_same_bytes_twice_are_a_duplicate_not_a_witness():
    from seraph.news.corroboration import assess
    found = assess([_copy(0, "a", "Tata Steel halts output"),
                    _copy(1, "a", "Tata Steel halts output")])
    assert found["duplicates"] == 1 and found["distinct_texts"] == 1
    assert found["corroboration"] == "single_publisher"


def test_corroboration_does_not_raise_confirmations(master, tmp_path):
    """A syndication group is one reporting origin however many outlets
    carry it. Reporting the shape of the group must not change that."""
    from seraph.news.corroboration import describe_event
    from seraph.news.extraction import extract
    copies = [_copy(i, f"outlet{i}", "Tata Steel halts output after fire")
              for i in range(10)]
    event = extract(copies, master).event
    assert event.confirmations == 1
    assert describe_event(event, copies)["confirmations"] == 1


def test_the_payload_carries_corroboration_per_event(tmp_path, master):
    store = NewsStore(tmp_path / "corroboration.sqlite")
    store.register(source(source_id="federal_register_india",
                          may_store_full_text=True))
    item = FetchedItem("r1", "Import duty on steel raised to 25 per cent",
                       URL + "1", b"x")
    store.ingest("federal_register_india",
                 lambda *_: FetchResult((item,)), now=T0)
    payload = build_news_payload(store, master, decision_ts=T2)
    row = payload["surfaces"]["signals"]["items"][0]["corroboration"]
    assert row["independence_verified"] is False
    assert row["documents"] == 1 and row["revisions"] == 0


# ------------------------------------------- document depth (19 October)

def test_a_pre_block_is_an_article_container():
    """The GPO publishes every Federal Register notice as
    `<html><body><pre>...</pre></body></html>` with no `article` or `main`.
    Those pages parsed to nothing and were refused as "no usable article
    container", which is why no Federal Register full text was ever
    retrieved and why the store held abstracts only."""
    from seraph.news.enrichment import extract_article
    raw = (b"<html><head><title>FR</title></head><body><pre>"
           + b"The Department of Commerce determines that the subject "
             b"merchandise is being sold at less than fair value. " * 4
           + b"</pre></body></html>")
    text, truncated = extract_article(raw, "text/html")
    assert "less than fair value" in text and not truncated


def test_a_real_article_container_still_wins():
    from seraph.news.enrichment import extract_article
    raw = (b"<html><body><article>" + b"The operative text of the notice. " * 8
           + b"<pre>navigation junk</pre></article></body></html>")
    text, _ = extract_article(raw, "text/html")
    assert "operative text" in text


def test_the_adapter_names_where_the_full_text_can_be_read():
    """federalregister.gov answers a document request with a 302 to its
    `unblock` interstitial. That is the publisher declining automated
    access and is not worked around; the same US Government work is read
    from the GPO instead, and the reader still cites the publisher."""
    import json as _json
    from seraph.news.json_feed import parse_json_source
    body = _json.dumps(dict(results=[dict(
        title="Widgets From India: Final Determination",
        html_url="https://www.federalregister.gov/documents/2026/10/19/2026-21293/widgets",
        document_number="2026-21293", publication_date="2026-10-19",
        abstract="An abstract.")])).encode()
    row = parse_json_source("federal_register", body)[0]
    assert row["url"].startswith("https://www.federalregister.gov/"), (
        "the citation must stay the publisher's own link")
    assert row["document_url"] == (
        "https://www.govinfo.gov/content/pkg/FR-2026-10-19/html/2026-21293.htm")


def test_an_item_with_no_document_number_gets_no_retrieval_url():
    import json as _json
    from seraph.news.json_feed import parse_json_source
    body = _json.dumps(dict(results=[dict(
        title="Untitled notice", html_url="https://www.federalregister.gov/x",
        publication_date="2026-10-19")])).encode()
    assert "document_url" not in parse_json_source("federal_register", body)[0]


def test_enrichment_fetches_the_retrieval_url_not_the_citation():
    from seraph.news.enrichment import EnrichingFetcher
    item = FetchedItem("r", "T", "https://www.federalregister.gov/documents/x",
                       b"x", metadata={"document_url":
                                       "https://www.govinfo.gov/content/pkg/FR-x/html/y.htm"})
    assert EnrichingFetcher._retrieval_url(item).startswith(
        "https://www.govinfo.gov/")
    bare = FetchedItem("r", "T", "https://www.pib.gov.in/a", b"x")
    assert EnrichingFetcher._retrieval_url(bare) == "https://www.pib.gov.in/a"


def test_a_proceeding_phrase_is_not_a_carved_out_product():
    """Found on real text: an antidumping notice reads "excluding rates
    that are zero", and reading that as a product carve-out put a scope
    caveat on the document and capped its confidence over a sentence
    about arithmetic."""
    from seraph.news.scope import scope_of
    assert scope_of("excluding rates that are zero or de minimis",
                    body_retained=True).excluded_products == ()
    assert scope_of("excluding respondents with zero margins",
                    body_retained=True).excluded_products == ()
    assert scope_of("the order excludes hot-rolled coil",
                    body_retained=True).excluded_products == ("hot-rolled coil",)


def test_document_progress_counts_a_separately_published_document(tmp_path):
    store = NewsStore(tmp_path / "progress.sqlite")
    store.register(source(may_store_full_text=True))
    item = FetchedItem("r1", "Notice", "https://www.federalregister.gov/d/1",
                       b"x", metadata={"document_url":
                                       "https://www.govinfo.gov/content/pkg/FR-a/html/b.htm"})
    store.ingest("feed", lambda *_: FetchResult((item,)), now=T0)
    assert store.document_progress("feed")["feed"]["with_document"] == 0
    store.save_document("feed", "https://www.govinfo.gov/content/pkg/FR-a/html/b.htm",
                        text="t" * 500, document_hash="h", format="article")
    assert store.document_progress("feed")["feed"]["with_document"] == 1, (
        "joining on the citation url reported zero documents for every "
        "source whose text is published elsewhere")
