# C11 — Decision Support (FR43): the E11 read path for the portfolio overlay.
"""FR43 seam 2 — load holdings through a typed, `user_id`-scoped reader.

`portfolio.py` is a pure function over caller-supplied holdings, which is what
keeps its arithmetic testable in isolation. This module is the one place that
touches a database, so that property survives: nothing here computes exposure,
it only fetches rows and hands them to `portfolio_overlay`.

**Why the read lives in C11 and not in `StoreReader`.** AGENTS.md §6 forbids a
component reaching into another's tables — but ARCHITECTURE §1 assigns **E11
`user_portfolio` to C11**, which is also why `PortfolioHolding` is defined in
`portfolio.py` rather than in `shared_types`. C11 reading its own entity is the
rule, not an exception to it. `seraph/store/reader.py` is C1's and is not
touched.

## `exposure_pct` is derived, never read

E11 declares `exposure_pct double precision NOT NULL`, and the column is
**deliberately absent from the SELECT**. That is a stronger guarantee than
ignoring it in Python: the value cannot leak into the overlay even by mistake,
because it is never fetched. Exposure is a share *of the portfolio currently
held*, so a stored figure is stale the moment any other row changes — it is an
output of FR43's arithmetic, not an input to it. `portfolio_overlay` recomputes
`exposurePct` per holding from `value / Σ value`.

## What `at` can and cannot mean here

ARCHITECTURE §2 S10 types the call as `portfolioOverlay(userId, at)`, but **E11
has no time dimension**: its primary key is `(user_id, symbol)` and it carries
no timestamp, so there is no history to query and a point-in-time
reconstruction is impossible. `at` is therefore accepted and echoed as the
**evaluation** timestamp — which is what it legitimately is for the flag and
CSRS side of the call — while the holdings are labelled
`holdingsAsOf: "current"`. A caller that needs a historical portfolio is asking
for something the schema cannot answer, and the payload says so rather than
returning a number under a timestamp it does not honour. Adding history to E11
is a C1 schema change and is not made here.

## No measured flag data exists yet

`hawkes_output` has no production writer in this worktree, so no measured FR14
micro-flag has ever reached the overlay. Given no flag source the honest answer
for a real portfolio is **100% uncovered**, which this path returns and which is
the correct answer rather than a defect. Nothing here should be read as
production coverage.
"""
from __future__ import annotations

from typing import Any

from seraph.decision_support.portfolio import (
    PortfolioHolding,
    measured_flag_source,
    normalise_flag_source,
    portfolio_overlay,
)
from seraph.shared_types import ContractViolation, Err, Ok, SeraphWarning, err, ok

#: E11's columns as C11 consumes them. `exposure_pct` is **not** here, on
#: purpose — see the module docstring. `user_id` is the lookup key, not a field.
_HOLDING_COLUMNS = ("symbol", "quantity", "value", "sector")

_SELECT_HOLDINGS = (
    "SELECT symbol, quantity, value, sector "
    "FROM user_portfolio WHERE user_id = $1 ORDER BY symbol"
)


async def read_user_portfolio(conn: Any, user_id: str) -> Ok[tuple] | Err:
    """Load one user's E11 holdings, scoped to `user_id` and typed on the way in.

    `conn` may be an `asyncpg` connection or pool; both expose `fetch`. Rows are
    validated through `PortfolioHolding`, so a malformed row is a
    `CONTRACT_VIOLATION` naming the offending column rather than a bad number
    that reaches the arithmetic.

    **A user with no holdings is a successful read**, returning an empty tuple.
    It is not this function's place to decide that an empty portfolio is an
    error — `portfolio_overlay` already rejects it with the ContractViolation
    FR43 specifies, and duplicating that judgement here would give the same
    condition two different error shapes depending on the entry point.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        return err(ContractViolation(
            field="user_id",
            detail="user_id must be a non-empty identifier; an unscoped read "
                   "would return another user's holdings"))
    fetch = getattr(conn, "fetch", None)
    if fetch is None:
        return err(ContractViolation(
            field="conn",
            detail=f"expected an asyncpg connection or pool exposing fetch(), "
                   f"got {type(conn).__name__}"))

    rows = await fetch(_SELECT_HOLDINGS, user_id.strip())
    out: list[PortfolioHolding] = []
    for i, r in enumerate(rows):
        try:
            out.append(PortfolioHolding.model_validate(
                {k: r[k] for k in _HOLDING_COLUMNS}))
        except Exception as exc:                  # pydantic ValidationError et al.
            return err(ContractViolation(
                field=f"user_portfolio[{i}]",
                detail=f"row for symbol {r['symbol']!r} failed validation: {exc}"))
    return ok(tuple(out))


async def portfolio_overlay_for_user(
    conn: Any,
    user_id: str,
    at: str | None = None,
    *,
    sector_flags: object = None,
    sector_baselines: "dict[str, float] | None" = None,
    screen_measurement: bool = True,
) -> Ok[dict] | Err:
    """ARCHITECTURE S10 `portfolioOverlay(userId, at)` over the real E11 table.

    Loads the user's holdings, screens the flag source for sectors C5 could
    actually measure, and defers every percentage to `portfolio_overlay`.

    `screen_measurement` controls which flag adapter is used, and the default
    is the safe one:

    * `True` (default) — `measured_flag_source`: a `SectorFlag` emitted with no
      baseline behind it carries `flag="none"` purely as a fall-through
      (FR14's `ratio = 0.0 if base <= 0`), so it is treated as **uncovered**,
      not clean.
    * `False` — `normalise_flag_source`: every entry is taken as an explicit
      assertion of coverage. Correct only for a caller-supplied mapping that
      genuinely means "I checked this sector".

    Warnings from the flag screen and from the overlay are both returned, so a
    sector dropped for want of a baseline and a sector absent from the source
    entirely each surface their own PARTIAL_COVERAGE.
    """
    read = await read_user_portfolio(conn, user_id)
    if read.status == "error":
        return read
    holdings = read.value

    warnings: tuple[SeraphWarning, ...] = ()
    flags: object = sector_flags
    if sector_flags is not None:
        adapt = measured_flag_source if screen_measurement else normalise_flag_source
        adapted = (adapt(sector_flags, sector_baselines=sector_baselines)
                   if screen_measurement else adapt(sector_flags))
        if adapted.status == "error":
            return adapted
        flags = adapted.value
        warnings += tuple(adapted.warnings or ())

    # Empty holdings fall through to portfolio_overlay, which raises FR43's
    # existing empty-portfolio ContractViolation. Preserved deliberately.
    res = portfolio_overlay(holdings, flags)
    if res.status == "error":
        return res

    payload = dict(res.value)
    payload["userId"] = user_id.strip()
    payload["holdingsCount"] = len(holdings)
    # E11 has no time dimension, so this is the evaluation time, not a
    # point-in-time reconstruction of the portfolio. See the module docstring.
    payload["evaluatedAt"] = at
    payload["holdingsAsOf"] = "current"
    return ok(payload, warnings + tuple(res.warnings or ()))
