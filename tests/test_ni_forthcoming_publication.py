"""A forthcoming official publication — the case the replay-bound invariant
refused, which took the whole news channel down on real data.

The Federal Register places documents on public inspection and assigns them a
scheduled publication date, normally one to three business days ahead. So a
document SERAPH legitimately holds on 17 October carries `published_at` of
19 October. `Timing.__post_init__` rejected that outright:

    ValueError: first_seen_at 2026-10-17T21:47:26+05:30 precedes published_at
    2026-10-19T00:00:00+05:30: a source cannot be read before it publishes

One ordinary poll brought in 40 such documents, and from then on *every* read
of the store raised — the signal rail, the sector panel and the globe all
stopped. 44 rows in the pilot store are of this kind.

The guard is still worth having, because the dangerous direction is a
back-filled `first_seen_at`: hindsight dressed up as information the system
held. These tests pin both halves — the legitimate case is representable and
labelled, and the error case still raises.

The distinction is only available at acquisition, where `first_seen_at` is the
current instant and a later `published_at` can therefore only be a future
date. At read time the two are indistinguishable, so the flag is recorded on
the row rather than re-derived.
"""
from __future__ import annotations

import pytest

from seraph.news.acquisition import FetchedItem, FetchResult, NewsStore
from seraph.news.extraction import extract_events
from seraph.news.model import Place, Source, Story, Timing
from seraph.news.registry import MasterData

SEEN = "2026-10-17T21:47:26+05:30"
SCHEDULED = "2026-10-19T00:00:00+05:30"
PAST = "2026-10-16T09:00:00+05:30"


# --------------------------------------------------------- the type itself

def test_a_scheduled_publication_is_constructible():
    timing = Timing(first_seen_at=SEEN, published_at=SCHEDULED,
                    publication_scheduled=True)
    assert timing.published_at == SCHEDULED


def test_an_unflagged_future_publication_still_raises():
    """The guard's real target is a back-filled first_seen_at, which makes
    hindsight look like information the system had. Allowing every future
    publication date would retire that check silently."""
    with pytest.raises(ValueError, match="cannot be read before it publishes"):
        Timing(first_seen_at=SEEN, published_at=SCHEDULED)


def test_the_ordinary_case_is_unaffected():
    timing = Timing(first_seen_at=SEEN, published_at=PAST)
    assert timing.publication_scheduled is False
    assert timing.is_forthcoming(SEEN) is False


def test_a_forthcoming_document_is_still_visible_now():
    """It is knowable: we are holding it. Replay is bounded by first_seen_at,
    so a scheduled publication date withholds nothing."""
    timing = Timing(first_seen_at=SEEN, published_at=SCHEDULED,
                    publication_scheduled=True)
    assert timing.visible_at(SEEN) is True
    assert timing.visible_at("2026-10-17T21:47:25+05:30") is False


def test_is_forthcoming_reports_the_schedule():
    timing = Timing(first_seen_at=SEEN, published_at=SCHEDULED,
                    publication_scheduled=True)
    assert timing.is_forthcoming(SEEN) is True
    assert timing.is_forthcoming("2026-10-20T00:00:00+05:30") is False


def test_describe_carries_the_flag():
    """Nothing downstream should have to guess whether a date has passed."""
    described = Timing(first_seen_at=SEEN, published_at=SCHEDULED,
                       publication_scheduled=True).describe()
    assert described["publication_scheduled"] is True
    assert "publication_scheduled" not in Timing(
        first_seen_at=SEEN, published_at=PAST).describe()


# ------------------------------------------- the store decides and records

def source() -> Source:
    return Source(
        source_id="federal_register", provider="Office of the Federal Register",
        kind="regulator", url="https://example.invalid/feed",
        topic_coverage=("trade_remedies",), language="en",
        rights="public government feed; redistribution terms NOT reviewed",
        may_store_full_text=False, accessibility_verified=True,
        poll_interval_minutes=360)


def fetcher_for(published_at):
    """A fetcher returning one item whose publication date is ahead of the
    poll, which is what the Federal Register feed routinely hands over."""
    def fetch(src, cursor=None):
        return FetchResult(items=(FetchedItem(
            reference="fr-1", title="Widgets From India; Determinations",
            url="https://example.invalid/fr-1", raw=b"<rss/>",
            published_at=published_at, body=None, language="en"),))
    return fetch


@pytest.fixture
def store(tmp_path):
    db = NewsStore(tmp_path / "forthcoming.sqlite")
    db.register(source())
    return db


def test_the_store_marks_a_future_publication_as_scheduled(store):
    """At acquisition `first_seen_at` is the current instant, so a later
    publication date can only be in the future. That is the one moment the
    determination can honestly be made."""
    store.ingest("federal_register", fetcher_for("2099-01-01T00:00:00+05:30"))
    stories = store.stories()
    assert len(stories) == 1
    assert stories[0].timing.publication_scheduled is True


def test_the_store_does_not_mark_an_ordinary_publication(store):
    store.ingest("federal_register", fetcher_for(PAST))
    assert store.stories()[0].timing.publication_scheduled is False


def test_a_forthcoming_story_survives_a_round_trip(store):
    """The failure was not at write time — it was every read afterwards."""
    store.ingest("federal_register", fetcher_for("2099-01-01T00:00:00+05:30"))
    reread = NewsStore(store.path).stories()        # a fresh reader
    assert reread[0].timing.publication_scheduled is True
    assert reread[0].timing.is_forthcoming("2026-10-17T00:00:00+05:30") is True


def test_syndication_groups_read_a_forthcoming_story(store):
    """`syndication_groups` is what the news channel calls first, and it was
    the exact line that raised.

    The cutoff is taken from the story the store actually recorded, not
    written as a literal. An earlier version of this test hardcoded
    `2026-10-18T00:00:00+05:30`, which was comfortably in the future when it
    was written and went stale the moment the date rolled over — the story's
    `first_seen_at` is "now" at ingest, so it sorted *after* the cutoff and
    the query returned nothing. A test that asserts a store behaviour must
    not also depend on the wall clock.
    """
    store.ingest("federal_register", fetcher_for("2099-01-01T00:00:00+05:30"))
    recorded = store.stories()
    assert len(recorded) == 1, "nothing was ingested, so nothing is being read"
    seen_at = recorded[0].first_seen_at

    # `visible_at` filters on first_seen_at with <=, so the story's own
    # acquisition time is the tightest cutoff that must still include it.
    groups = store.syndication_groups(visible_at=seen_at)
    assert len(groups) == 1
    (stories,) = groups.values()
    assert stories[0].timing.publication_scheduled is True

    # And it is correctly withheld from a decision time before it arrived.
    assert store.syndication_groups(visible_at="2020-01-01T00:00:00+05:30") == {}


# ------------------------------------------------- the flag reaches the UI

def registry() -> MasterData:
    data = MasterData()
    data.add_place(Place("in", "India", "country", iso_code="IND",
                         lat=22.0, lon=79.0))
    return data


def test_an_event_built_from_a_forthcoming_story_carries_the_flag():
    """Dropping it here made the event unconstructible even after the store
    was fixed, because extraction rebuilds Timing from the primary story."""
    story = Story(story_id="s1", source_id="federal_register",
                  observation_id="o1",
                  title="Widgets From India; Determinations",
                  url="https://example.invalid/1", body=None,
                  timing=Timing(first_seen_at=SEEN, published_at=SCHEDULED,
                                publication_scheduled=True),
                  syndication_group="g1")
    results = list(extract_events([story], registry()))
    assert results and results[0].event is not None
    timing = results[0].event.timing
    assert timing.publication_scheduled is True
    assert timing.is_forthcoming(SEEN) is True
