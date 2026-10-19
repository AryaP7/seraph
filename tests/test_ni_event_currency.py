"""Event expiry — and the asymmetry that makes it more than an age cutoff.

`aggregate_by` had no notion of age. A tariff announcement from six months ago
rolled into the sector panel with exactly the weight of one from this morning,
and the panel presented both as "what is happening".

Two things could have been built. Only one is honest.

**Not built: magnitude decay.** Nothing here carries a loss estimate — every
edge is unsized, every direction qualitative. Multiplying a non-existent
quantity by a half-life nobody fitted manufactures precision from a constant
chosen to look reasonable.

**Built: a declared relevance horizon per event class.** How long news stays
current is a property of what kind of news it is, and it can be argued with.

The asymmetry these tests exist for: **a measure in force does not expire.**
An anti-dumping duty order from 2024 that has not been revoked is current
today — it is currently costing an exporter money. An earthquake from 2024 is
not.
"""
from __future__ import annotations

import pytest

from seraph.news.currency import (
    DEFAULT_HORIZON_DAYS,
    HORIZONS_DAYS,
    currency,
    horizon_days,
    partition,
)
from seraph.news.extraction import extract_events
from seraph.news.model import Place, Story, Timing
from seraph.news.registry import MasterData

NOW = "2026-10-18T09:00:00+05:30"


def registry() -> MasterData:
    data = MasterData()
    data.add_place(Place("in", "India", "country", iso_code="IND",
                         lat=22.0, lon=79.0))
    return data


def event_for(title: str, seen_at: str, *, hazard: bool = False):
    # `physical_hazard` is assigned from the SOURCE's kind hint, not from the
    # title — a hazard agency's feed is a hazard feed whatever it writes.
    story = Story(story_id="s1", source_id="federal_register",
                  observation_id="o1", title=title,
                  url="https://example.invalid/1", body=None,
                  timing=Timing(first_seen_at=seen_at), syndication_group="g1",
                  metadata={"source_kind_hint": "hazard_agency"} if hazard else {})
    results = list(extract_events([story], registry()))
    assert results and results[0].event is not None, title
    return results[0].event


def days_before(n: int) -> str:
    from datetime import datetime, timedelta
    moment = datetime.strptime(NOW, "%Y-%m-%dT%H:%M:%S%z") - timedelta(days=n)
    return moment.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + moment.strftime("%z")[-2:]


# ------------------------------------------ the asymmetry that matters most

DUTY_ORDER = ("Oleoresin Paprika From India: Antidumping Duty Order and "
              "Countervailing Duty Order")


def test_a_measure_in_force_never_expires():
    """A duty order from two years ago is still costing an exporter money. It
    is not a report of something that happened; it is a measure operating."""
    event = event_for(DUTY_ORDER, days_before(730))
    assert event.frame.policy_status == "effective"
    state = currency(event, NOW)
    assert state["current"] is True
    assert state["band"] == "in_force"
    assert "does not age out" in state["basis"]


def test_a_hazard_from_the_same_date_does_expire():
    """The contrast. Same age, different kind of fact."""
    event = event_for("M 6.2 - 40 km off the coast", days_before(730),
                      hazard=True)
    state = currency(event, NOW)
    assert state["current"] is False
    assert state["band"] == "historic"


def test_a_repealed_measure_is_no_longer_in_force():
    """`in_force` must mean *applies now*, not *was an instrument once*."""
    event = event_for("Certain Hot-Rolled Steel From India: Revocation of the "
                      "Antidumping Duty Order", days_before(730))
    assert event.frame.policy_status == "repealed"
    state = currency(event, NOW)
    assert state["band"] != "in_force"
    assert state["current"] is False


# ----------------------------------------------------------- the bands

@pytest.mark.parametrize("age,band", [
    (1, "fresh"), (5, "recent"), (10, "ageing"), (40, "historic"),
])
def test_bands_follow_the_declared_horizon(age, band):
    """physical_hazard is declared at 14 days: fresh <= 3.5, recent <= 7,
    ageing <= 14, historic beyond."""
    event = event_for("M 6.2 - 40 km off the coast", days_before(age),
                      hazard=True)
    assert event.event_type == "physical_hazard"
    assert currency(event, NOW)["band"] == band


def test_every_band_states_its_reason():
    """A filter that drops an event without saying why cannot be audited."""
    event = event_for("M 6.2 - 40 km off the coast", days_before(40),
                      hazard=True)
    state = currency(event, NOW)
    assert "relevance horizon" in state["basis"]
    assert str(state["horizon_days"]) in state["basis"]


def test_an_unknown_class_gets_a_short_default_not_an_unlimited_one():
    """An unrecognised event is the one we understand least. Carrying it
    forever is worse than ageing it out where it can be noticed."""
    assert DEFAULT_HORIZON_DAYS == 90
    assert "other" not in HORIZONS_DAYS
    event = event_for("Notice of Public Meeting; Pacific Fishery Council",
                      days_before(1))
    assert event.event_type == "other"
    assert horizon_days(event) == DEFAULT_HORIZON_DAYS


def test_horizons_are_declared_in_one_place():
    """Scattering `if age >` through the aggregation is how a horizon becomes
    unarguable. Each entry here is a claim someone can dispute."""
    assert HORIZONS_DAYS["physical_hazard"] < HORIZONS_DAYS["policy_rate_decision"]
    assert (HORIZONS_DAYS["official_speech"]
            < HORIZONS_DAYS["trade_remedy_determination"])


# ------------------------------------------------------- nothing is deleted

def test_an_event_with_no_age_is_kept_not_dropped():
    """Dropping on an unknown is how a corpus silently narrows."""
    story = Story(story_id="s", source_id="x", observation_id="o",
                  title="Something happened", url="https://example.invalid/1",
                  body=None, timing=Timing(), syndication_group="g")
    event = list(extract_events([story], registry()))[0].event
    state = currency(event, NOW)
    assert state["current"] is True
    assert state["band"] == "unknown_age"


@pytest.mark.parametrize("lifecycle", ["superseded", "retracted"])
def test_a_superseded_or_retracted_event_is_out_immediately(lifecycle):
    from dataclasses import replace
    event = replace(event_for(DUTY_ORDER, days_before(1)), lifecycle=lifecycle)
    state = currency(event, NOW)
    assert state["current"] is False
    assert state["band"] == "dead"


def test_partition_reports_what_it_excluded():
    """A caller must be able to say how many events it set aside and why,
    rather than silently narrowing."""
    events = [event_for(DUTY_ORDER, days_before(730)),
              event_for("M 6.2 - 40 km off the coast", days_before(730),
                        hazard=True)]
    split = partition(events, NOW)
    assert len(split["current"]) == 1
    assert len(split["expired"]) == 1
    assert len(split["states"]) == 2, "every event keeps a stated reason"
    assert "retained in the corpus" in split["note"]


def test_no_magnitude_is_decayed_anywhere():
    """The thing deliberately NOT built. If a decay factor ever appears, it is
    multiplying a quantity this system does not have."""
    import pathlib
    source = (pathlib.Path(__file__).resolve().parents[1]
              / "seraph/news/currency.py").read_text(encoding="utf-8")
    assert "half_life" not in source and "half-life" not in source.split("**")[0]
    assert "Not built: magnitude decay" in source
