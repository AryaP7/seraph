# Integration tests for the completed-session CSRS path (C8/C9).
"""SERAPH must be able to produce its central score from eligible data.

The pillars were computed daily and nothing fused them: the fusion lived only
in the bar-driven live loop, so a composite existed only while the market was
open. `scripts/score_completed_sessions.py` closes that by driving the
documented `ArchiveReplay` onto the same `InferenceService.process()` the live
loop uses.

These tests pin the two things that matter about it:

* it produces a **genuine** score — same engine, same mask, same gate;
* it never lets that score be mistaken for a **current** reading.
"""
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "prototype_runs" / "live.sqlite"

pytestmark = pytest.mark.skipif(
    not STORE.exists(), reason="no live store; run_daily.py writes its vintages")


@pytest.fixture(scope="module")
def scorer():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import score_completed_sessions as s
    return s


@pytest.fixture(scope="module")
def replayed(scorer):
    """Every session replayed once, shared across the tests."""
    by_day = scorer.read_vintages(STORE)
    if not by_day:
        pytest.skip("the live store holds no daily vintage")
    return by_day, scorer.score_sessions(by_day)


# ==========================================================================
# the engine produces a genuine score
# ==========================================================================
def test_the_official_engine_scores_completed_sessions(replayed):
    """1. The CSRS engine generates a score from eligible market data."""
    _, results = replayed
    scored = [r for _, r in results if r.csrs is not None]
    assert scored, (
        "no session produced a composite; SERAPH cannot generate its central "
        "score from its own vintages")
    assert len(scored) == len(results), (
        f"only {len(scored)} of {len(results)} sessions produced a composite")


def test_the_score_is_in_range_and_carries_its_mask(replayed):
    _, results = replayed
    _, latest = results[-1]
    point = latest.csrs
    assert point is not None
    assert 0.0 <= float(point.csrs) <= 1.0, "a CSRS is a 0..1 composite"
    assert len(point.mask) == 3, "the D2 mask is positional over PILLAR_ORDER"
    assert any(point.mask), (
        "a composite with an all-false mask would be a score computed from "
        "no eligible pillar")


def test_partial_pillar_coverage_is_the_approved_behaviour(replayed):
    """The methodology supports it explicitly; this is not a workaround.

    D2 excludes an absent pillar from the mask and renormalises the rest, and
    `_warmup_complete_at` excludes structural absences from the warm-up
    requirement. On this installation Hamilton is a standing structural
    absence, so the composite is carried by the remaining pillars — and the
    mask records exactly which.
    """
    from seraph.shared_types import PILLAR_ORDER

    _, results = replayed
    _, latest = results[-1]
    mask = dict(zip(PILLAR_ORDER, latest.csrs.mask))
    diagnostics = latest.pillar_diagnostics

    excluded = [p for p, on in mask.items() if not on]
    assert excluded, "this installation should have at least one absent pillar"
    for pillar in excluded:
        assert pillar in diagnostics, (
            f"{pillar} was excluded from the mask with no diagnostic saying why")

    shapley = dict(zip(PILLAR_ORDER, latest.csrs.shapley))
    for pillar, on in mask.items():
        if not on:
            assert shapley[pillar] == 0.0, (
                f"{pillar} is out of the mask but carries a non-zero "
                f"contribution")


def test_an_absent_pillar_is_never_substituted(replayed):
    """A declared absence must not become a number."""
    by_day, results = replayed
    day, latest = results[-1]
    for pillar, entry in by_day[day].items():
        if entry.get("score_eligible"):
            continue
        diagnostic = latest.pillar_diagnostics.get(pillar) or {}
        vintage = diagnostic.get("vintage") or {}
        assert vintage.get("value") in (None, ""), (
            f"{pillar} declared an absence but a value reached the engine")


# ==========================================================================
# it is never mistaken for a current reading
# ==========================================================================
def test_the_score_is_withheld_from_being_called_current(replayed):
    """4. Historical replay remains separately accessible and labelled.

    Every batch decision is `historical_replay`, so the publication gate must
    refuse it as a current market reading and say why.
    """
    _, results = replayed
    _, latest = results[-1]
    assert latest.request.mode == "historical_replay"
    assert latest.publication.current_allowed is False, (
        "a replay of a completed session must never be publishable as a "
        "current market reading")
    assert latest.publication.reasons, "a refusal must carry its reasons"


def test_the_decision_carries_its_own_source_session_timestamp(replayed):
    """2. The score is saved with its actual source-session timestamp."""
    by_day, results = replayed
    day, latest = results[-1]
    assert latest.request.as_of.date().isoformat() == day, (
        "the decision must be stamped with the session it scored, not the "
        "wall clock")
    assert latest.request.as_of.tzinfo is not None, "timestamps are IST-explicit"


def test_batch_decisions_never_land_on_the_live_stream():
    """The one substitution the mode discipline exists to prevent."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import score_completed_sessions as s
    from seraph.live.store import LiveStore

    assert s.STREAM == "replay"
    live = LiveStore(STORE, stream_id="live").latest_decision()
    assert live is None or not str(live.get("decision_id", "")).startswith(
        "archive:"), (
        "a batch-scored session reached the live stream, where it could be "
        "served as a current reading")


def test_the_committed_decision_is_readable_and_matches(replayed):
    """The score the frontend reads is the score the engine produced."""
    from seraph.live.store import LiveStore

    _, results = replayed
    _, latest = results[-1]
    stored = LiveStore(STORE, stream_id="replay").latest_decision()
    if stored is None:
        pytest.skip("nothing committed yet; run with --commit")
    point = ((stored.get("payload") or {}).get("csrs")) or {}
    if stored.get("decision_id") != latest.request.decision_id:
        pytest.skip("the store holds a different session than this replay")
    assert point.get("csrs") == pytest.approx(float(latest.csrs.csrs)), (
        "the committed score differs from what the engine produced")
    assert stored.get("publication_state") == "withheld"


# ==========================================================================
# the frontend reads it honestly
# ==========================================================================
def test_the_frontend_surfaces_the_score_without_claiming_it_is_current():
    """3. CURRENT displays the latest valid score without misrepresenting it."""
    from seraph.dashboard.redesign import current_session as CS

    session = CS.latest_session(STORE)
    composite = CS.composite_status(session, STORE)
    if not composite.get("available"):
        pytest.skip("no committed score to surface")

    assert isinstance(composite["value"], float)
    assert composite["publishable"] is False
    assert composite["publication_state"] == "withheld"
    assert composite["as_of"], "the reading must carry its session timestamp"


def test_the_current_view_states_the_refusal_next_to_the_number():
    """A score shown without its refusal would read as a live reading."""
    from seraph.dashboard.console_backend import prediction_surface
    from seraph.dashboard.redesign import component_views as V
    from seraph.dashboard.redesign import current_session as CS

    session = CS.latest_session(STORE)
    composite = CS.composite_status(session, STORE)
    if not composite.get("available"):
        pytest.skip("no committed score to surface")

    markup = V.current(session, composite, prediction_surface(),
                       {"market_state": "not_a_session", "why": []}, {})
    assert "not publishable as a current reading" in markup.lower()
    assert str(round(composite["value"], 3)) in markup


# ==========================================================================
# predictions keep working alongside
# ==========================================================================
def test_predictions_still_function_alongside_the_composite():
    """6. Predictions and early warnings continue functioning."""
    from seraph.dashboard.console_backend import prediction_surface

    surface = prediction_surface()
    if not surface.get("available"):
        pytest.skip("no saved prediction state")
    state = surface["state"]
    assert isinstance(state["predicted"].get("probability"), float)
    assert state["warning"].get("level")
    assert state["validation"]["status"] == "unvalidated", (
        "the validation status must not be quietly upgraded by this work")


def test_scoring_is_idempotent_on_decision_id(replayed, scorer):
    """Re-running must not create a second decision for the same session."""
    from seraph.live.store import LiveStore

    _, results = replayed
    day, latest = results[-1]
    store = LiveStore(STORE, stream_id="replay")
    before = store.latest_decision()
    if before is None:
        pytest.skip("nothing committed yet")
    scorer.commit(store, day, latest)
    after = store.latest_decision()
    assert after["decision_id"] == before["decision_id"]
    assert after["payload_hash"] == before["payload_hash"], (
        "a repeat commit changed the stored content")
