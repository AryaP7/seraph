"""C12 original console with server-side role projection and C11 interactions.

FIX10: the whole page is built from ONE coherent run/as-of bundle — the
selected complete run, its points up to the selected date, its report and its
action log. Reads are cached per `(store, run, role)` scope so a rerun does not
re-parse every point, and so a payload built for one scope can never be served
to another. `AUTH02` extends the scope tuple with identity and organisation.

FIX11: a tool result stays bound to the `(run_id, date, role, request_id)` it
was produced for. A late response whose context no longer matches the selection
is discarded instead of rendered, and the bridge is told why.
"""
from pathlib import Path
import os
import time
import streamlit as st
import streamlit.components.v1 as components
from seraph.orchestration.run_store import RunStore
from seraph.dashboard.console_backend import project_run, dispatch
from seraph.news import NewsStore
from seraph.news.registry import load_master_data
from seraph.dashboard.current_reader import VIEW_MODES, read_current, revision
from seraph.live.store import LiveStore
from seraph.shared_types import PILLAR_ORDER

console = components.declare_component('seraph_console', path=str(Path(__file__).parent/'console_component'))

#: Short, because a run can be extended while the page is open.
CACHE_TTL_SECONDS = 30

#: T08: how often the live view re-reads the runtime. An engineering default,
#: not a measured one — the plan says so, and nothing here depends on it being
#: right. A poll that finds an unchanged revision rebuilds nothing.
LIVE_POLL_SECONDS = 2.0


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _complete_runs(store_path: str):
    """Complete runs only. A run sealed but awaiting its report is not one."""
    return [r for r in RunStore(store_path).runs() if r['status'] == 'complete']


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _news_sources(news_path: str):
    """The news store and curated registry, or nothing with a reason.

    T13: `build_news_payload()` existed and nothing called it. This is the
    call. A missing store is not an error — it means the news channel is not
    connected, and the payload says exactly that instead of showing a
    fabricated map as though it were data.
    """
    path = Path(news_path)
    if not path.exists():
        return None, None, f'no news store at {path}'
    master, report = load_master_data()
    return str(path), report, None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _bundle(store_path: str, run_id: str, role: str):
    """One coherent run/as-of bundle, scoped by store, run and role.

    The action log is read only for the role that may see it, so a cached
    regulator payload cannot be handed to a retail session.
    """
    store = RunStore(store_path)
    return dict(
        points=store.points(run_id),
        report=store.report(run_id) if role != 'retail' else None,
        log=(store.action_log(run_id).payload(include_retracted=True)
             if role == 'regulator' else None),
    )


def csrs_metric(payload: dict | None) -> tuple:
    """The score to display, and the detail line under it.

    U01: `payload['csrs']` is `CsrsPoint.model_dump()` -- a dict with a
    nested float, a variance, a confidence interval and the D2 mask. The
    panel passed that whole dict to `st.metric`, which raises

        Invalid `value` type. Expected one of: int, float, Decimal,
        NumPy number. Provided type: dict.

    so a store holding a real decision rendered an exception where the score
    should be. Accepts the bare float too: a producer that writes a scalar is
    not wrong, it is just a different shape, and this is the one place that
    difference has to be absorbed.
    """
    body = (payload or {}).get('csrs')
    if body is None:
        return 'Unavailable', 'no CSRS in this decision'
    if isinstance(body, (int, float)) and not isinstance(body, bool):
        return round(float(body), 4), ''
    if not isinstance(body, dict):
        return 'Unavailable', f'unrecognised CSRS shape {type(body).__name__}'
    score = body.get('csrs')
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return 'Unavailable', 'this decision carries no numeric CSRS'
    bits = []
    low, high = body.get('ci_lower'), body.get('ci_upper')
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        bits.append(f'FR29 interval [{low:.3f}, {high:.3f}]')
    if body.get('alert_level'):
        bits.append(f"level {body['alert_level']}")
    mask = body.get('mask')
    if isinstance(mask, (list, tuple)) and len(mask) == len(PILLAR_ORDER):
        present = [p for p, on in zip(PILLAR_ORDER, mask) if on]
        bits.append('pillars ' + (', '.join(present) if present else 'NONE'))
    return round(float(score), 4), ' · '.join(bits)


def live_panel(store_path: Path):
    """T08 (audit finding R12): the live runtime, read and labelled.

    The console used to show archive runs only, and a replay rendered exactly
    like a current reading. Mode is now a first-class choice with no silent
    fallback: asking for LIVE when nothing has been committed says so rather
    than quietly serving a replay.
    """
    if not store_path.exists():
        st.info('No live runtime store yet. `python scripts/run_live.py '
                '--status` reports what the runtime would do; this panel '
                'shows what it has actually committed.')
        return None
    store = LiveStore(store_path)
    mode = st.radio('View mode', list(VIEW_MODES), horizontal=True,
                    key='live_view_mode',
                    help='live / replay / demo is a choice. Nothing here '
                         'falls back from one to another.')
    current = read_current(store, mode=mode)
    health = current.health

    left, right = st.columns(2)
    with left:
        st.caption('LATEST SCORE')
        if current.decision_id is None:
            st.warning(current.reason)
        else:
            score, detail = csrs_metric(current.payload)
            st.metric('CSRS', score, help=current.reason)
            if detail:
                st.caption(detail)
            age=current.age_seconds or 0
            age_text=(f'{age / 60:.0f} min old' if age >= 0
                      else f'{abs(age) / 60:.0f} min in the FUTURE')
            st.caption(f'decision `{current.decision_id}` · as of '
                       f'{current.as_of} · {current.publication_state} · '
                       f'{age_text}')
            if not current.is_current:
                st.warning(current.reason)
    with right:
        st.caption('WORKER HEALTH — a separate fact from the score')
        st.write(health.describe())
    return revision(store)


def store_paths() -> dict:
    """The three stores this console reads, and where each is configured.

    Independent by construction. U01's defect was structural rather than
    cosmetic: `main()` returned on a missing archive store before the live
    panel was built and before news was reached, so a machine running the
    live runtime and the news worker -- and nothing else -- showed one line
    of text saying to run a historical script. The audit probe recorded it as
    1 info message, 0 metrics, 0 radios. Each surface now stands or falls on
    its own store.
    """
    root = Path(__file__).resolve().parents[2]
    return dict(
        archive=Path(os.environ.get('SERAPH_PROTOTYPE_STORE',
                                    str(root/'prototype_runs/seraph.sqlite'))),
        live=Path(os.environ.get('SERAPH_LIVE_STORE',
                                 str(root/'prototype_runs/live.sqlite'))),
        news=Path(os.environ.get('SERAPH_NEWS_STORE',
                                 str(root/'prototype_runs/news-intelligence-pilot.sqlite'))),
    )


def _news_action(event: dict, role: str, news_path, news_master, payload):
    """Dispatch one role action against the news channel.

    Rebuilds the channel at the decision time the console is showing, so
    an action operates on the same facts the reader is looking at rather
    than on whatever has arrived since.
    """
    from seraph.dashboard.news_view import news_channel
    from seraph.news import workflows
    from seraph.news.acquisition import _now as news_now

    op = event.get('op')
    # `news_path` arrives as an OPEN STORE from main(), not a path.
    # Re-opening it raised "argument should be a str or an os.PathLike
    # object ... not 'NewsStore'", which the console then displayed as a
    # successful operation -- see the status-ordering fix in bridge.js.
    store = news_path if isinstance(news_path, NewsStore) else NewsStore(news_path)
    decision_ts = ((payload.get('news') or {}).get('as_of')) or news_now()
    channel = news_channel(store, news_master, decision_ts=decision_ts)
    events = {e.event_id: e for e in channel['eligible_events']}

    if op == 'news_review':
        return workflows.review_instrument_link(
            store, role=role,
            later_event_id=str(event.get('later') or ''),
            earlier_event_id=str(event.get('earlier') or ''),
            decision=str(event.get('decision') or ''),
            reason=str(event.get('reason') or ''),
            instrument_id=event.get('instrument_id'))

    if op == 'news_scenario':
        target = events.get(str(event.get('event_id') or ''))
        if target is None:
            raise ValueError('that event is not visible at this decision time')
        edge = None
        for edge_id in reversed(tuple(event.get('path') or ())):
            candidate = channel['master'].edges.get(edge_id)
            if candidate is not None and candidate.products:
                edge = candidate
                break
        if edge is None:
            for estimate in channel['estimates']:
                if estimate.event_id != target.event_id:
                    continue
                for edge_id in reversed(estimate.path or ()):
                    candidate = channel['master'].edges.get(edge_id)
                    if candidate is not None and candidate.products:
                        edge = candidate
                        break
                if edge is not None:
                    break
        low, high = event.get('pass_through_low'), event.get('pass_through_high')
        interval = (low, high) if (low not in (None, '') and
                                   high not in (None, '')) else None
        return workflows.run_scenario(
            target, channel['master'], role=role, edge=edge,
            product=event.get('product') or None,
            cost_base=event.get('cost_base'), pass_through=interval,
            on=decision_ts)

    # news_export
    comparison = None
    pair = event.get('compare') or ()
    if len(tuple(pair)) == 2:
        from seraph.news.comparison import compare_instruments
        comparison = compare_instruments(events.get(pair[0]),
                                         events.get(pair[1]),
                                         master=channel['master'])
    return workflows.export_analysis(
        role=role, channel=channel, scenario=event.get('scenario'),
        comparison=comparison,
        matrix=(channel.get('role_view') or {}).get('matrix'),
        event_ids=tuple(event.get('event_ids') or ()))


def acquisition_panel(news_path: Path):
    """Who is fetching news, and what each source actually returned.

    Startup used to be silent about this. The worker was started by one
    launcher and not by another, so whether the screen showed live news
    depended on the command the operator happened to type, and the only
    clue was a heartbeat age nobody reads as "your IDE launch does not
    fetch". This says which of the situations it is in, in words.

    It describes NEWS ACQUISITION and nothing else. The market pillars,
    the live runtime and the archive are separate services with their own
    panels, and a green line here is not a statement about any of them.
    """
    from seraph.dashboard import news_service
    from seraph.news.acquisition import _now as news_now

    state = news_service.status()
    label = {'dashboard': 'This dashboard started a supervised worker.',
             'external': 'A worker was already running; this dashboard did '
                         'not start a second one.',
             'disabled': 'Acquisition is switched off for this session.',
             'failed': 'This dashboard could not start a worker.',
             'exited': 'The worker this dashboard started has exited.',
             'not_asked': 'No worker has been requested.'}
    st.write(f"**{label.get(state.get('owner'), state.get('owner'))}** "
             f"{state.get('reason', '')}")

    if not news_path.exists():
        st.info('No news store yet; the worker creates one on its first pass.')
        return
    store = NewsStore(news_path)
    worker = store.worker_state(news_now())
    shown = {'state': worker['state'], 'activity': worker.get('activity'),
             'passes': worker.get('sequence'),
             'last beat': worker.get('last_beat_at'),
             'age (min)': worker.get('age_minutes'),
             'detail': worker.get('detail')}
    st.caption('ACQUISITION WORKER — liveness only. `degraded` means the '
               'worker is polling and at least one source is failing.')
    st.write(shown)

    rows = []
    for source in store.sources():
        health = store.health(source.source_id)
        rows.append(dict(source=source.source_id, status=health.status,
                         last_success=health.last_success_at,
                         last_attempt=health.last_attempt_at,
                         consecutive_failures=health.consecutive_failures,
                         error=health.last_error))
    rows.sort(key=lambda r: (r['status'] != 'never_succeeded',
                             r['consecutive_failures'] == 0, r['source']))
    st.caption(f'PER-SOURCE OUTCOMES — {sum(1 for r in rows if r["consecutive_failures"])} '
               f'of {len(rows)} source(s) currently failing. A failing source '
               f'is degraded coverage; the others keep acquiring.')
    st.dataframe(rows, use_container_width=True, hide_index=True)


def news_only_panel(news_path: Path, role: str):
    """The news channel with no market decision to anchor it.

    Deliberately a DIFFERENT surface from the console's news tab, not the
    same one with a gap. The console's version is bound to a selected
    historical decision and answers "what was known then"; this one has no
    such anchor and answers "what is known now". Labelling them the same
    would be the substitution the whole mode discipline exists to prevent.
    """
    if not news_path.exists():
        st.info(f'No news store at `{news_path}`. `./launch_news.ps1` '
                f'registers the reviewed catalogue and starts the worker.')
        return
    from seraph.dashboard.news_view import build_news_payload
    from seraph.news.acquisition import _now as news_now
    store = NewsStore(news_path)
    master = load_master_data()[0]
    as_of = news_now()
    st.caption(f'CURRENT NEWS · no market decision is selected, so this is '
               f'the live news clock at {as_of}, not a reconstruction.')
    payload = build_news_payload(store, master, decision_ts=as_of,
                                 role=role, strict_replay=False)
    channel = payload.get('channel') or {}
    events = channel.get('events') or []
    freshness = channel.get('freshness') or {}
    columns = st.columns(3)
    columns[0].metric('Events visible now', len(events))
    columns[1].metric('Sources reporting', len(channel.get('sources') or []))
    columns[2].metric('Registered issuers', len(getattr(master, 'entities', {})))
    if freshness:
        st.caption(f"Freshness: {freshness.get('state', 'unknown')} · "
                   f"{freshness.get('note', '')}")
    if events:
        st.dataframe([
            dict(published=e.get('published_at'), source=e.get('source_id'),
                 title=(e.get('title') or '')[:140],
                 kind=e.get('event_type'))
            for e in events[:40]], width='stretch')
    else:
        st.info('The news store is attached and holds no event visible at '
                'this clock. That is an empty result, not a failure.')


def archive_console(path: Path):
    """The historical console. Returns False when there is nothing to show.

    Its empty states are now statements about THIS surface rather than about
    the whole application, because the live and news surfaces above it may
    well be working.
    """
    if not path.exists():
        st.info(f'No archive store at `{path}`. `python '
                f'scripts/run_prototype.py` produces one. The live and news '
                f'surfaces above do not depend on it.')
        return False
    if not _complete_runs(str(path)):
        st.info('The archive store is attached and holds no COMPLETE run. A '
                'run that is sealed but awaiting its report is not complete; '
                'resume the canonical command.')
        return False
    return True


def main():
    st.set_page_config(page_title='SERAPH',layout='wide')
    st.markdown('<style>.block-container{max-width:1900px;padding-top:1rem}</style>',unsafe_allow_html=True)
    st.title('SERAPH')
    st.caption('Historical model outputs + explicitly tagged fabricated previews. Local role switching is not authentication. Experimental warnings are not validated crisis predictions.')
    paths=store_paths()
    path=paths['archive']
    live_path=paths['live']
    # Exactly one supervised worker, whichever command started this app.
    # `launch_prototype.ps1` starts one; `.claude/launch.json` and a bare
    # `streamlit run` did not, so the same application had live news or a
    # frozen store depending on how it was launched. The call stands aside
    # when a launcher already owns a worker, and an OS lock -- not this
    # call -- is what guarantees there is only ever one.
    from seraph.dashboard import news_service
    news_service.ensure_worker(paths['news'])
    with st.expander('NEWS ACQUISITION', expanded=False):
        acquisition_panel(paths['news'])
    role=st.session_state.setdefault('console_role','retail')
    with st.expander('LIVE RUNTIME', expanded=live_path.exists()):
        live_revision=live_panel(live_path)
    if live_revision and st.session_state.get('live_revision')!=live_revision:
        # The revision moved, so there is genuinely new data. Record it rather
        # than rebuilding the page under the user: a silent rebase loses a
        # half-typed form, and the console keeps drafts across renders.
        st.session_state['live_revision']=live_revision
        st.session_state['live_revision_seen_at']=time.strftime('%H:%M:%S')
    if not archive_console(path):
        # No historical console, but the other two surfaces are independent
        # and may both be live. This is the branch U01's early return made
        # unreachable.
        with st.expander('NEWS CHANNEL', expanded=paths['news'].exists()):
            news_only_panel(paths['news'], role)
        st.caption(f"Configured stores — archive `{path}` "
                   f"({'present' if path.exists() else 'ABSENT'}) · live "
                   f"`{live_path}` ({'present' if live_path.exists() else 'ABSENT'}) "
                   f"· news `{paths['news']}` "
                   f"({'present' if paths['news'].exists() else 'ABSENT'}). "
                   f"Override with SERAPH_PROTOTYPE_STORE, SERAPH_LIVE_STORE "
                   f"and SERAPH_NEWS_STORE.")
        return
    store=RunStore(path)
    runs=_complete_runs(str(path))
    selected=st.selectbox('Run',[r['id'] for r in runs])
    manifest=next(r['manifest'] for r in runs if r['id']==selected)
    bundle=_bundle(str(path),selected,role)
    points=bundle['points']
    day=st.selectbox('Historical decision date',[p['date'] for p in points],index=len(points)-1)
    point=next(p for p in points if p['date']==day)
    context=(selected,day,role)
    if st.session_state.get('console_context')!=context:
        st.session_state['console_context']=context
        st.session_state.pop('console_result',None)
    portfolio=st.session_state.get('console_portfolios',{}).get((selected,role))
    news_path=paths['news']
    news_store=NewsStore(news_path) if news_path.exists() else None
    news_master=load_master_data()[0] if news_store is not None else None
    news_mode = st.radio('News clock', ['current_news', 'historical_decision'], horizontal=True,
        help='Current news updates every 30 seconds with its own clock. Historical news uses only evidence received by the selected market decision.')
    news_offset = st.number_input('News page (40 events per page)', min_value=1, value=1, step=1)
    payload=project_run(point,manifest,points,role,
        log=bundle['log'],
        portfolio=portfolio,result=st.session_state.get('console_result'),
        report=bundle['report'],
        news_store=news_store,news_master=news_master, news_mode=news_mode, news_offset=(news_offset-1)*40)
    st.caption(f'Run {selected[:16]} · decision {point["evaluation_timestamp"]} · role {role}')
    st.caption(f'News: {news_mode} · {(payload.get("news") or {}).get("as_of", "unavailable")} · Market decision: {point["evaluation_timestamp"]}')
    # What the last manual refresh actually achieved. A refresh that could not
    # reach every source must say which ones, or it implies a completeness it
    # did not deliver.
    # Acquisition is asked for, not performed here. The page acknowledges
    # immediately and reports what the worker is doing, rather than blocking a
    # web request on eleven network fetches.
    _asked = st.session_state.get('news_acquire_request')
    if _asked and news_store is not None:
        _progress = (news_store if isinstance(news_store, NewsStore)
                     else NewsStore(news_store)).acquisition_progress(
            _asked.get('request_id'))
        _state = _progress.get('state', 'unknown')
        if _asked.get('state') == 'rate_limited':
            st.caption(f"Acquisition not requested: {_asked.get('note', '')}")
        elif _state in ('pending', 'running'):
            st.info(f"Acquisition requested ({_state}); the worker is serving "
                    f"it. This page keeps showing stored data until it lands.")
        elif _state == 'done':
            _done = _progress.get('progress') or {}
            _line = (f"Acquisition finished: "
                     f"{len(_done.get('fetched') or [])} fetched, "
                     f"{len(_done.get('unchanged') or [])} unchanged, "
                     f"{_done.get('new_stories', 0)} new stor(y/ies)")
            _bad = ((_done.get('failed') or {}), (_done.get('timed_out') or []),
                    (_done.get('skipped_for_budget') or []))
            if any(_bad):
                _line += (f" — failed: {', '.join(_bad[0]) or 'none'}"
                          f"; timed out: {', '.join(_bad[1]) or 'none'}"
                          f"; NOT contacted: {', '.join(_bad[2]) or 'none'}")
                st.warning(_line)
            else:
                st.caption(_line)
    event=console(payload=payload,key='original_console',default=None)
    if isinstance(event,dict) and event.get('id')!=st.session_state.get('console_last_event'):
        st.session_state['console_last_event']=event.get('id')
        try:
            if event.get('run_id')!=selected or event.get('date')!=day:
                raise ValueError('Stale request; retry for the selected run and date')
            # Three distinct operations. Only `news_acquire` touches a
            # network, and even it does not fetch here -- it QUEUES a request
            # that the worker serves, so N browser tabs produce one
            # acquisition instead of N fetch storms.
            if event.get('op') in ('news_project', 'news_refresh'):
                # Re-project stored data. This is what the 30-second display
                # timer does; it was wired to a forced fetch of every source,
                # per tab. `news_refresh` is accepted as the old name.
                _news_sources.clear()
                st.rerun()
            if event.get('op')=='news_acquire':
                if news_store is None:
                    raise ValueError('No news store is connected')
                # NOT `from ... import NewsStore`: that name is already bound
                # at module level, and re-importing it inside this function
                # makes it local for the WHOLE function -- the
                # `NewsStore(news_path)` call further up then raised
                # UnboundLocalError and the console failed to render.
                from seraph.news.acquisition import _now as _news_now
                # Same defect, same fix: this is already an open store.
                _acq = (news_store if isinstance(news_store, NewsStore)
                        else NewsStore(news_store))
                _asked = _acq.request_acquisition(
                    reason='console', requested_by='console', now=_news_now())
                st.session_state['news_acquire_request'] = _asked
                st.rerun()
            # --- the role ACTIONS -----------------------------------
            # A review queue on screen is not a review workflow and a
            # scenario function nothing can supply inputs to is not a
            # scenario feature. These three are what make them one. The
            # rules about who may do what live in seraph/news/workflows.py,
            # not here, so they can be tested without a browser.
            if event.get('op') in ('news_review', 'news_scenario', 'news_export'):
                if news_store is None:
                    raise ValueError('No news store is connected')
                result = _news_action(event, role, news_store, news_master,
                                      payload)
                # The console correlates a reply to its request by
                # `context.request_id`; without it the page never
                # acknowledges the operation and the status line reports
                # whatever the PREVIOUS one left behind.
                result.setdefault('context', dict(
                    run_id=selected, date=day, role=role,
                    request_id=event.get('id')))
                st.session_state['console_result'] = result
            elif event.get('op')=='role':
                new_role=event.get('role')
                if new_role not in ('retail','institutional','regulator'):raise ValueError('Unknown role')
                st.session_state['console_role']=new_role
            else:
                result=dispatch(store,point,role,event)
                st.session_state['console_result']=result
                if result['kind']=='portfolio':
                    st.session_state.setdefault('console_portfolios',{})[(selected,role)]=result['value']
                # A write changed durable state this bundle has cached.
                if result['kind']=='action':
                    _bundle.clear()
        except (ValueError,TypeError,KeyError,PermissionError) as exc:
            # PermissionError included: a role action sent while the role
            # is mid-switch must come back as a readable refusal, not as an
            # uncaught exception that replaces the whole console.
            st.session_state['console_result']={
                'error':str(exc),
                'context':dict(run_id=selected,date=day,role=role,
                               request_id=event.get('id'))}
        st.rerun()
    if not point['composite']:st.warning('No composite: original inputs unavailable.')
    if portfolio is None and point['portfolio'] is None:st.info('No user holdings supplied. Use TOOLS in the console to calculate portfolio coverage.')
    news=payload.get('news') or {}
    if news.get('status')=='connected':
        st.caption('News channel CONNECTED: '
                   +', '.join(news.get('connected_surfaces') or [])
                   +'. Still fabricated: '
                   +(', '.join(news.get('preview_surfaces') or []) or 'none')
                   +'. Original fitted model artifacts are reused in historical '
                    'mode; PostgreSQL fresh-data execution is not verified.')
    elif news.get('status')=='empty':
        # Connected but with nothing to show at THIS decision time is not the
        # same as having no news channel at all, and conflating them hides
        # whichever one is actually true.
        st.caption('News channel connected, nothing visible at this decision '
                   'time ('+str(news.get('reason'))+'). Map/sector previews '
                   'remain fabricated.')
    else:
        st.caption('News channel not connected ('+str(news.get('reason'))+'). '
                   'Map/sector previews remain fabricated. Original fitted '
                   'model artifacts are reused in historical mode.')


if __name__=='__main__': main()
