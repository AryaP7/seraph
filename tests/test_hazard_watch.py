import numpy as np
import pytest
from seraph.prediction.hazard_watch import public_event_watch


def event(identity='a', date='2020-01-03'):
    return dict(event=identity, published_date=date, source_url='https://example.org/declaration')


def test_publication_day_never_used_and_weekend_moves_to_next_session():
    dates = np.array(['2020-01-02','2020-01-03','2020-01-06','2020-01-07','2020-01-08'], dtype='datetime64[D]')
    result = public_event_watch(dates, [event()], duration=2)
    assert result['watch'].tolist() == [False,False,True,True,False]
    weekend = public_event_watch(dates, [event(date='2020-01-04')], duration=2)
    np.testing.assert_array_equal(weekend['watch'], result['watch'])


def test_future_declarations_cannot_rewrite_past_watches():
    dates = np.arange('2020-01-01','2020-03-01',dtype='datetime64[D]')
    first = public_event_watch(dates, [event()], duration=20)
    second = public_event_watch(dates, [event(),event('future','2020-02-10')], duration=20)
    np.testing.assert_array_equal(first['watch'][:40], second['watch'][:40])
    assert sum(first['watch']) == 20
    assert second['events'][1]['expired_in_sample'] is False


def test_overlapping_events_keep_both_identifiers():
    dates = np.arange('2020-01-01','2020-02-01',dtype='datetime64[D]')
    result = public_event_watch(dates,[event(),event('b','2020-01-04')],duration=2)
    assert result['active_events'][4] == 'a;b'
    with pytest.raises(ValueError):
        public_event_watch(dates, [event(),event()])
    with pytest.raises(ValueError):
        public_event_watch(dates, [event(date='2019-12-31')])
