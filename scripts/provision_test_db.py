"""DATA01 — provision the disposable guarded test database, and nothing else.

Creates `seraph_test_guard(token)`, inserts the token, applies `schema.sql`
and runs the migrations. Then prints the two environment variables the test
suite needs.

The guard exists because the worst outcome here is not a failed test — it is
running test DDL against the source or research database. So this script
refuses to touch anything whose database name does not start with
`seraph_test_`, refuses a DSN that is not on loopback, and refuses outright if
the target already looks like a real SERAPH database (any of the E1-E14 tables
with rows in it).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_DSN = "postgresql://seraph_test:seraph_test@127.0.0.1:5435/seraph_test_local"

#: If any of these holds rows, this is not a disposable test database.
REAL_DATA_TABLES = ("intraday_bars", "daily_prices", "csrs", "hawkes_output",
                    "rmt_output", "hamilton_output", "validation_results")

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def check_target(dsn: str) -> str:
    parsed = urlparse(dsn)
    name = (parsed.path or "").lstrip("/")
    if not name.startswith("seraph_test_"):
        raise SystemExit(
            f"refusing to provision {name!r}: the test guard may only ever be "
            f"placed in a database whose name starts with 'seraph_test_'. "
            f"Putting it in a source or research database is the one mistake "
            f"this script exists to prevent")
    if (parsed.hostname or "") not in LOOPBACK:
        raise SystemExit(
            f"refusing to provision a non-loopback host {parsed.hostname!r}: "
            f"the disposable test database is local only")
    return name


async def provision(dsn: str, token: str, *, apply_schema: bool) -> dict:
    import asyncpg

    from seraph.store import migrations

    name = check_target(dsn)
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        actual = await conn.fetchval("SELECT current_database()")
        if actual != name:
            raise SystemExit(f"connected to {actual!r}, expected {name!r}")

        for table in REAL_DATA_TABLES:
            exists = await conn.fetchval("SELECT to_regclass($1)", table)
            if not exists:
                continue
            rows = await conn.fetchval(f"SELECT count(*) FROM {table}")
            if rows:
                raise SystemExit(
                    f"refusing to provision: {table} already holds {rows} rows, so "
                    f"this is not a disposable test database. Point "
                    f"SERAPH_TEST_DB_DSN at a fresh one")

        await conn.execute(
            "CREATE TABLE IF NOT EXISTS seraph_test_guard (token text PRIMARY KEY)")
        await conn.execute(
            "INSERT INTO seraph_test_guard (token) VALUES ($1) "
            "ON CONFLICT (token) DO NOTHING", token)

        applied = {"applied": [], "pending": []}
        if apply_schema:
            schema = (ROOT / "seraph" / "store" / "schema.sql").read_text(encoding="utf-8")
            try:
                await conn.execute(schema)
            except Exception as exc:                          # noqa: BLE001
                # TimescaleDB may be absent in a plain Postgres image; the
                # non-hypertable DDL still applies and the tests say so.
                print(f"[warn] schema.sql did not apply cleanly: {exc}")
            applied = await migrations.migrate(conn)

        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "ORDER BY tablename")
        return dict(database=name, token_rows=await conn.fetchval(
            "SELECT count(*) FROM seraph_test_guard"),
            tables=[r["tablename"] for r in tables], migrations=applied)
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("SERAPH_TEST_DB_DSN",
                                                        DEFAULT_DSN))
    parser.add_argument("--token", default=os.environ.get("SERAPH_TEST_TOKEN"))
    parser.add_argument("--no-schema", action="store_true",
                        help="only place the guard marker")
    args = parser.parse_args()

    token = args.token or secrets.token_hex(16)
    try:
        report = asyncio.run(provision(args.dsn, token,
                                       apply_schema=not args.no_schema))
    except SystemExit:
        raise
    except Exception as exc:                                  # noqa: BLE001
        print(f"[provision] could not reach the test database: "
              f"{type(exc).__name__}: {exc}")
        print("[provision] start it first:\n"
              "    docker compose -f docker-compose.test.yml up -d")
        return 1

    print(f"[provision] database   : {report['database']}")
    print(f"[provision] guard rows : {report['token_rows']}")
    print(f"[provision] tables     : {len(report['tables'])}")
    print(f"[provision] migrations : applied {report['migrations']['applied']}")
    print("\nExport these for the test run (the token is not written to any file):\n")
    print(f'    $env:SERAPH_TEST_DB_DSN = "{args.dsn}"')
    print(f'    $env:SERAPH_TEST_TOKEN  = "{token}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
