"""Check saved research integrity, cutoff rules and untouched original files."""
from __future__ import annotations
import hashlib
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(original_root=None):
    out=ROOT/'research_results/v1_verified'
    manifest=json.loads((ROOT/'research_data/manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert sha(ROOT/'research_data'/name)==digest, f'Changed data: {name}'
    provenance=json.loads((out/'provenance.json').read_text())
    for name,digest in provenance['code_hashes'].items():
        assert sha(ROOT/Path(name.replace('\\', '/')))==digest, f'Model code changed since replay: {name}'
    for name,digest in provenance['outputs'].items():
        assert sha(out/name)==digest, f'Changed original output: {name}'
    audit=json.loads((out/'fit_audit.json').read_text())
    fits=0
    for name,rows in audit['prediction'].items():
        if not isinstance(rows,list):
            continue
        for fit in rows:
            assert fit['train_end'] <= fit['fitted_at']-15, name
            fits+=1
    alert_fits=0
    for name,rows in audit['alerts'].items():
        for fit in rows:
            assert fit['calibration_end_exclusive']-1<=fit['decision_index']-15,name
            assert fit['calibration']['alarm_fraction']<=.1+1e-12,name
            assert fit['calibration']['false_episodes_per_year']<=2+1e-12,name
            alert_fits+=1
    for file in ('predictions.parquet','features.parquet'):
        pd.testing.assert_frame_equal(pd.read_parquet(ROOT/'research_results/v1'/file),
                                      pd.read_parquet(out/file),check_exact=True)
    hazard=json.loads((out/'hazard_summary.json').read_text())
    assert sha(ROOT/'research_data/public_health_events.json')==hazard['source_hash']
    assert len(hazard['source_events'])==9
    for event in hazard['source_events']:
        assert event['first_session'] > event['published_date']
        assert event['observed_sessions']==20
    covid=next(e for e in hazard['evaluation']['external']['events'] if e['event']=='covid_2020')
    assert covid['first_warning']=='2020-01-31' and covid['lead_sessions']==14
    original=Path(original_root).resolve() if original_root is not None else None
    source_manifest=json.loads((ROOT/'source_original_manifest.json').read_text())
    missing,changed=[],[]
    for row in source_manifest if original is not None else []:
        path=Path(row['path'].replace('\\', '/'))
        if not path.is_absolute():
            path=original/path
        if not path.exists():
            missing.append(str(path))
        elif sha(path)!=row['sha256'].lower():
            changed.append(str(path))
    assert not missing and not changed, dict(missing=missing,changed=changed)
    result=dict(status='passed',supervised_refits= fits,alert_refits=alert_fits,
                unchanged_original_files=len(source_manifest) if original is not None else None,
                original_preservation_check='passed' if original is not None else 'not_requested',
                exact_replication=['predictions.parquet','features.parquet'],
                data_hashes='verified',code_hashes='verified',output_hashes='verified',
                covid_external_watch=dict(date=covid['first_warning'],lead_sessions=covid['lead_sessions']))
    (out/'integrity_check.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root', type=Path,
                        help='Optional local original checkout to verify; never required for a fresh clone.')
    run(parser.parse_args().original_root)
