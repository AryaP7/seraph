# shared_types — pydantic mirrors of ARCHITECTURE.md §0 (shared foundation, no component ID)
"""Scalar aliases, pillar order, Result/Warning/Error algebra.

ARCHITECTURE.md §0 is written in TypeScript as an interface description
language; this module is its binding Python realisation. Field names are
snake_case; every model serialises to the ARCHITECTURE camelCase spelling via
``model_dump(by_alias=True)`` (alias generator), and accepts either spelling on
input (``populate_by_name=True``).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Generic, Literal, TypeVar, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)
from pydantic.alias_generators import to_camel

# --- scalar aliases -------------------------------------------------------

ISODate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
# IST, always explicit — AGENTS.md §5. Anything else fails validation at the seam.
ISOTimestamp = Annotated[
    str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30$")
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SymbolId = str
SectorId = str
RunId = str

IST = timezone(timedelta(hours=5, minutes=30))


def ist_timestamp(dt: datetime) -> str:
    """Format an aware datetime as the canonical IST ISOTimestamp string."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime — timestamps must be explicit IST (+05:30)")
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def ist_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


# --- pillar order ---------------------------------------------------------

# PILLAR ORDER IS GLOBAL AND FIXED. Every Vec3, Mat3 and AvailabilityMask in
# this system uses this order. Violating it silently corrupts the CSRS.
PILLAR_ORDER = ["hawkes", "rmt", "hamilton"]
PillarId = Literal["hawkes", "rmt", "hamilton"]

Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]
# D2 — which pillars carry genuine information at this timestamp.
AvailabilityMask = tuple[bool, bool, bool]


def _validate_simplex(v: Vec3) -> Vec3:
    if any(x < 0 for x in v):
        raise ValueError(f"Simplex3 components must be >= 0; got {v}")
    if abs(sum(v) - 1.0) > 1e-9:
        raise ValueError(f"Simplex3 must sum to 1 (±1e-9); got sum={sum(v)!r}")
    return v


Simplex3 = Annotated[Vec3, AfterValidator(_validate_simplex)]


# --- base model -----------------------------------------------------------


class FrozenModel(BaseModel):
    """`readonly` in ARCHITECTURE ⇒ frozen=True here (AGENTS.md §6)."""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )


# --- warnings -------------------------------------------------------------

WarningCode = Literal[
    "PARTIAL_COVERAGE",
    "ESTIMATOR_FALLBACK",
    "STALE_OBSERVATION",
    "LOW_EVENT_COUNT",
    "UNIVERSE_UNDERFILLED",
    "SOURCE_SCHEMA_LEGACY",
    "MASK_DEGRADED",        # D2: scoring on fewer than 3 pillars
    "REBALANCE_ADJACENT",   # D3: Ω_t computed across a membership change
    "COMMON_SUPPORT_LOW",   # D3: eigenvector overlap below floor
    "NOISE_SATURATED",      # D4: R^(p) at ceiling, pillar contributing ~nothing
]


class SeraphWarning(FrozenModel):
    code: WarningCode
    message: str
    context: dict[str, str | int | float] = Field(default_factory=dict)


# --- error variants (discriminated on `kind`) -----------------------------


class SourceUnavailable(FrozenModel):
    kind: Literal["SOURCE_UNAVAILABLE"] = "SOURCE_UNAVAILABLE"
    source: str
    http_status: int | None = None
    retryable: Literal[True] = True


class SourceBlocked(FrozenModel):
    # NSE blocks datacentre IPs — verified constraint, non-retryable so it
    # does not burn retries.
    kind: Literal["SOURCE_BLOCKED"] = "SOURCE_BLOCKED"
    source: str
    hint: Literal["residential-ip-required"] = "residential-ip-required"
    retryable: Literal[False] = False


class SchemaMismatch(FrozenModel):
    kind: Literal["SCHEMA_MISMATCH"] = "SCHEMA_MISMATCH"
    source: str
    expected: str
    received: str
    retryable: Literal[False] = False


class InsufficientHistory(FrozenModel):
    kind: Literal["INSUFFICIENT_HISTORY"] = "INSUFFICIENT_HISTORY"
    required: int
    available: int
    as_of: ISODate
    retryable: Literal[False] = False


class EstimationDiverged(FrozenModel):
    kind: Literal["ESTIMATION_DIVERGED"] = "ESTIMATION_DIVERGED"
    estimator: str
    iterations: int
    last_objective: float
    retryable: Literal[False] = False


class ConstraintViolated(FrozenModel):
    kind: Literal["CONSTRAINT_VIOLATED"] = "CONSTRAINT_VIOLATED"
    constraint: str
    observed: float
    bound: float
    retryable: Literal[False] = False


class MissingDependency(FrozenModel):
    kind: Literal["MISSING_DEPENDENCY"] = "MISSING_DEPENDENCY"
    entity: str
    as_of: ISOTimestamp
    retryable: Literal[True] = True


class EmptyMask(FrozenModel):
    # D2 degenerate case: nothing to score.
    kind: Literal["EMPTY_MASK"] = "EMPTY_MASK"
    ts: ISOTimestamp
    retryable: Literal[False] = False


class ContractViolation(FrozenModel):
    kind: Literal["CONTRACT_VIOLATION"] = "CONTRACT_VIOLATION"
    field: str
    detail: str
    retryable: Literal[False] = False


SeraphError = Annotated[
    Union[
        SourceUnavailable,
        SourceBlocked,
        SchemaMismatch,
        InsufficientHistory,
        EstimationDiverged,
        ConstraintViolated,
        MissingDependency,
        EmptyMask,
        ContractViolation,
    ],
    Field(discriminator="kind"),
]


# --- Result<T> = Ok<T> | Err ---------------------------------------------
# Components never raise across a boundary — they return Err (AGENTS.md §5).

T = TypeVar("T")


class Ok(FrozenModel, Generic[T]):
    status: Literal["ok"] = "ok"
    value: T
    warnings: tuple[SeraphWarning, ...] = ()


class Err(FrozenModel):
    status: Literal["error"] = "error"
    error: SeraphError


Result = Union[Ok[T], Err]


def ok(value: T, warnings: tuple[SeraphWarning, ...] = ()) -> Ok[T]:
    return Ok(value=value, warnings=warnings)


def err(error) -> Err:
    return Err(error=error)
