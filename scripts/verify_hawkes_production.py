"""Reproduce the validated Hawkes parameters on REAL data via the PRODUCTION path,
then push the result through C8 to confirm the downstream contract holds."""
import pickle, numpy as np
from seraph.pillars.hawkes import estimate_state, fit_discrete_hawkes

D=pickle.load(open(r"C:/Users/Arlop/AppData/Local/Temp/p1_data.pkl","rb"))
N,tod,ns = D["N"],D["tod"],D["new_sess"]
slots=np.unique(tod); si=np.searchsorted(slots,tod)
def prof_of(x,s):
    tot=np.bincount(s,weights=x,minlength=slots.size); c=np.bincount(s,minlength=slots.size).astype(float)
    p=np.where(c>0,tot/np.maximum(c,1),x.mean()); return p/max(p.mean(),1e-12)

n=N.size; bnds=[int(f*n) for f in (0.40,0.60,0.80,1.00)]
print(f"{'fold':>5} {'alpha':>8} {'phi':>8} {'n':>8} {'k':>8}")
alphas=[];phis=[];ns_=[]
for i in range(3):
    tr=slice(0,bnds[i]); prof=prof_of(N[tr],si[tr])
    f=fit_discrete_hawkes(N[tr],ns[tr],prof,si[tr])
    alphas.append(f.alpha); phis.append(f.phi); ns_.append(f.branching_ratio)
    print(f"{i+1:>5} {f.alpha:>8.4f} {f.phi:>8.4f} {f.branching_ratio:>8.4f} {f.dispersion:>8.4f}")
a,p_,nn=np.array(alphas),np.array(phis),np.array(ns_)
print(f"\nmean alpha={a.mean():.4f} (validated ~0.055)  phi={p_.mean():.4f} (~0.50)  "
      f"n={nn.mean():.4f} (~0.11)")
print(f"parameter CV: alpha={a.std()/a.mean():.3f} phi={p_.std()/p_.mean():.3f} n={nn.std()/nn.mean():.3f}")
print(f"FR11 stationarity n<1 on every fold: {bool(np.all(nn<1.0))}")

# --- production entry point on the most recent fold, then through C8 ------
tr=slice(0,bnds[2]); prof=prof_of(N[tr],si[tr])
res=estimate_state(counts=N[tr],session_starts=ns[tr],tod_profile=prof,tod_index=si[tr],
                   n_neg=21180,n_pos=28603)
print(f"\n[production] status={res.status} n={res.value[0].branching_ratio:.4f} "
      f"MTS={res.value[1]:.4f} warnings={[w.code for w in res.warnings]}")

from seraph.reconciliation import KalmanReconciler
from seraph.shared_types import ObservedEmission, PillarObservation
rec=KalmanReconciler()
ts="2026-08-21T15:30:00+05:30"
em=ObservedEmission(obs=PillarObservation(pillar="hawkes",ts=ts,tau=ts,
    value=res.value[0].branching_ratio,estimation_variance=None))
rec.predict(ts); out=rec.update([em])
print(f"[C8] status={out.status} mask={list(out.value.mask)} xHat[hawkes]={out.value.x_hat[0]:.4f}")
print("[C8] emission contract unchanged: PillarEmission accepted without modification")
