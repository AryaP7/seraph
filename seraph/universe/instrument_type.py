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

**FIX09 — an absent classification table is a failure, not a pass.** It used
to return an empty set, and `is_equity()` then accepted every symbol, which
silently readmits ETFs to the equity universe. The table's availability is now
an explicit status that callers must handle: `is_equity()` raises, and C3's
`build_snapshot()` returns `MISSING_DEPENDENCY` unless the caller opts into a
documented, visibly-degraded unclassified mode.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_ISIN_CSV = (
    Path(__file__).resolve().parents[2]
    / "vendor" / "eod2" / "src" / "eod2_data" / "isin.csv"
)
EQUITY_ISIN_PREFIX = "INE"
#: Below this, the file exists but is too sparse to be a usable classification
#: table — treated as unavailable rather than quietly filtering out real names.
MIN_USABLE_SYMBOLS = 100


class ClassificationUnavailable(RuntimeError):
    """Instrument classification is not available; no instrument may be assumed."""


@dataclass(frozen=True)
class ClassificationStatus:
    available: bool
    symbol_count: int
    source: str
    reason: str | None = None


@lru_cache(maxsize=1)
def equity_symbols() -> frozenset[str]:
    """Symbols whose ISIN marks them company equity.

    Returns an empty set when the vendor file is absent. Callers must consult
    `classification_status()` rather than reading an empty set as "no filter
    needed" — that was audit finding A14.
    """
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


def classification_status() -> ClassificationStatus:
    """Whether instrument classification can be relied on right now."""
    source = str(_ISIN_CSV)
    if not _ISIN_CSV.exists():
        return ClassificationStatus(False, 0, source,
                                    "ISIN table not found at the vendored path")
    table = equity_symbols()
    if len(table) < MIN_USABLE_SYMBOLS:
        return ClassificationStatus(
            False, len(table), source,
            f"ISIN table holds only {len(table)} equity symbols, below the "
            f"{MIN_USABLE_SYMBOLS} usable floor")
    return ClassificationStatus(True, len(table), source)


def is_equity(symbol: str) -> bool:
    """True when `symbol` is company equity.

    Raises `ClassificationUnavailable` when the ISIN table is missing or
    unusable. It never answers True by default: an unclassified instrument is
    unknown, not equity.
    """
    status = classification_status()
    if not status.available:
        raise ClassificationUnavailable(
            f"instrument classification unavailable ({status.reason}); "
            f"no symbol can be classified as equity")
    return symbol.upper() in equity_symbols()
