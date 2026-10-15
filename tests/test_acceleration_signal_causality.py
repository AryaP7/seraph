# C10 — causality regression tests for the two surviving T1 detection signals
"""`dd_accel` and `rv_accel` must be computable from information at or before t.

`DETECTION-CALIBRATION.md` reports these as the only two of fifteen screened
series that survive Holm correction on the T1 objective. That result is worth
exactly as much as the guarantee that neither signal can see the future, so the
guarantee is pinned here rather than left to a reading of the code.

Each positive test has a paired **negative control** that applies the identical
check to a deliberately non-causal variant and asserts the check FAILS. Without
those, a check that happens to pass everything would look like evidence. The
four forms controlled for are the ones a plausible rewrite would introduce:

* a **centred** window         — `dd[t+2] - dd[t-3]`
* a **forward difference**     — `dd[t+5] - dd[t]`
* a **full-sample normalisation** — `rv[t] / mean(rv)` over all time
* a **reversed cumulative**    — price path accumulated from the end backwards

Deliberately DB-free and deterministic: synthetic inputs, fixed seed. These tests
must stay runnable with no container and no corpus.

Run: pytest tests/test_acceleration_signal_causality.py -v
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from seraph.validation.epochs import CRISIS_WINDOW_DAYS  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ssc = _load("ssc_causality", "scripts/study_stress_candidates.py")
vas = _load("vas_causality", "scripts/validate_acceleration_signals.py")

N = 900
DD_LAG = 5            # dd_accel's differencing lag
RV_WINDOW = 20        # rv_accel's denominator window
CUTS = (120, 300, 455, 701, N - 1)
SIGNALS = ("dd_accel", "rv_accel")


# ------------------------------------------------------------------ fixtures --

def _inputs(n: int = N, seed: int = 20261013):
    """Synthetic observation grid with the same shape as the real one.

    A regime shift in the back half keeps the series non-stationary, which is
    what makes a full-sample normalisation detectable: on a stationary input its
    normaliser would barely move and the control would not fire.
    """
    rng = np.random.default_rng(seed)
    dates = [str(np.datetime64("2005-01-03") + np.timedelta64(i, "D"))
             for i in range(n)]
    lr = rng.normal(scale=0.009, size=n)
    lr[n // 2:] = rng.normal(loc=-0.002, scale=0.028, size=n - n // 2)
    rv = np.abs(rng.normal(loc=0.22, scale=0.05, size=n))
    rv[n // 2:] += 0.35
    ar = np.clip(rng.uniform(0.3, 0.9, size=n), 0, 1)
    bas = np.abs(rng.normal(loc=0.004, scale=0.001, size=n))
    return dates, lr, rv, ar, bas


@pytest.fixture(scope="module")
def grid():
    return _inputs()


@pytest.fixture(scope="module")
def built(grid):
    return ssc.build_features(*grid)


# ------------------------------------------------- the definitions, as maths --

def test_dd_accel_is_a_backward_five_day_difference(grid, built):
    """dd_accel[t] == drawdown[t] - drawdown[t-DD_LAG], exactly, nowhere else."""
    dd = built["drawdown"]
    expect = np.r_[np.full(DD_LAG, np.nan), dd[DD_LAG:] - dd[:-DD_LAG]]
    got = built["dd_accel"]
    np.testing.assert_array_equal(np.isfinite(expect), np.isfinite(got))
    ok = np.isfinite(expect)
    assert ok.sum() > 500
    np.testing.assert_array_equal(expect[ok], got[ok])
    # and it is NOT the forward difference, which is the same arithmetic shifted
    fwd = np.r_[dd[DD_LAG:] - dd[:-DD_LAG], np.full(DD_LAG, np.nan)]
    both = np.isfinite(fwd) & np.isfinite(got)
    assert not np.allclose(fwd[both], got[both]), \
        "dd_accel is indistinguishable from a forward difference"


def test_rv_accel_is_a_trailing_ratio(grid, built):
    """rv_accel[t] == rv[t] / mean(rv[t-RV_WINDOW+1 .. t]), exactly."""
    _, _, rv, _, _ = grid
    ma = ssc.roll(rv, RV_WINDOW, np.mean)
    expect = np.where(np.isfinite(ma) & (ma > 0), rv / ma, np.nan)
    got = built["rv_accel"]
    ok = np.isfinite(expect) & np.isfinite(got)
    assert ok.sum() > 500
    np.testing.assert_array_equal(expect[ok], got[ok])
    # not the full-sample normaliser
    full = rv / float(rv[np.isfinite(rv)].mean())
    assert not np.allclose(full[ok], got[ok]), \
        "rv_accel is indistinguishable from a full-sample normalisation"


def test_roll_window_ends_at_the_index_and_is_not_centred():
    a = np.arange(60, dtype=float)
    w = 7
    got = ssc.roll(a, w, np.max)
    trailing = np.array([a[max(0, i - w + 1):i + 1].max() for i in range(60)])
    centred = np.array([a[max(0, i - w // 2):i + w // 2 + 1].max()
                        for i in range(60)])
    ok = np.isfinite(got)
    np.testing.assert_array_equal(got[ok], trailing[ok])
    assert not np.allclose(got[ok], centred[ok]), \
        "roll() cannot be distinguished from a centred window"


def test_drawdown_price_path_accumulates_forward(grid):
    """px[i] = exp(sum(lr[0..i])); a reversed cumulative is exp(sum(lr[i..])).

    Both are 'a cumulative sum of lr'. Only one of them is allowed.
    """
    _, lr, _, _, _ = grid
    forward = np.exp(np.cumsum(lr))
    reversed_ = np.exp(np.cumsum(lr[::-1]))[::-1]
    assert forward[0] == pytest.approx(np.exp(lr[0]))
    assert reversed_[-1] == pytest.approx(np.exp(lr[-1]))
    assert not np.allclose(forward, reversed_)
    # the feature pipeline uses the forward one
    peak = ssc.roll(forward, 252, np.max)
    dd = 1.0 - forward / peak
    built = ssc.build_features(*grid)
    ok = np.isfinite(dd) & np.isfinite(built["drawdown"])
    assert ok.sum() > 500
    np.testing.assert_array_equal(dd[ok], built["drawdown"][ok])


# --------------------------------------------------- truncation invariance ----

def _rebuild_truncated(grid, t):
    dates, lr, rv, ar, bas = grid
    return ssc.build_features(dates[:t + 1], lr[:t + 1], rv[:t + 1],
                              ar[:t + 1], bas[:t + 1])


@pytest.mark.parametrize("name", SIGNALS)
def test_truncation_invariance(grid, built, name):
    """Rebuilding from inputs [0..t] must reproduce the value AT t, exactly.

    This is the single check that a centred window, a forward difference, a
    full-sample normalisation and a reversed non-scale-invariant cumulative all
    fail, because every one of them reads an index above t.
    """
    for t in CUTS:
        sub = _rebuild_truncated(grid, t)[name][t]
        full = built[name][t]
        assert np.isfinite(sub) == np.isfinite(full), \
            f"{name}: finiteness at t={t} depends on data after t"
        if np.isfinite(full):
            assert sub == full, (
                f"{name}[{t}] changed when future data was withheld: "
                f"{full!r} -> {sub!r}")


@pytest.mark.parametrize("name", SIGNALS)
def test_future_perturbation_leaves_the_past_bit_identical(grid, built, name):
    """Corrupting every input after t must not move a single value up to t."""
    dates, lr, rv, ar, bas = grid
    rng = np.random.default_rng(7)
    for t in CUTS[:-1]:
        k = t + 1
        lr2, rv2, ar2, bas2 = lr.copy(), rv.copy(), ar.copy(), bas.copy()
        lr2[k:] = lr[k:] * 7.0 + 0.013 + rng.normal(scale=0.02, size=len(lr) - k)
        rv2[k:] = rv[k:] * 3.0 + 5.0
        ar2[k:] = np.clip(1.0 - ar[k:], 1e-6, 1.0)
        bas2[k:] = bas[k:] * 11.0 + 1.0
        got = ssc.build_features(dates, lr2, rv2, ar2, bas2)[name][:k]
        exp = built[name][:k]
        np.testing.assert_array_equal(np.isfinite(exp), np.isfinite(got))
        ok = np.isfinite(exp)
        np.testing.assert_array_equal(exp[ok], got[ok])


# ----------------------------------------------------- negative controls ------
# Each asserts the check above FAILS on a deliberately non-causal variant. If
# one of these ever passes, the corresponding positive test has stopped testing
# anything and the suite must not be trusted.

def _leaky(grid):
    return vas.leaky_variants(*grid)


@pytest.mark.parametrize("variant", ["LEAK centred-window",
                                     "LEAK forward-difference",
                                     "LEAK full-sample-norm",
                                     "LEAK reversed-cumulative",
                                     "LEAK future-peak-drawdown"])
def test_negative_control_fails_truncation_invariance(grid, variant):
    """The teeth. A non-causal variant must be caught clearly, not at 1e-16."""
    dates, lr, rv, ar, bas = grid
    full = _leaky(grid)[variant]
    worst = 0.0
    for t in CUTS:
        sub = vas.leaky_variants(dates[:t + 1], lr[:t + 1], rv[:t + 1],
                                 ar[:t + 1], bas[:t + 1])[variant][t]
        a, b = full[t], sub
        if np.isfinite(a) != np.isfinite(b):
            worst = float("inf")
            break
        if np.isfinite(a):
            worst = max(worst, abs(a - b) / max(abs(a), abs(b), 1e-300))
    assert worst > 1e-6, (
        f"{variant} passed the truncation test — the test has no teeth "
        f"against this form (max relative delta {worst:.3e})")


def test_the_one_form_these_tests_cannot_see(grid):
    """A reversed cumulative behind a scale-invariant transform is invisible.

    `drawdown = 1 - px/peak` is unchanged when px is multiplied by a constant,
    and truncating a reversed cumsum rescales px by exactly such a constant. So
    neither truncation invariance nor future perturbation can refute that form.
    Asserted rather than described, so the blind spot stays documented and
    cannot be quietly forgotten; the forward direction of the cumulative is
    checked directly instead, in
    `test_drawdown_price_path_accumulates_forward`.
    """
    dates, lr, rv, ar, bas = grid
    name = "BLINDSPOT scale-inv-reversal"
    full = _leaky(grid)[name]
    worst = 0.0
    for t in CUTS:
        sub = vas.leaky_variants(dates[:t + 1], lr[:t + 1], rv[:t + 1],
                                 ar[:t + 1], bas[:t + 1])[name][t]
        if np.isfinite(full[t]) and np.isfinite(sub):
            worst = max(worst, abs(full[t] - sub)
                        / max(abs(full[t]), abs(sub), 1e-300))
    assert worst < 1e-6, (
        "the scale-invariant reversal is now detectable by truncation — good "
        "news, but this test documents the opposite and must be updated")


# ------------------------------------------------------------------- labels ---

def test_t1_label_depends_only_on_breaks_at_or_before_t():
    """FR32's T1 window runs FORWARD from the break, so y[t] looks backward."""
    n = 400
    breaks = [50, 180, 320]
    y = np.zeros(n, int)
    for i in breaks:
        y[(np.arange(i, i + CRISIS_WINDOW_DAYS)) % n] = 1
    causal = np.array([int(any(0 <= t - i < CRISIS_WINDOW_DAYS
                               for i in breaks if i <= t)) for t in range(n)])
    np.testing.assert_array_equal(y, causal)
    assert y.sum() == len(breaks) * CRISIS_WINDOW_DAYS


def test_t1_label_wraps_the_grid_when_an_onset_sits_at_the_end():
    """The modulo in `t1_auc` is for the shifted null, and it DOES wrap.

    Harmless for the observed statistic only while no real onset is within
    CRISIS_WINDOW_DAYS of the grid end — which the audit script asserts on the
    real grid. Pinned here so the exposure is known rather than assumed away.
    """
    n = 100
    y = np.zeros(n, int)
    i = n - 5
    y[(np.arange(i, i + CRISIS_WINDOW_DAYS)) % n] = 1
    assert y[0] == 1, "modulo wraparound is not behaving as documented"
    assert y[:25].sum() == CRISIS_WINDOW_DAYS - 5


# ---------------------------------------------------------- standardisation ---

def test_trailing_percentile_window_is_causal():
    dates = [str(np.datetime64("2005-01-03") + np.timedelta64(i, "D"))
             for i in range(1200)]
    rising = np.arange(1200, dtype=float)
    pct = ssc.trailing_pct(dates, rising, years=2)
    assert pct[-1] == pytest.approx(1.0), \
        "a causal window ending at t contains its own maximum at t"
    falling = rising[::-1].copy()
    pct2 = ssc.trailing_pct(dates, falling, years=2)
    assert pct2[-1] < 0.01, \
        "a causal window ending at t contains its own minimum at t"
    # A full-sample percentile would ALSO put the last value of a rising series
    # at 1.0, so the last point cannot discriminate. The middle can: a causal
    # window gives 1.0 there, a full-sample ECDF gives ~0.5.
    mid = 600
    assert pct[mid] == pytest.approx(1.0)
    full_sample = float((rising <= rising[mid]).mean())
    assert full_sample == pytest.approx((mid + 1) / 1200.0)
    assert abs(pct[mid] - full_sample) > 0.4, \
        "trailing_pct cannot be distinguished from a full-sample ECDF"


def test_fr28_ecdf_window_excludes_the_future():
    from seraph.fusion.standardize import ECDF_WINDOW_YEARS
    from seraph.orchestration.standardize import window_from
    series = [(f"{2000 + y}-06-15T15:30:00+05:30", float(y))
              for y in range(26)]
    as_of = "2015-06-15T15:30:00+05:30"
    w = window_from(series, as_of, years=ECDF_WINDOW_YEARS)
    future = {v for ts, v in series if ts > as_of}
    assert not (set(w) & future), "FR28's ECDF window admitted a future value"
    assert max(w) == 15.0 and min(w) == 10.0
    assert ECDF_WINDOW_YEARS == 5


# --------------------------------------------- the causal orthogonaliser ------

def test_causal_residual_matches_an_explicit_backward_ols():
    """The prefix-sum implementation must equal a brute-force [t-W, t-1] fit."""
    rng = np.random.default_rng(3)
    n, W, m = 700, 300, 60
    c = np.cumsum(rng.normal(size=n))
    s = 1.7 + 0.4 * c + rng.normal(scale=0.5, size=n)
    got = vas.causal_residual(s, c, window=W, min_obs=m)
    brute = np.full(n, np.nan)
    for t in range(n):
        lo = max(0, t - W)
        x, y = c[lo:t], s[lo:t]          # strictly before t
        if x.size < m:
            continue
        b, a = np.polyfit(x, y, 1)
        brute[t] = s[t] - (a + b * c[t])
    ok = np.isfinite(brute) & np.isfinite(got)
    assert ok.sum() > 500
    np.testing.assert_allclose(got[ok], brute[ok], rtol=1e-8, atol=1e-8)
    # the fit must NOT include index t: a fit over [t-W, t] gives a different answer
    incl = np.full(n, np.nan)
    for t in range(n):
        lo = max(0, t - W)
        x, y = c[lo:t + 1], s[lo:t + 1]
        if x.size < m:
            continue
        b, a = np.polyfit(x, y, 1)
        incl[t] = s[t] - (a + b * c[t])
    ok2 = np.isfinite(incl) & np.isfinite(got)
    assert not np.allclose(got[ok2], incl[ok2], rtol=1e-6), \
        "causal_residual cannot be distinguished from a fit that includes t"


def test_causal_residual_truncation_invariant():
    rng = np.random.default_rng(11)
    n, W, m = 700, 300, 60
    c = np.cumsum(rng.normal(size=n))
    s = 1.7 + 0.4 * c + rng.normal(scale=0.5, size=n)
    full = vas.causal_residual(s, c, window=W, min_obs=m)
    for t in (200, 400, 699):
        sub = vas.causal_residual(s[:t + 1], c[:t + 1], window=W, min_obs=m)[t]
        assert np.isfinite(sub) == np.isfinite(full[t])
        if np.isfinite(full[t]):
            assert sub == pytest.approx(full[t], rel=0, abs=1e-12)


def test_causal_residual_ignores_a_relationship_change_in_the_future():
    """A regime change after t must not alter the residual at t."""
    rng = np.random.default_rng(13)
    n, W, m = 700, 300, 60
    c = np.cumsum(rng.normal(size=n))
    s = 1.7 + 0.4 * c + rng.normal(scale=0.5, size=n)
    s2 = s.copy()
    s2[400:] = -9.0 * c[400:] + 100.0       # completely different relationship
    r1 = vas.causal_residual(s, c, window=W, min_obs=m)[:400]
    r2 = vas.causal_residual(s2, c, window=W, min_obs=m)[:400]
    ok = np.isfinite(r1)
    np.testing.assert_array_equal(r1[ok], r2[ok])
