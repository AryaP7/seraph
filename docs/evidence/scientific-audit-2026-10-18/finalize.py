"""C10 audit evidence manifest (FR32–38); no model or database changes."""
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
REPORT=ROOT/'docs/SERAPH-SCIENTIFIC-AUDIT-2026-10-18.md'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    test_file=OUT/'tests.xml'
    if not test_file.exists():
        raise SystemExit('Numerical test suite has not produced its final XML yet.')
    tree=ET.parse(test_file)
    suites=tree.findall('.//testsuite')
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites)
            for k in ('tests','failures','errors','skipped')}
    failures=[dict(name=e.attrib.get('name'),classname=e.attrib.get('classname'),
                   message=(e.find('failure').attrib.get('message') if e.find('failure') is not None
                            else e.find('error').attrib.get('message')))
              for e in tree.findall('.//testcase')
              if e.find('failure') is not None or e.find('error') is not None]
    invariants=subprocess.run([sys.executable,'scripts/check_invariants.py'],cwd=ROOT,
                              capture_output=True,text=True,check=False)
    (OUT/'invariant-check.txt').write_text(invariants.stdout+invariants.stderr,encoding='utf-8')
    integrity=json.loads((OUT/'input-integrity.json').read_text())
    roots={'code':ROOT,'artifact':ROOT/'research_results/v1_verified','data':ROOT/'research_data'}
    hashes_match=all(sha(roots[row['kind']]/row['path'].replace('\\','/'))==row['expected']
                     for row in integrity)
    diagnostics=json.loads((OUT/'diagnostics.json').read_text())
    summary=json.loads((OUT/'experiment/summary.json').read_text())
    fit_audit=json.loads((OUT/'experiment/fit-audit.json').read_text())
    cutoff_violations=[]
    for name,record in fit_audit.items():
        for fit in record.get('fits',[]):
            if fit['train_end']+15>fit['fitted_at']:
                cutoff_violations.append(dict(configuration=name,kind='fit',record=fit))
        for fit in record.get('alerts',[]):
            if fit['calibration_end_exclusive']-1+15>fit['decision_index']:
                cutoff_violations.append(dict(configuration=name,kind='alert',record=fit))
    original=pd.read_parquet(ROOT/'research_results/v1_verified/predictions.parquet')
    replicated=pd.read_parquet(OUT/'experiment/predictions.parquet')
    replication=[]
    for target in sorted(replicated.target.unique()):
        for model,old_model in [('baseline','baseline_logit'),('combined','combined')]:
            old=original[(original.target==target)&(original.model==old_model)].sort_values('date')
            new=replicated[(replicated.target==target)&(replicated.model==model)].sort_values('date')
            np.testing.assert_array_equal(old.date.to_numpy(),new.date.to_numpy())
            np.testing.assert_allclose(old.probability,new.probability,rtol=0,atol=1e-12,equal_nan=True)
            replication.append(dict(target=target,model=model,
                max_absolute_difference=float(np.nanmax(np.abs(old.probability.to_numpy()-new.probability.to_numpy())))))
    assert hashes_match,'Original research inputs changed since the audit.'
    assert invariants.returncode==0,invariants.stdout+invariants.stderr
    assert not cutoff_violations,cutoff_violations
    verification=dict(
        created_at=datetime.now(timezone(timedelta(hours=5,minutes=30))).isoformat(),
        numerical_tests=dict(**counts,passed=counts['tests']-counts['failures']-counts['errors']-counts['skipped'],
                             duration_seconds=sum(float(s.attrib.get('time',0)) for s in suites),
                             failures_detail=failures,report='tests.xml'),
        invariant_checker=dict(command='.venv/Scripts/python.exe scripts/check_invariants.py',
            exit_code=invariants.returncode,output='invariant-check.txt',checks=['PILLAR_ORDER consistency','C9 purity','AR_t placement',
                                'Explicit IST timestamps','shared_types frozen audit (informational)']),
        audit=dict(original_research_hashes_match=hashes_match,
            baseline_and_combined_replication_absolute_tolerance=1e-12,
            probability_replication=replication,
            recorded_mature_label_cutoff_violations=len(diagnostics['stored_cutoff_violations']),
            experiment_mature_label_cutoff_violations=len(cutoff_violations),
            mathematical_counterexamples='diagnostics.json and supplement.json',
            forecast_configurations=len(summary),
            supervised_configurations=sum(row['model']!='climatology' for row in summary),
            no_predictive_success_claim=True),
        environment=dict(python=sys.version,libraries={name:importlib.metadata.version(name)
            for name in ('numpy','scipy','pandas','statsmodels','pyarrow','pytest')}),
        scope='Targeted numerical/causality tests, not the full repository suite. No database accessed by the audit.')
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
    text=REPORT.read_text(encoding='utf-8')
    findings=[]
    for line in text.splitlines():
        if re.match(r'\| S\d\d \|',line):
            cells=[v.strip() for v in line.strip('|').split('|')]
            findings.append(dict(zip(('id','priority_status','finding','required_response'),cells)))
    with (OUT/'findings.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['id','priority_status','finding','required_response'])
        writer.writeheader(); writer.writerows(findings)
    missing=[]
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
        if '://' in target or target.startswith('#'):
            continue
        path=REPORT.parent/target.split('#')[0]
        if not path.exists():
            missing.append(target)
    assert not missing,missing
    sources=[ROOT/p for p in (
        'AGENTS.md','README-RESEARCH.md','EXPERIMENT.md','docs/SPEC.md','docs/ARCHITECTURE.md',
        'docs/EXPERIMENT-MATH.md','docs/PREDICTION-PILLARS.md','docs/REDESIGN-DECISIONS.md',
        'docs/AMENDMENT-03-jump-sparsity-R2.md',
        'seraph/prediction/models.py','seraph/prediction/pillars.py','seraph/prediction/evaluation.py',
        'seraph/pillars/hawkes/engine.py','seraph/pillars/rmt/engine.py','seraph/pillars/hamilton/engine.py',
        'seraph/features/jump_extraction.py','seraph/features/cross_sectional.py',
        'seraph/reconciliation/kalman.py','seraph/reconciliation/noise_model.py',
        'seraph/fusion/score.py','seraph/fusion/standardize.py','seraph/validation/harness.py',
        'seraph/validation/epochs.py','seraph/orchestration/standardize.py',
        'seraph/orchestration/hamilton_causal.py','seraph/orchestration/original_execution.py',
        'seraph/live/inference.py','scripts/run_prediction_experiment.py',
        'scripts/snapshot_research_data.py','scripts/evaluate_csrs_research.py',
        'research_data/market_snapshot.parquet','research_results/v1_verified/features.parquet',
        'research_results/v1_verified/predictions.parquet','research_results/v1_verified/fit_audit.json')]
    outputs=[REPORT,*[p for p in OUT.rglob('*') if p.is_file()
            and p.name!='manifest.json' and '__pycache__' not in p.parts]]
    manifest=dict(created_at=verification['created_at'],
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in sources},
        outputs={p.relative_to(ROOT).as_posix():sha(p) for p in outputs},
        findings=len(findings),broken_report_links=missing)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(tests=counts,findings=len(findings),broken_links=missing),indent=2))


if __name__=='__main__':
    main()
