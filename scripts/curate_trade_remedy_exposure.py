"""NI12 — curate India→sector exposure edges from documents already acquired.

Every edge here is cited to a **first-party US government notice that is in
this store**, not to a figure transcribed from a summary. The script reads
the citation out of the store rather than taking it from a human, so the
reference on the edge is exactly the document the pipeline received.

What such a notice establishes, and nothing more: the United States has an
anti-dumping or countervailing proceeding covering this product *from India*,
which means the product is imported from India. That is a documented trade
relationship. It is **not** a revenue share, **not** a company exposure and
**not** a loss — so every edge written here is unsized, and no loss amount
can be derived from it.

Run:
  python scripts/curate_trade_remedy_exposure.py            # show the plan
  python scripts/curate_trade_remedy_exposure.py --write    # append the rows
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.dashboard.news_view import news_channel          # noqa: E402
from seraph.news.acquisition import NewsStore, _now          # noqa: E402
from seraph.news.registry import load_master_data            # noqa: E402

CURATED = ROOT / "seraph/news/curated/exposure.csv"
STORE = ROOT / "prototype_runs/news-intelligence-pilot.sqlite"

#: sector -> (edge id, product terms, a headline substring that identifies a
#: document in the store good enough to cite for this product family).
#:
#: The product terms are deliberately narrow. An earlier version of the steel
#: edge matched `chromium` and `graphite electrode` and duly reported "adverse
#: for the steel sector": chromium trioxide is a metal-finishing chemical and
#: graphite electrodes are a consumable INPUT to electric-arc steelmaking.
FAMILIES = [
    dict(sector="chemicals", edge_id="india_chemicals_us_trade_remedy",
         products=["chromium trioxide", "perfluoroalkoxy",
                   "polyethylene terephthalate"],
         cite_on="Chromium Trioxide From India: Final Affirmative Determination",
         note=("US anti-dumping and countervailing proceedings cover chemical "
               "products from India, which establishes the import trade "
               "exists. It is NOT a revenue share and NOT a company "
               "exposure; the edge is unsized. Chromium trioxide is a "
               "metal-finishing chemical, not a steel article.")),
    dict(sector="aluminium", edge_id="india_aluminium_us_trade_remedy",
         products=["aluminum sheet", "aluminium sheet", "common alloy"],
         cite_on="Common Alloy Aluminum Sheet From Bahrain",
         note=("A US five-year review covers common alloy aluminium sheet "
               "from a group of countries including India, which establishes "
               "the import trade exists. Unsized: the review names no Indian "
               "volume or share.")),
    dict(sector="agriculture", edge_id="india_agriculture_us_trade_remedy",
         products=["oleoresin paprika", "warmwater shrimp", "shrimp"],
         cite_on="Oleoresin Paprika From India: Antidumping Duty Order",
         note=("US duty orders cover Indian agricultural and marine products, "
               "which establishes the export trade exists. Unsized, and a "
               "product-level measure is not sector revenue exposure.")),
    dict(sector="textiles", edge_id="india_textiles_us_trade_remedy",
         products=["polyester staple fiber", "denier polyester",
                   "polyester staple"],
         cite_on="Fine Denier Polyester Staple Fiber From India",
         note=("US anti-dumping proceedings cover Indian man-made fibre, "
               "which establishes the export trade exists. Unsized: the "
               "notice names no Indian volume or share.")),
    dict(sector="paper_packaging", edge_id="india_paper_us_trade_remedy",
         products=["paper shopping bags", "shopping bags"],
         cite_on="Certain Paper Shopping Bags From India",
         note=("US duty proceedings cover Indian paper packaging, which "
               "establishes the export trade exists. Unsized.")),
    # Graphite electrodes are a CONSUMABLE INPUT to electric-arc steelmaking,
    # not a steel article. An earlier version of the steel edge matched them
    # and reported "adverse for the steel sector", which is the wrong sector
    # AND the wrong direction -- a duty on Indian electrode EXPORTS is
    # adverse to the Indian electrode maker, not to Indian steelmakers, who
    # buy them. They get their own sector for exactly that reason.
    dict(sector="industrial_materials",
         edge_id="india_industrial_materials_us_trade_remedy",
         products=["graphite electrode", "graphite electrodes"],
         cite_on="Large Diameter Graphite Electrodes From India",
         note=("US proceedings cover Indian graphite electrodes, which "
               "establishes the export trade exists. These are a consumable "
               "INPUT to electric-arc steelmaking, not a steel article: the "
               "exposed party is the Indian electrode producer, not Indian "
               "steelmakers. Unsized.")),
]

HEADER_ORDER = ["edge_id", "from_id", "to_id", "mechanism", "magnitude",
                "unit", "confidence", "valid_from", "valid_to", "note",
                "source_ref", "known_from", "known_to", "registry_version",
                "event_types", "products", "target_role"]


def citations() -> dict:
    """headline substring -> the document URL this store actually received."""
    store = NewsStore(STORE)
    master, _ = load_master_data()
    channel = news_channel(store, master, decision_ts=_now(), limit=2000)
    references = channel["references"]
    found = {}
    for event in channel["eligible_events"]:
        for family in FAMILIES:
            if family["cite_on"].lower() in event.headline.lower():
                for ref in references.get(event.event_id, ()):
                    if (ref.get("url") or "").startswith("http"):
                        found.setdefault(family["cite_on"], ref["url"])
                        break
    return found


def main(write: bool) -> int:
    found = citations()
    existing = set()
    if CURATED.exists():
        with CURATED.open(newline="", encoding="utf-8") as handle:
            rows = csv.DictReader(
                line for line in handle if not line.lstrip().startswith("#"))
            existing = {r["edge_id"] for r in rows if r.get("edge_id")}

    planned, skipped = [], []
    for family in FAMILIES:
        url = found.get(family["cite_on"])
        if family["edge_id"] in existing:
            skipped.append((family["edge_id"], "already curated"))
            continue
        if not url:
            # No citation means no edge. An uncited relationship is an
            # assertion, and the loader refuses it anyway.
            skipped.append((family["edge_id"],
                            f"no acquired document matching "
                            f"{family['cite_on']!r}"))
            continue
        planned.append(dict(
            edge_id=family["edge_id"], from_id="in",
            to_id="sector:" + family["sector"], mechanism="export",
            magnitude="", unit="", confidence="medium",
            valid_from="", valid_to="", note=family["note"], source_ref=url,
            known_from=_now(), known_to="",
            registry_version="pilot-2026-10-17.3",
            event_types="trade_remedy_determination",
            products="|".join(family["products"]), target_role="exporter"))

    for edge_id, why in skipped:
        print(f"[skip]  {edge_id}: {why}")
    for row in planned:
        print(f"[plan]  {row['edge_id']} -> {row['to_id']}")
        print(f"        products: {row['products']}")
        print(f"        cite    : {row['source_ref'][:100]}")

    if not write:
        print(f"\n{len(planned)} edge(s) planned. Re-run with --write to append.")
        return 0
    if not planned:
        print("\nnothing to write")
        return 0
    with CURATED.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER_ORDER,
                                lineterminator="\n")
        for row in planned:
            writer.writerow(row)
    print(f"\nappended {len(planned)} edge(s) to {CURATED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    raise SystemExit(main(ap.parse_args().write))
