"""C13 NI08 — bounded, rights-gated official document enrichment.

Only configured government hosts are followed. Navigation, scripts and third
party pages are excluded; missing/blocked content remains a named limitation.
Enriched bytes create a new immutable observation/correction through NewsStore.
"""
from dataclasses import replace
from html.parser import HTMLParser
from urllib.parse import urlsplit
import hashlib
import re
import time

from seraph.news.acquisition import _now
from seraph.news.http_feed import FeedFetchError

HOSTS = {'www.federalreserve.gov', 'www.federalregister.gov', 'www.govinfo.gov',
         'pib.gov.in', 'www.pib.gov.in'}


class ArticleText(HTMLParser):
    """Keep article/main containers, with table row/cell boundaries intact."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        selector = (attrs.get('id', '') + ' ' + attrs.get('class', '')).lower()
        parent = self.stack[-1][1:] if self.stack else (False, False)
        # `pre` is a container here because for a whole class of official
        # documents it IS the document: the GPO publishes every Federal
        # Register notice as `<html><body><pre>…</pre></body></html>`, with
        # no `article` or `main` anywhere. Without it those pages parsed to
        # nothing and were refused as "no usable article container", which
        # is why no Federal Register full text was ever retrieved. A page
        # that has a real container still wins -- `pre` inside it is
        # already active -- so this only decides pages that have nothing
        # else, and the existing length guard still refuses a stray code
        # sample.
        active = parent[0] or tag in ('article', 'main', 'pre') or any(
            token in selector.split() for token in
            ('article__body', 'article-body', 'document-body', 'document-content',
             'col-md-8', 'pressreleasemain', 'pressreleasepage', 'pressreleasecontent'))
        blocked = parent[1] or tag in ('script', 'style', 'nav', 'header', 'footer', 'form', 'aside')
        if tag not in ('br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'wbr'):
            self.stack.append((tag, active, blocked))
        if active and not blocked and tag in ('p', 'div', 'tr', 'br', 'li', 'h1', 'h2', 'h3'):
            self.parts.append('\n')
        if active and not blocked and tag in ('td', 'th'):
            self.parts.append(' | ')

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, text):
        if self.stack and self.stack[-1][1] and not self.stack[-1][2]:
            self.parts.append(text)

    def text(self):
        return '\n'.join(re.sub(r'\s+', ' ', line).strip()
                         for line in ''.join(self.parts).splitlines() if line.strip())


def extract_article(raw, content_type, *, seconds=10):
    incomplete = False
    if 'application/pdf' in content_type or raw.startswith(b'%PDF-'):
        from seraph.news.pdf_text import extract_pdf
        try:
            text, incomplete = extract_pdf(raw, seconds=seconds)
        except (ValueError, TimeoutError) as exc:
            raise FeedFetchError(str(exc)) from exc
    elif 'html' in content_type:
        parser = ArticleText()
        parser.feed(raw.decode('utf-8', errors='replace'))
        text = parser.text()
    elif 'text/plain' in content_type:
        text = raw.decode('utf-8', errors='replace').strip()
    else:
        raise FeedFetchError('unsupported document format; no full-text claim')
    if len(text) < 100 or any(s in text.lower() for s in
                              ('access denied', 'verify you are human', 'request access to')):
        raise FeedFetchError('no usable article container; keep feed evidence only')
    return text[:200_000], incomplete or len(text) > 200_000


class EnrichingFetcher:
    """Retrieve permitted document text, once, and then stop paying for it.

    The defect this closes (audit A08): nothing persisted a successful
    retrieval. The per-process cache died with the process and the
    `document_attempts` cooldown explicitly did not apply to the
    `retrieved` status, so every pass re-fetched the FIRST permitted URL,
    spent the whole document budget on it, and marked the second document
    `deferred_for_budget`. With a one-document budget the second document
    never got a body — not after a restart, not after a hundred passes.

    Two changes, and they are the same change: the text is persisted, so
    reusing it costs nothing and produces the SAME bytes (an idempotent
    observation rather than a spurious correction); and the budget goes to
    documents that do not have text yet, least-recently-attempted first.
    """

    def __init__(self, fallback, *, max_documents=3, seconds=12, store=None):
        self.fallback = fallback
        self._http = fallback._http
        self.max_documents = max_documents
        self.seconds = seconds
        self.store = store
        self.cache = {}  # URL -> text, hash, incomplete, monotonic time, format, acquisition time
        self.failures = {}  # bounded retry cooldown when no store is supplied

    @staticmethod
    def _retrieval_url(item):
        """Where the TEXT is read from, which is not always the citation.

        federalregister.gov answers a document request with a 302 to its
        `unblock` interstitial -- the publisher declining automated
        access. That is not ours to work around, and the host allow-list
        correctly refuses to follow it. The adapter supplies
        `document_url` when the same work is published somewhere this
        client may actually read it (the GPO's govinfo.gov, already
        permitted), and the reader still cites `item.url`.
        """
        return ((item.metadata or {}).get('document_url')) or item.url

    def _permitted(self, url):
        split = urlsplit(url)
        return (split.hostname or '').lower() in HOSTS and split.scheme == 'https'

    def _cooling(self, source_id, url, attempt):
        return bool((attempt and attempt['retry_at'] > _now()
                     and attempt['status'] != 'retrieved')
                    or self.failures.get(url, 0) > time.monotonic())

    def __call__(self, source, cursor):
        result = self.fallback(source, cursor)
        # Retrieval of the document itself is a separate permission
        # from keeping its text. A source that may be fetched and
        # processed but not stored gets no document pass here,
        # because there is nowhere permitted to put the result.
        if not (source.permits('fetch') and source.permits('store')):
            return result
        deadline = min(time.monotonic() + self.seconds,
                       getattr(self, 'deadline_at', None) or float('inf'))
        candidates = list(result.items)
        references = {item.reference for item in candidates}
        if self.store is not None:
            candidates.extend(item for item in self.store.pending_documents(source.source_id)
                              if item.reference not in references)

        # --- who gets this pass's budget --------------------------------
        # Decided BEFORE fetching and over the whole candidate set, so a
        # document that already has text cannot take the budget from one
        # that has none. Among those that have none, the one attempted
        # longest ago goes first: that is what makes the queue drain
        # instead of rotating around its head.
        stored = {}
        outstanding = []
        for item in candidates:
            target = self._retrieval_url(item)
            if not self._permitted(target) or target in stored:
                continue
            record = (self.store.document(source.source_id, target)
                      if self.store is not None else None)
            stored[target] = record
            attempt = (self.store.document_attempt(source.source_id, target)
                       if self.store else None)
            fresh_enough = record is not None and not record['due_for_refresh']
            if fresh_enough or self._cooling(source.source_id, target, attempt):
                continue
            outstanding.append(((attempt or {}).get('attempted_at') or '',
                                target))
        outstanding.sort()
        allowed = {url for _stamp, url in outstanding[:max(0, self.max_documents)]}

        items, fetched = [], 0
        for item in candidates:
            metadata = dict(item.metadata or {})
            metadata.setdefault('text_scope', 'feed_summary' if item.body else 'headline_only')
            target = self._retrieval_url(item)
            host = (urlsplit(target).hostname or '').lower()
            permitted = self._permitted(target)
            # Restrict redirects too: the generic feed transport remains
            # usable, while document retrieval cannot follow off-host links.
            cached = self.cache.get(target)
            if cached and time.monotonic() - cached[3] > 3600:
                cached = None
            if cached is None:
                # Text already on file. Reused without a request, and the
                # bytes are the ones the earlier pass stored, so the
                # observation collapses onto the existing one instead of
                # publishing a body-less correction over it.
                record = stored.get(target)
                if record is not None and not record['due_for_refresh']:
                    cached = (record['text'], record['document_hash'],
                              record['truncated'], time.monotonic(),
                              record['format'], record['acquired_at'])
                    self.cache[target] = cached
            attempt = self.store.document_attempt(source.source_id, target) if self.store else None
            cooling = self._cooling(source.source_id, target, attempt)
            if not permitted:
                metadata['document_status'] = 'host_not_enabled'
                if self.store and attempt is None:
                    self.store.record_document_attempt(source.source_id, target,
                                                       'host_not_enabled', retry_seconds=86400)
            elif cached is None and cooling:
                metadata['document_status'] = 'retry_deferred'
            elif (cached is None and target in allowed
                  and fetched < self.max_documents and deadline-time.monotonic() > 1):
                fetched += 1
                try:
                    self._http._throttle(host)
                    status, headers, raw = self._http._open(
                        target, {'User-Agent': self._http.user_agent,
                                   'Accept': 'text/html,application/pdf,text/plain;q=0.9'},
                        timeout=max(.1, deadline-time.monotonic()),
                        allowed_hosts=HOSTS)
                    if status != 200:
                        raise FeedFetchError(f'document HTTP {status}')
                    content_type = headers.get('Content-Type', '').lower()
                    text, truncated = extract_article(raw, content_type,
                                                      seconds=deadline-time.monotonic())
                    format_ = 'pdf' if 'application/pdf' in content_type or raw.startswith(b'%PDF-') else 'article'
                    cached = (text, hashlib.sha256(raw).hexdigest(), truncated,
                              time.monotonic(), format_, _now())
                    self.cache[target] = cached
                    if len(self.cache) > 500:
                        self.cache.pop(next(iter(self.cache)))
                    if self.store:
                        self.store.record_document_attempt(source.source_id, target, 'retrieved')
                        # Durable, so the next pass spends its budget on a
                        # document that still has none.
                        self.store.save_document(
                            source.source_id, target, text=text,
                            document_hash=cached[1], format=format_,
                            truncated=truncated, acquired_at=cached[5])
                except Exception as exc:
                    metadata['document_status'] = f'unavailable: {type(exc).__name__}: {exc}'
                    self.failures[target] = time.monotonic() + 3600
                    if len(self.failures) > 500:
                        self.failures.pop(next(iter(self.failures)))
                    if self.store:
                        self.store.record_document_attempt(source.source_id, target,
                                                           metadata['document_status'])
            elif cached is None:
                metadata['document_status'] = 'deferred_for_budget'
            if cached:
                text, digest, truncated, _, format_, acquired = cached
                metadata.update(document_status='retrieved', document_hash=digest,
                                document_url=target,
                                text_scope=(format_+'_partial' if truncated else format_+'_text'),
                                document_format=format_, document_acquired_at=acquired,
                                document_truncated=truncated)
                item = replace(item, body=text, raw=item.raw+b'\nDOCUMENT\n'+text.encode('utf-8'))
            elif metadata.get('document_recovery_only'):
                continue  # No new evidence arrived; do not publish a correction.
            items.append(replace(item, metadata=metadata))
        return replace(result, items=tuple(items))
