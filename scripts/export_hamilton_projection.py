"""C7/FR48 — persist the existing lagged-RV diagnostic fit, without E8 writes."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from seraph.pillars.hamilton.engine import HamiltonEngine, project_xi
from seraph.pillars.hamilton.projection import artifact, project, save
from seraph.store.bootstrap import resolve_dsn
from scripts.fit_hamilton import load


async def run(args):
    import asyncpg
    if args.observations and args.derive_from:
        raise ValueError('Choose archived observations or a C4 rebuild, not both')
    pool = (None if args.observations else
            await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2))
    try:
        if args.observations:
            observed = json.loads(args.observations.read_text(encoding='utf-8'))
            dates, y = observed['dates'], np.asarray(observed['y'], dtype=float)
        else:
            dates, y = await load(pool)
        if args.derive_from:
            from scripts.build_observations import trading_days, universe_for, build_row
            days = [d for d in await trading_days(pool, args.derive_from)
                    if not args.through or d.isoformat() <= args.through]
            observations = []
            for i, day in enumerate(days):
                row = await build_row(pool, day, await universe_for(pool, day))
                if row is not None:
                    observations.append(row)
                if i % 25 == 0:
                    print(f'Actual C4 observations: {i+1}/{len(days)} through {day}', flush=True)
            dates = [r[0].isoformat() for r in observations]
            y = np.asarray([r[1:4] for r in observations], dtype=float)
    finally:
        if pool is not None:
            await pool.close()
    if args.through:
        indices = [i for i,d in enumerate(dates) if d <= args.through]
        dates, y = [dates[i] for i in indices], y[indices]
    if len(dates) < 250:
        raise ValueError('At least 250 actual stored observations are required')
    if (y.shape != (len(dates), 3) or not np.isfinite(y).all()
            or dates != sorted(set(dates))):
        raise ValueError('Actual C4 inputs require ordered unique dates and finite RV/AR/BAS rows')
    macro = None
    if args.covariates:
        from seraph.pillars.hamilton.covariates import align_observed
        macro = json.loads(args.covariates.read_text(encoding='utf-8'))
        dates, y, z, covariates, coverage = align_observed(dates, y, macro)
    else:
        center, scale = float(y[:,0].mean()), float(y[:,0].std())
        if scale <= 0:
            raise ValueError('Lagged RV must vary within the training interval')
        z = np.column_stack([np.ones(len(y)), np.r_[0., ((y[:,0]-center)/scale)[:-1]]])
        covariates = [dict(name='lagged_rv', unit='stored rv_t_yz units',
            center=center, scale=scale, meaning='prior session realised volatility; not a policy rate')]
    engine = HamiltonEngine(dates, y, exog_tvtp=z)
    result = engine.fit(probabilities='filtered')
    if result.status != 'ok':
        raise ValueError(f'Actual diagnostic fit unavailable: {result.error}')
    inputs = dict(dates=dates, y=y.tolist(), z=z.tolist(), source=(
        'existing C4 build_row over actual point-in-time daily corpus; read-only'
        if args.derive_from else observed.get('source', 'supplied actual C4 archive')
        if args.observations else 'stored hamilton_output RV/AR/BAS observations'))
    if args.observations:
        inputs['observation_source'] = dict(path=str(args.observations),
            sha256=hashlib.sha256(args.observations.read_bytes()).hexdigest(),
            provenance=observed.get('source'))
    if macro:
        inputs['macro_source'] = dict(path=str(args.covariates),
            sha256=hashlib.sha256(args.covariates.read_bytes()).hexdigest(),
            provenance=macro['source'], coverage=coverage,
            mode='retrospective diagnostic; receipt today does not establish historical vintage availability')
    args.out.mkdir(parents=True, exist_ok=True)
    input_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    input_path = args.out/('observations-'+input_hash+'.json')
    if not input_path.exists():
        input_path.write_text(json.dumps(inputs), encoding='utf-8')
    value = artifact(engine, covariates=covariates,
        input_manifest=dict(source=inputs['source'], path=str(input_path),
            sha256=input_hash, rows=len(y),
            fit_warnings=[w.model_dump(mode='json') for w in result.warnings],
            **({'macro_source': inputs['macro_source']} if macro else {})))
    # Verify the loaded parameter mapping against the original fitted engine.
    from datetime import date, timedelta
    session = (date.fromisoformat(dates[-1])+timedelta(days=1)).isoformat()
    rows = [dict(session=session, **{c['name']:c['center'] for c in covariates})]
    expected = project_xi(engine, [[1.] + [0.]*len(covariates)], xi0=value['initial_xi'])
    np.testing.assert_allclose(project(value, rows), expected, atol=1e-13)
    path = save(value, args.out)
    return dict(path=str(path), artifact_id=value['artifact_id'], training_end=dates[-1],
                round_trip_verified=True, warnings=[w.model_dump(mode='json') for w in result.warnings])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--through')
    p.add_argument('--derive-from', help='Bounded C4 observation rebuild from actual daily prices; read-only')
    p.add_argument('--observations', type=Path, help='Reuse an archived actual C4 dates/y input JSON')
    p.add_argument('--covariates', type=Path, help='Observed macro-covariate JSON with units, availability and evidence')
    p.add_argument('--out', type=Path, default=Path('prototype_runs/hamilton_projection'))
    print(json.dumps(asyncio.run(run(p.parse_args())), indent=2))
