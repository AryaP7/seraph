"""Read-only snapshot for the isolated SERAPH experiment. Never writes to SQL."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asyncpg
import numpy as np
import pandas as pd


async def snapshot(out: Path, source_dsn: str):
    out.mkdir(parents=True, exist_ok=True)
    conn = await asyncpg.connect(source_dsn, server_settings={
        "default_transaction_read_only": "on", "statement_timeout": "300000"})
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            assert await conn.fetchval("SHOW transaction_read_only") == "on"
            print("Read-only repeatable-read snapshot: computing point-in-time market panel", flush=True)
            rows = await conn.fetch("""
            WITH raw AS (
              SELECT symbol, date, adj_close, universe_member_flag, tottrdval,
                lag(adj_close) OVER (PARTITION BY symbol ORDER BY date) prev_close,
                lag(date) OVER (PARTITION BY symbol ORDER BY date) prev_date
              FROM daily_prices WHERE date >= '2004-01-01' AND adj_close > 0
            ), calendar AS (
              SELECT date, lag(date) OVER (ORDER BY date) prior_session
              FROM (SELECT DISTINCT date FROM daily_prices WHERE date >= '2004-01-01') d
            ), eligible AS (
              SELECT r.date, r.symbol, ln(r.adj_close/r.prev_close) lr,
                ((('x'||substr(md5(r.symbol),1,8))::bit(32)::bigint) % 10)::int bucket
              FROM raw r JOIN calendar c USING (date)
              WHERE r.date >= '2005-01-01' AND r.universe_member_flag
                AND r.prev_close > 0 AND r.prev_date=c.prior_session
            )
            SELECT date, bucket, avg(lr) bucket_return, count(*) n,
                   sum(lr) sum_return, sum(CASE WHEN lr<0 THEN 1 ELSE 0 END) n_down,
                   sum(CASE WHEN lr < -0.03 THEN 1 ELSE 0 END) n_down3,
                   sum(lr*lr) sum_sq
            FROM eligible GROUP BY date,bucket ORDER BY date,bucket
            """)
            buckets = pd.DataFrame([dict(r) for r in rows])
            buckets["date"] = pd.to_datetime(buckets["date"])
            groups = buckets.groupby("date")
            sums = groups[["n", "sum_return", "n_down", "n_down3", "sum_sq"]].sum()
            frame = pd.DataFrame(index=sums.index)
            frame["market_return"] = sums.sum_return / sums.n
            frame["universe_count"] = sums.n
            frame["breadth_down"] = sums.n_down / sums.n
            frame["breadth_down3"] = sums.n_down3 / sums.n
            frame["dispersion"] = np.sqrt(np.maximum(sums.sum_sq / sums.n - frame.market_return**2, 0))
            pivot = buckets.pivot(index="date", columns="bucket", values="bucket_return")
            for b in range(10):
                frame[f"factor_{b}"] = pivot.get(b, np.nan)
            queries = {
                "rmt": "SELECT date, eigenvalues, f_t, v_eig_t, omega_t, sca_t FROM rmt_output ORDER BY date",
                "hawkes": "SELECT ts, branching_ratio_n, mts FROM hawkes_output WHERE scope='market' ORDER BY ts",
                "vix": "SELECT date, india_vix FROM macro_covariates WHERE india_vix IS NOT NULL ORDER BY date",
            }
            for kind, query in queries.items():
                data = [dict(r) for r in await conn.fetch(query)]
                if not data:
                    continue
                if kind == "rmt":
                    for r in data:
                        ev = r.pop("eigenvalues")
                        r["lam1_share"] = float(ev[0])/len(ev) if ev else np.nan
                df = pd.DataFrame(data)
                df.to_parquet(out / f"original_{kind}.parquet", index=False)
                if kind in ("rmt", "vix"):
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date").add_prefix(f"original_{kind}_")
                    frame = frame.join(df)
            frame.index.name = "date"
            frame.reset_index().to_parquet(out / "market_snapshot.parquet", index=False)
            manifest = {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "source": "existing local SERAPH PostgreSQL; read-only repeatable-read",
                "rows": len(frame), "from": str(frame.index.min().date()), "to": str(frame.index.max().date()),
                "market_definition": "equal-weight average log return of available point-in-time universe members; research index, not an executable portfolio",
                "return_correction": "lag computed before universe filter; only consecutive global sessions admitted; re-entry gaps not mistaken for daily returns",
                "factors": "ten deterministic MD5 symbol buckets of the contemporaneous eligible universe; fixed grouping rule, not sectors or licensed indices",
                "limitations": ["underlying adjusted EOD2 snapshot is not an as-first-published vintage archive", "source universe construction inherited; turnover proxy and survivorship coverage caveats remain", "persisted original pillars retain prior research-selection history"],
            }
            manifest["files"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.parquet"))}
            (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            print(json.dumps({k: manifest[k] for k in ("rows", "from", "to")}), flush=True)
    finally:
        await conn.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "research_data")
    p.add_argument("--source-dsn", default="postgresql://seraph:seraph@localhost:5433/seraph")
    args = p.parse_args()
    asyncio.run(snapshot(args.out, args.source_dsn))
