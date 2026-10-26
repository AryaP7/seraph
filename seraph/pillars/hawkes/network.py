"""C5 — declared multivariate geometric excitation diagnostic (FR15).

The pooled production estimator is unchanged. Every scientific setting is
supplied in a named specification. B[target, source] is the integrated kernel;
it describes conditional excitation, not causal transmission or losses.
"""
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from seraph.shared_types import IST
from seraph.pillars.hawkes.sectors import digest


def counts_from_stream(stream, timeline, sector_members, *, start, end):
    nodes = sorted(sector_members)
    days = np.asarray(stream.day, dtype=str)
    ix = np.flatnonzero((days >= start) & (days <= end))
    snapshot = timeline.at(end)
    basket = set(snapshot.basket if snapshot else ())
    counts = np.full((len(ix), len(nodes)), np.nan)
    coverage = {}
    for column, sector in enumerate(nodes):
        members = sorted(set(sector_members[sector]) & basket)
        contributors = [s for s in members if s in stream.series and len(ix)
                        and np.isin(ix, stream.series[s].bar_index).all()]
        coverage[sector] = dict(declared=members, contributors=contributors)
        if contributors:
            lo, hi = int(ix[0]), int(ix[-1])
            inputs, manifest = stream.window(lo, hi, segments=[(lo,hi,tuple(contributors))],
                policy='fixed_at_fit_cutoff', declared=members, basket_id=snapshot.digest,
                basket_basis='existing provisional tariff basket', rebalance_date=snapshot.rebalance_date)
            counts[:,column] = inputs['n_neg']
            coverage[sector]['manifest'] = asdict(manifest)
    return dict(node_ids=nodes, counts=counts,
        timestamps=[stream.bars[int(i)].isoformat() for i in ix], coverage=coverage)


def fit_network(counts, timestamps, specification, *, node_ids, provenance):
    required = {'design_ref','model_status','decay','dispersion','l2','minimum_bars',
                'minimum_events','stationarity_bound','seasonality','session_reset','display_threshold'}
    if set(specification) != required:
        raise ValueError(f'Specification must explicitly declare {sorted(required)}')
    spec = dict(specification)
    if not spec['design_ref'] or spec['model_status'] not in ('user_declared','synthetic_test','proposed_unadopted'):
        raise ValueError('Name the design and its adoption status')
    phi, size, penalty, bound = map(float, (spec['decay'],spec['dispersion'],spec['l2'],spec['stationarity_bound']))
    if (not np.isfinite([phi,size,penalty,bound,spec['display_threshold']]).all() or
        not 0 <= phi < 1 or size <= 0 or penalty < 0 or not 0 < bound < 1 or
        spec['display_threshold'] < 0 or spec['minimum_bars'] < 2 or spec['minimum_events'] < 1):
        raise ValueError('Invalid explicitly declared model parameters')
    if spec['session_reset'] is not True or spec['seasonality'] not in ('training_tod','constant'):
        raise ValueError('Use session reset and an explicit supported seasonality policy')
    y = np.asarray(counts, dtype=float)
    n = len(node_ids)
    if n < 2 or len(set(node_ids)) != n or y.shape != (len(timestamps),n):
        raise ValueError('Counts must match the stable unique node and timestamp axes')
    moments = [datetime.fromisoformat(t) for t in timestamps]
    if any(t.tzinfo is None for t in moments) or moments != sorted(set(moments)):
        raise ValueError('Native bar timestamps must be aware, unique and ordered')
    if np.isinf(y).any() or (y[np.isfinite(y)] < 0).any() or (y[np.isfinite(y)]%1 != 0).any():
        raise ValueError('Counts must be nonnegative integers; NaN declares missing support')
    result = dict(schema='c5-directed-network/1', method='negative-binomial geometric excitation',
        convention='matrix[target, source]', node_ids=list(node_ids), specification=spec,
        input_start=timestamps[0] if timestamps else None,
        input_end=timestamps[-1] if timestamps else None,
        fitted_at=datetime.now(IST).isoformat(), provenance=provenance,
        input_sha256=digest([timestamps, [[None if np.isnan(v) else float(v) for v in row] for row in y]]),
        matrix=None, edges=[], hidden_edges=0,
        limitations=['Conditional excitation weights, not causal effects or probabilities of losses.',
            'Integrated infinite-lag kernel; session resets truncate realized within-session excitation.',
            'Full-sample descriptive fit is unavailable to decisions before its sample end and actual availability.'])
    support = np.isfinite(y).all(axis=0) & (np.nansum(y,axis=0) >= spec['minimum_events'])
    # A same-date step that is not exactly one bin is a break in the session:
    # a market-wide halt, or an absent bin. The recursion below must not run
    # across one, so it is measured HERE and reported, rather than raised from
    # inside the loop where it produced no artefact at all.
    within_session_breaks = [
        dict(after=moments[t-1].isoformat(), before=moments[t].isoformat(),
             seconds=(moments[t]-moments[t-1]).total_seconds())
        for t in range(1, len(moments))
        if moments[t].date() == moments[t-1].date()
        and (moments[t]-moments[t-1]).total_seconds() != 300]
    result['coverage'] = dict(bars=len(y), supported_nodes=[v for v,s in zip(node_ids,support) if s],
                              unsupported_nodes=[v for v,s in zip(node_ids,support) if not s],
                              within_session_breaks=within_session_breaks)
    if len(y) < spec['minimum_bars'] or not support.all():
        result.update(status='insufficient_support', reason='Declared bar/event support or complete native observations are missing')
    elif within_session_breaks:
        # Recorded, not fitted. The lag state resets at a session open by
        # design; it has no declared behaviour at an intraday break, and
        # choosing one would be a model decision rather than a fix.
        result.update(
            status='insufficient_support',
            reason=('The input contains %d within-session break(s), so the '
                    'excitation recursion cannot run across them without '
                    'attributing excitation to a period in which nothing '
                    'traded. The dates are reported in '
                    'coverage.within_session_breaks.'
                    % len(within_session_breaks)))
    elif spec['model_status'] == 'proposed_unadopted':
        result.update(status='design_required', reason='Owner-adopted real model specification is required before fitting')
    else:
        lag = np.zeros_like(y)
        for t in range(1,len(y)):
            if moments[t].date() == moments[t-1].date():
                # Guaranteed by the `within_session_breaks` check above, which
                # returns `insufficient_support` instead of reaching here.
                assert (moments[t]-moments[t-1]).total_seconds() == 300
                lag[t] = y[t-1]+phi*lag[t-1]
        tod = np.ones_like(y)
        if spec['seasonality'] == 'training_tod':
            slots = np.array([t.strftime('%H:%M') for t in moments])
            for slot in set(slots):
                tod[slots==slot] = np.maximum(y[slots==slot].mean(axis=0),1e-12)
            tod /= tod.mean(axis=0)
        lag *= 1-phi

        def objective(x):
            mu, matrix = x[:n], x[n:].reshape(n,n)
            intensity = np.maximum(tod*mu + lag@matrix.T,1e-12)
            nll = -(gammaln(y+size)-gammaln(size)-gammaln(y+1)
                    +size*(np.log(size)-np.log(size+intensity))
                    +y*(np.log(intensity)-np.log(size+intensity))).sum()
            grad_intensity = (size+y)/(size+intensity)-y/intensity
            gradient = np.r_[np.sum(grad_intensity*tod,axis=0),
                (grad_intensity.T@lag + 2*penalty*matrix).ravel()]
            return float(nll+penalty*np.square(matrix).sum()), gradient

        constraint_jac = np.zeros((n,n+n*n))
        for j in range(n):
            constraint_jac[j,n+j::n] = -1
        fit = minimize(objective, np.r_[np.maximum(y.mean(axis=0),1e-5),np.zeros(n*n)],
            jac=True, method='SLSQP', bounds=[(1e-9,None)]*n+[(0.,bound)]*(n*n),
            constraints=[dict(type='ineq', fun=lambda x:bound-x[n:].reshape(n,n).sum(axis=0),
                              jac=lambda x:constraint_jac)],
            options=dict(maxiter=1000,ftol=1e-9))
        matrix = fit.x[n:].reshape(n,n)
        radius = float(max(abs(np.linalg.eigvals(matrix))))
        result['diagnostics'] = dict(converged=bool(fit.success), iterations=int(fit.nit),
            objective=float(fit.fun), spectral_radius=radius, message=str(fit.message))
        if not fit.success or radius >= 1 or matrix.sum(axis=0).max()>bound+1e-6:
            result.update(status='fit_failed',reason='Optimizer or stationarity constraint did not pass')
        else:
            result.update(status='fitted', matrix=matrix.tolist(), immigrant_rate=fit.x[:n].tolist(),
                          seasonality=tod.tolist())
            for target in range(n):
                for source in range(n):
                    weight = float(matrix[target,source])
                    if target == source or weight <= 0:
                        continue
                    if weight < spec['display_threshold']:
                        result['hidden_edges'] += 1
                    else:
                        result['edges'].append(dict(source=node_ids[source],target=node_ids[target],weight=weight))
    result['available_at'] = datetime.now(IST).isoformat()
    result['artifact_id'] = digest(result)
    return result


def root():
    return Path(os.environ.get('SERAPH_NETWORK_ARTIFACTS',
                Path(__file__).resolve().parents[3]/'prototype_runs/hawkes_network'))


def save(result, directory=None):
    folder = Path(directory or root()); folder.mkdir(parents=True, exist_ok=True)
    path = folder/(result['artifact_id']+'.json')
    if not path.exists():
        with path.open('x', encoding='utf-8') as file:
            json.dump(result,file,indent=2,allow_nan=False)
    return path


def select(as_of, directory=None):
    cutoff = datetime.fromisoformat(as_of)
    eligible = []
    for path in Path(directory or root()).glob('*.json'):
        value = json.loads(path.read_text(encoding='utf-8'))
        if digest({k:v for k,v in value.items() if k!='artifact_id'}) != value['artifact_id']:
            raise ValueError('Network artifact content mismatch')
        if datetime.fromisoformat(value['available_at'])<=cutoff and (
                value['input_end'] is None or datetime.fromisoformat(value['input_end'])<=cutoff):
            eligible.append(value)
    return max(eligible,key=lambda v:v['available_at']) if eligible else dict(
        status='unavailable', reason='No declared fitted network artifact is available at this decision',edges=[])
