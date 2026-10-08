# CT-6 — C10 ⇄ C9: purity and leakage (ARCHITECTURE §5 ③)
"""C9 is pure — identical inputs → byte-identical output, 100/100. Train/test
overlap is caught mechanically, not by discipline. Negative: weights off the
simplex are rejected before scoring.

Written before C9/C10 exist; the simplex negative runs today.
Pinned C10 API (module seraph/validation/harness.py):

    def leakage_check(weights: FusionWeights,
                      test_epochs: Sequence[EpochId]) -> Literal["clean", "TRAIN_TEST_OVERLAP"]
"""
from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from fixtures.mock_generator import (
    DEFAULT_START,
    mock_fusion_weights,
    mock_reconciled_state,
    mock_xi,
)
from seraph.shared_types import CalibrationConfig, FusionWeights, fusion_weights_artefact_id


def test_ct6_score_is_pure_100_of_100():
    fusion = pytest.importorskip("seraph.fusion.score", reason="C9 not built yet (L6)")
    rng = np.random.default_rng(5)
    state = mock_reconciled_state(DEFAULT_START, rng)
    xi = mock_xi(rng)
    weights = mock_fusion_weights(seed=5)

    outputs = set()
    for _ in range(100):
        res = fusion.score(reconciled=state, xi=xi, weights=weights)
        assert res.status == "ok"
        outputs.add(res.value.model_dump_json(by_alias=True))
    assert len(outputs) == 1, "score() must be byte-identical on identical inputs"


def test_ct6_leakage_overlap_is_flagged():
    harness = pytest.importorskip(
        "seraph.validation.harness", reason="C10 not built yet (L7)"
    )
    weights = mock_fusion_weights(
        seed=5, epochs=("ilfs_2018", "covid_2020", "tightening_2022")
    )
    assert harness.leakage_check(weights, ("covid_2020",)) == "TRAIN_TEST_OVERLAP"
    assert harness.leakage_check(weights, ("gfc_2008",)) == "clean"


# --- runnable today: constraint enforced at the shared_types seam ----------


def test_ct6_negative_weights_off_simplex_rejected_before_scoring():
    cfg = CalibrationConfig(
        epochs=("ilfs_2018",), fold_held_out=None,
        kappa_miss=10.0, kappa_fa=1.0, mask_profile=(True, True, True),
    )
    bad_w = ((0.5, 0.4, 0.2), (0.3, 0.3, 0.4), (0.2, 0.2, 0.6))  # row 0 sums to 1.1
    with pytest.raises(ValidationError, match="Simplex3"):
        FusionWeights(
            artefact_id=fusion_weights_artefact_id(bad_w, cfg),
            calibrated_on=cfg,
            w=bad_w,
        )


def test_ct6_negative_negative_weight_rejected():
    cfg = CalibrationConfig(
        epochs=("ilfs_2018",), fold_held_out=None,
        kappa_miss=10.0, kappa_fa=1.0, mask_profile=(True, True, True),
    )
    bad_w = ((1.2, -0.2, 0.0), (0.3, 0.3, 0.4), (0.2, 0.2, 0.6))
    with pytest.raises(ValidationError, match="Simplex3"):
        FusionWeights(
            artefact_id=fusion_weights_artefact_id(bad_w, cfg),
            calibrated_on=cfg,
            w=bad_w,
        )
