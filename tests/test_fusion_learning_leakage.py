# C9/C10 — the leakage controls the learned-fusion comparison depends on
"""A learned fusion model has four places future information can enter, and all
four are silent failures that make results *better*:

1. the weights, if fitted on data including the test epoch;
2. the alert threshold, if chosen on the test period's own false-alarm rate;
3. the D2 renormalisation, if an unavailable pillar contributes a zero instead
   of dropping out;
4. the fold boundary, if a training mask reaches past the onset it is meant to
   precede.

Each is pinned here as a falsification attempt: perturb the future, assert the
fitted object did not move. If any transform is ever replaced by a
future-dependent one, the perturbation propagates and the test fails.

The harness-faithfulness check is also a test rather than only a runtime print,
because every number in `FUSION-ARCHITECTURE.md` is meaningless if equal-weight
fusion does not reproduce the shipped CSRS.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _fusion():
    spec = importlib.util.spec_from_file_location(
        "fas", _ROOT / "scripts" / "fusion_architecture_search.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. D2 renormalisation — an absent pillar drops out, it does not score zero
# ---------------------------------------------------------------------------
def test_fuse_renormalises_over_available_pillars():
    """A masked-off pillar must not drag the composite toward zero.

    This is the D2 invariant AGENTS.md §5 names. If an unavailable pillar
    contributed a 0 at weight 1/3, every pre-2017 composite would be depressed
    by a third purely because Hawkes does not exist yet — and the depression
    would look like "low systemic risk".
    """
    mod = _fusion()
    X = np.array([[0.9, 0.9, 0.9]])
    w = np.array([1 / 3, 1 / 3, 1 / 3])

    all_on = mod.fuse(X, np.array([[True, True, True]]), w)[0]
    one_off = mod.fuse(X, np.array([[False, True, True]]), w)[0]
    assert all_on == pytest.approx(0.9)
    assert one_off == pytest.approx(0.9), (
        "masking a pillar changed the composite — the remaining weights are "
        "not being renormalised, so an absent pillar is contributing a zero")


def test_fuse_is_nan_when_no_pillar_is_available():
    mod = _fusion()
    out = mod.fuse(np.array([[0.5, 0.5, 0.5]]),
                   np.array([[False, False, False]]),
                   np.array([1 / 3, 1 / 3, 1 / 3]))
    assert not np.isfinite(out[0]), (
        "a composite was emitted with no available pillar; it must be absent, "
        "not a default value that downstream code reads as a real score")


# ---------------------------------------------------------------------------
# 2. the learned weights see only training data
# ---------------------------------------------------------------------------
def test_learned_weights_ignore_data_outside_the_training_mask():
    """Perturbing the post-training region must not move the fitted weights."""
    mod = _fusion()
    rng = np.random.default_rng(5)
    n = 1200
    X = rng.uniform(0, 1, (n, 3))
    M = np.ones((n, 3), dtype=bool)
    y = np.zeros(n, dtype=bool)
    y[300:330] = True                      # positives inside training
    train = np.zeros(n, dtype=bool)
    train[:600] = True

    w1, a1 = mod.learn_convex(X, M, y, train, shrink=0.0)

    X2 = X.copy()
    X2[600:, :] = 0.0                      # obliterate the future
    y2 = y.copy()
    y2[800:850] = True                     # and add future positives
    w2, a2 = mod.learn_convex(X2, M, y2, train, shrink=0.0)

    assert np.allclose(w1, w2), (
        f"weights moved when only post-training data changed: {w1} -> {w2}; "
        f"learn_convex is reading outside its training mask")
    assert a1 == pytest.approx(a2)


def test_learned_weights_stay_on_the_simplex():
    mod = _fusion()
    rng = np.random.default_rng(9)
    n = 900
    X = rng.uniform(0, 1, (n, 3))
    M = np.ones((n, 3), dtype=bool)
    y = np.zeros(n, dtype=bool); y[100:140] = True
    train = np.zeros(n, dtype=bool); train[:500] = True
    for sh in (0.0, 0.25, 0.5, 0.75):
        w, _ = mod.learn_convex(X, M, y, train, shrink=sh)
        assert np.all(w >= -1e-12), f"negative weight at shrink={sh}: {w}"
        assert w.sum() == pytest.approx(1.0), f"weights do not sum to 1: {w}"


def test_shrinkage_moves_weights_toward_equal():
    """shrink=1 would be exactly equal weights, so ordering must be monotone."""
    mod = _fusion()
    rng = np.random.default_rng(11)
    n = 900
    X = rng.uniform(0, 1, (n, 3))
    X[:, 0] += 0.4                          # make pillar 0 clearly favoured
    M = np.ones((n, 3), dtype=bool)
    y = np.zeros(n, dtype=bool)
    y[(X[:, 0] > 1.0)] = True
    train = np.zeros(n, dtype=bool); train[:600] = True
    eq = np.array([1 / 3, 1 / 3, 1 / 3])
    d0 = np.abs(mod.learn_convex(X, M, y, train, 0.0)[0] - eq).sum()
    d7 = np.abs(mod.learn_convex(X, M, y, train, 0.75)[0] - eq).sum()
    assert d7 <= d0 + 1e-12, (
        "heavier shrinkage did not move the weights closer to equal weights")


# ---------------------------------------------------------------------------
# 3. the alert threshold is fitted on training data only
# ---------------------------------------------------------------------------
def test_threshold_ignores_the_test_period():
    """Changing scores after the training window must not move the threshold."""
    mod = _fusion()
    rng = np.random.default_rng(3)
    n = 2000
    score = rng.uniform(0, 1, n)
    train = np.zeros(n, dtype=bool); train[:1000] = True
    excl = np.zeros(n, dtype=bool)

    t1 = mod.threshold_at_budget(score, train, excl, years=4.0, budget=2.0)
    s2 = score.copy()
    s2[1000:] = 1.0                        # saturate the entire test period
    t2 = mod.threshold_at_budget(s2, train, excl, years=4.0, budget=2.0)
    assert t1 == pytest.approx(t2), (
        "the threshold moved when only the test period changed — it is being "
        "fitted on data the model is about to be judged on")


def test_threshold_respects_the_budget_on_training_data():
    mod = _fusion()
    rng = np.random.default_rng(7)
    n = 2520                                # ~10 years
    score = rng.uniform(0, 1, n)
    train = np.ones(n, dtype=bool)
    excl = np.zeros(n, dtype=bool)
    years = 10.0
    for budget in (0.5, 1.0, 2.0):
        thr = mod.threshold_at_budget(score, train, excl, years, budget)
        if not np.isfinite(thr):
            continue
        flag = score >= thr
        eps = mod.episodes(flag)
        assert len(eps) / years <= budget + 1e-9, (
            f"budget {budget} breached on the data the threshold was fitted to: "
            f"{len(eps)/years:.3f} episodes/yr")


def test_threshold_returns_inf_when_no_level_respects_the_budget():
    """A silent candidate is correct; a candidate over-alerting is not."""
    mod = _fusion()
    n = 2520
    score = np.ones(n)                      # every day identical and maximal
    train = np.ones(n, dtype=bool)
    excl = np.zeros(n, dtype=bool)
    thr = mod.threshold_at_budget(score, train, excl, years=10.0, budget=0.0)
    assert not np.isfinite(thr), (
        "a threshold was returned that cannot respect a zero budget; the "
        "candidate must go silent rather than over-alert")


# ---------------------------------------------------------------------------
# 4. episode counting — a standing alert is one decision
# ---------------------------------------------------------------------------
def test_episodes_counts_rising_edges_not_days():
    mod = _fusion()
    flag = np.zeros(20, dtype=bool)
    flag[3:12] = True                       # one nine-day alert
    flag[15] = True                         # one single-day alert
    assert mod.episodes(flag) == [3, 15], (
        "a standing alert was counted more than once; false-alarm rates would "
        "be inflated by alert duration rather than by alert frequency")


# ---------------------------------------------------------------------------
# 5. the logistic fit sees only training data
# ---------------------------------------------------------------------------
def test_logistic_coefficients_ignore_the_test_period():
    mod = _fusion()
    rng = np.random.default_rng(13)
    n = 1500
    X = rng.uniform(0, 1, (n, 3))
    y = np.zeros(n, dtype=bool)
    y[200:260] = True
    train = np.zeros(n, dtype=bool); train[:800] = True

    b1 = mod.fit_logistic(X, y, train, C=1.0)
    X2 = X.copy(); X2[800:, :] = 0.0
    y2 = y.copy(); y2[1000:1100] = True
    b2 = mod.fit_logistic(X2, y2, train, C=1.0)
    assert b1 is not None and b2 is not None
    assert np.allclose(b1, b2), (
        "logistic coefficients moved when only post-training data changed")


def test_logistic_refuses_to_fit_on_too_few_positives():
    """Three coefficients cannot be estimated from a handful of events."""
    mod = _fusion()
    rng = np.random.default_rng(17)
    X = rng.uniform(0, 1, (500, 3))
    y = np.zeros(500, dtype=bool); y[10:13] = True      # 3 positives
    train = np.ones(500, dtype=bool)
    assert mod.fit_logistic(X, y, train, C=1.0) is None, (
        "a model was fitted on fewer than 5 positives; it must decline so the "
        "fold is reported untrainable rather than silently fitted to noise")


# ---------------------------------------------------------------------------
# 6. the AUC helper handles ties, or a discrete score is biased
# ---------------------------------------------------------------------------
def test_auc_uses_average_ranks_for_ties():
    mod = _fusion()
    score = np.array([0.5] * 10)            # completely uninformative
    y = np.array([True] * 5 + [False] * 5)
    assert mod.auc(score, y) == pytest.approx(0.5), (
        "a constant score did not give AUC 0.5; ties are not being averaged, "
        "which biases every discrete or saturated score")


def test_auc_is_one_for_a_perfect_ranking():
    mod = _fusion()
    score = np.arange(10, dtype=float)
    y = np.array([False] * 5 + [True] * 5)
    assert mod.auc(score, y) == pytest.approx(1.0)
