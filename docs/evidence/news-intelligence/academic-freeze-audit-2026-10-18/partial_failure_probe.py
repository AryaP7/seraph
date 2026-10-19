"""Audit only: a partial source outage through worker and supervisor contracts.

Disposable SQLite; fake feed and child process. No network/process termination.
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
import run_news
import news_supervisor
from seraph.news.acquisition import NewsStore, _now

def main():
    with tempfile.TemporaryDirectory(prefix='seraph-partial-outage-') as folder:
        area = Path(folder)
        store = NewsStore(area / 'news.sqlite')
        args = argparse.Namespace(jobs=area/'jobs.sqlite', backfill=False,
                                  once=False, catch_up=False, interval=30)
        seen = []
        def stop(_seconds):
            seen.append(store.worker_state(_now()))
            raise KeyboardInterrupt
        reports = [dict(source_id='working_feed', ok=True, new_stories=1),
                   dict(source_id='temporarily_unavailable_feed', ok=False,
                        new_stories=0, error='HTTP 503')]
        with patch.object(run_news, 'register', return_value=0), \
             patch.object(run_news, 'build_fetcher', return_value=object()), \
             patch.object(run_news, 'poll_once', return_value=reports), \
             patch.object(run_news.time, 'sleep', side_effect=stop), \
             contextlib.redirect_stdout(io.StringIO()):
            run_news._run_worker(args, store)

        children = []
        class Child:
            def __init__(self):
                self.pid = 900000 + len(children)
                self.signalled = False
            def wait(self, timeout=None):
                if self.signalled:
                    return 1
                raise subprocess.TimeoutExpired('audit-fake-child', timeout)
            def poll(self):
                return 1 if self.signalled else None
            def send_signal(self, _signal):
                self.signalled = True
            def kill(self):
                self.signalled = True
        def spawn(*_args, **_kwargs):
            child = Child()
            children.append(child)
            store.beat(pid=child.pid, status=seen[0]['state'],
                       activity=seen[0]['activity'], detail=seen[0]['detail'])
            return child
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = news_supervisor.supervise(
                store.path, interval=30, max_restarts=2, once=False,
                spawn=spawn, sleep=lambda _: None, startup_grace=0,
                check_seconds=.01)
        result = dict(
            type='controlled contract reproduction, not a real publisher outage',
            one_successful_source=True, one_source_http_503=True,
            worker_after_partial_failure=seen[0],
            supervisor_child_starts=len(children),
            supervisor_terminations=sum(c.signalled for c in children),
            supervisor_exit=exit_code,
            final_state=store.worker_state(_now()),
            expected='a live progressing worker should keep good feeds acquiring; source failure stays visible')
        target = Path(__file__).with_name('partial-failure-result.json')
        target.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
