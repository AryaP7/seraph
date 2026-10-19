"""NI11/NI12 — verify in the real browser what was added today.

Three claims, each checked against the rendered DOM rather than the payload:

1. The sector panel reaches **five** sectors, with a direction and a mechanism
   on each row, from documents in the store.
2. A **forthcoming** Federal Register document is labelled as scheduled, not
   presented as already published. 44 stories in the pilot carry a publication
   date that has not arrived.
3. The evidence on a sector row is **clickable** through to the government
   document the inference was drawn from.

Like `verify_news_browser.py` this works on read-only copies of the stores and
drives the ordinary Streamlit flow — no payload injection.
"""
from __future__ import annotations

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
OUT = ROOT / 'docs/evidence/news-intelligence'


def main(simulate_dead_worker: bool = False) -> int:
    temp = ROOT / 'prototype_runs' / ('news-sectors-' + uuid4().hex[:8])
    temp.mkdir()
    for source, dest in [('seraph.sqlite', 'runs.sqlite'),
                         ('news-intelligence-pilot.sqlite', 'news.sqlite')]:
        uri = (ROOT / 'prototype_runs' / source).resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True)) as src:
            with closing(sqlite3.connect(temp / dest)) as dst:
                src.backup(dst)
    if simulate_dead_worker:
        # Age the heartbeat IN THE COPY so the warning path is exercised. The
        # real store is untouched, and nothing else is altered: a verification
        # that can only ever observe the healthy case verifies nothing about
        # the warning.
        with closing(sqlite3.connect(temp / 'news.sqlite')) as db:
            db.execute("UPDATE worker_heartbeat SET beat_at=?, status='running'",
                       ('2020-01-01T00:00:00+05:30',))
            if db.total_changes == 0:
                db.execute("INSERT INTO worker_heartbeat "
                           "(worker,beat_at,pid,status) VALUES (?,?,?,?)",
                           ('news.poll', '2020-01-01T00:00:00+05:30', 1, 'running'))
            db.commit()
        print('[verify] heartbeat in the COPY aged to 2020 to exercise the '
              'stopped-worker warning')

    env = dict(os.environ, SERAPH_PROTOTYPE_STORE=str(temp / 'runs.sqlite'),
               SERAPH_NEWS_STORE=str(temp / 'news.sqlite'),
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               PYTHONIOENCODING='utf-8')
    app_port, debug_port = free_port(), free_port()
    processes = []
    with (OUT / 'browser-sectors.log').open('w', encoding='utf-8') as log:
        try:
            processes.append(subprocess.Popen(
                [sys.executable, '-m', 'streamlit', 'run',
                 str(ROOT / 'seraph/dashboard/prototype_app.py'),
                 '--server.address=127.0.0.1', f'--server.port={app_port}',
                 '--server.headless=true', '--browser.gatherUsageStats=false'],
                cwd=ROOT, env=env, stdout=log, stderr=log))
            await_http(f'http://127.0.0.1:{app_port}/_stcore/health')
            edge = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft/Edge/Application/msedge.exe'
            processes.append(subprocess.Popen(
                [str(edge), '--headless=new', '--no-first-run',
                 '--disable-background-networking', '--enable-unsafe-swiftshader',
                 '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',
                 f'--user-data-dir={temp / "edge"}',
                 f'--remote-debugging-port={debug_port}',
                 '--window-size=1800,1400', 'about:blank'],
                stdout=log, stderr=log))
            pages = json.loads(await_http(f'http://127.0.0.1:{debug_port}/json/list'))
            with connect(next(p for p in pages if p['type'] == 'page')['webSocketDebuggerUrl'],
                         max_size=20_000_000) as ws:
                cdp = CDP(ws)
                cdp.call('Page.enable')
                cdp.call('Runtime.enable')
                cdp.call('Page.navigate', url=f'http://127.0.0.1:{app_port}')
                context = cdp.component()

                # 1. the sector panel, as rendered
                sectors = cdp.evaluate("""JSON.parse(JSON.stringify({
                    text: document.querySelector('#stress')?.textContent || '',
                    rows: [...document.querySelectorAll('#stress [data-event-ids]')]
                            .map(function(e){return e.textContent.trim();}).filter(Boolean)
                }))""", context)

                # 2a. the scope split, which must be stated not merely held
                # Read the line from its own element. Scraping textContent for
                # it bleeds the neighbouring event counter in front and the
                # first headline behind, which made the count unreadable.
                scope = cdp.evaluate(r"""JSON.parse(JSON.stringify({
                    line: ([...document.querySelectorAll('#signals p.m')]
                             .map(function(e){return e.textContent;})
                             .filter(function(t){return /\sin scope\s/.test(t);})[0] || ''),
                    reasons: ((document.querySelector('#signals')?.textContent || '')
                             .match(/(?:Not in scope|In scope):/g) || []).length
                }))""", context)

                # 2c. the role projection must reach the console payload.
                roles = cdp.evaluate(r"""JSON.parse(JSON.stringify({
                    has_role_view: !!(window.__SERAPH_LAST_PAYLOAD
                        && window.__SERAPH_LAST_PAYLOAD.news
                        && window.__SERAPH_LAST_PAYLOAD.news.role_view),
                    opposing_rendered: /Constrains:/.test(
                        document.querySelector('#signals')?.textContent || '')
                }))""", context)

                # 2b. worker liveness and staleness, as RENDERED. The point
                # of this whole block is that a stopped worker must not look
                # like a quiet market, so it is checked on the page, not in
                # the payload.
                liveness = cdp.evaluate(r"""JSON.parse(JSON.stringify({
                    banner: (document.querySelector('#preview-banner')?.textContent || ''),
                    stress: (document.querySelector('#stress')?.textContent || ''),
                    says_no_worker: /NO WORKER|WORKER STOPPED|WORKER FAILED/.test(
                        (document.querySelector('#preview-banner')?.textContent || '')
                        + (document.querySelector('#stress')?.textContent || '')),
                    says_stale: /STALE/.test(
                        (document.querySelector('#preview-banner')?.textContent || '')
                        + (document.querySelector('#stress')?.textContent || ''))
                }))""", context)

                # 2. the whole signal rail's text, to find the scheduled label
                rail = cdp.evaluate("""JSON.parse(JSON.stringify({
                    text: document.querySelector('#signals')?.textContent || '',
                    scheduled: (document.querySelector('#signals')?.textContent || '')
                                 .match(/scheduled for publication[^\\u00b7]*/gi) || []
                }))""", context)

                # 3. click an event the sector panel points at, and read its links
                clicked = cdp.evaluate("""(function(){
                    var el = document.querySelector('#signals details.sig');
                    if(!el) return {opened:false};
                    el.open = true;
                    return {opened:true,
                            text: el.textContent,
                            links: [...el.querySelectorAll('a')].map(function(a){return a.href;})};
                })()""", context)

                mentions = {name: name.replace('sector:', '') in sectors['text'].lower()
                            for name in ('sector:agriculture', 'sector:aluminium',
                                         'sector:auto', 'sector:chemicals',
                                         'sector:steel', 'sector:textiles',
                                         'sector:paper_packaging',
                                         'sector:industrial_materials')}

                shot = cdp.call('Page.captureScreenshot', format='png')
                (OUT / 'sectors-and-forthcoming.png').write_bytes(
                    base64.b64decode(shot['data']))

                result = dict(
                    opposing_rendered=roles['opposing_rendered'],
                    worker_warning_rendered=liveness['says_no_worker'],
                    stale_warning_rendered=liveness['says_stale'],
                    banner_excerpt=liveness['banner'][:300],
                    scope_line=scope['line'], scope_reason_labels=scope['reasons'],
                    sector_panel_rows=sectors['rows'][:40],
                    sectors_named=mentions,
                    sectors_named_count=sum(mentions.values()),
                    forthcoming_labels=rail['scheduled'][:10],
                    forthcoming_label_count=len(rail['scheduled']),
                    rail_says_published_without_qualifier=(
                        'Published' in rail['text']
                        and not rail['scheduled']),
                    clicked_event=dict(
                        opened=clicked.get('opened'),
                        links=clicked.get('links', [])[:8],
                        # The property that matters is that the evidence
                        # resolves to a PUBLISHER, not that it happens to be
                        # a .gov. Page one is now exchange announcements, and
                        # a .gov check would have quietly started failing for
                        # a reason that is not a defect.
                        publisher_links=[u for u in clicked.get('links', [])
                                         if any(d in u for d in (
                                             'federalregister.gov', 'rbi.org',
                                             'sebi.gov', 'nseindia.com',
                                             'bseindia.com', 'usgs.gov',
                                             'federalreserve.gov', 'ustr.gov',
                                             'pib.gov.in', 'europa.eu'))],
                    ),
                    ordinary_streamlit_flow=True, payload_injection=False,
                    isolated_store=str(temp / 'news.sqlite'))
                (OUT / 'sectors-and-forthcoming.json').write_text(
                    json.dumps(result, indent=2), encoding='utf-8')
                print(json.dumps(dict(
                    opposing_rendered=result['opposing_rendered'],
                    worker_warning_rendered=result['worker_warning_rendered'],
                    stale_warning_rendered=result['stale_warning_rendered'],
                    scope_line=result['scope_line'],
                    scope_reason_labels=result['scope_reason_labels'],
                    sectors_named=result['sectors_named_count'],
                    forthcoming_labels=result['forthcoming_label_count'],
                    clicked_links=len(result['clicked_event']['links']),
                    publisher_links=len(result['clicked_event']['publisher_links'])),
                    indent=2))
                return 0
        finally:
            for p in reversed(processes):
                subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'],
                               stdout=log, stderr=log, check=False)
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
            # Each run copies both stores — ~170MB — and four runs while
            # getting one selector right left 670MB of throwaway copies
            # behind. The evidence JSON and PNG are the durable output; the
            # copy is scaffolding, and it is removed only if it is the
            # directory this run created.
            if temp.name.startswith('news-sectors-') and temp.is_dir():
                shutil.rmtree(temp, ignore_errors=True)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--simulate-dead-worker', action='store_true',
                    help='age the heartbeat in the throwaway COPY so the '
                         'stopped-worker warning is exercised')
    raise SystemExit(main(ap.parse_args().simulate_dead_worker))
