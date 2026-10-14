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

---

**STATUS: R2 IS REALISED. THE FIRST TEST BELOW FAILS, AND THE FAILURE IS THE
PROJECT'S ANSWER — NOT A DEFECT AWAITING REPAIR.**

Workstream D triage, 2026-10-13. Evidence:
`docs/evidence/20261013T124930Z-51-ct3-jump-density-and-lm-calibration.log`;
reasoning in `docs/evidence/BLOCKER-TRIAGE.md` §D-1. Measured read-only over the
whole Hawkes universe (95 symbols, 18,269,762 bars, 244,772 symbol-days):

    negative jump events                21,180
    density                             0.0865 per symbol-day   (floor: 1.0)
    shortfall                           11.6x
    best single symbol (WEBELSOLAR)     0.3512 per symbol-day   — still 2.8x short

So the floor is missed by an order of magnitude **on every symbol in the
universe**, not marginally and not on an unlucky one. This reproduces
AMENDMENT-03 §1's 21,180 events / 0.0869 density independently.

**Why the number is not achievable.** AMENDMENT-03 §1 swept the full
Lee–Mykland grid (`K ∈ {156, 78, 40}` × `α ∈ {0.01, 0.05, 0.10}`) and density
moves only between 0.079 and 0.147 — a 1.9× span against a ~12× shortfall.
Every rung of the ROADMAP Phase-5 mitigation ladder was tried: 1-minute bars do
not exist in the corpus; coarsening `S_t` does not help because `S_t` was never
the binding constraint (all 25 states carry events, 20 of them ≥100); pooling
across symbols was adopted and goes *further* than the ladder. Reaching 1.0
per symbol-day needs ~12× more events, which at fixed `K` and `α` means either
sub-5-minute data (SPEC §7 item 12: unobtainable at budget) or an `α` so loose
the jump test stops being a jump test.

**And the requirement this floor guarded no longer exists.** SPEC v3.1 line 199:

> **FR10 `[v4]` AMENDED** | The system shall estimate a **discrete-time Hawkes
> process at the native 5-minute bar resolution** on the market-wide pooled
> stream of negative jump events … *Supersedes per-symbol one-trading-day
> continuous-time estimation, which AMENDMENT-03 §1–2 shows is unidentifiable
> with this data: density is 0.087 events/symbol-day, 75.8% of pooled events
> share a bar, and `β` pins to whatever bound is imposed.*

The spec quotes **this test's own failing measurement** as its reason for
retiring the per-symbol one-day window. The assertion is therefore a live record
of a resolved finding, and the pooled design FR10 `[v4]` actually specifies is
well identified on the same data (`α ≈ 0.055`, `φ ≈ 0.50` interior, `n ≈ 0.11`
stable at ~5% CV across folds — AMENDMENT-03 §5d).

**Deliberately left failing.** Workstream D did not weaken the assertion, lower
`MIN_NEG_JUMPS_PER_DAY`, or mark it `xfail`: ARCHITECTURE §5 ① still states the
floor and ROADMAP §4 records no agreed number, so retiring the gate is the C4/C5
owner's call, not a triage decision (AGENTS.md §9). See BLOCKER-TRIAGE.md §D-1
for the approval question.

**Separate finding, NOT the cause of this failure.** The Lee–Mykland rejection
threshold is mis-scaled by `1/c = 1.2533` (`tests/test_c4_lee_mykland_calibration.py`
has the derivation and the xfail pin). Correcting it raises density
0.0865 → 0.1478 per symbol-day — still **6.8× below the floor**, and the best
single symbol only reaches 0.5563. The conclusion above is robust to that
defect, which is why the two are triaged apart.
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
    """EXPECTED TO FAIL — R2 is realised; see the module docstring.

    Corpus-wide density is 0.0865 negative jumps per symbol-day against this
    1.0 floor, and SPEC FR10 `[v4]` cites that very number when superseding the
    per-symbol one-trading-day window this floor was the precondition for. The
    assertion is kept unmodified and failing so the finding stays visible;
    whether to retire the gate is the C4/C5 owner's decision
    (`docs/evidence/BLOCKER-TRIAGE.md` §D-1).

    The single-symbol number printed below is noisy (3 events on ~33 days); the
    authoritative figure is the full-universe measurement in
    `docs/evidence/20261013T124930Z-51-ct3-jump-density-and-lm-calibration.log`.
    """
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
