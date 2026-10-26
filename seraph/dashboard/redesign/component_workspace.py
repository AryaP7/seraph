# C12 — Redesigned console: WORKSPACE as controls inside the console (T05/T08/T09).
"""Portfolios, scenarios and regulator cases, rendered into the console's nav.

Every control is declarative: it names its operation and its inputs through
`data-rd-*` attributes, and the browser binder sends it through the console's
own `request()`. So the permission rules stay where they already are —
`WORKFLOW_ROLES` and `dispatch` in the backend — and a control this screen
forgets to hide is still refused by the engine rather than performed.

Kept apart from `component_views.py` because it is the only view that writes.
"""
from __future__ import annotations

from . import components as C, data
from .component_views import _section, esc


def workspace(bundle: dict, role: str, state: dict) -> str:
    if bundle.get("error"):
        return _section("Workspace unavailable", "durable workflows",
                        C.unavailable("durable workflows unavailable",
                                      str(bundle["error"])))
    blocks = [_section(
        "Workspace", "durable state, scoped to the selected decision",
        C.chips([C.chip("run", str(state.get("run_id") or "")[:16]),
                 C.chip("decision", str(state.get("date") or "")),
                 C.chip("role", role)]),
        note=str(bundle.get("identity_note") or ""))]
    blocks.append(_portfolios(bundle))
    blocks.append(_scenarios(bundle, role))
    blocks.append(_cases(bundle, role, state))
    return "".join(blocks)


def _portfolios(bundle: dict) -> str:
    portfolios = bundle.get("portfolios") or []
    held = bundle.get("holdings") or {}
    body = []

    if portfolios:
        options = "".join(
            '<option value="{pid}"{sel}>{name} · {short}</option>'.format(
                pid=esc(p["portfolio_id"]),
                sel=" selected" if p["portfolio_id"] == bundle.get("portfolio_id") else "",
                name=esc(p["name"]), short=esc(p["portfolio_id"][:12]))
            for p in portfolios)
        body.append('<label class="rd-metric-label">portfolio</label>'
                    '<select class="rd-select" data-rd-select="portfolio_id">'
                    + options + "</select>")
        rows = held.get("holdings") or []
        if rows:
            keys = sorted({k for r in rows for k in r})
            body.append(C.table(
                keys, [[r.get(k) for k in keys] for r in rows],
                numeric_columns={k for k in keys
                                 if k in ("quantity", "value", "weight")}))
            body.append('<p class="rd-panel-note">total value '
                        '<span class="rd-num">'
                        + esc(held.get("total_value")) + "</span></p>")
        else:
            body.append(C.unavailable(
                "no holdings in force",
                str(held.get("note")
                    or "this portfolio has no snapshot in force")))
        body.append(
            '<p class="rd-unavail-label" style="margin-top:14px">'
            "upload holdings</p>"
            '<input type="file" id="rd-ws-file" accept=".csv,.json" class="rd-input"/>'
            '<input type="text" id="rd-ws-effective" class="rd-input" value="'
            + esc(bundle.get("now_ist", "")) + '" placeholder="effective at (IST)"/>'
            '<button class="rd-button" data-rd-op="ws_preview"'
            ' data-rd-file-body="rd-ws-file"'
            ' data-rd-const-source_name="upload">Preview</button>'
            '<button class="rd-button" data-rd-op="ws_commit"'
            ' data-rd-file-body="rd-ws-file"'
            ' data-rd-field-effective_at="rd-ws-effective"'
            ' data-rd-const-source_name="upload">Save snapshot</button>'
            '<p class="rd-panel-note">Preview reports accepted and rejected '
            "rows before anything is committed. A rejected row is shown with "
            "its reason, not counted and discarded.</p>")
        preview = bundle.get("preview")
        if preview:
            body.append(C.chips([
                C.chip("accepted", str(preview.get("accepted")), tone="ok"),
                C.chip("rejected", str(preview.get("rejected")),
                       tone="warn" if preview.get("rejected") else "")]))
            rejected = preview.get("rejected_rows") or []
            if rejected:
                keys = sorted({k for r in rejected for k in r})
                body.append(C.table(keys,
                                    [[r.get(k) for k in keys] for r in rejected]))
            # Quality findings the parser cannot make: it is pure, so it
            # cannot check a symbol against the price corpus, and it cannot
            # tell a holding worth nothing from one nobody priced.
            findings = preview.get("quality") or []
            if findings:
                body.append(
                    '<p class="rd-unavail-label" style="margin-top:12px">'
                    "import quality</p>"
                    + "".join(C.unavailable("check this before committing", f)
                              for f in findings))
    else:
        body.append(C.unavailable(
            "no portfolio yet",
            "create one below; portfolios are durable and survive a restart"))

    body.append(
        '<p class="rd-unavail-label" style="margin-top:14px">new portfolio</p>'
        '<input type="text" id="rd-ws-new" class="rd-input" placeholder="portfolio name"/>'
        '<button class="rd-button" data-rd-op="ws_create"'
        ' data-rd-field-name="rd-ws-new">Create portfolio</button>')
    return _section("Portfolios", "T05 — durable holdings", "".join(body))


def _scenarios(bundle: dict, role: str) -> str:
    if role == "retail":
        return _section("Scenarios", "institutional or regulator", C.unavailable(
            "scenarios are an institutional or regulator tool",
            "the backend's WORKFLOW_ROLES table decides this, not this "
            "screen, and it refuses the operation for retail. Switch role, "
            "top left"))
    scenarios = bundle.get("scenarios") or []
    selected = esc(bundle.get("scenario_id") or "")
    body = []
    if scenarios:
        options = "".join(
            '<option value="{sid}"{sel}>{name} · r{rev}</option>'.format(
                sid=esc(s["scenario_id"]),
                sel=" selected" if s["scenario_id"] == bundle.get("scenario_id") else "",
                name=esc(s["name"]), rev=esc(s.get("assumption_version")))
            for s in scenarios)
        body.append(
            '<label class="rd-metric-label">scenario</label>'
            '<select class="rd-select" data-rd-select="scenario_id">'
            + options + "</select>"
            '<button class="rd-button" data-rd-op="sc_run"'
            ' data-rd-const-scenario_id="' + selected + '">Run</button>')
        execution = bundle.get("scenario_execution")
        if execution:
            body.append(C.table(
                ["field", "value"],
                [[k, str(v)[:120]] for k, v in execution.items()
                 if not isinstance(v, (dict, list))]))
        else:
            body.append(C.unavailable(
                "this scenario has not been run",
                "no execution is stored for it yet; Run records one"))
    else:
        body.append(C.unavailable(
            "no scenario saved yet",
            "save one below; a scenario is a labelled hypothetical and is "
            "stored with its assumptions"))

    pillars = "".join('<option value="{p}">{p}</option>'.format(p=esc(p))
                      for p in data.PILLAR_ORDER)
    body.append(
        '<p class="rd-unavail-label" style="margin-top:14px">'
        "save a rank-shock scenario</p>"
        '<input type="text" id="rd-sc-name" class="rd-input" placeholder="name"/>'
        '<select id="rd-sc-pillar" class="rd-select">' + pillars + "</select>"
        '<input type="number" id="rd-sc-delta" class="rd-input" step="0.05" value="0.1"/>'
        '<input type="number" id="rd-sc-horizon" class="rd-input" value="5"/>'
        '<input type="text" id="rd-sc-why" class="rd-input" placeholder="justification (required)"/>'
        '<button class="rd-button" data-rd-op="rd_scenario_save"'
        ' data-rd-field-name="rd-sc-name" data-rd-field-pillar="rd-sc-pillar"'
        ' data-rd-number-delta="rd-sc-delta"'
        ' data-rd-number-horizon="rd-sc-horizon"'
        ' data-rd-field-justification="rd-sc-why">Save scenario</button>'
        '<p class="rd-panel-note">A justification is required: an unlabelled '
        "hypothetical cannot be told apart from a measurement later.</p>")
    return _section("Scenarios", "T08 — labelled hypotheticals", "".join(body))


def _cases(bundle: dict, role: str, state: dict) -> str:
    if role != "regulator":
        return _section("Regulator cases", "regulator only", C.unavailable(
            "case management is a regulator tool",
            "the backend refuses these operations for this role (FR49). "
            "Switch role, top left"))
    cases = bundle.get("cases") or []
    body = []
    if cases:
        options = "".join(
            '<option value="{cid}"{sel}>{title} · {status} · v{ver}</option>'.format(
                cid=esc(c["case_id"]),
                sel=" selected" if c["case_id"] == bundle.get("case_id") else "",
                title=esc(c["title"][:40]), status=esc(c["status"]),
                ver=esc(c["version"]))
            for c in cases)
        current = next((c for c in cases
                        if c["case_id"] == bundle.get("case_id")), cases[0])
        case_id, version = esc(current["case_id"]), esc(current["version"])
        body.append(
            '<label class="rd-metric-label">case</label>'
            '<select class="rd-select" data-rd-select="case_id">'
            + options + "</select>"
            '<p class="rd-unavail-label" style="margin-top:14px">'
            "attach pinned evidence</p>"
            '<input type="text" id="rd-ev-ref" class="rd-input" value="'
            + esc(state.get("run_id")) + ":" + esc(state.get("date")) + '"/>'
            '<input type="text" id="rd-ev-rev" class="rd-input" value="1"/>'
            '<button class="rd-button" data-rd-op="rd_case_evidence"'
            ' data-rd-const-case_id="' + case_id + '"'
            ' data-rd-const-expected_version="' + version + '"'
            ' data-rd-field-ref_id="rd-ev-ref"'
            ' data-rd-field-revision="rd-ev-rev"'
            ' data-rd-const-kind="run_point">Attach</button>'
            '<p class="rd-unavail-label" style="margin-top:14px">'
            "record a decision</p>"
            '<input type="text" id="rd-dc-outcome" class="rd-input" value="soft_warning"/>'
            '<input type="text" id="rd-dc-why" class="rd-input" placeholder="rationale (required)"/>'
            '<button class="rd-button" data-rd-op="case_decision"'
            ' data-rd-const-case_id="' + case_id + '"'
            ' data-rd-const-expected_version="' + version + '"'
            ' data-rd-field-outcome="rd-dc-outcome"'
            ' data-rd-field-rationale="rd-dc-why"'
            ' data-rd-field-action_category="rd-dc-outcome">Record</button>')
    else:
        body.append(C.unavailable("no case open",
                                  "open one below against the selected alert"))
    body.append(
        '<p class="rd-unavail-label" style="margin-top:14px">'
        "open a case on this alert</p>"
        '<input type="text" id="rd-case-title" class="rd-input" placeholder="title"/>'
        '<button class="rd-button" data-rd-op="case_open"'
        ' data-rd-field-title="rd-case-title"'
        ' data-rd-const-priority="medium">Open case</button>')
    return _section("Regulator cases", "T09 — FR49 lifecycle", "".join(body))
