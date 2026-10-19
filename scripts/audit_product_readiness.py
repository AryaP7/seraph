"""Independent engineering audit probes; no market, model or source-store writes.

Synthetic inputs demonstrate runtime defects, not predictive performance.
Existing local news data are inspected through SQLite mode=ro only.
"""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(variable, "1")


def run():
    from seraph.live import BarBuilder, LiveLoop, MarketClock, ReplayFeed, Tick
    from seraph.shared_types import IST, ist_timestamp
    from seraph.identity import IdentityRegistry
    from seraph.decision_support.workspace import WorkspaceStore
    from seraph.news.registry import load_master_data
    from seraph.dashboard.console_backend import liveness_of

    now = datetime(2026, 10, 16, 11, 5, tzinfo=IST)
    stamp = lambda minute: f"2026-10-16T11:{minute:02d}:00+05:30"
    tick = lambda minute, price=100: Tick("AUDIT", stamp(minute), price)
    clock = MarketClock()
    findings = {}

    # This synthetic adapter makes no network connection.
    class SyntheticLiveFeed(ReplayFeed):
        is_live = True
        source_kind = "broker_websocket"

    feed = SyntheticLiveFeed([tick(1)])
    loop = LiveLoop(feed, clock=clock)
    loop.connect(["AUDIT"])
    decision = loop.tick(at=now)
    findings["live_without_evaluator"] = {
        "publishable": decision.publishable, "csrs": decision.csrs,
        "bars_closed": decision.bars_closed,
        "defect_reproduced": decision.publishable and decision.csrs is None,
    }
    from scripts.run_live import build_loop
    with patch.dict(os.environ, {}, clear=True):
        configured = build_loop(replay=True)
    findings["live_entrypoint_wiring"] = {
        "evaluate_is_none": configured.evaluate is None,
        "on_decision_is_none": configured.on_decision is None,
    }

    builder = BarBuilder(clock)
    builder.add([tick(1)])
    first = builder.close_elapsed(now)
    builder.add([tick(2, 999)])
    second = builder.close_elapsed(now)
    findings["late_tick_after_timer_close"] = {
        "first": [b.describe() for b in first],
        "second": [b.describe() for b in second],
        "late_ticks": builder.late_ticks,
        "defect_reproduced": bool(second and second[0].end == first[0].end),
    }
    builder = BarBuilder(clock)
    builder.add([Tick("AUDIT", stamp(1), 100, 100),
                 Tick("AUDIT", stamp(4), 101, 150)])
    first = builder.close_elapsed(now)
    builder.add([Tick("AUDIT", stamp(6), 102, 170),
                 Tick("AUDIT", stamp(9), 103, 200)])
    second = builder.close_elapsed(now.replace(minute=10))
    findings["volume_boundary_loss"] = {
        "previous_cumulative": 150, "next_cumulative": [170, 200],
        "second_bar_volume": second[0].volume,
        "difference_since_previous_bar": 50,
        "defect_reproduced": second[0].volume != 50,
        "note": "20 units between the prior bar's last and next bar's first tick disappear",
    }
    future = clock.recency("2026-10-17T11:00:00+05:30", at=now)
    findings["future_timestamp"] = future.describe()
    with patch.object(MarketClock, "now", return_value=now):
        findings["recent_archive_liveness"] = liveness_of({
            "evaluation_timestamp": stamp(4), "mode": "historical_replay"})

    with tempfile.TemporaryDirectory(prefix="seraph-readiness-") as tmp:
        registry = IdentityRegistry(Path(tmp) / "identity.sqlite")
        workspace = WorkspaceStore(Path(tmp) / "workspace.sqlite", registry)
        registry.add_organisation("audit", "Synthetic audit organisation", "institution")
        user = registry.upsert_user(provider_subject="audit", issuer="https://audit.invalid")
        registry.add_membership(user.user_id, "audit")
        registry.grant(user.user_id, "audit", "institutional", granted_by="audit")
        session = registry.open_session(user.user_id)
        principal = registry.resolve(session.session_id)
        book = workspace.create_portfolio(principal, name="Synthetic audit book")
        registry.revoke_grant(user.user_id, "audit", "institutional")
        allowed = registry.can(principal, "read", "portfolio", book["portfolio_id"])
        returned = workspace.portfolio(principal, book["portfolio_id"])
        findings["revoked_cached_principal"] = {
            "can_read": allowed, "workspace_read_returned": bool(returned),
            "note": "fresh resolve denies access; existing Principal remains authorized",
        }

    master, registry_report = load_master_data()
    registry_report.pop("directory", None)
    findings["news_registry"] = registry_report
    news_path = ROOT / "prototype_runs/news.sqlite"
    if news_path.exists():
        with sqlite3.connect(news_path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            sources = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sources")]
            findings["local_news_store"] = {
                "sources": [{k: s.get(k) for k in ("source_id", "provider", "kind")}
                            for s in sources],
                "counts": {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                           for table in ("stories", "observations", "ingest_log")},
            }

    inventory = []
    errors = []
    for directory in ("seraph", "scripts", "fixtures", "tests"):
        for path in sorted((ROOT / directory).rglob("*.py")):
            raw = path.read_bytes()
            try:
                tree = ast.parse(raw.decode("utf-8-sig"))
            except (SyntaxError, UnicodeDecodeError) as exc:
                errors.append({"path": path.relative_to(ROOT).as_posix(), "error": str(exc)})
                continue
            imports = sorted({node.module for node in ast.walk(tree)
                              if isinstance(node, ast.ImportFrom) and node.module})
            inventory.append({"path": path.relative_to(ROOT).as_posix(),
                              "sha256": hashlib.sha256(raw).hexdigest(),
                              "lines": len(raw.splitlines()), "imports": imports})
    return {
        "audit": "independent product-readiness audit",
        "created_at": ist_timestamp(datetime.now(IST)),
        "synthetic_probes_are_not_live_or_predictive_evidence": True,
        "findings": findings,
        "inventory_counts": dict(Counter(row["path"].split("/")[0] for row in inventory)),
        "syntax_errors": errors,
        "source_inventory": inventory,
    }


if __name__ == "__main__":
    result = run()
    target = (Path(sys.argv[1]) if len(sys.argv) > 1 else
              ROOT / "docs/evidence/INDEPENDENT-READINESS-2026-10-16.json")
    if target.exists():
        raise SystemExit(f"Refusing to overwrite audit evidence: {target}")
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "source_inventory"}, indent=2))
