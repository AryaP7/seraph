"""C2/C5 — dated continuous-session evidence and native coverage (FR1, FR10)."""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from seraph.shared_types import IST
from seraph.live.bars import Bar

REPORT = 'Closing-Auction-Session-22-Oct-2026_20261022155032.csv'


def schedule_file(tmp_path, *, received='2026-10-22T17:00:00+05:30'):
    raw = b'SYMBOL,FINAL PRICE\nA,100\n,\n'
    (tmp_path/REPORT).write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    source = dict(file=REPORT, url='https://nsearchives.nseindia.com/'+REPORT,
                  sha256=digest, received_at=received)
    doc = dict(schema='native-session-schedule/1', policy='common_continuous_session',
        sources=[source], dates={'2026-10-22': dict(cas_members=['A'],
        continuous_close='15:15:00', received_at=received, source_sha256=digest)})
    p = tmp_path/'schedule.json'
    p.write_text(json.dumps(doc))
    return p


def test_dated_schedule_never_extrapolates_membership_or_receipt(tmp_path):
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    schedule = NativeSessionSchedule.load(schedule_file(tmp_path))
    assert schedule.cutoffs(('A','B'), '2026-10-22T16:00:00+05:30') == {}
    assert schedule.cutoffs(('B',), '2026-10-24T16:00:00+05:30') == {}
    assert schedule.cutoffs(('A','B'), '2026-10-24T16:00:00+05:30') == {'2026-10-22':'15:15:00'}
    assert '2026-10-23' not in schedule.cutoffs(('A',), '2026-10-24T16:00:00+05:30')


def test_schedule_requires_matching_report_hash_and_members(tmp_path):
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    path = schedule_file(tmp_path)
    doc = json.loads(path.read_text())
    doc['dates']['2026-10-22']['cas_members'] = ['B']
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='members'):
        NativeSessionSchedule.load(path)
    path = schedule_file(tmp_path)
    (tmp_path/REPORT).write_bytes(b'SYMBOL,FINAL PRICE\nB,101\n')
    with pytest.raises(ValueError, match='hash'):
        NativeSessionSchedule.load(path)


def test_a_report_cannot_supply_another_dates_schedule(tmp_path):
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    path = schedule_file(tmp_path)
    doc = json.loads(path.read_text())
    doc['dates']['2026-10-21'] = doc['dates'].pop('2026-10-22')
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='date'):
        NativeSessionSchedule.load(path)


def add_preopen_notice(path, filename, *, rename=False):
    from seraph.market_calendar.native_sessions import CIRCULAR_ROOT, RENAME_NOTICE
    doc = json.loads(path.read_text())
    doc['special_preopen_notices'] = [filename]
    for name in [filename] + ([RENAME_NOTICE] if rename else []):
        raw = b'%PDF-1.4\nsynthetic circular fixture\n'
        (path.parent/name).write_bytes(raw)
        doc['sources'].append(dict(file=name, url=CIRCULAR_ROOT+name,
            sha256=hashlib.sha256(raw).hexdigest(), received_at='2026-10-22T17:00:00+05:30'))
    path.write_text(json.dumps(doc))


def test_special_preopen_excludes_auction_rows_from_the_whole_basket(tmp_path):
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    from seraph.pillars.hawkes.runtime import NativeHistory
    path = schedule_file(tmp_path)
    add_preopen_notice(path, 'CMTR65845.pdf')
    schedule = NativeSessionSchedule.load(path)
    assert schedule.openings(('ITC',), '2026-10-22T16:00:00+05:30') == {}
    assert schedule.openings(('B',), '2026-10-22T18:00:00+05:30') == {}
    assert schedule.openings(('ITC',), '2026-10-22T18:00:00+05:30') == {'2025-01-06':'10:00:00'}
    history = NativeHistory(tmp_path/'native.sqlite')
    starts = datetime(2025,1,6,9,20,tzinfo=IST)
    bars = []
    for i in range(10):
        end = starts+timedelta(minutes=5*i)
        for symbol in ('ITC','B'):
            if symbol == 'ITC' and i in (1,2,3):
                continue
            bars.append(Bar(symbol,(end-timedelta(minutes=5)).isoformat(),end.isoformat(),
                            100,100,100,100,1,10))
    cutoff='2026-10-22T18:00:00+05:30'
    history.append(bars, received_at=cutoff)
    checked = history.coverage(('ITC','B'),cutoff,window_start='2025-01-06',session_schedule=schedule)
    assert checked['observed_bins'] == 1 and checked['missing_symbol_bars'] == 0
    assert checked['excluded_noncommon_rows'] == 15
    assert len(history.rows(('ITC','B'),cutoff)) == 17
    assert [r['end'] for r in history.rows(('B',),cutoff,session_schedule=schedule,basket=('ITC','B'))] == ['2025-01-06T10:05:00+05:30']


def test_historical_broker_alias_requires_the_exchange_rename_source(tmp_path):
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    path = schedule_file(tmp_path)
    add_preopen_notice(path, 'CMTR70614.pdf')
    with pytest.raises(ValueError, match='alias'):
        NativeSessionSchedule.load(path)
    path = schedule_file(tmp_path)
    add_preopen_notice(path, 'CMTR70614.pdf', rename=True)
    schedule = NativeSessionSchedule.load(path)
    cutoff='2026-10-22T18:00:00+05:30'
    assert schedule.openings(('TMPV',),cutoff) == schedule.openings(('TATAMOTORS',),cutoff)


def test_cas_report_blank_tail_is_allowed_but_partial_or_duplicate_rows_are_not():
    from seraph.market_calendar.native_sessions import report_members
    assert report_members(b'SYMBOL,FINAL PRICE\nA,100\n,\n') == ['A']
    for raw in (b'SYMBOL,FINAL PRICE\n,100\n', b'SYMBOL,FINAL PRICE\nA,100\nA,101\n'):
        with pytest.raises(ValueError):
            report_members(raw)


def test_common_session_keeps_raw_closes_and_refuses_unexplained_holes(tmp_path):
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    from seraph.pillars.hawkes.runtime import NativeHistory
    schedule = NativeSessionSchedule.load(schedule_file(tmp_path))
    history = NativeHistory(tmp_path/'native.sqlite')
    received = '2026-10-22T18:00:00+05:30'
    def bar(symbol, minute):
        end = datetime(2026,10,22,15,minute,tzinfo=IST)
        return Bar(symbol,(end-timedelta(minutes=5)).isoformat(),end.isoformat(),100,100,100,100,1,10)
    history.append([bar('A',10),bar('A',15),bar('B',10),bar('B',15),bar('B',20)], received_at=received)
    strict = history.coverage(('A','B'),received,window_start='2026-10-22')
    assert strict['missing_symbol_bars'] == 1
    checked = history.coverage(('A','B'),received,window_start='2026-10-22',session_schedule=schedule)
    assert checked['missing_symbol_bars'] == 0 and checked['excluded_noncommon_rows'] == 1
    assert len(history.rows(('B',),received)) == 3
    assert len(history.rows(('B',),received,session_schedule=schedule,basket=('A','B'))) == 2
    history.append([bar('A',5)], received_at=received)
    checked = history.coverage(('A','B'),received,window_start='2026-10-22',session_schedule=schedule)
    assert checked['missing_bars_by_member'] == {'B':1}


def test_collector_uses_link_dates_and_normalizes_duplicate_path_slashes():
    from scripts.prepare_native_sessions import report_links
    url='https://nsearchives.nseindia.com//web/mediaattachment/2026-10/Closing-Auction-Session-22-Oct-2026_20261022155032.csv'
    assert report_links('<a href="'+url+'">download</a>') == {'2026-10-22':url.replace('.com//','.com/')}
    august='https://nsearchives.nseindia.com/web/mediaattachment/2026-08/Closing-Auction-Session-_06-Aug-2026_20260807211035.csv'
    assert report_links('<a href="'+august+'">download</a>') == {'2026-08-06':august}


def test_reseeding_preserves_and_validates_the_chosen_observation_policy(tmp_path):
    from scripts.prepare_native_hawkes import selected_schedule
    path = schedule_file(tmp_path)
    config = tmp_path/'native.json'
    assert selected_schedule(config) is None
    name = selected_schedule(config, path)
    config.write_text(json.dumps({'session_schedule_file':name}))
    assert selected_schedule(config) == name
    (tmp_path/REPORT).write_text('changed')
    with pytest.raises(ValueError, match='hash'):
        selected_schedule(config)


def test_filtered_session_cannot_count_toward_the_required_window(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    from seraph.pillars.hawkes import runtime
    schedule = NativeSessionSchedule.load(schedule_file(tmp_path))
    history = runtime.NativeHistory(tmp_path/'native.sqlite')
    ends = [datetime(2026,10,day,15,20,tzinfo=IST) for day in (21,22)]
    history.append([Bar('A',(end-timedelta(minutes=5)).isoformat(),end.isoformat(),
                        100,100,100,100,1,10) for end in ends],
                   received_at='2026-10-22T18:00:00+05:30')
    daily = SimpleNamespace(store=SimpleNamespace(deployments=lambda: []))
    producer = runtime.NativeHawkesProducer(history, daily, members=('A',),
        rebalance_date='2026-10-01', window_sessions=2, session_schedule=schedule,
        now=lambda: datetime(2026,10,24,18,tzinfo=IST))
    monkeypatch.setattr(runtime.PooledStream, 'build', lambda *a, **k: pytest.fail('insufficient input reached estimator'))
    result = producer.fit_pending()
    assert not result['fitted']
    assert result['reason'] == 'Insufficient common-session history'
    assert result['coverage']['observed_sessions'] == 1


def test_newly_eligible_session_evidence_invalidates_cached_coverage(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    from seraph.pillars.hawkes import runtime
    schedule = NativeSessionSchedule.load(schedule_file(tmp_path))
    producer = runtime.NativeHawkesProducer(runtime.NativeHistory(tmp_path/'native.sqlite'),
        SimpleNamespace(), members=('A',), rebalance_date='2026-10-01', window_sessions=1,
        session_schedule=schedule, now=lambda: datetime(2026,10,22,16,tzinfo=IST))
    calls = []
    def evaluate(cutoff, arrival=None):
        # `arrival` is the replay/live split added to `_fit_pending`: dated
        # rule sets are keyed on when the rule became KNOWN, which is what
        # moves from 16:00 to 18:00 below and must invalidate the cached
        # result. A replay passes a past bar cutoff with arrival unchanged.
        calls.append(cutoff)
        return {'fitted':False, 'dates':schedule.cutoffs(('A',),cutoff)}
    monkeypatch.setattr(producer, '_fit_pending', evaluate)
    assert producer.fit_pending()['dates'] == {}
    assert producer.fit_pending()['reused_result']
    producer.now = lambda: datetime(2026,10,22,18,tzinfo=IST)
    result = producer.fit_pending()
    assert len(calls) == 2 and not result['reused_result']
    assert result['dates'] == {'2026-10-22':'15:15:00'}


def test_seed_policy_widens_what_is_seeded_but_never_the_declared_basket():
    """A dated replay needs each epoch's own members; the live basket is fixed.

    `warm_native_hawkes_history.py --baskets dated` fits every cadence point
    against the basket that epoch actually had. Seeded from today's basket
    alone, a member which has since left the universe has no native rows, and
    the fit fails with `Incomplete common native-bar coverage` rather than
    producing anything -- 70 such symbols were measured on 2026-10-25. Widening
    the SEED must not widen the declared estimation basket, because the live
    path must not move when a replay needs deeper inputs.
    """
    from scripts.prepare_native_hawkes import seeded_symbols
    latest = ['AAA', 'BBB']
    earlier = [('BBB', 'CCC'), ('DDD',)]

    assert seeded_symbols('config', latest, earlier) == ['AAA', 'BBB']
    assert seeded_symbols('dated-union', latest, earlier) == [
        'AAA', 'BBB', 'CCC', 'DDD']
    # The latest basket is always covered, even if no snapshot repeats it.
    assert set(latest) <= set(seeded_symbols('dated-union', latest, earlier))
    # Deduplicated and ordered, so a reseed is byte-stable.
    assert seeded_symbols('dated-union', latest, [('BBB',), ('BBB',)]) == ['AAA', 'BBB']
    # Omitting the snapshots cannot silently widen anything.
    assert seeded_symbols('dated-union', latest) == ['AAA', 'BBB']
    with pytest.raises(ValueError, match='seed policy'):
        seeded_symbols('everything', latest, earlier)
