"""T05 — the basket a Hawkes window declares must be the basket it counted (R11).

The audit found that `write_hawkes_production.py` resolved the universe once at
the corpus end, pooled one stream from it, and sliced that stream for every
window — while separately resolving a point-in-time basket per window and
writing *that* into the artefact. The metadata described a membership which had
not produced the numbers next to it.

These tests use a changing-membership fixture with four symbols:

* ``CORE1``–``CORE3`` are members throughout,
* ``EXITER`` is a member of the early basket only,
* ``ENTRANT`` is a member of the late basket only,

and every one of them has bars across the whole grid, so a difference in the
pooled counts can only come from the member set, never from missing data. That
is the shape terminal-basket selection gets wrong in both directions at once.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from seraph.ingestion.hawkes_universe import BasketSnapshot, BasketTimeline
from seraph.pillars.hawkes.basket_stream import (
    DETECTOR_VERSION,
    MEMBERSHIP_POLICIES,
    PooledStream,
    event_hash_of,
    membership_segments,
    verify_manifest,
)

IST = timezone(timedelta(hours=5, minutes=30))
BARS_PER_SESSION = 75
SESSIONS = 12
FIRST_SESSION = datetime(2024, 1, 1, 9, 15, tzinfo=IST)


def grid() -> list:
    """`SESSIONS` consecutive days of `BARS_PER_SESSION` five-minute bars."""
    out = []
    for d in range(SESSIONS):
        day = FIRST_SESSION + timedelta(days=d)
        out.extend(day + timedelta(minutes=5 * b) for b in range(BARS_PER_SESSION))
    return out


def prices(seed: int, jump_bars: "dict[int, float]") -> np.ndarray:
    """A quiet random walk with large signed returns at the named bar indices."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, 2e-4, SESSIONS * BARS_PER_SESSION)
    for i, size in jump_bars.items():
        r[i] = size
    return 100.0 * np.exp(np.cumsum(r))


#: Bars well past the k=156 bipower warm-up, so a jump there can be flagged.
EXITER_JUMPS = {200: -0.05, 260: -0.05, 330: -0.05}
ENTRANT_JUMPS = {210: -0.05, 270: -0.05, 340: -0.05}


@pytest.fixture
def stream() -> PooledStream:
    bars = grid()
    rows = [
        ("CORE1", bars, prices(1, {205: -0.05, 400: -0.05})),
        ("CORE2", bars, prices(2, {215: -0.05, 410: -0.05})),
        ("CORE3", bars, prices(3, {225: -0.05, 420: 0.05})),
        ("EXITER", bars, prices(4, EXITER_JUMPS)),
        ("ENTRANT", bars, prices(5, ENTRANT_JUMPS)),
    ]
    return PooledStream.build(rows)


@pytest.fixture
def timeline() -> BasketTimeline:
    """EXITER leaves and ENTRANT arrives at the 2024-01-07 rebalance."""
    return BasketTimeline([
        BasketSnapshot("2024-01-01", ("CORE1", "CORE2", "CORE3", "EXITER"), 4),
        BasketSnapshot("2024-01-07", ("CORE1", "CORE2", "CORE3", "ENTRANT"), 4),
    ])


EARLY = (0, 5 * BARS_PER_SESSION - 1)        # 2024-01-01 .. 2024-01-05
LATE = (7 * BARS_PER_SESSION, SESSIONS * BARS_PER_SESSION - 1)


def pooled(stream, lo, hi, members, policy="fixed_at_fit_cutoff"):
    return stream.window(lo, hi, segments=[(lo, hi, tuple(members))],
                         policy=policy, declared=members, basket_id="t",
                         basket_basis="point_in_time", rebalance_date="2024-01-01")


# ------------------------------------------- the defect, both directions


def test_the_fixture_actually_produces_jumps(stream):
    """Guard the fixture: a test about counting events needs events."""
    assert stream.series["EXITER"].neg_index.size >= 3
    assert stream.series["ENTRANT"].neg_index.size >= 3
    assert stream.quality.symbols_used == 5


def test_an_exiting_symbol_keeps_its_events_in_the_windows_it_belonged_to(
        stream, timeline):
    """The survivorship direction: terminal-basket selection erases EXITER.

    Isolated by differencing against the three cores, so the claim is about
    EXITER's own events and not about any coincidence of totals — EXITER and
    ENTRANT happen to carry three jumps each, which is exactly how a wrong
    basket can leave an aggregate looking untouched.
    """
    lo, hi = EARLY
    correct, manifest = pooled(stream, lo, hi, timeline.members_at("2024-01-05"))
    terminal, _ = pooled(stream, lo, hi, timeline.members_at("2024-01-12"))
    cores, _ = pooled(stream, lo, hi, ["CORE1", "CORE2", "CORE3"])

    assert "EXITER" in timeline.members_at("2024-01-05")
    assert "EXITER" not in timeline.members_at("2024-01-12")

    bars = [i for i in stream.series["EXITER"].neg_index if lo <= i <= hi]
    assert bars, "the fixture must put EXITER events in this window"

    attributable = correct["n_neg"] - cores["n_neg"]
    assert attributable.sum() == len(bars)
    for i in bars:
        assert attributable[i - lo] >= 1, (
            "EXITER was a member on this bar, so its event belongs in the count")
        assert terminal["n_neg"][i - lo] == cores["n_neg"][i - lo], (
            "under terminal-basket selection EXITER's event is simply gone")
    assert "EXITER" not in manifest.members_without_data


def test_a_late_entrant_is_not_counted_before_it_joined(stream, timeline):
    """The composition direction, which is the large one in the real corpus."""
    lo, hi = EARLY
    correct, manifest = pooled(stream, lo, hi, timeline.members_at("2024-01-05"))
    terminal, terminal_manifest = pooled(
        stream, lo, hi, timeline.members_at("2024-01-12"))
    cores, _ = pooled(stream, lo, hi, ["CORE1", "CORE2", "CORE3"])

    assert stream.series["ENTRANT"].bars_in(lo, hi) > 0, (
        "ENTRANT has data here; only membership excludes it")
    bars = [i for i in stream.series["ENTRANT"].neg_index if lo <= i <= hi]
    assert bars

    for i in bars:
        assert terminal["n_neg"][i - lo] > cores["n_neg"][i - lo], (
            "the terminal basket counts ENTRANT in a window it had not joined")
        assert correct["n_neg"][i - lo] == cores["n_neg"][i - lo], (
            "per-window selection leaves it out, which is the correction")
    assert "ENTRANT" not in timeline.members_at("2024-01-05")
    assert "ENTRANT" not in terminal_manifest.members_without_data


def test_the_two_errors_do_not_cancel(stream, timeline):
    """One in, one out is not the same stream — events land on different bars."""
    lo, hi = EARLY
    correct, _ = pooled(stream, lo, hi, timeline.members_at("2024-01-05"))
    terminal, _ = pooled(stream, lo, hi, timeline.members_at("2024-01-12"))
    assert not np.array_equal(correct["n_neg"], terminal["n_neg"])


# ------------------------------------------- the manifest describes the input


def test_the_manifest_describes_the_counts_it_was_built_with(stream, timeline):
    lo, hi = EARLY
    inputs, manifest = pooled(stream, lo, hi, timeline.members_at("2024-01-05"))
    assert verify_manifest(manifest, n_neg=inputs["n_neg"],
                           n_pos=inputs["n_pos"], active=inputs["active"]) == []


def test_the_manifest_refuses_counts_from_a_different_basket(stream, timeline):
    """This is the R11 guard in the writer, exercised directly."""
    lo, hi = EARLY
    _, manifest = pooled(stream, lo, hi, timeline.members_at("2024-01-05"))
    other, _ = pooled(stream, lo, hi, timeline.members_at("2024-01-12"))
    problems = verify_manifest(manifest, n_neg=other["n_neg"],
                               n_pos=other["n_pos"], active=other["active"])
    assert problems, "a manifest from another basket must not validate"
    assert any("event hash disagrees" in p for p in problems)


def test_the_manifest_names_declared_members_without_data(stream):
    _, manifest = pooled(stream, *EARLY, ["CORE1", "GHOST"])
    assert manifest.members_declared == 2
    assert manifest.members_contributing == 1
    assert manifest.members_without_data == ("GHOST",)
    assert manifest.coverage == pytest.approx(0.5)


def test_coverage_is_reported_not_silently_tolerated(stream):
    _, manifest = pooled(stream, *EARLY, ["CORE1", "CORE2", "G1", "G2"])
    described = manifest.describe()
    assert described["membership"]["coverage"] == pytest.approx(0.5)
    assert described["membership"]["without_data"] == ["G1", "G2"]


def test_the_manifest_records_the_detector_version(stream):
    _, manifest = pooled(stream, *EARLY, ["CORE1"])
    assert manifest.detector_version == DETECTOR_VERSION
    assert "lee_mykland" in manifest.detector_version
    assert "k=156" in manifest.detector_version


def test_window_bounds_are_dates_from_the_data(stream):
    lo, hi = EARLY
    _, manifest = pooled(stream, lo, hi, ["CORE1"])
    assert manifest.training_start == "2024-01-01"
    assert manifest.as_of == "2024-01-05"
    assert manifest.n_sessions == 5
    assert manifest.n_bars == 5 * BARS_PER_SESSION


# ------------------------------------------- the content hash is a content hash


def test_the_input_hash_changes_when_a_price_inside_the_window_changes():
    bars = grid()
    base = prices(7, {200: -0.05})
    moved = base.copy()
    moved[100] *= 1.01                       # inside the early window
    a = PooledStream.build([("CORE1", bars, base)])
    b = PooledStream.build([("CORE1", bars, moved)])
    _, ma = pooled(a, *EARLY, ["CORE1"])
    _, mb = pooled(b, *EARLY, ["CORE1"])
    assert ma.input_row_hash != mb.input_row_hash


def test_the_input_hash_is_unmoved_by_a_price_outside_the_window():
    """Over-invalidation would make the hash useless for comparing windows."""
    bars = grid()
    base = prices(7, {200: -0.05})
    moved = base.copy()
    moved[-1] *= 1.01                        # last session, outside EARLY
    a = PooledStream.build([("CORE1", bars, base)])
    b = PooledStream.build([("CORE1", bars, moved)])
    _, ma = pooled(a, *EARLY, ["CORE1"])
    _, mb = pooled(b, *EARLY, ["CORE1"])
    assert ma.input_row_hash == mb.input_row_hash


def test_the_input_hash_distinguishes_the_member_set(stream):
    _, one = pooled(stream, *EARLY, ["CORE1", "CORE2"])
    _, two = pooled(stream, *EARLY, ["CORE1", "CORE3"])
    assert one.input_row_hash != two.input_row_hash


def test_the_input_hash_distinguishes_the_policy(stream, timeline):
    lo, hi = LATE
    cutoff = membership_segments(stream, lo, hi, policy="fixed_at_fit_cutoff",
                                 resolve=timeline.members_at)
    start = membership_segments(stream, lo, hi, policy="fixed_at_window_start",
                                resolve=timeline.members_at)
    _, a = stream.window(lo, hi, segments=cutoff, policy="fixed_at_fit_cutoff",
                         declared=cutoff[0][2], basket_id="x",
                         basket_basis="point_in_time", rebalance_date=None)
    _, b = stream.window(lo, hi, segments=start, policy="fixed_at_window_start",
                         declared=start[0][2], basket_id="x",
                         basket_basis="point_in_time", rebalance_date=None)
    assert a.input_row_hash != b.input_row_hash


def test_an_identical_rerun_reproduces_both_hashes(stream, timeline):
    lo, hi = EARLY
    first = pooled(stream, lo, hi, timeline.members_at("2024-01-05"))[1]
    again = PooledStream.build([
        ("CORE1", grid(), prices(1, {205: -0.05, 400: -0.05})),
        ("CORE2", grid(), prices(2, {215: -0.05, 410: -0.05})),
        ("CORE3", grid(), prices(3, {225: -0.05, 420: 0.05})),
        ("EXITER", grid(), prices(4, EXITER_JUMPS)),
        ("ENTRANT", grid(), prices(5, ENTRANT_JUMPS)),
    ])
    second = pooled(again, lo, hi, timeline.members_at("2024-01-05"))[1]
    assert first.input_row_hash == second.input_row_hash
    assert first.event_hash == second.event_hash


# ------------------------------------------- membership policies


def test_the_three_policies_are_named_and_distinguished():
    assert MEMBERSHIP_POLICIES == ("fixed_at_fit_cutoff",
                                   "fixed_at_window_start", "day_varying")


def test_an_unknown_policy_is_refused(stream, timeline):
    with pytest.raises(ValueError, match="unknown membership policy"):
        membership_segments(stream, *EARLY, policy="whatever_was_handy",
                            resolve=timeline.members_at)


def test_fit_cutoff_and_window_start_disagree_across_a_rebalance(stream, timeline):
    """A window straddling 2024-01-07 is exactly where the choice matters."""
    lo, hi = 4 * BARS_PER_SESSION, 9 * BARS_PER_SESSION - 1
    cutoff = membership_segments(stream, lo, hi, policy="fixed_at_fit_cutoff",
                                 resolve=timeline.members_at)
    start = membership_segments(stream, lo, hi, policy="fixed_at_window_start",
                                resolve=timeline.members_at)
    assert cutoff[0][2] != start[0][2]
    assert "ENTRANT" in cutoff[0][2] and "EXITER" in start[0][2]


def test_day_varying_splits_the_window_at_the_rebalance(stream, timeline):
    lo, hi = 4 * BARS_PER_SESSION, 9 * BARS_PER_SESSION - 1
    segments = membership_segments(stream, lo, hi, policy="day_varying",
                                   resolve=timeline.members_at)
    assert len(segments) == 2
    assert segments[0][2] == timeline.members_at("2024-01-05")
    assert segments[1][2] == timeline.members_at("2024-01-08")
    assert segments[0][1] + 1 == segments[1][0]


def test_day_varying_counts_each_symbol_only_while_it_was_a_member(
        stream, timeline):
    lo, hi = 4 * BARS_PER_SESSION, 9 * BARS_PER_SESSION - 1
    segments = membership_segments(stream, lo, hi, policy="day_varying",
                                   resolve=timeline.members_at)
    inputs, manifest = stream.window(
        lo, hi, segments=segments, policy="day_varying",
        declared=timeline.members_at("2024-01-09"), basket_id="x",
        basket_basis="fixed_research_basket", rebalance_date="2024-01-07")
    # Four members on every bar: three cores plus exactly one of the two
    # changing names, never both and never neither.
    assert set(np.unique(inputs["active"])) == {4.0}
    assert len(manifest.segments) == 2
    assert verify_manifest(manifest, n_neg=inputs["n_neg"],
                           n_pos=inputs["n_pos"], active=inputs["active"]) == []


def test_a_fixed_policy_yields_one_segment(stream, timeline):
    for policy in ("fixed_at_fit_cutoff", "fixed_at_window_start"):
        segments = membership_segments(stream, *EARLY, policy=policy,
                                       resolve=timeline.members_at)
        assert len(segments) == 1
        assert segments[0][:2] == EARLY


# ------------------------------------------- the window contract


def test_segments_must_tile_the_window(stream):
    lo, hi = EARLY
    with pytest.raises(ValueError, match="do not tile"):
        stream.window(lo, hi, segments=[(lo, hi - 10, ("CORE1",))],
                      policy="day_varying", declared=["CORE1"], basket_id="x",
                      basket_basis="point_in_time", rebalance_date=None)


def test_segments_must_not_leave_a_gap(stream):
    lo, hi = EARLY
    mid = (lo + hi) // 2
    with pytest.raises(ValueError, match="gap or overlap"):
        stream.window(lo, hi,
                      segments=[(lo, mid, ("CORE1",)), (mid + 2, hi, ("CORE1",))],
                      policy="day_varying", declared=["CORE1"], basket_id="x",
                      basket_basis="point_in_time", rebalance_date=None)


def test_an_empty_window_is_refused(stream):
    with pytest.raises(ValueError, match="empty window"):
        stream.window(50, 10, segments=[(50, 10, ("CORE1",))],
                      policy="fixed_at_fit_cutoff", declared=["CORE1"],
                      basket_id="x", basket_basis="point_in_time",
                      rebalance_date=None)


def test_pooling_is_additive_over_members(stream):
    """Pooling CORE1+CORE2 is pooling CORE1 plus pooling CORE2, exactly."""
    lo, hi = EARLY
    a, _ = pooled(stream, lo, hi, ["CORE1"])
    b, _ = pooled(stream, lo, hi, ["CORE2"])
    both, _ = pooled(stream, lo, hi, ["CORE1", "CORE2"])
    assert np.array_equal(a["n_neg"] + b["n_neg"], both["n_neg"])
    assert np.array_equal(a["active"] + b["active"], both["active"])


def test_a_member_with_no_series_contributes_nothing(stream):
    lo, hi = EARLY
    one, _ = pooled(stream, lo, hi, ["CORE1"])
    with_ghost, _ = pooled(stream, lo, hi, ["CORE1", "NOT_A_SYMBOL"])
    assert np.array_equal(one["active"], with_ghost["active"])


def test_non_positive_closes_are_dropped_and_counted():
    """A feed gap stored as zero has no log return; it is never patched."""
    bars = grid()
    p = prices(9, {200: -0.05})
    p[300:375] = 0.0                       # one whole session of zeros
    s = PooledStream.build([("CORE1", bars, p)])
    assert s.quality.bars_dropped_nonpositive == 75
    assert s.series["CORE1"].bars_kept == len(bars) - 75


def test_a_symbol_too_short_to_detect_a_jump_is_named_not_silently_dropped():
    bars = grid()[:100]
    s = PooledStream.build([("TINY", bars, prices(9, {})[:100])],
                           requested=["TINY"])
    assert s.quality.symbols_too_short == ("TINY",)
    assert s.quality.symbols_used == 0


def test_a_requested_symbol_with_no_rows_is_reported_absent():
    bars = grid()
    s = PooledStream.build([("CORE1", bars, prices(1, {200: -0.05}))],
                           requested=["CORE1", "DELISTED"])
    assert s.quality.symbols_absent == ("DELISTED",)


def test_a_symbol_with_zero_rows_is_absent_not_merely_short():
    """A coverage gap and a short series are different problems.

    221 of the 312 symbols that were ever universe members have no intraday
    bars in this corpus at all. Reporting those as "too short" would read as a
    detector limitation when it is the intraday backfill's scope.
    """
    s = PooledStream.build([("CORE1", grid(), prices(1, {200: -0.05})),
                            ("NEVER_PULLED", [], [])],
                           requested=["CORE1", "NEVER_PULLED"])
    assert s.quality.symbols_absent == ("NEVER_PULLED",)
    assert s.quality.symbols_too_short == ()


# ------------------------------------------- the basket timeline


def test_the_timeline_returns_the_snapshot_in_force(timeline):
    assert timeline.at("2024-01-06").rebalance_date == "2024-01-01"
    assert timeline.at("2024-01-07").rebalance_date == "2024-01-07"
    assert timeline.at("2024-01-08").rebalance_date == "2024-01-07"


def test_the_timeline_has_nothing_before_its_first_snapshot(timeline):
    assert timeline.at("2023-12-31") is None
    assert timeline.members_at("2023-12-31") == ()


def test_the_timeline_union_is_what_the_stream_must_load(timeline):
    assert set(timeline.union) == {"CORE1", "CORE2", "CORE3", "EXITER", "ENTRANT"}
    assert "EXITER" in timeline.describe()["never_in_terminal"]


def test_duplicate_rebalance_dates_are_refused():
    with pytest.raises(ValueError, match="share a rebalance date"):
        BasketTimeline([BasketSnapshot("2024-01-01", ("A",), 1),
                        BasketSnapshot("2024-01-01", ("B",), 1)])


def test_the_timeline_sorts_snapshots_given_out_of_order():
    t = BasketTimeline([BasketSnapshot("2024-06-01", ("B",), 1),
                        BasketSnapshot("2024-01-01", ("A",), 1)])
    assert [s.rebalance_date for s in t.snapshots] == ["2024-01-01", "2024-06-01"]
    assert t.members_at("2024-03-01") == ("A",)


def test_the_snapshot_digest_is_order_independent():
    a = BasketSnapshot("2024-01-01", ("A", "B"), 2)
    b = BasketSnapshot("2024-01-01", ("B", "A"), 2)
    assert a.digest == b.digest


# ------------------------------------------- hashing helper


def test_event_hash_separates_the_three_vectors():
    """Swapping neg and pos must not hash the same."""
    a = event_hash_of([1, 0], [0, 1], [2, 2])
    b = event_hash_of([0, 1], [1, 0], [2, 2])
    assert a != b
