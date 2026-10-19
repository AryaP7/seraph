"""C13 official listing/document endpoint probes; metadata only."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from seraph.news.http_feed import HttpFeedFetcher
from seraph.news.documents import parse_document
from seraph.news.json_feed import probe_json
urls={
'mofcom_listing':'https://english.mofcom.gov.cn/Policies/AnnouncementsOrders/index.html',
'apeda_dgft':'https://apeda.gov.in/dgft-notifications',
'nse_terms':'https://www.nseindia.com/static/terms-of-use',
}
r={}
f=HttpFeedFetcher(timeout=10)
for name,url in urls.items():
    try:
        status,headers,body=f._open(url,{'User-Agent':f.user_agent})
        r[name]=dict(status=status,metadata=parse_document(body))
        if name=='apeda_dgft':Path('docs/evidence/news-intelligence/apeda-probe.html').write_bytes(body)
    except Exception as e:r[name]=dict(error=str(e))
r['fr_india']=probe_json('https://www.federalregister.gov/api/v1/documents.json?per_page=40&order=newest&conditions[term]=India&fields[]=title&fields[]=html_url&fields[]=publication_date&fields[]=abstract&fields[]=document_number','federal_register',timeout=15)
Path('docs/evidence/news-intelligence/document-probes.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps(r,indent=2))
