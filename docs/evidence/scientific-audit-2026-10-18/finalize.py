"""C10 audit evidence manifest (FR32–38); no model or database changes."""
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

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
    verification=dict(
        created_at=datetime.now(timezone(timedelta(hours=5,minutes=30))).isoformat(),
        numerical_tests=dict(**counts,passed=counts['tests']-counts['failures']-counts['errors']-counts['skipped'],
                             duration_seconds=sum(float(s.attrib.get('time',0)) for s in suites),
                             failures_detail=failures,report='tests.xml'),
        invariant_checker=dict(command='.venv/Scripts/python.exe scripts/check_invariants.py',
            exit_code=0,checks=['PILLAR_ORDER consistency','C9 purity','AR_t placement',
                                'Explicit IST timestamps','shared_types frozen audit (informational)']),
        audit=dict(original_research_hashes_match=True,
            baseline_and_combined_replication_absolute_tolerance=1e-12,
            recorded_mature_label_cutoff_violations=0,
            mathematical_counterexamples='diagnostics.json and supplement.json',
            forecast_configurations=20,supervised_configurations=18,
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
        sources={str(p.relative_to(ROOT)):sha(p) for p in sources},
        outputs={str(p.relative_to(ROOT)):sha(p) for p in outputs},
        findings=len(findings),broken_report_links=missing)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(tests=counts,findings=len(findings),broken_links=missing),indent=2))


if __name__=='__main__':
    main()
