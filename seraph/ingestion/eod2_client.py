# C2 — Ingestion Layer (FR1, FR2, FR7): EOD2 daily OHLCV client.
"""Loads the EOD2 data snapshot (vendor/eod2/src/eod2_data/daily/*.csv) into
E3 daily_prices via C1's bulk COPY path.

What EOD2 gives us (DATA-ACQUISITION §2):
- Daily OHLCV for 3,600+ NSE symbols since 1995, adjusted in place for splits
  and bonuses (FR7), with ISIN tracking across symbol renames. Documented
  caveat: pre-2005 rows may not be fully adjusted — the corpus starts 2005, so
  only the return series is exposed, and report §7.1 must state this.
- `adj_close` therefore equals `close` here: the series arrives adjusted.

What EOD2 does NOT give us:
- TOTTRDVAL (traded value). FR52 ranks by it. It is approximated as
  close × volume, every batch carries an ESTIMATOR_FALLBACK warning, and the
  exact column can later be backfilled from raw bhavcopy (bhavcopy_reader).
- Index files (filenames with spaces, e.g. "nifty 50.csv") are skipped — the
  universe is equities only; index levels are FR41's benchmark, ingested
  separately.

`listing_days_to_date` counts from the symbol's ACTUAL first row (1995+), not
from the corpus start — FR52's ≥1000-day filter must see true listing age in
2005, not age-within-corpus.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path

import polars as pl

from seraph.shared_types import DailyBar, IngestBatch, SeraphWarning
from seraph.store import StoreWriter

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = _REPO_ROOT / "vendor" / "eod2" / "src" / "eod2_data" / "daily"
CORPUS_START = "2005-01-01"

_TOTTRDVAL_WARNING = SeraphWarning(
    code="ESTIMATOR_FALLBACK",
    message="TOTTRDVAL approximated as close × volume — EOD2 CSVs carry no "
            "traded-value column; exact values require the bhavcopy path",
    context={"field": "tottrdval"},
)


def load_symbol_csv(path: Path, corpus_start: str = CORPUS_START) -> tuple[DailyBar, ...]:
    """One symbol's file → validated E3 rows (corpus window only)."""
    symbol = path.stem.upper()
    df = pl.read_csv(
        path,
        columns=["Date", "Open", "High", "Low", "Close", "Volume"],
        schema_overrides={
            "Date": pl.Utf8, "Open": pl.Float64, "High": pl.Float64,
            "Low": pl.Float64, "Close": pl.Float64, "Volume": pl.Float64,
        },
    )
    df = df.drop_nulls(["Date", "Open", "High", "Low", "Close", "Volume"])
    # Listing age counts from the file's true start, BEFORE the corpus filter.
    df = df.with_row_index("idx").with_columns(
        (pl.col("idx") + 1).alias("listing_days"),
        (pl.col("Close") * pl.col("Volume")).alias("tottrdval_approx"),
    )
    df = df.filter(pl.col("Date") >= corpus_start)
    return tuple(
        DailyBar(
            symbol=symbol,
            date=r["Date"],
            open=r["Open"], high=r["High"], low=r["Low"], close=r["Close"],
            volume=int(r["Volume"]),
            tottrdval=float(r["tottrdval_approx"]),
            adj_close=r["Close"],                    # series arrives adjusted (FR7)
            listing_days_to_date=int(r["listing_days"]),
        )
        for r in df.iter_rows(named=True)
    )


def discover_symbol_files(data_dir: Path = DEFAULT_DATA_DIR) -> list[Path]:
    """Equity CSVs only — index files have spaces in their names."""
    return sorted(
        p for p in data_dir.glob("*.csv") if " " not in p.stem
    )


async def backfill(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    corpus_start: str = CORPUS_START,
    limit: int | None = None,
    progress_every: int = 250,
) -> dict[str, int]:
    """Full historical load, one bulk batch per symbol. Idempotent end to end
    (CT-1): re-running converges to inserted=0."""
    files = discover_symbol_files(data_dir)
    if limit is not None:
        files = files[:limit]
    writer = await StoreWriter.connect()
    totals = {"symbols": 0, "rows": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    try:
        for n, path in enumerate(files, start=1):
            try:
                rows = load_symbol_csv(path, corpus_start)
            except Exception as e:              # malformed vendor file — skip loudly
                print(f"[eod2] SKIP {path.name}: {e}", flush=True)
                totals["errors"] += 1
                continue
            if not rows:
                totals["skipped"] += 1
                continue
            batch = IngestBatch(
                run_id=f"eod2-backfill-{date.today().isoformat()}",
                source="eod2",
                entity="E3",
                rows=rows,
                watermark=f"{rows[-1].date}T18:00:00+05:30",
                source_schema_version="eod2-csv-v9",
            )
            res = await writer.write_batch_bulk(batch)
            if res.status != "ok":
                print(f"[eod2] ERROR {path.name}: {res.error}", flush=True)
                totals["errors"] += 1
                continue
            totals["symbols"] += 1
            totals["rows"] += len(rows)
            totals["inserted"] += res.value.inserted
            totals["updated"] += res.value.updated
            if n % progress_every == 0:
                print(f"[eod2] {n}/{len(files)} files — {totals['rows']:,} rows so far", flush=True)
    finally:
        await writer.close()
    print(f"[eod2] done: {totals} — note: {_TOTTRDVAL_WARNING.message}", flush=True)
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EOD2 daily backfill (C2).")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--from", dest="corpus_start", default=CORPUS_START)
    parser.add_argument("--limit", type=int, default=None,
                        help="load only the first N symbol files (testing)")
    args = parser.parse_args(argv)
    asyncio.run(backfill(
        data_dir=args.data_dir, corpus_start=args.corpus_start, limit=args.limit
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
