"""C12 — fitted macro and historical defensive scenarios in the canonical UI (FR46–48)."""
from datetime import date, timedelta
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st


def render_run(run):
    st.caption(f"Saved execution {run.get('run_key', '')}")
    for result in run.get('results', []):
        if result.get('kind') == 'macro_path':
            st.caption(f"Fitted artifact {result['artifact_id']} · initial filtered state {result['initial_state_date']}")
            for warning in result.get('fit_warnings', []):
                st.warning(warning['message'])
            st.line_chart(pd.DataFrame(result['xi_path'], index=result['sessions'],
                                      columns=['Tranquil', 'Stressed', 'Crisis']))
            def score(row):
                return row.get('csrs', row.get('value'))
            st.line_chart(pd.DataFrame({'Scenario CSRS': [score(r) for r in result['score_path']],
                'Baseline CSRS': [score(r) for r in result['baseline_score_path']]}, index=result['sessions']))
            for note in result['limitations']:
                st.caption(note)
        elif result.get('kind') == 'defensive':
            st.caption(f"{result['epoch']} · {result['currency']} · {', '.join(result['evidence_modes'])}")
            paths = {'Buy-and-hold baseline': result['baseline']['wealth']}
            rows = []
            for action in result['actions']:
                if action['status'] == 'available':
                    paths[action['id']] = action['wealth']
                    rows.append(dict(action=action['id'], maximum_drawdown_pct=100*action['maximum_drawdown'],
                        reduction_percentage_points=action['reduction_percentage_points'],
                        transaction_cost=action['transaction_cost'], carry_cost=action['carry_cost']))
                else:
                    st.warning(f"{action['id']}: {action['reason']}")
            st.line_chart(pd.DataFrame(paths, index=result['valuation_times']))
            st.caption(f"Baseline maximum drawdown: {100*result['baseline']['maximum_drawdown']:.4f}%")
            st.dataframe(rows, hide_index=True)
            st.caption('Ex-post ranking among evaluated actions: '+', '.join(result['ex_post_ranking']))
            for note in result['limitations']:
                st.caption(note)
        else:
            st.write(result)
    with st.expander('Recorded inputs and complete result'):
        st.json(run)


def benchmark_request(*, epoch, start, end, initial_cash, fraction, cost_bps, cash_rate):
    from seraph.ingestion.benchmark_client import load, SERIES_SOURCE, NIFTY_500
    import hashlib
    rows = load(start=start, end=end)
    if len(rows) < 2:
        raise ValueError('The official benchmark has fewer than two observations in this interval')
    times = [r.date+'T15:30:00+05:30' for r in rows]
    return dict(epoch=epoch, currency='INR', valuation_times=times, decision_at=times[0],
        positions=[dict(instrument='NIFTY500', quantity=1.)], initial_cash=initial_cash,
        cash_rate_per_session=cash_rate,
        series={'NIFTY500': dict(kind='index', currency='INR', multiplier=1.,
            price_basis='official index close; conditional notional exposure, not an executable share',
            source=dict(path=SERIES_SOURCE, sha256=hashlib.sha256(NIFTY_500.read_bytes()).hexdigest()),
            mode='historical_observation', prices=[dict(at=t, price=r.close) for t,r in zip(times,rows)])},
        actions=[dict(id='reduce_to_cash', type='reduce_to_cash', execution_at=times[1],
            fraction=fraction, transaction_cost_bps=cost_bps, fixed_cost=0., carry_per_session=0.)])


def forms(send, report, *, point, role):
    if role not in ('institutional', 'regulator'):
        return
    with st.expander('Save a fitted macro-path scenario'):
        from seraph.pillars.hamilton.projection import reconstruct
        folder = Path(os.environ.get('SERAPH_HAMILTON_PROJECTIONS',
            Path(__file__).resolve().parents[2]/'prototype_runs/hamilton_projection'))
        files = sorted(p for p in folder.glob('*.json') if not p.name.startswith('observations-'))
        selected = st.selectbox('Fitted projection artifact', ['Upload JSON']+[p.name for p in files])
        upload = st.file_uploader('Projection artifact JSON', type=['json'], key='macro_artifact')
        try:
            artifact = (json.loads(upload.getvalue()) if selected=='Upload JSON' and upload else
                        json.loads((folder/selected).read_text()) if selected!='Upload JSON' else None)
            if artifact:
                reconstruct(artifact)
        except (ValueError, KeyError, OSError) as exc:
            st.warning(str(exc)); artifact = None
        if artifact is None:
            st.info('Select a persisted fit or upload its JSON. The source-checkout command scripts/export_hamilton_projection.py creates one from stored observations.')
        else:
            st.caption(f"Training ends {artifact['training_end']} · actual fitted covariates only")
            st.dataframe(artifact['covariates'], hide_index=True)
            for warning in artifact.get('input_manifest', {}).get('fit_warnings', []):
                st.warning(warning['message'])
            coverage = artifact.get('input_manifest', {}).get('macro_source', {}).get('coverage', {})
            if coverage.get('excluded_dates'):
                st.caption(f"Fit omitted {len(coverage['excluded_dates'])} dates without policy observations; transitions are between retained observation pairs.")
            start = max(date.fromisoformat(point['date']), date.fromisoformat(artifact['initial_state_date']))+timedelta(days=1)
            initial = [dict(session=start.isoformat(), **{c['name']:c['center'] for c in artifact['covariates']})]
            baseline = st.text_area('Baseline covariate path JSON', json.dumps(initial, indent=2), key='macro_baseline_'+artifact['artifact_id'])
            path = st.text_area('Hypothetical covariate path JSON', json.dumps(initial, indent=2), key='macro_path_'+artifact['artifact_id'])
            name = st.text_input('Macro scenario name')
            why = st.text_input('Macro assumptions and justification')
            retro = st.checkbox('Explicit retrospective hypothetical: permit a fit newer than the market baseline')
            if st.button('Save macro scenario'):
                try:
                    from seraph.pillars.hamilton.projection import project
                    if artifact['training_end'] > point['date'] and not retro:
                        raise ValueError('Select the explicit retrospective hypothetical option before saving a fit newer than the market baseline.')
                    rows, base = json.loads(path), json.loads(baseline)
                    project(artifact, rows); project(artifact, base)
                    result = send('sc_save', name=name, kind='macro_path',
                        steps=[dict(artifact=artifact, path=rows, baseline_path=base,
                            analysis_mode='retrospective_hypothetical' if retro else 'hypothetical')],
                        assumptions=[dict(key='covariate_path', value=rows, unit='named artifact units',
                            justification=why, source=artifact['artifact_id'])])
                    report(result, 'Saved fitted macro scenario.')
                    if not result.get('error'):
                        st.rerun()
                except (ValueError, KeyError, TypeError) as exc:
                    st.warning(str(exc))
    with st.expander('Save a defensive action comparison'):
        st.caption('Historical comparison under declared prices and costs. Saved results include the pinned pillar decomposition. Sector rotation, linear hedge and index-put paths accept supplied instrument histories.')
        mode = st.radio('Defensive inputs', ['Stored official NIFTY 500 history', 'Supplied request JSON'], horizontal=True)
        request = None
        if mode == 'Stored official NIFTY 500 history':
            from seraph.validation.epochs import EPOCH_BREAKS
            epoch = st.selectbox('Historical epoch', list(EPOCH_BREAKS), index=list(EPOCH_BREAKS).index('covid_2020'))
            start = st.date_input('Comparison begins', date.fromisoformat(EPOCH_BREAKS[epoch][0]), key='def_start_'+epoch)
            end = st.date_input('Comparison ends', start+timedelta(days=60), key='def_end_'+epoch)
            initial_cash = st.number_input('Initial cash (INR)', min_value=0., value=1000.)
            fraction = st.number_input('Fraction of index exposure sold to cash', min_value=0., max_value=1., value=.5)
            cost_bps = st.number_input('Transaction cost (basis points)', min_value=0., value=10.)
            cash_rate = st.number_input('Cash return per observed session', min_value=-.99, value=0., format='%.6f')
            st.caption('One notional index unit. Decision at first stored close; execution at the next stored close. No rebalancing, fixed fees or carry. Index exposure is hypothetical; the index prices are historical.')
            try:
                request = benchmark_request(epoch=epoch, start=start.isoformat(), end=end.isoformat(),
                    initial_cash=initial_cash, fraction=fraction, cost_bps=cost_bps, cash_rate=cash_rate)
            except ValueError as exc:
                st.info(str(exc))
        else:
            upload = st.file_uploader('Defensive request JSON', type=['json'], key='def_request')
            pasted = st.text_area('Or paste defensive request JSON', key='def_paste')
            try:
                request = json.loads(upload.getvalue() if upload else pasted) if upload or pasted else None
            except ValueError as exc:
                st.warning(str(exc))
        name = st.text_input('Defensive comparison name')
        why = st.text_input('Defensive assumptions and justification')
        if request:
            st.download_button('Download editable comparison inputs', json.dumps(request, indent=2),
                file_name='seraph-defensive-inputs.json', mime='application/json')
        if st.button('Save defensive comparison'):
            try:
                from seraph.decision_support.defensive import compare
                if request is None:
                    raise ValueError('Supply comparison inputs first')
                compare(request)
                result = send('sc_save', name=name, kind='defensive', steps=[dict(request=request)],
                    assumptions=[dict(key='execution_and_costs', value=request['actions'],
                        unit=request['currency'], justification=why)])
                report(result, 'Saved historical defensive comparison.')
                if not result.get('error'):
                    st.rerun()
            except (ValueError, KeyError, TypeError) as exc:
                st.warning(str(exc))
