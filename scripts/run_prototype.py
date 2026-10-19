"""Canonical, restartable historical prototype. No source database writes."""
import argparse
import json
import sys
import os
import asyncio
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from seraph.market_calendar import DECISION_POLICIES
from seraph.orchestration.prototype import ROOT, run_archive, run_source_endpoint

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--store',type=Path,default=ROOT/'prototype_runs/seraph.sqlite')
    p.add_argument('--from',dest='start',default='2020-01-01')
    p.add_argument('--to',dest='end',default='2020-04-30')
    p.add_argument('--holdings',type=Path,help='Optional real user-supplied holdings JSON; never invented')
    p.add_argument('--source-date',help='Fresh original-model diagnostic endpoint; requires SERAPH_SOURCE_DB_DSN. No archive fallback.')
    p.add_argument('--decision-clock',choices=DECISION_POLICIES,default='session_close',
        help="session_close: evaluate at each session's declared close, so an authorised "
             'special-session close may use that session own later vintage. standard_1530: '
             'pin every decision to the regular 15:30 IST close and withhold later vintages.')
    a=p.parse_args()
    holdings=json.loads(a.holdings.read_text()) if a.holdings else None
    if a.source_date:
        dsn=os.environ.get('SERAPH_SOURCE_DB_DSN')
        if not dsn: p.error('Set SERAPH_SOURCE_DB_DSN explicitly for read-only source execution')
        result=asyncio.run(run_source_endpoint(a.store,dsn,a.source_date,holdings))
    else:
        result=run_archive(a.store,start=a.start,end=a.end,holdings=holdings,
            decision_policy=a.decision_clock)
    print(json.dumps(result,indent=2))
