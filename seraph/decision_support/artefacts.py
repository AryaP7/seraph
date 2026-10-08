# C11 — Decision Support (FR43–FR49)
"""The seven O10 artefacts.

Design rule throughout: **C11 translates, it does not compute risk.** Every
number it presents comes from C9/C10 or the store. The two simulators call
C9's `score()` on perturbed inputs rather than reimplementing the formula —
forking that logic is precisely what CT-7 exists to catch.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from seraph.fusion.score import score
from seraph.shared_types import (
    PILLAR_ORDER,
    ContractViolation,
    CsrsPoint,
    Err,
    FusionWeights,
    Ok,
    ReconciledState,
    SeraphWarning,
    Simplex3,
    err,
    ok,
)

#: FR46 — defensive actions, with the drawdown reduction each historically
#: delivered, keyed by the pillar that dominated the alert. These are
#: PLACEHOLDER magnitudes until C10's back-test fills them from the labelled
#: epochs; the structure is real, the numbers are not yet measured and must not
#: be reported as results.
ACTION_PLAYBOOK: dict[str, str] = {
    "hawkes": "reduce gross exposure in the flagged sectors",
    "rmt": "raise index-put overlay; diversification is failing",
    "hamilton": "extend duration / shift to cash pending regime resolution",
}

_PILLAR_PHRASE = {
    "hawkes": "self-reinforcing sell-side pressure",
    "rmt": "a breakdown in diversification across the market",
    "hamilton": "deteriorating liquidity and an unstable volatility regime",
}


def explain(point: CsrsPoint) -> Ok[dict] | Err:
    """FR44 — one-sentence, template-based explanation from the Shapley split.

    Mask-aware by construction (D2): a masked pillar carries Shapley 0, so it
    can never be named as the driver. When the mask is degraded the sentence
    says so, rather than presenting a partial reading as a complete one.
    """
    shapley = np.asarray(point.shapley, dtype=float)
    available = [i for i, m in enumerate(point.mask) if m]
    if not available:
        return err(ContractViolation(
            field="mask", detail="cannot explain a point scored on an empty mask"))
    dominant_idx = max(available, key=lambda i: shapley[i])
    dominant = PILLAR_ORDER[dominant_idx]

    level = {
        "green": "Risk is within normal range",
        "amber": "Elevated systemic risk",
        "red": "Severe systemic risk",
    }[point.alert_level]
    sentence = (
        f"{level} ({point.csrs:.2f}, 95% CI "
        f"{max(0.0, point.ci_lower):.2f}–{min(1.0, point.ci_upper):.2f}), "
        f"driven mainly by {_PILLAR_PHRASE[dominant]}."
    )
    warnings: tuple[SeraphWarning, ...] = ()
    if not all(point.mask):
        absent = [PILLAR_ORDER[i] for i, m in enumerate(point.mask) if not m]
        sentence += (
            f" Note: this reading excludes {', '.join(absent)}, which "
            f"{'is' if len(absent) == 1 else 'are'} unavailable for this period, "
            f"so it is not comparable with full-coverage readings."
        )
        warnings = (SeraphWarning(
            code="MASK_DEGRADED",
            message="explanation generated under a degraded mask",
            context={"absent": ",".join(absent)},
        ),)
    return ok({"sentence": sentence, "dominantPillar": dominant}, warnings)


def portfolio_overlay(
    holdings: "list[dict]", sector_flags: "dict[str, str]"
) -> Ok[dict] | Err:
    """FR43 — map sector micro-flags onto a user's holdings.

    `holdings` rows need `symbol`, `value` and `sector`. Exposure is reported as
    a percentage of total portfolio value, which is the number a retail holder
    can act on; naming flagged sectors without sizing them is not decision
    support.
    """
    if not holdings:
        return err(ContractViolation(field="holdings", detail="empty portfolio"))
    total = sum(float(h.get("value", 0.0)) for h in holdings)
    if total <= 0:
        return err(ContractViolation(
            field="holdings", detail="total portfolio value must be positive"))

    by_sector: dict[str, float] = {}
    for h in holdings:
        by_sector[h.get("sector", "unclassified")] = (
            by_sector.get(h.get("sector", "unclassified"), 0.0) + float(h.get("value", 0.0))
        )
    rows = [
        {
            "sectorId": sector,
            "pct": 100.0 * value / total,
            "flag": sector_flags.get(sector, "none"),
        }
        for sector, value in sorted(by_sector.items(), key=lambda kv: -kv[1])
    ]
    exposed = sum(r["pct"] for r in rows if r["flag"] == "amber")
    return ok({"exposedPct": exposed, "bySector": rows})


def flow_diagnostic(row: "dict") -> Ok[dict] | Err:
    """FR45 — market-level institutional-vs-residual flow.

    Downgraded per SPEC v2: bar data carries no counterparty tags, so this is a
    market aggregate and **must never be described as per-instrument retail
    attribution**. `residual_flow_share` is a proxy for non-institutional
    participation, not a measurement of it.
    """
    turnover = float(row.get("total_turnover", 0.0))
    if turnover <= 0:
        return err(ContractViolation(
            field="total_turnover", detail="turnover must be positive"))
    fii = float(row.get("fii_net", 0.0))
    dii = float(row.get("dii_net", 0.0))
    residual = 1.0 - (abs(fii) + abs(dii)) / turnover
    return ok({
        "fiiNet": fii,
        "diiNet": dii,
        "residualFlowShare": max(0.0, min(1.0, residual)),
        "basis": "market-level aggregate; not per-instrument attribution",
    })


def simulate_shock(
    *,
    reconciled: ReconciledState,
    xi: Simplex3,
    weights: FusionWeights,
    pillar: str,
    magnitude: float,
    horizon_days: int = 1,
    decay: float = 0.7,
) -> Ok[tuple] | Err:
    """FR47 — inject a shock into one pillar, hold the others at baseline.

    Calls C9's `score()` on a perturbed `ReconciledState`; it does not
    reimplement scoring. CT-7's requirement follows directly: at magnitude 0 the
    perturbation is the identity, so the unperturbed series is reproduced
    exactly.
    """
    if pillar not in PILLAR_ORDER:
        return err(ContractViolation(
            field="pillar", detail=f"unknown pillar {pillar!r}"))
    idx = PILLAR_ORDER.index(pillar)
    out = []
    for step in range(max(1, horizon_days)):
        bump = magnitude * (decay**step)
        x = list(reconciled.x_hat)
        x[idx] = float(np.clip(x[idx] + bump, 0.0, 1.0))
        perturbed = reconciled.model_copy(update={"x_hat": (x[0], x[1], x[2])})
        res = score(reconciled=perturbed, xi=xi, weights=weights)
        if res.status == "error":
            return res
        out.append(res.value)
    return ok(tuple(out))


def simulate_policy(
    *,
    reconciled: ReconciledState,
    weights: FusionWeights,
    z_path: "list | None" = None,
    xi_projector=None,
    xi_path: "list[Simplex3] | None" = None,
) -> Ok[tuple] | Err:
    """FR48 — counterfactual policy simulator over a hypothetical `z_t` path.

    A macro/policy path acts on the CSRS through the regime probabilities it
    implies, so the caller supplies `z_path` together with `xi_projector` —
    normally `functools.partial(project_xi, hamilton_engine)`. The projection
    itself stays in C7 because the covariate-to-regime mapping is Pillar 3's
    model; duplicating it here would create a second copy of the regime dynamics
    that could silently diverge from the live one.

    `xi_path` may be passed directly instead, for tests and for replaying a
    known regime path without a fitted engine.
    """
    if xi_path is None:
        if z_path is None or xi_projector is None:
            return err(ContractViolation(
                field="z_path",
                detail="supply z_path with an xi_projector, or an explicit xi_path",
            ))
        try:
            xi_path = list(xi_projector(z_path))
        except Exception as exc:                       # projector is caller-supplied
            return err(ContractViolation(
                field="xi_projector", detail=f"projection failed: {exc}"))
    if not xi_path:
        return err(ContractViolation(field="xi_path", detail="empty policy path"))

    out = []
    for xi in xi_path:
        res = score(reconciled=reconciled, xi=xi, weights=weights)
        if res.status == "error":
            return res
        out.append(res.value)
    return ok(tuple(out))


def playbook(dominant_pillar: str) -> Ok[dict] | Err:
    """FR46 — ranked defensive action for the dominant pillar.

    `drawdownReductionPct` is deliberately `None` until C10's epoch back-test
    supplies it. Returning a plausible-looking number here would be inventing a
    result, which is worse than returning nothing.
    """
    if dominant_pillar not in ACTION_PLAYBOOK:
        return err(ContractViolation(
            field="dominant_pillar", detail=f"unknown pillar {dominant_pillar!r}"))
    return ok({
        "action": ACTION_PLAYBOOK[dominant_pillar],
        "drawdownReductionPct": None,
        "status": "awaiting C10 back-test calibration",
    })


@dataclass
class DecisionSupport:
    """S10 — the C11 facade. Holds the regulator action log (FR49) in memory;
    persistence is C1's job via E12."""

    actions: list[dict]

    def __init__(self) -> None:
        self.actions = []

    def log_regulatory_action(
        self, *, alert_id: str, action: str, decomposition: tuple
    ) -> Ok[dict] | Err:
        """FR49 — record the regulator's response against the alert's pillar
        decomposition. Logging only: SPEC §7 item 5 puts using this log to
        recalibrate κ out of scope, and nothing here does so."""
        if action not in ("none", "soft_warning", "circuit_breaker"):
            return err(ContractViolation(
                field="action", detail=f"unknown action {action!r}"))
        entry = {
            "alertId": alert_id,
            "actionTaken": action,
            "pillarDecompositionSnapshot": tuple(float(x) for x in decomposition),
        }
        self.actions.append(entry)
        return ok(entry)

    async def persist_actions(self, pool) -> Ok[int] | Err:
        """FR49 — flush the in-memory log to E12 (regulatory_action_log).

        Idempotent on alert_id, matching C1's convention, so replaying a session
        cannot duplicate the audit trail. NFR26 requires these records be
        immutable in spirit; re-logging the same alert overwrites rather than
        appending a second, conflicting row.
        """
        import asyncpg as _asyncpg

        if not self.actions:
            return ok(0)
        try:
            async with pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO regulatory_action_log
                        (alert_id, ts, action_taken, pillar_decomposition_snapshot)
                    VALUES ($1, now(), $2, $3)
                    ON CONFLICT (alert_id) DO UPDATE SET
                        action_taken = EXCLUDED.action_taken,
                        pillar_decomposition_snapshot =
                            EXCLUDED.pillar_decomposition_snapshot
                    """,
                    [(a["alertId"], a["actionTaken"],
                      list(a["pillarDecompositionSnapshot"])) for a in self.actions],
                )
        except (OSError, _asyncpg.InterfaceError, _asyncpg.PostgresError) as exc:
            return err(ContractViolation(
                field="regulatory_action_log", detail=str(exc)))
        return ok(len(self.actions))
