# T03 — real pillar producers feeding the live decision path (audit R01)
"""`NullProducers` was hardwired into `run_live.build`, so every pillar
reported a structural absence, no CSRS was ever produced, and the publication
gate correctly refused to call anything current. That was an honest
description of a runtime with no producer attached.

These tests cover the producer that replaces it: `DailyVintageProducer` reads
the vintages `scripts/run_daily.py` persists (migration 003) and hands them to
`InferenceService` through the same `Producers` protocol `StaticProducers`
uses. Nothing is invented -- every vintage traces to a stored row.

The `origin` column is the load-bearing part and has its own tests. A number
computed by this installation and a number read from a prior research
artefact are both real, and they are not the same claim: Hawkes cannot be
computed here at all (its fresh estimate needs 5-minute intraday bars, and
`intraday_bars` is empty pending a Kite subscription), so an archived Hawkes
value shown as a current reading would be exactly the substitution this
project's mode discipline exists to prevent.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_args

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from seraph.live.engine_adapter import (                       # noqa: E402
    DECISION_ALLOWANCE,
    DailyVintageProducer,
    NullProducers,
    attach,
)
from seraph.live.inference import ORDER, InferenceService, Vintage  # noqa: E402
from seraph.live.store import LiveStore, StoreError            # noqa: E402
from seraph.shared_types.pillars import UnavailableEmission     # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
SESSIONS = [f"2026-08-{d:02d}" for d in range(3, 25)]

#: `UnavailableEmission.reason` is a closed Literal of exactly three values,
#: and a `Vintage`'s `absence_reason` flows into it. Read from the model
#: rather than retyped, so widening the Literal cannot leave this test
#: asserting a stale set.
PERMITTED_ABSENCE_REASONS = set(get_args(
    UnavailableEmission.model_fields["reason"].annotation))


def at(day: str, hour: int, minute: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+05:30")


@pytest.fixture
def store(tmp_path):
    return LiveStore(tmp_path / "runtime.sqlite")


def seed(store, *, day="2026-08-20", rmt=0.42, hamilton=0.31,
         hawkes_origin="archived", hawkes=0.051):
    """One day's vintages, as `run_daily.py` writes them."""
    close = at(day, 15, 30)
    available = (close + timedelta(minutes=30)).isoformat()
    store.record_daily_vintage(
        producer="rmt", input_end=close.isoformat(),
        emission_available_at=available, origin="computed", value=rmt,
        bundle_id="original rmt")
    store.record_daily_vintage(
        producer="hamilton", input_end=close.isoformat(),
        emission_available_at=available, origin="computed", value=hamilton,
        bundle_id="original hamilton")
    if hawkes_origin == "archived":
        store.record_daily_vintage(
            producer="hawkes", input_end=close.isoformat(),
            emission_available_at=available, origin="archived", value=hawkes,
            bundle_id="original hawkes (research snapshot)")
    else:
        store.record_daily_vintage(
            producer="hawkes", input_end=close.isoformat(),
            emission_available_at=available, origin="absent",
            # One of UnavailableEmission's three permitted reasons; the
            # specific cause (no intraday bars) lives in the detail, not here.
            absence="structural", absence_reason="no_data_coverage",
            bundle_id="original hawkes",
            detail=dict(reason="no 5-minute intraday bars; needs Kite"))
    return close


# ------------------------------------------------------- the store layer


class TestDailyVintagePersistence:
    def test_a_vintage_round_trips(self, store):
        seed(store)
        rows = {r["producer"]: r for r in
                store.daily_vintages(as_of=at("2026-08-21", 9, 0).isoformat())}
        assert set(rows) == set(ORDER)
        assert rows["rmt"]["value"] == 0.42
        assert rows["rmt"]["origin"] == "computed"
        assert rows["hawkes"]["origin"] == "archived"

    def test_writing_the_same_vintage_twice_stores_once(self, store):
        close = seed(store)
        again = store.record_daily_vintage(
            producer="rmt", input_end=close.isoformat(),
            emission_available_at=(close + timedelta(minutes=30)).isoformat(),
            origin="computed", value=0.42, bundle_id="original rmt")
        assert again["stored"] is False, "the daily job is not idempotent"

    def test_a_vintage_cannot_be_edited_in_place(self, store):
        """It is a record of what an estimator said; a revision is a new row."""
        import sqlite3
        seed(store)
        with pytest.raises(sqlite3.IntegrityError, match="record of what"):
            with store.connect() as db:
                db.execute("UPDATE daily_vintages SET value=0.99")

    def test_a_valueless_vintage_must_declare_its_absence(self, store):
        with pytest.raises(StoreError, match="never inferred"):
            store.record_daily_vintage(
                producer="rmt", input_end="2026-08-20T15:30:00+05:30",
                emission_available_at="2026-08-20T16:00:00+05:30",
                origin="absent")

    def test_an_unknown_origin_is_refused(self, store):
        with pytest.raises(StoreError, match="unknown vintage origin"):
            store.record_daily_vintage(
                producer="rmt", input_end="2026-08-20T15:30:00+05:30",
                emission_available_at="2026-08-20T16:00:00+05:30",
                origin="live", value=0.4)

    def test_a_nonfinite_value_is_refused(self, store):
        with pytest.raises(StoreError, match="non-finite"):
            store.record_daily_vintage(
                producer="rmt", input_end="2026-08-20T15:30:00+05:30",
                emission_available_at="2026-08-20T16:00:00+05:30",
                origin="computed", value=float("nan"))

    def test_a_vintage_not_yet_readable_is_not_returned(self, store):
        """The store applies the same availability rule the service does, so
        a producer cannot hand over a vintage the service would withhold."""
        seed(store)
        early = store.daily_vintages(as_of=at("2026-08-20", 15, 31).isoformat())
        assert early == [], "a vintage was readable before its emission time"

    def test_the_newest_vintage_per_pillar_wins(self, store):
        seed(store, day="2026-08-19", rmt=0.10)
        seed(store, day="2026-08-20", rmt=0.90)
        rows = {r["producer"]: r for r in
                store.daily_vintages(as_of=at("2026-08-21", 9, 0).isoformat())}
        assert rows["rmt"]["value"] == 0.90

    def test_history_is_preserved(self, store):
        seed(store, day="2026-08-19", rmt=0.10)
        seed(store, day="2026-08-20", rmt=0.90)
        history = store.vintage_history("rmt")
        assert [h["value"] for h in history] == [0.90, 0.10]


# ---------------------------------------------------------- the producer


class TestDailyVintageProducer:
    def test_it_hands_back_one_vintage_per_pillar(self, store):
        seed(store)
        produced = DailyVintageProducer(store=store).vintages_for(
            [], at("2026-08-21", 9, 20))
        assert [v.producer for v in produced] == list(ORDER)

    def test_stored_values_arrive_unchanged(self, store):
        seed(store)
        produced = {v.producer: v for v in
                    DailyVintageProducer(store=store).vintages_for(
                        [], at("2026-08-21", 9, 20))}
        assert produced["rmt"].value == 0.42
        assert produced["hamilton"].value == 0.31
        assert produced["hawkes"].value == 0.051

    def test_a_stored_absence_keeps_its_declared_kind(self, store):
        """structural drops the pillar from the D2 mask and transient does
        not; the producer must never infer one from the other."""
        seed(store, hawkes_origin="absent")
        produced = {v.producer: v for v in
                    DailyVintageProducer(store=store).vintages_for(
                        [], at("2026-08-21", 9, 20))}
        assert produced["hawkes"].value is None
        assert produced["hawkes"].absence == "structural"
        assert produced["hawkes"].absence_reason == "no_data_coverage"

    def test_a_pillar_with_no_row_is_a_declared_absence_not_a_guess(self, store):
        produced = {v.producer: v for v in
                    DailyVintageProducer(store=store).vintages_for(
                        [], at("2026-08-21", 9, 20))}
        assert all(v.value is None for v in produced.values())
        assert all(v.absence == "structural" for v in produced.values())
        assert produced["rmt"].absence_reason == "no_data_coverage"

    def test_the_absence_reason_is_one_the_service_accepts(self, store):
        """`PillarObservation.reason` is a closed Literal of three values, and
        a `Vintage`'s `absence_reason` flows into `UnavailableEmission.reason`.

        A descriptive string passes every test that builds a `Vintage`
        directly and then raises pydantic ValidationError the moment the
        service builds the emission -- which is how
        'no_daily_vintage_persisted' got as far as the real decision path
        before failing. This pins the contract at the producer boundary.
        """
        permitted = PERMITTED_ABSENCE_REASONS
        produced = DailyVintageProducer(store=store).vintages_for(
            [], at("2026-08-21", 9, 20))
        for vintage in produced:
            assert vintage.absence_reason in permitted, (
                f"{vintage.absence_reason!r} is not one of {permitted}; the "
                f"service will reject it when it builds the emission")

    def test_a_stored_absence_reason_is_also_one_the_service_accepts(self, store):
        seed(store, hawkes_origin="absent")
        produced = {v.producer: v for v in
                    DailyVintageProducer(store=store).vintages_for(
                        [], at("2026-08-21", 9, 20))}
        assert produced["hawkes"].absence_reason in PERMITTED_ABSENCE_REASONS

    def test_describe_reports_each_pillar_origin(self, store):
        seed(store)
        described = DailyVintageProducer(store=store).describe()
        assert described["kind"] == "daily_vintage"
        assert described["origins"]["rmt"] == "computed"
        assert described["origins"]["hawkes"] == "archived"
        assert "not a current reading" in described["note"]

    def test_describe_lists_only_pillars_carrying_a_value(self, store):
        seed(store, hawkes_origin="absent")
        described = DailyVintageProducer(store=store).describe()
        assert sorted(described["connected"]) == ["hamilton", "rmt"]

    def test_it_satisfies_the_same_protocol_as_the_null_producer(self, store):
        for producer in (DailyVintageProducer(store=store), NullProducers()):
            assert callable(producer.vintages_for)
            assert isinstance(producer.describe(), dict)


# ----------------------------------- producer -> service -> decision


class TestTheDecisionPathProducesAScore:
    def _service(self):
        """A service warm-started at DAILY cadence up to the day before the
        vintages under test.

        The spacing matters and is not a fixture detail. D4's observation
        noise `R^(p)(t - tau^(p))` grows with time since that pillar's
        previous update, and saturates. A warm start whose last observation
        is two months before the decision leaves every pillar at the noise
        ceiling, so the D2 mask excludes all three and no CSRS is produced --
        which is correct behaviour for stale inputs, and would make this test
        assert the wrong thing. Daily pillars observed daily is the realistic
        case and the one worth testing.
        """
        service = InferenceService(session_dates=SESSIONS)
        history = []
        for day in range(3, 20):                 # 2026-08-03 .. 2026-08-19
            stamp = at(f"2026-08-{day:02d}", 15, 30)
            for pillar, scale in (("hawkes", 0.05), ("rmt", 0.4),
                                  ("hamilton", 0.3)):
                history.append(Vintage(
                    producer=pillar, input_end=stamp.isoformat(),
                    emission_available_at=stamp.isoformat(),
                    value=scale + 0.001 * day))
        service.warm_start(history, cutoff=at("2026-08-20", 9, 15))
        return service

    def test_real_vintages_produce_a_csrs(self, store):
        """The thing R01 made impossible: a score from real pillar inputs."""
        from seraph.live.inference import DecisionRequest
        from seraph.live.engine_adapter import decision_id

        seed(store)
        service = self._service()
        producer = DailyVintageProducer(store=store)
        bar_end = at("2026-08-21", 10, 10)
        as_of = bar_end + DECISION_ALLOWANCE
        request = DecisionRequest(
            decision_id=decision_id(mode="live_shadow", stream_id="live",
                                    bar_end=bar_end.isoformat()),
            as_of=as_of, trigger="bar_close", mode="live_shadow")
        result = service.process(
            request, vintages=producer.vintages_for([], as_of), now=as_of)
        assert result.csrs is not None, "no CSRS from real vintages (R01)"
        assert 0.0 <= result.csrs.csrs <= 1.0

    def test_the_two_daily_pillars_carry_the_composite(self, store):
        """RMT and Hamilton are in the mask; Hawkes is not, and that is
        correct rather than a defect.

        `DECLARED_CADENCE` puts Hawkes at `bar_close` -- FR13 emits MTS_t at
        bar frequency. A daily-stamped value is therefore already stale
        against its own declared cadence, so D4's saturating noise takes its
        R to the ceiling and the D2 mask excludes it. The system is saying
        "this pillar is specified at bar frequency and you handed me a daily
        number", which is exactly right.

        The consequence is worth stating plainly: `--hawkes archived` gives an
        inspectable historical value, and it cannot contribute to a LIVE
        composite. The only route to Hawkes in a live CSRS is real 5-minute
        intraday bars.
        """
        from seraph.live.inference import DECLARED_CADENCE, DecisionRequest
        from seraph.live.engine_adapter import decision_id

        assert DECLARED_CADENCE["hawkes"] == "bar_close"
        assert DECLARED_CADENCE["rmt"] == "daily"

        seed(store)
        service = self._service()
        bar_end = at("2026-08-21", 10, 10)
        as_of = bar_end + DECISION_ALLOWANCE
        result = service.process(
            DecisionRequest(
                decision_id=decision_id(mode="live_shadow", stream_id="live",
                                        bar_end=bar_end.isoformat()),
                as_of=as_of, trigger="bar_close", mode="live_shadow"),
            vintages=DailyVintageProducer(store=store).vintages_for([], as_of),
            now=as_of)
        assert list(result.csrs.mask) == [False, True, True]
        assert result.csrs.csrs is not None
        # And the exclusion is said out loud, not silent.
        assert any("hawkes" in w.lower() for w in result.warnings)

    def test_an_absent_hawkes_drops_only_that_pillar(self, store):
        """A structural absence must remove Hawkes from the mask and leave a
        score standing on the other two, not void the composite."""
        from seraph.live.inference import DecisionRequest
        from seraph.live.engine_adapter import decision_id

        seed(store, hawkes_origin="absent")
        service = self._service()
        bar_end = at("2026-08-21", 10, 10)
        as_of = bar_end + DECISION_ALLOWANCE
        result = service.process(
            DecisionRequest(
                decision_id=decision_id(mode="live_shadow", stream_id="live",
                                        bar_end=bar_end.isoformat()),
                as_of=as_of, trigger="bar_close", mode="live_shadow"),
            vintages=DailyVintageProducer(store=store).vintages_for([], as_of),
            now=as_of)
        assert result.csrs is not None
        assert list(result.csrs.mask) == [False, True, True]
        assert any("hawkes" in w for w in result.warnings)


# ------------------------------------------------------- run_live wiring


class TestRunLiveAttachesTheRealProducer:
    def test_the_default_is_the_daily_producer(self, store):
        import run_live
        from seraph.live.clock import MarketClock

        loop, service, evaluator = run_live.build(
            replay=True, store=store, clock=MarketClock())
        assert isinstance(evaluator.producers, DailyVintageProducer)

    def test_the_null_producer_stays_reachable(self, store):
        """"No producer is connected" is a state the runtime must still be
        able to be in and report."""
        import run_live
        from seraph.live.clock import MarketClock

        loop, service, evaluator = run_live.build(
            replay=True, store=store, clock=MarketClock(), producers="none")
        assert isinstance(evaluator.producers, NullProducers)

    def test_a_replay_runs_on_its_own_stream(self, store):
        """X04: a replay's decisions must never be readable as the live
        stream's."""
        import run_live
        from seraph.live.clock import MarketClock

        _, _, replayed = run_live.build(replay=True, store=store,
                                        clock=MarketClock())
        assert replayed.stream_id == "replay"
        assert replayed.mode == "historical_replay"
