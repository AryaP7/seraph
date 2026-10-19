"""Additional bounded counterexamples; disposable stores, no market fits."""
import sys, json, tempfile
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,r'C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya')
from seraph.live.feed import Tick
from seraph.live.bars import BarBuilder
from seraph.live.clock import MarketClock
from seraph.market_calendar import SessionCalendar
from seraph.decision_support.workspace import WorkspaceStore, parse_holdings
from seraph.identity import IdentityRegistry

def emit(check, **data): print(json.dumps(dict(check=check,**data),default=str))
clock=MarketClock(SessionCalendar(session_dates=frozenset(['2026-10-16'])))
t='2026-10-16T10:00:01+05:30'
b=BarBuilder(clock)
b.add([Tick('X',t,100,100),Tick('X',t,99,101)])
emit('same_timestamp_down_tick',accepted=b.accepted_ticks,partial=b.partial()[0].describe(),quarantine=b.quarantined)
b=BarBuilder(clock); tick=Tick('X',t,100,100); b.add([tick])
resumed=BarBuilder(clock); resumed.restore(b.snapshot())
b.add([tick]); resumed.add([tick])
emit('bar_restart_duplicate',continuous_ticks=b.partial()[0].ticks,resumed_ticks=resumed.partial()[0].ticks)
for value in [float('nan'),float('inf')]:
 try:
  tick=Tick('X',t,value,100)
  builder=BarBuilder(clock); builder.add([tick])
  emit('nonfinite_tick',input=str(value),accepted=True,close=str(builder.partial()[0].close))
 except Exception as exc: emit('nonfinite_tick',input=str(value),accepted=False,error=str(exc))
for rows in [[dict(symbol='X',quantity=2,price=-10)],[dict(symbol='X',value='NaN')]]:
 preview=parse_holdings(json.dumps(rows),source_name='probe.json')
 emit('invalid_portfolio_number',input=rows,accepted=len(preview.accepted),total=str(preview.total_value),rejected=len(preview.rejected))
rows=[dict(symbol='X',value=100,sector='steel'),dict(symbol='X',value=100,sector='it')]
for items in [rows,list(reversed(rows))]:
 p=parse_holdings(json.dumps(items),source_name='probe.json')
 emit('conflicting_sector_merge',first_sector=items[0]['sector'],result_sector=p.accepted[0].sector,warnings=p.warnings)

with tempfile.TemporaryDirectory(prefix='seraph-extra-',dir=Path(__file__).parent) as tmp:
 registry=IdentityRegistry(Path(tmp)/'identity.sqlite')
 workspace=WorkspaceStore(Path(tmp)/'workspace.sqlite',registry)
 registry.add_organisation('audit','Audit household','retail_household')
 user=registry.upsert_user(provider_subject='audit',issuer='https://example.test')
 registry.add_membership(user.user_id,'audit')
 registry.grant(user.user_id,'audit','retail',granted_by='audit-admin')
 principal=registry.resolve(registry.open_session(user.user_id).session_id)
 portfolio=workspace.create_portfolio(principal,name='Audit')
 pid=portfolio['portfolio_id']
 raw=json.dumps([dict(symbol='X',quantity=10)])
 p=workspace.preview_import(principal,pid,raw,source_name='probe.json')
 workspace.commit_import(principal,pid,p,raw,effective_at='2099-01-01T10:00:00+05:30')
 current=workspace.current_holdings(principal,pid)
 emit('future_and_unvalued_holdings',basis=current['basis'],effective=current['effective_at'],holdings=current['holdings'],total=current['total_value'],preview_warnings=p.warnings)
 raw=json.dumps([dict(symbol='Y',value=100)])
 p=workspace.preview_import(principal,pid,raw,source_name='probe.json')
 p.accepted[0]=replace(p.accepted[0],value=999)
 workspace.commit_import(principal,pid,p,raw,effective_at='2099-01-02T10:00:00+05:30')
 current=workspace.current_holdings(principal,pid)
 emit('preview_not_bound_to_bytes',uploaded_value=100,stored_value=current['holdings'][0]['value'],hash_check_passed=True)
