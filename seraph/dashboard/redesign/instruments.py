# C12 — Redesigned console: SVG instruments (FR39, FR29 reporting).
"""Pure functions `value -> SVG string`. No Streamlit, no I/O, no analytics.

Every instrument here has the same obligation and it is the reason they are
pure: **an absent quantity must render as absent.** A gauge with nothing to
show keeps its track and its geometry and fills none of it, and says why. It
never draws zero, because zero is a reading and absence is not.

That obligation is testable precisely because these are strings: a test can
assert that an unavailable dial contains no filled arc, without a browser.
"""
from __future__ import annotations

import html
import math

from . import tokens as T

# --- the gauge's geometry -------------------------------------------------
#: Degrees clockwise from 12 o'clock. A 240-degree sweep with the opening at
#: the bottom, so the two ends read as a scale rather than as a closed ring.
GAUGE_START = -120.0
GAUGE_SWEEP = 240.0


def _polar(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    rad = math.radians(deg)
    return cx + r * math.sin(rad), cy - r * math.cos(rad)


def _arc(cx: float, cy: float, r: float, deg0: float, deg1: float) -> str:
    """An `M ... A ...` path from deg0 to deg1, clockwise."""
    x0, y0 = _polar(cx, cy, r, deg0)
    x1, y1 = _polar(cx, cy, r, deg1)
    large = 1 if abs(deg1 - deg0) > 180 else 0
    sweep = 1 if deg1 >= deg0 else 0
    return (f"M {x0:.2f} {y0:.2f} A {r:.2f} {r:.2f} 0 {large} {sweep} "
            f"{x1:.2f} {y1:.2f}")


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _fmt(x, places: int = 3, dash: str = "—") -> str:
    return f"{float(x):.{places}f}" if _is_number(x) else dash


# --------------------------------------------------------------------------
# The composite-score dial
# --------------------------------------------------------------------------
def composite_dial(*, value=None, ci_lower=None, ci_upper=None,
                   alert_level=None, unavailable_reason: str | None = None,
                   caption: str = "", size: int = 268) -> str:
    """The CSRS instrument, or its empty track with the reason it is empty.

    `value` is the CSRS on its own 0..1 scale — the scale is drawn, so the
    arc length is a readable quantity rather than a decoration. `ci_lower` /
    `ci_upper` draw the FR29 interval as a separate, thinner concentric band;
    they are a different quantity from the point estimate and are never
    merged into one arc with it.

    With no numeric `value` the dial renders the track **unfilled** and the
    centre reads an em dash under an `UNAVAILABLE` label. There is no code
    path here that substitutes zero: `_is_number` gates every fill.
    """
    cx = cy = size / 2
    r = size / 2 - 26
    r_ci = r - 17
    stroke = 15
    deg_end = GAUGE_START + GAUGE_SWEEP
    colour = T.alert_colour(alert_level) if _is_number(value) else T.TEXT_FAINT

    parts = [
        f'<svg class="rd-dial" viewBox="0 0 {size} {size}" width="{size}" '
        f'height="{size}" role="img" aria-label="composite systemic risk score">',
        # the empty track — always drawn, so the geometry is the same whether
        # or not there is a number to put in it
        f'<path d="{_arc(cx, cy, r, GAUGE_START, deg_end)}" fill="none" '
        f'stroke="{T.UNAVAILABLE_TRACK}" stroke-width="{stroke}" '
        f'stroke-linecap="round"/>',
    ]

    if _is_number(value):
        t = _clamp01(float(value))
        if t > 0.0005:
            parts.append(
                f'<path d="{_arc(cx, cy, r, GAUGE_START, GAUGE_START + GAUGE_SWEEP * t)}" '
                f'fill="none" stroke="{colour}" stroke-width="{stroke}" '
                f'stroke-linecap="round"/>')
        if _is_number(ci_lower) and _is_number(ci_upper):
            lo, hi = _clamp01(float(ci_lower)), _clamp01(float(ci_upper))
            if hi > lo:
                parts.append(
                    f'<path d="{_arc(cx, cy, r_ci, GAUGE_START + GAUGE_SWEEP * lo, GAUGE_START + GAUGE_SWEEP * hi)}" '
                    f'fill="none" stroke="{colour}" stroke-width="4" '
                    f'stroke-linecap="round" opacity=".42"/>')
        # the scale: end ticks, so the arc is read against 0..1 and not as a
        # proportion of something unnamed
        for t_tick, label in ((0.0, "0"), (1.0, "1")):
            x_t, y_t = _polar(cx, cy, r - stroke - 9,
                              GAUGE_START + GAUGE_SWEEP * t_tick)
            parts.append(
                f'<text x="{x_t:.1f}" y="{y_t:.1f}" fill="{T.TEXT_FAINT}" '
                f'font-size="10" text-anchor="middle" '
                f'dominant-baseline="middle">{label}</text>')
        parts.append(
            f'<text x="{cx}" y="{cy - 4}" fill="{T.TEXT}" font-size="42" '
            f'font-weight="600" text-anchor="middle" '
            f'dominant-baseline="middle">{_fmt(value, 3)}</text>')
        parts.append(
            f'<text x="{cx}" y="{cy + 26}" fill="{T.TEXT_DIM}" font-size="11" '
            f'text-anchor="middle">CSRS · 0–1</text>')
        if str(alert_level or "").strip():
            parts.append(
                f'<text x="{cx}" y="{cy + 44}" fill="{colour}" font-size="10.5" '
                f'letter-spacing="1.4" font-weight="650" text-anchor="middle">'
                f'{html.escape(str(alert_level).upper())}</text>')
    else:
        parts.append(
            f'<text x="{cx}" y="{cy - 6}" fill="{T.TEXT_FAINT}" font-size="40" '
            f'font-weight="500" text-anchor="middle" '
            f'dominant-baseline="middle">—</text>')
        parts.append(
            f'<text x="{cx}" y="{cy + 24}" fill="{T.TEXT_FAINT}" font-size="10" '
            f'letter-spacing="1.5" font-weight="650" text-anchor="middle">'
            f'UNAVAILABLE</text>')

    parts.append("</svg>")
    svg = "".join(parts)

    legend = []
    if _is_number(value):
        legend.append(_legend_item(colour,
                                   f"CSRS point estimate {_fmt(value, 4)}"))
        if _is_number(ci_lower) and _is_number(ci_upper):
            legend.append(_legend_item(
                colour,
                f"FR29 95% interval {_fmt(ci_lower, 3)} – {_fmt(ci_upper, 3)}",
                opacity=".42"))
    legend.append(_legend_item(T.UNAVAILABLE_TRACK, "unfilled scale (0–1)",
                               track=True))

    body = [f'<div class="rd-dial-wrap" style="text-align:center">{svg}</div>']
    if unavailable_reason and not _is_number(value):
        body.append(
            f'<div class="rd-unavail" style="margin-top:10px">'
            f'<p class="rd-unavail-label">no composite score</p>'
            f'<p class="rd-reason">{html.escape(unavailable_reason)}</p></div>')
    if caption:
        body.append(f'<p class="rd-panel-note">{html.escape(caption)}</p>')
    body.append('<div class="rd-legend">' + "".join(legend) + "</div>")
    return "".join(body)


def _legend_item(colour: str, label: str, *, opacity: str = "1",
                 track: bool = False) -> str:
    cls = "rd-swatch rd-swatch--track" if track else "rd-swatch"
    style = ("" if track
             else f'background:{colour};opacity:{opacity};')
    return (f'<span class="rd-legend-item"><span class="{cls}" '
            f'style="{style}"></span>{html.escape(label)}</span>')


# --------------------------------------------------------------------------
# Signed-contribution tracks
# --------------------------------------------------------------------------
def contribution_tracks(rows, *, unit: str, width: int = 520) -> str:
    """Rounded tracks for signed per-pillar contributions.

    `rows` is `[{name, value, colour, excluded, missing_reason}]`. **These are
    not percentages.** Shapley contributions to the CSRS are signed and sum to
    the score, not to 1, so each track is drawn on a shared symmetric axis
    scaled to the largest absolute contribution and labelled with `unit`.
    Nothing here divides by a total.

    Three row states, because they are three different claims:

    * **a contribution** — a bar, with a hairline floor so a real but tiny
      contribution stays visible as measured-and-tiny;
    * **excluded by the D2 mask** (`excluded: True`) — an empty dashed track.
      Its Shapley is exactly 0.0 by construction, and the number is still
      printed, but the track must not read as "consulted, contributed nought";
    * **no value at all** — an empty dashed track with the reason.
    """
    values = [abs(float(r["value"])) for r in rows
              if _is_number(r.get("value")) and not r.get("excluded")]
    scale = max(values) if values else 0.0
    row_h, gap = 30, 12
    height = len(rows) * (row_h + gap)
    mid = width / 2
    half = mid - 4

    out = [f'<svg class="rd-tracks" viewBox="0 0 {width} {height}" '
           f'width="100%" height="{height}" preserveAspectRatio="none" '
           f'role="img" aria-label="per-pillar contributions">']
    # the zero axis — drawn always, so a signed quantity has a visible origin
    out.append(f'<line x1="{mid}" y1="0" x2="{mid}" y2="{height}" '
               f'stroke="{T.BORDER}" stroke-width="1"/>')

    for i, row in enumerate(rows):
        y = i * (row_h + gap)
        colour = row.get("colour") or T.TEXT_FAINT
        out.append(f'<rect x="4" y="{y}" width="{width - 8}" height="{row_h}" '
                   f'rx="{row_h / 2:.1f}" fill="{T.UNAVAILABLE_TRACK}"/>')
        if row.get("excluded"):
            out.append(f'<rect x="4" y="{y}" width="{width - 8}" '
                       f'height="{row_h}" rx="{row_h / 2:.1f}" fill="none" '
                       f'stroke="{colour}" stroke-width="1" opacity=".45" '
                       f'stroke-dasharray="3 5"/>')
        elif _is_number(row.get("value")) and scale > 0:
            v = float(row["value"])
            length = abs(v) / scale * half
            if length < 1.5:
                # A real but vanishing contribution. A hairline keeps it
                # visible as measured-and-tiny rather than as absent.
                length = 1.5
            x = mid if v >= 0 else mid - length
            out.append(f'<rect x="{x:.2f}" y="{y}" width="{length:.2f}" '
                       f'height="{row_h}" rx="{row_h / 2:.1f}" fill="{colour}"/>')
        else:
            out.append(f'<rect x="4" y="{y}" width="{width - 8}" '
                       f'height="{row_h}" rx="{row_h / 2:.1f}" fill="none" '
                       f'stroke="{T.BORDER}" stroke-width="1" '
                       f'stroke-dasharray="4 4"/>')
    out.append("</svg>")

    labels: list[str] = []
    footnotes: list[str] = []
    for row in rows:
        colour = row.get("colour") or T.TEXT_FAINT
        name = html.escape(str(row.get("name", "")))
        if row.get("excluded"):
            shown = (f'{float(row["value"]):+.4f}'
                     if _is_number(row.get("value")) else "—")
            val = (f'<span class="rd-num" style="color:{T.TEXT_FAINT}">'
                   f'{shown}</span>')
            # Short on the row, because the row is one line tall. The full
            # statement lives in the note under the chart, which is where a
            # reader who wants the reason goes.
            tail = (f'<span style="color:{T.TEXT_FAINT}"> · excluded by mask'
                    f'</span>')
        elif _is_number(row.get("value")):
            val = f'<span class="rd-num" style="color:{colour}">{float(row["value"]):+.4f}</span>'
            tail = f'<span style="color:{T.TEXT_FAINT}"> {html.escape(unit)}</span>'
        else:
            val = f'<span style="color:{T.TEXT_FAINT}">not measured</span>'
            tail = ""
            footnotes.append(
                f'<b style="color:{colour}">{name}</b> — '
                f'{html.escape(str(row.get("missing_reason") or "no reason recorded"))}')
        labels.append(
            f'<div style="display:flex;justify-content:space-between;gap:14px;'
            f'align-items:baseline;height:30px;margin-bottom:12px;font-size:12px">'
            f'<span style="color:{colour};font-weight:600;letter-spacing:.09em;'
            f'text-transform:uppercase;font-size:10.5px">{name}</span>'
            f'<span style="text-align:right">{val}{tail}</span></div>')

    notes = "".join(f'<p class="rd-panel-note" style="margin-top:4px">{f}</p>'
                    for f in footnotes)
    return (f'<div style="display:grid;grid-template-columns:1fr 1.08fr;gap:20px;'
            f'align-items:start">'
            f'<div>{"".join(out)}</div><div>{"".join(labels)}</div></div>'
            f'{notes}'
            f'<p class="rd-panel-note">Axis is symmetric about zero and scaled to '
            f'the largest absolute contribution ({_fmt(scale, 4) if scale else "n/a"}). '
            f'These are signed contributions in {html.escape(unit)} — they are '
            f'<b>not</b> shares of a total and do not sum to 100%. A dashed '
            f'track is a pillar the D2 mask excluded: its contribution is 0 '
            f'because it was not consulted, which is a different statement '
            f'from a measured contribution of 0.</p>')


# --------------------------------------------------------------------------
# Weight tracks (these genuinely are a normalised set)
# --------------------------------------------------------------------------
def weight_tracks(rows, *, width: int = 520) -> str:
    """Rounded tracks for D2 effective weights, which do sum to 1 by design.

    Kept separate from `contribution_tracks` on purpose. Weights are a
    normalised allocation and may honestly be read as shares; Shapley
    contributions may not. Collapsing the two into one widget is how a signed
    quantity ends up in a pie chart.
    """
    row_h, gap = 22, 10
    height = max(1, len(rows)) * (row_h + gap)
    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
           f'preserveAspectRatio="none" role="img" aria-label="effective weights">']
    for i, row in enumerate(rows):
        y = i * (row_h + gap)
        colour = row.get("colour") or T.TEXT_FAINT
        out.append(f'<rect x="0" y="{y}" width="{width}" height="{row_h}" '
                   f'rx="{row_h / 2:.1f}" fill="{T.UNAVAILABLE_TRACK}"/>')
        if _is_number(row.get("value")):
            w = _clamp01(float(row["value"])) * width
            if w > 0.5:
                out.append(f'<rect x="0" y="{y}" width="{w:.2f}" height="{row_h}" '
                           f'rx="{row_h / 2:.1f}" fill="{colour}"/>')
    out.append("</svg>")

    labels = []
    for row in rows:
        colour = row.get("colour") or T.TEXT_FAINT
        shown = (f'{float(row["value"]):.3f}' if _is_number(row.get("value"))
                 else "—")
        labels.append(
            f'<div style="display:flex;justify-content:space-between;'
            f'height:22px;margin-bottom:10px;font-size:11.5px;align-items:center">'
            f'<span style="color:{colour};letter-spacing:.09em;'
            f'text-transform:uppercase;font-size:10px;font-weight:600">'
            f'{html.escape(str(row.get("name", "")))}</span>'
            f'<span class="rd-num" style="color:{T.TEXT_DIM}">{shown}</span></div>')

    return (f'<div style="display:grid;grid-template-columns:1fr .62fr;gap:18px;'
            f'align-items:start"><div>{"".join(out)}</div>'
            f'<div>{"".join(labels)}</div></div>')


# --------------------------------------------------------------------------
# The shared bottom timeline
# --------------------------------------------------------------------------
def timeline(rows, *, selected_date=None, height: int = 74) -> str:
    """One tick per decision date in the run, coverage shown as coverage.

    `rows` is `[{date, csrs, benchmark_available}]` straight off the FR41
    overlay. A date whose CSRS is `None` draws a **hollow** tick at the
    baseline: the session existed and produced no score, which is a different
    statement from "the score was low", and the two must not share a shape.
    """
    if not rows:
        return ('<div class="rd-unavail"><p class="rd-unavail-label">no timeline'
                '</p><p class="rd-reason">this run carries no decision dates'
                '</p></div>')
    width = 1200
    pad_l, pad_r, pad_b = 8, 8, 20
    usable = width - pad_l - pad_r
    step = usable / max(1, len(rows) - 1) if len(rows) > 1 else 0
    top, bottom = 10, height - pad_b
    span = bottom - top
    scored = [r for r in rows if _is_number(r.get("csrs"))]
    peak = max((float(r["csrs"]) for r in scored), default=1.0) or 1.0

    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
           f'preserveAspectRatio="none" role="img" '
           f'aria-label="decision-date timeline">',
           f'<line x1="{pad_l}" y1="{bottom}" x2="{width - pad_r}" y2="{bottom}" '
           f'stroke="{T.BORDER}" stroke-width="1"/>']
    sel_x = None
    for i, row in enumerate(rows):
        x = pad_l + i * step
        if selected_date is not None and row.get("date") == selected_date:
            sel_x = x
        if _is_number(row.get("csrs")):
            h = max(1.5, _clamp01(float(row["csrs"]) / peak) * span)
            out.append(f'<rect x="{x - 1.4:.2f}" y="{bottom - h:.2f}" width="2.8" '
                       f'height="{h:.2f}" rx="1.4" fill="{T.SELECTED}" '
                       f'opacity=".72"/>')
        else:
            out.append(f'<circle cx="{x:.2f}" cy="{bottom:.2f}" r="2.2" '
                       f'fill="none" stroke="{T.TEXT_FAINT}" stroke-width="1"/>')
        if row.get("benchmark_available") is False:
            out.append(f'<rect x="{x - 1.4:.2f}" y="{bottom + 4:.2f}" width="2.8" '
                       f'height="4" fill="{T.ALERT["amber"]}" opacity=".8"/>')
    if sel_x is not None:
        out.append(f'<line x1="{sel_x:.2f}" y1="{top - 6}" x2="{sel_x:.2f}" '
                   f'y2="{bottom + 9}" stroke="{T.ACCENT}" stroke-width="1.6"/>')
        out.append(f'<circle cx="{sel_x:.2f}" cy="{top - 6}" r="3.2" '
                   f'fill="{T.ACCENT}"/>')
    out.append("</svg>")

    first, last = rows[0].get("date", ""), rows[-1].get("date", "")
    legend = "".join([
        _legend_item(T.SELECTED, f"CSRS by decision date (peak {_fmt(peak, 3)})"),
        _legend_item(T.TEXT_FAINT, "session with no CSRS — hollow, not zero",
                     track=True),
        _legend_item(T.ALERT["amber"], "no official benchmark return that date"),
        _legend_item(T.ACCENT, "selected decision"),
    ])
    return ("".join(out) +
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:10.5px;color:{T.TEXT_FAINT};margin-top:2px">'
            f'<span class="rd-num">{html.escape(str(first))}</span>'
            f'<span class="rd-num">{html.escape(str(last))}</span></div>'
            f'<div class="rd-legend">{legend}</div>')
