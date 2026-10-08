# C12 — Dashboard (FR39-FR42)
"""Renders system state at the viewer role. Contains no analytics: every
number is fetched, never computed (ARCHITECTURE §1)."""
from seraph.dashboard.gateway import ROLE_FIELDS, ROLES, build_view, redistribution_notice

__all__ = ["ROLES", "ROLE_FIELDS", "build_view", "redistribution_notice"]
