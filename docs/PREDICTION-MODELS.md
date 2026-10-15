# Experimental predictive models

These additions are in the authorized experimental copy. They do not replace
Hawkes, RMT, Hamilton, the existing CSRS, or the original crisis-onset test.
They do not assert positive historical performance. `models.py` is a pure
array-level research layer without database access or writes.

## Target and decision time

The primary new endpoint is a loss of at least 10% from the decision close
within the **next 15 sessions**. It uses the minimum cumulative simple-return
path over sessions t+1 through t+15. This differs from a loss from an intervening
high (peak-to-trough drawdown). Today's return never enters today's label. The
last 15 labels, and any path with a missing return, are missing rather than
negative. This endpoint supplements the original pre-onset warning labels;
success on one endpoint must never be reported as success on the other.

Every decision is after today's close. Label i is eligible for training only
when i+15 <= t. The wrapper uses a maximum inclusive training index of t-15.
Features must already reflect information available by their decision time:
the wrapper cannot repair revised data, smoothed Hamilton probabilities,
future-selected universe membership, or previously optimized pillar settings.

## Small regularized future-loss challenger

`FutureLossLogit(feature_names, horizon=15, C=0.1, interactions=(), min_events=5)`
accepts an explicit feature schema and a short list of feature-name pairs.
For a three-input experiment, appropriate pairs to preregister include
`("hawkes", "rmt")` and `("hawkes", "hamilton")`. They are hypotheses about
conditional amplification, not guaranteed positive effects. Interactions are
optional and never selected automatically against test labels.

The model fits training-only median and IQR scales (standard-deviation fallback
for a zero IQR). Standardized inputs and pair products are clipped at magnitude
6. Missing observations are set to their training median. Entirely unobserved
training features stay inactive even if later populated. There is no learned
missingness indicator that could use changes in data coverage as a time proxy.
A row without any observed, trained feature receives no forecast.

The optimization is summed Bernoulli log loss divided by horizon plus
`||beta||²/(2*C)` and a weak intercept prior equivalent to half an observation
of each outcome. Dividing the likelihood by horizon increases shrinkage for
the heavily overlapping labels; it does **not** make them independent or
validate confidence intervals. Class balancing is deliberately absent to avoid
silently changing event base rates. `C=0.1` is a fixed research default, not an
empirically optimized or proven value.

If either outcome has fewer than five observed training labels, prediction is
an explicitly marked intercept-only historical-rate fallback:
`(positives + 0.5)/(observations + 1)`. Optimizer failures have a distinct fallback
status. Neither fallback constitutes successful trained three-pillar prediction.
No numerical probability is claimed to be calibrated without out-of-sample
calibration checks.

`walk_forward_predict(features, labels, feature_names, ...)` returns:

- `probability`: one positive-event probability per decision, or NaN.
- `train_end` and `fitted_at`: row indices documenting training maturity and refits.
- `training_count`, `fit_status`, `observed_features`: coverage and cold-start audit.
- `fits`: exact fitted coefficients, transforms, base rates, active features,
  optimizer status, and training boundaries for each refit.

The default minimum history is 756 mature labels, with 63-session refits and
expanding training. A fixed trailing window is available only when declared by
`max_train` before evaluation. Supplied onset labels can use the same wrapper
in a separately named experiment with their correct maturity horizon.

## EWMA/Student-t benchmark

`EWMAStudentTForecaster` is a simple fixed-parameter competitor: decay 0.94,
Student-t degrees of freedom 7, 60 contiguous sessions of warm-up, 20,000
simulated paths, seed 1729. It computes EWMA variance from log returns through
today and holds that variance constant over future zero-drift log-return paths.
The Student-t draws are scaled to unit variance. Common seeded simulation
draws make the series prefix-stable and reproducible. Missing observations
restart the warm-up, rather than being interpreted as zero returns.

The output includes path-loss probability, daily log-return volatility, status,
and Monte-Carlo standard error. That error is **simulation error only** and
is not uncertainty about model validity. Zero simulated crossings is a finite
simulation outcome, not a guarantee of zero risk. This benchmark is not GARCH,
not a marked Hawkes model, and not evidence of crisis prediction.

## Optional GJR-GARCH/Student-t benchmark

`gjr_garch_student_t_predict` uses the optional `arch` library to estimate a
zero-mean GJR-GARCH(1,1,1) with Student-t innovations. Fixed defaults are 756
past observations, 63-session refits, expanding estimation, 2,048 simulated
paths, and seed 1729. It estimates parameters through t-1, applies the observed
return at t to the variance recursion, and simulates the future loss path.
Asymmetric variance and heavy-tailed innovations are established library
features; the forecast recursion follows the library's documented approach.
See the [official model examples](https://arch.readthedocs.io/en/latest/univariate/univariate_volatility_modeling.html)
and [forecasting documentation](https://arch.readthedocs.io/en/latest/univariate/forecasting.html).

Missing daily returns reset history. Fits with no variation, failed convergence,
or invalid variance parameters emit no forecast and are logged. Output records
each training boundary, parameter set, fitted persistence, convergence flag,
and simulation error. Persistence near one is exposed rather than hidden;
out-of-sample calibration still decides whether the model is useful. This is a
benchmark and potential supplemental feature, not an additional original pillar.

## Validation controls

Tests perturb later features, later labels, and labels not yet mature at the
decision; prior forecasts must remain byte-identical. They independently verify
the off-by-one label definition, missing/incomplete horizons, one-class behavior,
inactive structural features, missing-data abstention, and baseline prefix
stability. These tests validate implementation causality, not economic skill.

Overlapping event labels need block-based uncertainty and chronological evaluation.
Thresholds, feature selection, hyperparameters, and external data publication
times are responsibilities of the protocol/evaluation layer. A COVID reconstruction
is retrospective because COVID already informed the research design.
