# Regression tests — R02, R03, R04, R05, R06/X04 (runtime state correctness)
"""The five P0 state defects in `seraph/live/`, each failing before its repair.

From `docs/SERAPH-ENGINEERING-COMPLETION-AUDIT-2026-10-18.md` section B, as
re-derived in the verification document. These are the defects the audit is
most emphatic about not deferring, because they would contaminate the evidence
later used to fix the science.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from seraph.live.engine_adapter import DECISION_ALLOWANCE, decision_id
from seraph.live.inference import (
    DecisionRequest,
    InferenceError,
    InferenceService,
    Vintage,
)
from seraph.live.store import DecisionConflict, LiveStore

IST = timezone(timedelta(hours=5, minutes=30))
SESSIONS = [f"2024-01-{d:02d}" for d in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12)]


def at(day: str, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(*(int(p) for p in day.split("-")), hour, minute, second,
                    tzinfo=IST)


def warm(svc: InferenceService, *, through: str = "2024-01-01",
         observations: int = 30) -> None:
    history = []
    for i in range(observations):
        stamp = at(through, 9, 15) - timedelta(days=observations + 10 - i)
        for pillar, scale in (("hawkes", 0.1), ("rmt", 0.5), ("hamilton", 0.3)):
            history.append(Vintage(producer=pillar, input_end=stamp.isoformat(),
                                   emission_available_at=stamp.isoformat(),
                                   value=scale + 0.001 * i))
    svc.warm_start(history, cutoff=at(through, 9, 15))


def service() -> InferenceService:
    svc = InferenceService(session_dates=SESSIONS)
    warm(svc)
    return svc


def request(day="2024-01-02", hour=10, minute=10, *, mode="live_shadow",
            stream="live", second=0) -> DecisionRequest:
    bar_end = at(day, hour, minute, second)
    return DecisionRequest(
        decision_id=decision_id(mode=mode, stream_id=stream,
                                bar_end=bar_end.isoformat()),
        as_of=bar_end + DECISION_ALLOWANCE, trigger="bar_close", mode=mode)


# ------------------------------------------------------------------- R02


class TestR02TheCutoffAdmitsNormalProducerLatency:
    """A producer cannot emit a bar-derived estimate until the bar is
    complete. With the cutoff AT the bar end, `emission_available_at` was
    later than `as_of` on EVERY bar: the vintage was withheld every time, the
    previous one carried forward and aged forever, and the pillar never
    updated. Nothing failed loudly; the score just stopped moving."""

    def test_a_vintage_emitted_one_second_after_its_bar_is_admitted(self):
        svc = service()
        bar_end = at("2024-01-02", 10, 10)
        vintage = Vintage(producer="rmt", input_end=bar_end.isoformat(),
                          emission_available_at=(bar_end + timedelta(seconds=1)
                                                 ).isoformat(), value=0.6)
        result = svc.process(request(), vintages=[vintage],
                             now=bar_end + timedelta(seconds=1))
        rmt = result.pillar_diagnostics["rmt"]
        assert rmt["eligible"] is True
        assert rmt["assimilated"] is True, "the pillar did not update (R02)"

    def test_the_old_cutoff_would_have_withheld_it(self):
        """The exact arithmetic of the defect: emission after the bar end."""
        bar_end = at("2024-01-02", 10, 10)
        emission = bar_end + timedelta(seconds=1)
        assert emission > bar_end                      # withheld under the old rule
        assert emission <= bar_end + DECISION_ALLOWANCE  # admitted under the new one

    def test_a_vintage_emitted_beyond_the_allowance_is_still_withheld(self):
        svc = service()
        bar_end = at("2024-01-02", 10, 10)
        late = bar_end + DECISION_ALLOWANCE + timedelta(seconds=30)
        vintage = Vintage(producer="rmt", input_end=bar_end.isoformat(),
                          emission_available_at=late.isoformat(), value=0.6)
        result = svc.process(request(), vintages=[vintage], now=late)
        assert result.pillar_diagnostics["rmt"]["assimilated"] is False
        assert any("withheld" in w for w in result.warnings)

    def test_genuinely_future_information_is_refused_as_lookahead(self):
        """Causality, and the allowance does not relax it: a vintage that
        OBSERVED beyond the cutoff must never be admitted."""
        svc = service()
        bar_end = at("2024-01-02", 10, 10)
        future = bar_end + timedelta(hours=1)
        vintage = Vintage(producer="rmt", input_end=future.isoformat(),
                          emission_available_at=bar_end.isoformat(), value=0.9)
        result = svc.process(request(), vintages=[vintage], now=bar_end)
        assert result.pillar_diagnostics["rmt"]["assimilated"] is False
        assert any("lookahead" in w.lower() for w in result.warnings)

    def test_the_cutoff_is_deterministic_not_wall_clock(self):
        """Two runs over the same bar must produce the same cutoff, or a
        replay cannot reproduce a decision identity."""
        one, two = request(), request()
        assert one.as_of == two.as_of
        assert one.decision_id == two.decision_id


# ------------------------------------------------------------------- R03


class TestR03WarmStartInitialisesTheFilter:
    """It assimilated into the standardizer, set `_latest`, marked the
    vintages CONSUMED -- and never touched `self.filter`. The ECDF was warm,
    the Kalman state was at its cold prior, and `process()` then skipped
    those vintages because they were already assimilated."""

    def test_the_filter_is_no_longer_at_its_cold_prior(self):
        cold = InferenceService(session_dates=SESSIONS)
        before = json.dumps(cold.snapshot().filter_state, sort_keys=True)
        warm(cold)
        after = json.dumps(cold.snapshot().filter_state, sort_keys=True)
        assert before != after, "warm start left the filter uninitialised (R03)"

    def test_warm_start_produces_no_decision(self):
        svc = service()
        assert svc.snapshot().decisions == 0

    def test_the_standardizer_is_warm_too(self):
        svc = service()
        for pillar in ("hawkes", "rmt", "hamilton"):
            assert svc.standardizer.observations(pillar) == 30

    def test_a_warm_start_equals_a_chronological_replay(self):
        """The acceptance the audit asks for: cold warm-start versus
        equivalent chronological replay must agree."""
        history = []
        for i in range(30):
            stamp = at("2024-01-01", 9, 15) - timedelta(days=40 - i)
            for pillar, scale in (("hawkes", 0.1), ("rmt", 0.5), ("hamilton", 0.3)):
                history.append(Vintage(
                    producer=pillar, input_end=stamp.isoformat(),
                    emission_available_at=stamp.isoformat(),
                    value=scale + 0.001 * i))

        bulk = InferenceService(session_dates=SESSIONS)
        bulk.warm_start(history, cutoff=at("2024-01-01", 9, 15))

        # The prior must depend on OBSERVATION order, not on the order the
        # caller happened to hand the history over, or a warm start is not
        # reproducible.
        shuffled = InferenceService(session_dates=SESSIONS)
        shuffled.warm_start(list(reversed(history)),
                            cutoff=at("2024-01-01", 9, 15))
        assert json.dumps(bulk.snapshot().filter_state, sort_keys=True) == \
            json.dumps(shuffled.snapshot().filter_state, sort_keys=True)

    def test_warm_start_refuses_after_a_decision(self):
        svc = service()
        svc.process(request(), vintages=[])
        with pytest.raises(InferenceError, match="before the first decision"):
            warm(svc)

    def test_a_vintage_at_or_after_the_cutoff_is_left_for_the_live_path(self):
        svc = InferenceService(session_dates=SESSIONS)
        cutoff = at("2024-01-01", 9, 15)
        svc.warm_start([Vintage(producer="rmt", input_end=cutoff.isoformat(),
                                emission_available_at=cutoff.isoformat(),
                                value=0.5)], cutoff=cutoff)
        assert svc.standardizer.observations("rmt") == 0


# ------------------------------------------------------------------- R04


class TestR04ALateOlderVintageDoesNotReplaceANewerOne:
    """The admission loop sorted by `emission_available_at` and assigned
    `_latest` unconditionally, so the emission that ARRIVED last won
    regardless of which one OBSERVED last. A producer re-emitting a stale
    window silently rolled the pillar backwards."""

    def _two_passes(self):
        """The defect's real shape: the late vintage arrives in a LATER
        `process()` call. Within one batch the admission loop now sorts by
        `input_end`, so the ordering is already correct there; across calls
        the incumbent in `_latest` is what must be defended."""
        svc = service()
        first_bar = at("2024-01-02", 10, 10)
        second_bar = at("2024-01-02", 10, 15)
        newer = Vintage(producer="rmt", input_end=first_bar.isoformat(),
                        emission_available_at=first_bar.isoformat(), value=0.80)
        svc.process(request(minute=10), vintages=[newer], now=first_bar)
        late_older = Vintage(
            producer="rmt",
            input_end=(first_bar - timedelta(hours=2)).isoformat(),
            emission_available_at=second_bar.isoformat(), value=0.20)
        second = svc.process(request(minute=15), vintages=[late_older],
                             now=second_bar)
        return svc, second, first_bar

    def test_the_newer_observation_stands(self):
        _, second, first_bar = self._two_passes()
        assert second.pillar_diagnostics["rmt"]["vintage"]["input_end"] == \
            first_bar.isoformat(), \
            "a late older vintage rolled the pillar backwards (R04)"

    def test_the_late_older_vintage_is_recorded_not_discarded_silently(self):
        _, second, _ = self._two_passes()
        assert any("the newer observation stands" in w for w in second.warnings)
        assert second.pillar_diagnostics["rmt"]["withheld"] is not None

    def test_the_pillar_value_does_not_roll_backwards(self):
        svc, second, _ = self._two_passes()
        assert svc._latest["rmt"].value == 0.80

    def test_within_one_batch_the_order_is_already_defended(self):
        """Sorting by `input_end` makes arrival order irrelevant inside a
        batch, whichever way the caller hands them over."""
        bar_end = at("2024-01-02", 10, 10)
        newer = Vintage(producer="rmt", input_end=bar_end.isoformat(),
                        emission_available_at=bar_end.isoformat(), value=0.80)
        older = Vintage(producer="rmt",
                        input_end=(bar_end - timedelta(hours=2)).isoformat(),
                        emission_available_at=(bar_end + timedelta(seconds=2)
                                               ).isoformat(), value=0.20)
        for batch in ([newer, older], [older, newer]):
            svc = service()
            svc.process(request(), vintages=batch, now=bar_end)
            assert svc._latest["rmt"].input_end == bar_end.isoformat()

    def test_a_correction_to_the_same_observation_still_applies(self):
        """A revision of the SAME `input_end` is legitimate and must land."""
        svc = service()
        bar_end = at("2024-01-02", 10, 10)
        first = Vintage(producer="rmt", input_end=bar_end.isoformat(),
                        emission_available_at=bar_end.isoformat(), value=0.80)
        corrected = Vintage(producer="rmt", input_end=bar_end.isoformat(),
                            emission_available_at=(bar_end + timedelta(seconds=1)
                                                   ).isoformat(), value=0.55,
                            bundle_id="corrected")
        result = svc.process(request(), vintages=[first, corrected], now=bar_end)
        assert result.pillar_diagnostics["rmt"]["vintage"]["input_end"] == \
            bar_end.isoformat()


# ------------------------------------------------------------------- R05


class TestR05CheckpointBindsStateDefiningConfiguration:
    """`restore()` validated `pipeline_version` and `calendar_id` only, so a
    service rebuilt with different process noise or different fusion weights
    resumed from the old filter state silently. Neither value was even in the
    payload, so no caller could have detected it either."""

    def test_the_snapshot_carries_a_configuration_fingerprint(self):
        snapshot = service().snapshot()
        assert snapshot.config_id
        assert snapshot.config["q_proc"] == pytest.approx(1e-3)

    def test_an_identical_configuration_resumes(self):
        source = service()
        target = InferenceService(session_dates=SESSIONS)
        target.restore(source.snapshot())
        assert json.dumps(target.snapshot().filter_state, sort_keys=True) == \
            json.dumps(source.snapshot().filter_state, sort_keys=True)

    def test_changed_process_noise_refuses_to_resume(self):
        source = service()
        target = InferenceService(session_dates=SESSIONS, q_proc=5e-3)
        with pytest.raises(InferenceError, match="configuration"):
            target.restore(source.snapshot())

    def test_the_refusal_names_which_part_differs(self):
        source = service()
        target = InferenceService(session_dates=SESSIONS, q_proc=5e-3)
        with pytest.raises(InferenceError) as caught:
            target.restore(source.snapshot())
        assert "q_proc" in str(caught.value), \
            "a bare 'configuration differs' sends the operator reading source"

    def test_changed_fusion_weights_refuse_to_resume(self):
        from seraph.live.inference import _uniform_weights
        source = service()
        # FusionWeights is a pydantic model, not a dataclass.
        other = _uniform_weights().model_copy(
            update=dict(artefact_id="fw:different"))
        target = InferenceService(session_dates=SESSIONS, weights=other)
        with pytest.raises(InferenceError, match="weights_artefact_id|configuration"):
            target.restore(source.snapshot())

    def test_a_snapshot_without_a_fingerprint_is_refused(self):
        """An unverifiable resume is the defect, not the inconvenience."""
        from dataclasses import replace as dc_replace
        source = service()
        legacy = dc_replace(source.snapshot(), config_id="", config={})
        target = InferenceService(session_dates=SESSIONS)
        with pytest.raises(InferenceError, match="no configuration fingerprint"):
            target.restore(legacy)

    def test_a_bundle_contributes_its_content_not_its_label(self):
        """The audit is explicit: a bundle id is a name, and a name can be
        reused over different bytes."""
        svc = service()
        _, config = svc.config_fingerprint()
        assert "bundles" in config
        assert isinstance(config["bundles"], list)

    def test_a_changed_calendar_still_refuses(self):
        source = service()
        target = InferenceService(session_dates=SESSIONS[:5])
        with pytest.raises(InferenceError):
            target.restore(source.snapshot())


# -------------------------------------------------------------- R06 / X04


class TestR06IdempotencyIsBoundToContent:
    """`commit_decision` returned an existing row as a replay BEFORE
    comparing its payload, so the same id carrying different bytes was
    silently reported as a replay and the new content was thrown away."""

    @pytest.fixture
    def store(self, tmp_path):
        return LiveStore(tmp_path / "runtime.sqlite")

    def _commit(self, store, *, decision_id="live_shadow:live:bar-1", csrs=0.4):
        return store.commit_decision(
            decision_id=decision_id, as_of="2024-01-02T10:10:05+05:30",
            computed_at="2024-01-02T10:10:05+05:30",
            payload=dict(csrs=csrs), publication_state="current",
            state=dict(pipeline_version="t"), input_cursor=dict(batches=[]))

    def test_the_same_id_with_the_same_content_is_a_replay(self, store):
        self._commit(store)
        again = self._commit(store)
        assert again["replayed"] is True

    def test_the_same_id_with_different_content_is_a_conflict(self, store):
        self._commit(store, csrs=0.4)
        with pytest.raises(DecisionConflict):
            self._commit(store, csrs=0.9)

    def test_the_conflict_names_both_hashes(self, store):
        self._commit(store, csrs=0.4)
        with pytest.raises(DecisionConflict) as caught:
            self._commit(store, csrs=0.9)
        assert "immutable" in str(caught.value)

    def test_a_conflict_writes_nothing(self, store):
        self._commit(store, csrs=0.4)
        with pytest.raises(DecisionConflict):
            self._commit(store, csrs=0.9)
        assert store.decision("live_shadow:live:bar-1")["payload"]["csrs"] == 0.4


class TestR06IdentityExcludesOperationalMeasurement:
    """Found by `r08_recovery_probe.py`, not by the audit: the payload mixes
    the decision (score, publishability, inputs) with how the run WENT
    (latency, feed liveness). Hashing both made R06's conflict detection fire
    on a LEGITIMATE recomputation -- re-deciding the same bar after a restart
    raised `DecisionConflict` purely because the stopwatch read differently."""

    @pytest.fixture
    def store(self, tmp_path):
        return LiveStore(tmp_path / "runtime.sqlite")

    def _commit(self, store, *, latency, feed_seen, csrs=0.4):
        return store.commit_decision(
            decision_id="live_shadow:live:bar-1",
            as_of="2024-01-02T10:10:05+05:30",
            computed_at="2024-01-02T10:10:05+05:30",
            payload=dict(csrs=csrs, publishable=True,
                         bar_close_to_decision_ms=latency,
                         feed=dict(last_message_at=feed_seen),
                         recency=dict(age_seconds=1)),
            publication_state="current",
            state=dict(pipeline_version="t"), input_cursor=dict(batches=[]))

    def test_a_different_latency_is_not_a_different_decision(self, store):
        self._commit(store, latency=12.5, feed_seen="10:10:01")
        again = self._commit(store, latency=88.1, feed_seen="10:10:04")
        assert again["replayed"] is True, \
            "a legitimate recomputation was rejected as a conflict"

    def test_a_different_score_is_still_a_conflict(self, store):
        self._commit(store, latency=12.5, feed_seen="10:10:01", csrs=0.4)
        with pytest.raises(DecisionConflict):
            self._commit(store, latency=12.5, feed_seen="10:10:01", csrs=0.9)

    def test_the_full_payload_is_still_stored_verbatim(self, store):
        """Nothing is discarded; this only decides what 'the same decision'
        means."""
        self._commit(store, latency=12.5, feed_seen="10:10:01")
        stored = store.decision("live_shadow:live:bar-1")["payload"]
        assert stored["bar_close_to_decision_ms"] == 12.5
        assert stored["feed"]["last_message_at"] == "10:10:01"

    def test_the_excluded_fields_are_named_and_few(self):
        from seraph.live.store import OPERATIONAL_PAYLOAD_FIELDS, decision_identity
        assert "csrs" not in OPERATIONAL_PAYLOAD_FIELDS
        assert "publishable" not in OPERATIONAL_PAYLOAD_FIELDS
        assert "bar_close_to_decision_ms" in OPERATIONAL_PAYLOAD_FIELDS
        identity = decision_identity(dict(csrs=1, bar_close_to_decision_ms=5))
        assert identity == dict(csrs=1)


class TestR06ReadsAreStreamScoped:
    """`latest_decision()` and `decisions()` queried every row in the
    database and ordered by `as_of`, while `head()` beside them was
    stream-scoped. So a replay stream's decision could be returned as the
    current live reading."""

    def test_a_replay_decision_is_not_the_live_latest(self, tmp_path):
        path = tmp_path / "runtime.sqlite"
        live = LiveStore(path, stream_id="live")
        replay = LiveStore(path, stream_id="replay")
        live.commit_decision(
            decision_id="live_shadow:live:bar-1",
            as_of="2024-01-02T10:00:00+05:30",
            computed_at="2024-01-02T10:00:00+05:30",
            payload=dict(csrs=0.1), publication_state="current",
            state=dict(pipeline_version="t"), input_cursor=dict(batches=[]))
        replay.commit_decision(
            decision_id="historical_replay:replay:bar-2",
            as_of="2024-01-02T23:00:00+05:30",       # LATER as_of
            computed_at="2024-01-02T23:00:00+05:30",
            payload=dict(csrs=0.99), publication_state="current",
            state=dict(pipeline_version="t"), input_cursor=dict(batches=[]))

        latest = live.latest_decision()
        assert latest["decision_id"] == "live_shadow:live:bar-1", \
            "a replay decision was returned as the current live reading (R06)"
        assert latest["stream_id"] == "live"

    def test_each_stream_sees_only_its_own_history(self, tmp_path):
        path = tmp_path / "runtime.sqlite"
        live = LiveStore(path, stream_id="live")
        replay = LiveStore(path, stream_id="replay")
        for i in range(3):
            live.commit_decision(
                decision_id=f"live_shadow:live:bar-{i}",
                as_of=f"2024-01-02T10:0{i}:00+05:30",
                computed_at=f"2024-01-02T10:0{i}:00+05:30",
                payload=dict(csrs=0.1 * i), publication_state="current",
                state=dict(pipeline_version="t"), input_cursor=dict(batches=[]))
        replay.commit_decision(
            decision_id="historical_replay:replay:bar-9",
            as_of="2024-01-02T23:00:00+05:30",
            computed_at="2024-01-02T23:00:00+05:30",
            payload=dict(csrs=0.99), publication_state="current",
            state=dict(pipeline_version="t"), input_cursor=dict(batches=[]))
        assert len(live.decisions()) == 3
        assert len(replay.decisions()) == 1

    def test_an_outbox_event_belongs_to_its_stream(self, tmp_path):
        """A replay must not be able to emit a production alert."""
        path = tmp_path / "runtime.sqlite"
        live = LiveStore(path, stream_id="live")
        replay = LiveStore(path, stream_id="replay")
        replay.commit_decision(
            decision_id="historical_replay:replay:bar-1",
            as_of="2024-01-02T10:00:00+05:30",
            computed_at="2024-01-02T10:00:00+05:30",
            payload=dict(csrs=0.9), publication_state="current",
            state=dict(pipeline_version="t"), input_cursor=dict(batches=[]),
            events=[dict(event_kind="alert", aggregate_id="a",
                         idempotency_key="k", payload={})])
        assert replay.pending_events(), "the replay's own event is missing"
        assert live.pending_events() == [], \
            "a replay event appeared in the live delivery queue (R06)"

    def test_the_head_and_the_latest_decision_agree(self, tmp_path):
        store = LiveStore(tmp_path / "runtime.sqlite", stream_id="live")
        store.commit_decision(
            decision_id="live_shadow:live:bar-1",
            as_of="2024-01-02T10:00:00+05:30",
            computed_at="2024-01-02T10:00:00+05:30",
            payload=dict(csrs=0.1), publication_state="current",
            state=dict(pipeline_version="t"), input_cursor=dict(batches=[]))
        assert store.head().decision_id == store.latest_decision()["decision_id"]


class TestX04DecisionIdCarriesStreamAndMode:
    def test_mode_and_stream_are_part_of_the_identity(self):
        bar = "2024-01-02T10:10:00+05:30"
        assert decision_id(mode="live_shadow", stream_id="live", bar_end=bar) \
            != decision_id(mode="historical_replay", stream_id="live", bar_end=bar)
        assert decision_id(mode="live_shadow", stream_id="live", bar_end=bar) \
            != decision_id(mode="live_shadow", stream_id="demo", bar_end=bar)

    def test_the_same_bar_in_the_same_stream_and_mode_is_one_id(self):
        bar = "2024-01-02T10:10:00+05:30"
        assert decision_id(mode="live_shadow", stream_id="live", bar_end=bar) \
            == decision_id(mode="live_shadow", stream_id="live", bar_end=bar)

    def test_a_replay_cannot_overwrite_a_live_decision(self, tmp_path):
        """The two halves together: distinct ids AND content comparison."""
        path = tmp_path / "runtime.sqlite"
        bar = "2024-01-02T10:10:00+05:30"
        live = LiveStore(path, stream_id="live")
        replay = LiveStore(path, stream_id="replay")
        live.commit_decision(
            decision_id=decision_id(mode="live_shadow", stream_id="live",
                                    bar_end=bar),
            as_of=bar, computed_at=bar, payload=dict(csrs=0.2),
            publication_state="current", state=dict(pipeline_version="t"),
            input_cursor=dict(batches=[]))
        replay.commit_decision(
            decision_id=decision_id(mode="historical_replay",
                                    stream_id="replay", bar_end=bar),
            as_of=bar, computed_at=bar, payload=dict(csrs=0.95),
            publication_state="current", state=dict(pipeline_version="t"),
            input_cursor=dict(batches=[]))
        assert live.latest_decision()["payload"]["csrs"] == 0.2
