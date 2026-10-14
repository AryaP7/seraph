# Post-fix plain causal re-run: stopped deliberately after block 0

Started 2026-10-13 02:30Z, stopped after block 0 completed.

**Reason.** Block 0 returned `llf=16677.68 conv=True min_offdiag=-7.105e-15`,
against the pre-fix run's `llf=16677.67 conv=True min_offdiag=-7.105e-15`
(`../20261012T134047Z-hamilton-causal-REAL/REPORT.md` §1, block 0). Identical.

That is the expected result and it is informative: `MarkovSwitching._em_iteration`
short-circuits the transition block under TVTP ("EM with TVTP is not yet
supported"), so the `_conditional_loglikelihoods` shape defect repaired in C7
this session never fired on the TVTP path. The filter and Kim smoother
marginalise correctly over the broadcast `S_{t-1}` axis either way, so the TVTP
likelihood is invariant to the fix — which block 0 now demonstrates on real data
rather than by argument.

Running the remaining 13 blocks would therefore have reproduced
`20261012T134047Z-hamilton-causal-REAL` to rounding, at ~110 minutes of CPU,
while telling us nothing new. The pre-fix run stands as the baseline.

**What this means.** The TVTP identification failure (6/14 nesting violations to
LR = -2,322.88, 3/14 non-converged, NFR17 0.269 sigma) is a **separate defect**
from the EM shape bug, and the fix does not address it. It is diagnosed and
attacked separately — see `../HAMILTON-REGIME-SUPPORT.md` and the TVTP warm-start
experiment.

Nothing was persisted by this run. `causal_run.json` / `.npz` were not produced.
