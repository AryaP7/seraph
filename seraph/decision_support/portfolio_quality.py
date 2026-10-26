# C11 — import quality checks the parser cannot make (FR43 inputs).
"""What is wrong with an imported portfolio, stated before it is analysed.

`workspace.parse_holdings` is deliberately **pure** — no database, no
identity, no writes — which is right, and it means two things it cannot do:

* it cannot tell whether a symbol exists in the NSE corpus, because that
  needs the price store;
* it cannot tell a holding that is genuinely worth nothing from one whose
  price was never found.

The second is not hypothetical. `AcceptedRow.to_holding()` reads
``value=self.value or 0.0``, so a row carrying a quantity and no price is
accepted and then valued at **zero**. It then sits in the exposure
calculation at 0.00% and changes nothing, which reads as "this holding
carries no risk" when the truth is "nobody priced it". 40 shares of a real
security are not zero rupees.

This module does not change that coercion — how an unpriced holding should
be treated in an exposure calculation is a scientific decision for the owner,
not a default to be switched quietly. What it does is make the condition
**visible**, so the frontend can say so and the number is read with the
caveat attached.
"""
from __future__ import annotations


def inspect_rows(accepted, *, priced: "set[str] | None" = None) -> dict:
    """Quality findings for a parsed import.

    `accepted` is the `ImportPreview.accepted` list. `priced` is the set of
    symbols the price corpus knows; pass `None` to skip that check rather
    than have it silently pass.

    Returns `{unpriced, unknown, zero_valued, unclassified, checked_symbols}`,
    each a list of symbols, plus a `notes` list naming what was NOT checked.
    """
    unpriced, zero_valued, unclassified, unknown = [], [], [], []
    notes = []

    for row in accepted or ():
        symbol = getattr(row, "symbol", None) or ""
        value = getattr(row, "value", None)
        price = getattr(row, "price", None)
        quantity = getattr(row, "quantity", None)
        sector = getattr(row, "sector", None)

        # No value and no way to derive one: `to_holding()` will make this
        # 0.0, and that zero is an absence wearing a measurement's clothes.
        if value is None and not (quantity is not None and price is not None):
            unpriced.append(symbol)
        elif value == 0:
            # A genuine zero is possible (a fully exited position left in the
            # file) and is NOT the same finding, so it is reported apart.
            zero_valued.append(symbol)

        if not sector:
            unclassified.append(symbol)
        if priced is not None and symbol and symbol not in priced:
            unknown.append(symbol)

    if priced is None:
        notes.append("symbols were not checked against the price corpus; "
                     "an unlisted or mistyped symbol would be accepted")

    return dict(
        unpriced=sorted(set(unpriced)),
        unknown=sorted(set(unknown)),
        zero_valued=sorted(set(zero_valued)),
        unclassified=sorted(set(unclassified)),
        checked_symbols=priced is not None,
        notes=notes,
    )


def summary(findings: dict) -> list[str]:
    """One human sentence per finding, or an empty list when all is well."""
    lines = []
    if findings.get("unpriced"):
        lines.append(
            f"{len(findings['unpriced'])} holding(s) have no price and no way "
            f"to derive one — {', '.join(findings['unpriced'][:6])}. They are "
            f"valued at ZERO in the analysis below, which is a missing price "
            f"shown as a measurement, not a holding that is worth nothing")
    if findings.get("unknown"):
        lines.append(
            f"{len(findings['unknown'])} symbol(s) are not in the price "
            f"corpus — {', '.join(findings['unknown'][:6])}. They were "
            f"accepted at the value supplied in the file; nothing verified "
            f"that they exist")
    if findings.get("zero_valued"):
        lines.append(
            f"{len(findings['zero_valued'])} holding(s) carry an explicit "
            f"value of zero — {', '.join(findings['zero_valued'][:6])}. That "
            f"is a supplied zero, not a missing price")
    if findings.get("unclassified"):
        lines.append(
            f"{len(findings['unclassified'])} holding(s) carry no sector and "
            f"group under UNCLASSIFIED, so no sector flag can reach them")
    lines.extend(findings.get("notes") or [])
    return lines

# --------------------------------------------------------------------------
# turning an import into analysable rows WITHOUT the silent zero
# --------------------------------------------------------------------------
def analysable_rows(accepted, *, sectors=None) -> dict:
    """Split an import into rows safe to analyse and rows that are not.

    `AcceptedRow.to_holding()` reads ``value=self.value or 0.0``. For a row
    carrying a quantity and no price that produces a holding worth zero,
    which then sits in the exposure calculation contributing nothing — a
    missing price wearing a measurement's clothes.

    This does not change that method, because other callers depend on it and
    how an unpriced holding should be treated is the owner's decision. It
    offers the alternative: rows whose value is genuinely known go to
    `rows`, rows whose value is not go to `withheld` with a reason, and the
    caller analyses the first and reports the second.

    `sectors` is an optional `{symbol: sector}` map used to fill a blank
    sector — the enrichment a PDF statement needs, since statements carry no
    sector column. A symbol absent from the map keeps its blank sector and is
    reported as unclassified rather than guessed at.
    """
    rows, withheld = [], []
    for row in accepted or ():
        symbol = getattr(row, "symbol", None) or ""
        value = getattr(row, "value", None)
        price = getattr(row, "price", None)
        quantity = getattr(row, "quantity", None)

        if value is None and quantity is not None and price is not None:
            value = quantity * price
        if value is None:
            withheld.append(dict(
                symbol=symbol, quantity=quantity,
                reason=("no value and no price to derive one. Analysing it "
                        "would require valuing it at zero, which is a "
                        "missing price presented as a measurement")))
            continue

        sector = getattr(row, "sector", None)
        enriched_from = None
        if not sector and sectors:
            looked_up = sectors.get(symbol)
            if looked_up:
                sector = looked_up
                enriched_from = "symbol sector map"

        entry = dict(symbol=symbol, value=float(value),
                     quantity=float(quantity or 0.0),
                     sector=sector or "unclassified")
        if enriched_from:
            entry["sector_source"] = enriched_from
        rows.append(entry)

    return dict(
        rows=rows, withheld=withheld,
        analysed_value=round(sum(r["value"] for r in rows), 2),
        withheld_count=len(withheld),
        note=("withheld rows are excluded from the analysis rather than "
              "valued at zero; the exposure percentages below are shares of "
              "the analysed value, not of the whole file"),
    )
