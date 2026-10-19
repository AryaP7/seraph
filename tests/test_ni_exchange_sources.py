"""Indian exchange filings — the coverage gap, and the claim not to overreach.

Indian issuer announcements were absent entirely, which is the single largest
coverage gap in a system about Indian market risk. Six endpoints were probed
live and registered; six others answered 403, 502, an SSL failure or something
that is not a feed, and are recorded as uncovered rather than dropped.

The interesting problem is what an NSE announcement actually says. Its RSS
title is the **filing entity and nothing else** — "JSW Steel Limited" — and
the subject lives in the body, which is not retained because the feed's terms
have not been read.

So the honest reading is narrow and worth stating: *an announcement exists,
filed by this issuer, and we do not know what it says.* That resolves to a
named entity and produces **no impact and no direction**. Turning "JSW Steel
filed something" into "adverse for steel" would be invention, and it is the
most tempting invention available here.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from seraph.news.estimation import estimate_impacts
from seraph.news.extraction import extract_events
from seraph.news.model import Story, Timing
from seraph.news.registry import load_master_data

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEEN = "2026-10-18T09:00:00+05:30"

_SPEC = importlib.util.spec_from_file_location(
    "run_news_sources_under_test", ROOT / "scripts/run_news.py")
_RN = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RN)


def filing(title: str, *, is_filing_feed: bool = True):
    master, _ = load_master_data()
    story = Story(story_id="s", source_id="nse_corporate_announcements",
                  observation_id="o", title=title, url="https://x.invalid/1",
                  body=None, timing=Timing(first_seen_at=SEEN),
                  syndication_group="g",
                  metadata={"title_is_filing_entity": is_filing_feed})
    event = list(extract_events([story], master))[0].event
    return event, master


# ------------------------------------------------- the sources themselves

def test_the_exchange_sources_are_registered():
    """Indian issuer announcements were the largest single coverage gap."""
    ids = {s.source_id for s in _RN.EXCHANGE_AND_POLICY_SOURCES}
    assert {"nse_corporate_announcements", "bse_notices"} <= ids


def test_every_new_source_withholds_full_text_until_terms_are_read():
    """The DR-10 default, not relaxed on the assumption that a public feed is
    a licensed one."""
    for source in _RN.EXCHANGE_AND_POLICY_SOURCES:
        if source.source_id == 'federalreserve_speeches':
            assert source.may_store_full_text
            assert 'https://www.federalreserve.gov/disclaimer.htm' in source.rights
            assert 'Third-party' in source.rights
            continue
        assert source.may_store_full_text is False, source.source_id
        assert source.rights.strip(), source.source_id


def test_every_new_source_was_actually_probed():
    for source in _RN.EXCHANGE_AND_POLICY_SOURCES:
        assert source.accessibility_verified is True, source.source_id


def test_unreachable_candidates_are_recorded_with_their_reason():
    """A gap nobody wrote down becomes a gap nobody remembers. "We have no
    coverage of Indian trade instruments" is a fact about this system."""
    recorded = {sid: why for sid, _url, why in _RN.UNAVAILABLE_SOURCES}
    assert "dgft_notifications" in recorded
    assert "403" in recorded["dgft_notifications"]
    assert "UNCOVERED" in recorded["dgft_notifications"]
    for why in recorded.values():
        assert "UNCOVERED" in why, "a failure that does not name what is lost"


def test_ssl_verification_is_not_disabled_to_reach_a_source():
    """Three Indian government endpoints fail certificate verification.
    Turning verification off would be bypassing a security control to gain
    coverage, which is not a trade this system may make."""
    recorded = dict((sid, why) for sid, _u, why in _RN.UNAVAILABLE_SOURCES)
    assert "NOT disabled" in recorded["cbic_whats_new"]
    for module in ("seraph/news/http_feed.py", "seraph/news/json_feed.py"):
        text = (ROOT / module).read_text(encoding="utf-8")
        assert "_create_unverified_context" not in text
        assert "CERT_NONE" not in text


def test_two_exchanges_reporting_one_filing_is_not_corroboration():
    """BSE and NSE both carry dually listed issuers. Counting that as two
    independent sources would turn one fact into two."""
    bse = next(s for s in _RN.EXCHANGE_AND_POLICY_SOURCES
               if s.source_id == "bse_notices")
    assert "NOT independent corroboration" in bse.notes


# --------------------------------- the filing entity, and nothing more

@pytest.mark.parametrize("title,entity", [
    ("JSW Steel Limited", "jsw_steel"),
    ("Vedanta Limited", "vedanta"),
    ("Oil India Limited", "oil_india"),
])
def test_an_exchange_filing_resolves_to_its_filing_entity(title, entity):
    """The feed's contract is that the title IS the filing entity."""
    event, _ = filing(title)
    assert entity in event.actors


def test_the_same_name_in_ordinary_prose_is_not_a_filing():
    """Otherwise any article mentioning a company becomes a filing by it."""
    event, _ = filing("JSW Steel Limited", is_filing_feed=False)
    assert event.actors == ()


def test_an_announcement_of_unknown_subject_produces_no_impact():
    """The most tempting invention available here. We know an announcement
    exists; we do not know what it says, and the body is not retained."""
    event, master = filing("JSW Steel Limited")
    assert estimate_impacts(event, master) == []


def test_an_announcement_of_unknown_subject_carries_no_direction():
    from seraph.news.estimation import direction_of
    event, _ = filing("JSW Steel Limited")
    assert direction_of(event) == "ambiguous"


# ------------------------------------------- the curated issuers

def test_the_registry_holds_the_issuers_the_feed_named():
    master, report = load_master_data()
    assert report.get("errors") == []
    for entity_id in ("jsw_steel", "vedanta", "oil_india", "sbi_cards",
                      "cyient", "railtel"):
        assert entity_id in master.entities


def test_an_issuer_whose_business_is_not_established_has_no_sector():
    """A wrong issuer-to-sector link puts a news event on somebody else's
    balance sheet. A small cap I cannot establish from the feed gets no
    sector rather than a plausible guess."""
    master, _ = load_master_data()
    for entity_id in ("ltm_limited", "jay_jalaram_technologies",
                      "master_components"):
        assert master.entities[entity_id].sector in (None, "")


def test_every_curated_issuer_cites_the_feed_that_named_it():
    master, _ = load_master_data()
    for entity_id in ("jsw_steel", "vedanta"):
        assert master.entities[entity_id].source, entity_id


def test_funds_are_not_registered_as_issuers():
    """An ETF announcement is a fund notice, not an issuer event."""
    curator = (ROOT / "scripts/curate_nse_issuers.py").read_text(encoding="utf-8")
    assert "Quantum Gold ETF" in curator
    assert "not an operating company" in curator
    master, _ = load_master_data()
    assert not any("etf" in e.lower() for e in master.entities)
