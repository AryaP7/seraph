# T0 — a fictional portfolio over REAL NSE securities, for end-to-end testing.
"""Twelve NSE-listed symbols with INVENTED ownership, for exercising FR43.

**What is real and what is not, stated once so it cannot be mistaken:**

* The **symbols** are real NSE-listed securities and the **prices** come from
  `daily_prices` — the acquired corpus, not this file. Nothing here invents a
  market price.
* The **quantities and cost bases are fiction.** They are test inputs chosen
  to exercise the analysis: a deliberate concentration, a spread across
  sectors, one small holding and one large one. They are nobody's positions.

Every row carries `TEST-INPUT` in its note for exactly that reason, and the
builder refuses to emit a portfolio without it.

Sectors are the NSE macro-sector names the universe uses, so the sector
breakdown in `portfolio_overlay` has something real to group by.
"""
from __future__ import annotations

import csv
import io

MARKER = "TEST-INPUT"

#: symbol, invented quantity, invented cost basis per share, sector.
#: Chosen for shape, not for plausibility as anyone's real book: FINANCIAL
#: SERVICES is deliberately over-weighted so concentration has something to
#: find, and TATASTEEL is deliberately tiny.
HOLDINGS: tuple[dict, ...] = (
    dict(symbol="RELIANCE",   quantity=250,  cost_basis=1105.00, sector="OIL GAS & CONSUMABLE FUELS"),
    dict(symbol="HDFCBANK",   quantity=1200, cost_basis=655.40,  sector="FINANCIAL SERVICES"),
    dict(symbol="ICICIBANK",  quantity=600,  cost_basis=1280.75, sector="FINANCIAL SERVICES"),
    dict(symbol="SBIN",       quantity=900,  cost_basis=870.10,  sector="FINANCIAL SERVICES"),
    dict(symbol="AXISBANK",   quantity=400,  cost_basis=1150.00, sector="FINANCIAL SERVICES"),
    dict(symbol="TCS",        quantity=180,  cost_basis=2610.00, sector="INFORMATION TECHNOLOGY"),
    dict(symbol="INFY",       quantity=350,  cost_basis=1190.25, sector="INFORMATION TECHNOLOGY"),
    dict(symbol="ITC",        quantity=2000, cost_basis=243.60,  sector="FAST MOVING CONSUMER GOODS"),
    dict(symbol="LT",         quantity=120,  cost_basis=3410.00, sector="CAPITAL GOODS"),
    dict(symbol="MARUTI",     quantity=40,   cost_basis=10850.00, sector="AUTOMOBILE AND AUTO COMPONENTS"),
    dict(symbol="SUNPHARMA",  quantity=300,  cost_basis=1690.00, sector="HEALTHCARE"),
    dict(symbol="TATASTEEL",  quantity=150,  cost_basis=172.40,  sector="METALS & MINING"),
)

COLUMNS = ("symbol", "quantity", "value", "sector", "cost_basis", "note")


def rows(prices: dict) -> list[dict]:
    """Holdings valued at REAL closes. `prices` is `{symbol: close}`.

    A symbol with no price is returned with `value=None` rather than dropped
    or valued at zero: an unpriced holding is a fact the analysis has to see,
    and it is what the missing-price case tests.
    """
    out = []
    for holding in HOLDINGS:
        close = prices.get(holding["symbol"])
        value = (round(float(close) * holding["quantity"], 2)
                 if close is not None else None)
        out.append(dict(
            symbol=holding["symbol"], quantity=holding["quantity"],
            value=value, sector=holding["sector"],
            cost_basis=holding["cost_basis"],
            note=f"{MARKER} invented ownership; price from daily_prices"))
    return out


def to_csv(prices: dict) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS))
    writer.writeheader()
    for row in rows(prices):
        writer.writerow({k: ("" if row.get(k) is None else row[k])
                         for k in COLUMNS})
    return buffer.getvalue()


def to_json(prices: dict) -> str:
    import json
    return json.dumps(dict(holdings=rows(prices)), indent=1)


def to_manual_entries(prices: dict) -> list[dict]:
    """The shape a manual-entry form submits: one dict per row, strings."""
    return [{k: ("" if r.get(k) is None else str(r[k])) for k in COLUMNS}
            for r in rows(prices)]


# --------------------------------------------------------------------------
def to_pdf(prices: dict) -> bytes:
    """A minimal text PDF statement, built without a PDF writer library.

    `reportlab` is not installed and this does not need it: a statement is a
    page of text, and a PDF of a page of text is a short, well-specified
    file. Writing it by hand keeps the test free of a dependency it would
    only use once.
    """
    lines = ["FICTIONAL HOLDINGS STATEMENT", f"{MARKER} - invented ownership",
             "", "SYMBOL        QTY        COST       VALUE", ""]
    for row in rows(prices):
        value = "" if row["value"] is None else f"{row['value']:.2f}"
        lines.append(f"{row['symbol']:<13} {row['quantity']:<10} "
                     f"{row['cost_basis']:<10} {value}")
    return _text_pdf(lines)


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _text_pdf(lines: "list[str]") -> bytes:
    """One page of monospaced text as a PDF 1.4 file."""
    content = ["BT", "/F1 10 Tf", "12 TL", "40 780 Td"]
    for line in lines:
        content.append(f"({_escape(line)}) Tj")
        content.append("T*")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)
