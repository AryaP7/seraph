"""C12 NI15 ordinary Streamlit flow and auto-refresh, isolated real-data copies."""
from __future__ import annotations
import base64,json,os,sqlite3,subprocess,sys,time
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from audit_console_browser import CDP,free_port,await_http
from websockets.sync.client import connect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'docs/evidence/news-intelligence'

def main():
    temp=ROOT/'prototype_runs'/('news-browser-'+uuid4().hex[:8]);temp.mkdir()
    for source,dest in [('seraph.sqlite','runs.sqlite'),('news-intelligence-pilot.sqlite','news.sqlite')]:
        with closing(sqlite3.connect((ROOT/'prototype_runs'/source).resolve().as_uri()+'?mode=ro',uri=True)) as src:
            with closing(sqlite3.connect(temp/dest)) as dst:src.backup(dst)
    env=dict(os.environ,SERAPH_PROTOTYPE_STORE=str(temp/'runs.sqlite'),SERAPH_NEWS_STORE=str(temp/'news.sqlite'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
    app_port,debug_port=free_port(),free_port()
    processes=[]
    with (OUT/'browser-app.log').open('w',encoding='utf-8') as log:
      try:
        processes.append(subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'seraph/dashboard/prototype_app.py'),'--server.address=127.0.0.1',f'--server.port={app_port}','--server.headless=true','--browser.gatherUsageStats=false'],cwd=ROOT,env=env,stdout=log,stderr=log))
        await_http(f'http://127.0.0.1:{app_port}/_stcore/health')
        edge=Path(os.environ['ProgramFiles(x86)'])/'Microsoft/Edge/Application/msedge.exe'
        processes.append(subprocess.Popen([str(edge),'--headless=new','--no-first-run','--disable-background-networking','--enable-unsafe-swiftshader','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',f'--user-data-dir={temp / "edge"}',f'--remote-debugging-port={debug_port}','--window-size=1800,1400','about:blank'],stdout=log,stderr=log))
        pages=json.loads(await_http(f'http://127.0.0.1:{debug_port}/json/list'))
        with connect(next(p for p in pages if p['type']=='page')['webSocketDebuggerUrl'],max_size=20_000_000) as ws:
            cdp=CDP(ws);cdp.call('Page.enable');cdp.call('Runtime.enable')
            cdp.call('Page.navigate',url=f'http://127.0.0.1:{app_port}')
            context=cdp.component()
            expression="""JSON.parse(JSON.stringify({banner:document.querySelector('#preview-banner').textContent,
                plan:window.SERAPH_GLOBE_API.plan(), signals:document.querySelector('#signals').textContent,
                request:document.querySelector('#req-status-global')?.textContent,
                markerCount:document.querySelectorAll('[data-news-node]').length}))"""
            initial=cdp.evaluate(expression,context)
            assert initial['plan']['markers'],initial
            assert 'current_news' in initial['banner'] and 'MARKET' in initial['banner']
            cdp.evaluate("document.querySelector('nav a[data-view=map]').click()",context)
            cdp.evaluate("document.querySelector('[data-news-node]').click()",context)
            evidence=cdp.evaluate("({text:document.querySelector('#dbody').textContent,links:[...document.querySelectorAll('#dbody a')].map(a=>a.href)})",context)
            assert evidence['links'],evidence
            screenshot=cdp.call('Page.captureScreenshot',format='png')
            (OUT/'ordinary-flow.png').write_bytes(base64.b64decode(screenshot['data']))
            # No payload injection: wait for the real component timer's backend rerun.
            time.sleep(33)
            refreshed=cdp.evaluate(expression,context)
            assert refreshed['plan']['asOf']!=initial['plan']['asOf']
            assert 'NO RESPONSE' not in (refreshed.get('request') or '')
            with closing(sqlite3.connect(temp/'news.sqlite')) as db:
                count=db.execute('SELECT COUNT(*) FROM news_snapshots').fetchone()[0]
            result=dict(initial=initial,refreshed=refreshed,clicked_evidence=evidence,persisted_snapshots=count,
                        ordinary_streamlit_flow=True,payload_injection=False,isolated_store=str(temp/'news.sqlite'))
            (OUT/'ordinary-flow.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(dict(markers=initial['markerCount'],arcs=len(initial['plan']['arcs']),links=len(evidence['links']),auto_refresh=True,snapshots=count)))
      finally:
        for p in reversed(processes):
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=log,stderr=log,check=False)
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill()
if __name__=='__main__':main()
