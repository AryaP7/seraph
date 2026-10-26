"""C5/FR15 — persist a directed diagnostic using actual native sector streams."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seraph.ingestion.hawkes_universe import BasketTimeline, TARIFF_SECTOR_BASKET
from seraph.pillars.hawkes.network import counts_from_stream, fit_network, save
from seraph.store.bootstrap import resolve_dsn
from scripts.write_hawkes_production import load_stream


async def run(args):
    import asyncpg
    spec = json.loads(args.specification.read_text(encoding='utf-8'))
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1,max_size=2)
    try:
        timeline = BasketTimeline.from_rows(await pool.fetch(
            'SELECT rebalance_date,members FROM universe_snapshots ORDER BY rebalance_date'))
        stream = await load_stream(pool,timeline.union,progress_every=0)
    finally:
        await pool.close()
    inputs = counts_from_stream(stream,timeline,TARIFF_SECTOR_BASKET,start=args.start,end=args.end)
    excluded = sorted(set(args.exclude_dates or ()))
    if excluded:
        # Whole sessions only. Dropping part of one would leave the very
        # discontinuity this is meant to avoid.
        import numpy as _np
        keep = [i for i, stamp in enumerate(inputs['timestamps'])
                if stamp[:10] not in excluded]
        if not keep:
            raise ValueError('--exclude-dates removed every session')
        inputs = dict(inputs,
                      counts=_np.asarray(inputs['counts'])[keep],
                      timestamps=[inputs['timestamps'][i] for i in keep])
    result = fit_network(inputs['counts'],inputs['timestamps'],spec,node_ids=inputs['node_ids'],
        provenance=dict(source='actual stored intraday_bars via C4 Lee–Mykland',
            mode='historical observation',requested_start=args.start,requested_end=args.end,
            mapping='provisional existing tariff-sector basket',coverage=inputs['coverage'],
            # Disclosed on the artefact so an exclusion can never be mistaken
            # for the adopted fit over the whole interval.
            excluded_sessions=excluded,
            exclusion_reason=(
                'Sessions excluded whole, by explicit request, because the '
                'excitation recursion cannot run across a within-session '
                'break. This is a scope reduction, not a model change: the '
                'specification, equations and parameters are unchanged.'
                if excluded else None)))
    path=save(result,args.out)
    print(json.dumps(dict(path=str(path),result=result),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',required=True)
    parser.add_argument('--end',required=True)
    parser.add_argument('--specification',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--exclude-dates',nargs='+',metavar='YYYY-MM-DD',
        help='Drop these whole sessions from the input and record them on the '
             'artefact. For a session the estimator cannot model across, such '
             'as a market-wide trading halt. Never silent: the dates and the '
             'reason travel in the result provenance.')
    asyncio.run(run(parser.parse_args()))
