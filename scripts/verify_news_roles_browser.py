"""C12 NI16 — verify role news and real portfolio submission in a browser.

Uses isolated SQLite backups and the normal Streamlit component protocol.
No evidence payload injection, acquisition requests or original-store writes.
"""
import argparse
import base64
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

from audit_console_browser import CDP, await_http, free_port
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]


def wait_for(cdp, context, expression, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = cdp.evaluate(expression, context)
        if result:
            return result
        time.sleep(.2)
    raise AssertionError(f'Browser did not reach expected state: {expression}')


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    temp = ROOT/'prototype_runs'/('news-roles-'+uuid4().hex[:8])
    temp.mkdir()
    for source, target in [('seraph.sqlite', 'runs.sqlite'),
                           ('news-intelligence-pilot.sqlite', 'news.sqlite')]:
        with closing(sqlite3.connect((ROOT/'prototype_runs'/source).resolve().as_uri()+'?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(temp/target)) as dst:
                src.backup(dst)
    env = dict(os.environ, SERAPH_PROTOTYPE_STORE=str(temp/'runs.sqlite'),
               SERAPH_NEWS_STORE=str(temp/'news.sqlite'), OPENBLAS_NUM_THREADS='1',
               OMP_NUM_THREADS='1', PYTHONIOENCODING='utf-8')
    app_port, debug_port = free_port(), free_port()
    processes = []
    with (output/'browser.log').open('w', encoding='utf-8') as log:
        try:
            processes.append(subprocess.Popen([sys.executable, '-m', 'streamlit', 'run',
                str(ROOT/'seraph/dashboard/prototype_app.py'), '--server.address=127.0.0.1',
                f'--server.port={app_port}', '--server.headless=true',
                '--browser.gatherUsageStats=false'], cwd=ROOT, env=env, stdout=log, stderr=log))
            await_http(f'http://127.0.0.1:{app_port}/_stcore/health')
            edge = Path(os.environ['ProgramFiles(x86)'])/'Microsoft/Edge/Application/msedge.exe'
            processes.append(subprocess.Popen([str(edge), '--headless=new', '--no-first-run',
                '--disable-background-networking', '--enable-unsafe-swiftshader',
                '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',
                f'--user-data-dir={temp/"edge"}', f'--remote-debugging-port={debug_port}',
                '--window-size=1800,1400', 'about:blank'], stdout=log, stderr=log))
            pages = json.loads(await_http(f'http://127.0.0.1:{debug_port}/json/list'))
            endpoint = next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page')
            with connect(endpoint, max_size=20_000_000) as ws:
                cdp = CDP(ws)
                cdp.call('Page.enable')
                cdp.call('Runtime.enable')
                cdp.call('Page.navigate', url=f'http://127.0.0.1:{app_port}')
                context = cdp.component()
                roles = {}
                for role in ('institutional', 'regulator', 'retail'):
                    cdp.evaluate(f"document.querySelector('#roles button[data-role={role}]').click()", context)
                    wait_for(cdp, context, f"document.querySelector('#roles button.on')?.dataset.role === '{role}' && document.querySelector('#role-news-home')?.textContent.includes('{role.upper()} NEWS INTELLIGENCE')")
                    roles[role] = cdp.evaluate("document.querySelector('#role-news-home').textContent", context)
                    assert 'role view unavailable' not in roles[role].lower()
                    layout = cdp.evaluate("""(()=>{const panel=document.querySelector('#role-news-home');
                      const p=panel.getBoundingClientRect(), host=panel.parentElement;
                      const siblings=[...host.children].filter(n=>n!==panel).map(n=>n.getBoundingClientRect());
                      return {width:p.width,hostWidth:host.clientWidth,visible:!!panel.getClientRects().length,
                        overlap:siblings.some(r=>p.top<r.bottom-1 && p.bottom>r.top+1)};})()""", context)
                    assert layout['visible'] and layout['width'] > layout['hostWidth']*.9, layout
                    assert not layout['overlap'], layout
                # Submit through the ordinary UI, exercising C11's aggregate
                # byHolding result on its way back into the news projection.
                cdp.evaluate("document.querySelector('nav a[data-view=tools]').click()", context)
                holdings = json.dumps([dict(symbol='TATASTEEL', sector='steel', value=100),
                                       dict(symbol='UNMAPPED_NEWS_TEST', value=50)])
                cdp.evaluate(f"document.querySelector('#holdings').value={json.dumps(holdings)}; document.querySelector('#portfolio-go').click()", context)
                wait_for(cdp, context, "document.querySelector('#req-status')?.textContent.includes('DONE') && document.querySelector('#req-status')?.textContent.includes('portfolio')")
                cdp.evaluate("document.querySelector('#roles button[data-role=retail]').click()", context)
                retail = wait_for(cdp, context, "document.querySelector('#role-news-home')?.textContent.includes('TATASTEEL') && document.querySelector('#role-news-home').textContent")
                assert 'UNMAPPED_NEWS_TEST' in retail and 'UNMAPPED' in retail
                assert 'Portfolio weight (not loss)' in retail
                cdp.evaluate("document.querySelector('#role-news-home').scrollIntoView({block:'start'})", context)
                cdp.evaluate("document.querySelector('iframe').scrollIntoView({block:'start'})")
                screenshot = cdp.call('Page.captureScreenshot', format='png')
                (output/'retail.png').write_bytes(base64.b64decode(screenshot['data']))
                cdp.evaluate("document.querySelector('nav a[data-view=map]').click()", context)
                plan = cdp.evaluate('window.SERAPH_GLOBE_API.plan()', context)
                assert plan['markers']
                cdp.evaluate("document.querySelector('[data-news-node]').click()", context)
                links = cdp.evaluate("[...document.querySelectorAll('#dbody a')].map(a=>a.href)", context)
                assert links
                report = dict(roles=roles, retail_with_holdings=retail, globe_markers=len(plan['markers']),
                              evidence_links=links, ordinary_streamlit_flow=True, payload_injection=False,
                              isolated_store=str(temp/'news.sqlite'))
                (output/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps(dict(roles=list(roles), portfolio=True, unmapped_warning=True,
                                      globe_markers=len(plan['markers']), evidence_links=len(links))))
        finally:
            for process in reversed(processes):
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=log, stderr=log, check=False)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
