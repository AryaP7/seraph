"""C13 NI00/09/15 copy-migration and real acquisition acceptance, no market refit."""
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_news import register, build_fetcher, poll_once
from seraph.news.acquisition import NewsStore, _now
from seraph.news.registry import load_master_data
from seraph.dashboard.news_view import build_news_payload
from seraph.dashboard.globe_payload import build_globe_payload
from seraph.dashboard.console_backend import renderer_geometry

ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'prototype_runs/news-intelligence-pilot.sqlite'
    original=ROOT/'prototype_runs/news.sqlite'
    if not out.exists() and original.exists():
        with closing(sqlite3.connect(original.resolve().as_uri()+'?mode=ro',uri=True)) as src:
            with closing(sqlite3.connect(out)) as dst:src.backup(dst)
    store=NewsStore(out)
    before=len(store.stories())
    register(store,reprobe=True)
    reports=poll_once(store,build_fetcher(),force=True)
    master,registry=load_master_data()
    now=_now()
    payload=build_news_payload(store,master,decision_ts=now,limit=1000)
    states,countries=renderer_geometry()
    globe=build_globe_payload(payload,master,revision='pilot-real-acquisition',as_of=now,
                              state_meshes=states,country_meshes=countries)
    snapshot=store.save_snapshot(dict(news=payload,globe=globe),available_at=_now(),method=payload['version'])
    report=dict(as_of=now,store=str(out),before_stories=before,after_stories=len(store.stories()),
                ingest=reports,registry=registry,coverage=payload['source_coverage'],snapshot_id=snapshot,
                events=len(payload['surfaces']['signals'].get('items',[])),
                nodes=len(globe['nodes']),edges=globe['edges'],
                signals=[dict(headline=i['headline'],event_type=i['event_type'],impacts=i['impacts'],interpretation=i['interpretation'])
                         for i in payload['surfaces']['signals'].get('items',[]) if i['impacts']])
    (ROOT/'docs/evidence/news-intelligence/live-pilot.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (ROOT/'docs/evidence/news-intelligence/live-globe.json').write_text(json.dumps(globe,indent=2),encoding='utf-8')
    print(json.dumps(dict(store=str(out),stories=report['after_stories'],nodes=report['nodes'],edges=len(globe['edges']),failed=[r['source_id'] for r in reports if not r['ok']]),indent=2))
if __name__=='__main__':main()
