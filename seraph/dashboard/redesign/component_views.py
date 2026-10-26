# C12 — Redesigned console: the views the component renders (FR39-FR49).
"""Markup for the redesigned screens, built in Python and carried in the payload.

The console is the product's UI, so these are entries in **its** nav rather
than a separate app. The component injects what this module returns and binds
the controls (`console_component/redesign_views.js`).

**Why the markup is built here.** The dial, the contribution tracks and the
timeline already exist in `instruments.py`, with the rules that matter encoded
and tested: an unavailable score keeps its track unfilled, a mask-excluded
pillar is never drawn as a measured zero, a scoreless session stays hollow. A
second implementation in JavaScript would be a second place for those to be
wrong. So they are rendered once, here, and shipped as strings.

Controls carry their operation declaratively — `data-rd-op` plus
`data-rd-field-*` / `data-rd-const-*` / `data-rd-json-*` / `data-rd-file-*` —
so the browser binder needs no knowledge of what any particular form means,
and every operation leaves through the console's own `request()` with its
idempotency id and stale-context refusal intact.
"""
from __future__ import annotations

import html

from . import components as C, data, instruments as I, tokens as T


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _section(title: str, subtitle: str = "", body: str = "",
             note: str = "") -> str:
    head = f'<p class="rd-panel-title">{esc(title)}</p>'
    if subtitle:
        head += f'<p class="rd-panel-sub">{esc(subtitle)}</p>'
    tail = f'<p class="rd-panel-note">{esc(note)}</p>' if note else ""
    return (f'<div class="rd-panel"><div class="rd-panel-head" '
            f'style="flex-direction:column;gap:3px">{head}</div>'
            f'{body}{tail}</div>')


def _grid(*cells: str, columns: str = "1fr 1fr") -> str:
    return (f'<div style="display:grid;grid-template-columns:{columns};'
            f'gap:14px;align-items:start">' + "".join(cells) + "</div>")


# ==========================================================================
# selection strip — run / date / sector basis / news clock
# ==========================================================================
def selection_strip(state: dict) -> str:
    """The controls that were a Streamlit sidebar, now part of the console.

    Each one re-projects rather than computes: changing the run, the date, the
    sector basis or the news clock asks a different question of the same
    engine. They go out as `rd_select`, which the host turns into a new
    projection.
    """
    def select(field: str, options, selected, label: str) -> str:
        if not options:
            return (f'<label class="rd-metric-label">{esc(label)}</label>'
                    f'<p class="rd-reason">none available</p>')
        items = "".join(
            f'<option value="{esc(o)}"'
            f'{" selected" if str(o) == str(selected) else ""}>'
            f'{esc(str(o)[:28])}</option>' for o in options)
        return (f'<label class="rd-metric-label">{esc(label)}</label>'
                f'<select class="rd-select" data-rd-select="{esc(field)}">'
                f'{items}</select>')

    return _section(
        "Selection", "what this projection is of",
        _grid(
            f'<div>{select("run", state.get("runs") or [], state.get("run_id"), "run")}</div>',
            f'<div>{select("date", state.get("dates") or [], state.get("date"), "decision date")}</div>',
            f'<div>{select("sector_basis", state.get("sector_bases") or [], state.get("sector_basis"), "sector analysis basis")}</div>',
            f'<div>{select("news_clock", state.get("news_clocks") or [], state.get("news_clock"), "news clock")}</div>',
            columns="repeat(4, minmax(0,1fr))"),
        note=("Role is the console's own switcher, top left. The sector basis "
              "defaults to the selected market decision; the retrospective "
              "archive answers what was measured later and does not change "
              "the historical score."))


# ==========================================================================
# OVERVIEW
# ==========================================================================
def overview(payload: dict, state: dict) -> str:
    composite = data.composite_of(payload)
    liveness = (payload or {}).get("liveness") or {}
    history = (payload or {}).get("history") or {}

    dial = I.composite_dial(
        value=composite["value"], ci_lower=composite["ci_lower"],
        ci_upper=composite["ci_upper"], alert_level=composite["alert_level"],
        unavailable_reason=composite["reason"],
        caption=(f'historical replay · decision {payload.get("timestamp")}'
                 if payload else ""))

    why = ""
    if liveness.get("why"):
        why = ('<div class="rd-card rd-card--flat" style="margin-top:12px">'
               '<p class="rd-unavail-label">why this is not a current reading'
               '</p>' + "".join(f'<p class="rd-reason">· {esc(w)}</p>'
                                for w in liveness["why"]) + "</div>")
    if composite["mask_degraded"]:
        why += ('<div style="margin-top:10px">' + C.chip(
            "D2 mask degraded — not comparable with full-coverage readings",
            tone="warn") + "</div>")
    explanation = ((payload or {}).get("view") or {}).get("explanation")
    if explanation:
        why += f'<p class="rd-panel-note">{esc(explanation)}</p>'

    pillars = "".join(f'<div>{C.pillar_card(row)}</div>'
                      for row in data.pillar_rows(payload))

    rows = [dict(r, colour=T.pillar_colour(r["name"]))
            for r in data.contribution_rows(payload)]
    weights = [dict(r, colour=T.pillar_colour(r["name"]))
               for r in data.weight_rows(payload)]
    view = (payload or {}).get("view") or {}
    if "shapley" in view:
        breakdown = _grid(
            f'<div>{I.contribution_tracks(rows, unit="CSRS score units")}</div>',
            f'<div>{I.weight_tracks(weights)}'
            f'<p class="rd-panel-note">Weights <b>are</b> a normalised '
            f'allocation and are drawn as shares. The contributions on the '
            f'left are signed, sum to the CSRS rather than to 1, and are not '
            f'drawn that way.</p></div>',
            columns="1.35fr 1fr")
    else:
        breakdown = C.unavailable(
            "decomposition withheld at this role",
            "the retail projection does not contain a Shapley vector — the "
            "field is absent from the payload, not hidden in it "
            "(gateway.ROLE_FIELDS). Switch role, top left")

    return (selection_strip(state)
            + _grid(
                _section("Composite systemic risk", "CSRS · FR28 / FR29",
                         dial + why),
                _section("Market state history",
                         "FR41 — CSRS and official Nifty 500 returns",
                         _history_block(history)),
                columns="0.95fr 2.05fr")
            + _section("Pillars", "Hawkes · RMT · Hamilton, in PILLAR_ORDER",
                       _grid(pillars, columns="repeat(3, minmax(0,1fr))"))
            + _section("Pillar readings — how this composite was formed",
                       "signed Shapley contributions and D2 effective weights",
                       breakdown)
            + _grid(_sector_block(payload), _holdings_block(payload),
                    columns="1.5fr 1fr")
            + _section("Decision timeline",
                       "every decision date in the selected run",
                       I.timeline(history.get("rows") or [],
                                  selected_date=state.get("date"))))


def _history_block(history: dict) -> str:
    """The FR41 overlay as a compact inline chart.

    Two units, so two scales: the CSRS line is drawn against 0..1 and the
    benchmark against its own range, and the note says so. They are never put
    on one axis, which would read as a comparison of level.
    """
    rows = history.get("rows") or []
    if not rows:
        return C.unavailable("no overlay to plot",
                             "this run's overlay carries no rows")
    units = history.get("units") or {}
    series = history.get("series") or {}
    width, height = 1000, 230
    scored = [r for r in rows if isinstance(r.get("csrs"), (int, float))]
    returns = [r["benchmark_return"] for r in rows
               if isinstance(r.get("benchmark_return"), (int, float))]
    span = max(1, len(rows) - 1)
    peak = max((abs(v) for v in returns), default=0.0) or 1.0

    def x(i):
        return 8 + i * (width - 16) / span

    csrs_pts, gaps = [], 0
    for i, row in enumerate(rows):
        value = row.get("csrs")
        if isinstance(value, (int, float)):
            csrs_pts.append(f"{x(i):.1f},{height - 24 - value * (height - 44):.1f}")
        else:
            gaps += 1
            csrs_pts.append(None)
    bench_pts = []
    for i, row in enumerate(rows):
        value = row.get("benchmark_return")
        if isinstance(value, (int, float)):
            mid = (height - 24) / 2 + 12
            bench_pts.append(f"{x(i):.1f},{mid - (value / peak) * (height - 60) / 2:.1f}")

    def polyline(points, colour, width_px, opacity="1"):
        runs, current = [], []
        for point in points:
            if point is None:
                if len(current) > 1:
                    runs.append(current)
                current = []
            else:
                current.append(point)
        if len(current) > 1:
            runs.append(current)
        return "".join(
            f'<polyline points="{" ".join(run)}" fill="none" '
            f'stroke="{colour}" stroke-width="{width_px}" '
            f'opacity="{opacity}"/>' for run in runs)

    svg = (f'<svg viewBox="0 0 {width} {height}" width="100%" '
           f'height="{height}" preserveAspectRatio="none">'
           f'{polyline(bench_pts, T.TEXT_FAINT, 1, "0.55")}'
           f'{polyline(csrs_pts, T.SELECTED, 1.8)}'
           f'</svg>')

    legend = "".join([
        f'<span class="rd-legend-item"><span class="rd-swatch" '
        f'style="background:{T.SELECTED}"></span>'
        f'CSRS — {esc(units.get("csrs", "composite score, 0..1"))}</span>',
        f'<span class="rd-legend-item"><span class="rd-swatch" '
        f'style="background:{T.TEXT_FAINT}"></span>'
        f'{esc(series.get("label", "benchmark"))} — '
        f'{esc(units.get("benchmark", "close-to-close return"))}</span>',
    ])
    coverage = history.get("coverage") or {}
    rep = history.get("representativeness") or {}
    chips = [C.chip("CSRS dates", str(coverage.get("csrs_dates", "—"))),
             C.chip("matched to benchmark", str(coverage.get("matched", "—")))]
    if isinstance(rep.get("correlation"), (int, float)):
        chips.append(C.chip("descriptive correlation",
                            f"{rep['correlation']:.3f}"))
    return (svg + f'<div class="rd-legend">{legend}</div>' + C.chips(chips)
            + f'<p class="rd-panel-note">Two different units on two scales — '
              f'the lines are not comparable in level. '
              f'{gaps} session(s) with no CSRS break the line rather than '
              f'being interpolated or zero-filled. {esc(rep.get("note", ""))}'
              f'</p>')


def _sector_block(payload: dict) -> str:
    sectors = (payload or {}).get("sector_observations") or {}
    if not sectors.get("available"):
        body = C.unavailable(
            "no measured sector observations",
            str(sectors.get("reason") or "no reason recorded"),
            str(sectors.get("blocked_by") or ""))
    else:
        body = C.table(
            ["sector", "jumps", "baseline", "ratio", "flag"],
            [[s.get("sector"), s.get("count"), s.get("baseline"),
              s.get("ratio"), s.get("flag")]
             for s in (sectors.get("sectors") or [])],
            numeric_columns={1, 2, 3})
    chips = ""
    if sectors.get("analysis_mode"):
        chips = C.chips([
            C.chip("analysis mode", str(sectors["analysis_mode"]),
                   tone="warn" if sectors["analysis_mode"]
                   == "retrospective_archive" else ""),
            C.chip("cutoff", str(sectors.get("analysis_cutoff") or "—"))])
    return _section("Measured sector activity",
                    "FR14 — native intraday jump counts against baselines",
                    body + chips, note=str(sectors.get("analysis_note") or ""))


def _holdings_block(payload: dict) -> str:
    portfolio = (payload or {}).get("portfolio")
    flow = (payload or {}).get("flow") or {}
    if portfolio:
        holdings = C.table(["field", "value"],
                           [[k, v] for k, v in sorted(portfolio.items())],
                           numeric_columns={1})
    else:
        holdings = C.unavailable(
            "no holdings supplied",
            "no saved portfolio is active for this role. An empty table here "
            "means nothing was supplied, not that exposure is nil")
    if flow.get("available"):
        flow_body = C.table(
            ["measure", str(flow.get("units", "value"))],
            [["FII net", flow.get("fiiNet")], ["DII net", flow.get("diiNet")],
             ["residual flow share", flow.get("residualFlowShare")]],
            numeric_columns={1})
    else:
        flow_body = C.unavailable("no flow print ingested",
                                  str(flow.get("reason") or ""))
    return (_section("Holdings", "portfolio coverage at this decision", holdings)
            + _section("Market flow", "FR45 / FR51 — market aggregate", flow_body))


# ==========================================================================
# EARLY WARNING
# ==========================================================================
def warning(forecast: dict) -> str:
    if not forecast.get("available"):
        return _section("Forecast & early warning", "no saved state",
                        C.unavailable("no prediction state",
                                      str(forecast.get("note") or ""),
                                      str(forecast.get("error") or "")))
    state = forecast["state"]
    predicted, warn = state["predicted"], state["warning"]
    validation = state.get("validation") or {}
    staleness = forecast.get("staleness") or {}

    level = str(warn.get("level"))
    colour = {"no_warning": T.ALERT["green"], "watch": T.ALERT["amber"],
              "warning": T.ALERT["red"], "alert": T.ALERT["red"]}.get(
                  level, T.TEXT_DIM)
    stale = ""
    if staleness.get("stale"):
        stale = ('<div style="margin-top:10px">'
                 + C.chip("STALE", tone="warn") + "</div>"
                 + f'<p class="rd-reason">{esc(staleness.get("detail"))}</p>')

    def pct(x):
        return "—" if not isinstance(x, (int, float)) else f"{x:.2%}"

    head = _grid(
        _section("Warning state", "a policy decision, not a measurement",
                 f'<p class="rd-metric-value" style="color:{colour};'
                 f'font-size:30px">{esc(forecast.get("warning_label"))}</p>'
                 f'<p class="rd-reason" style="margin-top:8px">'
                 f'{esc(warn.get("reason"))}</p>' + stale),
        _section("The forecast", "one probability, one model, point-in-time",
                 _grid(
                     f'<div>{C.metric("predicted probability", pct(predicted.get("probability")), "of the loss event", colour=T.SELECTED)}</div>',
                     f'<div>{C.metric("warning threshold", pct(warn.get("threshold")), "calibrated", colour=T.ACCENT)}</div>',
                     f'<div>{C.metric("horizon", str(predicted.get("horizon_sessions")), "sessions")}</div>',
                     columns="repeat(3, minmax(0,1fr))")
                 + C.chips([C.chip("decision date", str(state.get("as_of"))),
                            C.chip("model", str(predicted.get("model")))])),
        columns="1fr 1.25fr")

    banner = (f'<div class="rd-panel" style="border-color:#56222C;'
              f'background:#140A0E"><p class="rd-panel-title" '
              f'style="color:{T.ALERT["red"]}">'
              f'{esc(str(validation.get("status", "unvalidated")).upper())}</p>'
              f'<p class="rd-reason">{esc(validation.get("note"))}</p></div>')

    features = (state.get("measured") or {}).get("pillar_features") or {}
    measured = _section(
        "Measured — the three pillars at this close",
        "observations and arithmetic, not a forecast",
        C.table(["pillar", "indicator", "value"],
                [[v.get("pillar"), k,
                  None if v.get("value") is None else f'{v["value"]:.4f}']
                 for k, v in features.items()], numeric_columns={2}),
        note=str((state.get("measured") or {}).get("note") or ""))

    history = state.get("history") or {}
    metrics = history.get("metrics") or {}
    stats = history.get("alarm_stats") or {}

    def num(x, places=4):
        return "—" if not isinstance(x, (int, float)) else f"{x:.{places}f}"

    realised = _section(
        "Realised history", "retrospective replay, not foresight",
        _grid(
            f'<div>{C.metric("Brier", num(metrics.get("brier")), "lower is better")}</div>',
            f'<div>{C.metric("AUC", num(metrics.get("auc"), 3), "0.5 is chance")}</div>',
            f'<div>{C.metric("base rate", pct(metrics.get("base_rate")), "of matured labels")}</div>',
            f'<div>{C.metric("false episodes/yr", num(stats.get("false_episodes_per_year"), 2), "against budget")}</div>',
            columns="repeat(4, minmax(0,1fr))"),
        note=str(history.get("note") or ""))

    reliability = _section(
        "Calibration — did days it called p turn out p?",
        "the uncertainty this model supports; it yields no interval",
        C.table(["predicted range", "sessions", "mean predicted",
                 "realised rate"],
                [[f'{r["lower"]:.0%}–{r["upper"]:.0%}', r.get("count"),
                  None if r.get("mean_predicted") is None else num(r["mean_predicted"]),
                  None if r.get("realised_rate") is None else num(r["realised_rate"])]
                 for r in (history.get("reliability") or []) if r.get("count")],
                numeric_columns={1, 2, 3}))

    episodes = history.get("episodes") or []
    alarms = _section(
        "Alarm episodes", "contiguous runs of sessions in alarm",
        C.table(["start", "end"], [[e.get("start"), e.get("end")] for e in episodes])
        if episodes else C.unavailable(
            "no alarm episode recorded",
            "the retained history contains no session in alarm — an empty "
            "result, not a missing one"))

    return (head + banner + measured + realised
            + _grid(reliability, alarms, columns="1.1fr 1fr"))


# ==========================================================================
# EVALUATION
# ==========================================================================
def evaluation(surface: dict) -> str:
    if not surface.get("permitted"):
        return _section(
            "Evaluation", "institutional or regulator",
            C.unavailable(
                "not available at this role",
                "an ablation table reports what the instrument can and cannot "
                "do, not a current risk level. The backend withholds it from "
                "retail; switch role, top left"))
    design = surface.get("design") or {}
    if not design.get("committed"):
        return _section(
            "No committed design", "D5(d) precondition",
            C.unavailable("no pre-registered design is committed",
                          "so NO AUC can be computed at all",
                          str(surface.get("note") or ""))
            + f'<pre class="rd-code">{esc(surface.get("commit_hint"))}</pre>')
    if not design.get("intact", True):
        return _section("Design not intact", "committed then edited",
                        C.unavailable(
                            "the committed design no longer matches its hash",
                            "it was edited after it was committed, so no "
                            "result produced under it is reportable"))

    reports = surface.get("reports") or []
    if not reports:
        return _section("No saved evaluation run", "the design is committed",
                        C.unavailable("no run has been saved yet",
                                      f"this reads every artefact in "
                                      f"{surface.get('reports_dir')}"))
    report = reports[0]
    blocks = [_section(
        "Pre-registered design", "committed once, by a person",
        C.chips([C.chip("design hash", str(design.get("hash", ""))[:16] + "…"),
                 C.chip("Table-B scope", str(design.get("table_b_scope"))),
                 C.chip("configurations", str(design.get("configurations"))),
                 C.chip("intact", "yes" if design.get("intact") else "no",
                        tone="ok" if design.get("intact") else "bad")]))]

    blocks.append(_grid(
        f'<div>{C.metric("measured cells", str(report.get("measured")), "folds with an AUC", colour=T.SELECTED)}</div>',
        f'<div>{C.metric("unavailable cells", str(report.get("unavailable")), "each retained with a reason", colour=T.ALERT["amber"])}</div>',
        f'<div>{C.metric("not publishable", str(report.get("unpublishable")), "withheld from metrics")}</div>',
        columns="repeat(3, minmax(0,1fr))"))

    if report.get("comparability"):
        blocks.append(
            f'<div class="rd-panel" style="border-color:#5A4420;'
            f'background:#1E1708"><p class="rd-panel-title" '
            f'style="color:{T.ALERT["amber"]}">NOT A SINGLE RANKING</p>'
            f'<p class="rd-reason">{esc(report["comparability"])}</p></div>')

    import math
    configurations = report.get("configurations") or []
    for table_name in sorted({c["table"] for c in configurations}):
        rows = [c for c in configurations if c["table"] == table_name]
        body = []
        for c in rows:
            measured_folds = c.get("measured_folds") or 0
            auc = c.get("mean_auc")
            body.append([
                c.get("subset"), c.get("mode"), c.get("xi_mode"),
                f'{measured_folds}/{c.get("declared_folds")}',
                (round(auc, 4) if measured_folds and isinstance(auc, float)
                 and not math.isnan(auc) else None),
                (", ".join(f"{k} ×{v}" for k, v
                           in (c.get("unavailable_folds") or {}).items()) or None),
            ])
        blocks.append(_section(
            f"Table {table_name}", f'{rows[0].get("declared_folds")} folds declared',
            C.table(["subset", "mode", "xi", "folds", "mean AUC", "absences"],
                    body, numeric_columns={4})))

    absences = report.get("absences") or {}
    blocks.append(_section(
        "Unavailable cells", "each is a result, not a gap",
        C.table(["reason", "folds"],
                [[k, v] for k, v in sorted(absences.items(), key=lambda kv: -kv[1])],
                numeric_columns={1}) if absences
        else '<p class="rd-reason">Every declared fold was measured.</p>',
        note=("Each is retained in the artefact with its reason rather than "
              "dropped, which is what makes the ablation falsifiable "
              "(FR35/FR36).")))
    return "".join(blocks)


# ==========================================================================
# HEALTH
# ==========================================================================
def health(surface: dict, acquisition: dict, market_jobs: dict) -> str:
    by_health = surface.get("by_health") or {}
    status = surface.get("status", "unknown")
    blocks = [_section(
        "Installation health", f'as of {surface.get("at", "—")}',
        C.chips([
            C.chip("worst check", str(status),
                   tone="bad" if status == "failing" else "warn"),
            C.chip("ok", str(len(by_health.get("ok") or [])), tone="ok"),
            C.chip("stale", str(len(by_health.get("stale") or [])), tone="warn"),
            C.chip("failing", str(len(by_health.get("failing") or [])),
                   tone="bad"),
        ]), note=str(surface.get("note") or ""))]

    schedule = surface.get("schedule") or {}
    if schedule:
        last = schedule.get("last_run") or {}
        blocks.append(_section(
            "Daily schedule",
            "registered, executed and acquired are three different facts",
            C.chips([
                C.chip("registered", str(schedule.get("task_name")),
                       tone="ok" if schedule.get("registered") else "bad"),
                C.chip("runs at", f'{schedule.get("at_ist")} IST weekdays'),
                C.chip("expected session", str(schedule.get("expected_session"))),
            ]) + C.table(["step", "result"],
                         [[s.get("step"), "ok" if s.get("ok") else "FAILED"]
                          for s in last.get("steps") or []]),
            note=str(schedule.get("note") or "")))

    order = {"failing": 0, "never_succeeded": 1, "never_run": 2,
             "degraded": 3, "stale": 4, "ok": 5}
    checks = sorted(surface.get("checks") or [],
                    key=lambda c: (order.get(c.get("health"), 9), c.get("name", "")))
    blocks.append(_section(
        "Every check", "a check with no data is never ok",
        C.table(["check", "kind", "health", "detail"],
                [[c.get("name"), c.get("kind"), c.get("health"), c.get("detail")]
                 for c in checks])))

    sources = acquisition.get("sources") or []
    failing = sum(1 for s in sources if s.get("consecutive_failures"))
    worker = acquisition.get("worker") or {}
    state = str(worker.get("state") or "unknown")
    owner = str(acquisition.get("owner") or "unknown")
    # A dead fetcher is the single most misleading thing this screen could
    # under-report: the store still answers every read, so a full news
    # channel that is receiving nothing looks identical to a healthy one on
    # every other surface. The state therefore carries a tone, and the
    # worker's own detail and note are rendered rather than summarised into
    # a one-word chip.
    #
    # OWNER AND STATE ARE TWO DIFFERENT FACTS and they can disagree. `owner`
    # is what THIS dashboard did about starting a worker; `state` is the
    # store's heartbeat, which any process may have written -- a supervisor
    # started by the other launcher, or one run by hand. So a heartbeat
    # reading `running` beside an owner of `exited` is not a contradiction to
    # resolve in favour of the cheerful one: it means something else is
    # fetching, or something else fetched recently and stopped without
    # saying so. Saying that is the whole value of the panel.
    stopped = state in ("failed", "stopped", "dead", "unknown")
    ownerless = owner in ("exited", "failed", "stopped", "disabled")
    worker_detail = ""
    if stopped or ownerless:
        beat = (f'last heartbeat {worker.get("last_beat_at")}'
                f' ({worker.get("age_minutes")} minutes ago)'
                if worker.get("last_beat_at") else "")
        if stopped:
            worker_detail = C.unavailable(
                f"nothing is fetching — the acquisition worker is {state}",
                str(worker.get("detail") or ""), beat,
                str(worker.get("note") or ""),
                "every story below was acquired before it stopped; the store "
                "is readable and is not being added to")
        else:
            # The heartbeat is alive but it is not this dashboard's worker.
            worker_detail = C.unavailable(
                f"this dashboard has no acquisition worker — it is {owner}",
                str(acquisition.get("reason") or ""),
                (f"the store's heartbeat reads {state!r}, so a process this "
                 f"dashboard did not start has been fetching"), beat,
                "that process is not supervised from here, so nothing will "
                "restart it when it stops")
    blocks.append(_section(
        "News acquisition", "liveness only — not news content",
        f'<p class="rd-reason">{esc(acquisition.get("reason"))}</p>'
        + C.chips([C.chip("owner", str(acquisition.get("owner"))),
                   C.chip("state", state,
                          tone="bad" if stopped else "ok"),
                   C.chip("activity", str(worker.get("activity") or "—"))])
        + worker_detail
        + f'<p class="rd-unavail-label" style="margin-top:14px">per-source '
          f'outcomes — {failing} of {len(sources)} currently failing</p>'
        + C.table(["source", "status", "consecutive failures", "last success"],
                  [[s.get("source"), s.get("status"),
                    s.get("consecutive_failures"), s.get("last_success")]
                   for s in sources], numeric_columns={2})))

    if market_jobs.get("ran"):
        blocks.append(_section(
            "Market jobs", "C15 — reads a status file, runs nothing",
            C.chips([C.chip("last run", str(market_jobs.get("generated"))),
                     C.chip("session", str(market_jobs.get("session")))])
            + C.table(["step", "result"],
                      [[s.get("step"), "ok" if s.get("ok") else "FAILED"]
                       for s in market_jobs.get("steps") or []]),
            note=str(market_jobs.get("note") or "")))
    else:
        blocks.append(_section(
            "Market jobs", "C15",
            C.unavailable("the market jobs have not run",
                          str(market_jobs.get("note") or ""))))
    return "".join(blocks)

# ==========================================================================
# CURRENT SESSION — what SERAPH knows about the market now
# ==========================================================================
def current(session: dict, composite: dict, forecast: dict,
            liveness: dict, state: dict) -> str:
    """The default view: the latest completed session, not a 2020 replay.

    Three claims, kept apart because they are three different things:
    the **pillar readings** the daily job computed, the **forecast** and its
    calibrated warning, and the **composite**, which does not exist for a
    current session and says why rather than being fused here.
    """
    blocks = [_section(
        "Latest completed market session",
        "what SERAPH knows about the market now",
        C.chips([
            C.chip("inputs through", str(session.get("input_end") or "—"),
                   tone="ok" if session.get("available") else "warn"),
            C.chip("computed", str(session.get("computed_at") or "—")),
            C.chip("market", str((liveness or {}).get("market_state") or "—")),
            C.chip("next open", str((liveness or {}).get("next_open") or "—")),
        ]),
        note=("These are the readings the daily job produced for the last "
              "session it covered. They are current in the sense that nothing "
              "newer has been computed — not in the sense that the market is "
              "open right now."))]

    # --- the composite ----------------------------------------------------
    # A score produced by the official engine over this session's own
    # vintages. It is real, and it is NOT a current market reading: the
    # publication gate withheld it, and the refusal is shown beside it rather
    # than left to be inferred.
    if composite.get("available"):
        dial = I.composite_dial(
            value=composite["value"], ci_lower=composite.get("ci_lower"),
            ci_upper=composite.get("ci_upper"),
            alert_level=composite.get("alert_level"),
            caption=f'session {esc(composite.get("as_of"))}')
        state = str(composite.get("publication_state") or "unknown")
        dial += (
            f'<div style="margin-top:10px">'
            f'{C.chip("publication", state, tone="ok" if composite.get("publishable") else "warn")}'
            f'{C.chip("decision", str(composite.get("decision_id") or "")[:22])}'
            f'</div>'
            f'<p class="rd-panel-note">{esc(composite.get("note"))}</p>')
        if not composite.get("publishable"):
            dial += C.unavailable(
                "not publishable as a current reading",
                "this is a genuine composite for the session named above, "
                "computed by the same engine the live loop uses. It is "
                "withheld from being called current because it is a replay "
                "of a completed session, not a live market observation")
        for warning in composite.get("warnings") or []:
            dial += f'<p class="rd-panel-note">· {esc(warning)}</p>'
    else:
        dial = I.composite_dial(value=None,
                                unavailable_reason=composite["reason"],
                                caption="no composite for this session")
    scored = ", ".join(composite.get("scored") or []) or "none"
    absent = "; ".join(f"{n} ({why})" for n, why in composite.get("absent") or [])
    blocks.append(_grid(
        _section("Composite systemic risk", "CSRS · FR28 / FR29", dial),
        _section("Pillar readings for this session",
                 "computed by the daily job, not fused here",
                 _pillar_rows(session)
                 + f'<p class="rd-panel-note">Scored: <b>{esc(scored)}</b>. '
                   f'Absent: {esc(absent) or "none"}. A pillar that declared '
                   f'an absence is not a zero and is not substituted.</p>'),
        columns="0.95fr 2.05fr"))

    # --- the forecast, which IS current -----------------------------------
    if forecast.get("available"):
        fstate = forecast["state"]
        predicted, warn = fstate["predicted"], fstate["warning"]
        validation = fstate.get("validation") or {}
        level = str(warn.get("level"))
        colour = {"no_warning": T.ALERT["green"], "watch": T.ALERT["amber"],
                  "warning": T.ALERT["red"], "alert": T.ALERT["red"]}.get(
                      level, T.TEXT_DIM)

        def pct(x):
            return "—" if not isinstance(x, (int, float)) else f"{x:.2%}"

        stale = (forecast.get("staleness") or {})
        blocks.append(_section(
            "Current forecast and early warning",
            "one probability, one model, point-in-time",
            _grid(
                f'<div><p class="rd-metric-value" style="color:{colour};'
                f'font-size:26px">{esc(forecast.get("warning_label"))}</p>'
                f'<p class="rd-reason">{esc(warn.get("reason"))}</p></div>',
                f'<div>{C.metric("predicted probability", pct(predicted.get("probability")), "of the loss event", colour=T.SELECTED)}</div>',
                f'<div>{C.metric("warning threshold", pct(warn.get("threshold")), "calibrated", colour=T.ACCENT)}</div>',
                f'<div>{C.metric("horizon", str(predicted.get("horizon_sessions")), "sessions")}</div>',
                columns="1.4fr 1fr 1fr 0.8fr")
            + C.chips([
                C.chip("forecast as of", str(fstate.get("as_of") or "—"),
                       tone="warn" if stale.get("stale") else "ok"),
                C.chip("issued", str((fstate.get("issuance") or {}).get("issued_at") or "—")),
            ])
            + (f'<p class="rd-panel-note">{esc(stale.get("detail"))}</p>'
               if stale.get("detail") else "")
            + f'<div class="rd-panel" style="border-color:#56222C;'
              f'background:#140A0E;margin-top:12px">'
              f'<p class="rd-panel-title" style="color:{T.ALERT["red"]}">'
              f'{esc(str(validation.get("status", "unvalidated")).upper())}</p>'
              f'<p class="rd-reason">{esc(validation.get("note"))}</p></div>'))
    else:
        blocks.append(_section(
            "Current forecast and early warning", "no saved state",
            C.unavailable("no prediction state",
                          str(forecast.get("note") or ""))))

    # --- why there is no live stream --------------------------------------
    why = (liveness or {}).get("why") or []
    if why:
        blocks.append(_section(
            "Why this is not a streaming live reading",
            "the publication gate's own reasons",
            "".join(f'<p class="rd-reason">· {esc(w)}</p>' for w in why),
            note=("A completed session is not the same as a live stream. The "
                  "readings above are the most recent SERAPH has computed; "
                  "they are not a statement about the market at this instant.")))
    return "".join(blocks)


def _pillar_rows(session: dict) -> str:
    rows = []
    for p in session.get("pillars") or []:
        colour = T.pillar_colour(p["name"])
        if p["value"] is not None:
            value = (f'<span class="rd-num" style="color:{colour};'
                     f'font-size:17px">{p["value"]:.4f}</span>')
            note = esc(p.get("origin") or "")
        else:
            value = f'<span style="color:{T.TEXT_FAINT}">—</span>'
            note = esc((p.get("absence") or "not emitted")
                       + " · " + (p.get("reason") or "no reason recorded"))
        rows.append(
            f'<div class="rd-card rd-card--flat" style="margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:baseline">'
            f'<span style="color:{colour};font-weight:600;font-size:11px;'
            f'letter-spacing:.12em;text-transform:uppercase">'
            f'{esc(p["name"])}</span>{value}</div>'
            f'<p class="rd-panel-note">{note}</p>'
            f'<p class="rd-panel-note rd-num">inputs through '
            f'{esc(p.get("input_end") or "—")}</p></div>')
    return "".join(rows)
