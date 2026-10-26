"""C5/C8 — native live inputs, durability and missing-support admission (FR10–15)."""
from datetime import datetime, timedelta
import pytest

from seraph.live.bars import Bar
from seraph.shared_types import IST


def bar(symbol='A', minute=20, close=100):
    end = datetime(2026, 10, 22, 9, minute, tzinfo=IST)
    return Bar(symbol, (end-timedelta(minutes=5)).isoformat(), end.isoformat(),
               close, close, close, close, 2, 10)


def test_native_store_is_idempotent_and_refuses_revisions(tmp_path):
    from seraph.pillars.hawkes.runtime import NativeHistory
    history = NativeHistory(tmp_path/'native.sqlite')
    history.append([bar()], received_at=bar().end)
    history.append([bar()], received_at=bar().end)
    assert len(history.rows(['A'], bar().end)) == 1
    with pytest.raises(ValueError, match='revision'):
        history.append([bar(close=101)], received_at=bar().end)
    assert NativeHistory(history.path).rows(['A'], bar().end)[0]['close'] == 100


def test_native_history_never_reads_future_arrivals_or_partial_bars(tmp_path):
    from seraph.pillars.hawkes.runtime import NativeHistory
    from dataclasses import replace
    history = NativeHistory(tmp_path/'native.sqlite')
    with pytest.raises(ValueError, match='complete'):
        history.append([replace(bar(), complete=False)], received_at=bar().end)
    history.append([bar()], received_at=bar(minute=25).end)
    assert history.rows(['A'], bar().end) == []
    assert len(history.rows(['A'], bar(minute=25).end)) == 1


def test_native_missing_history_is_transient_and_never_zero(tmp_path):
    from seraph.pillars.hawkes.runtime import NativeHistory, NativeHawkesProducer
    from seraph.live.store import LiveStore
    from seraph.live.engine_adapter import DailyVintageProducer, registry_from_store
    store = LiveStore(tmp_path/'live.sqlite')
    registry = registry_from_store(store, allow_legacy=False)
    producer = NativeHawkesProducer(NativeHistory(tmp_path/'native.sqlite'),
        DailyVintageProducer(store, registry), members=('A',),
        rebalance_date='2026-10-01', window_sessions=500,
        now=lambda: datetime.fromisoformat(bar().end))
    values = producer.vintages_for([bar()], datetime.fromisoformat(bar().end))
    hawkes = next(v for v in values if v.producer == 'hawkes')
    assert hawkes.value is None and hawkes.absence == 'transient'
    assert hawkes.absence_reason == 'insufficient_history'
    assert producer.describe()['observed_sessions'] == 1
    assert store.vintage_history('hawkes') == []


def test_native_subscription_and_config_require_explicit_window(tmp_path):
    from seraph.pillars.hawkes.runtime import NativeHistory, NativeHawkesProducer
    with pytest.raises(ValueError, match='positive'):
        NativeHawkesProducer(NativeHistory(tmp_path/'native.sqlite'), None,
            members=('A',), rebalance_date='2026-10-01', window_sessions=0)


def test_actual_fit_availability_is_not_backdated_and_survives_restart(tmp_path):
    from seraph.pillars.hawkes.runtime import NativeHistory, NativeHawkesProducer
    from seraph.pillars.hawkes.engine import DiscreteHawkes
    from seraph.pillars.hawkes.basket_stream import PooledStream, basket_digest
    from seraph.live.engine_adapter import DailyVintageProducer, registry_from_store
    from seraph.live.store import LiveStore
    import numpy as np
    start = datetime(2026, 10, 19, 9, 20, tzinfo=IST)
    stamps = [start+timedelta(days=d, minutes=5*i) for d in range(3) for i in range(75)]
    stream = PooledStream.build([('A', stamps, np.full(len(stamps), 100.0))])
    _, manifest = stream.window(0, len(stamps)-1,
        segments=[(0,len(stamps)-1,('A',))], policy='fixed_at_fit_cutoff',
        declared=('A',), basket_id=basket_digest(('A',)), basket_basis='point_in_time',
        rebalance_date='2026-10-01')
    end = stamps[-1]
    completed = end + timedelta(seconds=12)
    store = LiveStore(tmp_path/'live.sqlite')
    daily = DailyVintageProducer(store, registry_from_store(store, allow_legacy=False))
    producer = NativeHawkesProducer(NativeHistory(tmp_path/'native.sqlite'), daily,
        members=('A',), rebalance_date='2026-10-01', window_sessions=3, now=lambda: completed)
    fit = DiscreteHawkes(mu=.1, alpha=.05, phi=.5, dispersion=10, n_bars=225, converged=True)
    producer._persist(fit, np.ones(75), manifest, end.isoformat())
    assert not store.daily_vintages(as_of=(end+timedelta(seconds=5)).isoformat())
    visible = daily.vintages_for([], completed)[0]
    assert visible.bundle_id.startswith('native-hawkes:')
    assert visible.emission_available_at == completed.isoformat()
    producer.now = lambda: completed+timedelta(minutes=5)
    producer._persist(fit, np.ones(75), manifest, end.isoformat())
    reopened = LiveStore(store.path).vintage_history('hawkes')
    assert len(reopened) == 1
    assert reopened[0]['emission_available_at'] == completed.isoformat()
    assert reopened[0]['value'] == pytest.approx(.1 / .9)
    assert reopened[0]['detail']['mts'] == 0.0


@pytest.mark.parametrize('missing', [False, True])
def test_native_fit_consumes_closed_common_grid_and_refuses_a_hole(tmp_path, monkeypatch, missing):
    from seraph.pillars.hawkes import runtime
    from seraph.pillars.hawkes.engine import DiscreteHawkes
    from seraph.live.engine_adapter import DailyVintageProducer, registry_from_store
    from seraph.live.store import LiveStore
    start = datetime(2026, 10, 19, 9, 20, tzinfo=IST)
    stamps = [start+timedelta(days=d, minutes=5*i) for d in range(3) for i in range(75)]
    bars = [Bar('A', (t-timedelta(minutes=5)).isoformat(), t.isoformat(),
                100,100,100,100,2,10) for t in stamps]
    if missing:
        bars.pop(100)  # Even a hole shared by the whole basket is not a zero.
    history = runtime.NativeHistory(tmp_path/'native.sqlite')
    history.append(bars[:-1], received_at=stamps[-1].isoformat())
    calls = []
    def fitted(*args):
        calls.append(args)
        return DiscreteHawkes(mu=.1, alpha=.05, phi=.5, dispersion=10,
                              n_bars=len(args[0]), converged=True)
    monkeypatch.setattr(runtime, 'fit_discrete_hawkes', fitted)
    store = LiveStore(tmp_path/'live.sqlite')
    daily = DailyVintageProducer(store, registry_from_store(store, allow_legacy=False))
    producer = runtime.NativeHawkesProducer(history, daily, members=('A',),
        rebalance_date='2026-10-01', window_sessions=3,
        now=lambda: stamps[-1]+timedelta(seconds=1))
    producer.vintages_for([bars[-1]], stamps[-1]+timedelta(seconds=5))
    assert calls == []  # The live callback never performs numerical fitting.
    producer.fit_pending()
    output = producer.vintages_for([bars[-1]], stamps[-1]+timedelta(seconds=5))[0]
    if missing:
        assert calls == [] and output.value is None
        assert producer.status['coverage']['grid_gaps'] == 1
    else:
        assert len(calls) == 1 and output.value == pytest.approx(.1/.9)
        assert len(store.deployments()) == 1


def test_read_only_native_status_names_configuration_and_worker_result(tmp_path):
    import json
    from seraph.pillars.hawkes.runtime import read_worker_status
    config = tmp_path/'native.json'
    config.write_text(json.dumps(dict(members=['A','B'], window_sessions=500,
        rebalance_date='2026-10-01', history_file='not-created.sqlite')))
    result = read_worker_status(config)
    assert result['configured'] and result['members'] == 2
    assert result['worker'] is None
    assert not (tmp_path/'not-created.sqlite').exists()
    config.with_suffix('.status.json').write_text(json.dumps(dict(
        fitted=False,reason='insufficient_history',observed_sessions=143)))
    assert read_worker_status(config)['worker']['observed_sessions'] == 143


def test_native_coverage_reports_missing_members_without_future_arrivals(tmp_path):
    from dataclasses import replace
    from seraph.pillars.hawkes.runtime import NativeHistory
    history = NativeHistory(tmp_path/'native.sqlite')
    early, late = bar(minute=25).end, bar(minute=30).end
    history.append([bar(), bar(minute=25), bar(symbol='B')], received_at=early)
    history.append([bar(symbol='B', minute=25)], received_at=late)
    history.append([replace(bar(symbol='OUTSIDE'), end=early,
                            start=bar().end)], received_at=early)
    coverage = history.coverage(('A', 'B'), early, window_start='2026-10-22')
    assert coverage['observed_bins'] == 2
    assert coverage['complete_members'] == ['A']
    assert coverage['missing_bars_by_member'] == {'B': 1}
    assert coverage['incomplete_bins'] == coverage['missing_symbol_bars'] == 1
    assert history.coverage(('A', 'B'), late,
                            window_start='2026-10-22')['incomplete_members'] == []


def test_idle_native_worker_skips_extraction_and_rechecks_a_late_gap_fill(tmp_path, monkeypatch):
    from seraph.pillars.hawkes import runtime
    from seraph.pillars.hawkes.engine import DiscreteHawkes
    from seraph.live.engine_adapter import DailyVintageProducer
    from seraph.live.store import LiveStore
    start = datetime(2026, 10, 19, 9, 20, tzinfo=IST)
    stamps = [start+timedelta(days=d, minutes=5*i) for d in range(3) for i in range(75)]
    bars = [Bar('A', (t-timedelta(minutes=5)).isoformat(), t.isoformat(),
                100,100,100,100,2,10) for t in stamps]
    missing = bars.pop(100)
    history = runtime.NativeHistory(tmp_path/'native.sqlite')
    now = [stamps[-1]+timedelta(seconds=1)]
    history.append(bars, received_at=now[0].isoformat())
    producer = runtime.NativeHawkesProducer(history,
        DailyVintageProducer(LiveStore(tmp_path/'live.sqlite')), members=('A',),
        rebalance_date='2026-10-01', window_sessions=3, now=lambda: now[0])
    calls = []
    original_build = runtime.PooledStream.build
    def build(*args, **kwargs):
        calls.append('extract')
        return original_build(*args, **kwargs)
    monkeypatch.setattr(runtime.PooledStream, 'build', build)
    monkeypatch.setattr(runtime, 'fit_discrete_hawkes', lambda *args:
        DiscreteHawkes(mu=.1, alpha=.05, phi=.5, dispersion=10,
                      n_bars=len(args[0]), converged=True))
    first = producer.fit_pending()
    assert not first['fitted'] and first['coverage']['grid_gaps'] == 1
    assert producer.fit_pending()['reused_result'] and calls == []
    future = now[0]+timedelta(minutes=1)
    history.append([missing], received_at=future.isoformat())
    assert producer.fit_pending()['reused_result'] and calls == []
    now[0] = future
    repaired = producer.fit_pending()
    assert repaired['fitted'] and calls == ['extract']
    assert repaired['evaluated_at'] != first['evaluated_at']


def test_runtime_connects_explicit_native_configuration_but_refuses_replay(tmp_path):
    import json
    from scripts.run_live import build
    from seraph.live.store import LiveStore
    from seraph.live.clock import MarketClock
    store = LiveStore(tmp_path/'live.sqlite')
    store.path.with_suffix('.native-hawkes.json').write_text(json.dumps(dict(
        members=['A'], rebalance_date='2026-10-01', window_sessions=500,
        history_file='native.sqlite')))
    config = store.path.with_suffix('.native-hawkes.json')
    _, _, live = build(replay=False, store=store, clock=MarketClock(), hawkes_config=config)
    assert live.producers.members == ('A',)
    _, _, replay = build(replay=True, store=store, clock=MarketClock())
    assert replay.producers.describe()['kind'] == 'daily_vintage'
    with pytest.raises(ValueError, match='live daily'):
        build(replay=True, store=store, clock=MarketClock(), hawkes_config=config)


def test_isolated_worker_reports_missing_history_and_releases_its_lock(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path
    from seraph.news.worker_lock import lock_held
    config = tmp_path/'native.json'
    config.write_text(json.dumps(dict(members=['A'], rebalance_date='2026-10-01',
        window_sessions=500, history_file='native.sqlite')))
    store = tmp_path/'live.sqlite'
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]/'scripts/run_native_hawkes.py'),
        '--config',str(config),'--store',str(store),'--once'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    status = json.loads(config.with_suffix('.status.json').read_text())
    assert status['fitted'] is False and status['reason'] == 'insufficient_history'
    assert not lock_held(store, 'native-hawkes')
