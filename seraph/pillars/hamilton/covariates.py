"""C7 — explicit observed macro inputs for diagnostic TVTP fitting (FR21, FR48).

No interpolation or invented release dates. Historical vintages are gated by
availability. Explicit latest-vintage diagnostic inputs retain their receipt
time and cannot support a point-in-time replay claim.
"""
from datetime import date, datetime

import numpy as np
from seraph.market_calendar import SessionCalendar


def align_observed(dates, y, document):
    if document.get('schema') != 'hamilton-observed-covariates/1':
        raise ValueError('Expected hamilton-observed-covariates/1')
    mode = document.get('mode')
    if mode not in ('historical_observation', 'retrospective_latest_vintage') or not document.get('source'):
        raise ValueError('Observed macro inputs require explicit source provenance')
    definitions = document.get('covariates', [])
    names = [c['name'] for c in definitions]
    if not names or len(set(names)) != len(names):
        raise ValueError('Covariates need unique names')
    if any(not c.get('unit') or not c.get('meaning') for c in definitions):
        raise ValueError('Every macro variable needs its units and meaning')
    rows = document['rows']
    keys = [r['date'] for r in rows]
    if keys != sorted(set(keys)):
        raise ValueError('Observed macro dates must be unique and ordered')
    indexed = {}
    for row in rows:
        day = date.fromisoformat(row['date'])
        available = datetime.fromisoformat(row['available_at'])
        if available.tzinfo is None or not row.get('evidence'):
            raise ValueError('Every observation needs aware availability and evidence')
        values = [float(row[n]) for n in names]
        if not np.isfinite(values).all():
            raise ValueError('Observed macro values must be finite')
        indexed[day.isoformat()] = (available, values)
    selected, raw, excluded = [], [], []
    # Values from the preceding supplied market session inform today's
    # transition. Availability must be no later than that preceding close.
    for i in range(1, len(dates)):
        prior = dates[i-1]
        found = indexed.get(prior)
        cutoff = datetime.fromisoformat(SessionCalendar().close_timestamp(prior))
        if found is None or (mode == 'historical_observation' and found[0] > cutoff):
            excluded.append(dates[i])
            continue
        selected.append(i)
        raw.append(found[1])
    if len(selected) < 250:
        raise ValueError(f'At least 250 release-eligible paired observations required; found {len(selected)}')
    values = np.asarray(raw, dtype=float)
    center, scale = values.mean(axis=0), values.std(axis=0)
    if (scale <= 0).any():
        raise ValueError('A constant macro covariate cannot identify a fitted sensitivity')
    covariates = [dict(**c, center=float(center[j]), scale=float(scale[j]))
                  for j,c in enumerate(definitions)]
    z = np.column_stack([np.ones(len(values)), (values-center)/scale])
    return ([dates[i] for i in selected], np.asarray(y)[selected], z, covariates,
            dict(paired=len(selected), excluded_dates=excluded, mode=mode,
                 causal_replay_eligible=mode == 'historical_observation',
                 alignment=('Previous supplied market session; available by its declared close; no filling'
                    if mode == 'historical_observation' else
                    'Previous supplied market session, latest revised values; receipt retained; no filling or historical-availability claim')))
