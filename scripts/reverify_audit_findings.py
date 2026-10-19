"""Re-probe every audit finding (A01-A14) against the current checkout.

The 2026-10-16 audit described the working tree at commit `51680bb`. This
script re-runs its reproductions so no finding is ever assumed still-present or
assumed fixed. It writes `docs/evidence/REVERIFY-<date>.json`.

It only ever creates temporary SQLite stores and reads the research archive.
No source database, persisted run or research artifact is modified.
"""
from __future__ import annotations
import json
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np                                                   # noqa: E402

from seraph.orchestration.prototype import InferenceSession, run_archive   # noqa: E402
from seraph.orchestration.run_store import RunStore                  # noqa: E402

PRESENT, FIXED = "present", "fixed"


def _point(run, day, value=1):
    return {"run_id": run, "date": day, "evaluation_timestamp": day + "T15:30:00+05:30",
            "data_cutoff": day + "T15:30:00+05:30", "original_pillars": {},
            "reconciled": {}, "composite": None,
            "coverage": {"mask": [False, False, False]}, "limitations": [], "value": value}


def _pillars(day, *, rmt_absence=None):
    out = {}
    for pillar in ("hawkes", "rmt", "hamilton"):
        if pillar == "hamilton":
            out[pillar] = dict(score_eligible=False, value=None, absence="structural",
                               absence_reason="no_data_coverage", reason="research exclusion")
        elif pillar == "rmt" and rmt_absence:
            out[pillar] = dict(score_eligible=False, value=None, absence=rmt_absence,
                               absence_reason="estimation_failed", reason="feed outage")
        else:
            out[pillar] = dict(score_eligible=True, value=0.3, reason="ok",
                               information_timestamp=day + "T15:30:00+05:30")
    return out


def a01_special_session_replay(tmp: Path) -> dict:
    results = {}
    for label, rng in (("muhurat_2024", ("2024-11-01", "2024-11-01")),
                       ("muhurat_2025", ("2025-10-21", "2025-10-21"))):
        try:
            report = run_archive(tmp / "a01.sqlite", start=rng[0], end=rng[1])
            results[label] = dict(ok=True, points=report["points"])
        except Exception as exc:                                     # noqa: BLE001
            results[label] = dict(ok=False, error=f"{type(exc).__name__}: {exc}")
    state = FIXED if all(v["ok"] for v in results.values()) else PRESENT
    return dict(finding="A01 archive replay by calendar date vs fixed 15:30 clock",
                state=state, detail=results)


def a02_transient_absence() -> dict:
    days = ["2020-01-01", "2020-01-02", "2020-01-03"]
    session = InferenceSession(days)
    masks = [session.step(days[0], _pillars(days[0]), [], run_id="x")["coverage"]["mask"],
             session.step(days[1], _pillars(days[1], rmt_absence="transient"), [],
                          run_id="x")["coverage"]["mask"],
             session.step(days[2], _pillars(days[2]), [], run_id="x")["coverage"]["mask"]]
    undeclared = dict(_pillars(days[0]))
    undeclared["rmt"] = dict(score_eligible=False, value=None, reason="no declaration")
    try:
        InferenceSession(days).step(days[0], undeclared, [], run_id="x")
        guessed = True
    except ValueError:
        guessed = False
    return dict(finding="A02 every absence mapped to structural",
                state=FIXED if masks[1][1] and not guessed else PRESENT,
                detail=dict(masks=masks, absence_type_inferred_silently=guessed))


def a03_a04_seal(tmp: Path) -> dict:
    store = RunStore(tmp / "a03.sqlite")
    run = store.begin(dict(mode="probe", start="2020-01-01", end="2020-01-01"))
    store.put(run, _point(run, "2020-01-01"))
    store.finish(run, ["2020-01-01"], requires_report=True)
    try:
        store.put(run, _point(run, "2099-12-31"))
        accepts_out_of_range = True
    except ValueError:
        accepts_out_of_range = False
    complete_without_report = any(r["status"] == "complete" for r in store.runs())
    store.report(run, {"v": 1})
    store.report(run, {"v": 2})
    revisions = store.report_revisions(run)
    overwrote = len(revisions) == 1
    return dict(finding="A03/A04 run sealing and report finalisation",
                state=FIXED if not (accepts_out_of_range or complete_without_report
                                    or overwrote) else PRESENT,
                detail=dict(complete_accepts_out_of_range=accepts_out_of_range,
                            complete_without_report=complete_without_report,
                            report_overwrite=overwrote,
                            revisions=[r["revision"] for r in revisions]))


def a05_state_bins() -> dict:
    """A05: does a production state-bin assignment move when the future moves?"""
    from seraph.features.jump_extraction import _bucket, state_variable
    rng = np.random.default_rng(3)
    base = rng.normal(size=40)
    extended = np.concatenate([base, rng.normal(size=20) + 5])

    production = {}
    for label, kwargs in (("train_prefix", dict(basis="train_prefix", train=30)),
                          ("trailing_window", dict(basis="trailing_window",
                                                   window=25, min_history=8))):
        before = state_variable(base, base, n_quantiles=5, **kwargs)["s_t"]
        after = state_variable(extended, extended, n_quantiles=5, **kwargs)["s_t"]
        production[label] = int((before != after[:base.size]).sum())

    # The deprecated whole-array path is retained for artefact reproduction and
    # is expected to still leak; that is not the production behaviour.
    legacy = int((_bucket(base, 5) != _bucket(extended, 5)[:base.size]).sum())
    return dict(finding="A05 whole-array state quantiles change past bins",
                state=FIXED if all(v == 0 for v in production.values()) else PRESENT,
                detail=dict(production_bins_changed_by_future_append=production,
                            legacy_full_sample_bins_changed=legacy,
                            note="the legacy _bucket path is deprecated, marked "
                                 "non-causal and kept only to reproduce pre-FIX04 "
                                 "artefacts"))


def a13_journal_noop(tmp: Path) -> dict:
    store = RunStore(tmp / "a13.sqlite")
    run = store.begin({"mode": "probe"})
    args = dict(alert_id="alert", action="none", decomposition=(0.1, 0.2, 0.3),
                at="2020-01-01T15:30:00+05:30")
    store.action(run, "r1", "regulator", "create", **args)
    try:
        result = store.action(run, "r2", "regulator", "update",
                              alert_id="alert", action="none")
        detail = dict(ok=True, result=result,
                      journal_length=len(store.action_log(run).journal()))
        state = FIXED
    except Exception as exc:                                         # noqa: BLE001
        detail = dict(ok=False, error=f"{type(exc).__name__}: {exc}")
        state = PRESENT
    return dict(finding="A13 no-op journal update raises IntegrityError",
                state=state, detail=detail)


def a14_classification() -> dict:
    import seraph.universe.instrument_type as it
    present = it._ISIN_CSV.exists()
    accepts_all = not it.equity_symbols()
    return dict(finding="A14 missing ISIN file makes is_equity accept everything",
                state=PRESENT if accepts_all or not hasattr(it, "classification_status")
                else FIXED,
                detail=dict(isin_file_present=present,
                            symbols_loaded=len(it.equity_symbols())))


def static_findings() -> list[dict]:
    """Findings verified by inspecting a marker in a source file.

    `marker_means` says what finding the marker's PRESENCE indicates, so the
    evidence file never leaves a bare boolean for a reader to interpret.
    """
    checks = [
        ("A06 validation_results key lacks table/design identity",
         "seraph/store/schema.sql",
         "PRIMARY KEY (pillar_subset, reconciliation_mode, xi_mode, epoch)", PRESENT,
         "the primary key still omits table_id, the preregistration hash and any "
         "evaluation-run identity, so Table A and Table B rows collide"),
        ("A08 Hawkes writer stores no fitted parameters and a constant flag",
         "scripts/write_hawkes_production.py", '"alpha_beta": None', PRESENT,
         "fitted parameters are discarded and the sector flag is hardcoded 'none'"),
        ("A09 backfill selects the latest universe snapshot",
         "scripts/write_hawkes_production.py",
         "FROM universe_snapshots ORDER BY rebalance_date DESC LIMIT 1", PRESENT,
         "historical windows are processed against today's membership"),
        ("A11 legacy datasource claims caching it does not apply",
         "seraph/dashboard/datasource.py", "@st.cache_data", FIXED,
         "the decorator the old docstring claimed is now really applied"),
        ("A11b legacy datasource mixes independent latest rows",
         "seraph/dashboard/datasource.py", "date <= $1 ORDER BY date DESC LIMIT 1", FIXED,
         "component reads are bounded by one resolved as_of date"),
        ("A12 bridge pending latch with no timeout or draft preservation",
         "seraph/dashboard/console_component/bridge.js", "pending=false", PRESENT,
         "a lost response leaves `pending` latched and blocks every later request"),
        ("A12b bridge has a bounded timeout and same-id retry",
         "seraph/dashboard/console_component/bridge.js", "REQUEST_TIMEOUT_MS", FIXED,
         "the in-flight record times out, offers retry and preserves drafts"),
    ]
    out = []
    for finding, path, marker, marker_means, note in checks:
        text = (ROOT / path).read_text(encoding="utf-8", errors="ignore")
        found = marker in text
        state = marker_means if found else (FIXED if marker_means == PRESENT else PRESENT)
        out.append(dict(finding=finding, state=state, detail=dict(
            path=path, marker=marker, marker_present=found,
            marker_means=marker_means, note=note)))
    return out


def ports() -> dict:
    out = {}
    for port in (5433, 5434, 8512):
        sock = socket.socket()
        sock.settimeout(0.6)
        out[str(port)] = sock.connect_ex(("127.0.0.1", port)) == 0
        sock.close()
    return out


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        tmp = Path(temp)
        findings = [a01_special_session_replay(tmp), a02_transient_absence(),
                    a03_a04_seal(tmp), a05_state_bins(), a13_journal_noop(tmp),
                    a14_classification()]
    findings.extend(static_findings())
    record = dict(generated=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                  note="Re-probe of the 2026-10-16 audit findings against the "
                       "current checkout. Temporary SQLite stores only; no source "
                       "database, persisted run or research artifact was modified.",
                  findings=findings, localhost_ports=ports())
    target = ROOT / "docs" / "evidence" / "REVERIFY-2026-10-16.json"
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
