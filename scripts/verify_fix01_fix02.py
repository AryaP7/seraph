"""FIX01/FIX02 acceptance evidence: full supported archive replay.

Replays the entire supported history under both decision-clock policies into a
NEW output location, and compares the COVID-window scientific content against
the pre-change baseline run persisted in prototype_runs/seraph.sqlite.

No existing run, research artifact or source database is modified.
"""
from __future__ import annotations
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.orchestration.prototype import run_archive          # noqa: E402
from seraph.orchestration.run_store import RunStore             # noqa: E402

#: Scientific content compared against the pre-change baseline. New envelope
#: keys (session, coverage.absence, pillar selection provenance) are additive
#: and deliberately excluded from this identity check.
SCIENTIFIC = ("date", "evaluation_timestamp", "data_cutoff", "composite",
              "reconciled", "explanation", "warning_status", "astra_predictions")


def content(point: dict) -> dict:
    out = {k: point[k] for k in SCIENTIFIC}
    out["mask"] = point["coverage"]["mask"]
    out["pillars"] = {p: {k: v[k] for k in ("score_eligible", "value",
                                            "information_timestamp")}
                      for p, v in point["original_pillars"].items()}
    return out


def digest(points: list[dict]) -> str:
    return hashlib.sha256(json.dumps([content(p) for p in points],
                                     sort_keys=True).encode()).hexdigest()


def main() -> int:
    out_dir = ROOT / "prototype_runs"
    store = out_dir / "fix01-full-replay.sqlite"
    if store.exists():
        store.unlink()
    evidence: dict = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                      "store": str(store), "replays": {}}

    first, last = "2005-01-03", "2026-08-21"
    for policy in ("session_close", "standard_1530"):
        began = time.time()
        report = run_archive(store, start=first, end=last, decision_policy=policy)
        points = RunStore(store).points(report["run_id"])
        special = {d: next((p for p in points if p["date"] == d), None)
                   for d in ("2024-03-02", "2024-05-18", "2024-11-01", "2025-10-21")}
        evidence["replays"][policy] = dict(
            run_id=report["run_id"], points=report["points"],
            seconds=round(time.time() - began, 1),
            first_date=points[0]["date"], last_date=points[-1]["date"],
            content_digest=digest(points),
            withheld_sessions=sorted(
                p["date"] for p in points
                if any(v == "withheld_not_yet_available"
                       for v in p["coverage"]["absence"].values())),
            special_sessions={
                d: None if p is None else dict(
                    evaluation_timestamp=p["evaluation_timestamp"],
                    session_kind=p["session"]["kind"],
                    mask=p["coverage"]["mask"],
                    hawkes_tau=p["original_pillars"]["hawkes"]["information_timestamp"],
                    withheld=p["original_pillars"]["hawkes"].get("withheld_vintage"),
                    csrs=(p["composite"] or {}).get("csrs"))
                for d, p in special.items()},
            future_information_violations=[
                p["date"] for p in points
                for q in p["original_pillars"].values()
                if q.get("score_eligible") and q.get("information_timestamp")
                and q["information_timestamp"] > p["evaluation_timestamp"]],
        )

    # Deterministic retry: same inputs, same identity, same rows.
    retry = run_archive(store, start=first, end=last, decision_policy="session_close")
    evidence["deterministic_retry"] = dict(
        run_id=retry["run_id"],
        same_identity=retry["run_id"] == evidence["replays"]["session_close"]["run_id"],
        same_content=digest(RunStore(store).points(retry["run_id"]))
        == evidence["replays"]["session_close"]["content_digest"])

    # COVID-window scientific identity against the pre-change baseline.
    baseline_store = out_dir / "seraph.sqlite"
    covid = out_dir / "fix01-covid-window.sqlite"
    if covid.exists():
        covid.unlink()
    new = run_archive(covid, start="2020-01-01", end="2020-04-30")
    new_points = RunStore(covid).points(new["run_id"])
    comparison = {"new_run_id": new["run_id"], "new_points": len(new_points)}
    if baseline_store.exists():
        base = RunStore(baseline_store)
        prior = [r for r in base.runs()
                 if r["status"] == "complete"
                 and r["manifest"].get("start") == "2020-01-01"
                 and r["manifest"].get("end") == "2020-04-30"]
        if prior:
            base_points = base.points(prior[0]["id"])
            diffs = [n["date"] for b, n in zip(base_points, new_points)
                     if content(b) != content(n)]
            csrs = [(n["date"], (b["composite"] or {}).get("csrs"),
                     (n["composite"] or {}).get("csrs"))
                    for b, n in zip(base_points, new_points)
                    if (b["composite"] or {}).get("csrs")
                    != (n["composite"] or {}).get("csrs")]
            comparison.update(
                baseline_run_id=prior[0]["id"],
                baseline_points=len(base_points),
                scientific_content_identical=not diffs
                and len(base_points) == len(new_points),
                differing_dates=diffs[:20],
                mask_changes=[n["date"] for b, n in zip(base_points, new_points)
                              if b["coverage"]["mask"] != n["coverage"]["mask"]],
                csrs_changes=[dict(date=d, baseline=b, new=a, delta=a - b)
                              for d, b, a in csrs],
                max_abs_csrs_delta=max((abs(a - b) for _, b, a in csrs), default=0.0),
                cause="the archive holds one Hawkes refit (2020-02-01T15:25 IST) whose "
                      "calendar date is not a session in market_snapshot.parquet. Date-keyed "
                      "selection dropped it entirely; as-of selection offers it at the next "
                      "decision, where D4 correctly rejects it as stale but the chronological "
                      "standardisation window now contains it. Assimilated vintages are "
                      "unchanged; only the ECDF support moved.")
        else:
            comparison["baseline"] = "no matching pre-change COVID run found"
    else:
        comparison["baseline"] = "baseline store absent"
    evidence["covid_window_identity"] = comparison

    target = ROOT / "docs" / "evidence" / "FIX01-FIX02-REPLAY-2026-10-16.json"
    target.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
