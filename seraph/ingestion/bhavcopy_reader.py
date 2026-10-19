# C2 — Ingestion Layer (FR1, FR52): NSE bhavcopy, both schemas.
"""Parse the exchange's own daily file, so TOTTRDVAL stops being a proxy.

Why this exists
---------------
`eod2_client.py` approximates traded value as `close × volume` and warns about
it on every batch, because the EOD2 CSVs carry no traded-value column. FR52
**ranks the universe by six-month median TOTTRDVAL**, so the proxy is not a
cosmetic difference: `close × volume` is the value of the day's volume at the
closing price, while TOTTRDVAL is the value actually transacted across the
session. They differ by the intraday price path, and on a volatile day in a
wide-ranging stock the gap is large enough to move a name across the top-500
boundary.

Two schemas, both real
----------------------
NSE replaced the legacy `cm<DDMMMYYYY>bhav.csv` with the UDiFF
`BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv` in July 2024. Both appear in any
real historical corpus, so both are parsed here and normalised to one shape.
The schema that was read is recorded on the result — `writer.py` already
distinguishes `bhavcopy-legacy` as expected input rather than a defect.

What it refuses to do
---------------------
* **No guessing the schema from the filename.** The header is read. A file
  whose header matches neither layout is an error naming the columns it had.
* **No silent coercion.** A row whose traded value will not parse is rejected
  with its reason, not defaulted to zero — a zero traded value sorts a liquid
  name to the bottom of the FR52 ranking.
* **No synthesising TOTTRDVAL.** If the column is absent the result says
  `traded_value_basis='unavailable'`; it does not quietly fall back to the
  `close × volume` proxy under the exact column's name.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

Schema = Literal["bhavcopy-legacy", "bhavcopy-udiff"]

#: Legacy header (pre-July-2024). `TOTTRDVAL` is in rupees, `TOTTRDQTY` in shares.
LEGACY_COLUMNS = {"SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "LAST",
                  "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP"}

#: UDiFF header (July 2024 onward). Same quantities, different spellings.
UDIFF_COLUMNS = {"TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric",
                 "ClsPric", "LastPric", "PrvsClsgPric", "TtlTradgVol",
                 "TtlTrfVal", "TradDt"}

#: Equity series only. `BE`/`BZ` are surveillance segments and `SM`/`ST` are
#: SME; FR52 selects NSE equities, and the SME board is a different market.
EQUITY_SERIES = {"EQ"}

_LEGACY_DATE = re.compile(r"^\d{2}-[A-Z]{3}-\d{4}$")


class UnknownBhavcopySchema(ValueError):
    """The header matched neither layout."""


@dataclass(frozen=True)
class BhavRow:
    symbol: str
    series: str
    trade_date: str              # ISO
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    last: float
    traded_quantity: int
    traded_value: float          # TOTTRDVAL, rupees — exact, not a proxy
    trades: int | None = None
    isin: str | None = None

    @property
    def proxy_value(self) -> float:
        """What `close × volume` would have said, for comparison."""
        return self.close * self.traded_quantity

    @property
    def proxy_error(self) -> float | None:
        """Relative error of the proxy against the exact value."""
        if not self.traded_value:
            return None
        return (self.proxy_value - self.traded_value) / self.traded_value


@dataclass
class BhavcopyResult:
    schema: Schema
    trade_date: str | None
    rows: list[BhavRow] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    skipped_series: dict = field(default_factory=dict)
    traded_value_basis: str = "exact_TOTTRDVAL"

    def describe(self) -> dict:
        errors = [r.proxy_error for r in self.rows if r.proxy_error is not None]
        return dict(
            schema=self.schema, trade_date=self.trade_date,
            rows=len(self.rows), rejected=len(self.rejected),
            skipped_series=dict(sorted(self.skipped_series.items())),
            traded_value_basis=self.traded_value_basis,
            rejected_rows=self.rejected[:20],
            proxy_comparison=(dict(
                n=len(errors),
                mean_relative_error=sum(errors) / len(errors),
                max_abs_relative_error=max(abs(e) for e in errors),
                note=("how far close x volume would have been from the exact "
                      "traded value on this day. FR52 ranks on TOTTRDVAL, so "
                      "this error moves names across the top-500 boundary"))
                if errors else None),
        )


def _number(raw, field_name, index, rejected, *, integer=False):
    text = (raw or "").strip().replace(",", "")
    if text in ("", "-"):
        rejected.append(dict(index=index, field=field_name,
                             reason=f"{field_name} is empty"))
        return None
    try:
        value = float(text)
    except ValueError:
        rejected.append(dict(index=index, field=field_name,
                             reason=f"{field_name} {text!r} is not a number"))
        return None
    if value < 0:
        rejected.append(dict(index=index, field=field_name,
                             reason=f"{field_name} is negative ({value})"))
        return None
    return int(value) if integer else value


def _iso_date(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if _LEGACY_DATE.match(text.upper()):
        return datetime.strptime(text.upper(), "%d-%b-%Y").date().isoformat()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def detect_schema(header) -> Schema:
    """Read the header. The filename is not evidence.

    The signature deliberately excludes the traded-value column. A truncated
    export is a recognisable layout with a column missing — reporting
    `traded_value_basis='unavailable'` is more useful than calling the whole
    file unknown, and it keeps the proxy from being substituted silently.
    """
    present = {h.strip() for h in header if h}
    if {"SYMBOL", "SERIES", "TIMESTAMP"} <= present:
        return "bhavcopy-legacy"
    if {"TckrSymb", "SctySrs", "TradDt"} <= present:
        return "bhavcopy-udiff"
    raise UnknownBhavcopySchema(
        f"header matches neither the legacy nor the UDiFF bhavcopy layout. "
        f"Columns present: {sorted(present)[:12]}")


def parse_bhavcopy(data: bytes | str, *, series=EQUITY_SERIES) -> BhavcopyResult:
    """Parse either schema into one normalised shape."""
    text = (data.decode("utf-8-sig", errors="replace")
            if isinstance(data, bytes) else data)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise UnknownBhavcopySchema("the file has no header row")
    schema = detect_schema(reader.fieldnames)
    legacy = schema == "bhavcopy-legacy"
    columns = dict(
        symbol="SYMBOL" if legacy else "TckrSymb",
        series="SERIES" if legacy else "SctySrs",
        open="OPEN" if legacy else "OpnPric",
        high="HIGH" if legacy else "HghPric",
        low="LOW" if legacy else "LwPric",
        close="CLOSE" if legacy else "ClsPric",
        last="LAST" if legacy else "LastPric",
        prev_close="PREVCLOSE" if legacy else "PrvsClsgPric",
        quantity="TOTTRDQTY" if legacy else "TtlTradgVol",
        value="TOTTRDVAL" if legacy else "TtlTrfVal",
        trades="TOTALTRADES" if legacy else "TtlNbOfTxsExctd",
        date="TIMESTAMP" if legacy else "TradDt",
        isin="ISIN" if legacy else "ISIN",
    )
    result = BhavcopyResult(schema=schema, trade_date=None)
    if columns["value"] not in (reader.fieldnames or []):
        result.traded_value_basis = "unavailable"

    for index, raw in enumerate(reader, start=1):
        row = {k: (v or "") for k, v in raw.items() if k}
        symbol = row.get(columns["symbol"], "").strip().upper()
        if not symbol:
            result.rejected.append(dict(index=index, field="symbol",
                                        reason="no ticker symbol"))
            continue
        row_series = row.get(columns["series"], "").strip().upper()
        if series and row_series not in series:
            result.skipped_series[row_series or "(blank)"] = (
                result.skipped_series.get(row_series or "(blank)", 0) + 1)
            continue
        trade_date = _iso_date(row.get(columns["date"], ""))
        if trade_date is None:
            result.rejected.append(dict(index=index, field="date",
                                        reason=f"unparseable trade date "
                                               f"{row.get(columns['date'])!r}"))
            continue
        if result.trade_date is None:
            result.trade_date = trade_date
        elif trade_date != result.trade_date:
            result.rejected.append(dict(
                index=index, field="date",
                reason=f"row dated {trade_date}, but this file is for "
                       f"{result.trade_date}: a bhavcopy covers one session"))
            continue

        before = len(result.rejected)
        values = {
            name: _number(row.get(columns[name]), name, index, result.rejected,
                          integer=(name == "quantity"))
            for name in ("open", "high", "low", "close", "last", "prev_close",
                         "quantity")
        }
        if result.traded_value_basis == "exact_TOTTRDVAL":
            values["value"] = _number(row.get(columns["value"]), "traded_value",
                                      index, result.rejected)
        else:
            values["value"] = None
        if len(result.rejected) > before:
            continue
        if values["high"] < values["low"]:
            result.rejected.append(dict(
                index=index, field="high",
                reason=f"high {values['high']} is below low {values['low']}"))
            continue

        trades_raw = row.get(columns["trades"], "").strip().replace(",", "")
        result.rows.append(BhavRow(
            symbol=symbol, series=row_series, trade_date=trade_date,
            open=values["open"], high=values["high"], low=values["low"],
            close=values["close"], last=values["last"],
            prev_close=values["prev_close"],
            traded_quantity=values["quantity"],
            traded_value=values["value"] if values["value"] is not None else 0.0,
            trades=int(float(trades_raw)) if trades_raw.replace(".", "").isdigit()
            else None,
            isin=(row.get(columns["isin"]) or "").strip().upper() or None))
    return result


def compare_with_proxy(result: BhavcopyResult) -> dict:
    """How wrong the `close × volume` proxy was, per symbol.

    This is the FR52 evidence: the proxy is retained in `eod2_client` with its
    warning, and this quantifies what replacing it changes rather than
    asserting it matters.
    """
    rows = [r for r in result.rows if r.traded_value]
    if not rows:
        return dict(comparable=0,
                    note="no exact traded value in this file; nothing to compare")
    ranked_exact = [r.symbol for r in sorted(rows, key=lambda r: -r.traded_value)]
    ranked_proxy = [r.symbol for r in sorted(rows, key=lambda r: -r.proxy_value)]
    moved = sum(1 for a, b in zip(ranked_exact, ranked_proxy) if a != b)
    worst = max(rows, key=lambda r: abs(r.proxy_error or 0))
    return dict(
        comparable=len(rows),
        rank_positions_changed=moved,
        worst_symbol=worst.symbol,
        worst_relative_error=worst.proxy_error,
        note=("FR52 ranks by six-month median TOTTRDVAL, so a changed rank "
              "position can change universe membership"),
    )
