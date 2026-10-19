# C1 — Store & Schema (FR8, FR38): DSN resolution and idempotent DDL apply.
from __future__ import annotations

import os
from pathlib import Path

import asyncpg

# Isolated experiment: never default writers/tests to the original database.
#
# Assembled from the SAME environment variables docker-compose.yml reads, with
# the same fallbacks, because the previous hardcoded form had drifted: it said
# password `seraph` while compose said `change-me-locally`, so the documented
# "run `docker compose up -d` first" could never make a DB test pass. Two
# copies of one default in two files is the only way that happens, so there is
# now one source for each field. It also keeps a password out of a versioned
# source file, which the project's own rule asks for even of a placeholder.
def _default_dsn() -> str:
    user = os.environ.get("SERAPH_DB_USER", "seraph")
    password = os.environ.get("SERAPH_DB_PASSWORD", "change-me-locally")
    host = os.environ.get("SERAPH_DB_HOST", "127.0.0.1")
    port = os.environ.get("SERAPH_DB_PORT", "5434")
    name = os.environ.get("SERAPH_DB_NAME", "seraph_research")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


DEFAULT_DSN = _default_dsn()
_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def resolve_dsn(dsn: str | None = None) -> str:
    """Explicit argument, then `SERAPH_DB_DSN`, then the compose-mirrored
    default — recomputed per call, so a variable set after import is honoured
    rather than silently losing to an import-time snapshot."""
    return dsn or os.environ.get("SERAPH_DB_DSN") or _default_dsn()


async def apply_schema(dsn: str | None = None) -> None:
    """Apply schema.sql. Safe to call repeatedly — the DDL is idempotent."""
    conn = await asyncpg.connect(resolve_dsn(dsn))
    try:
        await conn.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        await conn.close()
