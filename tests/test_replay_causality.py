# C10 — the leakage controls the unified crisis replay depends on
"""Every claim in `docs/evidence/CRISIS-REPLAY.md` rests on one property: no
value at decision date `t` may depend on an input dated after `t`.

That property is invisible in normal use. A replay with a centred window, a
full-sample normalisation or a threshold fitted on the evaluation episodes
produces *better-looking* results and no error, which is exactly why it has to
be pinned by test rather than by reading.

The tests below are written as **falsification attempts**: each one perturbs the
future and asserts the past did not move. If a future-dependent transform is
ever substituted, the perturbation propagates backwards and the test fails.

Threshold leakage gets its own test because it is the subtler of the two. Rule B
excludes index `i` from the trailing quantile it is compared against; without
that exclusion a single extreme value helps set the bar it is judged by, which
systematically suppresses exactly the alerts the replay exists to count.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _replay():
    spec = importlib.util.spec_from_file_location(
        "replay_crisis_warnings", _ROOT / "scripts" / "replay_crisis_warnings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dates(n: int, start_year: int = 2005) -> list[str]:
    """`n` strictly increasing ISO dates, dense enough to span several years."""
    out, y, m, d = [], start_year, 1, 1
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}-{d:02d}")
        d += 1
        if d > 28:
            d, m = 1, m + 1
            if m > 12:
                m, y = 1, y + 1
    return out


# ---------------------------------------------------------------------------
# 1. the transforms are backward-looking
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("w", [5, 20, 60])
def test_realised_vol_ignores_the_future(w):
    """Perturbing lr[500] must not move rv at any index < 500."""
    mod = _replay()
    rng = np.random.default_rng(7)
    lr = rng.normal(0, 0.01, 800)
    a = mod.realised_vol(lr, w)
    lr2 = lr.copy()
    lr2[500] = 5.0                      # a shock far larger than the series
    b = mod.realised_vol(lr2, w)
    fa, fb = a[:500], b[:500]
    both = np.isfinite(fa) & np.isfinite(fb)
    assert np.allclose(fa[both], fb[both]), (
        "a future observation changed a past realised-vol value — the window is "
        "not causal")
    # and it MUST move the present, or the test is vacuous
    assert b[500] > a[500] * 10


def test_drawdown_ignores_the_future():
    """A later peak must not deepen an earlier drawdown."""
    mod = _replay()
    rng = np.random.default_rng(11)
    lr = rng.normal(0.0005, 0.01, 600)
    a = mod.drawdown(lr)
    lr2 = lr.copy()
    lr2[400] = 1.0                      # a huge later rally -> new running max
    b = mod.drawdown(lr2)
    assert np.allclose(a[:400], b[:400]), (
        "a later peak changed an earlier drawdown — `maximum.accumulate` was "
        "replaced by a full-sample max")


def test_accel_is_a_backward_difference():
    mod = _replay()
    x = np.arange(50.0)
    a = mod.accel(x, 5)
    assert np.all(np.isnan(a[:5])), "the first `lag` values cannot be defined"
    assert np.allclose(a[5:], 5.0)
    # a future value must not leak into the present
    x2 = x.copy(); x2[30] = 999.0
    b = mod.accel(x2, 5)
    assert np.allclose(a[:30], b[:30], equal_nan=True), (
        "accel read forward — it must be x[i] - x[i-lag], never x[i+lag] - x[i]")


# ---------------------------------------------------------------------------
# 2. the threshold is not fitted on the day it judges
# ---------------------------------------------------------------------------
def test_rule_b_excludes_index_i_from_its_own_threshold():
    """The decisive leakage test for the alert rule.

    A lone extreme value must fire. If `i` were included in its own trailing
    quantile, a sufficiently extreme single value would raise the 95th
    percentile toward itself and could fail to cross — silently suppressing the
    alerts the replay is counting.
    """
    mod = _replay()
    n = 2000
    dates = _dates(n)
    vals = np.zeros(n)
    vals[:] = np.linspace(0.0, 1.0, n) * 1e-9      # essentially flat
    vals[1500] = 1.0                                # one unambiguous spike
    flags = mod.causal_quantile_flags(
        dates, vals, q=0.95, min_obs=250, years=5)
    assert bool(flags[1500]), (
        "a lone extreme value failed to cross its own trailing 95th percentile "
        "— index i is contaminating the threshold it is tested against")


def test_rule_b_threshold_uses_no_future_data():
    """Changing the tail of the series must not change an early flag."""
    mod = _replay()
    n = 2000
    dates = _dates(n)
    rng = np.random.default_rng(3)
    vals = rng.normal(0, 1, n)
    a = mod.causal_quantile_flags(dates, vals, min_obs=250)
    vals2 = vals.copy()
    vals2[1200:] += 50.0                 # a regime shift in the FUTURE only
    b = mod.causal_quantile_flags(dates, vals2, min_obs=250)
    assert np.array_equal(a[:1200], b[:1200]), (
        "a later regime shift changed earlier alert flags — the quantile window "
        "is not restricted to the past")


def test_rule_b_is_silent_until_min_obs_is_met():
    """An un-assessable warm-up must score as 'no warning', never as NaN.

    Emitting NaN would quietly drop those days from the denominator and inflate
    every rate computed over the series.
    """
    mod = _replay()
    n = 400
    dates = _dates(n)
    vals = np.linspace(0, 1, n)
    flags = mod.causal_quantile_flags(dates, vals, min_obs=250)
    assert flags.dtype == np.bool_, "flags must be boolean, not float/NaN"
    assert not flags[:250].any(), (
        "a flag fired before `min_obs` trailing observations existed")


# ---------------------------------------------------------------------------
# 3. the verdict is decided strictly before the onset
# ---------------------------------------------------------------------------
def test_assess_epoch_ignores_everything_at_or_after_the_onset():
    """An alert that starts ON the onset is not a warning.

    This is the distinction the whole exercise turns on, so it is asserted
    directly: a signal that fires only from the onset onward must score FAIL
    with `during_or_after_only` set, never PASS.
    """
    mod = _replay()
    n = 300
    dates = _dates(n)
    onset = dates[200]
    vals = np.ones(n)
    flags = np.zeros(n, dtype=bool)
    flags[200:] = True                   # fires exactly at the onset, not before
    r = mod.assess_epoch(dates, flags, vals, onset, horizon=15)
    assert r["verdict"] == "FAIL", (
        "an alert beginning at the onset was scored as a pre-onset warning")
    assert r["during_or_after_only"] is True
    assert r["first_warning_date"] is None
    assert r["lead_time_days"] is None


def test_assess_epoch_reports_the_true_lead_time():
    mod = _replay()
    n = 300
    dates = _dates(n)
    onset = dates[200]
    vals = np.ones(n)
    flags = np.zeros(n, dtype=bool)
    # dates[199] is the last day strictly before the onset, so a rising edge at
    # index 190 is a lead of 199-190+1 = 10 days.
    flags[190:198] = True
    r = mod.assess_epoch(dates, flags, vals, onset, horizon=15)
    assert r["verdict"] == "PASS"
    assert r["lead_time_days"] == 10
    assert r["first_warning_date"] == dates[190]
    assert r["within_fr32_lead_window"] is True, "10 days is inside FR32's 5-15"
    assert r["persisted_to_onset"] is False, "the alert lapsed before the onset"


def test_assess_epoch_marks_an_uncovered_epoch_untestable_not_failed():
    """Absent causal data must not be reported as a missed warning.

    Hamilton has no causal estimate before 2013-01-14, so the 2008 GFC is
    `UNTESTABLE` for every Hamilton-containing subset. Scoring it `FAIL` would
    manufacture a negative result out of missing data.
    """
    mod = _replay()
    n = 300
    dates = _dates(n)
    onset = dates[200]
    vals = np.full(n, np.nan)            # no causal value anywhere
    flags = np.zeros(n, dtype=bool)
    r = mod.assess_epoch(dates, flags, vals, onset, horizon=15)
    assert r["verdict"] == "UNTESTABLE"
    assert r["coverage_days_pre"] == 0


# ---------------------------------------------------------------------------
# 4. Hamilton's warm-up is not silently backfilled
# ---------------------------------------------------------------------------
def test_hamilton_causal_loader_emits_nothing_before_the_causal_index():
    """The in-sample fit must not be substituted for the missing warm-up.

    Skipped when the POSTFIX artefact is absent, because this pins the loader's
    contract against that specific file rather than re-deriving it.
    """
    mod = _replay()
    if not mod.HAM_NPZ.exists():
        pytest.skip(f"causal Hamilton artefact not present: {mod.HAM_NPZ.name}")
    z = np.load(mod.HAM_NPZ)
    fi = int(z["first_causal_index"])
    first_causal_date = str(z["dates"][fi])
    ham = mod.load_hamilton_causal()
    assert ham, "loader returned nothing at all"
    assert min(ham) == first_causal_date, (
        f"loader exposed a date before the causal index: {min(ham)} < "
        f"{first_causal_date} — the warm-up period is being backfilled")
    # the 2008 GFC must therefore be out of reach, causally
    assert min(ham) > "2008-09-15", (
        "if this ever passes, the 2008 epoch became causally testable for "
        "Hamilton and CRISIS-REPLAY.md's UNTESTABLE verdict must be revisited")
