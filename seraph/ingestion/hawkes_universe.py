# C2 — Ingestion Layer (FR1, NFR6): the ~100-symbol intraday universe for Pillar 1.
"""Which symbols get 5-minute bars pulled, and why.

SPEC §8 OQ1 is open and blocking: "Nifty 50 only, or Nifty 50 + tariff-exposed
sector representatives?" SERAPH-BUILD-ROADMAP §4 records the agreed default —
**Nifty 50 + tariff-exposed representatives**, because the §5.1.1 sector
micro-flags (FR14) and the Epoch-6 tariff analysis (O8) both need sectoral
coverage that a Nifty-50-only pull cannot provide.

The list is therefore built in two documented parts:

1. **Liquidity core (reproducible, no external list required).** The top
   `CORE_N` NSE equities by six-month median traded value at the most recent
   rebalance, taken straight from the C3 universe snapshot. This is a stated
   rule over data already in the store rather than a pasted index membership
   list, so it regenerates exactly and carries no licensing question. In
   practice it recovers essentially all of the Nifty 50 plus the remaining
   large caps.

2. **Tariff-exposed representatives (hand-picked, rule documented).** SPEC
   OQ11 resolves the taxonomy to NSE sectoral indices, but those constituent
   lists are not yet ingested, and DATA-ACQUISITION §5 flags that **solar has
   no clean NSE sectoral index at all**, so a hand-picked basket with a written
   selection rule is required by the spec itself. The rule applied here: for
   each of the five tariff-exposed sectors named in FR22 (steel, aluminium,
   auto components, solar, pharmaceuticals), take the most liquid NSE-listed
   names whose primary business sits in that sector.

**⚠ The sector basket below needs team confirmation before results are
reported.** It is a defensible starting selection, not an authoritative
taxonomy; once NSE sectoral index membership is ingested it should be replaced
by that membership, with this list kept only for the solar basket that no index
covers. Nothing downstream hardcodes these names — they are read from here.
"""
from __future__ import annotations

from seraph.universe.instrument_type import is_equity

CORE_N = 80

#: Hand-picked tariff-exposed representatives, grouped by the FR22 sectors.
#: Selection rule: most liquid NSE-listed names whose primary business is in
#: the sector. Confirm with the team / Dr. Satisha before reporting.
TARIFF_SECTOR_BASKET: dict[str, tuple[str, ...]] = {
    "steel": ("TATASTEEL", "JSWSTEEL", "SAIL", "JINDALSTEL"),
    "aluminium": ("HINDALCO", "NATIONALUM", "HINDZINC"),
    "auto_components": ("MOTHERSON", "BHARATFORG", "BOSCHLTD", "EXIDEIND", "SUNDRMFAST"),
    "solar": ("WEBELSOLAR", "BORORENEW", "SUZLON", "INOXWIND"),
    "pharmaceuticals": ("SUNPHARMA", "DRREDDY", "CIPLA", "LUPIN", "AUROPHARMA", "TORNTPHARM"),
}


def sector_of(symbol: str) -> str | None:
    """Reverse lookup for FR14's per-sector Hawkes re-estimation."""
    for sector, names in TARIFF_SECTOR_BASKET.items():
        if symbol in names:
            return sector
    return None


def build_symbol_list(core_members: "list[str] | tuple[str, ...]") -> tuple[str, ...]:
    """Liquidity core (in rank order) plus the tariff basket, de-duplicated.

    `core_members` is the C3 snapshot's `members`, already ranked by six-month
    median traded value, so the first CORE_N entries are the most liquid names.
    """
    out: list[str] = []
    seen: set[str] = set()
    # ETFs are excluded here as well as in C3: an index ETF's "jumps" are
    # index-level moves, so pooling them into the Hawkes event stream would
    # double-count market-wide shocks as if they were independent events.
    for s in list(core_members):
        if len(out) >= CORE_N:
            break
        if s not in seen and is_equity(s):
            out.append(s)
            seen.add(s)
    for names in TARIFF_SECTOR_BASKET.values():
        for s in names:
            if s not in seen:
                out.append(s)
                seen.add(s)
    return tuple(out)
