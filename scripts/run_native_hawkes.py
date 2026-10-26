"""C5 — isolated, owned native Hawkes estimation worker (FR10–15, NFR5)."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from seraph.live.store import LiveStore
    from seraph.live.engine_adapter import DailyVintageProducer
    from seraph.pillars.hawkes.runtime import NativeHistory, NativeHawkesProducer
    from seraph.news.worker_lock import worker_lock, WorkerAlreadyRunning
    from seraph.operations.jobs import pid_alive
    from seraph.shared_types import IST
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--owner-pid', type=int)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    from seraph.market_calendar.native_sessions import schedule_from_config
    producer = NativeHawkesProducer(
        NativeHistory(args.config.parent/config['history_file']), DailyVintageProducer(LiveStore(args.store)),
        members=config['members'], rebalance_date=config['rebalance_date'],
        window_sessions=config['window_sessions'], refit_sessions=config.get('refit_sessions', 5),
        session_schedule=schedule_from_config(args.config, config))
    status_path = args.config.with_suffix('.status.json')
    try:
        with worker_lock(args.store, name='native-hawkes'):
            while not args.owner_pid or pid_alive(args.owner_pid) is not False:
                try:
                    result = producer.fit_pending()
                except Exception as exc:
                    result = dict(fitted=False, reason='worker_error', error_type=type(exc).__name__)
                result['checked_at'] = datetime.now(IST).isoformat()
                temporary = status_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
                os.replace(temporary, status_path)
                if args.once:
                    print(json.dumps(result))
                    return 1 if result['reason'] == 'worker_error' else 0
                for _ in range(30):
                    if args.owner_pid and pid_alive(args.owner_pid) is False:
                        return 0
                    time.sleep(1)
    except WorkerAlreadyRunning:
        return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
