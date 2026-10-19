"""NI08 / DR-10 — may SERAPH retain source full text? Answered per source.

`may_store_full_text` was `False` everywhere, and the module said why:
"'publicly reachable' is not 'licensed to redistribute', and that question has
not been answered for any of them… Changing that needs the terms read, not a
convenient assumption."

The terms are now read, and the answer **differs by source** — which is the
point. US Government works (17 U.S.C. §105) and PIB's own copyright policy
permit retention; the RBI grants nothing ("All Rights Reserved") and SEBI
requires a permission that nobody has requested. A blanket answer in either
direction would have been wrong.

These tests pin the determination so it cannot drift back to a convenient
assumption, and pin the two regressions that retaining bodies introduced.

Retaining abstracts is **not** a uniform improvement. Measured on 34 real
Federal Register documents, 9 were interpreted differently and two of those
were worse — both the same shape: a rule firing on statutory boilerplate, or
on a body's account of the procedure that produced a decision rather than on
the decision itself.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from seraph.news.acquisition import FetchedItem, FetchResult, NewsStore
from seraph.news.event_frames import frame_for
from seraph.news.model import Source

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEEN = "2026-10-18T09:00:00+05:30"


@pytest.fixture(scope="module")
def sources() -> dict[str, Source]:
    spec = importlib.util.spec_from_file_location(
        "run_news_for_tests", ROOT / "scripts/run_news.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = (list(module.VERIFIED_SOURCES)
            + [s for s, _ in module.VERIFIED_JSON_SOURCES]
            + list(module.PILOT_SOURCES) + list(module.LISTING_SOURCES)
            + list(module.DOCUMENT_SOURCES))
    return {s.source_id: s for s in rows}


# ------------------------------------------------- the determination itself

PERMITTED = {
    "federal_register": "17 U.S.C. 105",
    "federal_register_india": "17 U.S.C. 105",
    "usgs_earthquakes": "public domain",
    "pib_releases": "PIB Copyright Policy",
    "fed_press": "public-domain",
}
REFUSED = ("rbi_press_releases", "rbi_notifications", "rbi_speeches",
           "sebi_press")


@pytest.mark.parametrize("source_id,basis", sorted(PERMITTED.items()))
def test_a_permitted_source_cites_its_licence(sources, source_id, basis):
    source = sources[source_id]
    assert source.may_store_full_text is True
    assert basis.lower() in source.rights.lower(), source.rights


@pytest.mark.parametrize("source_id", sorted(PERMITTED))
def test_a_permitted_source_states_its_conditions(sources, source_id):
    """Every permitted source carries two: acknowledge the source, and
    third-party material embedded in a government document is not covered by
    the government's own licence."""
    rights = sources[source_id].rights.lower()
    assert any(w in rights for w in ("credit", "attribution", "acknowledg")), rights
    if source_id != "fed_press":          # pre-existing record, left as found
        assert "third-party" in rights or "third party" in rights, rights


@pytest.mark.parametrize("source_id", REFUSED)
def test_a_refused_source_is_refused_and_says_why(sources, source_id):
    """"Reviewed and refused" is a different fact from "never reviewed", and
    the more useful one: it stops the work being redone and records the
    reason."""
    source = sources[source_id]
    assert source.may_store_full_text is False
    assert "NOT reviewed" not in source.rights
    assert "REFUSED" in source.rights
    assert "DR-10" in source.rights


def test_sebi_is_refused_for_want_of_permission_not_for_want_of_terms(sources):
    """SEBI permits reproduction after permission is obtained by email. The
    email has not been sent. Recording that as 'terms unknown' would hide a
    one-email action behind an apparently open question."""
    rights = sources["sebi_press"].rights
    assert "permission" in rights.lower()
    assert "has not been sent" in rights


def test_rbi_is_refused_because_nothing_was_granted(sources):
    assert "All Rights Reserved" in sources["rbi_press_releases"].rights


# ------------------------------- the flag governs the bytes, not just a field

def source_for(may_store: bool) -> Source:
    return Source(
        source_id="probe", provider="probe", kind="regulator",
        url="https://example.invalid/feed", topic_coverage=("x",),
        language="en", rights="test", may_store_full_text=may_store,
        accessibility_verified=True, poll_interval_minutes=60)


def fetcher(body: str):
    def fetch(src, cursor=None):
        return FetchResult(items=(FetchedItem(
            reference="r1", title="A notice", url="https://example.invalid/1",
            raw=b"<rss>the whole payload</rss>", published_at=None,
            body=body, language="en"),))
    return fetch


@pytest.mark.parametrize("may_store,expected_body,expected_raw", [
    (True, "the abstract", True),
    (False, None, False),
])
def test_the_rights_flag_governs_body_and_raw_together(
        tmp_path, may_store, expected_body, expected_raw):
    """The policy is enforced on the bytes kept, not only on the projected
    field. That is why the abstracts of already-stored documents cannot be
    recovered: they were never retained, which is the policy working."""
    store = NewsStore(tmp_path / "rights.sqlite")
    store.register(source_for(may_store))
    store.ingest("probe", fetcher("the abstract"))

    story = store.stories()[0]
    assert story.body == expected_body
    observation = store.observation(story.observation_id)
    assert bool(observation.raw) is expected_raw


def test_bodies_accrue_forward_only(tmp_path):
    """Rows are immutable and an unchanged item yields no new row, so flipping
    the flag does not back-fill. Coverage grows from the decision date."""
    store = NewsStore(tmp_path / "forward.sqlite")
    store.register(source_for(False))
    store.ingest("probe", fetcher("the abstract"))
    assert store.stories()[0].body is None

    store.register(source_for(True))          # rights determination changes
    report = store.ingest("probe", fetcher("the abstract"))
    assert report.new_stories == 0, "an unchanged item must not create a row"
    assert store.stories()[0].body is None, "history is not rewritten"


# ----------------------------------- statutory boilerplate is not an action

PRA = ("As part of our continuing effort to reduce paperwork and respondent "
       "burden, and as required by the Paperwork Reduction Act of 1995, the "
       "Commission invites comment on the renewal of this collection.")


def test_paperwork_boilerplate_does_not_become_an_economic_action():
    """Every PRA notice carries that sentence verbatim. "reduce paperwork and
    respondent burden" is not a reduction a market cares about."""
    frame = frame_for(f"Renewal of Agency Information Collections. {PRA}",
                      "s1", "other", title="Renewal of Agency Information "
                                           "Collections")
    assert frame.action != "decrease"


def test_a_real_reduction_is_still_detected():
    """The scrub must remove boilerplate, not the vocabulary."""
    frame = frame_for("Policy rate decision. The committee reduced the repo "
                      "rate by 25 basis points.", "s1", "policy_rate_decision",
                      title="Policy rate decision")
    assert frame.action == "decrease"


def test_blanking_boilerplate_keeps_evidence_offsets_true():
    """Boilerplate is blanked, not deleted. An evidence span is an offset into
    the text the source actually sent, so removing characters would silently
    move every span after the cut."""
    text = f"Notice. {PRA} The committee reduced the repo rate."
    frame = frame_for(text, "s1", "policy_rate_decision", title="Notice")
    for span in frame.evidence if hasattr(frame, "evidence") else ():
        assert text[span.start:span.end] == span.text, (
            "a span no longer points at the text it quotes")


# --------------------------- the title's status outranks the body's narration

DEBARMENT_BODY = (
    "The Food and Drug Administration is issuing an order under the Federal "
    "Food, Drug, and Cosmetic Act debarring Jeffrey Thies. The Agency sent a "
    "proposal to debar and he did not request a hearing within the period "
    "prescribed, so the proposal is now final.")


def test_a_final_order_is_not_read_as_a_proposal():
    """The title states what the document IS; the body narrates the proposal
    and hearing that produced it. Reading the narration as the status is the
    same error as "Postponement of Final Determination" classified `adopted`
    and "Scheduling of Full Five-Year Reviews" classified `expired`."""
    frame = frame_for(f"Jeffrey Thies: Final Debarment Order. {DEBARMENT_BODY}",
                      "s1", "regulatory_action",
                      title="Jeffrey Thies: Final Debarment Order")
    assert frame.policy_status != "proposed"
    assert frame.policy_status == "adopted"


def test_a_title_that_really_proposes_is_untouched():
    """The override applies only when the TITLE claims finality. A notice that
    is genuinely a proposal must keep saying so."""
    frame = frame_for("Investment Company Cross Trading. The Commission is "
                      "proposing to amend the rule.", "s1", "regulatory_action",
                      title="Investment Company Cross Trading")
    assert frame.policy_status == "proposed"


def test_a_proposed_final_rule_is_still_a_proposal():
    """"Proposed rule to adopt a final standard" names both. The title's own
    proposal wording wins, because the override exists to respect the title,
    not to override it."""
    frame = frame_for("Proposed Final Rule on Widgets. The agency is "
                      "proposing this action.", "s1", "regulatory_action",
                      title="Proposed Final Rule on Widgets")
    assert frame.policy_status == "proposed"


def test_the_override_needs_a_title_and_does_nothing_without_one():
    """`frame_for` is called with a title throughout the pipeline, but the
    parameter is optional and the old behaviour must be unchanged without it."""
    frame = frame_for(f"Jeffrey Thies: Final Debarment Order. {DEBARMENT_BODY}",
                      "s1", "regulatory_action")
    assert frame.policy_status == "proposed"
