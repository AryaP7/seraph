# C12 — Redesigned console: the F2 news adapter (FR39-FR42).
"""The news-intelligence channel, read through the EXISTING builder.

**This module exists to make the F1/F2 separation structural.** The market
channel's adapter (`data.py`) and the CSRS screen (`overview.py`) do not
import it, and `tests/test_redesign_overview.py` asserts that they do not.
A news quantity therefore cannot reach the composite, the pillars or the D2
mask by accident: there is no import path for it to travel along.

News informs a reader. It is not an input to the CSRS, and the exposure
routes it carries are documented mappings rather than measured contagion.
"""
from __future__ import annotations

from pathlib import Path

from seraph.dashboard.news_view import build_news_payload

__all__ = ["news_state", "acquisition_state"]


def news_state(news_path, *, role: str = "retail", decision_ts: str | None = None,
               offset: int = 0, strict_replay: bool = False) -> dict:
    """The F2 news channel, or an explicit statement that it is not attached.

    `decision_ts=None` means the live news clock — "what is known now" — and
    `strict_replay=False` goes with it. A decision timestamp with
    `strict_replay=True` answers the different question "what was known
    then". The two are never silently swapped; the caller chooses and the
    screen says which.

    **Reads `surfaces`, not `channel`.** `build_news_payload` returns
    `surfaces` (`signals`, `sector_stress`, `geography`, `assets`) plus
    `pagination`, `source_coverage`, `freshness`, `manifest`,
    `temporal_policy`, `registry` and `role_view`. It has never returned a
    `channel` key. Classic's `news_only_panel` reads `payload['channel']`
    and so always reports zero events and zero sources however full the
    store is; that panel is only reachable when no archive store exists,
    which is why it has gone unnoticed. This adapter reads the keys the
    payload actually has.

    Nothing here is allowed to reach a CSRS surface. F2 informs a reader; it
    is not an input to the composite.
    """
    path = Path(news_path)
    if not path.exists():
        return dict(connected=False, reason=(
            f"no news store at {path}. `./launch_news.ps1` registers the "
            f"reviewed catalogue and starts the worker"), payload=None)
    from seraph.news import NewsStore
    from seraph.news.acquisition import _now as news_now
    from seraph.news.registry import load_master_data

    clock = decision_ts or news_now()
    store = NewsStore(path)
    master = load_master_data()[0]
    payload = build_news_payload(store, master, decision_ts=clock, role=role,
                                 offset=offset, strict_replay=strict_replay)
    surfaces = payload.get("surfaces") or {}
    signals = (surfaces.get("signals") or {}).get("items") or []
    return dict(connected=True, reason="", payload=payload, as_of=clock,
                mode="historical_decision" if strict_replay else "current_news",
                surfaces=surfaces, signals=signals,
                pagination=payload.get("pagination") or {},
                source_coverage=payload.get("source_coverage") or {},
                freshness=payload.get("freshness") or {},
                manifest=payload.get("manifest") or {},
                temporal_policy=payload.get("temporal_policy") or {},
                registry=payload.get("registry") or {},
                role_view=payload.get("role_view") or {},
                connected_surfaces=payload.get("connected_surfaces") or [],
                preview_surfaces=payload.get("preview_surfaces") or [])


def acquisition_state(news_path) -> dict:
    """Who is fetching news, and what each source actually returned.

    Worker liveness and per-source outcomes are different facts from the
    news content, and from each other: a worker can be polling happily while
    a source has failed for days.
    """
    from seraph.dashboard import news_service

    state = dict(news_service.status())
    state.pop("process", None)
    path = Path(news_path)
    if not path.exists():
        return dict(owner=state.get("owner"), reason=state.get("reason", ""),
                    store=False, worker=None, sources=[],
                    note="no news store yet; the worker creates one on its "
                         "first pass")
    from seraph.news import NewsStore
    from seraph.news.acquisition import _now as news_now

    store = NewsStore(path)
    worker = store.worker_state(news_now())
    rows = []
    for source in store.sources():
        health = store.health(source.source_id)
        rows.append(dict(source=source.source_id, status=health.status,
                         consecutive_failures=health.consecutive_failures,
                         last_success=getattr(health, "last_success_at", None),
                         detail=getattr(health, "detail", None)))
    rows.sort(key=lambda r: (r["status"] != "never_succeeded",
                             r["consecutive_failures"] == 0, r["source"]))
    return dict(owner=state.get("owner"), reason=state.get("reason", ""),
                store=True, worker=worker, sources=rows, note="")
