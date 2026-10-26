# C12 — Redesigned console: HEALTH and OPERATIONS (OPS01, C15).
"""What is stale, what is broken, and who is fetching.

Three separate services with three separate panels, because a green line in
one is not a statement about the others:

* **source and store health** — `health_surface()`. The module it reads says
  in its own docstring that "an empty dashboard with a green banner is the
  specific failure this prevents", so nothing here maps silence to health: a
  check with no data reads `never_run` or `never_succeeded`, never `ok`.
* **news acquisition** — who owns the worker, its liveness, and what each
  source actually returned. Liveness and content are different facts.
* **market jobs** — whether the market data and decisions are up to date.
  Reads a status file; never runs the jobs.

Shown to every role: this is the state of the installation, not privileged
market content.
"""
from __future__ import annotations

import streamlit as st

from . import components as C, data, news_data, tokens as T

#: Nothing maps to "ok" except `ok`. A grey or green badge for `never_run`
#: would undo the module's own rule in the one place a reader looks.
_HEALTH_TONE = {"ok": "ok", "degraded": "warn", "stale": "warn",
                "never_run": "warn", "never_succeeded": "warn",
                "failing": "bad"}

_OWNER_LABEL = {
    "dashboard": "This frontend started a supervised worker.",
    "external": "A worker was already running — started by the other "
                "frontend's launcher or by hand. This one did not start a "
                "second, which is the single-worker guarantee working.",
    "disabled": "Acquisition is switched off for this session "
                "(SERAPH_NEWS_WORKER=0).",
    "failed": "This frontend could not start a worker.",
    "exited": "The worker this frontend started has exited.",
    "not_asked": "No worker has been requested.",
}


def render(*, role: str, news_path) -> None:
    C.html_block(
        '<div class="rd-topbar"><div>'
        '<p class="rd-eyebrow">SERAPH · redesigned console</p>'
        '<h1>Health</h1>'
        '<p class="rd-panel-sub" style="margin-top:4px">'
        'what is stale, what is broken — three services, three answers</p>'
        f'</div><div class="rd-topbar-right">{C.chip("role", role)}</div></div>')

    surface = data.health_state()
    _overall(surface)
    _schedule(surface)
    _checks(surface)

    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        _acquisition(news_path)
    with right:
        _market_jobs()
        _stores(surface)


# --------------------------------------------------------------------------
def _overall(surface: dict) -> None:
    status = surface.get("status", "unknown")
    by_health = surface.get("by_health") or {}
    tone = _HEALTH_TONE.get(status, "warn")
    with C.panel("Installation health", f"as of {surface.get('at', '—')}"):
        C.html_block(C.chips([
            C.chip("worst check", str(status), tone=tone),
            C.chip("ok", str(len(by_health.get("ok") or [])), tone="ok"),
            C.chip("stale", str(len(by_health.get("stale") or [])),
                   tone="warn" if by_health.get("stale") else ""),
            C.chip("failing", str(len(by_health.get("failing") or [])),
                   tone="bad" if by_health.get("failing") else ""),
        ]))
        for problem in surface.get("problems") or ():
            st.error(problem)
        C.html_block(f'<p class="rd-panel-note">'
                     f'{C.esc(surface.get("note", ""))}</p>')


def _schedule(surface: dict) -> None:
    schedule = surface.get("schedule") or {}
    if not schedule:
        return
    with C.panel("Daily schedule", "registered, executed and acquired are "
                                   "three different facts"):
        registered = schedule.get("registered")
        if registered is True:
            C.html_block(C.chips([
                C.chip("registered", str(schedule.get("task_name")), tone="ok"),
                C.chip("runs at", f"{schedule.get('at_ist')} IST weekdays"),
                C.chip("expected session", str(schedule.get("expected_session"))),
            ]))
            for line in schedule.get("task") or ():
                C.html_block(f'<p class="rd-panel-note rd-num">{C.esc(line)}</p>')
        elif registered is False:
            C.html_block(C.unavailable(
                "not registered",
                str(schedule.get("registration_detail") or "")))
        else:
            C.html_block(C.unavailable(
                "registration not checked",
                str(schedule.get("registration_detail")
                    or "registration was not checked on this platform")))

        last = schedule.get("last_run") or {}
        if last:
            rows = [[s.get("step"), "ok" if s.get("ok") else "FAILED"]
                    for s in last.get("steps") or []]
            if rows:
                C.html_block(C.table(["step", "result"], rows))
            C.html_block(C.chips([
                C.chip("ran", "yes" if last.get("ran") else "no",
                       tone="ok" if last.get("ran") else "warn"),
                C.chip("session", str(last.get("session") or "—")),
                C.chip("generated", str(last.get("generated") or "—")),
            ]))
            if last.get("note"):
                C.html_block(f'<p class="rd-panel-note">'
                             f'{C.esc(last["note"])}</p>')

        acquired = surface.get("schedule", {}).get("data") or {}
        if acquired:
            C.html_block(
                f'<p class="rd-panel-note">Data: acquired '
                f'<b>{C.esc(acquired.get("acquired"))}</b> · currency '
                f'<b>{C.esc(acquired.get("currency"))}</b> — '
                f'{C.esc(acquired.get("detail", ""))}</p>')
        C.html_block(f'<p class="rd-panel-note">'
                     f'{C.esc(schedule.get("note", ""))}</p>')


def _checks(surface: dict) -> None:
    checks = surface.get("checks") or []
    with C.panel("Every check", "a check with no data is never ok"):
        if not checks:
            C.html_block(C.unavailable(
                "no check reported",
                "the monitoring surface returned no checks at all, which is "
                "itself a finding rather than a clean bill of health"))
            return
        order = {"failing": 0, "never_succeeded": 1, "never_run": 2,
                 "degraded": 3, "stale": 4, "ok": 5}
        rows = sorted(checks, key=lambda c: (order.get(c.get("health"), 9),
                                             c.get("name", "")))
        C.html_block(C.table(
            ["check", "kind", "health", "detail", "age (min)"],
            [[c.get("name"), c.get("kind"), c.get("health"), c.get("detail"),
              (None if c.get("age_minutes") is None
               else round(float(c["age_minutes"]), 1))]
             for c in rows], numeric_columns={4}))


def _acquisition(news_path) -> None:
    state = news_data.acquisition_state(news_path)
    owner = state.get("owner")
    with C.panel("News acquisition", "liveness only — not news content"):
        C.html_block(
            f'<p class="rd-reason"><b>'
            f'{C.esc(_OWNER_LABEL.get(owner, str(owner)))}</b></p>'
            f'<p class="rd-panel-note">{C.esc(state.get("reason", ""))}</p>')
        if not state.get("store"):
            C.html_block(C.unavailable("no news store yet",
                                       str(state.get("note") or "")))
            return
        worker = state.get("worker") or {}
        C.html_block(C.chips([
            C.chip("state", str(worker.get("state") or "unknown")),
            C.chip("activity", str(worker.get("activity") or "—")),
            C.chip("passes", str(worker.get("sequence") or "—")),
            C.chip("last beat", str(worker.get("last_beat_at") or "never")),
        ]))
        C.html_block(
            '<p class="rd-panel-note"><code>degraded</code> means the worker '
            'is polling and at least one source is failing — that is a '
            'coverage statement, not a stopped worker.</p>')

        sources = state.get("sources") or []
        failing = sum(1 for s in sources if s.get("consecutive_failures"))
        C.html_block(
            f'<p class="rd-unavail-label" style="margin-top:14px">per-source '
            f'outcomes — {failing} of {len(sources)} currently failing</p>')
        C.html_block(C.table(
            ["source", "status", "consecutive failures", "last success"],
            [[s.get("source"), s.get("status"), s.get("consecutive_failures"),
              s.get("last_success")] for s in sources],
            numeric_columns={2}))


def _market_jobs() -> None:
    state = data.market_jobs_state()
    with C.panel("Market jobs", "C15 — reads a status file, runs nothing"):
        if not state.get("ran"):
            C.html_block(C.unavailable(
                "the market jobs have not run",
                str(state.get("note") or "")))
            return
        if state.get("blocked"):
            C.html_block(C.unavailable("market jobs could not run",
                                       str(state["blocked"])))
            return
        C.html_block(C.chips([
            C.chip("last run", str(state.get("generated") or "—")),
            C.chip("session", str(state.get("session") or "—")),
        ]))
        rows = [[s.get("step"), "ok" if s.get("ok") else
                 f"FAILED — {s.get('error') or s.get('output') or ''}"]
                for s in state.get("steps") or ()]
        if rows:
            C.html_block(C.table(["step", "result"], rows))
        C.html_block(
            f'<p class="rd-panel-note">{C.esc(state.get("note", ""))} '
            f'Startup alone does not establish a connected feed or a '
            f'publishable score — the Overview\'s Current basis shows those '
            f'separately.</p>')


def _stores(surface: dict) -> None:
    stores = surface.get("stores") or {}
    paths = data.store_paths()
    with C.panel("Configured stores", "and whether they exist"):
        rows = []
        for label, path in paths.items():
            rows.append([label, str(path),
                         "present" if path.exists() else "ABSENT"])
        for label, path in stores.items():
            if label not in paths:
                rows.append([label, str(path), ""])
        C.html_block(C.table(["store", "path", "state"], rows))
        C.html_block(
            '<p class="rd-panel-note">Override with '
            '<code>SERAPH_PROTOTYPE_STORE</code>, '
            '<code>SERAPH_LIVE_STORE</code> and '
            '<code>SERAPH_NEWS_STORE</code>. Both frontends resolve these '
            'through the same function, so they always read the same '
            'stores.</p>')
