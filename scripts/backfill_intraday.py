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
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from seraph.ingestion.hawkes_universe import build_symbol_list  # noqa: E402
from seraph.market_calendar.sessions import SessionCalendar  # noqa: E402
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



def _last_completed_session_close(now: datetime) -> datetime:
    """The close of the most recent session that has ALREADY finished.

    The default end of the request window used to be `now - 5 minutes`. Run
    during market hours -- which is exactly when a daily acquisition job runs
    -- that asks Kite for a window ending mid-session, and Kite correctly
    answers with the bars up to that point. Repeated once per session it
    silently truncated the last three 5-minute bars of 56 consecutive
    sessions (2026-08-03 .. 2026-10-22) for 87 of the 95 members: 14,616 of
    the 14,630 missing symbol-bars in the trailing 500-session window, i.e.
    99.90% of them. The eight unaffected members were backfilled by a
    separate later run that happened to pass an explicit `--to`.

    Nothing was wrong with the broker, the plan or the universe. The request
    never asked for the end of the day. Asking only for closes that have
    already happened cannot truncate a live session, and `close_timestamp`
    carries the real session hours, so a short session (Diwali Muhurat) ends
    at its own close rather than a hardcoded 15:30.
    """
    calendar = SessionCalendar()
    day = now.date()
    for _ in range(30):
        iso = day.isoformat()
        if calendar.is_session(iso):
            close = datetime.fromisoformat(calendar.close_timestamp(iso))
            if close <= now:
                return close
        day -= timedelta(days=1)
    raise RuntimeError(
        f"no completed trading session found in the 30 days before "
        f"{now.isoformat()}")

def load_checkpoint(path: Path = CHECKPOINT) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("done", []))


def save_checkpoint(done: set[str], path: Path = CHECKPOINT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix=path.name+'.', suffix='.tmp', delete=False) as f:
        json.dump({'schema': 'intraday-backfill/2', 'done': sorted(done)}, f)
        f.flush()
        os.fsync(f.fileno())
        temporary = Path(f.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def request_windows(frm: datetime, to: datetime):
    cursor = frm
    while cursor < to:
        end = min(cursor + timedelta(days=INTERVAL_MAX_DAYS[INTERVAL]), to)
        yield cursor, end
        cursor = end


def window_key(symbol, token, start, end):
    # Old symbol|date keys cannot say whether a window ended halfway through
    # a session/month. Retain them as history, but re-fetch rather than use
    # them to suppress a longer request. C1's upsert preserves idempotency.
    return f'v2|{symbol}|{token}|{INTERVAL}|{start.isoformat()}|{end.isoformat()}'


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


async def main(start: str, dry_run: bool, *, end: str | None = None,
               symbols: tuple[str, ...] | None = None,
               checkpoint: Path = CHECKPOINT) -> int:
    frm = datetime.fromisoformat(f"{start}T09:00:00+05:30")
    now = datetime.now(IST)
    to = (datetime.fromisoformat(f"{end}T15:30:00+05:30") if end else
          _last_completed_session_close(now))
    if not frm < to <= now:
        raise ValueError('Require start before end and an end no later than now')
    symbols = tuple(dict.fromkeys(symbols)) if symbols else await hawkes_symbols()
    windows = list(request_windows(frm, to))
    print(f"[intraday] Hawkes universe: {len(symbols)} symbols "
          f"(explicit selection or liquidity core + tariff basket)", flush=True)
    print(f"[intraday] {frm.isoformat()} to {to.isoformat()}: "
          f"{len(windows)} windows/symbol, at most {len(windows)*len(symbols)} requests", flush=True)
    if dry_run:
        # An explicit symbol list makes this a credential/network-free plan.
        return 0

    client = KiteClient()
    instruments = client.instruments_nse()
    missing = [s for s in symbols if s not in instruments]
    if missing:
        print(f"[intraday] WARNING {len(missing)} symbol(s) not found on NSE EQ, "
              f"skipping: {', '.join(missing)}", flush=True)
    symbols = tuple(s for s in symbols if s in instruments)

    done = load_checkpoint(checkpoint)
    writer = await StoreWriter.connect()
    total_rows = 0
    total_rejected = 0
    incomplete = len(missing)
    try:
        for n, symbol in enumerate(symbols, start=1):
            for w_start, w_end in windows:
                key = window_key(symbol, instruments[symbol], w_start, w_end)
                if key in done:
                    continue
                # Check the exact request before network I/O, not after the
                # generator has fetched a supposedly skipped window.
                candles = client.historical(instruments[symbol], INTERVAL, w_start, w_end)
                rejected = 0
                if candles:
                    bars, rejected = candles_to_bars(symbol, candles)
                    total_rejected += rejected
                    if not bars:
                        incomplete += 1
                        print(f'[intraday] {symbol} {w_start.date()}: all candles rejected; window remains pending', flush=True)
                        continue
                    batch = IngestBatch(
                        run_id=f"intraday-backfill-{to.date()}",
                        source="kite", entity="E1", rows=bars,
                        watermark=bars[-1].ts, source_schema_version="kite-v3",
                    )
                    res = await writer.write_batch_bulk(batch)
                    if res.status != "ok":
                        print(f"[intraday] ERROR {symbol} {w_start.date()}: {res.error}",
                              flush=True)
                        incomplete += 1
                        continue
                    total_rows += len(bars)
                if not candles or rejected:
                    # Empty vendor responses do not prove complete coverage;
                    # rejected rows must remain recoverable on the next run.
                    incomplete += 1
                    print(f'[intraday] {symbol} {w_start.date()}: empty/rejected rows; window remains pending', flush=True)
                    continue
                done.add(key)
                save_checkpoint(done, checkpoint)
            print(f"[intraday] {n}/{len(symbols)} {symbol:<14} "
                  f"cumulative rows {total_rows:,}", flush=True)
    finally:
        await writer.close()
    print(f"[intraday] done - {total_rows:,} bars across {len(symbols)} symbols, "
          f"{total_rejected} bar(s) rejected as unusable", flush=True)
    print(f'[intraday] incomplete windows/symbols: {incomplete}', flush=True)
    return 2 if incomplete else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", default=EARLIEST)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument('--to', dest='end', help='Last requested date, through 15:30 IST')
    p.add_argument('--symbols', nargs='+', help='Explicit bounded symbol selection')
    p.add_argument('--checkpoint', type=Path, default=CHECKPOINT)
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.start, a.dry_run, end=a.end,
        symbols=tuple(a.symbols) if a.symbols else None, checkpoint=a.checkpoint)))
