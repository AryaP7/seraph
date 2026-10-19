"""Does this measure apply at the moment being asked about?

Three defects motivated this, and the first two were mine.

**`adopted` was treated as in force.** A final determination is *decided*; a
measure begins applying when it takes effect, which may be weeks later or need
a separate order. Collapsing the two meant a 2024 determination reported as
currently operating — and because an in-force instrument never ages out, it
reported so forever.

**A 2099 effective date still read as in force.** The earlier fix converted a
future `effective` to `adopted`, which was right, and `adopted` was itself in
the in-force set. The downgrade only moved the problem one step.

**Applicability was evaluated once, at acquisition**, so a replay of last year
saw this year's measures and a since-repealed measure still applied.
"""
from __future__ import annotations

import pytest

from seraph.news.currency import discovery, in_force
from seraph.news.extraction import extract_events
from seraph.news.lifecycle import applicability, apply_supersession
from seraph.news.model import Place, Story, Timing
from seraph.news.registry import MasterData

NOW = "2026-10-18T09:00:00+05:30"


def registry() -> MasterData:
    data = MasterData()
    data.add_place(Place("in", "India", "country", iso_code="IND"))
    return data


def event_for(title: str, seen: str = "2026-10-01T00:00:00+05:30"):
    story = Story(story_id="s", source_id="x", observation_id="o", title=title,
                  url="https://example.invalid/1", body=None,
                  timing=Timing(first_seen_at=seen), syndication_group="g")
    results = list(extract_events([story], registry()))
    assert results and results[0].event is not None, title
    return results[0].event


# --------------------------------------- decided is not the same as applying

def test_an_adopted_determination_with_no_effective_date_is_not_in_force():
    """The central correction. A final determination is a decision; the
    measure begins when it takes effect."""
    event = event_for("Widgets From India: Final Affirmative Determination",
                      seen="2024-01-01T00:00:00+05:30")
    assert event.frame.policy_status == "adopted"
    state = applicability(event, NOW)
    assert state["in_force"] is False
    assert state["state"] == "decided_effect_unknown"


def test_an_issued_order_with_no_later_date_is_in_force():
    """A duty ORDER is the operative instrument and says so."""
    event = event_for("Widgets From India: Antidumping Duty Order",
                      seen="2024-01-01T00:00:00+05:30")
    assert applicability(event, NOW)["in_force"] is True


def test_a_measure_effective_in_2099_does_not_apply_today():
    event = event_for("Widgets: the measure is effective from 2099-01-01.")
    state = applicability(event, NOW)
    assert state["in_force"] is False
    assert state["state"] == "decided_not_yet_in_force"
    assert "2099" in state["basis"]


def test_a_measure_whose_date_has_arrived_does_apply():
    event = event_for("Widgets: the measure is effective from 2026-01-01.",
                      seen="2026-01-02T00:00:00+05:30")
    assert applicability(event, NOW)["in_force"] is True


def test_a_repealed_measure_does_not_apply():
    event = event_for("Widgets From India: Revocation of the Antidumping "
                      "Duty Order")
    state = applicability(event, NOW)
    assert state["state"] == "ended"
    assert state["in_force"] is False


@pytest.mark.parametrize("title", [
    "Widgets From India: Preliminary Affirmative Determination",
    "Widgets From India: Initiation of Antidumping Duty Investigation",
])
def test_a_pending_stage_applies_to_nothing(title):
    state = applicability(event_for(title), NOW)
    assert state["state"] == "pending"
    assert state["in_force"] is False


# ------------------------------------- the question needs a decision time

def test_applicability_depends_on_the_decision_time_asked_about():
    """Evaluated once at acquisition, a replay of last year sees this year's
    measures."""
    event = event_for("Widgets: the measure is effective from 2026-06-01.",
                      seen="2026-05-01T00:00:00+05:30")
    assert applicability(event, "2026-05-02T00:00:00+05:30")["in_force"] is False
    assert applicability(event, "2026-07-01T00:00:00+05:30")["in_force"] is True


def test_in_force_without_a_decision_time_is_false_not_true():
    """Returning True when the question cannot be answered is what made every
    adopted measure permanent."""
    event = event_for("Widgets From India: Antidumping Duty Order")
    assert in_force(event, None) is False
    assert in_force(event, NOW) is True


def test_every_answer_states_its_reason():
    for title in ("Widgets From India: Antidumping Duty Order",
                  "Widgets From India: Final Affirmative Determination",
                  "Widgets: the measure is effective from 2099-01-01."):
        assert applicability(event_for(title), NOW)["basis"]


def test_an_unreadable_effective_date_is_not_assumed_to_have_arrived():
    """Guessing in either direction is worse than reporting the unknown."""
    from dataclasses import replace
    event = event_for("Widgets From India: Antidumping Duty Order")
    broken = replace(event, timing=replace(event.timing,
                                           effective_at="not-a-date"))
    state = applicability(broken, NOW)
    assert state["in_force"] is False
    assert state["state"] == "decided_effect_unknown"


# ------------------------------------------------------- supersession

def test_a_superseded_measure_stops_applying():
    """An old adopted measure must not remain in force forever because its
    own row never changes: the later instrument is what ends it."""
    from dataclasses import replace
    old = event_for("Widgets From India: Antidumping Duty Order")
    newer = replace(event_for("Widgets From India: Amended Duty Order"),
                    event_id="evt_new", supersedes=old.event_id)
    # This test is about an operative replacement, not an amendment whose
    # effective status the title-only extractor has not established.
    newer = replace(newer, frame=replace(newer.frame, policy_status='effective'))
    states = apply_supersession([old, newer], NOW)
    assert states[old.event_id]["in_force"] is False
    assert states[old.event_id]["state"] == "superseded"
    assert states[old.event_id]["superseded_by"] == "evt_new"


def test_an_unsuperseded_measure_is_unaffected():
    event = event_for("Widgets From India: Antidumping Duty Order")
    states = apply_supersession([event], NOW)
    assert states[event.event_id]["in_force"] is True


# ------------------------- old news newly received is not a new development

def test_a_backfilled_document_is_a_late_discovery_not_a_development():
    """Both are "first seen today", and the rail sorts by first sighting, so a
    2024 document lands beside this morning's."""
    class E:
        timing = Timing(first_seen_at="2026-10-18T08:00:00+05:30",
                        published_at="2024-03-01T00:00:00+05:30")
    found = discovery(E(), NOW)
    assert found["kind"] == "late_discovery"
    assert found["lag_days"] > 300
    assert "not a new development" in found["basis"]


def test_a_document_received_near_publication_is_current():
    class E:
        timing = Timing(first_seen_at="2026-10-18T08:00:00+05:30",
                        published_at="2026-10-18T07:00:00+05:30")
    assert discovery(E(), NOW)["kind"] == "current"


def test_a_forthcoming_document_is_neither():
    class E:
        timing = Timing(first_seen_at="2026-10-18T08:00:00+05:30",
                        published_at="2026-10-20T00:00:00+05:30",
                        publication_scheduled=True)
    assert discovery(E(), NOW)["kind"] == "forthcoming"
