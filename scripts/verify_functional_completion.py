#!/usr/bin/env python3
# Functional completion verification — what works end to end, and what does not
"""Exercise each completed journey and record the result as evidence.

This is not a test suite and not an audit. It answers one question per
journey: does this work right now, on this installation, with real data?
Every check either produces a real artefact or says precisely what is
missing. Nothing is simulated and no placeholder stands in for a result.

Writes `docs/evidence/functional-completion-<date>.json`. Read-only with
respect to the research database; the only writes are to the runtime SQLite
store in a temporary directory.

Run: python scripts/verify_functional_completion.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from seraph.shared_types import IST, ist_timestamp                 # noqa: E402


def check(name: str, requirement: str):
    """Decorator recording one journey's outcome without aborting the rest."""
    def wrap(fn):
        def run() -> dict:
            try:
                result = fn()
                return dict(journey=name, requirement=requirement, **result)
            except Exception as exc:                        # noqa: BLE001
                return dict(journey=name, requirement=requirement,
                            works=False,
                            error=f"{type(exc).__name__}: {exc}"[:400])
        run.__name__ = fn.__name__
        return run
    return wrap


@check("daily market corpus", "FR1, FR7, FR8")
def corpus() -> dict:
    import asyncpg

    from seraph.store.bootstrap import DEFAULT_DSN

    async def go():
        c = await asyncpg.connect(DEFAULT_DSN, timeout=10)
        try:
            return dict(
                rows=await c.fetchval("select count(*) from daily_prices"),
                symbols=await c.fetchval(
                    "select count(distinct symbol) from daily_prices"),
                first=str(await c.fetchval("select min(date) from daily_prices")),
                last=str(await c.fetchval("select max(date) from daily_prices")))
        finally:
            await c.close()

    stats = asyncio.run(go())
    return dict(works=stats["rows"] > 1_000_000, evidence=stats,
                note="real NSE daily OHLCV from the vendored EOD2 snapshot")


@check("point-in-time universe", "FR52, FR54")
def universe() -> dict:
    import asyncpg

    from seraph.store.bootstrap import DEFAULT_DSN

    async def go():
        c = await asyncpg.connect(DEFAULT_DSN, timeout=10)
        try:
            rows = await c.fetch(
                "select rebalance_date, array_length(members,1) as n "
                "from universe_snapshots order by rebalance_date")
            return [(str(r["rebalance_date"]), r["n"]) for r in rows]
        finally:
            await c.close()

    snaps = asyncio.run(go())
    at_target = [s for s in snaps if s[1] == 500]
    return dict(works=len(at_target) > 20,
                evidence=dict(snapshots=len(snaps), at_target=len(at_target),
                              underfilled=len(snaps) - len(at_target),
                              first=snaps[0][0] if snaps else None,
                              last=snaps[-1][0] if snaps else None),
                note=("Q_t = 2.00 where N_t = 500. Early epochs are "
                      "UNDERFILLED, reproducing AMENDMENT-02 rather than "
                      "working around it"))


@check("equity classification", "FR52 equity filter")
def classification() -> dict:
    from seraph.universe.instrument_type import classification_status, is_equity

    status = classification_status()
    return dict(works=status.available and not is_equity("NIFTYBEES"),
                evidence=dict(symbols=status.symbol_count,
                              etf_excluded=not is_equity("NIFTYBEES"),
                              equity_admitted=is_equity("RELIANCE")),
                note="ETFs excluded so mechanical correlation stays out of C_t")


@check("daily pillar vintages", "FR16-FR19, FR20-FR24, R01")
def vintages() -> dict:
    from seraph.live.store import LiveStore

    store = LiveStore(ROOT / "prototype_runs" / "live.sqlite")
    rows = store.daily_vintages()
    by_producer = {r["producer"]: r for r in rows}
    computed = [p for p, r in by_producer.items() if r["origin"] == "computed"]
    return dict(works=bool(computed),
                evidence={p: dict(origin=r["origin"], value=r["value"],
                                  input_end=r["input_end"],
                                  absence=r["absence"])
                          for p, r in by_producer.items()},
                note=("`origin` distinguishes computed here from read from a "
                      "prior research artefact from absent"))


@check("real producer to CSRS", "R01, FR25-FR29")
def decision_path() -> dict:
    from seraph.live.engine_adapter import (DECISION_ALLOWANCE,
                                            DailyVintageProducer, decision_id)
    from seraph.live.inference import (DecisionRequest, InferenceService,
                                       Vintage)
    from seraph.live.store import LiveStore

    store = LiveStore(ROOT / "prototype_runs" / "live.sqlite")
    stored = {r["producer"]: r for r in store.daily_vintages()}
    if not stored:
        return dict(works=False,
                    error="no daily vintages; run scripts/run_daily.py first")

    newest = max(r["input_end"] for r in stored.values())
    anchor = datetime.fromisoformat(newest)
    sessions = [(anchor - timedelta(days=d)).date().isoformat()
                for d in range(40, -2, -1)]
    service = InferenceService(session_dates=sessions)
    history = []
    for day in range(18, 0, -1):
        stamp = anchor - timedelta(days=day)
        for pillar, scale in (("hawkes", 0.05), ("rmt", 0.23),
                              ("hamilton", 0.30)):
            history.append(Vintage(producer=pillar, input_end=stamp.isoformat(),
                                   emission_available_at=stamp.isoformat(),
                                   value=scale + 0.0005 * day))
    service.warm_start(history, cutoff=anchor - timedelta(hours=2))

    bar_end = anchor + timedelta(days=1)
    as_of = bar_end + DECISION_ALLOWANCE
    producer = DailyVintageProducer(store=store)
    result = service.process(
        DecisionRequest(
            decision_id=decision_id(mode="historical_replay",
                                    stream_id="verification",
                                    bar_end=bar_end.isoformat()),
            as_of=as_of, trigger="bar_close", mode="historical_replay"),
        vintages=producer.vintages_for([], as_of), now=as_of)
    csrs = result.csrs
    return dict(works=csrs is not None,
                evidence=dict(
                    csrs=(round(csrs.csrs, 6) if csrs else None),
                    mask=(list(csrs.mask) if csrs else None),
                    ci=([round(csrs.ci_lower, 4), round(csrs.ci_upper, 4)]
                        if csrs else None),
                    warnings=[w[:110] for w in result.warnings[:3]]),
                note=("warm start here is synthetic, so the SCORE is a path "
                      "demonstration; the vintages and the mask are real"))


@check("benchmark overlay", "FR41, FR54")
def overlay() -> dict:
    from seraph.ingestion import benchmark_client

    described = benchmark_client.describe()
    joined = benchmark_client.align([dict(date="2005-01-03", csrs=0.5),
                                     dict(date="2026-08-21", csrs=0.4)])
    return dict(works=described["available"] and joined["coverage"]["matched"] == 1,
                evidence=dict(series=described, coverage=joined["coverage"]),
                note=("the official NSE index; the pre-2012 gap is reported "
                      "rather than forward-filled or substituted"))


@check("market flow panel", "FR45, FR51")
def flow() -> dict:
    from seraph.dashboard.console_backend import market_flow

    current = market_flow()
    return dict(works=current.get("available", False), evidence=current,
                note=("real NSE print, or an explicit absence. No example "
                      "values are substituted"))


@check("durable role workflows", "FR42, FR43, FR47, FR49")
def workflows() -> dict:
    from seraph.dashboard.console_backend import WORKFLOW_ROLES, dispatch
    from seraph.orchestration.prototype import InferenceSession
    from seraph.orchestration.run_store import RunStore

    with tempfile.TemporaryDirectory() as scratch:
        import os
        os.environ["SERAPH_WORKSPACE_DIR"] = scratch
        store = RunStore(Path(scratch) / "ui.sqlite")
        run = store.begin(dict(mode="verification",
                               data_available_through="2020-01-01"))
        inputs = {p: dict(score_eligible=True, value=v, variance=0.01,
                          information_timestamp="2020-01-01T15:30:00+05:30")
                  for p, v in (("hawkes", 0.4), ("rmt", 0.5),
                               ("hamilton", 0.6))}
        point = InferenceSession(["2020-01-01"]).step(
            "2020-01-01", inputs, [], run_id=run)
        store.put(run, point)
        store.finish(run, 1)

        def event(op, **args):
            return dict(id=f"v-{op}", run_id=point["run_id"],
                        date=point["date"], op=op, **args)

        made = dispatch(store, point, "retail",
                        event("ws_create", name="Verification"))
        pid = made["value"]["portfolio_id"]
        dispatch(store, point, "retail", event(
            "ws_commit", portfolio_id=pid,
            body="symbol,quantity,price\nRELIANCE,10,1300\n",
            effective_at="2026-01-02T09:15:00+05:30"))
        held = dispatch(store, point, "retail",
                        event("ws_holdings", portfolio_id=pid))
        scenario = dispatch(store, point, "institutional", event(
            "sc_save", name="Verification shock", kind="rank_shock",
            steps=[dict(pillar="rmt", delta=0.2, horizon=3)],
            assumptions=[dict(key="shock", value=0.2, unit="rank",
                              justification="verification probe")]))
        sid = scenario["value"]["scenario_id"]
        ran = dispatch(store, point, "institutional",
                       event("sc_run", scenario_id=sid))
        case = dispatch(store, point, "regulator", event(
            "case_open", title="Verification case", priority="high"))
        return dict(
            works=bool(held["value"]["holdings"] and ran["value"]["results"]
                       and case["value"]["case_id"]),
            evidence=dict(operations=len(WORKFLOW_ROLES),
                          holdings=len(held["value"]["holdings"]),
                          scenario_run=bool(ran["value"]["results"]),
                          case=case["value"]["case_id"][:16],
                          identity=made["identity"]["note"][:60]),
            note="durable and owner-scoped; local demo identity, not auth")


@check("prospective forecast ledger", "R12, C10")
def forecasts() -> dict:
    from seraph.live.store import LiveStore

    store = LiveStore(ROOT / "prototype_runs" / "live.sqlite")
    rows = store.forecasts(limit=200)
    pending = store.forecasts(pending_only=True, limit=200)
    return dict(works=bool(rows),
                evidence=dict(issued=len(rows), pending=len(pending),
                              sample=[dict(model=r["model"],
                                           target=r["target"],
                                           probability=r["probability"],
                                           matures_after=r["matures_after"],
                                           outcome=r["outcome"])
                                      for r in rows[:3]]),
                note="outcome stays null until the horizon elapses")


@check("installed distribution", "O01, O02")
def packaging() -> dict:
    latest = sorted((ROOT / "docs" / "evidence").glob("PACKAGING-*.json"))
    if not latest:
        return dict(works=False,
                    error="no packaging evidence; run scripts/verify_packaging.py")
    body = json.loads(latest[-1].read_text(encoding="utf-8"))
    verdict = body.get("verdict", {})
    return dict(works=bool(verdict.get("passed")), evidence=verdict,
                note=f"from {latest[-1].name}")


BLOCKED = [
    dict(journey="fresh Hawkes pillar", requirement="FR10-FR15",
         blocked_by=("`intraday_bars` is empty. FR1 sources 5-minute bars "
                     "from Kite Connect; scripts/backfill_intraday.py is "
                     "written and checkpointed but needs a paid subscription "
                     "and a daily interactive login"),
         consequence=("Hawkes is published as an archived research estimate "
                      "or a declared absence. Because DECLARED_CADENCE puts "
                      "it at bar_close, an archived daily value is stale "
                      "against its own cadence and the D2 mask correctly "
                      "excludes it from a live composite"),
         needs="owner: a Kite Connect subscription and login"),
    dict(journey="measured sector micro-flags", requirement="FR14",
         blocked_by="same intraday dependency: per-sector jump counts come "
                    "from Lee-Mykland extraction over 5-minute bars (FR50)",
         consequence="the portfolio overlay names the absence and its cause; "
                     "no substitute is used",
         needs="owner: the same Kite dependency"),
    dict(journey="directed contagion network", requirement="FR15",
         blocked_by="needs the Hawkes branching matrix, which needs the same "
                    "intraday estimation",
         consequence="not displayed; no inferred network is shown",
         needs="owner: the same Kite dependency"),
    dict(journey="counterfactual policy path", requirement="FR48",
         blocked_by=("`project_xi` needs a FITTED HamiltonEngine and no fit "
                     "artefact is persisted. Hamilton is also under a "
                     "standing research exclusion (NOT_PRODUCTION)"),
         consequence="the direct regime-path simulator works; the macro "
                     "z-to-xi mapping is unavailable and says so",
         needs="owner: a decision on persisting a Hamilton fit despite the "
               "standing exclusion"),
    dict(journey="defensive action drawdown comparison", requirement="FR46",
         blocked_by=("needs declared positions, execution and cost "
                     "assumptions. Those are financially material choices "
                     "and are not invented here"),
         consequence="the playbook shows dominant-pillar guidance without a "
                     "measured drawdown reduction",
         needs="owner: the position/execution/cost contract"),
    dict(journey="institution exposure decomposition", requirement="FR42",
         blocked_by="needs authorised institution submissions. Private "
                    "positions are not derivable from public price bars",
         consequence="the surface reports absence rather than an inference",
         needs="owner: authorised data and a submission schema"),
    dict(journey="one-command launch of market plus news",
         requirement="C15 / O03",
         blocked_by=("launch_prototype.ps1, prototype_app.py and bridge.js "
                     "are being edited by a concurrent session in this "
                     "working tree"),
         consequence=("the market side runs from its own commands "
                      "(run_daily.py, run_live.py, run_forecast.py) and the "
                      "news side starts with the console. The server half of "
                      "every role workflow is complete and tested; its "
                      "browser controls are not wired"),
         needs="owner: decide whose changes to those files land first"),
]

CHECKS = [corpus, universe, classification, vintages, decision_path, overlay,
          flow, workflows, forecasts, packaging]


def main() -> int:
    results = [fn() for fn in CHECKS]
    working = [r for r in results if r.get("works")]
    report = dict(
        generated=ist_timestamp(datetime.now(IST).replace(microsecond=0)),
        summary=dict(journeys_checked=len(results), working=len(working),
                     not_working=len(results) - len(working),
                     blocked_elsewhere=len(BLOCKED)),
        journeys=results,
        blocked=BLOCKED,
        honesty=("`works` means the journey ran on this installation now. A "
                 "working journey is not a claim of predictive skill, "
                 "calibration or commercial readiness, and the blocked list "
                 "is not a list of things that nearly work"),
    )
    target = (ROOT / "docs" / "evidence" /
              f"functional-completion-{datetime.now(IST):%Y-%m-%d}.json")
    target.write_text(json.dumps(report, indent=2, default=str),
                      encoding="utf-8")
    for row in results:
        mark = "ok  " if row.get("works") else "FAIL"
        print(f"[{mark}] {row['journey']:34} ({row['requirement']})")
        if not row.get("works"):
            print(f"        {row.get('error', '')[:150]}")
    print(f"\n{len(working)}/{len(results)} journeys working; "
          f"{len(BLOCKED)} blocked on an owner action or external dependency")
    print(f"evidence: {target}")
    return 0 if len(working) == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
