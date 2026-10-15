"""Reproduce the isolated, frozen-design SERAPH forecasting experiment.

No network/database access. Run from any cwd with the experimental environment.
Artifacts include every daily forecast, fit cutoff, alert calibration and failure.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd

from seraph.prediction.pillars import PillarConfig, build_pillar_features
from seraph.prediction.models import (
    EWMAStudentTForecaster, future_loss_labels, walk_forward_predict,
    gjr_garch_student_t_predict,
)
from seraph.prediction.evaluation import (
    AlertConfig, onset_labels, calibrate_alerts, alarm_stats,
    probability_metrics, event_warnings, episode_spans, paired_brier_block_interval,
)
from seraph.validation.epochs import EPOCH_BREAKS

HORIZON = 15
PILLARS = ['hawkes_daily_intensity', 'rmt_fast_leading_share',
           'rmt_fast_minus_slow', 'hamilton_daily_next_volatility']
ALL_FEATURES = ['ewma_volatility', *PILLARS]
CANDIDATES = {
    'baseline_logit': ['ewma_volatility'],
    'three_pillars': PILLARS,
    'combined': ALL_FEATURES,
    'without_hawkes': [x for x in ALL_FEATURES if not x.startswith('hawkes')],
    'without_rmt': [x for x in ALL_FEATURES if not x.startswith('rmt')],
    'without_hamilton': [x for x in ALL_FEATURES if not x.startswith('hamilton')],
}


def serial(value):
    if isinstance(value, dict):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [serial(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return 'abstain' if value == np.inf else None
    if isinstance(value, (np.floating, np.bool_)):
        return value.item()
    return value


def save_json(path, data):
    path.write_text(json.dumps(serial(data), indent=2, allow_nan=False), encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_text(summary):
    lines = ['# SERAPH experimental replay', '',
             'Status: research implementation complete; original crisis-prediction claim remains unvalidated.', '',
             f"Data as of **{summary['as_of']}**. This is a historical snapshot, not live monitoring.", '',
             'All three pillar families are present in `three_pillars` and `combined`. Ablations are comparison controls.', '',
             '## Original pre-onset question', '',
             'Combined model, fixed 15-session window before each unchanged project event date:', '',
             '| Event | Label | Result | First warning | Lead sessions |',
             '|---|---|---|---|---|']
    combined = next(m for m in summary['models'] if m['target'] == 'onset15' and m['model'] == 'combined')
    for row in combined['events']:
        lines.append(f"| {row['event']} | {row['label_date']} | {row['status']} | {row['first_warning'] or '-'} | {row['lead_sessions'] or '-'} |")
    lines += ['', 'All dates are inherited provisional research labels; tariff-2026 is explicitly unresolved and cannot establish validation.', '',
              '## Probability and alert comparisons', '',
              'Lower Brier score is better. Metrics below share common forecast coverage within each target. Alert rates use each model’s own assessable coverage.', '',
              '| Target | Model | Brier | AUC | False episodes/year | Warning time |',
              '|---|---|---:|---:|---:|---:|']
    def fmt(v, percent=False):
        return '-' if v is None else f'{100*v:.1f}%' if percent else f'{v:.4f}'
    for m in summary['models']:
        metric, stats = m['metrics_common'], m['alarm_stats']
        lines.append(f"| {m['target']} | {m['model']} | {fmt(metric['brier'])} | {fmt(metric['auc'])} | {fmt(stats['false_episodes_per_year'])} | {fmt(stats['alarm_fraction'], True)} |")
    lines += ['', 'The loss endpoint is a 10% decline from the decision close at any close in the next 15 sessions. It is not a named-crisis forecast.', '',
              '## Combined versus volatility logistic baseline', '',
              'Paired Brier differences below use common pairwise coverage. Negative favors combined. Intervals are descriptive 63-session block bootstrap intervals, not confirmation after model selection.', '']
    for m in summary['models']:
        if m['model'] == 'combined':
            ci = m['vs_baseline_brier']
            lines.append(f"- {m['target']}: difference {fmt(ci['mean'])}; interval [{fmt(ci['lower'])}, {fmt(ci['upper'])}].")
    lines += ['', '## What this establishes', '',
              'The software now issues causal, timestamped future-target forecasts and auditable alerts. It can replay the available history without reading future labels during fitting. That establishes implementation behavior, not dependable crisis foresight.', '',
              '## Limits', '']
    lines.extend('- '+x for x in summary['limitations'])
    lines += ['', '## Reproduction', '',
              'Run `./.venv/Scripts/python.exe scripts/run_prediction_experiment.py --out research_results/replication` from this copied project. No source database access is needed. See `EXPERIMENT.md` for fixed choices and `docs/EXPERIMENT-MATH.md` for repaired fusion equations.', '',
              'Artifacts: `predictions.parquet`, `features.parquet`, `summary.json`, `fit_audit.json`, `alert_episodes.csv`, `event_warnings.csv`, `provenance.json`.', '']
    return '\n'.join(lines)


def run(data_dir, out):
    out.mkdir(parents=True, exist_ok=True)
    if (out/'summary.json').exists():
        raise SystemExit('Output already contains a completed run. Choose a new --out to preserve evidence.')
    frame = pd.read_parquet(data_dir/'market_snapshot.parquet').sort_values('date').reset_index(drop=True)
    if frame.date.duplicated().any():
        raise ValueError('duplicate decision sessions')
    dates = frame.date.to_numpy(dtype='datetime64[D]')
    simple_returns = np.expm1(frame.market_return.to_numpy(float))
    print('Building causal daily Hawkes / RMT / Hamilton variants...', flush=True)
    pillar_config = PillarConfig()
    pillars = build_pillar_features(frame.market_return.to_numpy(float),
                                   frame[[f'factor_{i}' for i in range(10)]].to_numpy(float), config=pillar_config)
    ewma = EWMAStudentTForecaster().predict(simple_returns)
    features = pd.DataFrame(pillars.values)
    features['ewma_volatility'] = ewma['volatility']
    features.insert(0, 'date', frame.date)
    features.to_parquet(out/'features.parquet', index=False)
    labels = {'loss10_15': future_loss_labels(simple_returns),
              'onset15': onset_labels(dates, [v[0] for v in EPOCH_BREAKS.values()])}
    forecasts, audit = {}, {'pillars': pillars.diagnostics, 'prediction': {}, 'alerts': {}}
    for target, y in labels.items():
        for name, names in CANDIDATES.items():
            print(f'Forecasting {target}/{name}...', flush=True)
            result = walk_forward_predict(features, y, names)
            forecasts[target, name] = dict(probability=result.probability,
                                           train_end=result.train_end, status=result.fit_status,
                                           features=names)
            audit['prediction'][f'{target}/{name}'] = result.fits
    forecasts['loss10_15', 'ewma_student_t'] = dict(
        probability=ewma['probability'], train_end=np.full(len(frame), -1),
        status=ewma['status'], features=['ewma_volatility'])
    audit['prediction']['loss10_15/ewma_student_t'] = ewma['metadata']
    print('Forecasting GJR-GARCH Student-t benchmark...', flush=True)
    gjr = gjr_garch_student_t_predict(simple_returns)
    forecasts['loss10_15', 'gjr_garch_t'] = dict(
        probability=gjr['probability'], train_end=gjr['train_end'],
        status=gjr['status'], features=['market_log_return_history'])
    audit['prediction']['loss10_15/gjr_garch_t'] = dict(fits=gjr['fits'], metadata=gjr['metadata'])
    alert_config = AlertConfig()
    common = {target: np.logical_and.reduce([np.isfinite(f['probability']) for (t, _), f in forecasts.items() if t == target])
              for target in labels}
    models, tables, episodes, events = [], [], [], []
    for (target, name), f in forecasts.items():
        print(f'Evaluating {target}/{name}...', flush=True)
        y, p = labels[target], f['probability']
        alerts = calibrate_alerts(p, y, alert_config)
        th = alerts['threshold']
        event_rows = event_warnings(dates, p, th, EPOCH_BREAKS)
        # Show named events for both endpoints, but label loss-target alerts as such.
        row = dict(target=target, model=name, features=f['features'],
                   metrics=probability_metrics(p, y), metrics_common=probability_metrics(p, y, common[target]),
                   alarm_stats=alarm_stats(p, y, th), events=event_rows,
                   fit_status_counts={str(k):int(v) for k,v in zip(*np.unique(f['status'], return_counts=True))},
                   vs_baseline_brier=paired_brier_block_interval(p, forecasts[target, 'baseline_logit']['probability'], y))
        models.append(row)
        audit['alerts'][f'{target}/{name}'] = alerts['fits']
        table = pd.DataFrame(dict(date=frame.date, target=target, model=name, probability=p,
                                  label=y, threshold=th, alarm=alerts['alarm'],
                                  train_end=f['train_end'], fit_status=f['status']))
        tables.append(table)
        for start, end in episode_spans(alerts['alarm']):
            complete = bool(np.isfinite(y[start:end]).all())
            episodes.append(dict(target=target, model=name, start=str(dates[start]), end=str(dates[end-1]),
                                 sessions=end-start, outcome=('pending' if not complete else
                                     'contains_positive_target' if np.any(y[start:end] == 1) else 'false_alarm')))
        events.extend(dict(target=target, model=name, **e) for e in event_rows)
    limitations = [
        'Retrospective research: COVID and the other events informed project design. This is not an untouched pre-COVID model or prospective validation.',
        'Underlying adjusted prices are a current snapshot, not an as-first-published vintage archive. Universe/survivorship and turnover-proxy caveats are inherited.',
        'The market series is an equal-weight geometric-return research index of available universe members, not a tradable portfolio or the NIFTY index.',
        'All project event dates are provisional; tariff-2026 is explicitly unresolved. Warnings against that placeholder are diagnostic only.',
        'New daily-tail Hawkes and 10 hash-portfolio RMT are distinct from original intraday/500-stock estimators; no high-dimensional RMT significance claim is made.',
        'Hamilton next-crisis-state probability denotes a fitted high-volatility latent state, not the probability of a named crisis.',
        'Only six labelled episodes exist; overlapping daily positives do not create six independent years of crises. Sampling and regime uncertainty remain substantial.',
        'Threshold budgets are fit on past data and may be violated subsequently. Abstention, missingness, and unassessable early periods are retained.',
        'Bootstrap intervals do not correct for research/model selection, changing regimes, data revisions or label uncertainty.',
        'HMM cap-limited and Hawkes sparse-event fits remain visible in fit_audit.json; forecasts contain model uncertainty not captured by simulation standard errors.',
        'No broker execution, production monitoring, point-in-time news/macro ingestion, or production acceptance is claimed.',
    ]
    summary = dict(created_utc=datetime.now(timezone.utc).isoformat(), as_of=str(dates[-1]),
                   protocol=dict(horizon=15, loss_barrier=.10, min_train=756, refit_every=63, C=.1,
                                 pillar_config=asdict(pillar_config), alert_config=asdict(alert_config),
                                 candidate_features=CANDIDATES),
                   data_manifest=json.loads((data_dir/'manifest.json').read_text(encoding='utf-8')),
                   models=models, limitations=limitations,
                   empirical_acceptance=dict(status='unvalidated',
                       reason='Retrospective replay does not establish dependable advance crisis prediction; inspect measured results and retain failed hypotheses.'))
    pd.concat(tables, ignore_index=True).to_parquet(out/'predictions.parquet', index=False)
    pd.DataFrame(episodes).to_csv(out/'alert_episodes.csv', index=False)
    pd.DataFrame(events).to_csv(out/'event_warnings.csv', index=False)
    save_json(out/'fit_audit.json', audit)
    save_json(out/'summary.json', summary)
    code = [Path(__file__), ROOT/'EXPERIMENT.md', ROOT/'seraph/validation/epochs.py',
            *[ROOT/'seraph/prediction'/name for name in ('models.py','pillars.py','evaluation.py')]]
    provenance = dict(created_utc=summary['created_utc'], python=sys.version,
                      libraries={name:importlib.metadata.version(name) for name in
                                 ('numpy','scipy','pandas','pyarrow','arch','statsmodels')},
                      code_hashes={str(p.relative_to(ROOT)):sha(p) for p in code},
                      data_hash=sha(data_dir/'market_snapshot.parquet'),
                      outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    save_json(out/'provenance.json', provenance)
    (out/'REPORT.md').write_text(report_text(summary), encoding='utf-8')
    print(f'Completed. Results: {out}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT/'research_data')
    parser.add_argument('--out', type=Path, default=ROOT/'research_results'/'v1_verified')
    args = parser.parse_args()
    run(args.data.resolve(), args.out.resolve())
