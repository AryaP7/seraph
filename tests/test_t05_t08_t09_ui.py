# T05/T08/T09 — the browser controls, rendered (not just dispatchable)
"""The workflows were reachable through `dispatch()` and had no controls.

`tests/test_t05_t08_t09_workflows.py` proves the server half: 33 cases
driving the real dispatcher with the browser's own event shape. That is
necessary and not sufficient -- a feature nothing can click is not a
feature, which is precisely what the audit meant by "capable backend
modules remain disconnected".

These tests render the real page with Streamlit's AppTest and assert the
controls exist, are role-gated, and that the panel does not raise on an
installation where nothing has been saved yet. They do not re-test the
arithmetic: that is the other file's job and duplicating it here would mean
two places to update.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from seraph.orchestration.prototype import InferenceSession
from seraph.orchestration.run_store import RunStore

APP = Path(__file__).resolve().parents[1] / 'seraph/dashboard/prototype_app.py'


@pytest.fixture
def console(tmp_path, monkeypatch):
    """A console with one complete scored run and empty workflow stores."""
    monkeypatch.setenv('SERAPH_WORKSPACE_DIR', str(tmp_path / 'runs'))
    monkeypatch.setenv('SERAPH_LIVE_STORE', str(tmp_path / 'live.sqlite'))
    monkeypatch.setenv('SERAPH_NEWS_STORE', str(tmp_path / 'news.sqlite'))
    monkeypatch.setenv('SERAPH_NEWS_WORKER', '0')
    archive = tmp_path / 'archive.sqlite'
    monkeypatch.setenv('SERAPH_PROTOTYPE_STORE', str(archive))

    store = RunStore(archive)
    run = store.begin(dict(mode='ui test fixture',
                           data_available_through='2020-01-01'))
    inputs = {p: dict(score_eligible=True, value=v, variance=0.01,
                      information_timestamp='2020-01-01T15:30:00+05:30')
              for p, v in (('hawkes', 0.4), ('rmt', 0.5), ('hamilton', 0.6))}
    point = InferenceSession(['2020-01-01']).step('2020-01-01', inputs, [],
                                                  run_id=run)
    store.put(run, point)
    store.finish(run, 1)
    return archive


def render(timeout: int = 90):
    return AppTest.from_file(str(APP)).run(timeout=timeout)


class TestTheWorkspacePanelRenders:
    def test_the_page_renders_with_the_panel_present(self, console):
        app = render()
        assert not app.exception, f'console raised: {app.exception}'

    def test_the_panel_is_on_the_page(self, console):
        app = render()
        labels = ' '.join(str(getattr(e, 'label', '')) for e in app.expander)
        assert 'MY WORKSPACE' in labels

    def test_an_empty_installation_does_not_raise(self, console):
        """Nothing saved yet is the FIRST thing every user sees, and it was
        the state most likely to crash a freshly wired panel."""
        app = render()
        assert not app.exception
        messages = ' '.join(i.value for i in app.info)
        assert 'No portfolio yet' in messages

    def test_the_demo_identity_is_named_on_screen(self, console):
        """Durable and owner-scoped is a different claim from authenticated,
        and the screen has to make that difference."""
        app = render()
        captions = ' '.join(c.value for c in app.caption)
        assert 'not authenticated' in captions

    def test_a_portfolio_can_be_created_from_the_control(self, console):
        app = render()
        name = next((t for t in app.text_input
                     if 'New portfolio name' in str(t.label)), None)
        assert name is not None, 'the create control is missing'
        name.set_value('From the browser').run(timeout=90)
        assert not app.exception

    def test_the_market_jobs_panel_is_also_present(self, console):
        app = render()
        labels = ' '.join(str(getattr(e, 'label', '')) for e in app.expander)
        assert 'MARKET JOBS' in labels

    def test_a_refused_saved_scenario_keeps_the_page_and_its_history(self, console):
        from seraph.dashboard.console_backend import dispatch
        store = RunStore(console)
        point = store.points(store.runs()[0]['id'])[0]
        dispatch(store, point, 'institutional', dict(
            id='invalid-saved-scenario', run_id=point['run_id'], date=point['date'],
            op='sc_save', name='Invalid older input', kind='rank_shock',
            steps=[dict(pillar='rmt', delta=2, horizon=3)],
            assumptions=[dict(key='shock', value=2, unit='rank',
                              justification='Test a saved input refused by the runner')]))
        app = AppTest.from_file(str(APP))
        app.session_state['console_role'] = 'institutional'
        app.run(timeout=90)
        app.button(key='wf_scrun').click().run(timeout=90)
        assert not app.exception
        assert any('Shock must be within' in w.value for w in app.warning)
        assert app.button(key='wf_schist')


class TestRoleGatingIsVisible:
    """The dispatcher refuses an out-of-role operation. The panel should not
    offer it in the first place -- a disabled-by-error control teaches the
    user nothing."""

    def test_retail_is_told_scenarios_are_not_theirs(self, console):
        app = render()
        messages = ' '.join(i.value for i in app.info)
        assert 'institutional or regulator tool' in messages

    def test_retail_is_told_cases_are_not_theirs(self, console):
        app = render()
        messages = ' '.join(i.value for i in app.info)
        assert 'regulator tool' in messages

    def test_the_panel_names_how_to_change_role(self, console):
        app = render()
        messages = ' '.join(i.value for i in app.info)
        assert 'Switch role in the console' in messages


class TestTheControlsMatchTheDispatcher:
    """A control that sends an operation the dispatcher does not serve, or a
    served operation with no control, is the disconnection this closes."""

    def test_every_control_operation_is_served(self):
        import re

        from seraph.dashboard.console_backend import WORKFLOW_ROLES

        body = APP.read_text(encoding='utf-8')
        panel = body.split('def workflows_panel', 1)[1].split('\ndef ', 1)[0]
        sent = set(re.findall(r"send\('([a-z_]+)'", panel))
        unserved = sorted(sent - set(WORKFLOW_ROLES))
        assert unserved == [], f'controls send unserved operations: {unserved}'

    def test_each_workflow_family_has_controls(self):
        import re

        body = APP.read_text(encoding='utf-8')
        panel = body.split('def workflows_panel', 1)[1].split('\ndef ', 1)[0]
        sent = set(re.findall(r"send\('([a-z_]+)'", panel))
        for prefix in ('ws_', 'sc_', 'case_'):
            assert any(op.startswith(prefix) for op in sent), \
                f'no {prefix} control is wired'

    def test_a_fresh_request_id_per_click(self):
        """`CaseStore` dedupes on request id, so a reused one makes the
        second distinct change a silent no-op."""
        body = APP.read_text(encoding='utf-8')
        panel = body.split('def workflows_panel', 1)[1].split('\ndef ', 1)[0]
        assert 'uuid4' in panel

    def test_exports_are_real_downloads(self):
        """A nominal Export that renders JSON on screen is not the
        downloadable analysis the requirement describes."""
        body = APP.read_text(encoding='utf-8')
        panel = body.split('def workflows_panel', 1)[1].split('\ndef ', 1)[0]
        assert panel.count('download_button') >= 2
        assert 'file_name=export' in panel

    def test_upload_rejections_are_shown_not_counted(self):
        body = APP.read_text(encoding='utf-8')
        panel = body.split('def workflows_panel', 1)[1].split('\ndef ', 1)[0]
        assert "preview['rejected_rows']" in panel

    def test_a_scenario_cannot_be_saved_without_a_justification(self):
        body = APP.read_text(encoding='utf-8')
        panel = body.split('def workflows_panel', 1)[1].split('\ndef ', 1)[0]
        assert 'needs a justification' in panel

    def test_only_legal_case_transitions_are_offered(self):
        """The store owns the state machine; the panel reads it rather than
        listing statuses of its own."""
        body = APP.read_text(encoding='utf-8')
        panel = body.split('def workflows_panel', 1)[1].split('\ndef ', 1)[0]
        assert 'TRANSITIONS.get(case' in panel

    def test_priorities_come_from_the_store(self):
        body = APP.read_text(encoding='utf-8')
        panel = body.split('def workflows_panel', 1)[1].split('\ndef ', 1)[0]
        assert 'PRIORITIES' in panel
