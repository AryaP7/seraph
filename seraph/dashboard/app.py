# C12 — Dashboard (FR39–FR42): the Streamlit application.
"""Renders SERAPH state at the viewer's role.

Streamlit per SPEC NFR36; Plotly Dash was considered and explicitly rejected
(SPEC §7 item 7). **This layer contains no analytics** — every number is
fetched from C9/C10/C11 or the store (ARCHITECTURE §1). A chart that needs a
value no component produces is a missing FR, not a dashboard feature, and is
shown as an explicit gap rather than filled with something plausible.

RBAC is applied by `gateway.build_view` before anything reaches this module, so
a field a role may not see never enters the page (CT-8). The role selector here
is a **demo affordance, not authentication** — NFR25 specifies OAuth2, which is
out of scope for this build, and the UI says so rather than implying a security
guarantee it does not provide.

Run: streamlit run seraph/dashboard/app.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import streamlit as st

from seraph.dashboard.gateway import ROLES, build_view, redistribution_notice
from seraph.dashboard.theme import (
    ALERT_COLOUR,
    REGIME_COLOURS,
    REGIME_LABELS,
    TOKENS,
    css,
    signature_html,
)
from seraph.pillars.rmt import mp_bounds

PILLAR_LABELS = {
    "hawkes": ("MARKET TOXICITY", "MTS"),
    "rmt": ("SYSTEMIC COUPLING", "λ1/N"),
    "hamilton": ("LIQUIDITY STRESS", "LSD"),
}


GLOBE_ASSET = Path(__file__).parent / "assets" / "globe.html"


#: The asset collapses to a single stacked column at `@media(max-width:1180px)`
#: (its `main` grid is `296px 1fr 292px` above that). Streamlit's default block
#: container leaves the iframe ~1126px, just under the threshold, which silently
#: unstacks both rails and pushes them past the iframe's height. The container
#: must therefore be widened past 1180px for the intended layout to appear.
GLOBE_MIN_WIDTH_PX = 1180
GLOBE_HEIGHT_PX = 960


def render_globe(height: int = GLOBE_HEIGHT_PX) -> None:
    """Embed the standalone three.js geospatial stage — integration step 1 of 2.

    **Step 1 (this):** the scene is embedded verbatim in Streamlit's sandboxed
    iframe, purely to confirm it renders in this environment. It runs on its
    own internal geometry and is **not** wired to E7/E8/E10, so it is labelled
    as such. `datasource.py` refuses to show plausible placeholders on a risk
    instrument; an unlabelled 3D surface that looks like live exposure would be
    exactly that failure, so the banner is not optional.

    **Step 2 (later):** vendor three.js locally, drop the Overpass call, and
    feed it the real reconciled state once C9 is producing a CSRS series.

    Requires network: three.js r128 from cdnjs, and OSM Overpass geometry.
    """
    import streamlit.components.v1 as components

    if not GLOBE_ASSET.exists():
        st.info(f"Geospatial stage asset not found at {GLOBE_ASSET}.")
        return
    st.markdown(
        f'<div style="background:{TOKENS["accent"]}1A;border-left:3px solid '
        f'{TOKENS["accent"]};padding:6px 12px;font-family:var(--mono);'
        f'font-size:10.5px;color:{TOKENS["ink_secondary"]};margin:6px 0">'
        f'GEOSPATIAL STAGE — rendering check only. This scene is not yet '
        f'connected to the SERAPH pipeline; its geometry and markers are '
        f'internal to the asset and are <b>not</b> a market reading.</div>',
        unsafe_allow_html=True)
    # scrolling=True is deliberate: on a viewport narrower than
    # GLOBE_MIN_WIDTH_PX the asset's own media query stacks the rails, and a
    # reachable scrollbar is strictly better than silently clipping them.
    components.html(GLOBE_ASSET.read_text(encoding="utf-8"),
                    height=height, scrolling=True)


# --- DEMO SCAFFOLDING (delete with seraph/dashboard/demo_data.py) ----------
CONSOLE_ASSET = Path(__file__).parent / "assets" / "console.html"


def render_console(height: int = 1000) -> None:
    """The unified console — the design reference for the eventual C12 build.

    Self-contained (no CDN, no fetch) and rendered in the same terminal idiom as
    the geospatial stage, so role switching and the CSRS system share one visual
    language instead of Streamlit's default widget chrome. Role buttons apply
    the CT-8 field split; in the real gateway those fields are omitted upstream
    rather than dimmed in the view, which the ACCESS panel says explicitly.

    Every value it displays is fabricated — see DEMO-DELETE-ME.md.
    """
    import streamlit.components.v1 as components

    if not CONSOLE_ASSET.exists():
        st.info(f"Console asset not found at {CONSOLE_ASSET}.")
        return
    components.html(CONSOLE_ASSET.read_text(encoding="utf-8"),
                    height=height, scrolling=True)


def render_sparkline(values, colour: str, h: int = 34) -> str:
    """Inline SVG trend line. Purely presentational — no axes, no scale claim."""
    v = np.asarray(values, dtype=float)
    if v.size < 2:
        return ""
    lo, hi = float(v.min()), float(v.max())
    span = max(hi - lo, 1e-9)
    xs = np.linspace(0.0, 240.0, v.size)
    ys = h - 2 - (v - lo) / span * (h - 4)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (f'<svg viewBox="0 0 240 {h}" width="100%" height="{h}" '
            f'preserveAspectRatio="none" style="display:block">'
            f'<polyline points="{pts}" fill="none" stroke="{colour}" '
            f'stroke-width="1.4" vector-effect="non-scaling-stroke"/></svg>')


def render_trends(history: dict) -> str:
    """Four trend strips. Present ONLY in demo mode — the real fetch layer
    returns no `history` key, so this silently disappears in production."""
    spec = (("csrs", "CSRS", TOKENS["stressed"]),
            ("lam1", "COUPLING lambda1/N", TOKENS["accent"]),
            ("mts", "CONTAGION MTS", TOKENS["tranquil"]),
            ("lsd", "LIQUIDITY LSD", TOKENS["crisis"]))
    cells = []
    for key, label, colour in spec:
        series = history.get(key) or []
        if not series:
            continue
        cells.append(
            f'<div style="flex:1;min-width:150px">'
            f'<div style="font-family:var(--mono);font-size:9.5px;letter-spacing:.12em;'
            f'color:{TOKENS["ink_tertiary"]};display:flex;justify-content:space-between">'
            f'<span>{label}</span><span style="color:{colour}">'
            f'{float(series[-1]):.3f}</span></div>'
            f'{render_sparkline(series, colour)}</div>')
    return (f'<div style="display:flex;gap:14px;padding:9px 12px;'
            f'background:var(--bg-sunken);border:1px solid var(--separator);'
            f'border-radius:4px;margin-top:10px">{"".join(cells)}</div>')
# --- END DEMO SCAFFOLDING --------------------------------------------------


def _card(title: str, body_html: str, right: str = "") -> str:
    right_html = (f'<span style="float:right;color:{TOKENS["ink_quaternary"]}">'
                  f'{right}</span>') if right else ""
    return (f'<div class="srph-card"><h3>{title}{right_html}</h3>'
            f'<div class="srph-body">{body_html}</div></div>')


def render_ticker(view: dict, pillar_scores: dict) -> str:
    """Dense status strip — the reference mock's idiom, carrying real values."""
    items = [f"<span><b>CSRS</b>{view['csrs']:.3f}</span>",
             f"<span><b>CI</b>{view['ciLower']:.3f}–{view['ciUpper']:.3f}</span>"]
    for pid, (_, short) in PILLAR_LABELS.items():
        val = pillar_scores.get(pid)
        shown = "—" if val is None else f"{val:.3f}"
        items.append(f"<span><b>{short}</b>{shown}</span>")
    if view.get("maskDegraded"):
        items.append(f'<span style="color:{TOKENS["stressed"]}"><b>MASK</b>DEGRADED</span>')
    return f'<div class="srph-ticker">{"".join(items)}</div>'


def render_regime_stack(xi) -> str:
    """FR39 regime-probability stack.

    Regime is encoded three times — colour, fixed stack position (tranquil
    always left, crisis always right) and an explicit text label — because
    green/amber/red alone fails for red-green colour blindness (DESIGN.md §3).
    """
    if xi is None:
        return '<div class="srph-note">awaiting Pillar 3 fit</div>'
    segs, labels = [], []
    for i, (p, colour, name) in enumerate(zip(xi, REGIME_COLOURS, REGIME_LABELS)):
        segs.append(f'<div style="width:{p*100:.1f}%;background:{colour};height:100%"></div>')
        labels.append(
            f'<span style="font-family:var(--mono);font-size:10px;color:{colour}">'
            f'{name} {p*100:.0f}%</span>')
    return (
        '<div style="display:flex;height:22px;border-radius:3px;overflow:hidden;'
        f'background:{TOKENS["bg_overlay"]}">{"".join(segs)}</div>'
        f'<div style="display:flex;justify-content:space-between;margin-top:6px">'
        f'{"".join(labels)}</div>'
    )


def render_shapley(shapley: dict) -> str:
    """FR31/FR39 pillar decomposition. A masked pillar is drawn in the
    'noise' ink at zero — present but visibly subordinate, never hidden."""
    if not shapley:
        return '<div class="srph-note">no decomposition available</div>'
    total = sum(abs(v) for v in shapley.values()) or 1.0
    rows = []
    for pid, val in shapley.items():
        label = PILLAR_LABELS.get(pid, (pid.upper(), pid))[0]
        pct = 100.0 * abs(val) / total
        colour = TOKENS["accent"] if val > 0 else TOKENS["ink_quaternary"]
        rows.append(
            f'<div style="margin-bottom:7px">'
            f'<div style="font-family:var(--mono);font-size:10px;'
            f'color:{TOKENS["ink_secondary"]};display:flex;justify-content:space-between">'
            f'<span>{label}</span><span>{val:+.3f}</span></div>'
            f'<div style="height:4px;background:{TOKENS["bg_overlay"]};border-radius:2px;'
            f'margin-top:3px"><div style="width:{pct:.1f}%;height:100%;'
            f'background:{colour};border-radius:2px"></div></div></div>')
    return "".join(rows)


def render_signals(view: dict, sector_flags) -> str:
    """Signals feed — the mock's most useful idea. Entries are derived only
    from values the system actually emits: the alert level, mask degradation
    and sector micro-flags. Nothing is invented to fill the panel."""
    out = []
    level = view["alertLevel"]
    if level != "green":
        colour = ALERT_COLOUR[level]
        out.append(
            f'<div style="padding:8px 0;border-bottom:1px solid {TOKENS["separator"]}">'
            f'<span class="srph-chip" style="color:{colour};border-color:{colour}77">'
            f'{level.upper()}</span>'
            f'<div style="font-size:12px;margin-top:4px;color:{TOKENS["ink_primary"]}">'
            f'{view.get("explanation","")}</div></div>')
    for flag in sector_flags or ():
        sector = flag.get("sectorId") if isinstance(flag, dict) else flag.sector_id
        state = flag.get("flag") if isinstance(flag, dict) else flag.flag
        if state != "amber":
            continue
        out.append(
            f'<div style="padding:8px 0;border-bottom:1px solid {TOKENS["separator"]}">'
            f'<span class="srph-chip" style="color:{TOKENS["stressed"]};'
            f'border-color:{TOKENS["stressed"]}77">SECTOR</span>'
            f'<div style="font-size:12px;margin-top:4px">{sector}: intensity above '
            f'baseline</div></div>')
    if not out:
        out.append('<div class="srph-note">no active signals</div>')
    return "".join(out)


def render_mp_density(f_t, lam_minus, lam_plus, q_t, n_t) -> str:
    """FR39 Marchenko–Pastur plot. The bulk is drawn in `--ink-quaternary`,
    DESIGN.md's designated 'noise' value: present, subordinate, not hidden.
    λ± is labelled with the Q actually in force (AMENDMENT-02), never a
    hard-coded Q=2."""
    if lam_plus is None:
        return '<div class="srph-note">awaiting Pillar 2 run</div>'
    xs = np.linspace(max(lam_minus * 0.5, 1e-3), lam_plus * 1.35, 90)
    dens = np.where(
        (xs > lam_minus) & (xs < lam_plus),
        np.sqrt(np.clip((lam_plus - xs) * (xs - lam_minus), 0, None)) / (2 * np.pi * xs),
        0.0)
    peak = dens.max() or 1.0
    bars = []
    for x, d in zip(xs, dens):
        h = 100.0 * d / peak
        colour = TOKENS["ink_quaternary"] if x <= lam_plus else TOKENS["crisis"]
        bars.append(f'<div style="flex:1;height:{max(h,1):.1f}%;background:{colour};'
                    f'margin-right:1px"></div>')
    return (
        f'<div style="display:flex;align-items:flex-end;height:90px">{"".join(bars)}</div>'
        f'<div class="srph-note" style="margin-top:6px">'
        f'N_t={n_t} · Q_t={q_t:.2f} · λ±=[{lam_minus:.3f}, {lam_plus:.3f}] · '
        f'F_t={f_t:.4f}</div>')


def main() -> None:
    st.set_page_config(page_title="SERAPH", layout="wide",
                       initial_sidebar_state="collapsed")
    st.markdown(css(), unsafe_allow_html=True)
    # Streamlit's default block container caps the content column well below the
    # geospatial asset's 1180px breakpoint (see GLOBE_MIN_WIDTH_PX). `layout=
    # "wide"` alone is not enough — the padding and max-width still bind.
    st.markdown(
        "<style>.block-container{max-width:100%!important;"
        "padding-left:1.2rem!important;padding-right:1.2rem!important;"
        "padding-top:2.4rem!important}</style>",
        unsafe_allow_html=True)

    with st.sidebar:
        st.caption("Demo affordance — not authentication (NFR25 OAuth2 is out of scope)")
        role = st.selectbox("Role", ROLES, index=1)
        # DEMO SCAFFOLDING: view switch between the unified console and the
        # original Streamlit-native panels.
        unified = st.checkbox(
            "Unified console", value=True,
            help="The full-width terminal console with role buttons. Uncheck "
                 "for the original Streamlit-native panels.")
        show_globe = st.checkbox(
            "Geospatial stage (3D)", value=True,
            help="WebGL scene. Needs network access for three.js (cdnjs) and "
                 "OSM Overpass geometry. Not yet wired to the pipeline.")
        st.caption(redistribution_notice())

    from seraph.dashboard.datasource import latest_state

    state = latest_state()
    if state is None:
        st.markdown('<div class="srph-brand">SER<span class="accent">APH</span></div>',
                    unsafe_allow_html=True)
        st.warning(
            "No scored output yet. The dashboard shows only what the pipeline "
            "has produced — run the ingestion, universe, observation and pillar "
            "steps first. Nothing here is simulated to fill the gap.")
        if show_globe:
            render_globe()
        return

    view_res = build_view(
        role, state["point"],
        explanation=state.get("explanation", ""),
        pillar_scores=state.get("pillar_scores", {}),
        regime_probabilities=state.get("xi"),
        sector_flags=state.get("sector_flags", ()),
        spectral=state.get("spectral", {}),
        contagion_network=state.get("contagion_network"),
    )
    if view_res.status == "error":
        st.error(f"gateway rejected the request: {view_res.error}")
        return
    view = view_res.value

    # DEMO SCAFFOLDING: the unified console carries its own brand, nav, ticker
    # and DEMO chip, so Streamlit must not print a second SERAPH header above
    # it — two brands stacked read as two products.
    if unified:
        render_console()
        return

    if state.get("demo"):
        st.markdown(
            f'<div style="background:{TOKENS["crisis"]}22;border-left:3px solid '
            f'{TOKENS["crisis"]};padding:7px 12px;font-family:var(--mono);'
            f'font-size:11px;color:{TOKENS["ink_primary"]};margin-bottom:8px">'
            f'DEMO MODE — synthetic T0 data, not a market reading. '
            f'Unset SERAPH_DEMO to use the live pipeline.</div>',
            unsafe_allow_html=True)

    st.markdown(
        f'<div class="srph-brand">SER<span class="accent">APH</span>'
        f'<span style="font-family:var(--mono);font-size:10px;letter-spacing:.14em;'
        f'color:{TOKENS["ink_tertiary"]};margin-left:18px">'
        f'SYSTEMIC EARLY-RISK ALERT FOR PORTFOLIO HEALTH · {view["ts"]}</span></div>',
        unsafe_allow_html=True)
    st.markdown(render_ticker(view, state.get("pillar_scores", {})),
                unsafe_allow_html=True)
    # `history` is only ever populated by demo_data.py, so this strip vanishes
    # automatically once the demo module is removed.
    if state.get("history"):
        st.markdown(render_trends(state["history"]), unsafe_allow_html=True)
    if show_globe:
        render_globe()

    left, mid, right = st.columns([1.05, 1.5, 1.05])

    with mid:
        st.markdown(signature_html(
            view["csrs"], view["variance"], view["ciLower"], view["ciUpper"],
            view["alertLevel"], view.get("maskDegraded", False)),
            unsafe_allow_html=True)
        if "regimeProbabilities" in view:
            st.markdown(_card("REGIME PROBABILITIES",
                              render_regime_stack(view["regimeProbabilities"])),
                        unsafe_allow_html=True)
        spectral = view.get("spectral") or {}
        if spectral:
            st.markdown(_card("MARCHENKO–PASTUR SPECTRUM", render_mp_density(
                spectral.get("f_t", 0.0), spectral.get("lambda_minus"),
                spectral.get("lambda_plus"), spectral.get("q_t", 0.0),
                spectral.get("n_t", 0))), unsafe_allow_html=True)

    with left:
        st.markdown(_card("SIGNALS", render_signals(view, view.get("sectorFlags"))),
                    unsafe_allow_html=True)

    with right:
        if "shapley" in view:
            st.markdown(_card("PILLAR DECOMPOSITION", render_shapley(view["shapley"]),
                              right="SHAPLEY"), unsafe_allow_html=True)
        if role == "retail":
            st.markdown(_card("WHAT THIS MEANS",
                              f'<div style="font-size:13px;line-height:1.5">'
                              f'{view.get("explanation","")}</div>'),
                        unsafe_allow_html=True)


if __name__ == "__main__":
    main()
