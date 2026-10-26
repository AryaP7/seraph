# C12 — Redesigned console: the host (FR39-FR49).
"""The SECOND frontend. Classic is unchanged and remains the fallback.

    .\\launch_redesign.ps1            # this app, port 8520
    .\\launch_prototype.ps1           # Classic, port 8512 — unchanged

**The console is the UI.** SERAPH's interface is the 3D console, so the
redesigned screens are entries in *its* nav — OVERVIEW, EARLY WARNING,
WORKSPACE, EVALUATION, HEALTH alongside RISK MAP, CONSOLE, SIGNAL FEED,
PILLARS, EXPOSURE, FORECASTS, TOOLS, METHOD. This module is a thin host: it
builds one payload, serves one full-bleed component, and routes the events
that come back. There is no sidebar and no second navigation, because a
second navigation is what made the product look like a tab inside something
else.

The component is **forked** into this package
(`redesign/console_component/`) so that adding nav entries cannot change
Classic. The backends are not forked: every number still comes from
`console_backend.project_run`, `dispatch`, `prediction_surface`,
`experiment_surface` and `health_surface`.

**Running both at once is safe.** `news_service.ensure_worker()` probes the OS
lock and stands aside when a supervisor already owns the store.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from seraph.dashboard.console_backend import (
    dispatch,
    news_branch,
    project_run,
    sector_analysis,
)
from seraph.dashboard.redesign import REDESIGN_VERSION
from seraph.dashboard.redesign import component_views as V
from seraph.dashboard.redesign import component_workspace as W
from seraph.dashboard.redesign import current_session as CS
from seraph.dashboard.redesign import data, news_data
from seraph.news import NewsStore
from seraph.news.registry import load_master_data
from seraph.orchestration.prototype import clean
from seraph.orchestration.run_store import RunStore

CACHE_TTL_SECONDS = 30
NEWS_TTL_SECONDS = 30

ROLES = ("retail", "institutional", "regulator")
SECTOR_DECISION_TIME = "Selected market decision"
SECTOR_RETROSPECTIVE = "Retrospective analytical archive"
SECTOR_BASES = (SECTOR_DECISION_TIME, SECTOR_RETROSPECTIVE)
NEWS_CLOCKS = ("current_news", "historical_decision")
NEWS_LAYERS = ("off", "on")

_COMPONENT_PATH = Path(__file__).resolve().parent / "console_component"
_console = components.declare_component("seraph_redesigned_console",
                                        path=str(_COMPONENT_PATH))


# --------------------------------------------------------------------------
# cached reads
# --------------------------------------------------------------------------
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _runs(archive_path: str):
    return [dict(id=r["id"], manifest=r["manifest"])
            for r in data.complete_runs(archive_path)]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _bundle(archive_path: str, run_id: str, role: str):
    return data.run_bundle(archive_path, run_id, role)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _forecast():
    return data.forecast_state()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _evaluation(role: str):
    return data.evaluation_state(role)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _health():
    return data.health_state()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _acquisition(news_path: str):
    return news_data.acquisition_state(news_path)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _latest_session(live_path: str):
    """The newest readable vintage per pillar. Short TTL: the daily job can
    write a new one while the page is open."""
    return CS.latest_session(live_path)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _market_jobs():
    return data.market_jobs_state()


@st.cache_data(ttl=NEWS_TTL_SECONDS, show_spinner=False)
def _news(news_path: str, point: dict, role: str, mode: str, offset: int,
          flags: dict) -> dict:
    """The F2 branch, built once per TTL.

    Measured on this installation: `project_run` is 0.2 s without the news
    store and ~50 s with it, because the aggregates describe every eligible
    event by design. `payload['news']` is written once by `news_branch` and
    read by nothing else in `project_run`, so building it separately and
    assigning it back is the same payload, not a reconstruction of one.

    The cache is NOT dropped on the component's 30-second re-projection
    timer: clearing it there would leave the console rebuilding something it
    never finishes before the next tick. The TTL is the interval instead.
    """
    store = NewsStore(Path(news_path))
    master = load_master_data()[0]
    return clean(news_branch(point, store=store, master=master, role=role,
                             news_mode=mode, news_offset=offset,
                             hawkes_sector_flags=flags))


# --------------------------------------------------------------------------
def _import_quality(body) -> list:
    """Findings the pure parser cannot make, for the import preview.

    Re-parses the uploaded text rather than reaching into the dispatcher's
    result, because `parse_holdings` is pure and cheap and the alternative is
    threading a second return value through the backend for a display
    concern.
    """
    if not body:
        return []
    try:
        from seraph.decision_support.portfolio_quality import inspect_rows, summary
        from seraph.decision_support.workspace import parse_holdings
        preview = parse_holdings(body, source_name="preview")
        return summary(inspect_rows(preview.accepted, priced=_priced_symbols()))
    except Exception as exc:                                  # noqa: BLE001
        return [f"import quality could not be checked: "
                f"{type(exc).__name__}: {exc}"]


@st.cache_data(ttl=600, show_spinner=False)
def _priced_symbols():
    """Symbols the price corpus knows at its latest session, or None.

    `None` means the check could not run, and `inspect_rows` reports that
    rather than letting an unchecked symbol pass as verified.
    """
    try:
        import asyncio

        import asyncpg

        from seraph.store.bootstrap import DEFAULT_DSN

        async def read():
            conn = await asyncpg.connect(DEFAULT_DSN, timeout=5)
            try:
                day = await conn.fetchval("SELECT MAX(date) FROM daily_prices")
                rows = await conn.fetch(
                    "SELECT symbol FROM daily_prices WHERE date=$1", day)
                return {r["symbol"] for r in rows}
            finally:
                await conn.close()
        return asyncio.run(read())
    except Exception:                                         # noqa: BLE001
        return None


def _state():
    """Selection state. It lives in session state because the component is
    the only UI — there is no sidebar holding it."""
    s = st.session_state
    s.setdefault("rd_role", "retail")
    s.setdefault("rd_sector_basis", SECTOR_DECISION_TIME)
    s.setdefault("rd_news_clock", "current_news")
    # ON by default. With the channel detached the map, sector-stress and
    # geography surfaces fall back to the console's illustrative layer and
    # are labelled FABRICATED -- which is true of that view, but it is not
    # what this installation actually has. Attached, `preview_surfaces` is
    # empty and all four surfaces are real, so the honest default is the one
    # that shows the real channel.
    s.setdefault("rd_news_layer", "on")
    s.setdefault("rd_news_page", 1)
    return s


def _sector_as_of(basis: str) -> str | None:
    """The retrospective cutoff, or None for decision-time.

    `None` is not "no basis" — it is the decision-time basis, which is what
    `sector_analysis` treats as "only artefacts available by the selected
    market decision".
    """
    if basis != SECTOR_RETROSPECTIVE:
        return None
    from datetime import datetime

    from seraph.shared_types import IST
    return datetime.now(IST).isoformat()


def _workspace_bundle(archive_path, run_id, date, role) -> dict:
    """One read of the three durable workflows, for the WORKSPACE view."""
    s = st.session_state

    def call(op, **args):
        try:
            return data.workspace_call(archive_path, run_id, date, role, op,
                                       **args)
        except (ValueError, TypeError, KeyError, PermissionError) as exc:
            return {"error": str(exc)}

    identity = call("ws_portfolios")
    if identity.get("error"):
        return dict(error=identity["error"])

    from datetime import datetime

    from seraph.shared_types import IST

    portfolios = identity.get("value") or []
    portfolio_id = s.get("rd_portfolio_id") or (
        portfolios[0]["portfolio_id"] if portfolios else None)
    holdings = {}
    if portfolio_id:
        holdings = call("ws_holdings",
                        portfolio_id=portfolio_id).get("value") or {}

    scenarios = (call("sc_list").get("value") or []) if role != "retail" else []
    scenario_id = s.get("rd_scenario_id") or (
        scenarios[0]["scenario_id"] if scenarios else None)
    cases = (call("case_list").get("value") or []) if role == "regulator" else []
    case_id = s.get("rd_case_id") or (cases[0]["case_id"] if cases else None)

    return dict(
        identity_note=(identity.get("identity") or {}).get("note", ""),
        portfolios=portfolios, portfolio_id=portfolio_id, holdings=holdings,
        scenarios=scenarios, scenario_id=scenario_id,
        scenario_execution=s.get("rd_scenario_execution"),
        cases=cases, case_id=case_id, preview=s.get("rd_ws_preview"),
        now_ist=datetime.now(IST).replace(microsecond=0).isoformat())


# --------------------------------------------------------------------------
def _handle(event, archive_path, run_id, date, role, store, point,
            news_store, news_master, payload) -> None:
    """One component event, through the same backend paths Classic uses.

    A refusal is recorded as a readable result bound to the request id, not
    raised: the component correlates a reply by `context.request_id`, and
    without one the status line reports whatever the previous operation left.
    """
    s = st.session_state
    op = event.get("op")
    try:
        # Selection changes are re-projections, not computations, so they are
        # not checked against the run/date context the compute ops are.
        if op == "rd_select":
            field, value = event.get("field"), event.get("value")
            mapping = {"run": "rd_run_id", "date": "rd_date",
                       "sector_basis": "rd_sector_basis",
                       "news_clock": "rd_news_clock",
                       "news_layer": "rd_news_layer",
                       "portfolio_id": "rd_portfolio_id",
                       "scenario_id": "rd_scenario_id",
                       "case_id": "rd_case_id"}
            if field not in mapping:
                raise ValueError(f"unknown selection {field!r}")
            s[mapping[field]] = value
            if field == "run":
                s.pop("rd_date", None)        # a date belongs to one run
            return

        if op == "role":
            wanted = event.get("role")
            if wanted not in ROLES:
                raise ValueError("Unknown role")
            s["rd_role"] = wanted
            return

        if event.get("run_id") != run_id or event.get("date") != date:
            raise ValueError("Stale request; retry for the selected run and date")

        if op in ("news_project", "news_refresh"):
            # Re-project stored data. NOT a fetch, and the cached branch is
            # kept: this arrives on a 30-second timer and the branch costs
            # ~50 s to rebuild.
            return

        if op == "news_acquire":
            if news_store is None:
                raise ValueError("No news store is attached to this view")
            from seraph.news.acquisition import _now as news_now
            s["rd_news_acquire"] = news_store.request_acquisition(
                reason="console", requested_by="redesign-console",
                now=news_now())
            return

        if op in ("news_review", "news_scenario", "news_export"):
            if news_store is None:
                raise ValueError("No news store is attached to this view")
            from seraph.dashboard.prototype_app import _news_action
            result = _news_action(event, role, news_store, news_master,
                                  payload, s.setdefault("rd_news_analyses", {}))
            result.setdefault("context", dict(run_id=run_id, date=date,
                                              role=role,
                                              request_id=event.get("id")))
            s["rd_console_result"] = result
            return

        # The two composite forms a flat control set cannot express.
        if op == "rd_scenario_save":
            if not str(event.get("justification", "")).strip():
                raise ValueError(
                    "An assumption needs a justification: an unlabelled "
                    "hypothetical cannot be told apart from a measurement "
                    "later")
            s["rd_console_result"] = dispatch(store, point, role, dict(
                id=event["id"], run_id=run_id, date=date, op="sc_save",
                name=event.get("name"), kind="rank_shock",
                steps=[dict(pillar=event.get("pillar"),
                            delta=event.get("delta"),
                            horizon=int(event.get("horizon") or 1))],
                assumptions=[dict(key="shock", value=event.get("delta"),
                                  unit="rank",
                                  justification=event["justification"])]))
            return

        if op == "rd_case_evidence":
            s["rd_console_result"] = dispatch(store, point, role, dict(
                id=event["id"], run_id=run_id, date=date, op="case_evidence",
                case_id=event.get("case_id"),
                expected_version=int(event.get("expected_version") or 0),
                refs=[dict(kind=event.get("kind"),
                           ref_id=event.get("ref_id"),
                           revision=event.get("revision"))]))
            return

        result = dispatch(store, point, role, event)
        s["rd_console_result"] = result
        if result.get("kind") == "portfolio":
            s.setdefault("rd_console_portfolios", {})[(run_id, role)] = \
                result["value"]
        if op == "ws_preview":
            preview = dict(result.get("value") or {})
            preview["quality"] = _import_quality(event.get("body"))
            s["rd_ws_preview"] = preview
        if op == "sc_run":
            s["rd_scenario_execution"] = result.get("value")
    except (ValueError, TypeError, KeyError, PermissionError) as exc:
        # PermissionError included: a role action sent mid-switch must come
        # back as a readable refusal, not an uncaught exception that replaces
        # the whole console.
        s["rd_console_result"] = {
            "error": str(exc),
            "context": dict(run_id=run_id, date=date, role=role,
                            request_id=event.get("id"))}


# --------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="SERAPH", layout="wide",
                       initial_sidebar_state="collapsed")
    # The console is the whole page: no sidebar, no second navigation.
    st.markdown(
        "<style>[data-testid='stSidebar'],[data-testid='stHeader']{display:none}"
        "[data-testid='stAppViewContainer'] .block-container{padding:0;"
        "max-width:100%}.stApp{background:#080D16}</style>",
        unsafe_allow_html=True)

    s = _state()
    paths = data.store_paths()
    from seraph.dashboard import news_service
    news_service.ensure_worker(paths["news"])

    role = s["rd_role"]
    runs = _runs(str(paths["archive"]))
    if not runs:
        st.error(f"No complete run in {paths['archive']}. "
                 f"`python scripts/run_prototype.py` produces one.")
        return
    run_ids = [r["id"] for r in runs]
    run_id = s.get("rd_run_id") if s.get("rd_run_id") in run_ids else run_ids[-1]
    s["rd_run_id"] = run_id
    manifest = next(r["manifest"] for r in runs if r["id"] == run_id)

    bundle = _bundle(str(paths["archive"]), run_id, role)
    points = bundle["points"]
    dates = [p["date"] for p in points]
    date = s.get("rd_date") if s.get("rd_date") in dates else dates[-1]
    s["rd_date"] = date
    point = next(p for p in points if p["date"] == date)

    sector_as_of = _sector_as_of(s["rd_sector_basis"])
    measured = sector_analysis(point["evaluation_timestamp"], sector_as_of)

    attach_news = s["rd_news_layer"] == "on"
    news_store = (NewsStore(paths["news"])
                  if attach_news and paths["news"].exists() else None)
    news_master = load_master_data()[0] if news_store is not None else None

    computed = s.get("rd_console_portfolios", {}).get((run_id, role))
    payload = project_run(
        point, manifest, points, role, log=bundle["log"],
        report=bundle["report"], portfolio=computed,
        result=s.get("rd_console_result"),
        sector_archive_as_of=sector_as_of)
    if news_store is not None:
        with st.spinner("Building the news channel…"):
            payload["news"] = _news(str(paths["news"]), point, role,
                                    s["rd_news_clock"],
                                    (s["rd_news_page"] - 1) * 40,
                                    measured["flags"])

    selection = dict(runs=run_ids, run_id=run_id, dates=dates, date=date,
                     sector_bases=list(SECTOR_BASES),
                     sector_basis=s["rd_sector_basis"],
                     news_clocks=list(NEWS_CLOCKS),
                     news_clock=s["rd_news_clock"],
                     news_layers=list(NEWS_LAYERS),
                     news_layer=s["rd_news_layer"],
                     role=role, version=REDESIGN_VERSION)

    session = _latest_session(str(paths["live"]))
    payload["redesign"] = dict(selection=selection, views={
        # The landing view. The archive replay is still one click away under
        # HISTORICAL, but it is no longer what the console opens on: a system
        # holding current pillar readings must not headline a 2020 replay.
        "current": V.current(session, CS.composite_status(session, paths["live"]),
                             _forecast(), payload.get("liveness") or {},
                             selection),
        "overview": V.overview(payload, selection),
        "warning": V.warning(_forecast()),
        "evaluation": V.evaluation(_evaluation(role)),
        "health": V.health(_health(), _acquisition(str(paths["news"])),
                           _market_jobs()),
        "workspace": W.workspace(
            _workspace_bundle(paths["archive"], run_id, date, role),
            role, selection),
    })

    event = _console(payload=payload, key="redesigned_console", default=None)
    if isinstance(event, dict) and event.get("id") != s.get("rd_last_event"):
        s["rd_last_event"] = event.get("id")
        _handle(event, paths["archive"], run_id, date, role,
                RunStore(str(paths["archive"])), point, news_store,
                news_master, payload)
        st.rerun()


if __name__ == "__main__":
    main()
