# T0 — mock stream conformance to ARCHITECTURE §0/§2 shapes
"""The whole point of T0 is that C8–C12 can trust its output blindly. These
tests prove the mocks are shape-valid, that the seams' validators actually
reject bad data, and that serialisation round-trips through the ARCHITECTURE
camelCase spelling."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError

from fixtures.mock_generator import (
    DEFAULT_START,
    mock_csrs_stream,
    mock_fusion_weights,
    mock_reconciled_stream,
    mock_tick_stream,
)
from seraph.shared_types import (
    PILLAR_ORDER,
    CsrsPoint,
    IntradayBar,
    PillarEmission,
    ReconciledState,
    ist_timestamp,
)

_EMISSION = TypeAdapter(PillarEmission)


def test_pillar_order_is_the_fixed_global_order():
    assert PILLAR_ORDER == ["hawkes", "rmt", "hamilton"]


def test_tick_stream_shape_and_order():
    stream = mock_tick_stream(n_ticks=30, seed=0, hawkes_structural_ticks=10,
                              transient_rate=0.1)
    assert len(stream) == 30
    for tick in stream:
        assert len(tick) == 3
        for pillar, em in zip(PILLAR_ORDER, tick):
            observed_pillar = em.obs.pillar if em.kind == "observed" else em.pillar
            assert observed_pillar == pillar


def test_structural_and_transient_absence_both_present():
    stream = mock_tick_stream(n_ticks=200, seed=1, hawkes_structural_ticks=20,
                              transient_rate=0.05)
    flat = [em for tick in stream for em in tick]
    kinds = {(em.absence if em.kind == "unavailable" else "observed") for em in flat}
    assert {"observed", "structural", "transient"} <= kinds


def test_emission_union_round_trips_through_camel_case_json():
    stream = mock_tick_stream(n_ticks=10, seed=2, hawkes_structural_ticks=3)
    for tick in stream:
        for em in tick:
            parsed = _EMISSION.validate_json(em.model_dump_json(by_alias=True))
            assert parsed == em


def test_observation_tau_never_after_ts():
    stream = mock_tick_stream(n_ticks=50, seed=3, transient_rate=0.0)
    for tick in stream:
        for em in tick:
            if em.kind == "observed":
                assert em.obs.tau <= em.obs.ts


def test_reconciled_stream_is_psd_and_aliased():
    for state in mock_reconciled_stream(n=25, seed=4):
        p = np.asarray(state.P)
        assert np.allclose(p, p.T)
        assert np.linalg.eigvalsh(p).min() >= -1e-9
        dumped = state.model_dump(by_alias=True)
        assert {"ts", "xHat", "P", "tauLastUpdate", "mask", "noiseSaturated", "mode"} <= set(dumped)
        assert ReconciledState.model_validate(dumped) == state


def test_csrs_stream_bounds_and_audit_trail():
    stream = mock_csrs_stream(n=40, seed=5)
    for point in stream:
        assert 0.0 <= point.csrs <= 1.0
        assert point.ci_lower <= point.csrs <= point.ci_upper
        assert point.variance >= 0.0
        assert len(point.weights_artefact_id) == 64  # audit trail present
        for row in point.effective_weights:
            assert sum(row) == pytest.approx(1.0, abs=1e-9)
        assert CsrsPoint.model_validate_json(point.model_dump_json(by_alias=True)) == point


def test_degraded_mask_zeroes_masked_columns():
    stream = mock_csrs_stream(n=10, seed=6, mask=(False, True, True))
    for point in stream:
        assert point.mask == (False, True, True)
        assert point.shapley[0] == 0.0
        for row in point.effective_weights:
            assert row[0] == 0.0


def test_fusion_weights_artefact_id_is_content_bound():
    a = mock_fusion_weights(seed=7)
    b = mock_fusion_weights(seed=7)
    c = mock_fusion_weights(seed=8)
    assert a.artefact_id == b.artefact_id
    assert a.artefact_id != c.artefact_id


# --- the validators must bite --------------------------------------------


def test_frozen_models_reject_mutation():
    state = mock_reconciled_stream(n=1, seed=9)[0]
    with pytest.raises(ValidationError):
        state.mask = (False, False, False)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError, match="IST"):
        ist_timestamp(datetime(2020, 3, 2, 9, 15, 0))  # no tzinfo


def test_non_ist_string_rejected_at_the_seam():
    with pytest.raises(ValidationError):
        ReconciledState(
            ts="2020-03-02T09:15:00Z",  # UTC — must be explicit +05:30
            x_hat=(0.1, 0.2, 0.3),
            P=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            tau_last_update=(None, None, None),
            mask=(True, True, True),
            mode="kalman",
        )


def test_jump_sign_iff_is_jump():
    ts = ist_timestamp(DEFAULT_START)
    with pytest.raises(ValidationError):
        IntradayBar(symbol="X", ts=ts, open=1, high=1, low=1, close=1,
                    volume=1, is_jump=True, jump_sign=0)
    with pytest.raises(ValidationError):
        IntradayBar(symbol="X", ts=ts, open=1, high=1, low=1, close=1,
                    volume=1, is_jump=False, jump_sign=1)


def test_csrs_out_of_bounds_rejected():
    good = mock_csrs_stream(n=1, seed=10)[0]
    data = good.model_dump()
    data["csrs"] = 1.5
    with pytest.raises(ValidationError):
        CsrsPoint.model_validate(data)
