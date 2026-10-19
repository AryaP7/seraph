# C13 — News, events, entities and exposure (PRODUCT-CONTRACTS §5)
"""Flow F2: external sources → events → entities/places/assets → exposure →
impact estimates → overlays.

Kept strictly apart from flow F1 (market data → pillars → CSRS). A
news-derived sector stress and a Hawkes sector intensity are different series
with different units, coverage and uncertainty; nothing in this package reads
or writes the other channel.
"""
from seraph.news.acquisition import (
    FetchedItem,
    FetchResult,
    IngestReport,
    NewsStore,
    SourceNotRegistered,
)
from seraph.news.model import (
    DEFAULT_PERMISSIONS,
    SYNDICATION_KEY_VERSION,
    USES,
    Asset,
    Entity,
    Event,
    EvidenceSpan,
    ExposureEdge,
    ImpactEstimate,
    Place,
    RawObservation,
    Source,
    SourceHealth,
    Story,
    event_identity,
    syndication_key,
    syndication_tokens,
)

__all__ = [
    "DEFAULT_PERMISSIONS",
    "SYNDICATION_KEY_VERSION",
    "USES",
    "Asset",
    "Entity",
    "Event",
    "EvidenceSpan",
    "ExposureEdge",
    "FetchResult",
    "FetchedItem",
    "ImpactEstimate",
    "IngestReport",
    "NewsStore",
    "Place",
    "RawObservation",
    "Source",
    "SourceHealth",
    "SourceNotRegistered",
    "Story",
    "event_identity",
    "syndication_key",
    "syndication_tokens",
]
