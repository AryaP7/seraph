"""Generate docs/IMPLEMENTATION-STATUS.md from the ticket rows below.

The plan (§2) requires separate columns for implemented / canonical-route
integrated / real-input verified / recovery accepted / scientific status, and
requires counts to be *generated* from the rows rather than typed by hand —
the previous status register drifted (it claimed 25 verified while listing 27
IDs, and said no news had been fetched while a local store held 30 stories).

Edit TICKETS here; never hand-edit the generated markdown.

State vocabulary, used per column:
    yes        done and evidenced
    partial    some of it, with the remainder named
    no         not done
    n/a        the column does not apply to this ticket
    blocked:X  cannot proceed until X
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "IMPLEMENTATION-STATUS.md"

COLUMNS = ("implemented", "integrated", "real_input", "recovery", "science")

#: id, finding, implemented, integrated, real_input, recovery, science,
#: files, evidence, blocker
TICKETS = [
    dict(id="T00", finding="baseline inconsistent",
         implemented="yes", integrated="n/a", real_input="yes", recovery="n/a",
         science="n/a",
         files="scripts/build_implementation_status.py, docs/IMPLEMENTATION-STATUS.md",
         evidence="docs/evidence/T00-RECONCILE-2026-10-16.json — R01/R02/R03 "
                  "reproduced against current code; 130 uncommitted paths "
                  "preserved; 0 stashes",
         blocker=""),
    dict(id="T01", finding="R02 publication gates claim currency without a score",
         implemented="yes", integrated="yes", real_input="partial",
         recovery="n/a", science="n/a",
         files="seraph/live/publication.py (new), live/loop.py, live/clock.py, "
               "dashboard/console_backend.py",
         evidence="tests/test_t01_publication_gating.py; "
                  "docs/evidence/T01-PUBLICATION-2026-10-16.json",
         blocker="real-feed provenance needs broker credentials"),
    dict(id="T02", finding="R03 bar finality and volume accounting",
         implemented="yes", integrated="yes", real_input="no", recovery="yes",
         science="n/a",
         files="seraph/live/bars.py",
         evidence="tests/test_t02_bar_finality.py; "
                  "docs/evidence/T02-BARS-2026-10-16.json",
         blocker="real tick stream needs broker credentials"),
    dict(id="T03", finding="R05 role buttons do not open role workspaces",
         implemented="yes", integrated="yes", real_input="n/a", recovery="n/a",
         science="n/a",
         files="seraph/dashboard/console_component/bridge.js, "
               "console_component/index.html, dashboard/prototype_app.py",
         evidence="tests/js/bridge_harness.mjs; tests/test_t03_role_routes.py; "
                  "browser capture",
         blocker=""),
    dict(id="T04", finding="R06 authentication and owned workflows bypassed",
         implemented="partial", integrated="no", real_input="n/a",
         recovery="n/a", science="n/a",
         files="seraph/identity/model.py (StalePrincipal, authorization_revision), "
               "seraph/identity/registry.py (revalidate, check_revision, "
               "can/require/visible revalidate)",
         evidence="tests/test_t04_authorization_freshness.py (20 passed): revoked "
                  "grant/session/membership, disabled user and expired session all "
                  "deny a cached Principal; scope narrowed mid-request fails the "
                  "commit check; visible() revalidates once for 50 resources",
         blocker="authorization freshness DONE. Remaining: OIDC login wiring "
                 "(deferred by owner) and the application service boundary, "
                 "which T08/T14 integration needs"),
    dict(id="T05", finding="R11 Hawkes basket metadata does not govern the stream",
         implemented="yes", integrated="partial", real_input="yes",
         recovery="n/a",
         science="input provenance only; no model change",
         files="seraph/pillars/hawkes/basket_stream.py (new: StreamBuilder, "
               "PooledStream, WindowManifest, membership_segments, "
               "verify_manifest), seraph/ingestion/hawkes_universe.py "
               "(BasketTimeline), scripts/write_hawkes_production.py (rewired), "
               "scripts/compare_hawkes_basket_selection.py (new)",
         evidence="tests/test_t05_hawkes_basket.py; "
                  "docs/evidence/T05-BASKET-SELECTION-2026-10-16.json — on the "
                  "real corpus 465/473 windows had different pooled counts; "
                  "terminal-basket selection inflated contributors 1.41x (max "
                  "1.57x) and negative events 1.42x",
         blocker="the corrected rows are NOT yet persisted. The source "
                 "database is read-only, so --write needs the research "
                 "instance on 5434; until then C8 still reads the 473 "
                 "pre-T05 rows computed from the terminal basket"),
    dict(id="T06", finding="R01 live entry point does not invoke the risk engine",
         implemented="yes", integrated="yes", real_input="partial",
         recovery="partial", science="unchanged pillars; units decision DR-09",
         files="seraph/live/inference.py (new: DecisionRequest/DecisionResult, "
               "InferenceService, DeploymentRegistry, StandardizerHistory, "
               "StateSnapshot, sessions_elapsed), "
               "seraph/live/archive_adapter.py (new), "
               "seraph/live/engine_adapter.py (new: attach, ServiceEvaluator, "
               "NullProducers), seraph/live/loop.py (warmup_source, feed_sink), "
               "scripts/verify_t06_equivalence.py (new)",
         evidence="tests/test_t06_inference_service.py (42), "
                  "test_t06_archive_equivalence.py (11), "
                  "test_t06_engine_in_the_loop.py (12); "
                  "docs/evidence/T06-EQUIVALENCE-FULL-2026-10-17.json and "
                  "T06-EQUIVALENCE-1530-2026-10-17.json — 5,361 archive "
                  "sessions under BOTH decision policies, 0 disagreements on "
                  "reconciled state or composite",
         blocker="NO LIVE PRODUCER IS CONNECTED. The loop invokes the engine "
                 "on every bar close, but NullProducers emits a structural "
                 "absence for all three pillars, so a live tick yields no "
                 "CSRS. Live Hawkes needs T07's warm-started count window; "
                 "RMT/Hamilton are daily store products. Snapshot/restore "
                 "exists in memory; durability is T07"),
    dict(id="T07", finding="R04 no recoverable scoring state",
         implemented="yes", integrated="yes", real_input="no", recovery="yes",
         science="n/a",
         files="seraph/live/store.py (new), live/migrations/001_runtime.sql "
               "(new), live/lifecycle.py (new), live/loop.py (last_closed), "
               "live/clock.py (next_open finds a later window the same day), "
               "scripts/run_live.py (restore, durable commit, bounded --once, "
               "read-only --status)",
         evidence="tests/test_t07_durable_runtime.py (42) — crash injected at "
                  "ALL FOUR writes inside the one transaction, each leaving no "
                  "decision, no advanced head and no outbox row; "
                  "tests/test_t07_runtime_recovery.py (10) — the real loop, "
                  "service and store across a restart; "
                  "docs/evidence/T07-DURABILITY-2026-10-17.json",
         blocker="no live feed, so the durable path has never run against a "
                 "real tick stream. Delivery is at-least-once with a receiver "
                 "idempotency key and no transport is attached yet (T15)"),
    dict(id="T08", finding="R12 UI shows historical runs only",
         implemented="yes", integrated="yes", real_input="partial",
         recovery="n/a", science="n/a",
         files="seraph/dashboard/current_reader.py (new), prototype_app.py "
               "(LIVE RUNTIME panel, live/replay/demo selector), "
               "seraph/live/store.py (injectable commit time)",
         evidence="tests/test_t08_current_reader.py (25); "
                  "docs/evidence/T08-CURRENT-READER-2026-10-17.json — "
                  "verified in the real browser: a withheld decision shows "
                  "with its id, its own timestamp and the refusal reason; "
                  "demo mode consults no decision at all",
         blocker="no live feed, so no REAL live decision has ever been "
                 "committed; the browser check used a synthetic decision in "
                 "a scratch store. The two-second fragment poll is not wired "
                 "— revision() and RefreshGate exist and are tested"),
    dict(id="T09", finding="R07 narrow news acquisition",
         implemented="yes", integrated="yes", real_input="yes",
         recovery="partial", science="n/a",
         files="seraph/news/json_feed.py (new: named JSON adapters + "
               "JsonSourceFetcher), seraph/news/http_feed.py (day-granular "
               "date formats, day_granular()), scripts/run_news.py "
               "(VERIFIED_JSON_SOURCES, REJECTED_SOURCES), "
               "scripts/probe_news_sources.py",
         evidence="tests/test_t09_source_breadth.py (27); "
                  "docs/evidence/NEWS-SOURCE-PROBE-2026-10-17.json and "
                  "T09-SOURCE-BREADTH-2026-10-17.json — 11 candidates "
                  "probed, 6 usable, 86 new stories on the first poll "
                  "(Federal Register 40, SEBI 30, USGS 16). SEBI needed a "
                  "date-format fix; PIB carries no date element at all and "
                  "is rejected WITH the reason recorded",
         blocker="six sources are not world coverage. PIB unusable (no "
                 "publication time anywhere in its feed), GDELT rate-limited "
                 "and unregistered. 10 of 12 visible events now classify as "
                 "'other' — the extractor's vocabulary is RBI-shaped (T11/T12)"),
    dict(id="T10", finding="R08 reference data empty",
         implemented="partial", integrated="yes", real_input="yes",
         recovery="n/a", science="n/a",
         files="seraph/news/curated/places.csv, entities.csv, "
               "source_places.csv (new), seraph/news/registry.py "
               "(source_places, resolve_place, token-based partial matching)",
         evidence="5 places (each naming its GeoNames record), 1 entity and 5 "
                  "source issuing locations, all first-party cited; the "
                  "loader refuses an uncited row and that is now exercised by "
                  "the shipped rows. Washington D.C. and Mumbai both appear "
                  "as real origins on the globe",
         blocker="0 assets and 0 exposure edges. Without an edge there is no "
                 "transmission path to draw and no sector aggregate to "
                 "compute from news"),
    dict(id="T11", finding="R09 interpretation defects",
         implemented="partial", integrated="no", real_input="partial",
         recovery="n/a", science="rule system, not a measured model",
         files="seraph/news/extraction.py, news/model.py",
         evidence="monetary/banking event types added against the real RBI "
                  "corpus: 30/30 stories classify, 0 'other'",
         blocker="confirmations still count story IDs not provenance roots. "
                 "Origin resolution IS now wired (from the source's curated "
                 "issuing location); facility resolution is wired but has no "
                 "curated facility to resolve to"),
    dict(id="T12", finding="R09 category rules only",
         implemented="no", integrated="no", real_input="no", recovery="n/a",
         science="ordinal, not predictive", files="", evidence="", blocker=""),
    dict(id="T13", finding="R07/R08 map disconnected",
         implemented="yes", integrated="yes", real_input="yes",
         recovery="n/a", science="ordinal and evidential; not predictive",
         files="seraph/dashboard/globe_payload.py (new), "
               "console_component/news_layer.js (new), "
               "console_component/index.html (SERAPH_GLOBE_API, news layer), "
               "console_backend.py (news_branch, renderer_geometry), "
               "news_view.py, prototype_app.py, bridge.js",
         evidence="tests/test_t13_globe_payload.py (37), "
                  "test_t13_origin_and_resolution.py (17), "
                  "tests/js/news_layer_harness.mjs (27); "
                  "docs/evidence/T13-NEWS-TO-GLOBE-2026-10-17.json and "
                  "T13-GLOBE-BROWSER-2026-10-17.jpg — 30 real RBI stories "
                  "place India and Mumbai on the original globe in the real "
                  "browser, beside the fabricated layer, in a different palette",
         blocker="no exposure edge is curated, so the PATHS layer is "
                 "legitimately empty and browser acceptance 2 (foreign origin "
                 "-> evidenced Indian exposure) is not met. Showing this on a "
                 "CURRENT decision needs T08: no persisted run reaches "
                 "2026-10-16 when these stories were first seen"),
    dict(id="T14", finding="R10 role workflow libraries unused",
         implemented="partial", integrated="no", real_input="no",
         recovery="no", science="n/a",
         files="decision_support/workspace.py, scenarios.py, cases.py",
         evidence="library tests pass; console does not call them",
         blocker="depends on T04, T08, T13"),
    dict(id="T15", finding="R12 operations incomplete",
         implemented="partial", integrated="no", real_input="no",
         recovery="no", science="n/a",
         files="seraph/operations/*, seraph/store/migrations/*",
         evidence="job lease/checkpoint and alert ledger tested in isolation",
         blocker="no delivery transport; backup/restore never exercised"),
    dict(id="T16", finding="prospective ledger not achieved",
         implemented="no", integrated="no", real_input="no", recovery="n/a",
         science="not started; preserve existing negative results",
         files="", evidence="", blocker="needs T07 live decisions to accrue"),
    dict(id="T17", finding="role differentiators proposed",
         implemented="no", integrated="no", real_input="no", recovery="n/a",
         science="n/a", files="", evidence="", blocker="depends on T14"),
    dict(id="T18", finding="release gate outstanding",
         implemented="no", integrated="no", real_input="no", recovery="no",
         science="no", files="", evidence="", blocker="depends on T01-T16"),
]


def tally() -> dict:
    counts = {c: {} for c in COLUMNS}
    for ticket in TICKETS:
        for column in COLUMNS:
            value = ticket[column] or "no"
            head = value.split(":")[0]
            counts[column][head] = counts[column].get(head, 0) + 1
    return counts


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    except Exception:                                        # noqa: BLE001
        return "unknown"


def render() -> str:
    counts = tally()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S%z")
    lines = [
        "# SERAPH implementation status",
        "",
        "**Generated** by `scripts/build_implementation_status.py` — do not",
        "hand-edit. Totals come from the rows, so they cannot drift out of step",
        "with them the way the previous register did.",
        "",
        f"Generated: {stamp} · git HEAD `{git_head()}`",
        "",
        "Ticket definitions and acceptance gates:",
        "[technical plan](SERAPH-TECHNICAL-DEVELOPMENT-PLAN-2026-10-16.md) §4.",
        "Findings: [independent audit]"
        "(INDEPENDENT-PRODUCT-READINESS-AUDIT-2026-10-16.md).",
        "",
        "## What the columns mean",
        "",
        "The distinction the audit insisted on: **code existing is not a",
        "delivered capability.** A library with passing tests that the canonical",
        "route never calls is `implemented: yes, integrated: no`.",
        "",
        "| Column | Question it answers |",
        "|---|---|",
        "| implemented | does usable code exist, with tests? |",
        "| integrated | does the supported entry point actually call it? |",
        "| real_input | verified against real external input, not fixtures? |",
        "| recovery | restart/fault behaviour exercised? |",
        "| science | scientific qualification, separate from engineering |",
        "",
        "`n/a` means the column does not apply. `blocked:X` names what is needed.",
        "",
        "## Tickets",
        "",
        "| id | finding | impl | integ | real input | recovery | science | files | evidence | blocker |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in TICKETS:
        lines.append(
            f"| **{t['id']}** | {t['finding']} | {t['implemented']} | "
            f"{t['integrated']} | {t['real_input']} | {t['recovery']} | "
            f"{t['science'] or '—'} | {t['files'] or '—'} | "
            f"{t['evidence'] or '—'} | {t['blocker'] or '—'} |")

    lines += ["", "## Generated totals", "",
              "| Column | " + " | ".join(
                  sorted({k for c in COLUMNS for k in counts[c]})) + " |",
              "|---" * (1 + len({k for c in COLUMNS for k in counts[c]})) + "|"]
    keys = sorted({k for c in COLUMNS for k in counts[c]})
    for column in COLUMNS:
        row = " | ".join(str(counts[column].get(k, 0)) for k in keys)
        lines.append(f"| {column} | {row} |")

    integrated = counts["integrated"].get("yes", 0)
    lines += [
        "",
        f"**{integrated} of {len(TICKETS)} tickets are integrated into the "
        f"supported entry point.** That is the number that describes product "
        f"completion; `implemented` counts describe library coverage.",
        "",
        "## Standing qualifications",
        "",
        "- Engineering completion is never predictive validation. The original",
        "  advance-warning claim remains unestablished.",
        "- Three RBI feeds are not world news coverage.",
        "- Synthetic and fixture evidence is software evidence only.",
        "- `seraph/shared_types/` is unchanged by every ticket here.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    TARGET.write_text(render(), encoding="utf-8")
    counts = tally()
    print(f"wrote {TARGET.relative_to(ROOT)}")
    print(f"tickets: {len(TICKETS)} | integrated yes: "
          f"{counts['integrated'].get('yes', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
