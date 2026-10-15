import asyncio, asyncpg, sys, os
sys.path.insert(0, os.getcwd())
from seraph.store.bootstrap import resolve_dsn
async def m():
    c = await asyncpg.connect(resolve_dsn(), timeout=10)
    rows = await c.fetch("""SELECT rebalance_date, array_length(members,1) n, eligible_count,
                                   array_length(entrants,1) ent, array_length(leavers,1) lv, churn_fraction
                            FROM universe_snapshots ORDER BY rebalance_date""")
    print(f"snapshots: {len(rows)}")
    print(f"{'rebalance':<13}{'members':>9}{'eligible':>10}{'entrants':>10}{'leavers':>9}{'churn':>8}")
    print("-"*62)
    for r in rows:
        print(f"{str(r['rebalance_date']):<13}{(r['n'] or 0):>9}{(r['eligible_count'] or 0):>10}"
              f"{(r['ent'] or 0):>10}{(r['lv'] or 0):>9}{(r['churn_fraction'] or 0):>8.3f}")
    ns = [r['n'] or 0 for r in rows]
    print()
    print(f"members range        : {min(ns)} .. {max(ns)}")
    print(f"snapshots at exactly 500 : {sum(1 for n in ns if n==500)}/{len(ns)}")
    print(f"snapshots below 500      : {sum(1 for n in ns if n<500)}/{len(ns)}")
    # FR52 bug trap: rank-before-filter silently yields <500. Check eligible>=members always.
    bad = [(str(r['rebalance_date']), r['n'], r['eligible_count']) for r in rows
           if (r['eligible_count'] or 0) < (r['n'] or 0)]
    print(f"eligible_count < members (impossible) : {len(bad)}  {bad[:3]}")
    # duplicates within a snapshot
    dup = await c.fetchval("""SELECT count(*) FROM universe_snapshots
                              WHERE array_length(members,1) <> (SELECT count(DISTINCT x) FROM unnest(members) x)""")
    print(f"snapshots containing duplicate members: {dup}")
    await c.close()
asyncio.run(m())
