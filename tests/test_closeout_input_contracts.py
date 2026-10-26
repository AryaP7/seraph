"""F02/F08 — bounded calendar admission and observed macro alignment."""
from datetime import date, timedelta
import hashlib

import numpy as np
import pytest

from seraph.live.clock import MarketClock
from seraph.market_calendar.exchange import ExchangeCalendar
from seraph.pillars.hamilton.covariates import align_observed


def test_configured_feed_resolves_login_source_but_replay_does_not(monkeypatch, tmp_path):
    from seraph.ingestion import kite_client
    from seraph.live.feed import resolve_feed, KiteTickerFeed, ReplayFeed
    env = tmp_path/'env'
    env.write_text('KITE_API_KEY=synthetic-contract-key\n')
    monkeypatch.setattr(kite_client, 'ENV_FILE', env)
    monkeypatch.delenv('KITE_API_KEY', raising=False)
    replay=ReplayFeed([])
    assert resolve_feed(allow_replay=replay,use_env_file=True) is replay
    import os
    assert 'KITE_API_KEY' not in os.environ
    assert isinstance(resolve_feed(use_env_file=True),KiteTickerFeed)


def test_broker_rejection_is_named_sanitized_and_can_recover(monkeypatch):
    from types import SimpleNamespace
    import sys
    from seraph.ingestion import kite_client
    from seraph.live.feed import KiteTickerFeed
    from seraph.live.lifecycle import SessionLifecycle
    from scripts.run_live import update_feed_lifecycle

    class Ticker:
        MODE_FULL = 'full'
        connected = False
        def __init__(self, *_): pass
        def connect(self, **_): pass
        def is_connected(self): return self.connected
        def subscribe(self, _): pass
        def set_mode(self, *_): pass

    monkeypatch.setitem(sys.modules, 'kiteconnect', SimpleNamespace(KiteTicker=Ticker))
    monkeypatch.setattr(kite_client, 'KiteClient', lambda **_: SimpleNamespace(
        instruments_nse=lambda: {'TEST': 1}))
    feed=KiteTickerFeed(api_key='synthetic-key',access_token='synthetic-token')
    feed.connect(['TEST'])
    feed._ticker.on_error(None,1006,'HTTP 403 https://invalid/?access_token=do-not-display')
    feed._ticker.on_close(None,1006,'connection lost')
    health=feed.health()
    assert not health.connected and '403' in health.detail and 'kite_login.py' in health.detail
    assert 'do-not-display' not in health.detail and 'https://' not in health.detail
    lc=SessionLifecycle(); lc.to('warming_up'); lc.to('connecting')
    update_feed_lifecycle(lc,health.describe())
    assert lc.state=='degraded' and not lc.may_publish
    feed._ticker.connected=True
    feed._ticker.on_connect(feed._ticker,None)
    update_feed_lifecycle(lc,feed.health().describe())
    assert lc.state=='waiting_session' and '403' not in feed.health().detail
    assert 'no valid market quote' in feed.health().detail


def test_calendar_holiday_bounds_and_evidence(tmp_path):
    source = tmp_path/'notice.txt'
    source.write_text('synthetic notice for contract test')
    doc = dict(schema='nse-cash-calendar/1', start='2026-10-20',end='2026-10-21',
        evidence=[dict(url='https://nsearchives.nseindia.com/test-notice',file=source.name,
            sha256=hashlib.sha256(source.read_bytes()).hexdigest())],
        days=[dict(date='2026-10-20',status='closed',evidence_indices=[0]),
              dict(date='2026-10-21',status='open',kind='regular',
                   windows=[['09:15:00','15:30:00']],evidence_indices=[0])])
    calendar = ExchangeCalendar(doc,source_dir=tmp_path)
    clock = MarketClock(calendar)
    assert not clock.is_session('2026-10-20')
    assert clock.is_session('2026-10-21')
    assert calendar.verified_for('2026-10-21')
    assert not calendar.verified_for('2026-10-22')
    assert calendar.session('2024-11-01').kind == 'muhurat'
    assert clock.is_session('2024-03-02')
    source.write_text('changed')
    with pytest.raises(ValueError,match='hash mismatch'):
        ExchangeCalendar(doc,source_dir=tmp_path)


def test_macro_alignment_excludes_late_release_without_filling():
    dates = [(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(254)]
    doc = dict(schema='hamilton-observed-covariates/1',mode='historical_observation',
        source={'mode':'synthetic contract test'},covariates=[dict(name='policy',unit='percent',meaning='test policy level')],
        rows=[dict(date=d,available_at=d+'T10:00:00+05:30',policy=4+i/100,
                   evidence='synthetic-test') for i,d in enumerate(dates)])
    doc['rows'][5]['available_at']=dates[6]+'T16:00:00+05:30'
    selected,y,z,metadata,coverage=align_observed(dates,np.zeros((254,3)),doc)
    assert len(selected)==252 and dates[6] not in selected
    assert z.shape==(252,2)
    assert z[:,1].mean()==pytest.approx(0,abs=1e-12)
    assert metadata[0]['unit']=='percent'
    assert coverage['excluded_dates']==[dates[6]]
    doc['mode']='retrospective_latest_vintage'
    for row in doc['rows']:
        row['available_at']='2026-10-21T15:00:00+05:30'
    selected,_,_,_,coverage=align_observed(dates,np.zeros((254,3)),doc)
    assert len(selected)==253 and not coverage['causal_replay_eligible']
    assert 'latest revised' in coverage['alignment']
    for row in doc['rows']:
        row['policy']=5
    with pytest.raises(ValueError,match='constant'):
        align_observed(dates,np.zeros((254,3)),doc)


def test_live_warmup_requires_history_but_respects_structural_exclusion(tmp_path):
    from datetime import datetime
    from seraph.live.inference import InferenceService, Vintage, DecisionRequest
    from seraph.live.store import LiveStore
    from scripts.run_live import build
    from seraph.orchestration.standardize import MIN_WINDOW_OBS
    _, runtime, _ = build(replay=True,store=LiveStore(tmp_path/'live.sqlite'),clock=MarketClock())
    assert runtime.warmup_observations == MIN_WINDOW_OBS
    assert not runtime.warmup_complete
    svc=InferenceService(session_dates=['2026-01-02','2026-01-05','2026-01-06','2026-01-07'],
                         warmup_observations=3)
    for i,day in enumerate(('2026-01-02','2026-01-05','2026-01-06')):
        stamp=day+'T15:30:00+05:30'
        rows=[Vintage(producer='rmt',input_end=stamp,emission_available_at=stamp,value=.2+i/10)]
        rows += [Vintage(producer=p,input_end=stamp,emission_available_at=stamp,
                         absence='structural',absence_reason='no_data_coverage')
                 for p in ('hawkes','hamilton')]
        svc.process(DecisionRequest(decision_id=day,as_of=datetime.fromisoformat(stamp),
                    trigger='bar_close',mode='historical_replay'),vintages=rows)
        assert svc.warmup_complete is (i==2)
    stamp='2026-01-07T15:30:00+05:30'
    svc.process(DecisionRequest(decision_id='transient',as_of=datetime.fromisoformat(stamp),
                trigger='bar_close',mode='historical_replay'),vintages=[Vintage(
                    producer='hamilton',input_end=stamp,emission_available_at=stamp,
                    absence='transient',absence_reason='estimation_failed')])
    assert not svc.warmup_complete
def test_declared_absences_are_admitted_only_after_actual_registration(tmp_path):
    from datetime import datetime, timedelta
    from scripts.run_daily import persist, HAMILTON_EXCLUSION
    from seraph.live.store import LiveStore
    from seraph.live.engine_adapter import registry_from_store, DailyVintageProducer
    from seraph.shared_types import IST
    store = LiveStore(tmp_path/'runtime.sqlite')
    before = datetime.now(IST).replace(microsecond=0)
    persist(store, '2020-04-30', {'hamilton': HAMILTON_EXCLUSION}, hawkes_mode='absent')
    registry = registry_from_store(store, allow_legacy=False)
    rows = DailyVintageProducer(store, deployments=registry).vintages_for([], before+timedelta(seconds=2))
    assert len(rows) == 3
    assert all(r.absence == 'structural' for r in rows)
    assert all(registry.reason_unusable(r.bundle_id, before+timedelta(seconds=2)) is None for r in rows)
    assert all(datetime.fromisoformat(r.emission_available_at) >= before for r in rows)
    assert store.daily_vintages(as_of='2020-04-30T16:00:00+05:30') == []
    repeat = persist(store, '2020-04-30', {'hamilton': HAMILTON_EXCLUSION}, hawkes_mode='absent')
    assert all(not r['stored'] for r in repeat)



def test_runtime_history_resume_counts_only_compatible_registered_values(tmp_path):
    from scripts.run_daily import persist
    from scripts.warm_runtime_history import registered_days
    from seraph.live.store import LiveStore
    store = LiveStore(tmp_path/'history.sqlite')
    store.record_daily_vintage(producer='rmt', input_end='2020-04-28T15:30:00+05:30',
        emission_available_at='2020-04-28T15:31:00+05:30', origin='computed',
        value=.2, bundle_id='unregistered-old-output')
    persist(store, '2020-04-29', {'rmt': {'score_eligible': True, 'value': .3}},
            hawkes_mode='absent')
    persist(store, '2020-04-30', {}, hawkes_mode='absent')
    assert registered_days(store) == {'2020-04-29'}
    repeat = persist(store, '2020-04-29', {'rmt': {'score_eligible': True, 'value': .3}},
                     hawkes_mode='absent')
    assert all(not row['stored'] for row in repeat)
    assert registered_days(store) == {'2020-04-29'}


def test_history_planning_and_daily_computation_honor_the_same_source(monkeypatch):
    import asyncio
    import asyncpg
    from scripts import run_daily
    seen = []
    class Connection:
        async def close(self):
            seen.append('closed')
    connection = Connection()
    async def connect(dsn):
        seen.append(dsn)
        return connection
    async def compute(conn, day):
        assert conn is connection
        return {'day': day}, {}
    monkeypatch.setenv('SERAPH_DB_DSN', 'postgresql://test-source.invalid/test')
    monkeypatch.setattr(asyncpg, 'connect', connect)
    monkeypatch.setattr(run_daily, '_rmt_only', compute)
    assert asyncio.run(run_daily.compute_pillars('2020-04-30')) == ({'day': '2020-04-30'}, {})
    assert seen == ['postgresql://test-source.invalid/test', 'closed']


def test_resuming_completed_rmt_also_registers_latest_exclusions(tmp_path):
    from scripts.warm_runtime_history import register_daily_exclusions
    from seraph.live.store import LiveStore
    from seraph.live.engine_adapter import registry_from_store, DailyVintageProducer
    from datetime import datetime, timedelta
    from seraph.shared_types import IST
    store = LiveStore(tmp_path/'resume.sqlite')
    store.record_daily_vintage(producer='hamilton', input_end='2020-04-30T15:30:00+05:30',
        emission_available_at='2020-04-30T15:31:00+05:30', origin='absent',
        absence='structural', absence_reason='no_data_coverage', bundle_id='legacy-exclusion')
    register_daily_exclusions(store, '2020-04-30')
    registry = registry_from_store(store, allow_legacy=False)
    now = datetime.now(IST) + timedelta(seconds=1)
    rows = DailyVintageProducer(store, deployments=registry).vintages_for([], now)
    declarations = [r for r in rows if r.producer in ('hawkes', 'hamilton')]
    assert len(declarations) == 2
    assert all(r.value is None and r.absence == 'structural' for r in declarations)
    assert all(registry.reason_unusable(r.bundle_id, now) is None for r in declarations)
    assert store.vintage_history('rmt') == []

# ------------------------------------------- the warm-up shortfall, reported


def test_warmup_progress_counts_distinct_input_ends_and_names_absence(tmp_path):
    """`assess_publication` can only say `warmup_incomplete`.

    This reports HOW short each pillar is, using the rule the standardizer
    admits by -- one observation per distinct `input_end` -- so a retained
    model re-emitted under a second timestamp cannot inflate it. A pillar
    holding only declared absences is `absent`, which is a different fact
    from partial progress: Hamilton is a standing structural exclusion while
    Hawkes is genuinely mid-warm-up.
    """
    from seraph.dashboard.console_backend import warmup_progress
    from seraph.live.store import LiveStore

    store = LiveStore(tmp_path / "live.sqlite")
    # Two computed observations, plus the SAME input_end twice, which must
    # count once.
    for day, value in (("2026-01-05", 0.2), ("2026-01-12", 0.3)):
        store.record_daily_vintage(
            producer="hawkes", input_end=f"{day}T15:15:00+05:30",
            emission_available_at=f"{day}T16:00:00+05:30",
            origin="computed", value=value, bundle_id="native-hawkes:test")
    store.record_daily_vintage(
        producer="hawkes", input_end="2026-01-12T15:15:00+05:30",
        emission_available_at="2026-01-12T18:00:00+05:30",
        origin="computed", value=0.3, bundle_id="native-hawkes:test")
    # An archived research value is reported separately, never counted as
    # live-admissible progress.
    store.record_daily_vintage(
        producer="hawkes", input_end="2026-01-19T15:25:00+05:30",
        emission_available_at="2026-01-19T15:55:00+05:30",
        origin="archived", value=0.4, bundle_id="original hawkes")
    # Hamilton: declared absence only.
    store.record_daily_vintage(
        producer="hamilton", input_end="2026-01-05T15:30:00+05:30",
        emission_available_at="2026-01-05T15:30:00+05:30",
        origin="absent", absence="structural",
        absence_reason="standing research decision")

    report = warmup_progress(store, required=5)
    hawkes = report["pillars"]["hawkes"]
    assert hawkes["observations"] == 2, "the repeated input_end counts once"
    assert hawkes["archived_not_counted"] == 1
    assert hawkes["shortfall"] == 3 and hawkes["ready"] is False
    assert hawkes["absent"] is False, "partial progress is not absence"

    hamilton = report["pillars"]["hamilton"]
    assert hamilton["absent"] is True and hamilton["observations"] == 0
    assert hamilton["declared_absences"] == 1

    assert report["required"] == 5 and report["ready"] is False
