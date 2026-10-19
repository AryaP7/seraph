"""Build an isolated copy, then exercise its wheel payload without source fallback."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

with tempfile.TemporaryDirectory(prefix='wheel-probe-', dir=OUT) as temp:
    area = Path(temp)
    src = area/'source'
    src.mkdir()
    for name in ('seraph', 'fixtures'):
        shutil.copytree(ROOT/name, src/name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('pyproject.toml', 'README-AI-SETUP.md'):
        shutil.copy2(ROOT/name, src/name)
    build = subprocess.run([sys.executable, '-c',
        'from setuptools.build_meta import build_wheel; build_wheel("dist")'],
        cwd=src, capture_output=True, text=True)
    (OUT/'wheel-build.log').write_text(build.stdout+build.stderr, encoding='utf-8')
    if build.returncode:
        raise RuntimeError('isolated wheel build failed; see wheel-build.log')
    wheel = next((src/'dist').glob('*.whl'))
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        installed = area/'installed'
        z.extractall(installed)
    required = [str(p.relative_to(ROOT)).replace('\\', '/')
                for folder, glob in [('seraph/live/migrations', '*.sql'),
                                     ('seraph/store/migrations', '*.sql'),
                                     ('seraph/news/curated', '*.csv')]
                for p in (ROOT/folder).glob(glob)]
    check = '''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
result = {}
try:
    from seraph.live.store import LiveStore
    store = LiveStore(Path(sys.argv[2])/'scratch.sqlite')
    result['live_head'] = str(store.head())
except Exception as exc:
    result['live_error'] = type(exc).__name__+': '+str(exc)
try:
    from seraph.news.registry import load_master_data
    master, report = load_master_data()
    result['master_report'] = str(report)
except Exception as exc:
    result['master_error'] = type(exc).__name__+': '+str(exc)
try:
    import seraph.orchestration.original_execution
    result['original_execution_import'] = 'ok'
except Exception as exc:
    result['original_execution_error'] = type(exc).__name__+': '+str(exc)
print(json.dumps(result))
'''
    runtime = ROOT/'.venv/Scripts/python.exe'
    def runtime_path(path):
        if sys.platform == 'win32':
            return str(path)
        return subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()
    run = subprocess.run([str(runtime), '-I', '-c', check, runtime_path(installed), runtime_path(area)],
                         cwd=area, capture_output=True, text=True)
    result = {'build_exit': build.returncode, 'wheel': wheel.name,
              'missing_runtime_assets': [n for n in required if n not in names],
              'probe_exit': run.returncode, 'installed_payload_probe': run.stdout.strip(),
              'stderr': run.stderr[-2000:],
              'limitation': 'Uses existing dependency environment; not a fresh dependency installation.'}
    (OUT/'packaging.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
