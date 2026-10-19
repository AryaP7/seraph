"""Article depth must not weaken provenance, rights, or acquisition bounds."""
from types import SimpleNamespace
from dataclasses import replace
import pytest
from seraph.news.enrichment import EnrichingFetcher, extract_article
from seraph.news.acquisition import FetchedItem, FetchResult, NewsStore
from seraph.news.model import Source
from seraph.news.http_feed import FeedFetchError, HttpFeedFetcher

URL = 'https://www.federalreserve.gov/newsevents/pressreleases/policy.htm'
TEXT = 'The Board adopts a rule on capital requirements. ' * 5
RAW = ('<nav>Proposes a misleading tariff</nav><article><p>'+TEXT+
       '</p><script>Tariff rises 500%</script><table><tr><td>Rate</td><td>5%</td></tr></table></article>').encode()


def source(permitted):
    return Source('fed', 'Federal Reserve', 'official_policy', URL, ('policy',),
                  may_store_full_text=permitted, accessibility_verified=True)


def test_article_excludes_navigation_and_scripts_preserves_table():
    text, truncated = extract_article(RAW, 'text/html')
    assert 'misleading' not in text and '500%' not in text
    assert '| Rate | 5%' in text
    assert TEXT.strip() in text
    assert not truncated


def test_no_article_container_is_an_explicit_abstention():
    with pytest.raises(FeedFetchError):
        extract_article(b'<body>Navigation and ads only</body>', 'text/html')


def router():
    calls = []
    http = HttpFeedFetcher(transport=lambda url, headers:
                           (calls.append(url) or (200, {'Content-Type':'text/html'}, RAW)))
    class Feed:
        _http = http
        def __call__(self, source, cursor):
            return FetchResult((FetchedItem('one', 'A policy decision', URL, b'feed'),))
    return EnrichingFetcher(Feed()), calls


def test_rights_gate_prevents_document_fetch():
    fetcher, calls = router()
    assert fetcher(source(False), None).items[0].body is None
    assert calls == []


def test_document_is_new_immutable_observation_and_idempotent(tmp_path):
    store = NewsStore(tmp_path/'news.sqlite')
    store.register(source(True))
    original = FetchedItem('one', 'A policy decision', URL, b'feed')
    store.ingest('fed', lambda *_: FetchResult((original,)))
    fetcher, calls = router()
    report = store.ingest('fed', fetcher)
    assert report.new_stories == 1 and report.corrections == 1
    stories = store.stories()
    assert len(stories) == 2
    enriched = next(s for s in stories if s.body)
    assert enriched.metadata['text_scope'] == 'article_text'
    assert enriched.first_seen_at >= enriched.metadata['document_acquired_at']
    assert store.ingest('fed', fetcher).new_stories == 0
    assert len(calls) == 1


def test_deferred_documents_resume_after_restart_and_unchanged_feed(tmp_path):
    store = NewsStore(tmp_path/'news.sqlite')
    store.register(source(True))
    original = FetchedItem('one', 'A policy decision', URL, b'feed')
    store.ingest('fed', lambda *_: FetchResult((original,)))
    calls = []
    class Unchanged:
        _http = HttpFeedFetcher(transport=lambda url, headers:
                               (calls.append(url) or (200, {'Content-Type':'text/html'}, RAW)))
        def __call__(self, *_):
            return FetchResult(http_status=304)
    restarted = NewsStore(store.path)
    fetcher = EnrichingFetcher(Unchanged(), store=restarted)
    assert restarted.ingest('fed', fetcher).corrections == 1
    assert len(calls) == 1
    assert not restarted.pending_documents('fed')
    assert restarted.ingest('fed', fetcher).new_stories == 0


def test_failed_document_does_not_starve_later_articles(tmp_path):
    store = NewsStore(tmp_path/'news.sqlite')
    store.register(source(True))
    originals = tuple(FetchedItem(str(i), f'Policy {i}', URL+str(i), str(i).encode()) for i in range(2))
    calls = []
    def transport(url, headers):
        calls.append(url)
        return (403, {}, b'') if url.endswith('0') else (200, {'Content-Type':'text/html'}, RAW)
    class Feed:
        _http = HttpFeedFetcher(transport=transport)
        def __call__(self, *_):
            return FetchResult(originals)
    fetcher = EnrichingFetcher(Feed(), max_documents=1, store=store)
    store.ingest('fed', fetcher)
    # The retry cooldown survives the fetcher and worker, not just this object.
    restarted = EnrichingFetcher(Feed(), max_documents=1, store=NewsStore(store.path))
    assert store.ingest('fed', restarted).corrections == 1
    assert calls == [URL+'0', URL+'1']
    assert 'unavailable' in store.document_attempt('fed', URL+'0')['status']


def test_newly_permitted_documents_can_enrich_old_metadata_only_rows(tmp_path):
    store = NewsStore(tmp_path/'news.sqlite')
    store.register(source(False))
    store.ingest('fed', lambda *_: FetchResult((FetchedItem('one', 'Policy', URL, b'feed'),)))
    original = store.stories()[0]
    assert store.observation(original.observation_id).raw is None
    store.register(source(True))  # Reviewed permission changed; old bytes stay absent.
    class Unchanged:
        _http = HttpFeedFetcher(transport=lambda *_: (200, {'Content-Type':'text/html'}, RAW))
        def __call__(self, *_):
            return FetchResult(http_status=304)
    no_budget = EnrichingFetcher(Unchanged(), store=store, max_documents=0)
    assert store.ingest('fed', no_budget).new_stories == 0
    fetcher = EnrichingFetcher(Unchanged(), store=store)
    assert store.ingest('fed', fetcher).corrections == 1
    enriched = [s for s in store.stories() if s.body][0]
    assert enriched.corrects == original.story_id
    assert enriched.metadata['reconstructed_from_observation'] == original.observation_id
    assert store.observation(original.observation_id).raw is None
