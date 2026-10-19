"""T02 — bar finality and volume continuity (audit finding R03).

Two reproductions from the audit:

* `close_elapsed()` removed the accumulator but kept no watermark, so a late
  tick **recreated and re-emitted the same closed window**. The probe got the
  11:00–11:05 bar twice, first with close 100 then with close 999, while
  `late_ticks` stayed zero.
* Volume used the first and last cumulative totals *inside* each bar. With
  prior cumulative 150 and next-bar ticks 170 and 200 it reported 30 instead
  of the 50 traded since the boundary — the 20 units between the previous
  bar's last tick and this bar's first tick disappeared.

Plan §14.1 R03 requires: finalized windows cannot reopen with an empty
accumulator or after restart, plus volume boundary, duplicate and out-of-order
cases.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from seraph.live import BarBuilder, MarketClock, Tick
from seraph.shared_types import IST, ist_timestamp


def at(hour, minute, second=0, day=(2026, 10, 16)):
    return datetime(*day, hour, minute, second, tzinfo=IST)


def tick(symbol, when, price, volume=None):
    return Tick(symbol=symbol, ts=ist_timestamp(when), last_price=price,
                volume_traded=volume)


@pytest.fixture
def builder():
    return BarBuilder(MarketClock())


# ------------------------------------------------------ finality


def test_a_finalized_window_cannot_reopen(builder):
    """The audit's exact reproduction."""
    builder.add([tick("AUDIT", at(11, 0), 100)])
    first = builder.close_elapsed(at(11, 5))
    assert [b.close for b in first] == [100]

    second = builder.add([tick("AUDIT", at(11, 1), 999)])
    assert second == [], "the closed window must not be re-emitted"
    assert builder.late_ticks == 1
    assert builder.partial() == [], "and must not reopen as a partial bar"


def test_the_watermark_holds_with_no_accumulator_present(builder):
    """The old check only fired while a NEWER accumulator existed."""
    builder.add([tick("X", at(11, 0), 100)])
    builder.close_elapsed(at(11, 5))
    assert builder.watermark("X") == ist_timestamp(at(11, 5))
    assert builder.describe()["open_bars"] == 0
    assert builder.add([tick("X", at(11, 2), 500)]) == []
    assert builder.late_ticks == 1


def test_the_watermark_survives_a_restart(builder):
    builder.add([tick("X", at(11, 0), 100)])
    builder.close_elapsed(at(11, 5))

    revived = BarBuilder(MarketClock())
    revived.restore(builder.snapshot())
    assert revived.watermark("X") == ist_timestamp(at(11, 5))
    assert revived.add([tick("X", at(11, 2), 777)]) == []
    assert revived.late_ticks == 1


def test_an_open_accumulator_survives_a_restart(builder):
    builder.add([tick("X", at(11, 0), 100), tick("X", at(11, 2), 105)])
    revived = BarBuilder(MarketClock())
    revived.restore(builder.snapshot())
    closed = revived.close_elapsed(at(11, 5))
    assert len(closed) == 1
    assert (closed[0].open, closed[0].high, closed[0].close) == (100, 105, 105)


def test_an_unsupported_snapshot_version_is_refused(builder):
    with pytest.raises(ValueError, match="unsupported bar snapshot version"):
        builder.restore({"version": 99, "symbols": {}})


def test_a_later_window_still_closes_the_earlier_one(builder):
    builder.add([tick("X", at(11, 0), 100)])
    closed = builder.add([tick("X", at(11, 6), 110)])
    assert len(closed) == 1 and closed[0].end == ist_timestamp(at(11, 5))


# ------------------------------------------------------ volume


def test_volume_is_measured_across_the_boundary(builder):
    """The audit's 150 → 170, 200 case: the answer is 50, not 30."""
    builder.add([tick("V", at(11, 0), 100, 100),
                 tick("V", at(11, 3), 101, 150)])
    builder.close_elapsed(at(11, 5))
    builder.add([tick("V", at(11, 6), 102, 170),
                 tick("V", at(11, 8), 103, 200)])
    second = builder.close_elapsed(at(11, 10))
    assert second[0].volume == 50
    assert second[0].volume_quality == "exact"


def test_the_first_window_of_a_connection_cannot_claim_exact_volume(builder):
    """No baseline exists, so the opening interval is partial, not a guess."""
    builder.add([tick("V", at(11, 0), 100, 500_000),
                 tick("V", at(11, 2), 101, 512_000)])
    first = builder.close_elapsed(at(11, 5))
    assert first[0].volume is None
    assert first[0].volume_quality == "partial"


def test_a_cumulative_volume_that_falls_invalidates_rather_than_clamps(builder):
    builder.add([tick("V", at(11, 0), 100, 100), tick("V", at(11, 2), 101, 150)])
    builder.close_elapsed(at(11, 5))
    builder.add([tick("V", at(11, 6), 102, 170),
                 tick("V", at(11, 7), 103, 20)])          # provider reset
    closed = builder.close_elapsed(at(11, 10))
    assert closed[0].volume is None
    assert closed[0].volume_quality == "uncertain"
    assert any(q["reason"] == "volume_reset_or_revision"
               for q in builder.quarantined)


def test_absent_volume_is_unavailable_not_zero(builder):
    builder.add([tick("V", at(11, 0), 100), tick("V", at(11, 2), 101)])
    closed = builder.close_elapsed(at(11, 5))
    assert closed[0].volume is None
    assert closed[0].volume_quality in ("unavailable", "partial")


def test_a_new_session_resets_the_cumulative_baseline(builder):
    builder.add([tick("V", at(11, 0), 100, 900_000)])
    builder.close_elapsed(at(11, 5))
    # Next trading day: the exchange's cumulative counter restarts.
    builder.add([tick("V", at(11, 0, day=(2026, 10, 19)), 101, 1_000),
                 tick("V", at(11, 2, day=(2026, 10, 19)), 102, 4_000)])
    closed = builder.close_elapsed(at(11, 5, day=(2026, 10, 19)))
    assert closed[0].volume is None, \
        "a new session has no carried baseline; it does not subtract yesterday"
    assert closed[0].volume_quality == "partial"


def test_volume_accumulates_over_several_consecutive_bars(builder):
    builder.add([tick("V", at(11, 0), 100, 1_000)])
    builder.close_elapsed(at(11, 5))
    totals = []
    for index, (minute, cumulative) in enumerate(
            [(6, 1_500), (11, 2_200), (16, 2_900)]):
        builder.add([tick("V", at(11, minute), 100 + index, cumulative)])
        closed = builder.close_elapsed(at(11, minute + 5))
        if closed:
            totals.append(closed[0].volume)
    assert totals == [500, 700, 700]


# ------------------------------------------ duplicates and ordering


def test_an_identical_duplicate_tick_is_ignored(builder):
    original = tick("D", at(11, 0), 100, 50)
    builder.add([original])
    before = builder.accepted_ticks
    builder.add([tick("D", at(11, 0), 100, 50)])
    assert builder.accepted_ticks == before
    assert any(q["reason"] == "duplicate" for q in builder.quarantined)


def test_an_out_of_order_tick_is_quarantined_and_marks_volume_uncertain(builder):
    builder.add([tick("O", at(11, 0), 100, 10), tick("O", at(11, 3), 102, 40)])
    builder.add([tick("O", at(11, 1), 101, 25)])
    assert any(q["reason"] == "out_of_order" for q in builder.quarantined)
    assert builder.partial()[0].volume_quality == "uncertain"


def test_a_tick_exactly_on_the_boundary_belongs_to_the_next_window(builder):
    """Windows are half-open [start, end)."""
    builder.add([tick("B", at(11, 0), 100)])
    closed = builder.add([tick("B", at(11, 5), 200)])
    assert len(closed) == 1 and closed[0].close == 100
    assert builder.partial()[0].start == ist_timestamp(at(11, 5))


def test_a_tick_outside_any_session_is_quarantined(builder):
    builder.add([tick("X", at(11, 0, day=(2026, 10, 17)), 100)])   # Saturday
    assert builder.out_of_session_ticks == 1
    assert builder.partial() == []


# ------------------------------------------------- reporting


def test_quarantine_reasons_are_counted_for_operations(builder):
    builder.add([tick("X", at(11, 0), 100)])
    builder.close_elapsed(at(11, 5))
    builder.add([tick("X", at(11, 1), 999),
                 tick("X", at(11, 0, day=(2026, 10, 17)), 50)])
    described = builder.describe()
    assert described["quarantine_reasons"]["late_finalized"] == 1
    assert described["quarantine_reasons"]["outside_session"] == 1
    assert "cannot reopen" in described["note"]


def test_several_symbols_keep_independent_state(builder):
    builder.add([tick("A", at(11, 0), 100), tick("B", at(11, 0), 200)])
    builder.close_elapsed(at(11, 5))
    assert builder.watermark("A") == builder.watermark("B")
    builder.add([tick("A", at(11, 6), 110)])
    assert builder.describe()["open_bars"] == 1
