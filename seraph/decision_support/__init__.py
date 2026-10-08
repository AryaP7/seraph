# C11 — Decision Support (FR43–FR49)
"""Turns scored output into role-specific, actionable artefacts.

O10's reformulation names seven deliverables. Each is implemented here as a
pure-ish function over data the rest of the system already produces — C11 adds
no analytics of its own beyond translation, and in particular **never forks the
scoring logic**: the simulators call C9's `score()` directly, which is what
CT-7 asserts (a zero-magnitude shock must reproduce the unperturbed series
exactly).

Mask-awareness is a first-class concern here, not a detail. When a pillar is
structurally absent the explanation must not attribute an alert to it, and the
portfolio overlay must not imply coverage it does not have (D2's reporting
obligation).
"""
from seraph.decision_support.artefacts import (
    ACTION_PLAYBOOK,
    DecisionSupport,
    explain,
    flow_diagnostic,
    playbook,
    portfolio_overlay,
    simulate_policy,
    simulate_shock,
)

__all__ = [
    "ACTION_PLAYBOOK",
    "DecisionSupport",
    "explain",
    "flow_diagnostic",
    "playbook",
    "portfolio_overlay",
    "simulate_policy",
    "simulate_shock",
]
