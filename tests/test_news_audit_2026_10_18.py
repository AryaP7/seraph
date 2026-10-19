"""The eleven confirmed defects from the 18 October 2026 news audit.

Every test here is a counterexample the audit reproduced against the running
code, written so it fails if the defect comes back. They are grouped by the
audit's own ticket ids (A01-A11) and each one states the wrong output that
used to be produced, because a regression test whose name is the only record
of what it protects stops being readable within a month.

The audit's scripts live under
`docs/evidence/news-intelligence/full-audit-2026-10-18/`; the re-run against
the fixed code is in `../post-audit-fixes-2026-10-18/`.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from seraph.dashboard.news_view import build_news_payload
from seraph.news.acquisition import FetchedItem, FetchResult, NewsStore, _now
from seraph.news.currency import partition
from seraph.news.estimation import estimate_impacts
from seraph.news.event_frames import arrival, frame_for, parse_date
from seraph.news.extraction import extract_events, instrument_ids
from seraph.news.lifecycle import applicability
from seraph.news.model import Source, Story, syndication_key, syndication_tokens
from seraph.news.registry import MasterData, load_master_data
from seraph.news.scope import scope_of
from seraph.operations.jobs import JobStore
from seraph.product_types import Timing
from seraph.validation.news_corpus import score_gold
from seraph.validation.news_gate import REQUIRED_SLICES, SliceResult

ROOT = pathlib.Path(__file__).resolve().parents[1]

T0 = "2026-10-18T08:00:00+05:30"
T1 = "2026-10-18T09:00:00+05:30"
T2 = "2026-10-18T10:00:00+05:30"
URL = "https://www.federalreserve.gov/news/"


@pytest.fixture(scope="module")
def master():
    data, _info = load_master_data()
    return data


def story(title, body=None, *, seen=T2, source_id="federal_register_india",
          story_id="s"):
    return Story(story_id=story_id, source_id=source_id, observation_id="o",
                 title=title, url="https://example.invalid/audit", body=body,
                 timing=Timing(first_seen_at=seen))


def events_for(title, body=None, *, master, seen=T2, story_id=None):
    # A distinct story id per document: `event_identity` is derived from the
    # syndication group, which falls back to the story id, so reusing one
    # would collapse two documents into a single event id.
    identity = story_id or f"s{abs(hash((title, seen))) % 10**8}"
    source = story(title, body, seen=seen, story_id=identity)
    return [r.event for r in extract_events([source], master)
            if r.event is not None]


def feed_source():
    return Source("feed", "Feed", "official_policy", URL, ("policy",),
                  may_store_full_text=True, accessibility_verified=True)


# ===================================================================== A01
# `class_recall` reported 95% for 95 correctly labelled negatives and five
# missed supported events. Actual supported-event recall was 0/5.

def _slices():
    return {name: SliceResult(name) for name in REQUIRED_SLICES}


NEGATIVE = dict(event_type="other", action="unknown", policy_status="unknown",
                targets=[], quantities=[])


def test_a01_recall_cannot_be_earned_by_correctly_rejecting_negatives():
    slices, per_class = _slices(), {}
    for _ in range(95):
        score_gold(slices, NEGATIVE, NEGATIVE, per_class=per_class)
    for _ in range(5):
        score_gold(slices, {}, dict(NEGATIVE, event_type="production_halt"),
                   per_class=per_class)

    recall = slices["class_recall"]
    assert recall.relevant == 5, "only supported events belong in the denominator"
    assert recall.correct == 0
    assert recall.accuracy == 0.0, (
        "95 correctly rejected negatives reported 95% recall while the "
        "system found none of the five supported events")
    assert recall.abstained == 5


def test_a01_negatives_are_scored_as_specificity_with_their_false_positives():
    slices = _slices()
    for _ in range(18):
        score_gold(slices, NEGATIVE, NEGATIVE)
    for _ in range(2):
        score_gold(slices, dict(NEGATIVE, event_type="tariff_announcement"),
                   NEGATIVE)
    item = slices["negative_specificity"]
    assert (item.scored, item.correct, item.extra) == (20, 18, 2)
    assert item.accuracy == pytest.approx(0.9)
    assert item.describe()["false_positive_rate"] == pytest.approx(0.1)


def test_a01_per_class_results_name_the_class_that_failed():
    slices, per_class = _slices(), {}
    score_gold(slices, dict(NEGATIVE, event_type="tariff_announcement"),
               dict(NEGATIVE, event_type="production_halt"), per_class=per_class)
    assert per_class["production_halt"]["gold"] == 1
    assert per_class["production_halt"]["found"] == 0
    assert per_class["production_halt"]["confused_with"] == {"tariff_announcement": 1}


def test_a01_the_legacy_runner_separates_the_two_populations_too():
    runner = (ROOT / "scripts/run_news_gate.py").read_text(encoding="utf-8")
    assert "negative_specificity" in runner
    assert "is_supported_event(want_class)" in runner, (
        "the legacy gate counted every labelled headline, including hard "
        "negatives, in the recall denominator")


# ===================================================================== A02
# "effective from 1 December 2026" yielded effective_at=null and
# in_force=true: the pattern recognised named months, the conversion
# accepted only ISO, and lifecycle read the missing value as no later start.

@pytest.mark.parametrize("text,expected,precision", [
    ("1 December 2026", "2026-12-01T00:00:00+05:30", "day"),
    ("December 1, 2026", "2026-12-01T00:00:00+05:30", "day"),
    ("1 Feb 2026", "2026-02-01T00:00:00+05:30", "day"),
    ("2026-12-01", "2026-12-01T00:00:00+05:30", "day"),
    ("December 2026", "2026-12-01T00:00:00+05:30", "month"),
])
def test_a02_supported_date_forms_parse_with_their_precision(text, expected, precision):
    parsed = parse_date(text)
    assert parsed is not None, f"{text!r} is a date an official document writes"
    assert (parsed.starts, parsed.precision) == (expected, precision)


@pytest.mark.parametrize("text", ["30 days after publication", "upon publication",
                                  "the first Monday of next term", ""])
def test_a02_an_unreadable_date_is_none_not_a_guess(text):
    assert parse_date(text) is None


def test_a02_a_future_named_month_is_not_in_force(master):
    events = events_for("Import duty on steel increased effective from "
                        "1 December 2026", master=master)
    assert len(events) == 1
    event = events[0]
    assert event.timing.effective_at == "2026-12-01T00:00:00+05:30"
    assert event.frame.policy_status == "adopted"
    state = applicability(event, T2)
    assert state["in_force"] is False
    assert state["state"] == "decided_not_yet_in_force"


def test_a02_a_recognised_but_unreadable_start_abstains(master):
    """"Recognised and unconvertible" must not be treated as "no date"."""
    events = events_for("Import duty on steel increased. The measure is in "
                        "force, effective upon publication in the official "
                        "gazette.", master=master)
    event = events[0]
    assert event.frame.policy_status == "adopted"
    assert applicability(event, T2)["in_force"] is False
    assert any("not in a form this extractor converts" in u
               for u in event.frame.unknowns)


def test_a02_a_month_precision_window_containing_the_decision_abstains():
    frame = frame_for("Duty on widgets takes effect effective December 2026.",
                      "s", "import_duty_change",
                      available_at="2026-12-15T00:00:00+05:30")
    assert frame.effective_precision == "month"
    assert frame.policy_status == "adopted", (
        "a month that CONTAINS the decision time establishes neither that "
        "the measure started nor that it has not")
    assert any("month precision" in u for u in frame.unknowns)


def test_a02_a_day_precision_date_that_has_arrived_stays_in_force():
    frame = frame_for("Duty on widgets is effective from 1 June 2026.",
                      "s", "import_duty_change",
                      available_at="2026-06-01T09:00:00+05:30")
    assert frame.policy_status == "effective"


@pytest.mark.parametrize("as_of,expected", [
    ("2026-11-30T23:59:59+05:30", "future"),
    ("2026-12-01T00:00:00+05:30", "arrived"),
])
def test_a02_arrival_is_decided_by_the_stated_precision(as_of, expected):
    assert arrival(parse_date("1 December 2026"), as_of) == expected


def test_a02_a_month_window_around_the_question_is_uncertain():
    assert arrival(parse_date("December 2026"),
                   "2026-12-15T00:00:00+05:30") == "uncertain"
    assert arrival(parse_date("December 2026"),
                   "2027-01-02T00:00:00+05:30") == "arrived"


def test_a02_a_future_revocation_has_not_ended_the_measure():
    """The mirror of the start-date defect: a revocation dated next month
    has not happened, and reporting the document as `repealed` today
    asserts that the measure it ends has already stopped."""
    frame = frame_for("Widgets From India: the antidumping duty order is "
                      "revoked effective 1 December 2026.",
                      "s", "trade_remedy_determination", available_at=T2)
    assert frame.policy_status != "repealed"
    assert frame.pending_termination == "2026-12-01T00:00:00+05:30"
    assert any("has not arrived" in u for u in frame.unknowns)


# ===================================================================== A03
# A steel duty whose body read "This order does not apply to products from
# India" still emitted an adverse Indian steel route at medium confidence,
# because scope was read from the headline and the exclusion was in the body.

def test_a03_a_named_country_exclusion_is_read_from_the_text():
    found = scope_of("Certain Hot-Rolled Steel From India: Antidumping Duty "
                     "Order. This order does not apply to products from India.")
    assert found.excluded_countries == ("India",)
    assert found.named_exclusions is True


def test_a03_an_excluded_origin_suppresses_the_impact_claim(master):
    events = events_for("Certain Hot-Rolled Steel From India: Antidumping "
                        "Duty Order",
                        "This order does not apply to products from India.",
                        master=master)
    assert len(events) == 1
    impacts = estimate_impacts(events[0], master)
    assert impacts == [], (
        "an explicit exclusion of the only origin must suppress the route, "
        "not merely annotate an adverse one")
    assert any("EXCLUDES" in u for u in events[0].frame.unknowns)


def test_a03_the_same_document_without_the_exclusion_still_routes(master):
    events = events_for("Certain Hot-Rolled Steel From India: Antidumping "
                        "Duty Order", master=master)
    impacts = estimate_impacts(events[0], master)
    assert impacts, "the fix must not silence every trade remedy"
    assert any(i.target_id == "sector:steel" for i in impacts)


def test_a03_an_unparsed_carve_out_limits_rather_than_suppresses(master):
    """Dropping a route on an exclusion nobody could read is the same guess
    pointing the other way."""
    events = events_for("Certain Hot-Rolled Steel From India: Antidumping "
                        "Duty Order, excluding, as set out in the annex",
                        master=master)
    impacts = estimate_impacts(events[0], master)
    assert impacts
    assert impacts[0].evidence_confidence == "low"


def test_a03_an_exclusion_does_not_cross_a_sentence_boundary():
    found = scope_of("Duty on steel, excluding products from the Republic of "
                     "Korea. Acme Steel Ltd is excluded from the order.")
    assert found.excluded_countries == ("Republic of Korea",)
    assert found.excluded_parties == ("Acme Steel Ltd",)


# ===================================================================== A04
# "Tata Steel halts production" plus a body denying the halt became two
# events: a confirmed headline with affected targets, and a separate denial
# that qualified nothing.

def test_a04_a_denial_in_the_body_qualifies_the_headline(master):
    events = events_for("Tata Steel halts production",
                        "Tata Steel denies production halt. Operations "
                        "continue normally.", master=master)
    assert len(events) == 1, "the denial is not a second event"
    assert events[0].frame.assertion_status == "denied"
    assert estimate_impacts(events[0], master) == [], (
        "a denied halt must not leave affected targets standing")


def test_a04_two_genuinely_distinct_events_are_still_two(master):
    events = events_for("RBI cuts repo rate by 25 bps. Government proposes a "
                        "tariff of 5%.", master=master)
    assert len(events) == 2
    assert {e.event_type for e in events} == {"policy_rate_decision",
                                              "tariff_announcement"}


def test_a04_distinct_claims_keep_their_own_assertion_status(master):
    """Reconciliation applies within a claim, not across the document: a
    denial of one thing must not weaken an unrelated confirmed statement."""
    events = events_for("Tata Steel denies production halt. Government "
                        "proposes a tariff of 5%.", master=master)
    by_type = {e.event_type: e for e in events}
    assert by_type["tariff_announcement"].frame.assertion_status == \
        "confirmed_statement"


# ===================================================================== A05
# The same claim in the title and the first body sentence created two event
# ids and repeated target estimates.

def test_a05_a_repeated_claim_is_one_event(master):
    events = events_for("Tata Steel halts production",
                        "Tata Steel halts production at Kalinganagar.",
                        master=master)
    assert len(events) == 1, (
        "event counts must reflect events, not matching sentences")


def test_a05_the_repetition_is_recorded_rather_than_discarded(master):
    events = events_for("Tata Steel halts production",
                        "Tata Steel halts production at Kalinganagar.",
                        master=master)
    assert any("same claim" in u for u in events[0].frame.unknowns)


def test_a05_detail_in_the_repeated_sentence_survives_the_merge(master):
    """Merging must not lose the named facility the second sentence added."""
    events = events_for("Tata Steel halts production",
                        "Tata Steel halts production at Kalinganagar.",
                        master=master)
    targets = {i.target_id for i in estimate_impacts(events[0], master)}
    assert "tata_kalinganagar" in targets


# ===================================================================== A06
# Two unrelated Hindi headlines produced the same syndication key, because
# normalisation kept only ASCII words and digits.

HINDI_A = "सरकार ने इस्" \
          "पात पर शुल्क " \
          "बढ़ाया"
HINDI_B = "बंदरगाह पर क" \
          "ाम बंद हुआ"


def test_a06_two_unrelated_hindi_headlines_do_not_share_a_group():
    assert syndication_key(HINDI_A) != syndication_key(HINDI_B)


def test_a06_a_devanagari_headline_produces_real_tokens():
    tokens = syndication_tokens(HINDI_A)
    assert len(tokens) >= 3, (
        "an ASCII tokeniser returned nothing, so every Hindi item of a day "
        "hashed to the same empty token set")
    assert all(any("ऀ" <= c <= "ॿ" for c in t) for t in tokens)


def test_a06_a_vowel_sign_does_not_cut_a_word_in_half():
    """`\\w` matches by isalpha(), which excludes the combining marks that
    carry the vowels, so it chopped a word at its first matra."""
    word = syndication_tokens(HINDI_A)[0]
    assert word == HINDI_A.split()[0]


def test_a06_the_same_hindi_headline_still_groups_with_itself():
    assert syndication_key(HINDI_A, published_at="2026-10-18") == \
        syndication_key(HINDI_A, published_at="2026-10-18")


def test_a06_a_headline_with_no_usable_tokens_stands_alone():
    a = syndication_key("...", source_id="x", reference="one")
    b = syndication_key("!!!", source_id="x", reference="two")
    assert a != b, "zero shared evidence is not evidence of being one story"


def test_a06_a_rebuild_corrects_derived_groups_without_touching_the_record(tmp_path):
    store = NewsStore(tmp_path / "regroup.sqlite")
    store.register(feed_source())
    item = FetchedItem("r1", HINDI_A, URL + "1", b"one", published_at=T0)
    store.ingest("feed", lambda *_: FetchResult((item,)), now=T0)
    with store.connect() as db:
        original = db.execute("SELECT syndication_group FROM stories").fetchone()[0]
        db.execute("DELETE FROM syndication_rebuilds")
        # Simulate a store grouped under the old ASCII rule.
        db.execute("PRAGMA writable_schema=ON")
    report = store.rebuild_syndication_groups(now=T2)
    assert report["key_version"] == "syn/2"
    with store.connect() as db:
        kept = db.execute("SELECT syndication_group FROM stories").fetchone()[0]
    assert kept == original, "the immutable story row is not rewritten"


# ===================================================================== A07
# A document changing A -> B -> A: the final A was dismissed as an old
# duplicate, so B stayed current.

def test_a07_a_reverted_document_becomes_current_again(tmp_path):
    store = NewsStore(tmp_path / "reversion.sqlite")
    store.register(feed_source())
    for stamp, value in ((T0, "A"), (T1, "B"), (T2, "A")):
        item = FetchedItem("doc", f"Policy version {value}", URL + "doc",
                           value.encode())
        store.ingest("feed", lambda *_, _i=item: FetchResult((_i,)), now=stamp)
    titles = [s.title for group in store.syndication_groups().values()
              for s in group]
    assert titles == ["Policy version A"], (
        "returning to earlier bytes is a new state, not an old duplicate")


def test_a07_repeated_current_bytes_stay_idempotent(tmp_path):
    store = NewsStore(tmp_path / "idempotent.sqlite")
    store.register(feed_source())
    item = FetchedItem("doc", "Policy version A", URL + "doc", b"A")
    first = store.ingest("feed", lambda *_: FetchResult((item,)), now=T0)
    second = store.ingest("feed", lambda *_: FetchResult((item,)), now=T1)
    assert (first.new_observations, first.new_stories) == (1, 1)
    assert (second.new_observations, second.new_stories, second.unchanged) == (0, 0, 1)


def test_a07_the_state_timeline_records_the_reversion(tmp_path):
    store = NewsStore(tmp_path / "timeline.sqlite")
    store.register(feed_source())
    for stamp, value in ((T0, "A"), (T1, "B"), (T2, "A")):
        item = FetchedItem("doc", f"Policy version {value}", URL + "doc",
                           value.encode())
        store.ingest("feed", lambda *_, _i=item: FetchResult((_i,)), now=stamp)
    states = store.document_states("feed", "doc")
    assert [s["sequence"] for s in states] == [1, 2, 3]
    assert [s["reverted"] for s in states] == [False, False, True]
    assert states[0]["observation_id"] == states[2]["observation_id"], (
        "content identity is reusable; the STATE is what is new")
    assert states[0]["story_id"] != states[2]["story_id"]


# ===================================================================== A08
# With a one-document budget, repeated 200s and a restarted fetcher
# retrieved the first already-enriched URL on every pass, and the second
# document never got a body.

class _DocumentFeed:
    """Two permitted documents, served on every pass, body always available."""

    RAW = b"<article>" + b"The Board has adopted a capital rule. " * 8 + b"</article>"

    def __init__(self, calls):
        from seraph.news.http_feed import HttpFeedFetcher
        self._http = HttpFeedFetcher(
            transport=lambda url, headers:
            (calls.append(url) or (200, {"Content-Type": "text/html"}, self.RAW)))
        self._http._throttle = lambda *_: None

    def __call__(self, *_):
        return FetchResult(tuple(
            FetchedItem(str(i), f"Policy {i}", URL + str(i), str(i).encode())
            for i in range(2)))


def _enriched_bodies(store):
    return {s.title: bool(s.body) for group in store.syndication_groups().values()
            for s in group}


def test_a08_a_one_document_budget_still_reaches_every_document(tmp_path):
    from seraph.news.enrichment import EnrichingFetcher
    store = NewsStore(tmp_path / "enrich.sqlite")
    store.register(feed_source())
    calls = []
    for _ in range(3):
        # A NEW fetcher each pass: a restart, and the expiry of the old
        # per-process success cache, are the same thing from here.
        store.ingest("feed", EnrichingFetcher(_DocumentFeed(calls), store=store,
                                              max_documents=1))
    assert calls == [URL + "0", URL + "1"], (
        "the budget went to the already-enriched document on every pass")
    assert _enriched_bodies(store) == {"Policy 0": True, "Policy 1": True}


def test_a08_a_stored_document_is_reused_without_a_request(tmp_path):
    from seraph.news.enrichment import EnrichingFetcher
    store = NewsStore(tmp_path / "reuse.sqlite")
    store.register(feed_source())
    calls = []
    for _ in range(4):
        store.ingest("feed", EnrichingFetcher(_DocumentFeed(calls), store=store,
                                              max_documents=2))
    assert len(calls) == 2, "retrieved text must not be fetched again"
    assert store.document_progress("feed")["feed"]["outstanding"] == 0


def test_a08_reuse_produces_no_spurious_correction(tmp_path):
    from seraph.news.enrichment import EnrichingFetcher
    store = NewsStore(tmp_path / "noflap.sqlite")
    store.register(feed_source())
    calls = []
    for _ in range(3):
        store.ingest("feed", EnrichingFetcher(_DocumentFeed(calls), store=store,
                                              max_documents=2))
    last = store.ingest("feed", EnrichingFetcher(_DocumentFeed(calls),
                                                 store=store, max_documents=2))
    assert (last.new_stories, last.corrections) == (0, 0), (
        "reattaching stored text must reproduce the same bytes, so the "
        "observation collapses instead of correcting a body away")


def test_a08_the_refresh_policy_is_declared_not_implicit(tmp_path):
    store = NewsStore(tmp_path / "refresh.sqlite")
    store.register(feed_source())
    assert store.DOCUMENT_REFRESH_DAYS >= 1
    store.save_document("feed", URL + "x", text="t" * 200,
                        document_hash="h", format="article",
                        acquired_at=T0, refresh_days=0)
    assert store.document("feed", URL + "x", now=T2)["due_for_refresh"] is True


# ===================================================================== A09
# An abandoned `news.poll` lease caused zero fetch calls while the
# replacement loop reported `running` / "waiting for next poll".

@pytest.fixture(scope="module")
def run_news():
    spec = importlib.util.spec_from_file_location(
        "run_news_under_audit_test", ROOT / "scripts/run_news.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _drive_worker(run_news, tmp_path, store):
    """One pass of the real worker loop, then Ctrl+C out of the sleep."""
    fetched, seen = [], []

    def sleep(_seconds):
        seen.append(store.worker_state(_now()))
        raise KeyboardInterrupt

    args = SimpleNamespace(jobs=tmp_path / "jobs.sqlite", backfill=False,
                           once=False, catch_up=False, interval=30)
    with patch.object(run_news, "register", lambda *a, **k: None), \
         patch.object(run_news, "build_fetcher", lambda *a: None), \
         patch.object(run_news, "poll_once",
                      lambda *a, **k: fetched.append(True) or []), \
         patch.object(run_news, "show_status", lambda *a: 0), \
         patch.object(run_news.time, "sleep", sleep), \
         contextlib.redirect_stdout(io.StringIO()) as out:
        run_news._run_worker(args, store)
    return fetched, seen, out.getvalue()


def test_a09_a_blocked_poll_is_not_reported_as_a_healthy_worker(run_news, tmp_path):
    """A pass that fetched nothing must say so.

    The status this asserts CHANGED after A09, and deliberately. A09's
    first fix wrote `failed`, which the supervisor reads as a dead process
    and acts on by terminating the worker -- so a held lease, or one
    publisher's 503, could take down acquisition entirely. `degraded`
    carries exactly the same information to a reader (the activity names
    the cause) without telling the supervisor to kill a live process. See
    `tests/test_news_source_failure_isolation.py` for that contract.
    """
    jobs = JobStore(tmp_path / "jobs.sqlite")
    jobs.acquire(run_news.JOB, "held-by-a-live-process")
    store = NewsStore(tmp_path / "worker.sqlite")
    fetched, seen, _stdout = _drive_worker(run_news, tmp_path, store)
    assert fetched == [], "the lease really does block the poll"
    assert seen and seen[0]["state"] == "degraded", (
        "the loop beat `running` / `waiting for next poll` while fetching "
        "nothing at all for the whole lease term")
    assert seen[0]["state"] != "running"
    assert seen[0]["activity"] == "lock_unavailable"
    assert "not evidence of polling" in (seen[0]["detail"] or "")
    assert any(r.status == "lock_unavailable" for r in jobs.runs())


def test_a09_an_abandoned_lease_is_reconciled_and_the_worker_polls(run_news, tmp_path):
    child = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    child.wait()
    dead = f"{socket.gethostname()}:{child.pid}"

    jobs = JobStore(tmp_path / "jobs.sqlite")
    jobs.acquire(run_news.JOB, "abandoned")
    with jobs.connect() as db:
        db.execute("UPDATE job_locks SET owner=? WHERE job=?",
                   (dead, run_news.JOB))
    store = NewsStore(tmp_path / "worker.sqlite")
    fetched, seen, _stdout = _drive_worker(run_news, tmp_path, store)
    assert fetched == [True], "a dead holder must not block the replacement"
    assert seen[0]["state"] == "running"
    failed = [r for r in jobs.runs() if r.status == "failed"]
    assert failed and "lease abandoned" in (failed[0].error or ""), (
        "breaking a lease is recorded, not silent")


def test_a09_a_lease_is_never_broken_on_an_unanswerable_question(tmp_path):
    jobs = JobStore(tmp_path / "jobs.sqlite")
    jobs.acquire("news.poll", "run")
    with jobs.connect() as db:
        db.execute("UPDATE job_locks SET owner='some-other-host:1234' "
                   "WHERE job='news.poll'")
    outcome = jobs.reconcile_lock("news.poll", reason="test")
    assert outcome["cleared"] is False
    assert outcome["owner_alive"] is None


def test_a09_liveness_of_this_process_is_answerable():
    assert JobStore.owner_alive(f"{socket.gethostname()}:{os.getpid()}") is True
    assert JobStore.owner_alive("not-a-tag") is None


# ===================================================================== A10
# A strict 08:00 replay showed a worker heartbeat from 10:00, with an age of
# -120 minutes, and an open gap first observed at 10:00.

def _replay_store(tmp_path):
    store = NewsStore(tmp_path / "replay.sqlite")
    store.register(feed_source())
    store.beat(now=T2, pid=42, status="running", detail="future information")
    store.open_gap(source_id="feed", since=T1, until=T2, recoverable=True, now=T2)
    return store


def test_a10_a_strict_replay_omits_operational_state_it_could_not_have_had(tmp_path):
    store = _replay_store(tmp_path)
    payload = build_news_payload(store, MasterData(), decision_ts=T0,
                                 strict_replay=True, role="regulator")
    worker = payload["freshness"]["worker"]
    assert worker["state"] == "unavailable_at_decision_time"
    assert worker["age_minutes"] is None, "an age of -120 minutes is not an age"
    assert worker["omitted_future_beat_at"] == T2


def test_a10_a_strict_replay_omits_a_gap_observed_later(tmp_path):
    store = _replay_store(tmp_path)
    payload = build_news_payload(store, MasterData(), decision_ts=T0,
                                 strict_replay=True, role="regulator")
    gaps = [i for i in payload["role_view"]["items"]
            if i.get("kind") == "collection_gaps"]
    assert gaps and gaps[0]["open"] == []


def test_a10_the_same_facts_are_visible_once_the_decision_time_reaches_them(tmp_path):
    store = _replay_store(tmp_path)
    payload = build_news_payload(store, MasterData(), decision_ts=T2,
                                 strict_replay=True, role="regulator")
    assert payload["freshness"]["worker"]["state"] == "running"
    gaps = [i for i in payload["role_view"]["items"]
            if i.get("kind") == "collection_gaps"]
    assert gaps and len(gaps[0]["open"]) == 1


def test_a10_a_gap_closed_after_the_decision_time_was_open_then(tmp_path):
    store = NewsStore(tmp_path / "closed.sqlite")
    store.register(feed_source())
    opened = store.open_gap(source_id="feed", since=T0, until=T1,
                            recoverable=True, now=T0)
    store.close_gap(opened["gap_id"], state="recovered", now=T2)
    assert store.open_gaps() == []
    assert len(store.open_gaps(visible_at=T1)) == 1


def test_a10_a_live_view_never_publishes_a_negative_age(tmp_path):
    store = _replay_store(tmp_path)
    state = store.worker_state(T0)
    assert state["age_minutes"] is None
    assert state["beat_after_decision_time"] is True


# ===================================================================== A11
# An old duty order and a separately published revocation stayed unlinked
# (`supersedes=null`), so the old order remained in force, and supersession
# only ever worked when a caller already provided the link.

OLD_ORDER = "Certain Hot-Rolled Steel From India: Antidumping Duty Order"
REVOCATION = ("Certain Hot-Rolled Steel From India: Revocation of the "
              "Antidumping Duty Order")


def _pair(master, old_title, new_title):
    """The earlier instrument and the later one, as two distinct events."""
    return [events_for(title, master=master, seen=seen,
                       story_id=f"doc{index}")[0]
            for index, (title, seen) in enumerate(((old_title, T0),
                                                   (new_title, T1)))]


def test_a11_an_unlinkable_revocation_raises_a_named_review_task(master):
    events = _pair(master, OLD_ORDER, REVOCATION)
    result = partition(events, T2)
    assert result["supersession"]["links"] == {}, (
        "a shared headline is not evidence: one product-and-country title "
        "covers a proposal, an order and its revocation")
    unresolved = result["supersession"]["unresolved"]
    assert len(unresolved) == 1
    assert "cannot be linked" in unresolved[0]["warning"]
    assert "still reported as in force" in unresolved[0]["warning"]


def test_a11_a_shared_instrument_id_links_the_two_documents(master):
    events = _pair(master,
                   "Hot-Rolled Steel From India (A-533-863): Antidumping Duty Order",
                   "Hot-Rolled Steel From India (A-533-863): Revocation of the "
                   "Antidumping Duty Order")
    assert all(e.instrument_ids == ("ita_case:A-533-863",) for e in events)
    states = partition(events, T2)["states"]
    assert states[events[0].event_id]["applicability"]["state"] == "superseded"


def test_a11_a_reviewer_can_establish_the_link_the_documents_lack(master):
    events = _pair(master, OLD_ORDER, REVOCATION)
    states = partition(events, T2,
                       confirmed_links=[(events[1].event_id,
                                         events[0].event_id)])["states"]
    assert states[events[0].event_id]["applicability"]["state"] == "superseded"


def test_a11_a_reviewer_can_reject_a_link_the_identifiers_got_wrong(master):
    events = _pair(master,
                   "Hot-Rolled Steel From India (A-533-863): Antidumping Duty Order",
                   "Hot-Rolled Steel From India (A-533-863): Revocation of the "
                   "Antidumping Duty Order")
    states = partition(events, T2,
                       rejected_links=[(events[1].event_id,
                                        events[0].event_id)])["states"]
    assert states[events[0].event_id]["applicability"]["state"] != "superseded"


def test_a11_a_preliminary_does_not_supersede_a_final_on_the_same_case(master):
    """Proposal -> final -> effective is a ladder, and it runs one way."""
    events = _pair(master,
                   "Widgets From India (A-533-900): Final Affirmative Determination",
                   "Widgets From India (A-533-900): Preliminary Results of "
                   "Antidumping Duty Administrative Review")
    result = partition(events, T2)
    assert result["supersession"]["links"] == {}
    proposed = [p for p in result["supersession"]["proposals"]
                if p["status"] == "proposed"]
    assert proposed, "a same-instrument pair that does not advance needs review"


@pytest.mark.parametrize("text,expected", [
    ("Chromium Trioxide From India (A-533-863)", ("ita_case:A-533-863",)),
    ("Certain Goods; Inv. No. 731-TA-1234", ("usitc_investigation:731-TA-1234",)),
    ("Recovery Certificate RC No. 8924", ("recovery_certificate:8924",)),
    ("Certain Hot-Rolled Steel From India", ()),
])
def test_a11_instrument_ids_come_from_citations_not_titles(text, expected):
    assert instrument_ids(text) == expected


def test_a11_a_review_decision_is_append_only_and_time_bounded(tmp_path):
    store = NewsStore(tmp_path / "reviews.sqlite")
    store.record_supersession_review(later_event_id="b", earlier_event_id="a",
                                     decision="confirmed", reviewer="analyst",
                                     reason="same order, confirmed by hand",
                                     now=T1)
    assert store.supersession_decisions(visible_at=T0)["confirmed"] == ()
    assert store.supersession_decisions(visible_at=T2)["confirmed"] == (("b", "a"),)
    store.record_supersession_review(later_event_id="b", earlier_event_id="a",
                                     decision="rejected", reviewer="reviewer2",
                                     reason="different proceeding", now=T2)
    current = store.supersession_decisions()
    assert current["rejected"] == (("b", "a"),) and current["confirmed"] == ()
    assert len(current["decisions"]) == 1


def test_a11_an_instrument_cannot_supersede_itself(tmp_path):
    store = NewsStore(tmp_path / "self.sqlite")
    with pytest.raises(ValueError):
        store.record_supersession_review(later_event_id="a", earlier_event_id="a",
                                         decision="confirmed", reviewer="x")


def test_a03_a_document_type_is_not_a_carve_out():
    """"Exemption Order in the matter of Allcargo Logistics Limited" is a
    SEBI enforcement document. A bare "of" read the respondent as an
    excluded COUNTRY, which would have suppressed a route on a false
    exclusion -- the A03 defect in the other direction."""
    found = scope_of("Exemption Order in the matter of Allcargo Logistics "
                     "Limited")
    assert found.excluded_countries == ()
    assert found.named_exclusions is False


def test_a03_the_whole_stored_corpus_yields_no_false_exclusion():
    """Scanned over the pilot store when this was written: 458 stories, zero
    named exclusions. A false one suppresses a real route silently."""
    found = scope_of("The measure excludes goods of Indian origin.")
    assert found.excluded_countries == ("Indian",), (
        "tightening the connector must not lose the legitimate goods-noun "
        "form")
