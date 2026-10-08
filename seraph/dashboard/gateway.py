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

from typing import Literal

from seraph.shared_types import (
    PILLAR_ORDER,
    ContractViolation,
    CsrsPoint,
    Err,
    Ok,
    err,
    ok,
)

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
        "institutionDecomposition": None,   # regulator-only slot; FR42
        "actionLog": action_log or [],
        "preRegistrationHash": None,
    }
    allowed = ROLE_FIELDS[role]
    payload = {k: v for k, v in full.items() if k in allowed}
    payload["role"] = role
    return ok(payload)


def redistribution_notice() -> str:
    """SPEC §7 item 14 / DATA-ACQUISITION §1 — Kite-derived data may not be
    publicly redistributed, so this dashboard is local/demo-only. Surfaced in
    the UI rather than buried in a doc, because the constraint is easy to
    forget precisely when someone is about to deploy a demo."""
    return (
        "Local/demo use only — intraday data is Kite-derived and may not be "
        "publicly redistributed (SPEC §7.14). Raise hosting with the guide first."
    )
