#!/usr/bin/env python3
# C8/C9 orchestration — T06 acceptance on the real verified archive.
"""Replay the archive through both orchestration paths and diff them.

T06's gate is "raw replay and incremental results agree on supported
configuration". A synthetic fixture can show the adapter translates; only the
real archive shows the timestamp service reproduces the results the project
already has. This script builds each session's `originals` exactly the way
`run_archive()` does — same as-of Hawkes vintage selection, same RMT
structural/transient rule, same standing Hamilton exclusion — runs it through
`InferenceSession.step()` and through `InferenceService`, and reports every
field that differs.

Read-only: it touches the archive files and writes one JSON report. No
database, no store.

Run:
  python scripts/verify_t06_equivalence.py --start 2020-01-01 --end 2020-06-30 \
      --out docs/evidence/T06-EQUIVALENCE-2026-10-17.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seraph.live.archive_adapter import ArchiveReplay, equivalence_report  # noqa: E402
from seraph.live.inference import SERVICE_VERSION  # noqa: E402
from seraph.market_calendar import SessionCalendar  # noqa: E402
from seraph.orchestration.prototype import InferenceSession, load_archive  # noqa: E402


def build_originals(day, rmap, hmap, vintages, cursor, calendar,
                    decision, rmt_first_date):
    """The same per-session input `run_archive()` constructs, nothing added."""
    while cursor < len(vintages) and vintages[cursor][0] <= decision:
        cursor += 1
    last_hawk = vintages[cursor - 1][1] if cursor else None
    r = rmap.get(day)
    h = hmap.get(day)
    tau_daily = calendar.close_timestamp(day)

    hawkes_entry = dict(
        model="original discrete intraday Hawkes",
        origin="verified fitted archive",
        score_eligible=last_hawk is not None,
        value=(last_hawk["branching_ratio_n"]
               / (1 - last_hawk["branching_ratio_n"])) if last_hawk else None,
        information_timestamp=(last_hawk["information_timestamp"]
                               if last_hawk else None),
        reason="no fitted intraday estimate available at this decision time")
    if last_hawk is None:
        hawkes_entry.update(absence="structural",
                            absence_reason="insufficient_history")

    rmt_entry = dict(model="original cross-sectional RMT",
                     origin="verified fitted archive",
                     score_eligible=r is not None,
                     value=r["lam1_share"] if r else None,
                     information_timestamp=tau_daily)
    if r is None:
        structural = rmt_first_date is None or day < rmt_first_date
        rmt_entry.update(
            absence="structural" if structural else "transient",
            absence_reason=("insufficient_history" if structural
                            else "estimation_failed"))

    hamilton_entry = dict(
        model="original multivariate TVTP Hamilton",
        origin="causal research archive NOT_PRODUCTION",
        score_eligible=False, value=None, information_timestamp=tau_daily,
        absence="structural", absence_reason="no_data_coverage",
        exclusion="standing research decision (NOT_PRODUCTION)")
    return ({"hawkes": hawkes_entry, "rmt": rmt_entry,
             "hamilton": hamilton_entry}, cursor, h)


def main(start: str, end: str, policy: str, out: str | None) -> int:
    market, rmt, hawkes, ham, _forecast, _sources, _manifest = load_archive()
    dates = [d for d in market.date.tolist() if d <= end]
    if not dates:
        print("[t06] requested range is empty")
        return 1
    calendar = SessionCalendar(session_dates=frozenset(market.date.tolist()))
    replay = ArchiveReplay(tuple(market.date.tolist()), decision_policy=policy)
    # Both paths must run on the SAME decision clock. Letting InferenceSession
    # build its own defaults it back to `session_close`, and the comparison
    # then measures the policy difference instead of the orchestration — which
    # is how the first run of this script reported 449 phantom disagreements
    # under `standard_1530`.
    session = InferenceSession(market.date.tolist(),
                               decision_clock=replay.clock)

    rmap = rmt.set_index("date").to_dict("index")
    hmap = ham.set_index("date").to_dict("index")
    vintages = sorted(((row["information_timestamp"], row)
                       for row in hawkes.to_dict("records")),
                      key=lambda item: item[0])
    rmt_first_date = min(rmap) if rmap else None

    cursor = 0
    compared, disagreements = 0, []
    warning_only = 0
    for day in dates:
        decision = replay.clock.decision_timestamp(day)
        originals, cursor, _h = build_originals(
            day, rmap, hmap, vintages, cursor, calendar, decision,
            rmt_first_date)
        report = equivalence_report(session, replay, day, originals)
        if day < start:
            continue
        compared += 1
        if not report["agrees"]:
            disagreements.append(report)
        elif set(report["archive_warnings"]) != set(report["service_warnings"]):
            warning_only += 1

    print(f"[t06] sessions compared: {compared} ({start}..{end}, policy {policy})")
    print(f"[t06] disagreements on reconciled state or composite: "
          f"{len(disagreements)}")
    print(f"[t06] sessions agreeing numerically but differing in warnings: "
          f"{warning_only}")
    for report in disagreements[:5]:
        print(f"  {report['day']}: {report['differences'][:3]}")

    summary = dict(
        generated="T06 / audit finding R01 — archive equivalence",
        service_version=SERVICE_VERSION, decision_policy=policy,
        start=start, end=end, sessions_compared=compared,
        disagreements=len(disagreements),
        warning_only_differences=warning_only,
        first_disagreements=disagreements[:10],
        comparison_basis=(
            "same date cadence, same decision clock, same archive inputs. "
            "Warning lists are reported but not required to match, and the "
            "differences were categorised rather than waved past: (1) an "
            "absence is worded with its typed absence_reason by the service "
            "and with the adapter's free-text reason by the archive path; "
            "(2) a carried-forward pillar is omitted from the batch by the "
            "service, so C8's STALE_OBSERVATION and the re-standardisation's "
            "PARTIAL_COVERAGE echo do not recur. Neither changes a number, "
            "and the mask exclusion that NOISE_SATURATED announced is "
            "re-reported by the service from the resulting state."),
        qualification=("Equivalence on replayed archive inputs. It does not "
                       "establish live operation, which needs T07 durability "
                       "and T08 delivery, and it is not predictive evidence."))
    if out:
        Path(out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"[t06] wrote {out}")
    return 0 if not disagreements else 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2020-06-30")
    ap.add_argument("--policy", default="session_close",
                    choices=["session_close", "standard_1530"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    raise SystemExit(main(a.start, a.end, a.policy, a.out))
