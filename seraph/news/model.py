# C13 — News subsystem contracts (PRODUCT-CONTRACTS §5)
"""Sources, observations, stories, events, entities, exposure and estimates.

This is flow **F2** of the three the product keeps separate:

    F2  External sources → timestamped news/events → entities/places/assets
        → exposure relationships → news impact estimates → overlays

It never touches F1 (market data → pillars → CSRS). A news-derived sector
stress and a Hawkes sector intensity are different series, in different units,
with different coverage, and this package never produces one from the other.

Three things here are load-bearing and easy to get wrong:

* **Five times, not one.** `published_at` is not when SERAPH knew something.
  `Story.timing` carries all five and the replay bound is `first_seen_at`.
* **Syndication is not confirmation.** A `Story` belongs to a
  `syndication_group`; an `Event` aggregates a group, so ten copies of one
  agency wire are one piece of evidence with ten witnesses, not ten events.
* **An estimate has separate dimensions.** Severity, evidence confidence,
  exposure magnitude, direction and horizon are five fields, because
  collapsing them into "0.7 stress" destroys the only information a user can
  actually check.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from seraph.news.event_frames import EventFrameV2

from seraph.product_types import Coverage, SourceRef, Timing
from seraph.shared_types import ISOTimestamp

# --------------------------------------------------------------- sources

SourceKind = Literal["official_policy", "exchange_notice", "regulator",
                     "news_agency", "company_filing", "weather_advisory",
                     "commodity_price"]

FailureBehaviour = Literal["report_missing", "retry_then_report"]

#: The uses this product actually makes of a source's text, each of which a
#: licence may permit separately. One boolean (`may_store_full_text`) was
#: covering all five, so a source whose terms allow transient processing but
#: not storage, or storage but not display, could only be modelled as "all"
#: or "none" — and "none" throws away analysis the terms permit.
#:
#:  fetch       request the document at all
#:  process     read it in memory to extract facts, without keeping it
#:  store       persist the text
#:  display     show the text (or a quotation of it) to a reader
#:  redistribute pass the text on to a third party or export it
USES = ("fetch", "process", "store", "display", "redistribute")

#: What a source permits when nothing has been reviewed. Fetching and
#: transient processing of a public page are the two the pilot relies on and
#: the two a publisher's terms least often forbid; everything that keeps or
#: republishes the text stays off until somebody reads the licence.
DEFAULT_PERMISSIONS = ("fetch", "process")


@dataclass(frozen=True)
class Source:
    """A registered feed. Nothing unregistered may enter scoring."""

    source_id: str
    provider: str
    kind: SourceKind
    url: str
    topic_coverage: tuple[str, ...]
    language: str = "en"
    #: What the licence actually permits. A source whose terms forbid storing
    #: full text is held as a link plus a hash, never as a stored article.
    rights: str = "unverified"
    may_store_full_text: bool = False
    retention_days: int | None = None
    poll_interval_minutes: int = 60
    failure_behaviour: FailureBehaviour = "retry_then_report"
    max_retries: int = 3
    notes: str | None = None
    #: False until someone has actually fetched it and read the terms.
    accessibility_verified: bool = False
    #: Per-use permissions. `None` means "not reviewed at that granularity",
    #: and the coarse `may_store_full_text` flag is used instead, so an
    #: existing registration keeps exactly the behaviour it had.
    permissions: tuple[str, ...] | None = None
    #: Who read the terms, when, and against which version of them. A
    #: permission with no review behind it is a guess with a boolean's
    #: confidence.
    rights_reviewed_by: str | None = None
    rights_reviewed_at: str | None = None
    rights_version: str | None = None

    def __post_init__(self) -> None:
        if self.permissions is not None:
            unknown = set(self.permissions) - set(USES)
            if unknown:
                raise ValueError(
                    f"{self.source_id}: unknown permitted use(s) "
                    f"{sorted(unknown)}; the uses this product makes are "
                    f"{list(USES)}")
            if "store" in self.permissions and "fetch" not in self.permissions:
                raise ValueError(
                    f"{self.source_id}: storing text that may not be fetched "
                    f"is not a coherent permission set")
        if self.retention_days is not None and self.retention_days <= 0:
            raise ValueError(
                f"{self.source_id}: a retention policy of "
                f"{self.retention_days} days cannot be enforced; use None "
                f"for 'no limit' rather than a zero that reads like one")

    def permits(self, use: str) -> bool:
        """Does the licence permit this use, as reviewed?

        Falls back to the coarse flag for a source nobody has reviewed at
        this granularity, so the answer is never more permissive than the
        registration it came from.
        """
        if use not in USES:
            raise ValueError(f"unknown use {use!r}; expected one of {list(USES)}")
        if self.permissions is not None:
            return use in self.permissions
        if use in ("fetch", "process"):
            return True
        if use in ("store", "display"):
            return bool(self.may_store_full_text)
        return False            # redistribution is never implied

    @property
    def rights_reviewed(self) -> bool:
        return bool(self.permissions is not None and self.rights_reviewed_by
                    and self.rights_reviewed_at)

    def describe(self) -> dict:
        return dict(source_id=self.source_id, provider=self.provider, kind=self.kind,
                    url=self.url, topic_coverage=list(self.topic_coverage),
                    language=self.language, rights=self.rights,
                    may_store_full_text=self.may_store_full_text,
                    retention_days=self.retention_days,
                    poll_interval_minutes=self.poll_interval_minutes,
                    failure_behaviour=self.failure_behaviour,
                    max_retries=self.max_retries,
                    accessibility_verified=self.accessibility_verified,
                    permissions=(None if self.permissions is None
                                 else sorted(self.permissions)),
                    permitted_uses={use: self.permits(use) for use in USES},
                    rights_reviewed=self.rights_reviewed,
                    rights_reviewed_by=self.rights_reviewed_by,
                    rights_reviewed_at=self.rights_reviewed_at,
                    rights_version=self.rights_version,
                    notes=self.notes)


@dataclass(frozen=True)
class SourceHealth:
    source_id: str
    last_attempt_at: ISOTimestamp | None = None
    last_success_at: ISOTimestamp | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    cursor: str | None = None

    @property
    def status(self) -> str:
        if self.last_success_at is None:
            return "never_succeeded"
        return "degraded" if self.consecutive_failures else "healthy"


# ---------------------------------------------------------- observations

@dataclass(frozen=True)
class RawObservation:
    """One fetch of one item, exactly as received.

    `content_hash` is over the raw bytes. Re-fetching the same item produces
    the same hash and therefore the same observation id, which is how a
    restart or a double poll collapses to one logical observation.
    """

    observation_id: str
    source_id: str
    reference: str                   # the item's URL or stable id at the source
    content_hash: str
    fetched_at: ISOTimestamp
    http_status: int | None = None
    parse_status: Literal["ok", "partial", "failed"] = "ok"
    cursor: str | None = None
    raw: bytes | None = None         # omitted when the licence forbids storage

    @staticmethod
    def identity(source_id: str, reference: str, content_hash: str) -> str:
        return "obs_" + hashlib.sha256(
            f"{source_id}|{reference}|{content_hash}".encode()).hexdigest()[:24]


# --------------------------------------------------------------- stories

@dataclass(frozen=True)
class Story:
    """A published item, deduplicated and grouped with its syndications."""

    story_id: str
    source_id: str
    observation_id: str
    title: str
    url: str
    timing: Timing
    body: str | None = None
    syndication_group: str | None = None
    corrects: str | None = None          # story_id this corrects
    retracts: str | None = None          # story_id this retracts
    language: str = "en"
    metadata: dict = field(default_factory=dict)

    @property
    def first_seen_at(self) -> ISOTimestamp | None:
        return self.timing.first_seen_at

    def source_ref(self, content_hash: str | None = None) -> SourceRef:
        return SourceRef(source_id=self.source_id, reference=self.url,
                         content_hash=content_hash,
                         retrieved_at=self.timing.first_seen_at)


#: Bumped whenever `syndication_key` changes what it groups, so a store can
#: say which rule produced the groups it holds and a rebuild is auditable
#: rather than silent. `syn/2` made the tokeniser Unicode-aware and stopped
#: empty token sets collapsing into one group.
SYNDICATION_KEY_VERSION = "syn/2"

#: English function words. They only ever match ASCII tokens, so a
#: Devanagari or other non-Latin headline is unaffected by them.
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "as", "at",
    "by", "with", "from", "after", "says", "said", "is", "are", "be"})

#: Below this many distinct content tokens a headline does not carry enough
#: evidence to be grouped WITH ANOTHER DOCUMENT, so it gets a key of its
#: own. One shared token is a coincidence; zero is what made every Hindi
#: headline on a given day one story.
MIN_GROUPING_TOKENS = 2


#: Unicode general categories that belong inside a word. Letters, numbers
#: and — the part `\w` gets wrong — the combining marks that carry the
#: vowels in an Indic script. `\w` matches by `isalpha()`, which excludes
#: categories Mn and Mc, so it chops "सरकार" after three characters at the
#: vowel sign. `[a-z0-9]`, the rule this replaces, matched none of it at
#: all: every Hindi headline normalised to an EMPTY token set, hashed with
#: the day, and the whole day's Hindi items became one syndication group.
#: The stored corpus has groups of 28 and 9 unrelated stories from this.
_WORD_CATEGORIES = frozenset({'Lu', 'Ll', 'Lt', 'Lm', 'Lo',
                              'Nd', 'Nl', 'No', 'Mn', 'Mc'})

#: Zero-width joiners sit inside conjuncts and are not boundaries.
_WORD_JOINERS = frozenset('‌‍ʼ’\'')


def syndication_tokens(title: str) -> tuple[str, ...]:
    """The content tokens a headline contributes to its group identity.

    Script-agnostic by construction: a token is a run of word characters by
    Unicode category, so Devanagari, Latin and digits are all tokenised by
    the same rule rather than by one that happens to fit English.
    """
    words, current = [], []
    for char in (title or "").casefold():
        if (unicodedata.category(char) in _WORD_CATEGORIES
                or (current and char in _WORD_JOINERS)):
            current.append(char)
        elif current:
            words.append(''.join(current))
            current = []
    if current:
        words.append(''.join(current))
    return tuple(w for w in words
                 if w not in _STOPWORDS and (len(w) > 2 or w.isdigit()))


def syndication_key(title: str, *, published_at: str | None = None,
                    source_id: str | None = None,
                    reference: str | None = None) -> str:
    """Group near-identical headlines from different outlets.

    Deliberately crude and deliberately explainable: normalise the headline,
    keep the content words, hash them with the publication date. A smarter
    clusterer is a later improvement; an unexplainable one is not an
    improvement at all, because an analyst has to be able to see why two
    stories were treated as one.

    What it will NOT do is group two documents on no evidence. A headline
    whose tokens do not survive normalisation is given a key derived from
    the publisher and the document reference instead, so it stands alone.
    Standing alone is the correct failure: an unmergeable document costs a
    duplicate, while a wrong merge silently destroys both stories.
    """
    keep = syndication_tokens(title)
    day = (published_at or "")[:10]
    if len(set(keep)) < MIN_GROUPING_TOKENS:
        evidence = f"{source_id or ''}|{reference or title or ''}"
        return "syn_doc_" + hashlib.sha256(
            (evidence + "|" + day).encode()).hexdigest()[:16]
    return "syn_" + hashlib.sha256(
        ("|".join(sorted(set(keep))) + "|" + day).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- events

EventType = Literal[
    # Trade and industrial
    "tariff_announcement", "export_restriction", "import_duty_change",
    "production_halt", "capacity_expansion", "facility_incident",
    "logistics_disruption", "subsidy_change",
    # A trade-remedy proceeding is a legal instrument with a stage, not a
    # tariff announcement. On the pilot corpus these were the single largest
    # group of events falling through to "other", and they are the class that
    # names an Indian product and a foreign measure in the same sentence.
    "trade_remedy_determination",
    # Monetary, banking and regulatory. Added once real RBI feeds were
    # connected: the first live source is a central bank, and classifying a
    # reserve-requirement change as "other" alongside a weekly statistical
    # bulletin makes the whole channel useless.
    "policy_rate_decision", "reserve_requirement_change",
    "prudential_norms_change", "forex_regulation", "bank_resolution",
    "liquidity_operation", "debt_instrument_event", "statistical_release",
    "official_speech", "regulatory_action",
    # An appeal against a regulator's order is a stage in someone else's
    # dispute, not a policy change. Naming it stops dozens of filings
    # diluting `other`, which must keep meaning "we do not know what this is".
    "regulatory_appeal",
    # Enforcement and recovery against a named party: attachment, demand,
    # prohibitory order, release, completion. A legal PROCESS with stages,
    # not a policy change, and adverse to the named party rather than to
    # whatever issuer happens to be mentioned in the same sentence.
    "securities_enforcement_action",
    # An administered price or margin, which is a policy instrument rather
    # than a market move: "137 कैंसर रोधी दवाओं पर व्यापार मार्जिन का युक्तिकरण".
    "price_control",
    # A change in who owns an issuer — divestment, stake sale, merger.
    "ownership_change",
    "physical_hazard", "other",
]

Lifecycle = Literal["active", "developing", "resolved", "superseded", "retracted"]

Direction = Literal["adverse", "favourable", "ambiguous"]


@dataclass(frozen=True)
class EvidenceSpan:
    """Where in the text a claim came from. An extraction without one is not
    reviewable, so the extractor must produce it."""

    story_id: str
    start: int
    end: int
    text: str
    field: str


@dataclass(frozen=True)
class Event:
    """A thing that happened, assembled from one or more stories."""

    event_id: str
    event_type: EventType
    headline: str
    timing: Timing
    stories: tuple[str, ...]              # story_ids, including syndications
    actors: tuple[str, ...] = ()          # who did it (resolved entity ids or raw)
    affected: tuple[str, ...] = ()        # entity/place/asset ids
    quantities: tuple[tuple[str, float, str], ...] = ()   # (name, value, unit)
    evidence: tuple[EvidenceSpan, ...] = ()
    lifecycle: Lifecycle = "active"
    supersedes: str | None = None
    #: Identifiers this document CITES — a case number, an investigation
    #: number, a notification number. The only evidence on which one
    #: instrument may be linked to another; a shared headline is not one.
    instrument_ids: tuple[str, ...] = ()
    #: Places and facilities NAMED in the text, each with the role the
    #: extractor could establish — which, from a name match alone, is only
    #: "mentioned". The venue of a speech, the dateline of a release and the
    #: registered address of an issuer all look identical to a matcher, and
    #: calling any of them "affected" would put an impact on the map that no
    #: evidence supports. A role is promoted out of "mentioned" only by an
    #: evidenced rule, never by the fact that a word appeared.
    locations: tuple[tuple[str, str], ...] = ()   # (place/asset id, role)
    unresolved: tuple[str, ...] = ()      # facts the extractor would not guess
    extractor_version: str | None = None
    frame: EventFrameV2 | None = None
    reporting_origins: tuple[str, ...] = ()
    exposure_origins: tuple[str, ...] = ()

    @property
    def confirmations(self) -> int:
        """Distinct SOURCES, not distinct stories. Ten syndicated copies of
        one agency wire are one confirmation."""
        return len(set(self.reporting_origins)) if self.reporting_origins else (1 if self.stories else 0)

    def visible_at(self, decision_ts: ISOTimestamp) -> bool:
        return self.timing.visible_at(decision_ts)


# ------------------------------------------------- entities and places

EntityKind = Literal["issuer", "operator", "subsidiary", "government_body",
                     "industry_body"]

AssetKind = Literal["plant", "mine", "port", "refinery", "terminal",
                    "power_station", "warehouse"]


@dataclass(frozen=True)
class Entity:
    entity_id: str
    name: str
    kind: EntityKind
    symbol: str | None = None           # NSE trading symbol where listed
    isin: str | None = None
    sector: str | None = None
    parent_id: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    aliases: tuple[str, ...] = ()
    source: str | None = None           # where this record came from
    known_from: str | None = None

    def active_on(self, day: str) -> bool:
        return ((self.valid_from is None or self.valid_from <= day)
                and (self.valid_to is None or day < self.valid_to))


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    #: `point` is a coordinate a SOURCE reported — a hazard epicentre, a
    #: survey position — with no administrative meaning, no boundary and its
    #: own measurement uncertainty. Calling one a city overstates what is
    #: known about where it is.
    kind: Literal["country", "state", "district", "city", "point"]
    parent_id: str | None = None
    iso_code: str | None = None
    lat: float | None = None
    lon: float | None = None
    #: Alternative spellings a source may use. Official documents write
    #: countries in their long legal form ("People's Republic of China"),
    #: which never matches a short curated name however good the registry is.
    aliases: tuple[str, ...] = ()
    known_from: str | None = None


@dataclass(frozen=True)
class Asset:
    """A physical facility. Its location is the facility's, never the
    operator's registered-office address — conflating them is how a Mumbai
    headquarters becomes the site of a disrupted plant in Odisha."""

    asset_id: str
    name: str
    kind: AssetKind
    place_id: str
    operator_entity_id: str | None = None
    owner_entity_id: str | None = None
    capacity: float | None = None
    capacity_unit: str | None = None
    status: Literal["operational", "under_construction", "planned",
                    "maintenance", "unknown"] = "unknown"
    lat: float | None = None
    lon: float | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    source: str | None = None
    known_from: str | None = None


# -------------------------------------------------------------- exposure

Mechanism = Literal["revenue", "import", "export", "input_dependency",
                    "logistics", "supplier", "ownership", "operation"]


@dataclass(frozen=True)
class ExposureEdge:
    """A documented relationship. Every map arc must have one of these.

    `magnitude` without `unit` is meaningless, and `confidence` without
    `evidence` is an opinion, so both pairs are required together.
    """

    edge_id: str
    from_id: str
    to_id: str
    mechanism: Mechanism
    magnitude: float | None = None
    unit: str | None = None
    confidence: Literal["low", "medium", "high"] = "low"
    evidence: tuple[SourceRef, ...] = ()
    valid_from: str | None = None
    valid_to: str | None = None
    note: str | None = None
    known_from: str | None = None
    known_to: str | None = None
    registry_version: str | None = None
    event_types: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    target_role: str | None = None

    def visible_at(self, timestamp: str) -> bool:
        return bool(self.known_from and self.known_from <= timestamp
                    and (self.known_to is None or timestamp < self.known_to))

    def __post_init__(self) -> None:
        if (self.magnitude is None) != (self.unit is None):
            raise ValueError(
                f"{self.edge_id}: magnitude and unit travel together — a bare "
                "number is not a quantity")
        if not self.evidence:
            raise ValueError(
                f"{self.edge_id}: an exposure relationship needs inspectable "
                "evidence; an unevidenced edge is an assertion, not data")

    def active_on(self, day: str) -> bool:
        return ((self.valid_from is None or self.valid_from <= day)
                and (self.valid_to is None or day < self.valid_to))


# ------------------------------------------------------------- estimates

@dataclass(frozen=True)
class ImpactEstimate:
    """Five separate dimensions, never one collapsed number.

    `severity` is about the EVENT. `exposure_magnitude` is about the target's
    dependence on it. `evidence_confidence` is how sure we are the event is
    real and correctly linked. They multiply into nothing automatically — a
    caller that wants a single score must define and defend that combination
    itself, and say so.

    None of these is a probability of financial loss. Producing one requires a
    declared, calibrated target and an evaluation, which this subsystem does
    not have.
    """

    estimate_id: str
    event_id: str
    target_id: str                     # entity, sector or place
    target_kind: Literal["entity", "sector", "place", "asset"]
    severity: Literal["minor", "moderate", "major", "severe"]
    evidence_confidence: Literal["low", "medium", "high"]
    exposure_magnitude: float | None    # share of the target's activity
    exposure_unit: str | None
    direction: Direction
    horizon_days: int | None
    mechanism: Mechanism
    method_id: str
    method_version: str
    path: tuple[str, ...] = ()          # the edge_ids this travelled
    coverage: Coverage | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (self.exposure_magnitude is None) != (self.exposure_unit is None):
            raise ValueError(
                f"{self.estimate_id}: exposure magnitude and unit travel together")

    def describe(self) -> dict:
        return dict(
            estimate_id=self.estimate_id, event_id=self.event_id,
            target_id=self.target_id, target_kind=self.target_kind,
            severity=self.severity, evidence_confidence=self.evidence_confidence,
            exposure_magnitude=self.exposure_magnitude,
            exposure_unit=self.exposure_unit, direction=self.direction,
            horizon_days=self.horizon_days, mechanism=self.mechanism,
            method=f"{self.method_id}@{self.method_version}",
            path=list(self.path),
            limitations=list(self.limitations),
            not_a_loss_probability=(
                "severity and exposure are descriptive dimensions. This is not "
                "a probability of financial loss and has no calibrated target"),
        )


def event_identity(event_type: str, syndication: str, occurred_on: str) -> str:
    return "evt_" + hashlib.sha256(
        f"{event_type}|{syndication}|{occurred_on}".encode()).hexdigest()[:20]


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)
