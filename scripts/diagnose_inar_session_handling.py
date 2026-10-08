"""Diagnose the INAR b=0 result and the session-reset handling before model selection."""
import asyncio, numpy as np, asyncpg, pickle
from collections import Counter
from scipy.optimize import minimize
from seraph.features import extract_jumps
from seraph.ingestion.hawkes_universe import build_symbol_list
from seraph.store.bootstrap import resolve_dsn

async def load():
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        m = await pool.fetchval("SELECT members FROM universe_snapshots ORDER BY rebalance_date DESC LIMIT 1")
        syms = build_symbol_list(list(m)); ev=[]; grid={}
        for s in syms:
            rows = await pool.fetch("SELECT ts, close FROM intraday_bars WHERE symbol=$1 ORDER BY ts", s)
            if len(rows)<200: continue
            c=np.array([float(r["close"]) for r in rows]); ts=[r["ts"] for r in rows]
            out=extract_jumps(c)
            for t in ts: grid[t]=grid.get(t,0)+1          # symbols ACTIVE in that bar
            for i in np.flatnonzero(out["jump_sign"]==-1): ev.append(ts[i])
        return ev, grid
    finally: await pool.close()

ev, grid = asyncio.run(load())
bars = sorted(grid)
cnt = Counter(ev)
N = np.array([cnt.get(t,0) for t in bars], float)          # jumps per bar
S = np.array([grid[t] for t in bars], float)               # symbols active per bar
day = np.array([t.date() for t in bars])
tod = np.array([t.hour*60+t.minute for t in bars])
new_sess = np.r_[True, day[1:]!=day[:-1]]
pickle.dump({"N":N,"S":S,"day":day,"tod":tod,"new_sess":new_sess},
            open(r"C:/Users/Arlop/AppData/Local/Temp/p1_data.pkl","wb"))
print(f"bars={N.size:,} events={int(N.sum()):,} sessions={new_sess.sum():,} "
      f"symbols/bar median={np.median(S):.0f}")

# ---- 1. WHY b = 0? Profile the likelihood over b, session-aware ----------
def nll(theta, x, ns, reset="mu"):
    log_mu, la, lb = theta
    mu=np.exp(log_mu); a=1/(1+np.exp(-la)); b=1/(1+np.exp(-lb))
    if a+b>=0.9995: return 1e12
    base = mu if reset=="mu" else mu/(1-a-b)
    lam=base; prev=base; ll=0.0
    for i in range(x.size):
        if ns[i]: lam, prev = base, base
        l = mu + a*prev + b*lam
        if l<=0: return 1e12
        ll += x[i]*np.log(l)-l
        lam, prev = l, x[i]
    return -ll if np.isfinite(ll) else 1e12

def fit(x, ns, reset="mu", fix_b=None):
    best=None
    for a0,b0 in ((0.1,0.5),(0.3,0.3),(0.05,0.85),(0.02,0.02),(0.5,0.4)):
        if fix_b is not None: b0=fix_b
        x0=[np.log(max(x.mean()*(1-a0-b0),1e-6)), np.log(a0/(1-a0)), np.log(max(b0,1e-6)/(1-max(b0,1e-6)))]
        if fix_b is not None:
            f=lambda th: nll([th[0],th[1],np.log(max(fix_b,1e-9)/(1-max(fix_b,1e-9)))], x, ns, reset)
            r=minimize(f, x0[:2], method="Nelder-Mead", options={"maxiter":3000})
            r.x=np.r_[r.x, np.log(max(fix_b,1e-9)/(1-max(fix_b,1e-9)))]
        else:
            r=minimize(nll,x0,args=(x,ns,reset),method="Nelder-Mead",options={"maxiter":5000})
        if best is None or r.fun<best.fun: best=r
    mu=np.exp(best.x[0]); a=1/(1+np.exp(-best.x[1])); b=1/(1+np.exp(-best.x[2]))
    return mu,a,b,best.fun

sub = N[:60000]; ns_sub = new_sess[:60000]
print("\n[b-profile] fixing b, refitting mu and a (session reset -> mu):")
print(f"{'b':>8} {'mu':>10} {'a':>8} {'a+b':>8} {'nll':>14}")
for bfix in (0.0, 0.05, 0.2, 0.5, 0.8, 0.95):
    mu,a,b,f = fit(sub, ns_sub, reset="mu", fix_b=bfix)
    print(f"{bfix:>8.2f} {mu:>10.5f} {a:>8.4f} {a+bfix:>8.4f} {f:>14.2f}")

print("\n[reset handling] free fit under two session-reset conventions:")
for reset in ("mu","uncond"):
    mu,a,b,f = fit(sub, ns_sub, reset=reset)
    base = mu if reset=="mu" else mu/max(1-a-b,1e-9)
    print(f"  reset={reset:>7}: mu={mu:.5f} a={a:.4f} b={b:.4f} a+b={a+b:.4f} "
          f"session-start lambda={base:.4f}  nll={f:.2f}   (data mean={sub.mean():.4f})")
