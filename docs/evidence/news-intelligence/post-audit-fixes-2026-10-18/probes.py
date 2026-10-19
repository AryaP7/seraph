"""Independent continuation audit: isolated counterexamples, no production writes."""
import contextlib
from datetime import datetime, timedelta
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from seraph.news.acquisition import NewsStore, FetchedItem, FetchResult, _now
from seraph.news.model import Source, Story, syndication_key
from seraph.news.enrichment import EnrichingFetcher
from seraph.news.http_feed import HttpFeedFetcher
from seraph.news.registry import MasterData, load_master_data
from seraph.news.extraction import extract_events
from seraph.news.currency import partition
from seraph.product_types import Timing
from seraph.operations.jobs import JobStore
from seraph.dashboard.news_view import build_news_payload
from seraph.validation.news_gate import SliceResult, REQUIRED_SLICES
from seraph.validation.news_corpus import score_gold

T0 = '2026-10-18T08:00:00+05:30'
T1 = '2026-10-18T09:00:00+05:30'
T2 = '2026-10-18T10:00:00+05:30'
URL = 'https://www.federalreserve.gov/news/'


def source():
    return Source('feed', 'Feed', 'official_policy', URL, ('policy',),
                  may_store_full_text=True, accessibility_verified=True)


def main():
    report = {}
    with tempfile.TemporaryDirectory(prefix='seraph-news-audit-') as directory:
        tmp = Path(directory)
        store = NewsStore(tmp/'reversion.sqlite')
        store.register(source())
        reports = []
        for stamp, value in [(T0,'A'),(T1,'B'),(T2,'A')]:
            item = FetchedItem('doc', f'Policy version {value}', URL+'doc', value.encode())
            reports.append(store.ingest('feed', lambda *_: FetchResult((item,)), now=stamp).describe())
        report['reverted_document'] = dict(ingests=reports,
            current=[s.title for g in store.syndication_groups().values() for s in g], expected='Policy version A')

        store = NewsStore(tmp/'enrich.sqlite')
        store.register(source())
        calls = []
        raw = b'<article>' + b'The Board has adopted a capital rule. '*8 + b'</article>'
        class Feed:
            _http = HttpFeedFetcher(transport=lambda url, headers:
                (calls.append(url) or (200, {'Content-Type':'text/html'}, raw)))
            def __call__(self, *_):
                return FetchResult(tuple(FetchedItem(str(i),f'Policy {i}',URL+str(i),str(i).encode()) for i in range(2)))
        for _ in range(3):
            fetcher = EnrichingFetcher(Feed(), store=store, max_documents=1)
            fetcher._http._throttle = lambda *_: None
            store.ingest('feed', fetcher)
        report['document_budget_starvation'] = dict(calls=calls,
            current=[dict(title=s.title, body=bool(s.body)) for g in store.syndication_groups().values() for s in g],
            condition='restarted fetcher (also models expired per-process success cache) on repeated HTTP 200 feed')

        # Exercise the actual worker loop with a lease left by a dead process.
        spec = importlib.util.spec_from_file_location('audit_run_news', ROOT/'scripts/run_news.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        jobs = JobStore(tmp/'jobs.sqlite')
        jobs.acquire(module.JOB, 'abandoned')
        store = NewsStore(tmp/'worker.sqlite')
        fetched, waiting = [], []
        def sleep(_):
            waiting.append(store.worker_state(_now()))
            raise KeyboardInterrupt
        args = SimpleNamespace(jobs=tmp/'jobs.sqlite', backfill=False, once=False,
                               catch_up=False, interval=30)
        with patch.object(module,'register',lambda *a,**k:None), \
             patch.object(module,'build_fetcher',lambda *a:None), \
             patch.object(module,'poll_once',lambda *a,**k:fetched.append(True) or []), \
             patch.object(module,'show_status',lambda *a:0), \
             patch.object(module.time,'sleep',sleep), contextlib.redirect_stdout(io.StringIO()):
            module._run_worker(args,store)
        report['abandoned_job_lease'] = dict(fetch_calls=len(fetched), waiting=waiting,
            job_runs=[r.describe() for r in jobs.runs()], lease=jobs.lock_state(module.JOB))

        store = NewsStore(tmp/'replay.sqlite')
        store.register(source())
        store.beat(now=T2, pid=42, status='running', detail='future worker information')
        store.open_gap(source_id='feed', since=T1, until=T2, recoverable=True, now=T2)
        payload = build_news_payload(store, MasterData(), decision_ts=T0, strict_replay=True, role='regulator')
        report['strict_replay_future_operational_data'] = dict(
            replay_at=T0, worker=payload['freshness']['worker'], role_items=payload['role_view']['items'])

        titles = ['सरकार ने इस्पात पर शुल्क बढ़ाया', 'बंदरगाह पर काम बंद हुआ']
        report['hindi_syndication_collision'] = dict(titles=titles,keys=[syndication_key(t) for t in titles])

        old = Story('old','feed','o1','Certain Hot-Rolled Steel From India: Antidumping Duty Order',URL+'old',Timing(first_seen_at=T0))
        new = Story('new','feed','o2','Certain Hot-Rolled Steel From India: Revocation of the Antidumping Duty Order',URL+'new',Timing(first_seen_at=T1))
        events = [r.event for s in (old,new) for r in extract_events([s], MasterData()) if r.event]
        current = partition(events,T2)
        report['unlinked_repeal'] = dict(events=[dict(id=e.event_id, title=e.headline,
            supersedes=e.supersedes, stage=e.frame.policy_status,
            instrument_ids=list(e.instrument_ids)) for e in events],
            states=current['states'], supersession=current['supersession'],
            applicability={e.event_id: current['states'][e.event_id]['applicability']['state'] for e in events})

        # The same pair, where the documents DO cite a shared case number,
        # and again where a reviewer supplies the link the documents lack.
        cited_old = Story('co','feed','o3','Hot-Rolled Steel From India (A-533-863): Antidumping Duty Order',URL+'co',Timing(first_seen_at=T0))
        cited_new = Story('cn','feed','o4','Hot-Rolled Steel From India (A-533-863): Revocation of the Antidumping Duty Order',URL+'cn',Timing(first_seen_at=T1))
        cited = [r.event for s in (cited_old,cited_new) for r in extract_events([s], MasterData()) if r.event]
        linked = partition(cited,T2)
        reviewed = partition(events,T2,confirmed_links=[(events[1].event_id, events[0].event_id)])
        report['linked_repeal'] = dict(
            instrument_ids={e.event_id: list(e.instrument_ids) for e in cited},
            applicability={e.event_id: linked['states'][e.event_id]['applicability']['state'] for e in cited},
            links=linked['supersession']['links'],
            reviewed_applicability={e.event_id: reviewed['states'][e.event_id]['applicability']['state'] for e in events})

        slices = {n:SliceResult(n) for n in REQUIRED_SLICES}
        negative = dict(event_type='other',action='unknown',policy_status='unknown',targets=[],quantities=[])
        for _ in range(95):
            score_gold(slices, negative, negative)
        for _ in range(5):
            score_gold(slices, {}, dict(negative,event_type='production_halt'))
        report['class_recall_negative_inflation'] = dict(reported=slices['class_recall'].describe(),
            actual_supported_events_found=0, actual_supported_events=5)

    with contextlib.closing(sqlite3.connect((ROOT/'prototype_runs/news-intelligence-pilot.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
        count = lambda sql: db.execute(sql).fetchone()[0]
        sources = [json.loads(r[0]) for r in db.execute('SELECT payload FROM sources')]
        report['production_read_only'] = dict(sources=len(sources), publishers=len({s['provider'] for s in sources}),
            stories=count('SELECT COUNT(*) FROM stories'),
            nonempty_bodies=count("SELECT COUNT(*) FROM stories WHERE trim(coalesce(body,''))!=''"),
            source_permissions={s['source_id']:s['may_store_full_text'] for s in sources},
            heartbeat=[dict(zip(('worker','beat_at','pid','status','activity'),r)) for r in db.execute('SELECT worker,beat_at,pid,status,activity FROM worker_heartbeat')],
            hindi_groups=[dict(key=r[0],count=r[1]) for r in db.execute("SELECT syndication_group,COUNT(*) FROM stories WHERE language='hi' GROUP BY syndication_group HAVING COUNT(*)>1")])
    master, info = load_master_data()
    report['registry'] = dict(info,issuers=sum(e.kind=='issuer' for e in master.entities.values()),
        issuers_with_sector=sum(e.kind=='issuer' and bool(e.sector) for e in master.entities.values()),
        exact_asset_coordinates=sum(a.lat is not None and a.lon is not None for a in master.assets.values()))
    path = Path(__file__).with_name('findings.json')
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=True))


if __name__ == '__main__':
    main()
