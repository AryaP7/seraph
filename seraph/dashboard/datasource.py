# C12 — Dashboard (FR39-FR42): the fetch layer.
"""Reads whatever the pipeline has actually produced. Never computes, never
simulates: if a value is missing the dashboard shows a gap, because a plausible
placeholder on a risk instrument is worse than an empty panel.

**Route status (FIX10).** The canonical entry point is
`seraph/dashboard/prototype_app.py`, which reads one complete run from
`RunStore`. This module serves the **legacy Streamlit-native panel route**
(`app.main()`), kept for compatibility. It is still a supported route, so it
obeys the same rule as the canonical one:

    every supported view consumes ONE coherent run/as-of bundle.

It used to take three independent `ORDER BY ... LIMIT 1` rows — the newest
CSRS, the newest Hamilton row and the newest RMT row — which silently mixed
dates whenever one component lagged. It now resolves a single `as_of` date from
the CSRS row and fetches the pillar rows **as of that same date**. A component
with no row at or before `as_of` is reported `unavailable`, never borrowed from
another date.

**Caching (FIX10).** The previous docstring claimed `st.cache_data` was applied
here; it was not. `cached_bundle()` now really applies it, keyed by the scope
tuple so entries cannot leak across contexts. Identity and organisation are not
yet part of that scope because there is no identity layer; `AUTH02` extends
`CacheScope` and nothing else has to change.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import date, datetime

import asyncpg

from seraph.store.bootstrap import resolve_dsn

#: Seconds a cached bundle stays warm. Short, because this is a risk surface.
CACHE_TTL_SECONDS = 60


@dataclass(frozen=True)
class CacheScope:
    """Everything a cached dashboard read must be keyed by.

    `user_id` and `org_id` are placeholders until `AUTH01`/`AUTH02` land. They
    are part of the key now so that adding identity cannot accidentally serve
    one tenant a cached payload built for another.
    """

    source: str                      # which store this came from
    as_of: str | None = None         # None means "latest available"
    user_id: str | None = None       # AUTH01
    org_id: str | None = None        # AUTH02

    def key(self) -> tuple:
        return (self.source, self.as_of, self.user_id, self.org_id)


def _as_of_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


async def _fetch(as_of: str | None = None) -> dict | None:
    """One coherent bundle: resolve an as-of date, then read every component
    at that date. Never mixes rows from different dates."""
    try:
        pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2, timeout=5)
    except Exception:
        return None
    try:
        if as_of is None:
            csrs = await pool.fetchrow("SELECT * FROM csrs ORDER BY ts DESC LIMIT 1")
        else:
            csrs = await pool.fetchrow(
                "SELECT * FROM csrs WHERE ts::date <= $1::date ORDER BY ts DESC LIMIT 1",
                as_of)
        if csrs is None:
            return None
        resolved = _as_of_date(csrs["ts"])
        ham = await pool.fetchrow(
            "SELECT * FROM hamilton_output WHERE date <= $1 ORDER BY date DESC LIMIT 1",
            resolved)
        rmt = await pool.fetchrow(
            "SELECT * FROM rmt_output WHERE date <= $1 ORDER BY date DESC LIMIT 1",
            resolved)
        return {"csrs": csrs, "hamilton": ham, "rmt": rmt, "as_of": resolved.isoformat()}
    except Exception:
        return None
    finally:
        await pool.close()


def assemble(raw: dict | None) -> dict | None:
    """Turn one coherent raw bundle into the view-layer state.

    A pillar row older than the bundle's `as_of` is reported as stale with its
    own date rather than presented as the current reading.
    """
    if not raw or raw.get("csrs") is None:
        return None

    from seraph.shared_types import CsrsPoint, ist_timestamp

    row = raw["csrs"]
    as_of = raw.get("as_of")
    point = CsrsPoint(
        ts=ist_timestamp(row["ts"]),
        csrs=row["csrs"], variance=row["var_csrs"],
        ci_lower=row["ci_lower"], ci_upper=row["ci_upper"],
        shapley=tuple(row["shapley"]),
        alert_level=row["alert_level"],
        mask=tuple(row["mask"]),
        effective_weights=tuple(tuple(r) for r in row["effective_weights"]),
        xi_mode=row["xi_mode"],
        weights_artefact_id=row["weights_artefact_id"],
        reconciliation_mode=row["reconciliation_mode"],
    )
    ham, rmt = raw.get("hamilton"), raw.get("rmt")
    out: dict = {"point": point, "pillar_scores": {}, "spectral": {},
                 "as_of": as_of, "component_as_of": {}, "coherent": True}
    if ham is not None:
        out["xi"] = (ham["xi_1"], ham["xi_2"], ham["xi_3"])
        out["pillar_scores"]["hamilton"] = ham["lsd_t"]
        out["component_as_of"]["hamilton"] = _stamp(ham["date"], as_of, out)
    else:
        out["component_as_of"]["hamilton"] = "unavailable"
    if rmt is not None:
        # Pillar 2's state is lambda_1/N, not SCA_t (AMENDMENT-04 §6). SCA_t
        # remains the FR18 aggregate and is still persisted, but it is a
        # different object: measured lag-1 autocorrelation 0.425 against
        # lambda_1/N's 0.99974, and 2.48x larger steps at rebalance dates.
        # There is no scalar column, so it is derived from the stored spectrum,
        # which the FR16 trace identity makes exact.
        ev = rmt["eigenvalues"] or []
        n_t = len(ev) or None
        out["pillar_scores"]["rmt"] = (float(ev[0]) / n_t) if n_t else None
        out["spectral"] = {
            "f_t": rmt["f_t"], "lambda_minus": rmt["lambda_minus"],
            "lambda_plus": rmt["lambda_plus"],
            "q_t": (1000.0 / n_t) if n_t else 0.0, "n_t": n_t or 0,
        }
        out["component_as_of"]["rmt"] = _stamp(rmt["date"], as_of, out)
    else:
        out["component_as_of"]["rmt"] = "unavailable"
    from seraph.decision_support import explain
    exp = explain(point)
    out["explanation"] = exp.value["sentence"] if exp.status == "ok" else ""
    return out


def _stamp(component_date, as_of: str | None, out: dict) -> str:
    """Label a component's own date relative to the bundle's as-of date."""
    stamp = _as_of_date(component_date)
    text = stamp.isoformat() if stamp else "unknown"
    if as_of and text != as_of:
        out["coherent"] = False
        return f"{text} (stale relative to as_of {as_of})"
    return text


# --- DEMO SCAFFOLDING (delete with seraph/dashboard/demo_data.py) ----------
def demo_state() -> dict:
    """T0/mock preview state, reachable ONLY when SERAPH_DEMO=1.

    Every value is fabricated; see `seraph.dashboard.demo_data`, which carries
    the deletion instructions. Gated behind an explicit environment flag with a
    permanent on-page banner — a risk dashboard that can silently show
    synthetic numbers is a liability, so this path is loud and opt-in and is
    never a fallback for a failed fetch.
    """
    from seraph.dashboard.demo_data import demo_state as _demo

    state = _demo()
    state.setdefault("as_of", None)
    state["data_status"] = "preview"
    return state
# --- END DEMO SCAFFOLDING --------------------------------------------------


def load_bundle(scope: CacheScope) -> dict | None:
    """Uncached coherent read. Tests and the cached wrapper both call this."""
    if os.environ.get("SERAPH_DEMO") == "1":
        return demo_state()
    return assemble(asyncio.run(_fetch(scope.as_of)))


def cached_bundle(scope: CacheScope) -> dict | None:
    """Scope-keyed cached read. Really applies `st.cache_data` this time."""
    try:
        import streamlit as st
    except ImportError:
        return load_bundle(scope)

    @st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
    def _cached(key: tuple) -> dict | None:
        return load_bundle(CacheScope(*key))

    return _cached(scope.key())


def latest_state(as_of: str | None = None, *, scope: CacheScope | None = None) -> dict | None:
    """Assemble the latest coherent scored state, or None when nothing is scored.

    `as_of` selects a historical bundle; omitted, it resolves to the newest
    CSRS row and reads every other component at that same date.
    """
    if scope is None:
        scope = CacheScope(source=os.environ.get("SERAPH_DB_DSN", "default"), as_of=as_of)
    return cached_bundle(scope)
