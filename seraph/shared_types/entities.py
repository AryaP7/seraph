# shared_types — entity rows and store seams (SPEC §6 E1–E14; ARCHITECTURE §2 S1–S4)
"""Typed rows for every persisted entity plus the ingestion batch envelope.

Only shapes live here. DDL is C1's (`seraph/store/schema.sql`); network I/O is
C2's. Nothing in this module may import from any component package.
"""
from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, model_validator

from seraph.shared_types.core import (
    FrozenModel,
    ISODate,
    ISOTimestamp,
    RunId,
    SectorId,
    SymbolId,
)

# --- S2 read shapes / persisted rows --------------------------------------


class DailyBar(FrozenModel):
    """E3 — daily_prices (EOD2 / bhavcopy, 2005–2026, all NSE equities)."""

    symbol: SymbolId
    date: ISODate
    open: float
    high: float
    low: float
    close: float
    volume: int
    tottrdval: float          # traded value — split-invariant (SPEC E3 note)
    adj_close: float
    universe_member: bool = False   # written by C3, never C2
    listing_days_to_date: int = 0


class IntradayBar(FrozenModel):
    """E1 — intraday_bars (Kite Connect, 5-min, ~100 symbols, ~2015–2026)."""

    symbol: SymbolId
    ts: ISOTimestamp
    open: float
    high: float
    low: float
    close: float
    volume: int
    signed_volume: int = 0    # FR5, written by C4
    log_return: float = 0.0
    is_jump: bool = False     # FR50, written by C4
    jump_sign: Literal[-1, 0, 1] = 0

    @model_validator(mode="after")
    def _jump_sign_consistent(self) -> "IntradayBar":
        # jumpSign is 0 iff !isJump (ARCHITECTURE S2)
        if self.is_jump and self.jump_sign == 0:
            raise ValueError("is_jump=True requires jump_sign in {-1, +1}")
        if not self.is_jump and self.jump_sign != 0:
            raise ValueError("is_jump=False requires jump_sign == 0")
        return self


class MacroRow(FrozenModel):
    """E4 — macro_covariates (z_t). Nulls are expected (VIX pre-Nov-2007)."""

    date: ISODate
    rbi_repo_rate: float | None = None
    bank_credit_growth_yoy: float | None = None
    india_vix: float | None = None      # null before Nov 2007
    vix_available: bool = False
    inr_twi: float | None = None
    brent_price: float | None = None
    g_t: float | None = None            # FR22, written by C4
    g_t_sector_weighted: float | None = None


class MicroState(FrozenModel):
    """E2 — microstructure_state (derived by C4, not ingested)."""

    symbol: SymbolId
    ts: ISOTimestamp
    spread_ar: float | None = None      # null when undefined → warning, not error
    spread_cs: float | None = None
    amihud_illiq: float | None = None
    signed_vol_imbalance: float
    spread_quintile: Literal[1, 2, 3, 4, 5]
    imbalance_quintile: Literal[1, 2, 3, 4, 5]
    s_t: int = Field(ge=1, le=25)       # FR6 joint quintile state


class TariffEvent(FrozenModel):
    """E5 — tariff_events (hand-curated, FR4)."""

    event_id: str
    tau_k: ISODate
    delta_r_k: float
    severity_score: float               # scale undefined — SPEC [GAP]
    sectors_affected: tuple[str, ...]
    source_ref: str


class FlowAggregate(FrozenModel):
    """E14 — flow_aggregates (NSE FII/DII daily reports, FR51 → FR45)."""

    date: ISODate
    fii_net: float
    dii_net: float
    total_turnover: float
    residual_flow_share: float


class JumpEvent(FrozenModel):
    """S4 — Lee–Mykland jump event (FR50), consumed by C5."""

    symbol: SymbolId
    sector_id: SectorId
    ts: ISOTimestamp
    sign: Literal[-1, 1]
    magnitude: float
    test_statistic: float
    s_t: int = Field(ge=1, le=25)


class ObservationRow(FrozenModel):
    """S4 — y_t for the Hamilton filter (FR20)."""

    date: ISODate
    rv_yang_zhang: float
    rv_5_min: float | None = None       # null before intraday coverage
    ar_t: float                          # computed in C4, never in C6 (FR35)
    bas_t: float


# --- S3 universe ----------------------------------------------------------


class UniverseRule(FrozenModel):
    """FR52 + D3 — the rule is part of the snapshot so it is auditable."""

    min_listing_days: Literal[1000] = 1000
    rank_by: Literal["median_6m_tottrdval"] = "median_6m_tottrdval"
    take: Literal[500] = 500
    order: Literal["filter_then_rank"] = "filter_then_rank"
    buffer_incumbent_rank: Literal[550] = 550
    buffer_entrant_rank: Literal[450] = 450


class UniverseSnapshot(FrozenModel):
    """S3 — point-in-time universe at a rebalance date.

    `len(members) == 500` is the contract invariant; an underfilled universe
    must be surfaced by C3 as a UNIVERSE_UNDERFILLED warning (never silently
    shipped), so the model itself does not hard-reject a shortfall.
    """

    rebalance_date: ISODate
    members: tuple[SymbolId, ...]
    eligible_count: int
    entrants: tuple[SymbolId, ...]       # D3: churn is explicit, not inferred
    leavers: tuple[SymbolId, ...]
    churn_fraction: float
    rule: UniverseRule = UniverseRule()


# --- S1 ingestion envelope ------------------------------------------------

IngestSource = Literal[
    "eod2", "bhavcopy", "kite", "rbi", "fred", "nse-fii-dii", "tariff-manual"
]
IngestEntity = Literal["E1", "E3", "E4", "E5", "E14"]

E = TypeVar("E", bound=BaseModel)


class IngestBatch(FrozenModel, Generic[E]):
    """S1 — C2 → C1. writeBatch is idempotent on (entity, natural key)."""

    run_id: RunId
    source: IngestSource
    entity: IngestEntity
    rows: tuple[E, ...]
    watermark: ISOTimestamp
    source_schema_version: str           # "bhavcopy-legacy" | "bhavcopy-udiff" | ...


class WriteResult(FrozenModel):
    inserted: int
    updated: int
