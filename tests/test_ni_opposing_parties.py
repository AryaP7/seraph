"""Who gains and who loses from the same measure, side by side.

`EventFrameV2` has carried `beneficiaries` and `constrained_parties` since it
was written, and **nothing ever populated them**. Every impact reached the
screen as one signed direction for one target, so the same document read as
good or bad news depending on which target happened to be mapped.

A duty on imports of a product from India constrains the Indian exporter,
benefits the producer competing with it in the importing country, and
constrains the downstream buyer there who now pays more. All three follow from
one instrument.

The net effect is deliberately **not** computed. Which side dominates depends
on sizes this system does not hold, and a number produced without them would
be the most confident-looking invention available here.
"""
from __future__ import annotations

import pytest

from seraph.news.extraction import extract_events
from seraph.news.model import Story, Timing
from seraph.news.opposing import OPPOSING_ROLES, opposing_parties
from seraph.news.registry import load_master_data

SEEN = "2026-10-18T09:00:00+05:30"


def event_for(title: str):
    master, _ = load_master_data()
    story = Story(story_id="s", source_id="x", observation_id="o", title=title,
                  url="https://x.invalid/1", body=None,
                  timing=Timing(first_seen_at=SEEN), syndication_group="g")
    return list(extract_events([story], master))[0].event


# ------------------------------------------------------- both sides

def test_a_duty_constrains_the_exporter_and_benefits_the_producer():
    view = opposing_parties(
        event_for("Chromium Trioxide From India: Antidumping Duty Order"))
    assert "exporter" in view.constrained
    assert "domestic_producer" in view.benefiting
    assert view.is_two_sided


def test_the_downstream_buyer_is_constrained_too():
    """The side most often forgotten: a duty raises an input cost for the
    buyer in the importing country, who is not the exporter and not the
    protected producer."""
    view = opposing_parties(
        event_for("Chromium Trioxide From India: Antidumping Duty Order"))
    assert "downstream_buyer_in_importing_country" in view.constrained


def test_ending_a_measure_reverses_who_gains():
    """A revocation relieves whoever the measure constrained and exposes
    whoever it protected. The roles are the same; the sign is not."""
    view = opposing_parties(event_for(
        "Certain Hot-Rolled Steel From India: Revocation of the Antidumping "
        "Duty Order"))
    assert view.reversed_by_status is True
    assert "exporter" in view.benefiting
    assert "domestic_producer" in view.constrained


def test_the_frame_fields_are_actually_populated():
    """They existed for the whole project and were always empty."""
    event = event_for("Chromium Trioxide From India: Antidumping Duty Order")
    assert event.frame.beneficiaries, "beneficiaries is still empty"
    assert event.frame.constrained_parties, "constrained_parties is still empty"


# --------------------------------------------- what it refuses to claim

def test_the_net_effect_is_never_computed():
    """Which side dominates needs sizes this system does not hold."""
    view = opposing_parties(
        event_for("Chromium Trioxide From India: Antidumping Duty Order"))
    net = view.describe()["net_effect"]
    assert "NOT COMPUTED" in net
    assert "sizes this system does not hold" in net


def test_a_hazard_has_no_beneficiary():
    """An earthquake harms without benefiting anyone in particular, and
    inventing a beneficiary would be worse than saying nothing."""
    story = Story(story_id="s", source_id="x", observation_id="o",
                  title="M 6.2 - 40 km off the coast", url="u", body=None,
                  timing=Timing(first_seen_at=SEEN), syndication_group="g",
                  metadata={"source_kind_hint": "hazard_agency"})
    master, _ = load_master_data()
    event = list(extract_events([story], master))[0].event
    view = opposing_parties(event)
    assert view.benefiting == ()
    assert view.constrained == ()
    assert view.is_two_sided is False


def test_roles_are_named_not_companies():
    """It says "an exporter is constrained", not which companies those are.
    Naming them needs the exposure registry and its citations."""
    view = opposing_parties(
        event_for("Chromium Trioxide From India: Antidumping Duty Order"))
    for role in view.constrained + view.benefiting:
        assert "_" in role or role.islower(), f"{role!r} looks like a name"


def test_every_class_states_its_mechanism():
    """A side without a mechanism is an assertion about who wins."""
    for event_type, (constrained, benefiting, mechanism) in OPPOSING_ROLES.items():
        assert mechanism, f"{event_type} has no mechanism"
        assert constrained and benefiting, f"{event_type} is one-sided"


@pytest.mark.parametrize("event_type", sorted(OPPOSING_ROLES))
def test_no_role_is_both_constrained_and_benefiting(event_type):
    constrained, benefiting, _mechanism = OPPOSING_ROLES[event_type]
    assert not (set(constrained) & set(benefiting)), (
        f"{event_type} puts a role on both sides")


# ------------------------------------------------------ it reaches the UI

def test_the_rail_item_carries_both_sides():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    view = (root / "seraph/dashboard/news_view.py").read_text(encoding="utf-8")
    assert "opposing=_opposing_view(event)" in view
    bridge = (root / "seraph/dashboard/console_component/bridge.js").read_text(
        encoding="utf-8")
    assert "Constrains:" in bridge and "Benefits:" in bridge
    assert "net_effect" in bridge, "the UI shows sides without the caveat"
