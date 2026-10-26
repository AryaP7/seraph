# C12 — Redesigned console: charts (FR41).
"""Altair specs for the redesigned screens. Presentation only.

**Two series, two units, two axes.** `_history_with_benchmark` returns a CSRS
(a 0..1 composite score) and a benchmark return (a close-to-close return) and
says so in its own `units` dict. Putting them on one axis would be a category
error that reads as a comparison, so every chart here that shows both resolves
the y scale independently and labels each axis with its unit.

**Gaps stay gaps.** A session with no CSRS is `None` in the overlay rows. It
is passed through as a null so the line breaks, and it is never dropped (which
would silently close the gap by joining its neighbours) and never zero-filled.
"""
from __future__ import annotations

import altair as alt
import pandas as pd

from . import tokens as T

#: Altair config shared by every chart here, so one theme change moves all of
#: them and none of it leaks into a chart Classic draws.
_AXIS = dict(labelColor=T.TEXT_FAINT, titleColor=T.TEXT_DIM, tickColor=T.BORDER,
             domainColor=T.BORDER, gridColor="#17202E", labelFontSize=10,
             titleFontSize=10.5, titleFontWeight="normal", labelFont=T.MONO)


def _style(chart: alt.Chart, height: int) -> alt.Chart:
    return (chart
            .properties(height=height, background="transparent")
            .configure_view(stroke=None)
            .configure_axis(**_AXIS)
            .configure_legend(labelColor=T.TEXT_DIM, titleColor=T.TEXT_FAINT,
                              labelFontSize=10.5, titleFontSize=10,
                              symbolType="stroke", orient="top",
                              direction="horizontal", offset=6))


def market_state_history(history: dict, *, selected_date: str | None = None,
                         height: int = 268):
    """The FR41 overlay: CSRS against official Nifty 500 returns, two axes.

    Returns `(chart, note)` or `(None, reason)` when there is nothing to draw.
    `note` carries the series label, its source and both units so the chart is
    never read without them.
    """
    rows = (history or {}).get("rows") or []
    if not rows:
        return None, ("this run's overlay carries no rows, so there is no "
                      "history to plot")

    frame = pd.DataFrame([
        dict(date=r.get("date"),
             csrs=r.get("csrs"),
             benchmark_return=r.get("benchmark_return"))
        for r in rows])
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    if frame.empty:
        return None, "no row in this overlay carries a usable date"

    units = (history or {}).get("units") or {}
    csrs_unit = units.get("csrs", "composite score, 0..1")
    bench_unit = units.get("benchmark", "simple close-to-close return")
    series = (history or {}).get("series") or {}

    base = alt.Chart(frame).encode(
        x=alt.X("date:T", title=None,
                axis=alt.Axis(format="%b %Y", tickCount=6)))

    benchmark = base.mark_area(
        line=False, opacity=0.20,
        color=alt.Gradient(gradient="linear",
                           stops=[alt.GradientStop(color=T.TEXT_FAINT, offset=0),
                                  alt.GradientStop(color=T.SURFACE_2, offset=1)],
                           x1=1, x2=1, y1=1, y2=0),
    ).encode(
        y=alt.Y("benchmark_return:Q",
                title=f"benchmark — {bench_unit}",
                axis=alt.Axis(orient="right", format=".2%")),
        tooltip=[alt.Tooltip("date:T", title="date"),
                 alt.Tooltip("benchmark_return:Q", title="benchmark return",
                             format=".3%")])

    csrs = base.mark_line(color=T.SELECTED, strokeWidth=1.8,
                          interpolate="linear").encode(
        y=alt.Y("csrs:Q", title=f"CSRS — {csrs_unit}",
                scale=alt.Scale(domain=[0, 1], nice=False),
                axis=alt.Axis(orient="left", format=".2f")),
        tooltip=[alt.Tooltip("date:T", title="date"),
                 alt.Tooltip("csrs:Q", title="CSRS", format=".4f")])

    layers = [benchmark, csrs]
    if selected_date:
        marker = pd.DataFrame([dict(date=pd.to_datetime(selected_date,
                                                        errors="coerce"))])
        if marker["date"].notna().all():
            layers.append(alt.Chart(marker).mark_rule(
                color=T.ACCENT, strokeWidth=1.6).encode(x="date:T"))

    chart = alt.layer(*layers).resolve_scale(y="independent")
    note = (f"CSRS in {csrs_unit} on the left axis; "
            f"{series.get('label', 'benchmark')} in {bench_unit} on the right. "
            f"Two different units on two independent axes — the lines are not "
            f"comparable in level. Source: {series.get('source', 'not recorded')}. "
            f"A session with no CSRS breaks the line rather than being "
            f"interpolated or zero-filled.")
    return _style(chart, height), note


def pillar_detail(rows, *, value_key: str, title: str, height: int = 190):
    """A small bar chart of one named quantity per pillar.

    `rows` is `[{name, value}]`; a row with no value is **omitted from the
    marks and named in the returned note**, so the chart cannot imply it was
    measured at zero.
    """
    present = [r for r in rows if isinstance(r.get(value_key), (int, float))
               and not isinstance(r.get(value_key), bool)]
    absent = [str(r.get("name")) for r in rows if r not in present]
    if not present:
        return None, ("no pillar reported this quantity at this decision: "
                      + ", ".join(absent or ["none named"]))
    frame = pd.DataFrame([dict(pillar=r["name"], value=float(r[value_key]))
                          for r in present])
    chart = alt.Chart(frame).mark_bar(cornerRadius=5, height=16).encode(
        x=alt.X("value:Q", title=title),
        y=alt.Y("pillar:N", title=None, sort=[r["name"] for r in present]),
        color=alt.Color("pillar:N", legend=None,
                        scale=alt.Scale(domain=list(T.PILLAR_COLOUR),
                                        range=list(T.PILLAR_COLOUR.values()))),
        tooltip=[alt.Tooltip("pillar:N"), alt.Tooltip("value:Q", format=".4f")])
    note = title
    if absent:
        note += (" · not drawn, because no value was reported: "
                 + ", ".join(absent))
    return _style(chart, height), note


def forecast_against_threshold(series, *, height: int = 210):
    """The operational forecast against its calibrated warning threshold.

    Both series are probabilities, so this one legitimately shares an axis —
    unlike the FR41 overlay above, where sharing one would be a category
    error. Returns `(chart, note)` or `(None, reason)`.

    A gap in either line is a session the engine declined to score or could
    not calibrate. It is passed through as a null so the line breaks, never
    interpolated and never zero-filled.
    """
    rows = series or []
    if not rows:
        return None, "the saved forecast state carries no scored series"
    frame = pd.DataFrame([
        dict(date=r.get("date"), probability=r.get("probability"),
             threshold=r.get("threshold")) for r in rows])
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    if frame.empty:
        return None, "no row in the forecast series carries a usable date"

    long = frame.melt("date", ["probability", "threshold"],
                      var_name="series", value_name="value")
    chart = alt.Chart(long).mark_line(strokeWidth=1.5).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%b %Y", tickCount=6)),
        y=alt.Y("value:Q", title="probability", axis=alt.Axis(format=".0%")),
        color=alt.Color("series:N", title=None,
                        scale=alt.Scale(domain=["probability", "threshold"],
                                        range=[T.SELECTED, T.ACCENT])),
        tooltip=[alt.Tooltip("date:T"), alt.Tooltip("series:N"),
                 alt.Tooltip("value:Q", format=".4f")])
    note = ("Both series are probabilities on one axis, which is why they "
            "share it. A gap in either line is a session the engine declined "
            "to score or could not calibrate, shown rather than interpolated.")
    return _style(chart, height), note


def reliability(rows, *, height: int = 210):
    """Predicted probability against realised frequency, on matured labels.

    The model yields no interval, so this is the honest substitute for one:
    did the days it called 5% turn out 5%? The diagonal is drawn because
    without it the bars are unreadable — a point above the line is
    over-prediction, which is a finding, not something to hide.

    Bins with no sessions are dropped rather than plotted at zero: a bin
    nothing fell into has no realised rate, and drawing 0% would assert one.
    """
    present = [r for r in (rows or [])
               if r.get("count") and r.get("mean_predicted") is not None
               and r.get("realised_rate") is not None]
    if not present:
        return None, ("no reliability bin has both a mean prediction and a "
                      "realised rate yet; nothing can be plotted without "
                      "asserting a rate that was not measured")
    frame = pd.DataFrame([
        dict(predicted=float(r["mean_predicted"]),
             realised=float(r["realised_rate"]), sessions=int(r["count"]),
             band=f"{r['lower']:.0%}–{r['upper']:.0%}") for r in present])
    top = max(float(frame["predicted"].max()), float(frame["realised"].max()))
    top = min(1.0, max(0.05, top * 1.15))
    diagonal = alt.Chart(pd.DataFrame(dict(x=[0, top], y=[0, top]))).mark_line(
        color=T.TEXT_FAINT, strokeDash=[4, 4], strokeWidth=1).encode(
        x=alt.X("x:Q", scale=alt.Scale(domain=[0, top], nice=False)),
        y=alt.Y("y:Q", scale=alt.Scale(domain=[0, top], nice=False)))
    points = alt.Chart(frame).mark_circle(color=T.SELECTED, opacity=0.9).encode(
        x=alt.X("predicted:Q", title="mean predicted",
                scale=alt.Scale(domain=[0, top], nice=False),
                axis=alt.Axis(format=".0%")),
        y=alt.Y("realised:Q", title="realised frequency",
                scale=alt.Scale(domain=[0, top], nice=False),
                axis=alt.Axis(format=".0%")),
        size=alt.Size("sessions:Q", title="sessions",
                      scale=alt.Scale(range=[40, 420])),
        tooltip=[alt.Tooltip("band:N", title="band"),
                 alt.Tooltip("sessions:Q"),
                 alt.Tooltip("predicted:Q", format=".4f"),
                 alt.Tooltip("realised:Q", format=".4f")])
    dropped = len(rows or []) - len(present)
    note = ("The dashed line is perfect calibration. A point below it is "
            "over-prediction, above it under-prediction; the marker area is "
            "how many sessions fell in the band.")
    if dropped:
        note += (f" {dropped} bin(s) are not drawn because no session fell in "
                 f"them — an empty bin has no realised rate.")
    return _style(chart=alt.layer(diagonal, points), height=height), note
