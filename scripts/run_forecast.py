#!/usr/bin/env python3
# Incremental prospective forecasting (T04 / audit R12, C10)
"""Issue the forecast for ONE information cutoff and record it prospectively.

The historical experiment (`scripts/run_prediction_experiment.py`) already
produces 75,054 walk-forward rows with their realised labels. That is a
retrospective artefact: every row knows its outcome because the outcome had
happened before the file was written. C10's gap is the other thing --
"incremental forecast publication and an immutable dated prospective record
are not integrated into normal operation".

This is that path. For one cutoff it reads the saved walk-forward output,
takes the row for that date, and writes it into the append-only ledger
(migration 004) WITHOUT its label. The outcome is attached later, by
`--settle`, and only once the horizon has actually elapsed.

Why reuse the saved walk-forward rather than refit here
-------------------------------------------------------
The experiment's own `fit_status` column already distinguishes `forecast`
from `insufficient_training` and from a failed fit, and its walk-forward
discipline is what makes a row out-of-sample. Refitting independently in
this script would create a second, divergeable idea of what the model said
on a date -- the same mistake `_simulate_steps` avoids by calling the real
simulator. So this script's job is publication and maturity bookkeeping, not
estimation.

The consequence, stated plainly: a cutoff this script can publish is one the
experiment has already walked forward to. Issuing a forecast for a date
beyond the experiment's last run means re-running the experiment first. That
is a real limitation of the current wiring and it is reported rather than
papered over with a fresh ad-hoc fit.

Run:
    python scripts/run_forecast.py --as-of 2026-08-21
    python scripts/run_forecast.py --settle            # attach matured outcomes
    python scripts/run_forecast.py --status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seraph.live.store import LiveStore, StoreError                # noqa: E402
from seraph.shared_types import IST, ist_timestamp                 # noqa: E402

DEFAULT_RESULTS = ROOT / "research_results" / "v1_verified"

#: Calendar days allowed per horizon session when computing `matures_after`.
#: Deliberately generous: the horizon is in SESSIONS and this converts to a
#: wall-clock date, so erring long means an outcome is attached a little late
#: rather than a little early. Attaching early is the failure that matters --
#: it scores a forecast against a window that has not finished.
CALENDAR_DAYS_PER_SESSION = 1.6


def _stamp(moment: datetime) -> str:
    return ist_timestamp(moment.replace(microsecond=0))


def load_rows(results: Path) -> list[dict]:
    """The saved walk-forward predictions, as plain dicts."""
    import polars as pl

    path = results / "predictions.parquet"
    if not path.is_file():
        raise FileNotFoundError(
            f"no walk-forward output at {path}. Run "
            f"scripts/run_prediction_experiment.py first: this script "
            f"publishes what that produced and does not fit independently")
    return pl.read_parquet(path).to_dicts()


def artefact_id(results: Path) -> str:
    """Identity of the fitted artefact these forecasts came from.

    Content, not a label: a different fit over the same cutoff is a
    genuinely different forecast and must get its own ledger row.
    """
    audit = results / "fit_audit.json"
    if audit.is_file():
        return "fit:" + hashlib.sha256(audit.read_bytes()).hexdigest()[:24]
    path = results / "predictions.parquet"
    return "fit:" + hashlib.sha256(path.read_bytes()).hexdigest()[:24]


#: Horizon in sessions, read off the target name's trailing digits.
#: The experiment's targets are `loss10_15` (a 10% fall over 15 sessions) and
#: `onset15` (onset within 15), so the horizon is the LAST number in the
#: name, not the part after the last underscore -- splitting on '_' gives
#: 'onset15' back whole and `int()` raises on it.
_HORIZON_RE = re.compile(r"(\d+)(?!.*\d)")


def _horizon_of(target: str, default: int = 15) -> int:
    found = _HORIZON_RE.search(target or "")
    return int(found.group(1)) if found else default


def _as_date(value) -> str:
    if isinstance(value, str):
        return value[:10]
    return value.strftime("%Y-%m-%d")


def issue(store: LiveStore, as_of: str, *, results: Path) -> dict:
    """Publish every model's forecast for one cutoff."""
    rows = [r for r in load_rows(results) if _as_date(r["date"]) == as_of]
    if not rows:
        available = sorted({_as_date(r["date"]) for r in load_rows(results)})
        return dict(as_of=as_of, issued=[], skipped=[],
                    reason=(f"the saved walk-forward has no row for {as_of}. "
                            f"It covers {available[0]}..{available[-1]}; a "
                            f"later cutoff needs the experiment re-run "
                            f"first"))
    fit = artefact_id(results)
    issued, skipped = [], []
    for row in rows:
        horizon = _horizon_of(str(row.get("target", "")))
        matures = (datetime.fromisoformat(f"{as_of}T00:00:00+05:30")
                   + timedelta(days=round(horizon * CALENDAR_DAYS_PER_SESSION)))
        status = str(row.get("fit_status") or "unknown")
        if row.get("probability") is None:
            # A model that could not fit at this cutoff is recorded as such.
            # An abstention is a result; silently omitting it would make the
            # ledger look more confident than the system was.
            skipped.append(dict(model=row["model"], target=row["target"],
                                fit_status=status))
        written = store.record_forecast(
            target=str(row["target"]), model=str(row["model"]), as_of=as_of,
            artefact_id=fit, horizon=horizon,
            matures_after=_as_date(matures),
            fit_status=status,
            probability=(float(row["probability"])
                         if row.get("probability") is not None else None),
            threshold=(float(row["threshold"])
                       if row.get("threshold") is not None else None),
            alarm=(bool(row["alarm"]) if row.get("alarm") is not None else None),
            inputs_hash=fit,
            detail=dict(issue_mode="historical_import", train_end=row.get("train_end"),
                        source=str(results.relative_to(ROOT))))
        issued.append(dict(model=row["model"], target=row["target"],
                           stored=written["stored"],
                           matures_after=written["matures_after"]))
    return dict(as_of=as_of, artefact_id=fit, issued=issued, skipped=skipped,
                note=("labels are NOT written at issue time; run --settle "
                      "once each horizon has elapsed"))


def settle(store: LiveStore, *, results: Path, now: str | None = None) -> dict:
    """Attach realised outcomes to every forecast whose horizon has elapsed.

    The label comes from the same saved walk-forward output, which carries
    the realised `label` for historical dates. The store refuses any write
    before `matures_after`, so a label that exists in the file but whose
    window has not elapsed in wall-clock terms is still rejected -- the guard
    is the store's, not this script's.
    """
    moment = now or _stamp(datetime.now(IST))
    labels = {}
    for row in load_rows(results):
        if row.get("label") is not None:
            labels[(str(row["target"]), str(row["model"]),
                    _as_date(row["date"]))] = float(row["label"])
    settled, waiting, unlabelled = [], [], []
    for pending in store.forecasts(pending_only=True, limit=10_000):
        key = (pending["target"], pending["model"], pending["as_of"])
        if key not in labels:
            unlabelled.append(key)
            continue
        try:
            store.attach_outcome(
                target=pending["target"], model=pending["model"],
                as_of=pending["as_of"], artefact_id=pending["artefact_id"],
                outcome=labels[key], now=moment)
            settled.append(dict(zip(("target", "model", "as_of"), key)))
        except StoreError as exc:
            waiting.append(dict(zip(("target", "model", "as_of"), key),
                                reason=str(exc)[:120]))
    return dict(now=moment, settled=len(settled), waiting=len(waiting),
                unlabelled=len(unlabelled), detail=dict(
                    settled=settled[:10], waiting=waiting[:5]),
                note=("`waiting` are forecasts whose horizon has not elapsed. "
                      "`unlabelled` have no realised label available yet"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", help="information cutoff, YYYY-MM-DD")
    parser.add_argument("--settle", action="store_true",
                        help="attach outcomes to matured forecasts")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--store", type=Path,
                        default=ROOT / "prototype_runs" / "live.sqlite")
    parser.add_argument("--now", help="override the clock (testing)")
    args = parser.parse_args(argv)

    store = LiveStore(args.store)
    if args.status:
        rows = store.forecasts(limit=20)
        print(json.dumps(dict(
            forecasts=rows,
            pending=len(store.forecasts(pending_only=True, limit=10_000)),
            note=("`outcome` is null until the horizon has elapsed; that is "
                  "the ledger being prospective, not missing data")),
            indent=2, default=str))
        return 0
    if args.settle:
        print(json.dumps(settle(store, results=args.results, now=args.now),
                         indent=2, default=str))
        return 0
    if not args.as_of:
        parser.error("one of --as-of, --settle or --status is required")
    print(json.dumps(issue(store, args.as_of, results=args.results),
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
