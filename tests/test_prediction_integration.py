# Prediction and early warning, integrated into the main application
"""SERAPH is a risk prediction and early-warning system, and its engine
reached the user only as backend code, a CLI experiment and a separate
read-only parquet viewer. `seraph.prediction` was unreachable from
`seraph/dashboard/` entirely.

These tests cover the integration and, more importantly, the four ways a
prediction surface can mislead:

1. showing a placeholder, a mock or a stale artifact as if it were the engine;
2. running the three claims together, so a model output reads as a
   measurement and a policy threshold reads as a validated alarm;
3. inventing uncertainty the model does not support;
4. presenting an unvalidated forecast as demonstrated foresight.

The engine's own arithmetic is tested in `test_prediction_*.py` and the
frozen experiment's protocol in `research_results/`; this file does not
duplicate either.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from seraph.dashboard.console_backend import WARNING_LEVELS, prediction_surface
from seraph.prediction import operational
from seraph.prediction.evaluation import AlertConfig

APP = Path(__file__).resolve().parents[1] / 'seraph/dashboard/prototype_app.py'
SNAPSHOT = Path('research_data/market_snapshot.parquet')
PANEL = 'PREDICTION & EARLY WARNING'

pytestmark = pytest.mark.skipif(
    not SNAPSHOT.exists(),
    reason=f'needs the real market snapshot at {SNAPSHOT}')


@pytest.fixture(scope='module')
def state():
    """The actual engine on the actual snapshot. About twenty seconds."""
    return operational.run(SNAPSHOT, series_tail=120)


@pytest.fixture
def console(tmp_path, monkeypatch, state):
    monkeypatch.setenv('SERAPH_WORKSPACE_DIR', str(tmp_path / 'runs'))
    monkeypatch.setenv('SERAPH_LIVE_STORE', str(tmp_path / 'live.sqlite'))
    monkeypatch.setenv('SERAPH_NEWS_STORE', str(tmp_path / 'news.sqlite'))
    monkeypatch.setenv('SERAPH_NEWS_WORKER', '0')
    monkeypatch.setenv('SERAPH_PROTOTYPE_STORE', str(tmp_path / 'archive.sqlite'))
    saved = tmp_path / 'prediction.json'
    operational.save(state, saved)
    monkeypatch.setenv('SERAPH_PREDICTION_STATE', str(saved))
    return saved


def render(role='regulator', timeout=180):
    app = AppTest.from_file(str(APP))
    app.session_state['console_role'] = role
    return app.run(timeout=timeout)


def _labels(app):
    return ' '.join(str(getattr(e, 'label', '')) for e in app.expander)


class TestTheEngineIsTheOneTheExperimentFroze:
    def test_the_feature_set_has_not_drifted(self):
        """Two declarations of one list -- the frozen experiment script is
        deliberately not edited, so this is the mechanical check that the
        operational path still runs the same model."""
        operational.assert_matches_experiment()

    def test_all_three_pillar_families_are_present(self):
        """Directive: integrate the three-pillar architecture, do not replace
        it. A 'combined' model missing a pillar would still run."""
        families = {operational.FEATURE_PILLAR[name]
                    for name in operational.OPERATIONAL_FEATURES}
        assert {'hawkes', 'rmt', 'hamilton'} <= families

    def test_the_protocol_is_the_frozen_one(self):
        assert operational.HORIZON == 15
        assert operational.LOSS_BARRIER == 0.10

    def test_it_calls_the_real_engine_not_a_copy(self):
        """No prediction arithmetic may be reimplemented here: the module
        must call pillars/models/evaluation rather than reproduce them."""
        import ast

        source = Path('seraph/prediction/operational.py').read_text(
            encoding='utf-8')
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.update(a.name for a in node.names)
        for required in ('build_pillar_features', 'walk_forward_predict',
                         'calibrate_alerts', 'future_loss_labels'):
            assert required in imported, f'{required} is not reused'


class TestTheStateIsRealAndPointInTime:
    def test_it_produces_a_forecast_for_the_latest_session(self, state):
        probability = state.predicted['probability']
        assert probability is not None
        assert 0.0 <= probability <= 1.0
        assert state.predicted['fit_status'] == 'fitted'

    def test_the_decision_date_is_the_snapshot_end(self, state):
        assert state.as_of == state.snapshot['last_session']

    def test_training_labels_are_purged_by_the_horizon(self, state):
        """The property that makes the series replayable rather than
        retrospective: no label whose horizon had not elapsed was readable at
        the fit."""
        train_end = state.predicted['train_end_date']
        fitted_at = state.predicted['fitted_at_date']
        assert train_end is not None and fitted_at is not None
        assert train_end < fitted_at <= state.as_of

    def test_it_records_the_snapshot_it_ran_on(self, state):
        assert len(state.snapshot['sha256']) == 64
        assert state.snapshot['rows'] > 1000

    def test_the_series_carries_gaps_rather_than_interpolating(self, state):
        """A session the engine declined to score is None, not a filled
        value: an unbroken line would imply coverage it does not have."""
        assert state.series
        assert all(set(row) == {'date', 'probability', 'threshold', 'alarm',
                                'label'} for row in state.series)


class TestTheThreeClaimsStayApart:
    """Measured, predicted and warning are three different claims. Running
    them together is how a research instrument starts sounding like an
    oracle."""

    def test_the_state_separates_them(self, state):
        assert set(state.measured) >= {'pillar_features', 'note'}
        assert 'probability' in state.predicted
        assert 'level' in state.warning
        assert 'probability' not in state.measured
        assert 'value' not in state.predicted

    def test_measured_values_are_features_not_probabilities(self, state):
        for name, item in state.measured['pillar_features'].items():
            assert item['pillar'] == operational.FEATURE_PILLAR[name]

    def test_the_warning_is_a_policy_with_a_declared_budget(self, state):
        budget = state.warning['budget']
        assert budget['false_episodes_per_year'] == 2.0
        assert budget['max_alarm_fraction'] == 0.10
        assert 'policy, not a' in state.warning['note']

    def test_the_level_is_one_the_console_can_draw(self, state):
        assert state.warning['level'] in WARNING_LEVELS

    def test_history_is_marked_retrospective(self, state):
        assert 'retrospective' in state.history['note']

    def test_the_panel_renders_all_three_headings(self, console):
        app = render()
        text = ' '.join(m.value for m in app.markdown)
        assert 'Measured' in text
        assert 'What is predicted' in text
        assert 'Warning policy' in text
        assert 'retrospective replay, not foresight' in text


class TestUncertaintyIsNotInvented:
    def test_reliability_is_computed_on_matured_labels_only(self, state):
        rows = state.history['reliability']
        assert rows
        counted = sum(row['count'] for row in rows)
        assert counted == state.history['metrics']['n']

    def test_every_populated_bin_reports_both_sides(self, state):
        for row in state.history['reliability']:
            if row['count']:
                assert row['mean_predicted'] is not None
                assert row['realised_rate'] is not None
                assert row['lower'] <= row['mean_predicted'] <= row['upper']

    def test_no_confidence_interval_is_claimed_for_the_probability(self, state):
        """The logistic challenger yields none, so inventing one would be
        worse than the reliability table that replaces it."""
        assert not any(k in state.predicted
                       for k in ('ci_lower', 'ci_upper', 'variance',
                                 'standard_error'))

    def test_the_bins_are_fixed_not_quantiles(self):
        """Quantile bins move with the forecast distribution and make a
        miscalibrated model look evenly spread."""
        assert operational.RELIABILITY_EDGES[0] == 0.0
        assert operational.RELIABILITY_EDGES[-1] == 1.0


class TestNothingUnvalidatedIsPresentedAsProven:
    def test_the_state_carries_the_validation_status(self, state):
        assert state.validation['status'] == 'unvalidated'
        assert 'AMENDMENT-03' in state.validation['note']

    def test_the_panel_shows_it_as_an_error_not_a_footnote(self, console):
        app = render()
        errors = ' '.join(e.value for e in app.error)
        assert 'UNVALIDATED' in errors

    def test_the_definition_is_stated_not_implied(self, state):
        definition = state.predicted['definition']
        assert '10%' in definition
        assert '15 sessions' in definition

    def test_it_is_never_called_a_crisis_forecast(self, state):
        """Checked on the fields that make the claim, not the whole blob.

        A scan of the serialised state matched "validated forecast" inside
        the disclaimer that forbids it -- "not grounds for treating its
        output as a validated forecast" -- so the first version of this test
        failed on the very sentence it exists to require.
        """
        claims = ' '.join([
            state.predicted['definition'], state.predicted['model'],
            state.warning['reason'], state.history['note'],
            state.measured['note'],
        ]).lower()
        for banned in ('crisis', 'crash', 'guarantee', 'accurate',
                       'validated forecast'):
            assert banned not in claims, f'{banned!r} in: {claims[:200]}'
        # The endpoint is a stated loss, not a named event.
        assert 'falls 10%' in state.predicted['definition']

    def test_the_disclaimer_itself_is_present_and_explicit(self, state):
        note = state.validation['note'].lower()
        assert 'no advance-warning skill' in note
        assert 'not grounds for treating its output as a validated forecast' \
            in note


class TestTheConsoleReadsAndDoesNotFit:
    def test_the_panel_is_first_and_open(self, console):
        app = render()
        assert PANEL in _labels(app)
        first = next(e for e in app.expander if getattr(e, 'label', ''))
        assert PANEL in str(first.label), (
            'prediction is the system\'s purpose; it should not be below '
            'news acquisition')

    def test_the_panel_fits_nothing(self):
        """A full replay refits seventy-three models. On page render that is
        a cliff, which is why the job computes and the panel reads."""
        import ast

        tree = ast.parse(APP.read_text(encoding='utf-8'))
        panel = next(n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef)
                     and n.name == 'prediction_panel')
        called = set()
        for node in ast.walk(panel):
            if isinstance(node, ast.Call):
                func = node.func
                parts = []
                while isinstance(func, ast.Attribute):
                    parts.append(func.attr)
                    func = func.value
                if isinstance(func, ast.Name):
                    parts.append(func.id)
                if parts:
                    called.add('.'.join(reversed(parts)))
        for forbidden in ('operational.run', 'walk_forward_predict',
                          'build_pillar_features', 'calibrate_alerts'):
            assert forbidden not in called, f'the panel computes: {forbidden}'
        assert 'prediction_surface' in called

    def test_the_dashboard_now_reaches_the_prediction_package(self):
        import ast

        source = Path('seraph/dashboard/console_backend.py').read_text(
            encoding='utf-8')
        text = source
        assert 'run_prediction' in text or 'seraph.prediction' in text, (
            'the console does not reach the prediction engine')

    def test_a_missing_state_says_so_rather_than_showing_zero(self, tmp_path,
                                                              monkeypatch):
        monkeypatch.setenv('SERAPH_PREDICTION_STATE',
                           str(tmp_path / 'absent.json'))
        surface = prediction_surface()
        assert surface['available'] is False
        assert 'run_prediction' in surface['command']

    def test_a_truncated_state_does_not_crash_the_console(self, tmp_path,
                                                          monkeypatch):
        broken = tmp_path / 'broken.json'
        broken.write_text('{"as_of":', encoding='utf-8')
        monkeypatch.setenv('SERAPH_PREDICTION_STATE', str(broken))
        surface = prediction_surface()
        assert surface['available'] is False
        assert surface['error']

    def test_a_state_missing_a_section_is_refused(self, tmp_path, monkeypatch,
                                                  state):
        partial = state.to_json()
        del partial['warning']
        path = tmp_path / 'partial.json'
        path.write_text(json.dumps(partial), encoding='utf-8')
        monkeypatch.setenv('SERAPH_PREDICTION_STATE', str(path))
        surface = prediction_surface()
        assert surface['available'] is False
        assert 'warning' in surface['note']


class TestTheRefreshScheduleIsWired:
    def test_the_daily_sequence_runs_the_prediction_job(self):
        """Directive: predictions update on the intended refresh schedule.
        Before this, the state only changed when someone ran it by hand."""
        source = Path('scripts/run_market_jobs.py').read_text(encoding='utf-8')
        assert 'scripts/run_prediction.py' in source
        assert 'prediction and early warning' in source

    def test_the_job_can_report_without_running(self):
        """The console must never trigger a twenty-second fit to draw."""
        import sys

        scripts = str(Path('scripts').resolve())
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import run_prediction

        assert callable(run_prediction.status)

    def test_saving_overwrites_because_a_warning_is_current_status(
            self, tmp_path, state):
        """The opposite of the experiment artefact, which refuses to
        overwrite because each run is evidence of its own."""
        path = tmp_path / 'state.json'
        operational.save(state, path)
        operational.save(state, path)
        assert json.loads(path.read_text(encoding='utf-8'))['as_of']


class TestTheWarningLevelsAreComplete:
    def test_every_level_the_engine_can_emit_is_drawable(self):
        """`unassessable`, `abstained`, `warning` and `no_warning` are the
        four `operational.run` can produce."""
        source = Path('seraph/prediction/operational.py').read_text(
            encoding='utf-8')
        for level in WARNING_LEVELS:
            assert f'"{level}"' in source or f"'{level}'" in source

    def test_only_no_warning_is_drawn_as_success(self):
        for level, (_, style) in WARNING_LEVELS.items():
            if level != 'no_warning':
                assert style != 'success', level

    def test_an_abstention_is_not_a_quiet_all_clear(self, state):
        """An infinite threshold means no finite one met the budget. Drawing
        that as green would report safety the calibration refused to claim."""
        assert WARNING_LEVELS['abstained'][1] == 'warning'
        assert 'threshold_is_abstention' in state.warning


class TestTheAlertConfigIsTheDeclaredOne:
    def test_the_defaults_match_the_research_protocol(self):
        config = AlertConfig(horizon=operational.HORIZON)
        assert config.false_episodes_per_year == 2.0
        assert config.max_alarm_fraction == 0.10
        assert config.lookback == 1260
        assert config.min_calibration == 252

    def test_the_realised_false_alarm_rate_is_reported(self, state):
        stats = state.history['alarm_stats']
        assert stats['false_episodes_per_year'] is not None
        assert stats['alarm_fraction'] is not None

    def test_the_budget_is_reported_beside_what_it_achieved(self, state):
        """A budget without the realised rate is a promise; together they are
        a measurement."""
        budget = state.warning['budget']['false_episodes_per_year']
        realised = state.history['alarm_stats']['false_episodes_per_year']
        assert budget is not None and realised is not None
        assert np.isfinite(realised)


class TestTheConsoleWorksInAnInstalledWheel:
    """The first version routed the console's read through
    `scripts/run_prediction.py`, inserting `scripts/` into `sys.path`. That
    works in a source checkout and fails in an installed distribution, which
    has no scripts directory -- and `verify_packaging.py` installs one and
    probes it. For the system's core feature that is not good enough.
    """

    def test_the_console_does_not_reach_into_scripts(self):
        """Asserted on the parsed function, not its text.

        The first version searched the source segment for "scripts" and
        matched the docstring, which correctly explains that
        `scripts/run_prediction.py` runs the engine. Documentation naming a
        script is not a dependency on one -- the fourth time in this session
        that a text search found the word it was trying to forbid.
        """
        import ast

        source = Path('seraph/dashboard/console_backend.py').read_text(
            encoding='utf-8')
        surface = next(n for n in ast.walk(ast.parse(source))
                       if isinstance(n, ast.FunctionDef)
                       and n.name == 'prediction_surface')

        imported = set()
        for node in ast.walk(surface):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or '')
                imported.update(a.name for a in node.names)
        assert 'run_prediction' not in imported, (
            'prediction_surface imports the job script, so it cannot read a '
            'forecast from an installed wheel, which has no scripts/')

        touched = {f'{n.value.id}.{n.attr}' for n in ast.walk(surface)
                   if isinstance(n, ast.Attribute)
                   and isinstance(n.value, ast.Name)}
        assert 'sys.path' not in touched
        assert '_sys.path' not in touched

    def test_it_imports_the_package_directly(self):
        import ast

        source = Path('seraph/dashboard/console_backend.py').read_text(
            encoding='utf-8')
        modules = {n.module for n in ast.walk(ast.parse(source))
                   if isinstance(n, ast.ImportFrom) and n.module}
        assert 'seraph.prediction' in modules

    def test_the_package_owns_the_state_path(self):
        assert callable(operational.state_path)
        assert callable(operational.load_state)

    def test_the_default_path_is_absolute_and_package_relative(self,
                                                               monkeypatch):
        """A relative default resolves against the caller's cwd, so the
        console and the job would disagree about where the state lives."""
        monkeypatch.delenv('SERAPH_PREDICTION_STATE', raising=False)
        assert operational.state_path().is_absolute()

    def test_the_environment_override_still_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv('SERAPH_PREDICTION_STATE', str(tmp_path / 's.json'))
        assert operational.state_path() == tmp_path / 's.json'

    def test_the_job_defers_to_the_package(self):
        """One definition of where the state lives, not two that can drift."""
        import sys

        scripts = str(Path('scripts').resolve())
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import run_prediction

        assert run_prediction.state_path() == operational.state_path()


class TestNoDashboardCodeImportsAJobScript:
    """The whole class of defect, caught in the fast suite.

    `verify_packaging.py` builds a wheel, installs it outside the checkout
    and renders the console there -- the only check that catches a
    `scripts/` import, and it takes minutes, so it is run rarely. It caught
    `No module named 'run_market_jobs'` only after C15 had shipped, which
    made the runbook's own packaging claim stale in the meantime.

    This asserts the rule directly: nothing under `seraph/` may import a
    module that lives in `scripts/`, because `seraph/` is what gets
    installed and `scripts/` is not.
    """

    @staticmethod
    def _script_module_names() -> set[str]:
        return {p.stem for p in Path('scripts').glob('*.py')
                if not p.stem.startswith('_')}

    def test_scripts_are_not_importable_from_the_package(self):
        import ast

        scripts = self._script_module_names()
        assert scripts, 'no scripts found; the guard would be vacuous'

        offenders = []
        for path in Path('seraph').rglob('*.py'):
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:                      # pragma: no cover
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split('.')[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split('.')[0]]
                for name in names:
                    if name in scripts:
                        offenders.append(f'{path}:{node.lineno} imports {name}')
        assert offenders == [], (
            'these would fail in an installed wheel, which has no scripts/: '
            + '; '.join(offenders))

    def test_the_two_state_readers_live_in_the_package(self):
        from seraph.operations.market_jobs_status import read_status, status_path
        from seraph.prediction.operational import load_state, state_path

        for fn in (read_status, status_path, load_state, state_path):
            assert fn.__module__.startswith('seraph.'), fn

    def test_both_paths_are_absolute(self, monkeypatch):
        from seraph.operations import market_jobs_status
        from seraph.prediction import operational

        monkeypatch.delenv('SERAPH_MARKET_JOBS_STATUS', raising=False)
        monkeypatch.delenv('SERAPH_PREDICTION_STATE', raising=False)
        assert market_jobs_status.status_path().is_absolute()
        assert operational.state_path().is_absolute()

    def test_a_missing_market_status_is_reported_not_raised(self, tmp_path,
                                                            monkeypatch):
        from seraph.operations.market_jobs_status import read_status

        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'absent.json'))
        assert read_status()['ran'] is False

    def test_a_damaged_market_status_is_reported_not_raised(self, tmp_path,
                                                            monkeypatch):
        from seraph.operations.market_jobs_status import read_status

        broken = tmp_path / 'broken.json'
        broken.write_text('{"ran":', encoding='utf-8')
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS', str(broken))
        result = read_status()
        assert result['ran'] is False
        assert 'unreadable' in result['note']
