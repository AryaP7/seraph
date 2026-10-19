# C1 — Schema migrations (FIX06, OPS02)
"""Ordered, idempotent, recorded SQL migrations.

`schema.sql` creates the world from nothing and is idempotent, which is right
for a fresh database and useless for one that already holds evidence. A
migration changes an existing database **without destroying what is in it** —
the evaluation-identity change is exactly that case, because the thing it
fixes is evidence being silently overwritten.

Rules this runner enforces:

* migrations apply in filename order, once each, recorded in
  `schema_migrations` with the SHA-256 of the file that ran;
* a migration whose file changed after it was applied is an error, not a
  silent re-run — if the applied SQL no longer matches the file, nobody knows
  what the database actually contains;
* every migration runs inside its own transaction.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name        text        PRIMARY KEY,
    content_sha text        NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


class MigrationDrift(RuntimeError):
    """An applied migration's file has changed since it ran."""


def discover(directory: Path | None = None) -> list[tuple[str, str, str]]:
    """`(name, sha, sql)` for every migration, in filename order."""
    directory = Path(directory or MIGRATIONS_DIR)
    out = []
    for path in sorted(directory.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        out.append((path.name, hashlib.sha256(sql.encode()).hexdigest(), sql))
    return out


async def applied(conn) -> dict[str, str]:
    await conn.execute(LEDGER_DDL)
    rows = await conn.fetch("SELECT name, content_sha FROM schema_migrations")
    return {r["name"]: r["content_sha"] for r in rows}


async def pending(conn, directory: Path | None = None) -> list[tuple[str, str, str]]:
    done = await applied(conn)
    out = []
    for name, sha, sql in discover(directory):
        if name not in done:
            out.append((name, sha, sql))
        elif done[name] != sha:
            raise MigrationDrift(
                f"{name} was applied with content {done[name][:12]} but the file "
                f"now hashes to {sha[:12]}. Add a new migration rather than "
                f"editing one that has already run")
    return out


async def migrate(conn, directory: Path | None = None, *, dry_run: bool = False
                  ) -> dict:
    """Apply every pending migration. Returns what ran."""
    todo = await pending(conn, directory)
    if dry_run:
        return dict(pending=[name for name, _, _ in todo], applied=[],
                    dry_run=True)
    done = []
    for name, sha, sql in todo:
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations (name, content_sha) VALUES ($1,$2) "
                "ON CONFLICT (name) DO NOTHING", name, sha)
        done.append(name)
    return dict(pending=[], applied=done, dry_run=False)
