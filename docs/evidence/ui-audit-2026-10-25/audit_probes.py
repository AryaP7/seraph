"""Audit-only probes. Application code is not changed; writes use a temp workspace."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent


class Buttons(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button' and attrs.get('data-rd-op'):
            self.buttons.append(attrs)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from seraph.dashboard.redesign import component_workspace as W, data
    baseline = ROOT / 'docs/evidence/frontend-baseline-2026-10-24'
    comparisons = []
    for path in sorted((baseline / 'seraph').rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.html', '.js', '.css'):
            rel = path.relative_to(baseline)
            current = ROOT / rel
            comparisons.append(dict(path=rel.as_posix(), baseline=sha(path),
                                    current=sha(current) if current.exists() else None,
                                    equal=current.exists() and sha(path) == sha(current)))
    rel = Path('launch_prototype.ps1')
    comparisons.append(dict(path=str(rel), baseline=sha(baseline / rel),
                            current=sha(ROOT / rel), equal=sha(baseline / rel) == sha(ROOT / rel)))
    result = dict(classic_baseline=comparisons)
    with tempfile.TemporaryDirectory(prefix='seraph-ui-audit-') as temp:
        os.environ['SERAPH_WORKSPACE_DIR'] = temp
        paths = data.store_paths()
        run = data.complete_runs(paths['archive'])[-1]
        point = data.run_bundle(paths['archive'], run['id'], 'retail')['points'][-1]

        def call(op, **args):
            try:
                return data.workspace_call(paths['archive'], run['id'], point['date'],
                                           'retail', op, **args)
            except Exception as exc:
                return dict(error=f'{type(exc).__name__}: {exc}')

        created = call('ws_create', name='Disposable audit probe')
        pid = call('ws_portfolios')['value'][0]['portfolio_id']
        bundle = dict(portfolios=[dict(portfolio_id=pid, name='Audit')],
                      portfolio_id=pid, holdings={}, now_ist='2026-10-26T00:00:00+05:30')
        markup = W._portfolios(bundle)
        parser = Buttons()
        parser.feed(markup)
        result['emitted_upload_buttons'] = parser.buttons[:2]
        csv = 'symbol,qty,price,sector\nRELIANCE,10,2800,energy\n'
        result['preview_as_emitted'] = call('ws_preview', body=csv, source_name='upload')
        result['commit_as_emitted'] = call('ws_commit', body=csv, source_name='upload',
                                          effective_at='2026-10-26T00:00:00+05:30')
        good = call('ws_preview', portfolio_id=pid, body=csv, source_name='audit.csv')
        result['backend_with_required_id'] = dict(error=good.get('error'),
                                                  kind=good.get('kind'), value=good.get('value'))
    result['writes'] = 'Temporary isolated portfolio only; no user portfolio or application source edits.'
    (OUT / 'audit-probes.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
