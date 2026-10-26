# Tests for C12's redesigned console (seraph/dashboard/redesign).
"""The redesign's non-negotiables, asserted without a browser.

Two groups:

* **Isolation.** The redesigned frontend must not be able to change Classic.
  That is checked structurally — no Classic module may import the redesign
  package, and the redesign's stylesheet must be scoped.
* **Honesty.** Every rule the brief calls non-negotiable has a test, because
  each is a thing a later layout change could quietly break: an unavailable
  score must not render as zero, a declared absence must stay an absence, and
  signed contributions must not be turned into shares of a total.

The instruments are pure `value -> str` functions precisely so these can be
assertions about output rather than screenshots.
"""
from pathlib import Path

import pytest

from seraph.dashboard.redesign import components, data, instruments, theme, tokens
from seraph.shared_types import PILLAR_ORDER

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "seraph" / "dashboard"


def _identifiers(path) -> set[str]:
    """Every name the module's CODE mentions, ignoring strings and comments.

    Several of these rules are about what a module touches, and the modules
    explain in prose what they deliberately do not touch. Grepping the raw
    text makes that prose fail the test it is describing, so the assertions
    run against the parsed tree instead.
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[-1])
    return names


# ==========================================================================
# isolation — Classic must stay reachable and unaltered
# ==========================================================================
def test_no_classic_module_imports_the_redesign():
    """The dependency runs one way only.

    If a Classic module imported `redesign`, a change here could break the
    default frontend — which is the single thing this work is not allowed to
    do. Checked by reading the files rather than by importing them, so the
    test states a structural fact and not an import-order accident.
    """
    offenders = []
    for path in DASHBOARD.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "redesign" in text and "import" in text:
            for line in text.splitlines():
                if "import" in line and "redesign" in line:
                    offenders.append(f"{path.name}: {line.strip()}")
    assert offenders == [], (
        "Classic modules must not import the redesign package: " + "; ".join(offenders))


def test_classic_entry_points_still_exist():
    """Returning to Classic is choosing its launcher — nothing to revert."""
    assert (ROOT / "launch_prototype.ps1").is_file()
    assert (DASHBOARD / "prototype_app.py").is_file()
    assert (ROOT / "launch_redesign.ps1").is_file()
    assert (DASHBOARD / "redesign" / "app.py").is_file()


def test_the_two_launchers_use_different_ports():
    classic = (ROOT / "launch_prototype.ps1").read_text(encoding="utf-8")
    redesign = (ROOT / "launch_redesign.ps1").read_text(encoding="utf-8")
    assert "[int]$Port = 8512" in classic
    assert "[int]$Port = 8520" in redesign


def test_redesign_launcher_starts_no_duplicate_background_workers():
    """The redesigned launcher must not start a second news supervisor, a
    second market-jobs run or a second owned runtime by default.

    The OS lock in `worker_lock` covers the news worker; nothing covers the
    market jobs, so the launcher simply does not start them unless asked.
    """
    text = (ROOT / "launch_redesign.ps1").read_text(encoding="utf-8")
    assert "news_supervisor.py" not in text, (
        "the redesigned launcher must not spawn its own supervisor; the app "
        "asks for one and stands aside when the lock is held")
    for guarded, switch in (("run_market_jobs.py", "$WithMarketJobs"),
                            ("run_live.py", "$WithLiveRuntime")):
        assert guarded in text
        index = text.index(guarded)
        assert switch in text[:index], (
            f"{guarded} must be guarded by {switch}")


def test_the_app_stands_aside_when_a_supervisor_already_owns_the_store(tmp_path,
                                                                      monkeypatch):
    """Running both frontends must not produce two acquisition workers.

    The guarantee is the OS lock, not either app's bookkeeping, so this takes
    the real supervisor lock and then calls the exact function the redesigned
    app calls on first page view. The worker is left ENABLED, so standing
    aside is a genuine decision rather than the disabled short-circuit.
    """
    from seraph.dashboard import news_service
    from seraph.news.worker_lock import worker_lock

    store = tmp_path / "news.sqlite"
    store.write_bytes(b"")
    monkeypatch.setenv(news_service.ENV_FLAG, "1")
    monkeypatch.setattr(news_service, "_state", None, raising=False)

    with worker_lock(store, "supervisor"):
        state = news_service.ensure_worker(store)

    assert state["owner"] == "external"
    assert state["started"] is False
    assert "did not start a second one" in state["reason"]


def test_stylesheet_is_scoped_and_classic_cannot_be_restyled():
    css = theme.css()
    assert css.count("<style") == 1
    # No bare element selectors that would travel to another page's DOM.
    for naked in ("\nbody {", "\n* {", "\np {", "\ndiv {"):
        assert naked not in css, f"unscoped selector {naked.strip()!r} in the redesign CSS"
    assert "rd-" in css


def test_pillar_colours_cover_pillar_order_exactly():
    """The colour table is a contract keyed by PILLAR_ORDER, not decoration."""
    assert set(tokens.PILLAR_COLOUR) == set(PILLAR_ORDER)
    assert tokens.pillar_colour("hawkes") == tokens.PILLAR_COLOUR["hawkes"]
    assert tokens.pillar_colour("nonsense") == tokens.TEXT_FAINT


# ==========================================================================
# honesty — an absent quantity renders as absent
# ==========================================================================
def test_unavailable_dial_draws_no_value_and_never_zero():
    """The rule this whole screen exists to hold.

    An unavailable composite keeps the dial's geometry and fills none of it.
    The assertion is that the markup contains the empty track and the
    `UNAVAILABLE` label, carries no numeric readout, and in particular does
    not render `0.000`.
    """
    svg = instruments.composite_dial(
        value=None, unavailable_reason="no decision has been committed")
    assert "UNAVAILABLE" in svg
    assert tokens.UNAVAILABLE_TRACK in svg          # the track is still drawn
    assert "0.000" not in svg
    assert "no decision has been committed" in svg
    # exactly one arc: the empty track, with nothing filled over it
    assert svg.count("<path") == 1


def test_unavailable_dial_refuses_to_render_a_bare_absence():
    """A missing reason is itself reported, not rendered as a blank box."""
    svg = instruments.composite_dial(value=None)
    assert "UNAVAILABLE" in svg
    assert "0.000" not in svg


def test_available_dial_draws_the_value_and_the_interval_separately():
    svg = instruments.composite_dial(value=0.9899, ci_lower=0.7388,
                                     ci_upper=1.0, alert_level="red")
    assert "0.990" in svg
    assert tokens.ALERT["red"] in svg
    assert "FR29 95% interval" in svg
    # track + value arc + CI arc
    assert svg.count("<path") == 3


def test_dial_arcs_are_only_quantities_the_payload_carries():
    """No arc without a named quantity: with no interval, no interval arc."""
    svg = instruments.composite_dial(value=0.5, alert_level="amber")
    assert "FR29" not in svg
    assert svg.count("<path") == 2


def test_contributions_are_not_turned_into_percentages():
    """Signed Shapley contributions sum to the CSRS, not to 1."""
    markup = instruments.contribution_tracks(
        [dict(name="hawkes", value=0.0, excluded=True),
         dict(name="rmt", value=0.9899, excluded=False),
         dict(name="hamilton", value=None, excluded=True,
              missing_reason="regime support unvalidated")],
        unit="CSRS score units")
    assert "not</b> shares of a total" in markup
    assert "do not sum to 100%" in markup
    # The per-pillar label prints signed score units, never a percentage of
    # the composite. 0.9899 of a 0.9899 score would be "100%" in a share
    # rendering, which is precisely the reading this must not invite.
    assert "+0.9899" in markup
    assert "CSRS score units" in markup
    for forbidden in ("100.0%", "98.99%", "99%"):
        assert forbidden not in markup


def test_excluded_pillar_is_not_drawn_as_a_measured_zero():
    """0 by construction and 0 by measurement are different claims."""
    markup = instruments.contribution_tracks(
        [dict(name="hawkes", value=0.0, excluded=True)],
        unit="CSRS score units")
    assert "excluded by mask" in markup
    assert "stroke-dasharray" in markup, "an excluded pillar gets an empty track"


def test_weights_may_be_shares_and_say_so():
    markup = instruments.weight_tracks(
        [dict(name="hawkes", value=0.0), dict(name="rmt", value=1.0),
         dict(name="hamilton", value=0.0)])
    assert "1.000" in markup


def test_timeline_keeps_a_scoreless_session_hollow():
    """A session with no CSRS must not share a shape with a low CSRS."""
    markup = instruments.timeline(
        [dict(date="2020-01-01", csrs=0.5, benchmark_available=True),
         dict(date="2020-01-02", csrs=None, benchmark_available=True)],
        selected_date="2020-01-02")
    assert "<circle" in markup, "a scoreless session draws a hollow marker"
    assert "hollow, not zero" in markup


def test_unavailable_always_carries_a_reason():
    """`components.unavailable` is the one way this frontend claims absence."""
    markup = components.unavailable("no score")
    assert "no reason was recorded" in markup, (
        "an absence with no stated reason must report that as a defect")
    assert "no score" in components.unavailable("no score", "because X")
    assert "because X" in components.unavailable("no score", "because X")


def test_table_renders_a_missing_cell_as_a_dash_not_a_zero():
    markup = components.table(["sector", "jumps"], [["energy", None]])
    assert "—" in markup
    assert ">0<" not in markup


# ==========================================================================
# honesty — the adapter preserves absence
# ==========================================================================
def test_composite_of_never_substitutes_zero():
    for payload in (None, {}, {"view": {}},
                    {"view": {"csrs": None, "alertLevel": "unavailable"}},
                    {"view": {"csrs": {"csrs": None, "mask": [False] * 3}}}):
        got = data.composite_of(payload)
        assert got["value"] is None, payload
        assert got["reason"], f"an absent score must carry a reason: {payload}"


def test_composite_of_reads_both_payload_shapes():
    view_shape = data.composite_of(
        {"view": {"csrs": 0.5, "ciLower": 0.4, "ciUpper": 0.6,
                  "alertLevel": "amber"}})
    assert view_shape["value"] == 0.5
    assert view_shape["alert_level"] == "amber"

    raw_shape = data.composite_of(
        {"csrs": {"csrs": 0.5, "ci_lower": 0.4, "ci_upper": 0.6,
                  "alert_level": "amber", "mask": [True, True, False]}})
    assert raw_shape["value"] == 0.5
    assert raw_shape["mask_degraded"] is True


def test_pillar_rows_follow_pillar_order_not_dict_order():
    """PILLAR_ORDER is positional everywhere; reading a dict's order is a bug."""
    payload = {"view": {"role": "institutional", "pillarScores": {
        "hamilton": {"value": None, "score_eligible": False,
                     "reason": "regime support unvalidated"},
        "rmt": {"value": 0.24, "score_eligible": True},
        "hawkes": {"value": 0.10, "score_eligible": True}}},
        "mask": [False, True, False], "role": "institutional"}
    rows = data.pillar_rows(payload)
    assert [r["name"] for r in rows] == list(PILLAR_ORDER)
    assert [r["in_mask"] for r in rows] == [False, True, False]


def test_declared_absence_stays_absent_and_keeps_its_reason():
    """Hamilton's structural absence must never become a number."""
    payload = {"view": {"role": "institutional", "pillarScores": {
        "hamilton": {"value": None, "score_eligible": False,
                     "reason": "regime support unvalidated; diagnostic only"}}},
        "mask": [False, False, False], "role": "institutional"}
    row = next(r for r in data.pillar_rows(payload) if r["name"] == "hamilton")
    assert row["value"] is None
    assert row["eligible"] is False
    assert "regime support unvalidated" in row["reason"]
    card = components.pillar_card(row)
    assert "DECLARED NOT SCORED" in card.upper()
    assert "regime support unvalidated" in card
    assert "0.0000" not in card


def test_withheld_at_role_is_not_reported_as_not_emitted():
    """The retail projection omits `pillarScores` by construction.

    Calling that "not emitted" would be a false statement about the model:
    the pillar reported and the transport boundary removed it.
    """
    rows = data.pillar_rows({"view": {"role": "retail", "csrs": 0.5},
                             "role": "retail"})
    assert all(r["withheld"] for r in rows)
    card = components.pillar_card(rows[0])
    assert "withheld at this role" in card
    assert "not emitted" not in card.lower()


def test_institutional_absence_of_scores_is_not_called_withheld():
    """An institutional payload DOES carry pillarScores, so an empty one is a
    genuine absence rather than a role projection."""
    rows = data.pillar_rows({"view": {"role": "institutional", "csrs": 0.5},
                             "role": "institutional"})
    assert not any(r["withheld"] for r in rows)
    assert "not emitted" in components.pillar_card(rows[0]).lower()


def test_contribution_rows_flag_mask_exclusion():
    payload = {"view": {"role": "institutional",
                        "shapley": {"hawkes": 0.0, "rmt": 0.99, "hamilton": 0.0},
                        "pillarScores": {}},
               "mask": [False, True, False], "role": "institutional"}
    rows = {r["name"]: r for r in data.contribution_rows(payload)}
    assert rows["hawkes"]["excluded"] is True
    assert rows["rmt"]["excluded"] is False
    assert rows["hamilton"]["excluded"] is True


def test_weight_rows_read_the_first_mat3_row():
    payload = {"view": {"effectiveWeights": [[0.0, 1.0, 0.0]] * 3}}
    assert [r["value"] for r in data.weight_rows(payload)] == [0.0, 1.0, 0.0]


def test_weight_rows_survive_a_missing_matrix():
    assert all(r["value"] is None for r in data.weight_rows({"view": {}}))


# ==========================================================================
# honesty — charts
# ==========================================================================
def test_history_chart_states_both_units_and_refuses_one_axis():
    charts = pytest.importorskip("seraph.dashboard.redesign.charts")
    chart, note = charts.market_state_history({
        "rows": [dict(date="2020-01-01", csrs=0.1, benchmark_return=0.002),
                 dict(date="2020-01-02", csrs=None, benchmark_return=0.001)],
        "units": {"csrs": "composite score, 0..1",
                  "benchmark": "simple close-to-close return"},
        "series": {"label": "NIFTY 500", "source": "eod2"}})
    assert chart is not None
    assert "independent axes" in note
    assert "not comparable in level" in note
    assert "composite score, 0..1" in note
    spec = chart.to_dict()
    assert spec["resolve"]["scale"]["y"] == "independent"


def test_history_chart_reports_an_empty_overlay_rather_than_drawing_one():
    charts = pytest.importorskip("seraph.dashboard.redesign.charts")
    chart, reason = charts.market_state_history({"rows": []})
    assert chart is None
    assert "no rows" in reason


def test_pillar_detail_names_what_it_did_not_draw():
    charts = pytest.importorskip("seraph.dashboard.redesign.charts")
    chart, note = charts.pillar_detail(
        [dict(name="hawkes", v=0.1), dict(name="hamilton", v=None)],
        value_key="v", title="daily intensity")
    assert chart is not None
    assert "hamilton" in note
    assert "not drawn" in note


# ==========================================================================
# the channel separation (F1 / F2)
# ==========================================================================
def test_overview_module_carries_no_news_signal_into_the_composite():
    """F2 must not reach the CSRS surfaces.

    Structural, deliberately. The F2 adapter lives in its own module
    (`news_data.py`), and neither the CSRS screen nor the F1 adapter imports
    it — so there is no path along which a news quantity could reach a
    pillar, the mask or the dial. Prose about the separation is not what
    enforces it; the absent import is.
    """
    overview_src = (DASHBOARD / "redesign" / "overview.py").read_text(encoding="utf-8")
    for forbidden in ("build_news_payload", "build_globe_payload", "news_data"):
        assert forbidden not in overview_src, (
            f"the CSRS screen must not reach F2 via {forbidden}")

    adapter = (DASHBOARD / "redesign" / "data.py").read_text(encoding="utf-8")
    for forbidden in ("build_news_payload", "build_globe_payload", "news_data"):
        assert forbidden not in adapter, (
            f"the F1 adapter must not reach F2 via {forbidden}")


def test_news_screen_does_not_use_the_pillar_palette():
    """A documented news route must not look like a measured pillar.

    The pillar colours are reserved for measured market pillars. If the news
    screen drew with them, a glance could not tell an exposure mapping from a
    Hawkes edge — which is the confusion the whole channel separation exists
    to prevent.
    """
    from seraph.dashboard.redesign import news as news_screen

    src = (DASHBOARD / "redesign" / "news.py").read_text(encoding="utf-8")
    for colour in tokens.PILLAR_COLOUR.values():
        assert colour not in src, f"news screen must not use pillar colour {colour}"
    assert news_screen.NEWS_PRIMARY not in tokens.PILLAR_COLOUR.values()


def test_news_adapter_reads_surfaces_not_a_channel_key(tmp_path, monkeypatch):
    """`build_news_payload` returns `surfaces`; it has never returned `channel`.

    Classic's `news_only_panel` reads `payload['channel']` and therefore
    reports zero events and zero sources however full the store is. That
    branch is only reachable when no archive store exists, which is why it
    has gone unnoticed.

    Asserted behaviourally rather than by grepping the source, so the test
    cannot be satisfied by a comment: a payload shaped like the real one,
    carrying a `channel` key that is empty and a `surfaces` key that is not,
    must come back with the events found.
    """
    from seraph.dashboard.redesign import news_data

    store = tmp_path / "news.sqlite"
    store.write_bytes(b"")
    payload = dict(
        surfaces={"signals": {"items": [{"event_id": "evt_1",
                                         "headline": "a real event"}]}},
        channel={},                      # the key Classic reads; always empty
        pagination={"total": 1}, source_coverage={}, freshness={},
        manifest={}, temporal_policy={}, registry={}, role_view={},
        connected_surfaces=["signals"], preview_surfaces=[])

    monkeypatch.setattr(news_data, "build_news_payload",
                        lambda *a, **k: payload)
    monkeypatch.setattr("seraph.news.NewsStore", lambda *a, **k: object())
    monkeypatch.setattr("seraph.news.registry.load_master_data",
                        lambda *a, **k: (object(), None))

    state = news_data.news_state(store, role="retail", decision_ts="2026-01-01")
    assert state["connected"] is True
    assert len(state["signals"]) == 1, (
        "the adapter must read surfaces.signals, not the empty channel key")
    assert state["signals"][0]["event_id"] == "evt_1"


def test_every_screen_is_built_and_none_is_a_placeholder():
    """No screen may send the user back to Classic to do its job.

    The navigation now lives in the console itself rather than a Streamlit
    sidebar, so this asserts against the component's nav: every entry must
    either be one the original console already rendered or one the redesign
    module owns, and nothing may render a "use Classic instead" placeholder.
    """
    nav = _component_nav()
    original = {"map", "console", "feed", "pillars", "exposure", "forecasts",
                "tools", "method"}
    added = {"overview", "warning", "workspace", "evaluation", "health"}
    assert original <= set(nav), "the original console views must survive"
    assert added <= set(nav), "the redesigned views must be in the nav"

    host = (DASHBOARD / "redesign" / "app.py").read_text(encoding="utf-8")
    views = (DASHBOARD / "redesign" / "console_component"
             / "redesign_views.js").read_text(encoding="utf-8")
    for forbidden in ("gap_screen", "screen not implemented",
                      r"use .\launch_prototype.ps1"):
        assert forbidden not in host, f"{forbidden} is a placeholder"
    for view in added:
        assert f'"{view}"' in views or f"'{view}'" in views, (
            f"{view} is in the nav but the redesign module does not own it")


def _component_nav():
    """The forked console's nav entries, read out of its markup."""
    import re

    html = (DASHBOARD / "redesign" / "console_component"
            / "index.html").read_text(encoding="utf-8")
    return re.findall(r'data-view="([a-z]+)"', html)


def test_redesign_package_imports_no_validation_harness():
    """C9/C12 must not import C10 — the D1 one-directional rule."""
    for path in (DASHBOARD / "redesign").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from seraph.validation" not in text, path.name
        assert "import seraph.validation" not in text, path.name


# ==========================================================================
# RBAC — a role must not RECEIVE what it may not see
# ==========================================================================
def test_retail_payload_does_not_contain_institutional_fields():
    """CT-8's requirement, restated: hidden is not withheld.

    A retail payload must not merely omit institutional fields from the
    screen — it must not contain them, because anything serialised to the
    client is reachable by the client. This asserts it on the payload the
    redesigned frontend actually renders from.
    """
    from seraph.dashboard.gateway import ROLE_FIELDS

    paths = data.store_paths()
    runs = data.complete_runs(paths["archive"])
    if not runs:
        pytest.skip("no complete archive run in the configured store")
    run_id = runs[-1]["id"]
    dates = [p["date"] for p in data.run_bundle(paths["archive"], run_id, "retail")["points"]]
    decision = data.archive_decision(paths["archive"], run_id, dates[-1], "retail")
    assert decision["available"]

    view = decision["payload"]["view"]
    institutional_only = ROLE_FIELDS["institutional"] - ROLE_FIELDS["retail"]
    regulator_only = ROLE_FIELDS["regulator"] - ROLE_FIELDS["institutional"]
    leaked = sorted((institutional_only | regulator_only) & set(view))
    assert leaked == [], f"retail payload contains withheld fields: {leaked}"

    # The top-level payload too: Classic adds `pillars`/`report`/`mask` only
    # for non-retail roles, and the redesign renders the same payload.
    for field in ("pillars", "predictions", "limitations", "report", "mask",
                  "manifest", "action_log"):
        assert field not in decision["payload"], (
            f"retail payload must not carry {field!r}")


def test_evaluation_is_withheld_from_retail_by_the_backend():
    """The refusal comes from the backend, not from a frontend check."""
    assert data.evaluation_state("retail")["permitted"] is False
    assert data.evaluation_state("institutional")["permitted"] is True


def test_workspace_refuses_an_operation_the_role_may_not_invoke():
    """`WORKFLOW_ROLES` in the backend decides, not the screen.

    Scenarios are an institutional/regulator tool. A retail caller must be
    refused by `dispatch` itself, so that a frontend which forgot to hide the
    control still cannot perform the operation.
    """
    paths = data.store_paths()
    runs = data.complete_runs(paths["archive"])
    if not runs:
        pytest.skip("no complete archive run in the configured store")
    run_id = runs[-1]["id"]
    dates = [p["date"] for p in data.run_bundle(paths["archive"], run_id, "retail")["points"]]
    with pytest.raises((ValueError, PermissionError)):
        data.workspace_call(paths["archive"], run_id, dates[-1], "retail",
                            "sc_list")


# ==========================================================================
# the screens that were added after the Overview
# ==========================================================================
def test_every_screen_module_imports_and_exposes_render():
    from seraph.dashboard.redesign import (
        evaluation, forecast, news, operations, overview, workspace,
    )
    for module in (forecast, news, workspace, evaluation, operations, overview):
        assert callable(getattr(module, "render"))


def test_forecast_screen_reads_the_saved_state_and_never_fits():
    """A page render must not run the engine.

    Asserted against the module's identifiers, not its text, so that naming
    an engine function in a docstring neither satisfies nor breaks the test.
    """
    names = _identifiers(DASHBOARD / "redesign" / "forecast.py")
    for forbidden in ("walk_forward_predict", "calibrate_alerts",
                      "build_pillar_features"):
        assert forbidden not in names, (
            f"the forecast screen must read the saved state, not call "
            f"{forbidden}")


def test_evaluation_screen_offers_no_commit_and_no_run_control():
    """D5(d): committing a design is a person's act, never a page's.

    A control here would make the pre-registered design a side effect of
    opening a page, which is exactly what DR-05 step 5 prevents.
    """
    src = (DASHBOARD / "redesign" / "evaluation.py").read_text(encoding="utf-8")
    assert "st.button" not in src, (
        "the evaluation screen is read-only: no commit and no run control")
    assert "preregistration.commit" not in src


def test_workspace_goes_through_the_backend_dispatch():
    """No parallel persistence path and no second permission table.

    Against identifiers rather than text: the module's docstring explains
    that `WORKFLOW_ROLES` lives in the backend, and saying so must not fail
    a test about what the code touches.
    """
    names = _identifiers(DASHBOARD / "redesign" / "workspace.py")
    assert "workspace_call" in names
    for forbidden in ("WorkspaceStore", "ScenarioStore", "CaseStore",
                      "WORKFLOW_ROLES"):
        assert forbidden not in names, (
            f"the workspace screen must not reach persistence directly "
            f"({forbidden})")


def test_workspace_request_ids_are_unique_per_call(monkeypatch):
    """`CaseStore` dedupes on the request id, so a reused one is a silent
    no-op on the second distinct change.

    Behavioural: two calls must mint two different ids.
    """
    seen = []

    class _Store:
        def __init__(self, *a, **k):
            pass

        def points(self, run_id):
            return [{"date": "2020-01-01", "run_id": run_id}]

    monkeypatch.setattr(data, "RunStore", _Store)
    monkeypatch.setattr(data, "dispatch",
                        lambda store, point, role, event, **k: seen.append(
                            event["id"]) or {"ok": True})
    for _ in range(2):
        data.workspace_call("x", "run", "2020-01-01", "retail", "ws_portfolios")
    assert len(set(seen)) == 2, f"request ids must be unique per call: {seen}"


def test_operations_screen_never_maps_silence_to_health():
    """`never_run` and `never_succeeded` must not be drawn as ok."""
    from seraph.dashboard.redesign import operations

    for state in ("never_run", "never_succeeded", "failing", "stale",
                  "degraded"):
        assert operations._HEALTH_TONE.get(state) != "ok", (
            f"{state} must never be drawn as ok: silence is not health")
    assert operations._HEALTH_TONE["ok"] == "ok"


def test_activated_portfolio_reaches_the_decision_payload():
    """"Use this portfolio" must actually change what the Overview renders.

    The Workspace screen records the selection in session state; the Overview
    has to resolve it and rebuild the projection with the holdings in it.
    Without this the control sets a flag nothing consumes — which is the
    "capable backend, no route to a user" defect the workspace work exists to
    close, reintroduced one layer up.
    """
    paths = data.store_paths()
    runs = data.complete_runs(paths["archive"])
    if not runs:
        pytest.skip("no complete archive run in the configured store")
    run_id = runs[-1]["id"]
    dates = [p["date"] for p in
             data.run_bundle(paths["archive"], run_id, "institutional")["points"]]

    holdings = [{"symbol": "TEST", "value": 100.0, "quantity": 1,
                 "sector": "energy"}]
    decision = data.archive_decision(
        paths["archive"], run_id, dates[-1], "institutional",
        portfolio={"coveragePct": 0.0}, holdings=holdings,
        portfolio_context={"portfolio_id": "pf_test", "basis": "current"})
    assert decision["available"]
    assert decision["payload"]["portfolio"] == {"coveragePct": 0.0}
    assert decision["payload"]["portfolio_context"]["portfolio_id"] == "pf_test"


def test_resolve_active_portfolio_refuses_another_roles_selection():
    """One role's holdings must not render under another role."""
    got = data.resolve_active_portfolio(
        {"portfolio_id": "pf_x", "role": "retail", "basis": "current"},
        "regulator", at="2020-04-30T15:30:00+05:30")
    assert got["available"] is False
    assert got["reason"], "a refusal must say why"


def test_resolve_active_portfolio_with_no_selection_is_not_an_error():
    got = data.resolve_active_portfolio(None, "retail", at="2020-04-30T15:30:00+05:30")
    assert got["available"] is False
    assert got["reason"] == ""


def test_strict_replay_admits_no_evidence_received_after_the_decision():
    """The news clock is chosen, and a strict replay must not leak forward.

    `current_news` answers "what is known now"; `historical_decision` answers
    "what was known then". If the second admitted an item first seen after
    the decision, the channel would be showing hindsight as contemporaneous
    evidence — the exact substitution the mode discipline exists to prevent.
    """
    from seraph.dashboard.redesign import news_data

    paths = data.store_paths()
    if not paths["news"].exists():
        pytest.skip("no news store configured")
    runs = data.complete_runs(paths["archive"])
    if not runs:
        pytest.skip("no complete archive run in the configured store")
    run_id = runs[-1]["id"]
    points = data.run_bundle(paths["archive"], run_id, "institutional")["points"]
    decision_ts = points[-1]["evaluation_timestamp"]

    state = news_data.news_state(paths["news"], role="institutional",
                                 decision_ts=decision_ts, strict_replay=True)
    assert state["mode"] == "historical_decision"
    assert state["as_of"] == decision_ts
    assert state["temporal_policy"].get("strict") is True

    leaked = [item.get("event_id") for item in state["signals"]
              if (item.get("first_seen_at") or item.get("published_at") or "")
              > decision_ts]
    assert leaked == [], f"strict replay leaked post-decision evidence: {leaked}"


# ==========================================================================
# the Risk console — the existing component, embedded
# ==========================================================================
def test_risk_console_declares_the_same_component_directory():
    """Embedded, not copied.

    A second copy of `console_component/` would be a second thing to keep in
    step with the payload contract; the screen must point at the directory
    Classic's console uses.
    """
    from seraph.dashboard.redesign import console_screen

    assert console_screen._COMPONENT_PATH == DASHBOARD / "console_component"
    assert console_screen._COMPONENT_PATH.is_dir()
    assert (console_screen._COMPONENT_PATH / "bridge.js").is_file()


def test_risk_console_reuses_the_backend_paths_and_adds_no_second_dispatcher():
    """Every operation goes through `dispatch` / `_news_action`."""
    names = _identifiers(DASHBOARD / "redesign" / "console_screen.py")
    assert "dispatch" in names
    assert "_news_action" in names
    assert "project_run" in names
    # No parallel workflow table and no direct persistence.
    for forbidden in ("WORKFLOW_ROLES", "RegulatoryActionLog", "CaseStore",
                      "WorkspaceStore"):
        assert forbidden not in names, (
            f"the console screen must not reach past the backend "
            f"({forbidden})")


def test_risk_console_covers_every_operation_the_component_can_emit():
    """A button the component shows must have a handler behind it.

    The operations are read out of `bridge.js` itself rather than restated,
    so adding one there and forgetting it here fails this test.
    """
    import re

    from seraph.dashboard.redesign import console_screen

    bridge = (DASHBOARD / "console_component" / "bridge.js").read_text(
        encoding="utf-8")
    emitted = set(re.findall(r"request\('([a-z_]+)'", bridge))
    emitted |= set(re.findall(r"bind\('[a-z-]+','([a-z_]+)'", bridge))
    assert emitted, "no operations were found in bridge.js"

    handler = (DASHBOARD / "redesign" / "console_screen.py").read_text(
        encoding="utf-8")
    unhandled = sorted(
        op for op in emitted
        if f'"{op}"' not in handler and op not in console_screen.OPERATIONS)
    assert unhandled == [], (
        f"the console screen has no handler for: {unhandled}")


def test_news_branch_ttl_bounds_staleness_against_the_components_own_timer():
    """The TTL *is* the re-projection interval, so it must not exceed the
    interval at which the component asks for one.

    `bridge.js` fires `news_project` on a timer while the clock is
    `current_news`. The handler deliberately does not clear the cache there:
    the branch costs ~50 s to build on a warm store, so clearing on a 30 s
    timer would leave the console permanently rebuilding and never showing a
    result. The TTL is what keeps the view fresh instead, which only holds if
    it is no longer than the timer — read from `bridge.js` rather than
    restated, so changing the timer there fails this test.
    """
    import re

    from seraph.dashboard.redesign import console_screen

    bridge = (DASHBOARD / "console_component" / "bridge.js").read_text(
        encoding="utf-8")
    match = re.search(r"request\('news_project',\{\}\);?\s*\},\s*(\d+)\)",
                      bridge)
    assert match, "could not find the news_project timer in bridge.js"
    timer_seconds = int(match.group(1)) / 1000
    assert console_screen.NEWS_TTL_SECONDS <= timer_seconds, (
        f"the {console_screen.NEWS_TTL_SECONDS}s TTL must not exceed the "
        f"component's {timer_seconds}s re-projection timer")


def test_console_news_layer_is_opt_in_and_says_so():
    """Attaching F2 costs ~50 s on a warm store, so it is a choice.

    The screen must distinguish "not attached in this view" from "the channel
    is unavailable" — the second would be a false statement about the system.
    """
    src = (DASHBOARD / "redesign" / "console_screen.py").read_text(
        encoding="utf-8")
    assert "not attached to" in src
    assert "not a statement that" in src
    names = _identifiers(DASHBOARD / "redesign" / "console_screen.py")
    assert "toggle" in names, "the news layer must be a visible control"


def test_console_payload_news_branch_is_assignable_without_rebuilding():
    """The optimisation's premise: `payload['news']` is written once and read
    by nothing else in `project_run`.

    If that stopped being true, building the branch separately and assigning
    it back would silently diverge from what Classic renders. This pins the
    premise rather than the optimisation.
    """
    import ast

    source = (DASHBOARD / "console_backend.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "project_run")
    calls = [n for n in ast.walk(func)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "news_branch"]
    assert len(calls) == 1, (
        "project_run must build the news branch exactly once for the "
        "separate-build-and-assign to be equivalent")


# ==========================================================================
# live revision polling
# ==========================================================================
def test_live_monitor_is_a_fragment_that_polls():
    """Polling must rerun only the live panel, never the whole page.

    Classic records a revision move instead of acting on it, because
    rebuilding the page would silently rebase a half-typed form and lose it.
    A fragment reruns itself alone, so the reading can refresh without that
    cost — which is why the poll is implemented as one.
    """
    from seraph.dashboard.redesign import overview

    assert overview.LIVE_POLL_SECONDS == 2.0
    monitor = overview.live_monitor
    assert hasattr(monitor, "__wrapped__") or callable(monitor), (
        "live_monitor must be a callable fragment")
    src = (DASHBOARD / "redesign" / "overview.py").read_text(encoding="utf-8")
    assert "@st.fragment(run_every=LIVE_POLL_SECONDS)" in src, (
        "the poll interval must come from LIVE_POLL_SECONDS, not a literal")


def test_live_revision_is_absent_rather_than_invented_without_a_store(tmp_path):
    """No store means no revision. It must not be fabricated."""
    assert data.live_revision(tmp_path / "missing.sqlite") is None


def test_live_revision_is_stable_while_nothing_changes():
    """The id must move only when the screen's content moves, or polling it
    would rebuild the panel on every tick for no reason."""
    paths = data.store_paths()
    if not paths["live"].exists():
        pytest.skip("no live runtime store configured")
    first = data.live_revision(paths["live"])
    second = data.live_revision(paths["live"])
    assert first == second and first is not None


def test_polled_live_absence_stays_an_absence():
    """Polling an empty runtime more often does not produce a reading."""
    paths = data.store_paths()
    if not paths["live"].exists():
        pytest.skip("no live runtime store configured")
    for _ in range(3):
        got = data.live_decision(paths["live"], mode="live")
        if got["available"]:
            pytest.skip("this runtime has committed a decision")
        assert got["payload"] is None
        assert got["reason"]
        assert data.composite_of(got["payload"])["value"] is None


# ==========================================================================
# sector analysis basis
# ==========================================================================
def test_sector_basis_default_is_decision_time():
    """Decision-time is the only basis that answers what was measurable when
    the decision was taken, so it must stay the default."""
    from seraph.dashboard.redesign import app

    assert app.SECTOR_BASES[0] == app.SECTOR_DECISION_TIME
    assert app._sector_as_of(app.SECTOR_DECISION_TIME) is None
    assert app._sector_as_of(app.SECTOR_RETROSPECTIVE) is not None


def test_retrospective_basis_is_labelled_and_never_backdated():
    """The two bases must be impossible to confuse.

    `sector_analysis` carries `analysis_mode` and a note saying the
    retrospective view does not change the historical score or prove advance
    warning. The retrospective cutoff must be LATER than the decision, never
    backdated onto it.
    """
    from datetime import datetime

    from seraph.dashboard.console_backend import sector_analysis
    from seraph.shared_types import IST

    decision = "2020-04-30T15:30:00+05:30"
    now = datetime.now(IST).isoformat()

    at_decision = sector_analysis(decision, None)
    assert at_decision["analysis_mode"] == "decision_time"
    assert at_decision["analysis_cutoff"] == decision
    assert "Only sector artifacts available by the selected market decision" \
        in at_decision["analysis_note"]

    retrospective = sector_analysis(decision, now)
    assert retrospective["analysis_mode"] == "retrospective_archive"
    assert retrospective["analysis_cutoff"] == now
    assert retrospective["analysis_cutoff"] > decision, (
        "a retrospective cutoff must be later than the decision, never "
        "backdated onto it")
    assert "Does not change the historical score or prove advance warning" \
        in retrospective["analysis_note"]


def test_sector_basis_reaches_the_projection():
    """The chosen basis must actually change what the payload may contain.

    The Streamlit-cached `_decision` wrapper is gone with the sidebar, so
    this asserts the thing that always mattered: `main()` passes the
    resolved cutoff into `project_run`, rather than computing it and
    dropping it.
    """
    import ast

    tree = ast.parse((DASHBOARD / "redesign" / "app.py").read_text(
        encoding="utf-8"))
    main = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [n for n in ast.walk(main)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "project_run"]
    assert calls, "main() must build the payload with project_run"
    assert any(k.arg == "sector_archive_as_of" for c in calls
               for k in c.keywords), (
        "the sector basis must reach project_run, not be computed and dropped")


def test_console_news_toggle_does_not_fight_its_own_session_state():
    """A `value=` read from the same key as `key=` makes a toggle unflippable.

    Streamlit re-applies an explicitly passed default over the new widget
    state on the rerun after a click, so the control appears to do nothing.
    Found by trying to turn the layer on in a browser; this pins the fix.
    """
    import ast

    tree = ast.parse((DASHBOARD / "redesign" / "console_screen.py").read_text(
        encoding="utf-8"))
    toggles = [n for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "toggle"]
    assert toggles, "the console must expose the news layer as a toggle"
    for call in toggles:
        keywords = {k.arg for k in call.keywords}
        assert "key" in keywords, "the toggle must own its state via `key`"
        assert "value" not in keywords, (
            "passing `value` alongside `key` makes the toggle unflippable")
