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

import hashlib
from bisect import bisect_right
from dataclasses import dataclass

from seraph.universe.instrument_type import (
    ClassificationUnavailable,
    classification_status,
    is_equity,
)

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
    # FIX09: if classification is unavailable, `is_equity` raises rather than
    # letting ETFs back in silently. Fail here rather than pool a basket whose
    # composition is unknown.
    status = classification_status()
    if not status.available:
        raise ClassificationUnavailable(
            f"cannot build the Hawkes symbol list: {status.reason}. Pooling an "
            f"unclassified basket would mix index ETF moves into the event stream")
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


# --------------------------------------------------------- basket timeline
# T05 / audit finding R11. The Hawkes writer resolved the universe once, at the
# end of the corpus, and pooled every historical window over that one basket
# while recording a point-in-time basket in the artefact. Resolving membership
# per window needs the whole snapshot history, not just its last row, so the
# history gets a type of its own rather than being re-derived at each call site.


@dataclass(frozen=True)
class BasketSnapshot:
    """One C3 universe snapshot, already reduced to the Hawkes symbol list."""

    rebalance_date: str
    basket: tuple[str, ...]
    members: int

    @property
    def digest(self) -> str:
        return hashlib.sha256("|".join(sorted(self.basket)).encode()).hexdigest()


class BasketTimeline:
    """Which Hawkes basket was in force on a given date.

    Snapshots are half-yearly in this corpus, so `at()` is a bisect over a few
    dozen rows. Dates are ISO strings throughout, which compare correctly and
    avoid a timezone question that does not arise for a rebalance date.
    """

    def __init__(self, snapshots: "list[BasketSnapshot] | tuple[BasketSnapshot, ...]"):
        ordered = sorted(snapshots, key=lambda s: s.rebalance_date)
        seen = [s.rebalance_date for s in ordered]
        if len(set(seen)) != len(seen):
            raise ValueError("two snapshots share a rebalance date")
        self.snapshots: tuple[BasketSnapshot, ...] = tuple(ordered)
        self._dates = [s.rebalance_date for s in self.snapshots]

    @classmethod
    def from_rows(cls, rows) -> "BasketTimeline":
        """Build from `(rebalance_date, members)` rows of `universe_snapshots`.

        Each snapshot's ranked member list goes through `build_symbol_list`, so
        the per-window basket is produced by exactly the same documented rule
        as the single basket the writer used before — the rule did not change,
        only how often it is applied.
        """
        out = []
        for row in rows:
            date = str(row["rebalance_date"] if not isinstance(row, tuple) else row[0])
            members = list(row["members"] if not isinstance(row, tuple) else row[1])
            out.append(BasketSnapshot(rebalance_date=date,
                                      basket=build_symbol_list(members),
                                      members=len(members)))
        return cls(out)

    def __len__(self) -> int:
        return len(self.snapshots)

    def at(self, date: str) -> "BasketSnapshot | None":
        """The snapshot in force on `date` — the latest one not after it."""
        i = bisect_right(self._dates, str(date))
        return self.snapshots[i - 1] if i else None

    def members_at(self, date: str) -> tuple[str, ...]:
        snapshot = self.at(date)
        return snapshot.basket if snapshot else ()

    @property
    def union(self) -> tuple[str, ...]:
        """Every symbol that was ever a member.

        This is the set the stream must load. Loading only the terminal basket
        is what dropped exited symbols from the windows they belonged to.
        """
        out: set[str] = set()
        for snapshot in self.snapshots:
            out.update(snapshot.basket)
        return tuple(sorted(out))

    def describe(self) -> dict:
        return dict(
            snapshots=len(self.snapshots),
            first=self._dates[0] if self._dates else None,
            last=self._dates[-1] if self._dates else None,
            union_size=len(self.union),
            terminal_size=len(self.snapshots[-1].basket) if self.snapshots else 0,
            never_in_terminal=sorted(
                set(self.union) - set(self.snapshots[-1].basket)) if self.snapshots else [],
        )
