# Causal research extensions to the three original pillars

This experimental copy retains the original Hawkes, RMT and Hamilton engines.
`seraph/prediction/pillars.py` adds separately named daily variants for research;
it does not replace their stored outputs, rewrite their historical results, or
claim compliance with every original FR10–FR24 acceptance criterion. The user
authorized model amendments in this separate copy. These are hypotheses, not
evidence that a crisis has become predictable.

## Interface and information boundary

```python
result = build_pillar_features(
    market_returns,           # (n,) daily decimal returns, ascending dates
    factor_returns,           # (n,k), 2 <= k <= 64, fixed column identities
    daily_jump_counts=None,   # optional genuine intraday jumps aggregated daily
    config=PillarConfig(),
)
```

`result.values` contains same-length NumPy arrays. `NaN` means not available,
including initial training history. `result.diagnostics` records the fixed
configuration and every successful model fit's inclusive start index and
exclusive end index. The caller must preserve ascending date alignment and map
those indices back to dates in its run manifest.

Each emission at index t is available **after the close of session t**. It may
use that session's observed returns. Every fitted model emitted at t is trained
on observations through t−1, never future observations. Training windows contain
at most 1,000 sessions and refits occur every 63 sessions after at least 252
observed training returns/counts. The fixed defaults are a newly declared 2026
research plan. Their retrospective use does not make the research historically
preregistered or COVID an untouched holdout.

No function performs I/O, ingests future labels, downloads data, or writes to the
original project/database. These research NumPy APIs are outside the existing
typed production C5/C6/C7 interfaces and do not modify `shared_types`.

## Hawkes: separate daily tail-event and intraday-count variants

The daily tail proxy defines

\[
 N_t=1\{r_t<-2\sqrt{v_{t-1}}\},\qquad
 v_t=.94v_{t-1}+.06r_t^2.
\]

The first observed squared return initializes variance; twenty observed returns
are required before defining events. The threshold uses **prior** variance, so
a loss cannot inflate its own event threshold. No future quantiles are used.

The count conditional mean has a fixed five-session half-life:

\[
 d_{t+1}=\phi d_t+(1-\phi)N_t,\quad
 \phi=2^{-1/5},\quad
 E[N_{t+1}\mid\mathcal F_t]=\mu+n d_{t+1},\quad 0\leq n\leq .95.
\]

Normalizing the geometric kernel makes n the branching coefficient. The fit
minimizes Poisson negative log likelihood on strictly prior count/driver pairs,
using an analytic gradient. For binary market exceedances this is explicitly a
**quasi-Poisson conditional-count proxy**, not a calibrated Bernoulli probability
and not the original five-minute Hawkes stream. At least five training events
are required. Five is a numerical eligibility floor, not evidence of precise
parameter estimates. A fit at n=0 is valid evidence that this specification
found no excitation; it is not forcibly changed to make Hawkes influential.

Outputs are `hawkes_daily_intensity`, `hawkes_daily_branching` and
`hawkes_daily_excitation_ratio`. The last is next-session intensity divided by
the fitted stationary mean `mu/(1-n)`, not by the immigration rate. The new
five-day decay is a fixed research hypothesis; it was not estimated from the
full future corpus and is not an assertion that excitation lasts five days.

If genuine intraday jump counts are supplied, the same daily count recursion
also emits separate `hawkes_intraday_count_*` features. This does not restore
missing pre-2015 intraday coverage. Missing counts are never set to zero; they
reset excitation history and require a full new count-history warmup. Daily
tail events remain explicitly labelled a proxy across the entire sample.

Any supplied count series needs a stable or exposure-adjusted observation
universe. This module does not correct counts for changes in the number of
observed symbols. Raw count changes caused by coverage must not be interpreted
as contagion. Both channels are diagnostics of a fitted conditional mean;
forecast calibration and incremental warning performance are tested elsewhere.

## RMT: fast/slow covariance spectra on a small fixed panel

The complementary channel computes 60- and 252-session sample correlations with
fixed ten-percent identity shrinkage:

\[
 C_t^{shrunk}=.9C_t+.1I,\qquad q_t=\lambda_1(C_t^{shrunk})/k_t.
\]

Both windows use identical column support when the slow window is available.
Only fully observed, nonconstant columns qualify. No future fill, pairwise
correlation repair, MP p-value, or fixed 500-name aspect ratio is asserted.
Leading-vector rotation uses the previous and current vectors restricted to
their common column identities, renormalized before the absolute dot product.
The absolute value makes rotation invariant to eigenvector sign. A repeated
leading eigenvalue has no identifiable leading direction; rotation is then
unavailable rather than fabricated.

Outputs are `rmt_fast_leading_share`, `rmt_slow_leading_share`,
`rmt_fast_minus_slow`, `rmt_fast_rotation` and `rmt_panel_n`. The last is a
coverage diagnostic, **not an intended predictor**. The module does not emit
MP significance: the shrunk, heavy-tailed, serially dependent panel would need
its own null calibration.

The first repository snapshot supplies ten deterministic hash-bucket portfolios
from the historical eligible universe. They are **not economic sectors** and
must not be described as sectors. Their averaging suppresses idiosyncratic
noise and can mechanically make the common eigenvalue large. Changes in their
spectrum are an alternative portfolio-dependence channel, not an equivalent
replacement for the original large-universe RMT estimator. Historical membership
and return construction remain a separate data-quality responsibility.

## Hamilton: restricted three-state variance-switching model

The daily model is

\[
 r_t\mid S_t=j\sim N(0,\sigma_j^2),\qquad
 P(S_{t+1}=j\mid S_t=i)=A_{ij},\quad j\in\{0,1,2\}.
\]

The transition matrix is row stochastic. EM learns three variances and a
constant transition matrix on each training window. It uses diagonal transition
pseudocounts of 2 plus 0.01 in every cell and a variance floor at five percent
of the training mean squared return. These regularizers prevent numerical
collapse; they do **not** prove identification of three economically different
regimes. Fits record convergence, occupancy and variance separation so weak
regime evidence remains visible. The fixed 80-iteration cap and stopping rule
(relative MAP objective improvement below 1e-6 or parameter movement below
1e-5) limit runtime. Iteration-limited fits are recorded as such.

Parameters start deterministically from a persistent matrix and variance
multiples (.3, 1, 3) of the past training mean square. States are relabelled by
increasing fitted variance. Names tranquil/stressed/crisis therefore mean low,
middle and high conditional volatility **within that training window**. They
are not supervised crisis labels, and their semantics can vary across fits.

Training EM uses backward smoothing only inside the past training window for
parameter estimation. Emissions use a fresh forward-only Hamilton recursion:

\[
 \pi_{t|t}\propto(\pi_{t-1|t-1}A)\odot f(r_t),\quad
 \pi_{t+1|t}=\pi_{t|t}A.
\]

Missing observations have unit likelihood and propagate the prior without an
artificial measurement. A re-estimated model refilters its past training window
to initialize the current state; already emitted historical values are not
revised. The first observation uses a uniform state prior.

Outputs include the three filtered probabilities,
`hamilton_daily_next_crisis_prob`, `hamilton_daily_next_volatility` and
`hamilton_daily_lsd`. Next volatility is
`sqrt((filtered_probability @ A) @ fitted_variances)`, a one-session conditional
standard deviation, not an annualized volatility. Next crisis probability is
the probability of the fitted high-volatility state, **not a probability of a
named historical crisis or a specified future drawdown**.

This restricted Gaussian model omits GARCH dynamics, Student-t tails and TVTP.
It is a computationally modest challenger to the original multivariate engine,
which remains present. The explicit forward/backward implementation is audited
against exhaustive enumeration of short state paths rather than offered as a
new substitute for `statsmodels` in the original production component.

## Keeping the empirical comparison small

A suggested preset three-pillar feature set is daily Hawkes intensity, fast RMT
leading share/fast-minus-slow, and Hamilton next-session volatility. Do not pass
every redundant state probability, LSD and coverage count into a small-event
classifier simply because the API exposes them. Standalone and family-ablation
results must reveal whether a pillar contributes information. Retaining all
three pillars does not authorize inventing their statistical contribution.

Eight tests cover complete prefix invariance, independent exact Hamilton
filtering, missing-observation propagation, strictly past fit ranges, valid
probabilities/branching bounds, explicit missing count coverage, constant-factor
handling, repeated-eigenvalue ambiguity and invalid inputs. These are mathematical/data-causality checks, not
evidence of predictive skill on real crises.

The initial smoke run on the 5,361-session local snapshot produced overlapping
availability for all three new variants on 5,089 sessions. Hamilton had 82
refits, of which 75 met the convergence criterion and seven hit the cap; Hawkes
had 81 successful refits. Runtime was about 17 seconds on this machine. These
figures describe execution and eligibility, not a validated early-warning rate.

## Original-file verification and copied classification dependency

Read-only verification of `source_original_manifest.json` found all 307 recorded
original files unchanged (zero missing files and zero SHA-256 mismatches).
This covers the manifest's recorded files, not every unlisted original asset.

The initial broad non-DB regression run exposed a missing-copy dependency:
`is_equity()` falls back to accepting every symbol when the vendored ISIN CSV
is absent, causing ETF exclusion's CT2 assertion to fail. The existing public
classification file was copied unchanged into
`vendor/eod2/src/eod2_data/isin.csv` (248,628 bytes) from the same relative path
under `C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya/`. Its SHA-256 is
`e2bcf928b2ed9aada8ef74a1874ec6d4d9823de4b407c1ee6d06788eda3989a7`.
All six CT2 tests then passed. This restores an inherited dependency; it does
not alter original files or retrospectively repair a source-data universe.

Regression verification on 2026-10-14 covered the suite in partitions to bound
the expensive original Hamilton fits. After restoring the missing CSV, the
unique aggregate was **262 passed, 8 skipped, 2 expected failures, no unresolved
failures** at that checkpoint. The original broad pass reported 234 passed and the one CSV-dependent
failure; a targeted CT2 rerun corrected that failure. Eight inexpensive Hamilton
checks and all nineteen expensive Hamilton/policy tests then passed. Overlapping
CT2 reruns are not double-counted in the aggregate.

Every test subprocess set `SERAPH_DB_DSN` to a disabled localhost port (1), so
even collection-time database probes could not touch the original database or
the experimental database. The eight skips comprise two ingestion DB tests,
four CT3 intraday-data tests and two Hawkes-writer DB tests. Two inherited
expected failures existed at that checkpoint: the Lee–Mykland threshold-scaling
specification pin and the FR35 Table B fold-count conflict. The later
[C4 calibration amendment](AMENDMENT-RESEARCH-JUMP-CALIBRATION.md) fixes the first
with actual extraction and prefix-invariance regressions. The FR35 conflict
remains an expected failure.
All five mechanical invariant checks also passed.

The expensive test groups completed within their individual 300-second limits:
original Hamilton (7 tests, 275.78 seconds), Hamilton causality (5 tests,
243.05 seconds), regime recovery (6 tests, 223.34 seconds) and policy integration
(1 test, 200.80 seconds). Database integration was not exercised by this run.

The final accumulated count, including 30 additional evaluation/hazard/viewer
tests run by the other workstreams and four net additional C4 tests, is
**297 passed, 8 database skips, 1 expected failure** (306 collected tests).
Counts combine distinct tests from partitioned runs; this is not a claim that
all 306 were rerun together in a single pytest invocation. The C4 amendment does
not modify prediction-v1's daily Hawkes/RMT/Hamilton features or replay results.

## Reference implementations and distinctions

- [Statsmodels Hamilton examples](https://www.statsmodels.org/stable/examples/notebooks/generated/markov_autoregression.html)
  distinguish filtered and smoothed probabilities and include a three-state
  variance-switching example. The research implementation above uses its own
  explicitly restricted model; this is not a claim of numerical equivalence.
- [Scikit-learn covariance guide](https://scikit-learn.org/stable/modules/covariance.html)
  documents identity shrinkage. This module uses a fixed coefficient rather
  than describing that coefficient as a Ledoit-Wolf estimate.
