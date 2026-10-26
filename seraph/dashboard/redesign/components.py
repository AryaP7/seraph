# C12 — Redesigned console: layout primitives (FR39).
"""Small HTML builders shared by the redesigned screens.

They exist so that the honesty rules have exactly one implementation each.
`unavailable()` is the important one: a quantity that does not exist always
renders through it, which means it always carries a label *and* a reason, and
a reviewer can grep for the places that claim absence.
"""
from __future__ import annotations

import html
from contextlib import contextmanager

import streamlit as st

from . import tokens as T


def esc(text) -> str:
    return html.escape("" if text is None else str(text))


# --------------------------------------------------------------------------
@contextmanager
def panel(title: str, subtitle: str = "", *, note: str = ""):
    """A large rounded container. Streamlit content goes inside the `with`.

    Streamlit cannot nest arbitrary widgets inside a raw `<div>`, so the
    rounded container is drawn as a bordered `st.container` and the heading is
    emitted as HTML above its content.
    """
    box = st.container(border=True)
    with box:
        head = f'<p class="rd-panel-title">{esc(title)}</p>'
        if subtitle:
            head += f'<p class="rd-panel-sub">{esc(subtitle)}</p>'
        st.markdown(f'<div class="rd-panel-head" style="flex-direction:column;'
                    f'gap:3px">{head}</div>', unsafe_allow_html=True)
        yield box
        if note:
            st.markdown(f'<p class="rd-panel-note">{esc(note)}</p>',
                        unsafe_allow_html=True)


def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# --------------------------------------------------------------------------
def chip(label: str, value: str = "", *, tone: str = "") -> str:
    """A compact status pill. `tone` is one of '', 'ok', 'warn', 'bad', 'accent'."""
    cls = "rd-chip" + (f" rd-chip--{tone}" if tone else "")
    body = esc(label)
    if value:
        body += f" <b>{esc(value)}</b>"
    return f'<span class="{cls}"><span class="rd-dot"></span>{body}</span>'


def chips(items) -> str:
    return ('<div class="rd-topbar-right" style="justify-content:flex-start">'
            + "".join(items) + "</div>")


def unavailable(label: str, *reasons: str) -> str:
    """The one way this frontend says a quantity does not exist.

    Always a label AND at least one reason. A caller with nothing to say is a
    bug, and the placeholder below makes that visible on screen rather than
    rendering a silently blank box.
    """
    lines = [r for r in reasons if r]
    if not lines:
        lines = ["no reason was recorded for this absence — that is itself a "
                 "defect, not an empty result"]
    body = "".join(f'<p class="rd-reason">{esc(r)}</p>' for r in lines)
    return (f'<div class="rd-unavail"><p class="rd-unavail-label">{esc(label)}'
            f'</p>{body}</div>')


def metric(label: str, value: str, unit: str = "", *, colour: str | None = None,
           available: bool = True) -> str:
    """A single figure. `available=False` prints an em dash, never a zero."""
    shown = value if available else "—"
    tint = colour or (T.TEXT if available else T.TEXT_FAINT)
    out = (f'<p class="rd-metric-label">{esc(label)}</p>'
           f'<p class="rd-metric-value" style="color:{tint}">{esc(shown)}</p>')
    if unit:
        out += f'<p class="rd-metric-unit">{esc(unit)}</p>'
    return out


def table(headers, rows, *, numeric_columns=()) -> str:
    """A compact table. Columns named in `numeric_columns` get tabular numerals.

    A cell whose value is `None` renders as a dimmed em dash — the table's own
    version of the absence rule, so a blank cell never passes for a zero.
    """
    numeric = set(numeric_columns)
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = []
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            klass = []
            if i in numeric or headers[i] in numeric:
                klass.append("rd-n")
            if cell is None:
                klass.append("rd-muted")
                cell = "—"
            attr = f' class="{" ".join(klass)}"' if klass else ""
            cells.append(f"<td{attr}>{esc(cell)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<table class="rd-table"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>')


def pillar_card(row: dict) -> str:
    """One pillar card, coloured from the single `PILLAR_COLOUR` table.

    Four states, kept visually distinct because they are different facts:

    * **a reading** — a numeric value, with whether it entered the composite;
    * **declared not scored** (`score_eligible` false) — a structural absence
      that carries the engine's own reason;
    * **withheld at this role** — the engine emitted a reading and the C12
      transport boundary removed it from this role's payload. Reporting that
      as "not emitted" would be a false statement about the model;
    * **nothing emitted at all** — the pillar is missing from the payload.
    """
    name = row["name"]
    colour = T.pillar_colour(name)
    model = row.get("model") or ("model not named at this role"
                                 if row.get("withheld") else "model not named")
    head = (f'<div class="rd-pillar-rule" style="background:{colour}"></div>'
            f'<div class="rd-pillar-body">'
            f'<p class="rd-pillar-name" style="color:{colour}">{esc(name)}</p>'
            f'<p class="rd-pillar-model">{esc(model)}</p>')

    if row.get("withheld"):
        body = unavailable(
            "withheld at this role",
            f'the {row.get("role") or "current"} projection does not carry '
            f'per-pillar readings: gateway.ROLE_FIELDS omits "pillarScores", '
            f'so the field is absent from the payload rather than hidden in it',
            "the pillar did report — this role is not shown it. Switch to "
            "institutional or regulator to see the reading")
    elif not row.get("present"):
        body = unavailable(
            "not emitted",
            "this projection carries no entry for this pillar at all, which "
            "is different from a pillar that reported and was not scored")
    elif row.get("value") is None:
        body = unavailable(
            "declared not scored",
            str(row.get("reason") or "the engine recorded no reason"),
            f'origin: {row.get("origin")}' if row.get("origin") else "")
    else:
        in_mask = row.get("in_mask")
        if in_mask is True:
            mask_line = "entered the composite (D2 mask: included)"
            tone = "ok"
        elif in_mask is False:
            mask_line = "excluded from the composite (D2 mask: excluded)"
            tone = "warn"
        else:
            mask_line = "mask not visible at this role"
            tone = ""
        body = (
            f'<p class="rd-metric-value rd-num" style="font-size:30px;'
            f'color:{colour}">{float(row["value"]):.4f}</p>'
            f'<p class="rd-metric-unit">pillar score</p>'
            f'<div style="margin-top:10px">{chip(mask_line, tone=tone)}</div>')
        if row.get("reason"):
            body += f'<p class="rd-panel-note">{esc(row["reason"])}</p>'

    stamp = row.get("information_timestamp")
    tail = (f'<p class="rd-panel-note rd-num">information as of '
            f'{esc(stamp)}</p>' if stamp else
            '<p class="rd-panel-note">no information timestamp recorded</p>')
    return f'<div class="rd-pillar">{head}{body}{tail}</div></div>'
