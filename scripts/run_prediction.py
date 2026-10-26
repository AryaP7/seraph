#!/usr/bin/env python
"""Run SERAPH's prediction and early-warning engine, and persist its state.

    python scripts/run_prediction.py              # run and save
    python scripts/run_prediction.py --status     # read what was last saved
    python scripts/run_prediction.py --print      # run and print, save nothing

This is the operational job behind the console's PREDICTION & EARLY WARNING
panel. It runs the **actual** engine -- `build_pillar_features`,
`walk_forward_predict`, `calibrate_alerts` -- on the real market snapshot, in
about twenty seconds, and writes the current forecast and warning state for
the console to read.

Why a job and not a call from the page: a full causal replay refits the model
seventy-three times over twenty-one years of sessions, and doing that on page
render would make every refresh a cliff. The same reason `run_daily.py`
computes and the MARKET JOBS panel reads. `run_market_jobs.py` invokes this
as part of the daily sequence, so the panel refreshes on the intended
schedule rather than when someone happens to open it.

The engine reads a local parquet snapshot and nothing else: no database, no
network, no broker. It is safe to run at any time.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def default_snapshot() -> Path:
    """The package decides, so the job and the console agree.

    Prefers the rebuilt snapshot over the frozen experiment input; see
    `operational.snapshot_path`.
    """
    from seraph.prediction import operational

    return operational.snapshot_path()
DEFAULT_STATE = ROOT / 'prototype_runs' / 'prediction' / 'state.json'


def state_path() -> Path:
    """The package owns this, so the console does not need `scripts/`."""
    from seraph.prediction import operational

    return operational.state_path()


def status() -> dict:
    """What was last saved, without running anything."""
    from seraph.prediction import operational

    return operational.load_state()


def run(snapshot: Path, out: Path | None) -> dict:
    from seraph.prediction import operational

    if not snapshot.exists():
        return dict(ok=False, error=(
            f'no market snapshot at {snapshot}. The engine needs the '
            f'point-in-time market and factor panel; '
            f'scripts/snapshot_research_data.py builds it from the store.'))

    # Fails loudly if the operational feature set has drifted from the frozen
    # experiment's `combined` candidate -- two declarations of one list.
    operational.assert_matches_experiment()

    state = operational.run(snapshot)
    result = dict(ok=True, as_of=state.as_of,
                  probability=state.predicted['probability'],
                  warning=state.warning['level'],
                  threshold=state.warning['threshold'],
                  validation=state.validation['status'])
    if out is not None:
        from seraph.prediction import issuance
        ledger = issuance.runtime_store()
        state.issuance = issuance.issue(state, ledger)
        operational.save(state, out)
        result['issuance'] = state.issuance
        result['settlement'] = issuance.settle(ledger, snapshot)
        result['saved'] = str(out)
    result['state'] = state
    return result


def render(state) -> str:
    predicted = state.predicted if hasattr(state, 'predicted') else state['predicted']
    warning = state.warning if hasattr(state, 'warning') else state['warning']
    measured = state.measured if hasattr(state, 'measured') else state['measured']
    history = state.history if hasattr(state, 'history') else state['history']
    validation = state.validation if hasattr(state, 'validation') else state['validation']
    as_of = state.as_of if hasattr(state, 'as_of') else state['as_of']

    lines = [f'DECISION DATE {as_of}', '']
    lines.append('MEASURED  (observations at the decision close)')
    for name, item in measured['pillar_features'].items():
        value = '--' if item['value'] is None else f"{item['value']:.6f}"
        lines.append(f"  {item['pillar']:<20}{name:<34}{value}")
    lines += ['', 'PREDICTED  (one model output, not a measurement)']
    probability = predicted['probability']
    lines.append(f"  probability       "
                 f"{'--' if probability is None else format(probability, '.4f')}")
    lines.append(f"  {predicted['definition']}")
    lines.append(f"  model             {predicted['model']}")
    lines.append(f"  fit               {predicted['fit_status']}, "
                 f"{predicted['training_count']} training rows, labels through "
                 f"{predicted['train_end_date']}")
    lines += ['', 'WARNING  (a policy decision against a calibrated threshold)']
    lines.append(f"  level             {warning['level'].upper()}")
    lines.append(f"  {warning['reason']}")
    budget = warning['budget']
    lines.append(f"  budget            <= "
                 f"{budget['false_episodes_per_year']} false episodes/year and "
                 f"<= {budget['max_alarm_fraction']:.0%} of sessions in alarm")
    lines += ['', 'REALISED HISTORY  (retrospective replay, not foresight)']
    metrics, stats = history['metrics'], history['alarm_stats']

    def number(value, spec='.4f'):
        return '--' if value is None else format(value, spec)

    lines.append(f"  brier {number(metrics['brier'], '.5f')} | "
                 f"auc {number(metrics['auc'])} | "
                 f"{metrics['n']} forecasts | "
                 f"base rate {number(metrics.get('base_rate'))}")
    lines.append(f"  alarms on {number(stats['alarm_fraction'], '.2%')} of "
                 f"sessions | {number(stats['false_episodes_per_year'], '.2f')} "
                 f"false episodes/year across {stats['episodes']} episodes")
    lines.append('  reliability (predicted vs realised, matured labels only):')
    for row in history['reliability']:
        if not row['count']:
            continue
        lines.append(f"    [{row['lower']:.2f},{row['upper']:.2f})  "
                     f"n={row['count']:<6} predicted "
                     f"{row['mean_predicted']:.4f}  realised "
                     f"{row['realised_rate']:.4f}")
    lines += ['', f"VALIDATION  {validation['status'].upper()}",
              f"  {validation['note']}"]
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status', action='store_true',
                        help='read the saved state; run nothing')
    parser.add_argument('--print', dest='print_only', action='store_true',
                        help='run and print, but save nothing')
    parser.add_argument('--snapshot', type=Path, default=None,
                        help='default: the freshest available')
    parser.add_argument('--out', type=Path, default=None,
                        help=f'where to save (default {DEFAULT_STATE})')
    args = parser.parse_args(argv)

    if args.status:
        saved = status()
        if not saved['ran']:
            print(saved['note'])
            return 1
        print(render(saved['state']))
        print()
        print(f"saved state: {saved['path']}")
        return 0

    out = None if args.print_only else (args.out or state_path())
    outcome = run(args.snapshot or default_snapshot(), out)
    if not outcome['ok']:
        print(f"REFUSED: {outcome['error']}")
        return 2
    print(render(outcome['state']))
    if out is not None:
        print()
        print(f"saved -> {out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
