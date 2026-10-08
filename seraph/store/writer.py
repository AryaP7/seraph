# C1 — Store & Schema (FR8, FR38): StoreWriter — S1, idempotent on (entity, natural key).
"""Idempotency is a hard requirement, not an optimisation (CT-1): NSE sources
fail often and ingestion is re-run after every failure. Upserts are
`INSERT … ON CONFLICT DO UPDATE` keyed on the natural key; re-running an
identical batch reports `inserted: 0` and leaves the watermark unchanged.

Errors are returned as `Err`, never raised across the component boundary
(AGENTS.md §5)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import asyncpg
from pydantic import BaseModel

from seraph.shared_types import (
    ContractViolation,
    DailyBar,
    Err,
    FlowAggregate,
    IngestBatch,
    IntradayBar,
    MacroRow,
    Ok,
    SeraphWarning,
    SourceUnavailable,
    TariffEvent,
    WriteResult,
    err,
    ist_timestamp,
    ok,
)
from seraph.store.bootstrap import resolve_dsn


@dataclass(frozen=True)
class _EntitySpec:
    table: str
    key: tuple[str, ...]                 # column names forming the natural key
    columns: dict[str, str]              # model field -> column name
    model: type[BaseModel]
    date_fields: frozenset[str]          # model fields parsed to datetime.date
    ts_fields: frozenset[str]            # model fields parsed to aware datetime


_REGISTRY: dict[str, _EntitySpec] = {
    "E1": _EntitySpec(
        table="intraday_bars",
        key=("symbol", "ts"),
        columns={
            "symbol": "symbol", "ts": "ts", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
            "signed_volume": "signed_volume", "log_return": "log_return",
            "is_jump": "is_jump", "jump_sign": "jump_sign",
        },
        model=IntradayBar,
        date_fields=frozenset(),
        ts_fields=frozenset({"ts"}),
    ),
    "E3": _EntitySpec(
        table="daily_prices",
        key=("symbol", "date"),
        columns={
            "symbol": "symbol", "date": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
            "tottrdval": "tottrdval", "adj_close": "adj_close",
            "universe_member": "universe_member_flag",
            "listing_days_to_date": "listing_days_to_date",
        },
        model=DailyBar,
        date_fields=frozenset({"date"}),
        ts_fields=frozenset(),
    ),
    "E4": _EntitySpec(
        table="macro_covariates",
        key=("date",),
        columns={
            "date": "date", "rbi_repo_rate": "rbi_repo_rate",
            "bank_credit_growth_yoy": "bank_credit_growth_yoy",
            "india_vix": "india_vix", "vix_available": "vix_available",
            "inr_twi": "inr_twi", "brent_price": "brent_price",
            "g_t": "g_t", "g_t_sector_weighted": "g_t_sector_weighted",
        },
        model=MacroRow,
        date_fields=frozenset({"date"}),
        ts_fields=frozenset(),
    ),
    "E5": _EntitySpec(
        table="tariff_events",
        key=("event_id",),
        columns={
            "event_id": "event_id", "tau_k": "tau_k", "delta_r_k": "delta_r_k",
            "severity_score": "severity_score",
            "sectors_affected": "sectors_affected", "source_ref": "source_ref",
        },
        model=TariffEvent,
        date_fields=frozenset({"tau_k"}),
        ts_fields=frozenset(),
    ),
    "E14": _EntitySpec(
        table="flow_aggregates",
        key=("date",),
        columns={
            "date": "date", "fii_net": "fii_net", "dii_net": "dii_net",
            "total_turnover": "total_turnover",
            "residual_flow_share": "residual_flow_share",
        },
        model=FlowAggregate,
        date_fields=frozenset({"date"}),
        ts_fields=frozenset(),
    ),
}


def _upsert_sql(spec: _EntitySpec) -> str:
    cols = list(spec.columns.values())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    non_key = [c for c in cols if c not in spec.key]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_key)
    return (
        f"INSERT INTO {spec.table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT ({', '.join(spec.key)}) DO UPDATE SET {set_clause} "
        f"RETURNING (xmax = 0) AS inserted"
    )


def _row_params(spec: _EntitySpec, row: BaseModel) -> list:
    data = row.model_dump()
    params = []
    for field in spec.columns:
        v = data[field]
        if field in spec.date_fields and isinstance(v, str):
            v = date.fromisoformat(v)
        elif field in spec.ts_fields and isinstance(v, str):
            v = datetime.fromisoformat(v)
        elif isinstance(v, tuple):
            v = list(v)
        params.append(v)
    return params


class StoreWriter:
    """S1 — the only write path for ingestion entities (E1/E3/E4/E5/E14)."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str | None = None) -> "StoreWriter":
        pool = await asyncpg.create_pool(resolve_dsn(dsn), min_size=1, max_size=4)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def write_batch(self, batch: IngestBatch) -> Ok[WriteResult] | Err:
        spec = _REGISTRY.get(batch.entity)
        if spec is None:
            return err(ContractViolation(
                field="entity",
                detail=f"no writer registered for entity {batch.entity!r}",
            ))
        for row in batch.rows:
            if not isinstance(row, spec.model):
                return err(ContractViolation(
                    field="rows",
                    detail=(
                        f"entity {batch.entity} expects {spec.model.__name__} rows, "
                        f"got {type(row).__name__}"
                    ),
                ))

        warnings: tuple[SeraphWarning, ...] = ()
        if batch.source_schema_version == "bhavcopy-legacy":
            # Legacy pre-July-2024 bhavcopy schema is expected input, not a
            # failure (CT-1 negative case).
            warnings = (SeraphWarning(
                code="SOURCE_SCHEMA_LEGACY",
                message="batch normalised from the legacy (pre-UDiFF) bhavcopy schema",
                context={"source": batch.source, "runId": batch.run_id},
            ),)

        sql = _upsert_sql(spec)
        inserted = updated = 0
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    stmt = await conn.prepare(sql)
                    for row in batch.rows:
                        was_insert = await stmt.fetchval(*_row_params(spec, row))
                        if was_insert:
                            inserted += 1
                        else:
                            updated += 1
                    # Watermark only ever advances (GREATEST) — re-running an
                    # old batch never rewinds progress.
                    await conn.execute(
                        """
                        INSERT INTO ingestion_watermarks (source, entity, watermark, updated_at)
                        VALUES ($1, $2, $3, now())
                        ON CONFLICT (source, entity) DO UPDATE SET
                            watermark = GREATEST(ingestion_watermarks.watermark, EXCLUDED.watermark),
                            updated_at = now()
                        """,
                        batch.source, batch.entity, datetime.fromisoformat(batch.watermark),
                    )
        except (OSError, asyncpg.InterfaceError, asyncpg.CannotConnectNowError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        except asyncpg.PostgresError as e:
            return err(ContractViolation(field=spec.table, detail=str(e)))

        return ok(WriteResult(inserted=inserted, updated=updated), warnings=warnings)

    async def write_batch_bulk(self, batch: IngestBatch) -> Ok[WriteResult] | Err:
        """COPY-based upsert for large historical backfills (AGENTS.md §2:
        Postgres COPY, not row INSERT, at millions of rows). Identical
        idempotency contract to write_batch — COPY lands in a temp table and
        the real insert is the same ON CONFLICT upsert, so re-running a bulk
        batch also reports inserted: 0 (CT-1 semantics)."""
        spec = _REGISTRY.get(batch.entity)
        if spec is None:
            return err(ContractViolation(
                field="entity",
                detail=f"no writer registered for entity {batch.entity!r}",
            ))
        for row in batch.rows:
            if not isinstance(row, spec.model):
                return err(ContractViolation(
                    field="rows",
                    detail=(
                        f"entity {batch.entity} expects {spec.model.__name__} rows, "
                        f"got {type(row).__name__}"
                    ),
                ))

        warnings: tuple[SeraphWarning, ...] = ()
        if batch.source_schema_version == "bhavcopy-legacy":
            warnings = (SeraphWarning(
                code="SOURCE_SCHEMA_LEGACY",
                message="batch normalised from the legacy (pre-UDiFF) bhavcopy schema",
                context={"source": batch.source, "runId": batch.run_id},
            ),)

        cols = list(spec.columns.values())
        key_cols = ", ".join(spec.key)
        non_key = [c for c in cols if c not in spec.key]
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_key)
        records = [tuple(_row_params(spec, row)) for row in batch.rows]

        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        f"CREATE TEMP TABLE _bulk_stage "
                        f"(LIKE {spec.table} INCLUDING DEFAULTS) ON COMMIT DROP"
                    )
                    await conn.copy_records_to_table(
                        "_bulk_stage", records=records, columns=cols
                    )
                    counts = await conn.fetchrow(
                        f"""
                        WITH ins AS (
                            INSERT INTO {spec.table} ({', '.join(cols)})
                            SELECT DISTINCT ON ({key_cols}) {', '.join(cols)}
                            FROM _bulk_stage
                            ON CONFLICT ({key_cols}) DO UPDATE SET {set_clause}
                            RETURNING (xmax = 0) AS inserted
                        )
                        SELECT count(*) FILTER (WHERE inserted)     AS n_ins,
                               count(*) FILTER (WHERE NOT inserted) AS n_upd
                        FROM ins
                        """
                    )
                    await conn.execute(
                        """
                        INSERT INTO ingestion_watermarks (source, entity, watermark, updated_at)
                        VALUES ($1, $2, $3, now())
                        ON CONFLICT (source, entity) DO UPDATE SET
                            watermark = GREATEST(ingestion_watermarks.watermark, EXCLUDED.watermark),
                            updated_at = now()
                        """,
                        batch.source, batch.entity, datetime.fromisoformat(batch.watermark),
                    )
        except (OSError, asyncpg.InterfaceError, asyncpg.CannotConnectNowError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        except asyncpg.PostgresError as e:
            return err(ContractViolation(field=spec.table, detail=str(e)))

        return ok(
            WriteResult(inserted=counts["n_ins"], updated=counts["n_upd"]),
            warnings=warnings,
        )

    async def get_watermark(self, source: str, entity: str) -> Ok[str | None] | Err:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT watermark FROM ingestion_watermarks WHERE source = $1 AND entity = $2",
                    source, entity,
                )
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        if row is None:
            return ok(None)
        return ok(ist_timestamp(row["watermark"]))
