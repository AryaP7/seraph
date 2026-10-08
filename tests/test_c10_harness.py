# C10 — Validation Harness (FR30, FR33, FR35, D5)
"""Metrics, the FR30 loss, joint calibration, and the D5 pre-registration gate."""
from __future__ import annotations

import json
import numpy as np
import pytest

from fixtures.mock_generator import DEFAULT_START, mock_reconciled_state, mock_xi
from seraph.validation import (
    EPOCHS,
    HAWKES_EPOCHS,
    auc,
    calibrate,
    calibration_loss,
    configuration_list,
    content_hash,
    leakage_check,
    mean_lead_time,
    precision_at_recall,
)
from seraph.validation.preregistration import build, commit, verify


def test_auc_is_correct_on_a_known_ordering():
    assert auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == pytest.approx(1.0)
    assert auc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) == pytest.approx(0.0)
    assert auc([0.5, 0.5, 0.5, 0.5], [0, 0, 1, 1]) == pytest.approx(0.5)


def test_auc_is_nan_on_a_single_class_fold():
    """Reporting 0.5 would imply an evaluation that did not happen."""
    assert np.isnan(auc([0.1, 0.2, 0.3], [0, 0, 0]))


def test_mean_lead_time_counts_days_before_onset():
    scores = np.array([0.1, 0.2, 0.6, 0.7, 0.9, 0.9])
    labels = np.array([0, 0, 0, 0, 1, 1])          # onset at index 4
    assert mean_lead_time(scores, labels, threshold=0.5) == pytest.approx(2.0)


def test_missed_warning_is_nan_not_zero_lead_time():
    scores = np.array([0.1, 0.1, 0.1, 0.9])
    labels = np.array([0, 0, 0, 1])
    assert np.isnan(mean_lead_time(scores, labels, threshold=0.5))


def test_fr30_loss_is_asymmetric_towards_misses():
    """kappa_miss >> kappa_fa: missing a crisis must cost far more than a
    false alarm — the premise of a left-tail instrument."""
    miss = calibration_loss([0.0], [1], kappa_miss=10.0, kappa_fa=1.0)
    false_alarm = calibration_loss([1.0], [0], kappa_miss=10.0, kappa_fa=1.0)
    assert miss == pytest.approx(10.0)
    assert false_alarm == pytest.approx(1.0)
    assert miss > false_alarm


def test_precision_at_recall_runs():
    p = precision_at_recall([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0], target_recall=1.0)
    assert p == pytest.approx(1.0)


def test_calibrate_produces_one_artefact_with_nine_valid_weights():
    """O1 — all nine weights from a single optimisation run."""
    rng = np.random.default_rng(41)
    states, xis, labels = [], [], []
    for i in range(40):
        crisis = i >= 30
        st = mock_reconciled_state(DEFAULT_START, rng)
        x = list(st.x_hat)
        if crisis:
            x = [min(1.0, v + 0.4) for v in x]
        states.append(st.model_copy(update={"x_hat": (x[0], x[1], x[2])}))
        xis.append(mock_xi(rng))
        labels.append(1 if crisis else 0)

    res = calibrate(states=states, xis=xis, labels=labels,
                    train_epochs=("ilfs_2018", "covid_2020"), held_out="tariff_2026")
    assert res.status == "ok", res
    w = res.value
    assert len(w.w) == 3
    for row in w.w:
        assert sum(row) == pytest.approx(1.0, abs=1e-9)
        assert all(v >= 0 for v in row)
    assert len(w.artefact_id) == 64
    assert w.calibrated_on.fold_held_out == "tariff_2026"


def test_calibrate_rejects_misaligned_inputs():
    res = calibrate(states=[], xis=[], labels=[1], train_epochs=("gfc_2008",))
    assert res.status == "error"


def test_d5_leakage_check_is_a_set_intersection():
    rng = np.random.default_rng(42)
    states = [mock_reconciled_state(DEFAULT_START, rng) for _ in range(12)]
    xis = [mock_xi(rng) for _ in range(12)]
    labels = [0] * 8 + [1] * 4
    w = calibrate(states=states, xis=xis, labels=labels,
                  train_epochs=("gfc_2008", "covid_2020")).value
    assert leakage_check(w, ("covid_2020",)) == "TRAIN_TEST_OVERLAP"
    assert leakage_check(w, ("taper_2013",)) == "clean"


def test_fr35_configuration_counts_match_the_spec():
    """Table A: 7 subsets x 2 modes = 14. Table B: 3 subsets x 2 modes = 6."""
    cfgs = configuration_list()
    a = [c for c in cfgs if c["table"] == "A"]
    b = [c for c in cfgs if c["table"] == "B"]
    assert len(a) == 14 and len(b) == 6
    assert {len(c["pillarSubset"]) for c in a} == {1, 2, 3}
    # Table B never involves Hawkes — it covers the pre-2015 epochs.
    assert all("hawkes" not in c["pillarSubset"] for c in b)
    # Fold counts differ by table and must be recorded (D5b).
    assert {c["folds"] for c in a} == {len(HAWKES_EPOCHS)}
    assert {c["folds"] for c in b} == {len(EPOCHS)}


def test_r5_table_b_rows_carry_a_uniform_xi_control():
    """R5 — Hamilton is both a signal and the weighting over signals, so every
    Table B row needs its uniform-xi companion."""
    for c in configuration_list():
        if c["table"] == "B":
            assert c["xiModes"] == ["hamilton", "uniform"]


def test_d5_preregistration_hash_is_content_bound(tmp_path):
    design = build()
    h1 = content_hash(design)
    assert content_hash(build()) == h1, "same design must hash identically"
    tweaked = build(kappa_miss=99.0)
    assert content_hash(tweaked) != h1, "changing the design must change the hash"

    path = tmp_path / "prereg.json"
    _, digest = commit(design, path=path)
    ok_, stored = verify(path)
    assert ok_ and stored == digest


def test_d5_preregistration_refuses_to_be_rewritten(tmp_path):
    """The point of pre-registration is that it cannot be revised after
    results exist."""
    path = tmp_path / "prereg.json"
    _, first = commit(build(), path=path)
    _, second = commit(build(kappa_miss=99.0), path=path)
    assert first == second, "an existing pre-registration must not be overwritten"


def test_d5_design_states_table_incomparability(tmp_path):
    design = build()
    assert "not directly comparable" in design["tableComparability"]
    assert "DESCRIPTIVE" in design["reporting"]
