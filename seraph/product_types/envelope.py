# product_types — the metadata envelope (PRODUCT-CONTRACTS §1)
"""`Envelope` — what every product datum carries across a boundary.

The four rules this module enforces mechanically, because prose does not:

1. **`unknown` is never `0`.** An unavailable envelope has no value at all;
   you cannot read one out of it without being told it is absent.
2. **A replay at `T` reads only what was knowable at `T`** — see `time.py`.
3. **`preview` never enters a calculation.** `Envelope.value_for_calculation()`
   refuses a preview envelope, so a fabricated placeholder cannot silently
   become an input.
4. **Status travels with the datum**, not with the panel.

An `estimate` additionally has to say what its uncertainty *means*. A number
in `[0, 1]` could be a probability, a share, a rank or a confidence; the
`Uncertainty.meaning` field forces the producer to say which.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

from seraph.product_types.time import Timing
from seraph.shared_types import ISOTimestamp

#: Bump when the envelope's own shape changes.
ENVELOPE_SCHEMA_VERSION = 1

DataStatus = Literal[
    "observed",      # measured/recorded by an identified source
    "derived",       # computed by an identified producer from observed inputs
    "estimate",      # model output, with uncertainty whose meaning is published
    "scenario",      # hypothetical; depends on supplied assumptions
    "preview",       # illustrative placeholder; NEVER an input
    "unavailable",   # known to be absent
    "stale",         # real, but older than its freshness policy
]

AbsenceKind = Literal["structural", "transient"]

CALCULABLE = ("observed", "derived", "estimate", "scenario", "stale")


class PreviewUsedAsInput(RuntimeError):
    """A preview placeholder was about to enter a calculation."""


class ValueUnavailable(RuntimeError):
    """An absent datum was read as if it had a value."""


def content_id(*parts: Any) -> str:
    """Stable id from content. Same content, same id, every run."""
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class SourceRef:
    """Where a datum came from, precisely enough to fetch it again."""

    source_id: str
    reference: str                      # URL, file path, table row key
    content_hash: str | None = None     # hash of the raw bytes as received
    retrieved_at: ISOTimestamp | None = None
    note: str | None = None


@dataclass(frozen=True)
class Provenance:
    """Which component and version produced a derived or estimated datum."""

    producer: str                       # "C9.score", "news.impact", ...
    producer_version: str
    inputs: tuple[str, ...] = ()        # ids of the envelopes this consumed
    run_id: str | None = None
    model_id: str | None = None
    scenario_id: str | None = None


@dataclass(frozen=True)
class Coverage:
    """What population a datum covers — and what it does not.

    `measured_quiet` is the distinction the whole product turns on: a sector
    with no flagged exposure because it was checked and nothing was found is
    not the same as a sector nobody looked at. `population` is what was
    checked; `uncovered` is what was not.
    """

    population: str
    covered: int | None = None
    total: int | None = None
    uncovered: tuple[str, ...] = ()
    basis: str | None = None

    @property
    def fraction(self) -> float | None:
        if self.covered is None or not self.total:
            return None
        return self.covered / self.total

    @property
    def is_complete(self) -> bool:
        return bool(self.total) and self.covered == self.total and not self.uncovered


@dataclass(frozen=True)
class Uncertainty:
    """An interval is useless without its meaning. Say it."""

    kind: Literal["interval", "stddev", "probability", "qualitative"]
    meaning: str                        # "95% conditional CSRS interval", ...
    lower: float | None = None
    upper: float | None = None
    value: float | None = None
    label: Literal["low", "medium", "high"] | None = None

    def __post_init__(self) -> None:
        if not self.meaning.strip():
            raise ValueError("uncertainty must state what it means")
        if self.kind == "interval" and (self.lower is None or self.upper is None):
            raise ValueError("an interval needs both bounds")
        if (self.lower is not None and self.upper is not None
                and self.lower > self.upper):
            raise ValueError(f"interval is inverted: {self.lower} > {self.upper}")


@dataclass(frozen=True)
class Envelope:
    """A product datum and everything needed to read it honestly."""

    kind: str
    status: DataStatus
    value: Any = None
    id: str | None = None
    unit: str | None = None
    timing: Timing | None = None
    provenance: Provenance | None = None
    sources: tuple[SourceRef, ...] = ()
    coverage: Coverage | None = None
    uncertainty: Uncertainty | None = None
    absence: AbsenceKind | None = None
    absence_reason: str | None = None
    revision: int = 1
    supersedes: str | None = None
    owner: str | None = None
    org: str | None = None
    limitations: tuple[str, ...] = ()
    schema_version: int = ENVELOPE_SCHEMA_VERSION
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status == "unavailable":
            if self.absence not in ("structural", "transient"):
                raise ValueError(
                    f"{self.kind}: an unavailable datum must declare absence as "
                    "'structural' or 'transient' — absence type is never inferred")
            if self.value is not None:
                raise ValueError(
                    f"{self.kind}: an unavailable datum carries no value. Absent is "
                    "not zero, and not a middle bucket")
        elif self.absence is not None:
            raise ValueError(f"{self.kind}: absence is only meaningful when unavailable")
        if self.status == "estimate" and self.uncertainty is None:
            raise ValueError(
                f"{self.kind}: an estimate must publish what its uncertainty means")
        if self.status in ("derived", "estimate") and self.provenance is None:
            raise ValueError(
                f"{self.kind}: a {self.status} datum must name its producer and version")
        if self.status == "observed" and not self.sources:
            raise ValueError(
                f"{self.kind}: an observed datum must name at least one source")
        if self.id is None:
            object.__setattr__(self, "id", self._derive_id())

    def _derive_id(self) -> str:
        return content_id(self.kind, self.status, self.revision,
                          self.unit, self.value,
                          self.timing.describe() if self.timing else None,
                          asdict(self.provenance) if self.provenance else None,
                          [asdict(s) for s in self.sources])

    # ------------------------------------------------------------- reading

    @property
    def is_available(self) -> bool:
        return self.status != "unavailable"

    def value_for_calculation(self) -> Any:
        """Read the value for use as an INPUT. Refuses preview and absent data."""
        if self.status == "preview":
            raise PreviewUsedAsInput(
                f"{self.kind}: preview content is illustrative and must never enter "
                "a calculation. Connect its real producer first")
        if self.status == "unavailable":
            raise ValueUnavailable(
                f"{self.kind}: unavailable ({self.absence}: {self.absence_reason}). "
                "Handle the absence; do not substitute a value")
        return self.value

    def value_for_display(self, *, absent: Any = None) -> Any:
        """Read the value for DISPLAY. Absent renders as `absent`, not zero."""
        return absent if self.status == "unavailable" else self.value

    def visible_at(self, decision_ts: ISOTimestamp) -> bool:
        return self.timing is None or self.timing.visible_at(decision_ts)

    # ------------------------------------------------------------ revising

    def revise(self, **changes) -> "Envelope":
        """A new revision that records what it supersedes. Never mutates."""
        return replace(self, id=None, revision=self.revision + 1,
                       supersedes=self.id, **changes)

    def mark_stale(self, reason: str) -> "Envelope":
        if self.status in ("unavailable", "preview"):
            return self
        return replace(self, id=self.id, status="stale",
                       limitations=self.limitations + (reason,))

    # ----------------------------------------------------------- transport

    def to_payload(self) -> dict:
        """JSON-safe form for the UI transport. Status always travels."""
        out: dict = dict(id=self.id, kind=self.kind, status=self.status,
                         schemaVersion=self.schema_version, revision=self.revision)
        if self.status != "unavailable":
            out["value"] = self.value
        if self.unit:
            out["unit"] = self.unit
        if self.absence:
            out["absence"] = dict(kind=self.absence, reason=self.absence_reason)
        if self.timing:
            out["timing"] = self.timing.describe()
        if self.provenance:
            out["provenance"] = {k: v for k, v in asdict(self.provenance).items() if v}
        if self.sources:
            out["sources"] = [{k: v for k, v in asdict(s).items() if v}
                              for s in self.sources]
        if self.coverage:
            out["coverage"] = {**{k: v for k, v in asdict(self.coverage).items()
                                  if v not in (None, (), [])},
                               "fraction": self.coverage.fraction}
        if self.uncertainty:
            out["uncertainty"] = {k: v for k, v in asdict(self.uncertainty).items()
                                  if v is not None}
        if self.supersedes:
            out["supersedes"] = self.supersedes
        if self.owner:
            out["owner"] = self.owner
        if self.org:
            out["org"] = self.org
        if self.limitations:
            out["limitations"] = list(self.limitations)
        if self.extra:
            out["extra"] = self.extra
        return out


# --- constructors: the status is chosen deliberately, never by default ----

def observed(kind, value, *, sources, unit=None, timing=None, **kw) -> Envelope:
    return Envelope(kind=kind, status="observed", value=value, unit=unit,
                    sources=tuple(sources), timing=timing, **kw)


def derived(kind, value, *, provenance, unit=None, timing=None, **kw) -> Envelope:
    return Envelope(kind=kind, status="derived", value=value, unit=unit,
                    provenance=provenance, timing=timing, **kw)


def estimated(kind, value, *, provenance, uncertainty, unit=None, timing=None,
              **kw) -> Envelope:
    return Envelope(kind=kind, status="estimate", value=value, unit=unit,
                    provenance=provenance, uncertainty=uncertainty, timing=timing, **kw)


def scenario(kind, value, *, provenance, unit=None, **kw) -> Envelope:
    return Envelope(kind=kind, status="scenario", value=value, unit=unit,
                    provenance=provenance, **kw)


def preview(kind, value, *, note="illustrative placeholder; not a measurement",
            **kw) -> Envelope:
    """A labelled placeholder. `value_for_calculation()` will refuse it."""
    return Envelope(kind=kind, status="preview", value=value,
                    limitations=(note,), **kw)


def unavailable(kind, *, absence, reason, **kw) -> Envelope:
    return Envelope(kind=kind, status="unavailable", value=None,
                    absence=absence, absence_reason=reason, **kw)
