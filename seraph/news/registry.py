# C13 — Entity, place and asset master data (NEWS03)
"""Resolve a name in an article to a stable identifier, or abstain.

The failure this module exists to prevent: a headline says "Tata Steel halts
output at Kalinganagar", and a naive resolver links it to Tata Steel's Mumbai
registered office, putting a production halt on the wrong map pixel and the
wrong district's exposure. An operator's headquarters is not the location of
its plant, so `Asset` carries its own `place_id` and the resolver never
borrows one from the operator.

Abstention is a result, not a failure
-------------------------------------
`resolve()` returns a `Resolution` that is `resolved`, `ambiguous` or
`unknown`. An ambiguous mention names its candidates and resolves to nothing;
downstream treats it as unresolved and says so, rather than taking the first
candidate. That is the only behaviour that keeps a review set meaningful.

Curated registries ship EMPTY
-----------------------------
Following the convention `seraph/ingestion/tariff_events.py` already sets in
this repo: an entity, asset or exposure row without a citation is
indistinguishable from an invented one, so the loader refuses it and the
shipped files contain headers and curation instructions only. The machinery is
complete; the data is a human task.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from seraph.news.model import Asset, Entity, ExposureEdge, Place
from seraph.product_types import SourceRef

CURATED_DIR = Path(__file__).resolve().parent / "curated"

#: A citation must look like one. A blank or placeholder reference is rejected.
CITATION = re.compile(r"^(https?://|doc:|ref:|filing:)\S+")


#: A single token is never enough for a partial match. The real corpus
#: resolved the mention "India" to the entity `reserve_bank_of_india`, because
#: plain substring containment accepts any common word inside a longer name.
MIN_PARTIAL_TOKENS = 2


def _token_subsequence(needle: str, candidate: str) -> bool:
    """Is one name a contiguous run of whole words inside the other?

    Substring containment is too weak for names: "india" sits inside "reserve
    bank of india" and "air" inside "airtel". Matching on whole tokens, and
    requiring at least `MIN_PARTIAL_TOKENS` of them, keeps "Reserve Bank" ->
    "Reserve Bank of India" while rejecting "India" -> the same entity.
    """
    a, b = needle.split(), candidate.split()
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < MIN_PARTIAL_TOKENS:
        return False
    for start in range(len(long_) - len(short) + 1):
        if long_[start:start + len(short)] == short:
            return True
    return False


class CurationError(ValueError):
    """A curated row is missing something that cannot be guessed."""


@dataclass(frozen=True)
class Resolution:
    """What a mention resolved to — including when it resolved to nothing."""

    mention: str
    status: Literal["resolved", "ambiguous", "unknown"]
    entity_id: str | None = None
    candidates: tuple[str, ...] = ()
    matched_on: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "resolved"

    def describe(self) -> dict:
        return dict(mention=self.mention, status=self.status,
                    entity_id=self.entity_id, candidates=list(self.candidates),
                    matched_on=self.matched_on)


def _norm(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    cleaned = re.sub(r"\b(ltd|limited|pvt|private|inc|plc|corp|corporation|co)\b",
                     " ", cleaned)
    return " ".join(cleaned.split())


class MasterData:
    """Entities, places and assets, with validity dates and resolution."""

    def __init__(self, *, entities=(), places=(), assets=(), edges=(),
                 source_places=()):
        self.entities: dict[str, Entity] = {e.entity_id: e for e in entities}
        self.places: dict[str, Place] = {p.place_id: p for p in places}
        self.assets: dict[str, Asset] = {a.asset_id: a for a in assets}
        self.edges: dict[str, ExposureEdge] = {e.edge_id: e for e in edges}
        #: source_id -> {place_id, basis, source}. Where a SOURCE issues from.
        #: An event's origin is a property of who published it, not something
        #: an extractor should infer from the prose of each story.
        self.source_places: dict[str, dict] = {
            sp["source_id"]: sp for sp in source_places}
        #: Set by `as_of`. A registry that was never sliced has made no
        #: temporal assumption, which is different from having made none.
        self.as_of_timestamp = None
        self.temporal_assumptions = dict(
            assumed_always_known={}, total=0,
            policy='this registry has not been sliced to a decision time')

    def as_of(self, timestamp, *, strict=False):
        """The registry as it could have been known at `timestamp`.

        Historical evaluation uses strict=True and EXCLUDES unknown dates.
        Current monitoring may admit undated reference data with an explicit
        count. No acquisition date is invented to backdate the registry.
        """
        assumed = {}

        def eligible(records, kind):
            kept, undated = [], 0
            for record in records:
                known = getattr(record, 'known_from', None)
                if not known:
                    undated += 1
                    if not strict:
                        kept.append(record)
                elif known <= timestamp:
                    kept.append(record)
            if undated:
                assumed[kind] = undated
            return kept

        places = eligible(self.places.values(), 'places')
        known_places = {p.place_id for p in places}
        # Source-to-place mappings were exempt from this filter, which leaked
        # hindsight twice over: a mapping curated later appeared in an earlier
        # replay, and a mapping pointing at a place this `as_of` had already
        # filtered out survived as a dangling reference. A dangling mapping
        # does not raise -- the marker simply loses its coordinates, and an
        # absent marker is indistinguishable from an absent source.
        source_places = []
        undated_mappings = 0
        for sp in self.source_places.values():
            if sp['place_id'] not in known_places:
                continue
            if not sp.get('known_from'):
                undated_mappings += 1
                if not strict:
                    source_places.append(sp)
            elif sp['known_from'] <= timestamp:
                source_places.append(sp)
        if undated_mappings:
            assumed['source_places'] = undated_mappings

        snapshot = MasterData(
            entities=eligible(self.entities.values(), 'entities'),
            places=places,
            assets=eligible(self.assets.values(), 'assets'),
            edges=[e for e in self.edges.values() if e.visible_at(timestamp)],
            source_places=source_places)
        snapshot.as_of_timestamp = timestamp
        snapshot.temporal_assumptions = dict(
            assumed_always_known={} if strict else assumed,
            excluded_unknown_dates=assumed if strict else {},
            total=0 if strict else sum(assumed.values()), strict=strict,
            policy=('unknown historical availability is excluded' if strict else
                    'current monitoring admits undated reference data; not valid historical evidence'))
        return snapshot

    # ------------------------------------------------------------ build

    def add_entity(self, entity: Entity) -> Entity:
        self.entities[entity.entity_id] = entity
        return entity

    def add_place(self, place: Place) -> Place:
        self.places[place.place_id] = place
        return place

    def add_asset(self, asset: Asset) -> Asset:
        if asset.place_id not in self.places:
            raise CurationError(
                f"{asset.asset_id}: place {asset.place_id!r} is not registered. An "
                f"asset's location is its own, never borrowed from its operator")
        self.assets[asset.asset_id] = asset
        return asset

    def add_edge(self, edge: ExposureEdge) -> ExposureEdge:
        known = set(self.entities) | set(self.assets) | set(self.places)
        for end in (edge.from_id, edge.to_id):
            if end not in known and not end.startswith("sector:"):
                raise CurationError(
                    f"{edge.edge_id}: endpoint {end!r} is not a registered entity, "
                    f"asset, place or sector")
        self.edges[edge.edge_id] = edge
        return edge

    # --------------------------------------------------------- resolve

    def resolve(self, mention: str, *, on: str | None = None) -> Resolution:
        """Resolve a mention to one entity, or abstain with the candidates."""
        needle = _norm(mention)
        if not needle:
            return Resolution(mention=mention, status="unknown")
        exact, partial = [], []
        for entity in self.entities.values():
            if on and not entity.active_on(on):
                continue
            names = [entity.name, *entity.aliases]
            normed = [_norm(n) for n in names]
            if needle in normed:
                exact.append(entity.entity_id)
            elif any(_token_subsequence(needle, n) for n in normed if n):
                partial.append(entity.entity_id)
        if len(exact) == 1:
            return Resolution(mention=mention, status="resolved",
                              entity_id=exact[0], matched_on="exact")
        if len(exact) > 1:
            return Resolution(mention=mention, status="ambiguous",
                              candidates=tuple(sorted(exact)), matched_on="exact")
        if len(partial) == 1:
            return Resolution(mention=mention, status="resolved",
                              entity_id=partial[0], matched_on="partial")
        if len(partial) > 1:
            return Resolution(mention=mention, status="ambiguous",
                              candidates=tuple(sorted(partial)), matched_on="partial")
        return Resolution(mention=mention, status="unknown")

    def add_source_place(self, *, source_id: str, place_id: str, basis: str,
                         source: str, known_from: "str | None" = None) -> dict:
        if place_id not in self.places:
            raise CurationError(
                f"source {source_id}: place {place_id!r} is not registered. A "
                f"source's issuing location must be a curated place")
        if basis not in ("issuing_office", "jurisdiction"):
            raise CurationError(
                f"source {source_id}: basis {basis!r} must be "
                f"'issuing_office' or 'jurisdiction'. A specific address and "
                f"a territory are different claims and are drawn differently")
        record = dict(source_id=source_id, place_id=place_id, basis=basis,
                      source=source, known_from=known_from)
        self.source_places[source_id] = record
        return record

    def registry_completeness(self) -> dict:
        """Which curated rows cannot survive a strict replay, and why.

        `as_of(strict=True)` correctly excludes a record with no curation
        date — an undated row cannot be shown to have been knowable at the
        moment being reconstructed — and it does so silently, so the cost
        was invisible: five places, one entity and every one of the ten
        source-location mappings drop out, taking their routes with them.

        Naming the rows turns that into curation work somebody can finish.
        It does not invent a date for any of them: a `known_from` must be
        when THIS SYSTEM curated the record, and nothing here knows that.
        """
        def missing(records, key):
            return sorted(getattr(r, key) for r in records
                          if not getattr(r, 'known_from', None))

        # A hazard node is derived at render time from the event's own
        # reported coordinates. It is not a curated row and has no curation
        # date to be missing — counting it here would turn an ordinary
        # hazard feed into a growing registry debt.
        curated_places = [p for p in self.places.values()
                          if not p.place_id.startswith('hazard_')]
        rows = dict(
            places=missing(curated_places, 'place_id'),
            entities=missing(self.entities.values(), 'entity_id'),
            assets=missing(self.assets.values(), 'asset_id'),
            edges=sorted(e.edge_id for e in self.edges.values()
                         if not e.known_from),
            source_places=sorted(k for k, v in self.source_places.items()
                                 if not v.get('known_from')))
        total = sum(len(v) for v in rows.values())
        return dict(
            undated=rows, undated_total=total,
            counts=self.describe(),
            strict_replay_cost=(
                'a strict replay excludes every row listed here, so the '
                'routes that depend on them disappear from any historical '
                'reconstruction. That is the correct behaviour and a real '
                'coverage gap, not a defect to be fixed by backdating'),
            note=('`known_from` is the date this system curated the record. '
                  'It is never the date the underlying fact became true and '
                  'never the year of the document cited; inferring one from '
                  'the other is how hindsight gets into a replay'))

    def version_manifest(self) -> dict:
        """Source, mapping, exposure and interpretation versions together.

        A reconstruction is only reproducible if every input version is
        pinned. Checking one of them and trusting the rest is how a replay
        comes to differ from the run it claims to reproduce.
        """
        from seraph.news.extraction import EXTRACTOR_VERSION
        edge_versions = sorted({e.registry_version for e in self.edges.values()
                                if getattr(e, 'registry_version', None)})
        return dict(
            as_of=self.as_of_timestamp,
            interpretation=EXTRACTOR_VERSION,
            exposure_registry_versions=edge_versions,
            counts=self.describe(),
            temporal_assumptions=self.temporal_assumptions,
            note=('every version that shapes a reconstruction, in one place. '
                  'A replay that pins only some of these can differ from the '
                  'run it claims to reproduce'))

    def origin_of(self, source_id: str) -> dict | None:
        """Where this source issues from, or nothing. Never a guess."""
        return self.source_places.get(source_id)

    def resolve_place(self, mention: str) -> Resolution:
        """Resolve a place mention. Abstains on ambiguity, like entities."""
        needle = _norm(mention)
        if not needle:
            return Resolution(mention=mention, status="unknown")
        # Exact match on the name OR a curated alias. Deliberately not fuzzy:
        # "Korea" must not quietly become "Republic of Korea", and two places
        # claiming the same alias still abstain below.
        exact = [p.place_id for p in self.places.values()
                 if needle in {_norm(p.name)} | {_norm(a) for a in p.aliases}]
        if len(exact) == 1:
            return Resolution(mention=mention, status="resolved",
                              entity_id=exact[0], matched_on="place")
        if len(exact) > 1:
            return Resolution(mention=mention, status="ambiguous",
                              candidates=tuple(sorted(exact)),
                              matched_on="place")
        return Resolution(mention=mention, status="unknown")

    def resolve_asset(self, mention: str) -> Resolution:
        needle = _norm(mention)
        hits = [a.asset_id for a in self.assets.values()
                if needle and (needle in _norm(a.name) or _norm(a.name) in needle)]
        if len(hits) == 1:
            return Resolution(mention=mention, status="resolved", entity_id=hits[0],
                              matched_on="asset")
        if len(hits) > 1:
            return Resolution(mention=mention, status="ambiguous",
                              candidates=tuple(sorted(hits)), matched_on="asset")
        return Resolution(mention=mention, status="unknown")

    def place_of(self, node_id: str) -> str | None:
        """Where a node actually is.

        An asset's own place. An entity has NO place of its own here: a
        registered office is not an operating location, and returning one
        would put incidents on the wrong map.
        """
        asset = self.assets.get(node_id)
        if asset:
            return asset.place_id
        return node_id if node_id in self.places else None

    def symbols_for(self, entity_id: str) -> tuple[str, ...]:
        """The listed symbol for an entity, following parent links upward."""
        seen, out, current = set(), [], self.entities.get(entity_id)
        while current and current.entity_id not in seen:
            seen.add(current.entity_id)
            if current.symbol:
                out.append(current.symbol)
            current = self.entities.get(current.parent_id) if current.parent_id else None
        return tuple(out)

    def describe(self) -> dict:
        return dict(entities=len(self.entities), places=len(self.places),
                    assets=len(self.assets), edges=len(self.edges),
                    source_places=len(self.source_places))


# ------------------------------------------------------------- loaders

def _rows(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [r for r in csv.DictReader(
            line for line in handle if not line.lstrip().startswith("#"))
            if any((v or "").strip() for v in r.values())]


def _cite(row: dict, path: Path, line: int) -> str:
    reference = (row.get("source_ref") or "").strip()
    if not CITATION.match(reference):
        raise CurationError(
            f"{path.name} row {line}: source_ref {reference!r} is not a citation. "
            f"An uncited row is indistinguishable from an invented one")
    return reference


def load_master_data(directory: Path | None = None) -> tuple[MasterData, dict]:
    """Load the curated registries, or return an explicitly empty one.

    The report says `empty: True` with a reason rather than pretending an
    empty graph is a complete one.
    """
    directory = Path(directory or CURATED_DIR)
    data = MasterData()
    report = {"directory": str(directory), "errors": []}

    for line, row in enumerate(_rows(directory / "places.csv"), start=1):
        data.add_place(Place(
            place_id=row["place_id"].strip(), name=row["name"].strip(),
            kind=row["kind"].strip(), parent_id=(row.get("parent_id") or "").strip() or None,
            iso_code=(row.get("iso_code") or "").strip() or None,
            lat=float(row["lat"]) if (row.get("lat") or "").strip() else None,
            lon=float(row["lon"]) if (row.get("lon") or "").strip() else None,
            aliases=tuple(a.strip() for a in (row.get("aliases") or "").split("|")
                          if a.strip()),
            known_from=row.get("known_from") or None))

    for line, row in enumerate(_rows(directory / "entities.csv"), start=1):
        reference = _cite(row, directory / "entities.csv", line)
        data.add_entity(Entity(
            entity_id=row["entity_id"].strip(), name=row["name"].strip(),
            kind=row["kind"].strip(),
            symbol=(row.get("symbol") or "").strip() or None,
            isin=(row.get("isin") or "").strip() or None,
            sector=(row.get("sector") or "").strip() or None,
            parent_id=(row.get("parent_id") or "").strip() or None,
            valid_from=(row.get("valid_from") or "").strip() or None,
            valid_to=(row.get("valid_to") or "").strip() or None,
            aliases=tuple(a.strip() for a in (row.get("aliases") or "").split("|")
                          if a.strip()),
            source=reference, known_from=(row.get("known_from") or None)))

    for line, row in enumerate(_rows(directory / "assets.csv"), start=1):
        reference = _cite(row, directory / "assets.csv", line)
        data.add_asset(Asset(
            asset_id=row["asset_id"].strip(), name=row["name"].strip(),
            kind=row["kind"].strip(), place_id=row["place_id"].strip(),
            operator_entity_id=(row.get("operator_entity_id") or "").strip() or None,
            owner_entity_id=(row.get("owner_entity_id") or "").strip() or None,
            capacity=float(row["capacity"]) if (row.get("capacity") or "").strip() else None,
            capacity_unit=(row.get("capacity_unit") or "").strip() or None,
            status=(row.get("status") or "unknown").strip(),
            lat=float(row["lat"]) if (row.get("lat") or "").strip() else None,
            lon=float(row["lon"]) if (row.get("lon") or "").strip() else None,
            source=reference, known_from=(row.get("known_from") or None)))

    for line, row in enumerate(_rows(directory / "exposure.csv"), start=1):
        reference = _cite(row, directory / "exposure.csv", line)
        magnitude = (row.get("magnitude") or "").strip()
        unit = (row.get("unit") or "").strip()
        data.add_edge(ExposureEdge(
            edge_id=row["edge_id"].strip(), from_id=row["from_id"].strip(),
            to_id=row["to_id"].strip(), mechanism=row["mechanism"].strip(),
            magnitude=float(magnitude) if magnitude else None,
            unit=unit or None,
            confidence=(row.get("confidence") or "low").strip(),
            evidence=(SourceRef(source_id="curated", reference=reference),),
            valid_from=(row.get("valid_from") or "").strip() or None,
            valid_to=(row.get("valid_to") or "").strip() or None,
            note=(row.get("note") or "").strip() or None,
            known_from=(row.get('known_from') or '').strip() or None,
            known_to=(row.get('known_to') or '').strip() or None,
            registry_version=(row.get('registry_version') or '').strip() or None,
            event_types=tuple(filter(None, (row.get('event_types') or '').split('|'))),
            products=tuple(filter(None, (row.get('products') or '').split('|'))),
            target_role=(row.get('target_role') or '').strip() or None))

    for line, row in enumerate(_rows(directory / "source_places.csv"), start=1):
        reference = _cite(row, directory / "source_places.csv", line)
        data.add_source_place(
            source_id=row["source_id"].strip(),
            place_id=row["place_id"].strip(),
            basis=(row.get("basis") or "jurisdiction").strip(),
            source=reference,
            # Optional: a mapping without one is always-known, which is
            # correct for the rows curated at the start and keeps every
            # existing row valid.
            known_from=(row.get("known_from") or "").strip() or None)

    counts = data.describe()
    report.update(counts)
    report["empty"] = not any(counts.values())
    if report["empty"]:
        report["reason"] = (
            "the curated registries ship empty. Entity, asset and exposure rows "
            "each require a citation, and inventing them would put unevidenced "
            "arcs on the map. Curate seraph/news/curated/*.csv, one citation per "
            "row, then reload")
    return data, report
