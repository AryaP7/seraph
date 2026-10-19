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
            st.metric('CSRS', (current.payload or {}).get('csrs',
                                                          'Unavailable'),
                      help=current.reason)
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


def main():
    st.set_page_config(page_title='SERAPH',layout='wide')
    st.markdown('<style>.block-container{max-width:1900px;padding-top:1rem}</style>',unsafe_allow_html=True)
    st.title('SERAPH')
    st.caption('Historical model outputs + explicitly tagged fabricated previews. Local role switching is not authentication. Experimental warnings are not validated crisis predictions.')
    path=Path(os.environ.get('SERAPH_PROTOTYPE_STORE',str(Path(__file__).resolve().parents[2]/'prototype_runs/seraph.sqlite')))
    if not path.exists():
        st.info('No persisted run. Execute scripts/run_prototype.py first.');return
    live_path=Path(os.environ.get('SERAPH_LIVE_STORE',
        str(Path(__file__).resolve().parents[2]/'prototype_runs/live.sqlite')))
    with st.expander('LIVE RUNTIME', expanded=live_path.exists()):
        live_revision=live_panel(live_path)
    if live_revision and st.session_state.get('live_revision')!=live_revision:
        # The revision moved, so there is genuinely new data. Record it rather
        # than rebuilding the page under the user: a silent rebase loses a
        # half-typed form, and the console keeps drafts across renders.
        st.session_state['live_revision']=live_revision
        st.session_state['live_revision_seen_at']=time.strftime('%H:%M:%S')
    store=RunStore(path)
    runs=_complete_runs(str(path))
    if not runs:
        st.info('No complete runs; resume the canonical command.');return
    selected=st.selectbox('Run',[r['id'] for r in runs])
    manifest=next(r['manifest'] for r in runs if r['id']==selected)
    role=st.session_state.setdefault('console_role','retail')
    bundle=_bundle(str(path),selected,role)
    points=bundle['points']
    day=st.selectbox('Historical decision date',[p['date'] for p in points],index=len(points)-1)
    point=next(p for p in points if p['date']==day)
    context=(selected,day,role)
    if st.session_state.get('console_context')!=context:
        st.session_state['console_context']=context
        st.session_state.pop('console_result',None)
    portfolio=st.session_state.get('console_portfolios',{}).get((selected,role))
    news_path=Path(os.environ.get('SERAPH_NEWS_STORE',
        str(Path(__file__).resolve().parents[2]/'prototype_runs/news-intelligence-pilot.sqlite')))
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
        _progress = NewsStore(news_store).acquisition_progress(
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
                _asked = NewsStore(news_store).request_acquisition(
                    reason='console', requested_by='console', now=_news_now())
                st.session_state['news_acquire_request'] = _asked
                st.rerun()
            if event.get('op')=='role':
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
        except (ValueError,TypeError,KeyError) as exc:
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
