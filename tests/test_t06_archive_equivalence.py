"""T06 acceptance — raw replay and the timestamp service must agree.

The plan's gate for T06 is "raw replay and incremental results agree on
supported configuration", compared **at the same date cadence and
configuration**. These tests drive the same `originals` batches through
`InferenceSession.step()` (the date-keyed path that produced every existing
result) and through `InferenceService` via the archive adapter, and require
the reconciled state and the composite to match field by field.

What is deliberately *not* required to match is the warning list, and the
differences were categorised rather than waved past. The service omits a
carried-forward pillar from the emission batch rather than re-emitting it with
its old tau, so C8's STALE_OBSERVATION and the re-standardisation's
PARTIAL_COVERAGE echo do not recur; and an absence is worded with its typed
`absence_reason` rather than the adapter's free text. No number moves. The one
warning that *did* carry a consequence — NOISE_SATURATED, which excludes the
pillar from the mask — is re-reported by the service from the resulting state,
so the exclusion is still announced.
"""
from __future__ import annotations

import pytest

from seraph.live.archive_adapter import (
    ArchiveReplay,
    equivalence_report,
    vintages_from_originals,
)
from seraph.orchestration.prototype import InferenceSession

SESSIONS = [f"2024-01-{d:02d}" for d in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12)]


def originals(day: str, *, hawkes=None, rmt=None, hamilton=None,
              hawkes_absence="structural"):
    """The archive input contract (PRODUCT-CONTRACTS §3), one session."""
    close = f"{day}T15:30:00+05:30"

    def entry(value, absence):
        if value is None:
            return dict(score_eligible=False, value=None, absence=absence,
                        absence_reason="no_data_coverage")
        return dict(score_eligible=True, value=value,
                    information_timestamp=close)

    return {
        "hawkes": entry(hawkes, hawkes_absence),
        "rmt": entry(rmt, "transient"),
        "hamilton": entry(hamilton, "structural"),
    }


def both():
    return (InferenceSession(SESSIONS), ArchiveReplay(tuple(SESSIONS)))


# ------------------------------------------------------------- equivalence


def test_one_session_agrees():
    session, replay = both()
    report = equivalence_report(session, replay, "2024-01-02",
                                originals("2024-01-02", hawkes=0.11, rmt=0.42))
    assert report["agrees"], report["differences"]


def test_a_whole_range_agrees():
    session, replay = both()
    for i, day in enumerate(SESSIONS):
        report = equivalence_report(
            session, replay, day,
            originals(day, hawkes=0.10 + 0.002 * i, rmt=0.40 + 0.003 * i))
        assert report["agrees"], (day, report["differences"])


def test_structural_and_transient_absences_agree():
    session, replay = both()
    plan = [
        dict(hawkes=None, rmt=0.40),                      # structural hawkes
        dict(hawkes=0.11, rmt=None),                      # transient rmt
        dict(hawkes=0.12, rmt=0.41),
        dict(hawkes=None, rmt=None),                      # both absent
        dict(hawkes=0.13, rmt=0.43),
    ]
    for day, spec in zip(SESSIONS, plan):
        report = equivalence_report(session, replay, day,
                                    originals(day, **spec))
        assert report["agrees"], (day, report["differences"])


def test_a_repeated_hawkes_vintage_agrees():
    """The carry-forward case — the one place the two paths differ in method.

    The archive adapter re-supplies the same vintage each session; the
    timestamp service recognises it and omits the pillar from the batch. The
    numbers must still land in the same place.
    """
    session, replay = both()
    stuck = f"{SESSIONS[0]}T15:30:00+05:30"
    for i, day in enumerate(SESSIONS[:5]):
        batch = originals(day, hawkes=0.11, rmt=0.40 + 0.004 * i)
        batch["hawkes"]["information_timestamp"] = stuck      # never advances
        report = equivalence_report(session, replay, day, batch)
        assert report["agrees"], (day, report["differences"])


def test_the_warning_difference_is_the_suppressed_repeat_notice():
    session, replay = both()
    stuck = f"{SESSIONS[0]}T15:30:00+05:30"
    seen = []
    for i, day in enumerate(SESSIONS[:3]):
        batch = originals(day, hawkes=0.11, rmt=0.40 + 0.004 * i)
        batch["hawkes"]["information_timestamp"] = stuck
        seen.append(equivalence_report(session, replay, day, batch))
    assert all(r["agrees"] for r in seen)
    archive_text = " ".join(" ".join(r["archive_warnings"]) for r in seen)
    service_text = " ".join(" ".join(r["service_warnings"]) for r in seen)
    assert "repeated or older observation" in archive_text
    assert "repeated or older observation" not in service_text


def test_the_comparison_reports_a_real_difference_when_there_is_one():
    """Guard the guard: an equivalence check that cannot fail proves nothing.

    Six agreeing sessions first, so each pillar's ECDF has enough history for
    two different raw values to earn two different ranks; then the two paths
    are fed deliberately different data and must disagree.
    """
    session, replay = both()
    for i, day in enumerate(SESSIONS[:6]):
        report = equivalence_report(
            session, replay, day,
            originals(day, hawkes=0.10 + 0.01 * i, rmt=0.40 + 0.01 * i))
        assert report["agrees"], (day, report["differences"])

    day = SESSIONS[6]
    old = session.step(day, originals(day, hawkes=0.95, rmt=0.42), {},
                       run_id="x")
    new = replay.step(day, originals(day, hawkes=0.01, rmt=0.42))
    assert old["composite"]["csrs"] != new.csrs.model_dump()["csrs"], (
        "the comparison must be able to see a difference, or it proves "
        "nothing when it reports agreement")


# ------------------------------------------------------------- translation


def test_an_eligible_entry_becomes_an_available_vintage():
    out = vintages_from_originals(
        originals("2024-01-02", hawkes=0.11, rmt=0.42))
    by = {v.producer: v for v in out}
    assert by["hawkes"].value == 0.11
    assert by["hawkes"].input_end == by["hawkes"].emission_available_at, (
        "the archive contract carries one time per observation; the adapter "
        "must not invent a distinction it does not have")


def test_an_ineligible_entry_keeps_its_declared_absence_kind():
    out = vintages_from_originals(originals("2024-01-02", rmt=0.42))
    by = {v.producer: v for v in out}
    assert by["hawkes"].absence == "structural"
    assert by["hamilton"].absence == "structural"


def test_an_undeclared_absence_is_refused():
    batch = originals("2024-01-02", rmt=0.42)
    del batch["hawkes"]["absence"]
    with pytest.raises(ValueError, match="never inferred"):
        vintages_from_originals(batch)


def test_an_eligible_entry_without_a_timestamp_is_refused():
    batch = originals("2024-01-02", hawkes=0.11, rmt=0.42)
    batch["hawkes"]["information_timestamp"] = None
    with pytest.raises(ValueError, match="information timestamp"):
        vintages_from_originals(batch)


def test_the_adapter_uses_the_same_decision_clock():
    replay = ArchiveReplay(tuple(SESSIONS))
    result = replay.step("2024-01-02",
                         originals("2024-01-02", hawkes=0.11, rmt=0.42))
    assert result.request.as_of.isoformat() == \
        replay.clock.decision_timestamp("2024-01-02")
    assert result.request.trigger == "daily"
    assert result.request.mode == "historical_replay"
