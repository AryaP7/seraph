# C12 — Redesigned console (FR39-FR42), presentation only.
"""A SECOND Streamlit frontend for SERAPH. Classic stays the default.

This package is additive by construction. It imports from
`seraph.dashboard.console_backend`, `.current_reader` and `.gateway` and
contains **no analytics of its own** (ARCHITECTURE §1: C12 contains no
analytics). Nothing here is imported by `prototype_app.py` or by anything
Classic loads, and nothing here edits a shared file or emits unscoped CSS, so
Classic cannot be restyled by running this.

Six screens, all built from real outputs: Overview, Forecast & early warning,
News intelligence, Workspace, Evaluation, Health. None is a placeholder.

Returning to Classic is `.\\launch_prototype.ps1`. There is nothing to revert.
"""

REDESIGN_VERSION = "c12.redesign/2026-10-25.1"

__all__ = ["REDESIGN_VERSION"]
