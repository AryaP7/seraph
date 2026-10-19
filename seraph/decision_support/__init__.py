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

Two artefacts carry enough of their own rules to own a module, and neither
imports the other, so each is testable on its own:

* `portfolio.py` — FR43, the portfolio overlay and its exposure arithmetic,
  plus the flag-source adapters. Pure; no I/O.
* `portfolio_io.py` — FR43's E11 read path (S10's `portfolioOverlay(userId,
  at)`). The only module here that touches a database, which is what keeps
  `portfolio.py` testable in isolation.
* `action_log.py` — FR49, the regulator action log, its CRUD and its audit
  journal. Authorization for it lives in C12's gateway, since ARCHITECTURE §3
  fixes the dependency direction C12 → C11.
"""
from seraph.decision_support.action_log import (
    ACTIONS_TAKEN,
    ActionLogEntry,
    ActionLogJournalRecord,
    ActionTaken,
    DecisionSupport,
    RegulatoryActionLog,
)
from seraph.decision_support.artefacts import (
    ACTION_PLAYBOOK,
    explain,
    flow_diagnostic,
    playbook,
    simulate_policy,
    simulate_shock,
)
from seraph.decision_support.portfolio import (
    MICRO_FLAGS,
    UNCLASSIFIED,
    MicroFlag,
    PortfolioHolding,
    measured_flag_source,
    normalise_flag_source,
    portfolio_overlay,
)
from seraph.decision_support.portfolio_io import (
    portfolio_overlay_for_user,
    read_user_portfolio,
)

__all__ = [
    "ACTIONS_TAKEN",
    "ACTION_PLAYBOOK",
    "ActionLogEntry",
    "ActionLogJournalRecord",
    "ActionTaken",
    "DecisionSupport",
    "MICRO_FLAGS",
    "MicroFlag",
    "PortfolioHolding",
    "RegulatoryActionLog",
    "UNCLASSIFIED",
    "explain",
    "flow_diagnostic",
    "measured_flag_source",
    "normalise_flag_source",
    "playbook",
    "portfolio_overlay",
    "portfolio_overlay_for_user",
    "read_user_portfolio",
    "simulate_policy",
    "simulate_shock",
]
