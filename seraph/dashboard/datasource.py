# C12 — Dashboard (FR39-FR42): the fetch layer.
"""Reads whatever the pipeline has actually produced. Never computes, never
simulates: if a value is missing the dashboard shows a gap, because a plausible
placeholder on a risk instrument is worse than an empty panel.

`st.cache_data` is applied here per AGENTS.md §2 so the view layer never hits
the store on every rerun.
"""
from __future__ import annotations

import asyncio
from datetime import date

import asyncpg

from seraph.store.bootstrap import resolve_dsn


async def _fetch() -> dict | None:
    try:
        pool = await asyncpg.create_pool(resolve_dsn(), min_size=1, max_size=2, timeout=5)
    except Exception:
        return None
    try:
        csrs = await pool.fetchrow(
            "SELECT * FROM csrs ORDER BY ts DESC LIMIT 1")
        ham = await pool.fetchrow(
            "SELECT * FROM hamilton_output ORDER BY date DESC LIMIT 1")
        rmt = await pool.fetchrow(
            "SELECT * FROM rmt_output ORDER BY date DESC LIMIT 1")
        return {"csrs": csrs, "hamilton": ham, "rmt": rmt}
    except Exception:
        return None
    finally:
        await pool.close()


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

    return _demo()
# --- END DEMO SCAFFOLDING --------------------------------------------------


def latest_state() -> dict | None:
    """Assemble the latest scored state, or None when nothing is scored yet."""
    import os

    if os.environ.get("SERAPH_DEMO") == "1":
        return demo_state()
    raw = asyncio.run(_fetch())
    if not raw or raw.get("csrs") is None:
        return None

    from seraph.shared_types import CsrsPoint, ist_timestamp

    row = raw["csrs"]
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
    out: dict = {"point": point, "pillar_scores": {}, "spectral": {}}
    if ham is not None:
        out["xi"] = (ham["xi_1"], ham["xi_2"], ham["xi_3"])
        out["pillar_scores"]["hamilton"] = ham["lsd_t"]
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
    from seraph.decision_support import explain
    exp = explain(point)
    out["explanation"] = exp.value["sentence"] if exp.status == "ok" else ""
    return out
