"""DATA03 — both bhavcopy schemas parse, and TOTTRDVAL stops being a proxy.

The audit found no real bhavcopy reader at all: tests exercised a
`bhavcopy-legacy` *label* without parsing a real file. FR52 ranks the universe
by six-month median TOTTRDVAL, and `eod2_client` approximates it as
`close × volume`, so the exact column is not cosmetic — it decides membership.

Fixtures below are hand-built in both layouts rather than downloaded: the
point is that the parser handles the real column spellings, which is checkable
without the network.
"""
from __future__ import annotations

import pytest

from seraph.ingestion.bhavcopy_reader import (
    UnknownBhavcopySchema,
    compare_with_proxy,
    detect_schema,
    parse_bhavcopy,
)

LEGACY = (
    "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,"
    "TIMESTAMP,TOTALTRADES,ISIN\n"
    "RELIANCE,EQ,2800.00,2850.00,2780.00,2820.00,2820.00,2795.00,1000000,"
    "2815000000.00,28-JUN-2024,45000,INE002A01018\n"
    "TCS,EQ,3600.00,3620.00,3580.00,3600.00,3600.00,3595.00,500000,"
    "1800000000.00,28-JUN-2024,21000,INE467B01029\n"
    "GOLDBEES,EQ,55.00,55.50,54.80,55.20,55.20,55.00,2000000,"
    "110300000.00,28-JUN-2024,8000,INF204KB17I5\n"
    "SOMESME,SM,10.00,11.00,9.50,10.50,10.50,10.00,1000,"
    "10500.00,28-JUN-2024,12,INE999Z01011\n"
)

UDIFF = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
    "OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,TtlTradgVol,"
    "TtlTrfVal,TtlNbOfTxsExctd\n"
    "2024-08-01,2024-08-01,CM,NSE,STK,2885,INE002A01018,RELIANCE,EQ,"
    "2900.00,2950.00,2880.00,2930.00,2930.00,2895.00,1200000,"
    "3510000000.00,52000\n"
    "2024-08-01,2024-08-01,CM,NSE,STK,11536,INE467B01029,TCS,EQ,"
    "3700.00,3720.00,3680.00,3700.00,3700.00,3695.00,400000,"
    "1480000000.00,19000\n"
)


# ------------------------------------------------------ schema detection


def test_each_schema_is_detected_from_its_header():
    assert detect_schema(LEGACY.splitlines()[0].split(",")) == "bhavcopy-legacy"
    assert detect_schema(UDIFF.splitlines()[0].split(",")) == "bhavcopy-udiff"


def test_an_unknown_header_names_the_columns_it_saw():
    with pytest.raises(UnknownBhavcopySchema, match="Columns present"):
        parse_bhavcopy("FOO,BAR\n1,2\n")


def test_the_filename_is_not_evidence():
    """Detection reads the header; a legacy-looking name with UDiFF columns
    still parses as UDiFF."""
    assert parse_bhavcopy(UDIFF).schema == "bhavcopy-udiff"


# ----------------------------------------------------------- parsing


def test_the_legacy_schema_parses_with_exact_traded_value():
    result = parse_bhavcopy(LEGACY)
    assert result.schema == "bhavcopy-legacy"
    assert result.trade_date == "2024-06-28"
    assert result.traded_value_basis == "exact_TOTTRDVAL"
    reliance = next(r for r in result.rows if r.symbol == "RELIANCE")
    assert reliance.traded_value == 2815000000.0
    assert reliance.traded_quantity == 1000000
    assert reliance.isin == "INE002A01018"
    assert reliance.trades == 45000


def test_the_udiff_schema_parses_the_same_quantities():
    result = parse_bhavcopy(UDIFF)
    assert result.schema == "bhavcopy-udiff"
    assert result.trade_date == "2024-08-01"
    reliance = next(r for r in result.rows if r.symbol == "RELIANCE")
    assert reliance.traded_value == 3510000000.0
    assert reliance.traded_quantity == 1200000
    assert reliance.close == 2930.0 and reliance.prev_close == 2895.0


def test_both_schemas_normalise_to_one_shape():
    legacy = {r.symbol for r in parse_bhavcopy(LEGACY).rows}
    udiff = {r.symbol for r in parse_bhavcopy(UDIFF).rows}
    assert {"RELIANCE", "TCS"} <= legacy and {"RELIANCE", "TCS"} == udiff
    fields = lambda rows: {k for k in rows[0].__dataclass_fields__}  # noqa: E731
    assert fields(parse_bhavcopy(LEGACY).rows) == fields(parse_bhavcopy(UDIFF).rows)


def test_non_equity_series_are_skipped_and_counted():
    result = parse_bhavcopy(LEGACY)
    assert "SOMESME" not in {r.symbol for r in result.rows}
    assert result.skipped_series == {"SM": 1}


# --------------------------------------------------------- rejections


def test_an_unparseable_traded_value_is_rejected_not_zeroed():
    bad = LEGACY.replace("2815000000.00", "n/a")
    result = parse_bhavcopy(bad)
    assert "RELIANCE" not in {r.symbol for r in result.rows}
    assert any("traded_value" in r["field"] for r in result.rejected)
    # A zeroed traded value would sort a liquid name to the bottom of FR52.
    assert all(r.traded_value > 0 for r in result.rows)


def test_a_negative_quantity_is_rejected():
    bad = LEGACY.replace(",1000000,", ",-1000000,")
    assert any("negative" in r["reason"] for r in parse_bhavcopy(bad).rejected)


def test_high_below_low_is_rejected():
    bad = LEGACY.replace("2800.00,2850.00,2780.00", "2800.00,2700.00,2780.00")
    assert any("below low" in r["reason"] for r in parse_bhavcopy(bad).rejected)


def test_a_row_from_another_session_is_rejected():
    mixed = LEGACY + ("INFY,EQ,1500,1510,1490,1500,1500,1495,100,150000.00,"
                      "29-JUN-2024,10,INE009A01021\n")
    result = parse_bhavcopy(mixed)
    assert "INFY" not in {r.symbol for r in result.rows}
    assert any("a bhavcopy covers one session" in r["reason"]
               for r in result.rejected)


def test_an_unparseable_date_is_rejected():
    bad = LEGACY.replace("28-JUN-2024", "not-a-date")
    assert any("unparseable trade date" in r["reason"]
               for r in parse_bhavcopy(bad).rejected)


def test_a_missing_traded_value_column_is_declared_unavailable():
    """The proxy is never substituted under the exact column's name."""
    without = "\n".join(
        ",".join(part for i, part in enumerate(line.split(","))
                 if i != LEGACY.splitlines()[0].split(",").index("TOTTRDVAL"))
        for line in LEGACY.splitlines())
    result = parse_bhavcopy(without)
    assert result.traded_value_basis == "unavailable"
    assert all(r.traded_value == 0.0 for r in result.rows)
    assert result.describe()["traded_value_basis"] == "unavailable"


# ------------------------------------------ the proxy, quantified


def test_the_proxy_error_is_measured_not_asserted():
    result = parse_bhavcopy(LEGACY)
    reliance = next(r for r in result.rows if r.symbol == "RELIANCE")
    # close x volume = 2820 * 1,000,000 = 2.82e9 against an exact 2.815e9.
    assert reliance.proxy_value == pytest.approx(2.82e9)
    assert reliance.proxy_error == pytest.approx((2.82e9 - 2.815e9) / 2.815e9)


def test_the_comparison_reports_whether_ranking_would_change():
    comparison = compare_with_proxy(parse_bhavcopy(LEGACY))
    assert comparison["comparable"] == 3
    assert "universe membership" in comparison["note"]
    assert comparison["worst_symbol"] in {"RELIANCE", "TCS", "GOLDBEES"}


def test_a_rank_flip_between_exact_and_proxy_is_detected():
    """Two names whose order differs under the proxy."""
    flipped = (
        "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,"
        "TIMESTAMP\n"
        # Exact value higher, but a low close makes the proxy smaller.
        "AAA,EQ,100,180,95,100,100,99,1000000,150000000.00,28-JUN-2024\n"
        # Exact value lower, but a high close inflates the proxy.
        "BBB,EQ,140,150,139,145,145,140,1000000,142000000.00,28-JUN-2024\n")
    comparison = compare_with_proxy(parse_bhavcopy(flipped))
    assert comparison["rank_positions_changed"] == 2, \
        "the proxy reverses these two, which is exactly the FR52 risk"


def test_the_describe_summary_carries_the_proxy_comparison():
    described = parse_bhavcopy(LEGACY).describe()
    assert described["schema"] == "bhavcopy-legacy"
    assert described["proxy_comparison"]["n"] == 3
    assert "top-500 boundary" in described["proxy_comparison"]["note"]
