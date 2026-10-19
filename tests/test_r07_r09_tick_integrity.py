# Regression tests — R07a, R07b/X03, R09 (live feed and bar integrity)
"""Counterexamples from the 2026-10-18 completion audit and its verification.

Every test here failed before the repair in the same commit. They are named
for the defect, not the function, so a future reader can trace a failure back
to the finding that justified the code.

Sources:
* R07a/R07b — `docs/SERAPH-ENGINEERING-COMPLETION-AUDIT-2026-10-18.md`
* X03       — `docs/SERAPH-COMPLETION-AUDIT-VERIFICATION-2026-10-18.md` Part 3
* R09       — audit probe `docs/evidence/engineering-audit-2026-10-18/application.json`
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest

from seraph.live.bars import SNAPSHOT_VERSION, BarBuilder
from seraph.live.feed import (
    KiteTickerFeed,
    NullFeed,
    ReplayFeed,
    Tick,
    resolve_feed,
)

IST = "+05:30"
SESSION = "2026-10-16"


def tick(price=100.0, *, second=1, volume=None, sequence=None, symbol="RELIANCE"):
    return Tick(symbol=symbol, ts=f"{SESSION}T10:00:{second:02d}{IST}",
                last_price=price, volume_traded=volume, sequence=sequence)


# --------------------------------------------------------------- R07a: Tick


class TestR07aNonfinitePricesCannotReachOhlc:
    """`last_price <= 0` was the only guard, and NaN fails every comparison."""

    @pytest.mark.parametrize("price", [float("nan"), float("inf"), float("-inf")])
    def test_a_nonfinite_price_is_not_a_quote(self, price):
        with pytest.raises(ValueError, match="finite"):
            tick(price)

    def test_the_old_guard_would_have_admitted_nan(self):
        # The precise reason the old check passed: this is False, not True.
        assert (float("nan") <= 0) is False
        assert (float("inf") <= 0) is False

    def test_a_nonfinite_price_never_enters_a_bar(self):
        builder = BarBuilder()
        rejected, problem = Tick.accept(symbol="RELIANCE",
                                        ts=f"{SESSION}T10:00:01{IST}",
                                        last_price=float("nan"))
        assert rejected is None and "finite" in problem
        builder.add([tick(100.0)])
        (bar,) = builder.partial()
        assert bar.high == 100.0 and bar.low == 100.0

    @pytest.mark.parametrize("price", [0.0, -1.0])
    def test_a_non_positive_price_is_still_rejected(self, price):
        with pytest.raises(ValueError):
            tick(price)


class TestR07aVolumeAndIdentityValidation:
    def test_a_negative_cumulative_volume_is_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            tick(volume=-5)

    def test_a_fractional_volume_is_rejected(self):
        with pytest.raises(ValueError, match="fractional"):
            tick(volume=1.5)

    def test_a_nonfinite_volume_is_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            tick(volume=float("nan"))

    def test_a_tick_with_no_symbol_cannot_be_attributed(self):
        with pytest.raises(ValueError, match="no symbol"):
            tick(symbol="  ")

    def test_a_naive_timestamp_cannot_be_placed_in_a_session(self):
        with pytest.raises(ValueError, match="offset"):
            Tick(symbol="RELIANCE", ts=f"{SESSION}T10:00:01", last_price=100.0)

    def test_a_non_iso_timestamp_is_rejected(self):
        with pytest.raises(ValueError, match="ISO-8601"):
            Tick(symbol="RELIANCE", ts="16/10/2026 10:00", last_price=100.0)

    def test_a_negative_provider_sequence_is_rejected(self):
        with pytest.raises(ValueError, match="sequence"):
            tick(sequence=-1)

    def test_volume_may_legitimately_be_absent(self):
        assert tick(volume=None).volume_traded is None

    def test_accept_returns_a_reason_instead_of_raising(self):
        built, problem = Tick.accept(symbol="X", ts=f"{SESSION}T10:00:01{IST}",
                                     last_price=float("inf"))
        assert built is None
        assert "finite" in problem

    def test_accept_returns_the_tick_when_it_is_valid(self):
        built, problem = Tick.accept(symbol="X", ts=f"{SESSION}T10:00:01{IST}",
                                     last_price=100.0)
        assert problem is None and built.last_price == 100.0


# ------------------------------------------------- R07b / X03: ordering


class TestX03NoneVolumeDoesNotCrashTheBatch:
    """The reproduced crash. `_order_key` put `volume_traded` in an ordered
    tuple, so `None < int` raised TypeError out of `add()`."""

    def test_same_timestamp_and_price_with_and_without_volume(self):
        builder = BarBuilder()
        builder.add([tick(100.0, volume=5)])
        builder.add([tick(100.0, volume=None)])          # used to raise
        assert builder.accepted_ticks == 2

    def test_both_orderings_are_safe(self):
        builder = BarBuilder()
        builder.add([tick(100.0, volume=None), tick(100.0, volume=5)])
        assert builder.accepted_ticks == 2

    def test_a_malformed_tick_does_not_discard_its_neighbours(self):
        """The real damage: the exception escaped the per-tick loop, so every
        remaining tick in the batch was lost, not just the offending one."""
        builder = BarBuilder()
        builder.add([
            tick(100.0, second=1, volume=5),
            tick(101.0, second=1, volume=None),
            tick(102.0, second=2, volume=10),
            tick(103.0, second=3, volume=15),
        ])
        assert builder.accepted_ticks == 4
        (bar,) = builder.partial()
        assert bar.close == 103.0, "ticks after the None-volume tick were lost"


class TestR07bOrderingIsSymmetricInPrice:
    """Price was the tie-breaker, so a same-second down-tick was discarded
    while an up-tick was kept."""

    def test_a_same_second_down_tick_is_accepted(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=1), tick(99.0, second=1)])
        assert builder.accepted_ticks == 2
        assert not [q for q in builder.quarantined if q["reason"] == "out_of_order"]
        (bar,) = builder.partial()
        assert bar.low == 99.0 and bar.close == 99.0

    def test_a_same_second_up_tick_is_accepted(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=1), tick(101.0, second=1)])
        assert builder.accepted_ticks == 2
        (bar,) = builder.partial()
        assert bar.high == 101.0

    def test_rising_and_falling_are_treated_identically(self):
        rising, falling = BarBuilder(), BarBuilder()
        rising.add([tick(100.0, second=1), tick(101.0, second=1)])
        falling.add([tick(100.0, second=1), tick(99.0, second=1)])
        assert rising.accepted_ticks == falling.accepted_ticks == 2
        assert rising.describe()["quarantined"] == falling.describe()["quarantined"] == 0

    def test_a_down_tick_no_longer_poisons_the_bar_volume(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=1, volume=10),
                     tick(99.0, second=1, volume=20),
                     tick(99.5, second=2, volume=30)])
        (bar,) = builder.partial()
        assert bar.volume_quality != "uncertain"


class TestOrderingStillRejectsGenuineLateness:
    def test_an_earlier_timestamp_is_out_of_order(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=5)])
        builder.add([tick(100.5, second=2)])
        assert [q["reason"] for q in builder.quarantined] == ["out_of_order"]
        assert builder.accepted_ticks == 1

    def test_a_regressing_provider_sequence_is_out_of_order(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=1, sequence=10)])
        builder.add([tick(100.5, second=2, sequence=4)])
        assert [q["reason"] for q in builder.quarantined] == ["out_of_order"]

    def test_an_advancing_provider_sequence_is_accepted(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=1, sequence=4),
                     tick(100.5, second=1, sequence=10)])
        assert builder.accepted_ticks == 2

    def test_a_sequence_is_never_compared_against_a_missing_one(self):
        """Mixing a provider sequence with an absent one must not order
        anything: that comparison is what crashed."""
        builder = BarBuilder()
        builder.add([tick(100.0, second=1, sequence=10)])
        builder.add([tick(100.5, second=1, sequence=None)])
        assert builder.accepted_ticks == 2

    def test_an_exact_duplicate_is_still_a_duplicate(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=1, volume=5)])
        builder.add([tick(100.0, second=1, volume=5)])
        assert [q["reason"] for q in builder.quarantined] == ["duplicate"]
        assert builder.accepted_ticks == 1

    def test_two_none_volume_ticks_at_one_price_are_duplicates(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=1, volume=None),
                     tick(100.0, second=1, volume=None)])
        assert builder.accepted_ticks == 1


# --------------------------------------------- R08 (bars half): snapshot


class TestR08SnapshotCarriesOrderingAndDedupState:
    def test_the_snapshot_records_the_order_watermark(self):
        builder = BarBuilder()
        builder.add([tick(100.0, second=3, volume=5, sequence=7)])
        payload = builder.snapshot()["symbols"]["RELIANCE"]
        assert payload["last_ts"] == f"{SESSION}T10:00:03{IST}"
        assert payload["last_sequence"] == 7
        assert payload["seen_keys"], "the duplicate set was not persisted"

    def test_a_duplicate_is_still_detected_after_restore(self):
        """Version 1 resumed with an empty dedup set, so a redelivered batch
        was re-applied: the open bar double-counted its volume."""
        first = BarBuilder()
        first.add([tick(100.0, second=1, volume=10),
                   tick(101.0, second=2, volume=30)])
        resumed = BarBuilder()
        resumed.restore(first.snapshot())
        before = resumed.accepted_ticks          # carried over from the snapshot
        resumed.add([tick(100.0, second=1, volume=10),
                     tick(101.0, second=2, volume=30)])
        assert resumed.accepted_ticks - before == 0, "the redelivered batch was re-applied"
        assert {q["reason"] for q in resumed.quarantined} == {"duplicate"}
        assert len(resumed.quarantined) == 2

    def test_restore_reproduces_the_open_bar_exactly(self):
        first = BarBuilder()
        first.add([tick(100.0, second=1, volume=10),
                   tick(102.0, second=2, volume=30)])
        resumed = BarBuilder()
        resumed.restore(first.snapshot())
        assert [b.describe() for b in resumed.partial()] == \
               [b.describe() for b in first.partial()]

    def test_an_out_of_order_tick_is_still_rejected_after_restore(self):
        first = BarBuilder()
        first.add([tick(100.0, second=5)])
        resumed = BarBuilder()
        resumed.restore(first.snapshot())
        resumed.add([tick(100.5, second=2)])
        assert [q["reason"] for q in resumed.quarantined] == ["out_of_order"]

    def test_a_version_1_snapshot_is_refused_rather_than_misread(self):
        first = BarBuilder()
        first.add([tick(100.0, second=1)])
        stale = dict(first.snapshot(), version=1)
        with pytest.raises(ValueError, match="version"):
            BarBuilder().restore(stale)

    def test_the_snapshot_is_json_round_trippable(self):
        import json
        first = BarBuilder()
        first.add([tick(100.0, second=1, volume=10, sequence=3)])
        resumed = BarBuilder()
        resumed.restore(json.loads(json.dumps(first.snapshot())))
        before = resumed.accepted_ticks
        resumed.add([tick(100.0, second=1, volume=10, sequence=3)])
        assert resumed.accepted_ticks - before == 0
        assert [q["reason"] for q in resumed.quarantined] == ["duplicate"]

    def test_the_snapshot_is_stable_for_an_identical_state(self):
        """R05 hashes this payload: an arbitrary set order would make an
        unchanged state look changed and force a needless rebuild."""
        import json
        ticks = [tick(100.0, second=1, volume=10),
                 tick(101.0, second=2, volume=20),
                 tick(99.0, second=2, volume=30)]
        one, two = BarBuilder(), BarBuilder()
        one.add(list(ticks))
        two.add(list(ticks))
        assert json.dumps(one.snapshot(), sort_keys=True) == \
               json.dumps(two.snapshot(), sort_keys=True)

    def test_the_dedup_set_is_bounded_by_the_open_window(self):
        """Unbounded growth is why this could not be persisted before."""
        builder = BarBuilder()
        for second in range(1, 40):
            builder.add([tick(100.0 + second, second=second, volume=second)])
        builder.close_elapsed(at=datetime.fromisoformat(f"{SESSION}T11:00:00{IST}"))
        assert builder.snapshot()["symbols"]["RELIANCE"]["seen_keys"] == []

    def test_the_version_constant_is_what_snapshot_writes(self):
        assert BarBuilder().snapshot()["version"] == SNAPSHOT_VERSION


# ------------------------------------------------------------------ R09


class TestR09ExplicitReplayBeatsCredentials:
    """Audit probe: explicit replay with credentials present selected
    `KiteTickerFeed`, `is_live=true`. `--replay` must never open a socket."""

    def test_replay_wins_when_credentials_are_present(self, monkeypatch):
        monkeypatch.setenv("KITE_API_KEY", "a-real-looking-key")
        replay = ReplayFeed([], label="explicit replay")
        assert resolve_feed(allow_replay=replay) is replay

    def test_the_selected_feed_is_not_live(self, monkeypatch):
        monkeypatch.setenv("KITE_API_KEY", "a-real-looking-key")
        chosen = resolve_feed(allow_replay=ReplayFeed([], label="explicit"))
        assert chosen.is_live is False
        assert chosen.source_kind == "replay"
        assert chosen.health().is_live is False

    def test_no_broker_adapter_is_constructed_for_a_replay(self, monkeypatch):
        monkeypatch.setenv("KITE_API_KEY", "a-real-looking-key")

        def refuse(*_a, **_k):                     # pragma: no cover - must not run
            raise AssertionError("a replay must not construct a broker feed")

        monkeypatch.setattr("seraph.live.feed.KiteTickerFeed", refuse)
        assert resolve_feed(allow_replay=ReplayFeed([])).source_kind == "replay"

    def test_live_is_still_selected_when_no_replay_is_offered(self, monkeypatch):
        monkeypatch.setenv("KITE_API_KEY", "a-real-looking-key")
        assert isinstance(resolve_feed(), KiteTickerFeed)

    def test_without_credentials_or_replay_the_answer_is_honest(self, monkeypatch):
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        chosen = resolve_feed()
        assert isinstance(chosen, NullFeed)
        assert "never substituted" in chosen.health().detail

    def test_there_is_no_silent_fallback_from_live_to_archived(self, monkeypatch):
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        assert not isinstance(resolve_feed(), ReplayFeed)


class TestKiteAdapterNeverRaisesIntoTheSocketThread:
    def test_a_rejected_packet_is_counted_and_named(self):
        feed = KiteTickerFeed(api_key="k")
        feed._reject("price nan is not finite")
        feed._reject("price nan is not finite")
        assert feed.rejected == {"price nan is not finite": 2}
        assert "2x price nan is not finite" in feed.health().detail

    def test_a_clean_adapter_reports_no_rejects(self):
        assert "rejected" not in KiteTickerFeed(api_key="k").health().detail
