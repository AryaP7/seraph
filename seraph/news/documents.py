"""C13 NI08 — bounded official HTML metadata acquisition.

No browser automation, paywall bypass or arbitrary follow links. Metadata-only
sources retain the title/link/hash; body storage still follows Source rights.
"""
from __future__ import annotations
from html.parser import HTMLParser
import re
from seraph.news.acquisition import FetchedItem, FetchResult
from seraph.news.http_feed import HttpFeedFetcher, FeedFetchError

class DocumentMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title=[]
        self.headings=[]
        self.in_title=False
        self.in_heading=False
        self.meta={}
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='title':self.in_title=True
        if tag=='h1':self.in_heading=True
        if tag=='meta':
            self.meta[attrs.get('property',attrs.get('name','')).lower()]=attrs.get('content','')
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
        if tag=='h1':self.in_heading=False
    def handle_data(self,data):
        if self.in_title:self.title.append(data)
        if self.in_heading:self.headings.append(data)

def parse_document(body: bytes):
    parser=DocumentMetadata()
    parser.feed(body.decode('utf-8',errors='replace'))
    title=parser.meta.get('og:title') or ' '.join(parser.headings) or ' '.join(parser.title)
    title=re.sub(r'\s+',' ',title).strip()
    if not title or any(t in title.lower() for t in ('access denied','just a moment','403 forbidden')):
        raise FeedFetchError('official document did not return usable title metadata')
    return dict(title=title, published_at=None)

class DocumentFetcher:
    def __init__(self, fallback, document_sources):
        self.fallback=fallback
        self.document_sources=set(document_sources)
        self._http=getattr(fallback,'_http',HttpFeedFetcher())
    def __call__(self,source,cursor):
        if source.source_id not in self.document_sources:
            return self.fallback(source,cursor)
        from urllib.parse import urlsplit
        self._http._throttle(urlsplit(source.url).netloc)
        status,headers,body=self._http._open(source.url,{'User-Agent':self._http.user_agent,'Accept':'text/html'})
        if status!=200:raise FeedFetchError(f'HTTP {status} fetching official document')
        meta=parse_document(body)
        # Hash permitted metadata; dynamic visitor counts must not create corrections.
        item=FetchedItem(source.url,meta['title'],source.url,meta['title'].encode(),published_at=None)
        return FetchResult((item,),cursor=cursor,http_status=status)

class OfficialListing(HTMLParser):
    """Only same-publisher policy document links; navigation is excluded."""
    def __init__(self, base_url, path_prefix):
        super().__init__(convert_charrefs=True)
        self.base_url,self.path_prefix=base_url,path_prefix
        self.links=[]
        self.url=None
        self.parts=[]
    def handle_starttag(self,tag,attrs):
        from urllib.parse import urljoin,urlsplit
        if tag!='a':return
        url=urljoin(self.base_url,dict(attrs).get('href',''))
        parts=urlsplit(url)
        if parts.scheme=='https' and parts.netloc==urlsplit(self.base_url).netloc and parts.path.startswith(self.path_prefix):
            self.url=url;self.parts=[]
    def handle_data(self,data):
        if self.url:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.url:
            title=re.sub(r'\s+',' ',' '.join(self.parts)).strip()
            if title:self.links.append((self.url,title))
            self.url=None

class ListingFetcher:
    def __init__(self, fallback, listings):
        self.fallback=fallback
        self.listings=listings
        self._http=fallback._http
    def __call__(self,source,cursor):
        if source.source_id not in self.listings:return self.fallback(source,cursor)
        from urllib.parse import urlsplit
        self._http._throttle(urlsplit(source.url).netloc)
        status,headers,body=self._http._open(source.url,{'User-Agent':self._http.user_agent,'Accept':'text/html'})
        if status!=200:raise FeedFetchError(f'HTTP {status} from official listing')
        parser=OfficialListing(source.url,self.listings[source.source_id])
        parser.feed(body.decode('utf-8',errors='replace'))
        if not parser.links:raise FeedFetchError('official listing has no recognised document links')
        items=tuple(FetchedItem(url,title,url,title.encode(),metadata={'publication_precision':'unknown','acquisition':'official_listing_metadata'})
                    for url,title in dict(parser.links).items())
        return FetchResult(items,cursor=cursor,http_status=status)
