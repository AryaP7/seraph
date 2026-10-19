import json
import re
import pytest
from seraph.dashboard.connected_frontend import build_frontend


def point(day='2020-01-01', run='run-a'):
    return dict(run_id=run,date=day,composite=None,original_pillars={},astra_predictions=[])


def payload(html):
    return json.loads(re.search(r'<script id="seraph-run" type="application/json">(.*?)</script>',html,re.S).group(1))


def test_frontend_only_sends_selected_run_history_and_preserves_missingness():
    p=point()
    html=build_frontend(p,{},[p,point('2020-01-02')])
    data=payload(html)
    assert data['point']==p
    assert data['history']==[dict(date=p['date'],composite=None)]
    assert '29% AMBER' not in html
    assert '1,019 desks' not in html
    assert '<script src=' not in html
    with pytest.raises(ValueError,match='mix runs'):
        build_frontend(p,{},[point(run='run-b')])


def test_frontend_payload_cannot_escape_script():
    p=point(); p['note']='</script><img src=x onerror=alert(1)>'
    html=build_frontend(p,{},[p])
    assert p['note'] not in html
    assert payload(html)['point']==p
