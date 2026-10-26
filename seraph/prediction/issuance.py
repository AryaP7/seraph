"""C10 — operational issuance and observed-session settlement (FR30, FR32–37)."""
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from seraph.shared_types import IST
from seraph.live.store import LiveStore

SERIES = 'seraph-pit-equal-weight-log-return/1'
TARGET = 'research_market_loss10_15'
MODEL = 'operational_combined'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


def runtime_store():
    root = Path(__file__).resolve().parents[2]
    return LiveStore(Path(os.environ.get('SERAPH_LIVE_STORE',
                                        root / 'prototype_runs/live.sqlite')))


def issue(state, store, *, now=None):
    """Persist the computed result before publishing it to the UI."""
    moment = now or datetime.now(IST)
    if not state.model_manifest:
        raise ValueError('Regenerate the forecast with a fitted model manifest before issuance')
    if moment.tzinfo is None:
        raise ValueError('Issuance time requires an explicit timezone')
    moment = moment.astimezone(IST)
    model_id = digest(state.model_manifest)
    previous = next((row for row in store.forecasts(target=TARGET, limit=100000)
                     if row['model'] == MODEL and row['as_of'] == state.as_of
                     and row['artefact_id'] == model_id), None)
    issue_mode = (previous['detail']['issue_mode'] if previous else
                  'operational' if moment.date().isoformat() == state.as_of
                  else 'delayed_operational')
    horizon = state.predicted['horizon_sessions']
    # Lower bound only. Actual settlement requires the next H observed closes.
    lower_bound = (datetime.fromisoformat(state.as_of) +
                   timedelta(days=horizon)).date().isoformat()
    level = state.warning['level']
    detail = dict(schema='operational-issuance/1', series_id=SERIES,
                  issue_mode=issue_mode,
                  model_manifest=state.model_manifest, input_manifest=state.snapshot,
                  target=dict(horizon=horizon, barrier=state.predicted['loss_barrier'],
                              definition=state.predicted['definition']),
                  warning=state.warning, measured=state.measured,
                  maturity_rule='next H observed market sessions, never calendar approximation')
    written = store.record_forecast(
        target=TARGET, model=MODEL, as_of=state.as_of, artefact_id=model_id,
        horizon=horizon, matures_after=lower_bound,
        probability=state.predicted['probability'], threshold=state.warning['threshold'],
        alarm=(level == 'warning' if level in ('warning', 'no_warning') else None),
        fit_status=state.predicted['fit_status'], inputs_hash=state.snapshot['sha256'],
        detail=detail, at=moment)
    return dict(written, forecast_id=digest([TARGET, MODEL, state.as_of, model_id]),
                mode=detail['issue_mode'], series_id=SERIES)


def settle(store, snapshot, *, now=None, series_id=SERIES):
    """Settle from the same research index, retaining the exact outcome window."""
    from seraph.prediction.operational import _snapshot_frame
    if series_id != SERIES:
        raise ValueError('Outcome series differs from the forecast target series')
    moment = now or datetime.now(IST)
    frame = _snapshot_frame(Path(snapshot))
    dates = [str(d)[:10] for d in frame['date']]
    returns = frame['market_return'].to_numpy(float)
    source_hash = hashlib.sha256(Path(snapshot).read_bytes()).hexdigest()
    settled, pending = [], []
    for row in store.forecasts(target=TARGET, pending_only=True, limit=100000):
        detail = row['detail']
        if detail.get('series_id') != series_id or row['as_of'] not in dates:
            pending.append(dict(as_of=row['as_of'], reason='missing matching target history'))
            continue
        start = dates.index(row['as_of']) + 1
        stop = start + row['horizon']
        path = returns[start:stop]
        if (len(path) != row['horizon'] or not np.isfinite(path).all() or
                datetime.fromisoformat(dates[stop-1]+'T15:30:00+05:30') > moment):
            pending.append(dict(as_of=row['as_of'], reason='outcome window not yet observed'))
            continue
        outcome = float(np.min(np.cumsum(path)) <=
                        np.log1p(-detail['target']['barrier']))
        evidence = dict(series_id=series_id, snapshot_sha256=source_hash,
                        dates=dates[start:stop], log_returns=path.tolist(),
                        window_sha256=digest([dates[start:stop], path.tolist()]))
        settled.append(store.attach_outcome(
            target=row['target'], model=row['model'], as_of=row['as_of'],
            artefact_id=row['artefact_id'], outcome=outcome,
            now=moment.isoformat(), evidence=evidence))
    return dict(settled=settled, pending=pending)
