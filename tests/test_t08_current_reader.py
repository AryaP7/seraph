"""T08 — a live decision reaches the screen, labelled for what it is (R12).

The console read archive runs and nothing else, and a replay rendered
identically to a live reading. These tests pin the three separations that
make a current-result reader safe:

* the latest score and the worker's health are different facts;
* an outage leaves the last score inspectable **with its own timestamp** and
  never reissues it as now;
* `live`, `replay` and `demo` are chosen, never fallen back to.

Plus the polling contract: a revision id that moves only when the screen's
content moves, and a refresh that will not rebase a form under someone's hands.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from seraph.dashboard.current_reader import (
    READER_VERSION,
    VIEW_MODES,
    CurrentResult,
    RefreshGate,
    read_current,
    revision,
    worker_health,
)
from seraph.live.store import LiveStore

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 17, 11, 0, tzinfo=IST)


@pytest.fixture
def store(tmp_path):
    return LiveStore(tmp_path / "live.sqlite")


def commit(store, *, n=1, minute=55, publishable=True, hour=10, at=NOW):
    return store.commit_decision(
        at=at,
        decision_id=f"d{n}",
        as_of=f"2026-10-17T{hour:02d}:{minute:02d}:00+05:30",
        computed_at=f"2026-10-17T{hour:02d}:{minute:02d}:01+05:30",
        payload=dict(csrs=0.42, publication=dict(
            current_allowed=publishable, reasons=[] if publishable
            else ["unverified_feed"])),
        publication_state="current" if publishable else "withheld",
        state=dict(x=[1, 2, 3], n=n))


# ------------------------------------------------------------ the modes


def test_the_three_modes_are_explicit():
    assert VIEW_MODES == ("live", "replay", "demo")


def test_an_unknown_mode_is_refused(store):
    with pytest.raises(ValueError, match="unknown view mode"):
        read_current(store, mode="whatever", now=NOW)


def test_live_with_no_decision_does_not_fall_back_to_an_archive(store):
    """The whole point: a replay must never be served as a live reading."""
    result = read_current(store, mode="live", now=NOW)
    assert result.decision_id is None
    assert result.is_current is False
    assert "does NOT fall back" in result.reason


def test_demo_consults_no_decision_at_all(store):
    commit(store)
    result = read_current(store, mode="demo", now=NOW)
    assert result.decision_id is None
    assert result.is_current is False
    assert "never a reading of the market" in result.reason


def test_replay_shows_a_decision_but_never_as_current(store):
    commit(store)
    result = read_current(store, mode="replay", now=NOW,
                          lifecycle_state="collecting")
    assert result.decision_id == "d1"
    assert result.is_current is False
    assert "shown as a replay" in result.reason


def test_live_reports_a_fresh_publishable_decision_as_current(store):
    commit(store, minute=59)
    result = read_current(store, mode="live", now=NOW,
                          lifecycle_state="collecting")
    assert result.is_current is True
    assert result.decision_id == "d1"
    assert result.reason == "current reading from the live runtime"


# ------------------------------------------------- score vs worker health


def test_the_score_and_the_worker_are_separate_facts(store):
    commit(store, minute=59)
    result = read_current(store, mode="live", now=NOW,
                          lifecycle_state="collecting")
    assert result.health.state == "collecting"
    assert result.health.stream_version == 1
    assert result.payload["csrs"] == pytest.approx(0.42)
    # The health block never carries the score, and the score block never
    # carries a verdict about the worker.
    assert "csrs" not in result.health.describe()


def test_a_stopped_worker_does_not_erase_the_last_score(store):
    commit(store, minute=59)
    result = read_current(store, mode="live", now=NOW + timedelta(hours=3),
                          lifecycle_state="stopped")
    assert result.decision_id == "d1"
    assert result.payload is not None, "the last score stays inspectable"
    assert result.is_current is False
    assert result.health.stale is True


def test_an_outage_does_not_re_date_the_last_score(store):
    commit(store, minute=59)
    later = NOW + timedelta(hours=4)
    result = read_current(store, mode="live", now=later,
                          lifecycle_state="degraded")
    assert result.as_of == "2026-10-17T10:59:00+05:30", "its own timestamp"
    assert result.age_seconds > 3 * 3600
    assert "NOT re-dated" in result.reason


def test_a_withheld_decision_is_inspectable_but_not_current(store):
    commit(store, minute=59, publishable=False)
    result = read_current(store, mode="live", now=NOW,
                          lifecycle_state="collecting")
    assert result.is_current is False
    assert result.payload["publication"]["reasons"] == ["unverified_feed"]
    assert "withheld this decision" in result.reason


def test_an_age_limit_refuses_to_call_an_old_decision_current(store):
    commit(store, minute=0, hour=9)
    result = read_current(store, mode="live", now=NOW,
                          lifecycle_state="collecting",
                          max_age=timedelta(minutes=30))
    assert result.is_current is False
    assert "beyond the age this view will call current" in result.reason


def test_a_worker_that_never_ran_says_so(store):
    health = worker_health(store, lifecycle_state="initializing", now=NOW)
    assert health.stale is True
    assert health.last_pass_at is None
    assert "never committed a pass" in health.note


def test_health_surfaces_undelivered_and_dead_lettered_events(store):
    store.commit_decision(
        decision_id="d1", as_of="2026-10-17T10:59:00+05:30",
        computed_at="2026-10-17T10:59:01+05:30", payload={},
        publication_state="current", state={},
        events=[dict(event_kind="alert", payload={})])
    health = worker_health(store, lifecycle_state="collecting", now=NOW)
    assert health.undelivered_events == 1
    assert health.dead_letters == 0


def test_a_decision_from_the_future_is_a_defect_not_fresh_data(store):
    """Observed in the browser as "-340 min old", and let through.

    A decision stamped after now is a clock or data defect. Reporting a
    negative age as an age, and calling it current, is the same mistake the
    market clock already refuses for observations.
    """
    commit(store, hour=15, minute=30)
    result = read_current(store, mode="live", now=NOW,
                          lifecycle_state="collecting")
    assert result.age_seconds < 0
    assert result.is_current is False
    assert "in the FUTURE" in result.reason
    assert "clock or data defect" in result.reason


def test_a_future_decision_is_still_inspectable(store):
    commit(store, hour=15, minute=30)
    result = read_current(store, mode="live", now=NOW)
    assert result.decision_id == "d1"
    assert result.payload is not None


# ---------------------------------------------------------------- polling


def test_the_revision_moves_only_when_the_content_does(store):
    first = revision(store)
    assert revision(store) == first, "polling alone must not move it"
    commit(store)
    assert revision(store) != first


def test_the_revision_tracks_the_news_channel_too(store):
    base = revision(store, news_revision="r1")
    assert revision(store, news_revision="r1") == base
    assert revision(store, news_revision="r2") != base


def test_an_unchanged_revision_is_not_applied_again():
    gate = RefreshGate(revision="r1")
    assert gate.offer("r1")["action"] == "unchanged"


def test_new_data_applies_silently_when_nothing_is_being_edited():
    gate = RefreshGate(revision="r1")
    outcome = gate.offer("r2")
    assert outcome["action"] == "applied"
    assert gate.revision == "r2"


def test_new_data_is_held_and_announced_while_a_form_is_edited():
    """Rebasing a form under someone's hands loses an edit silently."""
    gate = RefreshGate(revision="r1", editing=True)
    outcome = gate.offer("r2")
    assert outcome["action"] == "held"
    assert gate.revision == "r1", "the baseline did not move"
    assert gate.pending_revision == "r2"
    assert "apply it explicitly" in outcome["message"]
    assert gate.describe()["has_newer_data"] is True


def test_held_data_is_applied_only_by_an_explicit_act():
    gate = RefreshGate(revision="r1", editing=True)
    gate.offer("r2")
    outcome = gate.apply_pending()
    assert outcome["action"] == "applied"
    assert gate.revision == "r2"
    assert gate.editing is False
    assert gate.describe()["has_newer_data"] is False


def test_applying_nothing_is_not_an_error():
    gate = RefreshGate(revision="r1")
    assert gate.apply_pending()["action"] == "nothing_pending"


def test_the_notice_list_is_bounded():
    gate = RefreshGate(revision="r0", editing=True)
    for i in range(20):
        gate.offer(f"r{i + 1}")
    assert len(gate.describe()["notices"]) == 5


# ------------------------------------------------------------- transport


def test_the_result_is_json_shaped_and_names_its_version(store):
    import json

    commit(store)
    result = read_current(store, mode="live", now=NOW)
    described = result.describe()
    json.dumps(described)
    assert described["version"] == READER_VERSION
    assert set(described) >= {"mode", "decision_id", "as_of", "is_current",
                              "reason", "health", "payload"}


def test_the_exact_persisted_decision_id_is_what_reaches_the_reader(store):
    """T08's acceptance: the id on screen is the id in the database."""
    committed = commit(store, n=7)
    result = read_current(store, mode="live", now=NOW)
    assert result.decision_id == committed["decision_id"] == "d7"
    assert store.decision(result.decision_id)["payload_hash"] == \
        committed["payload_hash"]
