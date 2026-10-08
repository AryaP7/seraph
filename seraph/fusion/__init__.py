# C9 — Fusion Engine (FR28, FR29, FR31)
"""Scores a reconciled pillar vector into a CSRS, given a fixed FusionWeights
artefact (produced by C10, consumed here — D1's one-directional flow). The
scoring path is a pure function: no I/O, no hidden state, no dependence on
C10's package."""
from seraph.fusion.masking import renormalize_masked
from seraph.fusion.score import PROVISIONAL_AMBER, PROVISIONAL_RED, score
from seraph.fusion.shapley import exact_shapley
from seraph.fusion.standardize import ECDF_WINDOW_YEARS, ecdf_transform

__all__ = [
    "ECDF_WINDOW_YEARS",
    "PROVISIONAL_AMBER",
    "PROVISIONAL_RED",
    "ecdf_transform",
    "exact_shapley",
    "renormalize_masked",
    "score",
]
