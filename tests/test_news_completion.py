"""News completion regressions: exercise real boundaries and crash states."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import importlib.util
from pathlib import Path
import subprocess

import pytest
from seraph.news.acquisition import NewsStore, FetchedItem, FetchResult
from seraph.news.model import Source
from seraph.news.roles import retail_view
from seraph.news.registry import MasterData
from seraph.news.model import Event, Place
from seraph.news.currency import partition
from seraph.product_types import Timing
from seraph.decision_support.portfolio import portfolio_overlay
from seraph.dashboard.news_view import _role_projection
from seraph.news.worker_lock import worker_lock, WorkerAlreadyRunning

T0 = '2026-10-18T08:00:00+05:30'
LATER = '2026-10-18T09:00:00+05:30'


def test_real_portfolio_contract_reaches_news():
    overlay = portfolio_overlay([dict(symbol='UNKNOWN', sector='steel', value=100)], {}).value
    result = _role_projection({}, MasterData(), 'retail', overlay, None)
    assert result['items'][0]['holding'] == 'UNKNOWN'
    assert result['items'][0]['sector'] == 'sector:steel'
    assert result['items'][0]['portfolio_weight_pct'] == 100
    assert not result['items'][0]['documented']
    assert result['notes'][0].startswith('0 holding(s) have a documented route')


def test_real_portfolio_default_sector_is_unmapped():
    overlay = portfolio_overlay([dict(symbol='UNKNOWN', value=100)], {}).value
    result = _role_projection({}, MasterData(), 'retail', overlay, None)
    assert not result['items']
    assert result['uncovered'][0]['holding'] == 'UNKNOWN'


def test_existing_sector_fallback_and_no_duplicate_routes():
    entity = SimpleNamespace(entity_id='firm', sector=None)
    master = SimpleNamespace(entities={'firm': entity})
    estimate = SimpleNamespace(event_id='event', target_id='firm', mechanism='operation', direction='adverse')
    view = retail_view({'estimates': [estimate]}, master,
                       [dict(entity_id='firm', sector='sector:steel')])
    assert len(view.items[0]['touching']) == 1
    assert view.items[0]['sector'] == 'sector:steel'


def test_crashed_request_reclaimed_and_old_completion_fenced(tmp_path):
    store = NewsStore(tmp_path/'news.sqlite')
    asked = store.request_acquisition(now=T0)
    first = store.claim_acquisition(worker='first', now=T0)
    restarted = NewsStore(store.path)
    assert restarted.request_acquisition(now=LATER)['request_id'] == asked['request_id']
    second = restarted.claim_acquisition(worker='second', now=LATER)
    assert second['claim_token'] != first['claim_token']
    assert not store.finish_acquisition(asked['request_id'], claim_token=first['claim_token'], progress={}, now=LATER)
    assert restarted.finish_acquisition(asked['request_id'], claim_token=second['claim_token'], progress={'ok': True}, now=LATER)
    assert restarted.acquisition_progress()['state'] == 'done'


def test_simultaneous_refreshes_coalesce(tmp_path):
    store = NewsStore(tmp_path/'news.sqlite')
    with ThreadPoolExecutor(8) as pool:
        asks = list(pool.map(lambda _: store.request_acquisition(now=T0), range(16)))
    assert len({a['request_id'] for a in asks}) == 1


def test_same_second_corrections_form_one_current_revision(tmp_path):
    store = NewsStore(tmp_path/'news.sqlite')
    store.register(Source('feed', 'Feed', 'official_policy', 'https://example.invalid',
                          ('policy',), accessibility_verified=True))
    for index in range(3):
        item = FetchedItem('same-document', f'Policy version {index}',
                           'https://example.invalid/doc', str(index).encode())
        store.ingest('feed', lambda *_: FetchResult((item,)), now=T0)
    current = [s for group in store.syndication_groups().values() for s in group]
    assert [s.title for s in current] == ['Policy version 2']
    assert len(store.stories()) == 3


def test_worker_lock_excludes_second_owner_then_releases(tmp_path):
    path = tmp_path/'news.sqlite'
    with worker_lock(path):
        with pytest.raises(WorkerAlreadyRunning):
            with worker_lock(path):
                pytest.fail('two owners')
    with worker_lock(path):
        pass


def test_strict_replay_does_not_admit_undated_place():
    master = MasterData(places=[Place('p', 'Place', 'city')])
    assert 'p' in master.as_of(T0).places
    strict = master.as_of(T0, strict=True)
    assert not strict.places
    assert strict.temporal_assumptions['excluded_unknown_dates'] == {'places': 1}
    assert strict.temporal_assumptions['total'] == 0


def test_actual_partition_applies_only_available_supersession():
    old = Event('old', 'other', 'old', Timing(first_seen_at=T0), ('a',))
    new = replace(old, event_id='new', supersedes='old', timing=Timing(first_seen_at=LATER))
    assert [e.event_id for e in partition([old, new], T0)['current']] == ['old']
    result = partition([old, new], LATER)
    assert [e.event_id for e in result['current']] == ['new']
    assert result['states']['old']['band'] == 'superseded'


def test_supervisor_terminates_hung_child_before_restart(tmp_path):
    path = Path(__file__).resolve().parents[1]/'scripts/news_supervisor.py'
    spec = importlib.util.spec_from_file_location('completion_supervisor', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actions = []

    class Child:
        pid = 4242
        stopped = False
        def wait(self, timeout=None):
            if self.stopped:
                return 1
            raise subprocess.TimeoutExpired('worker', timeout)
        def send_signal(self, signal):
            actions.append('terminated')
            self.stopped = True
        def poll(self):
            return 1 if self.stopped else None

    result = module.supervise(tmp_path/'news.sqlite', interval=30, max_restarts=0,
                              once=False, spawn=lambda *a, **kw: Child(),
                              sleep=lambda _: None, startup_grace=0)
    assert actions == ['terminated']
    assert result == 1
    assert NewsStore(tmp_path/'news.sqlite').worker_state(LATER)['state'] == 'failed'
