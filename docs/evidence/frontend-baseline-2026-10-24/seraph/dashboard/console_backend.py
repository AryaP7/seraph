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
                news_preview=None, news_mode="historical_decision", news_as_of=None, news_offset=0,
                holdings=None, portfolio_context=None, institution_decomposition=None, contagion_network=None,
                sector_archive_as_of=None):
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
    sector_surface = sector_analysis(point['evaluation_timestamp'], sector_archive_as_of)
    score = point['composite']
    if score:
        view = unwrap(build_view(role, CsrsPoint.model_validate(score),
            explanation=(point.get('explanation') or {}).get('sentence',''),
            pillar_scores=point['original_pillars'],
            spectral=point['original_pillars'].get('rmt',{}).get('detail',{}),
            action_log=log if role=='regulator' else None,
            institution_decomposition=institution_decomposition, contagion_network=contagion_network,
            playbook=unwrap(playbook(point['explanation']['dominantPillar']))))
    else:
        view = dict(role=role,csrs=None,alertLevel='unavailable',explanation='No composite: original inputs unavailable.',maskDegraded=True)
        if role == 'regulator':
            view['institutionDecomposition'] = institution_decomposition
            view['contagionNetwork'] = contagion_network
    payload = dict(run_id=point['run_id'],date=point['date'],timestamp=point['evaluation_timestamp'],
        cutoff=point['data_cutoff'],mode=manifest['mode'],role=role,view=view,
        history=_history_with_benchmark(points,point),
        # FR45/FR51: the real market aggregate, or an explicit absence. The
        # console previously carried three fabricated `(example)` values here.
        flow=market_flow(point.get('date')),
        portfolio=portfolio if portfolio is not None else point.get('portfolio'),
        portfolio_context=portfolio_context,sector_observations=sector_surface,
        news=news_branch(point, store=news_store, master=news_master,
                         preview=news_preview, role=role, news_mode=news_mode,
                         news_as_of=news_as_of, news_offset=news_offset,
                         # The retail view is only specific if it knows what
                         # the user holds; without it every holding would be
                         # reported as uncovered, which is true but useless.
                         portfolio=holdings if holdings is not None else portfolio,
                         hawkes_sector_flags=sector_surface['flags']),
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


def measured_sectors(as_of, *, input_through=None):
    from seraph.pillars.hawkes.sectors import select
    try:
        return select(as_of, input_through=input_through)
    except (OSError, ValueError, KeyError) as exc:
        return dict(available=False, flags={}, sectors=[], reason=str(exc))


def sector_analysis(decision_ts, archive_as_of=None):
    """An explicit retrospective view never backdates artifact availability."""
    cutoff = archive_as_of or decision_ts
    return dict(measured_sectors(cutoff, input_through=decision_ts[:10]), analysis_cutoff=cutoff,
                market_decision=decision_ts,
                analysis_mode='retrospective_archive' if archive_as_of else 'decision_time',
                analysis_note=('Retrospective measured sector activity; received/fitted after the selected '
                               'market decision. Does not change the historical score or prove advance warning.'
                               if archive_as_of else 'Only sector artifacts available by the selected market decision.'))


def market_flow(as_of: str | None = None) -> dict:
    """FR45/FR51 — the latest real market-level FII/DII flow, or why there
    is none.

    The console showed `FII net (example) -1200`, `DII net (example) 900`,
    `Residual share (example) 0.72` -- three fabricated numbers, labelled
    `(example)` but sitting where a measurement belongs. E14 now carries real
    published prints (`seraph/ingestion/flow_client.py` reads NSE's public
    `fiidiiTradeReact` endpoint and its index-turnover archive), so this
    reads them.

    Returns `available=False` with a reason rather than a placeholder when
    E14 is empty or unreachable. An empty panel that says why is honest; an
    example number in a measurement's place is not, however it is labelled.

    The flow is a MARKET AGGREGATE. `flow_diagnostic` carries the scope
    caveat and it must not be softened on the way to the screen: bar data has
    no counterparty tags, so `residualFlowShare` is a proxy for
    non-institutional participation and never a per-instrument retail
    attribution.
    """
    import asyncio

    from seraph.decision_support.artefacts import flow_diagnostic

    async def _read() -> dict | None:
        import asyncpg

        from seraph.store.bootstrap import DEFAULT_DSN
        connection = await asyncpg.connect(DEFAULT_DSN, timeout=5)
        try:
            sql = ("SELECT date, fii_net, dii_net, total_turnover, "
                   "residual_flow_share FROM flow_aggregates ")
            args: tuple = ()
            if as_of:
                # asyncpg binds a real `date`, not an ISO string, for a date
                # parameter -- a string raises DataError even with the cast.
                from datetime import date as _date
                sql += "WHERE date <= $1 "
                args = (_date.fromisoformat(as_of[:10]),)
            sql += "ORDER BY date DESC LIMIT 1"
            row = await connection.fetchrow(sql, *args)
            return dict(row) if row else None
        finally:
            await connection.close()

    try:
        row = asyncio.run(_read())
    except Exception as exc:                                # noqa: BLE001
        return dict(available=False,
                    reason=(f"the flow store could not be read "
                            f"({type(exc).__name__}). No example values are "
                            f"substituted"))
    if row is None:
        return dict(available=False,
                    reason=("no FII/DII print has been ingested yet. Run "
                            "`python -m seraph.ingestion.flow_client`; NSE "
                            "serves no free bulk history, so the series "
                            "accumulates forward from first capture"))

    numeric = {k: (float(v) if v is not None else None)
               for k, v in row.items() if k != "date"}
    result = flow_diagnostic(numeric)
    if result.status != "ok":
        return dict(available=False, date=str(row["date"]),
                    reason=f"stored flow row is unusable: {result.error}")
    return dict(available=True, date=str(row["date"]), **result.value,
                totalTurnoverCrore=numeric.get("total_turnover"),
                units="INR crore, as published by NSE",
                warnings=[w.message for w in result.warnings],
                scope=("market aggregate across NSE+BSE+MSEI for the FII/DII "
                       "numerator against NSE cash turnover. A proxy for "
                       "non-institutional participation, never a "
                       "per-instrument retail attribution"))


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


def dispatch(store, point, role, event, *, sector_archive_as_of=None):
    """Validate UI context and permission again before any computation/write."""
    if role not in ROLE_FIELDS:
        raise ValueError('Unknown role')
    if event.get('run_id') != point['run_id'] or event.get('date') != point['date']:
        raise ValueError('Stale request: select the current run/date and retry')
    # FIX11: every result carries the context it was produced for, so a late
    # response can be matched against the selection on arrival.
    context=dict(run_id=point['run_id'],date=point['date'],role=role,
                 request_id=event.get('id'))
    return dict(_dispatch(store,point,role,event,sector_archive_as_of=sector_archive_as_of),context=context)


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


def _workflow(point, role, event, *, store=None):
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
    identity = svc.describe(role)

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
        baseline = next((p for p in store.points(saved['baseline']['run_id'])
                         if p['date'] == saved['baseline']['date']), None)
        if baseline is None or baseline_from_point(baseline).artefact_id != saved['baseline']['artefact_id']:
            raise ValueError('The pinned scenario baseline is unavailable or has changed')
        results = _simulate_steps(baseline, saved['kind'], saved['steps'])
        return ok('sc_run', scenarios.record_run(
            principal, scenario_id, results=[r.model_dump(mode='json') if hasattr(r, 'model_dump') else r
                                             for r in results],
            inputs=dict(steps=saved['steps'], kind=saved['kind'],
                        run_id=baseline['run_id'], date=baseline['date'],
                        decomposition=baseline.get('composite'))))
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
                'Scenario assumptions and data modes are recorded with each result; '
                'historical action comparisons are ex-post, not an economic forecast or a prospective recommendation.',
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
    if kind == 'defensive':
        from seraph.decision_support.defensive import compare
        return [dict(kind=kind, **compare(steps[0]['request']))]
    if not point.get('composite') or not point.get('reconciled'):
        raise ValueError('No baseline state available for this run/date')
    state = ReconciledState.model_validate(point['reconciled'])
    weights = _weights_of(point)
    first = next((s for s in steps if isinstance(s, dict)), None)
    if first is None:
        raise ValueError('This scenario has no usable step')

    if kind == 'macro_path':
        from seraph.pillars.hamilton.projection import project
        artifact = first['artifact']
        path, baseline_path = first['path'], first['baseline_path']
        if [r['session'] for r in path] != [r['session'] for r in baseline_path]:
            raise ValueError('Macro and baseline paths must use the same sessions')
        if path[0]['session'] <= point['date']:
            raise ValueError('Projection sessions must follow the pinned market baseline')
        if artifact['training_end'] > point['date'] and first.get('analysis_mode') != 'retrospective_hypothetical':
            raise ValueError('A newer fit requires explicit retrospective_hypothetical mode')
        projected = project(artifact, path)
        base_xi = project(artifact, baseline_path)
        scores = unwrap(simulate_policy(reconciled=state, weights=weights, xi_path=projected))
        base_scores = unwrap(simulate_policy(reconciled=state, weights=weights, xi_path=base_xi))
        limitations = list(artifact['limitations'])
        coverage = artifact.get('input_manifest', {}).get('macro_source', {}).get('coverage', {})
        if coverage.get('excluded_dates'):
            limitations.append(f"{len(coverage['excluded_dates'])} input dates lacked policy observations. Fitted transitions advance over retained observation pairs; omitted sessions are not modelled transitions.")
        return [dict(kind=kind, artifact_id=artifact['artifact_id'], sessions=[r['session'] for r in path],
            initial_xi=artifact['initial_xi'], initial_state_date=artifact['initial_state_date'],
            xi_path=projected, baseline_xi_path=base_xi,
            score_path=[r.model_dump(mode='json') for r in scores],
            baseline_score_path=[r.model_dump(mode='json') for r in base_scores],
            fit_warnings=artifact.get('input_manifest', {}).get('fit_warnings', []),
            limitations=limitations + ['Equal regime weights or an excluded Hamilton pillar can leave the score unchanged.'])]

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


def _dispatch(store, point, role, event, *, sector_archive_as_of=None):
    op=event.get('op')
    workflow=_workflow(point,role,event,store=store)
    if workflow is not None:
        return workflow
    if op=='portfolio':
        holdings=event.get('holdings')
        if not isinstance(holdings,list) or len(holdings)>10000:
            raise ValueError('Provide a JSON list of at most 10000 holdings')
        measured = sector_analysis(point['evaluation_timestamp'], sector_archive_as_of)
        return dict(kind='portfolio',
                    value=unwrap(portfolio_overlay(holdings, measured['flags'])),
                    basis='User supplied current holdings; measured coverage shown separately',
                    sector_flags=measured)
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


# --- C12: the FR35 evaluation surface (T10) ------------------------------

#: Who may read an ablation table. Validation output is a research surface:
#: it reports what the instrument can and cannot do, which is the
#: institutional and regulatory question, not the retail traffic-light one
#: (FR42). Retail is told where it lives rather than shown an empty panel.
EXPERIMENT_ROLES = ('institutional', 'regulator')


def experiment_surface(root=None, role='retail'):
    """What the console can say about the FR35 ablation, and why.

    Reads only. The pre-registration is deliberately NOT committable from
    here: D5(d) makes a committed design the precondition for any AUC, and
    DR-05 step 5 left committing it to a person precisely so that it cannot
    happen as a side effect of something else. A button on a dashboard is
    exactly the "build step" that record refused.

    Returns a dict the panel renders, never a raised exception, so a console
    with no artefacts still draws.
    """
    import json
    import os
    from pathlib import Path

    from seraph.validation import experiment_store
    from seraph.validation.preregistration import DEFAULT_PATH, verify

    root = Path(root) if root else Path(__file__).resolve().parents[2]
    design_path = Path(os.environ.get('SERAPH_PREREGISTRATION',
                                      str(root / DEFAULT_PATH)))

    out = {
        'permitted': role in EXPERIMENT_ROLES,
        'role': role,
        'design': {'path': str(design_path), 'committed': design_path.exists()},
        'reports': [],
        'commit_hint': (
            'python -c "from seraph.validation.preregistration import commit; '
            'print(commit())"'),
        'note': (
            'The design is committed by a person, once, before the first AUC '
            'exists (D5(d), DR-05 step 5). This panel cannot do it: a control '
            'here would make the design a side effect of opening a page.'),
    }

    if design_path.exists():
        intact, digest = verify(design_path)
        out['design'].update(intact=intact, hash=digest)
        try:
            blob = json.loads(design_path.read_text(encoding='utf-8'))
            design = blob.get('design', {})
            out['design'].update(
                table_b_scope=design.get('tableBScope'),
                configurations=len(design.get('configurations', [])),
                amber_threshold=design.get('amberThreshold'),
                calibration_max_iter=design.get('calibrationMaxIter'))
        except (ValueError, OSError) as exc:
            out['design']['unreadable'] = str(exc)

    # Saved report artefacts, newest first. A directory rather than one file,
    # because save() refuses to overwrite -- each run is its own evidence.
    reports_dir = Path(os.environ.get(
        'SERAPH_EXPERIMENT_REPORTS', str(root / 'prototype_runs/experiments')))
    out['reports_dir'] = str(reports_dir)
    if reports_dir.exists():
        for path in sorted(reports_dir.glob('*.json'), reverse=True):
            try:
                report, digest, ok = experiment_store.load(path)
            except (ValueError, OSError, KeyError) as exc:
                out['reports'].append(dict(name=path.name, readable=False,
                                           error=str(exc)))
                continue
            out['reports'].append(dict(
                name=path.name, readable=True, artefact_id=digest, intact=ok,
                pre_registration_hash=report.pre_registration_hash,
                table_b_scope=report.table_b_scope,
                calibration_max_iter=report.calibration_max_iter,
                comparability=report.comparability,
                dataset_provenance=report.dataset_provenance,
                measured=len(report.measured()),
                unavailable=len(report.unavailable()),
                unpublishable=report.unpublishable_rows,
                absences=report.absence_census(),
                rendered=experiment_store.render(report),
                configurations=[
                    dict(table=s.table, subset='+'.join(s.pillar_subset),
                         mode=s.reconciliation_mode, xi_mode=s.xi_mode,
                         declared_folds=s.declared_folds,
                         measured_folds=s.measured_folds,
                         mean_auc=s.mean_auc, auc_min=s.auc_min,
                         auc_max=s.auc_max, complete=s.complete,
                         mean_lead_time_days=s.mean_lead_time_days,
                         unavailable_folds=s.unavailable_folds)
                    for s in report.configurations()],
            ))
    return out


# --- OPS01: the health surface -------------------------------------------

#: How many minutes may pass between successes before a LEDGER job reads as
#: stale. These are the console's declared expectations, not the jobs' own
#: schedules -- there is no scheduler yet (O03), so a budget here is what a
#: reader should expect if someone is running them, and a stale reading is
#: the honest answer when nobody is.
#:
#: Only jobs that actually go through `operations.jobs` belong here. The
#: market jobs (daily vintages, prospective forecast) write a status file
#: that the MARKET JOBS panel reads instead, so listing them would report
#: `never_run` for work that has run -- a false alarm, which is the mirror of
#: the false green banner this surface exists to prevent. Every other job
#: found in the ledger is reported too, under DEFAULT_JOB_BUDGET, so nothing
#: recorded there is invisible.
JOB_BUDGET_MINUTES = {
    'news.poll': 180,
}
DEFAULT_JOB_BUDGET = 1440


def health_surface(at=None):
    """What is stale, what is broken, and who was told (OPS01).

    `operations/monitoring.py` was written as a health reader and says in its
    own docstring that "an empty dashboard with a green banner is the
    specific failure this prevents" -- and then nothing in the dashboard read
    it. This is that reader, surfaced.

    Its first rule is the one worth preserving through the UI: **silence is
    never health.** A source that has never been fetched is
    `never_succeeded`, a job with no run is `never_run`, and neither is `ok`.
    So a console with nothing running must show that, not an empty green
    panel.
    """
    import os
    from datetime import datetime
    from pathlib import Path

    from seraph.shared_types import IST
    from seraph.operations import monitoring

    at = at or datetime.now(IST).replace(microsecond=0).isoformat()
    root = Path(__file__).resolve().parents[2]
    news_path = Path(os.environ.get(
        'SERAPH_NEWS_STORE',
        str(root / 'prototype_runs/news-intelligence-pilot.sqlite')))
    jobs_path = Path(os.environ.get('SERAPH_JOB_STORE',
                                    str(root / 'prototype_runs/jobs.sqlite')))

    out = {'at': at, 'checks': [], 'status': 'unknown', 'stores': {
        'news': str(news_path), 'jobs': str(jobs_path)}, 'problems': []}

    checks = []
    if news_path.exists():
        try:
            from seraph.news.acquisition import NewsStore

            checks.extend(monitoring.source_checks(NewsStore(news_path), at=at))
        except Exception as exc:                       # noqa: BLE001
            out['problems'].append(f'news sources unreadable: {exc}')
    else:
        out['problems'].append(
            f'no news store at {news_path}: nothing has ever been fetched, '
            f'which reads as never_succeeded rather than ok')

    if jobs_path.exists():
        try:
            from seraph.operations.jobs import JobStore

            store = JobStore(jobs_path)
            # Names from the ledger, not a guess. The first version of this
            # hard-coded `news_poll` while the ledger records `news.poll`, so
            # it reported never_run for a job with hundreds of runs.
            recorded = {r.job for r in store.runs(None, limit=1000)}
            budgets = {job: DEFAULT_JOB_BUDGET for job in recorded}
            budgets.update(JOB_BUDGET_MINUTES)
            checks.extend(monitoring.job_checks(store, budgets, at=at))
        except Exception as exc:                       # noqa: BLE001
            out['problems'].append(f'job ledger unreadable: {exc}')
    else:
        out['problems'].append(
            f'no job ledger at {jobs_path}: no job has ever been recorded, '
            f'which reads as never_run rather than ok')

    # O03: the schedule is part of health. A pipeline that is never invoked
    # produces no failures at all, which is the quietest way for a system to
    # stop working.
    out['schedule'] = _schedule_health()

    if checks:
        out.update(monitoring.overall(checks))
    else:
        out['note'] = ('no check could be run, which is itself not health: '
                       'see the problems listed beside this')
    return out


# --- C12: prediction and early warning (the core functional requirement) --

#: Warning levels, worst first, with how the console should draw each. A
#: level the engine can produce and this map does not carry would be drawn as
#: nothing, so the panel checks membership rather than using .get().
WARNING_LEVELS = {
    'warning': ('WARNING', 'error'),
    'abstained': ('ABSTAINED', 'warning'),
    'unassessable': ('UNASSESSABLE', 'warning'),
    'no_warning': ('NO WARNING', 'success'),
}


def prediction_surface():
    """The current forecast and warning state, read from the job's output.

    SERAPH is a prediction and early-warning system, and its engine existed
    only as backend code, a CLI experiment and a separate read-only artifact
    viewer. This is the main application's path to it.

    Reads; never fits. `scripts/run_prediction.py` runs the actual engine --
    `build_pillar_features`, `walk_forward_predict`, `calibrate_alerts` -- in
    about twenty seconds and persists the state, and `run_market_jobs.py`
    invokes it in the daily sequence. A page render that refitted
    seventy-three models would make every refresh a cliff, which is the same
    reason MARKET JOBS reads a status file.

    The three claims arrive separately and stay separate: `measured` is
    observation, `predicted` is one model output, `warning` is a policy
    decision. `validation` travels with all of them.
    """
    from seraph.prediction import operational

    # Through the package, not through `scripts/`: an installed wheel has no
    # scripts directory, and `verify_packaging.py` installs one and probes
    # it. Reading the core feature's state must not depend on running from a
    # source checkout.
    saved = operational.load_state()
    if not saved.get('ran'):
        return dict(available=False, path=saved.get('path'),
                    error=saved.get('error'),
                    note=saved.get('note', 'no prediction state is saved'),
                    command='python scripts/run_prediction.py')

    state = saved['state']
    required = ('predicted', 'warning', 'measured', 'history', 'validation')
    missing = [key for key in required if key not in state]
    if missing:
        return dict(available=False, path=saved['path'],
                    note=(f'the saved prediction state is missing {missing}; '
                          f're-run the job to regenerate it'),
                    command='python scripts/run_prediction.py')

    level = state['warning'].get('level')
    label, style = WARNING_LEVELS.get(level, (str(level).upper(), 'warning'))

    # O03: a failed or missed refresh keeps the last valid forecast -- the
    # panel still shows it -- but it must not be presented as current. The
    # staleness is computed against the expected session, not against the
    # file's mtime, because a re-run that produces the same date is not a
    # fresher forecast.
    from seraph.operations.schedule import prediction_staleness

    staleness = prediction_staleness(state.get('as_of'))
    return dict(available=True, path=saved['path'], state=state,
                as_of=state.get('as_of'),
                generated_at=state.get('generated_at'),
                warning_label=label, warning_style=style,
                level_known=level in WARNING_LEVELS,
                staleness=staleness)


def _schedule_health() -> dict:
    """Is the daily pipeline actually scheduled, and did it acquire data?

    Three separate questions, because each can be yes while the next is no:
    registered / executed / acquired fresh data. Reporting them as one status
    is how a green banner ends up sitting on a corpus that stopped updating.
    """
    import subprocess
    import sys

    from seraph.operations import schedule
    from seraph.operations.market_jobs_status import read_status

    name = schedule.task_name_override()
    out = dict(task_name=name, expected_session=schedule.expected_session(),
               at_ist=schedule.RUN_AT_IST.strftime('%H:%M'),
               registered=None, registration_detail='')

    if not sys.platform.startswith('win'):
        out['registration_detail'] = (
            'not checked: this is not Windows. `crontab -l` shows what is '
            'installed; `python scripts/schedule_market_jobs.py --cron` '
            'prints the line.')
    else:
        try:
            done = subprocess.run(schedule.query_command(name),
                                  capture_output=True, text=True, timeout=20)
            out['registered'] = done.returncode == 0
            if done.returncode != 0:
                out['registration_detail'] = (
                    'no scheduled task with this name. The pipeline runs only '
                    'when something invokes it; register it with '
                    '`python scripts/schedule_market_jobs.py --register`.')
            else:
                for line in (done.stdout or '').splitlines():
                    if line.split(':', 1)[0].strip() in (
                            'Next Run Time', 'Last Run Time', 'Last Result',
                            'Scheduled Task State'):
                        out.setdefault('task', []).append(line.strip())
        except (OSError, subprocess.SubprocessError) as exc:
            out['registration_detail'] = f'could not query the scheduler: {exc}'

    last = read_status()
    out['last_run'] = dict(
        ran=last.get('ran', False),
        generated=last.get('generated'),
        execution_ok=last.get('execution_ok', last.get('ok')),
        skipped=bool(last.get('skipped')),
        session=last.get('session'),
        steps=[dict(step=s.get('step'), ok=s.get('ok'))
               for s in last.get('steps', [])],
        note=last.get('note', ''))
    out['data'] = last.get('data') or dict(
        acquired='unknown', currency='unknown',
        detail='the last run recorded no freshness information')
    out['note'] = ('registered, executed and acquired-fresh-data are three '
                   'different facts. A task can be registered and never fire; '
                   'a run can succeed and bring no new data.')
    return out
