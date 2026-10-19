"""The role ACTIONS: review a link, price a scenario, export an analysis.

A review queue on screen is not a review workflow and a scenario function
nothing can supply inputs to is not a scenario feature. These cover the
server half; `scripts/verify_news_workflows_browser.py` drives the same
operations through the real UI.

Two defects found by driving them are pinned here, because both made a
broken operation look like a working one:

* the console passed an OPEN STORE where a path was expected, so every
  role action — and the console's own acquisition button — raised
  `argument should be a str or an os.PathLike object ... not 'NewsStore'`;
* and the bridge tested `answered` before `error`, so that refusal came
  back to the user as "DONE" with an empty detail.
"""
from __future__ import annotations

import pathlib

import pytest

from seraph.news.acquisition import FetchedItem, FetchResult, NewsStore
from seraph.news.model import Source
from seraph.news.registry import load_master_data
from seraph.news import workflows

ROOT = pathlib.Path(__file__).resolve().parents[1]
T0 = "2026-10-18T08:00:00+05:30"
URL = "https://www.federalreserve.gov/news/"


@pytest.fixture(scope="module")
def master():
    data, _info = load_master_data()
    return data


@pytest.fixture
def store(tmp_path):
    made = NewsStore(tmp_path / "news.sqlite")
    made.register(Source("feed", "Feed", "official_policy", URL, ("policy",),
                         may_store_full_text=True, accessibility_verified=True))
    item = FetchedItem("r1", "Import duty on steel raised to 25 per cent",
                       URL + "1", b"x")
    made.ingest("feed", lambda *_: FetchResult((item,)), now=T0)
    return made


# ------------------------------------------------ who may do what

def test_only_the_regulator_reviews_links(store):
    with pytest.raises(PermissionError):
        workflows.review_instrument_link(
            store, role="institutional", later_event_id="b",
            earlier_event_id="a", decision="confirmed", reason="x")


def test_only_the_institutional_view_prices_and_exports(master, store):
    with pytest.raises(PermissionError):
        workflows.export_analysis(role="retail", channel={})
    with pytest.raises(PermissionError):
        workflows.run_scenario(object(), master, role="regulator")


def test_a_demo_role_is_never_recorded_as_an_authenticated_user():
    anonymous = workflows.attribution("regulator")
    assert anonymous["authenticated"] is False
    assert anonymous["reviewer"].startswith(workflows.DEMO_PREFIX)
    assert "NOT authentication" in anonymous["basis"]


def test_a_server_identity_replaces_the_demo_one_when_there_is_one():
    real = workflows.attribution("regulator",
                                 authenticated_subject="user:1138")
    assert real == dict(reviewer="user:1138", authenticated=True,
                        basis="server-side authenticated session")


# ------------------------------------------------- the review workflow

def test_a_review_is_recorded_with_its_reason_and_time(store):
    out = workflows.review_instrument_link(
        store, role="regulator", later_event_id="evt_b",
        earlier_event_id="evt_a", decision="confirmed",
        reason="same case number, confirmed against the register")
    assert out["decision"] == "confirmed" and out["decided_at"]
    recorded = store.supersession_decisions()["decisions"]
    assert len(recorded) == 1
    assert "confirmed against the register" in recorded[0]["reason"]
    assert recorded[0]["reviewer"] == "demo-role:regulator"


def test_a_review_without_a_reason_is_refused(store):
    with pytest.raises(ValueError, match="reason"):
        workflows.review_instrument_link(
            store, role="regulator", later_event_id="b",
            earlier_event_id="a", decision="confirmed", reason="   ")


def test_only_two_decisions_exist(store):
    with pytest.raises(ValueError):
        workflows.review_instrument_link(
            store, role="regulator", later_event_id="b", earlier_event_id="a",
            decision="maybe", reason="unsure")


def test_a_decision_changes_projections_and_no_stored_document(store):
    before = [(s.story_id, s.title, s.body) for s in store.stories()]
    workflows.review_instrument_link(
        store, role="regulator", later_event_id="evt_b",
        earlier_event_id="evt_a", decision="confirmed", reason="checked")
    assert [(s.story_id, s.title, s.body) for s in store.stories()] == before, (
        "a reviewed judgement must not rewrite the evidence it is about")
    assert store.supersession_decisions()["confirmed"] == (("evt_b", "evt_a"),)


# ---------------------------------------------- the scenario inputs

def test_a_pass_through_outside_the_unit_interval_is_refused(master, store):
    from seraph.news.extraction import extract_events
    event = next(r.event for r in extract_events(store.stories(), master)
                 if r.event)
    with pytest.raises(ValueError, match="at most 1"):
        workflows.run_scenario(event, master, role="institutional",
                               pass_through=("0.2", "1.4"))


def test_an_inverted_pass_through_is_refused(master, store):
    from seraph.news.extraction import extract_events
    event = next(r.event for r in extract_events(store.stories(), master)
                 if r.event)
    with pytest.raises(ValueError, match="inverted"):
        workflows.run_scenario(event, master, role="institutional",
                               pass_through=("0.9", "0.2"))


def test_a_non_numeric_assumption_is_refused(master, store):
    from seraph.news.extraction import extract_events
    event = next(r.event for r in extract_events(store.stories(), master)
                 if r.event)
    with pytest.raises(ValueError, match="must be a number"):
        workflows.run_scenario(event, master, role="institutional",
                               cost_base="a lot")


def test_caller_assumptions_are_labelled_as_assumptions(master, store):
    from seraph.news.extraction import extract_events
    event = next(r.event for r in extract_events(store.stories(), master)
                 if r.event)
    out = workflows.run_scenario(event, master, role="institutional",
                                 cost_base="1000000",
                                 pass_through=("0.5", "0.8"))
    assert out["inputs"]["cost_base"] == "1000000"
    assert "not observed company data" in out["inputs"]["supplied_by"]


# ------------------------------------------------------- the export

def test_an_export_carries_evidence_and_limitations(master, store):
    from seraph.dashboard.news_view import news_channel
    channel = news_channel(store, master, decision_ts="2026-10-18T10:00:00+05:30")
    out = workflows.export_analysis(role="institutional", channel=channel)
    assert out["schema"] == "news-analysis-export/1"
    assert out["manifest"] and out["exported_at"]
    assert any("not a measured outcome" in line or "Qualitative mechanism" in line
               for line in out["limitations"])
    assert any("benchmark has NOT been passed" in line
               for line in out["limitations"])


# ------------------------------- the two defects found by driving it

def test_the_console_dispatch_accepts_an_open_store(master, store):
    """`main()` hands `_news_action` an OPEN STORE, not a path. Re-opening
    it raised "argument should be a str or an os.PathLike object ... not
    'NewsStore'" for every role action, and for the console's own
    acquisition button."""
    from seraph.dashboard.prototype_app import _news_action
    out = _news_action(dict(op="news_review", later="evt_b", earlier="evt_a",
                            decision="confirmed", reason="checked"),
                       "regulator", store, master,
                       {"news": {"as_of": "2026-10-18T10:00:00+05:30"}})
    assert out["kind"] == "news_review"
    assert store.supersession_decisions()["decisions"]


def test_the_acquisition_button_does_not_reopen_the_store():
    app = (ROOT / "seraph/dashboard/prototype_app.py").read_text(encoding="utf-8")
    assert "NewsStore(news_store).request_acquisition" not in app
    assert "NewsStore(news_store).acquisition_progress" not in app


def test_a_refused_operation_is_not_reported_as_done():
    """A refusal comes back with an `error` and no `kind`, carrying the
    same `context.request_id` as a success. Testing `answered` first
    showed it as "DONE" with an empty detail."""
    bridge = (ROOT / "seraph/dashboard/console_component/bridge.js").read_text(
        encoding="utf-8")
    block = bridge.split("const answered=", 1)[1].split("else if(contextMoved)", 1)[0]
    error_at = block.index("data.result.error")
    answered_at = block.index("else if(answered)")
    assert error_at < answered_at, (
        "the error branch must be tested before the answered branch")
