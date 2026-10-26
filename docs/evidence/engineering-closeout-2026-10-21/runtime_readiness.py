"""F02: actual configured readiness; never supplies synthetic history."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from scripts.run_live import build,cold_start
from seraph.live import MarketClock
from seraph.live.store import LiveStore
clock=MarketClock();store=LiveStore(Path('prototype_runs/live.sqlite'))
loop,service,_=build(replay=False,store=store,clock=clock)
warm=cold_start(service,store,clock.now())
result=dict(calendar=clock.calendar.completeness(),calendar_verified_today=clock.calendar.verified_for(clock.now().date().isoformat()),feed_type=type(loop.feed).__name__,warm_start=warm,deployments=store.deployments(),live_head=store.describe(),note='Readiness inspection only. No ticks manufactured, no decisions published.')
p=Path(__file__).with_suffix('.json');p.write_text(json.dumps(result,indent=2,default=str));print(json.dumps(result,indent=2,default=str))
