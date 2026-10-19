# C11 — FR43 portfolio overlay: exposure arithmetic and flag mapping
"""Independent of FR49 — this file imports nothing from the action log.

The invariant that matters most here is not the arithmetic, it is that an
absent micro-flag never reads as a clean one. `hawkes_output` is empty, so for
a real portfolio today the honest answer is "100% uncovered", and a test suite
that let "none" stand in for "unknown" would be certifying the opposite.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fixtures.mock_generator import mock_sector_flags
from seraph.decision_support import (
    MICRO_FLAGS,
    UNCLASSIFIED,
    PortfolioHolding,
    normalise_flag_source,
    portfolio_overlay,
)
from seraph.shared_types import SectorFlag

SECTORS = ("steel", "aluminium", "solar", "pharmaceuticals", "auto_components")


def _holdings(*pairs):
    """(sector, value) pairs → holdings rows with distinct symbols."""
    return [{"symbol": f"SYM{i}", "value": v, "sector": s}
            for i, (s, v) in enumerate(pairs)]


def _row(result, sector):
    return next(r for r in result.value["bySector"] if r["sectorId"] == sector)


# --- exposure arithmetic ---------------------------------------------------


def test_fr43_exposure_is_the_amber_share_of_total_portfolio_value():
    res = portfolio_overlay(
        _holdings(("steel", 60_000.0), ("pharmaceuticals", 40_000.0)),
        {"steel": "amber", "pharmaceuticals": "none"},
    )
    assert res.status == "ok"
    assert res.value["exposedPct"] == pytest.approx(60.0)
    assert res.value["totalValue"] == pytest.approx(100_000.0)
    assert res.value["coveredPct"] == pytest.approx(100.0)
    assert res.value["uncoveredPct"] == pytest.approx(0.0)
    assert res.warnings == ()


def test_fr43_sector_percentages_sum_to_one_hundred():
    res = portfolio_overlay(
        _holdings(("steel", 1.0), ("aluminium", 2.0), ("solar", 97.0)),
        {s: "none" for s in SECTORS},
    )
    assert res.status == "ok"
    assert sum(r["pct"] for r in res.value["bySector"]) == pytest.approx(100.0)
    assert _row(res, "solar")["pct"] == pytest.approx(97.0)


def test_fr43_several_holdings_in_one_sector_aggregate():
    res = portfolio_overlay(
        _holdings(("steel", 30_000.0), ("steel", 30_000.0),
                  ("pharmaceuticals", 40_000.0)),
        {"steel": "amber", "pharmaceuticals": "none"},
    )
    assert res.status == "ok"
    assert _row(res, "steel")["pct"] == pytest.approx(60.0)
    assert res.value["exposedPct"] == pytest.approx(60.0)


def test_fr43_repeated_symbol_is_one_position_matching_e11s_key():
    """E11 is keyed (user_id, symbol): two lots of a name are one position."""
    res = portfolio_overlay(
        [{"symbol": "TATASTEEL", "value": 40_000.0, "sector": "steel"},
         {"symbol": "TATASTEEL", "value": 20_000.0, "sector": "steel"},
         {"symbol": "SUNPHARMA", "value": 40_000.0, "sector": "pharmaceuticals"}],
        {"steel": "amber", "pharmaceuticals": "none"},
    )
    assert res.status == "ok"
    rows = res.value["byHolding"]
    assert [r["symbol"] for r in rows] == ["TATASTEEL", "SUNPHARMA"]
    assert rows[0]["exposurePct"] == pytest.approx(60.0)


def test_fr43_by_holding_carries_the_sector_flag_onto_each_line():
    """FR43 maps flags *onto the holdings*, and fills E11's exposure_pct."""
    res = portfolio_overlay(
        _holdings(("steel", 25_000.0), ("pharmaceuticals", 75_000.0)),
        {"steel": "amber", "pharmaceuticals": "none"},
    )
    assert res.status == "ok"
    rows = {r["symbol"]: r for r in res.value["byHolding"]}
    assert rows["SYM0"]["flag"] == "amber"
    assert rows["SYM0"]["exposurePct"] == pytest.approx(25.0)
    assert rows["SYM1"]["flag"] == "none"
    assert sum(r["exposurePct"] for r in res.value["byHolding"]) == pytest.approx(100.0)


def test_fr43_row_order_does_not_depend_on_input_order():
    """Equal-sized sectors must not reorder with the holdings list, or two
    identical portfolios render differently."""
    flags = {s: "none" for s in SECTORS}
    a = portfolio_overlay(_holdings(("steel", 50.0), ("solar", 50.0)), flags)
    b = portfolio_overlay(_holdings(("solar", 50.0), ("steel", 50.0)), flags)
    assert [r["sectorId"] for r in a.value["bySector"]] == \
           [r["sectorId"] for r in b.value["bySector"]] == ["solar", "steel"]


# --- missing mappings: the coverage obligation -----------------------------


def test_fr43_sector_absent_from_the_flag_source_is_uncovered_not_cleared():
    """The central honesty requirement. A sector nothing was said about must
    not be presented as "not flagged" — it was never checked."""
    res = portfolio_overlay(
        _holdings(("steel", 70_000.0), ("pharmaceuticals", 30_000.0)),
        {"steel": "amber"},                       # pharma: no flag at all
    )
    assert res.status == "ok"
    pharma = _row(res, "pharmaceuticals")
    assert pharma["covered"] is False
    assert res.value["uncoveredPct"] == pytest.approx(30.0)
    assert res.value["coveredPct"] == pytest.approx(70.0)
    assert [w.code for w in res.warnings] == ["PARTIAL_COVERAGE"]
    assert "pharmaceuticals" in res.warnings[0].context["sectors"]


def test_fr43_covered_and_unflagged_is_distinguishable_from_unknown():
    covered = portfolio_overlay(_holdings(("steel", 100.0)), {"steel": "none"})
    unknown = portfolio_overlay(_holdings(("steel", 100.0)), {})
    assert _row(covered, "steel")["covered"] is True
    assert _row(unknown, "steel")["covered"] is False
    assert covered.value["uncoveredPct"] == pytest.approx(0.0)
    assert unknown.value["uncoveredPct"] == pytest.approx(100.0)
    assert covered.warnings == () and unknown.warnings != ()


def test_fr43_no_flag_source_sizes_the_portfolio_and_claims_nothing():
    """What a real portfolio gets today: C5 has produced no micro-flags, so
    the overlay still sizes the holdings and flags nothing."""
    res = portfolio_overlay(_holdings(("steel", 60.0), ("solar", 40.0)), None)
    assert res.status == "ok"
    assert res.value["exposedPct"] == pytest.approx(0.0)
    assert res.value["uncoveredPct"] == pytest.approx(100.0)
    assert all(r["covered"] is False for r in res.value["bySector"])
    assert res.warnings[0].code == "PARTIAL_COVERAGE"


def test_fr43_holding_with_no_sector_is_sized_but_never_cleared():
    res = portfolio_overlay(
        [{"symbol": "UNKNOWNCO", "value": 20.0},
         {"symbol": "TATASTEEL", "value": 80.0, "sector": "steel"}],
        {"steel": "amber"},
    )
    assert res.status == "ok"
    row = _row(res, UNCLASSIFIED)
    assert row["pct"] == pytest.approx(20.0) and row["covered"] is False
    assert res.value["exposedPct"] == pytest.approx(80.0)
    assert res.value["uncoveredPct"] == pytest.approx(20.0)


def test_fr43_blank_sector_string_is_treated_as_unclassified():
    res = portfolio_overlay([{"symbol": "X", "value": 10.0, "sector": "   "}], {})
    assert res.status == "ok"
    assert res.value["bySector"][0]["sectorId"] == UNCLASSIFIED


# --- flag-source shapes ----------------------------------------------------


def test_fr43_accepts_the_sector_flags_c5_actually_emits():
    """FR14 emits tuple[SectorFlag, ...]; the overlay must take it directly
    rather than making every caller flatten it first."""
    flags = mock_sector_flags()
    res = portfolio_overlay(
        _holdings(("steel", 50.0), ("aluminium", 20.0), ("solar", 30.0)), flags)
    assert res.status == "ok"
    assert res.value["exposedPct"] == pytest.approx(70.0)   # steel + aluminium
    assert res.value["uncoveredPct"] == pytest.approx(0.0)
    assert res.warnings == ()


def test_fr43_accepts_the_dashboard_sector_flag_dicts():
    res = portfolio_overlay(
        _holdings(("steel", 50.0), ("pharmaceuticals", 50.0)),
        ({"sectorId": "steel", "flag": "amber"},
         {"sectorId": "pharmaceuticals", "flag": "none"}),
    )
    assert res.status == "ok"
    assert res.value["exposedPct"] == pytest.approx(50.0)


def test_fr43_accepts_typed_holdings():
    res = portfolio_overlay(
        [PortfolioHolding(symbol="TATASTEEL", value=100.0, quantity=5.0,
                          sector="steel")],
        {"steel": "amber"},
    )
    assert res.status == "ok"
    assert res.value["exposedPct"] == pytest.approx(100.0)


def test_fr43_normalise_flag_source_folds_every_accepted_shape():
    expected = {"steel": "amber"}
    for source in ({"steel": "amber"},
                   (SectorFlag(sector_id="steel", n=2.4, flag="amber"),),
                   [{"sectorId": "steel", "flag": "amber"}],
                   [{"sector_id": "steel", "flag": "amber"}]):
        res = normalise_flag_source(source)
        assert res.status == "ok" and res.value == expected
    assert normalise_flag_source(None).value == {}


# --- rejected input --------------------------------------------------------


def test_fr43_negative_empty_portfolio_is_rejected():
    for empty in ([], (), None):
        res = portfolio_overlay(empty, {"steel": "amber"})
        assert res.status == "error"
        assert res.error.kind == "CONTRACT_VIOLATION"
        assert res.error.field == "holdings"


def test_fr43_negative_zero_value_portfolio_is_rejected():
    """Exposure is a percentage *of portfolio value*; with no value there is
    no denominator and no honest number to report."""
    res = portfolio_overlay(_holdings(("steel", 0.0), ("solar", 0.0)),
                            {"steel": "amber"})
    assert res.status == "error"
    assert res.error.field == "holdings"
    assert "positive" in res.error.detail


@pytest.mark.parametrize("row, field_suffix", [
    ({"symbol": "X", "value": -5.0, "sector": "steel"}, "value"),
    ({"symbol": "X", "value": "not-a-number", "sector": "steel"}, "value"),
    ({"symbol": "X", "value": float("inf"), "sector": "steel"}, "value"),
    ({"symbol": "X", "value": float("nan"), "sector": "steel"}, "value"),
    ({"symbol": "X", "sector": "steel"}, "value"),
    ({"symbol": "  ", "value": 10.0, "sector": "steel"}, "symbol"),
    ({"value": 10.0, "sector": "steel"}, "symbol"),
    ({"symbol": "X", "value": 10.0, "quantity": -1.0}, "quantity"),
])
def test_fr43_negative_invalid_holdings_are_rejected(row, field_suffix):
    res = portfolio_overlay([row], {"steel": "amber"})
    assert res.status == "error"
    assert res.error.kind == "CONTRACT_VIOLATION"
    assert res.error.field == f"holdings[0].{field_suffix}"


def test_fr43_negative_non_mapping_row_is_rejected():
    res = portfolio_overlay(["TATASTEEL"], {})
    assert res.status == "error"
    assert res.error.field == "holdings[0]"


def test_fr43_negative_unknown_flag_value_is_rejected():
    """ARCHITECTURE §2 S10 fixes the union at none|amber. A third level would
    have to be agreed there first, not smuggled through a caller."""
    res = portfolio_overlay(_holdings(("steel", 10.0)), {"steel": "red"})
    assert res.status == "error"
    assert res.error.field == "sector_flags['steel']"


def test_fr43_negative_conflicting_flags_for_one_sector_are_rejected():
    res = portfolio_overlay(
        _holdings(("steel", 10.0)),
        (SectorFlag(sector_id="steel", n=2.4, flag="amber"),
         SectorFlag(sector_id="steel", n=0.4, flag="none")),
    )
    assert res.status == "error"
    assert "conflicting" in res.error.detail


def test_fr43_negative_malformed_flag_source_is_rejected():
    assert normalise_flag_source("steel=amber").status == "error"
    assert normalise_flag_source([object()]).status == "error"
    assert normalise_flag_source([{"flag": "amber"}]).status == "error"


def test_fr43_negative_one_symbol_in_two_sectors_is_rejected():
    """Silently picking a winner would change the sizing without telling
    anyone which classification was used."""
    res = portfolio_overlay(
        [{"symbol": "TATASTEEL", "value": 10.0, "sector": "steel"},
         {"symbol": "TATASTEEL", "value": 10.0, "sector": "aluminium"}],
        {"steel": "amber"},
    )
    assert res.status == "error"
    assert res.error.field == "holdings[1].sector"


# --- invariants ------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    rows=st.lists(
        st.tuples(
            st.sampled_from(SECTORS),
            st.floats(min_value=1.0, max_value=1e9,
                      allow_nan=False, allow_infinity=False),
        ),
        min_size=1, max_size=12,
    ),
    flag_map=st.dictionaries(
        st.sampled_from(SECTORS), st.sampled_from(MICRO_FLAGS), max_size=5),
)
def test_fr43_exposure_invariants_hold_for_any_positive_portfolio(rows, flag_map):
    res = portfolio_overlay(_holdings(*rows), flag_map)
    assert res.status == "ok"
    v = res.value

    assert sum(r["pct"] for r in v["bySector"]) == pytest.approx(100.0)
    assert sum(r["exposurePct"] for r in v["byHolding"]) == pytest.approx(100.0)
    assert v["coveredPct"] + v["uncoveredPct"] == pytest.approx(100.0)
    # Exposure can only be claimed over the part of the portfolio the flag
    # source actually spoke to.
    assert -1e-9 <= v["exposedPct"] <= v["coveredPct"] + 1e-9 <= 100.0 + 1e-9
    assert v["exposedPct"] == pytest.approx(
        sum(r["pct"] for r in v["bySector"] if r["flag"] == "amber"))
    assert all(r["flag"] in MICRO_FLAGS for r in v["bySector"])
    # An uncovered sector is never counted as exposure, and coverage is
    # reported exactly when it is incomplete.
    assert all(not (r["flag"] == "amber" and not r["covered"])
               for r in v["bySector"])
    assert (v["uncoveredPct"] > 0.0) == any(
        w.code == "PARTIAL_COVERAGE" for w in res.warnings)
