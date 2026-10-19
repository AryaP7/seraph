"""A partial source outage through the worker and supervisor contracts.

Adapted from the academic-freeze audit's probe of the same name, which
reproduced the defect. Two changes were needed to re-run it against the
fix:

* The original let the supervisor loop until it terminated the child. With
  the fix it never does, so the fake child's `wait()` raised
  `TimeoutExpired` for ever and the probe hung. The supervisor is now
  driven for a bounded number of checks.
* A second case was added for the protection that must SURVIVE the fix: a
  worker that stops beating is still replaced.

Disposable SQLite; fake feed and child processes. No network, no real
process termination.
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import run_news                                                 # noqa: E402
import news_supervisor                                          # noqa: E402
from seraph.news.acquisition import NewsStore, _now             # noqa: E402


class Child:
    """A child that stays alive until somebody signals it."""

    def __init__(self, pid):
        self.pid, self.signalled = pid, False

    def wait(self, timeout=None):
        if self.signalled:
            return 1
        raise subprocess.TimeoutExpired('probe-fake-child', timeout)

    def poll(self):
        return 1 if self.signalled else None

    def send_signal(self, _signal):
        self.signalled = True

    def kill(self):
        self.signalled = True


def one_worker_pass(store, reports):
    """Drive the real `_run_worker` for a single pass with these reports."""
    seen = []

    def stop(_seconds):
        seen.append(store.worker_state(_now()))
        raise KeyboardInterrupt

    args = argparse.Namespace(jobs=store.path.parent / 'jobs.sqlite',
                              backfill=False, once=False, catch_up=False,
                              interval=30)
    with patch.object(run_news, 'register', return_value=0), \
         patch.object(run_news, 'build_fetcher', return_value=object()), \
         patch.object(run_news, 'poll_once', return_value=reports), \
         patch.object(run_news.time, 'sleep', side_effect=stop), \
         contextlib.redirect_stdout(io.StringIO()):
        run_news._run_worker(args, store)
    return seen[0]


def drive_supervisor(store, *, beat_state, beat_activity, beat_detail,
                     max_checks, max_restarts=2):
    """Run the real `supervise` for a bounded number of liveness checks."""
    children, checks = [], {'n': 0}

    def spawn(*_a, **_k):
        child = Child(900000 + len(children))
        children.append(child)
        store.beat(pid=child.pid, status=beat_state, activity=beat_activity,
                   detail=beat_detail)
        return child

    def monotonic():
        # Each liveness check advances the clock past the startup grace and,
        # after `max_checks`, raises so the bounded probe always terminates.
        checks['n'] += 1
        if checks['n'] > max_checks:
            raise KeyboardInterrupt
        return float(checks['n'])

    with contextlib.redirect_stdout(io.StringIO()):
        exit_code = news_supervisor.supervise(
            store.path, interval=30, max_restarts=max_restarts, once=False,
            spawn=spawn, sleep=lambda _: None, startup_grace=0,
            check_seconds=.01, monotonic=monotonic)
    return dict(starts=len(children),
                # `starts - 1` is what the supervisor actually DECIDED to
                # do. The terminations count includes the one the probe
                # itself causes: ending the bounded loop raises
                # KeyboardInterrupt, and `supervise`'s `finally` signals
                # its child on the way out, which is correct teardown and
                # not a restart decision.
                restarts=max(0, len(children) - 1),
                terminations=sum(c.signalled for c in children),
                exit=exit_code, checks=checks['n'])


def main():
    result = {'type': 'controlled contract reproduction, '
                      'not a real publisher outage'}

    # --- one source down, one healthy -------------------------------
    with tempfile.TemporaryDirectory(prefix='seraph-partial-outage-') as folder:
        store = NewsStore(Path(folder) / 'news.sqlite')
        reports = [dict(source_id='working_feed', ok=True, new_stories=1),
                   dict(source_id='temporarily_unavailable_feed', ok=False,
                        new_stories=0, error='HTTP 503')]
        state = one_worker_pass(store, reports)
        result['partial_outage'] = dict(
            one_successful_source=True, one_source_http_503=True,
            worker_state=state['state'], worker_activity=state['activity'],
            worker_detail=state['detail'],
            worker_is_alive=state['state'] in NewsStore.ALIVE_STATUSES,
            supervisor=drive_supervisor(
                store, beat_state=state['state'],
                beat_activity=state['activity'], beat_detail=state['detail'],
                max_checks=40),
            expected=('the worker stays alive and keeps polling; the failed '
                      'source stays visible in its own health'))

    # --- the protection that must survive: a worker that stops ------
    with tempfile.TemporaryDirectory(prefix='seraph-dead-worker-') as folder:
        store = NewsStore(Path(folder) / 'news.sqlite')
        result['stopped_worker'] = dict(
            supervisor=drive_supervisor(
                store, beat_state='stopped', beat_activity='stopped',
                beat_detail='worker stopped beating', max_checks=40),
            expected=('a worker that is not alive is still terminated and '
                      'replaced, up to the restart bound'))

    Path(__file__).with_name('partial-failure-result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
