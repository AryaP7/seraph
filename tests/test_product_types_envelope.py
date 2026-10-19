"""PRODUCT-CONTRACTS §1 — the metadata envelope enforces its own four rules.

These are not shape tests. Each one is the rule the product keeps getting
wrong when it is only written down: unknown rendered as zero, a replay reading
tomorrow's news, a fabricated placeholder entering arithmetic, and a status
that lives on the panel instead of on the datum.
"""
from __future__ import annotations

import pytest

from seraph.product_types import (
    Coverage,
    Envelope,
    InformationClock,
    Provenance,
    ReplayBoundViolation,
    SourceRef,
    Timing,
    Uncertainty,
    content_id,
    derived,
    estimated,
    observed,
    preview,
    unavailable,
)
from seraph.product_types.envelope import PreviewUsedAsInput, ValueUnavailable

PROV = Provenance(producer="test.producer", producer_version="1.0.0")
SRC = SourceRef(source_id="src_a", reference="https://example.test/doc",
                content_hash="a" * 64, retrieved_at="2026-01-02T10:00:00+05:30")


# ------------------------------------------- rule 1: unknown is never zero


def test_an_unavailable_datum_carries_no_value_at_all():
    e = unavailable("sector_stress", absence="transient", reason="feed outage")
    assert e.value is None and e.is_available is False
    with pytest.raises(ValueUnavailable):
        e.value_for_calculation()


def test_an_unavailable_datum_cannot_smuggle_a_value():
    with pytest.raises(ValueError, match="Absent is not zero"):
        Envelope(kind="x", status="unavailable", value=0.0,
                 absence="structural", absence_reason="no coverage")


def test_absence_type_must_be_declared():
    with pytest.raises(ValueError, match="never inferred"):
        Envelope(kind="x", status="unavailable", absence=None, absence_reason="?")
    with pytest.raises(ValueError, match="never inferred"):
        Envelope(kind="x", status="unavailable", absence="maybe", absence_reason="?")


def test_absence_is_meaningless_on_an_available_datum():
    with pytest.raises(ValueError, match="only meaningful when unavailable"):
        Envelope(kind="x", status="derived", value=1, provenance=PROV,
                 absence="transient")


def test_display_renders_absent_as_the_caller_chooses_not_as_zero():
    e = unavailable("x", absence="structural", reason="no coverage")
    assert e.value_for_display() is None
    assert e.value_for_display(absent="—") == "—"


def test_coverage_separates_measured_quiet_from_never_looked_at():
    checked = Coverage(population="nifty500 sectors", covered=12, total=12)
    partial = Coverage(population="nifty500 sectors", covered=3, total=12,
                       uncovered=("pharma", "auto"))
    assert checked.is_complete and checked.fraction == 1.0
    assert not partial.is_complete and partial.fraction == 0.25
    assert "pharma" in partial.uncovered


# -------------------------------------------- rule 2: the replay bound


def test_first_seen_not_published_is_the_replay_bound():
    timing = Timing(published_at="2026-01-02T09:00:00+05:30",
                    first_seen_at="2026-01-02T11:40:00+05:30")
    e = observed("story", "text", sources=[SRC], timing=timing)
    # Published before the decision, but not yet RECEIVED: withheld.
    assert e.visible_at("2026-01-02T10:00:00+05:30") is False
    assert e.visible_at("2026-01-02T12:00:00+05:30") is True


def test_receiving_before_publication_is_rejected_as_incoherent():
    with pytest.raises(ValueError, match="precedes published_at"):
        Timing(published_at="2026-01-02T11:00:00+05:30",
               first_seen_at="2026-01-02T09:00:00+05:30")


def test_a_datum_with_no_external_source_has_nothing_to_withhold():
    e = derived("csrs", 0.4, provenance=PROV)
    assert e.visible_at("1999-01-01T00:00:00+05:30") is True


def test_the_information_clock_filters_a_stream():
    items = [
        observed("story", "early", sources=[SRC],
                 timing=Timing(first_seen_at="2026-01-02T09:00:00+05:30")),
        observed("story", "late", sources=[SRC],
                 timing=Timing(first_seen_at="2026-01-02T18:00:00+05:30")),
    ]
    clock = InformationClock("2026-01-02T12:00:00+05:30")
    kept = clock.filter(items, lambda e: e.timing)
    assert [e.value for e in kept] == ["early"]


def test_a_strict_clock_raises_rather_than_silently_dropping():
    late = observed("story", "late", sources=[SRC],
                    timing=Timing(first_seen_at="2026-01-02T18:00:00+05:30"))
    strict = InformationClock("2026-01-02T12:00:00+05:30", strict=True)
    with pytest.raises(ReplayBoundViolation):
        strict.filter([late], lambda e: e.timing)


# ------------------------------- rule 3: preview never enters a calculation


def test_preview_refuses_to_be_an_input_but_still_displays():
    e = preview("sector_stress", 0.72)
    with pytest.raises(PreviewUsedAsInput, match="must never enter"):
        e.value_for_calculation()
    assert e.value_for_display() == 0.72
    assert e.to_payload()["status"] == "preview"


def test_a_real_datum_reads_out_normally():
    assert derived("csrs", 0.4, provenance=PROV).value_for_calculation() == 0.4


# ---------------------------- rule 4: the status travels with the datum


def test_every_payload_carries_its_status_and_schema_version():
    for e in (derived("a", 1, provenance=PROV),
              preview("b", 2),
              unavailable("c", absence="structural", reason="none")):
        payload = e.to_payload()
        assert payload["status"] == e.status
        assert payload["schemaVersion"] == 1
    assert "value" not in unavailable(
        "c", absence="structural", reason="none").to_payload()


# --------------------------------------------- producers and uncertainty


def test_a_derived_datum_must_name_its_producer():
    with pytest.raises(ValueError, match="must name its producer"):
        Envelope(kind="x", status="derived", value=1)


def test_an_observed_datum_must_name_a_source():
    with pytest.raises(ValueError, match="must name at least one source"):
        Envelope(kind="x", status="observed", value=1)


def test_an_estimate_must_say_what_its_uncertainty_means():
    with pytest.raises(ValueError, match="what its uncertainty means"):
        Envelope(kind="x", status="estimate", value=1, provenance=PROV)
    with pytest.raises(ValueError, match="must state what it means"):
        Uncertainty(kind="interval", meaning="  ", lower=0, upper=1)
    good = estimated("x", 0.5, provenance=PROV,
                     uncertainty=Uncertainty(kind="interval", lower=0.3, upper=0.7,
                                             meaning="90% conditional interval"))
    assert good.to_payload()["uncertainty"]["meaning"].startswith("90%")


def test_an_inverted_interval_is_rejected():
    with pytest.raises(ValueError, match="inverted"):
        Uncertainty(kind="interval", meaning="m", lower=0.9, upper=0.1)


# ---------------------------------------------------------- identity


def test_the_same_content_gives_the_same_id():
    a = derived("csrs", 0.4, provenance=PROV)
    b = derived("csrs", 0.4, provenance=PROV)
    assert a.id == b.id == content_id(*[a.kind, a.status, a.revision, a.unit,
                                        a.value, None,
                                        dict(producer=PROV.producer,
                                             producer_version=PROV.producer_version,
                                             inputs=(), run_id=None, model_id=None,
                                             scenario_id=None), []])


def test_different_content_gives_a_different_id():
    assert derived("csrs", 0.4, provenance=PROV).id != \
        derived("csrs", 0.41, provenance=PROV).id


def test_a_revision_records_what_it_supersedes_and_does_not_mutate():
    first = derived("csrs", 0.4, provenance=PROV)
    second = first.revise(value=0.44)
    assert first.value == 0.4 and first.revision == 1
    assert second.value == 0.44 and second.revision == 2
    assert second.supersedes == first.id and second.id != first.id


def test_marking_stale_keeps_the_value_and_adds_the_reason():
    stale = derived("csrs", 0.4, provenance=PROV).mark_stale("older than 24h")
    assert stale.status == "stale" and stale.value == 0.4
    assert "older than 24h" in stale.limitations
    # A preview or an absent datum has nothing to go stale.
    assert preview("x", 1).mark_stale("r").status == "preview"
