"""F02 bounded configured-feed probe; copies stores and never fabricates ticks."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from seraph.operations.jobs import JobStore
from seraph.shared_types import IST

out = Path(__file__).with_name('runtime-probe-final')
out.mkdir(exist_ok=False)
runtime = out / 'live.sqlite'
jobs = out / 'jobs.sqlite'
with closing(sqlite3.connect((ROOT/'prototype_runs/live.sqlite').as_uri()+'?mode=ro',uri=True)) as source:
    with closing(sqlite3.connect(runtime)) as target:
        source.backup(target)
command = [sys.executable, '-u', str(ROOT/'scripts/run_live.py'), '--once',
           '--once-timeout', '5', '--interval', '1', '--store', str(runtime),
           '--jobs', str(jobs)]
# The persisted public health record is sufficient evidence. Do not retain
# third-party connection logging, which may include credential-bearing URLs.
run = subprocess.run(command, cwd=ROOT, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, timeout=45)
records = JobStore(jobs).runs(limit=1)
result = dict(at=datetime.now(IST).isoformat(), command=command, exit_code=run.returncode,
              observation=records[0].detail if records else None,
              note='Actual configured source, bounded probe against isolated copies; no fallback ticks.')
(out/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
