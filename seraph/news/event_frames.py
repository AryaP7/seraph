"""C13 — NI02/03 evidenced event frames, quantities and assertion semantics.

Offsets address ``title + '. ' + body`` (the permitted text representation),
not HTML bytes. Rules are English-only; other languages explicitly abstain.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
import re

from seraph.news.model import EvidenceSpan
from seraph.news.scope import scope_of

VERSION = 'event-rules/2.1'

@dataclass(frozen=True)
class QuantityV2:
    measure: str
    unit: str
    old_level: Decimal | None = None
    new_level: Decimal | None = None
    delta: Decimal | None = None
    denominator: str | None = None
    scope: str | None = None
    evidence: tuple[EvidenceSpan, ...] = ()

@dataclass(frozen=True)
class EventFrameV2:
    revision_id: str
    assertion_status: str
    action: str
    policy_status: str
    quantities: tuple[QuantityV2, ...] = ()
    mentioned_entities: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    beneficiaries: tuple[str, ...] = ()
    constrained_parties: tuple[str, ...] = ()
    evidence: tuple[EvidenceSpan, ...] = ()
    unknowns: tuple[str, ...] = ()
    extraction_method: str = VERSION
    schema_version: str = 'EventFrameV2/2'
    representation_hash: str = ''
    available_at: str | None = None
    #: The start date the document states, at the precision it states it.
    #: `effective_precision` is 'day' or 'month'; `effective_text` is the
    #: words that were read. A date that was RECOGNISED but could not be
    #: converted leaves `effective_at` None with `effective_text` set, which
    #: is the difference between "no date was given" and "a date was given
    #: and we could not read it" — the second must abstain, not proceed.
    effective_at: str | None = None
    effective_until: str | None = None      # exclusive end of the precision window
    effective_precision: str | None = None
    effective_text: str | None = None
    #: An instrument that ENDS another measure from a stated date. Set when
    #: the end has NOT arrived at `available_at`: the measure being revoked
    #: is still applying, so neither "ended" nor a favourable sign is true
    #: yet.
    pending_termination: str | None = None
    #: Product, country and party carve-outs read from the retained text.
    #: Empty is not "no exclusions" — `scope_determined` says whether the
    #: text spoke about scope at all.
    excluded_countries: tuple[str, ...] = ()
    excluded_products: tuple[str, ...] = ()
    excluded_parties: tuple[str, ...] = ()
    scope_determined: bool = False
    #: A carve-out was DETECTED. It may or may not have been named above;
    #: detected-but-unnamed still caps confidence, it just cannot suppress.
    scope_carve_out: bool = False
    scope_note: str | None = None

    def describe(self):
        return json.loads(json.dumps(asdict(self), default=str))

#: Sentences that appear verbatim in whole classes of notice and describe the
#: statute being complied with, not anything the document does. They are
#: removed before the action and stage rules run, because a rule cannot tell
#: "reduce paperwork burden" from a reduction that matters.
BOILERPLATE = re.compile(
    r"as part of (?:our|its) continuing effort to reduce paperwork and "
    r"respondent burden[^.]*\.|"
    r"as required by the paperwork reduction act(?: of \d{4})?[^.]*\.|"
    r"in (?:accordance|compliance) with the paperwork reduction act[^.]*\.",
    re.I)

ACTION_RULES = (
    ('cancel', r'\bcancel(?:s|led|ed|lation)?\b'),
    ('unchanged', r'\b(?:unchanged|holds?|maintains?)\b'),
    ('withdraw', r'\b(?:withdraws?|withdrawn|withdrawal|repeals?|revokes?)\b'),
    ('resume', r'\b(?:resumes?|resumed|reopens?|reopened|restarts?|restarted)\b'),
    ('decrease', r'\b(?:cuts?|reduces?|reduced|reduction|lowers?|lowered|decreases?)\b'),
    ('increase', r'\b(?:raises?|raised|increases?|increased|hikes?|hiked)\b'),
    ('stop', r'\b(?:halt(?:s|ed)?|suspend(?:s|ed)?|shutdown|shut down|stoppage|closes?|closed)\b'),
    ('extend', r'\b(?:extends?|extended)\b'),
    ('start', r'\b(?:implement|inaugurates?|starts?|started|commissions?|commissioned|launches?|launched|imposes?|imposed|introduces?|introduced)\b'),
    ('announce', r'\b(?:announces?|announced|propos(?:e|es|ed|ing)|consultation)\b'),
)
#: Date forms this extractor converts, and the precision each establishes.
#:
#: The pattern used to RECOGNISE "1 December 2026" and then convert only
#: `YYYY-MM-DD`, so on 18 October a document reading "effective from
#: 1 December 2026" produced `effective_at=null` — and lifecycle reads a
#: missing start date as "no later start", i.e. in force today. A named month
#: is not an unreadable date; it is the commonest way an official document
#: writes one.
MONTHS = {}
for _index, _name in enumerate(
        ('january', 'february', 'march', 'april', 'may', 'june', 'july',
         'august', 'september', 'october', 'november', 'december'), start=1):
    MONTHS[_name] = _index
    MONTHS[_name[:3]] = _index
MONTHS['sept'] = 9

#: Ordered longest-first: "1 December 2026" must not be read as the bare
#: month-and-year "December 2026" with a stray digit beside it.
DATE_TEXT = (r"(?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{4}"
             r"|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
             r"|\d{4}-\d{2}-\d{2}"
             r"|[A-Za-z]{3,9}\.?,?\s+\d{4})")

#: An explicit effective date. Defined HERE because the frame needs it to
#: decide whether a measure is in force yet, and imported by the extractor so
#: the two cannot drift apart. The trailing alternative matches the PHRASE
#: without a readable date ("effective upon publication"), because a stated
#: start we cannot convert must abstain rather than be treated as absent.
EFFECTIVE = re.compile(
    r"\beffective\s+(?:from\s+|on\s+|as\s+of\s+|beginning\s+|commencing\s+)?"
    r"(" + DATE_TEXT + r")", re.I)

#: A stated start that names no convertible date. Matched separately so the
#: two cases stay distinguishable in the evidence.
EFFECTIVE_VAGUE = re.compile(
    r"\b(?:effective|takes?\s+effect|shall\s+take\s+effect|in\s+force)\s+"
    r"((?:upon|on|from|after)\s+[^.;,]{3,60})", re.I)

#: A stated END: an expiry, a revocation or a sunset with a date. A measure
#: whose revocation takes effect next month has not stopped applying today,
#: and reporting it as `ended` is the mirror of the start-date defect.
ENDS = re.compile(
    r"\b(?:expir(?:es?|ing|ation)|terminat(?:es?|ing|ion)|revo(?:ked|cation)"
    r"|repealed|withdrawn|sunsets?|ceases?\s+to\s+(?:apply|have\s+effect)"
    r"|valid\s+(?:until|through|till))"
    r"(?:\s+(?:on|from|as\s+of|effective|with\s+effect\s+from|until|through"
    r"|till|after))?\s*(" + DATE_TEXT + r")", re.I)


@dataclass(frozen=True)
class ParsedDate:
    """A date at the precision the document actually stated.

    `starts` is the first instant the stated date can mean and `ends` the
    first instant after it, so a month-precision date is a WINDOW rather
    than a guessed first-of-the-month. A decision time inside that window
    cannot establish whether the date has arrived, and must say so.
    """

    starts: str
    ends: str
    precision: str
    text: str


def _ist(year: int, month: int, day: int) -> str:
    from datetime import date, timedelta
    return date(year, month, day).isoformat() + 'T00:00:00+05:30'


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def parse_date(raw: str | None) -> ParsedDate | None:
    """Convert a stated date, or return None rather than guess.

    None means RECOGNISED-BUT-UNREADABLE wherever the caller already knows a
    date phrase was present. The caller must abstain on that, never treat it
    as "no date was stated".
    """
    if not raw:
        return None
    text = raw.strip().rstrip('.,;')
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        year, month, day = (int(g) for g in iso.groups())
        try:
            start = _ist(year, month, day)
        except ValueError:
            return None
        from datetime import date, timedelta
        return ParsedDate(start,
                          (date(year, month, day) + timedelta(days=1)
                           ).isoformat() + 'T00:00:00+05:30', 'day', text)
    dmy = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})",
                       text, re.I)
    mdy = re.fullmatch(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})",
                       text, re.I)
    my = re.fullmatch(r"([A-Za-z]{3,9})\.?,?\s+(\d{4})", text, re.I)
    if dmy:
        day, name, year = int(dmy[1]), dmy[2].lower(), int(dmy[3])
    elif mdy:
        name, day, year = mdy[1].lower(), int(mdy[2]), int(mdy[3])
    elif my:
        name, year = my[1].lower(), int(my[2])
        month = MONTHS.get(name)
        if month is None:
            return None
        nyear, nmonth = _next_month(year, month)
        try:
            return ParsedDate(_ist(year, month, 1), _ist(nyear, nmonth, 1),
                              'month', text)
        except ValueError:
            return None
    else:
        return None
    month = MONTHS.get(name)
    if month is None:
        return None
    try:
        from datetime import date, timedelta
        return ParsedDate(_ist(year, month, day),
                          (date(year, month, day) + timedelta(days=1)
                           ).isoformat() + 'T00:00:00+05:30', 'day', text)
    except ValueError:
        return None


#: What a stated date establishes about a decision time.
ARRIVED, FUTURE, UNCERTAIN, UNKNOWN = 'arrived', 'future', 'uncertain', 'unknown'


def arrival(parsed: ParsedDate | None, as_of: str | None) -> str:
    """Has the stated date arrived by `as_of`? Never guessed.

    A month-precision date whose window contains `as_of` returns
    `uncertain`: the document did not say which day, so neither answer is
    established and the caller must abstain.
    """
    if parsed is None or not as_of:
        return UNKNOWN
    if as_of < parsed.starts:
        return FUTURE
    if parsed.precision == 'day':
        # The document named the day, so the window is not a question:
        # "effective from 1 June" applies from the first instant of 1 June.
        return ARRIVED
    # Coarser than a day. Only a decision time past the whole window
    # establishes that the start has arrived.
    return ARRIVED if as_of >= parsed.ends else UNCERTAIN

NUM = r'(\d+(?:\.\d+)?)'
PERCENT = r'(?:%|per\s*cent)'
LEVELS = re.compile(r'\bfrom\s+'+NUM+r'\s*'+PERCENT+r'\s+to\s+'+NUM+r'\s*'+PERCENT,re.I)
BPS = re.compile(NUM+r'\s*(?:basis points?|bps)\b',re.I)
RATE = re.compile(NUM+r'\s*'+PERCENT,re.I)


#: A title that states the document IS final. The body of such a notice
#: routinely narrates the proposal and hearing that preceded it, and a stage
#: rule reading that narration downgrades a decided action to a pending one --
#: the opposite of what the document says about itself.
FINALITY = re.compile(
    r"\b(?:final (?:rule|order|determination|results?|decision|action)|"
    r"final affirmative|final negative|debarment order|duty order)\b", re.I)

#: Stages that mean "not decided yet". These are the ones a finality marker in
#: the title must override when they were found only in the body.
PENDING_STAGES = frozenset({'proposed', 'consultation'})


def frame_for(text, story_id, event_type, *, available_at=None, language='en',
              title=None, body_retained=None):
    digest=hashlib.sha256(text.encode()).hexdigest()
    revision='rev_'+hashlib.sha256((digest+VERSION+event_type).encode()).hexdigest()[:24]
    spans=[]
    # Statutory boilerplate is BLANKED, not removed: every evidence span is an
    # offset into the text the source actually sent, so deleting characters
    # would silently move every span after the cut.
    searchable=BOILERPLATE.sub(lambda m:' '*len(m.group(0)),text)
    def span(match, field):
        s=EvidenceSpan(story_id,match.start(),match.end(),match.group(),field)
        spans.append(s)
        return s
    def choose(rules, default, field):
        for value, pattern in rules:
            match=re.search(pattern,searchable,re.I)
            if match:
                span(match,field)
                return value
        return default
    if language != 'en':
        # A narrow Hindi rule set now reads a few nouns (seraph/news/hindi.py).
        # It is NOT comprehension, so the assertion status stays
        # `reported_unconfirmed` whatever it matched, and the caveat naming
        # the rule set travels with the frame. Any other language still
        # abstains entirely.
        from seraph.news.hindi import CAVEAT, classify_hindi, is_hindi
        if language == 'hi' and is_hindi(text):
            matched, span_text = classify_hindi(text)
            notes = [CAVEAT]
            if matched == 'other':
                notes.append('no Hindi rule matched: this is not known to be '
                             'a market event, and is not known not to be')
            evidence = ()
            if span_text:
                found = re.search(re.escape(span_text), text)
                if found:
                    evidence = (EvidenceSpan(story_id, found.start(),
                                             found.end(), found.group(),
                                             'hindi_rule'),)
            return EventFrameV2(revision,'reported_unconfirmed','unknown',
                                'unknown', evidence=evidence,
                                unknowns=tuple(notes),
                                representation_hash=digest,
                                available_at=available_at)
        return EventFrameV2(revision,'reported_unconfirmed','unknown','unknown',
                            unknowns=('language unsupported by English rules',),
                            representation_hash=digest,available_at=available_at)
    assertion=choose((
        ('denied',r'\b(?:denies?|denied|denial|no (?:production )?halt|not (?:halted|shut|closed))\b'),
        ('hypothetical',r'\b(?:could|might|would|if)\b'),
        ('disputed',r'\b(?:disputed|conflicting reports)\b'),
        ('reported_unconfirmed',r'\b(?:alleged|unconfirmed|rumou?rs?)\b'),
    ),'confirmed_statement','assertion_status')
    # A trade-remedy proceeding has its own ladder, and reading it through the
    # generic rules collapses four different legal facts into "unknown": an
    # initiated investigation, a preliminary determination, a final
    # determination and an issued order are not the same measure.
    REMEDY_STAGES=(
        ('repealed',r'\b(?:revocation|revoked|terminat(?:ion|ed))\b'),
        # A review being SCHEDULED, INITIATED or INSTITUTED is a proceeding
        # being opened. Tested before the lapse rule because the procedural
        # cue is the more specific signal, and matched loosely between the
        # cue and the review word because the Federal Register writes
        # "Scheduling of FULL Five-Year Reviews".
        ('consultation',r'\b(?:scheduling|institution|initiation)\s+of\b'
                        r'(?=.{0,60}\b(?:sunset|five-?year|reviews?)\b)'),
        # `expired` asserts the measure NO LONGER APPLIES, so it needs
        # explicit lapse wording. A sunset review is the proceeding that
        # DECIDES whether an order continues and is published while the order
        # is still in force; keying `expired` on the review word itself
        # reported live duties as lapsed -- the opposite of the notice.
        ('expired',r'\b(?:expir(?:ed|es|ation)|lapsed?)\b'),
        ('effective',r'\b(?:dut(?:y|ies) order|antidumping duty order|'
                     r'countervailing duty order|imposition of)\b'),
        # Preliminary is tested BEFORE final, and final is guarded against a
        # postponement. A real corpus title reads "Preliminary Affirmative
        # Determination of Sales at Less-Than-Fair-Value, ..., Postponement
        # of Final Determination": it is a preliminary finding that names the
        # final stage it is deferring, and reading it as `adopted` turned
        # "no duty yet" into an adverse signal for Indian steel.
        ('announced',r'\bpreliminary\b(?=.{0,60}\b(?:determination|results?)\b)'
                     r'|\b(?:preliminary (?:affirmative|negative) determination|'
                     r'preliminary results)\b'),
        ('adopted',r'(?<!postponement of )(?<!extension of )'
                   r'(?<!scheduling of )\bfinal\b'
                   r'(?=.{0,60}\b(?:determination|results?)\b)'),
        ('consultation',r'\b(?:initiation of|initiating|opens? an? investigation|'
                        r'scheduling of|request for comments?)\b'),
    )
    #: An enforcement proceeding has stages, and they are the point: a
    #: release or completion LIFTS a constraint, an attachment imposes one.
    #: Release is tested first because "Release Order ... for RC 8924"
    #: contains the certificate vocabulary that imposes one.
    ENFORCEMENT_STAGES=(
        ('repealed',r'\b(?:release of attachment|release order|'
                    r'revocation|withdrawal of)\b'),
        ('expired',r'\b(?:completion of (?:RC|recovery certificate))\b'),
        ('effective',r'\b(?:notice of attachment|prohibitory order|'
                     r'attachment of (?:immovable|movable) property)\b'),
        ('announced',r'\b(?:notice of demand|show-?cause)\b'),
        ('adopted',r'\b(?:confirmatory order|exemption order)\b'),
    )
    if event_type=='securities_enforcement_action':
        frame_stage=choose(ENFORCEMENT_STAGES,'unknown','policy_status')
    elif event_type=='trade_remedy_determination':
        frame_stage=choose(REMEDY_STAGES,'unknown','policy_status')
    else:
        frame_stage=None
    policy=choose((
        ('repealed',r'\b(?:repealed|revoked)\b'),
        ('expired',r'\bexpired\b'),
        ('suspended',r'\bsuspended\b'),
        ('consultation',r'\bconsultation\b'),
        # `-ing` included: "the Commission is PROPOSING to amend the rule" is
        # how a Federal Register abstract almost always phrases it, and the
        # form was missing, so a proposal read as having no stage at all.
        ('proposed',r'\bpropos(?:e|es|ed|al|als|ing)\b'),
        ('effective',r'\b(?:takes? effect|effective from|in force)\b'),
        # `approved` is guarded. "Previously Approved Collections" describes
        # what the collections ARE, not an approval that just happened, and
        # every Paperwork Reduction Act renewal notice carries that phrase —
        # so a routine paperwork notice was being promoted to `adopted`.
        ('adopted',r'\b(?:adopted|enacted)\b'
                   r'|(?<!previously )\bapproved\b(?!\s+collections?\b)'),
        ('announced',r'\bannounced\b'),
    ),'unknown','policy_status')
    if frame_stage is not None and frame_stage!='unknown':
        policy=frame_stage
    # The title states what the document IS; the body often narrates the
    # proposal and hearing that preceded it. "Jeffrey Thies: Final Debarment
    # Order" was read as `proposed` because its abstract describes that
    # procedure. A finality marker in the title therefore outranks a pending
    # stage that was only ever found in the body — and only then, so a notice
    # whose title really does propose something is untouched.
    # Two cases, one rule. A pending stage found only in the BODY is overridden
    # by a title that states finality; and a title that states finality
    # establishes it even when nothing matched at all — "Jeffrey Thies: Final
    # Debarment Order" is a decided order whether or not a body says so, and
    # resolving it to `unknown` lost a fact the title stated plainly.
    if (title and FINALITY.search(title)
            and (policy in PENDING_STAGES or policy == 'unknown')
            and not re.search(r'\bpropos(?:es?|ed|al)\b', title, re.I)):
        policy='adopted'
    # `effective` asserts the measure APPLIES NOW. When the text carries an
    # explicit date that has not arrived yet, it has been decided but is not
    # in force — which is `adopted`. The distinction matters downstream:
    # `adopted` and `effective` are the two statuses that produce a signed
    # direction in the exposure walk.
    #
    # Four outcomes, and only the first may leave `effective` standing:
    # the date arrived; the date is still ahead; the date is coarser than the
    # question (a month that contains this decision time); and a start that
    # was STATED but could not be converted. The last three all abstain,
    # because "we could not read the date" is not evidence that the measure
    # applies today — which is exactly what reading only ISO dates produced.
    not_yet_in_force=None
    start_match=EFFECTIVE.search(searchable)
    start_date=parse_date(start_match.group(1)) if start_match else None
    vague=None if start_match else EFFECTIVE_VAGUE.search(searchable)
    if start_match:
        span(start_match,'effective_at')
    elif vague:
        span(vague,'effective_at')
    end_match=ENDS.search(searchable)
    end_date=parse_date(end_match.group(1)) if end_match else None
    if end_match:
        span(end_match,'ends_at')
    pending_termination=None
    if policy=='effective' and (start_match or vague):
        state=arrival(start_date,available_at) if available_at else UNKNOWN
        stated=(start_date.text if start_date else
                (start_match or vague).group(1).strip())
        if state==FUTURE:
            policy='adopted'
            not_yet_in_force=(
                f'decided but NOT yet in force: effective from {stated}, '
                f'which is after this decision time')
        elif state==UNCERTAIN:
            policy='adopted'
            not_yet_in_force=(
                f'effective date {stated!r} is stated only to '
                f'{start_date.precision} precision, which contains this '
                f'decision time: whether the measure has started is NOT '
                f'established, so it is not reported as in force')
        elif state==UNKNOWN and available_at:
            policy='adopted'
            not_yet_in_force=(
                f'an effective date was stated ({stated!r}) but is not in a '
                f'form this extractor converts: not assumed to have arrived')
    # The mirror case. A revocation or expiry dated in the future has not
    # happened: the measure it ends is still applying, and reporting the
    # document as `repealed`/`expired` today asserts the opposite.
    if policy in ('repealed','expired','suspended') and end_match and available_at:
        state=arrival(end_date,available_at)
        if state in (FUTURE,UNCERTAIN,UNKNOWN):
            stated=end_date.text if end_date else end_match.group(1).strip()
            pending_termination=end_date.starts if end_date else stated
            policy='adopted'
            not_yet_in_force=(
                f'this instrument ENDS a measure with effect from {stated}, '
                f'which has not arrived at this decision time: the measure '
                f'it ends is still applying, and neither the ending nor its '
                f'consequences are in force yet')
    action=choose(ACTION_RULES,'unknown','action')
    quantities=[]
    measure=({'policy_rate_decision':'policy_rate','reserve_requirement_change':'reserve_ratio',
              'tariff_announcement':'tariff_rate','import_duty_change':'import_duty',
              'capacity_expansion':'capacity'}.get(event_type))
    # A sentence without a rate subject cannot donate numbers to another claim.
    if measure and event_type != 'capacity_expansion':
        levels=LEVELS.search(text)
        if levels:
            old,new=Decimal(levels[1]),Decimal(levels[2])
            quantities.append(QuantityV2(measure,'percentage_points',old,new,new-old,
                evidence=(span(levels,'old_new_rate'),)))
            if action=='unknown': action='increase' if new>old else 'decrease' if new<old else 'unchanged'
        else:
            for match in BPS.finditer(text):
                sign=Decimal(-1) if action=='decrease' else Decimal(1) if action=='increase' else None
                quantities.append(QuantityV2(measure,'basis_points',
                    delta=Decimal(match[1])*sign if sign is not None else None,
                    evidence=(span(match,'rate_delta'),)))
            for match in RATE.finditer(text):
                quantities.append(QuantityV2(measure,'percent',new_level=Decimal(match[1]),
                                             evidence=(span(match,'rate_level'),)))
    if event_type == 'capacity_expansion':
        for match in re.finditer(NUM+r'\s*(million tonnes|mtpa|tonnes)\b', text, re.I):
            unit=match[2].lower()
            value=Decimal(match[1]) * (1000000 if unit in ('million tonnes','mtpa') else 1)
            quantities.append(QuantityV2('capacity', 'tonnes_per_year' if unit == 'mtpa' else 'tonnes',
                                        new_level=value, evidence=(span(match,'capacity'),)))
    unknowns=['net economic effect requires target-specific exposure', 'occurrence time not evidenced']
    if not_yet_in_force:unknowns.append(not_yet_in_force)
    if action=='unknown':unknowns.append('action not established')
    if event_type=='trade_remedy_determination':
        # Direction is NOT a property of the measure. A duty on an Indian
        # product is adverse to the exporter, favourable to a competing
        # domestic producer, and adverse to a downstream buyer. Only the
        # exposure registry's target role can resolve that.
        unknowns.append('trade-remedy direction depends on the target role '
                        '(exporter, competing producer, downstream buyer); '
                        'the measure alone does not establish a sign')
        if policy in ('announced','consultation'):
            unknowns.append('preliminary or initiated stage: no duty is '
                            'established by this document')
    scope=scope_of(text, body_retained=body_retained)
    if scope.determined:
        unknowns.extend(n for n in (scope.note,) if n)
    return EventFrameV2(revision,assertion,action,policy,tuple(quantities),
        evidence=tuple(spans),unknowns=tuple(unknowns),representation_hash=digest,
        available_at=available_at,
        effective_at=start_date.starts if start_date else None,
        effective_until=start_date.ends if start_date else None,
        effective_precision=start_date.precision if start_date else None,
        effective_text=(start_date.text if start_date else
                        (start_match or vague).group(1).strip()
                        if (start_match or vague) else None),
        pending_termination=pending_termination,
        excluded_countries=scope.excluded_countries,
        excluded_products=scope.excluded_products,
        excluded_parties=scope.excluded_parties,
        scope_determined=scope.determined,
        scope_carve_out=bool(scope.has_exclusions or scope.exempts_named_parties),
        scope_note=scope.limitation)
