# C2 — Ingestion Layer (FR51): NSE FII/DII flow client → E14 flow_aggregates.
"""Daily FII/DII net cash-market activity and the derived residual flow share,
which powers FR45's herd-share indicator.

OQ8b RESOLVES NEGATIVELY — THERE IS NO FREE BULK HISTORY
--------------------------------------------------------
DATA-ACQUISITION §6 item 8 asks "how far back is bulk retrieval practical".
Probed 2026-10-12:
  - `https://www.nseindia.com/api/fiidiiTradeReact`  → 200, and serves exactly
    ONE day: the latest published session. There is no date range parameter
    that works.
  - `…/fiidiiTradeReact?date=10-Oct-2026`            → 200 but the body is
    Akamai-obfuscated binary, not JSON. Not a usable archive.
  - `nsearchives …/content/fo/fii_stats_<dd-Mon-yyyy>.xls` → 200 for recent
    dates, 404 for 2012. It is also the wrong dataset: F&O participant stats,
    not cash-segment FII/DII.

**Consequence for FR45, stated plainly:** E14 can only be accumulated forward,
one session per run, from the day this client is first scheduled. There is no
FII/DII history for epochs 1–5 (GFC 2008 … tightening 2022) and none for the
tariff-2026 epoch before today. Any FR45 artefact must either be restricted to
the accumulated window or be reported as unavailable. Backfilling it needs a
paid or aggregator source, which is a procurement decision, not a code change.

This module therefore does NOT pretend to backfill. `ingest_latest()` captures
one session; running it daily from cron (AGENTS.md §2) is the intended use, and
`writeBatch` idempotency makes a double-run on the same session a no-op.

THE DENOMINATOR IS APPROXIMATE, AND DOUBLY SO
---------------------------------------------
`residual_flow_share = 1 − (FII_gross + DII_gross)/total_turnover` (SPEC FR45,
DATA-ACQUISITION §3) needs a cash-market turnover denominator that NSE does not
publish alongside the FII/DII report. Two routes, in preference order:

1. `--turnover-source nse-index` (default). NSE's own published
   `ind_close_all_<ddmmyyyy>.csv` carries a "Turnover (Rs. Cr.)" column; the
   Nifty 500 row is used as the NSE cash-market turnover proxy. A *published*
   figure, so it is auditable, but it covers Nifty-500 constituents, not the
   whole cash segment, so it understates the denominator and therefore
   **overstates** the residual share.
2. `--turnover-source e3`. Sum of E3 `tottrdval` for the date. E3's own
   `tottrdval` is itself approximated as `close × volume` by `eod2_client`
   (which raises ESTIMATOR_FALLBACK for exactly this reason), so this route is
   an approximation stacked on an approximation.

Neither matches the FII/DII numerator's scope: NSE's FII/DII report aggregates
NSE + BSE + MSEI, while both denominators are NSE-only. Every row written
therefore carries ESTIMATOR_FALLBACK, and a residual share outside [0, 1] is
surfaced as a warning rather than clipped — a clipped value would hide exactly
the scope mismatch a reader needs to see. The report must not present
`residual_flow_share` as a measured quantity.

UNITS: NSE publishes FII/DII in ₹ crore and index turnover in ₹ crore, so the
ratio is unit-consistent on route 1. E3's `tottrdval` is in rupees, so route 2
converts to crore explicitly. Getting this wrong silently moves the residual
share by 10^7, so the conversion is one named constant, not an inline literal.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from seraph.shared_types import (
    IST,
    FlowAggregate,
    IngestBatch,
    SeraphWarning,
)
#: Intra-component reuse: `_Fetcher` and its error variants are C2-internal
#: (hence underscored) and shared by both C2 clients rather than duplicated.
#: The retry/backoff, the rate-limit gap and the total-deadline guard are
#: fiddly enough that two copies would drift — and `ind_close_all_*.csv` is
#: fetched by both modules, so they share its cache too.
from seraph.ingestion.macro_client import (
    NSE_INDEX_ARCHIVE,
    _Blocked,
    _Fetcher,
    _NotFound,
    _Unavailable,
)

NSE_FII_DII_API = "https://www.nseindia.com/api/fiidiiTradeReact"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "artefacts" / "flow_raw"

#: ₹1 crore = 10^7 rupees. E3 `tottrdval` is in rupees; NSE reports crore.
RUPEES_PER_CRORE = 1e7

#: NSE's own index-turnover row used as the cash-market denominator proxy.
TURNOVER_INDEX = "Nifty 500"


#: Largest |published net − (buy − sell)| treated as source rounding rather
#: than a parse error. NSE publishes all three to 2dp, so anything beyond a
#: couple of paise means the fields disagree and the row should be looked at.
_NET_RECONCILE_TOL = 0.02


@dataclass(frozen=True)
class FiiDiiPrint:
    """One session's published FII/DII figures, in ₹ crore, as published.

    `fii_net`/`dii_net` are the values NSE *publishes*, not recomputed from
    buy − sell. The two agree to rounding, but recomputing them in float
    introduces representation noise (−1708.48 became −1708.480000000001 in a
    real run), and E14's columns are `numeric` — so the noise would be
    persisted exactly as written. Preserve what the source said.

    `gross` is buy + sell (two-sided participation), which is what FR45's
    numerator needs; the net would cancel a buy against a sell and understate
    participation.
    """

    date: date
    fii_buy: float
    fii_sell: float
    fii_net: float
    dii_buy: float
    dii_sell: float
    dii_net: float

    @property
    def gross(self) -> float:
        return self.fii_buy + self.fii_sell + self.dii_buy + self.dii_sell

    def net_reconciliation(self) -> tuple[tuple[str, float, float], ...]:
        """Published net vs buy − sell, per category, where they disagree
        beyond source rounding."""
        out = []
        for cat, buy, sell, net in (
            ("fii", self.fii_buy, self.fii_sell, self.fii_net),
            ("dii", self.dii_buy, self.dii_sell, self.dii_net),
        ):
            derived = buy - sell
            if abs(derived - net) > _NET_RECONCILE_TOL:
                out.append((cat, net, derived))
        return tuple(out)


def parse_fii_dii(payload: object) -> FiiDiiPrint:
    """NSE `fiidiiTradeReact` JSON → one print.

    Shape (verified 2026-10-12):
        [{"category":"DII","date":"12-Oct-2026","buyValue":"15506.73",
          "sellValue":"12461.71","netValue":"3045.02"}, {"category":"FII/FPI", …}]

    The category label has varied historically ("FII", "FII/FPI"), so it is
    matched by prefix. Both categories are required: a payload with only one is
    a partial publication and must not be written as if complete.
    """
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"unexpected FII/DII payload shape: {type(payload).__name__}")

    found: dict[str, dict] = {}
    day: date | None = None
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError(f"unexpected FII/DII entry: {entry!r}")
        category = str(entry.get("category", "")).strip().upper()
        key = "fii" if category.startswith("FII") else "dii" if category.startswith("DII") else None
        if key is None:
            continue
        parsed = datetime.strptime(str(entry["date"]).strip(), "%d-%b-%Y").date()
        if day is not None and parsed != day:
            raise ValueError(
                f"FII/DII payload mixes dates ({day} and {parsed}) — refusing to "
                "collapse two sessions into one row"
            )
        day = parsed
        found[key] = entry

    missing = {"fii", "dii"} - set(found)
    if missing or day is None:
        raise ValueError(
            f"FII/DII payload incomplete — missing {sorted(missing) or 'date'}; "
            "a partial publication is not written"
        )

    def num(entry: dict, field: str) -> float:
        raw = str(entry.get(field, "")).strip().replace(",", "")
        if raw in {"", "-", "NA"}:
            raise ValueError(f"FII/DII {field} not published: {entry!r}")
        return float(raw)

    return FiiDiiPrint(
        date=day,
        fii_buy=num(found["fii"], "buyValue"),
        fii_sell=num(found["fii"], "sellValue"),
        fii_net=num(found["fii"], "netValue"),
        dii_buy=num(found["dii"], "buyValue"),
        dii_sell=num(found["dii"], "sellValue"),
        dii_net=num(found["dii"], "netValue"),
    )


def parse_index_turnover(
    text: str, index_name: str = TURNOVER_INDEX
) -> float | None:
    """"Turnover (Rs. Cr.)" for one index out of `ind_close_all_<ddmmyyyy>.csv`.

    Header (verified 2026-10-12): Index Name, Index Date, Open, High, Low,
    Close, Points Change, Change(%), Volume, Turnover (Rs. Cr.), P/E, P/B,
    Div Yield. The column is located by name rather than position, because NSE
    has changed this file's width before. NSE's "-" placeholder → None.
    """
    import csv
    import io

    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return None
    if not header or header[0].lower() != "index name":
        raise ValueError(f"not an NSE ind_close_all CSV: header={header[:3]!r}")
    try:
        col = next(
            i for i, h in enumerate(header) if h.lower().startswith("turnover")
        )
    except StopIteration:
        raise ValueError(f"no turnover column in ind_close_all header: {header!r}")

    for row in reader:
        if len(row) <= col or row[0].strip().lower() != index_name.lower():
            continue
        raw = row[col].strip().replace(",", "")
        return None if raw in {"", "-"} else float(raw)
    return None


def residual_flow_share(gross_crore: float, turnover_crore: float) -> float:
    """FR45: 1 − gross institutional participation / total turnover.

    Returned unclipped. A value outside [0, 1] is real evidence that numerator
    and denominator disagree in scope, and the caller surfaces it as a warning;
    clipping here would destroy that evidence.
    """
    if turnover_crore <= 0:
        raise ValueError(f"non-positive turnover {turnover_crore!r} — cannot divide")
    return 1.0 - gross_crore / turnover_crore


def to_entity(
    print_: FiiDiiPrint, turnover_crore: float
) -> tuple[FlowAggregate, tuple[SeraphWarning, ...]]:
    """One print + denominator → an E14 row plus its mandatory caveats.

    Units: everything is ₹ crore here, matching NSE's publication. The share is
    dimensionless.
    """
    share = residual_flow_share(print_.gross, turnover_crore)
    warnings: list[SeraphWarning] = [SeraphWarning(
        code="ESTIMATOR_FALLBACK",
        message="residual_flow_share mixes an NSE+BSE+MSEI FII/DII numerator "
                "with an NSE-only turnover denominator; it is a proxy, not a "
                "measured participation share",
        context={"field": "residual_flow_share", "date": print_.date.isoformat()},
    )]
    for cat, published, derived in print_.net_reconciliation():
        # The published net is kept; the disagreement is surfaced rather than
        # silently resolved in either direction.
        warnings.append(SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=f"{cat}_net published as {published} but buy-sell gives "
                    f"{derived:.2f} — source fields disagree; published value kept",
            context={"date": print_.date.isoformat(), "category": cat},
        ))
    if not 0.0 <= share <= 1.0:
        warnings.append(SeraphWarning(
            code="ESTIMATOR_FALLBACK",
            message=f"residual_flow_share outside [0,1] ({share:.4f}) — numerator "
                    "and denominator scopes disagree; reported unclipped",
            context={"date": print_.date.isoformat(), "share": share},
        ))
    return FlowAggregate(
        date=print_.date.isoformat(),
        fii_net=print_.fii_net,
        dii_net=print_.dii_net,
        total_turnover=turnover_crore,
        residual_flow_share=share,
    ), tuple(warnings)


# --- turnover denominators -----------------------------------------------


def turnover_from_nse_index(fetcher: _Fetcher, day: date) -> float | None:
    """Published Nifty-500 cash turnover (₹ crore) for `day`, or None."""
    stamp = day.strftime("%d%m%Y")
    try:
        text = fetcher.get(
            f"{NSE_INDEX_ARCHIVE}/ind_close_all_{stamp}.csv",
            f"nse_ind_close_all_{stamp}.csv",
            referer="https://www.nseindia.com/",
        )
    except _NotFound:
        return None
    return parse_index_turnover(text)


async def turnover_from_e3(day: date) -> float | None:
    """Sum of E3 `tottrdval` for `day`, converted rupees → ₹ crore.

    Approximation stacked on an approximation — see the module docstring. Only
    used when explicitly selected.
    """
    from seraph.store import StoreReader

    reader = await StoreReader.connect()
    try:
        iso = day.isoformat()
        res = await reader.daily_bars(from_date=iso, to_date=iso)
        if res.status != "ok":
            raise RuntimeError(f"cannot read E3 for {iso}: {res.error}")
        if not res.value:
            return None
        return sum(b.tottrdval for b in res.value) / RUPEES_PER_CRORE
    finally:
        await reader.close()


# --- orchestration -------------------------------------------------------


async def ingest_latest(
    *,
    turnover_source: str = "nse-index",
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = True,
    dry_run: bool = False,
) -> dict:
    """Capture the latest published FII/DII session into E14.

    `refresh` defaults to True: the endpoint is a moving "latest session" view,
    so a cached copy would silently re-ingest a stale day.
    """
    fetcher = _Fetcher(cache_dir, refresh=refresh)
    stamp = datetime.now(IST).strftime("%Y%m%d")
    try:
        raw = fetcher.get(
            NSE_FII_DII_API,
            f"nse_fiidii_{stamp}.json",
            referer="https://www.nseindia.com/",
        )
    except _Blocked as e:
        return {"status": "error", "reason": f"SOURCE_BLOCKED {e.status}",
                "detail": "NSE FII/DII endpoint blocked — residential IP required"}
    except (_NotFound, _Unavailable) as e:
        return {"status": "error", "reason": "SOURCE_UNAVAILABLE", "detail": str(e)}

    try:
        print_ = parse_fii_dii(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as e:
        return {"status": "error", "reason": "SCHEMA_MISMATCH", "detail": str(e)}

    if turnover_source == "nse-index":
        try:
            turnover = turnover_from_nse_index(fetcher, print_.date)
        except (_Blocked, _Unavailable, ValueError) as e:
            return {"status": "error", "reason": "TURNOVER_UNAVAILABLE",
                    "detail": f"{type(e).__name__}: {e}"}
    elif turnover_source == "e3":
        turnover = await turnover_from_e3(print_.date)
    else:
        raise ValueError(f"turnover_source must be 'nse-index' or 'e3', "
                         f"got {turnover_source!r}")

    if turnover is None or turnover <= 0:
        # E14's schema makes total_turnover and residual_flow_share NOT NULL,
        # so a missing denominator cannot be written as a partial row. Report
        # it; do not invent a turnover figure.
        return {"status": "error", "reason": "TURNOVER_UNAVAILABLE",
                "detail": f"no usable {turnover_source} turnover for "
                          f"{print_.date.isoformat()} — row not written"}

    row, warnings = to_entity(print_, turnover)
    result: dict = {
        "status": "ok",
        "date": row.date,
        "fiiNet": row.fii_net,
        "diiNet": row.dii_net,
        "totalTurnoverCrore": row.total_turnover,
        "residualFlowShare": row.residual_flow_share,
        "turnoverSource": turnover_source,
        "warnings": [w.message for w in warnings],
        "historyLimitation": "forward-accumulating only — NSE serves no free "
                             "FII/DII bulk history (OQ8b resolves negatively)",
        "downloads": fetcher.manifest,
    }
    if dry_run:
        result["written"] = False
        return result

    from seraph.store import StoreWriter

    writer = await StoreWriter.connect()
    try:
        res = await writer.write_batch(IngestBatch(
            run_id=f"flow-{datetime.now(IST).strftime('%Y%m%dT%H%M%S')}",
            source="nse-fii-dii",
            entity="E14",
            rows=(row,),
            watermark=f"{row.date}T20:00:00+05:30",   # published ~8:30-9:30 PM IST
            source_schema_version=f"nse-fiidii-react-v1+turnover-{turnover_source}",
        ))
        if res.status != "ok":
            result["status"] = "error"
            result["reason"] = str(res.error)
            return result
        result["written"] = True
        result["inserted"] = res.value.inserted
        result["updated"] = res.value.updated
    finally:
        await writer.close()
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="NSE FII/DII flow ingestion (C2 → E14). Captures the latest "
                    "published session; there is no free bulk history."
    )
    p.add_argument("--turnover-source", choices=("nse-index", "e3"),
                   default="nse-index",
                   help="nse-index = NSE's published Nifty-500 cash turnover "
                        "(default); e3 = summed daily_prices tottrdval")
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    out = asyncio.run(ingest_latest(
        turnover_source=a.turnover_source, cache_dir=a.cache_dir, dry_run=a.dry_run
    ))
    print(json.dumps(out, indent=2, default=str), flush=True)
    return 0 if out.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
