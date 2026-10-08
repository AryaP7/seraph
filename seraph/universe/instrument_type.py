# C3 — Universe Constructor (FR52): equity-vs-fund classification.
"""FR52 selects from "NSE **equities**". EOD2's daily folder also contains
exchange-traded funds, and because the rule ranks by traded value they rank
highly: 20 of the 500 selected members were ETFs before this filter existed
(GOLDBEES, NIFTYBEES, LIQUIDBEES, SILVERBEES, BANKBEES, SETFNIF50, ...).

Leaving them in corrupts the RMT pillar specifically, and not subtly:

* **Index ETFs are near-exact linear combinations of other members.**
  NIFTYBEES, JUNIORBEES, BANKBEES and SETFNIF50 are by construction baskets of
  names already in the universe, so they inject mechanical, non-economic
  correlation straight into `C_t`. That inflates the leading eigenvalue — which
  is precisely the quantity `F_t`, `V_t^eig` and `AR_t` are built to measure.
  The pillar would read rising systemic coupling that is an artefact of its own
  constituent list.
* **Commodity ETFs** (GOLDBEES, SILVERBEES, SETFGOLD) track bullion, not Indian
  equity risk, and load on an unrelated factor.
* **Liquid-fund ETFs** (LIQUIDBEES, LIQUIDIETF) are money-market instruments
  with near-zero return variance by design — effectively constant columns in a
  correlation matrix.

**The rule.** Indian ISINs encode instrument type in their prefix: `INE` is
company equity, `INF` is mutual-fund/ETF units, `IN9`/`IN0` are other classes.
Filtering to `INE` is exact, reproducible from data already vendored, and
survivorship-safe — it classifies delisted companies correctly too, unlike a
live broker instrument dump which only lists what trades today.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_ISIN_CSV = (
    Path(__file__).resolve().parents[2]
    / "vendor" / "eod2" / "src" / "eod2_data" / "isin.csv"
)
EQUITY_ISIN_PREFIX = "INE"


@lru_cache(maxsize=1)
def equity_symbols() -> frozenset[str]:
    """Symbols whose ISIN marks them company equity. Empty set if the vendor
    file is absent — callers then apply no filter rather than silently
    emptying the universe."""
    if not _ISIN_CSV.exists():
        return frozenset()
    out: set[str] = set()
    with _ISIN_CSV.open(newline="", encoding="utf-8", errors="ignore") as fh:
        for row in csv.DictReader(fh):
            isin = (row.get("ISIN") or "").strip().upper()
            sym = (row.get("SYMBOL") or "").strip().upper()
            if sym and isin.startswith(EQUITY_ISIN_PREFIX):
                out.add(sym)
    return frozenset(out)


def is_equity(symbol: str) -> bool:
    """True when `symbol` is company equity, or when no ISIN table is available."""
    table = equity_symbols()
    return True if not table else symbol.upper() in table
