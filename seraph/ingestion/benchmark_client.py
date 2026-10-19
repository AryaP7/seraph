# C2 — Ingestion (FR41, FR54): the official Nifty 500 benchmark series.
"""The official index, for the FR41 historical overlay and the FR54 check.

FR41 asks for CSRS overlaid on benchmark Nifty 500 returns to support visual
back-testing. The console's history payload carried CSRS alone, so the chart
was a CSRS line and not the overlay the requirement describes -- the audit
recorded that as absent, correctly.

The series itself was already in the repository. `vendor/eod2/src/eod2_data/
daily/nifty 500.csv` is the official NSE index: 3,577 sessions from
2012-02-21, Open/High/Low/Close plus the index P/E. `eod2_client`'s
`discover_symbol_files` deliberately skips it -- "index files have spaces in
their names" -- because it loads EQUITIES into `daily_prices`, and an index is
not a tradeable member of the universe. So it needs its own reader rather
than a change to that filter.

Two things this module refuses to do
------------------------------------
**It does not forward-fill.** The index has its own holidays and the CSRS
archive has its own session set; where they differ the overlay reports a gap.
A chart that quietly interpolates a missing index day is showing a number
nobody published.

**It does not substitute a different index.** FR41 names Nifty 500. If the
file is absent the overlay is unavailable with a reason; Nifty 50 is a
different population and swapping it in would be a silent change of meaning.

The span mismatch is real and must stay visible: the index file begins
2012-02-21 while the daily equity corpus and the CSRS archive begin in 2005.
Overlay requests covering 2005-2012 therefore have a genuine benchmark gap,
and `align()` reports it rather than trimming the CSRS series to hide it.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: FR41 names this index. Not configurable by accident: see the module note.
NIFTY_500 = _REPO_ROOT / "vendor" / "eod2" / "src" / "eod2_data" / "daily" / "nifty 500.csv"

#: What the overlay calls the series on screen, with its provenance.
SERIES_LABEL = "NIFTY 500 (official NSE index close)"
SERIES_SOURCE = "vendor/eod2/src/eod2_data/daily/nifty 500.csv"


@dataclass(frozen=True)
class BenchmarkPoint:
    date: str
    close: float
    #: Simple return against the previous AVAILABLE session in the file, with
    #: that session named. A return across a gap is a multi-day return and
    #: saying so is the difference between a correct chart and a plausible one.
    prev_date: str | None = None
    simple_return: float | None = None
    sessions_spanned: int = 1


def load(path: Path | None = None, *, start: str | None = None,
         end: str | None = None) -> list[BenchmarkPoint]:
    """The index series, oldest first, with per-session simple returns."""
    source = Path(path or NIFTY_500)
    if not source.is_file():
        return []
    rows: list[tuple[str, float]] = []
    with source.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            stamp, raw = (row.get("Date") or "").strip(), (row.get("Close") or "").strip()
            if not stamp or not raw:
                continue
            try:
                close = float(raw)
            except ValueError:
                continue
            if not math.isfinite(close) or close <= 0:
                continue
            if start and stamp < start:
                continue
            if end and stamp > end:
                continue
            rows.append((stamp, close))
    rows.sort()
    out: list[BenchmarkPoint] = []
    for index, (stamp, close) in enumerate(rows):
        if index == 0:
            out.append(BenchmarkPoint(date=stamp, close=close))
            continue
        prev_date, prev_close = rows[index - 1]
        out.append(BenchmarkPoint(
            date=stamp, close=close, prev_date=prev_date,
            simple_return=(close / prev_close) - 1.0,
            sessions_spanned=1))
    return out


def describe(path: Path | None = None) -> dict:
    """Is the benchmark available, and over what span?"""
    series = load(path)
    if not series:
        return dict(available=False, label=SERIES_LABEL, source=SERIES_SOURCE,
                    reason=(f"the official Nifty 500 series is not present at "
                            f"{SERIES_SOURCE}. FR41 names this index; another "
                            f"index is a different population and is not "
                            f"substituted"))
    return dict(available=True, label=SERIES_LABEL, source=SERIES_SOURCE,
                sessions=len(series), first=series[0].date,
                last=series[-1].date,
                convention="simple close-to-close return, not forward-filled")


def align(history, *, path: Path | None = None) -> dict:
    """Join a CSRS history to the benchmark on the SAME dates (FR41).

    `history` is the console's own `[{date, csrs}, ...]`. Returns one row per
    CSRS date, each carrying the benchmark return for that date when the index
    published one, and `benchmark_available=False` when it did not.

    Dates are never moved to find a match and the series is never
    forward-filled: a date the index did not publish is a gap, and the
    summary counts it. Both series keep their own units -- the CSRS is a
    [0,1] score and the benchmark is a return -- so a renderer cannot put
    them on one axis by accident.
    """
    series = {p.date: p for p in load(path)}
    rows, matched, missing = [], 0, []
    for entry in history or ():
        stamp = entry.get("date")
        point = series.get(stamp)
        if point is not None and point.simple_return is not None:
            matched += 1
            rows.append(dict(date=stamp, csrs=entry.get("csrs"),
                             benchmark_close=point.close,
                             benchmark_return=point.simple_return,
                             benchmark_available=True))
        else:
            missing.append(stamp)
            rows.append(dict(date=stamp, csrs=entry.get("csrs"),
                             benchmark_close=(point.close if point else None),
                             benchmark_return=None,
                             benchmark_available=False))
    meta = describe(path)
    first_gap = missing[0] if missing else None
    return dict(
        rows=rows,
        series=dict(label=SERIES_LABEL, source=SERIES_SOURCE,
                    available=meta["available"],
                    first=meta.get("first"), last=meta.get("last")),
        units=dict(csrs="composite score, 0..1",
                   benchmark="simple close-to-close return"),
        coverage=dict(csrs_dates=len(rows), matched=matched,
                      benchmark_missing=len(missing),
                      first_missing=first_gap),
        note=(meta.get("reason") or
              (f"{matched} of {len(rows)} CSRS dates have an official "
               f"benchmark return. The {len(missing)} without one are shown "
               f"as gaps: the index series begins {meta.get('first')} while "
               f"the CSRS archive starts earlier, and no value is "
               f"forward-filled or substituted."
               if missing else
               f"all {matched} CSRS dates have an official benchmark return")),
    )


def representativeness(history, *, path: Path | None = None) -> dict:
    """FR54 — how closely the overlay's two series move together.

    FR54 asks for the correlation between the reconstructed universe's
    equal-weighted return and the official index, as evidence the FR52
    reconstruction is representative. This computes the correlation on
    whatever paired observations exist, and says how many that was. It is a
    descriptive statistic over available pairs and not a validation claim:
    with a short overlap it means very little, so `pairs` is reported beside
    it rather than buried.
    """
    joined = align(history, path=path)
    pairs = [(r["csrs"], r["benchmark_return"]) for r in joined["rows"]
             if r["benchmark_available"] and isinstance(r["csrs"], (int, float))]
    if len(pairs) < 3:
        return dict(available=False, pairs=len(pairs),
                    reason=("fewer than three paired observations; a "
                            "correlation over this would be noise"))
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return dict(available=False, pairs=len(pairs),
                    reason="one series is constant over the paired dates")
    return dict(available=True, pairs=len(pairs),
                correlation=cov / math.sqrt(var_x * var_y),
                note=("descriptive correlation of CSRS against official "
                      "benchmark returns over the paired dates. Not a "
                      "validation result and not an advance-warning claim"))
