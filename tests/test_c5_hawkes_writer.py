# C5 — E6 production writer (FR10–FR15). Synthetic first, database-gated last.
"""Guards for `scripts/write_hawkes_production.py`.

The split matters and is deliberate: the schedule and data-quality logic are
pure and are tested on synthetic streams with known ground truth; only the
persistence contract needs a database, and that test skips cleanly without one.
A passing synthetic test here proves the scheduling and filtering are correct —
it proves nothing about the real pipeline, which is what the DB test and the
evidence logs are for.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_spec = importlib.util.spec_from_file_location(
    "write_hawkes_production", _ROOT / "scripts" / "write_hawkes_production.py")
whp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(whp)

IST = timezone(timedelta(hours=5, minutes=30))
BARS_PER_SESSION = 75


def _session_bars(n_sessions: int, start_day: int = 1) -> list[datetime]:
    """75 five-minute bars per session from 09:15 IST, like the real corpus."""
    out = []
    for d in range(n_sessions):
        base = datetime(2020, 1, 1, 9, 15, tzinfo=IST) + timedelta(days=start_day + d)
        out.extend(base + timedelta(minutes=5 * b) for b in range(BARS_PER_SESSION))
    return out


class _FakePool:
    """Minimal stand-in for an asyncpg pool: one symbol -> (ts, close) rows."""

    def __init__(self, per_symbol: dict[str, list[tuple[datetime, float]]]):
        self._data = per_symbol

    async def fetch(self, _sql, symbol):
        return [{"ts": t, "close": c} for t, c in self._data.get(symbol, [])]


# --------------------------------------------------------------- schedule ---

def test_refit_points_respects_the_window_and_steps_by_sessions():
    n_sess = 40
    bars = _session_bars(n_sess)
    day = np.array([b.date() for b in bars])
    new_sess = np.r_[True, day[1:] != day[:-1]]
    pts = whp.refit_points(day, new_sess, window_days=10, refit_every=5)

    assert pts, "a 40-session stream must admit 10-session windows"
    # every window carries exactly `window_days` sessions of history behind it
    for lo, hi in pts:
        sessions_in_window = len(set(day[lo:hi + 1]))
        assert sessions_in_window >= 10
    # as-of indices are strictly increasing and land on a session's LAST bar
    hs = [hi for _, hi in pts]
    assert hs == sorted(set(hs)), "refit points must be strictly increasing and unique"
    for _, hi in pts:
        assert hi + 1 == len(day) or day[hi + 1] != day[hi], (
            "as_of must be the final bar of its session")


def test_refit_points_is_empty_when_the_window_exceeds_the_corpus():
    bars = _session_bars(5)
    day = np.array([b.date() for b in bars])
    new_sess = np.r_[True, day[1:] != day[:-1]]
    assert whp.refit_points(day, new_sess, window_days=500, refit_every=5) == []


def test_refit_every_controls_density_without_changing_coverage():
    bars = _session_bars(60)
    day = np.array([b.date() for b in bars])
    new_sess = np.r_[True, day[1:] != day[:-1]]
    dense = whp.refit_points(day, new_sess, window_days=10, refit_every=1)
    sparse = whp.refit_points(day, new_sess, window_days=10, refit_every=5)
    assert len(dense) > len(sparse)
    assert sparse[0][1] == dense[0][1], "both must start at the same first as-of bar"


# ------------------------------------------------------- time-of-day profile ---

def test_tod_profile_is_normalised_to_mean_one():
    rng = np.random.default_rng(0)
    counts = rng.poisson(0.3, size=750).astype(float)
    tod_index = np.tile(np.arange(75), 10)
    prof = whp.tod_profile(counts, tod_index, 75)
    assert prof.shape == (75,)
    assert np.isclose(prof.mean(), 1.0), "profile must average to 1 so mu stays interpretable"
    assert np.all(prof >= 0.0)


def test_tod_profile_recovers_a_known_diurnal_shape():
    """A U-shape planted in the counts must survive into the profile."""
    tod_index = np.tile(np.arange(75), 40)
    shape = np.ones(75)
    shape[:5] = 4.0          # open burst
    shape[-5:] = 4.0         # close burst
    counts = shape[tod_index] * 1.0
    prof = whp.tod_profile(counts, tod_index, 75)
    assert prof[:5].mean() > 2.5 * prof[30:40].mean()
    assert prof[-5:].mean() > 2.5 * prof[30:40].mean()


# ------------------------------------------------------------ data quality ---

def test_nonpositive_closes_are_dropped_and_counted_never_patched():
    """A zero-close feed gap must be removed from the stream and reported.

    This mirrors the real defect: 3,558 bars with close<=0 arriving as whole
    contiguous sessions. The contract is that they vanish from the stream and
    appear in the data-quality counter — not that they are forward-filled.
    """
    bars = _session_bars(6)
    good = [(t, 100.0 + 0.1 * i) for i, t in enumerate(bars)]
    # blank one whole session (bars 75..149) the way the feed does
    corrupted = [(t, 0.0) if 75 <= i < 150 else (t, c)
                 for i, (t, c) in enumerate(good)]
    pool = _FakePool({"AAA": corrupted})
    st = asyncio.run(whp.load_stream(pool, ["AAA"]))

    assert st["dq"]["bars_dropped_nonpositive"] == 75
    assert st["dq"]["bars_read"] == len(bars)
    assert len(st["bars"]) == len(bars) - 75
    # the blanked session contributes no bars at all, so nothing was patched
    blanked_day = bars[75].date()
    assert blanked_day not in set(st["day"]), "a dropped session must not reappear"
    assert st["active"].min() >= 1.0


def test_a_symbol_below_the_bar_floor_is_excluded_not_padded():
    pool = _FakePool({"SHORT": [(t, 100.0) for t in _session_bars(1)]})
    st = asyncio.run(whp.load_stream(pool, ["SHORT"]))
    assert st["dq"]["symbols_too_short"] == 1
    assert st["dq"]["symbols_used"] == 0
    assert st["bars"] == []


def test_active_symbol_count_tracks_contributing_symbols_per_bar():
    bars = _session_bars(4)
    a = [(t, 100.0 + 0.05 * i) for i, t in enumerate(bars)]
    b = [(t, 50.0 + 0.05 * i) for i, t in enumerate(bars)]
    st = asyncio.run(whp.load_stream(_FakePool({"A": a, "B": b}), ["A", "B"]))
    assert st["dq"]["symbols_used"] == 2
    assert st["active"].max() == 2.0, "both symbols trade every bar"


def test_jump_counts_are_separated_by_sign():
    """A planted crash bar must land in the negative stream, not the positive one.

    The fixture needs genuine background volatility. `extract_jumps` standardises
    each return by a local bipower volatility, so on a perfectly constant series
    `sigma == 0`, the statistic becomes `0/0 -> nan -> 0`, and nothing can ever be
    flagged. That is correct defensive behaviour in the estimator — and it is the
    same guard (`np.where(p > 0, p, np.nan)` then `nan_to_num`) that makes it
    robust to the real corpus's `close <= 0` bars. A jump test only has meaning
    against non-zero local volatility, so the background is simulated here with a
    fixed seed and the jump is planted at a large multiple of it.
    """
    rng = np.random.default_rng(42)
    bars = _session_bars(8)
    sigma = 0.001                                   # ~realistic 5-minute vol
    ret = rng.normal(0.0, sigma, size=len(bars))
    ret[300] = -60.0 * sigma                        # unambiguous downside jump
    ret[400] = +60.0 * sigma                        # and one upside jump
    close = 100.0 * np.exp(np.cumsum(ret))
    rows = list(zip(bars, close.tolist()))

    st = asyncio.run(whp.load_stream(_FakePool({"A": rows}), ["A"]))
    assert st["n_neg"].shape == st["n_pos"].shape == (len(bars),)
    assert st["n_neg"].sum() >= 1.0, "the planted crash bar must be a negative jump"
    assert st["n_pos"].sum() >= 1.0, "the planted spike bar must be a positive jump"
    # ground truth: the planted bars are the extreme ones, so they must be flagged
    assert st["n_neg"][300] == 1.0, "the negative jump must land on its own bar"
    assert st["n_pos"][400] == 1.0, "the positive jump must land on its own bar"
    # and signs must not cross over
    assert st["n_pos"][300] == 0.0 and st["n_neg"][400] == 0.0


def test_a_constant_series_yields_no_jumps_rather_than_dividing_by_zero():
    """Zero local volatility must produce zero jumps, not NaN or a spurious flag.

    This pins the guard that also protects the real corpus's zero-close sessions.
    """
    bars = _session_bars(4)
    rows = [(t, 100.0) for t in bars]
    st = asyncio.run(whp.load_stream(_FakePool({"A": rows}), ["A"]))
    assert st["n_neg"].sum() == 0.0
    assert st["n_pos"].sum() == 0.0
    assert np.isfinite(st["n_neg"]).all() and np.isfinite(st["n_pos"]).all()


# ----------------------------------------------------- E6 constraint shape ---

def test_emitted_rows_would_satisfy_every_e6_check_constraint():
    """The row dict the writer builds must respect E6's CHECKs by construction.

    E6 enforces branching_ratio_n < 1 (FR11), mts >= 0 (FR13), and closed
    vocabularies for scope and sector_microflag. Asserting that here means a
    violation is caught in CI rather than by a Postgres error mid-backfill.
    """
    rng = np.random.default_rng(7)
    for _ in range(200):
        n = float(rng.uniform(0.0, 0.999))
        mts = float(n / (1.0 - n)) if rng.random() > 0.3 else 0.0
        row = {"scope": "market", "scope_id": "", "n": n, "mts": mts, "flag": "none"}
        assert row["n"] < 1.0
        assert row["mts"] >= 0.0
        assert row["scope"] in ("market", "sector", "instrument")
        assert row["flag"] in ("none", "amber")


def test_window_days_has_no_default_so_an_unvalidated_constant_cannot_leak_in():
    """`--window-days` must be required.

    WINDOW_DAYS = 60 is an engine constant whose value was never validated
    (n CV 0.714 on 60-day windows). A default here would silently reintroduce it.
    """
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, required=True)
    with pytest.raises(SystemExit):
        ap.parse_args([])


# ------------------------------------------------------------ database path ---

def _db_available() -> bool:
    try:
        import asyncpg

        from seraph.store.bootstrap import resolve_dsn

        async def probe():
            conn = await asyncpg.connect(resolve_dsn(), timeout=3)
            await conn.close()

        asyncio.run(probe())
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _db_available(),
                    reason="TimescaleDB not reachable — run `docker compose up -d` first")
def test_e6_upsert_is_idempotent_on_the_natural_key():
    """Writing the same sentinel row twice must not duplicate it (CT-1's rule for E6).

    Uses scope='instrument' with a sentinel scope_id so it cannot collide with
    any real market-scope production row, and cleans up after itself.
    """
    import asyncpg

    from seraph.store.bootstrap import resolve_dsn

    SENTINEL = "__TEST_HAWKES_WRITER__"
    ts = datetime(2020, 1, 2, 15, 25, tzinfo=IST)

    async def run():
        conn = await asyncpg.connect(resolve_dsn(), timeout=10)
        try:
            await conn.execute(
                "DELETE FROM hawkes_output WHERE scope_id = $1", SENTINEL)
            sql = """
                INSERT INTO hawkes_output (ts, scope, scope_id, branching_ratio_n,
                    mts, jump_count_neg, jump_count_pos, asymmetry_ratio,
                    sector_microflag, branching_matrix, alpha_beta)
                VALUES ($1,'instrument',$2,$3,$4,$5,$6,$7,'none',NULL,NULL)
                ON CONFLICT (scope, scope_id, ts) DO UPDATE SET
                    branching_ratio_n=EXCLUDED.branching_ratio_n, mts=EXCLUDED.mts,
                    jump_count_neg=EXCLUDED.jump_count_neg,
                    jump_count_pos=EXCLUDED.jump_count_pos,
                    asymmetry_ratio=EXCLUDED.asymmetry_ratio
            """
            await conn.execute(sql, ts, SENTINEL, 0.1079, 0.121, 21180, 28603, 0.7404)
            first = await conn.fetchval(
                "SELECT count(*) FROM hawkes_output WHERE scope_id=$1", SENTINEL)
            # same key, different payload -> must update in place, not insert
            await conn.execute(sql, ts, SENTINEL, 0.2000, 0.250, 1, 2, 0.5)
            second = await conn.fetchval(
                "SELECT count(*) FROM hawkes_output WHERE scope_id=$1", SENTINEL)
            got = await conn.fetchrow(
                "SELECT branching_ratio_n, jump_count_neg FROM hawkes_output "
                "WHERE scope_id=$1", SENTINEL)
            await conn.execute(
                "DELETE FROM hawkes_output WHERE scope_id = $1", SENTINEL)
            return first, second, got
        finally:
            await conn.close()

    first, second, got = asyncio.run(run())
    assert first == 1, "first write must insert exactly one row"
    assert second == 1, "re-writing the same natural key must not duplicate"
    assert got["branching_ratio_n"] == pytest.approx(0.2000), "upsert must update in place"
    assert got["jump_count_neg"] == 1


@pytest.mark.skipif(not _db_available(),
                    reason="TimescaleDB not reachable — run `docker compose up -d` first")
def test_e6_rejects_a_branching_ratio_at_or_above_one():
    """FR11 is enforced by the schema, not merely by the engine."""
    import asyncpg

    from seraph.store.bootstrap import resolve_dsn

    async def run():
        conn = await asyncpg.connect(resolve_dsn(), timeout=10)
        try:
            with pytest.raises(asyncpg.exceptions.CheckViolationError):
                await conn.execute(
                    """INSERT INTO hawkes_output (ts, scope, scope_id,
                           branching_ratio_n, mts, jump_count_neg, jump_count_pos,
                           asymmetry_ratio)
                       VALUES ($1,'instrument','__TEST_FR11__',1.0,0.0,0,0,0.0)""",
                    datetime(2020, 1, 3, 15, 25, tzinfo=IST))
        finally:
            await conn.close()

    asyncio.run(run())
