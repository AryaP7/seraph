"""FIX09 — a missing instrument-classification table cannot silently pass.

Audit finding A14: `equity_symbols()` returned an empty set when the vendored
ISIN file was absent, and `is_equity()` then answered True for every symbol.
A deployment missing that one file would silently readmit ETFs to the FR52
equity universe — index ETFs are near-exact linear combinations of other
members, so they inflate exactly the leading eigenvalue the RMT pillar
measures.

The file is present in this checkout, so these tests drive the failure path by
pointing the module at a missing or unusable table.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seraph.universe import constructor as c3
from seraph.universe import instrument_type as it
from seraph.universe.constructor import SymbolStats, build_snapshot


@pytest.fixture
def unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(it, "_ISIN_CSV", tmp_path / "absent.csv")
    it.equity_symbols.cache_clear()
    yield
    it.equity_symbols.cache_clear()


@pytest.fixture
def too_sparse(monkeypatch, tmp_path):
    path = tmp_path / "sparse.csv"
    path.write_text("SYMBOL,ISIN\nRELIANCE,INE002A01018\n", encoding="utf-8")
    monkeypatch.setattr(it, "_ISIN_CSV", path)
    it.equity_symbols.cache_clear()
    yield
    it.equity_symbols.cache_clear()


def panel():
    return [SymbolStats(symbol=s, listing_days=2000, median_tottrdval=v)
            for s, v in [("RELIANCE", 9e9), ("NIFTYBEES", 8e9), ("TCS", 7e9)]]


def test_classification_status_reports_the_real_table():
    status = it.classification_status()
    assert status.available and status.symbol_count > it.MIN_USABLE_SYMBOLS
    assert status.reason is None


def test_a_missing_table_is_reported_unavailable(unavailable):
    status = it.classification_status()
    assert status.available is False and status.symbol_count == 0
    assert "not found" in status.reason


def test_a_sparse_table_is_reported_unavailable(too_sparse):
    status = it.classification_status()
    assert status.available is False
    assert "usable floor" in status.reason


def test_is_equity_raises_rather_than_accepting_everything(unavailable):
    with pytest.raises(it.ClassificationUnavailable):
        it.is_equity("NIFTYBEES")
    with pytest.raises(it.ClassificationUnavailable):
        it.is_equity("RELIANCE")


def test_universe_construction_fails_explicitly(unavailable):
    result = build_snapshot(rebalance_date="2020-01-01", panel=panel(), target=3)
    assert result.status == "error"
    assert result.error.kind == "MISSING_DEPENDENCY"
    assert result.error.entity == "instrument_classification"
    assert result.error.retryable is True


def test_the_degraded_mode_is_opt_in_and_visibly_warned(unavailable):
    result = build_snapshot(rebalance_date="2020-01-01", panel=panel(), target=3,
                            allow_unclassified=True)
    assert result.status == "ok"
    # The ETF is present precisely because the filter could not run, and the
    # snapshot says so rather than presenting itself as an equity universe.
    assert "NIFTYBEES" in result.value.members
    codes = [w.code for w in result.warnings]
    assert "PARTIAL_COVERAGE" in codes
    warning = next(w for w in result.warnings if w.code == "PARTIAL_COVERAGE")
    assert "equity filter was NOT applied" in warning.message
    assert "degraded" in warning.message


def test_the_normal_path_still_filters_etfs_out():
    result = build_snapshot(rebalance_date="2020-01-01", panel=panel(), target=3)
    assert result.status == "ok"
    assert "NIFTYBEES" not in result.value.members
    assert set(result.value.members) == {"RELIANCE", "TCS"}
    assert not any(w.code == "PARTIAL_COVERAGE" for w in result.warnings)


def test_the_hawkes_basket_refuses_an_unclassified_universe(unavailable):
    from seraph.ingestion.hawkes_universe import build_symbol_list
    with pytest.raises(it.ClassificationUnavailable, match="unclassified basket"):
        build_symbol_list(["RELIANCE", "NIFTYBEES"])


def test_equities_only_false_does_not_need_classification(unavailable):
    result = build_snapshot(rebalance_date="2020-01-01", panel=panel(), target=3,
                            equities_only=False)
    assert result.status == "ok" and "NIFTYBEES" in result.value.members
    assert not any(w.code == "PARTIAL_COVERAGE" for w in result.warnings)
