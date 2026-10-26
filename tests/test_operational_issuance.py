"""C10/F03: displayed issuance, retry conflicts, and exact observed-session outcomes."""
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from seraph.live.store import LiveStore, StoreError
from seraph.prediction import issuance


def state():
    return SimpleNamespace(
        as_of='2026-01-01', model_manifest={'fit': 'synthetic test parameters'},
        predicted=dict(probability=.2, horizon_sessions=15, loss_barrier=.1,
                       definition='synthetic test target', fit_status='forecast'),
        warning=dict(level='no_warning', threshold=.3), measured={},
        snapshot=dict(sha256='synthetic-input'))


def test_issuance_matches_display_and_conflicts_do_not_overwrite(tmp_path):
    store = LiveStore(tmp_path/'live.sqlite')
    s = state()
    now = datetime.fromisoformat('2026-01-02T16:00:00+05:30')
    first = issuance.issue(s, store, now=now)
    retry = issuance.issue(s, store, now=now)
    assert first['stored'] and not retry['stored']
    assert retry['issued_at'] == first['issued_at']
    row, = store.forecasts()
    assert row['probability'] == s.predicted['probability']
    assert row['detail']['warning'] == s.warning
    assert row['detail']['issue_mode'] == 'delayed_operational'
    s.predicted['probability'] = .9
    with pytest.raises(StoreError, match='conflicting'):
        issuance.issue(s, store, now=now)
    assert store.forecasts()[0]['probability'] == .2


def test_settlement_uses_fifteen_observed_returns_not_calendar_days(tmp_path):
    store = LiveStore(tmp_path/'live.sqlite')
    s = state()
    issuance.issue(s, store, now=datetime.fromisoformat('2026-01-02T16:00:00+05:30'))
    dates = pd.bdate_range('2026-01-01', periods=16)
    frame = pd.DataFrame(dict(date=dates, market_return=[0]+[-.01]*15,
                              **{f'factor_{i}': [0.]*16 for i in range(10)}))
    path = tmp_path/'snapshot.parquet'
    frame.iloc[:15].to_parquet(path)
    now = datetime.fromisoformat('2026-02-01T16:00:00+05:30')
    assert not issuance.settle(store, path, now=now)['settled']
    frame.to_parquet(path)
    with pytest.raises(ValueError, match='series'):
        issuance.settle(store, path, now=now, series_id='official-nifty')
    settled = issuance.settle(store, path, now=now)
    assert settled['settled'][0]['outcome'] == 1
    row, = store.forecasts()
    assert len(row['outcome_evidence']['dates']) == 15
    assert not issuance.settle(store, path, now=now)['settled']
