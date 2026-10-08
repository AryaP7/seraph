# CT-1 — C2 ⇄ C1: ingestion idempotency (ARCHITECTURE §5 ⑧)
"""Re-running a batch must not duplicate rows: `writeBatch` twice → second call
reports inserted == 0; the watermark advances exactly once. Negative: a
legacy-schema row is Ok + SOURCE_SCHEMA_LEGACY, never Err.

Needs a reachable TimescaleDB — `docker compose up -d`. Skips otherwise.
"""
from __future__ import annotations

import asyncio

import pytest

asyncpg = pytest.importorskip("asyncpg")

from seraph.shared_types import DailyBar, IngestBatch
from seraph.store import StoreWriter, apply_schema, resolve_dsn


def _db_available() -> bool:
    async def probe() -> None:
        conn = await asyncpg.connect(resolve_dsn(), timeout=3)
        await conn.close()

    try:
        asyncio.run(probe())
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="TimescaleDB not reachable — run `docker compose up -d` first",
)

_SYMBOLS = ("CT1TESTA", "CT1TESTB", "CT1TESTC")
_WATERMARK = "2020-01-03T18:00:00+05:30"


def _bar(symbol: str, day: int, close: float) -> DailyBar:
    return DailyBar(
        symbol=symbol, date=f"2020-01-0{day}",
        open=close - 1, high=close + 1, low=close - 2, close=close,
        volume=1_000_000, tottrdval=close * 1_000_000, adj_close=close,
    )


def _batch(schema_version: str = "bhavcopy-udiff") -> IngestBatch:
    rows = tuple(_bar(s, day=2, close=100.0 + i) for i, s in enumerate(_SYMBOLS))
    return IngestBatch(
        run_id="ct1-run", source="eod2", entity="E3", rows=rows,
        watermark=_WATERMARK, source_schema_version=schema_version,
    )


async def _clean(writer: StoreWriter) -> None:
    async with writer._pool.acquire() as conn:  # test-only reach-in
        await conn.execute(
            "DELETE FROM daily_prices WHERE symbol = ANY($1)", list(_SYMBOLS)
        )
        await conn.execute(
            "DELETE FROM ingestion_watermarks WHERE source = 'eod2' AND entity = 'E3'"
        )


def test_ct1_write_batch_is_idempotent_and_watermark_advances_once():
    async def run() -> None:
        await apply_schema()
        writer = await StoreWriter.connect()
        try:
            await _clean(writer)
            batch = _batch()

            first = await writer.write_batch(batch)
            assert first.status == "ok", getattr(first, "error", None)
            assert first.value.inserted == len(_SYMBOLS)
            assert first.value.updated == 0

            wm1 = await writer.get_watermark("eod2", "E3")
            assert wm1.status == "ok" and wm1.value == _WATERMARK

            second = await writer.write_batch(batch)
            assert second.status == "ok"
            assert second.value.inserted == 0, "re-run must not duplicate rows"
            assert second.value.updated == len(_SYMBOLS)

            wm2 = await writer.get_watermark("eod2", "E3")
            assert wm2.status == "ok" and wm2.value == _WATERMARK, (
                "watermark must advance exactly once for identical batches"
            )
        finally:
            await _clean(writer)
            await writer.close()

    asyncio.run(run())


def test_ct1_negative_legacy_schema_is_ok_with_warning_not_err():
    async def run() -> None:
        await apply_schema()
        writer = await StoreWriter.connect()
        try:
            await _clean(writer)
            res = await writer.write_batch(_batch(schema_version="bhavcopy-legacy"))
            assert res.status == "ok", "legacy schema is expected input, not a failure"
            assert any(w.code == "SOURCE_SCHEMA_LEGACY" for w in res.warnings)
        finally:
            await _clean(writer)
            await writer.close()

    asyncio.run(run())
