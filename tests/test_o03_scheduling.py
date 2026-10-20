# O03 — the daily schedule for the market/prediction/warning pipeline
"""`AGENTS.md` §2 chose cron and idempotent scripts, and then no schedule was
ever written: the pipeline ran when somebody launched the console, so the
prediction panel was current only on days the application happened to be
opened.

These tests cover the schedule's decisions and the two defects that building
it exposed. They do not re-test the pipeline steps themselves, which
`test_c15_unified_launch.py` and `test_prediction_integration.py` own.

The defects are the interesting part, and both were pre-existing:

* **R10's lease fencing could not acquire a lease on any existing ledger.**
  `generation` was added to `job_locks` under `CREATE TABLE IF NOT EXISTS`,
  which does nothing to a table that already exists. Every R10 test used a
  fresh `tmp_path`, so none of them saw it; the first scheduled run died on
  `table job_locks has 5 columns but 6 values were supplied`.
* **A completely successful pipeline exited 1 on a print.** `relative_to`
  raises for a path outside the tree, which is exactly the shape of failure
  that makes a scheduled run look broken when the work landed.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest

from seraph.operations import schedule
from seraph.operations.jobs import JobStore
from seraph.shared_types import IST

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_market_jobs  # noqa: E402


class TestTheTradingDayGate:
    """Weekday-plus-registry, reusing `MarketClock`. No holiday table is
    invented, because inventing one would be fabricating exchange data."""

    def test_a_weekend_is_refused(self):
        assert schedule.should_run('2026-10-24')['run'] is False   # Saturday
        assert schedule.should_run('2026-10-25')['run'] is False   # Sunday

    def test_a_weekday_runs(self):
        assert schedule.should_run('2026-10-20')['run'] is True
        assert schedule.should_run('2026-10-26')['run'] is True

    def test_a_skip_is_not_a_failure(self):
        decision = schedule.should_run('2026-10-24')
        assert 'skipped' in decision['reason']
        assert 'failure' in decision['reason']

    def test_an_unregistered_holiday_is_resolved_by_the_corpus(self):
        """The honest consequence of having no holiday calendar, stated in
        the reason a reader sees rather than left implicit."""
        reason = schedule.should_run('2026-10-20')['reason']
        assert 'holiday' in reason
        assert 'unchanged data rather than a failure' in reason

    def test_the_trigger_covers_only_weekdays(self):
        argv = schedule.register_command(python='py', script='s')
        assert 'MON,TUE,WED,THU,FRI' in argv
        assert '/sc' in argv and 'weekly' in argv


class TestExecutionAndFreshnessAreTwoFacts:
    """A successful job execution and successful acquisition of fresh data
    are different claims. Conflating them is how a green dashboard sits on
    top of a corpus that stopped updating."""

    def test_new_data_is_fresh(self):
        result = schedule.freshness(previous_session='2026-08-20',
                                    current_session='2026-08-21',
                                    expected='2026-08-21')
        assert result['acquired'] == 'fresh'
        assert result['currency'] == 'current'

    def test_no_new_data_is_unchanged_not_failed(self):
        result = schedule.freshness(previous_session='2026-08-21',
                                    current_session='2026-08-21',
                                    expected='2026-08-21')
        assert result['acquired'] == 'unchanged'
        assert result['currency'] == 'current'
        assert 'holiday' in result['detail']

    def test_a_shrinking_corpus_is_called_data_loss(self):
        result = schedule.freshness(previous_session='2026-08-21',
                                    current_session='2026-08-18',
                                    expected='2026-08-21')
        assert result['acquired'] == 'regressed'
        assert 'data loss' in result['detail']

    def test_a_short_gap_may_be_a_holiday(self):
        result = schedule.freshness(previous_session='2026-08-20',
                                    current_session='2026-08-21',
                                    expected='2026-08-24')
        assert result['currency'] == 'behind'
        assert result['sessions_behind'] == 3
        assert 'unregistered holiday also looks like' in result['detail']

    def test_a_wide_gap_does_not_blame_a_holiday(self):
        """Sixty days is the extent of the loaded corpus. Saying "holiday"
        there sends a reader looking for an exchange notice instead of at
        the loader."""
        result = schedule.freshness(previous_session='2026-08-21',
                                    current_session='2026-08-21',
                                    expected='2026-10-20')
        assert 'holiday also looks like' not in result['detail']
        assert 'extent of the loaded corpus' in result['detail']
        assert 'ingestion run' in result['detail']

    def test_an_unreadable_corpus_answers_neither_question(self):
        result = schedule.freshness(previous_session='2026-08-21',
                                    current_session=None)
        assert result['acquired'] == 'unknown'
        assert result['currency'] == 'unknown'

    def test_the_report_carries_both(self, tmp_path, monkeypatch):
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'status.json'))
        run_market_jobs._write(dict(
            generated='x', ok=True, execution_ok=True, session='2026-08-21',
            data=dict(acquired='unchanged', currency='behind')))
        from seraph.operations.market_jobs_status import read_status

        saved = read_status()
        assert saved['execution_ok'] is True
        assert saved['data']['acquired'] == 'unchanged'


class TestASkipDoesNotEraseTheLastRealRun:
    """The first version wrote a fresh report with `session: None`, which
    blanked the console every weekend and made the next weekday compare its
    corpus against nothing -- so a Monday with no new data reported
    `first_run` instead of `unchanged`."""

    def test_a_weekend_firing_preserves_the_previous_session(self, tmp_path,
                                                             monkeypatch):
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'status.json'))
        run_market_jobs._write(dict(
            generated='2026-10-23T18:30:00+05:30', ok=True, execution_ok=True,
            session='2026-08-21', corpus='7,385,306 daily rows',
            steps=[dict(step='daily vintages', ok=True)],
            data=dict(acquired='fresh', currency='current')))

        report = run_market_jobs.run_scheduled('2026-10-24')
        assert report['skipped'] is True
        assert report['session'] == '2026-08-21'
        assert report['steps'] == [dict(step='daily vintages', ok=True)]
        assert report['data']['acquired'] == 'fresh'

    def test_the_note_says_the_kept_fields_are_from_the_previous_run(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'status.json'))
        run_market_jobs._write(dict(generated='x', ok=True,
                                    session='2026-08-21'))
        report = run_market_jobs.run_scheduled('2026-10-24')
        assert 'last run that did work' in report['note']

    def test_a_first_ever_skip_does_not_invent_a_session(self, tmp_path,
                                                         monkeypatch):
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'status.json'))
        report = run_market_jobs.run_scheduled('2026-10-24')
        assert report['skipped'] is True
        assert 'session' not in report or report['session'] is None


class TestOverlapIsRefusedNotDuplicated:
    def test_a_held_lease_makes_the_second_firing_stand_aside(
            self, tmp_path, monkeypatch):
        """Two scheduler firings must not both estimate RMT and interleave
        two writes to the same status file."""
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'status.json'))
        monkeypatch.setattr(run_market_jobs, 'ROOT', tmp_path)
        run_market_jobs._write(dict(generated='x', ok=True,
                                    session='2026-08-21'))

        store = JobStore(tmp_path / 'prototype_runs' / 'jobs.sqlite')
        store.acquire(schedule.JOB_NAME, 'incumbent', lease_minutes=30)

        called = []
        monkeypatch.setattr(run_market_jobs, 'run_all',
                            lambda day=None: called.append(day))
        report = run_market_jobs.run_scheduled('2026-10-20')

        assert called == [], 'the pipeline ran while another holder had the lease'
        assert report['skipped'] is True
        assert 'stood aside' in report['note']
        assert report['session'] == '2026-08-21', 'the overlap clobbered history'


class TestTheLedgerMigrationThatR10Needed:
    """R10 added `generation` to `job_locks` under
    `CREATE TABLE IF NOT EXISTS`, which does nothing to an existing table.
    Lease fencing is a correctness mechanism and on every pre-existing
    installation it could not acquire a lease at all."""

    @staticmethod
    def _legacy(path: Path) -> None:
        db = sqlite3.connect(path)
        db.executescript('''
            CREATE TABLE job_locks (
                job TEXT PRIMARY KEY, owner TEXT NOT NULL,
                acquired_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                run_id TEXT NOT NULL);
            CREATE TABLE job_runs (
                run_id TEXT PRIMARY KEY, job TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT,
                status TEXT NOT NULL);
        ''')
        db.commit()
        db.close()

    def test_a_legacy_ledger_gains_the_fencing_column(self, tmp_path):
        path = tmp_path / 'jobs.sqlite'
        self._legacy(path)
        JobStore(path)
        db = sqlite3.connect(path)
        columns = {row[1] for row in db.execute('PRAGMA table_info(job_locks)')}
        assert 'generation' in columns

    def test_a_legacy_ledger_can_then_acquire_a_lease(self, tmp_path):
        """The exact failure: `table job_locks has 5 columns but 6 values
        were supplied`."""
        path = tmp_path / 'jobs.sqlite'
        self._legacy(path)
        store = JobStore(path)
        lease = store.acquire('market.daily', 'run-1', lease_minutes=5)
        assert lease['generation'] == 1

    def test_the_run_columns_are_added_too(self, tmp_path):
        path = tmp_path / 'jobs.sqlite'
        self._legacy(path)
        JobStore(path)
        db = sqlite3.connect(path)
        columns = {row[1] for row in db.execute('PRAGMA table_info(job_runs)')}
        assert {'attempt', 'error', 'detail'} <= columns

    def test_it_is_idempotent(self, tmp_path):
        path = tmp_path / 'jobs.sqlite'
        self._legacy(path)
        for _ in range(3):
            JobStore(path)
        db = sqlite3.connect(path)
        names = [row[1] for row in db.execute('PRAGMA table_info(job_locks)')]
        assert len(names) == len(set(names))

    def test_a_fresh_ledger_is_unaffected(self, tmp_path):
        store = JobStore(tmp_path / 'fresh.sqlite')
        assert store.acquire('j', 'r', lease_minutes=1)['generation'] == 1


class TestASuccessfulRunDoesNotExitOnAPrint:
    def test_an_out_of_tree_status_path_is_printed_not_raised(self, tmp_path,
                                                              monkeypatch,
                                                              capsys):
        """`relative_to` RAISES for a path outside the tree. A completely
        successful pipeline exited 1 on this line."""
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'outside.json'))
        monkeypatch.setattr(run_market_jobs, 'run_all', lambda day=None: dict(
            ok=True, session='2026-08-21', corpus='rows',
            steps=[dict(step='daily vintages', ok=True)]))
        code = run_market_jobs.main([])
        assert code == 0
        assert 'status:' in capsys.readouterr().out

    def test_the_source_no_longer_uses_the_import_time_constant(self):
        source = (SCRIPTS / 'run_market_jobs.py').read_text(encoding='utf-8')
        body = source.split('def main(', 1)[1]
        assert 'STATUS_PATH.relative_to' not in body


class TestTheRegistrationCommands:
    def test_the_task_runs_the_existing_pipeline(self):
        argv = schedule.register_command(python='py.exe',
                                         script='run_market_jobs.py')
        command = argv[argv.index('/tr') + 1]
        assert 'run_market_jobs.py' in command
        assert '--scheduled' in command

    def test_it_does_not_wrap_the_command_in_a_shell(self):
        """The `cmd /c cd /d ... &&` wrapper only added a layer of quoting
        that schtasks and PowerShell disagree about; the first registration
        failed on `Invalid argument/option - '&&'`. Both scripts resolve
        their paths from `__file__`, so no wrapper is needed."""
        argv = schedule.register_command(python='py.exe', script='s.py',
                                         working_directory='C:/anywhere')
        command = argv[argv.index('/tr') + 1]
        assert '&&' not in command
        assert 'cmd /c' not in command

    def test_re_registration_replaces_rather_than_duplicates(self):
        assert '/f' in schedule.register_command(python='p', script='s')

    def test_the_interpreter_is_the_virtualenv_one(self):
        """A task registered against a bare `python` resolves to whatever is
        on PATH at fire time and misses every dependency."""
        assert schedule.python_executable() == sys.executable
        assert Path(sys.executable).exists()

    def test_the_cron_line_is_weekdays_only(self):
        line = schedule.cron_line(python='py', script='s.py')
        assert '* * 1-5' in line
        assert '--scheduled' in line
        assert 'IST' in line

    def test_the_cron_line_states_the_local_conversion_when_they_differ(self):
        line = schedule.cron_line(python='py', script='s.py')
        if schedule.local_equals_ist():
            assert 'local on this machine' not in line
        else:
            assert 'local on this machine' in line

    def test_the_schedule_time_is_after_the_close(self):
        from seraph.market_calendar.sessions import REGULAR_CLOSE

        assert schedule.RUN_AT_IST > REGULAR_CLOSE

    def test_local_time_conversion_is_applied(self):
        """Task Scheduler and cron fire in local time. Assuming IST
        everywhere would run the job at the wrong hour off-shore."""
        converted = schedule.run_at_local(time(18, 30))
        expected = datetime.combine(date.today(), time(18, 30), tzinfo=IST)
        assert converted == expected.astimezone().timetz().replace(tzinfo=None)


class TestStalenessMarksWithoutDiscarding:
    """A failed or missed refresh keeps the last valid forecast -- the panel
    still shows it -- but must not present it as current."""

    def test_a_current_forecast_is_not_stale(self):
        result = schedule.prediction_staleness('2026-10-20',
                                               expected='2026-10-20')
        assert result['stale'] is False
        assert result['days_behind'] == 0

    def test_one_missed_session_is_within_the_allowance(self):
        result = schedule.prediction_staleness('2026-10-19',
                                               expected='2026-10-20')
        assert result['stale'] is False

    def test_a_longer_gap_is_stale(self):
        result = schedule.prediction_staleness('2026-10-10',
                                               expected='2026-10-20')
        assert result['stale'] is True
        assert 'NOT current' in result['detail']

    def test_a_wide_gap_points_at_ingestion_not_the_scheduler(self):
        result = schedule.prediction_staleness('2026-08-21',
                                               expected='2026-10-20')
        assert result['stale'] is True
        assert 'ingestion run' in result['detail']

    def test_no_saved_forecast_is_stale(self):
        assert schedule.prediction_staleness(None)['stale'] is True

    def test_the_surface_carries_it(self):
        from seraph.dashboard.console_backend import prediction_surface

        surface = prediction_surface()
        if surface['available']:
            assert 'staleness' in surface
            assert 'stale' in surface['staleness']


class TestTheHealthPanelShowsTheSchedule:
    def test_the_surface_has_a_schedule_section(self):
        from seraph.dashboard.console_backend import health_surface

        schedule_health = health_surface().get('schedule')
        assert schedule_health is not None
        for key in ('task_name', 'registered', 'last_run', 'data',
                    'expected_session'):
            assert key in schedule_health

    def test_it_separates_the_three_facts(self):
        from seraph.dashboard.console_backend import health_surface

        note = health_surface()['schedule']['note']
        assert 'three different facts' in note

    def test_an_unscheduled_installation_is_an_error_not_a_blank(self):
        """A pipeline that is never invoked produces no failures at all,
        which is the quietest way for a system to stop working."""
        body = (Path('seraph/dashboard/prototype_app.py')
                .read_text(encoding='utf-8'))
        panel = body.split('def health_panel', 1)[1].split('\ndef ', 1)[0]
        assert 'Not registered' in panel
        assert 'st.error' in panel

    def test_the_panel_reports_execution_and_data_separately(self):
        body = (Path('seraph/dashboard/prototype_app.py')
                .read_text(encoding='utf-8'))
        panel = body.split('def health_panel', 1)[1].split('\ndef ', 1)[0]
        assert 'execution' in panel
        assert "data.get('acquired'" in panel


class TestRecoveryAfterAMissedRun:
    def test_the_pipeline_recomputes_rather_than_resuming(self):
        """Nothing to catch up: `operational.run` rebuilds the whole series
        from the snapshot, so a missed day leaves no incremental state
        behind and the next run is simply correct."""
        import ast

        from seraph.prediction import operational

        source = Path(operational.__file__).read_text(encoding='utf-8')
        run = next(n for n in ast.walk(ast.parse(source))
                   if isinstance(n, ast.FunctionDef) and n.name == 'run')
        text = ast.get_source_segment(source, run) or ''
        assert 'resume' not in text.lower()
        assert 'checkpoint' not in text.lower()

    def test_every_step_is_idempotent_by_declaration(self):
        source = (SCRIPTS / 'run_market_jobs.py').read_text(encoding='utf-8')
        assert 'every step is idempotent' in source

    def test_an_abandoned_lease_does_not_block_the_next_firing(self, tmp_path):
        """A killed run must not hold the job forever. `reconcile_lock`
        clears a lease whose owner is gone."""
        store = JobStore(tmp_path / 'jobs.sqlite')
        store.acquire(schedule.JOB_NAME, 'dead-run', lease_minutes=30)
        # The owner must be THIS host with a dead pid: reconcile_lock
        # refuses to clear a lease it cannot verify, and a lease on another
        # host is exactly that case -- correctly, since the process may well
        # be alive there.
        import socket
        with sqlite3.connect(tmp_path / 'jobs.sqlite') as db:
            db.execute('UPDATE job_locks SET owner=? WHERE job=?',
                       (f'{socket.gethostname()}:999999', schedule.JOB_NAME))
        outcome = store.reconcile_lock(schedule.JOB_NAME,
                                       reason='test recovery')
        assert outcome['cleared'] is True
        assert store.acquire(schedule.JOB_NAME, 'next-run',
                             lease_minutes=5)['generation'] >= 2


class TestAFailedRunDoesNotReadAsTheLastGoodOne:
    """If the pipeline raises inside the lease, `run_all` never reaches
    `_write`, so the status file still holds the PREVIOUS run. Returning it
    unannotated would make last week's green steps read as this firing's
    result."""

    def test_the_failure_is_recorded_over_the_old_success(self, tmp_path,
                                                          monkeypatch):
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'status.json'))
        monkeypatch.setattr(run_market_jobs, 'ROOT', tmp_path)
        run_market_jobs._write(dict(
            generated='2026-10-19T18:30:00+05:30', ok=True, execution_ok=True,
            session='2026-08-21',
            steps=[dict(step='daily vintages', ok=True)],
            data=dict(acquired='fresh', currency='current')))

        def boom(day=None):
            raise RuntimeError('the corpus exploded')

        monkeypatch.setattr(run_market_jobs, 'run_all', boom)
        report = run_market_jobs.run_scheduled('2026-10-20')

        assert report['ok'] is False
        assert report['execution_ok'] is False
        assert 'FAILED under the lease' in report['note']
        assert 'the corpus exploded' in report['note']
        assert 'describe the last run that completed' in report['note']

    def test_the_ledger_records_it_too(self, tmp_path, monkeypatch):
        """So the HEALTH panel's job check sees the failure, not just the
        status file."""
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'status.json'))
        monkeypatch.setattr(run_market_jobs, 'ROOT', tmp_path)
        monkeypatch.setattr(run_market_jobs, 'run_all',
                            lambda day=None: (_ for _ in ()).throw(
                                RuntimeError('nope')))
        run_market_jobs.run_scheduled('2026-10-20')

        store = JobStore(tmp_path / 'prototype_runs' / 'jobs.sqlite')
        runs = store.runs(schedule.JOB_NAME, limit=3)
        assert runs and runs[0].status == 'failed'

    def test_a_successful_run_is_not_annotated_as_failed(self, tmp_path,
                                                         monkeypatch):
        monkeypatch.setenv('SERAPH_MARKET_JOBS_STATUS',
                           str(tmp_path / 'status.json'))
        monkeypatch.setattr(run_market_jobs, 'ROOT', tmp_path)
        monkeypatch.setattr(run_market_jobs, 'run_all', lambda day=None: (
            run_market_jobs._write(dict(generated='now', ok=True,
                                        execution_ok=True,
                                        session='2026-08-21', steps=[],
                                        data=dict(acquired='unchanged',
                                                  currency='current')))
            or dict(ok=True)))
        report = run_market_jobs.run_scheduled('2026-10-20')
        assert report['ok'] is True
        assert report['job_run']['status'] == 'succeeded'
        assert 'FAILED' not in report.get('note', '')
