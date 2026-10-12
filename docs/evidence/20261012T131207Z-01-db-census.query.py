# Read-only database census. SELECT only - no DDL, no writes.
import asyncio, asyncpg, sys, os, subprocess, datetime
sys.path.insert(0, os.getcwd())
from seraph.store.bootstrap import resolve_dsn

TABLES = ["daily_prices","intraday_bars","microstructure_state","macro_covariates",
          "tariff_events","hawkes_output","rmt_output","hamilton_output",
          "reconciled_state","csrs","universe_snapshots","ingestion_watermarks",
          "flow_aggregates","user_portfolio","regulatory_action_log","validation_results"]

async def main():
    dsn = resolve_dsn()
    conn = await asyncpg.connect(dsn, timeout=10)
    print(f"DSN                : {dsn}")
    print(f"server_version     : {await conn.fetchval('SHOW server_version')}")
    tsv = await conn.fetchval("SELECT extversion FROM pg_extension WHERE extname='timescaledb'")
    print(f"timescaledb ext    : {tsv}")
    _sz = await conn.fetchval("SELECT pg_size_pretty(pg_database_size(current_database()))")
    print(f"database size      : {_sz}")
    print()
    print(f"{'table':<26}{'rows':>14}  range")
    print("-" * 78)
    for t in TABLES:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)", t)
        if not exists:
            print(f"{t:<26}{'ABSENT':>14}")
            continue
        n = await conn.fetchval(f"SELECT count(*) FROM {t}")
        rng = ""
        if n:
            cols = [r["column_name"] for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name=$1", t)]
            for c in ("ts", "date", "rebalance_date"):
                if c in cols:
                    lo, hi = await conn.fetchrow(f"SELECT min({c}) a, max({c}) b FROM {t}")
                    rng = f"{c}: {lo} .. {hi}"
                    break
        print(f"{t:<26}{n:>14,}  {rng}")
    print()
    print("=== ingestion_watermarks (full) ===")
    for r in await conn.fetch("SELECT * FROM ingestion_watermarks ORDER BY source, entity"):
        print("  ", dict(r))
    print()
    print("=== rmt_output integrity (resolves 374 vs 5,363) ===")
    n = await conn.fetchval("SELECT count(*) FROM rmt_output")
    print(f"  rows                       : {n:,}")
    if n:
        print(f"  distinct dates             : {await conn.fetchval('SELECT count(DISTINCT date) FROM rmt_output'):,}")
        print(f"  empty eigenvalue arrays    : {await conn.fetchval('SELECT count(*) FROM rmt_output WHERE eigenvalues IS NULL OR array_length(eigenvalues,1) IS NULL'):,}")
        print(f"  rows with v1 populated     : {await conn.fetchval('SELECT count(*) FROM rmt_output WHERE v1 IS NOT NULL AND array_length(v1,1) > 0'):,}")
        row = await conn.fetchrow("""
            SELECT max(abs_dev) mx, avg(abs_dev) av FROM (
              SELECT abs((SELECT sum(e) FROM unnest(eigenvalues) e) - array_length(eigenvalues,1)) abs_dev
              FROM rmt_output WHERE array_length(eigenvalues,1) IS NOT NULL) s""")
        print(f"  FR16 max|trace - N_t|      : {row['mx']:.3e}   (guard: must be ~0)")
        print(f"  FR16 mean|trace - N_t|     : {row['av']:.3e}")
        r2 = await conn.fetchrow("SELECT min(array_length(eigenvalues,1)) a, max(array_length(eigenvalues,1)) b FROM rmt_output")
        print(f"  N_t range                  : {r2['a']} .. {r2['b']}")
    await conn.close()

asyncio.run(main())
