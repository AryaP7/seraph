"""C12: bind the original globe design to a single persisted run (FR39-42)."""
import json
from pathlib import Path

ASSETS = Path(__file__).parent / 'assets'


def build_frontend(point, manifest, points, report=None):
    """Render data only from this run and history no later than the decision."""
    run = point['run_id']
    if any(p['run_id'] != run for p in points):
        raise ValueError('Cannot mix runs in the frontend')
    payload = dict(point=point, manifest=manifest,
                   history=[dict(date=p['date'], composite=p['composite'])
                            for p in points if p['date'] <= point['date']],
                   report=report)
    encoded = json.dumps(payload, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (ASSETS/'connected.html').read_text(encoding='utf-8')
    return template.replace('/*STYLE*/', (ASSETS/'connected.css').read_text(encoding='utf-8')).replace(
        '/*PAYLOAD*/', encoded).replace('/*THREE*/', (ASSETS/'three.r128.min.js').read_text(encoding='utf-8')).replace(
        '/*CORE*/', (ASSETS/'globe_core.js').read_text(encoding='utf-8')).replace(
        '/*GEOMETRY*/', (ASSETS/'globe_geometry.js').read_text(encoding='utf-8')).replace(
        '/*APP*/', (ASSETS/'connected.js').read_text(encoding='utf-8'))
