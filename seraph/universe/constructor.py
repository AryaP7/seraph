# C3 — Universe Constructor (FR52, FR54)
"""Point-in-time universe reconstruction by liquidity rank.

FR52, in order — the order *is* the requirement:
  1. FILTER to symbols with >= 1000 trading days of listing history as at the
     rebalance date;
  2. RANK the eligible set by six-month median daily traded value (TOTTRDVAL);
  3. TAKE the top 500.
Ranking before filtering silently yields fewer than 500 names and is a named
bug trap in the spec.

Floating N (approved decision, 2026-08-23). Measured against the real corpus,
only 361 symbols clear the 1000-day filter at Jan-2008 and 412 at Jan-2009;
500 is first reachable in mid-2010. Rather than ship a silent short universe or
drop the GFC epoch, the realised size floats:

    N_t = min(500, eligible_t)

and Q_t = T / N_t is recomputed per rebalance by C6, with Marchenko-Pastur
bounds evaluated at Q_t. N_t = 500 (hence Q_t = 2) holds from roughly mid-2010
onward, i.e. for most of the corpus; earlier dates run at Q_t > 2 and are
labelled. A shortfall against the 500 target always raises
UNIVERSE_UNDERFILLED carrying the exact shortfall.

D3's buffer is scaled to the realised size: an incumbent is retained while its
rank <= 1.10*N_t, an entrant admitted only at rank <= 0.90*N_t. At N_t = 500
that is exactly D3's 550 / 450, so the decision is unchanged where it was
specified and merely well-defined where it was not.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import asyncpg

from seraph.shared_types import (
    Err,
    InsufficientHistory,
    MissingDependency,
    Ok,
    SeraphWarning,
    SourceUnavailable,
    UniverseRule,
    UniverseSnapshot,
    err,
    ok,
)
from seraph.store.bootstrap import resolve_dsn
from seraph.universe.instrument_type import is_equity

TARGET_N = 500
MIN_LISTING_DAYS = 1000
BUFFER_INCUMBENT_FACTOR = 1.10   # D3: 550 at N=500
BUFFER_ENTRANT_FACTOR = 0.90     # D3: 450 at N=500
LOOKBACK_MONTHS = 6


@dataclass(frozen=True)
class SymbolStats:
    """One symbol's state as at a rebalance date."""

    symbol: str
    listing_days: int
    median_tottrdval: float


def rebalance_dates(from_year: int, to_year: int) -> tuple[str, ...]:
    """Semi-annual calendar, no lag — the agreed default for SPEC OQ6
    (ROADMAP §4). Membership takes effect on the rebalance date itself."""
    return tuple(
        f"{y:04d}-{m:02d}-01" for y in range(from_year, to_year + 1) for m in (1, 7)
    )


def build_snapshot(
    *,
    rebalance_date: str,
    panel,
    incumbents: tuple[str, ...] = (),
    target: int = TARGET_N,
    use_buffer: bool = True,
    min_listing_days: int = MIN_LISTING_DAYS,
    equities_only: bool = True,
) -> Ok[UniverseSnapshot] | Err:
    """Pure core of FR52 — no I/O, so CT-2 drives it with a synthetic panel."""
    panel = list(panel)
    if not panel:
        return err(InsufficientHistory(
            required=min_listing_days, available=0, as_of=rebalance_date
        ))

    # STEP 1 — FILTER. Must precede the rank (FR52 bug trap).
    # FR52 selects NSE *equities*: exclude ETFs and fund units, which otherwise
    # rank highly on traded value and inject mechanical correlation into C_t
    # (see universe/instrument_type.py).
    eligible = [
        s for s in panel
        if s.listing_days >= min_listing_days and (not equities_only or is_equity(s.symbol))
    ]
    if not eligible:
        return err(InsufficientHistory(
            required=min_listing_days,
            available=max(s.listing_days for s in panel),
            as_of=rebalance_date,
        ))

    # STEP 2 — RANK by six-month median traded value, descending. The symbol
    # name breaks ties so a snapshot is reproducible run to run.
    ranked = sorted(eligible, key=lambda s: (-s.median_tottrdval, s.symbol))
    rank_of = {s.symbol: i + 1 for i, s in enumerate(ranked)}

    # STEP 3 — TAKE. N floats down to the eligible count, never up past target.
    n_target = min(target, len(ranked))

    if use_buffer and incumbents:
        keep_rank = round(BUFFER_INCUMBENT_FACTOR * n_target)
        admit_rank = round(BUFFER_ENTRANT_FACTOR * n_target)
        held = set(incumbents)
        selected = [
            s.symbol for s in ranked
            if s.symbol in held and rank_of[s.symbol] <= keep_rank
        ]
        selected += [
            s.symbol for s in ranked
            if s.symbol not in held and rank_of[s.symbol] <= admit_rank
        ]
        selected = sorted(set(selected), key=lambda sym: rank_of[sym])
        if len(selected) > n_target:
            selected = selected[:n_target]
        elif len(selected) < n_target:
            chosen = set(selected)
            for s in ranked:
                if len(selected) >= n_target:
                    break
                if s.symbol not in chosen:
                    selected.append(s.symbol)
                    chosen.add(s.symbol)
            selected.sort(key=lambda sym: rank_of[sym])
        members = tuple(selected)
    else:
        members = tuple(s.symbol for s in ranked[:n_target])

    prior = set(incumbents)
    current = set(members)
    entrants = tuple(sorted(current - prior, key=lambda sym: rank_of[sym]))
    leavers = tuple(sorted(prior - current))
    churn = (len(entrants) / len(members)) if members else 0.0

    warnings: list[SeraphWarning] = []
    if len(members) < target:
        warnings.append(SeraphWarning(
            code="UNIVERSE_UNDERFILLED",
            message=(
                f"only {len(members)} of {target} members at {rebalance_date} — "
                f"N floats to the eligible count and Q_t = T/N_t must be "
                f"recomputed for this date; readings are not comparable to "
                f"full-size dates without annotation"
            ),
            context={
                "members": len(members),
                "target": target,
                "shortfall": target - len(members),
                "eligible": len(eligible),
                "rebalanceDate": rebalance_date,
            },
        ))

    return ok(
        UniverseSnapshot(
            rebalance_date=rebalance_date,
            members=members,
            eligible_count=len(eligible),
            entrants=entrants,
            leavers=leavers,
            churn_fraction=churn,
            rule=UniverseRule(),
        ),
        tuple(warnings),
    )


class UniverseConstructor:
    """S3 — the DB-backed constructor. Reads daily_prices; writes
    universe_snapshots and the universe_member_flag."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str | None = None) -> "UniverseConstructor":
        pool = await asyncpg.create_pool(resolve_dsn(dsn), min_size=1, max_size=4)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def panel_at(self, as_of: str) -> list[SymbolStats]:
        """Listing history and six-month median traded value per symbol."""
        rows = await self._pool.fetch(
            f"""
            SELECT symbol,
                   max(listing_days_to_date) AS listing_days,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY tottrdval)
                       AS median_tottrdval
            FROM daily_prices
            WHERE date <= $1::date
              AND date >  $1::date - INTERVAL '{LOOKBACK_MONTHS} months'
            GROUP BY symbol
            """,
            date.fromisoformat(as_of),
        )
        return [
            SymbolStats(
                symbol=r["symbol"],
                listing_days=int(r["listing_days"] or 0),
                median_tottrdval=float(r["median_tottrdval"] or 0.0),
            )
            for r in rows
        ]

    async def build(
        self, as_of: str, *, use_buffer: bool = True
    ) -> Ok[UniverseSnapshot] | Err:
        """Build one rebalance snapshot, carrying the previous snapshot's
        members forward as incumbents so the D3 buffer has something to hold."""
        try:
            panel = await self.panel_at(as_of)
            prev = await self._previous_members(as_of)
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        return build_snapshot(
            rebalance_date=as_of, panel=panel, incumbents=prev, use_buffer=use_buffer
        )

    async def _previous_members(self, as_of: str) -> tuple[str, ...]:
        row = await self._pool.fetchrow(
            "SELECT members FROM universe_snapshots WHERE rebalance_date < $1::date "
            "ORDER BY rebalance_date DESC LIMIT 1",
            date.fromisoformat(as_of),
        )
        return tuple(row["members"]) if row else ()

    async def persist(self, snap: UniverseSnapshot) -> Ok[int] | Err:
        """Store the snapshot. Idempotent on rebalance_date."""
        try:
            await self._pool.execute(
                """
                INSERT INTO universe_snapshots
                    (rebalance_date, members, eligible_count, entrants, leavers,
                     churn_fraction, rule)
                VALUES ($1::date, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (rebalance_date) DO UPDATE SET
                    members = EXCLUDED.members,
                    eligible_count = EXCLUDED.eligible_count,
                    entrants = EXCLUDED.entrants,
                    leavers = EXCLUDED.leavers,
                    churn_fraction = EXCLUDED.churn_fraction,
                    rule = EXCLUDED.rule
                """,
                date.fromisoformat(snap.rebalance_date),
                list(snap.members), snap.eligible_count,
                list(snap.entrants), list(snap.leavers), snap.churn_fraction,
                snap.rule.model_dump_json(by_alias=True),
            )
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        return ok(len(snap.members))

    async def apply_membership_flags(
        self, snap: UniverseSnapshot, until: str
    ) -> Ok[int] | Err:
        """Stamp universe_member_flag over [rebalance_date, until). C3 owns
        this column — C2 never writes it."""
        try:
            status = await self._pool.execute(
                """
                UPDATE daily_prices SET universe_member_flag = (symbol = ANY($3))
                WHERE date >= $1::date AND date < $2::date
                """,
                date.fromisoformat(snap.rebalance_date),
                date.fromisoformat(until),
                list(snap.members),
            )
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        return ok(int(status.split()[-1]))

    async def members_at(self, on_date: str) -> Ok[tuple[str, ...]] | Err:
        try:
            row = await self._pool.fetchrow(
                "SELECT members FROM universe_snapshots WHERE rebalance_date <= $1::date "
                "ORDER BY rebalance_date DESC LIMIT 1",
                date.fromisoformat(on_date),
            )
        except (OSError, asyncpg.InterfaceError, asyncpg.PostgresError):
            return err(SourceUnavailable(source="postgres", http_status=None))
        if row is None:
            return err(MissingDependency(
                entity="universe_snapshots", as_of=f"{on_date}T00:00:00+05:30"
            ))
        return ok(tuple(row["members"]))

    async def validate_against_official_index(self, frm: str, to: str) -> Err:
        """FR54 — representativeness evidence. Blocked until the official Nifty
        500 index level series is ingested (FR2); returns an honest
        MISSING_DEPENDENCY rather than a fabricated correlation."""
        return err(MissingDependency(
            entity="nifty500_index_level", as_of=f"{to}T00:00:00+05:30"
        ))
