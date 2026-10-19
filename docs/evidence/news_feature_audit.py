"""Read-only SERAPH audit; writes only its explicitly requested audit output."""
import sys, sqlite3, json
from pathlib import Path
from collections import Counter
from dataclasses import replace
ROOT=Path(r'C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya')
sys.path.insert(0,str(ROOT))
from seraph.news.model import Story, Event, syndication_key
from seraph.news.registry import load_master_data, MasterData
from seraph.news.extraction import extract, classify
from seraph.news.estimation import direction_of, severity_of, evidence_confidence_of
from seraph.product_types import Timing
db=sqlite3.connect((ROOT/'prototype_runs/news.sqlite').as_uri()+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
sources=[json.loads(r['payload']) for r in db.execute('select payload from sources')]
rows=[dict(r) for r in db.execute('select * from stories order by first_seen_at,story_id')]
master, registry=load_master_data()
events=[]
for r in rows:
    story=Story(story_id=r['story_id'],source_id=r['source_id'],observation_id=r['observation_id'],title=r['title'],url=r['url'],timing=Timing(first_seen_at=r['first_seen_at'],published_at=r['published_at']),body=r['body'],syndication_group=r['syndication_group'])
    e=extract([story],master).event
    events.append({'title':r['title'],'event_type':e.event_type if e else None,'direction':direction_of(e) if e else None,'affected':list(e.affected) if e else [],'locations':list(e.locations) if e else []})
t=Timing(first_seen_at='2026-10-17T12:00:00+05:30',published_at='2026-10-17T11:00:00+05:30')
cases=[
('rate_cut','RBI cuts repo rate by 25 basis points','must not default to adverse for every target'),
('rate_hold','RBI holds repo rate unchanged','not a directional shock without expectations'),
('subsidy_withdrawal','Government withdraws subsidy for solar manufacturers','must not default to favourable'),
('negated_halt','Factory denies reports of production halt','must not create a confirmed halt'),
('proposed_tariff','Government proposes 50% tariff; consultation opens','proposal is not enacted or effective'),
('tariff_reduction','Import duty cut from 50% to 5%','old level is not a 50 percentage point increase'),
('port_routine','Port publishes annual report','port mention is not disruption'),
('expansion_cancelled','Company cancels new plant expansion','must not default to favourable'),
('routine_statistics','Weekly Statistical Supplement','publication itself has no adverse direction'),
('official_speech','Speech by Governor on financial inclusion','speech alone has no adverse direction')]
probes=[]
for key,title,expectation in cases:
    s=Story(key,'audit','audit_'+key,title,'https://example.invalid/'+key,t,syndication_group=key)
    e=extract([s],MasterData()).event
    probes.append({'id':key,'input':title,'expected_property':expectation,'actual':{'type':e.event_type,'direction':direction_of(e),'severity':severity_of(e),'quantities':e.quantities,'lifecycle':e.lifecycle,'occurred_at':e.timing.occurred_at}})
e=Event('test','tariff_announcement','test',t,('same_publisher_story_1','same_publisher_story_2'))
output={'scope':'2026-10-17 read-only audit; synthetic probes are counterexamples, not market validation','source_count':len(sources),'provider_count':len(set(s['provider'] for s in sources)),'sources':sources,'story_count':len(rows),'stories_with_body':sum(bool(r['body']) for r in rows),'stories_by_source':dict(Counter(r['source_id'] for r in rows)),'first_seen_range':[min(r['first_seen_at'] for r in rows),max(r['first_seen_at'] for r in rows)],'health':[dict(r) for r in db.execute('select * from source_health')],'registry':registry,'real_story_extractions':events,'adversarial_probes':probes,'confirmation_probe':{'two_story_ids_count':e.confirmations,'single_story_high_path_confidence':evidence_confidence_of(replace(e,stories=('one',)),'high'),'expected':'story IDs are not independent reporting origins; categorical high is not calibrated probability'}}
dest=Path(__file__).with_name('NEWS-FEATURE-AUDIT-EVIDENCE-2026-10-17.json')
dest.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({k:v for k,v in output.items() if k not in ('sources','real_story_extractions','health')},indent=2,ensure_ascii=False))
