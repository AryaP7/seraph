"""Read-only source census and isolated demo verification; audit evidence only."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]


def backup(source, target):
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)


def census():
    result = {}
    for name in ("seraph.sqlite", "live.sqlite", "news-intelligence-pilot.sqlite", "jobs.sqlite"):
        path = ROOT / "prototype_runs" / name
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            result[name] = {
                table: conn.execute('SELECT count(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0]
                for table in tables if table != "sqlite_sequence"}
            if name == "live.sqlite":
                result[name]["forecast_dates"] = [dict(r) for r in conn.execute(
                    "SELECT as_of, min(issued_at) AS first_issued, count(*) AS records "
                    "FROM prospective_forecasts GROUP BY as_of")]
                result[name]["decision_columns"] = [r[1] for r in conn.execute(
                    "PRAGMA table_info(live_decisions)")]
    return result


async def database():
    import asyncpg
    from seraph.store.bootstrap import DEFAULT_DSN
    conn = await asyncpg.connect(DEFAULT_DSN, timeout=10)
    try:
        async with conn.transaction(readonly=True):
            result = {"database": await conn.fetchval("SELECT current_database()")}
            for table in ("daily_prices", "intraday_bars", "universe_snapshots", "macro_covariates", "flow_aggregates"):
                result[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")
            result["daily_end"] = str(await conn.fetchval("SELECT max(date) FROM daily_prices"))
            return result
    finally:
        await conn.close()


def main():
    report = {"captured_at": datetime.now(timezone.utc).isoformat()}
    try:
        report["stores"] = census()
    except Exception as exc:
        report["census_error"] = f"{type(exc).__name__}: {exc}"
    try:
        report["database"] = asyncio.run(database())
    except Exception as exc:
        report["database_error"] = f"{type(exc).__name__}: {exc}"
    with tempfile.TemporaryDirectory(prefix="seraph-demo-audit-") as tmp:
        isolated = Path(tmp)
        (isolated / "prototype_runs").mkdir()
        for source, env in (
            ("seraph.sqlite", "SERAPH_PROTOTYPE_STORE"),
            ("live.sqlite", "SERAPH_LIVE_STORE"),
            ("news-intelligence-pilot.sqlite", "SERAPH_NEWS_STORE"),
            ("jobs.sqlite", "SERAPH_JOB_STORE"),
        ):
            target = isolated / "prototype_runs" / source
            backup(ROOT / "prototype_runs" / source, target)
            os.environ[env] = str(target)
        os.environ["SERAPH_WORKSPACE_DIR"] = str(isolated / "workspace")
        os.environ["SERAPH_NEWS_WORKER"] = "0"
        import verify_functional_completion as verifier
        # Only LiveStore-using checks need ROOT redirected. Existing evidence
        # remains in place, and all writes/migrations run on copies.
        verifier.ROOT = isolated
        report["journeys"] = []
        for fn in verifier.CHECKS:
            verifier.ROOT = ROOT if fn.__name__ == "packaging" else isolated
            item = fn()
            report["journeys"].append(item)
            print(item["journey"], item.get("works"), flush=True)
        from seraph.dashboard.console_backend import health_surface, prediction_surface
        report["health"] = health_surface()
        report["prediction"] = prediction_surface()
    (OUT / "runtime.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("stores", "database", "census_error", "database_error") if k in report}, indent=2))


if __name__ == "__main__":
    main()
