"""Bounded current-week calendar, transcribed from the cited official sources."""
from pathlib import Path
import hashlib,json,urllib.request
from datetime import datetime
folder=Path('prototype_runs/exchange_calendar/2026-10-21');folder.mkdir(parents=True,exist_ok=True)
sources=[('holidays.pdf','https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf'),('hours.html','https://www.nseindia.com/static/market-data/market-timings')]
evidence=[]
for name,url in sources:
 p=folder/name
 if not p.exists():
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
  with urllib.request.urlopen(req,timeout=20) as r: p.write_bytes(r.read())
 evidence.append(dict(url=url,file=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),retrieved_at=datetime.now().astimezone().isoformat()))
days=[]
for d in range(19,24):
 row=dict(date=f'2026-10-{d}',status='closed' if d==20 else 'open',evidence_indices=[0,1])
 if d!=20: row.update(kind='regular',windows=[['09:15:00','15:30:00']])
 days.append(row)
doc=dict(schema='nse-cash-calendar/1',start='2026-10-19',end='2026-10-23',evidence=evidence,days=days,note='Bounded current-week transcription; no authority outside this interval. October 20 is Dussehra. Ordinary NSE cash hours; not derivatives or pre-open hours.')
p=folder/'calendar.json';p.write_text(json.dumps(doc,indent=2));print(p)
