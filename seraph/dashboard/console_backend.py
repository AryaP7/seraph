"""C12 role projection and C11 interaction adapter (FR42-FR49).

Local role switching is a demonstration, not authenticated identity. Nevertheless
restricted fields are omitted at the Python-to-browser boundary.
"""
from seraph.dashboard.gateway import build_view, ROLE_FIELDS
from seraph.dashboard.globe_payload import build_globe_payload
from seraph.dashboard.news_view import build_news_payload
from seraph.shared_types import CsrsPoint, ReconciledState
from seraph.decision_support import playbook, portfolio_overlay, simulate_shock, simulate_policy
from seraph.orchestration.prototype import InferenceSession, clean


def unwrap(result):
    if result.status != 'ok':
        raise ValueError(str(result.error))
    return result.value


def liveness_of(point, *, feed=None, mode=None, warmup_complete=False):
    """Is this score a current market reading, or a replay?

    T01 / audit finding R02. The previous version judged currency from the
    point's *evaluation timestamp*, so a synthetic recent archive point
    displayed `CURRENT MARKET READING` while its own payload said no feed was
    configured. Evaluation time is not observation provenance.

    Currency now comes from the same `assess_publication` gate the live worker
    uses, with the feed's real provenance. A run read out of an archive store
    has no live feed by construction, so it can never be labelled current —
    which is the correct answer for every run this product can show today.
    """
    from datetime import datetime

    from seraph.live import MarketClock
    from seraph.live.publication import (
        FeedProvenance,
        InputProvenance,
        assess_publication,
        explain,
    )
    from seraph.shared_types import IST

    clock = MarketClock()
    observed = point.get('evaluation_timestamp')
    recency = clock.recency(observed)
    market = clock.state()
    now = datetime.now(IST).replace(microsecond=0)

    provenance = feed or FeedProvenance()          # no feed => unverified
    # A persisted archive point is a replay unless a live worker says so.
    resolved_mode = mode or ('live_shadow' if provenance.connected
                             and provenance.authenticated else 'historical_replay')
    assessment = assess_publication(
        mode=resolved_mode, csrs=point.get('composite'), feed=provenance,
        as_of=datetime.fromisoformat(observed) if observed else now, now=now,
        warmup_complete=warmup_complete,
        calendar_verified=not clock.calendar.completeness()[
            'completeness'].startswith('PARTIAL'),
        required_inputs=(InputProvenance(
            name='market_observation',
            observed_at=datetime.fromisoformat(observed) if observed else None,
            received_at=datetime.fromisoformat(observed) if observed else None,
            mandatory=True),),
        has_eligible_information=bool(point.get('composite')))

    return dict(
        is_live=assessment.current_allowed,
        publishable_as_current=assessment.current_allowed,
        recency=recency.state,
        age_minutes=recency.age_minutes,
        observed_at=observed,
        now=recency.now,
        market_state=market['state'],
        next_open=market.get('next_open'),
        feed=(f"{provenance.source_kind} — "
              f"{'connected' if provenance.connected else 'not connected'}"
              f"{'' if provenance.authenticated else ', unauthenticated'}"),
        mode=resolved_mode,
        headline=assessment.label,
        reasons=list(assessment.reasons),
        why=explain(assessment),
        note=recency.note)


def result_matches(result, run_id, date, role):
    """FIX11: a result belongs to the exact context that produced it.

    A response that arrives after the user changed run, date or role describes
    a state that is no longer on screen. It is discarded rather than rendered
    beside a different selection. A result with no context is legacy-shaped and
    is treated as non-matching, because its provenance cannot be established.
    """
    context = (result or {}).get('context')
    if not isinstance(context, dict):
        return False
    return (context.get('run_id') == run_id and context.get('date') == date
            and context.get('role') == role)


#: The renderer's own geometry vocabulary, read once from the component it
#: ships with, so the adapter cannot name a mesh the browser does not have.
_RENDERER_GEOMETRY: dict | None = None


def renderer_geometry():
    """`(state_meshes, country_meshes)` parsed from the console component.

    Hardcoding the list here would let it drift from the geometry the browser
    actually draws; reading it from the same file the browser loads cannot.
    """
    global _RENDERER_GEOMETRY
    if _RENDERER_GEOMETRY is None:
        import json as _json
        from pathlib import Path as _Path
        source = (_Path(__file__).parent / 'console_component' / 'index.html'
                  ).read_text(encoding='utf-8')
        start = source.index('var DATA = ')
        line = source[start + len('var DATA = '):source.index(chr(10), start)]
        data = _json.loads(line.rstrip().rstrip(';'))
        _RENDERER_GEOMETRY = dict(
            states=tuple(sorted({s['n'] for s in data.get('india', [])})),
            countries=tuple(sorted({c['i'] for c in data.get('world', [])})))
    return _RENDERER_GEOMETRY['states'], _RENDERER_GEOMETRY['countries']


def news_branch(point, *, store=None, master=None, preview=None,
                role='retail', hawkes_sector_flags=None, news_mode='historical_decision',
                news_as_of=None, news_offset=0, portfolio=None):
    """T13 — the `news` transport branch, or an explicit statement of absence.

    The console used to carry one flat string for every news surface at once
    (`news_status='FABRICATED PREVIEW'`), which made a connected surface
    indistinguishable from an unconnected one. Status is now per surface and
    per record, and comes from the data rather than from a constant.

    With no news store or registry attached this returns `status='absent'`
    naming what is missing — not a preview pretending to be a channel.
    """
    if store is None or master is None:
        return dict(
            status='absent', version=None,
            reason=('no news store or curated registry is attached to this '
                    'projection; the illustrative map layer is all that is '
                    'shown and it is labelled FABRICATED'),
            surfaces={}, preview_only=True)
    if news_mode not in ('historical_decision', 'current_news'):
        raise ValueError('Unknown news mode')
    if news_mode == 'current_news':
        from seraph.news.acquisition import _now
        clock = news_as_of or _now()
    else:
        clock = point['evaluation_timestamp']
        if news_as_of is not None and news_as_of != clock:
            raise ValueError('historical news clock differs from market decision')
    states, countries = renderer_geometry()
    payload = build_news_payload(
        store, master, decision_ts=clock, offset=news_offset,
        hawkes_sector_flags=hawkes_sector_flags,
        # The role asks a different question of the same facts; the holdings
        # are what make the retail answer specific rather than generic.
        role=role, holdings=portfolio, strict_replay=news_mode == 'historical_decision')
    globe = build_globe_payload(
        payload, master, revision=point['run_id'],
        as_of=clock,
        state_meshes=states, country_meshes=countries, preview=preview,
        role=role)
    context = dict(run_id=point['run_id'], date=point['date'], role=role,
                   news_mode=news_mode, news_as_of=clock,
                   market_as_of=point['evaluation_timestamp'])
    globe['context'] = context
    snapshot_id = None
    if news_mode == 'current_news':
        snapshot_id = store.save_snapshot(dict(context=context, payload=payload, globe=globe),
                                          available_at=clock, method=payload['version'])
    return dict(
        context=context, mode=news_mode, as_of=clock, snapshot_id=snapshot_id,
        pagination=payload.get('pagination'), source_coverage=payload['source_coverage'],
        # This dict is an EXPLICIT allow-list, so a new payload field reaches
        # the UI only by being named here. `freshness` carries worker liveness
        # and data age, and omitting it meant the console could not tell a
        # stopped worker from a quiet market however correct the payload was.
        freshness=payload.get('freshness'),
        role_view=payload.get('role_view'),
        # The pinned source/extractor/registry versions and whether this is
        # a reconstruction or a replay. Named here deliberately: the method
        # panel is where a reader asks what produced the numbers, and it
        # could previously only answer with a hard-coded sentence.
        manifest=payload.get('manifest'),
        temporal_policy=payload.get('temporal_policy'),
        status='connected' if payload['connected_surfaces'] else 'empty',
        version=payload['version'],
        connected_surfaces=payload['connected_surfaces'],
        preview_surfaces=payload['preview_surfaces'],
        surfaces=payload['surfaces'], registry=payload['registry'],
        globe=globe, preview_only=not payload['connected_surfaces'],
        reason=(None if payload['connected_surfaces'] else
                'the news store holds nothing visible at this decision time'))


def project_run(point, manifest, points, role, *, log=None, portfolio=None,
                result=None, report=None, news_store=None, news_master=None,
                news_preview=None, news_mode="historical_decision", news_as_of=None, news_offset=0):
    if role not in ROLE_FIELDS:
        raise ValueError('Unknown role')
    if any(p['run_id'] != point['run_id'] for p in points):
        raise ValueError('Mixed runs')
    stale_result = None
    if result and not result_matches(result, point['run_id'], point['date'], role):
        stale_result = dict(
            discarded=True,
            reason='this result was produced for a different run, date or role '
                   'and is not shown beside the current selection',
            produced_for=(result or {}).get('context'))
        result = None
    if result and ((result.get('kind') in ('action','policy') and role!='regulator') or (result.get('kind')=='shock' and role=='retail')):
        stale_result = dict(discarded=True,
                            reason='this operation is not available to the current role')
        result=None
    score = point['composite']
    if score:
        view = unwrap(build_view(role, CsrsPoint.model_validate(score),
            explanation=(point.get('explanation') or {}).get('sentence',''),
            pillar_scores=point['original_pillars'],
            spectral=point['original_pillars'].get('rmt',{}).get('detail',{}),
            action_log=log if role=='regulator' else None,
            playbook=unwrap(playbook(point['explanation']['dominantPillar']))))
    else:
        view = dict(role=role,csrs=None,alertLevel='unavailable',explanation='No composite: original inputs unavailable.',maskDegraded=True)
    payload = dict(run_id=point['run_id'],date=point['date'],timestamp=point['evaluation_timestamp'],
        cutoff=point['data_cutoff'],mode=manifest['mode'],role=role,view=view,
        history=[dict(date=p['date'],csrs=p['composite']['csrs'] if p['composite'] else None)
                 for p in points if p['date']<=point['date']],
        portfolio=portfolio if portfolio is not None else point.get('portfolio'),
        news=news_branch(point, store=news_store, master=news_master,
                         preview=news_preview, role=role, news_mode=news_mode,
                         news_as_of=news_as_of, news_offset=news_offset,
                         # The retail view is only specific if it knows what
                         # the user holds; without it every holding would be
                         # reported as uncovered, which is true but useless.
                         portfolio=portfolio),
        warning_status=point.get('warning_status'),result=result,
        liveness=liveness_of(point),
        discarded_result=stale_result,
        context=dict(run_id=point['run_id'],date=point['date'],role=role))
    if role != 'retail':
        payload.update(pillars=point['original_pillars'],predictions=point['astra_predictions'],
                       limitations=point['limitations'],report=report,
                       mask=score['mask'] if score else [False]*3)
    if role == 'regulator':
        payload.update(manifest=manifest,action_log=log or [])
    return clean(payload)


def dispatch(store, point, role, event):
    """Validate UI context and permission again before any computation/write."""
    if role not in ROLE_FIELDS:
        raise ValueError('Unknown role')
    if event.get('run_id') != point['run_id'] or event.get('date') != point['date']:
        raise ValueError('Stale request: select the current run/date and retry')
    # FIX11: every result carries the context it was produced for, so a late
    # response can be matched against the selection on arrival.
    context=dict(run_id=point['run_id'],date=point['date'],role=role,
                 request_id=event.get('id'))
    return dict(_dispatch(store,point,role,event),context=context)


def _dispatch(store, point, role, event):
    op=event.get('op')
    if op=='portfolio':
        holdings=event.get('holdings')
        if not isinstance(holdings,list) or len(holdings)>10000:
            raise ValueError('Provide a JSON list of at most 10000 holdings')
        # News preview flags never enter measured portfolio arithmetic.
        return dict(kind='portfolio',value=unwrap(portfolio_overlay(holdings,{})),basis='User supplied current holdings; measured sector flags unavailable')
    if op=='action':
        if role!='regulator': raise ValueError('Regulator role required')
        if not point['composite']: raise ValueError('No scored alert to annotate')
        request_id=event.get('id')
        if not isinstance(request_id,str) or not 1<=len(request_id)<=128: raise ValueError('Invalid request ID')
        value=store.action(point['run_id'],request_id,role,event.get('operation'),
            alert_id=point['run_id']+':'+point['date'],action=event.get('action'),
            decomposition=tuple(point['composite']['shapley']),at=point['evaluation_timestamp'])
        return dict(kind='action',value=value)
    if op not in ('shock','policy'): raise ValueError('Unknown operation')
    if role=='retail': raise ValueError('Institutional or regulator role required')
    if op=='policy' and role!='regulator': raise ValueError('Regulator role required for policy scenario')
    if not point.get('composite') or not point.get('reconciled'): raise ValueError('No baseline state available')
    state=ReconciledState.model_validate(point['reconciled'])
    weights=InferenceSession([point['date']]).weights
    if weights.artefact_id != point['composite']['weights_artefact_id']:
        raise ValueError('Saved weight version unavailable; cannot reproduce this baseline')
    if op=='shock':
        magnitude=float(event['magnitude']);horizon=int(event['horizon'])
        if not -1<=magnitude<=1 or not 1<=horizon<=60: raise ValueError('Shock must be within [-1,1]; horizon 1..60')
        results=unwrap(simulate_shock(reconciled=state,xi=(1/3,)*3,weights=weights,
            pillar=event['pillar'],magnitude=magnitude,horizon_days=horizon))
        note='Hypothetical rank shock through existing C11/C9, not a forecast. Excluded pillars remain excluded.'
    else:
        path=event.get('xi_path')
        if not isinstance(path,list) or not 1<=len(path)<=60: raise ValueError('Provide 1..60 regime probability rows')
        import math
        if any(not isinstance(row,list) or len(row)!=3 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or v>1 for v in row) or abs(sum(row)-1)>1e-8 for row in path):
            raise ValueError('Every regime row must contain three probabilities summing to one')
        results=unwrap(simulate_policy(reconciled=state,weights=weights,xi_path=[tuple(x) for x in path]))
        note='Explicit hypothetical regime path, not a fitted macro-policy forecast. Equal regime weights can make the result unchanged. Macro z-to-xi mapping remains unavailable.'
    return dict(kind=op,value=[(r.model_copy(update={'xi_mode':'uniform'}) if op=='shock' else r).model_dump(mode='json') for r in results],basis=note,regime_source='uniform baseline' if op=='shock' else 'user-supplied hypothetical path')
