"""F04/F07/F08/F09 — arithmetic, direction, artifacts and evidence boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from seraph.decision_support.defensive import compare
from seraph.pillars.hamilton.engine import HamiltonEngine, MultivariateTVTPHamilton, project_xi
from seraph.pillars.hamilton.projection import artifact, project, reconstruct, transform


def defensive_request():
    dates=[f'2020-02-{d:02d}T15:30:00+05:30' for d in (20,21,24,25,26)]
    def series(values,kind):
        return dict(prices=[dict(at=t,price=p) for t,p in zip(dates,values)],kind=kind,
                    currency='INR',multiplier=1.,source='explicit synthetic arithmetic fixture',
                    mode='synthetic_test',price_basis='synthetic adjusted prices')
    base=dict(execution_at=dates[1],transaction_cost_bps=10.,fixed_cost=0.,carry_per_session=0.)
    put=series([2,2,8,15,5],'index_put')
    put.update(price_basis='observed_option_premium',strike=100.,underlying='risk',expiry_at=dates[-1])
    return dict(epoch='covid_2020',currency='INR',valuation_times=dates,decision_at=dates[0],
        positions=[dict(instrument='risk',quantity=1.)],initial_cash=200.,cash_rate_per_session=0.,
        series=dict(risk=series([100,100,80,70,90],'equity'),safe=series([100,100,110,120,130],'sector_index'),
                    future=series([100,100,80,70,90],'linear_hedge'),put=put),
        actions=[dict(base,id='noop',type='none',transaction_cost_bps=0.),
            dict(base,id='cash',type='reduce_to_cash',fraction=.5),
            dict(base,id='rotate',type='sector_rotation',instrument='safe',fraction=.5),
            dict(base,id='hedge',type='hedge_ratio',instrument='future',hedge_ratio=.5,margin_fraction=.2),
            dict(base,id='put',type='index_put',instrument='put',quantity=1.)])


def test_all_defensive_actions_account_for_costs_and_no_op():
    r=compare(defensive_request())
    assert all(a['status']=='available' for a in r['actions']),r
    a={v['id']:v for v in r['actions']}
    assert a['noop']['wealth']==r['baseline']['wealth']
    assert a['cash']['wealth'][1]==pytest.approx(300-.05)
    assert a['cash']['wealth'][3]==pytest.approx(285-.05)
    assert a['hedge']['wealth'][3]==pytest.approx(285-.05)
    assert a['rotate']['transaction_cost']==pytest.approx(.1)
    assert a['put']['wealth'][3]==pytest.approx(283-.002)
    assert r['evidence_modes']==['synthetic_test']


def test_defensive_refuses_missing_option_prices_and_keeps_negative_benefit():
    req=defensive_request()
    req['series']['put']['kind']='index'
    req['actions'][1]['transaction_cost_bps']=9000
    out=compare(req)
    by_id={v['id']:v for v in out['actions']}
    assert by_id['put']['status']=='unsupported'
    assert by_id['cash']['reduction_percentage_points']<0
    req['actions'][1]['execution_at']=req['decision_at']
    assert compare(req)['actions'][1]['status']=='unsupported'
    req['actions'][1]['execution_at']=req['valuation_times'][1]
    req['series']['risk']['prices'].pop()
    with pytest.raises(ValueError,match='misaligned'):
        compare(req)


def projection_fixture():
    y=np.array([[1.,2.,3.],[2.,3.,4.],[3.,4.,5.]])
    z=np.column_stack([np.ones(3),[-1,0,1]])
    model=MultivariateTVTPHamilton(y,exog_tvtp=z)
    params=model.start_params
    for j in range(3):
        params[model.parameters[j,'regime_transition']]=[1+j,-.4,.2*j,.8]
    engine=HamiltonEngine(['2020-01-01','2020-01-02','2020-01-03'],y,z)
    engine._order=(1,2,0)
    engine._res=SimpleNamespace(model=model,params=params,
        filtered_marginal_probabilities=np.array([[.2,.3,.1],[.3,.3,.7],[.5,.4,.2]]))
    value=artifact(engine,covariates=[dict(name='lagged_rv',unit='synthetic units',center=2.,scale=1.)],
                   input_manifest=dict(mode='synthetic_test'))
    return engine,value


def test_projection_round_trip_and_non_self_inverse_regime_order():
    engine,value=projection_fixture()
    rows=[dict(session='2020-01-06',lagged_rv=2.)]
    z=transform(value,rows)
    transition=engine._res.model.regime_transition_matrix(engine._res.params,exog_tvtp=np.asarray(z))[:,:,0]
    raw=np.empty(3);raw[list(engine._order)]=value['initial_xi']
    expected=(transition@raw)[list(engine._order)]
    np.testing.assert_allclose(project_xi(engine,z,xi0=value['initial_xi'])[0],expected)
    np.testing.assert_allclose(project(value,rows)[0],expected)
    broken=deepcopy(value);broken['params'][0]+=1
    with pytest.raises(ValueError,match='hash'):
        reconstruct(broken)
    with pytest.raises(ValueError,match='supported covariates'):
        project(value,[dict(session='2020-01-06',repo_rate=2.)])


def test_network_direction_and_zero_input_remain_distinct():
    from seraph.pillars.hawkes.network import fit_network
    spec=dict(design_ref='synthetic direction regression, fixed before generation',model_status='synthetic_test',
        decay=.2,dispersion=100.,l2=.01,minimum_bars=100,minimum_events=10,
        stationarity_bound=.95,seasonality='constant',session_reset=True,display_threshold=.08)
    rng=np.random.default_rng(40)
    counts=[];times=[]
    for day in range(40):
        previous=0.
        for slot in range(60):
            a=rng.poisson(.5);b=rng.poisson(.08+.65*previous)
            counts.append([a,b]);previous=a
            times.append((datetime.fromisoformat('2020-01-01T09:15:00+05:30')+
                          timedelta(days=day,minutes=slot*5)).isoformat())
    result=fit_network(counts,times,spec,node_ids=['source','target'],provenance={'mode':'synthetic_test'})
    assert result['status']=='fitted',result.get('diagnostics')
    assert result['matrix'][1][0]>result['matrix'][0][1]+.2
    assert result['diagnostics']['spectral_radius']<1
    assert any(e['source']=='source' and e['target']=='target' for e in result['edges'])
    absent=fit_network(np.empty((0,2)),[],spec,node_ids=['a','b'],provenance={'mode':'synthetic_test'})
    assert absent['status']=='insufficient_support' and absent['matrix'] is None


def test_cited_historical_tariff_uses_old_duty_inclusive_base():
    from seraph.news.historical_examples import run
    result=run(role='institutional',cost_base='1000000',pass_through=('0.4','0.8'))
    assert result['status']=='conditional_scenario'
    assert [float(v) for v in result['monetary_range']]==[80000,160000]
    assert 'OLD 25%' in result['inputs']['cost_basis']
    assert result['curation']['source'] in result['evidence']
