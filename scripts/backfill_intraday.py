#!/usr/bin/env python3
# C2 — Ingestion Layer (FR1): checkpointed 5-minute intraday backfill for Pillar 1.
"""Pulls 5-minute bars for the ~100-symbol Hawkes universe and lands them in E1.

Resumable by construction: progress is tracked per (symbol, window) in a local
checkpoint file, and every write goes through C1's idempotent upsert, so a run
that dies at request 2,000 resumes there instead of starting over
(SERAPH-BUILD-ROADMAP Phase 2 calls this out explicitly).

Kite's access token expires daily — re-run `scripts/kite_login.py` first if the
run stops with a 403.

Run: python scripts/backfill_intraday.py [--from 2015-02-02] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from seraph.ingestion.hawkes_universe import build_symbol_list  # noqa: E402
from seraph.ingestion.kite_client import (  # noqa: E402
    INTERVAL_MAX_DAYS,
    KiteClient,
    candles_to_bars,
)
from seraph.shared_types import IST, IngestBatch  # noqa: E402
from seraph.store import StoreWriter  # noqa: E402
from seraph.store.bootstrap import resolve_dsn  # noqa: E402

CHECKPOINT = Path(__file__).resolve().parent.parent / "intraday_backfill.checkpoint.json"
INTERVAL = "5minute"
EARLIEST = "2015-02-02"          # measured by the Phase-0 probe, not assumed


def load_checkpoint() -> set[str]:
    if not CHECKPOINT.exists():
        return set()
    return set(json.loads(CHECKPOINT.read_text(encoding="utf-8")).get("done", []))


def save_checkpoint(done: set[str]) -> None:
    CHECKPOINT.write_text(json.dumps({"done": sorted(done)}, indent=0), encoding="utf-8")


async def hawkes_symbols() -> tuple[str, ...]:
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2)
    try:
        members = await pool.fetchval(
            "SELECT members FROM universe_snapshots ORDER BY rebalance_date DESC LIMIT 1"
        )
    finally:
        await pool.close()
    if not members:
        raise RuntimeError("no universe snapshot — run scripts/build_universe.py first")
    return build_symbol_list(list(members))


async def main(start: str, dry_run: bool) -> int:
    symbols = await hawkes_symbols()
    print(f"[intraday] Hawkes universe: {len(symbols)} symbols "
          f"(liquidity core + tariff basket)", flush=True)

    client = KiteClient()
    instruments = client.instruments_nse()
    missing = [s for s in symbols if s not in instruments]
    if missing:
        print(f"[intraday] WARNING {len(missing)} symbol(s) not found on NSE EQ, "
              f"skipping: {', '.join(missing)}", flush=True)
    symbols = tuple(s for s in symbols if s in instruments)

    frm = datetime.fromisoformat(f"{start}T09:00:00+05:30")
    to = datetime.now(IST)
    span_days = (to - frm).days
    windows = max(1, -(-span_days // INTERVAL_MAX_DAYS[INTERVAL]))
    print(f"[intraday] {start} to {to.date()}: ~{windows} windows/symbol, "
          f"~{windows * len(symbols)} requests total", flush=True)
    if dry_run:
        return 0

    done = load_checkpoint()
    writer = await StoreWriter.connect()
    total_rows = 0
    total_rejected = 0
    try:
        for n, symbol in enumerate(symbols, start=1):
            for w_start, candles in client.iter_candles(symbol, INTERVAL, frm, to):
                key = f"{symbol}|{w_start.date()}"
                if key in done:
                    continue
                if candles:
                    bars, rejected = candles_to_bars(symbol, candles)
                    total_rejected += rejected
                    batch = IngestBatch(
                        run_id=f"intraday-backfill-{to.date()}",
                        source="kite", entity="E1", rows=bars,
                        watermark=bars[-1].ts, source_schema_version="kite-v3",
                    )
                    res = await writer.write_batch_bulk(batch)
                    if res.status != "ok":
                        print(f"[intraday] ERROR {symbol} {w_start.date()}: {res.error}",
                              flush=True)
                        continue
                    total_rows += len(bars)
                done.add(key)
                save_checkpoint(done)
            print(f"[intraday] {n}/{len(symbols)} {symbol:<14} "
                  f"cumulative rows {total_rows:,}", flush=True)
    finally:
        await writer.close()
    print(f"[intraday] done - {total_rows:,} bars across {len(symbols)} symbols, "
          f"{total_rejected} bar(s) rejected as unusable", flush=True)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", default=EARLIEST)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.start, a.dry_run)))
