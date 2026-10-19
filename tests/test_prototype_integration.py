"""Synthetic contract tests; real archive smoke tests are explicitly separate."""
import json
import sqlite3
import pytest
from seraph.orchestration.run_store import RunStore
from seraph.orchestration.prototype import InferenceSession
from seraph.store.writer import _REGISTRY, _upsert_sql, _update_columns
from seraph.features.alignment import aligned_returns


def test_ingestion_update_ownership_and_failed_source_fields():
    for entity,protected in [('E4','g_t'),('E1','is_jump'),('E3','universe_member_flag')]:
        sql=_upsert_sql(_REGISTRY[entity]).split('DO UPDATE SET ')[1]
        assert f'{protected} = EXCLUDED' not in sql
    sql=_upsert_sql(_REGISTRY['E4'],['india_vix','vix_available']).split('DO UPDATE SET ')[1]
    assert 'brent_price' not in sql and 'g_t' not in sql
    with pytest.raises(ValueError): _update_columns(_REGISTRY['E4'],['g_t'])


def test_date_alignment_never_pairs_different_sessions():
    panel,names=aligned_returns({'complete':{1:100,2:101,3:102,4:103},
        'gap':{0:99,1:100,3:102,4:103}},[1,2,3,4],4)
    assert names==('complete',) and panel.shape==(3,1)


def test_flow_display_preserves_the_stored_proxy_without_clipping():
    from seraph.decision_support import flow_diagnostic
    result=flow_diagnostic(dict(fii_net=10,dii_net=20,total_turnover=100,residual_flow_share=-.2))
    assert result.status=='ok' and result.value['residualFlowShare']==-.2
    assert result.warnings


def test_source_reader_applies_cutoff_before_extraction():
    import asyncio
    from seraph.orchestration.original_execution import CutoffIntradayReader
    class Connection:
        async def fetch(self,sql,*args):
            assert 'ts<=$2' in sql and args==('SYNTHETIC','cutoff')
            return []
    reader=CutoffIntradayReader(Connection(),'cutoff')
    assert asyncio.run(reader.fetch('SELECT ts, close FROM intraday_bars WHERE symbol=$1 ORDER BY ts','SYNTHETIC'))==[]


def test_test_database_guard_rejects_application_targets():
    from conftest import validate_test_target
    for name in ['seraph','seraph_research','postgres','']:
        with pytest.raises(ValueError): validate_test_target('postgresql://localhost/'+name,'token')
    with pytest.raises(ValueError): validate_test_target('postgresql://localhost/seraph_test_demo','')
    assert validate_test_target('postgresql://localhost/seraph_test_demo','token')=='seraph_test_demo'


def originals(day,value=.3):
    # An ineligible pillar declares its absence type explicitly (FIX02).
    return {p:dict(score_eligible=p!='hamilton',value=value,
        information_timestamp=day+'T15:30:00+05:30',reason='unvalidated',
        absence=None if p!='hamilton' else 'structural',
        absence_reason=None if p!='hamilton' else 'no_data_coverage')
        for p in ('hawkes','rmt','hamilton')}


def test_restart_replays_exactly_and_missing_is_not_zero():
    days=['2020-01-01','2020-01-02','2020-01-03']
    s=InferenceSession(days); expected=[]
    for d in days: expected.append(s.step(d,originals(d),[],run_id='test'))
    restart=InferenceSession(days)
    assert [restart.step(d,originals(d),[],run_id='test') for d in days]==expected
    assert expected[-1]['coverage']['mask']==[True,True,False]
    assert expected[-1]['composite']['shapley'][2]==0
    missing={p:dict(score_eligible=False,reason='missing',absence='structural',
        absence_reason='no_data_coverage') for p in originals(days[0])}
    assert InferenceSession(days).step(days[0],missing,[],run_id='test')['composite'] is None


def test_future_pillar_rejected_and_portfolio_uncovered():
    s=InferenceSession(['2020-01-01','2020-01-02'])
    with pytest.raises(ValueError): s.step('2020-01-01',originals('2020-01-02'),[],run_id='x')
    p=InferenceSession(['2020-01-01']).step('2020-01-01',originals('2020-01-01'),[],run_id='x',
        holdings=[dict(symbol='SYNTHETIC',quantity=1,value=100,sector='steel')])
    assert p['portfolio']['uncoveredPct']==100 and p['portfolio']['exposedPct']==0


def point_payload(run,day,value=1):
    return {'run_id':run,'date':day,'evaluation_timestamp':day+'T15:30:00+05:30',
        'data_cutoff':day+'T15:30:00+05:30','original_pillars':{},'reconciled':{},
        'composite':None,'coverage':{'mask':[False,False,False]},
        'limitations':[],'value':value}


def test_store_idempotency_collision_and_run_separation(tmp_path):
    store=RunStore(tmp_path/'test.sqlite'); a=store.begin({'config':'a'});b=store.begin({'config':'b'})
    p=point_payload(a,'2020-01-01')
    store.put(a,p);store.put(a,p)
    with pytest.raises(ValueError): store.put(a,point_payload(a,'2020-01-01',value=2))
    with pytest.raises(ValueError): store.put(b,p)
    with pytest.raises(ValueError): store.finish(a,2)
    store.finish(a,1)
    assert len(RunStore(store.path).points(a))==1 and store.points(b)==[]


def test_durable_actions_authorization_retraction_and_retry(tmp_path):
    s=RunStore(tmp_path/'test.sqlite'); run=s.begin({'config':'test'})
    args=dict(alert_id='alert',action='none',decomposition=(.1,.2,.3),at='2020-01-01T15:30:00+05:30')
    with pytest.raises(ValueError): s.action(run,'bad','retail','create',**args)
    first=s.action(run,'1','regulator','create',**args)
    assert s.action(run,'1','regulator','create',**args)==first
    with pytest.raises(ValueError): s.action(run,'1','regulator','create',**dict(args,action='soft_warning'))
    s.action(run,'2','regulator','update',alert_id='alert',action='soft_warning')
    s.action(run,'3','regulator','delete',alert_id='alert')
    log=RunStore(s.path).action_log(run)
    assert len(log.journal())==3 and log.payload()==[]
    assert log.entries(include_retracted=True)[0].retracted
    with pytest.raises(sqlite3.IntegrityError):
        with s.connect() as db: db.execute('DELETE FROM action_events')
    assert len(s.action_log(run).journal())==3


def test_action_transaction_rolls_back_on_failure(tmp_path):
    s=RunStore(tmp_path/'test.sqlite'); run=s.begin({'config':'test'})
    with s.connect() as db:
        db.execute("CREATE TRIGGER reject_event BEFORE INSERT ON action_events BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        s.action(run,'1','regulator','create',alert_id='a',action='none',decomposition=(0,0,0))
    assert s.action_log(run).payload()==[] and s.action_log(run).journal()==()
