# product_types — the product-layer metadata envelope (PRODUCT-CONTRACTS §1)
"""Shared product vocabulary. **Not** the frozen mathematical seam.

`seraph/shared_types/` mirrors ARCHITECTURE §0/§2 and is frozen once Phase 1
lands: `Result`, `PillarEmission`, `ReconciledState`, `CsrsPoint`,
`FusionWeights`, `PILLAR_ORDER`. Product extensions never go there. This
package is the small shared vocabulary the product components (identity, news,
portfolio, scenario, case, dashboard) all speak, and it reuses the existing
`Ok`/`Err` and warning conventions at their seams rather than inventing new
ones.

The one rule everything here exists to enforce: **a number never travels
without its meaning**. Where it came from, when it was knowable, what it
covers, what unit it is in, and how sure anyone is.
"""
from seraph.product_types.envelope import (
    ENVELOPE_SCHEMA_VERSION,
    AbsenceKind,
    Coverage,
    DataStatus,
    Envelope,
    Provenance,
    SourceRef,
    Uncertainty,
    content_id,
    derived,
    estimated,
    observed,
    preview,
    scenario,
    unavailable,
)
from seraph.product_types.time import (
    InformationClock,
    ReplayBoundViolation,
    Timing,
    visible_at,
)

__all__ = [
    "ENVELOPE_SCHEMA_VERSION",
    "AbsenceKind",
    "Coverage",
    "DataStatus",
    "Envelope",
    "InformationClock",
    "Provenance",
    "ReplayBoundViolation",
    "SourceRef",
    "Timing",
    "Uncertainty",
    "content_id",
    "derived",
    "estimated",
    "observed",
    "preview",
    "scenario",
    "unavailable",
    "visible_at",
]
