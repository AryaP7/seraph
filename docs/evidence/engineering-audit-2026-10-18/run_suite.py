"""Run the engineering audit suite; only opt into an existing guarded test DB."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


async def test_database(env):
    import asyncpg
    dsn = env.get('SERAPH_TEST_DB_DSN') or 'postgresql://seraph_test:seraph_test@127.0.0.1:5435/seraph_test_local'
    parsed = urlparse(dsn)
    if parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or not parsed.path.lstrip('/').startswith('seraph_test_'):
        raise ValueError('audit refuses nonlocal or non-test database')
    conn = await asyncpg.connect(dsn, timeout=3)
    try:
        async with conn.transaction(readonly=True):
            actual = await conn.fetchval('SELECT current_database()')
            if actual != parsed.path.lstrip('/'):
                raise ValueError('database identity mismatch')
            token = env.get('SERAPH_TEST_TOKEN') or await conn.fetchval('SELECT token FROM seraph_test_guard LIMIT 1')
            if not token or not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM seraph_test_guard WHERE token=$1)', token):
                raise ValueError('guard token missing')
        env['SERAPH_TEST_DB_DSN'] = dsn
        env['SERAPH_TEST_TOKEN'] = token
        return {'enabled': True, 'database': actual, 'port': parsed.port}
    finally:
        await conn.close()


if __name__ == '__main__':
    env = dict(os.environ, PYTHONIOENCODING='utf-8', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    try:
        database = asyncio.run(test_database(env))
    except Exception as exc:
        database = {'enabled': False, 'reason_type': type(exc).__name__}
        env.pop('SERAPH_TEST_DB_DSN', None)
        env.pop('SERAPH_TEST_TOKEN', None)
    (OUT/'suite-environment.json').write_text(json.dumps(database, indent=2), encoding='utf-8')
    print(json.dumps(database), flush=True)
    with (OUT/'full-suite.log').open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-q',
                                 '--junitxml='+str(OUT/'full-suite.xml')],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    print(json.dumps({'exit_code': result.returncode, 'log': str(OUT/'full-suite.log')}), flush=True)
    sys.exit(result.returncode)
