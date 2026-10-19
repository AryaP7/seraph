from pathlib import Path
from streamlit.testing.v1 import AppTest
from seraph.orchestration.run_store import RunStore
from seraph.orchestration.prototype import InferenceSession

APP=Path(__file__).resolve().parents[1]/'seraph/dashboard/prototype_app.py'


def test_viewer_missing_store_is_explicit(tmp_path,monkeypatch):
    monkeypatch.setenv('SERAPH_PROTOTYPE_STORE',str(tmp_path/'missing.sqlite'))
    app=AppTest.from_file(str(APP)).run(timeout=30)
    assert not app.exception and 'No persisted run' in app.info[0].value
    assert not (tmp_path/'missing.sqlite').exists()


def test_viewer_selects_one_run_and_preserves_unavailability(tmp_path,monkeypatch):
    store=RunStore(tmp_path/'test.sqlite')
    run=store.begin(dict(mode='synthetic test fixture',data_available_through='2020-01-01'))
    originals={p:dict(score_eligible=False,reason='synthetic unavailable test',
        absence='structural',absence_reason='no_data_coverage') for p in ('hawkes','rmt','hamilton')}
    point=InferenceSession(['2020-01-01']).step('2020-01-01',originals,[],run_id=run)
    store.put(run,point);store.finish(run,1)
    monkeypatch.setenv('SERAPH_PROTOTYPE_STORE',str(store.path))
    app=AppTest.from_file(str(APP)).run(timeout=30)
    assert not app.exception
    assert app.selectbox[0].value==run
    assert any('No composite' in w.value for w in app.warning)
    assert any('No user holdings' in w.value for w in app.info)
