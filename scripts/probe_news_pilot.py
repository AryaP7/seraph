"""C13 NI09 bounded, reproducible source probes; no production writes."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from seraph.news.http_feed import probe
urls={
'pib_delhi':'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1',
'pib_english':'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=2&Regid=3',
'fed':'https://www.federalreserve.gov/feeds/press_all.xml',
'nse':'https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml',
}
rows={key:probe(url,timeout=12) for key,url in urls.items()}
path=Path('docs/evidence/news-intelligence/pilot-probes.json')
path.write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
