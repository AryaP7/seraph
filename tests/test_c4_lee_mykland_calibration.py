# C4 — Feature Deriver (FR50): is the Lee–Mykland test calibrated at its own α?
"""Pins the **size calibration** of the FR50 jump test, found by Workstream D
while triaging the CT-3 failure.

Evidence: `docs/evidence/20261013T124930Z-51-ct3-jump-density-and-lm-calibration.log`,
reasoning in `docs/evidence/BLOCKER-TRIAGE.md` §D-1.

**The finding.** `extract_jumps` builds its statistic as `L_i = |r_i| / σ̂_i`
where `bipower_volatility` already applies the `μ₁⁻² = π/2` bipower correction
(`/ _C_CONST**2` on the variance). So `σ̂_i` is an **unbiased estimate of σ**
and `L_i` is in true-σ units — test 1 below measures exactly that.

Lee & Mykland's published `C_n`, `S_n` carry a factor `1/c` (`c = E|N(0,1)| =
√(2/π)`) precisely *because* their own `σ̂` is the **uncorrected** bipower
estimate, which converges to `c·σ`. Their statistic is therefore `≈ |Z|/c`, and
multiplying their constants through by `c` recovers the textbook extreme-value
constants for the maximum of `n` i.i.d. `|N(0,1)|`:

    c·C_n = √(2 ln n) − (ln ln n + ln π)/(2√(2 ln n)) = a_n
    c·S_n = 1/√(2 ln n)                               = b_n

Applying the uncorrected-σ̂ constants to a corrected-σ̂ statistic double-counts
`μ₁`, so the rejection threshold is **1/c = 1.2533× too strict**. Measured
consequence on a pure-Brownian null (see the log): the shipped test rejects in
**0 of 400** samples against its nominal α = 0.01, and the same test with the
threshold scaled by `c` rejects in **0.0125** of them. Power at a 5σ jump is
0.250 shipped against 0.620 corrected.

**Why this is NOT fixed here.** The correction raises measured negative-jump
density from **0.0865 → 0.1478 per symbol-day**, and `0.087` is quoted verbatim
in **SPEC FR10 `[v4]`** as the justification for superseding per-symbol
one-day-window estimation. It is also the base of AMENDMENT-03 §1–§5d (21,180
events, the 75.8% tie fraction, `ρ = 0.0552`, `n ≈ 0.11`) and of the 473
production rows in `hawkes_output`. Changing it is a SPEC amendment, not a
routine fix, so AGENTS.md §1 applies: *"If you think a doc is wrong, say so and
ask — don't silently deviate."*

Test 3 is therefore `xfail(strict=True)`: it records the defect in executable
form, and the moment anyone corrects the calibration it **XPASSes and fails the
suite**, which is the intended prompt to amend SPEC FR10 and re-derive
AMENDMENT-03 rather than let the two drift apart silently.
"""
from __future__ import annotations

import numpy as np
import pytest

from seraph.features.jump_extraction import (
    LM_ALPHA,
    LM_WINDOW_K,
    _C_CONST,
    bipower_volatility,
    lee_mykland_threshold,
)


def _extreme_value_constants(n_obs: int) -> tuple[float, float]:
    """`(a_n, b_n)` for the maximum of `n` i.i.d. `|N(0,1)|`."""
    log_n = np.log(n_obs)
    root = np.sqrt(2.0 * log_n)
    a_n = root - (np.log(np.log(n_obs)) + np.log(np.pi)) / (2.0 * root)
    return float(a_n), float(1.0 / root)


def test_bipower_volatility_estimates_sigma_not_mu1_times_sigma():
    """`σ̂` carries the `μ₁⁻²` correction, so `|r|/σ̂` is in true-σ units.

    This is the premise of the whole module: if this test ever flips, the
    threshold in `extract_jumps` becomes correct as written and test 3 below
    should be deleted rather than un-xfailed.
    """
    rng = np.random.default_rng(20261013)
    sigma = 0.0012
    r = rng.normal(0.0, sigma, size=60_000)
    sig = bipower_volatility(r, LM_WINDOW_K)
    sig = sig[np.isfinite(sig)]
    ratio = float(sig.mean() / sigma)
    assert sig.size > 50_000
    assert ratio == pytest.approx(1.0, abs=0.02), (
        f"mean sigma_hat / sigma = {ratio:.4f}; expected ~1.0 (corrected) and "
        f"NOT ~{_C_CONST:.4f} (uncorrected, Lee-Mykland's own parameterisation)"
    )


def test_lee_mykland_threshold_is_the_published_cn_sn_form():
    """`lee_mykland_threshold` reproduces L&M's published constants exactly.

    Passing: the formula is faithfully transcribed. The defect in test 3 is a
    mismatch between this (correct) formula and the statistic it is applied to,
    not an error inside the formula.
    """
    for n in (500, 2_319, 18_781_302):
        a_n, b_n = _extreme_value_constants(n)
        beta_star = -np.log(-np.log(1.0 - LM_ALPHA))
        published = (a_n + b_n * beta_star) / _C_CONST
        assert lee_mykland_threshold(n, LM_ALPHA) == pytest.approx(
            published, rel=1e-12
        ), f"n={n}: threshold is not L&M's (C_n + S_n·β*) with the 1/c factor"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "OPEN QUESTION, not a bug to patch silently — see BLOCKER-TRIAGE.md "
        "§D-1b. extract_jumps feeds a mu_1-CORRECTED statistic to the "
        "UNCORRECTED-sigma-hat critical value, so the rejection threshold is "
        "1/c = 1.2533x too strict and the test's realised size is ~0 against "
        "a nominal alpha of 0.01. Correcting it moves negative-jump density "
        "0.0865 -> 0.1478 per symbol-day, and 0.087 is quoted verbatim in SPEC "
        "FR10 [v4]. Fixing the code without amending SPEC FR10 and re-deriving "
        "AMENDMENT-03 would put code and spec in contradiction (AGENTS.md §1). "
        "XPASS here is a FAILURE on purpose: it means someone corrected the "
        "calibration, and the spec work must follow."
    ),
)
def test_threshold_matches_the_statistic_extract_jumps_actually_feeds_it():
    """The critical value must match the scaling of the statistic it judges.

    `extract_jumps` compares `|r_i|/σ̂_i` (unbiased σ̂, so ≈ `|Z|`) against
    `lee_mykland_threshold(n)` (the critical value for `|Z|/c`). The two are
    out by exactly `1/c`.
    """
    for n in (500, 2_319, 18_781_302):
        a_n, b_n = _extreme_value_constants(n)
        beta_star = -np.log(-np.log(1.0 - LM_ALPHA))
        correct_for_standardised_statistic = a_n + b_n * beta_star
        shipped = lee_mykland_threshold(n, LM_ALPHA)
        assert shipped == pytest.approx(
            correct_for_standardised_statistic, rel=1e-9
        ), (
            f"n={n}: shipped threshold {shipped:.4f} vs "
            f"{correct_for_standardised_statistic:.4f} required for a "
            f"sigma-standardised statistic — out by "
            f"{shipped / correct_for_standardised_statistic:.4f} (= 1/c)"
        )
