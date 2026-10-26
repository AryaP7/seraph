"""C12 — F01/F03/F04/F09/F10 acceptance through the canonical browser UI.

Uses copies of actual stores and explicit demo holdings. Never injects a payload
or writes directly to workflow stores. Evidence and isolated stores are retained.
"""
from contextlib import closing
import argparse
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from audit_console_browser import CDP, await_http, free_port
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]


class RecordingSocket:
    def __init__(self, socket, report):
        self.socket, self.report = socket, report
        report['javascript_exceptions'] = []

    def send(self, value):
        return self.socket.send(value)

    def recv(self, **kwargs):
        value = self.socket.recv(**kwargs)
        message = json.loads(value)
        if message.get('method') == 'Runtime.exceptionThrown':
            self.report['javascript_exceptions'].append(message['params']['exceptionDetails'])
        return value


class Browser:
    def __init__(self, cdp):
        self.cdp = cdp

    def component(self, timeout=120):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                return self.cdp.component()
            except RuntimeError as exc:
                if 'did not render a run' not in str(exc):
                    raise
        raise RuntimeError('Canonical component did not render a run before the browser deadline')

    def evaluate(self, js, component=False):
        # Streamlit may recreate the iframe on a native widget rerun. Resolve
        # its context each time, rather than treating an old ID as permanent.
        if component:
            return self.cdp.evaluate(js, self.component())
        frame = self.cdp.call('Page.getFrameTree')['frameTree']['frame']['id']
        contexts = [k for k,v in self.cdp.contexts.items()
                    if v.get('auxData',{}).get('frameId') == frame
                    and v.get('auxData',{}).get('isDefault')]
        if not contexts:
            raise RuntimeError('Top-level execution context not ready')
        return self.cdp.evaluate(js, contexts[-1])

    def wait(self, js, component=False, timeout=120):
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            try:
                last = self.evaluate(f'!!document.body && ({js})', component)
                if last:
                    return last
            except RuntimeError as exc:
                if 'context' not in str(exc).lower():
                    raise
            time.sleep(.3)
        self.failure_context = self.text()
        raise AssertionError(f'Browser condition not met: {js}; last={last}')

    def click(self, text, *, tag='button,[role=tab]'):
        print('Click', text, flush=True)
        target = f"[...document.querySelectorAll({json.dumps(tag)})].find(n=>n.textContent.trim()==={json.dumps(text)})"
        self.wait(f'!!({target}) && !({target}).disabled && ({target}).getClientRects().length > 0', timeout=90)
        self.evaluate(f"(()=>{{let n={target}; n.scrollIntoView(); n.click();}})()")
        time.sleep(.8)

    def expand(self, text):
        self.evaluate("(()=>{const s=[...document.querySelectorAll('summary')].find(n=>n.textContent.includes("+json.dumps(text)+")); if(s&&!s.parentElement.open)s.click();})()")

    def fill(self, label, value):
        print('Fill', label, flush=True)
        js = """(()=>{const l=[...document.querySelectorAll('label')].find(n=>n.textContent.trim()===LABEL);
          if(!l)throw Error('No label '+LABEL); const e=document.getElementById(l.htmlFor)||l.parentElement.querySelector('input,textarea');
          if(!e)throw Error('No input '+LABEL); e.scrollIntoView(); e.focus(); e.select();})()"""
        self.evaluate(js.replace('LABEL', json.dumps(label)))
        self.cdp.call('Input.insertText', text=value)
        self.cdp.call('Input.dispatchKeyEvent',type='keyDown',key='Tab',code='Tab',windowsVirtualKeyCode=9)
        self.cdp.call('Input.dispatchKeyEvent',type='keyUp',key='Tab',code='Tab',windowsVirtualKeyCode=9)
        time.sleep(2)
        print('Input values', self.evaluate("[...document.querySelectorAll('input')].filter(n=>n.value.includes('Closeout')||n.value.includes('Hypothetical')).map(n=>({value:n.value,disabled:n.disabled}))"), flush=True)

    def role(self, role):
        print('Role', role, flush=True)
        self.evaluate(f"document.querySelector('#roles button[data-role={role}]').click()", True)
        self.wait(f"document.querySelector('#roles button.on')?.dataset.role === '{role}'", True)
        self.wait(f"document.body.innerText.includes('role {role}')")
        time.sleep(2)

    def text(self):
        return self.evaluate('document.body.innerText')

    def upload(self, label, path):
        self.wait("[...document.querySelectorAll('[data-testid=stFileUploader]')].some(n=>n.textContent.includes("+json.dumps(label)+") && n.querySelector('input[type=file]'))")
        self.evaluate("(()=>{const l=[...document.querySelectorAll('[data-testid=stFileUploader]')].find(n=>n.textContent.includes("+json.dumps(label)+")); if(!l)throw Error('Uploader absent'); window.__seraphUploadTarget=l.querySelector('input[type=file]');})()")
        node=self.cdp.call('Runtime.evaluate',expression='window.__seraphUploadTarget')['result']['objectId']
        self.cdp.call('DOM.setFileInputFiles',files=[str(path.resolve())],objectId=node)

    def select(self, label, option):
        print('Select',label,option,flush=True)
        self.wait("(()=>{const l=[...document.querySelectorAll('label')].find(n=>n.textContent.trim()==="+json.dumps(label)+"); const e=l&&(document.getElementById(l.htmlFor)||l.parentElement.querySelector('[role=combobox]')); return e&&!e.disabled&&e.getClientRects().length;})()")
        self.evaluate("(()=>{const l=[...document.querySelectorAll('label')].find(n=>n.textContent.trim()==="+json.dumps(label)+"); const e=document.getElementById(l.htmlFor)||l.parentElement.querySelector('[role=combobox]'); e.scrollIntoView(); e.click();})()")
        target="[...document.querySelectorAll('[role=option]')].find(n=>n.textContent.includes("+json.dumps(option)+"))"
        self.wait(f'!!({target})')
        self.evaluate(f'({target}).click()')

    def historical(self):
        self.click('historical_decision',tag='label')
        self.wait("document.body.innerText.includes('News: historical_decision')")

    def check(self, label):
        target = "[...document.querySelectorAll('[data-testid=stCheckbox]')].find(n=>n.textContent.trim()==="+json.dumps(label)+").querySelector('input')"
        self.wait(f'!!({target})')
        self.evaluate(f'(()=>{{const e={target}; if(!e.checked)e.click();}})()')
        self.wait(f'({target}).checked')
        time.sleep(2)

    def reload(self, role):
        self.cdp.call('Page.reload')
        self.wait("document.body.innerText.includes('Historical decision date')",timeout=120)
        self.component()
        self.role(role)
        self.historical()


def macro_workflow(b, report, out, downloads):
    """One real fitted policy artifact, with explicit hypothetical paths."""
    candidates=[]
    for path in (ROOT/'prototype_runs/hamilton_projection').glob('*.json'):
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema')=='hamilton-projection/1' and any(
                c['name']=='rbi_repo_rate' for c in value['covariates']):
            candidates.append((path,value))
    assert candidates,'No actual fitted policy artifact'
    path,artifact=sorted(candidates,key=lambda item:item[1]['fitted_at'])[-1]
    b.role('institutional'); b.historical()
    b.expand('MY WORKSPACE'); b.click('SCENARIOS')
    b.expand('Save a fitted macro-path scenario')
    b.upload('Projection artifact JSON',path)
    b.wait("document.body.innerText.includes('Training ends '+"+json.dumps(artifact['training_end'])+")")
    sessions=['2026-07-24','2026-07-27','2026-07-28']
    baseline=[dict(session=d,rbi_repo_rate=5.25) for d in sessions]
    scenario=[dict(session=d,rbi_repo_rate=5.5) for d in sessions]
    b.fill('Baseline covariate path JSON',json.dumps(baseline))
    b.fill('Hypothetical covariate path JSON',json.dumps(scenario))
    b.fill('Macro scenario name','Closeout repo-rate path +25bp')
    b.fill('Macro assumptions and justification','Explicit hypothetical +25bp repo path versus 5.25%; retrospective fit, no causal-policy effectiveness claim.')
    b.check('Explicit retrospective hypothetical: permit a fit newer than the market baseline')
    b.click('Save macro scenario')
    b.wait("[...document.querySelectorAll('button')].some(n=>n.textContent.trim()==='Run')")
    b.click('Run')
    b.wait('document.body.innerText.includes('+json.dumps('Fitted artifact '+artifact['artifact_id'])+')')
    report['macro_result_visible']=b.text()
    b.click('Export')
    time.sleep(2)
    b.reload('institutional'); b.expand('MY WORKSPACE'); b.click('SCENARIOS')
    b.wait('document.body.innerText.includes('+json.dumps('Fitted artifact '+artifact['artifact_id'])+')')
    report['macro_reopened']=True
    b.click('History'); b.click('Export')
    time.sleep(2)
    report['downloads']={p.name:json.loads(p.read_text(encoding='utf-8')) for p in downloads.glob('*.json')}
    report['artifact_id']=artifact['artifact_id']
    assert report['downloads'],'Export did not download'
    exported=next(iter(report['downloads'].values()))
    assert exported['scenario']['kind']=='macro_path'
    step=exported['scenario']['steps'][0]
    assert step['path']==scenario and step['baseline_path']==baseline
    assert step['analysis_mode']=='retrospective_hypothetical'
    assert step['artifact']['artifact_id']==artifact['artifact_id']
    result=exported['runs'][-1]['results'][0]
    import numpy as np
    from seraph.pillars.hamilton.projection import project
    np.testing.assert_allclose(result['xi_path'],project(artifact,scenario),atol=1e-13)
    np.testing.assert_allclose(result['baseline_xi_path'],project(artifact,baseline),atol=1e-13)
    np.testing.assert_allclose(np.sum(result['xi_path'],axis=1),1.,atol=1e-13)
    report['maximum_regime_probability_change']=float(np.max(np.abs(
        np.asarray(result['xi_path'])-np.asarray(result['baseline_xi_path']))))
    report['score_change']=[a['csrs']-z['csrs'] for a,z in zip(result['score_path'],result['baseline_score_path'])]
    report['baseline_consistency_verified']=True
    report['javascript_exceptions']=report.get('javascript_exceptions',[])
    assert not report['javascript_exceptions'],report['javascript_exceptions']
    report['passed']=True
    shot=b.cdp.call('Page.captureScreenshot',format='png')
    (out/'macro.png').write_bytes(base64.b64decode(shot['data']))


def institution_read_workflow(b,report,out,downloads):
    b.role('regulator'); b.historical(); b.expand('INSTITUTION EXPOSURES')
    b.wait("document.body.innerText.includes('Demonstration B')")
    report['institutions_reopened']=b.text()
    b.evaluate("document.querySelector('nav a[data-view=tools]').click()",True)
    b.wait("document.querySelector('#extra-content')?.textContent.includes('Demonstration B')",True)
    report['regulator_console']=b.evaluate("document.querySelector('#extra-content').textContent",True)
    assert 'Demonstration A' in report['regulator_console']
    b.click('Export institution decomposition'); time.sleep(2)
    report['downloads']={p.name:json.loads(p.read_text(encoding='utf-8')) for p in downloads.glob('*.json')}
    result=next(v for v in report['downloads'].values() if v.get('schema')=='institution-decomposition/1')
    assert result['total_known_value']==3000 and len(result['institutions'])==2
    assert sum(x['value'] for x in result['sectors'])==3000
    b.role('retail')
    assert 'INSTITUTION EXPOSURES' not in b.text()
    report['restricted_form_absent']=True
    assert not report['javascript_exceptions'],report['javascript_exceptions']
    report['passed']=True


def portfolio_workflow(b,report,out,downloads):
    b.role('retail'); b.historical(); b.expand('MY WORKSPACE'); b.click('PORTFOLIOS')
    b.fill('New portfolio name','Closeout retail holdings')
    b.click('Create portfolio')
    b.wait("[...document.querySelectorAll('button')].some(n=>n.textContent.trim()==='Save snapshot')")
    holdings=out.resolve()/'demo-holdings.csv'
    holdings.write_text('symbol,quantity,value,sector\nTATASTEEL,10,1000,steel\nINFY,20,2000,technology\n',encoding='utf-8')
    b.upload('Upload holdings (CSV or JSON)',holdings)
    b.wait("document.body.innerText.includes('2 accepted')")
    b.fill('Effective at (IST)','2020-02-01T09:00:00+05:30')
    b.click('Save snapshot')
    b.wait("document.body.innerText.includes('Saved. It will still be here after a restart.')")
    b.click('Use this portfolio')
    b.wait("document.body.innerText.includes('Active saved portfolio:')")
    report['portfolio_active']=b.text()
    b.evaluate("document.querySelector('nav a[data-view=console]').click()",True)
    b.wait("document.querySelector('#role-news-home')?.textContent.includes('TATASTEEL')",True)
    report['portfolio_news']=b.evaluate("document.querySelector('#role-news-home')?.textContent",True)
    b.evaluate("document.querySelector('nav a[data-view=exposure]').click()",True)
    b.wait("document.querySelector('#extra-content')?.textContent.includes('3000')",True)
    report['portfolio_overlay']=b.evaluate("document.querySelector('#extra-content')?.textContent",True)
    assert '3000' in report['portfolio_overlay'].replace(',','')
    assert 'TATASTEEL' in report['portfolio_news'] and 'INFY' in report['portfolio_news']
    b.reload('retail'); b.expand('MY WORKSPACE'); b.click('PORTFOLIOS')
    b.wait("[...document.querySelectorAll('button')].some(n=>n.textContent.trim()==='Use this portfolio')")
    b.click('Use this portfolio')
    b.wait("document.body.innerText.includes('Active saved portfolio:')")
    report['portfolio_reopened']=True
    assert not report['javascript_exceptions'],report['javascript_exceptions']
    report['passed']=True


def console_workflow(b,report,out,downloads):
    report['roles']={}
    for role in ('retail','institutional','regulator'):
        b.role(role)
        report['roles'][role]=b.evaluate("({role:document.querySelector('#roles button.on')?.dataset.role,banner:document.querySelector('#preview-banner')?.textContent,news:document.querySelector('#role-news-home')?.textContent,canvas:!!document.querySelector('canvas')})",True)
        assert report['roles'][role]['canvas']
        assert 'RUN ' in report['roles'][role]['banner']
    b.evaluate("document.querySelector('nav a[data-view=console]').click()",True)
    report['console']=b.evaluate("document.querySelector('#viewConsole').textContent",True)
    assert 'failed to render' not in report['console']
    b.evaluate("document.querySelector('.cta').click()",True)
    report['backtest']=b.evaluate("document.querySelector('#extra-content').textContent",True)
    assert 'NIFTY' in report['backtest'].upper()
    b.evaluate("document.querySelector('nav a[data-view=tools]').click()",True)
    report['flow_tools']=b.evaluate("document.querySelector('#extra-content').textContent",True)
    assert 'flow' in report['flow_tools'].lower()
    b.evaluate("document.querySelector('nav a[data-view=map]').click()",True)
    b.evaluate("[...document.querySelectorAll('iframe')].find(n=>n.title?.includes('seraph_console'))?.scrollIntoView({block:'center'})")
    time.sleep(2)
    shot=b.cdp.call('Page.captureScreenshot',format='png')
    (out/'canonical-globe.png').write_bytes(base64.b64decode(shot['data']))
    assert not report['javascript_exceptions'],report['javascript_exceptions']
    report['passed']=True


def evaluation_workflow(b, report, out, downloads):
    b.role('institutional'); b.historical()
    b.expand('EVALUATION')
    from seraph.dashboard.console_backend import experiment_surface
    surface = experiment_surface(role='institutional')
    item = next(r for r in surface['reports'] if r['name']=='2026-10-21-registered-real.json')
    b.wait('document.body.innerText.includes('+json.dumps('artefact '+item['artefact_id'][:16])+')')
    b.wait("document.body.innerText.includes('Table C') && document.body.innerText.includes('insufficient_training_sample')")
    report['evaluation_visible'] = b.text()
    assert item['intact'] and item['measured']==0 and item['unavailable']==152
    assert set(c['table'] for c in item['configurations'])=={'A','B','C'}
    report['report_identity']=item['artefact_id']
    report['measured_cells']=item['measured']; report['unavailable_cells']=item['unavailable']
    assert not report['javascript_exceptions'], report['javascript_exceptions']
    report['passed']=True


def sector_workflow(b, report, out, downloads):
    if report['resumed_workspace']:
        b.role('retail'); b.historical(); b.expand('MY WORKSPACE'); b.click('PORTFOLIOS')
        b.click('Use this portfolio')
        b.wait("document.body.innerText.includes('Active saved portfolio:')")
    else:
        portfolio_workflow(b, report, out, downloads)
    report['passed']=False
    b.expand('MEASURED SECTOR ACTIVITY')
    b.wait("document.body.innerText.includes('No measured sector observation set was available at this decision')")
    b.click('Retrospective analytical archive', tag='label')
    b.wait("document.body.innerText.includes('Sector observations end 2020-04-30')")
    # A native rerun can replace the iframe after its early captions arrive.
    # Navigate the current iframe until the measured holdings arrive there.
    b.wait("(()=>{document.querySelector('nav a[data-view=exposure]').click(); return document.querySelector('#extra-content')?.textContent.includes('33.333');})()",True)
    report['measured_portfolio_overlay']=b.evaluate("document.querySelector('#extra-content').textContent",True)
    report['sector_archive_visible']=b.text()
    assert 'Retrospective measured sector activity' in report['sector_archive_visible']
    b.click('Selected market decision',tag='label')
    b.wait("document.body.innerText.includes('Only sector artifacts available by the selected market decision')")
    b.wait("(()=>{document.querySelector('nav a[data-view=exposure]').click(); return document.querySelector('#extra-content')?.textContent.includes('\"coveredPct\": 0');})()",True)
    report['decision_time_coverage_restored']=True
    assert not report['javascript_exceptions'],report['javascript_exceptions']
    report['passed']=True


def main(out, resume_workspace=None, workflow='all'):
    out.mkdir(parents=True, exist_ok=False)
    temp = out.resolve()/'isolated'
    temp.mkdir()
    for name, target in [('seraph.sqlite','runs.sqlite'), ('news-intelligence-pilot.sqlite','news.sqlite'), ('live.sqlite','live.sqlite')]:
        with closing(sqlite3.connect((ROOT/'prototype_runs'/name).resolve().as_uri()+'?mode=ro',uri=True)) as source:
            with closing(sqlite3.connect(temp/target)) as dest:
                source.backup(dest)
    if resume_workspace:
        (temp/'workspace').mkdir()
        for source_path in resume_workspace.glob('*.sqlite'):
            with closing(sqlite3.connect(source_path.resolve().as_uri()+'?mode=ro',uri=True)) as source:
                with closing(sqlite3.connect(temp/'workspace'/source_path.name)) as dest:
                    source.backup(dest)
    env = dict(os.environ, SERAPH_PROTOTYPE_STORE=str(temp/'runs.sqlite'),
        SERAPH_NEWS_STORE=str(temp/'news.sqlite'), SERAPH_LIVE_STORE=str(temp/'live.sqlite'),
        SERAPH_WORKSPACE_DIR=str(temp/'workspace'), SERAPH_NEWS_WORKER='0',
        OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', PYTHONIOENCODING='utf-8')
    port, debug = free_port(), free_port()
    processes, report = [], {'mode':'actual archived prices; explicit demo submissions; hypothetical actions',
        'resumed_workspace':str(resume_workspace) if resume_workspace else None}
    def checkpoint():
        (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with (out/'browser.log').open('w',encoding='utf-8') as log:
        try:
            app = subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'seraph/dashboard/prototype_app.py'),
                '--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true','--browser.gatherUsageStats=false'],
                cwd=ROOT,env=env,stdout=log,stderr=log)
            processes.append(app)
            await_http(f'http://127.0.0.1:{port}/_stcore/health',timeout=90)
            edge = Path(os.environ['ProgramFiles(x86)'])/'Microsoft/Edge/Application/msedge.exe'
            processes.append(subprocess.Popen([str(edge),'--headless=new','--no-first-run','--disable-background-networking',
                '--enable-unsafe-swiftshader','--no-default-browser-check',
                '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',f'--user-data-dir={temp/"edge"}',f'--remote-debugging-port={debug}',
                '--window-size=1800,1400','about:blank'],stdout=log,stderr=log))
            pages = json.loads(await_http(f'http://127.0.0.1:{debug}/json/list'))
            endpoint = next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page' and p.get('url')=='about:blank')
            with connect(endpoint,max_size=20_000_000) as ws:
                cdp=CDP(RecordingSocket(ws,report)); b=Browser(cdp)
                cdp.call('Page.enable'); cdp.call('Runtime.enable')
                downloads=out.resolve()/'downloads'; downloads.mkdir()
                cdp.call('Browser.setDownloadBehavior',behavior='allow',downloadPath=str(downloads))
                cdp.call('Page.navigate',url=f'http://127.0.0.1:{port}')
                b.wait("document.body.innerText.includes('Historical decision date')", timeout=90)
                b.component()
                report['forecast_id_visible']='Forecast ledger ID:' in b.text()
                if workflow!='all':
                    {'macro':macro_workflow,'institutions':institution_read_workflow,
                     'portfolios':portfolio_workflow,'console':console_workflow,
                     'evaluation':evaluation_workflow,'sectors':sector_workflow}[workflow](b,report,out,downloads)
                    checkpoint()
                    return
                report['roles']={}
                for role in ('retail','institutional','regulator'):
                    b.role(role)
                    report['roles'][role]=b.evaluate("({role:document.querySelector('#roles button.on')?.dataset.role,banner:document.querySelector('#preview-banner')?.textContent,news:document.querySelector('#role-news-home')?.textContent,canvas:!!document.querySelector('canvas')})",True)
                b.role('institutional')
                for view in ('backtest','tools'):
                    selector = '.cta' if view == 'backtest' else 'nav a[data-view=tools]'
                    b.evaluate(f"document.querySelector({json.dumps(selector)}).click()",True)
                    report[view]=b.evaluate("document.querySelector('#extra-content')?.textContent",True)
                assert 'NIFTY' in report['backtest'].upper(),report['backtest']
                # This comparison is a historical workflow. Select its actual
                # news-clock control before editing; current-news refreshes
                # are independently exercised above and in the news verifier.
                b.historical()
                b.expand('MY WORKSPACE')
                report['workspace_dom']=b.evaluate("({text:document.body.innerText,buttons:[...document.querySelectorAll('button')].map(n=>n.textContent),summaries:[...document.querySelectorAll('summary')].map(n=>n.outerHTML)})")
                (out/'workspace-dom.json').write_text(json.dumps(report['workspace_dom'],indent=2),encoding='utf-8')
                b.click('SCENARIOS')
                if not resume_workspace:
                    b.expand('Save a defensive action comparison')
                    b.fill('Defensive comparison name','Closeout actual-index cash reduction')
                    b.fill('Defensive assumptions and justification','Hypothetical one-unit index exposure, next observed close, 50% reduction, 10 bps, zero cash return; actual stored COVID prices.')
                    time.sleep(3)
                    b.click('Save defensive comparison')
                b.wait("[...document.querySelectorAll('button')].some(n=>n.textContent.trim()==='Run')")
                b.click('Run')
                b.wait("document.body.innerText.includes('Baseline maximum drawdown:')")
                report['defensive_rendered']=b.text()
                b.click('Export')
                b.click('History')
                report['defensive_history']=b.text()
                checkpoint()
                # Reload the actual application: the saved scenario and execution
                # must survive even though Streamlit session state does not.
                b.reload('institutional')
                b.expand('MY WORKSPACE'); b.click('SCENARIOS')
                b.wait("[...document.querySelectorAll('button')].some(n=>n.textContent.trim()==='Run')")
                b.click('History'); b.click('Export')
                report['scenario_reopened']=True
                checkpoint()
                b.role('regulator'); b.expand('INSTITUTION EXPOSURES')
                for ident, name, body in [('DEMO-A','Demonstration A','symbol,quantity,value,sector\nTATASTEEL,10,1000,steel\n'),
                                          ('DEMO-B','Demonstration B','symbol,quantity,value,sector\nINFY,20,2000,technology\n')]:
                    b.fill('Institution ID',ident); b.fill('Institution display name',name)
                    b.fill('Or paste holdings CSV',body)
                    b.click('Preview institution submission')
                    b.click('Accept institution submission')
                    b.wait("document.body.innerText.includes('Saved revision')")
                    b.wait('document.body.innerText.includes('+json.dumps(name)+')')
                    report['latest_institution_saved']=ident
                    checkpoint()
                # The cutoff is an explicit widget value, so advance it by
                # reloading; no manufactured receive/effective timestamps.
                b.reload('regulator')
                b.expand('INSTITUTION EXPOSURES')
                report['institutions_reopened']=b.text()
                assert all(s in report['institutions_reopened'].replace(',','') for s in ('Demonstration A','Demonstration B','3000'))
                b.click('Export institution decomposition')
                time.sleep(2)
                report['downloads']={p.name:json.loads(p.read_text(encoding='utf-8')) for p in downloads.glob('*.json')}
                assert any(v.get('total_known_value')==3000 for v in report['downloads'].values())
                report['regulator_console']=b.evaluate("document.querySelector('#extra-content')?.textContent",True)
                assert 'Demonstration A' in report['regulator_console'] and 'Demonstration B' in report['regulator_console']
                shot=cdp.call('Page.captureScreenshot',format='png')
                (out/'regulator.png').write_bytes(base64.b64decode(shot['data']))
                b.role('retail')
                report['restricted_form_absent']='INSTITUTION EXPOSURES' not in b.text()
                assert report['restricted_form_absent']
                checkpoint()
                b.expand('MY WORKSPACE'); b.click('PORTFOLIOS')
                b.fill('New portfolio name','Closeout retail holdings')
                b.click('Create portfolio')
                b.wait("[...document.querySelectorAll('button')].some(n=>n.textContent.trim()==='Save snapshot')")
                holdings=out.resolve()/'demo-holdings.csv'
                holdings.write_text('symbol,quantity,value,sector\nTATASTEEL,10,1000,steel\nINFY,20,2000,technology\n',encoding='utf-8')
                b.upload('Upload holdings (CSV or JSON)',holdings)
                b.wait("document.body.innerText.includes('2 accepted')")
                b.fill('Effective at (IST)','2020-02-01T09:00:00+05:30')
                b.click('Save snapshot')
                b.wait("document.body.innerText.includes('Saved. It will still be here after a restart.')")
                b.click('Use this portfolio')
                b.wait("document.body.innerText.includes('Active saved portfolio:')")
                report['portfolio_active']=b.text()
                report['portfolio_news']=b.evaluate("document.querySelector('#role-news-home')?.textContent",True)
                b.evaluate("document.querySelector('nav a[data-view=exposure]').click()",True)
                report['portfolio_overlay']=b.evaluate("document.querySelector('#extra-content')?.textContent",True)
                assert '3000' in report['portfolio_overlay'].replace(',','')
                checkpoint()
                b.reload('retail'); b.expand('MY WORKSPACE'); b.click('PORTFOLIOS')
                b.wait("[...document.querySelectorAll('button')].some(n=>n.textContent.trim()==='Use this portfolio')")
                b.click('Use this portfolio')
                b.wait("document.body.innerText.includes('Active saved portfolio:')")
                report['portfolio_reopened']=True
                assert not report['javascript_exceptions'],report['javascript_exceptions']
                report['passed']=True
                checkpoint()
        except Exception as exc:
            report['error']=str(exc)
            report['failure_context']=getattr(b,'failure_context',None)
            try:
                report['last_page']=b.text()
            except Exception:
                pass
            try:
                report['component_at_failure']=b.evaluate("({text:document.body.innerText,extra:document.querySelector('#extra-content')?.textContent})",True)
            except Exception:
                pass
            try:
                report['frames']=cdp.call('Page.getFrameTree')
                shot=cdp.call('Page.captureScreenshot',format='png')
                (out/'failure.png').write_bytes(base64.b64decode(shot['data']))
            except Exception:
                pass
            raise
        finally:
            checkpoint()
            for process in reversed(processes):
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=log,stderr=log,check=False)
    print(json.dumps({'passed':report.get('passed',False),'evidence':str(out)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--resume-workspace',type=Path,help='Continue the named prior browser store, copied read-only')
    p.add_argument('--workflow',choices=('all','macro','institutions','portfolios','console','evaluation','sectors'),default='all')
    args=p.parse_args()
    main(args.output,args.resume_workspace,args.workflow)
