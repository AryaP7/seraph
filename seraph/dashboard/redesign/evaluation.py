# C12 — Redesigned console: EVALUATION (FR35 ablation, T10).
"""The FR35 ablation tables, read-only — and read-only in two specific places.

* **No commit control.** D5(d) makes a committed pre-registered design the
  precondition for any AUC, and DR-05 step 5 left committing it to a person
  so that it cannot happen as a side effect. A button here would be exactly
  that side effect. The command is printed instead.
* **No run control.** A full ablation calibrates once per fold; starting one
  on page render would make every refresh a cliff.

What this screen shows that a table of numbers hides: how many of each
configuration's declared folds were actually measured, and which absence
accounts for the rest. **An unavailable cell is a result, not a gap** — it is
retained with its reason and counted, never dropped to make a table look
complete.
"""
from __future__ import annotations

import math

import streamlit as st

from . import components as C, data, tokens as T


def _finite(x) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and not math.isnan(x) and not math.isinf(x))


def render(*, role: str) -> None:
    surface = data.evaluation_state(role)

    C.html_block(
        '<div class="rd-topbar"><div>'
        '<p class="rd-eyebrow">SERAPH · redesigned console</p>'
        '<h1>Evaluation</h1>'
        '<p class="rd-panel-sub" style="margin-top:4px">'
        'FR35 ablation — what this instrument has been shown to do</p>'
        f'</div><div class="rd-topbar-right">{C.chip("role", role)}</div></div>')

    if not surface.get("permitted"):
        with C.panel("Evaluation", "institutional or regulator"):
            C.html_block(C.unavailable(
                "not available at this role",
                "an ablation table reports what the instrument can and cannot "
                "do, not a current risk level. The backend withholds it from "
                "retail; switch role in the sidebar"))
        return

    design = surface.get("design") or {}
    if not design.get("committed"):
        with C.panel("No committed design", "D5(d) precondition"):
            C.html_block(C.unavailable(
                "no pre-registered design is committed",
                "so NO AUC can be computed at all",
                str(surface.get("note") or ""),
                f"expected at {design.get('path')} · override with "
                f"SERAPH_PREREGISTRATION"))
            st.code(surface.get("commit_hint", ""), language="bash")
        return

    if not design.get("intact", True):
        with C.panel("Design not intact", "committed then edited"):
            C.html_block(C.unavailable(
                "the committed design no longer matches its own hash",
                "it was edited after it was committed, so no result produced "
                "under it is reportable"))
        return

    _design(design)

    reports = surface.get("reports") or []
    if not reports:
        with C.panel("No saved evaluation run", "the design is committed"):
            C.html_block(C.unavailable(
                "no run has been saved yet",
                f"this screen reads every artefact in "
                f"{surface.get('reports_dir')}"))
            st.code("python scripts/run_experiment.py --dataset fixture "
                    "--out <path>", language="bash")
        return

    names = [r["name"] for r in reports]
    chosen = st.selectbox("Saved evaluation run", names, key="rd_experiment")
    report = next(r for r in reports if r["name"] == chosen)

    if not report.get("readable"):
        with C.panel("Unreadable artefact", chosen):
            C.html_block(C.unavailable("could not be read",
                                       str(report.get("error"))))
        return
    if not report.get("intact"):
        C.html_block(
            f'<div class="rd-panel" style="border-color:#56222C;'
            f'background:#140A0E"><p class="rd-panel-title" '
            f'style="color:{T.ALERT["red"]}">ARTEFACT NOT INTACT</p>'
            f'<p class="rd-reason">This artefact does not match its own '
            f'content hash — it was edited after it was written. Do not quote '
            f'these numbers.</p></div>')

    _counts(report)
    _tables(report)
    _absences(report)

    with st.expander("The run as text"):
        st.code(report.get("rendered", ""))
    if report.get("dataset_provenance"):
        with st.expander("Stored evaluation input provenance"):
            st.json(report["dataset_provenance"])


# --------------------------------------------------------------------------
def _design(design: dict) -> None:
    with C.panel("Pre-registered design", "committed once, by a person"):
        C.html_block(C.chips([
            C.chip("design hash", str(design.get("hash", ""))[:16] + "…"),
            C.chip("Table-B scope", str(design.get("table_b_scope"))),
            C.chip("configurations", str(design.get("configurations"))),
            C.chip("amber threshold", str(design.get("amber_threshold"))),
            C.chip("calibration budget", str(design.get("calibration_max_iter"))),
            C.chip("intact", "yes" if design.get("intact") else "no",
                   tone="ok" if design.get("intact") else "bad"),
        ]))


def _counts(report: dict) -> None:
    a, b, c = st.columns(3)
    for column, (label, key, unit, tone) in zip(
            (a, b, c),
            (("measured cells", "measured", "folds with an AUC", T.SELECTED),
             ("unavailable cells", "unavailable", "each retained with a reason",
              T.ALERT["amber"]),
             ("not publishable", "unpublishable", "withheld from metrics",
              T.TEXT_DIM))):
        with column:
            C.html_block(C.metric(label, str(report.get(key, "—")), unit,
                                  colour=tone))
    C.html_block(C.chips([
        C.chip("artefact", str(report.get("artefact_id", ""))[:16] + "…"),
        C.chip("design", str(report.get("pre_registration_hash", ""))[:16] + "…"),
        C.chip("budget", str(report.get("calibration_max_iter"))),
    ]))
    if report.get("comparability"):
        # Above the tables, not below: the one thing a reader will do with
        # three tables is rank them together.
        C.html_block(
            f'<div class="rd-panel" style="border-color:#5A4420;'
            f'background:#1E1708"><p class="rd-panel-title" '
            f'style="color:{T.ALERT["amber"]}">NOT A SINGLE RANKING</p>'
            f'<p class="rd-reason">{C.esc(report["comparability"])}</p></div>')


def _tables(report: dict) -> None:
    configurations = report.get("configurations") or []
    for table in sorted({c["table"] for c in configurations}):
        rows = [c for c in configurations if c["table"] == table]
        declared = rows[0].get("declared_folds")
        with C.panel(f"Table {table}", f"{declared} folds declared"):
            body = []
            for c in rows:
                measured = c.get("measured_folds") or 0
                body.append([
                    c.get("subset"), c.get("mode"), c.get("xi_mode"),
                    f"{measured}/{c.get('declared_folds')}",
                    (round(c["mean_auc"], 4) if measured and _finite(c.get("mean_auc"))
                     else None),
                    ("—" if c.get("auc_min") is None
                     else f"{c['auc_min']:.3f}..{c['auc_max']:.3f}"),
                    (round(c["mean_lead_time_days"], 1)
                     if _finite(c.get("mean_lead_time_days")) else None),
                    (", ".join(f"{k} ×{v}" for k, v
                               in (c.get("unavailable_folds") or {}).items())
                     or None),
                ])
            C.html_block(C.table(
                ["subset", "mode", "xi", "folds", "mean AUC", "spread",
                 "lead (d)", "absences"], body, numeric_columns={4, 6}))
            measured_total = sum(c.get("measured_folds") or 0 for c in rows)
            if not measured_total:
                C.html_block(
                    '<p class="rd-panel-note">No configuration in this table '
                    'measured a single fold. The absences column says why for '
                    'each — that is the result, not an empty table.</p>')


def _absences(report: dict) -> None:
    absences = report.get("absences") or {}
    with C.panel("Unavailable cells", "each is a result, not a gap"):
        if not absences:
            C.html_block('<p class="rd-reason">Every declared fold was '
                         'measured.</p>')
            return
        total = sum(absences.values())
        C.html_block(C.table(
            ["reason", "folds"],
            [[reason, count] for reason, count
             in sorted(absences.items(), key=lambda kv: -kv[1])],
            numeric_columns={1}))
        C.html_block(
            f'<p class="rd-panel-note"><span class="rd-num">{total}</span> '
            f'declared fold(s) produced no AUC. Each is retained in the '
            f'artefact with its reason rather than dropped, which is what '
            f'makes the ablation falsifiable (FR35/FR36).</p>')
        if report.get("unpublishable"):
            C.html_block(
                f'<p class="rd-panel-note">'
                f'<span class="rd-num">{C.esc(report["unpublishable"])}</span> '
                f'unavailable rows are retained with their reasons. Only '
                f'measured rows from Tables A, B and C may be published as '
                f'evaluation metrics.</p>')
