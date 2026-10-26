# C12 — Redesigned console: RISK CONSOLE — the instrument panel (FR42-FR49).
"""The existing custom component, embedded — not reimplemented.

Several workflows live **only** in `console_component/` and reach the user
through nothing else in the product:

* the FR49 **regulator action journal** (`action`),
* the **pillar shock simulator** (`shock`, C11/C9),
* the **counterfactual policy simulator** (`policy`, regulator),
* **ad-hoc portfolio coverage** from pasted holdings (`portfolio`) — distinct
  from the *saved* portfolios on the Workspace screen,
* the news **role actions** (`news_review`, `news_scenario`, `news_export`)
  and queued acquisition (`news_acquire`),
* the risk map / globe itself, and the eight views that hang off it.

Rebuilding those natively would mean a second implementation of workflows the
regression suite already covers through `dispatch` and `_news_action`, which
is the duplication this work is explicitly not allowed to create. So this
screen declares the same component against the same payload and runs the same
event loop.

**It therefore looks like the original console inside its frame**, because it
*is* the original renderer. That is stated on screen rather than disguised:
the surrounding chrome is the redesigned system, the instrument inside it is
the existing one.

`_news_action` and `store_paths` are imported from `prototype_app` for the
same reason: they are the working implementations, and a copy here would be a
thing that drifts. Nothing in this module writes to Classic or changes its
behaviour — the import direction is one-way.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from seraph.dashboard.console_backend import (
    dispatch,
    news_branch,
    project_run,
    sector_analysis,
)
from seraph.news import NewsStore
from seraph.news.registry import load_master_data
from seraph.orchestration.prototype import clean
from seraph.orchestration.run_store import RunStore

from . import components as C, data

#: How long a built news branch stays reusable. Matches the other reads.
NEWS_TTL_SECONDS = 30

#: Whether the F2 layer is attached when the console is first opened. Off,
#: because attaching it costs ~50 s on a warm store — see the toggle.
_CONSOLE_ATTACH_NEWS_DEFAULT = False

#: Declared against the SAME directory Classic's console uses. A second copy
#: of the component would be a second thing to keep in step with the payload.
_COMPONENT_PATH = Path(__file__).resolve().parents[1] / "console_component"
_console = components.declare_component("seraph_console_redesign",
                                        path=str(_COMPONENT_PATH))

#: Operations the component can emit, and who the backend lets invoke them.
#: Listed for the reader only — `dispatch` and `WORKFLOW_ROLES` enforce it.
OPERATIONS = ("portfolio", "shock", "policy", "action", "role",
              "news_project", "news_refresh", "news_acquire", "news_review",
              "news_scenario", "news_export")


@st.cache_data(ttl=NEWS_TTL_SECONDS, show_spinner=False)
def _news_branch(news_path: str, point: dict, role: str, news_mode: str,
                 news_offset: int, flags: dict) -> dict:
    """The F2 branch of the console payload, built once per 30 seconds.

    **Why this is cached and the rest is not.** Measured on this installation:
    `project_run` takes 0.2 s without the news store and 46.5 s with it — the
    whole cost is walking ~2,000 eligible events and building the globe
    layers. The payload also carries `result`, which must be the operation
    the user just performed and so can never come from a cache. Caching the
    whole projection would therefore make every TOOLS operation wait 46 s for
    news it already had.

    `payload['news']` is written once by `news_branch` and read by nothing
    else in `project_run`, so building it separately and assigning it back is
    the same payload, not a reconstruction of one. `clean()` is applied here
    because `project_run` normally applies it to the whole payload.

    In `current_news` mode `news_branch` saves an audit snapshot. Caching
    means one snapshot per 30 s rather than one per render — and the snapshot
    still describes exactly the payload that was served, because that payload
    is this one.
    """
    store = NewsStore(Path(news_path))
    master = load_master_data()[0]
    return clean(news_branch(point, store=store, master=master, role=role,
                             news_mode=news_mode, news_offset=news_offset,
                             hawkes_sector_flags=flags))


def render(*, role: str, archive_path, news_path, run_id: str | None,
           date: str | None, news_mode: str, news_offset: int,
           sector_archive_as_of: str | None = None) -> str | None:
    """Returns the role the component asked to switch to, or None."""
    C.html_block(
        '<div class="rd-topbar"><div>'
        '<p class="rd-eyebrow">SERAPH · redesigned console</p>'
        '<h1>Risk console</h1>'
        '<p class="rd-panel-sub" style="margin-top:4px">'
        'the instrument panel — risk map, signal feed, pillars, exposure, '
        'forecasts, tools and method</p></div>'
        f'<div class="rd-topbar-right">{C.chip("role", role)}'
        f'{C.chip("news clock", news_mode)}</div></div>')

    if not run_id or not date:
        with C.panel("No decision selected", "risk console"):
            C.html_block(C.unavailable(
                "a run and decision date are required",
                "the console is bound to one coherent run/as-of bundle, and "
                "the backend refuses a stale context",
                "choose a run and date in the sidebar"))
        return None

    store = RunStore(str(archive_path))
    runs = [r for r in store.runs() if r["status"] == "complete"]
    match = next((r for r in runs if r["id"] == run_id), None)
    if match is None:
        with C.panel("Run unavailable", "risk console"):
            C.html_block(C.unavailable("no such complete run", str(run_id)))
        return None

    bundle = data.run_bundle(archive_path, run_id, role)
    points = bundle["points"]
    point = next((p for p in points if p["date"] == date), None)
    if point is None:
        with C.panel("Decision unavailable", "risk console"):
            C.html_block(C.unavailable(
                "this run has no decision on that date", str(date)))
        return None

    C.html_block(
        '<div class="rd-card rd-card--flat" style="margin-bottom:12px">'
        '<p class="rd-reason">The panel below is the <b>existing</b> console '
        'renderer, embedded rather than rebuilt: the regulator action journal '
        '(FR49), the shock and policy simulators, ad-hoc portfolio coverage '
        'and the news role actions exist only here, and reimplementing them '
        'would create a second copy of workflows the regression suite already '
        'covers. It keeps its own visual language inside the frame because it '
        'is the original instrument, not a restyled imitation of one.</p>'
        '</div>')

    # The two Streamlit-native panels Classic feeds into the payload. They
    # render their own controls and return what the component displays.
    measured = sector_analysis(point["evaluation_timestamp"],
                               sector_archive_as_of)
    if sector_archive_as_of:
        C.html_block(
            f'<div style="margin-bottom:10px">'
            f'{C.chip("sector basis", "RETROSPECTIVE ARCHIVE", tone="warn")}'
            f'</div>'
            f'<p class="rd-panel-note">{C.esc(measured.get("analysis_note"))}</p>')
    with st.expander("Institution exposures", expanded=False):
        from seraph.dashboard.institution_ui import panel as institution_panel
        institution_decomposition = institution_panel(role,
                                                      flags=measured["flags"])
    with st.expander("Directed contagion network (F07)", expanded=False):
        from seraph.dashboard.network_ui import panel as network_panel
        directed_network = network_panel(role, point["evaluation_timestamp"])

    # The F2 layer is opt-in, and the reason is measured, not aesthetic: on
    # this store the branch takes ~50 s to build because the aggregates
    # describe every eligible event by design (so a documented exposure
    # cannot disappear by being on another page). Without it the console —
    # globe, pillars, exposure, forecasts, tools, the action journal — opens
    # in about a fifth of a second. With it attached the news surfaces and
    # role actions work. The screen says which state it is in; it does not
    # pretend the channel is absent when it is merely not attached here.
    # `key` alone, with no `value`. Passing `value=` read from the SAME
    # session-state key makes the widget fight itself: on the rerun after a
    # click Streamlit re-applies the passed default over the new widget state,
    # so the toggle flips back and never turns on. With a key, Streamlit owns
    # the state and seeds it from `_CONSOLE_ATTACH_NEWS_DEFAULT` once.
    st.session_state.setdefault("rd_console_attach_news",
                                _CONSOLE_ATTACH_NEWS_DEFAULT)
    attach_news = st.toggle(
        "Attach the news channel (F2) to the console",
        key="rd_console_attach_news",
        help="Off: the console opens immediately and the news surfaces read "
             "NOT CONNECTED. On: the news map layer, signal feed and news "
             "role actions work, and the first build takes about a minute "
             "on this store.")
    store_present = Path(news_path).exists()
    news_store = (NewsStore(news_path)
                  if (attach_news and store_present) else None)
    news_master = load_master_data()[0] if news_store is not None else None
    if not attach_news:
        C.html_block(
            '<p class="rd-panel-note">The news channel is <b>not attached to '
            'this view</b>. That is a choice made here, not a statement that '
            'the channel is unavailable — the News intelligence screen reads '
            'it, and the surfaces below will say NOT CONNECTED, which is true '
            'of this view.</p>')
    elif not store_present:
        C.html_block(C.unavailable(
            "no news store to attach",
            f"nothing exists at {news_path}"))

    active = st.session_state.get("rd_active_portfolio")
    holdings = overlay = portfolio_context = None
    if active:
        resolved = data.resolve_active_portfolio(
            active, role, at=point["evaluation_timestamp"],
            flags=measured["flags"])
        if resolved["available"]:
            holdings = resolved["holdings"]
            overlay = resolved["overlay"]
            portfolio_context = resolved["context"]

    # An ad-hoc `portfolio` result from the TOOLS panel wins over the saved
    # one, the same precedence Classic applies: the user just computed it.
    computed = st.session_state.get("rd_console_portfolios", {}).get((run_id, role))
    if computed is not None:
        overlay = computed

    # Built WITHOUT the news store (0.2 s) and then given the cached F2
    # branch, so an operation's result is always fresh while the expensive
    # news walk is paid once per TTL. See `_news_branch`.
    payload = project_run(
        point, match["manifest"], points, role,
        log=bundle["log"], report=bundle["report"],
        portfolio=overlay, holdings=holdings,
        portfolio_context=portfolio_context,
        institution_decomposition=institution_decomposition,
        contagion_network=directed_network,
        result=st.session_state.get("rd_console_result"),
        sector_archive_as_of=sector_archive_as_of)
    if news_store is not None:
        with st.spinner("Building the news channel for the console…"):
            payload["news"] = _news_branch(
                str(news_path), point, role, news_mode, news_offset,
                measured["flags"])

    event = _console(payload=payload, key="redesign_console", default=None)
    switch_to = None
    if isinstance(event, dict) and event.get("id") != st.session_state.get(
            "rd_console_last_event"):
        st.session_state["rd_console_last_event"] = event.get("id")
        switch_to = _handle(event, role, run_id, date, store, point,
                            news_store, news_master, payload)
        st.rerun()

    _status(payload, news_store)
    return switch_to


# --------------------------------------------------------------------------
def _handle(event, role, run_id, date, store, point, news_store, news_master,
            payload) -> str | None:
    """One component event, through the SAME paths Classic uses.

    A refusal is recorded as a readable result bound to the request id, not
    raised: the component correlates a reply by `context.request_id`, and
    without one the panel reports whatever the previous operation left behind.
    """
    try:
        if event.get("run_id") != run_id or event.get("date") != date:
            raise ValueError("Stale request; retry for the selected run and date")

        op = event.get("op")

        if op == "role":
            wanted = event.get("role")
            if wanted not in ("retail", "institutional", "regulator"):
                raise ValueError("Unknown role")
            return wanted

        if op in ("news_project", "news_refresh"):
            # Re-project stored data. NOT a fetch: this is what the display
            # timer asks for, and wiring it to a forced fetch per tab is the
            # defect that produced N fetch storms for N open tabs.
            #
            # The cache is deliberately NOT cleared here. `bridge.js` fires
            # this on a 30-second display timer, and the branch costs ~50 s to
            # rebuild on this store, so clearing would put the console into a
            # permanent rebuild it never finishes before the next tick.
            # Classic can clear its `_news_sources` cheaply because that
            # caches only the store handle, not the projection. Here the TTL
            # *is* the re-projection interval, and it matches the timer.
            return None

        if op == "news_acquire":
            if news_store is None:
                raise ValueError("No news store is connected")
            from seraph.news.acquisition import _now as news_now
            asked = news_store.request_acquisition(
                reason="console", requested_by="redesign-console",
                now=news_now())
            st.session_state["rd_news_acquire_request"] = asked
            # QUEUED, not fetched: N browser tabs must produce one
            # acquisition rather than N fetch storms. The worker serves it
            # and the screen keeps showing stored data until it lands, so
            # the cached branch stays valid until then.
            return None

        if op in ("news_review", "news_scenario", "news_export"):
            if news_store is None:
                raise ValueError("No news store is connected")
            # Classic's implementation, imported rather than copied.
            from seraph.dashboard.prototype_app import _news_action
            result = _news_action(
                event, role, news_store, news_master, payload,
                st.session_state.setdefault("rd_news_analyses", {}))
            result.setdefault("context", dict(
                run_id=run_id, date=date, role=role,
                request_id=event.get("id")))
            st.session_state["rd_console_result"] = result
            return None

        result = dispatch(store, point, role, event)
        st.session_state["rd_console_result"] = result
        if result["kind"] == "portfolio":
            st.session_state.setdefault(
                "rd_console_portfolios", {})[(run_id, role)] = result["value"]
            # An ad-hoc calculation supersedes a saved selection on screen.
            st.session_state.pop("rd_active_portfolio", None)
    except (ValueError, TypeError, KeyError, PermissionError) as exc:
        # PermissionError included: a role action sent mid-switch must come
        # back as a readable refusal, not an uncaught exception that replaces
        # the whole console.
        st.session_state["rd_console_result"] = {
            "error": str(exc),
            "context": dict(run_id=run_id, date=date, role=role,
                            request_id=event.get("id"))}
    return None


def _status(payload, news_store) -> None:
    """What the last acquisition request achieved, and the channel's state."""
    asked = st.session_state.get("rd_news_acquire_request")
    if asked and news_store is not None:
        progress = news_store.acquisition_progress(asked.get("request_id"))
        state = progress.get("state", "unknown")
        if asked.get("state") == "rate_limited":
            C.html_block(f'<p class="rd-panel-note">Acquisition not '
                         f'requested: {C.esc(asked.get("note", ""))}</p>')
        elif state in ("pending", "running"):
            C.html_block(
                f'<div style="margin-top:10px">'
                f'{C.chip("acquisition", state, tone="warn")}</div>'
                f'<p class="rd-panel-note">The worker is serving it. This page '
                f'keeps showing stored data until it lands.</p>')
        elif state == "done":
            done = progress.get("progress") or {}
            bad = ((done.get("failed") or {}), (done.get("timed_out") or []),
                   (done.get("skipped_for_budget") or []))
            line = (f"{len(done.get('fetched') or [])} fetched, "
                    f"{len(done.get('unchanged') or [])} unchanged, "
                    f"{done.get('new_stories', 0)} new")
            if any(bad):
                line += (f" — failed: {', '.join(bad[0]) or 'none'}; timed "
                         f"out: {', '.join(bad[1]) or 'none'}; NOT contacted: "
                         f"{', '.join(bad[2]) or 'none'}")
            C.html_block(f'<p class="rd-panel-note">Acquisition finished: '
                         f'{C.esc(line)}</p>')

    news = payload.get("news") or {}
    status = news.get("status")
    if status == "connected":
        C.html_block(
            f'<p class="rd-panel-note">News channel CONNECTED: '
            f'{C.esc(", ".join(news.get("connected_surfaces") or []))}. Still '
            f'fabricated: '
            f'{C.esc(", ".join(news.get("preview_surfaces") or []) or "none")}.'
            f'</p>')
    elif status == "empty":
        C.html_block(
            f'<p class="rd-panel-note">News channel connected, nothing '
            f'visible at this decision time '
            f'({C.esc(news.get("reason"))}).</p>')
    else:
        C.html_block(
            f'<p class="rd-panel-note">News channel not connected '
            f'({C.esc(news.get("reason"))}). The map layer remains '
            f'FABRICATED and is labelled so.</p>')

    result = payload.get("result")
    if isinstance(result, dict) and result.get("error"):
        st.warning(result["error"])
    discarded = payload.get("discarded_result")
    if discarded:
        C.html_block(C.unavailable("result discarded",
                                   str(discarded.get("reason"))))
    C.html_block(
        f'<p class="rd-panel-note rd-num">Run {C.esc(payload.get("run_id", "")[:16])} '
        f'· decision {C.esc(payload.get("timestamp"))} · role '
        f'{C.esc(payload.get("role"))}</p>')
