"""C6/C8 — populate real registered ECDF history through the daily producer (F02, FR28).

The default prints the plan. --execute computes missing observations, records
actual availability, and resumes from persisted vintages after interruption.
It never promotes unregistered research snapshots or changes a scientific gate.
"""
import argparse
import asyncio
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def stamp():
    from seraph.shared_types import IST
    return datetime.now(IST).isoformat()


async def observed_days(through, count):
    import asyncpg
    from seraph.store.bootstrap import resolve_dsn
    from scripts.build_observations import trading_days
    conn = await asyncpg.connect(resolve_dsn())
    try:
        days = await trading_days(conn, (date.fromisoformat(through)-timedelta(days=365*5)).isoformat())
        return [d.isoformat() for d in days if d.isoformat() <= through][-count:]
    finally:
        await conn.close()


def registered_days(store):
    """Only compatible, explicitly registered computed values count."""
    from seraph.live.engine_adapter import registry_from_store
    registry = registry_from_store(store, allow_legacy=False)
    manifests = {r['bundle_id']: r for r in store.deployments()}
    engine_hash = hashlib.sha256((ROOT/'seraph/pillars/rmt/engine.py').read_bytes()).hexdigest()
    now = datetime.fromisoformat(stamp())
    result = set()
    for row in store.vintage_history('rmt', limit=100000):
        if row['origin'] != 'computed' or row['value'] is None:
            continue
        if datetime.fromisoformat(row['emission_available_at']) > now:
            continue
        if registry.reason_unusable(row['bundle_id'], now):
            continue
        manifest = json.loads(manifests[row['bundle_id']].get('notes') or '{}')
        if manifest.get('implementation_sha256') == engine_hash:
            result.add(row['input_end'][:10])
    return result


def compute(day, store_path):
    # One BLAS thread per independent day; retain all existing bootstrap and
    # estimator settings. Only orchestration is parallelised.
    os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    from scripts.run_daily import compute_pillars, persist
    from seraph.live.store import LiveStore
    start = stamp()
    pillars, audit = asyncio.run(compute_pillars(day, hamilton='excluded'))
    rows = persist(LiveStore(store_path), day, pillars, hawkes_mode='absent', input_audit=audit)
    return dict(day=day, started_at=start, finished_at=stamp(),
                eligible=bool(pillars.get('rmt', {}).get('score_eligible')),
                rows=rows, limitations=audit.get('limitations', []), errors=audit.get('errors', {}))


def register_daily_exclusions(store, day):
    """Refresh explicit missing producers even when the day's RMT already exists.

    Reusing an RMT observation must not leave the latest standing exclusion
    attached to an old unregistered declaration. These are absence records,
    never measured or fitted pillar values.
    """
    from scripts.run_daily import persist_absence, HAMILTON_EXCLUSION
    end = day + 'T15:30:00+05:30'
    return [persist_absence(store, 'hamilton', end,
                absence=HAMILTON_EXCLUSION['absence'],
                reason=HAMILTON_EXCLUSION['absence_reason'],
                detail={'reason': HAMILTON_EXCLUSION['reason']}),
            persist_absence(store, 'hawkes', end, absence='structural',
                reason='no_data_coverage', detail={'reason':
                    'The daily producer has no registered fresh native-intraday Hawkes estimate; archived values are not current.'})]


def write_status(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')
    os.replace(temporary, path)


def main():
    from seraph.orchestration.standardize import MIN_WINDOW_OBS
    from seraph.live.store import LiveStore
    from seraph.news.worker_lock import worker_lock
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', required=True)
    parser.add_argument('--store', type=Path, default=ROOT/'prototype_runs/live.sqlite')
    parser.add_argument('--status-file', type=Path, default=ROOT/'prototype_runs/runtime-warmup-status.json')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=1)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.through+'T15:30:00+05:30')
    if cutoff > datetime.fromisoformat(stamp()):
        parser.error('--through must be a completed observed session')
    store = LiveStore(args.store)
    days = asyncio.run(observed_days(args.through, MIN_WINDOW_OBS))
    present = registered_days(store)
    pending = [d for d in days if d not in present]
    plan = dict(schema='runtime-history-build/1', started_at=stamp(), through=args.through,
        required=MIN_WINDOW_OBS, selected_days=days, already_present=sorted(set(days)&present),
        pending=pending.copy(), completed=[], failures=[], status='planned',
        note='RMT history from the existing producer. Hamilton remains excluded; no current Hawkes model is invented. Actual emission availability is retained.')
    if not args.execute:
        print(json.dumps(plan, indent=2)); return 0
    with worker_lock(args.store, name='runtime-history-build'):
        plan['status']='running'; write_status(args.status_file, plan)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(compute, day, str(args.store)): day for day in pending}
            for future in as_completed(futures):
                day = futures[future]
                try:
                    item = future.result()
                    plan['completed'].append(item)
                    print(f"[warmup] {day}: eligible={item['eligible']} ({len(plan['completed'])}/{len(pending)})", flush=True)
                except Exception as exc:
                    plan['failures'].append(dict(day=day, error=str(exc)))
                    print(f'[warmup] {day}: failed; recorded in status', flush=True)
                plan['pending'].remove(day)
                plan['updated_at']=stamp(); write_status(args.status_file, plan)
        if days:
            plan['exclusion_declarations'] = register_daily_exclusions(store, days[-1])
        plan['registered_observations']=len(set(days)&registered_days(store))
        plan['status']=('complete' if plan['registered_observations']>=MIN_WINDOW_OBS else 'incomplete')
        plan['finished_at']=stamp(); write_status(args.status_file, plan)
        print(json.dumps({k:plan[k] for k in ('status','registered_observations','required')}))
        return 0 if plan['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
