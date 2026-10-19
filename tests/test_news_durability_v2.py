"""C13 NI06/07 atomic ingestion, historic health, cadence and corrections."""
import pytest
from seraph.news.acquisition import NewsStore, FetchResult, FetchedItem
from seraph.news.model import Source
from seraph.dashboard.news_view import news_channel
from seraph.news.registry import MasterData

A='2026-10-17T09:00:00+05:30'
B='2026-10-17T10:00:00+05:30'

@pytest.fixture
def store(tmp_path):
    db=NewsStore(tmp_path/'news.sqlite')
    db.register(Source('feed','Official','official_policy','https://example.org',(),poll_interval_minutes=60,max_retries=1))
    return db

def item(title='RBI cuts repo rate by 25 bps',ref='one'):
    return FetchedItem(ref,title,'https://example.org/'+ref,title.encode())

def test_health_history_not_mutable_current(store):
    store.ingest('feed',lambda *_:FetchResult((item(),)),now=A)
    def fail(*_):raise RuntimeError('offline')
    store.ingest('feed',fail,now=B)
    assert store.coverage_at(A).covered==1
    assert store.coverage_at(B).covered==0
    assert NewsStore(store.path).health_at('feed',A).status=='healthy'

def test_due_times_survive_restart(store):
    store.ingest('feed',lambda *_:FetchResult((item(),)),now=A)
    assert NewsStore(store.path).due_sources('2026-10-17T09:59:00+05:30')==[]
    assert len(store.due_sources(B))==1

def test_batch_rollback_has_no_partial_document_or_cursor(store):
    bad=FetchedItem('bad',None,'https://example.org/bad',b'bad')
    with pytest.raises(Exception):
        store.ingest('feed',lambda *_:FetchResult((item(),bad),cursor='new'),now=A)
    assert store.stories()==[]
    assert store.health('feed').cursor is None

def test_correction_preserves_history_and_replaces_current(store):
    store.ingest('feed',lambda *_:FetchResult((item(),)),now=A)
    store.ingest('feed',lambda *_:FetchResult((item('RBI holds repo rate unchanged'),)),now=B)
    assert len(store.stories())==2
    assert list(store.syndication_groups(visible_at=A).values())[0][0].title.startswith('RBI cuts')
    current=list(store.syndication_groups(visible_at=B).values())
    assert len(current)==1 and current[0][0].title.endswith('unchanged')

def test_latest_before_pagination(store):
    store.ingest('feed',lambda *_:FetchResult(tuple(item(f'RBI releases bulletin {i}',str(i)) for i in range(45))),now=A)
    store.ingest('feed',lambda *_:FetchResult((item('RBI cuts repo rate by 25 bps','new'),)),now=B)
    channel=news_channel(store,MasterData(),decision_ts=B,limit=10)
    assert channel['events'][0].headline.startswith('RBI cuts')
    assert channel['pagination']['total']==46
    assert channel['pagination']['displayed']==10
    assert channel['pagination']['next_offset']==10


def test_aggregates_cover_every_eligible_event_not_just_the_page(store):
    """The signal rail is paginated. The sector panel and the globe are not.

    This replaces an earlier assertion that estimates were a SUBSET of the
    displayed page. That is what the code did, and it was the defect: on the
    pilot store (181 eligible events, 40 per page) the documented
    Kalinganagar -> sector:steel exposure vanished from the sector panel
    entirely, which reads as "steel has no documented exposure" rather than
    "you are looking at page 1 of 5".
    """
    store.ingest('feed',lambda *_:FetchResult(tuple(item(f'RBI releases bulletin {i}',str(i)) for i in range(45))),now=A)
    store.ingest('feed',lambda *_:FetchResult((item('RBI cuts repo rate by 25 bps','new'),)),now=B)
    channel=news_channel(store,MasterData(),decision_ts=B,limit=10)
    assert len(channel['events'])==10, 'the rail is still paginated'
    assert len(channel['eligible_events'])==46, 'the aggregates see everything'
    assert channel['pagination']['aggregates_cover']==46
    covered={e.event_id for e in channel['eligible_events']}
    assert {e.event_id for e in channel['estimates']} <= covered


def test_a_sector_impact_survives_falling_off_the_first_page(store):
    """The exact shape of the pilot defect, in miniature."""
    store.ingest('feed',lambda *_:FetchResult((item('RBI cuts repo rate by 25 bps','old'),)),now=A)
    store.ingest('feed',lambda *_:FetchResult(tuple(item(f'RBI releases bulletin {i}',str(i)) for i in range(20))),now=B)
    wide=news_channel(store,MasterData(),decision_ts=B,limit=100)
    narrow=news_channel(store,MasterData(),decision_ts=B,limit=2)
    assert len(narrow['events'])==2 and len(wide['events'])==21
    assert {e.estimate_id for e in narrow['estimates']}=={e.estimate_id for e in wide['estimates']}
