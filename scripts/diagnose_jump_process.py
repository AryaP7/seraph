#!/usr/bin/env python3
# C5 diagnostics — the measurements behind AMENDMENT-03.
"""Is NSE jump clustering SEQUENTIAL (Hawkes) or CONTEMPORANEOUS (common shock)?

Reports tie structure, overdispersion, count autocorrelation, and an
out-of-sample comparison of Poisson / negative-binomial / discrete-Hawkes on
identical data with session-boundary resets. Re-run this before changing any
Pillar 1 modelling decision.

Run: python scripts/diagnose_jump_process.py
"""

import asyncio, numpy as np, asyncpg
from collections import Counter
from scipy.optimize import minimize
from scipy.stats import nbinom
from seraph.features import extract_jumps
from seraph.ingestion.hawkes_universe import build_symbol_list
from seraph.store.bootstrap import resolve_dsn

async def load():
    pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=4)
    try:
        m = await pool.fetchval("SELECT members FROM universe_snapshots ORDER BY rebalance_date DESC LIMIT 1")
        syms = build_symbol_list(list(m)); ev=[]; grid=set()
        for s in syms:
            rows = await pool.fetch("SELECT ts, close FROM intraday_bars WHERE symbol=$1 ORDER BY ts", s)
            if len(rows) < 200: continue
            c=np.array([float(r["close"]) for r in rows]); ts=[r["ts"] for r in rows]
            out=extract_jumps(c)
            for i in np.flatnonzero(out["jump_sign"]==-1): ev.append(ts[i])
            grid.update(ts)
        return ev, sorted(grid)
    finally: await pool.close()

ev, grid = asyncio.run(load())
cnt=Counter(ev)
N=np.array([cnt.get(t,0) for t in grid], dtype=float)
sess=np.array([t.date() for t in grid])
new_session=np.r_[True, sess[1:]!=sess[:-1]]
print(f"bars={N.size:,}  events={int(N.sum()):,}  sessions={new_session.sum():,}")
print(f"mean={N.mean():.5f}  var={N.var():.5f}  var/mean={N.var()/N.mean():.2f}  max={int(N.max())}")

# --- Overdispersion: is contemporaneous clustering beyond Poisson? -------
print(f"\n[dispersion] Poisson expects var/mean = 1.0; observed {N.var()/N.mean():.2f}")
print(f"[dispersion] => contemporaneous clustering is {'SEVERE' if N.var()/N.mean()>3 else 'mild'}")

# --- Sequential dependence: lag-k autocorrelation of counts -------------
def acf(x,k):
    x=x-x.mean(); return float((x[:-k]*x[k:]).sum()/ (x*x).sum())
print(f"[sequential] count autocorrelation: " +
      "  ".join(f"lag{k}={acf(N,k):+.4f}" for k in (1,2,3,5,10,75)))

# --- Model comparison on identical data, out-of-sample ------------------
split=int(0.7*N.size); tr, te = N[:split], N[split:]
ns_te = new_session[split:]

def nll_pois(lam, x): 
    lam=max(lam,1e-12); return float(np.sum(lam - x*np.log(lam)))
def nll_nb(theta, x):
    mu,k = np.exp(theta[0]), np.exp(theta[1])
    if mu<=0 or k<=0: return 1e12
    p = k/(k+mu)
    return float(-np.sum(nbinom.logpmf(x, k, p)))
def nll_inar(theta, x, ns):
    log_mu, la, lb = theta
    mu=np.exp(log_mu); a=1/(1+np.exp(-la)); b=1/(1+np.exp(-lb))
    if a+b>=0.999: return 1e12
    base=mu/(1-a-b); prev_lam=base; prev_n=base; ll=0.0
    for i in range(x.size):
        if ns[i]: prev_lam, prev_n = base, base     # reset across sessions
        l=mu+a*prev_n+b*prev_lam
        if l<=0: return 1e12
        ll += x[i]*np.log(l)-l
        prev_lam, prev_n = l, x[i]
    return -ll if np.isfinite(ll) else 1e12

lam_hat=tr.mean()
r_nb=minimize(nll_nb, [np.log(tr.mean()), 0.0], args=(tr,), method="Nelder-Mead",
              options={"maxiter":3000})
ns_tr=new_session[:split]
r_in=None
for a0,b0 in ((0.1,0.5),(0.3,0.3),(0.05,0.85),(0.02,0.02)):
    x0=[np.log(max(tr.mean()*(1-a0-b0),1e-6)), np.log(a0/(1-a0)), np.log(b0/(1-b0))]
    r=minimize(nll_inar,x0,args=(tr,ns_tr),method="Nelder-Mead",options={"maxiter":5000})
    if r_in is None or r.fun<r_in.fun: r_in=r
mu_i=np.exp(r_in.x[0]); a_i=1/(1+np.exp(-r_in.x[1])); b_i=1/(1+np.exp(-r_in.x[2]))

oos = {
  "Poisson (constant rate)": nll_pois(lam_hat, te)/te.size,
  "NegBinomial (overdispersed, no dynamics)": nll_nb(r_nb.x, te)/te.size,
  "INAR/Hawkes-discrete (self-exciting)": nll_inar(r_in.x, te, ns_te)/te.size,
}
print(f"\n[out-of-sample nll per bar, lower is better]  test bars={te.size:,}")
for k,v in sorted(oos.items(), key=lambda kv: kv[1]): print(f"  {v:.5f}   {k}")
best=min(oos,key=oos.get)
print(f"\n[verdict] best out-of-sample: {best}")
print(f"[INAR params] mu={mu_i:.5f} a={a_i:.5f} b={b_i:.5f} -> n=a/(1-b)={a_i/max(1-b_i,1e-9):.5f}")
print(f"[NB params] mu={np.exp(r_nb.x[0]):.5f} k={np.exp(r_nb.x[1]):.4f} "
      f"(k->inf would be Poisson; small k = strong overdispersion)")
