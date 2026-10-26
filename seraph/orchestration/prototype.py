"""Canonical historical prototype: verified observations -> C8 -> C9 -> C11.

The archive input adapter reuses real fitted artifacts, never refits them or
claims they are live. New original-model observations can use the same step()
contract. Astra forecasts remain a separate channel, not extra CSRS pillars.

Input contract (docs/PRODUCT-CONTRACTS.md §3). Every entry of `originals` is
keyed by pillar and carries `score_eligible`; an eligible entry carries a
finite `value` and an IST `information_timestamp` (tau). An INELIGIBLE entry
must declare `absence` explicitly as 'structural' or 'transient' — the adapter
never guesses, because guessing 'structural' silently dropped a temporarily
unavailable pillar out of the D2 mask (audit finding A02).

Decision clock (FIX01). The decision timestamp comes from the session calendar,
not a hardcoded 15:30. An observation whose tau falls after the decision
timestamp is WITHHELD as a transient absence, never accepted and no longer
fatal; an observation dated after the decision session is still a hard error,
because nothing inside a session can carry a later date.
"""
from __future__ import annotations
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from seraph.market_calendar import DecisionClock, SessionCalendar
from seraph.orchestration.run_store import RunStore
from seraph.orchestration.standardize import standardise
from seraph.reconciliation.kalman import KalmanReconciler
from seraph.fusion.score import score
from seraph.shared_types import (CalibrationConfig, FusionWeights, ObservedEmission,
    PillarObservation, UnavailableEmission)
from seraph.shared_types.fusion import fusion_weights_artefact_id
from seraph.decision_support import explain, portfolio_overlay

ROOT = Path(__file__).resolve().parents[2]
ORDER = ('hawkes','rmt','hamilton')
ABSENCE_KINDS = ('structural','transient')
#: UnavailableEmission.reason is a frozen shared_types Literal. Finer-grained
#: adapter reasons map onto it here and keep their exact wording in the
#: persisted payload and in `limitations`, rather than widening a frozen type.
ABSENCE_REASONS = ('no_data_coverage','estimation_failed','insufficient_history')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value, (list,tuple,np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (np.floating,float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (pd.Timestamp,datetime,date)):
        return value.isoformat()
    if isinstance(value,np.bool_):
        return bool(value)
    return value


class InferenceSession:
    """Chronological step API shared by archive replay and future adapters.

    Restart is deterministic replay from immutable input, not unversioned
    deserialization of mutable estimator internals.
    """
    def __init__(self, calendar, *, decision_clock=None, reconciliation_mode="kalman"):
        dates = [date.fromisoformat(d) for d in calendar]
        self.clock = decision_clock or DecisionClock(
            SessionCalendar(session_dates=frozenset(calendar)))
        self.filter = KalmanReconciler(session_dates=dates, mode=reconciliation_mode,
            session_hours=self.clock.calendar.hours_map())
        self.history = {p:[] for p in ORDER}
        self.last = None
        w = ((1/3,1/3,1/3),)*3
        cfg = CalibrationConfig(epochs=(),kappa_miss=1,kappa_fa=1,mask_profile=(True,True,False))
        self.weights = FusionWeights(artefact_id=fusion_weights_artefact_id(w,cfg),calibrated_on=cfg,w=w)

    def step(self, day, originals, predictions, *, run_id, holdings=None):
        if self.last is not None and day <= self.last:
            raise ValueError('Inference requires strictly increasing session dates')
        ts = self.clock.decision_timestamp(day)
        # Validate the entire batch before changing ECDF/filter state.
        withheld = {}
        for pillar, item in originals.items():
            if item.get('score_eligible'):
                if item.get('value') is None or not np.isfinite(item['value']):
                    raise ValueError('Non-finite eligible pillar value')
                tau = item.get('information_timestamp')
                if not tau:
                    raise ValueError('Eligible pillar observation needs an information timestamp')
                if tau[:10] > day:
                    # A later DATE can never belong to this session: adapter bug.
                    raise ValueError(f'{pillar}: observation dated after the decision session')
                if datetime.fromisoformat(tau) > datetime.fromisoformat(ts):
                    # FIX01: a same-session vintage that has not arrived yet at
                    # this decision time. Withheld, not assimilated, not fatal.
                    withheld[pillar] = tau
            elif item.get('absence') not in ABSENCE_KINDS:
                raise ValueError(
                    f"{pillar}: an ineligible pillar must declare absence as one of "
                    f"{ABSENCE_KINDS}; absence type is never inferred (FIX02)")
            elif item.get('absence_reason', 'no_data_coverage') not in ABSENCE_REASONS:
                raise ValueError(f'{pillar}: absence_reason must be one of {ABSENCE_REASONS}')
        emissions, issues = [], []
        for pillar in ORDER:
            item = originals[pillar]
            if item.get('score_eligible') and item.get('value') is not None and pillar not in withheld:
                tau = item['information_timestamp']
                past = self.history[pillar]
                lower = f'{int(day[:4])-5:04d}'+day[4:]
                past[:] = [(d,v) for d,v in past if d[:10] >= lower]
                rank,var,warnings = standardise(item['value'],window=[v for _,v in past],
                    raw_variance=item.get('variance'),pillar=pillar)
                emissions.append(ObservedEmission(obs=PillarObservation(
                    pillar=pillar,ts=ts,tau=tau,value=rank,estimation_variance=var)))
                if not past or past[-1][0] < tau:
                    past.append((tau,item['value']))
                issues.extend(w.message for w in warnings)
            elif pillar in withheld:
                # Stays in the mask: the pillar exists, this vintage is simply
                # not available yet at the decision time. D4 inflates its age.
                emissions.append(UnavailableEmission(pillar=pillar,ts=ts,absence='transient',
                    reason='no_data_coverage'))
                issues.append(f'{pillar}: vintage {withheld[pillar]} is later than the '
                              f'decision timestamp {ts}; withheld as not yet available')
            else:
                emissions.append(UnavailableEmission(pillar=pillar,ts=ts,
                    absence=item['absence'],
                    reason=item.get('absence_reason','no_data_coverage')))
                issues.append(f"{pillar}: {item.get('reason','unavailable')} "
                              f"[{item['absence']}]")
        state = self.filter.update(emissions)
        if state.status != 'ok':
            raise ValueError(str(state.error))
        issues.extend(w.message for w in state.warnings)
        # Preserve the documented original-Hamilton unavailability decision.
        # Its causal research diagnostics are displayed but never silently
        # promoted to a validated regime weighting.
        result = score(reconciled=state.value,xi=(1/3,1/3,1/3),weights=self.weights,xi_mode='uniform')
        point = result.value if result.status == 'ok' else None
        if point is None:
            issues.append('CSRS unavailable: no eligible original pillar observations')
        portfolio = None
        if holdings is not None:
            overlay = portfolio_overlay(holdings,None)
            if overlay.status == 'ok':
                portfolio = overlay.value
                issues.extend(w.message for w in overlay.warnings)
            else:
                issues.append('Portfolio: '+str(overlay.error))
        self.last = day
        session = self.clock.calendar.session(day)
        # The persisted record must not claim an eligible observation whose
        # vintage was withheld. Record the withheld vintage separately and
        # mark the entry ineligible, without mutating the caller's input.
        recorded = dict(originals)
        for pillar, tau in withheld.items():
            entry = dict(recorded[pillar])
            entry.update(score_eligible=False, value=None, information_timestamp=None,
                         absence='transient', absence_reason='no_data_coverage',
                         withheld_vintage=tau, withheld_value=recorded[pillar].get('value'),
                         withheld_reason='not_yet_available at the decision timestamp',
                         reason=f'vintage {tau} arrives after the decision timestamp {ts}')
            recorded[pillar] = entry
        return clean(dict(run_id=run_id,date=day,evaluation_timestamp=ts,
            data_cutoff=ts,original_pillars=recorded,astra_predictions=predictions,
            reconciled=state.value.model_dump(),composite=point.model_dump() if point else None,
            warning_status='experimental thresholds; advance-warning skill unvalidated',
            explanation=explain(point).value if point else None,portfolio=portfolio,
            session=dict(kind=session.kind,windows=[list(w) for w in session.windows],
                close=session.close,decision_policy=self.clock.policy,
                evidence_status=session.evidence_status),
            coverage=dict(mask=list(state.value.mask),degraded=not all(state.value.mask),
                absence={p:('withheld_not_yet_available' if p in withheld
                            else None if originals[p].get('score_eligible')
                            and originals[p].get('value') is not None
                            else originals[p].get('absence')) for p in ORDER},
                sector_flags='unavailable',portfolio_basis='current supplied holdings; not historical'),
            errors=[],limitations=sorted(set(issues))))


def load_archive(root=ROOT):
    root=Path(root)
    data=root/'research_data'; results=root/'research_results/v1_verified'
    manifest=json.loads((data/'manifest.json').read_text())
    provenance=json.loads((results/'provenance.json').read_text())
    sources={}
    for base,entries in [(data,manifest['files']),(results,provenance['outputs']),
                         (root,provenance['code_hashes'])]:
        for name,expected in entries.items():
            path=base/Path(name.replace('\\','/'))
            if sha(path)!=expected:
                raise ValueError(f'Archive integrity mismatch: {name}')
            sources[str(path.relative_to(root))]=expected
    market=pd.read_parquet(data/'market_snapshot.parquet')
    rmt=pd.read_parquet(data/'original_rmt.parquet')
    hawkes=pd.read_parquet(data/'original_hawkes.parquet')
    forecast=pd.read_parquet(results/'predictions.parquet')
    for frame in (market,rmt,forecast):
        frame['date']=pd.to_datetime(frame['date']).dt.strftime('%Y-%m-%d')
    if market.date.duplicated().any() or not market.date.is_monotonic_increasing:
        raise ValueError('Market session axis must be unique and ordered')
    if forecast.duplicated(['date','target','model']).any() or rmt.date.duplicated().any():
        raise ValueError('Duplicate source identities')
    index={d:i for i,d in enumerate(market.date)}
    for row in forecast.itertuples():
        if np.isfinite(row.probability):
            lag=1 if row.model in ('gjr_garch_t','ewma_student_t') else 15
            if row.train_end>=0 and row.train_end>index[row.date]-lag:
                raise ValueError('Forecast fit crosses information cutoff')
    hawkes['information_timestamp']=pd.to_datetime(hawkes.ts,utc=True).dt.tz_convert('Asia/Kolkata').map(lambda x:x.isoformat())
    hawkes['date']=hawkes.information_timestamp.str[:10]
    hdir=root/'docs/evidence/20261013T023028Z-hamilton-causal-POSTFIX'
    hpath=hdir/'causal_xi_NOT_PRODUCTION.npz'
    hmeta=hdir/'causal_run.json'
    sources[str(hpath.relative_to(root))]=sha(hpath)
    sources[str(hmeta.relative_to(root))]=sha(hmeta)
    with np.load(hpath,allow_pickle=False) as z:
        ham=pd.DataFrame(dict(date=z['dates'],lsd=z['lsd'],xi1=z['xi'][0],xi2=z['xi'][1],xi3=z['xi'][2]))
    # Source is a labelled causal research archive, not the smoothed E8 table.
    return market,rmt,hawkes,ham,forecast,sources,manifest


def run_archive(store_path, *, start='2020-01-01', end='2020-04-30', root=ROOT, holdings=None,
                decision_policy='session_close'):
    market,rmt,hawkes,ham,forecast,sources,data_manifest=load_archive(root)
    dates=market.date.tolist()
    if start>end or end>dates[-1] or not any(start<=d<=end for d in dates):
        raise ValueError('Requested range is empty or beyond verified data cutoff')
    calendar=SessionCalendar(session_dates=frozenset(dates))
    clock=DecisionClock(calendar,policy=decision_policy)
    code={str(p.relative_to(root)):sha(p) for p in sorted((Path(root)/'seraph').rglob('*.py'))}
    manifest=dict(format_version=1,mode='verified historical artifact replay',
        start=start,end=end,data_available_through=dates[-1],data_provenance=data_manifest,
        sources=sources,code_hashes=code,holdings=holdings,
        decision_clock=clean(clock.describe()),
        inference=dict(pillars=list(ORDER),rmt_quantity='lambda_1/N (existing research adapter)',
            hamilton='causal diagnostics retained; not eligible for original fusion',
            weights='equal-weight uncalibrated research baseline',xi_mode='uniform',
            amber=.5,red=.75,
            clock='observed trading sessions; session-aware decision timestamps',
            hawkes_selection='as-of: latest refit whose information timestamp is at or '
                             'before the decision timestamp'),
        executed=['artifact ingestion','C8 reconciliation','C9 fusion','C11 explanations/coverage'],
        reused=['original C5/C6/C7 historical estimates','Astra future-target forecasts'],
        skipped=[dict(component='fresh original-pillar fitting',reason='raw source DB unavailable in offline archive mode'),
                 dict(component='PostgreSQL E1-E14 persistence',reason='local prototype store is separate'),
                 dict(component='production sector flags',reason='no measured source')],
        scientific_status='experimental; no established crisis-warning edge')
    store=RunStore(store_path); run_id=store.begin(manifest)
    rmap=rmt.set_index('date').to_dict('index'); hmap=ham.set_index('date').to_dict('index')
    pmap={d:g for d,g in forecast.groupby('date')}
    # FIX01 as-of selection: Hawkes refits are an irregular vintage stream, not
    # a per-session table. Order them by information timestamp and advance a
    # pointer to the latest vintage available at each decision timestamp. A
    # later same-session refit (e.g. a Muhurat evening fit) is simply not yet
    # reachable at an earlier decision clock, and the previous vintage stands.
    vintages=sorted(((row['information_timestamp'],row) for row in
                     hawkes.to_dict('records')),key=lambda item:item[0])
    rmt_first_date=min(rmap) if rmap else None
    session_obj=InferenceSession(dates,decision_clock=clock)
    cursor=0; count=0; persisted=[]
    for day in dates:
        if day>end: break
        decision=clock.decision_timestamp(day)
        while cursor<len(vintages) and vintages[cursor][0]<=decision:
            cursor+=1
        last_hawk=vintages[cursor-1][1] if cursor else None
        pending=(vintages[cursor][0] if cursor<len(vintages)
                 and vintages[cursor][0][:10]==day else None)
        r=rmap.get(day); h=hmap.get(day)
        tau_daily=calendar.close_timestamp(day)
        hawkes_entry=dict(model='original discrete intraday Hawkes',origin='verified fitted archive',
            score_eligible=last_hawk is not None,
            value=(last_hawk['branching_ratio_n']/(1-last_hawk['branching_ratio_n'])) if last_hawk else None,
            information_timestamp=last_hawk['information_timestamp'] if last_hawk else None,
            detail=last_hawk,reason='no fitted intraday estimate available at this decision time',
            selection='as-of latest vintage at or before the decision timestamp')
        if pending:
            hawkes_entry['withheld_vintage']=pending
            hawkes_entry['withheld_note']=('a later refit exists for this session but arrives '
                                           f'after the decision timestamp {decision}')
        if last_hawk is None:
            hawkes_entry.update(absence='structural',absence_reason='insufficient_history',
                reason='no fitted intraday estimate exists on or before this decision time')
        rmt_entry=dict(model='original cross-sectional RMT',origin='verified fitted archive',
            score_eligible=r is not None,value=r['lam1_share'] if r else None,
            information_timestamp=tau_daily,detail=r,
            reason='no RMT observation on this session')
        if r is None:
            # Before coverage begins the estimate cannot exist (structural); a
            # gap inside coverage is a failed update, so the pillar stays in
            # the mask and D4 inflates its age (transient).
            structural=rmt_first_date is None or day<rmt_first_date
            rmt_entry.update(
                absence='structural' if structural else 'transient',
                absence_reason='insufficient_history' if structural else 'estimation_failed',
                reason='no RMT history before coverage begins' if structural
                       else 'RMT estimate missing inside its covered range')
        originals={'hawkes':hawkes_entry,'rmt':rmt_entry,
            'hamilton':dict(model='original multivariate TVTP Hamilton',origin='causal research archive NOT_PRODUCTION',
                score_eligible=False,value=None,information_timestamp=tau_daily,detail=h,
                absence='structural',absence_reason='no_data_coverage',
                exclusion='standing research decision (NOT_PRODUCTION); not a feed outage',
                reason='regime support unvalidated; diagnostic only, existing exclusion preserved')}
        predictions=[]
        if day in pmap:
            # Realised outcomes are evaluation-only and never enter inference.
            predictions=pmap[day].drop(columns=['label']).to_dict('records')
        point=session_obj.step(day,originals,predictions,run_id=run_id,holdings=holdings)
        if day>=start:
            store.put(run_id,point); persisted.append(day); count+=1
    # FIX03: seal against the exact expected date set, and withhold completion
    # until the required comparison report exists.
    store.finish(run_id,persisted,requires_report=True)
    selected=forecast[forecast.date.between(start,end)]
    comparison=[]
    from seraph.validation.harness import auc
    common={}
    for target,group in selected.groupby('target'):
        supports=[set(g.dropna(subset=['probability','label']).date) for _,g in group.groupby('model')]
        common[target]=set.intersection(*supports) if supports else set()
    for (target,model),g in selected.groupby(['target','model']):
        valid=g[g.date.isin(common[target])].dropna(subset=['probability','label'])
        comparison.append(dict(target=target,model=model,n=len(valid),
            coverage_basis='common dates across all displayed models for this target',
            brier=float(((valid.probability-valid.label)**2).mean()) if len(valid) else None,
            auc=float(auc(valid.probability.to_numpy(),valid.label.to_numpy())) if len(valid) and valid.label.nunique()==2 else None))
    report=clean(dict(run_id=run_id,points=count,database=str(Path(store_path).resolve()),
        status='complete historical artifact replay; fresh original-model execution not verified',
        retrospective_comparison=comparison))
    store.report(run_id,report)
    return report


async def run_source_endpoint(store_path, source_dsn, day, holdings=None):
    """Explicit fresh-source mode; never substitutes an archive on failure."""
    import asyncpg
    from seraph.orchestration.original_execution import execute_originals
    conn=await asyncpg.connect(source_dsn,timeout=5,server_settings={
        'default_transaction_read_only':'on','timezone':'Asia/Kolkata'})
    try:
        async with conn.transaction(readonly=True,isolation='repeatable_read'):
            originals,audit=await execute_originals(conn,day)
            source_identity=await conn.fetchval('SELECT current_database()')
    finally:
        await conn.close()
    code={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'seraph').rglob('*.py'))}
    manifest=clean(dict(format_version=1,mode='fresh original-model endpoint',start=day,end=day,
        data_available_through=day,source_database=source_identity,source_audit=audit,
        code_hashes=code,holdings=holdings,scientific_status='unvalidated',
        skipped=['Astra forecasts beyond the archived experiment require an independent forecast run']))
    store=RunStore(store_path);run_id=store.begin(manifest)
    # No invented ECDF warmup: fresh endpoint diagnostics are persisted, but
    # cannot become a calibrated composite using a single observation. The
    # standardised rank cannot exist for this period in this mode, so the
    # absence is structural — the pillar leaves the D2 mask and the composite
    # is withheld, exactly as documented. It is not a feed outage.
    for p in originals.values():
        if p['score_eligible']:
            p['score_eligible']=False
            p['reason']='fresh model executed; chronological ECDF warmup not yet available in endpoint mode'
        p['absence']='structural'
        p['absence_reason']=p.get('absence_reason') or 'insufficient_history'
    result=InferenceSession([day]).step(day,originals,[],run_id=run_id,holdings=holdings)
    result['limitations'].extend(audit['limitations'])
    result['errors']=audit['errors']
    store.put(run_id,result);store.finish(run_id,[day])
    return dict(run_id=run_id,points=1,status='fresh model diagnostics; composite warmup remains incomplete')
