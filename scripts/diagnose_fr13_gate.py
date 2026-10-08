"""FR13 diagnosis: what null is the asymmetry gate testing, and is 0.74 real?"""
import asyncio, numpy as np, asyncpg
from scipy.stats import binomtest
from seraph.features import extract_jumps
from seraph.ingestion.hawkes_universe import build_symbol_list, sector_of
from seraph.store.bootstrap import resolve_dsn

async def load():
    pool=await asyncpg.create_pool(resolve_dsn(),min_size=1,max_size=4)
    try:
        m=await pool.fetchval("SELECT members FROM universe_snapshots ORDER BY rebalance_date DESC LIMIT 1")
        per_sym={}; per_sec={}; series=[]
        for s in build_symbol_list(list(m)):
            rows=await pool.fetch("SELECT ts, close FROM intraday_bars WHERE symbol=$1 ORDER BY ts",s)
            if len(rows)<500: continue
            c=np.array([float(r["close"]) for r in rows]); ts=[r["ts"] for r in rows]
            o=extract_jumps(c); neg=int((o["jump_sign"]==-1).sum()); pos=int((o["jump_sign"]==1).sum())
            per_sym[s]=(neg,pos)
            sec=sector_of(s) or "market_residual"
            a,b=per_sec.get(sec,(0,0)); per_sec[sec]=(a+neg,b+pos)
            for i in np.flatnonzero(o["jump_sign"]!=0):
                series.append((ts[i], 1 if o["jump_sign"][i]==-1 else 0))
        return per_sym, per_sec, sorted(series)
    finally: await pool.close()

per_sym, per_sec, series = asyncio.run(load())
NEG=sum(v[0] for v in per_sym.values()); POS=sum(v[1] for v in per_sym.values()); J=NEG+POS
p_hat=NEG/J
print(f"total jumps={J:,}  negative={NEG:,}  positive={POS:,}")
print(f"downside share p = {p_hat:.4f}   raw ratio neg/pos = {NEG/POS:.4f}")

# 1. Is the market symmetric (H0: p = 0.5)?
bt=binomtest(NEG,J,0.5,alternative="two-sided")
z=(NEG-J*0.5)/np.sqrt(J*0.25)
print(f"\n[H0: p=0.5 symmetric]  z = {z:+.1f}   p-value = {bt.pvalue:.3e}")
print(f"  => the 5-minute NSE jump stream is {'NOT ' if bt.pvalue<0.01 else ''}symmetric; "
      f"positive jumps genuinely outnumber negative")

# 2. Is the baseline stable across symbols / sectors?
shares=np.array([v[0]/max(v[0]+v[1],1) for v in per_sym.values() if sum(v)>=50])
print(f"\n[per-symbol downside share] n={shares.size} mean={shares.mean():.4f} "
      f"sd={shares.std():.4f} min={shares.min():.4f} max={shares.max():.4f}")
print("[per-sector downside share]")
for sec,(a,b) in sorted(per_sec.items(), key=lambda kv:-sum(kv[1])):
    tot=a+b
    print(f"  {sec:<18} p={a/max(tot,1):.4f}  (n={tot:,})")

# 3. Would a windowed test against the MARKET BASELINE ever fire?
lab=np.array([d for _,d in series])
W=500
fires=[]
for i in range(0,lab.size-W,W):
    w=lab[i:i+W]; k=int(w.sum())
    fires.append(binomtest(k,W,p_hat,alternative="greater").pvalue < 0.05)
fires=np.array(fires)
print(f"\n[windowed gate vs market baseline p={p_hat:.4f}, W={W} jumps, alpha=0.05]")
print(f"  windows={fires.size}  fired={fires.sum()} ({100*fires.mean():.1f}%)")
print(f"  => gate is {'INFORMATIVE' if 0.01 < fires.mean() < 0.5 else 'DEGENERATE'}")
# and against the symmetric null, for contrast
f2=np.array([binomtest(int(lab[i:i+W].sum()),W,0.5,alternative="greater").pvalue<0.05
             for i in range(0,lab.size-W,W)])
print(f"  same test against p=0.5 instead: fired {f2.sum()}/{f2.size} ({100*f2.mean():.1f}%)")
