# C11 — portfolio import beyond CSV/JSON (FR43 inputs).
"""Turn a broker/platform statement into the rows `parse_holdings` accepts.

`decision_support/workspace.parse_holdings` already takes CSV and JSON and is
the one place a holding becomes an accepted or rejected row. This module does
not duplicate that: it converts other **carriers** — a PDF statement today —
into CSV text and hands it straight back to `parse_holdings`, so every import
path ends at the same validator, the same rejection reasons and the same
normalised shape.

That is the whole design rule here. A second parser would mean a second idea
of what a valid holding is, and the two would drift.

**PDF is text extraction, not table interpretation.** `news/pdf_text.py`
already extracts PDF text in a disposable subprocess with size, page and
character caps — the right posture for a file a user uploaded. This reuses it
rather than calling `pypdf` in-process. A scanned statement has no extractable
text and is rejected saying so; no OCR is claimed.

**What is deliberately NOT here.** A TradingView shared-portfolio URL and a
Zerodha holdings pull are both network integrations against third-party
services. Neither is implemented, and neither is stubbed: an unimplemented
integration that returns plausible rows is indistinguishable from a working
one until someone trusts it.
"""
from __future__ import annotations

import csv
import io
import re

#: Column names the holdings parser understands, in the order written out.
#: `_norm_header` in `workspace.py` lowercases and strips, so these match.
COLUMNS = ("symbol", "quantity", "value", "sector", "cost_basis")

#: A statement line we can read: SYMBOL, then numbers. Deliberately strict —
#: a line we are not sure about is reported, never guessed at.
_ROW = re.compile(
    r"^\s*(?P<symbol>[A-Z][A-Z0-9&.\-]{1,19})\s+"
    r"(?P<rest>[\d,.\s()%-]+?)\s*$")

_NUMBER = re.compile(r"-?[\d,]+(?:\.\d+)?")


class ImportUnsupported(ValueError):
    """The carrier is not one this module can read."""


def holdings_csv_from_pdf(raw: bytes, *, seconds: float = 10.0) -> dict:
    """Extract holdings from a PDF statement into CSV text.

    Returns `{csv, rows, skipped, incomplete, note}`. `skipped` carries every
    line that looked like it might be a holding and was not read, with the
    reason — a count of ignored lines is not something a user can act on.

    Raises `ImportUnsupported` when the PDF yields no text at all, which is
    what a scanned statement does.
    """
    from seraph.news.pdf_text import extract_pdf

    try:
        text, incomplete = extract_pdf(raw, seconds=seconds)
    except (ValueError, TimeoutError) as exc:
        raise ImportUnsupported(str(exc)) from exc

    rows: list[dict] = []
    skipped: list[dict] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("[Page "):
            continue
        match = _ROW.match(stripped)
        if match is None:
            # Only report lines that plausibly carry a holding: a statement
            # is mostly prose and headings, and reporting all of it as
            # skipped would bury the lines that matter.
            if re.match(r"^[A-Z][A-Z0-9&.\-]{1,19}\s", stripped):
                skipped.append(dict(line=number, text=stripped[:120],
                                    reason="no numeric columns on this line"))
            continue
        numbers = [n.replace(",", "") for n in _NUMBER.findall(match["rest"])]
        if len(numbers) < 2:
            skipped.append(dict(
                line=number, text=stripped[:120],
                reason=(f"needs at least a quantity and a value; found "
                        f"{len(numbers)} number(s)")))
            continue
        rows.append(dict(symbol=match["symbol"], quantity=numbers[0],
                         value=numbers[-1], sector="", cost_basis=(
                             numbers[1] if len(numbers) > 2 else "")))

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in COLUMNS})

    return dict(
        csv=buffer.getvalue(), rows=len(rows), skipped=skipped,
        incomplete=incomplete,
        note=("text extraction only; no OCR and no table-structure "
              "interpretation is claimed. Columns are read positionally as "
              "symbol, quantity, [cost basis], value — check the preview "
              "before committing"))


#: A shared TradingView WATCHLIST. Portfolios have no equivalent — see
#: `holdings_csv_from_tradingview`.
_TV_WATCHLIST = re.compile(
    # `www.` or a two-letter locale (`in.`, `de.`, `jp.`) or neither.
    # Allowing only the locale form rejected the canonical www URL.
    r"^https?://(?:www\.|[a-z]{2}\.)?tradingview\.com/watchlists/(\d+)/?",
    re.IGNORECASE)


def tradingview_watchlist_symbols(url: str, *, fetch=None) -> dict:
    """Symbols from a PUBLIC TradingView watchlist URL. Not a portfolio.

    **What TradingView actually offers**, checked against their own support
    pages rather than assumed:

    * **Portfolios cannot be shared by URL at all.** They are created by
      importing a CSV/XLSX, by adding symbols manually, or from a watchlist,
      and the support article lists no sharing or public-link feature. There
      is also no holdings export — TradingView's own answer to "how can I
      download a list of holdings" is to export transactions and filter them.
    * **Watchlists can be shared**, at `tradingview.com/watchlists/<id>/`,
      and anyone with the link can view or copy the list.

    So the nearest real thing is a watchlist, and a watchlist is a list of
    **symbols with no quantities**. That cannot become a portfolio: without a
    quantity or a value there is no position to size, and inventing one would
    be fabricating the user's holdings.

    This therefore returns symbols only, and `portfolio_ready=False`. The
    caller must ask the user for quantities; it must not treat this as an
    imported portfolio.

    `fetch` is injected for testing. Nothing here is verified against a live
    TradingView page — see `VERIFICATION` below.
    """
    match = _TV_WATCHLIST.match((url or "").strip())
    if match is None:
        raise ImportUnsupported(
            "not a TradingView watchlist URL. Expected "
            "https://www.tradingview.com/watchlists/<id>/ . Note that "
            "TradingView PORTFOLIOS cannot be shared by URL at all; only "
            "watchlists can, and a watchlist carries no quantities")

    if fetch is None:
        raise ImportUnsupported(
            "no fetcher supplied. This import performs a network read of a "
            "third-party page, which the caller must authorise and provide "
            "explicitly rather than have a parser do on its own")

    text = fetch(url)
    symbols, seen = [], set()
    for raw in re.findall(r"\b(?:NSE|BSE)[:\-]([A-Z][A-Z0-9&.\-]{1,19})\b",
                          text or ""):
        if raw not in seen:
            seen.add(raw)
            symbols.append(raw)

    return dict(
        symbols=symbols,
        portfolio_ready=False,
        reason=("a TradingView watchlist carries symbols and no quantities, "
                "so it cannot by itself be a portfolio. Supply quantities "
                "for these symbols to make one"),
        source=url,
        note=("TradingView portfolios have no public share URL; this reads a "
              "shared WATCHLIST, which is a different object"))


#: Honest status of this integration, surfaced rather than buried.
VERIFICATION = dict(
    portfolio_url=dict(
        supported=False,
        finding=("TradingView provides no public share URL for portfolios "
                 "and no holdings export. Verified against TradingView's own "
                 "support documentation on 2026-10-26.")),
    watchlist_url=dict(
        supported=True, verified=False,
        finding=("Shared watchlists exist at tradingview.com/watchlists/<id>/ "
                 "and the parser is implemented, but it has NOT been verified "
                 "against a live page: no legitimately accessible real shared "
                 "watchlist link was available to test with. Treat as "
                 "unverified until one is supplied.")),
)


def holdings_csv_from_zerodha(*, tokens_path=None) -> dict:
    """NOT IMPLEMENTED — the Kite client here is market data, not holdings.

    `ingestion/kite_client.py` authenticates for instrument and bar data. The
    holdings endpoint is a different scope on the user's own account, and
    pulling someone's real positions is an action they must authorise
    explicitly rather than something a dashboard does because it can.
    """
    raise ImportUnsupported(
        "Zerodha holdings import is not implemented. The Kite client in this "
        "repository authenticates for market data; reading a user's holdings "
        "is a different scope on their own account and needs their explicit "
        "authorisation, not a dashboard deciding to")
