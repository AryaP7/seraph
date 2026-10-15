# SERAPH redesign decisions

## Diagnosis

The original CSRS combines contemporaneous diagnostics. An ECDF rank of stress
is not `P(crisis in the next h sessions)`. Hawkes measures clustering of events
already visible; RMT measures common cross-sectional structure; a Hamilton
filter infers latent state from observations. Each can be informative about
conditional risk without anticipating an external shock's first arrival.

The prior marginal-feature audit is evidence of failure on its tested screens.
Its language that there is no information any architecture could ever use is
too strong: unsuccessful marginal screens do not prove absence of conditional,
nonlinear or temporal information. The bounded new experiment tests one such
architecture honestly; it also does not establish useful onset prediction.

The copy keeps diagnostic measurement, future-target probability, and public
hazard watch as distinct quantities. A risk decision should expose which one
triggered it, its information date and its empirical error rate.

## Original pillars retained

| Family | Original implementation kept | Added research variant | Intended contribution |
|---|---|---|---|
| Hawkes | Intraday negative-jump event model | Stable daily-tail self-excitation | Conditional event clustering |
| RMT | Original spectrum and common-support rotation | 60/252-session shrinkage spectra of 10 fixed stock portfolios | Fast versus slow dependence |
| Hamilton | Statsmodels TVTP engine | Restricted zero-mean three-state variance model, training-only EM and forward emissions | Next-state volatility context |

The variants make assumptions explicit and can operate across the available
daily history. Their outputs are not claimed equivalent to the original
estimators. All three enter the combined predictor; drop-one-family models
are controls testing incremental information, not proposed pillar removals.

The fusion's conditional variance is corrected to `a'Pa` where
`a=sum_j xi_j w_j`. Missing observations produce prediction uncertainty, not
virtual information. Both are correctness repairs, not sources of new
predictive information. See `EXPERIMENT-MATH.md` for derivations and limits.

## Why these libraries

Verified against primary project sources on 2026-10-14. A method implemented
in a serious risk library is not thereby proven to predict this dataset's
crisis labels, and no claim about a particular trading firm's private systems
is made.

| Library/repository | Relevant capability | Decision in this copy |
|---|---|---|
| [arch](https://github.com/bashtage/arch) and [model documentation](https://arch.readthedocs.io/en/latest/univariate/univariate_volatility_modeling.html) | GJR asymmetric conditional variance and Student-t innovations | Implemented as a causal path-loss benchmark, with fit failures visible |
| [statsmodels](https://www.statsmodels.org/stable/examples/notebooks/generated/markov_autoregression.html) | Hamilton filtering, variance switching, filtered versus smoothed probabilities | Original TVTP engine retained; reference for explicit restricted daily variant |
| [tick](https://github.com/X-DataInitiative/tick) | Hawkes process inference and simulation | Reference for event models; its continuous-time assumptions and Windows experimental support do not make it a drop-in repair for tied bar events |
| [skfolio](https://github.com/skfolio/skfolio) | Portfolio optimization and covariance estimators | Useful later for portfolio decisions; not installed as an alleged crisis predictor |
| [MSGARCH](https://github.com/keblu/MSGARCH) | Markov-switching GARCH and published risk-forecasting research | Independent benchmark candidate; R runtime not introduced merely to duplicate current state models |
| [Open Source Risk Engine](https://github.com/OpenSourceRisk/Engine) | Portfolio risk and valuation infrastructure | Relevant to scenario/exposure integration, not evidence of advance event forecasting |

The new small logistic layer uses NumPy/SciPy directly, with train-only median
and IQR transforms, regularization and no prevalence-distorting class weights.
It is intentionally small relative to the six labelled episodes. GJR variance
obeys `omega + alpha*r² + gamma*r²*I(r<0) + beta*h`, and standardized Student-t
paths are simulated forward. These distribution assumptions remain testable
assumptions; Monte Carlo standard errors do not include model uncertainty.

## Evidence discipline

At decision `t`, predictors use observations through `t`; parameter-estimation
cutoffs are saved. Supervised labels enter training only when `i+15<=t`. Alert
calibration reads only prior out-of-sample predictions and matured outcomes.
The next-session convention for dated WHO announcements is a disclosed
approximation because exact historical publication timestamps are incomplete.

Results include missed crises, false alerts, missing coverage, all ablations
and GJR fit failures. The paired Brier bootstrap is descriptive. None of these
results is an untouched holdout: earlier project work and COVID informed the
research. A fit on fewer rows does not erase that selection history.

## What an operational risk engine still needs

This copy supplies the historical research engine and a review interface.
Operational acceptance remains unmet. Required next evidence includes an
immutable timestamped observation archive, independently fixed crisis labels,
forward monitoring over new data, stable calibration and failure policies, and
measured portfolio risk decisions under realistic costs. General external
credit/policy feeds need uniform inclusion rules and all-event evaluation,
as the health register illustrates; hand-labelled winning headlines would
create another retrospective illusion.

Health declarations demonstrate a plausible public-information route to a
COVID watch. They do not predict every shock, validate the original pillars,
or solve the earlier taper/credit/policy crises. The saved results make that
boundary inspectable instead of concealing it behind a single composite score.
