# C13 — Structured extraction from story text (NEWS05)
"""Turn stories into events, with evidence spans, and abstain where unsure.

This extractor is **rule-based and deliberately explainable**. Every field it
emits points at the characters it came from, so a review set can mark it right
or wrong and an analyst can see why it decided what it did. An unexplainable
extractor cannot be reviewed, and a news pipeline nobody can audit is worse
than no news pipeline.

What it will not do
-------------------
* It does not guess an event type. No pattern match means `other`, and the
  caller sees that nothing specific was recognised.
* It does not guess quantities. A percentage with no recognised subject stays
  out of `quantities` and goes into `unresolved`.
* It does not resolve entities itself — `MasterData.resolve` does, and returns
  `ambiguous` rather than picking a candidate. An ambiguous mention is carried
  in `unresolved`, never silently dropped and never silently chosen.

Article text is untrusted input
-------------------------------
Nothing in a story can reach an application command, a grant or a regulator
action. This module only ever produces `Event` records; it has no write path
to anything else, and `scrub()` strips the shapes that try.

If a language model is substituted for these rules, the contract is the same:
schema validation, evidence spans, a versioned prompt and model id, a review
set, and explicit abstention. The `extractor_version` field exists so a
re-extraction is distinguishable from the original.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from seraph.news.event_frames import frame_for, VERSION

from seraph.news.model import (
    Event,
    EventType,
    EvidenceSpan,
    Story,
    event_identity,
)
from seraph.news.registry import MasterData
from seraph.product_types import Timing

EXTRACTOR_VERSION = VERSION

#: Ordered: the first pattern that matches wins, most specific first.
#:
#: The monetary/banking block was written against the RBI feeds actually
#: connected on 2026-10-16, not against imagined content. Order matters a lot
#: here: "Change in Daily Minimum Cash Reserve" must reach
#: `reserve_requirement_change` before the generic auction pattern sees the
#: word "Reserve", and a speech about financial stability must not be read as
#: a policy decision.
#: "<Product> From <Country>[, <Country> and <Country>]" — the Federal
#: Register's documented title form for a trade-remedy proceeding. The names
#: after "From" are the subject origins of the goods, which is a structured
#: fact about the instrument rather than a passing mention of a place.
SUBJECT_ORIGIN = re.compile(
    r"\bfrom\s+((?:the\s+)?[A-Z][\w'’.-]*(?:\s+(?:of|and|the)?\s*[A-Z][\w'’.-]*)*"
    r"(?:\s*,\s*(?:and\s+)?(?:the\s+)?[A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*)*)*)"
    r"\s*[:;]", re.I)

EVENT_PATTERNS: tuple[tuple[EventType, re.Pattern], ...] = (
    # --- speeches first: they TALK about everything below and decide nothing.
    ("official_speech",
     re.compile(r"\b(keynote address|special address|welcome remarks|inaugural "
                r"(?:session|address)|edited transcript|valedictory|speech by|"
                r"address (?:by|delivered)|RBI Talks)\b", re.I)),
    # --- an appeal is a stage in someone else's dispute, not a policy change.
    # Placed first: "Appeal No. 7114 of 2026 filed by ..." carries no other
    # cue, and dozens of them were diluting `other`.
    ("regulatory_appeal",
     re.compile(r"\bappeal no\.?\s*\d+|\bappeal\s+(?:no|number)\b|"
                r"\bsecurities appellate tribunal\b|\bSAT\b(?=.{0,40}appeal)", re.I)),
    # --- monetary and prudential: binding, and materially different from each other
    ("reserve_requirement_change",
     re.compile(r"\b(cash reserve ratio|\bCRR\b|statutory liquidity ratio|\bSLR\b"
                r"|daily minimum cash reserve)\b", re.I)),
    ("policy_rate_decision",
     # The Fed's vocabulary alongside the RBI's. A system whose first pillar
     # is a central bank classified every FOMC statement as "other".
     re.compile(r"\b(repo rate|policy rate|reverse repo|bank rate|"
                r"monetary policy (?:statement|committee|decision)|\bMPC\b|"
                r"\bFOMC\b|federal open market committee|"
                r"discount rate meetings?)\b", re.I)),
    ("prudential_norms_change",
     re.compile(r"\b(prudential norms|capital adequacy|amendment directions|"
                r"master direction|provisioning norms|exposure norms|"
                r"supervisory stress test|stress test (?:models|scenarios)|"
                r"third-?party risk management guidance)\b", re.I)),
    ("forex_regulation",
     re.compile(r"\b(inter-?bank dealings|foreign exchange risk|\bFEMA\b|"
                r"forex (?:regulation|reserve))\b", re.I)),
    ("bank_resolution",
     re.compile(r"\b(amalgamation|merger of|moratorium|licence (?:cancell|revok)|"
                r"all-?inclusive directions|prompt corrective action|\bPCA\b)\b", re.I)),
    ("liquidity_operation",
     re.compile(r"\b(auction|open market operation|\bOMO\b|variable rate (?:repo|"
                r"reverse repo)|\bVRR\b|\bVRRR\b|money market operations|"
                r"underwriting)\b", re.I)),
    ("debt_instrument_event",
     re.compile(r"\b(sovereign gold bond|\bSGB\b|premature redemption|"
                r"government stock|treasury bill|state government securities)\b", re.I)),
    ("statistical_release",
     re.compile(r"\b(weekly statistical supplement|bulletin|balance of payments|"
                r"statistical (?:release|supplement)|data release|"
                r"survey of consumer finances|economic projections|"
                r"summary of economic projections)\b", re.I)),
    # --- trade and industrial
    # Trade remedies come FIRST: "anti-dumping" appears in both, and a
    # determination is a stage in a proceeding rather than a new tariff.
    ("trade_remedy_determination",
     re.compile(r"\b(?:anti-?dumping|countervailing|less than fair value|\bLTFV\b|"
                r"critical circumstances|sunset review|five-?year reviews?|"
                r"administrative review|trade remed(?:y|ies))\b"
                # "Preliminary/Final Affirmative Determination" is the Federal
                # Register's own short form and carries no other word to key
                # on; without it the short titles fell through to "other".
                r"|\b(?:preliminary|final)\s+(?:affirmative|negative)\s+"
                r"(?:\w+\s+){0,3}determinations?\b"
                # The USITC's own form: "<Product> From <Countries>;
                # Determinations", with no duty word anywhere in the title.
                # Missing it hid real Indian trade remedies, including oil
                # country tubular goods — steel pipe for wells.
                # The country list itself contains commas ("From India,
                # South Korea, Turkey, Ukraine, and Vietnam;"), so the span
                # may not exclude them — only the terminator may.
                r"|\bfrom\s+\w[^;]{0,120}?[;,]\s*determinations?\b"
                r"|\bdeterminations?\b(?=.{0,80}\b(?:dut(?:y|ies)|dumping|"
                r"subsid(?:y|ies)|investigation|review)\b)"
                r"|\b(?:dut(?:y|ies)|dumping|subsid(?:y|ies)|investigation|review)\b"
                r"(?=.{0,80}\bdeterminations?\b)", re.I)),
    ("tariff_announcement",
     re.compile(r"\b(tariff|safeguard dut(?:y|ies)|anti-?dumping)\b", re.I)),
    ("import_duty_change",
     re.compile(r"\bimport dut(?:y|ies)\b|\bcustoms dut(?:y|ies)\b", re.I)),
    ("export_restriction",
     re.compile(r"\bexport (?:ban|curbs?|restrictions?|controls?|dut(?:y|ies)|quota)\b", re.I)),
    ("policy_rate_decision",
     re.compile(r"\b(repo rate|policy rate|reverse repo|bank rate)\b", re.I)),
    ("production_halt",
     re.compile(r"\b(halt(?:s|ed)?|suspend(?:s|ed)?|shut ?down|stoppage|strike|lockout)\b", re.I)),
    ("facility_incident",
     re.compile(r"\b(fire|explosion|blast|accident|collapse|flood(?:ing|ed)?)\b", re.I)),
    ("logistics_disruption",
     # A mode of transport is not an event. Keying on the bare words made
     # "Advance Traveler Information for Rail" -- a passenger-rail
     # rulemaking -- a logistics disruption, and would do the same to any
     # document that merely mentions a port. `congestion` and `blockade`
     # stay standalone because they are disruptions by themselves; a
     # transport noun now needs disruption vocabulary with it, in either
     # order and within a sentence's reach.
     re.compile(r"\b(?:congestion|blockade)\b"
                r"|\b(?:ports?|shipping|railways?|rail|freight|berth|"
                r"terminal|harbour|harbor)\b"
                r"(?=.{0,80}\b(?:closed?|closures?|suspend(?:ed|s|ing)?|"
                r"suspension|halt(?:ed|s|ing)?|strikes?|lockout|"
                r"derail(?:ment|ed)|backlog|stranded|divert(?:ed|ing)|"
                r"diversion|disrupt(?:ed|ion|ions)|delays?|bottleneck|"
                r"shut(?:down)?)\b)"
                r"|\b(?:closed?|closures?|suspend(?:ed|s|ing)?|suspension|"
                r"halt(?:ed|s|ing)?|strikes?|lockout|derail(?:ment|ed)|"
                r"backlog|stranded|divert(?:ed|ing)|diversion|"
                r"disrupt(?:ed|ion|ions)|delays?|bottleneck|shut(?:down)?)\b"
                r"(?=.{0,80}\b(?:ports?|shipping|railways?|rail|freight|"
                r"berth|terminal|harbour|harbor)\b)", re.I)),
    ("capacity_expansion",
     re.compile(r"\b(expansion|commission(?:ed|ing)|new (?:plant|line|unit))\b", re.I)),
    ("subsidy_change",
     re.compile(r"\b(subsidy|incentive scheme|PLI)\b", re.I)),
    # Tested BEFORE the generic regulatory rule: these notices carry
    # "order" and sometimes "penalty", so the broader pattern would absorb
    # them and lose the recovery stage that is the whole point.
    ("securities_enforcement_action",
     re.compile(r"\brecovery certificates?\b|\bRC\s*No\.?\s*\d+|"
                r"\bRC\s+\d+\s+of\s+\d{4}\b|"
                r"\bnotice of attachment\b|\brelease of attachment\b|"
                r"\bprohibitory order\b|\bnotice of demand\b|"
                r"\bconfirmatory order\b|\bexemption order\b|"
                r"\battachment of (?:immovable|movable) property\b", re.I)),
    ("regulatory_action",
     # Supervisory acts, enforcement and authorisations alike. The Fed's
     # bulletin is largely these, and leaving them in `other` made that
     # bucket mean "unprocessed" rather than "we do not know what this is".
     re.compile(r"\b(penalt(?:y|ies)|show-?cause|licence (?:suspend|cancel)|"
                r"enforcement actions?|cease and desist|consent order|"
                r"approval of (?:the )?application|debarment order|"
                r"requests? public comment|comment period|"
                # Rulemaking: a core regulatory class and most of what a
                # federal register publishes. "The Commission is proposing to
                # amend the rule" was falling through to `other`.
                r"notice of proposed rulemaking|proposed rule|"
                r"propos(?:es|ing|ed) to (?:amend|adopt|rescind|revise)|"
                r"final rule|interim final rule)\b", re.I)),
)

PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:per ?cent|%)", re.I)
TONNES = re.compile(r"(\d+(?:\.\d+)?)\s*(million tonnes|mt|tonnes|mtpa)\b", re.I)
#: Imported, not redefined: the frame decides whether a measure is in force
#: from this same pattern, and two copies would drift.
from seraph.news.event_frames import EFFECTIVE  # noqa: E402

#: Identifiers a document uses to cite ITSELF or the instrument it changes.
#:
#: Supersession used to work only when a caller already supplied the link,
#: so an old duty order and a separately published revocation of it sat in
#: the store unconnected and the order stayed reported as in force. The
#: linkage has to come from something the documents share, and the only
#: honest candidate is an identifier they both print. Matching on similar
#: TITLES is explicitly not done here: "Certain Hot-Rolled Steel From
#: India" heads a proposal, a preliminary determination, a final
#: determination, an order, three administrative reviews and a revocation,
#: and merging them on the title would silently collapse six legal facts
#: into one.
INSTRUMENT_IDS = (
    # Commerce/ITA antidumping (A-) and countervailing (C-) case numbers.
    ("ita_case", re.compile(r"\b([AC]-\d{3}-\d{3})\b")),
    # USITC investigation numbers, with or without the "Inv. No." prefix.
    ("usitc_investigation",
     re.compile(r"\b(?:Inv(?:\.|estigation)?\s*(?:Nos?\.?)?\s*)?"
                r"(\d{3}-TA-\d{2,4})\b", re.I)),
    # SEBI recovery certificates.
    ("recovery_certificate",
     re.compile(r"\bRC\s*(?:No\.?)?\s*(\d+(?:\s*of\s*\d{4})?)", re.I)),
    # CBIC/DGFT notifications and circulars.
    ("notification",
     re.compile(r"\b(?:Notification|Circular)\s+No\.?\s*"
                r"([\w][\w/.()-]{2,40})", re.I)),
    # Federal Register document numbers.
    ("federal_register", re.compile(r"\b(\d{4}-\d{5,6})\b")),
)

#: Legal stages, in the order a proceeding passes through them. A later
#: document on the SAME instrument replaces an earlier one; a terminating
#: stage replaces any of them.
STAGE_LADDER = {"unknown": 0, "consultation": 1, "announced": 1,
                "proposed": 1, "adopted": 2, "effective": 3}
TERMINATING_STAGES = frozenset({"repealed", "expired", "suspended"})

#: Vocabulary that says this document CHANGES another instrument. Used only
#: to decide whether an unlinked document deserves a warning — never to
#: create a link.
AMENDS = re.compile(
    r"\b(?:revocation|revok(?:es|ed|ing)|repeal(?:s|ed|ing)?|rescind(?:s|ed)?|"
    r"amendment|amend(?:s|ed|ing)|modif(?:y|ies|ied|ication)|"
    r"supersed(?:es|ed|ing)|terminat(?:es|ed|ion)|withdraw(?:s|n|al))\b", re.I)


def instrument_ids(text: str) -> tuple[str, ...]:
    """Identifiers the text cites, normalised. Never inferred from a title."""
    found = []
    for kind, pattern in INSTRUMENT_IDS:
        for match in pattern.finditer(text or ""):
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,;:").upper()
            if value:
                found.append(f"{kind}:{value}")
    return tuple(dict.fromkeys(found))


#: Shapes that look like an instruction to the application rather than news.
INJECTION = re.compile(
    r"(ignore (?:all |the )?(?:previous|above) instructions"
    r"|system prompt|you are now|</?script"
    r"|grant (?:me |the )?(?:admin|regulator|access)"
    r"|execute the following|run this command)", re.I)


@dataclass(frozen=True)
class Extraction:
    event: Event | None
    unresolved: tuple[str, ...]
    injection_detected: bool
    note: str | None = None


def scrub(text: str) -> tuple[str, bool]:
    """Neutralise instruction-shaped text before anything reads it.

    The content is kept — an article genuinely about prompt injection is still
    news — but the shapes are flattened so no downstream renderer or model
    treats them as directives, and the caller is told it happened.
    """
    if not text:
        return "", False
    found = bool(INJECTION.search(text))
    cleaned = INJECTION.sub(lambda m: "[redacted-directive]", text)
    cleaned = cleaned.replace("<", "&lt;").replace(">", "&gt;")
    return cleaned, found


def classify(text: str) -> tuple[EventType, re.Match | None]:
    if re.search(r'\b(?:publishes?|published) (?:an? )?annual report\b', text, re.I):
        return 'statistical_release', re.search(r'annual report', text, re.I)
    for event_type, pattern in EVENT_PATTERNS:
        match = pattern.search(text)
        if match:
            return event_type, match
    return "other", None


def extract(stories: list[Story], master: MasterData, *,
            sectors: dict[str, tuple[str, ...]] | None = None) -> Extraction:
    """Build one event from one syndication group.

    `stories` are the copies of a single story. Passing ten syndicated copies
    produces ONE event citing ten stories — which is what makes
    `Event.confirmations` meaningful.
    """
    if not stories:
        return Extraction(event=None, unresolved=(), injection_detected=False,
                          note="no stories supplied")
    primary = min(stories, key=lambda s: (s.first_seen_at or "", s.story_id))
    title, title_injection = scrub(primary.title)
    body, body_injection = scrub(primary.body or "")
    text = f"{title}. {body}".strip()
    injection = title_injection or body_injection

    event_type, match = classify(text)
    if primary.language == "hi":
        # The English rules find nothing in Devanagari, so the whole feed fell
        # to `other`. The Hindi rules map to the SAME event vocabulary; the
        # caveat that this is keyword matching rather than comprehension is
        # carried on the frame, not hidden here.
        from seraph.news.hindi import classify_hindi
        hindi_type, _hindi_span = classify_hindi(text)
        if hindi_type != "other":
            event_type = hindi_type
    if primary.metadata.get("source_kind_hint") == "hazard_agency":
        event_type = "physical_hazard"
    # Semantic spans refer to the original permitted text, before display escaping.
    original_text = f"{primary.title}. {primary.body or ''}".strip()
    # `beneficiaries` and `constrained_parties` have existed on the frame
    # since it was written and nothing ever populated them, so every impact
    # reached the screen as one signed direction and the reader never saw the
    # other side of the same instrument.
    frame = frame_for(original_text, primary.story_id, event_type,
                      available_at=max(s.first_seen_at or '' for s in stories),
                      language=primary.language,
                      # The document's own statement of its status, separable
                      # from the body's account of how it got there.
                      title=primary.title,
                      # What the RECORD holds, so a limitation cannot claim
                      # the body is unavailable when it is on file.
                      body_retained=bool(primary.body))
    if frame is not None:
        from dataclasses import replace as _replace
        from seraph.news.opposing import opposing_parties
        _view = opposing_parties(type("E", (), {
            "event_type": event_type, "frame": frame})())
        if _view.constrained or _view.benefiting:
            frame = _replace(frame, beneficiaries=tuple(_view.benefiting),
                             constrained_parties=tuple(_view.constrained))

    evidence: list[EvidenceSpan] = []
    if match:
        evidence.append(EvidenceSpan(story_id=primary.story_id, start=match.start(),
                                     end=match.end(), text=match.group(0),
                                     field="event_type"))

    unresolved: list[str] = []
    actors: list[str] = []
    affected: list[str] = []
    locations: list[tuple[str, str]] = []
    on_day = (primary.first_seen_at or "")[:10] or None
    for mention in _candidate_names(text):
        # T11/T13: a mention may name an entity, a facility OR a place, and
        # only the last two can ever be drawn on a map. Resolving entities
        # alone is why a sourced event could never reach the globe however
        # complete the registry was. Order matters: the most specific claim
        # wins, so a named plant is the plant and not the city it sits in.
        resolution = master.resolve(mention, on=on_day)
        field = "affected"
        if resolution.status != "resolved":
            asset = master.resolve_asset(mention)
            if asset.status == "resolved":
                resolution, field = asset, "affected_asset"
            elif asset.status == "ambiguous":
                resolution = asset
        if resolution.status != "resolved":
            found = master.resolve_place(mention)
            if found.status == "resolved":
                resolution, field = found, "affected_place"
            elif found.status == "ambiguous" and resolution.status != "ambiguous":
                resolution = found
        if resolution.status == "resolved":
            # A located record is a MENTION until something evidences its
            # role. The RBI corpus names Mumbai in a speech title; the venue
            # of a speech is not an affected location, and a name match
            # cannot tell the two apart.
            if field in ("affected_place", "affected_asset"):
                locations.append((resolution.entity_id, "mentioned"))
            else:
                # Mention alone does not establish who is economically affected.
                entity = master.entities.get(resolution.entity_id)
                if entity and entity.kind == "government_body":
                    actors.append(resolution.entity_id)
                elif (entity and entity.kind == "issuer"
                      and primary.metadata.get("title_is_filing_entity")):
                    # On an exchange filing feed the title IS the filing
                    # entity -- that is the feed's contract, not a name
                    # spotted in prose. The issuer is therefore the subject of
                    # the document, which is a stronger claim than a mention
                    # and a weaker one than being economically affected: the
                    # SUBJECT of the announcement is not retained, so nothing
                    # here says what happened to them.
                    actors.append(resolution.entity_id)
            span = _span(text, mention)
            if span:
                evidence.append(EvidenceSpan(story_id=primary.story_id, start=span[0],
                                             end=span[1], text=mention,
                                             field=field))
        elif resolution.status == "ambiguous":
            unresolved.append(
                f"{mention!r} matches {len(resolution.candidates)} records "
                f"({', '.join(resolution.candidates[:3])}); not linked")
        # unknown mentions are simply not records we know about

    mentioned_entities = []
    exposure_origins = []
    for entity in master.entities.values():
        if not entity.active_on(on_day or '9999-12-31'):
            continue
        for name in (entity.name,) + entity.aliases:
            hit = re.search(rf"\b{re.escape(name)}\b", original_text, re.I)
            if not hit or master.resolve(name, on=on_day).status != "resolved":
                continue
            mentioned_entities.append(entity.entity_id)
            # Direct grammatical subject of an operational change, not a quote/mention.
            tail = original_text[hit.end():hit.end()+65]
            if (frame.assertion_status == 'confirmed_statement'
                and event_type in ('production_halt', 'facility_incident', 'capacity_expansion')
                and re.match(r'\s+(?:halts?|suspends?|resumes?|reopens?|commissions?|inaugurates?)\b', tail, re.I)):
                affected.append(entity.entity_id)
                if entity.sector:
                    affected.append('sector:' + entity.sector)
            break
    # A trade remedy's subject origins: the countries whose goods the
    # instrument covers. Resolved against the curated place registry only, so
    # an unknown country produces nothing rather than a guess.
    if event_type == 'trade_remedy_determination':
        header = SUBJECT_ORIGIN.search(original_text)
        if header:
            for candidate in re.split(r",|\band\b", header.group(1)):
                name = candidate.strip().removeprefix('the ').strip()
                if not name:
                    continue
                found = master.resolve_place(name)
                if found.status == 'resolved' and found.entity_id not in exposure_origins:
                    exposure_origins.append(found.entity_id)
                    # Recorded as a ROLE, not just an exposure seed.
                    # `exposure_origins` also carries the issuer-jurisdiction
                    # seed, and "the goods come from here" and "the issuing
                    # authority is here" are different claims that must not
                    # share a label on the map.
                    locations.append((found.entity_id, 'subject_origin'))
                    evidence.append(EvidenceSpan(
                        story_id=primary.story_id,
                        start=header.start(1), end=header.end(1),
                        text=header.group(1)[:120], field='subject_origin'))

    # Issuer jurisdiction seeds a scoped exposure query, never an occurrence dot.
    source_place = master.origin_of(primary.source_id)
    if (source_place and source_place.get('basis') == 'jurisdiction'
        # A trade remedy has an issuing jurisdiction like any other
        # instrument: the authority that imposes the duty is also the
        # destination market the duty applies in. Leaving the class out
        # meant every determination reached the scenario path with no
        # destination, and the arithmetic refused for a reason that was
        # about this omission rather than about the document.
        and event_type in ('export_restriction', 'tariff_announcement',
                           'import_duty_change', 'trade_remedy_determination')
        and frame.assertion_status == 'confirmed_statement'):
        exposure_origins.append(source_place['place_id'])
        locations.append((source_place['place_id'], 'issuer_jurisdiction'))
    frame = replace(frame, mentioned_entities=tuple(sorted(set(mentioned_entities))))
    if frame.assertion_status == 'confirmed_statement' and frame.action in ('stop', 'resume', 'start'):
        for asset in master.assets.values():
            if re.search(rf"\b{re.escape(asset.name)}\b", original_text, re.I) and event_type in ('production_halt', 'facility_incident', 'capacity_expansion'):
                affected.append(asset.asset_id)
                locations = [(n,r) for n,r in locations if n != asset.asset_id]
                locations.append((asset.asset_id, 'occurrence'))
    quantities: list[tuple[str, float, str]] = []
    for pattern, unit in ((PERCENT, "percent"), (TONNES, "tonnes")):
        for found in pattern.finditer(text):
            value = float(found.group(1))
            actual_unit = unit
            if unit == 'tonnes' and found.group(2).lower() in ('million tonnes','mtpa'):
                value *= 1_000_000
                if found.group(2).lower() == 'mtpa': actual_unit = 'tonnes_per_year' 
            subject = _subject_before(text, found.start())
            if subject is None:
                unresolved.append(
                    f"quantity {found.group(0)!r} has no recognised subject; "
                    f"not recorded as a measured quantity")
                continue
            quantities.append((subject, value, actual_unit))
            evidence.append(EvidenceSpan(story_id=primary.story_id,
                                         start=found.start(), end=found.end(),
                                         text=found.group(0), field="quantity"))

    # The frame already read the start date with the shared parser; reading
    # it a second time here is how the two came to disagree, with the frame
    # recognising "1 December 2026" and the timing silently dropping it.
    effective_at = None
    effective_match = EFFECTIVE.search(text)
    if effective_match:
        evidence.append(EvidenceSpan(story_id=primary.story_id,
                                     start=effective_match.start(),
                                     end=effective_match.end(),
                                     text=effective_match.group(0),
                                     field="effective_at"))
    stated = getattr(frame, "effective_text", None)
    if frame is not None and frame.effective_at:
        if frame.effective_precision == "day":
            effective_at = frame.effective_at
        else:
            # A month establishes a WINDOW. Publishing its first instant as
            # the effective date would claim a day the document never named.
            unresolved.append(
                f"effective date {stated!r} is stated only to "
                f"{frame.effective_precision} precision "
                f"({frame.effective_at[:10]}..{frame.effective_until[:10]}); "
                f"no exact start is recorded")
    elif stated:
        unresolved.append(
            f"effective date {stated!r} is not in a form this extractor parses; "
            f"left unset rather than guessed")

    sector_hits = []
    for sector, words in (sectors or {}).items():
        if any(re.search(rf"\b{re.escape(w)}\b", text, re.I) for w in words):
            # Only an explicit measure ON the target establishes applicability.
            if re.search(rf"\b(?:duty|tariff|ban)\s+(?:imposed\s+)?on\s+(?:{'|'.join(re.escape(w) for w in words)})\b", original_text, re.I):
                sector_hits.append(f"sector:{sector}")

    cited = instrument_ids(original_text)
    for value in cited:
        found = re.search(re.escape(value.split(':', 1)[1]), original_text, re.I)
        if found:
            evidence.append(EvidenceSpan(story_id=primary.story_id,
                                         start=found.start(), end=found.end(),
                                         text=found.group(0),
                                         field="instrument_id"))

    timing = Timing(first_seen_at=primary.first_seen_at,
                    published_at=primary.timing.published_at,
                    occurred_at=primary.metadata.get("occurred_at"),
                    effective_at=effective_at,
                    # Carried from the story, never re-derived: an event
                    # built from a forthcoming Federal Register document has
                    # a publication date that has not arrived yet, and
                    # dropping the flag here made the event unconstructible.
                    publication_scheduled=primary.timing.publication_scheduled)
    group = primary.syndication_group or primary.story_id
    event = Event(
        event_id=event_identity(event_type, group,
                                (primary.first_seen_at or "")[:10]),
        event_type=event_type, headline=title, timing=timing,
        stories=tuple(sorted(s.story_id for s in stories)),
        actors=tuple(actors),
        locations=tuple(dict.fromkeys(locations)),
        affected=tuple(dict.fromkeys(affected + sector_hits)),
        quantities=tuple(quantities), evidence=tuple(evidence),
        unresolved=tuple(unresolved), extractor_version=EXTRACTOR_VERSION,
        frame=frame, reporting_origins=(group,), exposure_origins=tuple(exposure_origins),
        instrument_ids=cited)
    note = None
    if event_type == "other":
        note = ("no event pattern matched; recorded as `other` rather than "
                "forced into a category")
    return Extraction(event=event, unresolved=tuple(unresolved),
                      injection_detected=injection, note=note)


def _candidate_names(text: str) -> list[str]:
    """Capitalised runs — the cheap, explainable name candidate rule."""
    out, seen = [], set()
    for match in re.finditer(r"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,3})", text):
        name = match.group(1).strip()
        if len(name) < 3 or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


def _span(text: str, needle: str) -> tuple[int, int] | None:
    index = text.find(needle)
    return (index, index + len(needle)) if index >= 0 else None


def _subject_before(text: str, position: int) -> str | None:
    """The noun a quantity is about, if the sentence makes it obvious."""
    window = text[max(0, position - 60):position].lower()
    for subject in ("import duty", "export duty", "customs duty", "tariff",
                    "repo rate", "policy rate", "capacity", "output",
                    "production", "price"):
        if subject in window:
            return subject.replace(" ", "_")
    return None


#: How strongly a clause asserts its claim. When one document makes the same
#: claim more than once, the WEAKEST assertion is what the document as a
#: whole establishes: a headline that says a plant halted and a body that
#: says the company denies it is not a halt plus a denial, it is a contested
#: claim, and reporting the first half on its own is the worse of the two
#: readings a reader could take away.
ASSERTION_RANK = {
    'denied': 0, 'disputed': 1, 'hypothetical': 2,
    'reported_unconfirmed': 3, 'confirmed_statement': 4,
}


def _claim_key(event) -> tuple:
    """What claim a clause makes, ignoring HOW strongly it makes it.

    Deliberately coarse and deliberately explainable: the class of event,
    the action, and the registered entities named. Two sentences agreeing
    on all three are the same claim about the same parties — a repetition
    or a contradiction, never two independent events. The assertion status
    is excluded on purpose, so a denial lands in the same group as the
    claim it denies instead of becoming an event of its own.
    """
    frame = getattr(event, 'frame', None)
    return (event.event_type,
            getattr(frame, 'action', None),
            tuple(sorted(getattr(frame, 'mentioned_entities', ()) or ())))


def extract_events(stories: list[Story], master: MasterData, *, sectors=None) -> list[Extraction]:
    """Independent sentences may emit independent frames with original-text offsets.

    Single-frame extract remains the compatibility API. This adapter splits only
    sentence boundaries/newlines, never decimal points or semicolons qualifying a
    proposal. Cross-sentence/coreference claims abstain rather than being joined.

    Two defects this adapter used to have, and they are the same defect:

    * **A denial became a second event.** "Tata Steel halts production"
      followed by a body denying the halt produced a CONFIRMED halt with
      affected targets, plus a separate denial that qualified nothing. The
      screen then showed an adverse, confirmed event the document itself
      contradicts.
    * **A repetition became a second event.** The same claim in the title
      and in the first body sentence produced two event ids and two sets of
      target estimates, so the event count measured matching sentences
      rather than events.

    Both are fixed by reconciling the document BEFORE splitting: clauses are
    grouped by the claim they make, and a document that turns out to make
    one claim is extracted as one event over its whole text — which is also
    where the assertion rules already prefer a denial over a bare assertion.
    """
    if not stories:
        return []
    primary = min(stories, key=lambda s: (s.first_seen_at or '', s.story_id))
    text = f"{primary.title}. {primary.body or ''}".strip()
    clauses = list(re.finditer(r'.+?(?:[.!?](?=\s|$)|\n|$)', text))
    matches = [(m, classify(m.group())[0]) for m in clauses if classify(m.group())[0] != 'other']
    if len(matches) <= 1:
        return [extract(stories, master, sectors=sectors)]

    built = []
    for index, (match, _) in enumerate(matches):
        local = replace(primary, title=match.group().strip(), body=None,
                        syndication_group=(primary.syndication_group or primary.story_id) + f':clause:{index}')
        result = extract([local], master, sectors=sectors)
        offset = match.start() + len(match.group()) - len(match.group().lstrip())
        built.append((index, offset, result))

    # --- reconcile first, split second ---------------------------------
    groups: dict[tuple, list] = {}
    for item in built:
        groups.setdefault(_claim_key(item[2].event), []).append(item)

    if len(groups) <= 1:
        # The document makes ONE claim, however many sentences make it.
        # Extracted over the whole text so the denial, the repetition and
        # the detail ("...at Kalinganagar") are all evidence for the single
        # event they describe, with offsets into the text as received.
        single = extract(stories, master, sectors=sectors)
        if single.event is not None and len(built) > 1:
            extra = len(built) - 1
            single = replace(single, event=replace(
                single.event, frame=replace(
                    single.event.frame,
                    unknowns=single.event.frame.unknowns + (
                        f'{extra} further sentence(s) in this document make '
                        f'the same claim about the same parties; they are '
                        f'repeated evidence for one event, not separate '
                        f'events',))))
        return [single]

    out = []
    for members in groups.values():
        # The weakest assertion in the group is what the document
        # establishes about this claim; a confirmed sentence standing beside
        # a denial of the same claim does not make the claim confirmed.
        index, offset, result = min(
            members,
            key=lambda m: (ASSERTION_RANK.get(
                getattr(m[2].event.frame, 'assertion_status', ''), 9), m[0]))
        event = result.event

        def shift(span, _offset=offset):
            return replace(span, start=span.start+_offset, end=span.end+_offset)

        # Every member's evidence, each shifted by its OWN offset: a reader
        # must be able to see the repeated or contradicting sentence, not
        # just the one that won.
        supporting = tuple(
            replace(span, start=span.start+other_offset, end=span.end+other_offset)
            for other_index, other_offset, other in members
            if other_index != index
            for span in other.event.frame.evidence)
        notes = ()
        if len(members) > 1:
            statuses = sorted({getattr(m[2].event.frame, 'assertion_status', '')
                               for m in members})
            notes = (f'{len(members) - 1} further sentence(s) in this '
                     f'document make the same claim about the same parties '
                     f'(assertion status seen: {", ".join(statuses)}); the '
                     f'weakest is what the document establishes',)
        frame = replace(event.frame,
            evidence=tuple(shift(e) for e in event.frame.evidence) + supporting,
            quantities=tuple(replace(q,evidence=tuple(shift(e) for e in q.evidence)) for q in event.frame.quantities),
            unknowns=event.frame.unknowns + notes,
            representation_hash=__import__('hashlib').sha256(text.encode()).hexdigest())
        event = replace(event, frame=frame, evidence=tuple(shift(e) for e in event.evidence),
                        stories=tuple(sorted(s.story_id for s in stories)))
        out.append(replace(result,event=event))
    return out
