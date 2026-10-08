# C1 — Store & Schema (FR8, FR38): StoreReader — S2, typed reads for everything.
"""No component reaches into another component's tables directly — they come
through here (AGENTS.md §6). Rows come back as shared_types models with
timestamps rendered in explicit IST."""
from __future__ import annotations

from datetime import date, datetime

import asyncpg

from seraph.shared_types import (
    DailyBar,
    Err,
    IntradayBar,
    MacroRow,
    MicroState,
    Ok,
    SourceUnavailable,
    err,
    ist_date,
    ist_timestamp,
    ok,
)
from seraph.store.bootstrap import resolve_dsn


class StoreReader:
    """S2 — typed query methods over the persisted entities."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str | None = None) -> "StoreReader":
        pool = await asyncpg.create_pool(resolve_dsn(dsn), min_size=1, max_size=4)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def daily_bars(
        self,
        *,
        symbols: tuple[str, ...] | None = None,
        from_date: str,
        to_date: str,
        universe_only: bool = False,
    ) -> Ok[tuple[DailyBar, ...]] | Err:
        sql = (
            "SELECT symbol, date, open, high, low, close, volume, tottrdval, "
            "adj_close, universe_member_flag, listing_days_to_date "
            "FROM daily_prices WHERE date >= $1 AND date <= $2"
        )
        params: list = [date.fromisoformat(from_date), date.fromisoformat(to_date)]
        if symbols is not None:
            params.append(list(symbols))
            sql += f" AND symbol = ANY(${len(params)})"
        if universe_only:
            sql += " AND universe_member_flag"
        sql += " ORDER BY symbol, date"
        try:
            rows = await self._fetch(sql, params)
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        return ok(tuple(
            DailyBar(
                symbol=r["symbol"], date=ist_date(r["date"]),
                open=r["open"], high=r["high"], low=r["low"], close=r["close"],
                volume=r["volume"], tottrdval=float(r["tottrdval"]),
                adj_close=r["adj_close"],
                universe_member=r["universe_member_flag"],
                listing_days_to_date=r["listing_days_to_date"],
            )
            for r in rows
        ))

    async def intraday_bars(
        self, *, symbols: tuple[str, ...], from_ts: str, to_ts: str
    ) -> Ok[tuple[IntradayBar, ...]] | Err:
        sql = (
            "SELECT symbol, ts, open, high, low, close, volume, signed_volume, "
            "log_return, is_jump, jump_sign "
            "FROM intraday_bars "
            "WHERE symbol = ANY($1) AND ts >= $2 AND ts <= $3 ORDER BY symbol, ts"
        )
        params = [list(symbols), datetime.fromisoformat(from_ts), datetime.fromisoformat(to_ts)]
        try:
            rows = await self._fetch(sql, params)
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        return ok(tuple(
            IntradayBar(
                symbol=r["symbol"], ts=ist_timestamp(r["ts"]),
                open=r["open"], high=r["high"], low=r["low"], close=r["close"],
                volume=r["volume"], signed_volume=r["signed_volume"],
                log_return=r["log_return"], is_jump=r["is_jump"],
                jump_sign=r["jump_sign"],
            )
            for r in rows
        ))

    async def macro_covariates(
        self, *, from_date: str, to_date: str
    ) -> Ok[tuple[MacroRow, ...]] | Err:
        sql = (
            "SELECT date, rbi_repo_rate, bank_credit_growth_yoy, india_vix, "
            "vix_available, inr_twi, brent_price, g_t, g_t_sector_weighted "
            "FROM macro_covariates WHERE date >= $1 AND date <= $2 ORDER BY date"
        )
        params = [date.fromisoformat(from_date), date.fromisoformat(to_date)]
        try:
            rows = await self._fetch(sql, params)
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        return ok(tuple(
            MacroRow(
                date=ist_date(r["date"]), rbi_repo_rate=r["rbi_repo_rate"],
                bank_credit_growth_yoy=r["bank_credit_growth_yoy"],
                india_vix=r["india_vix"], vix_available=r["vix_available"],
                inr_twi=r["inr_twi"], brent_price=r["brent_price"],
                g_t=r["g_t"], g_t_sector_weighted=r["g_t_sector_weighted"],
            )
            for r in rows
        ))

    async def microstructure_state(
        self, *, symbols: tuple[str, ...], from_ts: str, to_ts: str
    ) -> Ok[tuple[MicroState, ...]] | Err:
        sql = (
            "SELECT symbol, ts, spread_ar, spread_cs, amihud_illiq, "
            "signed_vol_imbalance, spread_quintile, imbalance_quintile, s_t "
            "FROM microstructure_state "
            "WHERE symbol = ANY($1) AND ts >= $2 AND ts <= $3 ORDER BY symbol, ts"
        )
        params = [list(symbols), datetime.fromisoformat(from_ts), datetime.fromisoformat(to_ts)]
        try:
            rows = await self._fetch(sql, params)
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        return ok(tuple(
            MicroState(
                symbol=r["symbol"], ts=ist_timestamp(r["ts"]),
                spread_ar=r["spread_ar"], spread_cs=r["spread_cs"],
                amihud_illiq=r["amihud_illiq"],
                signed_vol_imbalance=r["signed_vol_imbalance"],
                spread_quintile=r["spread_quintile"],
                imbalance_quintile=r["imbalance_quintile"], s_t=r["s_t"],
            )
            for r in rows
        ))

    async def _fetch(self, sql: str, params: list) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql, *params)
