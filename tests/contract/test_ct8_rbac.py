# CT-8 — C11 ⇄ C12: RBAC at the gateway (ARCHITECTURE §5 ⑩)
"""The retail payload must contain no institution-level fields **at the
transport layer** — absent, not merely unrendered. Hiding a field in the view
is not access control: anything serialised reaches the client."""
from __future__ import annotations

import json

import numpy as np
import pytest

from fixtures.mock_generator import DEFAULT_START, mock_csrs_point, mock_fusion_weights
from seraph.dashboard.gateway import ROLE_FIELDS, ROLES, build_view


def _point(mask=(True, True, True)):
    rng = np.random.default_rng(31)
    return mock_csrs_point(DEFAULT_START, rng,
                           weights=mock_fusion_weights(seed=31), mask=mask)


def test_ct8_retail_payload_omits_institutional_fields_entirely():
    res = build_view("retail", _point(), explanation="test",
                     contagion_network={"edges": [["a", "b"]]},
                     sector_flags=({"sectorId": "steel", "flag": "amber"},))
    assert res.status == "ok"
    payload = res.value
    for forbidden in ("shapley", "contagionNetwork", "weightsArtefactId",
                      "sectorFlags", "effectiveWeights", "institutionDecomposition",
                      "actionLog"):
        assert forbidden not in payload, f"{forbidden} leaked into the retail payload"
    # And it must not merely be absent from the dict but from the wire form.
    wire = json.dumps(payload, default=str)
    assert "contagionNetwork" not in wire and "shapley" not in wire


def test_ct8_roles_are_strictly_cumulative():
    assert ROLE_FIELDS["retail"] < ROLE_FIELDS["institutional"] < ROLE_FIELDS["regulator"]


def test_ct8_institutional_sees_decomposition_but_not_regulator_fields():
    res = build_view("institutional", _point(), explanation="x")
    assert res.status == "ok"
    assert "shapley" in res.value and "sectorFlags" in res.value
    assert "contagionNetwork" not in res.value
    assert "weightsArtefactId" not in res.value


def test_ct8_regulator_sees_the_audit_trail():
    res = build_view("regulator", _point(), explanation="x",
                     contagion_network={"edges": []}, action_log=[{"alertId": "a1"}])
    assert res.status == "ok"
    assert res.value["weightsArtefactId"]
    assert res.value["contagionNetwork"] is not None
    assert res.value["actionLog"] == [{"alertId": "a1"}]


def test_ct8_every_role_is_told_when_the_reading_is_degraded():
    """D2's reporting obligation applies to retail too — withholding it from
    the least expert audience would be exactly backwards."""
    for role in ROLES:
        res = build_view(role, _point(mask=(False, True, True)), explanation="x")
        assert res.status == "ok"
        assert res.value["maskDegraded"] is True


def test_ct8_negative_unknown_role_is_rejected():
    res = build_view("admin", _point())
    assert res.status == "error"
    assert res.error.kind == "CONTRACT_VIOLATION"


def test_ct8_new_fields_default_to_invisible():
    """Projection onto an allow-list means an unlisted field cannot leak."""
    res = build_view("retail", _point(), explanation="x")
    assert set(res.value) - {"role"} <= ROLE_FIELDS["retail"]
