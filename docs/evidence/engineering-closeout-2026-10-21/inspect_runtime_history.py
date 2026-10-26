"""F02 actual registered-history inspection; no feed connection or fake decisions."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.run_live import build, cold_start
from seraph.live.clock import MarketClock
from seraph.live.engine_adapter import DailyVintageProducer
from seraph.live.store import LiveStore
from seraph.shared_types import IST


def inspect():
    with tempfile.TemporaryDirectory(prefix='seraph-history-readiness-') as directory:
        copied = Path(directory)/'live.sqlite'
        with closing(sqlite3.connect((ROOT/'prototype_runs/live.sqlite').as_uri()+'?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(copied)) as target:
                source.backup(target)
        store = LiveStore(copied)
        clock = MarketClock()
        _, service, _ = build(replay=False, store=store, clock=clock)
        cutoff = datetime.now(IST)
        start = cold_start(service, store, cutoff)
        current = DailyVintageProducer(store, deployments=service.deployments).vintages_for([], cutoff)
        inputs = [dict(producer=v.producer, input_end=v.input_end,
            available_at=v.emission_available_at, bundle_id=v.bundle_id,
            absence=v.absence, value=v.value,
            refusal=service.deployments.reason_unusable(v.bundle_id, cutoff)) for v in current]
        required = [v.producer for v in current if v.absence != 'structural']
        usable = {p: len(service.standardizer.window(p, cutoff)) for p in start['observations']}
        ready = bool(required) and all(usable[p] >= service.warmup_observations for p in required)
        return dict(at=cutoff.isoformat(), observations=start['observations'],
            usable_observations=usable,
            threshold=service.warmup_observations, required_pillars=required,
            inputs=inputs, history_ready=ready,
            all_latest_inputs_admitted=all(v['refusal'] is None for v in inputs),
            rejected_history=start['rejected'], decision_produced=False,
            note='Real store copy and canonical cold start. No feed connection, closed bar or current-score claim.')


if __name__ == '__main__':
    result = inspect()
    path = Path(sys.argv[1])
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('observations','threshold','history_ready','all_latest_inputs_admitted')}))
