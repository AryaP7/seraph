"""Curate listed issuers from the exchange feed that actually names them.

NSE's corporate-announcement RSS carries the FILING ENTITY as its title and
nothing else — "JSW Steel Limited", "Vedanta Limited". The subject of the
announcement is in the body, which is not retained because the feed's terms
have not been read. So the title alone cannot say what happened, but it is an
authoritative statement that this entity files on this exchange, and that is
exactly what an entity registry needs.

**Sectors are assigned only where the assignment is not in doubt.** A wrong
issuer-to-sector link puts a news event on somebody else's balance sheet, and
a small cap whose business I cannot establish from the feed gets no sector
rather than a plausible guess. `sector` is blank for those, and they are still
useful: an announcement resolves to a named entity even when it routes nowhere.

**ETFs are not operating companies.** A Quantum Gold ETF announcement is a fund
notice, not an issuer event, and it is deliberately not registered as an
issuer.

Run:
  python scripts/curate_nse_issuers.py          # show the plan
  python scripts/curate_nse_issuers.py --write  # append the rows
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CURATED = ROOT / "seraph/news/curated/entities.csv"
STORE = ROOT / "prototype_runs/news-intelligence-pilot.sqlite"
FEED = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"

#: entity_id -> (name, sector or None, aliases)
#: A sector appears only where the company's primary business is not in doubt.
#: Everything else is registered without one on purpose.
ISSUERS = {
    "jsw_steel": ("JSW Steel Limited", "steel", "JSW Steel"),
    "vedanta": ("Vedanta Limited", "metals_mining", "Vedanta"),
    "oil_india": ("Oil India Limited", "energy", "Oil India|OIL"),
    "sbi_cards": ("SBI Cards and Payment Services Limited", "financials",
                  "SBI Cards|SBI Card"),
    "cyient": ("Cyient Limited", "it_services", "Cyient"),
    "railtel": ("Railtel Corporation Of India Limited", "telecom",
                "RailTel|Railtel Corporation"),
    "kpi_green_energy": ("KPI Green Energy Limited", "energy",
                         "KPI Green|KPI Green Energy"),
    "camlin_fine_sciences": ("Camlin Fine Sciences Limited", "chemicals",
                             "Camlin Fine"),
    "zen_technologies": ("Zen Technologies Limited", "defence", "Zen Tech"),
    "prime_securities": ("Prime Securities Limited", "financials",
                         "Prime Securities"),
    # Business not established from the feed; registered WITHOUT a sector
    # rather than guessed. They still resolve as named entities.
    "cyber_media_research": ("Cyber Media Research & Services Limited", None,
                             "Cyber Media Research"),
    "master_components": ("Master Components Limited", None, ""),
    "jay_jalaram_technologies": ("Jay Jalaram Technologies Limited", None, ""),
    "ltm_limited": ("LTM Limited", None, ""),
}

#: Seen in the feed and deliberately NOT registered as issuers.
NOT_ISSUERS = {
    "Quantum Gold ETF": "an exchange-traded fund, not an operating company",
    "Quantum Nifty 50 ETF": "an exchange-traded fund, not an operating company",
}

HEADER = ["entity_id", "name", "kind", "symbol", "isin", "sector", "parent_id",
          "valid_from", "valid_to", "aliases", "source_ref", "known_from"]


def seen_in_feed() -> set[str]:
    """Issuer names the stored NSE feed actually carried."""
    if not STORE.exists():
        return set()
    with sqlite3.connect(STORE) as db:
        return {row[0] for row in db.execute(
            "SELECT DISTINCT title FROM stories "
            "WHERE source_id='nse_corporate_announcements'")}


def main(write: bool) -> int:
    from seraph.news.acquisition import _now

    existing = set()
    if CURATED.exists():
        with CURATED.open(newline="", encoding="utf-8") as handle:
            rows = csv.DictReader(
                line for line in handle if not line.lstrip().startswith("#"))
            existing = {r["entity_id"] for r in rows if r.get("entity_id")}

    present = seen_in_feed()
    planned, skipped = [], []
    for entity_id, (name, sector, aliases) in sorted(ISSUERS.items()):
        if entity_id in existing:
            skipped.append((entity_id, "already curated"))
            continue
        if present and name not in present:
            # Only register what the feed actually named. Adding an issuer the
            # source never mentioned would be padding the registry.
            skipped.append((entity_id, f"{name!r} not present in the stored feed"))
            continue
        planned.append({
            "entity_id": entity_id, "name": name, "kind": "issuer",
            "symbol": "", "isin": "", "sector": sector or "", "parent_id": "",
            "valid_from": "", "valid_to": "", "aliases": aliases,
            "source_ref": FEED, "known_from": _now()})

    for entity_id, why in skipped:
        print(f"[skip]  {entity_id}: {why}")
    for name, why in NOT_ISSUERS.items():
        print(f"[omit]  {name}: {why}")
    for row in planned:
        sector = row["sector"] or "(no sector: business not established)"
        print(f"[plan]  {row['entity_id']:26s} {sector}")

    if not write:
        print(f"\n{len(planned)} issuer(s) planned. Re-run with --write.")
        return 0
    if not planned:
        print("\nnothing to write")
        return 0
    with CURATED.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, lineterminator="\n")
        for row in planned:
            writer.writerow(row)
    print(f"\nappended {len(planned)} issuer(s) to {CURATED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    raise SystemExit(main(ap.parse_args().write))
