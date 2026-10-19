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
        history=_history_with_benchmark(points,point),
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


def _history_with_benchmark(points, point) -> dict:
    """The FR41 overlay: CSRS and official Nifty 500 returns on the same dates.

    This used to be `[{date, csrs}, ...]` -- a CSRS line, which is not the
    overlay FR41 describes ("overlay historical CSRS on benchmark Nifty 500
    returns to support visual back-testing"). The audit recorded the feature
    as absent, correctly.

    Returns a dict rather than a list so the renderer gets the series label,
    its source, the units of BOTH series and the coverage gaps alongside the
    rows. The units matter: a CSRS is a 0..1 score and a benchmark return is
    a return, so a chart cannot put them on one axis by accident.
    """
    from seraph.ingestion import benchmark_client

    rows = [dict(date=p['date'],
                 csrs=p['composite']['csrs'] if p['composite'] else None)
            for p in points if p['date'] <= point['date']]
    overlay = benchmark_client.align(rows)
    overlay['representativeness'] = benchmark_client.representativeness(rows)
    return overlay


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


#: Durable-workflow operations (T05/T08/T09). Kept in one table so the
#: dispatcher below stays readable and so a new operation cannot be added
#: without declaring the role that may invoke it.
#:
#: The defect these close is not a bug in `WorkspaceStore`, `ScenarioStore`
#: or `CaseStore` -- all three are implemented and tested. It is that nothing
#: in the dashboard ever CALLED them: around 1,300 lines of working
#: persistence with no route to a user. Portfolios lived in
#: `st.session_state`, scenarios were transient, and the regulator case
#: lifecycle had no caller at all.
WORKFLOW_ROLES = {
    # portfolios and watchlists — any role may own their own
    'ws_portfolios': ('retail', 'institutional', 'regulator'),
    'ws_create': ('retail', 'institutional', 'regulator'),
    'ws_preview': ('retail', 'institutional', 'regulator'),
    'ws_commit': ('retail', 'institutional', 'regulator'),
    'ws_holdings': ('retail', 'institutional', 'regulator'),
    'ws_snapshots': ('retail', 'institutional', 'regulator'),
    'ws_watchlist_save': ('retail', 'institutional', 'regulator'),
    'ws_watchlists': ('retail', 'institutional', 'regulator'),
    # scenarios — an institutional/regulator tool, as ScenarioStore enforces
    'sc_list': ('institutional', 'regulator'),
    'sc_save': ('institutional', 'regulator'),
    'sc_run': ('institutional', 'regulator'),
    'sc_compare': ('institutional', 'regulator'),
    'sc_review': ('institutional', 'regulator'),
    'sc_history': ('institutional', 'regulator'),
    'sc_export': ('institutional', 'regulator'),
    # cases — regulator only
    'case_list': ('regulator',),
    'case_open': ('regulator',),
    'case_evidence': ('regulator',),
    'case_decision': ('regulator',),
    'case_status': ('regulator',),
    'case_export': ('regulator',),
}


def _workflow(point, role, event):
    """Serve one durable-workflow operation, or `None` if `op` is not one.

    Every call resolves a `Principal` through the identity registry and the
    stores enforce their own authorisation on top of `WORKFLOW_ROLES` -- two
    independent checks, because the role in a browser event is a claim and
    `ScenarioStore.save` refusing a retail principal is the guarantee.
    """
    op = event.get('op')
    if op not in WORKFLOW_ROLES:
        return None
    if role not in WORKFLOW_ROLES[op]:
        raise ValueError(f'{op} is not available to the {role} role')

    from seraph.dashboard import workspace_service as svc
    from seraph.decision_support.scenarios import Assumption, baseline_from_point

    bundle = svc.stores()
    principal = svc.demo_principal(role, reg=bundle['registry'])
    workspace, scenarios, cases = (bundle['workspace'], bundle['scenarios'],
                                   bundle['cases'])
    identity = svc.describe()

    def ok(kind, value, **extra):
        return dict(kind=kind, value=value, identity=identity, **extra)

    # ---------------------------------------------------- T05 portfolios
    if op == 'ws_portfolios':
        return ok('ws_portfolios', workspace.portfolios(principal))
    if op == 'ws_create':
        name = str(event.get('name') or '').strip()
        if not 1 <= len(name) <= 120:
            raise ValueError('A portfolio needs a name of 1-120 characters')
        return ok('ws_create', workspace.create_portfolio(principal, name=name))
    if op == 'ws_preview':
        body = event.get('body')
        if not isinstance(body, str) or not body.strip():
            raise ValueError('Paste or upload CSV/JSON holdings first')
        if len(body) > 4_000_000:
            raise ValueError('That upload is larger than this release supports')
        preview = workspace.preview_import(
            principal, _require(event, 'portfolio_id'), body,
            source_name=str(event.get('source_name') or 'pasted.csv'))
        return ok('ws_preview', preview.describe())
    if op == 'ws_commit':
        body = event.get('body')
        if not isinstance(body, str) or not body.strip():
            raise ValueError('Nothing to commit; preview an import first')
        portfolio_id = _require(event, 'portfolio_id')
        # Re-parsed server side from the ORIGINAL bytes, never from the
        # preview the browser echoes back: a mutated preview must not be
        # able to turn an uploaded 100 into a stored 999 (P03).
        preview = workspace.preview_import(
            principal, portfolio_id, body,
            source_name=str(event.get('source_name') or 'pasted.csv'))
        saved = workspace.commit_import(
            principal, portfolio_id, preview, body,
            effective_at=str(event.get('effective_at') or _now_stamp()),
            note=event.get('note') or None)
        return ok('ws_commit', saved, rejected=len(preview.rejected))
    if op == 'ws_holdings':
        portfolio_id = _require(event, 'portfolio_id')
        as_of = event.get('as_of')
        value = (workspace.holdings_as_of(principal, portfolio_id, as_of)
                 if as_of else workspace.current_holdings(principal, portfolio_id))
        return ok('ws_holdings', value)
    if op == 'ws_snapshots':
        return ok('ws_snapshots',
                  workspace.snapshots(principal, _require(event, 'portfolio_id')))
    if op == 'ws_watchlist_save':
        items = event.get('items')
        if not isinstance(items, list) or len(items) > 500:
            raise ValueError('A watchlist is a list of at most 500 symbols')
        name = str(event.get('name') or '').strip() or 'default'
        return ok('ws_watchlist_save',
                  workspace.save_watchlist(principal, name,
                                           [str(i).upper()[:32] for i in items]))
    if op == 'ws_watchlists':
        return ok('ws_watchlists', workspace.watchlists(principal))

    # ----------------------------------------------------- T08 scenarios
    if op == 'sc_list':
        return ok('sc_list', scenarios.scenarios(principal))
    if op == 'sc_save':
        name = str(event.get('name') or '').strip()
        if not 1 <= len(name) <= 120:
            raise ValueError('A scenario needs a name of 1-120 characters')
        steps = event.get('steps')
        if not isinstance(steps, list) or not steps:
            raise ValueError('A scenario needs at least one step')
        raw = event.get('assumptions') or []
        if not isinstance(raw, list):
            raise ValueError('Assumptions must be a list')
        assumptions = [
            Assumption(key=str(a.get('key'))[:80], value=a.get('value'),
                       unit=str(a.get('unit') or 'rank')[:40],
                       justification=str(a.get('justification') or '')[:400],
                       source=(str(a['source'])[:200] if a.get('source') else None))
            for a in raw if isinstance(a, dict)]
        if not assumptions:
            raise ValueError(
                'A scenario must declare its assumptions: an unlabelled '
                'hypothetical cannot be told apart from a measurement later')
        return ok('sc_save', scenarios.save(
            principal, name=name, kind=str(event.get('kind') or 'rank_shock'),
            baseline=baseline_from_point(point), steps=steps,
            assumptions=assumptions))
    if op == 'sc_run':
        scenario_id = _require(event, 'scenario_id')
        saved = scenarios.scenario(principal, scenario_id)
        # Run the scenario's OWN stored steps through the same simulator the
        # transient tool uses, so a saved scenario and an ad-hoc shock cannot
        # diverge in arithmetic.
        results = _simulate_steps(point, saved['kind'], saved['steps'])
        return ok('sc_run', scenarios.record_run(
            principal, scenario_id, results=[r.model_dump(mode='json')
                                             for r in results],
            inputs=dict(steps=saved['steps'], kind=saved['kind'],
                        run_id=point['run_id'], date=point['date'])))
    if op == 'sc_compare':
        return ok('sc_compare', scenarios.compare(
            principal, _require(event, 'left_id'), _require(event, 'right_id')))
    if op == 'sc_review':
        verdict = event.get('verdict')
        if verdict not in ('approved', 'changes_requested', 'rejected'):
            raise ValueError('Unknown verdict')
        return ok('sc_review', scenarios.review(
            principal, _require(event, 'scenario_id'), verdict=verdict,
            comment=(str(event['comment'])[:2000] if event.get('comment') else None),
            assumption_version=event.get('assumption_version'),
            run_key=event.get('run_key')))
    if op == 'sc_history':
        scenario_id = _require(event, 'scenario_id')
        return ok('sc_history', dict(
            scenario=scenarios.scenario(principal, scenario_id),
            assumptions=scenarios.assumption_history(principal, scenario_id),
            runs=scenarios.runs(principal, scenario_id)))
    if op == 'sc_export':
        scenario_id = _require(event, 'scenario_id')
        return ok('sc_export', dict(
            scenario=scenarios.scenario(principal, scenario_id),
            assumption_history=scenarios.assumption_history(principal, scenario_id),
            runs=scenarios.runs(principal, scenario_id),
            exported_at=_now_stamp(), identity=identity,
            limitations=[
                'Scenario outputs are hypothetical pillar-rank arithmetic, '
                'not an economic forecast or a loss estimate.',
                identity['note']]),
            filename=f'seraph-scenario-{scenario_id}.json')

    # --------------------------------------------------------- T09 cases
    if op == 'case_list':
        return ok('case_list', cases.cases(principal, status=event.get('status')))
    if op == 'case_open':
        title = str(event.get('title') or '').strip()
        if not 3 <= len(title) <= 200:
            raise ValueError('A case needs a title of 3-200 characters')
        # Vocabulary comes from `cases.Priority`, not from this module: an
        # invented value here would be refused deeper down with a worse
        # message, or worse, accepted and stored.
        from seraph.decision_support.cases import PRIORITIES
        priority = event.get('priority') or 'medium'
        if priority not in PRIORITIES:
            raise ValueError(
                f"Unknown priority {priority!r}; this release uses "
                f"{', '.join(PRIORITIES)}")
        return ok('case_open', cases.open_case(
            principal, title=title, priority=priority,
            related=dict(run_id=point['run_id'], date=point['date'],
                         alert_id=f"{point['run_id']}:{point['date']}"),
            request_id=_require(event, 'id')))
    if op == 'case_evidence':
        from seraph.decision_support.cases import EvidenceRef
        refs = event.get('refs')
        if not isinstance(refs, list) or not refs:
            raise ValueError('Attach at least one evidence reference')
        pinned = []
        for r in refs:
            if not isinstance(r, dict):
                continue
            # `revision` is what makes replay honest (CaseStore's own words):
            # an evidence pointer with no revision can silently come back as
            # different content later, so it is required rather than defaulted.
            revision = str(r.get('revision') or '').strip()
            if not revision:
                raise ValueError(
                    'Each evidence reference needs a revision; an unpinned '
                    'pointer cannot be replayed honestly')
            pinned.append(EvidenceRef(
                kind=str(r.get('kind') or '')[:40],
                ref_id=str(r.get('ref_id') or '')[:200],
                revision=revision[:200],
                label=(str(r['label'])[:200] if r.get('label') else None),
                captured_at=_now_stamp()))
        if not pinned:
            raise ValueError('Attach at least one evidence reference')
        return ok('case_evidence', cases.attach_evidence(
            principal, _require(event, 'case_id'), pinned,
            expected_version=int(event.get('expected_version', 0)),
            request_id=_require(event, 'id')))
    if op == 'case_decision':
        rationale = str(event.get('rationale') or '').strip()
        if len(rationale) < 3:
            raise ValueError('A decision needs a recorded rationale')
        return ok('case_decision', cases.record_decision(
            principal, _require(event, 'case_id'),
            outcome=str(event.get('outcome') or '')[:80],
            rationale=rationale[:2000],
            action_category=(str(event['action_category'])[:80]
                             if event.get('action_category') else None),
            expected_version=int(event.get('expected_version', 0)),
            request_id=_require(event, 'id')))
    if op == 'case_status':
        # `CaseStore.TRANSITIONS` is the state machine and it refuses an
        # illegal MOVE with the permitted moves quoted. This only checks that
        # the status is a real one; which moves are legal from here is the
        # store's question, not this layer's, and duplicating that table would
        # be two maps to keep in step.
        from seraph.decision_support.cases import TRANSITIONS
        status = event.get('status')
        if status not in TRANSITIONS:
            raise ValueError(
                f"Unknown case status {status!r}; this release uses "
                f"{', '.join(sorted(TRANSITIONS))}")
        return ok('case_status', cases.set_status(
            principal, _require(event, 'case_id'), status=status,
            expected_version=int(event.get('expected_version', 0)),
            request_id=_require(event, 'id'),
            reason=(str(event['reason'])[:400] if event.get('reason') else None)))
    if op == 'case_export':
        case_id = _require(event, 'case_id')
        return ok('case_export', cases.export(principal, case_id),
                  filename=f'seraph-case-{case_id}.json')
    return None                                     # pragma: no cover


def _require(event, key):
    value = event.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} is required')
    return value.strip()[:200]


def _now_stamp() -> str:
    from datetime import datetime
    from seraph.shared_types import IST, ist_timestamp
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


def _weights_of(point):
    """The fusion weights this point was scored under, or refuse.

    Same check the ad-hoc shock path makes: reproducing a baseline under a
    DIFFERENT weight artefact would silently compare two things.
    """
    weights = InferenceSession([point['date']]).weights
    if weights.artefact_id != point['composite']['weights_artefact_id']:
        raise ValueError(
            'Saved weight version unavailable; cannot reproduce this baseline')
    return weights


def _simulate_steps(point, kind, steps):
    """One saved scenario's steps through the EXISTING simulators.

    A saved scenario and the transient shock tool must produce the same
    numbers from the same inputs, so this calls `simulate_shock` /
    `simulate_policy` with exactly the arguments the ad-hoc path uses rather
    than growing a second copy of the arithmetic. `xi=(1/3,)*3` and the
    `xi_mode='uniform'` relabelling below mirror that path deliberately: a
    saved rank shock is a sensitivity probe against a uniform regime
    baseline, not a regime forecast.
    """
    if not point.get('composite') or not point.get('reconciled'):
        raise ValueError('No baseline state available for this run/date')
    state = ReconciledState.model_validate(point['reconciled'])
    weights = _weights_of(point)
    first = next((s for s in steps if isinstance(s, dict)), None)
    if first is None:
        raise ValueError('This scenario has no usable step')

    if kind == 'regime_path':
        import math
        path = [tuple(s['xi']) for s in steps
                if isinstance(s, dict) and isinstance(s.get('xi'), list)]
        if not path:
            raise ValueError('A regime-path scenario needs at least one xi row')
        for row in path:
            if len(row) != 3 or abs(sum(row) - 1) > 1e-8 or any(
                    not isinstance(v, (int, float)) or not math.isfinite(v)
                    or v < 0 or v > 1 for v in row):
                raise ValueError(
                    'Every regime row must contain three probabilities '
                    'summing to one')
        return unwrap(simulate_policy(reconciled=state, weights=weights,
                                      xi_path=path))

    magnitude = float(first.get('delta') or first.get('magnitude') or 0.0)
    horizon = int(first.get('horizon') or 1)
    if not -1 <= magnitude <= 1 or not 1 <= horizon <= 60:
        raise ValueError('Shock must be within [-1,1]; horizon 1..60')
    results = unwrap(simulate_shock(
        reconciled=state, xi=(1 / 3,) * 3, weights=weights,
        pillar=str(first.get('pillar') or ''), magnitude=magnitude,
        horizon_days=horizon))
    return [r.model_copy(update={'xi_mode': 'uniform'}) for r in results]


def _dispatch(store, point, role, event):
    op=event.get('op')
    workflow=_workflow(point,role,event)
    if workflow is not None:
        return workflow
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
