# ============================================================================
#  ##  DEMO SCAFFOLDING — DELETE BEFORE ANY REAL USE  ##
#
#  EVERY NUMBER IN THIS FILE IS FABRICATED. Nothing here is derived from the
#  pipeline, from E6/E7/E8, or from any market. It exists so the interface can
#  be shown end-to-end before C5/C8/C9 are wired.
#
#  Removal (see DEMO-DELETE-ME.md at the repo root):
#     1. delete this file
#     2. delete the `demo_data` import + SERAPH_DEMO branch in datasource.py
#     3. delete DEMO-DELETE-ME.md
#  Nothing else imports it, and the real path in datasource.py is untouched, so
#  removing it cannot break the production fetch.
#
#  It is reachable ONLY with SERAPH_DEMO=1 and the page renders a permanent
#  banner while it is active. Do not make it a silent fallback: this is a risk
#  instrument, and a plausible fabricated reading is worse than an empty panel.
# ============================================================================
"""Fabricated full-coverage state for demonstrations. Not a market reading."""
from __future__ import annotations

import numpy as np

#: Fixed so a demo is identical every run — a demo that changes between takes
#: invites the audience to read meaning into the movement.
DEMO_SEED = 7            # yields CSRS 0.625, CI [0.439, 0.811], AMBER — a live-looking reading
DEMO_TS = "2026-08-21T15:30:00+05:30"


def _series(rng, n, end, vol, lo, hi):
    """A bounded random walk pinned to finish at `end`.

    Pinned deliberately: an unanchored walk drifts to its clip bound and the
    strip then contradicts the headline number sitting next to it (a CSRS
    sparkline ending at 0.05 beside a 0.625 reading). Cosmetic only.
    """
    x = np.cumsum(rng.normal(0, vol, n))
    x = x - x[-1] + end
    return np.clip(x, lo, hi)


def demo_state() -> dict:
    """A complete, fully-available SERAPH state — every value invented.

    Unlike the earlier T0 preview this runs a FULL mask (all three pillars
    present) so the degraded-mask messaging does not dominate the screen during
    a demo. That makes it look like a working system, which is the point, and
    is exactly why the DEMO banner must stay visible.
    """
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    from fixtures.mock_generator import mock_csrs_point, mock_fusion_weights
    from seraph.decision_support import explain

    rng = np.random.default_rng(DEMO_SEED)
    point = mock_csrs_point(
        _dt(2026, 8, 21, 15, 30, tzinfo=_tz(_td(hours=5, minutes=30))), rng, weights=mock_fusion_weights(seed=DEMO_SEED),
        mask=(True, True, True),          # full coverage — all pillars "reporting"
    )
    exp = explain(point)

    n = 180
    return {
        "point": point,
        "demo": True,
        "explanation": exp.value["sentence"] if exp.status == "ok" else "",
        # All three pillars present, on their own natural raw scales.
        "pillar_scores": {
            "hawkes": 0.121,      # MTS_t = n/(1-n) at n ~ 0.108
            "rmt": 0.2535,        # lambda_1/N, the Pillar 2 coupling state
            "hamilton": 1.42,     # LSD_t = xi_2 + 2*xi_3, on [0,3]
        },
        "xi": (0.21, 0.46, 0.33),
        "sector_flags": (
            {"sectorId": "steel", "flag": "amber"},
            {"sectorId": "aluminium", "flag": "amber"},
            {"sectorId": "pharmaceuticals", "flag": "none"},
            {"sectorId": "banking", "flag": "none"},
        ),
        "spectral": {
            "f_t": 0.0206, "lambda_minus": 0.142, "lambda_plus": 2.634,
            "q_t": 2.02, "n_t": 496,
        },
        # Cosmetic history for the trend strips.
        "history": {
            # Each pinned to the headline value it sits beside.
            "csrs": _series(rng, n, 0.625, 0.013, 0.05, 0.95).tolist(),
            "lam1": _series(rng, n, 0.2535, 0.0035, 0.15, 0.40).tolist(),
            "mts": _series(rng, n, 0.121, 0.005, 0.0, 0.45).tolist(),
            "lsd": _series(rng, n, 1.42, 0.045, 0.0, 3.0).tolist(),
        },
        "contagion_network": None,
    }
