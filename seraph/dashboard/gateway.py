# C12 — Dashboard (FR39–FR42): the RBAC gateway.
"""Role-scoped payload assembly. **RBAC is enforced here, at the transport
boundary — never in the view layer.**

CT-8's requirement is precise and worth restating: a retail payload must not
merely *hide* institution-level fields, it must not *contain* them. Anything
serialised to the client is reachable by the client, so filtering in a template
or with a CSS rule is not access control at all. Every role's payload is built
by construction from that role's allowed field set.

C12 contains no analytics (ARCHITECTURE §1). Every number here is fetched from
C9/C10/C11 or the store; a chart needing a value no component produces is a
missing FR, not a dashboard feature.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from seraph.shared_types import (
    PILLAR_ORDER,
    ContractViolation,
    CsrsPoint,
    Err,
    Ok,
    err,
    ok,
)

if TYPE_CHECKING:          # C12 → C11 is the documented direction (ARCHITECTURE §3)
    from seraph.decision_support import RegulatoryActionLog

Role = Literal["retail", "institutional", "regulator"]
ROLES: tuple[Role, ...] = ("retail", "institutional", "regulator")

#: Fields each role may receive. Cumulative by design: a regulator sees
#: everything an institution does, and so on. Retail deliberately receives no
#: raw pillar decomposition — NFR22 requires comprehensibility without a
#: quantitative-finance background, and a Shapley vector is not that.
_RETAIL_FIELDS = frozenset({
    "ts", "alertLevel", "csrs", "ciLower", "ciUpper", "variance",
    "explanation", "maskDegraded", "portfolioExposurePct",
})
_INSTITUTIONAL_FIELDS = _RETAIL_FIELDS | frozenset({
    "shapley", "pillarScores", "regimeProbabilities", "sectorFlags",
    "effectiveWeights", "reconciliationMode", "spectral", "playbook",
})
_REGULATOR_FIELDS = _INSTITUTIONAL_FIELDS | frozenset({
    "weightsArtefactId", "contagionNetwork", "institutionDecomposition",
    "actionLog", "preRegistrationHash",
})

ROLE_FIELDS: dict[str, frozenset[str]] = {
    "retail": _RETAIL_FIELDS,
    "institutional": _INSTITUTIONAL_FIELDS,
    "regulator": _REGULATOR_FIELDS,
}


def build_view(
    role: str,
    point: CsrsPoint,
    *,
    explanation: str = "",
    pillar_scores: dict | None = None,
    regime_probabilities: tuple | None = None,
    sector_flags: tuple = (),
    spectral: dict | None = None,
    contagion_network: dict | None = None,
    portfolio_exposure_pct: float | None = None,
    action_log: list | None = None,
    playbook: dict | None = None,
    institution_decomposition: dict | None = None,
) -> Ok[dict] | Err:
    """Assemble the payload for `role`, containing only that role's fields.

    The full record is built first and then *projected* onto the role's allowed
    set, so adding a new field defaults to invisible rather than defaulting to
    leaked — the safe direction for an access-control boundary.
    """
    if role not in ROLE_FIELDS:
        return err(ContractViolation(field="role", detail=f"unknown role {role!r}"))

    full = {
        "ts": point.ts,
        "alertLevel": point.alert_level,
        "csrs": point.csrs,
        "ciLower": max(0.0, point.ci_lower),
        "ciUpper": min(1.0, point.ci_upper),
        "variance": point.variance,
        "explanation": explanation,
        # D2 reporting obligation: a degraded reading is labelled for every
        # role, including retail. Hiding it from the least expert audience
        # would be exactly backwards.
        "maskDegraded": not all(point.mask),
        "portfolioExposurePct": portfolio_exposure_pct,
        "shapley": dict(zip(PILLAR_ORDER, point.shapley)),
        "pillarScores": pillar_scores or {},
        "regimeProbabilities": regime_probabilities,
        "sectorFlags": sector_flags,
        "effectiveWeights": point.effective_weights,
        "reconciliationMode": point.reconciliation_mode,
        "spectral": spectral or {},
        "playbook": playbook,
        "weightsArtefactId": point.weights_artefact_id,
        "contagionNetwork": contagion_network,
        "institutionDecomposition": institution_decomposition,
        "actionLog": action_log or [],
        "preRegistrationHash": None,
    }
    allowed = ROLE_FIELDS[role]
    payload = {k: v for k, v in full.items() if k in allowed}
    payload["role"] = role
    return ok(payload)


# --- FR49 action-log authorization ----------------------------------------
# C11 owns the log itself (E12); C12 owns who may touch it. The split is forced
# by ARCHITECTURE §3's C12 → C11 direction, and is the right one regardless:
# the transport boundary is where access control belongs (FR42), for the same
# reason CT-8 insists a hidden field is not a withheld field.

ActionLogOp = Literal["create", "read", "update", "delete"]
ACTION_LOG_OPS: tuple[ActionLogOp, ...] = ("create", "read", "update", "delete")

#: The field-level grant that governs *seeing* the log. Already present in
#: `_REGULATOR_FIELDS` above — this names it rather than restating the policy.
_ACTION_LOG_FIELD = "actionLog"
_ACTION_LOG_MUTATIONS: frozenset[str] = frozenset({"create", "update", "delete"})


def action_log_permissions(role: str) -> frozenset[ActionLogOp]:
    """Which FR49 operations `role` may perform.

    Derived from `ROLE_FIELDS` rather than declared a second time: a parallel
    permission table is a thing that drifts, and the drift would be silent.
    Reading requires the field-level grant — the CT-8 principle, that a role
    which may not receive a field may not fetch it either. Mutating requires
    the regulator role on top, so granting some other role visibility later
    cannot quietly hand it write access; FR49 records *the regulator's* action.
    """
    if _ACTION_LOG_FIELD not in ROLE_FIELDS.get(role, frozenset()):
        return frozenset()
    ops = {"read"}
    if role == "regulator":
        ops |= _ACTION_LOG_MUTATIONS
    return frozenset(ops)                      # type: ignore[arg-type]


def authorize_action_log(role: str, op: str) -> Ok[ActionLogOp] | Err:
    """Gate one FR49 operation.

    Denials come back as `CONTRACT_VIOLATION` on `role`, matching how
    `build_view` rejects an unknown role. `SeraphError` (ARCHITECTURE §0) has
    no `Forbidden` variant and AGENTS.md §6 forbids inventing an ad hoc kind,
    so adding one is a shared_types proposal rather than something to slip in
    here.
    """
    if role not in ROLE_FIELDS:
        return err(ContractViolation(field="role", detail=f"unknown role {role!r}"))
    if op not in ACTION_LOG_OPS:
        return err(ContractViolation(
            field="operation", detail=f"unknown action-log operation {op!r}"))
    if op not in action_log_permissions(role):
        return err(ContractViolation(
            field="role",
            detail=f"role {role!r} may not {op} the regulator action log (FR49)"))
    return ok(op)                              # type: ignore[arg-type]


def action_log_request(
    role: str,
    op: str,
    log: "RegulatoryActionLog",
    *,
    alert_id: str | None = None,
    action: str | None = None,
    decomposition: tuple | None = None,
    at: str | None = None,
    include_retracted: bool = False,
) -> Ok | Err:
    """Authorize, then perform, one FR49 operation against C11's log.

    Authorization resolves before any side effect, so a denied mutation leaves
    the log and its journal untouched. The authorised role is handed to C11 as
    the `actor` its audit journal records (NFR26) — eventually the OAuth2
    subject NFR25 specifies, which this signature will not have to change to
    accommodate.
    """
    auth = authorize_action_log(role, op)
    if auth.status == "error":
        return auth

    if op == "read":
        if alert_id is None:
            return ok(log.payload(include_retracted=include_retracted))
        found = log.read(alert_id, include_retracted=include_retracted)
        if found.status == "error":
            return found
        return ok(found.value.model_dump(by_alias=True))

    if alert_id is None:
        return err(ContractViolation(
            field="alert_id", detail=f"{op} needs an alert_id"))
    if op == "delete":
        res = log.delete(alert_id=alert_id, actor=role)
    elif action is None:
        return err(ContractViolation(
            field="action", detail=f"{op} needs an action"))
    elif op == "create":
        if decomposition is None:
            return err(ContractViolation(
                field="decomposition",
                detail="create needs the alert's pillar decomposition snapshot"))
        res = log.create(alert_id=alert_id, action=action,
                         decomposition=decomposition, actor=role, at=at)
    else:
        res = log.update(alert_id=alert_id, action=action, actor=role,
                         decomposition=decomposition)
    if res.status == "error":
        return res
    return ok(res.value.model_dump(by_alias=True), res.warnings)


def redistribution_notice() -> str:
    """SPEC §7 item 14 / DATA-ACQUISITION §1 — Kite-derived data may not be
    publicly redistributed, so this dashboard is local/demo-only. Surfaced in
    the UI rather than buried in a doc, because the constraint is easy to
    forget precisely when someone is about to deploy a demo."""
    return (
        "Local/demo use only — intraday data is Kite-derived and may not be "
        "publicly redistributed (SPEC §7.14). Raise hosting with the guide first."
    )
