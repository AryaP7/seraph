# Tests for the console-native redesigned frontend.
"""The redesign lives INSIDE the 3D console, not in a shell around it.

SERAPH's interface is the console component, so the redesigned screens are
entries in its own nav. These tests pin that architecture and the things it
makes possible to get wrong:

* the component is **forked**, so adding nav entries cannot change Classic;
* every nav entry is rendered by someone;
* every control the views emit has a handler in the host;
* the FABRICATED tag is claimed from the payload rather than stamped on
  everything at load.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "seraph" / "dashboard"
CLASSIC = DASHBOARD / "console_component"
FORK = DASHBOARD / "redesign" / "console_component"

ORIGINAL_VIEWS = {"map", "console", "feed", "pillars", "exposure",
                  "forecasts", "tools", "method"}
ADDED_VIEWS = {"overview", "warning", "workspace", "evaluation", "health"}


def _nav():
    import re
    return re.findall(r'data-view="([a-z]+)"',
                      (FORK / "index.html").read_text(encoding="utf-8"))


# ==========================================================================
# the fork
# ==========================================================================
def test_the_component_is_forked_so_classic_cannot_change():
    """Classic shares nothing that the redesign edits.

    The nav entries are added to the fork. If the redesign pointed at
    Classic's directory instead, every button added here would appear in
    Classic too, and Classic would stop being an untouched fallback.
    """
    assert FORK.is_dir(), "the redesign must have its own component"
    for name in ("index.html", "bridge.js", "news_layer.js",
                 "three.r128.min.js"):
        assert (FORK / name).is_file(), f"the fork is missing {name}"

    from seraph.dashboard.redesign import app
    assert app._COMPONENT_PATH == FORK
    assert app._COMPONENT_PATH != CLASSIC


def test_classic_component_has_only_its_original_views():
    """The proof that forking worked: Classic's nav is untouched."""
    import re
    classic_nav = set(re.findall(
        r'data-view="([a-z]+)"', (CLASSIC / "index.html").read_text(encoding="utf-8")))
    assert classic_nav == ORIGINAL_VIEWS, (
        f"Classic's nav changed: {sorted(classic_nav ^ ORIGINAL_VIEWS)}")
    assert not (ADDED_VIEWS & classic_nav), (
        "redesigned views leaked into Classic's component")


def test_classic_component_declares_a_different_streamlit_component():
    """Two components in one process must not collide on a name."""
    import re
    host = (DASHBOARD / "redesign" / "app.py").read_text(encoding="utf-8")
    classic = (DASHBOARD / "prototype_app.py").read_text(encoding="utf-8")
    mine = set(re.findall(r"declare_component\(\s*['\"]([a-z_]+)['\"]", host))
    theirs = set(re.findall(r"declare_component\(\s*['\"]([a-z_]+)['\"]", classic))
    assert mine and theirs
    assert not (mine & theirs), f"component name collision: {mine & theirs}"


# ==========================================================================
# the navigation
# ==========================================================================
def test_the_nav_keeps_every_original_view_and_adds_the_redesigned_ones():
    nav = _nav()
    assert len(nav) == len(set(nav)), f"duplicate nav entries: {nav}"
    assert ORIGINAL_VIEWS <= set(nav), (
        "the redesign must not remove any of the console's own views")
    assert ADDED_VIEWS <= set(nav)


def test_there_is_no_second_navigation():
    """A sidebar is what made the product look like a tab inside something
    else. The host must not create one."""
    host = (DASHBOARD / "redesign" / "app.py").read_text(encoding="utf-8")
    for forbidden in ("st.sidebar", "SCREENS = (", "st.radio(\"screen\""):
        assert forbidden not in host, f"{forbidden} reintroduces a second nav"
    assert "stSidebar" in host and "display:none" in host, (
        "the host must hide Streamlit's own chrome")


def test_every_added_view_is_owned_by_the_redesign_module():
    views = (FORK / "redesign_views.js").read_text(encoding="utf-8")
    for view in ADDED_VIEWS:
        assert f"'{view}'" in views, f"{view} is in the nav but unowned"


def test_every_added_view_has_markup_built_for_it():
    """The host must supply markup for each view it put in the nav."""
    import ast
    host = (DASHBOARD / "redesign" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(host)
    keys = {k.value for node in ast.walk(tree)
            if isinstance(node, ast.Dict)
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert ADDED_VIEWS <= keys, (
        f"no markup is built for: {sorted(ADDED_VIEWS - keys)}")


# ==========================================================================
# controls
# ==========================================================================
def test_every_control_the_views_emit_has_a_handler():
    """A button that reaches the host and finds no branch is a dead control.

    The operations are read out of the rendered markup rather than restated,
    so adding a control without a handler fails here.
    """
    import re

    from seraph.dashboard.redesign import component_views as V
    from seraph.dashboard.redesign import component_workspace as W

    state = dict(runs=[], run_id="r", dates=[], date="d",
                 sector_bases=["a", "b"], sector_basis="a",
                 news_clocks=["current_news"], news_clock="current_news",
                 news_layers=["off", "on"], news_layer="off")
    markup = V.overview({}, state)
    for role in ("retail", "institutional", "regulator"):
        markup += W.workspace(
            dict(portfolios=[{"portfolio_id": "p1", "name": "n"}],
                 scenarios=[{"scenario_id": "s1", "name": "n",
                             "assumption_version": 1}],
                 cases=[{"case_id": "c1", "title": "t", "status": "triage",
                         "version": 1}],
                 holdings={}, identity_note="", now_ist=""),
            role, state)

    ops = set(re.findall(r'data-rd-op="([a-z_]+)"', markup))
    assert ops, "the views emit no controls at all"

    host = (DASHBOARD / "redesign" / "app.py").read_text(encoding="utf-8")
    unhandled = sorted(op for op in ops if f'"{op}"' not in host)
    # Operations the backend dispatcher owns need no branch in the host:
    # they fall through to `dispatch`, which is what should handle them.
    from seraph.dashboard.console_backend import WORKFLOW_ROLES
    unhandled = [op for op in unhandled if op not in WORKFLOW_ROLES]
    assert unhandled == [], f"controls with no handler: {unhandled}"


def test_selection_controls_are_routed():
    """Changing run, date, basis or clock must re-project, not be dropped."""
    host = (DASHBOARD / "redesign" / "app.py").read_text(encoding="utf-8")
    assert '"rd_select"' in host
    for field in ("run", "date", "sector_basis", "news_clock", "news_layer"):
        assert f'"{field}"' in host, f"{field} selection is not routed"


def test_a_refused_operation_does_not_replace_the_console():
    """A refusal is a readable result bound to its request id."""
    import ast
    tree = ast.parse((DASHBOARD / "redesign" / "app.py").read_text(
        encoding="utf-8"))
    handler = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "_handle")
    handlers = [h for n in ast.walk(handler)
                if isinstance(n, ast.Try) for h in n.handlers]
    caught = {e.id for h in handlers if h.type is not None
              for e in ast.walk(h.type) if isinstance(e, ast.Name)}
    assert {"ValueError", "PermissionError"} <= caught, (
        "a refused role action must come back as a refusal, not an "
        "exception that replaces the whole console")


# ==========================================================================
# honesty — the FABRICATED claim
# ==========================================================================
def test_the_fabricated_tag_is_claimed_from_the_payload():
    """bridge.js stamps FABRICATED on every card at load, before any payload
    has arrived — so it cannot know. Its own comment says why that is wrong.

    The fork must re-tag from `connected_surfaces`, so a card backed by real
    data loses the claim and a card that is not keeps it.
    """
    views = (FORK / "redesign_views.js").read_text(encoding="utf-8")
    assert "connected_surfaces" in views, (
        "the tag must be decided from the payload, not left as stamped")
    assert "retagCards" in views
    for surface in ("signals", "sector_stress", "assets"):
        assert surface in views, f"{surface} is not re-tagged"


def test_panels_with_no_engine_were_removed_not_relabelled():
    """INPUT COMMODITIES and METEOROLOGICAL INPUTS had no data source
    anywhere in SERAPH. A prettier label on invented numbers is still
    invented numbers, so they are gone from the fork."""
    html = (FORK / "index.html").read_text(encoding="utf-8")
    for gone in ("INPUT COMMODITIES", "METEOROLOGICAL INPUTS"):
        assert gone not in html, f"{gone} has no engine and must not be shown"
    # ...and they are still in Classic, which this work does not touch.
    classic = (CLASSIC / "index.html").read_text(encoding="utf-8")
    assert "INPUT COMMODITIES" in classic, "Classic must be untouched"


def test_the_news_layer_is_attached_by_default():
    """Detached, the map/sector/geography surfaces fall back to the console's
    illustrative layer and read FABRICATED. Attached, `preview_surfaces` is
    empty and all four are real — so attached is the honest default."""
    host = (DASHBOARD / "redesign" / "app.py").read_text(encoding="utf-8")
    assert 'setdefault("rd_news_layer", "on")' in host


@pytest.mark.parametrize("surface", ["signals", "sector_stress", "geography",
                                     "assets"])
def test_the_real_channel_reports_these_surfaces_as_connected(surface):
    """The premise behind removing the tag: with the engine attached these
    surfaces carry real data, and the payload says so itself."""
    from seraph.dashboard.redesign import data, news_data

    paths = data.store_paths()
    if not paths["news"].exists():
        pytest.skip("no news store configured")
    state = news_data.news_state(paths["news"], role="retail")
    if not state.get("connected"):
        pytest.skip("the news channel is not attached in this environment")
    if not state.get("signals"):
        pytest.skip("the store holds no eligible event at this clock")
    assert surface in state["connected_surfaces"], (
        f"{surface} is drawn as real but the payload does not list it as "
        f"connected")
    assert surface not in (state.get("preview_surfaces") or []), (
        f"{surface} is listed as a fabricated preview")
