"""A narrow Hindi rule set — comprehension is NOT claimed.

PIB publishes in Hindi, and `Lang=1` returns the same Hindi content as
`Lang=2`: there is no English PIB RSS at that endpoint, so "obtain usable
English coverage" is not available and multilingual extraction is the only
remaining route.

Until now every Hindi item abstained entirely — `assertion_status
= reported_unconfirmed`, `unknowns = ('language unsupported by English
rules',)`. That was honest and it cost the whole feed.

**What this is.** A keyword rule set over the vocabulary that actually appears
in this corpus, mapping to the SAME event types the English rules use. Every
rule below is grounded in a real headline, quoted with it, so a reader can
check the rule against the text that motivated it rather than against my
guess at Hindi.

**What this is not.** Comprehension. These rules read a handful of nouns. They
do not parse Hindi grammar, do not resolve negation, and cannot tell a
proposal from a decision — so a Hindi event never claims
`confirmed_statement` on the strength of them, and every one carries an
explicit caveat naming the rule set. The original Hindi text is retained as
evidence so the claim can be checked against the source.

**What the corpus is mostly.** Reading all 22 received PIB items: condolences,
a craft fair, Ayurveda and menopause awareness, youth programmes, a sanitation
campaign, a naval squadron's departure. Perhaps four are market-relevant. A
rule set that classified most of this feed would be wrong; leaving the
majority as `other` is the correct outcome, not a shortfall.
"""
from __future__ import annotations

import re

#: (event_type, pattern, the real headline that motivated the rule).
#: Order matters: the first match wins, so the specific precede the generic.
HINDI_RULES: tuple[tuple[str, str, str], ...] = (
    # "137 कैंसर रोधी दवाओं पर व्यापार मार्जिन का युक्तिकरण"
    # — rationalisation of the trade margin on 137 anti-cancer drugs.
    ("price_control",
     r"(?:दवाओं|दवा|औषधि|औषधियों)\s*(?:पर|के)?.*?"
     r"(?:मूल्य|कीमत|मार्जिन|युक्तिकरण|नियंत्रण)"
     r"|(?:मूल्य|कीमत|मार्जिन)\s*(?:नियंत्रण|सीमा|युक्तिकरण)",
     "137 कैंसर रोधी दवाओं पर व्यापार मार्जिन का युक्तिकरण"),

    # "आईडीबीआई में सरकार की हिस्सेदारी से संबंधित विधायी घटनाक्रमों पर स्पष्टीकरण"
    # — a clarification on the government's stake in IDBI Bank.
    ("ownership_change",
     r"हिस्सेदारी|विनिवेश|निजीकरण|अधिग्रहण|विलय",
     "आईडीबीआई में सरकार की हिस्सेदारी से संबंधित विधायी घटनाक्रमों पर स्पष्टीकरण"),

    # Monetary policy. Not present in the received sample, included because
    # the RBI vocabulary is fixed and an unmatched rate decision is the most
    # costly single miss this feed could produce.
    ("policy_rate_decision",
     r"रेपो\s*दर|नीतिगत\s*दर|मौद्रिक\s*नीति|रिवर्स\s*रेपो|बैंक\s*दर",
     "(not in the received sample; RBI vocabulary is fixed)"),

    ("export_restriction",
     r"निर्यात\s*(?:पर\s*)?(?:प्रतिबंध|रोक|शुल्क)",
     "(not in the received sample)"),

    ("tariff_announcement",
     r"आयात\s*शुल्क|सीमा\s*शुल्क|टैरिफ|प्रतिकारी\s*शुल्क|डंपिंग\s*रोधी",
     "(not in the received sample)"),

    # "सीएक्यूएम ने एनसीआर में अनुपालन स्थिति और प्रवर्तन कार्रवाइयों की समीक्षा की"
    # — CAQM reviewed compliance status and enforcement actions in the NCR.
    ("regulatory_action",
     r"प्रवर्तन|अनुपालन|निरीक्षण|जुर्माना|कारण\s*बताओ|अधिसूचना|"
     r"दिशा-?निर्देश|आदेश\s*जारी",
     "सीएक्यूएम ने एनसीआर में अनुपालन स्थिति और प्रवर्तन कार्रवाइयों की समीक्षा की"),

    ("physical_hazard",
     r"भूकंप|बाढ़|चक्रवात|भूस्खलन|आग\s*लग|विस्फोट",
     "(not in the received sample; USGS covers hazards in English)"),

    ("production_halt",
     r"उत्पादन\s*(?:बंद|ठप|रोक)|संयंत्र\s*बंद|हड़ताल|तालाबंदी",
     "(not in the received sample)"),
)

#: Devanagari names for places the curated registry already holds. Resolution
#: still goes through the registry — this only lets a Hindi spelling reach it.
HINDI_PLACES: dict[str, str] = {
    "भारत": "in",
    "दिल्ली": "in",
    "एनसीआर": "in",
    "मुंबई": "in",
    "ओडिशा": "in",
    "गुजरात": "in",
    "महाराष्ट्र": "in",
    "कर्नाटक": "in",
    "अमेरिका": "us",
    "चीन": "cn",
}

#: Attached to every Hindi interpretation. The reader must be able to tell a
#: keyword hit from an understood sentence.
CAVEAT = ("interpreted by a NARROW Hindi keyword rule set, not by language "
          "comprehension: it reads a few nouns, does not parse grammar or "
          "negation, and cannot distinguish a proposal from a decision. The "
          "original Hindi text is retained as evidence")

_COMPILED = tuple((event_type, re.compile(pattern), example)
                  for event_type, pattern, example in HINDI_RULES)


def is_hindi(text: str) -> bool:
    """Does this text contain Devanagari at all?"""
    return any(0x900 <= ord(ch) <= 0x97F for ch in text)


def classify_hindi(text: str) -> tuple[str, str | None]:
    """(event_type, the matched substring) — `other` when nothing matches.

    `other` is the expected outcome for most of this feed and is not a
    failure: the majority of PIB's Hindi releases are not market events.
    """
    for event_type, pattern, _example in _COMPILED:
        found = pattern.search(text)
        if found:
            return event_type, found.group(0)
    return "other", None


def places_in(text: str) -> list[str]:
    """Registry ids for Devanagari place names appearing in the text."""
    return sorted({place_id for name, place_id in HINDI_PLACES.items()
                   if name in text})
