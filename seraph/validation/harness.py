# C10 — Validation Harness (FR30, FR32–FR37): the D5 machine checks.
"""leakage_check is computed by intersecting the weight artefact's training
epochs with the test epochs — a machine check, not discipline (ARCHITECTURE
§2 S9). A non-clean row must not be reported.

The rest of the harness (calibrate / evaluate / runAblation, pre-registration
hashing) lands in Phase 8; nothing here may compute an AUC before the
pre-registered configuration file exists (D5d)."""
from __future__ import annotations

from typing import Iterable, Literal

from seraph.shared_types import EpochId, FusionWeights


def leakage_check(
    weights: FusionWeights, test_epochs: Iterable[EpochId]
) -> Literal["clean", "TRAIN_TEST_OVERLAP"]:
    overlap = set(weights.calibrated_on.epochs) & set(test_epochs)
    return "TRAIN_TEST_OVERLAP" if overlap else "clean"


# --- FR30 calibration and FR33 metrics -----------------------------------

import numpy as np  # noqa: E402
from scipy.optimize import minimize  # noqa: E402

from seraph.fusion.score import score  # noqa: E402
from seraph.shared_types import (  # noqa: E402
    CalibrationConfig,
    ConstraintViolated,
    FusionWeights,
    Ok,
    err,
    fusion_weights_artefact_id,
    ok,
)


def auc(scores, labels) -> float:
    """Rank-based AUC (Mann-Whitney U), tie-aware. Returns NaN when a fold
    contains only one class — reporting 0.5 there would imply an evaluation
    that did not actually happen."""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=int)
    pos, neg = int((y == 1).sum()), int((y == 0).sum())
    if pos == 0 or neg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, s.size + 1, dtype=float)
    # average ranks within ties
    _, inv, counts = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.zeros(counts.size)
    np.add.at(sums, inv, ranks)
    ranks = (sums / counts)[inv]
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2.0) / (pos * neg))


def mean_lead_time(scores, labels, threshold: float) -> float:
    """FR33 — trading days between the first sustained amber crossing and the
    start of the labelled crisis window. NaN when no crossing precedes it: a
    missed warning is not a lead time of zero."""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=int)
    onsets = np.flatnonzero((y == 1) & (np.r_[0, y[:-1]] == 0))
    if onsets.size == 0:
        return float("nan")
    leads = []
    for onset in onsets:
        pre = s[:onset]
        crossed = np.flatnonzero(pre >= threshold)
        if crossed.size:
            leads.append(float(onset - crossed[0]))
    return float(np.mean(leads)) if leads else float("nan")


def precision_at_recall(scores, labels, target_recall: float = 0.8) -> float:
    s = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=int)
    if (y == 1).sum() == 0:
        return float("nan")
    for thr in np.unique(s)[::-1]:
        pred = s >= thr
        recall = float((pred & (y == 1)).sum()) / float((y == 1).sum())
        if recall >= target_recall:
            tp_fp = int(pred.sum())
            return float((pred & (y == 1)).sum()) / tp_fp if tp_fp else float("nan")
    return float("nan")


def calibration_loss(scores, labels, kappa_miss: float, kappa_fa: float) -> float:
    """FR30 — L = kappa_miss * sum_{t in C}(1 - CSRS) + kappa_fa * sum_{t not in C} CSRS.

    Asymmetric by design (kappa_miss >> kappa_fa): missing a systemic event is
    far costlier than a false alarm, which is the whole premise of a left-tail
    early-warning instrument.
    """
    s = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=int)
    return float(kappa_miss * (1.0 - s[y == 1]).sum() + kappa_fa * s[y == 0].sum())


def _simplex(v: np.ndarray) -> tuple[float, float, float]:
    """Softmax onto the 3-simplex, with the residual clamped at zero.

    The third component is taken as the residual so the row sums to exactly 1
    under Simplex3's 1e-9 tolerance; without the clamp it can land at -1e-16
    for a saturated softmax and fail the non-negativity check on a rounding
    artefact rather than a real constraint violation.
    """
    e = np.exp(v - v.max())
    p = e / e.sum()
    a, b, c = (max(0.0, float(x)) for x in (p[0], p[1], p[2]))
    total = a + b + c
    if total <= 0:
        return (1 / 3, 1 / 3, 1 / 3)
    return (a / total, b / total, c / total)


def calibrate(
    *,
    states,
    xis,
    labels,
    train_epochs,
    held_out=None,
    kappa_miss: float = 10.0,
    kappa_fa: float = 1.0,
    mask_profile=(True, True, True),
) -> Ok[FusionWeights] | Err:
    """FR30 — jointly optimise all nine weights under one objective.

    O1's acceptance criterion requires exactly one optimisation run producing
    all nine weights, so the three regime rows are optimised together rather
    than fitted one at a time. Softmax parameterisation keeps each row on the
    simplex by construction, satisfying FR28's constraints without a penalty
    term that could be traded off against the loss.
    """
    labels = np.asarray(labels, dtype=int)
    if len(states) != len(xis) or len(states) != labels.size:
        return err(ConstraintViolated(
            constraint="states, xis and labels must align",
            observed=float(len(states)), bound=float(labels.size)))
    if labels.size == 0:
        return err(ConstraintViolated(
            constraint="empty calibration sample", observed=0.0, bound=1.0))

    def build_weights(theta):
        rows = tuple(_simplex(theta[i * 3:(i + 1) * 3]) for i in range(3))
        cfg = CalibrationConfig(
            epochs=tuple(train_epochs), fold_held_out=held_out,
            kappa_miss=kappa_miss, kappa_fa=kappa_fa, mask_profile=mask_profile)
        return FusionWeights(
            artefact_id=fusion_weights_artefact_id(rows, cfg),
            calibrated_on=cfg, w=rows)

    def objective(theta):
        w = build_weights(theta)
        vals = []
        for st, xi in zip(states, xis):
            r = score(reconciled=st, xi=xi, weights=w)
            if r.status == "error":
                return 1e12
            vals.append(r.value.csrs)
        return calibration_loss(vals, labels, kappa_miss, kappa_fa)

    best = minimize(objective, np.zeros(9), method="Nelder-Mead",
                    options={"maxiter": 1200, "fatol": 1e-8, "xatol": 1e-6})
    if not np.isfinite(best.fun) or best.fun >= 1e12:
        return err(ConstraintViolated(
            constraint="calibration failed to find a feasible weight set",
            observed=float(best.fun), bound=1e12))
    return ok(build_weights(best.x))
