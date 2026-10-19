"""Replay versioning — source-to-place mappings were exempt from `as_of`.

`MasterData.as_of(t)` filters entities, places and assets by `known_from`, and
edges by `visible_at`. It then passed `source_places` through untouched, which
leaked hindsight into replay twice:

1. A mapping curated today — "the Federal Register issues from Washington" —
   appeared in a replay of a date before anyone had established it. The globe
   drew a provenance marker the system could not have drawn then.

2. Worse because silent: `as_of` *does* filter places. A source_place pointing
   at a filtered-out place survived, so the registry held a mapping to a place
   it did not contain. Nothing raises — the marker loses its coordinates, and
   an absent marker is indistinguishable from an absent source.
"""
from __future__ import annotations

import pytest

from seraph.news.model import Place
from seraph.news.registry import MasterData, load_master_data

EARLY = "2020-01-01T00:00:00+05:30"
LATE = "2026-10-18T09:00:00+05:30"


def registry() -> MasterData:
    data = MasterData()
    data.add_place(Place("us", "United States", "country", iso_code="USA",
                         lat=39.76, lon=-98.5))
    # A place nobody had curated until 2026.
    data.add_place(Place("in_mh_mumbai", "Mumbai", "city", lat=19.07, lon=72.87,
                         known_from="2026-06-01T00:00:00+05:30"))
    return data


# ------------------------------------------------- the mapping is versioned

def test_a_mapping_curated_later_is_absent_from_an_earlier_replay():
    data = registry()
    data.add_source_place(source_id="federal_register", place_id="us",
                          basis="issuing_office", source="ref",
                          known_from="2026-10-01T00:00:00+05:30")
    assert "federal_register" in data.as_of(LATE).source_places
    assert "federal_register" not in data.as_of(EARLY).source_places


def test_a_mapping_without_known_from_is_always_known():
    """Optional on purpose: the rows curated at the start of the project have
    no date, and inventing one would be worse than treating them as known."""
    data = registry()
    data.add_source_place(source_id="federal_register", place_id="us",
                          basis="issuing_office", source="ref")
    assert "federal_register" in data.as_of(EARLY).source_places


# ------------------------------------- the silent half: dangling references

def test_a_mapping_to_an_unknown_place_is_dropped_not_dangled():
    """Mumbai is not known until 2026. A mapping pointing at it must not
    survive an earlier `as_of`, or the registry holds a reference to a place
    it does not contain."""
    data = registry()
    data.add_source_place(source_id="rbi_press_releases",
                          place_id="in_mh_mumbai", basis="issuing_office",
                          source="ref")
    early = data.as_of(EARLY)
    assert "in_mh_mumbai" not in early.places
    assert "rbi_press_releases" not in early.source_places


@pytest.mark.parametrize("timestamp", [EARLY, LATE, "2026-06-02T00:00:00+05:30"])
def test_no_as_of_ever_produces_a_dangling_mapping(timestamp):
    """The invariant, stated directly. A dangling mapping does not raise — the
    marker simply loses its coordinates — so it has to be asserted."""
    data = registry()
    data.add_source_place(source_id="a", place_id="us", basis="jurisdiction",
                          source="ref")
    data.add_source_place(source_id="b", place_id="in_mh_mumbai",
                          basis="issuing_office", source="ref")
    snapshot = data.as_of(timestamp)
    dangling = [sp for sp in snapshot.source_places.values()
                if sp["place_id"] not in snapshot.places]
    assert dangling == []


def test_the_real_registry_has_no_dangling_mapping_at_any_epoch():
    """Against the curated files rather than a fixture."""
    master, report = load_master_data()
    assert report.get("errors") == []
    for timestamp in (EARLY, "2024-01-01T00:00:00+05:30", LATE):
        snapshot = master.as_of(timestamp)
        dangling = [sp for sp in snapshot.source_places.values()
                    if sp["place_id"] not in snapshot.places]
        assert dangling == [], f"dangling mapping at {timestamp}: {dangling}"


def test_an_earlier_epoch_is_a_strict_subset():
    """A replay cannot know more than a later one. If this ever fails, some
    collection is being filtered the wrong way round."""
    master, _ = load_master_data()
    early, late = master.as_of(EARLY), master.as_of(LATE)
    assert set(early.places) <= set(late.places)
    assert set(early.entities) <= set(late.entities)
    assert set(early.assets) <= set(late.assets)
    assert set(early.source_places) <= set(late.source_places)


def test_the_curated_loader_reads_known_from():
    """The column is optional, but it must be read when present, or the
    versioning silently never applies to real data."""
    import pathlib
    source = (pathlib.Path(__file__).resolve().parents[1]
              / "seraph/news/registry.py").read_text(encoding="utf-8")
    loader = source.split("source_places.csv", 1)[1][:800]
    assert "known_from" in loader
