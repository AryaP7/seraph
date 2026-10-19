"""NI10/NI12 — curate NTPC's first-party station table, never infer coordinates.

Append only missing identities. Store structured facts and a source hash, not
the entire copyrighted webpage. Commissioned MW is capacity, NOT loss exposure.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seraph.news.enrichment import extract_article
from seraph.news.acquisition import _now

URL = 'https://ntpc.co.in/power-generation/coal-stations'
DIRECTORY = ROOT/'seraph/news/curated'


def append_new(filename, key, additions):
    path = DIRECTORY/filename
    original = path.read_text(encoding='utf-8')
    reader = csv.DictReader(line for line in original.splitlines() if not line.startswith('#'))
    existing = {r[key] for r in reader}
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator='\n')
    count = 0
    for row in additions:
        if row[key] not in existing:
            writer.writerow(row)
            existing.add(row[key])
            count += 1
    if count:
        with path.open('a', encoding='utf-8', newline='') as handle:
            if not original.endswith('\n'):
                handle.write('\n')
            handle.write(output.getvalue())
    return count


def main():
    with urllib.request.urlopen(URL, timeout=20) as response:
        raw = response.read(2_000_000)
        text, truncated = extract_article(raw, response.headers.get('Content-Type', ''))
    table = text.split('Joint Ventures/ Subsidiaries:')[0]
    rows = []
    for line in table.splitlines():
        cells = [c.strip() for c in line.split('|') if c.strip()]
        if len(cells) == 4 and re.fullmatch(r'\d+\.?', cells[0]):
            name, state, capacity = cells[1:]
            rows.append((name, state, float(capacity.replace(',', ''))))
    if len(rows) < 20 or truncated:
        raise SystemExit('Station table could not be verified; no curation written')
    now = _now()
    slug = lambda s: re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
    places, assets, edges = [], [], []
    for name, state, capacity in rows:
        place = 'ntpc_state_' + slug(state)
        asset = 'ntpc_' + slug(name)
        places.append(dict(place_id=place, name=state, kind='state', parent_id='in',
                           source_ref=URL, known_from=now))
        assets.append(dict(asset_id=asset, name=name, kind='power_station', place_id=place,
                           owner_entity_id='ntpc', operator_entity_id='ntpc', capacity=capacity,
                           capacity_unit='MW', status='unknown', source_ref=URL, known_from=now))
        for target, mechanism, role in [('ntpc', 'ownership', 'operator'),
                                        ('sector:energy', 'operation', 'domestic_producer')]:
            edges.append(dict(edge_id=asset+'_'+slug(target), from_id=asset, to_id=target,
                               mechanism=mechanism, confidence='high', source_ref=URL,
                               known_from=now, registry_version='official-stations-2026-10-18',
                               event_types='production_halt|facility_incident|capacity_expansion',
                               target_role=role, note='NTPC owned coal station. State-level location only; '
                               'exact facility coordinates unverified. Commissioned MW is nameplate '
                               'capacity, not operating output or financial loss. Sector route is '
                               'qualitative energy production exposure; no revenue share inferred.'))
    counts = dict(
        entities=append_new('entities.csv', 'entity_id', [dict(entity_id='ntpc', name='NTPC Limited',
            kind='issuer', sector='energy', aliases='NTPC', source_ref=URL, known_from=now)]),
        places=append_new('places.csv', 'place_id', places),
        assets=append_new('assets.csv', 'asset_id', assets),
        edges=append_new('exposure.csv', 'edge_id', edges))
    evidence = dict(source=URL, fetched_at=now, source_hash=hashlib.sha256(raw).hexdigest(),
                    rows=[dict(name=n, state=s, commissioned_capacity_mw=c) for n,s,c in rows],
                    added=counts, coordinate_precision='state only; no exact facility pins',
                    note='Ownership and sector participation are distinct relationships; '
                         'event/target aggregation must deduplicate overlapping paths. '
                         'This expands energy coverage, not foreign supply-chain coverage.')
    path = ROOT/'docs/evidence/news-intelligence/ntpc-facility-curation.json'
    if path.exists():
        path = path.with_name('ntpc-facility-curation-'+slug(now)+'.json')
    path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
