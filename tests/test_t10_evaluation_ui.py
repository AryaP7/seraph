# T10 — the FR35 evaluation surface, rendered (closes C12)
"""T10 was built as a library and a CLI and left out of the console.

That is the defect the audit named in as many words -- "capable backend
modules remain disconnected" -- and the feature checklist files this item
under **C12**, asking for an "execution/report journey". A text renderer
behind a script is not a journey, so `seraph.validation` being imported
nowhere in `seraph/dashboard/` was the gap, not a style preference.

These tests render the real page with Streamlit's AppTest and assert the
panel exists, is role-gated, states its refusal when no design is committed,
and does not offer the two controls it must never offer. They do not re-test
the ablation arithmetic: `test_t10_experiment_runner.py` owns that, and
duplicating it here would mean two places to update.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fixtures import experiment_dataset
from seraph.dashboard.console_backend import experiment_surface
from seraph.orchestration.prototype import InferenceSession
from seraph.orchestration.run_store import RunStore
from seraph.validation import experiment, experiment_store
from seraph.validation.preregistration import build, commit

APP = Path(__file__).resolve().parents[1] / 'seraph/dashboard/prototype_app.py'
PANEL = 'EVALUATION'
BUDGET = 40


def _console(tmp_path, monkeypatch):
    """A console with one complete scored run, as the other UI tests build."""
    monkeypatch.setenv('SERAPH_WORKSPACE_DIR', str(tmp_path / 'runs'))
    monkeypatch.setenv('SERAPH_LIVE_STORE', str(tmp_path / 'live.sqlite'))
    monkeypatch.setenv('SERAPH_NEWS_STORE', str(tmp_path / 'news.sqlite'))
    monkeypatch.setenv('SERAPH_NEWS_WORKER', '0')
    archive = tmp_path / 'archive.sqlite'
    monkeypatch.setenv('SERAPH_PROTOTYPE_STORE', str(archive))

    store = RunStore(archive)
    run = store.begin(dict(mode='evaluation ui fixture',
                           data_available_through='2020-01-01'))
    inputs = {p: dict(score_eligible=True, value=v, variance=0.01,
                      information_timestamp='2020-01-01T15:30:00+05:30')
              for p, v in (('hawkes', 0.4), ('rmt', 0.5), ('hamilton', 0.6))}
    point = InferenceSession(['2020-01-01']).step('2020-01-01', inputs, [],
                                                  run_id=run)
    store.put(run, point)
    store.finish(run, 1)
    return archive


@pytest.fixture
def bare(tmp_path, monkeypatch):
    """A console whose pre-registration has never been committed."""
    _console(tmp_path, monkeypatch)
    monkeypatch.setenv('SERAPH_PREREGISTRATION',
                       str(tmp_path / 'absent-preregistration.json'))
    monkeypatch.setenv('SERAPH_EXPERIMENT_REPORTS',
                       str(tmp_path / 'experiments'))
    return tmp_path


@pytest.fixture(scope="module")
def saved_run(tmp_path_factory):
    """One committed design and one saved report, built once."""
    root = tmp_path_factory.mktemp('evaluation')
    design = root / 'preregistration.json'
    commit(build(calibration_max_iter=BUDGET), design)
    reports = root / 'experiments'
    result = experiment.run(
        dataset=experiment_dataset.build(per_epoch=16),
        preregistration=design, tables=('B',))
    assert result.status == 'ok'
    experiment_store.save(result.value, reports / 'exp-01.json')
    return dict(root=root, design=design, reports=reports,
                report=result.value)


@pytest.fixture
def complete(tmp_path, monkeypatch, saved_run):
    _console(tmp_path, monkeypatch)
    monkeypatch.setenv('SERAPH_PREREGISTRATION', str(saved_run['design']))
    monkeypatch.setenv('SERAPH_EXPERIMENT_REPORTS', str(saved_run['reports']))
    return saved_run


def render(role: str | None = None, timeout: int = 120):
    """Render the console, optionally as a role other than the default.

    The console reads `st.session_state['console_role']`, defaulting to
    retail. The panel's role gate returns before the design checks, so the
    refusal assertions below have to arrive as a role that may see the
    surface at all -- the first version of these tests rendered as retail and
    asserted the design warning, which the page never reaches.
    """
    app = AppTest.from_file(str(APP))
    if role is not None:
        app.session_state['console_role'] = role
    return app.run(timeout=timeout)


def _labels(app):
    return ' '.join(str(getattr(e, 'label', '')) for e in app.expander)


def _panel_source() -> str:
    body = Path('seraph/dashboard/prototype_app.py').read_text(encoding='utf-8')
    return body.split('def experiment_panel', 1)[1].split('\ndef ', 1)[0]


class TestThePanelIsOnThePage:
    def test_the_page_still_renders(self, bare):
        app = render()
        assert not app.exception, f'console raised: {app.exception}'

    def test_the_evaluation_panel_exists(self, bare):
        """The whole point: before this, `seraph.validation` was imported
        nowhere under seraph/dashboard/."""
        assert PANEL in _labels(render())

    def test_the_dashboard_now_reaches_the_validation_package(self):
        import ast

        source = Path('seraph/dashboard/console_backend.py').read_text(
            encoding='utf-8')
        modules = {
            node.module for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert any(m.startswith('seraph.validation') for m in modules), (
            'the console does not import the validation package, so the '
            'evaluation surface is not actually wired')


class TestItRefusesBeforeTheDesignIsCommitted:
    def test_it_says_no_auc_can_be_computed(self, bare):
        app = render('regulator')
        warnings = ' '.join(w.value for w in app.warning)
        assert 'no pre-registered design' in warnings.lower()
        assert 'no AUC can be computed' in warnings

    def test_it_prints_the_command_instead_of_offering_a_button(self, bare):
        """D5(d) and DR-05 step 5: the design is committed by a person, once.
        A control here would make it a side effect of opening a page."""
        app = render('regulator')
        code = ' '.join(c.value for c in app.code)
        assert 'preregistration import commit' in code

    def test_it_names_where_the_design_is_expected(self, bare):
        app = render('regulator')
        captions = ' '.join(c.value for c in app.caption)
        assert 'SERAPH_PREREGISTRATION' in captions

    def test_retail_is_gated_before_the_design_is_even_consulted(self, bare):
        """Order matters: a retail reader is told whose tool this is, not
        shown a pre-registration diagnostic they cannot act on."""
        app = render('retail')
        messages = ' '.join(i.value for i in app.info)
        assert 'institutional or regulator tool' in messages
        assert 'no AUC can be computed' not in ' '.join(
            w.value for w in app.warning)


def _panel_calls() -> set[str]:
    """Every function the panel actually CALLS, by dotted name.

    Parsed, not grepped. The first version of these two tests matched the
    substrings "button" and "run_experiment" in the panel's own docstring and
    help text -- it prints the `scripts/run_experiment.py` command and
    explains why a button would be wrong, so a text search finds exactly the
    words it is trying to forbid. The same trap as matching "calibrate"
    inside "calibrated_on_epochs".
    """
    import ast

    tree = ast.parse(Path('seraph/dashboard/prototype_app.py').read_text(
        encoding='utf-8'))
    panel = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)
                 and n.name == 'experiment_panel')
    names = set()
    for node in ast.walk(panel):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        parts = []
        while isinstance(func, ast.Attribute):
            parts.append(func.attr)
            func = func.value
        if isinstance(func, ast.Name):
            parts.append(func.id)
        if parts:
            names.add('.'.join(reversed(parts)))
    return names


class TestTheTwoControlsItMustNotOffer:
    """Asserted on the calls the panel makes, because the claim is about what
    the page CANNOT do and a rendered page only shows what it does."""

    def test_there_is_no_commit_control(self):
        """D5(d) and DR-05 step 5: the design is committed by a person, once.
        A control here would make it a side effect of opening a page."""
        calls = _panel_calls()
        assert not [c for c in calls if c.endswith('button')], (
            f"the panel renders a control: {sorted(calls)}")
        assert 'commit' not in calls

    def test_there_is_no_run_control(self):
        """A full ablation calibrates once per fold. Starting one on page
        render would make every refresh a cliff -- the same reason MARKET
        JOBS reads a status file rather than estimating."""
        calls = _panel_calls()
        forbidden = {'experiment.run', 'run', 'run_experiment', 'calibrate',
                     'sweep', 'transfer', 'score_subset'}
        assert not (calls & forbidden), f"the panel computes: {calls & forbidden}"

    def test_it_reads_through_the_backend(self):
        """Not straight off the filesystem: the panel asks console_backend,
        which is where the role gate and the artefact verification live."""
        assert 'experiment_surface' in _panel_calls()

    def test_the_panel_explains_both_refusals(self):
        source = _panel_source()
        assert 'side effect' in source
        assert 'cliff' in source


class TestRoleGating:
    """FR42: an ablation table reports what the instrument can and cannot do,
    which is the institutional and regulatory question, not the retail
    traffic-light one."""

    def test_retail_is_told_it_is_not_their_tool(self, complete):
        app = render()
        messages = ' '.join(i.value for i in app.info)
        assert 'institutional or regulator tool' in messages

    def test_retail_is_told_how_to_change_role(self, complete):
        app = render()
        messages = ' '.join(i.value for i in app.info)
        assert 'Switch role' in messages

    def test_the_backend_permits_only_the_two_roles(self, complete):
        assert experiment_surface(role='retail')['permitted'] is False
        for role in ('institutional', 'regulator'):
            assert experiment_surface(role=role)['permitted'] is True


class TestWhatAReaderIsShown:
    """Asserted through the backend the panel renders from, so the data the
    page receives is checked without driving a role switch through the UI."""

    def test_the_saved_run_is_found_and_verified(self, complete):
        surface = experiment_surface(role='regulator')
        assert [r['name'] for r in surface['reports']] == ['exp-01.json']
        assert surface['reports'][0]['intact'] is True

    def test_measured_and_declared_folds_are_both_carried(self, complete):
        """A mean without its fold count hides a configuration that measured
        fewer folds than it declared."""
        rows = experiment_surface(role='regulator')['reports'][0][
            'configurations']
        assert rows
        for row in rows:
            assert 'measured_folds' in row and 'declared_folds' in row

    def test_the_comparability_warning_travels_with_the_rows(self, complete):
        surface = experiment_surface(role='regulator')
        assert 'ranking' in surface['reports'][0]['comparability'].lower()

    def test_the_absence_census_is_present_even_when_empty(self, complete):
        assert 'absences' in experiment_surface(
            role='regulator')['reports'][0]

    def test_the_unpublishable_count_is_carried(self, complete):
        assert 'unpublishable' in experiment_surface(
            role='regulator')['reports'][0]

    def test_the_design_fingerprint_is_shown(self, complete):
        design = experiment_surface(role='regulator')['design']
        assert design['committed'] and design['intact']
        assert design['configurations'] == 26
        assert design['table_b_scope'] == 'two_epoch'


class TestItRefusesTamperedEvidence:
    def test_an_edited_design_is_reported_as_not_intact(self, tmp_path,
                                                        monkeypatch):
        _console(tmp_path, monkeypatch)
        design = tmp_path / 'preregistration.json'
        commit(build(calibration_max_iter=BUDGET), design)
        blob = json.loads(design.read_text(encoding='utf-8'))
        blob['design']['kappaMiss'] = 999.0
        design.write_text(json.dumps(blob), encoding='utf-8')
        monkeypatch.setenv('SERAPH_PREREGISTRATION', str(design))
        monkeypatch.setenv('SERAPH_EXPERIMENT_REPORTS',
                           str(tmp_path / 'experiments'))

        assert experiment_surface(role='regulator')['design']['intact'] is False
        app = render('regulator')
        assert not app.exception
        errors = ' '.join(e.value for e in app.error)
        assert 'no longer matches its own recorded hash' in errors

    def test_an_edited_artefact_is_reported_as_not_intact(self, tmp_path,
                                                          monkeypatch,
                                                          saved_run):
        _console(tmp_path, monkeypatch)
        reports = tmp_path / 'experiments'
        reports.mkdir()
        target = reports / 'edited.json'
        blob = json.loads(
            (saved_run['reports'] / 'exp-01.json').read_text(encoding='utf-8'))
        blob['report']['rows'][0]['auc'] = 0.99
        target.write_text(json.dumps(blob), encoding='utf-8')
        monkeypatch.setenv('SERAPH_PREREGISTRATION', str(saved_run['design']))
        monkeypatch.setenv('SERAPH_EXPERIMENT_REPORTS', str(reports))

        surface = experiment_surface(role='regulator')
        assert surface['reports'][0]['intact'] is False

    def test_an_unreadable_artefact_does_not_crash_the_panel(self, tmp_path,
                                                             monkeypatch,
                                                             saved_run):
        """A console that raises on one bad file takes every other surface
        down with it."""
        _console(tmp_path, monkeypatch)
        reports = tmp_path / 'experiments'
        reports.mkdir()
        (reports / 'truncated.json').write_text('{"artefactId":',
                                                encoding='utf-8')
        monkeypatch.setenv('SERAPH_PREREGISTRATION', str(saved_run['design']))
        monkeypatch.setenv('SERAPH_EXPERIMENT_REPORTS', str(reports))

        surface = experiment_surface(role='regulator')
        assert surface['reports'][0]['readable'] is False
        app = render('regulator')
        assert not app.exception


class TestTheHealthSurfaceIsWired:
    """OPS01's reader said "an empty dashboard with a green banner is the
    specific failure this prevents", and then nothing in the dashboard read
    it. `seraph.operations` was unreachable from `seraph/dashboard/`."""

    def test_the_health_panel_is_on_the_page(self, bare):
        assert 'HEALTH' in _labels(render('regulator'))

    def test_the_console_reaches_the_operations_package(self):
        import ast

        source = Path('seraph/dashboard/console_backend.py').read_text(
            encoding='utf-8')
        modules = {
            node.module for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert any(m.startswith('seraph.operations') for m in modules)

    def test_silence_is_never_reported_as_health(self, tmp_path, monkeypatch):
        """The module's first rule, preserved through the UI: a store that
        does not exist is `never_*`, not `ok`."""
        from seraph.dashboard.console_backend import health_surface

        monkeypatch.setenv('SERAPH_NEWS_STORE', str(tmp_path / 'absent.sqlite'))
        monkeypatch.setenv('SERAPH_JOB_STORE', str(tmp_path / 'absent-jobs.sqlite'))
        surface = health_surface()
        assert surface['status'] != 'ok'
        assert surface['problems'], 'two missing stores produced no problem'
        assert any('never' in p for p in surface['problems'])

    def test_no_health_level_maps_to_success_except_ok(self):
        """A green badge for `never_run` would undo the module's rule in the
        one place a reader looks."""
        from seraph.dashboard import prototype_app

        for level, (_, style) in prototype_app._HEALTH_STYLE.items():
            if level != 'ok':
                assert style in ('warning', 'error'), level

    def test_job_names_come_from_the_ledger_not_a_guess(self):
        """The first version hard-coded `news_poll` while the ledger records
        `news.poll`, so it reported never_run for a job with hundreds of
        runs -- the mirror of the false green banner."""
        source = Path('seraph/dashboard/console_backend.py').read_text(
            encoding='utf-8')
        body = source.split('def health_surface', 1)[1]
        assert 'store.runs(None' in body
        assert 'DEFAULT_JOB_BUDGET' in body

    def test_the_market_jobs_are_not_expected_in_the_ledger(self):
        """They write a status file the MARKET JOBS panel reads. Listing them
        here would report never_run for work that has run."""
        from seraph.dashboard.console_backend import JOB_BUDGET_MINUTES

        assert 'daily_vintages' not in JOB_BUDGET_MINUTES
        assert 'prospective_forecast' not in JOB_BUDGET_MINUTES

    def test_the_panel_computes_nothing(self):
        source = Path('seraph/dashboard/prototype_app.py').read_text(
            encoding='utf-8')
        body = source.split('def health_panel', 1)[1].split('\ndef ', 1)[0]
        for forbidden in ('acquire(', 'JobStore(', 'poll(', 'run('):
            assert forbidden not in body, forbidden
