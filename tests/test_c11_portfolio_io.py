# C11 — FR43's two production seams: the E11 reader and the flag-source adapter
"""The failure these tests exist to prevent is a sector reported as *cleared*
that was never measured.

FR14's arithmetic makes that easy to do by accident
(`seraph/pillars/hawkes/engine.py`, `sector_flags`):

    base  = sector_baselines.get(sector, 0.0)
    ratio = realised / base if base > 0 else 0.0
    flag  = "amber" if ratio >= amber_multiple else "none"

A sector with **no baseline** falls through to `ratio = 0.0` and is emitted with
`flag="none"` — byte-identical to a sector that was measured and found quiet.
Pushed through `normalise_flag_source` it becomes `covered: true` and its share
lands in `coveredPct`, so the overlay would state that a sector nobody looked at
is clean. `measured_flag_source` is the screen that stops that, and the tests
below pin both halves: that an unmeasured `none` is **uncovered**, and that a
genuinely measured `none` is still **covered**.

The reader half is pinned on two properties that are also silent when broken:
`user_id` scoping (an unscoped read returns another user's portfolio) and the
exclusion of the stored `exposure_pct` column (a stale stored figure silently
replacing derived arithmetic).

No database is required. `_Conn` is a stub exposing `fetch`, which is the whole
surface `read_user_portfolio` uses, so these run hermetically and fast. There is
no pytest-asyncio in this project, so coroutines are driven with `asyncio.run`,
matching `tests/test_csrs_research_driver.py`.
"""
from __future__ import annotations

import asyncio

import pytest

from seraph.decision_support.portfolio import (
    MICRO_FLAGS,
    measured_flag_source,
    normalise_flag_source,
)
from seraph.decision_support.portfolio_io import (
    _SELECT_HOLDINGS,
    portfolio_overlay_for_user,
    read_user_portfolio,
)
from seraph.shared_types import SectorFlag


class _Conn:
    """Minimal asyncpg stand-in: `fetch(sql, *params)` over an in-memory E11.

    Rows are plain dicts, which support `r[key]` exactly as `asyncpg.Record`
    does for the column access the reader performs. The stub applies the
    `user_id` filter **itself**, so a reader that forgot its WHERE clause would
    still be caught by `test_read_is_scoped_to_the_requested_user`: the
    assertion is on what comes back, not on the SQL text.
    """

    def __init__(self, table: list[dict]):
        self.table = table
        self.calls: list[tuple] = []

    async def fetch(self, sql: str, *params):
        self.calls.append((sql, params))
        uid = params[0] if params else None
        rows = [r for r in self.table if r["user_id"] == uid]
        return sorted(rows, key=lambda r: r["symbol"])


def _e11(user_id: str, symbol: str, value: float, sector: str,
         *, quantity: float = 1.0, exposure_pct: float = -999.0) -> dict:
    """One E11 row. `exposure_pct` defaults to a **deliberately absurd** value
    so that any test which accidentally depends on it fails loudly."""
    return {"user_id": user_id, "symbol": symbol, "quantity": quantity,
            "value": value, "sector": sector, "exposure_pct": exposure_pct}


TABLE = [
    _e11("alice", "TATASTEEL", 60.0, "steel"),
    _e11("alice", "SUNPHARMA", 40.0, "pharmaceuticals"),
    _e11("bob", "INFY", 100.0, "it_services"),
]


# ---------------------------------------------------------------------------
# ownership / user_id scoping
# ---------------------------------------------------------------------------
def test_read_is_scoped_to_the_requested_user():
    """An unscoped read would hand one user another's holdings."""
    res = asyncio.run(read_user_portfolio(_Conn(TABLE), "alice"))
    assert res.status == "ok"
    assert [h.symbol for h in res.value] == ["SUNPHARMA", "TATASTEEL"]
    assert "INFY" not in [h.symbol for h in res.value], (
        "bob's holding appeared in alice's portfolio")

    other = asyncio.run(read_user_portfolio(_Conn(TABLE), "bob"))
    assert [h.symbol for h in other.value] == ["INFY"]


def test_read_passes_the_user_id_as_a_bound_parameter():
    """Scoping must be a bound parameter, not interpolated into the SQL."""
    conn = _Conn(TABLE)
    asyncio.run(read_user_portfolio(conn, "alice"))
    sql, params = conn.calls[0]
    assert params == ("alice",)
    assert "alice" not in sql, "user_id was interpolated into the SQL text"
    assert "$1" in sql


@pytest.mark.parametrize("bad", ["", "   ", None, 7])
def test_read_rejects_a_blank_or_non_string_user_id(bad):
    res = asyncio.run(read_user_portfolio(_Conn(TABLE), bad))
    assert res.status == "error"
    assert res.error.kind == "CONTRACT_VIOLATION"
    assert res.error.field == "user_id"


def test_read_trims_the_user_id_before_scoping():
    res = asyncio.run(read_user_portfolio(_Conn(TABLE), "  alice  "))
    assert res.status == "ok"
    assert len(res.value) == 2


def test_read_rejects_something_that_is_not_a_connection():
    res = asyncio.run(read_user_portfolio(object(), "alice"))
    assert res.status == "error"
    assert res.error.field == "conn"


# ---------------------------------------------------------------------------
# exposure_pct is derived, never read
# ---------------------------------------------------------------------------
def test_stored_exposure_pct_is_not_even_selected():
    """The strongest form of 'never read as source of truth': the column is
    absent from the query, so it cannot leak in by mistake."""
    assert "exposure_pct" not in _SELECT_HOLDINGS
    for col in ("symbol", "quantity", "value", "sector"):
        assert col in _SELECT_HOLDINGS
    assert "user_id = $1" in _SELECT_HOLDINGS


def test_exposure_pct_is_recomputed_and_ignores_the_stored_value():
    """Every stored `exposure_pct` in TABLE is -999.0. The derived figures must
    be the real shares, which is only possible if the column is ignored."""
    res = asyncio.run(portfolio_overlay_for_user(_Conn(TABLE), "alice"))
    assert res.status == "ok"
    by = {r["symbol"]: r["exposurePct"] for r in res.value["byHolding"]}
    assert by["TATASTEEL"] == pytest.approx(60.0)
    assert by["SUNPHARMA"] == pytest.approx(40.0)
    assert all(v > 0 for v in by.values()), "a stored -999.0 reached the output"


# ---------------------------------------------------------------------------
# empty portfolio — the existing ContractViolation is preserved
# ---------------------------------------------------------------------------
def test_a_user_with_no_holdings_is_a_successful_read_of_nothing():
    """The reader must not turn an empty portfolio into a read error; that
    judgement belongs to FR43's arithmetic, in one place."""
    res = asyncio.run(read_user_portfolio(_Conn(TABLE), "carol"))
    assert res.status == "ok"
    assert res.value == ()


def test_empty_portfolio_still_raises_the_existing_contract_violation():
    """FR43's empty-portfolio rejection must be reached through the new entry
    point too, with the same field and the same error kind."""
    res = asyncio.run(portfolio_overlay_for_user(_Conn(TABLE), "carol"))
    assert res.status == "error"
    assert res.error.kind == "CONTRACT_VIOLATION"
    assert res.error.field == "holdings"
    assert "empty portfolio" in res.error.detail


# ---------------------------------------------------------------------------
# missing measurements — the central honesty requirement
# ---------------------------------------------------------------------------
def test_unmeasured_none_from_a_zero_baseline_is_uncovered_not_clean():
    """FR14 emits flag="none", n=0.0 when base <= 0. That must not read as
    cleared."""
    flags = (SectorFlag(sector_id="steel", n=0.0, flag="none"),)
    res = measured_flag_source(flags)
    assert res.status == "ok"
    assert res.value == {}, "an unmeasured sector was kept as a coverage claim"
    assert res.warnings and res.warnings[0].code == "PARTIAL_COVERAGE"
    assert "steel" in res.warnings[0].context["sectors"]


def test_the_same_flag_through_the_old_path_would_have_read_as_clean():
    """Pins the defect being fixed, so the fix cannot be silently reverted."""
    flags = (SectorFlag(sector_id="steel", n=0.0, flag="none"),)
    naive = normalise_flag_source(flags)
    assert naive.value == {"steel": "none"}, (
        "normalise_flag_source's documented behaviour changed; it is supposed "
        "to treat every entry as an explicit coverage claim")
    screened = measured_flag_source(flags)
    assert screened.value == {}
    assert naive.value != screened.value, (
        "the adapter is not actually screening anything")


def test_unmeasured_sector_lands_in_uncovered_pct_end_to_end():
    """The whole point, measured in percentages: an unmeasured steel sector
    must appear as 60% uncovered, not 60% clean."""
    flags = (SectorFlag(sector_id="steel", n=0.0, flag="none"),
             SectorFlag(sector_id="pharmaceuticals", n=1.2, flag="none"))
    res = asyncio.run(portfolio_overlay_for_user(
        _Conn(TABLE), "alice", "2026-10-14T15:30:00+05:30",
        sector_flags=flags))
    assert res.status == "ok"
    rows = {r["sectorId"]: r for r in res.value["bySector"]}
    assert rows["steel"]["covered"] is False
    assert rows["pharmaceuticals"]["covered"] is True
    assert res.value["uncoveredPct"] == pytest.approx(60.0)
    assert res.value["coveredPct"] == pytest.approx(40.0)
    assert res.value["exposedPct"] == pytest.approx(0.0)
    codes = [w.code for w in res.warnings]
    assert codes.count("PARTIAL_COVERAGE") >= 1


def test_baselines_disambiguate_a_genuinely_quiet_measured_sector():
    """n == 0.0 is ambiguous without baselines. Supplied with them, a sector
    whose baseline is positive is measured even at a zero ratio."""
    flags = (SectorFlag(sector_id="steel", n=0.0, flag="none"),)
    without = measured_flag_source(flags)
    assert without.value == {}                      # conservative default
    with_base = measured_flag_source(flags, sector_baselines={"steel": 0.4})
    assert with_base.value == {"steel": "none"}, (
        "a positive baseline means the sector WAS measured and found quiet")
    assert with_base.warnings == ()
    zero_base = measured_flag_source(flags, sector_baselines={"steel": 0.0})
    assert zero_base.value == {}
    assert zero_base.warnings and "baseline" in \
        zero_base.warnings[0].context["reason"]


def test_a_dict_flag_without_an_n_is_treated_as_unmeasured():
    """A bare {sectorId, flag} carries no measurement evidence, which is
    exactly the default-`none` case this adapter screens."""
    res = measured_flag_source(({"sectorId": "steel", "flag": "none"},))
    assert res.value == {}
    assert res.warnings and res.warnings[0].code == "PARTIAL_COVERAGE"


def test_a_plain_mapping_is_refused_rather_than_screened():
    """A mapping is an explicit caller assertion of coverage; screening it
    would silently discard a claim the caller meant to make."""
    res = measured_flag_source({"steel": "none"})
    assert res.status == "error"
    assert res.error.field == "sector_flags"
    assert "normalise_flag_source" in res.error.detail


# ---------------------------------------------------------------------------
# genuine measured flags
# ---------------------------------------------------------------------------
def test_measured_amber_is_covered_and_exposed():
    flags = (SectorFlag(sector_id="steel", n=2.5, flag="amber"),
             SectorFlag(sector_id="pharmaceuticals", n=0.8, flag="none"))
    res = asyncio.run(portfolio_overlay_for_user(
        _Conn(TABLE), "alice", sector_flags=flags))
    assert res.status == "ok"
    assert res.value["exposedPct"] == pytest.approx(60.0)   # steel
    assert res.value["uncoveredPct"] == pytest.approx(0.0)
    assert res.value["coveredPct"] == pytest.approx(100.0)
    assert res.warnings == (), "fully measured coverage must warn about nothing"


def test_amber_is_kept_even_at_a_zero_ratio_because_amber_implies_measurement():
    """A defensive case: FR14 cannot emit amber from ratio 0, but if a caller
    hands one over, amber is an affirmative statement and is kept."""
    res = measured_flag_source((SectorFlag(sector_id="steel", n=0.0,
                                           flag="amber"),))
    assert res.value == {"steel": "amber"}
    assert res.warnings == ()


def test_measured_none_with_a_positive_ratio_is_covered():
    res = measured_flag_source((SectorFlag(sector_id="steel", n=0.9,
                                           flag="none"),))
    assert res.value == {"steel": "none"}
    assert res.warnings == ()


def test_micro_flags_union_is_not_widened():
    """Coverage rides alongside the flag; S10's union stays two-valued."""
    assert MICRO_FLAGS == ("none", "amber")


def test_an_out_of_union_flag_is_rejected_by_the_adapter_too():
    res = measured_flag_source(({"sectorId": "steel", "flag": "unknown",
                                 "n": 1.0},))
    assert res.status == "error"
    assert "S10" in res.error.detail


def test_conflicting_flags_for_one_sector_are_rejected():
    res = measured_flag_source((SectorFlag(sector_id="steel", n=2.0, flag="amber"),
                                SectorFlag(sector_id="steel", n=0.5, flag="none")))
    assert res.status == "error"
    assert "conflicting" in res.error.detail


# ---------------------------------------------------------------------------
# coverage calculations
# ---------------------------------------------------------------------------
def test_no_flag_source_at_all_is_one_hundred_percent_uncovered():
    """What a real portfolio gets today: no production micro-flag source
    exists, so nothing can be claimed clean."""
    res = asyncio.run(portfolio_overlay_for_user(_Conn(TABLE), "alice"))
    assert res.status == "ok"
    assert res.value["uncoveredPct"] == pytest.approx(100.0)
    assert res.value["coveredPct"] == pytest.approx(0.0)
    assert res.value["exposedPct"] == pytest.approx(0.0)
    assert all(r["covered"] is False for r in res.value["bySector"])


def test_covered_plus_uncovered_is_always_one_hundred():
    for flags in (None,
                  (SectorFlag(sector_id="steel", n=0.0, flag="none"),),
                  (SectorFlag(sector_id="steel", n=2.0, flag="amber"),),
                  (SectorFlag(sector_id="steel", n=2.0, flag="amber"),
                   SectorFlag(sector_id="pharmaceuticals", n=1.0, flag="none"))):
        res = asyncio.run(portfolio_overlay_for_user(
            _Conn(TABLE), "alice", sector_flags=flags))
        assert res.status == "ok"
        assert (res.value["coveredPct"] + res.value["uncoveredPct"]
                == pytest.approx(100.0))


def test_exposed_pct_never_exceeds_covered_pct():
    """You cannot be exposed in a sector you could not measure."""
    flags = (SectorFlag(sector_id="steel", n=0.0, flag="none"),
             SectorFlag(sector_id="pharmaceuticals", n=3.0, flag="amber"))
    res = asyncio.run(portfolio_overlay_for_user(
        _Conn(TABLE), "alice", sector_flags=flags))
    assert res.value["exposedPct"] <= res.value["coveredPct"] + 1e-9
    assert res.value["exposedPct"] == pytest.approx(40.0)   # pharma only


def test_screen_measurement_false_restores_the_explicit_assertion_path():
    """Opt-out exists for a caller-supplied mapping that genuinely asserts
    coverage; it must route to normalise_flag_source."""
    res = asyncio.run(portfolio_overlay_for_user(
        _Conn(TABLE), "alice", sector_flags={"steel": "none",
                                             "pharmaceuticals": "none"},
        screen_measurement=False))
    assert res.status == "ok"
    assert res.value["uncoveredPct"] == pytest.approx(0.0)
    assert res.value["exposedPct"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# the `at` limitation is stated in the payload, not papered over
# ---------------------------------------------------------------------------
def test_payload_states_that_holdings_are_current_not_point_in_time():
    """E11's PK is (user_id, symbol) with no timestamp, so S10's `at` cannot be
    honoured as a point-in-time lookup. The payload must say so."""
    at = "2020-03-23T15:30:00+05:30"
    res = asyncio.run(portfolio_overlay_for_user(_Conn(TABLE), "alice", at))
    assert res.status == "ok"
    assert res.value["evaluatedAt"] == at
    assert res.value["holdingsAsOf"] == "current", (
        "a historical `at` must not be presented as a reconstructed portfolio")
    assert res.value["userId"] == "alice"
    assert res.value["holdingsCount"] == 2


def test_a_malformed_e11_row_is_a_contract_violation_naming_the_row():
    bad = [_e11("dave", "NEGVAL", -5.0, "steel")]
    res = asyncio.run(read_user_portfolio(_Conn(bad), "dave"))
    assert res.status == "error"
    assert res.error.kind == "CONTRACT_VIOLATION"
    assert "NEGVAL" in res.error.detail
