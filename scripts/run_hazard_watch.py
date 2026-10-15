"""Replay a separately labelled public-health watch and its union with SERAPH.

Predeclared after observing the market-model failure: 20 sessions, all sourced
new WHO PHEIC declarations, next-observed-session availability, no event-specific
tuning or probability claims. See docs/EXTERNAL-HAZARD-SOURCES.md.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from seraph.prediction.hazard_watch import public_event_watch
from seraph.prediction.evaluation import onset_labels, event_warnings, alarm_stats, episode_spans
from seraph.validation.epochs import EPOCH_BREAKS


def run(results):
    if (results/'hazard_summary.json').exists():
        raise SystemExit('Hazard result already exists; retain it and use a new results directory.')
    source = ROOT/'research_data/public_health_events.json'
    payload = json.loads(source.read_text(encoding='utf-8'))
    events = payload if isinstance(payload,list) else payload['events']
    frame = pd.read_parquet(results/'predictions.parquet')
    selected = frame[(frame.target == 'onset15') & (frame.model == 'combined')].sort_values('date')
    dates = selected.date.to_numpy(dtype='datetime64[D]')
    watch = public_event_watch(dates,events,duration=20)
    # Evaluate only from the first declaration onward; earlier absence of
    # event records is not evidence of a functioning alert feed.
    start = min(np.datetime64(e['published_date'],'D') for e in events)
    ext_covered = dates > start
    model_covered = np.isfinite(selected.probability.to_numpy()) & ~np.isnan(selected.threshold.to_numpy())
    model_alarm = selected.alarm.to_numpy(bool)
    combined_watch = model_alarm | watch['watch']
    labels = onset_labels(dates,[v[0] for v in EPOCH_BREAKS.values()])
    evaluation = {}
    for name,values,covered in [('external',watch['watch'],ext_covered),
                                 ('combined',combined_watch,ext_covered & model_covered)]:
        score = np.where(covered,values.astype(float),np.nan)
        evaluation[name] = dict(alarm_stats=alarm_stats(score,labels,.5),
                               events=event_warnings(dates,score,np.full(len(dates),.5),EPOCH_BREAKS))
    source_audit = []
    for event in watch['events']:
        indices = np.array([event['event'] in ids.split(';') for ids in watch['active_events']])
        matched = [name for name,(date,_) in EPOCH_BREAKS.items()
                   if any(indices[max(0,int(np.searchsorted(dates,np.datetime64(date)))-15):int(np.searchsorted(dates,np.datetime64(date)))])]
        source_audit.append(dict(**event, matched_project_events=','.join(matched),
                                 unmatched_under_project_labels=not bool(matched)))
    table = pd.DataFrame(dict(date=selected.date,external_watch=watch['watch'],
                              combined_model_alarm=model_alarm,combined_watch=combined_watch,
                              active_events=watch['active_events'],
                              external_assessable=ext_covered,combined_assessable=ext_covered & model_covered))
    table.to_parquet(results/'hazard_watch.parquet',index=False)
    summary = dict(protocol=dict(duration_sessions=20,availability='strictly next observed session after published date',
                                 rule='each new WHO PHEIC declaration, irrespective of subsequent market outcome',
                                 established_after='v1 market-model results observed; hypothesis is hindsight-informed',
                                 score_interpretation='binary contextual watch, never a calibrated probability'),
                   source_events=source_audit,evaluation=evaluation,
                   source_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
                   limitations=[
                       'Historical counterfactual scenario, not evidence that this policy existed or was chosen before COVID.',
                       'The public announcement identifies a health emergency. It does not establish an impending financial crisis, causal market effect, or probability of loss.',
                       'The 20-session watch duration was chosen after seeing market-only results; sensitivity and prospective validation remain required. All declarations stay in the audit.',
                       'Next-session availability from a page date approximates dissemination; publication timestamps and immutable as-of archives are incomplete.',
                       'Unmatched health watches are labelled false only relative to the six provisional project market-event labels; these are not a universal inventory of financial crises.',
                       'The external watch is additional context. It does not repair or validate the market-only three-pillar onset model.',
                   ])
    (results/'hazard_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    pd.DataFrame(source_audit).to_csv(results/'hazard_event_audit.csv',index=False)
    lines = ['# Public-event hazard watch: separate counterfactual replay','',
             'This is an additional contextual watch, not a crisis probability. The rule was designed after the market-model failure; it was not preregistered before COVID.','',
             'Every sourced new WHO public-health emergency declaration starts a fixed 20-session watch on the next observed trading session. No event is selected based on the subsequent market return.','',
             '| Declaration | Published | First session | Matched project events |','|---|---|---|---|']
    for e in source_audit:
        lines.append(f"| {e['event']} | {e['published_date']} | {e['first_session']} | {e['matched_project_events'] or 'None'} |")
    lines += ['', '## Full warning cost', '',
              '| Policy | Episodes | Unmatched episodes | Unmatched/year | Time under watch |',
              '|---|---:|---:|---:|---:|']
    for name, result in evaluation.items():
        s = result['alarm_stats']
        lines.append(f"| {name} | {s['episodes']} | {s['false_episodes']} | {s['false_episodes_per_year']:.2f} | {s['alarm_fraction']:.1%} |")
    lines += ['', 'These unmatched counts use the project’s provisional market-event labels. The union with the market alarm has a higher false-alarm rate; the external COVID trigger does not validate the combined policy.']
    lines += ['', '## Pre-onset record of the external channel alone','',
              '| Project event | Result | First warning | Lead sessions |','|---|---|---|---|']
    for e in evaluation['external']['events']:
        lines.append(f"| {e['event']} | {e['status']} | {e['first_warning'] or '-'} | {e['lead_sessions'] or '-'} |")
    lines += ['', '## Limits',''] + ['- '+x for x in summary['limitations']]
    (results/'HAZARD-REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(evaluation,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=ROOT/'research_results/v1_verified')
    run(parser.parse_args().results.resolve())
