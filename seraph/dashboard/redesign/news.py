# C12 — Redesigned console: NEWS INTELLIGENCE (F2).
"""The news channel, on its own screen and in its own palette.

**F2 is not F1.** No quantity on this screen enters the CSRS, the pillars or
the D2 mask, and this module is never imported by `overview.py` or by the F1
adapter — `tests/test_redesign_overview.py` asserts that structurally, so the
separation does not depend on anyone remembering it.

Two consequences for the design, both deliberate:

* **A different palette.** The pillar colours (lavender / cyan / amber) are
  reserved for measured market pillars. Nothing here uses them, so a glance
  cannot confuse a documented news exposure with a measured Hawkes edge.
* **Exposure routes are mappings, not measurements.** A sector appearing here
  means the curated registry documents a route from an event to that sector.
  It is not an estimate of contagion and must never be read as one.

**Two clocks, never swapped.** `current_news` is the live clock answering
"what is known now". `historical_decision` is a strict replay answering "what
was known at that decision". The screen states which is in force; it does not
fall back from one to the other.
"""
from __future__ import annotations

import streamlit as st

from . import components as C, tokens as T

#: F2's own accents. Deliberately NOT PILLAR_COLOUR — see the module note.
NEWS_PRIMARY = "#5BD6B0"
NEWS_SECONDARY = "#D98FC0"

SEVERITY_TONE = {"severe": "bad", "major": "bad", "moderate": "warn",
                 "minor": "", "none": ""}


def render(*, role: str, clock: str, state: dict) -> None:
    """`state` comes from `news_data.news_state`, built and cached by the app.

    Taking it rather than building it keeps this module free of I/O and lets
    the caller key the cache on the clock — a `current_news` payload must
    never be served for a `historical_decision` request.
    """
    strict = clock == "historical_decision"

    C.html_block(
        f'<div class="rd-topbar" style="border-color:#24433C">'
        f'<div><p class="rd-eyebrow" style="color:{NEWS_PRIMARY}">'
        f'SERAPH · F2 news intelligence</p>'
        f'<h1>News intelligence</h1>'
        f'<p class="rd-panel-sub" style="margin-top:4px">'
        f'a separate channel from the market pillars — no news signal enters '
        f'the CSRS</p></div>'
        f'<div class="rd-topbar-right">'
        f'{C.chip("clock", clock, tone="accent")}'
        f'{C.chip("role", role)}'
        f'</div></div>')

    if not state.get("connected"):
        with C.panel("News channel not attached", "F2"):
            C.html_block(C.unavailable("no news store", state.get("reason", "")))
        return

    _clock_banner(state, strict)
    _freshness(state)
    _signals(state)
    _sector_and_geography(state)
    _assets(state)
    _coverage(state)
    _method(state)


# --------------------------------------------------------------------------
def _clock_banner(state: dict, strict: bool) -> None:
    if strict:
        C.html_block(
            f'<div class="rd-panel" style="border-color:#3A3366;'
            f'background:#15122A"><p class="rd-panel-title" '
            f'style="color:{T.ACCENT}">HISTORICAL REPLAY</p>'
            f'<p class="rd-reason">Only evidence received by '
            f'<span class="rd-num">{C.esc(state.get("as_of"))}</span> is '
            f'shown. This answers what was known at that decision, not what '
            f'is known now, and the two are never substituted for one '
            f'another.</p></div>')
    else:
        C.html_block(
            f'<p class="rd-panel-note">CURRENT NEWS · live news clock at '
            f'<span class="rd-num">{C.esc(state.get("as_of"))}</span>. This is '
            f'what is known now, not a reconstruction of any market '
            f'decision.</p>')


def _freshness(state: dict) -> None:
    fresh = state.get("freshness") or {}
    worker = fresh.get("worker") or {}
    bits = []
    if fresh:
        stale = fresh.get("stale")
        bits.append(C.chip("channel", "stale" if stale else "fresh",
                           tone="warn" if stale else "ok"))
        if fresh.get("age_minutes") is not None:
            bits.append(C.chip("newest item",
                               f"{fresh['age_minutes']:.1f} min old"))
        if fresh.get("late_sources") is not None:
            bits.append(C.chip(
                "late sources",
                f"{fresh['late_sources']} of {fresh.get('total_sources', '?')}",
                tone="warn" if fresh.get("late_sources") else ""))
    if worker:
        bits.append(C.chip("worker", str(worker.get("activity")
                                         or worker.get("state") or "unknown")))
    if bits:
        C.html_block(C.chips(bits))
    if worker.get("note"):
        C.html_block(f'<p class="rd-panel-note">{C.esc(worker["note"])}</p>')


def _signals(state: dict) -> None:
    signals = state.get("signals") or []
    pagination = state.get("pagination") or {}

    with C.panel("Signal rail", "events visible at this clock"):
        if not signals:
            C.html_block(C.unavailable(
                "no event visible at this clock",
                "the news store is attached and holds nothing eligible at "
                "this moment. That is an empty result, not a failure"))
            return
        rows = []
        for item in signals:
            rows.append([
                item.get("published_at") or item.get("first_seen_at"),
                item.get("event_type"),
                (item.get("headline") or "")[:120],
                item.get("lifecycle"),
                item.get("confidence") or item.get("evidence_confidence"),
            ])
        C.html_block(C.table(
            ["published", "event type", "headline", "lifecycle", "confidence"],
            rows))
        total = pagination.get("total")
        shown = pagination.get("displayed", len(signals))
        offset = pagination.get("offset", 0)
        C.html_block(C.chips([
            C.chip("showing", f"{offset + 1}–{offset + shown} of {total}"),
            C.chip("page size", str(pagination.get("limit", "—"))),
        ]))
        if pagination.get("note"):
            C.html_block(f'<p class="rd-panel-note">'
                         f'{C.esc(pagination["note"])}</p>')


def _sector_and_geography(state: dict) -> None:
    surfaces = state.get("surfaces") or {}
    left, right = st.columns([1.15, 1], gap="medium")

    with left:
        sector = surfaces.get("sector_stress") or {}
        with C.panel("Sector exposure routes",
                     "documented mappings — NOT measured contagion"):
            news_block = sector.get("news") or {}
            rows = news_block.get("rows") or []
            if not rows:
                C.html_block(C.unavailable(
                    "no sector route visible",
                    str(news_block.get("reason")
                        or "no event at this clock maps to a documented "
                           "sector route")))
            else:
                C.html_block(C.table(
                    ["sector", "severity", "confidence", "direction",
                     "mechanisms"],
                    [[r.get("sector"), r.get("severity"),
                      r.get("evidence_confidence"),
                      ", ".join(r.get("direction") or []) or None,
                      len(r.get("mechanisms") or []) or None]
                     for r in rows], numeric_columns={4}))
            C.html_block(
                f'<div style="margin-top:10px">'
                f'{C.chip("status", str(news_block.get("status", "—")))}</div>'
                f'<p class="rd-panel-note">A row here means the curated '
                f'registry documents a route from an event to that sector. It '
                f'is <b>not</b> an estimate of contagion, it carries no '
                f'magnitude, and it is drawn in the F2 palette so it cannot be '
                f'mistaken for the measured Hawkes network.</p>')

    with right:
        geography = surfaces.get("geography") or {}
        with C.panel("Geography", "places named by eligible events"):
            regions = geography.get("regions") or []
            if not regions:
                C.html_block(C.unavailable(
                    "no place named",
                    "no event at this clock resolves to a registered place"))
            else:
                C.html_block(C.table(
                    ["place", "severity", "events", "status"],
                    [[r.get("name"), r.get("severity"),
                      len(r.get("events") or []) or None, r.get("status")]
                     for r in regions], numeric_columns={2}))
            if geography.get("status"):
                C.html_block(C.chips([
                    C.chip("surface status", str(geography["status"]),
                           tone="warn" if geography["status"] == "estimate"
                           else "")]))


def _assets(state: dict) -> None:
    assets = (state.get("surfaces") or {}).get("assets") or {}
    items = assets.get("items") or []
    with C.panel("Assets", "registered facilities referenced by events"):
        if not items:
            C.html_block(C.unavailable(
                "no asset referenced",
                "no event at this clock references a registered asset"))
            return
        C.html_block(C.table(
            ["asset", "kind", "operator", "capacity", "status"],
            [[a.get("name"), a.get("kind"), a.get("operator"),
              (None if a.get("capacity") is None
               else f"{a['capacity']:g} {a.get('capacity_unit', '')}".strip()),
              a.get("status")] for a in items[:40]], numeric_columns={3}))
        if len(items) > 40:
            C.html_block(f'<p class="rd-panel-note">Showing 40 of '
                         f'{len(items)} registered assets.</p>')


def _coverage(state: dict) -> None:
    coverage = state.get("source_coverage") or {}
    with C.panel("Source coverage", "what this channel does and does not see"):
        bits = [
            C.chip("publishers", str(coverage.get("publishers", "—"))),
            C.chip("registered feeds", str(coverage.get("registered_feeds", "—"))),
            C.chip("covered", f"{coverage.get('covered', '—')} of "
                              f"{coverage.get('total', '—')}"),
        ]
        languages = coverage.get("languages") or []
        if languages:
            bits.append(C.chip("languages", ", ".join(languages)))
        C.html_block(C.chips(bits))

        uncovered = coverage.get("uncovered") or []
        if uncovered:
            C.html_block(
                '<p class="rd-unavail-label" style="margin-top:14px">'
                'not covered right now</p>'
                + "".join(f'<p class="rd-reason">· {C.esc(u)}</p>'
                          for u in uncovered))
        gaps = coverage.get("coverage_gaps") or []
        if gaps:
            C.html_block(
                '<p class="rd-unavail-label" style="margin-top:14px">'
                'declared coverage gaps — standing limitations, not outages</p>'
                + "".join(f'<p class="rd-reason">· {C.esc(g)}</p>'
                          for g in gaps))


def _method(state: dict) -> None:
    manifest = state.get("manifest") or {}
    policy = state.get("temporal_policy") or {}
    with st.expander("Method — what produced these numbers", expanded=False):
        if manifest:
            rows = [[k, str(v)[:160]] for k, v in manifest.items()
                    if not isinstance(v, (dict, list))]
            C.html_block(C.table(["field", "value"], rows))
        if policy:
            C.html_block(
                f'<p class="rd-panel-note"><b>Temporal policy:</b> '
                f'{C.esc(policy.get("policy", ""))} · strict='
                f'{C.esc(policy.get("strict"))} · '
                f'{C.esc(policy.get("total"))} reference records admitted'
                f'</p>')
            excluded = policy.get("excluded_unknown_dates") or {}
            if excluded:
                C.html_block(
                    f'<p class="rd-panel-note">Excluded for unknown dates: '
                    f'{C.esc(excluded)}</p>')
        connected = state.get("connected_surfaces") or []
        preview = state.get("preview_surfaces") or []
        C.html_block(C.chips([
            C.chip("connected surfaces", ", ".join(connected) or "none",
                   tone="ok" if connected else "warn"),
            C.chip("still fabricated", ", ".join(preview) or "none",
                   tone="warn" if preview else "ok"),
        ]))


# --------------------------------------------------------------------------
def pending_network() -> None:
    """F07 is not implemented and continues to display as pending."""
    with C.panel("Directed contagion network", "F07"):
        C.html_block(
            f'<div style="margin-bottom:10px">'
            f'{C.chip("F07 directed network", "PENDING", tone="warn")}</div>')
        C.html_block(C.unavailable(
            "not implemented",
            "the directed contagion network is pending. The exposure routes "
            "above are documented mappings in the F2 palette and are "
            "deliberately drawn unlike the measured Hawkes network, which "
            "lives in the market channel"))
