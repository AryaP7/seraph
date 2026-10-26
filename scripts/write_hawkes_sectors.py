"""C5 — produce FR14 observations from actual C4 jump streams and declared intervals."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seraph.ingestion.hawkes_universe import BasketTimeline, TARIFF_SECTOR_BASKET
from seraph.pillars.hawkes.sectors import observe, save
from seraph.store.bootstrap import resolve_dsn
from scripts.write_hawkes_production import load_stream


async def run(args):
    import asyncpg
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        rows = await pool.fetch('SELECT rebalance_date,members FROM universe_snapshots ORDER BY rebalance_date')
        timeline = BasketTimeline.from_rows(rows)
        stream = await load_stream(pool, timeline.union, progress_every=0)
        result = observe(stream, timeline, TARIFF_SECTOR_BASKET,
            baseline_start=args.baseline_start, baseline_end=args.baseline_end,
            observation_start=args.observation_start, observation_end=args.observation_end,
            mapping_basis='existing provisional tariff-representative basket; not an NSE sector index')
        return save(result, directory=args.out)
    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('baseline-start', 'baseline-end', 'observation-start', 'observation-end'):
        parser.add_argument('--' + field, required=True)
    parser.add_argument('--out', type=Path)
    print(json.dumps(asyncio.run(run(parser.parse_args())), indent=2))
