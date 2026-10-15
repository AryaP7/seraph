# Experimental mathematical amendments: reconciliation and composite uncertainty

This document applies only to **SERAPH-Research**, the separately authorized
experimental copy. The original project and its historical specifications
remain unchanged. These amendments explicitly supersede the incompatible
FR29 formula and D4/CT-4 saturation requirement in the copied historical
documents. They correct information accounting; they do not establish
advance-warning performance or calibrated confidence coverage.

The original three pillars remain in their fixed order: Hawkes, RMT, Hamilton.
No shared boundary schema was changed.

## 1. One uncertain pillar vector requires cross-regime covariance

The implemented point score uses a common uncertain pillar vector `x`:

```
c = sum_j xi[j] * w[j].T @ x = a.T @ x
a = sum_j xi[j] * w[j]
```

Conditioning on the supplied weights and regime probabilities, and writing
`P = Cov(x)`, elementary covariance propagation gives:

```
Var(c | xi, w) = a.T @ P @ a
              = sum_j sum_k xi[j] * xi[k] * w[j].T @ P @ w[k]
```

The historical formula retained only the `j == k` terms. It would be valid
for independent uncertain vectors per regime, but the implementation has
one shared vector. For three identical weight rows and uniform `xi`, the
score remains `w.T @ x`. The old formula spuriously returned one-third of
its variance. The corrected formula is invariant to how identical rows are
mixed.

This is **not** a latent random-regime mixture interval. For a random regime
`J` and conditional score moments `(m_j, v_j)`, total variance would be
`sum_j xi[j] * (v_j + (m_j - mean_m)**2)`. That is a different estimand.
Uncertainty in the fitted weights, regime probabilities, model parameters,
and data revisions is not included in the current conditional interval.

The score continues to clip its point inputs to `[0, 1]`. Its interval is a
local linear/Gaussian approximation based on the upstream covariance, not
the exact distribution of a clipped random variable, not a forecast loss
interval, and not a calibrated crisis probability. These limitations are
unchanged and must stay visible in research reporting.

Mask-renormalized weights are zero for an absent pillar. Consequently a
large variance in a structurally absent coordinate contributes nothing to
the composite variance. There is no need to manufacture a covariance cap.

## 2. Missing data supplies no measurement likelihood

For a random-walk state, prediction is:

```
x_pred = x_previous
P_pred = P_previous + Q * elapsed_bars
```

When no measurement arrives, those are also the posterior moments. The old
virtual update used the predicted mean as a synthetic observation. Its
innovation was zero, but its covariance still contracted. Repeated virtual
updates therefore generated certainty from no information.

The experimental implementation removes virtual updates completely. It
uses a Joseph-form covariance update only for an actual usable observation.
In particular:

- Omitted or unavailable emissions perform no scalar measurement update.
- A transient failure preserves the availability of a previously observed
  pillar; a failed first observation cannot promote an unseen prior into
  an available pillar.
- Structural absence excludes that pillar from the composite mask.
- `tau` records information vintage. An observation with `tau` at or before
  the last assimilated vintage is ignored with `STALE_OBSERVATION`, even if
  it is delivered at a new request timestamp or has a changed value.
- Revision of an already assimilated vintage requires an explicit replay;
  this simple online filter does not implement out-of-sequence corrections.
- A new but stale measurement can be assimilated once with age-inflated
  noise. This is a declared approximation to a delayed-observation model,
  not an exact state-augmentation treatment of delayed data.
- A measurement at the noise-saturation threshold is excluded and skipped;
  it does not contract covariance or advance the last-assimilated vintage.
- An observed signal that subsequently ages past that threshold is masked
  out even if the caller keeps repeating the same vintage. An explicitly
  transient absence retains its previously observed pillar per the existing
  D2 contract, with increasing prediction uncertainty.
- The complete batch is validated before state mutation. Duplicate pillars
  in one batch and nonfinite/negative-variance observations are rejected.

The bounded saturating observation-noise curve is retained for usable
delayed measurements. Bounded measurement noise does **not** mathematically
bound prediction covariance during absence and does **not** imply near-zero
Kalman gain if the prior covariance is large. Saturation is an explicit
staleness exclusion policy. A supplied zero measurement variance receives
a numerical floor of `1e-12` to avoid degeneracy; this is not calibration.

Under prolonged absence, a random walk's covariance can grow without bound.
That is the correct model consequence. The unavailable coordinate remains
masked out of the composite. If bounded latent-state variance is desired,
it requires a separately justified mean-reverting transition model and
validation, not fictitious measurements.

Historical CT-4 asked the absent-state covariance to saturate. Its test now
checks exact random-walk prediction variance, stable mean, proper masking,
and covariance reduction on the first genuine observation. This change is
mathematically required and is not a relaxed predictive acceptance test.

## 3. State the diffusion and staleness clock explicitly

`KalmanReconciler` adds optional keyword arguments without changing the
shared output schema:

```
time_basis="trading"             # default
session_dates=None               # weekday approximation unless provided
```

The trading clock counts elapsed regular NSE session time, 09:15–15:30 IST,
in five-minute units. One complete regular session is 75 units. Overnight
and weekend intervals contribute zero. Without `session_dates`, Monday to
Friday is used: this is explicitly **not** an exchange holiday calendar.

For a historical replay, supply actual session dates as `datetime.date`
objects, for example from the dataset's validated decision-date calendar.
Dates omitted from that list contribute zero; explicitly listed weekend
sessions are permitted. All listed sessions currently use the regular
hours, so shortened/exceptional-hours sessions need a richer calendar
implementation. Do not infer an exact exchange calendar from this fallback.

`time_basis="calendar"` separately opts into wall-clock five-minute units.
It cannot be combined with `session_dates`. Both diffusion and observation
staleness use the same chosen clock, avoiding incompatible units. `q_proc`
and `h_bars` require calibration for that clock; historical parameters fitted
to wall time must not be described as calibrated for trading time.

The default trading clock is a modeling choice, not a claim that no financial
information arrives overnight. An explicit overnight-jump component is a
possible separate extension. The change prevents silently treating a
weekend as hundreds of ordinary trading observations.

Public predict/state methods now reject noncanonical or invalid timestamps
as `ContractViolation` without mutating state. Timestamps remain explicit
IST throughout.

## 4. Verification and limits

Analytic regression tests verify scalar Gaussian updates, exact covariance
growth without measurements, duplicate-vintage idempotence, stale exclusion,
batch atomicity, session/calendar units, and the identical-weight variance
counterexample. A seeded Monte Carlo check independently confirms the
linear composite's covariance, and a mask test confirms that an arbitrarily
large absent-coordinate prior cannot contaminate active-score uncertainty.

These are mathematical correctness checks. Historical prediction metrics
must be rerun on separately recorded experiment artifacts. Passing these
tests does not demonstrate useful warning lead time, acceptable false alarms,
or empirical interval coverage.
