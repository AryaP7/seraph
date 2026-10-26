"""C7 — explicit fitted TVTP projection artifacts for FR48 scenarios.

Only parameter arrays and metadata are loaded. The fitted mapping remains in
the existing Hamilton engine; this module supplies its persisted preprocessing.
"""
from datetime import datetime, date
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import statsmodels

from seraph.shared_types import IST
from seraph.pillars.hamilton.engine import HamiltonEngine, MultivariateTVTPHamilton, project_xi


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def artifact(engine, *, covariates, input_manifest):
    """Capture an actual fitted engine and the training-only scaler used for it."""
    if engine._res is None or engine.exog_tvtp is None:
        raise ValueError('A fitted TVTP engine is required')
    if len(covariates) + 1 != engine.exog_tvtp.shape[1]:
        raise ValueError('Covariates must describe all columns after the intercept')
    raw = np.asarray(engine._res.filtered_marginal_probabilities, dtype=float)
    if raw.shape[0] != 3:
        raw = raw.T
    initial = raw[list(engine._order), len(engine.dates)-1]
    value = dict(schema='hamilton-projection/1', params=engine._res.params.tolist(),
        order=[int(i) for i in engine._order], k_endog=engine.y.shape[1],
        covariates=covariates, intercept='first column, constant 1',
        training_start=engine.dates[0], training_end=engine.dates[-1],
        fitted_at=datetime.now(IST).isoformat(), initial_xi=initial.tolist(),
        initial_state_date=engine.dates[-1], initial_state_kind='filtered',
        implementation_sha256=hashlib.sha256(Path(__file__).with_name('engine.py').read_bytes()).hexdigest(),
        statsmodels_version=statsmodels.__version__, input_manifest=input_manifest,
        limitations=['Hypothetical conditional transition projection; not causal policy effectiveness.',
                    'Hamilton remains excluded from the actual composite under the standing research decision.'])
    macro = input_manifest.get('macro_source', {})
    if macro.get('coverage', {}).get('mode') == 'retrospective_latest_vintage':
        value['limitations'].append(
            'Policy inputs are latest-vintage historical observations received after the sample. '
            'This fit does not establish historical publication availability or causal replay performance.')
    value['artifact_id'] = identity(value)
    reconstruct(value)
    return value


def reconstruct(value):
    if value.get('schema') != 'hamilton-projection/1' or identity(
            {k: v for k, v in value.items() if k != 'artifact_id'}) != value.get('artifact_id'):
        raise ValueError('Projection artifact schema or content hash mismatch')
    if value['statsmodels_version'] != statsmodels.__version__:
        raise ValueError('Projection needs the statsmodels version recorded in its artifact')
    covariates = value['covariates']
    names = [c['name'] for c in covariates]
    if not names or len(set(names)) != len(names):
        raise ValueError('Covariate names must be nonempty and unique')
    for c in covariates:
        if not c['unit'] or not np.isfinite([c['center'], c['scale']]).all() or c['scale'] <= 0:
            raise ValueError('Every covariate needs its units and finite positive training scale')
    if sorted(value['order']) != [0, 1, 2] or value['k_endog'] != 3:
        raise ValueError('Invalid model dimension or regime order')
    xi = np.asarray(value['initial_xi'], dtype=float)
    if xi.shape != (3,) or not np.isfinite(xi).all() or (xi < 0).any() or abs(xi.sum()-1) > 1e-8:
        raise ValueError('Initial state must be a probability simplex')
    y = np.zeros((2, value['k_endog']))
    z = np.ones((2, len(covariates)+1))
    model = MultivariateTVTPHamilton(y, exog_tvtp=z)
    params = np.asarray(value['params'], dtype=float)
    if params.shape != (model.k_params,) or not np.isfinite(params).all():
        raise ValueError('Invalid fitted parameter vector')
    engine = HamiltonEngine([value['training_end']]*2, y, exog_tvtp=z)
    engine._res = SimpleNamespace(model=model, params=params)
    engine._order = tuple(value['order'])
    return engine


def transform(value, rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 260:
        raise ValueError('Supply 1..260 hypothetical session rows')
    names = [c['name'] for c in value['covariates']]
    dates = [r['session'] for r in rows]
    if dates != sorted(set(dates)) or dates[0] <= value['initial_state_date']:
        raise ValueError('Sessions must be unique, ordered and after the fitted initial state')
    out = []
    for row in rows:
        date.fromisoformat(row['session'])
        if set(row) != {'session', *names}:
            raise ValueError(f'Provide exactly the supported covariates: {names}')
        values = [float(row[c['name']]) for c in value['covariates']]
        if not np.isfinite(values).all():
            raise ValueError('Macro covariates must be finite')
        out.append([1.] + [(x-c['center'])/c['scale'] for x,c in zip(values,value['covariates'])])
    return out


def project(value, rows):
    engine = reconstruct(value)
    return project_xi(engine, transform(value, rows), xi0=value['initial_xi'])


def save(value, directory):
    reconstruct(value)
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (value['artifact_id']+'.json')
    if not path.exists():
        with path.open('x', encoding='utf-8') as file:
            json.dump(value, file, indent=2, allow_nan=False)
    return path
