# CT-9 — C9: mask renormalisation (ARCHITECTURE §5 ④, decision D2)
"""Degraded-mask scoring is well-defined and IS the ablation-subset code path
(one implementation, not two). Negatives: all-false mask → EMPTY_MASK; weights
with all mass on masked pillars → uniform fallback + MASK_DEGRADED.

Written before C9 exists; skips until seraph/fusion/score.py lands.
"""
from __future__ import annotations

import numpy as np
import pytest

from fixtures.mock_generator import (
    DEFAULT_START,
    mock_fusion_weights,
    mock_reconciled_state,
    mock_xi,
)
from seraph.shared_types import ReconciledState


def _with_mask(state: ReconciledState, mask) -> ReconciledState:
    tau = tuple(t if m else None for t, m in zip(state.tau_last_update, mask))
    return state.model_copy(update={"mask": mask, "tau_last_update": tau})


def test_ct9_masked_scoring_renormalises_and_zeroes_shapley():
    fusion = pytest.importorskip("seraph.fusion.score", reason="C9 not built yet (L6)")
    rng = np.random.default_rng(9)
    state_full = mock_reconciled_state(DEFAULT_START, rng)
    state_masked = _with_mask(state_full, (False, True, True))
    xi = mock_xi(rng)
    weights = mock_fusion_weights(seed=9)

    full = fusion.score(reconciled=state_full, xi=xi, weights=weights)
    masked = fusion.score(reconciled=state_masked, xi=xi, weights=weights)
    assert full.status == "ok" and masked.status == "ok"

    for row in masked.value.effective_weights:
        assert sum(row) == pytest.approx(1.0, abs=1e-9)
        assert row[0] == 0.0, "masked pillar must carry zero weight"
    assert masked.value.shapley[0] == 0.0, (
        "FR44 must never attribute an alert to an absent pillar"
    )
    assert masked.value.mask == (False, True, True)
    # D2 reporting obligation: degraded scoring is labelled, not silent.
    assert any(w.code == "MASK_DEGRADED" for w in masked.warnings)


def test_ct9_masked_result_equals_ablation_subset_row():
    """D2 consequence 2: scoring with mask [F,T,T] must be IDENTICAL to the
    Table B 'RMT+Hamilton' ablation configuration on the same inputs. The
    ablation runner therefore scores subsets by constructing the mask and
    calling score() — never by a second implementation."""
    fusion = pytest.importorskip("seraph.fusion.score", reason="C9 not built yet (L6)")
    ablation = pytest.importorskip(
        "seraph.validation.ablation", reason="C10 not built yet (L7)"
    )
    rng = np.random.default_rng(9)
    state = mock_reconciled_state(DEFAULT_START, rng)
    xi = mock_xi(rng)
    weights = mock_fusion_weights(seed=9)

    assert ablation.subset_mask(("rmt", "hamilton")) == (False, True, True)

    masked = fusion.score(
        reconciled=_with_mask(state, (False, True, True)), xi=xi, weights=weights
    )
    subset = ablation.score_subset(
        reconciled=state, xi=xi, weights=weights, subset=("rmt", "hamilton")
    )
    assert masked.status == "ok" and subset.status == "ok"
    assert masked.value.model_dump_json() == subset.value.model_dump_json(), (
        "degraded production path and ablation subset must be the same code path"
    )


def test_ct9_negative_empty_mask_is_an_error():
    fusion = pytest.importorskip("seraph.fusion.score", reason="C9 not built yet (L6)")
    rng = np.random.default_rng(9)
    state = _with_mask(mock_reconciled_state(DEFAULT_START, rng), (False, False, False))
    res = fusion.score(reconciled=state, xi=mock_xi(rng), weights=mock_fusion_weights(seed=9))
    assert res.status == "error"
    assert res.error.kind == "EMPTY_MASK"


def test_ct9_negative_all_mass_on_masked_pillar_falls_back_uniform():
    fusion = pytest.importorskip("seraph.fusion.score", reason="C9 not built yet (L6)")
    rng = np.random.default_rng(9)
    state = _with_mask(mock_reconciled_state(DEFAULT_START, rng), (False, True, True))

    # Every regime row puts all mass on Hawkes — which the mask excludes.
    from seraph.shared_types import CalibrationConfig, FusionWeights, fusion_weights_artefact_id
    cfg = CalibrationConfig(
        epochs=("gfc_2008",), fold_held_out=None,
        kappa_miss=10.0, kappa_fa=1.0, mask_profile=(True, True, True),
    )
    degenerate = ((1.0, 0.0, 0.0),) * 3
    weights = FusionWeights(
        artefact_id=fusion_weights_artefact_id(degenerate, cfg),
        calibrated_on=cfg, w=degenerate,
    )

    res = fusion.score(reconciled=state, xi=mock_xi(rng), weights=weights)
    assert res.status == "ok"
    for row in res.value.effective_weights:
        assert row == pytest.approx((0.0, 0.5, 0.5)), (
            "Σ(m ⊙ w_j) = 0 → uniform weights over available pillars"
        )
    assert any(w.code == "MASK_DEGRADED" for w in res.warnings)
