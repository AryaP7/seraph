"""C5 — seed the live native history from read-only E1 inputs (FR10–15).

Requires an explicit estimation window and candle timestamp convention.
Does not fit the pending F07 network or promote archived pillar estimates.

`--seed-members` and the point-in-time replay
---------------------------------------------
By default this seeds exactly the latest snapshot's basket, which is the
basket the live config declares. That is right for the live path and wrong for
a historical replay: `warm_native_hawkes_history.py --baskets dated` fits each
cadence point against the basket THAT EPOCH actually had, and a member which
has since left the universe has no rows in a history seeded from today's
basket alone. Measured on 2026-10-25, 70 symbols appeared in the dated epoch
baskets with no native rows at all, and every historical fit therefore failed
with `Incomplete common native-bar coverage` — 82 of 94 members incomplete at
the 2025-02-05 candidate.

`--seed-members dated-union` seeds the union of every snapshot's basket, so a
replayed epoch can see its own members. It does NOT change what the config
declares: `members` stays the latest basket, because that is the live
estimation basket and nothing about the live path should move when a replay
needs deeper inputs. The config records `seed_policy` and `seeded_members` so
an artefact says which it was built with rather than leaving it to be
inferred from row counts.
"""
import argparse
import asyncio
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def selected_schedule(config_path, requested=None):
    """Validate an explicit choice, preserving it when the history is reseeded."""
    from seraph.market_calendar.native_sessions import NativeSessionSchedule
    config_path = Path(config_path)
    if requested is not None:
        name = Path(os.path.relpath(Path(requested).resolve(), config_path.resolve().parent)).as_posix()
    elif config_path.exists():
        name = json.loads(config_path.read_text(encoding='utf-8')).get('session_schedule_file')
    else:
        name = None
    if name:
        NativeSessionSchedule.load(config_path.parent/name)
    return name


def seeded_symbols(policy, latest, earlier=()):
    """Which symbols to seed rows for, given the policy and the snapshots.

    `latest` is the declared estimation basket and is always seeded. Under
    'dated-union' every earlier snapshot's basket joins it, because a
    point-in-time replay fits each epoch against the members that epoch had.
    The declared basket itself is never widened by this — callers keep using
    `latest` for `members`.
    """
    if policy not in ('config', 'dated-union'):
        raise ValueError(f'Unknown seed policy {policy!r}')
    if policy == 'config':
        return sorted(latest)
    union = set(latest)
    for basket in earlier:
        union |= set(basket)
    return sorted(union)


async def prepare(args):
    import asyncpg
    from seraph.store.bootstrap import resolve_dsn
    from seraph.shared_types import IST
    from seraph.live.bars import Bar
    from seraph.pillars.hawkes.runtime import NativeHistory
    from seraph.ingestion.hawkes_universe import build_symbol_list
    now = datetime.now(IST)
    if date.fromisoformat(args.through) > now.date():
        raise ValueError('Cannot seed future native inputs')
    session_schedule_file = selected_schedule(args.config, getattr(args, 'session_schedule', None))
    conn = await asyncpg.connect(resolve_dsn())
    history = NativeHistory(args.config.with_suffix('.sqlite'))
    count = 0
    coverage = {}
    try:
        async with conn.transaction(readonly=True, isolation='repeatable_read'):
            snapshot = await conn.fetchrow('SELECT rebalance_date,members FROM universe_snapshots '
                'WHERE rebalance_date<=$1 ORDER BY rebalance_date DESC LIMIT 1', date.fromisoformat(args.through))
            if not snapshot:
                raise ValueError('No point-in-time basket is available')
            members = sorted(build_symbol_list(snapshot['members']))
            # The config keeps declaring the live basket; only what gets SEEDED
            # widens, so a dated replay can see each epoch's own members.
            policy = getattr(args, 'seed_members', 'config')
            earlier = []
            if policy == 'dated-union':
                earlier = [build_symbol_list(row['members']) for row in await conn.fetch(
                    'SELECT members FROM universe_snapshots '
                    'WHERE rebalance_date<=$1 ORDER BY rebalance_date',
                    date.fromisoformat(args.through))]
            seeded = seeded_symbols(policy, members, earlier)
            for symbol in seeded:
                rows = await conn.fetch('SELECT ts,close FROM intraday_bars WHERE symbol=$1 '
                    'AND ts<$2 ORDER BY ts', symbol,
                    datetime.fromisoformat(args.through+'T00:00:00+05:30')+timedelta(days=1))
                bars = []
                for row in rows:
                    stamp = row['ts'].astimezone(IST)
                    end = stamp + (timedelta(minutes=5) if args.bar_timestamps == 'start' else timedelta())
                    if end > now:
                        continue
                    close = float(row['close'])
                    bars.append(Bar(symbol, (end-timedelta(minutes=5)).isoformat(), end.isoformat(),
                                    close, close, close, close, 0, volume=None))
                history.append(bars, received_at=datetime.now(IST).isoformat(), source='research_E1_native_close')
                if bars:
                    coverage[symbol] = dict(bars=len(bars), first=bars[0].end, last=bars[-1].end)
                count += len(bars)
        config = dict(schema='native-hawkes-config/1', members=members,
            rebalance_date=snapshot['rebalance_date'].isoformat(), window_sessions=args.window_sessions,
            refit_sessions=5,
            history_file=history.path.name, prepared_at=datetime.now(IST).isoformat(),
            source_timestamp_label=args.bar_timestamps, source_through=args.through,
            basket_rule='existing CORE_N liquidity core plus provisional tariff representatives',
            seed_policy=getattr(args, 'seed_members', 'config'), seeded_members=len(seeded),
            native_rows=count, coverage=coverage,
            note='Partial or stale coverage remains unavailable; no fabricated bars or archived scores.')
        args.config.parent.mkdir(parents=True, exist_ok=True)
        if session_schedule_file:
            config['session_schedule_file'] = session_schedule_file
        temporary = args.config.with_suffix('.tmp')
        temporary.write_text(json.dumps(config, indent=2), encoding='utf-8')
        os.replace(temporary, args.config)
        print(json.dumps(dict(config=str(args.config), native_rows=count,
                              members=len(members), covered_members=len(coverage))))
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', required=True)
    parser.add_argument('--window-sessions', type=int, required=True)
    parser.add_argument('--bar-timestamps', choices=('start','end'), required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--session-schedule', type=Path,
                        help='Dated common-session evidence; an existing choice is preserved if omitted')
    parser.add_argument('--seed-members', choices=('config', 'dated-union'), default='config',
                        help="Which members to seed rows for. 'config' (default) seeds the latest "
                             "snapshot's basket, which is what the live path estimates on. "
                             "'dated-union' also seeds every earlier snapshot's basket, which a "
                             "point-in-time replay needs; the declared `members` is unchanged either way")
    args = parser.parse_args()
    if args.window_sessions < 1:
        parser.error('--window-sessions must be positive')
    asyncio.run(prepare(args))


if __name__ == '__main__':
    main()
