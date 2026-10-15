# Experimental C4 amendment: Lee–Mykland units and causal test-family size

Date: 2026-10-14. Scope: this separate research copy only. The original checkout,
database jump flags and stored Hawkes estimates are unchanged. The new daily
prediction-v1 pipeline does not call `extract_jumps`, so this amendment does not
change its computed features, targets, replay or warning results.

## Correct the statistic/critical-value mismatch

`bipower_volatility()` applies the reciprocal-square correction for
`c = sqrt(2/pi)`, so its volatility estimate is in sigma units. The corresponding
test statistic is approximately `|Z|`. The original
`lee_mykland_threshold(n, alpha)` implements the published constants for the
uncorrected volatility convention and approximately `|Z|/c`. Applying it
unchanged to the corrected statistic made the threshold too large by `1/c`.

The helper's default remains the published convention. The explicit keyword
`standardized=True` multiplies that critical value by c, and `extract_jumps()`
now uses that keyword. This matches the actual statistic's units without
silently redefining a public mathematical helper.

The relationship follows the test definition and extreme-value normalization
in [Lee and Mykland (2008), Jumps in Financial Markets](https://public.econ.duke.edu/~get/browse/courses/201/spr12/DOWNLOADS/VolatilityMeasures/SpecificlPapers/lee_mykland_rfs_08.pdf).
This is an algebraic normalization repair. It is not proof of exact finite-sample
test size under stochastic volatility, seasonal intraday variance, dependent
returns, missing bars or overnight discontinuities.

## Stop future corpus length from revising historical jump flags

Previously, extraction chose n from the count of all finite local-volatility
estimates in the entire input. Appending future prices increased its common
critical value and could revoke already emitted historical jumps.

The experimental default is now `test_block_size=75`, a fixed testing family
corresponding to the scheduled five-minute slots in a regular NSE session.
This is a preset per-block multiple-testing convention; it was not chosen to
attain a desired jump density. Other frequencies/calendars require an explicit
preset size. The API receives no timestamps, so its caller must align sessions
and decide how to handle overnight gaps. Using the same threshold across many
sessions does not deliver whole-history family-wise error control.

`test_block_size=None` is an explicit **retrospective diagnostic mode**, in which
n again uses the complete supplied input. It still uses corrected statistic
units, but its flags can change on append and must not back a causal replay.
It does not exactly reproduce the original, incorrectly scaled detector.

The prior full-sample quantile construction in `state_variable()` is outside
this bounded repair. Fixing `extract_jumps()` alone does not establish that every
legacy feature in the full intraday pipeline is causal.

## Historical evidence is not regenerated

Numbers quoted in the original SPEC, AMENDMENT-03 and old handoffs—including
21,180 negative jumps, density around 0.087, the tie fraction, branching ratio
around 0.11, stored fitted parameters and the earlier 0.1478 corrected-density
diagnostic—describe their original configurations. None is a verified result
for the new corrected, 75-test-block default. Neither a corpus re-extraction nor
a Hawkes recalibration was performed here. Their previous conclusions must not
be silently carried into a newly extracted intraday stream.

Original stored intraday outputs retain their provenance. The new daily
Hawkes proxy stays explicitly separate; this amendment does not convert it into
the unavailable historical five-minute data.

## Verification

The old strict xfail was replaced with passing normalization regressions,
including actual price extraction at a shock lying between the correct and
incorrect thresholds. A separate constructed-price test reproduces the former
append-dependence and checks exact prefix invariance under the new default.
Tests also preserve the helper's published default, cover explicit retrospective
mode and reject invalid alpha/test-family sizes.

Focused C4/C5-writer run: **28 passed, 2 database tests skipped**. Database access
was disabled via `SERAPH_DB_DSN` pointing to localhost port 1. This verifies
formula and API behavior; it does not claim a new observed NSE jump density or
improved crisis prediction.
