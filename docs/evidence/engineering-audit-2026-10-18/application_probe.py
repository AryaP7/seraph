"""Bounded application/deployment checks; disposable writes, read-only DB census."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
result = {}

from seraph.live.feed import ReplayFeed, resolve_feed
replay = ReplayFeed([], label='audit')
with patch.dict(os.environ, {'KITE_API_KEY': 'audit-placeholder-never-connected'}):
    selected = resolve_feed(allow_replay=replay)
    result['explicit_replay_with_credentials'] = {
        'selected': type(selected).__name__, 'is_live': selected.is_live,
        'network_connected': False}

result['installed_packages'] = {name: importlib.util.find_spec(name) is not None
                                for name in ('kiteconnect', 'pypdf', 'setuptools')}
result['ports'] = {}
for port in (5433, 5434, 5435):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2):
            result['ports'][str(port)] = 'accepting'
    except OSError:
        result['ports'][str(port)] = 'not accepting'

async def research_census():
    import asyncpg
    from seraph.store.bootstrap import resolve_dsn
    from urllib.parse import urlparse
    dsn = resolve_dsn()
    parsed = urlparse(dsn)
    if parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        return {'not_inspected': 'nonlocal configured database'}
    conn = await asyncpg.connect(dsn, timeout=3)
    try:
        async with conn.transaction(readonly=True):
            tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            names = {r['table_name'] for r in tables}
            counts = {}
            for name in ('daily_prices', 'intraday_bars', 'universe_membership', 'macro_covariates', 'validation_results'):
                counts[name] = await conn.fetchval('SELECT count(*) FROM '+name) if name in names else 'absent'
            return {'database': await conn.fetchval('SELECT current_database()'),
                    'public_tables': sorted(names), 'counts': counts, 'read_only': True}
    finally:
        await conn.close()
try:
    result['database'] = asyncio.run(research_census())
except Exception as exc:
    result['database'] = {'error_type': type(exc).__name__}

from seraph.live.store import LiveStore
from streamlit.testing.v1 import AppTest
with tempfile.TemporaryDirectory(prefix='app-probe-', dir=OUT) as temp:
    area = Path(temp)
    live = LiveStore(area/'live.sqlite')
    live.commit_decision(decision_id='audit', as_of='2026-10-18T10:00:00+05:30',
        computed_at='2026-10-18T10:00:01+05:30', payload={'csrs': {'csrs': .4}},
        publication_state='current', state={})
    with patch.dict(os.environ, {'SERAPH_PROTOTYPE_STORE': str(area/'absent.sqlite'),
                                'SERAPH_LIVE_STORE': str(area/'live.sqlite')}):
        app = AppTest.from_file(str(ROOT/'seraph/dashboard/prototype_app.py')).run(timeout=30)
        result['live_only_canonical_app'] = {
            'info': [e.value for e in app.info],
            'metrics': len(app.metric), 'radios': len(app.radio),
            'exceptions': [e.value for e in app.exception]}
    source = "from pathlib import Path\nfrom seraph.dashboard.prototype_app import live_panel\nlive_panel(Path("+repr(str(area/'live.sqlite'))+"))\n"
    panel = AppTest.from_string(source).run(timeout=30)
    result['persisted_nested_csrs_panel'] = {'exceptions': [e.value for e in panel.exception]}

(OUT/'application.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
