# C1 — Store & Schema (FR8, FR38): DSN resolution and idempotent DDL apply.
from __future__ import annotations

import os
from pathlib import Path

import asyncpg

DEFAULT_DSN = "postgresql://seraph:seraph@localhost:5433/seraph"
_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def resolve_dsn(dsn: str | None = None) -> str:
    return dsn or os.environ.get("SERAPH_DB_DSN", DEFAULT_DSN)


async def apply_schema(dsn: str | None = None) -> None:
    """Apply schema.sql. Safe to call repeatedly — the DDL is idempotent."""
    conn = await asyncpg.connect(resolve_dsn(dsn))
    try:
        await conn.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        await conn.close()
