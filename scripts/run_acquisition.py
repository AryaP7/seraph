#!/usr/bin/env python
"""Bring SERAPH's inputs up to date: acquire fresh EOD, then re-derive.

    python scripts/run_acquisition.py              # acquire and re-derive
    python scripts/run_acquisition.py --status     # what the last run did
    python scripts/run_acquisition.py --sessions 3 # bound the backfill
    python scripts/run_acquisition.py --dry-run    # what it would fetch

Three things that are one logical unit -- "make the inputs current" -- and so
live in one step rather than three the scheduler has to sequence:

1. **Acquire** the sessions the corpus is missing, from NSE's public bhavcopy
   archive. No credentials: Kite Connect is needed for *intraday* bars, not
   end-of-day data.
2. **Re-flag the universe** for the years that gained sessions. A fresh
   `daily_prices` row has `universe_member_flag = false` until C3 applies the
   current snapshot's membership, and the market panel is built only from
   flagged rows -- so without this the new sessions exist and are invisible.
   This was the actual integration gap: acquisition alone changed nothing
   downstream.
3. **Rebuild the market snapshot** the prediction engine reads.

Steps 2 and 3 run when new sessions arrive or a prior derivation is pending.
The published cutoff also detects a crash before pending status was saved.

The snapshot is rebuilt into `research_data/current/`, NOT over
`research_data/market_snapshot.parquet`. That file is the input
`research_results/v1` was produced from and its sha256 is in that run's
manifest; rebuilding it in place would make the frozen experiment
unreproducible. `operational.snapshot_path()` prefers the rebuilt one.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
import os
import uuid
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seraph.shared_types import IST, ist_timestamp  # noqa: E402

DEFAULT_STATUS = ROOT / "prototype_runs" / "acquisition-status.json"


def status_path() -> Path:
    import os

    return Path(os.environ.get("SERAPH_ACQUISITION_STATUS",
                               str(DEFAULT_STATUS)))


def _stamp() -> str:
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


def _write(report: dict) -> None:
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    os.replace(temporary, path)


def _published_cutoff():
    """Only a checked pair of snapshot/manifest bytes is a derived input."""
    current = ROOT / 'research_data/current'
    try:
        pointer = current / 'active.json'
        info = json.loads(pointer.read_text()) if pointer.exists() else None
        folder = current / 'versions' / info['version'] if info else current
        manifest_path = folder / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        digest = hashlib.sha256((folder / 'market_snapshot.parquet').read_bytes()).hexdigest()
        if digest != manifest['files']['market_snapshot.parquet']:
            return None
        if info and (digest != info['sha256'] or
                     hashlib.sha256(manifest_path.read_bytes()).hexdigest() != info['manifest_sha256']):
            return None
        return manifest['to']
    except (OSError, ValueError, KeyError):
        return None


def status() -> dict:
    path = status_path()
    if not path.is_file():
        return dict(ran=False, path=str(path), note=(
            "acquisition has never run in this installation. "
            "`python scripts/run_acquisition.py` runs it; "
            "`run_market_jobs.py` runs it as the first daily step."))
    try:
        return dict(ran=True, path=str(path),
                    **json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        return dict(ran=False, path=str(path),
                    note=f"the acquisition status file is unreadable: {exc}")


def _step(label: str, argv: list[str], *, timeout: int) -> dict:
    """One re-derivation step, captured rather than allowed to abort the rest."""
    started = _stamp()
    try:
        done = subprocess.run([sys.executable, *argv], cwd=ROOT,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return dict(step=label, ok=False, started=started,
                    error=f"exceeded {timeout}s")
    except Exception as exc:                                # noqa: BLE001
        return dict(step=label, ok=False, started=started,
                    error=f"{type(exc).__name__}: {exc}"[:200])
    tail = (done.stdout or done.stderr or "").strip().splitlines()
    return dict(step=label, ok=done.returncode == 0, started=started,
                finished=_stamp(), exit_code=done.returncode,
                output=tail[-5:])


def _research_dsn() -> str:
    from seraph.store.bootstrap import DEFAULT_DSN

    return DEFAULT_DSN


def run(*, limit: int | None = None, refresh: bool = False) -> dict:
    from seraph.ingestion import bhavcopy_client

    previous = status()
    acquisition = asyncio.run(bhavcopy_client.acquire(limit=limit,
                                                      refresh=refresh))
    report = dict(generated=_stamp(), acquisition=acquisition,
                  derived=[], ok=bool(acquisition.get("ok")),
                  acquired=bool(acquisition.get("acquired")))

    if acquisition.get("blocked"):
        report.update(ok=False, note=acquisition["blocked"],
                      pending_derived_sessions=previous.get('pending_derived_sessions', []))
        _write(report)
        return report

    stored = acquisition.get("stored_sessions") or []
    pending = set(previous.get("pending_derived_sessions") or [])
    # Recover older status records that predate the explicit pending field.
    if any(not s.get('ok') for s in previous.get('derived', [])):
        pending.update((previous.get('acquisition') or {}).get('stored_sessions') or [])
    pending.update(stored)
    published = _published_cutoff()
    latest = acquisition.get('latest_after')
    if latest and (published is None or published < latest):
        pending.add(latest)
    report.update(corpus_cutoff=latest, snapshot_cutoff=published)
    if not pending:
        report["note"] = (
            "executed, acquired nothing. Every requested session was already "
            "stored or not published (a holiday, or the file is not out yet). "
            "Nothing downstream is re-derived, because re-deriving unchanged "
            "inputs produces identical files.")
        _write(report)
        return report

    # Only the years that gained sessions. A full 2005-2026 rebuild re-reads
    # every rebalance for no reason.
    report['pending_derived_sessions'] = sorted(pending)
    report['corpus_cutoff'] = acquisition.get('latest_after')
    _write(report)  # Crash recovery starts before the first derived operation.
    years = sorted({day[:4] for day in stored} | {day[:4] for day in pending})
    if published and latest and published < latest:
        years = sorted(set(years) | {str(y) for y in
                       range(int(published[:4]), int(latest[:4]) + 1)})
    steps = [
        _step(f"universe flags {year}",
              ["scripts/build_universe.py", "--from", year, "--to", year],
              timeout=1800)
        for year in years
    ]
    version = Path("research_data/current/versions") / uuid.uuid4().hex
    if all(s['ok'] for s in steps):
        steps.append(_step(
        "market snapshot",
        ["scripts/snapshot_research_data.py",
         "--out", str(version),
         "--source-dsn", _research_dsn()],
        timeout=1800))
    if all(s['ok'] for s in steps):
        try:
            manifest_path = ROOT / version / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            snapshot = ROOT / version / 'market_snapshot.parquet'
            digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            if digest != manifest['files']['market_snapshot.parquet']:
                raise ValueError('snapshot bytes do not match manifest')
            if manifest['to'] != acquisition.get('latest_after'):
                raise ValueError('derived cutoff differs from corpus cutoff')
            from seraph.prediction.operational import _snapshot_frame
            frame = _snapshot_frame(snapshot)
            if str(frame['date'].iloc[-1])[:10] != manifest['to']:
                raise ValueError('snapshot dates do not match manifest')
            pointer = ROOT / 'research_data/current/active.json'
            temporary = pointer.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(
                version=version.name, sha256=digest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                cutoff=manifest['to'])), encoding='utf-8')
            os.replace(temporary, pointer)
            report.update(pending_derived_sessions=[], snapshot_cutoff=manifest['to'],
                          snapshot_sha256=digest)
        except (OSError, ValueError, KeyError) as exc:
            steps.append(dict(step='publish snapshot', ok=False, error=str(exc)))

    report["derived"] = steps
    report["ok"] = report["ok"] and all(s["ok"] for s in steps)
    report["note"] = (
        f"acquired {len(stored)} session(s) through "
        f"{acquisition.get('latest_after')}, then re-derived the universe "
        f"flags for {', '.join(years)} and the market snapshot. The "
        f"prediction step reads that snapshot.")
    if not all(s["ok"] for s in steps):
        report["note"] += (
            " A re-derivation step FAILED, so the snapshot may not reflect "
            "the newly stored sessions and the prediction that follows may "
            "still be for an earlier date.")
    _write(report)
    return report


def render(report: dict) -> str:
    acquisition = report.get("acquisition") or {}
    lines = [f"ACQUISITION  {report.get('generated', '')}"]
    if report.get("note"):
        lines.append(f"  {report['note']}")
    lines.append("")
    lines.append(f"  corpus {acquisition.get('latest_before')} -> "
                 f"{acquisition.get('latest_after')}  "
                 f"(expected {acquisition.get('expected')})")
    sessions = acquisition.get("sessions") or []
    if sessions:
        import collections

        counts = collections.Counter(s["status"] for s in sessions)
        lines.append("  sessions: " + ", ".join(
            f"{status} {count}" for status, count in sorted(counts.items())))
        for item in sessions:
            if item["status"] != "stored":
                lines.append(f"    [{item['status']}] {item['day']}: "
                             f"{str(item.get('detail'))[:110]}")
    if acquisition.get("rows_written"):
        lines.append(f"  rows written: {acquisition['rows_written']:,}")
    for step in report.get("derived", ()):
        mark = "ok  " if step["ok"] else "FAIL"
        lines.append(f"  [{mark}] {step['step']}")
        if not step["ok"]:
            lines.append(f"         {step.get('error') or step.get('output')}")
    lines.append("")
    lines.append("  EXECUTED and ACQUIRED FRESH DATA are separate: "
                 f"ok={report.get('ok')} acquired={report.get('acquired')}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true",
                        help="report the last run; acquire nothing")
    parser.add_argument("--sessions", type=int, default=None,
                        help="acquire at most this many missing sessions")
    parser.add_argument("--refresh", action="store_true",
                        help="re-fetch even if the raw file is cached")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be fetched; fetch nothing")
    args = parser.parse_args(argv)

    if args.status:
        saved = status()
        if not saved.get("ran"):
            print(saved["note"])
            return 1
        print(render(saved))
        return 0

    if args.dry_run:
        import asyncpg

        from seraph.ingestion.bhavcopy_client import (
            latest_stored_session,
            sessions_to_acquire,
        )
        from seraph.operations.schedule import expected_session

        async def peek():
            connection = await asyncpg.connect(_research_dsn(), timeout=10)
            try:
                return await latest_stored_session(connection)
            finally:
                await connection.close()

        try:
            latest = asyncio.run(peek())
        except Exception as exc:                            # noqa: BLE001
            print(f"the research database is unreachable: {exc}")
            return 2
        expected = expected_session()
        days = sessions_to_acquire(latest_stored=latest, expected=expected,
                                   limit=args.sessions)
        print(f"corpus ends {latest}; expected session {expected}")
        print(f"{len(days)} session(s) would be fetched"
              + (f": {days[0]} .. {days[-1]}" if days else ""))
        print("A day that turns out to be an exchange holiday comes back "
              "not_published, which costs one request and is not a failure.")
        return 0

    report = run(limit=args.sessions, refresh=args.refresh)
    print(render(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
