"""What a measure actually covers — and what it carves out.

An exposure walk matches an event to an edge on `products`. That match treats
the document as if its scope were the whole product family, and trade
instruments almost never are: they cover a defined article, exclude named
variants, and sometimes exempt named parties. A duty "on certain corrosion-
resistant steel products, excluding products with a specified coating" is not
a duty on corrosion-resistant steel.

Getting this wrong is directional, not merely imprecise: an exclusion that is
missed turns "this does not apply to you" into an adverse signal.

**What is extractable here is narrow, and that is stated rather than hidden.**
These documents are mostly titles. A title carries the covered article and
occasionally the word "excluding"; the operative scope — tariff lines, the
"Scope of the Order" section, the list of exempted producers — lives in the
body, which is retained for five of seventeen sources. So:

* a scope found in the text is reported, with the span that evidenced it;
* a scope that is NOT found is reported as `unknown`, never as "no exclusions";
* `unknown` scope does not block a match, because requiring full scope before
  any inference would silently drop every title-only document. It attaches a
  limitation instead, and that limitation travels to the screen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Carve-out language. `exclusive` is deliberately absent: "Exclusively listed
#: companies" and "Exclusive Economic Zone" both appear in this corpus and
#: neither is an exclusion from a measure.
EXCLUSION = re.compile(
    r"\b(?:but\s+)?exclud(?:es|ing|ed)\b"
    r"|\bexcept(?:\s+for)?\b"
    r"|\bexempt(?:s|ed|ion)?\s+(?:from|for)\b"
    r"|\bother\s+than\b"
    r"|\bcarve-?outs?\b"
    r"|\bdoes\s+not\s+(?:apply|cover|include)\b", re.I)

#: An explicit statement of what IS covered.
INCLUSION = re.compile(
    r"\bscope\s+of\s+the\s+order\b"
    r"|\bcovered\s+(?:merchandise|products?|articles?)\b"
    r"|\bsubject\s+merchandise\b"
    r"|\bapplies\s+(?:only\s+)?to\b", re.I)

#: Named-party exemptions: "X is excluded from the order".
PARTY_EXEMPTION = re.compile(
    r"\b(?:excluded|exempt(?:ed)?)\s+(?:producers?|exporters?|companies|"
    r"respondents?|entities)\b", re.I)

#: ---------------------------------------------------------------------
#: Carve-outs that name WHAT is outside the measure.
#:
#: Detecting that an exclusion exists was never enough. A steel duty whose
#: body reads "This order does not apply to products from India" still
#: emitted an adverse Indian steel route, because the impact walk read the
#: headline and the exclusion lived in the body. An exclusion that is read
#: and then not enforced is worse than one that was never read: it is
#: evidence, on the record, pointing the opposite way to the output.
#:
#: These patterns are deliberately literal. The carve-out is only acted on
#: when the text NAMES the excluded country, product or party; a detected
#: but unnamed carve-out still only lowers confidence, as before, because
#: suppressing a route on an exclusion we could not read would be the same
#: guess in the other direction.
#:
#: The keyword half is case-insensitive and the captured name is not —
#: scoped inline flags, so `[A-Z]` keeps meaning "a capitalised word" and a
#: sentence-initial verb still matches.
#: A capitalised word. A dot may only sit INSIDE one ("U.S.A"), never end
#: it, so a proper-noun run cannot swallow the full stop and keep going into
#: the next sentence — which is how "the Republic of Korea. Acme Steel"
#: became one excluded country.
_WORD = r"[A-Z][\w'\u2019-]*(?:\.[A-Za-z][\w'\u2019-]*)*"
_PROPER = (r"(?:the\s+)?" + _WORD
           + r"(?:\s+(?:of|and|the)\s+" + _WORD + r"|\s+" + _WORD + r"){0,3}")

#: Captures that are a sentence frame rather than a name.
_PREPOSITION = r"(?!(?:from|to|for|of|by|under|with|any|all)\b)"

#: A bare "of" is NOT an origin connector. It matched "Exemption Order in
#: the matter **of** Allcargo Logistics Limited" — a SEBI enforcement
#: document — and filed the respondent as an excluded COUNTRY, which would
#: then have suppressed a route. An origin needs "from", "originating in",
#: or a goods noun carrying the "of". `(?!\s+order\b)` keeps "Exemption
#: Order", a document type, out of the carve-out vocabulary entirely.
EXCLUDED_ORIGIN = re.compile(
    r"(?i:\b(?:does\s+not\s+(?:apply|cover|include)|exclud(?:es|ing|ed)"
    r"|except(?:\s+for)?|other\s+than|exempt(?:s|ed|ion)?)\b(?!\s+order\b)"
    r"[^.;]{0,60}?"
    r"(?:\b(?:from|originating\s+in)\s+"
    r"|\b(?:products?|goods?|merchandise|articles?|imports?)\s+of\s+))"
    r"(" + _PROPER + r")")

EXCLUDED_PRODUCT = re.compile(
    r"(?i:\b(?:does\s+not\s+(?:apply|cover|include)|exclud(?:es|ing|ed)"
    r"|other\s+than)\s+(?:to\s+|for\s+)?)"
    + _PREPOSITION +
    r"([a-z][a-z0-9\u2010-\u2015 /-]{2,60}?)"
    r"(?=\s*(?:\bfrom\b|\boriginating\b|[.;,]|$))")

EXCLUDED_PARTY = re.compile(
    r"(" + _PROPER + r")\s+(?i:(?:is|are|was|were)\s+"
    r"(?:excluded|exempt(?:ed)?)\s+from\b)")

#: Words a captured "product" may not be, because they name the instrument
#: or the sentence frame rather than an article.
_NOT_A_PRODUCT = frozenset({
    "this", "the", "that", "it", "them", "any", "all", "such", "any of",
    "products", "product", "goods", "merchandise", "articles", "imports",
    "the order", "this order", "the measure", "the duty",
})


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().strip(".,;:").removeprefix(
        "the ").removeprefix("The ").strip()


@dataclass(frozen=True)
class Scope:
    """What a measure covers, as far as the received text establishes it."""

    has_exclusions: bool = False
    has_explicit_coverage: bool = False
    exempts_named_parties: bool = False
    spans: tuple = field(default_factory=tuple)
    determined: bool = False
    #: What the text NAMED as outside the measure. Empty is not "nothing is
    #: excluded": `determined` and `has_exclusions` carry that distinction.
    excluded_countries: tuple = field(default_factory=tuple)
    excluded_products: tuple = field(default_factory=tuple)
    excluded_parties: tuple = field(default_factory=tuple)
    #: Whether a document body was actually retained for this item. `None`
    #: means the caller did not say. The limitation below used to assert
    #: "the body is not retained for this source" whatever the record held,
    #: so a reader of a fully retained document was told the opposite of
    #: what was on file.
    body_retained: "bool | None" = None

    @property
    def named_exclusions(self) -> bool:
        """Did the text name something specific as outside the measure?

        Only a NAMED carve-out may suppress an impact claim. A detected but
        unparsed one lowers confidence instead — suppressing on an exclusion
        nobody could read is the same guess pointed the other way.
        """
        return bool(self.excluded_countries or self.excluded_products
                    or self.excluded_parties)

    @property
    def note(self) -> str | None:
        """One line naming the carve-out, for the frame's `unknowns`."""
        parts = []
        if self.excluded_countries:
            parts.append("origin(s) " + ", ".join(self.excluded_countries))
        if self.excluded_products:
            parts.append("product(s) " + ", ".join(self.excluded_products))
        if self.excluded_parties:
            parts.append("part(y/ies) " + ", ".join(self.excluded_parties))
        if not parts:
            return None
        return ("the received text EXCLUDES " + "; ".join(parts)
                + " from this measure: no applicable impact is claimed for "
                  "what it names")

    @property
    def limitation(self) -> str | None:
        """What a reader must not conclude from this scope."""
        if not self.determined:
            if self.body_retained is True:
                return ("product scope was NOT established: the retained "
                        "document says nothing about which articles are "
                        "covered, so a product-family match may include "
                        "articles the measure does not cover")
            if self.body_retained is False:
                return ("product scope was NOT established from the received "
                        "text: the operative scope lives in the document "
                        "body, which is not retained for this item. A "
                        "product-family match may therefore include articles "
                        "the measure does not cover")
            return ("product scope was NOT established from the received "
                    "text. A product-family match may therefore include "
                    "articles the measure does not cover")
        if self.named_exclusions:
            return self.note
        if self.has_exclusions or self.exempts_named_parties:
            return ("this instrument carves something out. The exclusion was "
                    "detected but NOT parsed, so which articles or parties "
                    "are outside it is unknown, and a match on the product "
                    "family may include something excluded")
        return None

    def describe(self) -> dict:
        return dict(determined=self.determined,
                    has_exclusions=self.has_exclusions,
                    has_explicit_coverage=self.has_explicit_coverage,
                    exempts_named_parties=self.exempts_named_parties,
                    excluded_countries=list(self.excluded_countries),
                    excluded_products=list(self.excluded_products),
                    excluded_parties=list(self.excluded_parties),
                    evidence=[dict(text=t, start=s, end=e)
                              for t, s, e in self.spans],
                    limitation=self.limitation)


def scope_of(text: str, *, body_retained: "bool | None" = None) -> Scope:
    """Read what the text says about coverage. Never infer absence.

    `body_retained` is what the RECORD says about this item, and it only
    ever shapes the wording of the limitation. The scope itself is read
    from the text in hand either way.
    """
    if not text:
        return Scope(body_retained=body_retained)

    spans = []
    exclusions = list(EXCLUSION.finditer(text))
    coverage = list(INCLUSION.finditer(text))
    parties = list(PARTY_EXEMPTION.finditer(text))
    named_origins = list(EXCLUDED_ORIGIN.finditer(text))
    named_products = list(EXCLUDED_PRODUCT.finditer(text))
    named_parties = list(EXCLUDED_PARTY.finditer(text))
    for match in (exclusions + coverage + parties + named_origins
                  + named_products + named_parties):
        spans.append((match.group(0), match.start(), match.end()))

    countries = tuple(dict.fromkeys(
        _clean(m.group(1)) for m in named_origins if _clean(m.group(1))))
    products = tuple(dict.fromkeys(
        p for p in (_clean(m.group(1)) for m in named_products)
        if p and p.lower() not in _NOT_A_PRODUCT))
    party_names = tuple(dict.fromkeys(
        _clean(m.group(1)) for m in named_parties if _clean(m.group(1))))

    return Scope(
        has_exclusions=bool(exclusions),
        has_explicit_coverage=bool(coverage),
        exempts_named_parties=bool(parties or party_names),
        spans=tuple(spans),
        excluded_countries=countries,
        excluded_products=products,
        excluded_parties=party_names,
        body_retained=body_retained,
        # `determined` means the text SAID something about scope. Silence is
        # not "no exclusions"; it is "we were not told".
        determined=bool(exclusions or coverage or parties or named_origins
                        or named_products or named_parties))


def applies_to_product(scope: Scope, product_matched: bool) -> dict:
    """Whether a product match should be trusted, and what to say about it.

    An undetermined or carved-out scope does NOT block the match. Requiring
    full scope before any inference would silently drop every title-only
    document, which is most of this corpus. The match stands and carries its
    limitation to the screen.
    """
    return dict(
        matched=product_matched,
        scope_determined=scope.determined,
        confidence_ceiling=("medium" if scope.determined
                            and not scope.has_exclusions else "low"),
        limitation=scope.limitation,
        note=("a product-family match is not a scope determination. The "
              "instrument's own scope section is authoritative and is not "
              "retained for most sources here"))


def excluded_place_ids(frame, master) -> dict:
    """Resolve the frame's named excluded origins to curated place ids.

    Returns `{place_id: name}`. A name the place registry does not know
    resolves to nothing and is reported separately: an unresolvable
    exclusion must not silently become "no exclusion", and it must not
    suppress an unrelated route either.
    """
    resolved, unresolved = {}, []
    for name in getattr(frame, "excluded_countries", ()) or ():
        found = master.resolve_place(name)
        if getattr(found, "status", "") == "resolved":
            resolved[found.entity_id] = name
        else:
            unresolved.append(name)
    return dict(places=resolved, unresolved=tuple(unresolved))


def excludes_product(frame, products) -> bool:
    """Is EVERY product on this relationship named as excluded?

    All of them, not any: a relationship covering steel and aluminium when
    only aluminium is carved out still has a live route.
    """
    carved = [p.casefold() for p in
              (getattr(frame, "excluded_products", ()) or ())]
    products = [p for p in (products or ())]
    if not carved or not products:
        return False
    return all(any(c in p.casefold() or p.casefold() in c for c in carved)
               for p in products)


def excludes_party(frame, *names) -> bool:
    """Is one of these names explicitly exempted by the instrument?"""
    carved = [p.casefold() for p in
              (getattr(frame, "excluded_parties", ()) or ())]
    if not carved:
        return False
    return any(name and any(c == name.casefold() or c in name.casefold()
                            for c in carved) for name in names)
