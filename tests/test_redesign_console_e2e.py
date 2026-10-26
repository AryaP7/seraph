# End-to-end verification of the console-native redesigned frontend.
"""Every nav entry, against the real backends, for every role.

`test_redesign_console_native.py` pins the ARCHITECTURE by reading the files:
the component is forked, the nav has thirteen entries, every control has a
handler. That is structure, and structure passing is not the same as the
screen having something true to show.

This module answers the other question — does each of the thirteen views
actually get served, from the real stores, for each role, and do the
operations behind them work. So it:

* projects a real archived decision through `console_backend.project_run`
  for all three roles and checks that every payload field the thirteen views
  read is present (or legitimately withheld for that role);
* drives the WORKSPACE operations through `console_backend.dispatch` against
  a **disposable** store directory, including the create -> preview ->
  commit -> holdings round trip, and checks the refusals;
* reads EVALUATION, EARLY WARNING, HEALTH and NEWS from their own surfaces
  and checks each either carries data or states its absence with a reason.

The honesty rules are not re-asserted here; `test_redesign_overview.py` owns
them. What is asserted here is reachability and permission.

A test that needs something this installation may not have (a news store, a
saved prediction state) SKIPS with the reason rather than passing vacuously.
"""
from __future__ import annotations

import re

import pytest

from seraph.dashboard.console_backend import WORKFLOW_ROLES, project_run
from seraph.dashboard.redesign import component_views as V
from seraph.dashboard.redesign import component_workspace as W
from seraph.dashboard.redesign import data

ROLES = ("retail", "institutional", "regulator")

#: The thirteen nav entries, and who renders each one.
#:
#: `redesign` views are built in Python and carried in `payload['redesign']`.
#: `console` views are rendered by `bridge.js` from the payload directly —
#: for those the Python-side obligation is that the field they read is in the
#: payload, which is what `PAYLOAD_READS` below pins.
CONSOLE_VIEWS = ("map", "console", "feed", "pillars", "exposure",
                 "forecasts", "tools", "method")
REDESIGN_VIEWS = ("current", "overview", "warning", "workspace",
                  "evaluation", "health")
ALL_VIEWS = CONSOLE_VIEWS + REDESIGN_VIEWS

#: What each console-rendered view reads out of the payload. Taken from the
#: `show()` branches in the forked `bridge.js`. A payload field dropped by a
#: backend change fails here instead of rendering an empty panel in a demo.
PAYLOAD_READS = {
    "map": ("news",),
    "console": ("view", "history", "liveness", "limitations"),
    "feed": ("news", "view"),
    "pillars": ("pillars", "mask", "view"),
    "exposure": ("portfolio",),
    "forecasts": ("predictions",),
    "tools": ("role",),
    "method": ("manifest", "context", "cutoff"),
}

#: Fields `gateway.ROLE_FIELDS` withholds from some roles. Absent for those
#: roles is correct and is not a missing field — see honesty rule 6.
WITHHELD = {"pillarScores", "shapley", "effectiveWeights", "spectral",
            "regimeProbabilities", "institutionDecomposition",
            "contagionNetwork", "variance", "ciLower", "ciUpper",
            "actionLog", "playbook", "preRegistrationHash"}

#: Top-level payload fields `project_run` withholds BY ROLE, and the fallback
#: the forked `bridge.js` renders in their place. Declared rather than
#: derived, so both a new gate and a removed one fail this module and have to
#: be a decision:
#:
#:   pillars     -> renderPillars reads `data.pillars?.[name]` and says
#:                  "Model internals are not supplied to this role."
#:   mask        -> same panel, same fallback
#:   limitations -> renderMethod defaults to the experimental-warning line
#:   manifest    -> renderMethod appends it only `if(data.manifest)`
#:   predictions -> the FORECASTS branch is `role==='retail' ? <message> :
#:                  table(data.predictions)`
GATED_TOP_LEVEL = {
    "retail": {"limitations", "pillars", "mask", "predictions", "manifest"},
    "institutional": {"manifest"},
    "regulator": set(),
}


# ==========================================================================
# fixtures — the real archive, and a disposable workspace
# ==========================================================================
@pytest.fixture(scope="module")
def archive():
    """The newest complete run in the configured archive."""
    paths = data.store_paths()
    runs = data.complete_runs(paths["archive"])
    if not runs:
        pytest.skip(f"no complete run in {paths['archive']}")
    return dict(paths=paths, run=runs[-1])


@pytest.fixture(scope="module")
def projected(archive):
    """One real decision, projected for each role.

    The news branch is deliberately NOT attached: it costs ~50 s to build on
    this installation and the views that need it are covered by the news
    tests below. `project_run` still writes `payload['news']` as an explicit
    absence, which is the shape those views must handle anyway.
    """
    run = archive["run"]
    out = {}
    for role in ROLES:
        bundle = data.run_bundle(archive["paths"]["archive"], run["id"], role)
        points = bundle["points"]
        payload = project_run(points[-1], run["manifest"], points, role,
                              log=bundle["log"], report=bundle["report"])
        out[role] = dict(payload=payload, points=points, point=points[-1])
    return out


@pytest.fixture
def disposable(tmp_path, monkeypatch):
    """A throwaway store directory for the workflow writes.

    `workspace_service._runs_dir()` honours `SERAPH_WORKSPACE_DIR`, so the
    identity registry, the portfolios, the scenarios and the regulator cases
    all land under `tmp_path` and this test writes nothing into
    `prototype_runs/`. Without this the suite would accumulate rows in the
    installation the demonstration runs against.
    """
    monkeypatch.setenv("SERAPH_WORKSPACE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def selection(archive):
    run = archive["run"]
    points = data.run_bundle(archive["paths"]["archive"], run["id"],
                             "regulator")["points"]
    return dict(runs=[run["id"]], run_id=run["id"],
                dates=[p["date"] for p in points], date=points[-1]["date"],
                sector_bases=["Selected market decision",
                              "Retrospective analytical archive"],
                sector_basis="Selected market decision",
                news_clocks=["current_news", "historical_decision"],
                news_clock="historical_decision",
                news_layers=["off", "on"], news_layer="off",
                role="regulator", version="test")


# ==========================================================================
# every nav entry is served
# ==========================================================================
def test_every_console_view_has_the_payload_it_reads(projected):
    """A console-rendered view whose payload field is gone renders empty.

    Checked at `regulator`, the one role nothing is withheld from, so this
    asserts the field exists at all rather than re-asserting the role gates
    that the next test owns.
    """
    payload = projected["regulator"]["payload"]
    missing = {view: [f for f in reads if f not in payload]
               for view, reads in PAYLOAD_READS.items()
               if any(f not in payload for f in reads)}
    assert missing == {}, f"payload fields missing: {missing}"


@pytest.mark.parametrize("role", ROLES)
def test_the_fields_withheld_from_a_role_are_exactly_the_declared_ones(
        projected, role):
    """Role gating is a decision, so a change to it must be made on purpose.

    A field that newly disappears for a role fails here rather than becoming
    a quietly empty panel; a gate that is lifted fails too, because showing a
    retail user the model internals is equally a decision.
    """
    payload = projected[role]["payload"]
    read = {f for reads in PAYLOAD_READS.values() for f in reads}
    absent = {f for f in read if f not in payload}
    assert absent == GATED_TOP_LEVEL[role], (
        f"{role}: withheld fields are {sorted(absent)}, declared "
        f"{sorted(GATED_TOP_LEVEL[role])}")


@pytest.mark.parametrize("role", ROLES)
def test_every_redesigned_view_renders_markup_from_the_real_payload(
        projected, selection, role, disposable):
    """The five added views, built the way `app.py` builds them.

    Markup, not a dict: `redesign_views.js` injects the string, so a view
    that returns nothing is a blank panel on screen.
    """
    payload = projected[role]["payload"]
    views = {
        "overview": V.overview(payload, dict(selection, role=role)),
        "warning": V.warning(data.forecast_state()),
        "evaluation": V.evaluation(data.evaluation_state(role)),
        "health": V.health(data.health_state(), {}, data.market_jobs_state()),
        "workspace": W.workspace(dict(portfolios=[], scenarios=[], cases=[],
                                      holdings={}, identity_note="",
                                      now_ist=""),
                                 role, dict(selection, role=role)),
    }
    for name, markup in views.items():
        assert isinstance(markup, str) and markup.strip(), (
            f"{role}/{name} rendered nothing")
        assert "rd-" in markup, (
            f"{role}/{name} carries no redesign markup — it would inherit "
            f"the console's own styling and read as a different screen")


def test_the_nav_and_the_renderers_agree(projected, selection, disposable):
    """Fourteen entries in the nav, fourteen views someone renders.

    The nav is read from the fork's markup, so adding a button without a
    renderer fails here rather than opening a blank screen.
    """
    from pathlib import Path
    fork = (Path(__file__).resolve().parents[1] / "seraph" / "dashboard" /
            "redesign" / "console_component" / "index.html")
    nav = re.findall(r'data-view="([a-z]+)"', fork.read_text(encoding="utf-8"))
    assert len(nav) == 14, f"expected fourteen nav entries, found {len(nav)}: {nav}"
    assert set(nav) == set(ALL_VIEWS), (
        f"nav and renderers disagree: {sorted(set(nav) ^ set(ALL_VIEWS))}")


@pytest.mark.parametrize("role", ROLES)
def test_a_withheld_field_is_absent_and_not_zero(projected, role):
    """Role gating removes the field; it never substitutes a number.

    A withheld `pillarScores` rendered as 0 would be a false statement about
    the model, so the gateway must drop the key rather than blank it.
    """
    from seraph.dashboard.gateway import ROLE_FIELDS
    view = projected[role]["payload"]["view"]
    allowed = set(ROLE_FIELDS[role])
    for field in WITHHELD:
        if field in allowed:
            continue
        assert field not in view, (
            f"{role}: {field} is withheld by ROLE_FIELDS but present in the "
            f"payload")


# ==========================================================================
# WORKSPACE — the real dispatch, against a disposable store
# ==========================================================================
@pytest.mark.parametrize("role", ROLES)
def test_a_portfolio_round_trip_through_the_real_backend(archive, disposable,
                                                         role):
    """create -> preview -> commit -> holdings, all through `dispatch`.

    This is the one durable workflow every role owns, and it is the path the
    WORKSPACE screen's buttons take. Any role may keep their own portfolio,
    so all three must complete it.
    """
    paths, run = archive["paths"], archive["run"]
    points = data.run_bundle(paths["archive"], run["id"], role)["points"]
    date = points[-1]["date"]

    def call(op, **args):
        return data.workspace_call(paths["archive"], run["id"], date, role,
                                   op, **args)

    created = call("ws_create", name=f"e2e {role}", kind="portfolio")
    assert not created.get("error"), f"ws_create refused: {created.get('error')}"
    listed = call("ws_portfolios")
    ids = [p["portfolio_id"] for p in (listed.get("value") or [])]
    assert ids, "a created portfolio does not appear in ws_portfolios"
    pid = ids[0]

    preview = call("ws_preview", portfolio_id=pid,
                   body="symbol,qty,price,sector\nRELIANCE,10,2800,energy\n",
                   source_name="e2e.csv")
    assert not preview.get("error"), f"ws_preview refused: {preview.get('error')}"

    committed = call("ws_commit", portfolio_id=pid,
                     body="symbol,qty,price,sector\nRELIANCE,10,2800,energy\n",
                     source_name="e2e.csv")
    assert not committed.get("error"), f"ws_commit refused: {committed.get('error')}"

    held = call("ws_holdings", portfolio_id=pid)
    rows = (held.get("value") or {}).get("holdings") or []
    assert any(r["symbol"] == "RELIANCE" for r in rows), (
        f"a committed holding is not readable back: {held}")


def test_a_scenario_round_trip_for_the_roles_that_own_it(archive, disposable):
    """Scenarios are an institutional/regulator tool — save, then run."""
    paths, run = archive["paths"], archive["run"]
    points = data.run_bundle(paths["archive"], run["id"], "institutional")["points"]
    date = points[-1]["date"]

    saved = data.workspace_call(
        paths["archive"], run["id"], date, "institutional", "sc_save",
        name="e2e shock", kind="rank_shock",
        steps=[dict(pillar="hawkes", delta=1.0, horizon=1)],
        assumptions=[dict(key="shock", value=1.0, unit="rank",
                          justification="end-to-end verification only")])
    assert not saved.get("error"), f"sc_save refused: {saved.get('error')}"

    listed = data.workspace_call(paths["archive"], run["id"], date,
                                 "institutional", "sc_list")
    scenarios = listed.get("value") or []
    assert scenarios, "a saved scenario does not appear in sc_list"

    run_result = data.workspace_call(
        paths["archive"], run["id"], date, "institutional", "sc_run",
        scenario_id=scenarios[0]["scenario_id"])
    assert not run_result.get("error"), f"sc_run refused: {run_result.get('error')}"


def test_a_regulator_case_round_trip(archive, disposable):
    """Open a case, attach evidence, record a decision — regulator only."""
    paths, run = archive["paths"], archive["run"]
    points = data.run_bundle(paths["archive"], run["id"], "regulator")["points"]
    date = points[-1]["date"]

    def call(op, **args):
        return data.workspace_call(paths["archive"], run["id"], date,
                                   "regulator", op, **args)

    opened = call("case_open", title="e2e case")
    assert not opened.get("error"), f"case_open refused: {opened.get('error')}"
    cases = call("case_list").get("value") or []
    assert cases, "an opened case does not appear in case_list"
    case = cases[0]

    # The revision is REQUIRED, and that is the point of the field: an
    # evidence pointer with no revision can come back as different content
    # later, so the decision timestamp is what pins this one.
    evidence = call("case_evidence", case_id=case["case_id"],
                    expected_version=case["version"],
                    refs=[dict(kind="run", ref_id=run["id"],
                               revision=points[-1]["evaluation_timestamp"])])
    assert not evidence.get("error"), (
        f"case_evidence refused: {evidence.get('error')}")

    attached = (evidence.get("value") or {})
    assert attached.get("version", 0) > case["version"], (
        "attaching evidence did not advance the case version, so a "
        "concurrent edit could overwrite it unnoticed")

    decided = call("case_decision", case_id=case["case_id"],
                   expected_version=attached["version"],
                   outcome="closed",
                   rationale="end-to-end verification only; not a finding")
    assert not decided.get("error"), (
        f"case_decision refused: {decided.get('error')}")


def test_evidence_without_a_revision_is_refused(archive, disposable):
    """An unpinned evidence pointer cannot be replayed honestly.

    The regulator case file is the audit trail, so this refusal is a product
    guarantee and not an input-validation detail.
    """
    paths, run = archive["paths"], archive["run"]
    points = data.run_bundle(paths["archive"], run["id"], "regulator")["points"]
    date = points[-1]["date"]
    data.workspace_call(paths["archive"], run["id"], date, "regulator",
                        "case_open", title="e2e unpinned")
    cases = data.workspace_call(paths["archive"], run["id"], date,
                                "regulator", "case_list")["value"]
    with pytest.raises(ValueError, match="revision"):
        data.workspace_call(
            paths["archive"], run["id"], date, "regulator", "case_evidence",
            case_id=cases[0]["case_id"],
            expected_version=cases[0]["version"],
            refs=[dict(kind="run", ref_id=run["id"], revision=None)])


@pytest.mark.parametrize("op,role", [
    (op, role) for op, allowed in sorted(WORKFLOW_ROLES.items())
    for role in ROLES if role not in allowed
])
def test_an_operation_is_refused_to_a_role_that_does_not_own_it(
        archive, disposable, op, role):
    """Every (operation, role) pair outside `WORKFLOW_ROLES` must refuse.

    Parametrised off the table itself, so a permission widened in the backend
    without a decision shows up here as a test that stops refusing.
    """
    paths, run = archive["paths"], archive["run"]
    points = data.run_bundle(paths["archive"], run["id"], role)["points"]
    with pytest.raises((ValueError, PermissionError)) as caught:
        data.workspace_call(paths["archive"], run["id"], points[-1]["date"],
                            role, op)
    assert op in str(caught.value) or "role" in str(caught.value).lower(), (
        f"{op}/{role} was refused, but the refusal does not say why: "
        f"{caught.value}")


@pytest.mark.parametrize("role", ROLES)
def test_the_workspace_screen_offers_only_what_the_role_may_invoke(
        selection, role):
    """A button a role cannot use must not be drawn for that role.

    The screen is built from the same `WORKFLOW_ROLES` table the backend
    enforces, so an offered-but-refused control is a drift between the two.
    """
    markup = W.workspace(
        dict(portfolios=[{"portfolio_id": "p1", "name": "n"}],
             scenarios=[{"scenario_id": "s1", "name": "n",
                         "assumption_version": 1}],
             cases=[{"case_id": "c1", "title": "t", "status": "triage",
                     "version": 1}],
             holdings={}, identity_note="", now_ist=""),
        role, dict(selection, role=role))
    offered = set(re.findall(r'data-rd-op="([a-z_]+)"', markup))
    forbidden = sorted(op for op in offered
                       if op in WORKFLOW_ROLES
                       and role not in WORKFLOW_ROLES[op])
    assert forbidden == [], (
        f"{role} is offered operations it cannot invoke: {forbidden}")


# ==========================================================================
# EVALUATION / EARLY WARNING / HEALTH / NEWS
# ==========================================================================
@pytest.mark.parametrize("role", ROLES)
def test_evaluation_is_read_only_for_every_role(role):
    """No commit control and no run control — D5(d) and page-render cost."""
    markup = V.evaluation(data.evaluation_state(role))
    ops = set(re.findall(r'data-rd-op="([a-z_]+)"', markup))
    assert ops == set(), (
        f"EVALUATION offers operations to {role}: {sorted(ops)}. Committing a "
        f"pre-registered design is a person's act and a full ablation on page "
        f"render would make every refresh a cliff")


def test_evaluation_states_whether_the_role_may_see_it():
    """`permitted` false is an answer, not an empty screen."""
    for role in ROLES:
        surface = data.evaluation_state(role)
        assert "permitted" in surface, f"{role}: no permission statement"
        markup = V.evaluation(surface)
        if not surface["permitted"]:
            assert "rd-unavail" in markup or "not" in markup.lower(), (
                f"{role} may not see the ablation, and the screen does not "
                f"say so")


def test_early_warning_separates_measured_predicted_and_warning():
    """Three different claims, never run together into one number."""
    surface = data.forecast_state()
    if not surface.get("available"):
        pytest.skip(f"no saved prediction state: {surface.get('reason')}")
    state = surface["state"]
    for block in ("measured", "predicted", "warning"):
        assert block in state, f"the forecast state has no {block!r} block"
    markup = V.warning(surface)
    assert markup.strip(), "EARLY WARNING rendered nothing"
    # The warning level is a policy decision against a threshold; the screen
    # must carry the threshold, or the level is an unfalsifiable claim.
    if state["warning"].get("threshold") is not None:
        assert "threshold" in markup.lower(), (
            "a warning level is shown without the threshold it was taken "
            "against")


def test_the_prediction_surface_is_read_not_fitted():
    """Opening a screen must never fit a model.

    Two reads of the surface return the same `generated_at`: a render that
    re-fit would move it, and a model that re-fits on page view cannot be
    audited against the state that produced the warning.
    """
    first = data.forecast_state()
    if not first.get("available"):
        pytest.skip("no saved prediction state")
    second = data.forecast_state()
    assert first["state"]["generated_at"] == second["state"]["generated_at"]
    assert first["state"]["as_of"] == second["state"]["as_of"]


def test_health_never_maps_silence_to_ok():
    """A check with no data reads `never_run`, not `ok`."""
    surface = data.health_state()
    assert "checks" in surface and "status" in surface
    for check in surface["checks"]:
        if check.get("health") == "ok":
            assert check.get("last_success_at") or check.get("observed") or \
                   check.get("detail"), (
                f"{check.get('name')} reads ok with nothing behind it: {check}")
    markup = V.health(surface, {}, data.market_jobs_state())
    assert markup.strip(), "HEALTH rendered nothing"


def test_health_reports_a_failed_news_worker_rather_than_omitting_it():
    """A dead fetcher is the single most misleading thing to omit.

    With the worker down the store still answers every read, so a screen that
    only reports the store would show a full, healthy news channel that is
    not receiving anything.
    """
    paths = data.store_paths()
    if not paths["news"].exists():
        pytest.skip("no news store configured")
    from seraph.dashboard.redesign import news_data
    acquisition = news_data.acquisition_state(paths["news"])
    worker = acquisition.get("worker") or {}
    state = worker.get("state")
    if state in (None, "running", "ok", "idle"):
        pytest.skip(f"the acquisition worker is {state!r} here, not stopped")

    markup = V.health(data.health_state(), acquisition,
                      data.market_jobs_state())
    assert "nothing is fetching" in markup.lower(), (
        f"the worker is {state!r} and HEALTH does not say nothing is "
        f"fetching")
    # The worker's own detail is the checkable part. A one-word chip reading
    # "failed" does not tell an operator whether to restart it or fix it.
    detail = str(worker.get("detail") or "")
    if detail:
        from seraph.dashboard.redesign.component_views import esc
        assert esc(detail) in markup, (
            "HEALTH reports the worker as stopped but drops the reason it "
            "recorded")


def test_a_stopped_worker_is_not_drawn_as_a_healthy_channel():
    """The chip must carry a bad tone, not render neutral.

    Built from a synthetic acquisition state so the assertion holds on an
    installation whose worker happens to be running.
    """
    stopped = dict(
        owner="not_asked", reason="the worker has not been asked for",
        store=True, sources=[],
        worker=dict(worker="news.poll", state="failed",
                    last_beat_at="2026-10-25T18:26:54+05:30",
                    age_minutes=200.8, pid=None,
                    detail="worker exited 1; gave up after 5 restarts",
                    note="a stopped worker and a quiet market look identical "
                         "on every other surface"))
    markup = V.health(dict(checks=[], by_health={}, status="ok"), stopped,
                      dict(ran=False, note=""))
    assert "rd-chip--bad" in markup, (
        "a failed worker renders as a neutral chip, which reads as normal")
    assert "rd-chip--ok" not in markup.split("News acquisition")[-1], (
        "a failed worker is drawn with the healthy tone")
    assert "gave up after 5 restarts" in markup


def test_news_intelligence_is_either_connected_or_states_its_absence():
    """Never a fabricated preview presented as a channel."""
    paths = data.store_paths()
    from seraph.dashboard.redesign import news_data
    if not paths["news"].exists():
        pytest.skip("no news store configured")
    state = news_data.news_state(paths["news"], role="retail")
    assert "connected" in state
    if not state.get("connected"):
        assert state.get("reason"), (
            "the news channel is not connected and gives no reason")


def test_the_news_branch_is_absent_not_fabricated_when_detached(projected):
    """`project_run` without a store must say so in the payload."""
    news = projected["retail"]["payload"]["news"]
    assert news.get("status") == "absent"
    assert news.get("reason"), "an absent news branch with no reason"
    assert news.get("preview_only") is True


# ==========================================================================
# the component's own script
# ==========================================================================
def _component(name: str):
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "seraph" / "dashboard" /
            name / "index.html").read_text(encoding="utf-8")


def test_no_script_fills_a_panel_the_fork_removed():
    """Removing a panel must remove the code that filled it.

    `el("commod").innerHTML = ...` survived the removal of INPUT COMMODITIES
    and threw `TypeError: Cannot set properties of null` on every load. An
    uncaught throw at this level stops every statement after it in the same
    script, so one dead panel silently disabled the rest of the console's
    own initialisation — which is why this is a test and not a lint.

    Only the fork is checked against its own markup: Classic has its own
    long-standing references and this work does not touch it.
    """
    fork = _component("redesign/console_component")
    classic = _component("console_component")
    ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', fork))
    # `el(...)` dereferences immediately; `getElementById` callers in this
    # file guard their result, so only the former can throw at load.
    referenced = set(re.findall(r'\bel\(\s*["\']([A-Za-z0-9_-]+)["\']\s*\)',
                                fork))
    classic_ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', classic))
    classic_refs = set(re.findall(r'\bel\(\s*["\']([A-Za-z0-9_-]+)["\']\s*\)',
                                  classic))

    introduced = (referenced - ids) - (classic_refs - classic_ids)
    assert introduced == set(), (
        f"the fork's script fills panels that are not in its markup: "
        f"{sorted(introduced)}. Removing a panel must remove its script too")


def test_the_three_js_failure_message_does_not_blame_the_network():
    """three.js is vendored, so a load failure is never a connectivity problem.

    `three.r128.min.js` sits beside the component and is served with it. The
    message that shipped told the reader the page "needs an internet
    connection the first time you open it", which sends someone to check
    their network when the real cause is that the file is not being served:
    opened as a standalone document — a saved copy, a `file://` path, an
    editor preview, a `data:` snapshot — a relative `<script src>` resolves
    to nothing, and the component never receives its payload either.
    """
    from pathlib import Path
    fork = Path(__file__).resolve().parents[1] / "seraph" / "dashboard" / \
        "redesign" / "console_component"
    assert (fork / "three.r128.min.js").is_file(), (
        "three.js must be vendored beside the component")

    html = (fork / "index.html").read_text(encoding="utf-8")
    guard = html[html.index('if (typeof THREE === "undefined")'):][:1800]
    # The MESSAGE only — the comment above it quotes the old wording to say
    # why it was wrong, and must not be mistaken for the message itself.
    message = guard[guard.index("die("):guard.index("} else")]
    assert "needs an internet connection" not in message, (
        "the failure message still blames the network for a vendored script")
    lowered = message.lower()
    assert "three.r128.min.js" in lowered and "vendored" in lowered, (
        "the message must say the script is local, so the reader does not go "
        "looking for a network fault")
    assert "launch_redesign" in message, (
        "the message must say how to open this component properly")


def test_the_flow_panel_is_not_tagged_fabricated():
    """`flowHTML()` renders measured E14 prints, or says why it cannot.

    The tag outlived the three invented numbers it was put there for, so it
    sat above real published prints and above an honest absence. A tag that
    appears over true things is one a reader learns to ignore, and ignoring
    it is what the panels that ARE previews depend on.
    """
    from pathlib import Path
    bridge = (Path(__file__).resolve().parents[1] / "seraph" / "dashboard" /
              "redesign" / "console_component" /
              "bridge.js").read_text(encoding="utf-8")
    call = re.search(r"card\('Institutional / residual flow',(.{0,60}?)\);",
                     bridge)
    assert call, "the residual-flow card is gone from the fork"
    assert "tag" not in call.group(1), (
        f"the flow card still prepends the FABRICATED tag to measured "
        f"flow: {call.group(1)!r}")
    assert "flowHTML()" in call.group(1)


def test_the_static_banner_does_not_name_removed_panels():
    """The fallback banner is what a reader sees before any payload arrives.

    Naming COMMODITIES and WEATHER there outlived the panels themselves, so
    the first thing on screen described two surfaces that do not exist.
    """
    fork = _component("redesign/console_component")
    banner = re.search(r'<div id="preview-banner">(.*?)</div>', fork)
    assert banner, "the fork has no preview banner"
    text = banner.group(1).upper()
    for gone in ("COMMODITIES", "WEATHER"):
        assert gone not in text, (
            f"the banner still names {gone}, which this fork removed")


# ==========================================================================
# the freshness gate
# ==========================================================================
@pytest.mark.parametrize("role", ROLES)
def test_an_archived_decision_is_labelled_a_replay_for_every_role(projected,
                                                                  role):
    """An archive run is a replay by construction and every role is told.

    Softening this for the retail view is the single most consequential thing
    this frontend could get wrong: a 2020 score read as today's market.
    """
    liveness = projected[role]["payload"]["liveness"]
    assert liveness, f"{role}: no liveness judgement on an archived decision"
    headline = str(liveness.get("headline", "")).upper()
    assert "NOT A CURRENT MARKET READING" in headline or "REPLAY" in headline, (
        f"{role}: an archived decision is headlined {headline!r}")
    assert liveness.get("publishable_as_current") is False, (
        f"{role}: a {liveness.get('recency')} decision may not be published "
        f"as a current reading")
    assert liveness.get("why"), (
        f"{role}: the gate refuses publication and gives no reason a reader "
        f"could check")


def test_the_staleness_statement_names_the_age_and_the_observation(projected):
    """The banner must be checkable: the age AND what it was measured from."""
    liveness = projected["regulator"]["payload"]["liveness"]
    text = " ".join(str(v) for v in liveness.values())
    assert re.search(r"\d", text), (
        "the freshness statement carries no number, so a reader cannot tell "
        "a one-hour delay from a six-year one")
