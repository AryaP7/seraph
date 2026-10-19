"""Bounded audit counterexamples; no production database writes or model fits."""
import sys, json, tempfile
from pathlib import Path
from datetime import datetime, timedelta
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from seraph.live.inference import InferenceService, Vintage, DecisionRequest
from seraph.live.publication import InputProvenance, MAX_CLOCK_SKEW
from seraph.dashboard.current_reader import read_current
from seraph.validation.harness import mean_lead_time
from seraph.live.store import LiveStore
from seraph.operations.jobs import JobStore

def emit(name, **kw): print(json.dumps(dict(check=name, **kw), default=str))
dt=lambda x: datetime.fromisoformat(x)
day='2026-10-16'
t=dt(day+'T10:00:00+05:30')
v=Vintage('hawkes',day+'T09:55:00+05:30',day+'T09:55:01+05:30',value=.8)
s=InferenceService(session_dates=[day],warmup_observations=0)
s.warm_start([v],cutoff=t)
r=s.process(DecisionRequest('warm',t,'bar_close','historical_replay'))
emit('warm_start',score_exists=r.csrs is not None,filter_tau=s.snapshot().filter_state['tau'],diagnostic=r.pillar_diagnostics['hawkes'])

s=InferenceService(session_dates=[day])
r=s.process(DecisionRequest('first',t,'bar_close','historical_replay'),vintages=[v])
snap=s.snapshot()
restored=InferenceService(session_dates=[day],q_proc=.9)
restored.restore(snap)
emit('restore_different_config',accepted=True,original_q=.001,restored_q=.9,snapshot_id=snap.state_id,restored_id=restored.snapshot().state_id)
v_old=Vintage('hawkes',day+'T09:20:00+05:30',day+'T09:20:01+05:30',value=.1)
r2=s.process(DecisionRequest('late_old',t+timedelta(minutes=5),'bar_close','historical_replay'),vintages=[v_old])
emit('out_of_order_vintage',latest_input=s.snapshot().vintages['hawkes']['input_end'],filter_tau=s.snapshot().filter_state['tau'][0],warnings=r2.warnings)

emit('normal_poll_delay',reasons=InputProvenance('bar:X',t,t+timedelta(seconds=1)).reasons(as_of=t,now=t+timedelta(seconds=1),skew=MAX_CLOCK_SKEW))
class DummyStore:
 def head(self): return SimpleNamespace(updated_at=t.isoformat(),version=4)
 def describe(self): return dict(undelivered_events=0,dead_letters=0)
 def latest_decision(self): return dict(decision_id='old',as_of=(t-timedelta(days=7)).isoformat(),computed_at=(t-timedelta(days=7)).isoformat(),publication_state='current',payload={'csrs':{'csrs':.4}})
cur=read_current(DummyStore(),now=t)
emit('old_score_fresh_worker',is_current=cur.is_current,age_seconds=cur.age_seconds)
emit('legacy_lead_time',one_isolated_crossing=mean_lead_time([.9,0,0,0,0,0],[0,0,0,0,0,1],.5))

with tempfile.TemporaryDirectory(prefix='seraph-audit-',dir=Path(__file__).parent) as tmp:
 store=LiveStore(Path(tmp)/'runtime.sqlite')
 base=dict(decision_id='same',as_of=t.isoformat(),computed_at=t.isoformat(),payload={'csrs':.1},publication_state='withheld',state={})
 store.commit_decision(**base)
 base['payload']={'csrs':.99}
 base['publication_state']='current'
 again=store.commit_decision(**base)
 emit('conflicting_decision_id',accepted_as_replay=again['replayed'],persisted_payload=store.decision('same')['payload'])
 other=LiveStore(Path(tmp)/'runtime.sqlite',stream_id='other')
 emit('cross_stream_latest',other_head=other.head().decision_id,other_latest=other.latest_decision()['decision_id'])
 jobs=JobStore(Path(tmp)/'jobs.sqlite')
 jobs.acquire('audit','old',lease_minutes=1,now=t)
 jobs.acquire('audit','new',lease_minutes=1,now=t+timedelta(minutes=2))
 jobs.checkpoint('audit',{'owner':'new'},run_id='new')
 jobs.checkpoint('audit',{'owner':'old'},run_id='old')
 emit('expired_job_writer',lock_owner=jobs.lock_state('audit')['run_id'],checkpoint_owner=jobs.last_checkpoint('audit')['run_id'])

from streamlit.elements.metric import _parse_value
try:
 _parse_value({'csrs':.4})
 emit('live_metric_dictionary',accepted=True)
except Exception as exc:
 emit('live_metric_dictionary',error=type(exc).__name__,detail=str(exc))
