# C11 — Decision Support (FR43)
"""Portfolio overlay — C5's sector micro-flags mapped onto a user's holdings.

C11 translates, it does not compute risk. The only risk signal in play here is
the FR14 sector micro-flag, which reaches this module from C5 through the
caller; nothing here derives one, and — the part that matters — **an absent
flag is never read as a clean one**.

Exposure, defined once. Every percentage is of total portfolio value:

    totalValue   = Σ_h value(h)                            [must be > 0]
    value(s)     = Σ_{h : sector(h) = s} value(h)
    pct(s)       = 100 · value(s) / totalValue             [Σ_s pct(s) = 100]
    exposedPct   = Σ_{s : flag(s) = "amber"} pct(s)        ← the FR43 headline
    uncoveredPct = Σ_{s : s ∉ flag source} pct(s)
    coveredPct   = 100 − uncoveredPct

`flag(s) = "none"` therefore means *the flag source covers s and did not flag
it*. A sector the source says nothing about comes back `covered: false`, lands
in `uncoveredPct`, and raises PARTIAL_COVERAGE. Presenting it as "none" would
imply coverage the overlay does not have — the D2 reporting obligation this
component exists to honour. `hawkes_output` is empty today, so the honest
answer for a real portfolio is currently "100% uncovered" until C5 runs.

ARCHITECTURE §2 S10 types the per-sector flag as exactly `"none"|"amber"`, with
no member for "unknown", so coverage rides alongside the flag rather than
widening the union. Short positions are out of scope: exposure is a percentage
of portfolio value, which stops being defined once a holding can be negative,
so a negative value is rejected rather than netted.

**Not yet wired, and deliberately so.** Two integration steps sit outside this
module and neither is taken:

* S10 specifies `portfolioOverlay(userId, at)`, which needs a
  `StoreReader.user_portfolio()` read of E11 (C1's to add) and a micro-flag
  reader over E6. Neither exists, so this is a pure function over
  caller-supplied holdings and a caller-supplied flag source — which is also
  what keeps it testable in isolation.
* Nothing in `seraph/dashboard/` calls it. `build_view` can carry
  `portfolioExposurePct` but has no field for `uncoveredPct`, so wiring this
  into the retail view as it stands would show an exposure number without
  saying what was never checked — the failure `maskDegraded` exists to prevent.
  That field is a C12 RBAC decision (`ROLE_FIELDS`, asserted by CT-8), not
  something to add from here.

There is also no real micro-flag data to wire: `hawkes_output` holds zero rows
and has no production writer, so every flag this module has ever been handed
came from `fixtures.mock_generator.mock_sector_flags`, which is labelled T0 and
fabricated.
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, ValidationError, field_validator

from seraph.shared_types import (
    ContractViolation,
    Err,
    FrozenModel,
    Ok,
    SectorFlag,
    SectorId,
    SeraphWarning,
    SymbolId,
    err,
    ok,
)

#: The S10 union, verbatim. Not ours to widen.
MicroFlag = Literal["none", "amber"]
MICRO_FLAGS: tuple[MicroFlag, ...] = ("none", "amber")

#: Bucket for a holding whose sector the caller did not supply. Its value is
#: real so it is sized, but it can never be cleared: an unknown sector cannot
#: be matched against a micro-flag.
UNCLASSIFIED: SectorId = "unclassified"


class PortfolioHolding(FrozenModel):
    """One E11 `user_portfolio` row as C11 consumes it (SPEC §6 E11).

    `user_id` is the caller's own key and `exposure_pct` is what this module
    derives, so neither is an input. E11/E12 shapes live in C11 rather than in
    `shared_types` because ARCHITECTURE §1 assigns both entities to C11;
    promoting them is a separate, approval-gated change.
    """

    symbol: SymbolId
    value: float = Field(ge=0.0)
    quantity: float = Field(default=0.0, ge=0.0)
    sector: SectorId = UNCLASSIFIED

    @field_validator("symbol")
    @classmethod
    def _symbol_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("symbol must be a non-empty identifier")
        return v.strip()

    @field_validator("sector")
    @classmethod
    def _blank_sector_is_unclassified(cls, v: str) -> str:
        return v.strip() if v and v.strip() else UNCLASSIFIED

    @field_validator("value", "quantity")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v


def _as_holding(row: object, index: int) -> Ok[PortfolioHolding] | Err:
    """Validate one row. Holdings arrive as dicts from the dashboard and as
    models from anything typed; both are accepted, neither is trusted."""
    if isinstance(row, PortfolioHolding):
        return ok(row)
    if not isinstance(row, dict):
        return err(ContractViolation(
            field=f"holdings[{index}]",
            detail=f"expected a mapping or PortfolioHolding, "
                   f"got {type(row).__name__}"))
    try:
        return ok(PortfolioHolding.model_validate(row))
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ())) or "?"
        return err(ContractViolation(
            field=f"holdings[{index}].{loc}",
            detail=first.get("msg", "invalid holding")))


def normalise_flag_source(source: object) -> Ok[dict[str, MicroFlag]] | Err:
    """Fold any accepted micro-flag carrier into one `{sectorId: flag}` dict.

    Accepts `tuple[SectorFlag, ...]` (what C5's FR14 path actually emits), the
    `{"sectorId": …, "flag": …}` dicts the dashboard already passes around, and
    a plain mapping. `None` and `{}` are legitimate: they mean *no micro-flag
    coverage at all*, which is not the same statement as "nothing is flagged",
    and the difference is carried through to the caller rather than flattened.
    """
    if source is None:
        return ok({})
    items: list[tuple[str, object]] = []
    if isinstance(source, dict):
        items = [(str(k), v) for k, v in source.items()]
    elif isinstance(source, (list, tuple)):
        for i, f in enumerate(source):
            if isinstance(f, SectorFlag):
                items.append((f.sector_id, f.flag))
                continue
            if isinstance(f, dict):
                sid = f.get("sectorId", f.get("sector_id"))
                if isinstance(sid, str) and sid.strip():
                    items.append((sid.strip(), f.get("flag")))
                    continue
            return err(ContractViolation(
                field=f"sector_flags[{i}]",
                detail="expected a SectorFlag or a {sectorId, flag} mapping"))
    else:
        return err(ContractViolation(
            field="sector_flags",
            detail=f"expected a mapping or a sequence of SectorFlag, "
                   f"got {type(source).__name__}"))

    out: dict[str, MicroFlag] = {}
    for sector, flag in items:
        if flag not in MICRO_FLAGS:
            return err(ContractViolation(
                field=f"sector_flags[{sector!r}]",
                detail=f"flag must be one of {MICRO_FLAGS}, got {flag!r} "
                       f"(ARCHITECTURE §2 S10)"))
        if sector in out and out[sector] != flag:
            return err(ContractViolation(
                field=f"sector_flags[{sector!r}]",
                detail=f"conflicting micro-flags for one sector: "
                       f"{out[sector]!r} and {flag!r}"))
        out[sector] = flag       # type: ignore[assignment]
    return ok(out)


def portfolio_overlay(holdings: object, sector_flags: object = None) -> Ok[dict] | Err:
    """FR43 — size a holdings list against the sector micro-flags.

    Returns `exposedPct` (the share of portfolio value sitting in amber-flagged
    sectors), the per-sector breakdown S10 specifies, the per-holding breakdown
    that fills E11's `exposure_pct`, and the coverage accounting that says how
    much of the portfolio the flag source could speak to at all. Naming flagged
    sectors without sizing them is not decision support; sizing them without
    saying what was never checked is worse.

    Rows need `symbol` and `value`. `sector` defaults to `UNCLASSIFIED`.
    `quantity` is accepted and validated so a whole E11 row can be passed
    straight in, but it takes no part in the sizing and is not echoed back:
    exposure is value-based per FR43, and summing share counts across symbols
    would mean nothing.
    """
    try:
        rows = list(holdings) if holdings is not None else []
    except TypeError:
        return err(ContractViolation(
            field="holdings", detail="holdings must be an iterable of rows"))
    if not rows:
        return err(ContractViolation(
            field="holdings",
            detail="empty portfolio — FR43's holdings list is optional, but an "
                   "empty one has no value to apportion"))

    flags_res = normalise_flag_source(sector_flags)
    if flags_res.status == "error":
        return flags_res
    flags = flags_res.value

    # One row per symbol, matching E11's (user_id, symbol) key: several lots of
    # the same name are one position. The same symbol under two sectors is a
    # caller inconsistency, not something to silently pick a winner for.
    merged: dict[str, dict] = {}
    for i, row in enumerate(rows):
        parsed = _as_holding(row, i)
        if parsed.status == "error":
            return parsed
        h = parsed.value
        prev = merged.get(h.symbol)
        if prev is None:
            merged[h.symbol] = {"symbol": h.symbol, "sector": h.sector,
                                "value": h.value}
        elif prev["sector"] != h.sector:
            return err(ContractViolation(
                field=f"holdings[{i}].sector",
                detail=f"symbol {h.symbol!r} is assigned to two sectors: "
                       f"{prev['sector']!r} and {h.sector!r}"))
        else:
            prev["value"] += h.value

    total = math.fsum(p["value"] for p in merged.values())
    if total <= 0.0:
        return err(ContractViolation(
            field="holdings",
            detail="total portfolio value must be positive to report exposure "
                   "as a percentage of it"))

    by_sector: dict[str, float] = {}
    for p in merged.values():
        by_sector[p["sector"]] = by_sector.get(p["sector"], 0.0) + p["value"]

    # Largest exposure first; sectorId breaks ties so row order is a function
    # of the portfolio, not of the order the rows happened to arrive in.
    sector_rows = [
        {
            "sectorId": sector,
            "pct": 100.0 * value / total,
            "flag": flags.get(sector, "none"),
            "covered": sector in flags,
        }
        for sector, value in sorted(by_sector.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    holding_rows = [
        {
            "symbol": p["symbol"],
            "sectorId": p["sector"],
            "exposurePct": 100.0 * p["value"] / total,      # E11.exposure_pct
            "flag": flags.get(p["sector"], "none"),
            "covered": p["sector"] in flags,
        }
        for p in sorted(merged.values(), key=lambda p: (-p["value"], p["symbol"]))
    ]

    exposed = math.fsum(r["pct"] for r in sector_rows if r["flag"] == "amber")
    uncovered = math.fsum(r["pct"] for r in sector_rows if not r["covered"])

    warnings: tuple[SeraphWarning, ...] = ()
    if uncovered > 0.0:
        blind = sorted({r["sectorId"] for r in sector_rows if not r["covered"]})
        warnings = (SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=(f"{uncovered:.1f}% of portfolio value sits in sectors with "
                     f"no FR14 micro-flag available — that share is neither "
                     f"flagged nor cleared"),
            context={"uncoveredPct": round(uncovered, 6),
                     "sectors": ",".join(blind)},
        ),)

    return ok({
        "totalValue": total,
        "exposedPct": exposed,
        "coveredPct": 100.0 - uncovered,
        "uncoveredPct": uncovered,
        "bySector": sector_rows,
        "byHolding": holding_rows,
    }, warnings)


def measured_flag_source(
    flags: object,
    *,
    sector_baselines: "dict[str, float] | None" = None,
) -> Ok[dict[str, MicroFlag]] | Err:
    """FR43 seam 1 — keep only the sectors C5 could actually **measure**.

    `normalise_flag_source` above treats every entry it is handed as a
    statement of coverage, which is right for a caller-supplied mapping: if the
    dashboard says `{"steel": "none"}` it is asserting that steel was checked
    and is quiet. It is *wrong* for C5's own emission, and the reason is in
    FR14's arithmetic (`seraph/pillars/hawkes/engine.py`, `sector_flags`):

        base     = sector_baselines.get(sector, 0.0)
        ratio    = realised / base if base > 0 else 0.0
        flag     = "amber" if ratio >= amber_multiple else "none"

    When a sector has **no baseline** — `base <= 0`, i.e. nothing against which
    to judge its realised intensity — `ratio` falls through to `0.0` and the
    flag is emitted as **`"none"`**. That value is indistinguishable from a
    sector that was measured and found quiet, so pushing C5's tuple straight
    through `normalise_flag_source` marks an **unmeasurable** sector as
    `covered: true` and folds its share into `coveredPct`. The overlay would
    then report a sector as *cleared* that was never looked at — exactly the
    inversion this module exists to prevent.

    This adapter drops those entries instead. A dropped sector is simply absent
    from the returned mapping, so the existing machinery does the rest
    unchanged: `portfolio_overlay` reports `covered: false`, adds the share to
    `uncoveredPct`, and raises PARTIAL_COVERAGE. **`MICRO_FLAGS` is untouched**
    — coverage still rides alongside the flag rather than widening the S10
    union.

    **The discrimination rule, and its one genuine ambiguity.** `n` on a
    `SectorFlag` carries the intensity ratio, so:

    * `flag == "amber"` → `ratio >= amber_multiple > 0` → measured.
    * `n > 0` → `base > 0` and at least one event → measured, quiet.
    * `n == 0.0` → **ambiguous**: either `base <= 0` (unmeasurable) *or*
      `base > 0` with a zero event count (measured, and as quiet as it gets).

    The default resolves that ambiguity **conservatively, toward uncovered**.
    The two errors are not symmetric: calling an unmeasured sector clean
    overstates what the system knows, while calling a measured-quiet sector
    uncovered merely understates it. For a tool whose purpose is to avoid
    reading silence as safety, understating is the correct direction — and the
    PARTIAL_COVERAGE warning names the sector either way, so nothing is hidden.

    Pass `sector_baselines` to remove the ambiguity entirely: a sector is then
    measured iff its baseline is strictly positive, which is precisely C5's own
    condition. Callers holding the baselines should do this.

    Entries carrying no measurement evidence at all (a bare
    `{"sectorId": …, "flag": …}` dict, which has no `n`) are treated as
    **unmeasured**, because a default `"none"` with nothing behind it is the
    very case this adapter exists to catch. Callers that genuinely mean "I
    checked, it is quiet" should keep using `normalise_flag_source`.

    Returns the measured subset, with PARTIAL_COVERAGE listing what was
    dropped and why.
    """
    if flags is None:
        return ok({})
    if isinstance(flags, dict):
        return err(ContractViolation(
            field="sector_flags",
            detail="a plain mapping carries no measurement evidence, so it "
                   "cannot be screened for coverage; it is an explicit caller "
                   "assertion — use normalise_flag_source for that shape"))
    if not isinstance(flags, (list, tuple)):
        return err(ContractViolation(
            field="sector_flags",
            detail=f"expected a sequence of SectorFlag, got "
                   f"{type(flags).__name__}"))

    measured: dict[str, MicroFlag] = {}
    dropped: dict[str, str] = {}
    for i, f in enumerate(flags):
        if isinstance(f, SectorFlag):
            sector, flag, ratio = f.sector_id, f.flag, float(f.n)
        elif isinstance(f, dict):
            sid = f.get("sectorId", f.get("sector_id"))
            if not isinstance(sid, str) or not sid.strip():
                return err(ContractViolation(
                    field=f"sector_flags[{i}]",
                    detail="expected a SectorFlag or a {sectorId, flag} mapping"))
            sector, flag = sid.strip(), f.get("flag")
            n = f.get("n")
            ratio = float(n) if isinstance(n, (int, float)) else float("nan")
        else:
            return err(ContractViolation(
                field=f"sector_flags[{i}]",
                detail="expected a SectorFlag or a {sectorId, flag} mapping"))

        if flag not in MICRO_FLAGS:
            return err(ContractViolation(
                field=f"sector_flags[{sector!r}]",
                detail=f"flag must be one of {MICRO_FLAGS}, got {flag!r} "
                       f"(ARCHITECTURE §2 S10)"))

        if sector_baselines is not None:
            base = float(sector_baselines.get(sector, 0.0))
            is_measured = math.isfinite(base) and base > 0.0
            why = f"baseline {base!r} is not positive"
        elif flag == "amber":
            is_measured, why = True, ""
        elif math.isfinite(ratio) and ratio > 0.0:
            is_measured, why = True, ""
        else:
            is_measured = False
            why = ("no intensity ratio supplied" if not math.isfinite(ratio)
                   else "intensity ratio is 0.0, so the sector either had no "
                        "baseline to measure against or no events; without "
                        "baselines the two are indistinguishable")

        if not is_measured:
            dropped[sector] = why
            continue
        prev = measured.get(sector)
        if prev is not None and prev != flag:
            return err(ContractViolation(
                field=f"sector_flags[{sector!r}]",
                detail=f"conflicting micro-flags for one sector: "
                       f"{prev!r} and {flag!r}"))
        measured[sector] = flag       # type: ignore[assignment]

    warnings: tuple[SeraphWarning, ...] = ()
    if dropped:
        warnings = (SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=(f"{len(dropped)} sector(s) emitted a micro-flag that was "
                     f"not measured and are reported as uncovered, not clean: "
                     f"{', '.join(sorted(dropped))}"),
            context={"sectors": ",".join(sorted(dropped)),
                     "reason": "; ".join(f"{s}: {r}" for s, r in
                                         sorted(dropped.items()))},
        ),)
    return ok(measured, warnings)
