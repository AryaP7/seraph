# CT-3 — C4 ⇄ C5: jump-event sufficiency (ARCHITECTURE §5 ①, risk R2)
"""**Run this first.** It is the cheapest possible test of R2, the project's
highest-probability technical failure: Lee–Mykland on 5-minute bars may not
yield enough negative jumps per rolling one-day window to identify a Hawkes
kernel across 25 `S_t` states. No estimation happens here — it is pure counting,
so it can run the moment intraday bars exist and long before C5 is written.

If this fails, the pre-agreed mitigation ladder (ROADMAP Phase 5) applies in
order: drop to 1-minute bars, coarsen `S_t` to 9 states, pool across symbols
within a sector, lengthen the estimation window past one day.

**On the floor.** ARCHITECTURE says "≥ agreed floor" without fixing a number.
`MIN_NEG_JUMPS_PER_DAY` is set to 1.0 as a *structural* floor — below one
negative jump per symbol-day the per-day event stream is empty more often than
not and a one-day-window MLE cannot be posed at all. This is a necessary
condition, not a sufficient one for good identification; the diagnostic
printout is the number that actually informs the C5 design.
"""
from __future__ import annotations

import asyncio

import numpy as np
import pytest

asyncpg = pytest.importorskip("asyncpg")

from seraph.features import extract_jumps, state_variable, tick_test
from seraph.store.bootstrap import resolve_dsn

MIN_NEG_JUMPS_PER_DAY = 1.0
MIN_STATES_POPULATED = 2
BARS_PER_DAY = 75          # NSE: 09:15-15:30 at 5-minute resolution


def _fetch_symbol_month():
    """One real symbol-month of 5-minute bars, for the best-covered symbol."""
    async def go():
        pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2, timeout=5)
        try:
            sym = await pool.fetchval(
                "SELECT symbol FROM intraday_bars GROUP BY symbol "
                "ORDER BY count(*) DESC LIMIT 1")
            if sym is None:
                return None, None
            rows = await pool.fetch(
                """
                SELECT ts, close, volume FROM intraday_bars
                WHERE symbol = $1
                  AND ts > (SELECT max(ts) FROM intraday_bars WHERE symbol = $1)
                           - INTERVAL '45 days'
                ORDER BY ts
                """, sym)
            return sym, rows
        finally:
            await pool.close()

    try:
        return asyncio.run(go())
    except Exception:
        return None, None


_SYMBOL, _ROWS = _fetch_symbol_month()

pytestmark = pytest.mark.skipif(
    not _ROWS or len(_ROWS) < 5 * BARS_PER_DAY,
    reason="not enough intraday bars yet — run scripts/backfill_intraday.py",
)


def _jump_frame():
    close = np.array([float(r["close"]) for r in _ROWS])
    volume = np.array([float(r["volume"]) for r in _ROWS])
    out = extract_jumps(close)
    signed = tick_test(close, volume)
    # Rolling imbalance and a simple dispersion proxy, purely to populate S_t
    # for this counting exercise; production S_t uses C4's spread estimators.
    window = 20
    imbalance = np.convolve(signed, np.ones(window), mode="same") / window
    spread = np.abs(out["log_return"])
    st = state_variable(spread, imbalance)
    days = len(_ROWS) / BARS_PER_DAY
    return out, st, days


def test_ct3_negative_jump_density_supports_a_one_day_window():
    out, st, days = _jump_frame()
    neg = int((out["jump_sign"] == -1).sum())
    pos = int((out["jump_sign"] == 1).sum())
    per_day = neg / days
    print(
        f"\n[CT-3] symbol={_SYMBOL}  bars={len(_ROWS)}  ~{days:.1f} trading days"
        f"\n[CT-3] negative jumps={neg} ({per_day:.2f}/day)  positive jumps={pos}"
        f"\n[CT-3] asymmetry neg/pos={neg / max(pos, 1):.2f}"
    )
    assert per_day >= MIN_NEG_JUMPS_PER_DAY, (
        f"only {per_day:.2f} negative jumps per symbol-day — below the "
        f"structural floor of {MIN_NEG_JUMPS_PER_DAY}. Apply the R2 mitigation "
        f"ladder: 1-minute bars, then coarsen S_t, then pool by sector."
    )


def test_ct3_events_populate_at_least_two_states():
    out, st, _ = _jump_frame()
    mask = out["is_jump"] & (out["jump_sign"] == -1)
    states = st["s_t"][mask]
    counts = {int(s): int((states == s).sum()) for s in np.unique(states)}
    print(f"\n[CT-3] negative jumps per S_t state: {counts}")
    assert len(counts) >= MIN_STATES_POPULATED, (
        f"negative jumps land in only {len(counts)} S_t state(s); a "
        f"state-dependent kernel needs at least {MIN_STATES_POPULATED}"
    )


def test_ct3_state_and_sign_invariants_hold_on_real_data():
    out, st, _ = _jump_frame()
    assert st["s_t"].min() >= 1 and st["s_t"].max() <= 25, "S_t must lie in 1..25"
    # jump_sign != 0 iff is_jump — the E1 invariant, on real data
    assert np.array_equal(out["is_jump"], out["jump_sign"] != 0)


def test_ct3_negative_a_flat_series_yields_no_jumps_not_an_error():
    """A zero-jump stretch is an empty result, never an exception."""
    flat = np.full(500, 100.0)
    out = extract_jumps(flat)
    assert int(out["is_jump"].sum()) == 0
    assert np.array_equal(out["jump_sign"], np.zeros(500, dtype=np.int8))
