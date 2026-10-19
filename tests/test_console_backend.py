import pytest
from seraph.dashboard.console_backend import project_run, dispatch
from seraph.orchestration.prototype import InferenceSession
from seraph.orchestration.run_store import RunStore


def saved(tmp_path):
    store=RunStore(tmp_path/'ui.sqlite')
    manifest=dict(mode='synthetic test fixture',data_available_through='2020-01-01')
    run=store.begin(manifest)
    inputs={p:dict(score_eligible=False,reason='test missing',absence='structural',
        absence_reason='no_data_coverage') for p in ('hawkes','rmt','hamilton')}
    point=InferenceSession(['2020-01-01']).step('2020-01-01',inputs,[],run_id=run)
    store.put(run,point);store.finish(run,1)
    return store,manifest,point


def event(point,op,**args):
    return dict(id='request-1',run_id=point['run_id'],date=point['date'],op=op,**args)


def test_role_projection_no_restricted_payload(tmp_path):
    store,m,p=saved(tmp_path)
    p['original_pillars']['hawkes']['secret']='sentinel'
    for role in ('retail','institutional','regulator'):
        data=project_run(p,m,[p],role,log=[{'private':'audit'}],report={'x':1})
        assert ('pillars' in data)==(role!='retail')
        assert ('action_log' in data)==(role=='regulator')
        assert ('manifest' in data)==(role=='regulator')
        if role=='retail':assert 'sentinel' not in str(data) and 'private' not in str(data)
    with pytest.raises(ValueError):project_run(p,m,[p],'unknown')


def test_reject_stale_requests_and_unauthorized_actions(tmp_path):
    store,m,p=saved(tmp_path)
    with pytest.raises(ValueError,match='Stale'):dispatch(store,p,'retail',{**event(p,'portfolio'),'date':'1999-01-01'})
    with pytest.raises(ValueError,match='Regulator'):dispatch(store,p,'institutional',event(p,'action'))
    with pytest.raises(ValueError,match='Institutional'):dispatch(store,p,'retail',event(p,'shock'))
    with pytest.raises(ValueError,match='Regulator'):dispatch(store,p,'institutional',event(p,'policy'))
    assert store.action_log(p['run_id']).payload()==[]


def test_holdings_use_real_overlay_not_fabricated_news(tmp_path):
    store,m,p=saved(tmp_path)
    result=dispatch(store,p,'retail',event(p,'portfolio',holdings=[dict(symbol='ABC',value=100,sector='Steel')]))
    assert result['kind']=='portfolio'
    assert result['value']['uncoveredPct']==100
    assert result['value']['exposedPct']==0

def scored(tmp_path):
    from seraph.shared_types import ReconciledState
    from seraph.fusion.score import score
    from seraph.decision_support import explain
    store,m,p=saved(tmp_path)
    state=ReconciledState(ts=p['evaluation_timestamp'],x_hat=(.2,.4,.6),P=((.01,0,0),(0,.01,0),(0,0,.01)),tau_last_update=(p['evaluation_timestamp'],)*3,mask=(True,True,False),mode='kalman')
    weights=InferenceSession([p['date']]).weights
    baseline=score(reconciled=state,xi=(1/3,)*3,weights=weights).value
    p['reconciled']=state.model_dump(mode='json');p['composite']=baseline.model_dump(mode='json');p['explanation']=explain(baseline).value
    return store,m,p


def test_simulation_identity_and_policy_validation(tmp_path):
    store,m,p=scored(tmp_path)
    res=dispatch(store,p,'institutional',event(p,'shock',pillar='rmt',magnitude=0,horizon=3))
    assert all(x['csrs']==pytest.approx(p['composite']['csrs']) for x in res['value'])
    res=dispatch(store,p,'institutional',event(p,'shock',pillar='rmt',magnitude=.1,horizon=3))
    assert res['value'][0]['csrs']>p['composite']['csrs']
    assert res['value'][-1]['csrs']<res['value'][0]['csrs']
    with pytest.raises(ValueError):dispatch(store,p,'regulator',event(p,'policy',xi_path=[[.8,.8,.8]]))
    assert len(dispatch(store,p,'regulator',event(p,'policy',xi_path=[[.8,.1,.1]]))['value'])==1


def test_ui_actions_persist_and_retry_once(tmp_path):
    store,m,p=scored(tmp_path)
    e=event(p,'action',operation='create',action='soft_warning')
    assert dispatch(store,p,'regulator',e)==dispatch(store,p,'regulator',e)
    assert len(store.action_log(p['run_id']).journal())==1
    dispatch(store,p,'regulator',{**e,'id':'second','operation':'update','action':'none'})
    dispatch(store,p,'regulator',{**e,'id':'third','operation':'delete'})
    assert RunStore(store.path).action_log(p['run_id']).entries(include_retracted=True)[0].retracted


def test_scored_retail_projection_omits_internals(tmp_path):
    store,m,p=scored(tmp_path)
    view=project_run(p,m,[p],'retail')['view']
    assert 'shapley' not in view and 'pillarScores' not in view and 'actionLog' not in view
    assert view['csrs']==p['composite']['csrs']


def test_role_change_drops_restricted_prior_results(tmp_path):
    store,m,p=scored(tmp_path)
    for kind in ('action','policy','shock'):
        assert project_run(p,m,[p],'retail',result={'kind':kind,'value':'private'})['result'] is None
    assert project_run(p,m,[p],'institutional',result={'kind':'action','value':'private'})['result'] is None
