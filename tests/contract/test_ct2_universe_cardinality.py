# CT-2 — C3 ⇄ C6: universe cardinality and churn (ARCHITECTURE §5 ⑤)
"""Proves RMT receives the intended universe, that FR52's filter precedes the
rank, and that D3's buffer reduces churn.

Note on the fixture size: ARCHITECTURE's sketch says "600-symbol panel, 120
with <1000 days" and also asserts 500 members — arithmetically impossible
(600−120 = 480). The panel is 650 here so 530 names are eligible and a full
500-member universe is actually reachable; the 120 short-history names and the
40 rank traps are kept exactly as specified. The 480-eligible case is asserted
separately as the underfill negative.
"""
from __future__ import annotations

import pytest

from seraph.universe.constructor import SymbolStats, build_snapshot

N_TOTAL, N_SHORT, N_TRAPS = 650, 120, 40


def _panel(n_total: int = N_TOTAL, n_short: int = N_SHORT, n_traps: int = N_TRAPS):
    """Long-history names get modest turnover; the first `n_traps` short-history
    names get enormous turnover, so ranking BEFORE filtering would pull them in."""
    panel = []
    for i in range(n_total - n_short):
        panel.append(SymbolStats(f"LONG{i:04d}", listing_days=1200 + i, median_tottrdval=1e6 + i))
    for i in range(n_short):
        turnover = 1e12 - i if i < n_traps else 1e3
        panel.append(SymbolStats(f"SHORT{i:04d}", listing_days=999 - i, median_tottrdval=turnover))
    return panel


def test_ct2_exactly_500_members_and_filter_precedes_rank():
    res = build_snapshot(equities_only=False, rebalance_date="2020-01-01", panel=_panel())
    assert res.status == "ok", res
    snap = res.value

    assert len(snap.members) == 500
    assert len(set(snap.members)) == 500, "no duplicates"
    assert snap.eligible_count == N_TOTAL - N_SHORT

    # None of the 120 short-history names may appear — including the 40 traps,
    # which outrank every eligible name on turnover alone (FR52 bug trap).
    assert not [m for m in snap.members if m.startswith("SHORT")]

    # Ranking is by turnover among the eligible, descending.
    assert snap.members[0] == "LONG0529"


def test_ct2_negative_underfilled_universe_warns_never_silent():
    res = build_snapshot(equities_only=False, rebalance_date="2008-01-01", panel=_panel(600, 120, 40))
    assert res.status == "ok", "underfill is a warning, not an error"
    snap = res.value
    assert len(snap.members) == 480, "N floats down to the eligible count"
    warn = [w for w in res.warnings if w.code == "UNIVERSE_UNDERFILLED"]
    assert warn, "a short universe must never ship silently"
    assert warn[0].context["shortfall"] == 20
    assert warn[0].context["members"] == 480


def test_ct2_buffer_rule_reduces_churn():
    """D3(b): incumbents held to a looser rank than entrants must clear, so
    names flapping across the boundary do not churn the universe."""
    first = build_snapshot(equities_only=False, rebalance_date="2020-01-01", panel=_panel())
    assert first.status == "ok"
    incumbents = first.value.members

    # Next period: turnover reshuffles around the rank-500 boundary.
    shifted = []
    for s in _panel():
        bump = 1.0
        if s.symbol.startswith("LONG"):
            idx = int(s.symbol[4:])
            if 470 <= idx <= 530:          # the flap zone straddling rank 500
                bump = 1.05 if idx % 2 else 0.95
        shifted.append(SymbolStats(s.symbol, s.listing_days, s.median_tottrdval * bump))

    with_buffer = build_snapshot(equities_only=False, rebalance_date="2020-07-01", panel=shifted, incumbents=incumbents, use_buffer=True)
    without = build_snapshot(equities_only=False, rebalance_date="2020-07-01", panel=shifted, incumbents=incumbents, use_buffer=False
    )
    assert with_buffer.status == "ok" and without.status == "ok"
    assert with_buffer.value.churn_fraction < without.value.churn_fraction
    assert len(with_buffer.value.members) == 500


def test_ct2_churn_bookkeeping_is_consistent():
    first = build_snapshot(equities_only=False, rebalance_date="2020-01-01", panel=_panel())
    incumbents = first.value.members
    # Drop the 5 most liquid incumbents out of eligibility entirely.
    culled = [s for s in _panel() if s.symbol not in set(incumbents[:5])]
    second = build_snapshot(equities_only=False, rebalance_date="2020-07-01", panel=culled, incumbents=incumbents
    )
    assert second.status == "ok"
    snap = second.value
    assert set(snap.leavers) == set(incumbents[:5])
    assert len(snap.entrants) == len(snap.leavers)
    assert snap.churn_fraction == pytest.approx(len(snap.entrants) / len(snap.members))
    assert set(snap.entrants).isdisjoint(incumbents)


def test_ct2_negative_empty_panel_is_an_error():
    res = build_snapshot(equities_only=False, rebalance_date="2020-01-01", panel=[])
    assert res.status == "error"
    assert res.error.kind == "INSUFFICIENT_HISTORY"


def test_ct2_etfs_are_excluded_from_an_equity_universe():
    """FR52 selects NSE *equities*. ETFs rank high on traded value and index
    ETFs are linear combinations of other members, so leaving them in injects
    mechanical correlation into C_t and inflates the very eigenvalue the RMT
    pillar measures. Classification is by ISIN prefix (INE = equity)."""
    from seraph.universe import is_equity

    assert is_equity("RELIANCE") and is_equity("TATASTEEL")
    for etf in ("GOLDBEES", "NIFTYBEES", "LIQUIDBEES", "SILVERBEES", "BANKBEES"):
        assert not is_equity(etf), f"{etf} is a fund unit, not an equity"

    panel = [
        SymbolStats("RELIANCE", 5000, 9e9),
        SymbolStats("NIFTYBEES", 5000, 8e9),   # would outrank most equities
        SymbolStats("LIQUIDBEES", 5000, 7e9),
        SymbolStats("TATASTEEL", 5000, 6e9),
    ]
    res = build_snapshot(rebalance_date="2020-01-01", panel=panel, target=4)
    assert res.status == "ok"
    assert set(res.value.members) == {"RELIANCE", "TATASTEEL"}
    assert res.value.eligible_count == 2
