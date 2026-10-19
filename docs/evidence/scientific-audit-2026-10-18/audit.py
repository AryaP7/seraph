"""C10 scientific audit (FR30, FR32–37): frozen-artifact diagnostics.

Read-only with respect to source data and models. Writes only beside this file.
Run with --experiment for the finite, retrospective candidate list in PLAN.md.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from seraph.prediction.evaluation import (
    alarm_stats, calibrate_alerts, episode_spans, event_warnings,
    paired_brier_block_interval, probability_metrics,
)
from seraph.prediction.models import walk_forward_predict
from seraph.validation.epochs import EPOCH_BREAKS

FEATURES = ['ewma_volatility', 'hawkes_daily_intensity',
            'rmt_fast_leading_share', 'rmt_fast_minus_slow',
            'hamilton_daily_next_volatility']


def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [clean(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, (np.integer, np.bool_)):
        return x.item()
    return x


def save(name, obj):
    (OUT / name).write_text(json.dumps(clean(obj), indent=2, allow_nan=False), encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load():
    base = ROOT / 'research_results/v1_verified'
    provenance = json.loads((base / 'provenance.json').read_text())
    checks = []
    for name, expected in provenance['code_hashes'].items():
        path = ROOT / name
        checks.append(dict(kind='code', path=name, expected=expected,
                           actual=sha(path), matches=sha(path) == expected))
    for name in ('features.parquet', 'predictions.parquet', 'fit_audit.json'):
        actual = sha(base / name)
        expected = provenance['outputs'][name]
        checks.append(dict(kind='artifact', path=name, expected=expected,
                           actual=actual, matches=actual == expected))
        assert actual == expected, f'Changed saved evidence: {name}'
    actual = sha(ROOT / 'research_data/market_snapshot.parquet')
    assert actual == provenance['data_hash']
    checks.append(dict(kind='data', path='market_snapshot.parquet', actual=actual,
                       matches=True, expected=provenance['data_hash']))
    save('input-integrity.json', checks)
    frame = pd.read_parquet(ROOT / 'research_data/market_snapshot.parquet')
    features = pd.read_parquet(base / 'features.parquet')
    predictions = pd.read_parquet(base / 'predictions.parquet')
    assert (frame.date.to_numpy() == features.date.to_numpy()).all()
    assert frame.date.is_monotonic_increasing and not frame.date.duplicated().any()
    return frame, features, predictions, json.loads((base / 'fit_audit.json').read_text())


def average_precision(p, y):
    """Non-interpolated AP with equal-score ties grouped at one threshold."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    keep = np.isfinite(p) & np.isfinite(y)
    p, y = p[keep], y[keep]
    if not len(p) or y.sum() == 0:
        return None
    order = np.argsort(-p, kind='stable')
    p, y = p[order], y[order]
    ends = np.r_[np.flatnonzero(np.diff(p) != 0), len(p)-1]
    tp = np.cumsum(y)[ends]
    recall = tp / y.sum()
    return float(np.sum(np.diff(np.r_[0., recall]) * tp / (ends + 1)))


def metrics(p, y, mask=None):
    p, y = np.asarray(p, float), np.asarray(y, float)
    keep = np.isfinite(p) & np.isfinite(y)
    if mask is not None:
        keep &= mask
    result = probability_metrics(p, y, keep)
    result['average_precision'] = average_precision(p[keep], y[keep])
    result['mean_probability'] = float(np.mean(p[keep])) if keep.any() else None
    result['always_negative_accuracy'] = 1 - result['base_rate'] if keep.any() else None
    return result


def climatology(y):
    """Same 756-label eligibility/63-session refits as the supervised baseline."""
    p = np.full(len(y), np.nan)
    last = -63
    rate = np.nan
    for t in range(15, len(y)):
        mature = y[:t-15+1]
        mature = mature[np.isfinite(mature)]
        if len(mature) >= 756 and t-last >= 63:
            rate, last = (mature.sum()+.5)/(len(mature)+1), t
        p[t] = rate
    return p


def math_probes():
    from seraph.validation.harness import mean_lead_time, calibration_loss
    from seraph.pillars.hamilton.engine import MultivariateTVTPHamilton, _half_life
    from seraph.pillars.rmt.engine import mp_bounds
    # A single isolated alarm 99 sessions before an onset is credited by the
    # legacy metric even though no alarm exists in the required last 15 days.
    scores = np.zeros(120); scores[1] = 1
    labels = np.zeros(120); labels[100:110] = 1
    legacy = mean_lead_time(scores, labels, .5)
    assert legacy == 99 and not (scores[85:100] >= .5).any()
    # Even knowing the true probability does not minimize the linear loss.
    truth = np.r_[np.ones(10), np.zeros(90)]
    losses = {str(p): calibration_loss(np.full(100, p), truth, 10., 1.)
              for p in (0., .1, 1.)}
    assert losses['1.0'] < losses['0.1']
    half = [dict(stay_probability=p, implemented=_half_life(p),
                 geometric_continuous_median=float(np.log(.5)/np.log(p)),
                 expected_spell_length=float(1/(1-p))) for p in (.5, .9, .99)]
    # Valid correlation matrices; independence rejection is not crisis risk.
    sector = np.eye(100)
    for g in range(5):
        sl = slice(20*g, 20*(g+1))
        sector[sl, sl] = .75*np.eye(20)+.25*np.ones((20,20))
    common = .75*np.eye(100)+.25*np.ones((100,100))
    edge = mp_bounds(2)[1]
    spectral = []
    for name, matrix in [('five_independent_sectors', sector), ('one_market_mode', common)]:
        eig = np.linalg.eigvalsh(matrix)
        spectral.append(dict(case=name, leading_share=eig[-1]/100,
                             exceedance_fraction=float((eig>edge).mean()), mp_upper=edge))
    assert spectral[1]['leading_share'] > spectral[0]['leading_share']
    assert spectral[1]['exceedance_fraction'] < spectral[0]['exceedance_fraction']
    # Reproduce the original block-filter future-dependent variance floor.
    rng = np.random.default_rng(410)
    y = rng.normal(size=(400, 3))*.1 + np.array([.5, .4, .01])
    train = MultivariateTVTPHamilton(y[:300])
    params = train.start_params.copy()  # fixed, legal training-only parameters
    ordinary = MultivariateTVTPHamilton(y)
    changed_y = y.copy(); changed_y[350:] += 100.
    changed = MultivariateTVTPHamilton(changed_y)
    before = np.asarray(ordinary.filter(params).filtered_marginal_probabilities)
    after = np.asarray(changed.filter(params).filtered_marginal_probabilities)
    if before.shape[0] != 3:
        before, after = before.T, after.T
    difference = float(np.max(np.abs(before[:,300:350]-after[:,300:350])))
    assert difference > 1e-6, 'Expected original floor dependence did not reproduce'
    # Freezing the floor to training removes this isolated leak.
    ordinary._var_floor = train._var_floor.copy()
    changed._var_floor = train._var_floor.copy()
    fixed_before = np.asarray(ordinary.filter(params).filtered_marginal_probabilities)
    fixed_after = np.asarray(changed.filter(params).filtered_marginal_probabilities)
    if fixed_before.shape[0] != 3:
        fixed_before, fixed_after = fixed_before.T, fixed_after.T
    fixed_diff = float(np.max(np.abs(fixed_before[:,300:350]-fixed_after[:,300:350])))
    assert fixed_diff < 1e-12
    return dict(legacy_lead_time=dict(reported_sessions=legacy, valid_15_session_warning=False),
                linear_loss_at_true_probability_point1=losses,
                hamilton_duration=half, rmt_exceedance_counterexample=spectral,
                original_hamilton_future_floor=dict(
                    max_prefix_probability_change=difference,
                    with_training_floor_max_change=fixed_diff,
                    scope='Original batched hamilton_causal.walk_forward; NOT daily prediction/pillars.py',
                    synthetic_only=True))


def diagnose(frame, features, predictions, fits):
    stats = []
    for col in features.columns[1:]:
        x = features[col].to_numpy(float); finite = x[np.isfinite(x)]
        stats.append(dict(feature=col, n=len(finite), unavailable=len(x)-len(finite),
                          mean=np.mean(finite), std=np.std(finite), min=np.min(finite),
                          p05=np.quantile(finite,.05), median=np.median(finite),
                          p95=np.quantile(finite,.95), max=np.max(finite),
                          zero_fraction=np.mean(np.isclose(finite,0.,atol=1e-10))))
    pd.DataFrame(stats).to_csv(OUT/'feature-summary.csv', index=False)
    features[FEATURES].corr(method='spearman').to_csv(OUT/'feature-correlations.csv')
    rows, calibration, era_rows, event_rows = [], [], [], []
    for target in ('loss10_15', 'onset15'):
        group = predictions[predictions.target==target]
        pivot = group.pivot(index='date',columns='model',values='probability')
        y = group[group.model=='combined'].sort_values('date').label.to_numpy(float)
        p0 = climatology(y)
        pivot['mature_climatology'] = p0
        common = np.isfinite(pivot.to_numpy()).all(axis=1) & np.isfinite(y)
        for model in pivot.columns:
            p = pivot[model].to_numpy(float)
            row = dict(target=target, model=model, **metrics(p,y,common))
            row['brier_skill_vs_mature_climatology'] = 1 - row['brier']/metrics(p0,y,common)['brier']
            rows.append(row)
            if model not in ('combined','baseline_logit','mature_climatology'):
                continue
            for lo,hi in ((0,.01),(.01,.025),(.025,.05),(.05,.10),(.10,.20),(.20,.40),(.40,1.00001)):
                m = common & (p>=lo) & (p<hi)
                calibration.append(dict(target=target,model=model,bin_low=lo,bin_high=hi,
                                        n=int(m.sum()),predicted=np.mean(p[m]) if m.any() else None,
                                        observed=np.mean(y[m]) if m.any() else None))
            years = pd.DatetimeIndex(pivot.index).year
            for label, lo,hi in [('through_2014',0,2014),('2015_2019',2015,2019),
                                 ('2020_2022',2020,2022),('2023_onward',2023,9999)]:
                era_rows.append(dict(target=target,model=model,era=label,
                                     **metrics(p,y,common & (years>=lo) & (years<=hi))))
        for model in ('combined','baseline_logit'):
            g = group[group.model==model].sort_values('date')
            event_rows += [dict(target=target,model=model,**r) for r in event_warnings(
                g.date,g.probability,g.threshold,EPOCH_BREAKS)]
    pd.DataFrame(rows).to_csv(OUT/'existing-metrics.csv',index=False)
    pd.DataFrame(calibration).to_csv(OUT/'reliability.csv',index=False)
    pd.DataFrame(era_rows).to_csv(OUT/'existing-era-metrics.csv',index=False)
    pd.DataFrame(event_rows).to_csv(OUT/'existing-event-warnings.csv',index=False)
    hmm = fits['pillars']['hamilton_fits']; hawkes=fits['pillars']['hawkes_daily_fits']
    # Check stored fit and threshold cutoffs; labels at i mature at i+15.
    violations=[]
    for name, records in fits['prediction'].items():
        if not isinstance(records,list):
            continue
        for f in records:
            if f['train_end']+15 > f['fitted_at']:
                violations.append(dict(model=name,fit=f['fitted_at']))
    for name, records in fits['alerts'].items():
        for f in records:
            if f['calibration_end_exclusive']-1+15 > f['decision_index']:
                violations.append(dict(alert=name,fit=f['decision_index']))
    assert not violations
    intervals=[]
    for target in ('loss10_15','onset15'):
        g=predictions[predictions.target==target]
        c=g[g.model=='combined'].sort_values('date')
        b=g[g.model=='baseline_logit'].sort_values('date')
        for block in (21,63,126):
            intervals.append(dict(target=target,**paired_brier_block_interval(
                c.probability,b.probability,c.label,block=block)))
    save('diagnostics.json',dict(
        created_at=datetime.now(timezone.utc).isoformat(),
        data=dict(n=len(frame),start=str(frame.date.min()),end=str(frame.date.max()),
                  min_members=int(frame.universe_count.min()),max_members=int(frame.universe_count.max()),
                  missing_market_returns=int(frame.market_return.isna().sum()),
                  extreme_return_rows=frame.loc[frame.market_return.abs().nlargest(8).index,
                    ['date','market_return','universe_count']].assign(date=lambda d:d.date.astype(str)).to_dict('records')),
        hamilton=dict(fits=len(hmm),nonconverged=sum(not f['converged'] for f in hmm),
                      min_state_occupancy=min(min(f['occupancy_fraction']) for f in hmm)),
        hawkes=dict(fits=len(hawkes),zero_branching_fits=sum(f['branching']<1e-10 for f in hawkes),
                    min_events=min(f['events'] for f in hawkes)),
        stored_cutoff_violations=violations, paired_intervals=intervals,
        mathematical_probes=math_probes()))
    print(pd.DataFrame(rows).query("model in ['combined','baseline_logit','mature_climatology']").to_string(index=False),flush=True)


def experiment(frame, features, predictions):
    dest=OUT/'experiment'
    dest.mkdir(exist_ok=True)
    if (dest/'summary.json').exists():
        raise SystemExit('Completed experiment exists; preserve it.')
    features=features.copy()
    features['return_20']=frame.market_return.rolling(20,min_periods=20).sum()
    features['breadth_down']=frame.breadth_down
    context=['ewma_volatility','return_20','breadth_down']
    configs={
        'baseline':dict(names=FEATURES[:1]), 'combined':dict(names=FEATURES),
        'baseline_C1':dict(names=FEATURES[:1],C=1.),
        'combined_C1':dict(names=FEATURES,C=1.),
        'baseline_5y':dict(names=FEATURES[:1],max_train=1260),
        'combined_5y':dict(names=FEATURES,max_train=1260),
        'combined_interaction':dict(names=FEATURES,
            interactions=[('hawkes_daily_intensity','rmt_fast_minus_slow')]),
        'context':dict(names=context),
        'context_combined':dict(names=context+FEATURES[1:]),
    }
    summary=[]; all_tables=[]; audit={}; events=[]; era=[]; bins=[]
    dates=frame.date.to_numpy(dtype='datetime64[D]')
    for target in ('loss10_15','onset15'):
        original=predictions[(predictions.target==target)&(predictions.model=='combined')].sort_values('date')
        y=original.label.to_numpy(float)
        outputs={'climatology':climatology(y)}
        for name,cfg in configs.items():
            print(f'Exploratory {target}/{name}',flush=True)
            result=walk_forward_predict(features,y,cfg['names'],C=cfg.get('C',.1),
                        max_train=cfg.get('max_train'),interactions=cfg.get('interactions',()))
            outputs[name]=result.probability
            audit[target+'/'+name]=dict(fits=result.fits)
            assert all(f['train_end']+15<=f['fitted_at'] for f in result.fits)
            if name in ('baseline','combined'):
                old_name='baseline_logit' if name=='baseline' else 'combined'
                old=predictions[(predictions.target==target)&(predictions.model==old_name)].sort_values('date')
                np.testing.assert_allclose(result.probability,old.probability,rtol=0,atol=1e-12,equal_nan=True)
        common=np.logical_and.reduce([np.isfinite(v) for v in outputs.values()]) & np.isfinite(y)
        for name,p in outputs.items():
            alerts=calibrate_alerts(p,y)
            audit.setdefault(target+'/'+name,{})['alerts']=alerts['fits']
            matched=('context' if name=='context_combined' else 'baseline_C1' if name=='combined_C1'
                     else 'baseline_5y' if name=='combined_5y' else 'baseline')
            row=dict(target=target,model=name,**metrics(p,y,common),
                     matched_baseline=matched,alerts=alarm_stats(p,y,alerts['threshold']),
                     vs_matched=paired_brier_block_interval(p,outputs[matched],y))
            # Exclude the unresolved tariff pre-window plus all subsequent rows;
            # avoids redefining historical positives as negatives or contaminating
            # assessment with later training that incorporates the placeholder.
            tariff_idx=int(np.searchsorted(dates,np.datetime64(EPOCH_BREAKS['tariff_2026'][0])))
            before_tariff=np.arange(len(y))<tariff_idx-15
            row['assessment_before_unresolved_tariff']=metrics(p,y,common & before_tariff)
            rows=event_warnings(dates,p,alerts['threshold'],EPOCH_BREAKS)
            valid_events=[r for r in rows if r['event']!='tariff_2026' and r['status']!='unassessable']
            row['events_excluding_tariff']=dict(assessable=len(valid_events),
                        warned=sum(r['status']=='warned' for r in valid_events))
            summary.append(row)
            events.extend(dict(target=target,model=name,**r) for r in rows)
            years=frame.date.dt.year.to_numpy()
            for label,lo,hi in [('through_2014',0,2014),('2015_2019',2015,2019),
                                ('2020_2022',2020,2022),('2023_onward',2023,9999)]:
                era.append(dict(target=target,model=name,era=label,
                                **metrics(p,y,common & (years>=lo) & (years<=hi))))
            for lo,hi in ((0,.01),(.01,.025),(.025,.05),(.05,.10),(.10,.20),(.20,.40),(.40,1.00001)):
                m=common & (p>=lo)&(p<hi)
                bins.append(dict(target=target,model=name,low=lo,high=hi,n=int(m.sum()),
                                 predicted=np.mean(p[m]) if m.any() else None,
                                 observed=np.mean(y[m]) if m.any() else None))
            all_tables.append(pd.DataFrame(dict(date=frame.date,target=target,model=name,
                probability=p,label=y,threshold=alerts['threshold'],alarm=alerts['alarm'])))
    pd.concat(all_tables).to_parquet(dest/'predictions.parquet',index=False)
    pd.DataFrame(events).to_csv(dest/'event-warnings.csv',index=False)
    pd.DataFrame(era).to_csv(dest/'era-metrics.csv',index=False)
    pd.DataFrame(bins).to_csv(dest/'reliability.csv',index=False)
    (dest/'fit-audit.json').write_text(json.dumps(clean(audit),indent=2),encoding='utf-8')
    (dest/'summary.json').write_text(json.dumps(clean(summary),indent=2),encoding='utf-8')
    flat=[]
    for r in summary:
        flat.append({k:v for k,v in r.items() if not isinstance(v,dict)} |
                    r['alerts'] | {'assessable_events_ex_tariff':r['events_excluding_tariff']['assessable'],
                                  'warned_events_ex_tariff':r['events_excluding_tariff']['warned'],
                                  'brier_difference':r['vs_matched']['mean'],
                                  'difference_lower':r['vs_matched']['lower'],
                                  'difference_upper':r['vs_matched']['upper']})
    pd.DataFrame(flat).to_csv(dest/'metrics.csv',index=False)
    print(pd.DataFrame(flat)[['target','model','brier','auc','average_precision','warned_events_ex_tariff']].to_string(index=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',action='store_true')
    args=parser.parse_args()
    data=load()
    if args.experiment:
        experiment(*data[:3])
    else:
        diagnose(*data)
    save('latest-run.json',dict(script_sha256=sha(Path(__file__)),plan_sha256=sha(OUT/'PLAN.md'),
                               created_at=datetime.now(timezone.utc).isoformat(),experiment=args.experiment))
