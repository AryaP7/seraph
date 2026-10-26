# C12 — Redesigned console: FORECAST & EARLY WARNING (C9/C10 -> C12).
"""SERAPH's stated purpose, on its own screen.

**Three headings, because they are three different claims**, and running
them together is how a research instrument starts sounding like an oracle:

* *Measured* — the pillar feature values at the decision close. Observations
  and arithmetic.
* *Predicted* — one probability, from one model, point-in-time.
* *Warning* — whether that probability crossed a threshold calibrated on past
  out-of-sample scores under a declared false-alarm budget. A policy, not a
  proof.

The realised history is labelled retrospective replay, and the reliability
chart is the uncertainty statement this model actually supports: the logistic
challenger yields no interval, so inventing one would be worse than showing
whether the days it called 5% turned out 5%. This installation's own
calibration shows it over-predicting, which is the reason to display it
rather than a reason to hide it.

Reads; never fits. `scripts/run_prediction.py` runs the engine and persists
the state; `run_market_jobs.py` refreshes it daily. A page render that refit
seventy-three models would make every refresh a cliff.
"""
from __future__ import annotations

import streamlit as st

from . import charts, components as C, data, instruments as I, tokens as T

#: Warning levels this screen knows how to draw. A level outside this table is
#: shown verbatim rather than mapped to a colour it does not have a meaning
#: for — a mislabelled warning is worse than an unstyled one.
_LEVEL_TONE = {"no_warning": "ok", "watch": "warn", "warning": "bad",
               "alert": "bad", "elevated": "warn"}


def _pct(x, places: int = 2) -> str:
    return "—" if not isinstance(x, (int, float)) or isinstance(x, bool) \
        else f"{float(x):.{places}%}"


def _num(x, places: int = 4) -> str:
    return "—" if not isinstance(x, (int, float)) or isinstance(x, bool) \
        else f"{float(x):.{places}f}"


def render(*, role: str) -> None:
    surface = data.forecast_state()

    C.html_block(
        '<div class="rd-topbar"><div>'
        '<p class="rd-eyebrow">SERAPH · redesigned console</p>'
        '<h1>Forecast &amp; early warning</h1>'
        '<p class="rd-panel-sub" style="margin-top:4px">'
        'measured · predicted · warning — three different claims</p>'
        '</div></div>')

    if not surface.get("available"):
        with C.panel("No forecast", "the engine has produced no saved state"):
            C.html_block(C.unavailable(
                "no prediction state",
                str(surface.get("note") or "no reason recorded"),
                str(surface.get("error") or "")))
            st.code(surface.get("command", "python scripts/run_prediction.py"),
                    language="bash")
        return

    state = surface["state"]
    predicted, warning = state["predicted"], state["warning"]
    validation = state.get("validation") or {}
    staleness = surface.get("staleness") or {}

    _headline(surface, state, warning, staleness)
    _validation_banner(validation)
    _what_is_predicted(predicted)
    _measured(state)
    _policy(warning)
    _realised(state)
    _series(state)

    if role == "retail":
        C.html_block(
            '<p class="rd-panel-note">This screen is shown to every role: it '
            'reports what the instrument can and cannot do, which is not '
            'privileged market content. The per-pillar decomposition of a '
            '<i>decision</i> is role-scoped, and lives on the Overview.</p>')


# --------------------------------------------------------------------------
def _headline(surface, state, warning, staleness) -> None:
    left, right = st.columns([1, 1.25], gap="medium")

    with left:
        with C.panel("Warning state", "a policy decision, not a measurement"):
            level = warning.get("level")
            tone = _LEVEL_TONE.get(str(level), "")
            label = surface.get("warning_label", str(level).upper())
            colour = {"ok": T.ALERT["green"], "warn": T.ALERT["amber"],
                      "bad": T.ALERT["red"]}.get(tone, T.TEXT_DIM)
            C.html_block(
                f'<p class="rd-metric-value" style="color:{colour};'
                f'font-size:30px">{C.esc(label)}</p>'
                f'<p class="rd-reason" style="margin-top:8px">'
                f'{C.esc(warning.get("reason", ""))}</p>')
            if not surface.get("level_known"):
                C.html_block(
                    '<p class="rd-panel-note">This level is not one the '
                    'console knows how to draw, so it is shown verbatim '
                    'rather than mapped to a colour.</p>')
            if staleness.get("stale"):
                C.html_block(
                    f'<div style="margin-top:12px">'
                    f'{C.chip("STALE", tone="warn")}</div>'
                    f'<p class="rd-reason">{C.esc(staleness.get("detail", ""))}'
                    f'</p>'
                    '<p class="rd-panel-note">The forecast below is still the '
                    'last valid one and is not discarded — but it is not '
                    'current, and a stale "no warning" read as current is '
                    'worse than no reading.</p>')
            elif staleness.get("days_behind"):
                C.html_block(f'<p class="rd-panel-note">Within the refresh '
                             f'allowance: {C.esc(staleness.get("detail", ""))}</p>')

    with right:
        with C.panel("The forecast", "one probability, one model, point-in-time"):
            a, b, c = st.columns(3)
            probability = (state.get("predicted") or {}).get("probability")
            threshold = warning.get("threshold")
            with a:
                C.html_block(C.metric(
                    "predicted probability", _pct(probability),
                    "of the loss event below",
                    colour=T.SELECTED,
                    available=isinstance(probability, (int, float))))
            with b:
                C.html_block(C.metric(
                    "warning threshold", _pct(threshold), "calibrated",
                    colour=T.ACCENT,
                    available=isinstance(threshold, (int, float))))
            with c:
                horizon = (state.get("predicted") or {}).get("horizon_sessions")
                C.html_block(C.metric("horizon", str(horizon), "sessions",
                                      available=horizon is not None))

            issuance = state.get("issuance") or {}
            snapshot = state.get("snapshot") or {}
            bits = [C.chip("decision date", str(state.get("as_of") or "—"))]
            if issuance.get("forecast_id"):
                bits.append(C.chip("forecast ledger",
                                   str(issuance["forecast_id"])[:16] + "…"))
            if issuance.get("mode"):
                bits.append(C.chip("mode", str(issuance["mode"])))
            if issuance.get("matures_after"):
                bits.append(C.chip("matures after",
                                   str(issuance["matures_after"])))
            C.html_block(C.chips(bits))
            if snapshot:
                C.html_block(
                    f'<p class="rd-panel-note">Computed '
                    f'{C.esc(surface.get("generated_at"))} · snapshot '
                    f'<span class="rd-num">'
                    f'{C.esc(str(snapshot.get("sha256", ""))[:12])}</span> '
                    f'({C.esc(snapshot.get("rows"))} sessions, '
                    f'{C.esc(snapshot.get("first_session"))} to '
                    f'{C.esc(snapshot.get("last_session"))})</p>')


def _validation_banner(validation: dict) -> None:
    """Before any number is interpreted, not after."""
    status = str(validation.get("status", "unvalidated")).upper()
    C.html_block(
        f'<div class="rd-panel" style="border-color:#56222C;'
        f'background:#140A0E;margin-top:2px">'
        f'<p class="rd-panel-title" style="color:{T.ALERT["red"]}">'
        f'{C.esc(status)}</p>'
        f'<p class="rd-reason">{C.esc(validation.get("note", ""))}</p></div>')


def _what_is_predicted(predicted: dict) -> None:
    with C.panel("What is predicted", "the event, stated exactly"):
        C.html_block(
            f'<p style="font-size:14px;line-height:1.6;margin:0 0 12px">'
            f'{C.esc(predicted.get("definition", "no definition recorded"))}</p>')
        features = predicted.get("features") or []
        C.html_block(
            f'<p class="rd-panel-note">Model: '
            f'{C.esc(predicted.get("model"))} · fit '
            f'{C.esc(predicted.get("fit_status"))} on '
            f'<span class="rd-num">{C.esc(predicted.get("training_count"))}</span> '
            f'rows, using labels matured through '
            f'{C.esc(predicted.get("train_end_date"))} (fitted '
            f'{C.esc(predicted.get("fitted_at_date"))}, '
            f'{C.esc(predicted.get("refits"))} refits over the series). '
            f'<b>{C.esc(predicted.get("observed_features"))} of '
            f'{len(features)}</b> features were observed at this date.</p>')


def _measured(state: dict) -> None:
    with C.panel("Measured — the three pillars at this close",
                 "observations and arithmetic, not a forecast"):
        features = (state.get("measured") or {}).get("pillar_features") or {}
        rows = [[item.get("pillar"), name,
                 None if item.get("value") is None else _num(item.get("value"))]
                for name, item in features.items()]
        if rows:
            C.html_block(C.table(["pillar", "indicator", "value"], rows,
                                 numeric_columns={2}))
            feature_rows = [dict(name=item.get("pillar"), value=item.get("value"))
                            for item in features.values()]
            chart, note = charts.pillar_detail(
                feature_rows, value_key="value",
                title="feature value at this close", height=160)
            if chart is not None:
                st.altair_chart(chart, use_container_width=True)
                C.html_block(f'<p class="rd-panel-note">{C.esc(note)}</p>')
        else:
            C.html_block(C.unavailable(
                "no pillar features recorded",
                "the saved state carries no measured feature values for this "
                "close"))
        market_return = (state.get("measured") or {}).get("market_return")
        bits = []
        if isinstance(market_return, (int, float)):
            bits.append(C.chip("market return at close", _pct(market_return, 3)))
        if (state.get("measured") or {}).get("sessions"):
            bits.append(C.chip("sessions in corpus",
                               str(state["measured"]["sessions"])))
        if bits:
            C.html_block(C.chips(bits))
        C.html_block(f'<p class="rd-panel-note">'
                     f'{C.esc((state.get("measured") or {}).get("note", ""))}</p>')


def _policy(warning: dict) -> None:
    with C.panel("Warning policy", "how the threshold is chosen"):
        budget = warning.get("budget") or {}
        C.html_block(
            f'<p class="rd-reason">The threshold is recalibrated from past '
            f'out-of-sample scores and matured outcomes only, to hold at most '
            f'<b>{C.esc(budget.get("false_episodes_per_year"))}</b> false '
            f'episodes per year and keep at most '
            f'<b>{_pct(budget.get("max_alarm_fraction"), 0)}</b> of sessions '
            f'in alarm, over a {C.esc(budget.get("lookback_sessions"))}-session '
            f'lookback needing {C.esc(budget.get("min_calibration"))} matured '
            f'outcomes. {C.esc(warning.get("calibrations"))} recalibrations so '
            f'far.</p>'
            f'<p class="rd-panel-note">{C.esc(warning.get("note", ""))}</p>')
        if warning.get("threshold_is_abstention"):
            C.html_block(C.unavailable(
                "the calibration abstained",
                "no finite threshold met the declared budget on recent "
                "history, so no warning can be issued — rather than one being "
                "issued on a threshold that does not meet the policy"))


def _realised(state: dict) -> None:
    history = state.get("history") or {}
    metrics = history.get("metrics") or {}
    stats = history.get("alarm_stats") or {}

    with C.panel("Realised history", "retrospective replay, not foresight"):
        a, b, c, d = st.columns(4)
        for column, (label, value, unit) in zip(
                (a, b, c, d),
                (("Brier", _num(metrics.get("brier")), "lower is better"),
                 ("AUC", _num(metrics.get("auc"), 3), "0.5 is chance"),
                 ("base rate", _pct(metrics.get("base_rate")), "of matured labels"),
                 ("false episodes/yr",
                  _num(stats.get("false_episodes_per_year"), 2),
                  f"budget {(state.get('warning') or {}).get('budget', {}).get('false_episodes_per_year', '—')}"))):
            with column:
                C.html_block(C.metric(label, value, unit,
                                      available=value != "—"))
        C.html_block(
            f'<p class="rd-panel-note">'
            f'<span class="rd-num">{C.esc(metrics.get("n"))}</span> forecasts '
            f'with matured outcomes, {C.esc(metrics.get("positives"))} of them '
            f'positive. Alarms on {_pct(stats.get("alarm_fraction"))} of '
            f'assessable sessions across {C.esc(stats.get("episodes"))} '
            f'episodes. {C.esc(history.get("note", ""))}</p>')

    left, right = st.columns([1.1, 1], gap="medium")
    with left:
        with C.panel("Calibration", "did days it called p turn out p?"):
            C.html_block(
                '<p class="rd-panel-note">The uncertainty this model '
                'supports. It yields no interval, so this is the honest '
                'substitute: predicted against realised frequency, on matured '
                'labels only.</p>')
            chart, note = charts.reliability(history.get("reliability") or [])
            if chart is None:
                C.html_block(C.unavailable("no calibration to show", note))
            else:
                st.altair_chart(chart, use_container_width=True)
                C.html_block(f'<p class="rd-panel-note">{C.esc(note)}</p>')
            rows = [[f"{r['lower']:.0%}–{r['upper']:.0%}", r.get("count"),
                     None if r.get("mean_predicted") is None
                     else _num(r["mean_predicted"]),
                     None if r.get("realised_rate") is None
                     else _num(r["realised_rate"])]
                    for r in (history.get("reliability") or []) if r.get("count")]
            if rows:
                C.html_block(C.table(
                    ["predicted range", "sessions", "mean predicted",
                     "realised rate"], rows, numeric_columns={1, 2, 3}))

    with right:
        with C.panel("Alarm episodes", "contiguous runs of sessions in alarm"):
            episodes = history.get("episodes") or []
            if episodes:
                C.html_block(C.table(
                    ["start", "end"],
                    [[e.get("start"), e.get("end")] for e in episodes]))
                C.html_block(
                    f'<p class="rd-panel-note">{len(episodes)} episode(s) in '
                    f'the retained window. An episode is a run of consecutive '
                    f'alarm sessions, not one alarm per row.</p>')
            else:
                C.html_block(C.unavailable(
                    "no alarm episode recorded",
                    "the retained history contains no session in alarm. That "
                    "is an empty result, not a missing one"))


def _series(state: dict) -> None:
    with C.panel("Forecast against its warning threshold",
                 "the scored series, as issued"):
        series = state.get("series") or []
        chart, note = charts.forecast_against_threshold(series)
        if chart is None:
            C.html_block(C.unavailable("no scored series", note))
            return
        st.altair_chart(chart, use_container_width=True)
        alarms = sum(1 for r in series if r.get("alarm"))
        C.html_block(
            f'<p class="rd-panel-note">The last '
            f'<span class="rd-num">{len(series)}</span> sessions; '
            f'<span class="rd-num">{alarms}</span> of them were in alarm. '
            f'{C.esc(note)}</p>')
