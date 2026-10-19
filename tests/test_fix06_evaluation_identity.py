"""FIX06 — evaluation identity, and the migration machinery it needs.

Audit finding A06: `validation_results`' key was
`(pillar_subset, reconciliation_mode, xi_mode, epoch)`, so a Table A row and a
Table B row for the same configuration and epoch collided, and re-running an
experiment overwrote the previous evidence in place.

The migration itself needs PostgreSQL, so the SQL-executing assertions are
skipped without one and say so. What runs everywhere: the collision is real
under the old key and gone under the new one, the migration text preserves
rather than drops, and the runner refuses a migration whose file changed after
it ran.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pytest

from seraph.store import migrations

MIGRATION = (Path(migrations.MIGRATIONS_DIR) / "001_evaluation_identity.sql")

OLD_KEY = ("pillar_subset", "reconciliation_mode", "xi_mode", "epoch")
NEW_KEY = ("evaluation_run_id", "table_id", "pillar_subset",
           "reconciliation_mode", "xi_mode", "epoch")


def row(table_id, run="run_1", subset="rmt+hamilton", mode="kalman",
        xi="hamilton", epoch="covid_2020"):
    return dict(evaluation_run_id=run, table_id=table_id, pillar_subset=subset,
                reconciliation_mode=mode, xi_mode=xi, epoch=epoch)


def key_of(record, columns):
    return tuple(record[c] for c in columns)


# ------------------------------------------------- the collision itself


def test_table_a_and_table_b_collide_under_the_old_key():
    a, b = row("A"), row("B")
    assert key_of(a, OLD_KEY) == key_of(b, OLD_KEY), \
        "this equality is the defect: two different results, one key"


def test_they_do_not_collide_under_the_new_key():
    assert key_of(row("A"), NEW_KEY) != key_of(row("B"), NEW_KEY)


def test_a_repeated_experiment_no_longer_overwrites_the_first():
    first, second = row("A", run="run_1"), row("A", run="run_2")
    assert key_of(first, OLD_KEY) == key_of(second, OLD_KEY)
    assert key_of(first, NEW_KEY) != key_of(second, NEW_KEY)


# ------------------------------------------- what the migration says


def test_the_migration_preserves_existing_rows_rather_than_dropping_them():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "DROP TABLE" not in sql.upper()
    assert "DELETE FROM validation_results" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    # Legacy rows are adopted into a named run, not relabelled as something else.
    assert "legacy_pre_migration" in sql
    assert "legacy_unknown" in sql


def test_the_migration_does_not_presume_the_fr35_decision():
    """FIX05 is unresolved, so the schema must accept either answer."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "two_epoch" in sql and "six_epoch" in sql
    assert "legacy_unknown" in sql


def test_the_new_primary_key_carries_run_and_table_identity():
    sql = MIGRATION.read_text(encoding="utf-8")
    declared = re.search(r"ADD PRIMARY KEY \(([^)]*)\)", sql, re.S)
    assert declared, "the migration must declare the new key"
    columns = {c.strip() for c in declared.group(1).split(",")}
    assert columns == set(NEW_KEY)


def test_the_migration_is_written_to_be_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS evaluation_runs" in sql
    assert "ADD COLUMN IF NOT EXISTS evaluation_run_id" in sql
    assert "ON CONFLICT (evaluation_run_id) DO NOTHING" in sql
    statements = [line for line in sql.splitlines()
                  if not line.lstrip().startswith("--")]
    body = chr(10).join(statements).strip()
    assert body.startswith("BEGIN;") and body.endswith("COMMIT;"), (
        "the whole migration must run as one transaction")


# ----------------------------------------------------- the runner


def test_discovery_is_ordered_and_hashed():
    found = migrations.discover()
    assert found, "at least the evaluation-identity migration must be present"
    assert [name for name, _, _ in found] == sorted(name for name, _, _ in found)
    name, sha, sql = found[0]
    assert sha == hashlib.sha256(sql.encode()).hexdigest()


class FakeConn:
    """Enough of an asyncpg connection to drive the runner's bookkeeping."""

    def __init__(self, ledger=None):
        self.ledger = dict(ledger or {})
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append(sql)
        if sql.strip().startswith("INSERT INTO schema_migrations"):
            self.ledger[args[0]] = args[1]

    async def fetch(self, sql):
        return [{"name": n, "content_sha": s} for n, s in self.ledger.items()]

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False
        return _Tx()


def test_a_pending_migration_is_applied_once():
    """Asserted against what `discover()` finds, not a hard-coded list.

    These two assertions used to name `001_evaluation_identity.sql` literally,
    so adding T10's `002_experiment_rows.sql` failed them -- for the inventory
    having grown, which is not what either test is about. The properties are
    that every pending migration is applied, in filename order, and that a
    second run applies none of them again.
    """
    import asyncio
    conn = FakeConn()
    discovered = [name for name, _, _ in migrations.discover()]
    assert len(discovered) >= 2, "this guards order, so it needs two of them"

    first = asyncio.run(migrations.migrate(conn))
    assert first["applied"] == discovered
    second = asyncio.run(migrations.migrate(conn))
    assert second["applied"] == [], "a second run must be a no-op"


def test_a_dry_run_changes_nothing():
    import asyncio
    conn = FakeConn()
    result = asyncio.run(migrations.migrate(conn, dry_run=True))
    assert result["dry_run"] is True
    assert result["pending"] == [name for name, _, _ in migrations.discover()]
    assert result["applied"] == []
    assert not any("ALTER TABLE" in sql for sql in conn.executed)


def test_an_edited_applied_migration_is_an_error_not_a_silent_rerun():
    import asyncio
    conn = FakeConn({"001_evaluation_identity.sql": "0" * 64})
    with pytest.raises(migrations.MigrationDrift, match="Add a new migration"):
        asyncio.run(migrations.pending(conn))


# --------------------------------------------- real PostgreSQL, if present


REAL_DB = os.environ.get("SERAPH_TEST_DB_DSN")


@pytest.mark.skipif(not REAL_DB,
                    reason="needs a disposable seraph_test_* database; "
                           "set SERAPH_TEST_DB_DSN and SERAPH_TEST_TOKEN")
def test_the_migration_applies_and_preserves_rows_on_a_real_database():
    import asyncio

    import asyncpg

    async def run():
        conn = await asyncpg.connect(REAL_DB)
        try:
            await conn.execute("""
                DROP TABLE IF EXISTS validation_results;
                DROP TABLE IF EXISTS evaluation_runs;
                DROP TABLE IF EXISTS schema_migrations;
                CREATE TABLE validation_results (
                    pillar_subset text NOT NULL, reconciliation_mode text NOT NULL,
                    xi_mode text NOT NULL DEFAULT 'hamilton', epoch text NOT NULL,
                    table_id text NOT NULL, auc double precision NOT NULL,
                    mean_lead_time_days double precision NOT NULL,
                    precision_at_recall double precision NOT NULL,
                    weights_artefact_id text NOT NULL, leakage_check text NOT NULL,
                    pre_registration_hash text NOT NULL,
                    PRIMARY KEY (pillar_subset, reconciliation_mode, xi_mode, epoch));
                INSERT INTO validation_results VALUES
                    ('rmt+hamilton','kalman','hamilton','covid_2020','A',
                     0.61,3.0,0.4,'w','clean','h');
            """)
            await migrations.migrate(conn)
            kept = await conn.fetchval("SELECT count(*) FROM validation_results")
            adopted = await conn.fetchval(
                "SELECT evaluation_run_id FROM validation_results LIMIT 1")
            # The collision that used to be impossible is now insertable.
            await conn.execute(
                "INSERT INTO evaluation_runs (evaluation_run_id, "
                "pre_registration_hash, design_label, table_b_scope) "
                "VALUES ('legacy_pre_migration2','h','x','six_epoch') "
                "ON CONFLICT DO NOTHING")
            await conn.execute("""
                INSERT INTO validation_results VALUES
                    ('rmt+hamilton','kalman','hamilton','covid_2020','B',
                     0.55,2.0,0.3,'w','clean','h','legacy_pre_migration')""")
            both = await conn.fetchval("SELECT count(*) FROM validation_results")
            return kept, adopted, both
        finally:
            await conn.close()

    kept, adopted, both = asyncio.run(run())
    assert kept == 1, "the pre-existing row must survive"
    assert adopted == "legacy_pre_migration"
    assert both == 2, "Table A and Table B rows must now coexist"
