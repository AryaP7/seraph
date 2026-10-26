"""F06/F10 — data provenance, institution totals, cutoff selection and access."""
from copy import deepcopy

import pytest

from seraph.dashboard import workspace_service as svc
from seraph.decision_support.institutions import InstitutionStore
from seraph.identity import AuthorizationError


def test_institution_revisions_totals_and_role_denial(tmp_path, monkeypatch):
    monkeypatch.setenv('SERAPH_WORKSPACE_DIR', str(tmp_path))
    registry = svc.registry()
    principal = svc.demo_principal('regulator', reg=registry)
    store = InstitutionStore(tmp_path/'institutions.sqlite', registry)
    args = dict(source='demo', source_name='a.csv',
                effective_at='2026-10-01T00:00:00+05:30',
                received_at='2026-10-02T00:00:00+05:30')
    store.submit(principal, institution_id='demo-a', name='Demo A',
                 body='symbol,value,sector\nX,100,banking\n', **args)
    store.submit(principal, institution_id='demo-b', name='Demo B',
                 body='symbol,value,sector\nY,300,energy\n', **args)
    old = store.decomposition(principal, cutoff='2026-10-02T12:00:00+05:30',
                              flags={'banking': 'amber'})
    assert old['total_known_value'] == 400
    assert sum(r['share_pct'] for r in old['sectors']) == 100
    assert old['covered_value'] == 100
    store.submit(principal, institution_id='demo-a', name='Demo A',
                 body='symbol,value,sector\nX,200,banking\n',
                 **dict(args, received_at='2026-10-03T00:00:00+05:30'))
    reopened = InstitutionStore(store.path, registry)
    assert reopened.decomposition(principal, cutoff='2026-10-02T12:00:00+05:30')['total_known_value'] == 400
    assert reopened.decomposition(principal, cutoff='2026-10-04T12:00:00+05:30')['total_known_value'] == 500
    for role in ('retail', 'institutional'):
        with pytest.raises(AuthorizationError):
            reopened.decomposition(svc.demo_principal(role, reg=registry),
                                   cutoff='2026-10-04T12:00:00+05:30')
    with pytest.raises(ValueError, match='rejected/duplicate'):
        store.submit(principal, institution_id='bad', name='bad',
            body='symbol,value,currency\nX,100,USD\n', **args)
    assert len(reopened.decomposition(principal, cutoff='2026-10-04T12:00:00+05:30')['institutions']) == 2


def test_stored_adapter_keeps_missing_modes_and_rejects_future_state():
    from seraph.orchestration.prototype import InferenceSession
    from seraph.validation.datasets import from_run_store
    absent = {p: dict(score_eligible=False, absence='structural',
                     absence_reason='no_data_coverage', reason='test')
              for p in ('hawkes', 'rmt', 'hamilton')}
    point = InferenceSession(['2020-02-20']).step('2020-02-20', absent, [], run_id='r')
    point['original_pillars']['hamilton']['detail'] = {'xi': [1., 0., 0.]}

    class Store:
        def runs(self):
            return [dict(id='r', status='complete', manifest={'mode': 'historical observation'})]
        def points(self, _):
            return [point]

    definitions = {'covid_2020': dict(start='2020-02-20', end='2020-02-20',
                                    break_date='2020-02-20', sessions=['2020-02-20'])}
    result = from_run_store(Store(), ['r'], definitions, cutoff='2020-02-20T16:00:00+05:30')
    assert 'forward_fill' not in result['dataset']['covid_2020'].observations
    assert result['dataset']['covid_2020'].observations['kalman'][0].label == 1
    assert result['dataset']['covid_2020'].pillar_coverage == frozenset()
    point['reconciled']['ts'] = '2026-10-20T15:30:00+05:30'
    with pytest.raises(ValueError, match='future'):
        from_run_store(Store(), ['r'], definitions, cutoff='2020-02-20T16:00:00+05:30')


def test_sector_archive_never_becomes_historical_knowledge(tmp_path, monkeypatch):
    from seraph.pillars.hawkes.sectors import digest, save
    from seraph.dashboard.console_backend import sector_analysis, dispatch
    from seraph.dashboard.news_view import sector_panel
    monkeypatch.setenv('SERAPH_SECTOR_ARTIFACTS', str(tmp_path))
    body = dict(input_end='2020-04-30', available=True, flags={'steel':'amber'},
                sectors=[], mapping_basis='synthetic coverage regression')
    body['artifact_id']=digest(body)
    artifact=save(body, directory=tmp_path)
    newer = dict(body, input_end='2026-10-19', available=False, flags={})
    newer.pop('artifact_id')
    newer['artifact_id'] = digest(newer)
    latest = save(newer, directory=tmp_path)
    decision='2020-04-30T15:30:00+05:30'
    assert sector_analysis(decision)['flags']=={}
    archive=sector_analysis(decision, latest['available_at'])
    assert archive['flags']=={'steel':'amber'}
    assert archive['analysis_mode']=='retrospective_archive'
    point=dict(run_id='r',date='2020-04-30',evaluation_timestamp=decision)
    event=dict(op='portfolio',run_id='r',date=point['date'],id='request',
               holdings=[dict(symbol='TEST',value=100,sector='steel')])
    historical=dispatch(None,point,'retail',event)
    retrospective=dispatch(None,point,'retail',event,sector_archive_as_of=latest['available_at'])
    assert historical['value']['coveredPct']==0
    assert retrospective['value']['coveredPct']==100
    assert retrospective['value']['exposedPct']==100
    assert retrospective['sector_flags']['market_decision']==decision
    panel=sector_panel({'estimates':[]},hawkes_sector_flags=archive['flags'])
    assert 'intensity' in panel['hawkes']['rows'][0]['unit']
