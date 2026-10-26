# C12 — Redesigned console: WORKSPACE (T05, T08, T09).
"""Portfolios, scenarios and regulator cases — the three durable workflows.

Every control here goes through `console_backend.dispatch` with the same
event shape Classic uses and the regression suite already drives. There is no
second permission table and no second persistence path: `WORKFLOW_ROLES` in
the backend decides who may invoke what, and `dispatch` re-validates the
run/date context and the role before any write.

The screen is scoped to a selected run and decision date for the same reason
Classic's is: a case is opened against *this* alert and a scenario's baseline
is *this* point. `dispatch` refuses a stale context, so the selection is part
of the operation rather than decoration around it.

A refused operation is a readable result, not a failure of the page — the
same rule the console dispatcher holds. `_send` therefore returns an error
dict rather than letting a `ValueError` or `PermissionError` replace the
whole screen.
"""
from __future__ import annotations

import json

import streamlit as st

from . import components as C, data
from seraph.shared_types import PILLAR_ORDER


def _send(archive_path, run_id, date, role, op, **args) -> dict:
    """One dispatch. A refusal comes back as `{'error': ...}`, never a crash."""
    try:
        return data.workspace_call(archive_path, run_id, date, role, op, **args)
    except (ValueError, TypeError, KeyError, PermissionError) as exc:
        return {"error": str(exc)}


def _report(outcome: dict, success: str) -> dict:
    if outcome.get("error"):
        st.warning(outcome["error"])
    else:
        st.success(success)
    return outcome


def render(*, role: str, archive_path, run_id: str | None,
           date: str | None) -> None:
    C.html_block(
        '<div class="rd-topbar"><div>'
        '<p class="rd-eyebrow">SERAPH · redesigned console</p>'
        '<h1>Workspace</h1>'
        '<p class="rd-panel-sub" style="margin-top:4px">'
        'portfolios · scenarios · regulator cases — durable state, scoped to '
        'the selected decision</p></div>'
        f'<div class="rd-topbar-right">{C.chip("role", role)}</div></div>')

    if not run_id or not date:
        with C.panel("No decision selected", "workspace"):
            C.html_block(C.unavailable(
                "a run and decision date are required",
                "every workspace operation is scoped to a decision — a case "
                "is opened against this alert, a scenario's baseline is this "
                "point — and the backend refuses a stale context",
                "choose a run and date in the sidebar, with basis set to "
                "Historical"))
        return

    def send(op, **args):
        return _send(archive_path, run_id, date, role, op, **args)

    identity = send("ws_portfolios")
    if identity.get("error"):
        with C.panel("Workspace unavailable", "durable workflows"):
            C.html_block(C.unavailable("durable workflows unavailable",
                                       identity["error"]))
        return

    C.html_block(C.chips([
        C.chip("run", run_id[:16] + "…"), C.chip("decision", date),
    ]))
    note = (identity.get("identity") or {}).get("note")
    if note:
        C.html_block(f'<p class="rd-panel-note">{C.esc(note)}</p>')

    portfolios, scenarios, cases = st.tabs(
        ["PORTFOLIOS", "SCENARIOS", "REGULATOR CASES"])
    with portfolios:
        _portfolios(send, identity, role)
    with scenarios:
        _scenarios(send, role, date)
    with cases:
        _cases(send, role, run_id, date)


# --------------------------------------------------------------------------
def _portfolios(send, identity, role) -> None:
    existing = identity.get("value") or []

    if existing:
        labels = {f"{p['name']} · {p['portfolio_id'][:12]}": p["portfolio_id"]
                  for p in existing}
        chosen = st.selectbox("Portfolio", list(labels), key="rd_wf_pf")
        pid = labels[chosen]

        held = send("ws_holdings", portfolio_id=pid)
        if held.get("error"):
            st.warning(held["error"])
            return
        held = held["value"]

        basis = st.radio("Analysis holdings basis", ["current", "historical"],
                         horizontal=True, key="rd_wf_pf_basis")
        left, right = st.columns(2)
        if left.button("Use this portfolio", key="rd_wf_pf_use",
                       use_container_width=True):
            st.session_state["rd_active_portfolio"] = dict(
                portfolio_id=pid, role=role, basis=basis)
            st.success("Active for the Overview's holdings panel.")
        if right.button("Clear active portfolio", key="rd_wf_pf_clear",
                        use_container_width=True):
            st.session_state.pop("rd_active_portfolio", None)
            st.success("Cleared.")

        C.html_block(C.chips([
            C.chip("basis", str(held.get("basis"))),
            C.chip("effective", str(held.get("effective_at") or "—")),
        ]))
        if held.get("scheduled"):
            C.html_block(
                f'<div style="margin-top:8px">'
                f'{C.chip("scheduled snapshot NOT in force", str(held["scheduled"].get("effective_at")), tone="warn")}'
                f'</div>')
        holdings = held.get("holdings") or []
        if holdings:
            keys = sorted({k for h in holdings for k in h})
            C.html_block(C.table(
                keys, [[h.get(k) for k in keys] for h in holdings],
                numeric_columns={k for k in keys
                                 if k in ("quantity", "value", "weight")}))
            C.html_block(f'<p class="rd-panel-note">total value '
                         f'<span class="rd-num">'
                         f'{C.esc(held.get("total_value"))}</span></p>')
        else:
            C.html_block(C.unavailable(
                "no holdings in force",
                str(held.get("note") or "this portfolio has no snapshot in "
                                        "force at the selected basis")))

        upload = st.file_uploader("Upload holdings (CSV or JSON)",
                                  type=["csv", "json"], key="rd_wf_up")
        body = None
        if upload is not None:
            body = upload.getvalue().decode("utf-8", errors="replace")
            preview = send("ws_preview", portfolio_id=pid, body=body,
                           source_name=upload.name)
            if preview.get("error"):
                st.warning(preview["error"])
            else:
                preview = preview["value"]
                C.html_block(C.chips([
                    C.chip("accepted", str(preview.get("accepted")), tone="ok"),
                    C.chip("rejected", str(preview.get("rejected")),
                           tone="warn" if preview.get("rejected") else ""),
                ]))
                rejected = preview.get("rejected_rows") or []
                if rejected:
                    # Actionable, not a count: "12 rows rejected" is not a
                    # result anyone can act on.
                    keys = sorted({k for r in rejected for k in r})
                    C.html_block(C.table(
                        keys, [[r.get(k) for k in keys] for r in rejected]))
                for warning in preview.get("warnings") or ():
                    st.warning(warning)

        effective = st.text_input("Effective at (IST)", value=_now_ist(),
                                  key="rd_wf_eff")
        if st.button("Save snapshot", key="rd_wf_commit") and body:
            _report(send("ws_commit", portfolio_id=pid, body=body,
                         effective_at=effective, source_name=upload.name),
                    "Saved. It will still be here after a restart.")

        with st.expander("Snapshot history"):
            snaps = send("ws_snapshots", portfolio_id=pid)
            rows = (snaps.get("value") or []) if not snaps.get("error") else []
            if rows:
                keys = sorted({k for r in rows for k in r})
                C.html_block(C.table(
                    keys, [[r.get(k) for k in keys] for r in rows]))
            else:
                C.html_block(C.unavailable(
                    "no snapshot yet",
                    "this portfolio has never had holdings committed"))
    else:
        C.html_block(C.unavailable(
            "no portfolio yet",
            "create one below; portfolios are durable and survive a restart"))

    st.divider()
    new_name = st.text_input("New portfolio name", key="rd_wf_new")
    if st.button("Create portfolio", key="rd_wf_create") and new_name.strip():
        _report(send("ws_create", name=new_name), "Created.")
        st.rerun()

    with st.expander("Watchlists"):
        items = st.text_input("Symbols, comma separated", key="rd_wf_wl")
        if st.button("Save watchlist", key="rd_wf_wlsave") and items.strip():
            _report(send("ws_watchlist_save", name="default",
                         items=[s.strip() for s in items.split(",") if s.strip()]),
                    "Watchlist saved.")
        saved = send("ws_watchlists")
        value = saved.get("value") if not saved.get("error") else None
        if value:
            st.json(value)
        else:
            C.html_block(C.unavailable("no watchlist saved",
                                       "none has been saved for this identity"))


# --------------------------------------------------------------------------
def _scenarios(send, role, date) -> None:
    if role == "retail":
        C.html_block(C.unavailable(
            "scenarios are an institutional or regulator tool",
            "the backend's WORKFLOW_ROLES table — not this screen — decides "
            "this, and it refuses the operation for retail. Switch role in "
            "the sidebar"))
        return

    listing = send("sc_list")
    if listing.get("error"):
        C.html_block(C.unavailable("scenarios unavailable", listing["error"]))
        return
    saved = listing.get("value") or []

    if saved:
        labels = {f"{s['name']} · r{s['assumption_version']} · "
                  f"{s['scenario_id'][:10]}": s["scenario_id"] for s in saved}
        chosen = st.selectbox("Scenario", list(labels), key="rd_wf_sc")
        sid = labels[chosen]

        columns = st.columns(4)
        if columns[0].button("Run", key="rd_wf_scrun", use_container_width=True):
            outcome = _report(send("sc_run", scenario_id=sid), "Ran.")
            if not outcome.get("error"):
                st.session_state["rd_scenario_execution"] = outcome["value"]

        previous = st.session_state.get("rd_scenario_execution")
        if not previous or not str(previous.get("run_key", "")).startswith(sid + ":"):
            history = send("sc_history", scenario_id=sid)
            executions = ((history.get("value") or {}).get("runs", [])
                          if not history.get("error") else [])
            previous = executions[-1] if executions else None
        if previous and str(previous.get("run_key", "")).startswith(sid + ":"):
            # The scenario renderer is Classic's, reused: it knows the shape
            # of an execution and there is no reason for a second one.
            from seraph.dashboard.scenario_ui import render_run
            render_run(previous)
        else:
            C.html_block(C.unavailable(
                "this scenario has not been run",
                "no execution is stored for it yet; Run records one"))

        verdict = columns[1].selectbox(
            "Verdict", ["approved", "changes_requested", "rejected"],
            key="rd_wf_scv", label_visibility="collapsed")
        if columns[2].button("Record review", key="rd_wf_screv",
                             use_container_width=True):
            _report(send("sc_review", scenario_id=sid, verdict=verdict),
                    "Review recorded against this exact revision.")
        export = send("sc_export", scenario_id=sid)
        if not export.get("error"):
            columns[3].download_button(
                "Export", data=json.dumps(export["value"], indent=2,
                                          default=str),
                file_name=export.get("filename", f"scenario-{sid[:8]}.json"),
                mime="application/json", key="rd_wf_scexp",
                use_container_width=True)

        with st.expander("History"):
            history = send("sc_history", scenario_id=sid)
            if history.get("error"):
                st.warning(history["error"])
            else:
                st.json(history.get("value") or {})

        if len(labels) > 1:
            other = st.selectbox("Compare with",
                                 [k for k in labels if labels[k] != sid],
                                 key="rd_wf_sccmp")
            if st.button("Compare", key="rd_wf_sccmpgo"):
                outcome = send("sc_compare", left_id=sid, right_id=labels[other])
                if outcome.get("error"):
                    st.warning(outcome["error"])
                else:
                    st.json(outcome["value"])
    else:
        C.html_block(C.unavailable(
            "no scenario saved yet",
            "save one below; a scenario is a labelled hypothetical and is "
            "stored with its assumptions"))

    # Classic's scenario forms, reused rather than reimplemented.
    from seraph.dashboard.scenario_ui import forms as scenario_forms
    with st.expander("Scenario builders"):
        scenario_forms(send, _report, point={"date": date}, role=role)

    with st.expander("Save a new rank-shock scenario"):
        name = st.text_input("Name", key="rd_wf_scname")
        pillar = st.selectbox("Pillar", list(PILLAR_ORDER), key="rd_wf_scp")
        delta = st.number_input("Rank shock", -1.0, 1.0, 0.1, 0.05,
                                key="rd_wf_scd")
        horizon = st.number_input("Horizon (sessions)", 1, 60, 5,
                                  key="rd_wf_sch")
        why = st.text_input("Justification (required)", key="rd_wf_scj")
        if st.button("Save scenario", key="rd_wf_scsave"):
            if not why.strip():
                st.warning("An assumption needs a justification: an "
                           "unlabelled hypothetical cannot be told apart "
                           "from a measurement later.")
            else:
                _report(send("sc_save", name=name, kind="rank_shock",
                             steps=[dict(pillar=pillar, delta=delta,
                                         horizon=int(horizon))],
                             assumptions=[dict(key="shock", value=delta,
                                               unit="rank", justification=why)]),
                        "Saved with its assumptions.")
                st.rerun()


# --------------------------------------------------------------------------
def _cases(send, role, run_id, date) -> None:
    if role != "regulator":
        C.html_block(C.unavailable(
            "case management is a regulator tool",
            "the backend refuses these operations for this role (FR49). "
            "Switch role in the sidebar"))
        return

    listing = send("case_list")
    if listing.get("error"):
        C.html_block(C.unavailable("cases unavailable", listing["error"]))
        return
    open_cases = listing.get("value") or []

    if open_cases:
        labels = {f"{c['title'][:40]} · {c['status']} · v{c['version']}": c
                  for c in open_cases}
        chosen = st.selectbox("Case", list(labels), key="rd_wf_case")
        case = labels[chosen]
        cid, version = case["case_id"], case["version"]
        C.html_block(C.chips([
            C.chip("case", cid[:16] + "…"),
            C.chip("status", str(case["status"])),
            C.chip("version", str(version)),
        ]))

        with st.expander("Attach pinned evidence"):
            kind = st.selectbox("Kind", ["run_point", "news_event", "story",
                                         "model_fit", "scenario"],
                                key="rd_wf_evk")
            ref = st.text_input("Reference id", key="rd_wf_evr",
                                value=f"{run_id}:{date}")
            revision = st.text_input("Revision (required)", "1",
                                     key="rd_wf_evrev")
            if st.button("Attach", key="rd_wf_evgo"):
                _report(send("case_evidence", case_id=cid,
                             expected_version=version,
                             refs=[dict(kind=kind, ref_id=ref,
                                        revision=revision)]),
                        "Evidence pinned at that revision.")
                st.rerun()

        with st.expander("Record a decision"):
            outcome = st.text_input("Outcome", "soft_warning", key="rd_wf_dco")
            rationale = st.text_area("Rationale (required)", key="rd_wf_dcr")
            if st.button("Record", key="rd_wf_dcgo"):
                _report(send("case_decision", case_id=cid,
                             expected_version=version, outcome=outcome,
                             rationale=rationale, action_category=outcome),
                        "Decision recorded.")
                st.rerun()

        with st.expander("Change status"):
            from seraph.decision_support.cases import TRANSITIONS
            allowed = TRANSITIONS.get(case["status"], ())
            if allowed:
                target = st.selectbox("To", list(allowed), key="rd_wf_stt")
                reason = st.text_input("Reason", key="rd_wf_str")
                if st.button("Apply", key="rd_wf_stgo"):
                    _report(send("case_status", case_id=cid,
                                 expected_version=version, status=target,
                                 reason=reason), f"Moved to {target}.")
                    st.rerun()
            else:
                C.html_block(C.unavailable(
                    "no transition permitted",
                    f"the case lifecycle permits no move from "
                    f"{case['status']}"))

        export = send("case_export", case_id=cid)
        if not export.get("error"):
            st.download_button(
                "Export case", data=json.dumps(export["value"], indent=2,
                                               default=str),
                file_name=export.get("filename", f"case-{cid[:8]}.json"),
                mime="application/json", key="rd_wf_caseexp")
    else:
        C.html_block(C.unavailable(
            "no case open",
            "open one below against the selected alert"))

    st.divider()
    with st.expander("Open a case on this alert", expanded=not open_cases):
        from seraph.decision_support.cases import PRIORITIES
        title = st.text_input("Title", key="rd_wf_ctitle")
        priority = st.selectbox("Priority", list(PRIORITIES), index=1,
                                key="rd_wf_cpri")
        if st.button("Open case", key="rd_wf_cgo") and title.strip():
            _report(send("case_open", title=title, priority=priority),
                    "Case opened against the selected alert.")
            st.rerun()


def _now_ist() -> str:
    from datetime import datetime
    from seraph.shared_types import IST
    return datetime.now(IST).replace(microsecond=0).isoformat()
