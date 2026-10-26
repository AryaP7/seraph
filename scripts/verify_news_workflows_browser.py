"""C12 — the role WORKFLOWS, driven through the real UI.

`verify_news_roles_browser.py` proves the three role projections render.
It does not press anything: a review queue on screen is not a review
workflow, and a scenario function nothing can supply inputs to is not a
scenario feature. This exercises the controls themselves.

What it drives, as a user would:

* institutional — the product/country matrix is present; the conditional
  scenario form takes the caller's assumptions and returns either an
  arithmetic result or a NAMED reason it cannot; export returns the
  analysis with its evidence and limitations.
* regulator — an instrument-link decision is refused without a reason,
  accepted with one, and the recorded decision names a DEMO role rather
  than an authenticated user. Persistence is checked in the STORE, not
  taken from the status line.

Two things learned the hard way and encoded here: the request status
lives in `#req-status-global` (`#req-status` exists only inside the TOOLS
view), and `request()` DROPS a call while another is in flight, so every
action waits for the previous one to settle.

Isolated SQLite copies, the ordinary Streamlit component protocol, no
injected payloads. Usage:

    python scripts/verify_news_workflows_browser.py --output DIR
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from audit_console_browser import CDP, await_http, free_port
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATUS = "document.querySelector('#req-status-global')?.textContent || ''"


def wait_idle(cdp, context, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = cdp.evaluate(STATUS, context) or ''
        if 'SENDING' not in text.upper():
            return text
        time.sleep(.5)
    return cdp.evaluate(STATUS, context) or ''


def wait_settled(cdp, context, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = cdp.evaluate(STATUS, context) or ''
        if any(word in text.upper() for word in ('DONE', 'FAILED', 'TIMED')):
            return text
        time.sleep(.5)
    return cdp.evaluate(STATUS, context) or ''


def wait_for(cdp, context, expression, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = cdp.evaluate(expression, context)
        if result:
            return result
        time.sleep(.25)
    return None


def main(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    temp = ROOT / 'prototype_runs' / ('news-workflows-' + uuid4().hex[:8])
    temp.mkdir()
    for source, target in [('seraph.sqlite', 'runs.sqlite'),
                           ('news-intelligence-pilot.sqlite', 'news.sqlite')]:
        uri = (ROOT / 'prototype_runs' / source).resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True)) as src:
            with closing(sqlite3.connect(temp / target)) as dst:
                src.backup(dst)
    env = dict(os.environ, SERAPH_PROTOTYPE_STORE=str(temp / 'runs.sqlite'),
               SERAPH_NEWS_STORE=str(temp / 'news.sqlite'),
               # The worker is not the subject here, and a live one makes
               # the page move under the assertions.
               SERAPH_NEWS_WORKER='0',
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               PYTHONIOENCODING='utf-8')
    app_port, debug_port = free_port(), free_port()
    processes, report = [], {}
    with (output / 'browser.log').open('w', encoding='utf-8') as log:
        try:
            edge = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft/Edge/Application/msedge.exe'
            processes.append(subprocess.Popen(
                [str(edge), '--headless=new', '--no-first-run',
                 '--disable-background-networking', '--enable-unsafe-swiftshader',
                 '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',
                 f'--user-data-dir={temp / "edge"}',
                 f'--remote-debugging-port={debug_port}',
                 '--window-size=1800,1400', 'about:blank'], stdout=log, stderr=log))
            pages = json.loads(await_http(f'http://127.0.0.1:{debug_port}/json/list',
                                          timeout=120))
            endpoint = next(p['webSocketDebuggerUrl'] for p in pages
                            if p['type'] == 'page')
            processes.append(subprocess.Popen(
                [sys.executable, '-m', 'streamlit', 'run',
                 str(ROOT / 'seraph/dashboard/prototype_app.py'),
                 '--server.address=127.0.0.1', f'--server.port={app_port}',
                 '--server.headless=true', '--browser.gatherUsageStats=false'],
                cwd=ROOT, env=env, stdout=log, stderr=log))
            await_http(f'http://127.0.0.1:{app_port}/_stcore/health', timeout=120)

            with connect(endpoint, max_size=20_000_000) as ws:
                cdp = CDP(ws)
                cdp.call('Page.enable')
                cdp.call('Runtime.enable')
                downloads = output.resolve() / 'downloads'
                downloads.mkdir(exist_ok=True)
                cdp.call('Browser.setDownloadBehavior', behavior='allow', downloadPath=str(downloads))
                cdp.call('Page.navigate', url=f'http://127.0.0.1:{app_port}')
                context = cdp.component()
                wait_for(cdp, context, "!!document.querySelector('#roles button')")

                # ---------------------------------------- institutional
                cdp.evaluate("document.querySelector("
                             "'#roles button[data-role=institutional]').click()",
                             context)
                panel = wait_for(
                    cdp, context,
                    "document.querySelector('#role-news-home')"
                    "?.textContent.includes('INSTITUTIONAL NEWS')"
                    " && document.querySelector('#role-news-home').textContent")
                report['institutional_panel'] = bool(panel)
                report['matrix_rendered'] = bool(
                    panel and 'PRODUCT' in panel and 'EXPOSURE' in panel)
                report['matrix_says_unsized'] = bool(panel and 'UNSIZED' in panel)
                report['scenario_form_rendered'] = bool(cdp.evaluate(
                    "!!document.querySelector('#news-scenario-go')", context))
                report['export_button_rendered'] = bool(cdp.evaluate(
                    "!!document.querySelector('#news-export-go')", context))
                report['compare_offered'] = bool(cdp.evaluate(
                    "!!document.querySelector('#news-compare-go')", context))

                if report['scenario_form_rendered']:
                    wait_idle(cdp, context)
                    cdp.evaluate(
                        "document.querySelector('#news-scenario-base').value='1000000';"
                        "document.querySelector('#news-scenario-low').value='0.5';"
                        "document.querySelector('#news-scenario-high').value='0.8';"
                        "document.querySelector('#news-scenario-go').click()",
                        context)
                    report['scenario_status'] = wait_settled(cdp, context)

                wait_idle(cdp, context)
                cdp.evaluate("document.querySelector('#news-export-go').click()",
                             context)
                report['export_status'] = wait_settled(cdp, context)
                link = wait_for(cdp, context, "document.querySelector('#news-export-link')?.download")
                report['download_link'] = link
                if link:
                    cdp.evaluate("document.querySelector('#news-export-link').click()", context)
                    deadline = time.monotonic() + 30
                    while not (downloads / link).exists() and time.monotonic() < deadline:
                        time.sleep(.25)
                    downloaded = json.loads((downloads / link).read_text(encoding='utf-8'))
                    report['download_verified'] = bool(downloaded.get('analysis_id') and downloaded.get('matrix'))
                    report['download_scenario_matches_inputs'] = (downloaded.get('scenario') or {}).get('inputs', {}).get('cost_base') == '1000000'
                    report['download_decision_ts'] = downloaded.get('decision_ts')


                # The result itself is rendered in the TOOLS view.
                wait_idle(cdp, context)
                cdp.evaluate(
                    "document.querySelector('nav a[data-view=tools]').click()",
                    context)
                shown = wait_for(
                    cdp, context,
                    "document.querySelector('#viewExtra')?.textContent",
                    timeout=30) or ''
                report['result_rendered'] = any(
                    k in shown for k in ('news_export', 'news_scenario'))
                report['export_carries_limitations'] = 'limitations' in shown

                # -------------------------------------------- regulator
                wait_idle(cdp, context)
                cdp.evaluate("document.querySelector("
                             "'#roles button[data-role=regulator]').click()",
                             context)
                reg = wait_for(
                    cdp, context,
                    "document.querySelector('#role-news-home')"
                    "?.textContent.includes('REGULATOR NEWS')"
                    " && document.querySelector('#role-news-home').textContent")
                report['regulator_panel'] = bool(reg)
                report['review_queue_rendered'] = bool(
                    reg and 'INSTRUMENT LINK REVIEW' in reg)
                report['role_is_regulator'] = cdp.evaluate(
                    "document.querySelector('#roles button.on')?.dataset.role",
                    context)
                report['review_controls'] = cdp.evaluate(
                    "document.querySelectorAll('.news-review-go').length", context)

                if report['review_controls']:
                    wait_idle(cdp, context)
                    cdp.evaluate(
                        "(()=>{const c=document.querySelector('.news-review');"
                        "c.querySelector('.news-review-earlier').value='evt_probe_earlier';"
                        "c.querySelector('.news-review-reason').value='';"
                        "c.querySelector('.news-review-go').click();})()", context)
                    time.sleep(2)
                    refused = cdp.evaluate(STATUS, context) or ''
                    report['refused_without_reason'] = 'reason' in refused.lower()

                    wait_idle(cdp, context)
                    cdp.evaluate(
                        "(()=>{const c=document.querySelector('.news-review');"
                        "c.querySelector('.news-review-earlier').value='evt_probe_earlier';"
                        "c.querySelector('.news-review-reason').value="
                        "'probe: same case number, confirmed against the register';"
                        "c.querySelector('.news-review-go').click();})()", context)
                    report['review_status'] = wait_settled(cdp, context)

                shot = cdp.call('Page.captureScreenshot', format='png')
                (output / 'workflows.png').write_bytes(base64.b64decode(shot['data']))

            # The decision must be ON FILE, and must say it was a demo role.
            from seraph.news.acquisition import NewsStore
            decisions = NewsStore(temp / 'news.sqlite').supersession_decisions()
            report['decisions_recorded'] = len(decisions['decisions'])
            report['decision_rows'] = decisions['decisions'][:3]
            report['recorded_as_demo_identity'] = (
                all(str(d['reviewer']).startswith('demo-role:')
                    for d in decisions['decisions'])
                if decisions['decisions'] else None)
        finally:
            for process in reversed(processes):
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=log, stderr=log, check=False)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
    (output / 'result.json').write_text(json.dumps(report, indent=2),
                                        encoding='utf-8')
    shutil.rmtree(temp, ignore_errors=True)
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(main(parser.parse_args().output))
