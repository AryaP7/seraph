# C12 — Redesigned console: the read adapter (FR39-FR42).
"""Everything the redesigned frontend knows, read through the EXISTING paths.

**No new pipeline, no second engine.** Every number on the redesigned screen
comes from a call that Classic already makes:

| what | call | owner |
|---|---|---|
| the projected decision payload | `console_backend.project_run` | C12 |
| the live runtime read | `current_reader.read_current` / `revision` | C12 |
| the forecast and warning state | `console_backend.prediction_surface` | C12 → C? |
| source / store health | `console_backend.health_surface` | C12 |
| store locations | `prototype_app.store_paths` | C12 |

`store_paths` is **imported**, not reimplemented: it resolves
`SERAPH_PROTOTYPE_STORE` / `SERAPH_LIVE_STORE` / `SERAPH_NEWS_STORE`, and a
second copy of that logic here is exactly the divergence this package is
supposed to avoid. Importing it is also what makes the two frontends read the
same stores on a machine where those variables are set.

`project_run` applies the C12 RBAC projection (`gateway.ROLE_FIELDS`) before
anything reaches this module, so a field a role may not receive is absent
here too — this adapter cannot widen a role's view because it never sees the
unprojected record.

This module contains no analytics (ARCHITECTURE §1) and does not import C10.
"""
from __future__ import annotations

from pathlib import Path

from seraph.dashboard.console_backend import (
    dispatch,
    experiment_surface,
    health_surface,
    prediction_surface,
    project_run,
)
from seraph.dashboard.current_reader import VIEW_MODES, read_current, revision
from seraph.dashboard.gateway import ROLE_FIELDS
from seraph.dashboard.prototype_app import store_paths
from seraph.live.store import LiveStore
from seraph.orchestration.run_store import RunStore
from seraph.shared_types import PILLAR_ORDER

__all__ = [
    "VIEW_MODES", "PILLAR_ORDER", "store_paths", "complete_runs",
    "run_bundle", "archive_decision", "live_decision", "forecast_state",
    "health_state", "live_revision", "pillar_rows", "contribution_rows",
    "weight_rows", "composite_of", "evaluation_state",
    "resolve_active_portfolio",
    "market_jobs_state", "workspace_call",
]


# --------------------------------------------------------------------------
# archive side
# --------------------------------------------------------------------------
def complete_runs(archive_path) -> list[dict]:
    """Complete runs only — a sealed run awaiting its report is not one.

    Same rule as Classic's `_complete_runs`; stated here rather than imported
    because Classic's copy is a Streamlit-cached function and this one is
    called from tests that have no Streamlit runtime.
    """
    path = Path(archive_path)
    if not path.exists():
        return []
    return [r for r in RunStore(str(path)).runs() if r["status"] == "complete"]


def run_bundle(archive_path, run_id: str, role: str) -> dict:
    """The coherent run bundle — points, report, action log — for one role.

    The action log is read only for the role allowed to see it, so a cached
    regulator bundle can never be served into a retail render.
    """
    store = RunStore(str(archive_path))
    return dict(
        points=store.points(run_id),
        report=store.report(run_id) if role != "retail" else None,
        log=(store.action_log(run_id).payload(include_retracted=True)
             if role == "regulator" else None),
    )


def resolve_active_portfolio(selection: dict | None, role: str, *, at: str,
                             flags=None) -> dict:
    """Saved holdings and their overlay, for the portfolio the user activated.

    Reuses `workspace_service.active_portfolio` — the same resolver Classic
    calls — so holdings reach the decision payload through one path. It
    raises when the selection belongs to another role, which is a refusal to
    show one role's holdings under another, not an error to swallow: the
    caller surfaces it and drops the selection.

    Returns `{available, holdings, overlay, context, note, reason}`.
    """
    if not selection:
        return dict(available=False, holdings=None, overlay=None,
                    context=None, note="", reason="")
    from seraph.dashboard.workspace_service import active_portfolio

    try:
        resolved = active_portfolio(selection, role, at=at, flags=flags or {})
    except (ValueError, PermissionError, KeyError) as exc:
        return dict(available=False, holdings=None, overlay=None,
                    context=None, note="", reason=str(exc))
    return dict(available=True, holdings=resolved["holdings"],
                overlay=resolved["overlay"], context=resolved["context"],
                note=resolved["note"], reason="")


def archive_decision(archive_path, run_id: str, date: str, role: str,
                     **kwargs) -> dict:
    """One historical decision, projected exactly as Classic projects it.

    Returns `{available, payload, point, manifest, points, reason}`. An
    archive decision is a **replay** by construction; `payload['liveness']`
    carries that judgement and the caller must render it, never soften it.
    """
    runs = complete_runs(archive_path)
    match = next((r for r in runs if r["id"] == run_id), None)
    if match is None:
        return dict(available=False, payload=None, point=None, manifest=None,
                    points=[], reason=f"no complete run {run_id!r} in this store")
    bundle = run_bundle(archive_path, run_id, role)
    points = bundle["points"]
    point = next((p for p in points if p["date"] == date), None)
    if point is None:
        return dict(available=False, payload=None, point=None,
                    manifest=match["manifest"], points=points,
                    reason=f"run {run_id[:12]} has no decision dated {date}")
    payload = project_run(point, match["manifest"], points, role,
                          log=bundle["log"], report=bundle["report"], **kwargs)
    return dict(available=True, payload=payload, point=point,
                manifest=match["manifest"], points=points, reason="")


# --------------------------------------------------------------------------
# live side
# --------------------------------------------------------------------------
def live_decision(live_path, mode: str = "live") -> dict:
    """What the runtime has actually committed in `mode`, or why nothing has.

    There is no fallback between modes here and there must never be one:
    `read_current` refuses to serve an archive run when asked for `live`,
    because an archive run is a replay and would be mislabelled.
    """
    path = Path(live_path)
    if not path.exists():
        return dict(connected=False, available=False, payload=None,
                    reason=(f"no live runtime store at {path}. "
                            f"`python scripts/run_live.py --status` reports "
                            f"what the runtime would do; this reads what it "
                            f"has committed"),
                    health=None, mode=mode)
    current = read_current(LiveStore(path), mode=mode)
    described = current.describe()
    return dict(connected=True,
                available=current.decision_id is not None,
                payload=current.payload, reason=current.reason,
                health=described["health"], mode=mode,
                decision_id=current.decision_id, as_of=current.as_of,
                computed_at=current.computed_at,
                publication_state=current.publication_state,
                is_current=current.is_current,
                age_seconds=current.age_seconds)


def live_revision(live_path) -> str | None:
    """A cheap id that moves exactly when the live screen's content moves."""
    path = Path(live_path)
    return revision(LiveStore(path)) if path.exists() else None


# --------------------------------------------------------------------------
# cross-cutting surfaces
# --------------------------------------------------------------------------
def forecast_state() -> dict:
    """`prediction_surface()` — reads the saved state, never fits."""
    return prediction_surface()


def health_state() -> dict:
    """`health_surface()` — source/store/schedule health."""
    return health_surface()


def evaluation_state(role: str) -> dict:
    """`experiment_surface(role)` — the FR35 ablation, read-only.

    Read-only is not a simplification: D5(d) makes a committed pre-registered
    design the precondition for any AUC, and committing it is left to a
    person so it cannot happen as a side effect of opening a page. This
    adapter therefore exposes no commit and no run call, exactly as Classic's
    panel does.
    """
    return experiment_surface(role=role)


def market_jobs_state() -> dict:
    """What the market side of startup achieved (C15). Reads a status file.

    Never runs the jobs: a page render that triggered a two-minute RMT
    estimate would make every refresh a cliff.
    """
    from seraph.operations.market_jobs_status import read_status
    return read_status()


# --------------------------------------------------------------------------
# durable workflows (T05/T08/T09)
# --------------------------------------------------------------------------
def workspace_call(archive_path, run_id: str, date: str, role: str, op: str,
                   **args) -> dict:
    """One durable-workflow operation, through the SAME `dispatch` as Classic.

    Not a parallel implementation: `console_backend.dispatch` re-validates the
    UI context and the role permission before any computation or write, and
    `WORKFLOW_ROLES` there — not this module — decides who may invoke what. A
    second permission table here would be a thing that drifts, and the drift
    would be silent.

    The request id must be unique per call: `CaseStore` dedupes on it, so a
    reused id makes the second distinct change a silent no-op.
    """
    import uuid

    store = RunStore(str(archive_path))
    point = next((p for p in store.points(run_id) if p["date"] == date), None)
    if point is None:
        raise ValueError(f"run {run_id[:12]} has no decision dated {date}")
    event = dict(id=f"rd-{op}-{uuid.uuid4().hex[:12]}",
                 run_id=run_id, date=date, op=op, **args)
    return dispatch(store, point, role, event)


# --------------------------------------------------------------------------
# shaping, not computing
# --------------------------------------------------------------------------
def composite_of(payload: dict | None) -> dict:
    """The dial's inputs from a projected payload, or an explicit absence.

    Accepts both shapes the console has to absorb: the `view` dict a
    `project_run` payload carries, and the bare `csrs` body a live decision
    carries. Returns `value=None` plus a reason whenever there is no numeric
    score — this function has no branch that returns 0.0 for a missing score.
    """
    if not payload:
        return dict(value=None, ci_lower=None, ci_upper=None, alert_level=None,
                    variance=None, mask_degraded=None,
                    reason="no decision payload was supplied")
    view = payload.get("view") if isinstance(payload.get("view"), dict) else payload
    body = view.get("csrs")
    if isinstance(body, dict):                 # a raw CsrsPoint dump
        value = body.get("csrs")
        return dict(value=value if _num(value) else None,
                    ci_lower=body.get("ci_lower"), ci_upper=body.get("ci_upper"),
                    alert_level=body.get("alert_level"),
                    variance=body.get("variance"),
                    mask_degraded=(not all(body["mask"])
                                   if isinstance(body.get("mask"), (list, tuple))
                                   else None),
                    reason="" if _num(value) else
                           "this decision carries no numeric CSRS")
    if _num(body):
        return dict(value=float(body), ci_lower=view.get("ciLower"),
                    ci_upper=view.get("ciUpper"),
                    alert_level=view.get("alertLevel"),
                    variance=view.get("variance"),
                    mask_degraded=view.get("maskDegraded"), reason="")
    return dict(value=None, ci_lower=None, ci_upper=None,
                alert_level=view.get("alertLevel"), variance=None,
                mask_degraded=view.get("maskDegraded"),
                reason=(view.get("explanation")
                        or "no composite: original inputs unavailable"))


def pillar_rows(payload: dict | None) -> list[dict]:
    """One row per pillar in `PILLAR_ORDER`, absence carried as absence.

    `PILLAR_ORDER` is iterated rather than the payload's key order: the mask
    and every `Vec3` in the system are positional, so reading them against
    whatever order a dict happened to serialise in is how a CSRS gets
    silently misattributed.

    `score_eligible: False` with `value: None` is the engine declaring a
    pillar it did not score — a *structural* statement that travels with its
    own reason. It is never rewritten as 0.

    `withheld` is the fourth state and it matters: at `retail`,
    `pillarScores` is not in `ROLE_FIELDS` and `build_view` never puts it in
    the payload. The engine emitted a reading; the transport boundary removed
    it. Reporting that as "the pillar emitted nothing" would be a false
    statement about the model, so the flag is derived from `ROLE_FIELDS` —
    read from the gateway, never restated here, so the two cannot drift.
    """
    view = (payload or {}).get("view") or {}
    scores = view.get("pillarScores") or (payload or {}).get("pillars") or {}
    role = view.get("role") or (payload or {}).get("role")
    withheld = (not scores
                and role in ROLE_FIELDS
                and "pillarScores" not in ROLE_FIELDS[role])
    mask = (payload or {}).get("mask")
    if not isinstance(mask, (list, tuple)) or len(mask) != len(PILLAR_ORDER):
        mask = [None] * len(PILLAR_ORDER)
    rows = []
    for i, name in enumerate(PILLAR_ORDER):
        entry = scores.get(name) or {}
        value = entry.get("value")
        rows.append(dict(
            name=name,
            value=value if _num(value) else None,
            eligible=entry.get("score_eligible"),
            in_mask=mask[i],
            model=entry.get("model"),
            origin=entry.get("origin"),
            reason=entry.get("reason"),
            information_timestamp=entry.get("information_timestamp"),
            detail=entry.get("detail") or {},
            present=bool(entry),
            withheld=withheld,
            role=role,
        ))
    return rows


def contribution_rows(payload: dict | None) -> list[dict]:
    """Per-pillar Shapley contributions, in `PILLAR_ORDER`.

    Signed, and summing to the CSRS rather than to 1. The caller renders them
    on a symmetric axis in score units; nothing here normalises them.

    `excluded` marks a pillar the D2 mask kept out of the composite. Its
    Shapley is exactly 0.0 — and that zero is *by construction*, not a
    measurement that happened to come out at nought. The two are different
    claims, so the flag travels with the row and the renderer draws them
    differently. Collapsing them would tell a reader the pillar was consulted
    and found to contribute nothing.
    """
    view = (payload or {}).get("view") or {}
    shapley = view.get("shapley")
    rows = pillar_rows(payload)
    out = []
    for row in rows:
        name = row["name"]
        if isinstance(shapley, dict):
            value = shapley.get(name)
        elif isinstance(shapley, (list, tuple)) and len(shapley) == len(PILLAR_ORDER):
            value = shapley[PILLAR_ORDER.index(name)]
        else:
            value = None
        out.append(dict(
            name=name,
            value=float(value) if _num(value) else None,
            excluded=row["in_mask"] is False,
            missing_reason=(row["reason"] or "this role's payload carries no "
                            "Shapley decomposition"),
        ))
    return out


def weight_rows(payload: dict | None) -> list[dict]:
    """D2 effective weights, in `PILLAR_ORDER`.

    `effectiveWeights` arrives as `Mat3` (one weight vector per reconciliation
    row). The diagonal-free truth is that every row of the matrix is the same
    weight vector in the current engine, so the first row is taken and the
    caller is told that is what it is.
    """
    view = (payload or {}).get("view") or {}
    weights = view.get("effectiveWeights")
    vector = None
    if isinstance(weights, (list, tuple)) and weights:
        head = weights[0]
        if isinstance(head, (list, tuple)) and len(head) == len(PILLAR_ORDER):
            vector = head
        elif all(_num(w) for w in weights) and len(weights) == len(PILLAR_ORDER):
            vector = weights
    return [dict(name=name,
                 value=float(vector[i]) if vector and _num(vector[i]) else None)
            for i, name in enumerate(PILLAR_ORDER)]


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)
