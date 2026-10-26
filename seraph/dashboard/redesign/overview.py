# C12 — Redesigned console: the OVERVIEW screen (FR39-FR42, FR29, FR41).
"""The first redesigned screen, built from SERAPH's actual outputs.

Reading order on the page mirrors the order the questions are asked in:
what is the score and what was the market doing (dial + history), which
pillars produced it (three cards), how they combined (breakdown), what it
touches (sectors / holdings), and when (timeline).

**The honesty rules this screen is written against.** They are listed here
because every one of them is a thing the layout would otherwise invite:

1. An unavailable composite keeps the dial's geometry and fills none of it.
   `instruments.composite_dial` has no branch that substitutes zero, and the
   reason is rendered beside it.
2. Hamilton is a declared structural absence and Hawkes is in warm-up. Both
   render through `components.pillar_card`'s "declared not scored" state with
   the engine's own reason — not as an empty chart and not as 0.
3. The dial's arcs are the CSRS point estimate and the FR29 interval, each
   named in the legend. No arc exists that does not correspond to a quantity
   the payload carries.
4. Shapley contributions are signed and sum to the CSRS, so they are drawn on
   a symmetric axis in score units. The one widget that draws shares —
   `weight_tracks` — draws D2 effective weights, which are normalised by
   construction, and says so.
5. A session with no CSRS stays missing in the chart and hollow in the
   timeline.
6. Every stale, historical or unavailable state carries its timestamp or its
   scenario label.
7. The news channel (F2) does not appear in any CSRS surface here. Its card
   states the separation and carries no number that could be mistaken for a
   pillar input.
"""
from __future__ import annotations

import streamlit as st

import time

from . import charts, components as C, data, instruments as I, tokens as T

#: How often the live view re-reads the runtime. Classic declares
#: `LIVE_POLL_SECONDS = 2.0` and never uses it, so there is no behaviour to
#: copy — this implements what the constant intends.
#:
#: The poll lives in a Streamlit **fragment**, which reruns only itself. That
#: is what makes polling safe: Classic's own note explains that rebuilding the
#: page when the revision moves would silently rebase a half-typed form and
#: lose it, which is why Classic recorded the movement instead of acting on
#: it. A fragment refreshes the live panel without touching the rest of the
#: page, so neither the reading nor the draft is sacrificed.
LIVE_POLL_SECONDS = 2.0

#: What the top bar calls each basis, and what that basis is allowed to claim.
BASIS_CURRENT = "Current — live runtime"
BASIS_ARCHIVE = "Historical — archive replay"
BASES = (BASIS_CURRENT, BASIS_ARCHIVE)


# ==========================================================================
# top bar
# ==========================================================================
def top_bar(*, basis: str, role: str, selection_label: str,
            freshness: list[str]) -> None:
    """Page identity, what is selected, and the freshness/mode statement."""
    C.html_block(
        f'<div class="rd-topbar">'
        f'<div><p class="rd-eyebrow">SERAPH · redesigned console</p>'
        f'<h1>Overview</h1>'
        f'<p class="rd-panel-sub" style="margin-top:4px">{C.esc(selection_label)}</p>'
        f'</div>'
        f'<div class="rd-topbar-right">'
        f'{C.chip("basis", basis, tone="accent")}'
        f'{C.chip("role", role)}'
        f'{"".join(freshness)}'
        f'</div></div>')


def freshness_chips(*, basis: str, liveness: dict | None,
                    live: dict | None, forecast: dict | None) -> list[str]:
    """The mode/freshness statement, assembled from what each source says.

    Nothing is inferred here. `liveness.headline` is the publication gate's
    own verdict and is passed through verbatim, because softening it on the
    way to the screen is exactly the defect `liveness_of` was written to fix.
    """
    out = []
    if basis == BASIS_ARCHIVE and liveness:
        tone = "ok" if liveness.get("is_live") else "bad"
        out.append(C.chip(liveness.get("headline", "publication state unknown"),
                          tone=tone))
        if liveness.get("observed_at"):
            out.append(C.chip("observed", str(liveness["observed_at"])))
        if liveness.get("market_state"):
            out.append(C.chip("market", str(liveness["market_state"])))
    if basis == BASIS_CURRENT and live is not None:
        if live.get("available"):
            out.append(C.chip("live decision", str(live.get("as_of") or ""),
                              tone="ok" if live.get("is_current") else "warn"))
        else:
            out.append(C.chip("no live decision committed", tone="bad"))
        health = live.get("health") or {}
        if health:
            out.append(C.chip("worker",
                              "stale" if health.get("stale") else "committing",
                              tone="warn" if health.get("stale") else "ok"))
    if forecast and forecast.get("available"):
        stale = (forecast.get("staleness") or {}).get("stale")
        out.append(C.chip("forecast as of", str(forecast.get("as_of") or ""),
                          tone="warn" if stale else "ok"))
    return out


# ==========================================================================
# row 1 — the instrument and the history
# ==========================================================================
def composite_row(*, basis: str, payload: dict | None, live: dict | None,
                  history: dict | None, selected_date: str | None,
                  point: dict | None, live_path=None,
                  live_mode: str = "live") -> None:
    left, right = st.columns([0.95, 2.05], gap="medium")

    with left:
        with C.panel("Composite systemic risk", "CSRS · FR28 / FR29"):
            if basis == BASIS_CURRENT:
                # Polled, in a fragment, so the live reading refreshes without
                # rebasing the rest of the page. See `live_monitor`.
                live_monitor(live_path, live_mode)
            else:
                _archive_dial(payload, point)

    with right:
        with C.panel("Market state history",
                     "FR41 — CSRS overlaid on official Nifty 500 returns"):
            if basis == BASIS_CURRENT and not (live or {}).get("available"):
                C.html_block(C.unavailable(
                    "no current history",
                    "the live runtime has committed no decisions, so there is "
                    "no current series to plot. The archive replay below is a "
                    "different basis and is labelled as one — it is not shown "
                    "here in its place",
                    str((live or {}).get("reason") or "")))
            else:
                chart, note = charts.market_state_history(
                    history or {}, selected_date=selected_date)
                if chart is None:
                    C.html_block(C.unavailable("no overlay to plot", note))
                else:
                    st.altair_chart(chart, use_container_width=True)
                    C.html_block(f'<p class="rd-panel-note">{C.esc(note)}</p>')
                    _coverage_line(history)


def _archive_dial(payload: dict | None, point: dict | None) -> None:
    comp = data.composite_of(payload)
    stamp = (payload or {}).get("timestamp") or (point or {}).get(
        "evaluation_timestamp")
    caption = (f"historical replay · decision {stamp}" if stamp
               else "historical replay")
    C.html_block(I.composite_dial(
        value=comp["value"], ci_lower=comp["ci_lower"],
        ci_upper=comp["ci_upper"], alert_level=comp["alert_level"],
        unavailable_reason=comp["reason"], caption=caption))

    liveness = (payload or {}).get("liveness") or {}
    if liveness.get("why"):
        C.html_block(
            '<div class="rd-card rd-card--flat" style="margin-top:12px">'
            '<p class="rd-unavail-label">why this is not a current reading</p>'
            + "".join(f'<p class="rd-reason">· {C.esc(w)}</p>'
                      for w in liveness["why"]) + "</div>")
    if comp["mask_degraded"]:
        C.html_block(
            f'<div style="margin-top:10px">'
            f'{C.chip("D2 mask degraded — not comparable with full-coverage readings", tone="warn")}'
            f'</div>')
    if (payload or {}).get("view", {}).get("explanation"):
        C.html_block(f'<p class="rd-panel-note">'
                     f'{C.esc(payload["view"]["explanation"])}</p>')


@st.fragment(run_every=LIVE_POLL_SECONDS)
def live_monitor(live_path, mode: str) -> None:
    """Poll the live runtime and render what it has actually committed.

    Reruns only this fragment, every `LIVE_POLL_SECONDS`. `revision()` is the
    cheap id that moves exactly when the screen's content moves, so a tick
    that finds it unchanged rebuilds nothing.

    **Nothing here invents a reading.** With no committed decision the dial
    keeps its track and fills none of it, and the panel states that the
    runtime has committed nothing — a polled absence is still an absence, and
    polling it more often does not make it a number.
    """
    revision = data.live_revision(live_path)
    seen = st.session_state.get("rd_live_revision")
    if revision and revision != seen:
        st.session_state["rd_live_revision"] = revision
        st.session_state["rd_live_revision_at"] = time.strftime("%H:%M:%S")

    live = data.live_decision(live_path, mode=mode)
    _current_dial(live)

    bits = [C.chip("polling", f"every {LIVE_POLL_SECONDS:g}s", tone="ok")]
    if revision:
        bits.append(C.chip("runtime revision", revision[:12]))
        if st.session_state.get("rd_live_revision_at"):
            bits.append(C.chip("last moved",
                               str(st.session_state["rd_live_revision_at"])))
    else:
        bits.append(C.chip("no runtime store", tone="warn"))
    C.html_block(C.chips(bits))
    C.html_block(
        '<p class="rd-panel-note">The revision is a hash of the stream head, '
        'the latest decision and the news revision. It moving is the only '
        'evidence that anything the screen shows has changed; a tick that '
        'finds it unchanged rebuilds nothing, and a revision that never moves '
        'means the runtime has committed nothing — not that the poll '
        'failed.</p>')


def _current_dial(live: dict | None) -> None:
    live = live or {}
    if not live.get("available"):
        C.html_block(I.composite_dial(
            value=None,
            unavailable_reason=str(live.get("reason")
                                   or "no live decision is available"),
            caption=f"basis: {live.get('mode', 'live')} · no fallback to an archive run"))
        health = live.get("health") or {}
        if health:
            C.html_block(
                '<div class="rd-card rd-card--flat" style="margin-top:12px">'
                '<p class="rd-unavail-label">worker health — a separate fact '
                'from the score</p>'
                f'<p class="rd-reason">{C.esc(health.get("note", ""))}</p>'
                f'<p class="rd-reason rd-num">last pass '
                f'{C.esc(health.get("last_pass_at") or "never")} · stream '
                f'version {C.esc(health.get("stream_version"))} · undelivered '
                f'{C.esc(health.get("undelivered_events"))} · dead letters '
                f'{C.esc(health.get("dead_letters"))}</p></div>')
        return

    comp = data.composite_of(live.get("payload"))
    age = live.get("age_seconds")
    age_text = (f"{age / 60:.0f} min old" if isinstance(age, (int, float))
                else "age not recorded")
    C.html_block(I.composite_dial(
        value=comp["value"], ci_lower=comp["ci_lower"],
        ci_upper=comp["ci_upper"], alert_level=comp["alert_level"],
        unavailable_reason=comp["reason"],
        caption=(f"decision {live.get('decision_id')} · as of "
                 f"{live.get('as_of')} · {live.get('publication_state')} · "
                 f"{age_text}")))
    if not live.get("is_current"):
        C.html_block(f'<div style="margin-top:10px">'
                     f'{C.chip("not publishable as current", tone="warn")}</div>'
                     f'<p class="rd-panel-note">{C.esc(live.get("reason"))}</p>')


def _coverage_line(history: dict | None) -> None:
    cov = (history or {}).get("coverage") or {}
    rep = (history or {}).get("representativeness") or {}
    bits = []
    if cov:
        bits.append(C.chip("CSRS dates", str(cov.get("csrs_dates", "—"))))
        bits.append(C.chip("matched to benchmark", str(cov.get("matched", "—"))))
        missing = cov.get("benchmark_missing")
        if missing:
            bits.append(C.chip("benchmark missing", str(missing), tone="warn"))
    if rep.get("available") and isinstance(rep.get("correlation"), (int, float)):
        bits.append(C.chip("descriptive correlation",
                           f"{rep['correlation']:.3f}"))
    if bits:
        C.html_block(C.chips(bits))
    if rep.get("note"):
        C.html_block(f'<p class="rd-panel-note">{C.esc(rep["note"])}</p>')


# ==========================================================================
# row 2 — the three pillars
# ==========================================================================
def pillar_row(payload: dict | None, *, basis: str,
               live: dict | None = None) -> None:
    source = payload if basis == BASIS_ARCHIVE else (live or {}).get("payload")
    rows = data.pillar_rows(source)
    with C.panel("Pillars", "Hawkes · RMT · Hamilton, in PILLAR_ORDER"):
        if not source:
            C.html_block(C.unavailable(
                "no pillar readings",
                "there is no decision payload on this basis, so no pillar has "
                "reported. This is an absence of input, not three readings of "
                "zero",
                str((live or {}).get("reason") or "")))
            return
        columns = st.columns(len(rows), gap="small")
        for column, row in zip(columns, rows):
            with column:
                C.html_block(C.pillar_card(row))
        declared = [r for r in rows if r["present"] and r["value"] is None]
        if declared:
            C.html_block(
                '<p class="rd-panel-note">'
                + "; ".join(f"<b>{C.esc(r['name'])}</b> is a declared absence: "
                            f"{C.esc(r['reason'])}" for r in declared)
                + ". A declared absence is an <b>Ok</b> emission carrying a "
                  "reason, not an error, and it is never rendered as zero.</p>")


# ==========================================================================
# row 3 — how the pillars combined
# ==========================================================================
def breakdown_row(payload: dict | None) -> None:
    with C.panel("Pillar readings — how this composite was formed",
                 "signed Shapley contributions and D2 effective weights"):
        view = (payload or {}).get("view") or {}
        if not view:
            C.html_block(C.unavailable(
                "no decomposition",
                "no decision payload is selected on this basis"))
            return
        if "shapley" not in view:
            C.html_block(C.unavailable(
                "decomposition withheld at this role",
                "the retail projection does not contain a Shapley vector — "
                "the field is absent from the payload, not hidden in it "
                "(gateway.ROLE_FIELDS). Switch role to institutional or "
                "regulator to see it"))
            return

        left, right = st.columns([1.35, 1], gap="medium")
        with left:
            C.html_block('<p class="rd-unavail-label" style="color:'
                         f'{T.TEXT_DIM}">contribution to the CSRS</p>')
            rows = [dict(r, colour=T.pillar_colour(r["name"]))
                    for r in data.contribution_rows(payload)]
            C.html_block(I.contribution_tracks(rows, unit="CSRS score units"))
        with right:
            C.html_block('<p class="rd-unavail-label" style="color:'
                         f'{T.TEXT_DIM}">D2 effective weights</p>')
            weights = [dict(r, colour=T.pillar_colour(r["name"]))
                       for r in data.weight_rows(payload)]
            C.html_block(I.weight_tracks(weights))
            total = sum(r["value"] for r in weights
                        if isinstance(r["value"], (int, float)))
            C.html_block(
                f'<p class="rd-panel-note">Weights <b>are</b> a normalised '
                f'allocation and sum to <span class="rd-num">{total:.3f}</span> '
                f'over the masked pillars, which is why they are drawn as '
                f'shares. The contributions on the left are not, and are not '
                f'drawn that way.</p>')
            mode = view.get("reconciliationMode")
            artefact = (payload or {}).get("view", {}).get("weightsArtefactId")
            bits = []
            if mode:
                bits.append(C.chip("reconciliation", str(mode)))
            if artefact:
                bits.append(C.chip("weights artefact", str(artefact)[:16] + "…"))
            if bits:
                C.html_block(C.chips(bits))


# ==========================================================================
# row 4 — sectors and holdings
# ==========================================================================
def exposure_row(payload: dict | None, *, no_payload_reason: str = "") -> None:
    """Sectors, holdings and flow.

    With no payload at all — the Current basis before the runtime has
    committed anything — each panel says *that*, rather than reporting the
    generic "no reason recorded" placeholder. An absence whose stated cause is
    wrong is not better than an absence with no cause.
    """
    left, right = st.columns([1.5, 1], gap="medium")
    sectors = (payload or {}).get("sector_observations") or {}
    absent = no_payload_reason if payload is None else ""

    with left:
        with C.panel("Measured sector activity",
                     "FR14 — native intraday jump counts against declared baselines"):
            if not sectors.get("available"):
                C.html_block(C.unavailable(
                    "no measured sector observations",
                    absent or str(sectors.get("reason") or "no reason recorded"),
                    str(sectors.get("blocked_by") or ""),
                    str(sectors.get("note") or "")))
            else:
                rows = [[s.get("sector"), s.get("count"), s.get("baseline"),
                         s.get("ratio"), s.get("flag")]
                        for s in (sectors.get("sectors") or [])]
                C.html_block(C.table(
                    ["sector", "jumps", "baseline", "ratio", "flag"], rows,
                    numeric_columns={1, 2, 3}))
            if sectors.get("analysis_note"):
                C.html_block(f'<p class="rd-panel-note">'
                             f'{C.esc(sectors["analysis_note"])}</p>')
            if sectors.get("analysis_mode"):
                C.html_block(C.chips([
                    C.chip("analysis mode", str(sectors["analysis_mode"]),
                           tone="warn" if sectors["analysis_mode"]
                           == "retrospective_archive" else ""),
                    C.chip("cutoff", str(sectors.get("analysis_cutoff") or "—")),
                ]))

        with C.panel("Pillar readings at this decision",
                     "the value each pillar reported, before the D2 mask"):
            chart, note = charts.pillar_detail(
                data.pillar_rows(payload), value_key="value",
                title="pillar score reported at this decision")
            if chart is None:
                C.html_block(C.unavailable("no pillar reported a value", note))
            else:
                st.altair_chart(chart, use_container_width=True)
                C.html_block(f'<p class="rd-panel-note">{C.esc(note)}</p>')
                C.html_block(
                    '<p class="rd-panel-note">These are the readings as '
                    'emitted. Whether a reading <b>entered the composite</b> '
                    'is the D2 mask, shown on the pillar cards above — a '
                    'pillar can report a value and still be excluded.</p>')

    with right:
        with C.panel("Holdings", "portfolio coverage at this decision"):
            portfolio = (payload or {}).get("portfolio")
            context = (payload or {}).get("portfolio_context")
            if not portfolio:
                C.html_block(C.unavailable(
                    "no holdings supplied",
                    absent or
                    "no saved portfolio is active for this role, so no "
                    "exposure has been calculated. An empty table here means "
                    "nothing was supplied, not that exposure is nil"))
            else:
                rows = [[k, v] for k, v in sorted(portfolio.items())
                        ] if isinstance(portfolio, dict) else []
                C.html_block(C.table(["field", "value"], rows,
                                     numeric_columns={1}))
                if context:
                    C.html_block(f'<p class="rd-panel-note">'
                                 f'{C.esc(context)}</p>')

        with C.panel("Market flow", "FR45 / FR51 — FII / DII, market aggregate"):
            flow = (payload or {}).get("flow") or {}
            if not flow.get("available"):
                C.html_block(C.unavailable(
                    "no flow print ingested",
                    absent or str(flow.get("reason") or "no reason recorded")))
            else:
                rows = [["FII net", flow.get("fiiNet")],
                        ["DII net", flow.get("diiNet")],
                        ["residual flow share", flow.get("residualFlowShare")],
                        ["total turnover", flow.get("totalTurnoverCrore")]]
                C.html_block(C.table(["measure", flow.get("units", "value")],
                                     rows, numeric_columns={1}))
                C.html_block(f'<p class="rd-panel-note">'
                             f'{C.esc(flow.get("scope", ""))}</p>')


# ==========================================================================
# row 5 — the shared bottom timeline
# ==========================================================================
def timeline_row(history: dict | None, *, selected_date: str | None) -> None:
    with C.panel("Decision timeline", "every decision date in the selected run"):
        rows = (history or {}).get("rows") or []
        C.html_block(I.timeline(rows, selected_date=selected_date))


# ==========================================================================
# the separation statement
# ==========================================================================
def channel_separation(news_pending: bool = True) -> None:
    """F1 and F2 are different channels and the screen must keep saying so."""
    with C.panel("Channel separation",
                 "F1 market pillars · F2 news intelligence"):
        C.html_block(
            '<div class="rd-card rd-card--flat">'
            '<p class="rd-reason">The composite score, the pillars and the '
            'breakdown above are the <b>F1</b> market channel. The <b>F2</b> '
            'news-intelligence channel is a separate subsystem: no news signal '
            'enters the CSRS, and nothing on this screen mixes the two. News '
            'exposure routes are documented mappings, not measured contagion, '
            'and they are rendered on their own screen so the distinction '
            'survives a glance.</p></div>')
        if news_pending:
            C.html_block(
                f'<div style="margin-top:10px">'
                f'{C.chip("F07 directed network", "PENDING", tone="warn")}'
                f'{C.chip("news exposure explorer", "separate from the measured Hawkes network")}'
                f'</div>'
                f'<p class="rd-panel-note">The directed contagion network '
                f'(F07) is not implemented and continues to display as '
                f'pending. Any news-exposure view is visually distinct from '
                f'the measured Hawkes network and is never drawn with the '
                f'pillar palette.</p>')


# ==========================================================================
# states
# ==========================================================================
def archive_unavailable(reason: str, archive_path) -> None:
    with C.panel("Overview", "historical archive"):
        C.html_block(C.unavailable(
            "no historical decision selected", reason,
            f"configured archive store: {archive_path}",
            "override with SERAPH_PROTOTYPE_STORE"))


def render(*, basis: str, role: str, payload: dict | None, point: dict | None,
           history: dict | None, selected_date: str | None,
           live: dict | None, forecast: dict | None,
           selection_label: str, live_path=None,
           live_mode: str = "live") -> None:
    """The whole OVERVIEW screen, in reading order."""
    liveness = (payload or {}).get("liveness")
    top_bar(basis=basis, role=role, selection_label=selection_label,
            freshness=freshness_chips(basis=basis, liveness=liveness,
                                      live=live, forecast=forecast))
    composite_row(basis=basis, payload=payload, live=live, history=history,
                  selected_date=selected_date, point=point,
                  live_path=live_path, live_mode=live_mode)
    pillar_row(payload, basis=basis, live=live)
    breakdown_row(payload if basis == BASIS_ARCHIVE else (live or {}).get("payload"))
    # Sectors, holdings and flow come off the projected archive payload. On
    # the Current basis there is none, so each panel is told to say that
    # rather than reporting a store-level reason it has not actually read.
    exposure_row(payload, no_payload_reason=(
        f"these are read from a projected decision, and this basis "
        f"({basis.lower()}) has none selected — "
        f"{(live or {}).get('reason', 'no decision is available')}"))
    timeline_row(history, selected_date=selected_date)
    channel_separation()
