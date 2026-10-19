"""NI03/NI11 — a trade-remedy determination is not "other", and its stage matters.

On the pilot corpus 125 of 181 events fell through to `other`, and the largest
group among them were US anti-dumping and countervailing determinations naming
Indian products — the exact class that carries a foreign measure and an Indian
product in one sentence:

    Large Diameter Graphite Electrodes From India: Preliminary Affirmative ...
    Chromium Trioxide From India: Final Affirmative Determination of Sales ...
    Oleoresin Paprika From India: Antidumping Duty Order and Countervailing ...

The plan is explicit twice over that the legal stage is the point —
"recommendation differs from imposed duty", "proposed/final/effective/
repealed states". An initiated investigation, a preliminary determination, a
final determination and an issued order are four different facts about whether
a duty exists.

What these tests also pin is what the class must NOT do: assign a direction.
A duty on an Indian product is adverse to the exporter, favourable to a
competing domestic producer and adverse to a downstream buyer. Only the
exposure registry's target role resolves that.
"""
from __future__ import annotations

import pytest

from seraph.news.extraction import extract_events
from seraph.news.model import Source, Story, Timing
from seraph.news.registry import MasterData

SEEN = "2026-10-17T09:00:00+05:30"


def story(title, body=None):
    return Story(story_id="s1", source_id="federal_register", observation_id="o1",
                 title=title, url="https://example.invalid/1", body=body,
                 timing=Timing(first_seen_at=SEEN, published_at=SEEN),
                 syndication_group="g1")


def registry() -> MasterData:
    """A registry that knows India, so resolution is exercised, not emptiness."""
    from seraph.news.model import Place

    data = MasterData()
    data.add_place(Place("in", "India", "country", iso_code="IND",
                         lat=22.0, lon=79.0))
    data.add_place(Place("us", "United States", "country", iso_code="USA",
                         lat=39.76, lon=-98.5))
    return data


def frame_for(title, body=None, master=None):
    results = list(extract_events([story(title, body)], master or registry()))
    assert results and results[0].event is not None, title
    return results[0].event


# ------------------------------------------------------- the class exists


@pytest.mark.parametrize("title", [
    "Chromium Trioxide From India: Final Affirmative Determination of Sales at"
    " Less Than Fair Value",
    "Large Diameter Graphite Electrodes From India: Preliminary Affirmative"
    " Critical Circumstances Determination in Countervailing Duty Investigation",
    "Certain Corrosion-Resistant Steel Products From the Republic of Korea:"
    " Preliminary Results of Antidumping Duty Administrative Review",
    "Oleoresin Paprika From India: Antidumping Duty Order",
    "Common Alloy Aluminum Sheet From Bahrain and India; Scheduling of Full"
    " Five-Year Reviews",
])
def test_a_trade_remedy_is_classified_as_one(title):
    assert frame_for(title).event_type == "trade_remedy_determination"


def test_a_plain_tariff_announcement_is_still_a_tariff_announcement():
    """The new rule runs first; it must not swallow the generic class."""
    event = frame_for("Government raises the safeguard tariff on steel imports"
                      " to 12 per cent")
    assert event.event_type == "tariff_announcement"


def test_an_unrelated_determination_is_not_a_trade_remedy():
    """'Determinations' alone is not a proceeding about duties."""
    event = frame_for("Jeffrey Thies: Final Debarment Order")
    assert event.event_type != "trade_remedy_determination"


# ------------------------------------------------------------- the stage


@pytest.mark.parametrize("title,stage", [
    ("Oleoresin Paprika From India: Antidumping Duty Order and Countervailing"
     " Duty Order", "effective"),
    ("Chromium Trioxide From India: Final Affirmative Determination of Sales"
     " at Less Than Fair Value", "adopted"),
    ("Large Diameter Graphite Electrodes From India: Preliminary Affirmative"
     " Critical Circumstances Determination", "announced"),
    ("Certain Steel Nails From India: Initiation of Antidumping Duty"
     " Investigation", "consultation"),
    # This row used to expect "expired", which was wrong and is the reason
    # the stage rule was rewritten: a five-year review being SCHEDULED is the
    # proceeding that decides whether an order continues, published while the
    # order is still in force. "expired" asserts the duty no longer applies,
    # the opposite of what the notice says. See test_ni12_sector_edges.py.
    ("Common Alloy Aluminum Sheet From India; Scheduling of Full Five-Year"
     " Reviews", "consultation"),
    ("Certain Hot-Rolled Steel From India: Revocation of the Antidumping Duty"
     " Order", "repealed"),
])
def test_the_legal_stage_is_read_from_the_instrument(title, stage):
    assert frame_for(title).frame.policy_status == stage


def test_a_preliminary_stage_says_no_duty_is_established():
    """A recommendation is not an imposed duty, and the frame must say so."""
    event = frame_for("Large Diameter Graphite Electrodes From India:"
                      " Preliminary Affirmative Determination")
    unknowns = " ".join(event.frame.unknowns)
    assert "no duty is established by this document" in unknowns


def test_an_order_does_not_carry_the_preliminary_caveat():
    event = frame_for("Oleoresin Paprika From India: Antidumping Duty Order")
    unknowns = " ".join(event.frame.unknowns)
    assert "no duty is established" not in unknowns


def test_an_unreadable_stage_stays_unknown_rather_than_guessing():
    event = frame_for("Certain Frozen Warmwater Shrimp From India: Rescission"
                      " of Antidumping Duty Administrative Review in Part")
    assert event.frame.policy_status in ("unknown", "repealed")


def test_a_postponed_final_determination_is_still_preliminary():
    """A real corpus title, and a false adverse signal it used to produce.

    "Preliminary Affirmative Determination of Sales at Less-Than-Fair-Value,
    Preliminary Affirmative Determination of Critical Circumstances,
    Postponement of Final Determination, and Extension of Provisional
    Measures" is a PRELIMINARY finding that names the final stage it is
    deferring. Reading it as `adopted` turned "no duty yet" into an adverse
    signal for Indian steel.
    """
    event = frame_for("Large Diameter Graphite Electrodes From India:"
                      " Preliminary Affirmative Determination of Sales at"
                      " Less-Than-Fair-Value, Preliminary Affirmative"
                      " Determination of Critical Circumstances, Postponement"
                      " of Final Determination, and Extension of Provisional"
                      " Measures")
    assert event.frame.policy_status == "announced"


def test_a_genuine_final_determination_is_adopted():
    event = frame_for("Chromium Trioxide From India: Final Affirmative"
                      " Determination of Sales at Less Than Fair Value")
    assert event.frame.policy_status == "adopted"


# ----------------------------------------- the subject origin of the goods


@pytest.mark.parametrize("title,expected", [
    ("Oleoresin Paprika From India: Antidumping Duty Order", ["in"]),
    ("Chromium Trioxide From India: Final Affirmative Determination", ["in"]),
    ("Certain Paper Shopping Bags From Cambodia: Preliminary Results", []),
])
def test_the_country_after_from_is_the_subject_origin(title, expected):
    """The Federal Register's documented title form, parsed deterministically.

    It is NOT a loose place mention: a speech venue and a dateline stay
    mentions, because a matcher cannot tell their role. "<Product> From
    <Country>:" is a structured fact about the instrument.
    """
    assert list(frame_for(title).exposure_origins) == expected


def test_a_subject_origin_is_not_marked_affected():
    """It seeds a scoped exposure query; being affected still needs an edge."""
    event = frame_for("Chromium Trioxide From India: Final Affirmative"
                      " Determination")
    assert "in" not in event.affected


def test_the_subject_origin_carries_an_evidence_span():
    event = frame_for("Oleoresin Paprika From India: Antidumping Duty Order")
    fields = {span.field for span in event.evidence}
    assert "subject_origin" in fields


def test_an_unknown_country_produces_nothing_rather_than_a_guess():
    event = frame_for("Widgets From Ruritania: Final Affirmative Determination")
    assert event.exposure_origins == ()


def test_a_non_remedy_title_does_not_get_subject_origins():
    """The rule is scoped to the one documented title form."""
    event = frame_for("Keynote address delivered in India by the Governor")
    assert event.exposure_origins == ()


# ------------------------------------------- direction is never assumed


@pytest.mark.parametrize("title", [
    "Chromium Trioxide From India: Final Affirmative Determination of Sales at"
    " Less Than Fair Value",
    "Oleoresin Paprika From India: Antidumping Duty Order",
])
def test_the_measure_alone_does_not_establish_a_sign(title):
    unknowns = " ".join(frame_for(title).frame.unknowns)
    assert "depends on the target role" in unknowns
    assert "exporter, competing producer, downstream buyer" in unknowns


def test_a_trade_remedy_claims_no_quantity_it_cannot_read():
    event = frame_for("Chromium Trioxide From India: Final Affirmative"
                      " Determination of Sales at Less Than Fair Value")
    assert event.frame.quantities == ()


# ------------------------------------- the USITC's bare determination form


@pytest.mark.parametrize("title", [
    "Oil Country Tubular Goods From India, South Korea, Turkey, Ukraine, and"
    " Vietnam; Determinations",
    "Perfluoroalkoxy Alkane From India; Determinations",
    "Oleoresin Paprika From India; Determinations",
    "Linear Hydraulic Cylinders From Canada, China, India, Mexico, and South"
    " Korea, Determinations",
])
def test_a_bare_usitc_determination_is_a_trade_remedy(title):
    """The Commission writes "Determinations" and no duty word at all.

    My first rule required a duty/dumping/subsidy word within 80 characters,
    so every one of these was invisible — including oil country tubular
    goods, which is steel pipe for wells and reaches the Indian steel sector.
    The distinguishing grammar is the subject-origin construction followed by
    the word, which a debarment order or a pricing model does not have.
    """
    assert frame_for(title).event_type == "trade_remedy_determination"


def test_the_country_list_may_contain_commas():
    """The span may not exclude commas; only the terminator may."""
    event = frame_for("Oil Country Tubular Goods From India, South Korea,"
                      " Turkey, Ukraine, and Vietnam; Determinations")
    assert "in" in event.exposure_origins


@pytest.mark.parametrize("title", [
    "Jeffrey Thies: Final Debarment Order",
    "Global Benchmark for Efficient Drug Pricing (GLOBE) Model",
    "Investment Company Cross Trading",
])
def test_an_unrelated_notice_is_not_swept_in(title):
    assert frame_for(title).event_type != "trade_remedy_determination"


def test_a_bare_determination_states_no_legal_stage():
    """It does not say what was determined, so nothing may be inferred."""
    event = frame_for("Oleoresin Paprika From India; Determinations")
    assert event.frame.policy_status == "unknown"


# ------------------------------------------- the Fed and appellate filings


@pytest.mark.parametrize("title,expected", [
    ("Federal Reserve Board announces enforcement action against American"
     " Express Company", "regulatory_action"),
    ("Federal Reserve Board announces approval of application by Peoples"
     " Bancorp Inc.", "regulatory_action"),
    ("Federal Reserve Board announces it will extend the comment period on"
     " its proposal", "regulatory_action"),
    ("Minutes of the Board's discount rate meetings on August 17, September 9,"
     " and September 16, 2026", "policy_rate_decision"),
    ("Federal Reserve issues FOMC statement", "policy_rate_decision"),
    ("Minutes of the Federal Open Market Committee, September 15-16, 2026",
     "policy_rate_decision"),
    ("Federal Reserve Board releases results of the 2025 Survey of Consumer"
     " Finances", "statistical_release"),
    ("Enhanced Transparency and Public Accountability of the Supervisory"
     " Stress Test Models and Scenarios", "prudential_norms_change"),
    ("Appeal No. 7114 of 2026 filed by A. Balamurugan", "regulatory_appeal"),
])
def test_the_remaining_groups_are_named(title, expected):
    """A system whose first pillar is a central bank classified every FOMC
    statement as `other`; dozens of SEBI appeals diluted the same bucket."""
    assert frame_for(title).event_type == expected


def test_other_still_means_we_do_not_know():
    """Naming classes must not turn `other` into a catch-all that never fires."""
    assert frame_for("Millennium Challenge Corporation Selection Criteria"
                     " and Methodology Report").event_type == "other"


# --------------------------------------------- place aliases and roles


def test_a_long_legal_country_name_resolves_through_an_alias():
    """Official documents write countries in their long legal form.

    `Entity` has carried aliases from the start; `Place` had none, so a
    curated country could never match the name an official document uses.
    China costs something here: it has a curated place AND a curated exposure
    edge into an Indian sector, and a remedy written as "the People's Republic
    of China" reached neither.
    """
    from seraph.news.model import Place

    data = MasterData()
    data.add_place(Place("cn", "China", "country", iso_code="CHN",
                         aliases=("People's Republic of China", "PRC")))
    assert data.resolve_place("People's Republic of China").entity_id == "cn"
    assert data.resolve_place("PRC").entity_id == "cn"
    assert data.resolve_place("China").entity_id == "cn"


def test_alias_matching_is_exact_not_fuzzy():
    """"Korea" must not quietly become "Republic of Korea"."""
    from seraph.news.model import Place

    data = MasterData()
    data.add_place(Place("kr", "Republic of Korea", "country"))
    assert data.resolve_place("Korea").status == "unknown"


def test_two_places_claiming_one_alias_still_abstain():
    from seraph.news.model import Place

    data = MasterData()
    data.add_place(Place("a", "North Something", "country", aliases=("Somewhere",)))
    data.add_place(Place("b", "South Something", "country", aliases=("Somewhere",)))
    assert data.resolve_place("Somewhere").status == "ambiguous"


def test_the_shipped_registry_resolves_the_long_forms():
    from seraph.news.registry import load_master_data

    data, _ = load_master_data()
    assert data.resolve_place("People's Republic of China").entity_id == "cn"
    assert data.resolve_place("United States of America").entity_id == "us"


def test_a_subject_origin_is_recorded_as_its_own_role():
    """Not merged with the issuer-jurisdiction exposure seed.

    `exposure_origins` carries both "the goods come from here" and "the
    issuing authority is here". They are different claims and must not share
    a label on the map: before this split, a US tariff notice put the United
    States in the globe's `subjects` layer, captioned "goods from here are
    covered by the instrument".
    """
    event = frame_for("Chromium Trioxide From India: Final Affirmative"
                      " Determination")
    roles = dict((node, role) for node, role in event.locations)
    assert roles.get("in") == "subject_origin"


# --------------------------------------------- the product scope is narrow


def test_the_steel_edge_covers_steel_articles_only():
    """An input to steelmaking is not a steel export.

    The first version of this edge matched `chromium` and `graphite
    electrode`, and both duly produced "adverse for the steel sector":
    chromium trioxide is a metal-finishing chemical, and large-diameter
    graphite electrodes are a consumable INPUT to electric-arc steelmaking.
    A US duty on either is a duty on a different Indian industry.
    """
    from seraph.news.registry import load_master_data

    data, _ = load_master_data()
    edge = data.edges["india_steel_us_trade_remedy"]
    products = " ".join(edge.products).lower()
    assert "chromium" not in products
    assert "graphite" not in products
    assert "steel" in products


def test_the_edge_records_why_the_scope_is_narrow():
    from seraph.news.registry import load_master_data

    data, _ = load_master_data()
    note = (data.edges["india_steel_us_trade_remedy"].note or "").lower()
    assert "chromium trioxide" in note and "graphite electrodes" in note
    assert "input" in note


def test_the_edge_is_unsized_so_no_loss_can_be_derived():
    from seraph.news.registry import load_master_data

    data, _ = load_master_data()
    edge = data.edges["india_steel_us_trade_remedy"]
    assert edge.magnitude is None and edge.unit is None
    assert edge.evidence, "an unevidenced edge is an assertion"


# ------------------------------------------------- on the real corpus


ROOT_STORE = "prototype_runs/news-intelligence-pilot.sqlite"


@pytest.mark.skipif(
    not __import__("pathlib").Path(ROOT_STORE).exists()
    and not (__import__("pathlib").Path(__file__).resolve().parent.parent
             / ROOT_STORE).exists(),
    reason="the pilot store is not present in this checkout")
def test_the_real_corpus_now_classifies_its_trade_remedies():
    from pathlib import Path

    from seraph.dashboard.news_view import news_channel
    from seraph.news.acquisition import NewsStore, _now
    from seraph.news.registry import load_master_data

    root = Path(__file__).resolve().parent.parent
    store = NewsStore(root / ROOT_STORE)
    master, _ = load_master_data()
    channel = news_channel(store, master, decision_ts=_now(), limit=1000)
    remedies = [e for e in channel["eligible_events"]
                if e.event_type == "trade_remedy_determination"]
    assert len(remedies) >= 20, "the corpus holds a substantial remedy slice"
    stages = {e.frame.policy_status for e in remedies}
    # The point of the class: it separates stages rather than flattening them.
    assert len(stages & {"announced", "adopted", "effective"}) >= 2
