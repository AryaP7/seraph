"""C12/F02 — ordinary launcher ownership on isolated stores, with real workers."""
from contextlib import closing
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time

from audit_console_browser import await_http, free_port

ROOT=Path(__file__).resolve().parents[1]


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    out=out.resolve()
    for name,target in [('seraph.sqlite','runs.sqlite'),('news-intelligence-pilot.sqlite','news.sqlite'),('live.sqlite','live.sqlite')]:
        with closing(sqlite3.connect((ROOT/'prototype_runs'/name).as_uri()+'?mode=ro',uri=True)) as src:
            with closing(sqlite3.connect(out/target)) as dst:
                src.backup(dst)
    for name in ('market-jobs.log','market-jobs-errors.log','live-runtime.log','live-runtime-errors.log','news-worker.log','news-worker-errors.log'):
        p=ROOT/'prototype_runs'/name
        if p.exists():shutil.copy2(p,out/('before-'+name))
    port=free_port()
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONIOENCODING='utf-8',
        SERAPH_MARKET_JOBS_STATUS=str(out/'market-status.json'),SERAPH_ACQUISITION_STATUS=str(out/'acquisition-status.json'))
    report={}
    with (out/'launcher.log').open('w',encoding='utf-8') as log:
        child=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'launch_prototype.ps1'),
            '-Store',str(out/'runs.sqlite'),'-NewsStore',str(out/'news.sqlite'),'-LiveStore',str(out/'live.sqlite'),'-Port',str(port)],
            cwd=ROOT,env=env,stdout=log,stderr=log)
        try:
            await_http(f'http://127.0.0.1:{port}/_stcore/health',timeout=90)
            time.sleep(10)
            report['ordinary_app_started']=True
            report['launcher_pid']=child.pid
            duplicate=subprocess.run([sys.executable,'scripts/run_live.py','--store',str(out/'live.sqlite'),'--once','--once-timeout','1'],
                cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            report['duplicate_stdout']=duplicate.stdout
            report['duplicate_refused']='already owns this store' in duplicate.stdout
            log.flush()
            started=(out/'launcher.log').read_text(encoding='utf-8')
            report['owned_children']=[int(p) for p in re.findall(r'pid (\d+)',started)]
            report['market_news_runtime_started']=all(s in started for s in ('market jobs pid','owned market runtime pid','news worker supervisor pid'))
        finally:
            subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=log,stderr=log,check=False)
            child.wait(timeout=20)
            for name in ('market-jobs.log','market-jobs-errors.log','live-runtime.log','live-runtime-errors.log','news-worker.log','news-worker-errors.log'):
                p=ROOT/'prototype_runs'/name
                if p.exists():shutil.copy2(p,out/name)
    # Check precisely the PIDs created by this launch; never stop other jobs.
    time.sleep(2)
    from seraph.operations.jobs import pid_alive
    report['owned_children_stopped']={str(pid):not pid_alive(pid) for pid in report.get('owned_children',[])}
    report['passed']=bool(report.get('duplicate_refused') and report.get('market_news_runtime_started') and
                          report['owned_children_stopped'] and all(report['owned_children_stopped'].values()))
    report['scope']='Real ordinary startup/duplicate refusal/owned process-tree shutdown; no current-market publication claim. Daily job may still be in progress at shutdown.'
    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    raise SystemExit(main(p.parse_args().output))
