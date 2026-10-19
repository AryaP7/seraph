"""C13 NI08 — real bounded document retrieval on an isolated pilot-store copy."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seraph.news.acquisition import NewsStore, FetchResult, _now
from seraph.news.enrichment import EnrichingFetcher
from seraph.news.http_feed import HttpFeedFetcher
from seraph.news.registry import load_master_data


def main(output):
    if output.exists():
        raise ValueError('refusing to overwrite evidence')
    source = ROOT/'prototype_runs/news-intelligence-pilot.sqlite'
    target = ROOT/'prototype_runs'/('document-recovery-'+uuid4().hex[:8]+'.sqlite')
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    store = NewsStore(target)
    before = store.stories()
    class UnchangedFeed:
        _http = HttpFeedFetcher(timeout=8)
        def __call__(self, source, cursor):
            return FetchResult(http_status=304, cursor=cursor)
    fetcher = EnrichingFetcher(UnchangedFeed(), store=store, max_documents=2, seconds=12)
    results = []
    for source_id in ('fed_press', 'federalreserve_speeches', 'federal_register'):
        if source_id in {s.source_id for s in store.sources()}:
            results.append(store.ingest(source_id, fetcher).describe())
    stories = store.stories()
    old_ids = {s.story_id for s in before}
    enriched = [s for s in stories if s.story_id not in old_ids]
    master, registry = load_master_data()
    with store.connect() as db:
        attempts = [dict(zip(('source','url','at','retry_at','status'), row))
                    for row in db.execute('SELECT * FROM document_attempts')]
    report = dict(generated_at=_now(), isolated_store=str(target),
                  original_store_unchanged=True, simulated_feed_304=True,
                  document_http_requests_real=True, reports=results,
                  production=dict(sources=len(store.sources()), stories=len(before),
                                  nonempty_bodies=sum(bool(s.body and s.body.strip()) for s in before)),
                  registry=registry, issuers=sum(e.kind == 'issuer' for e in master.entities.values()),
                  issuers_with_sector=sum(e.kind == 'issuer' and bool(e.sector) for e in master.entities.values()),
                  assets_with_coordinates=sum(a.lat is not None and a.lon is not None for a in master.assets.values()),
                  attempts=attempts, new_documents=[dict(story_id=s.story_id, url=s.url,
                  characters=len(s.body or ''), metadata=s.metadata) for s in enriched])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(new_documents=len(enriched), attempts=len(attempts),
                         registry=registry, evidence=str(output))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
