"""FIX02 — structural versus transient absence is carried, never inferred.

Audit finding A02: `InferenceSession.step()` mapped every ineligible input to
`absence='structural'`. A temporary RMT outage therefore moved the D2 mask from
`[true, true, false]` to `[true, false, false]` — a pillar that *should* exist
was dropped out of fusion instead of staying in the mask with D4 age-inflated
uncertainty, which is exactly the mechanism SPEC objective O6 depends on.

The repair makes absence a declared part of the adapter contract
(docs/PRODUCT-CONTRACTS.md §3). An ineligible pillar that does not declare its
absence type is an error, because guessing is the defect.
"""
from __future__ import annotations

import pytest

from seraph.orchestration.prototype import InferenceSession

DAYS = ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"]


def _observed(day, value=0.3):
    return dict(score_eligible=True, value=value, model="synthetic",
                information_timestamp=day + "T15:30:00+05:30", reason="ok")


def _absent(kind, reason_code, text):
    return dict(score_eligible=False, value=None, absence=kind,
                absence_reason=reason_code, reason=text)


def _batch(day, rmt=None):
    return {"hawkes": _observed(day), "rmt": rmt or _observed(day),
            "hamilton": _absent("structural", "no_data_coverage",
                                "diagnostic only; standing research exclusion")}


def test_transient_outage_keeps_the_pillar_in_the_mask():
    session = InferenceSession(DAYS)
    seeded = session.step(DAYS[0], _batch(DAYS[0]), [], run_id="x")
    outage = session.step(DAYS[1], _batch(DAYS[1], _absent(
        "transient", "estimation_failed", "upstream feed outage")), [], run_id="x")
    recovered = session.step(DAYS[2], _batch(DAYS[2]), [], run_id="x")

    assert seeded["coverage"]["mask"] == [True, True, False]
    # The regression: this used to collapse to [True, False, False].
    assert outage["coverage"]["mask"] == [True, True, False]
    assert outage["coverage"]["absence"]["rmt"] == "transient"
    assert recovered["coverage"]["mask"] == [True, True, False]


def test_a_transient_outage_grows_uncertainty_rather_than_inventing_a_value():
    session = InferenceSession(DAYS)
    seeded = session.step(DAYS[0], _batch(DAYS[0]), [], run_id="x")
    outage = session.step(DAYS[1], _batch(DAYS[1], _absent(
        "transient", "estimation_failed", "upstream feed outage")), [], run_id="x")
    rmt_before = seeded["reconciled"]["P"][1][1]
    rmt_after = outage["reconciled"]["P"][1][1]
    assert rmt_after > rmt_before, "an absent update must not reduce covariance"
    # No fictitious measurement: the vintage marker does not move.
    assert outage["reconciled"]["tau_last_update"][1] == \
        seeded["reconciled"]["tau_last_update"][1]


def test_structural_absence_excludes_the_pillar_from_the_mask():
    session = InferenceSession(DAYS)
    point = session.step(DAYS[0], _batch(DAYS[0], _absent(
        "structural", "insufficient_history", "no RMT history before coverage begins")),
        [], run_id="x")
    assert point["coverage"]["mask"] == [True, False, False]
    assert point["coverage"]["absence"]["rmt"] == "structural"


def test_an_ineligible_pillar_must_declare_its_absence_type():
    session = InferenceSession(DAYS)
    undeclared = _batch(DAYS[0], dict(score_eligible=False, value=None,
                                      reason="something went wrong"))
    with pytest.raises(ValueError, match="must declare absence"):
        session.step(DAYS[0], undeclared, [], run_id="x")


def test_an_unknown_absence_reason_is_rejected():
    session = InferenceSession(DAYS)
    bad = _batch(DAYS[0], dict(score_eligible=False, value=None, absence="transient",
                               absence_reason="vibes", reason="x"))
    with pytest.raises(ValueError, match="absence_reason must be one of"):
        session.step(DAYS[0], bad, [], run_id="x")


def test_structural_and_transient_are_distinguishable_in_the_persisted_payload():
    session = InferenceSession(DAYS)
    point = session.step(DAYS[0], {
        "hawkes": _observed(DAYS[0]),
        "rmt": _absent("transient", "estimation_failed", "feed outage"),
        "hamilton": _absent("structural", "no_data_coverage", "research exclusion"),
    }, [], run_id="x")
    assert point["coverage"]["absence"] == {
        "hawkes": None, "rmt": "transient", "hamilton": "structural"}
    assert any("[transient]" in m for m in point["limitations"])
    assert any("[structural]" in m for m in point["limitations"])


def test_historical_noncoverage_then_first_observation_flips_the_mask():
    session = InferenceSession(DAYS)
    before = session.step(DAYS[0], _batch(DAYS[0], _absent(
        "structural", "insufficient_history", "no coverage yet")), [], run_id="x")
    first = session.step(DAYS[1], _batch(DAYS[1]), [], run_id="x")
    assert before["coverage"]["mask"][1] is False
    assert before["reconciled"]["tau_last_update"][1] is None
    assert first["coverage"]["mask"][1] is True
    assert first["reconciled"]["tau_last_update"][1] is not None
    # The genuine first observation reduces covariance below the diffused
    # prior it was applied to (p0 + q * one session of bars), rather than
    # below the pre-diffusion value.
    diffused = before["reconciled"]["P"][1][1] + 1e-3 * 75
    assert first["reconciled"]["P"][1][1] < diffused


def test_a_repeated_identical_vintage_is_stale_not_new_information():
    session = InferenceSession(DAYS)
    first = session.step(DAYS[0], _batch(DAYS[0]), [], run_id="x")
    stale = dict(_observed(DAYS[1]))
    stale["information_timestamp"] = DAYS[0] + "T15:30:00+05:30"   # same vintage again
    repeated = session.step(DAYS[1], {"hawkes": stale, "rmt": stale,
                                      "hamilton": _absent("structural", "no_data_coverage",
                                                          "research exclusion")},
                            [], run_id="x")
    assert repeated["reconciled"]["tau_last_update"][1] == \
        first["reconciled"]["tau_last_update"][1]
    assert any("repeated or older observation ignored" in m
               for m in repeated["limitations"])
    # No new information means no covariance reduction.
    assert repeated["reconciled"]["P"][1][1] > first["reconciled"]["P"][1][1]


def test_research_exclusion_is_structural_and_survives_the_whole_replay():
    """Original Hamilton's NOT_PRODUCTION decision is a standing exclusion, not
    a feed outage: it must keep the pillar out of fusion on every session."""
    session = InferenceSession(DAYS)
    points = [session.step(d, _batch(d), [], run_id="x") for d in DAYS[:3]]
    assert all(p["coverage"]["mask"][2] is False for p in points)
    assert all(p["coverage"]["absence"]["hamilton"] == "structural" for p in points)
    assert all((p["composite"] or {}).get("shapley", [0, 0, 0])[2] == 0 for p in points)
