# C12 — News → globe adapter (T13; audit findings R07/R08).
"""Put sourced events on the globe the console already draws, or say why not.

**The defect (R07/R08).** `build_news_payload()` existed, ran against the real
news store, and nothing called it. The console's map drew a hardcoded
fabricated dataset — four Indian states with invented stress ratios, two arcs
with invented endpoints — and the payload carried one flat string,
`news_status='FABRICATED PREVIEW'`, for every surface at once. So a real story
could not reach the map, and a viewer could not tell which parts of the map
were real.

**What this module is.** The single adapter between the news channel's
overlays and the renderer's geometry. Everything the map draws passes through
here, which is what makes three rules enforceable rather than hoped for:

1. **A node is placed by evidence or not at all.** A node whose place cannot
   be resolved to a coordinate goes to `unresolved`, which the signal rail and
   the review queue show. It never becomes a point at the operator's
   headquarters, at the country centroid, or anywhere else convenient.
2. **Precision is carried, not rounded away.** `location_precision` is one of
   `facility`, `city`, `region`, `country`, taken from the record that
   supplied the coordinate. A country-level policy origin and a specific plant
   are different claims and the renderer is told which it has.
3. **Layers do not blend.** Event origins, potentially affected locations,
   documented transmission paths and (optionally) market-pillar diagnostics
   are separate layers with separate legends. A news mechanism labelled
   "negative" is not CSRS red, and nothing here converts one into the other.

**Preview content is kept, in its own layer, labelled.** The existing
illustrative dataset is not deleted — it is returned under
`layers.preview` with `status="preview"` and `fabricated=True`, so the two can
coexist on screen with the combination stated. No preview coordinate, stress
number or dependency is ever emitted into the evidenced layers.

**One coordinate adapter.** `to_globe()` is the only lon/lat → world-space
conversion, and it is the exact arithmetic the renderer's `toXYZ` performs.
`tests/test_t13_globe_payload.py` checks it against known points and across
the antimeridian, and cross-checks it against the JavaScript.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, Sequence

from seraph.news.model import word_tokens

ADAPTER_VERSION = "c12.globe_payload/2026-10-17.1"

#: The renderer's geometry vocabulary. Bumping this is how a mapping change
#: becomes visible to anyone reading a stored payload.
GEOMETRY_MAP_VERSION = "c12.globe_geometry/2026-10-17.1"

LocationPrecision = Literal["facility", "point", "city", "region", "country"]
PRECISION_BY_PLACE_KIND: "Mapping[str, LocationPrecision]" = {
    "country": "country", "state": "region", "district": "region",
    "city": "city",
    # A coordinate the source itself reported, with its own uncertainty and
    # no administrative meaning. A hazard epicentre is not a city.
    "point": "point",
}

#: Marker treatment per precision. The renderer keys its outline on this, so a
#: country-level claim cannot be drawn as a pinpoint.
MARKER_BY_PRECISION: "Mapping[str, str]" = {
    "facility": "pin", "point": "dot", "city": "dot", "region": "ring",
    "country": "outline",
}

SEVERITY_ORDER = ("minor", "moderate", "major", "severe")
CONFIDENCE_ORDER = ("low", "medium", "high")

#: How many transmission paths may be drawn at once. Beyond this the payload
#: reports a hidden count rather than quietly dropping evidence — visual
#: culling is not absence.
DEFAULT_MAX_EDGES = 24


# --------------------------------------------------------- the one adapter


def to_globe(lon: float, lat: float, radius: float = 1.0
             ) -> "tuple[float, float, float]":
    """lon/lat degrees → renderer world space. +Y is the north pole.

    This is `toXYZ` from the renderer, in Python, so the server and the
    browser cannot disagree about where a point is:

        p = (90 - lat) * D2R ; t = (lon + 180) * D2R
        x = -r sin p cos t ; y = r cos p ; z = r sin p sin t
    """
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"latitude {lat} is outside [-90, 90]")
    p = math.radians(90.0 - lat)
    t = math.radians(_wrap_lon(lon) + 180.0)
    return (-radius * math.sin(p) * math.cos(t),
            radius * math.cos(p),
            radius * math.sin(p) * math.sin(t))


def _wrap_lon(lon: float) -> float:
    """Normalise longitude into [-180, 180).

    The antimeridian is a seam in the data, not in the sphere: 181 and -179
    are the same meridian and must land on the same point.

    A value already in range is returned untouched. Running every coordinate
    through the modulo would nudge 84.85 to 84.85000000000002, and a stored
    facility coordinate must be exactly what the registry recorded.
    """
    lon = float(lon)
    if -180.0 <= lon < 180.0:
        return lon
    return (lon + 180.0) % 360.0 - 180.0


def _slug(value: str) -> str:
    """A stable, collision-free id fragment for any value, in any script.

    X01 (completion-audit verification, Part 3). This was
    `re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")`, which
    deletes every non-ASCII character. Two different Devanagari state names
    therefore produced the SAME geometry id:

        geo:in-state:uttar-pradesh   <- 'Uttar Pradesh'
        geo:in-state:                <- 'उत्तर प्रदेश'
        geo:in-state:                <- 'तमिलनाडु'

    so the renderer pinned both states to one mesh. Same bug class as N02's
    headline grouping and X02's entity resolver.

    The ASCII form is kept verbatim where it is already unambiguous, so
    every existing id is unchanged and no stored payload or saved evidence
    is invalidated. When normalisation would lose information -- an empty
    result, or characters dropped -- a short content hash of the original
    is appended, which distinguishes the cases without making ASCII ids
    unreadable.
    """
    text = str(value)
    ascii_form = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    # Did the ASCII reduction lose anything that mattered? Compare against
    # a script-agnostic tokenisation of the same string.
    meaningful = "".join(word_tokens(text))
    if ascii_form and meaningful == re.sub(r"[^a-z0-9]+", "", text.lower()):
        return ascii_form
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{ascii_form}-u{digest}" if ascii_form else f"u{digest}"


# ------------------------------------------------------- geometry resolver


@dataclass(frozen=True)
class Placement:
    """Where a node is, how precisely, and which mesh carries it."""

    geometry_id: str
    mesh_id: str
    mesh_kind: str
    coordinates: "tuple[float, float]"
    location_precision: str
    source_record: str

    def describe(self) -> dict:
        return dict(geometry_id=self.geometry_id, mesh_id=self.mesh_id,
                    mesh_kind=self.mesh_kind,
                    coordinates=[self.coordinates[0], self.coordinates[1]],
                    coordinate_order="lon_lat",
                    location_precision=self.location_precision,
                    marker=MARKER_BY_PRECISION[self.location_precision],
                    world=list(to_globe(*self.coordinates)),
                    placed_from=self.source_record,
                    geometry_map_version=GEOMETRY_MAP_VERSION)


class GeometryResolver:
    """Registry record → renderer geometry, or nothing.

    The mapping is a rule, not a table of hand-placed dots:

    * an **asset** with its own coordinate is a `facility`;
    * a **place** with a coordinate is a `city` or `region` by its kind;
    * a **place** without a coordinate falls back to its parent chain, and the
      precision degrades with it, so a city resolved through its state is
      labelled `region` and not `city`;
    * a **country** resolves to the renderer's own country ring by ISO-3, so
      no coordinate is invented for it at all;
    * an Indian **state** resolves to the renderer's state ring by name.

    Anything that reaches the end of those rules is unresolved and says so.
    """

    def __init__(self, master, *, state_meshes: "Iterable[str]" = (),
                 country_meshes: "Iterable[str]" = ()) -> None:
        self.master = master
        self.state_meshes = {s.lower(): s for s in state_meshes}
        self.country_meshes = {c.upper() for c in country_meshes}

    # ------------------------------------------------------------- lookups

    def _place(self, place_id: str):
        return getattr(self.master, "places", {}).get(place_id)

    def _asset(self, asset_id: str):
        return getattr(self.master, "assets", {}).get(asset_id)

    def resolve(self, target_id: str) -> "Placement | None":
        """Resolve by what the id IS, not by how it is spelled.

        Curated ids are bare snake_case (`in_mh_mumbai`), while fixtures and
        some call sites use `place:`/`asset:` prefixes. Keying on the prefix
        would silently fail to place every real row, so the registry is asked
        first and the prefix is only a fallback.
        """
        if target_id.startswith("sector:"):
            # A sector is not a point on the earth. Sector nodes belong to the
            # sector panel; what the globe shows is the assets and regions
            # that sector's exposure actually reaches.
            return None
        if target_id in getattr(self.master, "assets", {}):
            return self._from_asset(target_id)
        if target_id in getattr(self.master, "places", {}):
            return self._from_place(target_id, degraded=False)
        if target_id.startswith("asset:"):
            return self._from_asset(target_id)
        if target_id.startswith("place:"):
            return self._from_place(target_id, degraded=False)
        # Anything else — an entity, typically — is located only through the
        # place the registry gives it. `MasterData.place_of` deliberately
        # returns nothing for an entity, because a registered office is not an
        # operating location; this adapter does not second-guess that.
        resolver = getattr(self.master, "place_of", None)
        place_id = resolver(target_id) if callable(resolver) else None
        if place_id and place_id != target_id:
            return self._from_place(place_id, degraded=False)
        return None

    def _from_asset(self, asset_id: str) -> "Placement | None":
        asset = self._asset(asset_id)
        if asset is None:
            return None
        if asset.lat is not None and asset.lon is not None:
            return Placement(
                geometry_id=f"geo:asset:{_slug(asset.asset_id)}",
                mesh_id="asset_marker", mesh_kind="point",
                coordinates=(_wrap_lon(asset.lon), float(asset.lat)),
                location_precision="facility",
                source_record=f"asset:{asset.asset_id}")
        # No facility coordinate: fall back to its place, with the precision
        # degraded to whatever that place actually is.
        if asset.place_id:
            return self._from_place(asset.place_id, degraded=True)
        return None

    def _from_place(self, place_id: str, *, degraded: bool
                    ) -> "Placement | None":
        place = self._place(place_id)
        if place is None:
            return None
        precision = PRECISION_BY_PLACE_KIND.get(place.kind, "region")

        if place.kind == "country" and place.iso_code:
            iso = place.iso_code.upper()
            if not self.country_meshes or iso in self.country_meshes:
                centre = ((_wrap_lon(place.lon), float(place.lat))
                          if place.lat is not None and place.lon is not None
                          else None)
                return Placement(
                    geometry_id=f"geo:country:{iso}",
                    mesh_id=f"world_country:{iso}", mesh_kind="country_ring",
                    coordinates=centre or (0.0, 0.0),
                    location_precision="country",
                    source_record=f"place:{place.place_id}"
                    + ("" if centre else " (ring only; no centroid supplied)"))

        if place.kind == "state":
            mesh = self.state_meshes.get(place.name.lower())
            if mesh:
                centre = ((_wrap_lon(place.lon), float(place.lat))
                          if place.lat is not None and place.lon is not None
                          else None)
                return Placement(
                    geometry_id=f"geo:in-state:{_slug(place.name)}",
                    mesh_id=f"india_state:{mesh}", mesh_kind="state_ring",
                    coordinates=centre or (0.0, 0.0),
                    location_precision="region",
                    source_record=f"place:{place.place_id}"
                    + ("" if centre else " (ring only; no centroid supplied)"))

        if place.lat is not None and place.lon is not None:
            return Placement(
                geometry_id=f"geo:place:{_slug(place.place_id)}",
                mesh_id="place_marker", mesh_kind="point",
                coordinates=(_wrap_lon(place.lon), float(place.lat)),
                location_precision="region" if degraded else precision,
                source_record=f"place:{place.place_id}")

        if place.parent_id:
            parent = self._from_place(place.parent_id, degraded=True)
            if parent is not None:
                return parent
        return None


# ------------------------------------------------------------- the payload


def _display_name(master, target_id: str) -> str | None:
    """The registry's own name for a node, for the label on the globe."""
    place = getattr(master, "places", {}).get(target_id)
    if place is not None:
        return place.name
    asset = getattr(master, "assets", {}).get(target_id)
    if asset is not None:
        return asset.name
    entity = getattr(master, "entities", {}).get(target_id)
    if entity is not None:
        return entity.name
    return None


def _rank(value: str, order: "Sequence[str]") -> int:
    try:
        return order.index(value)
    except ValueError:
        return -1


def build_globe_payload(news_payload: dict, master, *,
                        revision: str, as_of: str,
                        sources_health: dict | None = None,
                        state_meshes: "Iterable[str]" = (),
                        country_meshes: "Iterable[str]" = (),
                        max_edges: int = DEFAULT_MAX_EDGES,
                        preview: dict | None = None,
                        role: str = "retail",
                        pillar_diagnostics: dict | None = None) -> dict:
    """The `news` transport branch the console renders.

    `news_payload` is `build_news_payload()`'s output, unchanged. Nothing is
    recomputed here: this projects what the news channel already decided onto
    geometry, so a disagreement between the map and the signal rail is not
    possible.
    """
    if news_payload.get('decision_ts') and news_payload['decision_ts'] != as_of:
        raise ValueError('news payload clock does not match globe context')
    if news_payload.get('source_places'):
        import copy
        from seraph.news.model import Place
        master = copy.deepcopy(master)
        for row in news_payload['source_places']:
            master.add_place(Place(row['place_id'], row['name'],
                                   row.get('kind') or 'point',
                                   lat=row['lat'], lon=row['lon']))
    resolver = GeometryResolver(master, state_meshes=state_meshes,
                                country_meshes=country_meshes)
    surfaces = news_payload.get("surfaces", {})
    geography = surfaces.get("geography", {})
    signals = surfaces.get("signals", {})
    assets = surfaces.get("assets", {})
    sectors = surfaces.get("sector_stress", {})

    nodes: dict[str, dict] = {}
    # Deduplicated by node id: thirty stories mentioning one unplaceable body
    # is one review item with thirty events, not thirty review items.
    unplaceable: dict[str, dict] = {}

    def place(target_id: str, *, kind: str, layer: str, severity: str | None,
              evidence_ids: "Sequence[str]", events: "Sequence[str]",
              label: str | None = None) -> str | None:
        placement = resolver.resolve(target_id)
        if placement is None and str(target_id).startswith("sector:"):
            # Handled above as a sector-terminated path. Not a review item.
            return None
        if placement is None:
            held = unplaceable.setdefault(target_id, dict(
                node_id=target_id, kind=kind, layer=layer,
                reason=("no evidenced coordinate or mapped geometry for this "
                        "record; it stays in the signal rail and the review "
                        "queue rather than being drawn somewhere plausible"),
                events=[]))
            held["events"] = sorted(set(held["events"]) | set(events))
            return None
        node = nodes.setdefault(target_id, dict(
            node_id=target_id, kind=kind,
            # A map label names the PLACE. The headline belongs in the click
            # detail: a marker captioned with a whole press-release title is
            # unreadable on a globe and says nothing about where it is.
            label=_display_name(master, target_id) or label or target_id,
            place_id=(target_id if target_id.startswith("place:")
                      else getattr(master, "place_of", lambda _x: None)(target_id)),
            layers=[], severity=None, events=[], evidence_ids=[],
            status="derived", **placement.describe()))
        if layer not in node["layers"]:
            node["layers"].append(layer)
        if severity and (_rank(severity, SEVERITY_ORDER)
                         > _rank(node["severity"] or "", SEVERITY_ORDER)):
            node["severity"] = severity
        node["events"] = sorted(set(node["events"]) | set(events))
        node["evidence_ids"] = sorted(set(node["evidence_ids"])
                                      | set(evidence_ids))
        return target_id

    # --- layer 1: event origins ------------------------------------------
    origins: list[str] = []
    for item in signals.get("items", []):
        for actor in item.get("origins", ()) or ():
            placed = place(actor, kind="origin", layer="origins",
                           severity=None, evidence_ids=item.get("sources", ()),
                           events=[item["event_id"]],
                           label=item.get("headline"))
            if placed:
                origins.append(placed)

    provenance = []
    for item in signals.get('items', []):
        for node_id in item.get('issuer_provenance', []):
            placed = place(node_id, kind='issuer_provenance', layer='provenance',
                           severity=None, evidence_ids=item.get('sources', ()), events=[item['event_id']])
            if placed: provenance.append(placed)

    # --- layer 1b: the goods an instrument covers come from here ----------
    #
    # Evidenced, and none of the other layers: the instrument names this
    # country as the origin of the goods under investigation. It says nothing
    # yet about who is affected — that still needs an exposure edge.
    subjects: list[str] = []
    for item in signals.get("items", []):
        for node_id in item.get("subject_origins", ()) or ():
            placed = place(node_id, kind="subject", layer="subjects",
                           severity=None, evidence_ids=item.get("sources", ()),
                           events=[item["event_id"]])
            if placed:
                subjects.append(placed)

    # --- layer 2a: locations NAMED but whose role is not established ------
    #
    # A speech venue, a dateline and a registered address look identical to a
    # name matcher. Drawing them as "affected" would put an impact on the map
    # that nothing evidences, and dropping them would hide a real, sourced
    # location. They get their own layer with their role stated.
    mentioned: list[str] = []
    for item in signals.get("items", []):
        for entry in item.get("locations", ()) or ():
            if entry.get("role") != "mentioned": continue
            placed = place(entry["node_id"], kind="mention", layer="mentions",
                           severity=None, evidence_ids=item.get("sources", ()),
                           events=[item["event_id"]])
            if placed:
                mentioned.append(placed)

    # --- layer 2b: potentially affected locations and assets --------------
    affected: list[str] = []
    for region in geography.get("regions", []):
        placed = place(region["place_id"], kind="place", layer="affected",
                       severity=region.get("severity"), evidence_ids=(),
                       events=region.get("events", ()),
                       label=region.get("name"))
        if placed:
            affected.append(placed)
    for item in assets.get("items", []):
        if not item.get("events"):
            continue
        placed = place(item["asset_id"], kind="asset", layer="affected",
                       severity=None, evidence_ids=(),
                       events=item.get("events", ()), label=item.get("name"))
        if placed:
            affected.append(placed)

    # --- layer 3: documented transmission paths ---------------------------
    #
    # A path that ENDS in a sector is complete, not broken. The globe draws
    # geography, so the sector leg is handed to the sector panel and recorded
    # here as a terminated path. Filing it in the review queue, as happened
    # before, reported a deliberate design rule as a missing coordinate and
    # buried real geography failures among non-failures.
    edges = []
    sector_terminated = []
    for arc in geography.get("arcs", []):
        for end, role in ((arc["from_id"], "from"), (arc["to_id"], "to")):
            if str(end).startswith("sector:"):
                sector_terminated.append(dict(
                    edge_id=arc["edge_id"], event_id=arc["event_id"],
                    sector=str(end).removeprefix("sector:"), endpoint_role=role,
                    mechanism=arc.get("mechanism"),
                    evidence_ids=list(arc.get("evidence", ())),
                    shown_in="sector_panel",
                    note=("a sector is not a point on the earth. This leg of "
                          "the path is shown in the sector panel; the globe "
                          "shows the assets and regions it reaches")))
        source = place(arc["from_id"], kind="endpoint", layer="paths",
                       severity=None, evidence_ids=arc.get("evidence", ()),
                       events=[arc["event_id"]])
        target = place(arc["to_id"], kind="endpoint", layer="paths",
                       severity=None, evidence_ids=arc.get("evidence", ()),
                       events=[arc["event_id"]])
        if source is None or target is None:
            continue
        edges.append(dict(
            edge_id=arc["edge_id"], event_id=arc["event_id"],
            event_revision=arc.get("event_revision"),
            from_node=source, to_node=target,
            mechanism=arc.get("mechanism"),
            direction=arc.get("direction", "unknown"),
            confidence=arc.get("confidence", "low"),
            magnitude=arc.get("magnitude"), unit=arc.get("unit"),
            evidence_ids=list(arc.get("evidence", ())),
            known_at=arc.get("known_at"),
            valid_from=arc.get("valid_from"), valid_to=arc.get("valid_to"),
            status="observed", relationship_status="documented", impact_status="hypothesis",
            note=("a documented relationship with its own evidence, not a "
                  "fitted contagion edge and not a CSRS quantity")))

    # Deterministic priority: better-evidenced paths first, ties broken by
    # edge id so the same inputs always draw the same picture.
    edges.sort(key=lambda e: (-_rank(e["confidence"], CONFIDENCE_ORDER),
                              -len(e["evidence_ids"]), e["edge_id"]))
    visible, hidden = edges[:max_edges], edges[max_edges:]

    payload = dict(
        revision=revision, as_of=as_of,
        version=ADAPTER_VERSION, geometry_map_version=GEOMETRY_MAP_VERSION,
        sources_health=sources_health or news_payload.get("source_coverage"),
        coverage=news_payload.get("source_coverage"),
        signals=signals,
        sector_aggregates=sectors,
        nodes=sorted(nodes.values(), key=lambda n: n["node_id"]),
        edges=visible,
        sector_terminated_paths=sorted(
            {(d["edge_id"], d["sector"]): d
             for d in sector_terminated}.values(),
            key=lambda d: (d["edge_id"], d["sector"])),
        hidden_edges=dict(
            count=len(hidden), edge_ids=[e["edge_id"] for e in hidden],
            reason=(f"more than {max_edges} documented paths are visible at "
                    f"this decision time; the rest are hidden for legibility "
                    f"and are listed here. Hidden is not absent")),
        unresolved=sorted(unplaceable.values(),
                          key=lambda u: u["node_id"]),
        review_queue=dict(
            count=len(unplaceable),
            note=("these records have evidence but no mapped geometry. They "
                  "are reviewable work, not errors, and they are deliberately "
                  "not drawn")),
        layers=dict(
            provenance=dict(node_ids=sorted(set(provenance)), legend='publisher / issuer provenance',
                            semantics='publishing office or issuing jurisdiction; not event occurrence'),
            origins=dict(node_ids=sorted(set(origins)), legend="event origin",
                         semantics="evidenced event occurrence; never inferred from publisher office"),
            subjects=dict(
                node_ids=sorted(set(subjects)),
                legend="goods from here are covered by the instrument",
                semantics=("the document names this country as the origin of "
                           "the goods under investigation. Who is affected by "
                           "that still requires a documented exposure")),
            mentions=dict(
                node_ids=sorted(set(mentioned)),
                legend="named in the story; role not established",
                semantics=("the location appears in the text. Whether it is "
                           "affected, the origin, or merely a venue is not "
                           "something a name match can decide, so no impact "
                           "is claimed here")),
            affected=dict(node_ids=sorted(set(affected)),
                          legend="potentially affected location or asset",
                          semantics=("an evidenced exposure relationship "
                                     "reaches here; it is not a loss estimate")),
            paths=dict(edge_ids=[e["edge_id"] for e in visible],
                       legend="documented transmission path",
                       semantics="an ExposureEdge with its own evidence"),
            market_diagnostics=(
                dict(status="attached", legend="measured pillar diagnostic",
                     semantics=("the market channel, shown for context only; "
                                "it shares no colour scale with the news "
                                "layers"), **pillar_diagnostics)
                if pillar_diagnostics else
                dict(status="absent", node_ids=[],
                     reason="no measured per-location pillar diagnostic exists")),
            preview=_preview_layer(preview),
        ),
        limitations=_limitations(news_payload, unplaceable, hidden, preview),
        channel_note=news_payload.get("channel_note"),
    )
    # Click detail is computed here, once, rather than reimplemented in
    # JavaScript. Two implementations of "what this node claims" is two
    # chances to disagree about evidence, and only one of them is tested.
    payload["role"] = role
    payload["details"] = {
        node_id: node_detail(payload, node_id, role=role)
        for node_id in ([n["node_id"] for n in payload["nodes"]]
                        + [u["node_id"] for u in payload["unresolved"]])}
    return payload


def _preview_layer(preview: dict | None) -> dict:
    if not preview:
        return dict(status="absent", fabricated=False, items=[],
                    note="no illustrative dataset is attached to this payload")
    return dict(
        status="preview", fabricated=True,
        label="FABRICATED PREVIEW — illustrative geography, not evidence",
        items=preview.get("items", []),
        arcs=preview.get("arcs", []),
        note=("kept as its own layer so the original console identity "
              "survives. Nothing in this layer enters estimate_impacts, "
              "portfolio coverage or alert dispatch, and it shares no "
              "identifier space with the evidenced layers"))


def _limitations(news_payload: dict, unresolved, hidden, preview) -> list[str]:
    out = []
    coverage = news_payload.get("source_coverage") or {}
    if not coverage.get("complete", True):
        out.append(
            f"source coverage is incomplete: {coverage.get('covered')} of "
            f"{coverage.get('total')} sources were read. An empty map with "
            f"uncovered sources is missing coverage, not a quiet world")
    if unresolved:
        out.append(
            f"{len(unresolved)} evidenced record(s) have no mapped geometry "
            f"and are not drawn; they are in the review queue")
    if hidden:
        out.append(f"{len(hidden)} documented path(s) are hidden for "
                   f"legibility and are listed in hidden_edges")
    if preview:
        out.append("an illustrative preview layer is present and is labelled "
                   "FABRICATED; real signals and fabricated geography are on "
                   "screen together")
    if news_payload.get("injection_flags"):
        out.append(f"{news_payload['injection_flags']} story group(s) tripped "
                   f"the prompt-injection check and were handled as data")
    out.append("news mechanisms are ordinal and evidential. They are not "
               "probabilities of financial loss and share no scale with CSRS")
    return out


# ------------------------------------------------------------ click detail


def node_detail(payload: dict, node_id: str, *, role: str = "retail") -> dict:
    """What a click shows: the claim, its times, its evidence and its gaps."""
    node = next((n for n in payload.get("nodes", [])
                 if n["node_id"] == node_id), None)
    if node is None:
        unresolved = next((u for u in payload.get("unresolved", [])
                           if u["node_id"] == node_id), None)
        if unresolved is not None:
            return dict(node_id=node_id, status="unresolved",
                        reason=unresolved["reason"],
                        events=unresolved.get("events", []),
                        allowed_actions=_actions(role, resolved=False))
        return dict(node_id=node_id, status="unknown",
                    reason="no such node in this payload")

    items = {i["event_id"]: i for i in
             payload.get("signals", {}).get("items", [])}
    related = [items[e] for e in node["events"] if e in items]
    edges = [e for e in payload.get("edges", [])
             if node_id in (e["from_node"], e["to_node"])]
    return dict(
        node_id=node_id, status=node["status"], kind=node["kind"],
        label=node.get("label"),
        placement=dict(geometry_id=node["geometry_id"],
                       mesh_id=node["mesh_id"],
                       coordinates=node["coordinates"],
                       coordinate_order=node["coordinate_order"],
                       location_precision=node["location_precision"],
                       placed_from=node["placed_from"]),
        events=[dict(
            event_id=item["event_id"], headline=item["headline"],
            event_type=item["event_type"], lifecycle=item["lifecycle"],
            revision=item.get("revision"),
            actor=item.get("actors", []), affected=item.get("affected", []),
            source_statement=item.get("source_statement"),
            published_at=item.get("published_at"),
            first_seen_at=item.get("first_seen_at"),
            effective_at=item.get("effective_at"),
            sources=item.get("sources", []),
            evidence_links=item.get('evidence_links', []),
            interpretation=item.get('interpretation'),
            impacts=item.get('impacts', []),
            unknowns=item.get("unresolved", [])) for item in related],
        mechanism_path=[dict(
            edge_id=e["edge_id"], mechanism=e["mechanism"],
            direction=e["direction"], confidence=e["confidence"],
            magnitude=e["magnitude"], unit=e["unit"],
            evidence_ids=e["evidence_ids"], known_at=e.get("known_at"),
            valid_from=e.get("valid_from"), valid_to=e.get("valid_to"))
            for e in edges],
        allowed_actions=_actions(role, resolved=True),
        qualification=("times shown are the source's publication time and "
                       "SERAPH's first-seen time. A replay is bounded by "
                       "first-seen, never by publication"),
    )


def _actions(role: str, *, resolved: bool) -> list[str]:
    base = ["open_source", "copy_evidence_ids"]
    if role == "retail":
        return base + (["add_to_watchlist"] if resolved else [])
    if role == "institutional":
        return base + ["open_scenario", "attach_to_review"]
    if role == "regulator":
        return base + ["open_case", "request_evidence_export"]
    return base
