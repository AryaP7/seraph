"""A narrow Hindi rule set — and the claim it must never make.

PIB publishes in Hindi, and `Lang=1` returns the same Hindi content as
`Lang=2`: there is no English PIB RSS at that endpoint, so "obtain usable
English coverage" was checked and is not available. Multilingual extraction is
the only remaining route, and every Hindi item previously abstained entirely.

The hazard in fixing this is overclaiming. These rules read a handful of
nouns. They do not parse grammar or negation and cannot tell a proposal from a
decision — so a Hindi event must never present like an English one, however
confidently a keyword matched.

The rules are grounded in the 42 PIB items actually received. Most of that
corpus is condolences, a craft fair, Ayurveda awareness and youth programmes:
a rule set that classified most of this feed would be wrong, and leaving the
majority as `other` is the correct outcome.
"""
from __future__ import annotations

import pytest

from seraph.news.event_frames import frame_for
from seraph.news.hindi import (
    CAVEAT,
    HINDI_RULES,
    classify_hindi,
    is_hindi,
    places_in,
)

# Real headlines from the received corpus.
DRUG_MARGIN = "137 कैंसर रोधी दवाओं पर व्यापार मार्जिन का युक्तिकरण"
IDBI_STAKE = ("आईडीबीआई में सरकार की हिस्सेदारी से संबंधित विधायी "
              "घटनाक्रमों पर स्पष्टीकरण")
CAQM = ("सीएक्यूएम ने एनसीआर में अनुपालन स्थिति और प्रवर्तन कार्रवाइयों की "
        "समीक्षा की")
CONDOLENCE = "श्री सी. पी. राधाकृष्णन ने संगीतकार देवा के निधन पर शोक व्यक्त किया"
CRAFT_FAIR = "शिल्प समागम मेला 2026-मैसूर, कर्नाटक"
AYURVEDA = "विश्व रजोनिवृत्ति दिवस 2026: आयुर्वेद रजोनिवृत्ति स्वास्थ्य"


# ------------------------------------------------- it reads what it should

@pytest.mark.parametrize("headline,expected", [
    (DRUG_MARGIN, "price_control"),
    (IDBI_STAKE, "ownership_change"),
    (CAQM, "regulatory_action"),
    ("रिजर्व बैंक ने रेपो दर 25 आधार अंक घटाई", "policy_rate_decision"),
    ("सरकार ने चावल के निर्यात पर प्रतिबंध लगाया", "export_restriction"),
    ("इस्पात आयात पर सीमा शुल्क बढ़ाया गया", "tariff_announcement"),
    ("ओडिशा में भूकंप के झटके महसूस किए गए", "physical_hazard"),
])
def test_a_market_relevant_headline_is_classified(headline, expected):
    assert classify_hindi(headline)[0] == expected


def test_the_match_is_returned_so_it_can_be_shown(headline=DRUG_MARGIN):
    """A classification nobody can check against the source text is an
    assertion. The matched substring becomes an evidence span."""
    event_type, matched = classify_hindi(headline)
    assert event_type == "price_control"
    assert matched and matched in headline


# -------------------------------------------- it stays quiet when it should

@pytest.mark.parametrize("headline", [CONDOLENCE, CRAFT_FAIR, AYURVEDA])
def test_the_non_market_majority_stays_other(headline):
    """Most of this feed is not market news. A rule set that classified it
    would be wrong, and `other` here is correctness, not a shortfall."""
    assert classify_hindi(headline)[0] == "other"


def test_an_unmatched_hindi_item_says_it_is_not_known_either_way():
    frame = frame_for(CONDOLENCE, "s1", "other", language="hi",
                      available_at="2026-10-18T09:00:00+05:30")
    assert any("not known to be a market event" in u for u in frame.unknowns)
    assert any("not known not to be" in u for u in frame.unknowns)


# ------------------------------------------ it never claims comprehension

@pytest.mark.parametrize("headline", [DRUG_MARGIN, IDBI_STAKE, CAQM])
def test_a_hindi_frame_is_never_a_confirmed_statement(headline):
    """The claim this file exists to prevent. However confidently a keyword
    matched, nobody read the sentence."""
    frame = frame_for(headline, "s1", "price_control", language="hi",
                      available_at="2026-10-18T09:00:00+05:30")
    assert frame.assertion_status == "reported_unconfirmed"


def test_every_hindi_frame_carries_the_caveat():
    frame = frame_for(DRUG_MARGIN, "s1", "price_control", language="hi",
                      available_at="2026-10-18T09:00:00+05:30")
    assert CAVEAT in frame.unknowns
    assert "not by language comprehension" in CAVEAT
    assert "does not parse grammar or negation" in CAVEAT


def test_a_hindi_frame_keeps_the_original_text_as_evidence():
    frame = frame_for(DRUG_MARGIN, "s1", "price_control", language="hi",
                      available_at="2026-10-18T09:00:00+05:30")
    assert frame.evidence
    span = frame.evidence[0]
    assert span.field == "hindi_rule"
    assert DRUG_MARGIN[span.start:span.end] == span.text


def test_another_language_still_abstains_entirely():
    """The widening is Hindi-specific. A Tamil or Bengali feed must not
    inherit rules written for Devanagari."""
    frame = frame_for("அறிவிப்பு வெளியிடப்பட்டது", "s1", "other",
                      language="ta", available_at="2026-10-18T09:00:00+05:30")
    assert frame.unknowns == ("language unsupported by English rules",)


# ----------------------------------------------------- places and grounding

def test_devanagari_place_names_reach_the_registry():
    assert places_in(CAQM) == ["in"]
    assert places_in("चीन और अमेरिका के बीच") == ["cn", "us"]
    # The craft fair names कर्नाटक (Karnataka), which IS in India, so it
    # resolves correctly. A headline naming no place resolves to nothing --
    # which is the property worth pinning, and my first version of this
    # assertion had the geography wrong rather than the code.
    assert places_in(CRAFT_FAIR) == ["in"]
    assert places_in(CONDOLENCE) == []


def test_is_hindi_detects_devanagari():
    assert is_hindi(DRUG_MARGIN)
    assert not is_hindi("Chromium Trioxide From India")


def test_every_rule_records_the_headline_that_motivated_it():
    """So a reader can check a rule against the text it came from rather than
    against my guess at Hindi."""
    for event_type, pattern, example in HINDI_RULES:
        assert example, f"{event_type} has no grounding example"
        assert isinstance(pattern, str) and pattern
